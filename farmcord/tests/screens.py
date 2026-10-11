"""Screenshots of the farm for checking the page by eye. Not collected with the tests; run it by name:

    pytest farmcord/tests/screens.py

It saves the Yard and Plot 1 at desktop, upright phone and sideways phone sizes, every other kind of room at desktop
size, the Yard in each season and in rain and snow, the plots (a growing field, a ripe field, a pen, a plot for sale
and the dig question), the Market (the room, each shop tab, the bank counter and the payout settings) and the
farmhouse (the room, each board tab, the wardrobe, a decorated extra room, its decorations tray and a decorated Yard)
at desktop and upright phone sizes, to the folder in the FARMCORD_SHOTS environment variable (default:
./farmcord-shots)
"""

import os
from pathlib import Path

import pytest
from selenium.webdriver.common.by import By

from farmcord.catalog import CROPS, PLOTS
from farmcord.game.animals import arrive
from farmcord.game.calendar import DAY, EPOCH, HOUR, season_at, weather_at
from farmcord.game.model import Animal, Decoration, Item, new_farm
from farmcord.game.progress import xp_for_level
from farmcord.tests import test_browser
from farmcord.tests.test_browser import PLAYER_ID, SIZES, browser, fakes, on_loop, open_farm, walk
from farmcord.tests.test_browser_house import go_home
from farmcord.tests.test_browser_plots import go_to, hold, tap

driver = test_browser.driver
live = test_browser.live
# The exits to take from the farmhouse to reach each room shot
ROUTES = {
    "farmhouse": [],
    "yard": [("right", "Yard")],
    "pond": [("right", "Yard"), ("up", "Pond")],
    "market": [("right", "Yard"), ("down", "Market")],
    "farmland": [("right", "Yard"), ("right", "Farmland")],
    "plot1": [("right", "Yard"), ("right", "Farmland"), ("up", "Plot 1")],
}
SHOTS = [(room, size) for room in ("yard", "plot1") for size in SIZES]
SHOTS += [(room, "desktop") for room in ("farmhouse", "pond", "market", "farmland")]
# A growing field, spot by spot: None (untilled), "tilled", or (crop, stage, watered)
GROWING = [
    None,
    "tilled",
    ("wildflowers", 0, True),
    ("wheat", 1, True),
    ("corn", 2, False),
    ("sunflowers", 0, False),
    "tilled",
    ("pumpkin", 1, False),
    ("blueberries", 2, True),
]
# A ripe field, spot by spot: "rotted", or (crop, hours since it ripened)
RIPE = [
    ("wildflowers", 1),
    ("wheat", 2),
    ("corn", 10),
    ("sunflowers", 30),
    ("pumpkin", 0.5),
    "rotted",
    ("blueberries", 3),
    ("tulips", 1),
    ("lilies", 12),
]
# A pen: (kind, sex, grown up, what ails it)
PEN = [
    ("chicken", "female", True, None),
    ("chicken", "male", True, None),
    ("chicken", "female", False, None),
    ("cow", "female", True, "sickly"),
    ("cow", "male", False, None),
    ("pig", "male", True, "malnourished"),
]
PLOT_SHOTS = ["growing", "ripe", "pen", "locked", "dig"]
MARKET_SHOTS = ["room", "stuck", "seeds", "animals", "feed", "tools", "sell", "looks", "clothes", "bank", "payouts"]
# The farmhouse's shots, and the board tab each board shot opens
BOARD_SHOTS = {
    "board": "farm",
    "storage": "storage",
    "animals": "animals",
    "badges": "badges",
    "leaderboard": "leaders",
    "about": "about",
}
HOUSE_SHOTS = ["room", *BOARD_SHOTS, "wardrobe", "decorated", "decorating", "yard"]
# The farmhouse's farm: its storage, its decorations (item, where, x and y shares of the room; None: not placed) and
# its animals (kind, sex, grown up, pen; None: waiting in the farmhouse)
HOUSE_STOCK = {
    "seed:wildflowers": Item("seed:wildflowers", 12),
    "seed:corn": Item("seed:corn", 30),
    "crop:wheat": Item("crop:wheat", 7, 120),
    "crop:pumpkin:x": Item("crop:pumpkin:x", 2, 1424),
    "feed:goat": Item("feed:goat", 18),
}
HOUSE_DECORATIONS = [
    ("well", "room2", 0.74, 0.73),
    ("garden_gnome", "room2", 0.65, 0.8),
    ("bench", "room2", 0.35, 0.75),
    ("flower_pot", "room2", 0.24, 0.75),
    ("flower_pot", "room2", 0.45, 0.75),
    ("lantern", "room2", 0.54, 0.92),
    ("windmill", "yard", 0.61, 0.44),
    ("scarecrow", "yard", 0.86, 0.72),
    ("hay_bale", "yard", 0.36, 0.87),
    ("wooden_fence", "yard", 0.71, 0.92),
    ("birdhouse", None, 0, 0),
    ("flower_pot", None, 0, 0),
    ("flower_pot", None, 0, 0),
    ("hay_bale", None, 0, 0),
]
HOUSE_ANIMALS = [
    ("goat", "female", True, 2),
    ("goat", "male", True, 2),
    ("chicken", "female", True, 2),
    ("goat", "female", False, None),
    ("goat", "male", False, None),
]
# The Market's farm: what it holds in storage, and its pen: (kind, sex, grown up, what ails it, expecting)
STOCK = {
    "seed:wildflowers": Item("seed:wildflowers", 12),
    "seed:tulips": Item("seed:tulips", 4),
    "feed:chicken": Item("feed:chicken", 25),
    "crop:wheat": Item("crop:wheat", 7, 120),
    "crop:tulips": Item("crop:tulips", 3, 27),
    "crop:tulips:x": Item("crop:tulips:x", 1, 18),
}
MARKET_PEN = [
    ("chicken", "female", True, None, True),
    ("chicken", "male", True, None, False),
    ("chicken", "female", False, None, False),
    ("goose", "female", True, "sickly", False),
]


