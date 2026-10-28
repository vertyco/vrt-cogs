import asyncio
import itertools
import time

import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from activityhub.bundled import snake
from activityhub.bundled.games import bundled_games
from activityhub.tests.browser import (
    DISCORD_QUERY,
    TEST_HOST_PAGE,
    WAITS_FOR_DOUBLE_TAP,
    LiveHub,
    fresh,
    hub_web_copy,
    start_chrome,
    wait_for,
)
from activityhub.tests.fakes import (
    ADMIN_ID,
    GUILD_ID,
    GUILD_OWNER_ID,
    MANAGER_ID,
    MEMBER_ID,
    OWNER_ID,
    make_hub,
    register,
)

# A picture that loads with no network, so a test never sees an avatar fail to load by chance
OFFLINE_AVATAR = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8'/%3E"
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
    for user in hub.bot.users.values():
        user.display_avatar.url = OFFLINE_AVATAR
    for game in bundled_games(hub.scores, hub.payouts):
        register(hub, game, included=True)
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


def test_a_finished_round_cashes_in_once(driver, live):
    live.hub.config.guild_from_id(GUILD_ID).data["payouts"] = {"2048": {"on": True, "rate": 1, "cap": 50, "plays": 3}}
    open_game(driver, live, "2048")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    press(driver, *[Keys.ARROW_LEFT, Keys.ARROW_UP, Keys.ARROW_RIGHT, Keys.ARROW_DOWN] * 6)
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('3 of 3 cash-ins left today')")
    worth = min(int(driver.execute_script("return document.querySelector('.arcade-final').dataset.value")), 50)
    click_screen_button(driver, f"Cash in {worth}")
    wait_for(driver, "document.querySelector('.arcade-paid')")
    assert driver.execute_script("return document.querySelector('.arcade-paid').innerText") == f"+{worth} credits"
    assert "2 cash-ins left" in driver.execute_script(f"return {SCREEN_TEXT}")
    assert live.hub.payouts.bank.balances[MEMBER_ID] == worth


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


# The cell just ahead of the snake as a round starts, and a corner well away from its path
APPLE_AHEAD = (snake.START[0][0] + 1, snake.START[0][1])
APPLE_FAR = (0, 0)
# How long the snake runs before the pause: past its first step (140 ms), well short of the wall (about 1.2 s)
SNAKE_RUN_MS = 400
# Records each request the game's frame sends, on the menu page, which outlives the frame
SPY_ON_FETCH = """
const real = window.fetch;
window.parent.fetchSpy = [];
window.fetch = (url, init = {}) => {
  window.parent.fetchSpy.push({
    url: String(url),
    keepalive: init.keepalive === true,
    auth: Boolean(init.headers && init.headers.Authorization),
  });
  return real(url, init);
};
"""
# Makes a Snake round's proof measure 64 KB, as a very long round's turns can. The finish's own body, which has the
# round's id, is still made for real
BIG_PROOF = """
const real = JSON.stringify;
JSON.stringify = function (value, ...rest) {
  if (value && typeof value === 'object' && 'ticks' in value && !('run' in value)) {
    return 'x'.repeat(64 * 1024);
  }
  return real.call(this, value, ...rest);
};
"""


def seed_snake(live, monkeypatch, apple):
    """Every Snake round starts with its first apple on this cell"""
    seed = next(seed for seed in itertools.count() if snake.SnakeGame(seed).food == apple)

    async def seeded_start(ctx, data):
        return {"seed": seed, "run": live.hub.scores.open_run(ctx, "snake", seed)}

    monkeypatch.setitem(live.hub.registry.games["snake"].actions, "start", seeded_start)


def record_finishes(live, monkeypatch, key, delay=0) -> list:
    """Every finish the game's page sends, as the bot gets it. With a delay, each takes that many seconds to answer"""
    game = live.hub.registry.games[key]
    real = game.actions["finish"]
    sent = []

    async def recorded(ctx, data):
        sent.append(data)
        await asyncio.sleep(delay)
        return await real(ctx, data)

    monkeypatch.setitem(game.actions, "finish", recorded)
    return sent


def finishes_sent(driver):
    """(keepalive, has a login) for each finish the game's frame sent, read from the menu page"""
    driver.switch_to.default_content()
    calls = driver.execute_script("return window.fetchSpy")
    return [(call["keepalive"], call["auth"]) for call in calls if call["url"].endswith("/api/finish")]


def snake_move_then_pause(driver):
    """Start a round heading right, and pause it SNAKE_RUN_MS later. Returns the score"""
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN})")
    # Both keys in one chain, so the browser gets them that far apart however slowly the test itself runs
    ActionChains(driver).send_keys(Keys.ARROW_RIGHT).pause(SNAKE_RUN_MS / 1000).send_keys(Keys.ESCAPE).perform()
    wait_for(driver, f"{SCREEN_TEXT}.includes('Paused')")
    return driver.execute_script(f"return {SCORE}")


def score_then_pause(driver, live, monkeypatch, key):
    """Score in a round of the open game, then pause it. Returns the score"""
    if key == "snake":
        seed_snake(live, monkeypatch, APPLE_AHEAD)
        return snake_move_then_pause(driver)
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    play_until(driver, f"{SCORE} > 0")
    press(driver, Keys.ESCAPE)
    wait_for(driver, f"{SCREEN_TEXT}.includes('Paused')")
    return driver.execute_script(f"return {SCORE}")


def leave_game(driver, live, how, key):
    """Take the player out of the open game without the arcade's Menu button"""
    driver.switch_to.default_content()
    if how == "join":
        # Join opens the friend's game in place of this one, which removes this game's frame
        other = "2048" if key == "snake" else "snake"
        driver.execute_script(f"window.testHost.openGame('{other}')")
    else:
        # Closing the Activity unloads the menu page, and the game's frame with it
        fresh(driver, live)


