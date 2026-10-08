import math

import pytest

from activityhub.common.files import build_id
from activityhub.common.replies import SESSION_EXPIRED
from activityhub.tests.fakes import GUILD_ID, MEMBER_ID, OWNER_ID, session_headers


async def turn_off(hub, key="demo"):
    await hub.config.guild_from_id(GUILD_ID).disabled.set([key])


@pytest.mark.asyncio
async def test_game_page_gets_base_and_import_map(client, server, demo):
    resp = await client.get("/games/demo/")
    text = await resp.text()
    assert resp.status == 200 and resp.headers["Cache-Control"] == "no-cache"
    assert f'<base href="/games/demo/{build_id(demo.web_dir)}/" />' in text
    hub_root = f"/hub/{server.hub_build()}/"
    imports = f'{{"activityhub": "{hub_root}sdk.js", "activityhub/": "{hub_root}"}}'
    assert f'<script type="importmap">{{"imports": {imports}}}</script>' in text
    assert text.index("<base") < text.index('<meta charset="utf-8" />')
    assert '<script type="module" src="game.js"></script>' in text


@pytest.mark.asyncio
async def test_unknown_games_are_404(client, demo):
    assert (await client.get("/games/nope/b/game.js")).status == 404
    assert (await client.post("/games/nope/api/echo", json={})).status == 404
    assert (await client.post("/games/nope/")).status == 404


@pytest.mark.asyncio
async def test_page_of_an_unloaded_game_leads_back_to_the_menu(client, demo):
    # The menu may still list a game whose cog unloaded a moment ago, so its frame needs a way out
    resp = await client.get("/games/nope/?frame_id=f")
    text = await resp.text()
    assert resp.status == 404 and "isn&#x27;t installed" in text
    assert 'id="back"' in text and '"activityhub": "/hub/' in text
    # A frame that reloads on another address under the game, like a router path, gets the same way out
    resp = await client.get("/games/nope/b/play", headers={"Sec-Fetch-Dest": "iframe"})
    text = await resp.text()
    assert resp.status == 404 and "isn&#x27;t installed" in text and 'id="back"' in text
    resp = await client.get("/games/nope/b/game.js", headers={"Sec-Fetch-Dest": "script"})
    assert resp.status == 404 and "installed" not in await resp.text()


@pytest.mark.asyncio
async def test_page_of_a_turned_off_game_says_so(client, hub, demo):
    await turn_off(hub)
    resp = await client.get(f"/games/demo/?frame_id=f&guild_id={GUILD_ID}")
    text = await resp.text()
    assert resp.status == 403 and "turned off" in text
    assert 'id="back"' in text
    assert 'import { backToMenu } from "activityhub"' in text
    assert '"activityhub": "/hub/' in text
    assert (await client.get("/games/demo/?guild_id=999")).status == 200
    assert (await client.get("/games/demo/?guild_id=abc")).status == 200


@pytest.mark.asyncio
async def test_page_and_files_are_read_only(client, demo):
    assert (await client.post("/games/demo/")).status == 405
    assert (await client.post("/games/demo/b/game.js")).status == 405


@pytest.mark.asyncio
async def test_game_files_are_served_under_any_build(client, demo):
    js = await client.get("/games/demo/anything/game.js")
    assert js.status == 200 and js.headers["Content-Type"].startswith("text/javascript")
    svg = await client.get("/games/demo/x/icon.svg")
    assert svg.headers["Content-Type"].startswith("image/svg+xml")


@pytest.mark.asyncio
async def test_game_files_cannot_escape_web_dir(client, demo):
    for path in ("/games/demo/b/..%2Fsecret.txt", "/games/demo/b/..%5Csecret.txt", "/games/demo/b/", "/games/demo/b/x"):
        resp = await client.get(path)
        assert resp.status == 404
        assert "SECRET" not in await resp.text()


@pytest.mark.asyncio
async def test_hidden_files_are_never_served(client, demo):
    (demo.web_dir / ".env").write_text("TOKEN=SECRET", encoding="utf-8")
    (demo.web_dir / ".git").mkdir()
    (demo.web_dir / ".git" / "config").write_text("SECRET", encoding="utf-8")
    for path in ("/games/demo/b/.env", "/games/demo/b/.git/config", "/games/demo/b/x/..%2F.env"):
        resp = await client.get(path)
        assert resp.status == 404
        assert "SECRET" not in await resp.text()
    assert (await client.get("/games/demo/b/game.js")).status == 200


