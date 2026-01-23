"""
Bot Arena - Real-Time Battle Engine

This module contains the physics simulation for real-time bot combat.
It simulates continuous movement, rotation, and combat at a fixed timestep.

Range Scaling:
    Original BA3 weapon ranges (25-220) are designed for a smaller arena scale.
    We scale these to our 1000x1000 arena using RANGE_SCALE_FACTOR.
    This ensures weapons have meaningful engagement distances.

Collision Detection:
    Uses pixel-perfect collision detection when available (numpy installed).
    Falls back to simple circular hitboxes otherwise.
"""

import math
import random
import typing as t
from dataclasses import dataclass, field
from enum import Enum

if t.TYPE_CHECKING:
    from .collision import CollisionManager

# Try to import pixel-perfect collision (requires numpy)
try:
    from .collision import CollisionManager as _CollisionManager

    HAS_PIXEL_COLLISION = True
except ImportError:
    HAS_PIXEL_COLLISION = False
    _CollisionManager = None  # type: ignore

if t.TYPE_CHECKING:
    try:
        from .models import Bot, TacticalOrders
    except ImportError:
        Bot = t.Any  # Fallback when running standalone
        TacticalOrders = t.Any

# ─────────────────────────────────────────────────────────────────────────────
# RANGE SCALING
# Original BA3 ranges were for a ~250px arena, we use 1000px
# Scale factor converts original ranges to meaningful distances
# ─────────────────────────────────────────────────────────────────────────────
RANGE_SCALE_FACTOR = 2.5  # Multiplier for weapon ranges (Smaller means shorter range)


class AIBehavior(str, Enum):
    """AI behavior modes - simplified to 3 core behaviors"""

    AGGRESSIVE = "aggressive"  # Close distance, stay in enemy's face
    DEFENSIVE = "defensive"  # Maintain max range, retreat when approached
    TACTICAL = "tactical"  # Balanced - optimal range, repositioning


class TargetPriority(str, Enum):
    """Target selection priority - simplified to 3 meaningful options"""

    FOCUS_FIRE = "focus_fire"  # Attack same target as teammates (coordinated)
    WEAKEST = "weakest"  # Target lowest HP enemy (finish kills)
    CLOSEST = "closest"  # Attack nearest enemy (reactive, default)


# Default behaviors for chassis types (used when no tactical orders given)
# Based on original Bot Arena 3 chassis characteristics
DEFAULT_CHASSIS_BEHAVIORS = {
    # Light chassis - fast and agile
    "DLZ-100": AIBehavior.TACTICAL,  # Starter chassis, good all-rounder
    "DLZ-250": AIBehavior.AGGRESSIVE,  # Upgraded light, more aggressive
    # Medium chassis - balanced
    "SmartMove": AIBehavior.TACTICAL,  # Smart AI chassis
    "CLR-Z050": AIBehavior.DEFENSIVE,  # Tanky medium
    "Electron": AIBehavior.TACTICAL,  # High-capacity medium
    # Heavy chassis - slow but tough
    "Durichas": AIBehavior.DEFENSIVE,  # Heavy tank
    "Deliverance": AIBehavior.DEFENSIVE,  # Ultimate heavy, prefers range
}


@dataclass
class Vector2:
    """2D vector for position and velocity"""

    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: "Vector2") -> "Vector2":
        return Vector2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vector2") -> "Vector2":
        return Vector2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vector2":
        return Vector2(self.x * scalar, self.y * scalar)

    def magnitude(self) -> float:
        return math.sqrt(self.x**2 + self.y**2)

    def normalized(self) -> "Vector2":
        mag = self.magnitude()
        if mag == 0:
            return Vector2(0, 0)
        return Vector2(self.x / mag, self.y / mag)

    def distance_to(self, other: "Vector2") -> float:
        return (self - other).magnitude()

    def angle_to(self, other: "Vector2") -> float:
        """Return angle in degrees from self to other (0 = right, 90 = down)"""
        dx = other.x - self.x
        dy = other.y - self.y
        return math.degrees(math.atan2(dy, dx)) % 360

    def to_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)

    def to_int_tuple(self) -> tuple[int, int]:
        return (int(self.x), int(self.y))


@dataclass
class BotRuntimeState:
    """Runtime state for a bot during real-time battle simulation"""

    bot_id: str
    bot_name: str
    team: int

    # Visual/stats data from bot
    chassis_name: str
    plating_name: str
    component_name: str
    max_health: int
    speed: float  # pixels per second
    rotation_speed: float  # degrees per second
    turret_rotation_speed: float  # degrees per second for weapon turret (separate from chassis)
    intelligence: int

    # Weapon stats (SCALED for arena - see RANGE_SCALE_FACTOR)
    damage_per_shot: int
    shots_per_second: float
    min_range: int  # Already scaled when passed in
    max_range: int  # Already scaled when passed in
    is_healer: bool
    allows_point_blank: bool = False  # If True, can hit targets even when inside min_range
    projectile_type: str = "bullet"  # Type of projectile this weapon fires
    muzzle_offset: float = 92.0  # Distance from bot center to weapon muzzle (for projectile spawn)

    # AI behavior (derived from tactical orders or chassis default)
    behavior: AIBehavior = AIBehavior.TACTICAL

    # Tactical orders from player
    target_priority: TargetPriority = TargetPriority.CLOSEST

    # Chassis agility (0.0-1.0) - how well the bot can turn while moving
    # 0.0 = must completely stop to turn, 1.0 = can turn at full speed
    agility: float = 0.5

    # Weapon archetype for movement bonuses
    weapon_archetype: str = "BRAWLER"  # BRAWLER, SKIRMISHER, RIFLE, SNIPER

    # Runtime state
    position: Vector2 = field(default_factory=Vector2)
    velocity: Vector2 = field(default_factory=Vector2)
    orientation: float = 0.0  # Chassis facing direction (degrees, 0 = right, 90 = down)
    weapon_orientation: float = 0.0  # Weapon turret facing direction (independent of chassis)
    target_orientation: float = 0.0  # Desired orientation (for stop-turn-move)
    is_turning: bool = False  # Whether the bot is currently turning before moving
    health: int = 0
    is_alive: bool = True
    last_shot_time: float = 0.0
    target_id: t.Optional[str] = None
    last_target_check: float = 0.0  # Time of last target re-evaluation (for switching targets)

    # AI state - position-based movement with commitment
    target_position: Vector2 = field(default_factory=Vector2)  # Where bot wants to be
    commitment_timer: float = 0.0  # Time remaining committed to current target_position
    dodge_timer: float = 0.0  # Cooldown until next dodge is allowed
    dodge_direction: int = 0  # Current dodge direction (0=none, 1=right, -1=left)
    dodge_duration: float = 0.0  # Time remaining in current dodge

    # Wall collision state
    wall_escape_timer: float = 0.0  # Time remaining in wall escape mode
    last_wall_contact: float = 0.0  # Time of last wall contact

    # Statistics
    damage_dealt: int = 0
    damage_taken: int = 0
    kills: int = 0

    def take_damage(self, damage: int) -> int:
        """Apply damage, return actual damage dealt"""
        actual = min(damage, self.health)
        self.health -= actual
        self.damage_taken += actual
        if self.health <= 0:
            self.health = 0
            self.is_alive = False
        return actual

    def heal(self, amount: int) -> int:
        """Heal, return actual amount healed"""
        if not self.is_alive:
            return 0
        actual = min(amount, self.max_health - self.health)
        self.health += actual
        return actual

    def can_shoot(self, current_time: float) -> bool:
        """Check if weapon is ready to fire"""
        if self.shots_per_second <= 0:
            return False
        time_between_shots = 1.0 / self.shots_per_second
        return current_time - self.last_shot_time >= time_between_shots

    def get_preferred_range(self) -> float:
        """Get the preferred engagement range based on movement stance.

        Range preferences (derived from stance - no need for separate setting):
        - AGGRESSIVE: Just outside min_range (15-20% into range band)
        - DEFENSIVE: Near max range (90-95% of max)
        - TACTICAL: Optimal midpoint (50% of range band)
        """
        if self.behavior == AIBehavior.AGGRESSIVE:
            return self.min_range + (self.max_range - self.min_range) * 0.18
        elif self.behavior == AIBehavior.DEFENSIVE:
            return self.max_range * 0.92
        else:  # TACTICAL
            return (self.min_range + self.max_range) / 2

    def to_frame_data(self) -> dict:
        """Export state for frame capture"""
        return {
            "id": self.bot_id,
            "name": self.bot_name,
            "team": self.team,
            "chassis": self.chassis_name,
            "plating": self.plating_name,
            "component": self.component_name,
            "x": self.position.x,
            "y": self.position.y,
            "orientation": self.orientation,
            "weapon_orientation": self.weapon_orientation,
            "health": self.health,
            "max_health": self.max_health,
            "is_alive": self.is_alive,
            "target_id": self.target_id,
            "is_turning": self.is_turning,
        }


