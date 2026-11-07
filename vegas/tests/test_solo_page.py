"""The solo games in headless Chrome against the real hub and cog. Slots: the lever, the reels landing on what the bot
drew, and the jackpot on the machine, on the menu card and as news for the whole window. All In: the wheel's gold slice
and where it stops"""

import asyncio
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

from vegas.common import rounds
from vegas.common.games import slots
from vegas.tests import test_browser
from vegas.tests.tables_kit import Rigged
from vegas.tests.test_browser import (
    at_size,
    browser,
    fakes,
    me_on_the_hub,
    on_loop,
    open_casino,
    problems,
    result_big,
    walk_up,
)

driver = test_browser.driver
live = test_browser.live
SLOTS_ART = Path(__file__).resolve().parents[1] / "web" / "art" / "slots"
ANN = {"id": "9", "name": "Ann", "amount": 48_000}

# Where the lever's knob is drawn at rest, in the page's pixels, and how far down it travels, under the room the
# machine keeps for a jackpot note
LEVER = """
const scene = await import(new URL("scenes/slots.js", document.baseURI).href);
const { noteReach } = await import(new URL("table.js", document.baseURI).href);
const canvas = document.querySelector("#scene canvas");
const box = canvas.getBoundingClientRect();
const lever = scene.leverAt(box.width, box.height, noteReach(canvas.parentElement));
const x = box.left + lever.x;
const y = box.top + lever.y;
const fire = (type, dy, buttons) =>
  canvas.dispatchEvent(new PointerEvent(type, {
    clientX: x, clientY: y + dy, pointerId: 1, pointerType: "mouse", isPrimary: true, bubbles: true,
    cancelable: true, button: 0, buttons,
  }));
const frame = () => new Promise((resolve) => setTimeout(resolve, 16));
"""

# Hovers the knob until the scene shows the hand cursor there: the scene is drawn and the lever is where leverAt says
LEVER_READY = (
    "const done = arguments[arguments.length - 1];"
    "(async () => {"
    + LEVER
    + """
  for (let tries = 0; tries < 200; tries += 1) {
    fire("pointermove", 0, 0);
    if (canvas.style.cursor === "pointer") {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return false;
})().then(done, (e) => done(String(e)));
"""
)

# Presses the knob, drags it down reach x its travel over ms (no move at all when ms is 0), and lets go
PULL = (
    "const [ms, reach, done] = arguments;"
    "(async () => {"
    + LEVER
    + """
  fire("pointerdown", 0, 1);
  const start = performance.now();
  while (ms > 0) {
    await frame();
    const k = Math.min(1, (performance.now() - start) / ms);
    fire("pointermove", k * reach * lever.travel, 1);
    if (k >= 1) {
      break;
    }
  }
  fire("pointerup", ms > 0 ? reach * lever.travel : 0, 0);
  return true;
})().then(done, (e) => done(String(e)));
"""
)


def lever_ready(driver):
    browser.wait_for(driver, "document.querySelector('#scene canvas') !== null")
    assert driver.execute_async_script(LEVER_READY) is True


def pull_lever(driver, ms=150, reach=1.0):
    """Drags the machine's lever down with the page's own pointer events, the way a finger would"""
    lever_ready(driver)
    assert driver.execute_async_script(PULL, ms, reach) is True


def pick_bet(driver, chip):
    driver.find_element(By.ID, "clear").click()
    driver.find_element(By.CSS_SELECTOR, f'#chips .chip[data-value="{chip}"]').click()
    browser.wait_for(driver, f"document.getElementById('amount').textContent === '{chip}'")


def place_hidden(driver):
    return not driver.find_element(By.ID, "place").is_displayed()


def test_a_lever_pull_spins_the_reels_and_pays_what_the_bot_drew(driver, live):
    live.cog.rng = Rigged(ints=[3, 3, 3])
    open_casino(driver, live)
    walk_up(driver, "slots")
    assert driver.find_element(By.ID, "status-text").text == "Pick your bet, then pull the lever."
    pick_bet(driver, 100)
    assert place_hidden(driver)
    pull_lever(driver, 150)
    browser.wait_for(driver, "document.getElementById('status-text').textContent === 'The reels are spinning...'")
    assert place_hidden(driver)
    # Each machine is private, so the window only hears where the player is, never busy
    me = me_on_the_hub(live)
    assert (me.status, me.busy) == ("At Slots", False)
    browser.wait_for(driver, "!document.getElementById('result').hidden", timeout=15)
    assert result_big(driver) == "You win 1,400"
    browser.wait_for(driver, "document.getElementById('balance').textContent === '2,300'")
    assert place_hidden(driver)
    assert not problems(driver)


def test_a_tap_is_the_gentlest_pull_and_a_short_drag_springs_back(driver, live, monkeypatch):
    strengths = []
    spin_seconds = slots.spin_seconds

    def recorded(strength):
        strengths.append(strength)
        return spin_seconds(strength)

    monkeypatch.setattr(rounds.slots, "spin_seconds", recorded)
    open_casino(driver, live)
    walk_up(driver, "slots")
    # With no bet the tray refuses the pull, and says why under the chips until the bet changes
    driver.find_element(By.ID, "clear").click()
    pull_lever(driver, 0, reach=0)
    browser.wait_for(driver, "document.getElementById('why').textContent === 'Pick a bet of at least 10.'")
    assert driver.find_element(By.ID, "why").is_displayed()
    driver.find_element(By.ID, "min").click()
    browser.wait_for(driver, "document.getElementById('why').hidden")
    pull_lever(driver, 300, reach=0.5)
    driver.execute_script("return new Promise((resolve) => setTimeout(resolve, 1000))")
    assert strengths == []
    assert live.cog.bank.balances.get(fakes.MEMBER_ID, 1000) == 1000
    pull_lever(driver, 0, reach=0)
    WebDriverWait(driver, 10).until(lambda _: strengths)
    assert strengths == [0.0]
    browser.wait_for(driver, "!document.getElementById('result').hidden", timeout=15)
    assert not problems(driver)


# What a press 22 px either side of the knob's middle reaches (the scene shows the hand cursor over the lever), and
# whether a drag on the canvas could scroll the page
THUMB = (
    "const done = arguments[arguments.length - 1];"
    "(async () => {"
    + LEVER
    + """
  const edges = [];
  for (const dx of [-22, 22]) {
    canvas.dispatchEvent(new PointerEvent("pointermove", { clientX: 1, clientY: 1, bubbles: true }));
    canvas.dispatchEvent(new PointerEvent("pointermove", { clientX: x + dx, clientY: y, bubbles: true }));
    edges.push(canvas.style.cursor === "pointer");
  }
  return { edges, touch: getComputedStyle(canvas).touchAction };
})().then(done, (e) => done(String(e)));
"""
)


def test_the_lever_takes_a_thumb_on_an_upright_phone(driver, live):
    with at_size(driver, 390, 844, 2, True):
        open_casino(driver, live)
        walk_up(driver, "slots")
        lever_ready(driver)
        assert driver.execute_async_script(THUMB) == {"edges": [True, True], "touch": "none"}
        assert not problems(driver)


