import logging

import pytest

from activityhub.tests.fakes import (
    ADMIN_ID,
    GUILD_ID,
    GUILD_OWNER_ID,
    MANAGER_ID,
    MEMBER_ID,
    OWNER_ID,
    session_headers,
)

LOOK_LIST = {"layout": "list", "accent": None, "background": None, "details": None}


async def menu(client, headers=None):
    resp = await client.get("/hub/api/menu", headers=headers or {})
    return resp.status, await resp.json()


async def save(client, headers, body):
    resp = await client.post("/hub/api/settings", json=body, headers=headers)
    return resp.status, await resp.json()


def keys(state):
    return [game["key"] for game in state["games"]]


@pytest.mark.asyncio
async def test_preview_without_a_session(client, hub, demo, second):
    await hub.config.look.set({"layout": "list"})
    status, state = await menu(client)
    assert status == 200
    assert state["player"] is None and state["tabs"] == [] and state["switches"] == [] and state["launch"] is None
    assert keys(state) == ["second", "demo"]
    assert state["games"][1]["icon"].startswith("/games/demo/") and state["games"][1]["icon"].endswith("/icon.svg")
    assert state["look"]["layout"] == "list"


@pytest.mark.asyncio
async def test_bad_session_is_refused(client, demo):
    status, state = await menu(client, {"Authorization": "Bearer nope"})
    assert status == 401 and "expired" in state["error"]


@pytest.mark.asyncio
async def test_member_state(client, hub, demo, second):
    await hub.config.look.set({"accent": "#111111"})
    await hub.config.guild_from_id(GUILD_ID).look.set({"layout": "list"})
    await hub.config.user_from_id(MEMBER_ID).look.set({"layout": "compact"})
    status, state = await menu(client, session_headers(hub))
    assert status == 200
    assert state["player"]["id"] == str(MEMBER_ID)
    assert state["look"] == {
        "theme": "orb",
        "layout": "compact",
        "accent": "#111111",
        "background": "dark",
        "details": True,
        "sounds": True,
        "fps": True,
    }
    assert state["looks"]["guild"] == {"layout": "list"} and state["looks"]["user"] == {"layout": "compact"}
    assert state["tabs"] == ["look", "order"] and state["switches"] == []


@pytest.mark.asyncio
async def test_turned_off_games_are_left_out(client, hub, demo, second):
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["second"])
    status, state = await menu(client, session_headers(hub))
    assert keys(state) == ["demo"]


@pytest.mark.asyncio
async def test_games_off_everywhere_have_no_card_or_switch(client, hub, demo, second):
    await hub.config.disabled.set(["second"])
    status, state = await menu(client, session_headers(hub, guild_id=None))
    assert keys(state) == ["demo"]
    status, state = await menu(client)
    assert keys(state) == ["demo"]
    status, state = await menu(client, session_headers(hub, user_id=MANAGER_ID))
    assert keys(state) == ["demo"] and [s["key"] for s in state["switches"]] == ["demo"]


@pytest.mark.asyncio
async def test_server_save_keeps_its_choice_for_games_off_everywhere(client, hub, demo, second):
    await hub.config.disabled.set(["second"])
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["second"])
    await save(client, session_headers(hub, user_id=MANAGER_ID), {"tab": "server", "disabled": ["demo"]})
    assert hub.config.guilds[GUILD_ID]["disabled"] == ["second", "demo"]


@pytest.mark.asyncio
async def test_player_order_is_used(client, hub, demo, second):
    await hub.config.user_from_id(MEMBER_ID).order.set(["demo"])
    status, state = await menu(client, session_headers(hub))
    assert keys(state) == ["demo", "second"]


@pytest.mark.asyncio
async def test_dm_player_sees_every_game_and_no_server_tab(client, hub, demo, second):
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["second"])
    status, state = await menu(client, session_headers(hub, guild_id=None))
    assert keys(state) == ["second", "demo"]
    assert state["tabs"] == ["look", "order"] and state["looks"]["guild"] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_id, tabs",
    [
        (MANAGER_ID, ["look", "order", "server"]),
        (ADMIN_ID, ["look", "order", "server"]),
        (GUILD_OWNER_ID, ["look", "order", "server"]),
        (OWNER_ID, ["look", "order", "server", "defaults"]),
    ],
)
async def test_tabs_and_switches_by_permission(client, hub, demo, second, user_id, tabs):
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["demo"])
    status, state = await menu(client, session_headers(hub, user_id=user_id))
    assert state["tabs"] == tabs
    assert state["switches"] == [
        {"key": "second", "name": "Alpha Game", "on": True},
        {"key": "demo", "name": "Demo", "on": False},
    ]


@pytest.mark.asyncio
async def test_remembered_launch_is_handed_out_once(client, hub, demo):
    hub.launches.remember(MEMBER_ID, "demo")
    headers = session_headers(hub)
    assert (await menu(client, headers))[1]["launch"] == "demo"
    assert (await menu(client, headers))[1]["launch"] is None


