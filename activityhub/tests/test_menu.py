from pathlib import Path
from types import SimpleNamespace

import pytest

from activityhub.common.games import Game
from activityhub.common.looks import SettingsError
from activityhub.common.menu import (
    allowed_tabs,
    clean_order,
    merge_order,
    game_json,
    merge_disabled,
    ordered_games,
    player_json,
)


def game(key, name, icon=None, thumbnail=None):
    return Game(
        key=key, name=name, web_dir=Path("."), cog=None, description=f"{name} desc", icon=icon, thumbnail=thumbnail
    )


GAMES = [game("zeta", "Zeta"), game("alpha", "alpha"), game("mid", "Middle")]


def keys(games):
    return [g.key for g in games]


def test_no_saved_order_is_alphabetical_by_name():
    assert keys(ordered_games(GAMES, [])) == ["alpha", "mid", "zeta"]


def test_saved_order_comes_first_then_the_rest_alphabetically():
    assert keys(ordered_games(GAMES, ["zeta"])) == ["zeta", "alpha", "mid"]


def test_unknown_and_repeated_keys_in_an_order_are_ignored():
    assert keys(ordered_games(GAMES, ["gone", "mid", "mid", "zeta"])) == ["mid", "zeta", "alpha"]


def test_clean_order_keeps_installed_keys_once():
    assert clean_order(["mid", "gone", "mid", "zeta"], {"mid", "zeta", "alpha"}) == ["mid", "zeta"]


@pytest.mark.parametrize("value", [None, "mid", ["mid", 3], {"mid": 1}])
def test_clean_order_refuses_bad_input(value):
    with pytest.raises(SettingsError):
        clean_order(value, {"mid"})


def test_merge_disabled_keeps_uninstalled_games_off():
    saved = ["gone", "alpha"]
    assert merge_disabled(saved, ["mid"], {"alpha", "mid", "zeta"}) == ["gone", "mid"]


def test_merge_disabled_ignores_unknown_sent_keys():
    assert merge_disabled([], ["mid", "nope", "mid"], {"mid"}) == ["mid"]


def test_merge_disabled_refuses_bad_input():
    with pytest.raises(SettingsError):
        merge_disabled([], "mid", {"mid"})


def test_tabs_for_each_kind_of_player():
    assert allowed_tabs(in_guild=True, can_manage=False, is_owner=False) == ["look", "order"]
    assert allowed_tabs(in_guild=True, can_manage=True, is_owner=False) == ["look", "order", "server"]
    assert allowed_tabs(in_guild=True, can_manage=False, is_owner=True) == ["look", "order", "server", "defaults"]
    assert allowed_tabs(in_guild=False, can_manage=False, is_owner=True) == ["look", "order", "defaults"]
    assert allowed_tabs(in_guild=False, can_manage=True, is_owner=False) == ["look", "order"]


def test_game_json():
    assert game_json(game("mid", "Middle", icon="art/icon one.png", thumbnail="art/wide.png"), "abc123") == {
        "key": "mid",
        "name": "Middle",
        "description": "Middle desc",
        "icon": "/games/mid/abc123/art/icon%20one.png",
        "thumbnail": "/games/mid/abc123/art/wide.png",
    }
    plain = game_json(game("mid", "Middle"), "abc123")
    assert plain["icon"] is None and plain["thumbnail"] is None


def test_player_json_in_a_server_and_in_a_dm():
    user = SimpleNamespace(
        id=7, name="vert", display_name="Vert", display_avatar=SimpleNamespace(url="https://cdn/a.png")
    )
    guild = SimpleNamespace(id=9, name="Vertyco", icon=SimpleNamespace(url="https://cdn/g.png"))
    assert player_json(SimpleNamespace(author=user, guild=guild)) == {
        "id": "7",
        "username": "vert",
        "displayName": "Vert",
        "avatar": "https://cdn/a.png",
        "guildId": "9",
        "guildName": "Vertyco",
        "guildIcon": "https://cdn/g.png",
    }
    dm = player_json(SimpleNamespace(author=user, guild=None))
    assert dm["guildId"] is None and dm["guildName"] is None and dm["guildIcon"] is None


def test_merge_order_appends_saved_installed_keys_that_were_not_sent():
    installed = {"a", "b", "c", "d"}
    assert merge_order(["c", "gone", "a", "b"], ["d", "b"], installed) == ["d", "b", "c", "a"]
    assert merge_order([], ["b", "b", "gone"], installed) == ["b"]
    with pytest.raises(SettingsError):
        merge_order(["a"], "nope", installed)


def test_merge_order_with_none_resets_to_alphabetical():
    assert merge_order(["c", "a", "b"], None, {"a", "b", "c"}) == []


def test_merge_order_with_an_empty_list_keeps_the_saved_order():
    # What the menu sends from a server with every game off: the order still applies in other servers
    assert merge_order(["c", "a", "b"], [], {"a", "b", "c"}) == ["c", "a", "b"]
