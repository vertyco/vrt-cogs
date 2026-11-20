from dataclasses import asdict

import pytest

from penguinwars.common.tuning import SLIDERS, SettingsError, Tuning, clean_tuning, load_tuning


def test_defaults_are_the_mockups_numbers():
    assert asdict(Tuning()) == {
        "slide_speed": 11.0,
        "friction_share": 1.7,
        "friction_fixed": 1.4,
        "slide_wait": 0.9,
        "brace_seconds": 0.5,
        "brace_wait": 1.2,
        "fish_boost": 1.12,
        "seal_reach": 1.7,
        "seal_wait": 2.2,
        "ice_speed": 1.0,
        "wind_push": 1.5,
        "walrus_push": 4.5,
        "snowball_push": 2.6,
    }


def test_every_field_has_a_slider_holding_its_default():
    assert set(SLIDERS) == set(asdict(Tuning()))
    for name, value in asdict(Tuning()).items():
        slider = SLIDERS[name]
        assert {"label", "low", "high", "step"} <= set(slider)
        assert slider["low"] <= value <= slider["high"]


def test_clean_tuning_accepts_the_defaults():
    assert clean_tuning(asdict(Tuning())) == Tuning()


def test_clean_tuning_refuses_a_number_off_its_slider():
    with pytest.raises(SettingsError):
        clean_tuning({**asdict(Tuning()), "slide_speed": 999})


@pytest.mark.parametrize(
    "bad",
    [None, [], {}, {"slide_speed": "fast"}, {"slide_speed": float("nan")}, {**asdict(Tuning()), "slide_speed": True}],
)
def test_clean_tuning_refuses_junk(bad):
    with pytest.raises(SettingsError):
        clean_tuning(bad)


def test_load_tuning_keeps_defaults_for_missing_or_old_fields():
    tuning = load_tuning({"slide_speed": 8, "old_field": 3, "brace_wait": 99, "seal_wait": "x"})
    assert tuning.slide_speed == 8
    assert tuning.brace_wait == Tuning().brace_wait
    assert tuning.seal_wait == Tuning().seal_wait
    assert not hasattr(tuning, "old_field")
