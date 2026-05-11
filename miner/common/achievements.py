from __future__ import annotations

import typing as t
from dataclasses import dataclass

from . import constants

AchievementCategory = t.Literal[
    "Clean Mining",
    "Solo Speed Clears",
    "Tool Mastery",
    "Performance Bonuses",
    "Critical Hits",
    "Rock Modifiers",
    "Resource Milestones",
    "Party Play",
    "Rock Count Milestones",
    "Rare Encounters",
]
RetroactiveRule = t.Literal["resource_lower_bound", "resource_any_positive", "tool_at_least_tier"]


@dataclass(frozen=True, slots=True)
class AchievementDef:
    key: str
    name: str
    category: AchievementCategory
    condition: str
    retroactive_rule: RetroactiveRule | None = None
    resource: constants.Resource | None = None
    threshold: int | None = None
    tool: constants.ToolName | None = None


CATEGORY_ORDER: tuple[AchievementCategory, ...] = (
    "Clean Mining",
    "Solo Speed Clears",
    "Tool Mastery",
    "Performance Bonuses",
    "Critical Hits",
    "Rock Modifiers",
    "Resource Milestones",
    "Party Play",
    "Rock Count Milestones",
    "Rare Encounters",
)


ACHIEVEMENTS: tuple[AchievementDef, ...] = (
    AchievementDef(
        "clean_streak_5", "Steady Hands", "Clean Mining", "Mine 5 rocks in a row without a single overswing."
    ),
    AchievementDef(
        "clean_streak_10", "Iron Discipline", "Clean Mining", "Mine 10 rocks in a row without a single overswing."
    ),
    AchievementDef(
        "clean_streak_25", "Patient Miner", "Clean Mining", "Mine 25 rocks in a row without a single overswing."
    ),
    AchievementDef(
        "clean_streak_50", "Unbreakable Focus", "Clean Mining", "Mine 50 rocks in a row without a single overswing."
    ),
    AchievementDef(
        "clean_streak_100", "Perfect Rhythm", "Clean Mining", "Mine 100 rocks in a row without a single overswing."
    ),
    AchievementDef(
        "solo_speed_small", "Lone Chipper", "Solo Speed Clears", "Solo clear a Small Rock within 20 seconds."
    ),
    AchievementDef(
        "solo_speed_medium", "Lone Striker", "Solo Speed Clears", "Solo clear a Medium Rock within 40 seconds."
    ),
    AchievementDef(
        "solo_speed_large", "Lone Crusher", "Solo Speed Clears", "Solo clear a Large Rock within 60 seconds."
    ),
    AchievementDef("solo_speed_meteor", "Meteor Slayer", "Solo Speed Clears", "Solo clear a Meteor within 90 seconds."),
    AchievementDef(
        "solo_speed_geode", "Geode Tamer", "Solo Speed Clears", "Solo clear a Volatile Geode within 130 seconds."
    ),
    AchievementDef(
        "tool_stone",
        "First Upgrade",
        "Tool Mastery",
        "Upgrade to a Stone Pickaxe.",
        retroactive_rule="tool_at_least_tier",
        tool="stone",
    ),
    AchievementDef(
        "tool_iron",
        "Getting Serious",
        "Tool Mastery",
        "Upgrade to an Iron Pickaxe.",
        retroactive_rule="tool_at_least_tier",
        tool="iron",
    ),
    AchievementDef(
        "tool_steel",
        "Forged in Steel",
        "Tool Mastery",
        "Upgrade to a Steel Pickaxe.",
        retroactive_rule="tool_at_least_tier",
        tool="steel",
    ),
    AchievementDef(
        "tool_carbide",
        "Hard Edge",
        "Tool Mastery",
        "Upgrade to a Carbide Pickaxe.",
        retroactive_rule="tool_at_least_tier",
        tool="carbide",
    ),
    AchievementDef(
        "tool_diamond",
        "The Diamond Standard",
        "Tool Mastery",
        "Upgrade to a Diamond Pickaxe.",
        retroactive_rule="tool_at_least_tier",
        tool="diamond",
    ),
    AchievementDef(
        "tool_shatter_survived",
        "Close Shave",
        "Tool Mastery",
        "Survive an overswing that rolled for a shatter and escaped with the tool intact.",
    ),
    AchievementDef(
        "tool_repaired_from_critical",
        "Battle Worn",
        "Tool Mastery",
        "Repair a tool from at or below 10% durability back to full.",
    ),
    AchievementDef(
        "tool_shatter_comeback",
        "Comeback Kid",
        "Tool Mastery",
        "Shatter a tool, then successfully mine a later rock encounter.",
    ),
    AchievementDef(
        "perf_any_bonus",
        "Above Average",
        "Performance Bonuses",
        "Earn any performance bonus tier (70+ score) on a rock.",
    ),
    AchievementDef(
        "perf_max_any",
        "Peak Performance",
        "Performance Bonuses",
        "Earn the maximum performance score (90+) on any rock.",
    ),
    AchievementDef(
        "perf_max_streak_3",
        "Triple Crown",
        "Performance Bonuses",
        "Earn the maximum performance score (90+) on 3 consecutive rocks.",
    ),
    AchievementDef(
        "clean_and_perf_max",
        "Flawless",
        "Performance Bonuses",
        "Clear a rock with no overswings and earn a 90+ performance score on that same rock.",
    ),
    AchievementDef("perf_max_meteor", "Meteor Ace", "Performance Bonuses", "Earn a 90+ performance score on a Meteor."),
    AchievementDef(
        "perf_max_geode", "Geode Ghost", "Performance Bonuses", "Earn a 90+ performance score on a Volatile Geode."
    ),
    AchievementDef("crit_first", "Lucky Hit", "Critical Hits", "Land your first critical hit."),
    AchievementDef(
        "crit_five_single_rock",
        "Critical Mass",
        "Critical Hits",
        "Land 5 critical hits within a single rock encounter.",
    ),
    AchievementDef("modifier_electrified", "Amped Up", "Rock Modifiers", "Mine a rock with the Electrified modifier."),
    AchievementDef(
        "modifier_crystalline", "Crystal Clear", "Rock Modifiers", "Mine a rock with the Crystalline modifier."
    ),
    AchievementDef(
        "modifier_volatile", "Playing with Fire", "Rock Modifiers", "Mine a rock with the Volatile modifier."
    ),
    AchievementDef(
        "modifier_enchanted", "Enchanted Strike", "Rock Modifiers", "Mine a rock with the Enchanted modifier."
    ),
    AchievementDef(
        "modifier_fortified", "Cracked the Shell", "Rock Modifiers", "Mine a rock with the Fortified modifier."
    ),
    AchievementDef("modifier_blessed", "Blessed Haul", "Rock Modifiers", "Mine a rock with the Blessed modifier."),
    AchievementDef(
        "modifier_double",
        "Double Trouble",
        "Rock Modifiers",
        "Mine a rock that spawned with 2 modifiers active at the same time.",
    ),
    AchievementDef(
        "modifier_total_50", "Modifier Magnet", "Rock Modifiers", "Mine 50 rocks that had at least one modifier active."
    ),
    AchievementDef(
        "resource_first_loot",
        "First Haul",
        "Resource Milestones",
        "Collect loot from a rock for the first time.",
        retroactive_rule="resource_any_positive",
    ),
    AchievementDef(
        "resource_stone_1000",
        "Stone Mason",
        "Resource Milestones",
        "Accumulate 1,000 stone total.",
        retroactive_rule="resource_lower_bound",
        resource="stone",
        threshold=1_000,
    ),
    AchievementDef(
        "resource_iron_500",
        "Iron Worker",
        "Resource Milestones",
        "Accumulate 500 iron total.",
        retroactive_rule="resource_lower_bound",
        resource="iron",
        threshold=500,
    ),
    AchievementDef(
        "resource_gems_100",
        "Gem Seeker",
        "Resource Milestones",
        "Accumulate 100 gems total.",
        retroactive_rule="resource_lower_bound",
        resource="gems",
        threshold=100,
    ),
    AchievementDef(
        "resource_stone_100000",
        "Rock Baron",
        "Resource Milestones",
        "Accumulate 100,000 stone total.",
        retroactive_rule="resource_lower_bound",
        resource="stone",
        threshold=100_000,
    ),
    AchievementDef(
        "resource_iron_50000",
        "Iron Titan",
        "Resource Milestones",
        "Accumulate 50,000 iron total.",
        retroactive_rule="resource_lower_bound",
        resource="iron",
        threshold=50_000,
    ),
    AchievementDef(
        "resource_gems_5000",
        "Gem Hoarder",
        "Resource Milestones",
        "Accumulate 5,000 gems total.",
        retroactive_rule="resource_lower_bound",
        resource="gems",
        threshold=5_000,
    ),
    AchievementDef(
        "party_three_players",
        "Crew Call",
        "Party Play",
        "Participate in a rock encounter alongside 2 or more other players (3+ total).",
    ),
    AchievementDef(
        "party_role_breaker", "The Breaker", "Party Play", "Earn the Breaker synergy role in a party encounter."
    ),
    AchievementDef(
        "party_role_stabilizer",
        "The Stabilizer",
        "Party Play",
        "Earn the Stabilizer synergy role in a party encounter.",
    ),
    AchievementDef(
        "party_role_finisher", "The Finisher", "Party Play", "Earn the Finisher synergy role in a party encounter."
    ),
    AchievementDef(
        "party_full_synergy",
        "Full Synergy",
        "Party Play",
        "Be part of a party where all 3 synergy roles are simultaneously active on the same rock.",
    ),
    AchievementDef(
        "party_group_sessions_25",
        "Better With Friends",
        "Party Play",
        "Participate in 25 group mining sessions where at least one other player contributed.",
    ),
    AchievementDef(
        "party_all_roles",
        "Jack of All Trades",
        "Party Play",
        "Earn all 3 party synergy roles at least once.",
    ),
    AchievementDef("rocks_mined_50", "Regular", "Rock Count Milestones", "Mine 50 rocks total."),
    AchievementDef("rocks_mined_250", "Veteran Miner", "Rock Count Milestones", "Mine 250 rocks total."),
    AchievementDef("rocks_mined_1000", "Rock Legend", "Rock Count Milestones", "Mine 1,000 rocks total."),
    AchievementDef(
        "rock_variety_all",
        "All Shapes and Sizes",
        "Rock Count Milestones",
        "Mine a Small Rock, Medium Rock, Large Rock, Meteor, and Volatile Geode at least once each.",
    ),
    AchievementDef("rare_first_meteor", "Starfall", "Rare Encounters", "Mine your first Meteor."),
    AchievementDef("rare_first_geode", "The Unstable", "Rare Encounters", "Mine your first Volatile Geode."),
)


