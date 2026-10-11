import math
import random

import pytest

from botarena3.common import battle as engine
from botarena3.common import shapes
from botarena3.common.arenas import ARENAS
from botarena3.tests.helpers import battle, place, robot


@pytest.fixture
def open_field(monkeypatch):
    monkeypatch.setattr(shapes, "wall_hit", lambda x, y: False)


def test_robots_start_moving_on_the_countdowns_go(open_field):
    b = battle([robot(weapon=None)], [robot(weapon=None)])
    start = [(r.x, r.y) for r in b.robots]
    for _ in range(engine.MOVE_AT):
        b.tick()
    assert b.moving and [(r.x, r.y) for r in b.robots] != start


def test_driving_moves_two_pixels_and_turns_by_a_tenth_of_the_sway(open_field):
    b = battle([robot()], [robot(weapon=None)])
    me = b.robots[0]
    place(me, 200, 240, 0)
    me.sway = 30
    b.drive(me)
    assert me.rot == pytest.approx(3)
    assert me.x == pytest.approx(200 + 2 * math.sin(math.radians(3)))
    assert me.y == pytest.approx(240 - 2 * math.cos(math.radians(3)))
    assert me.sway == pytest.approx(30 / 1.04)


def test_a_settled_sway_picks_a_new_wobble(open_field):
    b = battle([robot()], [robot(weapon=None)])
    me = b.robots[0]
    me.sway = 0.5
    b.drive(me)
    assert me.sway == 0
    b.drive(me)
    assert me.sway == -10  # random(21) - 10 with every random at 0


def test_a_nan_sway_drives_straight_on(open_field):
    b = battle([robot()], [robot(weapon=None)])
    me = b.robots[0]
    place(me, 200, 240, 90)
    b.steer(me, 150, 0, 100)
    assert math.isnan(me.sway)
    b.drive(me)
    assert me.rot == 90 and me.x == pytest.approx(202) and math.isnan(me.sway)


def test_a_feeler_touching_a_robot_stops_it_and_it_turns_on_the_spot(open_field):
    b = battle([robot(weapon=None)], [robot(weapon=None)])
    me, block = b.robots
    place(me, 200, 240, 0)
    place(block, 200, 205, 0)
    b.moving = True
    b.move(me)
    assert (me.x, me.y, me.rot) == (200, 240, 0)
    assert me.stuck == engine.STUCK_STEPS - 1 and me.turn == -engine.FUSSY_TURN
    b.move(me)
    assert me.rot == -5


def test_walls_stop_robots():
    b = battle([robot(weapon=None)], [robot(weapon=None)])
    me = b.robots[0]
    b.moving = True
    for _ in range(600):
        b.move(me)
    assert 0 < me.x < 540 and 0 < me.y < 480


def test_an_order_on_empty_ground_goes_there_inside_the_box(open_field):
    b = battle([robot()], [robot(weapon=None)])
    me = b.robots[0]
    assert b.order(1, me.id, 600, 10)
    assert me.order == ("goto", engine.RIGHT, engine.TOP) and me.lock == 0


def test_an_order_on_a_living_robot_follows_it_and_on_yourself_goes_back_to_normal(open_field):
    b = battle([robot(), robot("mate", weapon=None)], [robot(weapon=None)])
    me, mate, enemy = b.robots
    assert b.order(1, me.id, enemy.x, enemy.y) and me.order == ("follow", enemy)
    assert b.order(1, me.id, me.x, me.y) and me.order == ("standard",)
    assert b.order(1, me.id, mate.x, mate.y) and me.order == ("follow", mate)


def test_orders_are_refused_for_the_other_side_wrecks_and_the_dead(open_field):
    b = battle([robot()], [robot(weapon=None), robot(weapon=None)])
    me, enemy, wreck = b.robots
    assert not b.order(2, me.id, 300, 300)
    assert not b.order(1, enemy.id, 300, 300)
    wreck.health = 0
    assert not b.order(1, me.id, wreck.x, wreck.y) and me.order == ("standard",)
    me.health = 0
    assert not b.order(1, me.id, 300, 300)


def test_an_order_wakes_a_robot_without_a_weapon(open_field):
    b = battle([robot(weapon=None)], [robot(weapon=None)])
    me = b.robots[0]
    assert me.lock is None
    b.order(1, me.id, 300, 100)
    b.tick()
    assert me.lock == engine.SCAN_EVERY and not math.isnan(me.sway)


def test_a_go_there_order_ends_close_to_its_spot(open_field):
    b = battle([robot(weapon=None)], [robot(weapon=None)])
    me = b.robots[0]
    place(me, 200, 240, 0)
    # About 29 pixels away, and outside the robot's own outline
    assert b.order(1, me.id, 215, 215)
    me.lock = 1
    b.tick()
    assert me.order == ("standard",)


def test_a_pvp_fight_without_damage_is_a_draw_after_60_seconds(open_field):
    quiet = battle([robot(weapon=None)], [robot(weapon=None)], owned=(True, True), draws=True)
    for _ in range(engine.DRAW_STEPS):
        quiet.tick()
    assert (quiet.ended, quiet.winner) == (engine.DRAW_STEPS, 0)
    career = battle([robot(weapon=None)], [robot(weapon=None)])
    for _ in range(engine.DRAW_STEPS + 10):
        career.tick()
    assert career.ended is None


def test_a_seeded_battle_replays_exactly():
    def play(seed):
        b = engine.Battle(
            ([robot("A"), robot("B", weapon='RAPTOR "DT-01"')], list(ARENAS[0].opponents)),
            (1, 9),
            owned=(True, False),
            rng=random.Random(seed),
        )
        log = []
        for _ in range(900):
            b.tick()
            log.append((b.view(), b.take_events()))
        return log

    assert play(7) == play(7)
    assert play(7) != play(8)
