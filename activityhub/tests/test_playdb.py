import pytest

from activityhub.db.tables import Play

BIG_ID = 1234567890123456789


@pytest.mark.asyncio
async def test_a_play_row_keeps_big_ids_and_an_empty_server(playdb):
    await Play.insert(
        Play(
            guild_id=BIG_ID, user_id=BIG_ID + 1, game="vegas", platform="mobile", started_at=1792181645.5, seconds=372.5
        ),
        Play(guild_id=None, user_id=BIG_ID, game="tanks", platform="", started_at=1792190000.0, seconds=0.0),
    )
    columns = (Play.guild_id, Play.user_id, Play.game, Play.platform, Play.started_at, Play.seconds)
    rows = await Play.select(*columns).order_by(Play.started_at)
    assert rows == [
        {
            "guild_id": BIG_ID,
            "user_id": BIG_ID + 1,
            "game": "vegas",
            "platform": "mobile",
            "started_at": 1792181645.5,
            "seconds": 372.5,
        },
        {
            "guild_id": None,
            "user_id": BIG_ID,
            "game": "tanks",
            "platform": "",
            "started_at": 1792190000.0,
            "seconds": 0.0,
        },
    ]
