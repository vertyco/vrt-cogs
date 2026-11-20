import random
from math import hypot

from pytest import approx

from penguinwars.common.floe import ICE, SINK
from penguinwars.common.round import BRACE_MASS, DT, RADIUS, SEATS, Fish, Round
from penguinwars.common.tuning import Tuning

SEAL_SEAT = 5


def make_round(**rules):
    return Round(Tuning(**rules), random.Random(3))


def collect(game, seconds):
    """Step the round and return [(seconds_in, event)] for every event, clearing them as it goes."""
    found = []
    for _ in range(round(seconds / DT)):
        game.step()
        found += [(game.elapsed, event) for event in game.events]
        game.events.clear()
    return found


def game_fish(x, z):
    return Fish(x, z, 14.0)


def until(game, kind, each_step=None):
    while not any(e[0] == kind for e in game.events):
        if each_step:
            each_step()
        game.step()


def kinds(found, kind):
    return [(t, e) for t, e in found if e[0] == kind]


def seal_game():
    """Six penguins with seat 5 already a swimming seal that may dive right away."""
    game = make_round()
    game.penguins[SEAL_SEAT].alive = False
    seal = game.penguins[SEAL_SEAT].seal
    seal.state, seal.cd = 1, 0.0
    return game


def splash_game(distance):
    """A seal dives at angle 0 and one penguin waits `distance` inside the splash point."""
    game = seal_game()
    assert game.dive(SEAL_SEAT, 0.0, 2.2)
    seal = game.penguins[SEAL_SEAT].seal
    p = game.penguins[0]
    p.x, p.z, p.cd = seal.tx - distance, seal.tz, 0.0
    return game, p


def test_first_fish_comes_6_seconds_in_away_from_the_edge_and_penguins():
    game = make_round()
    assert game.fish is None
    found = collect(game, 5.8)
    assert not kinds(found, "fish")
    found = collect(game, 0.5)
    ((when, event),) = kinds(found, "fish")
    assert when == approx(6.0, abs=2 * DT)
    assert game.fish is not None
    assert [event[1], event[2]] == [round(game.fish.x * 100), round(game.fish.z * 100)]
    top = max(t.ring for t in game.floe.tiles if t.state == ICE)
    assert game.floe.tile_at(game.fish.x, game.fish.z).ring < top
    assert game.fish.life > 13
    for p in game.penguins:
        assert hypot(p.x - game.fish.x, p.z - game.fish.z) > 1.4


def test_a_fish_disappears_after_14_seconds():
    game = make_round()
    game.fish = game_fish(0.0, 0.0)
    found = collect(game, 13.8)
    assert not kinds(found, "fish_gone")
    found = collect(game, 0.4)
    assert [e for _, e in kinds(found, "fish_gone")] == [["fish_gone", "timeout"]]
    assert game.fish is None
    assert 5 <= game.fish_timer <= 8


def test_a_fish_goes_when_its_tile_sinks():
    game = make_round()
    game.fish = game_fish(0.0, 0.0)
    game.floe.tile_at(0.0, 0.0).state = SINK
    found = collect(game, DT * 2)
    assert [e for _, e in kinds(found, "fish_gone")] == [["fish_gone", "sank"]]
    assert game.fish is None
    assert 6 <= game.fish_timer <= 9 + 0.8


def test_the_next_fish_comes_8_to_12_seconds_after_one_is_eaten():
    game = make_round()
    p = game.penguins[0]
    game.fish = game_fish(p.x, p.z)
    found = collect(game, 13)
    ((eaten, _),) = kinds(found, "gulp")
    ((next_fish, _),) = kinds(found, "fish")
    assert 8 - DT <= next_fish - eaten <= 12 + DT


def test_touching_a_fish_takes_it():
    game = make_round()
    p = game.penguins[0]
    game.fish = game_fish(p.x + RADIUS + 0.31, p.z)
    collect(game, DT)
    assert game.fish is not None
    assert not game.rows()[0][2] & 4
    game.fish.x = p.x + RADIUS + 0.29
    found = collect(game, DT)
    assert [e for _, e in found] == [["gulp", 0]]
    assert game.fish is None
    assert game.rows()[0][2] & 4
    assert 8 <= game.fish_timer <= 12


def test_fish_eaten_are_counted_per_seat():
    game = make_round()
    for seat in (0, 3, 0):
        p = game.penguins[seat]
        p.fish = False
        game.fish = game_fish(p.x, p.z)
        collect(game, DT)
    assert game.results()["fish"] == [2, 0, 0, 1, 0, 0]


def test_a_fish_slide_is_12_percent_stronger_and_twice_as_heavy():
    game = make_round()
    p = game.penguins[0]
    p.cd, p.fish = 0.0, True
    assert game.slide(0, 0.0, 1.0, 1.0)
    assert (p.vx, p.vz) == approx((0.0, 11.0 * 1.12))
    flags = game.rows()[0][2]
    assert flags & 8 and not flags & 4
    assert game.events[-1] == ["slide", 0, 1]


def test_heavy_stops_being_heavy_when_slow():
    game = make_round()
    p = game.penguins[0]
    p.heavy, p.vz = True, 0.5
    game.step()
    assert not p.heavy
    assert not game.rows()[0][2] & 8
    p.heavy, p.vz = True, 6.0
    game.step()
    assert p.heavy


def barrel(brace):
    game = make_round()
    for seat in range(2, SEATS):
        game.penguins[seat].x, game.penguins[seat].z = 40 + seat * 3, 0.0
    a, b = game.penguins[0], game.penguins[1]
    a.x, a.z, a.vx, a.vz, a.heavy = -0.6, 0.0, 8.0, 0.0, True
    b.x, b.z, b.vx, b.vz = 0.6, 0.0, 0.0, 0.0
    b.brace = brace
    for _ in range(4):
        game.step()
    return a, b


