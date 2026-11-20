import asyncio
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait

from marblemunch.main import MarbleMunch

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="marblemunch"]'
# Runs in the game's frame before its scripts. The sound's two volume knobs are the only gains wired straight to
# the speakers, music's first and the effects' second. Every tone played is counted, and the song (the only long
# sound) keeps the time it was last told to stop
SOUND_SPY = """
window.buses = [];
window.tones = 0;
window.songs = [];
const realConnect = AudioNode.prototype.connect;
AudioNode.prototype.connect = function (target, ...rest) {
  if (this instanceof GainNode && target instanceof AudioDestinationNode) {
    window.buses.push(this);
  }
  return realConnect.call(this, target, ...rest);
};
const realTone = OscillatorNode.prototype.start;
OscillatorNode.prototype.start = function (...args) {
  window.tones += 1;
  return realTone.apply(this, args);
};
const realStop = AudioBufferSourceNode.prototype.stop;
AudioBufferSourceNode.prototype.stop = function (when = 0) {
  if (this.buffer && this.buffer.duration > 10) {
    window.songs.push(this);
    this.endsAt = when;
  }
  return realStop.call(this, when);
};
"""
MUSIC_LEVEL = 0.33
EFFECTS_LEVEL = 0.6
# The sound panel's controls a finger can't press: off the screen, under 44 px, or under something else at their middle
NOT_PRESSABLE = """
return ['sound', 'sfx', 'sfx-volume', 'music', 'music-volume'].filter((id) => {
  const node = document.getElementById(id);
  const box = node.getBoundingClientRect();
  const inside = box.left >= 0 && box.top >= 0 && box.right <= innerWidth && box.bottom <= innerHeight;
  const big = box.width >= 44 && box.height >= 44;
  const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
  return !(inside && big && node.contains(hit));
});
"""
# Whether the sound panel stays clear of the hub's people button, whose arrival notes slide out under it
CLEAR_OF_PEOPLE = """
const a = document.getElementById('sound-panel').getBoundingClientRect();
const b = document.querySelector('.hub-people').getBoundingClientRect();
return a.right < b.left || b.right < a.left || a.bottom < b.top || b.bottom < a.top;
"""
LONG_NAME = "Maximilian Featherstonehaugh"
LONG_NOTICE = "You've used every cash-in for today. They come back at midnight UTC."
# Where an element sits on the screen
RECT = """
const b = document.querySelector(arguments[0]).getBoundingClientRect();
return { left: b.left, top: b.top, right: b.right, bottom: b.bottom, width: b.width, height: b.height };
"""
# Whether the page fits a sideways phone: no taller than the screen, the board above the page's bottom padding, and
# Back and Sound wholly on screen
FITS = """
const inside = (id) => {
  const b = document.getElementById(id).getBoundingClientRect();
  return b.left >= 0 && b.top >= 0 && b.right <= innerWidth && b.bottom <= innerHeight;
};
const board = document.querySelector('#board canvas').getBoundingClientRect();
return {
  height: document.documentElement.scrollHeight,
  board: board.bottom <= innerHeight - 12,
  back: inside('back'),
  sound: inside('sound'),
};
"""
# The side panel's buttons that can't be scrolled into view inside it and then pressed at their middle. A finger can't
# scroll the page itself, so a button only reached by scrolling the page doesn't count
OUT_OF_REACH = """
return arguments[0].filter((selector) => {
  const node = document.querySelector(selector);
  node.scrollIntoView({ block: 'nearest' });
  const b = node.getBoundingClientRect();
  const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
  const pageMoved = document.scrollingElement.scrollTop !== 0 || document.body.scrollTop !== 0;
  return pageMoved || !node.contains(hit);
});
"""
# Whether the yellow ring around the player's own score card, 5 px outside it, fits inside the side panel, which cuts
# off anything past its edges once it scrolls
RING_INSIDE = """
const card = document.querySelector('.score.mine').getBoundingClientRect();
const side = document.querySelector('.side').getBoundingClientRect();
return card.left - 5 >= side.left && card.right + 5 <= side.right && card.top - 5 >= side.top;
"""
# What the round munch button covers in the side panel: the parts of the panel's elements it shows, since it scrolls
UNDER_MUNCH = """
const munch = document.getElementById('munch').getBoundingClientRect();
const side = document.querySelector('.side').getBoundingClientRect();
const covered = [];
for (const node of document.querySelectorAll('.side *')) {
  const b = node.getBoundingClientRect();
  const left = Math.max(b.left, side.left), right = Math.min(b.right, side.right);
  const top = Math.max(b.top, side.top), bottom = Math.min(b.bottom, side.bottom);
  if (right > left && bottom > top && left < munch.right && right > munch.left && top < munch.bottom && bottom > munch.top) {
    covered.push(node.id || node.className || node.tagName);
  }
}
return covered;
"""
# Whether a press just above and just below each watcher face, at its middle, lands on that face
FACE_REACH = """
return [...document.querySelectorAll('#watching .face')].map((face) => {
  const b = face.getBoundingClientRect();
  const x = b.left + b.width / 2;
  return [face.contains(document.elementFromPoint(x, b.top - 8)), face.contains(document.elementFromPoint(x, b.bottom + 8))];
});
"""
# Where each line of an element's text sits
LINES = """
const range = document.createRange();
range.selectNodeContents(document.querySelector(arguments[0]));
return [...range.getClientRects()].map((b) => ({ left: b.left, right: b.right, top: b.top }));
"""


