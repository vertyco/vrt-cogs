import asyncio
import time
from types import SimpleNamespace

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

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
    # Headless Chrome still plays the games' sounds through the computer's speakers
    options.add_argument("--mute-audio")
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


class Person:
    """Someone playing on another device, seated by the test straight into the match"""

    def __init__(self, user_id, name):
        avatar = SimpleNamespace(url="")
        author = SimpleNamespace(id=user_id, name=name, display_name=name, global_name=name, display_avatar=avatar)
        self.ctx = SimpleNamespace(author=author)

    async def send(self, data):
        pass


def run(live, coro):
    return asyncio.run_coroutine_threadsafe(coro, live.loop).result(5)


def me_in_the_window(live):
    """The player's entry in the bot's list of who is here, with the status and busy flag their page last sent"""
    return live.server.presence.windows["i-1"].people[fakes.MEMBER_ID]


def the_match(cog):
    return next(iter(cog.matches.values()))


def sit_down(driver):
    browser.wait_for(driver, "document.querySelectorAll('#seats li').length === 2", timeout=20)
    driver.find_element(By.CSS_SELECTOR, "#seats li:first-child button").click()
    browser.wait_for(driver, "!document.getElementById('start').hidden")


def seat_a_person(driver, live, cog, name, user_id=901):
    """Put someone at the right base, waiting until the player's page shows them there"""

    async def sit():
        the_match(cog).sit(Person(user_id, name), 1)

    run(live, sit())
    browser.wait_for(driver, "document.querySelector('#seats li:nth-child(2) .who:not(.cpu)') !== null")


def start_against_a_person(driver, live, cog, name="Ann"):
    open_game(driver, live)
    sit_down(driver)
    seat_a_person(driver, live, cog, name)
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'", timeout=10)


def tag_text(driver, number):
    return driver.execute_script(f"return document.getElementById('side-{number}').textContent")


def test_watchers_show_as_faces_and_the_player_says_watching(driver, live):
    open_game(driver, live)
    live.add_person(fakes.MANAGER_ID, where="ageofwar")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    assert driver.execute_script("return document.querySelector('.corner .hub-people') !== null")
    me = me_in_the_window(live)
    WebDriverWait(driver, 10).until(lambda _: me.status == "Watching")
    assert me.busy is False


def test_a_seated_player_says_what_they_are_doing_and_is_busy_only_in_a_battle(driver, live, cog):
    open_game(driver, live)
    me = me_in_the_window(live)
    sit_down(driver)
    WebDriverWait(driver, 10).until(lambda _: me.status == "Setting up")
    assert me.busy is False
    # Alone with the computer, nobody else watches, so the row of faces stays out of the way
    assert driver.find_element(By.ID, "watching").get_attribute("hidden")
    driver.find_element(By.ID, "start").click()
    WebDriverWait(driver, 10).until(lambda _: me.status == "Battle vs CPU")
    assert me.busy is True
    # Both sides are named for the player too, not only for people watching
    browser.wait_for(driver, "!document.getElementById('sides').hidden")
    assert tag_text(driver, 1) == the_match(cog).seats[0].name
    assert tag_text(driver, 2) == "Computer"
    driver.find_element(By.ID, "give-up").click()
    driver.find_element(By.ID, "quit-yes").click()
    WebDriverWait(driver, 10).until(lambda _: me.status == "Lost")
    assert me.busy is False


def test_the_status_names_a_person_across_the_battle_and_their_side_is_named_too(driver, live, cog):
    open_game(driver, live)
    me = me_in_the_window(live)
    start_against_a_person(driver, live, cog, "Ann")
    WebDriverWait(driver, 10).until(lambda _: me.status == "Battle vs Ann")
    assert me.busy is True
    assert tag_text(driver, 2) == "Ann"


@pytest.mark.parametrize("winner,said", [(1, "Won"), (2, "Lost")])
def test_the_results_say_won_or_lost_and_the_player_is_no_longer_busy(driver, live, cog, winner, said):
    start_against_the_computer(driver, live)
    me = me_in_the_window(live)
    match = the_match(cog)
    # These battles are ended by hand, so their wins stay out of the leaderboard the other tests share
    match.record = lambda results: None

    async def finish():
        match.battle.winner = winner
        match.finish()

    run(live, finish())
    WebDriverWait(driver, 10).until(lambda _: me.status == said)
    assert me.busy is False