@pytest.mark.parametrize(("key", "how"), [("snake", "join"), ("snake", "close"), ("2048", "join")])
def test_leaving_mid_round_saves_the_score_so_far(driver, live, monkeypatch, key, how):
    sent = record_finishes(live, monkeypatch, key)
    open_game(driver, live, key)
    driver.execute_script(SPY_ON_FETCH)
    score = score_then_pause(driver, live, monkeypatch, key)
    assert score > 0
    leave_game(driver, live, how, key)
    WebDriverWait(driver, 5).until(lambda d: saved_best(live, key))
    assert saved_best(live, key)["score"] == score
    assert len(sent) == 1
    if how == "join":
        # On a real network only a keepalive request gets out of a removed frame. Closing replaced the page that
        # held this record
        assert finishes_sent(driver) == [(True, True)]


def test_leaving_a_round_with_no_score_sends_nothing(driver, live, monkeypatch):
    seed_snake(live, monkeypatch, APPLE_FAR)
    sent = record_finishes(live, monkeypatch, "snake")
    open_game(driver, live, "snake")
    driver.execute_script(SPY_ON_FETCH)
    assert snake_move_then_pause(driver) == 0
    leave_game(driver, live, "join", "snake")
    assert finishes_sent(driver) == []
    wait_ms(driver, 500)
    assert sent == []


def test_a_round_saving_as_the_player_leaves_is_sent_once_and_kept(driver, live, monkeypatch):
    seed_snake(live, monkeypatch, APPLE_AHEAD)
    sent = record_finishes(live, monkeypatch, "snake", delay=1)
    open_game(driver, live, "snake")
    driver.execute_script(SPY_ON_FETCH)
    score = snake_move_then_pause(driver)
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Saving')")
    leave_game(driver, live, "join", "snake")
    WebDriverWait(driver, 5).until(lambda d: saved_best(live, "snake"))
    assert saved_best(live, "snake")["score"] == score
    assert len(sent) == 1
    # The save already on its way is a keepalive request too, so the Join can't cut it off
    assert finishes_sent(driver) == [(True, True)]


def test_a_proof_too_big_for_keepalive_goes_as_a_normal_request(driver, live, monkeypatch):
    seed_snake(live, monkeypatch, APPLE_AHEAD)
    open_game(driver, live, "snake")
    driver.execute_script(SPY_ON_FETCH)
    driver.execute_script(BIG_PROOF)
    score = snake_move_then_pause(driver)
    assert score > 0
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('New best!')")
    assert saved_best(live, "snake")["score"] == score
    assert finishes_sent(driver) == [(False, True)]


def test_the_menu_button_saves_a_round_once(driver, live, monkeypatch):
    seed_snake(live, monkeypatch, APPLE_AHEAD)
    sent = record_finishes(live, monkeypatch, "snake")
    open_game(driver, live, "snake")
    driver.execute_script(SPY_ON_FETCH)
    score = snake_move_then_pause(driver)
    assert score > 0
    driver.find_element(By.CSS_SELECTOR, ".arcade-back").click()
    driver.switch_to.default_content()
    wait_for(driver, "document.body.dataset.closed === '1'")
    # Closing the frame after the Menu button's save must not send the round again
    assert finishes_sent(driver) == [(True, True)]
    assert len(sent) == 1
    assert saved_best(live, "snake")["score"] == score


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


ARROWS = [Keys.ARROW_LEFT, Keys.ARROW_UP, Keys.ARROW_RIGHT, Keys.ARROW_DOWN]
SCORE = "Number(document.querySelector('.arcade-score').textContent.replace(/,/g, ''))"
# Records every passing note as it appears, with its width, so a test needn't catch the 1.6 s it stays up
RECORD_NOTES = """
window.notes = [];
const box = document.querySelector('.arcade-pass');
new MutationObserver(() => {
  if (!box.hidden && box.textContent) window.notes.push({ text: box.textContent, width: box.offsetWidth });
}).observe(box, { childList: true, attributes: true, attributeFilter: ['hidden'] });
"""


def me(live):
    window = live.server.presence.windows.get("i-1")
    return window.people.get(MEMBER_ID) if window else None


def size_frame(driver, width, height=700):
    """The test host page has no styles, so its game frame is the browser's small default, a phone's size"""
    driver.switch_to.default_content()
    driver.execute_script(
        f"document.getElementById('game-frame').style.cssText = 'width: {width}px; height: {height}px'"
    )
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))


def in_host(driver, script):
    """Run a script on the menu page around the game's frame, and come back into the frame"""
    driver.switch_to.default_content()
    try:
        return driver.execute_script(script)
    finally:
        driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))


def play_until(driver, condition, batches=60):
    """Make moves in 2048 until the JavaScript condition holds"""
    for _ in range(batches):
        if driver.execute_script(f"return {condition}"):
            return
        press(driver, *ARROWS * 2)
    raise AssertionError(f"Still not true after {batches} batches of moves: {condition}")


def start_round(driver):
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    driver.execute_script(RECORD_NOTES)


def strip_rows(driver):
    return driver.execute_script("return [...document.querySelectorAll('.arcade-live li')].map((li) => li.className)")


def test_the_arcade_reports_what_the_player_is_doing(driver, live):
    open_game(driver, live, "2048")
    driver.switch_to.default_content()
    wait_for(driver, "window.testHost.presence.people.length === 1")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    assert driver.execute_script("return document.querySelector('.arcade-bar .hub-people') !== null")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    # A board waiting for its first move isn't busy yet, so a friend's Join doesn't ask before taking the player
    WebDriverWait(driver, 5).until(lambda d: me(live) and me(live).status == "Playing · 0")
    assert me(live).data == {"state": "playing", "score": 0}
    time.sleep(0.6)
    assert me(live).busy is False
    # The first move gets the round going, and busy turns on with it
    press(driver, *ARROWS)
    WebDriverWait(driver, 5).until(lambda d: me(live).busy)
    assert me(live).status.startswith("Playing · ")


