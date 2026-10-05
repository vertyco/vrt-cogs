from __future__ import annotations

import typing as t
from dataclasses import dataclass

from . import constants

AchievementCategory = t.Literal[
    "Clean Mining",
    "Solo Speed Clears",
    "Elite Speed Clears",
    "Tool Mastery",
    "Performance Bonuses",
    "Critical Hits",
    "Rock Modifiers",
    "Modifier Combos",
    "Resource Milestones",
    "Party Play",
    "Crew Milestones",
    "Role Mastery",
    "Rock Count Milestones",
    "Rare Encounters",
    "Clutch Plays",
    "Mishaps",
    "Mastery",
]
RetroactiveRule = t.Literal[
    "resource_lower_bound",
    "resource_any_positive",
    "tool_at_least_tier",
    "stat_at_least",
    "all_stats_positive",
    "solo_time_within",
    "collection",
]


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
    stat: str | None = None  # PlayerAchievementStats column read by stat_at_least / solo_time_within
    stats: tuple[str, ...] | None = None  # Columns that must all be positive for all_stats_positive
    seconds: float | None = None  # Time limit for solo_time_within
    requires: tuple[str, ...] | None = None  # Keys a collection needs; None means every other visible achievement
    hidden: bool = False  # Shown as ??? until unlocked


CATEGORY_ORDER: tuple[AchievementCategory, ...] = t.get_args(AchievementCategory)

ROLE_STATS: tuple[str, ...] = ("role_breaker_total", "role_stabilizer_total", "role_finisher_total")
VARIETY_STATS: tuple[str, ...] = ("mined_small", "mined_medium", "mined_large", "mined_meteor", "mined_geode")
MODIFIER_KEYS: tuple[str, ...] = (
    "modifier_electrified",
    "modifier_crystalline",
    "modifier_volatile",
    "modifier_enchanted",
    "modifier_fortified",
    "modifier_blessed",
)
SPEED_KEYS: tuple[str, ...] = (
    "solo_speed_small",
    "solo_speed_medium",
    "solo_speed_large",
    "solo_speed_meteor",
    "solo_speed_geode",
    "elite_speed_small",
    "elite_speed_medium",
    "elite_speed_large",
    "elite_speed_geode",
)


def counter(
    key: str, name: str, category: AchievementCategory, condition: str, stat: str, threshold: int, hidden: bool = False
) -> AchievementDef:
    """An achievement that unlocks once a saved stats column reaches `threshold`."""
    return AchievementDef(
        key, name, category, condition, retroactive_rule="stat_at_least", stat=stat, threshold=threshold, hidden=hidden
    )


def solo_time(
    key: str, name: str, category: AchievementCategory, condition: str, stat: str, seconds: float
) -> AchievementDef:
    """An achievement that unlocks once the saved best solo clear time is within `seconds`."""
    return AchievementDef(
        key, name, category, condition, retroactive_rule="solo_time_within", stat=stat, seconds=seconds
    )


