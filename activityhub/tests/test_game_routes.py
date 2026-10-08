import pytest

from activityhub.common.files import build_id
from activityhub.tests.fakes import GUILD_ID, MEMBER_ID, session_headers


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
    assert (await client.post("/games/demo/api/nope", json={}, headers=headers)).status == 404
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
