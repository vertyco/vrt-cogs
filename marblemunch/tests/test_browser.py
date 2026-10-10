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
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    browser.wait_for(driver, "!document.getElementById('open-payouts').hidden")
    driver.find_element(By.ID, "open-payouts").click()
    assert driver.find_element(By.ID, "payouts-rate-label").text == "Credits per marble"
    driver.find_element(By.ID, "payouts-on").click()
    driver.find_element(By.ID, "payouts-plays").send_keys(Keys.BACKSPACE, "5")
    driver.find_element(By.ID, "save-payouts").click()
    browser.wait_for(driver, "document.getElementById('payouts-status').textContent === 'Saved.'")
    saved = run(live, read(live.cog.config.guild_from_id(fakes.GUILD_ID).payouts))
    assert saved == {"on": True, "rate": 100, "cap": 1000, "plays": 5}
    driver.find_element(By.ID, "payouts-plays").send_keys(Keys.BACKSPACE)
    driver.find_element(By.ID, "save-payouts").click()
    browser.wait_for(driver, "document.getElementById('payouts-status').textContent.includes('Cash-ins a day')")
