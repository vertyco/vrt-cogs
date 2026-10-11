"""The page in headless Chrome against the real hub and the real cog, with a hand-moved clock and seeded rolls"""

import asyncio
import os
import random

import pytest
from piccolo.engine.sqlite import SQLiteEngine
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait

from farmcord.catalog import ANIMALS
from farmcord.common.actions import OPENING
from farmcord.db.tables import TABLES
from farmcord.game.animals import arrive
from farmcord.game.calendar import DAY, HOUR, season_at, weather_at
from farmcord.game.market import PLACES
from farmcord.game.model import Animal
from farmcord.game.progress import xp_for_level
from farmcord.main import FarmCord
from farmcord.tests.fakes import Clock, FakeBank, Today

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="farmcord"]'
PLAYER_ID = fakes.MEMBER_ID
SIZES = {
    "desktop": {"width": 1280, "height": 800, "deviceScaleFactor": 1, "mobile": False},
    "phone": {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True},
    "sideways": {"width": 844, "height": 390, "deviceScaleFactor": 2, "mobile": True},
}
# The farm's map: each room's exits. The farmhouse's extra rooms open off it, each door shown once the room is owned
MAP = {
    "farmhouse": {"right": "yard", "left": "room2"},
    "room2": {"right": "farmhouse", "left": "room3"},
    "room3": {"right": "room2"},
    "yard": {"left": "farmhouse", "up": "pond", "down": "market", "right": "farmland1"},
    "pond": {"down": "yard"},
    "market": {"up": "yard"},
    "farmland1": {"left": "yard", "up": "plot1", "down": "plot2", "right": "farmland2"},
    "farmland2": {"left": "farmland1", "up": "plot3", "down": "plot4", "right": "farmland3"},
    "farmland3": {"left": "farmland2", "up": "plot5", "down": "plot6", "right": "plot7"},
    "plot1": {"down": "farmland1"},
    "plot2": {"up": "farmland1"},
    "plot3": {"down": "farmland2"},
    "plot4": {"up": "farmland2"},
    "plot5": {"down": "farmland3"},
    "plot6": {"up": "farmland3"},
    "plot7": {"left": "farmland3"},
}
WEATHER_WORDS = {"sun": "Sunny", "rain": "Rain", "snow": "Snow"}
# The toast for a failure on the page's side, as opposed to the bot turning an action down
PAGE_BUG = "Something went wrong. If it keeps happening, close FarmCord and open it again."
# How long the page waits to ask for the farm again after a request for it failed
RETRY_MS = 30_000


@pytest.fixture(scope="module")
def driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--mute-audio")
    options.add_argument("--window-size=1280,800")
    # PixiJS needs WebGL. Headless Chrome may have no graphics card to use, and this lets it draw in software
    options.add_argument("--enable-unsafe-swiftshader")
    # Left to itself, Selenium opens a log file for the driver and never closes it
    with open(os.devnull, "wb") as log:
        try:
            chrome = webdriver.Chrome(options=options, service=Service(log_output=log))
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
    cog = FarmCord(hub.bot)
    engine = SQLiteEngine(path=str(tmp_path / "farmcord.sqlite"))
    for table in TABLES:
        table._meta.db = engine
    cog.clock = Clock()
    cog.rng = random.Random(1)
    cog.payouts.bank = FakeBank()
    cog.payouts.today = Today()
    assert fakes.register(hub, cog) is not None
    server = browser.LiveHub(hub, browser.hub_web_copy(tmp_path))
    server.start()
    on_loop(server, make_tables())
    on_loop(server, cog.config.clear_all())
    cog.ready.set()
    server.cog = cog
    driver.set_window_size(1280, 800)
    browser.fresh(driver, server)
    yield server
    on_loop(server, cog.cog_unload())
    # Chrome lets go of the page's connections before the server goes, so none is cut off mid-request
    driver.get("about:blank")
    server.stop()
    # The hub's test server stops its event loop with connections still closing. A moment more lets them close, then
    # the loop closes with its own sockets
    server.loop.run_until_complete(asyncio.sleep(0.2))
    server.loop.close()


def enter_game(driver, live, menu_script=""):
    """FarmCord's frame opened from the hub's menu, without waiting for the farm. `menu_script` runs in the menu first"""
    driver.switch_to.default_content()
    driver.get(f"{live.url}/{browser.DISCORD_QUERY}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    if menu_script:
        driver.execute_script(menu_script)
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))


def open_farm(driver, live):
    enter_game(driver, live)
    browser.wait_for(driver, "!document.querySelector('.purse').hidden", timeout=30)


