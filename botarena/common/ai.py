"""
Bot Arena - Battle AI

Decides what every bot wants to do; the engine (engine.py) carries it out with physics.

Every few tenths of a second (sooner on a smarter chassis) each bot re-plans:
    1. Target - who to shoot, by its target priority. Targets are sticky, so bots don't
       flip-flop between enemies and waste time swinging their turret
    2. Spot - where to stand. Nearby spots are scored for the bot's stance: can it hit its
       target from there, how many enemies can hit it there (using their real weapon ranges),
       walls, teammates, and how long the drive is
Every tick it then steers toward that spot (the engine picks forward or reverse gear),
jinks and sidesteps incoming shots when its chassis is side-on to them, and aims its turret
where the target will be when the shot lands.

Intelligence is skill: it sets how well a bot leads its shots, how quickly it reads a
target's change of direction or notices an incoming shell, how often it re-plans, and how
cleanly it judges targets and spots.
"""

import math
import typing as t
from dataclasses import dataclass

from .engine import (
    ACCELERATION,
    BRAKING,
    POINT_BLANK_REACH,
    REVERSE_SPEED,
    AIBehavior,
    BotRuntimeState,
    TargetPriority,
    Vector2,
)

if t.TYPE_CHECKING:
    from .engine import BattleEngine

# Seconds a bot takes to read a target's change of direction or notice an incoming shot,
# from intelligence 0 to intelligence 10
REACTION_SLOW = 0.45
REACTION_FAST = 0.10
# Seconds between re-plans, from intelligence 0 to intelligence 10
PLAN_SLOW = 0.65
PLAN_FAST = 0.30
# Below this share of health a bot falls back to a friendly healer (until it's RECOVERED more)
RETREAT_HEALTH = {AIBehavior.AGGRESSIVE: 0.15, AIBehavior.TACTICAL: 0.3, AIBehavior.DEFENSIVE: 0.4}
RECOVERED = 0.25
# Tactical bots strafe up to this far either side of their spot
STRAFE_REACH = 80.0
# ...and circle their target instead of chasing their exact spot while within this distance of it
ORBIT_LEASH = 160.0
# Shots passing this close to a hull's edge are worth sidestepping
DODGE_MARGIN = 10.0
# Seconds of an enemy's approach counted into its reach when judging how dangerous a spot is
THREAT_LOOKAHEAD = 1.5
# A bot this close to its spot has arrived
ARRIVED = 20.0
# Spots closer than this to a wall (or teammate) score worse
WALL_MARGIN = 160.0
CROWD_RADIUS = 110.0
# Open ground a falling-back bot wants behind it (away from the enemies) before it feels cornered
ESCAPE_ROOM = 300.0


@dataclass(frozen=True)
class StanceProfile:
    """How a stance weighs a spot (and how stubbornly it keeps its target)"""

    attack: float  # Being able to hit the target from the spot
    caution: float  # Avoiding spots enemies can hit
    travel: float  # Penalty per second of driving to the spot
    flank: float  # Attacking from a different angle than teammates (or the target's turret)
    cohesion: float  # Staying within reach of a friendly healer
    stickiness: float  # How many seconds better a new target must look before switching


PROFILES = {
    AIBehavior.AGGRESSIVE: StanceProfile(
        attack=2.0, caution=0.35, travel=0.15, flank=0.0, cohesion=0.0, stickiness=1.5
    ),
    AIBehavior.DEFENSIVE: StanceProfile(attack=1.5, caution=1.6, travel=0.35, flank=0.0, cohesion=0.5, stickiness=0.75),
    AIBehavior.TACTICAL: StanceProfile(attack=1.6, caution=0.9, travel=0.25, flank=0.6, cohesion=0.25, stickiness=0.75),
}
# Healers mostly care about staying within reach of their patient, and weigh danger by stance
HEALER_CAUTION = {AIBehavior.AGGRESSIVE: 0.35, AIBehavior.TACTICAL: 0.6, AIBehavior.DEFENSIVE: 0.9}
# ...until they're this badly hurt themselves
HEALER_SELF_PRESERVATION = 0.35


def angle_diff(a: float, b: float) -> float:
    """Signed smallest turn from heading b to heading a, in degrees (-180 to 180)."""
    return (a - b + 180.0) % 360.0 - 180.0


def heading_vector(degrees: float) -> Vector2:
    rad = math.radians(degrees)
    return Vector2(math.cos(rad), math.sin(rad))


def dps(bot: BotRuntimeState) -> float:
    return abs(bot.damage_per_shot) * bot.shots_per_second


