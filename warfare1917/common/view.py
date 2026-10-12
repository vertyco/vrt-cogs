"""The battle as messages for the page: the whole battle when someone joins, then an update every 3 steps.

Everything is a whole number, a string or a list of those, packed into short lists to keep an update small (a battle
of 100 soldiers is under 6 KB of JSON). Positions and morale go out times 10 so one decimal survives; the page divides.
An update carries the whole state every time, since positions change every step anyway, plus the events taken since
the last update. A reader takes the events once per update and sends the same update to everyone watching.
"""

import typing as t

from .data import SIDES, SOLDIER_TYPES
from .gas import Cloud
from .morale import bonus_xp, stats
from .squads import STATES, Soldier, Squad, Tank, Trench

if t.TYPE_CHECKING:
    from .battle import Battle, Side

DIAL_FULL = 1000  # a full dial, as 0 to 1000
FLAG_OFFICER = 1  # bit 0: near an officer (silver star)
FLAG_MASKS = 2  # bit 1: masks on
FLAG_MASKS_MOVING = 4  # bit 2: masks going on or off
FLAG_PASSING = 8  # bit 3: passing through
STATE_CODES = {name: index for index, name in enumerate(STATES)}
TYPE_CODES = {name: index for index, name in enumerate(SOLDIER_TYPES)}


def x10(value: float) -> int:
    return round(value * 10)


def squad_flags(squad: Squad) -> int:
    flags = FLAG_OFFICER if squad.near_officer else 0
    if squad.masks == "on":
        flags |= FLAG_MASKS
    elif squad.masks in ("on_going", "off_going"):
        flags |= FLAG_MASKS_MOVING
    if squad.passing:
        flags |= FLAG_PASSING
    return flags


def soldier_row(soldier: Soldier) -> list[int]:
    """[id, x10, y10, frame, playing, stamp, scale, type, then the earlier jumps as frame, playing, stamp, newest
    first]. The newest jump is the one the clip is on; the earlier ones are its other jumps of the last few steps, so
    a page that draws a step between two of them makes both"""
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
        row.extend((frame, int(playing), stamp))
    return row


def tank_row(tank: Tank) -> list[int]:
    return [
        tank.id,
        x10(tank.x),
        x10(tank.y),
        x10(max(tank.health, 0)),
        tank.gun_stamp,
        tank.mg_stamp,
        0 if tank.alive else 1,
    ]


def member_row(member: Soldier | Tank) -> list[int]:
    return tank_row(member) if isinstance(member, Tank) else soldier_row(member)


def squad_row(squad: Squad, members: list[Soldier | Tank]) -> list:
    """[squad id, side, slot, state code, flags, pool x10, trench index or -1, members]"""
    return [
        squad.id,
        SIDES.index(squad.side),
        squad.slot,
        STATE_CODES[squad.state],
        squad_flags(squad),
        x10(max(squad.pool, 0)),
        -1 if squad.trench is None else squad.trench.index,
        [member_row(member) for member in members],
    ]


def squad_rows(battle: "Battle") -> list[list]:
    """Every squad with a member on the field, then the burning wrecks, which stay on the field in a squad of their
    own (a destroyed tank's squad leaves its side's list)"""
    rows = [squad_row(squad, squad.members) for side in battle.sides.values() for squad in side.squads if squad.leader]
    rows.extend(squad_row(wreck.squad, [wreck]) for wreck in battle.wrecks)
    return rows


def trench_row(trench: Trench) -> list:
    owner = -1 if trench.owner is None else SIDES.index(trench.owner)
    return [owner, int(trench.locked), [0 if squad is None else squad.id for squad in trench.slots]]


def cloud_row(cloud: Cloud, step: int) -> list[int]:
    fading = step >= cloud.fade_start
    return [cloud.id, x10(cloud.x), x10(cloud.y), SIDES.index(cloud.owner), cloud.fade_start if fading else -1]


def fill(count: float, size: float, on: bool) -> int:
    """A dial's fill as 0 to 1000; a slot the mission doesn't allow stays empty"""
    if not on or size <= 0:
        return 0
    return min(DIAL_FULL, round(count / size * DIAL_FULL))


def dials(side: "Side") -> list:
    units = [fill(c, m, on) for c, m, on in zip(side.unit_timer, side.unit_timer_max, side.units, strict=True)]
    supports = [
        fill(c, m, on) for c, m, on in zip(side.support_timer, side.support_timer_max, side.supports, strict=True)
    ]
    return [units, supports, int(side.gas_button)]


def state(battle: "Battle") -> dict:
    british, german = battle.sides["british"], battle.sides["german"]
    return {
        "q": squad_rows(battle),
        "t": [trench_row(trench) for trench in battle.trenches],
        "g": [cloud_row(cloud, battle.step) for cloud in battle.gas],
        "m": [x10(british.morale), x10(german.morale), x10(british.morale_max), x10(german.morale_max)],
        "f": [
            british.ground,
            german.ground,
            int(british.front_squad is None),
            int(german.front_squad is None),
            battle.slow_ticks,
        ],
        "h": {name: dials(side) for name, side in battle.sides.items()},
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
    """The results screen's numbers (postBattleScreen, F5:4358-4469). XP is the campaign side's own: kill XP on a
    first try, and bonus XP on a win. Custom and versus battles pay none."""
    side = battle.mission.side
    first = battle.campaign and battle.first_try
    return {
        "winner": battle.winner,
        "how": battle.how,
        "stats": stats(battle),
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
        "trenches": list(mission.trenches),
        "wire": list(mission.wires),
        "title": mission.title,
        "mission": mission.number,
        "side": mission.side,
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
            "supports": {name: list(side.supports) for name, side in sides.items()},
            "upgrades": {name: sorted(side.upgrades) for name, side in sides.items()},
            "step": battle.step,
            "paused": battle.paused,
            "s": state(battle),
            "watchers": watchers,
            # Where the player of the side a watcher watches is looking, if their page has said
            "camera": run.camera.get(battle.mission.side),
            "result": result(battle, next_screen) if ended else None,
        }
    }
