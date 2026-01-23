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

    def dot(self, other: "Vector2") -> float:
        """Dot product with another vector"""
        return self.x * other.x + self.y * other.y


# ─────────────────────────────────────────────────────────────────────────────
# THREAT TRACKING
# Tracks damage sources and enables smarter target prioritization
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ThreatEntry:
    """Tracks threat from a single enemy"""

    enemy_id: str
    damage_received: int = 0  # Total damage taken from this enemy
    last_hit_time: float = 0.0  # When we were last hit by this enemy
    times_hit: int = 0  # Number of times hit by this enemy

    def get_threat_score(self, current_time: float, decay_rate: float = 0.1) -> float:
        """Calculate current threat score with time decay.

        Recent damage is weighted more heavily than old damage.
        Score decays over time so bots don't hold grudges forever.
        """
        time_since_hit = current_time - self.last_hit_time
        decay_factor = math.exp(-decay_rate * time_since_hit)
        # Base threat on damage, boosted by hit frequency
        return self.damage_received * decay_factor * (1 + self.times_hit * 0.1)


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

    # Threat tracking - for smarter target selection
    threat_map: dict[str, ThreatEntry] = field(default_factory=dict)  # enemy_id -> threat info
    last_damage_time: float = 0.0  # When this bot last took damage (for reactive dodging)
    last_damage_source: t.Optional[str] = None  # Who dealt the last damage

    # Statistics
    damage_dealt: int = 0
    damage_taken: int = 0
    kills: int = 0

    def take_damage(self, damage: int, source_id: t.Optional[str] = None, current_time: float = 0.0) -> int:
        """Apply damage, return actual damage dealt.

        Args:
            damage: Amount of damage to apply
            source_id: ID of the bot that dealt the damage (for threat tracking)
            current_time: Current simulation time (for threat decay)
        """
        actual = min(damage, self.health)
        self.health -= actual
        self.damage_taken += actual

        # Track threat from damage source
        if source_id and actual > 0:
            self.last_damage_time = current_time
            self.last_damage_source = source_id
            if source_id not in self.threat_map:
                self.threat_map[source_id] = ThreatEntry(enemy_id=source_id)
            threat = self.threat_map[source_id]
            threat.damage_received += actual
            threat.last_hit_time = current_time
            threat.times_hit += 1

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

    def get_target_reevaluation_interval(self) -> float:
        """Get how often this bot should re-evaluate targets based on intelligence.

        Higher intelligence = more frequent target checks = more adaptive behavior.
        Range: 1.2s (intel 10) to 2.8s (intel 1)
        """
        # Intelligence ranges from 1-10, map to 2.8s down to 1.2s
        return 3.0 - (self.intelligence / 10.0) * 1.6

    def get_highest_threat(self, current_time: float) -> t.Optional[str]:
        """Get the enemy that poses the highest threat to this bot.

        Returns None if no threats recorded.
        """
        if not self.threat_map:
            return None

        best_threat_id = None
        best_score = 0.0

        for enemy_id, threat in self.threat_map.items():
            score = threat.get_threat_score(current_time)
            if score > best_score:
                best_score = score
                best_threat_id = enemy_id

        # Only return if threat is significant (score > 10)
        return best_threat_id if best_score > 10 else None

    def was_recently_damaged(self, current_time: float, threshold: float = 0.5) -> bool:
        """Check if this bot took damage recently (for reactive dodging).

        Args:
            current_time: Current simulation time
            threshold: Time window in seconds to consider "recent"
        """
        return current_time - self.last_damage_time < threshold

    def get_health_percentage(self) -> float:
        """Get current health as a percentage (0.0 to 1.0)"""
        if self.max_health <= 0:
            return 0.0
        return self.health / self.max_health

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

    STALEMATE PREVENTION:
    If no damage is dealt for a prolonged period, bots become increasingly
    aggressive to force engagement and prevent infinite standoffs.
    """

    # Stalemate prevention thresholds
    STALEMATE_WARNING_TIME = 8.0  # Seconds without damage before bots get antsy
    STALEMATE_FORCE_TIME = 15.0  # Seconds without damage before forced aggression

    def __init__(self, config: BattleConfig = None):
        self.config = config or BattleConfig()
        self.bots: dict[str, BotRuntimeState] = {}
        self.projectiles: list[Projectile] = []
        self.frames: list[FrameData] = []
        self.current_time: float = 0.0
        self.frame_number: int = 0
        self.dt: float = 1.0 / self.config.fps
        self.events: list[dict] = []  # Events for current frame

        self.last_damage_time: float = 0.0  # For stalemate detection

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
            self._update_stalemate_prevention()  # Check for stalemate and modify behaviors
            self._update_movement()
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

    def _get_stalemate_aggression_bonus(self) -> float:
        """Calculate how aggressive bots should become based on stalemate duration.

        Returns a value from 0.0 (normal) to 1.0 (maximum aggression).
        """
        time_without_damage = self.current_time - self.last_damage_time

        if time_without_damage < self.STALEMATE_WARNING_TIME:
            return 0.0

        # Ramp up aggression between warning and force time
        progress = (time_without_damage - self.STALEMATE_WARNING_TIME) / (
            self.STALEMATE_FORCE_TIME - self.STALEMATE_WARNING_TIME
        )
        return min(1.0, progress)

    def _update_stalemate_prevention(self):
        """Modify bot behaviors if a stalemate is detected.

        When no damage has been dealt for a while:
        1. Reduce commitment timers (more frequent repositioning)
        2. Decrease preferred ranges (close the distance)
        3. Eventually force all bots to become AGGRESSIVE
        """
        aggression_bonus = self._get_stalemate_aggression_bonus()

        if aggression_bonus <= 0:
            return  # No stalemate, normal behavior

        for bot in self.bots.values():
            if not bot.is_alive:
                continue
            if bot.is_healer:
                continue  # Don't force healers to be aggressive

            # Reduce commitment timers to force more frequent repositioning
            if bot.commitment_timer > 0.5:
                reduction = aggression_bonus * 0.5  # Up to 50% reduction
                bot.commitment_timer *= 1.0 - reduction

            # At maximum aggression, force bots to close distance
            if aggression_bonus >= 0.8:
                # Calculate distance to nearest enemy
                nearest_enemy = self._find_nearest_enemy(bot)
                if nearest_enemy:
                    dist = bot.position.distance_to(nearest_enemy.position)
                    # If too far, override target position to move closer
                    if dist > bot.max_range * 0.6:
                        # Set target position closer to enemy
                        direction = (nearest_enemy.position - bot.position).normalized()
                        close_distance = bot.min_range * 1.3 if bot.min_range > 0 else 100
                        bot.target_position = nearest_enemy.position - direction * close_distance
                        bot.commitment_timer = 0.3  # Short commitment to reassess quickly

    def _update_ai(self):
        """Update bot AI - target selection and decision making.

        Intelligence affects how often bots re-evaluate targets:
        - High intel (10): Re-evaluates every 1.4s - very adaptive
        - Low intel (1): Re-evaluates every 2.8s - slow to adapt

        Bots also force re-evaluation when:
        - They have no target
        - Current target died
        - They took damage from a different enemy (reactive targeting)
        """
        for bot in self.bots.values():
            if not bot.is_alive:
                continue

            # Calculate intelligence-scaled re-evaluation interval
            reevaluation_interval = bot.get_target_reevaluation_interval()
            time_since_target_check = self.current_time - bot.last_target_check

            # Force re-evaluation conditions
            should_reevaluate = time_since_target_check >= reevaluation_interval

            # React to being hit by a NEW enemy (not our current target)
            if bot.was_recently_damaged(self.current_time, threshold=0.3):
                if bot.last_damage_source and bot.last_damage_source != bot.target_id:
                    # We're being attacked by someone we're not targeting!
                    # Higher intelligence = more likely to react
                    react_chance = 0.3 + (bot.intelligence / 10.0) * 0.5  # 30-80% chance
                    if random.random() < react_chance:
                        should_reevaluate = True

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
        """Select target from candidates based on priority with threat weighting.

        Threat weighting: Bots remember who hurt them and factor that into targeting.
        Higher intelligence = better threat assessment and less random noise.
        """
        if not candidates:
            return None

        # Get threat scores for all candidates
        def get_threat_bonus(enemy_id: str) -> float:
            """Get threat bonus for an enemy (higher = more threatening)"""
            if enemy_id not in bot.threat_map:
                return 0.0
            threat = bot.threat_map[enemy_id]
            # Scale threat influence by intelligence (smarter bots remember better)
            intel_factor = bot.intelligence / 10.0
            return threat.get_threat_score(self.current_time) * intel_factor * 0.5

        if priority == TargetPriority.WEAKEST:
            # Sort by health (lowest first), with intelligence-based noise
            # Threat bonus makes us prefer enemies who hurt us (revenge targeting)
            def score(c: BotRuntimeState) -> float:
                noise = random.uniform(0, 20) * (10 - bot.intelligence) / 10
                threat_bonus = get_threat_bonus(c.bot_id)
                # Lower score = higher priority, so subtract threat bonus
                return c.health + noise - threat_bonus

            target = min(candidates, key=score)

        else:  # CLOSEST (default) or FOCUS_FIRE fallback
            # Sort by distance (closest first), with noise and threat weighting
            def score(c: BotRuntimeState) -> float:
                dist = bot.position.distance_to(c.position)
                noise = random.uniform(0, 50) * (10 - bot.intelligence) / 10
                threat_bonus = get_threat_bonus(c.bot_id)
                # Lower score = higher priority, so subtract threat bonus from distance
                return dist + noise - threat_bonus

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

        Position-based system with team awareness and wall avoidance.

        Features:
        - AGGRESSIVE: Position just outside min_range, directly toward target
        - DEFENSIVE: Position at max_range, directly away from target
        - TACTICAL: Position at optimal range, with some lateral offset
        - Wall avoidance: Penalize positions near arena edges
        - Spread awareness: Offset from allies targeting same enemy
        - Weapon archetype modifiers: Snipers prefer clear sightlines, brawlers flank
        - Stalemate prevention: Reduce ranges when no damage dealt for a while
        """
        preferred_range = bot.get_preferred_range()

        # ─────────────────────────────────────────────────────────────────────
        # STALEMATE PREVENTION: Reduce preferred range if stalemate detected
        # ─────────────────────────────────────────────────────────────────────
        aggression_bonus = self._get_stalemate_aggression_bonus()
        if aggression_bonus > 0 and not bot.is_healer:
            # Reduce preferred range by up to 40% during stalemate
            range_reduction = aggression_bonus * 0.4
            preferred_range *= 1.0 - range_reduction

        # Direction from bot to target
        dx = target.position.x - bot.position.x
        dy = target.position.y - bot.position.y
        dist = max(1.0, math.sqrt(dx * dx + dy * dy))
        dir_x = dx / dist
        dir_y = dy / dist

        # Perpendicular vector for lateral movement
        perp_x = -dir_y
        perp_y = dir_x

        # Calculate ideal distance based on behavior (modified by stalemate)
        if bot.behavior == AIBehavior.AGGRESSIVE:
            # Want to be just outside min_range
            ideal_distance = bot.min_range * 1.15 if bot.min_range > 0 else preferred_range
        elif bot.behavior == AIBehavior.DEFENSIVE:
            # Want to be at max range (reduced during stalemate)
            base_defensive_range = bot.max_range * 0.92
            ideal_distance = base_defensive_range * (1.0 - aggression_bonus * 0.3)
        else:  # TACTICAL
            # Want to be at optimal range
            ideal_distance = preferred_range

        # Base target position along the line to enemy at ideal distance
        base_x = target.position.x - dir_x * ideal_distance
        base_y = target.position.y - dir_y * ideal_distance

        # ─────────────────────────────────────────────────────────────────────
        # SPREAD AWARENESS: Avoid stacking on allies targeting the same enemy
        # ─────────────────────────────────────────────────────────────────────
        spread_offset_x = 0.0
        spread_offset_y = 0.0

        allies_targeting_same = []
        for ally in self.bots.values():
            if ally.bot_id == bot.bot_id:
                continue
            if ally.team != bot.team:
                continue
            if not ally.is_alive:
                continue
            if ally.target_id == target.bot_id:
                allies_targeting_same.append(ally)

        if allies_targeting_same:
            # Calculate offset to spread out from allies
            for ally in allies_targeting_same:
                ally_to_base = Vector2(base_x - ally.position.x, base_y - ally.position.y)
                dist_to_ally = ally_to_base.magnitude()
                if dist_to_ally < 120:  # Too close to ally's position
                    # Push away from ally along perpendicular axis
                    if dist_to_ally > 0:
                        push_dir = ally_to_base.normalized()
                    else:
                        # Same position - pick random direction
                        push_dir = Vector2(perp_x, perp_y) * random.choice([-1, 1])
                    spread_offset_x += push_dir.x * (120 - dist_to_ally) * 0.5
                    spread_offset_y += push_dir.y * (120 - dist_to_ally) * 0.5

        # ─────────────────────────────────────────────────────────────────────
        # WEAPON ARCHETYPE MODIFIERS
        # ─────────────────────────────────────────────────────────────────────
        archetype_offset_x = 0.0
        archetype_offset_y = 0.0

        if bot.weapon_archetype == "SNIPER":
            # Snipers prefer positions with clear sightlines - slight lateral offset
            # to avoid being directly in front of melee allies
            lateral_offset = random.uniform(30, 80) * random.choice([-1, 1])
            archetype_offset_x += perp_x * lateral_offset
            archetype_offset_y += perp_y * lateral_offset
        elif bot.weapon_archetype == "BRAWLER":
            # Brawlers try to flank - approach from angles
            if bot.behavior == AIBehavior.AGGRESSIVE:
                flank_offset = random.uniform(20, 60) * random.choice([-1, 1])
                archetype_offset_x += perp_x * flank_offset
                archetype_offset_y += perp_y * flank_offset

        # Add offsets for TACTICAL behavior repositioning
        tactical_offset_x = 0.0
        tactical_offset_y = 0.0
        if bot.behavior == AIBehavior.TACTICAL:
            offset = random.uniform(-50, 50)
            tactical_offset_x = perp_x * offset
            tactical_offset_y = perp_y * offset

        # Combine all offsets
        target_x = base_x + spread_offset_x + archetype_offset_x + tactical_offset_x
        target_y = base_y + spread_offset_y + archetype_offset_y + tactical_offset_y

        # ─────────────────────────────────────────────────────────────────────
        # WALL AVOIDANCE: Push position away from walls
        # ─────────────────────────────────────────────────────────────────────
        wall_margin = 100.0  # Distance from wall to start avoiding
        wall_push_strength = 0.7  # How strongly to push away from walls

        # Left wall
        if target_x < wall_margin:
            push = (wall_margin - target_x) * wall_push_strength
            target_x += push
        # Right wall
        elif target_x > self.config.arena_width - wall_margin:
            push = (target_x - (self.config.arena_width - wall_margin)) * wall_push_strength
            target_x -= push
        # Top wall
        if target_y < wall_margin:
            push = (wall_margin - target_y) * wall_push_strength
            target_y += push
        # Bottom wall
        elif target_y > self.config.arena_height - wall_margin:
            push = (target_y - (self.config.arena_height - wall_margin)) * wall_push_strength
            target_y -= push

        # Final clamp to arena bounds (hard limit)
        margin = 60.0
        target_x = max(margin, min(self.config.arena_width - margin, target_x))
        target_y = max(margin, min(self.config.arena_height - margin, target_y))

        return Vector2(target_x, target_y)

    def _maybe_dodge(self, bot: BotRuntimeState, target: BotRuntimeState):
        """Check if bot should initiate a dodge maneuver.

        REACTIVE DODGING: Dodges are triggered by:
        1. Taking recent damage (pain response)
        2. Incoming projectiles heading toward this bot
        3. Random chance (baseline evasion, intelligence-scaled)
        4. Low health (survival instinct)

        Dodges are quick perpendicular bursts that provide evasion
        without the infinite orbit problem of continuous strafing.
        """
        # Currently in a dodge - let it play out
        if bot.dodge_duration > 0:
            return

        # Dodge on cooldown
        if bot.dodge_timer > 0:
            return

        # ─────────────────────────────────────────────────────────────────────
        # REACTIVE DODGE TRIGGERS
        # ─────────────────────────────────────────────────────────────────────
        dodge_triggered = False
        dodge_direction = random.choice([-1, 1])

        # 1. PAIN RESPONSE: Just took damage - dodge away!
        if bot.was_recently_damaged(self.current_time, threshold=0.25):
            # Higher intelligence = more likely to react to pain
            pain_dodge_chance = 0.15 + (bot.intelligence / 10.0) * 0.35  # 15-50%
            if random.random() < pain_dodge_chance:
                dodge_triggered = True
                # Try to dodge away from damage source
                if bot.last_damage_source and bot.last_damage_source in self.bots:
                    attacker = self.bots[bot.last_damage_source]
                    if attacker.is_alive:
                        # Dodge perpendicular to attacker's direction
                        to_attacker = attacker.position - bot.position
                        if to_attacker.magnitude() > 0:
                            # Pick perpendicular direction randomly
                            dodge_direction = 1 if random.random() > 0.5 else -1

        # 2. INCOMING PROJECTILES: Check if any projectiles are heading our way
        if not dodge_triggered:
            incoming_threat = self._check_incoming_projectiles(bot)
            if incoming_threat:
                # Intelligence affects reaction to incoming fire
                projectile_dodge_chance = 0.1 + (bot.intelligence / 10.0) * 0.4  # 10-50%
                if random.random() < projectile_dodge_chance:
                    dodge_triggered = True
                    # Pick a perpendicular direction randomly to evade
                    dodge_direction = random.choice([-1, 1])

        # 3. LOW HEALTH SURVIVAL: More likely to dodge when hurt
        if not dodge_triggered:
            health_pct = bot.get_health_percentage()
            if health_pct < 0.4:  # Below 40% health
                # Desperate dodging - low health makes bots more evasive
                survival_dodge_chance = 0.05 * (1.0 - health_pct)  # Up to 3% per frame
                if random.random() < survival_dodge_chance:
                    dodge_triggered = True

        # 4. BASELINE RANDOM DODGE: Intelligence-scaled evasion
        if not dodge_triggered:
            # Base chance + intelligence bonus
            base_chance = 0.015 + (bot.intelligence / 100.0) * 0.025  # 1.5-4% per frame
            if random.random() < base_chance:
                dodge_triggered = True

        if not dodge_triggered:
            return

        # ─────────────────────────────────────────────────────────────────────
        # EXECUTE DODGE
        # ─────────────────────────────────────────────────────────────────────
        bot.dodge_direction = dodge_direction
        bot.dodge_duration = 0.2 + (bot.agility * 0.1)  # 200-300ms based on agility

        # Cooldown scales inversely with intelligence (smarter = can dodge more often)
        base_cooldown = 2.0 - (bot.intelligence / 10.0) * 0.8  # 1.2-2.0s base
        bot.dodge_timer = base_cooldown + random.uniform(-0.3, 0.5)

    def _check_incoming_projectiles(self, bot: BotRuntimeState) -> t.Optional[Projectile]:
        """Check if any enemy projectiles are heading toward this bot.

        Returns the most threatening projectile, or None if clear.
        """
        threat_radius = 80.0  # How close a projectile needs to pass to be threatening
        prediction_time = 0.5  # Look ahead time in seconds

        for proj in self.projectiles:
            if not proj.alive:
                continue
            if proj.is_heal:
                continue  # Ignore healing projectiles
            if proj.shooter_id == bot.bot_id:
                continue  # Ignore our own projectiles

            # Check if shooter is enemy
            shooter = self.bots.get(proj.shooter_id)
            if shooter and shooter.team == bot.team:
                continue  # Friendly fire projectile

            # Predict where projectile will be
            future_pos = proj.position + proj.velocity * prediction_time

            # Check if projectile path comes close to bot
            # Using point-to-line-segment distance
            proj_start = proj.position
            proj_end = future_pos

            dx = proj_end.x - proj_start.x
            dy = proj_end.y - proj_start.y
            line_len_sq = dx * dx + dy * dy

            if line_len_sq == 0:
                continue

            # Parameter t for closest point on line segment
            t = max(
                0, min(1, ((bot.position.x - proj_start.x) * dx + (bot.position.y - proj_start.y) * dy) / line_len_sq)
            )

            # Closest point on projectile path
            closest_x = proj_start.x + t * dx
            closest_y = proj_start.y + t * dy

            # Distance from bot to closest point
            dist_sq = (bot.position.x - closest_x) ** 2 + (bot.position.y - closest_y) ** 2

            if dist_sq < threat_radius * threat_radius:
                # This projectile is a threat!
                return proj

        return None

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
        """Wander toward arena center when no target.

        Uses commitment system to avoid jittery orientation changes.
        """
        # Check if we need a new wander target
        # Re-use commitment_timer for wandering consistency
        if bot.commitment_timer <= 0 or bot.target_position is None:
            center_x = self.config.arena_width / 2
            center_y = self.config.arena_height / 2

            # Add some randomness to the center target
            target_x = center_x + random.uniform(-100, 100)
            target_y = center_y + random.uniform(-100, 100)

            bot.target_position = Vector2(target_x, target_y)
            # Longer commitment when wandering - smooth movement
            bot.commitment_timer = random.uniform(1.5, 3.0)

        # Use the committed target position
        dx = bot.target_position.x - bot.position.x
        dy = bot.target_position.y - bot.position.y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < 50:
            # Near target, pick a new random direction smoothly
            if bot.commitment_timer <= 0:
                bot.target_orientation = (bot.orientation + random.uniform(-45, 45)) % 360
                bot.commitment_timer = random.uniform(1.0, 2.0)
            self._rotate_chassis_towards(bot, bot.target_orientation)
            return

        # Move toward committed target
        desired_angle = math.degrees(math.atan2(dy, dx)) % 360
        self._rotate_chassis_towards(bot, desired_angle)

        rad = math.radians(bot.orientation)
        move_vec = Vector2(math.cos(rad), math.sin(rad)) * (bot.speed * 0.5 * self.dt)
        self._apply_movement(bot, move_vec)

    def _find_lowest_health_ally(self, bot: BotRuntimeState) -> t.Optional[BotRuntimeState]:
        """Find the best ally to heal using triage logic.

        TRIAGE PRIORITIES (in order):
        1. Critical allies (<30% health) - emergency healing needed
        2. Damaged allies (<70% health) - standard healing
        3. High-value allies (high DPS) - prefer healing damage dealers
        4. Nearest damaged ally - if equal priority, heal closest

        Ignores:
        - Full health allies (100%)
        - Nearly-full allies (>90%) unless no other options
        - Self

        Returns None if no ally needs healing.
        """
        candidates: list[tuple[float, BotRuntimeState]] = []

        for other in self.bots.values():
            if other.bot_id == bot.bot_id:
                continue
            if not other.is_alive:
                continue
            if other.team != bot.team:
                continue

            health_pct = other.get_health_percentage()

            # Skip full health allies
            if health_pct >= 0.98:
                continue

            # Calculate priority score (LOWER = higher priority)
            score = 0.0

            # Health urgency (main factor)
            if health_pct < 0.3:
                score = 0  # CRITICAL - highest priority
            elif health_pct < 0.5:
                score = 100  # Urgent
            elif health_pct < 0.7:
                score = 200  # Standard
            elif health_pct < 0.9:
                score = 300  # Low priority
            else:
                score = 400  # Very low priority (nearly full)

            # Add health percentage as tiebreaker (lower health = lower score = higher priority)
            score += health_pct * 50

            # Bonus for high-DPS allies (prefer keeping damage dealers alive)
            # Higher damage_per_shot * shots_per_second = higher DPS
            ally_dps = other.damage_per_shot * other.shots_per_second
            if ally_dps > 30:  # High DPS threshold
                score -= 25  # Priority boost

            # Slight bonus for closer allies (easier to reach)
            distance = bot.position.distance_to(other.position)
            score += distance * 0.05  # Small distance penalty

            candidates.append((score, other))

        if not candidates:
            return None

        # Sort by score (lowest first) and return best candidate
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

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
        PROTECTOR/HEALER movement with smart positioning and self-preservation.

        BEHAVIOR PRIORITIES:
        1. SELF-PRESERVATION: If healer is low health, prioritize survival
        2. ANTICIPATION: Position near allies about to engage (frontline support)
        3. PROTECTION: Stay behind ally relative to enemies
        4. RANGE MANAGEMENT: Stay within healing range but not too close

        Key intelligence-based differences:
        - Higher intel = better threat awareness and positioning
        - Higher intel = smarter triage (handled in target selection)
        """
        # Find the ally to protect/heal using triage
        ally_to_heal = self._find_lowest_health_ally(bot)

        # ─────────────────────────────────────────────────────────────────────
        # SELF-PRESERVATION CHECK
        # If healer is critically low, prioritize survival over healing
        # ─────────────────────────────────────────────────────────────────────
        healer_health_pct = bot.get_health_percentage()
        is_in_danger = healer_health_pct < 0.35

        if is_in_danger:
            nearest_enemy = self._find_nearest_enemy(bot)
            if nearest_enemy:
                enemy_dist = bot.position.distance_to(nearest_enemy.position)
                # If enemy is close and we're low, RUN AWAY
                if enemy_dist < bot.max_range * 0.8:
                    self._flee_from_enemy(bot, nearest_enemy)
                    return

        if not ally_to_heal:
            # No ally needs healing - find someone to support proactively
            # Stay near the ally most likely to take damage (closest to enemies)
            ally_to_heal = self._find_frontline_ally(bot)

            if not ally_to_heal:
                # No allies at all - wander toward center
                self._wander_movement(bot)
                return

        # Find nearest enemy for positioning calculations
        nearest_enemy = self._find_nearest_enemy(bot)

        # Calculate desired position
        ally_pos = ally_to_heal.position
        bot_to_ally_dist = bot.position.distance_to(ally_pos)

        # Healing range management - stay within range but not too close
        # Ideal distance is 60-70% of max healing range
        ideal_ally_distance = max(50, bot.max_range * 0.6)
        max_ally_distance = bot.max_range * 0.85

        if nearest_enemy:
            enemy_pos = nearest_enemy.position
            # Vector from enemy to ally (direction of "behind ally")
            enemy_to_ally = ally_pos - enemy_pos
            enemy_to_ally_dist = enemy_to_ally.magnitude()

            if enemy_to_ally_dist > 0:
                direction = enemy_to_ally.normalized()
                # Position behind ally but maintain healing distance
                target_pos = ally_pos + direction * ideal_ally_distance

                # ─── SMART POSITIONING: Avoid walls ───
                # Check if target position is near a wall and adjust
                target_pos = self._adjust_position_for_walls(target_pos, ideal_ally_distance * 0.5)
            else:
                target_pos = ally_pos
        else:
            # No enemy visible - position behind ally based on their facing
            rad = math.radians(ally_to_heal.orientation + 180)
            target_pos = ally_pos + Vector2(math.cos(rad), math.sin(rad)) * ideal_ally_distance

        # Calculate movement direction to reach target position
        to_target = target_pos - bot.position
        target_distance = to_target.magnitude()

        if target_distance < 15:
            # At target position - face toward ally for healing shots
            target_angle = bot.position.angle_to(ally_pos)
            self._rotate_chassis_towards(bot, target_angle, speed_mult=0.5)
            bot.is_turning = False

            # Small movement to avoid being stationary
            rad = math.radians(bot.orientation)
            move_vec = Vector2(math.cos(rad), math.sin(rad)) * (bot.speed * 0.08 * self.dt)
            self._apply_movement(bot, move_vec)
            return

        # Move toward target position
        desired_angle = bot.position.angle_to(target_pos)

        # Speed based on urgency
        if bot_to_ally_dist > max_ally_distance:
            speed_mult = 1.0  # Sprint to catch up
        elif bot_to_ally_dist > ideal_ally_distance * 1.5:
            speed_mult = 0.9
        elif target_distance > ideal_ally_distance:
            speed_mult = 0.75
        else:
            speed_mult = 0.5

        # Apply agility penalty for turning
        angle_diff = abs((desired_angle - bot.orientation + 180) % 360 - 180)
        angle_penalty = min(1.0, angle_diff / 90.0)
        effective_speed_mult = speed_mult * (1.0 - angle_penalty * (1.0 - bot.agility))
        effective_speed_mult = max(0.3, effective_speed_mult)

        bot.is_turning = angle_diff > 30

        # Rotate and move
        self._rotate_chassis_towards(bot, desired_angle, speed_mult=1.2)
        rad = math.radians(bot.orientation)
        move_vec = Vector2(math.cos(rad), math.sin(rad)) * (bot.speed * effective_speed_mult * self.dt)
        self._apply_movement(bot, move_vec)

    def _find_frontline_ally(self, bot: BotRuntimeState) -> t.Optional[BotRuntimeState]:
        """Find the ally closest to enemies (frontline) for proactive support.

        Used when no ally needs healing - positions healer near action.
        """
        nearest_enemy = self._find_nearest_enemy(bot)
        if not nearest_enemy:
            return None

        closest_to_enemy: t.Optional[BotRuntimeState] = None
        closest_dist = float("inf")

        for ally in self.bots.values():
            if ally.bot_id == bot.bot_id:
                continue
            if ally.team != bot.team:
                continue
            if not ally.is_alive:
                continue

            dist = ally.position.distance_to(nearest_enemy.position)
            if dist < closest_dist:
                closest_dist = dist
                closest_to_enemy = ally

        return closest_to_enemy

    def _flee_from_enemy(self, bot: BotRuntimeState, enemy: BotRuntimeState):
        """Emergency flee behavior for low-health healers.

        Moves directly away from the threatening enemy.
        """
        # Direction away from enemy
        flee_vec = bot.position - enemy.position
        flee_dist = flee_vec.magnitude()

        if flee_dist > 0:
            flee_dir = flee_vec.normalized()
            desired_angle = math.degrees(math.atan2(flee_dir.y, flee_dir.x)) % 360
        else:
            # On top of enemy - pick random direction
            desired_angle = random.uniform(0, 360)

        # Rotate toward flee direction
        self._rotate_chassis_towards(bot, desired_angle, speed_mult=1.5)

        # Move at max speed
        rad = math.radians(bot.orientation)
        move_vec = Vector2(math.cos(rad), math.sin(rad)) * (bot.speed * self.dt)
        self._apply_movement(bot, move_vec)

    def _adjust_position_for_walls(self, pos: Vector2, margin: float) -> Vector2:
        """Adjust a position to avoid being too close to walls.

        Args:
            pos: Desired position
            margin: Minimum distance from walls

        Returns:
            Adjusted position pushed away from walls if necessary
        """
        adjusted_x = pos.x
        adjusted_y = pos.y

        wall_buffer = margin + 60.0  # Extra buffer beyond margin

        if adjusted_x < wall_buffer:
            adjusted_x = wall_buffer
        elif adjusted_x > self.config.arena_width - wall_buffer:
            adjusted_x = self.config.arena_width - wall_buffer

        if adjusted_y < wall_buffer:
            adjusted_y = wall_buffer
        elif adjusted_y > self.config.arena_height - wall_buffer:
            adjusted_y = self.config.arena_height - wall_buffer

        return Vector2(adjusted_x, adjusted_y)

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

        # Collision checking
        for other in self.bots.values():
            if other.bot_id != bot.bot_id and other.is_alive:
                if new_pos.distance_to(other.position) < self.config.bot_radius * 2.2:
                    return  # Collision, don't move

        bot.position = new_pos

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
                    # Returns None if no mask is available for this bot
                    pixel_collision = self.collision_manager.check_collision(
                        proj.position.x,
                        proj.position.y,
                        bot.bot_id,
                        bot.position.x,
                        bot.position.y,
                        bot.orientation,
                    )
                    if pixel_collision is not None:
                        collision = pixel_collision
                    else:
                        # No mask available, fall back to circular collision
                        collision = proj.position.distance_to(bot.position) < self.config.bot_radius
                else:
                    # No collision manager, use simple circular collision
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
                        # Don't track threat for friendly fire
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
                        # Enemy hit - full damage with threat tracking
                        actual = hit_bot.take_damage(
                            proj.damage, source_id=proj.shooter_id, current_time=self.current_time
                        )
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
                    actual = target.take_damage(
                        bot.damage_per_shot, source_id=bot.bot_id, current_time=self.current_time
                    )
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