ACHIEVEMENTS_BY_KEY: dict[str, AchievementDef] = {achievement.key: achievement for achievement in ACHIEVEMENTS}
TOTAL_ACHIEVEMENTS: int = len(ACHIEVEMENTS)

CLEAN_STREAK_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (5, "clean_streak_5"),
    (10, "clean_streak_10"),
    (25, "clean_streak_25"),
    (50, "clean_streak_50"),
    (100, "clean_streak_100"),
)

SOLO_SPEED_THRESHOLDS: dict[constants.RockTierName, tuple[str, float]] = {
    "small": ("solo_speed_small", 20.0),
    "medium": ("solo_speed_medium", 40.0),
    "large": ("solo_speed_large", 60.0),
    "meteor": ("solo_speed_meteor", 90.0),
    "volatile geode": ("solo_speed_geode", 130.0),
}

ROCK_COUNT_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (50, "rocks_mined_50"),
    (250, "rocks_mined_250"),
    (1000, "rocks_mined_1000"),
)

MODIFIER_ACHIEVEMENT_KEYS: dict[str, str] = {
    "electrified": "modifier_electrified",
    "crystalline": "modifier_crystalline",
    "volatile": "modifier_volatile",
    "enchanted": "modifier_enchanted",
    "fortified": "modifier_fortified",
    "blessed": "modifier_blessed",
}

