import asyncio
import random
import time
from types import SimpleNamespace

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.by import By

from botarena3.common import career, leaderboard
from botarena3.common.arenas import ARENAS, CHALLENGES, WEIGHT_CLASSES
from botarena3.main import BotArena3
from botarena3.tests.fakes import FakeConn, FakeRoom

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="botarena3"]'
ME = fakes.MEMBER_ID


@pytest.fixture(scope="module")
def driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
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
    return BotArena3(bot=None)


@pytest.fixture
def live(tmp_path, driver, cog):
    hub = fakes.make_hub()
    assert fakes.register(hub, cog) is not None
    server = browser.LiveHub(hub, browser.hub_web_copy(tmp_path))
    server.start()
    driver.set_window_size(1280, 800)
    browser.fresh(driver, server)
    yield server
    # Stopped on the server's own event loop, so no battle loop is left running when it closes
    asyncio.run_coroutine_threadsafe(cog.cog_unload(), server.loop).result(5)
    server.stop()


def open_game(driver, live, query=browser.DISCORD_QUERY):
    driver.get(f"{live.url}/{query}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))


def on_screen(driver, name, timeout=20):
    browser.wait_for(driver, f"document.body.dataset.screen === '{name}'", timeout=timeout)


def found(driver, path):
    """Where one of the original's clips is on the page in CSS pixels, with its frame and how see-through it is"""
    box = driver.execute_script("return window.botArena3.find(arguments[0])", path)
    assert box, path
    return box


def rect_of(driver, selector):
    """An element's left, top, right and bottom on the page"""
    return driver.execute_script(
        "const r = document.querySelector(arguments[0]).getBoundingClientRect();"
        "return [r.left, r.top, r.right, r.bottom];",
        selector,
    )


def pointer_at(driver, x, y):
    """Mouse actions that start with the pointer on a point of the page, in CSS pixels"""
    canvas = driver.find_element(By.CSS_SELECTOR, "#stage canvas")
    left, top, right, bottom = rect_of(driver, "#stage canvas")
    middle = (x - (left + right) / 2, y - (top + bottom) / 2)
    return ActionChains(driver).move_to_element_with_offset(canvas, *middle).pause(0.2)


def still(driver, path, timeout=10):
    """Where one of the original's clips comes to rest on the stage: found in the same place twice running, so a
    clip that slides or plays its way in is pressed where it stops"""
    end = time.monotonic() + timeout
    last = None
    while True:
        box = driver.execute_script("return window.botArena3.find(arguments[0])", path)
        if box and last and all(box[key] == last[key] for key in ("x", "y", "w", "h")):
            return box
        assert time.monotonic() < end, f"{path} never came to rest on the stage"
        last = box
        time.sleep(0.05)


def press(driver, path):
    """Click the middle of one of the original's clips, once it is on the stage and still"""
    box = still(driver, path)
    pointer_at(driver, box["x"] + box["w"] / 2, box["y"] + box["h"] / 2).click().perform()


def stage_scale(driver):
    """CSS pixels to one of the original's pixels"""
    left, _, right, _ = rect_of(driver, "#stage canvas")
    return (right - left) / 640


def stays(driver, script, seconds=1.5):
    """True when the script's answer is still true after a while, for something that must not happen"""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not driver.execute_script(f"return {script}"):
            return False
        time.sleep(0.1)
    return True


def on_server(live, coro):
    """Run something on the live hub's own thread, the way the bot would"""
    return asyncio.run_coroutine_threadsafe(coro, live.loop).result(5)


def seed_career(cog, live, data):
    asyncio.run_coroutine_threadsafe(cog.config.user_from_id(ME).career.set(data), live.loop).result(5)


def saved_career(cog, live):
    # Config's value reads are awaitables, not coroutines, so one is wrapped to run on the bot's loop
    async def read():
        return await cog.config.user_from_id(ME).career()

    return asyncio.run_coroutine_threadsafe(read(), live.loop).result(5)


def eventually(check, timeout=5):
    """Wait until the bot's side shows what a request should have changed"""
    end = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < end, "the bot never showed the change"
        time.sleep(0.1)


def shop_with(driver, live, cog, data):
    """Continue a career straight into the shop"""
    seed_career(cog, live, data)
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b2")
    on_screen(driver, "shop")


def monitor(driver):
    """The info monitor's frame label, and the variables its text fields show"""
    shown = driver.execute_script("return document.body.dataset.monitor")
    return shown, found(driver, "infomon.screen")["vars"]


def test_the_game_opens_on_the_menu_with_continue_greyed(driver, live, cog):
    open_game(driver, live)
    on_screen(driver, "menu")
    browser.wait_for(driver, "window.botArena3.find('b1')?.alpha === 1")
    assert found(driver, "b2")["alpha"] == 0.5
    # A greyed button does nothing: the menu stays, with every button on it
    press(driver, "b2")
    assert stays(driver, "document.body.dataset.screen === 'menu' && window.botArena3.find('b1') !== null")
    assert saved_career(cog, live) is None
    problems = [line for line in browser.console_lines(driver) if "Uncaught" in line]
    assert not problems, problems


def test_new_career_goes_to_the_shop(driver, live, cog):
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b1")
    on_screen(driver, "shop")
    assert saved_career(cog, live)["cash"] == career.START_CASH


def test_new_career_over_an_old_one_asks_first(driver, live, cog):
    old = career.new_career()
    old["cash"] = 123
    seed_career(cog, live, old)
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b1")
    assert saved_career(cog, live)["cash"] == 123
    press(driver, "confirm.yes")
    on_screen(driver, "shop")
    assert saved_career(cog, live)["cash"] == career.START_CASH


def test_settings_keep_the_volumes_on_this_device(driver, live):
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b5")
    on_screen(driver, "settings")
    # The volume sliders, SHOP BLURS and DONE, without the quality buttons
    assert driver.execute_script("return window.botArena3.find('611')") is None
    assert found(driver, "755")
    assert found(driver, "donebut")
    slider = found(driver, "svol.slider")
    # Down 20 steps of the slider, from the 70 it starts on to 50: 1.8 pixels a step, in a holder the original
    # drew at 0.8473 of its size
    pointer_at(driver, slider["x"] + slider["w"] / 2, slider["y"] + slider["h"] / 2).click_and_hold().pause(
        0.2
    ).move_by_offset(0, round(20 * 1.8 * 0.8473 * stage_scale(driver))).pause(0.3).release().perform()
    browser.wait_for(driver, "localStorage.getItem('botarena3.sound') !== null")
    sound, music = driver.execute_script(
        "return [localStorage.getItem('botarena3.sound'), localStorage.getItem('botarena3.music')]"
    )
    assert abs(int(sound) - 50) <= 1
    assert music in (None, "35")


def test_the_whole_of_an_invisible_button_takes_a_press(driver, live):
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b4")
    on_screen(driver, "instructions")
    # Next page (art 657 in the instructions, 718): its press area is an invisible shape 82 by 21 of the original's
    # pixels, wider than the lettering on it
    button = found(driver, "718.657")
    scale = stage_scale(driver)
    assert abs(button["w"] - 82 * scale) <= 2 and abs(button["h"] - 21 * scale) <= 2
    assert found(driver, "718")["frame"] == 1
    # Pressed just inside its left edge, left of the lettering
    pointer_at(driver, button["x"] + 2, button["y"] + button["h"] / 2).click().perform()
    browser.wait_for(driver, "window.botArena3.find('718')?.frame === 2")


@pytest.mark.parametrize("size", [(1280, 800), (390, 844), (800, 600)])
def test_the_back_button_stays_off_the_art(driver, live, size):
    driver.set_window_size(*size)
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b4")
    on_screen(driver, "instructions")
    assert driver.find_element(By.ID, "back").is_displayed()
    back, stage = rect_of(driver, "#back"), rect_of(driver, "#stage canvas")
    apart = back[2] <= stage[0] or back[3] <= stage[1] or back[0] >= stage[2] or back[1] >= stage[3]
    assert apart, (back, stage)


def test_a_new_career_lost_with_the_connection_gives_the_menu_back(driver, live, cog):
    asked = []

    async def unanswered(conn, value):
        asked.append(value)

    cog.new_career = unanswered
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b1")
    browser.wait_for(driver, "window.botArena3.find('b4') === null")
    assert asked == [True]
    # The connection drops before the answer, and the bot sends the career again to the new one
    on_server(live, live.server.rooms.close_all())
    browser.wait_for(driver, "window.botArena3.find('b4')?.alpha === 1", timeout=20)
    press(driver, "b4")
    on_screen(driver, "instructions")


def test_the_confirm_panel_waits_for_its_art(driver, live, cog):
    old = career.new_career()
    old["cash"] = 123
    seed_career(cog, live, old)
    # The info monitor's art page can't load for now
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": ["*atlas-1.png"]})
    try:
        open_game(driver, live)
        on_screen(driver, "menu")
        press(driver, "b1")
        assert stays(driver, "window.botArena3.find('confirm.yes') === null")
    finally:
        driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": []})
    warned = [line for line in browser.console_lines(driver) if "before its art page loaded" in line]
    assert not warned, warned
    press(driver, "b1")
    browser.wait_for(driver, "window.botArena3.find('confirm.yes') !== null")
    press(driver, "confirm.yes")
    on_screen(driver, "shop")
    assert saved_career(cog, live)["cash"] == career.START_CASH


def test_buying_a_chassis_plating_and_gun_and_mounting_them(driver, live, cog):
    seed_career(cog, live, career.new_career())
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b2")
    on_screen(driver, "shop")
    press(driver, "chassisviewbutton")
    press(driver, "shop.itemhold.listitem0")
    press(driver, "buyitembutton")
    eventually(lambda: len(saved_career(cog, live)["robots"]) == 1)
    browser.wait_for(driver, "window.botArena3.find('mybots.itemhold.listitem0') !== null")
    press(driver, "platingviewbutton")
    press(driver, "shop.itemhold.listitem0")
    press(driver, "buyitembutton")
    browser.wait_for(driver, "window.botArena3.find('inventory.itemhold.listitem0') !== null")
    press(driver, "mybots.itemhold.listitem0")
    press(driver, "inventory.itemhold.listitem0")
    press(driver, "mountitembutton")
    eventually(lambda: saved_career(cog, live)["inventory"] == [])
    saved = saved_career(cog, live)
    assert saved["robots"][0]["plating"] == 'SANTRIN "AURO"' and saved["inventory"] == []
    browser.wait_for(driver, "document.body.dataset.monitor === 'prompt'")
    assert monitor(driver)[1]["txt_displaytext"] == career.MOUNTED


def test_start_with_an_unplated_robot_shows_the_originals_error(driver, live, cog):
    data = career.new_career()
    career.buy(data, 'AKAUMIN "DLZ-100"')
    seed_career(cog, live, data)
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b2")
    on_screen(driver, "shop")
    press(driver, "startbattlebutton")
    browser.wait_for(driver, "window.botArena3.find('infomon') !== null")
    assert driver.execute_script("return document.body.dataset.screen") == "shop"
    assert driver.execute_script("return document.body.dataset.monitor") == "error"
    # The original's header, then each problem on its own line
    assert monitor(driver)[1]["txt_displaytext"] == f"{career.CANT_FIGHT_BECAUSE}\r{career.UNPLATED}\r"
    assert stays(driver, "document.body.dataset.screen === 'shop'")


def test_renaming_a_robot_keeps_the_originals_rule(driver, live, cog):
    data = career.new_career()
    career.buy(data, 'AKAUMIN "DLZ-100"')
    seed_career(cog, live, data)
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b2")
    on_screen(driver, "shop")
    press(driver, "mybots.itemhold.listitem0")
    press(driver, "botnamebox")
    field = driver.find_element(By.ID, "name-input")
    field.clear()
    field.send_keys("max power!\n")
    eventually(lambda: saved_career(cog, live)["robots"][0]["name"] == "MAX POWER", timeout=10)
    renamed_and_still_picked(driver)


def renamed_and_still_picked(driver):
    """The robot's new name reached the page, in its row and on the monitor, and the robot is still picked"""
    row = "window.botArena3.find('mybots.itemhold.listitem0')"
    browser.wait_for(driver, f"{row}?.vars.itemtitle === 'MAX POWER'")
    browser.wait_for(driver, "window.botArena3.find('infomon.screen')?.vars.txt_name === 'MAX POWER'")
    picked = "window.botArena3.find('sellbotbutton')?.alpha === 1"
    browser.wait_for(driver, picked)
    # Every answer the bot owed has come, and none of them let the robot go
    assert stays(driver, f"{picked} && {row}.vars.itemtitle === 'MAX POWER'")


def test_an_older_rename_answered_late_keeps_the_newer_name_and_the_pick(driver, live, cog):
    data = career.new_career()
    career.buy(data, 'AKAUMIN "DLZ-100"')
    shop_with(driver, live, cog, data)
    real = cog.send_career
    in_order = asyncio.Lock()
    held = []

    async def late_first_answer(user_id, saved, requester=None, extra=None):
        # The answer to the empty name WebDriver's clear() sends comes after the player sent the real one, as on a
        # slow connection. Answers still go out in the order the bot made them
        async with in_order:
            if extra and extra.get("done") == "rename" and saved["robots"][0]["name"] == "":
                held.append(True)
                await asyncio.sleep(1.5)
            await real(user_id, saved, requester, extra)

    cog.send_career = late_first_answer
    press(driver, "mybots.itemhold.listitem0")
    press(driver, "botnamebox")
    field = driver.find_element(By.ID, "name-input")
    field.clear()
    field.send_keys("max power!\n")
    eventually(lambda: saved_career(cog, live)["robots"][0]["name"] == "MAX POWER", timeout=10)
    renamed_and_still_picked(driver)
    # The empty name's answer really was held back
    assert held == [True]


def test_a_refusal_of_something_else_keeps_the_name_on_its_way(driver, live, cog):
    data = career.new_career()
    career.buy(data, 'AKAUMIN "DLZ-100"')
    shop_with(driver, live, cog, data)
    real = cog.shop
    held = []

    async def slow_refusal(conn, kind, act):
        # A team color request the bot refuses, answered only after the player has sent a new name
        if kind != "color":
            await real(conn, kind, act)
            return
        held.append(kind)
        await asyncio.sleep(1.5)
        saved = await cog.config.user_from_id(ME).career()
        await conn.send({"career": career.view(saved), "refused": career.BAD_COLOR})

    cog.shop = slow_refusal
    press(driver, "mybots.itemhold.listitem0")
    press(driver, "524.tc3")
    press(driver, "botnamebox")
    field = driver.find_element(By.ID, "name-input")
    field.clear()
    field.send_keys("max power!\n")
    eventually(lambda: saved_career(cog, live)["robots"][0]["name"] == "MAX POWER", timeout=10)
    assert held == ["color"]
    # The refusal shows on the monitor, and the robot keeps its new name and its pick throughout
    browser.wait_for(driver, "document.body.dataset.monitor === 'error'")
    row = "window.botArena3.find('mybots.itemhold.listitem0')"
    picked = "window.botArena3.find('sellbotbutton')?.alpha === 1"
    browser.wait_for(driver, f"{picked} && {row}?.vars.itemtitle === 'MAX POWER'")
    assert stays(driver, f"{picked} && {row}.vars.itemtitle === 'MAX POWER'")
    assert saved_career(cog, live)["color"] == 1


def test_the_info_monitor_shows_a_weapon_the_originals_way(driver, live, cog):
    shop_with(driver, live, cog, career.new_career())
    press(driver, "mountviewbutton")
    # KEDRON "SPKL-D4": refire rate 190, 9 damage a shot
    press(driver, "shop.itemhold.listitem1")
    shown, words = monitor(driver)
    assert shown == "weapon_show"
    assert words["txt_name"] == 'KEDRON "SPKL-D4"' and words["txt_subname"] == "WEAPON: FIREWORKS"
    assert words["txt_damage"] == "CAUSES 9 DAMAGE PER SHOT"
    assert words["txt_refirerate"] == "FIRES 376.2 SHOTS PER MINUTE"
    assert words["txt_dps"] == "INFLICTS 3385.8 DAMAGE PER MINUTE"
    assert words["txt_ranges"] == "FIRING DISTANCE: 0-120"
    assert words["txt_cost"] == "COST: 450" and words["txt_weight"] == "WEIGHT: 3"
    assert found(driver, "buyitembutton")["alpha"] == 1


def test_what_you_cannot_afford_is_greyed_and_buys_nothing(driver, live, cog):
    data = career.new_career()
    data["cash"] = 2999
    shop_with(driver, live, cog, data)
    assert found(driver, "buyitembutton")["alpha"] == 0.5
    press(driver, "shop.itemhold.listitem0")
    assert monitor(driver)[0] == "chassis_show"
    assert found(driver, "buyitembutton")["alpha"] == 0.5
    press(driver, "buyitembutton")
    assert stays(driver, "window.botArena3.find('mybots.itemhold.listitem0') === null")
    assert saved_career(cog, live)["robots"] == []


def test_the_shop_scrolls_and_never_lists_the_secret_laser(driver, live, cog):
    data = career.new_career()
    data["level"] = career.BEATEN_LEVEL
    shop_with(driver, live, cog, data)
    press(driver, "mountviewbutton")
    assert driver.execute_script("return window.botArena3.find('shop.itemhold.listitem15')") is None
    # The scroller runs 190 of the original's pixels, from the top of the list to its bottom
    scroller = found(driver, "shop.scroller")
    scale = stage_scale(driver)
    pointer_at(driver, scroller["x"] + scroller["w"] / 2, scroller["y"] + scroller["h"] / 2).click_and_hold().pause(
        0.2
    ).move_by_offset(0, round(200 * scale)).pause(0.3).release().perform()
    holder = found(driver, "shop")
    bottom = holder["y"] + holder["h"]
    last = "window.botArena3.find('shop.itemhold.listitem15')"
    browser.wait_for(driver, f"{last} !== null && {last}.y + 40 * {scale} <= {bottom + 2}")
    # Sixteen weapons up to level 16, and nothing after them, though the laser's level is 18
    assert driver.execute_script("return window.botArena3.find('shop.itemhold.listitem16')") is None
    press(driver, "shop.itemhold.listitem15")
    assert monitor(driver)[1]["txt_name"] == "SCREAM SHARD"


def test_a_team_color_pick_reaches_the_bot(driver, live, cog):
    shop_with(driver, live, cog, career.new_career())
    assert found(driver, "524.tc1.shower")
    assert driver.execute_script("return window.botArena3.find('524.tc3.shower')") is None
    press(driver, "524.tc3")
    eventually(lambda: saved_career(cog, live)["color"] == 3)
    browser.wait_for(driver, "window.botArena3.find('524.tc3.shower') !== null")
    browser.wait_for(driver, "document.body.dataset.monitor === 'prompt'")
    assert monitor(driver)[1]["txt_displaytext"] == career.COLOR_CHANGED
    assert driver.execute_script("return window.botArena3.find('524.tc1.shower')") is None


def test_dismounting_disabling_and_selling_a_robot(driver, live, cog):
    data = career.new_career()
    for name in ('AKAUMIN "DLZ-100"', 'SANTRIN "AURO"', 'ZINTEK "LP"'):
        career.buy(data, name)
    career.mount(data, 0, 0)
    career.mount(data, 0, 0)
    shop_with(driver, live, cog, data)
    assert found(driver, "dismounttopbutton")["alpha"] == 0.5
    press(driver, "mybots.itemhold.listitem0")
    shown, words = monitor(driver)
    assert shown == "mybot_show" and words["txt_weight"] == "WEIGHT: 10"
    assert words["txt_dps"] == "INFLICTS 990 DAMAGE PER MINUTE"
    assert words["txt_shielding"] == "HAS 250 POINTS OF SHIELDING"
    assert words["txt_resale"] == "RESALE VALUE: 1775"
    press(driver, "dismounttopbutton")
    eventually(lambda: saved_career(cog, live)["inventory"] == ['ZINTEK "LP"'])
    browser.wait_for(driver, "window.botArena3.find('inventory.itemhold.listitem0') !== null")
    press(driver, "mybots.itemhold.listitem0")
    press(driver, "enabledisablebutton")
    eventually(lambda: saved_career(cog, live)["robots"][0]["enabled"] is False)
    browser.wait_for(driver, "document.body.dataset.monitor === 'prompt'")
    assert monitor(driver)[1]["txt_displaytext"] == career.DISABLED
    press(driver, "mybots.itemhold.listitem0")
    press(driver, "sellbotbutton")
    eventually(lambda: saved_career(cog, live)["robots"] == [])
    assert saved_career(cog, live)["cash"] == data["cash"] + 1500 + 150


def screen_resolution(driver):
    """The page's drawing pixels per CSS pixel (the device's, up to 2)"""
    return driver.execute_script("return Math.min(window.devicePixelRatio || 1, 2)")


def test_words_are_drawn_again_sharp_when_the_window_grows(driver, live):
    driver.set_window_size(700, 560)
    open_game(driver, live)
    on_screen(driver, "menu")
    # NEW CAREER's words (field 355 of the menu button)
    words = "b1.355"
    browser.wait_for(driver, f"window.botArena3.find('{words}') !== null")
    before = found(driver, words)
    driver.set_window_size(1280, 800)
    browser.wait_for(driver, f"window.botArena3.find('{words}').density > {before['density']} + 0.1")
    after = found(driver, words)
    assert abs(after["density"] - min(3, stage_scale(driver) * screen_resolution(driver))) < 0.01
    # A new canvas at the new density, for a field the same size on the stage
    assert after["pixels"] > before["pixels"]
    assert abs(after["pixels"] / after["density"] - before["pixels"] / before["density"]) < 2


def test_row_pictures_are_drawn_again_when_the_window_grows(driver, live, cog):
    driver.set_window_size(700, 560)
    data = career.new_career()
    career.buy(data, 'AKAUMIN "DLZ-100"')
    shop_with(driver, live, cog, data)
    picture = "mybots.itemhold.listitem0.bmphold.picture"
    before = found(driver, picture)["pixels"]
    driver.set_window_size(1280, 800)
    browser.wait_for(driver, f"window.botArena3.find('{picture}').pixels > {before} + 10")
    # The original's 180 pixel row, at the screen's new pixels per stage pixel
    wide = 180 * stage_scale(driver) * screen_resolution(driver)
    assert abs(found(driver, picture)["pixels"] - wide) <= 2


def test_purchase_is_checked_when_a_part_is_picked_and_after_a_buy(driver, live, cog):
    data = career.new_career()
    data["cash"] = 5000
    shop_with(driver, live, cog, data)
    press(driver, "shop.itemhold.listitem0")
    assert found(driver, "buyitembutton")["alpha"] == 1
    press(driver, "buyitembutton")
    eventually(lambda: len(saved_career(cog, live)["robots"]) == 1)
    # The 2,000 left can't buy another, and the original greys the button as the buy finishes
    browser.wait_for(driver, "window.botArena3.find('buyitembutton').alpha === 0.5")
    # More cash from another device, with a plating bought there: the lists follow, but as in the original the
    # button is only checked again when a part is picked
    richer = saved_career(cog, live)
    richer["cash"] = 9300
    career.buy(richer, 'SANTRIN "AURO"')
    seed_career(cog, live, richer)
    on_server(live, cog.send_career(ME, richer))
    browser.wait_for(driver, "window.botArena3.find('inventory.itemhold.listitem0') !== null")
    assert stays(driver, "window.botArena3.find('buyitembutton').alpha === 0.5")
    press(driver, "shop.itemhold.listitem0")
    press(driver, "shop.itemhold.listitem0")
    assert found(driver, "buyitembutton")["alpha"] == 1


def test_typing_inside_a_name_keeps_the_cursor_there(driver, live, cog):
    data = career.new_career()
    career.buy(data, 'AKAUMIN "DLZ-100"')
    shop_with(driver, live, cog, data)
    press(driver, "mybots.itemhold.listitem0")
    press(driver, "botnamebox")
    field = driver.find_element(By.ID, "name-input")
    driver.execute_script("arguments[0].setSelectionRange(5, 5)", field)
    field.send_keys("x")
    assert driver.execute_script("return [arguments[0].value, arguments[0].selectionStart]", field) == [
        "ROBOTX NAME",
        6,
    ]


def ready_career():
    data = career.new_career()
    for name in ('AKAUMIN "DLZ-100"', 'SANTRIN "AURO"', 'ZINTEK "LP"'):
        career.buy(data, name)
    career.mount(data, 0, 0)
    career.mount(data, 0, 0)
    return data


def arena_list_with(driver, live, cog, data):
    """Continue a career through the shop's START into the arena list"""
    shop_with(driver, live, cog, data)
    press(driver, "startbattlebutton")
    on_screen(driver, "levelselect")


def tell_page(cog, live, message):
    """Send every page the player has open a message, the way the bot does"""

    async def send():
        for window in cog.windows.values():
            for conn in list(window.room.connections):
                await conn.send(message)

    on_server(live, send())


def node_done(driver, index, frame):
    """Wait for an arena list node to finish playing its mark: good ends on frame 14 of the original's node, locked
    on 28, bad on 41 and poor on 55"""
    browser.wait_for(driver, f"window.botArena3.find('bholder.levelnode{index}.node')?.frame === {frame}")


def nothing_at(driver, path):
    """True when one of the original's clips is missing, hidden or off the stage"""
    return driver.execute_script("return window.botArena3.find(arguments[0])", path) is None


def test_the_second_arena_starts_a_battle_and_takes_its_fee(driver, live, cog):
    data = ready_career()
    data["level"] = 2
    arena = ARENAS[1]
    assert arena.fee > 0
    arena_list_with(driver, live, cog, data)
    node_done(driver, 1, 14)
    press(driver, "bholder.levelnode1")
    still(driver, "iholder.playbutton")
    # The original's battle information, word for word
    info = found(driver, "iholder")
    assert info["frame"] == 1
    assert info["vars"]["battlename"] == arena.name
    view = career.view(data)
    assert info["vars"]["details"] == (
        f"WEIGHT LIMIT: {arena.weight_class} ({WEIGHT_CLASSES[arena.weight_class]})\r"
        f"YOUR TEAM'S WEIGHT: {view['weight']}\r\r"
        f"ENTRY COST: {arena.fee}\rYOUR CASH: {view['cash']}\r\rPRIZE MONEY: {arena.prize}"
    )
    assert found(driver, "iholder.map.bg.graphic")["frame"] == arena.background
    assert found(driver, "iholder.map.ob.graphic")["frame"] == arena.background
    press(driver, "iholder.playbutton")
    on_screen(driver, "battle")
    assert cog.running(ME) is not None and cog.running(ME).index == 1
    eventually(lambda: saved_career(cog, live)["fee"] == arena.fee)
    assert saved_career(cog, live)["cash"] == view["cash"] - arena.fee


def test_a_locked_arena_has_no_play_button(driver, live, cog):
    arena_list_with(driver, live, cog, ready_career())
    node_done(driver, 5, 28)
    press(driver, "bholder.levelnode5")
    browser.wait_for(driver, "window.botArena3.find('iholder')?.frame === 5")
    still(driver, "iholder.backbutton")
    assert stays(driver, "window.botArena3.find('iholder.playbutton') === null")
    # Back to the list, and an open arena shows PLAY again
    press(driver, "iholder.backbutton")
    press(driver, "bholder.levelnode0")
    browser.wait_for(driver, "window.botArena3.find('iholder')?.frame === 1")
    still(driver, "iholder.playbutton")


def test_a_node_lights_up_under_the_pointer(driver, live, cog):
    arena_list_with(driver, live, cog, ready_career())
    node_done(driver, 0, 14)
    lit = "window.botArena3.find('bholder.levelnode0.node.{}')?.alpha === {}"
    assert driver.execute_script(f"return {lit.format('thename', 0)}")
    node = still(driver, "bholder.levelnode0")
    pointer_at(driver, node["x"] + node["w"] / 2, node["y"] + node["h"] / 2).perform()
    browser.wait_for(driver, f"{lit.format('thename', 1)} && {lit.format('glower', 1)}")
    # Away from it, the name and glow fade out
    stage = rect_of(driver, "#stage canvas")
    pointer_at(driver, stage[0] + 5, stage[1] + 5).perform()
    browser.wait_for(driver, f"{lit.format('thename', 0)} && {lit.format('glower', 0)}")


def test_too_heavy_and_too_poor_arenas_show_the_originals_marks(driver, live, cog):
    data = ready_career()
    # A 40 weight team with 50 cash at level 3: the first two arenas allow 35, the third 45; the second costs 100
    # and the third 300
    data["robots"][0]["chassis"] = 'XEROI "DELIVERANCE"'
    data["robots"][0]["plating"] = 'GAIACORP "LB-MK2"'
    data.update(level=3, cash=50)
    assert career.view(data)["arenas"][:3] == ["bad", "both", "poor"]
    arena_list_with(driver, live, cog, data)
    # Too heavy and too poor at once shows as too heavy on the node
    for index, end in ((0, 41), (1, 41), (2, 55)):
        node_done(driver, index, end)
    press(driver, "bholder.levelnode1")
    browser.wait_for(driver, "window.botArena3.find('iholder')?.frame === 3")
    still(driver, "iholder.backbutton")
    assert nothing_at(driver, "iholder.playbutton")
    details = found(driver, "iholder")["vars"]["details"]
    assert "YOUR TEAM'S WEIGHT: 40\r" in details and "YOUR CASH: 50\r" in details
    press(driver, "iholder.backbutton")
    press(driver, "bholder.levelnode2")
    browser.wait_for(driver, "window.botArena3.find('iholder')?.frame === 2")
    still(driver, "iholder.backbutton")
    assert nothing_at(driver, "iholder.playbutton")
    assert found(driver, "iholder")["vars"]["battlename"] == "CHROMETEK RALLY"
    assert found(driver, "iholder.map.bg.graphic")["frame"] == ARENAS[2].background
    press(driver, "iholder.backbutton")
    press(driver, "bholder.levelnode0")
    browser.wait_for(driver, "window.botArena3.find('iholder')?.frame === 4")
    still(driver, "iholder.backbutton")
    assert nothing_at(driver, "iholder.playbutton")


def test_a_refused_arena_shows_the_bots_words_and_the_arena_again(driver, live, cog):
    data = ready_career()
    arena_list_with(driver, live, cog, data)
    press(driver, "bholder.levelnode0")
    still(driver, "iholder.playbutton")
    # Another device disables the only robot before PLAY reaches the bot
    data["robots"][0]["enabled"] = False
    seed_career(cog, live, data)
    press(driver, "iholder.playbutton")
    browser.wait_for(driver, "!document.getElementById('toast').hidden")
    assert driver.execute_script("return document.getElementById('toast').textContent") == career.ARENA_CLOSED
    still(driver, "iholder.playbutton")
    assert driver.execute_script("return document.body.dataset.screen") == "levelselect"
    assert cog.running(ME) is None


def test_a_challenge_starts_from_the_menu(driver, live, cog):
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b3")
    on_screen(driver, "challengeselect")
    press(driver, "bholder.levelnode1")
    still(driver, "iholder.playbutton")
    info = found(driver, "iholder")
    assert info["frame"] == 1
    assert info["vars"]["battlename"] == CHALLENGES[1].name
    assert info["vars"]["details"] == CHALLENGES[1].description
    assert found(driver, "iholder.map.ob.graphic")["frame"] == CHALLENGES[1].background
    press(driver, "iholder.backbutton")
    press(driver, "bholder.levelnode0")
    press(driver, "iholder.playbutton")
    on_screen(driver, "battle")
    assert cog.running(ME).kind == "challenge" and cog.running(ME).index == 0


def test_the_lists_go_back_to_the_shop_and_the_menu(driver, live, cog):
    arena_list_with(driver, live, cog, ready_career())
    assert still(driver, "bholder.backbutton")["vars"]["displaytext"] == "SHOP"
    press(driver, "bholder.backbutton")
    on_screen(driver, "shop")
    press(driver, "exitbutton")
    on_screen(driver, "menu")
    press(driver, "b3")
    on_screen(driver, "challengeselect")
    assert still(driver, "bholder.backbutton")["vars"]["displaytext"] == "BACK"
    press(driver, "bholder.backbutton")
    on_screen(driver, "menu")


def test_the_win_screen_goes_back_to_the_shop(driver, live, cog):
    run = start_first_arena(driver, live, cog)

    def win_the_game():
        # The battle counts as the one that beats the game, and the player wins it
        run.beats_game = True
        for robot in run.battle.robots[1:]:
            run.battle.hurt(robot, robot.health, team=1)

    on_loop(live, win_the_game)
    on_screen(driver, "wingame", timeout=15)
    press(driver, "backbutton")
    on_screen(driver, "shop")


def start_first_arena(driver, live, cog):
    seed_career(cog, live, ready_career())
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b2")
    on_screen(driver, "shop")
    press(driver, "startbattlebutton")
    on_screen(driver, "levelselect")
    press(driver, "bholder.levelnode0")
    press(driver, "iholder.playbutton")
    on_screen(driver, "battle")
    return cog.running(ME)


def on_loop(live, fn):
    async def run():
        return fn()

    return asyncio.run_coroutine_threadsafe(run(), live.loop).result(5)


def stage_to_page(driver, x, y):
    canvas = driver.find_element(By.CSS_SELECTOR, "#stage canvas")
    w, h = driver.execute_script("const r = arguments[0].getBoundingClientRect(); return [r.width, r.height];", canvas)
    scale = min(w / 640, h / 480)
    return canvas, (x - 320) * scale, (y - 240) * scale


class MostRandom(random.Random):
    """Every random(n) is n - 1: a wreck gets the most flames the original gives one"""

    def randrange(self, start, stop=None, step=1):
        return start - 1 if stop is None else stop - 1


def test_a_battle_draws_its_robots_and_follows_the_bot(driver, live, cog):
    run = start_first_arena(driver, live, cog)
    browser.wait_for(driver, f"Number(document.body.dataset.step) > {3 * 11}", timeout=10)
    assert driver.execute_script("return Number(document.body.dataset.robots)") == len(run.battle.robots)
    # The countdown's "3" shows from the original's frame 41: its frame is the drawn step, a moment behind the bot.
    # Its art is empty for a few frames between numbers, where it can't be found, so both are read together
    step, frame = browser.wait_for(
        driver,
        "(() => { const step = Number(document.body.dataset.step);"
        " const found = window.botArena3.find('startcountdown');"
        " return step > 45 && found !== null && [step, found.frame]; })()",
        timeout=10,
    )
    assert frame == min(step, 161)
    assert 0 < on_loop(live, lambda: run.battle.step) - step <= 2 * 33


def test_dragging_from_a_robot_orders_it(driver, live, cog):
    run = start_first_arena(driver, live, cog)
    mine = run.battle.robots[0]
    canvas, x, y = stage_to_page(driver, mine.x, mine.y)
    _, tx, ty = stage_to_page(driver, 300, 100)
    # Over one of your robots, the original's status rings show its normal order
    assert nothing_at(driver, "ios")
    ActionChains(driver).move_to_element_with_offset(canvas, x, y).pause(0.3).perform()
    browser.wait_for(driver, "window.botArena3.find('ios')?.frame === 3")
    ActionChains(driver).move_to_element_with_offset(canvas, x, y).click_and_hold().move_to_element_with_offset(
        canvas, tx, ty
    ).release().perform()
    eventually(lambda: on_loop(live, lambda: mine.order[0]) == "goto")
    # The original's move marker, on the ground where the drag ended
    browser.wait_for(driver, "window.botArena3.find('mo.stat')?.frame === 1")
    marker = found(driver, "mo")
    left, top, right, bottom = rect_of(driver, "#stage canvas")
    px, py = (left + right) / 2 + tx, (top + bottom) / 2 + ty
    assert marker["x"] <= px <= marker["x"] + marker["w"] and marker["y"] <= py <= marker["y"] + marker["h"]


def test_winning_pays_and_goes_back_to_the_shop(driver, live, cog):
    run = start_first_arena(driver, live, cog)

    def win():
        for robot in run.battle.robots[1:]:
            run.battle.hurt(robot, robot.health, team=1)

    on_loop(live, win)
    # The original's winning banner plays on the countdown, from its "complose" frame
    browser.wait_for(driver, "(window.botArena3.find('startcountdown')?.frame ?? 0) >= 232")
    on_screen(driver, "shop", timeout=15)
    assert saved_career(cog, live)["level"] == 2


def test_on_an_upright_phone_a_touch_drag_gives_an_order(driver, live, cog):
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}
    )
    driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1})
    try:
        run = start_first_arena(driver, live, cog)
        canvas = driver.find_element(By.CSS_SELECTOR, "#stage canvas")
        w, h = driver.execute_script(
            "const r = arguments[0].getBoundingClientRect(); return [r.width, r.height];", canvas
        )
        assert w <= 391 and h <= 845
        mine = run.battle.robots[0]
        canvas, x, y = stage_to_page(driver, mine.x, mine.y)
        _, tx, ty = stage_to_page(driver, 300, 100)
        center = driver.execute_script(
            "const r = arguments[0].getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2];", canvas
        )
        # Touch points are in the top page's coordinates, and the game sits in the hub's frame
        driver.switch_to.default_content()
        frame = driver.execute_script(
            "const r = document.getElementById('game-frame').getBoundingClientRect(); return [r.x, r.y];"
        )
        for kind, px, py in (("touchStart", x, y), ("touchMove", tx, ty), ("touchEnd", tx, ty)):
            point = {"x": frame[0] + center[0] + px, "y": frame[1] + center[1] + py}
            driver.execute_cdp_cmd(
                "Input.dispatchTouchEvent", {"type": kind, "touchPoints": [] if kind == "touchEnd" else [point]}
            )
        driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
        eventually(lambda: on_loop(live, lambda: mine.order[0]) == "goto")
    finally:
        driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": False})
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_a_page_that_reconnects_mid_battle_gets_the_battle_back(driver, live, cog):
    run = start_first_arena(driver, live, cog)
    enemy = run.battle.robots[1]
    browser.wait_for(driver, f"window.botArena3.find('stats{enemy.id}') !== null")

    async def drop_and_wreck():
        # The connection drops, and an enemy is wrecked before the page is back: the page never hears of it
        await live.server.rooms.close_all()
        run.battle.rng = MostRandom()
        run.battle.hurt(enemy, enemy.health, team=1)

    on_server(live, drop_and_wreck())
    # The battle the bot sends again shows the wreck: no name or health bar, and its four flames
    browser.wait_for(
        driver,
        f"window.botArena3.find('stats{enemy.id}') === null && window.botArena3.find('fire3') !== null",
        timeout=20,
    )
    assert driver.execute_script("return document.body.dataset.screen") == "battle"
    assert driver.execute_script("return Number(document.body.dataset.robots)") == len(run.battle.robots)
    assert nothing_at(driver, "fire4")


