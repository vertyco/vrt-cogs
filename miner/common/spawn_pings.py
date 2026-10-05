from ..db.tables import PlayerAchievementStats
from . import constants
from .rock_achievements import VARIETY_COLUMNS


def mined_rock_types(stats: PlayerAchievementStats) -> list[constants.RockTierName]:
    """Rock types this player has been paid from at least once, in ROCK_ORDER."""
    return [key for key in constants.ROCK_ORDER if getattr(stats, VARIETY_COLUMNS[key], False)]


def wants_ping(mined: bool, picks: list[str] | None, rock_type: str) -> bool:
    """Only a mined type can ping; empty picks mean every mined type."""
    return bool(mined) and (not picks or rock_type in picks)


def pinged_types(
    subscribed: bool, picks: list[str] | None, mined: list[constants.RockTierName]
) -> list[constants.RockTierName]:
    """The rock types that would ping this player right now, in ROCK_ORDER."""
    if not subscribed:
        return []
    return [key for key in mined if wants_ping(True, picks, key)]


def ping_summary(subscribed: bool, picks: list[str] | None, mined: list[constants.RockTierName]) -> str | None:
    """Plain words for which rock types ping this player, or None when none can."""
    types = pinged_types(subscribed, picks, mined)
    if not types:
        return None
    if not picks:
        return "every rock type you've mined"
    return ", ".join(constants.ROCK_TYPES[key].display_name for key in types)


def picks_to_save(ticked: list[str], offered: list[constants.RockTierName]) -> list[str]:
    """Ticked keys in ROCK_ORDER. Ticking every offered type saves as empty, so types mined later ping too."""
    if set(ticked) == set(offered):
        return []
    return [key for key in constants.ROCK_ORDER if key in ticked]


def panel_text(subscribed: bool, picks: list[str] | None, mined: list[constants.RockTierName]) -> str:
    """The text above the rock type dropdown in the notify panel."""
    summary = ping_summary(subscribed, picks, mined)
    lines = [f"Rock spawn pings in this server: {f'on for {summary}' if summary else 'off'}"]
    if not mined:
        lines.append("You can turn on pings for a rock type once you've mined one. Join in on the next rock first!")
        return "\n".join(lines)
    lines.append("Pick the rock types you want a ping for. Clear every pick to turn pings off.")
    lines.append("-# You can only enable notifications for the rock types you have discovered.")
    lines.append("-# Your rock type picks apply in every server where your pings are on.")
    return "\n".join(lines)
