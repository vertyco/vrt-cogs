import random

from ageofwar.common.battle import Battle
from ageofwar.common.cpu import AGE_FRAMES, MAX_ALIVE, Computer
from ageofwar.common.data import BASE_HEALTH, EVOLVE_HEALTH, START_CASH, age_units


def computer_battle(seed: int = 2) -> Battle:
    fight = Battle(random.Random(seed))
    side = fight.sides[2]
    side.cpu = Computer(side)
    # Nothing on the left fights back, so the computer's units would walk into the left base
    fight.sides[1].base.health = 1e9
    return fight


def test_the_computer_trains_units_of_its_age_and_keeps_six_at_most():
    fight = computer_battle()
    most = 0
    for _ in range(6000):
        fight.step()
        mine = [unit for unit in fight.units if unit.side == 2 and not unit.dead]
        most = max(most, len(mine))
        assert all(unit.kind in age_units(1) for unit in mine)
    assert most == MAX_ALIVE


def test_the_computer_never_spends_money():
    fight = computer_battle()
    for _ in range(3000):
        fight.step()
    assert fight.sides[2].cash == START_CASH


def test_the_computer_moves_to_the_next_age_on_a_timer():
    fight = computer_battle()
    for _ in range(AGE_FRAMES - 1):
        fight.step()
    assert fight.sides[2].age == 1
    fight.step()
    side = fight.sides[2]
    assert side.age == 2 and side.base.max_health == BASE_HEALTH + EVOLVE_HEALTH * 2


def test_the_computer_builds_its_first_turret_on_schedule():
    fight = computer_battle()
    for _ in range(999):
        fight.step()
    assert fight.sides[2].turrets[0] is None
    fight.step()
    assert fight.sides[2].turrets[0].kind == 1


def test_the_computers_training_shows_on_its_bar():
    fight = computer_battle(seed=3)
    seen = set()
    for _ in range(2000):
        fight.step()
        training, progress = fight.side_view(fight.sides[2])[6:8]
        assert training in (0, *age_units(1))
        if training:
            seen.add(progress)
    assert min(seen) < 20 and max(seen) > 80
