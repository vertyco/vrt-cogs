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
    """AI behavior patterns for bots - derived from MovementStance"""

    AGGRESSIVE = "aggressive"  # Rush straight at enemies, close range preference
    DEFENSIVE = "defensive"  # Keep distance, kite enemies, stay at max range
    FLANKER = "flanker"  # Circle around targets, attack from sides
    SNIPER = "sniper"  # Stay far back, minimal movement, max range
    BERSERKER = "berserker"  # Erratic, unpredictable, charges in
    TACTICAL = "tactical"  # Balanced, uses cover positions, smart movement
    KITING = "kiting"  # Attack while backing away
    HOLD = "hold"  # Stay in position, minimal movement
    PROTECTOR = "protector"  # Stay close to low-health allies, protect them


class TargetPriority(str, Enum):
    """Target selection priority"""

    FOCUS_FIRE = "focus_fire"  # Attack same target as teammates
    WEAKEST = "weakest"  # Target lowest HP enemy
    STRONGEST = "strongest"  # Target highest HP enemy
    CLOSEST = "closest"  # Attack nearest enemy
    FURTHEST = "furthest"  # Attack furthest enemy


class EngagementRange(str, Enum):
    """Preferred engagement distance override"""

    AUTO = "auto"  # AI manages based on weapon stats
    CLOSE = "close"  # Force close range
    OPTIMAL = "optimal"  # Stay at midpoint of min/max range
    MAX = "max"  # Force maximum range


