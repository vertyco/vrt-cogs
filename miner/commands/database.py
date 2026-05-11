import typing as t

import asyncpg
import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
from ..db.tables import Player, ensure_db_connection
from ..engine import engine
from ..views.postgres_creds import SetConnectionView


class DatabaseCommands(MixinMeta):
    @commands.group(name="minerdb")
    @commands.is_owner()
    async def dbsetgroup(self, ctx: commands.Context):
        """Database Commands"""

    @dbsetgroup.command(name="postgres")
    async def dbsetgroup_postgres(self, ctx: commands.Context):
        """Set the Postgres connection info"""
        await SetConnectionView(self, ctx).start()

    @dbsetgroup.command(name="nukedb")
    @ensure_db_connection()
    async def dbsetgroup_nukedb(self, ctx: commands.Context, confirm: bool):
        """Delete the database for this cog and reinitialize it

        THIS CANNOT BE UNDONE!"""
        if not confirm:
            return await ctx.send(f"You must confirm this action with `{ctx.clean_prefix}minerdb nukedb True`")
        config = await self.bot.get_shared_api_tokens("postgres")
        if not config:
            return await ctx.send(f"Postgres credentials not set! Use `{ctx.clean_prefix}minerdb postgres` command!")
        if self.db:
            tmp = self.db
            self.db = None
            tmp.pool.terminate()
        conn = None
        try:
            # Connect to the 'postgres' maintenance database to drop the target database
            config_copy = dict(config)
            config_copy["database"] = "postgres"
            try:
                conn = await asyncpg.connect(**config_copy)
            except asyncpg.InvalidPasswordError:
                return await ctx.send("Invalid password!")
            except asyncpg.InvalidCatalogNameError:
                return await ctx.send("Invalid database name!")
            except asyncpg.InvalidAuthorizationSpecificationError:
                return await ctx.send("Invalid user!")

            await conn.execute(f"DROP DATABASE IF EXISTS {engine.db_name(self)}")
        finally:
            if conn:
                await conn.close()

        await ctx.send("Database has been nuked, please reload the cog.")

    @dbsetgroup.command(name="diagnose")
    async def dbsetgroup_diagnose(self, ctx: commands.Context):
        """Check the database connection"""
        config = await self.bot.get_shared_api_tokens("postgres")
        if not config:
            return await ctx.send(f"Postgres credentials not set! Use `{ctx.clean_prefix}minerdb postgres` command!")
        issues = await engine.diagnose_issues(self, config)
        for p in pagify(issues, page_length=1980):
            await ctx.send(box(p, lang="python"))

    @dbsetgroup.command(name="cooldown")
    @ensure_db_connection()
    async def dbsetgroup_cooldown(self, ctx: commands.Context, seconds: commands.positive_int):
        """Set global `/rock` cooldown in seconds (enforced per guild)."""
        if seconds < 10:
            await ctx.send("Cooldown must be at least 10 seconds.")
            return
        if seconds > 3600:
            await ctx.send("Cooldown cannot exceed 3600 seconds (1 hour).")
            return

        settings = await self.db_utils.get_create_global_settings()
        settings.spawn_cooldown_seconds = seconds
        await settings.save()

        minutes = seconds // 60
        await ctx.send(f"Global rock spawn cooldown set to `{minutes} minute(s)` ({seconds}s).")

    @dbsetgroup.command(name="achievementsync")
    @ensure_db_connection()
    async def dbsetgroup_achievement_sync(self, ctx: commands.Context, user: t.Optional[discord.User] = None):
        """Backfill exact-only Miner achievements globally."""
        if user is not None:
            unlocked = await self.sync_player_achievements(user)
            if unlocked:
                names = ", ".join(achievement.name for achievement in unlocked)
                await ctx.send(f"Synced `{len(unlocked)}` achievements for {user.mention}: {names}")
            else:
                await ctx.send(f"No new retroactive achievements were found for {user.mention}.")
            return

        player_ids = await Player.select(Player.id).output(as_list=True)
        total_new = 0
        for player_id in player_ids:
            total_new += len(await self.sync_player_achievements(player_id))

        await ctx.send(
            f"Synced exact-only Miner achievements for `{len(player_ids)}` players. New unlocks recorded: `{total_new}`."
        )