@pytest.fixture(scope="module")
def driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    # Headless Chrome still plays the games' sounds through the computer's speakers
    options.add_argument("--mute-audio")
    options.add_argument("--window-size=1280,800")
    # PixiJS needs WebGL. Headless Chrome may have no graphics card to use, and this lets it draw in software
    options.add_argument("--enable-unsafe-swiftshader")
    try:
        chrome = webdriver.Chrome(options=options)
    except WebDriverException as e:
        pytest.skip(f"Chrome can't start on this machine: {e.msg}")
    yield chrome
    chrome.quit()


@pytest.fixture
def live(tmp_path, driver):
    hub = fakes.make_hub()
    cog = MarbleMunch(bot=hub.bot)
    cog.payouts.bank = fakes.FakeBank()
    assert fakes.register(hub, cog) is not None
    server = browser.LiveHub(hub, browser.hub_web_copy(tmp_path))
    server.start()
    driver.set_window_size(1280, 800)
    browser.fresh(driver, server)
    server.cog = cog
    yield server
    # Stopped on the server's own event loop, so no match loop is left running when it closes
    asyncio.run_coroutine_threadsafe(cog.cog_unload(), server.loop).result(5)
    server.stop()


def open_game(driver, live, insets=None):
    """Open Marble Munch from the menu. Insets are Discord's room for its buttons and the notch, in px per side"""
    driver.get(f"{live.url}/{browser.DISCORD_QUERY}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    # Discord sets these on the menu's page, and the hub passes them on to the game's
    for side, size in (insets or {}).items():
        driver.execute_script(
            "document.documentElement.style.setProperty(arguments[0], arguments[1])",
            f"--discord-safe-area-inset-{side}",
            f"{size}px",
        )
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(driver, "document.querySelectorAll('#scores li').length === 4", timeout=20)


def tap_bottom_hippo(driver):
    canvas = driver.find_element(By.CSS_SELECTOR, "#board canvas")
    side = min(canvas.size["width"], canvas.size["height"])
    # The bottom hippo's head, a third of the board below its middle
    ActionChains(driver).move_to_element_with_offset(canvas, 0, int(side * 0.33)).click().perform()


def test_a_solo_round_starts_and_streams_updates(driver, live):
    open_game(driver, live)
    tap_bottom_hippo(driver)
    browser.wait_for(driver, "!document.getElementById('stand').hidden")
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'", timeout=10)
    ActionChains(driver).key_down(Keys.SPACE).pause(0.3).key_up(Keys.SPACE).perform()
    driver.switch_to.default_content()
    assert browser.wait_for(driver, "/\\d+ TPS$/.test(document.querySelector('.fps').textContent)", timeout=5)
    problems = [line for line in browser.console_lines(driver) if "Uncaught" in line or "marblemunch" in line]
    assert not problems, problems


def run(live, coro):
    """Run a coroutine on the server's own event loop, where the cog's Config is used"""
    return asyncio.run_coroutine_threadsafe(coro, live.loop).result(5)


async def read(value):
    # A Config value's read is awaitable but not a coroutine, which run_coroutine_threadsafe needs
    return await value()


def call(live, fn):
    """Run a plain function on the server's own event loop, between the match's updates"""

    async def go():
        return fn()

    return run(live, go())


def the_match(live):
    return next(iter(live.cog.matches.values()))


@contextmanager
def phone(driver, width, height):
    """A touch screen of this size until the block ends"""
    metrics = {"width": width, "height": height, "deviceScaleFactor": 2, "mobile": True}
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", metrics)
    driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
    try:
        yield
    finally:
        driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": False})
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def rect(driver, selector):
    return driver.execute_script(RECT, selector)


def payouts_on(live):
    on = {"on": True, "rate": 100, "cap": 1000, "plays": 3}
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set(on))
    # Saved data lasts across tests, and an earlier one may have used today's cash-ins
    run(live, live.cog.config.member_from_ids(fakes.GUILD_ID, fakes.MEMBER_ID).cashed.set({}))


def offer(live, marbles):
    """Offer this page's player a cash-in for a round of this many marbles, 100 credits each"""
    live.cog.offers[fakes.MEMBER_ID] = (fakes.GUILD_ID, marbles)
    run(live, live.cog.send_offer(the_match(live).room.connections[0], marbles))


def add_watchers(live, count):
    """Other people in the window with the game open, each a member of the server"""
    guild = live.hub.bot.guilds[fakes.GUILD_ID]
    for number in range(count):
        user = fakes.fake_user(100 + number, f"watcher {number + 1}")
        live.hub.bot.users[user.id] = user
        guild.members[user.id] = fakes.fake_member(user, guild)
        live.add_person(user.id, where="marblemunch")


def seat_me_and_wait(live):
    """Seat this page's player, with the countdown held so the waiting screen stays"""

    def seat():
        match = the_match(live)
        match.tick_waiting = lambda: None
        match.sit(match.room.connections[0], 0)

    call(live, seat)


def end_a_round_with_results(live):
    """Play no round at all: a new board straight to its results, which stay up, and an unrecorded result"""

    def finish():
        match = the_match(live)
        match.record = lambda match, results: None
        match.begin_round()
        match.end_round()
        match.tick_results = lambda: None

    call(live, finish)


