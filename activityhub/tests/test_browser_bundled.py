import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from activityhub.bundled.games import bundled_games
from activityhub.tests.browser import (
    DISCORD_QUERY,
    TEST_HOST_PAGE,
    LiveHub,
    fresh,
    hub_web_copy,
    start_chrome,
    wait_for,
)
from activityhub.tests.fakes import GUILD_ID, MEMBER_ID, make_hub, register

SCREEN_TEXT = "document.querySelector('.arcade-screen').innerText"
SCREEN_OPEN = "!document.querySelector('.arcade-screen').hidden"


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
    for game in bundled_games(hub.scores):
        register(hub, game)
    server = LiveHub(hub, hub_web_copy(tmp_path, index=TEST_HOST_PAGE))
    server.start()
    driver.set_window_size(900, 800)
    fresh(driver, server)
    yield server
    server.stop()


def open_game(driver, live, key, query=DISCORD_QUERY):
    driver.get(f"{live.url}/{query}")
    assert wait_for(driver, "document.body.dataset.login") == "online"
    driver.execute_script(f"window.testHost.openGame('{key}')")
    wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "document.querySelector('.arcade-screen button.primary')")


def click_screen_button(driver, text):
    """Click a screen's button once it shows. Screens fade in, and a see-through button has no text yet"""

    def find(d):
        buttons = d.find_elements(By.CSS_SELECTOR, ".arcade-screen button")
        return next((button for button in buttons if button.text == text), None)

    WebDriverWait(driver, 5).until(find).click()


def press(driver, *keys):
    actions = ActionChains(driver)
    for key in keys:
        actions.send_keys(key).pause(0.02)
    actions.perform()


def saved_best(live, key):
    return live.hub.config.members.get(GUILD_ID, {}).get(MEMBER_ID, {}).get("best", {}).get(key)


def test_2048_round_is_saved_and_shows_the_board(driver, live):
    open_game(driver, live, "2048")
    wait_for(driver, f"{SCREEN_TEXT}.includes('No score here yet')")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    press(driver, *[Keys.ARROW_LEFT, Keys.ARROW_UP, Keys.ARROW_RIGHT, Keys.ARROW_DOWN] * 6)
    press(driver, Keys.ESCAPE)
    wait_for(driver, f"{SCREEN_TEXT}.includes('Paused')")
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Top scores in Test Server') || {SCREEN_TEXT}.includes('Your best')")
    shown = int(driver.execute_script("return document.querySelector('.arcade-final').dataset.value"))
    assert shown > 0
    assert saved_best(live, "2048")["score"] == shown
    assert "New best!" in driver.execute_script(f"return {SCREEN_TEXT}")
    assert driver.execute_script("return document.querySelector('.arcade-best').innerText") == f"{shown:,}"


def test_snake_crash_ends_the_round_by_itself(driver, live):
    open_game(driver, live, "snake")
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN})")
    # The snake waits for a first direction, then goes straight ahead into the wall: ten steps of 140 ms
    press(driver, Keys.ARROW_RIGHT)
    wait_for(driver, f"{SCREEN_OPEN} && {SCREEN_TEXT}.includes('Game over')", timeout=10)
    wait_for(driver, f"!{SCREEN_TEXT}.includes('Saving')")
    text = driver.execute_script(f"return {SCREEN_TEXT}")
    assert "wasn't saved" not in text and "didn't add up" not in text


def test_snake_turns_are_replayed_by_the_bot(driver, live):
    open_game(driver, live, "snake")
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN})")
    press(driver, Keys.ARROW_UP)
    driver.execute_script("return new Promise((done) => setTimeout(done, 400))")
    press(driver, Keys.ARROW_LEFT)
    wait_for(driver, f"{SCREEN_OPEN} && {SCREEN_TEXT}.includes('Game over')", timeout=15)
    wait_for(driver, f"!{SCREEN_TEXT}.includes('Saving')")
    text = driver.execute_script(f"return {SCREEN_TEXT}")
    assert "wasn't saved" not in text and "didn't add up" not in text


