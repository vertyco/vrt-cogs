from types import SimpleNamespace

import pytest

from marblemunch.common.leaderboard import Result
from marblemunch.main import MarbleMunch
from marblemunch.tests.fakes import FakeConn, FakeRoom


@pytest.mark.asyncio
async def test_activityhub_accepts_the_game():
    games = pytest.importorskip("activityhub.common.games")
    game = await games.validate_game(MarbleMunch(bot=None))
    assert game.key == "marblemunch" and game.name == "Marble Munch"
    assert set(game.socket) == {"join", "message", "leave"} and set(game.actions) == {"leaderboard"}
    assert game.icon == "icon.svg" and game.thumbnail == "thumb.png"


@pytest.mark.asyncio
async def test_deleting_a_players_data_takes_them_off_the_leaderboard():
    cog = MarbleMunch(bot=None)
    await cog.save_results([Result(1, "Maya", 3, True), Result(2, "Sam", 1, False)])
    await cog.red_delete_data_for_user(requester="user", user_id=1)
    board = await cog.leaderboard(SimpleNamespace(author=SimpleNamespace(id=1)), {})
    assert [row["name"] for row in board["top"]] == ["Sam"] and board["you"] is None


@pytest.mark.asyncio
async def test_a_window_whose_room_was_replaced_keeps_its_match_on_the_new_room():
    # Reloading ActivityHub gives every window a fresh room, while the match and its kept seats live on
    cog = MarbleMunch(bot=None)
    old_room, new_room = FakeRoom("window"), FakeRoom("window")
    match = cog.match_for(FakeConn(old_room, 1))
    try:
        assert cog.match_for(FakeConn(new_room, 1)) is match
        assert match.room is new_room
    finally:
        await cog.cog_unload()
