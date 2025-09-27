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
from ..db.tables import GlobalSettings, GlobalSnapshot, GuildSettings, GuildSnapshot

log = logging.getLogger("red.vrt.metrics.tasks.snapshot")


class Snapshot(MixinMeta):
    def change_snapshot_interval(self, minutes: int) -> None:
        """Change the snapshot interval in minutes."""
        if minutes < 1:
            raise ValueError("Snapshot interval must be at least 1 minute.")
        self.take_snapshot.change_interval(minutes=minutes)
        log.info(f"Snapshot interval changed to {minutes} minutes.")

    @tasks.loop(minutes=5)
    async def take_snapshot(self) -> None:
        if not self.db_active():
            return
        start = perf_counter()
        is_global = await bank.is_global()
        global_config: GlobalSettings = await self.db_utils.get_create_global_settings()

        global_bank_balances: dict[int, int] = defaultdict(int)
        if is_global:
            members = await bank._config.all_users()
            for user_id, wallet in members.items():
                global_bank_balances[user_id] += wallet["balance"]

        guild_snapshots: list[GuildSnapshot] = []
        guild_settings = await GuildSettings.objects().where(
            (GuildSettings.track_bank.eq(True)) | (GuildSettings.track_members.eq(True))
        )
        for settings in guild_settings:
            if not settings.track_members and is_global:
                continue  # No need to process guilds not tracking members in global mode

            guild = self.bot.get_guild(settings.id)
            if not guild:
                continue

            bank_total = None
            average_balance = None
            if not is_global and settings.track_bank:
                members = await bank._config.all_members(guild)
                bank_total = sum(value["balance"] for value in members.values())
                average_balance = bank_total // len(members) if len(members) > 0 else 0
                for user_id, wallet in members.items():
                    global_bank_balances[user_id] += wallet["balance"]

            member_total = None
            online_members = None
            idle_members = None
            dnd_members = None
            offline_members = None
            if settings.track_members:
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
                        case _:
                            log.error(f"Unknown status for member {member.id} in guild {guild.id}: {member.status}")

            if any(
                [
                    bank_total,
                    average_balance,
                    member_total,
                    online_members,
                    idle_members,
                    dnd_members,
                    offline_members,
                ]
            ):
                guild_snapshot = GuildSnapshot(
                    guild=settings.id,
                    bank_total=bank_total,
                    average_balance=average_balance,
                    member_total=member_total,
                    online_members=online_members,
                    idle_members=idle_members,
                    dnd_members=dnd_members,
                    offline_members=offline_members,
                )
                guild_snapshots.append(guild_snapshot)

        if guild_snapshots:
            await GuildSnapshot.insert(*guild_snapshots)

        # Global Snapshots
        if global_config.track_bank or global_config.track_members or global_config.track_performance:
            global_bank_total = None
            global_average_balance = None
            if global_config.track_bank:
                global_bank_total = sum(global_bank_balances.values())
                global_average_balance = (
                    global_bank_total // len(global_bank_balances) if len(global_bank_balances) > 0 else 0
                )

            global_member_total = None
            global_online_members = None
            global_idle_members = None
            global_dnd_members = None
            global_offline_members = None
            if global_config.track_members:
                (
                    global_member_total,
                    global_online_members,
                    global_idle_members,
                    global_dnd_members,
                    global_offline_members,
                ) = 0, 0, 0, 0, 0
                members = {}
                for member in self.bot.get_all_members():
                    if member.bot:
                        continue
                    members[member.id] = member
                global_member_total = len(members)
                for member in members.values():
                    match member.status.value:
                        case discord.Status.online:
                            global_online_members += 1
                        case discord.Status.idle:
                            global_idle_members += 1
                        case discord.Status.dnd:
                            global_dnd_members += 1
                        case discord.Status.offline | discord.Status.invisible:
                            global_offline_members += 1
                        case _:
                            log.error(f"Unknown status for member {member.id} in global snapshot: {member.status}")

            if global_config.track_performance:
                bot_process = psutil.Process(os.getpid())
                cpu_usage_percent = bot_process.cpu_percent(interval=0.1)
                memory_usage_percent = psutil.virtual_memory().percent
                active_tasks = len(asyncio.all_tasks())
                latency = self.bot.latency
            else:
                cpu_usage_percent = None
                memory_usage_percent = None
                active_tasks = None
                latency = None

            if any(
                [
                    global_bank_balances,
                    global_average_balance,
                    global_member_total,
                    global_online_members,
                    global_idle_members,
                    global_dnd_members,
                    global_offline_members,
                    latency,
                    cpu_usage_percent,
                    memory_usage_percent,
                    active_tasks,
                ]
            ):
                global_snapshot = GlobalSnapshot(
                    bank_total=global_bank_total,
                    average_balance=global_average_balance,
                    member_total=global_member_total,
                    online_members=global_online_members,
                    idle_members=global_idle_members,
                    dnd_members=global_dnd_members,
                    offline_members=global_offline_members,
                    latency_ms=latency * 1000 if latency else None,
                    cpu_usage_percent=cpu_usage_percent,
                    memory_usage_percent=memory_usage_percent,
                    active_tasks=active_tasks,
                    snapshot_duration_seconds=perf_counter() - start,
                )
                await global_snapshot.save()
