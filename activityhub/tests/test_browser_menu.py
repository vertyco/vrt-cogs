import time

import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.select import Select

from activityhub.tests.browser import (
    DISCORD_QUERY,
    LiveHub,
    console_lines,
    fresh,
    hub_web_copy,
    start_chrome,
    wait_for,
    wait_for_console,
)
from activityhub.tests.fakes import (
    ADMIN_ID,
    GUILD_ID,
    MANAGER_ID,
    MEMBER_ID,
    OWNER_ID,
    DemoCog,
    make_hub,
    register,
    write_demo_web,
)

CARDS = "[...document.querySelectorAll('#games .card')].map((card) => card.dataset.key)"
PILLS = "[...document.querySelectorAll('#games .pill')].map((pill) => pill.dataset.key)"
SELECTED = "document.querySelector('#games .pill.selected').dataset.key"
# Records the pitch of every tone the menu starts, so a test can tell the move, select and back sounds apart
SOUND_SPY = """
window.soundLog = [];
const realStart = OscillatorNode.prototype.start;
OscillatorNode.prototype.start = function (...args) {
  window.soundLog.push(Math.round(this.frequency.value));
  return realStart.apply(this, args);
};
"""
MOVE, SELECT, BACK = 1700, 880, 1175
# The game frame's opacity and the menu's display, straight after clicking the demo card
OPEN_DEMO = """
document.querySelector('.card[data-key="demo"]').click();
const frame = document.getElementById('game-frame');
return [getComputedStyle(frame).opacity, getComputedStyle(document.getElementById('menu')).display];
"""
COUNTER = "document.querySelector('.fps').textContent"
# True once the Orb menu's opening and turns are over; only the endless background loops still run
SETTLED = """document.getAnimations().every(
  (animation) => animation.effect.getComputedTiming().endTime === Infinity || animation.playState !== "running"
)"""
# Run in a game's frame: hub.stat() with the script's argument
SHOW_STAT = """
const text = arguments[0];
const done = arguments[arguments.length - 1];
import('activityhub').then(async ({ connect }) => {
  const hub = await connect();
  hub.stat(text);
  done();
});
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
    register(hub, DemoCog(write_demo_web(tmp_path / "demo")))
    register(hub, DemoCog(write_demo_web(tmp_path / "second"), key="second", name="Alpha Game", cog_name="Second"))
    server = LiveHub(hub, hub_web_copy(tmp_path))
    server.start()
    driver.set_window_size(1280, 800)
    fresh(driver, server)
    yield server
    server.stop()


def open_menu(driver, live, query=""):
    driver.get(f"{live.url}/{query}")
    wait_for(driver, "document.querySelectorAll('#games .card').length > 0")


def open_settings(driver):
    driver.find_element(By.ID, "gear").click()
    wait_for(driver, "getComputedStyle(document.getElementById('panel')).transform === 'none'")


def pick_tab(driver, tab):
    driver.find_element(By.CSS_SELECTOR, f'#tabs .tab[data-tab="{tab}"]').click()


def save(driver):
    driver.find_element(By.ID, "save").click()
    wait_for(driver, "document.getElementById('panel-status').textContent === 'Saved.'")


def no_sideways_scroll(driver):
    return driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth")


def test_preview_on_desktop_and_phone(driver, live):
    open_menu(driver, live)
    assert driver.execute_script(f"return {CARDS}") == ["second", "demo"]
    # With nothing set anywhere, the menu uses the Orb theme
    assert driver.execute_script("return document.body.dataset.theme") == "orb"
    assert "Preview" in driver.find_element(By.ID, "notice").text
    assert not driver.find_element(By.ID, "gear").is_displayed()
    assert no_sideways_scroll(driver)
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride", {"width": 375, "height": 740, "deviceScaleFactor": 1, "mobile": True}
    )
    try:
        open_menu(driver, live)
        assert driver.execute_script("return window.innerWidth") == 375
        assert no_sideways_scroll(driver)
        assert all(card.is_displayed() for card in driver.find_elements(By.CSS_SELECTOR, "#games .card"))
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


@pytest.mark.parametrize("layout", ["grid", "list", "compact"])
def test_each_layout(driver, live, layout):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": layout}
    open_menu(driver, live)
    assert driver.execute_script(f"return document.getElementById('games').classList.contains('{layout}')")
    card = driver.find_element(By.CSS_SELECTOR, "#games .card")
    if layout == "grid":
        # Columns are at least 176 px wide, and the cards in a row share one height
        heights = {c.size["height"] for c in driver.find_elements(By.CSS_SELECTOR, "#games .card")}
        assert card.size["width"] >= 176 and len(heights) == 1
    desc_shown = driver.find_element(By.CSS_SELECTOR, "#games .desc").is_displayed()
    assert desc_shown is (layout != "compact")
    assert no_sideways_scroll(driver)


def test_details_off_hides_descriptions(driver, live):
    live.hub.config.globals["look"] = {"details": False, "layout": "list"}
    open_menu(driver, live)
    assert not driver.find_element(By.CSS_SELECTOR, "#games .desc").is_displayed()


def test_in_discord_header_and_member_tabs(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    open_menu(driver, live, DISCORD_QUERY)
    assert driver.find_element(By.ID, "who-name").text == "Test Server"
    assert driver.find_element(By.ID, "who-letter").text == "T"
    assert not driver.find_element(By.ID, "notice").is_displayed()
    open_settings(driver)
    tabs = [tab.text for tab in driver.find_elements(By.CSS_SELECTOR, "#tabs .tab")]
    assert tabs == ["My look", "My order"]


def test_look_previews_live_and_saves(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    open_menu(driver, live, DISCORD_QUERY)
    open_settings(driver)
    Select(driver.find_element(By.ID, "field-layout")).select_by_value("list")
    assert driver.execute_script("return document.getElementById('games').classList.contains('list')")
    assert MEMBER_ID not in live.hub.config.users or live.hub.config.users[MEMBER_ID]["look"] == {}
    save(driver)
    assert live.hub.config.users[MEMBER_ID]["look"] == {"layout": "list"}


def test_keyboard_focus_goes_into_settings_and_back_to_the_gear(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    open_menu(driver, live, DISCORD_QUERY)
    open_settings(driver)
    assert driver.execute_script("return document.activeElement.dataset.tab") == "look"
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    wait_for(driver, "!document.body.classList.contains('panel-open')")
    assert driver.execute_script("return document.activeElement.id") == "gear"


def test_a_save_after_a_bot_restart_logs_in_again_and_keeps_the_edits(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    open_menu(driver, live, DISCORD_QUERY)
    open_settings(driver)
    Select(driver.find_element(By.ID, "field-layout")).select_by_value("list")
    # The bot restarted while the panel was open, and forgot the login
    live.hub.sessions.sessions.clear()
    save(driver)
    assert live.hub.config.users[MEMBER_ID]["look"] == {"layout": "list"}
    assert driver.execute_script("return document.body.classList.contains('panel-open')")
    assert driver.execute_script("return window.fakeDiscord") == {"created": 1, "authorize": 2, "authenticate": 1}


def test_reset_is_staged_until_saved(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    live.hub.config.user_from_id(MEMBER_ID).data["look"] = {"layout": "list"}
    open_menu(driver, live, DISCORD_QUERY)
    open_settings(driver)
    driver.find_element(By.ID, "reset").click()
    assert Select(driver.find_element(By.ID, "field-layout")).first_selected_option.get_attribute("value") == ""
    assert driver.execute_script("return document.getElementById('games').classList.contains('grid')")
    driver.find_element(By.ID, "close").click()
    assert driver.execute_script("return document.getElementById('games').classList.contains('list')")
    assert live.hub.config.users[MEMBER_ID]["look"] == {"layout": "list"}


def test_order_with_the_arrow_buttons(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    open_menu(driver, live, DISCORD_QUERY)
    open_settings(driver)
    pick_tab(driver, "order")
    driver.find_element(By.CSS_SELECTOR, '.order-row[data-key="second"] [data-move="down"]').click()
    save(driver)
    assert live.hub.config.users[MEMBER_ID]["order"] == ["demo", "second"]
    driver.find_element(By.ID, "close").click()
    assert driver.execute_script(f"return {CARDS}") == ["demo", "second"]


def test_reset_order_saves_alphabetical(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    live.hub.config.user_from_id(MEMBER_ID).data["order"] = ["demo", "second"]
    open_menu(driver, live, DISCORD_QUERY)
    assert driver.execute_script(f"return {CARDS}") == ["demo", "second"]
    open_settings(driver)
    pick_tab(driver, "order")
    driver.find_element(By.ID, "reset").click()
    save(driver)
    assert live.hub.config.users[MEMBER_ID]["order"] == []
    driver.find_element(By.ID, "close").click()
    assert driver.execute_script(f"return {CARDS}") == ["second", "demo"]


def test_dropping_something_from_outside_leaves_the_order_alone(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    open_menu(driver, live, DISCORD_QUERY)
    open_settings(driver)
    pick_tab(driver, "order")
    # A drop of text that isn't a row from the list, like a file or a dragged link
    driver.execute_script("""
        const row = document.querySelector('.order-row[data-key="demo"]');
        const data = new DataTransfer();
        data.setData('text/plain', '9');
        row.dispatchEvent(new DragEvent('drop', { dataTransfer: data, bubbles: true, cancelable: true }));
        """)
    rows = "[...document.querySelectorAll('.order-row')].map((row) => row.dataset.key)"
    assert driver.execute_script(f"return {rows}") == ["second", "demo"]


def test_server_tab_turns_a_game_off(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    live.user_id = MANAGER_ID
    open_menu(driver, live, DISCORD_QUERY)
    open_settings(driver)
    pick_tab(driver, "server")
    driver.find_element(By.CSS_SELECTOR, '.switch input[data-key="demo"]').click()
    save(driver)
    assert live.hub.config.guilds[GUILD_ID]["disabled"] == ["demo"]
    driver.find_element(By.ID, "close").click()
    assert driver.execute_script(f"return {CARDS}") == ["second"]


def test_defaults_tab_turns_a_game_off_everywhere(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    live.user_id = OWNER_ID
    open_menu(driver, live, DISCORD_QUERY)
    open_settings(driver)
    pick_tab(driver, "defaults")
    driver.find_element(By.CSS_SELECTOR, '.switch input[data-key="demo"]').click()
    save(driver)
    assert live.hub.config.globals["disabled"] == ["demo"]
    pick_tab(driver, "server")
    assert not driver.find_elements(By.CSS_SELECTOR, '.switch input[data-key="demo"]')
    driver.find_element(By.ID, "close").click()
    assert driver.execute_script(f"return {CARDS}") == ["second"]


def test_open_a_game_and_come_back(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    # One script clicks and looks, so the game's page can't have loaded in between
    hidden, menu = driver.execute_script(OPEN_DEMO)
    assert hidden == "0" and menu != "none"
    wait_for(driver, "document.body.classList.contains('playing')")
    assert driver.execute_script("return getComputedStyle(document.getElementById('menu')).display") == "none"
    assert driver.execute_script("return getComputedStyle(document.getElementById('game-frame')).opacity") == "1"
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "window.demo && window.demo.done")
    assert driver.execute_script("return window.demo.player.id") == str(MEMBER_ID)
    driver.find_element(By.ID, "back").click()
    driver.switch_to.default_content()
    wait_for(driver, "document.getElementById('game-frame') === null")
    assert driver.find_element(By.CSS_SELECTOR, '.card[data-key="demo"]').is_displayed()


def test_remembered_launch_opens_the_game(driver, live):
    live.hub.launches.remember(MEMBER_ID, "demo")
    driver.get(f"{live.url}/{DISCORD_QUERY}")
    src = wait_for(driver, "document.getElementById('game-frame') && document.getElementById('game-frame').src")
    assert "/games/demo/" in src and "frame_id=f" in src


def test_expired_session_logs_in_again_without_a_new_handshake(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    old_session = driver.execute_script("return window.activityhubHost.login.session")
    live.hub.sessions.sessions.clear()
    driver.find_element(By.CSS_SELECTOR, '.card[data-key="demo"]').click()
    wait_for(
        driver,
        f"window.activityhubHost.login.session && window.activityhubHost.login.session !== '{old_session}'",
    )
    # The game logs in again by itself and keeps running
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "window.demo && window.demo.done")
    assert driver.execute_script("return [window.demo.error, window.demo.echo.user]") == [None, MEMBER_ID]
    driver.switch_to.default_content()
    # The game can finish all that before its fade in does
    wait_for(driver, "document.body.classList.contains('playing')")
    deadline = time.monotonic() + 10
    while len(live.hub.sessions.sessions) != 1 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert driver.execute_script("return window.fakeDiscord") == {"created": 1, "authorize": 2, "authenticate": 1}
    assert len(live.hub.sessions.sessions) == 1


def test_the_discord_token_is_dropped_once_discord_accepts_it(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    wait_for(driver, "window.fakeDiscord.authenticate === 1")
    login = driver.execute_async_script("const done = arguments[0]; window.activityhubHost.ready.then(done);")
    assert login["session"] and "accessToken" not in login


def test_logins_needed_at_once_share_one_authorize(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    shared = driver.execute_async_script("""
        const done = arguments[0];
        const host = window.activityhubHost;
        Promise.all([host.relogin(), host.relogin()]).then(([a, b]) => done(a === b && !("accessToken" in a)));
        """)
    assert shared is True
    assert driver.execute_script("return window.fakeDiscord.authorize") == 2


def test_restart_when_discord_refuses_a_second_authorize_shows_the_notice(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    driver.execute_script("window.fakeDiscord.failAuthorize = true; window.noReload = 'still here';")
    live.hub.sessions.sessions.clear()
    driver.find_element(By.CSS_SELECTOR, '.card[data-key="demo"]').click()
    wait_for(driver, "document.getElementById('notice').textContent.includes('Your session expired')")
    assert not driver.find_element(By.ID, "notice").get_attribute("hidden")
    assert driver.find_elements(By.ID, "game-frame") == []
    assert driver.execute_script("return window.noReload") == "still here"
    assert driver.execute_script("return window.fakeDiscord.created") == 1
    assert len(live.hub.sessions.sessions) == 0


def test_a_page_discord_never_answers_says_why(driver, tmp_path):
    # Like the game frame's address opened in its own tab: the page waits for a Discord that isn't there
    web = hub_web_copy(tmp_path)
    host = web / "host.js"
    text = host.read_text(encoding="utf-8")
    assert "const DISCORD_WAIT_MS = 10000;" in text
    host.write_text(text.replace("const DISCORD_WAIT_MS = 10000;", "const DISCORD_WAIT_MS = 300;"), encoding="utf-8")
    hub = make_hub()
    register(hub, DemoCog(write_demo_web(tmp_path / "demo")))
    server = LiveHub(hub, web)
    server.start()
    try:
        fresh(driver, server)
        driver.get(f"{server.url}/{DISCORD_QUERY}&silent=1")
        wait_for(driver, "document.getElementById('notice').textContent.includes('only works inside Discord')")
        assert driver.find_element(By.ID, "notice").text == (
            "Discord hasn't answered yet. This address only works inside Discord; for the browser preview, "
            "open / without the ?frame_id=... part."
        )
        wait_for_console(driver, "ActivityHub: Discord hasn't answered yet.")
        # It keeps waiting, so a Discord that is only slow still gets the menu
        driver.execute_script("window.answerDiscord()")
        wait_for(driver, "document.querySelectorAll('#games .card').length > 0")
        assert driver.find_element(By.ID, "notice").get_attribute("hidden")
    finally:
        server.stop()


def test_empty_state_points_admins_to_the_guide(driver, live):
    live.hub.registry.games.clear()
    live.user_id = MANAGER_ID
    driver.get(f"{live.url}/{DISCORD_QUERY}")
    text = wait_for(
        driver, "document.querySelector('#games .empty') && document.querySelector('#games .empty').textContent"
    )
    assert "No games to play here yet." in text and "DEVELOPERS.md" in text


@pytest.fixture
def sound_spy(driver):
    script = driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": SOUND_SPY})
    yield
    driver.execute_cdp_cmd("Page.removeScriptToEvaluateOnNewDocument", {"identifier": script["identifier"]})


def press(driver, key):
    ActionChains(driver).send_keys(key).perform()


def sounds(driver):
    return driver.execute_script("return window.soundLog")


def fetched(driver, name):
    return wait_for(
        driver, f"performance.getEntriesByType('resource').some((entry) => entry.name.endsWith('/sounds/{name}'))"
    )


def add_thumbnail_game(live, tmp_path):
    folder = write_demo_web(tmp_path / "third")
    register(live.hub, DemoCog(folder, key="third", name="Third", cog_name="Third", thumbnail="thumb.svg"))
    return folder


def touch_device(driver, width, height):
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": True}
    )
    driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})


def plain_device(driver):
    driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": False})
    driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def slide(driver, start, end, steps=8):
    """One finger from start to end, in small moves like a real swipe"""
    (x0, y0), (x1, y1) = start, end
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y0}]})
    for i in range(1, steps + 1):
        point = {"x": x0 + (x1 - x0) * i / steps, "y": y0 + (y1 - y0) * i / steps}
        driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [point]})
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def test_orb_swipes_move_along_the_ring_on_a_phone_held_sideways(driver, live, tmp_path, sound_spy):
    for i in range(4):
        folder = write_demo_web(tmp_path / f"extra{i}")
        register(live.hub, DemoCog(folder, key=f"extra{i}", name=f"Extra {i}", cog_name=f"Extra{i}"))
    touch_device(driver, 844, 390)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        assert driver.execute_script("return document.body.dataset.theme") == "orb"
        assert driver.execute_script(f"return {PILLS}")[:3] == ["second", "demo", "extra0"]
        # Down along the ring moves to the next game, one per step, like the highlight follows the finger
        slide(driver, (420, 200), (420, 300))
        wait_for(driver, f"{SELECTED} === 'extra0'")
        # Browsers keep a page quiet until the first touch ends, so the move sound comes from the next slide on
        slide(driver, (420, 300), (420, 250))
        wait_for(driver, f"{SELECTED} === 'demo'")
        wait_for(driver, f"window.soundLog.includes({MOVE})")
        # Left and right work too, and a slide that starts on a pill doesn't open its game
        slide(driver, (500, 200), (600, 200))
        wait_for(driver, f"{SELECTED} === 'extra1'")
        pill = driver.find_element(By.CSS_SELECTOR, '#games .pill[data-key="extra1"]').rect
        x, y = pill["x"] + pill["width"] / 2, pill["y"] + pill["height"] / 2
        slide(driver, (x, y), (x - 50, y))
        wait_for(driver, f"{SELECTED} === 'extra0'")
        assert driver.find_elements(By.ID, "game-frame") == []
        # A fast slide that arrives in one big move goes as far as a slow one, here three steps
        slide(driver, (420, 190), (420, 190 + 3 * 44 + 10), steps=1)
        wait_for(driver, f"{SELECTED} === 'extra3'")
        assert driver.execute_script("return window.scrollY") == 0
    finally:
        plain_device(driver)


def test_orb_swipes_move_along_the_ring_on_an_upright_phone(driver, live):
    touch_device(driver, 375, 740)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        slide(driver, (300, 510), (300, 560))
        wait_for(driver, f"{SELECTED} === 'demo'")
        assert driver.find_element(By.CSS_SELECTOR, "#orb-screen .screen-name").text.lower() == "demo"
        assert driver.execute_script("return window.scrollY") == 0
        assert driver.find_elements(By.ID, "game-frame") == []
    finally:
        plain_device(driver)


# Where the Orb menu draws things on the screen, each as [left, top, right, bottom]
ORB_LAYOUT = """
const box = (node) => { const r = node.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
const pills = [...document.querySelectorAll('#games .pill:not(.off-ring)')];
const down = document.querySelector('.orb-arrow.down');
const middle = box(down);
return {
  page: [document.documentElement.scrollHeight, innerHeight],
  bar: box(document.querySelector('.bar')),
  panel: box(document.getElementById('orb-screen')),
  arm: box(document.querySelector('#orb-screen .screen-arm')),
  ring: pills.flatMap((pill) => [box(pill.querySelector('.pod')), box(pill.querySelector('.plate'))]),
  down: down.hidden ? null : middle,
  downOnTop: document.elementFromPoint((middle[0] + middle[2]) / 2, (middle[1] + middle[3]) / 2) === down,
};
"""


def test_orb_upright_phone_fits_between_discords_buttons(driver, live, tmp_path):
    # Enough games that the ring scrolls, so the arrow under it shows
    for i in range(5):
        register(
            live.hub, DemoCog(write_demo_web(tmp_path / f"x{i}"), key=f"x{i}", name=f"Extra {i}", cog_name=f"X{i}")
        )
    touch_device(driver, 390, 844)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        # Discord's phone app covers the top with its back pill and Leave button, and the bottom with the home bar
        driver.execute_script(
            "document.documentElement.style.setProperty('--discord-safe-area-inset-top', '100px');"
            "document.documentElement.style.setProperty('--discord-safe-area-inset-bottom', '34px');"
            "window.dispatchEvent(new Event('resize'));"
        )
        wait_for(driver, SETTLED)
        layout = driver.execute_script(ORB_LAYOUT)
        # The page is exactly the screen, so a finger can't scroll it or bounce it
        assert layout["page"][0] == layout["page"][1]
        # The panel hangs under the header, its arm stays above it, and the ring and its arrow fit between the
        # panel and the home bar, with nothing over the arrow
        bar, panel = layout["bar"], layout["panel"]
        assert panel[1] >= bar[3] and layout["arm"][3] < panel[3]
        assert layout["down"] is not None and layout["downOnTop"]
        for box in [*layout["ring"], layout["down"]]:
            assert panel[3] <= box[1] and box[3] <= 844 - 34
    finally:
        plain_device(driver)


def test_orb_slides_hold_the_page_still_and_work_from_anywhere(driver, live):
    touch_device(driver, 390, 844)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        # The menu's own listener runs first; this one hears whether the slide kept the page from scrolling
        driver.execute_script(
            "window.heldStill = [];"
            "window.addEventListener('touchmove', (event) => window.heldStill.push(event.defaultPrevented));"
        )
        # A slide that starts on the orb, away from every tab, still moves along the ring
        slide(driver, (30, 540), (30, 600))
        wait_for(driver, f"{SELECTED} === 'demo'")
        assert driver.execute_script("return window.heldStill.length > 0 && window.heldStill.every(Boolean)")
        assert driver.find_elements(By.ID, "game-frame") == []
    finally:
        plain_device(driver)


def test_orb_theme_menu_moves_with_the_arrow_keys(driver, live):
    live.hub.config.globals["look"] = {"theme": "orb"}
    open_menu(driver, live, DISCORD_QUERY)
    assert driver.execute_script(f"return {PILLS}") == ["second", "demo", ""]
    assert driver.execute_script(f"return {SELECTED}") == "second"
    assert driver.find_element(By.CSS_SELECTOR, "#orb-screen .screen-name").text.lower() == "alpha game"
    assert driver.find_element(By.CSS_SELECTOR, ".orb").is_displayed()
    assert not driver.find_element(By.ID, "gear").is_displayed()
    assert no_sideways_scroll(driver)
    press(driver, Keys.ARROW_DOWN)
    assert driver.execute_script(f"return {SELECTED}") == "demo"
    assert driver.find_element(By.CSS_SELECTOR, "#orb-screen .screen-name").text.lower() == "demo"
    press(driver, Keys.ENTER)
    src = wait_for(driver, "document.getElementById('game-frame') && document.getElementById('game-frame').src")
    assert "/games/demo/" in src
    wait_for(driver, "document.body.classList.contains('playing')")
    assert not driver.find_element(By.CSS_SELECTOR, ".orb").is_displayed()
    driver.execute_script("window.activityhubHost.closeGame()")
    wait_for(driver, f"{SELECTED} === 'demo' && document.activeElement.dataset.key === 'demo'")


def test_orb_wheel_and_arrows_scroll_a_long_list(driver, live, tmp_path):
    for i in range(10):
        folder = write_demo_web(tmp_path / f"extra{i}")
        register(live.hub, DemoCog(folder, key=f"extra{i}", name=f"Extra {i}", cog_name=f"Extra{i}"))
    live.hub.config.globals["look"] = {"theme": "orb"}
    open_menu(driver, live)
    up, down = (driver.find_element(By.CSS_SELECTOR, f".orb-arrow.{side}") for side in ("up", "down"))
    assert driver.execute_script(f"return {SELECTED}") == "second"
    assert down.is_displayed() and not up.is_displayed()
    # One notch of a mouse wheel moves one pill
    wheel = "document.dispatchEvent(new WheelEvent('wheel', {deltaY: %d, cancelable: true}))"
    driver.execute_script(wheel % 100)
    assert driver.execute_script(f"return {SELECTED}") == "demo"
    for _ in range(8):
        down.click()
    # The rows scrolled to keep the selection on the ring, so there are pills above it now
    wait_for(driver, "!document.querySelector('.orb-arrow.up').hidden")
    assert driver.execute_script(f"return {SELECTED}") == "extra7"
    assert not driver.execute_script(
        "return document.querySelector('#games .pill.selected').classList.contains('off-ring')"
    )
    driver.execute_script(wheel % -100)
    assert driver.execute_script(f"return {SELECTED}") == "extra6"


def mouse(driver, kind, x, y, **extra):
    """A real mouse event, so the browser also works out what's under the pointer, like with a hand on the mouse"""
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, **extra})