def fail_next(driver, action):
    """The page's next request for this action fails on the way, like a dropped connection"""
    driver.execute_script(
        """
        const real = window.fetch;
        window.fetch = (url, ...rest) => {
          if (!String(url).endsWith(`/api/${arguments[0]}`)) {
            return real(url, ...rest);
          }
          window.fetch = real;
          return Promise.reject(new TypeError("the connection dropped"));
        };
        """,
        action,
    )


def shorten_retries(driver):
    """The page's wait before asking again takes a moment instead, and each one asked for is kept in window.retries"""
    driver.execute_script(f"""
      const wait = window.setTimeout;
      window.retries = [];
      window.setTimeout = (fn, ms, ...rest) => {{
        if (ms === {RETRY_MS}) {{
          window.retries.push(ms);
          return wait(fn, 100, ...rest);
        }}
        return wait(fn, ms, ...rest);
      }};
    """)


def problems(driver):
    return [line for line in browser.console_lines(driver) if "Uncaught" in line or "FarmCord:" in line]


def text(driver, element_id):
    return driver.find_element(By.ID, element_id).text


def exits(driver):
    return {button.get_attribute("data-dir"): button.text for button in driver.find_elements(By.CSS_SELECTOR, ".exit")}


def walk(driver, direction, room):
    driver.find_element(By.CSS_SELECTOR, f'.exit[data-dir="{direction}"]').click()
    browser.wait_for(driver, f"document.getElementById('room-name').textContent === '{room}'")


def press(driver, key):
    driver.find_element(By.TAG_NAME, "body").send_keys(key)


def pressed(driver, element_id):
    return driver.find_element(By.ID, element_id).get_attribute("aria-pressed")


def saved_farm(live):
    return on_loop(live, live.cog.store.load(PLAYER_ID))


def wait_until(driver, check, timeout=10):
    WebDriverWait(driver, timeout).until(lambda _: check())


def watch_toasts(driver):
    """Keeps every toast shown from now on, since toasts leave on their own. toasts_seen() reads them"""
    driver.execute_script("""
      window.toastsSeen = [];
      new MutationObserver((changes) => {
        for (const change of changes) {
          window.toastsSeen.push(...[...change.addedNodes].map((node) => `${node.className}: ${node.textContent}`));
        }
      }).observe(document.getElementById("toasts"), { childList: true });
    """)


def toasts_seen(driver):
    return driver.execute_script("return window.toastsSeen")


async def change_farm(cog, **changes):
    farm = await cog.store.load(PLAYER_ID)
    for name, value in changes.items():
        setattr(farm, name, value)
    await cog.store.save(farm)


async def raise_a_chick(cog, level):
    """A chick in a pen, and the farm's XP just short of `level`, so the chick growing up reaches it"""
    farm = await cog.store.load(PLAYER_ID)
    farm.plots[2].unlocked = True
    farm.plots[2].kind = "animals"
    chick = Animal(kind="chicken", sex="female", plot=2)
    arrive(chick, cog.clock())
    farm.animals.append(chick)
    farm.level = level - 1
    farm.xp = xp_for_level(level) - 10
    await cog.store.save(farm)


def test_the_farm_opens_in_the_farmhouse_with_the_hud(driver, live):
    open_farm(driver, live)
    now = live.cog.clock()
    assert text(driver, "room-name") == "Farmhouse"
    assert driver.find_element(By.ID, "app").get_attribute("data-room") == "farmhouse"
    assert text(driver, "coins") == "0"
    assert text(driver, "level") == "Level 1"
    assert text(driver, "season") == season_at(now).title()
    assert text(driver, "weather-name") == WEATHER_WORDS[weather_at(now)]
    assert exits(driver) == {"right": "Yard"}
    tools = [button.get_attribute("data-tool") for button in driver.find_elements(By.CSS_SELECTOR, "#tools .tool")]
    assert tools == ["hoe", "can", "seed", "feed", "hand"]
    assert driver.find_element(By.CSS_SELECTOR, '.tool[data-tool="can"] .badge').text == "10/10"
    assert driver.find_element(By.CSS_SELECTOR, '.tool[data-tool="hand"]').get_attribute("aria-pressed") == "true"
    assert driver.find_element(By.ID, "notice").get_attribute("hidden") is not None
    assert not driver.find_element(By.ID, "away").get_attribute("open")
    assert not problems(driver)


