"""Texas Hold'em's dock in headless Chrome against the real hub and cog: the action bar, the moves ticked in advance,
buying in, the bot's offers, and what the hub hears the player is doing"""

import asyncio
import math
import re
import threading
import time

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait

from vegas.common.games.holdem import Action
from vegas.common.table import DECISION_TIME, PACE
from vegas.tests import test_browser
from vegas.tests.fakes import FakeConn, FakeRoom
from vegas.tests.test_browser import (
    at_size,
    browser,
    fakes,
    guest,
    me_on_the_hub,
    on_loop,
    open_casino,
    problems,
    walk_up,
)

driver = test_browser.driver
live = test_browser.live
ME = fakes.MEMBER_ID
# Animations and CPU thinking run at this share of their real time, so a hand takes seconds
SPEED = 0.2
SIZES = {"desktop": (1280, 800, 1, False), "phone": (390, 844, 2, True), "sideways": (844, 390, 2, True)}


def calm(spot, rng):
    """A CPU that calls whatever is bet and checks otherwise, so every hand reaches the showdown"""
    return Action("call") if spot.legal.call else Action("check")


def held(gate, play=calm):
    """CPUs that wait for `gate` (a threading.Event) before each move. They think off the bot's loop, so waiting there
    holds only the hand"""

    def choose(spot, rng):
        gate.wait(10)
        return play(spot, rng)

    return choose


def flop_bettor(first, second):
    """CPUs that play the preflop calmly. On the flop the first one to act waits for `first` and bets, and the rest
    wait for `second`"""
    flop = []

    def choose(spot, rng):
        if spot.street != "flop":
            return calm(spot, rng)
        flop.append(spot)
        if len(flop) == 1:
            first.wait(10)
            return Action("raise", spot.legal.min_to)
        second.wait(10)
        return calm(spot, rng)

    return choose


def quick_table(live, choose=calm):
    """The window's Hold'em table, made before anyone walks up to it: quick, with CPUs that play `choose`. Also returns
    a list of every event it sends, with each message the page's player sends it as kind "page" """
    events = []

    async def make():
        table = live.cog.floors["i-1"].table("holdem")
        table.speed = SPEED
        table.choose = choose
        send, handle = table.event, table.handle

        async def event(kind, **data):
            events.append({"kind": kind, **data})
            await send(kind, **data)

        async def heard(conn, kind, data):
            if conn.ctx.author.id == ME:
                events.append({"kind": "page", **data})
            await handle(conn, kind, data)

        table.event, table.handle = event, heard
        return table

    return on_loop(live, make()), events


def said(events, kind):
    return [event for event in events if event["kind"] == "page" and event["t"] == kind]


def hold_deals(table, gate):
    """No hand is dealt until `gate` opens, so seated players wait between hands"""
    prepare = table.prepare

    async def held_prepare():
        await asyncio.to_thread(gate.wait, 10)
        return await prepare()

    table.prepare = held_prepare


def second_device(live):
    """The page's player with the casino open on another device too, at the Hold'em table"""

    async def arrive():
        floor = live.cog.floors["i-1"]
        conn = FakeConn(FakeRoom("i-1"), guest(live, ME), floor.guild)
        floor.where[conn] = None
        await floor.enter(conn, "holdem")
        return conn

    return on_loop(live, arrive())


class Caller(FakeConn):
    """Someone else at the table whose page calls or checks whenever the bot asks"""

    def __init__(self, room, who, guild, cog):
        super().__init__(room, who, guild)
        self.cog = cog

    async def send(self, data):
        await super().send(data)
        if data.get("t") == "ask" and data.get("game") == "holdem":
            move = "call" if "call" in data["moves"] else "check"
            asyncio.get_running_loop().create_task(self.cog.message(self.ctx, self, {"t": "move", "move": move}))


def sit_guest(live, user_id, seat, buy_in=None):
    """Someone else at the Hold'em table in the bot's records: sitting free, or buying in for this much"""

    async def sit():
        floor = live.cog.floors["i-1"]
        conn = Caller(FakeRoom("i-1"), guest(live, user_id), floor.guild, live.cog)
        floor.where[conn] = None
        await floor.enter(conn, "holdem")
        if buy_in is None:
            message = {"t": "sit", "seat": seat}
        else:
            message = {"t": "buy_in", "seat": seat, "amount": buy_in, "post": False}
        await live.cog.message(conn.ctx, conn, message)
        return conn

    return on_loop(live, sit())


# Where the scene draws a seat, from the middle of the canvas, in CSS pixels
SEAT_SPOT = """
const [number, done] = arguments;
import(new URL("scenes/holdem.js", document.baseURI).href).then((scene) => {
  const host = document.getElementById("scene");
  const spot = scene.layoutFor(host.clientWidth, host.clientHeight, null, true).seats[number];
  done([spot.x - host.clientWidth / 2, spot.y - host.clientHeight / 2]);
}).catch((e) => done(String(e)));
"""


def tap_seat(driver, number, until):
    """Tap a seat where the scene draws it, again until `until()` is true: the scene may still be starting"""
    browser.wait_for(driver, "document.querySelector('#scene canvas') !== null")
    dx, dy = driver.execute_async_script(SEAT_SPOT, number)
    for _ in range(10):
        canvas = driver.find_element(By.CSS_SELECTOR, "#scene canvas")
        ActionChains(driver).move_to_element_with_offset(canvas, int(dx), int(dy)).click().perform()
        try:
            WebDriverWait(driver, 1.5).until(lambda _: until())
            return
        except TimeoutException:
            continue
    raise AssertionError(f"tapping seat {number} did nothing")


def is_open(driver, element_id):
    return driver.execute_script(f"return document.getElementById('{element_id}').open")


def bar_up(driver):
    """The action bar is in and has finished sliding"""
    return driver.execute_script(
        "const bar = document.getElementById('hd-bar');"
        "return bar.classList.contains('up') && bar.getAnimations().length === 0"
    )


def call_until(driver, done, tries):
    """Presses Call whenever the action bar is up, until done() is true or the tries run out"""
    for _ in range(tries):
        if done():
            return
        if bar_up(driver):
            driver.find_element(By.ID, "hd-call").click()
        time.sleep(0.1)


def resized(driver, width, height):
    """The game's page has its new size: it reaches the page inside the hub's frame a frame after the screen changes"""
    browser.wait_for(driver, f"innerWidth === {width} && innerHeight === {height}")


def strip_up(driver):
    """The offer's strip shows in the dock and has finished popping in"""
    return driver.execute_script(
        "const strip = document.getElementById('hd-offer');return !strip.hidden && strip.getAnimations().length === 0"
    )


def ticks_shown(driver):
    return driver.execute_script("return !document.getElementById('hd-ticks').hidden")


def my_moves(events, seat):
    return [e for e in events if e["kind"] == "act" and e["seat"] == seat and e["move"] not in ("blind", "post")]


def text(driver, element_id):
    return driver.find_element(By.ID, element_id).text


def my_conn(live):
    """The page's own connection to the bot, for sending it tables and events the way the bot does"""
    floor = live.cog.floors["i-1"]
    return next(each for each in floor.where if each.ctx.author.id == ME and not isinstance(each, FakeConn))


# How many lines a button's words take, and whether they fit inside it
LINES = """
const node = document.querySelector(arguments[0]);
const range = document.createRange();
range.selectNodeContents(node);
const tops = new Set([...range.getClientRects()].map((rect) => Math.round(rect.top)));
return { lines: tops.size, fits: node.scrollWidth <= node.clientWidth };
"""


BAR = "#hd-bar button, #hd-bar input"
# Presses a button the way a finger would, then reports the dock in the same moment, before any answer can arrive
PRESS = """
document.getElementById(arguments[0]).click();
const pending = document.getElementById('hd-pending');
return {
  up: document.getElementById('hd-bar').classList.contains('up'),
  pending: pending.hidden ? null : pending.textContent,
};
"""


def test_a_lone_player_sits_free_and_plays_a_practice_hand_with_the_bar(driver, live):
    open_casino(driver, live)
    table, events = quick_table(live)
    walk_up(driver, "holdem")
    assert text(driver, "status-text") == "Tap an empty seat to practice for free."
    assert not driver.find_element(By.ID, "tray").is_displayed()
    tap_seat(driver, 0, lambda: table.seat_of(ME) is not None)
    assert table.seat_of(ME).real == 0
    # Seat 0 has the first button, so a CPU acts first and the player's first turn faces the big blind
    browser.wait_for(driver, "document.getElementById('hd-bar').classList.contains('up')", timeout=15)
    WebDriverWait(driver, 5).until(lambda _: bar_up(driver))
    assert text(driver, "hd-fold") == "Fold"
    assert re.fullmatch(r"Call\s+20", text(driver, "hd-call"))
    driver.find_element(By.CSS_SELECTOR, '#hd-sizes [data-size="pot"]').click()
    # A pot-sized raise: the call, then the pot once called. 20 to call into 50 makes it 90
    assert re.fullmatch(r"Raise to\s+90", text(driver, "hd-raise"))
    assert driver.execute_script(PRESS, "hd-raise") == {"up": False, "pending": "Raise to 90"}
    WebDriverWait(driver, 10).until(lambda _: my_moves(events, 0))
    assert my_moves(events, 0)[0]["move"] == "raise" and my_moves(events, 0)[0]["amount"] == 90
    # The words standing in for the raise go once the table plays it
    browser.wait_for(driver, "document.getElementById('hd-pending').hidden")
    # Then check or call to the end of the hand
    call_until(driver, lambda: any(event["kind"] == "win" for event in events), 300)
    assert any(event["kind"] == "win" for event in events)
    assert not problems(driver)


def test_a_second_player_gets_the_buy_in_dialog_and_the_practicer_gets_the_offer(driver, live):
    open_casino(driver, live)
    table, events = quick_table(live)
    other = sit_guest(live, fakes.MANAGER_ID, 0)
    walk_up(driver, "holdem")
    browser.wait_for(driver, "document.getElementById('status-text').textContent === 'Tap an empty seat to buy in.'")
    tap_seat(driver, 5, lambda: is_open(driver, "hd-buyin"))
    assert text(driver, "hd-buyin-title") == "Buy in"
    assert (text(driver, "hd-buyin-min"), text(driver, "hd-buyin-max")) == ("400", "2,000")
    # The slider starts at the most the player can pay: their whole balance of 1,000, under the 2,000 Max
    assert text(driver, "hd-buyin-amount") == "1,000"
    assert not driver.find_element(By.ID, "hd-buyin-left").is_displayed()
    assert not driver.find_element(By.ID, "hd-buyin-post").is_displayed()
    driver.find_element(By.ID, "hd-buyin-yes").click()
    WebDriverWait(driver, 10).until(lambda _: table.seat_of(ME) is not None)
    assert (table.seat_of(ME).number, table.seat_of(ME).real) == (5, 1000)
    assert not is_open(driver, "hd-buyin")
    # The practicer is asked to buy in so a real game can start, and saying yes starts it
    WebDriverWait(driver, 10).until(lambda _: other.of("offer"))
    offer = other.last("offer")
    assert (offer["kind"], offer["min"], offer["max"]) == ("join", 400, 2000)
    on_loop(live, live.cog.message(other.ctx, other, {"t": "buy_in", "seat": None, "amount": 1000}))
    me = me_on_the_hub(live)
    WebDriverWait(driver, 20).until(lambda _: me.status.startswith("Texas Hold'em · "))
    assert re.fullmatch(r"Texas Hold'em · [\d,]+ chips", me.status) and me.data == {"table": "holdem"}
    assert said(events, "buy_in") == [{"kind": "page", "t": "buy_in", "seat": 5, "amount": 1000, "post": False}]
    assert not problems(driver)


def test_a_seat_in_a_real_game_offers_both_ways_in(driver, live):
    open_casino(driver, live)
    table, events = quick_table(live)
    first = sit_guest(live, fakes.MANAGER_ID, 0)
    sit_guest(live, 101, 4, buy_in=1000)
    WebDriverWait(driver, 10).until(lambda _: first.of("offer"))
    on_loop(live, live.cog.message(first.ctx, first, {"t": "buy_in", "seat": None, "amount": 1000}))
    WebDriverWait(driver, 20).until(lambda _: table.mode == "real")
    walk_up(driver, "holdem")
    # The page may still be showing the last practice hand, which offers only the one way in
    for _ in range(20):
        tap_seat(driver, 5, lambda: is_open(driver, "hd-buyin"))
        if driver.find_element(By.ID, "hd-buyin-post").is_displayed():
            break
        driver.find_element(By.ID, "hd-buyin-no").click()
        time.sleep(0.3)
    assert text(driver, "hd-buyin-post") == "Pay 20 and play now"
    assert text(driver, "hd-buyin-wait") == "Wait for the big blind"
    assert not driver.find_element(By.ID, "hd-buyin-yes").is_displayed()
    assert text(driver, "hd-buyin-no") == "Cancel"
    driver.find_element(By.ID, "hd-buyin-wait").click()
    assert not is_open(driver, "hd-buyin")
    WebDriverWait(driver, 10).until(lambda _: said(events, "buy_in"))
    assert said(events, "buy_in") == [{"kind": "page", "t": "buy_in", "seat": 5, "amount": 1000, "post": False}]
    WebDriverWait(driver, 10).until(lambda _: table.seat_of(ME) is not None)
    assert not problems(driver)


# With 20 to call when the turn comes, Check/Fold folds and Call any calls
@pytest.mark.parametrize("advance, move", [("check_fold", "fold"), ("call_any", "call")])
def test_check_fold_and_call_any_act_by_themselves_when_the_turn_comes(driver, live, advance, move):
    open_casino(driver, live)
    gate = threading.Event()
    table, events = quick_table(live, held(gate))
    try:
        walk_up(driver, "holdem")
        tap_seat(driver, 0, lambda: table.seat_of(ME) is not None)
        # Seat 0 has the button, so the CPU after the big blind thinks first, held until the gate opens
        browser.wait_for(driver, "!document.getElementById('hd-ticks').hidden", timeout=15)
        assert not bar_up(driver)
        tick = driver.find_element(By.CSS_SELECTOR, f'#hd-ticks [data-advance="{advance}"]')
        tick.click()
        assert tick.get_attribute("aria-pressed") == "true"
        gate.set()
        WebDriverWait(driver, 15).until(lambda _: my_moves(events, 0))
        # No button was pressed and the action bar never came
        assert my_moves(events, 0)[0]["move"] == move
        assert tick.get_attribute("aria-pressed") == "false"
        assert not bar_up(driver)
    finally:
        gate.set()
    assert not problems(driver)


def test_a_ticked_check_clears_when_a_bet_appears(driver, live):
    open_casino(driver, live)
    first, second = threading.Event(), threading.Event()
    table, events = quick_table(live, flop_bettor(first, second))
    try:
        walk_up(driver, "holdem")
        tap_seat(driver, 0, lambda: table.seat_of(ME) is not None)
        # Call the preflop with the bar, then tick Check on the flop while the first CPU thinks
        call_until(driver, lambda: table.street == "flop" and ticks_shown(driver), 150)
        check = driver.find_element(By.CSS_SELECTOR, '#hd-ticks [data-advance="check"]')
        check.click()
        assert check.get_attribute("aria-pressed") == "true"
        moves = len(said(events, "move"))
        first.set()
        # The CPU bets while the next one thinks: Check can't happen now, so it clears and greys out
        browser.wait_for(driver, """document.querySelector('#hd-ticks [data-advance="check"]').disabled""")
        assert check.get_attribute("aria-pressed") == "false"
        assert ticks_shown(driver)
        second.set()
        # So the turn brings the bar instead of a move made by itself
        WebDriverWait(driver, 15).until(lambda _: bar_up(driver))
        assert len(said(events, "move")) == moves
    finally:
        first.set()
        second.set()
    assert not problems(driver)


def test_the_status_says_practicing_then_watching(driver, live):
    open_casino(driver, live)
    gate = threading.Event()
    table, events = quick_table(live, held(gate))
    me = me_on_the_hub(live)
    try:
        walk_up(driver, "holdem")
        WebDriverWait(driver, 10).until(lambda _: me.status == "Watching Hold'em")
        assert me.busy is False and me.data == {"table": "holdem"}
        tap_seat(driver, 0, lambda: table.seat_of(ME) is not None)
        WebDriverWait(driver, 10).until(lambda _: me.status == "Practicing Hold'em" and me.busy)
        # Standing up mid-hand greys the button at once, and the seat goes when the hand ends
        stand = driver.find_element(By.ID, "hd-stand")
        stand.click()
        assert not stand.is_enabled()
        browser.wait_for(driver, "document.getElementById('status-text').textContent.includes('stand up')")
        gate.set()
        WebDriverWait(driver, 20).until(lambda _: me.status == "Watching Hold'em" and not me.busy)
        browser.wait_for(driver, "document.getElementById('hd-stand').hidden")
    finally:
        gate.set()
    assert not problems(driver)


def test_the_practicer_gets_a_counted_down_offer_and_watch_instead_stands_them_up(driver, live):
    open_casino(driver, live)
    table, events = quick_table(live)
    me = me_on_the_hub(live)
    walk_up(driver, "holdem")
    tap_seat(driver, 0, lambda: table.seat_of(ME) is not None)
    WebDriverWait(driver, 10).until(lambda _: table.street is not None)
    sit_guest(live, fakes.MANAGER_ID, 5, buy_in=1000)
    # Dealt into a practice hand, so the offer is a strip in the dock. It waits while the bar asks for a move
    call_until(driver, lambda: strip_up(driver), 150)
    assert strip_up(driver) and not is_open(driver, "hd-buyin")
    assert text(driver, "hd-buyin-title") == "A real game is starting. Buy in?"
    assert re.fullmatch(r"\d+s", text(driver, "hd-buyin-left"))
    assert re.fullmatch(r"Buy in\s+1,000", text(driver, "hd-buyin-yes"))
    # Saying no takes the player off the table, and the button says so
    assert text(driver, "hd-buyin-no") == "Watch instead"
    driver.find_element(By.ID, "hd-buyin-no").click()
    browser.wait_for(driver, "document.getElementById('hd-offer').hidden")
    WebDriverWait(driver, 10).until(lambda _: said(events, "decline"))
    # The practice hand plays out, then the player who said no stands up to watch
    call_until(driver, lambda: me.status == "Watching Hold'em", 300)
    assert me.status == "Watching Hold'em"
    assert table.seat_of(ME) is None
    assert not problems(driver)


# Each control found by the selector: big enough for a thumb on a phone, takes a press at its middle, and on screen
CONTROLS_CHECK = """
const [selector, mobile] = arguments;
const controls = [...document.querySelectorAll(selector)].filter(
  (node) => node.offsetParent !== null && getComputedStyle(node).visibility === 'visible'
);
const box = (node) => node.getBoundingClientRect();
return {
  controls: controls.length,
  small: controls.filter((node) => mobile && box(node).height < 44).map((node) => node.id || node.textContent),
  missed: controls.filter((node) => {
    const r = box(node);
    return !node.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2));
  }).map((node) => node.id || node.textContent),
  off: controls.filter((node) => {
    const r = box(node);
    return r.left < 0 || r.top < 0 || r.right > innerWidth || r.bottom > innerHeight;
  }).map((node) => node.id || node.textContent),
};
"""


