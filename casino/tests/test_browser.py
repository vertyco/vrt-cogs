"""The page in headless Chrome against the real hub and the real cog, with a stand-in bank and a seeded deck"""

import asyncio
import random

import pytest
from piccolo.engine.sqlite import SQLiteEngine
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

from casino.common.money import Money
from casino.db.tables import TABLES
from casino.main import Casino
from casino.tests.fakes import FakeBank

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="casino"]'
UPRIGHT_PHONE = {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}
# The move each game's test presses whenever the bot asks: the one that ends the round soonest
QUICK_MOVE = {"blackjack": "stay", "war": "surrender", "double": "cashout", "craps": "roll"}


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


def on_loop(live, coro):
    return asyncio.run_coroutine_threadsafe(coro, live.loop).result(15)


async def make_tables():
    for table in TABLES:
        await table.create_table(if_not_exists=True)


@pytest.fixture
def live(tmp_path, driver):
    hub = fakes.make_hub()
    hub.bot.get_guild(fakes.GUILD_ID).roles = []
    cog = Casino(hub.bot)
    engine = SQLiteEngine(path=str(tmp_path / "casino.sqlite"))
    for table in TABLES:
        table._meta.db = engine
    cog.bank = FakeBank(start=1000)
    cog.money = Money(cog.store, cog.bank)
    cog.rng = random.Random(7)
    assert fakes.register(hub, cog) is not None
    server = browser.LiveHub(hub, browser.hub_web_copy(tmp_path))
    server.start()
    on_loop(server, make_tables())
    cog.ready.set()
    server.cog = cog
    driver.set_window_size(1280, 800)
    browser.fresh(driver, server)
    yield server
    on_loop(server, cog.cog_unload())
    server.stop()


