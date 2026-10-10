"""The shot engine against the original's formulas, worked from the decompiled ActionScript"""

import math

import pytest

from tanks.common.items import AIR_STRIKE, PARACHUTES, SHIELD
from tanks.common.physics import (
    BNUKE,
    MISSILE,
    NUKE,
    SMALL,
    Shell,
    Shot,
    in_fireball,
    js_div,
    launch,
)
from tanks.common.terrain import js_round
from tanks.tests.helpers import GROUND, flat, rng, tank_at

SMALL_MISSILE, MISSILE_WEAPON, VOLCANO, SHOWER, HOT_SHOWER, BALL, BALL_V2 = 0, 1, 4, 5, 6, 8, 11


def fire(weapon, angle, power, tanks, field, strike=(0.0, 1)):
    me = tanks[0]
    me.angle, me.power = angle, power
    shot = Shot(field, tanks, me, rng())
    shot.fire(weapon, strike)
    return shot, shot.run()


def events(script, kind):
    return [event for event in script["events"] if event[1] == kind]


def flight_time(steps):
    """The original adds 0.1 to its time each frame, with the same rounding drift"""
    t = 0.0
    for _ in range(steps):
        t += 0.1
    return t


def test_a_shell_follows_the_original_flight_and_lands_back_on_its_own_tank():
    field = flat()
    me = tank_at(0, 100, field)
    shot, script = fire(SMALL_MISSILE, 90, 20, [me], field)
    # Straight up at power 20: it leaves its tank's box, then comes down onto it at t = 4.0 (the 41st step)
    t = flight_time(40)
    y = (me.y - 1) - math.sin(0.017 * 90) * 20 * t + 9.81 / 2 * t * t
    boom = events(script, "boom")[0]
    assert boom[0] == 41 and boom[2] == 100.0 and boom[3] == round(y, 1)
    # The blast goes off five steps later: 50 x 0.3958 x 0.8726 pixels wide, harm 5, by distance to the tank
    width = 50 * 0.3958 * 0.8726
    damage = js_round(width / ((abs(y - me.y) + 1) / 5))
    assert me.energy == 100 - damage
    # Hurting yourself costs 50 a point
    assert me.kit.money == 5000 - damage * 50 and me.kit.score == -damage * 50


def test_wind_is_added_to_the_sideways_speed_every_step():
    field = flat(wind=60)
    me = tank_at(0, 100, field)
    shot, script = fire(SMALL_MISSILE, 90, 30, [me], field)
    points = script["shells"][0][1]
    # Step 11: t = 1.0, and the sideways speed has gained 60 / 600 ten times
    vox = math.cos(math.radians(90)) * 30 + 10 * 60 / 600
    assert points[20] == round(100 + vox * flight_time(10), 1)


def test_a_ground_hit_digs_the_originals_crater():
    field = flat()
    me = tank_at(0, 100, field)
    shot, script = fire(SMALL_MISSILE, 135, 40, [me], field)
    shell = shot.shells[0]
    width = SMALL.width
    column = js_round(shell.x)
    dist = math.hypot(column - shell.x, GROUND - shell.y)
    # Under the fireball a column drops by par2 + par1 / 2 (7.5 + 7.5), less toward the edge
    assert field.tops[column] == pytest.approx(GROUND + 15 * math.cos(0.017 * dist * (180 / width)))
    changed = [c for c, top in enumerate(field.tops) if top != GROUND]
    assert changed and all(abs(c - shell.x) <= width / 2 + 1 for c in changed)


def test_an_atom_bomb_digs_deeper_and_wider():
    field = flat()
    shell = Shell("plain", NUKE, tank_at(0, 50, field), 300.0, 300.0, 0, 0, rotation=0)
    shot = Shot(field, [shell.owner], shell.owner, rng())
    shot.blast(shell)
    # par1 35 and par2 30: the top moves down 30 + 35 / 2 at full strength
    assert field.tops[300] == pytest.approx(GROUND + 47.5)
    assert NUKE.width == 50 * 3.8341
    assert sum(1 for top in field.tops if top != GROUND) > 150