def test_a_battle_the_bot_stopped_goes_back_to_the_shop(driver, live, cog):
    run = start_first_arena(driver, live, cog)
    browser.wait_for(driver, "Number(document.body.dataset.step) > 0")

    def stop():
        # As when the battle loop fails: the battle leaves the window's list, and no "over" comes
        window = next(w for w in cog.windows.values() if run.id in w.runs)
        del window.runs[run.id]
        window.dirty = True

    on_loop(live, stop)
    on_screen(driver, "shop", timeout=15)


def elsewhere(cog, live, run):
    """A battle of the player's that no list in this window shows, as when it runs in another window"""

    def another():
        window = next(w for w in cog.windows.values() if run.id in w.runs)
        message = window.full(run, window.room.connections[0])
        message["battle"]["id"] = "elsewhere"
        return message

    tell_page(cog, live, on_loop(live, another))


def test_a_new_battle_on_the_battle_screen_is_judged_on_its_own_listing(driver, live, cog):
    run = start_first_arena(driver, live, cog)
    browser.wait_for(driver, "Number(document.body.dataset.step) > 0")
    tell_page(
        cog, live, {"lobby": {"battles": [{"id": run.id, "kind": "arena", "title": "", "names": []}], "fights": []}}
    )
    # A different battle takes the screen; a list without it then says nothing about it, since no list has shown it
    elsewhere(cog, live, run)
    tell_page(cog, live, {"lobby": {"battles": [], "fights": []}})
    assert stays(driver, "document.body.dataset.screen === 'battle'")


