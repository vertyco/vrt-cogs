from botarena3.common import arenas, parts


def test_the_tables_have_the_originals_counts():
    assert len(parts.WEAPONS) == 18 and len(parts.PLATINGS) == 11 and len(parts.CHASSIS) == 8
    assert len(arenas.ARENAS) == 15 and len(arenas.CHALLENGES) == 7


def test_weapons_keep_the_originals_numbers():
    lp = parts.WEAPONS['ZINTEK "LP"']
    assert (lp.weight, lp.cost, lp.damage, lp.refire, lp.max_range, lp.min_range, lp.spread) == (
        2,
        250,
        10,
        50,
        170,
        25,
        3,
    )
    assert (lp.gun, lp.sound, lp.rico_min, lp.rico_max, lp.hostile, lp.level) == (10, "gun04", 1, 3, True, 1)
    tool = parts.WEAPONS['ZENI "PRS"']
    assert tool.damage == -65 and tool.hostile is False and tool.level == 9
    assert parts.WEAPONS[parts.SECRET_LASER].damage == 9001
    assert parts.WEAPONS[parts.PRIZE_WEAPON].level == 30


def test_platings_and_chassis_keep_the_originals_numbers():
    auro = parts.PLATINGS['SANTRIN "AURO"']
    assert (auro.weight, auro.cost, auro.shielding, auro.graphic, auro.level) == (3, 300, 200, 9, 1)
    assert parts.PLATINGS[parts.PRIZE_PLATING].shielding == 2000
    light = parts.CHASSIS['AKAUMIN "DLZ-100"']
    assert (light.weight, light.cost, light.max_load, light.shielding, light.level) == (5, 3000, 16, 50, 1)
    assert parts.CHASSIS['XEROI "DELIVERANCE"'].max_load == 85


def test_the_shop_lists_parts_by_level_and_never_the_secret_laser():
    assert [w.name for w in parts.for_sale("weapon", 1)] == ['ZINTEK "LP"', 'KEDRON "SPKL-D4"', 'RAPTOR "DT-01"']
    assert [c.name for c in parts.for_sale("chassis", 1)] == ['AKAUMIN "DLZ-100"']
    beaten = [w.name for w in parts.for_sale("weapon", 18)]
    assert len(beaten) == 16 and parts.SECRET_LASER not in beaten and parts.PRIZE_WEAPON not in beaten


def test_arenas_keep_the_originals_order_and_numbers():
    first, final = arenas.ARENAS[0], arenas.FINAL
    assert (first.name, first.weight_class, first.fee, first.prize, first.level, first.win_level) == (
        "ROXTAN PARK ARENA",
        "ORIENTATION",
        0,
        200,
        1,
        2,
    )
    assert [r["name"] for r in first.opponents] == ["WRECKER", "STEELHEART"]
    assert (final.name, final.fee, final.prize, final.level, final.win_level) == (
        "THE FINAL HOUR",
        22000,
        50000,
        15,
        16,
    )
    assert list(arenas.WEIGHT_CLASSES.items()) == [
        ("ORIENTATION", 35),
        ("LIGHTWEIGHT", 45),
        ("MIDDLEWEIGHT", 70),
        ("HEAVYWEIGHT", 95),
        ("MEGAWEIGHT", 120),
        ("SUPER MEGAWEIGHT", 150),
    ]


def test_challenges_bring_both_teams():
    intro = arenas.CHALLENGES[0]
    assert intro.name == "TRAINING: INTRODUCTION" and intro.background == 1
    assert intro.players[0]["name"] == "BULLYBOY" and intro.players[0]["weapon"] == 'RAPTOR "DT-01"'
    assert arenas.CHALLENGES[-1].name == "FUN: HAMMERTIME"


def test_every_ready_made_robot_uses_real_parts_and_has_plating():
    teams = (
        [a.opponents for a in arenas.ARENAS]
        + [c.players for c in arenas.CHALLENGES]
        + [c.opponents for c in arenas.CHALLENGES]
    )
    for team in teams:
        assert team
        for robot in team:
            assert robot["chassis"] in parts.CHASSIS and robot["plating"] in parts.PLATINGS
            assert robot["weapon"] is None or robot["weapon"] in parts.WEAPONS
