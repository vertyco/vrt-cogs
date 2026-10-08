"""
Bot Arena - Real-Time Battle Engine

This module contains the physics simulation for real-time bot combat.
It simulates continuous movement, rotation, and combat at a fixed timestep.

Range Scaling:
    Original BA3 weapon ranges (25-220) are designed for a smaller arena scale.
    We scale these to our 1000x1000 arena using RANGE_SCALE_FACTOR.
    This ensures weapons have meaningful engagement distances.

Collision Detection:
    Projectiles hit the actual plating pixels (see collision.py) and are swept along
    their whole path each tick, so fast shots can't skip through a hull between frames.
    A circular hitbox is only used for a plating without an image.

Movement:
    Bots drive like tanks: they accelerate and brake along their chassis heading (forward,
    or slower in reverse), slide around each other on contact, and slide along the arena walls.

AI:
    ai.py decides who each bot shoots, where it stands and where it aims; this module
    carries that out with physics.
"""

import math
import random
import typing as t
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from .collision import CollisionManager

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
SPLASH_DAMAGE_FRACTION = 0.5  # Share of a splash weapon's hit damage dealt to other enemies in the blast

# Drive train, as multiples of a bot's top speed per second (3.0 = full speed in a third of a second)
ACCELERATION = 3.0
BRAKING = 5.0
# Longest step a projectile takes between collision checks, so fast shots can't skip over a thin hull edge
PROJECTILE_SWEEP_STEP = 6.0
# Weapons that can fire point-blank never miss a target whose center is this close (melee weapon reach)
POINT_BLANK_REACH = 92.0
# Top speed in reverse, as a share of forward top speed
REVERSE_SPEED = 0.6
# Seconds quicker the other gear must be before a bot changes between forward and reverse
GEAR_HYSTERESIS = 0.4
# Turn rate every chassis gets on top of its own (degrees per second), so even heavy tanks can react
ROTATION_BOOST = 4.0
# Extra degrees a shot can stray when the shooter crosses its line of fire at full speed (scaled by
# how fast it moves sideways to its target; driving straight at or away from it doesn't throw off aim)
MOVING_SPREAD = 18.0
# Projectile speed per type, as multiples of BattleConfig.projectile_speed
PROJECTILE_SPEEDS = {
    "laser": 2.0,  # Very fast
    "cannon": 0.5,  # Slow, heavy shells a side-on bot can roll out of the way of
    "missile": 0.6,  # Slow too, but splashes
    "bullet": 1.0,
    "heal": 1.8,  # Fast, so it catches moving allies
    "shockwave": 2.5,  # Very fast close-range burst
}


class AIBehavior(str, Enum):
    """Movement stance (see ai.py for how each one weighs where to stand)"""

    AGGRESSIVE = "aggressive"  # Charge in nose-first, get under long weapons' minimum range, hold ground
    DEFENSIVE = "defensive"  # Stay just out of the enemy's reach, plant to shoot, turn and run when chased
    TACTICAL = "tactical"  # Side-on strafing at mid range, flank, sidestep slow shots


class TargetPriority(str, Enum):
    """Who a bot shoots (see ai.py)"""

    FOCUS_FIRE = "focus_fire"  # The team agrees on the enemy it can kill fastest together
    WEAKEST = "weakest"  # Whoever this weapon can finish soonest
    CLOSEST = "closest"  # Whoever it can shoot soonest, preferring whoever shoots it (default)
    SUPPORT_FIRST = "support_first"  # Healers first, then the hardest hitter