def test_the_last_round_cashes_in_from_the_side_panel(driver, live):
    on = {"on": True, "rate": 100, "cap": 1000, "plays": 3}
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set(on))
    run(live, live.cog.config.member_from_ids(fakes.GUILD_ID, fakes.MEMBER_ID).cashed.set({}))
    open_game(driver, live)
    assert not driver.find_element(By.ID, "open-payouts").is_displayed()
    conn = next(iter(live.cog.matches.values())).room.connections[0]
    live.cog.offers[fakes.MEMBER_ID] = (fakes.GUILD_ID, 4)
    run(live, live.cog.send_offer(conn, 4))
    browser.wait_for(driver, "!document.getElementById('cashin').hidden")
    assert "worth 400 credits" in driver.find_element(By.ID, "cashin-text").text
    driver.find_element(By.ID, "cashin-button").click()
    browser.wait_for(driver, "document.getElementById('cashin').hidden")
    assert "+400 credits" in driver.find_element(By.ID, "toast").text
    assert live.cog.payouts.bank.balances[fakes.MEMBER_ID] == 400


def test_a_server_admin_sets_payouts_from_the_game(driver, live):
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set({}))
    # Saved data lasts across tests, and an earlier one may have cashed in today
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).tally.set({}))
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    browser.wait_for(driver, "!document.getElementById('open-payouts').hidden")
    driver.find_element(By.ID, "open-payouts").click()
    assert driver.find_element(By.ID, "payouts-rate-label").text == "Credits per marble"
    assert "Today: 0 credits paid to 0 players" in driver.find_element(By.ID, "payouts-today").text
    driver.find_element(By.ID, "payouts-on").click()
    driver.find_element(By.ID, "payouts-plays").send_keys(Keys.BACKSPACE, "5")
    driver.find_element(By.ID, "save-payouts").click()
    browser.wait_for(driver, "document.getElementById('payouts-status').textContent === 'Saved.'")
    saved = run(live, read(live.cog.config.guild_from_id(fakes.GUILD_ID).payouts))
    assert saved == {"on": True, "rate": 100, "cap": 1000, "plays": 5}
    driver.find_element(By.ID, "payouts-plays").send_keys(Keys.BACKSPACE)
    driver.find_element(By.ID, "save-payouts").click()
    browser.wait_for(driver, "document.getElementById('payouts-status').textContent.includes('Cash-ins a day')")


def test_watchers_show_as_faces_and_the_player_says_watching(driver, live):
    open_game(driver, live)
    live.add_person(fakes.MANAGER_ID, where="marblemunch")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    assert driver.execute_script("return document.querySelector('.side .hub-people') !== null")
    me = live.server.presence.windows["i-1"].people[fakes.MEMBER_ID]
    assert me.status == "Watching" and me.busy is False


def test_a_seated_player_alone_has_no_watching_row_and_a_round_marks_them_busy(driver, live):
    open_game(driver, live)
    me = live.server.presence.windows["i-1"].people[fakes.MEMBER_ID]
    tap_bottom_hippo(driver)
    browser.wait_for(driver, "!document.getElementById('stand').hidden")
    assert driver.find_element(By.ID, "watching").get_attribute("hidden")
    WebDriverWait(driver, 10).until(lambda _: me.status == "Waiting for a round")
    assert me.busy is False
    driver.find_element(By.ID, "start").click()
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    assert me.status.startswith("Orange hippo · ")


def test_a_new_people_list_that_changes_nothing_leaves_the_faces_alone(driver, live):
    open_game(driver, live)
    other = live.add_person(fakes.MANAGER_ID, where="marblemunch")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    # A face redrawn between a press and its release would lose the tap, and lists arrive several times a second
    driver.execute_script(
        "window.redrawn = 0;"
        "new MutationObserver((list) => { window.redrawn += list.length; })"
        ".observe(document.getElementById('watching'), { childList: true });"
    )
    live.update_person(other, where="marblemunch", status="Reading the rules")
    time.sleep(1.2)
    assert driver.execute_script("return window.redrawn") == 0
    # The same observer does see a real change
    live.update_person(other)
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 1")
    assert driver.execute_script("return window.redrawn") > 0


def test_an_unchanged_status_is_not_sent_again_while_a_round_streams(driver, live):
    open_game(driver, live)
    me = live.server.presence.windows["i-1"].people[fakes.MEMBER_ID]
    tap_bottom_hippo(driver)
    browser.wait_for(driver, "!document.getElementById('stand').hidden")
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'", timeout=10)
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    # The player eats nothing, so nothing about their status changes for the rest of the round. The hub would
    # still pass on every call, and the bot would send the window's list again each time
    time.sleep(0.6)
    sent = []
    original = live.server.presence.update

    async def counting(conn, data):
        sent.append(data)
        await original(conn, data)

    live.server.presence.update = counting
    time.sleep(1.5)
    assert sent == []


def test_tapping_a_watcher_face_says_who_it_is(driver, live):
    open_game(driver, live)
    live.add_person(fakes.MANAGER_ID, where="marblemunch")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    driver.find_element(By.CSS_SELECTOR, '#watching .face[title="Manager"]').click()
    toast = driver.find_element(By.ID, "toast")
    browser.wait_for(driver, "!document.getElementById('toast').hidden")
    assert "Manager" in toast.text and toast.text.endswith("is watching.")


