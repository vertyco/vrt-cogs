from __future__ import annotations

import math
import random
import typing as t
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter

from . import constants

OverswingKind = t.Literal["slip", "resisted", "damage", "break", "shatter"]


@dataclass(frozen=True, slots=True)
class OverswingResult:
    """What a too-fast swing did to the player's pickaxe."""

    kind: OverswingKind
    durability: int  # Pickaxe durability after the swing
    damage: int  # Durability lost on this swing


@dataclass(slots=True)
class Payouts:
    """Everything the end of a rock pays out, keyed by user id."""

    loot: dict[int, dict[constants.Resource, int]]
    scores: dict[int, int]
    bonus_pct: dict[int, float]
    synergy: dict[str, t.Any]


def downgraded_tool(tool: constants.ToolName) -> constants.ToolTier:
    """The tool one tier below `tool`."""
    return constants.TOOLS[constants.TOOL_ORDER[constants.TOOL_ORDER.index(tool) - 1]]


def redraw_interval(miners: int) -> float:
    """Seconds between two redraws of a live rock; busier rocks redraw less often."""
    extra = max(0, miners - 1) * constants.REDRAW_SECONDS_PER_MINER
    return max(constants.REDRAW_MIN_SECONDS, 1.0 + extra)


def split_by_damage(amount: int, ranked: list[tuple[int, int]], total: int) -> dict[int, int]:
    """Split `amount` by damage share, rounding down, then hand leftovers to the biggest remainders."""
    shares: dict[int, int] = {}
    remainders: list[tuple[int, float]] = []
    for uid, damage in ranked:
        exact = (amount * damage) / total if total else 0
        shares[uid] = int(exact)
        if shares[uid] < exact:
            remainders.append((uid, exact - shares[uid]))
    leftover = amount - sum(shares.values())
    remainders.sort(key=lambda item: item[1], reverse=True)
    for uid, __ in remainders[: max(0, leftover)]:
        shares[uid] += 1
    return shares