def test_a_battle_in_another_window_that_ended_unheard_goes_back_to_the_shop(driver, live, cog):
    run = start_first_arena(driver, live, cog)
    browser.wait_for(driver, "Number(document.body.dataset.step) > 0")
    elsewhere(cog, live, run)
    # The connection came back after the battle ended: its "over" never came, and the bot says there's no battle now
    tell_page(cog, live, {"lobby": {"battles": [], "fights": []}, "mine": None})
    on_screen(driver, "shop", timeout=15)


def test_a_battle_in_another_window_still_running_stays_on_screen(driver, live, cog):
    run = start_first_arena(driver, live, cog)
    browser.wait_for(driver, "Number(document.body.dataset.step) > 0")
    elsewhere(cog, live, run)
    tell_page(cog, live, {"lobby": {"battles": [], "fights": []}, "mine": "elsewhere"})
    assert stays(driver, "document.body.dataset.screen === 'battle'")


class Guest:
    """A second player in the page's window, talking to the bot directly. Not in the hub's room, so the bot's
    broadcasts don't reach it, which these tests don't need"""

    def __init__(self, cog, user_id=902, name="Vainne"):
        window = next(iter(cog.windows.values()))
        author = SimpleNamespace(
            id=user_id, name=name, display_name=name, global_name=name, display_avatar=SimpleNamespace(url="")
        )
        self.ctx = SimpleNamespace(author=author, instance_id="i-1", room_id=window.room.id)
        self.room = window.room
        self.sent = []

    async def send(self, data):
        self.sent.append(data)


