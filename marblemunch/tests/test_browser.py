import asyncio
import time
from types import SimpleNamespace

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from marblemunch.main import MarbleMunch

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="marblemunch"]'


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


def open_game(driver, live):
    driver.get(f"{live.url}/{browser.DISCORD_QUERY}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
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
    driver.find_element(By.ID, "start").click()
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    conn = next(iter(live.cog.matches.values())).room.connections[0]
    run(live, conn.close(4100))
    WebDriverWait(driver, 10).until(lambda _: me.status == "Not connected")
    assert me.busy is False


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
