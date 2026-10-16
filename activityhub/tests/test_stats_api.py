import time

import pytest
import pytest_asyncio

from activityhub.db.tables import Play
from activityhub.tests.fakes import ADMIN_ID, GUILD_ID, MANAGER_ID, MEMBER_ID, OWNER_ID, session_headers


async def stats(client, headers, **query):
    params = {"days": "7", "offset": "0", **query}
    resp = await client.get("/hub/api/stats", params=params, headers=headers)
    return resp.status, await resp.json()


@pytest_asyncio.fixture
async def plays(hub, playdb, demo):
    hub.playlog.opened()
    now = time.time()
    await Play.insert(
        Play(guild_id=GUILD_ID, user_id=MEMBER_ID, game="demo", platform="mobile", started_at=now - 60, seconds=30),
        Play(guild_id=600, user_id=MEMBER_ID, game="demo", platform="desktop", started_at=now - 60, seconds=10),
    )


@pytest.mark.asyncio
async def test_an_admin_sees_their_own_server_only(client, hub, plays):
    headers = session_headers(hub, user_id=ADMIN_ID)
    status, body = await stats(client, headers)
    assert status == 200 and body["server"] == str(GUILD_ID) and body["servers"] is None
    assert [(game["key"], game["name"], game["plays"]) for game in body["games"]] == [("demo", "Demo", 1)]
    assert (await stats(client, headers, server=str(GUILD_ID)))[0] == 200
    for server in ["600", "all", "none"]:
        status, body = await stats(client, headers, server=server)
        assert status == 403 and body["error"] == "You can't see these numbers."


@pytest.mark.asyncio
async def test_the_owner_sees_any_server(client, hub, plays):
    headers = session_headers(hub, user_id=OWNER_ID)
    status, body = await stats(client, headers, server="all", days="0")
    assert status == 200 and body["overall"]["plays"] == 2
    assert [server["id"] for server in body["servers"]] == [str(GUILD_ID), "600"]
    assert (await stats(client, headers, server="600"))[1]["overall"]["plays"] == 1
    # Outside a server the owner starts on all servers
    status, body = await stats(client, session_headers(hub, user_id=OWNER_ID, guild_id=None))
    assert status == 200 and body["server"] == "all"


@pytest.mark.asyncio
async def test_players_and_strangers_are_refused(client, hub, plays):
    assert (await stats(client, session_headers(hub, user_id=MEMBER_ID)))[0] == 403
    assert (await stats(client, session_headers(hub, user_id=ADMIN_ID, guild_id=None)))[0] == 403
    assert (await stats(client, {}))[0] == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [{"days": "14"}, {"offset": "abc"}, {"offset": "900"}, {"server": "x"}])
async def test_bad_settings_get_400(client, hub, plays, query):
    assert (await stats(client, session_headers(hub, user_id=OWNER_ID), **query))[0] == 400


@pytest.mark.asyncio
async def test_a_closed_database_gets_503(client, hub):
    status, body = await stats(client, session_headers(hub, user_id=OWNER_ID))
    assert status == 503 and body["error"] == "The play log isn't available. The bot's log says why."


@pytest.mark.asyncio
async def test_the_stats_tab_saves_nothing(client, hub, demo):
    headers = session_headers(hub, user_id=MANAGER_ID)
    body = {"tab": "stats", "look": {"layout": "list"}, "disabled": ["demo"]}
    resp = await client.post("/hub/api/settings", json=body, headers=headers)
    assert resp.status == 400
    assert await hub.config.look() == {} and await hub.config.disabled() == []
    assert hub.config.guilds.get(GUILD_ID, {}).get("disabled", []) == []
