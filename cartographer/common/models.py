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
    message_backup_limit: int = 0  # How many messages to store per channel (0 == disabled)
    auto_backup_interval_hours: int = 0
    last_backup: datetime = Field(default_factory=lambda: datetime.now().astimezone() - timedelta(days=999))

    @property
    def last_backup_f(self) -> str:
        return f"<t:{int(self.last_backup.timestamp())}:F>"

    @property
    def last_backup_r(self) -> str:
        return f"<t:{int(self.last_backup.timestamp())}:R>"

    async def backup(self, guild: discord.Guild) -> None:
        serialized = await GuildBackup.serialize(guild, limit=self.message_backup_limit)
        self.backups.append(serialized)
        self.last_backup = datetime.now().astimezone()


class DB(Base):
    configs: dict[int, GuildSettings] = {}
    max_backups_per_guild: int = 5
    allow_auto_backups: bool = False
    ignored_guilds: list[int] = []
    allowed_guilds: list[int] = []

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())

    def cleanup(self, guild: discord.Guild | int):
        conf = self.get_conf(guild)
        conf.backups = conf.backups[-self.max_backups_per_guild :]
