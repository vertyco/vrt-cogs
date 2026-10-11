import asyncio

import pytest
import pytest_asyncio

from activityhub.common import presence as presence_module
from activityhub.tests.fakes import GUILD_ID, MANAGER_ID, MEMBER_ID, DemoCog, register, write_demo_web
from activityhub.tests.test_live import READY, close_code, next_json, session_token


class FollowCog(DemoCog):
    """Says who the player followed, so a test can see conn.follow"""

    async def on_join(self, ctx, conn):
        await conn.send({"follow": conn.follow})


@pytest_asyncio.fixture(autouse=True)
async def quick(monkeypatch, server, client):
    monkeypatch.setattr(presence_module, "SEND_EVERY", 0)
    yield
    # Most tests never stop the server, so this cancels the graces left running after their links closed
    server.presence.stop()


@pytest.fixture
def follow_game(hub, tmp_path):
    cog = FollowCog(write_demo_web(tmp_path / "demo"))
    assert register(hub, cog) is not None
    return cog


async def menu_link(client, hub, **kwargs):
    ws = await client.ws_connect("/hub/ws")
    await ws.send_json({"session": session_token(hub, **kwargs)})
    assert await next_json(ws) == READY
    return ws


@pytest.mark.asyncio
async def test_the_menu_link_needs_a_login(client, hub):
    ws = await client.ws_connect("/hub/ws")
    await ws.send_json({"session": "nope"})
    assert await close_code(ws) == 4001


@pytest.mark.asyncio
async def test_the_menu_link_reports_where_people_are(client, hub, demo):
    ann = await menu_link(client, hub)
    assert [p["id"] for p in (await next_json(ann))["people"]] == [str(MEMBER_ID)]
    bo = await menu_link(client, hub, user_id=MANAGER_ID)
    await next_json(ann)
    await bo.send_json({"where": "demo", "status": "Clicking", "data": None, "busy": False, "away": False})
    people = (await next_json(ann))["people"]
    assert [(p["id"], p["game"], p["status"]) for p in people] == [
        (str(MEMBER_ID), None, ""),
        (str(MANAGER_ID), "demo", "Clicking"),
    ]
    await ann.close()
    await bo.close()


@pytest.mark.asyncio
async def test_menu_link_survives_junk(client, hub, demo):
    ann = await menu_link(client, hub)
    await next_json(ann)
    await ann.send_str("not json")
    await ann.send_json(["where"])
    await ann.send_json({"where": "demo", "hack": 1})
    await ann.send_json({"activityhub": "echo", "t": 5})
    assert await next_json(ann) == {"activityhub": "echo", "t": 5}
    await ann.send_json({"where": "demo"})
    assert (await next_json(ann))["people"][0]["game"] == "demo"
    await ann.close()


@pytest.mark.asyncio
async def test_a_failing_menu_message_keeps_the_link(client, hub, server, demo, monkeypatch, caplog):
    async def broken(conn, data):
        raise RuntimeError("boom")

    monkeypatch.setattr(server.presence, "update", broken)
    ann = await menu_link(client, hub)
    await next_json(ann)
    await ann.send_json({"where": "demo"})
    await ann.send_json({"activityhub": "echo", "t": 1})
    assert await next_json(ann) == {"activityhub": "echo", "t": 1}
    assert "of the menu failed" in caplog.text and "boom" in caplog.text
    await ann.close()


@pytest.mark.asyncio
async def test_a_game_is_on_when_installed_and_not_switched_off(hub, server, demo):
    assert await server.game_on(GUILD_ID, "demo") is True
    assert await server.game_on(GUILD_ID, "nothing") is False
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["demo"])
    assert await server.game_on(GUILD_ID, "demo") is False


@pytest.mark.asyncio
async def test_a_game_the_owner_switched_off_is_off_everywhere(hub, server, demo):
    await hub.config.disabled.set(["demo"])
    assert await server.game_on(GUILD_ID, "demo") is False
    assert await server.game_on(None, "demo") is False


@pytest.mark.asyncio
async def test_outside_a_server_only_the_owners_switch_counts(hub, server, demo):
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["demo"])
    assert await server.game_on(None, "demo") is True


@pytest.mark.asyncio
async def test_shutdown_closes_the_menu_link_1001(client, hub, server):
    ann = await menu_link(client, hub)
    await next_json(ann)
    closing = asyncio.create_task(server.on_shutdown(None))
    assert await close_code(ann) == 1001
    await closing


@pytest.mark.asyncio
async def test_stopping_the_server_empties_the_people_lists(client, hub, server):
    ann = await menu_link(client, hub)
    await next_json(ann)
    assert len(server.presence.links()) == 1
    await server.stop()
    assert server.presence.links() == []
    await ann.close()


@pytest.mark.asyncio
async def test_follow_only_counts_inside_the_window(client, hub, follow_game):
    bo = await menu_link(client, hub, user_id=MANAGER_ID)
    for follow, expected in [(str(MANAGER_ID), MANAGER_ID), ("999", None), (str(MEMBER_ID), None), (None, None)]:
        ws = await client.ws_connect("/games/demo/ws")
        await ws.send_json({"session": session_token(hub), "follow": follow})
        assert await next_json(ws) == READY
        assert await next_json(ws) == {"follow": expected}
        await ws.close()
    far = await client.ws_connect("/games/demo/ws")
    await far.send_json({"session": session_token(hub, instance_id="i-2"), "follow": str(MANAGER_ID)})
    assert await next_json(far) == READY
    assert await next_json(far) == {"follow": None}
    await far.close()
    await bo.close()
