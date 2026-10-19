"""The win check, the stuck check with its repair and fail names, and the auto-finisher.

Both checks are timed waits that something starts and anything later restarts, as the original's coroutines are
(GameFinishController$$StartCheckToWin and MapFailController$$TryCheckForCannotShootFail stop the running wait before
starting a new one). Their timers fire in the checks phase. The stuck check's repair returns the pigs it emptied for
the core to make vanish, so this module never imports places. web/sim/checks.js mirrors this file.
"""

from __future__ import annotations

from . import base
from . import grid as gridx
from .mathx import idiv
from .numbers import STUCK_DELAY, STUCK_INPUT_EXTRA, WIN_DELAY

# Queue-front blockers and grid blockers a stuck fail can be named after, in the order that wins a tie
# (MapFailController$$TriggerBlockerFail, RVA 0x58E585C)
FRONT_NAMES = ["locked_out", "frozen", "totem"]
GRID_NAMES = ["ufo", "curtain", "spaceship"]


def request_win_check(state: base.State) -> None:
    """A pig is about to vanish, a feature left the grid or a target died: (re)start the wait before the win check
    (GameFinishController$$StartCheckToWin, RVA 0x5250D14, restarts <CheckToWinEnumerator>d__29)."""
    base.cancel(state, "win_check")
    base.schedule(state, WIN_DELAY, "win_check", None)


def win_check(state: base.State, args: None) -> None:  # noqa: ARG001
    """Timer: once nothing holds the finish back (checked every tick), the level is won when no pigs are left
    anywhere (<CheckToWinEnumerator>d__29$$MoveNext, RVA 0x526CF14; MapProvider$$IsMapCleared, RVA 0x58E7F3C)."""
    if state.over is not None:
        return
    for module in base.MODULES:
        hook = getattr(module, "holds_finish", None)
        if hook is not None and hook(state):
            base.schedule(state, 1, "win_check", None)
            return
    if base.live_pig_count(state) == 0:
        state.over = {"result": "won", "tick": state.tick, "kind": None, "name": None}
        base.emit(state, "won", {})


def request_stuck_check(state: base.State) -> None:
    """A pig was tapped, left a queue, landed in a slot or is about to vanish, or the last shot in flight ended:
    (re)start the stuck check's wait (MapFailController$$TryCheckForCannotShootFail, RVA 0x58DFB98, from the handlers
    OnEnable subscribes)."""
    base.cancel(state, "stuck_check")
    base.schedule(state, STUCK_DELAY, "stuck_check", "look")


def stuck_check(state: base.State, stage: str) -> list[int] | None:
    """Timer (MapFailController.<CheckForCannotShootFail>d__41$$MoveNext, RVA 0x58E7A8C). "look": after the first
    wait, and then every tick until nothing is mid-action, decide whether the level is stuck; a stuck level blocked
    only by input-only blockers waits STUCK_INPUT_EXTRA more and then acts on that decision without looking again
    ("act"). Acting fails the level when every color's ammo fits what is left of it, else repairs. Returns the pigs
    the repair emptied, in the order they vanish, or None when it did not repair."""
    if state.over is not None:
        return None
    if stage == "look":
        if busy(state):
            base.schedule(state, 1, "stuck_check", "look")
            return None
        input_only = input_only_blocked(state)
        stuck = (input_only or not can_shoot_any(state)) and base.live_pig_count(state) > 0
        if not stuck:
            return None
        if input_only:
            base.schedule(state, STUCK_INPUT_EXTRA, "stuck_check", "act")
            return None
    extras = extra_ammo(state)
    if not extras:
        base.fail(state, "stuck", fail_name(state))
        return None
    return repair(state, extras)


def busy(state: base.State) -> bool:
    """Something is mid-action: a shot in flight or a feature's own action (FailCheckDelayCondition: a lock opening,
    a mallet or hammer working, a Hungry Door finishing, a spaceship launching, a Pixel Mixer releasing)."""
    if state.shots:
        return True
    for module in base.MODULES:
        hook = getattr(module, "busy", None)
        if hook is not None and hook(state):
            return True
    return False


def front_blocker(state: base.State, pig: base.Pig) -> str | None:
    """The fail name of the feature blocking a queue-front entry, or None."""
    for module in base.MODULES:
        hook = getattr(module, "blocker", None)
        if hook is not None:
            name = hook(state, pig)
            if name is not None:
                return name
    return None


def fronts(state: base.State) -> list[base.Pig]:
    return [state.pigs[queue[0]] for queue in state.queues if queue]


def normally_tappable(state: base.State, pig: base.Pig) -> bool:
    """A queue front that could be tapped if a tray were free: nothing disabling or locking it and no feature against
    it (MapFailController$$<NormallyTappableFirstShooterExists>b__50_0, the additive tap conditions). A feature with a
    can_tap_normally hook answers through it instead of can_tap (a Connected group needn't fit on the belt here)."""
    if "untappable" in pig.tags or "disabled" in pig.tags:
        return False
    for module in base.MODULES:
        normal = getattr(module, "can_tap_normally", None)
        if normal is not None:
            if normal(state, pig) is not None:
                return False
            continue
        hook = getattr(module, "can_tap", None)
        if hook is not None and hook(state, pig, False) is not None:
            return False
    return True