def test_the_status_follows_the_round(driver, live):
    open_game(driver, live, "2048")
    WebDriverWait(driver, 5).until(lambda d: me(live) and me(live).status == "Getting ready" and not me(live).busy)
    assert me(live).data == {"state": "idle"}
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    play_until(driver, f"{SCORE} >= 4")
    press(driver, Keys.ESCAPE)
    WebDriverWait(driver, 5).until(lambda d: me(live).status.startswith("Paused · ") and me(live).busy)
    assert me(live).data["state"] == "paused" and me(live).data["score"] >= 4
    click_screen_button(driver, "End round")
    WebDriverWait(driver, 5).until(lambda d: me(live).status.startswith("Scored ") and not me(live).busy)
    assert me(live).data["state"] == "over" and me(live).data["score"] >= 4


def test_a_round_that_fails_to_start_puts_the_status_back(driver, live, monkeypatch):
    game = live.hub.registry.games["2048"]
    real_start = game.actions["start"]
    calls = []

    async def flaky_start(ctx, data):
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError("the bot hiccuped before starting the round")
        return await real_start(ctx, data)

    monkeypatch.setitem(game.actions, "start", flaky_start)
    open_game(driver, live, "2048")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    play_until(driver, f"{SCORE} >= 4")
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    WebDriverWait(driver, 5).until(lambda d: me(live).status.startswith("Scored "))
    wait_for(driver, f"!{SCREEN_TEXT}.includes('Saving')")
    click_screen_button(driver, "Play again")
    wait_for(driver, f'{SCREEN_TEXT}.includes("Couldn\'t start a round")')
    WebDriverWait(driver, 5).until(lambda d: me(live).status == "Getting ready" and not me(live).busy)


def test_strip_hidden_when_alone(driver, live):
    open_game(driver, live, "snake")
    assert driver.execute_script("return document.querySelector('.arcade-live').hidden") is True


def test_the_strip_ranks_people_here_and_notes_a_pass(driver, live):
    open_game(driver, live, "2048")
    size_frame(driver, 900)
    live.add_person(MANAGER_ID, where="2048", status="Scored 1", data={"state": "over", "score": 1})
    wait_for(driver, "!document.querySelector('.arcade-live').hidden")
    assert "Manager" in driver.find_element(By.CSS_SELECTOR, ".arcade-live").text
    # A round starts at 0, below the rival's 1, so the first points pass them
    start_round(driver)
    play_until(driver, "window.notes.length > 0")
    assert driver.execute_script("return window.notes[0].text") == "You passed Manager!"
    driver.execute_script("document.querySelector('.arcade-bar button.arcade-icon:last-child').click()")
    click_screen_button(driver, "End round")
    assert "1st of 2 here right now" in wait_for(driver, SCREEN_TEXT)


def test_the_strip_shows_three_on_a_phone_and_five_on_a_desktop(driver, live):
    open_game(driver, live, "snake")
    others = [MANAGER_ID, ADMIN_ID, OWNER_ID, GUILD_OWNER_ID]
    for i, user_id in enumerate(others):
        live.add_person(user_id, where="snake", status="Scored", data={"state": "over", "score": 50 - i})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length > 0")
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN})")
    # The frame is a phone's width: the top three of five, with the player's own place in the last spot
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 4")
    rows = strip_rows(driver)
    assert rows[2] == "you" and rows[3] == "arcade-live-more"
    assert driver.find_element(By.CSS_SELECTOR, ".arcade-live-more").text == "+2"
    assert driver.find_element(By.CSS_SELECTOR, ".arcade-live li.you .rank").text == "5"
    # Only the player's own name stays, to mark their entry
    assert not driver.find_element(By.CSS_SELECTOR, ".arcade-live .name").is_displayed()
    assert driver.find_element(By.CSS_SELECTOR, ".arcade-live li.you .name").text == "You"
    size_frame(driver, 900)
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 5")
    assert strip_rows(driver)[4] == "you"
    assert driver.find_element(By.CSS_SELECTOR, ".arcade-live .name").is_displayed()


def test_a_strip_entry_changes_in_place(driver, live):
    open_game(driver, live, "2048")
    rival = live.add_person(MANAGER_ID, where="2048", status="Scored 9", data={"state": "over", "score": 9})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 1")
    driver.execute_script(
        "window.firstRow = document.querySelector('.arcade-live li');"
        "window.firstFace = window.firstRow.querySelector('.avatar');"
        "window.touched = 0; window.reordered = 0;"
        "new MutationObserver((records) => { window.touched += records.length; })"
        "  .observe(document.querySelector('.arcade-live'), { childList: true, subtree: true, characterData: true });"
        "new MutationObserver((records) => { window.reordered += records.length; })"
        "  .observe(document.querySelector('.arcade-live'), { childList: true });"
    )
    # A new status line with the same score changes nothing the strip shows
    live.update_person(rival, where="2048", status="Looking around", data={"state": "over", "score": 9})
    wait_for(driver, "parent.testHost.presence.people.some((p) => p.status === 'Looking around')")
    assert driver.execute_script("return window.touched") == 0
    # A new score is written into the same entry, and its picture stays
    live.update_person(rival, where="2048", status="Scored 12", data={"state": "over", "score": 12})
    wait_for(driver, "document.querySelector('.arcade-live .points').textContent === '12'")
    assert driver.execute_script("return window.reordered") == 0
    assert driver.execute_script(
        "return document.querySelector('.arcade-live li') === window.firstRow"
        " && window.firstRow.querySelector('.avatar') === window.firstFace && window.firstFace.isConnected"
    )


