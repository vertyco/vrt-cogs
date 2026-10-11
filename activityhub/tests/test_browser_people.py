import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from activityhub.tests.browser import (
    DISCORD_QUERY,
    TEST_HOST_PAGE,
    LiveHub,
    fresh,
    hub_web_copy,
    start_chrome,
    wait_for,
)
from activityhub.tests.fakes import ADMIN_ID, MANAGER_ID, DemoCog, make_hub, register, write_demo_web

# A game that places the people button in its own page, right after connect()
PLACED_JS = """import { connect } from "activityhub";
const hub = await connect();
document.body.append(hub.peopleButton());
window.demo = { done: true };
"""
FLOATING = "document.querySelector('.hub-people.floating')"
PANEL = "document.querySelector('.hub-people-panel')"
CONFIRM = "document.querySelector('.hub-confirm')"
PREVIEW = "Open this from Discord to see who's here."


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
    register(hub, DemoCog(write_demo_web(tmp_path / "demo")))
    placed = write_demo_web(tmp_path / "placed")
    (placed / "game.js").write_text(PLACED_JS, encoding="utf-8")
    register(hub, DemoCog(placed, key="placed", name="Placed", cog_name="Placed"))
    server = LiveHub(hub, hub_web_copy(tmp_path, index=TEST_HOST_PAGE))
    server.start()
    driver.set_window_size(1280, 800)
    fresh(driver, server)
    yield server
    server.stop()


def open_game(driver, live, key="demo"):
    driver.get(f"{live.url}/{DISCORD_QUERY}")
    assert wait_for(driver, "document.body.dataset.login") == "online"
    driver.execute_script(f"window.testHost.openGame('{key}')")
    wait_for(driver, "document.body.classList.contains('playing')")


def open_panel(driver):
    driver.execute_script("window.testHost.people.open()")
    # Past the panel's slide in, so a mouse aimed at a button lands on it
    wait_for(driver, f"getComputedStyle({PANEL}).transform === 'none'")


def person_status(driver, user_id, status):
    wait_for(driver, f"window.testHost.presence.people.find((p) => p.id === '{user_id}')?.status === '{status}'")


def ask_to_leave(driver, live):
    """The player is mid-round in demo, and the panel is open on someone in placed"""
    open_game(driver, live)
    live.add_person(ADMIN_ID, where="placed")
    wait_for(driver, "window.testHost.presence.people.length === 2")
    driver.execute_script("window.testHost.setBusy(true)")
    open_panel(driver)


def test_a_game_that_does_nothing_gets_the_floating_button(driver, live):
    open_game(driver, live)
    wait_for(driver, f"!{FLOATING}.hidden")
    # Alone in the window, the button offers an invite
    label = driver.execute_script(f"return {FLOATING}.querySelector('button').getAttribute('aria-label')")
    assert label == "Invite friends"
    live.add_person(MANAGER_ID, where="demo")
    wait_for(driver, f"{FLOATING}.querySelector('.hub-count')?.textContent === '1'")


def test_a_placed_button_replaces_the_floating_one(driver, live):
    open_game(driver, live, "placed")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "document.querySelector('.hub-people .hub-people-button')")
    driver.switch_to.default_content()
    # Past the floating button's fallback after the page loaded
    driver.execute_async_script("setTimeout(arguments[0], 2300)")
    assert driver.execute_script(f"return {FLOATING}.hidden") is True


def test_the_panel_groups_people_and_joins(driver, live):
    open_game(driver, live)
    live.add_person(MANAGER_ID, where="demo", status="Clicking")
    live.add_person(ADMIN_ID, where="placed", status="Busy")
    wait_for(driver, "window.testHost.presence.people.length === 3")
    driver.execute_script("window.testHost.people.open()")
    titles = wait_for(driver, f"[...{PANEL}.querySelectorAll('.hub-group-title')].map((h) => h.textContent)")
    assert titles[0] == "Here in demo" and titles[1].startswith("placed")
    rows = driver.execute_script(f"return [...{PANEL}.querySelectorAll('.hub-person')].map((r) => r.innerText)")
    assert any("Manager" in row and "Clicking" in row for row in rows)
    driver.execute_script(f"{PANEL}.querySelector('[data-join=\"{ADMIN_ID}\"]').click()")
    wait_for(driver, "window.testHost.gameKey === 'placed' && window.testHost.follow.id === '4'")
    assert driver.execute_script(f"return {PANEL}.hidden") is True


