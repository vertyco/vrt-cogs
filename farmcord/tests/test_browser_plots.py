"""The plot rooms in headless Chrome: a crop worked from tilling to harvest in Plot 1, the dig question, Plot 2 bought
as a pen and its chicken fed and watered, breeding from an animal's panel, a small animal tapped behind a big one, a
double tap that feeds once, the Pond filling the can, a tap that walks the farmer over before the bot hears of it, a
broken tap handler reported like any page bug, and the whole field on screen on an upright phone"""

import random

import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from farmcord.catalog import CANS, CROPS, DRY_STAGE_LOSS, PLOTS
from farmcord.game.animals import arrive
from farmcord.game.model import Animal, Item
from farmcord.game.progress import xp_for_level
from farmcord.tests import test_browser
from farmcord.tests.test_browser import (
    PAGE_BUG,
    PLAYER_ID,
    SIZES,
    browser,
    fakes,
    on_loop,
    open_farm,
    problems,
    saved_farm,
    text,
    toasts_seen,
    wait_until,
    walk,
    watch_toasts,
)

driver = test_browser.driver
live = test_browser.live
WILDFLOWERS = CROPS["wildflowers"]
# The exits from the farmhouse to each room
ROUTES = {
    "pond": [("right", "Yard"), ("up", "Pond")],
    "market": [("right", "Yard"), ("down", "Market")],
    "plot1": [("right", "Yard"), ("right", "Farmland"), ("up", "Plot 1")],
    "plot2": [("right", "Yard"), ("right", "Farmland"), ("down", "Plot 2")],
}


def keep_ctx(driver):
    """Keeps what room views work with (the page's ctx) as window.farm, so a test can find things on the farm"""
    driver.execute_async_script("""
      const done = arguments[arguments.length - 1];
      import("./game.js").then((game) => {
        for (const kind of ["farmhouse", "room", "yard", "pond", "market", "farmland", "plot"]) {
          const view = game.VIEWS[kind] || {};
          game.VIEWS[kind] = { ...view, enter: (ctx, room) => { window.farm = ctx; return view.enter?.(ctx, room); } };
        }
        done();
      });
    """)


def go_to(driver, live, room):
    open_farm(driver, live)
    keep_ctx(driver)
    for direction, name in ROUTES[room]:
        walk(driver, direction, name)
    # The farmer finishes walking in, so his next walk starts from where he stands
    browser.wait_for(driver, "window.farm && !window.farm.scene.farmer.walk")


def place_of(driver, label):
    """Where on the canvas to tap something on the farm, by its label: "spot:4", "animal:<id>" or "pond". Its own point
    (a spot's soil, the Pond's water) when its hit shape takes it; else the point deepest inside its hit shape (an
    animal's body, so a tap still lands while it walks); else the middle of its picture"""
    browser.wait_for(driver, f"window.farm.scene.targets.some((t) => t.node.label === '{label}')")
    return driver.execute_script(
        """
        const scene = window.farm.scene;
        const target = scene.targets.find((t) => t.node.label === arguments[0]);
        const takes = (point) => target.hit(scene.world.toLocal(point));
        const box = target.node.getBounds().rectangle;
        let at = target.node.getGlobalPosition();
        if (!target.hit) {
          at = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
        } else if (!takes(at)) {
          const grid = [];
          for (let i = 0; i <= 20; i += 1) {
            for (let j = 0; j <= 20; j += 1) {
              const point = { x: box.x + (box.width * i) / 20, y: box.y + (box.height * j) / 20 };
              grid.push({ ...point, in: takes(point) });
            }
          }
          const out = grid.filter((point) => !point.in);
          const depth = (p) => Math.min(...out.map((q) => (q.x - p.x) ** 2 + (q.y - p.y) ** 2));
          at = grid.filter((point) => point.in).reduce((best, point) => (depth(point) > depth(best) ? point : best));
        }
        const canvas = scene.app.canvas.getBoundingClientRect();
        return [at.x - canvas.width / 2, at.y - canvas.height / 2];
        """,
        label,
    )


