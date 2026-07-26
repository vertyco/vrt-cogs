from paltools.commands.admin import SETTING_HIGHLIGHTS, Admin

fmt = Admin.format_setting


def test_bools_render_as_words_not_numbers():
    # bool is a subclass of int, so an int-first branch would render these as 1 and 0
    assert fmt(True) == "Yes"
    assert fmt(False) == "No"


def test_whole_floats_lose_the_decimal():
    assert fmt(1.0) == "1"
    assert fmt(0.5) == "0.5"


def test_strings_and_ints_pass_through():
    assert fmt("PlayerDropItem") == "PlayerDropItem"
    assert fmt(128) == "128"


def test_empty_value_gets_a_placeholder():
    # An embed field value cannot be an empty string
    assert fmt("") == "-"


def test_highlight_keys_are_unique():
    keys = [key for key, _label in SETTING_HIGHLIGHTS]
    assert len(keys) == len(set(keys))