def test_join_asks_first_when_busy(driver, live):
    open_game(driver, live)
    live.add_person(ADMIN_ID, where="placed")
    wait_for(driver, "window.testHost.presence.people.length === 2")
    driver.execute_script("window.testHost.setBusy(true); window.testHost.people.open()")
    driver.execute_script(f"{PANEL}.querySelector('[data-join=\"{ADMIN_ID}\"]').click()")
    text = wait_for(
        driver,
        "!document.querySelector('.hub-confirm').hidden && document.querySelector('.hub-confirm-text').textContent",
    )
    # Each player name is set apart from the words around it
    assert text == "Leave demo to join \u2068Admin\u2069 in placed?"
    bidi = driver.execute_script("return getComputedStyle(document.querySelector('.hub-confirm-text')).unicodeBidi")
    assert bidi == "isolate"
    assert driver.execute_script("return document.activeElement.classList.contains('hub-confirm-stay')")
    driver.execute_script("document.querySelector('.hub-confirm-stay').click()")
    assert driver.execute_script("return window.testHost.gameKey") == "demo"
    # Focus goes back to the Join button that asked
    assert driver.execute_script("return document.activeElement.dataset.join") == str(ADMIN_ID)
    driver.execute_script(f"{PANEL}.querySelector('[data-join=\"{ADMIN_ID}\"]').click()")
    driver.execute_script("document.querySelector('.hub-confirm-leave').click()")
    wait_for(driver, "window.testHost.gameKey === 'placed'")


def test_an_arrival_slides_out_of_the_button(driver, live):
    open_game(driver, live)
    wait_for(driver, f"!{FLOATING}.hidden")
    # Past the quiet time after the link opened, so this counts as someone arriving
    driver.execute_script("window.testHost.presence.quietUntil = 0")
    live.add_person(MANAGER_ID, where="demo")
    note = wait_for(driver, f"{FLOATING}.querySelector('.hub-note')?.textContent")
    assert note == "\u2068Manager\u2069 joined"


def test_no_arrival_notes_right_after_connecting(driver, live):
    live.add_person(MANAGER_ID, where="demo")
    open_game(driver, live)
    wait_for(driver, f"!{FLOATING}.hidden && {FLOATING}.querySelector('.hub-count')")
    assert driver.execute_script(f"return {FLOATING}.querySelector('.hub-note')") is None


def test_invite_opens_discords_window(driver, live):
    open_game(driver, live)
    driver.execute_script("window.testHost.people.open()")
    driver.execute_script(f"{PANEL}.querySelector('.hub-invite-button').click()")
    assert wait_for(driver, "window.fakeDiscord.invite") == 1


def test_status_lines_stay_plain_text_and_isolated(driver, live):
    open_game(driver, live)
    # Markup and a right-to-left override, as another player's status could carry them
    line = "<b>bold</b> \u202etxet"
    live.add_person(MANAGER_ID, where="demo", status=line)
    wait_for(driver, "window.testHost.presence.people.length === 2")
    driver.execute_script("window.testHost.people.open()")
    row = f"[...{PANEL}.querySelectorAll('.hub-person')].find((r) => r.innerText.includes('Manager'))"
    wait_for(driver, f"{row}?.querySelector('.hub-person-status').textContent.includes('bold')")
    assert driver.execute_script(f"return {row}.querySelector('.hub-person-status').textContent") == line
    assert driver.execute_script(f"return {row}.querySelector('b')") is None
    for part in ("name", "status"):
        bidi = driver.execute_script(f"return getComputedStyle({row}.querySelector('.hub-person-{part}')).unicodeBidi")
        assert bidi == "isolate"