# Default behaviors for chassis types (used when no tactical orders given)
# Based on original Bot Arena 3 chassis characteristics
DEFAULT_CHASSIS_BEHAVIORS = {
    # Light chassis - fast and agile
    "DLZ-100": AIBehavior.TACTICAL,  # Starter chassis, good all-rounder
    "DLZ-250": AIBehavior.AGGRESSIVE,  # Upgraded light, more aggressive
    # Medium chassis - balanced
    "Smartmove": AIBehavior.TACTICAL,  # Smart AI chassis
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
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Vector2":
        mag = self.magnitude()
        if mag == 0:
            return Vector2(0, 0)
        return Vector2(self.x / mag, self.y / mag)

    def distance_to(self, other: "Vector2") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

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


def distance_to_segment(point: Vector2, start: Vector2, end: Vector2) -> float:
    """Shortest distance from a point to the line segment start-end."""
    dx = end.x - start.x
    dy = end.y - start.y
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return point.distance_to(start)
    t_along = max(0.0, min(1.0, ((point.x - start.x) * dx + (point.y - start.y) * dy) / length_sq))
    return math.hypot(point.x - (start.x + t_along * dx), point.y - (start.y + t_along * dy))


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
    muzzle_offset: float = 92.0  # Distance from the turret pivot to the barrel tip (for projectile spawn)
    turret_offset_x: float = 0.0  # Turret pivot offset from the bot center, before the chassis turns
    turret_offset_y: float = 0.0
    spread: float = 0.0  # Most degrees a shot can stray from the turret direction
    splash_radius: float = 0.0  # Blast reach (to enemy hulls) when a shot hits an enemy

    # AI behavior (derived from tactical orders or chassis default)
    behavior: AIBehavior = AIBehavior.TACTICAL

    # Tactical orders from player
    target_priority: TargetPriority = TargetPriority.CLOSEST

    # Chassis agility (0.0-1.0) - how well the bot can turn while moving
    # 0.0 = must completely stop to turn, 1.0 = can turn at full speed
    agility: float = 0.5

    # Runtime state
    position: Vector2 = field(default_factory=Vector2)
    velocity: Vector2 = field(default_factory=Vector2)  # How far the bot actually moved last tick, per second
    current_speed: float = 0.0  # Speed along the chassis heading, negative in reverse (see ACCELERATION/BRAKING)
    gear: int = 1  # 1 = driving forward, -1 = reversing
    orientation: float = 0.0  # Chassis facing direction (degrees, 0 = right, 90 = down)
    weapon_orientation: float = 0.0  # Weapon turret facing direction (independent of chassis)
    is_turning: bool = False  # Whether the chassis is still swinging round to its travel direction
    health: int = 0
    is_alive: bool = True
    last_shot_time: float = 0.0
    target_id: t.Optional[str] = None  # Who it's after (who it maneuvers against)
    fire_id: t.Optional[str] = None  # Who its turret is on (its target, or an enemy in reach meanwhile)
    # Velocity over the last few ticks, newest last (shooters read it, a slow chassis a few ticks late)
    track: deque = field(default_factory=lambda: deque(maxlen=20))

    # AI plan (see ai.py)
    plan_timer: float = 0.0  # Seconds until the bot re-plans its target and spot
    move_goal: t.Optional[Vector2] = None  # The spot it's driving to
    escort_id: t.Optional[str] = None  # The ally a healer is shadowing
    retreating: bool = False  # Falling back to a healer
    lead: float = 1.0  # Share of the needed lead it gives its shots
    aim_point: t.Optional[Vector2] = None  # Where the turret is pointing
    strafe_dir: int = 1  # Tactical strafing direction around its spot
    strafe_timer: float = 0.0  # Seconds until it next switches strafing direction
    shot_at_time: float = -1.0  # When an enemy last fired a projectile at it
    shot_noticed: float = -1.0  # The last such shot it reacted to
    dodge_until: float = 0.0  # Sidestepping an incoming shot until then
    dodge_dir: int = 1  # Rolling forward (1) or back (-1) to sidestep

    # Steering for this tick, set by the AI and carried out by the engine
    move_heading: t.Optional[float] = None  # Direction to travel (degrees), None to hold still
    move_throttle: float = 0.0  # Share of top speed
    move_distance: float = 0.0  # How far it has left to go that way
    move_horizon: float = 0.0  # How far it expects to keep going that way (picks forward or reverse gear)
    face_angle: t.Optional[float] = None  # Heading to turn toward while holding still

    # Who has been hurting this bot (Closest targeting prefers them)
    threat_map: dict[str, ThreatEntry] = field(default_factory=dict)  # enemy_id -> threat info

    # Statistics
    damage_dealt: int = 0
    damage_taken: int = 0
    healing_done: int = 0
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
    splash_radius: float = 0.0  # Blast reach applied when this shot hits an enemy
    age: float = 0.0  # Seconds since it was fired

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
            "age": self.age,
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
    seed: t.Optional[int] = None  # RNG seed for reproducible battles (None = random)


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
        # Dedicated RNG instance for deterministic, reproducible battles
        self.seed: int = self.config.seed if self.config.seed is not None else random.randrange(2**32)
        self.rng = random.Random(self.seed)
        self.bots: dict[str, BotRuntimeState] = {}
        self.projectiles: list[Projectile] = []
        self.frames: list[FrameData] = []
        self.current_time: float = 0.0
        self.frame_number: int = 0
        self.dt: float = 1.0 / self.config.fps
        self.events: list[dict] = []  # Events for current frame

        self.last_damage_time: float = 0.0  # For stalemate detection

        # Pixel-perfect collision detection against each bot's plating
        self.collision_manager = CollisionManager()
        # How far each bot's hull reaches, so touching bots stop where their platings meet
        self.hull_radii: dict[str, float] = {}

        # Imported here because ai.py builds on this module's types
        from .ai import BattleAI

        self.ai = BattleAI(self)

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
        spread: float = 0.0,
        splash_radius: float = 0.0,
        turret_offset: tuple[float, float] = (0.0, 0.0),
    ):
        """Add a bot to the simulation.

        Args:
            min_range: Minimum weapon range (will be scaled by RANGE_SCALE_FACTOR)
            max_range: Maximum weapon range (will be scaled by RANGE_SCALE_FACTOR)
            behavior: AI movement behavior (from tactical orders or chassis default)
            target_priority: Who to target (from tactical orders)
            projectile_type: Visual type of projectile (bullet, laser, cannon, missile, heal)
            muzzle_offset: Distance from the turret pivot to the barrel tip (for projectile spawn point)
            turret_offset: Turret pivot offset from the bot center while the chassis faces right
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
            turret_offset_x=turret_offset[0],
            turret_offset_y=turret_offset[1],
            spread=spread,
            splash_radius=splash_radius,
            health=max_health,
            behavior=behavior,
            target_priority=target_priority or TargetPriority.CLOSEST,
            agility=max(0.0, min(1.0, agility)),  # Clamp to 0-1
        )
        self.bots[bot_id] = state

        # Register collision mask for pixel-perfect collision detection (plating shape)
        self.collision_manager.register_bot(bot_id, plating_name, component_name)
        self.hull_radii[bot_id] = self.collision_manager.hull_radius(bot_id) or self.config.bot_radius

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

        # Team 2 starts at bottom, facing up
        if team2:
            spacing = self.config.arena_width / (len(team2) + 1)
            for i, bot in enumerate(team2):
                bot.position = Vector2((i + 1) * spacing, self.config.arena_height - spawn_y_offset)
                bot.orientation = 270
                bot.weapon_orientation = 270

    def run(self) -> dict:
        """
        Run the complete battle simulation.

        Returns a dict with battle results and frame data.
        """
        self.setup_positions()
        self.ai.setup()
        self.current_time = 0.0
        self.frame_number = 0

        max_frames = int(self.config.max_duration * self.config.fps)

        while self.frame_number < max_frames:
            self.step()

            # Check for battle end
            if self._check_battle_end():
                break

            self.current_time += self.dt
            self.frame_number += 1

        return self._build_result()

    def step(self):
        """Advance every system by one tick and capture the frame."""
        self.events = []
        self.ai.update()  # Targets, spots, steering and aim
        self._update_movement()
        self._update_weapon_orientation()
        self._update_projectiles()
        self._update_combat()
        self._capture_frame()

    def stalemate_pressure(self) -> float:
        """How long the fight has gone without damage, from 0.0 (normal) to 1.0 (force engagement).

        The AI closes ranges and drops its caution as this rises, so standoffs can't last forever.
        """
        time_without_damage = self.current_time - self.last_damage_time

        if time_without_damage < self.STALEMATE_WARNING_TIME:
            return 0.0

        # Ramp up aggression between warning and force time
        progress = (time_without_damage - self.STALEMATE_WARNING_TIME) / (
            self.STALEMATE_FORCE_TIME - self.STALEMATE_WARNING_TIME
        )
        return min(1.0, progress)

    def projectile_speed(self, bot: BotRuntimeState) -> float:
        return self.config.projectile_speed * PROJECTILE_SPEEDS.get(bot.projectile_type, 1.0)

    def _update_movement(self):
        """Carry out each bot's steering from the AI: turn the chassis and drive."""
        for bot in self.bots.values():
            if not bot.is_alive:
                continue
            if bot.move_heading is None:
                if bot.face_angle is not None:
                    self._rotate_chassis_towards(bot, bot.face_angle)
                bot.is_turning = False
                self._drive(bot, 0.0)
            else:
                self._drive_toward(bot, bot.move_heading, bot.move_throttle, bot.move_distance, bot.move_horizon)
            bot.track.append(bot.velocity)

    def _drive_toward(self, bot: BotRuntimeState, heading: float, throttle: float, distance: float, horizon: float):
        """Travel `distance` along `heading`, nose-first or in reverse, whichever covers `horizon` sooner.

        Reversing is slower but needs no turn, so a bot backs a short way off an enemy while keeping
        its nose toward it, and a side-on bot jinks by rolling forward and back.
        """
        rotation = bot.rotation_speed + ROTATION_BOOST
        forward_turn = abs((heading - bot.orientation + 180) % 360 - 180)
        forward_time = forward_turn / rotation + horizon / max(1.0, bot.speed)
        reverse_time = (180 - forward_turn) / rotation + horizon / max(1.0, bot.speed * REVERSE_SPEED)
        # Stay in the current gear unless the other is clearly quicker, so it doesn't dither
        if bot.gear > 0:
            reverse = reverse_time + GEAR_HYSTERESIS < forward_time
        else:
            reverse = reverse_time < forward_time + GEAR_HYSTERESIS
        bot.gear = -1 if reverse else 1

        facing = (heading + 180) % 360 if reverse else heading
        self._rotate_chassis_towards(bot, facing)
        off = abs((facing - bot.orientation + 180) % 360 - 180)
        bot.is_turning = off > 30

        # Agile chassis keep their speed through a turn, sluggish ones slow down for it
        speed_mult = throttle * max(0.25 if off < 75 else 0.1, 1.0 - min(1.0, off / 90.0) * (1.0 - bot.agility))
        # Ease off on arrival so the bot brakes onto its spot instead of overshooting it
        speed_mult = min(speed_mult, self._arrival_speed_mult(bot, distance))
        self._drive(bot, -speed_mult * REVERSE_SPEED if reverse else speed_mult)

    def _update_weapon_orientation(self):
        """Swing each turret toward its aim point (or along the chassis with nothing to shoot)."""
        for bot in self.bots.values():
            if not bot.is_alive:
                continue
            if bot.aim_point is None:
                self._rotate_weapon_towards(bot, bot.orientation)
            else:
                self._rotate_weapon_towards(bot, self._turret_pivot(bot).angle_to(bot.aim_point))

    def _rotate_weapon_towards(self, bot: BotRuntimeState, target_angle: float):
        """Rotate the turret toward an angle at its own rate (independent of the chassis)."""
        angle_diff = (target_angle - bot.weapon_orientation + 180) % 360 - 180
        max_rotation = bot.turret_rotation_speed * self.dt
        if abs(angle_diff) <= max_rotation:
            bot.weapon_orientation = target_angle
        elif angle_diff > 0:
            bot.weapon_orientation = (bot.weapon_orientation + max_rotation) % 360
        else:
            bot.weapon_orientation = (bot.weapon_orientation - max_rotation) % 360

    def _rotate_chassis_towards(self, bot: BotRuntimeState, target_angle: float, speed_mult: float = 1.0):
        """Rotate chassis towards target angle (every chassis gets ROTATION_BOOST on top of its own rate)."""
        angle_diff = (target_angle - bot.orientation + 360) % 360
        if angle_diff > 180:
            angle_diff -= 360

        max_rotation = (bot.rotation_speed + ROTATION_BOOST) * self.dt * speed_mult
        if abs(angle_diff) <= max_rotation:
            bot.orientation = target_angle
        elif angle_diff > 0:
            bot.orientation = (bot.orientation + max_rotation) % 360
        else:
            bot.orientation = (bot.orientation - max_rotation) % 360

    def _arrival_speed_mult(self, bot: BotRuntimeState, distance: float) -> float:
        """Top-speed fraction that still lets the bot brake to a stop within `distance`."""
        if bot.speed <= 0:
            return 0.0
        return min(1.0, math.sqrt(2.0 * bot.speed * BRAKING * distance) / bot.speed)

    def _drive(self, bot: BotRuntimeState, speed_mult: float):
        """Speed up or brake toward a fraction of top speed (negative reverses), then roll along the chassis heading.

        Speed changes are rate-limited (ACCELERATION/BRAKING) so bots ease into motion and
        coast to a stop instead of snapping between full speed and standing still.
        """
        target_speed = bot.speed * max(-REVERSE_SPEED, min(1.0, speed_mult))
        speeding_up = abs(target_speed) > abs(bot.current_speed) and target_speed * bot.current_speed >= 0
        rate = bot.speed * (ACCELERATION if speeding_up else BRAKING) * self.dt
        bot.current_speed += max(-rate, min(rate, target_speed - bot.current_speed))
        if abs(bot.current_speed) < 1e-6:
            bot.current_speed = 0.0
            bot.velocity = Vector2(0, 0)
            return

        rad = math.radians(bot.orientation)
        move_vec = Vector2(math.cos(rad), math.sin(rad)) * (bot.current_speed * self.dt)
        self._apply_movement(bot, move_vec)

    def _contact_distance(self, bot: BotRuntimeState, other: BotRuntimeState) -> float:
        """How close two bots' centers can get before their platings touch."""
        radii = self.hull_radii.get(bot.bot_id, self.config.bot_radius) + self.hull_radii.get(
            other.bot_id, self.config.bot_radius
        )
        # Kept inside the minimum weapon range floor (see add_bot) so a bot hugging an enemy still sits in
        # its dead zone, and never closer than the original fixed spacing
        return max(self.config.bot_radius * 2.2, min(radii, self.config.bot_radius * 2.5 - 2.0))

    def _bot_overlap(self, bot: BotRuntimeState, pos: Vector2) -> float:
        """How deep a bot standing at `pos` would sink into the closest other bot (0 when clear)."""
        deepest = 0.0
        for other in self.bots.values():
            if other.bot_id != bot.bot_id and other.is_alive:
                deepest = max(deepest, self._contact_distance(bot, other) - pos.distance_to(other.position))
        return deepest

    def _apply_movement(self, bot: BotRuntimeState, move_vec: Vector2):
        """Move a bot, sliding along the arena walls and around other bots instead of stopping dead."""
        old_pos = bot.position
        step = move_vec.magnitude()
        heading = move_vec.normalized()

        # Bots slide around each other: drop the part of the move that pushes into a bot it touches
        for other in self.bots.values():
            if other.bot_id == bot.bot_id or not other.is_alive:
                continue
            offset = old_pos + move_vec - other.position
            if offset.magnitude() >= self._contact_distance(bot, other):
                continue
            normal = offset.normalized() if offset.magnitude() > 0 else (old_pos - other.position).normalized()
            pushing_in = move_vec.dot(normal)
            if pushing_in < 0:
                move_vec = move_vec - normal * pushing_in
            if move_vec.magnitude() < step * 0.3:
                # Nearly head-on: veer around the side the bot is already leaning toward
                tangent = Vector2(-normal.y, normal.x)
                side = 1.0 if heading.dot(tangent) >= 0 else -1.0
                move_vec = move_vec + tangent * (side * step * 0.6)

        new_pos = old_pos + move_vec

        # Arena edge buffer - keeps bots away from the visual walls of the arena.
        # Clamping each axis on its own lets bots slide along a wall they drive into.
        arena_buffer = 40.0
        min_bound = self.config.bot_radius + arena_buffer
        max_x = self.config.arena_width - self.config.bot_radius - arena_buffer
        max_y = self.config.arena_height - self.config.bot_radius - arena_buffer
        new_pos.x = max(min_bound, min(max_x, new_pos.x))
        new_pos.y = max(min_bound, min(max_y, new_pos.y))

        # Never end a move sunk deeper into another bot than where it started
        if self._bot_overlap(bot, new_pos) > max(0.0, self._bot_overlap(bot, old_pos)) + 0.01:
            new_pos = old_pos

        moved = new_pos - old_pos
        bot.position = new_pos
        bot.velocity = moved * (1.0 / self.dt)
        # Scraping along a wall or another bot bleeds off speed
        bot.current_speed = math.copysign(min(abs(bot.current_speed), moved.magnitude() / self.dt), bot.current_speed)

    def lane_blocked(self, shooter: BotRuntimeState, start: Vector2, end: Vector2) -> bool:
        """Whether a teammate of `shooter` stands in the way of a shot from `start` toward `end`."""
        blocking_radius = self.config.bot_radius * 1.2
        reach = start.distance_to(end)
        for bot in self.bots.values():
            if not bot.is_alive or bot.bot_id == shooter.bot_id or bot.team != shooter.team:
                continue
            # Only teammates between the two points (not behind the target) are in the way
            if (
                start.distance_to(bot.position) < reach
                and distance_to_segment(bot.position, start, end) < blocking_radius
            ):
                return True
        return False

    def _update_projectiles(self):
        """Move projectiles, sweeping each one's path this tick for the first bot it touches"""
        for proj in self.projectiles:
            if not proj.alive:
                continue

            start = proj.position
            end = start + proj.velocity * self.dt
            # A fresh shot also checks its muzzle point, in case the barrel is already inside a hull
            hit_bot, impact = self.sweep_projectile(proj, start, end, include_start=proj.age == 0)
            proj.age += self.dt
            if hit_bot:
                proj.position = impact
                self.resolve_projectile_hit(proj, hit_bot)
                continue
            proj.position = end

            # Check if out of bounds
            if (
                proj.position.x < 0
                or proj.position.x > self.config.arena_width
                or proj.position.y < 0
                or proj.position.y > self.config.arena_height
            ):
                proj.alive = False

        self.projectiles = [p for p in self.projectiles if p.alive]

    def sweep_projectile(
        self, proj: Projectile, start: Vector2, end: Vector2, include_start: bool = False
    ) -> tuple[t.Optional[BotRuntimeState], Vector2]:
        """Find the first living bot (teammates included) a projectile touches between two points.

        Returns (bot, impact point), or (None, end) when the path is clear. Heal shots pass
        through enemies, so only teammates of the healer can stop them.
        """
        shooter = self.bots.get(proj.shooter_id)
        candidates = []
        for bot in self.bots.values():
            if not bot.is_alive or bot.bot_id == proj.shooter_id:
                continue
            if proj.is_heal and shooter is not None and bot.team != shooter.team:
                continue
            # Broad phase: skip bots whose hull can't reach the path at all
            reach = self.collision_manager.bounding_radius(bot.bot_id) or self.config.bot_radius
            if distance_to_segment(bot.position, start, end) <= reach:
                candidates.append(bot)
        if not candidates:
            return None, end

        path = end - start
        steps = max(1, math.ceil(path.magnitude() / PROJECTILE_SWEEP_STEP))
        for i in range(0 if include_start else 1, steps + 1):
            point = start + path * (i / steps)
            for bot in candidates:
                if self.point_touches_bot(point, bot):
                    return bot, point
        return None, end

    def point_touches_bot(self, point: Vector2, bot: BotRuntimeState) -> bool:
        """Pixel-perfect hull test when the plating has a mask, otherwise a circular hitbox."""
        collision = self.collision_manager.check_collision(
            point.x, point.y, bot.bot_id, bot.position.x, bot.position.y, bot.orientation
        )
        if collision is None:
            return point.distance_to(bot.position) < self.config.bot_radius
        return collision

    def resolve_projectile_hit(self, proj: Projectile, hit_bot: BotRuntimeState):
        """Apply a projectile that touched a bot: heal, friendly block, or enemy damage."""
        shooter = self.bots.get(proj.shooter_id)
        is_friendly_fire = shooter is not None and hit_bot.team == shooter.team

        if proj.is_heal:
            # Heal projectiles only heal teammates (intended or not) and pass through enemies
            if is_friendly_fire or hit_bot.bot_id == proj.target_id:
                self.apply_heal(proj.shooter_id, hit_bot, abs(proj.damage), impact=proj.position)
                proj.alive = False
            return

        if is_friendly_fire:
            self.absorb_blocked_shot(proj, hit_bot)
        else:
            self.deal_damage(proj.shooter_id, hit_bot, proj.damage, impact=proj.position)
            if proj.splash_radius > 0 and shooter is not None:
                self.explode(proj, shooter, hit_bot)
        proj.alive = False

    def explode(self, proj: Projectile, shooter: BotRuntimeState, primary: BotRuntimeState):
        """Splash part of the hit onto other enemies whose hull is within the blast."""
        splash_damage = int(proj.damage * SPLASH_DAMAGE_FRACTION)
        hits = 0
        for bot in list(self.bots.values()):
            if not bot.is_alive or bot.team == shooter.team or bot.bot_id == primary.bot_id:
                continue
            # Measured to the hull, not the center: bots never stand closer than ~70px apart
            if proj.position.distance_to(bot.position) - self.config.bot_radius <= proj.splash_radius:
                self.deal_damage(shooter.bot_id, bot, splash_damage, splash=True)
                hits += 1
        self.events.append(
            {
                "type": "splash",
                "shooter_id": shooter.bot_id,
                "hits": hits,
                "x": proj.position.x,
                "y": proj.position.y,
                "radius": proj.splash_radius,
            }
        )

    def absorb_blocked_shot(self, proj: Projectile, blocker: BotRuntimeState):
        """A teammate blocked the shot: it takes reduced friendly fire damage (25%)."""
        actual = blocker.take_damage(proj.damage // 4, source_id=proj.shooter_id, current_time=self.current_time)
        if actual > 0:
            self.last_damage_time = self.current_time
        self.events.append(
            {
                "type": "blocked",
                "shooter_id": proj.shooter_id,
                "blocker_id": blocker.bot_id,
                "target_id": proj.target_id,
                "damage": actual,
                "x": proj.position.x,
                "y": proj.position.y,
            }
        )
        # If the teammate died from the blocked shot, emit the same
        # kill event as the normal damage path so stats/render stay in sync
        if not blocker.is_alive:
            if proj.shooter_id in self.bots:
                self.bots[proj.shooter_id].kills += 1
            self.events.append(self._kill_event(proj.shooter_id, blocker))

    def deal_damage(
        self,
        shooter_id: str,
        victim: BotRuntimeState,
        amount: int,
        impact: t.Optional[Vector2] = None,
        splash: bool = False,
    ) -> int:
        """Damage an enemy, credit the shooter, and log the hit (and kill). Returns damage actually dealt.

        `impact` is where the shot touched the hull (the victim's center if unknown), and
        `splash` marks blast damage from a nearby explosion rather than a direct hit.
        """
        actual = victim.take_damage(amount, source_id=shooter_id, current_time=self.current_time)
        if actual > 0:
            self.last_damage_time = self.current_time
        shooter = self.bots.get(shooter_id)
        if shooter:
            shooter.damage_dealt += actual
        impact = impact or victim.position
        self.events.append(
            {
                "type": "hit",
                "shooter_id": shooter_id,
                "target_id": victim.bot_id,
                "damage": actual,
                "x": impact.x,
                "y": impact.y,
                "projectile_type": shooter.projectile_type if shooter else "bullet",
                "splash": splash,
            }
        )
        if actual > 0 and not victim.is_alive:
            if shooter:
                shooter.kills += 1
            self.events.append(self._kill_event(shooter_id, victim))
        return actual

    def apply_heal(
        self, healer_id: str, target: BotRuntimeState, amount: int, impact: t.Optional[Vector2] = None
    ) -> int:
        """Heal a teammate, credit the healer's healing, and log it. Returns the amount actually healed."""
        actual = target.heal(amount)
        healer = self.bots.get(healer_id)
        if healer:
            healer.healing_done += actual
        impact = impact or target.position
        self.events.append(
            {
                "type": "heal",
                "shooter_id": healer_id,
                "target_id": target.bot_id,
                "amount": actual,
                "x": impact.x,
                "y": impact.y,
            }
        )
        return actual

    def _kill_event(self, killer_id: str, victim: BotRuntimeState) -> dict:
        return {
            "type": "kill",
            "killer_id": killer_id,
            "victim_id": victim.bot_id,
            "x": victim.position.x,
            "y": victim.position.y,
        }

    def _turret_pivot(self, bot: BotRuntimeState) -> Vector2:
        """Where the turret sits on the turned chassis (its mount point moves as the chassis turns)."""
        rad = math.radians(bot.orientation)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        return Vector2(
            bot.position.x + bot.turret_offset_x * cos_a - bot.turret_offset_y * sin_a,
            bot.position.y + bot.turret_offset_x * sin_a + bot.turret_offset_y * cos_a,
        )

    def _update_combat(self):
        """Handle weapon firing"""
        for bot in self.bots.values():
            if not bot.is_alive:
                continue
            if not bot.fire_id or bot.fire_id not in self.bots:
                continue
            if not bot.can_shoot(self.current_time):
                continue

            target = self.bots[bot.fire_id]
            if not target.is_alive:
                continue

            # Check range
            distance = bot.position.distance_to(target.position)
            # Weapons with min_range=0 can shoot point-blank (bypass min_range check)
            if not bot.allows_point_blank and distance < bot.min_range:
                continue
            if distance > bot.max_range:
                continue

            # Only fire once the turret is on the aim point (the AI leads moving targets). The window
            # is the target's apparent size, plus a little slop for a less disciplined chassis
            pivot = self._turret_pivot(bot)
            aim = bot.aim_point or target.position
            aim_distance = max(1.0, pivot.distance_to(aim))
            hull = self.hull_radii.get(target.bot_id, self.config.bot_radius)
            tolerance = math.degrees(math.atan2(hull * 0.7, aim_distance)) + (1.0 - bot.intelligence / 10.0) * 6.0
            if abs((pivot.angle_to(aim) - bot.weapon_orientation + 180) % 360 - 180) > tolerance:
                continue

            # Don't shoot through teammates (healers want to hit them, so they skip this)
            if not bot.is_healer and self.lane_blocked(bot, pivot, aim):
                continue

            # Fire!
            bot.last_shot_time = self.current_time
            proj_speed = self.projectile_speed(bot)

            weapon_rad = math.radians(bot.weapon_orientation)
            direction = Vector2(math.cos(weapon_rad), math.sin(weapon_rad))

            # Spawn the projectile at the barrel tip: the turret pivot (which turns with the chassis)
            # plus muzzle_offset along the weapon's facing direction. Clamp the spawn distance so the
            # projectile never spawns past the target (a target inside the muzzle offset would
            # otherwise be impossible to hit)
            spawn_distance = min(bot.muzzle_offset, max(0.0, distance - 1.0))
            muzzle_pos = pivot + direction * spawn_distance
            shot_direction = direction

            # Point-blank weapons can't miss a target within reach (and the barrel would be inside it anyway)
            if bot.allows_point_blank and distance < max(bot.muzzle_offset, POINT_BLANK_REACH):
                # Direct hit - no projectile needed; the renderer shows the burst from the hit event
                if bot.is_healer:
                    self.apply_heal(bot.bot_id, target, abs(bot.damage_per_shot), impact=muzzle_pos)
                else:
                    self.deal_damage(bot.bot_id, target, bot.damage_per_shot, impact=muzzle_pos)
            else:
                # Normal projectile: the weapon's own spread (mostly near the middle), plus an even wobble
                # the faster the shooter crosses its line of fire
                sideways = abs(bot.velocity.x * direction.y - bot.velocity.y * direction.x)
                wobble = MOVING_SPREAD * min(1.0, sideways / max(1.0, bot.speed))
                if bot.spread > 0 or wobble > 0:
                    stray = self.rng.triangular(-bot.spread, bot.spread, 0) if bot.spread > 0 else 0.0
                    stray += self.rng.uniform(-wobble, wobble) if wobble > 0 else 0.0
                    shot_direction = Vector2(
                        math.cos(math.radians(bot.weapon_orientation + stray)),
                        math.sin(math.radians(bot.weapon_orientation + stray)),
                    )
                if not bot.is_healer:
                    target.shot_at_time = self.current_time  # The target may notice and jink
                proj = Projectile(
                    shooter_id=bot.bot_id,
                    target_id=target.bot_id,
                    position=muzzle_pos,
                    velocity=shot_direction * proj_speed,
                    damage=abs(bot.damage_per_shot),
                    is_heal=bot.is_healer,
                    projectile_type=bot.projectile_type,
                    splash_radius=bot.splash_radius,
                )
                self.projectiles.append(proj)

            self.events.append(
                {
                    "type": "shot",
                    "shooter_id": bot.bot_id,
                    "target_id": target.bot_id,
                    "is_heal": bot.is_healer,
                    "projectile_type": bot.projectile_type,
                    "x": muzzle_pos.x,
                    "y": muzzle_pos.y,
                    "angle": math.degrees(math.atan2(shot_direction.y, shot_direction.x)) % 360,
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
            "seed": self.seed,
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
                    "healing_done": bot.healing_done,
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