def open_casino(driver, live, balance="1,000"):
    driver.get(f"{live.url}/{browser.DISCORD_QUERY}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(driver, f"document.getElementById('balance').textContent === '{balance}'", timeout=20)


def walk_up(driver, game):
    driver.find_element(By.CSS_SELECTOR, f'.station[data-key="{game}"]').click()
    browser.wait_for(driver, "!document.getElementById('table').hidden")
    browser.wait_for(driver, "document.getElementById('status-text').textContent !== 'Walking up to the table...'")


def problems(driver):
    return [line for line in browser.console_lines(driver) if "Uncaught" in line or "Casino:" in line]


def test_the_lobby_shows_every_table_and_the_casino(driver, live):
    open_casino(driver, live)
    assert len(driver.find_elements(By.CSS_SELECTOR, "#floor .station")) == 9
    assert driver.find_element(By.ID, "casino-name").text == "Redjumpman's Casino"
    assert driver.find_element(By.ID, "tier").text == "Basic"
    assert driver.find_element(By.ID, "open-settings").get_attribute("hidden") is not None
    assert not problems(driver)


@pytest.mark.parametrize("game", ["allin", "blackjack", "coin", "craps", "cups", "dice", "hilo", "war", "double"])
def test_every_game_plays_a_round(driver, live, game):
    open_casino(driver, live)
    walk_up(driver, game)
    if game == "blackjack":
        driver.find_element(By.ID, "sit").click()
        browser.wait_for(driver, "!document.getElementById('stand').hidden")
    choice = driver.find_elements(By.CSS_SELECTOR, "#choices button")
    if choice:
        choice[0].click()
    browser.wait_for(driver, "!document.getElementById('place').disabled && !document.getElementById('place').hidden")
    driver.find_element(By.ID, "place").click()
    # Press the quickest move whenever the bot asks, until the result shows
    for _ in range(120):
        if driver.execute_script("return !document.getElementById('result').hidden"):
            break
        move = QUICK_MOVE.get(game)
        buttons = driver.find_elements(By.CSS_SELECTOR, f'#moves [data-move="{move}"]') if move else []
        if buttons and buttons[0].is_displayed():
            buttons[0].click()
        driver.execute_script("return new Promise((resolve) => setTimeout(resolve, 250))")
    big = driver.find_element(By.ID, "result-big").text
    assert big.startswith(("You win", "House wins", "No luck", "Bust", "Push", "Surrendered")), big
    assert not problems(driver)


def test_a_called_coin_flip_pays_the_multiplied_bet(driver, live):
    live.cog.rng = random.Random(1)
    side = random.Random(1).choice(("heads", "tails"))
    on_loop(live, live.cog.store.save_game(fakes.GUILD_ID, "coin", cooldown=60))
    open_casino(driver, live)
    walk_up(driver, "coin")
    driver.find_element(By.CSS_SELECTOR, f'#choices [data-choice="{side}"]').click()
    driver.find_element(By.ID, "place").click()
    browser.wait_for(driver, "!document.getElementById('result').hidden", timeout=10)
    assert driver.find_element(By.ID, "result-big").text == "You win 15"
    browser.wait_for(driver, "document.getElementById('balance').textContent === '1,005'")
    # Once the round ends, the cooldown greys the tray out and says why
    browser.wait_for(driver, "document.getElementById('why').textContent.includes('Coin is ready again in')")


def test_only_admins_get_the_settings_and_their_changes_reach_the_tables(driver, live):
    live.user_id = fakes.MANAGER_ID
    open_casino(driver, live)
    driver.find_element(By.ID, "open-settings").click()
    browser.wait_for(driver, "document.querySelectorAll('#panel-tabs button').length === 5")
    driver.find_element(By.XPATH, "//nav[@id='panel-tabs']/button[text()='Games']").click()
    row = driver.find_element(By.XPATH, "//table[contains(@class,'grid')]//tr[td[text()='Coin']]")
    maximum = row.find_elements(By.CSS_SELECTOR, "input[type=number]")[2]
    maximum.clear()
    maximum.send_keys("20")
    row.find_element(By.XPATH, ".//button[text()='Save']").click()
    browser.wait_for(driver, "document.getElementById('toast').textContent === 'Saved.'")
    game = on_loop(live, live.cog.store.game(fakes.GUILD_ID, "coin"))
    assert game.max_bet == 20
    assert not problems(driver)


def test_house_rules_stats_and_memberships_open_for_everyone(driver, live):
    open_casino(driver, live)
    driver.find_element(By.ID, "open-rules").click()
    browser.wait_for(driver, "document.getElementById('panel-body').textContent.includes('How to play')")
    assert "Redjumpman's Casino" in driver.find_element(By.ID, "panel-body").text
    driver.find_element(By.ID, "panel-close").click()
    driver.find_element(By.ID, "open-stats").click()
    browser.wait_for(driver, "document.getElementById('panel-body').textContent.includes('pushes or surrenders')")
    driver.find_element(By.ID, "panel-close").click()
    driver.find_element(By.ID, "open-tiers").click()
    browser.wait_for(driver, "document.getElementById('panel-body').textContent.includes('Everyone plays as Basic')")
    assert not problems(driver)


def test_on_an_upright_phone_the_floor_pans_and_the_dock_sits_under_the_scene(driver, live):
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", UPRIGHT_PHONE)
    try:
        open_casino(driver, live)
        browser.wait_for(driver, "document.getElementById('lobby').scrollLeft > 0")
        walk_up(driver, "dice")
        scene = driver.execute_script("return document.getElementById('scene').getBoundingClientRect().bottom")
        dock = driver.execute_script("return document.querySelector('.dock').getBoundingClientRect().top")
        assert dock >= scene - 1
        assert driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth")
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_a_player_short_of_the_minimum_bet_is_told_why(driver, live):
    live.cog.bank.balances[fakes.MEMBER_ID] = 5
    open_casino(driver, live, balance="5")
    walk_up(driver, "dice")
    browser.wait_for(driver, "!document.getElementById('why').hidden")
    assert driver.find_element(By.ID, "why").text == "You don't have enough credits for the minimum bet."
    assert not driver.find_element(By.ID, "place").is_displayed()


def test_the_membership_form_keeps_a_deleted_role_and_warns_about_open_memberships(driver, live):
    # The role 4242 was deleted from the server after the membership was made
    live.hub.bot.get_guild(fakes.GUILD_ID).get_role = lambda role_id: None
    gold = {"name": "Gold", "color": "yellow", "access": 1, "req_role_id": 4242}
    on_loop(live, live.cog.store.save_membership(fakes.GUILD_ID, gold))
    live.user_id = fakes.MANAGER_ID
    open_casino(driver, live)
    driver.find_element(By.ID, "open-settings").click()
    browser.wait_for(driver, "document.querySelectorAll('#panel-tabs button').length === 5")
    driver.find_element(By.XPATH, "//nav[@id='panel-tabs']/button[text()='Memberships']").click()
    driver.find_element(By.XPATH, "//*[@id='panel-body']//button[text()='Edit']").click()
    role = driver.find_element(By.XPATH, "//label[contains(., 'Needs role')]/select")
    assert role.get_attribute("value") == "4242" and "Deleted role" in role.text
    assert not driver.find_element(By.CSS_SELECTOR, "#panel-body p.warn").is_displayed()
    driver.find_element(By.XPATH, "//*[@id='panel-body']//button[text()='Save']").click()
    browser.wait_for(driver, "document.getElementById('toast').textContent === 'Saved.'")
    assert on_loop(live, live.cog.store.membership_named(fakes.GUILD_ID, "Gold")).req_role_id == 4242
    driver.find_element(By.XPATH, "//*[@id='panel-body']//button[text()='New membership']").click()
    warning = driver.find_element(By.CSS_SELECTOR, "#panel-body p.warn")
    assert warning.is_displayed() and "every player gets it automatically" in warning.text
    assert not problems(driver)