def folder() -> Path:
    path = Path(os.environ.get("FARMCORD_SHOTS", "farmcord-shots"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def shoot(chrome, name: str) -> None:
    # Long enough for the farmer to finish walking in
    chrome.execute_script("return new Promise((resolve) => setTimeout(resolve, 1200))")
    chrome.switch_to.default_content()
    chrome.save_screenshot(str(folder() / f"{name}.png"))
    chrome.switch_to.frame(chrome.find_element(By.ID, "game-frame"))


def first_day(season: str, weather: str) -> float:
    """1 a.m. UTC on the first day with this season and weather"""
    for day in range(400):
        moment = EPOCH + day * DAY + HOUR
        if season_at(moment) == season and weather_at(moment) == weather:
            return moment
    raise AssertionError(f"No {weather} day in {season}")


@pytest.mark.parametrize("room, size", SHOTS)
def test_rooms(driver, live, room, size):  # noqa: F811
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES[size])
    try:
        open_farm(driver, live)
        for direction, name in ROUTES[room]:
            walk(driver, direction, name)
        shoot(driver, f"{room}-{size}")
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


@pytest.mark.parametrize(
    "season, weather",
    [
        ("spring", "sun"),
        ("summer", "sun"),
        ("autumn", "sun"),
        ("winter", "sun"),
        ("summer", "rain"),
        ("winter", "snow"),
    ],
)
def test_yard_seasons(driver, live, season, weather):  # noqa: F811
    live.cog.clock.now = first_day(season, weather)
    open_farm(driver, live)
    walk(driver, "right", "Yard")
    shoot(driver, f"yard-{season}-{weather}")


def grow(spot, crop: str, planted_ago: float, watered: int) -> None:
    spot.state, spot.crop, spot.stage_len = "growing", crop, CROPS[crop].grow_time / 3
    spot.planted_at -= planted_ago
    spot.watered = watered


async def set_farm(cog, plots: dict, animals: list) -> None:
    """A level 60 farm, settled now, with its plots' spots and its pen's animals laid out"""
    farm = await cog.store.load(PLAYER_ID)
    now = cog.clock()
    farm.level, farm.xp, farm.coins = 60, xp_for_level(60), PLOTS[2].price + 250
    farm.settled_at = now
    for number, plan in plots.items():
        for spot, what in zip(farm.plots[number].spots, plan):
            spot.planted_at = now
            if what in ("tilled", "rotted"):
                spot.state, spot.crop = what, "tulips" if what == "rotted" else None
            elif what and len(what) == 3:
                crop, stage, watered = what
                grow(spot, crop, (stage + 0.5) * CROPS[crop].grow_time / 3, (1 << stage) if watered else 0)
            elif what:
                crop, hours = what
                grow(spot, crop, CROPS[crop].grow_time + hours * HOUR, 0b111)
    for kind, sex, adult, ails in animals:
        farm.plots[2].unlocked, farm.plots[2].kind = True, "animals"
        animal = Animal(kind=kind, sex=sex, plot=2, adult=adult, value=100)
        arrive(animal, now - HOUR)
        if ails:
            setattr(animal, ails, True)
        farm.animals.append(animal)
    await cog.store.save(farm)


@pytest.mark.parametrize("shot", PLOT_SHOTS)
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_plots(driver, live, shot, size):  # noqa: F811
    on_loop(live, live.cog.act_open(fakes.context_for(live.hub), {}))
    field = {"growing": GROWING, "ripe": RIPE, "dig": GROWING}.get(shot)
    on_loop(live, set_farm(live.cog, {1: field} if field else {}, PEN if shot == "pen" else []))
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES[size])
    try:
        go_to(driver, live, "plot2" if shot in ("pen", "locked") else "plot1")
        if shot == "dig":
            hold(driver, "hoe")
            tap(driver, "spot:4")
            driver.execute_script(
                "return new Promise((r) => { const t = setInterval(() => { if (document.getElementById('confirm').open) { clearInterval(t); r(); } }, 50); })"
            )
        shoot(driver, f"plot-{shot}-{size}")
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