def test_the_players_own_points_do_not_redraw_the_pictures(driver, live):
    open_game(driver, live, "2048")
    size_frame(driver, 900)
    live.add_person(MANAGER_ID, where="2048", status="Scored 9999", data={"state": "over", "score": 9999})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 1")
    start_round(driver)
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 2")
    driver.execute_script(
        "window.firstRow = document.querySelector('.arcade-live li');"
        "window.firstFace = window.firstRow.querySelector('.avatar');"
    )
    play_until(driver, f"{SCORE} >= 12")
    assert driver.execute_script(
        "return document.querySelector('.arcade-live li') === window.firstRow"
        " && window.firstRow.querySelector('.avatar') === window.firstFace && window.firstFace.isConnected"
    )


def test_another_players_name_is_shown_as_text(driver, live):
    live.hub.bot.guilds[GUILD_ID].members[MANAGER_ID].display_name = "<i>Rex</i>"
    open_game(driver, live, "2048")
    size_frame(driver, 900)
    live.add_person(MANAGER_ID, where="2048", status="Scored 1", data={"state": "over", "score": 1})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 1")
    assert driver.find_element(By.CSS_SELECTOR, ".arcade-live .name").text == "<i>Rex</i>"
    assert driver.execute_script("return document.querySelectorAll('.arcade-live i').length") == 0
    start_round(driver)
    play_until(driver, "window.notes.length > 0")
    assert driver.execute_script("return window.notes[0].text") == "You passed <i>Rex</i>!"
    assert driver.execute_script("return document.querySelector('.arcade-pass i') === null")


STRIP_NAMES = (
    "[...document.querySelectorAll('.arcade-live .name')].map((n) => [n.textContent, n.scrollWidth <= n.clientWidth])"
)


def test_a_long_name_in_the_strip_is_cut_at_whole_characters(driver, live):
    members = live.hub.bot.guilds[GUILD_ID].members
    members[MANAGER_ID].display_name = "Ana\U0001f469‍\U0001f4bbBellecarlotta"
    members[ADMIN_ID].display_name = "W" * 32
    open_game(driver, live, "2048")
    size_frame(driver, 900)
    live.add_person(MANAGER_ID, where="2048", status="Scored 9", data={"state": "over", "score": 9})
    live.add_person(ADMIN_ID, where="2048", status="Scored 7", data={"state": "over", "score": 7})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 2")
    # Eleven whole characters and "…", as in every game's own view, shown in full with no cut of the browser's own
    assert driver.execute_script(f"return {STRIP_NAMES}") == [
        ["Ana\U0001f469‍\U0001f4bbBelleca…", True],
        ["W" * 11 + "…", True],
    ]
    # On an upright phone, with the player's own entry too, the strip still fits across
    start_round(driver)
    size_frame(driver, 390, 700)
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 3")
    assert driver.execute_script(
        "const strip = document.querySelector('.arcade-live'); return strip.scrollWidth <= strip.clientWidth"
    )


def test_a_made_up_state_shows_no_mark(driver, live):
    open_game(driver, live, "2048")
    live.add_person(MANAGER_ID, where="2048", status="Scored 3", data={"state": "constructor", "score": 3})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 1")
    assert driver.execute_script("return document.querySelector('.arcade-live .state') === null")


def test_a_missing_picture_becomes_the_first_letter(driver, live):
    members = live.hub.bot.guilds[GUILD_ID].members
    members[MANAGER_ID].display_avatar.url = ""
    members[ADMIN_ID].display_avatar.url = "http://127.0.0.1:1/missing.png"
    open_game(driver, live, "2048")
    live.add_person(MANAGER_ID, where="2048", status="Scored 9", data={"state": "over", "score": 9})
    live.add_person(ADMIN_ID, where="2048", status="Scored 7", data={"state": "over", "score": 7})
    wait_for(driver, "document.querySelectorAll('.arcade-live span.avatar').length === 2")
    letters = driver.execute_script(
        "return [...document.querySelectorAll('.arcade-live span.avatar')].map((s) => s.textContent)"
    )
    assert letters == ["M", "A"]


def test_the_people_button_in_the_bar_opens_the_panel(driver, live):
    open_game(driver, live, "2048")
    size_frame(driver, 900)
    driver.find_element(By.CSS_SELECTOR, ".arcade-bar .hub-people button").click()
    driver.switch_to.default_content()
    wait_for(driver, "!document.querySelector('.hub-people-panel').hidden")


# ---------- Who is passed ----------


def test_someone_already_behind_is_never_passed(driver, live):
    open_game(driver, live, "2048")
    size_frame(driver, 900)
    start_round(driver)
    play_until(driver, f"{SCORE} >= 8")
    live.add_person(MANAGER_ID, where="2048", status="Playing · 2", data={"state": "playing", "score": 2})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 2")
    before = driver.execute_script(f"return {SCORE}")
    play_until(driver, f"{SCORE} >= {before + 8}")
    assert driver.execute_script("return window.notes") == []


def test_someone_who_starts_over_is_not_passed(driver, live):
    open_game(driver, live, "2048")
    size_frame(driver, 900)
    rival = live.add_person(MANAGER_ID, where="2048", status="Playing · 500", data={"state": "playing", "score": 500})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 1")
    start_round(driver)
    play_until(driver, f"{SCORE} >= 8")
    # The rival, far ahead, starts a new round: 0, then 2 points, both below the player
    live.update_person(rival, where="2048", status="Restarted", data={"state": "playing", "score": 0})
    wait_for(driver, "parent.testHost.presence.people.some((p) => p.status === 'Restarted')")
    live.update_person(rival, where="2048", status="Playing · 2", data={"state": "playing", "score": 2})
    wait_for(driver, "parent.testHost.presence.people.some((p) => p.status === 'Playing \\u00b7 2')")
    before = driver.execute_script(f"return {SCORE}")
    play_until(driver, f"{SCORE} >= {before + 8}")
    assert driver.execute_script("return window.notes") == []


def test_getting_ahead_of_someone_mid_round_is_noted(driver, live):
    open_game(driver, live, "2048")
    size_frame(driver, 900)
    start_round(driver)
    play_until(driver, f"{SCORE} >= 4")
    ahead = driver.execute_script(f"return {SCORE}") + 6
    live.add_person(MANAGER_ID, where="2048", status="Playing", data={"state": "playing", "score": ahead})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 2")
    play_until(driver, "window.notes.length > 0")
    assert driver.execute_script("return window.notes[0].text") == "You passed Manager!"


