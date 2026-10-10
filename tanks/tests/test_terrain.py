import math
import random

import pytest

from tanks.common.terrain import LANDSCAPES, WIDTH, Field, generate, js_round


@pytest.mark.parametrize("landscape", LANDSCAPES)
def test_every_landscape_fills_the_field_with_ground(landscape):
    for seed in range(40):
        field = generate(landscape, random.Random(seed))
        assert len(field.tops) == WIDTH
        assert all(math.isfinite(top) for top in field.tops)
        # The original's generators: the first can rise above the field or sink below it, the others stay low
        assert all(-30 <= top <= 525 for top in field.tops)
        assert all(0 <= x < WIDTH for x, _ in field.trees)


def test_each_landscape_starts_with_its_own_wind():
    for seed in range(60):
        rng = random.Random(seed)
        assert 30 <= abs(generate(1, rng).wind) <= 79
        assert 25 <= abs(generate(2, rng).wind) <= 49
        assert abs(generate(3, rng).wind) <= 19


def test_the_second_landscape_is_a_low_band_and_the_third_almost_flat():
    for seed in range(20):
        assert all(286 - 70 <= top <= 286 + 70 for top in generate(2, random.Random(seed)).tops)
        assert all(365 - 21 <= top <= 365 + 21 for top in generate(3, random.Random(seed)).tops)


def test_trees_grow_on_the_first_two_landscapes_only():
    rng = random.Random(4)
    assert 2 <= len(generate(1, rng).trees) <= 6
    assert len(generate(2, rng).trees) > 10
    assert generate(3, rng).trees == []


def test_wind_wanders_by_at_most_half_the_landscapes_change_each_turn():
    field = Field(1, [300.0] * WIDTH, 0.0)
    rng = random.Random(1)
    for _ in range(200):
        before = field.wind
        field.change_wind(rng)
        assert -7 <= field.wind - before <= 8


def test_outside_the_field_there_is_no_ground():
    field = Field(3, [300.0] * WIDTH, 0.0)
    assert math.isnan(field.top(-1)) and math.isnan(field.top(WIDTH))
    assert not field.top(-1) < 1000 and not field.top(WIDTH) >= 0


def test_rounding_matches_flash():
    assert [js_round(v) for v in (0.5, 1.5, 2.5, -0.5, -1.5, 2.4)] == [1, 2, 3, 0, -1, 2]