def tap(driver, label, clicks=1):
    """Clicks something on the farm by its label, once or more, as fast as a double tap"""
    x, y = place_of(driver, label)
    canvas = driver.find_element(By.CSS_SELECTOR, "#stage canvas")
    actions = ActionChains(driver).move_to_element_with_offset(canvas, round(x), round(y))
    for _ in range(clicks):
        actions.click()
    actions.perform()


def hold(driver, tool):
    driver.find_element(By.CSS_SELECTOR, f'.tool[data-tool="{tool}"]').click()


def pick(driver, tool, key):
    hold(driver, tool)
    browser.wait_for(driver, "!document.getElementById('picker').hidden")
    choice = driver.find_element(By.CSS_SELECTOR, f'#picker-list .choice[data-key="{key}"]')
    words = choice.text.split("\n")
    choice.click()
    return words


def refresh(driver):
    """Has the page ask the bot for the farm, as it does when a moment it shows passes"""
    driver.execute_async_script("window.farm.refresh().then(arguments[arguments.length - 1])")


def spot(live, plot, index):
    return saved_farm(live).plots[plot].spots[index]


async def make_pen(cog, *animals, **changes):
    """Plot 2 as a pen holding `animals` (Animal, how long ago it arrived), with the farm's other fields changed"""
    farm = await cog.store.load(PLAYER_ID)
    farm.plots[2].unlocked = True
    farm.plots[2].kind = "animals"
    for animal, ago in animals:
        animal.plot = 2
        arrive(animal, cog.clock() - ago)
        farm.animals.append(animal)
    for name, value in changes.items():
        setattr(farm, name, value)
    await cog.store.save(farm)


def grown(kind, sex):
    return Animal(kind=kind, sex=sex, adult=True, value=85)


@pytest.fixture
def still(driver):
    """Reduced motion: pen animals stand where they first appear, apart, so a tap can't land on one walking past"""
    driver.execute_cdp_cmd(
        "Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]}
    )
    yield
    driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"features": []})


def test_a_tap_walks_the_farmer_there_before_the_bot_hears_of_it(driver, live):
    go_to(driver, live, "plot1")
    hold(driver, "hoe")
    tap(driver, "spot:0")
    # The farmer sets off across the field, and the bot hears nothing until he gets there
    assert driver.execute_script("return window.farm.scene.farmer.walk !== null")
    assert spot(live, 1, 0).state == "untilled"
    wait_until(driver, lambda: spot(live, 1, 0).state == "tilled")
    where = driver.execute_script("const f = window.farm.scene.farmer; return [f.x, f.y]")
    goal = driver.execute_script(
        "const t = window.farm.scene.targets.find((t) => t.node.label === 'spot:0'); return [t.walkTo.x, t.walkTo.y]"
    )
    assert where == goal
    assert spot(live, 1, 1).state == "untilled"
    assert not problems(driver)


