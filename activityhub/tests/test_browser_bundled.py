import asyncio
import contextlib
import itertools
import time

import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait

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
    fake_member,
    fake_user,
    make_hub,
    register,
)

# A picture that loads with no network, so a test never sees an avatar fail to load by chance
OFFLINE_AVATAR = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8'/%3E"
SCREEN_TEXT = "document.querySelector('.arcade-screen').innerText"
SCREEN_OPEN = "!document.querySelector('.arcade-screen').hidden"
GAMES = ["2048", "snake", "brickbreaker"]
# Retry save's look next to Play again's, whether it sits in a button row, its height, and whether it shows whole: in
# the window, with hit tests near its top, at its middle and near its bottom all finding it
RETRY_LOOK = """
const buttons = [...document.querySelectorAll('.arcade-screen button')];
const retry = buttons.find((b) => b.textContent === 'Retry save');
const again = buttons.find((b) => b.textContent === 'Play again');
const look = (b) => {
  const s = getComputedStyle(b);
  return { radius: s.borderTopLeftRadius, background: s.backgroundColor, color: s.color };
};
const box = retry.getBoundingClientRect();
const hits = [box.top + 2, box.top + box.height / 2, box.bottom - 2].every(
  (y) => document.elementFromPoint(box.left + box.width / 2, y) === retry,
);
return {
  inRow: retry.parentElement.classList.contains('arcade-actions'),
  height: box.height,
  shown: box.top >= 0 && box.bottom <= innerHeight && hits,
  retry: look(retry),
  again: look(again),
};
"""


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
    # The frame's default 150 px height leaves the results card little more than its button row
    size_frame(driver, 640)
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
    # Worded the same as the offer
    assert "2 of 3 cash-ins left today." in driver.execute_script(f"return {SCREEN_TEXT}")
    assert live.hub.payouts.bank.balances[MEMBER_ID] == worth


def test_2048_round_is_saved_and_shows_the_board(driver, live):
    open_game(driver, live, "2048")
    wait_for(driver, f"{SCREEN_TEXT}.includes('No score here yet')")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    press(driver, *[Keys.ARROW_LEFT, Keys.ARROW_UP, Keys.ARROW_RIGHT, Keys.ARROW_DOWN] * 6)
    press(driver, Keys.ESCAPE)
    wait_for(driver, f"{SCREEN_TEXT}.includes('Paused')")
    # A keyboard has the keys the card names
    assert "Press Esc or P to keep playing." in driver.execute_script(f"return {SCREEN_TEXT}")
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Top scores in Test Server') || {SCREEN_TEXT}.includes('Your best')")
    shown = int(driver.execute_script("return document.querySelector('.arcade-final').dataset.value"))
    assert shown > 0
    assert saved_best(live, "2048")["score"] == shown
    assert "New best!" in driver.execute_script(f"return {SCREEN_TEXT}")
    assert driver.execute_script("return document.querySelector('.arcade-best').innerText") == f"{shown:,}"


# Slides 2048's tiles until two merge, then reads where the "+N" box is 0, 300 and 650 ms into its rise: its top and
# bottom inside the stage, and its top against the board's. All in one go, so the box can't be taken away in between
GAIN_PLACES = """
document.querySelector('.gain')?.remove();
const keys = ['ArrowLeft', 'ArrowUp', 'ArrowRight', 'ArrowDown'];
for (let i = 0; i < 200 && !document.querySelector('.gain'); i++) {
  window.dispatchEvent(new KeyboardEvent('keydown', { key: keys[i % 4] }));
}
const gain = document.querySelector('.gain');
const stage = document.getElementById('stage').getBoundingClientRect();
const board = document.getElementById('board').getBoundingClientRect();
const rise = gain.getAnimations()[0];
rise.pause();
return [0, 300, 650].map((ms) => {
  rise.currentTime = ms;
  const box = gain.getBoundingClientRect();
  return { ms, top: box.top - stage.top, bottom: stage.bottom - box.bottom, fromBoard: box.top - board.top };
});
"""
# Slides up and right until the "+N" shows over a tile that just merged in the top-right corner, then says whether the
# points are what is on top at their middle. They let presses through, so they take them for the one hit test
GAIN_OVER_A_MERGE = """
return (async () => {
  const keys = ['ArrowUp', 'ArrowRight', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowRight', 'ArrowDown'];
  for (let i = 0; i < 120; i++) {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: keys[i % keys.length] }));
    await new Promise((done) => setTimeout(done, 120));
    const gain = document.querySelector('.gain');
    if (!gain) continue;
    const g = gain.getBoundingClientRect();
    const under = [...document.querySelectorAll('.tile.merged')].some((tile) => {
      const t = tile.getBoundingClientRect();
      return t.left < g.right && t.right > g.left && t.top < g.bottom && t.bottom > g.top;
    });
    if (!under) continue;
    gain.style.pointerEvents = 'auto';
    const top = document.elementFromPoint(g.left + g.width / 2, g.top + g.height / 2);
    gain.style.pointerEvents = '';
    return top === gain;
  }
  return null;
})();
"""


def test_the_merge_points_stay_inside_the_play_area(driver, live):
    open_game(driver, live, "2048")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    for width, height in [(1280, 800), (390, 844), (844, 390)]:
        with touch_if_phone(driver, width):
            size_frame(driver, width, height)
            wait_ms(driver, 200)
            places = driver.execute_script(GAIN_PLACES)
            assert all(place["top"] >= 0 and place["bottom"] >= 0 for place in places), (width, height, places)
            if height > 520:
                # Where there is room above the board, the points still start just above its top edge
                assert abs(places[0]["fromBoard"] + 4) <= 0.5, (width, height, places)
    # Sideways they start over the top-right cell, and a tile merging there doesn't hide them
    assert driver.execute_script(GAIN_OVER_A_MERGE) is True


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
    # Lives are lives, so Multi-ball's "+2 balls" can only mean balls in play
    assert "You have 3 lives." in driver.execute_script("return document.querySelector('.arcade-help').textContent")
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


# Records, in the page's own clock, when the falling Game over tune starts (its first note, 392 Hz, plays nowhere else)
# and each card that opens, on the menu page, which outlives the game's frame. window.duringTheWait runs 100 ms after
# the tune starts. Every launch then goes straight up and no brick drops a power-up
SPY_ON_THE_END = """
window.overTune = null;
window.parent.cards = [];
const realSet = AudioParam.prototype.setValueAtTime;
AudioParam.prototype.setValueAtTime = function (value, time) {
  if (value === 392 && window.overTune === null) {
    window.overTune = performance.now();
    setTimeout(() => window.duringTheWait?.(), 100);
  }
  return realSet.call(this, value, time);
};
new MutationObserver(() => {
  const heading = document.querySelector('.arcade-screen h1');
  if (heading) window.parent.cards.push([heading.textContent, performance.now()]);
}).observe(document.querySelector('.arcade-screen'), { childList: true });
Math.random = () => 0.5;
"""
ESC_DURING_THE_WAIT = "window.duringTheWait = () => dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))"
MENU_DURING_THE_WAIT = "window.duringTheWait = () => document.querySelector('.arcade-back').click()"