def press_on(driver, selector):
    ActionChains(driver).move_to_element(driver.find_element(By.CSS_SELECTOR, selector)).click_and_hold().perform()


def test_a_join_click_survives_a_list_arriving_mid_press(driver, live):
    open_game(driver, live)
    conn = live.add_person(ADMIN_ID, where="placed", status="one")
    wait_for(driver, "window.testHost.presence.people.length === 2")
    open_panel(driver)
    press_on(driver, f'.hub-people-panel [data-join="{ADMIN_ID}"]')
    try:
        # The status line changes, which redraws the panel unless a press is under way
        live.update_person(conn, where="placed", status="two")
        person_status(driver, ADMIN_ID, "two")
    finally:
        ActionChains(driver).release().perform()
    wait_for(driver, "window.testHost.gameKey === 'placed'")


def test_the_panel_catches_up_once_the_press_ends(driver, live):
    open_game(driver, live)
    conn = live.add_person(MANAGER_ID, where="demo", status="one")
    wait_for(driver, "window.testHost.presence.people.length === 2")
    open_panel(driver)
    press_on(driver, ".hub-people-panel .hub-panel-head h2")
    try:
        live.update_person(conn, where="demo", status="two")
        person_status(driver, MANAGER_ID, "two")
        assert "two" not in driver.execute_script(f"return {PANEL}.innerText")
    finally:
        ActionChains(driver).release().perform()
    wait_for(driver, f"{PANEL}.innerText.includes('two')")


def test_the_same_rows_are_not_drawn_again(driver, live):
    open_game(driver, live)
    conn = live.add_person(MANAGER_ID, where="demo", status="one")
    wait_for(driver, "window.testHost.presence.people.length === 2")
    open_panel(driver)
    driver.execute_script(f"window.row = {PANEL}.querySelector('.hub-person')")
    # The game's data isn't shown in the panel
    live.update_person(conn, where="demo", status="one", data={"wave": 4})
    wait_for(driver, "window.testHost.presence.people.find((p) => p.id === '3').data?.wave === 4")
    assert driver.execute_script(f"return window.row === {PANEL}.querySelector('.hub-person')")
    live.update_person(conn, where="demo", status="two", data={"wave": 4})
    wait_for(driver, f"{PANEL}.innerText.includes('two')")
    assert driver.execute_script(f"return window.row !== {PANEL}.querySelector('.hub-person')")


def test_the_button_keeps_its_pictures_until_who_is_shown_changes(driver, live):
    open_game(driver, live)
    conn = live.add_person(MANAGER_ID, where="placed", status="a")
    wait_for(driver, f"{FLOATING}.querySelector('.hub-count')?.textContent === '1'")
    face = f"{FLOATING}.querySelector('.hub-people-face')"
    driver.execute_script(f"window.face = {face}")
    live.update_person(conn, where="placed", status="b")
    person_status(driver, MANAGER_ID, "b")
    assert driver.execute_script(f"return window.face === {face}")
    # Into this game, the button shows their picture instead of the people icon
    live.update_person(conn, where="demo", status="b")
    wait_for(driver, f"window.face !== {face}")
    assert driver.execute_script(f"return !!{FLOATING}.querySelector('.hub-stack')")


def test_a_game_can_size_its_button(driver, live):
    open_game(driver, live, "placed")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    height = "document.querySelector('.hub-people-button')?.getBoundingClientRect().height"
    # Once the button exists and the stylesheet has reached it
    wait_for(driver, f"{height} === 36")
    driver.execute_script("document.documentElement.style.setProperty('--hub-people-size', '48px')")
    assert driver.execute_script(f"return {height}") == 48


