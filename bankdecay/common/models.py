from datetime import datetime

import discord
from pydantic import Field

from . import Base


class User(Base):
    last_active: datetime = Field(default_factory=lambda: datetime.now())

    @property
    def seen_r(self) -> str:
        return f"<t:{int(self.last_active.timestamp())}:R>"

    @property
    def seen_f(self) -> str:
        return f"<t:{int(self.last_active.timestamp())}:F>"


class GuildSettings(Base):
    enabled: bool = False
    inactive_days: int = 30
    percent_decay: float = 0.05  # 5%
    users: dict[int, User] = {}
    total_decayed: int = 0
    ignored_roles: list[int] = []
    log_channel: int = 0

    def get_user(self, user: discord.Member | discord.User | int) -> User:
        uid = user if isinstance(user, int) else user.id
        return self.users.setdefault(uid, User())


class DB(Base):
    configs: dict[int, GuildSettings] = {}
    last_run: datetime = None

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())

    def refresh_user(self, user: discord.Member | discord.User) -> None:
        if isinstance(user, discord.User):
            return
        conf = self.get_conf(user.guild)
        conf.get_user(user).last_active = datetime.now()