@pytest.mark.asyncio
async def test_a_page_that_cant_be_read_leads_back_to_the_menu(client, demo, caplog):
    # A bundler rebuilding the page can leave index.html missing or half written for a moment
    index = demo.web_dir / "index.html"
    index.unlink()
    resp = await client.get("/games/demo/")
    text = await resp.text()
    assert resp.status == 500 and "Something went wrong." in text and 'id="back"' in text
    assert "Couldn't read index.html of demo" in caplog.text
    index.write_bytes("<!doctype html><p>caf\u00e9</p>".encode("cp1252"))
    resp = await client.get("/games/demo/")
    assert resp.status == 500 and 'id="back"' in await resp.text()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [{"Sec-Fetch-Dest": "iframe"}, {"Sec-Fetch-Dest": "document"}, {"Accept": "text/html,application/xhtml+xml"}],
)
async def test_the_frame_going_to_a_missing_page_leads_back_to_the_menu(client, demo, caplog, headers):
    # A router path, a reload after pushState, or an href="#" link (which leads to the build folder itself)
    for path in ("/games/demo/b/play", "/games/demo/b/"):
        resp = await client.get(path, headers=headers)
        text = await resp.text()
        assert resp.status == 404 and "This page isn&#x27;t part of the game." in text
        assert 'id="back"' in text and '"activityhub": "/hub/' in text
        assert f"demo: the game frame went to {path!r}, which isn't a file in web_dir" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {"Sec-Fetch-Dest": "script"}, {"Sec-Fetch-Dest": "empty", "Accept": "*/*"}])
async def test_a_missing_file_for_the_page_is_a_plain_404(client, demo, caplog, headers):
    resp = await client.get("/games/demo/b/missing.js", headers=headers)
    assert resp.status == 404 and "Back to the menu" not in await resp.text()
    assert "game frame" not in caplog.text


@pytest.mark.asyncio
async def test_action_needs_a_session(client, demo):
    resp = await client.post("/games/demo/api/echo", json={})
    assert resp.status == 401


@pytest.mark.asyncio
async def test_action_gets_the_proven_player(client, hub, demo):
    resp = await client.post("/games/demo/api/echo", json={"n": 1}, headers=session_headers(hub))
    assert resp.status == 200
    assert await resp.json() == {"user": MEMBER_ID, "guild": GUILD_ID, "instance": "i-1", "data": {"n": 1}}


@pytest.mark.asyncio
async def test_turned_off_is_checked_before_the_action_name(client, hub, demo):
    await turn_off(hub)
    headers = session_headers(hub)
    assert (await client.post("/games/demo/api/echo", json={}, headers=headers)).status == 403
    assert (await client.post("/games/demo/api/nope", json={}, headers=headers)).status == 403


@pytest.mark.asyncio
async def test_dm_players_ignore_server_switches(client, hub, demo):
    await turn_off(hub)
    resp = await client.post("/games/demo/api/echo", json={}, headers=session_headers(hub, guild_id=None))
    assert resp.status == 200 and (await resp.json())["guild"] is None


@pytest.mark.asyncio
async def test_unknown_action_and_bad_bodies(client, hub, demo):
    headers = session_headers(hub)
    nope = await client.post("/games/demo/api/nodata", json={}, headers=headers)
    assert nope.status == 404 and await nope.json() == {"error": "That action doesn't exist: nodata."}
    assert (await client.post("/games/demo/api/echo", json=[1], headers=headers)).status == 400
    assert (await client.post("/games/demo/api/echo", data="x", headers=headers)).status == 400
    assert (await client.get("/games/demo/api/echo", headers=headers)).status == 405


@pytest.mark.asyncio
async def test_action_results(client, hub, demo, caplog):
    headers = session_headers(hub)

    async def call(name):
        resp = await client.post(f"/games/demo/api/{name}", json={}, headers=headers)
        return resp.status, await resp.json()

    assert await call("none") == (200, {})
    assert await call("refuse") == (400, {"error": "Not today."})
    assert await call("crash") == (500, {"error": "Something went wrong."})
    assert await call("list") == (500, {"error": "Something went wrong."})
    assert await call("weird") == (500, {"error": "Something went wrong."})
    assert "action broke" in caplog.text


@pytest.mark.asyncio
async def test_an_error_must_be_words(client, hub, demo, caplog):
    headers = session_headers(hub)

    async def give(result):
        demo.result = result
        resp = await client.post("/games/demo/api/give", json={}, headers=headers)
        return resp.status, await resp.json()

    # A reply built as {"error": problem_or_none} is a normal reply when there is no problem
    assert await give({"error": None, "x": 1}) == (200, {"error": None, "x": 1})
    # Anything else would show the player a Python repr, or an error with no words
    assert await give({"error": ""}) == (500, {"error": "Something went wrong."})
    assert await give({"error": "  "}) == (500, {"error": "Something went wrong."})
    assert "Action demo.give returned an empty error: '  '" in caplog.text
    assert await give({"error": {"code": 1}}) == (500, {"error": "Something went wrong."})
    assert await give({"error": 0}) == (500, {"error": "Something went wrong."})
    assert "Action demo.give returned an error that isn't text: {'code': 1}" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("number", [math.nan, math.inf, -math.inf])
async def test_replies_with_numbers_json_cant_hold_are_refused(client, hub, demo, caplog, number):
    # Python would write NaN or Infinity, and the page couldn't read the reply
    demo.result = {"ratio": number}
    resp = await client.post("/games/demo/api/give", json={}, headers=session_headers(hub))
    assert resp.status == 500 and await resp.json() == {"error": "Something went wrong."}
    assert "Action demo.give returned something that isn't JSON" in caplog.text