def intercept_time(origin: Vector2, pos: Vector2, vel: Vector2, speed: float, head_start: float) -> float:
    """Seconds until a shot from `origin` meets a target at `pos` moving at `vel`.

    The shot flies at `speed` but leaves the barrel `head_start` ahead of the origin.
    """
    if speed <= 0:
        return 0.0
    offset = pos - origin
    a = vel.dot(vel) - speed * speed
    b = 2.0 * (offset.dot(vel) - speed * head_start)
    c = offset.dot(offset) - head_start * head_start
    if c <= 0:
        return 0.0  # Already inside the barrel's reach
    if abs(a) < 1e-6:
        flight = -c / b if b < 0 else offset.magnitude() / speed
    else:
        disc = b * b - 4 * a * c
        if disc < 0:
            return offset.magnitude() / speed
        root = math.sqrt(disc)
        flight = min((x for x in ((-b - root) / (2 * a), (-b + root) / (2 * a)) if x > 0), default=0.0)
    return max(0.0, min(3.0, flight))


class BattleAI:
    """Targeting, positioning, steering and aiming for every bot in a battle."""

    def __init__(self, engine: "BattleEngine"):
        self.engine = engine
        # Shared Focus Fire target per team, and when the team next reconsiders it
        self.team_focus: dict[int, str] = {}
        self.focus_until: dict[int, float] = {}
        self._ready = False

    # ─────────────────────────────────────────────────────────────────────────
    # Per-bot skill
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def skill(bot: BotRuntimeState) -> float:
        return max(0.0, min(1.0, bot.intelligence / 10.0))

    def reaction(self, bot: BotRuntimeState) -> float:
        return REACTION_SLOW - (REACTION_SLOW - REACTION_FAST) * self.skill(bot)

    def plan_interval(self, bot: BotRuntimeState) -> float:
        return PLAN_SLOW - (PLAN_SLOW - PLAN_FAST) * self.skill(bot)

    def roll_lead(self, bot: BotRuntimeState) -> float:
        """How much of the needed lead the bot gives its shots until its next plan (1.0 = perfect)."""
        skill = self.skill(bot)
        center = 0.55 + 0.45 * skill
        wobble = 0.25 * (1.0 - skill)
        return self.engine.rng.uniform(center - wobble, center + wobble)

    # ─────────────────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────────────────
    def setup(self):
        """Stagger the first plans so the bots don't all think on the same tick."""
        rng = self.engine.rng
        for bot in self.engine.bots.values():
            bot.plan_timer = rng.uniform(0.0, self.plan_interval(bot))
            bot.lead = self.roll_lead(bot)
            bot.strafe_dir = rng.choice((-1, 1))
            bot.strafe_timer = rng.uniform(0.6, 1.4)
        self._ready = True

    def update(self):
        """Decide targets, spots, steering and aim for every living bot this tick."""
        if not self._ready:
            self.setup()
        dt = self.engine.dt
        for bot in self.engine.bots.values():
            if not bot.is_alive:
                continue
            bot.plan_timer -= dt
            if bot.plan_timer <= 0 or self.needs_replan(bot):
                self.plan(bot)
                bot.plan_timer = self.plan_interval(bot) * self.engine.rng.uniform(0.85, 1.15)
            self.steer(bot)
            self.aim(bot)

    def needs_replan(self, bot: BotRuntimeState) -> bool:
        """Re-plan at once when the target died (or a healer's patient is topped up)."""
        if bot.target_id is None:
            return bot.move_goal is None
        target = self.engine.bots.get(bot.target_id)
        if target is None or not target.is_alive:
            return True
        return bot.is_healer and target.health >= target.max_health

    def plan(self, bot: BotRuntimeState):
        if bot.is_healer:
            self.plan_healer(bot)
            return
        target = self.pick_target(bot)
        bot.target_id = target.bot_id if target else None
        if target is None:
            bot.move_goal = None
            return
        self.update_retreat(bot)
        bot.move_goal = self.best_spot(bot, target)
        bot.lead = self.roll_lead(bot)

    # ─────────────────────────────────────────────────────────────────────────
    # Targeting
    # ─────────────────────────────────────────────────────────────────────────
    def enemies_of(self, bot: BotRuntimeState) -> list[BotRuntimeState]:
        return [b for b in self.engine.bots.values() if b.is_alive and b.team != bot.team]

    def allies_of(self, bot: BotRuntimeState) -> list[BotRuntimeState]:
        return [b for b in self.engine.bots.values() if b.is_alive and b.team == bot.team and b.bot_id != bot.bot_id]

    def engage_time(self, bot: BotRuntimeState, enemy: BotRuntimeState) -> float:
        """Rough seconds until `bot` could be shooting `enemy`: driving into range plus swinging the turret."""
        dist = bot.position.distance_to(enemy.position)
        if dist > bot.max_range:
            gap = dist - bot.max_range * 0.9
        elif dist < bot.min_range and not bot.allows_point_blank:
            gap = bot.min_range - dist
        else:
            gap = 0.0
        swing = abs(angle_diff(bot.position.angle_to(enemy.position), bot.weapon_orientation))
        return gap / max(1.0, bot.speed) + swing / max(1.0, bot.turret_rotation_speed)

    def target_score(self, bot: BotRuntimeState, enemy: BotRuntimeState, priority: TargetPriority) -> float:
        """How good a target `enemy` is for `bot` under a priority, roughly in seconds (lower is better)."""
        engage = self.engage_time(bot, enemy)
        if priority == TargetPriority.WEAKEST:
            # Whoever dies soonest to this weapon, counting the drive to reach them
            return enemy.health / max(1.0, dps(bot)) + engage
        if priority == TargetPriority.SUPPORT_FIRST:
            # Healers first, then whoever hits hardest
            if enemy.is_healer:
                return engage
            hardest = max((dps(e) for e in self.enemies_of(bot) if not e.is_healer), default=1.0)
            return engage + 4.0 + 3.0 * (1.0 - dps(enemy) / max(1.0, hardest))
        # CLOSEST: whoever it can be shooting soonest, preferring whoever has been shooting it
        score = engage + bot.position.distance_to(enemy.position) / 600.0
        threat = bot.threat_map.get(enemy.bot_id)
        if threat:
            score -= 0.75 * min(1.0, threat.get_threat_score(self.engine.current_time) / (0.1 * bot.max_health))
        return score

    def team_focus_target(self, team: int) -> t.Optional[BotRuntimeState]:
        """The one enemy a team's Focus Fire bots agree on: the one they can kill fastest together."""
        engine = self.engine
        current = engine.bots.get(self.team_focus.get(team, ""))
        if current is not None and current.is_alive and engine.current_time < self.focus_until.get(team, 0.0):
            return current
        shooters = [
            b
            for b in engine.bots.values()
            if b.is_alive and b.team == team and not b.is_healer and b.target_priority == TargetPriority.FOCUS_FIRE
        ]
        enemies = [b for b in engine.bots.values() if b.is_alive and b.team != team]
        if not shooters or not enemies:
            return None
        team_dps = sum(dps(b) for b in shooters)

        def team_score(enemy: BotRuntimeState) -> float:
            engage = sum(self.engage_time(b, enemy) for b in shooters) / len(shooters)
            return enemy.health / max(1.0, team_dps) + engage

        best = min(enemies, key=team_score)
        if current is not None and current.is_alive and team_score(current) <= team_score(best) + 1.0:
            best = current
        self.team_focus[team] = best.bot_id
        self.focus_until[team] = engine.current_time + 1.0
        return best

    def pick_target(self, bot: BotRuntimeState) -> t.Optional[BotRuntimeState]:
        enemies = self.enemies_of(bot)
        if not enemies:
            return None
        priority = bot.target_priority
        if priority == TargetPriority.FOCUS_FIRE:
            focus = self.team_focus_target(bot.team)
            if focus is not None and self.engage_time(bot, focus) < 6.0:
                return focus
            priority = TargetPriority.CLOSEST  # Can't reach the team's target any time soon

        # A dumber chassis misjudges which enemy is best
        noise = 0.4 * (1.0 - self.skill(bot))
        scores = {e.bot_id: self.target_score(bot, e, priority) + self.engine.rng.gauss(0.0, noise) for e in enemies}
        best = min(enemies, key=lambda e: scores[e.bot_id])
        current = self.engine.bots.get(bot.target_id) if bot.target_id else None
        if current is not None and current.bot_id in scores and current is not best:
            # Stick with the current target unless the new one is clearly better
            if scores[current.bot_id] <= scores[best.bot_id] + PROFILES[bot.behavior].stickiness:
                return current
        return best

    # ─────────────────────────────────────────────────────────────────────────
    # Positioning
    # ─────────────────────────────────────────────────────────────────────────
    def update_retreat(self, bot: BotRuntimeState):
        """Badly hurt bots fall back to a friendly healer (if there is one) until they're patched up."""
        healers = [a for a in self.allies_of(bot) if a.is_healer]
        if not healers or self.engine.stalemate_pressure() >= 0.8:
            bot.retreating = False
            return
        threshold = RETREAT_HEALTH.get(bot.behavior, 0.3)
        health = bot.get_health_percentage()
        bot.retreating = health < threshold + (RECOVERED if bot.retreating else 0.0)

    def low_range(self, bot: BotRuntimeState, other: BotRuntimeState) -> float:
        """Closest useful distance to `other`: the weapon's minimum range, or hull contact for point-blank weapons."""
        if bot.allows_point_blank:
            return self.engine._contact_distance(bot, other) + 10.0
        return float(bot.min_range)

    def ideal_range(self, bot: BotRuntimeState, target: BotRuntimeState) -> float:
        """The distance the bot's stance wants to fight its target from."""
        low = self.low_range(bot, target)
        high = float(bot.max_range)
        if bot.behavior == AIBehavior.AGGRESSIVE:
            ideal = low + (high - low) * 0.2
            # Get under a weapon that can't fire point-blank, where it can't shoot back
            if not target.allows_point_blank and not target.is_healer and target.min_range > low + 20:
                ideal = min(ideal, max(low + 10.0, target.min_range * 0.75))
        elif bot.behavior == AIBehavior.DEFENSIVE:
            ideal = high * 0.85
            # Stretch a little further to stay just past the reach of a slightly shorter weapon
            reach = target.max_range + 40.0 + target.speed * 0.5
            if not target.is_healer and ideal < reach < high * 0.95:
                ideal = reach
        else:
            ideal = (low + high) / 2
        if bot.behavior == AIBehavior.DEFENSIVE and self.closing_in(target, bot):
            # Let an enemy that's already coming walk into range instead of driving out to meet it
            ideal = max(ideal, min(high * 0.95, bot.position.distance_to(target.position)))
        # Stalemate: everyone closes in
        pressure = self.engine.stalemate_pressure()
        return ideal + (low + (high - low) * 0.15 - ideal) * pressure

    @staticmethod
    def closing_in(chaser: BotRuntimeState, quarry: BotRuntimeState) -> bool:
        """Whether `chaser` is driving toward `quarry` at a good share of its top speed."""
        offset = quarry.position - chaser.position
        dist = offset.magnitude()
        return dist > 0 and chaser.velocity.dot(offset) / dist > 0.3 * chaser.speed

    @staticmethod
    def band_fit(low: float, high: float, dist: float, ideal: float) -> float:
        """1.0 at the ideal distance, falling to 0 at the edges of the range band, and below 0 outside it
        (lower the further out, so a bot out of range always prefers a step closer)."""
        if dist > high:
            return -min(3.0, (dist - high) / 150.0)
        if dist < low:
            return -min(2.0, (low - dist) / 80.0)
        return 1.0 - min(1.0, abs(dist - ideal) / max(60.0, (high - low) / 2))

    def danger(
        self,
        bot: BotRuntimeState,
        spot: Vector2,
        enemies: list[BotRuntimeState],
        target: t.Optional[BotRuntimeState] = None,
        trading: bool = False,
    ) -> float:
        """How dangerous `spot` is: per enemy that can reach it, 0 (harmless) to 1 (would shred the bot).

        When `trading` (the bot can hit `target` from the spot), the target's own fire mostly counts as a
        fair trade, so bots still fight an equal-ranged enemy instead of fleeing it. Spots out of the target's
        reach (kiting) or where only the target can shoot (a dead zone, out-ranged) still score as they are.
        """
        total = 0.0
        for enemy in enemies:
            if enemy.is_healer:
                continue
            offset = spot - enemy.position
            dist = offset.magnitude()
            # Where it could be shooting from soon, if it's driving this way
            closing = max(0.0, enemy.velocity.dot(offset) / dist) if dist > 0 else 0.0
            reach = enemy.max_range + 30.0 + closing * THREAT_LOOKAHEAD
            if dist > reach + 40.0:
                continue
            exposure = 1.0 if dist <= reach else 1.0 - (dist - reach) / 40.0
            if not enemy.allows_point_blank and dist < enemy.min_range:
                exposure *= max(0.0, 1.0 - (enemy.min_range - dist) / 30.0)  # Inside its dead zone
            if enemy.target_id == bot.bot_id:
                exposure *= 1.5
            # Share of the bot's health this enemy would strip in ten seconds, saturating at 1
            strip = dps(enemy) * exposure * 10.0 / max(bot.health, 0.35 * bot.max_health)
            total += (1.0 - math.exp(-strip)) * (0.3 if trading and enemy is target else 1.0)
        return total

    def wall_penalty(self, spot: Vector2) -> float:
        cfg = self.engine.config
        penalty = 0.0
        for gap in (spot.x, cfg.arena_width - spot.x, spot.y, cfg.arena_height - spot.y):
            if gap < WALL_MARGIN:
                penalty += ((WALL_MARGIN - gap) / WALL_MARGIN) ** 2
        return penalty * 0.8

    def cornered_penalty(self, bot: BotRuntimeState, spot: Vector2, enemies: list[BotRuntimeState]) -> float:
        """0 with open ground ahead of the bot past `spot`, up to 1 with a wall right there (only near enemies).

        Measured along the way the bot would be heading (or straight away from the enemies, for a spot
        it's already at), so a bot falling back slides along walls and kites around the arena instead
        of backing itself into a wall or a corner.
        """
        if not any(not e.is_healer and spot.distance_to(e.position) < e.max_range + 250.0 for e in enemies):
            return 0.0
        heading = spot - bot.position
        if heading.magnitude() < 30.0:
            heading = Vector2(0.0, 0.0)
            for enemy in enemies:
                offset = spot - enemy.position
                heading = heading + offset.normalized() * (1.0 / max(50.0, offset.magnitude()))
        direction = heading.normalized()
        if direction.magnitude() == 0:
            return 0.0
        cfg = self.engine.config
        margin = cfg.bot_radius + 40.0
        room = math.inf
        for pos, step, low, high in (
            (spot.x, direction.x, margin, cfg.arena_width - margin),
            (spot.y, direction.y, margin, cfg.arena_height - margin),
        ):
            if step > 1e-6:
                room = min(room, (high - pos) / step)
            elif step < -1e-6:
                room = min(room, (low - pos) / step)
        return max(0.0, 1.0 - room / ESCAPE_ROOM)

    def crowd_penalty(self, spot: Vector2, allies: list[BotRuntimeState]) -> float:
        penalty = 0.0
        for ally in allies:
            where = ally.move_goal or ally.position
            dist = spot.distance_to(where)
            if dist < CROWD_RADIUS:
                penalty += (CROWD_RADIUS - dist) / CROWD_RADIUS * 0.8
        return penalty

    def healer_bonus(self, spot: Vector2, allies: list[BotRuntimeState]) -> float:
        """1.0 inside a friendly healer's reach, fading over the next 200px (0 with no healer)."""
        best = 0.0
        for ally in allies:
            if ally.is_healer:
                reach = ally.max_range * 0.9
                best = max(best, 1.0 - max(0.0, spot.distance_to(ally.position) - reach) / 200.0)
        return max(0.0, best)

    def flank_bonus(self, bot: BotRuntimeState, spot: Vector2, target: BotRuntimeState) -> float:
        """Attack from a different side than teammates on the same target, or away from its turret."""
        to_spot = target.position.angle_to(spot)
        partners = [
            a
            for a in self.allies_of(bot)
            if not a.is_healer and a.target_id == target.bot_id and a.bot_id != bot.bot_id
        ]
        if partners:
            spread = [
                min(90.0, abs(angle_diff(to_spot, target.position.angle_to(a.position)))) / 90.0 for a in partners
            ]
            return sum(spread) / len(spread)
        return min(120.0, abs(angle_diff(to_spot, target.weapon_orientation))) / 120.0 * 0.5

    def clamp_to_arena(self, spot: Vector2) -> Vector2:
        cfg = self.engine.config
        margin = cfg.bot_radius + 48.0
        return Vector2(
            max(margin, min(cfg.arena_width - margin, spot.x)),
            max(margin, min(cfg.arena_height - margin, spot.y)),
        )

    def ring(self, center: Vector2, bearing: float, distances: t.Iterable[float], offsets: t.Iterable[float]):
        """Spots around `center` at the given distances, fanned out from `bearing` (degrees)."""
        for dist in distances:
            for offset in offsets:
                yield self.clamp_to_arena(center + heading_vector(bearing + offset) * dist)

    def candidate_spots(self, bot: BotRuntimeState, around: Vector2, distances: list[float]) -> list[Vector2]:
        spots = [bot.position]
        if bot.move_goal is not None:
            spots.append(bot.move_goal)
        spots.extend(self.ring(around, around.angle_to(bot.position), distances, (-75, -45, -20, 0, 20, 45, 75)))
        step = max(50.0, min(100.0, bot.speed * 1.2))
        spots.extend(self.ring(bot.position, 0.0, (step, step * 2.5), range(0, 360, 45)))
        return spots

    def best_spot(self, bot: BotRuntimeState, target: BotRuntimeState) -> Vector2:
        """Score the spots around the bot for its stance and return the best one."""
        profile = PROFILES[bot.behavior]
        enemies = self.enemies_of(bot)
        allies = self.allies_of(bot)
        low, high = self.low_range(bot, target), float(bot.max_range)
        ideal = self.ideal_range(bot, target)
        pressure = self.engine.stalemate_pressure()

        attack = profile.attack
        caution = profile.caution * (1.0 - 0.8 * pressure)
        travel = profile.travel * (1.0 - pressure)
        cohesion = profile.cohesion
        if bot.retreating:
            attack, caution, cohesion = attack * 0.3, caution * 2.5, 3.0

        noise = 0.3 * (1.0 - self.skill(bot))
        best, best_score = bot.position, -math.inf
        for spot in self.candidate_spots(bot, target.position, [ideal * 0.85, ideal, ideal * 1.15]):
            fit = self.band_fit(low, high, spot.distance_to(target.position), ideal)
            score = attack * fit
            blocked = self.engine.lane_blocked(bot, spot, target.position)
            if blocked:
                score -= attack * 0.6
            score -= caution * self.danger(bot, spot, enemies, target, trading=fit > 0 and not blocked)
            score -= self.wall_penalty(spot) + self.crowd_penalty(spot, allies)
            if caution > 1.0:
                score -= caution * 0.6 * self.cornered_penalty(bot, spot, enemies)
            if cohesion:
                score += cohesion * self.healer_bonus(spot, allies)
            if profile.flank:
                score += profile.flank * self.flank_bonus(bot, spot, target)
            score -= travel * bot.position.distance_to(spot) / max(1.0, bot.speed)
            if bot.move_goal is not None and spot.distance_to(bot.move_goal) < 30.0:
                score += 0.15  # Don't dither between near-equal spots
            score += self.engine.rng.gauss(0.0, noise)
            if score > best_score:
                best, best_score = spot, score
        return best

    # ─────────────────────────────────────────────────────────────────────────
    # Healers
    # ─────────────────────────────────────────────────────────────────────────
    def triage(self, bot: BotRuntimeState) -> t.Optional[BotRuntimeState]:
        """The ally most in need of healing: lowest health first, nearer and current patients preferred."""
        best, best_score = None, math.inf
        for ally in self.allies_of(bot):
            health = ally.get_health_percentage()
            if health >= 0.97:
                continue
            score = health + bot.position.distance_to(ally.position) / 2000.0
            if ally.bot_id == bot.target_id:
                score -= 0.1  # Finish topping up the current patient
            if score < best_score:
                best, best_score = ally, score
        return best

    def frontline_ally(self, bot: BotRuntimeState) -> t.Optional[BotRuntimeState]:
        """The fighter closest to the enemy, to shadow while nobody needs healing."""
        enemies = self.enemies_of(bot)
        allies = [a for a in self.allies_of(bot) if not a.is_healer] or self.allies_of(bot)
        if not allies:
            return None
        if not enemies:
            return allies[0]
        return min(allies, key=lambda a: min(a.position.distance_to(e.position) for e in enemies))

    def plan_healer(self, bot: BotRuntimeState):
        """Heal whoever triage picks, from a spot within reach of them and out of the enemies' reach."""
        patient = self.triage(bot)
        bot.target_id = patient.bot_id if patient else None
        anchor = patient or self.frontline_ally(bot)
        bot.escort_id = anchor.bot_id if anchor else None
        enemies = self.enemies_of(bot)
        allies = self.allies_of(bot)
        caution = HEALER_CAUTION.get(bot.behavior, 0.6)
        if bot.get_health_percentage() < HEALER_SELF_PRESERVATION:
            caution *= 2.5
        if anchor is None:
            # Nobody left to heal: keep out of trouble
            spots = self.candidate_spots(bot, bot.position, [])
            bot.move_goal = min(spots, key=lambda s: self.danger(bot, s, enemies) + self.wall_penalty(s))
            return

        ideal = max(60.0, bot.max_range * 0.55)
        low = 0.0 if bot.allows_point_blank else float(bot.min_range)
        high = float(bot.max_range)
        noise = 0.3 * (1.0 - self.skill(bot))
        best, best_score = bot.position, -math.inf
        for spot in self.candidate_spots(bot, anchor.position, [ideal * 0.8, ideal, ideal * 1.2]):
            score = 3.0 * self.band_fit(low, high, spot.distance_to(anchor.position), ideal)
            score -= caution * self.danger(bot, spot, enemies)
            score -= self.wall_penalty(spot) + self.crowd_penalty(spot, allies)
            score -= caution * 0.6 * self.cornered_penalty(bot, spot, enemies)
            score -= 0.3 * bot.position.distance_to(spot) / max(1.0, bot.speed)
            if bot.move_goal is not None and spot.distance_to(bot.move_goal) < 30.0:
                score += 0.15
            score += self.engine.rng.gauss(0.0, noise)
            if score > best_score:
                best, best_score = spot, score
        bot.move_goal = best
        bot.lead = self.roll_lead(bot)

    # ─────────────────────────────────────────────────────────────────────────
    # Steering
    # ─────────────────────────────────────────────────────────────────────────
    def live_target(self, bot: BotRuntimeState) -> t.Optional[BotRuntimeState]:
        target = self.engine.bots.get(bot.target_id) if bot.target_id else None
        return target if target is not None and target.is_alive else None

    def nearest_enemy(self, bot: BotRuntimeState) -> t.Optional[BotRuntimeState]:
        enemies = self.enemies_of(bot)
        return min(enemies, key=lambda e: bot.position.distance_to(e.position)) if enemies else None

    def drive(
        self,
        bot: BotRuntimeState,
        heading: t.Optional[float],
        throttle: float = 1.0,
        distance: float = 0.0,
        horizon: t.Optional[float] = None,
    ):
        """Ask the engine to travel `distance` along `heading` (None holds still).

        The engine drives forward or in reverse, whichever covers `horizon` (default: the distance)
        sooner, so a bot that expects to keep going that way turns around rather than reversing.
        """
        bot.move_heading = None if heading is None else heading % 360
        bot.move_throttle = throttle
        bot.move_distance = distance
        bot.move_horizon = distance if horizon is None else max(distance, horizon)

    def steer(self, bot: BotRuntimeState):
        """Turn this tick's plan into a travel direction for the engine."""
        if self.dodge(bot):
            return
        target = self.live_target(bot)
        look = target if target is not None and target.team != bot.team else self.nearest_enemy(bot)
        bot.face_angle = bot.position.angle_to(look.position) if look else None

        goal = bot.move_goal
        if goal is None:
            self.drive(bot, None)
            return
        dist = bot.position.distance_to(goal)
        if (
            bot.behavior == AIBehavior.TACTICAL
            and look is not None
            and look is target
            and not bot.is_healer
            and not bot.retreating
            and dist < ORBIT_LEASH
            and abs(self.range_error(bot, target)) < 0.6
        ):
            self.orbit(bot, target, goal)
            return
        if dist > ARRIVED:
            horizon = None
            if look is not None and (bot.behavior == AIBehavior.DEFENSIVE or bot.retreating or bot.is_healer):
                # Falling back from an enemy that may keep coming: plan to keep going (turn and run,
                # turret firing over the back) rather than creep away in reverse
                if goal.distance_to(look.position) > bot.position.distance_to(look.position) + 20.0:
                    horizon = 6.0 * bot.speed
            self.drive(bot, bot.position.angle_to(goal), 1.0, dist, horizon)
            return
        # Hold the spot nose-on to the enemy (aggressive and defensive bots plant to shoot). A defensive bot
        # that out-ranges an enemy coming for it waits facing away instead, turret over its back, ready to run
        if (
            bot.behavior == AIBehavior.DEFENSIVE
            and look is not None
            and look.max_range < bot.max_range
            and self.closing_in(look, bot)
        ):
            bot.face_angle = (bot.position.angle_to(look.position) + 180.0) % 360
        self.drive(bot, None)

    def range_error(self, bot: BotRuntimeState, target: BotRuntimeState) -> float:
        """How far off its stance's ideal range the bot is, from -1 (much too close) to 1 (much too far)."""
        low, high = self.low_range(bot, target), float(bot.max_range)
        off = bot.position.distance_to(target.position) - self.ideal_range(bot, target)
        return max(-1.0, min(1.0, off / max(60.0, (high - low) / 2)))

    def orbit(self, bot: BotRuntimeState, target: BotRuntimeState, goal: Vector2):
        """Circle the target side-on at the stance's range, near the planned spot, jinking back and forth.

        Direction flips at random and right after an enemy fires at the bot (once it notices), so a
        shooter leading the old course misses.
        """
        rng = self.engine.rng
        now = self.engine.current_time
        bot.strafe_timer -= self.engine.dt
        bearing = bot.position.angle_to(target.position)
        side = (bearing + 90.0) % 360
        error = self.range_error(bot, target)

        # Jinking only works side-on and near the right range (a tank can only roll along its own axis),
        # and a chassis needs a moment to stop and roll back the other way
        side_on = abs(math.sin(math.radians(bot.orientation - bearing))) > 0.85
        settled = side_on and abs(error) < 0.35 and bot.strafe_timer < 1.0
        flip = settled and bot.strafe_timer <= 0
        if bot.shot_at_time > bot.shot_noticed and now - bot.shot_at_time >= self.reaction(bot):
            bot.shot_noticed = bot.shot_at_time
            flip = flip or (settled and rng.random() < 0.4 + 0.5 * self.skill(bot))
        # Stay within reach of the planned spot along the circle
        drift = (bot.position - goal).dot(heading_vector(side))
        if flip or drift * bot.strafe_dir > STRAFE_REACH:
            bot.strafe_dir = -bot.strafe_dir
            bot.strafe_timer = rng.uniform(1.3, 2.2)  # Flips again (at random) once under 1s left
        # Lean in or out to hold the ideal range
        heading = bearing + bot.strafe_dir * (90.0 - 45.0 * error)
        self.drive(bot, heading, 1.0, STRAFE_REACH)
        bot.face_angle = None

    def incoming_shot(self, bot: BotRuntimeState) -> t.Optional[tuple[float, Vector2, Vector2]]:
        """The soonest noticed enemy shot that will hit the bot: (seconds to impact, its velocity,
        and where it passes relative to the bot's center)."""
        engine = self.engine
        reaction = self.reaction(bot)
        reach = engine.hull_radii.get(bot.bot_id, engine.config.bot_radius) + DODGE_MARGIN
        soonest = None
        for proj in engine.projectiles:
            if not proj.alive or proj.is_heal or proj.age < reaction:
                continue
            shooter = engine.bots.get(proj.shooter_id)
            if shooter is None or shooter.team == bot.team:
                continue
            speed_sq = proj.velocity.dot(proj.velocity)
            if speed_sq <= 0:
                continue
            impact = (bot.position - proj.position).dot(proj.velocity) / speed_sq
            if impact <= 0 or impact > 1.5:
                continue
            miss = proj.position + proj.velocity * impact - bot.position
            if miss.magnitude() <= reach and (soonest is None or impact < soonest[0]):
                soonest = (impact, proj.velocity, miss)
        return soonest

    def roll_distance(self, bot: BotRuntimeState, gear: int, seconds: float) -> float:
        """How far along its heading a bot gets in `seconds` flooring it forward (1) or in reverse (-1)."""
        top = bot.speed * (1.0 if gear > 0 else -REVERSE_SPEED)
        speed, travelled, step = bot.current_speed, 0.0, self.engine.dt
        for _ in range(int(seconds / step)):
            speeding_up = abs(top) > abs(speed) and top * speed >= 0
            rate = bot.speed * (ACCELERATION if speeding_up else BRAKING) * step
            speed += max(-rate, min(rate, top - speed))
            travelled += speed * step
        return travelled

    def dodge(self, bot: BotRuntimeState) -> bool:
        """Sidestep a noticed incoming shot by rolling forward or back along the chassis.

        Tanks can't strafe, so this only helps a bot that's side-on to the shot: one facing the
        shooter (or facing away) just rolls along the shot's path and gets hit anyway.
        """
        now = self.engine.current_time
        if now < bot.dodge_until:
            self.drive(bot, bot.orientation if bot.dodge_dir > 0 else bot.orientation + 180.0, 1.0, 200.0)
            return True
        shot = self.incoming_shot(bot)
        if shot is None:
            return False
        impact, velocity, miss = shot
        if impact < 0.12:
            return False
        facing = heading_vector(bot.orientation)
        flight = velocity.normalized()

        def passes_by(gear: int) -> float:
            # How far from the bot's center the shot passes if it rolls that way until impact
            offset = miss - facing * self.roll_distance(bot, gear, impact)
            along = offset.dot(flight)
            return (offset - flight * along).magnitude()

        forward, back = passes_by(1), passes_by(-1)
        if max(forward, back) < miss.magnitude() + 8.0:
            return False  # Can't get meaningfully further from it (nose-on, or no time)
        bot.dodge_dir = 1 if forward >= back else -1
        bot.dodge_until = now + impact + 0.1
        self.drive(bot, bot.orientation if bot.dodge_dir > 0 else bot.orientation + 180.0, 1.0, 200.0)
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Aiming
    # ─────────────────────────────────────────────────────────────────────────
    def perceived_velocity(self, shooter: BotRuntimeState, target: BotRuntimeState) -> Vector2:
        """The target's velocity as the shooter has read it so far (a slow chassis is a few frames behind)."""
        track = target.track
        if not track:
            return Vector2(0.0, 0.0)
        lag = int(round(self.reaction(shooter) / self.engine.dt))
        return track[max(0, len(track) - 1 - lag)]

    def in_band(self, bot: BotRuntimeState, other: BotRuntimeState) -> bool:
        """Whether `other` is within the bot's weapon range right now."""
        dist = bot.position.distance_to(other.position)
        return dist <= bot.max_range and (bot.allows_point_blank or dist >= bot.min_range)

    def opportunity(self, bot: BotRuntimeState) -> t.Optional[BotRuntimeState]:
        """While its chosen target is out of range, the enemy in range the turret can swing onto quickest."""
        current = self.engine.bots.get(bot.fire_id) if bot.fire_id else None
        if current is not None and current.is_alive and current.team != bot.team and self.in_band(bot, current):
            return current  # Keep shooting the same one rather than swinging between two
        in_reach = [e for e in self.enemies_of(bot) if self.in_band(bot, e)]
        if not in_reach:
            return None
        return min(
            in_reach,
            key=lambda e: abs(angle_diff(bot.position.angle_to(e.position), bot.weapon_orientation)),
        )

    def aim(self, bot: BotRuntimeState):
        """Point the turret where the target will be when the shot gets there.

        A bot whose chosen target is out of range keeps heading for it, but shoots whatever enemy it
        can reach meanwhile. A healer with nobody to heal yet keeps its turret on the ally it's
        shadowing, ready to fire.
        """
        target = self.live_target(bot)
        if bot.is_healer:
            if target is None and bot.escort_id:
                escort = self.engine.bots.get(bot.escort_id)
                target = escort if escort is not None and escort.is_alive else None
            bot.fire_id = bot.target_id
        elif target is not None:
            if not self.in_band(bot, target):
                target = self.opportunity(bot) or target
            bot.fire_id = target.bot_id
        if target is None:
            bot.fire_id = None
            bot.aim_point = None
            return
        engine = self.engine
        if bot.allows_point_blank and bot.position.distance_to(target.position) < max(
            bot.muzzle_offset, POINT_BLANK_REACH
        ):
            bot.aim_point = target.position  # Point-blank weapons hit whatever they touch
            return
        pivot = engine._turret_pivot(bot)
        velocity = self.perceived_velocity(bot, target) * bot.lead
        head_start = min(bot.muzzle_offset, pivot.distance_to(target.position))
        flight = intercept_time(pivot, target.position, velocity, engine.projectile_speed(bot), head_start)
        bot.aim_point = target.position + velocity * flight
