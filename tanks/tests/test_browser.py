import asyncio
from types import SimpleNamespace

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.select import Select

from tanks.main import Tanks

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="tanks"]'
UPRIGHT_PHONE = {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}


class Player:
    """Someone playing on another device, seated by the test straight into the match"""

    def __init__(self, user_id, name):
        avatar = SimpleNamespace(url="")
        author = SimpleNamespace(id=user_id, name=name, display_name=name, global_name=name, display_avatar=avatar)
        self.ctx = SimpleNamespace(author=author)

    async def send(self, data):
        pass


@pytest.fixture(scope="module")
def driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
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
def cog():
    return Tanks(bot=None)


@pytest.fixture
def live(tmp_path, driver, cog):
    hub = fakes.make_hub()
    assert fakes.register(hub, cog) is not None
    server = browser.LiveHub(hub, browser.hub_web_copy(tmp_path))
    server.start()
    driver.set_window_size(1280, 800)
    browser.fresh(driver, server)
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
    browser.wait_for(driver, "document.querySelectorAll('#seats li').length === 5", timeout=20)


def test_a_match_against_a_computer_starts_and_plays_a_shot(driver, live):
    open_game(driver, live)
    driver.find_element(By.CSS_SELECTOR, "#seats li:first-child button").click()
    browser.wait_for(driver, "!document.getElementById('start').hidden")
    Select(driver.find_element(By.CSS_SELECTOR, "#seats li:nth-child(2) select")).select_by_value("easy")
    browser.wait_for(driver, "!document.getElementById('start').disabled")
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'shop'", timeout=10)
    driver.find_element(By.ID, "done").click()
    browser.wait_for(driver, "!document.getElementById('controls').classList.contains('waiting')", timeout=10)
    ActionChains(driver).key_down(Keys.ARROW_UP).pause(0.3).key_up(Keys.ARROW_UP).send_keys(Keys.SPACE).perform()
    # The shot plays, then the computer takes its turn
    browser.wait_for(driver, "document.querySelector('#cards .turn.seat-1')", timeout=20)
    driver.switch_to.default_content()
    assert browser.wait_for(driver, "/\\d+ TPS$/.test(document.querySelector('.fps').textContent)", timeout=5)
    problems = [line for line in browser.console_lines(driver) if "Uncaught" in line or "Tanks" in line]
    assert not problems, problems


def watch_a_match_start(driver, live, cog):
    """Open the game as a watcher while two people elsewhere and a computer start a match. The first is done shopping"""
    open_game(driver, live)
    match = next(iter(cog.matches.values()))
    first, second = Player(901, "Vainne"), Player(902, "Vert")

    async def start():
        for number, player in ((0, first), (2, second)):
            seat = match.seats[number]
            seat.user_id, seat.name, seat.board_name, seat.conn = (
                player.ctx.author.id,
                player.ctx.author.name,
                "",
                player,
            )
        match.seats[1].level, match.seats[1].name = "normal", "CPU 2"
        match.fix_host()
        match.start_match(first, True)
        await match.message(first, {"done": True})

    asyncio.run_coroutine_threadsafe(start(), live.loop).result(10)
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'shop'", timeout=10)
    return match, first, second


def test_watchers_see_who_is_still_shopping(driver, live, cog):
    watch_a_match_start(driver, live, cog)
    browser.wait_for(driver, "document.querySelectorAll('#shoppers li').length === 3", timeout=10)
    rows = driver.find_elements(By.CSS_SELECTOR, "#shoppers li")
    assert [row.find_element(By.CSS_SELECTOR, ".status").text for row in rows] == ["Done", "Ready", "Shopping"]
    assert not driver.find_element(By.ID, "store").is_displayed()
    assert "Round 1 of 5" in driver.find_element(By.ID, "money").text


def test_on_an_upright_phone_the_field_is_only_as_tall_as_it_needs(driver, live, cog):
    match, first, second = watch_a_match_start(driver, live, cog)
    asyncio.run_coroutine_threadsafe(match.message(second, {"done": True}), live.loop).result(10)
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'", timeout=10)
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", UPRIGHT_PHONE)
    try:
        # The cards then sit right under the field instead of leaving a gap above and below it
        browser.wait_for(driver, "document.getElementById('field-box').getBoundingClientRect().width < 400")
        width, height = driver.execute_script(
            "const r = document.getElementById('field-box').getBoundingClientRect(); return [r.width, r.height]"
        )
        assert abs(height - width * 400 / 550) < 2
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
