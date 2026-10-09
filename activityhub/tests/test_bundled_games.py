import pytest

from activityhub.bundled import bricks, snake, twenty48
from activityhub.bundled.games import NO_BOARD, NO_ROUND, NOT_SAVED, PRACTICE, WEB_DIR, bundled_games
from activityhub.bundled.scores import BOARD_SIZE, RUN_TTL, ScoreBoard
from activityhub.tests.fakes import (
    ADMIN_ID,
    GUILD_ID,
    MANAGER_ID,
    MEMBER_ID,
    OWNER_ID,
    fake_member,
    fake_user,
    register,
    session_headers,
)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(hub):
    clock = Clock()
    hub.scores = ScoreBoard(hub.config, clock=clock)
    for game in bundled_games(hub.scores):
        assert register(hub, game) is not None
    return clock


def moves_2048(seed: int, count: int = 40) -> str:
    """Moves a real page could send: each one slides something"""
    board, moves = twenty48.Board(seed), ""
    while len(moves) < count:
        # A move that slides nothing leaves the board as it was, so the first one that slides is kept
        direction = next((d for d in "ULDR" if board.move(d)), None)
        if direction is None:
            break
        moves += direction
    return moves


async def start(client, hub, key="2048", **who) -> dict:
    resp = await client.post(f"/games/{key}/api/start", json={}, headers=session_headers(hub, **who))
    assert resp.status == 200
    return await resp.json()


async def finish(client, hub, body, key="2048", **who):
    resp = await client.post(f"/games/{key}/api/finish", json=body, headers=session_headers(hub, **who))
    return resp.status, await resp.json()


async def play_2048(client, hub, clock, count=40, **who) -> tuple[int, dict]:
    opened = await start(client, hub, **who)
    moves = moves_2048(opened["seed"], count)
    clock.now += 60
    return await finish(client, hub, {"run": opened["run"], "moves": moves}, **who)


def test_bundled_games_register(hub, clock):
    assert {"snake", "2048", "brickbreaker"} <= set(hub.registry.games)
    game = hub.registry.games["snake"]
    assert game.icon == "icon.svg" and game.thumbnail == "thumb.svg"
    assert game.cog.qualified_name == "ActivityHub Snake"
    assert set(game.actions) == {"start", "finish", "board"}


@pytest.mark.asyncio
async def test_game_pages_can_import_the_hub_files(client, server, clock):
    text = await (await client.get("/games/snake/")).text()
    assert f'"activityhub/": "/hub/{server.hub_build()}/"' in text


@pytest.mark.asyncio
async def test_a_real_round_is_saved_and_ranked(client, hub, clock):
    status, result = await play_2048(client, hub, clock)
    assert status == 200
    assert result["score"] > 0 and result["newBest"] and result["best"] == result["score"]
    board = result["board"]
    assert board["server"] == "Test Server"
    row = {
        "rank": 1,
        "name": "Member",
        "avatar": hub.bot.get_user(MEMBER_ID).display_avatar.url,
        "score": result["score"],
        "you": True,
    }
    assert board["top"] == [row]
    assert board["you"] == row


@pytest.mark.asyncio
async def test_a_lower_score_keeps_the_best(client, hub, clock):
    _, first = await play_2048(client, hub, clock, count=60)
    _, second = await play_2048(client, hub, clock, count=5)
    assert second["score"] < first["score"]
    assert not second["newBest"] and second["best"] == first["score"]


@pytest.mark.asyncio
async def test_changed_moves_are_refused(client, hub, clock):
    opened = await start(client, hub)
    moves = moves_2048(opened["seed"])
    clock.now += 60
    status, result = await finish(client, hub, {"run": opened["run"], "moves": moves + "X"})
    assert status == 400 and result["error"] == NOT_SAVED
    assert hub.config.members.get(GUILD_ID, {}).get(MEMBER_ID, {}).get("best", {}) == {}
    # A refused round is closed, so it can't be sent again with other moves
    body = {"run": opened["run"], "moves": moves}
    assert (await finish(client, hub, body)) == (400, {"error": NO_ROUND})


@pytest.mark.asyncio
async def test_a_round_faster_than_possible_is_refused(client, hub, clock):
    opened = await start(client, hub)
    clock.now += 0.1
    status, result = await finish(client, hub, {"run": opened["run"], "moves": moves_2048(opened["seed"])})
    assert status == 400 and result["error"] == NOT_SAVED


@pytest.mark.asyncio
async def test_a_round_is_saved_once_and_only_by_its_player(client, hub, clock):
    opened = await start(client, hub)
    body = {"run": opened["run"], "moves": moves_2048(opened["seed"])}
    clock.now += 60
    assert (await finish(client, hub, body, user_id=OWNER_ID)) == (400, {"error": NO_ROUND})
    assert (await finish(client, hub, body, key="snake")) == (400, {"error": NO_ROUND})
    saved = await finish(client, hub, body)
    assert saved[0] == 200
    # Sent again by Retry save because the answer never arrived: the same answer, so the player isn't told the
    # saved round was lost
    assert (await finish(client, hub, body)) == saved


@pytest.mark.asyncio
async def test_a_failed_save_keeps_the_round_for_retry_save(client, hub, clock, monkeypatch):
    opened = await start(client, hub)
    body = {"run": opened["run"], "moves": moves_2048(opened["seed"])}
    clock.now += 60
    real_save = hub.scores.save

    async def broken_save(*args):
        monkeypatch.setattr(hub.scores, "save", real_save)
        raise OSError("the disk is full")

    monkeypatch.setattr(hub.scores, "save", broken_save)
    assert (await finish(client, hub, body))[0] == 500
    status, result = await finish(client, hub, body)
    assert status == 200 and result["newBest"]


