"""Boosters and the revive.

A booster's pick and animation happen on the page with its clock stopped, so its whole effect lands in the one tap
that applies it. The revive is the bot's tap after a fail: the map pauses (the belt stands still, the exit line's
grace stops counting and pigs can't be tapped) while it works, then play goes on. web/sim/boosters.js mirrors this
file.
"""

from __future__ import annotations

from . import aim, base, belt, checks, places
from . import grid as gridx
from .numbers import BOMB_DAMAGE, BOMB_SIZE, HOP, REVIVE_DELAY, REVIVE_GAP, SHOT_DAMAGE


def apply_tray(state: base.State) -> str | None:
    """The Tray booster: one more tray on the belt for the rest of the level (TrayPowerupController.<ExecutePowerup>
    d__14$$MoveNext, RVA 0x52CB220, -> ConveyorController$$AddSlot, RVA 0x58AA75C). The booster buttons only work
    while the auto-finisher isn't running (resources #9814). Returns why it was refused, or None."""
    if state.finishing:
        return "auto-finisher running"
    state.tray_total += 1
    base.emit(state, "tray_added", {"trays": state.tray_total})
    return None


def apply_hand(state: base.State, queue: int, index: int) -> str | None:
    """The Hand booster's pick: that one pig is taken from anywhere in its queue and placed on the belt like a front
    pig (HandPowerupController$$PerformPowerup, RVA 0x52D9F80; CanTapShooterCondition$$CheckMainConditions, RVA
    0x58B3258, rule 2: with the Hand on any queue pig can be tapped, and only the busy, belt-full and feature rules
    still apply). A feature's own tap (a hammer, frozen block or mallet) runs through its on_tap with `hand` true.
    The buttons only work while the auto-finisher isn't running. Returns why it was refused, or None."""
    if state.finishing:
        return "auto-finisher running"
    if queue < 0 or queue >= len(state.queues):
        return "no such queue"
    if index < 0 or index >= len(state.queues[queue]):
        return "no such pig"
    return places.tap_pig(state, state.pigs[state.queues[queue][index]], True)


def feature_pinned(state: base.State, pig: base.Pig) -> bool:
    """True for a pig with any feature on it: a tag, or a feature module that lists it (ShooterCanShuffleCondition$$
    Call, RVA 0x5905C38, lets only pigs with no feature through)."""
    if pig.tags:
        return True
    for module in base.MODULES:
        hook = getattr(module, "pins", None)
        if hook is not None and hook(state, pig.id):
            return True
    return False


def shuffle_spots(state: base.State) -> list[list[int]]:
    """[queue, index] of every plain pig, queue by queue, front to back."""
    spots = []
    for queue_index, queue in enumerate(state.queues):
        for index, pig_id in enumerate(queue):
            if not feature_pinned(state, state.pigs[pig_id]):
                spots.append([queue_index, index])
    return spots


def can_shuffle(state: base.State) -> bool:
    """Shuffling needs at least two plain pigs, else nothing could move."""
    return len(shuffle_spots(state)) >= 2


def apply_shuffle(state: base.State) -> str | None:
    """The Shuffle booster: the plain pigs of every queue are pooled front to back, shuffled with a Fisher-Yates loop
    (i from n - 1 down to 1, k from 0 to i) on the level's seeded generator, and refilled into the same spots in the
    same order, so queue lengths and every featured pig stay as they were (MapController$$ShuffleQueues, RVA
    0x58CB924). Features react to booster_done (a Surprise pig that is now first is revealed). Returns why it was
    refused, or None."""
    if state.finishing:
        return "auto-finisher running"
    spots = shuffle_spots(state)
    if len(spots) < 2:
        return "nothing to shuffle"
    pool = [state.queues[queue][index] for queue, index in spots]
    for i in range(len(pool) - 1, 0, -1):
        k = state.rng.rand_int(i + 1)
        pool[i], pool[k] = pool[k], pool[i]
    moved = []
    for (queue, index), pig_id in zip(spots, pool):
        if state.queues[queue][index] != pig_id:
            state.queues[queue][index] = pig_id
            moved.append(pig_id)
    base.emit(state, "shuffled", {"ids": moved})
    base.emit(state, "booster_done", {"name": "shuffle"})
    return None