def play_a_round_to_its_end(driver, live, mine, other):
    """Seat the player at the bottom hippo, start a round and end it with these scores for them and the top hippo"""
    open_game(driver, live)
    tap_bottom_hippo(driver)
    browser.wait_for(driver, "!document.getElementById('stand').hidden")
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'", timeout=10)
    match = next(iter(live.cog.matches.values()))
    # These rounds are ended by hand, so their results stay out of the leaderboard the other tests share
    match.record = lambda match, results: None

    async def finish():
        for hippo, score in zip(match.board.hippos, (mine, 0, other, 0)):
            hippo.score = score
        match.end_round()
        # Long enough that the next round's wait doesn't start while the test looks at the results
        match.stage_left = 30 * 30

    run(live, finish())
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'results'")
    return live.server.presence.windows["i-1"].people[fakes.MEMBER_ID]


@pytest.mark.parametrize(
    "mine,other,said",
    [(5, 3, "Won with 5 marbles"), (3, 5, "Ate 3 marbles"), (0, 5, "Ate 0 marbles")],
)
def test_the_results_say_how_the_player_did(driver, live, mine, other, said):
    me = play_a_round_to_its_end(driver, live, mine, other)
    WebDriverWait(driver, 10).until(lambda _: me.status == said)
    assert me.busy is False


def test_a_player_who_sits_in_a_seat_vacated_during_the_results_is_waiting_for_a_round(driver, live):
    open_game(driver, live)
    me = live.server.presence.windows["i-1"].people[fakes.MEMBER_ID]
    match = next(iter(live.cog.matches.values()))
    mine = match.room.connections[0]
    # Another player's seat, so this page watches the round
    other = SimpleNamespace(ctx=SimpleNamespace(guild=None, author=SimpleNamespace(id=1001)))
    match.record = lambda match, results: None

    async def seat_other():
        seat = match.seats[1]
        seat.user_id, seat.name, seat.board_name, seat.conn = 1001, "Ann", "Ann", other
        match.countdown = 1

    run(live, seat_other())
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'", timeout=10)

    async def finish():
        match.board.hippos[1].score = 4
        match.end_round()
        match.stage_left = 30 * 30
        # Ann leaves during the results, and this player sits where she was, with her 4 marbles still on the seat
        match.stand(other)
        assert match.sit(mine, 1) is None

    run(live, finish())
    WebDriverWait(driver, 10).until(lambda _: me.status != "Watching")
    assert me.status == "Waiting for a round"


def test_a_closed_connection_clears_the_status_and_busy_flag(driver, live):
    open_game(driver, live)
    me = live.server.presence.windows["i-1"].people[fakes.MEMBER_ID]
    tap_bottom_hippo(driver)
    browser.wait_for(driver, "!document.getElementById('stand').hidden")
    match = the_match(live)
    conn = match.room.connections[0]
    starting = match.tick_starting

    # The connection closes just after "Munch!", while that word is still on the board
    def tick_starting():
        starting()
        if match.stage == "playing":
            live.loop.call_later(0.2, lambda: live.loop.create_task(conn.close(4100)))

    match.tick_starting = tick_starting
    driver.find_element(By.ID, "start").click()
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    WebDriverWait(driver, 10).until(lambda _: me.status == "Not connected")
    assert me.busy is False
    # Clearing "Munch!" a moment later leaves the reason the game stopped on the board
    time.sleep(1)
    assert driver.execute_script(
        "return [document.getElementById('overlay').hidden, document.getElementById('overlay-big').textContent,"
        " document.getElementById('munch').hidden]"
    ) == [False, "Sorry!", True]


def test_a_closed_connection_hides_the_buttons_that_need_it(driver, live):
    payouts_on(live)
    open_game(driver, live)
    seat_me_and_wait(live)
    browser.wait_for(driver, "!document.getElementById('start').hidden")
    offer(live, 7)
    browser.wait_for(driver, "!document.getElementById('cashin').hidden")
    run(live, the_match(live).room.connections[0].close(4100))
    browser.wait_for(driver, "document.getElementById('overlay-big').textContent === 'Sorry!'")
    hidden = "return ['cashin', 'start', 'stand'].map((id) => document.getElementById(id).hidden)"
    assert driver.execute_script(hidden) == [True, True, True]


# ---------- Phones ----------


def test_an_upright_phone_alone_shows_no_watching_row_and_full_size_controls(driver, live):
    with phone(driver, 390, 844):
        open_game(driver, live)
        # The faces are still made, so the row is only hidden while the player is the one person watching
        browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 1")
        assert driver.find_element(By.ID, "watching").get_attribute("hidden")
        assert rect(driver, ".hub-people-button")["height"] == rect(driver, "#back")["height"] == 44
        assert driver.execute_script(browser.WAITS_FOR_DOUBLE_TAP) == []
        driver.find_element(By.ID, "open-leaderboard").click()
        browser.wait_for(driver, "document.getElementById('leaderboard').open")
        box = rect(driver, "#leaderboard")
        assert box["left"] >= 0 and box["right"] <= 390
        assert abs(box["left"] - (390 - box["right"])) <= 1
        assert driver.execute_script(browser.WAITS_FOR_DOUBLE_TAP) == []
        close = "return getComputedStyle(document.getElementById('close-leaderboard')).backgroundColor"
        assert driver.execute_script(close) == "rgb(243, 241, 255)"
        driver.find_element(By.ID, "close-leaderboard").click()
        # The reconnecting banner sits over the board, not over the title row
        driver.execute_script("document.getElementById('banner').hidden = false")
        banner = rect(driver, "#banner")
        for selector in ("h1", "#left"):
            other = rect(driver, selector)
            assert banner["bottom"] <= other["top"] or banner["top"] >= other["bottom"], selector