def tappable_front_exists(state: base.State) -> bool:
    """MapFailController$$NormallyTappableFirstShooterExists, RVA 0x58DFF18."""
    return any(normally_tappable(state, pig) for pig in fronts(state))


def input_only_blocked(state: base.State) -> bool:
    """No queue front can be tapped and every queue front is a Bull Totem
    (MapFailController$$AreAllQueuesBlockedByInputOnlyBlockers, RVA 0x58E1188)."""
    front = fronts(state)
    if not front or tappable_front_exists(state):
        return False
    return all(front_blocker(state, pig) == "totem" for pig in front)


def live_pigs(state: base.State) -> list[base.Pig]:
    """Pigs whose place is on the map, by id."""
    return [state.pigs[pig_id] for pig_id in sorted(state.pigs) if state.pigs[pig_id].place not in ("gone", "held")]


def usable_pigs(state: base.State) -> list[base.Pig]:
    """With a tappable queue front, every pig on the map that isn't disabled; otherwise only the pigs outside the
    queues that can be tapped (MapFailController$$CanShootAnyTargetNew, RVA 0x58DFBEC: GetNotDisabledShooters or
    GetShootersOutsideOfQueue)."""
    live = live_pigs(state)
    if tappable_front_exists(state):
        return [pig for pig in live if "disabled" not in pig.tags]
    return [pig for pig in live if pig.place != "queue" and "untappable" not in pig.tags]


def matches(target: gridx.Target, color: int) -> bool:
    """The target takes shots of this color (HitTarget$$IsTargetMatch, RVA 0x544E608)."""
    return target.match_all or target.color == color or (target.colors is not None and color in target.colors)


def can_shoot_any(state: base.State) -> bool:
    """Some usable pig with ammo has a color some exposed target takes (MapFailController$$CanShoot, RVA 0x58DFFF8)."""
    targets = exposed_targets(state)
    for pig in usable_pigs(state):
        if pig.ammo >= 1 and any(matches(target, pig.color) for target in targets):
            return True
    return False


def ignored_obstacles(state: base.State) -> set[int]:
    """Target ids of obstacles the stuck check sees through, such as wood blocks and Music Toys: a level is never
    called stuck because of them, though they still stop real shots (MapFailController$$RebuildIgnoredObstaclesCache,
    RVA 0x58E0A1C)."""
    ignored: set[int] = set()
    for module in base.MODULES:
        hook = getattr(module, "ignored_obstacles", None)
        if hook is not None:
            ignored.update(hook(state))
    return ignored


def blocked_cells(state: base.State, ignored: set[int]) -> list[int]:
    """1 for every cell holding something solid that the check doesn't see through, else 0. A cube always counts."""
    grid = state.grid
    blocked = [0] * (grid.width * grid.height)
    for cell, occupants in enumerate(grid.cells):
        for target_id in occupants:
            target = grid.targets[target_id]
            if gridx.is_solid(target) and (target.owner == 0 or target_id not in ignored):
                blocked[cell] = 1
                break
    return blocked


def clear_lines(grid: gridx.Grid, blocked: list[int], axis: int) -> list[int]:
    """1 for every cell reached from either end of its row (or column) through cells that aren't blocked."""
    clear = [0] * len(blocked)
    count = grid.height if axis == gridx.AXIS_ROW else grid.width
    for line in range(count):
        for side in (gridx.FROM_START, gridx.FROM_END):
            for cell in gridx.line_cells(grid, axis, line, side):
                if blocked[cell]:
                    break
                clear[cell] = 1
    return clear


def exposed(grid: gridx.Grid, rows: list[int], columns: list[int], cell: int) -> bool:
    """On an edge, or the neighbor beside it is clear along its row, or the neighbor above or below it is clear along
    its column."""
    width, height = grid.width, grid.height
    x = cell % width
    y = idiv(cell, width)
    if x == 0 or y == 0 or x == width - 1 or y == height - 1:
        return True
    return bool(rows[cell - 1] or rows[cell + 1] or columns[cell - width] or columns[cell + width])


def exposed_targets(state: base.State) -> list[gridx.Target]:
    """Every live hit target in an exposed cell. In a cell holding an obstacle the check doesn't see through, only
    targets that are obstacles themselves count, not the cube under them
    (PixelGridController$$GetObjectsExposedToAnyGridEdgeAxisAligned, RVA 0x6644F40)."""
    grid = state.grid
    ignored = ignored_obstacles(state)
    blocked = blocked_cells(state, ignored)
    rows = clear_lines(grid, blocked, gridx.AXIS_ROW)
    columns = clear_lines(grid, blocked, gridx.AXIS_COLUMN)
    targets = []
    for cell, occupants in enumerate(grid.cells):
        if not occupants or not exposed(grid, rows, columns, cell):
            continue
        here = [grid.targets[target_id] for target_id in occupants]
        walled = any(t.obstacle and t.owner != 0 and t.id not in ignored for t in here)
        for target in here:
            if target.hittable and not target.dead and (not walled or (target.obstacle and target.owner != 0)):
                targets.append(target)
    return targets