PAGE_MATH = """
const done = arguments[arguments.length - 1];
import(new URL("scenes/slots.js", document.baseURI).href).then((scene) => done({
  shares: [scene.shareOf(30000, 10, 500), scene.shareOf(30000, 750, 500), scene.shareOf(30005, 250, 500)],
  line: scene.jackpotLine(30000, 250, 500),
  strengths: [null, 120, 900, 5000, 510].map((ms) => scene.strengthOf(ms)),
})).catch((e) => done(String(e)));
"""


def test_the_slots_page_math_matches_the_bot(driver, live):
    open_casino(driver, live)
    found = driver.execute_async_script(PAGE_MATH)
    assert found == {
        "shares": [600, 30010, 15005],
        "line": "7-7-7 pays you 15,002 at this bet",
        "strengths": [0, 1, 0, 0, 0.5],
    }
    # The bot feeds the bet into the pot before it works out the share
    # (the bot never takes a bet over the max, so the page's 750 is the max's 500)
    cases = ((30000, 10), (30000, 500), (30005, 250))
    assert [slots.share(pot * slots.CENTS + slots.fed(bet), bet, 500) for pot, bet in cases] == [600, 30010, 15005]
    line = slots.share(30000 * slots.CENTS + slots.fed(250), 250, 500)
    assert found["line"] == f"7-7-7 pays you {line:,} at this bet"


# Makes the machine with a stand-in stage, plays each spin event, times it and reads what each reel's window shows then:
# the symbols above, on and below the line, from the labels the scene gives its reels, slots and symbols
TIMED_SPINS = """
const [events, done] = arguments;
(async () => {
  const pixi = await import(new URL("vendor/pixi.min.mjs", document.baseURI).href);
  const scene = await import(new URL("scenes/slots.js", document.baseURI).href);
  const app = new pixi.Application();
  await app.init({ width: 600, height: 600, backgroundAlpha: 0 });
  const root = new pixi.Container();
  app.stage.addChild(root);
  const stage = {
    app, root, game: "slots", title: "Slots", sound: { play() {} }, me: () => null, nameOf: () => "",
    settings: () => ({ min: 10, max: 500 }), actions: { place: () => true },
  };
  const machine = await scene.createScene(stage);
  machine.layout(600, 600);
  // The three slots nearest the line, top to bottom
  const windowOf = (index) => root.getChildByLabel(`reel-${index}`, true).getChildrenByLabel("slot", true)
    .map((slot) => [slot.y, slot.children.find((piece) => piece.visible).label])
    .sort((a, b) => Math.abs(a[0]) - Math.abs(b[0]))
    .slice(0, 3)
    .sort((a, b) => a[0] - b[0])
    .map(([, name]) => name);
  const found = [];
  for (const event of events) {
    const start = performance.now();
    await machine.play(event);
    const took = performance.now() - start;
    const shown = [0, 1, 2].map(windowOf);
    found.push([took, scene.landTimes(event.seconds, event.reels.map((reel) => reel[1])), shown]);
  }
  machine.destroy?.();
  app.destroy(true, { children: true });
  return found;
})().then(done, (e) => done(String(e)));
"""


def spin_event(seconds, stops):
    reels = [slots.window(stop) for stop in stops]
    strength = (seconds - slots.MIN_SPIN) / (slots.MAX_SPIN - slots.MIN_SPIN)
    return {"t": "event", "game": "slots", "kind": "spin", "stops": stops, "reels": reels, "seconds": seconds,
            "strength": strength}  # fmt: skip


def test_every_spin_lands_within_its_seconds_on_the_bots_stops(driver, live):
    open_casino(driver, live)
    driver.set_script_timeout(30)
    # Bell, coin, seven: the first two differ. Bell, bell, diamond: they match, so the third reel lingers
    apart, matched = [3, 5, 0], [3, 6, 9]
    assert slots.STRIP[3] != slots.STRIP[5] and slots.STRIP[3] == slots.STRIP[6]
    events = [spin_event(seconds, stops) for seconds in (slots.MIN_SPIN, slots.MAX_SPIN) for stops in (apart, matched)]
    found = driver.execute_async_script(TIMED_SPINS, events)
    assert isinstance(found, list), found
    for event, (took, lands, shown) in zip(events, found):
        assert took <= event["seconds"] * 1000 + 120, (event["seconds"], took)
        assert lands[0] < lands[1] < lands[2] <= event["seconds"] * 1000
        # Each reel shows exactly the bot's window: a near miss on screen is a real one
        assert shown == event["reels"]
    for at in (0, 2):
        apart_lands, matched_lands = found[at][1], found[at + 1][1]
        assert matched_lands[2] - matched_lands[1] >= 1.5 * (apart_lands[2] - apart_lands[1])
    assert not problems(driver)


# The reels' speeds at the gentlest and the hardest pull, then a reel spinning at the hardest pull's speed brought to
# land on stop 9 with its symbol on the line 3 seconds on: its place and speed every 10 ms until well after it settles
SLOW_DOWN = """
const done = arguments[arguments.length - 1];
import(new URL("scenes/slots.js", document.baseURI).href).then((scene) => {
  const speeds = [scene.reelSpeed(0), scene.reelSpeed(1)];
  const plan = scene.landing({ pos: 0, speed: speeds[1] }, 0, 9, 3000, speeds[1]);
  const path = [];
  for (let at = 0; at <= 4000; at += 10) {
    const { pos, speed } = plan.motion(at);
    path.push([at, pos, speed]);
  }
  done({ speeds, target: plan.target, path });
}).catch((e) => done(String(e)));
"""


def test_a_reel_slows_down_for_a_long_time_and_crawls_onto_the_line(driver, live):
    open_casino(driver, live)
    found = driver.execute_async_script(SLOW_DOWN)
    assert isinstance(found, dict), found
    # In symbols a millisecond: a hard pull spins faster than a gentle one, but never as a blur
    gentle, hard = found["speeds"]
    assert 0 < gentle < hard <= 0.022, found["speeds"]
    target, path = found["target"], found["path"]

    def first(test):
        return next(at for at, pos, speed in path if test(pos, speed))

    # The reel ends on the bot's stop: place p shows stop -p
    assert -target % len(slots.STRIP) == 9 and path[-1][1] == target
    arrives = first(lambda pos, speed: pos >= target)
    assert 2990 <= arrives <= 3010, arrives
    # It slows down for over a second, never speeding up again, and the last symbol takes 300 ms or more to crawl
    # onto the line
    slowing = first(lambda pos, speed: speed < 0.9 * hard)
    assert arrives - slowing >= 1000, (slowing, arrives)
    speeds = [speed for at, pos, speed in path if slowing <= at <= arrives]
    assert all(later <= sooner + 1e-9 for sooner, later in zip(speeds, speeds[1:]))
    assert arrives - first(lambda pos, speed: pos >= target - 1) >= 300
    # Then it runs a little past the line and settles back onto it
    past = max(pos for at, pos, speed in path) - target
    assert 0.05 <= past <= 0.3, past
    assert first(lambda pos, speed: pos == target and speed == 0) <= arrives + 600