@dataclass
class Projectile:
    """A projectile in flight"""

    shooter_id: str
    target_id: str
    position: Vector2
    velocity: Vector2
    damage: int
    is_heal: bool = False
    alive: bool = True
    projectile_type: str = "bullet"  # Type of projectile for rendering
    ttl: float = -1.0  # Time-to-live in seconds (-1 = infinite, expires when <= 0)

    def to_frame_data(self) -> dict:
        return {
            "shooter_id": self.shooter_id,
            "target_id": self.target_id,
            "x": self.position.x,
            "y": self.position.y,
            "vx": self.velocity.x,
            "vy": self.velocity.y,
            "damage": self.damage,
            "is_heal": self.is_heal,
            "projectile_type": self.projectile_type,
        }


@dataclass
class FrameData:
    """A single frame of battle state for rendering"""

    frame_number: int
    time: float
    bots: list[dict]
    projectiles: list[dict]
    events: list[dict]  # hits, kills, etc.


@dataclass
class BattleConfig:
    """Configuration for a battle simulation"""

    arena_width: int = 1000
    arena_height: int = 1000
    fps: int = 30
    max_duration: float = 120.0  # seconds
    projectile_speed: float = 500.0  # pixels per second
    bot_radius: float = 32.0  # collision radius


class BattleEngine:
    """
    Real-time battle simulation engine.

    Runs a physics-based simulation with continuous movement and combat.
    All times are in seconds, positions in pixels.
    """

    def __init__(self, config: BattleConfig = None):
        self.config = config or BattleConfig()
        self.bots: dict[str, BotRuntimeState] = {}
        self.projectiles: list[Projectile] = []
        self.frames: list[FrameData] = []
        self.current_time: float = 0.0
        self.frame_number: int = 0
        self.dt: float = 1.0 / self.config.fps
        self.events: list[dict] = []  # Events for current frame

        self.last_damage_time: float = 0.0  # For battle statistics

        # Wall collision constants
        self.wall_margin: float = 50.0  # Distance from edge to consider "against wall"
        self.wall_escape_duration: float = 0.5  # How long to stay in escape mode after wall contact

        # Pixel-perfect collision detection (when numpy is available)
        self.collision_manager: t.Optional["CollisionManager"] = None
        if HAS_PIXEL_COLLISION and _CollisionManager is not None:
            self.collision_manager = _CollisionManager()

    def add_bot(
        self,
        bot_id: str,
        bot_name: str,
        team: int,
        chassis_name: str,
        plating_name: str,
        component_name: str,
        max_health: int,
        speed: float,
        rotation_speed: float,
        intelligence: int,
        damage_per_shot: int,
        shots_per_minute: float,
        min_range: int,
        max_range: int,
        is_healer: bool,
        agility: float = 0.5,
        behavior: t.Optional[AIBehavior] = None,
        target_priority: t.Optional[TargetPriority] = None,
        projectile_type: str = "bullet",
        muzzle_offset: float = 50.0,
        turret_rotation_speed: float = 15.0,
    ):
        """Add a bot to the simulation.

        Args:
            min_range: Minimum weapon range (will be scaled by RANGE_SCALE_FACTOR)
            max_range: Maximum weapon range (will be scaled by RANGE_SCALE_FACTOR)
            behavior: AI movement behavior (from tactical orders or chassis default)
            target_priority: Who to target (from tactical orders)
            projectile_type: Visual type of projectile (bullet, laser, cannon, missile, heal)
            muzzle_offset: Distance from bot center to weapon muzzle (for projectile spawn point)
        """
        shots_per_second = shots_per_minute / 60.0

        # Apply range scaling - original BA3 ranges are for smaller arena
        scaled_min_range = int(min_range * RANGE_SCALE_FACTOR)
        scaled_max_range = int(max_range * RANGE_SCALE_FACTOR)

        # Ensure minimum range is at least bot collision diameter + buffer
        min_collision_buffer = int(self.config.bot_radius * 2.5)
        scaled_min_range = max(scaled_min_range, min_collision_buffer)

        # Track if weapon originally had min_range=0 (allows point-blank shooting)
        allows_point_blank = min_range == 0

        # Determine weapon archetype based on ranges for movement modifiers
        # BRAWLER: Close range specialist (min≤30, max≤150)
        # SKIRMISHER: Versatile close-to-mid fighter (min≤30, max>150)
        # RIFLE: Mid-range fighter (min>30, max<180)
        # SNIPER: Long-range specialist (min>30, max≥180)
        if min_range > 30:
            if max_range >= 180:
                weapon_archetype = "SNIPER"
            else:
                weapon_archetype = "RIFLE"
        elif max_range > 150:
            weapon_archetype = "SKIRMISHER"
        else:
            weapon_archetype = "BRAWLER"

        # Determine behavior - use provided, or chassis default, or fallback to TACTICAL
        if behavior is None:
            behavior = DEFAULT_CHASSIS_BEHAVIORS.get(chassis_name, AIBehavior.TACTICAL)

        state = BotRuntimeState(
            bot_id=bot_id,
            bot_name=bot_name,
            team=team,
            chassis_name=chassis_name,
            plating_name=plating_name,
            component_name=component_name,
            max_health=max_health,
            speed=speed,
            rotation_speed=rotation_speed,
            turret_rotation_speed=turret_rotation_speed,
            intelligence=intelligence,
            damage_per_shot=damage_per_shot,
            shots_per_second=shots_per_second,
            min_range=scaled_min_range,
            max_range=scaled_max_range,
            is_healer=is_healer,
            allows_point_blank=allows_point_blank,
            projectile_type=projectile_type,
            muzzle_offset=muzzle_offset,
            health=max_health,
            behavior=behavior,
            target_priority=target_priority or TargetPriority.CLOSEST,
            agility=max(0.0, min(1.0, agility)),  # Clamp to 0-1
            weapon_archetype=weapon_archetype,
            commitment_timer=0.0,
            dodge_timer=random.uniform(0.5, 2.0),  # Stagger initial dodge timers
        )
        self.bots[bot_id] = state

        # Register collision mask for pixel-perfect collision detection
        # Uses plating + weapon to match visual rendering
        if self.collision_manager is not None:
            self.collision_manager.register_bot(bot_id, plating_name, component_name)

    def setup_positions(self):
        """Place bots in starting positions"""
        team1 = [b for b in self.bots.values() if b.team == 1]
        team2 = [b for b in self.bots.values() if b.team == 2]

        arena_buffer = 40.0
        spawn_y_offset = 80 + arena_buffer

        # Team 1 starts at top, facing down
        if team1:
            spacing = self.config.arena_width / (len(team1) + 1)
            for i, bot in enumerate(team1):
                bot.position = Vector2((i + 1) * spacing, spawn_y_offset)
                bot.orientation = 90
                bot.weapon_orientation = 90
                bot.target_orientation = 90

        # Team 2 starts at bottom, facing up
        if team2:
            spacing = self.config.arena_width / (len(team2) + 1)
            for i, bot in enumerate(team2):
                bot.position = Vector2((i + 1) * spacing, self.config.arena_height - spawn_y_offset)
                bot.orientation = 270
                bot.weapon_orientation = 270
                bot.target_orientation = 270

    def run(self) -> dict:
        """
        Run the complete battle simulation.

        Returns a dict with battle results and frame data.
        """
        self.setup_positions()
        self.current_time = 0.0
        self.frame_number = 0

        max_frames = int(self.config.max_duration * self.config.fps)

        while self.frame_number < max_frames:
            self.events = []

            # Update all systems
            self._update_ai()
            self._update_movement()
            self._separate_overlapping_bots()  # Push apart any bots that got stuck together
            self._update_weapon_orientation()
            self._update_projectiles()
            self._update_combat()

            # Capture frame
            self._capture_frame()

            # Check for battle end
            if self._check_battle_end():
                break

            self.current_time += self.dt
            self.frame_number += 1

        return self._build_result()

    def _update_ai(self):
        """Update bot AI - target selection and decision making"""
        for bot in self.bots.values():
            if not bot.is_alive:
                continue

            # Target re-evaluation: check every 2 seconds if current target is still optimal
            # If a closer, in-range enemy appears, switch targets
            time_since_target_check = self.current_time - bot.last_target_check
            should_reevaluate = time_since_target_check >= 2.0

            if should_reevaluate or not bot.target_id:
                bot.target_id = self._find_best_target(bot)
                bot.last_target_check = self.current_time
            elif bot.target_id:
                # Verify current target is still valid
                current_target = self.bots.get(bot.target_id)
                if not current_target or not current_target.is_alive:
                    bot.target_id = self._find_best_target(bot)
                    bot.last_target_check = self.current_time

    def _find_best_target(self, bot: BotRuntimeState) -> t.Optional[str]:
        """Find the best target for this bot based on tactical orders"""
        candidates = []

        for other in self.bots.values():
            if other.bot_id == bot.bot_id:
                continue
            if not other.is_alive:
                continue

            # Healers target friendly, weapons target enemy
            if bot.is_healer:
                if other.team != bot.team:
                    continue
                # Don't heal full health bots
                if other.health >= other.max_health:
                    continue
                candidates.append(other)
            else:
                if other.team == bot.team:
                    continue
                # Only consider enemies within reasonable approach distance
                # max_range * 2.0 allows bots to pursue enemies but prevents chasing unreachable targets
                distance = bot.position.distance_to(other.position)
                max_approach_distance = bot.max_range * 2.0
                if distance <= max_approach_distance:
                    candidates.append(other)

        if not candidates:
            return None

        # FOCUS_FIRE: Find what teammates are targeting and prioritize that
        if bot.target_priority == TargetPriority.FOCUS_FIRE:
            # Count how many teammates are targeting each enemy
            target_counts: dict[str, int] = {}
            for ally in self.bots.values():
                if ally.team == bot.team and ally.bot_id != bot.bot_id and ally.is_alive:
                    if ally.target_id and ally.target_id in [c.bot_id for c in candidates]:
                        target_counts[ally.target_id] = target_counts.get(ally.target_id, 0) + 1

            if target_counts:
                # Target what most allies are targeting
                best_target_id = max(target_counts, key=target_counts.get)
                return best_target_id
            # Fall through to WEAKEST if no allies have targets
            return self._select_by_priority(bot, candidates, TargetPriority.WEAKEST)

        return self._select_by_priority(bot, candidates, bot.target_priority)

    def _select_by_priority(
        self, bot: BotRuntimeState, candidates: list[BotRuntimeState], priority: TargetPriority
    ) -> t.Optional[str]:
        """Select target from candidates based on priority (3 options)"""
        if not candidates:
            return None

        if priority == TargetPriority.WEAKEST:
            # Sort by health (lowest first), with intelligence-based noise
            def score(c: BotRuntimeState) -> float:
                noise = random.uniform(0, 20) * (10 - bot.intelligence) / 10
                return c.health + noise

            target = min(candidates, key=score)

        else:  # CLOSEST (default) or FOCUS_FIRE fallback
            # Sort by distance (closest first), with noise
            def score(c: BotRuntimeState) -> float:
                dist = bot.position.distance_to(c.position)
                noise = random.uniform(0, 50) * (10 - bot.intelligence) / 10
                return dist + noise

            target = min(candidates, key=score)

        return target.bot_id

    def _update_weapon_orientation(self):
        """Update weapon turret to track target independently of chassis"""
        for bot in self.bots.values():
            if not bot.is_alive:
                continue

            if not bot.target_id or bot.target_id not in self.bots:
                # No target - weapon follows chassis
                self._rotate_weapon_towards(bot, bot.orientation)
                continue

            target = self.bots[bot.target_id]
            if not target.is_alive:
                self._rotate_weapon_towards(bot, bot.orientation)
                continue

            # Weapon tracks target independently
            target_angle = bot.position.angle_to(target.position)
            self._rotate_weapon_towards(bot, target_angle)

    def _rotate_weapon_towards(self, bot: BotRuntimeState, target_angle: float):
        """Rotate weapon turret towards target angle (faster than chassis).

        Weapons track independently and faster than the chassis moves.
        This lets bots fire while maneuvering.
        """
        angle_diff = (target_angle - bot.weapon_orientation + 360) % 360
        if angle_diff > 180:
            angle_diff -= 360
        # Use dedicated turret rotation speed (separate from chassis rotation)
        effective_rotation = bot.turret_rotation_speed

        max_rotation = effective_rotation * self.dt
        if abs(angle_diff) <= max_rotation:
            bot.weapon_orientation = target_angle
        elif angle_diff > 0:
            bot.weapon_orientation = (bot.weapon_orientation + max_rotation) % 360
        else:
            bot.weapon_orientation = (bot.weapon_orientation - max_rotation) % 360

    def _update_movement(self):
        """Update bot movement using position-based commitment system.

        Core design:
        1. Calculate a TARGET POSITION based on behavior
        2. COMMIT to that position for 1-2 seconds
        3. Move toward target position at full speed
        4. Periodic DODGE impulses for evasion
        """
        for bot in self.bots.values():
            if not bot.is_alive:
                continue

            # Update timers
            if bot.commitment_timer > 0:
                bot.commitment_timer -= self.dt
            if bot.dodge_timer > 0:
                bot.dodge_timer -= self.dt
            if bot.dodge_duration > 0:
                bot.dodge_duration -= self.dt

            # No target - wander toward center
            if not bot.target_id or bot.target_id not in self.bots:
                self._wander_movement(bot)
                continue

            target = self.bots[bot.target_id]
            if not target.is_alive:
                self._wander_movement(bot)
                continue

            # Healers use special ally-following logic regardless of stance setting
            if bot.is_healer:
                self._protector_movement(bot, target)
                continue

            # Calculate and commit to target position
            if bot.commitment_timer <= 0:
                bot.target_position = self._calculate_target_position(bot, target)
                bot.commitment_timer = random.uniform(1.0, 2.0)

            # Check for dodge opportunity
            self._maybe_dodge(bot, target)

            # Execute movement toward target position
            self._move_toward_position(bot, target)

    def _calculate_target_position(self, bot: BotRuntimeState, target: BotRuntimeState) -> Vector2:
        """Calculate where this bot wants to be based on its behavior.

        Position-based system - no angles, just "where do I want to stand?"

        AGGRESSIVE: Position just outside min_range, directly toward target
        DEFENSIVE: Position at max_range, directly away from target
        TACTICAL: Position at optimal range, with some lateral offset
        """
        preferred_range = bot.get_preferred_range()

        # Direction from bot to target
        dx = target.position.x - bot.position.x
        dy = target.position.y - bot.position.y
        dist = max(1.0, math.sqrt(dx * dx + dy * dy))
        dir_x = dx / dist
        dir_y = dy / dist

        # Calculate ideal distance based on behavior
        if bot.behavior == AIBehavior.AGGRESSIVE:
            # Want to be just outside min_range
            ideal_distance = bot.min_range * 1.15 if bot.min_range > 0 else preferred_range
        elif bot.behavior == AIBehavior.DEFENSIVE:
            # Want to be at max range
            ideal_distance = bot.max_range * 0.92
        else:  # TACTICAL
            # Want to be at optimal range
            ideal_distance = preferred_range

        # Target position is along the line to enemy at ideal distance
        target_x = target.position.x - dir_x * ideal_distance
        target_y = target.position.y - dir_y * ideal_distance

        # Add small random offset for TACTICAL to create repositioning
        if bot.behavior == AIBehavior.TACTICAL:
            perpendicular_x = -dir_y
            perpendicular_y = dir_x
            offset = random.uniform(-50, 50)
            target_x += perpendicular_x * offset
            target_y += perpendicular_y * offset

        # Clamp to arena bounds
        margin = 60.0
        target_x = max(margin, min(self.config.arena_width - margin, target_x))
        target_y = max(margin, min(self.config.arena_height - margin, target_y))

        return Vector2(target_x, target_y)

    def _maybe_dodge(self, bot: BotRuntimeState, target: BotRuntimeState):
        """Check if bot should initiate a dodge maneuver.

        Dodges are quick perpendicular bursts that provide evasion
        without the infinite orbit problem of continuous strafing.
        """
        # Currently in a dodge - let it play out
        if bot.dodge_duration > 0:
            return

        # Dodge on cooldown
        if bot.dodge_timer > 0:
            return

        # Random chance to dodge (intelligence affects frequency)
        dodge_chance = 0.02 + (bot.intelligence / 100.0) * 0.03  # 2-5% per frame
        if random.random() > dodge_chance:
            return

        # Initiate dodge!
        bot.dodge_direction = random.choice([-1, 1])
        bot.dodge_duration = 0.25  # 250ms dodge
        bot.dodge_timer = random.uniform(1.0, 3.0)  # Cooldown before next dodge

    def _move_toward_position(self, bot: BotRuntimeState, target: BotRuntimeState):
        """Move bot toward its target_position, handling dodges and walls."""
        # Calculate direction to target position
        dx = bot.target_position.x - bot.position.x
        dy = bot.target_position.y - bot.position.y
        distance_to_target = math.sqrt(dx * dx + dy * dy)

        if distance_to_target < 5.0:
            # Close enough - just face the enemy
            enemy_angle = bot.position.angle_to(target.position)
            self._rotate_chassis_towards(bot, enemy_angle)
            return

        # Normalize direction
        dir_x = dx / distance_to_target
        dir_y = dy / distance_to_target

        # Apply dodge if active
        if bot.dodge_duration > 0:
            # Perpendicular dodge
            perpendicular_x = -dir_y * bot.dodge_direction
            perpendicular_y = dir_x * bot.dodge_direction
            # Blend dodge with movement (70% dodge, 30% forward)
            dir_x = dir_x * 0.3 + perpendicular_x * 0.7
            dir_y = dir_y * 0.3 + perpendicular_y * 0.7
            # Renormalize
            mag = math.sqrt(dir_x * dir_x + dir_y * dir_y)
            dir_x /= mag
            dir_y /= mag

        # Calculate desired movement angle
        desired_angle = math.degrees(math.atan2(dir_y, dir_x)) % 360

        # Calculate speed based on angle difference and agility
        angle_diff = abs((desired_angle - bot.orientation + 180) % 360 - 180)
        angle_penalty = min(1.0, angle_diff / 90.0)
        speed_mult = 1.0 - angle_penalty * (1.0 - bot.agility)

        # Minimum speed to prevent shuffling
        speed_mult = max(0.3, speed_mult)

        # Rotate chassis toward movement direction
        self._rotate_chassis_towards(bot, desired_angle)

        # Apply movement
        move_vec = Vector2(
            math.cos(math.radians(bot.orientation)) * bot.speed * speed_mult * self.dt,
            math.sin(math.radians(bot.orientation)) * bot.speed * speed_mult * self.dt,
        )
        self._apply_movement(bot, move_vec)

    def _wander_movement(self, bot: BotRuntimeState):
        """Wander toward arena center when no target"""
        center_x = self.config.arena_width / 2
        center_y = self.config.arena_height / 2

        # Add some randomness
        target_x = center_x + random.uniform(-100, 100)
        target_y = center_y + random.uniform(-100, 100)

        dx = target_x - bot.position.x
        dy = target_y - bot.position.y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < 50:
            # Near center, just rotate randomly
            bot.target_orientation = (bot.orientation + random.uniform(-30, 30)) % 360
            self._rotate_chassis_towards(bot, bot.target_orientation)
            return

        # Move toward center
        desired_angle = math.degrees(math.atan2(dy, dx)) % 360
        self._rotate_chassis_towards(bot, desired_angle)

        rad = math.radians(bot.orientation)
        move_vec = Vector2(math.cos(rad), math.sin(rad)) * (bot.speed * 0.5 * self.dt)
        self._apply_movement(bot, move_vec)

    def _find_lowest_health_ally(self, bot: BotRuntimeState) -> t.Optional[BotRuntimeState]:
        """Find the ally with the lowest health percentage (excluding self).

        Returns None if no valid ally is found.
        Always returns an ally if one exists (even at full health) to support protector behavior.
        """
        lowest_ally: t.Optional[BotRuntimeState] = None
        lowest_health_pct: float = float("inf")  # Start high so ANY ally will be selected

        for other in self.bots.values():
            if other.bot_id == bot.bot_id:
                continue
            if not other.is_alive:
                continue
            if other.team != bot.team:
                continue

            health_pct = other.health / other.max_health if other.max_health > 0 else 1.0
            if health_pct < lowest_health_pct:
                lowest_health_pct = health_pct
                lowest_ally = other

        return lowest_ally

    def _find_nearest_enemy(self, bot: BotRuntimeState) -> t.Optional[BotRuntimeState]:
        """Find the nearest enemy to this bot."""
        nearest_enemy: t.Optional[BotRuntimeState] = None
        nearest_dist: float = float("inf")

        for other in self.bots.values():
            if other.bot_id == bot.bot_id:
                continue
            if not other.is_alive:
                continue
            if other.team == bot.team:
                continue

            dist = bot.position.distance_to(other.position)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_enemy = other

        return nearest_enemy

    def _protector_movement(self, bot: BotRuntimeState, target: BotRuntimeState):
        """
        PROTECTOR movement - stay CLOSE to lowest-health ally and position BEHIND them.

        Ideal for healer bots. The protector:
        1. Finds the ally with the lowest health percentage
        2. Stays VERY close to that ally (tight follow distance)
        3. Positions so the ally is BETWEEN them and enemies (hides behind ally)
        4. Follows ally movement CLOSELY - mirrors their movement
        5. Prioritizes ally survival over self-preservation

        Key behavior differences:
        - MUCH closer follow distance than other behaviors
        - Aggressive repositioning to stay behind ally
        - High speed to keep up with ally movement
        - Doesn't care about enemy range, only ally position
        """
        # Find the ally to protect (lowest health)
        ally_to_protect = self._find_lowest_health_ally(bot)

        if not ally_to_protect:
            # No ally to protect - wander toward center
            self._wander_movement(bot)
            return

        # Find nearest enemy for positioning calculations
        nearest_enemy = self._find_nearest_enemy(bot)

        # Calculate desired position: BEHIND ally relative to enemy
        ally_pos = ally_to_protect.position
        bot_to_ally_dist = bot.position.distance_to(ally_pos)

        # TIGHT follow distance - stay very close to ally!
        # Use 40-60 pixels ideally, never more than 50% of healing range
        ideal_ally_distance = min(55, max(bot.min_range * 0.5, 40))
        max_ally_distance = min(bot.max_range * 0.4, 150)  # MUCH tighter max distance

        if nearest_enemy:
            enemy_pos = nearest_enemy.position
            # Vector from enemy to ally
            enemy_to_ally = ally_pos - enemy_pos
            enemy_to_ally_dist = enemy_to_ally.magnitude()

            if enemy_to_ally_dist > 0:
                # Normalize and scale to get position DIRECTLY behind ally
                direction = enemy_to_ally.normalized()
                # Target position is behind ally (on the opposite side from enemy)
                # Position closer to ally than before
                target_pos = ally_pos + direction * ideal_ally_distance
            else:
                # Enemy and ally at same position (rare), just stay near ally
                target_pos = ally_pos
        else:
            # No enemy visible - stay directly behind ally based on ally's facing
            rad = math.radians(ally_to_protect.orientation + 180)
            target_pos = ally_pos + Vector2(math.cos(rad), math.sin(rad)) * ideal_ally_distance

        # Calculate movement direction to reach target position
        to_target = target_pos - bot.position
        target_distance = to_target.magnitude()

        if target_distance < 10:  # Slightly larger tolerance
            # Already at target position - face threats but stay ready to move
            if nearest_enemy:
                target_angle = bot.position.angle_to(nearest_enemy.position)
            else:
                target_angle = bot.position.angle_to(ally_pos)
            # Small random offset to not be a sitting duck
            jitter_angle = (target_angle + random.uniform(-15, 15)) % 360
            self._rotate_chassis_towards(bot, jitter_angle, speed_mult=0.3)
            bot.is_turning = False

            # Tiny movement to avoid being stationary
            rad = math.radians(bot.orientation)
            move_vec = Vector2(math.cos(rad), math.sin(rad)) * (bot.speed * 0.1 * self.dt)
            self._apply_movement(bot, move_vec)
            return

        # Move toward target position - URGENCY based on distance from ally
        desired_angle = bot.position.angle_to(target_pos)

        # Speed depends on urgency - HIGHER speeds than before for tight following
        if bot_to_ally_dist > max_ally_distance:
            # WAY too far from ally - SPRINT to catch up!
            speed_mult = 1.0
        elif bot_to_ally_dist > ideal_ally_distance * 2:
            # Getting too far - fast catch up
            speed_mult = 0.95
        elif target_distance > ideal_ally_distance:
            # Need to reposition to get behind ally
            speed_mult = 0.85
        elif target_distance > 30:
            # Close but adjusting
            speed_mult = 0.7
        else:
            # Fine tuning position
            speed_mult = 0.5

        # Execute agile movement towards calculated position
        bot.target_orientation = desired_angle

        angle_diff = abs((desired_angle - bot.orientation + 180) % 360 - 180)
        angle_penalty = min(1.0, angle_diff / 90.0)
        effective_speed_mult = speed_mult * (1.0 - angle_penalty * (1.0 - bot.agility))

        # Higher minimum speed for protectors - they need to keep up
        if angle_diff < 120:
            effective_speed_mult = max(0.35, effective_speed_mult)

        bot.is_turning = angle_diff > 25  # More tolerant of angle differences

        # Rotate toward target - faster rotation for protectors
        turn_speed_mult = 1.2 + (1.0 - effective_speed_mult) * 0.5
        self._rotate_chassis_towards(bot, desired_angle, speed_mult=turn_speed_mult)

        # Move
        rad = math.radians(bot.orientation)
        move_vec = Vector2(math.cos(rad), math.sin(rad)) * (bot.speed * effective_speed_mult * self.dt)
        self._apply_movement(bot, move_vec)

    def _rotate_chassis_towards(self, bot: BotRuntimeState, target_angle: float, speed_mult: float = 1.0):
        """Rotate chassis towards target angle.

        All bots get a base rotation speed boost to make tactical orders responsive.
        This ensures even slow heavy chassis can react to tactical situations.
        """
        angle_diff = (target_angle - bot.orientation + 360) % 360
        if angle_diff > 180:
            angle_diff -= 360

        # Base rotation boost - makes all bots more responsive to tactical orders
        # Original rotation_speed ranges from 3-12 deg/frame, which is too slow
        # Add a flat boost so even heavy tanks can respond to threats
        base_rotation_boost = 4.0  # degrees per second bonus for all bots
        effective_rotation = bot.rotation_speed + base_rotation_boost

        max_rotation = effective_rotation * self.dt * speed_mult
        if abs(angle_diff) <= max_rotation:
            bot.orientation = target_angle
        elif angle_diff > 0:
            bot.orientation = (bot.orientation + max_rotation) % 360
        else:
            bot.orientation = (bot.orientation - max_rotation) % 360

    def _rotate_towards(self, bot: BotRuntimeState, target_angle: float, speed_mult: float = 1.0):
        """Deprecated - use _rotate_chassis_towards instead"""
        self._rotate_chassis_towards(bot, target_angle, speed_mult)

    def _is_against_wall(self, bot: BotRuntimeState) -> tuple[bool, list[str]]:
        """
        Check if bot is against a wall.

        Returns:
            (is_against_wall, list of wall sides hit: 'left', 'right', 'top', 'bottom')
        """
        x, y = bot.position.x, bot.position.y
        walls_hit: list[str] = []

        # Arena edge buffer - matches the buffer in _apply_movement
        # Reduced from 40 to 25 to minimize oscillation (total buffer becomes 75px instead of 90px)
        arena_buffer = 25.0

        if x <= self.wall_margin + arena_buffer:
            walls_hit.append("left")
        elif x >= self.config.arena_width - self.wall_margin - arena_buffer:
            walls_hit.append("right")
        if y <= self.wall_margin + arena_buffer:
            walls_hit.append("top")
        elif y >= self.config.arena_height - self.wall_margin - arena_buffer:
            walls_hit.append("bottom")

        return len(walls_hit) > 0, walls_hit

    def _get_wall_escape_vector(self, bot: BotRuntimeState, walls_hit: list[str]) -> tuple[float, float]:
        """
        Calculate the escape direction and speed multiplier when against a wall.

        Returns:
            (escape_angle, speed_multiplier)
        """
        escape_x = 0.0
        escape_y = 0.0

        # Build escape vector pointing away from walls
        for wall in walls_hit:
            if wall == "left":
                escape_x += 1.0  # Move right
            elif wall == "right":
                escape_x -= 1.0  # Move left
            elif wall == "top":
                escape_y += 1.0  # Move down
            elif wall == "bottom":
                escape_y -= 1.0  # Move up

        # Calculate escape angle
        if escape_x == 0 and escape_y == 0:
            return 0.0, 0.0

        escape_angle = math.degrees(math.atan2(escape_y, escape_x)) % 360
        return escape_angle, 0.85  # High speed to escape quickly

    def _is_moving_towards_wall(self, bot: BotRuntimeState, desired_angle: float, walls_hit: list[str]) -> bool:
        """
        Check if the bot's desired movement direction would move it further into a wall.
        """
        rad = math.radians(desired_angle)
        move_x = math.cos(rad)
        move_y = math.sin(rad)

        for wall in walls_hit:
            if wall == "left" and move_x < -0.3:  # Moving left into left wall
                return True
            elif wall == "right" and move_x > 0.3:  # Moving right into right wall
                return True
            elif wall == "top" and move_y < -0.3:  # Moving up into top wall
                return True
            elif wall == "bottom" and move_y > 0.3:  # Moving down into bottom wall
                return True

        return False

    def _apply_movement(self, bot: BotRuntimeState, move_vec: Vector2):
        """Apply movement vector with bounds, collision checking, and wall response"""
        new_pos = bot.position + move_vec

        # Track if we hit a wall boundary
        hit_wall = False

        # Arena edge buffer - keeps bots away from the visual walls of the arena
        # The arena background has visible walls, so bots shouldn't clip into them
        arena_buffer = 40.0  # Pixels from edge where bots can't go

        # Bounds checking with wall hit detection (using buffer zone)
        min_bound = self.config.bot_radius + arena_buffer
        max_x = self.config.arena_width - self.config.bot_radius - arena_buffer
        max_y = self.config.arena_height - self.config.bot_radius - arena_buffer

        if new_pos.x < min_bound:
            new_pos.x = min_bound
            hit_wall = True
        elif new_pos.x > max_x:
            new_pos.x = max_x
            hit_wall = True

        if new_pos.y < min_bound:
            new_pos.y = min_bound
            hit_wall = True
        elif new_pos.y > max_y:
            new_pos.y = max_y
            hit_wall = True

        # If we hit a wall, trigger escape mode
        if hit_wall:
            bot.wall_escape_timer = self.wall_escape_duration
            bot.last_wall_contact = self.current_time

        # Collision checking - but ALLOW movement that separates overlapping bots
        min_separation = self.config.bot_radius * 2.2
        for other in self.bots.values():
            if other.bot_id != bot.bot_id and other.is_alive:
                current_dist = bot.position.distance_to(other.position)
                new_dist = new_pos.distance_to(other.position)

                # If we're already overlapping, only allow movement that increases distance
                if current_dist < min_separation:
                    if new_dist <= current_dist:
                        return  # Movement would make overlap worse or same, reject
                    # Movement increases distance - allow it even if still overlapping
                elif new_dist < min_separation:
                    return  # Would create new overlap, reject

        bot.position = new_pos

    def _separate_overlapping_bots(self):
        """Push apart any bots that are overlapping.

        This prevents the "melee blob" problem where bots get stuck
        in a clump and can't escape because movement is blocked.
        """
        min_separation = self.config.bot_radius * 2.2
        separation_force = 8.0  # Pixels per frame to push apart
        arena_buffer = 40.0

        # Check all pairs of bots for overlap
        bot_list = [b for b in self.bots.values() if b.is_alive]

        for i, bot_a in enumerate(bot_list):
            for bot_b in bot_list[i + 1 :]:
                dist = bot_a.position.distance_to(bot_b.position)

                if dist < min_separation and dist > 0.1:
                    # Calculate push direction (away from each other)
                    dx = bot_b.position.x - bot_a.position.x
                    dy = bot_b.position.y - bot_a.position.y

                    # Normalize
                    dx /= dist
                    dy /= dist

                    # Calculate overlap amount
                    overlap = min_separation - dist
                    push = min(overlap * 0.5, separation_force)

                    # Push both bots apart equally
                    new_a_x = bot_a.position.x - dx * push
                    new_a_y = bot_a.position.y - dy * push
                    new_b_x = bot_b.position.x + dx * push
                    new_b_y = bot_b.position.y + dy * push

                    # Clamp to arena bounds
                    min_bound = self.config.bot_radius + arena_buffer
                    max_x = self.config.arena_width - self.config.bot_radius - arena_buffer
                    max_y = self.config.arena_height - self.config.bot_radius - arena_buffer

                    bot_a.position.x = max(min_bound, min(max_x, new_a_x))
                    bot_a.position.y = max(min_bound, min(max_y, new_a_y))
                    bot_b.position.x = max(min_bound, min(max_x, new_b_x))
                    bot_b.position.y = max(min_bound, min(max_y, new_b_y))

    def _friendly_in_line_of_fire(self, shooter: BotRuntimeState, target: BotRuntimeState) -> bool:
        """Check if any friendly bot is between shooter and target.

        Uses a simple line-circle intersection test to see if the projectile
        path would pass through a teammate.

        Args:
            shooter: The bot that wants to fire
            target: The intended target

        Returns:
            True if a friendly is blocking the shot, False if clear to fire
        """
        # Check each bot on the same team (excluding shooter)
        for bot in self.bots.values():
            if not bot.is_alive:
                continue
            if bot.bot_id == shooter.bot_id:
                continue
            if bot.team != shooter.team:
                continue  # Only check friendlies

            # Check if this friendly is between shooter and target
            # Using point-to-line-segment distance
            shooter_pos = shooter.position
            target_pos = target.position
            friendly_pos = bot.position

            # Vector from shooter to target
            dx = target_pos.x - shooter_pos.x
            dy = target_pos.y - shooter_pos.y
            line_len_sq = dx * dx + dy * dy

            if line_len_sq == 0:
                continue  # Shooter and target at same position

            # Calculate how far along the line the closest point to friendly is
            t = max(
                0, min(1, ((friendly_pos.x - shooter_pos.x) * dx + (friendly_pos.y - shooter_pos.y) * dy) / line_len_sq)
            )

            # Find the closest point on the line segment
            closest_x = shooter_pos.x + t * dx
            closest_y = shooter_pos.y + t * dy

            # Distance from friendly to the closest point on the shot path
            dist_sq = (friendly_pos.x - closest_x) ** 2 + (friendly_pos.y - closest_y) ** 2

            # If friendly is close to the line of fire, don't shoot
            # Use bot_radius with some margin for safety
            blocking_radius = self.config.bot_radius * 1.2
            if dist_sq < blocking_radius * blocking_radius:
                # Also verify the friendly is actually BETWEEN shooter and target (not behind)
                dist_to_friendly = shooter_pos.distance_to(friendly_pos)
                dist_to_target = shooter_pos.distance_to(target_pos)
                if dist_to_friendly < dist_to_target:
                    return True  # Friendly is blocking!

        return False  # Clear to fire

    def _update_projectiles(self):
        """Update projectile positions and check for hits"""
        for proj in self.projectiles:
            if not proj.alive:
                continue

            # Check TTL expiration
            if proj.ttl > 0:
                proj.ttl -= self.dt
                if proj.ttl <= 0:
                    proj.alive = False
                    continue

            # Move projectile
            proj.position = proj.position + proj.velocity * self.dt

            # Check for collision with ANY bot (including teammates blocking shots)
            hit_bot = None
            for bot in self.bots.values():
                if not bot.is_alive:
                    continue
                # Skip the shooter - can't hit yourself
                if bot.bot_id == proj.shooter_id:
                    continue

                # Check collision - use pixel-perfect if available, otherwise circular hitbox
                collision = False
                if self.collision_manager is not None:
                    # Pixel-perfect collision: check if projectile hits non-transparent pixel
                    collision = self.collision_manager.check_collision(
                        proj.position.x,
                        proj.position.y,
                        bot.bot_id,
                        bot.position.x,
                        bot.position.y,
                        bot.orientation,
                    )
                else:
                    # Fallback: simple circular collision
                    collision = proj.position.distance_to(bot.position) < self.config.bot_radius

                if collision:
                    hit_bot = bot
                    break

            if hit_bot:
                # Determine if this is the intended target or a blocker
                shooter = self.bots.get(proj.shooter_id)
                is_friendly_fire = shooter and hit_bot.team == shooter.team

                if proj.is_heal:
                    # Heal projectiles only heal teammates (intended or not)
                    if is_friendly_fire or hit_bot.bot_id == proj.target_id:
                        actual = hit_bot.heal(abs(proj.damage))
                        if proj.shooter_id in self.bots:
                            self.bots[proj.shooter_id].damage_dealt += actual
                        self.events.append(
                            {
                                "type": "heal",
                                "shooter_id": proj.shooter_id,
                                "target_id": hit_bot.bot_id,
                                "amount": actual,
                            }
                        )
                        proj.alive = False
                    # Heal projectiles pass through enemies
                else:
                    # Damage projectiles hit ANY bot they touch (including teammates blocking)
                    if is_friendly_fire:
                        # Teammate blocked the shot - reduced friendly fire damage (25%)
                        actual = hit_bot.take_damage(proj.damage // 4)
                        self.events.append(
                            {
                                "type": "blocked",
                                "shooter_id": proj.shooter_id,
                                "blocker_id": hit_bot.bot_id,
                                "target_id": proj.target_id,
                            }
                        )
                    else:
                        # Enemy hit - full damage
                        actual = hit_bot.take_damage(proj.damage)
                        if actual > 0:
                            self.last_damage_time = self.current_time
                        if proj.shooter_id in self.bots:
                            self.bots[proj.shooter_id].damage_dealt += actual
                        self.events.append(
                            {
                                "type": "hit",
                                "shooter_id": proj.shooter_id,
                                "target_id": hit_bot.bot_id,
                                "damage": actual,
                            }
                        )

                        # Check for kill
                        if not hit_bot.is_alive:
                            if proj.shooter_id in self.bots:
                                self.bots[proj.shooter_id].kills += 1
                            self.events.append(
                                {
                                    "type": "kill",
                                    "killer_id": proj.shooter_id,
                                    "victim_id": hit_bot.bot_id,
                                }
                            )

                    proj.alive = False

            # Check if out of bounds
            if (
                proj.position.x < 0
                or proj.position.x > self.config.arena_width
                or proj.position.y < 0
                or proj.position.y > self.config.arena_height
            ):
                proj.alive = False

        # Remove dead projectiles
        self.projectiles = [p for p in self.projectiles if p.alive]

    def _update_combat(self):
        """Handle weapon firing"""
        for bot in self.bots.values():
            if not bot.is_alive:
                continue
            if not bot.target_id or bot.target_id not in self.bots:
                continue
            if not bot.can_shoot(self.current_time):
                continue

            target = self.bots[bot.target_id]
            if not target.is_alive:
                continue

            # Check range
            distance = bot.position.distance_to(target.position)
            # Weapons with min_range=0 can shoot point-blank (bypass min_range check)
            if not bot.allows_point_blank and distance < bot.min_range:
                continue
            if distance > bot.max_range:
                continue

            # Check weapon facing (must be within cone based on intelligence)
            # Use weapon_orientation, not chassis orientation
            target_angle = bot.position.angle_to(target.position)
            angle_diff = abs((target_angle - bot.weapon_orientation + 360) % 360)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff

            facing_tolerance = 10 + bot.intelligence * 3  # Higher intel = wider effective cone
            if angle_diff > facing_tolerance:
                continue

            # Check for friendly bots in line of fire (don't shoot through teammates!)
            # Skip this check for healers - they WANT to hit friendlies
            if not bot.is_healer and self._friendly_in_line_of_fire(bot, target):
                continue

            # Fire!
            bot.last_shot_time = self.current_time

            # Create projectile - fires from weapon direction
            # Projectile speed varies by type for visual effect
            projectile_speeds = {
                "laser": self.config.projectile_speed * 2.0,  # Very fast
                "cannon": self.config.projectile_speed * 0.65,  # Slower
                "missile": self.config.projectile_speed * 0.8,  # Medium-slow
                "bullet": self.config.projectile_speed,  # Default
                "heal": self.config.projectile_speed * 1.8,  # Very fast - needs to hit moving allies
                "shockwave": self.config.projectile_speed * 2.5,  # Very fast close-range burst
            }
            proj_speed = projectile_speeds.get(bot.projectile_type, self.config.projectile_speed)

            weapon_rad = math.radians(bot.weapon_orientation)
            direction = Vector2(math.cos(weapon_rad), math.sin(weapon_rad))

            # Calculate muzzle position - spawn projectile at weapon's barrel, not bot center
            # muzzle_offset is the distance from bot center along the weapon's facing direction
            muzzle_pos = Vector2(
                bot.position.x + direction.x * bot.muzzle_offset,
                bot.position.y + direction.y * bot.muzzle_offset,
            )

            # For point-blank weapons, check if target is closer than the muzzle offset
            # If so, the shot would spawn PAST the target - apply damage directly instead
            if bot.allows_point_blank and distance < bot.muzzle_offset:
                # Direct hit - no projectile needed
                if bot.is_healer:
                    actual = target.heal(abs(bot.damage_per_shot))
                    bot.damage_dealt += actual
                    self.events.append(
                        {
                            "type": "heal",
                            "shooter_id": bot.bot_id,
                            "target_id": target.bot_id,
                            "amount": actual,
                        }
                    )
                else:
                    actual = target.take_damage(bot.damage_per_shot)
                    if actual > 0:
                        self.last_damage_time = self.current_time
                    bot.damage_dealt += actual
                    self.events.append(
                        {
                            "type": "hit",
                            "shooter_id": bot.bot_id,
                            "target_id": target.bot_id,
                            "damage": actual,
                        }
                    )
                    # Check for kill
                    if not target.is_alive:
                        bot.kills += 1
                        self.events.append(
                            {
                                "type": "kill",
                                "killer_id": bot.bot_id,
                                "victim_id": target.bot_id,
                            }
                        )
                # Spawn visual shockwave at target position with zero velocity (splash effect)
                proj = Projectile(
                    shooter_id=bot.bot_id,
                    target_id=bot.target_id,
                    position=Vector2(target.position.x, target.position.y),
                    velocity=Vector2(0, 0),  # Stationary burst effect
                    damage=0,  # Damage already applied
                    is_heal=bot.is_healer,
                    projectile_type=bot.projectile_type,
                    ttl=0.15,  # Short-lived visual effect (150ms)
                )
                self.projectiles.append(proj)
            else:
                # Normal projectile
                proj = Projectile(
                    shooter_id=bot.bot_id,
                    target_id=bot.target_id,
                    position=muzzle_pos,
                    velocity=direction * proj_speed,
                    damage=abs(bot.damage_per_shot),
                    is_heal=bot.is_healer,
                    projectile_type=bot.projectile_type,
                )
                self.projectiles.append(proj)

            self.events.append(
                {
                    "type": "shot",
                    "shooter_id": bot.bot_id,
                    "target_id": target.bot_id,
                    "is_heal": bot.is_healer,
                }
            )

    def _capture_frame(self):
        """Capture current state as a frame"""
        frame = FrameData(
            frame_number=self.frame_number,
            time=self.current_time,
            bots=[bot.to_frame_data() for bot in self.bots.values()],
            projectiles=[p.to_frame_data() for p in self.projectiles],
            events=list(self.events),
        )
        self.frames.append(frame)

    def _check_battle_end(self) -> bool:
        """Check if battle should end"""
        team1_alive = any(b.is_alive for b in self.bots.values() if b.team == 1)
        team2_alive = any(b.is_alive for b in self.bots.values() if b.team == 2)
        return not (team1_alive and team2_alive)

    def _build_result(self) -> dict:
        """Build the final battle result"""
        team1_alive = any(b.is_alive for b in self.bots.values() if b.team == 1)
        team2_alive = any(b.is_alive for b in self.bots.values() if b.team == 2)

        if team1_alive and not team2_alive:
            winner = 1
        elif team2_alive and not team1_alive:
            winner = 2
        else:
            winner = 0  # Draw

        return {
            "winner_team": winner,
            "total_frames": len(self.frames),
            "duration": self.current_time,
            "fps": self.config.fps,
            "arena_width": self.config.arena_width,
            "arena_height": self.config.arena_height,
            "team1_survivors": [b.bot_id for b in self.bots.values() if b.team == 1 and b.is_alive],
            "team2_survivors": [b.bot_id for b in self.bots.values() if b.team == 2 and b.is_alive],
            "bot_stats": {
                bot_id: {
                    "name": bot.bot_name,
                    "team": bot.team,
                    "final_health": bot.health,
                    "max_health": bot.max_health,
                    "damage_dealt": bot.damage_dealt,
                    "damage_taken": bot.damage_taken,
                    "kills": bot.kills,
                    "survived": bot.is_alive,
                }
                for bot_id, bot in self.bots.items()
            },
            "frames": [
                {
                    "frame": f.frame_number,
                    "time": f.time,
                    "bots": f.bots,
                    "projectiles": f.projectiles,
                    "events": f.events,
                }
                for f in self.frames
            ],
        }
