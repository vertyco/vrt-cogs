import math

import pytest

from botarena3.common import battle as engine
from botarena3.common import shapes
from botarena3.common.parts import CHASSIS, PLATINGS
from botarena3.tests.helpers import (
    AURO,
    BIG,
    FIREWORKS,
    LIGHT,
    LP,
    REPAIR,
    THICK,
    ZeroRandom,
    battle,
    place,
    robot,
    shots,
)


@pytest.fixture
def open_field(monkeypatch):
    """No walls, so a test about shots isn't about where the arena's walls are"""
    monkeypatch.setattr(shapes, "wall_hit", lambda x, y: False)


def test_flash_helpers():
    rng = ZeroRandom()
    assert engine.flash_random(rng, 0) == 0 and engine.flash_random(rng, 5) == 0
    assert engine.wrap(190) == -170 and engine.wrap(-190) == 170 and engine.wrap(540) == 180
    assert engine.settle(30, math.nan) == 30 and engine.settle(30, 200) == -160
    assert math.isnan(engine.angle(150, 0, 100)) and math.isnan(engine.angle(0, 0, 0))
    assert engine.angle(-100, 0, 100) == pytest.approx(math.pi)


def test_setup_matches_the_original():
    b = battle([robot("A"), robot("B")], [robot("C", weapon=None)])
    a, bb, c = b.robots
    assert (a.id, a.team, a.x, a.rot) == (1, 1, 60, 90) and (c.id, c.team, c.x, c.rot) == (3, 2, 480, -90)
    assert a.y == pytest.approx(400 / 3 + 40) and bb.y == pytest.approx(800 / 3 + 40) and c.y == 240
    assert a.max_health == a.health == PLATINGS[AURO].shielding + CHASSIS[LIGHT].shielding * 3
    assert a.frame == 10 and c.frame == 1
    assert (c.min_range, c.max_range, c.lock) == (50, 100, None)
    assert b.setup()[0]["weapon"] == LP and b.colors == [1, 9]


def test_a_gun_fires_each_time_its_cooldown_fills(open_field):
    b = battle([robot()], [robot(weapon=None, plating=THICK, chassis=BIG)])
    left, right = b.robots
    place(left, 200, 240, 90)
    place(right, 300, 240, -90)
    left.lock = 0
    events = []
    for _ in range(60):
        b.tick()
        events += b.take_events()
    assert shots(events) == [20, 40, 60]
    assert right.health == right.max_health - 30


def test_a_cooldown_that_overshoots_waits_a_step(open_field):
    b = battle([robot(weapon=FIREWORKS)], [robot(weapon=None, plating=THICK, chassis=BIG)])
    left, right = b.robots
    place(left, 200, 240, 90)
    place(right, 280, 240, -90)
    left.lock = 0
    events = []
    for _ in range(21):
        b.tick()
        events += b.take_events()
    assert shots(events) == [7, 14, 21]


def test_the_closest_enemy_past_the_shortest_range_is_the_target(open_field):
    b = battle([robot()], [robot("near", weapon=None), robot("mid", weapon=None), robot("far", weapon=None)])
    me, near, mid, far = b.robots
    place(me, 200, 240, 90)
    place(near, 215, 240, -90)
    place(mid, 300, 240, -90)
    place(far, 350, 240, -90)
    me.lock = 0
    b.tick()
    assert me.target is mid and me.follow is mid


def test_a_target_out_of_range_is_followed_but_not_locked(open_field):
    b = battle([robot()], [robot(weapon=None)])
    me, them = b.robots
    place(me, 100, 240, 90)
    place(them, 400, 240, -90)
    me.lock = 0
    b.tick()
    assert me.target is None and me.follow is them and me.closer is True


