from __future__ import annotations

import logging
from datetime import datetime, timedelta

import discord
from pydantic import Field
from redbot.core.i18n import Translator

from . import Base
from .serializers import GuildBackup

log = logging.getLogger("red.vrt.cartographer.models")
_ = Translator("Cartographer", __file__)


class GuildSettings(Base):
    backups: list[GuildBackup] = []
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
        limit: int = 0,
        backup_members: bool = True,
        backup_roles: bool = True,
        backup_emojis: bool = True,
        backup_stickers: bool = True,
    ) -> None:
        serialized = await GuildBackup.serialize(
            guild,
            limit=limit,
            backup_members=backup_members,
            backup_roles=backup_roles,
            backup_emojis=backup_emojis,
            backup_stickers=backup_stickers,
        )
        self.backups.append(serialized)
        self.last_backup = datetime.now().astimezone()


class DB(Base):
    configs: dict[int, GuildSettings] = {}
    max_backups_per_guild: int = 5
    allow_auto_backups: bool = False

    message_backup_limit: int = 0  # How many messages to backup per channel
    backup_members: bool = True
    backup_roles: bool = True
    backup_emojis: bool = True
    backup_stickers: bool = True

    ignored_guilds: list[int] = []
    allowed_guilds: list[int] = []

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())

    def cleanup(self, guild: discord.Guild | int):
        conf = self.get_conf(guild)
        conf.backups = conf.backups[-self.max_backups_per_guild :]
