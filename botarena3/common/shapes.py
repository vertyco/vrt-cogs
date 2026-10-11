"""Hit outlines from the original's art, built into shapes.json by FlashRE/bot-arena-3/tools/build_shapes.py: the
robot outline for each frame of the original's bot shape with its three feelers, the arena walls, and where each gun's
tip is. A hit test is one lookup in a pixel mask, which follows Flash's own shape test to a fraction of a pixel"""

import base64
import json
import math
from pathlib import Path

SHAPES = json.loads((Path(__file__).parent / "shapes.json").read_text(encoding="utf-8"))
DEG = 0.017453292519943295
BOT_FRAMES = 10


class Mask:
    def __init__(self, data: dict):
        self.x0, self.y0, self.scale = data["x0"], data["y0"], data["scale"]
        self.width, self.height = data["w"], data["h"]
        self.row = (self.width + 7) // 8
        self.bits = base64.b64decode(data["bits"])

    def hit(self, x: float, y: float) -> bool:
        col = math.floor((x - self.x0) * self.scale)
        row = math.floor((y - self.y0) * self.scale)
        if not (0 <= col < self.width and 0 <= row < self.height):
            return False
        return bool(self.bits[row * self.row + col // 8] & (0x80 >> (col % 8)))


ROBOTS = {int(frame): Mask(entry["mask"]) for frame, entry in SHAPES["robots"].items()}
FEELERS = {int(frame): [tuple(point) for point in entry["feelers"]] for frame, entry in SHAPES["robots"].items()}
WALLS = Mask(SHAPES["walls"]["mask"])
GUN_MOUNTS = {int(frame): matrix for frame, matrix in SHAPES["guns"]["mounts"].items()}
GUN_TIPS = {int(frame): tuple(point) for frame, point in SHAPES["guns"]["tips"].items()}


def bot_frame(gun: int | None, owned: bool) -> int:
    """The frame of the bot shape a robot uses. The original sends a player's robot to its weapon's art number (Flash
    stops on the last frame past it) and never moves the computer's robots off the first"""
    if not owned or gun is None:
        return 1
    return min(gun, BOT_FRAMES)


def to_stage(x: float, y: float, rot: float, local_x: float, local_y: float) -> tuple[float, float]:
    cos, sin = math.cos(DEG * rot), math.sin(DEG * rot)
    return x + cos * local_x - sin * local_y, y + sin * local_x + cos * local_y


def robot_hit(frame: int, x: float, y: float, rot: float, px: float, py: float) -> bool:
    cos, sin = math.cos(DEG * rot), math.sin(DEG * rot)
    dx, dy = px - x, py - y
    return ROBOTS[frame].hit(cos * dx + sin * dy, -sin * dx + cos * dy)


def wall_hit(px: float, py: float) -> bool:
    return WALLS.hit(px, py)


def gun_tip(top_frame: int, gun_frame: int, x: float, y: float, rot: float, gun_rot: float) -> tuple[float, float]:
    """Where a shot starts: the gun's tip, through the gun's mount on the robot's top (turned by its aim, keeping the
    mount's scale, as setting _rotation does in Flash), then the robot's place and facing"""
    a, b, c, d, tx, ty = GUN_MOUNTS[top_frame]
    sx, sy = math.hypot(a, b), math.hypot(c, d)
    cos, sin = math.cos(DEG * gun_rot), math.sin(DEG * gun_rot)
    px, py = GUN_TIPS[gun_frame]
    return to_stage(x, y, rot, sx * cos * px - sy * sin * py + tx, sx * sin * px + sy * cos * py + ty)