def test_the_side_panel_keeps_clear_of_the_right_edge(driver, live):
    open_game(driver, live)
    driver.execute_script("document.documentElement.style.setProperty('--safe-right', '30px')")
    open_panel(driver)
    assert driver.execute_script(f"return getComputedStyle({PANEL}).paddingRight") == "30px"


def test_a_button_from_an_earlier_page_is_forgotten(driver, live):
    open_game(driver, live, "placed")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "document.querySelector('.hub-people-button')")
    driver.switch_to.default_content()
    # A page of the game still on screen keeps its button
    assert driver.execute_script("const u = window.testHost.people; u.gameLoaded(); return !!u.placed")
    # One from a page that has since been replaced doesn't
    stale = "document.implementation.createHTMLDocument('').createElement('span')"
    forgotten = f"const u = window.testHost.people; u.placed = {stale}; u.gameLoaded(); return u.placed"
    assert driver.execute_script(forgotten) is None


def test_closing_the_game_hides_the_button_and_forgets_a_placed_one(driver, live):
    open_game(driver, live, "placed")
    wait_for(driver, "!!window.testHost.people.placed")
    driver.execute_script("window.testHost.people.open()")
    driver.execute_script("window.testHost.closeGame()")
    assert driver.execute_script(f"return {FLOATING}.hidden") is True
    assert driver.execute_script(f"return {PANEL}.hidden") is True
    assert driver.execute_script("return window.testHost.people.placed") is None
    # The next game, one that places no button, gets the floating one
    driver.execute_script("window.testHost.openGame('demo')")
    wait_for(driver, f"!{FLOATING}.hidden")


def test_escape_and_a_tap_outside_close_the_panel(driver, live):
    open_game(driver, live)
    open_panel(driver)
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    wait_for(driver, f"{PANEL}.hidden")
    open_panel(driver)
    driver.find_element(By.CLASS_NAME, "hub-people-scrim").click()
    wait_for(driver, f"{PANEL}.hidden")
    assert driver.execute_script("return document.querySelector('.hub-people-scrim').hidden") is True


def test_escape_on_the_question_stays_and_the_dialog_is_named(driver, live):
    ask_to_leave(driver, live)
    driver.execute_script(f"{PANEL}.querySelector('[data-join=\"{ADMIN_ID}\"]').click()")
    wait_for(driver, f"!{CONFIRM}.hidden")
    # The question is the dialog's name, read out once
    named = f"document.getElementById({CONFIRM}.getAttribute('aria-labelledby'))"
    assert driver.execute_script(f"return {named} === document.querySelector('.hub-confirm-text')")
    assert driver.execute_script(f"return {CONFIRM}.getAttribute('aria-describedby')") is None
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    wait_for(driver, f"{CONFIRM}.hidden")
    # The panel stays open, and focus is back on the Join that asked
    assert driver.execute_script(f"return {PANEL}.hidden") is False
    assert driver.execute_script("return document.activeElement.dataset.join") == str(ADMIN_ID)
    assert driver.execute_script("return window.testHost.gameKey") == "demo"


def test_closing_the_game_settles_the_question(driver, live):
    ask_to_leave(driver, live)
    ask = (
        "const p = window.testHost.presence.view('demo').find((x) => x.id === '4');"
        "window.testHost.join(p).then(() => { window.%s = true; });"
    )
    driver.execute_script(ask % "firstDone")
    wait_for(driver, f"!{CONFIRM}.hidden")
    # A second question replaces the first, which is answered as Stay
    driver.execute_script(ask % "secondDone")
    wait_for(driver, "window.firstDone === true")
    assert driver.execute_script(f"return {CONFIRM}.hidden") is False
    driver.execute_script("window.testHost.closeGame()")
    wait_for(driver, f"{CONFIRM}.hidden && window.secondDone === true")
    assert driver.execute_script("return document.querySelector('.hub-people-scrim').hidden") is True
    assert driver.execute_script("return window.testHost.gameKey") is None


