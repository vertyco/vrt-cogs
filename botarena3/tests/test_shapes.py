import json
import math
from pathlib import Path

import pytest

from botarena3.common import shapes

RAW = json.loads((Path(shapes.__file__).parent / "shapes.json").read_text(encoding="utf-8"))


def set_extent(mask: shapes.Mask) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for row in range(mask.height):
        for col in range(mask.width):
            if mask.bits[row * mask.row + col // 8] & (0x80 >> (col % 8)):
                xs.append(col)
                ys.append(row)
    return (
        mask.x0 + min(xs) / mask.scale,
        mask.y0 + min(ys) / mask.scale,
        mask.x0 + (max(xs) + 1) / mask.scale,
        mask.y0 + (max(ys) + 1) / mask.scale,
    )


@pytest.mark.parametrize("frame", range(1, shapes.BOT_FRAMES + 1))
def test_each_robot_frame_has_an_outline_that_lines_up_with_its_shape(frame):
    mask = shapes.ROBOTS[frame]
    assert mask.hit(0, 0)
    assert not mask.hit(40, 0) and not mask.hit(0, 40)
    extent = set_extent(mask)
    for got, want in zip(extent, RAW["robots"][str(frame)]["bounds"]):
        assert abs(got - want) <= 1, (frame, extent)


@pytest.mark.parametrize("frame", range(1, shapes.BOT_FRAMES + 1))
def test_each_robot_frame_has_three_feelers_in_front_outside_itself(frame):
    feelers = shapes.FEELERS[frame]
    assert len(feelers) == 3
    for x, y in feelers:
        assert y < 0 and not shapes.ROBOTS[frame].hit(x, y)


def test_the_bot_frame_follows_the_originals_oddities():
    assert shapes.bot_frame(3, owned=True) == 3
    assert shapes.bot_frame(14, owned=True) == 10
    assert shapes.bot_frame(None, owned=True) == 1
    assert shapes.bot_frame(3, owned=False) == 1


def test_robot_outlines_turn_with_the_robot():
    # Facing right (90), a point 30 pixels in front is in the stage's +x direction
    front = shapes.FEELERS[1][1]
    x, y = shapes.to_stage(100, 100, 90, *front)
    assert x > 120 and abs(y - 100) < 1
    assert shapes.robot_hit(1, 100, 100, 90, 100, 100)
    assert not shapes.robot_hit(1, 100, 100, 90, 160, 100)


def test_the_walls_ring_the_arena_and_the_starts_are_clear():
    assert shapes.wall_hit(2, 2) and shapes.wall_hit(538, 478)
    for count in range(1, 6):
        for number in range(1, count + 1):
            y = 400 / (count + 1) * number + 40
            assert not shapes.wall_hit(60, y) and not shapes.wall_hit(480, y)


def test_the_gun_tip_is_in_front_of_the_robot():
    x, y = shapes.gun_tip(1, 10, 100, 100, 0, 0)
    assert y < 100
    x, y = shapes.gun_tip(1, 10, 100, 100, 90, 0)
    assert x > 100
    # Turning the gun 90 degrees on a robot facing up points it right
    x, y = shapes.gun_tip(1, 10, 100, 100, 0, 90)
    assert x > 100
    assert set(shapes.GUN_MOUNTS) == set(range(1, 12)) and set(shapes.GUN_TIPS) == set(range(1, 19))
    assert all(math.isfinite(v) for m in shapes.GUN_MOUNTS.values() for v in m)
