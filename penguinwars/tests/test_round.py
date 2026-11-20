from math import hypot
import random

from pytest import approx

from penguinwars.common.round import (
    DT,
    END_PAUSE,
    SEATS,
    Push,
    Round,
    friction,
    speed_for,
    stop_distance,
)
from penguinwars.common.tuning import Tuning


def make_round(**rules):
    return Round(Tuning(**rules), random.Random(3))


def run(game, seconds):
    for _ in range(round(seconds / DT)):
        game.step()


def two_penguins(gap=0.5):
    """Seats 0 and 1 on the ice with the rest already in the water."""
    game = make_round()
    for seat in range(2, SEATS):
        game.penguins[seat].alive = False
    a, b = game.penguins[0], game.penguins[1]
    a.x, a.z, b.x, b.z = -gap / 2, 0.0, gap / 2, 0.0
    a.cd = b.cd = 0.0
    return game


def speed(game, seat):
    p = game.penguins[seat]
    return hypot(p.vx, p.vz)


def run_until_hit(game, limit=3.0):
    """Steps until a hit or bounce and returns the slider speed on arrival (after that step friction)."""
    for _ in range(round(limit / DT)):
        before = speed(game, 0)
        game.step()
        if any(e[0] in ("hit", "bounce") for e in game.events):
            return friction(before, DT, game.tuning)
    raise AssertionError("no hit happened")


def test_a_full_slide_travels_about_half_the_ice():
    assert stop_distance(11, Tuning()) == approx(5.18, abs=0.01)


def test_speed_for_undoes_stop_distance():
    tuning = Tuning()
    assert stop_distance(speed_for(3.0, tuning), tuning) == approx(3.0, abs=0.01)


def test_stepping_the_friction_lands_near_the_stop_distance():
    tuning = Tuning()
    v, travelled = 11.0, 0.0
    while v > 0:
        travelled += v * DT
        v = friction(v, DT, tuning)
    assert travelled == approx(stop_distance(11, tuning), abs=0.2)


def test_head_on_hit_mostly_stops_the_slider_and_launches_the_other():
    game = two_penguins(gap=0.5)
    game.slide(0, 1, 0, 1.0)
    before = run_until_hit(game)
    assert speed(game, 0) < 0.1 * before and speed(game, 1) > 1.0 * before


def test_a_braced_penguin_stays_and_the_attacker_bounces_back():
    game = two_penguins(gap=0.5)
    game.brace(1)
    game.slide(0, 1, 0, 1.0)
    start = game.penguins[1].x
    run_until_hit(game)
    assert game.penguins[0].vx < 0
    run(game, 0.5)
    assert abs(game.penguins[1].x - start) < 0.3


def test_a_bounce_into_the_water_credits_the_bracer():
    game = two_penguins(gap=0.5)
    game.brace(1)
    game.slide(0, 1, 0, 1.0)
    run_until_hit(game)
    game.penguins[0].x = -4.1
    game.penguins[0].vx = -5.0
    run(game, 1.0)
    assert not game.penguins[0].alive
    assert game.results()["knocked"][1] == 1


def test_brace_lasts_half_a_second_and_blocks_slides_for_1_2():
    game = two_penguins(gap=4)
    assert game.brace(0)
    run(game, 0.4)
    assert game.penguins[0].brace > 0
    run(game, 0.2)
    assert game.penguins[0].brace == 0
    assert game.slide(0, 1, 0, 1.0) is False
    run(game, 0.7)
    assert game.slide(0, 1, 0, 1.0) is True


def test_slides_wait_0_9_seconds():
    game = two_penguins(gap=4)
    assert game.slide(0, 0, 1, 0.1)
    run(game, 0.8)
    assert game.slide(0, 0, 1, 0.1) is False
    run(game, 0.15)
    assert game.slide(0, 0, 1, 0.1) is True


def test_power_is_clamped_and_direction_normalized():
    game = two_penguins(gap=4)
    game.slide(0, 3, 4, 9)
    p = game.penguins[0]
    assert (p.vx, p.vz) == approx((0.6 * 11, 0.8 * 11))
    game.slide(1, 0, 1, 0.0)
    assert speed(game, 1) == approx(0.08 * 11)


def test_junk_slides_are_refused():
    game = two_penguins(gap=4)
    assert game.slide(0, 0, 0, 1) is False
    assert game.slide(0, float("nan"), 1, 1) is False
    assert game.slide(0, 1, 0, float("inf")) is False
    assert game.slide(7, 1, 0, 1) is False
    assert game.slide(0, 1, 0, 1) is True


def test_falling_needs_the_middle_off_solid_ice():
    game = two_penguins(gap=4)
    edge = game.floe.edge_point(0.0)[2]
    game.penguins[0].x, game.penguins[0].z = edge - 0.1, 0.0
    game.step()
    assert game.penguins[0].alive
    game.penguins[0].x = edge + 0.2
    game.step()
    assert not game.penguins[0].alive


def knocked_in(game, seat):
    """Drop a penguin in the sea and return the round's results."""
    game.penguins[seat].x = 9.0
    game.step()
    return game.results()


