import asyncio
import logging
import typing as t
from datetime import datetime

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_number, text_to_file

from .common.formatting import humanize_size
from .common.models import DB
from .common.serializers import GuildBackup
from .common.views import BackupMenu

log = logging.getLogger("red.vrt.cartographer")
_ = Translator("Cartographer", __file__)
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


# redgettext -D main.py common/formatting.py common/models.py common/serializers.py common/views.py --command-docstring


@cog_i18n(_)
class Cartographer(commands.Cog):
    """
    Backup & Restore tools for Discord servers.

    This cog can backup & restore the following:
    - Bans (including reason)
    - Categories (permissions/order)
    - Text channels (permissions/order)
    - Voice channels (permissions/order)
    - Forum channels  (permissions/order)[Not forum posts]
    - Roles (permissions/color/name/icon and what members they're assigned to)
    - Emojis (name/roles, Very slow and rate limit heavy)
    - Stickers (name/description, Very slow and rate limit heavy)
    - Members (roles and nicknames)
    - Messages (Optional, can be disabled)
    - Server icon/banner/splash/discovery splash/description/name
    - All server verification/security settings
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.1.8"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})

        self.root = cog_data_path(self)
        self.backups_dir = self.root / "backups"

        self.db: DB = DB()
        self.saving = False

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        self.auto_backup.cancel()

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")
        self.auto_backup.start()

    async def save(self) -> None:
        if self.saving:
            return
        try:
            self.saving = True
            dump = await asyncio.to_thread(self.db.model_dump, mode="json")
            await self.config.db.set(dump)
        except Exception as e:
            log.exception("Failed to save config", exc_info=e)
        finally:
            self.saving = False

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = _("Version: {}\nAuthor: {}").format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        """No data to delete"""

    @tasks.loop(minutes=1)
    async def auto_backup(self):
        if not self.db.allow_auto_backups:
            return
        now = datetime.now().astimezone()
        save = False
        for guild_id in list(self.db.configs.keys()):
            settings = self.db.configs[guild_id]
            if not settings.auto_backup_interval_hours:
                continue
            if guild_id in self.db.ignored_guilds:
                continue
            if self.db.allowed_guilds and guild_id not in self.db.allowed_guilds:
                continue
            guild = self.bot.get_guild(guild_id)
            if not guild:
                log.info("Removing guild %s from backups", guild_id)
                # Delete the backups
                del self.db.configs[guild_id]
                path = self.backups_dir / str(guild_id)
                if path.exists():
                    for backup in path.iterdir():
                        backup.unlink()
                    path.rmdir()
                continue

            delta_hours = (now.timestamp() - settings.last_backup.timestamp()) / 3600
            if int(delta_hours) < int(settings.auto_backup_interval_hours):
                continue

            await settings.backup(
                guild=guild,
                backups_dir=self.backups_dir,
                limit=self.db.message_backup_limit,
                backup_members=self.db.backup_members,
                backup_roles=self.db.backup_roles,
                backup_emojis=self.db.backup_emojis,
                backup_stickers=self.db.backup_stickers,
            )
            save = True
            self.db.cleanup(guild, self.backups_dir)

        if save:
            await self.save()

    @commands.command(name="cartographer", aliases=["carto"])
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(administrator=True)
    @commands.guild_only()
    async def cartographer_menu(self, ctx: commands.Context):
        """Open the Backup/Restore menu

        This cog can backup & restore the following:
        - Bans (including reason)
        - Categories (permissions/order)
        - Text channels (permissions/order)
        - Voice channels (permissions/order)
        - Forum channels  (permissions/order)[Not forum posts]
        - Roles (permissions/color/name/icon and what members they're assigned to)
        - Emojis (name/roles, Very slow and rate limit heavy)
        - Stickers (name/description, Very slow and rate limit heavy)
        - Members (roles and nicknames)
        - Messages (Optional, can be disabled)
        - Server icon/banner/splash/discovery splash/description/name
        - All server verification/security settings
        """
        if ctx.guild.id in self.db.ignored_guilds:
            txt = _("This server is in the ingored list!")
            return await ctx.send(txt)
        if self.db.allowed_guilds and ctx.guild.id not in self.db.allowed_guilds:
            txt = _("This server is not in the allowed list!")
            return await ctx.send(txt)

        guild_backups_folder = self.backups_dir / str(ctx.guild.id)
        guild_backups_folder.mkdir(parents=True, exist_ok=True)
        view = BackupMenu(ctx, self.db, guild_backups_folder)
        try:
            await view.start()
            await view.wait()
        finally:
            await self.save()

    @commands.group(name="cartographerset", aliases=["cartoset"])
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def cartographer_base(self, ctx: commands.Context):
        """Backup & Restore Tools"""

    @cartographer_base.command(name="wipebackups")
    @commands.is_owner()
    async def wipe_all_backups(self, ctx: commands.Context, confirm: bool):
        """
        Wipe all backups for all servers

        This action cannot be undone!
        """
        if not confirm:
            return await ctx.send(_("Please confirm this action by passing `True` as an argument"))

        self.backups_dir.mkdir(parents=True, exist_ok=True)
        for guild_backup_folder in self.backups_dir.iterdir():
            for backup in guild_backup_folder.iterdir():
                backup.unlink()
            guild_backup_folder.rmdir()

        await self.save()
        await ctx.send(_("All backups have been wiped!"))

    @cartographer_base.command(name="backup")
    async def backup_server(self, ctx: commands.Context, limit: int = 0):
        """
        Create a backup of this server

        limit: How many messages to backup per channel (0 for None)
        """
        if ctx.guild.id in self.db.ignored_guilds:
            txt = _("This server is in the ingored list!")
            return await ctx.send(txt)
        if self.db.allowed_guilds and ctx.guild.id not in self.db.allowed_guilds:
            txt = _("This server is not in the allowed list!")
            return await ctx.send(txt)

        async with ctx.typing():
            conf = self.db.get_conf(ctx.guild)
            await conf.backup(
                guild=ctx.guild,
                backups_dir=self.backups_dir,
                limit=limit,
                backup_members=self.db.backup_members,
                backup_roles=self.db.backup_roles,
                backup_emojis=self.db.backup_emojis,
                backup_stickers=self.db.backup_stickers,
            )
            await ctx.send(_("A backup has been created!"))
            await self.save()

    @cartographer_base.command(name="restorelatest")
    @commands.bot_has_permissions(administrator=True)
    async def restore_server_latest(self, ctx: commands.Context):
        """
        Restore the latest backup for this server
        """
        if ctx.guild.id in self.db.ignored_guilds:
            txt = _("This server is in the ingored list!")
            return await ctx.send(txt)
        if self.db.allowed_guilds and ctx.guild.id not in self.db.allowed_guilds:
            txt = _("This server is not in the allowed list!")
            return await ctx.send(txt)

        async with ctx.typing():
            backups = self.backups_dir / str(ctx.guild.id)
            if not backups.exists():
                txt = _("There are no backups for this guild!")
                return await ctx.send(txt)
            latest = sorted(backups.iterdir(), key=lambda x: x.stat().st_mtime)[-1]
            backup = await asyncio.to_thread(GuildBackup.model_validate_json, latest.read_text(encoding="utf-8"))
            results = await backup.restore(ctx.guild, ctx.channel)
            await ctx.send(_("Server restore is complete!"))
            if results:
                txt = _("The following errors occurred while restoring the backup")
                await ctx.send(txt, file=text_to_file(results, "restore_results.txt"))

    @cartographer_base.command(name="view")
    @commands.is_owner()
    async def view_settings(self, ctx: commands.Context):
        """View current global settings"""
        all_backups = 0
        total_size = 0
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        for guild_backup_folder in self.backups_dir.iterdir():
            all_backups += len(list(guild_backup_folder.iterdir()))
            for backup in guild_backup_folder.iterdir():
                total_size += backup.stat().st_size

        ignored = ", ".join([f"`{i}`" for i in self.db.ignored_guilds]) if self.db.ignored_guilds else _("**None Set**")
        allowed = ", ".join([f"`{i}`" for i in self.db.allowed_guilds]) if self.db.allowed_guilds else _("**None Set**")

        txt = _(
            "### Global Settings\n"
            "- Global backups: {}\n"
            "- Max backups per server: {}\n"
            "- Allow auto-backups: {}\n"
            "- Message backup limit: {}\n"
            "- Backup Members: {}\n"
            "- Backup Roles: {}\n"
            "- Backup Emojis: {}\n"
            "- Backup Stickers: {}\n"
            "- Ignored servers: {}\n"
            "- Allowed servers: {}\n"
        ).format(
            f"**{humanize_number(all_backups)}** ({humanize_size(total_size)})",
            f"**{self.db.max_backups_per_guild}**",
            f"**{self.db.allow_auto_backups}**",
            f"**{self.db.message_backup_limit}**",
            f"**{self.db.backup_members}**",
            f"**{self.db.backup_roles}**",
            f"**{self.db.backup_emojis}**",
            f"**{self.db.backup_stickers}**",
            ignored,
            allowed,
        )
        await ctx.send(txt)

    @cartographer_base.command(name="autobackups")
    @commands.is_owner()
    async def toggle_auto_backups(self, ctx: commands.Context):
        """Enable/Disable allowing auto backups"""
        if self.db.allow_auto_backups:
            self.db.allow_auto_backups = False
            txt = _("Auto backups have been **Disabled**")
        else:
            self.db.allow_auto_backups = True
            txt = _("Auto backups have been **Enabled**")
        await ctx.send(txt)
        await self.save()

    @cartographer_base.command(name="messagelimit")
    @commands.is_owner()
    async def set_message_limit(self, ctx: commands.Context, limit: int):
        """Set the message backup limit per channel for auto backups

        Set to 0 to disable message backups

        ⚠️**Warning**⚠️
        Setting this to a high number can cause backups to be slow and take up a lot of space.
        """
        if limit < 0:
            return await ctx.send(_("Limit must be 0 or higher"))
        self.db.message_backup_limit = limit
        if limit == 0:
            await ctx.send(_("Message backup has been **Disabled**"))
        else:
            await ctx.send(_("Message backup limit has been set"))
        await self.save()

    @cartographer_base.command(name="backupmembers")
    @commands.is_owner()
    async def toggle_backup_members(self, ctx: commands.Context):
        """Toggle backing up members

        ⚠️**Warning**⚠️
        Restoring the roles of all members can be slow for large servers.
        """
        self.db.backup_members = not self.db.backup_members
        warning = _("\n⚠️**Warning**⚠️\nRestoring the roles of all members can be slow for large servers.")
        if self.db.backup_members:
            txt = _("Members will now be backed up") + warning
        else:
            txt = _("Members will no longer be backed up")
        await ctx.send(txt)
        await self.save()

    @cartographer_base.command(name="backuproles")
    @commands.is_owner()
    async def toggle_backup_roles(self, ctx: commands.Context):
        """Toggle backing up roles

        ⚠️**Warning**⚠️
        Any roles above the bot's role will not be restored.
        """
        self.db.backup_roles = not self.db.backup_roles
        warning = _("\n⚠️**Warning**⚠️\nAny roles above the bot's role will not be restored.")
        if self.db.backup_roles:
            txt = _("Roles will now be backed up") + warning
        else:
            txt = _("Roles will no longer be backed up")
        await ctx.send(txt)
        await self.save()

    @cartographer_base.command(name="backupemojis")
    @commands.is_owner()
    async def toggle_backup_emojis(self, ctx: commands.Context):
        """Toggle backing up emojis

        ⚠️**Warning**⚠️
        Restoring emojis is EXTREMELY rate-limited and can take a long time (like hours) for servers with many emojis.
        """
        self.db.backup_emojis = not self.db.backup_emojis
        warning = _(
            "\n⚠️**Warning**⚠️\nRestoring emojis is EXTREMELY rate-limited and can take a long time (like hours) for servers with many emojis."
        )
        if self.db.backup_emojis:
            txt = _("Emojis will now be backed up") + warning
        else:
            txt = _("Emojis will no longer be backed up")
        await ctx.send(txt)
        await self.save()

    @cartographer_base.command(name="backupstickers")
    @commands.is_owner()
    async def toggle_backup_stickers(self, ctx: commands.Context):
        """Toggle backing up stickers

        ⚠️**Warning**⚠️
        Restoring stickers is EXTREMELY rate-limited and can take a long time (like hours) for servers with many stickers.
        """
        self.db.backup_stickers = not self.db.backup_stickers
        warning = _(
            "\n⚠️**Warning**⚠️\nRestoring stickers is EXTREMELY rate-limited and can take a long time (like hours) for servers with many stickers."
        )
        if self.db.backup_stickers:
            txt = _("Stickers will now be backed up") + warning
        else:
            txt = _("Stickers will no longer be backed up")
        await ctx.send(txt)
        await self.save()

    @cartographer_base.command(name="maxbackups")
    @commands.is_owner()
    async def set_max_backups(self, ctx: commands.Context, max_backups: int):
        """Set the max amount of backups a server can have"""
        self.db.max_backups_per_guild = max_backups
        if max_backups == 0:
            txt = _("Max backups set to 0, Cartographer has been **Disabled**")
        else:
            txt = _("Max backup count has been set")
        await ctx.send(txt)
        await self.save()

    @cartographer_base.command(name="ignore")
    @commands.is_owner()
    async def ignore_list(self, ctx: commands.Context, guild: discord.Guild):
        """Add/Remove a server from the ignore list"""
        if guild.id in self.db.ignored_guilds:
            self.db.ignored_guilds.remove(guild.id)
            txt = _("Server removed from the ignore list")
        else:
            self.db.ignored_guilds.append(guild.id)
            txt = _("Server added to the ignore list")
        await ctx.send(txt)
        await self.save()

    @cartographer_base.command(name="allow")
    @commands.is_owner()
    async def allow_list(self, ctx: commands.Context, guild: discord.Guild):
        """Add/Remove a server from the allow list"""
        if guild.id in self.db.allowed_guilds:
            self.db.allowed_guilds.remove(guild.id)
            txt = _("Server removed from the allow list")
        else:
            self.db.allowed_guilds.append(guild.id)
            txt = _("Server added to the allow list")
        await ctx.send(txt)
        await self.save()
