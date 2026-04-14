import typing as t
from enum import IntEnum

import discord

from . import Base

RULE_NAME_PREFIX = "NoPing"
MAX_KEYWORDS_PER_RULE = 1000


class Weekday(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

    @property
    def short(self) -> str:
        return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][self.value]

    @property
    def label(self) -> str:
        return self.name.capitalize()


class TimeWindow(Base):
    """A single availability window within a day (e.g., 9:00 - 17:00)."""

    start_hour: int = 9
    start_minute: int = 0
    end_hour: int = 17
    end_minute: int = 0

    def format(self) -> str:
        start = f"{self.start_hour:02d}:{self.start_minute:02d}"
        end = f"{self.end_hour:02d}:{self.end_minute:02d}"
        return f"{start} - {end}"

    def total_minutes(self) -> int:
        return (self.end_hour * 60 + self.end_minute) - (self.start_hour * 60 + self.start_minute)


class DaySchedule(Base):
    """Schedule windows for a specific day of the week."""

    enabled: bool = False
    windows: list[TimeWindow] = []


class UserSchedule(Base):
    """A user's noping schedule. If no days have windows, noping is permanent when enabled."""

    enabled: bool = False
    timezone: t.Optional[str] = None
    days: dict[int, DaySchedule] = {}

    def get_day(self, day: int) -> DaySchedule:
        return self.days.setdefault(day, DaySchedule())

    def has_schedule(self) -> bool:
        """Return True if any day has enabled windows."""
        return any(d.enabled and d.windows for d in self.days.values())

    def is_noping_active_at(self, weekday: int, hour: int, minute: int) -> bool:
        """Check if noping should be active at the given time.

        If no schedule is configured, noping is permanent (always active when enabled).
        If a schedule IS configured, noping is active when the user is NOT in an availability window.
        """
        if not self.enabled:
            return False
        if not self.has_schedule():
            return True
        day = self.days.get(weekday)
        if not day or not day.enabled or not day.windows:
            return True
        current = hour * 60 + minute
        for window in day.windows:
            start = window.start_hour * 60 + window.start_minute
            end = window.end_hour * 60 + window.end_minute
            if start <= current < end:
                return False
        return True

    def format_schedule(self) -> str:
        """Return a human-readable summary of the schedule."""
        if not self.has_schedule():
            return "Always active (no schedule set)"
        lines = []
        for day_val in range(7):
            day_name = Weekday(day_val).label
            day_sched = self.days.get(day_val)
            if not day_sched or not day_sched.enabled or not day_sched.windows:
                lines.append(f"**{day_name}**: No pings allowed all day")
            else:
                windows_str = ", ".join(w.format() for w in day_sched.windows)
                lines.append(f"**{day_name}**: Available {windows_str}")
        return "\n".join(lines)


class GuildSettings(Base):
    timezone: str = "UTC"
    allow_user_noping: bool = True
    users: dict[int, UserSchedule] = {}
    rule_ids: list[int] = []

    def get_user(self, user_id: int) -> UserSchedule:
        return self.users.setdefault(user_id, UserSchedule())

    def get_active_user_ids(self) -> list[int]:
        """Get user IDs that currently have noping enabled (regardless of schedule)."""
        return [uid for uid, sched in self.users.items() if sched.enabled]

    def remove_user(self, user_id: int) -> bool:
        """Remove a user's schedule. Returns True if the user was found."""
        return self.users.pop(user_id, None) is not None


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
