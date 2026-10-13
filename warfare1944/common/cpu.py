"""The CPU side: when it deploys squads, when it calls fire support, when it leaves cover, and what it has on the
field at the start.

The battle calls each method from its own tick (common/battle.py): `deploy_tick` on the one-second tick, `support_tick`
on the slow tick, `cover_tick` on the really-slow tick, `run_timers` at the end of every step and `place_squads` once at
the start. The CPU pays unit costs from its own RP, deploys through the same squad making as a human (`make_squad`),
has no upgrades and gives no orders.
"""

import typing as t

from .blasts import call_strike
from .data import DIFFICULTY, UNIT_KINDS, UNITS
from .missions import Mission, other_side
from .squads import Soldier, Squad, Tank, leave_cover, make_squad
from .tanks import make_bunker

if t.TYPE_CHECKING:
    from .battle import Battle

FIRST_TRY = 4  # spawnEnemyTimer at a battle start: the first try comes on the fifth one-second tick, F6:6728
WAIT_CHANCE = 6  # each pool entry adds a "wait" 1 time in 6, F6:10884
RANDOM_LANE = 250  # random(1000) <= 250 picks a random lane, 251 in 1000, F6:10888
LANES = (1, 2, 3)
SWAP_NEAR_EDGE = 100  # the random support target must be past x 100 ...
SWAP_FAR_EDGE = 150  # ... and short of the field's width minus this, F6:4034-4036
BUNKER_DELAY_MS = 20  # the bunker appears 20 ms in, F6:6766
PRESPAWN_MS = 3000  # a pre-placed squad appears 3,000 ms times its lane number in, F6:6774
PRESPAWN_INSET = 300  # and stands this far in from its side's spawn point, F6:6774, 6783

# What the CPU may pick at each RP level. The highest level reached wins, but every level reached draws its own
# random numbers first (spawnEnemy, F6:4107-4205).
TIERS = (
    (300, ("riflemen", "assault")),
    (400, ("officer", "machineGun", "bazooka", "riflemen", "assault")),
    (500, ("sniper", "mortarTeam", "officer", "machineGun", "bazooka", "riflemen", "assault")),
)
TANK_RP = 800  # a tank is picked from here up, if the pool has one and it is off cooldown

# Per mood, the n of the "1 in n" a squad in cover rolls to leave it, for line squads (riflemen, assault), for sniper
# and bazooka squads and for officer and machine gun squads (enemyUnitAI, F6:3865-3925). Static never leaves.
LEAVE_ROLLS = {
    "aggressive": (2, 3, 5),
    "balanced": (3, 7, 10),
    "defensive": (5, 7, 15),
}
LINE_KINDS = ("riflemen", "assault")
MARKSMAN_KINDS = ("sniper", "bazooka")
SPECIAL_KINDS = ("officer", "machineGun")