def test_an_unchanged_status_is_not_sent_again_when_the_bot_sends_a_new_picture_of_the_battle(driver, live, cog):
    start_against_the_computer(driver, live)
    me = me_in_the_window(live)
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    match = the_match(cog)
    time.sleep(0.6)
    sent = []
    original = live.server.presence.update

    async def counting(conn, data):
        sent.append(data)
        await original(conn, data)

    live.server.presence.update = counting
    # The bot sends a new picture whenever something in the match changes, and the page redraws from each one.
    # The hub would pass on every status the page repeats, and the bot would send the window's list again each time
    pictures = []
    original_state = match.state
    match.state = lambda: pictures.append(1) or original_state()
    for _ in range(6):
        match.dirty = True
        time.sleep(0.4)
    assert len(pictures) >= 4
    assert sent == []


def test_a_closed_connection_clears_the_status_and_busy_flag(driver, live, cog):
    start_against_the_computer(driver, live)
    me = me_in_the_window(live)
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    conn = the_match(cog).room.connections[0]
    run(live, conn.close(4100))
    WebDriverWait(driver, 10).until(lambda _: me.status == "Not connected")
    assert me.busy is False


def test_the_side_of_a_person_the_computer_took_over_says_so(driver, live, cog):
    start_against_a_person(driver, live, cog, "Ann")

    async def away():
        the_match(cog).take_over(1)

    run(live, away())
    browser.wait_for(driver, "document.getElementById('side-2').textContent.includes('(computer playing)')")
    assert tag_text(driver, 2).startswith("Ann")


def test_long_names_on_the_side_tags_are_cut_without_splitting_an_emoji(driver, live, cog):
    start_against_a_person(driver, live, cog, "Ann")
    family = "\U0001f468‍\U0001f469‍\U0001f467‍\U0001f466"
    cuts = {
        "Twelve chars": "Twelve chars",
        "Averyverylongname": "Averyverylo…",
        family * 13: family * 11 + "…",
    }
    for name, shown in cuts.items():

        async def rename(name=name):
            the_match(cog).seats[1].name = name
            the_match(cog).dirty = True

        run(live, rename())
        WebDriverWait(driver, 10).until(lambda _, shown=shown: tag_text(driver, 2) == shown)
    # A name can't turn the words around it, and stays big enough to read on a phone
    style = driver.execute_script(
        "const s = getComputedStyle(document.getElementById('side-2'));return [s.unicodeBidi, parseFloat(s.fontSize)];"
    )
    assert style[0] == "isolate" and style[1] >= 12


def sides_with_watchers(driver, live, cog):
    """A battle against a person with a long name, with two watchers, one of them away"""
    start_against_a_person(driver, live, cog, "Bartholomew Wellington the Third")
    manager = live.add_person(fakes.MANAGER_ID, where="ageofwar")
    live.add_person(fakes.ADMIN_ID, where="ageofwar", away=True)
    browser.wait_for(driver, "document.querySelectorAll('#side-watchers .face').length === 2")
    return manager


def test_watchers_show_as_faces_next_to_the_side_names_and_hide_when_nobody_watches(driver, live, cog):
    start_against_a_person(driver, live, cog, "Ann")
    assert driver.find_element(By.ID, "side-watchers").get_attribute("hidden")
    manager = live.add_person(fakes.MANAGER_ID, where="ageofwar")
    browser.wait_for(driver, "document.querySelectorAll('#side-watchers .face').length === 1")
    # The player is at a base, so only the others count
    assert driver.find_element(By.CSS_SELECTOR, "#side-watchers .label").text == "1 watching"
    # They go back to the menu, so they are no longer here
    live.update_person(manager)
    browser.wait_for(driver, "document.getElementById('side-watchers').hidden")


def test_an_away_watcher_is_dimmed(driver, live, cog):
    sides_with_watchers(driver, live, cog)
    assert driver.execute_script("return document.querySelectorAll('#side-watchers .face.away').length") == 1
    assert driver.execute_script("return document.querySelector('#side-watchers .face.away').title") == "Admin"


