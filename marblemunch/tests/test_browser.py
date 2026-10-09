import asyncio

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from marblemunch.main import MarbleMunch

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="marblemunch"]'


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
def live(tmp_path, driver):
    hub = fakes.make_hub()
    cog = MarbleMunch(bot=None)
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
