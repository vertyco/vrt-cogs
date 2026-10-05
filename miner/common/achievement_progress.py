from __future__ import annotations

import typing as t

import discord
from redbot.core.utils.chat_formatting import humanize_number

from . import achievements, constants

HIDDEN_LINE = "🔒 **???**\n-# Hidden. Keep mining to find it."

COUNTER_LABELS: dict[str, str] = {
    "rocks_mined_total": "Rocks mined",
    "modifier_rocks_mined_total": "Modifier rocks mined",
    "group_sessions_total": "Group mining sessions",
    "role_breaker_total": "Breaker roles earned",
    "role_stabilizer_total": "Stabilizer roles earned",
    "role_finisher_total": "Finisher roles earned",
}
COLUMN_NAMES: dict[str, str] = {
    "role_breaker_total": "Breaker",
    "role_stabilizer_total": "Stabilizer",
    "role_finisher_total": "Finisher",
    "mined_small": "Small",
    "mined_medium": "Medium",
    "mined_large": "Large",
    "mined_meteor": "Meteor",
    "mined_geode": "Geode",
}


def achievement_line(item: achievements.AchievementDef, unlocked_row: t.Any | None, progress: str | None) -> str:
    """One achievement's entry on its category page."""
    if unlocked_row is not None:
        unlocked_at = discord.utils.format_dt(unlocked_row.created_on, style="R")
        return f"✅ **{item.name}**\n-# {item.condition}\n-# Unlocked {unlocked_at}"
    if item.hidden:
        return HIDDEN_LINE
    if progress:
        return f"🔒 **{item.name}**\n-# {item.condition}\n-# {progress}"
    return f"🔒 **{item.name}**\n-# {item.condition}"


def progress_line(
    item: achievements.AchievementDef,
    stats: t.Any,
    resource_lower_bounds: dict[constants.Resource, int],
    unlocked_keys: set[str],
) -> str | None:
    """Progress text under a locked achievement, or None when there is nothing to count."""
    rule = item.retroactive_rule
    if item.hidden:
        return None
    if rule == "stat_at_least":
        return counter_progress(item, stats)
    if rule == "all_stats_positive":
        return all_stats_progress(item, stats)
    if rule == "solo_time_within":
        return solo_progress(getattr(stats, item.stat) or 0.0, item.seconds or 0.0)
    if rule == "collection":
        required = achievements.required_keys(item)
        done = sum(1 for key in required if key in unlocked_keys)
        return f"Achievements unlocked: `{done}` / `{len(required)}`"
    if rule in ("tool_at_least_tier", "resource_any_positive", "resource_lower_bound"):
        return holdings_progress(item, resource_lower_bounds)
    if item.key == "tool_shatter_comeback":
        if int(stats.shatter_recovery_stage or 0) > 0:
            return "Comeback is primed: successfully mine any later rock encounter."
        return "Shatter a tool first, then finish a later rock encounter."
    return None


def holdings_progress(
    item: achievements.AchievementDef, resource_lower_bounds: dict[constants.Resource, int]
) -> str | None:
    """Progress for the pickaxe tier and lifetime resource achievements."""
    if item.retroactive_rule == "tool_at_least_tier" and item.tool is not None:
        return f"Current tool milestone target: `{constants.TOOLS[item.tool].display_name}`"
    if item.retroactive_rule == "resource_any_positive":
        return f"Tracked mined resources total: `{humanize_number(sum(resource_lower_bounds.values()))}`"
    if item.resource and item.threshold is not None:
        current = int(resource_lower_bounds.get(item.resource, 0))
        return (
            f"Mined {item.resource}: `{humanize_number(min(current, item.threshold))}` / "
            f"`{humanize_number(item.threshold)}`"
        )
    return None


def counter_progress(item: achievements.AchievementDef, stats: t.Any) -> str | None:
    threshold = item.threshold or 0
    if item.stat == "clean_streak_best":
        current = int(stats.clean_streak_current or 0)
        return f"Current clean streak: `{min(current, threshold)}` / `{threshold}`"
    if item.stat == "perf_max_streak_best":
        if threshold <= 1:
            return None
        current = int(stats.perf_max_streak_current or 0)
        return f"Current 90+ streak: `{min(current, threshold)}` / `{threshold}`"
    label = COUNTER_LABELS.get(item.stat or "")
    if label is None:
        return None
    current = int(getattr(stats, item.stat) or 0)
    return f"{label}: `{humanize_number(min(current, threshold))}` / `{humanize_number(threshold)}`"


def all_stats_progress(item: achievements.AchievementDef, stats: t.Any) -> str:
    columns = item.stats or ()
    label = "Roles earned" if columns and columns[0].startswith("role_") else "Rock types mined"
    missing = [COLUMN_NAMES[column] for column in columns if not getattr(stats, column)]
    text = f"{label}: `{len(columns) - len(missing)}` / `{len(columns)}`"
    return f"{text} | missing {', '.join(missing)}" if missing else text


def solo_progress(best_time: float, target_time: float) -> str:
    if best_time <= 0:
        return f"Best solo clear: `none yet` | target `<= {target_time:.0f}s`"
    return f"Best solo clear: `{best_time:.1f}s` | target `<= {target_time:.0f}s`"
