from tanks.common.items import (
    AIR_STRIKE,
    EXTRAS,
    FUEL,
    NOT_ENOUGH_MONEY,
    PARACHUTES,
    SMALL_MISSILE,
    UP_ENERGY,
    WEAPONS,
    Kit,
)


def test_the_shop_has_the_originals_14_weapons_and_12_extras():
    assert len(WEAPONS) == 14 and len(EXTRAS) == 12
    assert (WEAPONS[3].name, WEAPONS[3].price, WEAPONS[3].pack) == ("Atom bomb", 13000, 1)
    assert (WEAPONS[AIR_STRIKE].name, WEAPONS[AIR_STRIKE].price) == ("Air strike", 25000)
    assert (EXTRAS[FUEL].name, EXTRAS[FUEL].price, EXTRAS[FUEL].pack) == ("Fuel", 3000, 50)
    assert (EXTRAS[UP_ENERGY].name, EXTRAS[UP_ENERGY].price) == ("Upgrade energy", 5000)


def test_every_seat_starts_with_99_missiles_500_fuel_and_5000():
    kit = Kit()
    assert kit.guns == [99] + [0] * 13
    assert kit.extras[FUEL] == 500 and sum(kit.extras) == 500
    assert kit.money == 5000 and kit.score == 0 and kit.kills == 0
    assert kit.max_energy == 100


def test_buying_adds_a_pack_and_takes_the_price():
    kit = Kit()
    assert kit.buy("extra", PARACHUTES) is None
    assert kit.extras[PARACHUTES] == 5 and kit.money == 0
    assert kit.buy("weapon", 1) == NOT_ENOUGH_MONEY
    assert kit.guns[1] == 0 and kit.money == 0


def test_energy_upgrades_add_ten_health_each():
    kit = Kit()
    kit.extras[UP_ENERGY] = 3
    assert kit.max_energy == 130


def test_the_small_missile_never_runs_out_and_others_fall_back_to_it():
    kit = Kit()
    assert kit.spend_shot() == SMALL_MISSILE and kit.guns[0] == 99
    kit.guns[2] = 1
    kit.weapon = 2
    assert kit.owns(2)
    assert kit.spend_shot() == 2
    assert kit.guns[2] == 0 and kit.weapon == SMALL_MISSILE and not kit.owns(2)
