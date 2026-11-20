import asyncio
from dataclasses import asdict

import pytest

from penguinwars.common.leaderboard import Result
from penguinwars.common.tuning import SLIDERS, Tuning
from penguinwars.main import PenguinWars
from penguinwars.tests.fakes import ADMIN_ID, GUILD_ID, OWNER_ID, FakeBot, FakeConn, FakeRoom, answer


@pytest.mark.asyncio
async def test_activityhub_accepts_the_game():
    games = pytest.importorskip("activityhub.common.games")
    game = await games.validate_game(PenguinWars(bot=None))
    assert game.key == "penguinwars" and game.name == "Penguin Wars"
    assert set(game.socket) == {"join", "message", "leave"}
    assert set(game.actions) == {
        "leaderboard",
        "shop",
        "buy",
        "wear",
        "extras",
        "crate",
        "party",
        "snowball",
        "profile",
        "shop_settings",
        "save_shop",
        "tuning",
        "save_tuning",
    }
    assert game.icon == "icon.svg" and game.thumbnail == "thumb.png"


@pytest.mark.asyncio
async def test_one_window_shares_one_match():
    cog = PenguinWars(bot=None)
    room = FakeRoom("window")
    match = cog.match_for(FakeConn(room, 1))
    try:
        assert cog.match_for(FakeConn(room, 2)) is match
        assert cog.match_for(FakeConn(FakeRoom("other"), 3)) is not match
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_a_window_whose_room_was_replaced_keeps_its_match_on_the_new_room():
    cog = PenguinWars(bot=None)
    old_room, new_room = FakeRoom("window"), FakeRoom("window")
    match = cog.match_for(FakeConn(old_room, 1))
    try:
        assert cog.match_for(FakeConn(new_room, 1)) is match
        assert match.room is new_room
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_joining_sits_and_leaving_go_through_the_window_match():
    cog = PenguinWars(bot=None)
    conn = FakeConn(FakeRoom("window"), 1)
    try:
        assert await cog.looks_of(1) == {"neck": "scarf"}
        await cog.join(conn.ctx, conn)
        assert conn.sent[-1]["state"]["stage"] == "waiting"
        await cog.message(conn.ctx, conn, {"sit": True})
        match = cog.matches["window"]
        assert match.stage == "starting" and match.seats[0].user_id == 1
        await cog.leave(conn.ctx, conn)
        # The only player left mid-round, so the round stopped and their seat emptied
        assert match.stage == "waiting" and not match.seats[0].human
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", [{}, {"slide_speed": 14.0}, {"slide_speed": "fast"}])
async def test_saved_settings_load_in_range_values_only(saved):
    cog = PenguinWars(bot=None)
    await cog.config.clear_all()
    await cog.config.tuning.set(saved)
    await cog.cog_load()
    assert cog.tuning.slide_speed == (14.0 if saved == {"slide_speed": 14.0} else Tuning().slide_speed)


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", ["junk", None, 7])
async def test_a_saved_value_that_is_not_an_object_counts_as_empty(saved, monkeypatch):
    cog = PenguinWars(bot=None)
    monkeypatch.setattr(cog.config, "tuning", answer(saved))
    await cog.cog_load()
    assert cog.tuning == Tuning()


def board_ctx(conn, guild=True):
    ctx = conn.ctx
    if not guild:
        ctx.guild, ctx.guild_id = None, None
    return ctx


@pytest.mark.asyncio
async def test_a_finished_round_is_saved_per_player_and_the_board_ranks_it():
    cog = PenguinWars(bot=None)
    await cog.config.clear_all_members()
    conn = FakeConn(FakeRoom("window"), 1)
    ctx = board_ctx(conn)
    ctx.guild.members = []
    results = [Result(1, "Ann", 2, True), Result(2, "Bo", 1, False)]
    cog.record_round(GUILD_ID, results)
    cog.record_round(GUILD_ID, [Result(1, "Ann Renamed", 1, True)])
    await asyncio.gather(*cog.saving)
    board = await cog.config.all_members(ctx.guild)
    assert board[1] == {"wins": 2, "knockouts": 3, "rounds": 2, "name": "Ann Renamed"}
    answer_ = await cog.leaderboard(ctx, {})
    assert answer_["dm"] is False and [row["id"] for row in answer_["top"]] == ["1", "2"]
    assert answer_["you"]["rank"] == 1