def test_an_upright_phone_keeps_the_board_still_and_big_through_a_round(driver, live):
    payouts_on(live)
    with phone(driver, 390, 844):
        open_game(driver, live, {"top": 47, "bottom": 34})
        match = the_match(live)
        mine = match.room.connections[0]
        other = SimpleNamespace(ctx=SimpleNamespace(guild=None, author=SimpleNamespace(id=1001)))

        def seat_both():
            match.record = lambda match, results: None
            match.sit(mine, 0)
            seat = match.seats[2]
            seat.user_id, seat.name, seat.board_name, seat.conn = 1001, LONG_NAME, LONG_NAME, other
            match.tick_starting = lambda: None
            match.countdown = 1

        call(live, seat_both)
        browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'starting'")
        time.sleep(0.3)
        assert not driver.find_element(By.ID, "munch").get_attribute("hidden")
        before = rect(driver, "#board canvas")
        tags = driver.execute_script("return [...document.querySelectorAll('#scores .tag')].map((t) => t.textContent)")
        assert tags == ["CPU", "CPU"]
        call(live, lambda: match.__dict__.pop("tick_starting"))
        browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'")
        time.sleep(0.3)
        after = rect(driver, "#board canvas")
        assert all(abs(before[key] - after[key]) <= 1 for key in ("left", "top", "width", "height")), (before, after)

        def finish():
            for hippo, score in zip(match.board.hippos, (3, 0, 5, 0)):
                hippo.score = score
            match.end_round()
            match.tick_results = lambda: None

        call(live, finish)
        browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'results'")
        assert "Start" not in driver.find_element(By.ID, "hint").text
        assert driver.find_element(By.ID, "overlay-big").text.replace("\n", " ") == "Maximilian … wins!"
        assert all(0 <= line["left"] and line["right"] <= 390 for line in driver.execute_script(LINES, "#overlay-big"))
        offer(live, 7)
        browser.wait_for(driver, "!document.getElementById('cashin').hidden")
        box, text, button = (rect(driver, s) for s in ("#cashin", "#cashin-text", "#cashin-button"))
        assert box["height"] <= 80
        assert button["top"] < text["bottom"] and button["bottom"] > text["top"]
        board = rect(driver, "#board canvas")
        # Name tags are drawn 22 px tall on a 600 px board, so this keeps them at least 10 px on screen
        assert min(board["width"], board["height"]) >= 270


@pytest.mark.parametrize("width,height", [(390, 844), (844, 390)])
def test_a_long_toast_wraps_inside_the_board_and_lets_presses_through(driver, live, width, height):
    with phone(driver, width, height):
        open_game(driver, live)
        run(live, the_match(live).room.connections[0].send({"notice": LONG_NOTICE}))
        browser.wait_for(driver, "!document.getElementById('toast').hidden")
        toast, play = rect(driver, "#toast"), rect(driver, ".play")
        assert toast["left"] >= play["left"] + 11.5 and toast["right"] <= play["right"] - 11.5
        assert len({round(line["top"]) for line in driver.execute_script(LINES, "#toast")}) >= 2
        assert driver.execute_script("return document.documentElement.scrollWidth") == width
        middle = "const b = document.getElementById('toast').getBoundingClientRect();" + (
            "return document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2).tagName"
        )
        assert driver.execute_script(middle) == "CANVAS"


def test_a_crowded_sideways_phone_keeps_the_page_on_screen_and_every_button_in_reach(driver, live):
    payouts_on(live)
    add_watchers(live, 12)
    fits = {"height": 390, "board": True, "back": True, "sound": True}
    with phone(driver, 844, 390):
        open_game(driver, live)
        seat_me_and_wait(live)
        browser.wait_for(driver, "!document.getElementById('start').hidden")
        browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 6")
        assert driver.execute_script(FITS) == fits
        assert driver.execute_script(RING_INSIDE)
        assert driver.execute_script(OUT_OF_REACH, ["#start", "#stand", "#open-leaderboard"]) == []
        end_a_round_with_results(live)
        browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'results'")
        offer(live, 7)
        browser.wait_for(driver, "!document.getElementById('cashin').hidden")
        assert driver.execute_script(FITS) == fits
        assert driver.execute_script(OUT_OF_REACH, ["#stand", "#cashin-button"]) == []
        run(live, the_match(live).room.connections[0].close(4100))
        browser.wait_for(driver, "document.getElementById('overlay-big').textContent === 'Sorry!'")
        assert driver.execute_script(FITS) == fits