def bomb_cells(state: base.State, x: int, y: int) -> list[int]:
    """The cells a bomb on (x, y) covers, in the original's order: the BOMB_SIZE full rows through y from the lowest,
    each left to right, then the BOMB_SIZE full columns through x from the left, each bottom to top, skipping cells a
    row already listed (CrossSelectionShape.<GetAbsolutePositions>d__3$$MoveNext, RVA 0x553B294)."""
    grid = state.grid
    half = (BOMB_SIZE - 1 if BOMB_SIZE > 0 else BOMB_SIZE) >> 1
    cells: list[int] = []
    seen: set[int] = set()
    for offset in range(-half, half + 1):
        row = y + offset
        if 0 <= row < grid.height:
            for column in range(grid.width):
                cell = gridx.cell_of(grid, column, row)
                if cell not in seen:
                    seen.add(cell)
                    cells.append(cell)
    for offset in range(-half, half + 1):
        column = x + offset
        if 0 <= column < grid.width:
            for row in range(grid.height):
                cell = gridx.cell_of(grid, column, row)
                if cell not in seen:
                    seen.add(cell)
                    cells.append(cell)
    return cells


def bomb_targets(state: base.State, x: int, y: int) -> list[gridx.Target]:
    """Everything a bomb on (x, y) damages: each living hittable target on the cross once, in cell order, cubes before
    the cell's features (DemolishPowerupController.<ExecutePowerup>d__25$$MoveNext, RVA 0x52DF4A0, gives each one a
    DamageInfo of 1). A big cube standing on several cells of the cross takes one hit."""
    found: list[gridx.Target] = []
    seen: set[int] = set()
    for cell in bomb_cells(state, x, y):
        for target in gridx.at(state.grid, cell):
            if target.hittable and not target.dead and target.id not in seen:
                seen.add(target.id)
                found.append(target)
    return found


def apply_bomb(state: base.State, x: int, y: int) -> str | None:
    """The Demolish booster: every damageable thing on the cross through cell (x, y) takes 1 hit at once (the page
    shows the bomb's drop first, with the clock held). A pick with nothing to hit is refused and costs nothing. The
    stuck check starts again, as it does when the last shot in flight ends. Returns why it was refused, or None."""
    if state.finishing:
        return "auto-finisher running"
    grid = state.grid
    if not 0 <= x < grid.width or not 0 <= y < grid.height:
        return "no such cell"
    targets = bomb_targets(state, x, y)
    if not targets:
        return "nothing to blow up"
    base.emit(state, "bombed", {"x": x, "y": y, "hits": len(targets)})
    for target in targets:
        aim.hit(state, target, BOMB_DAMAGE, None)
    checks.request_stuck_check(state)
    base.emit(state, "booster_done", {"name": "bomb"})
    return None


def cube_hidden(state: base.State, cube: gridx.Target) -> bool:
    """True for a cube a feature module hides (a Surprise Pixel not yet revealed): the Super Shooter skips it."""
    for module in base.MODULES:
        hook = getattr(module, "hides_cube", None)
        if hook is not None and hook(state, cube):
            return True
    return False


def super_viable(state: base.State, cube: gridx.Target) -> bool:
    """A living cube the Super Shooter may shoot: no obstacle stands on any of its cells and it isn't a hidden
    Surprise Pixel (the powerup's isPixelViableConditions, read from SuperShooterPowerupController, RVA 0x52CD9C4)."""
    if cube.owner != 0 or cube.dead or not cube.hittable or not cube.cells:
        return False
    for cell in cube.cells:
        for target in gridx.at(state.grid, cell):
            if target.obstacle and not target.dead:
                return False
    return not cube_hidden(state, cube)


def super_targets(state: base.State, x: int, y: int) -> list[gridx.Target]:
    """Every cube the Super Shooter hits for a pick on (x, y): the picked cube's color, row by row from the lowest,
    each row left to right, a big cube once at its first cell (SameMaterialSelectionShape.<GetAbsolutePositions>
    d__11$$MoveNext, RVA 0x553E988, and the HashSet in <ShootPixels>, RVA 0x52D4D5C). A picked cell with no cube, or
    whose cube fails the viability check, selects nothing."""
    grid = state.grid
    picked = next((t for t in gridx.at(grid, gridx.cell_of(grid, x, y)) if t.owner == 0 and not t.dead), None)
    if picked is None or not super_viable(state, picked):
        return []
    found: list[gridx.Target] = []
    seen: set[int] = set()
    for row in range(grid.height):
        for column in range(grid.width):
            for target in gridx.at(grid, gridx.cell_of(grid, column, row)):
                if target.owner != 0 or target.dead or target.color != picked.color or target.id in seen:
                    continue
                seen.add(target.id)
                if super_viable(state, target):
                    found.append(target)
    return found


