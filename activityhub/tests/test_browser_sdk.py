import asyncio
import shutil

import pytest
from selenium.webdriver.common.by import By

from activityhub.common.server import HUB_WEB_DIR
from activityhub.tests.browser import (
    DISCORD_QUERY,
    TEST_HOST_PAGE,
    LiveHub,
    fresh,
    hub_web_copy,
    start_chrome,
    wait_for,
    wait_for_console,
)
from activityhub.tests.fakes import GUILD_ID, MEMBER_ID, DemoCog, make_hub, register, write_demo_web

# A game page that starts its own Discord toolkit, the real one, instead of using hub.discord
OWN_SDK_JS = """import { DiscordSDK } from "./discord-sdk.js";
new DiscordSDK("1000").ready();
document.getElementById("status").textContent = "started";
"""


@pytest.fixture(scope="module")
def driver():
    chrome = start_chrome()
    if chrome is None:
        pytest.skip("Chrome can't start on this machine")
    yield chrome
    chrome.quit()


@pytest.fixture
def live(tmp_path, driver):
    hub = make_hub()
    hub.demo = DemoCog(write_demo_web(tmp_path / "demo"))
    register(hub, hub.demo)
    register(hub, DemoCog(write_demo_web(tmp_path / "quiet"), key="quiet", cog_name="Quiet", with_socket=False))
    own = write_demo_web(tmp_path / "own")
    (own / "game.js").write_text(OWN_SDK_JS, encoding="utf-8")
    shutil.copy(HUB_WEB_DIR / "vendor" / "discord-sdk.js", own / "discord-sdk.js")
    register(hub, DemoCog(own, key="own", cog_name="Own"))
    server = LiveHub(hub, hub_web_copy(tmp_path, index=TEST_HOST_PAGE))
    server.start()
    fresh(driver, server)
    yield server
    server.stop()


def open_host(driver, live, query=DISCORD_QUERY):
    driver.get(f"{live.url}/{query}")
    return wait_for(driver, "document.body.dataset.login")


def open_game(driver, key="demo"):
    """Open a game in the host that is already showing, and switch into its frame"""
    driver.execute_script(f"window.testHost.openGame('{key}')")
    wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "window.demo && window.demo.done")


def open_game_in_host(driver, live, key="demo"):
    assert open_host(driver, live) == "online"
    open_game(driver, key)


def in_game(driver, script: str):
    """
    Run JavaScript in the game frame, with hub from connect() and HubError, and return what it passes to done().
    Must be called from inside the game frame
    """
    return driver.execute_async_script(
        "const done = arguments[0];"
        "import('activityhub').then(async ({ connect, HubError }) => {"
        "  const hub = await connect();"
        f"  {script}"
        "}).catch((e) => done(`failed: ${e.name}: ${e.message}`));"
    )


def test_game_opened_directly_in_a_browser_is_offline(driver, live):
    driver.get(f"{live.url}/games/demo/")
    wait_for(driver, "window.demo && window.demo.done")
    assert driver.execute_script("return [window.demo.offline, window.demo.player]") == [True, None]
    driver.find_element(By.ID, "back").click()
    wait_for(driver, "location.pathname === '/'")


def test_host_logs_in_once(driver, live):
    assert open_host(driver, live) == "online"
    calls = driver.execute_script("return window.fakeDiscord")
    assert calls == {"created": 1, "authorize": 1, "authenticate": 1}
    player = driver.execute_script("return window.testHost.login.player")
    assert player["id"] == str(MEMBER_ID) and player["guildId"] == str(GUILD_ID)


def test_host_outside_discord_is_offline(driver, live):
    assert open_host(driver, live, query="") == "offline"
    assert driver.execute_script("return window.fakeDiscord === undefined")


def test_game_in_the_frame_borrows_the_login(driver, live):
    open_game_in_host(driver, live)
    demo = driver.execute_script("return window.demo")
    assert demo["offline"] is False and demo.get("error") is None
    assert demo["player"]["guildId"] == str(GUILD_ID)
    assert demo["echo"] == {"user": MEMBER_ID, "guild": GUILD_ID, "instance": "i-1", "data": {"n": 1}}
    wait_for(driver, "window.demo.messages.length >= 2")
    messages = driver.execute_script("return window.demo.messages")
    assert messages[0] == {"joined": MEMBER_ID, "peers": 0}
    assert messages[1] == {"echo": {"ping": 1}}
    assert driver.execute_script("return window.fakeDiscord === undefined")
    assert driver.execute_script("return window.parent.fakeDiscord.created") == 1


