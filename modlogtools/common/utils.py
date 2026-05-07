from __future__ import annotations

import re
from datetime import datetime, timezone

import discord

DELETED_USER_SENTINEL = 0xDE1
WARN_ID_RE = re.compile(r"unwarn\s+\d+\s+(\d+)`")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def from_unix(timestamp: int | float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def extract_warn_id(reason: str | None) -> str | None:
    if not reason:
        return None
    match = WARN_ID_RE.search(reason)
    if match is None:
        return None
    return match.group(1)


def get_user_id(user: discord.abc.User | discord.Object | int) -> int:
    if isinstance(user, int):
        return user
    return user.id
