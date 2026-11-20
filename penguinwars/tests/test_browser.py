import asyncio
import time
from contextlib import contextmanager
from dataclasses import asdict, replace
from io import BytesIO
from itertools import combinations
from math import hypot
from os import environ
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait

from penguinwars.common.floe import CRACK, ICE, S
from penguinwars.common.maps import classic_map
from penguinwars.common.match import GRACE_SECONDS
from penguinwars.common.round import DT, HEAVY_MASS, RADIUS, friction
from penguinwars.common.shop import EXTRAS, ITEMS, KINDS, SOLD
from penguinwars.common.tuning import TWISTS, Tuning
from penguinwars.main import PenguinWars
from penguinwars.tests.fakes import FakeBank

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="penguinwars"]'


def start_chrome():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    # Headless Chrome still plays the games' sounds through the computer's speakers
    options.add_argument("--mute-audio")
    options.add_argument("--window-size=1280,800")
    # PlayCanvas needs WebGL. Headless Chrome may have no graphics card to use, and this lets it draw in software
    options.add_argument("--enable-unsafe-swiftshader")
    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as e:
        pytest.skip(f"Chrome can't start on this machine: {e.msg}")


@pytest.fixture(scope="module")
def driver():
    chrome = start_chrome()
    try:
        yield chrome
    finally:
        chrome.quit()


@pytest.fixture
def live(tmp_path, driver):
    hub = fakes.make_hub()
    cog = PenguinWars(bot=hub.bot)
    cog.shop.bank = FakeBank()
    play_on_classic_ice(cog)
    assert fakes.register(hub, cog) is not None
    server = browser.LiveHub(hub, browser.hub_web_copy(tmp_path))
    server.start()
    driver.set_window_size(1280, 800)
    browser.fresh(driver, server)
    server.cog = cog
    yield server
    # Stopped on the server's own event loop, so no match loop is left running when it closes
    asyncio.run_coroutine_threadsafe(cog.cog_unload(), server.loop).result(5)
    # A leaderboard save cut off with the loop would keep Red's Config file lock taken for every later test
    asyncio.run_coroutine_threadsafe(saves_done(cog), server.loop).result(6)
    server.stop()


async def saves_done(cog):
    await asyncio.wait_for(asyncio.gather(*cog.saving), 5)


def play_on_classic_ice(cog):
    """Every match this cog starts plays on the whole floe with no hazard, as these tests place penguins and tiles by
    the classic ice. A test for another map sets its match's `fixed_map` before the round begins"""
    start = cog.match_for

    def pinned(conn):
        match = start(conn)
        match.fixed_map = match.fixed_map or classic_map()
        return match

    cog.match_for = pinned


def open_game(driver, live, query=browser.DISCORD_QUERY):
    driver.get(f"{live.url}/{query}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(driver, "window.pc && document.getElementById('game').width > 0", timeout=20)


SIZES = {"phone": (390, 844), "sideways": (844, 390), "desktop": (1280, 800)}
NAMES = ("Ann", "Bo", "Cy", "Di", "Ed", "Flo")


def run(live, coro):
    """Run a coroutine on the server's own event loop, where the match lives"""
    return asyncio.run_coroutine_threadsafe(coro, live.loop).result(5)


def match_of(live):
    return next(iter(live.cog.matches.values()))


def me_in(live):
    return live.server.presence.windows["i-1"].people[fakes.MEMBER_ID]


def seat_others(live, names):
    """Seat these people in the first free seats. They have no page"""
    match = match_of(live)

    async def fill():
        free = [number for number, seat in enumerate(match.seats) if not seat.human]
        for number, name in zip(free, names):
            author = SimpleNamespace(id=2000 + number, display_name=name)
            seat = match.seats[number]
            seat.user_id, seat.name = author.id, name
            seat.conn = SimpleNamespace(ctx=SimpleNamespace(author=author))
        match.dirty = True

    run(live, fill())


def sit_and_start(driver, live):
    """Alone, Play starts the round at once"""
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    driver.find_element(By.ID, "go").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)


def sit_beside(driver, live, names=("Ann",)):
    """These people with no page sit first, so this player's Play waits for the countdown, with the Start button"""
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    seat_others(live, names)
    driver.find_element(By.ID, "go").click()
    browser.wait_for(driver, "!document.getElementById('start').hidden")


def keep_company(live):
    """A person with no page joins the round in a CPU's seat, so this player's dropped connection leaves it running"""
    seat_others(live, ("Ann",))


def end_the_round(live):
    """End the running round by hand and hold its results on screen"""
    match = match_of(live)

    async def finish():
        match.end_round()
        match.stage_left = 30 * 30

    run(live, finish())


def ice_reach(floe):
    """How far the ice that still holds a penguin reaches from the middle, tile edges included: what the page puts the
    seals' circle around"""
    return max(hypot(tile.x, tile.z) + S for tile in floe.tiles if tile.state in (ICE, CRACK))


def hint_line(driver):
    """What the hint says, or None with it faded away"""
    return driver.execute_script(
        "const hint = document.getElementById('hint');"
        "return hint.classList.contains('gone') || hint.hidden ? null : hint.textContent;"
    )


def problems_in_console(driver):
    driver.switch_to.default_content()
    return [line for line in browser.console_lines(driver) if "Uncaught" in line or "penguinwars" in line]


def test_the_game_opens_and_the_engine_starts(driver, live):
    open_game(driver, live)
    assert driver.execute_script("return window.pc.version") == "2.23.3"
    assert not problems_in_console(driver)


def test_an_error_in_the_game_frame_shows_in_the_console_check(driver, live):
    open_game(driver, live)
    driver.execute_script("setTimeout(() => { throw new Error('frame canary'); }, 0)")
    driver.switch_to.default_content()
    lines = browser.wait_for_console(driver, "frame canary")
    assert any("Uncaught" in line for line in lines)


def test_a_solo_round_starts_and_streams_updates(driver, live):
    sit_and_start(driver, live)
    browser.wait_for(driver, "document.getElementById('left').textContent === '6 left'", timeout=8)
    driver.switch_to.default_content()
    assert browser.wait_for(driver, "/\\d+ TPS$/.test(document.querySelector('.fps').textContent)", timeout=5)
    assert not problems_in_console(driver)


def test_status_and_busy_follow_the_round(driver, live):
    open_game(driver, live)
    me = me_in(live)
    WebDriverWait(driver, 10).until(lambda _: me.status == "Watching")
    assert me.busy is False
    # Alone, Play starts the round
    driver.find_element(By.ID, "go").click()
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    assert me.status == "Round 1 · 6 left"
    end_the_round(live)
    WebDriverWait(driver, 10).until(lambda _: not me.busy)
    assert me.status == "Waiting for a round"
    run(live, match_of(live).room.connections[0].close(4100))
    WebDriverWait(driver, 10).until(lambda _: me.status == "Not connected")
    assert me.busy is False


def test_a_fallen_penguin_says_it_is_a_seal(driver, live):
    sit_and_start(driver, live)
    match = match_of(live)

    async def drown():
        match.round.fall(match.seat_driven_by(match.room.connections[0]))

    run(live, drown())
    WebDriverWait(driver, 10).until(lambda _: me_in(live).status.startswith("Seal · "))


def test_the_ice_is_full_so_a_seventh_player_can_join_the_line(driver, live):
    open_game(driver, live)
    seat_others(live, NAMES)
    browser.wait_for(driver, "document.getElementById('go').textContent === 'Join the line'")
    assert not driver.find_element(By.ID, "go").get_property("disabled")
    assert driver.find_element(By.ID, "title").is_displayed()
    driver.find_element(By.ID, "go").click()
    browser.wait_for(driver, "document.getElementById('starting').textContent === \"You're next\"")
    assert driver.find_element(By.ID, "go").text == "Leave the line"
    WebDriverWait(driver, 10).until(lambda _: me_in(live).status == "Next up")
    assert me_in(live).busy is False
    driver.find_element(By.ID, "go").click()
    browser.wait_for(driver, "document.getElementById('go').textContent === 'Join the line'")
    assert not driver.find_element(By.ID, "starting").is_displayed()


def test_a_watcher_is_told_they_can_join_next_round(driver, live):
    open_game(driver, live)
    seat_others(live, NAMES)
    match = match_of(live)

    async def hurry():
        match.countdown = 1

    run(live, hurry())
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    # A second window opening the game mid-round learns the reason from its first message. The first stays open,
    # since a match with nobody connected ends
    first = driver.current_window_handle
    driver.switch_to.new_window("tab")
    try:
        open_game(driver, live)
        browser.wait_for(driver, "document.body.dataset.stage === 'playing'")
        assert hint_line(driver) == "Watching. Tap to join the line"
        WebDriverWait(driver, 3).until(lambda d: d.find_element(By.ID, "hint").is_displayed())
        assert not driver.find_element(By.ID, "title").is_displayed()
        assert not driver.find_element(By.ID, "end").is_displayed()
        WebDriverWait(driver, 10).until(lambda _: me_in(live).status == "Watching")
        assert me_in(live).busy is False
    finally:
        driver.close()
        driver.switch_to.window(first)


def test_the_seated_card_lists_who_is_on_the_ice(driver, live):
    open_game(driver, live)
    sit_beside(driver, live, ("Ann", "Bo", "Bartholomew The Third", "Di", "Ed"))
    assert driver.find_element(By.ID, "starting").text.startswith("Starting in ")
    browser.wait_for(driver, "document.querySelectorAll('#ice li').length === 5")
    names = [item.text for item in driver.find_elements(By.CSS_SELECTOR, "#ice li")]
    assert names == ["Ann", "Bo", "Bartholomew…", "Di", "+2"]


def test_the_end_card_names_the_winner_and_play_again_starts_the_next_round(driver, live):
    sit_and_start(driver, live)
    end_the_round(live)
    browser.wait_for(driver, "document.body.dataset.stage === 'results'")
    browser.wait_for(driver, "!document.getElementById('end').hidden")
    assert driver.find_element(By.ID, "again").text == "Play again"
    assert driver.find_element(By.ID, "end-head").text
    assert not driver.find_element(By.ID, "title").is_displayed()
    driver.find_element(By.ID, "again").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'starting'", timeout=10)
    assert not driver.find_element(By.ID, "end").is_displayed()
    assert driver.find_element(By.ID, "count").is_displayed()


FAMILY = "👨‍👩‍👧"
LONG_NAME = "A" * 14 + FAMILY + "BBBB"


def only_these_survive(live, survivors):
    match = match_of(live)

    async def drown():
        for number in range(6):
            if number not in survivors:
                match.round.fall(number)

    run(live, drown())


def end_head(driver):
    browser.wait_for(driver, "document.body.dataset.stage === 'results'", timeout=10)
    browser.wait_for(driver, "!document.getElementById('end').hidden")
    head = driver.find_element(By.ID, "end-head").text
    # The name sits between marks that keep a right-to-left name from turning the sentence around
    return head.replace("⁨", "").replace("⁩", "")


def test_the_end_card_says_you_win(driver, live):
    sit_and_start(driver, live)
    only_these_survive(live, {0})
    assert end_head(driver) == "You win!"
    assert driver.find_element(By.ID, "end-text").text == "Last penguin on the ice."
    assert "Knockouts: " in driver.find_element(By.ID, "end-stats").text


def test_the_end_card_names_another_winner_cut_by_whole_characters(driver, live):
    open_game(driver, live)
    sit_beside(driver, live, (LONG_NAME,))
    browser.wait_for(driver, "document.querySelectorAll('#ice li').length === 2")
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    only_these_survive(live, {0})
    # 16 characters at most, counting the family emoji as one
    assert end_head(driver) == "A" * 14 + FAMILY + "… wins"
    assert "of 6." in driver.find_element(By.ID, "end-text").text


def test_the_end_card_with_no_winner_has_no_place_line(driver, live):
    sit_and_start(driver, live)
    only_these_survive(live, set())
    assert end_head(driver) == "Nobody made it"
    assert not driver.find_element(By.ID, "end-text").is_displayed()
    assert driver.find_element(By.ID, "end-stats").text.startswith("Round ")


def test_status_and_busy_reach_the_hub_only_when_they_change(driver, live):
    sit_and_start(driver, live)
    me = me_in(live)
    WebDriverWait(driver, 10).until(lambda _: me.busy and me.status == "Round 1 · 6 left")
    time.sleep(0.6)
    sent = []
    original = live.server.presence.update

    async def counting(conn, data):
        sent.append(data)
        await original(conn, data)

    live.server.presence.update = counting
    match = match_of(live)
    before = match.tick_count
    time.sleep(2.5)
    # A few seconds of frames reached the page, and none of them said anything new
    assert match.tick_count - before > 30
    assert sent == []


def test_the_browser_preview_says_to_open_it_in_discord(driver, live):
    driver.get(f"{live.url}/")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(driver, "!document.getElementById('title').hidden", timeout=20)
    assert driver.find_element(By.ID, "note").text == "Open Penguin Wars in Discord to play."
    assert not driver.find_element(By.ID, "go").is_displayed()


def test_the_title_card_fits_a_sideways_phone_without_scrolling(driver, live):
    open_game(driver, live)
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride", {"width": 844, "height": 390, "deviceScaleFactor": 1, "mobile": False}
    )
    try:
        browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
        steps = driver.execute_script("return document.querySelectorAll('#title .steps li').length")
        assert steps == 4
        fits = driver.execute_script(
            "const card = document.querySelector('#title .card');"
            "const r = card.getBoundingClientRect();"
            "return [card.scrollHeight - card.clientHeight, r.top, innerHeight - r.bottom];"
        )
        assert fits[0] <= 0, fits
        bar = driver.execute_script("return document.getElementById('bar').getBoundingClientRect().bottom")
        assert fits[1] >= bar - 1 and fits[2] >= 0, (fits, bar)
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_someone_not_seated_during_the_results_can_press_play(driver, live):
    open_game(driver, live)
    seat_others(live, ("Ann", "Bo"))
    match = match_of(live)

    async def hurry():
        match.countdown = 1

    run(live, hurry())
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    end_the_round(live)
    browser.wait_for(driver, "document.body.dataset.stage === 'results'")
    assert driver.find_element(By.ID, "go").text == "Play"
    driver.find_element(By.ID, "go").click()
    # The results are held at 30 seconds, and the seconds run on through the 10-second countdown after them
    browser.wait_for(driver, "/^Next round in (39|40)$/.test(document.getElementById('starting').textContent)")

    async def others_stand():
        for seat in match.seats:
            if seat.human and seat.user_id != fakes.MEMBER_ID:
                seat.clear()
        match.dirty = True

    # Left alone, the results wait for this player, so nothing says a round is coming
    run(live, others_stand())
    browser.wait_for(driver, "document.getElementById('starting').textContent === \"Start when you're ready\"")
    assert driver.find_element(By.ID, "start").is_displayed()
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'starting'", timeout=5)


def shown_words(driver):
    return driver.execute_script("return document.body.innerText")


def test_alone_the_end_card_stays_until_play_again(driver, live):
    with sized(driver, "narrow upright"):
        sit_and_start(driver, live)
        # A player on the ice has no Shop button beside the hint
        assert not driver.find_element(By.ID, "watch-shop").is_displayed()
        match = match_of(live)
        only_these_survive(live, {0})
        assert end_head(driver) == "You win!"

        async def nearly_over():
            # One update from the end, were the results counting down
            match.stage_left = 1

        run(live, nearly_over())
        time.sleep(1)
        assert match.stage == "results" and driver.find_element(By.ID, "end").is_displayed()
        words = shown_words(driver)
        assert "Next round" not in words and "Starting in" not in words, words
        keep_shot(driver, "solo-end-card.png")
        driver.find_element(By.ID, "again").click()
        browser.wait_for(driver, "document.body.dataset.stage === 'starting'", timeout=5)


def test_left_alone_in_a_seat_the_card_offers_start_and_nothing_counts_down(driver, live):
    with sized(driver, "narrow upright"):
        open_game(driver, live)
        sit_beside(driver, live)
        assert driver.find_element(By.ID, "starting").text.startswith("Starting in ")
        match = match_of(live)

        async def ann_stands():
            match.seats[0].clear()
            match.dirty = True

        run(live, ann_stands())
        browser.wait_for(driver, "document.getElementById('starting').textContent === \"Start when you're ready\"")
        time.sleep(1.2)
        assert match.stage == "waiting" and match.countdown is None
        assert driver.find_element(By.ID, "starting").text == "Start when you're ready"
        assert driver.find_element(By.ID, "start").is_displayed()
        keep_shot(driver, "solo-waiting.png")
        driver.find_element(By.ID, "start").click()
        browser.wait_for(driver, "document.body.dataset.stage === 'starting'", timeout=5)


BUTTON_PRESSES = """
return [...document.querySelectorAll('button')].filter((b) => b.offsetParent !== null).map((b) => {
  const r = b.getBoundingClientRect();
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return {id: b.id || b.className, ok: !!hit && b.contains(hit)};
});
"""


def check_presses(driver, wanted):
    buttons = driver.execute_script(BUTTON_PRESSES)
    assert wanted <= {button["id"] for button in buttons}, buttons
    assert all(button["ok"] for button in buttons), buttons


@pytest.mark.parametrize("size", list(SIZES))
def test_every_button_gets_its_press(driver, live, size):
    width, height = SIZES[size]
    open_game(driver, live)
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    try:
        browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
        check_presses(driver, {"go", "back", "mute"})
        sit_beside(driver, live)
        check_presses(driver, {"start", "stand", "back", "mute"})
        driver.find_element(By.ID, "start").click()
        browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
        end_the_round(live)
        browser.wait_for(driver, "!document.getElementById('end').hidden")
        check_presses(driver, {"again", "back", "mute"})
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_the_people_button_sits_in_the_bar(driver, live):
    open_game(driver, live)
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False}
    )
    try:
        browser.wait_for(driver, "document.querySelector('.bar .hub-people')")
        assert not driver.execute_script("return document.querySelector('body > .hub-people')")
        rects = driver.execute_script(
            "return [...document.querySelectorAll('.bar button, .bar .chip')].filter((e) => e.offsetParent !== null)"
            ".map((e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })"
        )
        assert len(rects) >= 3
        rects.sort()
        for left, right in zip(rects, rects[1:]):
            assert left[2] <= right[0] + 0.5, rects
        assert max(rect[1] for rect in rects) - min(rect[1] for rect in rects) < 12, rects
        assert max(rect[2] for rect in rects) <= 390
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


# ---------- The world on screen ----------


def drawn(driver, name):
    """Whether a named thing in the 3D scene is showing, and where it is drawn: [shown, x, y, z]"""
    return driver.execute_script(
        "const thing = pc.Application.getApplication().root.findByName(arguments[0]);"
        "const at = thing.getPosition();"
        "return [thing.enabled, at.x, at.y, at.z];",
        name,
    )


def tile_drawn(driver, index):
    """What the graphics card is handed for a tile: [shown, x, y, z, its cap]. An empty slot draws nothing"""
    return driver.execute_script(TILE_SLOT + "return tileSlot(arguments[0]);", index)


def start_tile_trail(driver, index):
    """Note what is drawn for a tile on every screen update, in window.trail as [ms, shown, x, y, z]"""
    driver.execute_script(
        TILE_SLOT + "window.trail = [];"
        "pc.Application.getApplication().on('update', () => {"
        "  window.trail.push([performance.now(), ...tileSlot(arguments[0]).slice(0, 4)]);"
        "});",
        index,
    )


def start_trail(driver, name):
    """Note where a named thing is drawn on every screen update, in window.trail as [ms, shown, x, y, z]"""
    driver.execute_script(
        "const app = pc.Application.getApplication();"
        "const thing = app.root.findByName(arguments[0]);"
        "window.trail = [];"
        "app.on('update', () => {"
        "  const at = thing.getPosition();"
        "  window.trail.push([performance.now(), thing.enabled, at.x, at.y, at.z]);"
        "});",
        name,
    )


def shown_tags(driver):
    """The name tags showing, as [text, font pixels, is own tag, opacity]"""
    return driver.execute_script(
        "return [...document.querySelectorAll('.tag')].filter((tag) => !tag.hidden).map((tag) => {"
        "  const style = getComputedStyle(tag);"
        "  return [tag.textContent, parseFloat(style.fontSize), tag.classList.contains('you'), Number(style.opacity)];"
        "});"
    )


def calm(live):
    """No CPU moves from here on, so only the test moves a penguin"""
    match = match_of(live)

    async def stop():
        for seat in match.seats:
            seat.cpu = None

    run(live, stop())


def wait_for_penguins(driver):
    browser.wait_for(driver, "document.querySelectorAll('.tag:not([hidden])').length > 0", timeout=10)


def glide(live, seat=0, power=0.5):
    """Slide this seat's penguin toward +x. At half power it goes about 2.2 and stops after about 1.2 seconds"""
    match = match_of(live)

    async def push():
        match.round.penguins[seat].cd = 0.0
        assert match.round.slide(seat, 1, 0, power)

    run(live, push())


