"""The page in headless Chrome against the real hub and the real cog, with a stand-in bank and a seeded deck"""

import asyncio
import contextlib
import io
import random
import time

import pytest
from piccolo.engine.sqlite import SQLiteEngine
from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from vegas.common.catalog import GAMES
from vegas.common.money import Money
from vegas.db.tables import TABLES
from vegas.main import Vegas
from vegas.tests.fakes import FakeBank, FakeConn, FakeRoom

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="vegas"]'
UPRIGHT_PHONE = {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}
# The move each game's test presses whenever the bot asks: the one that ends the round soonest
QUICK_MOVE = {"blackjack": "stay", "war": "surrender", "double": "cashout", "craps": "roll"}


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


def on_loop(live, coro):
    return asyncio.run_coroutine_threadsafe(coro, live.loop).result(15)


async def make_tables():
    for table in TABLES:
        await table.create_table(if_not_exists=True)


@pytest.fixture
def live(tmp_path, driver):
    hub = fakes.make_hub()
    hub.bot.get_guild(fakes.GUILD_ID).roles = []
    cog = Vegas(hub.bot)
    engine = SQLiteEngine(path=str(tmp_path / "casino.sqlite"))
    for table in TABLES:
        table._meta.db = engine
    cog.bank = FakeBank(start=1000)
    cog.money = Money(cog.store, cog.bank)
    cog.rng = random.Random(7)
    assert fakes.register(hub, cog) is not None
    server = browser.LiveHub(hub, browser.hub_web_copy(tmp_path))
    server.start()
    on_loop(server, make_tables())
    cog.ready.set()
    server.cog = cog
    driver.set_window_size(1280, 800)
    browser.fresh(driver, server)
    yield server
    on_loop(server, cog.cog_unload())
    server.stop()


