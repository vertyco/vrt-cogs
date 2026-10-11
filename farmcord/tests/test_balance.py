"""The game's pace, checked by playing simulate.py's players through the real rules with a fixed seed: level 90 in
about two weeks of nonstop play or three to four of casual play, a level-up in a new player's first session, and every
plot affordable within a day of its level. Both runs together take a second or two"""

import time

import pytest

from farmcord.catalog import PLOTS
from farmcord.game.calendar import DAY, HOUR
from farmcord.tests.simulate import GOAL, SPRING, Casual, Nonstop, day_of, play, plot_waits


@pytest.fixture(scope="module")
def runs():
    began = time.perf_counter()
    played = {"nonstop": play(Nonstop(), SPRING), "casual": play(Casual(), SPRING)}
    return played, time.perf_counter() - began


def test_the_simulation_runs_in_under_a_minute(runs):
    assert runs[1] < 60


def test_nonstop_play_reaches_level_90_in_12_to_16_days(runs):
    days = day_of(runs[0]["nonstop"], GOAL)
    assert days is not None and 12 <= days <= 16


def test_casual_play_reaches_level_90_in_21_to_28_days(runs):
    days = day_of(runs[0]["casual"], GOAL)
    assert days is not None and 21 <= days <= 28


def test_the_first_level_up_comes_inside_the_first_session(runs):
    """A new player who keeps playing levels up within 2 hours. Casual visits are moments, so only the nonstop
    player has a first session to measure"""
    nonstop = runs[0]["nonstop"]
    assert nonstop.reached[2] - nonstop.start < 2 * HOUR


@pytest.mark.parametrize("player", ["nonstop", "casual"])
def test_every_plot_is_bought_within_a_day_of_its_level(runs, player):
    waits = plot_waits(runs[0][player])
    assert set(waits) == set(PLOTS) - {1}
    late = {plot: wait for plot, wait in waits.items() if wait is None or wait * HOUR > DAY}
    assert late == {}
