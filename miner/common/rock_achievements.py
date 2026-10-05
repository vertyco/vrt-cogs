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
    role_count: int  # Party roles active on the rock
    damage_share: float  # This player's damage / the rock's total damage
    top_damage: bool  # Strictly more damage than every other miner
    tool_key: constants.ToolName | None  # Pickaxe this player last hit with
    weakest_tool_alone: bool  # Lower pickaxe tier than every other miner
    seconds_left: float  # Rock time limit minus duration
    hp_left_ratio: float  # HP left / max HP
    shattered_tool: constants.ToolName | None  # Pickaxe lost to an overswing on this rock
    end_durability_ratio: float | None  # See end_durability_ratio()


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


def end_durability_ratio(
    swung: constants.ToolName | None, tool_after: constants.ToolName, durability: int | None
) -> float | None:
    """Pickaxe condition after this rock's wear. None for wood, or when it is not the pickaxe the miner hit with."""
    max_durability = constants.TOOLS[tool_after].max_durability
    if not max_durability or swung != tool_after:
        return None
    return (durability or 0) / max_durability


def weakest_tool_alone(session: RockSession, user_id: int) -> bool:
    mine = session.tools.get(user_id)
    others = [tool for uid, tool in session.tools.items() if uid != user_id]
    if mine is None or not others:
        return False
    rank = constants.TOOL_ORDER.index
    return all(rank(mine) < rank(tool) for tool in others)


def outcome_for(
    session: RockSession,
    user_id: int,
    score: int,
    role: str | None,
    duration_seconds: float,
    role_count: int,
    end_ratio: float | None = None,
) -> RockOutcome:
    damage = session.participants.get(user_id, 0)
    total = sum(session.participants.values())
    others = [dealt for uid, dealt in session.participants.items() if uid != user_id]
    return RockOutcome(
        rock_key=session.rocktype.key,
        modifier_keys=tuple(mod.key for mod in session.modifiers),
        participant_count=len(session.participants),
        duration_seconds=duration_seconds,
        depleted=session.depleted,
        full_synergy=role_count >= 3,
        overswings=session.overswings.get(user_id, 0),
        score=score,
        crit_hits=session.crit_hits.get(user_id, 0),
        role=role,
        shattered=user_id in session.shattered_users,
        resisted_shatter=user_id in session.shatter_resist_survivors,
        role_count=role_count,
        damage_share=(damage / total) if total else 0.0,
        top_damage=damage > 0 and all(damage > dealt for dealt in others),
        tool_key=session.tools.get(user_id),
        weakest_tool_alone=weakest_tool_alone(session, user_id),
        seconds_left=session.rocktype.ttl_seconds - duration_seconds,
        hp_left_ratio=session.current_hp / session.max_hp,
        shattered_tool=session.shattered_tools.get(user_id),
        end_durability_ratio=end_ratio,
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
    """Achievement keys decided by this one rock. Counter achievements unlock in the retroactive sync instead."""
    return [
        *performance_keys(outcome),
        *modifier_achievement_keys(outcome),
        *party_keys(outcome),
        *shatter_keys(outcome, totals),
        *combo_keys(outcome),
        *clutch_keys(outcome),
        *mishap_keys(outcome),
    ]


def performance_keys(outcome: RockOutcome) -> list[str]:
    keys: list[str] = []
    # A 70-89 score is not saved anywhere, so this first stays a live check
    if outcome.score >= achievements.PERFORMANCE_ANY_THRESHOLD:
        keys.append("perf_any_bonus")
    if outcome.score >= achievements.PERFORMANCE_MAX_THRESHOLD:
        if outcome.rock_key == "meteor":
            keys.append("perf_max_meteor")
        elif outcome.rock_key == "volatile geode":
            keys.append("perf_max_geode")
        if outcome.depleted and outcome.overswings == 0:
            keys.append("clean_and_perf_max")
    if outcome.crit_hits > 0:
        keys.append("crit_first")
    if outcome.crit_hits >= 5:
        keys.append("crit_five_single_rock")
    if outcome.crit_hits >= 10:
        keys.append("crit_ten_single_rock")
    return keys


def modifier_achievement_keys(outcome: RockOutcome) -> list[str]:
    keys = [
        achievements.MODIFIER_ACHIEVEMENT_KEYS[key]
        for key in outcome.modifier_keys
        if key in achievements.MODIFIER_ACHIEVEMENT_KEYS
    ]
    if len(outcome.modifier_keys) >= 2:
        keys.append("modifier_double")
    return keys


def party_keys(outcome: RockOutcome) -> list[str]:
    keys: list[str] = []
    if outcome.participant_count >= 3:
        keys.append("party_three_players")
    if outcome.participant_count >= 6:
        keys.append("party_six_players")
    if outcome.participant_count >= 10:
        keys.append("party_ten_players")
    if outcome.full_synergy:
        keys.append("party_full_synergy")
    if outcome.participant_count == 2 and outcome.role_count == 2:
        keys.append("role_tag_team")
    return keys


def shatter_keys(outcome: RockOutcome, totals: StatTotals) -> list[str]:
    keys: list[str] = []
    if outcome.resisted_shatter:
        keys.append("tool_shatter_survived")
    if totals.shatter_stage and not outcome.shattered:
        keys.append("tool_shatter_comeback")
    return keys


def combo_keys(outcome: RockOutcome) -> list[str]:
    mods = set(outcome.modifier_keys)
    keys: list[str] = []
    if {"blessed", "enchanted"} <= mods:
        keys.append("combo_divine")
    if {"electrified", "volatile"} <= mods and outcome.depleted and outcome.overswings == 0:
        keys.append("combo_perfect_storm")
    if "fortified" in mods and outcome.depleted and outcome.participant_count == 1:
        keys.append("combo_siege_breaker")
    return keys


def clutch_keys(outcome: RockOutcome) -> list[str]:
    keys: list[str] = []
    crowd = outcome.participant_count >= 3
    # A shatter's tool downgrade can land after pay_out read the row, so the ratio may describe the lost pickaxe
    ratio = None if outcome.shattered else outcome.end_durability_ratio
    if crowd and outcome.damage_share >= 0.70:
        keys.append("clutch_carry")
    if outcome.depleted and outcome.seconds_left <= 5:
        keys.append("clutch_photo_finish")
    if crowd and outcome.top_damage and outcome.weakest_tool_alone:
        keys.append("clutch_underdog")
    if outcome.depleted and ratio is not None and ratio <= 0.05:
        keys.append("clutch_fumes")
    geode_ace = outcome.rock_key == "volatile geode" and outcome.score >= achievements.PERFORMANCE_MAX_THRESHOLD
    if geode_ace and ratio is not None and ratio <= 0.30:
        keys.append("clutch_glass_cannon")
    if outcome.depleted and outcome.rock_key in ("meteor", "volatile geode") and outcome.tool_key == "wood":
        keys.append("clutch_splinters")
    return keys


def mishap_keys(outcome: RockOutcome) -> list[str]:
    keys: list[str] = []
    if outcome.shattered_tool == "diamond":
        keys.append("mishap_butterfingers")
    if outcome.shattered_tool and outcome.rock_key == "volatile geode":
        keys.append("mishap_wrong_rock")
    if not outcome.depleted and outcome.hp_left_ratio <= 0.05:
        keys.append("mishap_so_close")
    return keys