def test_a_new_people_list_that_changes_nothing_leaves_the_faces_alone(driver, live, cog):
    manager = sides_with_watchers(driver, live, cog)
    # A face redrawn between a press and its release would lose the tap, and lists arrive several times a second
    driver.execute_script(
        "window.redrawn = 0;"
        "new MutationObserver((list) => { window.redrawn += list.length; })"
        ".observe(document.getElementById('side-watchers'), { childList: true });"
    )
    live.update_person(manager, where="ageofwar", status="Reading the rules")
    time.sleep(1.2)
    assert driver.execute_script("return window.redrawn") == 0
    # The same observer does see a real change
    live.update_person(manager)
    browser.wait_for(driver, "document.querySelectorAll('#side-watchers .face').length === 1")
    assert driver.execute_script("return window.redrawn") > 0


def test_tapping_a_watcher_face_says_who_it_is(driver, live, cog):
    sides_with_watchers(driver, live, cog)
    driver.find_element(By.CSS_SELECTOR, '#side-watchers .face[title="Manager"]').click()
    browser.wait_for(driver, "!document.getElementById('toast').hidden")
    text = driver.find_element(By.ID, "toast").text
    assert "Manager" in text and text.endswith("is watching.")


def test_the_watching_count_is_people_not_connections(driver, live, cog):
    sides_with_watchers(driver, live, cog)
    # The bot counts connections, so one person with the game open on two devices is two to it
    match = the_match(cog)
    match.watching = lambda: 5

    async def new_picture():
        # The new name comes in the same picture as the new count, so it shows the page has drawn that picture
        match.seats[1].name = "Zed"
        match.dirty = True

    run(live, new_picture())
    WebDriverWait(driver, 10).until(lambda _: tag_text(driver, 2) == "Zed")
    assert driver.find_element(By.CSS_SELECTOR, "#side-watchers .label").text == "2 watching"


def test_the_setup_panel_shows_the_same_faces(driver, live):
    open_game(driver, live)
    live.add_person(fakes.MANAGER_ID, where="ageofwar")
    live.add_person(fakes.ADMIN_ID, where="ageofwar", away=True)
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 3")
    assert driver.find_element(By.CSS_SELECTOR, "#watching .label").text == "3 watching"
    assert driver.execute_script("return document.querySelectorAll('#watching .face.away').length") == 1


def go_to(driver, width, height, mobile=False):
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 2 if mobile else 1, "mobile": mobile},
    )
    browser.wait_for(driver, f"window.innerWidth === {width}")
    time.sleep(0.5)


def rect_of(driver, selector):
    return driver.execute_script(
        "const e = document.querySelector(arguments[0]); if (!e) { return null; }"
        "const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom];",
        selector,
    )


# Desktop, a very wide window, windows 250 and 300 wide between the menus, a phone held sideways and one upright
SIZES = [
    (1280, 720, False),
    (1900, 700, False),
    (900, 390, False),
    (950, 390, False),
    (844, 390, True),
    (568, 320, True),
    (390, 844, True),
]


@pytest.mark.parametrize("width,height,mobile", SIZES)
def test_the_corner_buttons_and_the_people_button_fit_between_the_menus(driver, live, width, height, mobile):
    # Against the computer there are five round buttons, the most the row ever holds
    start_against_the_computer(driver, live)
    live.add_person(fakes.MANAGER_ID, where="ageofwar")
    try:
        go_to(driver, width, height, mobile)
        assert driver.find_element(By.ID, "pause").is_displayed()
        corner = rect_of(driver, ".corner")
        assert driver.execute_script("return document.querySelector('.corner .hub-people') !== null")
        assert corner[0] >= -1 and corner[2] <= width + 1
        app = driver.execute_script("return document.getElementById('app').dataset")
        if app["layout"] == "wide" and app["corner"] != "below":
            left, right = rect_of(driver, "#hud .strip.left"), rect_of(driver, "#hud .strip.right")
            assert left[2] <= corner[0] and corner[2] <= right[0]
        # Wherever the row sits, every button is what a press at its center reaches, so no menu covers one
        hits = driver.execute_script(
            "return [...document.querySelectorAll('.corner button')].filter((b) => b.offsetParent).map((b) => {"
            "const r = b.getBoundingClientRect();"
            "const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);"
            "return [b.id || b.className, b.contains(hit)]; })"
        )
        assert len(hits) == 6 and all(reached for _, reached in hits), hits
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