def test_a_crawling_reel_is_drawn_sharp(driver, live):
    open_casino(driver, live)
    # The last reel of a gentle spin, 150 ms before its symbol reaches the line: still moving, but without blur, so the
    # symbols crawling past the line can be read
    found = on_stand_in(
        driver,
        """
    const event = given[0];
    const lands = scene.landTimes(event.seconds, event.reels.map((reel) => reel[1]));
    const start = performance.now();
    const spin = machine.play(event);
    await pause(start + lands[2] - 150 - performance.now());
    const filter = root.getChildByLabel("reel-2", true).getChildByLabel("strip").filters[0];
    const blur = filter.enabled ? filter.strengthY : 0;
    const moving = !(await still());
    await spin;
    return { blur, moving };
""",
        spin_event(slots.MIN_SPIN, [3, 5, 0]),
    )
    assert found == {"blur": 0, "moving": True}, found
    assert not problems(driver)


PILL = "document.querySelector('.game-card[data-key=\"slots\"] .jackpot')"


def pill(driver):
    return driver.execute_script(f"return {PILL}?.textContent")


def news_after(driver, live, amount):
    on_loop(live, live.cog.send_jackpot(fakes.GUILD_ID, amount, ANN, live.cog.floors["i-1"]))
    browser.wait_for(driver, "!document.getElementById('news').hidden")
    # Its slide-in, which moves it up from under the bar, is done
    browser.wait_for(driver, "document.getElementById('news').getAnimations().length === 0")
    return driver.execute_script("return document.getElementById('news').textContent")


# The news note's box against the top bar, the scene and the dock, and what a press at the lever's knob and at the
# middle of its arm reaches while the note shows
NEWS_PLACE = (
    "const done = arguments[arguments.length - 1];"
    "(async () => {"
    + LEVER
    + """
  const rect = (node) => node.getBoundingClientRect();
  const news = rect(document.getElementById("news"));
  const dock = rect(document.querySelector(".dock"));
  const top = rect(document.querySelector(".top"));
  const apart = (a, b) => a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom;
  return {
    under_bar: news.top >= top.bottom,
    clear_of_dock: apart(news, dock),
    knob: document.elementFromPoint(x, y) === canvas,
    arm: document.elementFromPoint(x, y + lever.travel / 2) === canvas,
  };
})().then(done, (e) => done(String(e)));
"""
)


def test_the_jackpot_shows_on_the_card_the_machine_and_as_news(driver, live):
    open_casino(driver, live)
    browser.wait_for(driver, f"{PILL}?.textContent")
    assert pill(driver) == "Jackpot 30,000"
    assert news_after(driver, live, 31_000) == "Ann hit the jackpot: 48,000!"
    assert pill(driver) == "Jackpot 31,000"
    # The note goes away by itself
    browser.wait_for(driver, "document.getElementById('news').hidden", timeout=8)
    walk_up(driver, "slots")
    lever_ready(driver)
    assert news_after(driver, live, 32_000) == "Ann hit the jackpot: 48,000!"
    assert driver.execute_async_script(NEWS_PLACE) == {
        "under_bar": True,
        "clear_of_dock": True,
        "knob": True,
        "arm": True,
    }
    driver.find_element(By.ID, "open-rules").click()
    browser.wait_for(driver, "document.getElementById('panel-body').textContent.includes('Pay table')")
    # House rules ask the bot, which still has the seed: the notes above were sent straight to the window
    lines = [line.text for line in driver.find_elements(By.CSS_SELECTOR, "#panel-body .house-line")]
    assert "Bets 10 to 500 · Jackpot 30,000" in lines
    assert not problems(driver)


async def keep_announcing(live, stop):
    """A jackpot message to the window every tenth of a second, until `stop` has something in it"""
    floor = live.cog.floors["i-1"]
    for step in range(1, 300):
        if stop:
            return
        await live.cog.send_jackpot(fakes.GUILD_ID, 30_000 + step * 10, None, floor)
        await asyncio.sleep(0.1)


def test_a_card_press_survives_jackpot_updates(driver, live):
    open_casino(driver, live)
    browser.wait_for(driver, f"{PILL}?.textContent")
    driver.execute_script(
        "window.replaced = 0;"
        "const count = (list) => { window.replaced += list.length; };"
        "new MutationObserver(count).observe(document.getElementById('menu'), { childList: true });"
        "document.querySelectorAll('.game-card').forEach((card) =>"
        "  new MutationObserver(count).observe(card, { childList: true }));"
    )
    stop = []
    announcing = asyncio.run_coroutine_threadsafe(keep_announcing(live, stop), live.loop)
    try:
        browser.wait_for(driver, f"Number({PILL}.textContent.replace(/\\D/g, '')) >= 30030")
        card = driver.find_element(By.CSS_SELECTOR, ".game-card[data-key='hilo'] .label")
        ActionChains(driver).move_to_element(card).click_and_hold().pause(0.8).release().perform()
        browser.wait_for(driver, "!document.getElementById('table').hidden")
        assert driver.execute_script("return window.replaced") == 0
        assert driver.execute_script("return document.getElementById('app').dataset.view") == "table"
    finally:
        stop.append(True)
        announcing.result(15)
    assert not problems(driver)


# ---------- The machine on a canvas of its own ----------

# Makes the machine on its own 600 by 600 canvas at the page's top left, with a stand-in stage whose place() says yes
# and counts the pulls. `fire(type, dy, buttons)` sends the pointer events of finger number `finger` at the knob (dy
# pixels below it), `drag(to)` moves it down `to` of the lever's travel, and `still()` says whether every reel stood
# still over the last tenth of a second. The check, the body of an async function, comes after it, and `given` holds
# the values passed with it
STAND_IN = """
const done = arguments[arguments.length - 1];
const given = [...arguments].slice(0, -1);
(async () => {
  const pixi = await import(new URL("vendor/pixi.min.mjs", document.baseURI).href);
  const scene = await import(new URL("scenes/slots.js", document.baseURI).href);
  const app = new pixi.Application();
  await app.init({ width: 600, height: 600, backgroundAlpha: 0 });
  app.canvas.style.cssText = "position: fixed; left: 0; top: 0; z-index: 99";
  document.body.append(app.canvas);
  const root = new pixi.Container();
  app.stage.addChild(root);
  const placed = [];
  const stage = {
    app, root, game: "slots", title: "Slots", sound: { play() {} }, me: () => null, nameOf: () => "",
    settings: () => ({ min: 10, max: 500 }), actions: { place: (strength) => placed.push(strength) > 0 },
  };
  const machine = await scene.createScene(stage);
  machine.layout(600, 600);
  const lever = scene.leverAt(600, 600);
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  // Presses find the lever where the last drawn frame put it
  await pause(100);
  let finger = 1;
  const fire = (type, dy, buttons) => app.canvas.dispatchEvent(new PointerEvent(type, {
    clientX: lever.x, clientY: lever.y + dy, pointerId: finger, pointerType: "touch", isPrimary: true, bubbles: true,
    cancelable: true, button: 0, buttons,
  }));
  const drag = async (to) => {
    for (let step = 1; step <= 8; step += 1) {
      await pause(16);
      fire("pointermove", (to * lever.travel * step) / 8, 1);
    }
  };
  const places = () => [0, 1, 2].map((index) =>
    root.getChildByLabel(`reel-${index}`, true).getChildrenByLabel("slot", true).map((slot) => slot.y).join());
  const still = async () => {
    const before = places().join("|");
    await pause(100);
    return places().join("|") === before;
  };
  try {
    return await check();
  } finally {
    machine.destroy?.();
    app.destroy(true, { children: true });
  }
"""