def test_the_direction_buttons_and_arrow_keys_walk_between_rooms(driver, live):
    open_farm(driver, live)
    walk(driver, "right", "Yard")
    assert driver.find_element(By.ID, "app").get_attribute("data-room") == "yard"
    assert exits(driver) == {"left": "Farmhouse", "up": "Pond", "down": "Market", "right": "Farmland"}
    walk(driver, "left", "Farmhouse")
    press(driver, Keys.ARROW_RIGHT)
    browser.wait_for(driver, "document.getElementById('room-name').textContent === 'Yard'")
    press(driver, Keys.ARROW_UP)
    browser.wait_for(driver, "document.getElementById('room-name').textContent === 'Pond'")
    # No way out to the left of the Pond, so the key does nothing
    press(driver, Keys.ARROW_LEFT)
    press(driver, Keys.ARROW_DOWN)
    browser.wait_for(driver, "document.getElementById('room-name').textContent === 'Yard'")
    assert not problems(driver)


def test_the_rooms_follow_the_map(driver, live):
    open_farm(driver, live)
    script = """
      const done = arguments[arguments.length - 1];
      import("./rooms.js").then((rooms) => {
        const all = Object.entries(rooms.ROOMS);
        done([Object.fromEntries(all.map(([id, room]) => [id, room.exits])), all.filter(([, room]) => room.floor)
          .map(([id]) => id)]);
      });
    """
    exits, floors = driver.execute_async_script(script)
    assert exits == MAP
    # Decorations stand only where the bot places them
    assert sorted(floors) == sorted(PLACES)


def test_the_sound_and_music_switches_save_with_the_farm(driver, live):
    open_farm(driver, live)
    driver.find_element(By.ID, "sound").click()
    assert pressed(driver, "sound") == "false"
    wait_until(driver, lambda: not saved_farm(live).sound)
    assert driver.execute_script("return localStorage.getItem('farmcord:sound')") == "off"
    driver.find_element(By.ID, "music").click()
    assert pressed(driver, "music") == "false"
    driver.find_element(By.ID, "sound").click()
    assert pressed(driver, "sound") == "true"
    wait_until(driver, lambda: saved_farm(live).sound and not saved_farm(live).music)
    assert driver.execute_script("return localStorage.getItem('farmcord:music')") == "off"
    assert not problems(driver)


def test_the_switches_saved_with_the_farm_win_when_it_opens(driver, live):
    open_farm(driver, live)
    driver.execute_script("localStorage.setItem('farmcord:music', 'on')")
    on_loop(live, change_farm(live.cog, music=False))
    open_farm(driver, live)
    assert pressed(driver, "music") == "false"
    assert pressed(driver, "sound") == "true"
    assert driver.execute_script("return localStorage.getItem('farmcord:music')") == "off"


def test_the_seed_button_picks_a_seed_the_farm_owns(driver, live):
    open_farm(driver, live)
    seeds = driver.find_element(By.CSS_SELECTOR, '.tool[data-tool="seed"]')
    seeds.click()
    browser.wait_for(driver, "!document.getElementById('picker').hidden")
    assert text(driver, "picker-title") == "Seeds"
    choice = driver.find_element(By.CSS_SELECTOR, '#picker-list .choice[data-key="seed:wildflowers"]')
    # Each seed says how long it takes to grow if planted today: the test's day is in Wildflowers' season
    assert choice.text.split("\n") == ["Wildflowers", "Grows in 30 min", "5"]
    choice.click()
    assert driver.find_element(By.ID, "picker").get_attribute("hidden") is not None
    assert seeds.get_attribute("aria-pressed") == "true"
    assert seeds.find_element(By.CSS_SELECTOR, ".badge").text == "5"
    # A new farm has no feed, so the feed picker says where to get some and the seed stays chosen
    driver.find_element(By.CSS_SELECTOR, '.tool[data-tool="feed"]').click()
    assert text(driver, "picker-empty") == "You have no feed. Buy some at the Market, or grow a feed crop."
    driver.find_element(By.ID, "picker-close").click()
    assert seeds.get_attribute("aria-pressed") == "true"
    driver.find_element(By.CSS_SELECTOR, '.tool[data-tool="hoe"]').click()
    assert seeds.get_attribute("aria-pressed") == "false"
    assert not problems(driver)


