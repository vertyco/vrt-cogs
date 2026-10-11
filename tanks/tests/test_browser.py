import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait

from tanks.main import Tanks

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="tanks"]'
UPRIGHT_PHONE = {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}


class Player:
    """Someone playing on another device, seated by the test straight into the match"""

    def __init__(self, user_id, name):
        avatar = SimpleNamespace(url="")
        author = SimpleNamespace(id=user_id, name=name, display_name=name, global_name=name, display_avatar=avatar)
        self.ctx = SimpleNamespace(author=author)

    async def send(self, data):
        pass


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
    return Tanks(bot=None)


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


def open_game(driver, live):
    driver.get(f"{live.url}/{browser.DISCORD_QUERY}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(driver, "document.querySelectorAll('#seats li').length === 5", timeout=20)


def test_a_match_against_a_computer_starts_and_plays_a_shot(driver, live):
    open_game(driver, live)
    driver.find_element(By.CSS_SELECTOR, "#seats li:first-child button").click()
    browser.wait_for(driver, "!document.getElementById('start').hidden")
    Select(driver.find_element(By.CSS_SELECTOR, "#seats li:nth-child(2) select")).select_by_value("easy")
    browser.wait_for(driver, "!document.getElementById('start').disabled")
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'shop'", timeout=10)
    driver.find_element(By.ID, "done").click()
    browser.wait_for(driver, "!document.getElementById('controls').classList.contains('waiting')", timeout=10)
    ActionChains(driver).key_down(Keys.ARROW_UP).pause(0.3).key_up(Keys.ARROW_UP).send_keys(Keys.SPACE).perform()
    # The shot plays, then the computer takes its turn
    browser.wait_for(driver, "document.querySelector('#cards .turn.seat-1')", timeout=20)
    driver.switch_to.default_content()
    assert browser.wait_for(driver, "/\\d+ TPS$/.test(document.querySelector('.fps').textContent)", timeout=5)
    problems = [line for line in browser.console_lines(driver) if "Uncaught" in line or "Tanks" in line]
    assert not problems, problems


def watch_a_match_start(driver, live, cog):
    """Open the game as a watcher while two people elsewhere and a computer start a match. The first is done shopping"""
    open_game(driver, live)
    match = next(iter(cog.matches.values()))
    first, second = Player(901, "Vainne"), Player(902, "Vert")

    async def start():
        for number, player in ((0, first), (2, second)):
            seat = match.seats[number]
            seat.user_id, seat.name, seat.board_name, seat.conn = (
                player.ctx.author.id,
                player.ctx.author.name,
                "",
                player,
            )
        match.seats[1].level, match.seats[1].name = "normal", "CPU 2"
        match.fix_host()
        match.start_match(first, True)
        await match.message(first, {"done": True})

    asyncio.run_coroutine_threadsafe(start(), live.loop).result(10)
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'shop'", timeout=10)
    return match, first, second


def test_watchers_see_who_is_still_shopping(driver, live, cog):
    watch_a_match_start(driver, live, cog)
    browser.wait_for(driver, "document.querySelectorAll('#shoppers li').length === 3", timeout=10)
    rows = driver.find_elements(By.CSS_SELECTOR, "#shoppers li")
    assert [row.find_element(By.CSS_SELECTOR, ".status").text for row in rows] == ["Done", "Ready", "Shopping"]
    assert not driver.find_element(By.ID, "store").is_displayed()
    assert "Round 1 of 5" in driver.find_element(By.ID, "money").text


def test_on_an_upright_phone_the_field_is_only_as_tall_as_it_needs(driver, live, cog):
    match, first, second = watch_a_match_start(driver, live, cog)
    asyncio.run_coroutine_threadsafe(match.message(second, {"done": True}), live.loop).result(10)
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'", timeout=10)
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", UPRIGHT_PHONE)
    try:
        # The cards then sit right under the field instead of leaving a gap above and below it
        browser.wait_for(driver, "document.getElementById('field-box').getBoundingClientRect().width < 400")
        width, height = driver.execute_script(
            "const r = document.getElementById('field-box').getBoundingClientRect(); return [r.width, r.height]"
        )
        assert abs(height - width * 400 / 550) < 2
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def run(live, coro):
    """Run a coroutine on the server's own event loop, where the match lives"""
    return asyncio.run_coroutine_threadsafe(coro, live.loop).result(5)


def me_in_the_window(live):
    """The player's entry in the bot's list of who is here, with the status and busy flag their page last sent"""
    return live.server.presence.windows["i-1"].people[fakes.MEMBER_ID]


def sit_down(driver):
    driver.find_element(By.CSS_SELECTOR, "#seats li:first-child button").click()
    browser.wait_for(driver, "!document.getElementById('start').hidden")


def start_against_a_computer(driver):
    """Put an easy computer in the second seat and start the match, which opens on the shop"""
    Select(driver.find_element(By.CSS_SELECTOR, "#seats li:nth-child(2) select")).select_by_value("easy")
    browser.wait_for(driver, "!document.getElementById('start').disabled")
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'shop'", timeout=10)


def sit_down_and_start(driver):
    sit_down(driver)
    start_against_a_computer(driver)


def test_watchers_show_as_faces_and_the_player_says_watching(driver, live):
    open_game(driver, live)
    live.add_person(fakes.MANAGER_ID, where="tanks")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    assert driver.execute_script("return document.querySelector('header.top .hub-people') !== null")
    me = me_in_the_window(live)
    assert me.status == "Watching" and me.busy is False


def test_a_seated_player_says_what_they_are_doing_and_is_busy_from_the_shop_on(driver, live):
    open_game(driver, live)
    me = me_in_the_window(live)
    sit_down(driver)
    WebDriverWait(driver, 10).until(lambda _: me.status == "Setting up")
    assert me.busy is False
    # Alone with computers, nobody else watches, so the row of faces stays out of the way
    assert driver.find_element(By.ID, "watching").get_attribute("hidden")
    start_against_a_computer(driver)
    WebDriverWait(driver, 10).until(lambda _: me.status == "Shopping · round 1 of 5")
    assert me.busy is True
    driver.find_element(By.ID, "done").click()
    browser.wait_for(driver, "!document.getElementById('controls').classList.contains('waiting')", timeout=10)
    WebDriverWait(driver, 10).until(lambda _: me.status == "Aiming · round 1 of 5")
    assert me.busy is True


@pytest.mark.parametrize(
    "mine,other,said",
    [(900, 100, "Finished 1st"), (100, 900, "Finished 2nd"), (500, 500, "Finished 1st")],
)
def test_the_results_say_where_the_player_placed_and_the_player_is_no_longer_busy(driver, live, cog, mine, other, said):
    open_game(driver, live)
    me = me_in_the_window(live)
    sit_down_and_start(driver)
    match = next(iter(cog.matches.values()))
    # These matches are ended by hand, so their results stay out of the leaderboard the other tests share
    match.record = lambda results: None

    async def finish():
        match.seats[0].kit.score, match.seats[1].kit.score = mine, other
        match.finish()

    run(live, finish())
    WebDriverWait(driver, 10).until(lambda _: me.status == said)
    assert me.busy is False


def test_an_unchanged_status_is_not_sent_again_when_the_bot_sends_a_new_picture_of_the_match(driver, live, cog):
    open_game(driver, live)
    me = me_in_the_window(live)
    sit_down_and_start(driver)
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    match = next(iter(cog.matches.values()))
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
    open_game(driver, live)
    me = me_in_the_window(live)
    sit_down_and_start(driver)
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    conn = next(iter(cog.matches.values())).room.connections[0]
    run(live, conn.close(4100))
    WebDriverWait(driver, 10).until(lambda _: me.status == "Not connected")
    assert me.busy is False


def test_a_new_people_list_that_changes_nothing_leaves_the_faces_alone(driver, live):
    open_game(driver, live)
    other = live.add_person(fakes.MANAGER_ID, where="tanks")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    # A face redrawn between a press and its release would lose the tap, and lists arrive several times a second
    driver.execute_script(
        "window.redrawn = 0;"
        "new MutationObserver((list) => { window.redrawn += list.length; })"
        ".observe(document.getElementById('watching'), { childList: true });"
    )
    live.update_person(other, where="tanks", status="Reading the rules")
    time.sleep(1.2)
    assert driver.execute_script("return window.redrawn") == 0
    # The same observer does see a real change
    live.update_person(other)
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 1")
    assert driver.execute_script("return window.redrawn") > 0


def test_tapping_a_watcher_face_says_who_it_is(driver, live):
    open_game(driver, live)
    live.add_person(fakes.MANAGER_ID, where="tanks")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    driver.find_element(By.CSS_SELECTOR, '#watching .face[title="Manager"]').click()
    toast = driver.find_element(By.ID, "toast")
    browser.wait_for(driver, "!document.getElementById('toast').hidden")
    assert "Manager" in toast.text and toast.text.endswith("is watching.")


def test_an_away_watcher_is_dimmed(driver, live):
    open_game(driver, live)
    other = live.add_person(fakes.MANAGER_ID, where="tanks")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    assert driver.execute_script("return document.querySelectorAll('#watching .face.away').length") == 0
    live.update_person(other, where="tanks", away=True)
    browser.wait_for(driver, "document.querySelectorAll('#watching .face.away').length === 1")


def test_the_watching_count_is_people_not_connections(driver, live, cog):
    open_game(driver, live)
    live.add_person(fakes.MANAGER_ID, where="tanks")
    browser.wait_for(driver, "document.querySelectorAll('#watching .face').length === 2")
    match = next(iter(cog.matches.values()))
    # The bot counts connections, so one person with the game open on two devices is two to it
    match.watching = lambda: 5
    match.dirty = True
    time.sleep(0.6)
    assert driver.find_element(By.CSS_SELECTOR, "#watching .label").text == "2 watching"


def from_scene(driver, call, *args):
    """What a function exported by the page's scene.js gives for these arguments"""
    driver.set_script_timeout(10)
    return driver.execute_async_script(
        "const done = arguments[arguments.length - 1];"
        "const args = Array.from(arguments).slice(0, -1);"
        f"import('./scene.js').then((scene) => done(scene.{call}(...args))).catch((e) => done(String(e)));",
        *args,
    )


def test_a_long_name_over_a_tank_is_cut_without_splitting_an_emoji(driver, live):
    open_game(driver, live)
    family = "👨‍👩‍👧‍👦"
    names = ["Vert", "Twelve chars", "Averyverylongname", family * 13]
    assert from_scene(driver, "fieldName", names[0]) == "Vert"
    assert from_scene(driver, "fieldName", names[1]) == "Twelve chars"
    assert from_scene(driver, "fieldName", names[2]) == "Averyverylo…"
    assert from_scene(driver, "fieldName", names[3]) == family * 11 + "…"
    # A small field gets shorter names
    assert from_scene(driver, "fieldName", names[2], 8) == "Averyve…"
    assert from_scene(driver, "fieldName", "Eight ch", 8) == "Eight ch"
    assert from_scene(driver, "fieldName", family * 9, 8) == family * 7 + "…"


def box(x, width=58, height=10, y=0):
    """A name's rectangle: centered on x, `y` the top edge"""
    return {"x": x, "y": y, "width": width, "height": height}


def test_names_far_apart_stay_in_one_row_and_names_that_touch_stack_up(driver, live):
    open_game(driver, live)
    apart = from_scene(driver, "layoutNames", [box(100), box(300), box(500)])
    assert [place["rise"] for place in apart] == [0, 0, 0]
    assert [place["x"] for place in apart] == [100, 300, 500]
    # The same five names at the closest spacing the bot puts tanks (70), too wide to share a row
    crowd = from_scene(driver, "layoutNames", [box(45 + 70 * n, width=80) for n in range(5)])
    assert [place["rise"] for place in crowd] == [0, 11, 0, 11, 0]
    # A name only 1 px clear of the last one still goes up, 2 px clear stays
    assert [p["rise"] for p in from_scene(driver, "layoutNames", [box(100, 50), box(151, 50)])] == [0, 11]
    assert [p["rise"] for p in from_scene(driver, "layoutNames", [box(100, 50), box(152, 50)])] == [0, 0]


def test_names_are_listed_in_the_order_given_however_they_sort_across_the_field(driver, live):
    open_game(driver, live)
    placed = from_scene(driver, "layoutNames", [box(300, 80), box(60, 80), box(330, 80)])
    # The name at 330 touches the one at 300, so it is the one raised
    assert [place["rise"] for place in placed] == [0, 0, 11]


def test_a_name_goes_up_as_far_as_it_takes_to_clear_a_lower_neighbour_on_a_slope(driver, live):
    open_game(driver, live)
    # The right-hand tank sits 12 px lower than the left-hand one, so a name raised one row (25 px) from its own
    # tank lands at the left-hand name's height again. It has to go up two rows
    slope = [box(100, 80, 24, y=100), box(160, 80, 24, y=112)]
    assert [p["rise"] for p in from_scene(driver, "layoutNames", slope)] == [0, 50]
    # On the level the same two names need only one row
    level = [box(100, 80, 24, y=100), box(160, 80, 24, y=100)]
    assert [p["rise"] for p in from_scene(driver, "layoutNames", level)] == [0, 25]
    # A higher right-hand neighbour is already clear of the left-hand name and stays where it is
    higher = [box(100, 80, 24, y=100), box(160, 80, 24, y=70)]
    assert [p["rise"] for p in from_scene(driver, "layoutNames", higher)] == [0, 0]


def test_a_crowd_stacks_up_to_five_rows_and_then_a_name_takes_the_row_it_covers_least(driver, live):
    open_game(driver, live)
    # Four names over the same spot fill rows 0 to 3, and a narrow one beside them takes row 4
    stack = [box(100, 100, 10, y=100) for _ in range(4)] + [box(140, 20, 10, y=100)]
    assert [p["rise"] for p in from_scene(driver, "layoutNames", stack)] == [0, 11, 22, 33, 44]
    # A wide name beside those would cover half a name in each of rows 0 to 3 and only a corner of the narrow one in
    # row 4, which is all five rows taken, so it goes to row 4
    crowd = stack + [box(150, 100, 10, y=100)]
    assert [p["rise"] for p in from_scene(driver, "layoutNames", crowd)] == [0, 11, 22, 33, 44, 44]


def test_a_name_beside_the_edge_of_the_field_is_pulled_in_so_nothing_is_cut_off(driver, live):
    open_game(driver, live)
    placed = from_scene(driver, "layoutNames", [box(8, 58), box(545, 58)])
    assert [place["x"] for place in placed] == [29, 521]


def test_each_seats_tank_carries_that_seats_name_cut_for_the_size_of_the_field(driver, live, cog):
    open_game(driver, live)
    sit_down(driver)
    match = next(iter(cog.matches.values()))
    other = Player(901, "Bartholomew Wellington the Third")

    async def seat_the_long_name():
        seat = match.seats[2]
        seat.user_id, seat.name, seat.board_name, seat.conn = 901, other.ctx.author.name, "", other
        match.fix_host()
        match.dirty = True

    run(live, seat_the_long_name())
    browser.wait_for(driver, "document.querySelectorAll('#seats li')[2].textContent.includes('Bartholomew')")
    start_against_a_computer(driver)
    driver.find_element(By.ID, "done").click()
    run(live, match.message(other, {"done": True}))
    browser.wait_for(driver, "document.getElementById('app').dataset.stage === 'playing'", timeout=15)
    names = "JSON.parse(document.querySelector('#field canvas').dataset.names || '{}')"
    # Seat 0 is this player, seat 1 the computer and seat 2 the other player. Seats 3 and 4 are empty and have no tank
    big = {"0": "Member", "1": "CPU 2", "2": "Bartholomew…"}
    assert browser.wait_for(driver, f"JSON.stringify({names}) === JSON.stringify({json.dumps(big)})")
    # An upright phone's field is small, so the long name is cut shorter
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", UPRIGHT_PHONE)
    try:
        small = {"0": "Member", "1": "CPU 2", "2": "Barthol…"}
        assert browser.wait_for(driver, f"JSON.stringify({names}) === JSON.stringify({json.dumps(small)})")
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_a_raised_name_has_a_tick_down_to_its_tank_and_a_name_left_in_place_has_none(driver, live, cog):
    open_game(driver, live)
    sit_down_and_start(driver)
    driver.find_element(By.ID, "done").click()
    browser.wait_for(driver, "!document.getElementById('controls').classList.contains('waiting')", timeout=15)
    match = next(iter(cog.matches.values()))
    ticks = "JSON.stringify(JSON.parse(document.querySelector('#field canvas').dataset.ticks || '[]'))"

    first = match.tanks[0]

    async def put(second_x):
        # Level with the first tank, so only their sideways distance decides whether the names touch
        match.tanks[1].x, match.tanks[1].y = float(second_x), first.y
        match.dirty = True

    run(live, put(first.x + 15))
    # The second tank's name would sit on the first one's, so it goes up and gets a tick to its tank
    assert browser.wait_for(driver, f"{ticks} === '[1]'")
    run(live, put(first.x + 200 if first.x < 300 else first.x - 200))
    assert browser.wait_for(driver, f"{ticks} === '[]'")
