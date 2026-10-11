import asyncio
import re

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from boulderbash.common.rules import MAX_COLORS, board_origin, tile_size
from boulderbash.main import BoulderBash

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="boulderbash"]'
KEY = (fakes.GUILD_ID, fakes.MEMBER_ID)


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
    cog = BoulderBash(bot=hub.bot)
    cog.payouts.bank = fakes.FakeBank()
    assert fakes.register(hub, cog) is not None
    server = browser.LiveHub(hub, browser.hub_web_copy(tmp_path))
    server.start()
    driver.set_window_size(1280, 800)
    browser.fresh(driver, server)
    server.cog = cog
    yield server
    # Stopped on the server's own event loop, so no game loop is left running when it closes
    asyncio.run_coroutine_threadsafe(cog.cog_unload(), server.loop).result(5)
    server.stop()


def run(live, coro):
    """Run a coroutine on the server's own event loop, where the cog's Config is used"""
    return asyncio.run_coroutine_threadsafe(coro, live.loop).result(5)


async def read(value):
    # A Config value's read is awaitable but not a coroutine, which run_coroutine_threadsafe needs
    return await value()


def open_game(driver, live):
    driver.get(f"{live.url}/{browser.DISCORD_QUERY}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(driver, "!!document.querySelector('#scene canvas')", timeout=20)


def start_mode(driver, mode_name):
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'modes'")
    driver.find_element(By.XPATH, f"//button[@data-mode][text()='{mode_name}']").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'play'", timeout=10)


def pause(driver, ms: int) -> None:
    driver.execute_script(f"return new Promise((done) => setTimeout(done, {ms}))")


def wait_idle(live, driver):
    game = live.cog.games[KEY]
    for _ in range(100):
        # A little past the bot's idle time, since the page plays the same motion a moment later
        if game.idle_at[0] + 150 <= live.cog.clock():
            return game
        pause(driver, 100)
    raise AssertionError("the board never went idle")


def find_pair(board) -> tuple[int, int]:
    """A plain block with a plain neighbor of the same color, so tapping it picks a group"""
    for row in range(board.rows):
        for col in range(board.cols - 1):
            a, b = board.grid[row][col], board.grid[row][col + 1]
            if a and b and not a.special and not b.special and a.color == b.color and a.color < MAX_COLORS:
                return row, col
    raise AssertionError("no pair on the board")


def tap_cell(driver, mode, level, row, col):
    """Click a cell's middle, working out where the page drew it from the stage's transform"""
    transform = driver.execute_script("return document.getElementById('stage').style.transform")
    x, y, scale = (float(n) for n in re.findall(r"[-0-9.]+", transform)[:3])
    left, top = board_origin(mode, level, 0)
    tile_w, tile_h = tile_size(mode, level)
    sx = x + (left + col * tile_w + tile_w / 2) * scale
    sy = y + (top + row * tile_h + tile_h / 2) * scale
    canvas = driver.find_element(By.CSS_SELECTOR, "#scene canvas")
    offset_x = int(sx - canvas.size["width"] / 2)
    offset_y = int(sy - canvas.size["height"] / 2)
    ActionChains(driver).move_to_element_with_offset(canvas, offset_x, offset_y).click().perform()


def smash_a_group(live, driver):
    game = wait_idle(live, driver)
    board = game.boards[0]
    row, col = find_pair(board)
    tap_cell(driver, game.mode, board.level, row, col)
    for _ in range(50):
        if board.selection:
            break
        pause(driver, 50)
    assert (row, col) in board.selection
    tap_cell(driver, game.mode, board.level, row, col)
    browser.wait_for(driver, "document.getElementById('score').textContent !== '0'", timeout=5)
    return game


def problems(driver):
    return [line for line in browser.console_lines(driver) if "Uncaught" in line or "Boulder Bash" in line]


def test_the_title_and_how_to_play_work(driver, live):
    open_game(driver, live)
    assert driver.find_element(By.ID, "start").is_displayed()
    assert not driver.find_element(By.ID, "open-payouts").is_displayed()
    driver.find_element(By.ID, "how").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'help'")
    for page in (2, 3, 4, 1):
        driver.find_element(By.ID, "help-more").click()
        assert driver.find_element(By.CSS_SELECTOR, f'.help-page[data-page="{page}"]').is_displayed()
    driver.find_element(By.ID, "help-back").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'title'")
    assert not problems(driver)


def test_a_normal_game_selects_then_smashes(driver, live):
    open_game(driver, live)
    start_mode(driver, "Normal")
    game = smash_a_group(live, driver)
    assert game.score > 0
    assert driver.find_element(By.ID, "score").text == str(game.score)
    assert "of 100" in driver.find_element(By.ID, "next-0").text
    assert not problems(driver)


def test_an_extreme_x2_game_draws_two_boards(driver, live):
    open_game(driver, live)
    start_mode(driver, "Extreme x2")
    game = wait_idle(live, driver)
    assert len(game.boards) == 2
    assert "of 75" in driver.find_element(By.ID, "next-1").text
    driver.find_element(By.ID, "end").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'over'", timeout=10)
    assert not problems(driver)


def test_the_finished_game_cashes_in_from_the_game_over_tablet(driver, live):
    on = {"on": True, "rate": 1, "cap": 1000, "plays": 3}
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set(on))
    run(live, live.cog.config.member_from_ids(fakes.GUILD_ID, fakes.MEMBER_ID).cashed.set({}))
    open_game(driver, live)
    start_mode(driver, "Normal")
    game = smash_a_group(live, driver)
    driver.find_element(By.ID, "end").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'over'", timeout=10)
    browser.wait_for(driver, "!document.getElementById('cashin').hidden", timeout=10)
    assert f"Worth {game.score} credits" in driver.find_element(By.ID, "cashin-text").text
    assert "New best! #1 on this server" in driver.find_element(By.ID, "standing").text
    driver.find_element(By.ID, "cashin-button").click()
    browser.wait_for(driver, "document.getElementById('cashin').hidden")
    assert f"+{game.score} credits" in driver.find_element(By.ID, "toast").text
    assert live.cog.payouts.bank.balances[fakes.MEMBER_ID] == game.score
    driver.find_element(By.ID, "restart").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'title'")


