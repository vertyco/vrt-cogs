import logging
import os
import typing as t
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import uuid4

import orjson
from pydantic import VERSION, BaseModel, Field, field_validator

log = logging.getLogger("red.vrt.botarena")


def get_weight_bar(
    chassis_weight: int,
    plating_weight: int,
    weapon_weight: int,
    capacity: int,
    bar_length: int = 12,
) -> str:
    """Generate a visual weight bar using colored emoji squares.

    Args:
        chassis_weight: Weight of the chassis itself (green squares)
        plating_weight: Weight of equipped plating (blue squares)
        weapon_weight: Weight of equipped weapon (red squares)
        capacity: Total weight capacity of the chassis
        bar_length: Length of the bar in squares (default 12)

    Returns:
        String like "🟩🟩🟩🟩🟦🟦🟥⬛⬛⬛⬛⬛⬛⬛⬛⬛"
    """
    if capacity <= 0:
        return "⬛" * bar_length

    # Calculate proportional squares (round to nearest)
    green = round(chassis_weight / capacity * bar_length)
    blue = round(plating_weight / capacity * bar_length)
    red = round(weapon_weight / capacity * bar_length)

    # Ensure we don't exceed bar_length due to rounding
    used = green + blue + red
    while used > bar_length:
        # Reduce the largest non-zero component first
        if red >= blue and red >= green and red > 0:
            red -= 1
        elif blue >= green and blue > 0:
            blue -= 1
        elif green > 0:
            green -= 1
        used = green + blue + red

    black = bar_length - green - blue - red

    bar = "🟩" * green + "🟦" * blue + "🟥" * red + "⬛" * max(0, black)
    return f"`{bar}`"


async def render_bot_image(
    plating_name: str,
    weapon_name: t.Optional[str],
    orientation: int = 0,
) -> bytes:
    """Get PNG image bytes of a bot with specified parts.

    Uses the unified render_bot_sprite_to_bytes() function for consistent
    rendering between battle and garage views.

    Args:
        plating_name: Name of the plating (required)
        weapon_name: Name of the weapon (or None)
        orientation: Orientation angle in degrees (0 = facing right)

    Returns:
        PNG image bytes showing the bot with its equipped parts
    """
    import asyncio

    from ..common.bot_sprite import render_bot_sprite_to_bytes
    from ..constants.parts import build_registry

    registry = build_registry()

    def _render():
        return render_bot_sprite_to_bytes(
            plating_name=plating_name,
            registry=registry,
            weapon_name=weapon_name,
            orientation=orientation,
            weapon_orientation=orientation,
            scale=0.65,  # Scale for 65x65 output from 80x80 base images
            output_size=(65, 65),
        )

    return await asyncio.to_thread(_render)