class RockSession:
    """State and rules for one live rock. Never calls Discord or the database."""

    def __init__(
        self,
        rocktype: constants.RockType,
        modifiers: list[constants.Modifier] | None = None,
        ping: str | None = None,
    ):
        self.rocktype = rocktype
        self.modifiers = modifiers or []
        self.ping = ping

        hp_mult = loot_mult = volatility_mult = 1.0
        for mod in self.modifiers:
            hp_mult *= mod.hp_multiplier
            loot_mult *= mod.loot_multiplier
            volatility_mult *= mod.volatility_multiplier

        self.max_hp = max(1, int(round(rocktype.hp * hp_mult)))
        self.current_hp = self.max_hp
        self.total_loot: dict[constants.Resource, int] = {
            k: max(1, int(round(v * loot_mult))) for k, v in rocktype.total_loot.items() if v > 0
        }
        self.floor_loot: dict[constants.Resource, int] = {
            k: max(1, int(round(v * loot_mult))) for k, v in rocktype.floor_loot.items() if v > 0
        }
        self.overswing_break_chance = min(1.0, rocktype.overswing_break_chance * volatility_mult)
        self.overswing_damage_chance = min(1.0, rocktype.overswing_damage_chance * volatility_mult)

        # user_id -> totals for this rock
        self.participants: dict[int, int] = defaultdict(int)
        self.hits: dict[int, int] = defaultdict(int)
        self.overswings: dict[int, int] = defaultdict(int)
        self.crit_hits: dict[int, int] = defaultdict(int)
        self.low_hp_damage: dict[int, int] = defaultdict(int)
        self.shatter_resist_survivors: set[int] = set()
        self.shattered_users: set[int] = set()
        self.tools: dict[int, constants.ToolName] = {}  # Pickaxe each miner last hit with
        self.perks: dict[int, frozenset[str]] = {}  # Perks each miner last hit with
        self.shattered_tools: dict[int, constants.ToolName] = {}  # Pickaxe lost to an overswing
        self.actions: deque[str] = deque(maxlen=constants.RECENT_ACTIONS_SHOWN)

        self.started_at: float = 0.0
        self.end_time: datetime | None = None

    def start(self) -> None:
        self.started_at = perf_counter()
        self.end_time = datetime.now() + timedelta(seconds=self.rocktype.ttl_seconds)

    @property
    def depleted(self) -> bool:
        return self.current_hp <= 0

    def duration(self) -> float:
        return max(0.0, perf_counter() - self.started_at)

    def ranked(self) -> list[tuple[int, int]]:
        """(user_id, damage) pairs, highest damage first."""
        return sorted(self.participants.items(), key=lambda item: item[1], reverse=True)

    def apply_hit(self, user_id: int, name: str, tool: constants.ToolTier, perks: frozenset[str] = frozenset()) -> int:
        """Apply one swing at normal pace and return the damage it dealt."""
        power = tool.power
        if "forceful" in perks:
            power = round(power * constants.FORCEFUL_POWER_MULTIPLIER)
        crit_chance = tool.crit_chance + (constants.LUCKY_CRIT_CHANCE_BONUS if "lucky" in perks else 0.0)
        crit = random.random() < crit_chance
        if crit:
            power = round(power * tool.crit_multiplier)
            self.crit_hits[user_id] += 1
        low_hp = self.current_hp <= self.max_hp * constants.PARTY_FINISHER_HP_THRESHOLD
        if low_hp and "closer" in perks:
            power = round(power * constants.CLOSER_DAMAGE_MULTIPLIER)
        damage = min(power, self.current_hp)
        if low_hp:
            self.low_hp_damage[user_id] += damage
        self.current_hp -= damage
        self.participants[user_id] += damage
        self.hits[user_id] += 1
        self.tools[user_id] = tool.key
        self.perks[user_id] = perks
        self.actions.append(("💥CRITICAL HIT! " if crit else "") + f"{name}: +{damage} damage!")
        return damage

    def judge_overswing(
        self, tool: constants.ToolTier, durability: int, roll: float, sturdy: bool = False
    ) -> OverswingResult:
        """Decide what a too-fast swing does, given a random `roll` between 0 and 1."""
        max_durability = tool.max_durability or 0
        ratio = (durability / max_durability) if max_durability else None
        allow_catastrophic = ratio is None or ratio <= constants.OVERSWING_SHATTER_DURA_THRESHOLD
        shatter_chance = self.overswing_break_chance * (1 - tool.shatter_resistance)
        if allow_catastrophic and roll < shatter_chance:
            return OverswingResult("shatter", durability, 0)
        if roll < self.overswing_damage_chance:
            hit = self.rocktype.overswing_damage
            if sturdy:
                hit = max(1, math.ceil(hit * constants.STURDY_WEAR_MULTIPLIER))
            remaining = max(0, durability - hit)
            dealt = hit if remaining else durability
            return OverswingResult("damage" if remaining else "break", remaining, dealt)
        if allow_catastrophic and tool.shatter_resistance > 0 and roll < self.overswing_break_chance:
            return OverswingResult("resisted", durability, 0)
        return OverswingResult("slip", durability, 0)

    def record_overswing(
        self,
        user_id: int,
        name: str,
        tool: constants.ToolTier,
        result: OverswingResult | None,
    ) -> None:
        """Count a too-fast swing. `result` is None for wood pickaxes, which never roll."""
        self.overswings[user_id] += 1
        kind = "slip" if result is None else result.kind
        lost = result.damage if result else 0
        if kind == "resisted":
            self.shatter_resist_survivors.add(user_id)
        if kind in ("shatter", "break"):
            self.shattered_users.add(user_id)
            self.shattered_tools[user_id] = tool.key
            self.perks[user_id] = frozenset()  # The lost pickaxe took its perks with it
        if kind in ("slip", "resisted"):
            self.actions.append(f"🤕{name} slipped and fell from swinging too fast!")
        elif kind == "damage":
            self.actions.append(f"⚠️{name} did {lost} damage to their pickaxe swinging too hastily!")
        elif kind == "shatter":
            self.actions.append(f"‼️{name} shattered their {tool.display_name}!")
        # "break" (pickaxe worn to 0 by overswing damage) adds no recent-action line, as before

    def tool_wear(self, user_id: int, synergy: dict[str, t.Any]) -> int:
        """Durability a paid miner's pickaxe loses at the end of the rock."""
        wear = max(1, self.hits.get(user_id, 0) // constants.HITS_PER_DURA_LOST)
        if user_id in synergy["durability_bonus_participants"]:
            wear = max(1, wear - synergy["durability_discount"])
        if "sturdy" in self.perks.get(user_id, frozenset()):
            wear = max(1, math.ceil(wear * constants.STURDY_WEAR_MULTIPLIER))
        return wear

    def performance(self, ranked: list[tuple[int, int]], total: int) -> tuple[dict[int, int], dict[int, float]]:
        """Performance score and loot bonus percentage per miner."""
        scores: dict[int, int] = {}
        bonus_pct: dict[int, float] = {}
        for uid, damage in ranked:
            hits = self.hits.get(uid, 0)
            swings = hits + self.overswings.get(uid, 0)
            damage_ratio = (damage / total) if total else 0.0
            control_ratio = (hits / swings) if swings else 1.0
            activity_ratio = min(1.0, hits / constants.PERFORMANCE_HIT_TARGET)
            score = round(
                (damage_ratio * constants.PERFORMANCE_DAMAGE_SCORE_MAX)
                + (control_ratio * constants.PERFORMANCE_CONTROL_SCORE_MAX)
                + (activity_ratio * constants.PERFORMANCE_ACTIVITY_SCORE_MAX)
            )
            scores[uid] = score
            bonus_pct[uid] = next((pct for floor, pct in constants.PERFORMANCE_BONUS_TIERS if score >= floor), 0.0)
        return scores, bonus_pct

    def bonus_for(
        self,
        uid: int,
        resource: constants.Resource,
        base: int,
        bonus_pct: dict[int, float],
        synergy: dict[str, t.Any],
    ) -> int:
        """Performance, crew and Prospector bonuses on top of a miner's base share."""
        if base <= 0:
            return 0
        pct = bonus_pct.get(uid, 0.0)
        if resource == "gems":
            pct = min(pct, constants.PERFORMANCE_GEM_BONUS_CAP)
        extra = int(base * pct)
        if resource in ("stone", "iron") and uid in synergy["bonus_participants"]:
            extra += int(base * synergy["loot_bonus_pct"])
        if resource == "gems" and "prospector" in self.perks.get(uid, frozenset()):
            extra += math.ceil(base * constants.PROSPECTOR_GEM_BONUS)
        return extra

    def compute_payouts(self) -> Payouts:
        """Split the loot pool by damage. A collapse pays the floor pool, depletion the full pool."""
        pool = self.total_loot if self.depleted else self.floor_loot
        ranked = [(uid, damage) for uid, damage in self.ranked() if damage > 0]
        total = sum(damage for __, damage in ranked)
        synergy = self.party_synergy()
        scores, bonus_pct = self.performance(ranked, total)
        loot: dict[int, dict[constants.Resource, int]] = {uid: {} for uid, __ in ranked}
        for resource, amount in pool.items():
            for uid, base in split_by_damage(amount, ranked, total).items():
                loot[uid][resource] = base + self.bonus_for(uid, resource, base, bonus_pct, synergy)
        return Payouts(loot=loot, scores=scores, bonus_pct=bonus_pct, synergy=synergy)

    def party_synergy(self) -> dict[str, t.Any]:
        """Crew roles held right now and the bonus they unlock."""
        ranked = self.ranked()
        total = sum(damage for __, damage in ranked)
        eligible = [
            uid
            for uid, damage in ranked
            if self.hits.get(uid, 0) >= constants.PARTY_SYNERGY_MIN_HITS
            and ((damage / total) if total else 0.0) >= constants.PARTY_SYNERGY_MIN_DAMAGE_SHARE
        ]
        roles = self.pick_roles(ranked, total, eligible) if len(eligible) >= 2 else []
        loot_bonus_pct = 0.0
        if len(roles) >= 3:
            loot_bonus_pct = constants.PARTY_SYNERGY_THREE_ROLE_LOOT_BONUS
        elif len(roles) >= 2:
            loot_bonus_pct = constants.PARTY_SYNERGY_TWO_ROLE_LOOT_BONUS
        return {
            "active": len(roles) >= 2,
            "roles": roles,
            "eligible_participants": eligible,
            "bonus_participants": set(eligible) if len(eligible) >= 2 else set(),
            "durability_bonus_participants": {uid for __, uid in roles},
            "loot_bonus_pct": loot_bonus_pct,
            "durability_discount": constants.PARTY_SYNERGY_DURABILITY_DISCOUNT if len(roles) >= 2 else 0,
        }

    def pick_roles(self, ranked: list[tuple[int, int]], total: int, eligible: list[int]) -> list[tuple[str, int]]:
        roles: list[tuple[str, int]] = []
        breaker = next(
            (
                uid
                for uid, damage in ranked
                if uid in eligible and ((damage / total) if total else 0.0) >= constants.PARTY_BREAKER_MIN_DAMAGE_SHARE
            ),
            None,
        )
        if breaker is not None:
            roles.append(("Breaker", breaker))
        stabilizer = self.pick_stabilizer(eligible, {uid for __, uid in roles})
        if stabilizer is not None:
            roles.append(("Stabilizer", stabilizer))
        finisher = self.pick_finisher(eligible, {uid for __, uid in roles})
        if finisher is not None:
            roles.append(("Finisher", finisher))
        return roles

    def pick_stabilizer(self, eligible: list[int], used: set[int]) -> int | None:
        candidates = sorted(
            eligible,
            key=lambda uid: (self.overswings.get(uid, 0), -self.hits.get(uid, 0), -self.participants.get(uid, 0)),
        )
        for uid in candidates:
            if uid in used:
                continue
            hits = self.hits.get(uid, 0)
            swings = hits + self.overswings.get(uid, 0)
            rate = (self.overswings.get(uid, 0) / swings) if swings else 0.0
            if rate <= constants.PARTY_STABILIZER_MAX_OVERSWING_RATE:
                return uid
        return None

    def pick_finisher(self, eligible: list[int], used: set[int]) -> int | None:
        total_low = sum(self.low_hp_damage.values())
        for uid in sorted(eligible, key=lambda uid: self.low_hp_damage.get(uid, 0), reverse=True):
            if uid in used:
                continue
            low = self.low_hp_damage.get(uid, 0)
            share = (low / total_low) if total_low else 0.0
            if low and share >= constants.PARTY_FINISHER_MIN_DAMAGE_SHARE:
                return uid
        return None
