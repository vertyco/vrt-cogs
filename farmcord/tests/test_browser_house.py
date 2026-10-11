"""The farmhouse in headless Chrome: the board (a new farm's seeds, tools and badges, throwing seeds away, a waiting
baby moved into a pen, storage bought once on a double tap, the leaderboard and the About panel), an extra room
bought, described and decorated by dragging (kept as shares of the whole room), decorations dragged into the Yard by
touch, a decoration dropped on the tray put away where the tray covers the floor, a new season that keeps what the
player is doing, the wardrobe, and the farmhouse and its board on an upright phone"""

import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from farmcord.catalog import ACHIEVEMENTS, CANS, CREDIT, CREDIT_URL, DESCRIPTION_LIMIT, HOES, PEN_SIZE, ROOMS, STORAGE
from farmcord.game.calendar import WEEK
from farmcord.game.model import Animal, Decoration, Item, new_farm
from farmcord.game.progress import xp_for_level
from farmcord.tests import test_browser
from farmcord.tests.test_browser import (
    PLAYER_ID,
    SIZES,
    browser,
    change_farm,
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
from farmcord.tests.test_browser_market import panel_open, start_farm, toast_shown
from farmcord.tests.test_browser_plots import grown, keep_ctx, make_pen, refresh, tap

driver = test_browser.driver
live = test_browser.live
TABS = ["farm", "storage", "animals", "badges", "leaders", "about"]
# The page's words when every pen is full, as the Market's
PENS_FULL = "Your pens are full"
# A room's size in pixels. A decoration's x and y are shares of it
ROOM_WIDTH, ROOM_HEIGHT = 1280, 720
# How near a dropped decoration lands to the point it was dropped on, in room pixels
DROP_SLACK = 3


def go_home(driver, live):
    """The farm opened, and the farmer back in the farmhouse with the page's ctx kept as window.farm"""
    open_farm(driver, live)
    keep_ctx(driver)
    walk(driver, "right", "Yard")
    walk(driver, "left", "Farmhouse")
    browser.wait_for(driver, "window.farm && !window.farm.scene.farmer.walk")


def show_tab(driver, tab):
    driver.find_element(By.CSS_SELECTOR, f'.board .shop-tab[data-tab="{tab}"]').click()
    browser.wait_for(
        driver,
        f"document.querySelector('.board .shop-tab[data-tab=\"{tab}\"]').getAttribute('aria-pressed') === 'true'",
    )


def open_board(driver, live, tab="farm"):
    go_home(driver, live)
    tap(driver, "board")
    panel_open(driver, "Farm board")
    show_tab(driver, tab)


def row(driver, key):
    return browser.wait_for(driver, f"document.querySelector('.board .shop-row[data-key=\"{key}\"]')")


def deal(element):
    return element.find_element(By.CSS_SELECTOR, "button.deal")


def close_panel(driver):
    driver.find_element(By.ID, "panel-close").click()
    browser.wait_for(driver, "!document.getElementById('panel').open")


def canvas_offset(driver, x, y):
    """Where a point of the room is on the canvas, from its middle, for mouse moves"""
    return driver.execute_script(
        """
        const scene = window.farm.scene;
        const at = scene.world.toGlobal({ x: arguments[0], y: arguments[1] });
        const canvas = scene.app.canvas.getBoundingClientRect();
        return [at.x - canvas.width / 2, at.y - canvas.height / 2];
        """,
        x,
        y,
    )


def drop_at(driver, element, x, y):
    """Drags an element (a decoration in the tray) with the mouse onto the room's point x, y"""
    canvas = driver.find_element(By.CSS_SELECTOR, "#stage canvas")
    dx, dy = canvas_offset(driver, x, y)
    chain = ActionChains(driver).click_and_hold(element)
    chain.move_to_element_with_offset(canvas, round(dx) - 30, round(dy) - 30)
    chain.move_to_element_with_offset(canvas, round(dx), round(dy)).release().perform()


def decoration_offset(driver, decoration_id):
    """The middle of a placed decoration's picture on the canvas, from the canvas's middle"""
    return driver.execute_script(
        """
        const scene = window.farm.scene;
        const node = scene.things.getChildByLabel(`decor:${arguments[0]}`);
        const box = node.getBounds().rectangle;
        const canvas = scene.app.canvas.getBoundingClientRect();
        return [box.x + box.width / 2 - canvas.width / 2, box.y + box.height / 2 - canvas.height / 2];
        """,
        decoration_id,
    )


def drawn(driver, decoration_id):
    return driver.execute_script(
        "return Boolean(window.farm.scene.things.getChildByLabel(`decor:${arguments[0]}`))", decoration_id
    )


def test_the_board_shows_a_new_farms_seeds_tools_and_badges(driver, live):
    open_board(driver, live)
    # The farm tab: FarmCoins and the starter tools
    can = row(driver, "tool:can")
    assert CANS[0].name in can.text and f"{CANS[0].capacity} of {CANS[0].capacity} water" in can.text
    assert HOES[0].name in row(driver, "tool:hoe").text
    assert "0 FarmCoins" in driver.find_element(By.CSS_SELECTOR, ".board").text
    show_tab(driver, "storage")
    seeds = row(driver, "seed:wildflowers")
    assert "Wildflowers" in seeds.text
    assert seeds.find_element(By.CSS_SELECTOR, ".shop-owned").text == f"5 of {STORAGE[0].limit}"
    assert driver.find_elements(By.CSS_SELECTOR, '.board .shop-row[data-key^="crop:"]') == []
    show_tab(driver, "badges")
    tiles = driver.find_elements(By.CSS_SELECTOR, ".badges li")
    assert [tile.get_attribute("data-key") for tile in tiles] == list(ACHIEVEMENTS)
    assert driver.find_elements(By.CSS_SELECTOR, ".badges li.earned") == []
    assert ACHIEVEMENTS["first_crop"].name in tiles[0].text
    # A badge earned since lights up when the board hears of it
    on_loop(live, change_farm(live.cog, achievements={"first_crop": live.cog.clock()}))
    refresh(driver)
    lit = browser.wait_for(driver, "[...document.querySelectorAll('.badges li.earned')].map((li) => li.dataset.key)")
    assert lit == ["first_crop"]
    assert not problems(driver)


def test_seeds_are_thrown_away_from_the_board(driver, live):
    items = {
        "seed:wildflowers": Item("seed:wildflowers", 5),
        "crop:wildflowers": Item("crop:wildflowers", 6, 24),
        "feed:chicken": Item("feed:chicken", 3),
    }
    start_farm(live, items=items)
    open_board(driver, live, "storage")
    crops = row(driver, "crop:wildflowers")
    assert "Worth 24 FarmCoins" in crops.text
    # Feed can't be thrown away
    assert row(driver, "feed:chicken").find_elements(By.CSS_SELECTOR, "button.deal") == []
    seeds = row(driver, "seed:wildflowers")
    box = seeds.find_element(By.CSS_SELECTOR, "input.shop-count")
    assert box.get_attribute("value") == "1"
    seeds.find_element(By.CSS_SELECTOR, "button.more").click()
    deal(seeds).click()
    browser.wait_for(driver, "document.getElementById('confirm').open")
    assert text(driver, "confirm-text").startswith("Throw away 2 Wildflowers seeds?")
    driver.find_element(By.ID, "confirm-no").click()
    assert saved_farm(live).items["seed:wildflowers"].quantity == 5
    deal(row(driver, "seed:wildflowers")).click()
    browser.wait_for(driver, "document.getElementById('confirm').open")
    driver.find_element(By.ID, "confirm-yes").click()
    wait_until(driver, lambda: saved_farm(live).items["seed:wildflowers"].quantity == 3)
    browser.wait_for(
        driver,
        "document.querySelector('.board .shop-row[data-key=\"seed:wildflowers\"] .shop-owned')?.textContent "
        f"=== '3 of {STORAGE[0].limit}'",
    )
    assert not problems(driver)


def test_a_waiting_baby_moves_into_a_pen_with_room(driver, live):
    start_farm(live)
    full = [(grown("chicken", "female"), 0) for _ in range(PEN_SIZE)]
    on_loop(live, make_pen(live.cog, *full))
    baby = Animal(kind="chicken", sex="male")
    farm = saved_farm(live)
    farm.animals.append(baby)
    on_loop(live, live.cog.store.save(farm))
    go_home(driver, live)
    # The baby waits in the farmhouse; tapping it opens the board's animals
    tap(driver, f"baby:{baby.id}")
    panel_open(driver, "Farm board")
    waiting = row(driver, f"baby:{baby.id}")
    assert waiting.find_element(By.CSS_SELECTOR, ".shop-why").text == PENS_FULL
    assert not deal(waiting).is_enabled()
    # A second pen with room
    farm = saved_farm(live)
    farm.plots[3].unlocked, farm.plots[3].kind = True, "animals"
    on_loop(live, live.cog.store.save(farm))
    refresh(driver)
    pens = browser.wait_for(driver, f"document.querySelector('.shop-row[data-key=\"baby:{baby.id}\"] select.shop-pen')")
    assert [option.text for option in pens.find_elements(By.TAG_NAME, "option")] == [f"Plot 3 (0 of {PEN_SIZE})"]
    deal(row(driver, f"baby:{baby.id}")).click()
    wait_until(driver, lambda: next(a for a in saved_farm(live).animals if a.id == baby.id).plot == 3)
    moved = next(animal for animal in saved_farm(live).animals if animal.id == baby.id)
    assert moved.arrived_at == live.cog.clock()
    browser.wait_for(driver, f"!document.querySelector('.shop-row[data-key=\"baby:{baby.id}\"]')")
    close_panel(driver)
    assert not driver.execute_script(f"return window.farm.scene.targets.some((t) => t.node.label === 'baby:{baby.id}')")
    assert not problems(driver)


def test_a_double_tap_buys_storage_once(driver, live):
    start_farm(live, level=STORAGE[1].level, coins=STORAGE[1].price + STORAGE[2].price)
    open_board(driver, live)
    upgrade = row(driver, "storage")
    assert f"{STORAGE[1].limit} of each" in upgrade.text
    watch_toasts(driver)
    # The bot is busy with the player's farm, so the first purchase is still on its way when the second tap lands
    lock = live.cog.locks[PLAYER_ID]
    on_loop(live, lock.acquire())
    try:
        ActionChains(driver).double_click(deal(upgrade)).perform()
        driver.execute_async_script("setTimeout(arguments[arguments.length - 1], 500)")
    finally:
        live.loop.call_soon_threadsafe(lock.release)
    wait_until(driver, lambda: saved_farm(live).storage_tier == 1)
    driver.execute_async_script("setTimeout(arguments[arguments.length - 1], 1000)")
    farm = saved_farm(live)
    assert (farm.storage_tier, farm.coins) == (1, STORAGE[2].price)
    # The second tap never reached the bot, which would have said no to it
    assert [seen for seen in toasts_seen(driver) if seen.startswith("toast error")] == []
    # The next upgrade opens at a higher level
    browser.wait_for(
        driver,
        f"document.querySelector('.board .shop-row[data-key=\"storage\"]')?.textContent"
        f".includes('Unlocks at level {STORAGE[2].level}')",
    )
    assert not problems(driver)


def test_a_room_is_bought_described_and_decorated(driver, live):
    second = ROOMS[2]
    pot = Decoration(item="flower_pot")
    start_farm(live, level=second.level, coins=second.price + 100, decorations=[pot])
    open_board(driver, live)
    assert driver.find_elements(By.CSS_SELECTOR, '.exit[data-dir="left"]') == []
    offer = row(driver, "room")
    assert second.name in offer.text and f"{second.price:,}" in offer.text
    deal(offer).click()
    wait_until(driver, lambda: saved_farm(live).rooms == 1)
    assert saved_farm(live).coins == 100
    toast_shown(driver, f"Your {second.name.lower()} is ready. Its door is on the left side of the Farmhouse.")
    close_panel(driver)
    # Its door appears, and leads to it
    walk(driver, "left", second.name)
    browser.wait_for(driver, "window.farm.room().id === 'room2' && !window.farm.scene.farmer.walk")
    # Its description box
    note = driver.find_element(By.ID, "room-note-text")
    assert note.get_attribute("maxlength") == str(DESCRIPTION_LIMIT)
    words = "My hat collection lives here."
    note.send_keys(words)
    assert text(driver, "room-note-count") == f"{len(words)}/{DESCRIPTION_LIMIT}"
    driver.find_element(By.ID, "room-note-save").click()
    wait_until(driver, lambda: saved_farm(live).descriptions.get(2) == words)
    # A decoration dragged from the tray onto the floor
    driver.find_element(By.ID, "decorate").click()
    item = browser.wait_for(driver, "document.querySelector('#decor-tray .decor-item[data-item=\"flower_pot\"]')")
    assert "Flower pot" in item.text
    drop_at(driver, item, 400, 600)
    wait_until(driver, lambda: saved_farm(live).decorations[0].room == "room2")
    # Kept as shares of the whole room
    placed = saved_farm(live).decorations[0]
    assert placed.x * ROOM_WIDTH == pytest.approx(400, abs=DROP_SLACK)
    assert placed.y * ROOM_HEIGHT == pytest.approx(600, abs=DROP_SLACK)
    browser.wait_for(driver, f"Boolean(window.farm.scene.things.getChildByLabel('decor:{pot.id}'))")
    browser.wait_for(driver, "!document.querySelector('#decor-tray .decor-item')")
    # Dragged back off the floor, onto the tray, it is put away
    canvas = driver.find_element(By.CSS_SELECTOR, "#stage canvas")
    dx, dy = decoration_offset(driver, pot.id)
    chain = ActionChains(driver).move_to_element_with_offset(canvas, round(dx), round(dy)).click_and_hold()
    chain.move_by_offset(0, 20).move_to_element(driver.find_element(By.ID, "decor-tray")).release().perform()
    wait_until(driver, lambda: saved_farm(live).decorations[0].room is None)
    browser.wait_for(driver, "Boolean(document.querySelector('#decor-tray .decor-item[data-item=\"flower_pot\"]'))")
    assert not drawn(driver, pot.id)
    assert not problems(driver)


def test_decorations_in_the_yard_are_drawn_and_dragged_by_touch(driver, live):
    fence = Decoration(item="wooden_fence", room="yard", x=0.5, y=0.5)
    gnome = Decoration(item="garden_gnome")
    start_farm(live, decorations=[fence, gnome])
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES["phone"])
    driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1})
    try:
        open_farm(driver, live)
        keep_ctx(driver)
        walk(driver, "right", "Yard")
        browser.wait_for(driver, "window.farm && !window.farm.scene.farmer.walk")
        # The placed fence stands at its shares of the Yard
        where = driver.execute_script(
            "const node = window.farm.scene.things.getChildByLabel(arguments[0]); return node && [node.x, node.y]",
            f"decor:{fence.id}",
        )
        assert where == pytest.approx([0.5 * ROOM_WIDTH, 0.5 * ROOM_HEIGHT])
        driver.find_element(By.ID, "decorate").click()
        item = browser.wait_for(driver, "document.querySelector('#decor-tray .decor-item[data-item=\"garden_gnome\"]')")
        # A finger drags the gnome from the tray to the floor: the page's points are the frame's, Chrome's are the
        # whole window's
        start = driver.execute_script(
            "const b = arguments[0].getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]", item
        )
        goal = driver.execute_script(
            """
            const scene = window.farm.scene;
            const at = scene.world.toGlobal({ x: arguments[0], y: arguments[1] });
            const canvas = scene.app.canvas.getBoundingClientRect();
            return [canvas.x + at.x, canvas.y + at.y];
            """,
            580,
            590,
        )
        # Somewhere the farmer isn't, in the part of the Yard on screen
        driver.switch_to.default_content()
        frame = driver.execute_script("return document.getElementById('game-frame').getBoundingClientRect().toJSON()")
        points = [(start[0] + (goal[0] - start[0]) * t, start[1] + (goal[1] - start[1]) * t) for t in (0, 0.3, 0.7, 1)]
        for kind, (x, y) in zip(["touchStart", "touchMove", "touchMove", "touchMove"], points):
            point = {"x": frame["x"] + x, "y": frame["y"] + y}
            driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [point]})
        driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
        wait_until(driver, lambda: saved_farm(live).decorations[1].room == "yard")
        placed = saved_farm(live).decorations[1]
        assert placed.x * ROOM_WIDTH == pytest.approx(580, abs=DROP_SLACK)
        assert placed.y * ROOM_HEIGHT == pytest.approx(590, abs=DROP_SLACK)
        assert saved_farm(live).decorations[0].room == "yard"
        assert not problems(driver)
    finally:
        driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": False})
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_a_decoration_dropped_on_the_tray_is_put_away_even_over_the_floor(driver, live):
    fence = Decoration(item="wooden_fence", room="yard", x=0.5, y=0.9)
    start_farm(live, decorations=[fence])
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES["sideways"])
    try:
        open_farm(driver, live)
        keep_ctx(driver)
        walk(driver, "right", "Yard")
        browser.wait_for(driver, "window.farm && !window.farm.scene.farmer.walk")
        driver.find_element(By.ID, "decorate").click()
        tray = driver.find_element(By.ID, "decor-tray")
        # On a sideways phone the tray covers the back of the Yard's floor: the point it is dropped on is floor too
        under = driver.execute_script(
            """
            const box = arguments[0].getBoundingClientRect();
            const scene = window.farm.scene;
            const canvas = scene.app.canvas.getBoundingClientRect();
            const at = scene.world.toLocal({ x: box.x + box.width / 2 - canvas.x, y: box.bottom - 12 - canvas.y });
            const floor = window.farm.room().floor;
            return at.x >= floor.left && at.x <= floor.right && at.y >= floor.top && at.y <= floor.bottom;
            """,
            tray,
        )
        assert under
        canvas = driver.find_element(By.CSS_SELECTOR, "#stage canvas")
        dx, dy = decoration_offset(driver, fence.id)
        chain = ActionChains(driver).move_to_element_with_offset(canvas, round(dx), round(dy)).click_and_hold()
        chain.move_by_offset(0, -20).move_to_element_with_offset(tray, 0, round(tray.size["height"] / 2) - 12)
        chain.release().perform()
        wait_until(driver, lambda: saved_farm(live).decorations[0].room is None)
        assert not problems(driver)
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_a_new_season_keeps_what_the_player_is_doing_in_a_room(driver, live):
    second = ROOMS[2]
    pot = Decoration(item="flower_pot")
    start_farm(live, level=second.level, rooms=1, decorations=[pot])
    go_home(driver, live)
    walk(driver, "left", second.name)
    browser.wait_for(driver, "window.farm.room().id === 'room2' && !window.farm.scene.farmer.walk")
    words = "Half a thought"
    driver.find_element(By.ID, "room-note-text").send_keys(words)
    driver.find_element(By.ID, "decorate").click()
    item = browser.wait_for(driver, "document.querySelector('#decor-tray .decor-item[data-item=\"flower_pot\"]')")
    # A decoration is being dragged when the season turns, and the room is drawn again
    ActionChains(driver).click_and_hold(item).move_by_offset(0, 160).perform()
    browser.wait_for(driver, "document.getElementById('decor-tray').classList.contains('dragging')")
    season = driver.execute_script("return window.farm.state().season.name")
    live.cog.clock.move(WEEK)
    refresh(driver)
    browser.wait_for(driver, f"window.farm.state().season.name !== '{season}'")
    # The words not saved yet and the open tray stay (the box waits under the tray); the drag ends, and letting go
    # places nothing
    assert driver.find_element(By.ID, "room-note-text").get_property("value") == words
    count = driver.find_element(By.ID, "room-note-count").get_property("textContent")
    assert count == f"{len(words)}/{DESCRIPTION_LIMIT}"
    assert not driver.find_element(By.ID, "room-note-save").get_property("disabled")
    tray = driver.find_element(By.ID, "decor-tray")
    assert tray.is_displayed() and "dragging" not in tray.get_attribute("class")
    assert driver.find_elements(By.CSS_SELECTOR, '#decor-tray .decor-item[data-item="flower_pot"]')
    ActionChains(driver).move_by_offset(0, 40).release().perform()
    driver.execute_async_script("setTimeout(arguments[arguments.length - 1], 500)")
    assert saved_farm(live).decorations[0].room is None
    assert not drawn(driver, pot.id)
    # Walking out and back in starts the box afresh from the words the bot keeps
    driver.find_element(By.ID, "decor-done").click()
    walk(driver, "right", "Farmhouse")
    walk(driver, "left", second.name)
    browser.wait_for(driver, "window.farm.room().id === 'room2' && !document.getElementById('room-note').hidden")
    assert driver.find_element(By.ID, "room-note-text").get_property("value") == ""
    assert not problems(driver)