@pytest.mark.asyncio
async def test_remembered_launch_skips_off_and_missing_games(client, hub, demo):
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["demo"])
    hub.launches.remember(MEMBER_ID, "demo")
    assert (await menu(client, session_headers(hub)))[1]["launch"] is None
    hub.launches.remember(MEMBER_ID, "gone")
    assert (await menu(client, session_headers(hub)))[1]["launch"] is None


@pytest.mark.asyncio
async def test_settings_need_a_session_and_an_object(client, hub):
    assert (await client.post("/hub/api/settings", json={"tab": "look", "look": {}})).status == 401
    assert (await client.post("/hub/api/settings", json=["look"], headers=session_headers(hub))).status == 400


@pytest.mark.asyncio
async def test_save_my_look(client, hub, demo):
    status, state = await save(client, session_headers(hub), {"tab": "look", "look": LOOK_LIST})
    assert status == 200 and state["look"]["layout"] == "list" and state["launch"] is None
    assert hub.config.users[MEMBER_ID]["look"] == {"layout": "list"}


@pytest.mark.asyncio
async def test_bad_look_is_refused_and_nothing_is_saved(client, hub):
    await hub.config.user_from_id(MEMBER_ID).look.set({"layout": "list"})
    status, body = await save(client, session_headers(hub), {"tab": "look", "look": {"layout": "tiles"}})
    assert status == 400 and "layout" in body["error"]
    assert hub.config.users[MEMBER_ID]["look"] == {"layout": "list"}


@pytest.mark.asyncio
async def test_save_my_order_keeps_installed_games(client, hub, demo, second):
    status, state = await save(client, session_headers(hub), {"tab": "order", "order": ["second", "gone", "demo"]})
    assert status == 200 and keys(state) == ["second", "demo"]
    assert hub.config.users[MEMBER_ID]["order"] == ["second", "demo"]


@pytest.mark.asyncio
async def test_save_my_order_keeps_the_places_of_games_that_are_off_here(client, hub, demo, second):
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["second"])
    await hub.config.user_from_id(MEMBER_ID).order.set(["second", "gone", "demo"])
    status, state = await save(client, session_headers(hub), {"tab": "order", "order": ["demo"]})
    assert status == 200 and keys(state) == ["demo"]
    assert hub.config.users[MEMBER_ID]["order"] == ["demo", "second"]


@pytest.mark.asyncio
async def test_reset_my_order_goes_back_to_alphabetical(client, hub, demo, second):
    await hub.config.user_from_id(MEMBER_ID).order.set(["demo", "second"])
    status, state = await save(client, session_headers(hub), {"tab": "order", "order": None})
    # "Alpha Game" is the second game's name, so it sorts first
    assert status == 200 and keys(state) == ["second", "demo"]
    assert hub.config.users[MEMBER_ID]["order"] == []


@pytest.mark.asyncio
async def test_a_manager_who_left_the_server_loses_the_server_tab(client, hub, demo):
    headers = session_headers(hub, user_id=MANAGER_ID)
    assert (await menu(client, headers))[1]["tabs"] == ["look", "order", "server"]
    del hub.bot.guilds[GUILD_ID].members[MANAGER_ID]
    assert (await menu(client, headers))[1]["tabs"] == ["look", "order"]
    assert (await save(client, headers, {"tab": "server", "disabled": ["demo"]}))[0] == 403


@pytest.mark.asyncio
async def test_the_server_owner_always_gets_the_server_tab(client, hub, demo):
    # Even when the member cache doesn't have them, like a bot without the members intent
    del hub.bot.guilds[GUILD_ID].members[GUILD_OWNER_ID]
    headers = session_headers(hub, user_id=GUILD_OWNER_ID)
    assert (await menu(client, headers))[1]["tabs"] == ["look", "order", "server"]
    assert (await save(client, headers, {"tab": "server", "look": {"theme": "standard"}}))[0] == 200
    assert hub.config.guilds[GUILD_ID]["look"] == {"theme": "standard"}


@pytest.mark.asyncio
async def test_the_server_theme_applies_to_members_who_kept_the_default(client, hub, demo):
    await hub.config.look.set({"theme": "orb"})
    await save(client, session_headers(hub, user_id=MANAGER_ID), {"tab": "server", "look": {"theme": "standard"}})
    # A member who changed another field still gets the server's theme
    await hub.config.user_from_id(MEMBER_ID).look.set({"fps": False})
    assert (await menu(client, session_headers(hub)))[1]["look"]["theme"] == "standard"
    # A member's own pick wins over the server's
    await hub.config.user_from_id(MEMBER_ID).look.set({"theme": "orb"})
    assert (await menu(client, session_headers(hub)))[1]["look"]["theme"] == "orb"
    # Back on Default, the server's theme applies again
    await save(client, session_headers(hub), {"tab": "look", "look": {"theme": None}})
    assert (await menu(client, session_headers(hub)))[1]["look"]["theme"] == "standard"