def test_a_crop_is_tilled_planted_watered_and_harvested_in_plot_1(driver, live):
    go_to(driver, live, "plot1")
    hold(driver, "hoe")
    tap(driver, "spot:4")
    wait_until(driver, lambda: spot(live, 1, 4).state == "tilled")
    # The seed picker gives each seed's grow time today: Wildflowers are in season
    assert pick(driver, "seed", "seed:wildflowers") == ["Wildflowers", "Grows in 30 min", "5"]
    tap(driver, "spot:4")
    wait_until(driver, lambda: spot(live, 1, 4).state == "growing")
    assert saved_farm(live).items["seed:wildflowers"].quantity == 4
    hold(driver, "can")
    tap(driver, "spot:4")
    wait_until(driver, lambda: spot(live, 1, 4).watered == 1)
    assert saved_farm(live).water == CANS[0].capacity - 1
    browser.wait_for(driver, "document.querySelector('.tool[data-tool=\"can\"] .badge').textContent === '9/10'")
    # Watered soil looks wet; the dry spots around it don't
    tints = driver.execute_script(
        "return Object.fromEntries(window.farm.scene.targets.filter((t) => t.node.label?.startsWith('spot:'))"
        ".map((t) => [t.node.label, t.node.getChildByLabel('crop').tint]))"
    )
    assert tints["spot:4"] != 0xFFFFFF and tints["spot:3"] == 0xFFFFFF
    # The hand only looks at a growing crop: what it is and how long until it's ripe
    hold(driver, "hand")
    tap(driver, "spot:4")
    look = browser.wait_for(driver, "[...document.querySelectorAll('#toasts .toast')].at(-1)?.textContent")
    assert look.startswith("Wildflowers: just planted, ripe in 30 min.") and "Watered for this stage" in look
    live.cog.clock.move(WILDFLOWERS.grow_time + 1)
    refresh(driver)
    # Ripe: it sparkles
    browser.wait_for(
        driver, "!!window.farm.scene.targets.find((t) => t.node.label === 'spot:4').node.getChildByLabel('sparkle')"
    )
    tap(driver, "spot:4")
    wait_until(driver, lambda: spot(live, 1, 4).state == "untilled")
    # The popup tells what the harvest brought. Stages 2 and 3 went dry
    farm = saved_farm(live)
    exceptional = "crop:wildflowers:x" in farm.items
    amount = farm.items["crop:wildflowers:x" if exceptional else "crop:wildflowers"].quantity
    xp = round(WILDFLOWERS.xp * (1 - 2 * DRY_STAGE_LOSS) * (2 if exceptional else 1))
    popup = browser.wait_for(driver, "document.querySelector('#toasts .toast.harvest')?.textContent")
    assert popup.startswith(f"+{amount} {'exceptional ' if exceptional else ''}Wildflowers")
    assert popup.endswith(f"+{xp} XP")
    assert ("free seed" in popup) == (farm.items["seed:wildflowers"].quantity > 4)
    assert not problems(driver)


def test_the_hoe_asks_before_digging_up_a_crop(driver, live):
    ctx = fakes.context_for(live.hub)
    on_loop(live, live.cog.act_open(ctx, {}))
    # Crops on spot 4 and on spot 8 in front of it, whose plants stand over spot 4's soil
    for index in (4, 8):
        on_loop(live, live.cog.act_till(ctx, {"plot": 1, "spot": index}))
        on_loop(live, live.cog.act_plant(ctx, {"plot": 1, "spot": index, "crop": "wildflowers"}))
    go_to(driver, live, "plot1")
    hold(driver, "hoe")
    tap(driver, "spot:4")
    browser.wait_for(driver, "document.getElementById('confirm').open")
    assert text(driver, "confirm-text") == "Dig up the wildflowers?"
    driver.find_element(By.ID, "confirm-no").click()
    browser.wait_for(driver, "!document.getElementById('confirm').open")
    assert spot(live, 1, 4).state == "growing"
    tap(driver, "spot:4")
    browser.wait_for(driver, "document.getElementById('confirm').open")
    driver.find_element(By.ID, "confirm-yes").click()
    wait_until(driver, lambda: spot(live, 1, 4).state == "untilled")
    assert spot(live, 1, 8).state == "growing"
    assert not problems(driver)