def lose_every_ball(driver, first_wall):
    """Launch each ball straight up and move the paddle to a wall away from it, so it falls past. The paddle goes to
    first_wall (-1 left, 1 right) first, then to the other wall, then back. Returns as the last ball flies"""
    canvas = driver.find_element(By.ID, "game")
    edge = canvas.size["width"] // 2 - 1
    for life, wall in enumerate([first_wall, -first_wall, first_wall]):
        press(driver, Keys.SPACE)
        wait_for(driver, f"{HINT}.hidden")
        ActionChains(driver).move_to_element_with_offset(canvas, wall * edge, 0).perform()
        if life < 2:
            # The next ball rests on the paddle, where it went
            wait_for(driver, WAITING["brickbreaker"])


def test_brick_breaker_shows_the_last_ball_lost_before_game_over(driver, live, monkeypatch):
    sent = record_finishes(live, monkeypatch, "brickbreaker")
    open_game(driver, live, "brickbreaker")
    size_frame(driver, 900, 700)
    driver.execute_script(SPY_ON_THE_END)
    # Esc during the wait pauses the round, which still ends with one results card and one save
    driver.execute_script(ESC_DURING_THE_WAIT)
    click_screen_button(driver, "Play")
    wait_for(driver, WAITING["brickbreaker"])
    lose_every_ball(driver, -1)
    wait_for(driver, f"{SCREEN_TEXT}.includes('Game over') && !{SCREEN_TEXT}.includes('Saving')")
    # Long enough for a second results card to show, if one were coming
    wait_ms(driver, 600)
    tune, cards = driver.execute_script("return [window.overTune, window.parent.cards]")
    assert [title for title, _ in cards] == ["Paused", "Game over"], cards
    # The player sees the last ball fall and hears the tune start before the card opens, as long as Snake's crash
    assert 450 <= cards[1][1] - tune <= 550, (tune, cards)
    assert len(sent) == 1
    # The menu button during the wait saves the round once and goes back to the menu, with no results card
    driver.execute_script("window.overTune = null; window.parent.cards = [];")
    driver.execute_script(MENU_DURING_THE_WAIT)
    click_screen_button(driver, "Play again")
    wait_for(driver, WAITING["brickbreaker"])
    lose_every_ball(driver, 1)
    wait_closed(driver)
    assert len(sent) == 2
    assert driver.execute_script("return window.cards") == []


# Holds Brick Breaker's levels back for 1.5 s in every page opened from here on, as a slow network would
HOLD_LEVELS = """
const realFetch = window.fetch;
window.fetch = (url, init) => String(url).endsWith('/levels.json')
  ? new Promise((done) => setTimeout(done, 1500)).then(() => realFetch(url, init))
  : realFetch(url, init);
"""
CANVAS_SHOWN = "getComputedStyle(document.getElementById('game')).visibility === 'visible'"


def test_brick_breaker_shows_no_empty_box_while_its_levels_load(driver, live):
    script = driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": HOLD_LEVELS})
    try:
        driver.get(f"{live.url}/{DISCORD_QUERY}")
        assert wait_for(driver, "document.body.dataset.login") == "online"
        driver.execute_script("window.testHost.openGame('brickbreaker')")
        # The menu shows the frame once its page has loaded, which doesn't wait for the levels
        wait_for(driver, "document.getElementById('game-frame').classList.contains('loading') === false")
        driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
        shown = driver.execute_script(f"return [{CANVAS_SHOWN}, document.querySelector('.arcade-screen')]")
        assert shown == [False, None]
        wait_for(driver, "document.querySelector('.arcade-screen button.primary')")
    finally:
        driver.execute_cdp_cmd("Page.removeScriptToEvaluateOnNewDocument", script)
    for width, height in [(1280, 800), (390, 844), (844, 390)]:
        size_frame(driver, width, height)
        assert wait_for(driver, CANVAS_SHOWN), (width, height)


# Brick Breaker's hint, a Level cleared banner put on the stage by hand, the canvas, and the paddle's top, which is
# 592 of the field's 640 game pixels down (PADDLE_Y in its game.js)
INSIDE_THE_FIELD = """
const banner = document.createElement('div');
banner.className = 'arcade-banner';
banner.style.animation = 'none';
for (const [tag, text] of [['strong', 'Level cleared!'], ['span', '+100 points. Level 2 is next.']]) {
  const part = document.createElement(tag);
  part.textContent = text;
  banner.append(part);
}
document.getElementById('stage').append(banner);
const box = (node) => {
  const r = node.getBoundingClientRect();
  return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
};
const range = document.createRange();
range.selectNodeContents(banner.querySelector('strong'));
const field = box(document.getElementById('game'));
const found = {
  hint: box(document.querySelector('.arcade-hint')),
  banner: box(banner),
  titleLines: range.getClientRects().length,
  field,
  paddleTop: field.top + ((field.bottom - field.top) * 592) / 640,
};
banner.remove();
return found;
"""


@pytest.mark.parametrize(
    ("width", "height", "others"), [(1280, 800, False), (390, 844, False), (844, 390, False), (844, 390, True)]
)
def test_brick_breakers_hint_and_banner_sit_inside_its_field(driver, live, width, height, others):
    open_game(driver, live, "brickbreaker")
    if others:
        # The row of scores above the game takes height from the stage, and so width from the field
        for user_id, score in [(MANAGER_ID, 500), (ADMIN_ID, 400), (OWNER_ID, 300)]:
            live.add_person(user_id, where="brickbreaker", status="Scored", data={"state": "over", "score": score})
        wait_for(driver, "!document.querySelector('.arcade-live').hidden")
    with touch_if_phone(driver, width):
        size_frame(driver, width, height)
        click_screen_button(driver, "Play")
        wait_for(driver, f"{WAITING['brickbreaker']} && !({SCREEN_OPEN})")
        found = driver.execute_script(INSIDE_THE_FIELD)
    hint, banner, field = found["hint"], found["banner"], found["field"]
    for part in (hint, banner):
        assert field["left"] <= part["left"] and part["right"] <= field["right"], found
    assert found["titleLines"] == 1, found
    assert hint["top"] - banner["bottom"] >= 8, found
    assert hint["bottom"] <= found["paddleTop"], found


# The size each power-up capsule's letter draws at on the screen, and its size in game pixels, from the canvas's own
# calls. A capsule draws its letter after moving to where the capsule is, and the power-up timers at the top draw theirs
# in place, so only moved letters count. Every launch then goes up and to the left and every broken brick drops a
# capsule, so one falls within a second
SPY_ON_CAPSULE_LETTERS = """
window.letters = [];
const realFill = CanvasRenderingContext2D.prototype.fillText;
CanvasRenderingContext2D.prototype.fillText = function (text, x, y) {
  const { e, f } = this.getTransform();
  if (['W', 'M', 'S', '+'].includes(text) && (e || f)) {
    const size = Number(this.font.match(/(\\d+)px/)[1]);
    const box = this.measureText(text);
    window.letters.push({
      onScreen: (size * this.getTransform().a) / devicePixelRatio,
      width: box.width,
      height: box.actualBoundingBoxAscent + box.actualBoundingBoxDescent,
    });
  }
  return realFill.call(this, text, x, y);
};
Math.random = () => 0;
"""


