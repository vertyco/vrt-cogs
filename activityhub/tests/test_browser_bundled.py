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
    WebDriverWait(driver, 5).until(lambda d: me(live) and me(live).status == "Playing · 0" and me(live).busy)
    assert me(live).data == {"state": "playing", "score": 0}


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
            "(() => { const g = document.querySelector('#board, #game'); return g.getBoundingClientRect().height > 100; })()",
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
