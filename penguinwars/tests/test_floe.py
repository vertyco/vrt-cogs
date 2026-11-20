from collections import Counter
from math import sqrt
import random

from pytest import approx

from penguinwars.common.floe import CRACK, GONE, ICE, SINK, Floe
from penguinwars.common.tuning import Tuning


def make_floe(**rules):
    return Floe(Tuning(**rules), random.Random(7))


def run_floe(seconds, dt=0.05, floe=None, start=0.0, **rules):
    floe = floe or make_floe(**rules)
    events = []
    steps = round(seconds / dt)
    for i in range(steps):
        floe.step(dt, start + (i + 1) * dt, events)
    return floe, events


def test_ice_has_61_tiles_in_five_rings():
    assert Counter(tile.ring for tile in make_floe().tiles) == {0: 1, 1: 6, 2: 12, 3: 18, 4: 24}


def test_tile_centers_are_pointy_top_hexes():
    tile = next(t for t in make_floe().tiles if (t.q, t.r) == (1, 2))
    assert tile.x == approx(0.62 * sqrt(3) * 2) and tile.z == approx(0.62 * 1.5 * 2)


def test_tiles_loop_q_then_r():
    tiles = make_floe().tiles
    assert (tiles[0].q, tiles[0].r) == (-4, 0)
    assert (tiles[1].q, tiles[1].r) == (-4, 1)


def test_cracked_ice_holds_and_sinking_ice_does_not():
    floe = make_floe()
    tile = floe.tiles[0]
    assert floe.solid(tile.x, tile.z)
    tile.state = CRACK
    assert floe.solid(tile.x, tile.z)
    tile.state = SINK
    assert not floe.solid(tile.x, tile.z)
    tile.state = GONE
    assert not floe.solid(tile.x, tile.z)


def test_open_water_is_not_solid():
    assert not make_floe().solid(50, 50)


def test_first_crack_comes_3_seconds_in_on_the_outer_ring():
    floe, events = run_floe(2.9)
    assert not events
    floe, events = run_floe(3.1)
    assert events[0][0] == "crack" and floe.tiles[events[0][1]].ring == 4


def test_a_crack_sinks_after_1_3_seconds_and_is_gone_1_0_later():
    floe, events = run_floe(3.1)  # the first crack lands at 3.0
    index = events[0][1]
    assert floe.tiles[index].state == CRACK
    floe, events = run_floe(1.1, floe=floe, start=3.1)  # now 4.2
    assert ["sink", index] not in events
    floe, events = run_floe(0.2, floe=floe, start=4.2)  # now 4.4
    assert ["sink", index] in events and floe.tiles[index].state == SINK
    floe, events = run_floe(0.8, floe=floe, start=4.4)  # now 5.2
    assert ["gone", index] not in events
    floe, events = run_floe(0.2, floe=floe, start=5.2)  # now 5.4
    assert ["gone", index] in events and floe.tiles[index].state == GONE


def test_gap_shrinks_from_1_45_to_0_6():
    floe = make_floe()
    assert floe.gap(0) == approx(1.45)
    assert floe.gap(50) == approx(0.85)
    assert floe.gap(500) == 0.6


def test_ice_speed_divides_the_gap():
    assert make_floe(ice_speed=0.5).gap(0) == approx(2.9)


def test_inner_rings_wait_for_the_outer_ring():
    floe = make_floe()
    cracked = []
    for i in range(1200):
        events = []
        before = [t.state for t in floe.tiles]
        floe.step(0.05, (i + 1) * 0.05, events)
        for kind, index in (e for e in events if e[0] == "crack"):
            ring = floe.tiles[index].ring
            assert all(before[j] != ICE for j, t in enumerate(floe.tiles) if t.ring > ring)
            cracked.append(ring)
    assert cracked[:24] == [4] * 24 and 3 in cracked


def test_everything_eventually_sinks():
    floe, _ = run_floe(120)
    assert all(t.state == GONE for t in floe.tiles)


def test_edge_point_is_just_past_the_outermost_ice():
    floe = make_floe()
    x, z, r = floe.edge_point(0)
    assert 4.6 < r < 5.0
    assert x == approx(r + 0.35) and z == approx(0.0)
    floe.by_axial[(0, 0)].state = floe.by_axial[(1, 0)].state = GONE
    assert floe.edge_point(0) == (x, z, r)
    for tile in floe.tiles:
        if tile.ring >= 3 and abs(tile.z) < 0.5:
            tile.state = GONE
    assert floe.edge_point(0)[2] < r