def test_the_away_summary_and_the_level_up_popup_show_on_open(driver, live):
    ctx = fakes.context_for(live.hub)
    cog = live.cog
    on_loop(live, cog.act_open(ctx, {}))
    on_loop(live, cog.act_till(ctx, {"plot": 1, "spot": 0}))
    on_loop(live, cog.act_plant(ctx, {"plot": 1, "spot": 0, "crop": "wildflowers"}))
    on_loop(live, raise_a_chick(cog, 5))
    cog.clock.move(DAY - HOUR)
    open_farm(driver, live)
    browser.wait_for(driver, "document.getElementById('away').open")
    lines = text(driver, "away-lines")
    assert "Wildflowers in Plot 1 are ripe" in lines
    assert "Wildflowers in Plot 1 dried out" in lines
    assert "Your chicken grew up" in lines or "Your exceptional chicken grew up" in lines
    driver.find_element(By.ID, "away-ok").click()
    browser.wait_for(driver, "document.getElementById('levelup').open")
    assert text(driver, "levelup-title") == "Level 5!"
    assert text(driver, "levelup-coins") == "+50 FarmCoins"
    unlocks = text(driver, "levelup-unlocks")
    assert "Plot 2" in unlocks and "Big watering can" in unlocks
    driver.find_element(By.ID, "levelup-ok").click()
    browser.wait_for(driver, "!document.getElementById('levelup').open")
    assert text(driver, "level") == "Level 5"
    assert not problems(driver)


def test_the_page_asks_again_when_a_moment_it_shows_passes(driver, live):
    ctx = fakes.context_for(live.hub)
    on_loop(live, live.cog.act_open(ctx, {}))
    on_loop(live, raise_a_chick(live.cog, 5))
    # The page opens 2 seconds before the chick grows up, and the bot's clock moves on past it
    live.cog.clock.move(ANIMALS["chicken"].grow_time - 2)
    open_farm(driver, live)
    assert text(driver, "level") == "Level 4"
    live.cog.clock.move(5)
    browser.wait_for(driver, "document.getElementById('levelup').open", timeout=15)
    assert text(driver, "level") == "Level 5"
    toasts = driver.execute_script("return [...document.querySelectorAll('#toasts .toast')].map((t) => t.textContent)")
    assert any(toast.startswith(("Your chicken grew up", "Your exceptional chicken grew up")) for toast in toasts)
    assert not problems(driver)


def test_a_refused_request_shows_the_bots_reason(driver, live):
    open_farm(driver, live)
    live.cog.ready.clear()
    driver.find_element(By.ID, "sound").click()
    # The toast's text, read whole: it fades in, and Selenium reads text it can't see yet as empty
    toast = browser.wait_for(driver, "document.querySelector('#toasts .toast.error')?.textContent")
    assert toast == OPENING


def test_a_bug_in_a_room_view_goes_to_the_console_not_a_refusal_toast(driver, live):
    open_farm(driver, live)
    watch_toasts(driver)
    # Views that break: the Farmhouse's when a new state arrives, and the Yard's, an async one, when the farmer walks in
    driver.execute_async_script("""
      const done = arguments[arguments.length - 1];
      import("./game.js").then((game) => {
        game.VIEWS.farmhouse = { update() { throw new Error("the farmhouse view broke"); } };
        game.VIEWS.yard = { async enter() { throw new Error("the yard view broke"); } };
        done();
      });
    """)
    driver.find_element(By.ID, "sound").click()
    seen = browser.wait_for_console(driver, "the farmhouse view broke")
    # The bot took the action, and the page still keeps the state and moves between rooms
    wait_until(driver, lambda: not saved_farm(live).sound)
    walk(driver, "right", "Yard")
    seen += browser.wait_for_console(driver, "the yard view broke")
    walk(driver, "left", "Farmhouse")
    assert [line for line in seen if "view broke" in line and "FarmCord:" not in line] == []
    assert toasts_seen(driver) == [f"toast error: {PAGE_BUG}"] * 2


def test_a_lost_connection_is_not_shown_as_the_bots_refusal(driver, live):
    open_farm(driver, live)
    watch_toasts(driver)
    driver.execute_script("window.fetch = () => Promise.reject(new TypeError('the connection dropped'))")
    driver.find_element(By.ID, "sound").click()
    seen = browser.wait_for_console(driver, "the connection dropped")
    assert [line for line in seen if "connection dropped" in line and "FarmCord:" not in line] == []
    assert toasts_seen(driver) == [f"toast error: {PAGE_BUG}"]