@pytest.mark.parametrize("insets", [{}, {"left": 59, "right": 59, "bottom": 21}])
def test_the_sideways_munch_button_leaves_the_side_panel_clear(driver, live, insets):
    payouts_on(live)
    add_watchers(live, 12)
    with phone(driver, 844, 390):
        open_game(driver, live, insets)
        match = the_match(live)

        def begin():
            match.sit(match.room.connections[0], 0)
            match.begin_round()
            match.stage = "playing"
            # The board holds still, so the round can't end while the test looks
            match.tick_playing = lambda: None

        call(live, begin)
        browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'")
        browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 6")
        offer(live, 7)
        browser.wait_for(driver, "!document.getElementById('cashin').hidden")
        assert driver.execute_script(UNDER_MUNCH) == []
        driver.execute_script("const side = document.querySelector('.side'); side.scrollTop = side.scrollHeight")
        assert driver.execute_script(UNDER_MUNCH) == []
        assert driver.execute_script(OUT_OF_REACH, [".hub-people-button", "#cashin-button"]) == []


def test_a_sideways_watcher_mid_round_keeps_no_room_for_a_munch_button(driver, live):
    payouts_on(live)
    add_watchers(live, 12)
    with phone(driver, 844, 390):
        open_game(driver, live, {"left": 59, "right": 59, "bottom": 21})
        match = the_match(live)
        guild = live.hub.bot.guilds[fakes.GUILD_ID]
        other = SimpleNamespace(ctx=SimpleNamespace(guild=None, guild_id=None, author=guild.members[100]))

        def begin():
            match.sit(other, 1)
            match.begin_round()
            match.stage = "playing"
            match.tick_playing = lambda: None

        call(live, begin)
        browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'")
        browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 6")
        offer(live, 7)
        browser.wait_for(driver, "!document.getElementById('cashin').hidden")
        assert driver.find_element(By.ID, "munch").get_attribute("hidden")
        # The panel runs down the screen, so the people button shows whole without scrolling the panel
        side, people = rect(driver, ".side"), rect(driver, ".hub-people-button")
        assert people["bottom"] <= side["bottom"]
        assert side["bottom"] > 390 - 126


@pytest.mark.parametrize("insets", [{}, {"left": 47, "right": 47, "bottom": 21}])
def test_a_sideways_phone_alone_shows_the_whole_people_button_above_the_munch_button(driver, live, insets):
    with phone(driver, 844, 390):
        open_game(driver, live, insets)
        match = the_match(live)

        def begin():
            match.sit(match.room.connections[0], 0)
            match.begin_round()
            match.stage = "playing"
            match.tick_playing = lambda: None

        call(live, begin)
        browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'")
        browser.wait_for(driver, "!document.getElementById('munch').hidden")
        side, people, munch = (rect(driver, s) for s in (".side", ".hub-people-button", "#munch"))
        assert people["bottom"] <= side["bottom"] and people["bottom"] <= munch["top"], (side, people, munch)


def test_a_sideways_phone_shows_each_dialogs_buttons_without_scrolling(driver, live):
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set({}))
    live.user_id = fakes.MANAGER_ID
    dialogs = (
        ("open-leaderboard", "leaderboard", ["close-leaderboard"]),
        ("open-payouts", "payouts", ["save-payouts", "reset-payouts", "close-payouts"]),
    )
    with phone(driver, 844, 390):
        open_game(driver, live)
        browser.wait_for(driver, "!document.getElementById('open-payouts').hidden")
        for opener, dialog, buttons in dialogs:
            driver.find_element(By.ID, opener).click()
            browser.wait_for(driver, f"document.getElementById('{dialog}').open")
            box = rect(driver, f"#{dialog}")
            assert box["top"] >= 0 and box["bottom"] <= 390, (dialog, box)
            for button in buttons:
                found = rect(driver, f"#{button}")
                assert found["top"] >= box["top"] and found["bottom"] <= box["bottom"], (button, found, box)
            driver.find_element(By.ID, f"close-{dialog}").click()


def test_a_cash_in_note_with_nothing_to_cash_steps_aside_for_the_round(driver, live):
    payouts_on(live)
    with phone(driver, 390, 844):
        open_game(driver, live)
        offer(live, 0)
        browser.wait_for(driver, "!document.getElementById('cashin').hidden")
        assert driver.find_element(By.ID, "cashin").is_displayed()
        assert "Munch some marbles" in driver.find_element(By.ID, "cashin-text").text
        match = the_match(live)

        def begin():
            match.sit(match.room.connections[0], 0)
            match.begin_round()
            match.stage = "playing"
            match.tick_playing = lambda: None

        call(live, begin)
        browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'")
        assert not driver.find_element(By.ID, "cashin").is_displayed()
        # A round that can still be cashed in stays through the next one
        offer(live, 7)
        browser.wait_for(driver, "!document.getElementById('cashin-button').hidden")
        assert driver.find_element(By.ID, "cashin").is_displayed()


def test_watcher_faces_take_a_finger_press_around_them(driver, live):
    payouts_on(live)
    with phone(driver, 390, 844):
        open_game(driver, live)
        live.add_person(fakes.MANAGER_ID, where="marblemunch")
        browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
        # The hub's arrival notes and focus ring take the game's own colors
        colors = (
            "const s = getComputedStyle(document.querySelector('.hub-people'));"
            "return ['--hub-accent', '--hub-on-accent'].map((name) => s.getPropertyValue(name).trim())"
        )
        assert driver.execute_script(colors) == ["#ffd23f", "#1f1747"]
        offer(live, 7)
        browser.wait_for(driver, "!document.getElementById('cashin').hidden")
        assert driver.execute_script(FACE_REACH) == [[True, True], [True, True]]
        assert rect(driver, "#watching .face")["width"] == 26
        assert driver.execute_script(OUT_OF_REACH, [".hub-people-button", "#cashin-button"]) == []