def test_a_note_is_announced_once_it_exists(driver, live):
    open_game(driver, live)
    wait_for(driver, f"!{FLOATING}.hidden")
    driver.execute_script("window.testHost.presence.quietUntil = 0")
    driver.execute_script(
        f"new MutationObserver((records) => {{ window.atInsert = records[0].addedNodes[0].textContent; }})"
        f".observe({FLOATING}, {{ childList: true }})"
    )
    live.add_person(MANAGER_ID, where="demo")
    wait_for(driver, f"{FLOATING}.querySelector('.hub-note')?.textContent")
    # A live region that is born with its words in it is often not read out
    assert driver.execute_script("return window.atInsert") == ""
    assert driver.execute_script(f"return {FLOATING}.querySelector('.hub-note').getAttribute('role')") == "status"


def test_a_long_note_stays_on_the_screen(driver, live):
    open_game(driver, live)
    wait_for(driver, f"!{FLOATING}.hidden")
    shown = driver.execute_async_script(
        f"""const done = arguments[arguments.length - 1];
        import('./people.js').then(({{ showNote }}) => {{
          showNote({FLOATING}, 'x'.repeat(400));
          const note = {FLOATING}.querySelector('.hub-note');
          // The words go in a frame after the note, so measure once they are there
          requestAnimationFrame(() => requestAnimationFrame(() => {{
            const box = note.getBoundingClientRect();
            done([note.textContent.length, box.left >= 0, box.right <= innerWidth, getComputedStyle(note).textOverflow]);
          }}));
        }});"""
    )
    assert shown == [400, True, True, "ellipsis"]


@pytest.mark.parametrize("left", ["30%", "55%"])
def test_a_long_note_from_a_button_mid_screen_stays_on_the_screen(driver, live, left):
    open_game(driver, live)
    wait_for(driver, f"!{FLOATING}.hidden")
    # A game can put its button anywhere, such as the middle of its bar. The note opens toward the far side
    shown = driver.execute_async_script(
        f"""const done = arguments[arguments.length - 1];
        Object.assign({FLOATING}.style, {{ left: '{left}', right: 'auto', top: '40%' }});
        import('./people.js').then(({{ showNote }}) => {{
          showNote({FLOATING}, 'x'.repeat(400));
          const note = {FLOATING}.querySelector('.hub-note');
          requestAnimationFrame(() => requestAnimationFrame(() => {{
            const box = note.getBoundingClientRect();
            done([box.left >= 0, box.right <= innerWidth, getComputedStyle(note).textOverflow]);
          }}));
        }});"""
    )
    assert shown == [True, True, "ellipsis"]


def test_outside_discord_the_panel_says_where_to_go(driver, live):
    driver.get(f"{live.url}/")
    assert wait_for(driver, "document.body.dataset.login") == "offline"
    driver.execute_script("window.testHost.people.open()")
    assert wait_for(driver, f"{PANEL}.querySelector('.hub-panel-note')?.textContent") == PREVIEW


def test_a_game_opened_on_its_own_gets_a_button_that_says_where_to_go(driver, live):
    driver.get(f"{live.url}/games/placed/")
    wait_for(driver, "document.querySelector('.hub-people .hub-people-button')")
    button = "document.querySelector('.hub-people-button')"
    assert driver.execute_script(f"return {button}.title") == PREVIEW
    assert driver.execute_script(f"return {button}.getAttribute('aria-label')") == PREVIEW


def test_alone_the_panel_offers_the_invite_first(driver, live):
    open_game(driver, live)
    open_panel(driver)
    first = f"{PANEL}.querySelector('.hub-panel-body').firstElementChild"
    assert driver.execute_script(f"return {first}.classList.contains('hub-invite')")
    assert driver.execute_script(f"return {first}.textContent") == "Nobody else is here yet.Invite friends"
    assert driver.execute_script(f"return {first}.querySelector('.hub-invite-button').classList.contains('primary')")


