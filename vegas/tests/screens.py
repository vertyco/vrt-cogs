"""Screenshots of the casino for checking art by eye. Not collected with the tests; run it by name:

    pytest vegas/tests/screens.py -k war

It saves the lobby and each game's table (waiting, mid-round, and with its result) at desktop, upright phone
and sideways phone sizes, to the folder in the VEGAS_SHOTS environment variable (default: ./vegas-shots). The
discord-phone and discord-sideways sizes are the game's frame inside Discord's phone app on a small phone, with the
edges Discord asks to keep clear: `-k discord` takes only those.

Slots picks a bet of 100 and pulls the lever hard and fast, on reels rigged to land 7-7-7, so the result is the
jackpot's celebration.

All In shows the wheel at x2 and at x200 (the thinnest slice), then spins twice with no cooldown: a win at x200, shot
mid-spin and after, then a loss at x3.

`-k menu_scenario` takes the polish rounds of the game-card menu, Slots and All In (MENU_SCENARIOS), each a numbered
set of moments at each size: the menu empty, with an 8-digit balance, then crowded (faces with "+N" at every game, War
closed, a crowd in the lobby) at its top and scrolled to its end; Slots waiting, mid-spin, a small win, three bells with their
coin shower and the jackpot at the height of its show; All In as above; and House rules at the Slots pay table

Texas Hold'em gets whole hands instead, each a folder of numbered frames at each size, played at real speed through
the bot's real table: `-k holdem` takes a free practice hand against the real CPUs, a real hand against a second
player, a split pot then an all in run-out with a big pot, another player's turn running down and a reload mid-hand,
a watcher's view, a buy-in offer on the player's own turn, side pots between three players, and the House rules
chart
"""

import asyncio
import os
import threading
import time
from pathlib import Path

import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

from vegas.common.catalog import GAMES
from vegas.tests import test_browser
from vegas.tests.fakes import FakeConn, FakeRoom
from vegas.tests.tables_kit import Rigged
from vegas.tests.test_browser import QUICK_MOVE, browser, fakes, guest, on_loop, open_casino, problems, walk_up
from vegas.tests.test_holdem_page import ME, Caller, bar_up, card, cards, sit_guest, strip_up, tap_seat, ticks_shown
from vegas.tests.test_solo_page import lever_ready, pick_bet, pull_lever

driver = test_browser.driver
live = test_browser.live
SIZES = {
    "desktop": (1280, 800, 1, False),
    "phone": (390, 844, 2, True),
    "sideways": (844, 390, 2, True),
    # The game's frame inside Discord's Android app on a 360-wide phone: the frame under Discord's top bar, and the
    # edges Discord says to keep clear (the navigation bar upright; the top and the camera's notch sideways)
    "discord-phone": (360, 701, 3, True),
    "discord-sideways": (670, 361, 3, True),
}
INSETS = {"discord-phone": {"bottom": 48}, "discord-sideways": {"top": 30, "left": 33}}
# The page scripts that set a size's insets, removed when the size is cleared
INSET_SCRIPTS = []
# The second real player's seat in the real hand
GUEST_SEAT = 4
# Two decks stacked for one session: A-K against A-K splits the pot, then Kings catch a third King on the river
# against Aces after both go all in
SPLIT = ({0: cards("Ac Kd"), GUEST_SEAT: cards("Ad Ks")}, cards("Qs Jc 7h 4d 2s"))
ALL_IN = ({0: cards("Ks Kh"), GUEST_SEAT: cards("As Ad")}, cards("7c 2d 9h Jc") + [card("Kd")])
# Three hands for the side pot: Ann (seat 2) has Aces, Manager Kings, the player Queens, on a board that helps nobody
SIDE_POT = ({0: cards("Qs Qh"), 2: cards("Ac Ah"), GUEST_SEAT: cards("Kc Kd")}, cards("2c 7d 9h Js 3s"))