ACHIEVEMENTS: tuple[AchievementDef, ...] = (
    # Clean Mining
    counter(
        "clean_streak_5",
        "Steady Hands",
        "Clean Mining",
        "Mine 5 rocks in a row without a single overswing.",
        "clean_streak_best",
        5,
    ),
    counter(
        "clean_streak_10",
        "Iron Discipline",
        "Clean Mining",
        "Mine 10 rocks in a row without a single overswing.",
        "clean_streak_best",
        10,
    ),
    counter(
        "clean_streak_25",
        "Patient Miner",
        "Clean Mining",
        "Mine 25 rocks in a row without a single overswing.",
        "clean_streak_best",
        25,
    ),
    counter(
        "clean_streak_50",
        "Unbreakable Focus",
        "Clean Mining",
        "Mine 50 rocks in a row without a single overswing.",
        "clean_streak_best",
        50,
    ),
    counter(
        "clean_streak_100",
        "Perfect Rhythm",
        "Clean Mining",
        "Mine 100 rocks in a row without a single overswing.",
        "clean_streak_best",
        100,
    ),
    # Solo Speed Clears
    solo_time(
        "solo_speed_small",
        "Lone Chipper",
        "Solo Speed Clears",
        "Solo clear a Small Rock within 20 seconds.",
        "best_solo_small_seconds",
        20.0,
    ),
    solo_time(
        "solo_speed_medium",
        "Lone Striker",
        "Solo Speed Clears",
        "Solo clear a Medium Rock within 40 seconds.",
        "best_solo_medium_seconds",
        40.0,
    ),
    solo_time(
        "solo_speed_large",
        "Lone Crusher",
        "Solo Speed Clears",
        "Solo clear a Large Rock within 60 seconds.",
        "best_solo_large_seconds",
        60.0,
    ),
    solo_time(
        "solo_speed_meteor",
        "Meteor Slayer",
        "Solo Speed Clears",
        "Solo clear a Meteor within 90 seconds.",
        "best_solo_meteor_seconds",
        90.0,
    ),
    solo_time(
        "solo_speed_geode",
        "Geode Tamer",
        "Solo Speed Clears",
        "Solo clear a Volatile Geode within 130 seconds.",
        "best_solo_geode_seconds",
        130.0,
    ),
    # Elite Speed Clears
    solo_time(
        "elite_speed_small",
        "Blink",
        "Elite Speed Clears",
        "Solo clear a Small Rock within 8 seconds.",
        "best_solo_small_seconds",
        8.0,
    ),
    solo_time(
        "elite_speed_medium",
        "Rapid Fire",
        "Elite Speed Clears",
        "Solo clear a Medium Rock within 20 seconds.",
        "best_solo_medium_seconds",
        20.0,
    ),
    solo_time(
        "elite_speed_large",
        "Landslide",
        "Elite Speed Clears",
        "Solo clear a Large Rock within 50 seconds.",
        "best_solo_large_seconds",
        50.0,
    ),
    solo_time(
        "elite_speed_geode",
        "Defuser",
        "Elite Speed Clears",
        "Solo clear a Volatile Geode within 80 seconds.",
        "best_solo_geode_seconds",
        80.0,
    ),
    # Tool Mastery
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
    # Performance Bonuses. A 90+ score also counts as 70+, so the best 90+ streak proves both firsts.
    counter(
        "perf_any_bonus",
        "Above Average",
        "Performance Bonuses",
        "Earn any performance bonus tier (70+ score) on a rock.",
        "perf_max_streak_best",
        1,
    ),
    counter(
        "perf_max_any",
        "Peak Performance",
        "Performance Bonuses",
        "Earn the maximum performance score (90+) on any rock.",
        "perf_max_streak_best",
        1,
    ),
    counter(
        "perf_max_streak_3",
        "Triple Crown",
        "Performance Bonuses",
        "Earn the maximum performance score (90+) on 3 consecutive rocks.",
        "perf_max_streak_best",
        3,
    ),
    counter(
        "perf_max_streak_5",
        "Untouchable",
        "Performance Bonuses",
        "Earn a 90+ performance score on 5 rocks in a row.",
        "perf_max_streak_best",
        5,
    ),
    counter(
        "perf_max_streak_10",
        "Machine",
        "Performance Bonuses",
        "Earn a 90+ performance score on 10 rocks in a row.",
        "perf_max_streak_best",
        10,
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
    # Critical Hits
    AchievementDef("crit_first", "Lucky Hit", "Critical Hits", "Land your first critical hit."),
    AchievementDef(
        "crit_five_single_rock",
        "Critical Mass",
        "Critical Hits",
        "Land 5 critical hits within a single rock encounter.",
    ),
    AchievementDef(
        "crit_ten_single_rock", "Crit Storm", "Critical Hits", "Land 10 critical hits within a single rock encounter."
    ),
    # Rock Modifiers
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
    counter(
        "modifier_total_50",
        "Modifier Magnet",
        "Rock Modifiers",
        "Mine 50 rocks that had at least one modifier active.",
        "modifier_rocks_mined_total",
        50,
    ),
    counter(
        "modifier_total_250",
        "Storm Chaser",
        "Rock Modifiers",
        "Mine 250 rocks that had at least one modifier active.",
        "modifier_rocks_mined_total",
        250,
    ),
    counter(
        "modifier_total_1000",
        "Anomaly Hunter",
        "Rock Modifiers",
        "Mine 1,000 rocks that had at least one modifier active.",
        "modifier_rocks_mined_total",
        1000,
    ),
    # Modifier Combos
    AchievementDef(
        "combo_divine", "Divine Combo", "Modifier Combos", "Mine a rock that is both Blessed and Enchanted."
    ),
    AchievementDef(
        "combo_perfect_storm",
        "Perfect Storm",
        "Modifier Combos",
        "Clear a rock that is both Electrified and Volatile without a single overswing.",
    ),
    AchievementDef("combo_siege_breaker", "Siege Breaker", "Modifier Combos", "Solo clear a Fortified rock."),
    # Resource Milestones
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
        "resource_stone_500000",
        "Quarry King",
        "Resource Milestones",
        "Accumulate 500,000 stone total.",
        retroactive_rule="resource_lower_bound",
        resource="stone",
        threshold=500_000,
    ),
    AchievementDef(
        "resource_iron_250000",
        "Foundry Boss",
        "Resource Milestones",
        "Accumulate 250,000 iron total.",
        retroactive_rule="resource_lower_bound",
        resource="iron",
        threshold=250_000,
    ),
    AchievementDef(
        "resource_gems_25000",
        "Dragon's Hoard",
        "Resource Milestones",
        "Accumulate 25,000 gems total.",
        retroactive_rule="resource_lower_bound",
        resource="gems",
        threshold=25_000,
    ),
    # Party Play
    AchievementDef(
        "party_three_players",
        "Crew Call",
        "Party Play",
        "Participate in a rock encounter alongside 2 or more other players (3+ total).",
    ),
    counter(
        "party_role_breaker",
        "The Breaker",
        "Party Play",
        "Earn the Breaker synergy role in a party encounter.",
        "role_breaker_total",
        1,
    ),
    counter(
        "party_role_stabilizer",
        "The Stabilizer",
        "Party Play",
        "Earn the Stabilizer synergy role in a party encounter.",
        "role_stabilizer_total",
        1,
    ),
    counter(
        "party_role_finisher",
        "The Finisher",
        "Party Play",
        "Earn the Finisher synergy role in a party encounter.",
        "role_finisher_total",
        1,
    ),
    AchievementDef(
        "party_full_synergy",
        "Full Synergy",
        "Party Play",
        "Be part of a party where all 3 synergy roles are simultaneously active on the same rock.",
    ),
    counter(
        "party_group_sessions_25",
        "Better With Friends",
        "Party Play",
        "Participate in 25 group mining sessions where at least one other player contributed.",
        "group_sessions_total",
        25,
    ),
    AchievementDef(
        "party_all_roles",
        "Jack of All Trades",
        "Party Play",
        "Earn all 3 party synergy roles at least once.",
        retroactive_rule="all_stats_positive",
        stats=ROLE_STATS,
    ),
    # Crew Milestones
    counter(
        "party_group_sessions_100",
        "Crew Chief",
        "Crew Milestones",
        "Participate in 100 group mining sessions.",
        "group_sessions_total",
        100,
    ),
    counter(
        "party_group_sessions_500",
        "Union Rep",
        "Crew Milestones",
        "Participate in 500 group mining sessions.",
        "group_sessions_total",
        500,
    ),
    AchievementDef(
        "party_six_players",
        "Expedition",
        "Crew Milestones",
        "Mine a rock alongside 5 or more other players (6+ total).",
    ),
    AchievementDef(
        "party_ten_players",
        "Gold Rush",
        "Crew Milestones",
        "Mine a rock alongside 9 or more other players (10+ total).",
    ),
    # Role Mastery
    counter(
        "role_breaker_50", "Wrecking Ball", "Role Mastery", "Earn the Breaker role 50 times.", "role_breaker_total", 50
    ),
    counter(
        "role_stabilizer_50",
        "Steady as Stone",
        "Role Mastery",
        "Earn the Stabilizer role 50 times.",
        "role_stabilizer_total",
        50,
    ),
    counter(
        "role_finisher_50", "The Closer", "Role Mastery", "Earn the Finisher role 50 times.", "role_finisher_total", 50
    ),
    AchievementDef(
        "role_tag_team",
        "Tag Team",
        "Role Mastery",
        "Mine a rock with exactly one other player where you both earn a role.",
    ),
    # Rock Count Milestones
    counter("rocks_mined_50", "Regular", "Rock Count Milestones", "Mine 50 rocks total.", "rocks_mined_total", 50),
    counter(
        "rocks_mined_250", "Veteran Miner", "Rock Count Milestones", "Mine 250 rocks total.", "rocks_mined_total", 250
    ),
    counter(
        "rocks_mined_1000", "Rock Legend", "Rock Count Milestones", "Mine 1,000 rocks total.", "rocks_mined_total", 1000
    ),
    counter(
        "rocks_mined_2500",
        "Mountain Mover",
        "Rock Count Milestones",
        "Mine 2,500 rocks total.",
        "rocks_mined_total",
        2500,
    ),
    counter(
        "rocks_mined_5000", "Bedrock", "Rock Count Milestones", "Mine 5,000 rocks total.", "rocks_mined_total", 5000
    ),
    counter(
        "rocks_mined_10000",
        "Geologist",
        "Rock Count Milestones",
        "Mine 10,000 rocks total.",
        "rocks_mined_total",
        10000,
    ),
    AchievementDef(
        "rock_variety_all",
        "All Shapes and Sizes",
        "Rock Count Milestones",
        "Mine a Small Rock, Medium Rock, Large Rock, Meteor, and Volatile Geode at least once each.",
        retroactive_rule="all_stats_positive",
        stats=VARIETY_STATS,
    ),
    # Rare Encounters
    counter("rare_first_meteor", "Starfall", "Rare Encounters", "Mine your first Meteor.", "mined_meteor", 1),
    counter("rare_first_geode", "The Unstable", "Rare Encounters", "Mine your first Volatile Geode.", "mined_geode", 1),
    # Clutch Plays
    AchievementDef(
        "clutch_carry", "Carried the Team", "Clutch Plays", "Deal 70% or more of the damage on a rock with 3+ miners."
    ),
    AchievementDef(
        "clutch_photo_finish",
        "Photo Finish",
        "Clutch Plays",
        "Clear a rock in the last 5 seconds before it collapses.",
        hidden=True,
    ),
    AchievementDef(
        "clutch_underdog",
        "Underdog",
        "Clutch Plays",
        "Deal the most damage on a rock with 3+ miners while holding the weakest pickaxe there.",
    ),
    AchievementDef(
        "clutch_fumes",
        "Running on Fumes",
        "Clutch Plays",
        "Clear a rock and end it with your pickaxe at 5% durability or less, still intact.",
    ),
    AchievementDef(
        "clutch_glass_cannon",
        "Glass Cannon",
        "Clutch Plays",
        "Earn a 90+ score on a Volatile Geode and end it with your pickaxe at 30% durability or less.",
    ),
    AchievementDef(
        "clutch_splinters",
        "Splinters",
        "Clutch Plays",
        "Help clear a Meteor or Volatile Geode while swinging a Wood Pickaxe.",
    ),
    # Mishaps
    AchievementDef("mishap_butterfingers", "Butterfingers", "Mishaps", "Shatter a Diamond Pickaxe.", hidden=True),
    AchievementDef("mishap_wrong_rock", "Wrong Rock", "Mishaps", "Shatter a pickaxe on a Volatile Geode.", hidden=True),
    AchievementDef(
        "mishap_so_close",
        "So Close",
        "Mishaps",
        "Be part of a rock that collapses with 5% HP or less left.",
        hidden=True,
    ),
    # Mastery. Completionist stays last so it sees the other collections unlocked in the same pass.
    AchievementDef(
        "mastery_modifiers",
        "Modifier Collector",
        "Mastery",
        "Unlock all 6 single-modifier achievements.",
        retroactive_rule="collection",
        requires=MODIFIER_KEYS,
    ),
    AchievementDef(
        "mastery_speed",
        "Speed Demon",
        "Mastery",
        "Unlock every Solo Speed Clear and Elite Speed Clear.",
        retroactive_rule="collection",
        requires=SPEED_KEYS,
    ),
    AchievementDef(
        "mastery_completionist",
        "Completionist",
        "Mastery",
        "Unlock every other achievement that is not hidden.",
        retroactive_rule="collection",
    ),
)


