import logging
from datetime import datetime, timezone

import discord

from . import Base

log = logging.getLogger("red.vrt.imgen.models")


class RoleCooldown(Base):
    """Role-based cooldown configuration that also acts as an allow list."""

    role_id: int
    cooldown_seconds: int = 60  # Seconds between generations


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
    default_model: str = "gpt-image-1"
    default_size: str = "auto"
    default_quality: str = "auto"

    def get_user_cooldown(self, member: discord.Member) -> int:
        """
        Get the cooldown for a member based on their roles.
        Returns cooldown_seconds - uses the most permissive (lowest) value.
        Returns -1 if user has no allowed roles (when roles are configured).
        Returns 0 if no roles are configured (open access).
        """
        if not self.role_cooldowns:
            # No roles configured = open access with no cooldown
            return 0

        member_role_ids = {r.id for r in member.roles}
        applicable = [rc for rid, rc in self.role_cooldowns.items() if rid in member_role_ids]

        if not applicable:
            return -1  # No access - user doesn't have any allowed roles

        # Use the most permissive (lowest cooldown)
        return min(rc.cooldown_seconds for rc in applicable)

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
