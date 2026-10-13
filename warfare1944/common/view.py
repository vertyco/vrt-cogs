"""The battle as messages for the page: the whole battle when someone joins, then an update every 3 steps.

Everything is a whole number, a string or a list of those, packed into short lists to keep an update small (a battle
of 120 soldiers is under 6 KB of JSON). Positions and morale go out times 10 so one decimal survives; the page divides.
An update carries the whole state every time, since positions change every step anyway, plus the events taken since
the last update. A reader takes the events once per update and sends the same update to everyone watching.
"""

import typing as t

from .data import LANES, SIDES, SOLDIER_TYPES, UNIT_KINDS
from .morale import bonus_xp, stats
from .orders import greyed
from .smoke import Cloud
from .squads import STATES, Cover, Soldier, Squad, Tank

if t.TYPE_CHECKING:
    from .battle import Battle, Side

UPDATE_STEPS = 3  # the steps one update covers (common/lobby.py STEPS)
DIAL_FULL = 1000  # a full dial, as 0 to 1000
FLAG_OFFICER = 1  # bit 0: near an officer (silver star)
FLAG_PASSING = 2  # bit 1: passing through a cover
FLAG_SMOKED = 4  # bit 2: smoked
FLAG_IN_COVER = 8  # bit 3: every member is in its cover and Advance is allowed
FLAG_SMOKE_ROUNDS = 16  # bit 4: a mortar team firing its smoke rounds
FLAG_OBJECTIVE = 32  # bit 5: the objective
FLAG_SUPPRESSING = 64  # bit 6: Suppressing Fire shots left
FLAG_TARGET = 128  # bit 7: the squad has an enemy squad it is engaging (INTEL's "Engaging.")
BROKEN_BITS = {"mg": 1, "gun": 2, "engine": 4}
STATE_CODES = {name: index for index, name in enumerate(STATES)}
TYPE_CODES = {name: index for index, name in enumerate(SOLDIER_TYPES)}


def x10(value: float) -> int:
    return round(value * 10)


def squad_flags(squad: Squad) -> int:
    checks = (
        (squad.near_officer, FLAG_OFFICER),
        (squad.passing, FLAG_PASSING),
        (squad.smoked, FLAG_SMOKED),
        (not greyed(squad, "advance"), FLAG_IN_COVER),
        (squad.firing_smoke, FLAG_SMOKE_ROUNDS),
        (squad.objective, FLAG_OBJECTIVE),
        (squad.suppress > 0, FLAG_SUPPRESSING),
        (squad.target is not None and len(squad.target.members) > 0, FLAG_TARGET),
    )
    return sum(bit for on, bit in checks if on)


def soldier_row(soldier: Soldier, step: int) -> list[int]:
    """[id, x10, y10, frame, playing, stamp, scale, type, then the earlier jumps as frame, playing, stamp, newest
    first]. The newest jump is the one the clip is on; the earlier ones are its other jumps of this update's steps, so
    a page that draws a step between two of them makes both. Jumps from before those steps went out in an earlier
    update."""
    frame, playing, stamp = soldier.jumps[-1]
    row = [
        soldier.id,
        x10(soldier.x),
        x10(soldier.y),
        frame,
        int(playing),
        stamp,
        round(soldier.scale * 100),
        TYPE_CODES[soldier.type],
    ]
    for frame, playing, stamp in reversed(soldier.jumps[:-1]):
        if stamp >= step - UPDATE_STEPS:
            row.extend((frame, int(playing), stamp))
    return row


def tank_row(tank: Tank) -> list[int]:
    """[id, x10, y10, health x10, gun stamp, mg stamp, wrecked, turret frame, turret playing, turret stamp, broken
    parts: 1 machine gun, 2 main gun, 4 engine]"""
    return [
        tank.id,
        x10(tank.x),
        x10(tank.y),
        x10(max(tank.health, 0)),
        tank.gun_stamp,
        tank.mg_stamp,
        0 if tank.alive else 1,
        tank.turret.frame,
        int(tank.turret.playing),
        tank.turret_stamp,
        sum(BROKEN_BITS[part] for part in tank.broken),
    ]


def member_row(member: Soldier | Tank, step: int) -> list[int]:
    return tank_row(member) if isinstance(member, Tank) else soldier_row(member, step)


def squad_row(squad: Squad, members: list[Soldier | Tank], step: int) -> list:
    """[squad id, side, slot (9 the bunker), state code, flags, pool x10, lane, cover index or -1, members]"""
    return [
        squad.id,
        SIDES.index(squad.side),
        squad.slot,
        STATE_CODES[squad.state],
        squad_flags(squad),
        x10(max(squad.pool, 0)),
        squad.lane,
        -1 if squad.cover is None else squad.cover.index,
        [member_row(member, step) for member in members],
    ]


def squad_rows(battle: "Battle") -> list[list]:
    """Every squad with a member on the field, then the burning wrecks, which stay on the field in a squad of their
    own (a destroyed tank's squad leaves its side's list)"""
    step = battle.step
    rows = [
        squad_row(squad, squad.members, step) for side in battle.sides.values() for squad in side.squads if squad.leader
    ]
    rows.extend(squad_row(wreck.squad, [wreck], step) for wreck in battle.wrecks)
    return rows


