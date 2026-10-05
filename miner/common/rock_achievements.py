from __future__ import annotations

import typing as t
from dataclasses import dataclass

from ..db.tables import PlayerAchievementStats
from . import achievements, constants
from .rock_session import RockSession

# Rock key -> PlayerAchievementStats column, for the "mined one of each" and solo speed stats
VARIETY_COLUMNS: dict[str, str] = {
    "small": "mined_small",
    "medium": "mined_medium",
    "large": "mined_large",
    "meteor": "mined_meteor",
    "volatile geode": "mined_geode",
}
SOLO_COLUMNS: dict[str, str] = {
    "small": "best_solo_small_seconds",
    "medium": "best_solo_medium_seconds",
    "large": "best_solo_large_seconds",
    "meteor": "best_solo_meteor_seconds",
    "volatile geode": "best_solo_geode_seconds",
}
ROLE_COLUMNS: dict[str, str] = {
    "Breaker": "role_breaker_total",
    "Stabilizer": "role_stabilizer_total",
    "Finisher": "role_finisher_total",
}
ROLE_KEYS: dict[str, str] = {
    "Breaker": "party_role_breaker",
    "Stabilizer": "party_role_stabilizer",
    "Finisher": "party_role_finisher",
}


@dataclass(frozen=True, slots=True)
class RockOutcome:
    """What one player did on one finished rock, as achievement bookkeeping needs it."""

    rock_key: constants.RockTierName
    modifier_keys: tuple[str, ...]
    participant_count: int
    duration_seconds: float
    depleted: bool
    full_synergy: bool
    overswings: int
    score: int
    crit_hits: int
    role: str | None
    shattered: bool
    resisted_shatter: bool


@dataclass(frozen=True, slots=True)
class StatTotals:
    """A player's lifetime counters after counting this rock."""

    rocks_mined: int
    group_sessions: int
    modifier_rocks: int
    variety: dict[str, bool]
    clean_streak: int
    clean_streak_best: int
    perf_max_streak: int
    perf_max_streak_best: int
    role_totals: dict[str, int]
    shatter_stage: int


def outcome_for(
    session: RockSession,
    user_id: int,
    score: int,
    role: str | None,
    duration_seconds: float,
    full_synergy: bool,
) -> RockOutcome:
    return RockOutcome(
        rock_key=session.rocktype.key,
        modifier_keys=tuple(mod.key for mod in session.modifiers),
        participant_count=len(session.participants),
        duration_seconds=duration_seconds,
        depleted=session.depleted,
        full_synergy=full_synergy,
        overswings=session.overswings.get(user_id, 0),
        score=score,
        crit_hits=session.crit_hits.get(user_id, 0),
        role=role,
        shattered=user_id in session.shattered_users,
        resisted_shatter=user_id in session.shatter_resist_survivors,
    )


def new_totals(stats: t.Any, outcome: RockOutcome) -> StatTotals:
    """Counters after this rock. `stats` is the player's PlayerAchievementStats row."""
    clean = (stats.clean_streak_current or 0) + 1 if outcome.overswings == 0 else 0
    maxed = outcome.score >= achievements.PERFORMANCE_MAX_THRESHOLD
    perf = (stats.perf_max_streak_current or 0) + 1 if maxed else 0
    return StatTotals(
        rocks_mined=(stats.rocks_mined_total or 0) + 1,
        group_sessions=(stats.group_sessions_total or 0) + (1 if outcome.participant_count >= 2 else 0),
        modifier_rocks=(stats.modifier_rocks_mined_total or 0) + (1 if outcome.modifier_keys else 0),
        variety={key: bool(getattr(stats, col)) or outcome.rock_key == key for key, col in VARIETY_COLUMNS.items()},
        clean_streak=clean,
        clean_streak_best=max(stats.clean_streak_best or 0, clean),
        perf_max_streak=perf,
        perf_max_streak_best=max(stats.perf_max_streak_best or 0, perf),
        role_totals={
            role: (getattr(stats, col) or 0) + (1 if outcome.role == role else 0) for role, col in ROLE_COLUMNS.items()
        },
        shatter_stage=int(stats.shatter_recovery_stage or 0),
    )