async def market_farm(cog) -> None:
    """A level 12 farm with FarmCoins, seeds, feed and crops to sell, a pen in Plot 2, a better can, two outfit pieces
    and a rival farm ahead of it on the leaderboard"""
    farm = await cog.store.load(PLAYER_ID)
    now = cog.clock()
    farm.level, farm.xp, farm.coins, farm.can_tier = 12, xp_for_level(12) + 40, 1480, 1
    farm.items = {key: Item(item.key, item.quantity, item.worth) for key, item in STOCK.items()}
    farm.outfits = {"straw_hat", "plaid_shirt"}
    farm.plots[2].unlocked, farm.plots[2].kind = True, "animals"
    for kind, sex, adult, ails, expecting in MARKET_PEN:
        animal = Animal(kind=kind, sex=sex, plot=2, adult=adult, value=95 if adult else 0)
        arrive(animal, now - HOUR)
        if ails:
            setattr(animal, ails, True)
        if expecting:
            animal.bred, animal.litter, animal.pregnant_until = True, 2, now + HOUR
        farm.animals.append(animal)
    await cog.store.save(farm)
    rival = new_farm(fakes.OWNER_ID, "Hayseed Hannah", now)
    rival.level, rival.xp = 31, xp_for_level(31) + 900
    await cog.store.save(rival)


def show_market(driver, live, shot) -> None:
    """Opens what the shot shows, once the farmer stands in the Market"""
    if shot in ("seeds", "animals", "feed", "tools", "sell", "looks", "clothes"):
        tap(driver, "stall")
        browser.wait_for(driver, "document.getElementById('panel').open")
        driver.find_element(By.CSS_SELECTOR, f'.shop-tab[data-tab="{"looks" if shot == "clothes" else shot}"]').click()
        if shot == "clothes":
            driver.execute_script("document.querySelectorAll('.shop-heading')[1].scrollIntoView()")
    elif shot in ("bank", "payouts"):
        tap(driver, "bank")
        browser.wait_for(driver, "document.getElementById('bank-offer')?.textContent")
        if shot == "payouts":
            driver.find_element(By.ID, "bank-gear").click()
            browser.wait_for(driver, "document.getElementById('payouts').open")