def screen_box(driver, label):
    """Where a piece of the room labelled `label` is on the page"""
    return driver.execute_script(
        """
        const scene = window.farm.scene;
        const box = scene.things.getChildByLabel(arguments[0]).getBounds().rectangle;
        const canvas = scene.app.canvas.getBoundingClientRect();
        return { left: canvas.x + box.x, top: canvas.y + box.y, right: canvas.x + box.x + box.width,
                 bottom: canvas.y + box.y + box.height };
        """,
        label,
    )


def overlap(a, b):
    return a["left"] < b["right"] and b["left"] < a["right"] and a["top"] < b["bottom"] and b["top"] < a["bottom"]


def test_the_farmhouse_fits_an_upright_phone(driver, live):
    start_farm(live, level=ROOMS[2].level, rooms=1, outfits={"straw_hat", "cap", "plaid_shirt", "blue_overalls"})
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES["phone"])
    try:
        go_home(driver, live)
        # The doors on each side leave the board, the wardrobe and their names clear to tap
        exits = driver.execute_script(
            "return [...document.querySelectorAll('.exit')].map((node) => node.getBoundingClientRect().toJSON())"
        )
        assert len(exits) == 2
        pieces = {label: screen_box(driver, label) for label in ["board", "board:name", "wardrobe", "wardrobe:name"]}
        for label, box in pieces.items():
            assert not any(overlap(box, door) for door in exits), (label, box, exits)
        # The wardrobe's Wear button shows without scrolling
        tap(driver, "wardrobe")
        panel_open(driver, "Wardrobe")
        driver.find_element(By.CSS_SELECTOR, '.outfit-choice[data-slot="hat"][data-key="cap"]').click()
        wear = driver.execute_script("return document.getElementById('wear').getBoundingClientRect().toJSON()")
        shown = driver.execute_script("return document.getElementById('panel').getBoundingClientRect().toJSON()")
        assert shown["top"] <= wear["top"] and wear["bottom"] <= shown["bottom"], (wear, shown)
        assert not problems(driver)
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_the_farmer_changes_clothes_at_the_wardrobe(driver, live):
    start_farm(live, outfits={"straw_hat", "plaid_shirt", "blue_overalls"})
    go_home(driver, live)
    tap(driver, "wardrobe")
    panel_open(driver, "Wardrobe")
    layers = "[...document.querySelectorAll('.wardrobe-preview [data-layer]')].map((n) => n.dataset.layer)"
    assert driver.execute_script(f"return {layers}") == ["base"]
    hats = driver.find_elements(By.CSS_SELECTOR, '.outfit-choice[data-slot="hat"]')
    assert [hat.get_attribute("data-key") for hat in hats] == ["", "straw_hat"]
    # Picking only shows it on the preview
    hats[1].click()
    browser.wait_for(driver, f"{layers}.join() === 'base,hat'")
    assert saved_farm(live).hat is None
    driver.find_element(By.CSS_SELECTOR, '.outfit-choice[data-slot="bottom"][data-key="blue_overalls"]').click()
    browser.wait_for(driver, f"{layers}.join() === 'base,bottom,hat'")
    driver.find_element(By.ID, "wear").click()
    wait_until(driver, lambda: (saved_farm(live).hat, saved_farm(live).bottom) == ("straw_hat", "blue_overalls"))
    assert saved_farm(live).top is None
    browser.wait_for(driver, "window.farm.scene.farmer.outfit.hat === 'straw_hat'")
    browser.wait_for(driver, "document.getElementById('wear').disabled")
    # And off again
    driver.find_element(By.CSS_SELECTOR, '.outfit-choice[data-slot="hat"][data-key=""]').click()
    driver.find_element(By.ID, "wear").click()
    wait_until(driver, lambda: saved_farm(live).hat is None)
    assert not problems(driver)


