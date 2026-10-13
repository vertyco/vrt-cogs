import asyncio

import pytest

from ageofwar.common.lobby import GAME_GONE, STILL_PLAYING, Lobby
from ageofwar.common.match import PLAYING, RESULTS, SETUP
from ageofwar.tests.fakes import FakeConn, FakeRoom


class Window:
    """A lobby on a fake room, and whether it said it was empty"""

    def __init__(self):
        self.room = FakeRoom()
        self.empty = False
        self.lobby = Lobby(self.room, lambda results: None, self.emptied)

    def emptied(self, lobby: Lobby) -> None:
        self.empty = True

    async def arrive(self, user_id: int, follow: int | None = None) -> FakeConn:
        conn = FakeConn(self.room, user_id)
        conn.follow = follow
        await self.lobby.join(conn, follow)
        return conn

    async def send(self, conn: FakeConn, data) -> None:
        await self.lobby.message(conn, data)

    def close(self) -> None:
        self.lobby.stop()


def last(conn: FakeConn, key: str):
    return next(message[key] for message in reversed(conn.sent) if key in message)


@pytest.fixture
def window():
    made = Window()
    yield made
    made.close()


@pytest.mark.asyncio
async def test_the_first_page_goes_straight_into_a_new_match(window):
    first = await window.arrive(1)
    assert len(window.lobby.matches) == 1
    assert window.lobby.match_of(first) is not None and last(first, "state")["stage"] == SETUP


@pytest.mark.asyncio
async def test_a_later_page_gets_the_games_list_and_can_watch(window):
    first = await window.arrive(1)
    await window.send(first, {"sit": 0})
    second = await window.arrive(2)
    games = last(second, "games")
    assert len(games) == 1 and games[0]["seats"][0]["name"] == "Player 1"
    await window.send(second, {"watch": games[0]["id"]})
    assert window.lobby.match_of(second) is window.lobby.match_of(first)


@pytest.mark.asyncio
async def test_starting_your_own_game_makes_a_second_match_with_you_as_host(window):
    first = await window.arrive(1)
    await window.send(first, {"sit": 0})
    await window.send(first, {"start": True})
    second = await window.arrive(2)
    await window.send(second, {"new": True})
    mine = window.lobby.match_of(second)
    assert len(window.lobby.matches) == 2 and mine is not window.lobby.match_of(first)
    assert mine.seat_of(2) is mine.seats[0] and mine.host == 0
    await window.send(second, {"start": True})
    assert mine.stage == PLAYING and window.lobby.match_of(first).stage == PLAYING


@pytest.mark.asyncio
async def test_a_watcher_can_leave_a_battle_for_the_list(window):
    first = await window.arrive(1)
    await window.send(first, {"sit": 0})
    await window.send(first, {"start": True})
    second = await window.arrive(2)
    await window.send(second, {"watch": next(iter(window.lobby.matches))})
    await window.send(second, {"games": True})
    assert window.lobby.match_of(second) is None and last(second, "games")[0]["stage"] == PLAYING


@pytest.mark.asyncio
async def test_a_player_commanding_a_base_must_give_up_before_leaving(window):
    first = await window.arrive(1)
    await window.send(first, {"sit": 0})
    await window.send(first, {"start": True})
    await window.send(first, {"games": True})
    await window.send(first, {"new": True})
    assert {"notice": STILL_PLAYING} in first.sent and len(window.lobby.matches) == 1
    await window.send(first, {"quit": True})
    await window.send(first, {"games": True})
    match = next(iter(window.lobby.matches.values()))
    # Nobody is left at a base, so the finished match goes back to an empty setup
    assert window.lobby.match_of(first) is None and match.stage == SETUP and not match.seats[0].human


@pytest.mark.asyncio
async def test_leaving_a_setup_frees_the_seat_at_once(window):
    first = await window.arrive(1)
    await window.send(first, {"sit": 0})
    await window.send(first, {"games": True})
    match = next(iter(window.lobby.matches.values()))
    assert not match.seats[0].human and match.audience == []


@pytest.mark.asyncio
async def test_a_returning_player_lands_back_at_their_base(window):
    first = await window.arrive(1)
    await window.send(first, {"sit": 0})
    await window.send(first, {"start": True})
    await window.arrive(2)
    first.drop()
    window.lobby.leave(first)
    again = await window.arrive(1)
    assert window.lobby.match_of(again) is not None and last(again, "state")["stage"] == PLAYING


@pytest.mark.asyncio
async def test_join_puts_the_player_with_their_friend(window):
    first = await window.arrive(1)
    await window.send(first, {"sit": 0})
    second = await window.arrive(2)
    await window.send(second, {"new": True})
    friend = await window.arrive(3, follow=2)
    assert window.lobby.match_of(friend) is window.lobby.match_of(second)


@pytest.mark.asyncio
async def test_watching_a_game_that_ended_resends_the_list(window):
    first = await window.arrive(1)
    second = await window.arrive(2)
    await window.send(first, {"games": True})
    await window.send(second, {"watch": "gone"})
    assert {"notice": GAME_GONE} in second.sent and "games" in second.sent[-1]
    # The emptied match stops on its next update, and the lists go out after it
    await asyncio.sleep(0.1)
    assert window.lobby.matches == {}


@pytest.mark.asyncio
async def test_the_window_says_it_is_empty_once_its_matches_and_pages_are_gone(window):
    first = await window.arrive(1)
    match = window.lobby.match_of(first)
    first.drop()
    window.lobby.leave(first)
    window.lobby.match_ended(match)
    assert window.empty and window.lobby.matches == {}


@pytest.mark.asyncio
async def test_results_stage_counts_in_the_list(window):
    first = await window.arrive(1)
    await window.send(first, {"sit": 0})
    await window.send(first, {"start": True})
    await window.send(first, {"quit": True})
    second = await window.arrive(2)
    assert last(second, "games")[0]["stage"] == RESULTS