@pytest.mark.parametrize("shot", MARKET_SHOTS)
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_market(driver, live, shot, size):  # noqa: F811
    """The payout settings are shown to a server admin, everything else to a player"""
    if shot == "payouts":
        live.user_id = fakes.MANAGER_ID
    ctx = fakes.context_for(live.hub, user_id=live.user_id)
    on_loop(live, live.cog.act_open(ctx, {}))
    on = {"on": True, "rate": 2, "cap": 1000, "plays": 3}
    on_loop(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set(on))
    if shot == "stuck":
        on_loop(live, test_browser.change_farm(live.cog, items={}))
    elif shot != "payouts":
        on_loop(live, market_farm(live.cog))
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES[size])
    try:
        go_to(driver, live, "market")
        show_market(driver, live, shot)
        shoot(driver, f"market-{shot}-{size}")
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


async def house_farm(cog) -> None:
    """A level 55 farm with both extra rooms, a stocked storage, a pen, two babies waiting, some badges, a wardrobe of
    clothes worn in part, decorations in its Yard and second room and a few left to place, and two rival farms"""
    farm = await cog.store.load(PLAYER_ID)
    now = cog.clock()
    farm.level, farm.xp, farm.coins, farm.rooms, farm.storage_tier = 55, xp_for_level(55) + 300, 7400, 2, 1
    farm.can_tier, farm.water, farm.hoe_tier = 2, 37, 1
    farm.items = {key: Item(item.key, item.quantity, item.worth) for key, item in HOUSE_STOCK.items()}
    farm.achievements = {key: now - DAY for key in ("first_crop", "free_seeds", "sell_crop", "exceptional_crop")}
    farm.outfits = {"straw_hat", "cap", "plaid_shirt", "t_shirt", "blue_overalls", "jeans"}
    farm.hat, farm.top, farm.bottom = "straw_hat", "plaid_shirt", "blue_overalls"
    farm.descriptions = {2: "Grandma's quilt room. Mind the gnome by the well, he bites."}
    farm.decorations = [Decoration(item=item, room=room, x=x, y=y) for item, room, x, y in HOUSE_DECORATIONS]
    farm.plots[2].unlocked, farm.plots[2].kind = True, "animals"
    for kind, sex, adult, plot in HOUSE_ANIMALS:
        animal = Animal(kind=kind, sex=sex, plot=plot, adult=adult, value=95 if adult else 0)
        arrive(animal, now - HOUR)
        farm.animals.append(animal)
    await cog.store.save(farm)
    for user_id, name, level in ((fakes.OWNER_ID, "Hayseed Hannah", 71), (fakes.MANAGER_ID, "Tractor Tom", 38)):
        rival = new_farm(user_id, name, now)
        rival.level, rival.xp = level, xp_for_level(level) + 120
        await cog.store.save(rival)


def show_house(driver, live, shot) -> None:
    """Opens what the shot shows, once the farmer stands in the farmhouse"""
    if shot in BOARD_SHOTS:
        tap(driver, "board")
        browser.wait_for(driver, "document.getElementById('panel').open")
        tab = BOARD_SHOTS[shot]
        driver.find_element(By.CSS_SELECTOR, f'.board .shop-tab[data-tab="{tab}"]').click()
        if tab == "leaders":
            browser.wait_for(driver, "document.querySelectorAll('.leaders li').length")
    elif shot == "wardrobe":
        tap(driver, "wardrobe")
        browser.wait_for(driver, "document.getElementById('panel').open")
        driver.find_element(By.CSS_SELECTOR, '.outfit-choice[data-slot="hat"][data-key="cap"]').click()
    elif shot in ("decorated", "decorating"):
        walk(driver, "left", "Second room")
        if shot == "decorating":
            driver.find_element(By.ID, "decorate").click()
    elif shot == "yard":
        walk(driver, "right", "Yard")


@pytest.mark.parametrize("shot", HOUSE_SHOTS)
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_house(driver, live, shot, size):  # noqa: F811
    on_loop(live, live.cog.act_open(fakes.context_for(live.hub), {}))
    on_loop(live, house_farm(live.cog))
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES[size])
    try:
        go_home(driver, live)
        show_house(driver, live, shot)
        shoot(driver, f"house-{shot}-{size}")
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