# The middle of a pill's tab, and its key
PILL_SPOT = """
const pill = document.querySelector(arguments[0]);
const plate = pill.querySelector('.plate').getBoundingClientRect();
return [pill.dataset.key, plate.left + 30, plate.top + plate.height / 2];
"""


def test_orb_wheel_scrolls_the_whole_list_with_the_mouse_on_the_ring(driver, live, tmp_path):
    for i in range(10):
        folder = write_demo_web(tmp_path / f"extra{i}")
        register(live.hub, DemoCog(folder, key=f"extra{i}", name=f"Extra {i}", cog_name=f"Extra{i}"))
    open_menu(driver, live, DISCORD_QUERY)
    wait_for(driver, SETTLED)
    pills = driver.execute_script(f"return {PILLS}")
    # Pointing at a pill selects it
    key, x, y = driver.execute_script(PILL_SPOT, "#games .pill:nth-child(3)")
    mouse(driver, "mouseMoved", x, y)
    wait_for(driver, f"{SELECTED} === {key!r}")
    # Each notch moves one pill to the end of the list, though the ring scrolls other pills under the still mouse
    for key in pills[3:]:
        mouse(driver, "mouseWheel", x, y, deltaX=0, deltaY=100)
        wait_for(driver, SETTLED)
        assert driver.execute_script(f"return {SELECTED}") == key
    assert driver.execute_script("return document.body.classList.contains('hover-held')")
    # A nudge of the hand on the mouse leaves the selection alone
    mouse(driver, "mouseMoved", x + 4, y)
    wait_for(driver, SETTLED)
    assert driver.execute_script(f"return {SELECTED}") == pills[-1]
    # Moving the mouse onto a pill selects it again
    key, x, y = driver.execute_script(PILL_SPOT, "#games .pill:not(.off-ring)")
    mouse(driver, "mouseMoved", x, y)
    wait_for(driver, f"{SELECTED} === {key!r}")
    assert not driver.execute_script("return document.body.classList.contains('hover-held')")