def guest_in(live, cog, user_id=902, name="Vainne"):
    return Guest(cog, user_id, name)


def say(cog, live, conn, kind, value):
    asyncio.run_coroutine_threadsafe(cog.message(conn.ctx, conn, {kind: value}), live.loop).result(5)


def open_fight_id(live, cog):
    return on_loop(live, lambda: next(iter(next(iter(cog.windows.values())).fights)))


def set_career(cog, live, user_id, data):
    asyncio.run_coroutine_threadsafe(cog.config.user_from_id(user_id).career.set(data), live.loop).result(5)


def pvp_screen(driver, live, cog, data=None):
    """The PvP screen, from the menu, for a player with this career"""
    if data is not None:
        seed_career(cog, live, data)
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "pvpbutton")
    on_screen(driver, "pvp")


def row(driver, path):
    """A list row's words: its title and its details line"""
    words = found(driver, path)["vars"]
    return words["itemtitle"], words["itemdetails"]


def test_a_fight_opened_on_the_page_can_be_joined(driver, live, cog):
    pvp_screen(driver, live, cog, ready_career())
    # The weight classes list no limit first, then the original's six
    assert row(driver, "weightlist.itemhold.row0") == ("NO LIMIT", "")
    assert row(driver, "weightlist.itemhold.row1") == ("ORIENTATION", f"WEIGHT LIMIT: {WEIGHT_CLASSES['ORIENTATION']}")
    press(driver, "weightlist.itemhold.row1")
    press(driver, "arenalist.itemhold.row1")
    press(driver, "openfight")
    browser.wait_for(driver, "document.body.dataset.fights === '1'")
    (fight,) = on_loop(live, lambda: list(next(iter(cog.windows.values())).fights.values()))
    assert (fight.background, fight.weight) == (2, "ORIENTATION")
    # Your own fight says it can be cancelled
    assert row(driver, "fightlist.itemhold.row0")[1] == "CANCEL"
    guest = guest_in(live, cog)
    set_career(cog, live, 902, ready_career())
    say(cog, live, guest, "join", open_fight_id(live, cog))
    on_screen(driver, "battle")
    assert cog.running(ME).players == {ME: 1, 902: 2}