class Cpu:
    def __init__(self, side: str, mission: Mission, difficulty: str):
        """`side` is the side the CPU plays. The mission's own side is only ever given a CPU in a headless run, where
        its pool is the squads the mission lets that side deploy and its supports and pace are the mission's."""
        self.side = side
        self.mission = mission
        self.mood = mission.mood
        self.random_supports = mission.random_supports
        if side == mission.side:
            self.pool = [kind for kind, on in zip(UNIT_KINDS, mission.units[side], strict=True) if on]
        else:
            self.pool = list(mission.cpu_pool)
        self.supports = list(mission.cpu_supports)
        factors = DIFFICULTY[difficulty]
        self.squad_gap: float = factors["squad_gap"]
        self.support_gap: float = factors["support_gap"]
        # spawnEnemyTimer and its maximum (F6:6728, 7270); the support counter in slow ticks (F6:3996-4001)
        self.deploy_timer: float = FIRST_TRY
        self.deploy_max: float = mission.cpu_rate
        self.support_rate: float = mission.support_rate
        self.support_max: float = mission.support_rate
        self.support_wave = 0
        # Every unit type starts ready at each battle start (enemyTimers, F6:10909-10915, B54): the steps left on
        # its cooldown, 0 when it is ready. The cooldown is the unit's base time in steps, with no upgrades.
        self.cooldown = {kind: 0 for kind in UNIT_KINDS}

    def ready(self, kind: str) -> bool:
        return self.cooldown.get(kind) == 0

    def deploy_tick(self, battle: "Battle") -> None:
        """spawnEnemy (F6:4086-4231), one-second tick. The counter starts at 4 and a try comes when it goes below 0, so
        the first is 5 s in; it then starts again at R times the difficulty factor. A try deploys nothing when the
        pick is a "wait", is empty, costs more than the CPU has or is on cooldown."""
        if not battle.spawn_active:
            return
        self.deploy_timer -= 1
        if self.deploy_timer >= 0:
            return
        self.deploy_timer = self.deploy_max * self.squad_gap
        kind = self.pick(battle)
        if kind is None or kind not in UNIT_KINDS:
            return
        cost = UNITS[self.side][kind]["cost"]
        if battle.sides[self.side].rp < cost or not self.ready(kind):
            return
        lane = self.choose_lane(battle, kind)
        if lane is None:
            return
        make_squad(battle, self.side, kind, lane)
        battle.adjust_rp(self.side, -cost)
        self.cooldown[kind] = UNITS[self.side][kind]["cooldown"]

    def pick(self, battle: "Battle") -> str | None:
        """What this try aims to deploy. The draws are made in the original's order: one over the whole pool, then for
        each RP level reached a "wait" draw per pool entry and a pick draw."""
        rp = battle.sides[self.side].rp
        pick = self.choose(battle, self.pool)
        for need, kinds in TIERS:
            if rp < need:
                continue
            options = []
            for entry in self.pool:
                if entry in kinds and self.ready(entry):
                    options.append(entry)
                if battle.random(WAIT_CHANCE) == 0:
                    options.append("wait")
            pick = self.choose(battle, options)
        if rp >= TANK_RP and "tank" in self.pool and self.ready("tank"):
            pick = "tank"
        return pick

    @staticmethod
    def choose(battle: "Battle", items: list[str]) -> str | None:
        """items[random(len)], and nothing from an empty list"""
        return items[battle.random(len(items))] if items else None

    def choose_lane(self, battle: "Battle", kind: str) -> int | None:
        """chooseSpawnZone (F6:4232-4285): walking the foe's squads in deploy order, the lane of the last squad whose
        leader is further forward than the next squad's leader; 251 times in 1000 a random lane instead; lane 2 when
        none was found. A tank aimed at a lane with cover tries again. With no lane open to it the tank is not sent
        (the original would loop forever; no map reaches it)."""
        if kind == "tank" and all(battle.lane_has_cover(lane) for lane in LANES):
            return None
        foe = other_side(self.side)
        squads = battle.sides[foe].squads
        while True:
            lane = 0
            for index, squad in enumerate(squads[:-1]):
                after = squads[index + 1]
                if not squad.members or not after.members:
                    continue
                here, there = squad.members[0].x, after.members[0].x
                if (here > there) if foe == "british" else (here < there):
                    lane = squad.lane
            if battle.random(1000) <= RANDOM_LANE:
                lane = battle.random(3) + 1
            if lane == 0:
                lane = 2
            if kind == "tank" and battle.lane_has_cover(lane):
                continue
            return lane

    def run_timers(self, battle: "Battle") -> None:  # noqa: ARG002
        """runEnemyTimers (F6:4060-4074), the end of every unpaused step: each unit on cooldown counts down one"""
        for kind, left in self.cooldown.items():
            if left > 0:
                self.cooldown[kind] = left - 1

    def support_tick(self, battle: "Battle") -> None:
        """enemySupportGenerator (F6:4002-4058), slow tick: each time the counter goes below 0 (S + 1 ticks the first
        time, then S times the difficulty factor), call the next support on one of the foe's squads. With no squad to
        aim at nothing is called and the list does not move on. It goes on after a defend countdown ends."""
        self.support_rate -= 1
        if self.support_rate >= 0:
            return
        self.support_rate = self.support_max * self.support_gap
        target = self.support_target(battle)
        if target is None:
            return
        index = battle.random(len(self.supports)) if self.random_supports else self.support_wave
        if index < len(self.supports):
            call_strike(battle, self.supports[index], target.x, target.y, self.side)
        self.support_wave += 1
        if self.support_wave >= len(self.supports):
            self.support_wave = 0

    def support_target(self, battle: "Battle") -> Soldier | Tank | None:
        """The foe's member the strike lands on. Walking the foe's squads newest first (a for..in), a squad's leader
        wins when it is further forward than the first squad's leader (the original's reference is whatever the loop
        variable `x` was left at, which is the oldest squad), and each squad also rolls 1 in 5 to swap in a random
        squad's leader that stands inside the field (three separate random picks, as the original draws them)."""
        foe = other_side(self.side)
        squads = [squad for squad in battle.live_squads(foe) if squad.members]
        if not squads:
            return None
        reference = squads[0].members[0].x
        target = None
        for squad in battle.newest_first(squads):
            leader = squad.members[0]
            if (leader.x > reference) if foe == "british" else (leader.x < reference):
                target = leader
            if battle.random(5) == 0:
                swapped = self.swap_target(battle, squads)
                if swapped is not None:
                    target = swapped
        return target

    @staticmethod
    def swap_target(battle: "Battle", squads: list[Squad]) -> Soldier | Tank | None:
        count = len(squads)
        if squads[battle.random(count)].members[0].x > SWAP_NEAR_EDGE:
            if squads[battle.random(count)].members[0].x < battle.width - SWAP_FAR_EDGE:
                return squads[battle.random(count)].members[0]
        return None

    def cover_tick(self, battle: "Battle") -> None:
        """enemyUnitAI (F6:3865-3925), really-slow tick: every squad sitting fully in cover with no target rolls to
        leave it. Mortar teams and tanks never roll."""
        rolls = LEAVE_ROLLS.get(self.mood)
        if rolls is None:
            return
        # for (v in squads), F6:3867
        for squad in battle.newest_first(battle.live_squads(self.side)):
            if squad.state == "entrench" and squad.all_in_cover and squad.target is None:
                self.roll_leave(battle, squad, rolls)

    @staticmethod
    def roll_leave(battle: "Battle", squad: Squad, rolls: tuple[int, int, int]) -> None:
        """The three rolls are always drawn, in this order, whatever the squad's kind (the original's `random(n) == 0
        && type == ...` draws first)"""
        line, marksman, special = rolls
        leave = False
        if battle.random(line) == 0 and squad.kind in LINE_KINDS:
            leave = True
        if battle.random(marksman) == 0 and squad.kind in MARKSMAN_KINDS:
            leave = True
        if battle.random(special) == 0 and squad.kind in SPECIAL_KINDS:
            leave = True
        if leave:
            leave_cover(battle, squad)

    def place_squads(self, battle: "Battle") -> None:
        """startBattle's free squads (F6:6762-6791), on the battle clock: the bunker at 20 ms, then each lane's
        pre-placed squads at 3,000 ms times the lane, all members on one x, then the presets at their seconds. They
        belong to the mission's CPU side only, tanks and the American side's included (B52, W6). The end cancels them
        all (B53)."""
        mission = battle.mission
        if self.side == mission.side:
            return
        for lane in LANES:
            if mission.bunker is not None and mission.bunker[0] == lane:
                self.later(
                    battle,
                    BUNKER_DELAY_MS,
                    lambda x=mission.bunker[1], lane=lane: make_bunker(battle, self.side, lane, x),
                )
            for squad_lane, kind in mission.prespawns:
                if squad_lane == lane:
                    x = self.prespawn_x(battle, kind)
                    self.later(
                        battle,
                        PRESPAWN_MS * lane,
                        lambda kind=kind, lane=lane, x=x: make_squad(battle, self.side, kind, lane, x),
                    )
        for index, (seconds, kind, lane) in enumerate(mission.presets):
            objective = mission.objective == ("preset", index)
            x = battle.spawn_x(self.side)
            self.later(
                battle,
                seconds * 1000,
                lambda kind=kind, lane=lane, x=x, objective=objective: make_squad(
                    battle, self.side, kind, lane, x, objective
                ),
            )

    def prespawn_x(self, battle: "Battle", kind: str) -> float:
        """Where a pre-placed squad stands: the German side 300 in from its spawn point (a tank on the point itself),
        the American side 300 in from its own"""
        spawn = battle.spawn_x(self.side)
        if self.side == "german":
            return spawn if kind == "tank" else spawn - PRESPAWN_INSET
        return spawn + PRESPAWN_INSET

    @staticmethod
    def later(battle: "Battle", ms: float, fn: t.Callable[[], t.Any]) -> None:
        battle.spawn_timers.append(battle.after(ms, fn))
