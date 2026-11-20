from dataclasses import asdict, dataclass, fields, replace
from math import isfinite
from typing import Any


class SettingsError(ValueError):
    pass


@dataclass
class Tuning:
    slide_speed: float = 11.0
    friction_share: float = 1.7
    friction_fixed: float = 1.4
    slide_wait: float = 0.9
    brace_seconds: float = 0.5
    brace_wait: float = 1.2
    fish_boost: float = 1.12
    seal_reach: float = 1.7
    seal_wait: float = 2.2
    ice_speed: float = 1.0
    # How far one gust of wind slides a penguin that stands still
    wind_push: float = 1.5
    # The speed a walrus slam gives a penguin right beside it
    walrus_push: float = 4.5
    # The speed a snowball gives a penguin it lands right on
    snowball_push: float = 2.6


SLIDERS: dict[str, dict] = {
    "slide_speed": {"label": "Slide speed", "low": 6, "high": 16, "step": 0.5},
    "friction_share": {"label": "Friction (share of speed)", "low": 0.8, "high": 3, "step": 0.1},
    "friction_fixed": {"label": "Friction (fixed)", "low": 0.4, "high": 3, "step": 0.1},
    "slide_wait": {"label": "Seconds between slides", "low": 0.3, "high": 2, "step": 0.1},
    "brace_seconds": {"label": "Brace length", "low": 0.2, "high": 1, "step": 0.05},
    "brace_wait": {"label": "Seconds between braces", "low": 0.5, "high": 3, "step": 0.1},
    "fish_boost": {"label": "Fish power boost", "low": 1, "high": 1.5, "step": 0.01},
    "seal_reach": {"label": "Seal reach", "low": 1, "high": 3, "step": 0.1},
    "seal_wait": {"label": "Seconds between seals", "low": 1, "high": 5, "step": 0.1},
    "ice_speed": {"label": "Ice pace (only the gap between cracks)", "low": 0.4, "high": 1.5, "step": 0.05},
    "wind_push": {"label": "Wind push (how far a gust moves a penguin)", "low": 0.5, "high": 3, "step": 0.1},
    "walrus_push": {"label": "Walrus slam strength", "low": 2, "high": 9, "step": 0.5},
    "snowball_push": {"label": "Snowball nudge strength", "low": 1, "high": 5, "step": 0.1},
}


def in_range(name: str, value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        if not isfinite(value):
            return False
    except OverflowError:
        return False
    return SLIDERS[name]["low"] <= value <= SLIDERS[name]["high"]


def clean_tuning(value: Any) -> Tuning:
    if not isinstance(value, dict):
        raise SettingsError("Settings must be an object")
    names = {f.name for f in fields(Tuning)}
    if set(value) != names:
        raise SettingsError("Settings must have exactly the known fields")
    for name in names:
        if not in_range(name, value[name]):
            raise SettingsError(f"{name} is outside its range")
    return Tuning(**{name: float(value[name]) for name in names})


def load_tuning(saved: dict) -> Tuning:
    values = asdict(Tuning())
    for name in values:
        if name in saved and in_range(name, saved[name]):
            values[name] = float(saved[name])
    return Tuning(**values)


# Party rounds: one round where a rule is different for everybody. `rules` multiplies tuning numbers for that round,
# and `fish` multiplies the wait for each fish. `line` tells players what is different
TWISTS: dict[str, dict] = {
    "frenzy": {"name": "Fish frenzy", "line": "A new fish every couple of seconds", "fish": 0.2},
    "slippery": {
        "name": "Slippery ice",
        "line": "Everyone slides much further",
        "rules": {"friction_share": 0.5, "friction_fixed": 0.5},
    },
    "turbo": {"name": "Turbo", "line": "Half the wait between slides", "rules": {"slide_wait": 0.5, "seal_wait": 0.5}},
    "melt": {"name": "Fast melt", "line": "The ice breaks up twice as fast", "rules": {"ice_speed": 2.0}},
}


def twist_tuning(tuning: Tuning, kind: str | None) -> Tuning:
    """The numbers a party round of this kind is played with. They may leave the sliders' ranges"""
    rules = TWISTS[kind].get("rules", {}) if kind is not None else {}
    if not rules:
        return tuning
    return replace(tuning, **{name: getattr(tuning, name) * by for name, by in rules.items()})


def fish_pace(kind: str | None) -> float:
    return TWISTS[kind].get("fish", 1.0) if kind is not None else 1.0