def test_tapping_someone_elses_fight_joins_it_on_the_right(driver, live, cog):
    pvp_screen(driver, live, cog, ready_career())
    guest = guest_in(live, cog)
    set_career(cog, live, 902, ready_career())
    say(cog, live, guest, "open", [3, None, "server"])
    browser.wait_for(driver, "document.body.dataset.fights === '1'")
    assert row(driver, "fightlist.itemhold.row0") == ("VAINNE", "NO LIMIT")
    press(driver, "fightlist.itemhold.row0")
    on_screen(driver, "battle")
    run = cog.running(ME)
    assert run.players == {902: 1, ME: 2} and run.background == 3
    assert driver.execute_script("return document.body.dataset.watching") is None


def test_your_own_fight_row_cancels_it(driver, live, cog):
    pvp_screen(driver, live, cog, ready_career())
    press(driver, "weightlist.itemhold.row0")
    press(driver, "arenalist.itemhold.row0")
    press(driver, "openfight")
    browser.wait_for(driver, "document.body.dataset.fights === '1'")
    assert on_loop(live, lambda: next(iter(next(iter(cog.windows.values())).fights.values())).weight) is None
    press(driver, "fightlist.itemhold.row0")
    browser.wait_for(driver, "document.body.dataset.fights === '0'")
    assert on_loop(live, lambda: next(iter(cog.windows.values())).fights) == {}


def test_the_fights_list_stays_scrolled_when_a_fight_is_added(driver, live, cog):
    pvp_screen(driver, live, cog)

    def open_by(user_id):
        set_career(cog, live, user_id, ready_career())
        say(cog, live, guest_in(live, cog, user_id, f"Player {user_id}"), "open", [1, None, "server"])

    for user_id in range(910, 917):
        open_by(user_id)
    browser.wait_for(driver, "document.body.dataset.fights === '7'")
    third = "fightlist.itemhold.row2"
    # Scrolled to the bottom, 7 rows of 40 in a list that shows 220, the rows sit 60 higher
    scrolled = still(driver, third)["y"] - 60 * stage_scale(driver)
    near = f"Math.abs(window.botArena3.find('{third}')?.y - {scrolled}) < 1"
    scroller = still(driver, "fightlist.scroller")
    pointer_at(driver, scroller["x"] + scroller["w"] / 2, scroller["y"] + scroller["h"] / 2).click_and_hold().pause(
        0.2
    ).move_by_offset(0, round(200 * stage_scale(driver))).pause(0.3).release().perform()
    browser.wait_for(driver, near)
    open_by(917)
    browser.wait_for(driver, "document.body.dataset.fights === '8'")
    # The same rows stay where they were, under the player's finger
    assert row(driver, third)[0] == "PLAYER 912"
    assert stays(driver, near)