def on_stand_in(driver, check, *given):
    """Runs `check` against the machine on its own canvas, and returns its answer"""
    driver.set_script_timeout(30)
    script = STAND_IN + "async function check() {" + check + "}\n})().then(done, (e) => done(String(e)));"
    return driver.execute_async_script(script, *given)


def test_the_knob_rests_where_lever_at_says(driver, live):
    open_casino(driver, live)
    found = on_stand_in(
        driver,
        """
    const knob = root.getChildByLabel("knob", true).getGlobalPosition();
    return [Math.round(knob.x - lever.x), Math.round(knob.y - lever.y)];
""",
    )
    assert found == [0, 0]
    assert not problems(driver)


def test_a_cancelled_touch_leaves_the_lever_working(driver, live):
    open_casino(driver, live)
    # The phone takes the touch back halfway down (an edge swipe, a turn of the phone): nothing is sent, and the next
    # drag pulls as usual
    found = on_stand_in(
        driver,
        """
    fire("pointerdown", 0, 1);
    await drag(0.5);
    app.canvas.dispatchEvent(new PointerEvent("pointercancel", { pointerId: 1, pointerType: "touch", bubbles: true }));
    await pause(600);
    const before = placed.length;
    finger = 2;
    fire("pointerdown", 0, 1);
    await drag(1);
    fire("pointerup", lever.travel, 0);
    return [before, placed.length];
""",
    )
    assert found == [0, 1]
    assert not problems(driver)


def test_a_refused_pull_stops_the_reels_at_once(driver, live):
    open_casino(driver, live)
    # The reels spin up as the lever hits the bottom. The bot refuses the pull (its notice), so they stop well before
    # they would have coasted to a stop on their own
    found = on_stand_in(
        driver,
        """
    fire("pointerdown", 0, 1);
    await drag(1);
    fire("pointerup", lever.travel, 0);
    await pause(300);
    const spinning = !(await still());
    machine.notice?.();
    await pause(750);
    return [spinning, await still()];
""",
    )
    assert found == [True, True]
    assert not problems(driver)


def test_spinning_reels_blur_and_sharpen_as_they_stop(driver, live):
    open_casino(driver, live)
    # How much each reel's strip is blurred up and down, in design pixels: 0 when it isn't
    found = on_stand_in(
        driver,
        """
    const blur = () => [0, 1, 2].map((index) => {
      const filter = root.getChildByLabel(`reel-${index}`, true).getChildByLabel("strip").filters?.[0];
      return filter?.enabled ? filter.strengthY : 0;
    });
    const resting = blur();
    fire("pointerdown", 0, 1);
    await drag(1);
    fire("pointerup", lever.travel, 0);
    await pause(450);
    const fast = blur();
    for (let tries = 0; tries < 60 && !(await still()); tries += 1) {}
    return { resting, fast, stopped: blur() };
""",
    )
    assert found["resting"] == [0, 0, 0] and found["stopped"] == [0, 0, 0], found
    assert min(found["fast"]) >= 4, found
    assert not problems(driver)


# Whether a part and everything holding it show
SHOWN = """
const shown = (node) => {
  for (let at = node; at; at = at.parent) {
    if (!at.visible || at.alpha <= 0) {
      return false;
    }
  }
  return true;
};
"""

JACKPOT = {"outcome": "jackpot", "payout": 6001, "stake": 100, "balance": 8401}
BELLS = {"outcome": "win", "payout": 1400, "stake": 100, "balance": 2500}


def test_the_jackpot_is_the_machines_biggest_show(driver, live):
    open_casino(driver, live)
    # At rest and at the show's height: how many jackpot lines show, how tall the marquee's JACKPOT is on screen, how
    # many coins fly, and how many of those are out past the cabinet's sides
    found = on_stand_in(
        driver,
        SHOWN
        + """
    machine.jackpot(30000);
    machine.preview(100);
    await pause(100);
    const title = root.getChildByLabel("jackpot-title", true);
    const tall = () => title.getBounds().maxY - title.getBounds().minY;
    const lines = () => root.getChildrenByLabel("jackpot-line", true).filter((line) => line.text && shown(line)).length;
    const look = () => {
      const box = root.getChildByLabel("machine", true).getBounds();
      const coins = root.getChildrenByLabel("flying-coin", true).filter(shown).map((coin) => coin.getBounds());
      const past = coins.filter((coin) => coin.maxX < box.minX || coin.minX > box.maxX);
      return { lines: lines(), title: tall(), coins: coins.length, past: past.length };
    };
    const rest = look();
    machine.result(given[0]);
    await pause(1300);
    const peak = look();
    await pause(4500);
    return { rest, peak, after: look() };
""",
        JACKPOT,
    )
    rest, peak, after = found["rest"], found["peak"], found["after"]
    assert rest["lines"] == 1 and peak["lines"] == 0 and after["lines"] == 1, found
    assert peak["title"] >= 1.25 * rest["title"], found
    assert abs(after["title"] - rest["title"]) <= 1, found
    assert peak["coins"] >= 40 and peak["past"] >= 10, found
    assert not problems(driver)


@pytest.mark.parametrize("message", [BELLS, JACKPOT], ids=["bells", "jackpot"])
def test_flying_coins_never_cover_the_win_counting_on_the_belly(driver, live, message):
    open_casino(driver, live)
    # Every twentieth of a second for two seconds, the coins in front of the machine that overlap the belly's count
    found = on_stand_in(
        driver,
        SHOWN
        + """
    const meter = root.getChildByLabel("meter", true);
    const over = (a, b) => a.minX < b.maxX && a.maxX > b.minX && a.minY < b.maxY && a.maxY > b.minY;
    machine.result(given[0]);
    const hits = [];
    let flown = 0;
    for (let step = 0; step < 40; step += 1) {
      await pause(50);
      const words = meter.getBounds();
      const coins = root.getChildByLabel("fountain", true).getChildrenByLabel("flying-coin").filter(shown);
      flown = Math.max(flown, coins.length);
      hits.push(...coins.filter((coin) => over(coin.getBounds(), words)).map(() => step));
    }
    return { hits, flown };
""",
        message,
    )
    assert found["flown"] >= 20, found
    assert found["hits"] == [], found
    assert not problems(driver)


# ---------- A connection that drops ----------

# Makes the page's connection to the bot look down (as while it reconnects), or back up, without closing it
CONNECTION_DOWN = """
if (!window.realReadyState) {
  window.realReadyState = Object.getOwnPropertyDescriptor(WebSocket.prototype, "readyState");
  Object.defineProperty(WebSocket.prototype, "readyState", {
    get() {
      return window.connectionDown ? WebSocket.CLOSED : window.realReadyState.get.call(this);
    },
  });
}
window.connectionDown = arguments[0];
"""