@pytest.mark.asyncio
async def test_starting_again_drops_the_unfinished_round(client, hub, clock):
    first = await start(client, hub)
    await start(client, hub)
    clock.now += 60
    body = {"run": first["run"], "moves": moves_2048(first["seed"])}
    assert (await finish(client, hub, body)) == (400, {"error": NO_ROUND})


@pytest.mark.asyncio
async def test_old_rounds_expire(client, hub, clock):
    opened = await start(client, hub)
    clock.now += RUN_TTL + 1
    await start(client, hub, key="snake")  # any new round clears out expired ones
    assert opened["run"] not in hub.scores.runs


@pytest.mark.asyncio
async def test_outside_a_server_nothing_is_saved(client, hub, clock):
    opened = await start(client, hub, guild_id=None)
    assert opened["run"] is None and isinstance(opened["seed"], int)
    assert (await finish(client, hub, {"run": "x", "moves": ""}, guild_id=None)) == (400, {"error": PRACTICE})
    resp = await client.post("/games/2048/api/board", json={}, headers=session_headers(hub, guild_id=None))
    assert resp.status == 400 and (await resp.json())["error"] == NO_BOARD


@pytest.mark.asyncio
async def test_snake_and_brick_breaker_rounds_are_saved(client, hub, clock):
    opened = await start(client, hub, key="snake")
    clock.now += 60
    status, result = await finish(client, hub, {"run": opened["run"], "moves": [], "ticks": 9}, key="snake")
    # Nine steps right may or may not pass an apple; either way the round is real
    assert status == 200 and result["score"] >= 0

    opened = await start(client, hub, key="brickbreaker")
    clock.now += 60
    levels = bricks.load_levels(WEB_DIR / "brickbreaker" / "levels.json")
    body = {"run": opened["run"], "bricks": bricks.breakable_count(levels[0]), "levels_cleared": 1}
    status, result = await finish(client, hub, body, key="brickbreaker")
    assert status == 200 and result["score"] == bricks.breakable_count(levels[0]) * 10 + 100


@pytest.mark.asyncio
async def test_snake_too_fast_is_refused(client, hub, clock):
    opened = await start(client, hub, key="snake")
    clock.now += 0.5
    status, result = await finish(client, hub, {"run": opened["run"], "moves": [], "ticks": 9}, key="snake")
    assert status == 400 and result["error"] == NOT_SAVED


@pytest.mark.asyncio
async def test_a_made_up_long_round_is_refused_without_a_replay(client, hub, clock, monkeypatch):
    replays = []
    monkeypatch.setattr(snake, "replay", lambda *args: replays.append(args))
    opened = await start(client, hub, key="snake")
    clock.now += 60
    status, result = await finish(client, hub, {"run": opened["run"], "moves": [], "ticks": 10**6}, key="snake")
    assert status == 400 and result["error"] == NOT_SAVED
    assert replays == []


def save(hub, user_id, key, score, at):
    member = hub.bot.get_guild(GUILD_ID).get_member(user_id)
    best = hub.config.member(member).data["best"]
    best[key] = {"score": score, "at": at}


@pytest.mark.asyncio
async def test_board_orders_by_score_then_who_got_there_first(hub, clock):
    guild = hub.bot.get_guild(GUILD_ID)
    save(hub, OWNER_ID, "2048", 500, 2.0)
    save(hub, MANAGER_ID, "2048", 500, 1.0)
    save(hub, ADMIN_ID, "2048", 900, 3.0)
    save(hub, MEMBER_ID, "snake", 10, 1.0)  # a different game
    hub.config.member_from_ids(GUILD_ID, 999).data["best"]["2048"] = {"score": 9999, "at": 0.0}  # left the server
    board = await hub.scores.board(guild, guild.get_member(MEMBER_ID), "2048")
    assert [row["name"] for row in board["top"]] == ["Admin", "Manager", "Owner"]
    assert [row["rank"] for row in board["top"]] == [1, 2, 3]
    assert board["you"] is None


@pytest.mark.asyncio
async def test_board_shows_your_rank_below_the_top(hub, clock):
    guild = hub.bot.get_guild(GUILD_ID)
    for i in range(BOARD_SIZE + 2):
        user_id = 100 + i
        guild.members[user_id] = fake_member(fake_user(user_id, f"player{i}"), guild)
        hub.config.member_from_ids(GUILD_ID, user_id).data["best"]["2048"] = {"score": 1000 + i, "at": 1.0}
    save(hub, MEMBER_ID, "2048", 5, 1.0)
    board = await hub.scores.board(guild, guild.get_member(MEMBER_ID), "2048")
    assert len(board["top"]) == BOARD_SIZE
    assert not any(row["you"] for row in board["top"])
    avatar = hub.bot.get_user(MEMBER_ID).display_avatar.url
    assert board["you"] == {"rank": BOARD_SIZE + 3, "name": "Member", "avatar": avatar, "score": 5, "you": True}


@pytest.mark.asyncio
async def test_a_zero_score_isnt_saved(hub, clock):
    member = hub.bot.get_guild(GUILD_ID).get_member(MEMBER_ID)
    assert await hub.scores.save(member, "2048", 0) == (0, False)
    assert hub.config.member(member).data["best"] == {}