def most_common(counts: dict[str, int], order: list[str]) -> str | None:
    """The name with the highest count, the earlier in order on a tie; None when every count is 0."""
    best = None
    for name in order:
        if counts.get(name, 0) > 0 and (best is None or counts[name] > counts[best]):
            best = name
    return best


def fail_name(state: base.State) -> str:
    """What a stuck fail is called (MapFailController$$TriggerBlockerFail, RVA 0x58E585C): with no tappable queue
    front, after the most common blocker at the queue fronts; else after the most common of U.F.O.s, curtains and
    spaceships on the grid; else the general obstacle fail."""
    if not tappable_front_exists(state):
        counts: dict[str, int] = {}
        for pig in fronts(state):
            name = front_blocker(state, pig)
            if name is not None:
                counts[name] = counts.get(name, 0) + 1
        name = most_common(counts, FRONT_NAMES)
        if name is not None:
            return name
    grid_counts: dict[str, int] = {}
    for module in base.MODULES:
        hook = getattr(module, "fail_counts", None)
        if hook is not None:
            for name, count in hook(state).items():
                grid_counts[name] = grid_counts.get(name, 0) + count
    return most_common(grid_counts, GRID_NAMES) or "obstacles"


def ammo_pigs(state: base.State) -> list[base.Pig]:
    """Pigs on the map that carry ammo for the count, by id (ShooterProvider$$GetAllShootersByMaterial)."""
    return [pig for pig in live_pigs(state) if "disabled" not in pig.tags]


def hits_left(state: base.State, color: int) -> int:
    """Hits still needed for this color: its cubes' health plus what shot features of that color still take."""
    total = 0
    for target in state.grid.targets:
        if target.owner == 0 and not target.dead and target.color == color:
            total += target.health
    for module in base.MODULES:
        hook = getattr(module, "remaining_hits", None)
        if hook is not None:
            total += hook(state, color)
    return total


def extra_ammo(state: base.State) -> list[list[int]]:
    """[color, extra] for every color whose pigs carry more ammo than it has hits left, by color
    (MapFailController$$CheckShootersAndPixelsInSync, RVA 0x58E509C)."""
    ammo: dict[int, int] = {}
    for pig in ammo_pigs(state):
        ammo[pig.color] = ammo.get(pig.color, 0) + pig.ammo
    extras = []
    for color in sorted(ammo):
        extra = ammo[color] - hits_left(state, color)
        if extra > 0:
            extras.append([color, extra])
    return extras


def screen_order(state: base.State, pig: base.Pig) -> list[int]:
    """Lowest on the screen first: the back rows of the queues, then the slot row, the exit line and the rescue row,
    then the belt. The original sorts by the pig's world z (MapController.<>c$$<SyncShootersAndPixels>b__74_1)."""
    for index, queue in enumerate(state.queues):
        if pig.id in queue:
            return [0, -queue.index(pig.id), index]
    if pig.place == "belt":
        return [2, 0, pig.id]
    return [1, 0, pig.id]


def repair(state: base.State, extras: list[list[int]]) -> list[int]:
    """Instead of failing, take the extra ammo away, lowest pigs first, and return the pigs left empty, after every
    pig already empty (MapController$$SyncShootersAndPixels, RVA 0x58D1F50). The core makes them vanish and then
    tries the auto-finisher."""
    emptied = [pig.id for pig in ammo_pigs(state) if pig.ammo == 0]
    for color, extra in extras:
        pigs = [pig for pig in ammo_pigs(state) if pig.color == color]
        pigs.sort(key=lambda pig: screen_order(state, pig))
        for pig in pigs:
            take = min(pig.ammo, extra)
            if take == 0:
                continue
            pig.ammo -= take
            extra -= take
            base.emit(state, "ammo_trimmed", {"pig": pig.id, "ammo": pig.ammo})
            if pig.ammo == 0:
                emptied.append(pig.id)
    return emptied


def try_autofinish(state: base.State) -> None:
    """Start the auto-finisher once the pigs left anywhere fit on the belt's trays (MapController$$TryActivateAutoFinisher,
    RVA 0x58CD8A0): from then on the belt runs twice as fast, pigs fire faster and trays loop instead of leaving
    (MapAutoFinisherController$$OnAutoFinisherActivated, RVA 0x58CB6D8). Features react through on_autofinish."""
    if state.finishing or base.live_pig_count(state) > state.tray_total:
        return
    state.finishing = True
    base.emit(state, "autofinish", {})
    base.call_hooks(state, "on_autofinish")