def test_brick_breakers_capsule_letters_are_readable_on_a_phone(driver, live):
    open_game(driver, live, "brickbreaker")
    size_frame(driver, 390, 844)
    click_screen_button(driver, "Play")
    wait_for(driver, f"{WAITING['brickbreaker']} && !({SCREEN_OPEN})")
    driver.execute_script(SPY_ON_CAPSULE_LETTERS)
    press(driver, Keys.SPACE)
    letter = wait_for(driver, "window.letters[0]")
    # About 10 px on the screen is the least a phone shows readably. The capsule is 36 by 16 game pixels with round ends
    assert 11 <= letter["onScreen"] <= 12, letter
    assert letter["width"] <= 20 and letter["height"] <= 16, letter


# Records how tall the level's name in the top strip is drawn, in screen pixels
SPY_ON_THE_LEVEL = """
window.levelPx = null;
const realFill = CanvasRenderingContext2D.prototype.fillText;
CanvasRenderingContext2D.prototype.fillText = function (text, x, y) {
  if (String(text).startsWith('LEVEL')) {
    window.levelPx = (Number(this.font.match(/([\d.]+)px/)[1]) * this.getTransform().a) / devicePixelRatio;
  }
  return realFill.call(this, text, x, y);
};
"""


def test_brick_breakers_level_reads_on_a_sideways_phone_and_is_unchanged_on_a_desktop(driver, live):
    open_game(driver, live, "brickbreaker")
    driver.execute_script(SPY_ON_THE_LEVEL)
    click_screen_button(driver, "Play")
    wait_for(driver, f"{WAITING['brickbreaker']} && !({SCREEN_OPEN})")
    sizes = {}
    for width, height in [(844, 390), (1280, 800)]:
        size_frame(driver, width, height)
        wait_ms(driver, 150)
        scale = driver.execute_script(
            "return document.querySelector('#stage canvas').getBoundingClientRect().width / 480"
        )
        sizes[width] = (driver.execute_script("return window.levelPx"), scale)
    assert sizes[844][0] >= 9.9, sizes
    assert sizes[1280][0] == pytest.approx(14 * sizes[1280][1], abs=0.1), sizes


def test_a_finger_lines_the_paddle_up_before_a_tap_launches_the_ball(driver, live):
    with touch_screen(driver):
        open_game(driver, live, "brickbreaker")
        size_frame(driver, 390, 844)
        click_screen_button(driver, "Play")
        wait_for(driver, f"{WAITING['brickbreaker']} && !({SCREEN_OPEN})")
        assert driver.execute_script(f"return {HINT}.textContent") == "Drag to aim, tap to launch"
        finger_slide(driver, "#stage canvas", 0.3, 0.7)
        wait_ms(driver, 300)
        assert driver.execute_script(f"return {WAITING['brickbreaker']}")
        finger_slide(driver, "#stage canvas", 0.5, 0.5)
        wait_for(driver, f"{HINT}.hidden")


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
    # A phone held sideways, where the card is too short for its words and both button rows
    size_frame(driver, 844, 390)
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    press(driver, *[Keys.ARROW_LEFT, Keys.ARROW_UP, Keys.ARROW_RIGHT, Keys.ARROW_DOWN] * 4)
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Something went wrong')")
    assert saved_best(live, "2048") is None
    # Retry save is a button like Play again, in a row of its own, and it has the keyboard, so Enter can't start a new
    # round over the unsaved score. It shows above the last row, which stays on the card's bottom edge
    wait_for(driver, "document.activeElement.textContent === 'Retry save'", timeout=3)
    look = driver.execute_script(RETRY_LOOK)
    assert look["inRow"] and look["height"] >= 42 and look["shown"], look
    assert look["retry"] == look["again"] and look["retry"]["radius"] == "12px", look
    click_screen_button(driver, "Retry save")
    wait_for(driver, f"{SCREEN_TEXT}.includes('New best!')")
    assert len(calls) == 2 and calls[0] == calls[1]
    assert saved_best(live, "2048")["score"] > 0


# The finish request fails the way it does with no network, inside the game's frame, so the save fails at once
NO_NETWORK_FOR_FINISH = """
const real = window.fetch;
window.fetch = (url, init) =>
  String(url).endsWith('/api/finish') ? Promise.reject(new TypeError('Failed to fetch')) : real(url, init);
"""


def test_a_save_with_no_network_gives_retry_save_the_keyboard_on_a_sideways_phone(driver, live):
    open_game(driver, live, "2048")
    # Discord's sideways phone app, whose buttons take the top and left edges
    set_safe_area(driver, top="30px", left="33px")
    size_frame(driver, 844, 390)
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    press(driver, *ARROWS * 2)
    driver.execute_script(NO_NETWORK_FOR_FINISH)
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    # A save failing before the card's first frame still gives Retry save the keyboard, and the card raises it clear of
    # the button row
    wait_for(driver, "document.activeElement.textContent === 'Retry save'", timeout=3)
    wait_ms(driver, 300)
    card = driver.execute_script(
        "const c = document.querySelector('.arcade-card'); const b = document.activeElement.getBoundingClientRect();"
        "const row = c.querySelector(':scope > .arcade-actions:last-child').getBoundingClientRect();"
        "return [c.scrollHeight > c.clientHeight + 1, row.top - b.bottom, b.top >= c.getBoundingClientRect().top]"
    )
    # Retry save and its focus ring sit clear of the button row fixed under it, inside the card
    assert card[0] and card[1] >= 4 and card[2], card


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


# The words sdk.js gives a request that got no answer
UNREACHABLE = "Couldn't reach the bot. Check your connection and try again."
# The start request fails the way it does with no network, inside the game's frame
NO_NETWORK_FOR_START = """
const real = window.fetch;
window.fetch = (url, init) =>
  String(url).endsWith('/api/start') ? Promise.reject(new TypeError('Failed to fetch')) : real(url, init);
"""


