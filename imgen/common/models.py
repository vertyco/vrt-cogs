import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import discord

from . import Base

log = logging.getLogger("red.vrt.imgen.models")

QuotaInterval = Literal["daily", "monthly"]


class RoleAccess(Base):
    """Role-based access configuration that also acts as an allow list."""

    role_id: int
    quota: int = 10  # Generations per interval, 0 = unlimited
    quota_interval: QuotaInterval = "daily"
    allowed_models: list[str] = []
    allowed_sizes: list[str] = []
    allowed_qualities: list[str] = []


class UserUsage(Base):
    """Tracks a user's generation counts for daily and monthly periods."""

    daily_count: int = 0
    daily_date: str = ""  # YYYY-MM-DD in UTC
    monthly_count: int = 0
    monthly_date: str = ""  # YYYY-MM in UTC


@dataclass
class AccessLimits:
    has_access: bool
    daily_quota: int  # 0 = unlimited/not applicable
    monthly_quota: int  # 0 = unlimited/not applicable
    allowed_models: set[str] | None
    allowed_sizes: set[str] | None
    allowed_qualities: set[str] | None


class GuildSettings(Base):
    """Per-guild configuration."""

    # OpenAI API key for this guild
    api_key: str | None = None

    # Logging channel for all generations
    log_channel: int = 0

    # Role-based access and quotas (role_id -> RoleAccess)
    # If empty, everyone can use (no restrictions)
    # If populated, acts as an allow list with per-role quotas
    role_access: dict[int, RoleAccess] = {}

    # User usage tracking: user_id -> UserUsage
    user_usage: dict[int, UserUsage] = {}

    # Default generation settings
    default_model: str = "gpt-image-1.5"
    default_size: str = "auto"
    default_quality: str = "auto"

    def get_access_limits(self, member: discord.Member) -> AccessLimits:
        """Resolve access limits for a member based on their roles."""
        if not self.role_access:
            return AccessLimits(
                has_access=True,
                daily_quota=0,
                monthly_quota=0,
                allowed_models=None,
                allowed_sizes=None,
                allowed_qualities=None,
            )

        member_role_ids = {r.id for r in member.roles}
        applicable = [ra for rid, ra in self.role_access.items() if rid in member_role_ids]

        if not applicable:
            return AccessLimits(
                has_access=False,
                daily_quota=-1,
                monthly_quota=-1,
                allowed_models=None,
                allowed_sizes=None,
                allowed_qualities=None,
            )

        # Resolve quotas per interval type, taking the most permissive (highest) for each
        daily_roles = [ra for ra in applicable if ra.quota_interval == "daily"]
        monthly_roles = [ra for ra in applicable if ra.quota_interval == "monthly"]

        daily_quota = 0  # 0 = not applicable (no daily roles)
        if daily_roles:
            if any(ra.quota == 0 for ra in daily_roles):
                daily_quota = 0  # Unlimited
            else:
                daily_quota = max(ra.quota for ra in daily_roles)

        monthly_quota = 0  # 0 = not applicable (no monthly roles)
        if monthly_roles:
            if any(ra.quota == 0 for ra in monthly_roles):
                monthly_quota = 0  # Unlimited
            else:
                monthly_quota = max(ra.quota for ra in monthly_roles)

        def resolve_allowed(values: list[list[str]]) -> set[str] | None:
            if any(not v for v in values):
                return None
            merged: set[str] = set()
            for value_list in values:
                merged.update(value_list)
            return merged

        allowed_models = resolve_allowed([ra.allowed_models for ra in applicable])
        allowed_sizes = resolve_allowed([ra.allowed_sizes for ra in applicable])
        allowed_qualities = resolve_allowed([ra.allowed_qualities for ra in applicable])

        return AccessLimits(
            has_access=True,
            daily_quota=daily_quota,
            monthly_quota=monthly_quota,
            allowed_models=allowed_models,
            allowed_sizes=allowed_sizes,
            allowed_qualities=allowed_qualities,
        )

    def get_today_utc(self) -> str:
        """Get today's date string in UTC."""
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    def get_current_month_utc(self) -> str:
        """Get current month string in UTC."""
        return datetime.now(tz=timezone.utc).strftime("%Y-%m")

    def get_user_daily_usage(self, member: discord.Member) -> int:
        """Get the number of generations a user has made today (UTC)."""
        usage = self.user_usage.get(member.id)
        if not usage or usage.daily_date != self.get_today_utc():
            return 0
        return usage.daily_count

    def get_user_monthly_usage(self, member: discord.Member) -> int:
        """Get the number of generations a user has made this month (UTC)."""
        usage = self.user_usage.get(member.id)
        if not usage or usage.monthly_date != self.get_current_month_utc():
            return 0
        return usage.monthly_count

    def can_generate(self, member: discord.Member) -> tuple[bool, str]:
        """
        Check if a member can generate an image.
        Returns (can_generate, reason).
        """
        if member.id == member.guild.owner_id:
            return (True, "")

        access = self.get_access_limits(member)

        if not access.has_access:
            return (False, "You don't have a role that allows image generation.")

        # Check daily quota (0 = unlimited/not applicable)
        if access.daily_quota > 0:
            used_today = self.get_user_daily_usage(member)
            if used_today >= access.daily_quota:
                now = datetime.now(tz=timezone.utc)
                tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                reset_ts = int(tomorrow.timestamp())
                return (False, f"You've used all {access.daily_quota} of your daily generations. Resets <t:{reset_ts}:R>.")

        # Check monthly quota (0 = unlimited/not applicable)
        if access.monthly_quota > 0:
            used_this_month = self.get_user_monthly_usage(member)
            if used_this_month >= access.monthly_quota:
                now = datetime.now(tz=timezone.utc)
                if now.month == 12:
                    first_of_next = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                else:
                    first_of_next = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
                reset_ts = int(first_of_next.timestamp())
                return (False, f"You've used all {access.monthly_quota} of your monthly generations. Resets <t:{reset_ts}:R>.")

        return (True, "")

    def record_generation(self, member: discord.Member) -> None:
        """Record a generation for quota tracking."""
        today = self.get_today_utc()
        month = self.get_current_month_utc()
        usage = self.user_usage.get(member.id)

        if not usage:
            self.user_usage[member.id] = UserUsage(daily_count=1, daily_date=today, monthly_count=1, monthly_date=month)
            return

        if usage.daily_date != today:
            usage.daily_count = 1
            usage.daily_date = today
        else:
            usage.daily_count += 1

        if usage.monthly_date != month:
            usage.monthly_count = 1
            usage.monthly_date = month
        else:
            usage.monthly_count += 1


class DB(Base):
    """Root database model."""

    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
