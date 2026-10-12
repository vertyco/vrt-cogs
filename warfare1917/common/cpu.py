"""The CPU side: when it deploys squads, when it calls fire support, and when it sends its trench squads out.

Every method runs from the battle's slow tick (every 40 steps, F5:6828-6842). The CPU deploys through the same squad
making as a human (`make_squad`), with no deploy timers and no upgrades.
"""

import typing as t

from .blasts import launch
from .data import SUPPORT_KINDS, UNIT_KINDS
from .missions import Mission, other_side
from .squads import Soldier, Squad, Tank, Trench, make_squad

if t.TYPE_CHECKING:
    from .battle import Battle

CHARGE_DELAY_MS = 4000  # a full trench charges out this long after the roll, F5:2533
SWAP_NEAR_EDGE = 100  # the random support target must be past x 100 ...
SWAP_FAR_EDGE = 150  # ... and short of the field's width minus this, F5:2693-2695
FIRST_SQUAD_RATE = 10  # the first squad comes once the counter is down to this, F5:2613

# Per mood, the chance denominators (1 in n) of leaving a trench by squad kind, F5:2540-2597
LEAVE_CHANCES = {
    "aggressive": {"line": 5, "sniper": 10, "special": 20},
    "balanced": {"line": 10, "sniper": 20, "special": 30},
    "defensive": {"line": 20, "sniper": 35, "special": 60},
}
# Per mood, the chance denominator of a full trench charging out together (defensive never does), F5:2532
CHARGE_CHANCES = {"aggressive": 15, "balanced": 30}
LINE_KINDS = ("riflemen", "assault")
SPECIAL_KINDS = ("officer", "machineGun")


class Cpu:
    def __init__(self, side: str, mission: Mission):
        """`side` is the side the CPU plays. The mission's own side is only ever given to a CPU in a headless run,
        where the allowed units and supports are its lists."""
        self.side = side
        self.mood = mission.mood
        self.random_picks = mission.random_picks
        if side == mission.side:
            self.squads = [kind for kind, on in zip(UNIT_KINDS, mission.units[side], strict=True) if on]
            self.supports = [kind for kind, on in zip(SUPPORT_KINDS, mission.supports[side], strict=True) if on]
        else:
            self.squads = list(mission.cpu_squads)
            self.supports = list(mission.cpu_supports)
        # setupEnemyUnitGenerator / setupEnemySupportGenerator, F5:2604-2609, 2664-2669
        self.unit_rate_max = mission.cpu_rate
        self.unit_rate = mission.cpu_rate
        self.unit_wave = 0
        self.first_squad = True
        self.support_rate_max = mission.support_rate
        self.support_rate = mission.support_rate
        self.support_wave = 0

    def squads_tick(self, battle: "Battle") -> None:
        """enemyUnitGenerator (F5:2610-2663): the first squad once the counter reaches 10, then one each time it goes
        below 0, or sooner while the foe holds half the ground (B13: half the rate, not half the current count)"""
        if not self.squads:
            return
        self.unit_rate -= 1
        if self.first_squad and self.unit_rate <= FIRST_SQUAD_RATE:
            self.first_squad = False
            self.unit_rate = self.unit_rate_max
            self.deploy(battle)
        if self.unit_rate < 0:
            self.next_squad(battle)
        if battle.sides[self.side].panic and self.unit_rate <= self.unit_rate_max / 2:
            self.next_squad(battle)

    def next_squad(self, battle: "Battle") -> None:
        """The next entry of the list, going back to the top after the last (B10: no empty turn)"""
        self.unit_rate = self.unit_rate_max
        self.unit_wave += 1
        if self.unit_wave >= len(self.squads):
            self.unit_wave = 0
        self.deploy(battle)

    def deploy(self, battle: "Battle") -> None:
        if self.random_picks:
            kind = self.squads[battle.random(len(self.squads))]
        else:
            kind = self.squads[self.unit_wave]
        make_squad(battle, self.side, kind)

    def support_tick(self, battle: "Battle") -> None:
        """enemySupportGenerator (F5:2670-2719): each time the counter goes below 0, call the next support on one of
        the foe's squads. With no squad to aim at nothing is called and the list does not move on."""
        self.support_rate -= 1
        if self.support_rate >= 0:
            return
        self.support_rate = self.support_rate_max
        target = self.support_target(battle)
        if target is None:
            return
        if self.random_picks:
            index = battle.random(len(self.supports))
        else:
            index = self.support_wave
        if index < len(self.supports):
            launch(battle, self.supports[index], target.x, self.side)
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

    def trench_tick(self, battle: "Battle") -> None:
        """enemyUnitAI (F5:2524-2597): full trenches may charge out together, then every squad sitting fully in a
        trench with nothing to shoot may leave it (B11: every squad rolls, not only the first)"""
        chance = CHARGE_CHANCES.get(self.mood)
        # for (t in trenches), F5:2526
        for trench in battle.newest_first(battle.trenches):
            if trench.owner != self.side or any(slot is None for slot in trench.slots):
                continue
            if chance is not None and battle.random(chance) == 0:
                battle.after(CHARGE_DELAY_MS, lambda trench=trench: self.charge(battle, trench))
        chances = LEAVE_CHANCES[self.mood]
        # for (v in squads), F5:2536
        for squad in battle.newest_first(battle.live_squads(self.side)):
            if squad.state == "entrench" and squad.all_in_trench and squad.target is None:
                self.roll_leave(battle, squad, chances)

    @staticmethod
    def roll_leave(battle: "Battle", squad: Squad, chances: dict[str, int]) -> None:
        """The three rolls are always drawn, in this order, whatever the squad's kind (the original's `random(n) == 0
        && type == ...` draws first)"""
        leave = False
        if battle.random(chances["line"]) == 0 and squad.kind in LINE_KINDS:
            leave = True
        if battle.random(chances["sniper"]) == 0 and squad.kind == "sniper":
            leave = True
        if battle.random(chances["special"]) == 0 and squad.kind in SPECIAL_KINDS:
            leave = True
        if leave:
            squad.state = "exitTrench"

    @staticmethod
    def charge(battle: "Battle", trench: Trench) -> None:
        """enemyCharge (F5:2598-2603): whoever sits in the trench's three slots now goes over the top"""
        if battle.state != "playing":
            return
        for squad in trench.slots:
            if squad is not None:
                squad.state = "exitTrench"