def test_a_start_with_no_network_says_so_once(driver, live):
    open_game(driver, live, "2048")
    driver.execute_script(NO_NETWORK_FOR_START)
    click_screen_button(driver, "Play")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Try again')")
    # sdk.js's own words already say what happened, so nothing goes in front of them
    status = driver.execute_script("return document.querySelector('.arcade-screen .arcade-error').textContent")
    assert status == UNREACHABLE


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
    wait_for(driver, "document.querySelectorAll('.arcade-live li').length === 2")
    start_round(driver)
    play_until(driver, "window.notes.length > 0")
    note = driver.execute_script("return window.notes[0]")
    assert note["text"].startswith("You passed M")
    assert note["width"] <= driver.execute_script("return document.getElementById('stage').clientWidth") - 16
    # The first points (4 or more) pass both at once. Each name is cut to eleven characters and "…", as in the strip,
    # so the second name still shows
    assert "M" * 11 + "…" in note["text"] and "M" * 12 not in note["text"], note
    assert "A" * 11 + "…" in note["text"] and "A" * 12 not in note["text"], note


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
PAYOUT_COLOR = "getComputedStyle(document.querySelector('.arcade-payouts-status')).color"
# The arcade's muted gray and error red (--arcade-muted, --arcade-bad)
MUTED = "rgb(154, 164, 184)"
ERROR_RED = "rgb(252, 129, 129)"
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
  mute: place('.arcade-bar .arcade-sound'),
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
    assert driver.execute_script(f"return {PAYOUT_COLOR}") == MUTED
    wait_for(driver, f"{PAYOUT_STATUS} === 'Saved.'")
    assert driver.execute_script(f"return {PAYOUT_COLOR}") == MUTED
    assert not driver.execute_script(f"return {SAVE_BUTTON}.disabled")
    assert live.hub.config.guilds[GUILD_ID]["payouts"] == {"snake": {"on": True, "rate": 2.5, "cap": 1000, "plays": 3}}
    # A bad number is refused with the bot's reason in the error red, nothing changes, and Save works again
    plays = driver.find_element(By.CSS_SELECTOR, 'dialog.arcade-payouts input[data-field="plays"]')
    plays.send_keys(Keys.BACKSPACE)
    click_dialog_button(driver, "Save")
    assert driver.execute_script(f"return {SAVE_BUTTON}.disabled")
    wait_for(driver, f"{PAYOUT_STATUS}.includes('cash-ins a day')")
    assert driver.execute_script(f"return {PAYOUT_COLOR}") == ERROR_RED
    assert not driver.execute_script(f"return {SAVE_BUTTON}.disabled")
    assert live.hub.config.guilds[GUILD_ID]["payouts"]["snake"]["plays"] == 3
    # The red goes with the refusal: the dialog opens plain again
    click_dialog_button(driver, "Close")
    wait_for(driver, f"!{DIALOG}.open")
    open_payouts(driver)
    assert driver.execute_script(f"return {PAYOUT_STATUS}") == ""
    assert driver.execute_script(f"return {PAYOUT_COLOR}") == MUTED
    # Reset shows the defaults, and Close throws away what wasn't saved
    click_dialog_button(driver, "Reset to defaults")
    assert driver.execute_script(f"return {RATE_BOX}") == "25"
    assert driver.execute_script(f"return {PAYOUT_COLOR}") == MUTED
    click_dialog_button(driver, "Close")
    wait_for(driver, f"!{DIALOG}.open")
    open_payouts(driver)
    assert driver.execute_script(f"return {RATE_BOX}") == "2.5"


def test_the_gear_shows_only_between_rounds(driver, live):
    live.hub.config.guild_from_id(GUILD_ID).data["payouts"] = {"2048": {"on": True, "rate": 1, "cap": 50, "plays": 3}}
    live.user_id = MANAGER_ID
    open_game(driver, live, "2048")
    # The frame's default 150 px height leaves the results card little more than its button row
    size_frame(driver, 640)
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


# ---------- Phones, touch and the screen's edges ----------


@contextlib.contextmanager
def touch_screen(driver):
    """A phone: touch events, and the pointer: coarse and hover: none its browser reports. Put back afterwards, since
    every test in this file shares the browser"""
    driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
    features = [{"name": "pointer", "value": "coarse"}, {"name": "hover", "value": "none"}]
    driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"features": features})
    try:
        yield
    finally:
        driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"features": []})
        driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": False})


def touch_if_phone(driver, width):
    return touch_screen(driver) if width < 1000 else contextlib.nullcontext()


def add_members(live, user_ids, key=None):
    """More people in the test server. With a game's key, each has a best score in it, so its board fills up"""
    guild = live.hub.bot.guilds[GUILD_ID]
    for i, user_id in enumerate(user_ids):
        user = fake_user(user_id, f"visitor{user_id}")
        user.display_avatar.url = OFFLINE_AVATAR
        live.hub.bot.users[user_id] = user
        guild.members[user_id] = fake_member(user, guild)
        if key:
            live.hub.config.member_from_ids(GUILD_ID, user_id).data["best"] = {key: {"score": 1000 - i, "at": i}}


def finish_with_offer(live, monkeypatch, key):
    """Every finish of the game answers with the server's board, a new best and a cash-in offer, whatever the round"""

    async def finish(ctx, data):
        board = await live.hub.scores.board(ctx.guild, ctx.author, key)
        offer = {"worth": 50, "left": 3, "plays": 3, "currency": "credits"}
        return {"score": 50, "best": 50, "newBest": True, "board": board, "offer": offer}

    monkeypatch.setitem(live.hub.registry.games[key].actions, "finish", finish)


def end_round(driver):
    """Start a round of the open game and end it from the pause card"""
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN})")
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")


# The open card's last button row, at the card's top and scrolled to its end: whether each button shows whole in the
# window and answers a hit test at its middle, and whether its focus ring has room inside the card. Also whether the
# card opened at its top with its heading showing, and which button has the keyboard. A button shows whole when hit
# tests near its top, at its middle and near its bottom all find it
CARD_FIT = """
const card = document.querySelector('.arcade-card');
const box = card.getBoundingClientRect();
const row = card.querySelector(':scope > .arcade-actions:last-child');
const shows = (b) => {
  const r = b.getBoundingClientRect();
  const hits = [r.top + 2, r.top + r.height / 2, r.bottom - 2].every(
    (y) => document.elementFromPoint(r.left + r.width / 2, y) === b,
  );
  return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth && hits;
};
const buttons = () => [...row.querySelectorAll('button')].map((b) => {
  const r = b.getBoundingClientRect();
  return { text: b.textContent, shown: shows(b), ring: r.top - 4 >= box.top && r.bottom + 4 <= box.bottom - 1 };
});
const top = {
  scrolls: card.scrollHeight > card.clientHeight + 1,
  scrollTop: card.scrollTop,
  heading: card.querySelector('h1').getBoundingClientRect().top >= box.top,
  focus: document.activeElement.textContent,
  focusShown: shows(document.activeElement),
  focusGap: row.getBoundingClientRect().top - document.activeElement.getBoundingClientRect().bottom - 4,
};
card.scrollTop = 0;
top.buttons = buttons();
const rowTop = row.getBoundingClientRect().top;
card.scrollTop = card.scrollHeight;
const end = { buttons: buttons(), rowMoved: Math.abs(row.getBoundingClientRect().top - rowTop) };
card.scrollTop = 0;
return { top, end };
"""


def check_card(driver, names, focus):
    """The open card is taller than its room, with the keyboard on focus and that button showing whole. It opened at its
    top with its heading showing, or raised just far enough to clear the focused button and its ring from the button
    row. The row stays whole in view while the rest scrolls under it"""
    found = driver.execute_script(CARD_FIT)
    top, end = found["top"], found["end"]
    assert top["scrolls"] and top["focus"] == focus and top["focusShown"], found
    # At the card's very end the row is back in its own place, where the ring may sit up to its 4 px under it
    assert (top["scrollTop"] == 0 and top["heading"]) or -4 <= top["focusGap"] < 1, found
    for state in (top, end):
        assert [button["text"] for button in state["buttons"]] == names, found
        assert all(button["shown"] and button["ring"] for button in state["buttons"]), found
    assert end["rowMoved"] < 1, found