def test_six_tags_show_during_a_round(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    tags = shown_tags(driver)
    assert len(tags) == 6
    names = [seat.name if len(seat.name) <= 13 else f"{seat.name[:12]}…" for seat in match_of(live).seats]
    assert sorted(tag[0] for tag in tags) == sorted(names)
    assert all(tag[1] >= 10 for tag in tags)
    assert [tag[2] for tag in tags].count(True) == 1
    assert next(tag for tag in tags if tag[2])[0] == match_of(live).seats[0].name
    assert not problems_in_console(driver)


def test_the_canvas_draws_the_ice(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    # "Go!" covers the middle of the screen as the round starts
    browser.wait_for(driver, "document.getElementById('count').hidden")
    shot = Image.open(BytesIO(driver.get_screenshot_as_png())).convert("RGB")
    red, green, blue = shot.getpixel((shot.width // 2, shot.height // 2))
    # The snow on the middle tile. The sea is #14587a at its brightest
    assert min(red, green, blue) > 170, (red, green, blue)


def test_with_no_round_the_whole_ice_shows_and_no_penguins(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    assert all(tile_drawn(driver, index)[0] for index in range(61))
    assert not any(drawn(driver, f"penguin-{seat}")[0] for seat in range(6))
    assert shown_tags(driver) == []
    assert not problems_in_console(driver)


def test_only_the_players_penguin_has_the_ring(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    rings = driver.execute_script(
        "const root = pc.Application.getApplication().root;"
        "return [0, 1, 2, 3, 4, 5].map((seat) => Boolean(root.findByName(`penguin-${seat}`).findByName('ring')));"
    )
    assert rings == [True, False, False, False, False, False]


def test_penguins_stay_on_the_ice_through_the_results_then_it_clears(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)

    async def melt():
        match.round.floe.tiles[0].state, match.round.floe.tiles[0].t = 3, 0.0
        match.round.events.append(["gone", 0])

    run(live, melt())
    WebDriverWait(driver, 5).until(lambda d: not tile_drawn(d, 0)[0])
    end_the_round(live)
    browser.wait_for(driver, "document.body.dataset.stage === 'results'")
    assert drawn(driver, "penguin-0")[0] and len(shown_tags(driver)) == 6
    assert not tile_drawn(driver, 0)[0]

    async def next_stage():
        # Alone, the results wait for the player, so they step out and the results run out
        match.stand(match.room.connections[0])
        match.stage_left = 1

    run(live, next_stage())
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    browser.wait_for(driver, "document.querySelectorAll('.tag:not([hidden])').length === 0")
    assert not any(drawn(driver, f"penguin-{seat}")[0] for seat in range(6))
    assert all(tile_drawn(driver, index)[0] for index in range(61))


def test_the_next_round_moves_though_its_frame_numbers_start_over(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    time.sleep(1)
    end_the_round(live)
    browser.wait_for(driver, "!document.getElementById('end').hidden")
    driver.find_element(By.ID, "again").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    calm(live)
    before = drawn(driver, "penguin-0")[1]
    glide(live)
    # Frame numbers are back near 0 here. A page keeping the old round's order would hold the penguin still
    WebDriverWait(driver, 3).until(lambda d: drawn(d, "penguin-0")[1] > before + 1)
    assert not problems_in_console(driver)


def test_a_tile_cracks_shakes_sinks_and_goes_on_the_bots_events(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    match = match_of(live)
    rest = tile_drawn(driver, 0)[1]

    async def crack():
        tile = match.round.floe.tiles[0]
        tile.state, tile.t = 1, 0.0
        match.round.events.append(["crack", 0])

    start_tile_trail(driver, 0)
    run(live, crack())
    WebDriverWait(driver, 6).until(lambda d: not tile_drawn(d, 0)[0])
    trail = driver.execute_script("return window.trail")
    shaken = {row[2] for row in trail if row[1] and row[3] == 0}
    assert len(shaken) > 2 and all(abs(x - rest) < 0.2 for x in shaken)
    assert min(row[3] for row in trail) < -0.5


def test_someone_arriving_mid_round_sees_the_right_ice(driver, live):
    sit_and_start(driver, live)
    match = match_of(live)

    async def melt():
        tiles = match.round.floe.tiles
        # Wound far back, so each tile holds its state for the whole test
        for index, state in ((0, 3), (1, 2), (2, 1)):
            tiles[index].state, tiles[index].t = state, -1000.0

    run(live, melt())
    first = driver.current_window_handle
    driver.switch_to.new_window("tab")
    try:
        open_game(driver, live)
        wait_for_penguins(driver)
        gone, sinking, cracked, whole = [tile_drawn(driver, index) for index in (0, 1, 2, 3)]
        assert not gone[0] and gone[4] == []
        assert sinking[0] and -1.6 <= sinking[2] < -0.1 and sinking[4] == ["crack"]
        assert cracked[0] and cracked[4] == ["crack"]
        assert whole[0] and whole[4] == ["snow"]
        start_tile_trail(driver, 2)
        browser.wait_for(driver, "window.trail.length > 4", timeout=10)
        trail = driver.execute_script("return window.trail")
        assert len({row[2] for row in trail}) > 1
    finally:
        driver.close()
        driver.switch_to.window(first)


def test_someone_arriving_mid_round_sees_seals_and_the_fish(driver, live):
    sit_and_start(driver, live)
    match = match_of(live)

    async def set_up():
        match.round.fall(1)
        match.round.penguins[1].seal.t = 0.0
        match.round.penguins[1].seal.state = 1
        match.round.spawn_fish()

    run(live, set_up())
    fish = match.round.fish
    first = driver.current_window_handle
    driver.switch_to.new_window("tab")
    try:
        open_game(driver, live)
        wait_for_penguins(driver)
        seal = drawn(driver, "seal-1")
        assert seal[0] and not drawn(driver, "penguin-1")[0]
        assert not drawn(driver, "seal-2")[0] and drawn(driver, "penguin-2")[0]
        # It has been swimming for a while, so it doesn't come out from under the ice
        assert hypot(seal[1], seal[3]) > ice_reach(match.round.floe)
        shown, x, _, z = drawn(driver, "fish")
        assert shown and (x, z) == pytest.approx((fish.x, fish.z), abs=0.02)
    finally:
        driver.close()
        driver.switch_to.window(first)


def test_a_fish_comes_and_goes_on_the_bots_events(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)

    async def spawn():
        match.round.spawn_fish()

    run(live, spawn())
    WebDriverWait(driver, 5).until(lambda d: drawn(d, "fish")[0])

    async def take():
        match.round.fish = None
        match.round.events.append(["gulp", 0])

    run(live, take())
    WebDriverWait(driver, 5).until(lambda d: not drawn(d, "fish")[0])


def test_a_fallen_penguins_tag_follows_its_seal(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)

    async def drown():
        match.round.fall(0)

    run(live, drown())
    # Under the water for a moment, with no tag
    browser.wait_for(driver, "document.querySelectorAll('.tag:not([hidden])').length === 5")
    WebDriverWait(driver, 5).until(lambda d: drawn(d, "seal-0")[0])
    browser.wait_for(driver, "document.querySelector('.tag.you.seal:not([hidden])')")
    assert not drawn(driver, "penguin-0")[0]
    moved = driver.execute_script(
        "const tag = document.querySelector('.tag.you');"
        "const before = tag.style.transform;"
        "return new Promise((done) => setTimeout(() => done([before, tag.style.transform]), 800));"
    )
    assert moved[0] != moved[1]


def test_an_away_persons_tag_is_dimmed(driver, live):
    open_game(driver, live)
    sit_beside(driver, live)
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    wait_for_penguins(driver)
    match = match_of(live)

    async def drop():
        match.seats[0].dropped_at = match.clock()
        match.dirty = True

    run(live, drop())
    browser.wait_for(driver, "document.querySelector('.tag.away')")
    tags = {tag[0]: tag[3] for tag in shown_tags(driver)}
    assert tags["Ann"] < 0.8
    assert tags[match.seats[1].name] == 1


def test_an_event_riding_a_snapshot_runs_like_a_frame_event(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)

    async def drown():
        match.round.fall(1)

    run(live, drown())
    WebDriverWait(driver, 5).until(lambda d: drawn(d, "seal-1")[0])
    start_trail(driver, "seal-1")
    target = {}

    async def dive():
        # Set together, so the bot sends the dive's event on a snapshot in place of a frame
        seal = match.round.penguins[1].seal
        seal.cd = 0.0
        assert match.round.dive(1, 0.0, 30.0)
        target["x"], target["z"] = seal.tx, seal.tz
        match.dirty = True

    run(live, dive())
    time.sleep(1.4)
    trail = driver.execute_script("return window.trail")
    # Only the event knows where the seal is going: the snapshot's seal list says just "diving"
    assert min(hypot(row[2] - target["x"], row[4] - target["z"]) for row in trail) < 0.4
    assert max(row[3] for row in trail) > 0.3


def snapshots_every_few_updates(live, seconds):
    match = match_of(live)

    async def spam():
        for _ in range(int(seconds * 10)):
            match.dirty = True
            await asyncio.sleep(0.1)

    asyncio.run_coroutine_threadsafe(spam(), live.loop)


def test_a_penguin_lies_down_and_faces_where_it_slides_then_stands(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    driver.execute_script(
        "const app = pc.Application.getApplication();"
        "const penguin = app.root.findByName('penguin-0');"
        "window.leans = [];"
        "app.on('update', () => window.leans.push(penguin.children[0].getLocalEulerAngles().x));"
    )
    # Strong enough to lie down for, and not so strong that it leaves the ice
    glide(live, power=0.6)
    time.sleep(2.2)
    leans = driver.execute_script("return window.leans")
    assert max(leans) > 60
    assert abs(leans[-1]) < 10
    facing = driver.execute_script(
        "const turn = new pc.Vec3(0, 0, 1);"
        "pc.Application.getApplication().root.findByName('penguin-0').getWorldTransform().transformVector(turn, turn);"
        "return [turn.x, turn.z];"
    )
    assert facing[0] > 0.9 and abs(facing[1]) < 0.4


def test_a_penguins_fish_and_brace_show_from_its_flags(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)

    def set_flags(fish, brace):
        async def change():
            match.round.penguins[1].fish, match.round.penguins[1].brace = fish, brace

        run(live, change())

    read = "return ['beak-fish', 'shield'].map((name) =>" + (
        " pc.Application.getApplication().root.findByName('penguin-1').findByName(name).enabled)"
    )
    set_flags(True, 30.0)
    WebDriverWait(driver, 5).until(lambda d: d.execute_script(read) == [True, True])
    set_flags(False, 0.0)
    WebDriverWait(driver, 5).until(lambda d: d.execute_script(read) == [False, False])


def test_snapshots_during_play_never_make_a_penguin_jump(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    start_trail(driver, "penguin-0")
    snapshots_every_few_updates(live, 1.2)
    glide(live)
    time.sleep(1.5)
    trail = driver.execute_script("return window.trail")
    start, end = trail[0][2], trail[-1][2]
    assert end - start > 1.5
    # While it slides. It starts at half of the top speed of 11, and slows from there
    moving = [row for row in trail if start + 0.1 < row[2] < end - 0.5]
    assert len(moving) > 10
    steps = [(later[2] - earlier[2], (later[0] - earlier[0]) / 1000) for earlier, later in zip(moving, moving[1:])]
    assert all(step >= -1e-6 for step, _ in steps), steps
    # A page starting over on a snapshot jumps ahead, then stands still until its delay has built back up
    assert max(step / seconds for step, seconds in steps) < 11, steps
    assert sum(step < 1e-6 for step, _ in steps) <= 3, steps


def test_snapshots_never_restart_a_fall_or_a_sinking_tile(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)

    async def go():
        match.round.fall(1)
        tile = match.round.floe.tiles[0]
        tile.state, tile.t = 2, 0.0
        match.round.events.append(["sink", 0])

    start_trail(driver, "penguin-1")
    # Only while the tile is drawn: one that has gone under is taken away, and its emptied slot reads as height 0
    driver.execute_script(
        TILE_SLOT + "window.tileTrail = [];"
        "pc.Application.getApplication().on('update', () => {"
        "  const [shown, , height] = tileSlot(0);"
        "  if (shown) { window.tileTrail.push(height); }"
        "});"
    )
    snapshots_every_few_updates(live, 1.0)
    run(live, go())
    time.sleep(1.1)
    heights = [row[3] for row in driver.execute_script("return window.trail") if row[1]]
    assert len(heights) > 2 and heights[-1] < 0
    assert all(later <= earlier + 1e-6 for earlier, later in zip(heights, heights[1:])), heights
    tile = driver.execute_script("return window.tileTrail")
    assert min(tile) < -0.3
    assert all(later <= earlier + 1e-6 for earlier, later in zip(tile, tile[1:])), tile


def test_a_page_back_from_the_background_jumps_to_now(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    # Chrome closes the link of a frozen page, and the page connects again once it is back
    keep_company(live)
    start_trail(driver, "penguin-0")
    browser.wait_for(driver, "window.trail.length > 3")
    driver.execute_cdp_cmd("Page.setWebLifecycleState", {"state": "frozen"})
    try:
        glide(live)
        time.sleep(1.6)
    finally:
        driver.execute_cdp_cmd("Page.setWebLifecycleState", {"state": "active"})
        # Freezing also hides the page, and thawing doesn't show it again. This keeps the tab drawing, for later tests too
        driver.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
    bot_x = match_of(live).round.penguins[0].x
    assert bot_x > 1.5
    WebDriverWait(driver, 5).until(lambda d: abs(drawn(d, "penguin-0")[1] - bot_x) < 0.05)
    trail = driver.execute_script("return window.trail")
    gap, back = max((later[0] - earlier[0], index + 1) for index, (earlier, later) in enumerate(zip(trail, trail[1:])))
    assert gap > 1000, "the page never stopped drawing"
    # It waits where it was until news arrives, then it is where the bot says, with nothing drawn in between
    xs = [row[2] for row in trail[back:]]
    assert all(abs(x) < 0.05 or abs(x - bot_x) < 0.05 for x in xs), (bot_x, xs)


def test_a_page_not_drawing_with_its_link_open_lands_where_the_round_is(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)

    async def hold_the_ice():
        match.round.floe.crack_timer = 1000.0

    run(live, hold_the_ice())

    async def drown(seat, x, z):
        match.round.penguins[seat].x, match.round.penguins[seat].z = x, z
        match.round.fall(seat)

    # The engine asks for each next screen update through this method, so with it empty the drawing stops, just as on a
    # hidden page, while the connection keeps delivering frames. The scene is the update listener that takes events
    driver.execute_script(
        "const app = pc.Application.getApplication();"
        "const scene = app._callbacks.get('update').find((listener) => listener.scope.onEvent).scope;"
        "window.heard = [];"
        "scene.onEvent((event) => window.heard.push(event));"
        "app.requestAnimationFrame = () => {};"
    )
    time.sleep(0.1)
    glide(live)
    run(live, drown(1, 3.0, 0.0))
    time.sleep(1.4)
    # Fallen too recently for its seal to be up when the page comes back
    run(live, drown(2, -3.0, 0.0))
    time.sleep(0.6)
    driver.execute_script(
        "const app = pc.Application.getApplication();"
        "const names = ['penguin-0', 'seal-1', 'penguin-2'];"
        "const things = names.map((name) => app.root.findByName(name));"
        "window.paths = names.map(() => []);"
        "app.on('update', () => things.forEach((thing, index) => {"
        "  const at = thing.getPosition();"
        "  window.paths[index].push([thing.enabled, at.x, at.z]);"
        "}));"
        "delete app.requestAnimationFrame;"
        "app.requestAnimationFrame();"
    )
    WebDriverWait(driver, 5).until(lambda d: drawn(d, "seal-2")[0])
    slider, seal, faller = driver.execute_script("return window.paths")
    # What moved while nothing was drawn is simply where it is now, from the first update back
    bot_x = match.round.penguins[0].x
    assert bot_x > 1.5 and all(abs(x - bot_x) < 0.05 for _, x, _ in slider), (bot_x, slider[:20])
    # A fall that happened while nothing was drawn is over, and doesn't play again
    assert not any(shown for shown, _, _ in faller), faller[:20]
    # A seal that came up unseen is already out on its swim circle, with no swim out from the penguin's old spot
    circle = ice_reach(match.round.floe) + 0.8
    assert seal[0][0] and all(abs(hypot(x, z) - circle) < 0.1 for _, x, z in seal), (circle, seal[:20])
    # Nothing that happened in the frames it skipped plays an effect. The next event, seen live, does
    heard = driver.execute_script("return window.heard")
    assert [event for event in heard if event[0] in ("slide", "fall", "seal")] == [["seal", 2]], heard


# ---------- Controls ----------

# The scene, reached the way the no-drawing test reaches it
SCENE = "pc.Application.getApplication()._callbacks.get('update').find((listener) => listener.scope.onEvent).scope"
# How many draws the last drawn frame took. The lobby only draws some of its frames, and a frame that isn't drawn
# counts none. The first call starts the count, so it is asked once before the number is needed
LAST_DRAWS = (
    "(() => {"
    f"  const scene = {SCENE};"
    "  if (!scene.drawsSeen) {"
    "    scene.drawsSeen = [0];"
    "    scene.app.on('frameend', () => {"
    "      scene.drawsSeen[0] = scene.app.stats.drawCalls.total || scene.drawsSeen[0];"
    "    });"
    "  }"
    "  return scene.drawsSeen[0];"
    "})()"
)
# One slot is a matrix of 16 numbers: the place sits at 12 to 14, and the last is 0 in an empty slot
TILE_SLOT = f"""
const floe = {SCENE}.floe;
const inUse = (copies, index) => copies.cells[index * 16 + 15] !== 0;
function tileSlot(index) {{
  const at = index * 16;
  const cap = ["snow", "crack"].filter((name) => inUse(floe[name], index));
  return [inUse(floe.body, index), floe.body.cells[at + 12], floe.body.cells[at + 13], floe.body.cells[at + 14], cap];
}}
"""
FINGER_FRAME = 1 / 60
TOUCH = RADIUS * 2
SHIELD = "pc.Application.getApplication().root.findByName('penguin-0').findByName('shield').enabled"
# The middle of the screen, and a pull straight down the page: the penguin at the top of the ice slides down it
PRESS = (195, 300)
PULLED = (195, 420)


@pytest.fixture
def phone(driver):
    """A phone-sized page that takes fingers"""
    width, height = SIZES["phone"]
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 2})
    try:
        yield driver
    finally:
        # A finger left down by a failed test would swallow the next test's touches
        try:
            touch(driver, "touchCancel")
        except WebDriverException:
            pass
        driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": False})
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def touch(driver, kind, *points):
    spots = [{"x": x, "y": y} for x, y in points]
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": kind, "touchPoints": spots})


def pull(driver, start=PRESS, end=PULLED, steps=6):
    """One finger down at start and moved to end, a frame per move, and still down"""
    (x0, y0), (x1, y1) = start, end
    touch(driver, "touchStart", start)
    for step in range(1, steps + 1):
        time.sleep(FINGER_FRAME)
        touch(driver, "touchMove", (x0 + (x1 - x0) * step / steps, y0 + (y1 - y0) * step / steps))


def lift(driver):
    touch(driver, "touchEnd")


def tap(driver, spot=PRESS):
    touch(driver, "touchStart", spot)
    lift(driver)


def on_the_ice(driver, live):
    """In a round with nothing else moving, the ice holding still and the player's penguin ready to go"""
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)

    async def hold_the_ice():
        match.round.floe.crack_timer = 1000.0

    run(live, hold_the_ice())
    browser.wait_for(driver, f"{SCENE}.pens[0].row[3] === 0")


def as_a_seal(driver, live):
    """As on_the_ice, then knocked in, with the seal up and allowed to dive"""
    on_the_ice(driver, live)
    match = match_of(live)

    async def drown():
        match.round.fall(0)

    run(live, drown())
    WebDriverWait(driver, 5).until(lambda d: drawn(d, "seal-0")[0])
    time.sleep(1)


def hear_the_page(live):
    """A list that fills with everything the page sends the match from now on"""
    match = match_of(live)
    original = match.message
    heard = []

    async def listening(conn, data):
        heard.append(data)
        await original(conn, data)

    async def listen():
        match.message = listening

    run(live, listen())
    return heard


def hold_the_bot(live):
    """The bot stops updating: it still hears the page, but no frame or event comes back"""
    match = match_of(live)

    async def idle():
        pass

    async def hold():
        match.tick = idle

    run(live, hold())


def screen_spot(driver, x, z):
    return driver.execute_script(
        f"const at = {SCENE}.camera.camera.worldToScreen(new pc.Vec3(arguments[0], 0, arguments[1]));"
        "return [at.x, at.y];",
        x,
        z,
    )


def facing(driver, name):
    """Which way a named thing in the 3D scene points, as [x, z] of length 1"""
    return driver.execute_script(
        "const turn = new pc.Vec3(0, 0, 1);"
        "pc.Application.getApplication().root.findByName(arguments[0]).getWorldTransform().transformVector(turn, turn);"
        "turn.y = 0;"
        "turn.normalize();"
        "return [turn.x, turn.z];",
        name,
    )


def arrow(driver):
    """The aim arrow: [shown, length of the shaft, its color]"""
    return driver.execute_script(
        "const app = pc.Application.getApplication();"
        "const root = app.root.findByName('arrow');"
        "const shaft = root.children[0];"
        "const color = shaft.render.meshInstances[0].material.emissive;"
        "return [root.enabled, shaft.getLocalScale().z, [color.r, color.g, color.b]];"
    )


def test_a_drag_moves_the_penguin_before_the_bot_answers(driver, live, phone):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    hold_the_bot(live)
    driver.execute_script(
        "const tag = document.querySelector('.tag.you');"
        "window.tagTrail = [];"
        "pc.Application.getApplication().on('prerender', () => {"
        "  window.tagTrail.push([performance.now(), tag.style.transform]);"
        "});"
        "document.getElementById('game').addEventListener('pointerup', () => {"
        "  window.lifted = performance.now();"
        "}, true);"
    )
    pull(driver)
    lift(driver)
    browser.wait_for(driver, "window.lifted && window.tagTrail.at(-1)[0] > window.lifted + 100")
    trail, lifted = driver.execute_script("return [window.tagTrail, window.lifted]")
    before = [row[1] for row in trail if row[0] < lifted]
    after = [row[1] for row in trail if row[0] >= lifted]
    assert len(set(before)) == 1, before
    # The same frame the finger came up
    assert after[0] != before[-1]
    assert len(set(after)) > 3
    assert heard and len(heard[0]["slide"]) == 3
    assert not problems_in_console(driver)


def test_a_lifted_finger_slides_where_the_bot_slides(driver, live, phone):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    match = match_of(live)
    driver.execute_script(
        f"const scene = {SCENE};"
        "window.squashes = [];"
        "scene.app.on('update', () => window.squashes.push(scene.pens[0].squash));"
    )
    pull(driver)
    lift(driver)
    WebDriverWait(driver, 3).until(lambda _: heard)
    dx, dz, power = heard[0]["slide"]
    assert dx == pytest.approx(0, abs=1e-6) and dz == pytest.approx(-1)
    assert power == pytest.approx(110 / 124.8)
    penguin = match.round.penguins[0]
    time.sleep(2.2)
    assert penguin.vz == 0 and penguin.z < 0
    # Handed back to the bot's stream, right on its stopping place
    browser.wait_for(driver, f"!{SCENE}.prediction.ghost.active")
    assert drawn(driver, "penguin-0")[3] == pytest.approx(penguin.z, abs=0.02)
    # One squash when the finger lifted, with none added when the bot's own event landed
    squashes = driver.execute_script("return window.squashes")
    assert max(squashes) > 0.3
    assert sum(later > earlier for earlier, later in zip(squashes, squashes[1:])) == 1


def test_a_slide_while_knocked_lands_where_the_bot_stops(driver, live, phone):
    on_the_ice(driver, live)
    match = match_of(live)
    first = match.round.penguins[0]

    async def knock():
        first.vx = 8.0

    run(live, knock())
    pull(driver, end=(195, 350))
    lift(driver)
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active", timeout=2)
    # Well under the 2.5 seconds a ghost gets, since it stops short of the bot's penguin
    browser.wait_for(driver, f"!{SCENE}.prediction.ghost.active", timeout=1.7)
    WebDriverWait(driver, 1).until(lambda d: drawn(d, "penguin-0")[1] == pytest.approx(first.x, abs=0.02))


def test_a_slide_the_bot_refuses_hands_back(driver, live, phone):
    on_the_ice(driver, live)
    match = match_of(live)

    async def not_ready_yet():
        match.round.penguins[0].cd = 30.0

    # The page still thinks the penguin is ready, since no frame comes back to say otherwise
    hold_the_bot(live)
    run(live, not_ready_yet())
    start = drawn(driver, "penguin-0")[3]
    pull(driver)
    lift(driver)
    WebDriverWait(driver, 1).until(lambda d: drawn(d, "penguin-0")[3] < start - 0.5)
    WebDriverWait(driver, 2).until(lambda d: drawn(d, "penguin-0")[3] == pytest.approx(start, abs=0.02))


def watch_the_bubble(driver):
    """Note on every drawn frame whether the bubble is up, in window.bubble as [ms, up], and when the finger lifts"""
    driver.execute_script(
        "window.bubble = [];"
        f"pc.Application.getApplication().on('update', () => window.bubble.push([performance.now(), {SHIELD}]));"
        "document.getElementById('game').addEventListener('pointerup', () => {"
        "  window.lifted = performance.now();"
        "}, true);"
    )


def bubble_after_the_tap(driver):
    """The bubble's frames from the lift on, and how many seconds it stayed up in one piece"""
    rows, lifted = driver.execute_script("return [window.bubble, window.lifted]")
    after = [row for row in rows if row[0] >= lifted]
    ups = [index for index, row in enumerate(after) if row[1]]
    assert ups == list(range(ups[-1] + 1)), "the bubble came up late or blinked"
    return after, (after[ups[-1]][0] - after[0][0]) / 1000


def test_a_tap_braces_and_shows_the_bubble(driver, live, phone):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    watch_the_bubble(driver)
    tap(driver)
    WebDriverWait(driver, 2).until(lambda _: heard == [{"brace": True}])
    assert match_of(live).round.penguins[0].cd > 0
    time.sleep(1.2)
    # Up from the first frame after the lift, through the bot's own brace in one piece, then gone
    after, seconds = bubble_after_the_tap(driver)
    assert after[0][1]
    assert match_of(live).tuning.brace_seconds - 0.05 <= seconds < 1
    assert not after[-1][1]
    assert not problems_in_console(driver)


def test_a_brace_the_bot_never_answers_loses_its_bubble(driver, live, phone):
    on_the_ice(driver, live)
    hold_the_bot(live)
    watch_the_bubble(driver)
    tap(driver)
    time.sleep(0.7)
    after, seconds = bubble_after_the_tap(driver)
    assert after[0][1]
    assert 0.2 <= seconds <= 0.4
    assert not after[-1][1]
    # The ring is back to ready, since the bot never took the brace
    assert driver.execute_script(f"return {SCENE}.prediction.waitOn(0)") == 0


def test_the_ring_greys_on_the_lift_before_the_bot_answers(driver, live, phone):
    on_the_ice(driver, live)
    ring = (
        "pc.Application.getApplication().root.findByName('penguin-0').findByName('ring')"
        ".render.meshInstances[0].material.emissive.r"
    )
    ready = driver.execute_script(f"return {ring}")
    hold_the_bot(live)
    pull(driver)
    lift(driver)
    # Well inside the 0.6 seconds the bot gets to answer
    time.sleep(0.2)
    assert driver.execute_script(f"return {ring}") < ready
    # With no answer the page takes the slide back, and the ring goes back to the bot's word
    browser.wait_for(driver, f"{ring} === {ready}", timeout=2)


def test_a_long_press_does_nothing(driver, live, phone):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    touch(driver, "touchStart", PRESS)
    time.sleep(0.4)
    lift(driver)
    time.sleep(0.2)
    assert heard == []
    assert not driver.execute_script(f"return {SHIELD}")


@pytest.mark.parametrize("how", ["touchCancel", "capture lost", "blur", "page hide", "page hidden"])
def test_a_cancelled_drag_fires_nothing_and_hides_the_arrow(driver, live, phone, how):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    driver.execute_script(
        "document.getElementById('game').addEventListener('pointerdown', (e) => {"
        "  window.finger = e.pointerId;"
        "}, true);"
    )
    pull(driver)
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[0])
    cancels = {
        "capture lost": "document.getElementById('game').releasePointerCapture(window.finger)",
        "blur": "window.dispatchEvent(new Event('blur'))",
        "page hide": "window.dispatchEvent(new Event('pagehide'))",
        "page hidden": "Object.defineProperty(document, 'hidden', { value: true, configurable: true });"
        "document.dispatchEvent(new Event('visibilitychange'));"
        "delete document.hidden;",
    }
    if how == "touchCancel":
        touch(driver, "touchCancel")
    else:
        driver.execute_script(cancels[how])
    if how == "capture lost":
        # The browser sends the loss of capture along with the next touch event, which may be a while off
        touch(driver, "touchMove", PULLED)
    WebDriverWait(driver, 2).until(lambda d: not arrow(d)[0])
    if how != "touchCancel":
        lift(driver)
    time.sleep(0.3)
    assert heard == []
    assert not arrow(driver)[0]
    assert driver.execute_script(f"return {SCENE}.pens[0].windup") == 0


@pytest.mark.parametrize("size", ["sideways", "desktop"])
def test_the_controls_work_at_every_size(driver, live, phone, size):
    width, height = SIZES[size]
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    check_presses(driver, {"back", "mute"})
    middle = (width / 2, height / 2)
    pull(driver, middle, (width / 2, height / 2 + 80))
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[0])
    lift(driver)
    WebDriverWait(driver, 2).until(lambda _: heard)
    assert heard[0]["slide"][2] == pytest.approx(70 / (min(width, height) * 0.32))
    time.sleep(1)
    tap(driver, middle)
    WebDriverWait(driver, 2).until(lambda _: {"brace": True} in heard)


def test_a_drag_ends_with_the_round(driver, live, phone):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    pull(driver)
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[0])
    end_the_round(live)
    WebDriverWait(driver, 3).until(lambda d: not arrow(d)[0])
    lift(driver)
    time.sleep(0.2)
    assert heard == []


def test_the_screen_turning_ends_a_drag(driver, live, phone):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    pull(driver)
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[0])
    width, height = SIZES["sideways"]
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    WebDriverWait(driver, 2).until(lambda d: not arrow(d)[0])
    lift(driver)
    time.sleep(0.3)
    assert heard == []


def finger_spots(driver, kind, spots):
    """Fingers by number going down, moving or lifting. A finger left out of a touchMove stays where it is, and
    touchEnd lifts only the fingers it names"""
    points = [{"x": x, "y": y, "id": finger} for finger, (x, y) in spots.items()]
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})


def test_a_second_finger_takes_over_the_drag(driver, live, phone):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    finger_spots(driver, "touchStart", {0: PRESS})
    time.sleep(FINGER_FRAME)
    finger_spots(driver, "touchMove", {0: PULLED})
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[0])
    other, old_spot, new_spot = (100, 300), (195, 520), (100, 420)
    finger_spots(driver, "touchStart", {0: PULLED, 1: other})
    # The aim belongs to the new finger now, and it hasn't pulled at all
    WebDriverWait(driver, 2).until(lambda d: not arrow(d)[0])
    # The old finger moving does nothing
    finger_spots(driver, "touchMove", {0: old_spot, 1: other})
    time.sleep(0.1)
    assert not arrow(driver)[0]
    finger_spots(driver, "touchMove", {0: old_spot, 1: new_spot})
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[0])
    # Nor does it lifting
    finger_spots(driver, "touchEnd", {0: old_spot})
    time.sleep(0.1)
    assert heard == [] and arrow(driver)[0]
    touch(driver, "touchEnd")
    WebDriverWait(driver, 2).until(lambda _: heard)
    assert heard[0]["slide"][2] == pytest.approx(110 / (min(SIZES["phone"]) * 0.32))


def test_no_aim_work_runs_with_no_drag(driver, live, phone):
    on_the_ice(driver, live)
    driver.execute_script(
        "const controls = pc.Application.getApplication()._callbacks.get('update')"
        "  .find((listener) => listener.scope.drawAim).scope;"
        "const moves = controls.moves;"
        "window.looks = 0;"
        "controls.moves = function () {"
        "  window.looks += 1;"
        "  return moves.call(this);"
        "};"
    )
    time.sleep(0.2)
    assert driver.execute_script("return window.looks") == 0
    pull(driver)
    time.sleep(0.1)
    assert driver.execute_script("return window.looks") > 0
    touch(driver, "touchCancel")


def test_a_new_round_ends_a_live_ghost(driver, live, phone):
    on_the_ice(driver, live)
    match = match_of(live)
    pull(driver)
    lift(driver)
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active", timeout=2)

    async def next_round():
        match.end_round()
        match.play_again = True

    run(live, next_round())
    browser.wait_for(driver, f"{SCENE}.round === 2", timeout=2)
    assert not driver.execute_script(f"return {SCENE}.prediction.ghost.active")
    time.sleep(0.1)
    assert drawn(driver, "penguin-0")[3] == pytest.approx(match.round.penguins[0].z, abs=0.02)


def test_losing_the_seat_ends_a_live_ghost(driver, live, phone):
    on_the_ice(driver, live)
    match = match_of(live)
    pull(driver)
    lift(driver)
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active", timeout=2)

    async def lose_the_seat():
        match.end_round()
        match.stage_left = 30 * 30
        match.seats[0].clear()
        match.dirty = True

    run(live, lose_the_seat())
    browser.wait_for(driver, f"{SCENE}.mySeat === null", timeout=2)
    assert not driver.execute_script(f"return {SCENE}.prediction.ghost.active")


def test_a_live_ghost_lands_on_the_round_across_a_reconnect(driver, live, phone):
    on_the_ice(driver, live)
    keep_company(live)
    match = match_of(live)
    pull(driver)
    lift(driver)
    # Once the bot has answered the slide: a connection closed before its next tick makes the page give the ghost up
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active && {SCENE}.prediction.slideLeft === 0", timeout=2)
    run(live, match.room.connections[0].close(1012))
    browser.wait_for(driver, "!document.getElementById('banner').hidden", timeout=2)
    browser.wait_for(driver, "document.getElementById('banner').hidden", timeout=8)
    browser.wait_for(driver, f"!{SCENE}.prediction.ghost.active", timeout=4)
    penguin = match.round.penguins[0]
    WebDriverWait(driver, 4).until(lambda _: penguin.vz == 0)
    WebDriverWait(driver, 2).until(lambda d: drawn(d, "penguin-0")[3] == pytest.approx(penguin.z, abs=0.02))


def test_a_drag_ends_when_the_connection_drops(driver, live, phone):
    on_the_ice(driver, live)
    keep_company(live)
    heard = hear_the_page(live)
    pull(driver)
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[0])
    run(live, match_of(live).room.connections[0].close(1012))
    WebDriverWait(driver, 3).until(lambda d: not arrow(d)[0])
    lift(driver)
    time.sleep(0.2)
    assert heard == []


def test_fingers_do_nothing_before_the_round(driver, live, phone):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    driver.find_element(By.ID, "go").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'starting'", timeout=10)
    match = match_of(live)

    async def stay():
        match.stage_left = 30 * 30

    run(live, stay())
    heard = hear_the_page(live)
    pull(driver)
    time.sleep(0.1)
    assert not arrow(driver)[0]
    lift(driver)
    tap(driver)
    time.sleep(0.2)
    assert heard == []