def test_blast_damage_falls_off_with_distance_and_pays_the_attacker():
    field = flat()
    me, them = tank_at(0, 50, field), tank_at(1, 210, field)
    shell = Shell("plain", MISSILE, me, 200.0, 290.0, 0, 0, rotation=0)
    Shot(field, [me, them], me, rng()).blast(shell)
    distance = math.hypot(200 - them.x, 290 - them.y)
    damage = js_round(MISSILE.width / ((distance + 1) / 13))
    assert them.energy == 100 - damage
    assert me.kit.money == 5000 + damage * 100 and me.kit.score == damage * 100


def test_a_kill_pays_5000_once_however_many_blasts_hit_the_wreck():
    field = flat()
    me, them = tank_at(0, 50, field), tank_at(1, 210, field, energy=5)
    for _ in range(3):
        Shot(field, [me, them], me, rng()).blast(Shell("plain", MISSILE, me, 210.0, 297.0, 0, 0, rotation=0))
    # Damage to an unshielded tank is capped at its health, and a dead tank takes no more
    assert me.kit.kills == 1
    assert me.kit.money == 5000 + 5 * 100 + 5000


def test_a_shield_soaks_the_blast_and_breaks_into_double_damage():
    field = flat()
    me, them = tank_at(0, 50, field), tank_at(1, 210, field)
    them.raise_shield(SHIELD)
    them.kit.extras[SHIELD] = 0
    shell = Shell("plain", BNUKE, me, 210.0, 297.0, 0, 0, rotation=0)
    Shot(field, [me, them], me, rng()).blast(shell)
    distance = math.hypot(0, 297 - them.y)
    soak = js_round(BNUKE.width / ((distance / 2 + 1) / 24))
    # The Shield holds 200; what's left over hits the tank twice as hard
    assert soak > 200
    assert them.shield is None
    assert them.energy == 100 - (soak - 200) * 2


def test_the_volcano_bomb_throws_five_pieces_three_steps_after_it_hits():
    field = flat()
    me = tank_at(0, 100, field)
    shot, script = fire(VOLCANO, 135, 40, [me], field)
    hit = events(script, "boom")[0]
    pieces = script["shells"][1:]
    assert len(pieces) == 5
    assert all(piece[0] == hit[0] + 4 for piece in pieces)
    assert all(piece[1][:2] == [hit[2], round(shot.shells[0].y - 5, 1)] for piece in pieces)
    assert len(events(script, "boom")) == 6


