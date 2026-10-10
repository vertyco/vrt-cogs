from types import SimpleNamespace

import pytest

from tanks.common.leaderboard import Result
from tanks.main import Tanks
from tanks.tests.fakes import FakeConn, FakeRoom


@pytest.mark.asyncio
async def test_activityhub_accepts_the_game():
    games = pytest.importorskip("activityhub.common.games")
    game = await games.validate_game(Tanks(bot=None))
    assert game.key == "tanks" and game.name == "Tanks"
    assert set(game.socket) == {"join", "message", "leave"} and set(game.actions) == {"leaderboard"}
    assert game.icon == "icon.svg" and game.thumbnail == "thumb.png"


@pytest.mark.asyncio
async def test_results_are_saved_and_ranked():
    cog = Tanks(bot=None)
    await cog.save_results([Result(1, "Maya", 3, True), Result(2, "Sam", 5, False)])
    await cog.save_results([Result(2, "Sam", 1, True)])
    board = await cog.leaderboard(SimpleNamespace(author=SimpleNamespace(id=2)), {})
    assert [row["name"] for row in board["top"]] == ["Sam", "Maya"]
    assert board["you"]["kills"] == 6 and board["you"]["matches"] == 2


@pytest.mark.asyncio
async def test_deleting_a_players_data_takes_them_off_the_leaderboard():
    cog = Tanks(bot=None)
    await cog.save_results([Result(1, "Maya", 3, True), Result(2, "Sam", 1, False)])
    await cog.red_delete_data_for_user(requester="user", user_id=1)
    board = await cog.leaderboard(SimpleNamespace(author=SimpleNamespace(id=1)), {})
    assert [row["name"] for row in board["top"]] == ["Sam"] and board["you"] is None


@pytest.mark.asyncio
async def test_a_window_whose_room_was_replaced_keeps_its_match_on_the_new_room():
    # Reloading ActivityHub gives every window a fresh room, while the match and its kept seats live on
    cog = Tanks(bot=None)
    old_room, new_room = FakeRoom("window"), FakeRoom("window")
    match = cog.match_for(FakeConn(old_room, 1))
    try:
        assert cog.match_for(FakeConn(new_room, 1)) is match
        assert match.room is new_room
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_each_window_gets_its_own_match():
    cog = Tanks(bot=None)
    try:
        first = cog.match_for(FakeConn(FakeRoom("a"), 1))
        second = cog.match_for(FakeConn(FakeRoom("b"), 2))
        assert first is not second and set(cog.matches) == {"a", "b"}
    finally:
        await cog.cog_unload()