@pytest.mark.parametrize("game", GAMES)
def test_a_card_too_tall_for_the_screen_keeps_its_buttons_in_view(driver, live, monkeypatch, game):
    add_members(live, range(100, 110), key=game)
    finish_with_offer(live, monkeypatch, game)
    open_game(driver, live, game)
    size_frame(driver, 844, 390)
    click_screen_button(driver, "Leaderboard")
    wait_for(driver, "document.querySelector('.arcade-board')")
    wait_ms(driver, 250)
    check_card(driver, ["Back"], "Back")
    click_screen_button(driver, "Back")
    end_round(driver)
    # The board and the offer arrive with the save, above Play again, and the keyboard then goes to the first button,
    # Cash in, without scrolling the card
    wait_for(driver, "document.querySelector('.arcade-board') && document.querySelector('.arcade-offer')")
    wait_ms(driver, 250)
    check_card(driver, ["Play again", "Menu"], "Cash in 50")
    size_frame(driver, 1280, 800)
    wait_ms(driver, 100)
    check_card(driver, ["Play again", "Menu"], "Cash in 50")
    # A frame too short for much more than the row keeps it on the card's edge too
    size_frame(driver, 480, 270)
    click_screen_button(driver, "Play again")
    wait_for(driver, f"!({SCREEN_OPEN})")
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    wait_for(driver, "document.querySelector('.arcade-board') && document.querySelector('.arcade-offer')")
    wait_ms(driver, 250)
    check_card(driver, ["Play again", "Menu"], "Cash in 50")


# Shows the passing note, and says whether it covers the playfield or the arrow pad, and whether it is in the window
PASS_FIT = """
const note = document.querySelector('.arcade-pass');
note.textContent = 'You passed Manager and Admin!';
note.hidden = false;
const box = note.getBoundingClientRect();
const covers = [...document.querySelectorAll('#board, #game, #dpad:not([hidden])')].some((field) => {
  const r = field.getBoundingClientRect();
  return box.bottom > r.top && box.top < r.bottom && box.right > r.left && box.left < r.right;
});
return { covers, inside: box.top >= 0 && box.left >= 0 && box.right <= innerWidth && box.bottom <= innerHeight };
"""
# Whether a hit test at the middle of the hub's arrival note finds the note. A note takes no clicks, which would let a
# hit test see straight through it, so it takes them for this
NOTE_ON_TOP = """
const note = document.querySelector('.hub-note');
note.style.pointerEvents = 'auto';
const box = note.getBoundingClientRect();
return note.contains(document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2));
"""


def arrive(driver, live, user_id, game):
    """Someone new comes into the game, and a fresh note about it shows under the game's people button. Arrivals close
    together share one note, so it may name someone else first"""
    in_host(driver, "window.testHost.presence.quietUntil = 0")
    driver.execute_script("window.oldNote = document.querySelector('.hub-note')")
    live.add_person(user_id, where=game, status="Getting ready", data={"state": "idle"})
    wait_for(
        driver,
        "document.querySelector('.hub-note') !== window.oldNote && document.querySelector('.hub-note')?.textContent",
    )


@pytest.mark.parametrize("game", GAMES)
def test_the_passing_note_and_arrival_notes_stay_off_the_game(driver, live, game):
    add_members(live, [200, 201, 202, 203])
    open_game(driver, live, game)
    for user_id, score in [(MANAGER_ID, 500), (ADMIN_ID, 400), (OWNER_ID, 300), (GUILD_OWNER_ID, 200)]:
        live.add_person(user_id, where=game, status="Scored", data={"state": "over", "score": score})
    wait_for(driver, "!document.querySelector('.arcade-live').hidden")
    # The title card dims everything below the bar, but not the arrival note hanging out of it
    size_frame(driver, 1280, 800)
    arrive(driver, live, 200, game)
    assert driver.execute_script(NOTE_ON_TOP)
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN})")
    for (width, height), user_id in zip([(1280, 800), (390, 844), (844, 390)], [201, 202, 203]):
        with touch_if_phone(driver, width):
            size_frame(driver, width, height)
            wait_ms(driver, 200)
            arrive(driver, live, user_id, game)
            found = driver.execute_script(PASS_FIT)
            assert not found["covers"] and found["inside"], (width, height, found)
            assert driver.execute_script(NOTE_ON_TOP), (width, height)


# For each top bar button showing: whether hit tests 21 px above and below its middle, at its middle and near both its
# ends, all find that button, and none of them its neighbour
TAP_AREAS = """
return [...document.querySelectorAll('.arcade-back, .arcade-bar .arcade-icon, .arcade-bar .hub-people-button')]
  .filter((b) => b.offsetParent !== null)
  .map((b) => {
    const r = b.getBoundingClientRect();
    const middle = r.top + r.height / 2;
    const finds = (x, y) => b.contains(document.elementFromPoint(x, y));
    const xs = [r.left + 1, r.left + r.width / 2, r.right - 1];
    const ok = xs.every((x) => finds(x, middle - 21) && finds(x, middle + 21));
    return { name: b.getAttribute('aria-label') || b.textContent, ok };
  });
"""


@pytest.mark.parametrize("game", GAMES)
def test_every_top_bar_button_has_a_finger_sized_tap_area(driver, live, game):
    live.user_id = MANAGER_ID
    open_game(driver, live, game)
    with touch_screen(driver):
        # Before the first move the gear shows beside pause: the bar's five buttons
        click_screen_button(driver, "Play")
        wait_for(driver, f"!({SCREEN_OPEN})")
        for width, height in [(390, 844), (844, 390), (320, 640)]:
            size_frame(driver, width, height)
            wait_ms(driver, 100)
            areas = driver.execute_script(TAP_AREAS)
            assert len(areas) == 5 and all(area["ok"] for area in areas), (width, height, areas)
        # A touch screen has no Esc or P to name: Resume is right there
        driver.find_element(By.CSS_SELECTOR, ".arcade-bar .arcade-icon[aria-label='Pause']").click()
        wait_for(driver, f"{SCREEN_TEXT}.includes('Paused')")
        assert "Esc" not in driver.execute_script(f"return {SCREEN_TEXT}")


PRESS_LOOK = (
    "const s = getComputedStyle(document.querySelector(arguments[0])); return [s.backgroundColor, s.transform];"
)
BAR_BUTTONS = [
    ".arcade-back",
    ".arcade-bar .hub-people-button",
    GEAR,
    ".arcade-bar .arcade-sound",
    ".arcade-bar .arcade-icon[aria-label='Pause']",
]


def test_top_bar_buttons_show_a_press_on_a_touch_screen(driver, live):
    live.user_id = MANAGER_ID
    open_game(driver, live, "2048")
    size_frame(driver, 390, 700)
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    WebDriverWait(driver, 5).until(shown_gear)
    with touch_screen(driver):
        for selector in BAR_BUTTONS:
            idle = driver.execute_script(PRESS_LOOK, selector)
            button = driver.find_element(By.CSS_SELECTOR, selector)
            ActionChains(driver).move_to_element(button).click_and_hold().perform()
            wait_ms(driver, 200)
            held = driver.execute_script(PRESS_LOOK, selector)
            # Slid off before lifting, so the press doesn't click
            ActionChains(driver).move_by_offset(0, 300).release().perform()
            wait_ms(driver, 200)
            assert held[0] != idle[0] and held[1] == "matrix(0.94, 0, 0, 0.94, 0, 0)", (selector, idle, held)
            assert driver.execute_script(PRESS_LOOK, selector) == idle, selector


def open_game_sized(driver, live, key, width, height):
    """open_game, with the game's frame at this size before its page loads"""
    driver.get(f"{live.url}/{DISCORD_QUERY}")
    assert wait_for(driver, "document.body.dataset.login") == "online"
    driver.execute_script(
        f"window.testHost.openGame('{key}');"
        f"document.getElementById('game-frame').style.cssText = 'width: {width}px; height: {height}px'"
    )
    wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "document.querySelector('.arcade-screen button.primary')")