def test_the_shower_splits_into_five_at_three_seconds_and_the_hot_shower_into_seven():
    field = flat()
    for weapon, count in ((SHOWER, 5), (HOT_SHOWER, 7)):
        field = flat()
        shot, script = fire(weapon, 135, 50, [tank_at(0, 100, field)], field)
        pieces = shot.shells[1:]
        assert len(pieces) == count
        # The split happens on the step where t reaches 3.0; the pieces fly from the next step
        assert all(piece.start_step == 32 for piece in pieces)
        spreads = sorted(piece.spread for piece in pieces)
        assert spreads == [(n - count // 2) / 20 for n in range(count)]
        blast = BNUKE if weapon == HOT_SHOWER else pieces[0].blast
        assert all(piece.blast is blast for piece in pieces)


def test_a_ball_rolls_downhill_and_blows_up_in_the_valley():
    field = flat()
    # A slope falling to the right from x = 150 down to a valley at x = 250, then rising again
    for column in range(150, 400):
        field.tops[column] = GROUND + (column - 150) * 0.5 if column <= 250 else GROUND + 50 - (column - 250) * 0.5
    me = tank_at(0, 60, field)
    shot, script = fire(BALL, 135, 32, [me], field)
    ball = shot.shells[0]
    # It landed on the slope, rolled a pixel a step down to the lowest column, and stopped there
    assert len(ball.points) > 20
    assert js_round(ball.x) == 250
    assert events(script, "boom")[0][3] == round(ball.y, 1)


def test_a_v2_ball_on_a_slope_blows_up_where_it_lands():
    field = flat()
    for column in range(150, 400):
        field.tops[column] = GROUND + (column - 150) * 0.5
    me = tank_at(0, 60, field)
    shot, script = fire(BALL_V2, 135, 32, [me], field)
    ball = shot.shells[0]
    boom = events(script, "boom")[0]
    # The original's V2 compares the slope the other way round, so on a plain slope it never starts rolling
    assert boom[2] == round(ball.x, 1)
    assert ball.points[-1][0] == round(ball.x, 1)


def test_the_air_strike_drops_five_shells_from_above_the_field():
    field = flat(wind=80)
    me = tank_at(0, 50, field)
    shot, script = fire(AIR_STRIKE, 90, 50, [me], field, strike=(300.0, 1))
    starts = [shell[1][:2] for shell in script["shells"]]
    assert starts == [[180.0 + 20 * n, -50.0] for n in range(5)]
    # They fly right at speed 10 with no wind, 0.12 of a time unit a step
    assert script["shells"][0][1][2] == round(180 + 10 * 0.12, 1)
    assert len(events(script, "boom")) == 5
    left = Shot(flat(), [tank_at(0, 50, flat())], tank_at(0, 50, flat()), rng())
    left.fire(AIR_STRIKE, (300.0, -1))
    assert [shell.x0 for shell in left.shells] == [420.0 - 20 * n for n in range(5)]


def test_a_dead_tank_blows_up_five_steps_later_and_hurts_its_neighbour():
    field = flat()
    me, wreck, near = tank_at(0, 50, field), tank_at(1, 300, field, energy=1), tank_at(2, 330, field)
    shot = Shot(field, [me, wreck, near], me, rng())
    shot.blast(Shell("plain", MISSILE, me, 300.0, 296.0, 0, 0, rotation=0))
    near_after_blast = near.energy
    money_before = wreck.kit.money
    script = shot.run()
    die = events(script, "die")[0]
    assert die[2] == 1
    distance = math.hypot(300 - near.x, wreck.y - near.y)
    damage = min(js_round(70 / ((distance + 1) / 14)), near_after_blast)
    assert near.energy == near_after_blast - damage
    # The wreck's owner is paid for what its explosion did
    assert wreck.kit.money == money_before + damage * 100


def test_a_shell_that_leaves_the_field_tells_its_owner_where():
    field = flat()
    me = tank_at(0, 500, field)
    shot, script = fire(MISSILE_WEAPON, 160, 80, [me], field)
    assert not events(script, "boom")
    assert me.last_shot is not None and me.last_shot[0] > 550


def test_tanks_fall_when_their_ground_is_blown_away():
    field = flat()
    me, them = tank_at(0, 50, field), tank_at(1, 300, field)
    for column in range(280, 321):
        field.tops[column] = GROUND + 60
    script = Shot(field, [me, them], me, rng()).run()
    # 60 pixels with no parachute: it lands two pixels above the new ground, hurt by the fall
    assert them.y == GROUND + 60 - 2
    assert 0 < them.energy < 100
    assert events(script, "tank")[-1][3]["y"] == GROUND + 58


def test_a_parachute_opens_and_is_used_up():
    field = flat()
    me, them = tank_at(0, 50, field), tank_at(1, 300, field)
    them.kit.extras[PARACHUTES] = 2
    for column in range(280, 321):
        field.tops[column] = GROUND + 60
    script = Shot(field, [me, them], me, rng()).run()
    assert them.energy == 100 and them.y == GROUND + 58
    assert them.kit.extras[PARACHUTES] == 1
    assert any(event[3]["chute"] for event in events(script, "tank") if event[2] == 1)


def test_a_teleport_moves_the_tank_at_frame_41_and_it_falls():
    field = flat()
    me = tank_at(0, 50, field)
    shot = Shot(field, [me], me, rng())
    shot.teleport(400.0, 100.0)
    script = shot.run()
    assert script["events"][0] == [0, "beam", 0, 50.0, GROUND - 2, 400.0, 100.0]
    moved = [event for event in events(script, "tank") if event[0] == 40]
    assert moved and moved[0][3]["x"] == 400.0 and moved[0][3]["y"] == 100.0
    assert me.y == GROUND - 2
    assert me.energy < 100


def test_shells_leave_their_own_tank_before_they_can_hit_it():
    field = flat()
    me = tank_at(0, 100, field)
    shell = launch(SMALL, "plain", me, me.x, me.y - 1, 135, 50)
    assert shell.immune


def test_the_fireball_shape_has_a_middle_and_two_side_flames():
    assert in_fireball(0, 0)
    assert in_fireball(20, 0) and in_fireball(-20, 0)
    # The gap between the middle and the side flames isn't part of the drawing
    assert not in_fireball(14.5, 0)
    assert not in_fireball(0, 13)


def test_division_by_zero_works_like_flash():
    assert js_div(1, 0) == math.inf and js_div(-1, 0) == -math.inf
    assert math.isnan(js_div(0, 0))
    assert js_div(6, 3) == 2
