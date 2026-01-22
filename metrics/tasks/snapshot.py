import asyncio
import logging
import os
from collections import defaultdict
from time import perf_counter

import discord
import psutil
from discord.ext import tasks
from redbot.core import bank
from redbot.core.utils import AsyncIter

from ..abc import MixinMeta
from ..db.tables import (
    GlobalEconomySnapshot,
    GlobalMemberSnapshot,
    GlobalPerformanceSnapshot,
    GlobalSettings,
    GuildEconomySnapshot,
    GuildMemberSnapshot,
    GuildSettings,
)

log = logging.getLogger("red.vrt.metrics.tasks.snapshot")


class Snapshot(MixinMeta):
    def configure_task_intervals(self, settings: GlobalSettings) -> None:
        """Configure all task loop intervals based on settings."""
        if settings.economy_interval != 10:
            self.economy_snapshot_task.change_interval(minutes=settings.economy_interval)
        if settings.member_interval != 15:
            self.member_snapshot_task.change_interval(minutes=settings.member_interval)
        if settings.performance_interval != 3:
            self.performance_snapshot_task.change_interval(minutes=settings.performance_interval)

    def change_economy_interval(self, minutes: int) -> None:
        """Change the economy snapshot interval in minutes."""
        self.economy_snapshot_task.change_interval(minutes=minutes)
        log.info(f"Economy snapshot interval changed to {minutes} minutes.")

    def change_member_interval(self, minutes: int) -> None:
        """Change the member snapshot interval in minutes."""
        self.member_snapshot_task.change_interval(minutes=minutes)
        log.info(f"Member snapshot interval changed to {minutes} minutes.")

    def change_performance_interval(self, minutes: int) -> None:
        """Change the performance snapshot interval in minutes."""
        self.performance_snapshot_task.change_interval(minutes=minutes)
        log.info(f"Performance snapshot interval changed to {minutes} minutes.")

    # =========================================================================
    # Economy Snapshot Task
    # =========================================================================

    @tasks.loop(minutes=10)
    async def economy_snapshot_task(self) -> None:
        """Capture economy/bank statistics."""
        if not self.db_active():
            return

        global_config: GlobalSettings = await self.db_utils.get_create_global_settings()
        if not global_config.track_bank:
            return

        is_global = await bank.is_global()
        global_bank_balances: dict[int, int] = defaultdict(int)

        # Collect global bank data first
        if is_global:
            members = await bank._config.all_users()
            for user_id, wallet in members.items():
                global_bank_balances[user_id] += wallet["balance"]

        # Guild-level economy snapshots
        guild_snapshots: list[GuildEconomySnapshot] = []
        guild_settings = await GuildSettings.objects().where(GuildSettings.track_bank.eq(True))

        for settings in guild_settings:
            if is_global:
                continue  # Skip guild-level tracking when economy is global

            guild = self.bot.get_guild(settings.id)
            if not guild:
                continue

            members = await bank._config.all_members(guild)
            if not members:
                continue

            bank_total = sum(value["balance"] for value in members.values())
            average_balance = bank_total // len(members) if members else 0

            # Add to global tracking
            for user_id, wallet in members.items():
                global_bank_balances[user_id] += wallet["balance"]

            guild_snapshots.append(
                GuildEconomySnapshot(
                    guild=settings.id,
                    bank_total=bank_total,
                    average_balance=average_balance,
                    member_count=len(members),
                )
            )

        if guild_snapshots:
            await GuildEconomySnapshot.insert(*guild_snapshots)

        # Global economy snapshot
        if global_bank_balances:
            global_bank_total = sum(global_bank_balances.values())
            global_average_balance = global_bank_total // len(global_bank_balances) if global_bank_balances else 0

            await GlobalEconomySnapshot(
                bank_total=global_bank_total,
                average_balance=global_average_balance,
                member_count=len(global_bank_balances),
                guild_count=len(guild_snapshots) if not is_global else None,
            ).save()

    # =========================================================================
    # Member Snapshot Task
    # =========================================================================

    @tasks.loop(minutes=15)
    async def member_snapshot_task(self) -> None:
        """Capture member statistics."""
        if not self.db_active():
            return

        global_config: GlobalSettings = await self.db_utils.get_create_global_settings()
        if not global_config.track_members:
            return

        # Guild-level member snapshots
        guild_snapshots: list[GuildMemberSnapshot] = []
        guild_settings = await GuildSettings.objects().where(GuildSettings.track_members.eq(True))

        for settings in guild_settings:
            guild = self.bot.get_guild(settings.id)
            if not guild:
                continue

            member_total = guild.member_count or 0
            online_members, idle_members, dnd_members, offline_members = 0, 0, 0, 0

            async for member in AsyncIter(guild.members):
                match member.status:
                    case discord.Status.online:
                        online_members += 1
                    case discord.Status.idle:
                        idle_members += 1
                    case discord.Status.dnd:
                        dnd_members += 1
                    case discord.Status.offline | discord.Status.invisible:
                        offline_members += 1

            guild_snapshots.append(
                GuildMemberSnapshot(
                    guild=settings.id,
                    member_total=member_total,
                    online_members=online_members,
                    idle_members=idle_members,
                    dnd_members=dnd_members,
                    offline_members=offline_members,
                )
            )

        if guild_snapshots:
            await GuildMemberSnapshot.insert(*guild_snapshots)

        # Global member snapshot
        members: dict[int, discord.Member] = {}
        for member in self.bot.get_all_members():
            if member.bot:
                continue
            members[member.id] = member

        global_member_total = len(members)
        global_online, global_idle, global_dnd, global_offline = 0, 0, 0, 0

        for member in members.values():
            match member.status:
                case discord.Status.online:
                    global_online += 1
                case discord.Status.idle:
                    global_idle += 1
                case discord.Status.dnd:
                    global_dnd += 1
                case discord.Status.offline | discord.Status.invisible:
                    global_offline += 1

        await GlobalMemberSnapshot(
            guild_count=len(self.bot.guilds),
            member_total=global_member_total,
            online_members=global_online,
            idle_members=global_idle,
            dnd_members=global_dnd,
            offline_members=global_offline,
        ).save()

    # =========================================================================
    # Performance Snapshot Task
    # =========================================================================

    @tasks.loop(minutes=3)
    async def performance_snapshot_task(self) -> None:
        """Capture bot/system performance metrics."""
        if not self.db_active():
            return

        global_config: GlobalSettings = await self.db_utils.get_create_global_settings()
        if not global_config.track_performance:
            return

        start = perf_counter()

        bot_process = psutil.Process(os.getpid())
        cpu_usage_percent = bot_process.cpu_percent(interval=0.1)
        memory_info = bot_process.memory_info()
        memory_used_mb = memory_info.rss / (1024 * 1024)
        memory_usage_percent = psutil.virtual_memory().percent
        active_tasks = len(asyncio.all_tasks())
        latency = self.bot.latency
        shard_count = self.bot.shard_count or 1
        guild_count = len(self.bot.guilds)

        await GlobalPerformanceSnapshot(
            latency_ms=latency * 1000,
            shard_count=shard_count,
            cpu_usage_percent=cpu_usage_percent,
            memory_usage_percent=memory_usage_percent,
            memory_used_mb=memory_used_mb,
            active_tasks=active_tasks,
            guild_count=guild_count,
            snapshot_duration_seconds=perf_counter() - start,
        ).save()