def test_frame_rate_counter_shows_by_default_and_each_player_can_hide_it(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    open_menu(driver, live, DISCORD_QUERY)
    assert wait_for(driver, "/^\d+ FPS$/.test(document.querySelector('.fps').textContent)")
    counter = driver.find_element(By.CSS_SELECTOR, ".fps")
    # It stays in the corner while a game is open
    driver.find_element(By.CSS_SELECTOR, '#games .card[data-key="demo"]').click()
    wait_for(driver, "document.body.classList.contains('playing')")
    assert counter.is_displayed()
    driver.execute_script("window.activityhubHost.closeGame()")
    open_settings(driver)
    pick_tab(driver, "look")
    Select(driver.find_element(By.ID, "field-fps")).select_by_value("false")
    assert not counter.is_displayed()
    save(driver)
    assert live.hub.config.users[MEMBER_ID]["look"] == {"fps": False}


def test_a_live_game_shows_its_delay_and_its_own_figure_after_the_frame_rate(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    driver.find_element(By.CSS_SELECTOR, '#games .card[data-key="demo"]').click()
    # The demo game opens a live connection, so the hub times a round trip by itself
    assert wait_for(driver, rf"/^\d+ FPS · \d+ ms$/.test({COUNTER})")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "window.demo && window.demo.done")
    driver.execute_async_script(SHOW_STAT, "30 TPS")
    driver.switch_to.default_content()
    assert wait_for(driver, rf"/^\d+ FPS · \d+ ms · 30 TPS$/.test({COUNTER})")
    # The pill is small, so a long text is cut to fit
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    driver.execute_async_script(SHOW_STAT, "x" * 100)
    driver.switch_to.default_content()
    assert wait_for(driver, rf"/^\d+ FPS · \d+ ms · x{{40}}$/.test({COUNTER})")
    # The next game starts without either
    driver.execute_script("window.activityhubHost.closeGame()")
    assert wait_for(driver, rf"/^\d+ FPS$/.test({COUNTER})")


@pytest.mark.parametrize("look", [{"theme": "standard"}, {"theme": "orb"}], ids=["standard", "orb"])
def test_the_header_sits_below_discords_buttons_on_a_phone(driver, live, look):
    live.hub.config.globals["look"] = look
    open_menu(driver, live, DISCORD_QUERY)
    # Discord's phone app sets this on the menu's page, for the room its back pill and Leave button take
    driver.execute_script("document.documentElement.style.setProperty('--discord-safe-area-inset-top', '40px')")
    assert driver.execute_script("return document.getElementById('who-name').getBoundingClientRect().top") >= 40


def test_orb_theme_on_a_phone(driver, live, tmp_path):
    # A name too long for its tab is cut short inside it, not pushed off the side of the screen
    long_name = "A game with a name long enough to run off the screen"
    register(live.hub, DemoCog(write_demo_web(tmp_path / "long"), key="long", name=long_name, cog_name="Long"))
    live.hub.config.globals["look"] = {"theme": "orb"}
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride", {"width": 375, "height": 740, "deviceScaleFactor": 1, "mobile": True}
    )
    try:
        open_menu(driver, live)
        wait_for(driver, SETTLED)
        # A phone widens the page to fit whatever sticks out, so the page is checked against the phone's width
        assert driver.execute_script("return document.documentElement.scrollWidth") <= 375
        rights = "[...document.querySelectorAll('#games .pill')].map((pill) => pill.getBoundingClientRect().right)"
        assert max(driver.execute_script(f"return {rights}")) <= 375
        # The pods hold the icons, and the panel above the ring shows the selected game's description
        pill = driver.find_element(By.CSS_SELECTOR, '#games .pill[data-key="demo"]')
        assert pill.find_element(By.CSS_SELECTOR, ".pod .icon").is_displayed()
        layout = driver.execute_script(ORB_LAYOUT)
        assert driver.find_element(By.ID, "orb-screen").is_displayed()
        assert all(layout["panel"][3] <= box[1] for box in layout["ring"])
        screen = driver.find_element(By.ID, "orb-screen")
        wait_for(driver, "document.querySelector('#orb-screen .screen-desc').textContent.length > 0")
        assert screen.find_element(By.CSS_SELECTOR, ".screen-desc").is_displayed()
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_orb_sounds_play_on_move_select_and_back(driver, live, sound_spy):
    live.hub.config.globals["look"] = {"theme": "orb"}
    open_menu(driver, live)
    press(driver, Keys.ARROW_DOWN)
    wait_for(driver, f"window.soundLog.includes({MOVE})")
    fetched(driver, "ambient.mp3")
    press(driver, Keys.ENTER)
    wait_for(driver, f"window.soundLog.includes({SELECT}) && document.getElementById('game-frame') !== null")
    driver.execute_script("window.activityhubHost.closeGame()")
    wait_for(driver, f"window.soundLog.includes({BACK})")
    fetched(driver, "menu.mp3")