def finger_swipe(driver, start, end, steps=8):
    """One finger on the game's page from start to end (CSS pixels in the game's frame), a frame per move, then up"""
    driver.switch_to.default_content()
    left, top = driver.execute_script(
        "const r = document.getElementById('game-frame').getBoundingClientRect(); return [r.left, r.top];"
    )
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
    (x0, y0), (x1, y1) = start, end

    def touch(kind, x=None, y=None):
        points = [] if x is None else [{"x": left + x, "y": top + y}]
        driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})
        time.sleep(0.03)

    touch("touchStart", x0, y0)
    for i in range(1, steps + 1):
        touch("touchMove", x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
    touch("touchEnd")


def open_fights_by(live, cog, user_ids):
    for user_id in user_ids:
        set_career(cog, live, user_id, ready_career())
        say(cog, live, guest_in(live, cog, user_id, f"Player {user_id}"), "open", [1, None, "server"])


def test_a_fight_row_held_down_through_a_list_update_still_joins(driver, live, cog):
    pvp_screen(driver, live, cog, ready_career())
    open_fights_by(live, cog, [910])
    browser.wait_for(driver, "document.body.dataset.fights === '1'")
    first = still(driver, "fightlist.itemhold.row0")
    held = pointer_at(driver, first["x"] + first["w"] / 2, first["y"] + first["h"] / 2).click_and_hold()
    held.perform()
    # The list changes while the button is down; the row under it stays the same row
    open_fights_by(live, cog, [911])
    browser.wait_for(driver, "document.body.dataset.fights === '2'")
    ActionChains(driver).release().perform()
    on_screen(driver, "battle")
    assert cog.running(ME).players == {910: 1, ME: 2}


def test_the_wheel_and_a_swipe_scroll_the_fights_list_without_joining(driver, live, cog):
    pvp_screen(driver, live, cog)
    open_fights_by(live, cog, range(910, 917))
    browser.wait_for(driver, "document.body.dataset.fights === '7'")
    third = "fightlist.itemhold.row2"
    top = still(driver, third)["y"]
    scale = stage_scale(driver)
    # Scrolled to the bottom, 7 rows of 40 in a list that shows 220, the rows sit 60 higher
    bottom = f"Math.abs(window.botArena3.find('{third}')?.y - {top - 60 * scale}) < 1"
    first = still(driver, "fightlist.itemhold.row0")
    middle = (first["x"] + first["w"] / 2, first["y"] + first["h"] / 2)
    canvas = driver.find_element(By.CSS_SELECTOR, "#stage canvas")
    left, upper_edge, right, lower_edge = rect_of(driver, "#stage canvas")
    origin = ScrollOrigin.from_element(
        canvas, round(middle[0] - (left + right) / 2), round(middle[1] - (upper_edge + lower_edge) / 2)
    )
    ActionChains(driver).scroll_from_origin(origin, 0, 300).perform()
    browser.wait_for(driver, bottom)
    # A finger dragging the rows down scrolls them back, and lets go without joining the fight under it
    try:
        finger_swipe(driver, middle, (middle[0], middle[1] + 70 * scale))
        browser.wait_for(driver, f"Math.abs(window.botArena3.find('{third}')?.y - {top}) < 1")
    finally:
        driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": False})
    assert stays(driver, "document.body.dataset.screen === 'pvp'")
    assert cog.running(ME) is None


def test_fights_from_your_own_channel_come_first(driver, live, cog):
    live.add_person(fakes.MANAGER_ID, where="botarena3")
    pvp_screen(driver, live, cog)
    open_fights_by(live, cog, [910, fakes.MANAGER_ID])
    browser.wait_for(driver, "document.body.dataset.fights === '2'")
    assert row(driver, "fightlist.itemhold.row0")[0] == f"PLAYER {fakes.MANAGER_ID}"
    assert row(driver, "fightlist.itemhold.row1")[0] == "PLAYER 910"


def test_a_fight_opened_for_my_channel_is_kept_to_the_window(driver, live, cog):
    pvp_screen(driver, live, cog, ready_career())
    assert driver.execute_script("return document.body.dataset.who") == "server"
    press(driver, "whochannel")
    browser.wait_for(driver, "document.body.dataset.who === 'channel'")
    press(driver, "weightlist.itemhold.row0")
    press(driver, "arenalist.itemhold.row0")
    press(driver, "openfight")
    browser.wait_for(driver, "document.body.dataset.fights === '1'")
    (fight,) = on_loop(live, lambda: list(next(iter(cog.windows.values())).fights.values()))
    assert fight.instance_id == "i-1"
    # Back on the screen, the whole server is picked again
    press(driver, "backbutton")
    on_screen(driver, "menu")
    press(driver, "pvpbutton")
    on_screen(driver, "pvp")
    assert driver.execute_script("return document.body.dataset.who") == "server"


def test_open_fight_shows_the_originals_error_when_the_team_cant_go(driver, live, cog):
    data = career.new_career()
    career.buy(data, 'AKAUMIN "DLZ-100"')
    pvp_screen(driver, live, cog, data)
    # OPEN FIGHT works once an arena and a weight class are picked, as the shop's buttons wait for a pick
    assert found(driver, "openfight")["alpha"] == 0.5
    press(driver, "weightlist.itemhold.row0")
    press(driver, "arenalist.itemhold.row0")
    assert found(driver, "openfight")["alpha"] == 1
    press(driver, "openfight")
    browser.wait_for(driver, "document.body.dataset.monitor === 'error'")
    assert monitor(driver)[1]["txt_displaytext"] == f"{career.CANT_FIGHT_BECAUSE}\r{career.UNPLATED}\r"
    assert stays(driver, "document.body.dataset.fights === '0'")


def test_open_fight_shows_the_originals_too_heavy_words(driver, live, cog):
    data = ready_career()
    data["robots"][0]["chassis"] = 'XEROI "DELIVERANCE"'
    data["robots"][0]["plating"] = 'GAIACORP "LB-MK2"'
    assert career.view(data)["weight"] > WEIGHT_CLASSES["ORIENTATION"]
    pvp_screen(driver, live, cog, data)
    press(driver, "weightlist.itemhold.row1")
    press(driver, "arenalist.itemhold.row0")
    press(driver, "openfight")
    browser.wait_for(driver, "document.body.dataset.monitor === 'error'")
    # The arena list's own words for a team too heavy for a battle
    assert monitor(driver)[1]["txt_displaytext"] == (
        "SORRY, YOUR TEAM OF ROBOTS WEIGH TOO MUCH TO ENTER THIS BATTLE.\r\r"
        "HINT: RETURN TO THE SHOP SCREEN AND DISABLE SOME OF YOUR BOTS."
    )
    assert stays(driver, "document.body.dataset.fights === '0'")
    # With no limit the same team goes, and the error goes with the fight the bot opened
    press(driver, "weightlist.itemhold.row0")
    press(driver, "openfight")
    browser.wait_for(driver, "document.body.dataset.fights === '1'")
    browser.wait_for(driver, "document.body.dataset.monitor === undefined")
    assert found(driver, "infomon.screen")["frame"] == 1


def test_watching_someone_elses_battle(driver, live, cog):
    open_game(driver, live)
    on_screen(driver, "menu")
    guest = guest_in(live, cog)
    say(cog, live, guest, "challenge", 0)
    press(driver, "watchbutton")
    on_screen(driver, "watch")
    assert row(driver, "watchlist.itemhold.row0") == (CHALLENGES[0].name, "VAINNE VS COMPUTER")
    press(driver, "watchlist.itemhold.row0")
    on_screen(driver, "battle")
    assert driver.execute_script("return document.body.dataset.watching") == "true"
    run = cog.running(902)
    assert len(run.watchers) == 1
    # LEAVE stops watching and goes back to the list
    press(driver, "leavebutton")
    on_screen(driver, "watch")
    assert run.watchers == []
    assert driver.execute_script("return document.body.dataset.watching") is None
    press(driver, "backbutton")
    on_screen(driver, "menu")


def test_a_watcher_that_reconnects_keeps_watching(driver, live, cog):
    open_game(driver, live)
    on_screen(driver, "menu")
    guest = guest_in(live, cog)
    say(cog, live, guest, "challenge", 0)
    press(driver, "watchbutton")
    on_screen(driver, "watch")
    press(driver, "watchlist.itemhold.row0")
    on_screen(driver, "battle")
    run = cog.running(902)
    eventually(lambda: len(run.watchers) == 1)
    first = run.watchers[0]
    # The bot forgets a watcher whose connection closes; the page asks again once it is back
    on_server(live, live.server.rooms.close_all())
    eventually(lambda: len(run.watchers) == 1 and run.watchers[0] is not first, timeout=20)
    assert driver.execute_script("return document.body.dataset.screen") == "battle"


def test_your_fight_starting_as_a_watched_battle_ends_takes_you_to_it(driver, live, cog):
    pvp_screen(driver, live, cog, ready_career())
    press(driver, "weightlist.itemhold.row0")
    press(driver, "arenalist.itemhold.row0")
    press(driver, "openfight")
    browser.wait_for(driver, "document.body.dataset.fights === '1'")
    fight_id = open_fight_id(live, cog)
    press(driver, "backbutton")
    on_screen(driver, "menu")
    say(cog, live, guest_in(live, cog), "challenge", 0)
    press(driver, "watchbutton")
    on_screen(driver, "watch")
    press(driver, "watchlist.itemhold.row0")
    on_screen(driver, "battle")
    browser.wait_for(driver, "document.body.dataset.watching === 'true'")
    watched = cog.running(902)
    joiner = guest_in(live, cog, 903, "Mira")
    set_career(cog, live, 903, ready_career())

    async def end_and_join():
        # The watched battle ends, so the page starts its fade back to Watch, and someone joins the player's fight
        # right behind it
        window = next(iter(cog.windows.values()))
        await window.finish(watched)
        await cog.message(joiner.ctx, joiner, {"join": fight_id})

    on_server(live, end_and_join())
    assert cog.running(ME).players == {ME: 1, 903: 2}
    # The fade ends on the player's own fight, not on Watch
    browser.wait_for(driver, "document.body.dataset.watching === undefined")
    assert stays(driver, "document.body.dataset.screen === 'battle'", seconds=3)
    assert driver.execute_script("return document.body.dataset.watching") is None
    # The watched battle's end, coming again late, doesn't take the player away from their fight
    tell_page(cog, live, {"over": {"id": watched.id, "next": "watch"}})
    assert stays(driver, "document.body.dataset.screen === 'battle'", seconds=2)
    step = int(driver.execute_script("return document.body.dataset.step"))
    browser.wait_for(driver, f"Number(document.body.dataset.step) > {step}")


def start_guests_fight(live, cog):
    """Two players who aren't on the page fight each other in its window"""
    first, second = guest_in(live, cog), guest_in(live, cog, 903, "Mira")
    for user_id in (902, 903):
        set_career(cog, live, user_id, ready_career())
    say(cog, live, first, "open", [1, None, "server"])
    say(cog, live, second, "join", open_fight_id(live, cog))
    return cog.running(902)


@pytest.mark.parametrize("winner,words", [(1, "VAINNE WINS"), (2, "MIRA WINS")])
def test_a_watcher_sees_the_winners_name(driver, live, cog, winner, words):
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "watchbutton")
    on_screen(driver, "watch")
    run = start_guests_fight(live, cog)
    browser.wait_for(driver, "window.botArena3.find('watchlist.itemhold.row0') !== null")
    assert row(driver, "watchlist.itemhold.row0") == ("PVP", "VAINNE VS MIRA")
    press(driver, "watchlist.itemhold.row0")
    on_screen(driver, "battle")
    on_loop(live, lambda: run.battle.finish(winner))
    shows_words(driver, words)
    # The words take the banner's place: neither side's banner shows
    assert nothing_at(driver, "startcountdown.547") and nothing_at(driver, "startcountdown.549")
    on_screen(driver, "watch", timeout=15)