def test_plot_2_is_bought_as_a_pen_and_its_chicken_fed_and_watered(driver, live):
    go_to(driver, live, "plot2")
    # Too low a level: the plot shows what it needs and can't be bought yet
    card = browser.wait_for(
        driver, "!document.getElementById('plot-card').hidden && document.getElementById('plot-card')"
    )
    assert "Plot 2" in card.text and "Level 5" in card.text and f"{PLOTS[2].price:,}" in card.text
    assert not driver.find_element(By.ID, "plot-unlock").is_enabled()
    on_loop(live, test_browser.change_farm(live.cog, level=5, xp=xp_for_level(5), coins=PLOTS[2].price + 100))
    refresh(driver)
    browser.wait_for(driver, "!document.getElementById('plot-unlock').disabled")
    driver.find_element(By.ID, "plot-unlock").click()
    browser.wait_for(driver, "document.getElementById('panel').open")
    driver.find_element(By.CSS_SELECTOR, '.kind-choice[data-kind="animals"]').click()
    wait_until(driver, lambda: saved_farm(live).plots[2].unlocked)
    farm = saved_farm(live)
    assert farm.plots[2].kind == "animals" and farm.coins == 100
    browser.wait_for(driver, "!document.getElementById('panel').open && document.getElementById('plot-card').hidden")
    # An empty pen can turn back into a crop plot, for the switching fee
    switch = browser.wait_for(
        driver, "!document.getElementById('plot-switch').hidden && document.getElementById('plot-switch')"
    )
    assert "crop plot" in switch.text and "250" in switch.text
    # A chicken and its feed, put on the farm directly, an hour before she gets hungry
    chicken = Animal(kind="chicken", sex="female")
    on_loop(live, make_pen(live.cog, (chicken, 0), items={"feed:chicken": Item("feed:chicken", 3)}))
    live.cog.clock.move(3600)
    refresh(driver)
    browser.wait_for(driver, "document.getElementById('plot-switch').hidden")
    assert pick(driver, "feed", "feed:chicken") == ["Chicken feed", "3"]
    tap(driver, f"animal:{chicken.id}")
    wait_until(driver, lambda: saved_farm(live).items["feed:chicken"].quantity == 2)
    assert saved_farm(live).animals[0].fed_at == live.cog.clock()
    hold(driver, "can")
    tap(driver, f"animal:{chicken.id}")
    wait_until(driver, lambda: saved_farm(live).animals[0].watered_at == live.cog.clock())
    assert saved_farm(live).water == CANS[0].capacity - 1
    assert not problems(driver)


def test_an_empty_plot_turns_into_a_pen_after_the_player_says_yes(driver, live):
    ctx = fakes.context_for(live.hub)
    on_loop(live, live.cog.act_open(ctx, {}))
    farm = saved_farm(live)
    farm.plots[2].unlocked = True
    farm.coins = 300
    on_loop(live, live.cog.store.save(farm))
    go_to(driver, live, "plot2")
    switch = browser.wait_for(
        driver, "!document.getElementById('plot-switch').hidden && document.getElementById('plot-switch')"
    )
    assert "Make it a pen" in switch.text and "250" in switch.text
    switch.click()
    browser.wait_for(driver, "document.getElementById('confirm').open")
    assert text(driver, "confirm-text") == "Turn Plot 2 into a pen for 250 FarmCoins?"
    driver.find_element(By.ID, "confirm-no").click()
    browser.wait_for(driver, "!document.getElementById('confirm').open")
    driver.execute_async_script("setTimeout(arguments[arguments.length - 1], 500)")
    assert (saved_farm(live).plots[2].kind, saved_farm(live).coins) == ("crops", 300)
    switch.click()
    browser.wait_for(driver, "document.getElementById('confirm').open")
    driver.find_element(By.ID, "confirm-yes").click()
    wait_until(driver, lambda: saved_farm(live).plots[2].kind == "animals")
    farm = saved_farm(live)
    assert (farm.coins, farm.switches) == (50, 1)
    # Back to crops costs the next fee, twice the last
    browser.wait_for(driver, "document.getElementById('plot-switch').textContent.includes('crop plot')")
    assert "500" in text(driver, "plot-switch")
    assert not problems(driver)