@pytest.mark.parametrize("look", [{"theme": "orb", "sounds": False}, {"theme": "standard", "sounds": True}])
def test_no_sounds_when_off_or_in_the_standard_theme(driver, live, sound_spy, look):
    live.hub.config.globals["look"] = look
    open_menu(driver, live)
    press(driver, Keys.ARROW_DOWN)
    driver.find_element(By.CSS_SELECTOR, '#games .card[data-key="demo"]').click()
    wait_for(driver, "document.getElementById('game-frame') !== null")
    driver.execute_script("window.activityhubHost.closeGame()")
    time.sleep(0.3)
    assert sounds(driver) == []


def test_orb_settings_pill_and_theme_fields(driver, live):
    live.hub.config.globals["look"] = {"theme": "orb"}
    open_menu(driver, live, DISCORD_QUERY)
    driver.find_element(By.CSS_SELECTOR, "#games .settings-pill").click()
    wait_for(driver, "getComputedStyle(document.getElementById('panel')).transform === 'none'")
    assert driver.find_element(By.CSS_SELECTOR, "#orb-screen .screen-name").text.lower() == "settings"
    fields = "[...document.querySelectorAll('#tab-body [id^=field-]')].map((field) => field.id)"
    assert driver.execute_script(f"return {fields}") == [
        "field-theme",
        "field-glow",
        "field-details",
        "field-sounds",
        "field-fps",
    ]
    Select(driver.find_element(By.ID, "field-theme")).select_by_value("standard")
    assert driver.execute_script("return document.body.dataset.theme") == "standard"

    assert driver.execute_script(f"return {fields}") == [
        "field-theme",
        "field-layout",
        "field-accent",
        "field-background",
        "field-details",
        "field-fps",
    ]
    save(driver)
    assert live.hub.config.users[MEMBER_ID]["look"] == {"theme": "standard"}


def test_orb_glow_color_recolors_the_theme_and_saves(driver, live):
    live.hub.config.globals["look"] = {"theme": "orb"}
    open_menu(driver, live, DISCORD_QUERY)
    tone = "getComputedStyle(document.documentElement).getPropertyValue('--orb-main').trim()"
    assert driver.execute_script(f"return {tone}") == "143 220 38"
    driver.find_element(By.CSS_SELECTOR, "#games .settings-pill").click()
    wait_for(driver, "getComputedStyle(document.getElementById('panel')).transform === 'none'")
    driver.find_element(By.CSS_SELECTOR, '#field-glow .swatch[data-swatch="#ED4245"]').click()
    # The preview turns the theme red at once: red stays the strongest of the three
    red, green, blue = (int(v) for v in driver.execute_script(f"return {tone}").split())
    assert red > green and red > blue
    save(driver)
    assert live.hub.config.users[MEMBER_ID]["look"] == {"glow": "#ED4245"}
    # The Standard theme's accent is its own color, and the glow doesn't change it
    Select(driver.find_element(By.ID, "field-theme")).select_by_value("standard")
    assert (
        driver.find_element(By.CSS_SELECTOR, '#field-accent .swatch[data-swatch="default"]').get_attribute(
            "aria-pressed"
        )
        == "true"
    )


def test_orb_select_prompt_opens_the_selected_game(driver, live):
    live.hub.config.globals["look"] = {"theme": "orb"}
    open_menu(driver, live, DISCORD_QUERY)
    press(driver, Keys.ARROW_DOWN)
    assert driver.execute_script(f"return {SELECTED}") == "demo"
    driver.find_element(By.CSS_SELECTOR, "#orb-screen .screen-select").click()
    src = wait_for(driver, "document.getElementById('game-frame') && document.getElementById('game-frame').src")
    assert "/games/demo/" in src


def test_orb_menu_survives_a_resize_behind_a_game(driver, live):
    live.hub.config.globals["look"] = {"theme": "orb"}
    open_menu(driver, live, DISCORD_QUERY)
    driver.find_element(By.CSS_SELECTOR, '#games .pill[data-key="demo"]').click()
    wait_for(driver, "document.body.classList.contains('playing')")
    console_lines(driver)
    # Behind a game the scene is hidden and has no size; the menu lays itself out again once it shows
    driver.set_window_size(1000, 700)
    driver.execute_script("window.activityhubHost.closeGame()")
    wait_for(driver, f"{SELECTED} === 'demo'")
    assert [line for line in console_lines(driver) if "Error" in line] == []
    pill = driver.find_element(By.CSS_SELECTOR, '#games .pill[data-key="demo"]').rect
    assert 0 < pill["x"] < driver.execute_script("return innerWidth")


def test_orb_settings_close_button_closes_the_panel(driver, live):
    live.hub.config.globals["look"] = {"theme": "orb"}
    open_menu(driver, live, DISCORD_QUERY)
    driver.find_element(By.CSS_SELECTOR, "#games .settings-pill").click()
    wait_for(driver, "getComputedStyle(document.getElementById('panel')).transform === 'none'")
    # A real click, so anything drawn over the button would intercept it and fail the test
    driver.find_element(By.ID, "close").click()
    wait_for(driver, "!document.body.classList.contains('panel-open')")


@pytest.mark.parametrize("layout", ["grid", "list", "compact"])
def test_thumbnail_by_layout(driver, live, tmp_path, layout):
    add_thumbnail_game(live, tmp_path)
    live.hub.config.globals["look"] = {"theme": "standard", "layout": layout}
    open_menu(driver, live)
    card = driver.find_element(By.CSS_SELECTOR, '#games .card[data-key="third"]')
    thumb = card.find_element(By.CSS_SELECTOR, ".thumb")
    wait_for(driver, "document.querySelector('.card[data-key=third] .thumb').complete")
    assert thumb.get_attribute("src").endswith("/thumb.svg")
    assert thumb.is_displayed() is (layout != "compact")
    assert card.find_element(By.CSS_SELECTOR, ".icon").is_displayed() is (layout == "compact")
    if layout == "grid":
        # The picture spans the card's width at 16:9
        assert abs(thumb.size["width"] - card.size["width"]) <= 2
        assert abs(thumb.size["height"] - thumb.size["width"] * 9 / 16) <= 2


def test_missing_thumbnail_falls_back_to_the_icon(driver, live, tmp_path):
    live.hub.config.globals["look"] = {"theme": "standard"}
    folder = add_thumbnail_game(live, tmp_path)
    (folder / "thumb.svg").unlink()
    open_menu(driver, live)
    wait_for(driver, "!document.querySelector('.card[data-key=third]').classList.contains('has-thumb')")
    card = driver.find_element(By.CSS_SELECTOR, '#games .card[data-key="third"]')
    assert card.find_element(By.CSS_SELECTOR, ".icon").is_displayed()
    assert not card.find_elements(By.CSS_SELECTOR, ".thumb")


