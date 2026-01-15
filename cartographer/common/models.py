from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import discord
from pydantic import Field
from redbot.core.i18n import Translator

from . import Base
from .serializers import GuildBackup

log = logging.getLogger("red.vrt.cartographer.models")
_ = Translator("Cartographer", __file__)


class RestoreOptions(Base):
    """Options for granular restore control."""

    # Category toggles - what to restore
    server_settings: bool = True  # name, description, icon, banner, splash, verification, etc.
    roles: bool = True
    emojis: bool = True
    stickers: bool = True
    categories: bool = True
    text_channels: bool = True
    voice_channels: bool = True
    forums: bool = True
    bans: bool = True

    # Behavior options
    restore_member_roles: bool = True  # Whether to restore role assignments to members
    delete_unmatched: bool = False  # Whether to delete items not in backup (destructive)

    def summary(self) -> str:
        """Return a summary of what will be restored."""
        lines = []
        if self.server_settings:
            lines.append(_("✅ Server Settings"))
        if self.roles:
            lines.append(_("✅ Roles"))
        if self.emojis:
            lines.append(_("✅ Emojis"))
        if self.stickers:
            lines.append(_("✅ Stickers"))
        if self.categories:
            lines.append(_("✅ Categories"))
        if self.text_channels:
            lines.append(_("✅ Text Channels"))
        if self.voice_channels:
            lines.append(_("✅ Voice Channels"))
        if self.forums:
            lines.append(_("✅ Forum Channels"))
        if self.bans:
            lines.append(_("✅ Bans"))

        if self.restore_member_roles:
            lines.append(_("✅ Member Role Assignments"))
        else:
            lines.append(_("❌ Member Role Assignments"))

        if self.delete_unmatched:
            lines.append(_("⚠️ Delete items not in backup"))
        else:
            lines.append(_("➕ Additive restore (keep existing items)"))

        return "\n".join(lines)


class GuildSettings(Base):
    auto_backup_interval_hours: int = 0
    last_backup: datetime = Field(default_factory=lambda: datetime.now().astimezone() - timedelta(days=999))

    @property
    def last_backup_f(self) -> str:
        return f"<t:{int(self.last_backup.timestamp())}:F>"

    @property
    def last_backup_r(self) -> str:
        return f"<t:{int(self.last_backup.timestamp())}:R>"

    async def backup(
        self,
        guild: discord.Guild,
        backups_dir: Path,
        limit: int = 0,
        backup_members: bool = True,
        backup_roles: bool = True,
        backup_emojis: bool = True,
        backup_stickers: bool = True,
    ) -> None:
        backup_obj = await GuildBackup.serialize(
            guild=guild,
            limit=limit,
            backup_members=backup_members,
            backup_roles=backup_roles,
            backup_emojis=backup_emojis,
            backup_stickers=backup_stickers,
        )
        dump = await asyncio.to_thread(backup_obj.model_dump_json)
        backup_dir = backups_dir / str(guild.id)
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Clean the guild name to make it filename safe
        guild_name = "".join(c for c in guild.name if c.isalnum())
        backup_file = backup_dir / f"{guild_name}_{int(datetime.now().timestamp())}.json"
        with open(backup_file, "w", encoding="utf-8") as f:
            f.write(dump)
            f.flush()
            os.fsync(f.fileno())

        if hasattr(os, "O_DIRECTORY"):
            fd = os.open(backup_file.parent, os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

        self.last_backup = datetime.now().astimezone()


class DB(Base):
    configs: dict[int, GuildSettings] = {}
    max_backups_per_guild: int = 5
    allow_auto_backups: bool = False

    message_backup_limit: int = 0  # How many messages to backup per channel
    backup_members: bool = True
    backup_roles: bool = True
    backup_emojis: bool = False
    backup_stickers: bool = False

    ignored_guilds: list[int] = []
    allowed_guilds: list[int] = []

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())

    def cleanup(self, guild: discord.Guild | int, backup_dir: Path):
        guild_id = str(guild) if isinstance(guild, int) else str(guild.id)
        path = backup_dir / guild_id
        if not path.exists():
            return
        # Ensure there are no more than `max_backups_per_guild` backups
        # Delete oldest backups if there are more than `max_backups_per_guild`
        backups = sorted(path.iterdir(), key=lambda x: x.stat().st_mtime)
        if len(backups) <= self.max_backups_per_guild:
            return
        for backup in backups[: -self.max_backups_per_guild]:
            log.debug("Cleaning up old backup: %s", backup)
            backup.unlink()