def test_a_long_passing_note_is_cut_short_on_a_phone(driver, live):
    members = live.hub.bot.guilds[GUILD_ID].members
    members[MANAGER_ID].display_name = "M" * 32
    members[ADMIN_ID].display_name = "A" * 32
    open_game(driver, live, "2048")
    size_frame(driver, 360, 640)
    live.add_person(MANAGER_ID, where="2048", status="Scored 3", data={"state": "over", "score": 3})
    live.add_person(ADMIN_ID, where="2048", status="Scored 2", data={"state": "over", "score": 2})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length > 0")
    start_round(driver)
    play_until(driver, "window.notes.length > 0")
    note = driver.execute_script("return window.notes[0]")
    assert note["text"].startswith("You passed M")
    assert note["width"] <= driver.execute_script("return document.getElementById('stage').clientWidth") - 16


# ---------- Where the strip sits ----------

# Where the strip, the playfield and the score are, in the frame's own pixels
GEOMETRY = """
const strip = document.querySelector('.arcade-live').getBoundingClientRect();
const field = document.querySelector('#board, #game').getBoundingClientRect();
const score = document.querySelector('.arcade-score');
const box = score.getBoundingClientRect();
const top = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
return {
  stripBottom: strip.bottom, fieldTop: field.top, fieldBottom: field.bottom, fieldHeight: field.height,
  height: innerHeight, scoreVisible: top === score,
};
"""


@pytest.mark.parametrize("game", ["2048", "snake", "brickbreaker"])
def test_the_strip_never_covers_the_playfield(driver, live, game):
    open_game(driver, live, game)
    for user_id, score in [(MANAGER_ID, 500), (ADMIN_ID, 400), (OWNER_ID, 300)]:
        live.add_person(user_id, where=game, status="Scored", data={"state": "over", "score": score})
    wait_for(driver, "!document.querySelector('.arcade-live').hidden")
    click_screen_button(driver, "Play")
    for width, height in [(1280, 720), (1024, 576), (800, 600)]:
        size_frame(driver, width, height)
        wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 4")
        # The playfield sizes itself to the room under the strip, once the frame has been resized
        wait_for(
            driver,
            "(() => { const g = document.querySelector('#board, #game').getBoundingClientRect();"
            " return g.height > 100 && g.bottom <= innerHeight + 0.5; })()",
        )
        found = driver.execute_script(GEOMETRY)
        assert found["fieldTop"] >= found["stripBottom"] - 0.5, (width, height, found)
        assert found["fieldBottom"] <= found["height"] + 0.5, (width, height, found)
        assert found["scoreVisible"], (width, height, found)


def test_the_playfield_resizes_when_the_strip_comes_and_goes(driver, live):
    open_game(driver, live, "snake")
    size_frame(driver, 900, 700)
    height = "document.getElementById('stage').clientHeight"
    alone = driver.execute_script(f"return {height}")
    rival = live.add_person(MANAGER_ID, where="snake", status="Scored 9", data={"state": "over", "score": 9})
    wait_for(driver, f"{height} < {alone}")
    strip = driver.execute_script("return document.querySelector('.arcade-live').offsetHeight")
    assert abs(driver.execute_script(f"return {height}") - (alone - strip)) <= 1
    live.update_person(rival, where=None, status="", data=None)
    wait_for(driver, f"{height} === {alone}")


def test_an_arrival_note_shows_above_the_strip(driver, live):
    open_game(driver, live, "snake")
    size_frame(driver, 1280, 720)
    for user_id, score in [(MANAGER_ID, 500), (ADMIN_ID, 400)]:
        live.add_person(user_id, where="snake", status="Scored", data={"state": "over", "score": score})
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 2")
    # Mid-round, with no screen over the playfield
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN})")
    # Past the quiet time after the link opened, so this counts as someone arriving
    in_host(driver, "window.testHost.presence.quietUntil = 0")
    live.add_person(OWNER_ID, where="snake", status="Getting ready", data={"state": "idle"})
    wait_for(driver, "document.querySelector('.hub-note')?.textContent")
    on_top = driver.execute_script(
        """
        const note = document.querySelector('.hub-note');
        // A note takes no clicks, which would also let a hit test see straight through it
        note.style.pointerEvents = 'auto';
        // Something placed later in the page, like a game's own banner, must not paint over the note
        const layer = document.createElement('div');
        layer.style.cssText = 'position: fixed; inset: 0;';
        document.body.append(layer);
        const box = note.getBoundingClientRect();
        const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        const overlaps = [...document.querySelectorAll('.arcade-live li')].some((li) => {
          const pill = li.getBoundingClientRect();
          return box.bottom > pill.top && box.top < pill.bottom && box.right > pill.left && box.left < pill.right;
        });
        return { onTop: note.contains(hit), overStrip: overlaps };
        """
    )
    assert on_top == {"onTop": True, "overStrip": True}


# ---------- Payout settings ----------

