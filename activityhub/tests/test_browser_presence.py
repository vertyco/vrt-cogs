import asyncio
import time

import pytest

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
from activityhub.tests.fakes import MANAGER_ID, MEMBER_ID, DemoCog, make_hub, register, write_demo_web

EMOJI = "\U0001f600"


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
    register(hub, DemoCog(write_demo_web(tmp_path / "demo")))
    server = LiveHub(hub, hub_web_copy(tmp_path, index=TEST_HOST_PAGE))
    server.start()
    fresh(driver, server)
    yield server
    server.stop()


def me(live):
    window = live.server.presence.windows.get("i-1")
    return window.people.get(MEMBER_ID) if window else None


def state(live):
    """What the bot has for the player, or None while it has nobody listed"""
    person = me(live)
    return (person.where, person.status, person.data, person.busy) if person else None


def eventually(check, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError("condition never became true")


def open_host(driver, live):
    driver.get(f"{live.url}/{DISCORD_QUERY}")
    assert wait_for(driver, "document.body.dataset.login") == "online"


def close_links(live, code, restart=False):
    """Close every menu link from the bot's side. A restart also makes the bot forget its people and every login"""

    async def close():
        for conn in live.server.presence.links():
            await conn.end(code)
        if restart:
            live.server.presence.stop()
            live.hub.sessions.sessions.clear()

    asyncio.run_coroutine_threadsafe(close(), live.loop).result(5)


def hide_page(driver, hidden):
    driver.execute_script(
        "Object.defineProperty(document, 'hidden', {configurable: true, get: () => arguments[0]});"
        "document.dispatchEvent(new Event('visibilitychange'));",
        hidden,
    )


def test_the_menu_link_says_where_the_player_is(driver, live):
    open_host(driver, live)
    eventually(lambda: me(live) is not None and me(live).where is None)
    driver.execute_script("window.testHost.openGame('demo')")
    eventually(lambda: me(live).where == "demo")
    driver.execute_script("window.testHost.setStatus('Clicking', {n: 3}); window.testHost.setBusy(true)")
    eventually(lambda: (me(live).status, me(live).data, me(live).busy) == ("Clicking", {"n": 3}, True))
    driver.execute_script("window.testHost.closeGame()")
    eventually(lambda: (me(live).where, me(live).status, me(live).busy) == (None, "", False))


def test_a_status_is_cut_by_whole_characters(driver, live):
    open_host(driver, live)
    eventually(lambda: me(live) is not None)
    # The 60th character is an emoji, which JavaScript counts as two units: it stays whole
    driver.execute_script("window.testHost.setStatus('a'.repeat(59) + '\\u{1F600}zzz')")
    eventually(lambda: me(live).status == "a" * 59 + EMOJI)
    # The 61st is one, so it goes entirely rather than leaving half of it
    driver.execute_script("window.testHost.setStatus('a'.repeat(60) + '\\u{1F600}')")
    eventually(lambda: me(live).status == "a" * 60)
    driver.execute_script("window.testHost.setStatus(null)")
    eventually(lambda: me(live).status == "")


def test_status_data_is_a_checked_copy(driver, live):
    open_host(driver, live)
    result = driver.execute_script(
        r"""
        const host = window.testHost;
        const data = () => host.presence.state.data;
        const out = {};
        const game = { n: 1 };
        host.setStatus('x', game);
        // The game changes its object after the call
        game.big = 'y'.repeat(2000);
        out.copy = data();
        host.setStatus('x', { t: '\ud83d' });
        out.halfEmoji = data();
        host.setStatus('x', { t: '\u{1F600}' });
        out.emoji = data();
        host.setStatus('x', { t: '\\ud83d' });
        out.textLookingLikeAnEscape = data();
        host.setStatus('x', { t: 'y'.repeat(2000) });
        out.tooBig = data();
        const loop = {};
        loop.loop = loop;
        host.setStatus('x', loop);
        out.loop = data();
        host.setStatus('x', () => {});
        out.notJson = data();
        return out;
        """
    )
    assert result == {
        "copy": {"n": 1},
        "halfEmoji": None,
        "emoji": {"t": EMOJI},
        "textLookingLikeAnEscape": {"t": "\\ud83d"},
        "tooBig": None,
        "loop": None,
        "notJson": None,
    }


def test_the_page_gets_the_people_list(driver, live):
    open_host(driver, live)
    eventually(lambda: me(live) is not None)
    live.add_person(MANAGER_ID, where="demo", status="Clicking")
    names = wait_for(
        driver,
        "window.testHost.presence.people.length === 2"
        " && window.testHost.presence.view('demo').map((p) => [p.name, p.you, p.here])",
    )
    assert names == [["Member", True, False], ["Manager", False, True]]


def test_a_reconnected_menu_link_sends_everything_again(driver, live):
    open_host(driver, live)
    eventually(lambda: me(live) is not None)
    driver.execute_script("window.testHost.openGame('demo')")
    driver.execute_script("window.testHost.setStatus('Clicking', {n: 3}); window.testHost.setBusy(true)")
    wanted = ("demo", "Clicking", {"n": 3}, True)
    eventually(lambda: state(live) == wanted)
    before = me(live)
    close_links(live, 1001, restart=True)
    # The bot has forgotten the player, and the page has to log in again before it can say where they are
    eventually(lambda: state(live) == wanted and me(live) is not before, timeout=20)


def test_the_page_says_when_discord_hides_the_activity(driver, live):
    open_host(driver, live)
    eventually(lambda: me(live) is not None)
    hide_page(driver, False)
    eventually(lambda: me(live).away is False)
    hide_page(driver, True)
    eventually(lambda: me(live).away is True)
    hide_page(driver, False)
    eventually(lambda: me(live).away is False)


def test_the_people_list_empties_when_the_menu_link_closes_for_good(driver, live):
    open_host(driver, live)
    eventually(lambda: me(live) is not None)
    live.add_person(MANAGER_ID, where="demo")
    wait_for(driver, "window.testHost.presence.people.length === 2")
    driver.execute_script("window.heard = []; window.testHost.presence.listen((p) => window.heard.push(p.length))")
    # A code the page doesn't reconnect after
    close_links(live, 1008)
    wait_for(driver, "window.testHost.presence.people.length === 0")
    # The last thing the listener heard, after any list that was still on its way, is that nobody is here
    assert driver.execute_script("return window.heard.at(-1)") == 0
    assert driver.execute_script("return window.testHost.presence.conn") is None


def test_a_refused_login_does_not_end_the_session(driver, live):
    open_host(driver, live)
    eventually(lambda: me(live) is not None)

    async def refuse(code):
        return None

    live.server.exchange_code = refuse
    close_links(live, 1001, restart=True)
    seen = wait_for_console(driver, "the menu link closed")
    assert any("couldn't log in again" in line for line in seen)
    assert driver.execute_script("return document.body.dataset.expired") is None
    # The first wait was 15 s, and the next try would wait twice that
    assert driver.execute_script("return window.testHost.presence.retryMs") == 30000


def test_the_wait_between_menu_link_tries_doubles_up_to_two_minutes(driver, live):
    open_host(driver, live)
    waits = driver.execute_script(
        "const p = window.testHost.presence; p.start = () => {}; const out = [p.retryMs];"
        "for (let i = 0; i < 5; i++) { p.retryLater(); out.push(p.retryMs); }"
        "return out;"
    )
    assert waits == [15000, 30000, 60000, 120000, 120000, 120000]


def test_a_change_waiting_to_be_sent_goes_out_with_the_next_send(driver, live):
    open_host(driver, live)
    sent = driver.execute_async_script(
        "const done = arguments[0];"
        "import('./presence.js').then(async ({ Presence }) => {"
        "  const p = new Presence({ login: { player: { id: '9' } } });"
        "  const sent = [];"
        "  p.conn = { send: (state) => { sent.push(state.status); return true; } };"
        "  p.set({ status: 'a' });"
        "  p.send();"
        "  await new Promise((resolve) => setTimeout(resolve, 600));"
        "  done(sent);"
        "});"
    )
    assert sent == ["a"]


def test_arrivals_are_people_new_to_your_game(driver, live):
    open_host(driver, live)
    result = driver.execute_async_script(
        "const done = arguments[0];"
        "import('./presence.js').then(({ arrivals }) => {"
        "  const before = [{id: '1', game: 'demo'}, {id: '2', game: null}];"
        "  const after = [{id: '1', game: 'demo'}, {id: '2', game: 'demo'}, {id: '9', game: 'demo'},"
        "    {id: '3', game: 'snake'}];"
        "  done([arrivals(before, after, 'demo', '9').map((p) => p.id), arrivals(before, after, null, '9').length]);"
        "});"
    )
    assert result == [["2"], 0]


def test_people_coming_back_after_a_drop_are_not_arrivals(driver, live):
    open_host(driver, live)
    result = driver.execute_async_script(
        r"""
        const done = arguments[0];
        import('./presence.js').then(({ Presence }) => {
          const p = new Presence({ login: { player: { id: '9' } } });
          const person = (id, game = 'demo') => ({ id, game });
          const noted = [];
          p.listen((people, arrived) => noted.push(arrived.map((x) => x.id)));
          p.state.where = 'demo';
          // 1 and 2 were in the game, 3 was in the menu, when the link dropped
          p.remember([person('1'), person('2'), person('3', null)]);
          p.comeBack();
          p.quietUntil = 0;
          // 1 is back, 7 is new
          p.receive({ people: [person('1'), person('7')] });
          // 2 is back later, and 1 is not new
          p.receive({ people: [person('1'), person('7'), person('2')] });
          // 3 was never in the game, so going in is an arrival
          p.receive({ people: [person('1'), person('7'), person('2'), person('3')] });
          // 1 left and came again: back for good, so it is an arrival now
          p.receive({ people: [person('7'), person('2'), person('3')] });
          p.receive({ people: [person('7'), person('2'), person('3'), person('1')] });
          // Someone listed in the menu first, as the bot does until their game's update reaches it, is still back
          p.remember([person('4')]);
          p.receive({ people: [person('7'), person('4', null)] });
          p.receive({ people: [person('7'), person('4')] });
          // After the time is over nobody is back any more
          p.remember([person('5')]);
          p.returningUntil = 0;
          p.receive({ people: [person('7'), person('4'), person('5')] });
          done(noted);
        });
        """
    )
    assert result == [["7"], [], ["3"], [], ["1"], [], [], ["5"]]