def test_orb_screen_shows_the_thumbnail(driver, live, tmp_path):
    add_thumbnail_game(live, tmp_path)
    live.hub.config.globals["look"] = {"theme": "orb"}
    open_menu(driver, live)
    driver.execute_script("document.querySelector('#games .pill[data-key=third]').focus()")
    picture = driver.find_element(By.CSS_SELECTOR, "#orb-screen .screen-picture .thumb")
    assert picture.get_attribute("src").endswith("/thumb.svg") and picture.is_displayed()
    driver.execute_script("document.querySelector('#games .pill[data-key=demo]').focus()")
    assert driver.find_element(By.CSS_SELECTOR, "#orb-screen .screen-icon").is_displayed()


def test_first_menu_comes_with_the_login(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    asked = driver.execute_script("return performance.getEntriesByType('resource').map((entry) => entry.name)")
    assert any("/hub/api/token" in name for name in asked)
    assert not any("/hub/api/menu" in name or "/hub/api/config" in name for name in asked)
    wait_for(driver, "window.fakeDiscord.authenticate === 1")


BUBBLE = "document.querySelector('.card[data-key=\"demo\"] .bubble')"
HOVER = "document.getElementById('hover-people')"
DEMO_CARD = '.card[data-key="demo"]'
PEOPLE_ROW = "document.getElementById('people-row')"


def hover_demo(driver):
    """The mouse rests on the demo card until its players show"""
    ActionChains(driver).move_to_element(driver.find_element(By.CSS_SELECTOR, DEMO_CARD)).perform()
    wait_for(driver, f"!{HOVER}.hidden")


def person_status(driver, user_id, status):
    wait_for(driver, f"window.activityhubHost.presence.people.find((p) => p.id === '{user_id}')?.status === '{status}'")


def tap(driver, x, y):
    for kind, points in (("touchStart", [{"x": x, "y": y}]), ("touchEnd", [])):
        driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})


