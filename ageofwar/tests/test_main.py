from types import SimpleNamespace

import pytest

from ageofwar.common.leaderboard import Result
from ageofwar.main import AgeOfWar
from ageofwar.tests.fakes import FakeConn, FakeRoom


def asker(user_id: int) -> SimpleNamespace:
    return SimpleNamespace(author=SimpleNamespace(id=user_id))


@pytest.mark.asyncio
async def test_activityhub_accepts_the_game():
    games = pytest.importorskip("activityhub.common.games")
    game = await games.validate_game(AgeOfWar(bot=None))
    assert game.key == "ageofwar" and game.name == "Age of War"
    assert set(game.socket) == {"join", "message", "leave"} and set(game.actions) == {"leaderboard"}
    assert game.icon == "icon.png" and game.thumbnail == "thumb.png"


@pytest.mark.asyncio
async def test_wins_are_saved_and_ranked():
    cog = AgeOfWar(bot=None)
    await cog.save_results([Result(1, "Maya", "normal", 9000), Result(2, "Sam", "normal", 8000)])
    await cog.save_results([Result(1, "Maya", "normal", 7000)])
    boards = await cog.leaderboard(asker(2), {})
    assert [row["name"] for row in boards["normal"]["top"]] == ["Maya", "Sam"]
    assert boards["normal"]["you"]["rank"] == 2


@pytest.mark.asyncio
async def test_deleting_a_players_data_takes_them_off_the_leaderboard():
    cog = AgeOfWar(bot=None)
    await cog.save_results([Result(1, "Maya", "normal", 9000), Result(2, "Sam", "normal", 8000)])
    await cog.red_delete_data_for_user(requester="user", user_id=1)
    boards = await cog.leaderboard(asker(1), {})
    assert [row["name"] for row in boards["normal"]["top"]] == ["Sam"] and boards["normal"]["you"] is None


@pytest.mark.asyncio
async def test_a_window_whose_room_was_replaced_keeps_its_match_on_the_new_room():
    # Reloading ActivityHub gives every window a fresh room, while the match and its kept seats live on
    cog = AgeOfWar(bot=None)
    old_room, new_room = FakeRoom("window"), FakeRoom("window")
    match = cog.match_for(FakeConn(old_room, 1))
    try:
        assert cog.match_for(FakeConn(new_room, 1)) is match
        assert match.room is new_room
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_each_window_gets_its_own_match():
    cog = AgeOfWar(bot=None)
    try:
        first = cog.match_for(FakeConn(FakeRoom("a"), 1))
        second = cog.match_for(FakeConn(FakeRoom("b"), 2))
        assert first is not second and set(cog.matches) == {"a", "b"}
    finally:
        await cog.cog_unload()