def shows_words(driver, words):
    """The countdown shows these words on the stage, where the original's banner goes"""
    script = (
        "window.botArena3.find('startcountdown')?.vars.result === arguments[0]"
        " && window.botArena3.find('startcountdown.result') !== null"
    )
    end = time.monotonic() + 10
    while not driver.execute_script(f"return {script}", words):
        assert time.monotonic() < end, f"the battle never showed {words}"
        time.sleep(0.1)


def test_a_watcher_sees_the_computer_win(driver, live, cog):
    open_game(driver, live)
    on_screen(driver, "menu")
    guest = guest_in(live, cog)
    say(cog, live, guest, "challenge", 0)
    press(driver, "watchbutton")
    on_screen(driver, "watch")
    press(driver, "watchlist.itemhold.row0")
    on_screen(driver, "battle")
    run = cog.running(902)
    on_loop(live, lambda: run.battle.finish(2))
    shows_words(driver, "COMPUTER WINS")


def test_a_drawn_pvp_fight_shows_draw_and_goes_back_to_pvp(driver, live, cog):
    pvp_screen(driver, live, cog, ready_career())
    guest = guest_in(live, cog)
    set_career(cog, live, 902, ready_career())
    say(cog, live, guest, "open", [2, None, "server"])
    browser.wait_for(driver, "document.body.dataset.fights === '1'")
    press(driver, "fightlist.itemhold.row0")
    on_screen(driver, "battle")
    run = cog.running(ME)
    on_loop(live, lambda: run.battle.finish(0))
    shows_words(driver, "DRAW")
    assert nothing_at(driver, "startcountdown.547") and nothing_at(driver, "startcountdown.549")
    on_screen(driver, "pvp", timeout=15)


def seed_records(cog, live, records):
    async def write():
        for user_id, (name, wins, losses, draws) in records.items():
            entry = {**leaderboard.DEFAULTS, "name": name, "wins": wins, "losses": losses, "draws": draws}
            await cog.config.user_from_id(user_id).pvp.set(entry)

    on_server(live, write())


def test_the_leaderboard_opens_from_pvp(driver, live, cog):
    # Eleven players above you, so your own row shows under the top ten
    seed_records(cog, live, {1000 + n: (f"Player {n}", 20 - n, n, 1) for n in range(11)})
    seed_records(cog, live, {ME: ("Me", 0, 4, 2)})
    pvp_screen(driver, live, cog)
    press(driver, "boardbutton")
    on_screen(driver, "board")
    browser.wait_for(driver, "window.botArena3.find('boardlist.itemhold.row0') !== null")
    assert row(driver, "boardlist.itemhold.row0") == ("1. PLAYER 0", "WON 20, LOST 0, DREW 1")
    # Your row comes last, under the top ten, once the list scrolls to it
    last = "window.botArena3.find('boardlist.itemhold.row{}')"
    assert driver.execute_script(f"return {last.format(11)}") is None
    scroller = found(driver, "boardlist.scroller")
    pointer_at(driver, scroller["x"] + scroller["w"] / 2, scroller["y"] + scroller["h"] / 2).click_and_hold().pause(
        0.2
    ).move_by_offset(0, round(200 * stage_scale(driver))).pause(0.3).release().perform()
    browser.wait_for(driver, f"{last.format(10)}?.vars.itemtitle === '12. ME'")
    assert row(driver, "boardlist.itemhold.row10")[1] == "WON 0, LOST 4, DREW 2"
    press(driver, "backbutton")
    on_screen(driver, "pvp")
    press(driver, "backbutton")
    on_screen(driver, "menu")


# ---------- Who's here ----------


def me_in_the_window(live):
    """The player's entry in the hub's list of who is here, with the status and busy flag their page last sent"""
    return live.server.presence.windows["i-1"].people[ME]


def says(live, text, busy=False, timeout=10):
    """Wait until the hub's list shows the player doing this"""
    end = time.monotonic() + timeout
    while True:
        me = me_in_the_window(live)
        if (me.status, me.busy) == (text, busy):
            return
        assert time.monotonic() < end, f"the player says {(me.status, me.busy)}, not {(text, busy)}"
        time.sleep(0.1)


def test_the_status_follows_a_career_from_the_menu_to_a_battle_and_back(driver, live, cog):
    seed_career(cog, live, ready_career())
    open_game(driver, live)
    on_screen(driver, "menu")
    says(live, "In the menu")
    press(driver, "b2")
    on_screen(driver, "shop")
    says(live, "In the shop")
    press(driver, "startbattlebutton")
    on_screen(driver, "levelselect")
    says(live, "Picking an arena")
    press(driver, "bholder.levelnode0")
    press(driver, "iholder.playbutton")
    on_screen(driver, "battle")
    # The arena's name, as its list shows it, and a battle of their own: a friend's Join asks first
    says(live, ARENAS[0].name, busy=True)
    run = cog.running(ME)
    on_loop(live, lambda: run.battle.finish(1))
    on_screen(driver, "shop", timeout=15)
    says(live, "In the shop")


def test_the_status_names_a_challenge(driver, live, cog):
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b3")
    on_screen(driver, "challengeselect")
    says(live, "Picking an arena")
    press(driver, "bholder.levelnode0")
    press(driver, "iholder.playbutton")
    on_screen(driver, "battle")
    says(live, f"Challenge: {CHALLENGES[0].name}", busy=True)


def test_the_status_on_pvp_says_whether_your_fight_is_open_and_names_who_you_fight(driver, live, cog):
    pvp_screen(driver, live, cog, ready_career())
    says(live, "Looking for a 1 vs 1")
    press(driver, "weightlist.itemhold.row0")
    press(driver, "arenalist.itemhold.row0")
    press(driver, "openfight")
    says(live, "Waiting for a 1 vs 1")
    press(driver, "boardbutton")
    on_screen(driver, "board")
    says(live, "Looking at the leaderboard")
    press(driver, "backbutton")
    on_screen(driver, "pvp")
    says(live, "Waiting for a 1 vs 1")
    set_career(cog, live, 902, ready_career())
    say(cog, live, guest_in(live, cog), "join", open_fight_id(live, cog))
    on_screen(driver, "battle")
    says(live, "Battle vs Vainne", busy=True)


def test_a_watcher_says_who_they_watch_is_not_busy_and_sees_their_own_face(driver, live, cog):
    open_game(driver, live)
    on_screen(driver, "menu")
    say(cog, live, guest_in(live, cog), "challenge", 0)
    press(driver, "watchbutton")
    on_screen(driver, "watch")
    says(live, "Picking a battle to watch")
    press(driver, "watchlist.itemhold.row0")
    on_screen(driver, "battle")
    says(live, "Watching Vainne vs COMPUTER")
    browser.wait_for(driver, "document.querySelectorAll('#watchers .face').length === 1")
    assert driver.find_element(By.CSS_SELECTOR, "#watchers .face").get_attribute("title") == "You"
    press(driver, "leavebutton")
    on_screen(driver, "watch")
    says(live, "Picking a battle to watch")
    assert driver.find_element(By.ID, "watchers").get_attribute("hidden")


def test_a_connection_closed_for_good_says_not_connected(driver, live, cog):
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b3")
    on_screen(driver, "challengeselect")
    press(driver, "bholder.levelnode0")
    press(driver, "iholder.playbutton")
    on_screen(driver, "battle")
    says(live, f"Challenge: {CHALLENGES[0].name}", busy=True)
    # An admin turned the game off in this server: the page doesn't try again
    on_server(live, live.server.rooms.close_off(fakes.GUILD_ID, ["botarena3"]))
    says(live, "Not connected")