def test_the_admin_payout_settings_fit_an_upright_phone(driver, live):
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set({}))
    live.user_id = fakes.MANAGER_ID
    with phone(driver, 390, 844):
        open_game(driver, live)
        browser.wait_for(driver, "!document.getElementById('open-payouts').hidden")
        order = "return [...document.querySelector('.corner').children].map((node) => node.id)"
        assert driver.execute_script(order) == ["back", "sound-spot", "open-payouts"]
        driver.find_element(By.ID, "open-payouts").click()
        browser.wait_for(driver, "document.getElementById('payouts').open")
        box = rect(driver, "#payouts")
        assert box["left"] >= 0 and box["right"] <= 390
        assert abs(box["left"] - (390 - box["right"])) <= 1
        for selector in ("#payouts-rate", "#payouts-cap", "#payouts-plays", ".payout-switch"):
            assert rect(driver, selector)["height"] >= 44, selector
        assert driver.execute_script(browser.WAITS_FOR_DOUBLE_TAP) == []
        colors = "return arguments[0].map((id) => getComputedStyle(document.getElementById(id)).backgroundColor)"
        assert driver.execute_script(colors, ["save-payouts", "reset-payouts", "close-payouts"]) == [
            "rgb(255, 210, 63)",
            "rgb(243, 241, 255)",
            "rgb(243, 241, 255)",
        ]


def test_closing_a_dialog_gives_focus_back_to_its_button(driver, live):
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set({}))
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    browser.wait_for(driver, "!document.getElementById('open-payouts').hidden")
    for opener, dialog in (("open-leaderboard", "leaderboard"), ("open-payouts", "payouts")):
        driver.find_element(By.ID, opener).send_keys(Keys.ENTER)
        browser.wait_for(driver, f"document.getElementById('{dialog}').open")
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        browser.wait_for(driver, f"!document.getElementById('{dialog}').open")
        browser.wait_for(driver, f"document.activeElement.id === '{opener}'", timeout=2)
        # Space stays the hippo's key, so it doesn't open the dialog again
        ActionChains(driver).send_keys(Keys.SPACE).perform()
        time.sleep(0.3)
        assert not driver.execute_script(f"return document.getElementById('{dialog}').open")


def test_an_away_watcher_is_dimmed(driver, live):
    open_game(driver, live)
    other = live.add_person(fakes.MANAGER_ID, where="marblemunch")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    assert driver.execute_script("return document.querySelectorAll('#watching .face.away').length") == 0
    live.update_person(other, where="marblemunch", away=True)
    browser.wait_for(driver, "document.querySelectorAll('#watching .face.away').length === 1")


def test_the_watching_count_is_people_not_connections(driver, live):
    open_game(driver, live)
    live.add_person(fakes.MANAGER_ID, where="marblemunch")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    match = next(iter(live.cog.matches.values()))
    # The bot counts connections, so one person with the game open on two devices is two to it
    match.watching = lambda: 5
    match.dirty = True
    time.sleep(0.6)
    assert driver.find_element(By.CSS_SELECTOR, "#watching .label").text == "2 watching"


# ---------- Sound panel ----------


@pytest.fixture
def spy(driver):
    script = driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": SOUND_SPY})
    yield
    driver.execute_cdp_cmd("Page.removeScriptToEvaluateOnNewDocument", {"identifier": script["identifier"]})


def open_sound(driver):
    driver.find_element(By.ID, "sound").click()
    browser.wait_for(driver, "!document.getElementById('sound-panel').hidden")


def panel_open(driver):
    """Whether the sound panel shows, and what its button tells screen readers"""
    return driver.execute_script(
        "return [!document.getElementById('sound-panel').hidden,"
        " document.getElementById('sound').getAttribute('aria-expanded')]"
    )


def saved(driver, key):
    return driver.execute_script(f"return localStorage.getItem('marblemunch:{key}')")


def gain(driver, bus):
    """A volume knob's level: 0 is the music's, 1 the effects'"""
    return driver.execute_script(f"return window.buses[{bus}].gain.value")


def muted(driver):
    return "muted" in driver.find_element(By.ID, "sound").get_attribute("class")


def test_the_sound_button_opens_the_panel_and_it_closes_again(driver, live):
    open_game(driver, live)
    assert panel_open(driver) == [False, "false"]
    assert driver.find_element(By.ID, "sound").get_attribute("aria-controls") == "sound-panel"
    open_sound(driver)
    assert panel_open(driver) == [True, "true"]
    # Pressing a switch keeps the panel open, and Space stays the hippo's key even with the switch focused
    driver.find_element(By.ID, "sfx").click()
    ActionChains(driver).send_keys(Keys.SPACE).perform()
    assert driver.find_element(By.ID, "sfx").get_attribute("aria-checked") == "false"
    assert panel_open(driver) == [True, "true"]
    driver.find_element(By.ID, "sound").click()
    assert panel_open(driver) == [False, "false"]
    open_sound(driver)
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    assert panel_open(driver) == [False, "false"]
    assert driver.execute_script("return document.activeElement.id") == "sound"
    open_sound(driver)
    driver.find_element(By.ID, "scores").click()
    assert panel_open(driver) == [False, "false"]


