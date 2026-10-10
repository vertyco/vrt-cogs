import random

import pytest

from ageofwar.common.battle import HEAL_FRAMES, Battle, Unit
from ageofwar.common.data import (
    BASE_HEALTH,
    EVOLVE_HEALTH,
    EVOLVE_XP,
    SPECIAL_COOLDOWN,
    SPOT_PRICES,
    START_CASH,
    TURRETS,
    UNITS,
    flash_round,
    reward,
)


def battle(seed: int = 1) -> Battle:
    return Battle(random.Random(seed))


def run(fight: Battle, frames: int) -> None:
    for _ in range(frames):
        fight.step()


def test_flash_round_rounds_halves_up_like_actionscript():
    assert [flash_round(v) for v in (2.5, -2.5, -0.4, -0.5, -0.6, 19.5)] == [3, -2, 0, 0, -1, 20]


def test_a_bought_unit_walks_out_once_its_training_is_done():
    fight = battle()
    assert fight.buy_unit(1, 1)
    assert fight.sides[1].cash == START_CASH - UNITS[1].cost
    run(fight, UNITS[1].train - 1)
    assert fight.units == []
    run(fight, 1)
    assert [unit.kind for unit in fight.units] == [1]


def test_the_queue_holds_five_and_trains_them_in_order():
    fight = battle()
    fight.sides[1].cash = 10_000
    assert all(fight.buy_unit(1, kind) for kind in (1, 2, 3, 1, 2))
    assert not fight.buy_unit(1, 1)
    assert fight.sides[1].tray == [1, 2, 3, 1, 2]
    run(fight, UNITS[1].train)
    assert fight.sides[1].tray == [2, 3, 1, 2, 0] and fight.sides[1].training == 2


def test_units_from_another_age_or_without_the_money_are_refused():
    fight = battle()
    assert not fight.buy_unit(1, 4)
    fight.sides[1].cash = UNITS[3].cost - 1
    assert not fight.buy_unit(1, 3)
    assert fight.sides[1].cash == UNITS[3].cost - 1


def test_a_kill_pays_the_killer_and_gives_both_sides_experience():
    fight = battle()
    knight = fight.spawn(1, 6)
    club = fight.spawn(2, 1)
    knight.x, club.x = 480.0, 520.0
    run(fight, 400)
    assert club.dead
    paid = reward(1)
    assert fight.sides[1].cash == START_CASH + paid
    assert fight.sides[1].xp == paid * 2
    assert fight.sides[2].xp == flash_round(paid / 2)


def test_a_dead_unit_lies_there_before_it_goes():
    fight = battle()
    unit = fight.spawn(2, 1)
    unit.health = 0
    run(fight, 2)
    assert unit.dead and unit in fight.units and unit not in fight.field
    run(fight, 80)
    assert unit not in fight.units


def test_units_stop_behind_a_friend_instead_of_walking_through_it():
    fight = battle()
    front = fight.spawn(1, 1)
    back = fight.spawn(1, 1)
    front.x, back.x = 300.0, 250.0
    fight.sides[2].base.health = 1e9
    run(fight, 600)
    assert back.x < front.x - (front.half_width + back.half_width)


def test_a_turret_shoots_an_enemy_in_range():
    fight = battle()
    fight.place_turret(1, 1, 1)
    enemy = fight.spawn(2, 3)
    enemy.x = 220.0
    shots = 0
    for _ in range(200):
        fight.step()
        shots = max(shots, len(fight.shots))
    assert shots > 0
    assert enemy.health < enemy.max_health


def test_turrets_need_a_free_spot_and_the_money():
    fight = battle()
    assert fight.build_turret(1, 1, 1)
    assert fight.sides[1].cash == START_CASH - TURRETS[1].cost
    assert not fight.build_turret(1, 1, 1)
    assert not fight.build_turret(1, 1, 2)
    assert not fight.build_turret(1, 4, 1)