def test_a_server_admin_sets_payouts_from_the_title(driver, live):
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set({}))
    # Saved data lasts across tests, and an earlier one may have cashed in today
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).tally.set({}))
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    browser.wait_for(driver, "!document.getElementById('open-payouts').hidden")
    driver.find_element(By.ID, "open-payouts").click()
    assert driver.find_element(By.ID, "payouts-rate-label").text == "Credits per point"
    assert "at most 3,000 credits a day" in driver.find_element(By.ID, "payouts-day").text
    assert "Today: 0 credits paid to 0 players" in driver.find_element(By.ID, "payouts-today").text
    driver.find_element(By.ID, "payouts-on").click()
    driver.find_element(By.ID, "payouts-plays").send_keys(Keys.BACKSPACE, "5")
    driver.find_element(By.ID, "save-payouts").click()
    browser.wait_for(driver, "document.getElementById('payouts-status').textContent === 'Saved.'")
    saved = run(live, read(live.cog.config.guild_from_id(fakes.GUILD_ID).payouts))
    assert saved == {"on": True, "rate": 0.2, "cap": 1000, "plays": 5}
    driver.find_element(By.ID, "payouts-plays").send_keys(Keys.BACKSPACE)
    driver.find_element(By.ID, "save-payouts").click()
    browser.wait_for(driver, "document.getElementById('payouts-status').textContent.includes('Cash-ins a day')")


def test_the_browser_preview_shows_the_title_and_says_to_open_discord(driver, live):
    driver.get(f"{live.url}/games/boulderbash/")
    browser.wait_for(driver, "!!document.querySelector('#scene canvas')", timeout=20)
    driver.find_element(By.ID, "open-scores").click()
    browser.wait_for(driver, "document.getElementById('you').textContent.includes('Open Boulder Bash in Discord')")
    driver.find_element(By.ID, "close-scores").click()
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "!document.getElementById('message').hidden")
    assert "Open Boulder Bash in Discord to play" in driver.find_element(By.ID, "message-text").text
    assert driver.execute_script("return document.getElementById('stage').dataset.screen") == "title"
    assert not problems(driver)
