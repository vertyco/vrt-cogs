from __future__ import annotations

import typing as t
from dataclasses import dataclass

# Type aliases
Resource = t.Literal["stone", "iron", "gems"]
ToolName = t.Literal["wood", "stone", "iron", "steel"]
RockTierName = t.Literal["small", "medium", "large", "meteor", "volatile geode"]

RESOURCES: tuple[Resource, ...] = ("stone", "iron", "gems")
TOOL_ORDER: tuple[ToolName, ...] = ("wood", "stone", "iron", "steel", "carbide", "diamond")
ROCK_ORDER: tuple[RockTierName, ...] = ("small", "medium", "large", "meteor", "volatile geode")

# Pacing
SWINGS_PER_THRESHOLD: int = 3
OVERSWING_THRESHOLD_SECONDS: int = 3  # seconds between swings to count as overswing
# Fraction of max durability at or below which catastrophic overswing shatters are allowed
OVERSWING_SHATTER_DURA_THRESHOLD: float = 0.25
# Durability percentage thresholds where we start warning players about tool condition
DURABILITY_WARNING_THRESHOLDS: tuple[float, ...] = (0.25, 0.10)

# Spawning
ACTIVITY_WINDOW_SECONDS: int = 5 * 60  # Length of sliding window in seconds
MIN_TIME_BETWEEN_SPAWNS: int = 10  # seconds
ABSOLUTE_MAX_TIME_BETWEEN_SPAWNS: int = 10 * 60  # 10 minutes, after which even a single person can spawn a rock
SPAWN_PROB_MIN: float = 0.05  # minimum spawn chance
SPAWN_PROB_MAX: float = 0.50  # maximum spawn chance
SCALE_PER_MESSAGE: float = 0.03  # per-message increase to spawn chance
SPAWN_BONUS_MAX: float = 0.15  # max activity bonus to add to spawn chance

# Spawn feedback (UX)
RUMBLE_MIN_INTERVAL_SECONDS: float = 60.0  # minimum time between rumble messages per key
RUMBLE_MEDIUM_THRESHOLD: float = 0.10  # spawn probability where rumble feedback can start
RUMBLE_HIGH_THRESHOLD: float = 0.30  # spawn probability considered "high" for rumble
RUMBLE_CHANCE_MEDIUM: float = 0.10  # chance to send rumble when in medium range
RUMBLE_CHANCE_HIGH: float = 0.30  # chance to send rumble when in high range

# Status command spawn buckets
STATUS_PROB_LOW_MAX: float = 0.05
STATUS_PROB_MEDIUM_MAX: float = 0.20

PER_GUILD_ROCK_CAP: int = 4
PER_CHANNEL_ROCK_CAP: int = 1

# UI / visuals
HP_BAR_SEGMENTS: int = 10
HP_BAR_FILLED: str = "▰"
HP_BAR_EMPTY: str = "▱"

# Tool repair cost percentage (e.g., 0.5 = 50% of upgrade cost)
TOOL_REPAIR_COST_PCT: float = 0.5
HITS_PER_DURA_LOST: int = 4  # 1 durability lost per 4 hits

# Emojis (adjust to your server assets if needed)
PICKAXE_EMOJI: str = "\N{PICK}\N{VARIATION SELECTOR-16}"
ROCK_EMOJI: str = "\N{ROCK}"
GEM_EMOJI: str = "\N{GEM STONE}"
INSPECT_EMOJI: str = "\N{LEFT-POINTING MAGNIFYING GLASS}"
IRON_EMOJI: str = "\N{CHAINS}\N{VARIATION SELECTOR-16}"
TROPHY_EMOJI: str = "\N{TROPHY}"
CLOCK_EMOJI: str = "\N{ALARM CLOCK}"


def resource_emoji(resource: str) -> str:
    match resource:
        case "stone":
            return ROCK_EMOJI
        case "iron":
            return IRON_EMOJI
        case "gems":
            return GEM_EMOJI
        case _:
            return ""


# Static image URLs
COLLAPSED_MINESHAFT_URL = "https://i.imgur.com/QIHaYpJ.png"
DEPLETED_ROCK_URL = "https://i.imgur.com/lJhh1n2.png"


@dataclass(frozen=True, slots=True)
class ToolTier:
    key: ToolName
    display_name: str
    power: int
    crit_chance: float
    crit_multiplier: float
    # None for base tier; dict for upgrade cost in resources
    upgrade_cost: dict[Resource, int] | None
    max_durability: int | None
    shatter_resistance: float = 0.0  # Chance to resist shattering on overswing