def test_selling_a_turret_pays_half_its_price():
    fight = battle()
    fight.sides[1].cash = 1000
    fight.build_turret(1, 2, 1)
    cash = fight.sides[1].cash
    assert fight.sell_turret(1, 1)
    assert fight.sides[1].cash == cash + flash_round(TURRETS[2].cost / 2)
    assert not fight.sell_turret(1, 1)


def test_extra_turret_spots_cost_more_each_time_and_stop_at_three():
    fight = battle()
    fight.sides[1].cash = sum(SPOT_PRICES) + 5
    assert all(fight.add_spot(1) for _ in SPOT_PRICES)
    assert fight.sides[1].cash == 5 and fight.sides[1].addons == 3
    fight.sides[1].cash = 100_000
    assert not fight.add_spot(1)


def test_evolving_needs_experience_and_adds_base_health():
    fight = battle()
    side = fight.sides[1]
    side.xp = EVOLVE_XP[0] - 1
    assert not fight.evolve(1)
    side.xp = EVOLVE_XP[0]
    assert fight.evolve(1)
    assert side.age == 2
    assert side.base.health == side.base.max_health == BASE_HEALTH + EVOLVE_HEALTH * 2


@pytest.mark.parametrize("age", [1, 2, 4, 5])
def test_each_ages_special_hurts_the_enemy(age):
    fight = battle(age)
    fight.sides[1].age = age
    enemies = [fight.spawn(2, 1) for _ in range(12)]
    for number, enemy in enumerate(enemies):
        enemy.x = 150.0 + number * 50
    run(fight, 2)
    assert fight.special(1)
    run(fight, 300)
    assert any(enemy.health < enemy.max_health for enemy in enemies)
    assert fight.specials == []


def test_the_third_ages_special_heals_its_own_units():
    fight = battle()
    fight.sides[1].age = 3
    unit = fight.spawn(1, 7)
    unit.health = 50.0
    run(fight, 2)
    assert fight.special(1)
    run(fight, 10)
    assert unit.health > 50
    run(fight, HEAL_FRAMES)
    assert fight.sides[1].healing == 0


def test_a_special_needs_its_cooldown():
    fight = battle()
    run(fight, 2)
    assert fight.special(1)
    run(fight, SPECIAL_COOLDOWN - 1)
    assert not fight.special(1)
    run(fight, 1)
    assert fight.special(1)


def test_a_base_falls_once_its_rounded_health_drops_below_zero():
    fight = battle()
    fight.sides[2].base.health = -0.4
    fight.step()
    assert fight.winner is None
    fight.sides[2].base.health = -0.6
    fight.step()
    assert fight.winner == 1


def test_the_computers_units_are_stronger_on_harder_difficulties():
    unit = Unit(1, 3, 2, 500.0, 2.0)
    assert unit.health == UNITS[3].health * 2 and unit.damage == UNITS[3].damage * 2


def test_the_same_seed_plays_the_same_battle():
    def play(seed):
        fight = battle(seed)
        fight.sides[1].cash = fight.sides[2].cash = 5000
        for kind in (1, 2, 3, 2):
            fight.buy_unit(1, kind)
            fight.buy_unit(2, kind)
        fight.place_turret(1, 1, 1)
        return [fight.view() for _ in range(900) if fight.step() is None]

    assert play(4) == play(4)


def test_a_snapshot_holds_units_shots_and_both_sides():
    fight = battle()
    fight.spawn(1, 1)
    fight.place_turret(2, 1, 1)
    view = fight.view()
    assert set(view) == {"f", "u", "b", "x", "s", "e"}
    # Places go out in tenths, and a new unit stands a random fraction of a pixel past its spawn point
    assert view["u"][0][:3] == [1, 1, 1] and 1500 <= view["u"][0][3] <= 1510
    assert len(view["s"]) == 2 and view["s"][1][10][0][0] == 1