def open_casino(driver, live, balance="1,000"):
    driver.get(f"{live.url}/{browser.DISCORD_QUERY}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(driver, f"document.getElementById('balance').textContent === '{balance}'", timeout=20)


def walk_up(driver, game):
    driver.find_element(By.CSS_SELECTOR, f'.station[data-key="{game}"]').click()
    browser.wait_for(driver, "!document.getElementById('table').hidden")
    browser.wait_for(driver, "document.getElementById('status-text').textContent !== 'Walking up to the table...'")


def problems(driver):
    return [line for line in browser.console_lines(driver) if "Uncaught" in line or "Vegas:" in line]


def test_the_lobby_shows_every_table_and_the_casino(driver, live):
    open_casino(driver, live)
    assert len(driver.find_elements(By.CSS_SELECTOR, "#floor .station")) == 9
    assert driver.find_element(By.ID, "casino-name").text == "Redjumpman's Casino"
    assert driver.find_element(By.ID, "tier").text == "Basic"
    assert driver.find_element(By.ID, "open-settings").get_attribute("hidden") is not None
    assert not problems(driver)


@pytest.mark.parametrize("game", ["allin", "blackjack", "coin", "craps", "cups", "dice", "hilo", "war", "double"])
def test_every_game_plays_a_round(driver, live, game):
    open_casino(driver, live)
    walk_up(driver, game)
    if game == "blackjack":
        driver.find_element(By.ID, "sit").click()
        browser.wait_for(driver, "!document.getElementById('stand').hidden")
    choice = driver.find_elements(By.CSS_SELECTOR, "#choices button")
    if choice:
        choice[0].click()
    browser.wait_for(driver, "!document.getElementById('place').disabled && !document.getElementById('place').hidden")
    driver.find_element(By.ID, "place").click()
    if game == "allin":
        browser.wait_for(driver, "document.getElementById('confirm').open")
        driver.find_element(By.ID, "confirm-yes").click()
    # Press the quickest move whenever the bot asks, until the result shows
    for _ in range(120):
        if driver.execute_script("return !document.getElementById('result').hidden"):
            break
        move = QUICK_MOVE.get(game)
        buttons = driver.find_elements(By.CSS_SELECTOR, f'#moves [data-move="{move}"]') if move else []
        if buttons and buttons[0].is_displayed():
            buttons[0].click()
        driver.execute_script("return new Promise((resolve) => setTimeout(resolve, 250))")
    big = driver.find_element(By.ID, "result-big").text
    assert big.startswith(("You win", "House wins", "No luck", "Bust", "Push", "Surrendered")), big
    assert not problems(driver)


def test_a_called_coin_flip_pays_the_multiplied_bet(driver, live):
    live.cog.rng = random.Random(1)
    side = random.Random(1).choice(("heads", "tails"))
    on_loop(live, live.cog.store.save_game(fakes.GUILD_ID, "coin", cooldown=60))
    open_casino(driver, live)
    walk_up(driver, "coin")
    driver.find_element(By.CSS_SELECTOR, f'#choices [data-choice="{side}"]').click()
    driver.find_element(By.ID, "place").click()
    browser.wait_for(driver, "!document.getElementById('result').hidden", timeout=10)
    assert driver.find_element(By.ID, "result-big").text == "You win 15"
    browser.wait_for(driver, "document.getElementById('balance').textContent === '1,005'")
    # Once the round ends, the cooldown greys the tray out and says why
    browser.wait_for(driver, "document.getElementById('why').textContent.includes('Coin is ready again in')")


def test_only_admins_get_the_settings_and_their_changes_reach_the_tables(driver, live):
    live.user_id = fakes.MANAGER_ID
    open_casino(driver, live)
    driver.find_element(By.ID, "open-settings").click()
    browser.wait_for(driver, "document.querySelectorAll('#panel-tabs button').length === 5")
    driver.find_element(By.XPATH, "//nav[@id='panel-tabs']/button[text()='Games']").click()
    row = driver.find_element(By.XPATH, "//table[contains(@class,'grid')]//tr[td[text()='Coin']]")
    maximum = row.find_elements(By.CSS_SELECTOR, "input[type=number]")[2]
    maximum.clear()
    maximum.send_keys("20")
    row.find_element(By.XPATH, ".//button[text()='Save']").click()
    browser.wait_for(driver, "document.getElementById('toast').textContent === 'Saved.'")
    game = on_loop(live, live.cog.store.game(fakes.GUILD_ID, "coin"))
    assert game.max_bet == 20
    assert not problems(driver)


def test_house_rules_stats_and_memberships_open_for_everyone(driver, live):
    open_casino(driver, live)
    driver.find_element(By.ID, "open-rules").click()
    browser.wait_for(driver, "document.getElementById('panel-body').textContent.includes('How to play')")
    assert "Redjumpman's Casino" in driver.find_element(By.ID, "panel-body").text
    driver.find_element(By.ID, "panel-close").click()
    driver.find_element(By.ID, "open-stats").click()
    browser.wait_for(driver, "document.getElementById('panel-body').textContent.includes('pushes or surrenders')")
    driver.find_element(By.ID, "panel-close").click()
    driver.find_element(By.ID, "open-tiers").click()
    browser.wait_for(driver, "document.getElementById('panel-body').textContent.includes('Everyone plays as Basic')")
    assert not problems(driver)


def test_on_an_upright_phone_the_floor_pans_and_the_dock_sits_under_the_scene(driver, live):
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", UPRIGHT_PHONE)
    try:
        open_casino(driver, live)
        browser.wait_for(driver, "document.getElementById('lobby').scrollLeft > 0")
        walk_up(driver, "dice")
        scene = driver.execute_script("return document.getElementById('scene').getBoundingClientRect().bottom")
        dock = driver.execute_script("return document.querySelector('.dock').getBoundingClientRect().top")
        assert dock >= scene - 1
        assert driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth")
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_a_player_short_of_the_minimum_bet_is_told_why(driver, live):
    live.cog.bank.balances[fakes.MEMBER_ID] = 5
    open_casino(driver, live, balance="5")
    walk_up(driver, "dice")
    browser.wait_for(driver, "!document.getElementById('why').hidden")
    assert driver.find_element(By.ID, "why").text == "You don't have enough credits for the minimum bet."
    assert not driver.find_element(By.ID, "place").is_displayed()


def test_all_in_says_it_bets_everything_and_asks_first(driver, live):
    open_casino(driver, live)
    walk_up(driver, "allin")
    browser.wait_for(driver, "document.getElementById('place').textContent === 'Bet all 1,000'")
    assert driver.find_element(By.ID, "all-in-stake").text == "Bets your whole balance: 1,000"
    assert driver.find_element(By.ID, "all-in-odds").text == "1 in 4 chance to win 2,000. Lose and your balance is 0."
    driver.find_element(By.ID, "mult-up").click()
    assert driver.find_element(By.ID, "all-in-odds").text.startswith("1 in 5 chance to win 3,000.")
    driver.find_element(By.ID, "place").click()
    browser.wait_for(driver, "document.getElementById('confirm').open")
    assert "whole balance of 1,000" in driver.find_element(By.ID, "confirm-text").text
    assert driver.find_element(By.ID, "confirm-yes").text == "Yes, go all in"
    driver.find_element(By.ID, "confirm-no").click()
    # Saying no sends nothing: no result, and the balance is untouched
    driver.execute_script("return new Promise((resolve) => setTimeout(resolve, 500))")
    assert live.cog.bank.balances.get(fakes.MEMBER_ID) == 1000
    assert driver.find_element(By.ID, "result").get_attribute("hidden") is not None
    driver.find_element(By.ID, "place").click()
    browser.wait_for(driver, "document.getElementById('confirm').open")
    driver.find_element(By.ID, "confirm-yes").click()
    browser.wait_for(driver, "!document.getElementById('result').hidden", timeout=15)
    assert not problems(driver)


def test_the_membership_form_keeps_a_deleted_role_and_warns_about_open_memberships(driver, live):
    # The role 4242 was deleted from the server after the membership was made
    live.hub.bot.get_guild(fakes.GUILD_ID).get_role = lambda role_id: None
    gold = {"name": "Gold", "color": "yellow", "access": 1, "req_role_id": 4242}
    on_loop(live, live.cog.store.save_membership(fakes.GUILD_ID, gold))
    live.user_id = fakes.MANAGER_ID
    open_casino(driver, live)
    driver.find_element(By.ID, "open-settings").click()
    browser.wait_for(driver, "document.querySelectorAll('#panel-tabs button').length === 5")
    driver.find_element(By.XPATH, "//nav[@id='panel-tabs']/button[text()='Memberships']").click()
    driver.find_element(By.XPATH, "//*[@id='panel-body']//button[text()='Edit']").click()
    role = driver.find_element(By.XPATH, "//label[contains(., 'Needs role')]/select")
    assert role.get_attribute("value") == "4242" and "Deleted role" in role.text
    assert not driver.find_element(By.CSS_SELECTOR, "#panel-body p.warn").is_displayed()
    driver.find_element(By.XPATH, "//*[@id='panel-body']//button[text()='Save']").click()
    browser.wait_for(driver, "document.getElementById('toast').textContent === 'Saved.'")
    assert on_loop(live, live.cog.store.membership_named(fakes.GUILD_ID, "Gold")).req_role_id == 4242
    driver.find_element(By.XPATH, "//*[@id='panel-body']//button[text()='New membership']").click()
    warning = driver.find_element(By.CSS_SELECTOR, "#panel-body p.warn")
    assert warning.is_displayed() and "every player gets it automatically" in warning.text
    assert not problems(driver)


def test_a_membership_raises_the_trays_max_bet(driver, live):
    gold = on_loop(live, live.cog.store.save_membership(fakes.GUILD_ID, {"name": "Gold", "bet_boost": 2.0}))
    on_loop(live, live.cog.store.set_membership(fakes.GUILD_ID, fakes.MEMBER_ID, gold.id, by_hand=True))
    open_casino(driver, live)
    walk_up(driver, "dice")
    driver.find_element(By.ID, "max").click()
    browser.wait_for(driver, "document.getElementById('amount').textContent === '200'")
    assert not problems(driver)


def me_on_the_hub(live):
    return live.server.presence.windows["i-1"].people[fakes.MEMBER_ID]


def guest(live, user_id, name=None):
    """A member of the test server when the id is one of theirs, otherwise someone made up"""
    guild = live.hub.bot.get_guild(fakes.GUILD_ID)
    return guild.get_member(user_id) or fakes.fake_member(fakes.fake_user(user_id, name or f"guest{user_id}"), guild)


def stand_at(live, user_id, spot, name=None):
    """Put another player on the floor in the bot's records: at a table, or in the lobby when the spot is None"""

    async def place():
        floor = live.cog.floors["i-1"]
        conn = FakeConn(FakeRoom("i-1"), guest(live, user_id, name), floor.guild)
        floor.where[conn] = spot
        await floor.send_lobby()
        return conn

    return on_loop(live, place())


def faces_in(driver, selector):
    return driver.execute_script(
        "return [...document.querySelectorAll(arguments[0] + ' .face')].map((face) => [face.dataset.name, face.title])",
        selector,
    )


def test_the_lobby_shows_faces_and_the_status(driver, live):
    open_casino(driver, live)
    browser.wait_for(driver, "document.querySelectorAll('.lobby-crowd .face').length === 1")
    assert driver.find_element(By.CSS_SELECTOR, ".lobby-crowd .face").is_displayed()
    me = me_on_the_hub(live)
    WebDriverWait(driver, 10).until(lambda _: me.status == "In the lobby")
    assert me.busy is False
    assert driver.execute_script("return document.querySelector('.tools .hub-people') !== null")
    assert not problems(driver)


def test_a_table_sign_shows_three_faces_then_the_rest_and_the_lobby_shows_its_crowd(driver, live):
    open_casino(driver, live)
    for user_id in range(101, 106):
        stand_at(live, user_id, "blackjack")
    stand_at(live, 106, "craps")
    stand_at(live, 107, None)
    sign = ".station[data-key='blackjack']"
    browser.wait_for(driver, f'document.querySelectorAll("{sign} .faces .face").length === 3')
    assert driver.find_element(By.CSS_SELECTOR, f"{sign} .faces .more").text == "+2"
    browser.wait_for(driver, "document.querySelectorAll(\".station[data-key='craps'] .faces .face\").length === 1")
    assert driver.find_elements(By.CSS_SELECTOR, ".station[data-key='craps'] .faces .more") == []
    browser.wait_for(driver, "document.querySelectorAll('.lobby-crowd .face').length === 2")
    assert [name for name, title in faces_in(driver, ".lobby-crowd")][-1] == "Guest107"
    assert not problems(driver)


@contextlib.contextmanager
def at_size(driver, width, height, scale, mobile):
    """The page at a screen size, such as a phone held upright or sideways"""
    metrics = {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": mobile}
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", metrics)
    try:
        yield
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


SIZES = [
    pytest.param((1280, 720, 1, False), id="desktop"),
    pytest.param((390, 844, 2, True), id="phone"),
    pytest.param((844, 390, 2, True), id="sideways"),
    pytest.param((320, 568, 2, True), id="small-phone"),
]


async def fill_tables(live, people, spots):
    """Put this many other players at each of these spots in the bot's records, then tell everyone"""
    floor = live.cog.floors["i-1"]
    for spot in spots:
        for number in range(people):
            conn = FakeConn(FakeRoom("i-1"), guest(live, 101 + number), floor.guild)
            floor.where[conn] = spot
    await floor.send_lobby()


LOBBY_AND_STRIP = """
const box = (node) => { const r = node.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
const foot = document.querySelector('.lobby-foot');
return {
  lobby: box(document.getElementById('lobby')),
  foot: foot.hidden ? null : box(foot),
  faces: [...document.querySelectorAll('.lobby-crowd .face')].map(box),
  window: [innerWidth, innerHeight],
  sideways: document.documentElement.scrollWidth > innerWidth,
};
"""


@pytest.mark.parametrize("size", SIZES)
def test_the_row_of_faces_takes_its_room_from_the_floor(driver, live, size):
    with at_size(driver, *size):
        open_casino(driver, live)
        for user_id in range(101, 111):
            stand_at(live, user_id, None)
        browser.wait_for(driver, "document.querySelectorAll('.lobby-crowd .face').length === 8")
        found = driver.execute_script(LOBBY_AND_STRIP)
        lobby, foot = found["lobby"], found["foot"]
        # The floor ends where the strip starts, so the strip can't be over a table, and everything stays on screen
        assert foot is not None and lobby[3] <= foot[1] + 0.5 and foot[3] <= found["window"][1] + 0.5
        assert all(face[0] >= 0 and face[2] <= found["window"][0] for face in found["faces"])
        assert not found["sideways"]
        assert not problems(driver)


def test_the_phone_lobby_opens_in_the_middle_once_the_faces_row_is_there(driver, live):
    with at_size(driver, 390, 844, 2, True):
        open_casino(driver, live)
        browser.wait_for(driver, "document.querySelectorAll('.lobby-crowd .face').length === 1")
        # The slot machine's medallion is at the exact middle of the picture. The row of faces took room from the
        # floor after it was centred, which must not leave the view off to one side
        middle = driver.execute_script(
            "const box = document.querySelector(\".station[data-key='allin'] .medallion\").getBoundingClientRect();"
            "return [(box.left + box.right) / 2, innerWidth / 2];"
        )
        assert abs(middle[0] - middle[1]) <= 4
        assert not problems(driver)


ROWS_AND_NEIGHBOURS = """
// The medallions bob, which moves a row of faces a few pixels. It stands still here so the check is the same each time
const still = document.createElement('style');
still.textContent = '.medallion { animation: none !important; }';
document.head.append(still);
const box = (node) => node.getBoundingClientRect();
const touches = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
const stations = [...document.querySelectorAll('.station')];
const found = [];
for (const station of stations) {
  const row = box(station.querySelector('.faces'));
  const more = station.querySelector('.faces .more');
  for (const other of stations.filter((node) => node !== station)) {
    if (touches(row, box(other)) || touches(row, box(other.querySelector('.medallion')))) {
      found.push(station.dataset.key + ' touches ' + other.dataset.key);
    }
  }
  found.push(station.dataset.key + ' says ' + (more ? more.textContent : 'nothing'));
}
return found;
"""


@pytest.mark.parametrize("size", SIZES)
def test_a_tables_faces_stay_clear_of_the_next_table_even_with_a_crowd(driver, live, size):
    with at_size(driver, *size):
        open_casino(driver, live)
        on_loop(live, fill_tables(live, 13, list(GAMES)))
        browser.wait_for(driver, "document.querySelectorAll('.station .faces .face').length === 27")
        found = driver.execute_script(ROWS_AND_NEIGHBOURS)
        assert [line for line in found if "touches" in line] == []
        assert sorted(line for line in found if "says" in line) == sorted(f"{game} says +10" for game in GAMES)
        assert not problems(driver)


def test_the_hubs_arrival_note_shows_over_the_floor(driver, live):
    open_casino(driver, live)
    # The hub makes no arrival notes for a few seconds after a page connects. This ends that quiet time at once
    driver.switch_to.default_content()
    driver.execute_script("window.activityhubHost.presence.quietUntil = 0")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    live.add_person(fakes.MANAGER_ID, where="vegas")
    browser.wait_for(driver, "document.querySelector('.hub-note') !== null")
    # Its slide-in, which fades it up from nothing, is done
    browser.wait_for(driver, "document.querySelector('.hub-note').getAnimations().length === 0")
    # A point in the note's padding at its middle height, away from its rounded corners, and under the top bar
    # where the floor would show if it were painted over the note
    x, y, ratio = driver.execute_script(
        "const note = document.querySelector('.hub-note').getBoundingClientRect();"
        "const bar = document.querySelector('.top').getBoundingClientRect();"
        "return [note.left + 5, Math.max(note.top + note.height / 2, bar.bottom + 3), window.devicePixelRatio];"
    )
    shot = Image.open(io.BytesIO(driver.get_screenshot_as_png())).convert("RGB")
    # The note is the hub's blue, since the page sets no accent of its own
    found = shot.getpixel((round(x * ratio), round(y * ratio)))
    assert all(abs(got - want) <= 12 for got, want in zip(found, (0x58, 0x65, 0xF2))), found
    assert not problems(driver)


def test_a_face_names_who_it_is_and_what_they_are_doing(driver, live):
    open_casino(driver, live)
    other = live.add_person(fakes.MANAGER_ID, where="vegas", status="Blackjack \u00b7 bet 200")
    stand_at(live, fakes.MANAGER_ID, "blackjack")
    sign = ".station[data-key='blackjack']"
    browser.wait_for(driver, f'document.querySelectorAll("{sign} .faces .face").length === 1')
    browser.wait_for(driver, f'document.querySelector("{sign} .face").title.endsWith("Blackjack \\u00b7 bet 200")')
    assert faces_in(driver, sign)[0][1].startswith("\u2068Manager\u2069")
    # A new status shows without the face being redrawn, which would lose a tap on it
    driver.execute_script(
        "window.redrawn = 0;"
        "document.querySelectorAll('.faces, .lobby-crowd').forEach((box) =>"
        "  new MutationObserver((list) => { window.redrawn += list.length; }).observe(box, { childList: true }));"
    )
    live.update_person(other, where="vegas", status="Blackjack")
    browser.wait_for(driver, f'document.querySelector("{sign} .face").title.endsWith("Blackjack")')
    # Away people are dimmed and say so
    live.update_person(other, where="vegas", status="Blackjack", away=True)
    browser.wait_for(driver, f'document.querySelector("{sign} .face.away") !== null')
    assert faces_in(driver, sign)[0][1].endswith("Away")
    time.sleep(0.6)
    assert driver.execute_script("return window.redrawn") == 0
    assert not problems(driver)


async def keep_scoring(live, conn, stop):
    """Someone else in the window whose status changes every tenth of a second, so a new people list goes out as
    often as the hub sends them, until `stop` has something in it"""
    for score in range(1, 300):
        if stop:
            return
        state = {"where": "vegas", "status": f"Craps · bet {score}", "data": None, "busy": True, "away": False}
        await live.server.presence.update(conn, state)
        await asyncio.sleep(0.1)


def test_a_click_on_a_tables_name_opens_it_while_people_lists_keep_coming(driver, live):
    open_casino(driver, live)
    other = live.add_person(fakes.MANAGER_ID, where="vegas", status="Craps")
    stand_at(live, fakes.MANAGER_ID, "craps")
    face = ".station[data-key='craps'] .face"
    browser.wait_for(driver, f'document.querySelector("{face}")?.title.endsWith("Craps")')
    driver.execute_script(
        "window.relabelled = 0;"
        "document.querySelectorAll('.station .label').forEach((label) =>"
        "  new MutationObserver((list) => { window.relabelled += list.length; })"
        "    .observe(label, { childList: true, subtree: true, characterData: true }));"
    )
    stop = []
    scoring = asyncio.run_coroutine_threadsafe(keep_scoring(live, other, stop), live.loop)
    try:
        # A few lists have arrived. They are merged up to 4 a second, so the face can skip a number
        browser.wait_for(driver, f'Number(document.querySelector("{face}").title.split("bet ")[1]) >= 3')
        # Lists that change no table's name or note leave every name label as it is
        assert driver.execute_script("return window.relabelled") == 0
        # A press held long enough for more lists to arrive before the release still opens the table
        label = driver.find_element(By.CSS_SELECTOR, ".station[data-key='hilo'] .label")
        ActionChains(driver).move_to_element(label).click_and_hold().pause(0.8).release().perform()
        browser.wait_for(driver, "!document.getElementById('table').hidden")
        assert driver.execute_script("return document.getElementById('app').dataset.view") == "table"
    finally:
        stop.append(True)
        scoring.result(15)
    assert not problems(driver)


def test_a_long_name_is_cut_without_splitting_a_character(driver, live):
    open_casino(driver, live)
    stand_at(live, 101, None, name="Ana\U0001f469\u200d\U0001f4bbBellecarlotta")
    browser.wait_for(driver, "document.querySelectorAll('.lobby-crowd .face').length === 2")
    title = faces_in(driver, ".lobby-crowd")[-1][1]
    assert title == "\u2068Ana\U0001f469\u200d\U0001f4bbBelleca\u2026\u2069"


TOAST_AND_FACES = """
const box = (node) => { const r = node.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
return {
  toast: box(document.getElementById('toast')),
  foot: box(document.querySelector('.lobby-foot')),
  faces: [...document.querySelectorAll('.lobby-crowd .face, .lobby-crowd .more')].map(box),
};
"""


@pytest.mark.parametrize("size", SIZES)
def test_tapping_a_face_in_the_lobby_says_who_it_is_without_covering_the_faces(driver, live, size):
    with at_size(driver, *size):
        open_casino(driver, live)
        stand_at(live, 101, None, name="Zed")
        for user_id in range(102, 111):
            stand_at(live, user_id, None)
        browser.wait_for(driver, "document.querySelectorAll('.lobby-crowd .face').length === 8")
        driver.find_element(By.CSS_SELECTOR, ".lobby-crowd .face[data-name='Zed']").click()
        browser.wait_for(driver, "!document.getElementById('toast').hidden")
        assert driver.find_element(By.ID, "toast").text == "\u2068Zed\u2069"
        # The card stands on the strip under the floor, so it hides none of the faces it is about
        found = driver.execute_script(TOAST_AND_FACES)
        toast, foot = found["toast"], found["foot"]
        assert toast[3] <= foot[1] + 0.5
        for face in found["faces"]:
            assert not (face[0] < toast[2] and toast[0] < face[2] and face[1] < toast[3] and toast[1] < face[3]), face
        assert not problems(driver)


def test_a_picture_that_will_not_load_is_a_letter(driver, live):
    open_casino(driver, live)
    guild = live.hub.bot.get_guild(fakes.GUILD_ID)
    who = fakes.fake_member(fakes.fake_user(101, "Zed"), guild)
    who.display_avatar = type(who.display_avatar)(url="http://127.0.0.1:1/missing.png")
    guild.members[101] = who
    stand_at(live, 101, None)
    face = ".lobby-crowd .face[data-name='Zed']"
    browser.wait_for(driver, f'document.querySelector("{face}") && !document.querySelector("{face} img")')
    assert driver.find_element(By.CSS_SELECTOR, face).text == "Z"


async def friend_at(live, user_id, game):
    """A friend who is already on the floor, at a table when there is one, when the player's page opens"""
    guild = live.hub.bot.get_guild(fakes.GUILD_ID)
    conn = FakeConn(FakeRoom("i-1"), guild.get_member(user_id), guild)
    await live.cog.join(conn.ctx, conn)
    if game:
        await live.cog.message(conn.ctx, conn, {"t": "enter", "game": game})


def join_friend(driver, live, user_id):
    """Open the casino the way the hub's Join button does, with the friend as the follow"""
    driver.get(f"{live.url}/{browser.DISCORD_QUERY}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.execute_script(f"window.activityhubHost.join({{id: '{user_id}', name: 'Friend', game: 'vegas'}})")
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(driver, "document.getElementById('balance').textContent === '1,000'", timeout=20)


def where_am_i(live):
    floor = live.cog.floors["i-1"]
    return [game for conn, game in floor.where.items() if conn.ctx.author.id == fakes.MEMBER_ID]


def test_joining_a_friend_walks_to_their_table(driver, live):
    on_loop(live, friend_at(live, fakes.MANAGER_ID, "dice"))
    join_friend(driver, live, fakes.MANAGER_ID)
    browser.wait_for(driver, "!document.getElementById('table').hidden")
    WebDriverWait(driver, 10).until(lambda _: where_am_i(live) == ["dice"])
    me = me_on_the_hub(live)
    WebDriverWait(driver, 10).until(lambda _: me.status == "At Dice")
    # Back on the floor, the walk is not done again
    driver.find_element(By.ID, "back").click()
    browser.wait_for(driver, "!document.getElementById('lobby').hidden")
    time.sleep(0.8)
    assert where_am_i(live) == [None]
    assert not problems(driver)


@pytest.mark.parametrize("friend_on_the_floor", [True, False])
def test_a_friend_in_the_lobby_or_gone_leaves_the_player_in_the_lobby(driver, live, friend_on_the_floor):
    if friend_on_the_floor:
        on_loop(live, friend_at(live, fakes.MANAGER_ID, None))
    join_friend(driver, live, fakes.MANAGER_ID)
    browser.wait_for(driver, "document.querySelectorAll('.lobby-crowd .face').length >= 1")
    time.sleep(0.8)
    assert where_am_i(live) == [None]
    assert driver.execute_script("return document.getElementById('table').hidden")
    assert not problems(driver)


def test_a_friend_at_a_closed_table_still_gets_the_walk(driver, live):
    on_loop(live, live.cog.store.save_game(fakes.GUILD_ID, "dice", is_open=False))
    on_loop(live, friend_at(live, fakes.MANAGER_ID, "dice"))
    join_friend(driver, live, fakes.MANAGER_ID)
    browser.wait_for(driver, "!document.getElementById('table').hidden")
    browser.wait_for(driver, "document.getElementById('why').textContent === 'Dice is closed.'")
    assert where_am_i(live) == ["dice"]


def test_the_status_and_busy_flag_follow_the_player_through_a_round(driver, live):
    open_casino(driver, live)
    me = me_on_the_hub(live)
    walk_up(driver, "dice")
    WebDriverWait(driver, 10).until(lambda _: me.status == "At Dice")
    assert me.busy is False and me.data == {"table": "dice"}
    driver.find_element(By.ID, "place").click()
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    assert me.status.startswith("Dice \u00b7 bet ")
    browser.wait_for(driver, "!document.getElementById('result').hidden", timeout=15)
    WebDriverWait(driver, 10).until(lambda _: not me.busy)
    assert me.status == "At Dice"
    driver.find_element(By.ID, "back").click()
    WebDriverWait(driver, 10).until(lambda _: me.status == "In the lobby")
    assert not problems(driver)


def test_the_craps_shooter_says_they_have_the_dice(driver, live):
    open_casino(driver, live)
    me = me_on_the_hub(live)
    walk_up(driver, "craps")
    driver.find_element(By.ID, "place").click()
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    assert me.status == "Craps \u00b7 has the dice"


def test_an_unchanged_status_is_not_sent_again_while_the_table_keeps_talking(driver, live):
    open_casino(driver, live)
    me = me_on_the_hub(live)
    walk_up(driver, "dice")
    WebDriverWait(driver, 10).until(lambda _: me.status == "At Dice")
    time.sleep(0.6)
    sent = []
    original = live.server.presence.update

    async def counting(conn, data):
        sent.append(data)
        await original(conn, data)

    live.server.presence.update = counting
    table = live.cog.floors["i-1"].tables["dice"]
    for _ in range(4):
        on_loop(live, table.push())
    time.sleep(1.2)
    assert sent == []


def test_a_closed_connection_says_not_connected_and_clears_busy(driver, live):
    open_casino(driver, live)
    me = me_on_the_hub(live)
    walk_up(driver, "dice")
    driver.find_element(By.ID, "place").click()
    WebDriverWait(driver, 10).until(lambda _: me.busy)
    conn = next(conn for conn in live.cog.floors["i-1"].where if conn.ctx.author.id == fakes.MEMBER_ID)
    on_loop(live, conn.close(4100))
    WebDriverWait(driver, 10).until(lambda _: me.status == "Not connected")
    assert me.busy is False
