import asyncio
import time

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from ageofwar.main import AgeOfWar

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="ageofwar"]'
UPRIGHT_PHONE = {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}
HUD_BUTTONS = "#hud .row:not([hidden]) button.art"


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
    return AgeOfWar(bot=None)


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


def open_game(driver, live, query=browser.DISCORD_QUERY):
    driver.get(f"{live.url}/{query}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))


def start_against_the_computer(driver, live):
    open_game(driver, live)
    browser.wait_for(driver, "document.querySelectorAll('#seats li').length === 2", timeout=20)
    driver.find_element(By.CSS_SELECTOR, "#seats li:first-child button").click()
    browser.wait_for(driver, "!document.getElementById('start').hidden")
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'", timeout=10)


def press(driver, index):
    driver.execute_script(f"document.querySelectorAll('{HUD_BUTTONS}')[{index}].click()")


def test_a_bought_unit_trains_and_the_cash_drops(driver, live):
    start_against_the_computer(driver, live)
    browser.wait_for(driver, "document.querySelector('#hud .shadow.cash').textContent === '175'")
    press(driver, 0)
    press(driver, 0)
    browser.wait_for(driver, "document.querySelector('#hud .shadow.cash').textContent === '160'", timeout=5)
    browser.wait_for(driver, "document.querySelector('#hud .training').textContent.includes('Club man')", timeout=5)
    driver.switch_to.default_content()
    assert browser.wait_for(driver, "/\\d+ TPS$/.test(document.querySelector('.fps').textContent)", timeout=5)
    problems = [line for line in browser.console_lines(driver) if "Uncaught" in line or "Age of War" in line]
    assert not problems, problems


def first_spot(driver):
    """The canvas, and where on it the left base's first turret spot button is, from the canvas's center. The view
    starts on the left base, and the field sits on the canvas's bottom edge"""
    canvas = driver.find_element(By.CSS_SELECTOR, "#field canvas")
    width, height = driver.execute_script(
        "const r = arguments[0].getBoundingClientRect(); return [r.width, r.height];", canvas
    )
    scale = min(width / 650, height / 390)
    x = 54 * scale
    y = height - 450 * scale + (425 - 78.75) * scale
    return canvas, x - width / 2, y - height / 2


def cash_is(amount: int) -> str:
    return f"document.querySelector('#hud .shadow.cash').textContent === '{amount}'"


def test_a_turret_picked_in_the_menu_goes_on_the_spot_clicked(driver, live):
    start_against_the_computer(driver, live)
    browser.wait_for(driver, cash_is(175))
    # Build turrets, then the first age's first turret: the Rock slingshot, for 100
    press(driver, 1)
    press(driver, 0)
    canvas, x, y = first_spot(driver)
    # A real mouse, so the turret the original shows under the pointer is there too
    ActionChains(driver).move_to_element_with_offset(canvas, x, y).pause(0.3).click().perform()
    browser.wait_for(driver, cash_is(75), timeout=5)


def test_dragging_the_field_from_a_spot_button_does_not_press_it(driver, live):
    start_against_the_computer(driver, live)
    browser.wait_for(driver, cash_is(175))
    press(driver, 1)
    press(driver, 0)
    canvas, x, y = first_spot(driver)
    ActionChains(driver).move_to_element_with_offset(canvas, x, y).pause(0.3).click().perform()
    browser.wait_for(driver, cash_is(75), timeout=5)
    # Sell a turret: the spot's sell button sits where its build button was
    press(driver, 2)
    drag = ActionChains(driver).move_to_element_with_offset(canvas, x, y).pause(0.3).click_and_hold()
    drag.move_by_offset(-20, 0).move_by_offset(-20, 0).pause(0.3).release().perform()
    time.sleep(0.5)
    assert driver.execute_script(f"return {cash_is(75)}")
    # The view slid back to the base, and a plain press still sells, for half the price
    ActionChains(driver).move_to_element_with_offset(canvas, x, y).pause(0.3).click().perform()
    browser.wait_for(driver, cash_is(125), timeout=5)


def test_giving_up_shows_the_originals_defeat_screen(driver, live):
    start_against_the_computer(driver, live)
    driver.find_element(By.ID, "give-up").click()
    driver.find_element(By.ID, "quit-yes").click()
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'results'", timeout=5)
    assert driver.find_element(By.ID, "results-title").text == "Defeat!"
    assert driver.find_element(By.ID, "continue").is_displayed()


def test_pausing_stops_the_battle(driver, live, cog):
    start_against_the_computer(driver, live)
    driver.find_element(By.ID, "pause").click()
    browser.wait_for(driver, "!document.getElementById('overlay').hidden", timeout=5)
    match = next(iter(cog.matches.values()))
    frame = match.battle.frame
    time.sleep(0.5)
    assert match.paused and match.battle.frame == frame
    driver.find_element(By.ID, "resume").click()
    browser.wait_for(driver, "document.getElementById('overlay').hidden", timeout=5)


def test_on_an_upright_phone_the_menus_fit_the_width(driver, live):
    start_against_the_computer(driver, live)
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", UPRIGHT_PHONE)
    try:
        browser.wait_for(driver, "document.getElementById('app').dataset.layout === 'tall'")
        edges = driver.execute_script(
            "return [...document.querySelectorAll('#hud .strip')].map((s) => {"
            "const r = s.getBoundingClientRect(); return [r.left, r.right, r.bottom]; })"
        )
        for left, right, bottom in edges:
            assert left >= -1 and right <= 391 and bottom <= 845
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_the_browser_preview_plays_a_recorded_battle(driver, live):
    open_game(driver, live, query="")
    browser.wait_for(driver, "!document.getElementById('toast').hidden", timeout=10)
    assert "Preview" in driver.find_element(By.ID, "toast").text
    assert driver.find_element(By.ID, "setup").get_attribute("hidden") is not None
    problems = [line for line in browser.console_lines(driver) if "Uncaught" in line or "Age of War" in line]
    assert not problems, problems