@pytest.mark.asyncio
async def test_refused_settings_are_logged(client, hub, caplog):
    with caplog.at_level(logging.DEBUG, logger="red.vrt.activityhub.hub_routes"):
        await save(client, session_headers(hub), {"tab": "look", "look": {"layout": "tiles"}})
    assert "Refused a look settings save" in caplog.text


@pytest.mark.asyncio
async def test_members_cannot_save_server_or_defaults(client, hub, demo):
    headers = session_headers(hub)
    assert (await save(client, headers, {"tab": "server", "disabled": ["demo"]}))[0] == 403
    assert (await save(client, headers, {"tab": "defaults", "look": LOOK_LIST}))[0] == 403
    assert (await save(client, headers, {"tab": "nonsense"}))[0] == 403
    assert hub.config.guild_from_id(GUILD_ID).data["disabled"] == []


@pytest.mark.asyncio
async def test_server_tab_needs_a_server(client, hub, demo):
    headers = session_headers(hub, user_id=OWNER_ID, guild_id=None)
    assert (await save(client, headers, {"tab": "server", "disabled": ["demo"]}))[0] == 403


@pytest.mark.asyncio
async def test_manager_saves_server_look_and_switches(client, hub, demo, second):
    headers = session_headers(hub, user_id=MANAGER_ID)
    status, state = await save(client, headers, {"tab": "server", "look": LOOK_LIST, "disabled": ["demo"]})
    assert status == 200
    assert hub.config.guilds[GUILD_ID] == {"look": {"layout": "list"}, "disabled": ["demo"]}
    assert keys(state) == ["second"]


@pytest.mark.asyncio
async def test_server_look_only_save_keeps_games_off(client, hub, demo, second):
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["demo"])
    headers = session_headers(hub, user_id=MANAGER_ID)
    status, state = await save(client, headers, {"tab": "server", "look": LOOK_LIST})
    assert status == 200
    assert hub.config.guilds[GUILD_ID]["disabled"] == ["demo"]
    assert keys(state) == ["second"]


@pytest.mark.asyncio
async def test_server_switch_only_save_keeps_the_look(client, hub, demo):
    await hub.config.guild_from_id(GUILD_ID).look.set({"layout": "list"})
    headers = session_headers(hub, user_id=MANAGER_ID)
    await save(client, headers, {"tab": "server", "disabled": []})
    assert hub.config.guilds[GUILD_ID]["look"] == {"layout": "list"}


@pytest.mark.asyncio
async def test_server_save_keeps_uninstalled_games_off(client, hub, demo):
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["gone"])
    headers = session_headers(hub, user_id=MANAGER_ID)
    await save(client, headers, {"tab": "server", "disabled": ["demo"]})
    assert hub.config.guilds[GUILD_ID]["disabled"] == ["gone", "demo"]


@pytest.mark.asyncio
async def test_bad_server_save_changes_nothing(client, hub, demo):
    headers = session_headers(hub, user_id=MANAGER_ID)
    status, body = await save(client, headers, {"tab": "server", "look": {"layout": "x"}, "disabled": ["demo"]})
    assert status == 400
    assert hub.config.guilds[GUILD_ID] == {"look": {}, "disabled": []}


@pytest.mark.asyncio
async def test_owner_saves_defaults(client, hub, demo):
    headers = session_headers(hub, user_id=OWNER_ID)
    status, state = await save(client, headers, {"tab": "defaults", "look": {**LOOK_LIST, "background": "darker"}})
    assert status == 200
    assert hub.config.globals["look"] == {"layout": "list", "background": "darker"}
    assert (await save(client, session_headers(hub, user_id=MANAGER_ID), {"tab": "defaults", "look": {}}))[0] == 403


@pytest.mark.asyncio
async def test_owner_turns_a_game_off_everywhere(client, hub, demo, second):
    headers = session_headers(hub, user_id=OWNER_ID)
    status, state = await save(client, headers, {"tab": "defaults", "disabled": ["demo", "nope"]})
    assert status == 200 and hub.config.globals["disabled"] == ["demo"]
    assert keys(state) == ["second"]
    assert state["globalSwitches"] == [
        {"key": "second", "name": "Alpha Game", "on": True},
        {"key": "demo", "name": "Demo", "on": False},
    ]
    assert [s["key"] for s in state["switches"]] == ["second"]
    status, state = await save(client, headers, {"tab": "defaults", "look": {"layout": "list"}})
    assert hub.config.globals["disabled"] == ["demo"]
    status, state = await save(client, headers, {"tab": "defaults", "disabled": []})
    assert hub.config.globals["disabled"] == [] and keys(state) == ["second", "demo"]


@pytest.mark.asyncio
async def test_only_the_owner_gets_global_switches(client, hub, demo):
    headers = session_headers(hub, user_id=MANAGER_ID)
    status, state = await menu(client, headers)
    assert state["globalSwitches"] == []
    assert (await save(client, headers, {"tab": "defaults", "disabled": ["demo"]}))[0] == 403
    assert hub.config.globals["disabled"] == []