def test_bubbles_count_people_in_each_game(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    assert driver.execute_script("return document.querySelectorAll('#games .bubble').length") == 0
    live.add_person(MANAGER_ID, where="demo", status="Clicking")
    assert wait_for(driver, f"{BUBBLE}?.textContent") == "1"
    live.add_person(ADMIN_ID, where="demo")
    assert wait_for(driver, f"{BUBBLE}?.textContent === '2' && {BUBBLE}.getAttribute('aria-label')") == "2 playing Demo"


def test_hovering_a_card_lists_its_players(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo", status="Clicking")
    live.add_person(ADMIN_ID, where="demo", instance="i-2")
    wait_for(driver, BUBBLE)
    hover_demo(driver)
    text = wait_for(driver, f"{HOVER}.innerText")
    assert "Manager" in text and "Clicking" in text and "+1 playing in another channel" in text
    # The list stays while the mouse moves onto it, so its Join button can be pressed
    ActionChains(driver).move_to_element(
        driver.find_element(By.CSS_SELECTOR, "#hover-people .hub-join")
    ).click().perform()
    wait_for(driver, "document.body.classList.contains('playing')")
    assert driver.execute_script("return window.activityhubHost.follow") == {"id": str(MANAGER_ID), "name": "Manager"}


def test_tapping_the_bubble_opens_the_list_not_the_game(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "list"}
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo")
    wait_for(driver, BUBBLE)
    driver.execute_script(f"{BUBBLE}.click()")
    wait_for(driver, f"!{HOVER}.hidden")
    assert not driver.execute_script("return document.body.classList.contains('opening')")
    # A second tap puts it away again
    driver.execute_script(f"{BUBBLE}.click()")
    wait_for(driver, f"{HOVER}.hidden")


def test_alone_shows_invite_and_no_bubbles(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    wait_for(driver, f"!{PEOPLE_ROW}.hidden")
    assert driver.find_element(By.CSS_SELECTOR, "#people-row .invite-pill").text == "Invite friends"
    assert driver.execute_script("return document.querySelectorAll('#games .bubble').length") == 0
    driver.find_element(By.CSS_SELECTOR, "#people-row .invite-pill").click()
    assert wait_for(driver, "window.fakeDiscord.invite") == 1


def test_the_header_shows_everyone_else(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo")
    live.add_person(ADMIN_ID, away=True)
    wait_for(driver, "document.querySelectorAll('#people-row .face').length === 2")
    assert driver.execute_script("return document.querySelectorAll('#people-row .face .game-badge').length") == 1
    assert driver.execute_script("return document.querySelectorAll('#people-row .hub-avatar.away').length") == 1
    driver.find_element(By.CSS_SELECTOR, "#people-row .people-stack").click()
    wait_for(driver, "!document.querySelector('.hub-people-panel').hidden")


def test_the_orb_screen_lists_who_is_playing(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo", status="Clicking")
    driver.execute_script("document.querySelector('.pill[data-key=\"demo\"]').focus()")
    text = wait_for(
        driver, "document.querySelector('#orb-screen .screen-face:not(.leaving) .screen-people')?.innerText"
    )
    # The title is set in capitals, which innerText reports
    assert "playing now" in text.lower() and "Manager" in text


def test_no_bubbles_and_no_row_once_the_menu_link_is_gone(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo")
    wait_for(driver, BUBBLE)
    wait_for(driver, f"!{PEOPLE_ROW}.hidden")
    # What the menu link does when it gives up for good: an empty list for every page
    driver.execute_script("const p = window.activityhubHost.presence; p.people = []; p.elsewhere = {}; p.notify([])")
    wait_for(driver, f"{BUBBLE} === null && {PEOPLE_ROW}.hidden")


def test_a_hover_join_click_survives_a_list_arriving_mid_press(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    conn = live.add_person(MANAGER_ID, where="demo", status="one")
    wait_for(driver, BUBBLE)
    hover_demo(driver)
    join = driver.find_element(By.CSS_SELECTOR, "#hover-people .hub-join")
    ActionChains(driver).move_to_element(join).click_and_hold().perform()
    try:
        # The status line changes, which redraws the list unless a press is under way in it
        live.update_person(conn, where="demo", status="two")
        person_status(driver, MANAGER_ID, "two")
        assert "two" not in driver.execute_script(f"return {HOVER}.innerText")
    finally:
        ActionChains(driver).release().perform()
    wait_for(driver, "document.body.classList.contains('playing')")


def test_the_hover_list_catches_up_once_the_press_ends(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    conn = live.add_person(MANAGER_ID, where="demo", status="one")
    wait_for(driver, BUBBLE)
    hover_demo(driver)
    # A press on the list's own text, which is no button, still holds the list as it is
    name = driver.find_element(By.CSS_SELECTOR, "#hover-people .hub-person-name")
    ActionChains(driver).move_to_element(name).click_and_hold().perform()
    try:
        live.update_person(conn, where="demo", status="two")
        person_status(driver, MANAGER_ID, "two")
        assert "two" not in driver.execute_script(f"return {HOVER}.innerText")
    finally:
        ActionChains(driver).release().perform()
    wait_for(driver, f"{HOVER}.innerText.includes('two')")


def test_a_space_press_on_a_hover_join_survives_a_list_arriving(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    conn = live.add_person(MANAGER_ID, where="demo", status="one")
    wait_for(driver, BUBBLE)
    hover_demo(driver)
    driver.execute_script(f"{HOVER}.querySelector('.hub-join').focus()")
    ActionChains(driver).key_down(Keys.SPACE).perform()
    try:
        live.update_person(conn, where="demo", status="two")
        person_status(driver, MANAGER_ID, "two")
    finally:
        ActionChains(driver).key_up(Keys.SPACE).perform()
    wait_for(driver, "document.body.classList.contains('playing')")


def test_lists_that_change_nothing_shown_are_not_drawn_again(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    conn = live.add_person(MANAGER_ID, where="demo", status="one")
    wait_for(driver, BUBBLE)
    hover_demo(driver)
    wait_for(driver, f"{PEOPLE_ROW}.querySelector('.face')")
    driver.execute_script(
        f"window.listRow = {HOVER}.querySelector('.hub-person'); window.stack = {PEOPLE_ROW}.querySelector('.people-stack')"
    )
    # The game's data isn't shown in either place
    live.update_person(conn, where="demo", status="one", data={"wave": 4})
    wait_for(driver, "window.activityhubHost.presence.people.find((p) => p.id === '3').data?.wave === 4")
    assert driver.execute_script(f"return window.listRow === {HOVER}.querySelector('.hub-person')")
    assert driver.execute_script(f"return window.stack === {PEOPLE_ROW}.querySelector('.people-stack')")
    # A new status line is drawn in the list, and only changes the faces' tooltips
    live.update_person(conn, where="demo", status="two", data={"wave": 4})
    wait_for(driver, f"{HOVER}.innerText.includes('two')")
    assert driver.execute_script(f"return window.listRow !== {HOVER}.querySelector('.hub-person')")
    assert driver.execute_script(f"return window.stack === {PEOPLE_ROW}.querySelector('.people-stack')")
    assert driver.execute_script(f"return {PEOPLE_ROW}.querySelector('.face').title") == "Manager: two"


def test_the_header_row_waits_out_a_press(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo")
    wait_for(driver, "document.querySelectorAll('#people-row .face').length === 1")
    stack = driver.find_element(By.CSS_SELECTOR, "#people-row .people-stack")
    ActionChains(driver).move_to_element(stack).click_and_hold().perform()
    try:
        # Someone else arrives, which redraws the row unless a press is under way in it
        live.add_person(ADMIN_ID, away=True)
        wait_for(driver, "window.activityhubHost.presence.people.length === 3")
        assert driver.execute_script("return document.querySelectorAll('#people-row .face').length") == 1
    finally:
        ActionChains(driver).release().perform()
    wait_for(driver, "!document.querySelector('.hub-people-panel').hidden")
    wait_for(driver, "document.querySelectorAll('#people-row .face').length === 2")


def test_the_orb_screen_join_survives_a_list_arriving_mid_press(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    conn = live.add_person(MANAGER_ID, where="demo", status="one")
    driver.execute_script("document.querySelector('.pill[data-key=\"demo\"]').focus()")
    wait_for(driver, "document.querySelector('#orb-screen .screen-face:not(.leaving) .screen-people .hub-join')")
    wait_for(driver, SETTLED)
    join = driver.find_element(By.CSS_SELECTOR, "#orb-screen .screen-face:not(.leaving) .hub-join")
    ActionChains(driver).move_to_element(join).click_and_hold().perform()
    try:
        live.update_person(conn, where="demo", status="two")
        person_status(driver, MANAGER_ID, "two")
    finally:
        ActionChains(driver).release().perform()
    wait_for(driver, "document.body.classList.contains('playing')")
    assert driver.execute_script("return window.activityhubHost.follow.name") == "Manager"


def test_a_pod_bubble_only_selects_the_pod_when_the_screen_lists_the_players(driver, live):
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo")
    pod = '.pill[data-key="demo"] .pod .bubble'
    wait_for(driver, f"document.querySelector('{pod}')?.textContent === '1'")
    wait_for(driver, SETTLED)
    driver.find_element(By.CSS_SELECTOR, pod).click()
    wait_for(driver, f"{SELECTED} === 'demo'")
    assert driver.execute_script(f"return {HOVER}.hidden")
    assert not driver.execute_script("return document.body.classList.contains('opening')")


def test_on_an_upright_phone_the_orb_bubble_opens_the_list_beside_the_pod(driver, live):
    touch_device(driver, 390, 844)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        live.add_person(MANAGER_ID, where="demo", status="Clicking")
        pod = '.pill[data-key="demo"] .pod .bubble'
        wait_for(driver, f"document.querySelector('{pod}')?.textContent === '1'")
        wait_for(driver, SETTLED)
        box = driver.execute_script(f"return document.querySelector('{pod}').getBoundingClientRect().toJSON()")
        tap(driver, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        wait_for(driver, f"!{HOVER}.hidden")
        assert "Manager" in driver.execute_script(f"return {HOVER}.innerText")
        # The panel on this screen is a fixed size with no room for players, so the list opens in its place
        screen = "document.querySelector('#orb-screen .screen-face:not(.leaving) .screen-people')"
        assert driver.execute_script(f"return {screen}.dataset.key") == "demo"
        assert driver.execute_script(f"return !{screen}.getClientRects().length")
        assert driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth")
        assert not driver.execute_script("return document.body.classList.contains('opening')")
    finally:
        plain_device(driver)


# Puts a crowd in the page's people list the way the menu link would: this player, then `count` others in `game`
CROWD = """
const [count, game, elsewhere] = arguments;
const p = window.activityhubHost.presence;
const people = [{ id: p.me, name: 'Me', avatar: null, game: null, status: '', data: null, busy: false, away: false }];
for (let i = 0; i < count; i++) {
  people.push({
    id: String(100 + i), name: 'Player ' + i, avatar: null, game, status: 'Playing', data: null, busy: false, away: false,
  });
}
// The bot's own lists are ignored from here on, or the next one would take the crowd away again
p.receive = () => {};
p.people = people;
p.elsewhere = elsewhere;
p.notify([]);
"""
BOX_RECT = "const r = document.getElementById('hover-people').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]"


class NoIconCog(DemoCog):
    """A game with no picture of its own"""

    async def activityhub_game(self) -> dict:
        desc = await super().activityhub_game()
        del desc["icon"]
        return desc


def crowd(driver, count, game="demo", elsewhere=None):
    wait_for(driver, "window.activityhubHost.presence.people.length > 0")
    driver.execute_script(CROWD, count, game, elsewhere or {})


def viewport(driver, width, height):
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )


def inside_the_screen(driver, selector):
    return driver.execute_script(
        f"const r = document.querySelector('{selector}').getBoundingClientRect();"
        "return r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth"
    )


def test_the_hover_list_moves_with_its_card_when_the_page_scrolls(driver, live, tmp_path):
    for i in range(8):
        folder = write_demo_web(tmp_path / f"extra{i}")
        register(live.hub, DemoCog(folder, key=f"extra{i}", name=f"Extra {i}", cog_name=f"Extra{i}"))
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "list"}
    viewport(driver, 1280, 420)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        live.add_person(MANAGER_ID, where="demo")
        wait_for(driver, BUBBLE)
        hover_demo(driver)
        gap = f"{HOVER}.getBoundingClientRect().top - document.querySelector('{DEMO_CARD}').getBoundingClientRect().bottom"
        before = driver.execute_script(f"return {gap}")
        driver.execute_script("window.scrollBy(0, 40)")
        wait_for(driver, "window.scrollY > 0")
        wait_for(driver, f"Math.abs(({gap}) - {before}) < 1")
    finally:
        plain_device(driver)


@pytest.mark.parametrize(("width", "height", "layout"), [(1280, 568, "grid"), (390, 844, "list")])
def test_a_crowded_hover_list_stays_on_the_screen_and_scrolls(driver, live, width, height, layout):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": layout}
    viewport(driver, width, height)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        crowd(driver, 20)
        wait_for(driver, BUBBLE)
        driver.execute_script(f"{BUBBLE}.click()")
        wait_for(driver, f"!{HOVER}.hidden")
        assert inside_the_screen(driver, "#hover-people")
        # There are more rows than fit, and the last Join is reached by scrolling to it
        assert driver.execute_script(f"return {HOVER}.scrollHeight > {HOVER}.clientHeight")
        driver.execute_script(f"{HOVER}.scrollTop = {HOVER}.scrollHeight")
        last = driver.find_elements(By.CSS_SELECTOR, "#hover-people .hub-join")[-1]
        assert len(driver.find_elements(By.CSS_SELECTOR, "#hover-people .hub-join")) == 20
        box = driver.execute_script(BOX_RECT)
        assert box[1] <= last.rect["y"] and last.rect["y"] + last.rect["height"] <= box[3] + 1
        last.click()
        wait_for(driver, "document.body.classList.contains('playing')")
    finally:
        plain_device(driver)


def test_a_full_orb_screen_leaves_its_list_out_when_the_select_prompt_would_not_fit(driver, live):
    viewport(driver, 1082, 568)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        driver.execute_script("document.querySelector('.pill[data-key=\"demo\"]').focus()")
        crowd(driver, 7, elsewhere={"demo": 3})
        pod = '.pill[data-key="demo"] .pod .bubble'
        wait_for(driver, f"document.querySelector('{pod}')?.textContent === '7'")
        wait_for(driver, "document.getElementById('orb-screen').classList.contains('no-room')")
        assert inside_the_screen(driver, "#orb-screen .screen-select")
        assert driver.execute_script(
            "return !document.querySelector('.screen-face .screen-people').getClientRects().length"
        )
        # The bubble opens the hover list in its place, and the list shows everyone
        wait_for(driver, SETTLED)
        driver.find_element(By.CSS_SELECTOR, pod).click()
        wait_for(driver, f"!{HOVER}.hidden")
        assert driver.execute_script(f"return {HOVER}.querySelectorAll('.hub-person').length") == 7
        # With room for the list again it goes back in, and the Select prompt is still on the screen
        viewport(driver, 1280, 1000)
        wait_for(driver, "!document.getElementById('orb-screen').classList.contains('no-room')")
        assert driver.execute_script(
            "return document.querySelector('.screen-face .screen-people').getClientRects().length > 0"
        )
        assert inside_the_screen(driver, "#orb-screen .screen-select")
    finally:
        plain_device(driver)


# What the header row looks like next to the server's name: whether it is clipped, what the name kept, and what the
# faces and the count add up to
HEADER_FIT = """
const stack = document.querySelector('#people-row .people-stack');
const more = stack.querySelector('.more');
const name = document.getElementById('who-name');
const style = getComputedStyle(name);
const range = document.createRange();
range.selectNodeContents(name);
const text = range.getBoundingClientRect();
const box = stack.getBoundingClientRect();
return {
  faces: stack.querySelectorAll('.face').length,
  count: more ? Number(more.textContent.replace('+', '')) : 0,
  clipped: stack.scrollWidth > stack.clientWidth + 1,
  moreInside: !more || more.getBoundingClientRect().right <= box.right + 1,
  rowFits: box.right <= document.getElementById('people-row').getBoundingClientRect().right + 1 && box.right <= innerWidth,
  textWidth: text.width,
  shown: name.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
  em: parseFloat(style.fontSize),
  gap: box.left - text.right,
};
"""


@pytest.mark.parametrize("theme", ["orb", "standard"])
@pytest.mark.parametrize("name", ["Vert", "Vertyco ARK Gaming Community"])
def test_the_header_row_fits_beside_the_server_name(driver, live, theme, name):
    live.hub.config.globals["look"] = {"theme": theme}
    live.hub.bot.guilds[GUILD_ID].name = name
    touch_device(driver, 390, 844)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        for others in (1, 2, 3, 12):
            crowd(driver, others)
            wait_for(driver, "document.querySelector('#people-row .people-stack')")
            fit = driver.execute_script(HEADER_FIT)
            assert not fit["clipped"] and fit["moreInside"] and fit["rowFits"], (others, fit)
            # The name keeps six em of its text, or all of it when that is shorter
            assert fit["shown"] >= min(fit["textWidth"], 6 * fit["em"]) - 1, (others, fit)
            # Whatever the faces leave out is counted
            assert fit["faces"] + fit["count"] == others, (others, fit)
            if name == "Vert":
                assert fit["gap"] <= 17, (others, fit)
    finally:
        plain_device(driver)


@pytest.mark.parametrize("theme", ["orb", "standard"])
def test_the_header_row_is_never_clipped_when_there_is_no_room_for_a_face(driver, live, theme):
    live.hub.config.globals["look"] = {"theme": theme}
    live.hub.bot.guilds[GUILD_ID].name = "Vertyco ARK Gaming Community"
    touch_device(driver, 320, 640)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        crowd(driver, 12)
        wait_for(driver, "document.querySelector('#people-row .people-stack')")
        fit = driver.execute_script(HEADER_FIT)
        # The count alone, whole, and the name gives way to it
        assert not fit["clipped"] and fit["moreInside"] and fit["rowFits"], fit
        assert fit["faces"] == 0 and fit["count"] == 12, fit
        assert driver.execute_script(
            "return !!document.querySelector('#people-row .people-stack.count-only .hub-icon')"
        )
        if theme == "standard":
            # The row stops short of the settings gear beside it
            row, gear = driver.execute_script(
                "return ['people-row', 'gear'].map((id) => document.getElementById(id).getBoundingClientRect().toJSON())"
            )
            assert gear["width"] > 0 and row["right"] <= gear["left"] + 0.5, (row, gear)
    finally:
        plain_device(driver)


def test_alone_on_a_phone_the_invite_is_its_icon(driver, live):
    touch_device(driver, 390, 844)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        crowd(driver, 0)
        wait_for(driver, "document.querySelector('#people-row .invite-pill.compact')")
        pill = "document.querySelector('#people-row .invite-pill')"
        assert driver.execute_script(
            f"return [{pill}.textContent, {pill}.title, {pill}.getAttribute('aria-label')]"
        ) == ["", "Invite friends", "Invite friends"]
    finally:
        plain_device(driver)


def test_the_header_row_is_fitted_again_when_the_window_changes(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard"}
    live.hub.bot.guilds[GUILD_ID].name = "Vertyco ARK Gaming Community"
    open_menu(driver, live, DISCORD_QUERY)
    crowd(driver, 12)
    wait_for(driver, "document.querySelectorAll('#people-row .face').length === 5")
    assert driver.execute_script("return document.querySelector('#people-row .more').textContent") == "+7"
    touch_device(driver, 360, 740)
    try:
        wait_for(driver, "document.querySelectorAll('#people-row .face').length < 5")
        fit = driver.execute_script(HEADER_FIT)
        assert not fit["clipped"] and fit["moreInside"] and fit["rowFits"] and fit["faces"] + fit["count"] == 12, fit
    finally:
        plain_device(driver)


def test_settings_previews_keep_the_bubbles(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    live.user_id = OWNER_ID
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo")
    wait_for(driver, f"{BUBBLE}?.textContent === '1'")
    open_settings(driver)
    assert driver.execute_script(f"return {BUBBLE} !== null")
    # Drawing the cards again for a preview isn't a new arrival, so nothing pops
    Select(driver.find_element(By.ID, "field-layout")).select_by_value("list")
    wait_for(driver, "document.getElementById('games').classList.contains('list')")
    assert driver.execute_script(f"return {BUBBLE}?.textContent") == "1"
    assert not driver.execute_script(f"return {BUBBLE}.classList.contains('pop')")


def test_coming_back_from_a_game_does_not_pop_the_bubbles(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo")
    wait_for(driver, f"{BUBBLE}?.classList.contains('pop')")
    driver.execute_script("window.activityhubHost.openGame('second')")
    wait_for(driver, "document.body.classList.contains('playing')")
    driver.execute_script("window.activityhubHost.closeGame()")
    wait_for(driver, f"{BUBBLE}?.textContent === '1'")
    assert not driver.execute_script(f"return {BUBBLE}.classList.contains('pop')")


@pytest.mark.parametrize("layout", ["list", "compact"])
def test_a_long_title_runs_clear_of_the_bubble(driver, live, layout):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": layout}
    touch_device(driver, 390, 844)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        live.add_person(MANAGER_ID, where="demo")
        wait_for(driver, BUBBLE)
        name = f"document.querySelector('{DEMO_CARD} .name')"
        driver.execute_script(f"{name}.textContent = 'Super Long Game Name Deluxe Edition Remastered'")
        clear = driver.execute_script(
            f"""const range = document.createRange(); range.selectNodeContents({name});
            const bubble = {BUBBLE}.getBoundingClientRect();
            return [...range.getClientRects()].every((r) => r.right <= bubble.left || r.bottom <= bubble.top);"""
        )
        assert clear
    finally:
        plain_device(driver)


def test_keyboard_focus_opens_the_list_and_tabbing_away_closes_it(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo", status="Clicking")
    wait_for(driver, BUBBLE)
    driver.execute_script("document.querySelector('.card[data-key=\"second\"]').focus()")
    ActionChains(driver).send_keys(Keys.TAB).perform()
    assert driver.execute_script("return document.activeElement.dataset.key") == "demo"
    wait_for(driver, f"!{HOVER}.hidden")
    # A group of its own with a name, not a tooltip, since it holds buttons
    assert driver.execute_script(f"return [{HOVER}.getAttribute('role'), {HOVER}.getAttribute('aria-label')]") == [
        "group",
        "Playing Demo",
    ]
    # The list comes right after the last card, so the next Tab reaches its Join buttons and keeps it open
    ActionChains(driver).send_keys(Keys.TAB).perform()
    assert driver.execute_script("return document.activeElement.classList.contains('hub-join')")
    time.sleep(0.5)
    assert driver.execute_script(f"return !{HOVER}.hidden")
    # And Tab out of it puts it away
    ActionChains(driver).send_keys(Keys.TAB).perform()
    wait_for(driver, f"{HOVER}.hidden")


def test_focus_going_into_the_list_cancels_a_waiting_swap(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo", status="Clicking")
    wait_for(driver, BUBBLE)
    hover_demo(driver)
    # Focus is on the card (a click on it would open the game, so only focus it), and its card has a timer waiting
    driver.execute_script("document.querySelector('.card[data-key=\"second\"]').focus()")
    driver.execute_script(f"{HOVER}.querySelector('.hub-join').focus()")
    time.sleep(0.6)
    assert driver.execute_script(f"return !{HOVER}.hidden && document.activeElement.classList.contains('hub-join')")


def test_leaving_the_card_closes_the_list(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo")
    wait_for(driver, BUBBLE)
    hover_demo(driver)
    ActionChains(driver).move_by_offset(0, 400).perform()
    wait_for(driver, f"{HOVER}.hidden")


def test_escape_and_a_tap_outside_close_the_list(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo")
    wait_for(driver, BUBBLE)
    driver.execute_script(f"{BUBBLE}.click()")
    wait_for(driver, f"!{HOVER}.hidden")
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    wait_for(driver, f"{HOVER}.hidden")
    driver.execute_script(f"{BUBBLE}.click()")
    wait_for(driver, f"!{HOVER}.hidden")
    # A press inside the list leaves it open, and one anywhere else closes it
    driver.execute_script(f"{HOVER}.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true }}))")
    assert driver.execute_script(f"return !{HOVER}.hidden")
    driver.execute_script("document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))")
    wait_for(driver, f"{HOVER}.hidden")


@pytest.mark.parametrize("layout", ["grid", "list"])
def test_a_touch_on_a_bubble_opens_the_list_and_not_the_game(driver, live, layout):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": layout}
    touch_device(driver, 390, 844)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        live.add_person(MANAGER_ID, where="demo")
        wait_for(driver, BUBBLE)
        box = driver.execute_script(f"return {BUBBLE}.getBoundingClientRect().toJSON()")
        tap(driver, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        wait_for(driver, f"!{HOVER}.hidden")
        time.sleep(0.4)
        assert driver.execute_script(f"return !{HOVER}.hidden")
        assert not driver.execute_script("return document.body.classList.contains('opening')")
        # A tap anywhere else puts it away
        tap(driver, 200, 820)
        wait_for(driver, f"{HOVER}.hidden")
    finally:
        plain_device(driver)


@pytest.mark.parametrize("side", ["left", "right"])
def test_the_hover_list_keeps_clear_of_the_safe_area_at_the_sides(driver, live, side):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "list"}
    viewport(driver, 390, 844)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        # A phone's notch, or Discord's own buttons, take this much room at one side
        driver.execute_script(
            f"document.documentElement.style.setProperty('--discord-safe-area-inset-{side}', '100px');"
            "window.dispatchEvent(new Event('resize'));"
        )
        live.add_person(MANAGER_ID, where="demo")
        wait_for(driver, BUBBLE)
        driver.execute_script(f"{BUBBLE}.click()")
        wait_for(driver, f"!{HOVER}.hidden")
        left, _, right, _ = driver.execute_script(BOX_RECT)
        # 8 px from the screen's edge, and from the safe area's
        low, high = (108, 382) if side == "left" else (8, 282)
        assert left >= low - 0.5 and right <= high + 0.5, (left, right)
    finally:
        plain_device(driver)


def test_a_header_badge_falls_back_to_the_games_first_letter(driver, live, tmp_path):
    live.hub.config.globals["look"] = {"theme": "standard"}
    register(live.hub, NoIconCog(write_demo_web(tmp_path / "quiet"), key="quiet", name="Quiet Game", cog_name="Quiet"))
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="quiet")
    wait_for(driver, "document.querySelector('#people-row .face .game-badge')")
    badge = "document.querySelector('#people-row .face .game-badge')"
    assert driver.execute_script(f"return [{badge}.tagName, {badge}.textContent]") == ["SPAN", "Q"]


def test_a_long_list_scrolls_in_the_orb_by_wheel_and_by_touch(driver, live):
    touch_device(driver, 390, 844)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        crowd(driver, 20)
        pod = '.pill[data-key="demo"] .pod .bubble'
        wait_for(driver, f"document.querySelector('{pod}')")
        wait_for(driver, SETTLED)
        driver.execute_script(f"document.querySelector('{pod}').click()")
        wait_for(driver, f"!{HOVER}.hidden")
        box = driver.execute_script(BOX_RECT)
        x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        # A finger drag scrolls the list and doesn't move the Orb's selection
        slide(driver, (x, y + 100), (x, y - 100))
        wait_for(driver, f"{HOVER}.scrollTop > 0")
        assert driver.execute_script(f"return {SELECTED}") == "demo"
        # So does the wheel (here back up), which would otherwise turn the Orb
        before = driver.execute_script(f"return {HOVER}.scrollTop")
        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": -120}
        )
        wait_for(driver, f"{HOVER}.scrollTop < {before}")
        assert driver.execute_script(f"return {SELECTED}") == "demo"
    finally:
        plain_device(driver)


PANEL_BODY = "document.querySelector('.hub-people-panel .hub-panel-body')"
PANEL_RECT = f"const r = {PANEL_BODY}.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]"


def open_crowded_people_panel(driver, live):
    """The Orb menu with the people panel open over it, holding more people than fit"""
    open_menu(driver, live, DISCORD_QUERY)
    crowd(driver, 30)
    wait_for(driver, SETTLED)
    driver.execute_script("window.activityhubHost.people.open()")
    wait_for(driver, f"{PANEL_BODY}.scrollHeight > {PANEL_BODY}.clientHeight")
    # Measured once the panel has slid all the way in
    wait_for(driver, SETTLED)
    box = driver.execute_script(PANEL_RECT)
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def test_the_people_panel_scrolls_over_the_orb_by_touch(driver, live):
    touch_device(driver, 390, 844)
    try:
        x, y = open_crowded_people_panel(driver, live)
        selected = driver.execute_script(f"return {SELECTED}")
        # A finger drag scrolls the panel, and the ring behind it stays where it was
        slide(driver, (x, y + 100), (x, y - 100))
        wait_for(driver, f"{PANEL_BODY}.scrollTop > 0")
        assert driver.execute_script(f"return {SELECTED}") == selected
    finally:
        plain_device(driver)


def wheel_at(driver, x, y):
    """Two notches of a mouse wheel, down, with the mouse at x, y"""
    driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": 240}
    )


def test_the_people_panel_scrolls_over_the_orb_by_wheel_and_keeps_its_keys(driver, live):
    driver.set_window_size(1280, 600)
    x, y = open_crowded_people_panel(driver, live)
    selected = driver.execute_script(f"return {SELECTED}")
    wheel_at(driver, x, y)
    wait_for(driver, f"{PANEL_BODY}.scrollTop > 0")
    # The arrow keys belong to the panel too, not the ring behind it
    ActionChains(driver).send_keys(Keys.ARROW_DOWN).perform()
    assert driver.execute_script(f"return {SELECTED}") == selected
    # Once the panel closes, the ring takes the wheel again
    driver.execute_script("window.activityhubHost.people.close()")
    wheel_at(driver, x, y)
    wait_for(driver, f"{SELECTED} !== '{selected}'")


def tab_to_a_hover_join(driver):
    """Focus on the last card, then Tab into the list that follows it"""
    driver.execute_script("document.querySelector('.card[data-key=\"second\"]').focus()")
    ActionChains(driver).send_keys(Keys.TAB).perform()
    wait_for(driver, f"!{HOVER}.hidden")
    ActionChains(driver).send_keys(Keys.TAB).perform()
    assert driver.execute_script("return document.activeElement.classList.contains('hub-join')")


def test_focus_stays_on_a_hover_join_when_the_list_is_drawn_again(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo", status="Clicking")
    wait_for(driver, BUBBLE)
    tab_to_a_hover_join(driver)
    live.add_person(ADMIN_ID, where="demo")
    wait_for(driver, f"{HOVER}.querySelectorAll('.hub-person').length === 2")
    time.sleep(0.5)
    assert driver.execute_script("return document.activeElement.dataset.join") == str(MANAGER_ID)
    assert driver.execute_script(f"return !{HOVER}.hidden")


def test_escape_in_the_list_puts_focus_back_on_its_card(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    live.add_person(MANAGER_ID, where="demo", status="Clicking")
    wait_for(driver, BUBBLE)
    tab_to_a_hover_join(driver)
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    wait_for(driver, f"{HOVER}.hidden")
    assert driver.execute_script("return document.activeElement.dataset.key") == "demo"
    # Back on its card, the list Escape closed stays closed
    time.sleep(0.6)
    assert driver.execute_script(f"return {HOVER}.hidden")


def test_focus_goes_back_to_the_card_when_the_last_player_in_its_list_leaves(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    conn = live.add_person(MANAGER_ID, where="demo", status="Clicking")
    wait_for(driver, BUBBLE)
    tab_to_a_hover_join(driver)
    live.update_person(conn, where=None)
    wait_for(driver, f"{HOVER}.hidden")
    assert driver.execute_script("return document.activeElement.dataset.key") == "demo"


def test_focus_goes_to_the_list_when_the_person_it_was_on_leaves(driver, live):
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    open_menu(driver, live, DISCORD_QUERY)
    conn = live.add_person(MANAGER_ID, where="demo", status="Clicking")
    live.add_person(ADMIN_ID, where="demo")
    wait_for(driver, f"{BUBBLE}?.textContent === '2'")
    tab_to_a_hover_join(driver)
    assert driver.execute_script("return document.activeElement.dataset.join") == str(MANAGER_ID)
    live.update_person(conn, where=None)
    wait_for(driver, f"{HOVER}.querySelectorAll('.hub-person').length === 1")
    time.sleep(0.5)
    assert driver.execute_script("return document.activeElement.id") == "hover-people"
    assert driver.execute_script(f"return !{HOVER}.hidden")


PRICED_BADGE = "document.querySelector('.card[data-key=\"priced\"] .economy')"
# Whether the priced card's badge stays inside the card, as on a phone
BADGE_INSIDE = f"""
const card = document.querySelector('.card[data-key="priced"]').getBoundingClientRect();
const badge = {PRICED_BADGE}.getBoundingClientRect();
return badge.left >= card.left - 0.5 && badge.right <= card.right + 0.5;
"""


def test_currency_badges_show_and_the_server_switch_hides_them(driver, live, tmp_path):
    folder = write_demo_web(tmp_path / "priced")
    line = "Win <b>coins</b> & more in every round"
    register(live.hub, DemoCog(folder, key="priced", name="Priced", cog_name="Priced", economy=line))
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "grid"}
    live.user_id = MANAGER_ID
    open_menu(driver, live, DISCORD_QUERY)
    assert driver.execute_script(f"return {PRICED_BADGE}.querySelector('.economy-text').textContent") == line
    assert not driver.find_elements(By.CSS_SELECTOR, '.card[data-key="priced"] .economy b')
    assert not driver.find_elements(By.CSS_SELECTOR, '.card[data-key="demo"] .economy')
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride", {"width": 375, "height": 740, "deviceScaleFactor": 1, "mobile": True}
    )
    try:
        open_menu(driver, live, DISCORD_QUERY)
        assert driver.execute_script(BADGE_INSIDE) and no_sideways_scroll(driver)
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
    open_menu(driver, live, DISCORD_QUERY)
    open_settings(driver)
    pick_tab(driver, "server")
    driver.find_element(By.ID, "economy-labels").click()
    save(driver)
    assert live.hub.config.guilds[GUILD_ID]["economy_labels"] is False
    driver.find_element(By.ID, "close").click()
    assert not driver.find_elements(By.CSS_SELECTOR, "#games .economy")


def test_the_orb_screen_shows_the_selected_games_badge(driver, live, tmp_path):
    folder = write_demo_web(tmp_path / "priced")
    register(live.hub, DemoCog(folder, key="priced", name="Priced", cog_name="Priced", economy="Bet credits"))
    open_menu(driver, live, DISCORD_QUERY)
    assert driver.execute_script("return document.body.dataset.theme") == "orb"
    # Focus selects a pill, like pointing at it; a click would open the game
    driver.execute_script("document.querySelector('#games .pill[data-key=\"priced\"]').focus()")
    wait_for(driver, "document.querySelector('#orb-screen .screen-face .economy-text')?.textContent === 'Bet credits'")


def test_badges_refresh_after_coming_back_from_a_game(driver, live, tmp_path):
    answer = {"line": "Cash in up to 500 credits"}

    async def economy_line(guild):
        return answer["line"]

    folder = write_demo_web(tmp_path / "priced")
    register(live.hub, DemoCog(folder, key="priced", name="Priced", cog_name="Priced", economy=economy_line))
    live.hub.config.globals["look"] = {"theme": "standard", "layout": "list"}
    open_menu(driver, live, DISCORD_QUERY)
    badge = "(document.querySelector('.card[data-key=\"priced\"] .economy-text')?.textContent ?? null)"
    assert driver.execute_script(f"return {badge}") == "Cash in up to 500 credits"
    driver.find_element(By.CSS_SELECTOR, '.card[data-key="demo"]').click()
    wait_for(driver, "document.body.classList.contains('playing')")
    # An admin turns the game's payouts off while away from the menu
    answer["line"] = None
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "window.demo && window.demo.done")
    driver.find_element(By.ID, "back").click()
    driver.switch_to.default_content()
    wait_for(driver, f"{badge} === null")
    answer["line"] = "Cash in up to 900 credits"
    driver.find_element(By.CSS_SELECTOR, '.card[data-key="demo"]').click()
    wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "window.demo && window.demo.done")
    driver.find_element(By.ID, "back").click()
    driver.switch_to.default_content()
    wait_for(driver, f"{badge} === 'Cash in up to 900 credits'")


@pytest.mark.parametrize("look", [{"layout": "compact"}, {"layout": "list", "details": False}])
def test_every_layout_shows_the_badges_words(driver, live, tmp_path, look):
    folder = write_demo_web(tmp_path / "priced")
    register(live.hub, DemoCog(folder, key="priced", name="Priced", cog_name="Priced", economy="Bet credits"))
    live.hub.config.globals["look"] = {"theme": "standard", **look}
    open_menu(driver, live, DISCORD_QUERY)
    words = driver.find_element(By.CSS_SELECTOR, '.card[data-key="priced"] .economy-text')
    assert words.is_displayed() and words.text == "Bet credits"
    assert no_sideways_scroll(driver)