# What each side's arrow says, and how far it sticks out of its name's text
ARROWS = (
    "const mark = (id, side) => getComputedStyle(document.querySelector(`#${id} .tag-name`), side).content;"
    "return [mark('side-1', '::before'), mark('side-2', '::after')];"
)
ARROW_ROOM = (
    "const room = (id) => {"
    "const name = document.querySelector(`#${id} .tag-name`);"
    "const range = document.createRange(); range.selectNodeContents(name);"
    "const text = range.getBoundingClientRect(); const box = name.getBoundingClientRect();"
    "return [box.left - text.left, box.right - text.right]; };"
    "return [room('side-1'), room('side-2')];"
)


@pytest.mark.parametrize("width,height,mobile", SIZES)
def test_the_side_names_and_faces_stay_on_screen_and_clear_the_buttons_and_menus(
    driver, live, cog, width, height, mobile
):
    sides_with_watchers(driver, live, cog)
    try:
        go_to(driver, width, height, mobile)
        corner = rect_of(driver, ".corner")
        scale = driver.execute_script(
            "return parseFloat(getComputedStyle(document.getElementById('app')).getPropertyValue('--left-scale'))"
        )
        layout = driver.execute_script("return document.getElementById('app').dataset.layout")
        for selector in ("#side-1", "#side-2", "#side-watchers"):
            left, top, right, bottom = rect_of(driver, selector)
            assert left >= 0 and right <= width and bottom <= height, selector
            # Under the round buttons and a note sliding out of the people button (about 34 px), so neither covers
            # the other
            assert top >= corner[3] + 34, selector
            # Above the ground, where the units walk
            assert bottom <= 0.7 * height, selector
            if layout == "wide":
                # Under the menus' wooden panels, which the original draws 75 high at its own size
                assert top >= 75 * scale, selector
                # And away from the bases' health bars at the edges
                assert left >= 80 and right <= width - 80, selector
        # The left name, then "vs", then the right name, on one row at these widths, with an arrow for each base
        one, two, versus = rect_of(driver, "#side-1"), rect_of(driver, "#side-2"), rect_of(driver, ".vs")
        assert one[2] <= versus[0] and versus[2] <= two[0] and abs(one[1] - two[1]) < 2
        # The names are centered under the round buttons, wherever those sit
        names = rect_of(driver, ".versus")
        assert abs((names[0] + names[2]) / 2 - (corner[0] + corner[2]) / 2) < 2
        assert driver.execute_script(ARROWS) == ['"◀︎"', '"▶︎"']
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_the_people_button_is_as_tall_as_the_round_buttons_beside_it_before_a_battle(driver, live):
    open_game(driver, live)
    try:
        go_to(driver, 900, 390)
        # The round buttons shrink to 30 px when the gap between the menus is small, but only in a battle
        assert driver.execute_script("return document.getElementById('app').dataset.corner") == "small"
        heights = driver.execute_script(
            "return [...document.querySelectorAll('.corner #back, .corner .hub-people-button')]"
            ".map((e) => e.getBoundingClientRect().height)"
        )
        assert heights == [36, 36]
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_a_row_of_names_that_wraps_keeps_each_arrow_with_its_name(driver, live, cog):
    start_against_a_person(driver, live, cog, "M" * 12)

    async def widen():
        the_match(cog).seats[0].name = "W" * 12
        the_match(cog).dirty = True

    run(live, widen())
    WebDriverWait(driver, 10).until(lambda _: tag_text(driver, 1) == "W" * 12)
    try:
        go_to(driver, 320, 568, mobile=True)
        one, two = rect_of(driver, "#side-1"), rect_of(driver, "#side-2")
        # Too wide for one row, so the right name is under the left one
        assert two[1] >= one[3]
        for left, _, right, _ in (one, two):
            assert left >= 0 and right <= 320
        assert driver.execute_script(ARROWS) == ['"◀︎"', '"▶︎"']
        # Each arrow is part of its own name, a little before the left one's letters and after the right one's
        (before_left, _), (_, after_right) = driver.execute_script(ARROW_ROOM)
        assert before_left < -8 and after_right > 8
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