def test_the_leaderboard_on_the_board_lists_the_player_and_their_rank(driver, live):
    rival = new_farm(fakes.OWNER_ID, "Rival", live.cog.clock())
    rival.level, rival.xp = 10, xp_for_level(10)
    on_loop(live, live.cog.store.save(rival))
    start_farm(live, level=3)
    open_board(driver, live, "leaders")
    rows = browser.wait_for(
        driver,
        "document.querySelectorAll('.leaders li').length === 2 && "
        "[...document.querySelectorAll('.leaders li')].map((li) => li.textContent)",
    )
    assert rows[0].startswith("#1") and "Rival" in rows[0] and "Level 10" in rows[0]
    assert rows[1].startswith("#2") and "Member" in rows[1] and "Level 3" in rows[1]
    assert driver.find_element(By.CSS_SELECTOR, ".leaders li.mine").text.startswith("#2")
    assert text(driver, "leaders-you") == "Your farm is #2"
    assert not problems(driver)


def test_the_about_panel_credits_vainne_and_opens_the_link(driver, live):
    open_board(driver, live, "farm")
    driver.execute_script("""
      window.opened = [];
      window.farm.hub().discord.commands.openExternalLink = async (args) => { window.opened.push(args); };
    """)
    show_tab(driver, "about")
    credit = driver.find_element(By.ID, "credit")
    assert credit.text == CREDIT and credit.tag_name == "button"
    credit.click()
    assert browser.wait_for(driver, "window.opened.length && window.opened") == [{"url": CREDIT_URL}]
    # Outside Discord the credit is plain text
    driver.execute_script("const hub = window.farm.hub(); window.farm.hub = () => ({ ...hub, discord: null })")
    show_tab(driver, "farm")
    show_tab(driver, "about")
    credit = driver.find_element(By.ID, "credit")
    assert credit.text == CREDIT and credit.tag_name == "p"
    assert not problems(driver)


@pytest.mark.parametrize("tab", TABS)
def test_the_board_fits_an_upright_phone(driver, live, tab):
    items = {"seed:wildflowers": Item("seed:wildflowers", 12), "crop:corn:x": Item("crop:corn:x", 3, 150)}
    start_farm(live, level=60, coins=5000, items=items)
    farm = saved_farm(live)
    farm.animals.append(Animal(kind="cow", sex="female"))
    on_loop(live, live.cog.store.save(farm))
    on_loop(live, make_pen(live.cog, (grown("cow", "female"), 3600)))
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES["phone"])
    try:
        open_board(driver, live, tab)
        sizes = driver.execute_script(
            """
            const panel = document.getElementById('panel');
            const boxes = [...panel.querySelectorAll('.shop-tab, .board button, .board input, .board select')]
              .map((node) => node.getBoundingClientRect());
            return { scroll: panel.scrollWidth, width: panel.clientWidth, right: Math.max(...boxes.map((b) => b.right)),
                     left: Math.min(...boxes.map((b) => b.left)), screen: innerWidth };
            """
        )
        assert sizes["scroll"] <= sizes["width"], sizes
        assert 0 <= sizes["left"] and sizes["right"] <= sizes["screen"], sizes
        assert not problems(driver)
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