def test_a_knockout_counts_within_3_seconds():
    for wait, expected in ((2.9, 1), (3.1, 0)):
        game = two_penguins(gap=4)
        game.penguins[1].last_hit = Push(0, game.elapsed, "hit")
        game.elapsed += wait
        assert knocked_in(game, 1)["knocked"][0] == expected


def test_the_fall_event_names_who_gets_the_knockout_and_how():
    for wait, by, how in ((2.9, 0, "hit"), (3.1, -1, "")):
        game = two_penguins(gap=4)
        game.penguins[1].last_hit = Push(0, game.elapsed, "hit")
        game.elapsed += wait
        results = knocked_in(game, 1)
        assert [e for e in game.events if e[0] == "fall"] == [["fall", 1, by, how]]
        assert results["by"] == [-1, by, -1, -1, -1, -1]


def test_a_penguin_nobody_pushed_falls_with_nobody_credited():
    game = two_penguins(gap=4)
    results = knocked_in(game, 1)
    assert ["fall", 1, -1, ""] in game.events
    assert results["knocked"] == [0] * SEATS


def test_a_plain_hit_knockout_counts_as_a_knockout_and_nothing_else():
    game = two_penguins(gap=0.5)
    game.slide(0, 1, 0, 1.0)
    run_until_hit(game)
    results = knocked_in(game, 1)
    assert ["fall", 1, 0, "hit"] in game.events
    assert results["knocked"] == [1, 0, 0, 0, 0, 0]
    assert results["bounce"] == results["seal"] == [0] * SEATS


def test_a_knockout_off_a_brace_is_tallied_as_a_bounce_for_the_bracer():
    game = two_penguins(gap=0.5)
    game.brace(1)
    game.slide(0, 1, 0, 1.0)
    run_until_hit(game)
    results = knocked_in(game, 0)
    assert ["fall", 0, 1, "bounce"] in game.events
    assert results["knocked"] == results["bounce"] == [0, 1, 0, 0, 0, 0]
    assert results["seal"] == [0] * SEATS


def test_the_last_penguin_wins_with_places():
    game = make_round()
    for seat in range(1, SEATS):
        game.penguins[seat].x = 9.0
        game.step()
    assert game.winner == 0 and not game.finished
    run(game, END_PAUSE + 0.1)
    assert game.finished and game.winner == 0
    results = game.results()
    assert results["winner"] == 0 and sorted(results["places"]) == [1, 2, 3, 4, 5, 6]
    assert results["places"][0] == 1


def test_everyone_falling_together_has_no_winner():
    game = make_round()
    for p in game.penguins:
        p.x = 9.0
    game.step()
    assert game.winner is None
    run(game, END_PAUSE + 0.1)
    assert game.finished
    results = game.results()
    assert results["winner"] is None and sorted(results["places"]) == [1, 2, 3, 4, 5, 6]


def started_round():
    return make_round()


def test_frames_are_small_whole_numbers():
    frame = started_round().frame()
    assert all(type(v) is int for row in frame["p"] for v in row) and len(frame["p"]) == 6
    assert "e" not in frame


def test_frame_flags_add_up():
    game = two_penguins(gap=4)
    game.brace(1)
    game.penguins[0].heavy = True
    game.penguins[0].fish = True
    rows = game.frame()["p"]
    assert rows[0][2] == 1 + 4 + 8 and rows[1][2] == 1 + 2 and rows[2][2] == 0


def test_frame_events_are_handed_out_once():
    game = two_penguins(gap=4)
    game.slide(0, 1, 0, 1.0)
    first = game.frame()
    assert ["slide", 0, 0] in first["e"]
    assert "e" not in game.frame()


def test_snapshot_leaves_events_alone():
    game = two_penguins(gap=4)
    game.slide(0, 1, 0, 1.0)
    snap = game.snapshot()
    assert "e" not in snap
    assert set(snap) == {"f", "p", "t", "fish", "crate", "seals", "snow", "map"}
    assert snap["fish"] is None and snap["seals"] == [0] * 6 and len(snap["t"]) == 61
    assert snap["snow"] == [] and snap["t"] == [0] * 61
    assert snap["map"] == {
        "shape": "classic",
        "name": "Classic",
        "hazard": "",
        "hazard_name": "",
        "line": "The whole floe",
    }
    assert ["slide", 0, 0] in game.frame()["e"]


def test_hit_events_carry_hundredths():
    game = two_penguins(gap=0.5)
    game.slide(0, 1, 0, 1.0)
    run_until_hit(game)
    hit = next(e for e in game.frame()["e"] if e[0] == "hit")
    assert len(hit) == 5 and all(type(v) is int for v in hit[1:]) and hit[4] == 1
    assert 20 <= hit[3] <= 100


def test_results_have_exactly_eight_keys():
    results = make_round().results()
    assert set(results) == {"winner", "places", "knocked", "by", "fish", "seal", "bounce", "seconds"}
    assert all(results[name] == [0] * SEATS for name in ("knocked", "fish", "seal", "bounce"))
    assert results["by"] == [-1] * SEATS


def test_set_tuning_works_mid_round_and_reaches_the_floe():
    game = two_penguins(gap=4)
    run(game, 1.0)
    game.set_tuning(Tuning(slide_speed=6.0))
    assert game.floe.tuning.slide_speed == 6.0
    game.slide(0, 1, 0, 1.0)
    assert speed(game, 0) == approx(6.0)
