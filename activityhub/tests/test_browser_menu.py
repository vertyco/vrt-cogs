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
        # Up along the ring brings the next game in, one per step
        slide(driver, (420, 300), (420, 200))
        wait_for(driver, f"{SELECTED} === 'extra0'")
        # Browsers keep a page quiet until the first touch ends, so the move sound comes from the next slide on
        slide(driver, (420, 200), (420, 250))
        wait_for(driver, f"{SELECTED} === 'demo'")
        wait_for(driver, f"window.soundLog.includes({MOVE})")
        # Left and right work too, and a slide that starts on a pill doesn't open its game
        slide(driver, (600, 200), (500, 200))
        wait_for(driver, f"{SELECTED} === 'extra1'")
        pill = driver.find_element(By.CSS_SELECTOR, '#games .pill[data-key="extra1"]').rect
        x, y = pill["x"] + pill["width"] / 2, pill["y"] + pill["height"] / 2
        slide(driver, (x, y), (x + 50, y))
        wait_for(driver, f"{SELECTED} === 'extra0'")
        assert driver.find_elements(By.ID, "game-frame") == []
        # A fast slide that arrives in one big move goes as far as a slow one, here three steps
        slide(driver, (420, 340), (420, 340 - 3 * 44 - 10), steps=1)
        wait_for(driver, f"{SELECTED} === 'extra3'")
        assert driver.execute_script("return window.scrollY") == 0
    finally:
        plain_device(driver)


def test_orb_swipes_move_along_the_ring_on_an_upright_phone(driver, live):
    touch_device(driver, 375, 740)
    try:
        open_menu(driver, live, DISCORD_QUERY)
        slide(driver, (300, 560), (300, 510))
        wait_for(driver, f"{SELECTED} === 'demo'")
        assert driver.find_element(By.CSS_SELECTOR, "#orb-screen .screen-name").text.lower() == "demo"
        assert driver.execute_script("return window.scrollY") == 0
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
        # The pods hold the icons, and the panel docked at the bottom shows the selected game's description
        pill = driver.find_element(By.CSS_SELECTOR, '#games .pill[data-key="demo"]')
        assert pill.find_element(By.CSS_SELECTOR, ".pod .icon").is_displayed()
        screen = driver.find_element(By.ID, "orb-screen")
        assert screen.is_displayed() and screen.rect["y"] > 740 / 2
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