def test_a_hen_breeds_from_her_panel_and_a_failed_try_says_so(driver, live, still):
    ctx = fakes.context_for(live.hub)
    on_loop(live, live.cog.act_open(ctx, {}))
    hen, rooster = grown("chicken", "female"), grown("chicken", "male")
    on_loop(live, make_pen(live.cog, (hen, 3600), (rooster, 3600)))
    # The first roll fails
    live.cog.rng = random.Random(2)
    go_to(driver, live, "plot2")
    tap(driver, f"animal:{rooster.id}")
    browser.wait_for(driver, "document.getElementById('panel').open")
    assert driver.find_elements(By.ID, "breed") == []
    driver.find_element(By.ID, "panel-close").click()
    tap(driver, f"animal:{hen.id}")
    browser.wait_for(driver, "document.getElementById('panel').open")
    assert text(driver, "panel-title") == "Chicken"
    driver.find_element(By.ID, "breed").click()
    wait_until(driver, lambda: saved_farm(live).animals[0].tried_at == live.cog.clock())
    toast = browser.wait_for(driver, "[...document.querySelectorAll('#toasts .toast')].at(-1)?.textContent")
    assert toast == "No luck this time. Try again in 2 hours."
    # The panel follows the new state: no Breed button while she rests
    browser.wait_for(driver, "!document.getElementById('breed') && document.querySelector('.breed-note')")
    live.cog.clock.move(2 * 3600)
    live.cog.rng = random.Random(1)
    refresh(driver)
    browser.wait_for(driver, "document.getElementById('breed')").click()
    wait_until(driver, lambda: saved_farm(live).animals[0].bred)
    browser.wait_for(driver, "document.querySelector('.breed-note')?.textContent === \"She's already expecting\"")
    assert not problems(driver)


async def change_animal(cog, animal_id, **changes):
    farm = await cog.store.load(PLAYER_ID)
    animal = next(animal for animal in farm.animals if animal.id == animal_id)
    for name, value in changes.items():
        setattr(animal, name, value)
    await cog.store.save(farm)


def breed_note(driver, words):
    browser.wait_for(driver, f"document.querySelector('.breed-note')?.textContent === {words!r}")
    assert driver.find_elements(By.ID, "breed") == []


def test_a_female_is_told_in_the_bots_words_why_she_cant_breed(driver, live, still):
    ctx = fakes.context_for(live.hub)
    on_loop(live, live.cog.act_open(ctx, {}))
    hen = grown("chicken", "female")
    on_loop(live, make_pen(live.cog, (hen, 3600)))
    go_to(driver, live, "plot2")
    tap(driver, f"animal:{hen.id}")
    breed_note(driver, "She needs a healthy grown-up male chicken in her pen")
    # The panel follows each new state. A rooster arrives, but she tried for babies half an hour ago
    on_loop(live, make_pen(live.cog, (grown("chicken", "male"), 3600)))
    on_loop(live, change_animal(live.cog, hen.id, tried_at=live.cog.clock() - 1800))
    refresh(driver)
    breed_note(driver, "She needs a rest. Try again in 90 minutes")
    on_loop(live, change_animal(live.cog, hen.id, tried_at=0.0, bred=True))
    refresh(driver)
    breed_note(driver, "She's already had her babies")
    assert not problems(driver)


def test_the_watering_can_fills_at_the_pond(driver, live):
    ctx = fakes.context_for(live.hub)
    on_loop(live, live.cog.act_open(ctx, {}))
    on_loop(live, test_browser.change_farm(live.cog, water=3))
    go_to(driver, live, "pond")
    hold(driver, "can")
    tap(driver, "pond")
    wait_until(driver, lambda: saved_farm(live).water == CANS[0].capacity)
    browser.wait_for(driver, "document.querySelector('.tool[data-tool=\"can\"] .badge').textContent === '10/10'")
    assert not problems(driver)


def panel_title_after_tapping(driver, label):
    tap(driver, label)
    browser.wait_for(driver, "document.getElementById('panel').open")
    title = text(driver, "panel-title")
    driver.find_element(By.ID, "panel-close").click()
    browser.wait_for(driver, "!document.getElementById('panel').open")
    return title


