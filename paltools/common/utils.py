from redbot.core.i18n import Translator

from .models import PalPlayer

_ = Translator("PalTools", __file__)


def snapshot_from_players(players: list[PalPlayer]) -> dict[str, PalPlayer]:
    return {p.player_id: p for p in players if not p.is_placeholder}


def diff_snapshots(
    prev: dict[str, PalPlayer], current: dict[str, PalPlayer]
) -> tuple[list[PalPlayer], list[PalPlayer]]:
    joined = [p for pid, p in current.items() if pid not in prev]
    left = [p for pid, p in prev.items() if pid not in current]
    return joined, left


def format_player_lines(players: list[PalPlayer], budget: int = 950) -> str:
    """Roster trimmed to stay under Discord's 1024 char embed field limit"""
    lines = []
    for player in players:
        line = f"{player.name} (lvl {player.level}, {player.ping:.0f}ms)"
        if budget - len(line) - 1 < 0:
            break
        lines.append(line)
        budget -= len(line) + 1
    value = "\n".join(lines)
    if len(lines) < len(players):
        value += _("\n...and {} more").format(len(players) - len(lines))
    return value


def chunk_lines(lines: list[str], budget: int) -> list[str]:
    """Group lines into as few blocks as the budget allows.

    A poll tick can surface a whole server's worth of joins at once (a restart, a wipe night),
    and one message per player would be both slower and unreadable.
    """
    blocks: list[str] = []
    current: list[str] = []
    length = 0
    for line in lines:
        if len(line) > budget:
            # Nothing sane produces this, but a single over-long line would fail the send and
            # take every line batched with it down too
            line = line[: budget - 1] + "…"
        cost = len(line) + (1 if current else 0)
        if current and length + cost > budget:
            blocks.append("\n".join(current))
            current, length = [], 0
            cost = len(line)
        current.append(line)
        length += cost
    if current:
        blocks.append("\n".join(current))
    return blocks


def format_playtime(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return "<1m"
    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins or not parts:
        parts.append(f"{mins}m")
    return " ".join(parts)