GEAR = ".arcade-bar .arcade-payouts-open"
DIALOG = "document.querySelector('dialog.arcade-payouts')"
PAYOUT_STATUS = "document.querySelector('.arcade-payouts-status').textContent"
RATE_BOX = "document.querySelector('.arcade-payouts input[data-field=\"rate\"]').value"
# Where the open dialog and everything in it sits, in the frame's own pixels
DIALOG_FIT = """
const dialog = document.querySelector('dialog.arcade-payouts');
const box = dialog.getBoundingClientRect();
const parts = [...dialog.querySelectorAll('button, input[type=number]')].map((node) => {
  const rect = node.getBoundingClientRect();
  return { text: node.textContent || node.dataset.field, left: rect.left, right: rect.right, height: rect.height };
});
return {
  top: box.top, bottom: box.bottom, left: box.left, right: box.right, width: innerWidth, height: innerHeight,
  sideways: dialog.scrollWidth > dialog.clientWidth || document.documentElement.scrollWidth > innerWidth,
  parts,
};
"""
# Where the bar's parts sit, whether the score shows whole, and where Best is. A hit test respects clipping and sees
# what is drawn on top, so the score's ends and middle only answer as the score when nothing cuts it off or covers it.
# Best shows whole inside its room, or sits entirely on the row below it, out of sight
BAR_FIT = """
const bar = document.querySelector('.arcade-bar');
const box = bar.getBoundingClientRect();
const place = (selector) => {
  const rect = document.querySelector(selector).getBoundingClientRect();
  return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
};
const score = document.querySelector('.arcade-score');
const rect = score.getBoundingClientRect();
const xs = [rect.left + 1, (rect.left + rect.right) / 2, rect.right - 1];
const ends = xs.map((x) => document.elementFromPoint(x, (rect.top + rect.bottom) / 2));
const room = document.querySelector('.arcade-best-room').getBoundingClientRect();
const best = document.querySelector('.arcade-best-room .arcade-stat').getBoundingClientRect();
const bestWhole = best.left >= room.left - 0.5 && best.right <= room.right + 0.5 && best.top >= room.top - 0.5
  && best.bottom <= room.bottom + 0.5 && best.left >= rect.right - 0.5;
return {
  bar: { left: box.left, right: box.right, top: box.top, bottom: box.bottom },
  overflows: bar.scrollWidth > bar.clientWidth,
  people: place('.arcade-bar .hub-people'),
  gear: place('.arcade-bar .arcade-payouts-open'),
  mute: place('.arcade-bar .arcade-icon[aria-label^="Turn sound"]'),
  pause: place('.arcade-bar .arcade-icon[aria-label="Pause"]'),
  score: place('.arcade-score'),
  scoreText: score.textContent,
  scoreWhole: ends.every((node) => node === score),
  bestPlaced: bestWhole || best.top >= room.bottom - 0.5,
  logo: document.querySelector('.arcade-bar-logo').getBoundingClientRect().width,
};
"""
GEAR_SHOWN = "!document.querySelector('.arcade-payouts-open').hidden"
HINT = "document.querySelector('.arcade-hint')"
SAVE_BUTTON = "[...document.querySelectorAll('dialog.arcade-payouts button')].find((b) => b.textContent === 'Save')"
COUNT_KEYS = "window.gameKeys = 0; window.addEventListener('keydown', () => { window.gameKeys += 1; });"
# A swipe on 2048's board in each direction, begun with the payout settings closed. The settings open (or not) while the
# finger is down, then it lifts. Returns, for each swipe, whether the dialog was open, whether the gear still shows,
# and the tiles' places, so a test can tell whether a move happened
SWIPE_ACROSS_DIALOG = """
const [openIt] = arguments;
const stage = document.getElementById('stage');
const gear = document.querySelector('.arcade-payouts-open');
const tiles = () => [...document.querySelectorAll('.tile')].map((t) => `${t.style.cssText}|${t.textContent}`).join(',');
const box = stage.getBoundingClientRect();
const x = box.left + box.width / 2;
const y = box.top + box.height / 2;
const out = [];
for (const [dx, dy] of [[120, 0], [-120, 0], [0, 120], [0, -120]]) {
  const before = tiles();
  stage.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, clientX: x, clientY: y, pointerId: 7 }));
  if (openIt) {
    gear.click();
  }
  const dialog = document.querySelector('dialog.arcade-payouts');
  const target = dialog && dialog.open ? dialog : stage;
  const end = { bubbles: true, clientX: x + dx, clientY: y + dy, pointerId: 7 };
  target.dispatchEvent(new PointerEvent('pointermove', end));
  target.dispatchEvent(new PointerEvent('pointerup', end));
  out.push({ dialogOpen: Boolean(dialog && dialog.open), gearShown: !gear.hidden, moved: tiles() !== before });
  if (dialog && dialog.open) {
    dialog.close();
  }
  // A finger sliding on and lifting later, with the settings closed again, can't finish the old swipe either
  window.dispatchEvent(new PointerEvent('pointermove', end));
  window.dispatchEvent(new PointerEvent('pointerup', end));
  out[out.length - 1].movedAfter = tiles() !== before;
}
return out;
"""


def shown_gear(driver):
    gears = driver.find_elements(By.CSS_SELECTOR, GEAR)
    return gears[0] if gears and gears[0].is_displayed() else None


def open_payouts(driver):
    WebDriverWait(driver, 5).until(shown_gear).click()
    wait_for(driver, f"{DIALOG}.open")


def click_dialog_button(driver, text):
    buttons = driver.find_elements(By.CSS_SELECTOR, "dialog.arcade-payouts button")
    next(button for button in buttons if button.text == text).click()


def record_payout_answers(live, monkeypatch, key) -> list:
    """Every answer the game's payouts action gives, as the bot sends it"""
    game = live.hub.registry.games[key]
    real = game.actions["payouts"]
    answers = []

    async def recorded(ctx, data):
        answer = await real(ctx, data)
        answers.append(answer)
        return answer

    monkeypatch.setitem(game.actions, "payouts", recorded)
    return answers


def wait_ms(driver, ms):
    driver.execute_script(f"return new Promise((done) => setTimeout(done, {ms}))")


