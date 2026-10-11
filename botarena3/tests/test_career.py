import pytest

from botarena3.common import career
from botarena3.common.arenas import ARENAS, FINAL
from botarena3.common.parts import PRIZE_PLATING, PRIZE_WEAPON, SECRET_LASER

LIGHT = 'AKAUMIN "DLZ-100"'
AURO = 'SANTRIN "AURO"'
LP = 'ZINTEK "LP"'
DT01 = 'RAPTOR "DT-01"'


def ready() -> dict:
    """A new career with one light robot: Auro plating and an LP gun mounted (load 5 + 3 + 2 = 10 of 16)"""
    c = career.new_career()
    career.buy(c, LIGHT)
    career.buy(c, AURO)
    career.buy(c, LP)
    career.mount(c, 0, 0)
    career.mount(c, 0, 0)
    return c


def test_a_new_career_matches_the_originals_start():
    assert career.new_career() == {
        "cash": 8200,
        "level": 1,
        "color": 1,
        "won": False,
        "robots": [],
        "inventory": [],
        "fee": 0,
    }


def test_buying_a_chassis_makes_an_enabled_robot_and_parts_go_to_the_inventory():
    c = career.new_career()
    assert career.buy(c, LIGHT) == career.BOUGHT
    assert c["robots"] == [{"name": "ROBOT NAME", "chassis": LIGHT, "plating": None, "weapon": None, "enabled": True}]
    career.buy(c, AURO)
    assert c["inventory"] == [AURO] and c["cash"] == 8200 - 3000 - 300


def test_the_shop_refuses_what_it_wouldnt_show_or_you_cant_afford():
    c = career.new_career()
    for name in ('CIRCES "XT"', SECRET_LASER, PRIZE_WEAPON, "NOT A PART"):
        with pytest.raises(career.ShopError):
            career.buy(c, name)
    c["cash"] = 100
    with pytest.raises(career.ShopError):
        career.buy(c, LP)
    assert c["inventory"] == [] and c["cash"] == 100


def test_at_most_five_robots():
    c = career.new_career()
    c["cash"] = 100000
    for _ in range(5):
        career.buy(c, LIGHT)
    with pytest.raises(career.ShopError):
        career.buy(c, LIGHT)
    career.buy(c, LP)
    assert len(c["robots"]) == 5 and c["inventory"] == [LP]


def test_plating_goes_on_first_and_a_weapon_needs_it():
    c = career.new_career()
    career.buy(c, LIGHT)
    career.buy(c, LP)
    with pytest.raises(career.ShopError):
        career.mount(c, 0, 0)
    career.buy(c, AURO)
    assert career.mount(c, 0, 1) == career.MOUNTED
    career.mount(c, 0, 0)
    assert c["robots"][0]["plating"] == AURO and c["robots"][0]["weapon"] == LP and c["inventory"] == []
    assert career.robot_load(c["robots"][0]) == 10


def test_a_part_must_fit_what_the_chassis_can_still_carry():
    c = career.new_career()
    c["cash"] = 100000
    c["level"] = 15
    career.buy(c, LIGHT)
    career.buy(c, 'GAIACORP "LB-MK2"')  # weight 8: 5 + 8 = 13 of 16
    career.mount(c, 0, 0)
    career.buy(c, 'RAPTOR "DT-02"')  # weight 5: 13 + 5 = 18 > 16
    with pytest.raises(career.ShopError):
        career.mount(c, 0, 0)
    assert not career.can_mount(c["robots"][0], 'RAPTOR "DT-02"')


def test_dismounting_takes_the_weapon_off_first():
    c = ready()
    assert career.dismount(c, 0) == career.DISMOUNTED
    assert c["robots"][0]["weapon"] is None and c["robots"][0]["plating"] == AURO and c["inventory"] == [LP]
    career.dismount(c, 0)
    assert c["robots"][0]["plating"] is None and c["inventory"] == [LP, AURO]
    with pytest.raises(career.ShopError):
        career.dismount(c, 0)


def test_selling_pays_half():
    c = ready()
    cash = c["cash"]
    career.buy(c, LP)
    assert career.sell(c, 0) == career.SOLD and c["cash"] == cash - 250 + 125
    cash = c["cash"]
    assert career.sell_robot(c, 0) == career.ROBOT_SOLD
    assert c["cash"] == cash + 1500 + 150 + 125 and c["robots"] == []


def test_enable_disable_rename_and_color():
    c = ready()
    assert career.toggle(c, 0) == career.DISABLED and c["robots"][0]["enabled"] is False
    assert career.toggle(c, 0) == career.ENABLED
    assert career.rename(c, 0, "MAX 9000") == "" and c["robots"][0]["name"] == "MAX 9000"
    for bad in ("lower", "TOO LONG A NAME 123", "BAD!", 7):
        with pytest.raises(career.ShopError):
            career.rename(c, 0, bad)
    assert career.set_color(c, 8) == career.COLOR_CHANGED and c["color"] == 8
    assert career.COLOR_CHANGED == "TEAM COLOR CHANGED!"
    for bad in (0, 9, True):
        with pytest.raises(career.ShopError):
            career.set_color(c, bad)