def fake_press(driver, button):
    """A pointer going down in the panel, as a press whose release may never come"""
    driver.execute_script(
        "document.querySelector('.hub-panel-head h2').dispatchEvent("
        "new PointerEvent('pointerdown', { bubbles: true, button: arguments[0] }))",
        button,
    )


def with_a_status_to_change(driver, live):
    open_game(driver, live)
    conn = live.add_person(MANAGER_ID, where="demo", status="one")
    wait_for(driver, "window.testHost.presence.people.length === 2")
    open_panel(driver)
    return conn


def test_a_press_with_another_button_does_not_hold_the_panel(driver, live):
    conn = with_a_status_to_change(driver, live)
    # A right click can open a menu that swallows its release, so it must not freeze the list
    fake_press(driver, 2)
    live.update_person(conn, where="demo", status="two")
    wait_for(driver, f"{PANEL}.innerText.includes('two')")


def test_losing_the_window_ends_a_press(driver, live):
    conn = with_a_status_to_change(driver, live)
    fake_press(driver, 0)
    live.update_person(conn, where="demo", status="two")
    person_status(driver, MANAGER_ID, "two")
    assert "two" not in driver.execute_script(f"return {PANEL}.innerText")
    driver.execute_script("window.dispatchEvent(new Event('blur'))")
    wait_for(driver, f"{PANEL}.innerText.includes('two')")


def test_closing_the_panel_ends_a_press(driver, live):
    conn = with_a_status_to_change(driver, live)
    fake_press(driver, 0)
    driver.execute_script("window.testHost.people.close()")
    live.update_person(conn, where="demo", status="two")
    person_status(driver, MANAGER_ID, "two")
    open_panel(driver)
    # Opened again, the list is current and further lists are drawn at once
    assert "two" in driver.execute_script(f"return {PANEL}.innerText")
    live.update_person(conn, where="demo", status="three")
    wait_for(driver, f"{PANEL}.innerText.includes('three')")


def test_a_space_press_on_join_survives_a_list_arriving(driver, live):
    open_game(driver, live)
    conn = live.add_person(ADMIN_ID, where="placed", status="one")
    wait_for(driver, "window.testHost.presence.people.length === 2")
    open_panel(driver)
    driver.execute_script(f"{PANEL}.querySelector('[data-join=\"{ADMIN_ID}\"]').focus()")
    ActionChains(driver).key_down(Keys.SPACE).perform()
    try:
        # A button is pressed when Space comes up, so the button must still be the same one then
        live.update_person(conn, where="placed", status="two")
        person_status(driver, ADMIN_ID, "two")
    finally:
        ActionChains(driver).key_up(Keys.SPACE).perform()
    wait_for(driver, "window.testHost.gameKey === 'placed'")


def test_keyboard_focus_on_invite_stays_through_a_redraw(driver, live):
    conn = with_a_status_to_change(driver, live)
    driver.execute_script(f"{PANEL}.querySelector('.hub-invite-button').focus()")
    live.update_person(conn, where="demo", status="two")
    wait_for(driver, f"{PANEL}.innerText.includes('two')")
    assert driver.execute_script("return document.activeElement.classList.contains('hub-invite-button')")
    assert driver.execute_script(f"return {PANEL}.contains(document.activeElement)")


def test_moving_focus_ends_a_held_space_press(driver, live):
    conn = with_a_status_to_change(driver, live)
    driver.execute_script(f"{PANEL}.querySelector('.hub-invite-button').focus()")
    ActionChains(driver).key_down(Keys.SPACE).perform()
    try:
        live.update_person(conn, where="demo", status="two")
        person_status(driver, MANAGER_ID, "two")
        assert "two" not in driver.execute_script(f"return {PANEL}.innerText")
        # The key comes up elsewhere, or never: focus leaving the panel is the end of the press
        driver.execute_script("document.body.focus(); document.activeElement.blur()")
        wait_for(driver, f"{PANEL}.innerText.includes('two')")
    finally:
        ActionChains(driver).key_up(Keys.SPACE).perform()