TOOLS: dict[ToolName, ToolTier] = {
    "wood": ToolTier(
        key="wood",
        display_name="Wood Pickaxe",
        power=4,
        crit_chance=0.05,
        crit_multiplier=1.25,
        upgrade_cost=None,
        max_durability=None,
    ),
    "stone": ToolTier(
        key="stone",
        display_name="Stone Pickaxe",
        power=7,
        crit_chance=0.07,
        crit_multiplier=1.4,
        upgrade_cost={"stone": 90},
        max_durability=98,
        shatter_resistance=0.02,
    ),
    "iron": ToolTier(
        key="iron",
        display_name="Iron Pickaxe",
        power=11,
        crit_chance=0.09,
        crit_multiplier=1.4,
        upgrade_cost={"stone": 260, "iron": 80},
        max_durability=242,
        shatter_resistance=0.06,
    ),
    "steel": ToolTier(
        key="steel",
        display_name="Steel Pickaxe",
        power=16,
        crit_chance=0.11,
        crit_multiplier=1.5,
        upgrade_cost={"stone": 440, "iron": 500, "gems": 10},
        max_durability=512,
        shatter_resistance=0.12,
    ),
    "carbide": ToolTier(
        key="carbide",
        display_name="Carbide Pickaxe",
        power=22,
        crit_chance=0.15,
        crit_multiplier=1.6,
        upgrade_cost={"stone": 3400, "iron": 1750, "gems": 30},
        max_durability=968,
        shatter_resistance=0.24,
    ),
    "diamond": ToolTier(
        key="diamond",
        display_name="Diamond Pickaxe",
        power=29,
        crit_chance=0.2,
        crit_multiplier=1.8,
        upgrade_cost={"stone": 6750, "iron": 2220, "gems": 115},
        max_durability=1682,
        shatter_resistance=0.50,
    ),
}


@dataclass(frozen=True, slots=True)
class RockType:
    key: RockTierName
    display_name: str
    hp: int
    image_url: str
    # Rarity: higher means rarer (e.g. 1=common, 2=uncommon, 3=rare, 4=epic, 5=legendary, 6=mythic, 7=divine)
    rarity: int
    # Total loot generated by this rock when depleted (distributed across contributors)
    total_loot: dict[Resource, int]
    # Minimum guaranteed loot per participant with >=1 hit
    floor_loot: dict[Resource, int]
    # Chance for players tool to break on overswing
    overswing_break_chance: float
    overswing_damage_chance: float
    # If tool doesnt shatter, how much damage to deal to tool durability
    overswing_damage: int
    # How long this rock stays active before collapsing, in seconds
    ttl_seconds: int


ROCK_TYPES: dict[RockTierName, RockType] = {
    "small": RockType(
        key="small",
        display_name="Small Rock",
        hp=120,
        image_url="https://i.imgur.com/1J23T3m.png",
        rarity=1,
        total_loot={"stone": 45},
        floor_loot={"stone": 5},
        overswing_break_chance=0.0,
        overswing_damage_chance=0.1,
        overswing_damage=5,
        ttl_seconds=90,
    ),
    "medium": RockType(
        key="medium",
        display_name="Medium Rock",
        hp=360,
        image_url="https://i.imgur.com/4MQBGYi.png",
        rarity=2,
        total_loot={"stone": 170, "iron": 30},
        floor_loot={"stone": 30},
        overswing_break_chance=0.02,
        overswing_damage_chance=0.1,
        overswing_damage=15,
        ttl_seconds=120,
    ),
    "large": RockType(
        key="large",
        display_name="Large Rock",
        hp=1000,
        image_url="https://i.imgur.com/BNrC5MD.png",
        rarity=3,
        total_loot={"stone": 360, "iron": 180, "gems": 2},
        floor_loot={"stone": 65, "iron": 20},
        overswing_break_chance=0.03,
        overswing_damage_chance=0.1,
        overswing_damage=25,
        ttl_seconds=150,
    ),
    "meteor": RockType(
        key="meteor",
        display_name="Meteor",
        hp=2000,
        image_url="https://i.imgur.com/fl1Hdts.png",
        rarity=10,
        total_loot={"stone": 75, "iron": 360, "gems": 10},
        floor_loot={"stone": 10, "iron": 42, "gems": 1},
        overswing_break_chance=0.1,
        overswing_damage_chance=0.35,
        overswing_damage=50,
        ttl_seconds=180,
    ),
    "volatile geode": RockType(
        key="volatile geode",
        display_name="Volatile Geode",
        hp=1500,
        image_url="https://i.imgur.com/bMPINaW.png",
        rarity=20,
        total_loot={"iron": 240, "gems": 65},
        floor_loot={"iron": 65, "gems": 7},
        overswing_break_chance=0.5,
        overswing_damage_chance=0.05,
        overswing_damage=80,
        ttl_seconds=210,
    ),
}

MAX_ROCK_TTL_SECONDS: int = max(rock.ttl_seconds for rock in ROCK_TYPES.values())