def test_fingers_do_nothing_for_someone_watching(driver, live, phone):
    open_game(driver, live)
    seat_others(live, NAMES)
    match = match_of(live)

    async def hurry():
        match.countdown = 1

    run(live, hurry())
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    wait_for_penguins(driver)
    heard = hear_the_page(live)
    pull(driver)
    time.sleep(0.1)
    assert not arrow(driver)[0]
    lift(driver)
    tap(driver)
    time.sleep(0.2)
    assert heard == []


@pytest.mark.parametrize("spot", ["#mute", "#round", ".bar .grow"])
def test_a_drag_never_starts_on_the_bar(driver, live, phone, spot):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    left, top = driver.execute_script(
        "const box = document.querySelector(arguments[0]).getBoundingClientRect();"
        "return [box.left + box.width / 2, box.top + box.height / 2];",
        spot,
    )
    pull(driver, (left, top), (left, top + 120))
    time.sleep(0.1)
    assert not arrow(driver)[0]
    lift(driver)
    time.sleep(0.2)
    assert heard == []


def real_reach(speed, tuning):
    """How far a slide at this speed goes, in the bot's own steps of friction"""
    gone = 0.0
    while speed > 0:
        speed = friction(speed, DT, tuning)
        gone += speed * DT
    return gone


def test_the_arrow_shows_the_slide_and_the_penguin_leans_into_it(driver, live, phone):
    on_the_ice(driver, live)
    match = match_of(live)
    pull(driver)
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[0])
    time.sleep(0.5)
    shown, length, color = arrow(driver)
    power = 110 / 124.8
    reach = real_reach(power * match.tuning.slide_speed, match.tuning)
    assert shown and length == pytest.approx(reach - 0.94, abs=0.01)
    # It points where the penguin goes, sits on the drawn penguin, and warms up from yellow to orange with the pull
    assert facing(driver, "arrow") == pytest.approx([0, -1], abs=0.01)
    assert drawn(driver, "arrow")[1] == pytest.approx(drawn(driver, "penguin-0")[1])
    assert drawn(driver, "arrow")[3] == pytest.approx(drawn(driver, "penguin-0")[3])
    assert color == pytest.approx([1, 0.81 - 0.5 * power, 0.2 - 0.1 * power], abs=0.01)
    lean = driver.execute_script(
        "const penguin = pc.Application.getApplication().root.findByName('penguin-0');"
        "return penguin.children[0].getLocalEulerAngles().x;"
    )
    assert facing(driver, "penguin-0") == pytest.approx([0, -1], abs=0.05)
    assert lean == pytest.approx(-12 * power, abs=0.5)
    touch(driver, "touchCancel")


def test_the_arrow_turns_orange_for_a_fish_and_grey_while_waiting(driver, live, phone):
    on_the_ice(driver, live)
    match = match_of(live)

    async def give_a_fish():
        match.round.penguins[0].fish = True

    async def make_it_wait():
        match.round.penguins[0].cd = 30.0

    pull(driver)
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[0])
    time.sleep(0.2)
    plain = arrow(driver)[1]
    run(live, give_a_fish())
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[2] == pytest.approx([1, 0.6, 0.15], abs=0.01))
    assert arrow(driver)[1] > plain
    run(live, make_it_wait())
    WebDriverWait(driver, 2).until(lambda d: arrow(d)[2] == pytest.approx([0.45, 0.5, 0.55], abs=0.01))
    touch(driver, "touchCancel")


def test_a_fish_slide_starts_faster_on_the_page_too(driver, live, phone):
    on_the_ice(driver, live)
    match = match_of(live)

    async def give_a_fish():
        match.round.penguins[0].fish = True

    run(live, give_a_fish())
    browser.wait_for(driver, f"{SCENE}.pens[0].row[2] & 4")
    driver.execute_script(
        f"const ghost = {SCENE}.prediction.ghost;"
        "const start = ghost.start;"
        "ghost.start = function (x, z, dx, dz, speed) {"
        "  window.opening = speed;"
        "  start.call(this, x, z, dx, dz, speed);"
        "};"
    )
    pull(driver)
    lift(driver)
    browser.wait_for(driver, "window.opening", timeout=2)
    assert driver.execute_script("return window.opening") == pytest.approx(
        110 / 124.8 * match.tuning.slide_speed * match.tuning.fish_boost
    )


def test_the_hint_teaches_each_move_the_first_time(driver, live, phone):
    on_the_ice(driver, live)
    assert hint_line(driver) == "Drag back anywhere, let go to slide"
    pull(driver)
    lift(driver)
    WebDriverWait(driver, 2).until(lambda d: hint_line(d) == "Tap to brace when someone slides at you")
    time.sleep(1.4)
    tap(driver)
    WebDriverWait(driver, 2).until(lambda d: hint_line(d) is None)
    match = match_of(live)

    async def drown():
        match.round.fall(0)

    run(live, drown())
    WebDriverWait(driver, 5).until(lambda d: hint_line(d) == "You're a seal now. Tap near the edge to splash")
    time.sleep(1)
    tap(driver, screen_spot(driver, 3.5, 0))
    WebDriverWait(driver, 2).until(lambda d: hint_line(d) is None)


def test_the_hint_fades_away_with_its_words_still_on(driver, live, phone):
    on_the_ice(driver, live)
    pull(driver)
    lift(driver)
    time.sleep(1.4)
    words = driver.execute_script("return document.getElementById('hint').textContent")
    assert words.startswith("Tap to brace")
    driver.execute_script(
        "const hint = document.getElementById('hint');"
        "window.fade = [];"
        "pc.Application.getApplication().on('update', () => {"
        "  window.fade.push([Number(getComputedStyle(hint).opacity), hint.textContent]);"
        "});"
    )
    tap(driver)
    time.sleep(0.8)
    fade = driver.execute_script("return window.fade")
    assert fade[0][0] == 1 and fade[-1][0] == 0
    # A pop would go straight from one to the other
    assert sum(0.1 < opacity < 0.9 for opacity, _ in fade) > 10
    assert {line for _, line in fade} == {words}


def test_the_hint_clears_the_hubs_frame_rate_counter(driver, live, phone):
    on_the_ice(driver, live)
    top = driver.execute_script("return document.getElementById('hint').getBoundingClientRect().bottom")
    driver.switch_to.default_content()
    browser.wait_for(driver, "document.querySelector('.fps').textContent")
    assert top <= driver.execute_script("return document.querySelector('.fps').getBoundingClientRect().top")


def test_a_seal_tap_dives(driver, live, phone):
    as_a_seal(driver, live)
    heard = hear_the_page(live)
    match = match_of(live)
    seal = match.round.penguins[0].seal
    start_trail(driver, "seal-0")
    driver.execute_script(
        f"const scene = {SCENE};"
        "window.diveClock = [];"
        "scene.app.on('update', () => {"
        "  if (scene.pens[0].seal.state === 'dive') {"
        "    window.diveClock.push(scene.pens[0].seal.t);"
        "  }"
        "});"
    )
    tap(driver, screen_spot(driver, 3.5, 0.5))
    WebDriverWait(driver, 2).until(lambda _: seal.state != 1)
    angle = heard[0]["splash"]
    assert angle == pytest.approx(0.1419, abs=0.02)
    # The seal heads for the very spot the bot picked
    x, z, _ = match.round.floe.edge_point(angle)
    assert (seal.tx, seal.tz) == pytest.approx((x, z))
    target = driver.execute_script(f"const seal = {SCENE}.pens[0].seal; return [seal.tx, seal.tz];")
    assert target == pytest.approx([x, z], abs=0.01)
    time.sleep(1.2)
    # Down, then up out of the water at the spot
    assert max(row[3] for row in driver.execute_script("return window.trail")) > 0.3
    # The bot's answer put it on the spot without starting the dive over
    clock = driver.execute_script("return window.diveClock")
    assert clock and all(later >= earlier for earlier, later in zip(clock, clock[1:])), clock
    assert not problems_in_console(driver)


def test_a_seal_starts_its_dive_before_the_bot_answers_and_stops_if_it_never_does(driver, live, phone):
    as_a_seal(driver, live)
    hold_the_bot(live)
    start_trail(driver, "seal-0")
    tap(driver, screen_spot(driver, 3.5, 0.5))
    time.sleep(0.15)
    assert driver.execute_script(f"return {SCENE}.pens[0].seal.state") == "dive"
    time.sleep(0.4)
    assert driver.execute_script(f"return {SCENE}.pens[0].seal.state") == "swim"
    heights = [row[3] for row in driver.execute_script("return window.trail")]
    assert min(heights) < heights[0] - 0.1


def test_a_seal_just_up_ignores_taps_as_the_bot_would(driver, live, phone):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    match = match_of(live)

    async def drown():
        match.round.fall(0)

    run(live, drown())
    WebDriverWait(driver, 5).until(lambda d: drawn(d, "seal-0")[0])
    tap(driver, screen_spot(driver, 3.5, 0))
    time.sleep(0.2)
    assert heard == []


def test_a_page_back_from_the_background_lands_a_sliding_ghost_on_the_round(driver, live, phone):
    on_the_ice(driver, live)
    # Chrome closes the link of a frozen page, and the page connects again once it is back
    keep_company(live)
    start_trail(driver, "penguin-0")
    browser.wait_for(driver, "window.trail.length > 3")
    pull(driver)
    lift(driver)
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active", timeout=2)
    # An earlier test may have left this on for the shared browser, and a page with it on keeps drawing while frozen
    driver.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": False})
    driver.execute_cdp_cmd("Page.setWebLifecycleState", {"state": "frozen"})
    try:
        time.sleep(2.6)
    finally:
        driver.execute_cdp_cmd("Page.setWebLifecycleState", {"state": "active"})
        driver.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
    bot_z = match_of(live).round.penguins[0].z
    assert bot_z < 0
    WebDriverWait(driver, 5).until(lambda d: abs(drawn(d, "penguin-0")[3] - bot_z) < 0.05)
    trail = driver.execute_script("return window.trail")
    gap, back = max((later[0] - earlier[0], index + 1) for index, (earlier, later) in enumerate(zip(trail, trail[1:])))
    assert gap > 1000, "the page never stopped drawing"
    # Waits on one spot until news arrives, then it is where the bot says, with no glide in between
    zs = [row[4] for row in trail[back:]]
    assert all(abs(z - zs[0]) < 0.05 or abs(z - bot_z) < 0.05 for z in zs), (bot_z, zs)


def test_a_page_not_drawing_lets_go_of_its_ghost(driver, live, phone):
    on_the_ice(driver, live)
    pull(driver)
    lift(driver)
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active", timeout=2)
    driver.execute_script("pc.Application.getApplication().requestAnimationFrame = () => {};")
    time.sleep(2.6)
    driver.execute_script(
        "const app = pc.Application.getApplication();"
        "const penguin = app.root.findByName('penguin-0');"
        "window.path = [];"
        "app.on('update', () => window.path.push(penguin.getPosition().z));"
        "delete app.requestAnimationFrame;"
        "app.requestAnimationFrame();"
    )
    browser.wait_for(driver, "window.path.length > 5")
    bot_z = match_of(live).round.penguins[0].z
    path = driver.execute_script("return window.path")
    assert all(abs(z - bot_z) < 0.05 for z in path), (bot_z, path[:20])
    assert not driver.execute_script(f"return {SCENE}.prediction.ghost.active")


def stop_drawing(driver):
    driver.execute_script("pc.Application.getApplication().requestAnimationFrame = () => {};")


def start_drawing(driver):
    driver.execute_script(
        "const app = pc.Application.getApplication();delete app.requestAnimationFrame;app.requestAnimationFrame();"
    )


def test_a_ghost_ends_on_frames_the_page_skipped(driver, live, phone):
    on_the_ice(driver, live)
    pull(driver)
    lift(driver)
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active", timeout=2)
    stop_drawing(driver)
    # Enough frames to push some out unseen. This reads the ghost with the page still not drawing
    time.sleep(0.45)
    assert not driver.execute_script(f"return {SCENE}.prediction.ghost.active")
    start_drawing(driver)


def held_frames(live):
    """Everything the bot broadcasts waits, until the coroutine this gives back lets it all go at once"""
    match = match_of(live)
    original = match.room.broadcast
    held = []

    async def wait(message):
        held.append(message)

    async def hold():
        match.room.broadcast = wait

    async def let_go():
        match.room.broadcast = original
        for message in held:
            await original(message)

    run(live, hold())
    return let_go


def test_a_burst_of_frames_blends_a_ghost_back(driver, live, phone):
    on_the_ice(driver, live)
    trail_of_my_penguin(driver)
    pull(driver)
    lift(driver)
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active", timeout=2)
    time.sleep(0.1)
    let_go = held_frames(live)
    # A stall about as long as the page waits before it treats itself as away, with a whole buffer's worth of frames in it
    time.sleep(0.49)
    run(live, let_go())
    browser.wait_for(driver, f"!{SCENE}.prediction.ghost.active", timeout=1)
    time.sleep(0.3)
    assert report_jump(driver, "burst") <= 20
    gaps = driver.execute_script("return window.gaps")
    assert len(gaps) == 1 and gaps[0] > 0.5


def test_a_ghost_ends_on_a_long_stop_in_drawing_even_with_no_news(driver, live, phone):
    on_the_ice(driver, live)
    # No frames come, so none are skipped: only the stop itself can show the page was away
    hold_the_bot(live)
    start = drawn(driver, "penguin-0")[3]
    pull(driver)
    lift(driver)
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active", timeout=2)
    stop_drawing(driver)
    time.sleep(0.8)
    start_drawing(driver)
    time.sleep(0.05)
    assert not driver.execute_script(f"return {SCENE}.prediction.ghost.active")
    assert drawn(driver, "penguin-0")[3] == pytest.approx(start, abs=0.02)


# ---------- The hand-back on a slow connection ----------


def slow_frames(live, seconds=0.2):
    """Everything the bot broadcasts reaches the pages this much later"""
    match = match_of(live)
    original = match.room.broadcast

    async def late(message):
        live.loop.call_later(seconds, lambda: asyncio.ensure_future(original(message)))

    async def slow():
        match.room.broadcast = late

    run(live, slow())


def trail_of_my_penguin(driver):
    """Note on every drawn frame where the player's name tag and penguin are on screen, in window.tagTrail, and how far
    the ghost was from the bot's stream each time it handed back, in window.gaps"""
    driver.execute_script(
        f"const scene = {SCENE};"
        "const tag = document.querySelector('.tag.you');"
        "window.tagTrail = [];"
        "window.gaps = [];"
        "scene.app.on('prerender', () => {"
        "  const spot = scene.tagSpot(scene.pens[scene.mySeat]);"
        "  const [left, top] = tag.style.transform.match(/-?[0-9.]+/g).map(Number);"
        "  window.tagTrail.push([performance.now(), left, top, spot.x, spot.y, scene.pens[scene.mySeat].z]);"
        "});"
        "const prediction = scene.prediction;"
        "const handBack = prediction.handBack;"
        "prediction.handBack = function () {"
        "  if (this.ghost.active && this.bot) {"
        "    window.gaps.push(Math.hypot(this.ghost.x - this.bot.x, this.ghost.z - this.bot.z));"
        "  }"
        "  handBack.call(this);"
        "};"
    )


def biggest_step(rows, column):
    return max(hypot(b[column] - a[column], b[column + 1] - a[column + 1]) for a, b in zip(rows, rows[1:]))


def report_jump(driver, name):
    """The biggest step the penguin takes on screen between two frames of a 60 Hz phone. This browser draws far faster
    than a phone, so its own frames would make every step look small"""
    rows, gaps = driver.execute_script("return [window.tagTrail, window.gaps]")
    phone_frames = [rows[0]]
    for row in rows[1:]:
        if row[0] - phone_frames[-1][0] >= 1000 / 60:
            phone_frames.append(row)
    penguin = biggest_step(phone_frames, 3)
    tag, raw_tag, raw_penguin = biggest_step(phone_frames, 1), biggest_step(rows, 1), biggest_step(rows, 3)
    print(
        f"{name}: at 60 Hz penguin {penguin:.1f} px, tag {tag:.1f} px. Every frame ({len(rows)}, "
        f"{(rows[-1][0] - rows[0][0]) / len(rows):.1f} ms each): penguin {raw_penguin:.1f} px, tag {raw_tag:.1f} px. "
        f"Hand-back gaps in units: {[round(gap, 2) for gap in gaps]}"
    )
    return penguin


def test_no_jump_handing_a_slide_back_on_a_slow_connection(driver, live, phone):
    on_the_ice(driver, live)
    slow_frames(live)
    time.sleep(0.5)
    trail_of_my_penguin(driver)
    pull(driver)
    lift(driver)
    time.sleep(3)
    assert report_jump(driver, "slide") <= 20
    assert not driver.execute_script(f"return {SCENE}.prediction.ghost.active")


def run_a_hit(driver, live, delay, fish=False):
    """The player slides at full speed into a penguin just out of touch, on a connection this slow. Gives the two
    penguins, and how far past the touching point the player's penguin was ever drawn, in units"""
    on_the_ice(driver, live)
    match = match_of(live)
    first, other, beyond = match.round.penguins[0], match.round.penguins[1], match.round.penguins[3]

    # The penguin past it moves aside, or the second hit lands by the ghost and hands it back by luck
    async def stand_in_the_way():
        other.x, other.z = first.x, first.z - 1.1
        beyond.x = -3.0
        first.fish = fish

    run(live, stand_in_the_way())
    time.sleep(0.3)
    touching = other.z + TOUCH
    slow_frames(live, delay)
    time.sleep(0.5)
    trail_of_my_penguin(driver)
    pull(driver)
    lift(driver)
    WebDriverWait(driver, 2).until(lambda _: other.vz < -1)
    browser.wait_for(driver, f"!{SCENE}.prediction.ghost.active", timeout=1.5)
    time.sleep(1)
    rows = driver.execute_script("return window.tagTrail")
    return first, other, touching - min(row[5] for row in rows)


@pytest.mark.parametrize("delay", [0.06, 0.2])
def test_a_hit_stops_the_penguin_at_the_touch_on_a_slow_connection(driver, live, phone, delay):
    first, other, past = run_a_hit(driver, live, delay)
    print(f"past the touch at {delay * 1000:.0f} ms: {past:.2f} units, {past * 30:.0f} px on a phone")
    # A whole penguin is 0.94 wide, so this is a penguin stopped by what it hit, not one sliding through it
    assert past < 0.3
    assert report_jump(driver, f"hit at {delay * 1000:.0f} ms") <= 20
    assert drawn(driver, "penguin-0")[3] == pytest.approx(first.z, abs=0.05)


def test_a_fish_slide_rolls_on_through_the_touch(driver, live, phone):
    first, other, past = run_a_hit(driver, live, 0.06, fish=True)
    print(f"past the touch with a fish: {past:.2f} units")
    assert past > 0.5
    # The drawn penguin would follow the bot's past the touch anyway, so ask what the ghost itself was told it weighs
    assert driver.execute_script(f"return {SCENE}.prediction.ghost.mass") == HEAVY_MASS
    assert drawn(driver, "penguin-0")[3] == pytest.approx(first.z, abs=0.05)


def test_no_jump_being_hit_on_a_slow_connection(driver, live, phone):
    on_the_ice(driver, live)
    match = match_of(live)
    first, other = match.round.penguins[0], match.round.penguins[1]

    async def come_from_the_side():
        other.x, other.z = first.x - 2.6, first.z - 1.2

    run(live, come_from_the_side())
    time.sleep(0.3)
    slow_frames(live)
    time.sleep(0.5)
    trail_of_my_penguin(driver)
    pull(driver, end=(195, 370))
    lift(driver)

    async def slam():
        other.cd = 0.0
        assert match.round.slide(1, 1, 0, 0.8)

    time.sleep(0.05)
    run(live, slam())
    browser.wait_for(driver, f"!{SCENE}.prediction.ghost.active", timeout=2)
    time.sleep(1)
    assert first.x > 0.3, "the slide missed"
    assert report_jump(driver, "being hit") <= 20


# ---------- Hits that land ----------

FX = f"{SCENE}.fx"


def record_effects(driver):
    """Note in window.sounds every sound asked for, and on every drawn frame in window.fxTrail: the time, how many
    particles of each kind show, the freeze left, the camera's shake and where penguin 1 is drawn"""
    driver.execute_script(
        f"const scene = {SCENE};"
        "const sound = scene.fx.sound;"
        "const play = sound.play;"
        "window.sounds = [];"
        "window.soundTimes = [];"
        "sound.play = function (kind, strength) {"
        "  window.sounds.push(kind);"
        "  window.soundTimes.push(performance.now());"
        "  return play.call(this, kind, strength);"
        "};"
        "window.heardEvents = [];"
        "const runEvent = scene.runEvent;"
        "scene.runEvent = function (event, ...rest) {"
        "  window.heardEvents.push([event[0], performance.now()]);"
        "  return runEvent.call(this, event, ...rest);"
        "};"
        "window.fxTrail = [];"
        "window.squashes = [];"
        "const other = scene.pens[1];"
        "scene.app.on('update', () => {"
        "  window.squashes.push(other.squash);"
        "  const counts = scene.fx.cloudList.map((cloud) => cloud.instance.instancingCount);"
        "  window.fxTrail.push([performance.now(), counts, scene.fx.freeze, scene.fx.shake, other.x, other.z]);"
        "});"
    )