def stat_updates(stats: t.Any, outcome: RockOutcome, totals: StatTotals) -> dict[t.Any, t.Any]:
    """Column -> new value for PlayerAchievementStats.update_self."""
    table = PlayerAchievementStats
    updates: dict[t.Any, t.Any] = {
        table.rocks_mined_total: totals.rocks_mined,
        table.group_sessions_total: totals.group_sessions,
        table.modifier_rocks_mined_total: totals.modifier_rocks,
        table.clean_streak_current: totals.clean_streak,
        table.clean_streak_best: totals.clean_streak_best,
        table.perf_max_streak_current: totals.perf_max_streak,
        table.perf_max_streak_best: totals.perf_max_streak_best,
    }
    for key, col in VARIETY_COLUMNS.items():
        updates[getattr(table, col)] = totals.variety[key]
    for role, col in ROLE_COLUMNS.items():
        updates[getattr(table, col)] = totals.role_totals[role]
    if totals.shatter_stage and not outcome.shattered:
        updates[table.shatter_recovery_stage] = 0
    if outcome.depleted and outcome.participant_count == 1:
        col = SOLO_COLUMNS[outcome.rock_key]
        best = getattr(stats, col) or 0.0
        if best <= 0 or outcome.duration_seconds < best:
            updates[getattr(table, col)] = outcome.duration_seconds
    return updates


def achievement_keys(outcome: RockOutcome, totals: StatTotals) -> list[str]:
    """Achievement keys this rock earns, in the same order the old code produced them."""
    return [
        *streak_keys(outcome, totals),
        *performance_keys(outcome, totals),
        *modifier_achievement_keys(outcome, totals),
        *party_keys(outcome, totals),
        *progress_keys(outcome, totals),
    ]


def streak_keys(outcome: RockOutcome, totals: StatTotals) -> list[str]:
    keys = [key for threshold, key in achievements.CLEAN_STREAK_THRESHOLDS if totals.clean_streak >= threshold]
    if outcome.depleted and outcome.participant_count == 1:
        solo_key, limit = achievements.SOLO_SPEED_THRESHOLDS[outcome.rock_key]
        if outcome.duration_seconds <= limit:
            keys.append(solo_key)
    return keys


def performance_keys(outcome: RockOutcome, totals: StatTotals) -> list[str]:
    keys: list[str] = []
    if outcome.score >= achievements.PERFORMANCE_ANY_THRESHOLD:
        keys.append("perf_any_bonus")
    if outcome.score >= achievements.PERFORMANCE_MAX_THRESHOLD:
        keys.append("perf_max_any")
        if outcome.rock_key == "meteor":
            keys.append("perf_max_meteor")
        elif outcome.rock_key == "volatile geode":
            keys.append("perf_max_geode")
        if outcome.depleted and outcome.overswings == 0:
            keys.append("clean_and_perf_max")
    if totals.perf_max_streak >= 3:
        keys.append("perf_max_streak_3")
    if outcome.crit_hits > 0:
        keys.append("crit_first")
    if outcome.crit_hits >= 5:
        keys.append("crit_five_single_rock")
    return keys


def modifier_achievement_keys(outcome: RockOutcome, totals: StatTotals) -> list[str]:
    keys = [
        achievements.MODIFIER_ACHIEVEMENT_KEYS[key]
        for key in outcome.modifier_keys
        if key in achievements.MODIFIER_ACHIEVEMENT_KEYS
    ]
    if len(outcome.modifier_keys) >= 2:
        keys.append("modifier_double")
    if totals.modifier_rocks >= 50:
        keys.append("modifier_total_50")
    return keys


def party_keys(outcome: RockOutcome, totals: StatTotals) -> list[str]:
    keys: list[str] = []
    if outcome.participant_count >= 3:
        keys.append("party_three_players")
    if outcome.role in ROLE_KEYS:
        keys.append(ROLE_KEYS[outcome.role])
    if outcome.full_synergy:
        keys.append("party_full_synergy")
    if totals.group_sessions >= 25:
        keys.append("party_group_sessions_25")
    if all(total > 0 for total in totals.role_totals.values()):
        keys.append("party_all_roles")
    return keys


def progress_keys(outcome: RockOutcome, totals: StatTotals) -> list[str]:
    keys = [key for threshold, key in achievements.ROCK_COUNT_THRESHOLDS if totals.rocks_mined >= threshold]
    if all(totals.variety.values()):
        keys.append("rock_variety_all")
    if outcome.rock_key == "meteor":
        keys.append("rare_first_meteor")
    elif outcome.rock_key == "volatile geode":
        keys.append("rare_first_geode")
    if outcome.resisted_shatter:
        keys.append("tool_shatter_survived")
    if totals.shatter_stage and not outcome.shattered:
        keys.append("tool_shatter_comeback")
    return keys