def near_the_bottom(driver, element):
    """A pointer over the element, near its bottom: over the playfield, below where the dialog sits"""
    return ActionChains(driver).move_to_element_with_offset(element, 0, element.size["height"] // 2 - 40)


def swipe_up(driver):
    press_down = near_the_bottom(driver, driver.find_element(By.ID, "stage")).click_and_hold()
    press_down.move_by_offset(0, -120).release().perform()


def tap(driver, element):
    near_the_bottom(driver, element).click().perform()


def test_no_tap_in_a_bundled_game_waits_for_a_double_tap(driver, live):
    live.user_id = MANAGER_ID
    open_game(driver, live, "snake")
    assert driver.execute_script(WAITS_FOR_DOUBLE_TAP) == []
    open_payouts(driver)
    assert driver.execute_script(WAITS_FOR_DOUBLE_TAP) == []


def test_an_admin_turns_payouts_on_from_the_gear(driver, live, monkeypatch):
    game = live.hub.registry.games["snake"]
    real_save = game.actions["save_payouts"]

    async def slow_save(ctx, data):
        # Long enough to see the page while the save is on its way
        await asyncio.sleep(0.4)
        return await real_save(ctx, data)

    monkeypatch.setitem(game.actions, "save_payouts", slow_save)
    live.user_id = MANAGER_ID
    open_game(driver, live, "snake")
    open_payouts(driver)
    text = driver.find_element(By.CSS_SELECTOR, "dialog.arcade-payouts").text
    assert "Snake payouts" in text and "Credits per apple" in text and "midnight UTC" in text
    assert "The bank is global" not in text
    driver.find_element(By.CSS_SELECTOR, 'dialog.arcade-payouts input[data-field="on"]').click()
    rate = driver.find_element(By.CSS_SELECTOR, 'dialog.arcade-payouts input[data-field="rate"]')
    rate.send_keys(Keys.BACKSPACE, Keys.BACKSPACE, "2.5")
    click_dialog_button(driver, "Save")
    # Save can't be pressed again until this save has its answer
    assert driver.execute_script(f"return {SAVE_BUTTON}.disabled && {PAYOUT_STATUS} === 'Saving...'")
    wait_for(driver, f"{PAYOUT_STATUS} === 'Saved.'")
    assert not driver.execute_script(f"return {SAVE_BUTTON}.disabled")
    assert live.hub.config.guilds[GUILD_ID]["payouts"] == {"snake": {"on": True, "rate": 2.5, "cap": 1000, "plays": 3}}
    # A bad number is refused with the bot's reason, nothing changes, and Save works again
    plays = driver.find_element(By.CSS_SELECTOR, 'dialog.arcade-payouts input[data-field="plays"]')
    plays.send_keys(Keys.BACKSPACE)
    click_dialog_button(driver, "Save")
    assert driver.execute_script(f"return {SAVE_BUTTON}.disabled")
    wait_for(driver, f"{PAYOUT_STATUS}.includes('cash-ins a day')")
    assert not driver.execute_script(f"return {SAVE_BUTTON}.disabled")
    assert live.hub.config.guilds[GUILD_ID]["payouts"]["snake"]["plays"] == 3
    # Reset shows the defaults, and Close throws away what wasn't saved
    click_dialog_button(driver, "Reset to defaults")
    assert driver.execute_script(f"return {RATE_BOX}") == "25"
    click_dialog_button(driver, "Close")
    wait_for(driver, f"!{DIALOG}.open")
    open_payouts(driver)
    assert driver.execute_script(f"return {RATE_BOX}") == "2.5"


def test_the_gear_shows_only_between_rounds(driver, live):
    live.hub.config.guild_from_id(GUILD_ID).data["payouts"] = {"2048": {"on": True, "rate": 1, "cap": 50, "plays": 3}}
    live.user_id = MANAGER_ID
    open_game(driver, live, "2048")
    WebDriverWait(driver, 5).until(shown_gear)
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    # The board waits for the first slide, which is still before the round
    assert shown_gear(driver) is not None
    play_until(driver, f"{SCORE} >= 4")
    assert shown_gear(driver) is None
    # A paused round is still running
    press(driver, Keys.ESCAPE)
    wait_for(driver, f"{SCREEN_TEXT}.includes('Paused')")
    assert shown_gear(driver) is None
    click_screen_button(driver, "Resume")
    wait_for(driver, f"!({SCREEN_OPEN})")
    assert shown_gear(driver) is None
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    # The results and the cash-in are between rounds
    wait_for(driver, f"{SCREEN_TEXT}.includes('cash-ins left today')")
    WebDriverWait(driver, 5).until(shown_gear)
    worth = min(int(driver.execute_script("return document.querySelector('.arcade-final').dataset.value")), 50)
    click_screen_button(driver, f"Cash in {worth}")
    wait_for(driver, "document.querySelector('.arcade-paid')")
    assert shown_gear(driver) is not None
    # So is the next round's wait for its first slide
    click_screen_button(driver, "Play again")
    wait_for(driver, f"!({SCREEN_OPEN})")
    assert shown_gear(driver) is not None


def test_a_key_or_swipe_with_the_payouts_open_does_not_start_a_round(driver, live):
    live.user_id = MANAGER_ID
    open_game(driver, live, "snake")
    size_frame(driver, 800, 640)
    click_screen_button(driver, "Play")
    waiting = f"!{HINT}.hidden && {HINT}.textContent.includes('to start')"
    wait_for(driver, waiting)
    open_payouts(driver)
    driver.execute_script(COUNT_KEYS)
    press(driver, Keys.ARROW_UP, Keys.ARROW_RIGHT, "w", Keys.SPACE, "p", "m")
    swipe_up(driver)
    wait_ms(driver, 400)
    assert driver.execute_script(f"return {waiting} && {DIALOG}.open && window.gameKeys === 0")
    # Escape closes it, and only that: the waiting round isn't paused
    press(driver, Keys.ESCAPE)
    wait_for(driver, f"!{DIALOG}.open")
    assert driver.execute_script(f"return {waiting} && !({SCREEN_OPEN}) && window.gameKeys === 0")
    # With the dialog closed, the same swipe starts the round, and the gear goes
    swipe_up(driver)
    wait_for(driver, f"{HINT}.hidden && !{GEAR_SHOWN}")


def test_a_tap_or_space_with_the_payouts_open_does_not_launch_the_ball(driver, live):
    live.user_id = MANAGER_ID
    open_game(driver, live, "brickbreaker")
    size_frame(driver, 800, 640)
    click_screen_button(driver, "Play")
    ready = f"!{HINT}.hidden && {HINT}.textContent.includes('to launch')"
    wait_for(driver, ready)
    open_payouts(driver)
    canvas = driver.find_element(By.CSS_SELECTOR, "#stage canvas")
    tap(driver, canvas)
    press(driver, Keys.SPACE)
    wait_ms(driver, 400)
    assert driver.execute_script(f"return {ready} && {DIALOG}.open")
    click_dialog_button(driver, "Close")
    wait_for(driver, f"!{DIALOG}.open")
    tap(driver, canvas)
    wait_for(driver, f"{HINT}.hidden && !{GEAR_SHOWN}")


def test_a_swipe_begun_before_the_payouts_opened_does_not_move_behind_them(driver, live):
    live.user_id = MANAGER_ID
    open_game(driver, live, "2048")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    for swipe in driver.execute_script(SWIPE_ACROSS_DIALOG, True):
        assert swipe == {"dialogOpen": True, "gearShown": True, "moved": False, "movedAfter": False}, swipe
    # The same swipes with the settings closed do slide the board, so the check above can see a move
    moves = driver.execute_script(SWIPE_ACROSS_DIALOG, False)
    assert any(swipe["moved"] for swipe in moves), moves
    assert shown_gear(driver) is None


def test_a_round_paused_before_its_first_move_is_still_between_rounds(driver, live):
    live.user_id = MANAGER_ID
    open_game(driver, live, "snake")
    click_screen_button(driver, "Play")
    wait_for(driver, f"!{HINT}.hidden && {HINT}.textContent.includes('to start')")
    open_payouts(driver)
    # Clicking into Discord's chat takes the focus away, which pauses the waiting round
    driver.execute_script("window.dispatchEvent(new Event('blur'))")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Paused')")
    assert driver.execute_script(f"return {DIALOG}.open") and shown_gear(driver) is not None
    press(driver, Keys.ESCAPE)
    wait_for(driver, f"!{DIALOG}.open")
    assert shown_gear(driver) is not None
    click_screen_button(driver, "Resume")
    wait_for(driver, f"!({SCREEN_OPEN})")
    assert shown_gear(driver) is not None


def test_a_plain_player_has_no_gear_and_the_settings_are_asked_for_once(driver, live, monkeypatch):
    answers = record_payout_answers(live, monkeypatch, "snake")
    open_game(driver, live, "snake")
    WebDriverWait(driver, 5).until(lambda d: answers)
    assert answers == [{"settings": None}]
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN})")
    press(driver, Keys.ARROW_RIGHT)
    wait_for(driver, f"{SCREEN_OPEN} && {SCREEN_TEXT}.includes('Game over')", timeout=10)
    assert len(answers) == 1
    assert shown_gear(driver) is None