IDLE = "document.getElementById('status-text').textContent === 'Pick your bet, then pull the lever.'"
SPINNING = "document.getElementById('status-text').textContent === 'The reels are spinning...'"


def test_a_pull_while_the_connection_is_down_springs_back_and_the_next_one_goes(driver, live):
    open_casino(driver, live)
    walk_up(driver, "slots")
    pick_bet(driver, 10)
    driver.execute_script(CONNECTION_DOWN, True)
    pull_lever(driver, 150)
    browser.wait_for(driver, "document.getElementById('toast').textContent === 'Not connected right now.'")
    driver.execute_script("return new Promise((resolve) => setTimeout(resolve, 600))")
    assert driver.execute_script(f"return {IDLE}")
    driver.execute_script(CONNECTION_DOWN, False)
    pull_lever(driver, 150)
    browser.wait_for(driver, "!document.getElementById('result').hidden", timeout=15)
    assert not problems(driver)


def test_a_pull_lost_with_the_old_connection_is_cleared_when_the_bot_says_hello_again(driver, live, monkeypatch):
    dispatch = live.cog.dispatch
    lost = []

    async def losing_the_first_pull(floor, conn, data):
        if data.get("t") == "pull" and not lost:
            lost.append(data)
            return
        await dispatch(floor, conn, data)

    monkeypatch.setattr(live.cog, "dispatch", losing_the_first_pull)
    open_casino(driver, live)
    walk_up(driver, "slots")
    pick_bet(driver, 10)
    # The pull goes out as the link drops, so the bot never hears it; the page waits for its spin
    pull_lever(driver, 150)
    browser.wait_for(driver, SPINNING)
    assert lost
    # Back on, the bot greets the page again, and the page stops waiting for a spin that will never come
    conn = next(each for each in live.cog.floors["i-1"].where if each.ctx.author.id == fakes.MEMBER_ID)
    on_loop(live, conn.send(on_loop(live, live.cog.hello(conn.ctx))))
    browser.wait_for(driver, IDLE)
    # Once the lever is back up, the next pull goes
    driver.execute_script("return new Promise((resolve) => setTimeout(resolve, 800))")
    pull_lever(driver, 150)
    browser.wait_for(driver, "!document.getElementById('result').hidden", timeout=15)
    assert not problems(driver)


# ---------- The winner's own note ----------

# Notes the moment the result and the news note each first show, and the moment the result first hides again
SHOWN_AT = """
window.shownAt = {};
for (const id of ["result", "news"]) {
  const node = document.getElementById(id);
  new MutationObserver(() => {
    if (!node.hidden && !(id in window.shownAt)) {
      window.shownAt[id] = performance.now();
    }
    if (node.hidden && id in window.shownAt && !(`${id}-gone` in window.shownAt)) {
      window.shownAt[`${id}-gone`] = performance.now();
    }
  }).observe(node, { attributes: true, attributeFilter: ["hidden"] });
}
"""


def test_the_winners_own_note_waits_until_their_result_card_hides(driver, live):
    """The winner's note waits for their reels and then for their result card, so the two never stack"""
    live.cog.rng = Rigged(ints=[0, 0, 0])
    open_casino(driver, live)
    walk_up(driver, "slots")
    pick_bet(driver, 100)
    # The bot pays at once instead of waiting out the spin, so the jackpot comes while the reels still turn
    live.cog.floors["i-1"].tables["slots"].speed = 0
    driver.execute_script(SHOWN_AT)
    pull_lever(driver, 150)
    browser.wait_for(driver, "'news' in window.shownAt", timeout=15)
    shown = driver.execute_script("return window.shownAt")
    assert "result-gone" in shown and shown["result-gone"] <= shown["news"], shown
    note = driver.execute_script("return document.getElementById('news').textContent")
    assert note == "Member hit the jackpot: 6,000!"
    assert not problems(driver)


# The scene's room in CSS pixels on a desktop, an upright phone and a sideways phone
SCENE_SIZES = {"desktop": (960, 745), "phone": (390, 485), "sideways": (564, 335)}

# The jackpot lines the machine shows, each with its words, its size on screen in CSS pixels and its box. A line counts
# when it has words and it and everything holding it show. `boxOf(label)` is the box of the part with that label
LINES = """
const shows = (node) => {
  for (let at = node; at; at = at.parent) {
    if (!at.visible || at.alpha <= 0) {
      return false;
    }
  }
  return true;
};
const boxOf = (label) => {
  const box = root.getChildByLabel(label, true).getBounds();
  return [box.minX, box.minY, box.maxX, box.maxY];
};
const lines = () => root.getChildrenByLabel("jackpot-line", true).filter((line) => line.text && shows(line)).map(
  (line) => {
    const top = line.toGlobal({ x: 0, y: 0 });
    const below = line.toGlobal({ x: 0, y: 1 });
    const box = line.getBounds();
    const px = line.style.fontSize * (below.y - top.y);
    return { words: line.text, px, box: [box.minX, box.minY, box.maxX, box.maxY] };
  },
);
"""


def apart(a, b) -> bool:
    """Two boxes, each [left, top, right, bottom], that don't overlap"""
    return a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3]


def test_a_cleared_bet_hides_the_jackpot_line(driver, live):
    open_casino(driver, live)
    found = on_stand_in(
        driver,
        LINES
        + """
    machine.jackpot(30000);
    machine.preview(100);
    const before = lines().map((line) => line.words);
    machine.preview(0);
    return [before, lines().map((line) => line.words)];
""",
    )
    assert found == [["7-7-7 pays you 6,000 at this bet"], []]
    assert not problems(driver)


@pytest.mark.parametrize("size", list(SCENE_SIZES))
def test_the_jackpot_line_reads_at_every_size_and_covers_no_reel_or_lever(driver, live, size):
    width, height = SCENE_SIZES[size]
    open_casino(driver, live)
    found = on_stand_in(
        driver,
        LINES
        + """
    const [width, height] = given;
    machine.jackpot(30000);
    machine.preview(100);
    machine.layout(width, height);
    const sign = root.getChildByLabel("sign", true);
    return {
      lines: lines(),
      keep: ["reel-0", "reel-1", "reel-2", "lever"].map(boxOf),
      sign: sign.visible ? root.getChildByLabel("machine", true).toGlobal({ x: 0, y: 0 }).x : null,
    };
""",
        width,
        height,
    )
    assert isinstance(found, dict), found
    assert [line["words"] for line in found["lines"]] == ["7-7-7 pays you 6,000 at this bet"]
    line = found["lines"][0]
    assert line["px"] >= 10, f"{size}: the line is {line['px']:.1f} px"
    left, top, right, bottom = line["box"]
    assert left >= 0 and top >= 0 and right <= width and bottom <= height, (size, line["box"])
    for box in found["keep"]:
        assert apart(line["box"], box), (size, line["box"], box)
    # On a sign beside the machine, the words sit in the middle of the gap between the scene's edge and the machine,
    # clear of that edge
    if found["sign"] is not None:
        assert abs((left + right) / 2 - found["sign"] / 2) <= 2, (size, line["box"], found["sign"])
        assert left >= 12, (size, line["box"])
    assert not problems(driver)