ACHIEVEMENTS_BY_KEY: dict[str, AchievementDef] = {achievement.key: achievement for achievement in ACHIEVEMENTS}
TOTAL_ACHIEVEMENTS: int = len(ACHIEVEMENTS)

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


def stat_rule_met(achievement: AchievementDef, stats: t.Any) -> bool:
    """Whether a player's saved PlayerAchievementStats row proves a stat-based achievement."""
    rule = achievement.retroactive_rule
    if rule == "stat_at_least" and achievement.stat and achievement.threshold is not None:
        return (getattr(stats, achievement.stat) or 0) >= achievement.threshold
    if rule == "all_stats_positive" and achievement.stats:
        return all((getattr(stats, column) or 0) > 0 for column in achievement.stats)
    if rule == "solo_time_within" and achievement.stat and achievement.seconds is not None:
        # 0 means the player has never solo cleared that rock type
        return 0 < (getattr(stats, achievement.stat) or 0.0) <= achievement.seconds
    return False


def get_exact_retroactive_unlock_keys(
    tool: constants.ToolName,
    resource_lower_bounds: dict[constants.Resource, int],
    stats: t.Any,
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
        elif stat_rule_met(achievement, stats):
            unlocked.append(achievement.key)

    return unlocked


def required_keys(achievement: AchievementDef) -> tuple[str, ...]:
    """Keys a collection achievement needs. No list means every other achievement that is not hidden."""
    if achievement.requires is not None:
        return achievement.requires
    return tuple(item.key for item in ACHIEVEMENTS if not item.hidden and item.key != achievement.key)


def collection_unlock_keys(unlocked: set[str]) -> list[str]:
    """Collection achievements that `unlocked` completes, checked in catalogue order so one can feed the next."""
    have = set(unlocked)
    earned: list[str] = []
    for achievement in ACHIEVEMENTS:
        if achievement.retroactive_rule != "collection" or achievement.key in have:
            continue
        if all(key in have for key in required_keys(achievement)):
            have.add(achievement.key)
            earned.append(achievement.key)
    return earned