def folder() -> Path:
    path = Path(os.environ.get("VEGAS_SHOTS", "vegas-shots"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def shoot(chrome, name: str) -> None:
    path = folder() / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    chrome.switch_to.default_content()
    chrome.save_screenshot(str(path))
    chrome.switch_to.frame(chrome.find_element(By.ID, "game-frame"))


def pause(chrome, ms: int) -> None:
    chrome.execute_script(f"return new Promise((resolve) => setTimeout(resolve, {ms}))")


# ---------- Texas Hold'em ----------


def holdem_table(live):
    """The window's Hold'em table as players get it, real speed and real CPUs, and every event it sends with the
    moment it was sent"""
    events = []

    async def make():
        table = live.cog.floors["i-1"].table("holdem")
        send = table.event

        async def event(kind, **data):
            events.append({"kind": kind, "at": time.monotonic(), **data})
            await send(kind, **data)

        table.event = event
        return table

    return on_loop(live, make()), events


def board_after(board: int, event: dict) -> int:
    """How many shared cards are out once this event has played"""
    if event["kind"] == "button":
        return 0
    if event["kind"] == "flop":
        return board + 3
    if event["kind"] in ("street", "runout"):
        return board + 1
    return board


def street_of(board: int) -> str:
    return {3: "flop", 4: "turn", 5: "river"}.get(board, "preflop")


def nth(kind: str, count: int, **match):
    """Passes on the count-th event of this kind with these values"""
    found = []

    def test(event, street):
        if event["kind"] == kind and all(event.get(key) == value for key, value in match.items()):
            found.append(event)
            return len(found) == count
        return False

    return test


def on_street(street: str, kind: str, **match):
    """Passes on the first event of this kind with these values once the board is at this street"""

    def test(event, now):
        return now == street and event["kind"] == kind and all(event.get(key) == value for key, value in match.items())

    return test


def watch(chrome, table, events, start, shots, on_turn, end) -> int:
    """Plays the page's turns with on_turn(street) and takes each shot (frame name, test(event, street), ms after the
    event, and an optional thing to do on the page first) once its event has come, from event number `start` until an
    event passing `end` has come and every shot due is taken. Returns the number of events seen. Shots whose event
    never came are printed, not taken"""
    waiting, due, seen, board, ended = list(shots), [], start, 0, False
    deadline = time.monotonic() + 240
    while not ended or due:
        assert time.monotonic() < deadline, "the hand never finished"
        while seen < len(events):
            event = events[seen]
            seen += 1
            board = board_after(board, event)
            for shot in [shot for shot in waiting if shot[1](event, street_of(board))]:
                waiting.remove(shot)
                due.append((event["at"] + shot[2] / 1000, shot))
            ended = ended or end(event, street_of(board))
        for when, shot in sorted(due, key=lambda item: item[0]):
            if when > time.monotonic():
                break
            due.remove((when, shot))
            if len(shot) > 3:
                shot[3](chrome)
            shoot(chrome, shot[0])
        if bar_up(chrome):
            on_turn(table.street)
        time.sleep(0.02)
    for shot in waiting:
        print(f"never taken: {shot[0]}")
    return seen


def press(chrome, element_id: str) -> None:
    chrome.find_element(By.ID, element_id).click()


def pick_half_pot(chrome) -> bool:
    """Sets the raise to half the pot. False when the bar has no raise"""
    if not chrome.find_element(By.ID, "hd-raise").is_displayed():
        return False
    chrome.find_element(By.CSS_SELECTOR, '#hd-sizes [data-size="half"]').click()
    return True


def tick_call_any(chrome) -> None:
    if ticks_shown(chrome):
        chrome.find_element(By.CSS_SELECTOR, '#hd-ticks [data-advance="call_any"]').click()


def practice_hand(chrome, live, name: str) -> None:
    """Alone at the table: sit for free, the CPUs arrive, the deal, the bar with a half-pot raise picked (then a call,
    so the CPUs stay in), Call any ticked on the flop, then check or call to the showdown and the win"""
    table, events = holdem_table(live)
    walk_up(chrome, "holdem")
    pause(chrome, 600)
    shoot(chrome, f"{name}/01-empty-table")
    turns = []

    def turn(street):
        turns.append(street)
        if len(turns) == 1 and pick_half_pot(chrome):
            shoot(chrome, f"{name}/04-your-turn")
            press(chrome, "hd-call")
            # The bar gives way to the move in words before the bot answers, and the chips slide out
            pause(chrome, 120)
            shoot(chrome, f"{name}/05-call-sent")
            return
        press(chrome, "hd-call")

    tap_seat(chrome, 0, lambda: table.seat_of(ME) is not None)
    shots = [
        (f"{name}/02-cpus-arrive", nth("seat", 1, seat=1), 200),
        (f"{name}/03-deal", nth("pitch", 5), 150),
        (f"{name}/06-flop-call-any-ticked", nth("flop", 1), 1250, tick_call_any),
        (f"{name}/07-turn", on_street("turn", "street"), 900),
        (f"{name}/08-river", on_street("river", "street"), 900),
        (f"{name}/09-showdown", nth("show", 1), 900),
        (f"{name}/10-win", nth("win", 1), 450),
        (f"{name}/11-won", nth("win", 1), 1750),
    ]
    watch(chrome, table, events, 0, shots, turn, nth("win", 1))
    assert not problems(chrome)


def real_hand(chrome, live, name: str) -> None:
    """A practicer and a second real player: the practicer's buy-in offer mid-hand, the CPUs leaving, the deal, a
    half-pot bet on every street that the other player calls, the showdown, and the win with the casino's cut"""
    table, events = holdem_table(live)
    walk_up(chrome, "holdem")
    tap_seat(chrome, 0, lambda: table.seat_of(ME) is not None)
    # Once the practicer is dealt in, the second player buys in, so the offer comes as the strip in the dock
    watch(chrome, table, events, 0, [], lambda street: None, nth("pitch", 8))
    pause(chrome, 600)
    sit_guest(live, fakes.MANAGER_ID, GUEST_SEAT, buy_in=1000)
    browser.wait_for(chrome, "!document.getElementById('hd-offer').hidden", timeout=15)
    for _ in range(50):
        if strip_up(chrome):
            break
        time.sleep(0.05)
    shoot(chrome, f"{name}/01-buy-in-offer")
    press(chrome, "hd-buyin-yes")

    def practice_turn(street):
        # Fold stays in place but greyed while a check is free
        press(chrome, "hd-fold" if chrome.find_element(By.ID, "hd-fold").is_enabled() else "hd-call")

    # The practice hand plays out with the practicer folded, then the CPUs leave for the real game
    # The table without the CPUs comes just before their first unseat, and they fade out as it arrives
    leaving = [(f"{name}/02-cpus-leave", nth("unseat", 1), 150)]
    seen = watch(chrome, table, events, 0, leaving, practice_turn, nth("unseat", 1))
    frames = {"preflop": "05-preflop-raise", "flop": "06-flop-bet", "river": "08-river-bet"}

    def turn(street):
        if not pick_half_pot(chrome):
            press(chrome, "hd-call")
            return
        if street in frames:
            shoot(chrome, f"{name}/{frames.pop(street)}")
        press(chrome, "hd-raise")

    shots = [
        (f"{name}/03-real-game-seated", nth("button", 1), 250),
        (f"{name}/04-deal", nth("pitch", 3), 150),
        (f"{name}/07-turn-call", on_street("turn", "act", seat=GUEST_SEAT, move="call"), 300),
        (f"{name}/09-showdown", nth("show", 1), 900),
        (f"{name}/10-cut", nth("win", 1), 300),
        (f"{name}/11-won", nth("win", 1), 1750),
    ]
    watch(chrome, table, events, seen, shots, turn, nth("win", 1))
    assert not problems(chrome)


class Thinker(Caller):
    """Someone else at the table who calls or checks after thinking: each question waits the next of `waits` seconds
    (none once they run out). Keeps the moment each question came"""

    def __init__(self, room, who, guild, cog, waits):
        super().__init__(room, who, guild, cog)
        self.waits = list(waits)
        self.asked = []

    async def send(self, data):
        await FakeConn.send(self, data)
        if data.get("t") == "ask" and data.get("game") == "holdem":
            self.asked.append(time.monotonic())
            move = "call" if "call" in data["moves"] else "check"
            asyncio.get_running_loop().create_task(self.answer(move, self.waits.pop(0) if self.waits else 0))

    async def answer(self, move, wait):
        await asyncio.sleep(wait)
        await self.cog.message(self.ctx, self, {"t": "move", "move": move})


def newcomer(live, user_id: int, name: str | None = None, kind=FakeConn, **extra):
    """A connection for someone else in the window: a watcher (FakeConn), a Caller or a Thinker"""
    floor = live.cog.floors["i-1"]
    return kind(FakeRoom("i-1"), guest(live, user_id, name), floor.guild, **extra)


def come_to_table(live, conn, seat: int | None = None, buy_in: int = 1000):
    """`conn` walks up to the Hold'em table and buys in at this seat, or only watches with no seat"""

    async def arrive():
        floor = live.cog.floors["i-1"]
        floor.where[conn] = None
        await floor.enter(conn, "holdem")
        if seat is not None:
            message = {"t": "buy_in", "seat": seat, "amount": buy_in, "post": False}
            await live.cog.message(conn.ctx, conn, message)

    on_loop(live, arrive())
    return conn


def hold_hands(table, gate) -> None:
    """No hand is dealt until `gate` (a threading.Event) opens"""
    prepare = table.prepare

    async def held():
        await asyncio.to_thread(gate.wait, 60)
        return await prepare()

    table.prepare = held


def stack_decks(table, hands) -> None:
    """The next hands get these decks, in order: each is (two cards for each seat, the five shared cards). The bot
    deals them in its own order, from the small blind round, then the board"""
    waiting = list(hands)
    shuffled = table.new_deck

    def new_deck():
        if not waiting:
            return shuffled()
        holes, board = waiting.pop(0)
        spots = table.hand.spots
        first = spots.dealt.index(spots.small)
        order = spots.dealt[first:] + spots.dealt[:first]
        draws = [tuple(holes[seat][0]) for seat in order] + [tuple(holes[seat][1]) for seat in order]
        draws += [tuple(each) for each in board]
        deck = shuffled()
        deck.cards = [each for each in deck.cards if each not in draws] + draws[::-1]
        return deck

    table.new_deck = new_deck


def start_real_game(chrome, live, table, other) -> None:
    """The page's player sits free, `other` buys in, the player takes the bot's offer between hands, and only then is
    the first hand dealt: a real game with no practice hand first"""
    gate = threading.Event()
    hold_hands(table, gate)
    try:
        tap_seat(chrome, 0, lambda: table.seat_of(ME) is not None)
        come_to_table(live, other, GUEST_SEAT)
        browser.wait_for(chrome, "document.getElementById('hd-buyin').open", timeout=15)
        press(chrome, "hd-buyin-yes")
        WebDriverWait(chrome, 10).until(lambda _: table.seat_of(ME).real > 0)
    finally:
        gate.set()


def play_until(chrome, on_turn, done, timeout: float = 120.0) -> None:
    """Plays the page's turns with on_turn(None) until done() is true"""
    deadline = time.monotonic() + timeout
    while not done():
        assert time.monotonic() < deadline, "the table never got there"
        if bar_up(chrome):
            on_turn(None)
        time.sleep(0.05)


def shoot_at(chrome, when: float, name: str) -> None:
    time.sleep(max(0.0, when - time.monotonic()))
    shoot(chrome, name)


def won(events):
    return lambda: any(event["kind"] == "win" for event in events)


def split_then_all_in(chrome, live, name: str) -> None:
    """Two real hands with stacked decks: half-pot bets called down to a split pot, then the player all in before the
    flop, called, both hands up, the board run out one card at a time, and a pot of about 100 big blinds"""
    table, events = holdem_table(live)
    stack_decks(table, [SPLIT, ALL_IN])
    walk_up(chrome, "holdem")
    start_real_game(chrome, live, table, newcomer(live, fakes.MANAGER_ID, kind=Caller, cog=live.cog))

    def turn(street):
        if table.hand_no >= 2:
            chrome.find_element(By.CSS_SELECTOR, '#hd-sizes [data-size="all"]').click()
            shoot(chrome, f"{name}/04-all-in-picked")
            press(chrome, "hd-raise")
        elif pick_half_pot(chrome):
            press(chrome, "hd-raise")
        else:
            press(chrome, "hd-call")

    shots = [
        (f"{name}/01-split-showdown", nth("show", 1), 900),
        (f"{name}/02-split-pot-divides", nth("win", 1), 450),
        (f"{name}/03-split-settled", nth("win", 1), 1750),
        (f"{name}/05-all-in-hands-up", nth("show", 2), 900),
        (f"{name}/06-run-out-flop", nth("runout", 2), 350),
        # The river's run-out holds, slides and turns over in about 1.25 s on the page, which plays about 0.25 s
        # behind the bot, and the win comes 1.6 s after the run-out
        (f"{name}/07-run-out-river", nth("runout", 5), 1620),
        (f"{name}/08-big-pot-celebration", nth("win", 2), 750),
        (f"{name}/09-big-pot-settled", nth("win", 2), 1750),
    ]
    watch(chrome, table, events, 0, shots, turn, nth("win", 2))
    assert not problems(chrome)


def turn_and_reconnect(chrome, live, name: str) -> None:
    """A real hand against someone who thinks: their clock ring drains green, amber and red, they call just in time;
    on the flop, while they think again, the page reloads and walks back up to the table"""
    table, events = holdem_table(live)
    walk_up(chrome, "holdem")
    other = newcomer(live, fakes.MANAGER_ID, kind=Thinker, cog=live.cog, waits=[32, 20])
    start_real_game(chrome, live, table, other)

    def call(street):
        press(chrome, "hd-call")

    play_until(chrome, call, lambda: other.asked)
    for seconds, frame in ((3, "01-their-turn"), (26.5, "02-their-turn-amber"), (31, "03-their-turn-red")):
        shoot_at(chrome, other.asked[0] + seconds, f"{name}/{frame}")
    play_until(chrome, call, lambda: len(other.asked) >= 2)
    time.sleep(max(0.0, other.asked[1] + 2 - time.monotonic()))
    open_casino(chrome, live, balance="0")
    walk_up(chrome, "holdem")
    shoot(chrome, f"{name}/04-reconnected")
    pause(chrome, 1000)
    shoot(chrome, f"{name}/05-reconnected-a-second-later")
    play_until(chrome, call, won(events))
    assert not problems(chrome)


def watching(chrome, live, name: str) -> None:
    """The page's player only watches a real hand between two others, with five more people watching. The first to
    arrive has a long name, so it is the first entry after the player's own in the people row"""
    table, events = holdem_table(live)
    gate = threading.Event()
    hold_hands(table, gate)
    try:
        for user_id, seat, who in ((201, 1, "Priyanka Venkataraman-Holloway"), (202, GUEST_SEAT, "Marcus")):
            come_to_table(live, newcomer(live, user_id, who, kind=Caller, cog=live.cog), seat)
        for user_id, who in ((203, "Ana"), (204, "Jules"), (205, "Kenji"), (206, "Omar"), (207, "Sofia")):
            come_to_table(live, newcomer(live, user_id, who))
        walk_up(chrome, "holdem")
        pause(chrome, 800)
        shoot(chrome, f"{name}/01-watchers-before-the-deal")
    finally:
        gate.set()
    shots = [
        (f"{name}/02-deal", nth("pitch", 3), 150),
        (f"{name}/03-flop", nth("flop", 1), 1300),
        (f"{name}/04-showdown", nth("show", 1), 900),
        (f"{name}/05-won", nth("win", 1), 1750),
    ]
    watch(chrome, table, events, 0, shots, lambda street: None, nth("win", 1))
    assert not problems(chrome)


def offer_on_your_turn(chrome, live, name: str) -> None:
    """Practicing alone: on the player's own turn, with the action bar up, a second person buys in and the bot offers
    the player a real buy-in. The player thinks a few seconds, then calls, and the offer comes back with its clock
    started over"""
    table, events = holdem_table(live)
    walk_up(chrome, "holdem")
    tap_seat(chrome, 0, lambda: table.seat_of(ME) is not None)
    browser.wait_for(chrome, "document.getElementById('hd-bar').classList.contains('up')", timeout=30)
    WebDriverWait(chrome, 5).until(lambda _: bar_up(chrome))
    come_to_table(live, newcomer(live, fakes.MANAGER_ID, kind=Caller, cog=live.cog), GUEST_SEAT)
    # The strip waits out of sight while the bar is up, so the offer's title is the sign it came
    browser.wait_for(chrome, "document.getElementById('hd-buyin-title').textContent.startsWith('A real game')")
    pause(chrome, 400)
    shoot(chrome, f"{name}/01-offer-on-your-turn")
    # Long enough that a clock left running would read about 30 s once the strip is back
    pause(chrome, 4000)
    press(chrome, "hd-call")
    moved = time.monotonic()
    pause(chrome, 600)
    shoot(chrome, f"{name}/02-after-your-move")
    WebDriverWait(chrome, 10).until(lambda _: strip_up(chrome))
    shoot_at(chrome, moved + 1.6, f"{name}/03-offer-back-fresh-clock")
    # One step of the slider past the player's balance of 1,000
    chrome.execute_script(PAST_BALANCE)
    pause(chrome, 300)
    shoot(chrome, f"{name}/04-offer-past-balance")
    assert not problems(chrome)


# Moves the buy-in slider one step up, the way a finger dragging it would
PAST_BALANCE = """
const slider = document.getElementById('hd-buyin-slider');
slider.value = String(Number(slider.value) + 1);
slider.dispatchEvent(new Event('input', { bubbles: true }));
"""


def side_pot(chrome, live, name: str) -> None:
    """Three real players on a stacked deck: the player and Manager buy in for 1,000, Ann for 400. The player goes all
    in before the flop and both call, so Ann's 400 makes a main pot and the rest a side pot. Ann's Aces win the main
    pot, Manager's Kings beat the player's Queens for the side pot"""
    table, events = holdem_table(live)
    stack_decks(table, [SIDE_POT])
    walk_up(chrome, "holdem")
    gate = threading.Event()
    hold_hands(table, gate)
    try:
        tap_seat(chrome, 0, lambda: table.seat_of(ME) is not None)
        come_to_table(live, newcomer(live, fakes.MANAGER_ID, kind=Caller, cog=live.cog), GUEST_SEAT)
        come_to_table(live, newcomer(live, 301, "Ann", kind=Caller, cog=live.cog), 2, buy_in=400)
        browser.wait_for(chrome, "document.getElementById('hd-buyin').open", timeout=15)
        press(chrome, "hd-buyin-yes")
        WebDriverWait(chrome, 10).until(lambda _: table.seat_of(ME).real > 0)
    finally:
        gate.set()

    def turn(street):
        chrome.find_element(By.CSS_SELECTOR, '#hd-sizes [data-size="all"]').click()
        press(chrome, "hd-raise")

    shots = [
        # The bets slide into a main and a side pot as the hands turn up, before the board runs out
        (f"{name}/00-pots-split", nth("show", 1), 350),
        (f"{name}/01-side-pot-hands-up", nth("show", 1), 900),
        (f"{name}/02-side-pots-pushed", nth("win", 1), 500),
        (f"{name}/03-side-pots-settled", nth("win", 1), 1750),
    ]
    watch(chrome, table, events, 0, shots, turn, nth("win", 1))
    assert not problems(chrome)


# Scrolls the House rules panel so this part of it is in view: the first match, or the one with these words
SCROLL_TO = """
const [selector, block, words] = arguments;
const nodes = [...document.querySelectorAll(selector)];
const node = words ? nodes.find((each) => each.textContent === words) : nodes[0];
node.scrollIntoView({ block });
"""


def house_rules(chrome, live, name: str) -> None:
    """The House rules panel: Hold'em's rules, then the top and the bottom of the hand rankings chart"""
    chrome.find_element(By.ID, "open-rules").click()
    browser.wait_for(chrome, "document.querySelectorAll('#panel-body .rank-chart li').length > 0")
    for frame, selector, block, words in (
        ("01-holdem-rules", "#panel-body h4", "start", "Texas Hold'em"),
        ("02-rankings-top", "#panel-body .rank-chart", "start", None),
        ("03-rankings-bottom", "#panel-body .rank-chart li:last-child", "end", None),
    ):
        chrome.execute_script(SCROLL_TO, selector, block, words)
        pause(chrome, 300)
        shoot(chrome, f"{name}/{frame}")
    assert not problems(chrome)


SCENARIOS = {
    "split-allin": split_then_all_in,
    "turn-reconnect": turn_and_reconnect,
    "watching": watching,
    "offer-turn": offer_on_your_turn,
    "side-pot": side_pot,
    "rules": house_rules,
}


def play_slots(chrome, name: str) -> None:
    """A bet of 100, then a quick hard pull of the lever: the reels mid-spin, then the result"""
    pick_bet(chrome, 100)
    lever_ready(chrome)
    shoot(chrome, f"{name}-1-waiting")
    pull_lever(chrome, 150)
    pause(chrome, 900)
    shoot(chrome, f"{name}-2-playing")
    browser.wait_for(chrome, "!document.getElementById('result').hidden", timeout=15)
    pause(chrome, 900)
    shoot(chrome, f"{name}-3-result")


def set_multiplier(chrome, value: int) -> None:
    chrome.execute_script(
        "const box = document.getElementById('mult-value');"
        "box.value = String(arguments[0]);"
        "box.dispatchEvent(new Event('input'));",
        value,
    )


def spin_all_in(chrome) -> None:
    browser.wait_for(chrome, "!document.getElementById('place').disabled && !document.getElementById('place').hidden")
    chrome.find_element(By.ID, "place").click()
    browser.wait_for(chrome, "document.getElementById('confirm').open")
    chrome.find_element(By.ID, "confirm-yes").click()


def play_all_in(chrome, name: str) -> None:
    """The wheel at x2 and x200, then a win at x200 (mid-spin and after) and a loss at x3"""
    browser.wait_for(chrome, "document.querySelector('#scene canvas') !== null")
    pause(chrome, 900)
    shoot(chrome, f"{name}-1-x2")
    set_multiplier(chrome, 200)
    pause(chrome, 600)
    shoot(chrome, f"{name}-2-x200")
    spin_all_in(chrome)
    pause(chrome, 1000)
    shoot(chrome, f"{name}-3-spinning")
    browser.wait_for(chrome, "!document.getElementById('result').hidden", timeout=15)
    pause(chrome, 450)
    shoot(chrome, f"{name}-4-win")
    browser.wait_for(chrome, "document.getElementById('result').hidden", timeout=15)
    set_multiplier(chrome, 3)
    spin_all_in(chrome)
    browser.wait_for(chrome, "!document.getElementById('result').hidden", timeout=15)
    pause(chrome, 350)
    shoot(chrome, f"{name}-5-lose")


# ---------- The menu, Slots and All In ----------

# How many made-up people stand at each game's table on the crowded menu, and the names they take in turn
CROWD = {
    "holdem": 6,
    "blackjack": 4,
    "craps": 2,
    "slots": 5,
    "allin": 1,
    "war": 2,
    "hilo": 3,
    "double": 7,
    "coin": 2,
    "cups": 1,
    "dice": 9,
}
CROWD_NAMES = ["Ann", "Marcus", "Priyanka Venkataraman", "Jules", "Kenji", "Omar", "Sofia", "Lucia", "Bo"]


def mouse_off_the_cards(chrome) -> None:
    """Headless Chrome leaves its mouse where it last clicked, which can hover-lift a card: it goes to the title"""
    ActionChains(chrome).move_to_element(chrome.find_element(By.ID, "casino-name")).perform()


async def crowd_in(live, counts: dict, standing: int) -> None:
    """Made-up people: `counts` at each game's table and `standing` in the lobby, then everyone is told"""
    floor = live.cog.floors["i-1"]
    spots = [spot for spot, count in counts.items() for _ in range(count)] + [None] * standing
    for number, spot in enumerate(spots):
        who = guest(live, 500 + number, CROWD_NAMES[number % len(CROWD_NAMES)])
        floor.where[FakeConn(FakeRoom("i-1"), who, floor.guild)] = spot
    await floor.send_lobby()


def menu_empty(chrome, live, name: str) -> None:
    """The menu with only the player in the window"""
    open_casino(chrome, live)
    mouse_off_the_cards(chrome)
    pause(chrome, 800)
    shoot(chrome, f"{name}-1-top")


def menu_rich(chrome, live, name: str) -> None:
    """The menu for a player with an 8-digit balance, which must keep clear of the casino's name"""
    live.cog.bank.balances[fakes.MEMBER_ID] = 40_000_000
    open_casino(chrome, live, balance="40,000,000")
    mouse_off_the_cards(chrome)
    pause(chrome, 800)
    shoot(chrome, f"{name}-1-top")


def menu_crowded(chrome, live, name: str) -> None:
    """People at every game, so the cards show up to 3 faces then "+N", War closed, and a crowd in the lobby: the top
    of the menu, then the menu scrolled to its end"""
    on_loop(live, live.cog.store.save_game(fakes.GUILD_ID, "war", is_open=False))
    open_casino(chrome, live)
    on_loop(live, crowd_in(live, CROWD, 11))
    faces = sum(min(3, count) for count in CROWD.values())
    browser.wait_for(chrome, f"document.querySelectorAll('.game-card .faces .face').length === {faces}")
    browser.wait_for(chrome, "document.querySelectorAll('.lobby-crowd .face').length === 8")
    mouse_off_the_cards(chrome)
    pause(chrome, 800)
    shoot(chrome, f"{name}-1-top")
    chrome.execute_script("const lobby = document.getElementById('lobby'); lobby.scrollTop = lobby.scrollHeight;")
    pause(chrome, 400)
    shoot(chrome, f"{name}-2-end")


def pull_for(chrome, words: str) -> None:
    """Pulls the lever and waits for the result card to start with these words"""
    pull_lever(chrome, 150)
    browser.wait_for(chrome, f"document.getElementById('result-big').textContent.startsWith('{words}')", timeout=15)


def slots_moments(chrome, live, name: str) -> None:
    """A bet of 100, then three hard pulls on rigged reels: two cherries (a small win, shot mid-spin and after), three
    bells (14 times the bet, with its coin shower) and 7-7-7 (the jackpot, shot at the height of its show)"""
    live.cog.rng = Rigged(ints=[2, 13, 4, 3, 6, 10, 0, 0, 0])
    open_casino(chrome, live)
    walk_up(chrome, "slots")
    pick_bet(chrome, 100)
    lever_ready(chrome)
    pause(chrome, 300)
    shoot(chrome, f"{name}-1-waiting")
    pull_lever(chrome, 150)
    pause(chrome, 900)
    shoot(chrome, f"{name}-2-spinning")
    browser.wait_for(chrome, "document.getElementById('result-big').textContent === 'You win 300'", timeout=15)
    pause(chrome, 900)
    shoot(chrome, f"{name}-3-small-win")
    pull_for(chrome, "You win 1,400")
    pause(chrome, 500)
    shoot(chrome, f"{name}-4-bells-win")
    pull_for(chrome, "Jackpot!")
    pause(chrome, 1300)
    shoot(chrome, f"{name}-5-jackpot")


def all_in_moments(chrome, live, name: str) -> None:
    """The wheel at x2 and x200, then a win at x200 (mid-spin and after) and a loss at x3, with no cooldown"""
    live.cog.rng = Rigged(ints=[0, 1])
    on_loop(live, live.cog.store.save_game(fakes.GUILD_ID, "allin", cooldown=0))
    open_casino(chrome, live)
    walk_up(chrome, "allin")
    play_all_in(chrome, name)


def slots_rules(chrome, live, name: str) -> None:
    """House rules opened at Slots, scrolled to the Slots pay table"""
    open_casino(chrome, live)
    walk_up(chrome, "slots")
    chrome.find_element(By.ID, "open-rules").click()
    browser.wait_for(chrome, "document.querySelectorAll('#panel-body .pay-chart li').length > 0")
    chrome.execute_script(SCROLL_TO, "#panel-body h4", "start", "Pay table")
    pause(chrome, 300)
    shoot(chrome, f"{name}-1-pay-table")


MENU_SCENARIOS = {
    "menu-empty": menu_empty,
    "menu-rich": menu_rich,
    "menu-crowded": menu_crowded,
    "slots": slots_moments,
    "allin": all_in_moments,
    "rules-slots": slots_rules,
}


def play_to_result(chrome, game: str, name: str) -> None:
    if game == "slots":
        play_slots(chrome, name)
        return
    if game == "allin":
        play_all_in(chrome, name)
        return
    if game == "blackjack":
        chrome.find_element(By.ID, "sit").click()
        browser.wait_for(chrome, "!document.getElementById('stand').hidden")
    choices = chrome.find_elements(By.CSS_SELECTOR, "#choices button")
    if choices:
        choices[0].click()
    browser.wait_for(chrome, "!document.getElementById('place').disabled && !document.getElementById('place').hidden")
    shoot(chrome, f"{name}-1-waiting")
    chrome.find_element(By.ID, "place").click()
    pause(chrome, 700)
    shoot(chrome, f"{name}-2-playing")
    for _ in range(120):
        if chrome.execute_script("return !document.getElementById('result').hidden"):
            break
        move = QUICK_MOVE.get(game)
        buttons = chrome.find_elements(By.CSS_SELECTOR, f'#moves [data-move="{move}"]') if move else []
        if buttons and buttons[0].is_displayed():
            buttons[0].click()
        pause(chrome, 250)
    shoot(chrome, f"{name}-3-result")


def set_size(chrome, size: str) -> None:
    width, height, scale, mobile = SIZES[size]
    metrics = {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": mobile}
    chrome.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", metrics)
    # Discord sets its safe area sizes on the menu's page, and the hub copies them into the game's frame
    sides = "".join(
        f"document.documentElement.style.setProperty('--discord-safe-area-inset-{side}', '{px}px');"
        for side, px in INSETS.get(size, {}).items()
    )
    # A new page has no <html> yet when this runs, so the sizes go on it once it is parsed
    script = f"if (window === window.top) {{ addEventListener('DOMContentLoaded', () => {{ {sides} }}); }}"
    INSET_SCRIPTS.append(chrome.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script}))


def clear_size(chrome) -> None:
    chrome.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
    while INSET_SCRIPTS:
        chrome.execute_cdp_cmd("Page.removeScriptToEvaluateOnNewDocument", INSET_SCRIPTS.pop())


@pytest.mark.parametrize("size", list(SIZES))
@pytest.mark.parametrize("game", ["lobby", *GAMES])
def test_screens(driver, live, game, size):  # noqa: F811
    set_size(driver, size)
    try:
        open_casino(driver, live)
        if game == "lobby":
            mouse_off_the_cards(driver)
            pause(driver, 800)
            shoot(driver, f"lobby-{size}")
            return
        if game == "holdem":
            practice_hand(driver, live, f"holdem-practice-{size}")
            return
        if game == "slots":
            live.cog.rng = Rigged(ints=[0, 0, 0])
        if game == "allin":
            live.cog.rng = Rigged(ints=[0, 1])
            on_loop(live, live.cog.store.save_game(fakes.GUILD_ID, "allin", cooldown=0))
        walk_up(driver, game)
        play_to_result(driver, game, f"{game}-{size}")
    finally:
        clear_size(driver)


@pytest.mark.parametrize("size", list(SIZES))
def test_holdem_real_hand(driver, live, size):  # noqa: F811
    set_size(driver, size)
    try:
        open_casino(driver, live)
        real_hand(driver, live, f"holdem-real-{size}")
    finally:
        clear_size(driver)


@pytest.mark.parametrize("size", list(SIZES))
@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_holdem_scenario(driver, live, scenario, size):  # noqa: F811
    set_size(driver, size)
    try:
        open_casino(driver, live)
        SCENARIOS[scenario](driver, live, f"holdem-{scenario}-{size}")
    finally:
        clear_size(driver)


@pytest.mark.parametrize("size", list(SIZES))
@pytest.mark.parametrize("scenario", list(MENU_SCENARIOS))
def test_menu_scenario(driver, live, scenario, size):  # noqa: F811
    set_size(driver, size)
    try:
        MENU_SCENARIOS[scenario](driver, live, f"{scenario}-{size}")
        assert not problems(driver)
    finally:
        clear_size(driver)