PERFORMANCE_ANY_THRESHOLD: int = constants.PERFORMANCE_BONUS_TIERS[-1][0] if constants.PERFORMANCE_BONUS_TIERS else 70
PERFORMANCE_MAX_THRESHOLD: int = constants.PERFORMANCE_BONUS_TIERS[0][0] if constants.PERFORMANCE_BONUS_TIERS else 90


def iter_achievements_by_category() -> tuple[tuple[AchievementCategory, tuple[AchievementDef, ...]], ...]:
    grouped: list[tuple[AchievementCategory, tuple[AchievementDef, ...]]] = []
    for category in CATEGORY_ORDER:
        items = tuple(achievement for achievement in ACHIEVEMENTS if achievement.category == category)
        grouped.append((category, items))
    return tuple(grouped)


def dedupe_achievement_defs(items: t.Iterable[AchievementDef]) -> list[AchievementDef]:
    seen: set[str] = set()
    deduped: list[AchievementDef] = []
    for item in items:
        if item.key in seen:
            continue
        seen.add(item.key)
        deduped.append(item)
    return deduped


def get_exact_retroactive_unlock_keys(
    tool: constants.ToolName,
    resource_lower_bounds: dict[constants.Resource, int],
) -> list[str]:
    unlocked: list[str] = []
    tool_index = constants.TOOL_ORDER.index(tool)

    for achievement in ACHIEVEMENTS:
        if achievement.retroactive_rule == "tool_at_least_tier" and achievement.tool is not None:
            if constants.TOOL_ORDER.index(achievement.tool) <= tool_index:
                unlocked.append(achievement.key)
        elif achievement.retroactive_rule == "resource_any_positive":
            if any(resource_lower_bounds.get(resource, 0) > 0 for resource in constants.RESOURCES):
                unlocked.append(achievement.key)
        elif (
            achievement.retroactive_rule == "resource_lower_bound"
            and achievement.resource is not None
            and achievement.threshold is not None
        ):
            if resource_lower_bounds.get(achievement.resource, 0) >= achievement.threshold:
                unlocked.append(achievement.key)

    return unlocked