def cover_row(cover: Cover) -> list[int]:
    """[holder squad id or 0, owner -1 none, 0 British, 1 German]"""
    owner = -1 if cover.owner is None else SIDES.index(cover.owner)
    return [0 if cover.holder is None else cover.holder.id, owner]


def fill(count: float, size: float, on: bool) -> int:
    """A dial's fill as 0 to 1000; a slot the mission doesn't allow stays empty"""
    if not on or size <= 0:
        return 0
    return min(DIAL_FULL, round(count / size * DIAL_FULL))


def dials(side: "Side") -> list[int]:
    return [fill(c, m, on) for c, m, on in zip(side.cooldown, side.cooldown_max, side.units, strict=True)]


def cloud_row(cloud: Cloud) -> list[int]:
    """[cloud id, x10, y10, side, step its fade starts]"""
    return [cloud.id, x10(cloud.x), x10(cloud.y), SIDES.index(cloud.owner), cloud.fade_start]


def state(battle: "Battle") -> dict:
    british, german = battle.sides["british"], battle.sides["german"]
    return {
        "q": squad_rows(battle),
        "c": [cover_row(cover) for cover in battle.covers],
        "k": [cloud_row(cloud) for cloud in battle.smoke],
        "m": [x10(british.morale), x10(german.morale), x10(british.morale_max), x10(german.morale_max)],
        # Ground taken, then whether each side has no front squad (its bar flashes dark red on every slow tick, F6:5727-5738)
        # and the slow ticks run so far, which the page counts to redo that flash
        "f": [
            british.ground,
            german.ground,
            int(british.front_squad is None),
            int(german.front_squad is None),
            battle.slow_ticks,
        ],
        "r": [british.rp, german.rp, british.rp_cap, german.rp_cap, battle.refill_dial()],
        "h": {name: dials(side) for name, side in battle.sides.items()},
        "t": [battle.mission_seconds, -1 if battle.defend_left is None else battle.defend_left],
    }


def update(battle: "Battle", step: int, run_id: str | int | None = None) -> dict:
    """The 3-step update: the whole state and the events since the last one (taken, so call it once per update and
    send the result to everyone). `step` is the step the update is for; `run_id` adds the run's id when the sender
    keeps several battles on one connection."""
    body: dict = {"step": step, "paused": battle.paused, "s": state(battle), "e": battle.take_events()}
    if run_id is not None:
        body["id"] = run_id
    return {"u": body}


def result(battle: "Battle", next_screen: str) -> dict:
    """The results screen's numbers (postBattleScreen, F6:6952-7186). XP is the campaign side's own: kill XP on a
    first try, and bonus XP on a win. Custom and versus battles pay none."""
    side = battle.mission.side
    first = battle.campaign and battle.first_try
    return {
        "winner": battle.winner,
        "how": battle.how,
        "stats": stats(battle),
        "seconds": battle.mission_seconds,
        "bonus_xp": bonus_xp(battle, side),
        "kill_xp": battle.kill_xp[side] if first else 0,
        "next": next_screen,
    }


def map_view(battle: "Battle") -> dict:
    mission = battle.mission
    return {
        "art": mission.art,
        "width": mission.width,
        "rain": mission.rain,
        "lanes": list(LANES),
        "covers": [list(cover) for cover in mission.covers],
        "wire": list(mission.wires),
        "title": mission.title,
        "mission": mission.number,
        "side": mission.side,
        "timed": mission.timed is not None,
    }


def full(
    run: t.Any,
    battle: "Battle",
    you: str | None,
    names: dict[str, str | None],
    watchers: list[dict],
    next_screen: str = "menu",
) -> dict:
    """The whole battle, for a player who starts, joins, rejoins or watches. `run` supplies the id and kind. `you` is
    the viewer's side, or None for a watcher. `next_screen` goes into the result of a battle that has ended. This
    reads the state and takes no events."""
    ended = battle.state == "ended"
    sides = battle.sides
    return {
        "battle": {
            "id": run.id,
            "kind": run.kind,
            "you": you,
            "names": {name: names.get(name) for name in SIDES},
            "map": map_view(battle),
            "units": {name: list(side.units) for name, side in sides.items()},
            "costs": {name: [battle.cost(name, slot) for slot in range(1, len(UNIT_KINDS) + 1)] for name in SIDES},
            "orders": {name: sorted(side.orders) for name, side in sides.items()},
            "upgrades": {name: sorted(side.upgrades) for name, side in sides.items()},
            "difficulty": battle.difficulty,
            "step": battle.step,
            "paused": battle.paused,
            "s": state(battle),
            "watchers": watchers,
            # Where the player of the side a watcher watches is looking, if their page has said
            "camera": run.camera.get(battle.mission.side),
            "result": result(battle, next_screen) if ended else None,
        }
    }
