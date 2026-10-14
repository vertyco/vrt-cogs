"""
One attempt at a Bloxorz stage: the board, the block or the two cubes, the bridges, and every landing rule.

Ported from the original's `overair2` (the block's at frame_50/PlaceObject3_1152_84 onClipEvent(load) lines 19-439,
written BL:n below; the cube's at frame_50/PlaceObject2_829_78 onClipEvent(load) lines 49-173, written CL:n) and the
bridge tile's close check (DefineSprite_320 frames 41 and 131).

The original runs in frames. A roll lasts 9 frames or more and a bridge takes 7 to open or close, so every bridge is
at rest when a roll lands. Everything one landing does happens in one frame: the support test, the presses, a join
and the joined block's own landing all read the bridges as they were at the start of that frame, because a tile's
`play()` only moves it on the next frame. A bridge that starts to close runs its check on the frame after, which is
`check()` here: the page tells the bot which pieces are mid-roll on that frame.
"""

from .stages import Stage, tile

PIECES = ("block", "a", "b")
DIRS = ("left", "up", "right", "down")
BRIDGES = "lkrq"
OPEN_AT_START = "kq"
SOLID = "bsvhfelkrq"

# (pose, direction) -> (pose after, anchor dx, anchor dy), DefineSprite_1152 frames 10 to 121
BLOCK_ROLLS = {
    ("up", "left"): ("long", -2, 0),
    ("up", "up"): ("far", 0, -1),
    ("up", "right"): ("long", 1, 0),
    ("up", "down"): ("far", 0, 2),
    ("far", "left"): ("far", -1, 0),
    ("far", "up"): ("up", 0, -2),
    ("far", "right"): ("far", 1, 0),
    ("far", "down"): ("up", 0, 1),
    ("long", "left"): ("up", -1, 0),
    ("long", "up"): ("long", 0, -1),
    ("long", "right"): ("up", 2, 0),
    ("long", "down"): ("long", 0, 1),
}

# DefineSprite_829 frames 10 to 40
CUBE_ROLLS = {"left": (-1, 0), "up": (0, -1), "right": (1, 0), "down": (0, 1)}

# A lying block tipped along its own length (BL:129, BL:190), and where it falls with one square over nothing
# after any other roll (BL:167-186, BL:226-245): (anchor square missing, other square missing)
TIP_DIRS = {"long": ("left", "right"), "far": ("up", "down")}
FORCED = {"long": ("left", "right"), "far": ("down", "up")}


def covered(pose: str, at: tuple[int, int]) -> list[tuple[int, int]]:
    """The squares a block covers, the anchor first (BL:21-23)."""
    x, y = at
    if pose == "far":
        return [(x, y), (x, y - 1)]
    if pose == "long":
        return [(x, y), (x + 1, y)]
    return [(x, y)]


def fall_end(kind: str, direction: str | None) -> dict:
    return {"fall": {"kind": kind, "dir": direction}}


class Frame:
    """What one frame's presses did: bridges told to move (a second `play()` that frame does nothing new) and the
    ones of those that were open, which run a close check on the next frame."""

    def __init__(self):
        self.turned: list[tuple[int, int]] = []
        self.closing: list[tuple[int, int]] = []