def test_the_bar_fits_a_thumb_at_every_size(driver, live):
    open_casino(driver, live)
    table, events = quick_table(live)
    walk_up(driver, "holdem")
    tap_seat(driver, 0, lambda: table.seat_of(ME) is not None)
    browser.wait_for(driver, "document.getElementById('hd-bar').classList.contains('up')", timeout=15)
    for name, (width, height, scale, mobile) in SIZES.items():
        with at_size(driver, width, height, scale, mobile):
            resized(driver, width, height)
            WebDriverWait(driver, 5).until(lambda _: bar_up(driver))
            found = driver.execute_script(CONTROLS_CHECK, BAR, mobile)
            # Min, ½ pot, ¾ pot, Pot, All in, the slider, Fold, Call and Raise
            assert found == {"controls": 9, "small": [], "missed": [], "off": []}, name
    assert not problems(driver)


SCENE_HEIGHT = "return document.getElementById('scene').getBoundingClientRect().height"
UNDER_STATUS = """
const box = (id) => document.getElementById(id).getBoundingClientRect();
return box('status').bottom <= box('hd-bar').top;
"""


def test_on_an_upright_phone_the_bar_leaves_the_status_line_and_the_table_in_place(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    ask = {"t": "ask", "game": "holdem", "moves": ["fold", "call", "raise"], "call": 60, "min_to": 120}
    ask.update(max_to=1940, pot=190, bet=0)
    with at_size(driver, 390, 844, 2, True):
        resized(driver, 390, 844)
        # A real hand, so the dock has no practice line: it is as short as it gets for a seated player
        on_loop(live, conn.send({**a_hand_on_the_flop(), "mode": "real"}))
        browser.wait_for(driver, "!document.getElementById('hd-ticks').hidden")
        between = driver.execute_script(SCENE_HEIGHT)
        on_loop(live, conn.send({**a_hand_on_the_flop(), "mode": "real", "turn": 0}))
        on_loop(live, conn.send(ask))
        WebDriverWait(driver, 5).until(lambda _: bar_up(driver))
        assert driver.execute_script(UNDER_STATUS)
        assert driver.execute_script(SCENE_HEIGHT) == between
    assert not problems(driver)


# The dock holds the bot's offer to join, whether or not its strip shows; the offer's seconds left; whether the
# status line shows
OFFER_OPEN = "return document.getElementById('hd-buyin-title').textContent.startsWith('A real game is starting.')"
SECONDS_LEFT = "return parseInt(document.getElementById('hd-buyin-left').textContent, 10) || 0"
STATUS_SHOWN = "return document.getElementById('status').getBoundingClientRect().height > 0"


def test_an_offer_on_the_players_turn_waits_behind_the_bar_and_comes_back_with_its_full_time(driver, live):
    open_casino(driver, live)
    table, events = quick_table(live)
    walk_up(driver, "holdem")
    tap_seat(driver, 0, lambda: table.seat_of(ME) is not None)
    browser.wait_for(driver, "document.getElementById('hd-bar').classList.contains('up')", timeout=15)
    # A newcomer buys in while the player thinks about their move
    sit_guest(live, fakes.MANAGER_ID, 5, buy_in=1000)
    WebDriverWait(driver, 10).until(lambda _: driver.execute_script(OFFER_OPEN))
    asked = time.monotonic()
    assert not is_open(driver, "hd-buyin")
    for name, (width, height, scale, mobile) in SIZES.items():
        with at_size(driver, width, height, scale, mobile):
            resized(driver, width, height)
            WebDriverWait(driver, 5).until(lambda _: bar_up(driver))
            # While the bar is up the offer hides completely, at every size: the bar's 9 controls are all there is,
            # the status line still shows, and nothing hangs past the dock's bottom
            found = driver.execute_script(CONTROLS_CHECK, f"{BAR}, #hd-offer button, #hd-offer input", mobile)
            assert found == {"controls": 9, "small": [], "missed": [], "off": []}, name
            assert driver.execute_script("return document.getElementById('hd-offer').hidden"), name
            assert driver.execute_script(STATUS_SHOWN) and driver.execute_script(DOCK_STILL), name
    # Escape is no answer while the hand goes on
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    time.sleep(max(0.3, 5 - (time.monotonic() - asked)))
    assert said(events, "decline") == []
    # The player moves: the bot starts the offer's time over, and its strip shows with all of it
    driver.find_element(By.ID, "hd-call").click()
    WebDriverWait(driver, 10).until(lambda _: my_moves(events, 0))
    assert my_moves(events, 0)[0]["move"] == "call"
    WebDriverWait(driver, 5).until(
        lambda _: strip_up(driver) and driver.execute_script(SECONDS_LEFT) >= DECISION_TIME - 2
    )
    driver.find_element(By.ID, "hd-buyin-no").click()
    browser.wait_for(driver, "document.getElementById('hd-offer').hidden")
    WebDriverWait(driver, 10).until(lambda _: said(events, "decline"))
    assert not problems(driver)


def test_an_offer_between_hands_is_the_dialog_and_closes_when_answered_on_another_device(driver, live):
    open_casino(driver, live)
    gate = threading.Event()
    table, events = quick_table(live)
    hold_deals(table, gate)
    try:
        walk_up(driver, "holdem")
        tap_seat(driver, 0, lambda: table.seat_of(ME) is not None)
        other_device = second_device(live)
        sit_guest(live, fakes.MANAGER_ID, 5, buy_in=1000)
        # Not dealt into a hand, so the offer is the dialog
        browser.wait_for(driver, "document.getElementById('hd-buyin').open", timeout=10)
        assert not driver.find_element(By.ID, "hd-offer").is_displayed()
        assert text(driver, "hd-buyin-title") == "A real game is starting. Buy in?"
        # Saying no on the other device makes the bot close the offer everywhere, and this page sends nothing more
        on_loop(live, live.cog.message(other_device.ctx, other_device, {"t": "decline"}))
        browser.wait_for(driver, "!document.getElementById('hd-buyin').open")
        time.sleep(0.3)
        assert len(said(events, "decline")) == 1
    finally:
        gate.set()
    assert not problems(driver)


QUICK_SIZES = """
const done = arguments[arguments.length - 1];
import(new URL("holdem.js", document.baseURI).href).then(({ ladder, quickSize }) => {
  const ask = { bet: 0, call: 20, pot: 50, min_to: 40, max_to: 2000 };
  const sizes = ["min", "half", "three", "pot", "all"].map((size) => quickSize(ask, size));
  const short = quickSize({ bet: 0, call: 0, pot: 30, min_to: 20, max_to: 100 }, "half");
  const deep = quickSize({ bet: 0, call: 0, pot: 900, min_to: 20, max_to: 100 }, "pot");
  const wide = ladder(400, 2000, 20);
  const odd = ladder(1234, 2000, 20);
  const flat = ladder(500, 500, 20);
  done({
    sizes, short, deep,
    wide: [wide.top, wide.at(0), wide.at(1), wide.at(79), wide.at(80), wide.index(1000)],
    odd: [odd.top, odd.at(0), odd.at(1), odd.at(38), odd.at(39)],
    flat: [flat.top, flat.at(0), flat.index(900)],
  });
}).catch((e) => done({ error: String(e) }));
"""


def test_quick_sizes_and_the_sliders_stops(driver, live):
    open_casino(driver, live)
    found = driver.execute_async_script(QUICK_SIZES)
    # 20 to call into a pot of 50: half the called pot of 70 is 35, so ½ pot raises to 55, ¾ to 73, Pot to 90
    assert found["sizes"] == [40, 55, 73, 90, 2000]
    # Kept inside the ask's range
    assert (found["short"], found["deep"]) == (20, 100)
    # A slider stops at both ends exactly and at every big blind between them
    assert found["wide"] == [80, 400, 420, 1980, 2000, 30]
    assert found["odd"] == [39, 1234, 1240, 1980, 2000]
    assert found["flat"] == [0, 500, 0]


# ---------- The table scene ----------

HOLDEM_KINDS = ("seat", "unseat", "button", "act", "pitch", "sweep", "flop", "street", "runout", "show", "win")
# Makes the Hold'em scene on a stage of its own inside the casino's page, the way table.js does, with the sounds it
# asks for written down. The Pixi ticker stays stopped, so only the scene's own animations move anything
SCENE_HARNESS = """
async function makeScene(width, height, me, laidOut = true) {
  const pixi = await import(new URL("vendor/pixi.min.mjs", document.baseURI).href);
  const holdem = await import(new URL("scenes/holdem.js", document.baseURI).href);
  const app = new pixi.Application();
  await app.init({ width, height, backgroundAlpha: 0, autoStart: false });
  const root = new pixi.Container();
  app.stage.addChild(root);
  const played = [];
  const stage = {
    app,
    root,
    game: "holdem",
    title: "Texas Hold'em",
    sound: { play: (name) => played.push(name) },
    me: () => me,
    nameOf: (id) => id,
    actions: { sit() {}, stand() {}, choose() {}, move() {}, place() {} },
  };
  const scene = await holdem.createScene(stage);
  if (laidOut) {
    scene.layout(width, height);
  }
  return { app, root, scene, played };
}
"""
PLAY_ALL = """
const [me, steps, done] = arguments;
(async () => {
  const { app, scene, played } = await makeScene(900, 600, me);
  const timings = [];
  for (const step of steps) {
    if (step.t === "table") {
      scene.show(step);
    } else if (step.t === "hole") {
      scene.hole(step);
    } else {
      const start = performance.now();
      await scene.play(step);
      timings.push([step.kind, performance.now() - start]);
    }
  }
  scene.destroy();
  app.destroy(true, { children: true });
  done({ timings, played });
})().catch((e) => done({ error: String((e && e.stack) || e) }));
"""


def card(text):
    """ "As" is the ace of spades, "10h" the ten of hearts"""
    suits = {"s": "spades", "h": "hearts", "d": "diamonds", "c": "clubs"}
    return [text[:-1], suits[text[-1]]]


def cards(text):
    return [card(part) for part in text.split()]


def seat_row(number, name, stack, *, me=False, bet=0, in_hand=False, folded=False, all_in=False, last=None):
    return {
        "seat": number,
        "id": str(ME) if me else f"cpu-{number}",
        "name": name,
        "avatar": None,
        "cpu": not me,
        "stack": stack,
        "bet": bet,
        "in_hand": in_hand,
        "folded": folded,
        "all_in": all_in,
        "cards": 2 if in_hand and not folded else 0,
        "last": last,
        "waiting": False,
        "away": False,
    }


def table_state(seats, **changes):
    state = {
        "t": "table",
        "game": "holdem",
        "phase": "idle",
        "round": 3,
        "left": None,
        "players": [{"id": str(ME), "name": "Member", "avatar": None, "away": False}],
        "mode": "practice",
        "stakes": {"small": 10, "big": 20, "min": 400, "max": 2000, "cut": 5},
        "seats": seats,
        "button": None,
        "board": [],
        "pots": [],
        "turn": None,
        "street": None,
        "hand": 3,
        "shown": {},
        "waiting": [],
    }
    state.update(changes)
    return state


def act(seat, move, amount, stack):
    return {"t": "event", "game": "holdem", "kind": "act", "seat": seat, "move": move, "amount": amount, "stack": stack}


def event(kind, **data):
    return {"t": "event", "game": "holdem", "kind": kind, **data}


def pitches(order):
    return [event("pitch", seat=seat) for seat in order * 2]


def a_hand_folded_on_the_turn():
    """Someone sits, then a hand in the bot's order: the table still on the last hand, the button, the blinds, the
    player's own cards, the deal, the new hand's first table at the first turn, a raise, the flop, checks, the turn, a
    bet everyone folds to"""
    seats = [
        seat_row(0, "Member", 2000, me=True),
        seat_row(1, "CPU Rosa", 2000),
        seat_row(2, "CPU Dex", 2000),
        None,
        seat_row(4, "CPU Mabel", 2000),
        None,
    ]
    joined = [*seats[:5], seat_row(5, "CPU Juno", 2000)]
    flop = [row and {**row, "in_hand": True, "cards": 2, "stack": 1940} for row in joined]
    flop[1] = {**flop[1], "stack": 1990, "folded": True, "cards": 0}
    flop[4] = {**flop[4], "stack": 2000, "folded": True, "cards": 0}
    dealt = [row and {**row, "in_hand": True, "cards": 2} for row in joined]
    dealt[1] = {**dealt[1], "stack": 1990, "bet": 10, "last": {"move": "blind", "amount": 10}}
    dealt[2] = {**dealt[2], "stack": 1980, "bet": 20, "last": {"move": "blind", "amount": 20}}
    return [
        table_state(seats, hand=2),
        table_state(joined, hand=2),
        event("seat", seat=5),
        event("button", seat=0),
        act(1, "blind", 10, 1990),
        act(2, "blind", 20, 1980),
        {"t": "hole", "game": "holdem", "hand": 3, "cards": cards("As Ks"), "name": "High card, Ace"},
        *pitches([1, 2, 4, 5, 0]),
        table_state(dealt, phase="playing", button=0, street="preflop", turn=4, left=35),
        act(4, "fold", 0, 2000),
        act(5, "raise", 60, 1940),
        act(0, "call", 60, 1940),
        act(1, "fold", 10, 1990),
        act(2, "call", 60, 1940),
        event("sweep", pots=[190]),
        event("flop", cards=cards("Ah 7c 2d")),
        table_state(flop, phase="playing", button=0, board=cards("Ah 7c 2d"), pots=[190], street="flop", turn=2),
        act(2, "check", 0, 1940),
        act(5, "check", 0, 1940),
        act(0, "check", 0, 1940),
        event("street", card=card("9s")),
        act(2, "check", 0, 1940),
        act(5, "raise", 120, 1820),
        act(0, "fold", 0, 1940),
        act(2, "fold", 0, 1940),
        act(5, "return", 0, 1940),
        event("win", awards=[{"amount": 190, "winners": [5], "shares": {"5": 190}}], best={}, cut=0, big=False),
    ]


def an_all_in_split_after_a_run_out():
    """Two players all in before the flop, the uncalled part back, both hands shown, five cards run out, a split"""
    seats = [
        seat_row(0, "Member", 1940, me=True),
        seat_row(1, "CPU Rosa", 1990),
        seat_row(2, "CPU Dex", 1940),
        None,
        seat_row(4, "CPU Mabel", 2000),
        seat_row(5, "CPU Juno", 2130),
    ]
    best = cards("Qh Qd Qs Qc Ac")
    shown = {
        "0": {"cards": cards("Qh Qd"), "name": "Pair of Queens"},
        "5": {"cards": cards("Qs Qc"), "name": "Pair of Queens"},
    }
    dealt = [row and {**row, "in_hand": True, "cards": 2} for row in seats]
    dealt[2] = {**dealt[2], "stack": 1930, "bet": 10, "last": {"move": "blind", "amount": 10}}
    dealt[4] = {**dealt[4], "stack": 1980, "bet": 20, "last": {"move": "blind", "amount": 20}}
    return [
        table_state(seats, hand=3, round=3, button=0),
        event("button", seat=1),
        act(2, "blind", 10, 1930),
        act(4, "blind", 20, 1980),
        {"t": "hole", "game": "holdem", "hand": 4, "cards": cards("Qh Qd"), "name": "Pair of Queens"},
        *pitches([2, 4, 5, 0, 1]),
        table_state(dealt, phase="playing", hand=4, round=4, button=1, street="preflop", turn=5, left=35),
        act(5, "all_in", 2130, 0),
        act(0, "all_in", 1940, 0),
        act(1, "fold", 0, 1990),
        act(2, "fold", 10, 1930),
        act(4, "fold", 20, 1980),
        act(5, "return", 1940, 190),
        event("show", hands=shown, pots=[3910]),
        *[event("runout", card=card(text)) for text in ("2c", "7d", "9h", "Ac", "3s")],
        event(
            "win",
            awards=[{"amount": 3910, "winners": [0, 5], "shares": {"0": 1955, "5": 1955}}],
            best={"0": best, "5": best},
            cut=0,
            big=True,
        ),
        event("unseat", seat=4),
    ]


def test_every_holdem_animation_finishes_within_its_pace(driver, live):
    open_casino(driver, live)
    driver.set_script_timeout(90)
    steps = a_hand_folded_on_the_turn() + an_all_in_split_after_a_run_out()
    report = driver.execute_async_script(SCENE_HARNESS + PLAY_ALL, str(ME), steps)
    assert "error" not in report, report.get("error")
    assert {kind for kind, took in report["timings"]} == set(HOLDEM_KINDS)
    for kind, took in report["timings"]:
        assert took <= PACE[kind] * 1000, f"{kind} took {took:.0f} ms of its {PACE[kind] * 1000:.0f}"
    # A sound for every action: the deal, chips, a check, a fold, an all in, the shuffle and the wins
    for sound in ("shuffle", "deal", "bet", "knock", "slide", "allin", "collect", "bigwin"):
        assert sound in report["played"], sound
    assert not problems(driver)


LAYOUTS = """
const [sizes, done] = arguments;
import(new URL("scenes/holdem.js", document.baseURI).href)
  .then((scene) => done(sizes.map(([width, height]) => scene.layoutFor(width, height))))
  .catch((e) => done({ error: String(e) }));
"""


def overlap(a, b):
    across = a["left"] < b["left"] + b["width"] and b["left"] < a["left"] + a["width"]
    return across and a["top"] < b["top"] + b["height"] and b["top"] < a["top"] + a["height"]


def inside(box, width, height):
    return (
        box["left"] >= 0
        and box["top"] >= 0
        and box["left"] + box["width"] <= width
        and box["top"] + box["height"] <= height
    )


def scene_size(driver):
    return driver.execute_script(
        "const host = document.getElementById('scene'); return [host.clientWidth, host.clientHeight]"
    )


def test_names_stay_at_least_10px_at_every_size(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    sizes = [(1280, 800), (390, 844), (844, 390)]
    # The scene's own space at each screen size, and a phone 100 pixels shorter
    for name, (width, height, scale, mobile) in SIZES.items():
        with at_size(driver, width, height, scale, mobile):
            resized(driver, width, height)
            sizes.append(tuple(scene_size(driver)))
            if name == "phone":
                phone = sizes[-1]
                sizes.append((sizes[-1][0], sizes[-1][1] - 100))
    # Upright screens of other shapes: a short phone, a tall one, a tablet
    sizes += [(360, 600), (430, 760), (768, 900)]
    layouts = driver.execute_async_script(LAYOUTS, sizes)
    # An upright phone gets the upright table, its shared cards about 55 pixels wide and the player's own bigger
    upright = layouts[sizes.index(phone)]
    assert upright["table"] == "upright" and upright["cardScale"] * 120 >= 50, upright["cardScale"]
    assert upright["hero"]["width"] >= 130, upright["hero"]
    assert "error" not in layouts, layouts
    for (width, height), layout in zip(sizes, layouts, strict=True):
        where = f"at {width}x{height}"
        seats = layout["seats"]
        assert len(seats) == 6, where
        assert all(seat["nameSize"] >= 10 for seat in seats), (where, [seat["nameSize"] for seat in seats])
        names = [seat["name"] for seat in seats]
        boxes = [seat["box"] for seat in seats]
        for one, box in enumerate(boxes):
            assert inside(names[one], width, height) and inside(box, width, height), (where, one, box)
            assert box["width"] >= names[one]["width"] >= seats[one]["nameWidth"] * 0.99, (where, one)
            # Nothing covers the shared cards or the player's own cards
            assert not overlap(box, layout["board"]), (where, one, "board")
            if one:
                assert not overlap(box, layout["hero"]), (where, one, "hero")
            for other in range(one + 1, 6):
                assert not overlap(box, boxes[other]), (where, one, other)
        assert inside(layout["board"], width, height) and inside(layout["hero"], width, height), where
        assert not overlap(layout["board"], layout["hero"]), where
        # Every seat keeps a margin from the scene's edges
        for box in [*boxes, layout["hero"]]:
            assert margin(box, width, height) >= 6, (where, box)
        bets_stay_clear(layout, width, height, where)
        marks_stay_apart(layout, where)
        note_stays_clear(layout, width, height, where)
    assert not problems(driver)


def note_stays_clear(layout, width, height, where):
    """The practice note on the felt stays on screen and clear of the seats, the shared cards, the player's own cards
    and every bet's chips and amount"""
    note, seats, hero = layout["note"], layout["seats"], layout["hero"]
    assert inside(note, width, height), (where, note)
    things = [seat["box"] for seat in seats] + hero["parts"] + [layout["board"]]
    for bet in [layout["pot"], hero["bet"], *(seat["bet"] for seat in seats)]:
        things += [bet["chips"], bet["words"]]
    assert not any(overlap(note, thing) for thing in things), (where, note)


def margin(box, width, height):
    """How far a box keeps from the nearest edge of a space this big"""
    right, bottom = box["left"] + box["width"], box["top"] + box["height"]
    return min(box["left"], box["top"], width - right, height - bottom)


def marks_stay_apart(layout, where):
    """The dealer button never covers a seat's tag (the last move, Away, Waiting) at its widest or the cards it shows
    at a showdown, and the player's own hand tag never covers their cards or the button"""
    for one, seat in enumerate(layout["seats"]):
        assert not overlap(seat["marks"]["button"], seat["marks"]["tag"]), (where, one)
        assert not overlap(seat["marks"]["button"], seat["marks"]["shown"]), (where, one)
    hero = layout["hero"]["marks"]
    assert not overlap(hero["hand"], hero["cards"]), (where, hero["hand"], hero["cards"])
    assert not overlap(hero["hand"], hero["button"]), where


def bets_stay_clear(layout, width, height, where):
    """Every bet's chips, its amount's room and its centered words stay on screen and clear of the seats, the shared
    cards, the pot and each other, for a watcher's six seats and for a player's own seat with the other five"""
    seats, pot, hero = layout["seats"], layout["pot"], layout["hero"]
    boxes = [seat["box"] for seat in seats]
    tables = {
        "watching": ([pot] + [seat["bet"] for seat in seats], boxes),
        "seated": ([pot] + [seat["bet"] for seat in seats[1:]] + [hero["bet"]], boxes[1:] + hero["parts"]),
    }
    # An amount's room fits a short amount ("12K", "999") at the names' size: 40 seat units, where 14 is the names'
    # font size
    least = 40 / 14 * seats[0]["nameSize"]
    for name, (bets, seat_boxes) in tables.items():
        for one, bet in enumerate(bets):
            spot = (where, name, one)
            assert bet["words"]["width"] >= least, (spot, bet["words"]["width"], least)
            for part in ("chips", "words", "zone"):
                assert inside(bet[part], width, height), (spot, part)
                assert not overlap(bet[part], layout["board"]), (spot, part, "board")
                assert not any(overlap(bet[part], box) for box in seat_boxes), (spot, part, "seat")
            for other in bets[one + 1 :]:
                for mine, theirs in (("chips", "chips"), ("chips", "words"), ("words", "chips"), ("words", "words")):
                    assert not overlap(bet[mine], other[theirs]), (spot, mine, theirs)
                assert not overlap(bet["zone"], other["zone"]), (spot, "zone")


RECONNECT = """
const [me, state, hole, changed, done] = arguments;
(async () => {
  const { app, root, scene } = await makeScene(900, 600, me);
  const walk = (node, found = []) => {
    found.push(node);
    node.children.forEach((child) => walk(child, found));
    return found;
  };
  const look = (node) => [node.x, node.y, node.alpha, node.visible, node.scale.x, node.rotation]
    .map((value) => (typeof value === "number" ? value.toFixed(2) : String(value))).join(",");
  let frames = 0;
  const realFrame = window.requestAnimationFrame;
  window.requestAnimationFrame = (step) => {
    frames += 1;
    return realFrame(step);
  };
  scene.show(state);
  scene.hole(hole);
  const drawn = walk(root);
  const looks = drawn.map(look);
  const framesAtOnce = frames;
  await new Promise((resolve) => setTimeout(resolve, 500));
  const moved = drawn.filter((node, index) => node.destroyed || look(node) !== looks[index]).length;
  const cards = drawn.filter((node) => node.back && node.face && node.visible);
  // How big a card is drawn: its scale times every container's above it
  const width = (node) => (node.parent ? Math.abs(node.scale.x) * width(node.parent) : 1);
  const hero = cards.filter((node) => node.face.visible && node.label === "hole");
  const backs = cards.filter((node) => node.back.visible);
  const ratio = hero.length && backs.length ? width(hero[0]) / width(backs[0]) : 0;
  scene.show(state);
  const again = walk(root);
  scene.show(changed);
  const after = walk(root);
  const texts = after.filter((node) => typeof node.text === "string").map((node) => node.text);
  window.requestAnimationFrame = realFrame;
  scene.destroy();
  app.destroy(true, { children: true });
  done({
    framesAtOnce,
    moved,
    cards: cards.length,
    faceUp: cards.filter((node) => node.face.visible).length,
    hero: hero.length,
    ratio,
    same: again.length === drawn.length && again.every((node, index) => node === drawn[index]),
    kept: after.length === drawn.length && after.every((node, index) => node === drawn[index]),
    texts,
  });
})().catch((e) => done({ error: String((e && e.stack) || e) }));
"""


def a_hand_on_the_flop():
    seats = [
        seat_row(0, "Member", 1940, me=True, in_hand=True, last={"move": "call", "amount": 60}),
        seat_row(1, "CPU Rosa", 1990, in_hand=True, folded=True, last={"move": "fold", "amount": 10}),
        seat_row(2, "CPU Dex", 1880, bet=60, in_hand=True, last={"move": "raise", "amount": 60}),
        None,
        seat_row(4, "CPU Mabel", 2000, in_hand=True, folded=True),
        seat_row(5, "CPU Juno", 1940, in_hand=True),
    ]
    board = cards("Ah 7c 2d")
    return table_state(seats, phase="playing", button=5, board=board, pots=[190], street="flop", turn=5, left=20.5)


def test_a_reconnect_redraws_the_table_without_animating(driver, live):
    open_casino(driver, live)
    state = a_hand_on_the_flop()
    hole = {"t": "hole", "game": "holdem", "hand": 3, "cards": cards("As Ks"), "name": "Pair of Aces"}
    changed = {**state, "seats": [*state["seats"]]}
    changed["seats"][5] = {**changed["seats"][5], "stack": 1234}
    report = driver.execute_async_script(SCENE_HARNESS + RECONNECT, str(ME), state, hole, changed)
    assert "error" not in report, report.get("error")
    # Drawn at once, and nothing moves afterwards
    assert report["framesAtOnce"] == 0 and report["moved"] == 0
    # The flop and the player's own two cards face up; two backs for each other player still in
    assert (report["cards"], report["faceUp"], report["hero"]) == (9, 5, 2)
    assert 1.4 <= report["ratio"] <= 1.8, report["ratio"]
    # Drawing the same table again rebuilds nothing, and a new stack only changes its words
    assert report["same"] and report["kept"]
    assert "1,234" in report["texts"]
    assert not problems(driver)


# Plays steps on a scene of its own and looks at it between them. A step is a table, a hole message or an event (one
# with "later" starts without waiting for it), or {"look": name}, {"wait": ms}, {"layout": [width, height]} or
# {"leave": true}. A look gathers, by owner ("seat-2", "bet-2", "pot", or "table"), the words showing, and every word's
# size on screen; the chips in each pile; the cards in the effects layer (on their way back to the deck); the dealt
# cards (by a number kept for each), how many each seat holds and which are face up; each stack's words and color;
# pictures with a mask; and where the dealer button is
# What every run step has to hand before its own script: a node's box on screen (drawn in by `inset` on each side),
# whether two boxes meet, a node's scale on screen, and the scene's pixels as drawn now, read at a point on screen
RUN_KIT = """
const box = (node, inset = 0) => {
  const b = node.getBounds();
  return { left: b.minX + inset, top: b.minY + inset, right: b.maxX - inset, bottom: b.maxY - inset };
};
const meet = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
const scaleOf = (node) => (node.parent ? Math.abs(node.scale.y) * scaleOf(node.parent) : 1);
const pixelsNow = () => {
  app.renderer.render(app.stage);
  const frame = new pixi.Rectangle(0, 0, app.screen.width, app.screen.height);
  const { pixels, width } = app.renderer.extract.pixels({ target: app.stage, frame });
  return (point) => {
    const at = (Math.round(point.y) * width + Math.round(point.x)) * 4;
    return [pixels[at], pixels[at + 1], pixels[at + 2], pixels[at + 3]];
  };
};
"""
STEPS = """
const [me, size, steps, kit, done] = arguments;
(async () => {
  const { app, root, scene } = await makeScene(size[0], size[1], me, size[2] !== false);
  const looks = {};
  const errors = [];
  const later = [];
  let ids = 0;
  let left = false;
  const walk = (node, visit, shown = true) => {
    const seen = shown && node.visible;
    visit(node, seen);
    node.children.forEach((child) => walk(child, visit, seen));
  };
  const within = (node, test) => {
    for (let at = node; at; at = at.parent) {
      if (test(at)) {
        return at;
      }
    }
    return null;
  };
  const isCard = (node) => Boolean(node.back && node.face);
  const isChip = (node) => typeof node.value === "number";
  const scaleOf = (node) => (node.parent ? Math.abs(node.scale.x) * scaleOf(node.parent) : 1);
  const box = (node) => {
    const bounds = node.getBounds();
    return { left: bounds.minX, top: bounds.minY, right: bounds.maxX, bottom: bounds.maxY };
  };
  const snapshot = () => {
    const look = { texts: {}, sizes: [], chips: {}, fxCards: 0, holes: [], faceUp: [], masks: 0, button: null };
    look.held = {};
    look.stacks = {};
    // Each pile's chips as [value, x, y] in the pile, by the bet or pot they belong to; the button's box, and each
    // seat's face-up cards' boxes
    look.piles = {};
    look.buttonBox = null;
    look.shownBoxes = {};
    const piles = new Map();
    const top = root.children[0];
    const fx = top.children[top.children.length - 1];
    walk(top, (node, seen) => {
      look.masks += node.mask ? 1 : 0;
      if (isCard(node) && within(node, (at) => at === fx)) {
        look.fxCards += 1;
      }
      const seat = within(node, (at) => /^seat-[0-9]$/.test(at.label || ""));
      if (isCard(node) && node.label === "hole" && seat) {
        look.held[seat.label] = (look.held[seat.label] || 0) + 1;
      }
      if (node.label === "stack" && seat && seen) {
        look.stacks[seat.label] = [node.text, node.style.fill];
      }
      if (isCard(node) && node.label === "hole") {
        node.testId = node.testId || ++ids;
        look.holes.push(node.testId);
        if (seen && node.face.visible && !node.back.visible) {
          look.faceUp.push(node.card);
        }
      }
      if (node.label === "button" && seen) {
        look.button = [node.x, node.y];
        look.buttonBox = box(node);
      }
      if (isCard(node) && node.label === "hole" && seat && seen && node.face.visible) {
        (look.shownBoxes[seat.label] = look.shownBoxes[seat.label] || []).push(box(node));
      }
      const owner = within(node, (at) => /^(seat|bet)-[0-9]$|^pot$/.test(at.label || ""));
      if (isChip(node) && owner) {
        look.chips[owner.label] = (look.chips[owner.label] || 0) + 1;
      }
      if (isChip(node) && owner && seen) {
        if (!piles.has(node.parent)) {
          piles.set(node.parent, []);
          (look.piles[owner.label] = look.piles[owner.label] || []).push(piles.get(node.parent));
        }
        piles.get(node.parent).push([node.value, node.x, node.y]);
      }
      if (typeof node.text === "string" && node.text && seen) {
        const key = owner ? owner.label : "table";
        (look.texts[key] = look.texts[key] || []).push(node.text);
        if (!within(node, (at) => isCard(at) || isChip(at))) {
          look.sizes.push([node.text, node.style.fontSize * scaleOf(node)]);
        }
      }
    });
    return look;
  };
  for (const step of steps) {
    try {
      if (step.look) {
        looks[step.look] = snapshot();
      } else if (step.wait) {
        await new Promise((resolve) => setTimeout(resolve, step.wait));
      } else if (step.layout) {
        scene.layout(...step.layout);
      } else if (step.run) {
        // A bit of script with the scene, the app, the scene's root and RUN_KIT to hand; what it returns is kept by
        // its name
        const pixi = await import(new URL("vendor/pixi.min.mjs", document.baseURI).href);
        const run = new Function("scene", "app", "root", "pixi", `${kit}\nreturn (async () => { ${step.js} })();`);
        looks[step.run] = await run(scene.table, app, root, pixi);
      } else if (step.cover) {
        // Points on an 11 by 11 grid over the scene (or the part of it `frame` gives) that nothing opaque is drawn on
        const pixi = await import(new URL("vendor/pixi.min.mjs", document.baseURI).href);
        const [wide, high] = step.frame || size;
        const frame = new pixi.Rectangle(0, 0, size[0], size[1]);
        const { pixels, width } = app.renderer.extract.pixels({ target: app.stage, frame });
        const bare = [];
        for (let row = 0; row <= 10; row += 1) {
          for (let column = 0; column <= 10; column += 1) {
            const x = Math.round((column / 10) * (wide - 1));
            const y = Math.round((row / 10) * (high - 1));
            if (pixels[(y * width + x) * 4 + 3] < 250) {
              bare.push([x, y]);
            }
          }
        }
        looks[step.cover] = bare;
      } else if (step.leave) {
        scene.destroy();
        app.destroy(true, { children: true });
        left = true;
      } else if (step.t === "table") {
        scene.show(step);
      } else if (step.t === "hole") {
        scene.hole(step);
      } else if (step.later) {
        later.push(scene.play(step));
      } else {
        await scene.play(step);
      }
    } catch (e) {
      errors.push(String((e && e.stack) || e));
    }
  }
  await Promise.all(later);
  if (!left) {
    scene.destroy();
    app.destroy(true, { children: true });
  }
  done({ looks, errors });
})().catch((e) => done({ looks: {}, errors: [String((e && e.stack) || e)] }));
"""


def run_steps(driver, steps, size=(900, 600), me=str(ME)):
    driver.set_script_timeout(60)
    report = driver.execute_async_script(SCENE_HARNESS + STEPS, me, list(size), steps, RUN_KIT)
    assert not report["errors"], report["errors"]
    return report["looks"]


def look(name):
    return {"look": name}


def later(message):
    return {**message, "later": True}


def a_deal_in_the_bots_order(hand=3):
    """How the bot starts a hand: the table still on the last hand, the button, the blinds, the player's own cards
    (numbered with the new hand), the cards flying out, then the new hand's first table at the first turn"""
    seats = [
        seat_row(0, "Member", 2000, me=True),
        seat_row(1, "CPU Rosa", 2000),
        seat_row(2, "CPU Dex", 2000),
        None,
        seat_row(4, "CPU Mabel", 2000),
        seat_row(5, "CPU Juno", 2000),
    ]
    dealt = [row and {**row, "in_hand": True, "cards": 2} for row in seats]
    dealt[1] = {**dealt[1], "stack": 1990, "bet": 10, "last": {"move": "blind", "amount": 10}}
    dealt[2] = {**dealt[2], "stack": 1980, "bet": 20, "last": {"move": "blind", "amount": 20}}
    return [
        table_state(seats, hand=hand - 1, button=5),
        event("button", seat=0),
        act(1, "blind", 10, 1990),
        act(2, "blind", 20, 1980),
        {"t": "hole", "game": "holdem", "hand": hand, "cards": cards("Ks Kd"), "name": "Pair of Kings"},
        *pitches([1, 2, 4, 5, 0]),
        table_state(dealt, phase="playing", hand=hand, button=0, street="preflop", turn=4, left=35),
    ]


def test_a_deal_in_the_bots_order_keeps_every_card_and_turns_mine_up(driver, live):
    open_casino(driver, live)
    *deal, first = a_deal_in_the_bots_order()
    looks = run_steps(driver, [*deal, look("dealt"), first, look("table"), {"wait": 400}, look("settled")])
    dealt, table, settled = looks["dealt"], looks["table"], looks["settled"]
    # Nothing goes back to the deck when the new hand's first table arrives: the dealt cards stay where they landed
    assert dealt["fxCards"] == table["fxCards"] == 0
    assert len(dealt["holes"]) == 10 and settled["holes"] == dealt["holes"]
    # The player's own cards turned face up as they landed, under their name and with their hand in words
    assert settled["faceUp"] == cards("Ks Kd")
    assert {"Member", "Pair of Kings"} <= set(settled["texts"]["seat-0"])
    assert not problems(driver)


def test_the_dealer_button_glides_to_its_next_seat(driver, live):
    open_casino(driver, live)
    deal = a_deal_in_the_bots_order()
    steps = [deal[0], look("before"), later(deal[1]), {"wait": 170}, look("middle"), {"wait": 400}, look("after")]
    looks = run_steps(driver, steps)
    start, middle, end = (looks[name]["button"] for name in ("before", "middle", "after"))
    assert start and middle and end and math.dist(start, end) > 100
    # Partway through, it is between the two seats, well away from both
    assert math.dist(start, middle) > 20 and math.dist(middle, end) > 20, (start, middle, end)
    assert math.dist(start, middle) + math.dist(middle, end) < math.dist(start, end) * 1.3
    assert not problems(driver)


def a_hand_to_the_showdown():
    """The flop on a table of five: a bet, a raise, a fold, calls; then the turn checked through, and the showdown and
    the win at the river. Each look is named after the move it follows"""
    seats = [
        seat_row(0, "Member", 1940, me=True, in_hand=True),
        seat_row(1, "CPU Rosa", 1940, in_hand=True),
        seat_row(2, "CPU Dex", 1940, in_hand=True),
        None,
        seat_row(4, "CPU Mabel", 1940, in_hand=True),
        seat_row(5, "CPU Juno", 1940, in_hand=True),
    ]
    shown = {
        "0": {"cards": cards("As Ks"), "name": "Pair of Aces"},
        "1": {"cards": cards("Qd Qc"), "name": "Pair of Queens"},
        "2": {"cards": cards("7h 7d"), "name": "Three of a kind, 7s"},
        "5": {"cards": cards("Jc 10c"), "name": "High card, Ace"},
    }
    win = {"amount": 1020, "winners": [2], "shares": {"2": 1020}}
    return [
        {"t": "hole", "game": "holdem", "hand": 3, "cards": cards("As Ks"), "name": "Pair of Aces"},
        table_state(seats, phase="playing", button=0, board=cards("Ah 7c 2d"), pots=[300], street="flop", turn=1),
        act(1, "raise", 60, 1880),
        look("bet"),
        act(2, "raise", 180, 1760),
        look("raise"),
        act(4, "fold", 0, 1940),
        look("fold"),
        act(5, "call", 180, 1760),
        act(0, "call", 180, 1760),
        act(1, "call", 180, 1760),
        look("call"),
        event("sweep", pots=[1020]),
        event("street", card=card("9s")),
        look("turn"),
        act(1, "check", 0, 1760),
        look("check"),
        act(2, "check", 0, 1760),
        act(5, "check", 0, 1760),
        act(0, "check", 0, 1760),
        event("street", card=card("3c")),
        event("show", hands=shown, pots=[1020]),
        look("showdown"),
        event("win", awards=[win], best={"2": cards("7h 7d 7c As Ks")}, cut=0, big=False),
        look("won"),
    ]


def test_each_move_names_itself_and_every_name_stays(driver, live):
    open_casino(driver, live)
    looks = run_steps(driver, a_hand_to_the_showdown())

    def says(name, seat, *words):
        texts = looks[name]["texts"].get(f"seat-{seat}", [])
        assert all(word in texts for word in words), (name, seat, texts)

    # The first chips of a round are a bet; every later move says its own word, beside the seat's name
    says("bet", 1, "CPU Rosa", "Bet 60")
    says("raise", 2, "CPU Dex", "Raise 180")
    says("fold", 4, "CPU Mabel", "Fold")
    says("call", 1, "CPU Rosa", "Call 180")
    assert "Bet 180" not in looks["call"]["texts"]["seat-1"]
    # A new round clears the tags, and the same seat's check says Check
    assert not set(looks["turn"]["texts"]["seat-1"]) & {"Call 180", "Bet 60"}
    says("check", 1, "CPU Rosa", "Check")
    # At the showdown and the win each shown seat keeps its name beside its hand's name: smaller to fit, then in
    # poker's own short words, never losing the rank
    named = {
        1: {"Pair of Queens", "Pair of Qs"},
        2: {"Three of a kind, 7s", "Trips 7s"},
        5: {"High card, Ace", "A high"},
    }
    for name in ("showdown", "won"):
        says(name, 0, "Member", "Pair of Aces")
        for seat, ways in named.items():
            texts = set(looks[name]["texts"][f"seat-{seat}"])
            assert texts & ways, (name, seat, texts)
    assert "Won 1,020" in looks["won"]["texts"]["bet-2"]
    # The same on a phone held either way, where the plates are narrowest
    steps = a_hand_to_the_showdown()
    showdown = steps.index(look("showdown"))
    for size in ((390, 560), (564, 334)):
        shown = run_steps(driver, [*steps[:showdown], {"wait": 300}, look("shown")], size=size)["shown"]
        for seat, ways in named.items():
            texts = set(shown["texts"][f"seat-{seat}"])
            assert texts & ways, (size, seat, texts)
    assert not problems(driver)


def test_leaving_mid_showdown_or_mid_win_leaves_no_errors(driver, live):
    open_casino(driver, live)
    steps = a_hand_to_the_showdown()
    showdown = steps.index(look("showdown")) - 1
    won = steps.index(look("won")) - 1
    run_steps(driver, [*steps[:showdown], later(steps[showdown]), {"wait": 250}, {"leave": True}, {"wait": 1200}])
    run_steps(driver, [*steps[:won], later(steps[won]), {"wait": 700}, {"leave": True}, {"wait": 2000}])
    assert not problems(driver)


def test_a_table_before_the_first_layout_is_drawn_at_it(driver, live):
    open_casino(driver, live)
    looks = run_steps(driver, [a_hand_on_the_flop(), {"layout": [900, 600]}, look("drawn")], size=(900, 600, False))
    assert {"CPU Dex", "1,880"} <= set(looks["drawn"]["texts"]["seat-2"])
    assert not problems(driver)


# A one-pixel picture, so players' faces load without the network
PICTURE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_a_phone_keeps_amounts_whole_piles_by_size_and_words_readable(driver, live):
    open_casino(driver, live)
    people = {"cpu": False, "avatar": PICTURE}
    seats = [
        {**seat_row(0, "Member", 1940, me=True, in_hand=True), "avatar": PICTURE},
        seat_row(1, "CPU Rosa", 1850, bet=150, in_hand=True, last={"move": "raise", "amount": 150}),
        seat_row(2, "CPU Dex", 5000, bet=5000, in_hand=True, last={"move": "raise", "amount": 5000}),
        {**seat_row(3, "Late Larry", 2000), **people, "id": "303", "waiting": True},
        {**seat_row(4, "Away Ann", 1801, bet=199, in_hand=True), **people, "id": "404", "away": True},
        seat_row(5, "CPU Juno", 7655, bet=12345, in_hand=True, last={"move": "call", "amount": 12345}),
    ]
    watchers = [{"id": str(500 + n), "name": f"Watcher {n}", "avatar": PICTURE, "away": n == 1} for n in range(8)]
    players = [{"id": str(ME), "name": "Member", "avatar": PICTURE, "away": False}, *watchers]
    state = table_state(seats, phase="playing", button=5, pots=[123456], street="flop", turn=0, players=players)
    phone = run_steps(driver, [state, {"wait": 400}, look("phone")], size=(390, 476))["phone"]
    # A pot and a bet keep every digit, with thousands separators
    texts = phone["texts"]
    assert "123,456" in texts["pot"] and "12,345" in texts["bet-5"], (texts["pot"][-2:], texts["bet-5"][-2:])
    # Each pile is the fewest chips that make its amount: 5,000 is one chip, and 199's ten chips lose only their
    # smallest past the two full columns
    piles = phone["piles"]
    assert values(piles["bet-2"]) == [5000] and values(piles["bet-1"]) == fewest(150)
    assert values(piles["bet-4"]) == fewest(199)[: len(values(piles["bet-4"]))] and len(values(piles["bet-4"])) >= 6
    # Every word is at least 10 pixels on screen: names, amounts, tags, badges and the watchers' "+N". A face's single
    # letter stands in for a picture, so it doesn't count as words
    small = [(words, size) for words, size in phone["sizes"] if size < 10 and len(words) > 1]
    assert not small, small
    assert "+3" in phone["texts"]["table"]
    assert {"Late Larry", "Waiting"} <= set(phone["texts"]["seat-3"])
    assert {"Away Ann", "Away"} <= set(phone["texts"]["seat-4"])
    # Players' pictures are cut round once, with no mask redrawn every frame
    assert phone["masks"] == 0
    assert not problems(driver)


def test_the_countdown_and_the_ticks_go_once_betting_ends_on_screen(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    on_loop(live, conn.send(a_hand_on_the_flop()))
    browser.wait_for(driver, "!document.getElementById('hd-ticks').hidden")
    # The player's turn: the dock counts it down
    send_all(live, conn, my_turn())
    browser.wait_for(driver, "document.getElementById('clock').textContent.endsWith('s')")
    # The player moves: the countdown is over, and stays gone through the showdown and the win
    on_loop(live, conn.send(act(0, "check", 0, 1940)))
    browser.wait_for(driver, "document.getElementById('clock').textContent === ''")
    # The bot sends no table between the last move and the end of the hand: the showdown itself ends the ticks
    shown = {"0": {"cards": cards("As Ks"), "name": "Pair of Aces"}, "2": {"cards": cards("Qd Qc"), "name": "Pair"}}
    on_loop(live, conn.send(event("show", hands=shown, pots=[250])))
    time.sleep(1.2)
    assert text(driver, "clock") == "" and not ticks_shown(driver)
    assert not problems(driver)


def test_someone_arriving_mid_deal_leaves_every_seat_two_cards(driver, live):
    open_casino(driver, live)
    *deal, first = a_deal_in_the_bots_order()
    pitched = deal.index(event("pitch", seat=1)) + 3
    # Someone opening the table mid-deal makes the bot send the table: every dealt seat already holds 2 cards
    arrived = {**first, "turn": None, "left": None}
    steps = [*deal[:pitched], arrived, *deal[pitched:], {"wait": 300}, look("dealt"), first, look("table")]
    looks = run_steps(driver, steps)
    # Before the next table comes, the rest of the deal lands on the cards already showing, adding none
    for name in ("dealt", "table"):
        assert looks[name]["held"] == {f"seat-{n}": 2 for n in (0, 1, 2, 4, 5)}, (name, looks[name]["held"])
    assert looks["dealt"]["fxCards"] == 0 and looks["dealt"]["faceUp"] == cards("Ks Kd")
    assert not problems(driver)


def test_an_all_in_winner_counts_up_in_gold(driver, live):
    open_casino(driver, live)
    seats = [
        seat_row(0, "Member", 1940, me=True, in_hand=True, folded=True),
        seat_row(1, "CPU Rosa", 0, in_hand=True, all_in=True, last={"move": "all_in", "amount": 500}),
        seat_row(2, "CPU Dex", 1500, in_hand=True, folded=True),
    ] + [None] * 3
    state = table_state(seats, phase="playing", button=0, board=cards("Ah 7c 2d 9s 3c"), pots=[1000], street="river")
    win = event("win", awards=[{"amount": 1000, "winners": [1], "shares": {"1": 1000}}], best={}, cut=0, big=False)
    looks = run_steps(driver, [state, look("before"), later(win), {"wait": 600}, look("counting"), {"wait": 1500}])
    assert looks["before"]["stacks"]["seat-1"][0] == "All in"
    # The win's chips land and the stack counts up in the stack's own gold, not the all in red
    assert looks["counting"]["stacks"]["seat-1"][1] == 0xF3D77A, looks["counting"]["stacks"]
    assert not problems(driver)


RANK_NAMES = [
    "Royal flush",
    "Straight flush",
    "Four of a kind",
    "Full house",
    "Flush",
    "Straight",
    "Three of a kind",
    "Two pair",
    "Pair",
    "High card",
]
# What each row of the chart shows, read off the page: its name, then its five cards
CHART = """
return [...document.querySelectorAll('#panel-body .rank-chart li')].map((row) => ({
  name: row.querySelector('.rank-name').textContent,
  cards: [...row.querySelectorAll('.mini-card')].map((card) => ({
    text: card.textContent,
    red: getComputedStyle(card).color === 'rgb(192, 24, 40)',
    size: parseFloat(getComputedStyle(card).fontSize),
  })),
}));
"""


def open_rules(driver):
    driver.find_element(By.ID, "open-rules").click()
    browser.wait_for(driver, "document.querySelectorAll('#panel-body .rank-chart li').length > 0")


def test_house_rules_explain_holdem_with_a_rankings_chart(driver, live):
    open_casino(driver, live)
    open_rules(driver)
    rows = driver.execute_script(CHART)
    assert [row["name"] for row in rows] == RANK_NAMES
    # The Royal flush row reads as the best straight flush, not a hand of its own
    about = driver.execute_script("return document.querySelector('#panel-body .rank-chart .rank-about').textContent")
    assert "straight flush" in about.lower(), about
    royal = rows[0]["cards"]
    assert [card["text"] for card in royal] == ["A♠", "K♠", "Q♠", "J♠", "10♠"]
    assert [card["red"] for card in rows[1]["cards"]] == [True] * 5
    assert all(len(row["cards"]) == 5 for row in rows)
    body = driver.find_element(By.ID, "panel-body").text
    assert "Buy-in 400 to 2,000 · Blinds 10/20 · Cut 5%" in body
    assert "5% of each pot that reaches the flop" in body
    for name, (width, height, scale, mobile) in SIZES.items():
        with at_size(driver, width, height, scale, mobile):
            resized(driver, width, height)
            assert driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth"), name
            sheet = driver.execute_script(
                "const list = document.querySelector('#panel-body .rank-chart');"
                "return {sideways: list.scrollWidth > list.clientWidth, sizes: [...list.querySelectorAll('.mini-card')]"
                ".map((card) => card.getBoundingClientRect().width)}"
            )
            assert not sheet["sideways"], name
            assert min(sheet["sizes"]) >= 22, (name, sheet["sizes"])
    assert not problems(driver)


def test_an_admin_changes_the_cut_and_sees_it_in_the_house_rules(driver, live):
    live.user_id = fakes.MANAGER_ID
    open_casino(driver, live)
    driver.find_element(By.ID, "open-settings").click()
    browser.wait_for(driver, "document.querySelectorAll('#panel-tabs button').length === 5")
    driver.find_element(By.XPATH, "//nav[@id='panel-tabs']/button[text()='Games']").click()
    row = driver.find_element(By.XPATH, "//table[contains(@class,'grid')]//tr[td[text()=\"Texas Hold'em\"]]")
    cells = row.find_elements(By.TAG_NAME, "td")
    assert cells[3].text == "-"
    cut = row.find_element(By.CSS_SELECTOR, "input.cut")
    assert (cut.get_attribute("min"), cut.get_attribute("max"), cut.get_attribute("step")) == ("0", "20", "0.5")
    assert "% cut" in cells[6].text
    assert "its Payout box is the casino's cut of each pot" in driver.find_element(By.ID, "panel-body").text
    cut.clear()
    cut.send_keys("7.5")
    row.find_element(By.XPATH, ".//button[text()='Save']").click()
    browser.wait_for(driver, "document.getElementById('toast').textContent === 'Saved.'")
    game = on_loop(live, live.cog.store.game(fakes.GUILD_ID, "holdem"))
    assert game.cut == 7.5 and game.cooldown == 0 and game.multiplier is None
    driver.find_element(By.ID, "panel-close").click()
    open_rules(driver)
    body = driver.find_element(By.ID, "panel-body").text
    assert "Cut 7.5%" in body and "7.5% of each pot that reaches the flop" in body
    assert not problems(driver)


DENOMINATIONS = [100000, 50000, 10000, 5000, 1000, 500, 100, 25, 10, 5, 1]


def fewest(amount):
    """The fewest chips that make amount, largest first"""
    chips = []
    for value in DENOMINATIONS:
        count, amount = divmod(amount, value)
        chips += [value] * count
    return chips


def values(piles):
    """Every chip's value in some piles, largest first"""
    return sorted((value for pile in piles for value, x, y in pile), reverse=True)


def columns(pile):
    """A pile's columns, each bottom to top, read off where its chips stand"""
    standing = {}
    for value, x, y in pile:
        standing.setdefault(round(x / 58), []).append((y, value))
    return [[value for y, value in sorted(column, reverse=True)] for column in standing.values()]


def test_chip_piles_are_the_fewest_chips_with_the_biggest_on_top(driver, live):
    open_casino(driver, live)
    seats = [
        seat_row(0, "Member", 1940, me=True, in_hand=True, bet=20),
        seat_row(1, "CPU Rosa", 1900, in_hand=True, bet=80),
        seat_row(2, "CPU Dex", 1360, in_hand=True, bet=640),
        None,
        seat_row(4, "CPU Mabel", 1392, in_hand=True, bet=608),
        None,
    ]
    state = table_state(seats, phase="playing", button=0, board=cards("Ah 7c 2d"), pots=[608], street="flop", turn=1)
    piles = run_steps(driver, [state, {"wait": 300}, look("table")])["table"]["piles"]
    for owner, amount in {"bet-0": 20, "bet-1": 80, "bet-2": 640, "bet-4": 608, "pot": 608}.items():
        # Every chip of the amount, and no more: a 20 blind is two 10s, 80 is three 25s and a 5
        assert values(piles[owner]) == fewest(amount), (owner, values(piles[owner]))
        # Each column has its biggest chip on top
        for column in columns(piles[owner][0]):
            assert column[-1] == max(column), (owner, column)
    # On a desktop each chip sits clearly above the one under it, so a pile of two reads as two chips
    rises = [
        below - above
        for pile in piles.values()
        for column in rises_of(pile[0])
        for below, above in zip(column, column[1:], strict=False)
    ]
    assert sum(rises) / len(rises) >= 6.5, rises
    # Where the table has room for tall piles (a desktop, an upright phone), every pile's second chip stands further
    # above the first, so two chips never read as one thick chip
    for size in ((900, 600), (960, 744), (390, 634)):
        piles = run_steps(driver, [state, {"wait": 300}, look("table")], size=size)["table"]["piles"]
        firsts = [column[0] - column[1] for pile in piles.values() for column in rises_of(pile[0]) if len(column) > 1]
        assert sum(firsts) / len(firsts) >= 9, (size, firsts)
    assert not problems(driver)


def rises_of(pile):
    """Each column of a pile as its chips' heights, bottom to top"""
    standing = {}
    for value, x, y in pile:
        standing.setdefault(round(x / 58), []).append(y)
    return [sorted(column, reverse=True) for column in standing.values()]


def test_the_wallpaper_covers_the_whole_scene_at_every_size(driver, live):
    open_casino(driver, live)
    for size in ((390, 760), (1400, 420), (900, 600), (564, 334), (768, 1000)):
        looks = run_steps(driver, [a_hand_on_the_flop(), {"wait": 100}, {"cover": "bare"}], size=size)
        assert looks["bare"] == [], (size, looks["bare"])
    assert not problems(driver)


def test_the_dealer_button_never_covers_shown_cards(driver, live):
    open_casino(driver, live)
    steps = a_hand_to_the_showdown()
    # The button on a CPU that shows its cards
    steps[1] = {**steps[1], "button": 2}
    showdown = steps.index(look("showdown"))
    for size in ((900, 600), (390, 560), (564, 334)):
        shown = run_steps(driver, [*steps[:showdown], {"wait": 900}, look("shown")], size=size)["shown"]
        button = shown["buttonBox"]
        assert button and set(shown["shownBoxes"]) >= {"seat-1", "seat-2", "seat-5"}, shown["shownBoxes"]
        for seat, boxes in shown["shownBoxes"].items():
            for card_box in boxes:
                apart = (
                    button["right"] <= card_box["left"]
                    or card_box["right"] <= button["left"]
                    or button["bottom"] <= card_box["top"]
                    or card_box["bottom"] <= button["top"]
                )
                assert apart, (size, seat, button, card_box)
    assert not problems(driver)


def test_tags_say_what_happened_and_leave_with_their_seat(driver, live):
    open_casino(driver, live)
    steps = a_hand_folded_on_the_turn()
    returned = steps.index(act(5, "return", 0, 1940)) + 1
    gone = [row and row["seat"] != 5 and row for row in steps[0]["seats"]]
    steps = [
        *steps[:returned],
        look("returned"),
        *steps[returned:],
        {"wait": 300},
        look("won"),
        event("unseat", seat=5),
        {"wait": 300},
        look("left"),
        table_state(gone, hand=3),
        {"wait": 300},
        look("after"),
    ]
    looks = run_steps(driver, steps)
    # An uncalled bet coming back says how much, in plain words
    assert "Got 120 back" in looks["returned"]["texts"]["seat-5"], looks["returned"]["texts"]["seat-5"]
    assert "Won 190" in looks["won"]["texts"]["bet-5"]
    # The CPU leaves with its win: its words never come back on the empty seat
    for name in ("left", "after"):
        assert not looks[name]["texts"].get("bet-5"), (name, looks[name]["texts"].get("bet-5"))
    assert not problems(driver)


def test_practice_says_play_chips_and_a_newcomer_joins_next_hand(driver, live):
    open_casino(driver, live)
    newcomer = {**seat_row(3, "Late Larry", 2000), "cpu": False, "id": "303"}
    seats = [
        seat_row(0, "Member", 1940, me=True, in_hand=True),
        seat_row(1, "CPU Rosa", 1940, in_hand=True),
        None,
        newcomer,
        None,
        None,
    ]
    practice = table_state(seats, phase="playing", button=0, pots=[120], street="flop", board=cards("Ah 7c 2d"))
    real = table_state([*seats[:3], {**newcomer, "in_hand": True}, None, None], mode="real", phase="playing")
    looks = run_steps(driver, [practice, {"wait": 300}, look("practice"), real, {"wait": 300}, look("real")])
    # Practice chips say so on the felt, and the newcomer's real buy-in reads as joining next hand
    assert set(looks["practice"]["texts"]["table"]) & {"Practice · play chips", "Practice"}
    assert "Next hand" in looks["practice"]["texts"]["seat-3"] and "2,000" not in looks["practice"]["texts"]["seat-3"]
    assert not set(looks["real"]["texts"].get("table", [])) & {"Practice · play chips", "Practice"}
    assert "2,000" in looks["real"]["texts"]["seat-3"]
    assert not problems(driver)


def test_the_dock_counts_the_player_in_from_the_deal_and_says_their_own_moves(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    seats = [seat_row(0, "Member", 1500, me=True), seat_row(1, "CPU Rosa", 2000), seat_row(2, "CPU Dex", 2000)]
    on_loop(live, conn.send(table_state([*seats, None, None, None], mode="real", hand=2)))
    browser.wait_for(driver, "!document.getElementById('hd-top-up').hidden")
    assert text(driver, "status-text") == "Next hand in a moment."
    # The next hand starts: from its first event there is no topping up until it ends
    on_loop(live, conn.send(event("button", seat=1)))
    browser.wait_for(driver, "document.getElementById('hd-top-up').hidden")
    # The player posts the big blind and gets their cards: the dock says so before the new hand's table comes, and
    # names their hand only once both cards have landed
    for message in (
        act(2, "blind", 10, 1990),
        act(0, "blind", 20, 1480),
        {"t": "hole", "game": "holdem", "hand": 3, "cards": cards("Ks Kd"), "name": "Pair of Kings"},
    ):
        on_loop(live, conn.send(message))
    browser.wait_for(driver, "document.getElementById('status-text').textContent === 'You posted the big blind 20'")
    time.sleep(0.3)
    assert text(driver, "status-text") == "You posted the big blind 20"
    for message in pitches([2, 0, 1]):
        on_loop(live, conn.send(message))
    said_so = "You posted the big blind 20 · Pair of Kings"
    browser.wait_for(driver, f"document.getElementById('status-text').textContent === '{said_so}'")
    assert not driver.find_element(By.ID, "hd-top-up").is_displayed()
    assert not driver.find_element(By.ID, "hd-note").is_displayed()
    # Another seat calls the big blind and the player raises: the dock follows the bets as the table plays them, so
    # this is a raise even though the last table it had showed no bets
    on_loop(live, conn.send(act(1, "call", 20, 1980)))
    on_loop(live, conn.send(act(0, "raise", 60, 1440)))
    raised = "You raised to 60 · Pair of Kings"
    browser.wait_for(driver, f"document.getElementById('status-text').textContent === '{raised}'")
    assert not problems(driver)


def test_the_dock_keeps_the_blind_through_the_first_table_and_says_what_came_back(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    seats = [seat_row(0, "Member", 1500, me=True), seat_row(1, "CPU Rosa", 2000), None, None, None, None]
    on_loop(live, conn.send(table_state(seats, mode="real", hand=2)))
    browser.wait_for(driver, "document.getElementById('status-text').textContent === 'Next hand in a moment.'")
    dealt = [
        seat_row(0, "Member", 1480, me=True, in_hand=True, bet=20, last={"move": "blind", "amount": 20}),
        seat_row(1, "CPU Rosa", 1990, in_hand=True, bet=10, last={"move": "blind", "amount": 10}),
        None,
        None,
        None,
        None,
    ]
    for message in (
        event("button", seat=1),
        act(1, "blind", 10, 1990),
        act(0, "blind", 20, 1480),
        {"t": "hole", "game": "holdem", "hand": 3, "cards": cards("Ks Kd"), "name": "Pair of Kings"},
        *pitches([1, 0]),
        table_state(dealt, mode="real", phase="playing", hand=3, button=1, street="preflop", turn=1, left=30),
    ):
        on_loop(live, conn.send(message))
    # The hand's first table only confirms the deal: the blind the player posted still shows
    posted = "You posted the big blind 20 · Pair of Kings"
    browser.wait_for(driver, f"document.getElementById('status-text').textContent === '{posted}'")
    time.sleep(0.3)
    assert text(driver, "status-text") == posted
    # The small blind folds, so half the big blind comes back to the player
    on_loop(live, conn.send(act(1, "fold", 10, 1990)))
    on_loop(live, conn.send(act(0, "return", 10, 1490)))
    back = "You got 10 back · Pair of Kings"
    browser.wait_for(driver, f"document.getElementById('status-text').textContent === '{back}'")
    assert not problems(driver)


def test_fold_stays_greyed_in_its_place_when_a_check_is_free(driver, live):
    open_casino(driver, live)
    table, events = quick_table(live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    on_loop(live, conn.send(a_hand_on_the_flop()))
    # A practice table says its chips are play chips
    browser.wait_for(driver, "!document.getElementById('hd-note').hidden")
    assert text(driver, "hd-note") == "Practice · play chips"
    # The ticks keep their words on one line, on a desktop and on a sideways phone
    browser.wait_for(driver, "!document.getElementById('hd-ticks').hidden")
    check_fold = '#hd-ticks [data-advance="check_fold"]'
    assert driver.execute_script(LINES, check_fold) == {"lines": 1, "fits": True}
    with at_size(driver, 844, 390, 2, True):
        resized(driver, 844, 390)
        assert driver.execute_script(LINES, check_fold) == {"lines": 1, "fits": True}
    on_loop(live, conn.send({**a_hand_on_the_flop(), "turn": 0}))
    ask = {"t": "ask", "game": "holdem", "moves": ["fold", "call", "raise"], "call": 60, "min_to": 120}
    ask.update(max_to=1940, pot=190, bet=0)
    on_loop(live, conn.send(ask))
    WebDriverWait(driver, 5).until(lambda _: bar_up(driver))
    where = driver.find_element(By.ID, "hd-fold").rect
    # A check is free: Fold stays where it was, greyed, and pressing it sends nothing
    on_loop(live, conn.send({**ask, "moves": ["check", "raise"], "call": 0}))
    browser.wait_for(driver, "document.getElementById('hd-fold').disabled")
    fold = driver.find_element(By.ID, "hd-fold")
    assert fold.is_displayed() and fold.rect == where
    ActionChains(driver).move_to_element(fold).click().perform()
    driver.execute_script("document.getElementById('hd-fold').click()")
    time.sleep(0.3)
    assert said(events, "move") == [] and bar_up(driver)
    # The player's time runs out and the table checks for them: the bar goes before the next table comes
    on_loop(live, conn.send(act(0, "check", 0, 1940)))
    WebDriverWait(driver, 5).until(lambda _: not bar_up(driver))
    assert text(driver, "status-text").startswith("You checked")
    assert not problems(driver)


# ---------- The table: motion, marks and the win ----------

TWEEN_EARLY = """
const done = arguments[arguments.length - 1];
import(new URL("scenes/kit.js", document.baseURI).href).then(async ({ ease, tween }) => {
  const target = { k: 0 };
  const shares = [];
  const realFrame = window.requestAnimationFrame;
  let first = true;
  // The first frame's time comes a little before the tween started, as a real frame's can
  window.requestAnimationFrame = (step) => realFrame((now) => {
    const at = first ? now - 40 : now;
    first = false;
    step(at);
    shares.push(target.k);
  });
  try {
    await tween(target, { k: 1 }, 120, ease.out);
  } finally {
    window.requestAnimationFrame = realFrame;
  }
  done(shares);
}).catch((e) => done({ error: String(e) }));
"""


def test_a_tween_never_moves_back_past_its_start(driver, live):
    open_casino(driver, live)
    shares = driver.execute_async_script(TWEEN_EARLY)
    assert "error" not in shares, shares
    # A share below 0 made a grey one step past white, which Pixi refuses, and the card it dimmed stayed bright
    assert min(shares) >= 0 and shares[-1] == 1, shares


# How many points around a seat's face, on its turn ring, show the ring's warning red
RED_RING = """
const seat = scene.seats[arguments_seat];
scene.everyFrame();
const pixel = pixelsNow();
let red = 0;
for (let angle = 0; angle < 360; angle += 3) {
  const turn = (angle * Math.PI) / 180;
  const [r, g, b] = pixel(seat.ring.toGlobal({ x: Math.cos(turn) * 34.5, y: Math.sin(turn) * 34.5 }));
  if (r > 200 && g < 120 && b < 120) {
    red += 1;
  }
}
return red;
"""


def test_the_turn_rings_last_seconds_stay_in_view_on_a_top_seat(driver, live):
    open_casino(driver, live)
    # CPU Dex's turn with 4 seconds left: the top left seat, whose plate hangs over its face
    state = {**a_hand_on_the_flop(), "turn": 2, "left": 4}
    for size in ((900, 600), (390, 700)):
        js = RED_RING.replace("arguments_seat", "2")
        red = run_steps(driver, [state, {"wait": 50}, {"run": "red", "js": js}], size=size)["red"]
        assert red >= 6, (size, red)
    assert not problems(driver)


# Across the turn ring at the middle of its colored arc, from inside to outside, what the ring itself draws there
# ("none", "dark" or "color", each change once), whether it draws dark on the far side of the face, where the arc has
# drained away, and how many points over the face itself it draws on. Everything but the ring is hidden, so nothing
# behind it can pass for its own drawing
RING_TRACK = """
const seat = scene.seats[2];
scene.everyFrame();
for (let at = seat.ring; at.parent; at = at.parent) {
  for (const other of at.parent.children) {
    other.visible = other === at;
  }
}
const pixel = pixelsNow();
const kind = (reach, angle) => {
  const [r, g, b, a] = pixel(seat.ring.toGlobal({ x: Math.cos(angle) * reach, y: Math.sin(angle) * reach }));
  return a < 40 ? "none" : 0.299 * r + 0.587 * g + 0.114 * b < 60 ? "dark" : "color";
};
const middle = seat.spot.inward > 0 ? Math.PI : 0;
const across = [];
for (let reach = 26; reach <= 42; reach += 0.25) {
  const here = kind(reach, middle);
  if (across[across.length - 1] !== here) {
    across.push(here);
  }
}
let stray = 0;
for (let angle = 0; angle < 360; angle += 3) {
  for (const reach of [6, 14, 22]) {
    stray += kind(reach, (angle * Math.PI) / 180) === "none" ? 0 : 1;
  }
}
return { across, drained: kind(34.5, middle + Math.PI), stray };
"""


def test_the_turn_ring_sits_on_a_dark_track(driver, live):
    open_casino(driver, live)
    # CPU Dex's turn with 8 seconds left: the ring's warning amber, close to Discord's orange default face
    state = {**a_hand_on_the_flop(), "turn": 2, "left": 8}
    for seconds in (8, 3, 20):
        found = run_steps(driver, [{**state, "left": seconds}, {"wait": 50}, {"run": "ring", "js": RING_TRACK}])["ring"]
        across = found["across"]
        # The colored arc has dark on both sides of it, so it reads on a face of its own color, and the dark runs on
        # around the whole face as a track
        assert "color" in across, (seconds, found)
        first, last = across.index("color"), len(across) - 1 - across[::-1].index("color")
        assert "dark" in across[:first] and "dark" in across[last:], (seconds, found)
        assert found["drained"] == "dark", (seconds, found)
        # Nothing of the ring is drawn across the face
        assert found["stray"] == 0, (seconds, found)
    # On a phone the track reaches in over the face's gold rim: a clear band of dark between the face and the amber
    dim = run_steps(driver, [state, {"wait": 50}, {"run": "dim", "js": RING_INSIDE}], size=(390, 634))["dim"]
    assert dim >= 2, dim
    assert not problems(driver)


# On a phone, along the turn ring's radius at the middle of its colored arc, how many CSS pixels just inside the arc
# are dim, before the face's gold rim or the face itself
RING_INSIDE = """
const seat = scene.seats[2];
scene.everyFrame();
const pixel = pixelsNow();
const middle = seat.spot.inward > 0 ? Math.PI : 0;
let dim = 0;
for (let reach = 31.75; reach >= 28; reach -= 0.25) {
  const [r, g, b] = pixel(seat.ring.toGlobal({ x: Math.cos(middle) * reach, y: Math.sin(middle) * reach }));
  if (0.299 * r + 0.587 * g + 0.114 * b >= 120) {
    break;
  }
  dim += 0.25;
}
return dim * scaleOf(seat.ring);
"""


# Which table the scene draws at each size, for a seated player or a watcher
TABLE_AT = """
const [sizes, done] = arguments;
import(new URL("scenes/holdem.js", document.baseURI).href)
  .then((scene) => done(sizes.map(([width, height, watching]) => scene.layoutFor(width, height, null, watching).table)))
  .catch((e) => done(String(e)));
"""


def test_a_narrow_phone_keeps_the_upright_table(driver, live):
    open_casino(driver, live)
    sizes = [(360, height, watching) for height in range(490, 550, 10) for watching in (False, True)]
    tables = driver.execute_async_script(TABLE_AT, sizes)
    # Tall chip piles only come where they leave every seat and bet its room, so a 360-wide phone keeps the bigger
    # upright table with low piles instead of turning to the small table across
    assert tables == ["upright"] * len(sizes), list(zip(sizes, tables, strict=False))
    assert not problems(driver)


# The turn glow's brightness on CPU Juno's face, every frame for a little over one pulse
GLOW_PULSE = """
const seat = scene.seats[5];
const seen = [];
const start = performance.now();
await new Promise((resolve) => {
  const look = () => {
    scene.everyFrame();
    seen.push(seat.glow.visible ? seat.glow.alpha : 0);
    if (performance.now() - start < 1900) {
      requestAnimationFrame(look);
    } else {
      resolve();
    }
  };
  requestAnimationFrame(look);
});
return seen;
"""


def test_a_cpus_turn_glow_stays_bright(driver, live):
    open_casino(driver, live)
    # A CPU has no clock, so its glow alone says whose turn it is
    state = {**a_hand_on_the_flop(), "left": None}
    seen = run_steps(driver, [state, {"wait": 50}, {"run": "glow", "js": GLOW_PULSE}])["glow"]
    assert len(seen) > 20, seen
    assert min(seen) >= 0.5, min(seen)
    assert not problems(driver)


# While the steps after it play, every frame: how often a flying pile of chips or a "+amount" meets the player's own
# cards and their hand's tag, a pile meets the shared cards, a pile is drawn over the cut's "House" label, a sparkle
# meets the player's own cards and tag, or a pile still plainly showing meets the player's own "Won" words while
# those plainly show too
WATCH = """
const isPile = (node) => node.children.some((child) => typeof child.value === "number");
const isCard = (node) => Boolean(node.back && node.face);
const own = scene.mine === null ? null : scene.seats[scene.mine];
window.seen = { mine: 0, board: 0, house: 0, sparks: 0, won: 0, frames: 0 };
window.watching = true;
const look = () => {
  if (!window.watching) {
    return;
  }
  window.seen.frames += 1;
  const covered = own && own.covered();
  const hero = covered ? [...own.cards, ...(own.handTag.visible ? [own.handTag] : [])].map((node) => box(node, 1)) : [];
  const winning = covered && scene.won[scene.mine] !== undefined && own.sum.visible;
  const won = winning && own.sum.alpha > 0.5 ? box(own.sum, 1) : null;
  const board = scene.board.filter((piece) => piece && !piece.destroyed).map((node) => box(node, 1));
  const fx = scene.layers.fx.children;
  const house = fx.find((node) => node.words && /^House/.test(node.words.text));
  for (const node of fx) {
    if (isPile(node)) {
      const pile = box(node, 1);
      window.seen.mine += hero.some((card) => meet(pile, card)) ? 1 : 0;
      window.seen.board += board.some((card) => meet(pile, card)) ? 1 : 0;
      window.seen.house += house && fx.indexOf(node) > fx.indexOf(house) ? 1 : 0;
      window.seen.won += won && node.alpha > 0.5 && meet(pile, won) ? 1 : 0;
    } else if (node.words && node !== house) {
      window.seen.mine += hero.some((card) => meet(box(node, 1), card)) ? 1 : 0;
    } else if (!node.words && !isCard(node)) {
      for (const piece of node.children) {
        window.seen.sparks += piece.alpha > 0.05 && hero.some((card) => meet(box(piece, 1), card)) ? 1 : 0;
      }
    }
  }
  requestAnimationFrame(look);
};
requestAnimationFrame(look);
return true;
"""
SEEN = "window.watching = false; return window.seen;"


def showdown_won(awards, best, cut):
    """The hand to the showdown, ending with these awards, best five cards and cut instead of its own win"""
    steps = [step for step in a_hand_to_the_showdown() if "look" not in step]
    steps[-1] = event("win", awards=awards, best=best, cut=cut, big=False)
    return steps


def a_hand_the_player_wins():
    """The flop to the river with five seats: the player calls a raise, then wins the pot with two pair, Aces and
    Sevens (a hand with a long name), the cut going to the house"""
    win = {"amount": 1000, "winners": [0], "shares": {"0": 1000}}
    steps = showdown_won([win], {"0": cards("Ac Ah 7h 7c 9s")}, 20)
    name = "Two pair, Aces and Sevens"
    steps[0] = {**steps[0], "cards": cards("Ac 7h"), "name": name}
    show = next(i for i, step in enumerate(steps) if step.get("kind") == "show")
    steps[show] = {**steps[show], "hands": {**steps[show]["hands"], "0": {"cards": cards("Ac 7h"), "name": name}}}
    return steps


def test_chips_and_sparkles_never_cross_the_players_cards_or_the_shared_cards(driver, live):
    open_casino(driver, live)
    hand = a_hand_the_player_wins()
    for size in ((900, 600), (390, 700), (564, 334)):
        steps = [*hand[:2], {"run": "watch", "js": WATCH}, *hand[2:], {"wait": 1200}, {"run": "seen", "js": SEEN}]
        seen = run_steps(driver, steps, size=size)["seen"]
        assert seen["frames"] > 20, (size, seen)
        # The player's call drops onto the felt in front of their cards, their win melts there, and their sparkles fly
        # away from the cards, with no coins falling back onto them
        assert seen["mine"] == 0 and seen["sparks"] == 0, (size, seen)
        # Their "Won" words come in as the chips melt away, never under the chips
        assert seen["won"] == 0, (size, seen)
        # Bets, the pot and the cut go around the shared cards
        assert seen["board"] == 0, (size, seen)
    assert not problems(driver)


def a_split_with_a_cut():
    """The hand to the showdown, split between seats 1 and 5, the house taking 32"""
    win = {"amount": 988, "winners": [1, 5], "shares": {"1": 494, "5": 494}}
    return showdown_won([win], {"1": cards("Qd Qc Ah 9s 7c"), "5": cards("Ah Jc 10c 9s 7c")}, 32)


def test_a_split_and_its_cut_keep_off_the_house_label_and_the_shared_cards(driver, live):
    open_casino(driver, live)
    hand = a_split_with_a_cut()
    showdown = next(i for i, step in enumerate(hand) if step.get("kind") == "show")
    for size in ((900, 600), (390, 634), (564, 334)):
        steps = [*hand[: showdown + 1], {"run": "watch", "js": WATCH}, *hand[showdown + 1 :]]
        ring = "return scene.potRing ? scene.potRing.visible : 'drawn into the felt'"
        steps += [{"wait": 1300}, {"run": "seen", "js": SEEN}, {"run": "ring", "js": ring}]
        looks = run_steps(driver, steps, size=size)
        # The pot's piles pass under the "House" label and around the shared cards
        assert looks["seen"]["house"] == 0 and looks["seen"]["board"] == 0, (size, looks["seen"])
        # Once the pot has gone to its winners its empty ring goes too, so it never shows under a lifted card
        assert looks["ring"] is False, size
    assert not problems(driver)


# While the steps after it play, every frame: how often a pile, a "+amount" or a sparkle meets a hand shown over a
# face, a "+amount" meets any seat's plate (its name and its hand's name) or reaches past the scene's edge, and a pile
# still plainly showing meets a winner's "Won" words while those plainly show too; and in how many frames a
# "+amount" showed at all
WATCH_SHOWN = """
const isPile = (node) => node.children.some((child) => typeof child.value === "number");
const isCard = (node) => Boolean(node.back && node.face);
const meets = (one, boxes) => boxes.some((other) => meet(one, other));
window.seen = { cards: 0, plates: 0, off: 0, won: 0, gains: 0, frames: 0 };
window.watching = true;
const look = () => {
  if (!window.watching) {
    return;
  }
  const seen = window.seen;
  seen.frames += 1;
  const seated = scene.seats.filter((seat) => seat.data && seat.body.visible);
  const shown = seated.filter((seat) => seat.mode === "shown");
  // Each shown card itself, without a winner's glow around it, which a pile melting beside it may brush
  const cards = shown.flatMap((seat) => seat.cards.map((node) => box(node.face, 1)));
  const plates = seated.map((seat) => box(seat.plate, 1));
  const winners = shown.filter((seat) => scene.won[seat.number] !== undefined && seat.sum.visible);
  const words = winners.filter((seat) => seat.sum.alpha > 0.5).map((seat) => box(seat.sum, 1));
  for (const node of scene.layers.fx.children) {
    const here = box(node, 1);
    if (isPile(node)) {
      seen.cards += meets(here, cards) ? 1 : 0;
      seen.won += node.alpha > 0.5 && meets(here, words) ? 1 : 0;
    } else if (node.words && node.words.text.startsWith("+")) {
      seen.gains += 1;
      seen.cards += meets(here, cards) ? 1 : 0;
      seen.plates += meets(here, plates) ? 1 : 0;
      const off = here.left < 0 || here.top < 0 || here.right > app.screen.width || here.bottom > app.screen.height;
      seen.off += off ? 1 : 0;
    } else if (!node.words && !isCard(node)) {
      for (const piece of node.children) {
        seen.cards += piece.alpha > 0.05 && meets(box(piece, 1), cards) ? 1 : 0;
      }
    }
  }
  requestAnimationFrame(look);
};
requestAnimationFrame(look);
return true;
"""


def others_take_the_side_pots():
    """At the river, CPU Lena at the top wins the main pot and CPU Mabel at the top right a side pot, with the
    player's and CPU Dex's hands shown too"""
    seats = [
        seat_row(0, "Member", 0, me=True, in_hand=True, all_in=True),
        seat_row(1, "CPU Rosa", 1990, in_hand=True, folded=True),
        seat_row(2, "CPU Dex", 1500, in_hand=True),
        seat_row(3, "CPU Lena", 0, in_hand=True, all_in=True),
        seat_row(4, "CPU Mabel", 900, in_hand=True),
        None,
    ]
    shown = {
        "0": {"cards": cards("Ks Kd"), "name": "Pair of Kings"},
        "2": {"cards": cards("Jc 10c"), "name": "Pair of Jacks"},
        "3": {"cards": cards("As Ah"), "name": "Pair of Aces"},
        "4": {"cards": cards("Qs Qh"), "name": "Pair of Queens"},
    }
    board = cards("2c 7d 9h Js 4s")
    main = {"amount": 1600, "winners": [3], "shares": {"3": 1600}}
    side = {"amount": 1000, "winners": [4], "shares": {"4": 1000}}
    best = {"3": cards("As Ah Js 9h 7d"), "4": cards("Qs Qh Js 9h 7d")}
    return [
        {"t": "hole", "game": "holdem", "hand": 3, "cards": cards("Ks Kd"), "name": "Pair of Kings"},
        table_state(seats, phase="playing", button=0, board=board, pots=[1600, 1000], street="river"),
        event("show", hands=shown, pots=[1600, 1000]),
        event("win", awards=[main, side], best=best, cut=0, big=False),
    ]


def short_all_in_before_the_run_out():
    """CPU Dex all in short before the flop against the player and CPU Mabel: the hands turn up with a main pot all
    three can win and a side pot only the player and Mabel can, before any card runs out"""
    seats = [
        seat_row(0, "Member", 1000, me=True),
        None,
        seat_row(2, "CPU Dex", 400),
        None,
        seat_row(4, "CPU Mabel", 1500),
        None,
    ]
    dealt = [row and {**row, "in_hand": True, "cards": 2} for row in seats]
    shown = {
        "0": {"cards": cards("Qs Qd"), "name": "Pair of Queens"},
        "2": {"cards": cards("As Ad"), "name": "Pair of Aces"},
        "4": {"cards": cards("Ks Kd"), "name": "Pair of Kings"},
    }
    return [
        table_state(seats, hand=8, round=8, button=2),
        {"t": "hole", "game": "holdem", "hand": 9, "cards": cards("Qs Qd"), "name": "Pair of Queens"},
        table_state(dealt, phase="playing", hand=9, round=9, button=4, street="preflop", turn=4, left=35),
        act(4, "raise", 1000, 500),
        act(0, "all_in", 1000, 0),
        act(2, "all_in", 400, 0),
        event("show", hands=shown, pots=[1200, 1200]),
    ]


# The pot's piles once the hands are up: each one's words, whether they keep apart and inside the scene, how many
# meet a seat or the place the shared cards run out to or show under the smallest readable size, and whether the
# pot's empty ring is drawn
POT_WORDS = """
const groups = scene.pot.children;
const words = groups.map((group) => group.children[1]);
const boxes = words.map((sum) => box(sum, 1));
const seats = scene.seats.filter((seat) => seat.data && seat.body.visible).map((seat) => box(seat.body, 1));
const plan = scene.plan.board;
const corner = scene.layers.fx.toGlobal({ x: plan.left, y: plan.top });
const far = scene.layers.fx.toGlobal({ x: plan.right, y: plan.bottom });
const board = { left: corner.x, top: corner.y, right: far.x, bottom: far.y };
return {
  texts: words.map((sum) => sum.words.text),
  apart: boxes.every((one, index) => boxes.slice(index + 1).every((other) => !meet(one, other))),
  seats: boxes.filter((one) => seats.some((other) => meet(one, other))).length,
  inside: boxes.every((one) => one.left >= 0 && one.top >= 0 && one.right <= app.screen.width),
  small: words.filter((sum) => sum.words.style.fontSize * scaleOf(sum.words) < 9.5).length,
  board: boxes.filter((one) => meet(one, board)).length,
  ring: scene.potRing.visible && scene.potRing.renderable,
};
"""


def test_side_pots_stand_apart_with_their_names_before_the_board_runs_out(driver, live):
    open_casino(driver, live)
    hand = short_all_in_before_the_run_out()
    for size in ((900, 600), (390, 634), (564, 334)):
        steps = [*hand[:-1], {"run": "watch", "js": WATCH_GATHER}, hand[-1], {"wait": 1600}]
        steps += [{"run": "seen", "js": SEEN}, {"run": "pots", "js": POT_WORDS}]
        looks = run_steps(driver, steps, size=size)
        found = looks["pots"]
        # The bets join the pots as the hands turn up, so each side pot is its own pile, named, before any card
        assert found["texts"] == ["Main 1,200", "Side 1,200"], (size, found)
        assert found["apart"] and found["inside"] and found["seats"] == 0, (size, found)
        assert found["small"] == 0 and found["board"] == 0, (size, found)
        # The piles come only once the bets have slid in: no frame shows a bet still in front of a seat beside them
        assert looks["seen"]["frames"] > 20 and looks["seen"]["both"] == 0, (size, looks["seen"])
        # With more than one pile, the pot's empty ring between them is gone
        assert not found["ring"], (size, found)
    assert not problems(driver)


# Every frame while the steps after it play: how often a seat still has chips in front of it while the pot already
# shows its piles
WATCH_GATHER = """
window.seen = { both: 0, frames: 0 };
window.watching = true;
const look = () => {
  if (!window.watching) {
    return;
  }
  window.seen.frames += 1;
  const betting = scene.seats.some((seat) => seat.chips.children.length > 0);
  window.seen.both += betting && scene.pot.children.length > 0 ? 1 : 0;
  requestAnimationFrame(look);
};
requestAnimationFrame(look);
return true;
"""


def test_another_winners_celebration_stays_off_their_shown_cards_and_hand_name(driver, live):
    open_casino(driver, live)
    alone = showdown_won([{"amount": 1020, "winners": [2], "shares": {"2": 1020}}], {"2": cards("7h 7d 7c As Ks")}, 0)
    # CPU Dex alone at the top left, a split between the two bottom corners, and side pots to the top and top right
    for hand in (alone, a_split_with_a_cut(), others_take_the_side_pots()):
        show = next(i for i, step in enumerate(hand) if step.get("kind") == "show")
        for size in ((900, 600), (390, 634), (564, 334)):
            steps = [*hand[: show + 1], {"run": "watch", "js": WATCH_SHOWN}, *hand[show + 1 :], {"wait": 1200}]
            seen = run_steps(driver, [*steps, {"run": "seen", "js": SEEN}], size=size)["seen"]
            assert seen["frames"] > 20 and seen["gains"] > 5, (size, seen)
            # The pot melts at each winner's bet spot, their sparkles fly out beside their cards with no coins, and
            # their "+amount" sits beside the plate, on the screen, never on a name or a hand
            assert seen["cards"] == 0 and seen["plates"] == 0 and seen["off"] == 0, (size, seen)
            # Their "Won" words come in as the chips melt away, never under the chips
            assert seen["won"] == 0, (size, seen)
    assert not problems(driver)


# Every frame while the steps after it play: how many sparkles still plainly showing reach past the scene's edge
WATCH_EDGE = """
const isPile = (node) => node.children.some((child) => typeof child.value === "number");
const isCard = (node) => Boolean(node.back && node.face);
window.seen = { cut: 0, sparks: 0, frames: 0 };
window.watching = true;
const look = () => {
  if (!window.watching) {
    return;
  }
  window.seen.frames += 1;
  for (const node of scene.layers.fx.children) {
    if (isPile(node) || node.words || isCard(node)) {
      continue;
    }
    for (const piece of node.children) {
      if (piece.alpha > 0.05) {
        const here = box(piece, 1);
        window.seen.sparks += 1;
        const out = here.left < 0 || here.top < 0 || here.right > app.screen.width || here.bottom > app.screen.height;
        window.seen.cut += out ? 1 : 0;
      }
    }
  }
  requestAnimationFrame(look);
};
requestAnimationFrame(look);
return true;
"""


def test_win_sparkles_burst_inward_near_the_scenes_edges(driver, live):
    open_casino(driver, live)
    alone = showdown_won([{"amount": 1020, "winners": [2], "shares": {"2": 1020}}], {"2": cards("7h 7d 7c As Ks")}, 0)
    # A winner everyone folded to in a corner (sparkles over the face), the player's own win, another player's at the
    # top left, a split between the bottom corners, and side pots to the top and top right
    hands = [a_hand_folded_on_the_turn(), a_hand_the_player_wins(), alone, a_split_with_a_cut()]
    for hand in [*hands, others_take_the_side_pots()]:
        for size in ((900, 600), (390, 634), (564, 334)):
            steps = [*hand[:-1], {"run": "watch", "js": WATCH_EDGE}, hand[-1], {"wait": 1200}]
            seen = run_steps(driver, [*steps, {"run": "seen", "js": SEEN}], size=size)["seen"]
            assert seen["sparks"] > 100 and seen["cut"] == 0, (hand[-1]["awards"], size, seen)
    assert not problems(driver)


# Whether a winning seat's glowing shown cards meet the hand's name on its plate's second line
GLOW_ON_NAME = """
const seat = scene.seats[2];
const bounds = seat.stack.getBounds();
const half = seat.stack.style.fontSize * scaleOf(seat.stack) * 0.42;
const middle = (bounds.minY + bounds.maxY) / 2;
const words = { left: bounds.minX, right: bounds.maxX, top: middle - half, bottom: middle + half };
const glows = seat.cards.flatMap((card) => card.children.filter((child) => child.label === "glow"));
return {
  glows: glows.length,
  text: seat.stack.text,
  meets: glows.some((glow) => {
    const b = glow.getBounds();
    return b.minX < words.right && words.left < b.maxX && b.minY < words.bottom && words.top < b.maxY;
  }),
};
"""


def test_a_winners_lifted_cards_leave_its_hand_name_clear(driver, live):
    open_casino(driver, live)
    steps = [step for step in a_hand_to_the_showdown() if "look" not in step]
    for size in ((900, 600), (390, 700)):
        found = run_steps(driver, [*steps, {"wait": 500}, {"run": "glow", "js": GLOW_ON_NAME}], size=size)["glow"]
        # CPU Dex, the top left seat with its plate over its face, wins with three 7s
        assert found["glows"] == 2 and found["text"], (size, found)
        assert not found["meets"], (size, found)
    assert not problems(driver)


def test_seats_the_table_no_longer_has_fade_out(driver, live):
    open_casino(driver, live)
    seats = [seat_row(0, "Member", 1000, me=True), seat_row(1, "CPU Rosa", 2000), seat_row(2, "CPU Dex", 2000)]
    before = table_state([*seats, None, None, None], hand=2)
    after = table_state([seats[0], None, None, None, None, None], mode="real", hand=2)
    looks = run_steps(driver, [before, {"wait": 50}, after, look("fading"), {"wait": 600}, look("gone")])
    # The CPUs fade out as a real game starts rather than vanishing in one frame
    assert "CPU Rosa" in looks["fading"]["texts"].get("seat-1", []), looks["fading"]["texts"]
    assert "CPU Rosa" not in looks["gone"]["texts"].get("seat-1", []), looks["gone"]["texts"]
    assert not problems(driver)


# The brightest point in the ring between the word and the edge of each empty seat's "Sit" disc
SIT_GLARE = """
scene.everyFrame();
const pixel = pixelsNow();
return scene.seats.filter((seat) => seat.empty.visible).map((seat) => {
  let brightest = 0;
  for (let angle = 0; angle < 360; angle += 10) {
    for (const reach of [19, 23, 27]) {
      const turn = (angle * Math.PI) / 180;
      const [r, g, b] = pixel(seat.empty.toGlobal({ x: Math.cos(turn) * reach, y: Math.sin(turn) * reach }));
      brightest = Math.max(brightest, 0.299 * r + 0.587 * g + 0.114 * b);
    }
  }
  return brightest;
});
"""


def test_an_empty_seats_sit_disc_hides_the_pad_under_it(driver, live):
    open_casino(driver, live)
    seats = [None, seat_row(1, "CPU Rosa", 2000), None, None, seat_row(4, "CPU Mabel", 2000), None]
    state = {**table_state(seats, hand=2), "players": []}
    for size in ((900, 600), (390, 700)):
        glare = run_steps(driver, [state, {"wait": 50}, {"run": "glare", "js": SIT_GLARE}], me="watcher", size=size)
        # The rail's gold pad no longer shows through as a bright bar across "Sit"
        assert glare["glare"] and max(glare["glare"]) < 80, (size, glare["glare"])
    assert not problems(driver)


WATCHER_LAYOUT = """
const [width, height, done] = arguments;
import(new URL("scenes/holdem.js", document.baseURI).href)
  .then((scene) => done(scene.layoutFor(width, height, null, true)))
  .catch((e) => done({ error: String(e) }));
"""


# Where the scene put each seat, in CSS pixels, and where the watcher's plan and the seated player's plan put them
DRAWN_SEATS = """
const holdem = await import(new URL("scenes/holdem.js", document.baseURI).href);
const { plan } = scene;
const where = (seats) => seats.map((seat) => [Math.round(seat.x), Math.round(seat.y)]);
const drawn = plan.spots.map((spot) => ({ x: plan.left + spot.x * plan.scale, y: plan.offset + spot.y * plan.scale }));
return {
  drawn: where(drawn),
  watching: where(holdem.layoutFor(app.screen.width, app.screen.height, null, true).seats),
  seated: where(holdem.layoutFor(app.screen.width, app.screen.height, null, false).seats),
};
"""


def test_a_watcher_sees_the_table_centered(driver, live):
    open_casino(driver, live)
    for width, height in ((390, 700), (390, 560), (1280, 700), (844, 334)):
        layout = driver.execute_async_script(WATCHER_LAYOUT, width, height)
        assert "error" not in layout, layout
        boxes = [seat["box"] for seat in layout["seats"]]
        top = min(box["top"] for box in boxes)
        bottom = height - max(box["top"] + box["height"] for box in boxes)
        # As much room above the six seats as below them: no empty band where the player's own seat would be
        assert abs(top - bottom) <= 8, (width, height, top, bottom)
    # Someone without a seat gets that plan from the scene itself, and taking a seat brings the player's own plan
    seated = a_hand_on_the_flop()
    watching = {**seated, "seats": [None, *seated["seats"][1:]]}
    steps = [watching, {"wait": 50}, {"run": "watching", "js": DRAWN_SEATS}, seated, {"wait": 400}]
    looks = run_steps(driver, [*steps, {"run": "seated", "js": DRAWN_SEATS}], size=(390, 700))
    assert looks["watching"]["drawn"] == looks["watching"]["watching"] != looks["watching"]["seated"], looks
    assert looks["seated"]["drawn"] == looks["seated"]["seated"], looks
    assert not problems(driver)


SMALL_FACES = """
scene.everyFrame();
return scene.board.map((piece) => (piece.bigIndex ? piece.bigIndex.key : null));
"""


def test_small_shared_cards_show_a_big_rank_and_suit(driver, live):
    open_casino(driver, live)
    state = a_hand_on_the_flop()
    small = run_steps(driver, [state, {"wait": 50}, {"run": "faces", "js": SMALL_FACES}], size=(564, 334))["faces"]
    # On a sideways phone the shared cards are about 32 pixels wide: each wears its rank and suit big
    assert small == ["A hearts", "7 clubs", "2 diamonds"], small
    big = run_steps(driver, [state, {"wait": 50}, {"run": "faces", "js": SMALL_FACES}], size=(900, 600))["faces"]
    # Drawn bigger, they keep their own art
    assert big == [None, None, None], big
    assert not problems(driver)


MOVE_WORDS = """
const done = arguments[arguments.length - 1];
import(new URL("scenes/holdem_seats.js", document.baseURI).href).then(({ handNames, moveWords }) => {
  const back = moveWords({ move: "return", amount: 20, back: 40 }, { big: 20 });
  done({
    back: [back.text, ...(back.shorter || [])],
    names: [
      "Two pair, Aces and Sevens",
      "Full house, Kings over Sevens",
      "Flush, King high",
      "Straight, Ten high",
    ].map(handNames),
  });
}).catch((e) => done({ error: String(e) }));
"""


def test_short_words_keep_what_matters(driver, live):
    open_casino(driver, live)
    words = driver.execute_async_script(MOVE_WORDS)
    assert "error" not in words, words
    # A tight tag still says how much came back
    assert words["back"] == ["Got 40 back", "40 back"], words["back"]
    # Before a hand loses its ranks, it says them alone
    two_pair, full_house, flush, straight = words["names"]
    assert "Aces & Sevens" in two_pair and two_pair.index("Aces & Sevens") < two_pair.index("Two pair"), two_pair
    assert "Ks full" in full_house and full_house.index("Ks full") < full_house.index("Full house"), full_house
    assert "K flush" in flush and flush.index("K flush") < flush.index("Flush"), flush
    assert "Ten straight" in straight and straight.index("Ten straight") < straight.index("Straight"), straight
    assert not problems(driver)


# The player's own hand tag and plate, and a seat's tucked cards and its tag, as boxes; the name's box is its letters
OWN_MARKS = """
const letters = (text) => {
  const b = text.getBounds();
  const half = text.style.fontSize * scaleOf(text) * 0.55;
  const middle = (b.minY + b.maxY) / 2;
  return { left: b.minX, right: b.maxX, top: middle - half, bottom: middle + half };
};
const own = scene.seats[scene.mine];
const dex = scene.seats[2];
return {
  hand: own.handTag.words.text,
  handSize: own.handTag.words.style.fontSize * scaleOf(own.handTag.words),
  handOnName: meet(box(own.handTag.back), letters(own.name)),
  tag: dex.tag.visible,
  tagOnCards: dex.tucked.children.length > 0 && meet(box(dex.tag.back), box(dex.tucked)),
};
"""


def test_the_players_hand_name_has_room_and_tags_sit_clear_of_cards(driver, live):
    open_casino(driver, live)
    state = a_hand_on_the_flop()
    hole = {"t": "hole", "game": "holdem", "hand": 3, "cards": cards("Ks Kd"), "name": "Three of a kind, Kings"}
    for size in ((900, 600), (390, 700)):
        marks = run_steps(driver, [state, hole, {"wait": 400}, {"run": "marks", "js": OWN_MARKS}], size=size)["marks"]
        # The hand's tag may grow past the cards' width, so its words stay whole, and on a desktop bigger than the
        # smallest size
        least = 12 if size == (900, 600) else 10
        assert marks["hand"] == "Three of a kind, Kings" and marks["handSize"] >= least, (size, marks)
        # It never touches the player's name on the plate under it
        assert not marks["handOnName"], (size, marks)
        # A seat's tag ("Raise 60") sits on the felt, not on the cards tucked behind its face
        assert marks["tag"] and not marks["tagOnCards"], (size, marks)
    assert not problems(driver)


def test_a_card_still_sliding_when_the_table_turns_lands_on_the_new_table(driver, live):
    open_casino(driver, live)
    seats = a_hand_on_the_flop()["seats"]
    state = table_state(seats, phase="playing", button=5, pots=[190], street="preflop", turn=5)
    places = """
    return scene.board.map((piece, index) => {
      const spot = scene.boardSpot(index);
      return Math.abs(piece.x - spot.x) < 0.5 && Math.abs(piece.y - spot.y) < 0.5;
    });
    """
    steps = [state, later(event("flop", cards=cards("Ah 7c 2d"))), {"wait": 60}, {"layout": [390, 700]}]
    steps += [{"wait": 900}, {"run": "placed", "js": places}]
    placed = run_steps(driver, steps, size=(900, 700))["placed"]
    # The phone turned upright while the flop slid out: each card ends on the upright table's place for it
    assert placed == [True, True, True], placed
    assert not problems(driver)


def test_the_table_ends_where_the_newest_layout_puts_it(driver, live):
    open_casino(driver, live)
    seated = a_hand_on_the_flop()
    watching = {**seated, "seats": [None, *seated["seats"][1:]]}
    # The viewer sits down, so the table starts gliding, and at once the scene gets smaller, which changes its size
    steps = [watching, {"wait": 100}, seated, {"layout": [390, 451]}, {"wait": 500}]
    where = "return [scene.root.x - scene.plan.left, scene.root.y - scene.plan.offset]"
    off = run_steps(driver, [*steps, {"run": "off", "js": where}], size=(390, 700))["off"]
    # The table sits where the newest layout puts it: the older glide stopped instead of pulling it back
    assert all(abs(value) < 0.5 for value in off), off
    assert not problems(driver)


def test_the_wallpaper_covers_the_scene_while_the_table_glides(driver, live):
    open_casino(driver, live)
    state = a_hand_on_the_flop()
    # A tall phone 100 pixels shorter at the same size of table: the table glides up to its new place, with only the
    # wallpaper above and below its picture. The dark toward the edges goes for this check, so only the wallpaper can
    # cover them
    shade = {"run": "shade", "js": "scene.art.shade.visible = false"}
    steps = [
        state,
        {"wait": 100},
        shade,
        {"layout": [390, 750]},
        {"wait": 30},
        {"cover": "gliding", "frame": [390, 750]},
    ]
    bare = run_steps(driver, steps, size=(390, 850))["gliding"]
    assert bare == [], bare
    assert not problems(driver)


# ---------- The dock: people, offers, the clock and the status line ----------


def guests(count):
    """Other people here, the first with a long name"""
    names = ["Bartholomew the Magnificent", *(f"Guest{n}" for n in range(1, count))]
    return [
        {"id": str(9000 + n), "name": name, "avatar": None, "bet": None, "choice": None, "away": False}
        for n, name in enumerate(names[:count])
    ]


MYSELF = {"id": str(ME), "name": "Member", "avatar": None, "bet": None, "choice": None, "away": False}
# The people list's entries: the player's own, the "+N" entry's words, and whether each is whole: inside the list's
# width and above the dock's bottom
PEOPLE_ROW = """
const list = document.getElementById('players');
const room = list.getBoundingClientRect();
const dock = list.closest('.dock').getBoundingClientRect();
return [...list.children].map((item) => {
  const box = item.getBoundingClientRect();
  return {
    me: item.classList.contains('me'),
    more: item.classList.contains('more') ? item.textContent.trim() : null,
    inside: box.left >= room.left - 0.5 && box.right <= room.right + 0.5 && box.bottom <= dock.bottom + 0.5
      && box.width > 0,
  };
});
"""
# The "+N" button and the player's own entry as drawn now, and later whether those same buttons are still drawn
KEEP_PEOPLE = """
window.kept = [...document.querySelectorAll('#players li.more button, #players li.me button')];
return window.kept.length;
"""
STILL_KEPT = "return window.kept.every((node) => node.isConnected)"


def open_everyone(driver):
    """Presses "+N" and waits for the hub's own list of everyone here to open"""
    driver.find_element(By.CSS_SELECTOR, "#players li.more button").click()
    driver.switch_to.default_content()
    try:
        WebDriverWait(driver, 5).until(lambda _: driver.execute_script(PANEL_OPEN))
    finally:
        driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))


PANEL_OPEN = "const panel = document.querySelector('.hub-people-panel'); return Boolean(panel && !panel.hidden)"


def test_an_upright_phone_lists_whole_names_then_a_count_that_opens_everyone(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    # Six people here, the player's own row last in the bot's list, as after a reload
    state = {**a_hand_on_the_flop(), "players": [*guests(5), MYSELF]}
    with at_size(driver, 390, 844, 2, True):
        resized(driver, 390, 844)
        on_loop(live, conn.send(state))
        browser.wait_for(driver, "document.querySelector('#players li.more') !== null")
        row = driver.execute_script(PEOPLE_ROW)
        # The player's own row first, then only whole entries (a long name ends in "..." inside its own), then "+N"
        # for everyone who didn't fit
        assert row[0]["me"] and all(entry["inside"] for entry in row), row
        assert row[-1]["more"] == f"+{6 - (len(row) - 1)}", row
        # Tables keep coming while the CPUs play: the entries stay the same buttons, so a tap that spans a table still
        # lands
        assert driver.execute_script(KEEP_PEOPLE) == 2
        for turn in (2, 5):
            on_loop(live, conn.send({**state, "turn": turn}))
            time.sleep(0.3)
        assert driver.execute_script(STILL_KEPT)
        # The count opens the hub's own list of everyone here
        open_everyone(driver)
    # With room for everyone the list shows them all, the player's own row still first
    browser.wait_for(driver, "document.querySelector('#players li.more') === null")
    row = driver.execute_script(PEOPLE_ROW)
    assert len(row) == 6 and row[0]["me"], row
    assert not problems(driver)


def test_a_sideways_watcher_lists_the_rows_that_fit_then_a_count_that_opens_everyone(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    seated = a_hand_on_the_flop()
    state = {**seated, "seats": [None, *seated["seats"][1:]], "players": [MYSELF, *guests(7)]}
    with at_size(driver, 844, 390, 2, True):
        resized(driver, 844, 390)
        on_loop(live, conn.send(state))
        browser.wait_for(driver, "document.querySelector('#players li.more') !== null")
        rows = driver.execute_script(PEOPLE_ROW)
        # Eight people here: the player's own row first, whole rows down to the dock's bottom, then "+N" for the rest,
        # and nothing to scroll
        assert rows[0]["me"] and all(row["inside"] for row in rows), rows
        assert rows[-1]["more"] == f"+{8 - (len(rows) - 1)}", rows
        assert driver.execute_script(DOCK_STILL)
        open_everyone(driver)
    assert not problems(driver)


def test_a_sideways_people_list_refits_when_the_offer_comes_back_after_the_move(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    state = {**a_hand_on_the_flop(), "players": [MYSELF, *guests(5)]}
    with at_size(driver, 844, 390, 2, True):
        resized(driver, 844, 390)
        send_all(live, conn, [state, {**state, "turn": 0, "waiting": [str(ME)]}, ASK, OFFER])
        WebDriverWait(driver, 5).until(lambda _: bar_up(driver))
        above = driver.execute_script(ABOVE_BAR)
        assert above["shown"] and above["under"] == 0 and above["more"], above
        # The player folds and the bot sends the offer again, before any table: its strip takes room above the people,
        # and the list refits to the rows still whole, with nothing to scroll
        driver.find_element(By.ID, "hd-fold").click()
        on_loop(live, conn.send({**OFFER, "max": 2000}))
        WebDriverWait(driver, 5).until(lambda _: strip_up(driver))
        rows = driver.execute_script(PEOPLE_ROW)
        assert rows[-1]["more"] and all(row["inside"] for row in rows), rows
        assert driver.execute_script(DOCK_STILL)
        # Sliding past the balance adds the reason's line to the strip: the list refits again, every row whole
        driver.execute_script(SLIDE_BUY_IN, 1)
        browser.wait_for(driver, "!document.getElementById('hd-buyin-why').hidden")
        rows = driver.execute_script(PEOPLE_ROW)
        assert all(row["inside"] for row in rows) and driver.execute_script(DOCK_STILL), rows
    assert not problems(driver)


def test_a_sideways_seated_player_sees_every_person_who_fits_under_their_buttons(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    state = {**a_hand_on_the_flop(), "players": [MYSELF, *guests(2)], "mode": "real"}
    with at_size(driver, 844, 390, 2, True):
        resized(driver, 844, 390)
        on_loop(live, conn.send(state))
        browser.wait_for(driver, "!document.getElementById('hd-ticks').hidden")
        # Between turns the list starts right under the seat's buttons, with no room kept for the bar, so all three
        # people show whole with no "+N"
        rows = driver.execute_script(PEOPLE_ROW)
        assert len(rows) == 3 and not any(row["more"] for row in rows), rows
        assert all(row["inside"] for row in rows) and driver.execute_script(DOCK_STILL), rows
        # The player's turn: the bar slides in over the dock's bottom, every move within reach, the status line above
        # it, and the list shows the people who fit whole above the bar, then "+N", none under the bar
        send_all(live, conn, [{**state, "turn": 0, "waiting": [str(ME)]}, ASK])
        WebDriverWait(driver, 5).until(lambda _: bar_up(driver))
        found = driver.execute_script(CONTROLS_CHECK, BAR, True)
        assert found == {"controls": 9, "small": [], "missed": [], "off": []}, found
        assert driver.execute_script(UNDER_STATUS) and driver.execute_script(DOCK_STILL)
        above = driver.execute_script(ABOVE_BAR)
        assert above["shown"] and above["under"] == 0 and above["rows"] == 2 and above["more"] == "+2", above
        # The bar goes: every person shows again
        on_loop(live, conn.send(act(0, "call", 60, 1880)))
        browser.wait_for(driver, "!document.getElementById('hd-bar').classList.contains('up')")
        rows = driver.execute_script(PEOPLE_ROW)
        assert len(rows) == 3 and not any(row["more"] for row in rows), rows
    assert not problems(driver)


# The people list on the player's turn: whether it shows, how many entries, the "+N" words, and how many entries reach
# under the bar's top
ABOVE_BAR = """
const list = document.getElementById('players');
const items = [...list.querySelectorAll('li')];
const bar = document.getElementById('hd-bar').getBoundingClientRect();
return {
  shown: getComputedStyle(list).visibility === 'visible',
  rows: items.length,
  more: items.find((item) => item.classList.contains('more'))?.textContent.trim() || '',
  under: items.filter((item) => item.getBoundingClientRect().bottom > bar.top + 0.5).length,
};
"""


def test_a_desktop_offer_is_the_one_choice_in_the_dock(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    on_loop(live, conn.send({**a_hand_on_the_flop(), "players": [MYSELF, *guests(2)]}))
    browser.wait_for(driver, "!document.getElementById('hd-ticks').hidden")
    assert driver.execute_script(SHOWN, "hd-stand")
    before = driver.execute_script(PEOPLE_TOP)
    on_loop(live, conn.send(OFFER))
    WebDriverWait(driver, 5).until(lambda _: strip_up(driver))
    # The ticks and Stand up step aside while the strip is open, as on a phone: Watch instead already stands the
    # player up
    assert not driver.execute_script(SHOWN, "hd-stand") and not driver.execute_script(SHOWN, "hd-ticks")
    found = driver.execute_script(CONTROLS_CHECK, "#hd-offer button, #hd-offer input, #hd-wait button", False)
    assert found == {"controls": 3, "small": [], "missed": [], "off": []}, found
    # The strip takes their place rather than adding to it: it starts where they did and the people here stay put
    after = driver.execute_script(PEOPLE_TOP)
    assert abs(after["people"] - before["people"]) < 0.5 and abs(after["strip"] - before["deck"]) < 0.5, (before, after)
    assert not problems(driver)


# Where the seat's rows start, where the offer's strip starts, and where the people list starts, in CSS pixels
PEOPLE_TOP = """
const top = (id) => document.getElementById(id).getBoundingClientRect().top;
return { deck: top('hd-deck'), strip: top('hd-offer'), people: top('players') };
"""


DOCK_STILL = """
const dock = document.querySelector('#table .dock');
return dock.scrollHeight === dock.clientHeight && dock.scrollTop === 0;
"""
SHOWN = "const node = document.getElementById(arguments[0]); return getComputedStyle(node).visibility === 'visible'"
OFFER = {"t": "offer", "game": "holdem", "kind": "join", "min": 400, "max": 1000, "left": 20}
ASK = {"t": "ask", "game": "holdem", "moves": ["fold", "call", "raise"], "call": 60, "min_to": 120, "max_to": 1940}
ASK.update(pot=190, bet=0)


# Moves the buy-in's slider this many steps, the way a finger does
SLIDE_BUY_IN = """
const slider = document.getElementById('hd-buyin-slider');
slider.value = String(Number(slider.value) + arguments[0]);
slider.dispatchEvent(new Event('input'));
"""


def my_turn():
    """The player's turn on the flop: the table waiting on them, then the bot asking for their move"""
    return [{**a_hand_on_the_flop(), "turn": 0, "waiting": [str(ME)]}, ASK]


def send_all(live, conn, messages):
    for message in messages:
        on_loop(live, conn.send(message))


def test_an_upright_offer_takes_the_ticks_place_and_the_table_keeps_its_size(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    with at_size(driver, 390, 844, 2, True):
        resized(driver, 390, 844)
        on_loop(live, conn.send(a_hand_on_the_flop()))
        browser.wait_for(driver, "!document.getElementById('hd-ticks').hidden")
        # Between turns the dock holds still: nothing hangs past its bottom for a finger to scroll to
        assert driver.execute_script(DOCK_STILL)
        between = driver.execute_script(SCENE_HEIGHT)
        on_loop(live, conn.send(OFFER))
        WebDriverWait(driver, 5).until(lambda _: strip_up(driver))
        # The offer's strip stands where the ticks were: the table keeps its size and nothing scrolls
        assert not driver.execute_script(SHOWN, "hd-ticks")
        assert driver.execute_script(SCENE_HEIGHT) == between and driver.execute_script(DOCK_STILL)
        found = driver.execute_script(CONTROLS_CHECK, "#hd-offer button, #hd-offer input", True)
        assert found == {"controls": 3, "small": [], "missed": [], "off": []}, found
        # The player's turn: the bar slides in over the dock, the offer hides completely rather than peeking out
        # above it, and the table still keeps its size
        send_all(live, conn, my_turn())
        WebDriverWait(driver, 5).until(lambda _: bar_up(driver))
        assert driver.execute_script("return document.getElementById('hd-offer').hidden")
        assert driver.execute_script(SCENE_HEIGHT) == between and driver.execute_script(DOCK_STILL)
        # The player moves: the bar goes, and the offer waits out of sight for the bot to send it again with its time
        # started over, rather than coming back for a moment with the countdown it had
        driver.find_element(By.ID, "hd-call").click()
        browser.wait_for(driver, "!document.getElementById('hd-bar').classList.contains('up')")
        time.sleep(0.5)
        assert driver.execute_script("return document.getElementById('hd-offer').hidden")
        on_loop(live, conn.send({**OFFER, "max": 2000}))
        WebDriverWait(driver, 5).until(lambda _: strip_up(driver))
        assert driver.execute_script(SECONDS_LEFT) >= OFFER["left"] - 1
        found = driver.execute_script(CONTROLS_CHECK, "#hd-offer button, #hd-offer input", True)
        assert found == {"controls": 3, "small": [], "missed": [], "off": []}, found
        # One step past the balance of 1,000: Buy in gives way to the reason, the slider stays to slide back with, and
        # the table still keeps its size
        driver.execute_script(SLIDE_BUY_IN, 1)
        browser.wait_for(driver, "!document.getElementById('hd-buyin-why').hidden")
        found = driver.execute_script(CONTROLS_CHECK, "#hd-offer button, #hd-offer input", True)
        assert found == {"controls": 2, "small": [], "missed": [], "off": []}, found
        assert driver.find_element(By.ID, "hd-buyin-slider").is_displayed()
        assert not driver.find_element(By.ID, "hd-buyin-yes").is_displayed()
        assert driver.execute_script(SCENE_HEIGHT) == between and driver.execute_script(DOCK_STILL)
        driver.execute_script(SLIDE_BUY_IN, -1)
        browser.wait_for(driver, "document.getElementById('hd-buyin-why').hidden")
        assert re.fullmatch(r"Buy in\s+1,000", text(driver, "hd-buyin-yes"))
        # An offer the player's balance can't meet says why, and the table still keeps its size
        on_loop(live, conn.send({**OFFER, "min": 900000, "max": 1000000}))
        browser.wait_for(driver, "document.getElementById('hd-buyin-why').textContent.includes('minimum')")
        assert driver.execute_script(SCENE_HEIGHT) == between and driver.execute_script(DOCK_STILL)
        # The player's time runs out: the bot sends the offer again while the bar is still up, before the event of the
        # move it played for them, and the strip shows once that event takes the bar away
        on_loop(live, conn.send(OFFER))
        browser.wait_for(driver, "document.getElementById('hd-buyin-why').hidden")
        send_all(live, conn, my_turn())
        WebDriverWait(driver, 5).until(lambda _: bar_up(driver))
        on_loop(live, conn.send(OFFER))
        time.sleep(0.3)
        assert driver.execute_script("return document.getElementById('hd-offer').hidden")
        on_loop(live, conn.send(act(0, "fold", 0, 1940)))
        browser.wait_for(driver, "!document.getElementById('hd-bar').classList.contains('up')")
        WebDriverWait(driver, 5).until(lambda _: strip_up(driver))
        assert driver.execute_script(SCENE_HEIGHT) == between and driver.execute_script(DOCK_STILL)
    assert not problems(driver)


# Each control's box and the people row's entries, at the sideways phone
SIDEWAYS_OFFER = """
const box = (node) => node.getBoundingClientRect();
const onScreen = (r) => r.width > 0 && r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight;
const slider = box(document.querySelector('#hd-offer input'));
const buttons = [...document.querySelectorAll('#hd-offer button')].filter((node) => node.offsetParent !== null).map(box);
const people = [...document.querySelectorAll('#players li')].map(box);
return {
  slider: onScreen(slider),
  ownRow: buttons.every((r) => r.bottom <= slider.top || r.top >= slider.bottom),
  people: people.length > 0 && people.every(onScreen),
};
"""


def test_a_sideways_offer_gives_its_slider_a_row_and_keeps_the_people_in_view(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    with at_size(driver, 844, 390, 2, True):
        resized(driver, 844, 390)
        on_loop(live, conn.send({**a_hand_on_the_flop(), "players": [MYSELF, *guests(2)]}))
        on_loop(live, conn.send(OFFER))
        WebDriverWait(driver, 5).until(lambda _: strip_up(driver))
        found = driver.execute_script(SIDEWAYS_OFFER)
        assert found == {"slider": True, "ownRow": True, "people": True}, found
        # Watch instead stands the player up, so Stand up steps aside while the offer is open
        assert not driver.find_element(By.ID, "hd-stand").is_displayed()
    assert not problems(driver)


def test_the_practice_note_is_a_small_label_on_an_upright_phone(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    with at_size(driver, 390, 844, 2, True):
        resized(driver, 390, 844)
        on_loop(live, conn.send(a_hand_on_the_flop()))
        browser.wait_for(driver, "!document.getElementById('hd-note').hidden")
        note, dock = driver.execute_script(
            "return [document.getElementById('hd-note'), document.querySelector('#table .dock')]"
            ".map((node) => node.getBoundingClientRect().width)"
        )
        # Only as wide as its words, as at the other sizes, so it never looks like an empty text box
        assert note < dock / 2, (note, dock)
    assert not problems(driver)


def test_the_dock_counts_down_only_the_players_own_turn(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    # CPU Juno's turn, 20 seconds left: the time drains on Juno's seat, and the dock shows no clock
    on_loop(live, conn.send(a_hand_on_the_flop()))
    browser.wait_for(driver, "!document.getElementById('hd-ticks').hidden")
    time.sleep(1.2)
    assert text(driver, "clock") == ""
    # The player's own turn: the dock counts it down
    send_all(live, conn, my_turn())
    browser.wait_for(driver, "/^[0-9]+s$/.test(document.getElementById('clock').textContent)")
    assert not problems(driver)


def status_is(driver, words):
    try:
        browser.wait_for(driver, f"document.getElementById('status-text').textContent === {words!r}", timeout=15)
    except TimeoutException:
        raise AssertionError(f"the status line says {text(driver, 'status-text')!r}") from None


def status_matches(driver, pattern):
    """The status line comes to read as the pattern, whole: long ways of saying it shorten where the dock is narrow"""
    try:
        WebDriverWait(driver, 15).until(lambda _: re.fullmatch(pattern, text(driver, "status-text")))
    except TimeoutException:
        raise AssertionError(f"the status line says {text(driver, 'status-text')!r}") from None


def sent(live, conn, steps):
    """Sends the messages among these steps at the bot's own pace, so the page never falls far enough behind to skip
    events"""
    for step in steps:
        if "look" not in step:
            on_loop(live, conn.send(step))
            time.sleep(PACE.get(step.get("kind"), 0) if step["t"] == "event" else 0)


def test_the_dock_says_how_the_hand_ended(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    # Someone else wins at the showdown: their name and their hand
    sent(live, my_conn(live), a_hand_to_the_showdown())
    status_is(driver, "CPU Dex won with three of a kind, 7s")
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    sent(live, conn, a_hand_the_player_wins())
    status_matches(driver, r"You won 1,000 with two pair, (Aces and Sevens|As & Sevens)")
    # All in before the flop: the dock keeps saying so while the board runs out, then says the pot was split
    steps = an_all_in_split_after_a_run_out()
    show = steps.index(act(5, "return", 1940, 190)) + 1
    sent(live, conn, steps[:show])
    status_is(driver, "You're all in · Pair of Queens")
    sent(live, conn, steps[show:])
    lines = []
    for _ in range(120):
        lines.append(text(driver, "status-text"))
        if lines[-1].startswith("Split pot"):
            break
        time.sleep(0.1)
    assert lines[-1] == "Split pot: you won 1,955", lines[-5:]
    assert all(line.startswith("You're all in") for line in lines[:-1]), sorted(set(lines))
    assert not problems(driver)


def an_all_in_won_on_the_river():
    """Both all in before the flop, the player's pair of Queens against Juno's Jacks. The river's Queen makes the
    player three of a kind, and the table after it names the hands again, as the bot's does after every card"""
    steps = an_all_in_split_after_a_run_out()
    show = next(i for i, step in enumerate(steps) if step.get("kind") == "show")
    hands = {
        "0": {"cards": cards("Qh Qd"), "name": "Pair of Queens"},
        "5": {"cards": cards("Js Jc"), "name": "Pair of Jacks"},
    }
    board = cards("2c 7d 9h 3s Qc")
    seats = [
        seat_row(0, "Member", 0, me=True, in_hand=True, all_in=True),
        seat_row(1, "CPU Rosa", 1990, in_hand=True, folded=True),
        seat_row(2, "CPU Dex", 1930, in_hand=True, folded=True),
        None,
        seat_row(4, "CPU Mabel", 1980, in_hand=True, folded=True),
        seat_row(5, "CPU Juno", 190, in_hand=True, all_in=True),
    ]
    shown = {**hands, "0": {**hands["0"], "name": "Three of a kind, Queens"}}
    river = table_state(seats, phase="playing", hand=4, round=4, button=1, street="river", board=board, pots=[3910])
    win = {"amount": 3910, "winners": [0], "shares": {"0": 3910}}
    return [
        *steps[:show],
        event("show", hands=hands, pots=[3910]),
        *[event("runout", card=one) for one in board],
        {**river, "shown": shown},
        event("win", awards=[win], best={"0": cards("Qh Qd Qc 9h 7d")}, cut=0, big=True),
    ]


def test_after_a_run_out_the_dock_names_the_hand_the_last_cards_made(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    sent(live, conn, an_all_in_won_on_the_river())
    # The dock agrees with the hand's tag above it: the river made three Queens
    status_matches(driver, r"You won 3,910 with (three of a kind, Queens|trips Qs)")
    # The next hand's table comes without its button, as after a reconnect: the result goes with its hand
    seats = [seat_row(0, "Member", 3910, me=True), None, None, None, None, seat_row(5, "CPU Juno", 190)]
    on_loop(live, conn.send(table_state(seats, hand=5, round=5)))
    status_is(driver, "Next hand in a moment.")
    assert not problems(driver)


PRIYANKA = {"id": "9001", "name": "Priyanka", "cpu": False}


def watched(steps):
    """The same steps for someone without a seat: Priyanka has the player's seat, and no cards come to the page"""

    def seen(step):
        if step["t"] != "table":
            return step
        seats = [{**row, **PRIYANKA} if row and row["id"] == str(ME) else row for row in step["seats"]]
        return {**step, "seats": seats}

    return [seen(step) for step in steps if step.get("t") not in (None, "hole")]


def test_a_watcher_reads_how_the_hand_ended_until_the_next_hand(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    sent(live, conn, watched(a_hand_to_the_showdown()))
    status_is(driver, "CPU Dex won with three of a kind, 7s")
    # The next hand starts: the call to sit comes back
    on_loop(live, conn.send(event("button", seat=1)))
    status_is(driver, "Tap an empty seat to buy in.")
    assert not problems(driver)


def test_side_pots_are_not_called_a_split(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    shown = {
        "0": {"cards": cards("Ks Kd"), "name": "Pair of Kings"},
        "2": {"cards": cards("Qs Qd"), "name": "Pair of Queens"},
    }
    state = {**a_hand_on_the_flop(), "shown": shown}
    main = {"amount": 300, "winners": [0], "shares": {"0": 300}}
    side = {"amount": 500, "winners": [2], "shares": {"2": 500}}
    win = event("win", awards=[main, side], best={}, cut=0, big=False)
    sent(live, my_conn(live), [state, win])
    # The player won the main pot and CPU Dex a side pot: nobody split anything
    status_is(driver, "You won 300 with a pair of Kings")
    # Someone watching hears who won what
    open_casino(driver, live)
    walk_up(driver, "holdem")
    sent(live, my_conn(live), watched([state, win]))
    status_is(driver, "Priyanka won 300 and CPU Dex won 500")
    assert not problems(driver)


def renamed(steps, seat, name):
    """The same steps with this seat's player under another name"""

    def seen(step):
        if step["t"] != "table":
            return step
        return {
            **step,
            "seats": [{**row, "name": name} if row and row["seat"] == seat else row for row in step["seats"]],
        }

    return [seen(step) for step in steps]


# The status line's words, and whether they fit it whole
STATUS_FITS = """
const words = document.getElementById('status-text');
return { text: words.textContent, fits: words.scrollWidth <= words.clientWidth };
"""


def fitted_status(driver, pattern):
    """The status line at each size, once it has fitted its words to the dock: every one matches the pattern whole"""
    for name, (width, height, scale, mobile) in SIZES.items():
        with at_size(driver, width, height, scale, mobile):
            resized(driver, width, height)
            try:
                WebDriverWait(driver, 5).until(lambda _: driver.execute_script(STATUS_FITS)["fits"])
            except TimeoutException:
                raise AssertionError((name, driver.execute_script(STATUS_FITS))) from None
            line = driver.execute_script(STATUS_FITS)["text"]
            assert re.fullmatch(pattern, line), (name, line)


def test_a_long_name_or_hand_never_cuts_off_how_the_hand_ended(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    # Someone watching sees a player with a long name win: the name is cut by whole characters, never the words
    # saying how the hand ended, which shorten to poker's own short words only where even that won't fit
    sent(live, conn, renamed(watched(a_hand_to_the_showdown()), 2, "Priyanka Venkataraman-Holloway"))
    browser.wait_for(driver, "document.getElementById('status-text').textContent.includes(' won ')", timeout=15)
    fitted_status(driver, r"Priyanka Ve… won with (three of a kind, 7s|trips 7s)")
    # The player's own win with a long hand's name, at a sideways phone's narrow dock too
    sent(live, conn, an_all_in_won_on_the_river())
    browser.wait_for(driver, "document.getElementById('status-text').textContent.startsWith('You won')", timeout=15)
    fitted_status(driver, r"You won 3,910 with (three of a kind, Queens|trips Qs)")
    assert not problems(driver)


def test_two_winners_keep_their_names_recognisable(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    # Side pots won by two people: a short name stays whole and a long one keeps at least six letters; where even that
    # won't fit, the amounts go first
    sent(live, conn, renamed(renamed(others_take_the_side_pots(), 3, "Ann"), 4, "Manager"))
    browser.wait_for(driver, "document.getElementById('status-text').textContent.includes('Manager')", timeout=15)
    fitted_status(driver, r"Ann won 1,600 and Manager won 1,000|Ann and Manager split the pot")
    long = renamed(renamed(others_take_the_side_pots(), 3, "Bartholomew the Magnificent"), 4, "CPU Dex")
    sent(live, conn, long)
    browser.wait_for(driver, "document.getElementById('status-text').textContent.includes('Barth')", timeout=15)
    name = r"(Bartholomew the Magnificent|Bartholomew…|Bartholome…|Bartholom…|Bartholo…|Barthol…|Bartho…)"
    fitted_status(driver, name + r" (won 1,600 and CPU Dex won 1,000|and CPU Dex split the pot)")
    assert not problems(driver)


def test_after_a_reconnect_the_dock_says_whether_the_player_bet_or_raised(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    seats = [
        seat_row(0, "Member", 1940, me=True, in_hand=True, bet=60, last={"move": "raise", "amount": 60}),
        seat_row(1, "CPU Rosa", 1990, in_hand=True, bet=10, last={"move": "blind", "amount": 10}),
        seat_row(2, "CPU Dex", 1980, in_hand=True, bet=20, last={"move": "blind", "amount": 20}),
        None,
        None,
        None,
    ]
    # Back at the table after raising the big blind: the dock's first table says so
    on_loop(live, conn.send(table_state(seats, phase="playing", button=0, street="preflop", turn=1, left=20)))
    status_is(driver, "You raised to 60")
    # On the flop, the first chips in are a bet
    flop = [{**seats[0], "stack": 1880}, *({**row, "bet": 0, "last": None} for row in seats[1:3]), None, None, None]
    board = cards("Ah 7c 2d")
    on_loop(live, conn.send(table_state(flop, phase="playing", button=0, street="flop", board=board, pots=[150])))
    status_is(driver, "You bet 60")
    assert not problems(driver)


def test_a_top_up_left_open_closes_when_the_next_hand_starts(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    seats = [seat_row(0, "Member", 1500, me=True), seat_row(1, "CPU Rosa", 2000), None, None, None, None]
    on_loop(live, conn.send(table_state(seats, mode="real", hand=2)))
    browser.wait_for(driver, "!document.getElementById('hd-top-up').hidden")
    driver.find_element(By.ID, "hd-top-up").click()
    browser.wait_for(driver, "document.getElementById('hd-buyin').open")
    # The next hand starts: the Top up closes with its first event, before the hand's own table comes
    on_loop(live, conn.send(event("button", seat=1)))
    time.sleep(0.6)
    assert not is_open(driver, "hd-buyin")
    assert not problems(driver)


# The status line: how many lines its words take, and whether the clock shows on the same line as them
STATUS_LINE = """
const range = document.createRange();
range.selectNodeContents(document.getElementById('status-text'));
const tops = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((rect) => Math.round(rect.top)));
const words = document.getElementById('status-text').getBoundingClientRect();
const clock = document.getElementById('clock').getBoundingClientRect();
const middle = (clock.top + clock.bottom) / 2;
return { lines: tops.size, clock: clock.width > 0 && middle > words.top && middle < words.bottom };
"""


def test_a_long_status_stays_one_line_with_its_clock(driver, live):
    open_casino(driver, live)
    walk_up(driver, "holdem")
    conn = my_conn(live)
    hole = {"t": "hole", "game": "holdem", "hand": 3, "cards": cards("Qs Qd"), "name": "Full house, Queens over Sevens"}
    send_all(live, conn, [a_hand_on_the_flop(), hole, *my_turn()])
    browser.wait_for(driver, "/^[0-9]+s$/.test(document.getElementById('clock').textContent)")
    for name, (width, height, scale, mobile) in SIZES.items():
        with at_size(driver, width, height, scale, mobile):
            resized(driver, width, height)
            assert driver.execute_script(STATUS_LINE) == {"lines": 1, "clock": True}, name
    assert not problems(driver)


def a_cut_taken_to_the_tray():
    """The hand to the showdown, CPU Dex winning, the house taking 52"""
    win = {"amount": 968, "winners": [2], "shares": {"2": 968}}
    return showdown_won([win], {"2": cards("7h 7d 7c As Ks")}, 52)


# While the steps after it play: how long the "House" label stays fully shown, and where the cut's chips were last
CUT_WATCH = """
window.cut = { shown: null, fading: null, pile: null, last: null };
const look = () => {
  const fx = scene.layers.fx.children;
  const house = fx.find((node) => node.words && /^House/.test(node.words.text));
  const now = performance.now();
  if (house && window.cut.shown === null) {
    window.cut.shown = now;
    window.cut.pile = fx[fx.indexOf(house) - 1];
  }
  if (house && house.alpha < 1 && window.cut.fading === null) {
    window.cut.fading = now;
  }
  const pile = window.cut.pile;
  if (pile && !pile.destroyed && pile.parent) {
    window.cut.last = { x: pile.x, y: pile.y };
  }
  if (window.cut.fading === null || (pile && !pile.destroyed && pile.parent)) {
    requestAnimationFrame(look);
  }
};
requestAnimationFrame(look);
return true;
"""
CUT_SEEN = """
const { shown, fading, last } = window.cut;
const tray = scene.dealerPoint();
return { held: fading - shown, reach: Math.hypot(last.x - tray.x, last.y - tray.y), k: scene.plan.k };
"""


def test_the_cut_shows_its_label_a_second_and_its_chips_end_in_the_tray(driver, live):
    open_casino(driver, live)
    steps = a_cut_taken_to_the_tray()
    show = next(i for i, step in enumerate(steps) if step.get("kind") == "show")
    for size in ((900, 600), (390, 700)):
        run = [*steps[: show + 1], {"run": "watch", "js": CUT_WATCH}, *steps[show + 1 :], {"wait": 1600}]
        cut = run_steps(driver, [*run, {"run": "cut", "js": CUT_SEEN}], size=size)["cut"]
        # "House 52" holds about a second before it fades, and the chips stop at the dealer's tray
        assert 850 <= cut["held"] <= 1300, (size, cut)
        assert cut["reach"] <= 2 * cut["k"], (size, cut)
    assert not problems(driver)