@pytest.mark.asyncio
async def test_a_window_with_no_server_saves_nothing_and_answers_dm():
    cog = PenguinWars(bot=None)
    ctx = board_ctx(FakeConn(FakeRoom("window"), 1), guild=False)
    cog.record_round(None, [Result(1, "Ann", 2, True)])
    assert not cog.saving
    assert await cog.leaderboard(ctx, {}) == {"top": [], "you": None, "dm": True}


@pytest.mark.asyncio
async def test_a_failed_save_for_one_player_leaves_the_others_saved(caplog, monkeypatch):
    cog = PenguinWars(bot=None)
    await cog.config.clear_all_members()
    real = cog.config.member_from_ids

    def flaky(guild_id, user_id):
        if user_id == 1:
            raise RuntimeError("disk full")
        return real(guild_id, user_id)

    monkeypatch.setattr(cog.config, "member_from_ids", flaky)
    cog.record_round(GUILD_ID, [Result(1, "Ann", 2, True), Result(2, "Bo", 1, False)])
    await asyncio.gather(*cog.saving)
    assert "Couldn't save a Penguin Wars result for user 1" in caplog.text
    assert (await real(GUILD_ID, 2).all())["rounds"] == 1


def tuned_cog():
    return PenguinWars(bot=FakeBot())


def numbers(**changes):
    return {**asdict(Tuning()), **changes}


@pytest.mark.asyncio
async def test_only_the_bot_owner_sees_or_saves_the_numbers():
    cog = tuned_cog()
    await cog.config.clear_all()
    owner, admin = FakeConn(FakeRoom("a"), OWNER_ID).ctx, FakeConn(FakeRoom("b"), ADMIN_ID).ctx
    assert await cog.tuning_view(admin, {}) == {"tuning": None}
    refused = await cog.save_tuning(admin, {"tuning": numbers(slide_speed=14.0)})
    assert "bot owner" in refused["error"]
    assert cog.tuning == Tuning() and await cog.config.tuning() == {}
    seen = await cog.tuning_view(owner, {})
    assert seen == {"tuning": asdict(Tuning()), "sliders": SLIDERS, "defaults": asdict(Tuning())}


@pytest.mark.asyncio
async def test_saved_numbers_reach_every_running_match_and_survive_a_reload():
    cog = tuned_cog()
    await cog.config.clear_all()
    owner = FakeConn(FakeRoom("a"), OWNER_ID).ctx
    first = cog.match_for(FakeConn(FakeRoom("one"), 1))
    second = cog.match_for(FakeConn(FakeRoom("two"), 2))
    try:
        first.begin_round()
        answered = await cog.save_tuning(owner, {"tuning": numbers(slide_speed=14.0, ice_speed=1.5)})
        assert answered["tuning"]["slide_speed"] == 14.0
        assert first.tuning.slide_speed == second.tuning.slide_speed == 14.0
        assert cog.match_for(FakeConn(FakeRoom("three"), 3)).tuning.ice_speed == 1.5
        again = PenguinWars(bot=FakeBot())
        await again.cog_load()
        assert again.tuning.slide_speed == 14.0 and again.tuning.ice_speed == 1.5
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_a_number_saved_mid_round_reaches_the_round_without_breaking_it():
    cog = tuned_cog()
    await cog.config.clear_all()
    owner = FakeConn(FakeRoom("a"), OWNER_ID).ctx
    conn = FakeConn(FakeRoom("one"), 1)
    match = cog.match_for(conn)
    try:
        await match.join(conn, {})
        match.begin_round()
        assert match.round is not None
        await cog.save_tuning(owner, {"tuning": numbers(brace_seconds=0.9, ice_speed=0.4)})
        assert match.round.tuning.brace_seconds == 0.9 and match.round.floe.tuning.ice_speed == 0.4
        await match.tick()
        assert match.state()["state"]["rules"]["brace_seconds"] == 0.9
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        None,
        "fast",
        {},
        numbers(slide_speed=99.0),
        numbers(slide_speed=float("nan")),
        numbers(seal_wait="2"),
        {**numbers(), "x": 1},
        numbers(slide_speed=10**400),
    ],
)
async def test_bad_numbers_are_refused_and_change_nothing(bad):
    cog = tuned_cog()
    await cog.config.clear_all()
    match = cog.match_for(FakeConn(FakeRoom("one"), 1))
    try:
        answered = await cog.save_tuning(FakeConn(FakeRoom("a"), OWNER_ID).ctx, {"tuning": bad})
        assert "error" in answered
        assert cog.tuning == Tuning() and match.tuning == Tuning() and await cog.config.tuning() == {}
    finally:
        await cog.cog_unload()