# The open card's top edge in the window, leaving out the transform of its opening animation
CARD_TOP = """
const card = document.querySelector('.arcade-card');
return card.offsetTop + card.offsetParent.getBoundingClientRect().top;
"""
CONTROLS_CENTRE = """
const card = document.querySelector('.arcade-card').getBoundingClientRect();
const list = document.querySelector('.arcade-controls').getBoundingClientRect();
return { card: card.left + card.width / 2, controls: list.left + list.width / 2 };
"""
KEY_EDGES = """
return [...document.querySelectorAll('.arcade-controls kbd')].map((k) => Math.round(k.getBoundingClientRect().right));
"""


@pytest.mark.parametrize("game", GAMES)
def test_the_title_card_holds_still_and_centres_its_controls(driver, live, monkeypatch, game):
    real_board = live.hub.registry.games[game].actions["board"]

    async def slow_board(ctx, data):
        await asyncio.sleep(0.6)
        return await real_board(ctx, data)

    monkeypatch.setitem(live.hub.registry.games[game].actions, "board", slow_board)
    for width, height in [(1280, 800), (390, 844), (844, 390)]:
        with touch_if_phone(driver, width):
            open_game_sized(driver, live, game, width, height)
            first = driver.execute_script(CARD_TOP)
            assert "No score here yet" not in driver.execute_script(f"return {SCREEN_TEXT}")
            # The player's standing arrives a moment later, in a line that already held its place
            wait_for(driver, f"{SCREEN_TEXT}.includes('No score here yet')")
            assert abs(driver.execute_script(CARD_TOP) - first) <= 2, (width, height)
            if width == 390:
                centres = driver.execute_script(CONTROLS_CENTRE)
                assert abs(centres["controls"] - centres["card"]) <= 2, centres
            elif width == 1280:
                # The keys still line up on their right
                assert len(set(driver.execute_script(KEY_EDGES))) == 1


# The open card, where it sits, its buttons, and how many animations are running on it
CARD_STATE = """
const card = document.querySelector('.arcade-card');
return {
  same: card === window.cardBefore,
  place: [card.offsetTop, card.offsetHeight],
  buttons: [...card.querySelectorAll('button')].map((b) => [b.textContent, b.disabled]),
  animations: card.getAnimations().length,
};
"""
REMEMBER_CARD = """
window.cardBefore = document.querySelector('.arcade-card');
return [window.cardBefore.offsetTop, window.cardBefore.offsetHeight];
"""


def press_while_a_round_starts(driver, text):
    """Press a card's button that starts a round, and check the card stays put while it starts"""
    # Past the card's own opening animation
    wait_ms(driver, 300)
    place = driver.execute_script(REMEMBER_CARD)
    click_screen_button(driver, text)
    found = driver.execute_script(CARD_STATE)
    assert found["same"] and found["animations"] == 0 and found["place"] == place, found
    assert ["Starting...", True] in found["buttons"] and all(off for _, off in found["buttons"]), found


def test_a_starting_round_keeps_its_card(driver, live, monkeypatch):
    game = live.hub.registry.games["2048"]
    real_start = game.actions["start"]
    calls = []

    async def slow_start(ctx, data):
        calls.append(1)
        await asyncio.sleep(0.6)
        if len(calls) == 2:
            raise RuntimeError("the bot hiccuped before starting the round")
        return await real_start(ctx, data)

    monkeypatch.setitem(game.actions, "start", slow_start)
    open_game(driver, live, "2048")
    press_while_a_round_starts(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN})")
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    wait_for(driver, f"!{SCREEN_TEXT}.includes('Saving')")
    press_while_a_round_starts(driver, "Play again")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Try again')")
    press_while_a_round_starts(driver, "Try again")
    wait_for(driver, f"!({SCREEN_OPEN})")


SAVING_CARD = f"{SCREEN_OPEN} && {SCREEN_TEXT}"
# Every text the screen shows from here on, kept on the menu page, which outlives the game's frame
RECORD_SCREEN = """
window.parent.screenTexts = [];
const screen = document.querySelector('.arcade-screen');
new MutationObserver(() => window.parent.screenTexts.push(screen.innerText))
  .observe(screen, { childList: true, subtree: true, characterData: true });
"""


def wait_closed(driver):
    driver.switch_to.default_content()
    wait_for(driver, "document.body.dataset.closed === '1'")


def test_menu_shows_a_card_while_the_score_saves(driver, live, monkeypatch):
    record_finishes(live, monkeypatch, "2048", delay=2)
    # Mid-round, with points to save
    open_game(driver, live, "2048")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    play_until(driver, f"{SCORE} > 0")
    driver.find_element(By.CSS_SELECTOR, ".arcade-back").click()
    wait_ms(driver, 100)
    assert driver.execute_script(f"return {SAVING_CARD}") == "Saving your score..."
    wait_closed(driver)
    # From a results card whose save is still on its way
    open_game(driver, live, "2048")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Saving...')")
    click_screen_button(driver, "Menu")
    wait_ms(driver, 100)
    assert driver.execute_script(f"return {SAVING_CARD}") == "Saving your score..."
    wait_closed(driver)
    # Once the save has landed, Menu goes straight back
    open_game(driver, live, "2048")
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    press(driver, Keys.ESCAPE)
    click_screen_button(driver, "End round")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Game over') && !{SCREEN_TEXT}.includes('Saving')")
    driver.execute_script(RECORD_SCREEN)
    click_screen_button(driver, "Menu")
    wait_closed(driver)
    assert not any("Saving your score" in text for text in driver.execute_script("return window.screenTexts"))


def test_play_has_the_keyboard_when_a_game_opens(driver, live):
    open_game(driver, live, "2048")
    wait_for(driver, "document.activeElement.textContent === 'Play'", timeout=3)
    # The next game opens in a new frame, with the player already logged in
    driver.switch_to.default_content()
    driver.execute_script("window.testHost.openGame('snake')")
    wait_for(driver, "document.getElementById('game-frame')?.title === 'snake'")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "document.querySelector('.arcade-screen button.primary')")
    wait_for(driver, "document.activeElement.textContent === 'Play'", timeout=3)
    press(driver, Keys.ENTER)
    wait_for(driver, f"!({SCREEN_OPEN})")


# Banners as the games show them, put on the stage by hand so a test needn't fill a board or clear a level, and for
# each, its title's lines, its width and the room it has
BANNERS = """
const stage = document.getElementById('stage');
const lines = (node) => {
  const range = document.createRange();
  range.selectNodeContents(node);
  return range.getClientRects().length;
};
const banners = [['You filled the board!', ''], ['Level cleared!', '+100 points. Level 2 is next.'], ['Extra life', '']];
return banners.map(([title, subtitle]) => {
  const node = document.createElement('div');
  node.className = 'arcade-banner';
  const strong = document.createElement('strong');
  strong.textContent = title;
  node.append(strong);
  if (subtitle) {
    const span = document.createElement('span');
    span.textContent = subtitle;
    node.append(span);
  }
  stage.append(node);
  const found = { title, lines: lines(strong), width: node.offsetWidth, room: stage.clientWidth - 32 };
  node.remove();
  return found;
});
"""
HINT_LINES = """
const hint = document.querySelector('.arcade-hint');
const range = document.createRange();
range.selectNodeContents(hint);
return { lines: range.getClientRects().length, width: hint.offsetWidth, room: hint.parentElement.clientWidth - 32 };
"""