def watched_by(live, cog, run, count, away=()):
    """People watching the battle, from the bot's side; the ones in `away` also in the hub's list, away"""
    ids = [fakes.MANAGER_ID, fakes.ADMIN_ID] + [910 + n for n in range(count - 2)]
    for user_id in ids[:count]:
        if user_id in away:
            live.add_person(user_id, where="botarena3", away=True)
        say(cog, live, guest_in(live, cog, user_id, f"Watcher {user_id}"), "watch", run.id)


def faces(driver):
    return driver.execute_script("return document.querySelectorAll('#watchers .face').length")


def test_watchers_show_as_faces_capped_and_hide_when_nobody_watches(driver, live, cog):
    run = start_first_arena(driver, live, cog)
    # Nobody watching: no empty row
    assert stays(driver, "document.getElementById('watchers').hidden")
    watched_by(live, cog, run, 3, away={fakes.MANAGER_ID})
    browser.wait_for(driver, "document.querySelectorAll('#watchers .face').length === 3")
    assert driver.find_element(By.CSS_SELECTOR, "#watchers .label").text == "3 watching"
    assert driver.execute_script("return document.querySelector('#watchers .more')") is None
    away = driver.find_elements(By.CSS_SELECTOR, "#watchers .face.away")
    assert [face.get_attribute("title") for face in away] == [f"Watcher {fakes.MANAGER_ID}"]
    # A picture that can't load shows the name's first letter
    assert driver.find_element(By.CSS_SELECTOR, "#watchers .face:not(.away)").text == "W"
    watched_by(live, cog, run, 12)
    browser.wait_for(driver, "document.querySelector('#watchers .label')?.textContent === '12 watching'")
    assert faces(driver) == 6
    assert driver.find_element(By.CSS_SELECTOR, "#watchers .more").text == "+6"

    async def everyone_leaves():
        window = cog.windows["server-500"]
        for conn in list(run.watchers):
            window.unwatch(conn)

    on_server(live, everyone_leaves())
    browser.wait_for(driver, "document.getElementById('watchers').hidden")


def test_a_people_list_that_changes_nothing_leaves_the_faces_alone(driver, live, cog):
    run = start_first_arena(driver, live, cog)
    manager = live.add_person(fakes.MANAGER_ID, where="botarena3")
    watched_by(live, cog, run, 2)
    browser.wait_for(driver, "document.querySelectorAll('#watchers .face').length === 2")
    # A face redrawn between a press and its release would lose the tap, and lists arrive several times a second
    driver.execute_script(
        "window.redrawn = 0;"
        "new MutationObserver((list) => { window.redrawn += list.length; })"
        ".observe(document.getElementById('watchers'), { childList: true, subtree: true });"
    )
    live.update_person(manager, where="botarena3", status="Reading the rules")
    time.sleep(1.2)
    assert driver.execute_script("return window.redrawn") == 0
    # The same observer sees a real change: the watcher went away
    live.update_person(manager, where="botarena3", away=True)
    browser.wait_for(driver, "document.querySelectorAll('#watchers .face.away').length === 1")
    assert driver.execute_script("return window.redrawn") > 0


def test_tapping_a_watcher_face_says_who_it_is(driver, live, cog):
    run = start_first_arena(driver, live, cog)
    say(cog, live, guest_in(live, cog, 902, "Vainne"), "watch", run.id)
    browser.wait_for(driver, "document.querySelectorAll('#watchers .face').length === 1")
    driver.find_element(By.CSS_SELECTOR, "#watchers .face").click()
    browser.wait_for(driver, "!document.getElementById('toast').hidden")
    assert driver.find_element(By.ID, "toast").text == "⁨Vainne⁩ is watching."


def apart(a, b):
    return a[2] <= b[0] or a[3] <= b[1] or a[0] >= b[2] or a[1] >= b[3]


def crowd(live, count, first=920):
    """Others in the player's window, in the hub's list, playing Bot Arena 3: the people button grows with them"""
    guild = live.hub.bot.get_guild(fakes.GUILD_ID)
    ids = list(range(first, first + count))
    for user_id in ids:
        user = fakes.fake_user(user_id, f"friend{user_id}")
        live.hub.bot.users[user_id] = user
        guild.members[user_id] = fakes.fake_member(user, guild)
        live.add_person(user_id, where="botarena3")
    return ids


def people_button_width(driver):
    return driver.execute_script("return document.querySelector('#people .hub-people').getBoundingClientRect().width")


@pytest.fixture
def screen(driver):
    """The page at an exact size, phones included: a window can't be made narrower than about 500 pixels"""

    def resize(width, height):
        driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < height},
        )

    yield resize
    driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


# A near 4:3 window, where the stage nearly fills the width, comes with the others
@pytest.mark.parametrize("size", [(1280, 800), (1100, 800), (390, 844), (844, 390)])
def test_the_faces_and_the_people_button_stay_in_the_black_bars(driver, live, cog, screen, size):
    screen(*size)
    run = start_first_arena(driver, live, cog)
    assert driver.execute_script("return [innerWidth, innerHeight]") == list(size)
    # Three others in the window: the people button is a wide pill of faces and a count, not a round button
    crowd(live, 3)
    browser.wait_for(driver, "document.querySelector('#people .hub-people').getBoundingClientRect().width > 70")
    watched_by(live, cog, run, 12)
    browser.wait_for(driver, "document.querySelectorAll('#watchers .face').length === 6")
    # The stage settles in the room the wider button leaves
    time.sleep(0.5)
    stage = rect_of(driver, "#stage canvas")
    # What shows: in a narrow bar the "12 watching" words make way for the faces and the +N
    shown = driver.execute_script(
        "return [...document.querySelectorAll('#watchers > *')].filter((el) => el.getClientRects().length)"
        ".map((el) => { const r = el.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; });"
    )
    assert len(shown) in (7, 8)
    people = rect_of(driver, "#people .hub-people")
    for part in [*shown, people]:
        assert apart(part, stage), (part, stage)
        assert part[0] >= 0 and part[1] >= 0 and part[2] <= size[0] and part[3] <= size[1]
    # Faces and words big enough to read on a phone, and never on top of each other or the people button
    for one, other in zip(shown, shown[1:]):
        assert apart(one, other), (one, other)
    assert all(part[3] - part[1] >= 10 for part in shown), shown
    assert all(apart(part, people) for part in shown), (shown, people)


def test_a_connection_that_keeps_failing_says_not_connected_until_it_is_back(driver, live, cog):
    open_game(driver, live)
    on_screen(driver, "menu")
    press(driver, "b3")
    on_screen(driver, "challengeselect")
    press(driver, "bholder.levelnode0")
    press(driver, "iholder.playbutton")
    on_screen(driver, "battle")
    says(live, f"Challenge: {CHALLENGES[0].name}", busy=True)

    def broken(conn):
        raise RuntimeError("the bot can't take the player back")

    # Every new connection fails as it joins, so the page's tries keep failing
    cog.window_for = broken
    on_server(live, live.server.rooms.close_all())
    says(live, "Not connected", timeout=60)
    # Once a try gets through, the window hears what the player is doing again
    del cog.window_for
    says(live, f"Challenge: {CHALLENGES[0].name}", busy=True, timeout=30)


def join_friend(driver, live, user_id):
    """Open the game the way the hub's Join button does, with the friend as the follow"""
    driver.get(f"{live.url}/{browser.DISCORD_QUERY}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.execute_script(f"window.activityhubHost.join({{id: '{user_id}', name: 'Friend', game: 'botarena3'}})")
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))


def friend_here(live, cog):
    """A friend already in the window when the player's page opens: in the hub's list, and connected to the game"""
    live.add_person(fakes.MANAGER_ID, where="botarena3")

    async def arrive():
        conn = FakeConn(FakeRoom(None, "server-500"), fakes.MANAGER_ID, "i-1")
        await cog.join(conn.ctx, conn)
        return conn

    return on_server(live, arrive())


def test_joining_a_friend_in_a_battle_watches_it(driver, live, cog):
    friend = friend_here(live, cog)
    say(cog, live, friend, "challenge", 0)
    join_friend(driver, live, fakes.MANAGER_ID)
    on_screen(driver, "battle")
    assert driver.execute_script("return document.body.dataset.watching") == "true"
    says(live, f"Watching Player {fakes.MANAGER_ID} vs COMPUTER")
    assert on_loop(live, lambda: [w.ctx.author.id for w in cog.running(fakes.MANAGER_ID).watchers]) == [ME]


def test_joining_a_friend_with_an_open_fight_lands_on_pvp(driver, live, cog):
    friend = friend_here(live, cog)
    set_career(cog, live, fakes.MANAGER_ID, ready_career())
    say(cog, live, friend, "open", [1, None, "server"])
    join_friend(driver, live, fakes.MANAGER_ID)
    on_screen(driver, "pvp")
    browser.wait_for(driver, "document.body.dataset.fights === '1'")
    says(live, "Looking for a 1 vs 1")


def test_joining_a_friend_who_is_not_in_a_battle_or_fight_opens_the_menu(driver, live, cog):
    friend_here(live, cog)
    join_friend(driver, live, fakes.MANAGER_ID)
    on_screen(driver, "menu")
    assert stays(driver, "document.body.dataset.screen === 'menu'")
    says(live, "In the menu")