def test_back_to_menu_closes_the_game_frame(driver, live):
    open_game_in_host(driver, live)
    driver.find_element(By.ID, "back").click()
    driver.switch_to.default_content()
    wait_for(driver, "document.body.dataset.closed === '1'")
    assert driver.find_elements(By.ID, "game-frame") == []
    assert driver.execute_script("return document.body.classList.contains('playing')") is False


def test_a_missing_page_in_the_frame_leads_back_to_the_menu(driver, live):
    # A router path is gone after a reload, and a bare 404 would leave the player stuck in the frame
    open_game_in_host(driver, live)
    driver.execute_script("setTimeout(() => { history.pushState({}, '', 'play'); location.reload(); }, 0)")
    wait_for(driver, "document.body.innerText.includes('part of the game.')")
    driver.find_element(By.ID, "back").click()
    driver.switch_to.default_content()
    wait_for(driver, "document.body.dataset.closed === '1'")
    assert driver.find_elements(By.ID, "game-frame") == []


def test_game_page_alone_in_discord_goes_to_the_menu(driver, live):
    driver.get(f"{live.url}/games/demo/{DISCORD_QUERY}")
    wait_for(driver, "location.pathname === '/' && document.body.dataset.login === 'online'")
    assert driver.execute_script("return location.search") == DISCORD_QUERY
    assert driver.execute_script("return window.fakeDiscord.created") == 1