@pytest.mark.asyncio
async def test_the_bot_owner_sees_why_something_went_wrong(client, hub, demo):
    owner, member = session_headers(hub, user_id=OWNER_ID), session_headers(hub)

    async def call(name, headers, result=None):
        demo.result = result
        resp = await client.post(f"/games/demo/api/{name}", json={}, headers=headers)
        assert resp.status == 500
        return (await resp.json())["error"]

    def owner_sees(reason):
        return (
            f"Something went wrong. (Only you see this, as the bot owner: {reason}. "
            "The bot's log has the full error.)"
        )

    assert await call("crash", owner) == owner_sees("RuntimeError: action broke")
    assert await call("list", owner) == owner_sees("returned list instead of a dict")
    assert await call("weird", owner) == owner_sees(
        "returned something that isn't JSON: Object of type object is not JSON serializable"
    )
    assert await call("give", owner, {"error": {"code": 1}}) == owner_sees(
        "returned an error that isn't text: {'code': 1}"
    )
    # Every other player sees only the plain message
    for name in ("crash", "list", "weird"):
        assert await call(name, member) == "Something went wrong."
    assert await call("give", member, {"error": {"code": 1}}) == "Something went wrong."


@pytest.mark.asyncio
async def test_the_bot_owner_sees_why_a_raw_route_went_wrong(client, hub, demo):
    owner, member = session_headers(hub, user_id=OWNER_ID), session_headers(hub)
    note = "Only you see this, as the bot owner: {}. The bot's log has the full error."

    async def get(path, headers):
        resp = await client.get(f"/games/demo/raw/{path}", headers=headers)
        assert resp.status == 500
        return (await resp.json())["error"]

    assert await get("crash", owner) == f"Something went wrong. ({note.format('RuntimeError: raw broke')})"
    not_a_response = note.format("returned dict, not a response")
    assert await get("notaresponse", owner) == f"Something went wrong. ({not_a_response})"
    for path in ("crash", "notaresponse"):
        assert await get(path, member) == "Something went wrong."
        assert await get(path, {}) == "Something went wrong."


@pytest.mark.asyncio
async def test_bodies_over_one_megabyte_are_refused(client, hub, demo):
    headers = {**session_headers(hub), "Content-Type": "application/json"}
    resp = await client.post("/games/demo/api/echo", data=b"x" * (1024 * 1024 + 1), headers=headers)
    assert resp.status == 413


@pytest.mark.asyncio
async def test_raw_routes_get_the_player_or_none(client, hub, demo):
    with_session = await client.get("/games/demo/raw/hello", headers=session_headers(hub))
    assert await with_session.json() == {"user": MEMBER_ID}
    without = await client.get("/games/demo/raw/hello")
    assert await without.json() == {"user": None}


@pytest.mark.asyncio
async def test_raw_routes_answer_an_expired_login_themselves(client, demo):
    # The hub forgot this login (a restart, a reload, or 12 hours). The header tells hub.fetch to log in again
    resp = await client.get("/games/demo/raw/hello", headers={"Authorization": "Bearer unknown"})
    assert resp.status == 401 and resp.headers["X-ActivityHub"] == "session-expired"
    assert await resp.json() == {"error": SESSION_EXPIRED}
    assert demo.events == []
    # Only a request with no login of the hub's reaches the handler with ctx None
    for headers in ({}, {"Authorization": "Basic dXNlcjpwYXNz"}):
        resp = await client.get("/games/demo/raw/hello", headers=headers)
        assert resp.status == 200 and await resp.json() == {"user": None}
        assert "X-ActivityHub" not in resp.headers
    assert demo.events == [("hello", None), ("hello", None)]


@pytest.mark.asyncio
async def test_raw_routes_match_method_and_path(client, demo):
    assert (await client.get("/games/demo/raw/nope")).status == 404
    assert (await client.post("/games/demo/raw/hello")).status == 404


@pytest.mark.asyncio
async def test_raw_routes_refuse_turned_off_sessions(client, hub, demo):
    await turn_off(hub)
    assert (await client.get("/games/demo/raw/hello", headers=session_headers(hub))).status == 403
    assert (await client.get("/games/demo/raw/hello")).status == 200


@pytest.mark.asyncio
async def test_raw_route_errors(client, demo, caplog):
    teapot = await client.post("/games/demo/raw/teapot")
    assert teapot.status == 403 and await teapot.text() == "no tea"
    assert (await client.get("/games/demo/raw/crash")).status == 500
    assert (await client.get("/games/demo/raw/notaresponse")).status == 500
    assert "raw broke" in caplog.text


@pytest.mark.asyncio
async def test_unloaded_games_disappear(client, hub, demo):
    hub.registry.remove(demo)
    assert (await client.get("/games/demo/")).status == 404
    assert (await client.post("/games/demo/api/echo", json={}, headers=session_headers(hub))).status == 404
