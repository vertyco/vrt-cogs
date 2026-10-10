import math
import random

import pytest

from tanks.common.cpu import LEVELS, TABLE, Brain, nearest, plan_first
from tanks.common.physics import Shot
from tanks.tests.helpers import GROUND, flat, rng, tank_at


def shoot(me, tanks, field):
    shot = Shot(field, tanks, me, rng())
    shot.fire(0)
    shot.run()


@pytest.mark.parametrize("level,divisor", [("very_easy", 120), ("easy", 120), ("normal", 110), ("hard", 80)])
def test_the_opening_shot_is_45_degrees_toward_the_target(level, divisor):
    field = flat()
    me, them = tank_at(0, 100, field), tank_at(1, 300, field)
    angle, power = plan_first(TABLE[level], me, them, wind=40)
    assert angle == 135 and power == 200 / (2 + 200 / divisor)
    angle, _ = plan_first(TABLE[level], them, me, wind=40)
    assert angle == 45


def test_very_hard_also_allows_for_wind_and_height_in_its_opening_shot():
    field = flat()
    me, them = tank_at(0, 100, field), tank_at(1, 300, field)
    them.y -= 40
    _, power = plan_first(TABLE["very_hard"], me, them, wind=26)
    assert power == pytest.approx(200 / (2 + 200 / 80) - 26 / 13 + 40 / 20)


@pytest.mark.parametrize("level", LEVELS)
def test_every_level_only_picks_shots_a_person_could_make(level):
    rng_ = random.Random(level)
    for _ in range(300):
        field = flat(wind=rng_.uniform(-90, 90))
        me = tank_at(0, rng_.uniform(20, 520), field, energy=rng_.uniform(1, 100))
        them = tank_at(1, rng_.uniform(20, 520), field)
        them.y -= rng_.uniform(-80, 80)
        brain = Brain(level)
        brain.new_round(me, [me, them])
        brain.turns = rng_.choice((0, 3))
        me.last_shot = (rng_.uniform(-50, 600), rng_.uniform(-100, 420))
        me.angle, me.power = rng_.randrange(0, 181, 2), rng_.uniform(0, 100)
        angle, power = brain.plan(me, [me, them], field.wind)
        assert type(angle) is int and 0 <= angle <= 180
        assert math.isfinite(power) and 0 <= power <= min(100, me.energy)


@pytest.mark.parametrize("gap", [120, 200, 280, 360])
def test_very_hard_hits_a_still_target_on_flat_ground_with_no_wind(gap):
    field = flat()
    me, them = tank_at(0, 80, field), tank_at(1, 80 + gap, field)
    brain = Brain("very_hard")
    brain.new_round(me, [me, them])
    for _ in range(2):
        me.angle, me.power = brain.plan(me, [me, them], field.wind)
        brain.fired(field.wind)
        shoot(me, [me, them], field)
        if them.energy < 100:
            break
        field.tops[:] = [GROUND] * len(field.tops)
    assert them.energy < 100


def test_a_computer_corrects_from_where_its_last_shot_landed():
    field = flat()
    me, them = tank_at(0, 80, field), tank_at(1, 400, field)
    brain = Brain("normal")
    brain.new_round(me, [me, them])
    me.angle, me.power = brain.plan(me, [me, them], 0)
    first_power = me.power
    # The opening shot landed short of the target, so the next one has more power
    me.last_shot = (300.0, GROUND)
    _, power = brain.plan(me, [me, them], 0)
    assert power > first_power


def test_computers_go_for_the_nearest_living_tank_and_start_over_when_it_dies():
    field = flat()
    me, close, far = tank_at(0, 100, field), tank_at(1, 200, field), tank_at(2, 400, field)
    assert nearest(me, [me, close, far]) is close
    brain = Brain("hard")
    brain.new_round(me, [me, close, far])
    brain.plan(me, [me, close, far], 0)
    me.last_shot = (150.0, GROUND)
    close.alive = False
    angle, power = brain.plan(me, [me, close, far], 0)
    assert brain.target is far and brain.turns == 1
    assert (angle, power) == (135, math.ceil(300 / (2 + 300 / 80)))


def test_a_plan_the_original_would_divide_by_zero_on_starts_over():
    field = flat()
    me, them = tank_at(0, 100, field), tank_at(1, 300, field)
    brain = Brain("hard")
    brain.new_round(me, [me, them])
    brain.turns = 1
    # At 40 degrees the hard level's wind weighting is 420 - 3 x 140 = 0, and a weak last shot that fell straight
    # down below the tank makes its wind correction 0 / 0
    me.angle, me.power, me.last_shot = 40, 20, (100.0, GROUND + 80)
    angle, power = brain.plan(me, [me, them], 10)
    assert (angle, power) == (135, math.ceil(200 / (2 + 200 / 80)))