def test_brick_breaker_starts_and_ends(driver, live):
    open_game(driver, live, "brickbreaker")
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN})")
    hint = "document.querySelector('.arcade-hint')"
    wait_for(driver, f"!{hint}.hidden && {hint}.innerText.includes('Space to launch')")
    press(driver, Keys.SPACE)
    # The launch clears the hint
    wait_for(driver, f"{hint}.hidden")
    press(driver, "p")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Paused')")
    click_screen_button(driver, "Resume")
    wait_for(driver, f"!({SCREEN_OPEN})")
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Game over') && !{SCREEN_TEXT}.includes('Saving')")
    assert "didn't add up" not in driver.execute_script(f"return {SCREEN_TEXT}")


def test_preview_outside_discord_plays_without_saving(driver, live):
    driver.get(f"{live.url}/games/2048/")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Preview')")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Game over') && {SCREEN_TEXT}.includes('Preview')")
    assert saved_best(live, "2048") is None


def test_menu_button_saves_the_round_and_leaves(driver, live):
    open_game(driver, live, "2048")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    press(driver, *[Keys.ARROW_LEFT, Keys.ARROW_UP, Keys.ARROW_RIGHT, Keys.ARROW_DOWN] * 4)
    driver.find_element(By.CSS_SELECTOR, ".arcade-back").click()
    driver.switch_to.default_content()
    wait_for(driver, "document.body.dataset.closed === '1'")
    assert saved_best(live, "2048")["score"] > 0


def test_a_save_that_fails_on_the_way_can_be_retried(driver, live, monkeypatch):
    game = live.hub.registry.games["2048"]
    real_finish = game.actions["finish"]
    calls = []

    async def flaky_finish(ctx, data):
        calls.append(data["run"])
        if len(calls) == 1:
            raise RuntimeError("the bot hiccuped before reading the round")
        return await real_finish(ctx, data)

    monkeypatch.setitem(game.actions, "finish", flaky_finish)
    open_game(driver, live, "2048")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    press(driver, *[Keys.ARROW_LEFT, Keys.ARROW_UP, Keys.ARROW_RIGHT, Keys.ARROW_DOWN] * 4)
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Something went wrong')")
    assert saved_best(live, "2048") is None
    click_screen_button(driver, "Retry save")
    wait_for(driver, f"{SCREEN_TEXT}.includes('New best!')")
    assert len(calls) == 2 and calls[0] == calls[1]
    assert saved_best(live, "2048")["score"] > 0


def set_safe_area(driver, **sides):
    """Set the safe area sizes the way Discord's phone app does: on the menu's page, never inside the game frame"""
    driver.switch_to.default_content()
    for side, size in sides.items():
        driver.execute_script(
            f"document.documentElement.style.setProperty('--discord-safe-area-inset-{side}', '{size}')"
        )
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))


def test_the_bar_sits_below_discords_buttons_on_a_phone(driver, live):
    driver.get(f"{live.url}/{DISCORD_QUERY}")
    assert wait_for(driver, "document.body.dataset.login") == "online"
    driver.execute_script("document.documentElement.style.setProperty('--discord-safe-area-inset-top', '40px')")
    driver.execute_script("window.testHost.openGame('snake')")
    wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    back = "document.querySelector('.arcade-back').getBoundingClientRect()"
    assert wait_for(driver, f"document.querySelector('.arcade-back') && {back}.top >= 40")
    # Turning the phone sideways moves Discord's buttons while the game is open
    set_safe_area(driver, top="0px", right="30px")
    assert wait_for(driver, f"{back}.top < 40")
    bar = "getComputedStyle(document.querySelector('.arcade-bar'))"
    assert driver.execute_script(f"return {bar}.paddingRight") == "38px"