def cabinet_edges() -> tuple[int, int]:
    """In machine.png's pixels: the right edge of the cabinet's column of side lights (where most of its rows end) and
    the outer end of the side hub that sticks out past it (where the widest row ends)"""
    alpha = Image.open(SLOTS_ART / "machine.png").convert("RGBA").getchannel("A").point(lambda a: 255 if a > 128 else 0)
    ends = [alpha.crop((0, y, alpha.width, y + 1)).getbbox() for y in range(alpha.height)]
    rights = Counter(box[2] for box in ends if box)
    return rights.most_common(1)[0][0], max(rights)


# The lever's arm and knob at rest in machine.png's pixels, and the knob's box in the page's pixels, in a scene of the
# size given
LEVER_PLACE = """
    const [width, height] = given;
    machine.layout(width, height);
    const cabinet = root.getChildByLabel("machine", true);
    const box = (label) => root.getChildByLabel(label, true).getBounds();
    const inArt = (label) => {
      const { minX, minY, maxX, maxY } = box(label);
      const [a, b] = [cabinet.toLocal({ x: minX, y: minY }), cabinet.toLocal({ x: maxX, y: maxY })];
      return [a.x, a.y, b.x, b.y];
    };
    const knob = box("knob");
    return { arm: inArt("arm"), knob: inArt("knob"), shown: [knob.minX, knob.minY, knob.maxX, knob.maxY] };
"""


@pytest.mark.parametrize("size", list(SCENE_SIZES))
def test_the_lever_stands_beside_the_cabinet_on_its_side_hub(driver, live, size):
    width, height = SCENE_SIZES[size]
    open_casino(driver, live)
    found = on_stand_in(driver, LEVER_PLACE, width, height)
    assert isinstance(found, dict), found
    lights, hub = cabinet_edges()
    # The arm rises out of the side hub (the part sticking out past the cabinet's edge), a hair right of its middle
    # where it looks centred: clear of the column of lights, and it neither floats past the hub's end nor sits on the
    # cabinet
    arm_left, _, arm_right, _ = found["arm"]
    assert 2 <= (arm_left + arm_right) / 2 - (lights + hub) / 2 <= 4, (lights, hub, found)
    assert arm_left >= lights and arm_right <= hub + 4, (lights, hub, found)
    left, top, right, bottom = found["shown"]
    assert left >= 0 and top >= 0 and right <= width and bottom <= height, (size, found["shown"])
    assert not problems(driver)


# ---------- The All In wheel ----------

# The wheel's math from the page: the gold slice's size, and where the pointer stops for a win or a loss
WHEEL_MATH = """
const done = arguments[arguments.length - 1];
import(new URL("scenes/allin.js", document.baseURI).href).then((scene) => {
  const stops = [];
  for (const multiplier of [2, 10, 1000]) {
    for (const random of [0, 0.5, 0.999]) {
      stops.push([multiplier, scene.sliceDegrees(multiplier), true, scene.landing(true, multiplier, random)]);
      stops.push([multiplier, scene.sliceDegrees(multiplier), false, scene.landing(false, multiplier, random)]);
    }
  }
  done({ slices: [2, 3, 10, 178, 1000, 1].map((multiplier) => scene.sliceDegrees(multiplier)), stops });
}).catch((e) => done(String(e)));
"""


def test_the_wheels_gold_slice_is_the_true_chance(driver, live):
    open_casino(driver, live)
    found = driver.execute_async_script(WHEEL_MATH)
    assert isinstance(found, dict), found
    assert found["slices"] == [90, 72, 30, 2, 2, 90]
    for multiplier, slice_degrees, win, stop in found["stops"]:
        assert 0 <= stop < 360, (multiplier, win, stop)
        # How far the pointer stops from the gold slice's middle, either way round
        apart = min(stop, 360 - stop)
        if win:
            assert apart <= slice_degrees / 2, (multiplier, stop)
        else:
            assert apart >= slice_degrees / 2 + 2, (multiplier, stop)


# Makes the wheel with a stand-in stage, plays each pull event and times it. Then reads where the pointer stopped, in
# degrees from the gold slice's middle, from the turn of the part of the wheel that spins (labelled "disc")
TIMED_PULLS = """
const [events, done] = arguments;
(async () => {
  const pixi = await import(new URL("vendor/pixi.min.mjs", document.baseURI).href);
  const scene = await import(new URL("scenes/allin.js", document.baseURI).href);
  const app = new pixi.Application();
  await app.init({ width: 600, height: 600, backgroundAlpha: 0 });
  const root = new pixi.Container();
  app.stage.addChild(root);
  const stage = {
    app, root, game: "allin", title: "All In", sound: { play() {} }, me: () => "1", nameOf: () => "Member",
    settings: () => ({}), actions: { place: () => true },
  };
  const wheel = await scene.createScene(stage);
  wheel.layout(600, 600);
  wheel.preview(3);
  const disc = root.getChildByLabel("disc", true);
  const found = [];
  for (const event of events) {
    const start = performance.now();
    await wheel.play(event);
    const took = performance.now() - start;
    found.push([took, (((-disc.angle) % 360) + 360) % 360]);
  }
  wheel.destroy?.();
  app.destroy(true, { children: true });
  return found;
})().then(done, (e) => done(String(e)));
"""


def test_a_wheel_spin_fits_the_pull_pace(driver, live):
    open_casino(driver, live)
    driver.set_script_timeout(30)
    events = [{"t": "event", "game": "allin", "kind": "pull", "win": win, "multiplier": 3} for win in (True, False)]
    found = driver.execute_async_script(TIMED_PULLS, events)
    assert isinstance(found, list), found
    for event, (took, stop) in zip(events, found):
        assert took <= 3000 + 120, (event["win"], took)
        # The gold slice at x3 is 72 degrees: a win stops inside it, a loss in the red
        apart = min(stop, 360 - stop)
        assert apart <= 36 if event["win"] else apart >= 38, (event["win"], stop)
    assert not problems(driver)


# Makes the wheel on its own canvas at the scene's own size, 560 by 700, so one scene pixel is one canvas pixel, with
# a stand-in stage for a player with a long name in wide capitals. The check, the body of an async function, comes
# after it
WHEEL_STAND_IN = """
const done = arguments[arguments.length - 1];
(async () => {
  const pixi = await import(new URL("vendor/pixi.min.mjs", document.baseURI).href);
  const scene = await import(new URL("scenes/allin.js", document.baseURI).href);
  const app = new pixi.Application();
  await app.init({ width: 560, height: 700, backgroundAlpha: 0, antialias: true });
  const root = new pixi.Container();
  app.stage.addChild(root);
  const stage = {
    app, root, game: "allin", title: "All In", sound: { play() {} }, me: () => "1",
    nameOf: () => "WOLFGANGMONTGOMERY", settings: () => ({}), actions: { place: () => true },
  };
  const wheel = await scene.createScene(stage);
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  try {
    return await check();
  } finally {
    wheel.destroy?.();
    app.destroy(true, { children: true });
  }
"""