def test_the_switches_turn_each_sound_off_and_the_button_shows_when_all_are(driver, live, spy):
    open_game(driver, live)
    open_sound(driver)
    browser.wait_for(driver, "window.songs.length > 0", timeout=20)
    driver.find_element(By.ID, "music").click()
    assert driver.find_element(By.ID, "music").get_attribute("aria-checked") == "false"
    assert saved(driver, "music") == "off"
    # The song fades out now instead of playing to its end
    assert driver.execute_script("return window.songs.every((song) => song.endsAt < song.context.currentTime + 1)")
    assert not muted(driver)
    driver.find_element(By.ID, "sfx").click()
    assert saved(driver, "sfx") == "off"
    assert muted(driver)
    # Effects that are off stay silent, even when their slider is let go
    driver.execute_script("window.tones = 0")
    driver.find_element(By.ID, "sfx-volume").send_keys(Keys.ARROW_LEFT)
    assert driver.execute_script("return window.tones") == 0
    # The switches leave the levels alone
    assert gain(driver, 0) == pytest.approx(MUSIC_LEVEL)
    assert gain(driver, 1) == pytest.approx(EFFECTS_LEVEL * 0.95**2)
    driver.find_element(By.ID, "sfx").click()
    assert saved(driver, "sfx") == "on"
    assert not muted(driver)


@pytest.mark.parametrize("kind,bus,level", [("music", 0, MUSIC_LEVEL), ("sfx", 1, EFFECTS_LEVEL)])
def test_a_slider_sets_its_own_volume_as_it_moves_and_saves_it_once_let_go(driver, live, spy, kind, bus, level):
    open_game(driver, live)
    open_sound(driver)
    slider = driver.find_element(By.ID, f"{kind}-volume")
    untouched = gain(driver, 1 - bus)
    driver.execute_script("window.tones = 0")
    ActionChains(driver).click_and_hold(slider).move_by_offset(-slider.size["width"] // 4, 0).perform()
    volume = int(slider.get_attribute("value"))
    assert 0 < volume < 100
    assert gain(driver, bus) == pytest.approx(level * (volume / 100) ** 2)
    assert gain(driver, 1 - bus) == untouched
    assert saved(driver, f"{kind}-volume") is None
    ActionChains(driver).release().perform()
    assert saved(driver, f"{kind}-volume") == str(volume)
    # Letting go of the effects slider plays an effect at the new level, so the player hears it
    tones = driver.execute_script("return window.tones")
    assert tones > 0 if kind == "sfx" else tones == 0


def test_the_sound_settings_survive_a_reload(driver, live, spy):
    open_game(driver, live)
    open_sound(driver)
    driver.find_element(By.ID, "music").click()
    driver.find_element(By.ID, "sfx").click()
    driver.find_element(By.ID, "music-volume").send_keys(Keys.HOME, Keys.ARROW_RIGHT, Keys.ARROW_RIGHT)
    driver.find_element(By.ID, "sfx-volume").send_keys(Keys.ARROW_LEFT)
    driver.switch_to.default_content()
    open_game(driver, live)
    assert driver.find_element(By.ID, "music-volume").get_attribute("value") == "10"
    assert driver.find_element(By.ID, "sfx-volume").get_attribute("value") == "95"
    assert driver.find_element(By.ID, "music").get_attribute("aria-checked") == "false"
    assert driver.find_element(By.ID, "sfx").get_attribute("aria-checked") == "false"
    assert muted(driver)
    # The knobs start at the saved levels as soon as the sound starts
    open_sound(driver)
    assert gain(driver, 0) == pytest.approx(MUSIC_LEVEL * 0.1**2)
    assert gain(driver, 1) == pytest.approx(EFFECTS_LEVEL * 0.95**2)


def test_a_missing_or_broken_saved_volume_is_full_volume(driver, live, spy):
    open_game(driver, live)
    driver.execute_script(
        "localStorage.setItem('marblemunch:music-volume', '150');"
        "localStorage.setItem('marblemunch:sfx-volume', 'loud');"
    )
    driver.switch_to.default_content()
    open_game(driver, live)
    open_sound(driver)
    assert driver.find_element(By.ID, "music-volume").get_attribute("value") == "100"
    assert driver.find_element(By.ID, "sfx-volume").get_attribute("value") == "100"
    assert gain(driver, 0) == pytest.approx(MUSIC_LEVEL)
    assert gain(driver, 1) == pytest.approx(EFFECTS_LEVEL)


@pytest.mark.parametrize("user_id", [fakes.MEMBER_ID, fakes.MANAGER_ID])
@pytest.mark.parametrize("width,height", [(390, 844), (360, 780), (844, 390)])
def test_every_sound_control_can_be_pressed_on_a_phone(driver, live, width, height, user_id):
    # A server admin also has the payout settings button in the same row
    live.user_id = user_id
    with phone(driver, width, height):
        open_game(driver, live)
        if user_id == fakes.MANAGER_ID:
            browser.wait_for(driver, "!document.getElementById('open-payouts').hidden")
        open_sound(driver)
        assert driver.execute_script(NOT_PRESSABLE) == []
        assert driver.execute_script(CLEAR_OF_PEOPLE)