def test_a_small_animal_behind_a_big_one_still_takes_its_own_taps(driver, live, still):
    ctx = fakes.context_for(live.hub)
    on_loop(live, live.cog.act_open(ctx, {}))
    # The hen takes the pen's first place and a grown cow its fourth
    hen, cow = grown("chicken", "female"), grown("cow", "female")
    others = [grown("chicken", "male"), Animal(kind="chicken", sex="male")]
    on_loop(live, make_pen(live.cog, (hen, 3600), *[(other, 3600) for other in others], (cow, 3600)))
    go_to(driver, live, "plot2")
    assert panel_title_after_tapping(driver, f"animal:{hen.id}") == "Chicken"
    assert panel_title_after_tapping(driver, f"animal:{cow.id}") == "Cow"
    # The cow moves just in front of the hen and to her right, so the empty corner of its picture covers the spot on
    # the hen a player taps, but its body doesn't. The tap is still the hen's
    x, y = place_of(driver, f"animal:{hen.id}")
    covered = driver.execute_script(
        """
        const scene = window.farm.scene;
        const canvas = scene.app.canvas.getBoundingClientRect();
        const screen = { x: arguments[0] + canvas.width / 2, y: arguments[1] + canvas.height / 2 };
        const point = scene.world.toLocal(screen);
        const cow = scene.targets.find((t) => t.node.label === `animal:${arguments[2]}`);
        cow.node.position.set(point.x + 60, point.y + 40);
        cow.node.zIndex = cow.node.y;
        return [cow.node.getBounds().rectangle.contains(screen.x, screen.y), Boolean(cow.hit?.(point))];
        """,
        x,
        y,
        cow.id,
    )
    assert covered == [True, False]
    assert panel_title_after_tapping(driver, f"animal:{hen.id}") == "Chicken"
    assert not problems(driver)


def test_a_double_tap_feeds_an_animal_once(driver, live, still):
    ctx = fakes.context_for(live.hub)
    on_loop(live, live.cog.act_open(ctx, {}))
    hen = grown("chicken", "female")
    on_loop(live, make_pen(live.cog, (hen, 3600), items={"feed:chicken": Item("feed:chicken", 3)}))
    go_to(driver, live, "plot2")
    pick(driver, "feed", "feed:chicken")
    # The bot is busy with the player's farm, so the first feeding is still on its way when the second tap lands
    lock = live.cog.locks[PLAYER_ID]
    on_loop(live, lock.acquire())
    try:
        tap(driver, f"animal:{hen.id}", clicks=2)
        driver.execute_async_script("setTimeout(arguments[arguments.length - 1], 500)")
    finally:
        live.loop.call_soon_threadsafe(lock.release)
    wait_until(driver, lambda: saved_farm(live).items["feed:chicken"].quantity < 3)
    driver.execute_async_script("setTimeout(arguments[arguments.length - 1], 1000)")
    assert saved_farm(live).items["feed:chicken"].quantity == 2
    assert not problems(driver)


def test_a_broken_tap_handler_is_reported_like_any_page_bug(driver, live):
    go_to(driver, live, "plot1")
    watch_toasts(driver)
    driver.execute_script("window.farm.tool = () => { throw new Error('the tool in hand broke'); }")
    tap(driver, "spot:4")
    seen = browser.wait_for_console(driver, "the tool in hand broke")
    assert [line for line in seen if "tool in hand broke" in line and "FarmCord:" not in line] == []
    browser.wait_for(driver, "window.toastsSeen.length")
    assert toasts_seen(driver) == [f"toast error: {PAGE_BUG}"]


@pytest.mark.parametrize("room", ["plot1", "plot2"])
def test_an_upright_phone_opens_a_plot_with_its_whole_field_on_screen(driver, live, room):
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES["phone"])
    try:
        go_to(driver, live, room)
        # The fence's left and right corners, where the camera has settled
        driver.execute_async_script("setTimeout(arguments[arguments.length - 1], 1500)")
        corners = driver.execute_script(
            """
            const world = window.farm.scene.world;
            return [world.toGlobal({ x: 310, y: 480 }).x, world.toGlobal({ x: 970, y: 480 }).x, innerWidth];
            """
        )
        assert 0 <= corners[0] and corners[1] <= corners[2], corners
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
