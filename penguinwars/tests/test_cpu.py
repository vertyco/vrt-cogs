import random
from math import atan2, hypot
from statistics import median

from penguinwars.common.cpu import NAMES, Cpu
from penguinwars.common.round import DT, KO_SECONDS, SEATS, SWIM, Round
from penguinwars.common.tuning import Tuning

SLIDE_MEMORY = 1.5


def new_game(seed=1, ice_speed=1.0, cpus=range(SEATS)):
    game = Round(Tuning(ice_speed=ice_speed), random.Random(seed))
    game.cpus = set(cpus)
    return game, {seat: Cpu(seat, random.Random(seed * 100 + seat)) for seat in cpus}


def play(seed, ice_speed=1.0, on_step=None):
    game, cpus = new_game(seed, ice_speed)
    while not game.finished and game.elapsed < 200:
        for cpu in cpus.values():
            cpu.act(game, [])
        game.step()
        if on_step:
            on_step(game)
        game.events.clear()
    return game


def lengths(ice_speed):
    return [play(seed, ice_speed).elapsed for seed in range(30)]


def test_names():
    assert NAMES == ["Pebble", "Sleet", "Biscuit", "Captain Slick", "Gus", "Flurry"]


def test_cpus_never_crash_and_rounds_always_end():
    for seed in range(30):
        assert play(seed).finished


def test_cpu_rounds_last_a_real_round():
    seconds = lengths(1.0)
    assert 30 <= median(seconds) <= 70 and max(seconds) < 75


def test_slower_ice_makes_longer_rounds():
    assert median(lengths(0.6)) > median(lengths(1.0))


def test_a_round_replays_from_its_seed():
    assert play(4).results() == play(4).results()


def test_cpus_rarely_slide_themselves_off():
    falls = own = 0
    last_slide = {}

    def watch(game):
        nonlocal falls, own
        for event in game.events:
            if event[0] == "slide":
                last_slide[event[1]] = game.elapsed
            elif event[0] == "fall":
                seat = event[1]
                hit = game.penguins[seat].last_hit
                falls += 1
                credited = hit is not None and game.elapsed - hit[1] < KO_SECONDS
                if not credited and game.elapsed - last_slide.get(seat, -99) <= SLIDE_MEMORY:
                    own += 1

    for seed in range(30):
        last_slide.clear()
        play(seed, on_step=watch)
    assert falls > 100
    assert own / falls < 0.2


def test_cpus_sometimes_brace_when_a_hit_is_coming():
    braced = 0
    for seed in range(100):
        game, cpus = new_game(seed, cpus=[0])
        game.penguins[0].x = game.penguins[0].z = 0.0
        game.penguins[0].cd = 0.0
        game.penguins[1].x, game.penguins[1].z = 1.5, 0.0
        game.penguins[1].vx = -8.0
        cpus[0].act(game, [])
        braced += game.penguins[0].brace > 0
    assert 15 < braced < 70


def test_cpus_stay_calm_when_nothing_is_coming():
    for seed in range(40):
        game, cpus = new_game(seed, cpus=[0])
        game.penguins[0].cd = 0.0
        cpus[0].act(game, [])
        assert game.penguins[0].brace == 0


def seal_setup(seed):
    game, cpus = new_game(seed, cpus=[5])
    for seat in range(5):
        game.penguins[seat].x, game.penguins[seat].z = seat * 0.3 - 0.6, 0.0
    game.penguins[0].x = game.floe.edge_point(0.0)[2] - 0.5
    game.penguins[5].alive = False
    game.penguins[5].seal.state = SWIM
    game.penguins[5].seal.cd = 0.0
    return game, cpus[5]


def test_a_fallen_cpu_splashes_penguins_near_the_edge():
    for seed in range(10):
        game, cpu = seal_setup(seed)
        cpu.act(game, [])
        dives = [e for e in game.events if e[0] == "dive"]
        assert len(dives) == 1
        _, seat, x, z = dives[0]
        assert seat == 5 and x > 300 and abs(z) < 150
        assert 4 <= game.penguins[5].seal.wait <= 7


def test_a_fallen_cpu_waits_when_nobody_is_near_the_edge():
    game, cpu = seal_setup(1)
    game.penguins[0].x = 0.5
    for _ in range(int(3 / DT)):
        cpu.act(game, [])
    assert not [e for e in game.events if e[0] == "dive"]


def pick_direction(humans, seed):
    game, cpus = new_game(seed, cpus=[0])
    for seat in (2, 4, 5):
        game.penguins[seat].alive = False
    game.penguins[0].x = game.penguins[0].z = 0.0
    game.penguins[0].cd = 0.0
    game.penguins[1].x, game.penguins[1].z = 1.2, 0.0
    game.penguins[3].x, game.penguins[3].z = -2.0, 0.0
    cpus[0].think = 0.0
    cpus[0].act(game, humans)
    p = game.penguins[0]
    assert hypot(p.vx, p.vz) > 0
    return atan2(p.vz, p.vx)


def test_cpus_sometimes_go_for_a_human():
    toward_human = sum(abs(pick_direction([3], seed)) > 2 for seed in range(200))
    assert 20 < toward_human < 90
    assert sum(abs(pick_direction([], seed)) > 2 for seed in range(200)) == 0


def test_the_first_think_waits_two_and_a_half_seconds():
    game, cpus = new_game(2, cpus=[0])
    game.penguins[0].cd = 0.0
    for _ in range(int(2.4 / DT)):
        cpus[0].act(game, [])
    assert not [e for e in game.events if e[0] == "slide"]