def test_a_failed_refresh_asks_the_bot_again_later(driver, live):
    ctx = fakes.context_for(live.hub)
    on_loop(live, live.cog.act_open(ctx, {}))
    on_loop(live, raise_a_chick(live.cog, 5))
    live.cog.clock.move(ANIMALS["chicken"].grow_time - 2)
    open_farm(driver, live)
    watch_toasts(driver)
    shorten_retries(driver)
    fail_next(driver, "state")
    # The chick grows up and the page asks the bot. That request fails, and the page asks again a little later
    live.cog.clock.move(5)
    browser.wait_for_console(driver, "the connection dropped", timeout=15)
    browser.wait_for(driver, "document.getElementById('levelup').open", timeout=15)
    assert text(driver, "level") == "Level 5"
    assert driver.execute_script("return window.retries") == [RETRY_MS]
    assert toasts_seen(driver)[0] == f"toast error: {PAGE_BUG}"


def test_a_farm_that_fails_to_open_offers_to_try_again(driver, live):
    live.cog.ready.clear()
    enter_game(driver, live)
    # The bot turned the request down, so the notice gives the bot's words
    browser.wait_for(driver, f"document.getElementById('notice-text').textContent === {OPENING!r}")
    retry = browser.wait_for(
        driver, "!document.getElementById('notice-retry').hidden && document.getElementById('notice-retry')"
    )
    assert retry.text == "Try again"
    # A failure on the page's side gets the plain words, never the error's own text
    fail_next(driver, "open")
    retry.click()
    browser.wait_for(driver, f"document.getElementById('notice-text').textContent === {PAGE_BUG!r}")
    seen = browser.wait_for_console(driver, "the connection dropped")
    assert [line for line in seen if "connection dropped" in line and "FarmCord:" not in line] == []
    live.cog.ready.set()
    driver.find_element(By.ID, "notice-retry").click()
    browser.wait_for(driver, "!document.querySelector('.purse').hidden")
    assert driver.find_element(By.ID, "notice").get_attribute("hidden") is not None
    assert text(driver, "room-name") == "Farmhouse"


def test_the_switches_wait_for_the_farm_to_open(driver, live):
    """A press while the farm is opening would race the switches saved with the farm"""
    on_loop(live, live.cog.act_open(fakes.context_for(live.hub), {}))
    lock = live.cog.locks[PLAYER_ID]
    on_loop(live, lock.acquire())
    try:
        enter_game(driver, live)
        # Connected: the hub's "who's here" button is in the HUD, and the open request waits on the bot
        browser.wait_for(driver, "document.getElementById('people').children.length")
        driver.find_element(By.ID, "sound").click()
        driver.find_element(By.ID, "music").click()
        assert (pressed(driver, "sound"), pressed(driver, "music")) == ("true", "true")
    finally:
        live.loop.call_soon_threadsafe(lock.release)
    browser.wait_for(driver, "!document.querySelector('.purse').hidden")
    assert (pressed(driver, "sound"), pressed(driver, "music")) == ("true", "true")
    driver.find_element(By.ID, "sound").click()
    assert pressed(driver, "sound") == "false"
    wait_until(driver, lambda: not saved_farm(live).sound)
    assert saved_farm(live).music
    assert not problems(driver)


def test_a_page_that_breaks_while_starting_says_so(driver, live):
    enter_game(
        driver,
        live,
        "window.activityhubHost.people.frameButton = () => { throw new Error('the people button broke'); };",
    )
    browser.wait_for(driver, f"document.getElementById('notice-text').textContent === {PAGE_BUG!r}")
    seen = browser.wait_for_console(driver, "the people button broke")
    assert [line for line in seen if "people button broke" in line and "FarmCord:" not in line] == []


@pytest.mark.parametrize("size", ["phone", "sideways"])
def test_phones_keep_the_hud_the_tools_and_the_exits_on_screen(driver, live, size):
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES[size])
    try:
        open_farm(driver, live)
        walk(driver, "right", "Yard")
        assert driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth")
        boxes = driver.execute_script(
            """
            const box = (node) => node.getBoundingClientRect().toJSON();
            const all = [...document.querySelectorAll('.exit, .tool, .switch, #back, .purse, .level, .weather')];
            return { all: all.map(box), tools: box(document.getElementById('tools')),
                     hud: box(document.getElementById('hud')),
                     down: box(document.querySelector('.exit[data-dir="down"]')),
                     up: box(document.querySelector('.exit[data-dir="up"]')),
                     width: innerWidth, height: innerHeight };
            """
        )
        for box in boxes["all"]:
            assert box["left"] >= 0 and box["right"] <= boxes["width"], box
            assert box["top"] >= 0 and box["bottom"] <= boxes["height"], box
        assert boxes["down"]["bottom"] <= boxes["tools"]["top"]
        assert boxes["up"]["top"] >= boxes["hud"]["bottom"]
        assert not problems(driver)
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