def test_hints_and_banners_sit_on_one_line_on_a_phone(driver, live):
    open_game(driver, live, "snake")
    with touch_screen(driver):
        size_frame(driver, 390, 844)
        click_screen_button(driver, "Play")
        wait_for(driver, f"{HINT}.textContent === 'Tap an arrow or swipe to start'")
        hint = driver.execute_script(HINT_LINES)
        assert hint["lines"] == 1 and hint["width"] <= hint["room"], hint
        for banner in driver.execute_script(BANNERS):
            assert banner["lines"] == 1 and banner["width"] <= banner["room"], banner


# The boxes of Snake's hint, a banner put on the stage by hand, its board, its arrow pad and its stage, and how many
# lines the hint takes
OVER_THE_BOARD = """
const stage = document.getElementById('stage');
const banner = document.createElement('div');
banner.className = 'arcade-banner';
banner.style.animation = 'none';
const strong = document.createElement('strong');
strong.textContent = 'You filled the board!';
banner.append(strong);
stage.append(banner);
const box = (node) => {
  const r = node.getBoundingClientRect();
  return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, middle: r.left + r.width / 2 };
};
const pad = document.getElementById('dpad');
const range = document.createRange();
range.selectNodeContents(document.querySelector('.arcade-hint'));
const found = {
  hint: box(document.querySelector('.arcade-hint')),
  hintLines: range.getClientRects().length,
  banner: box(banner),
  board: box(document.getElementById('board')),
  pad: pad.hidden ? null : box(pad),
  stage: box(stage),
};
banner.remove();
return found;
"""


@pytest.mark.parametrize(
    ("width", "height", "others"), [(1280, 800, False), (390, 844, False), (844, 390, False), (844, 390, True)]
)
def test_snakes_hint_and_banner_sit_over_its_board(driver, live, width, height, others):
    open_game(driver, live, "snake")
    if others:
        # The row of scores above the game takes height from the stage, and so width from the board
        for user_id, score in [(MANAGER_ID, 500), (ADMIN_ID, 400), (OWNER_ID, 300)]:
            live.add_person(user_id, where="snake", status="Scored", data={"state": "over", "score": score})
        wait_for(driver, "!document.querySelector('.arcade-live').hidden")
    with touch_if_phone(driver, width):
        size_frame(driver, width, height)
        click_screen_button(driver, "Play")
        wait_for(driver, f"{WAITING['snake']} && !({SCREEN_OPEN})")
        found = driver.execute_script(OVER_THE_BOARD)
    board, pad = found["board"], found["pad"]
    assert found["hintLines"] == 1, found
    for name in ("hint", "banner"):
        part = found[name]
        assert board["left"] <= part["left"] and part["right"] <= board["right"], (name, found)
        if pad:
            apart = part["right"] <= pad["left"] or part["bottom"] <= pad["top"] or part["top"] >= pad["bottom"]
            assert apart, (name, found)
        if width < height or not pad:
            # Upright and on a computer the board is in the middle of the stage, and so are they
            assert abs(part["middle"] - found["stage"]["middle"]) <= 1, (name, found)


@pytest.mark.parametrize(("game", "words"), [("brickbreaker", "to launch"), ("snake", "to start")])
def test_the_hint_hides_under_the_paused_card(driver, live, game, words):
    open_game(driver, live, game)
    click_screen_button(driver, "Play")
    wait_for(driver, f"!{HINT}.hidden && {HINT}.textContent.includes('{words}')")
    visibility = f"return getComputedStyle({HINT}).visibility"
    assert driver.execute_script(visibility) == "visible"
    # Paused, the card's own buttons are the only instructions
    press(driver, "p")
    wait_for(driver, f"{SCREEN_TEXT}.includes('Paused')")
    assert driver.execute_script(visibility) == "hidden"
    click_screen_button(driver, "Resume")
    wait_for(driver, f"!({SCREEN_OPEN})")
    assert driver.execute_script(visibility) == "visible"


OPEN_PAYOUTS_ANIMATIONS = """
document.querySelector('.arcade-payouts-open').click();
return document.querySelector('dialog.arcade-payouts').getAnimations().map((a) => a.animationName);
"""


def test_the_payout_dialog_opens_like_a_card(driver, live):
    live.user_id = MANAGER_ID
    open_game(driver, live, "snake")
    WebDriverWait(driver, 5).until(shown_gear)
    assert driver.execute_script(OPEN_PAYOUTS_ANIMATIONS) == ["card-in"]
    click_dialog_button(driver, "Close")
    wait_for(driver, f"!{DIALOG}.open")
    reduce = [{"name": "prefers-reduced-motion", "value": "reduce"}]
    driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"features": reduce})
    try:
        assert driver.execute_script(OPEN_PAYOUTS_ANIMATIONS) == []
    finally:
        driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"features": []})


# ---------- Sound ----------

SOUND = ".arcade-bar .arcade-sound"
SOUND_PANEL = "document.querySelector('.arcade-sound-panel')"
SOUND_SWITCH = "document.querySelector('.arcade-sound-panel input[type=checkbox]')"
VOLUME = "Number(document.querySelector('.arcade-volume').value)"
# Where the sound panel sits, what it holds, and whether a hit test at its middle finds it
PANEL_FIT = """
const panel = document.querySelector('.arcade-sound-panel');
const box = panel.getBoundingClientRect();
const toggle = panel.querySelector('.arcade-switch');
const slider = panel.querySelector('input[type=range]');
return {
  shown: !panel.hidden,
  inside: box.left >= 0 && box.top >= 0 && box.right <= innerWidth && box.bottom <= innerHeight,
  hit: panel.contains(document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)),
  label: toggle.textContent,
  on: toggle.querySelector('input').checked,
  sliderUnder: slider.getBoundingClientRect().top >= toggle.getBoundingClientRect().bottom,
  value: Number(slider.value),
};
"""
# Where the game's frame starts on the menu page, which is where the browser counts touch points from
FRAME_ORIGIN = """
const frame = document.getElementById('game-frame');
const box = frame.getBoundingClientRect();
return [box.left + frame.clientLeft, box.top + frame.clientTop];
"""
ELEMENT_BOX = (
    "const r = document.querySelector(arguments[0]).getBoundingClientRect(); return [r.left, r.top, r.width, r.height]"
)
# Whether the open game's round is still waiting for its first move
WAITING = {
    "2048": f"document.querySelectorAll('.tile').length === 2 && {SCORE} === 0",
    "snake": f"!{HINT}.hidden && {HINT}.textContent.includes('to start')",
    "brickbreaker": f"!{HINT}.hidden && {HINT}.textContent.includes('to launch')",
}


def finger_slide(driver, selector, start, end):
    """A finger pressed on the element at start (0 to 1 across it), slid to end, then lifted"""
    box = driver.execute_script(ELEMENT_BOX, selector)
    left, top = in_host(driver, FRAME_ORIGIN)
    y = top + box[1] + box[3] / 2
    xs = [left + box[0] + box[2] * (start + (end - start) * step / 8) for step in range(9)]
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": xs[0], "y": y}]})
    for x in xs[1:]:
        driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y}]})
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