def apply_super(state: base.State, x: int, y: int) -> str | None:
    """The Super Shooter booster: every viable cube of the picked cube's color takes one shot, in row order from the
    bottom, all at once in this tap (the page plays the volley with the clock held). A pick with nothing to shoot is
    refused and costs nothing. The stuck check starts again, as when the last shot in flight ends. Returns why it was
    refused, or None."""
    if state.finishing:
        return "auto-finisher running"
    grid = state.grid
    if not 0 <= x < grid.width or not 0 <= y < grid.height:
        return "no such cell"
    targets = super_targets(state, x, y)
    if not targets:
        return "nothing to shoot"
    base.emit(state, "super_shot", {"x": x, "y": y, "color": targets[0].color, "ids": [t.id for t in targets]})
    for target in targets:
        aim.hit(state, target, SHOT_DAMAGE, None)
    checks.request_stuck_check(state)
    base.emit(state, "booster_done", {"name": "super"})
    return None


def revive(state: base.State) -> str | None:
    """The revive after a fail: the fail is taken back and the map pauses. Its work starts REVIVE_DELAY ticks later
    (MapRescueController.<RescueMap>d__19$$MoveNext, RVA 0x58F27C4: Is Rescue Map Running on, then rescueMapDelay
    0.2 s, level3 #1051). Returns why it was refused, or None."""
    if state.over is None or state.over["result"] != "failed":
        return "not failed"
    if state.reviving:
        return "reviving"
    name = state.over["name"]
    state.over = None
    state.reviving = True
    base.emit(state, "revive_started", {"name": name})
    base.schedule(state, REVIVE_DELAY, "revive_act", name)
    return None


def act_revive(state: base.State, name: str) -> None:
    """Timer: the revive's work for the fail it took back, then the revive ends once that work is done (RescueMap
    runs one task per fail and waits for all of them). Out of space moves pigs to the rescue queue; every other fail
    is handled by the feature modules' revive hooks, each returning the ticks its work takes (RescueMapEventArgs,
    dump.cs:199338)."""
    if name == "out_of_space":
        moved = rescue_out_of_space(state)
        for index, entry in enumerate(moved):
            base.schedule(state, REVIVE_GAP * index, "rescue_pig", entry)
        # Each pig's hop to the rescue row takes HOP ticks; the revive ends when the last one lands
        done = REVIVE_GAP * (len(moved) - 1) + HOP if moved else 0
    else:
        done = 0
        for module in base.MODULES:
            hook = getattr(module, "revive", None)
            if hook is not None:
                done = max(done, hook(state, name))
    base.schedule(state, done, "revive_done", name)


def rescue_out_of_space(state: base.State) -> list[list]:
    """Take every slot pig, rearmost first, then the pigs waiting at the belt's exit, then every pig on the belt out
    of their places at once (MapRescueController.<RescueOutOfSpace>d__20$$MoveNext, RVA 0x58F351C: GetFilledMapSlots
    from the back, GetStrayShooters, GetShootersInConveyor; the offer frees every slot and the belt). The last two
    come in the map's shooter list order, which the pig ids stand in for. Returns [pig id, where it was] in the order
    they join the rescue queue."""
    moved = []
    for slot in range(len(state.slots) - 1, -1, -1):
        pig_id = state.slots[slot]
        if pig_id is not None:
            state.slots[slot] = None
            moved.append([pig_id, "slot"])
    for pig_id, _ in sorted(state.entrance):
        moved.append([pig_id, "exit"])
    state.entrance = []
    for pig_id in sorted(state.pigs):
        if state.pigs[pig_id].place == "belt":
            belt.remove(state, pig_id)
            moved.append([pig_id, "belt"])
    for pig_id, _ in moved:
        state.pigs[pig_id].place = "rescue"
    return moved


def rescue_pig(state: base.State, entry: list) -> None:
    """Timer: a pig joins the back of the rescue queue and hops there; it can't be tapped until it lands
    (MapRescueController$$RescueShooter, RVA 0x58EA538: ShooterQueueController$$Enqueue, then a default 0.25 s
    jump). Pigs follow each other rescueMapJumpInterval 0.05 s apart."""
    pig_id, origin = entry
    pig = state.pigs[pig_id]
    if pig.place != "rescue":
        return
    state.rescue.append(pig_id)
    pig.free_at = state.tick + HOP
    base.emit(state, "to_rescue", {"pig": pig_id, "index": len(state.rescue) - 1, "from": origin})


def end_revive(state: base.State, name: str) -> None:
    """Timer: the revive is over and the map runs again; pigs waiting at the exit take any free slots
    (MapEvents$$TriggerRescueMapFinished -> SlotEntranceQueueController$$OnRescueMapFinished). Features react to
    revive_done (the next Surprise pig is revealed)."""
    state.reviving = False
    places.drain_entrance(state)
    base.emit(state, "revive_done", {"name": name})