def test_a_cpu_round_plays_its_effects_without_errors(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    match = match_of(live)

    async def hurry():
        match.set_tuning(replace(match.tuning, ice_speed=8.0))

    run(live, hurry())
    record_effects(driver)
    driver.find_element(By.ID, "go").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'results'", timeout=90)
    browser.wait_for(driver, "!document.getElementById('end').hidden")
    sounds = driver.execute_script("return window.sounds")
    assert {"crack", "sink", "splash"} <= set(sounds), sounds
    assert driver.execute_script(f"return {FX}.sound.ac.state") == "running"
    trail = driver.execute_script("return window.fxTrail")
    # Spray showed at some point, and every count stayed inside its pool
    assert max(sum(row[1]) for row in trail) > 0
    assert not problems_in_console(driver)


def test_a_hit_throws_stars_holds_the_drawing_and_shakes_the_camera(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)
    first, other = match.round.penguins[0], match.round.penguins[1]

    async def line_up():
        match.round.floe.crack_timer = 1000.0
        first.x, first.z = 0.0, 0.0
        other.x, other.z = 2.2, 0.0

    run(live, line_up())
    time.sleep(0.5)
    record_effects(driver)

    async def slam():
        other.cd = 0.0
        assert match.round.slide(1, -1, 0, 0.9)

    run(live, slam())
    browser.wait_for(driver, "window.sounds.includes('bonk') || window.sounds.includes('bounce')", timeout=5)
    time.sleep(0.5)
    trail = driver.execute_script("return window.fxTrail")
    assert max(row[1][0] for row in trail) > 0, "no stars"
    assert max(row[3] for row in trail) >= 0.12, "no shake"
    held = [row for row in trail if row[2] > 0]
    assert held, "the drawing never held"
    # The struck penguin stood still on screen for as long as the hit held it, and it was held for no longer than the
    # longest freeze
    still = 0
    for earlier, later in zip(held, held[1:]):
        if (earlier[4], earlier[5]) == (later[4], later[5]):
            still += later[0] - earlier[0]
    assert still >= 30, still
    assert held[-1][0] - held[0][0] <= 130
    assert not problems_in_console(driver)


SOUND_OPEN = "document.getElementById('sound-panel').open"
MASTER_GAIN = f"return {FX}.sound.master.gain.value"


def open_sound_panel(driver):
    driver.find_element(By.ID, "mute").click()
    browser.wait_for(driver, SOUND_OPEN)


def close_sound_panel_by_escape(driver):
    driver.switch_to.active_element.send_keys(Keys.ESCAPE)
    browser.wait_for(driver, f"!{SOUND_OPEN}")


def forget_sound_settings(driver):
    """The sound settings stay in the browser between tests, so each test that saves one takes it away again"""
    driver.execute_script(
        "localStorage.removeItem('penguinwars:muted'); localStorage.removeItem('penguinwars:sfx-volume');"
    )


def test_the_first_press_unlocks_sound_and_the_switch_is_saved(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    assert driver.execute_script(f"return {FX}.sound.ac") is None
    try:
        open_sound_panel(driver)
        assert driver.execute_script(f"return [{FX}.sound.ac !== null, {FX}.sound.muted]") == [True, False]
        switch = driver.find_element(By.ID, "sfx-switch")
        switch.click()
        assert driver.execute_script(f"return {FX}.sound.muted") is True
        assert switch.get_attribute("aria-checked") == "false"
        assert driver.execute_script("return localStorage.getItem('penguinwars:muted')") == "on"
        switch.click()
        assert driver.execute_script(f"return {FX}.sound.muted") is False
        assert switch.get_attribute("aria-checked") == "true"
        assert speaker(driver) == ["on"]
        assert driver.execute_script("return localStorage.getItem('penguinwars:muted')") == "off"
    finally:
        forget_sound_settings(driver)


def test_a_freeze_never_makes_the_ghost_jump_or_let_go(driver, live, phone):
    on_the_ice(driver, live)
    trail_of_my_penguin(driver)
    driver.execute_script(
        f"const scene = {SCENE};"
        "window.drops = 0;"
        "const drop = scene.prediction.drop;"
        "scene.prediction.drop = function () { window.drops += 1; return drop.call(this); };"
    )
    pull(driver)
    lift(driver)
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active", timeout=2)
    # Three hits in a row, each holding the drawing for its longest freeze
    for _ in range(3):
        driver.execute_script(f"{FX}.hit(0, 0, 1)")
        time.sleep(0.15)
    time.sleep(1)
    assert driver.execute_script("return window.drops") == 0
    # In the world's units, since the camera shakes on a hit and moves everything on screen with it
    rows = driver.execute_script("return window.tagTrail")
    phone_frames = [rows[0]]
    for row in rows[1:]:
        if row[0] - phone_frames[-1][0] >= 1000 / 60:
            phone_frames.append(row)
    speed = max(
        abs(later[5] - earlier[5]) / ((later[0] - earlier[0]) / 1000)
        for earlier, later in zip(phone_frames, phone_frames[1:])
    )
    print(f"fastest the penguin moved through three freezes: {speed:.1f} units a second")
    # The slide starts under 10 units a second and the catch-up adds half again. A jump over a freeze would be several
    # times that
    assert speed < 20
    # The draw clock caught up, and the ghost's own clock with it
    assert driver.execute_script(f"return {SCENE}.clock.lag") == 0


def test_a_lift_during_a_freeze_still_sends_its_slide_at_once(driver, live, phone):
    on_the_ice(driver, live)
    heard = hear_the_page(live)
    driver.execute_script(
        f"const scene = {SCENE};"
        "window.frozenAt = null;"
        "document.getElementById('game').addEventListener('pointerup', () => {"
        "  window.frozenAt = scene.fx.freeze;"
        "}, true);"
    )
    pull(driver)
    driver.execute_script(f"{FX}.freeze = 0.5")
    lift(driver)
    WebDriverWait(driver, 3).until(lambda _: heard)
    assert driver.execute_script("return window.frozenAt") > 0
    assert len(heard[0]["slide"]) == 3
    assert not problems_in_console(driver)


def test_a_full_load_of_particles_adds_only_a_few_draw_calls(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)

    def draw_calls():
        time.sleep(0.4)
        return driver.execute_script(f"return {SCENE}.app.stats.drawCalls.total")

    before = draw_calls()
    driver.execute_script(
        f"const fx = {FX};"
        "for (const cloud of fx.cloudList) { fx.emit(Object.keys(fx.clouds)[fx.cloudList.indexOf(cloud)],"
        "  0, 0.5, 0, cloud.size, 0.1, 0.1, 30, 0.1, 0); }"
        "for (let i = 0; i < 4; i += 1) { fx.splashRing(i, 0); }"
        "fx.freeze = 0;"
    )
    after = driver.execute_script(
        "return new Promise((done) => {  setTimeout(() => done(%s.app.stats.drawCalls.total), 400);});" % SCENE
    )
    print(f"draw calls: {before} -> {after}")
    # One draw per kind of particle (the hit stars are their own, to show over the penguins), and the four rings
    kinds = driver.execute_script(f"return {FX}.cloudList.length")
    assert after - before <= kinds + 4


# ---------- Fix round 1 ----------


def test_particles_hold_through_a_freeze_and_then_run_at_real_time(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    # One long-lived particle, aged only by the drawing's time. A hold takes its length off its ageing and catching up
    # must not give it back
    lost = driver.execute_async_script(
        "const done = arguments[arguments.length - 1];"
        f"const fx = {FX};"
        "const cloud = fx.clouds.drop;"
        "const slot = cloud.next;"
        "fx.emit('drop', 0, 5, 0, 1, 0, 0, 30, 0.1, 0);"
        "const first = cloud.life[slot];"
        "const started = performance.now();"
        "fx.freeze = 0.09;"
        "setTimeout(() => {"
        "  done((performance.now() - started) / 1000 - (first - cloud.life[slot]));"
        "}, 800);"
    )
    assert lost >= 0.07, lost


def play_into_a_paused_context(driver):
    """Pauses the sound engine, asks for 41 sounds, and gives the number of sound parts made meanwhile, the number made
    once it resumes and its state then"""
    return driver.execute_async_script(
        "const done = arguments[arguments.length - 1];"
        f"const sound = {FX}.sound;"
        "const ac = sound.ac;"
        "let made = 0;"
        "for (const name of ['createOscillator', 'createBufferSource']) {"
        "  const make = ac[name].bind(ac);"
        "  ac[name] = () => { made += 1; return make(); };"
        "}"
        "ac.suspend().then(() => {"
        "  for (let i = 0; i < 40; i += 1) { sound.play('bonk'); }"
        "  sound.play('splash');"
        "  const paused = made;"
        "  ac.resume().then(() => setTimeout(() => done([paused, made, ac.state]), 250));"
        "});"
    )


def unlock_by_mouse(driver):
    open_sound_panel(driver)
    close_sound_panel_by_escape(driver)
    assert driver.execute_script(f"return {FX}.sound.muted") is False


def test_nothing_queues_in_a_paused_sound_engine_and_nothing_bursts_on_resume(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    unlock_by_mouse(driver)
    assert play_into_a_paused_context(driver) == [0, 0, "running"]


def test_the_sound_engine_pauses_with_the_page_and_resumes(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    unlock_by_mouse(driver)
    states = driver.execute_async_script(
        "const done = arguments[arguments.length - 1];"
        f"const ac = {FX}.sound.ac;"
        "const hide = (hidden) => {"
        "  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });"
        "  document.dispatchEvent(new Event('visibilitychange'));"
        "  return new Promise((wait) => setTimeout(() => wait(ac.state), 250));"
        "};"
        "hide(true).then((away) => hide(false).then((back) => done([away, back])));"
    )
    assert states == ["suspended", "running"]


def test_a_tap_on_a_phone_unlocks_sound(driver, live, phone):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    assert driver.execute_script(f"return {FX}.sound.ac") is None
    tap(driver, (195, 60))
    browser.wait_for(driver, f"{FX}.sound.ac && {FX}.sound.ac.state === 'running'", timeout=3)


# ---------- The sound panel ----------


def middle_of(driver, selector):
    left, top, right, bottom = box_of(driver, selector)
    return (left + right) / 2, (top + bottom) / 2


def test_the_sound_button_opens_the_panel_and_a_tap_outside_escape_or_the_button_closes_it(driver, live, phone):
    on_the_ice(driver, live)
    button = driver.find_element(By.ID, "mute")
    assert button.get_attribute("aria-controls") == "sound-panel"
    assert button.get_attribute("aria-expanded") == "false"
    sound_button = middle_of(driver, "#mute")
    tap(driver, sound_button)
    browser.wait_for(driver, SOUND_OPEN)
    assert button.get_attribute("aria-expanded") == "true"
    assert driver.execute_script("return document.getElementById('sound-panel').matches(':modal')")
    try:
        # A slider dragged off the panel's end leaves it open
        start = middle_of(driver, "#sfx-volume")
        pull(driver, start, (5, start[1]))
        lift(driver)
        time.sleep(0.2)
        assert driver.execute_script(f"return {SOUND_OPEN}")
        assert driver.find_element(By.ID, "sfx-volume").get_attribute("value") == "0"
        # A tap on the ice closes it, and the game never hears it: no brace goes to the bot
        heard = hear_the_page(live)
        tap(driver)
        browser.wait_for(driver, f"!{SOUND_OPEN}")
        time.sleep(0.3)
        assert heard == []
        assert button.get_attribute("aria-expanded") == "false"
        # Escape closes it
        tap(driver, sound_button)
        browser.wait_for(driver, SOUND_OPEN)
        close_sound_panel_by_escape(driver)
        # The button hears of the close a moment after the panel shuts
        WebDriverWait(driver, 3).until(lambda _: button.get_attribute("aria-expanded") == "false")
        # So does the sound button, and that same tap doesn't open it again
        tap(driver, sound_button)
        browser.wait_for(driver, SOUND_OPEN)
        tap(driver, sound_button)
        browser.wait_for(driver, f"!{SOUND_OPEN}")
        time.sleep(0.3)
        assert not driver.execute_script(f"return {SOUND_OPEN}")
        assert heard == []
        # A connection gone for good closes it, so the message's button takes its press
        tap(driver, sound_button)
        browser.wait_for(driver, SOUND_OPEN)
        run(live, match_of(live).room.connections[0].close(4100))
        browser.wait_for(driver, f"!{SOUND_OPEN}")
        browser.wait_for(driver, "!document.getElementById('message').hidden")
        assert driver.execute_script(PRESSED_AT_MIDDLE, driver.find_element(By.ID, "message-back"))
    finally:
        forget_sound_settings(driver)


def listen_to_the_sound(driver):
    """Note in window.sounds every sound asked for, and in window.parts every sound part made"""
    driver.execute_script(
        f"const sound = {FX}.sound;"
        "const play = sound.play;"
        "window.sounds = [];"
        "window.parts = 0;"
        "sound.play = function (kind, strength) {"
        "  window.sounds.push(kind);"
        "  return play.call(this, kind, strength);"
        "};"
        "for (const name of ['createOscillator', 'createBufferSource']) {"
        "  const make = sound.ac[name].bind(sound.ac);"
        "  sound.ac[name] = () => { window.parts += 1; return make(); };"
        "}"
    )


def move_volume(driver, value, let_go=True):
    """The slider moved to this value, and let go when let_go is set"""
    driver.execute_script(
        "const slider = document.getElementById('sfx-volume');"
        "slider.value = arguments[0];"
        "slider.dispatchEvent(new Event('input', {bubbles: true}));"
        "if (arguments[1]) { slider.dispatchEvent(new Event('change', {bubbles: true})); }",
        value,
        let_go,
    )


def speaker(driver):
    """Which of the bar's speakers are drawn: on, off or both"""
    return driver.execute_script(
        "return ['sound-on', 'sound-off']"
        ".filter((id) => document.getElementById(id).getClientRects().length).map((id) => id.slice(6));"
    )


def saved_sound(driver):
    return driver.execute_script(
        "return [localStorage.getItem('penguinwars:muted'), localStorage.getItem('penguinwars:sfx-volume')]"
    )


def test_the_switch_and_slider_set_the_effects_and_come_back_after_a_reload(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    try:
        open_sound_panel(driver)
        listen_to_the_sound(driver)
        assert speaker(driver) == ["on"]
        assert driver.execute_script(MASTER_GAIN) == pytest.approx(0.55)
        # The loudness follows the slider as it moves, along a curve: 0.55 times (40 / 100) squared
        move_volume(driver, 40, let_go=False)
        assert driver.execute_script(MASTER_GAIN) == pytest.approx(0.55 * 0.4**2)
        assert saved_sound(driver) == [None, None]
        assert driver.execute_script("return window.sounds") == []
        # Let go, it is saved and a bonk plays at the new level
        move_volume(driver, 40)
        assert saved_sound(driver) == [None, "40"]
        assert driver.execute_script("return [window.sounds, window.parts > 0]") == [["bonk"], True]
        # The switch turns the effects off, and leaves the level alone
        driver.find_element(By.ID, "sfx-switch").click()
        assert driver.execute_script(f"return {FX}.sound.muted") is True
        assert speaker(driver) == ["off"]
        # Once the switch's knob has slid across
        time.sleep(0.3)
        keep_shot(driver, "sound-panel-off.png")
        assert driver.execute_script(MASTER_GAIN) == pytest.approx(0.55 * 0.4**2)
        parts = driver.execute_script("return window.parts")
        move_volume(driver, 70)
        # Pressing the switch ticks like every button, before it turns the effects off
        assert driver.execute_script("return window.sounds") == ["bonk", "tap", "bonk"]
        assert driver.execute_script("return window.parts") == parts
        assert saved_sound(driver) == ["on", "70"]
        # A new visit starts from what was saved
        open_game(driver, live)
        browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
        slider = driver.find_element(By.ID, "sfx-volume")
        assert slider.get_attribute("value") == "70"
        assert driver.execute_script("return arguments[0].style.getPropertyValue('--level')", slider) == "70%"
        assert driver.find_element(By.ID, "sfx-switch").get_attribute("aria-checked") == "false"
        assert speaker(driver) == ["off"]
        open_sound_panel(driver)
        assert driver.execute_script(f"return {FX}.sound.muted") is True
        assert driver.execute_script(MASTER_GAIN) == pytest.approx(0.55 * 0.7**2)
        # A saved volume that isn't a number from 0 to 100 means full volume
        driver.execute_script("localStorage.setItem('penguinwars:sfx-volume', '');")
        open_game(driver, live)
        browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
        assert driver.find_element(By.ID, "sfx-volume").get_attribute("value") == "100"
    finally:
        forget_sound_settings(driver)


def test_a_mouse_press_that_starts_in_the_panel_and_ends_outside_leaves_it_open(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    try:
        open_sound_panel(driver)
        slider = driver.find_element(By.ID, "sfx-volume")
        # Each let go far to the left, over the game, where the click lands on the panel's backdrop
        for start in (driver.find_element(By.ID, "sfx-name"), slider):
            ActionChains(driver).click_and_hold(start).move_by_offset(-500, 0).release().perform()
            time.sleep(0.2)
            assert driver.execute_script(f"return {SOUND_OPEN}"), start.get_attribute("id")
        assert slider.get_attribute("value") == "0"
    finally:
        forget_sound_settings(driver)


def test_the_sound_panel_works_from_the_keyboard(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    try:
        driver.execute_script("document.getElementById('mute').focus();")
        driver.switch_to.active_element.send_keys(Keys.ENTER)
        browser.wait_for(driver, SOUND_OPEN)
        # Focus moves onto the switch, and Space flips it
        assert driver.switch_to.active_element.get_attribute("id") == "sfx-switch"
        driver.switch_to.active_element.send_keys(Keys.SPACE)
        assert driver.find_element(By.ID, "sfx-switch").get_attribute("aria-checked") == "false"
        driver.switch_to.active_element.send_keys(Keys.SPACE)
        assert driver.find_element(By.ID, "sfx-switch").get_attribute("aria-checked") == "true"
        driver.switch_to.active_element.send_keys(Keys.TAB)
        assert driver.switch_to.active_element.get_attribute("id") == "sfx-volume"
        driver.switch_to.active_element.send_keys(Keys.ARROW_LEFT)
        assert saved_sound(driver) == ["off", "95"]
        # Escape closes it and hands focus back to the sound button
        close_sound_panel_by_escape(driver)
        assert driver.switch_to.active_element.get_attribute("id") == "mute"
    finally:
        forget_sound_settings(driver)


def set_safe_area(driver, inset):
    """Discord's safe area this deep on every side"""
    driver.switch_to.default_content()
    for side in ("top", "right", "bottom", "left"):
        driver.execute_script(f"document.documentElement.style.setProperty('{NOTCH.format(side)}', '{inset}px');")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(
        driver,
        f"getComputedStyle(document.documentElement).getPropertyValue('{NOTCH.format('top')}').trim() === '{inset}px'",
    )


@pytest.mark.parametrize(
    ("size", "inset"), [("desktop", 0), ("phone", 0), ("narrow upright", 0), ("sideways", 0), ("sideways", 47)]
)
def test_the_sound_panel_fits_beside_the_people_button_and_every_control_takes_its_press(driver, live, size, inset):
    # The bot owner's bar holds every button
    live.user_id = fakes.OWNER_ID
    width, height = {**SIZES, **NARROW}[size]
    with sized(driver, size):
        open_game(driver, live)
        opened = time.monotonic()
        if inset:
            set_safe_area(driver, inset)
        browser.wait_for(driver, "!document.getElementById('open-tuning').hidden")
        open_sound_panel(driver)
        # The hub's arrival notes slide out under its people button, once a player's first moments are over
        time.sleep(max(0.0, ARRIVALS_QUIET - (time.monotonic() - opened)))
        live.add_person(fakes.ADMIN_ID, where="penguinwars", status="Watching")
        browser.wait_for(driver, "document.querySelector('.hub-note')?.textContent", timeout=5)
        time.sleep(0.3)
        panel, button = box_of(driver, "#sound-panel"), box_of(driver, "#mute")
        people, note = box_of(driver, ".bar .hub-people"), box_of(driver, ".hub-note")
        edge = max(inset, 8)
        assert panel[0] >= edge and panel[1] >= edge, panel
        assert panel[2] <= width - edge and panel[3] <= height - edge, panel
        assert apart(panel, people) and apart(panel, note), (panel, people, note)
        # Right under the sound button
        assert panel[0] <= button[0] and button[2] <= panel[2] and 0 < panel[1] - button[3] < 60, (panel, button)
        for control in ("sfx-switch", "sfx-volume"):
            element = driver.find_element(By.ID, control)
            assert driver.execute_script(PRESSED_AT_MIDDLE, element), control
            assert element.size["height"] >= 44, control
        keep_shot(driver, f"sound-panel-{size.replace(' ', '-')}{'-notch' if inset else ''}.png")


def test_fish_effects_follow_the_bots_events_and_an_eaten_fish_does_not_splash(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)

    def after(events):
        driver.execute_script(
            f"const scene = {SCENE}; scene.fx.freeze = 0;"
            "for (const event of arguments[0]) { scene.runEvent(event, true); }",
            events,
        )
        time.sleep(0.15)
        return driver.execute_script(
            f"const fx = {FX}; return [fx.clouds.star.instance.instancingCount, fx.clouds.drop.instance.instancingCount,"
            " fx.clouds.snow.instance.instancingCount, fx.rings.filter((ring) => ring.t >= 0).length];"
        )

    # Lands with a burst of stars
    assert after([["fish", 300, 100]])[0] > 0
    time.sleep(1.2)
    # Sinks with spray and a ring
    _, drops, _, rings = after([["fish_gone", "sank"]])
    assert drops > 0 and rings > 0
    time.sleep(1.2)
    # Times out with a puff of snow
    driver.execute_script(f"{SCENE}.showFish(1, 1)")
    assert after([["fish_gone", "timeout"]])[2] > 0
    time.sleep(1.2)
    # Eaten: the gulp is its own event, and a fish already gone has nothing to sink
    driver.execute_script(f"{SCENE}.showFish(1, 1)")
    after([["gulp", 0]])
    time.sleep(1.2)
    _, drops, _, rings = after([["fish_gone", "sank"]])
    assert drops == 0 and rings == 0


def slam_into_a_penguin(driver, live, delay, braced=False):
    """The player slides at full speed into a penguin just out of touch, with the bot this slow to answer. Gives the
    sounds, when they played, the events as the drawing reached them and the particle counts on each frame"""
    on_the_ice(driver, live)
    match = match_of(live)
    first, other, beyond = match.round.penguins[0], match.round.penguins[1], match.round.penguins[3]

    async def stand_in_the_way():
        other.x, other.z = first.x, first.z - 1.1
        beyond.x = -3.0
        other.brace = 30.0 if braced else 0.0

    run(live, stand_in_the_way())
    time.sleep(0.3)
    slow_frames(live, delay)
    time.sleep(0.5)
    record_effects(driver)
    pull(driver)
    lift(driver)
    # A struck penguin is sent off, a braced one throws the player back
    WebDriverWait(driver, 2).until(lambda _: first.vz > 1 if braced else other.vz < -1)
    time.sleep(delay + 0.8)
    return driver.execute_script("return [window.sounds, window.soundTimes, window.heardEvents, window.fxTrail]")


def test_the_players_own_hit_plays_before_the_bots_event_and_only_once(driver, live, phone):
    sounds, times, events, trail = slam_into_a_penguin(driver, live, 0.2)
    assert sounds.count("bonk") == 1, sounds
    bonk = times[sounds.index("bonk")]
    heard = next(at for kind, at in events if kind == "hit")
    assert heard - bonk > 80, heard - bonk
    # Stars were up before the bot's word arrived
    assert any(row[1][0] > 0 for row in trail if row[0] < heard)


def test_one_hit_squashes_the_struck_penguin_once(driver, live, phone):
    slam_into_a_penguin(driver, live, 0.2)
    squashes = driver.execute_script("return window.squashes")
    # Each time the squash jumps back up, which a second flinch from the bot's own word would add to
    jumps = sum(1 for before, after in zip(squashes, squashes[1:]) if after - before > 0.3)
    assert jumps == 1, jumps


def test_a_braced_penguin_bounces_the_player_with_no_hit(driver, live, phone):
    sounds, times, events, trail = slam_into_a_penguin(driver, live, 0.2, braced=True)
    assert sounds.count("bounce") == 1, sounds
    assert "bonk" not in sounds
    assert sum(1 for kind, _ in events if kind == "bounce") == 1


def test_a_strangers_hit_during_the_players_own_touch_still_plays_at_once(driver, live, phone):
    on_the_ice(driver, live)
    match = match_of(live)
    first, other, third, fourth = (match.round.penguins[seat] for seat in (0, 1, 3, 4))

    async def line_up():
        other.x, other.z = first.x, first.z - 1.1
        third.x, third.z = first.x + 0.8, first.z - 0.5
        fourth.x, fourth.z = first.x + 0.8, first.z - 1.7

    run(live, line_up())
    time.sleep(0.3)
    slow_frames(live, 0.2)
    time.sleep(0.5)
    record_effects(driver)
    pull(driver)

    async def stranger_slams():
        fourth.cd = 0.0
        assert match.round.slide(4, 0, 1, 0.7)

    run(live, stranger_slams())
    time.sleep(0.1)
    lift(driver)
    time.sleep(1.5)
    sounds, times, events = driver.execute_script("return [window.sounds, window.soundTimes, window.heardEvents]")
    hit_times = [at for kind, at in events if kind == "hit"]
    assert hit_times, events
    # The stranger's hit is the first the page hears, and it plays then, not later in place of the player's own
    bonks = [at for kind, at in zip(sounds, times) if kind == "bonk"]
    assert any(hit_times[0] - 5 <= at <= hit_times[0] + 10 for at in bonks), (hit_times, bonks)


def test_the_effects_are_warmed_up_and_then_gone(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    time.sleep(0.5)
    warming, clouds, rings = driver.execute_script(
        f"const fx = {FX};"
        "return [fx.warming, fx.cloudList.map((cloud) => cloud.root.enabled), fx.rings.map((ring) => ring.entity.enabled)];"
    )
    # Every kind of particle a trail, cheer, splash or crate can throw was warmed with the rest
    assert len(clouds) == 14
    assert (warming, clouds, rings) == (False, [False] * 14, [False] * 4)


STAR_YELLOW = (255, 210, 63)


def pause_after_a_hit(driver, wait_ms):
    """The next hit's effects are held where they stand this long after it lands, by stopping the engine's clock, and
    the screen spots and widths in pixels of its stars are noted then in window.stars"""
    driver.execute_script(
        f"const scene = {SCENE};"
        "const emit = scene.fx.emit;"
        "window.stars = null;"
        "window.armed = false;"
        "scene.fx.emit = function (kind, ...args) {"
        "  const result = emit.call(this, kind, ...args);"
        "  if (kind !== 'burst' || window.stars !== null || window.armed) { return result; }"
        "  window.armed = true;"
        "  setTimeout(() => {"
        "    scene.app.timeScale = 0;"
        "    scene.fx.shake = 0;"
        "    setTimeout(() => {"
        "      const cloud = scene.fx.clouds.burst;"
        "      const spot = new pc.Vec3();"
        "      const found = [];"
        "      for (let i = 0; i < cloud.size; i += 1) {"
        "        if (cloud.life[i] > 0) {"
        "          const at = new pc.Vec3(cloud.x[i], cloud.y[i], cloud.z[i]);"
        "          scene.camera.camera.worldToScreen(at, spot);"
        "          const scale = cloud.big[i] * (0.3 + 0.7 * (cloud.life[i] / cloud.max[i]));"
        "          found.push([spot.x, spot.y, scale * scene.fx.unit]);"
        "        }"
        "      }"
        "      window.stars = found;"
        "    }, 150);"
        "  }, arguments[0]);"
        "  return result;"
        "};",
        wait_ms,
    )


def hit_a_penguin(driver, live):
    """A penguin slams into another, with the page's clock held when it lands"""
    on_the_ice(driver, live)
    match = match_of(live)
    first, other = match.round.penguins[0], match.round.penguins[1]

    async def line_up():
        first.x, first.z = 0.0, 0.0
        other.x, other.z = 1.6, 0.0

    run(live, line_up())
    time.sleep(0.4)

    async def slam():
        other.cd = 0.0
        assert match.round.slide(1, -1, 0, 0.9)

    return slam


@pytest.mark.parametrize("size", ["phone", "sideways", "desktop"])
def test_hit_stars_show_over_the_penguins_at_one_size_on_every_screen(driver, live, size):
    width, height = SIZES[size]
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    try:
        slam = hit_a_penguin(driver, live)
        pause_after_a_hit(driver, 40)
        run(live, slam())
        browser.wait_for(driver, "window.stars !== null", timeout=5)
        time.sleep(0.3)
        stars = driver.execute_script("return window.stars")
        shot = Image.open(BytesIO(driver.get_screenshot_as_png())).convert("RGB")
        assert len(stars) >= 8
        # Spread out over the screen, not all on one point
        far = max(hypot(a[0] - b[0], a[1] - b[1]) for a in stars for b in stars)
        assert far >= 20, far
        # About 8 px across, whatever the screen
        widths = sorted(star[2] for star in stars)
        assert 6 <= widths[len(widths) // 2] <= 11, widths
        # Yellow on the screen at the stars' own spots, though penguins stand there
        seen = 0
        for x, y, _ in stars:
            near = [
                shot.getpixel((px, py))
                for px in range(int(x) - 1, int(x) + 2)
                for py in range(int(y) - 1, int(y) + 2)
                if 0 <= px < shot.width and 0 <= py < shot.height
            ]
            seen += any(all(abs(a - b) < 40 for a, b in zip(pixel, STAR_YELLOW)) for pixel in near)
        assert seen >= len(stars) * 0.6, (seen, len(stars))
        # And one star inside a penguin's own body still shows
        spot = driver.execute_script(
            f"const scene = {SCENE};"
            "const pen = scene.pens[3];"
            "scene.fx.emit('burst', pen.x, 0.5, pen.z, 3, 0, 0, 30, 12 / scene.fx.unit, 0, 0);"
            "const at = scene.camera.camera.worldToScreen(new pc.Vec3(pen.x, 0.5, pen.z));"
            "return [at.x, at.y];"
        )
        time.sleep(0.3)
        shot = Image.open(BytesIO(driver.get_screenshot_as_png())).convert("RGB")
        pixel = shot.getpixel((round(spot[0]), round(spot[1])))
        assert all(abs(a - b) < 40 for a, b in zip(pixel, STAR_YELLOW)), pixel
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


# Screenshots are only kept when PENGUINWARS_SHOTS names a folder
SHOTS = Path(environ["PENGUINWARS_SHOTS"]) if environ.get("PENGUINWARS_SHOTS") else None


def keep_shot(driver, name):
    if SHOTS is not None:
        (SHOTS / name).parent.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(SHOTS / name))


def line_card_problems(driver):
    """Whether the title card stays inside the screen, scrolls, and keeps its note to one line"""
    return driver.execute_script(
        "const card = document.querySelector('#title .card'); const r = card.getBoundingClientRect();"
        "const note = document.getElementById('note');"
        "const lines = note.hidden ? 0 : Math.round(note.getBoundingClientRect().height / parseFloat("
        "getComputedStyle(note).lineHeight));"
        "return {scroll: card.scrollHeight - card.clientHeight, top: r.top, bottom: innerHeight - r.bottom,"
        " lines, wide: card.scrollWidth - card.clientWidth};"
    )


@pytest.mark.parametrize("size", list(SIZES))
def test_the_line_cards_read_right_at_every_size(driver, live, size):
    width, height = SIZES[size]
    open_game(driver, live)
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    try:
        seat_others(live, NAMES)
        match = match_of(live)

        async def line_up():
            # Another watcher is ahead of this one
            match.line = [2100, fakes.MEMBER_ID]
            match.dirty = True

        run(live, line_up())
        browser.wait_for(driver, "document.getElementById('starting').textContent === '2nd in line'")
        assert not driver.find_element(By.ID, "note").is_displayed()
        keep_shot(driver, f"place-{size}.png")
        fit = line_card_problems(driver)
        assert fit["scroll"] <= 0 and fit["wide"] <= 0 and fit["top"] >= 0 and fit["bottom"] >= 0, fit

        async def swapped():
            match.line = [fakes.MEMBER_ID]
            match.sat_out = [fakes.MEMBER_ID]
            match.dirty = True

        run(live, swapped())
        browser.wait_for(driver, "document.getElementById('starting').textContent === \"You're next\"")
        browser.wait_for(driver, "!document.getElementById('note').hidden")
        assert driver.find_element(By.ID, "note").text == "You're sitting out this round"
        keep_shot(driver, f"swapped-{size}.png")
        fit = line_card_problems(driver)
        assert fit["lines"] == 1, fit
        assert fit["scroll"] <= 0 and fit["wide"] <= 0 and fit["top"] >= 0 and fit["bottom"] >= 0, fit
        check_presses(driver, {"go", "back", "mute"})
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def chip_fit(driver):
    """The hint chip's size, its clearance from the frame counter corner, and who gets a press at its middle"""
    return driver.execute_script(
        "const chip = document.getElementById('hint'); const r = chip.getBoundingClientRect();"
        "const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);"
        "return {height: r.height, width: r.width, bottom: innerHeight - r.bottom, left: r.left, right: innerWidth - r.right,"
        " hit: chip.contains(hit), x: r.left + r.width / 2, y: r.top + r.height / 2,"
        " events: getComputedStyle(chip).pointerEvents};"
    )


@pytest.mark.parametrize("size", list(SIZES))
def test_a_watcher_taps_the_hint_chip_to_join_and_leave_the_line_mid_round(driver, live, phone, size):
    open_game(driver, live)
    width, height = SIZES[size]
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    seat_others(live, NAMES)
    match = match_of(live)

    async def hurry():
        match.countdown = 1

    run(live, hurry())
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    browser.wait_for(driver, "document.getElementById('hint').textContent === 'Watching. Tap to join the line'")
    WebDriverWait(driver, 3).until(lambda d: chip_fit(d)["events"] == "auto")
    fit = chip_fit(driver)
    assert fit["height"] >= 44 and fit["hit"], fit
    assert fit["left"] >= 0 and fit["right"] >= 0, fit
    driver.switch_to.default_content()
    browser.wait_for(driver, "document.querySelector('.fps').textContent")
    counter = driver.execute_script(
        "const r = document.querySelector('.fps').getBoundingClientRect(); return [r.left, r.right, r.top]"
    )
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    # The hub's frame rate counter sits in the bottom left corner: the chip is above it or beside it
    assert fit["bottom"] >= 36 or fit["x"] - fit["width"] / 2 >= counter[1], (fit, counter)
    keep_shot(driver, f"chip-{size}.png")
    tap(driver, (fit["x"], fit["y"]))
    browser.wait_for(driver, "document.getElementById('hint').textContent === \"Watching. You're next. Tap to leave\"")
    assert match.line == [fakes.MEMBER_ID]
    fit = chip_fit(driver)
    assert fit["hit"] and fit["height"] >= 44, fit
    keep_shot(driver, f"chip-in-line-{size}.png")
    tap(driver, (fit["x"], fit["y"]))
    browser.wait_for(driver, "document.getElementById('hint').textContent === 'Watching. Tap to join the line'")
    assert match.line == []


def test_a_seated_players_hint_chip_lets_drags_through(driver, live, phone):
    on_the_ice(driver, live)
    browser.wait_for(driver, "document.getElementById('hint').textContent.startsWith('Drag back')")
    assert chip_fit(driver)["events"] == "none"


def test_a_swapped_out_player_is_told_why_in_the_next_round_after_play_again(driver, live):
    open_game(driver, live)
    sit_beside(driver, live, NAMES[:1])
    seat_others(live, NAMES[1:5])
    match = match_of(live)

    async def line_up():
        # A person with a page is waiting behind. The fake one stands in for them when the swap looks for a connection
        stand_in = SimpleNamespace(ctx=SimpleNamespace(author=SimpleNamespace(id=2100, display_name="Zed")))
        real = match.conn_of
        match.conn_of = lambda user_id: stand_in if user_id == 2100 else real(user_id)
        match.line = [2100]
        match.countdown = 1

    run(live, line_up())
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    # This player, in seat 1, falls first and seat 0 wins
    only_these_survive(live, {0})
    browser.wait_for(driver, "!document.getElementById('end').hidden", timeout=10)
    driver.find_element(By.ID, "again").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'starting'")
    assert [seat.user_id for seat in match.seats][1] == 2100
    browser.wait_for(
        driver, "document.getElementById('hint').textContent === \"Sitting out this round. You're next. Tap to leave\""
    )
    assert not driver.find_element(By.ID, "title").is_displayed()


LONG_NAMES = [f"Sir Waddlesworth the {n}th of the Frozen Southern Sea" for n in range(1, 11)]


def seed_board(live, count):
    """Rows for this server: the player is 4th, and the others have long names"""

    async def seed():
        # Config keeps its data from test to test, so start empty
        await live.cog.config.clear_all_members()
        for place in range(count):
            user_id = fakes.MEMBER_ID if place == 3 else 3000 + place
            entry = {"wins": 40 - place * 3, "knockouts": 120 - place, "rounds": 99, "name": LONG_NAMES[place]}
            await live.cog.config.member_from_ids(fakes.GUILD_ID, user_id).set(entry)

    run(live, seed())


BOARD_FIT = """
const box = document.getElementById('board').getBoundingClientRect();
const list = document.getElementById('leaders');
const names = [...list.querySelectorAll('.name')];
const rows = [...list.children].map((li) => li.getBoundingClientRect());
return {top: box.top, bottom: innerHeight - box.bottom, left: box.left, right: innerWidth - box.right,
  wide: list.scrollWidth - list.clientWidth, count: rows.length,
  oneLine: names.every((n) => n.getBoundingClientRect().height < 24),
  mine: [...list.querySelectorAll('li.mine .place')].map((n) => n.textContent),
  texts: [...list.querySelectorAll('li.mine .numbers')].map((n) => n.textContent),
  you: document.getElementById('you').textContent,
  invite: !document.getElementById('invite').hidden};
"""


def board_presses(driver, wanted):
    """The dialog's buttons get a press at their middle. The page behind a modal dialog can't be pressed"""
    buttons = {b["id"]: b["ok"] for b in driver.execute_script(BUTTON_PRESSES) if b["id"] in wanted}
    assert buttons == {name: True for name in wanted}, buttons


def open_board_at(driver, live, size):
    width, height = SIZES[size]
    open_game(driver, live)
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    check_presses(driver, {"open-board", "go", "back", "mute"})
    keep_shot(driver, f"t10c/title-{size}.png")
    driver.find_element(By.ID, "open-board").click()
    browser.wait_for(driver, "document.getElementById('you').textContent !== 'Loading...'")


@pytest.mark.parametrize("size", list(SIZES))
def test_the_full_board_shows_rows_marks_your_own_and_fits(driver, live, size):
    seed_board(live, 10)
    try:
        open_board_at(driver, live, size)
        keep_shot(driver, f"t10c/full-{size}.png")
        fit = driver.execute_script(BOARD_FIT)
        assert fit["count"] == 10 and fit["mine"] == ["#4"], fit
        assert fit["texts"] == ["31 wins · 117 knockouts · 99 rounds"], fit
        assert fit["you"] == "You: #4 with 31 wins" and not fit["invite"], fit
        assert fit["oneLine"] and fit["wide"] <= 0, fit
        assert min(fit["top"], fit["bottom"], fit["left"], fit["right"]) >= 0, fit
        board_presses(driver, {"close-board"})
        driver.find_element(By.ID, "close-board").click()
        assert not driver.find_element(By.ID, "board").is_displayed()
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


@pytest.mark.parametrize("size", list(SIZES))
def test_the_empty_board_reads_right_and_offers_an_invite_when_solo(driver, live, size):
    seed_board(live, 0)
    try:
        open_board_at(driver, live, size)
        keep_shot(driver, f"t10c/empty-{size}.png")
        fit = driver.execute_script(BOARD_FIT)
        assert fit["count"] == 0 and fit["you"] == "No rounds yet. Play with a friend to start the board.", fit
        assert fit["invite"] and min(fit["top"], fit["bottom"], fit["left"], fit["right"]) >= 0, fit
        board_presses(driver, {"invite", "close-board"})
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_a_player_with_no_rounds_is_told_how_to_get_on_the_board(driver, live):
    seed_board(live, 3)
    open_board_at(driver, live, "phone")
    assert driver.find_element(By.ID, "you").text == "Play a round with a friend to get on the board."
    assert driver.execute_script(BOARD_FIT)["mine"] == []
    driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_the_board_closes_when_the_round_starts_and_a_slide_still_works(driver, live, phone):
    open_game(driver, live)
    sit_beside(driver, live)
    driver.find_element(By.ID, "open-board").click()
    browser.wait_for(driver, "document.getElementById('board').open")
    match = match_of(live)

    async def hurry():
        match.countdown = 1

    run(live, hurry())
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    assert not driver.execute_script("return document.getElementById('board').open")
    wait_for_penguins(driver)
    calm(live)
    # This player sat down beside Ann, in seat 1
    browser.wait_for(driver, f"{SCENE}.pens[1].row[3] === 0")
    heard = hear_the_page(live)
    pull(driver)
    lift(driver)
    WebDriverWait(driver, 3).until(lambda _: heard)
    assert "slide" in heard[0]


# ---------- The shop ----------

ITEM = '.item[data-id="{}"]'
TAB = '#shop-tabs .tab[data-kind="{}"]'
# The card that takes a thing off, which every tab starts with
BARE = "(bare)"
SMALL ={"small upright": (320, 568), "small sideways": (568, 320)}
SHORT = {"short sideways": (667, 375), "short upright": (360, 560)}
# A 360 px Android phone inside Discord, whose own bar takes some of the height
NARROW = {"narrow upright": (360, 747), "narrow sideways": (747, 360)}
# Everything with a credit price, which is all an admin sets
CATALOG = {item: info["price"] for item, info in SOLD.items()}
HAT_IDS = [item for item, info in ITEMS.items() if info["kind"] == "hat"]
TRAIL_IDS = [item for item, info in ITEMS.items() if info["kind"] == "trail"]
# The kind of particle each trail leaves
TRAIL_CLOUDS = dict(zip(TRAIL_IDS, ("sparkle", "heart", "bubble", "flame", "snowflake", "leaf", "gem")))
MY_WINDOW = "document.getElementById('shop-window').getBoundingClientRect()"
GOLD = (255, 201, 51)
DM_QUERY = "?frame_id=f&instance_id=i-1&channel_id=5&platform=desktop"
HEAD = "{}.pens[{}].parts.head"


@contextmanager
def sized(driver, size, scale=1):
    width, height = {**SIZES, **SMALL, **SHORT, **NARROW}[size]
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": False},
    )
    try:
        yield
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


async def read(value):
    return await value()


def stock_shop(live, balance=10_000, owned=(), prices=None, wear=None, stats=None):
    """The player's credits, what they own and wear, and their play counts. `prices` is what the server's admin saved,
    keyed like SOLD, where a missing item is not sold, or None for the catalog's prices. Config keeps its data from
    test to test, so all of it starts clean"""
    assert prices is None or set(prices) <= set(SOLD), prices
    live.cog.shop.bank = FakeBank()
    live.cog.shop.bank.balances[fakes.MEMBER_ID] = balance

    async def reset():
        mine = {"owned": list(owned), "wear": dict(wear or {}), "stats": dict(stats or {})}
        await live.cog.config.user_from_id(fakes.MEMBER_ID).set(mine)
        group = live.cog.config.guild_from_id(fakes.GUILD_ID)
        await group.prices.set(prices)
        await group.tally.set({})
        await live.cog.config.prices.set(None)
        await live.cog.config.tally.set({})

    run(live, reset())


def wait_for_cards(driver):
    browser.wait_for(driver, "document.querySelector('#shop-shelf .item')")


def show_tab(driver, kind):
    """Each tab holds the cards of one kind of thing. Its cards are in once the bare card is"""
    driver.find_element(By.CSS_SELECTOR, TAB.format(kind)).click()
    browser.wait_for(driver, f"document.querySelector('{TAB.format(kind)}').getAttribute('aria-selected') === 'true'")
    wait_for_cards(driver)


def open_shop(driver, tab="hat"):
    """Opens the wardrobe from the title card, on the tab these tests shop from"""
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    driver.find_element(By.ID, "open-shop").click()
    wait_for_cards(driver)
    show_tab(driver, tab)


def tap_item(driver, item):
    driver.find_element(By.CSS_SELECTOR, ITEM.format(item)).click()


def item_state(driver, item):
    """What a card's state line says, or None while the shelf has no such card. Read from the page itself: a card
    scrolled out of the shelf has no text as Selenium sees it"""
    state = f"{ITEM.format(item)} .state"
    return driver.execute_script("return document.querySelector(arguments[0])?.textContent ?? null", state)


def wait_for_state(driver, item, text):
    WebDriverWait(driver, 5).until(lambda d: item_state(d, item) == text)


def shop_note(driver):
    return driver.find_element(By.ID, "shop-note").text


def my_wear(live):
    return run(live, read(live.cog.config.user_from_id(fakes.MEMBER_ID).wear))


def my_hat(live):
    return my_wear(live).get("hat")


def test_buying_a_hat_from_the_shop(driver, live):
    stock_shop(live, balance=3000)
    open_game(driver, live)
    open_shop(driver)
    balance = driver.find_element(By.ID, "shop-balance")
    act = driver.find_element(By.ID, "shop-act")
    assert balance.text == "3,000 credits"
    assert item_state(driver, "beanie") == "1,000"
    assert not act.is_displayed() and shop_note(driver) == "Tap something to try it on."
    tap_item(driver, "beanie")
    assert act.text == "Buy for 1,000"
    act.click()
    wait_for_state(driver, "beanie", "Owned")
    assert balance.text == "2,000 credits"
    assert live.cog.shop.bank.balances[fakes.MEMBER_ID] == 2000
    assert act.text == "Wear"
    act.click()
    wait_for_state(driver, "beanie", "Wearing")
    assert my_wear(live) == {"hat": "beanie", "neck": "scarf"}
    assert act.text == "Take off"
    act.click()
    wait_for_state(driver, "beanie", "Owned")
    assert my_wear(live) == {"neck": "scarf"}


def test_two_quick_taps_on_buy_charge_once_and_show_no_error(driver, live):
    stock_shop(live, balance=3000)
    open_game(driver, live)
    open_shop(driver)
    tap_item(driver, "beanie")
    driver.execute_script("const act = document.getElementById('shop-act'); act.click(); act.click();")
    wait_for_state(driver, "beanie", "Owned")
    assert live.cog.shop.bank.balances[fakes.MEMBER_ID] == 2000
    assert shop_note(driver) == ""


def test_a_player_short_of_credits_is_told_how_many_with_no_dead_button(driver, live):
    stock_shop(live, balance=700)
    open_game(driver, live)
    open_shop(driver)
    tap_item(driver, "beanie")
    assert shop_note(driver) == "You need 300 more credits."
    assert not driver.find_element(By.ID, "shop-act").is_displayed()


def test_in_a_dm_buying_says_so_and_wearing_works(driver, live):
    stock_shop(live, owned=["crown"])
    live.location = {"guild_id": None, "channel_id": 5}
    open_game(driver, live, DM_QUERY)
    open_shop(driver)
    act = driver.find_element(By.ID, "shop-act")
    assert driver.find_element(By.ID, "shop-balance").text == "Buying works in a server. Wearing works anywhere."
    assert item_state(driver, "beanie") == "In a server"
    tap_item(driver, "beanie")
    assert shop_note(driver) == "Open Penguin Wars in a server to buy this."
    assert not act.is_displayed()
    tap_item(driver, "crown")
    assert item_state(driver, "crown") == "Owned" and act.text == "Wear"
    act.click()
    wait_for_state(driver, "crown", "Wearing")
    assert my_hat(live) == "crown"


def test_an_item_this_server_doesnt_sell_says_so_and_can_still_be_worn(driver, live):
    stock_shop(live, owned=["beanie"], prices={"crown": 50})
    open_game(driver, live)
    open_shop(driver)
    assert item_state(driver, "crown") == "50"
    assert item_state(driver, "party") == "Not sold here"
    tap_item(driver, "party")
    assert shop_note(driver) == "This server doesn't sell this."
    assert not driver.find_element(By.ID, "shop-act").is_displayed()
    tap_item(driver, "beanie")
    assert driver.find_element(By.ID, "shop-act").text == "Wear"


def test_an_earned_hat_is_worn_without_buying_and_a_locked_one_shows_how_far_along_it_is(driver, live):
    stock_shop(live, stats={"rounds": 5, "wins": 2})
    open_game(driver, live)
    open_shop(driver)
    act = driver.find_element(By.ID, "shop-act")
    bar = "return document.querySelector(arguments[0]).querySelector('.bar')"
    # Five rounds played unlock the propeller cap
    assert item_state(driver, "propeller") == "Earned"
    assert driver.execute_script(f"{bar}.hidden", ITEM.format("propeller"))
    tap_item(driver, "propeller")
    assert act.text == "Wear"
    act.click()
    wait_for_state(driver, "propeller", "Wearing")
    assert my_wear(live) == {"hat": "propeller", "neck": "scarf"}
    assert live.cog.shop.bank.balances[fakes.MEMBER_ID] == 10_000
    # The wizard hat takes fifteen wins
    assert item_state(driver, "wizard") == "2/15"
    assert driver.execute_script(f"{bar}.style.getPropertyValue('--done')", ITEM.format("wizard")) == "13%"
    tap_item(driver, "wizard")
    assert shop_note(driver) == "Win 15 rounds (2/15)."
    assert not act.is_displayed()


def test_trying_on_shows_in_the_preview_and_closing_keeps_only_what_is_worn(driver, live):
    stock_shop(live, owned=["crown"])
    open_game(driver, live)
    open_shop(driver)
    read_hat = (
        "const head = pc.Application.getApplication().root.findByName('shop-penguin').findByName('hat');"
        "return head.children.map((hat) => hat.name);"
    )
    assert driver.execute_script(read_hat) == []
    tap_item(driver, "tophat")
    assert driver.execute_script(read_hat) == ["hat-tophat"]
    tap_item(driver, "crown")
    assert driver.execute_script(read_hat) == ["hat-crown"]
    driver.find_element(By.ID, "close-shop").click()
    browser.wait_for(driver, "!document.getElementById('shop').open")
    driver.find_element(By.ID, "open-shop").click()
    wait_for_cards(driver)
    assert driver.execute_script(read_hat) == []


def test_a_shop_left_open_while_the_bot_keeps_the_seat_closes_when_a_round_starts(driver, live):
    stock_shop(live)
    open_game(driver, live)
    seat_others(live, ("Ann",))
    open_shop(driver)
    match = match_of(live)

    async def seat_me_and_start():
        conn = next(iter(match.room.connections))
        match.seat_person(match.free_spot(), conn)
        match.begin_round()

    run(live, seat_me_and_start())
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    browser.wait_for(driver, "!document.getElementById('shop').open")


def test_the_preview_draws_on_the_games_canvas_and_stops_when_the_shop_closes(driver, live):
    stock_shop(live, owned=["crown"])
    open_game(driver, live)
    room = (
        "const app = pc.Application.getApplication();"
        "const camera = app.root.findByName('shop-camera');"
        "const penguin = app.root.findByName('shop-penguin');"
        "return {canvases: document.querySelectorAll('canvas').length, camera: Boolean(camera && camera.enabled),"
        " penguin: Boolean(penguin && penguin.enabled), listeners: app._callbacks.get('update').length,"
        f" draws: {LAST_DRAWS}}};"
    )
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    driver.execute_script(room)
    time.sleep(0.4)
    before = driver.execute_script(room)
    open_shop(driver)
    tap_item(driver, "crown")
    time.sleep(0.4)
    during = driver.execute_script(room)
    assert during["canvases"] == 1 and during["camera"] and during["penguin"], during
    assert during["draws"] > before["draws"], during
    # The window shows the preview, with the crown's gold on it
    box = driver.execute_script(f"const r = {MY_WINDOW}; return [r.left, r.top, r.right, r.bottom];")
    shot = Image.open(BytesIO(driver.get_screenshot_as_png())).convert("RGB").crop([round(n) for n in box])
    gold = sum(all(abs(a - b) < 60 for a, b in zip(pixel, GOLD)) for pixel in shot.getdata())
    assert gold > 80, gold
    # A press on the window stays in the dialog, and never reaches the game's canvas
    hit = driver.execute_script(
        f"const r = {MY_WINDOW};"
        "return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2).closest('#shop') !== null;"
    )
    assert hit
    driver.find_element(By.ID, "close-shop").click()
    browser.wait_for(driver, "!document.getElementById('shop').open")
    time.sleep(0.4)
    after = driver.execute_script(room)
    assert not after["camera"] and not after["penguin"], after
    assert after["listeners"] == before["listeners"] and after["draws"] == before["draws"], (before, after)
    assert not driver.execute_script("return document.body.classList.contains('shopping')")


SHOP_PRESSES = """
const found = [];
for (const b of document.querySelectorAll('#shop button')) {
  if (b.offsetParent === null) { continue; }
  b.scrollIntoView({block: 'center', behavior: 'instant'});
  const r = b.getBoundingClientRect();
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  found.push({id: b.dataset.id || b.dataset.kind || b.id, ok: !!hit && b.contains(hit), tall: r.height, left: r.left,
    right: innerWidth - r.right, top: r.top, bottom: innerHeight - r.bottom});
}
return found;
"""


def items_of(kind):
    return [item for item, info in ITEMS.items() if info["kind"] == kind]


@pytest.mark.parametrize("size", [*SIZES, *SMALL])
def test_the_shop_scrolls_and_every_button_gets_its_press(driver, live, size):
    stock_shop(live, owned=["beanie"])
    open_game(driver, live)
    # A sideways phone has little height, so there the tabs and the two buttons under the cards are a little shorter
    reach = 40 if {**SIZES, **SMALL}[size][1] <= 520 else 44
    with sized(driver, size):
        open_shop(driver)
        for kind in KINDS:
            show_tab(driver, kind)
            # The first thing of each kind is owned or can be bought, so the big button shows
            tap_item(driver, items_of(kind)[0])
            time.sleep(0.3)
            keep_shot(driver, f"t12/shop-{kind}-{size.replace(' ', '-')}.png")
            buttons = driver.execute_script(SHOP_PRESSES)
            wanted = {*KINDS, BARE, *items_of(kind), "shop-act", "close-shop"}
            assert {button["id"] for button in buttons} == wanted, buttons
            for button in buttons:
                assert button["ok"] and button["tall"] >= reach, button
                assert min(button["left"], button["right"], button["top"], button["bottom"]) >= 0, button
        show_tab(driver, "hat")
        fit = driver.execute_script(
            "const shelf = document.getElementById('shop-shelf');"
            "const window = document.getElementById('shop-window').getBoundingClientRect();"
            "return {extra: shelf.scrollHeight - shelf.clientHeight, width: window.width, height: window.height,"
            " wide: document.getElementById('shop').scrollWidth - innerWidth};"
        )
        assert fit["wide"] <= 0 and fit["width"] >= 120 and fit["height"] >= 120, fit
        if size in SMALL:
            assert fit["extra"] > 0, fit
        # The last hat is on screen after a scroll, and takes a real press
        driver.find_element(By.CSS_SELECTOR, ITEM.format(HAT_IDS[-1])).click()
        assert shop_note(driver) == "Bounce 5 penguins into the sea with your brace (0/5)."


def test_a_finger_scrolls_the_shop_on_a_short_screen(driver, live):
    stock_shop(live)
    open_game(driver, live)
    with sized(driver, "small sideways"):
        driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 2})
        try:
            open_shop(driver)
            box = driver.execute_script(
                "const r = document.getElementById('shop-shelf').getBoundingClientRect();"
                "return [r.left + r.width / 2, r.top + r.height - 12, r.top + 12];"
            )
            touch(driver, "touchStart", (box[0], box[1]))
            for step in range(1, 9):
                touch(driver, "touchMove", (box[0], box[1] + (box[2] - box[1]) * step / 8))
                time.sleep(0.016)
            touch(driver, "touchEnd")
            WebDriverWait(driver, 3).until(
                lambda d: d.execute_script("return document.getElementById('shop-shelf').scrollTop") > 10
            )
        finally:
            driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": False})


def test_a_long_currency_and_a_huge_price_stay_inside_the_shop(driver, live):
    stock_shop(live, balance=999_999_999, prices={item: 1_000_000_000 for item in SOLD})

    async def currency(guild=None):
        return "Golden Doubloons of the Frozen South"

    live.cog.shop.bank.get_currency_name = currency
    open_game(driver, live)
    with sized(driver, "phone"):
        open_shop(driver)
        tap_item(driver, "crown")
        spill = driver.execute_script(
            # Measured on the words themselves: right-aligned text spills to the left, where scrollWidth can't see it
            "const inside = [...document.querySelectorAll('#shop .item, #shop-balance, #shop-note')];"
            "return inside.filter((node) => {"
            "  const words = document.createRange();"
            "  words.selectNodeContents(node);"
            "  const [text, box] = [words.getBoundingClientRect(), node.getBoundingClientRect()];"
            "  return text.left < box.left - 1 || text.right > Math.min(box.right, innerWidth) + 1;"
            "}).map((node) => node.id || node.dataset.id);"
        )
        assert spill == []
        keep_shot(driver, "t12/shop-long.png")


def test_live_updates_leave_the_shop_cards_alone_and_a_press_lands(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    driver.execute_script(f"window.card = document.querySelector('{ITEM.format('tophat')}');")
    spot = driver.execute_script(
        "const r = window.card.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2];"
    )
    press = {"x": spot[0], "y": spot[1], "button": "left", "clickCount": 1}
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", **press})
    match = match_of(live)

    async def snapshot():
        match.dirty = True

    for _ in range(6):
        run(live, snapshot())
        time.sleep(0.05)
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", **press})
    assert driver.execute_script("return window.card.isConnected")
    assert driver.execute_script("return window.card.getAttribute('aria-pressed')") == "true"


def test_opening_the_shop_gives_up_the_seat_and_it_stays_open_through_a_round_start(driver, live):
    stock_shop(live)
    open_game(driver, live)
    sit_beside(driver, live, ("Ann", "Bo"))
    match = match_of(live)
    heard = hear_the_page(live)
    driver.find_element(By.ID, "open-shop").click()
    wait_for_cards(driver)
    WebDriverWait(driver, 3).until(lambda _: match.seat_of(fakes.MEMBER_ID) is None)
    assert heard == [{"stand": True}]
    show_tab(driver, "hat")
    tap_item(driver, "crown")
    # Ann and Bo carry on without this player
    assert match.countdown is not None

    async def hurry():
        match.countdown = 1

    run(live, hurry())
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    time.sleep(0.3)
    assert driver.execute_script("return document.getElementById('shop').open")
    assert driver.execute_script("return document.body.classList.contains('shopping')")
    assert drawn(driver, "shop-camera")[0]
    assert driver.find_element(By.CSS_SELECTOR, ITEM.format("crown")).get_attribute("aria-pressed") == "true"
    # A CPU took the spot
    assert fakes.MEMBER_ID not in match.round_players.values() and match.seats[2].cpu is not None


def test_the_end_card_opens_the_shop_too(driver, live):
    stock_shop(live)
    sit_and_start(driver, live)
    end_the_round(live)
    browser.wait_for(driver, "!document.getElementById('end').hidden")
    driver.find_element(By.ID, "end-shop").click()
    wait_for_cards(driver)
    assert driver.execute_script("return document.getElementById('shop').open")
    # Nothing on the page may show through the preview's window
    for spot in ("end", "title"):
        assert (
            driver.execute_script(f"return getComputedStyle(document.getElementById('{spot}')).visibility") == "hidden"
        )


WATCH_SIZES = ["narrow upright", "phone", "sideways", "desktop", "narrow sideways"]
WATCH_SHOTS = {"narrow upright": "watcher-shop.png", "narrow sideways": "watcher-shop-sideways.png"}
PRESSED_AT_MIDDLE = """
const r = arguments[0].getBoundingClientRect();
return arguments[0].contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2));
"""


# Where each tile on the ice is drawn, as a box round its top and its side down to the bottom of its body. Twelve
# points on a circle a little wider than the tile cover its corners however it is turned
ICE_TILES = f"""
{TILE_SLOT}
const camera = {SCENE}.camera.camera;
const boxes = [];
for (let index = 0; index < {SCENE}.tiles.length; index++) {{
  const [shown, x, y, z] = tileSlot(index);
  if (!shown) {{ continue; }}
  const xs = [];
  const ys = [];
  for (let step = 0; step < 12; step++) {{
    const angle = (step * Math.PI) / 6;
    for (const lift of [0.09, -0.29]) {{
      const at = camera.worldToScreen(new pc.Vec3(x + Math.cos(angle) * 0.62, y + lift, z + Math.sin(angle) * 0.62));
      xs.push(at.x);
      ys.push(at.y);
    }}
  }}
  boxes.push([Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]);
}}
return boxes;
"""


def box_of(driver, selector):
    """left, top, right, bottom"""
    return driver.execute_script(
        "const r = document.querySelector(arguments[0]).getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom];",
        selector,
    )


def apart(first, second):
    return first[2] <= second[0] or second[2] <= first[0] or first[3] <= second[1] or second[3] <= first[1]


def clear_of_the_hubs_counter(driver, box):
    """The hub draws its frame rate counter over the game's frame, in the bottom left corner"""
    driver.switch_to.default_content()
    try:
        browser.wait_for(driver, "document.querySelector('.fps').textContent")
        counter, frame = box_of(driver, ".fps"), box_of(driver, "#game-frame")
    finally:
        driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    return apart([box[0] + frame[0], box[1] + frame[1], box[2] + frame[0], box[3] + frame[1]], counter), counter


@pytest.mark.parametrize("size", WATCH_SIZES)
def test_someone_watching_a_round_shops_from_a_button_beside_the_hint(driver, live, size):
    stock_shop(live)
    with sized(driver, size):
        open_game(driver, live)
        opened = time.monotonic()
        browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
        button = driver.find_element(By.ID, "watch-shop")
        # Between rounds the cards hold the shop
        assert not button.is_displayed()
        seat_others(live, NAMES[:2])
        match = match_of(live)

        async def hurry():
            match.countdown = 1

        run(live, hurry())
        browser.wait_for(driver, "document.body.dataset.stage === 'starting'", timeout=10)
        # During the 3-2-1 the title card still offers a CPU's penguin, and holds the shop
        assert not button.is_displayed() and driver.find_element(By.ID, "go").is_displayed()

        async def hold_the_ice():
            match.round.floe.crack_timer = 1000.0

        # The whole floe stays, at its biggest
        run(live, hold_the_ice())
        browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
        WebDriverWait(driver, 3).until(lambda _: button.is_displayed())
        wait_for_penguins(driver)
        # The hub's arrival notes slide out under its people button, once a player's first moments are over
        time.sleep(max(0.0, ARRIVALS_QUIET - (time.monotonic() - opened)))
        live.add_person(fakes.ADMIN_ID, where="penguinwars", status="Watching")
        browser.wait_for(driver, "document.querySelector('.hub-note')", timeout=5)
        spot, chip, note = box_of(driver, "#watch-shop"), box_of(driver, "#hint"), box_of(driver, ".hub-note")
        tiles = driver.execute_script(ICE_TILES)
        width, height = SIZES.get(size) or NARROW[size]
        assert spot[3] - spot[1] >= 44 and min(spot[:2]) >= 0 and spot[2] <= width and spot[3] <= height, spot
        # On the hint's row, just after it
        assert abs((spot[1] + spot[3]) - (chip[1] + chip[3])) < 3 and 0 <= spot[0] - chip[2] <= 12, (spot, chip)
        assert len(tiles) == 61 and all(apart(spot, tile) for tile in tiles), (spot, ice_box(driver))
        assert apart(spot, note), (spot, note)
        assert driver.execute_script(PRESSED_AT_MIDDLE, button)
        clear, counter = clear_of_the_hubs_counter(driver, spot)
        assert clear, (spot, counter)
        if size in WATCH_SHOTS:
            keep_shot(driver, WATCH_SHOTS[size])
        # In the line, opening the shop gives up the place in it too
        driver.find_element(By.ID, "hint").click()
        WebDriverWait(driver, 3).until(lambda _: match.line == [fakes.MEMBER_ID])
        heard = hear_the_page(live)
        button.click()
        wait_for_cards(driver)
        WebDriverWait(driver, 3).until(lambda _: match.line == [])
        assert heard == [{"stand": True}]
        driver.find_element(By.ID, "close-shop").click()
        browser.wait_for(driver, "!document.getElementById('shop').open")
        browser.wait_for(driver, "document.getElementById('hint').textContent === 'Watching. Tap to join the line'")
        assert button.is_displayed()
        end_the_round(live)
        browser.wait_for(driver, "document.body.dataset.stage === 'results'")
        assert not button.is_displayed()


CARD_ROW = """
const box = document.querySelector(arguments[0]).getBoundingClientRect();
return [...document.querySelectorAll(`${arguments[0]} .btns button`)].filter((b) => b.offsetParent !== null).map((b) => {
  const r = b.getBoundingClientRect();
  return {id: b.id, left: r.left, right: r.right, top: r.top, bottom: r.bottom, inside: r.left >= box.left &&
    r.right <= box.right && r.top >= box.top && r.bottom <= box.bottom};
});
"""


def check_card_row(driver, card, wanted):
    buttons = driver.execute_script(CARD_ROW, card)
    assert wanted <= {button["id"] for button in buttons}, buttons
    for button in buttons:
        assert button["inside"] and button["bottom"] - button["top"] >= 44, button
    for first, second in combinations(buttons, 2):
        apart = max(first["left"] - second["right"], second["left"] - first["right"])
        below = max(first["top"] - second["bottom"], second["top"] - first["bottom"])
        assert max(apart, below) >= 8, (first, second)


@pytest.mark.parametrize("size", ["phone", "sideways"])
def test_the_card_buttons_fit_with_room_to_press(driver, live, size):
    stock_shop(live)
    open_game(driver, live)
    with sized(driver, size):
        browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
        check_card_row(driver, "#title .card", {"go", "open-board", "open-shop"})
        check_presses(driver, {"go", "open-board", "open-shop"})
        keep_shot(driver, f"t12/title-{size}.png")
        sit_beside(driver, live)
        check_card_row(driver, "#title .card", {"start", "stand", "open-board", "open-shop"})
        check_presses(driver, {"start", "stand", "open-board", "open-shop"})
        keep_shot(driver, f"t12/seated-{size}.png")
        driver.find_element(By.ID, "start").click()
        browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
        end_the_round(live)
        browser.wait_for(driver, "!document.getElementById('end').hidden")
        check_card_row(driver, "#end .card", {"again", "end-shop"})
        check_presses(driver, {"again", "end-shop"})
        keep_shot(driver, f"t12/end-{size}.png")


# The smallest sideways phone has no room for the whole title card, so there it scrolls, still under the row
@pytest.mark.parametrize(
    "size, scrolls",
    [("small upright", False), ("short upright", False), ("phone", False), ("narrow sideways", False)]
    + [("small sideways", True)],
)
def test_the_title_card_stays_under_the_watching_row_and_needs_no_scrolling(driver, live, size, scrolls):
    open_game(driver, live)
    with sized(driver, size):
        browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
        # Someone on the title card is watching, so the row shows with their own face
        browser.wait_for(driver, "!document.getElementById('watching').hidden")
        top, row, over = driver.execute_script(
            "const card = document.querySelector('#title .card');"
            "return [card.getBoundingClientRect().top, document.getElementById('watching').getBoundingClientRect().bottom,"
            "  card.scrollHeight - card.clientHeight];"
        )
        assert top >= row and (over > 0) == scrolls, (top, row, over)


# The wardrobe's penguin stands far out to sea, so anything in the air past this x is its own
ROOM_SIDE = 200
IN_THE_AIR = f"""
const cloud = {FX}.clouds[arguments[0]];
return [...cloud.x].filter((x, slot) => cloud.life[slot] > 0);
"""
# The first shape of the wardrobe's penguin is its body, which a skin repaints
ROOM_PENGUIN = "pc.Application.getApplication().root.findByName('shop-penguin')"
ROOM_BODY = f"return {ROOM_PENGUIN}.find((node) => node.render)[0].render.meshInstances[0].material.diffuse.toString()"
# A kind of particle that each cheer and each splash throws and the plain one doesn't
CHEER_CLOUDS = {"twirl": "sparkle", "backflip": "snow", "fireworks": "gem", "spin": "snowflake"}
SPLASH_CLOUDS = {"lovesplash": "heart", "bubblebath": "bubble", "sizzle": "flame", "starburst": "sparkle"}


def in_the_room(driver, cloud):
    """How many particles of one kind are in the air round the wardrobe's penguin"""
    spots = driver.execute_script(IN_THE_AIR, cloud)
    assert all(x > ROOM_SIDE for x in spots), (cloud, spots)
    return len(spots)


def wait_for_a_show(driver, item, cloud):
    """Tap a card once the air is clear of its particles, then wait for the preview to throw them"""
    WebDriverWait(driver, 5).until(lambda d: in_the_room(d, cloud) == 0)
    tap_item(driver, item)
    # A cheer or a splash on show plays to its end before the picked one starts
    WebDriverWait(driver, 8).until(lambda d: in_the_room(d, cloud) >= 3)


def test_every_item_shows_in_the_preview(driver, live):
    stock_shop(live)
    open_game(driver, live)
    with sized(driver, "phone", scale=2):
        open_shop(driver, tab="skin")

        def keep_window(name):
            if SHOTS is not None:
                r = driver.execute_script(f"const r = {MY_WINDOW}; return [r.left, r.top, r.right, r.bottom];")
                shot = Image.open(BytesIO(driver.get_screenshot_as_png())).convert("RGB")
                (SHOTS / "t12").mkdir(parents=True, exist_ok=True)
                shot.crop([round(n * 2) for n in r]).save(SHOTS / "t12" / name)

        bodies = {BARE: driver.execute_script(ROOM_BODY)}
        for skin in items_of("skin"):
            tap_item(driver, skin)
            bodies[skin] = driver.execute_script(ROOM_BODY)
            time.sleep(0.15)
            keep_window(f"preview-{skin}.png")
        # Each skin paints the body a color of its own
        assert len(set(bodies.values())) == len(bodies), bodies
        for kind in ("hat", "face", "neck", "back"):
            show_tab(driver, kind)
            for item in items_of(kind):
                tap_item(driver, item)
                browser.wait_for(driver, f"{ROOM_PENGUIN}.findByName('{kind}-{item}') !== null")
                time.sleep(0.15)
                keep_window(f"preview-{item}.png")
        for kind, clouds in (("trail", TRAIL_CLOUDS), ("cheer", CHEER_CLOUDS), ("splash", SPLASH_CLOUDS)):
            assert [*clouds] == items_of(kind)
            show_tab(driver, kind)
            for item, cloud in clouds.items():
                wait_for_a_show(driver, item, cloud)
                keep_window(f"preview-{item}.png")
    assert not problems_in_console(driver)


# ---------- Hats and trails on the ice ----------


def dress(live, seat, **looks):
    """What this seat wears, as {kind: item} with only the kinds worn, the way the bot sends it"""
    match = match_of(live)

    async def change():
        match.seats[seat].looks = {kind: item for kind, item in looks.items() if item}
        match.dirty = True

    run(live, change())


def wait_for_hat(driver, seat, hat):
    browser.wait_for(driver, f"{HEAD.format(SCENE, seat)}.children[0]?.name === 'hat-{hat}'")


# Six of each kind of thing a penguin wears, one for each seat
WORN_IDS = {
    kind: [item for item, info in ITEMS.items() if info["kind"] == kind][:6]
    for kind in ("skin", "hat", "face", "neck", "back")
}


def wait_for_worn(driver, seat, kind, item):
    browser.wait_for(driver, f"{SCENE}.pens[{seat}].parts.{kind}.children[0]?.name === '{kind}-{item}'")


HAT_POSE = f"""
const pen = {SCENE}.pens[arguments[0]];
const holder = arguments[1] === 'seal' ? pen.seal : pen.parts;
const hat = holder.head.children[0];
const box = hat.render.meshInstances[0].aabb;
const anchor = holder.head.getPosition();
const up = holder.head.up;
const off = box.center.clone().sub(anchor);
return {{shown: hat.enabled, lift: off.dot(up), upright: up.y, height: anchor.y}};
"""


def keep_close_up(driver, name, seat, seal=False):
    """A crop around a seat's head, kept with the other screenshots"""
    if SHOTS is None:
        return
    x, y = driver.execute_script(
        f"const scene = {SCENE};"
        "const pen = scene.pens[arguments[0]];"
        "const at = (arguments[1] ? pen.seal : pen.parts).head.getPosition();"
        "const spot = scene.camera.camera.worldToScreen(at);"
        "return [spot.x * devicePixelRatio, spot.y * devicePixelRatio];",
        seat,
        seal,
    )
    shot = Image.open(BytesIO(driver.get_screenshot_as_png())).convert("RGB")
    (SHOTS / "t12").mkdir(parents=True, exist_ok=True)
    shot.crop((round(x) - 150, round(y) - 150, round(x) + 150, round(y) + 150)).save(SHOTS / "t12" / name)


@pytest.mark.parametrize("hat", ["tophat", "flower"])
def test_a_hat_stays_on_through_every_pose(driver, live, hat):
    with sized(driver, "phone", scale=3):
        sit_and_start(driver, live)
        wait_for_penguins(driver)
        calm(live)
        match = match_of(live)

        async def move_apart():
            match.round.floe.crack_timer = 1000.0
            match.round.penguins[3].x, match.round.penguins[3].z = -3.0, 1.0

        run(live, move_apart())
        dress(live, 3, hat=hat)
        wait_for_hat(driver, 3, hat)
        time.sleep(0.2)
        pose = driver.execute_script(HAT_POSE, 3, "penguin")
        assert pose["shown"] and pose["lift"] > 0.1 and pose["upright"] > 0.9, pose
        keep_close_up(driver, f"pose-{hat}-stand.png", 3)
        glide(live, 3, power=0.6)
        browser.wait_for(driver, f"{SCENE}.pens[3].slide > 0.7", timeout=5)
        pose = driver.execute_script(HAT_POSE, 3, "penguin")
        assert pose["shown"] and pose["lift"] > 0.1 and abs(pose["upright"]) < 0.5, pose
        keep_close_up(driver, f"pose-{hat}-slide.png", 3)
        browser.wait_for(driver, f"{SCENE}.pens[3].slide < 0.1", timeout=6)

        async def brace():
            match.round.penguins[3].brace = 30.0

        run(live, brace())
        browser.wait_for(driver, f"{SCENE}.pens[3].bracing", timeout=5)
        pose = driver.execute_script(HAT_POSE, 3, "penguin")
        assert pose["shown"] and pose["lift"] > 0.05 and pose["upright"] > 0.9, pose
        time.sleep(0.15)
        keep_close_up(driver, f"pose-{hat}-brace.png", 3)

        async def drown():
            match.round.penguins[3].brace = 0.0
            match.round.fall(3)

        run(live, drown())
        browser.wait_for(driver, f"{SCENE}.pens[3].fall > 0.25", timeout=5)
        pose = driver.execute_script(HAT_POSE, 3, "penguin")
        assert pose["shown"] and pose["height"] < 1.4, pose
        keep_close_up(driver, f"pose-{hat}-fall.png", 3)
        browser.wait_for(driver, f"{SCENE}.pens[3].seal.state === 'swim' && {SCENE}.pens[3].seal.y > -0.2", timeout=6)
        pose = driver.execute_script(HAT_POSE, 3, "seal")
        assert pose["shown"] and pose["lift"] > 0.05, pose
        time.sleep(0.4)
        keep_close_up(driver, f"pose-{hat}-seal.png", 3, seal=True)


def test_someone_with_no_hat_keeps_a_bare_penguin_and_seal(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    count = (
        f"const pen = {SCENE}.pens[arguments[0]];"
        "return [pen.parts.root.find((node) => node.render).length, pen.parts.head.children.length,"
        " pen.seal.head.children.length];"
    )
    # A CPU's penguin comes in a scarf, which is a shape of its own
    dress(live, 2)
    browser.wait_for(driver, f"{SCENE}.pens[2].parts.neck.children.length === 0")
    bare = driver.execute_script(count, 2)
    assert bare[1:] == [0, 0]
    dress(live, 2, hat="flower")
    wait_for_hat(driver, 2, "flower")
    # One shape however many pieces the hat shows
    assert driver.execute_script(count, 2) == [bare[0] + 1, 1, 1]
    dress(live, 2)
    browser.wait_for(driver, f"{HEAD.format(SCENE, 2)}.children.length === 0")
    assert driver.execute_script(count, 2) == bare
    # Off and on again: taking off the only one of a hat doesn't lose its shape
    dress(live, 2, hat="flower")
    wait_for_hat(driver, 2, "flower")
    assert driver.execute_script(
        f"return {HEAD.format(SCENE, 2)}.children[0].render.meshInstances[0].mesh.vertexBuffer !== null"
    )


def test_a_hat_stays_when_the_players_ring_rebuilds_the_penguin(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    dress(live, 3, hat="beanie")
    wait_for_hat(driver, 3, "beanie")
    driver.execute_script(f"{SCENE}.moveRing(3);")
    wait_for_hat(driver, 3, "beanie")


def test_a_snapshot_with_the_same_hat_leaves_the_hat_alone(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    dress(live, 1, hat="crown")
    wait_for_hat(driver, 1, "crown")
    driver.execute_script(f"window.hat = {HEAD.format(SCENE, 1)}.children[0];")
    match = match_of(live)

    async def snapshot():
        match.dirty = True

    for _ in range(4):
        run(live, snapshot())
        time.sleep(0.05)
    assert driver.execute_script(f"return window.hat === {HEAD.format(SCENE, 1)}.children[0]")


def test_a_purchase_shows_on_everyones_penguin(driver, live):
    stock_shop(live, owned=["crown", "flames"])
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    match = match_of(live)
    seat_others(live, ["Ann"])
    # What a friend bought reaches this page, the same way this player's reaches theirs
    friend = match.seats[0]

    async def friend_buys():
        match.set_looks(friend.user_id, {"hat": "party", "trail": "hearts"})

    run(live, friend_buys())
    wait_for_hat(driver, 0, "party")
    assert driver.execute_script(f"return {SCENE}.pens[0].looks.trail") == "hearts"
    open_shop(driver)
    tap_item(driver, "crown")
    driver.find_element(By.ID, "shop-act").click()
    wait_for_state(driver, "crown", "Wearing")
    show_tab(driver, "trail")
    tap_item(driver, "flames")
    driver.find_element(By.ID, "shop-act").click()
    wait_for_state(driver, "flames", "Wearing")
    driver.find_element(By.ID, "close-shop").click()
    # Sitting down brings the new looks to the ice
    driver.find_element(By.ID, "go").click()
    WebDriverWait(driver, 3).until(lambda _: match.seats[1].user_id == fakes.MEMBER_ID)
    assert match.seats[1].looks == {"hat": "crown", "neck": "scarf", "trail": "flames"}
    wait_for_hat(driver, 1, "crown")
    browser.wait_for(driver, f"{SCENE}.pens[1].looks.trail === 'flames'")


PUFF = f"""
const fx = {FX};
const before = Object.fromEntries(Object.entries(fx.clouds).map(([name, cloud]) => [name, cloud.next]));
fx.trailLeft.fill(0);
const looks = arguments[1] ? {{trail: arguments[1]}} : {{}};
fx.trail({{seat: 0, vx: 8, vz: 0, x: 0, z: 0, sliding: true, row: [0, 0, arguments[0], 0], looks}}, 1);
return Object.keys(before).filter((name) => fx.clouds[name].next !== before[name]);
"""


def test_each_trail_replaces_the_snow_and_a_heavy_slide_stays_gold(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    assert driver.execute_script(PUFF, 1, None) == ["snow"]
    assert driver.execute_script(PUFF, 9, None) == ["star"]
    # Gold means a fish slide, so flames carry their own small flames and nothing gold
    assert driver.execute_script(PUFF, 1, "flames") == ["flame"]
    for trail in TRAIL_IDS:
        assert "snow" not in driver.execute_script(PUFF, 1, trail), trail
        # A fish's heavy slide is something the others need to see, so no trail can hide it
        assert driver.execute_script(PUFF, 9, trail) == ["star"], trail
    looks = {trail: tuple(driver.execute_script(PUFF, 1, trail)) for trail in TRAIL_IDS}
    assert len(set(looks.values())) == len(TRAIL_IDS), looks
    for trail, cloud in TRAIL_CLOUDS.items():
        assert cloud in looks[trail], (trail, looks[trail])


def test_a_trail_shows_for_that_penguin_only(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    dress(live, 1, trail="hearts")
    browser.wait_for(driver, f"{SCENE}.pens[1].looks.trail === 'hearts'")
    driver.execute_script(
        f"const fx = {FX};"
        "const total = (kind) => [...fx.clouds[kind].life].filter((life) => life > 0).length;"
        "window.peak = {heart: 0, snow: 0};"
        "window.watch = setInterval(() => {"
        "  window.peak.heart = Math.max(window.peak.heart, total('heart'));"
        "  window.peak.snow = Math.max(window.peak.snow, total('snow'));"
        "}, 16);"
    )
    glide(live, 1)
    time.sleep(0.7)
    first = driver.execute_script("return window.peak")
    # The snow is the push off, which every slide keeps. The trail itself is all hearts
    assert first["heart"] >= 3 and first["snow"] <= 6, first
    time.sleep(0.6)
    driver.execute_script("window.peak = {heart: 0, snow: 0};")
    glide(live, 2)
    time.sleep(0.7)
    second = driver.execute_script("clearInterval(window.watch); return window.peak")
    assert second["heart"] == 0 and second["snow"] > 6, second


def test_six_dressed_penguins_add_one_draw_per_thing_worn_and_none_per_skin_or_trail(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    count = f"return {SCENE}.app.stats.drawCalls.total"
    shapes = f"return {SCENE}.app.root.find((node) => node.render).length"
    time.sleep(0.3)
    # Every penguin starts in the scarf, and keeps something on its neck all through
    bare = driver.execute_script(count)
    for seat in range(6):
        dress(live, seat, hat=HAT_IDS[seat], neck="scarf", trail="hearts")
    wait_for_hat(driver, 5, HAT_IDS[5])
    time.sleep(0.3)
    hats = driver.execute_script(count)
    # A hat and something on the face, the neck and the back are one draw each. A skin only recolors the penguin
    for seat in range(6):
        dress(live, seat, trail="hearts", **{kind: WORN_IDS[kind][seat] for kind in WORN_IDS})
    wait_for_worn(driver, 5, "back", WORN_IDS["back"][5])
    time.sleep(0.3)
    dressed = driver.execute_script(count)
    print(f"draw calls: in scarves {bare}, six hats {hats}, six fully dressed {dressed}")
    assert hats - bare <= 6
    assert dressed - bare <= 18
    before = driver.execute_script(shapes)
    driver.execute_script(
        f"const fx = {FX};"
        "window.hearts = 0;"
        "fx.watch = () => { window.hearts = Math.max(window.hearts, fx.clouds.heart.instance.instancingCount); };"
        f"{SCENE}.app.on('update', fx.watch);"
    )
    for seat in range(6):
        glide(live, seat, power=0.7)
    time.sleep(0.8)
    hearts = driver.execute_script("return window.hearts")
    print(f"hearts in one draw: {hearts}")
    # Six penguins' trails all go through one drawn thing, and nothing new was made for them
    assert hearts >= 12
    assert driver.execute_script(shapes) == before


HAT_ON_SCREEN = f"""
const scene = {SCENE};
const pen = scene.pens[arguments[0]];
const box = pen.parts.head.children[0].render.meshInstances[0].aabb;
const low = box.getMin();
const high = box.getMax();
const screen = (x, y, z) => scene.camera.camera.worldToScreen(new pc.Vec3(x, y, z));
const corners = [low.x, high.x].flatMap((x) => [low.y, high.y].flatMap((y) => [low.z, high.z].map((z) => screen(x, y, z))));
const xs = corners.map((spot) => spot.x);
const ys = corners.map((spot) => spot.y);
const top = screen(pen.x, high.y, pen.z).y;
return {{wide: Math.max(...xs) - Math.min(...xs), tall: Math.max(...ys) - Math.min(...ys), top,
  tag: scene.tags.tags[arguments[0]].getBoundingClientRect().bottom}};
"""


def test_every_hat_reads_at_phone_size_and_stays_under_its_name(driver, live):
    with sized(driver, "phone", scale=2):
        sit_and_start(driver, live)
        wait_for_penguins(driver)
        calm(live)
        # Six seats, so the hats go on six at a time
        for first in range(0, len(HAT_IDS), 6):
            hats = HAT_IDS[first : first + 6]
            for seat, hat in enumerate(hats):
                dress(live, seat, hat=hat)
            wait_for_hat(driver, len(hats) - 1, hats[-1])
            time.sleep(0.3)
            keep_shot(driver, f"t12/hats-on-ice-{first // 6}.png")
            for seat, hat in enumerate(hats):
                box = driver.execute_script(HAT_ON_SCREEN, seat)
                print(hat, box)
                assert box["wide"] >= 14 and box["tall"] >= 12, (hat, box)
                assert box["tag"] <= box["top"] + 1, (hat, box)
                keep_close_up(driver, f"hat-{hat}.png", seat)


def test_every_trail_in_motion(driver, live):
    with sized(driver, "phone", scale=2):
        sit_and_start(driver, live)
        wait_for_penguins(driver)
        calm(live)
        match = match_of(live)

        async def line_up():
            for seat, penguin in enumerate(match.round.penguins):
                penguin.x, penguin.z = -2.6 + 5.2 * (seat > 3), -2.4 + 1.6 * (seat % 4)

        kinds = f"return Object.values({FX}.clouds).map((cloud) => cloud.next)"
        names = driver.execute_script(f"return Object.keys({FX}.clouds)")
        before = driver.execute_script(kinds)
        # Four slide side by side at a time, each with a trail of its own
        for first in range(0, len(TRAIL_IDS), 4):
            trails = TRAIL_IDS[first : first + 4]
            run(live, line_up())
            for seat in range(4):
                dress(live, seat, trail=trails[seat] if seat < len(trails) else None)
            browser.wait_for(driver, f"{SCENE}.pens[0].looks.trail === '{trails[0]}'")
            browser.wait_for(driver, f"{SCENE}.pens.every((pen) => pen.slide < 0.05)", timeout=6)
            time.sleep(0.3)
            for seat in range(len(trails)):
                glide(live, seat, power=0.75)
            time.sleep(0.55)
            keep_shot(driver, f"t12/trails-on-ice-{first // 4}.png")
            for seat, trail in enumerate(trails):
                keep_close_up(driver, f"trail-{trail}.png", seat)
            time.sleep(1.2)
        used = {name for name, old, new in zip(names, before, driver.execute_script(kinds)) if old != new}
        assert set(TRAIL_CLOUDS.values()) <= used, used
    assert not problems_in_console(driver)


# ---------- What admins see ----------


def price_box(driver, item):
    return driver.find_element(By.CSS_SELECTOR, f'#prices input[data-id="{item}"]')


def open_prices(driver):
    browser.wait_for(driver, "!document.getElementById('open-settings').hidden")
    driver.find_element(By.ID, "open-settings").click()
    browser.wait_for(driver, "document.querySelector('#prices input')")


def settings_status(driver):
    return driver.find_element(By.ID, "settings-status").text


def wait_for_settings_status(driver, text):
    WebDriverWait(driver, 5).until(lambda d: text in settings_status(d))


def saved_prices(live):
    return run(live, read(live.cog.config.guild_from_id(fakes.GUILD_ID).prices))


def retype(box, text):
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys(Keys.DELETE)
    if text:
        box.send_keys(text)


def test_a_server_admin_sets_prices_from_the_gear(driver, live):
    stock_shop(live)
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    open_prices(driver)
    assert driver.find_element(By.ID, "settings-today").text == "Today: 0 credits spent by 0 players."
    assert not driver.find_element(By.ID, "settings-global").is_displayed()
    assert [box.get_attribute("data-id") for box in driver.find_elements(By.CSS_SELECTOR, "#prices input")] == [*SOLD]
    assert price_box(driver, "beanie").get_attribute("value") == "1000"
    # Each box is named by the bot, and a title or a name style says what it is after its name. Read from the page
    # itself, as most of the list is scrolled out of sight
    names = driver.execute_script("return [...document.querySelectorAll('#prices label span')].map((n) => n.textContent)")
    said = {"title": " title", "name": " name style"}
    assert names == [info["name"] + said.get(info.get("kind"), "") for info in SOLD.values()]
    retype(price_box(driver, "beanie"), "5")
    retype(price_box(driver, "crown"), "")
    driver.find_element(By.ID, "save-settings").click()
    wait_for_settings_status(driver, "Saved.")
    saved = saved_prices(live)
    assert saved == {**{key: value for key, value in CATALOG.items() if key != "crown"}, "beanie": 5}
    # A price the bot refuses says why, and changes nothing
    retype(price_box(driver, "party"), "0")
    driver.find_element(By.ID, "save-settings").click()
    wait_for_settings_status(driver, "Party hat price must be a whole number")
    assert saved_prices(live) == saved
    # Text a number box can't read never turns into "not sold" by itself
    retype(price_box(driver, "party"), "1e")
    driver.find_element(By.ID, "save-settings").click()
    wait_for_settings_status(driver, "Party hat price isn't a number")
    assert saved_prices(live) == saved
    driver.find_element(By.ID, "reset-settings").click()
    assert settings_status(driver) == "Reset. Save to keep it."
    assert price_box(driver, "beanie").get_attribute("value") == "1000"
    assert price_box(driver, "crown").get_attribute("value") == "5000"
    assert saved_prices(live) == saved
    driver.find_element(By.ID, "save-settings").click()
    wait_for_settings_status(driver, "Saved.")
    assert saved_prices(live) == CATALOG
    driver.find_element(By.ID, "close-settings").click()
    assert not driver.find_element(By.ID, "settings").is_displayed()


def test_a_global_bank_says_the_prices_cover_every_server(driver, live):
    stock_shop(live)
    live.cog.shop.bank.global_bank = True
    live.user_id = fakes.OWNER_ID
    open_game(driver, live)
    open_prices(driver)
    assert driver.find_element(By.ID, "settings-global").text == (
        "The bank is global, so these prices apply in every server."
    )
    retype(price_box(driver, "beanie"), "7")
    driver.find_element(By.ID, "save-settings").click()
    wait_for_settings_status(driver, "Saved.")
    assert run(live, read(live.cog.config.prices))["beanie"] == 7


def answered(driver, action):
    return driver.execute_script(
        "return performance.getEntriesByType('resource').some((entry) =>"
        "  entry.name.endsWith(`/api/${arguments[0]}`) && entry.responseEnd > 0);",
        action,
    )


def test_players_never_see_the_gear(driver, live):
    stock_shop(live)
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    WebDriverWait(driver, 5).until(lambda d: answered(d, "shop_settings"))
    time.sleep(0.1)
    assert not driver.find_element(By.ID, "open-settings").is_displayed()
    assert not driver.execute_script("return document.getElementById('settings').open")


def test_the_gear_sits_in_the_bar_with_every_button_pressable(driver, live):
    stock_shop(live)
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    with sized(driver, "phone"):
        browser.wait_for(driver, "!document.getElementById('open-settings').hidden")
        check_presses(driver, {"open-settings", "back", "mute"})
        driver.find_element(By.ID, "open-settings").click()
        browser.wait_for(driver, "document.querySelector('#prices input')")
        keep_shot(driver, "t12/prices-phone.png")
        board_presses(driver, {"save-settings", "reset-settings", "close-settings"})


@pytest.mark.parametrize("size", ["sideways", "small upright"])
def test_the_prices_dialog_fits_and_scrolls(driver, live, size):
    stock_shop(live)
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    with sized(driver, size):
        open_prices(driver)
        keep_shot(driver, f"t12/prices-{size.replace(' ', '-')}.png")
        fit = driver.execute_script(
            "const r = document.getElementById('settings').getBoundingClientRect();"
            "return [r.top, innerHeight - r.bottom, r.left, innerWidth - r.right];"
        )
        assert min(fit) >= 0, fit
        for item in SOLD:
            box = price_box(driver, item)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", box)
            assert driver.execute_script(
                "const r = arguments[0].getBoundingClientRect();"
                "return arguments[0].contains(document.elementFromPoint(r.left + 8, r.top + r.height / 2));",
                box,
            ), item
        board_presses(driver, {"save-settings", "reset-settings", "close-settings"})
        heights = driver.execute_script(
            "return [...document.querySelectorAll('#settings button')].map((b) => b.getBoundingClientRect().height);"
        )
        assert min(heights) >= 44, heights


def test_opening_the_gear_mid_drag_fires_no_slide(driver, live, phone):
    stock_shop(live)
    live.user_id = fakes.MANAGER_ID
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    browser.wait_for(driver, f"{SCENE}.pens[0].row[3] === 0")
    browser.wait_for(driver, "!document.getElementById('open-settings').hidden")
    heard = hear_the_page(live)
    pull(driver)
    driver.execute_script("document.getElementById('open-settings').click();")
    browser.wait_for(driver, "document.querySelector('#prices input')")
    lift(driver)
    time.sleep(0.3)
    assert heard == []


def test_the_gear_dialog_stays_open_when_a_round_starts(driver, live):
    stock_shop(live)
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    sit_beside(driver, live)
    open_prices(driver)
    retype(price_box(driver, "beanie"), "42")
    match = match_of(live)

    async def hurry():
        match.countdown = 1

    run(live, hurry())
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    assert driver.execute_script("return document.getElementById('settings').open")
    assert price_box(driver, "beanie").get_attribute("value") == "42"


# ---------- The page always ends up matching the bot ----------


def tamper(driver, action, after):
    """Changes what the page gets back from one action, while the bot still runs it. `after` runs on each answer"""
    driver.execute_script(
        "const real = window.fetch;"
        "window.fetch = async (url, options) => {"
        "  const answer = await real(url, options);"
        f"  if (String(url).endsWith('/api/{action}')) {{ {after} }}"
        "  return answer;"
        "};"
    )


def short_waits(driver):
    """The page gives up on the bot in moments, so a test needn't wait out the real limit"""
    driver.execute_script(
        "const real = window.setTimeout;"
        "window.setTimeout = (fn, ms, ...rest) => real(fn, ms >= 5000 ? 300 : ms, ...rest);"
    )


def hold_the_bots_saves(live):
    """Takes the bot's lock on this player, so a buy or wear waits like a slow save. Gives back what lets it go"""
    lock = live.cog.lock(fakes.MEMBER_ID)
    run(live, lock.acquire())

    async def free():
        lock.release()

    return lambda: run(live, free())


def balance_text(driver):
    return driver.find_element(By.ID, "shop-balance").text


def act_of(driver):
    return driver.find_element(By.ID, "shop-act")


def wait_for_note(driver, text):
    WebDriverWait(driver, 5).until(lambda d: shop_note(d) == text)


def set_behind_the_page(live, owned=None, balance=None):
    """What a second device would change while this page is open"""
    if balance is not None:
        live.cog.shop.bank.balances[fakes.MEMBER_ID] = balance
    if owned is not None:
        run(live, set_value(live.cog.config.user_from_id(fakes.MEMBER_ID).owned, owned))


async def set_value(value, new):
    await value.set(new)


def test_a_refused_buy_shows_what_the_bot_has_and_keeps_the_note(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    set_behind_the_page(live, owned=["crown"], balance=9000)
    tap_item(driver, "crown")
    assert act_of(driver).text == "Buy for 5,000"
    act_of(driver).click()
    wait_for_state(driver, "crown", "Owned")
    assert shop_note(driver) == "You already own that."
    assert act_of(driver).text == "Wear" and act_of(driver).is_enabled()
    assert balance_text(driver) == "9,000 credits"


def test_a_buy_refused_for_credits_spent_elsewhere_drops_the_buy_button(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    set_behind_the_page(live, balance=10)
    tap_item(driver, "crown")
    act_of(driver).click()
    WebDriverWait(driver, 5).until(lambda d: balance_text(d) == "10 credits")
    assert shop_note(driver) == "You need 5,000 credits for that."
    assert not act_of(driver).is_displayed()


def test_a_lost_answer_still_shows_what_the_bot_did(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    tamper(driver, "buy", "throw new TypeError('The network dropped');")
    tap_item(driver, "crown")
    act_of(driver).click()
    wait_for_state(driver, "crown", "Owned")
    assert live.cog.shop.bank.balances[fakes.MEMBER_ID] == 5000
    assert balance_text(driver) == "5,000 credits"
    assert shop_note(driver) != ""
    assert act_of(driver).text == "Wear" and act_of(driver).is_enabled()


def test_an_answer_that_never_comes_never_leaves_buy_dead(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    tamper(driver, "buy", "return new Promise(() => {});")
    short_waits(driver)
    tap_item(driver, "crown")
    act_of(driver).click()
    wait_for_state(driver, "crown", "Owned")
    assert shop_note(driver) == "The bot didn't answer in time. Try again in a moment."
    assert act_of(driver).text == "Wear" and act_of(driver).is_enabled()
    act_of(driver).click()
    wait_for_state(driver, "crown", "Wearing")


def test_an_answer_later_than_the_limit_still_reaches_the_page(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    short_waits(driver)
    tap_item(driver, "crown")
    free = hold_the_bots_saves(live)
    act_of(driver).click()
    wait_for_note(driver, "The bot didn't answer in time. Try again in a moment.")
    assert act_of(driver).is_enabled() and item_state(driver, "crown") == "5,000"
    free()
    wait_for_state(driver, "crown", "Owned")
    assert balance_text(driver) == "5,000 credits"
    wait_for_note(driver, "")


def test_a_slow_answer_says_what_is_happening(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    tap_item(driver, "crown")
    for button, words, state in (
        ("Buy for 5,000", "Buying...", "Owned"),
        ("Wear", "Putting it on...", "Wearing"),
        ("Take off", "Taking it off...", "Owned"),
    ):
        act = act_of(driver)
        assert act.text == button
        free = hold_the_bots_saves(live)
        act.click()
        wait_for_note(driver, words)
        assert not act.is_enabled()
        free()
        wait_for_state(driver, "crown", state)
        if button != "Take off":
            assert act.is_enabled()


def test_a_reopen_during_a_take_off_shows_it_off(driver, live):
    stock_shop(live, owned=["beanie"], wear={"hat": "beanie"})
    open_game(driver, live)
    open_shop(driver)
    wait_for_state(driver, "beanie", "Wearing")
    tap_item(driver, "beanie")
    free = hold_the_bots_saves(live)
    act_of(driver).click()
    driver.find_element(By.ID, "close-shop").click()
    browser.wait_for(driver, "!document.getElementById('shop').open")
    driver.find_element(By.ID, "open-shop").click()
    # Nothing on show can be trusted yet, so it says so and offers nothing to press
    assert shop_note(driver) == "Loading..." and not act_of(driver).is_displayed()
    free()
    wait_for_state(driver, "beanie", "Owned")
    assert my_hat(live) is None


def test_a_reopen_during_a_buy_shows_the_buy(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    tap_item(driver, "crown")
    free = hold_the_bots_saves(live)
    act_of(driver).click()
    driver.find_element(By.ID, "close-shop").click()
    browser.wait_for(driver, "!document.getElementById('shop').open")
    driver.find_element(By.ID, "open-shop").click()
    free()
    wait_for_state(driver, "crown", "Owned")
    assert balance_text(driver) == "5,000 credits"
    tap_item(driver, "crown")
    assert act_of(driver).text == "Wear" and act_of(driver).is_enabled()


def test_closing_mid_request_leaves_the_next_visit_right(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    tap_item(driver, "crown")
    free = hold_the_bots_saves(live)
    act_of(driver).click()
    driver.find_element(By.ID, "close-shop").click()
    browser.wait_for(driver, "!document.getElementById('shop').open")
    free()
    WebDriverWait(driver, 5).until(lambda _: live.cog.shop.bank.balances[fakes.MEMBER_ID] == 5000)
    driver.find_element(By.ID, "open-shop").click()
    wait_for_cards(driver)
    wait_for_state(driver, "crown", "Owned")
    assert shop_note(driver) == "Tap something to try it on."


def test_a_refusal_stays_with_its_own_card(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    set_behind_the_page(live, owned=["crown"])
    tap_item(driver, "crown")
    free = hold_the_bots_saves(live)
    act_of(driver).click()
    wait_for_note(driver, "Buying...")
    tap_item(driver, "beanie")
    free()
    wait_for_state(driver, "crown", "Owned")
    assert shop_note(driver) == ""
    assert act_of(driver).text == "Buy for 1,000"


def test_a_fast_close_and_reopen_fills_the_shop_once(driver, live):
    stock_shop(live)
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    # Only the first load is slow, so the second one's answer lands first
    tamper(
        driver,
        "shop",
        "window.loads = (window.loads || 0) + 1; if (window.loads === 1) { await new Promise((go) => setTimeout(go, 2000)); }",
    )
    driver.find_element(By.ID, "open-shop").click()
    driver.find_element(By.ID, "close-shop").click()
    browser.wait_for(driver, "!document.getElementById('shop').open")
    driver.find_element(By.ID, "open-shop").click()
    wait_for_cards(driver)
    show_tab(driver, "hat")
    tap_item(driver, "crown")
    driver.execute_script(f"window.card = document.querySelector('{ITEM.format('crown')}');")
    time.sleep(2.2)
    assert driver.execute_script("return window.card.isConnected && window.card.getAttribute('aria-pressed')") == "true"


def test_a_fast_close_and_reopen_of_the_prices_keeps_what_is_typed(driver, live):
    stock_shop(live)
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    browser.wait_for(driver, "!document.getElementById('open-settings').hidden")
    tamper(
        driver,
        "shop_settings",
        "window.loads = (window.loads || 0) + 1; if (window.loads === 1) { await new Promise((go) => setTimeout(go, 2000)); }",
    )
    driver.find_element(By.ID, "open-settings").click()
    driver.find_element(By.ID, "close-settings").click()
    open_prices(driver)
    retype(price_box(driver, "beanie"), "77")
    driver.execute_script("window.box = document.querySelector('#prices input[data-id=\"beanie\"]');")
    time.sleep(2.2)
    assert driver.execute_script("return window.box.isConnected && window.box.value") == "77"


def test_save_and_reset_stay_off_until_the_prices_are_in(driver, live):
    stock_shop(live)
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    browser.wait_for(driver, "!document.getElementById('open-settings').hidden")
    tamper(driver, "shop_settings", "await new Promise((go) => setTimeout(go, 300));")
    buttons = (driver.find_element(By.ID, "save-settings"), driver.find_element(By.ID, "reset-settings"))
    driver.find_element(By.ID, "open-settings").click()
    assert settings_status(driver) == "Loading..."
    assert not any(button.is_enabled() for button in buttons)
    browser.wait_for(driver, "document.querySelector('#prices input')")
    assert all(button.is_enabled() for button in buttons)


def test_save_and_reset_stay_off_after_a_failed_load(driver, live):
    stock_shop(live)
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    browser.wait_for(driver, "!document.getElementById('open-settings').hidden")
    tamper(driver, "shop_settings", "throw new TypeError('The network dropped');")
    driver.find_element(By.ID, "open-settings").click()
    WebDriverWait(driver, 5).until(lambda d: settings_status(d) not in ("", "Loading..."))
    assert not driver.find_element(By.ID, "save-settings").is_enabled()
    assert not driver.find_element(By.ID, "reset-settings").is_enabled()
    assert driver.find_element(By.ID, "close-settings").is_enabled()


def test_the_preview_starts_from_the_last_known_looks(driver, live):
    stock_shop(live, owned=["crown"], wear={"hat": "crown"})
    open_game(driver, live)
    open_shop(driver)
    driver.find_element(By.ID, "close-shop").click()
    browser.wait_for(driver, "!document.getElementById('shop').open")
    tamper(driver, "shop", "throw new TypeError('The network dropped');")
    driver.find_element(By.ID, "open-shop").click()
    worn = driver.execute_script(
        "return pc.Application.getApplication().root.findByName('shop-penguin').findByName('hat')"
        ".children.map((hat) => hat.name);"
    )
    assert worn == ["hat-crown"]


def test_a_connection_gone_for_good_closes_the_shop_and_says_so(driver, live):
    stock_shop(live)
    open_game(driver, live)
    open_shop(driver)
    run(live, match_of(live).room.connections[0].close(4100))
    browser.wait_for(driver, "!document.getElementById('shop').open")
    browser.wait_for(driver, "!document.body.classList.contains('shopping')")
    assert driver.find_element(By.ID, "message").is_displayed()


GAME_CAMERA = f"{SCENE}.camera.enabled"


@pytest.mark.parametrize("size", ["phone", "sideways", "small upright", "small sideways"])
def test_the_game_rests_while_the_shop_covers_it_on_a_phone(driver, live, size):
    stock_shop(live)
    open_game(driver, live)
    with sized(driver, size):
        browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
        draws = f"return {LAST_DRAWS}"
        driver.execute_script(draws)
        time.sleep(0.3)
        before = driver.execute_script(draws)
        open_shop(driver)
        time.sleep(0.3)
        assert not driver.execute_script(f"return {GAME_CAMERA}")
        resting = driver.execute_script(draws)
        print(f"draw calls on {size}: lobby {before}, in the shop {resting}")
        # The preview costs about what the empty lobby does, so with the game drawing too it would be about double
        assert resting < before * 1.5
        # The preview still draws
        assert driver.execute_script("return pc.Application.getApplication().root.findByName('shop-camera').enabled")
        driver.find_element(By.ID, "close-shop").click()
        browser.wait_for(driver, GAME_CAMERA)
        time.sleep(0.3)
        assert driver.execute_script(draws) > before * 0.8
    assert not problems_in_console(driver)


def test_the_game_keeps_drawing_behind_the_desktop_shop(driver, live):
    stock_shop(live)
    open_game(driver, live)
    with sized(driver, "desktop"):
        open_shop(driver)
        time.sleep(0.3)
        assert driver.execute_script(f"return {GAME_CAMERA}")


def test_turning_a_window_big_wakes_the_game_behind_the_shop(driver, live):
    stock_shop(live)
    open_game(driver, live)
    with sized(driver, "phone"):
        open_shop(driver)
        browser.wait_for(driver, f"!{GAME_CAMERA}")
    # Back at the desktop size the shop is a box with the game around it
    browser.wait_for(driver, GAME_CAMERA)


def test_the_game_comes_back_when_the_shop_closes_mid_round(driver, live, phone):
    stock_shop(live)
    open_game(driver, live)
    sit_beside(driver, live, ("Ann", "Bo"))
    driver.find_element(By.ID, "open-shop").click()
    browser.wait_for(driver, f"!{GAME_CAMERA}")
    match = match_of(live)

    async def hurry():
        match.countdown = 1

    run(live, hurry())
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    time.sleep(0.3)
    # The shop still covers the phone, so the game still rests behind it
    assert not driver.execute_script(f"return {GAME_CAMERA}")
    driver.find_element(By.ID, "close-shop").click()
    browser.wait_for(driver, GAME_CAMERA)
    wait_for_penguins(driver)
    time.sleep(0.2)
    assert driver.execute_script(f"return {SCENE}.app.stats.drawCalls.total") > 60


KEYBOARD_FIT = """
const prices = document.getElementById('prices');
const box = document.activeElement;
box.scrollIntoView({block: 'nearest'});
const r = box.getBoundingClientRect();
const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
return {tall: prices.clientHeight, focused: box.tagName, hit: hit === box};
"""


@pytest.mark.parametrize("full, typing", [("sideways", (844, 190)), ("small upright", (320, 308))])
def test_a_phone_keyboard_never_squashes_the_box_being_typed_in(driver, live, full, typing):
    stock_shop(live)
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    with sized(driver, full):
        open_prices(driver)
        price_box(driver, "party").click()
        driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {"width": typing[0], "height": typing[1], "deviceScaleFactor": 1, "mobile": False},
        )
        time.sleep(0.3)
        fit = driver.execute_script(KEYBOARD_FIT)
        assert fit["focused"] == "INPUT" and fit["tall"] >= 60 and fit["hit"], fit


def test_the_sideways_shop_keeps_clear_of_a_top_inset(driver, live):
    stock_shop(live)
    open_game(driver, live)
    with sized(driver, "sideways"):
        # Discord sets it on the hub's page, and the hub hands it down to the game's page
        driver.execute_script(
            "parent.document.documentElement.style.setProperty('--discord-safe-area-inset-top', '30px');"
        )
        open_shop(driver)
        top = "return getComputedStyle(document.querySelector('.shop-panel')).paddingTop"
        WebDriverWait(driver, 3).until(lambda d: d.execute_script(top) == "30px")


# ---------- Crates and party rounds ----------


def test_the_crate_button_asks_on_the_first_press_and_pays_on_the_second(driver, live):
    price = EXTRAS["crate"]["price"]
    stock_shop(live, balance=500)
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)
    bank = live.cog.shop.bank.balances
    button = driver.find_element(By.ID, "drop-crate")
    WebDriverWait(driver, 5).until(lambda _: button.text == f"{price:,}")
    button.click()
    assert button.text == f"Drop for {price:,}?"
    time.sleep(0.3)
    assert bank[fakes.MEMBER_ID] == 500 and match.round.crate is None
    button.click()
    WebDriverWait(driver, 5).until(lambda _: match.round.crate is not None)
    WebDriverWait(driver, 5).until(lambda _: button.text == f"{price:,}" and button.is_enabled())
    assert bank[fakes.MEMBER_ID] == 500 - price


def test_a_bought_party_round_is_named_on_the_title_card_and_called_out_over_its_countdown(driver, live):
    kind, twist = next(iter(TWISTS.items()))
    stock_shop(live, balance=1000)
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    browser.wait_for(driver, "!document.getElementById('open-party').hidden")
    driver.find_element(By.ID, "open-party").click()
    browser.wait_for(driver, "document.querySelector('#twists .twist:enabled')")
    driver.find_element(By.CSS_SELECTOR, "#twists .twist").click()
    browser.wait_for(driver, "!document.getElementById('title-twist').hidden")
    assert not driver.execute_script("return document.getElementById('party').open")
    assert driver.find_element(By.ID, "title-twist").text == f"Next round: {twist['name']}, from Member"
    assert live.cog.shop.bank.balances[fakes.MEMBER_ID] == 1000 - EXTRAS["twist"]["price"]
    # Seated, the title card is out of the way of the 3-2-1
    driver.find_element(By.ID, "go").click()
    browser.wait_for(driver, "!document.getElementById('twist-call').hidden", timeout=10)
    called = driver.execute_script(
        "return [document.body.dataset.stage, document.getElementById('twist-name').textContent,"
        " document.getElementById('twist-line').textContent];"
    )
    assert called == ["starting", twist["name"], f"{twist['line']}. From Member"]
    assert match_of(live).twist["kind"] == kind


# ---------- Vert's tuning sliders ----------

SLIDER_SPOT = "const r = arguments[0].getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2];"


@contextmanager
def fingers(driver, size):
    """A page of this size that takes fingers"""
    with sized(driver, size):
        driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 2})
        try:
            yield
        finally:
            try:
                touch(driver, "touchCancel")
            except WebDriverException:
                pass
            driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": False})


def owner_on_the_ice(driver, live):
    live.user_id = fakes.OWNER_ID
    on_the_ice(driver, live)
    browser.wait_for(driver, "!document.getElementById('open-tuning').hidden")


def open_tuning(driver):
    driver.execute_script("document.getElementById('open-tuning').click();")
    browser.wait_for(driver, "document.querySelector('#sliders input')")


def slider(driver, name):
    return driver.find_element(By.CSS_SELECTOR, f'#sliders input[data-name="{name}"]')


def move_slider(driver, name, value):
    driver.execute_script(
        "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
        slider(driver, name),
        value,
    )


def bot_number(live, name):
    return getattr(live.cog.tuning, name)


def ice_box(driver):
    """Where the whole floe is on the screen: left, top, right, bottom"""
    return driver.execute_script(
        f"const scene = {SCENE}; const r = scene.floeRadius; const xs = []; const ys = [];"
        "for (let i = 0; i < 24; i++) {"
        "  const at = scene.camera.camera.worldToScreen(new pc.Vec3(Math.cos(i / 12 * Math.PI) * r, 0,"
        "    Math.sin(i / 12 * Math.PI) * r));"
        "  xs.push(at.x); ys.push(at.y);"
        "}"
        "return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];"
    )


def panel_box(driver):
    return driver.execute_script(
        "const r = document.getElementById('tuning').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom];"
    )


async def mark_dirty(live):
    match_of(live).dirty = True


def start_a_round_as_owner(driver, live):
    live.user_id = fakes.OWNER_ID
    open_game(driver, live)


def begin_round_on_screen(driver, live):
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    driver.find_element(By.ID, "go").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    wait_for_penguins(driver)
    calm(live)
    match = match_of(live)

    async def hold_the_ice():
        match.round.floe.crack_timer = 1000.0

    run(live, hold_the_ice())
    browser.wait_for(driver, f"{SCENE}.pens[0].row[3] === 0")
    browser.wait_for(driver, "!document.getElementById('open-tuning').hidden")


def test_players_and_admins_never_see_the_sliders_icon(driver, live):
    for user in (fakes.MEMBER_ID, fakes.MANAGER_ID):
        live.user_id = user
        open_game(driver, live)
        WebDriverWait(driver, 5).until(lambda d: answered(d, "tuning"))
        time.sleep(0.1)
        assert not driver.find_element(By.ID, "open-tuning").is_displayed()
        assert not driver.execute_script("return document.getElementById('tuning').open")
        driver.switch_to.default_content()


def test_moving_a_slider_changes_the_arrow_and_the_slide(driver, live, phone):
    owner_on_the_ice(driver, live)
    open_tuning(driver)
    before = bot_number(live, "slide_speed")
    pull(driver)
    shaft = arrow(driver)
    assert shaft[0]
    touch(driver, "touchCancel")
    move_slider(driver, "slide_speed", 16)
    WebDriverWait(driver, 5).until(lambda d: bot_number(live, "slide_speed") == 16)
    # The rules ride a snapshot back to the page, with no reload
    browser.wait_for(driver, f"{SCENE}.rules.slide_speed === 16")
    assert match_of(live).round.tuning.slide_speed == 16 != before
    pull(driver)
    longer = arrow(driver)
    heard = hear_the_page(live)
    lift(driver)
    WebDriverWait(driver, 5).until(lambda d: len(heard) == 1)
    assert longer[1] > shaft[1], (shaft, longer)
    assert "slide" in heard[0]
    assert not problems_in_console(driver)


def test_reset_puts_the_mockups_numbers_back(driver, live, phone):
    owner_on_the_ice(driver, live)
    open_tuning(driver)
    move_slider(driver, "seal_reach", 3)
    move_slider(driver, "ice_speed", 0.4)
    WebDriverWait(driver, 5).until(lambda d: bot_number(live, "ice_speed") == 0.4)
    assert bot_number(live, "seal_reach") == 3
    driver.find_element(By.ID, "reset-tuning").click()
    WebDriverWait(driver, 5).until(lambda d: live.cog.tuning == Tuning())
    assert run(live, read(live.cog.config.tuning)) == asdict(Tuning())
    shown = {
        box.get_attribute("data-name"): float(box.get_attribute("value"))
        for box in driver.find_elements(By.CSS_SELECTOR, "#sliders input")
    }
    assert shown == asdict(Tuning())
    texts = [out.text for out in driver.find_elements(By.CSS_SELECTOR, "#sliders output")]
    assert "11.0" in texts and "1.12" in texts and "0.9" in texts


def test_a_save_still_waiting_when_the_panel_closes_is_not_lost(driver, live, phone):
    owner_on_the_ice(driver, live)
    open_tuning(driver)
    # One script runs the move and the close together, so the 300 ms wait can't be what sends it
    driver.execute_script(
        "const box = document.querySelector('#sliders input[data-name=brace_wait]');"
        "box.value = 2.5; box.dispatchEvent(new Event('input', {bubbles: true}));"
        "document.getElementById('close-tuning').click();"
    )
    started = time.monotonic()
    WebDriverWait(driver, 5, poll_frequency=0.02).until(lambda d: bot_number(live, "brace_wait") == 2.5)
    assert time.monotonic() - started < 0.25
    assert match_of(live).round.tuning.brace_wait == 2.5


def test_a_state_update_never_rebuilds_a_slider(driver, live, phone):
    owner_on_the_ice(driver, live)
    open_tuning(driver)
    driver.execute_script("window.heldSlider = document.querySelector('#sliders input');")
    heard_before = driver.execute_script(f"return {SCENE}.rules.slide_speed;")
    assert heard_before == 11
    for _ in range(3):
        run(live, mark_dirty(live))
        time.sleep(0.3)
    assert driver.execute_script("return window.heldSlider === document.querySelector('#sliders input')")


TUNING_SIZES = [*SIZES, "small upright", "short sideways"]


def my_penguin_on_screen(driver):
    """Where the player's own penguin is drawn"""
    x, z = driver.execute_script(f"const row = {SCENE}.pens[0].row; return [row[0] / 100, row[1] / 100];")
    return screen_spot(driver, x, z)


@pytest.mark.parametrize("size", TUNING_SIZES)
def test_the_sheet_leaves_the_ice_and_the_buttons_alone(driver, live, size):
    start_a_round_as_owner(driver, live)
    with fingers(driver, size):
        begin_round_on_screen(driver, live)
        check_presses(driver, {"open-tuning", "back", "mute"})
        open_tuning(driver)
        time.sleep(1.5)
        keep_shot(driver, f"t13/tuning-{size}.png")
        check_presses(driver, {"open-tuning", "back", "mute", "reset-tuning", "close-tuning"})
        # The heading reads whole, not cut by the buttons beside it
        heading = "const head = document.getElementById('tuning-head'); return [head.clientWidth, head.scrollWidth];"
        room, needs = driver.execute_script(heading)
        assert room >= needs, (room, needs)
        dialog = driver.find_element(By.ID, "tuning")
        assert dialog.tag_name == "dialog"
        assert not driver.execute_script("return arguments[0].matches(':modal')", dialog)
        ice, panel = ice_box(driver), panel_box(driver)
        assert ice[2] <= panel[0] + 1 or ice[3] <= panel[1] + 1, (ice, panel)
        width, height = {**SIZES, **SMALL, **SHORT}[size]
        # The player's own penguin is clear of the sheet, with a body's width to spare
        mine = my_penguin_on_screen(driver)
        assert mine[0] <= panel[0] - 25 or mine[1] <= panel[1] - 25, (mine, panel)
        assert min(panel) >= 0 and panel[2] <= width + 1 and panel[3] <= height + 1, panel
        # Every slider can be reached by scrolling, and its middle takes the press
        for name in asdict(Tuning()):
            box = slider(driver, name)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", box)
            assert driver.execute_script(
                "const r = arguments[0].getBoundingClientRect();"
                "return arguments[0] === document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);",
                box,
            ), name


def test_the_sheet_keeps_its_heading_and_buttons_clear_of_a_notch(driver, live):
    start_a_round_as_owner(driver, live)
    with fingers(driver, "sideways"):
        begin_round_on_screen(driver, live)
        driver.execute_script(f"document.documentElement.style.setProperty('{NOTCH.format('right')}', '47px');")
        open_tuning(driver)
        check_presses(driver, {"reset-tuning", "close-tuning"})
        heading = "const head = document.getElementById('tuning-head'); return [head.clientWidth, head.scrollWidth];"
        room, needs = driver.execute_script(heading)
        assert room >= needs, (room, needs)
        right = "return document.getElementById('close-tuning').getBoundingClientRect().right"
        assert driver.execute_script(right) <= SIZES["sideways"][0] - 47


@pytest.mark.parametrize("size", NARROW)
def test_no_slider_scrolls_under_the_hubs_frame_rate_counter(driver, live, size):
    start_a_round_as_owner(driver, live)
    with sized(driver, size):
        begin_round_on_screen(driver, live)
        open_tuning(driver)
        time.sleep(0.5)
        sliders = driver.execute_script(
            "const r = document.getElementById('sliders').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom];"
        )
        driver.switch_to.default_content()
        browser.wait_for(driver, "document.querySelector('.fps').textContent")
        counter = driver.execute_script(
            "const r = document.querySelector('.fps').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom];"
        )
        # The box the sliders scroll in ends above the counter, or beside it on a sideways phone
        assert sliders[3] <= counter[1] or sliders[0] >= counter[2], (sliders, counter)


@pytest.mark.parametrize("size", TUNING_SIZES)
def test_a_finger_on_a_slider_never_reaches_the_game_but_one_on_the_ice_does(driver, live, size):
    start_a_round_as_owner(driver, live)
    with fingers(driver, size):
        begin_round_on_screen(driver, live)
        open_tuning(driver)
        heard = hear_the_page(live)
        box = slider(driver, "slide_wait")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", box)
        x, y = driver.execute_script(SLIDER_SPOT, box)
        before = bot_number(live, "slide_wait")
        pull(driver, (x - 20, y), (x + 20, y))
        shown = arrow(driver)[0]
        lift(driver)
        time.sleep(0.3)
        assert heard == [] and not shown
        WebDriverWait(driver, 5).until(lambda d: bot_number(live, "slide_wait") != before)
        # A finger on the ice, clear of the sheet, still starts a drag and slides
        left, top, right, bottom = ice_box(driver)
        start = ((left + right) / 2, (top + bottom) / 2)
        pull(driver, start, (start[0], start[1] - 50))
        assert arrow(driver)[0]
        lift(driver)
        WebDriverWait(driver, 5).until(lambda d: len(heard) == 1)
        assert "slide" in heard[0]


@pytest.mark.parametrize("how", ["pagehide", "back"])
def test_a_save_waiting_when_the_player_leaves_is_not_lost(driver, live, phone, how):
    owner_on_the_ice(driver, live)
    open_tuning(driver)
    driver.execute_script(
        "const box = document.querySelector('#sliders input[data-name=seal_wait]');"
        "box.value = 4; box.dispatchEvent(new Event('input', {bubbles: true}));"
    )
    started = time.monotonic()
    if how == "pagehide":
        driver.execute_script("window.dispatchEvent(new Event('pagehide'));")
    else:
        # A real press: the menu takes the game's page away as soon as the press has been handled
        driver.find_element(By.ID, "back").click()
    WebDriverWait(driver, 5, poll_frequency=0.02).until(lambda d: bot_number(live, "seal_wait") == 4)
    assert time.monotonic() - started < 0.25


class BrokenLock:
    async def __aenter__(self):
        raise RuntimeError("disk full")

    async def __aexit__(self, *details):
        return False


def test_after_a_failed_save_the_sliders_show_what_the_bot_has(driver, live, phone):
    owner_on_the_ice(driver, live)
    open_tuning(driver)
    live.cog.tuning_lock = BrokenLock()
    move_slider(driver, "slide_speed", 15)
    WebDriverWait(driver, 5).until(lambda d: slider(d, "slide_speed").get_attribute("value") == "11")
    assert bot_number(live, "slide_speed") == 11
    assert driver.find_element(By.ID, "tuning-status").text


def test_reopening_right_after_closing_shows_the_saved_numbers(driver, live, phone):
    owner_on_the_ice(driver, live)
    open_tuning(driver)
    driver.execute_script(
        "const box = document.querySelector('#sliders input[data-name=fish_boost]');"
        "box.value = 1.4; box.dispatchEvent(new Event('input', {bubbles: true}));"
        "document.getElementById('close-tuning').click();"
        "document.getElementById('open-tuning').click();"
    )
    browser.wait_for(driver, "document.querySelector('#sliders input')")
    assert float(slider(driver, "fish_boost").get_attribute("value")) == 1.4


# ---------- Two people on one window ----------

FRIEND = fakes.MOD_ID


@pytest.fixture
def friend():
    """A second person's own browser. Each test gets a new one, as each is a second copy of Chrome drawing in software"""
    chrome = start_chrome()
    try:
        yield chrome
    finally:
        chrome.quit()


def two_on_the_ice(driver, friend, live):
    """Both people seated in a round with the CPUs and the ice held still. Gives the friend's seat"""
    open_game(driver, live)
    live.user_id = FRIEND
    open_game(friend, live)
    browser.wait_for(friend, "document.body.dataset.stage === 'waiting'")
    match = match_of(live)

    async def seat_the_friend():
        # Alone, Play starts a round at once, so the friend is seated the way the line seats someone
        match.seat_person(5, match.conn_of(FRIEND))

    run(live, seat_the_friend())
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    driver.find_element(By.ID, "go").click()
    browser.wait_for(driver, "!document.getElementById('start').hidden")
    driver.find_element(By.ID, "start").click()
    for chrome in (driver, friend):
        browser.wait_for(chrome, "document.body.dataset.stage === 'playing'", timeout=10)
        wait_for_penguins(chrome)
    calm(live)
    match = match_of(live)

    async def hold_the_ice():
        match.round.floe.crack_timer = 1000.0

    run(live, hold_the_ice())
    return next(number for number, seat in enumerate(match.seats) if seat.user_id == FRIEND)


def fingers_on(chrome):
    width, height = SIZES["phone"]
    chrome.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    chrome.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 2})


def assert_both_clean(driver, friend):
    assert problems_in_console(driver) == []
    assert problems_in_console(friend) == []


def test_two_people_see_each_others_tag_and_slide(driver, friend, live):
    seat = two_on_the_ice(driver, friend, live)
    names = ("Member", "Mod")
    for chrome in (driver, friend):
        shown = {tag[0]: tag[2] for tag in shown_tags(chrome)}
        assert set(names) <= set(shown) and len(shown) == 6, shown
    assert {tag[0]: tag[2] for tag in shown_tags(driver)}["Member"] is True
    assert {tag[0]: tag[2] for tag in shown_tags(friend)}["Mod"] is True
    fingers_on(driver)
    fingers_on(friend)
    browser.wait_for(driver, f"{SCENE}.pens[0].row[3] === 0")
    browser.wait_for(friend, f"{SCENE}.pens[{seat}].row[3] === 0")
    for mover, watcher, name in ((driver, friend, "penguin-0"), (friend, driver, f"penguin-{seat}")):
        before = drawn(watcher, name)

        def moved(chrome):
            now = drawn(chrome, name)
            return hypot(now[1] - before[1], now[3] - before[3]) > 1

        pull(mover)
        lift(mover)
        WebDriverWait(watcher, 4).until(moved)
    assert_both_clean(driver, friend)


def test_someone_dropping_shows_as_away_and_keeps_their_seat_if_back_in_time(driver, friend, live):
    seat = two_on_the_ice(driver, friend, live)
    match = match_of(live)
    friend.get("about:blank")
    browser.wait_for(driver, f"{SCENE}.tags.tags[{seat}].classList.contains('away')", timeout=5)
    assert match.seats[seat].dropped_at is not None
    assert match.seats[seat].user_id == FRIEND
    open_game(friend, live)
    browser.wait_for(friend, f"{SCENE}.pens[{seat}].row !== null")
    browser.wait_for(driver, f"!{SCENE}.tags.tags[{seat}].classList.contains('away')", timeout=5)
    assert match.seats[seat].user_id == FRIEND and match.seats[seat].dropped_at is None
    # Their own penguin again, ring and all, on a round that carried on
    browser.wait_for(friend, f"{SCENE}.mySeat === {seat}")
    browser.wait_for(friend, f"{SCENE}.tags.tags[{seat}].classList.contains('you')")
    assert_both_clean(driver, friend)


def test_someone_gone_too_long_is_replaced_by_a_cpu_and_can_watch_on_return(driver, friend, live):
    seat = two_on_the_ice(driver, friend, live)
    match = match_of(live)
    friend.get("about:blank")
    WebDriverWait(driver, 5).until(lambda _: match.seats[seat].dropped_at is not None)

    async def wait_is_over():
        match.seats[seat].dropped_at -= GRACE_SECONDS

    run(live, wait_is_over())
    WebDriverWait(driver, 5).until(lambda _: not match.seats[seat].human)
    browser.wait_for(driver, f"!{SCENE}.tags.tags[{seat}].classList.contains('away')", timeout=5)
    name = driver.execute_script(f"return {SCENE}.tags.tags[{seat}].textContent")
    assert name != "Mod" and name
    assert match.stage == "playing"
    open_game(friend, live)
    browser.wait_for(friend, "document.getElementById('hint').textContent === 'Watching. Tap to join the line'")
    assert_both_clean(driver, friend)


# ---------- The phone pass ----------

DRAW_BUDGET = 250
ARRIVALS_QUIET = 5.5
READS_OF_TAGS = """
window.tagReads = 0;
for (const name of ['offsetWidth', 'offsetHeight']) {
  const real = Object.getOwnPropertyDescriptor(HTMLElement.prototype, name);
  Object.defineProperty(HTMLElement.prototype, name, {
    configurable: true,
    get() {
      if (this.classList.contains('tag')) {
        window.tagReads += 1;
      }
      return real.get.call(this);
    },
  });
}
"""


def frames_pass(driver, count=12):
    """Wait until the engine has drawn this many more frames"""
    driver.execute_async_script(
        "const [count, done] = arguments; const app = pc.Application.getApplication(); let left = count;"
        "const tick = () => { left -= 1; if (left <= 0) { app.off('frameend', tick); done(); } };"
        "app.on('frameend', tick);",
        count,
    )


def test_a_tags_size_is_only_read_when_its_words_change(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    driver.execute_script(READS_OF_TAGS)
    frames_pass(driver)
    assert driver.execute_script("return window.tagReads") == 0
    match = match_of(live)

    async def rename():
        match.seats[1].name = "Someone Much Longer"
        match.dirty = True

    before = driver.execute_script(f"return {SCENE}.tags.looks[1].width")
    run(live, rename())
    browser.wait_for(driver, f"{SCENE}.tags.tags[1].textContent.startsWith('Someone')")
    frames_pass(driver)
    # Width and height, once
    assert driver.execute_script("return window.tagReads") == 2
    assert driver.execute_script(f"return {SCENE}.tags.looks[1].width") > before
    # The game's font arriving changes every name
    driver.execute_script("window.tagReads = 0; document.fonts.dispatchEvent(new Event('loadingdone'));")
    frames_pass(driver)
    assert driver.execute_script("return window.tagReads") == 12


ROW_CHANGE = f"""
const scene = {SCENE};
const {{ tags }} = scene;
scene.app.off("prerender", scene.drawTags, scene);
const spot = (x, y) => ({{ x, y, seal: false }});
const rest = [null, null, null, null];
const top = () => tags.tags[1].getBoundingClientRect().top;
tags.place([spot(200, 300), spot(500, 300), ...rest], 1 / 60);
const start = top();
const tops = [];
for (let frame = 0; frame < 40; frame += 1) {{
  tags.place([spot(200, 300), spot(200, 300), ...rest], 1 / 60);
  tops.push(top());
}}
tags.place([spot(200, 300), null, ...rest], 1 / 60);
tags.place([spot(200, 300), spot(200, 300), ...rest], 1 / 60);
return {{ start, tops, comeBack: top() }};
"""


def test_a_name_moves_to_a_new_row_over_several_frames(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    row = driver.execute_script(ROW_CHANGE)
    tops = [row["start"], *row["tops"]]
    whole_way = abs(tops[-1] - tops[0])
    assert whole_way >= 18, tops
    # A name that comes on starts in its row, with nothing to ease from
    assert row["comeBack"] == pytest.approx(tops[-1], abs=0.5)
    steps = [abs(later - earlier) for earlier, later in zip(tops, tops[1:])]
    assert max(steps) <= whole_way * 0.3, tops
    assert sum(step > 0.5 for step in steps) >= 4, tops


TAG_TRAIL = f"""
const scene = {SCENE};
window.tagTrail = [];
scene.app.on('frameend', () => {{
  const tags = [];
  scene.tags.tags.forEach((tag, seat) => {{
    if (!tag.hidden) {{
      const box = tag.getBoundingClientRect();
      const {{ rise, aim }} = scene.tags.looks[seat];
      tags.push([seat, box.left, box.top, box.right, box.bottom, Math.abs(rise - aim) < 0.5]);
    }}
  }});
  window.tagTrail.push([performance.now(), tags]);
}});
"""
# Five penguins packed close on an upright phone, with the player's own sliding into them from up the ice
PILE = [(-0.5, 1.6), (0.5, 1.6), (0.0, 2.45), (-0.9, 2.5), (1.0, 2.55)]


def crossings(trail):
    """For each frame, the pairs of tags drawn over each other, and whether both had reached their spots"""
    frames = []
    for ms, tags in trail:
        crossed = []
        for index, a in enumerate(tags):
            for b in tags[index + 1 :]:
                across = min(a[3], b[3]) - max(a[1], b[1])
                down = min(a[4], b[4]) - max(a[2], b[2])
                if across > 0.5 and down > 0.5:
                    crossed.append(((a[0], b[0]), a[5] and b[5]))
        frames.append((ms, crossed))
    return frames


def longest_crossing(frames):
    """How long, in milliseconds, the longest run of frames with the same two tags drawn over each other lasts"""
    since, longest = {}, 0.0
    for ms, crossed in frames:
        now = {pair for pair, _ in crossed}
        for pair in now - since.keys():
            since[pair] = ms
        for pair in set(since) - now:
            longest = max(longest, ms - since.pop(pair))
    return max([longest, *(frames[-1][0] - start for start in since.values())])


def test_names_in_a_pile_never_sit_on_each_other(driver, live):
    with sized(driver, "narrow upright"):
        sit_and_start(driver, live)
        wait_for_penguins(driver)
        calm(live)
        match = match_of(live)

        async def pile_up():
            match.round.floe.crack_timer = 1000.0
            for seat, (x, z) in enumerate(PILE, start=1):
                penguin = match.round.penguins[seat]
                penguin.x, penguin.z, penguin.vx, penguin.vz = x, z, 0.0, 0.0
            match.round.penguins[0].x, match.round.penguins[0].z, match.round.penguins[0].cd = 0.0, -1.5, 0.0
            match.dirty = True

        run(live, pile_up())
        time.sleep(1.2)
        driver.execute_script(TAG_TRAIL)

        async def slide_in():
            assert match.round.slide(0, 0.05, 1, 0.75)

        run(live, slide_in())
        time.sleep(2.5)
        frames = crossings(driver.execute_script("return window.tagTrail"))
        assert len(frames) > 60
        # Two names that have reached their spots never sit on each other
        assert not [frame for frame in frames if any(settled for _, settled in frame[1])]
        # One easing over to a new spot may pass over another, but only for a moment
        assert longest_crossing(frames) <= 100, [frame for frame in frames if frame[1]]


HAT_AND_TAG = f"""
const scene = {SCENE};
const pen = scene.pens[arguments[0]];
const instance = pen.parts.head.children[0].render.meshInstances[0];
const world = instance.node.getWorldTransform();
const points = [];
instance.mesh.getPositions(points);
let top = Infinity;
const point = new pc.Vec3();
for (let i = 0; i < points.length; i += 3) {{
  world.transformPoint(point.set(points[i], points[i + 1], points[i + 2]), point);
  top = Math.min(top, scene.camera.camera.worldToScreen(point).y);
}}
return {{ top, tag: scene.tags.tags[arguments[0]].getBoundingClientRect().bottom, slide: pen.slide }};
"""


@pytest.mark.parametrize("hat", ["tophat", "party", "wizard"])
def test_a_tall_hat_stays_under_its_name_through_a_slide(driver, live, hat):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    dress(live, 1, hat=hat)
    wait_for_hat(driver, 1, hat)
    match = match_of(live)

    async def send_away():
        # Up the screen, where a hat on a penguin lying down points at its own name
        penguin = match.round.penguins[1]
        penguin.x, penguin.z, penguin.cd = 0.0, 3.0, 0.0
        assert match.round.slide(1, 0, -1, 0.9)

    run(live, send_away())
    browser.wait_for(driver, f"{SCENE}.pens[1].slide > 0.9", timeout=4)
    spots = [driver.execute_script(HAT_AND_TAG, 1) for _ in range(8)]
    lying = [spot for spot in spots if spot["slide"] > 0.7]
    assert lying, spots
    keep_shot(driver, f"t14/hat-mid-slide-{hat}.png")
    for spot in lying:
        assert spot["tag"] <= spot["top"] + 3, spot


NAME_LIFT = f"""
const scene = {SCENE};
const pen = scene.pens[arguments[0]];
const looks = pen.looks;
const worn = scene.tagSpot(pen).y;
pen.looks = {{}};
const bare = scene.tagSpot(pen).y;
pen.looks = looks;
return {{ lift: bare - worn, slide: pen.slide }};
"""


def test_a_hats_name_goes_back_to_its_place_once_the_slide_is_over(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    dress(live, 1, hat="tophat")
    wait_for_hat(driver, 1, "tophat")
    assert driver.execute_script(NAME_LIFT, 1)["lift"] == 0
    glide(live, seat=1)
    browser.wait_for(driver, f"{SCENE}.pens[1].slide > 0.9", timeout=4)
    browser.wait_for(driver, f"!{SCENE}.pens[1].sliding && {SCENE}.pens[1].slide < 0.01", timeout=6)
    settled = driver.execute_script(NAME_LIFT, 1)
    assert settled["lift"] == 0 and settled["slide"] > 0, settled


def shadow_depth(driver):
    """How deep the sun's shadow range runs, which the engine fits to the boxes of everything casting a shadow"""
    frames_pass(driver)
    return driver.execute_script(
        "const sun = pc.Application.getApplication().root.findByName('sun').light.light;"
        "return sun._renderData[0].shadowCamera.farClip;"
    )


def test_the_ice_keeps_one_shadow_depth_in_the_lobby_and_in_a_round(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    lobby = shadow_depth(driver)
    driver.find_element(By.ID, "go").click()
    browser.wait_for(driver, "document.body.dataset.stage === 'playing'", timeout=10)
    calm(live)
    wait_for_penguins(driver)
    spread_out = shadow_depth(driver)
    match = match_of(live)

    async def huddle():
        for seat, penguin in enumerate(match.round.penguins):
            penguin.x, penguin.z = 0.4 * seat, 0.0

    run(live, huddle())
    time.sleep(0.5)
    huddled = shadow_depth(driver)
    assert spread_out == pytest.approx(lobby, rel=0.1) and huddled == pytest.approx(lobby, rel=0.1), (
        lobby,
        spread_out,
        huddled,
    )


NOTCH = "--discord-safe-area-inset-{}"


def card_box(driver):
    return driver.execute_script(
        "const r = document.querySelector('#title .card').getBoundingClientRect();"
        "const style = getComputedStyle(document.getElementById('title'));"
        "return {left: r.left, right: innerWidth - r.right, bottom: innerHeight - r.bottom,"
        " padding: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft].map(parseFloat)};"
    )


def test_the_sideways_cards_keep_clear_of_a_notch_on_every_side(driver, live):
    with sized(driver, "sideways"):
        open_game(driver, live)
        browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
        bare = card_box(driver)
        assert bare["padding"][1:] == [10, 10, 10]
        for side in ("left", "right", "bottom"):
            driver.execute_script(f"document.documentElement.style.setProperty('{NOTCH.format(side)}', '47px');")
        box = card_box(driver)
        assert box["padding"][1:] == [47, 47, 47], box
        assert box["left"] >= 47 and box["right"] >= 47 and box["bottom"] >= 47, box


BAR_WIDTHS = (320, 340, 360, 375, 390, 400, 412, 430)
BAR_FIT = """
const bar = document.getElementById('bar');
const left = document.getElementById('left');
const buttons = [...bar.querySelectorAll('button')].filter((button) => button.getClientRects().length);
const words = left.getBoundingClientRect();
return {
  chip: document.getElementById('round').getBoundingClientRect().height,
  words: [words.width, words.height, left.scrollWidth, left.clientWidth],
  room: bar.querySelector('.grow').getBoundingClientRect().width,
  over: bar.scrollWidth - bar.clientWidth,
  inside: buttons.every((button) => {
    const box = button.getBoundingClientRect();
    return box.left >= 0 && box.right <= innerWidth;
  }),
  rows: new Set(buttons.map((button) => Math.round(button.getBoundingClientRect().top))).size,
};
"""


def bar_at(driver, width, inset):
    """The bar on an upright phone this wide, with Discord's safe area this deep on both sides"""
    driver.switch_to.default_content()
    for side in ("left", "right"):
        driver.execute_script(f"document.documentElement.style.setProperty('{NOTCH.format(side)}', '{inset}px');")
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride", {"width": width, "height": 747, "deviceScaleFactor": 1, "mobile": False}
    )
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(driver, f"innerWidth === {width}")
    browser.wait_for(
        driver,
        f"getComputedStyle(document.documentElement).getPropertyValue('{NOTCH.format('left')}').trim() === '{inset}px'",
    )
    frames_pass(driver, 3)
    return driver.execute_script(BAR_FIT)


@pytest.mark.parametrize("inset", [0, 24])
@pytest.mark.parametrize("who", [fakes.MEMBER_ID, fakes.ADMIN_ID, fakes.OWNER_ID])
def test_the_count_never_wraps_and_drops_its_words_only_without_room(driver, live, who, inset):
    live.user_id = who
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    browser.wait_for(
        driver, f"!document.getElementById('open-settings').hidden === {str(who != fakes.MEMBER_ID).lower()}"
    )
    browser.wait_for(driver, f"!document.getElementById('open-tuning').hidden === {str(who == fakes.OWNER_ID).lower()}")
    try:
        for width in BAR_WIDTHS:
            bar = bar_at(driver, width, inset)
            shown, tall, needs, has = bar["words"]
            # One line: two would make the words about 38 px tall and the chip taller than the buttons
            assert bar["chip"] < 40 and tall < 25, (width, bar)
            # The words show whole or not at all, and only go when the bar has no room for them
            assert shown == 0 or needs <= has, (width, bar)
            assert shown > 0 or bar["room"] < needs + 8, (width, bar)
            assert bar["inside"] and bar["rows"] == 1, (width, bar)
            assert inset or bar["over"] <= 0, (width, bar)
            if who == fakes.MEMBER_ID:
                assert shown > 0, (width, bar)
            if who == fakes.OWNER_ID and width == 360:
                assert shown == 0, bar
    finally:
        driver.switch_to.default_content()
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_the_fish_leaves_the_beak_with_the_slide(driver, live, phone):
    on_the_ice(driver, live)
    match = match_of(live)

    async def give_fish():
        match.round.penguins[0].fish = True

    run(live, give_fish())
    in_beak = f"{SCENE}.pens[0].parts.beakFish.enabled"
    browser.wait_for(driver, in_beak)
    hold_the_bot(live)
    pull(driver)
    lift(driver)
    # The bot hasn't said a word, and the fish has gone with the slide
    browser.wait_for(driver, f"{SCENE}.prediction.ghost.active", timeout=1)
    frames_pass(driver, 2)
    assert driver.execute_script(f"return {in_beak}") is False
    # A slide the bot never takes gives it back
    browser.wait_for(driver, f"!{SCENE}.prediction.ghost.active", timeout=3)
    browser.wait_for(driver, in_beak)


def test_a_seal_lands_on_the_new_circle_after_a_reconnect_over_shrunken_ice(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    keep_company(live)
    match = match_of(live)

    async def hold_and_drown():
        match.round.floe.crack_timer = 1000.0
        match.round.fall(1)

    run(live, hold_and_drown())
    WebDriverWait(driver, 5).until(lambda d: drawn(d, "seal-1")[0])
    time.sleep(0.6)

    async def lose_the_rim():
        for tile in match.round.floe.tiles:
            if tile.ring == 4:
                tile.state, tile.t = 3, 0.0

    connection = match.room.connections[0]
    run(live, connection.close(1012))
    browser.wait_for(driver, "!document.getElementById('banner').hidden", timeout=2)
    run(live, lose_the_rim())
    driver.execute_script(
        f"const scene = {SCENE};"
        "const seal = pc.Application.getApplication().root.findByName('seal-1');"
        "window.radii = [];"
        "scene.app.on('frameend', () => {"
        "  const at = seal.getPosition();"
        "  window.radii.push([Math.hypot(at.x, at.z), scene.floeRadius + 0.8]);"
        "});"
    )
    browser.wait_for(driver, "document.getElementById('banner').hidden", timeout=8)
    browser.wait_for(driver, f"{SCENE}.tiles.filter((tile) => tile.state === 3).length === 24", timeout=4)
    frames_pass(driver, 3)
    radii = driver.execute_script("return window.radii")
    shrunk = [(far, circle) for far, circle in radii if circle < radii[0][1]]
    assert shrunk, radii[-10:]
    assert all(abs(far - circle) < 0.1 for far, circle in shrunk), shrunk[:10]


def test_a_frame_before_the_first_snapshot_shows_no_round_chip(driver, live):
    real = live.cog.window_match

    async def frame_first(conn):
        await conn.send({"f": 1, "p": [[0, 0, 1, 0]] * 6})
        await asyncio.sleep(0.8)
        return await real(conn)

    live.cog.window_match = frame_first
    open_game(driver, live)
    frames_pass(driver, 3)
    assert driver.execute_script("return document.body.dataset.stage") is None
    assert driver.execute_script("return document.getElementById('round').hidden") is True
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'", timeout=5)
    assert driver.execute_script("return document.getElementById('round').hidden") is True


def test_the_hubs_arrival_note_never_sits_on_the_watching_row(driver, live, phone):
    open_game(driver, live)
    browser.wait_for(driver, "document.body.dataset.stage === 'waiting'")
    # The hub says nothing about who is here in a player's first moments, only about who arrives after that
    time.sleep(ARRIVALS_QUIET)
    for person in (fakes.ADMIN_ID, fakes.MOD_ID, fakes.OWNER_ID):
        live.add_person(person, where="penguinwars", status="Watching")
    # The note and the row at their widest, once all three have arrived
    browser.wait_for(driver, "document.querySelector('.hub-note')?.textContent.includes('others')", timeout=5)
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 4")
    note, row = driver.execute_script(
        "return ['.hub-note', '#watching'].map((name) => {"
        "  const r = document.querySelector(name).getBoundingClientRect();"
        "  return {left: r.left, right: r.right, top: r.top, bottom: r.bottom};"
        "});"
    )
    print(note, row)
    assert note["bottom"] <= row["top"] or note["left"] >= row["right"], (note, row)


def test_a_tall_phone_sees_no_line_where_the_sea_ends(driver, live, phone):
    on_the_ice(driver, live)
    shot = Image.open(BytesIO(driver.get_screenshot_as_png())).convert("RGB")
    # Past the bar's chips at the very top, and the open sea further down
    top, sea = shot.getpixel((200, 2)), shot.getpixel((200, 150))
    assert max(abs(a - b) for a, b in zip(top, sea)) <= 2, (top, sea)


def test_a_six_penguin_round_stays_under_the_draw_budget(driver, live):
    sit_and_start(driver, live)
    wait_for_penguins(driver)
    calm(live)
    # Everyone in everything: a skin, a hat, something on the face, the neck and the back, and a trail
    for seat in range(6):
        dress(live, seat, trail=TRAIL_IDS[seat], **{kind: WORN_IDS[kind][seat] for kind in WORN_IDS})
    wait_for_worn(driver, 5, "back", WORN_IDS["back"][5])
    driver.execute_script(
        f"const scene = {SCENE};"
        "window.draws = [];"
        "scene.app.on('frameend', () => window.draws.push(scene.app.stats.drawCalls.total));"
    )
    match = match_of(live)

    async def busy_ice():
        rim = [tile for tile in match.round.floe.tiles if tile.ring == 4]
        for tile in rim[:6]:
            tile.state, tile.t = 1, 0.0
        for tile in rim[6:12]:
            tile.state, tile.t = 2, 0.0
        match.dirty = True

    run(live, busy_ice())
    for seat in range(6):
        glide(live, seat, power=0.9)
    time.sleep(1)
    draws = driver.execute_script("return window.draws")
    print(f"draw calls in a six-penguin round: most {max(draws)}, last {draws[-1]}")
    assert max(draws) <= DRAW_BUDGET
