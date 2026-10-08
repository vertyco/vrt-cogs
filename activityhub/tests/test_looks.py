import pytest

from activityhub.common.looks import BUILTIN_LOOK, SettingsError, apply_look_change, effective_look


def test_valid_changes_are_saved():
    change = {
        "theme": "orb",
        "layout": "list",
        "accent": "#abcdef",
        "background": "gradient",
        "details": False,
        "sounds": False,
    }
    assert apply_look_change({}, change) == change


def test_null_clears_a_field_and_untouched_fields_stay():
    assert apply_look_change({"layout": "list", "details": False}, {"layout": None}) == {"details": False}


@pytest.mark.parametrize(
    "change",
    [
        {"layout": "tiles"},
        {"layout": 1},
        {"background": "light"},
        {"accent": "#12345"},
        {"accent": "red"},
        {"accent": "#GGGGGG"},
        {"details": "yes"},
        {"details": 1},
        {"theme": "xbox"},
        {"theme": True},
        {"sounds": "on"},
        {"sounds": 1},
    ],
)
def test_bad_values_are_refused(change):
    with pytest.raises(SettingsError):
        apply_look_change({}, change)


def test_unknown_fields_are_refused():
    with pytest.raises(SettingsError, match="Unknown look fields: font"):
        apply_look_change({}, {"font": "Comic Sans"})


def test_a_look_must_be_an_object():
    for change in (None, [], "grid"):
        with pytest.raises(SettingsError):
            apply_look_change({}, change)


def test_a_refused_change_leaves_the_saved_look_alone():
    saved = {"layout": "list"}
    with pytest.raises(SettingsError):
        apply_look_change(saved, {"layout": "grid", "accent": "nope"})
    assert saved == {"layout": "list"}


def test_effective_look_falls_back_to_builtin():
    assert effective_look() == BUILTIN_LOOK
    assert effective_look({}, {}, {}) == BUILTIN_LOOK


def test_most_specific_level_wins():
    look = effective_look({"layout": "list", "accent": "#111111"}, {"layout": "compact"}, {"accent": "#222222"})
    assert look == {**BUILTIN_LOOK, "layout": "compact", "accent": "#222222"}


def test_effective_look_ignores_bad_stored_values():
    assert effective_look({"layout": "tiles", "font": "x"}) == BUILTIN_LOOK
