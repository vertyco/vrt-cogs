from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta
from redbot.core.commands import parse_relativedelta


def parse_deny_duration(text: str | None) -> tuple[relativedelta | None, str | None]:
    """Split an optional leading re-appeal wait off a deny reason.

    Only the first word is checked, and only compact durations count (`6mo`, `2y`, `30d`), so `30 days` stays reason.
    `0` returns an empty relativedelta, which is falsy: compare the result against None, not truthiness.
    """
    parts = text.split(maxsplit=1) if text else []
    if not parts:
        return None, None
    first = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else None
    if first == "0":
        return relativedelta(), rest or None
    delta = parse_relativedelta(first)
    if delta is None:
        return None, text.strip()
    return delta, rest or None


def add_duration(start: datetime, delta: relativedelta) -> datetime | None:
    """Return start + delta, or None when the result is past what datetime can hold (year 9999)."""
    try:
        return start + delta
    except (ValueError, OverflowError):
        return None


def next_appeal_at(decided_at: datetime | None, reappeal_at: datetime | None, guild_cooldown: int) -> datetime | None:
    """When a denied user may appeal again: the per-denial override if set, else the server default. None = no wait."""
    if reappeal_at is not None:
        return reappeal_at
    if decided_at is None or guild_cooldown <= 0:
        return None
    return decided_at + timedelta(seconds=guild_cooldown)


def denial_message(
    guild_name: str,
    targetname: str,
    reason: str | None,
    eligible_at: datetime | None,
    now: datetime,
    can_reappeal: bool,
) -> str:
    """DM text for a denied user. Only says when they can appeal again if they really can, and must still wait."""
    txt = f"Your appeal has been denied in **{guild_name}**. You are still banned from {targetname}"
    if can_reappeal and eligible_at is not None and eligible_at > now:
        ts = int(eligible_at.timestamp())
        txt += f"\nYou can submit another appeal on <t:{ts}:F> (<t:{ts}:R>)."
    if reason:
        txt += f"\n\n**Reason**: {reason}"
    return txt
