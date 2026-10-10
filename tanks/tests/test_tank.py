import random

import pytest

from tanks.common.items import PARACHUTES, UP_ARMOR, UP_ENGINE, UP_HILL, WEAK_SHIELD
from tanks.common.tank import (
    armor,
    check_death,
    drive_frame,
    hurt,
    land,
    place,
    settle_frame,
    start_settling,
)
from tanks.common.terrain import WIDTH, Field
from tanks.tests.helpers import GROUND, flat, tank_at


def settle(tank, field, frames=400):
    start_settling(tank)
    for _ in range(frames):
        if not tank.settling:
            return
        settle_frame(tank, field)


def test_armor_lets_through_about_one_over_1_12_per_level():
    assert armor(0) == 1
    assert armor(1) == pytest.approx(1 / 1.12)
    assert armor(2) == pytest.approx(1 / 1.12 / (1.12 / (1 / 1.0002)))


def test_damage_from_another_tank_pays_100_a_point_and_5000_for_the_kill():
    field = flat()
    me, them = tank_at(0, 100, field), tank_at(1, 300, field, energy=30)
    hurt(them, 30, me)
    assert them.energy == 0
    assert me.kit.money == 5000 + 3000 + 5000 and me.kit.score == 8000 and me.kit.kills == 1


def test_a_hurt_tanks_power_drops_to_its_health():
    # Power can't be more than health, so the next turn starts at the power the shot will really use
    field = flat()
    me, them = tank_at(0, 100, field), tank_at(1, 300, field)
    them.power = 100.0
    hurt(them, 85, me)
    assert them.energy == 15 and them.view()["power"] == 15


def test_armor_softens_damage_but_not_the_attackers_pay():
    field = flat()
    me, them = tank_at(0, 100, field), tank_at(1, 300, field)
    them.kit.extras[UP_ARMOR] = 1
    hurt(them, 20, me)
    assert them.energy == pytest.approx(100 - 20 / 1.12)
    assert me.kit.money == 5000 + 2000


def test_hurting_yourself_costs_50_a_point_and_never_below_zero_money():
    field = flat()
    me = tank_at(0, 100, field)
    hurt(me, 20, me)
    assert me.kit.money == 4000 and me.kit.score == -1000
    me.kit.money = 300
    hurt(me, 20, me)
    assert me.kit.money == 0 and me.kit.score == -2000


def test_blowing_yourself_up_costs_2000_and_a_kill():
    field = flat()
    me = tank_at(0, 100, field, energy=10)
    hurt(me, 10, me)
    assert me.kit.kills == -1
    assert me.kit.score == -2000 - 500


def test_fall_damage_skips_the_shield_and_costs_a_third():
    field = flat()
    me = tank_at(0, 100, field)
    me.raise_shield(WEAK_SHIELD) if me.kit.extras[WEAK_SHIELD] else None
    me.shield, me.shield_left = WEAK_SHIELD, 100
    hurt(me, 30, me, fall=True)
    assert me.energy == 70 and me.shield_left == 100
    assert me.kit.money == 5000 - 500


def test_falling_off_the_bottom_kills_and_costs_2000_money():
    field = flat()
    me = tank_at(0, 100, field)
    me.y = 401
    assert check_death(me)
    assert not me.alive and me.energy == 0 and me.kit.money == 3000
    assert not check_death(me)


def test_tanks_are_spread_apart_by_350_over_the_number_of_tanks():
    rng = random.Random(2)
    field = Field(3, [300.0] * WIDTH, 0.0)
    for count in (2, 3, 4, 5):
        xs = place(field, list(range(count)), rng)
        assert all(20 <= x <= 519 for x in xs)
        assert all(abs(a - b) >= 350 / count for i, a in enumerate(xs) for b in xs[i + 1 :])


def test_tanks_are_never_placed_over_a_pit():
    rng = random.Random(3)
    field = Field(3, [300.0] * WIDTH, 0.0)
    for column in range(0, 400):
        field.tops[column] = 450
    xs = place(field, [0, 1], rng)
    assert all(x >= 400 for x in xs)


def test_a_new_tank_flattens_the_ground_under_it():
    field = flat()
    field.tops[100] = GROUND - 20
    tank = tank_at(0, 104, field)
    land(tank, field, random.Random(1))
    assert tank.y == GROUND - 4
    # Columns above the shadow's bottom are pushed down level with it
    assert field.tops[100] == tank.y + 3.25
    assert 46 <= tank.angle <= 178 and tank.angle % 2 == 0 and tank.power == 50


def test_driving_moves_half_a_pixel_a_frame_and_burns_fuel():
    field = flat()
    me = tank_at(0, 100, field)
    for _ in range(10):
        drive_frame(me, field, [me], 1)
    assert me.x == pytest.approx(105) and me.fuel == 490
    me.kit.extras[UP_ENGINE] = 1
    drive_frame(me, field, [me], -1)
    assert me.fuel == 489.5


def test_driving_stops_at_the_edges_and_when_fuel_runs_out():
    field = flat()
    me = tank_at(0, 10, field)
    drive_frame(me, field, [me], -1)
    assert me.x == 10
    me.fuel = 0
    drive_frame(me, field, [me], 1)
    assert me.x == 10


def test_driving_into_another_tank_bounces_back():
    field = flat()
    me, them = tank_at(0, 100, field), tank_at(1, 113.4, field)
    drive_frame(me, field, [me, them], 1)
    assert me.x == pytest.approx(100.5 - 0.6)


def test_a_steep_wall_stops_the_tank_unless_it_has_the_hill_upgrade():
    field = flat()
    for column in range(108, WIDTH):
        field.tops[column] = GROUND - 3
    me = tank_at(0, 100, field)
    for _ in range(20):
        drive_frame(me, field, [me], 1)
    stuck = me.x
    assert stuck < 103
    me.kit.extras[UP_HILL] = 1
    for _ in range(40):
        drive_frame(me, field, [me], 1)
    assert me.x > stuck + 5


def test_driving_off_a_ledge_hurts_more_the_further_it_falls():
    field = flat()
    for column in range(110, WIDTH):
        field.tops[column] = GROUND + 30
    me = tank_at(0, 100, field)
    for _ in range(80):
        drive_frame(me, field, [me], 1)
    assert me.y == GROUND + 28
    assert 60 <= me.energy < 100


def test_a_settling_tank_stops_once_it_stands_still():
    field = flat()
    me = tank_at(0, 100, field)
    me.y -= 40
    settle(me, field)
    assert not me.settling and me.y == GROUND - 2


def test_one_parachute_covers_every_fall_until_the_next_turn():
    field = flat()
    me = tank_at(0, 100, field)
    me.kit.extras[PARACHUTES] = 1
    for _ in range(2):
        me.y -= 60
        settle(me, field)
    assert me.energy == 100 and me.kit.extras[PARACHUTES] == 0
    me.start_turn()
    me.y -= 60
    settle(me, field)
    # No parachutes left to open
    assert me.energy < 100