def test_a_repair_tool_heals_the_most_hurt_teammate_up_to_full(open_field):
    b = battle(
        [robot(weapon=REPAIR), robot("hurt", weapon=None), robot("scratched", weapon=None)], [robot(weapon=None)]
    )
    medic, hurt, scratched, enemy = b.robots
    place(medic, 200, 240, 90)
    place(hurt, 260, 240, -90)
    place(scratched, 200, 300, 0)
    place(enemy, 480, 100, -90)
    hurt.health = hurt.max_health - 30
    scratched.health = scratched.max_health - 1
    medic.lock = 0
    events = []
    for _ in range(18):
        b.tick()
        events += b.take_events()
    assert medic.target is hurt
    assert shots(events) == [18] and hurt.health == hurt.max_health


def test_a_teammate_in_the_way_blocks_the_shot_unhurt(open_field):
    b = battle([robot(), robot("in the way", weapon=None)], [robot(weapon=None)])
    shooter, mate, enemy = b.robots
    place(shooter, 150, 240, 90)
    place(mate, 210, 240, 90)
    place(enemy, 290, 240, -90)
    shooter.lock = 0
    events = []
    for _ in range(20):
        b.tick()
        events += b.take_events()
    shot = next(e for e in events if e[1] == "shot")
    assert shot[10] == engine.HIT_ROBOT and shot[8] < 230
    assert mate.health == mate.max_health and enemy.health == enemy.max_health


def test_a_wreck_still_blocks_shots(open_field):
    b = battle([robot()], [robot("wreck", weapon=None), robot("alive", weapon=None)])
    shooter, wreck, alive = b.robots
    place(shooter, 150, 240, 90)
    place(wreck, 220, 240, -90)
    place(alive, 290, 240, -90)
    wreck.health = 0
    shooter.lock = 0
    for _ in range(20):
        b.tick()
    assert shooter.target is alive and alive.health == alive.max_health


def test_the_last_enemy_dying_ends_the_battle(open_field):
    b = battle([robot()], [robot(weapon=None)])
    left, right = b.robots
    place(left, 200, 240, 90)
    place(right, 300, 240, -90)
    right.health = 5
    left.lock = 0
    events = []
    for _ in range(20):
        b.tick()
        events += b.take_events()
    kinds = [e[1] for e in events]
    assert kinds[-3:] == ["shot", "end", "die"] or kinds[-3:] == ["shot", "die", "end"]
    assert (b.ended, b.winner, right.health) == (20, 1, 0)
    assert b.wrecks()[0][0] == right.id
    for _ in range(engine.BANNER_STEPS + engine.FADE_STEPS - 1):
        b.tick()
    assert not b.done()
    b.tick()
    assert b.done()


def test_damage_from_your_own_side_and_repairs_from_the_other_do_nothing():
    b = battle([robot(), robot(weapon=None)], [robot(weapon=None)])
    me, mate, enemy = b.robots
    b.hurt(mate, 50, team=1)
    assert mate.health == mate.max_health
    enemy.health -= 100
    b.hurt(enemy, -65, team=1)
    assert enemy.health == enemy.max_health - 100
    assert b.last_damage == 0


def test_nothing_moves_before_the_countdown_says_go():
    b = battle([robot(weapon=None)], [robot(weapon=None)])
    start = [(r.x, r.y, r.rot) for r in b.robots]
    for _ in range(engine.MOVE_AT - 1):
        b.tick()
    assert [(r.x, r.y, r.rot) for r in b.robots] == start and not b.moving


def test_the_view_and_events_are_plain_json(open_field):
    b = battle([robot()], [robot(weapon=None)])
    for _ in range(30):
        b.tick()
    row = b.view()[0]
    assert len(row) == 7 and all(isinstance(v, (int, float)) for v in row[:6])


def test_the_newest_robot_acts_first_in_a_mirror_fight(open_field):
    b = battle([robot()], [robot()])
    left, right = b.robots
    place(left, 200, 240, 90)
    place(right, 300, 240, -90)
    for one in (left, right):
        one.lock = 0
        one.health = 5
    for _ in range(20):
        b.tick()
    assert b.winner == 2
    assert left.health == 0 and right.health == 5