def on_wheel(driver, check):
    """Runs `check` against the wheel on its own canvas, and returns its answer"""
    driver.set_script_timeout(30)
    script = WHEEL_STAND_IN + "async function check() {" + check + "}\n})().then(done, (e) => done(String(e)));"
    return driver.execute_async_script(script)


# The face's color just past the edges of the thinnest gold slice (x200), where the pointer's tip stands after the
# nearest loss the wheel allows: 2 degrees clear of the slice, the tip about 1 degree either side of that. The glow is
# drawn at its brightest, and the pointer and the tag are hidden. Each sample: degrees past the edge, then red, green
# and blue
NEAR_A_SLIVER = """
wheel.layout(560, 700);
wheel.preview(200);
await pause(500);
app.ticker.stop();
for (const label of ["pointer", "tag"]) {
  root.getChildByLabel(label, true).visible = false;
}
root.getChildByLabel("glow", true).alpha = 1;
const middle = root.getChildByLabel("wheel", true).getGlobalPosition();
const half = scene.sliceDegrees(200) / 2;
const frame = new pixi.Rectangle(0, 0, 560, 700);
const { pixels, width } = app.renderer.extract.pixels({ target: app.stage, frame });
const found = [];
for (const side of [-1, 1]) {
  for (const past of [1.2, 2, 3]) {
    for (let radius = 130; radius <= 165; radius += 5) {
      const angle = ((half + past) * side * Math.PI) / 180;
      const x = Math.round(middle.x + Math.sin(angle) * radius);
      const y = Math.round(middle.y - Math.cos(angle) * radius);
      const at = (y * width + x) * 4;
      found.push([past, pixels[at], pixels[at + 1], pixels[at + 2]]);
    }
  }
}
return found;
"""


# Where the thinnest slice's tag stands and where its line ends, at rest and after two wins that stop at either edge
# of the slice: which side of the wheel the tag is on, how far from the wheel's middle the line ends, how far round from
# the slice's middle (in degrees), and how far down the pointer's tip reaches
TAG_LINE = """
wheel.layout(560, 700);
wheel.preview(200);
const tag = root.getChildByLabel("tag", true);
const disc = root.getChildByLabel("disc", true);
const middle = root.getChildByLabel("wheel", true).getGlobalPosition();
const look = () => {
  const end = tag.toGlobal(tag.end);
  const dx = end.x - middle.x;
  const dy = end.y - middle.y;
  const off = ((Math.atan2(dx, -dy) * 180) / Math.PI - disc.angle + 540) % 360 - 180;
  const tip = middle.y - root.getChildByLabel("pointer", true).getBounds().maxY;
  return { right: tag.getGlobalPosition().x > middle.x, radius: Math.hypot(dx, dy), off, tip };
};
await pause(700);
const found = [look()];
for (const draw of [0.02, 0.98]) {
  const random = Math.random;
  Math.random = () => draw;
  const spin = wheel.play({ kind: "pull", multiplier: 200, win: true });
  Math.random = random;
  await spin;
  await pause(900);
  found.push(look());
}
return { found, half: scene.sliceDegrees(200) / 2 };
"""


def test_a_thin_slices_tag_stays_on_one_side_and_its_line_ends_on_the_slice_below_the_pointer(driver, live):
    open_casino(driver, live)
    answer = on_wheel(driver, TAG_LINE)
    assert isinstance(answer, dict), answer
    for spot in answer["found"]:
        assert spot["right"], answer
        assert spot["radius"] < spot["tip"] - 4, answer
        assert abs(spot["off"]) <= answer["half"], answer
    assert not problems(driver)


# How much of the red face is streaked by its gold spokes and pegs, at full speed early in a spin and once the wheel
# stands still. Only the part that turns is drawn (no rim, shine, bulbs or pointer). Samples on rings from near the hub
# out to the pegs, over the red slices only (well clear of the gold slice and its trailing copy), in the wheel's own
# angles, so they turn with it: the share whose green stands out from the reds' (the reds have under 20, gold 160)
STREAKS = """
wheel.layout(560, 700);
wheel.preview(3);
await pause(300);
const disc = root.getChildByLabel("disc", true);
for (const part of [...root.getChildByLabel("wheel", true).children, root.getChildByLabel("pointer", true)]) {
  part.visible = part === disc;
}
const frame = new pixi.Rectangle(0, 0, 560, 700);
const half = scene.sliceDegrees(3) / 2;
const streaked = () => {
  const { pixels, width } = app.renderer.extract.pixels({ target: app.stage, frame });
  let lit = 0;
  let all = 0;
  for (let degrees = half + 20; degrees <= 360 - half - 20; degrees += 0.5) {
    const angle = (degrees * Math.PI) / 180;
    for (const radius of [80, 100, 120, 140, 165]) {
      const at = disc.toGlobal({ x: Math.sin(angle) * radius, y: -Math.cos(angle) * radius });
      const index = (Math.round(at.y) * width + Math.round(at.x)) * 4;
      lit += pixels[index + 1] >= 32 ? 1 : 0;
      all += 1;
    }
  }
  return lit / all;
};
const spin = wheel.play({ t: "event", game: "allin", kind: "pull", win: false, multiplier: 3 });
await pause(850);
const fast = streaked();
await spin;
await pause(150);
return { fast, still: streaked() };
"""


def test_the_wheels_spokes_and_pegs_blur_as_it_races_and_sharpen_as_it_stops(driver, live):
    """Racing, the wheel covers about a slice a frame, so sharp spokes would seem to stand still or flicker: they
    smear back along the way it turns, the way the reels blur, and are sharp again once it stops"""
    open_casino(driver, live)
    answer = on_wheel(driver, STREAKS)
    assert isinstance(answer, dict), answer
    assert answer["still"] <= 0.12, answer
    assert answer["fast"] >= 0.3, answer
    assert answer["fast"] >= 3 * answer["still"], answer
    assert not problems(driver)


def test_red_beside_a_thin_slice_never_reads_as_gold(driver, live):
    open_casino(driver, live)
    found = on_wheel(driver, NEAR_A_SLIVER)
    assert isinstance(found, list) and found, found
    # The face's reds have about a sixth as much green as red; gold has well over half
    gold = [sample for sample in found if sample[2] > 0.3 * sample[1]]
    assert gold == []
    assert not problems(driver)


# The name on the stand's plate, and its size on screen in CSS pixels, at a sideways phone's, an upright phone's and a
# desktop's room for the scene, in the page's order: laid out, shown, then laid out again as the room changes
PLATE = """
const plate = root.getChildByLabel("plate", true);
wheel.layout(560, 700);
wheel.show();
const found = [];
for (const [width, height] of [[564, 335], [390, 433], [960, 745]]) {
  wheel.layout(width, height);
  const top = plate.toGlobal({ x: 0, y: 0 });
  const below = plate.toGlobal({ x: 0, y: 1 });
  found.push([plate.text, plate.style.fontSize * (below.y - top.y)]);
}
return found;
"""


