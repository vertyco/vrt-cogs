import re
import typing as t

THEMES = ("standard", "orb")
LAYOUTS = ("grid", "list", "compact")
BACKGROUNDS = ("dark", "darker", "gradient")
# The orb theme brings its own colors, background and layout, and menu sounds only play in it
BUILTIN_LOOK = {
    "theme": "orb",
    "layout": "grid",
    "accent": "#5865F2",
    "background": "dark",
    "details": True,
    "sounds": True,
    # The frame rate counter in the corner, over the menu and every game
    "fps": True,
}
COLOR = re.compile(r"#[0-9A-Fa-f]{6}")


class SettingsError(ValueError):
    """A settings change the hub refuses, worded for the player"""


def value_ok(field: str, value: t.Any) -> bool:
    if field == "theme":
        return isinstance(value, str) and value in THEMES
    if field == "layout":
        return isinstance(value, str) and value in LAYOUTS
    if field == "background":
        return isinstance(value, str) and value in BACKGROUNDS
    if field == "accent":
        return isinstance(value, str) and COLOR.fullmatch(value) is not None
    if field in ("details", "sounds", "fps"):
        return isinstance(value, bool)
    return False


def apply_look_change(saved: dict, change: t.Any) -> dict:
    """A level's stored look after a change: set fields replace, null clears a field so it falls back"""
    if not isinstance(change, dict):
        raise SettingsError("A look must be an object.")
    unknown = sorted(str(name) for name in change if name not in BUILTIN_LOOK)
    if unknown:
        raise SettingsError(f"Unknown look fields: {', '.join(unknown)}")
    look = {name: value for name, value in saved.items() if name in BUILTIN_LOOK}
    for name, value in change.items():
        if value is None:
            look.pop(name, None)
        elif value_ok(name, value):
            look[name] = value
        else:
            raise SettingsError(f"{name} can't be {value!r}.")
    return look


def effective_look(*levels: dict) -> dict:
    """The built-in look overlaid with each level in turn, most general first"""
    look = dict(BUILTIN_LOOK)
    for level in levels:
        look.update({name: value for name, value in level.items() if value_ok(name, value)})
    return look