def test_an_expired_login_is_renewed_without_leaving_the_game(driver, live):
    # A bot restart or an ActivityHub reload forgets every login, while the menu's Discord connection is still good
    assert open_host(driver, live) == "online"
    live.hub.sessions.sessions.clear()
    driver.execute_script("window.testHost.openGame('demo')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "window.demo && window.demo.done")
    demo = driver.execute_script("return window.demo")
    assert demo.get("error") is None
    assert demo["echo"] == {"user": MEMBER_ID, "guild": GUILD_ID, "instance": "i-1", "data": {"n": 1}}
    wait_for(driver, "window.demo.messages.length >= 2")
    driver.switch_to.default_content()
    assert driver.execute_script("return window.fakeDiscord") == {"created": 1, "authorize": 2, "authenticate": 1}
    assert driver.execute_script("return document.body.dataset.expired") is None
    assert len(driver.find_elements(By.ID, "game-frame")) == 1
    assert len(live.hub.sessions.sessions) == 1


def test_a_live_connection_logs_in_again(driver, live):
    open_game_in_host(driver, live)
    live.hub.sessions.sessions.clear()
    assert in_game(driver, "const conn = await hub.socket(); conn.close(); done('open');") == "open"
    assert driver.execute_script("return window.parent.fakeDiscord.authorize") == 2


def test_a_raw_route_logs_in_again(driver, live):
    open_game_in_host(driver, live)
    live.hub.sessions.sessions.clear()
    reply = in_game(driver, "const resp = await hub.fetch('hello'); done([resp.status, await resp.json()]);")
    assert reply == [200, {"user": MEMBER_ID}]
    assert driver.execute_script("return window.parent.fakeDiscord.authorize") == 2
    # The route only ever saw the player, never the expired login as a request with no login
    hellos = [event for event in live.hub.demo.events if event[0] == "hello"]
    assert hellos == [("hello", MEMBER_ID)]


def test_requests_refused_together_share_one_login(driver, live):
    open_game_in_host(driver, live)
    live.hub.sessions.sessions.clear()
    replies = in_game(
        driver,
        "const replies = await Promise.all([1, 2, 3].map((n) => hub.api('echo', { n })));"
        "done(replies.map((reply) => reply.data.n));",
    )
    assert replies == [1, 2, 3]
    assert driver.execute_script("return window.parent.fakeDiscord.authorize") == 2
    assert len(live.hub.sessions.sessions) == 1


def test_when_discord_refuses_a_fresh_login_the_player_goes_back_to_the_menu(driver, live):
    open_game_in_host(driver, live)
    driver.execute_script("window.parent.fakeDiscord.failAuthorize = true")
    live.hub.sessions.sessions.clear()
    # The frame goes away while this runs, so nothing waits for it
    driver.execute_script("import('activityhub').then(({ connect }) => connect()).then((hub) => hub.api('echo'))")
    driver.switch_to.default_content()
    wait_for(driver, "document.body.dataset.expired === '1'")
    assert driver.find_elements(By.ID, "game-frame") == []


def test_when_the_retry_is_refused_too_the_player_goes_back_to_the_menu(driver, live):
    open_game_in_host(driver, live)
    # Logging in works, but the bot forgets each login at once
    live.server.request_context = lambda request: None
    driver.execute_script("import('activityhub').then(({ connect }) => connect()).then((hub) => hub.api('echo'))")
    driver.switch_to.default_content()
    wait_for(driver, "document.body.dataset.expired === '1'")
    assert driver.find_elements(By.ID, "game-frame") == []
    assert driver.execute_script("return window.fakeDiscord.authorize") == 2


def test_a_live_connection_to_a_game_without_socket_says_how_to_fix_it(driver, live):
    open_game_in_host(driver, live, key="quiet")
    caught = in_game(driver, "hub.socket().catch((e) => done([e instanceof HubError, e.status, e.message]));")
    assert caught == [
        True,
        4004,
        'This game has no live connection. Add "socket" to activityhub_game() and reload the cog.',
    ]


def test_a_reply_that_isnt_json_is_an_error(driver, live):
    # Something other than the bot, like a proxy's error page, answering with 200
    open_game_in_host(driver, live)
    caught = in_game(
        driver,
        "window.fetch = async () => new Response('<!doctype html><p>Proxy page</p>', { status: 200 });"
        "hub.api('echo').then(() => done('resolved'), (e) => done([e instanceof HubError, e.status, e.message]));",
    )
    assert caught == [True, 200, "The bot's reply wasn't valid JSON."]


def test_a_live_message_json_cant_send_is_refused(driver, live):
    open_game_in_host(driver, live)
    caught = in_game(
        driver,
        """
        const conn = await hub.socket();
        const echoed = new Promise((resolve) => conn.on((data) => data.echo && resolve(data)));
        const errors = [];
        for (const value of [undefined, () => 1]) {
          try {
            conn.send(value);
          } catch (e) {
            errors.push([e.name, e.message]);
          }
        }
        conn.send({ ok: 1 });
        done([errors, await echoed]);
        """,
    )
    needs = "conn.send() needs a JSON value (an object, array, string, number, boolean or null), got"
    assert caught == [[["TypeError", f"{needs} undefined"], ["TypeError", f"{needs} function"]], {"echo": {"ok": 1}}]


# Opens a live connection in the game frame and records everything that happens to it in window.live
WATCH_LIVE = """
    const conn = await hub.socket();
    window.live = { conn, events: [], messages: [] };
    conn.on((data) => window.live.messages.push(data));
    conn.onReconnecting((code) => window.live.events.push(["reconnecting", code]));
    conn.onReconnected(() => window.live.events.push(["reconnected"]));
    conn.onClose((code) => window.live.events.push(["closed", code]));
    done(true);
"""


def on_server(live, coro):
    """Run something on the live hub's own thread, the way the bot would"""
    return asyncio.run_coroutine_threadsafe(coro, live.loop).result(5)


def test_a_dropped_live_connection_reconnects_by_itself(driver, live):
    open_game_in_host(driver, live)
    assert in_game(driver, WATCH_LIVE) is True
    # What reloading ActivityHub or the game does to every live connection
    on_server(live, live.server.rooms.close_all())
    wait_for(driver, "window.live.events.length >= 2")
    assert driver.execute_script("return window.live.events") == [["reconnecting", 1001], ["reconnected"]]
    # The same conn works again, and the game's join ran for the new connection
    assert driver.execute_script("return window.live.conn.send({ n: 2 })") is True
    wait_for(driver, "window.live.messages.some((data) => data.echo && data.echo.n === 2)")
    assert {"joined": MEMBER_ID, "peers": 1} in driver.execute_script("return window.live.messages")


def test_a_reconnect_after_an_activityhub_reload_logs_in_again(driver, live):
    open_game_in_host(driver, live)
    assert in_game(driver, WATCH_LIVE) is True
    # A reload of ActivityHub forgets every login as well as closing every live connection
    live.hub.sessions.sessions.clear()
    on_server(live, live.server.rooms.close_all())
    wait_for(driver, "window.live.events.length >= 2")
    assert driver.execute_script("return window.live.events") == [["reconnecting", 1001], ["reconnected"]]
    assert driver.execute_script("return window.parent.fakeDiscord.authorize") == 2


def test_a_live_connection_closed_for_good_does_not_reconnect(driver, live):
    open_game_in_host(driver, live)
    assert in_game(driver, WATCH_LIVE) is True
    # The game was turned off everywhere, which reconnecting can't fix
    on_server(live, live.server.rooms.close_games(["demo"]))
    wait_for(driver, "window.live.events.length >= 1")
    assert driver.execute_script("return window.live.events") == [["closed", 4003]]
    assert driver.execute_script("return window.live.conn.send({ n: 3 })") is False


def test_closing_a_live_connection_ends_it_once(driver, live):
    open_game_in_host(driver, live)
    assert in_game(driver, WATCH_LIVE) is True
    driver.execute_script("window.live.conn.close()")
    wait_for(driver, "window.live.events.length >= 1")
    driver.execute_script("window.live.conn.close()")
    assert driver.execute_script("return window.live.events") == [["closed", 1000]]
    assert driver.execute_script("return window.live.conn.send({ n: 4 })") is False


def test_listeners_a_game_added_to_discord_go_when_it_closes(driver, live):
    # Discord's toolkit belongs to the menu and outlives the game. A listener left behind would still run, and
    # one that throws, from a page that's gone, would stop the reopened game's own listener
    assert open_host(driver, live) == "online"
    driver.execute_script("window.heard = []")
    subscribe = (
        "await hub.discord.subscribe('SPEAKING_START', (data) => window.parent.heard.push(['open %d', data]));"
        # ready() runs on the toolkit itself, whose private state a stand-in object couldn't reach
        "await hub.discord.ready();"
        "done(window.parent.fakeDiscordBus.count('SPEAKING_START'));"
    )
    open_game(driver)
    assert in_game(driver, subscribe % 1) == 1
    driver.switch_to.default_content()
    driver.execute_script("window.testHost.closeGame()")
    wait_for(driver, "window.fakeDiscordBus.count('SPEAKING_START') === 0")
    open_game(driver)
    assert in_game(driver, subscribe % 2) == 1
    driver.switch_to.default_content()
    driver.execute_script("window.fakeDiscordBus.emit('SPEAKING_START', { user_id: '2' })")
    assert driver.execute_script("return window.heard") == [["open 2", {"user_id": "2"}]]


def test_a_listener_the_game_removed_itself_is_left_alone(driver, live):
    open_game_in_host(driver, live)
    script = """
        const listener = () => {};
        await hub.discord.subscribe('SPEAKING_START', listener);
        await hub.discord.unsubscribe('SPEAKING_START', listener);
        done(window.parent.fakeDiscordBus.count('SPEAKING_START'));
    """
    assert in_game(driver, script) == 0
    driver.switch_to.default_content()
    driver.execute_script("""
        const sdk = window.testHost.sdk;
        const real = sdk.unsubscribe.bind(sdk);
        window.unsubscribed = 0;
        sdk.unsubscribe = (...args) => { window.unsubscribed += 1; return real(...args); };
        window.testHost.closeGame();
        """)
    assert driver.execute_script("return window.unsubscribed") == 0


def test_a_game_making_its_own_discord_sdk_is_told_in_the_console(driver, live):
    assert open_host(driver, live) == "online"
    driver.execute_script("window.testHost.openGame('own')")
    lines = wait_for_console(driver, "this game created its own DiscordSDK")
    line = next(line for line in lines if "own DiscordSDK" in line)
    assert "Use hub.discord from connect() instead." in line


def test_a_link_out_of_the_game_goes_back_to_the_menu(driver, live):
    # A Back link to / would otherwise load a second, offline menu inside the game frame
    open_game_in_host(driver, live)
    driver.execute_script(
        "const link = document.createElement('a'); link.href = '/'; document.body.append(link); link.click();"
    )
    driver.switch_to.default_content()
    wait_for(driver, "document.body.dataset.closed === '1'")
    assert driver.find_elements(By.ID, "game-frame") == []
    lines = wait_for_console(driver, "the game left its page")
    assert any("Use backToMenu() to go back to the menu." in line for line in lines)


def test_only_a_handshake_from_the_games_own_page_is_reported(driver, live):
    open_game_in_host(driver, live)
    driver.switch_to.default_content()
    driver.execute_script("""
        const frame = document.getElementById("game-frame");
        const send = (data) => window.dispatchEvent(new MessageEvent("message", { data, source: frame.contentWindow }));
        // A game's own messages to the menu, which look nothing like the toolkit's
        send([0, "hello"]);
        send([0, null]);
        send({ frame_id: "f" });
        send([1, { frame_id: "f" }]);
        // The menu loaded inside the frame by a link sends one too, but that is the link's fault
        frame.contentWindow.history.pushState({}, "", "/");
        send([0, { frame_id: "f" }]);
        frame.contentWindow.history.pushState({}, "", "/games/demo/");
        send([0, { frame_id: "f" }]);
        console.warn("all sent");
        """)
    lines = wait_for_console(driver, "all sent")
    assert len([line for line in lines if "own DiscordSDK" in line]) == 1
    assert not any("Uncaught" in line for line in lines)