# Default behaviors for chassis types (used when no tactical orders given)
# Based on original Bot Arena 3 chassis characteristics
DEFAULT_CHASSIS_BEHAVIORS = {
    # Light chassis - fast and agile
    "DLZ-100": AIBehavior.FLANKER,  # Starter chassis, good all-rounder
    "DLZ-250": AIBehavior.AGGRESSIVE,  # Upgraded light, more aggressive
    # Medium chassis - balanced
    "SmartMove": AIBehavior.TACTICAL,  # Smart AI chassis
    "CLR-Z050": AIBehavior.DEFENSIVE,  # Tanky medium
    "Electron": AIBehavior.TACTICAL,  # High-capacity medium
    # Heavy chassis - slow but tough
    "Durichas": AIBehavior.DEFENSIVE,  # Heavy tank
    "Deliverance": AIBehavior.SNIPER,  # Ultimate heavy, prefers range
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
    engagement_range: EngagementRange = EngagementRange.AUTO

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

    # AI state for complex behaviors
    strafe_direction: int = 1  # 1 = clockwise, -1 = counter-clockwise
    strafe_timer: float = 0.0  # Time until direction change
    wander_angle: float = 0.0  # Random wander offset
    wander_timer: float = 0.0  # Time until wander angle change

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
        """Get the preferred engagement range based on tactical orders.

        The engagement_range setting takes priority over behavior.
        For AUTO, the behavior determines the default preference.

        Range preferences are EXTREME to create dramatically different behaviors:
        - AGGRESSIVE/BERSERKER: 15-25% of range (in their face)
        - DEFENSIVE: 90-100% of range (max distance)
        - KITING: 70-85% of range (mobile but far)
        - FLANKER: 50-65% of range (medium, circling)
        - HOLD: doesn't matter, they don't move
        - SNIPER: 95%+ of max range
        """
        if self.engagement_range == EngagementRange.CLOSE:
            # Very close - just outside minimum range
            return self.min_range + (self.max_range - self.min_range) * 0.10
        elif self.engagement_range == EngagementRange.OPTIMAL:
            # Midpoint between min and max - balanced
            return (self.min_range + self.max_range) / 2
        elif self.engagement_range == EngagementRange.MAX:
            # Stay at max range - far back
            return self.max_range * 0.95  # Slightly inside max to ensure shots land
        else:  # AUTO - based on behavior
            if self.behavior in (AIBehavior.AGGRESSIVE, AIBehavior.BERSERKER):
                # VERY close-range fighters - get in their face!
                return self.min_range + (self.max_range - self.min_range) * 0.15
            elif self.behavior == AIBehavior.DEFENSIVE:
                # DEFENSIVE = maintain MAXIMUM possible range, always back away
                return self.max_range * 0.95
            elif self.behavior == AIBehavior.SNIPER:
                # Snipers want absolute max range
                return self.max_range * 0.98
            elif self.behavior == AIBehavior.KITING:
                # Kiters stay at 75-80% range for mobility while retreating
                return self.min_range + (self.max_range - self.min_range) * 0.78
            elif self.behavior == AIBehavior.FLANKER:
                # Flankers prefer medium range (50-60%) for circling
                return self.min_range + (self.max_range - self.min_range) * 0.55
            elif self.behavior == AIBehavior.HOLD:
                # Doesn't matter - they stay in place
                return (self.min_range + self.max_range) / 2
            elif self.behavior == AIBehavior.PROTECTOR:
                # Stay close to allies, use healing range
                return self.min_range + (self.max_range - self.min_range) * 0.4
            else:
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

        # Stalemate detection - forces engagement when bots circle too long
        self.last_damage_time: float = 0.0
        self.stalemate_mode: bool = False
        self.stalemate_threshold: float = 3.0  # Seconds without damage before forcing engagement

        # Corner-lock detection - when bots cluster together and can't shoot due to min range
        self.corner_lock_mode: bool = False
        self.corner_lock_threshold: float = 4.0  # Seconds in stalemate before checking for corner-lock
        self.dispersal_mode: bool = False  # Forces bots to spread out when corner-locked
        self.dispersal_timer: float = 0.0  # How long dispersal has been active

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
        engagement_range: t.Optional[EngagementRange] = None,
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
            engagement_range: Preferred engagement distance (from tactical orders)
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
            engagement_range=engagement_range or EngagementRange.AUTO,
            agility=max(0.0, min(1.0, agility)),  # Clamp to 0-1
            weapon_archetype=weapon_archetype,
            strafe_direction=random.choice([1, -1]),
            strafe_timer=random.uniform(0.5, 4.0),
            wander_angle=random.uniform(-30, 30),
            wander_timer=random.uniform(0.5, 2.0),
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

        # Arena edge buffer - keeps bots spawning away from walls
        arena_buffer = 40.0
        spawn_y_offset = 80 + arena_buffer  # Distance from edge for spawn row

        # Team 1 starts at top, facing down
        if team1:
            spacing = self.config.arena_width / (len(team1) + 1)
            for i, bot in enumerate(team1):
                bot.position = Vector2((i + 1) * spacing, spawn_y_offset)
                bot.orientation = 90  # chassis facing down
                bot.weapon_orientation = 90  # weapon also facing down initially
                bot.target_orientation = 90
                # Set strafe direction based on spawn side - left spawns circle left, right spawns circle right
                if bot.position.x < self.config.arena_width / 2:
                    bot.strafe_direction = -1  # Circle left (counter-clockwise)
                else:
                    bot.strafe_direction = 1  # Circle right (clockwise)

        # Team 2 starts at bottom, facing up
        if team2:
            spacing = self.config.arena_width / (len(team2) + 1)
            for i, bot in enumerate(team2):
                bot.position = Vector2((i + 1) * spacing, self.config.arena_height - spawn_y_offset)
                bot.orientation = 270  # chassis facing up
                bot.weapon_orientation = 270  # weapon also facing up initially
                bot.target_orientation = 270
                # Set strafe direction based on spawn side - left spawns circle left, right spawns circle right
                if bot.position.x < self.config.arena_width / 2:
                    bot.strafe_direction = -1  # Circle left (counter-clockwise)
                else:
                    bot.strafe_direction = 1  # Circle right (clockwise)

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

            # Check for stalemate - if no damage dealt for too long, force aggression
            self._update_stalemate_detection()

            # Update all systems
            self._update_ai()
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

    def _update_stalemate_detection(self):
        """
        Detect and resolve stalemate situations where bots can't engage.

        Two escalation levels:
        1. Stalemate Mode (8s no damage): Force bots to be more aggressive
        2. Dispersal Mode (12s no damage + corner-lock detected): Force bots to spread apart

        Corner-lock occurs when bots are clustered so close they can't shoot (min_range).
        """
        time_since_damage = self.current_time - self.last_damage_time

        # Level 1: Basic stalemate - bots are circling without engaging
        if time_since_damage >= self.stalemate_threshold and not self.stalemate_mode:
            self.stalemate_mode = True
            self.events.append(
                {
                    "type": "stalemate_engaged",
                    "time": self.current_time,
                }
            )

        # Level 2: Check for corner-lock after stalemate mode hasn't helped
        # Changed from 12s to 6s for faster intervention
        if self.stalemate_mode and time_since_damage >= self.stalemate_threshold + 6.0:
            if self._detect_corner_lock() and not self.dispersal_mode:
                self.dispersal_mode = True
                self.dispersal_timer = 0.0
                self.events.append(
                    {
                        "type": "dispersal_engaged",
                        "time": self.current_time,
                    }
                )

        # Track dispersal duration and exit if it's been long enough
        if self.dispersal_mode:
            self.dispersal_timer += self.dt
            # Exit dispersal mode after 6 seconds - more time to spread
            if self.dispersal_timer >= 6.0:
                self.dispersal_mode = False
                self.corner_lock_mode = False

    def _detect_corner_lock(self) -> bool:
        """
        Detect if bots are corner-locked (clustered together unable to shoot).

        Returns True if:
        - Bots are very close together (potential min_range issues)
        - At least one bot is against a wall
        - Bots can't shoot each other due to range restrictions
        """
        alive_bots = [b for b in self.bots.values() if b.is_alive]
        if len(alive_bots) < 2:
            return False

        # Check for dangerous clustering
        against_wall_count = 0
        mutual_deadlock_count = 0  # Both bots can't shoot each other

        for bot in alive_bots:
            # Check if against wall
            against_wall, _ = self._is_against_wall(bot)
            if against_wall:
                against_wall_count += 1

            # Check for mutual deadlocks with enemies
            for other in alive_bots:
                if other.bot_id == bot.bot_id or other.team == bot.team:
                    continue

                distance = bot.position.distance_to(other.position)

                # Check if BOTH bots are inside each other's min_range (deadlock)
                bot_cant_shoot = distance < bot.min_range
                other_cant_shoot = distance < other.min_range

                if bot_cant_shoot and other_cant_shoot:
                    mutual_deadlock_count += 1

        # Corner-lock detected if:
        # - Any mutual deadlock exists (both can't shoot)
        # - OR multiple bots against wall with close proximity
        return mutual_deadlock_count >= 1 or (against_wall_count >= 2)

    def _get_dispersal_direction(self, bot: BotRuntimeState) -> tuple[float, float]:
        """
        Calculate the direction a bot should move to disperse from a cluster.

        Returns (angle, speed_multiplier) that moves the bot:
        1. Away from the centroid of nearby enemies
        2. Away from walls
        3. Toward open space
        """
        alive_bots = [b for b in self.bots.values() if b.is_alive and b.bot_id != bot.bot_id]
        if not alive_bots:
            return bot.orientation, 0.5

        # Calculate centroid of nearby bots - prioritize enemies
        nearby_x = 0.0
        nearby_y = 0.0
        nearby_count = 0
        enemy_weight = 2.0  # Weight enemies more heavily

        for other in alive_bots:
            distance = bot.position.distance_to(other.position)
            if distance < 300:  # Consider "nearby" - increased range
                weight = enemy_weight if other.team != bot.team else 1.0
                nearby_x += other.position.x * weight
                nearby_y += other.position.y * weight
                nearby_count += weight

        if nearby_count > 0:
            # Move AWAY from weighted centroid (prioritizes escaping enemies)
            centroid_x = nearby_x / nearby_count
            centroid_y = nearby_y / nearby_count
            away_angle = math.degrees(math.atan2(bot.position.y - centroid_y, bot.position.x - centroid_x)) % 360
        else:
            # No nearby bots, move toward arena center
            center_x = self.config.arena_width / 2
            center_y = self.config.arena_height / 2
            away_angle = math.degrees(math.atan2(center_y - bot.position.y, center_x - bot.position.x)) % 360

        # Blend with wall escape if against wall - wall escape takes priority
        against_wall, walls_hit = self._is_against_wall(bot)
        if against_wall:
            wall_escape_angle, _ = self._get_wall_escape_vector(bot, walls_hit)
            # Wall escape is primary, disperse direction is secondary
            away_angle = (wall_escape_angle * 0.7 + away_angle * 0.3) % 360

        return away_angle, 1.0  # FULL speed to disperse - this is an emergency!

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
        """Select target from candidates based on priority"""
        if not candidates:
            return None

        if priority == TargetPriority.WEAKEST:
            # Sort by health (lowest first), with intelligence-based noise
            def score(c: BotRuntimeState) -> float:
                noise = random.uniform(0, 20) * (10 - bot.intelligence) / 10
                return c.health + noise

            target = min(candidates, key=score)

        elif priority == TargetPriority.STRONGEST:
            # Sort by health (highest first), with noise
            def score(c: BotRuntimeState) -> float:
                noise = random.uniform(0, 20) * (10 - bot.intelligence) / 10
                return -c.health + noise

            target = min(candidates, key=score)

        elif priority == TargetPriority.FURTHEST:
            # Filter to only in-range enemies - prevents chasing unreachable targets
            in_range_candidates = [c for c in candidates if bot.position.distance_to(c.position) <= bot.max_range * 1.5]
            # If no in-range enemies, fall back to closest approach
            if not in_range_candidates:
                in_range_candidates = candidates[:]

            # Sort by distance (furthest first), with noise
            def score(c: BotRuntimeState) -> float:
                dist = bot.position.distance_to(c.position)
                noise = random.uniform(0, 50) * (10 - bot.intelligence) / 10
                return -dist + noise

            target = min(in_range_candidates, key=score)

        else:  # CLOSEST (default)
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
        """Update bot movement based on AI behavior - STOP-TURN-MOVE pattern"""
        for bot in self.bots.values():
            if not bot.is_alive:
                continue

            # Update AI timers - shorter intervals for more active movement
            bot.strafe_timer -= self.dt
            bot.wander_timer -= self.dt

            if bot.strafe_timer <= 0:
                bot.strafe_direction *= -1
                bot.strafe_timer = random.uniform(1.0, 5.0)  # Longer, more varied intervals

            if bot.wander_timer <= 0:
                bot.wander_angle = random.uniform(-60, 60)  # Larger wander angles
                bot.wander_timer = random.uniform(0.3, 1.2)  # Shorter wander intervals

            if not bot.target_id or bot.target_id not in self.bots:
                # No target - wander randomly
                self._wander_movement(bot)
                continue

            target = self.bots[bot.target_id]
            if not target.is_alive:
                self._wander_movement(bot)
                continue

            # Execute behavior-specific movement
            # Most behaviors use the unified agile movement system
            # which calculates direction based on behavior in _calculate_desired_direction
            if bot.behavior == AIBehavior.PROTECTOR:
                # Protector has special ally-following logic
                self._protector_movement(bot, target)
            else:
                # All other behaviors use the unified system
                self._execute_agile_movement(bot, target)

    def _wander_movement(self, bot: BotRuntimeState):
        """Random wandering when no target - stop-turn-move pattern"""
        # Set new wander target direction periodically
        if bot.wander_timer <= 0:
            bot.target_orientation = (bot.orientation + random.uniform(-90, 90)) % 360
            bot.wander_timer = random.uniform(1.0, 3.0)
            bot.is_turning = True

        # Check if we need to turn
        angle_diff = abs((bot.target_orientation - bot.orientation + 180) % 360 - 180)

        if angle_diff > 15:
            # Still turning - don't move
            bot.is_turning = True
            self._rotate_chassis_towards(bot, bot.target_orientation)
        else:
            # Aligned - can move forward
            bot.is_turning = False
            rad = math.radians(bot.orientation)
            move_vec = Vector2(math.cos(rad), math.sin(rad)) * (bot.speed * 0.4 * self.dt)
            self._apply_movement(bot, move_vec)

    def _calculate_desired_direction(self, bot: BotRuntimeState, target: BotRuntimeState) -> tuple[float, float]:
        """Calculate the desired movement direction and speed multiplier based on behavior.

        Uses the bot's tactical orders (engagement_range) to determine preferred distance.
        Priority: Wall escape > Stalemate mode > Normal behavior
        Returns (direction_angle, speed_multiplier).

        BEHAVIOR DESIGN - Each stance has DRAMATICALLY different movement:

        AGGRESSIVE: Direct charge at FULL speed, minimal deviation (0-15° from target)
            - Speed: Always 1.0 toward enemy, 0.6-0.8 when adjusting
            - Angle: 0-15° deviation max (nearly direct approach)
            - Range: 15-25% of max (very close combat)

        DEFENSIVE: ALWAYS retreat, maintain MAX range, wide evasive strafing
            - Speed: 0.9-1.0 when retreating, 0.6-0.75 when maintaining
            - Angle: 150-180° from target (always backing away)
            - Range: 90-100% of max (max distance always)

        KITING: CONSTANT backward movement while firing, never stops
            - Speed: 0.85-1.0 constant (always moving)
            - Angle: 120-160° from target (retreating while circling)
            - Range: 70-85% of max (mobile but far)

        HOLD: COMPLETELY STATIONARY turret, zero forward/backward movement
            - Speed: 0.0-0.1 (nearly zero)
            - Angle: Only rotates to face target
            - Range: Doesn't move to adjust range

        FLANKING: CONSTANT perpendicular circling at high speed
            - Speed: 0.9-1.0 (fast lateral movement)
            - Angle: 85-95° from target (perpendicular orbit)
            - Range: 50-65% of max (medium range circling)

        PROTECTOR: Handled separately in _protector_movement()
        """
        distance = bot.position.distance_to(target.position)
        target_angle = bot.position.angle_to(target.position)

        # Get preferred range from tactical orders
        preferred_range = bot.get_preferred_range()

        # WALL COLLISION PRIORITY: Check for wall collision FIRST!
        # This takes precedence over all other movement decisions.
        against_wall, walls_hit = self._is_against_wall(bot)

        # Update wall escape timer
        if bot.wall_escape_timer > 0:
            bot.wall_escape_timer -= self.dt

        if against_wall or bot.wall_escape_timer > 0:
            # We're against a wall or recently hit one - need to escape!
            if against_wall:
                escape_angle, escape_speed = self._get_wall_escape_vector(bot, walls_hit)

                # Blend escape direction with target direction for smarter movement
                # Move along the wall towards the target rather than just straight away
                if distance < preferred_range:
                    # If target is close, prioritize wall escape to prevent pointing back at wall
                    # 70% escape angle, 30% retreat angle
                    retreat_angle = (target_angle + 180) % 360
                    blend_angle = (escape_angle * 0.7 + retreat_angle * 0.3) % 360
                    return blend_angle, escape_speed
                else:
                    # Calculate a direction that moves away from wall but toward target
                    angle_to_target = target_angle

                    # Check if normal movement would go into the wall
                    if self._is_moving_towards_wall(bot, angle_to_target, walls_hit):
                        # Blend escape with strafe - move along wall toward target
                        strafe_component = 45 * bot.strafe_direction
                        blended_angle = (escape_angle + strafe_component) % 360
                        return blended_angle, 0.8
                    # Otherwise, proceed with normal movement (target is accessible)

        # DISPERSAL MODE: Highest priority override when corner-locked!
        # Forces bots to spread apart when they're clustered and can't shoot.
        if self.dispersal_mode:
            return self._get_dispersal_direction(bot)

        # =========================================================================
        # FLEE MODE - DIRECT RETREAT WHEN INSIDE MIN_RANGE
        # No fancy maneuvering - just get out FAST. Strafing slows down escape.
        # =========================================================================
        if distance < bot.min_range * 0.95:  # Small buffer to prevent jitter
            # Direct retreat - no strafe offset
            retreat_angle = (target_angle + 180) % 360

            # Urgency scales with how deep inside min_range we are
            urgency = 1.0 - (distance / bot.min_range)  # 0-1, higher = more urgent
            speed = 0.9 + (0.1 * urgency)  # 0.9 to 1.0

            return retreat_angle, speed

        # =========================================================================
        # TOO FAR - outside maximum range (except HOLD stance which stays put)
        # =========================================================================
        if distance > bot.max_range * 1.05 and bot.behavior != AIBehavior.HOLD:
            # Approach target to get in range
            approach_angle = target_angle

            # Add slight strafe to approach at angle (more interesting)
            strafe_offset = 15 * bot.strafe_direction
            final_angle = (approach_angle + strafe_offset) % 360

            # Speed based on how far out of range
            overshoot = (distance - bot.max_range) / bot.max_range  # How far past max
            speed = min(1.0, 0.6 + (0.4 * overshoot))  # 0.6 to 1.0

            # Apply archetype modifier - long-range weapons advance slower
            # SNIPER/RIFLE need time to reposition, so they don't rush in aggressively
            if bot.weapon_archetype in ("SNIPER", "RIFLE"):
                speed *= 0.85  # -15% forward speed for long-range weapons
            # Note: BRAWLER and SKIRMISHER use normal approach speed

            return final_angle, speed

        # STALEMATE MODE: Force engagement with ASYMMETRIC behavior!
        # Team 1 charges aggressively, Team 2 holds ground - breaks the symmetric dance.
        if self.stalemate_mode:
            if bot.team == 1:
                # Team 1: CHARGE! Direct approach with minimal angle
                if distance > bot.min_range * 1.1:
                    return (target_angle + 5 * bot.strafe_direction) % 360, 1.0
                else:
                    # Inside min range - orbit to get out
                    return (target_angle + 70 * bot.strafe_direction) % 360, 0.9
            else:
                # Team 2: HOLD GROUND and let them come to us
                if distance < bot.min_range:
                    # Too close - retreat
                    return (target_angle + 180) % 360, 0.8
                elif distance > bot.max_range:
                    # Out of range - close in but slowly
                    return target_angle, 0.5
                else:
                    # In range - slow strafe, let team 1 close
                    return (target_angle + 40 * bot.strafe_direction) % 360, 0.4

        # =========================================================================
        # HOLD BEHAVIOR - STATIONARY TURRET
        # Stay COMPLETELY STILL, only rotate to track target
        # Zero forward/backward movement, act as a sniper turret
        # =========================================================================
        if bot.behavior == AIBehavior.HOLD:
            if distance > bot.max_range * 1.1:
                # Significantly out of range - very slowly inch forward
                return target_angle, 0.08
            elif distance < bot.min_range * 0.85:
                # Inside minimum range - back up slowly
                return (target_angle + 180) % 360, 0.1
            else:
                # IN RANGE - STAY COMPLETELY STILL
                # Only face the target, zero movement speed
                return target_angle, 0.0  # ZERO movement!

        # =========================================================================
        # KITING BEHAVIOR - CONSTANT BACKWARD MOVEMENT
        # Attack while ALWAYS moving backward, never stop, circle while retreating
        # =========================================================================
        if bot.behavior == AIBehavior.KITING:
            if distance > bot.max_range:
                # Out of range - approach at angle, but still evasive
                return (target_angle + 30 * bot.strafe_direction) % 360, 0.9
            elif distance < preferred_range * 0.7:
                # WAY too close! Full speed retreat!
                return (target_angle + 180 + (15 * bot.strafe_direction)) % 360, 1.0
            elif distance < preferred_range * 0.85:
                # Too close - back away quickly while circling
                return (target_angle + 180 + (30 * bot.strafe_direction)) % 360, 0.95
            elif distance < preferred_range:
                # Slightly too close - constant backward movement
                return (target_angle + 180 + (40 * bot.strafe_direction)) % 360, 0.9
            else:
                # At preferred range - STILL move backward while circling
                # Never stop moving! Orbit while maintaining distance
                return (target_angle + 180 + (55 * bot.strafe_direction)) % 360, 0.85

        # =========================================================================
        # AGGRESSIVE BEHAVIOR - SMART AGGRESSION
        # Charge at enemies but maintain optimal combat range (just outside min_range).
        # Key insight: Being inside min_range is bad for EVERYONE, including aggressors.
        # Smart aggressive bots stay at the edge of their firing range, not inside it.
        # =========================================================================
        if bot.behavior == AIBehavior.AGGRESSIVE:
            # Check if target is against a wall - don't pin them there
            target_against_wall, _ = self._is_against_wall(target)

            # Optimal range is just outside min_range - maximum pressure while still shooting
            optimal_close_range = bot.min_range * 1.15 if bot.min_range > 0 else preferred_range * 0.3

            if distance > bot.max_range:
                # Out of range - CHARGE at full speed with slight angle
                return (target_angle + 10 * bot.strafe_direction) % 360, 1.0
            elif distance > preferred_range:
                # In range but not close enough - approach aggressively
                return (target_angle + 8 * bot.strafe_direction) % 360, 0.95
            elif distance < optimal_close_range:
                # Too close! Back up to optimal range while circling
                # This prevents the corner-lock situation
                retreat_angle = (target_angle + 180 + 40 * bot.strafe_direction) % 360
                return retreat_angle, 0.8
            elif target_against_wall and distance < preferred_range * 0.7:
                # Target is cornered - orbit instead of pushing further
                # This prevents pinning enemies and causing stalemate
                return (target_angle + 75 * bot.strafe_direction) % 360, 0.85
            else:
                # Perfect aggressive range - circle tightly while maintaining pressure
                # Stay mobile to avoid being an easy target
                return (target_angle + 25 * bot.strafe_direction) % 360, 0.8

        # =========================================================================
        # DEFENSIVE BEHAVIOR - MAXIMUM RANGE MAINTENANCE
        # ALWAYS retreat when enemies approach, maintain MAX weapon range
        # Wide strafing patterns, prioritize evasion over damage
        # =========================================================================
        elif bot.behavior == AIBehavior.DEFENSIVE:
            # Check for wall proximity - affects retreat strategy
            against_wall, walls_hit = self._is_against_wall(bot)

            if against_wall:
                # At wall - can't retreat! Prioritize lateral evasion
                if distance < bot.min_range * 0.9:
                    # Too close AND at wall - desperate strafe along wall
                    escape_angle, _ = self._get_wall_escape_vector(bot, walls_hit)
                    lateral_angle = (escape_angle + 80 * bot.strafe_direction) % 360
                    return lateral_angle, 1.0
                elif distance < preferred_range * 0.8:
                    # Enemy too close at wall - fast lateral movement
                    escape_angle, _ = self._get_wall_escape_vector(bot, walls_hit)
                    lateral_angle = (escape_angle + 75 * bot.strafe_direction) % 360
                    return lateral_angle, 0.95
                else:
                    # Good range at wall - wide strafe along wall
                    escape_angle, _ = self._get_wall_escape_vector(bot, walls_hit)
                    lateral_angle = (escape_angle + 90 * bot.strafe_direction) % 360
                    return lateral_angle, 0.75

            # Normal defensive behavior - RETREAT PRIORITY!
            if distance < preferred_range * 0.6:
                # Enemy WAY too close - FULL SPEED RETREAT!
                retreat_angle = (target_angle + 175 + (5 * bot.strafe_direction)) % 360
                if self._is_moving_towards_wall(bot, retreat_angle, walls_hit):
                    return (target_angle + 90 * bot.strafe_direction) % 360, 1.0
                return retreat_angle, 1.0
            elif distance < preferred_range * 0.8:
                # Enemy approaching - fast retreat with evasion
                retreat_angle = (target_angle + 165 * bot.strafe_direction) % 360
                if self._is_moving_towards_wall(bot, retreat_angle, walls_hit):
                    return (target_angle + 95 * bot.strafe_direction) % 360, 0.95
                return retreat_angle, 0.95
            elif distance < preferred_range:
                # Slightly too close - back away with wide strafe
                retreat_angle = (target_angle + 155 * bot.strafe_direction) % 360
                if self._is_moving_towards_wall(bot, retreat_angle, walls_hit):
                    return (target_angle + 90 * bot.strafe_direction) % 360, 0.85
                return retreat_angle, 0.9
            elif distance > bot.max_range * 1.1:
                # Out of range - carefully approach at wide angle
                return (target_angle + 35 * bot.strafe_direction) % 360, 0.5
            else:
                # At preferred max range - evasive strafing with slight convergence
                return (target_angle + 75 * bot.strafe_direction) % 360, 0.7

        # =========================================================================
        # FLANKING BEHAVIOR - CONSTANT PERPENDICULAR CIRCLING
        # High speed lateral movement, orbit enemies at medium range
        # Never approach head-on, always circling
        # =========================================================================
        elif bot.behavior == AIBehavior.FLANKER:
            if distance > bot.max_range:
                # Out of range - approach at SHARP angle (flank approach)
                return (target_angle + 55 * bot.strafe_direction) % 360, 1.0
            elif distance < bot.min_range * 0.85:
                # Too close - spiral outward fast
                return (target_angle + 110 * bot.strafe_direction) % 360, 0.95
            elif distance < preferred_range * 0.7:
                # Inside preferred - circle outward (slightly retreating orbit)
                return (target_angle + 100 * bot.strafe_direction) % 360, 0.95
            elif distance > preferred_range * 1.2:
                # Outside preferred - spiral inward faster with 70-75 degree angle
                return (target_angle + 73 * bot.strafe_direction) % 360, 0.95
            else:
                # PERFECT flanking range - spiral inward with 70 degree angle
                # Creates meaningful convergence instead of near-infinite orbit
                return (target_angle + 70 * bot.strafe_direction) % 360, 1.0

        # =========================================================================
        # SNIPER BEHAVIOR - MAXIMUM RANGE, MINIMAL MOVEMENT
        # Stay at absolute max range, very slow deliberate movement
        # =========================================================================
        elif bot.behavior == AIBehavior.SNIPER:
            if distance < preferred_range * 0.7:
                # Way too close - retreat urgently
                return (target_angle + 178) % 360, 0.85
            elif distance < preferred_range * 0.85:
                # Too close - back away
                return (target_angle + 175 * bot.strafe_direction) % 360, 0.7
            elif distance > bot.max_range * 1.05:
                # Out of range - approach cautiously, minimal angle
                return target_angle, 0.4
            else:
                # Good sniper range - allow repositioning to avoid becoming sitting duck
                # Changed from 0.1 to 0.35 to maintain some mobility
                return (target_angle + 90 * bot.strafe_direction) % 360, 0.35

        # =========================================================================
        # BERSERKER BEHAVIOR - ERRATIC, UNPREDICTABLE, CHARGING
        # Wild movement, random direction changes, always aggressive
        # =========================================================================
        elif bot.behavior == AIBehavior.BERSERKER:
            erratic_offset = random.uniform(-50, 50)
            if distance > bot.max_range:
                # Wild charge! With some randomness
                return (target_angle + erratic_offset * 0.4) % 360, 1.0
            elif distance < bot.min_range * 0.75:
                # Even berserkers back up when too close - sometimes
                if random.random() < 0.25:
                    return (target_angle + 180 + erratic_offset) % 360, 0.75
                return (target_angle + 80 * bot.strafe_direction + erratic_offset) % 360, 0.95
            else:
                # In range - mostly aggressive with random bursts
                action = random.random()
                if action < 0.45:
                    # Charge closer!
                    return (target_angle + erratic_offset * 0.25) % 360, 1.0
                elif action < 0.75:
                    # Wild strafe
                    return (target_angle + 70 * bot.strafe_direction + erratic_offset) % 360, 0.9
                else:
                    # Random direction burst
                    return (target_angle + random.uniform(-100, 100)) % 360, 1.0

        # =========================================================================
        # TACTICAL BEHAVIOR - BALANCED, SMART MOVEMENT
        # Medium range, moderate strafing, balanced approach
        # =========================================================================
        else:
            if distance > bot.max_range:
                # Advance to get in range
                return (target_angle + 20 * bot.strafe_direction) % 360, 0.85
            elif distance < bot.min_range * 0.9:
                # Too close - retreat
                return (target_angle + 170 * bot.strafe_direction) % 360, 0.8
            elif distance < preferred_range * 0.8:
                # Inside preferred - back out while strafing
                return (target_angle + 130 * bot.strafe_direction) % 360, 0.75
            elif distance > preferred_range * 1.2:
                # Outside preferred - close in while strafing
                return (target_angle + 40 * bot.strafe_direction) % 360, 0.75
            else:
                # Perfect range - active strafe with inward pressure
                return (target_angle + 65 * bot.strafe_direction) % 360, 0.7

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
            # No ally to protect - fall back to defensive movement near center
            self._execute_agile_movement(bot, target)
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
            # Small random strafe to not be a sitting duck
            strafe_angle = (target_angle + 15 * bot.strafe_direction) % 360
            self._rotate_chassis_towards(bot, strafe_angle, speed_mult=0.3)
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

    def _execute_agile_movement(self, bot: BotRuntimeState, target: BotRuntimeState):
        """
        Execute agility-based movement - bots can turn while moving based on their agility stat.

        High agility (0.8-1.0): Can turn almost freely while moving at speed
        Medium agility (0.5-0.7): Must slow down moderately to turn
        Low agility (0.2-0.4): Must slow down significantly to turn
        Very low agility (0.0-0.2): Must nearly stop to turn (heavy tanks)
        """
        desired_dir, speed_mult = self._calculate_desired_direction(bot, target)

        if speed_mult <= 0:
            # No movement desired, just rotate chassis toward target
            target_angle = bot.position.angle_to(target.position)
            self._rotate_chassis_towards(bot, target_angle, speed_mult=0.5)
            bot.is_turning = False
            return

        # Set target orientation for movement
        bot.target_orientation = desired_dir

        # Check angle difference between current orientation and desired movement direction
        angle_diff = abs((desired_dir - bot.orientation + 180) % 360 - 180)

        # Calculate movement speed based on angle difference and agility
        # High agility = less speed penalty for turning
        # angle_penalty: 0 when aligned, 1 when perpendicular (90 degrees), higher when facing away
        angle_penalty = min(1.0, angle_diff / 90.0)

        # Agility reduces the penalty: high agility means less slowdown
        # With agility 1.0: no slowdown from turning
        # With agility 0.0: full slowdown (proportional to angle)
        effective_speed_mult = speed_mult * (1.0 - angle_penalty * (1.0 - bot.agility))

        # Minimum speed threshold - if speed is too low, bot appears to "shuffle"
        min_move_speed = 0.25  # Always move at least 25% speed

        # For very low agility bots facing the wrong way, they need to mostly stop
        if bot.agility < 0.3 and angle_diff > 60:
            # Heavy tanks must slow way down for big turns
            effective_speed_mult = speed_mult * 0.15
            bot.is_turning = True
        elif angle_diff > 120:
            # Facing mostly backwards - even agile bots slow down significantly
            effective_speed_mult = speed_mult * max(0.2, bot.agility * 0.5)
            bot.is_turning = True
        else:
            bot.is_turning = angle_diff > 30

        # Apply minimum speed to keep things moving (unless completely wrong direction)
        if angle_diff < 120:
            effective_speed_mult = max(min_move_speed, effective_speed_mult)

        # Always rotate toward desired direction (faster when moving slower)
        turn_speed_mult = 1.0 + (1.0 - effective_speed_mult) * 0.5  # Turn faster when moving slower
        self._rotate_chassis_towards(bot, desired_dir, speed_mult=turn_speed_mult)

        # Move in current facing direction (not desired direction)
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
                            self.stalemate_mode = False
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
                        self.stalemate_mode = False
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