class Attempt:
    def __init__(self, stage: Stage):
        self.stage = stage
        self.open: dict[tuple[int, int], bool] = {}
        for y, row in enumerate(stage.rows):
            for x, letter in enumerate(row):
                if letter in BRIDGES:
                    self.open[(x, y)] = letter in OPEN_AT_START
        self.moving: set[tuple[int, int]] = set()
        self.pending: list[tuple[int, int]] = []
        self.memory: dict[tuple[int, int], str] = {}
        self.cancelled: set[str] = set()
        self.over: str | None = None
        self.selected = "block"
        self.pose = "up"
        self.at: tuple[int, int] = stage.start
        self.cubes: dict[str, tuple[int, int]] | None = None

    @property
    def awaiting_check(self) -> bool:
        return bool(self.pending)

    # The board

    def solid(self, square: tuple[int, int]) -> bool:
        """BL:21-45: any tile holds, but a bridge only at its resting open frame (40 or 130)."""
        letter = tile(self.stage, *square)
        if letter not in SOLID:
            return False
        if letter in BRIDGES:
            return self.open[square] and square not in self.moving
        return True

    def bridge_state(self, square: tuple[int, int]) -> str | None:
        """ "open" at frame 40/130, "closed" at 33/123, None while it moves."""
        if square in self.moving:
            return None
        return "open" if self.open[square] else "closed"

    def press(self, square: tuple[int, int], kind: str, frame: Frame) -> dict:
        """Run one switch's list against each bridge as it was at the start of the frame (BL:311-335)."""
        bridges = []
        for x, y, mode in self.stage.switches.get(square, ()):
            target = (x, y)
            state = self.bridge_state(target)
            flash = None
            if mode == "off" or (mode == "onoff" and state == "open"):
                flash = "close"
            if mode == "on" or (mode == "onoff" and state == "closed"):
                flash = "open"
            moves = (state == "closed" and mode != "off") or (state == "open" and mode != "on")
            turn = moves and target not in frame.turned
            if turn:
                frame.turned.append(target)
                if state == "open":
                    frame.closing.append(target)
            bridges.append({"at": [x, y], "flash": flash, "turn": turn})
        return {"at": list(square), "kind": kind, "bridges": bridges}

    def finish(self, frame: Frame):
        """The frame is over: every bridge told to move starts moving."""
        for square in frame.turned:
            self.open[square] = not self.open[square]
        self.moving = set(frame.turned)
        self.pending = list(frame.closing)

    # The block

    def block_fall(self, pose: str, at: tuple[int, int], direction: str | None) -> dict | None:
        """BL:127-262: whether the block falls, its kind and the way it goes."""
        squares = covered(pose, at)
        held = [self.solid(square) for square in squares]
        if all(held):
            return None
        if pose == "up":
            return fall_end("tall", direction)
        if direction in TIP_DIRS[pose]:
            return fall_end("half" if any(held) else "full", direction)
        if not any(held):
            return fall_end("roll", direction)
        return fall_end("half", FORCED[pose][0] if not held[0] else FORCED[pose][1])

    def block_land(self, pose: str, at: tuple[int, int], direction: str | None, presses: bool, frame: Frame) -> dict:
        """The block's `overair2(pose, presses)` at `at`."""
        end = self.block_fall(pose, at, direction)
        letter = tile(self.stage, *at)
        if pose == "up" and letter == "e":
            end = {"win": True}
        elif pose == "up" and letter == "v":
            a, b = self.stage.splits[at]
            end = {"split": {"a": list(a), "b": list(b)}}
        elif pose == "up" and letter == "f":
            end = fall_end("fragile", direction)
        pressed = []
        if presses:
            for square in covered(pose, at):
                under = tile(self.stage, *square)
                if under == "s":
                    pressed.append(self.press(square, "soft", frame))
                elif under == "h" and pose == "up":
                    pressed.append(self.press(square, "heavy", frame))
        return {
            "piece": "block",
            "cause": "roll",
            "pose": pose,
            "at": list(at),
            "dir": direction,
            "presses": pressed,
            "closing": False,
            "end": end,
        }

    def settle_block(self, step: dict):
        end = step["end"] or {}
        if "fall" in end:
            self.over = "fall"
        elif "win" in end:
            self.over = "win"
        elif "split" in end:
            self.cubes = {"a": tuple(end["split"]["a"]), "b": tuple(end["split"]["b"])}
            self.selected = "a"
        else:
            self.pose = step["pose"]
            self.at = tuple(step["at"])

    # The cubes

    def join_shape(self, at: tuple[int, int], other: tuple[int, int]) -> tuple[str, tuple[int, int]] | None:
        """CL:145-160 with rejoinblocks' slip (CL:23-48): the joined block's pose and anchor."""
        x, y = at
        if other == (x + 1, y):
            return "long", (x, y)
        if other == (x - 1, y):
            return "long", (x - 1, y)
        if other == (x, y - 1):
            return "far", (x, y)
        if other == (x, y + 1):
            return "far", (x, y + 1)
        return None

    def cube_land(self, name: str, at: tuple[int, int], direction: str | None, presses: bool, frame: Frame) -> list:
        """A cube's `overair2("up", presses)` at `at`, then the join and the joined block's landing (CL:49-173).

        `direction` "none" is the original's cube at rest: on a bridge that gives way it tips off the bridge's open
        side (CL:63-76). None is a direction the bot doesn't know yet.

        The joined block lands in DefineSprite_1152 frame 290, and that landing's gotoAndStop jumps it straight to its
        resting frame, so the next frame's bridge check finds it at rest like after any other landing."""
        letter = tile(self.stage, *at)
        fall_dir = direction
        if direction == "none":
            fall_dir = "right" if letter in "lk" else "left" if letter in "rq" else None
            direction = None
        end = None if self.solid(at) else fall_end("cube", fall_dir)
        pressed = [self.press(at, "soft", frame)] if presses and letter == "s" else []
        step = {
            "piece": name,
            "cause": "roll",
            "pose": "cube",
            "at": list(at),
            "dir": direction,
            "presses": pressed,
            "closing": False,
            "end": end,
        }
        shape = self.join_shape(at, self.cubes["b" if name == "a" else "a"])
        if shape is None:
            return [step]
        pose, anchor = shape
        step["end"] = {"join": {"pose": pose, "at": list(anchor)}}
        joined = self.block_land(pose, anchor, None, True, frame)
        joined["cause"] = "join"
        return [step, joined]

    def settle_cubes(self, steps: list):
        step = steps[0]
        end = step["end"] or {}
        if "fall" in end:
            self.over = "fall"
        elif "join" in end:
            self.cubes = None
            self.selected = "block"
            self.settle_block(steps[1])
        else:
            self.cubes[step["piece"]] = tuple(step["at"])

    # Turns

    def roll(self, piece: str, direction: str) -> list[dict] | None:
        """One roll of the selected piece, landed. None when refused (nothing changes).

        A piece whose roll a check already stopped (an `end: snap` step) gets an empty list for that roll."""
        if self.over or piece != self.selected or direction not in DIRS:
            return None
        if piece in self.cancelled:
            self.cancelled.discard(piece)
            return []
        frame = Frame()
        self.moving = set()
        if piece == "block":
            pose, dx, dy = BLOCK_ROLLS[(self.pose, direction)]
            step = self.block_land(pose, (self.at[0] + dx, self.at[1] + dy), direction, True, frame)
            steps = [step]
            self.settle_block(step)
        else:
            dx, dy = CUBE_ROLLS[direction]
            x, y = self.cubes[piece]
            steps = self.cube_land(piece, (x + dx, y + dy), direction, True, frame)
            self.settle_cubes(steps)
        self.mark_closing(steps, frame)
        self.finish(frame)
        return steps

    def mark_closing(self, steps: list, frame: Frame):
        """Each step says whether one of its presses started to close a bridge."""
        for step in steps:
            started = {
                tuple(bridge["at"]) for press in step["presses"] for bridge in press["bridges"] if bridge["turn"]
            }
            step["closing"] = any(square in started for square in frame.closing)

    def check(self, rolling: set[str]) -> list[dict]:
        """The frame after a landing that started closing bridges: each one's frame 41/131 check (S320/f41).

        `rolling` names the pieces mid-roll on that frame. Such a piece is still on its square in the original. A
        cube there always stops (`end: snap`) or falls. The block uses the pose that bridge remembered the last time
        it saw the block at rest, or does nothing if it never did. A rolling piece's fall has `dir` None: it falls
        the way the roll the page just started was going."""
        if self.over or not self.pending:
            self.pending = []
            return []
        frame = Frame()
        steps = []
        for square in self.pending:
            if self.over:
                break
            if self.cubes is None:
                busy = "block" in rolling and "block" not in self.cancelled
                steps += self.check_block(square, busy, frame)
            else:
                steps += self.check_cubes(rolling, frame)
        self.pending = []
        for square in frame.turned:
            self.open[square] = not self.open[square]
        self.moving |= set(frame.turned)
        for step in steps:
            step["cause"] = "check" if step["cause"] == "roll" else step["cause"]
        return steps

    def check_block(self, square: tuple[int, int], busy: bool, frame: Frame) -> list[dict]:
        if not busy:
            self.memory[square] = self.pose
        pose = self.memory.get(square)
        if pose is None:
            return []
        step = self.block_land(pose, self.at, None, False, frame)
        if step["end"] is None and not busy:
            return []
        if step["end"] is None:
            step["end"] = {"snap": True}
            self.cancelled.add("block")
        self.settle_block(step)
        return [step]

    def check_cubes(self, rolling: set[str], frame: Frame) -> list[dict]:
        steps = []
        for name in ("a", "b"):
            if self.over or self.cubes is None:
                break
            moving = name in rolling and name not in self.cancelled
            landed = self.cube_land(name, self.cubes[name], None if moving else "none", False, frame)
            if moving:
                if landed[0]["end"] is None:
                    landed[0]["end"] = {"snap": True}
                    self.cancelled.add(name)
            elif landed[0]["end"] is None:
                continue
            self.settle_cubes(landed)
            steps += landed
        return steps

    def swap(self) -> bool:
        """Space: the other cube is selected. Not a move."""
        if self.over or self.cubes is None:
            return False
        self.selected = "b" if self.selected == "a" else "a"
        return True

    def piece(self) -> dict:
        if self.cubes is None:
            return {"pose": self.pose, "at": list(self.at)}
        return {"a": list(self.cubes["a"]), "b": list(self.cubes["b"]), "selected": self.selected}

    def snapshot(self) -> dict:
        return {"open": [list(square) for square, opened in sorted(self.open.items()) if opened], "piece": self.piece()}
