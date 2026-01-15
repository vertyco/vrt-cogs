import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import discord

from . import Base

log = logging.getLogger("red.vrt.imgen.models")


class RoleCooldown(Base):
    """Role-based cooldown configuration that also acts as an allow list."""

    role_id: int
    cooldown_seconds: int = 60  # Seconds between generations
    allowed_models: list[str] = []
    allowed_sizes: list[str] = []
    allowed_qualities: list[str] = []


@dataclass
class AccessLimits:
    has_access: bool
    cooldown_seconds: int
    allowed_models: set[str] | None
    allowed_sizes: set[str] | None
    allowed_qualities: set[str] | None


class GuildSettings(Base):
    """Per-guild configuration."""

    # OpenAI API key for this guild
    api_key: str | None = None

    # Logging channel for all generations
    log_channel: int = 0

    # Role-based access and cooldowns (role_id -> RoleCooldown)
    # If empty, everyone can use (no restrictions)
    # If populated, acts as an allow list with per-role cooldowns
    role_cooldowns: dict[int, RoleCooldown] = {}

    # User cooldown tracking: user_id -> last generation timestamp
    user_cooldowns: dict[int, float] = {}

    # Default generation settings
    default_model: str = "gpt-image-1.5"
    default_size: str = "auto"
    default_quality: str = "auto"

    def get_access_limits(self, member: discord.Member) -> AccessLimits:
        """Resolve access limits for a member based on their roles."""
        if not self.role_cooldowns:
            return AccessLimits(
                has_access=True,
                cooldown_seconds=0,
                allowed_models=None,
                allowed_sizes=None,
                allowed_qualities=None,
            )

        member_role_ids = {r.id for r in member.roles}
        applicable = [rc for rid, rc in self.role_cooldowns.items() if rid in member_role_ids]

        if not applicable:
            return AccessLimits(
                has_access=False,
                cooldown_seconds=-1,
                allowed_models=None,
                allowed_sizes=None,
                allowed_qualities=None,
            )

        cooldown_seconds = min(rc.cooldown_seconds for rc in applicable)

        def resolve_allowed(values: list[list[str]]) -> set[str] | None:
            if any(not v for v in values):
                return None
            merged: set[str] = set()
            for value_list in values:
                merged.update(value_list)
            return merged

        allowed_models = resolve_allowed([rc.allowed_models for rc in applicable])
        allowed_sizes = resolve_allowed([rc.allowed_sizes for rc in applicable])
        allowed_qualities = resolve_allowed([rc.allowed_qualities for rc in applicable])

        return AccessLimits(
            has_access=True,
            cooldown_seconds=cooldown_seconds,
            allowed_models=allowed_models,
            allowed_sizes=allowed_sizes,
            allowed_qualities=allowed_qualities,
        )

    def get_user_cooldown(self, member: discord.Member) -> int:
        """
        Get the cooldown for a member based on their roles.
        Returns cooldown_seconds - uses the most permissive (lowest) value.
        Returns -1 if user has no allowed roles (when roles are configured).
        Returns 0 if no roles are configured (open access).
        """
        access = self.get_access_limits(member)
        if not access.has_access:
            return -1
        return access.cooldown_seconds

    def can_generate(self, member: discord.Member) -> tuple[bool, str]:
        """
        Check if a member can generate an image.
        Returns (can_generate, reason).
        """
        cooldown_seconds = self.get_user_cooldown(member)

        if cooldown_seconds == -1:
            return (False, "You don't have a role that allows image generation.")

        # Check if user is on cooldown
        if cooldown_seconds > 0:
            last_gen = self.user_cooldowns.get(member.id, 0)
            now = datetime.now(tz=timezone.utc).timestamp()
            elapsed = now - last_gen
            remaining = cooldown_seconds - elapsed

            if remaining > 0:
                return (False, f"You're on cooldown. Try again <t:{int(last_gen + cooldown_seconds)}:R>.")

        return (True, "")

    def record_generation(self, member: discord.Member) -> None:
        """Record a generation for cooldown tracking."""
        self.user_cooldowns[member.id] = datetime.now(tz=timezone.utc).timestamp()


class DB(Base):
    """Root database model."""

    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