class ArenaBaseModel(BaseModel):
    """Base model with serialization helpers"""

    @classmethod
    def model_validate(cls, obj: t.Any, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)

    def model_dump(self, exclude_defaults: bool = False, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_dump(mode="json", exclude_defaults=exclude_defaults, **kwargs)
        return orjson.loads(super().json(exclude_defaults=exclude_defaults, **kwargs))

    def dumpjson(self, exclude_defaults: bool = False, pretty: bool = False, **kwargs) -> str:
        if pretty:
            kwargs["indent"] = 2
        if VERSION >= "2.0.1":
            return self.model_dump_json(exclude_defaults=exclude_defaults, **kwargs)
        return self.json(exclude_defaults=exclude_defaults, **kwargs)

    @classmethod
    def from_file(cls, path: Path) -> t.Self:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise IsADirectoryError(f"Path is not a file: {path}")
        if VERSION >= "2.0.1":
            text = path.read_text(encoding="utf-8")
            try:
                return cls.model_validate_json(text)
            except UnicodeDecodeError as e:
                log.warning(f"Failed to load {path}, attempting to load via json5")
                try:
                    import json5

                    data = json5.loads(text)
                    return cls.model_validate(data)
                except ImportError:
                    log.error("Failed to load via json5")
                    raise e
        try:
            return cls.parse_file(path, encoding="utf-8")
        except UnicodeDecodeError as e:
            log.warning(f"Failed to load {path}, attempting to load via json5")
            try:
                import json5

                data = json5.loads(path.read_text(encoding="utf-8"))
                return cls.parse_obj(data)
            except ImportError:
                log.error("Failed to load via json5")
                raise e

    def to_file(self, path: Path, pretty: bool = False) -> None:
        dump = self.dumpjson(exclude_defaults=True, pretty=pretty)
        # We want to write the file as safely as possible
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/core/_drivers/json.py#L224
        tmp_file = f"{path.stem}-{uuid4().fields[0]}.tmp"
        tmp_path = path.parent / tmp_file
        with tmp_path.open(encoding="utf-8", mode="w") as fs:
            fs.write(dump)
            fs.flush()  # This does get closed on context exit, ...
            os.fsync(fs.fileno())  # but that needs to happen prior to this line

        # Replace the original file with the new content
        tmp_path.replace(path)

        # Ensure directory fsync for better durability (Unix only)
        o_directory = getattr(os, "O_DIRECTORY", None)
        if o_directory is not None:
            fd = os.open(path.parent, o_directory)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


class WeightClass(str, Enum):
    LIGHT = "Light"
    MEDIUM = "Medium"
    HEAVY = "Heavy"
    ASSAULT = "Assault"


class ComponentType(str, Enum):
    WEAPON = "Weapon"
    HEALER = "Healer"
    SHIELD = "Shield"


# ─────────────────────────────────────────────────────────────────────────────
# TACTICAL ORDERS - Pre-battle configuration for bot AI behavior
# ─────────────────────────────────────────────────────────────────────────────
class MovementStance(str, Enum):
    """How the bot moves during combat - simplified to 3 core behaviors"""

    AGGRESSIVE = "aggressive"  # Close distance, stay in enemy's face
    DEFENSIVE = "defensive"  # Maintain max range, retreat when approached
    TACTICAL = "tactical"  # Balanced - optimal range with repositioning


class TargetPriority(str, Enum):
    """Who the bot targets - simplified to 3 meaningful options"""

    FOCUS_FIRE = "focus_fire"  # Attack same target as teammates (coordinated)
    WEAKEST = "weakest"  # Target lowest HP enemy (finish kills)
    CLOSEST = "closest"  # Attack nearest enemy (reactive, default)


class TacticalOrders(ArenaBaseModel):
    """Pre-battle orders that control bot AI behavior.

    - Movement Stance: How the bot positions itself (3 options)
    - Target Priority: Who the bot attacks (3 options)

    Total combinations: 9 (manageable for players to understand)
    """

    movement_stance: MovementStance = MovementStance.AGGRESSIVE
    target_priority: TargetPriority = TargetPriority.CLOSEST

    @field_validator("movement_stance", mode="before")
    @classmethod
    def migrate_legacy_stance(cls, v: t.Any) -> t.Any:
        """Convert legacy movement stance values to new defaults."""
        if isinstance(v, str):
            # Map legacy stances to their closest equivalents
            legacy_mapping = {
                "kiting": "tactical",  # Kiting → Tactical (balanced)
                "flanking": "aggressive",  # Flanking → Aggressive
                "hold": "defensive",  # Hold → Defensive
                "protector": "defensive",  # Protector → Defensive
            }
            return legacy_mapping.get(v, v)
        return v

    @field_validator("target_priority", mode="before")
    @classmethod
    def migrate_legacy_priority(cls, v: t.Any) -> t.Any:
        """Convert legacy target priority values to new defaults."""
        if isinstance(v, str):
            # Map legacy priorities to their closest equivalents
            legacy_mapping = {
                "strongest": "closest",  # Strongest → Closest (default)
                "furthest": "closest",  # Furthest → Closest (default)
            }
            return legacy_mapping.get(v, v)
        return v

    def get_summary(self) -> str:
        """Get a brief summary of the orders"""
        stance_icons = {
            MovementStance.AGGRESSIVE: "⚔️",
            MovementStance.DEFENSIVE: "🛡️",
            MovementStance.TACTICAL: "⚖️",
        }
        return f"{stance_icons.get(self.movement_stance, '•')} {self.movement_stance.value.title()}"


# ─────────────────────────────────────────────────────────────────────────────
# PART DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────
class Chassis(ArenaBaseModel):
    """The base frame of a bot - determines weight capacity, speed, and intelligence"""

    name: str
    weight_class: WeightClass
    speed: int  # Pixels per update cycle
    rotation_speed: int  # Degrees per update cycle
    turret_rotation_speed: int = 20  # Degrees per update cycle for weapon turret
    cost: int
    weight_capacity: int
    self_weight: int
    shielding: int  # Base shielding from chassis
    intelligence: int  # AI decision quality
    agility: float = 0.5  # 0.0-1.0: How well it can turn while moving (1.0 = full speed while turning)
    description: str = ""

    # ─── RENDER CENTER OVERRIDE ───────────────────────────────────────────────
    # By default, the center is assumed to be the middle of the image.
    # These offsets shift the rotation center from the image center.
    # Positive center_x = center is right of image center
    # Positive center_y = center is below image center
    # Units are in pixels of the SOURCE image (before any scaling)
    # ──────────────────────────────────────────────────────────────────────────
    center_x: float = 0.0  # X offset from image center for rotation pivot
    center_y: float = 0.0  # Y offset from image center for rotation pivot


class Plating(ArenaBaseModel):
    """Armor plating that provides additional shielding"""

    name: str
    shielding: int
    cost: int
    weight: int
    description: str = ""

    # ─── RENDER CENTER OVERRIDE ───────────────────────────────────────────────
    # By default, the center is assumed to be the middle of the image.
    # These offsets shift the rotation center from the image center.
    # Units are in pixels of the SOURCE image (before any scaling)
    # ──────────────────────────────────────────────────────────────────────────
    center_x: float = 0.0  # X offset from image center for rotation pivot
    center_y: float = 0.0  # Y offset from image center for rotation pivot

    # ─── WEAPON MOUNT POINT ────────────────────────────────────────────────────
    # The plating's weapon mount point determines where weapons are attached.
    # This is offset from the plating's center (after applying center_x/center_y).
    # If both are 0.0, weapons mount at the plating's rotation center.
    # Units are in pixels of the SOURCE image (before any scaling).
    # This allows each plating to have different weapon positioning, even when
    # using the same chassis.
    # ───────────────────────────────────────────────────────────────────────────
    weapon_mount_x: float = 0.0  # X offset from plating center for weapon attachment
    weapon_mount_y: float = 0.0  # Y offset from plating center for weapon attachment


class ProjectileType(str, Enum):
    BULLET = "bullet"  # Small round projectile, medium speed, white
    LASER = "laser"  # Thin beam line, very fast, red/orange
    CANNON = "cannon"  # Large round projectile, slower, blue
    MISSILE = "missile"  # Elongated shape with trail, medium speed, red/orange
    HEAL = "heal"  # Green healing beam
    SHOCKWAVE = "shockwave"  # Close-range hydraulic burst (Torrika KJ-557)


class Component(ArenaBaseModel):
    """Weapons, healers, and special equipment"""

    name: str
    component_type: ComponentType = ComponentType.WEAPON
    cost: int
    weight: int
    shots_per_minute: float
    damage_per_shot: int  # Negative for healers
    min_range: int
    max_range: int
    projectile_type: ProjectileType = ProjectileType.BULLET
    description: str = ""

    # ─── MOUNT POINT ──────────────────────────────────────────────────────────
    # The weapon rotates around its mount point, which is offset from image center.
    # mount_x/mount_y define the rotation pivot point as offset from image center.
    # Units are in pixels of the SOURCE image (before any scaling).
    # Typically mount_x is negative to place pivot near the back/handle of the weapon.
    # The mount point is also where the weapon attaches to the chassis center.
    # ──────────────────────────────────────────────────────────────────────────
    mount_x: float = 0.0  # X offset from image center for mount pivot
    mount_y: float = 0.0  # Y offset from image center for mount pivot

    @property
    def is_healer(self) -> bool:
        return self.component_type == ComponentType.HEALER or self.damage_per_shot < 0


# ─────────────────────────────────────────────────────────────────────────────
# BOT DEFINITION
# ─────────────────────────────────────────────────────────────────────────────
class Bot(ArenaBaseModel):
    """A fully assembled battle bot"""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique bot ID")
    name: str = "Unnamed Bot"
    chassis: Chassis
    plating: Plating
    component: Component

    # Tactical orders for battle AI
    tactical_orders: t.Optional[TacticalOrders] = None

    @property
    def total_weight(self) -> int:
        return self.chassis.self_weight + self.plating.weight + self.component.weight

    @property
    def weight_remaining(self) -> int:
        return self.chassis.weight_capacity - self.total_weight

    @property
    def total_shielding(self) -> int:
        return self.chassis.shielding + self.plating.shielding

    @property
    def total_cost(self) -> int:
        return self.chassis.cost + self.plating.cost + self.component.cost

    @property
    def is_valid(self) -> bool:
        """Check if the bot's total weight does not exceed the chassis's weight capacity."""
        return self.total_weight <= self.chassis.weight_capacity

    def get_stats_embed_field(self) -> str:
        """Return a formatted string for Discord embed fields"""
        return (
            f"**Chassis:** {self.chassis.name} ({self.chassis.weight_class.value})\n"
            f"**Plating:** {self.plating.name}\n"
            f"**Weapon:** {self.component.name}\n"
            f"**Shielding:** {self.total_shielding}\n"
            f"**Weight:** {self.total_weight}/{self.chassis.weight_capacity}\n"
            f"**Speed:** {self.chassis.speed} | **Intel:** {self.chassis.intelligence}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BATTLE STATE (Used during simulation)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class BotState:
    """Runtime state for a bot during battle"""

    bot: Bot
    health: int
    position: tuple[int, int] = field(default=None)
    orientation: int = 0  # Degrees, 0 = East, 90 = South
    turret_direction: int = 0
    team: int = field(default=None)
    last_shot_time: float = 0.0
    is_alive: bool = True

    def take_damage(self, damage: int) -> int:
        """Apply damage and return actual damage dealt"""
        actual = min(damage, self.health)
        self.health -= actual
        if self.health <= 0:
            self.health = 0
            self.is_alive = False
        return actual

    def heal(self, amount: int, max_health: int) -> int:
        """Heal and return actual amount healed"""
        if not self.is_alive:
            return 0
        actual = min(amount, max_health - self.health)
        self.health += actual
        return actual


@dataclass
class BattleResult:
    """Result of a completed battle"""

    winner_team: int  # 1, 2, or 0 for draw
    frames: list  # All frame states for rendering
    total_frames: int
    team1_survivors: list[str]  # Bot IDs that survived
    team2_survivors: list[str]
    damage_dealt: dict[str, int]  # Bot ID -> total damage dealt
    damage_taken: dict[str, int]  # Bot ID -> total damage taken


# ─────────────────────────────────────────────────────────────────────────────
# PLAYER DATA (Persisted via Config)
# ─────────────────────────────────────────────────────────────────────────────
class OwnedPart(ArenaBaseModel):
    """A part owned by a player (for inventory - unequipped plating/weapons)"""

    part_type: str  # "plating", "component"
    part_name: str
    quantity: int = 1


class OwnedChassis(ArenaBaseModel):
    """A chassis owned by a player - THIS IS THE BOT.

    The chassis is the core identity of the bot. Plating and weapons
    can be equipped/unequipped from it.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    chassis_name: str  # Reference to the chassis type
    custom_name: str = ""  # User-given name for this bot
    equipped_plating: t.Optional[str] = None  # Name of equipped plating (or None)
    equipped_weapon: t.Optional[str] = None  # Name of equipped weapon (or None)
    spawn_order: int = 0  # Spawn order priority (1-7, 0 = default/last)

    # Tactical orders - pre-battle AI configuration
    tactical_orders: TacticalOrders = Field(default_factory=TacticalOrders)

    @property
    def display_name(self) -> str:
        """Get the display name (custom name or chassis name)"""
        return self.custom_name or self.chassis_name

    @property
    def is_battle_ready(self) -> bool:
        """Check if bot has both plating and weapon equipped"""
        return self.equipped_plating is not None and self.equipped_weapon is not None

    def to_bot(self, parts_registry: "PartsRegistry") -> t.Optional[Bot]:
        """Convert to a full Bot object using the parts registry"""
        chassis = parts_registry.get_chassis(self.chassis_name)
        if not chassis:
            return None

        if not self.equipped_plating or not self.equipped_weapon:
            return None

        plating = parts_registry.get_plating(self.equipped_plating)
        component = parts_registry.get_component(self.equipped_weapon)

        if not all([chassis, plating, component]):
            return None

        return Bot(
            id=self.id,
            name=self.display_name,
            chassis=chassis,
            plating=plating,
            component=component,
            tactical_orders=self.tactical_orders,
        )

    def get_weight_display(self, registry: "PartsRegistry") -> str:
        """Get formatted weight display with visual bar.

        Args:
            registry: The parts registry to look up part weights

        Returns:
            String like "(8+4+2/32) 🟩🟩🟩🟩🟦🟦🟥⬛⬛⬛⬛⬛⬛⬛⬛⬛"
        """
        chassis = registry.get_chassis(self.chassis_name)
        plating = registry.get_plating(self.equipped_plating) if self.equipped_plating else None
        weapon = registry.get_component(self.equipped_weapon) if self.equipped_weapon else None

        c_weight = chassis.self_weight if chassis else 0
        p_weight = plating.weight if plating else 0
        w_weight = weapon.weight if weapon else 0
        capacity = chassis.weight_capacity if chassis else 1
        total = c_weight + p_weight + w_weight

        bar = get_weight_bar(c_weight, p_weight, w_weight, capacity)
        return f"{total} ({c_weight}+{p_weight}+{w_weight}/{capacity})\n{bar}"

    async def get_bot_image_bytes(self, orientation: int = 0) -> bytes:
        """Get PNG image bytes of this bot with equipped parts.

        Args:
            orientation: Orientation angle in degrees (0 = facing right)

        Returns:
            PNG image bytes showing the bot with its equipped parts.
            If no plating is equipped, returns the chassis image.

        Raises:
            RuntimeError: If no valid image could be generated.
        """
        if self.equipped_plating:
            # Have plating - render the full bot (plating + optional weapon)
            return await render_bot_image(
                plating_name=self.equipped_plating,
                weapon_name=self.equipped_weapon,
                orientation=orientation,
            )

        # No plating - just show the chassis image
        from ..common.image_utils import load_image_bytes

        chassis_bytes = load_image_bytes("chassis", self.chassis_name)
        if not chassis_bytes:
            raise RuntimeError(f"Failed to load chassis image for '{self.chassis_name}'")
        return chassis_bytes


# Available team colors for battle visualization
TEAM_COLORS = {
    "blue": (0, 120, 255),  # Bright blue
    "red": (255, 60, 60),  # Bright red
    "green": (60, 200, 60),  # Bright green
    "yellow": (255, 220, 0),  # Yellow
    "purple": (180, 60, 255),  # Purple
    "orange": (255, 140, 0),  # Orange
}

# Color emoji mapping for UI display
TEAM_COLOR_EMOJIS = {
    "blue": "🔵",
    "red": "🔴",
    "green": "🟢",
    "yellow": "🟡",
    "purple": "🟣",
    "orange": "🟠",
}


class PlayerData(ArenaBaseModel):
    """All data for a single player"""

    # Core resources
    # Starting credits: 8200 (original Bot Arena 3 starting cash)
    # Enough for: chassis (3000) + plating (300-800) + weapon (250-500) + upgrades
    credits: int = 8200

    # Team color for battle visualization
    team_color: str = "blue"

    # Chassis are the bots - each owned chassis is a bot
    owned_chassis: list[OwnedChassis] = Field(default_factory=list)

    # Equipment inventory - unequipped plating and weapons
    equipment_inventory: list[OwnedPart] = Field(default_factory=list)

    # Tutorial/onboarding state
    has_seen_tutorial: bool = False
    tutorial_step: int = 0  # Current tutorial step (0 = not started)

    # Campaign progress
    completed_missions: list[str] = Field(default_factory=list)  # Mission IDs
    attempted_missions: list[str] = Field(default_factory=list)  # Missions attempted (enemy info revealed)
    mission_attempts: dict[str, int] = Field(default_factory=dict)  # Mission ID -> attempt count
    unlocked_parts: list[str] = Field(default_factory=list)  # Parts unlocked via campaign

    # PvE stats
    campaign_wins: int = 0
    campaign_losses: int = 0

    # PvP stats
    pvp_wins: int = 0
    pvp_losses: int = 0
    pvp_draws: int = 0

    # Combat stats
    total_damage_dealt: int = 0
    total_damage_taken: int = 0
    bots_destroyed: int = 0
    bots_lost: int = 0

    @field_validator("team_color")
    @classmethod
    def validate_team_color(cls, v: str) -> str:
        """Ensure team_color is a valid option, fallback to blue if not."""
        if v not in TEAM_COLORS:
            return "blue"
        return v

    @property
    def wins(self) -> int:
        """Total wins (campaign + pvp)"""
        return self.campaign_wins + self.pvp_wins

    @property
    def losses(self) -> int:
        """Total losses (campaign + pvp)"""
        return self.campaign_losses + self.pvp_losses

    @property
    def draws(self) -> int:
        return self.pvp_draws

    @property
    def total_battles(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def win_rate(self) -> float:
        if self.total_battles == 0:
            return 0.0
        return self.wins / self.total_battles

    @property
    def has_any_parts(self) -> bool:
        """Check if the player owns any parts or chassis."""
        if self.owned_chassis:
            return True
        return any(part.quantity > 0 for part in self.equipment_inventory)

    @property
    def owned_parts(self) -> list["OwnedPart"]:
        """Return a unified list of owned parts, including chassis counts."""
        parts: list[OwnedPart] = [part for part in self.equipment_inventory if part.quantity > 0]
        chassis_counts: dict[str, int] = {}
        for chassis in self.owned_chassis:
            chassis_counts[chassis.chassis_name] = chassis_counts.get(chassis.chassis_name, 0) + 1
        for chassis_name, quantity in chassis_counts.items():
            parts.append(OwnedPart(part_type="chassis", part_name=chassis_name, quantity=quantity))
        return parts

    @property
    def campaign_progress(self) -> tuple[int, int]:
        """Return (completed, total) missions"""
        from .campaign import get_all_missions

        all_missions = get_all_missions()
        return len(self.completed_missions), len(all_missions)

    def has_completed_mission(self, mission_id: str) -> bool:
        """Check if a mission has been completed"""
        return mission_id in self.completed_missions

    def complete_mission(self, mission_id: str):
        """Mark a mission as completed"""
        if mission_id not in self.completed_missions:
            self.completed_missions.append(mission_id)

    def has_attempted_mission(self, mission_id: str) -> bool:
        """Check if a mission has been attempted (enemy info revealed)"""
        return mission_id in self.attempted_missions

    def attempt_mission(self, mission_id: str):
        """Mark a mission as attempted and increment attempt counter"""
        if mission_id not in self.attempted_missions:
            self.attempted_missions.append(mission_id)
        # Increment attempt count
        self.mission_attempts[mission_id] = self.mission_attempts.get(mission_id, 0) + 1

    def get_mission_attempts(self, mission_id: str) -> int:
        """Get the number of times this mission has been attempted"""
        return self.mission_attempts.get(mission_id, 0)

    def has_unlocked_part(self, part_name: str) -> bool:
        """Check if a part has been unlocked via campaign"""
        return part_name in self.unlocked_parts

    def unlock_part(self, part_name: str):
        """Unlock a part from campaign rewards"""
        if part_name not in self.unlocked_parts:
            self.unlocked_parts.append(part_name)

    # ─── NEW CHASSIS/BOT SYSTEM ────────────────────────────────────────────────

    def get_chassis_by_id(self, chassis_id: str) -> t.Optional[OwnedChassis]:
        """Find an owned chassis by ID"""
        for chassis in self.owned_chassis:
            if chassis.id == chassis_id:
                return chassis
        return None

    def get_chassis_by_name(self, name: str) -> t.Optional[OwnedChassis]:
        """Find an owned chassis by display name (case-insensitive)"""
        for chassis in self.owned_chassis:
            if chassis.display_name.lower() == name.lower():
                return chassis
        return None

    def get_battle_ready_bots(self) -> list[OwnedChassis]:
        """Get all chassis that have both plating and weapon equipped"""
        return [c for c in self.owned_chassis if c.is_battle_ready]

    def add_chassis(self, chassis_name: str, custom_name: str = "") -> t.Optional[OwnedChassis]:
        """Add a new chassis (bot) to the player's collection.

        Returns the new chassis, or None if the garage is full (max 7 bots).
        """
        if len(self.owned_chassis) >= 7:
            return None
        chassis = OwnedChassis(chassis_name=chassis_name, custom_name=custom_name)
        self.owned_chassis.append(chassis)
        return chassis

    def remove_chassis(self, chassis_id: str) -> t.Optional[OwnedChassis]:
        """Remove a chassis (returns the removed chassis, or None if not found)"""
        for i, chassis in enumerate(self.owned_chassis):
            if chassis.id == chassis_id:
                return self.owned_chassis.pop(i)
        return None

    def has_equipment(self, part_type: str, part_name: str) -> bool:
        """Check if player has a specific equipment piece in inventory"""
        for part in self.equipment_inventory:
            if part.part_type == part_type and part.part_name == part_name:
                return part.quantity > 0
        return False

    def get_equipment_quantity(self, part_type: str, part_name: str) -> int:
        """Get quantity of a specific equipment piece in inventory"""
        for part in self.equipment_inventory:
            if part.part_type == part_type and part.part_name == part_name:
                return part.quantity
        return 0

    def add_equipment(self, part_type: str, part_name: str, quantity: int = 1):
        """Add equipment to inventory"""
        for part in self.equipment_inventory:
            if part.part_type == part_type and part.part_name == part_name:
                part.quantity += quantity
                return
        self.equipment_inventory.append(OwnedPart(part_type=part_type, part_name=part_name, quantity=quantity))

    def remove_equipment(self, part_type: str, part_name: str, quantity: int = 1) -> bool:
        """Remove equipment from inventory. Returns True if successful."""
        for part in self.equipment_inventory:
            if part.part_type == part_type and part.part_name == part_name:
                if part.quantity >= quantity:
                    part.quantity -= quantity
                    return True
        return False

    def equip_plating(
        self, chassis_id: str, plating_name: str, registry: t.Optional["PartsRegistry"] = None
    ) -> tuple[bool, str]:
        """Equip plating to a chassis. Returns (success, message)

        Args:
            chassis_id: ID of the chassis to equip to
            plating_name: Name of the plating to equip
            registry: Parts registry for weight validation (optional but recommended)
        """
        chassis = self.get_chassis_by_id(chassis_id)
        if not chassis:
            return False, "Chassis not found"

        # Check if we have this plating in inventory
        if not self.has_equipment("plating", plating_name):
            return False, f"You don't have {plating_name} in your inventory"

        # Weight check if registry is provided
        if registry:
            chassis_def = registry.get_chassis(chassis.chassis_name)
            new_plating = registry.get_plating(plating_name)
            if chassis_def and new_plating:
                # Calculate weight with NEW plating (not old plating)
                chassis_weight = chassis_def.self_weight
                new_plating_weight = new_plating.weight
                weapon_weight = 0
                if chassis.equipped_weapon:
                    weapon = registry.get_component(chassis.equipped_weapon)
                    if weapon:
                        weapon_weight = weapon.weight

                total_weight = chassis_weight + new_plating_weight + weapon_weight
                if total_weight > chassis_def.weight_capacity:
                    return (
                        False,
                        f"This would make your bot overweight! Weight: {total_weight}/{chassis_def.weight_capacity}",
                    )

        # Unequip current plating first (returns to inventory)
        if chassis.equipped_plating:
            self.add_equipment("plating", chassis.equipped_plating)

        # Equip new plating
        self.remove_equipment("plating", plating_name)
        chassis.equipped_plating = plating_name
        return True, f"Equipped {plating_name}"

    def equip_weapon(
        self, chassis_id: str, weapon_name: str, registry: t.Optional["PartsRegistry"] = None
    ) -> tuple[bool, str]:
        """Equip weapon to a chassis. Returns (success, message)

        Args:
            chassis_id: ID of the chassis to equip to
            weapon_name: Name of the weapon to equip
            registry: Parts registry for weight validation (optional but recommended)
        """
        chassis = self.get_chassis_by_id(chassis_id)
        if not chassis:
            return False, "Chassis not found"

        # Check if we have this weapon in inventory
        if not self.has_equipment("component", weapon_name):
            return False, f"You don't have {weapon_name} in your inventory"

        # Weight check if registry is provided
        if registry:
            chassis_def = registry.get_chassis(chassis.chassis_name)
            new_weapon = registry.get_component(weapon_name)
            if chassis_def and new_weapon:
                # Calculate weight with NEW weapon (not old weapon)
                chassis_weight = chassis_def.self_weight
                plating_weight = 0
                if chassis.equipped_plating:
                    plating = registry.get_plating(chassis.equipped_plating)
                    if plating:
                        plating_weight = plating.weight
                new_weapon_weight = new_weapon.weight

                total_weight = chassis_weight + plating_weight + new_weapon_weight
                if total_weight > chassis_def.weight_capacity:
                    return (
                        False,
                        f"This would make your bot overweight! Weight: {total_weight}/{chassis_def.weight_capacity}",
                    )

        # Unequip current weapon first (returns to inventory)
        if chassis.equipped_weapon:
            self.add_equipment("component", chassis.equipped_weapon)

        # Equip new weapon
        self.remove_equipment("component", weapon_name)
        chassis.equipped_weapon = weapon_name
        return True, f"Equipped {weapon_name}"

    def unequip_plating(self, chassis_id: str) -> tuple[bool, str]:
        """Unequip plating from a chassis (returns to inventory)"""
        chassis = self.get_chassis_by_id(chassis_id)
        if not chassis:
            return False, "Chassis not found"

        if not chassis.equipped_plating:
            return False, "No plating equipped"

        self.add_equipment("plating", chassis.equipped_plating)
        chassis.equipped_plating = None
        return True, "Plating unequipped"

    def unequip_weapon(self, chassis_id: str) -> tuple[bool, str]:
        """Unequip weapon from a chassis (returns to inventory)"""
        chassis = self.get_chassis_by_id(chassis_id)
        if not chassis:
            return False, "Chassis not found"

        if not chassis.equipped_weapon:
            return False, "No weapon equipped"

        self.add_equipment("component", chassis.equipped_weapon)
        chassis.equipped_weapon = None
        return True, "Weapon unequipped"

    # ─── INVENTORY HELPERS ──────────────────────────────────────────────────────

    def count_part(self, part_type: str, part_name: str) -> int:
        """Count how many of a specific part the player owns"""
        if part_type == "chassis":
            # Count chassis of this type
            return sum(1 for c in self.owned_chassis if c.chassis_name == part_name)
        else:
            # Count from equipment inventory
            return self.get_equipment_quantity(part_type, part_name)

    def add_part(self, part_type: str, part_name: str, quantity: int = 1) -> bool:
        """Add a part to inventory.

        Returns True if successful, False if failed (e.g., garage full for chassis).
        """
        if part_type == "chassis":
            # Each chassis is a bot - check garage limit
            for _ in range(quantity):
                if self.add_chassis(part_name) is None:
                    return False
            return True
        else:
            # Add to equipment inventory
            self.add_equipment(part_type, part_name, quantity)
            return True


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE CONTAINER
# ─────────────────────────────────────────────────────────────────────────────
class DB(ArenaBaseModel):
    """Root database model"""

    players: dict[int, PlayerData] = Field(default_factory=dict)  # user_id -> PlayerData

    def get_player(self, user_id: int) -> PlayerData:
        """Get or create player data"""
        if user_id not in self.players:
            self.players[user_id] = PlayerData()
        return self.players[user_id]


# ─────────────────────────────────────────────────────────────────────────────
# PARTS REGISTRY (Runtime lookup for all available parts)
# ─────────────────────────────────────────────────────────────────────────────
class PartsRegistry:
    """Central registry for all available parts"""

    def __init__(self):
        self._chassis: dict[str, Chassis] = {}
        self._plating: dict[str, Plating] = {}
        self._components: dict[str, Component] = {}

    def register_chassis(self, chassis: Chassis):
        self._chassis[chassis.name] = chassis

    def register_plating(self, plating: Plating):
        self._plating[plating.name] = plating

    def register_component(self, component: Component):
        self._components[component.name] = component

    def get_chassis(self, name: str) -> t.Optional[Chassis]:
        return self._chassis.get(name)

    def get_plating(self, name: str) -> t.Optional[Plating]:
        return self._plating.get(name)

    def get_component(self, name: str) -> t.Optional[Component]:
        return self._components.get(name)

    def all_chassis(self) -> list[Chassis]:
        return list(self._chassis.values())

    def all_plating(self) -> list[Plating]:
        return list(self._plating.values())

    def all_components(self) -> list[Component]:
        return list(self._components.values())

    def chassis_by_class(self, weight_class: WeightClass) -> list[Chassis]:
        return [c for c in self._chassis.values() if c.weight_class == weight_class]