def test_the_payout_dialog_fits_a_phone(driver, live):
    live.hub.payouts.bank.global_bank = True
    live.user_id = OWNER_ID
    open_game(driver, live, "snake")
    size_frame(driver, 390, 844)
    open_payouts(driver)
    assert "The bank is global" in driver.find_element(By.CSS_SELECTOR, "dialog.arcade-payouts").text
    found = driver.execute_script(DIALOG_FIT)
    assert not found["sideways"], found
    assert found["top"] >= 0 and found["bottom"] <= found["height"], found
    assert found["left"] >= 0 and found["right"] <= found["width"], found
    for part in found["parts"]:
        assert part["height"] >= 40, part
        assert found["left"] <= part["left"] and part["right"] <= found["right"], part


def check_bar(driver, names):
    """Nothing spills out of the bar, these parts sit inside it in this order, the score shows whole, and Best is
    whole or out of sight"""
    found = driver.execute_script(BAR_FIT)
    bar = found["bar"]
    assert not found["overflows"], found
    order = [found[name] for name in names]
    for before, after in zip(order, order[1:]):
        assert before["right"] <= after["left"], found
    for part in order:
        assert bar["left"] <= part["left"] and part["right"] <= bar["right"], found
        assert bar["top"] <= part["top"] and part["bottom"] <= bar["bottom"], found
    assert found["scoreWhole"], found
    assert found["bestPlaced"], found
    # The logo is shown whole or not at all
    assert found["logo"] in (0, 26), found
    return found


@pytest.mark.parametrize("width", [320, 390])
def test_the_bar_fits_a_phone_between_rounds_and_mid_round(driver, live, width):
    live.user_id = MANAGER_ID
    # A 6-digit best beside the score, and three others here, so the people button shows their faces: the bar at its
    # fullest
    live.hub.config.member_from_ids(GUILD_ID, MANAGER_ID).data["best"] = {"2048": {"score": 123456, "at": 0}}
    open_game(driver, live, "2048")
    for user_id in (OWNER_ID, ADMIN_ID, GUILD_OWNER_ID):
        live.add_person(user_id, where="2048", status="Getting ready", data={"state": "idle"})
    size_frame(driver, width, 640)
    WebDriverWait(driver, 5).until(shown_gear)
    wait_for(driver, "document.querySelectorAll('.arcade-bar .hub-people .hub-avatar').length === 3")
    wait_for(driver, "document.querySelector('.arcade-best').textContent === '123,456'")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    # Before the first slide the round hasn't begun, so the gear shows beside pause
    check_bar(driver, ["score", "people", "gear", "mute", "pause"])
    press(driver, *ARROWS)
    wait_for(driver, f"!{GEAR_SHOWN}")
    # Mid-round there's no gear, and even a 7-digit score shows whole
    driver.execute_script("document.querySelector('.arcade-score').textContent = '1,234,567'")
    wait_ms(driver, 300)
    found = check_bar(driver, ["score", "people", "mute", "pause"])
    assert found["scoreText"] == "1,234,567"