def test_the_cant_fight_problems_in_the_originals_order():
    c = career.new_career()
    assert career.problems(c) == [career.NO_ROBOTS]
    career.buy(c, LIGHT)
    assert career.problems(c) == [career.UNPLATED]
    career.toggle(c, 0)
    assert career.problems(c) == [career.ALL_DISABLED]
    assert career.UNPLATED.startswith("ONE OF YOUR ENABLED BOTS HAS NO PLATING")
    assert career.problems(ready()) == []


def test_arena_status_and_entering():
    c = ready()
    assert career.team_weight(c) == 10
    assert career.arena_status(c, ARENAS[0]) == "good"
    assert career.arena_status(c, ARENAS[1]) == "locked"
    c["level"] = 15
    c["cash"] = 0
    assert career.arena_status(c, FINAL) == "poor"
    c["cash"] = 8200
    assert career.enter_arena(c, 0) is ARENAS[0]
    assert c["cash"] == 8200 - ARENAS[0].fee and c["fee"] == ARENAS[0].fee


def test_too_heavy_and_both():
    c = career.new_career()
    c["cash"] = 100000
    c["level"] = 15
    career.buy(c, 'XEROI "DELIVERANCE"')
    career.buy(c, 'KURON "SHRED-MK3"')
    career.mount(c, 0, 0)  # load 30 + 25 = 55 > Orientation's 35
    assert career.arena_status(c, ARENAS[0]) == "bad"
    c["cash"] = 0
    assert career.arena_status(c, ARENAS[1]) in ("both", "bad")
    with pytest.raises(career.ShopError):
        career.enter_arena(c, 0)


def test_cant_enter_with_problems_or_a_bad_index():
    c = career.new_career()
    for index in (0, -1, 15, True, "0"):
        with pytest.raises(career.ShopError):
            career.enter_arena(c, index)
    assert c["cash"] == 8200


def test_a_win_pays_the_prize_and_raises_the_level():
    c = ready()
    arena = career.enter_arena(c, 0)
    assert career.finish_arena(c, arena, won=True) is False
    assert c["cash"] == 8200 - 3000 - 300 - 250 + 200 and c["level"] == 2 and c["fee"] == 0


def test_a_loss_keeps_the_fee_spent():
    c = ready()
    c["level"] = 2
    cash = c["cash"]
    arena = career.enter_arena(c, 1)
    career.finish_arena(c, arena, won=False)
    assert c["cash"] == cash - arena.fee and c["level"] == 2 and c["fee"] == 0


def test_the_first_final_win_beats_the_game_once():
    c = ready()
    c["level"] = 15
    c["cash"] = 30000
    arena = career.enter_arena(c, len(ARENAS) - 1)
    assert career.finish_arena(c, arena, won=True) is True
    assert c["won"] is True and c["level"] == 18 and c["inventory"][-2:] == [PRIZE_WEAPON, PRIZE_PLATING]
    c["cash"] = 30000
    career.enter_arena(c, len(ARENAS) - 1)
    assert career.finish_arena(c, arena, won=True) is False
    assert c["inventory"].count(PRIZE_WEAPON) == 1


def test_a_refund_gives_the_held_fee_back():
    c = ready()
    c["level"] = 2
    cash = c["cash"]
    career.enter_arena(c, 1)
    career.refund(c)
    assert c["cash"] == cash and c["fee"] == 0


def test_the_team_is_a_copy_of_the_enabled_robots():
    c = ready()
    career.buy(c, LIGHT)
    career.toggle(c, 1)
    assert career.team(c) == [{"name": "ROBOT NAME", "chassis": LIGHT, "plating": AURO, "weapon": LP}]


def test_fight_problem_checks_the_team_and_the_weight_class():
    assert career.fight_problem(None, None) is not None
    assert career.fight_problem(career.new_career(), None) is not None
    assert career.fight_problem(ready(), "ORIENTATION") is None
    heavy = ready()
    heavy["robots"][0]["chassis"] = 'XEROI "DELIVERANCE"'
    heavy["robots"][0]["plating"] = 'KURON "SHRED-MK3"'  # 30 + 25 + 2 = 57, over Orientation's 35
    assert career.fight_problem(heavy, "ORIENTATION") is not None
    assert career.fight_problem(heavy, None) is None


def test_the_view_adds_what_the_page_needs():
    view = career.view(ready())
    assert view["robots"][0]["load"] == 10 and view["robots"][0]["max"] == 16
    assert view["weight"] == 10 and view["problems"] == [] and len(view["arenas"]) == 15
    assert view["arenas"][0] == "good" and career.view(None) is None


def test_requests_with_bad_values_change_nothing():
    for kind, value in [
        ("buy", 5),
        ("sell", "0"),
        ("sell", True),
        ("mount", [0]),
        ("mount", [0, 1.5]),
        ("rename", [0, 5]),
        ("toggle", None),
        ("color", "red"),
        ("teleport", 1),
    ]:
        assert career.action(kind, value) is None, (kind, value)
    c = ready()
    before = repr(c)
    for kind, value in [("sell", 3), ("toggle", 4), ("mount", [9, 0]), ("dismount", -1), ("sellRobot", 2)]:
        act = career.action(kind, value)
        with pytest.raises(career.ShopError):
            act(c)
    assert repr(c) == before
    assert career.action("buy", LP)(c) == career.BOUGHT