def test_a_long_name_on_the_plate_is_cut_rather_than_shrunk_under_10_px(driver, live):
    open_casino(driver, live)
    found = on_wheel(driver, PLATE)
    assert isinstance(found, list), found
    name = "WOLFGANGMONTGOMERY"
    for words, px in found:
        assert px >= 10, (words, px)
        assert words.endswith("…") and name.startswith(words[:-1]), words
    assert not problems(driver)


# ---------- The result card ----------

# Keeps hold of the table's Pixi app when it starts, so a test can find the scene's parts by their labels
CATCH_APP = "window.__PIXI_APP_INIT__ = (app) => { window.vegasApp = app; };"
SCENE_DRAWN = "Boolean(window.vegasApp?.stage.getChildByLabel(arguments[0] === 'allin' ? 'wheel' : 'lever', true))"

# The result card's box, the scene's and the jackpot note's (null when hidden), and the boxes of what the card must
# not cover, all in the page's pixels: All In's wheel (its rim, which holds the turning face), pointer and name plate;
# the whole slot machine, crown and bulbs included, and within it the reels, lever, marquee jackpot, and the belly and
# payout tray below the reels, where the coins fly
CARD_PLACE = """
const app = window.vegasApp;
const canvas = document.querySelector("#scene canvas").getBoundingClientRect();
const rect = (node) => {
  const box = node.getBoundingClientRect();
  return [box.left, box.top, box.right, box.bottom];
};
const drawn = (label) => {
  const box = app.stage.getChildByLabel(label, true).getBounds();
  return [canvas.left + box.minX, canvas.top + box.minY, canvas.left + box.maxX, canvas.top + box.maxY];
};
let keep;
if (arguments[0] === "allin") {
  keep = { plate: drawn("plate"), wheel: drawn("rim"), pointer: drawn("pointer") };
} else {
  const machine = drawn("machine");
  const reels = [0, 1, 2].map((index) => drawn(`reel-${index}`));
  keep = { machine, lever: drawn("lever"), jackpot: drawn("jackpot-title") };
  keep.tray = [machine[0], reels[0][3], machine[2], machine[3]];
  reels.forEach((box, index) => {
    keep[`reel ${index}`] = box;
  });
}
const news = document.getElementById("news");
// The headline's lines as the card shows them, from where each of its letters sits
const words = document.getElementById("result-big").firstChild;
const range = document.createRange();
const lines = new Map();
for (let at = 0; at < words.length; at += 1) {
  range.setStart(words, at);
  range.setEnd(words, at + 1);
  const top = Math.round(range.getBoundingClientRect().top);
  lines.set(top, (lines.get(top) || "") + words.data[at]);
}
// Whether the headline's letters stay inside the card's padding, so none sits on the border
range.selectNodeContents(words);
const letters = range.getBoundingClientRect();
const inner = document.getElementById("result-big").getBoundingClientRect();
return {
  inside: inner.left - 0.5 <= letters.left && letters.right <= inner.right + 0.5,
  size: parseFloat(getComputedStyle(document.getElementById("result-big")).fontSize),
  lines: [...lines.values()].map((line) => line.replace(/\\s+/g, " ").trim()),
  card: rect(document.getElementById("result")),
  scene: rect(document.getElementById("scene")),
  news: news.hidden ? null : rect(news),
  keep,
};
"""

PAGE_SIZES = {
    "desktop": (1280, 800, 1, False),
    "phone": (390, 844, 2, True),
    "sideways": (844, 390, 2, True),
    # A small desktop window, where the side spot beside the machine is just wide enough to take the card
    "small-window": (960, 480, 1, False),
}


def play_for_the_card(driver, live, game):
    """A win at All In, or a jackpot at Slots, ending with the result card up"""
    if game == "allin":
        live.cog.rng = Rigged(ints=[0])
        driver.find_element(By.ID, "place").click()
        browser.wait_for(driver, "document.getElementById('confirm').open")
        driver.find_element(By.ID, "confirm-yes").click()
    else:
        live.cog.rng = Rigged(ints=[0, 0, 0])
        pick_bet(driver, 100)
        pull_lever(driver, 150)
    browser.wait_for(driver, "!document.getElementById('result').hidden", timeout=15)
    # The card's pop-in is over, the dock shows the new balance, and the scene and the card have had a frame to
    # follow the dock's new size
    browser.wait_for(driver, "document.getElementById('result').getAnimations().length === 0")
    balance = "2,000" if game == "allin" else "6,900"
    browser.wait_for(driver, f"document.getElementById('balance').textContent === '{balance}'")
    driver.execute_async_script("const done = arguments[0]; requestAnimationFrame(() => requestAnimationFrame(done));")


@pytest.mark.parametrize("size", list(PAGE_SIZES))
@pytest.mark.parametrize("game", ["allin", "slots"])
def test_the_result_card_covers_nothing_that_matters(driver, live, game, size):
    with at_size(driver, *PAGE_SIZES[size]):
        open_casino(driver, live)
        driver.execute_script(CATCH_APP)
        walk_up(driver, game)
        WebDriverWait(driver, 10).until(lambda _: driver.execute_script(f"return {SCENE_DRAWN}", game))
        play_for_the_card(driver, live, game)
        found = driver.execute_script(CARD_PLACE, game)
        card, scene = found["card"], found["scene"]
        assert scene[0] <= card[0] and scene[1] <= card[1] and card[2] <= scene[2] and card[3] <= scene[3], found
        for name, box in found["keep"].items():
            assert apart(card, box), f"{size}: the card covers the {name}"
        assert found["news"] is None or apart(card, found["news"]), f"{size}: the card covers the jackpot note"
        assert found["inside"], f"{size}: the headline runs past the card's padding: {found}"
        # A jackpot's headline that has to break does so after "Jackpot!", never inside "You win", and on a desktop
        # it keeps the card's full size, as big as any other win's
        if game == "slots":
            assert len(found["lines"]) == 1 or found["lines"][0] == "Jackpot!", found["lines"]
        if game == "slots" and size == "desktop":
            assert found["size"] == 22, found
        assert not problems(driver)


# The jackpot note's box and the slot machine's, crown and bulbs included, in the page's pixels
NOTE_AND_MACHINE = """
const canvas = document.querySelector("#scene canvas").getBoundingClientRect();
const box = window.vegasApp.stage.getChildByLabel("machine", true).getBounds();
const note = document.getElementById("news").getBoundingClientRect();
return {
  note: [note.left, note.top, note.right, note.bottom],
  machine: [canvas.left + box.minX, canvas.top + box.minY, canvas.left + box.maxX, canvas.top + box.maxY],
};
"""


@pytest.mark.parametrize("size", list(PAGE_SIZES))
def test_a_jackpot_note_covers_nothing_of_the_machine(driver, live, size):
    with at_size(driver, *PAGE_SIZES[size]):
        open_casino(driver, live)
        driver.execute_script(CATCH_APP)
        walk_up(driver, "slots")
        WebDriverWait(driver, 10).until(lambda _: driver.execute_script(f"return {SCENE_DRAWN}", "slots"))
        lever_ready(driver)
        assert news_after(driver, live, 31_000) == "Ann hit the jackpot: 48,000!"
        found = driver.execute_script(NOTE_AND_MACHINE)
        assert apart(found["note"], found["machine"]), found
        assert not problems(driver)
