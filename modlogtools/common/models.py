from __future__ import annotations

from datetime import datetime, timedelta

import discord

from . import Base


class WarningRecord(Base):
    user_id: int
    warn_id: str
    points: int = 0
    description: str = ""
    moderator_id: int = 0
    created_at: datetime
    modlog_case_number: int | None = None
    expires_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution: str | None = None
    resolution_case_number: int | None = None
    expiry_override: bool = False
    decayed_points: int = 0

    @property
    def is_active(self) -> bool:
        return self.resolution is None

    @property
    def created_ts(self) -> int:
        return int(self.created_at.timestamp())

    @property
    def expires_ts(self) -> int | None:
        if self.expires_at is None:
            return None
        return int(self.expires_at.timestamp())


class GuildSettings(Base):
    warning_expiry_seconds: int | None = None
    delete_expired_modlog_messages: bool = False
    dm_on_expiry: bool = False
    point_decay_per_day: int = 0
    records: dict[str, WarningRecord] = {}
    last_full_sync: datetime | None = None

    @staticmethod
    def make_key(user_id: int, warn_id: str) -> str:
        return f"{user_id}:{warn_id}"

    def get_record(self, user_id: int, warn_id: str) -> WarningRecord | None:
        return self.records.get(self.make_key(user_id, warn_id))

    def set_record(self, record: WarningRecord) -> None:
        self.records[self.make_key(record.user_id, record.warn_id)] = record

    def get_warning_expiry(self) -> timedelta | None:
        # Treat 0 the same as unset so a zero value (only reachable via imported payloads)
        # cannot pass `is None` gates while every expiry computation treats it as disabled.
        if not self.warning_expiry_seconds:
            return None
        return timedelta(seconds=self.warning_expiry_seconds)

    def update_expiry(self, duration: timedelta | None) -> None:
        self.warning_expiry_seconds = None if duration is None else int(duration.total_seconds())


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        guild_id = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(guild_id, GuildSettings())