@pytest.mark.parametrize("game", GAMES)
def test_the_sound_button_opens_a_switch_and_a_volume_slider(driver, live, game):
    driver.set_window_size(1400, 1000)
    open_game(driver, live, game)
    # It opens whole in the window at every size, and a second press closes it
    for width, height in [(1280, 800), (390, 844), (844, 390)]:
        size_frame(driver, width, height)
        driver.find_element(By.CSS_SELECTOR, SOUND).click()
        found = driver.execute_script(PANEL_FIT)
        assert found["shown"] and found["inside"] and found["hit"] and found["sliderUnder"], (width, height, found)
        assert found["label"] == "Sound effects" and found["on"] and found["value"] == 100, found
        driver.find_element(By.CSS_SELECTOR, SOUND).click()
        assert driver.execute_script(f"return {SOUND_PANEL}.hidden")
    # A mouse drags the slider from its full end to about half, and a press anywhere else closes the panel
    size_frame(driver, 1280, 800)
    driver.find_element(By.CSS_SELECTOR, SOUND).click()
    slider = driver.find_element(By.CSS_SELECTOR, ".arcade-volume")
    half = slider.size["width"] // 2
    drag = ActionChains(driver).move_to_element_with_offset(slider, half - 3, 0).click_and_hold()
    drag.move_by_offset(-half + 3, 0).release().perform()
    assert 40 <= driver.execute_script(f"return {VOLUME}") <= 60
    screen = driver.find_element(By.CSS_SELECTOR, ".arcade-screen")
    ActionChains(driver).move_to_element_with_offset(screen, -600, 300).click().perform()
    assert driver.execute_script(f"return {SOUND_PANEL}.hidden")
    # Opening it in a round waiting for its first move doesn't start, steer or pause it, and arrow keys on the
    # slider move only the slider
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN}) && {WAITING[game]}")
    driver.find_element(By.CSS_SELECTOR, SOUND).click()
    driver.execute_script(COUNT_KEYS)
    driver.execute_script("document.querySelector('.arcade-volume').focus()")
    before = driver.execute_script(f"return {VOLUME}")
    press(driver, Keys.ARROW_LEFT, Keys.ARROW_LEFT, Keys.ARROW_UP, Keys.ARROW_RIGHT, Keys.ARROW_DOWN, Keys.ARROW_LEFT)
    wait_ms(driver, 300)
    assert driver.execute_script(f"return {VOLUME}") == before - 2
    assert driver.execute_script(f"return window.gameKeys === 0 && !({SCREEN_OPEN}) && {WAITING[game]}")
    # M still flips the switch
    driver.execute_script("document.activeElement.blur()")
    press(driver, "m")
    assert driver.execute_script(f"return {SOUND_SWITCH}.checked") is False
    # A finger drags it too
    with touch_screen(driver):
        size_frame(driver, 390, 844)
        finger_slide(driver, ".arcade-volume", 0.9, 0.3)
        level = driver.execute_script(f"return {VOLUME}")
        assert 15 <= level <= 45, level
    # The level and the switch are kept on this device
    open_game(driver, live, game)
    driver.find_element(By.CSS_SELECTOR, SOUND).click()
    assert driver.execute_script(f"return [{VOLUME}, {SOUND_SWITCH}.checked]") == [level, False]


def test_escape_on_the_sound_panel_gives_the_keyboard_back_to_the_game(driver, live):
    open_game(driver, live, "brickbreaker")
    size_frame(driver, 1280, 800)
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN}) && {WAITING['brickbreaker']}")
    driver.find_element(By.CSS_SELECTOR, SOUND).click()
    driver.find_element(By.CSS_SELECTOR, ".arcade-volume").click()
    assert driver.execute_script("return document.activeElement.className") == "arcade-volume"
    # Escape only closes the panel. No bar button keeps the keyboard, so the next Space launches the ball and nothing
    # else, and the round isn't paused
    press(driver, Keys.ESCAPE)
    assert driver.execute_script(f"return {SOUND_PANEL}.hidden && !document.activeElement.closest('.arcade-bar')")
    assert driver.execute_script(f"return !({SCREEN_OPEN})")
    press(driver, Keys.SPACE)
    wait_for(driver, f"{HINT}.hidden")
    assert driver.execute_script(f"return {SOUND_PANEL}.hidden && !({SCREEN_OPEN})")


def test_a_clicked_sound_switch_keeps_only_space_from_the_game(driver, live):
    open_game(driver, live, "snake")
    size_frame(driver, 1280, 800)
    click_screen_button(driver, "Play")
    wait_for(driver, f"!({SCREEN_OPEN}) && {WAITING['snake']}")
    driver.find_element(By.CSS_SELECTOR, SOUND).click()
    driver.find_element(By.CSS_SELECTOR, ".arcade-switch span").click()
    assert driver.execute_script(f"return [document.activeElement.type, {SOUND_SWITCH}.checked]") == ["checkbox", False]
    driver.execute_script(COUNT_KEYS)
    # Space flips the switch back and goes no further. An arrow key starts the round and P pauses it
    press(driver, Keys.SPACE)
    assert driver.execute_script(f"return [{SOUND_SWITCH}.checked, window.gameKeys]") == [True, 0]
    press(driver, Keys.ARROW_UP)
    wait_for(driver, f"{HINT}.hidden")
    press(driver, "p")
    wait_for(driver, SCREEN_OPEN)
    assert driver.execute_script("return window.gameKeys") == 2


# Each tone's starting volume and each oscillator made, recorded in the game's frame
SPY_ON_TONES = """
window.gains = [];
window.oscillators = 0;
const realSet = AudioParam.prototype.setValueAtTime;
AudioParam.prototype.setValueAtTime = function (value, time) {
  window.gains.push(value);
  return realSet.call(this, value, time);
};
const realOscillator = AudioContext.prototype.createOscillator;
AudioContext.prototype.createOscillator = function () {
  window.oscillators += 1;
  return realOscillator.call(this);
};
"""
SET_VOLUME = """
const slider = document.querySelector('.arcade-volume');
slider.value = String(arguments[0]);
slider.dispatchEvent(new Event('input'));
"""


def test_the_volume_scales_every_tone_and_the_switch_silences_them(driver, live):
    open_game(driver, live, "2048")
    driver.execute_script(SPY_ON_TONES)
    driver.execute_script(SET_VOLUME, 50)
    click_screen_button(driver, "Play")
    wait_for(driver, "document.querySelectorAll('.tile').length === 2")
    play_until(driver, "window.oscillators >= 4")
    # A slide's tone starts at 0.04 and a merge's at 0.09 at full volume: half that at 50. The rest are pitches
    gains = {round(value, 4) for value in driver.execute_script("return window.gains") if value < 1}
    assert gains and gains <= {0.02, 0.045}, gains
    driver.execute_script(f"{SOUND_SWITCH}.click()")
    made = driver.execute_script("return window.oscillators")
    press(driver, *ARROWS * 2)
    wait_ms(driver, 200)
    assert driver.execute_script("return window.oscillators") == made
