import math
import random

import pytest

from ageofwar.common.battle import Battle, Unit
from ageofwar.common.data import GROUND, TURRETS
from ageofwar.common.shots import BULLETS, CODES, KINDS, Flame, OilDrop, Shrapnel

# Where the left base's oil pot pours
OIL_X = 168.0


def fight_with_target(x: float = 330.0, kind: int = 9) -> tuple[Battle, Unit]:
    """A tough enemy that stands still at x"""
    fight = Battle(random.Random(6))
    target = fight.spawn(2, kind)
    target.x = x
    target.speed = 0.0
    target.health = target.max_health = 1e6
    return fight, target


@pytest.mark.parametrize("turret", sorted(TURRETS))
def test_every_turrets_shot_hurts_a_target_standing_in_its_range(turret):
    # The catapults throw from above their aim, so like the original's they sail over short units close by. The oil
    # pours a fixed way out from the base
    stats = TURRETS[turret]
    fight, target = fight_with_target(x=OIL_X if stats.bullet == 5 else min(360.0, 52 + stats.range * 0.8))
    fight.place_turret(1, turret, 1)
    for _ in range(800):
        fight.step()
    assert target.health < target.max_health, TURRETS[turret].name


@pytest.mark.parametrize("bullet", sorted(BULLETS))
def test_every_shot_leaves_the_field_in_the_end(bullet):
    fight = Battle(random.Random(7))
    fight.add(BULLETS[bullet](fight, 52.0, 300.0, 20.0, 10, 1))
    for _ in range(3000):
        fight.step()
    assert fight.shots == []


def test_a_shot_hurts_one_enemy_and_is_gone():
    fight, target = fight_with_target(x=200.0)
    second = fight.spawn(2, 9)
    second.x = 200.0
    second.health = second.max_health = 1e6
    drop = OilDrop(fight, 200.0, GROUND - 40, 0, 50, 1)
    fight.add(drop)
    for _ in range(40):
        fight.step()
    hurt = [unit for unit in (target, second) if unit.health < unit.max_health]
    assert len(hurt) == 1 and not drop.alive


def test_shots_never_hurt_their_own_side():
    fight = Battle(random.Random(8))
    friend = fight.spawn(1, 9)
    friend.x = 200.0
    fight.add(OilDrop(fight, 200.0, GROUND - 40, 0, 50, 1))
    for _ in range(40):
        fight.step()
    assert friend.health == friend.max_health


@pytest.mark.parametrize("kind, burn", [(Flame, 10), (Shrapnel, 30)])
def test_burning_bits_only_hurt_on_the_way_down(kind, burn):
    fight, target = fight_with_target(x=200.0)
    bit = kind(fight, 200.0, GROUND - 60, 0, 0, 1)
    fight.add(bit)
    rising = math.sin(math.radians(bit.rotation)) < 0
    for _ in range(80):
        fight.step()
    assert rising and target.max_health - target.health in (0, burn)


def test_every_kind_has_a_code_the_page_draws():
    assert len(KINDS) == len(set(KINDS)) == len(CODES)
    for bullet in BULLETS.values():
        assert bullet.kind in CODES