def test_a_heavy_slide_barrels_through_and_only_a_brace_stops_it():
    a, b = barrel(0.0)
    assert a.vx > 1 and b.vx > a.vx
    a, b = barrel(0.5)
    assert b.mass == BRACE_MASS
    assert a.vx < 0


def fallen_game():
    game = make_round()
    game.penguins[SEAL_SEAT].x = 50.0
    return game


def test_a_fallen_penguin_surfaces_as_a_seal_after_1_4_seconds():
    game = fallen_game()
    found = collect(game, 1.0)
    ((fell, _),) = kinds(found, "fall")
    assert game.penguins[SEAL_SEAT].seal.state == 0
    until(game, "seal")
    assert game.events == [["seal", SEAL_SEAT]]
    assert game.elapsed - fell == approx(1.4, abs=DT)
    seal = game.penguins[SEAL_SEAT].seal
    assert seal.state == 1
    assert seal.cd == approx(0.8)
    assert game.snapshot()["seals"] == [0, 0, 0, 0, 0, 1]


def test_a_cpu_seal_waits_3_to_5_seconds_before_its_first_dive():
    game = fallen_game()
    game.cpus = {SEAL_SEAT}
    collect(game, 1.0)
    until(game, "seal")
    assert 3 <= game.penguins[SEAL_SEAT].seal.cd <= 5


def test_a_dive_warns_for_0_6_then_leaps_for_0_42_then_splashes():
    game = seal_game()
    assert game.dive(SEAL_SEAT, 0.0, 2.2)
    seal = game.penguins[SEAL_SEAT].seal
    assert seal.state == 2
    assert game.events == [["dive", SEAL_SEAT, round(seal.tx * 100), round(seal.tz * 100)]]
    game.events.clear()
    collect(game, 0.5)
    assert seal.state == 2
    collect(game, 0.2)
    assert seal.state == 3
    assert game.snapshot()["seals"][SEAL_SEAT] == 3
    found = collect(game, 0.5)
    ((when, event),) = kinds(found, "splash")
    assert when == approx(1.02, abs=2 * DT)
    assert event == ["splash", SEAL_SEAT, round(seal.tx * 100), round(seal.tz * 100)]
    assert seal.state == 1


def test_a_splash_pulls_penguins_in_reach_toward_the_water():
    game, p = splash_game(1.0)
    until(game, "splash")
    assert (p.vx, p.vz) == approx((2.6 + 3.6 * (1 - 1.0 / 1.7), 0.0))


def test_a_braced_penguin_ignores_a_splash():
    game, p = splash_game(1.0)

    def hold():
        p.brace = 5.0

    until(game, "splash", hold)
    assert (p.vx, p.vz) == (0.0, 0.0)


def test_a_penguin_out_of_reach_is_left_alone():
    game, p = splash_game(1.8)
    until(game, "splash")
    assert (p.vx, p.vz) == (0.0, 0.0)


def test_a_splash_knockout_counts_for_the_seal():
    game, p = splash_game(0.5)
    found = collect(game, 4.0)
    assert ["fall", 0, SEAL_SEAT, "seal"] in [e for _, e in found]
    assert game.knocked[SEAL_SEAT] == 1


def test_a_splash_knockout_is_tallied_as_the_seals_and_not_as_a_bounce():
    game, _ = splash_game(0.5)
    collect(game, 4.0)
    results = game.results()
    assert results["seal"] == [0, 0, 0, 0, 0, 1]
    assert results["bounce"] == [0] * SEATS


def test_a_seal_waits_after_splashing():
    game = seal_game()
    assert game.dive(SEAL_SEAT, 0.0, 2.2)
    collect(game, 1.2)
    assert game.penguins[SEAL_SEAT].seal.state == 1
    assert not game.dive(SEAL_SEAT, 0.0, 2.2)
    collect(game, 1.8)
    assert not game.dive(SEAL_SEAT, 0.0, 2.2)
    collect(game, 0.6)
    assert game.dive(SEAL_SEAT, 0.0, 2.2)


def test_a_dive_is_refused_for_the_living_and_the_mid_dive():
    game = seal_game()
    assert not game.dive(0, 0.0, 2.2)
    assert game.dive(SEAL_SEAT, 0.0, 2.2)
    assert not game.dive(SEAL_SEAT, 1.0, 2.2)


def test_a_dive_refuses_junk():
    game = seal_game()
    for seat, angle, wait in [
        (True, 0.0, 2.2),
        ("5", 0.0, 2.2),
        (None, 0.0, 2.2),
        (9, 0.0, 2.2),
        (-1, 0.0, 2.2),
        (SEAL_SEAT, float("nan"), 2.2),
        (SEAL_SEAT, float("inf"), 2.2),
        (SEAL_SEAT, True, 2.2),
        (SEAL_SEAT, "0", 2.2),
        (SEAL_SEAT, 0.0, float("nan")),
        (SEAL_SEAT, 0.0, True),
        (SEAL_SEAT, 0.0, "2"),
    ]:
        assert not game.dive(seat, angle, wait)
    assert game.penguins[SEAL_SEAT].seal.state == 1
    assert not game.events


def test_a_seal_that_is_not_surfaced_or_still_cooling_cannot_dive():
    game = seal_game()
    game.penguins[SEAL_SEAT].seal.cd = 0.5
    assert not game.dive(SEAL_SEAT, 0.0, 2.2)
    game = make_round()
    game.penguins[SEAL_SEAT].alive = False
    assert not game.dive(SEAL_SEAT, 0.0, 2.2)
