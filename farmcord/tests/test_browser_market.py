"""The Market in headless Chrome: seeds bought at the stall, a chick bought into a pen with room, crops and grown
animals sold, FarmCoins turned into credits at the bank counter, the reason when they can't be, the payout settings
shown only to those who may change them, the free seed packet shown only to a farm with nothing left, a refusal
shown over the shop, and the shop on an upright phone"""

import asyncio
import io
import re

import pytest
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.select import Select

from farmcord.catalog import ACHIEVEMENTS, ANIMALS, CANS, COSMETICS, CROPS, PEN_SIZE
from farmcord.common.actions import IN_A_SERVER
from farmcord.common.payouts import PAYOUTS_OFF
from farmcord.game.calendar import HOUR
from farmcord.game.market import EXPECTING, NO_COINS
from farmcord.game.model import Item
from farmcord.game.progress import xp_for_level
from farmcord.tests import test_browser
from farmcord.tests.test_browser import (
    PLAYER_ID,
    SIZES,
    browser,
    change_farm,
    fakes,
    on_loop,
    problems,
    saved_farm,
    text,
    wait_until,
)
from farmcord.tests.test_browser_plots import go_to, grown, make_pen, refresh, tap

driver = test_browser.driver
live = test_browser.live
WILDFLOWERS = CROPS["wildflowers"]
CHICKEN = ANIMALS["chicken"]
# The bot's words when an item's stack is at the storage limit, and the page's when there is no pen for an animal
STORAGE_FULL = "Storage full"
NO_PEN = "Animals need a pen. Unlock a plot and pick Animals."
TABS = ["seeds", "animals", "feed", "tools", "sell", "looks"]


def start_farm(live, level=1, **changes):
    """The player's farm made by a first visit, then given a level and other fields"""
    on_loop(live, live.cog.act_open(fakes.context_for(live.hub), {}))
    on_loop(live, change_farm(live.cog, level=level, xp=xp_for_level(level), **changes))


def payouts(live, **settings):
    on_loop(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set(settings))


def panel_open(driver, title):
    browser.wait_for(
        driver,
        f"document.getElementById('panel').open && document.getElementById('panel-title').textContent === '{title}'",
    )


def show_tab(driver, tab):
    driver.find_element(By.CSS_SELECTOR, f'.shop-tab[data-tab="{tab}"]').click()
    browser.wait_for(
        driver, f"document.querySelector('.shop-tab[data-tab=\"{tab}\"]').getAttribute('aria-pressed') === 'true'"
    )


def open_shop(driver, live, tab):
    go_to(driver, live, "market")
    tap(driver, "stall")
    panel_open(driver, "Shop")
    show_tab(driver, tab)


async def open_pens(cog, *numbers):
    farm = await cog.store.load(PLAYER_ID)
    for number in numbers:
        farm.plots[number].unlocked = True
        farm.plots[number].kind = "animals"
    await cog.store.save(farm)


def row(driver, key):
    return browser.wait_for(driver, f"document.querySelector('.shop-row[data-key=\"{key}\"]')")


def type_count(element, count):
    box = element.find_element(By.CSS_SELECTOR, "input.shop-count")
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys(str(count))


def deals(element):
    return element.find_elements(By.CSS_SELECTOR, "button.deal")


def toast_shown(driver, words):
    """Waits for a toast with these words. A deal's own toast may come after the news it brought, like a badge"""
    browser.wait_for(
        driver, f"[...document.querySelectorAll('#toasts .toast')].some((t) => t.textContent === {words!r})"
    )


def open_bank(driver, live):
    go_to(driver, live, "market")
    tap(driver, "bank")
    panel_open(driver, "Bank")


def test_seeds_are_bought_at_the_stall(driver, live):
    lilies = CROPS["lilies"]
    full = {"seed:wildflowers": Item("seed:wildflowers", 5), "seed:lilies": Item("seed:lilies", 25)}
    start_farm(live, level=lilies.level, coins=100, items=full)
    open_shop(driver, live, "seeds")
    # What the state already shows the bot would refuse: no room left, or too few FarmCoins for that many
    stocked = row(driver, "seed:lilies")
    assert stocked.find_element(By.CSS_SELECTOR, ".shop-why").text == STORAGE_FULL
    assert not deals(stocked)[0].is_enabled()
    type_count(row(driver, "seed:tulips"), 100 // CROPS["tulips"].seed_price + 1)
    assert row(driver, "seed:tulips").find_element(By.CSS_SELECTOR, ".shop-why").text == NO_COINS
    assert not deals(row(driver, "seed:tulips"))[0].is_enabled()
    wildflowers = row(driver, "seed:wildflowers")
    assert "Wildflowers" in wildflowers.text and "Grows in 30 min" in wildflowers.text
    assert wildflowers.find_element(By.CSS_SELECTOR, ".shop-owned").text == "You have 5"
    assert "Tulips" in row(driver, "seed:tulips").text and deals(row(driver, "seed:tulips"))
    # A crop above the player's level shows the level it opens at, and can't be bought
    wheat = row(driver, "seed:wheat")
    assert f"Unlocks at level {CROPS['wheat'].level}" in wheat.text and not deals(wheat)
    # Stepped up once, then typed
    wildflowers.find_element(By.CSS_SELECTOR, "button.more").click()
    assert deals(wildflowers)[0].text.endswith(str(2 * WILDFLOWERS.seed_price))
    type_count(wildflowers, 4)
    assert deals(wildflowers)[0].text.endswith(str(4 * WILDFLOWERS.seed_price))
    deals(wildflowers)[0].click()
    wait_until(driver, lambda: saved_farm(live).items["seed:wildflowers"].quantity == 9)
    assert saved_farm(live).coins == 100 - 4 * WILDFLOWERS.seed_price
    browser.wait_for(
        driver,
        "document.querySelector('.shop-row[data-key=\"seed:wildflowers\"] .shop-owned').textContent === 'You have 9'",
    )
    assert text(driver, "coins") == str(100 - 4 * WILDFLOWERS.seed_price)
    assert not problems(driver)


def test_a_chick_is_bought_into_a_pen_with_room(driver, live):
    start_farm(live, level=CHICKEN.level, coins=100)
    open_shop(driver, live, "animals")
    chicken = row(driver, "baby:chicken")
    # No pen yet: the buttons are off, and the row says why
    assert chicken.find_element(By.CSS_SELECTOR, ".shop-why").text == NO_PEN
    assert [button.is_enabled() for button in deals(chicken)] == [False, False]
    assert f"Unlocks at level {ANIMALS['goose'].level}" in row(driver, "baby:goose").text
    on_loop(live, make_pen(live.cog))
    refresh(driver)
    pens = browser.wait_for(driver, "document.querySelector('.shop-row[data-key=\"baby:chicken\"] select.shop-pen')")
    assert [option.text for option in pens.find_elements(By.TAG_NAME, "option")] == [f"Plot 2 (0 of {PEN_SIZE})"]
    female = row(driver, "baby:chicken").find_element(By.CSS_SELECTOR, 'button.deal[data-sex="female"]')
    female.click()
    wait_until(driver, lambda: len(saved_farm(live).animals) == 1)
    farm = saved_farm(live)
    animal = farm.animals[0]
    assert (animal.kind, animal.sex, animal.plot, animal.adult) == ("chicken", "female", 2, False)
    assert farm.coins == 100 - CHICKEN.baby_price
    toast_shown(driver, "Your new chicken is in Plot 2")
    assert not problems(driver)


def test_a_new_animal_goes_into_the_pen_picked(driver, live):
    start_farm(live, level=CHICKEN.level, coins=100)
    on_loop(live, open_pens(live.cog, 2, 3))
    open_shop(driver, live, "animals")
    pens = Select(row(driver, "baby:chicken").find_element(By.CSS_SELECTOR, "select.shop-pen"))
    assert [option.text for option in pens.options] == [f"Plot 2 (0 of {PEN_SIZE})", f"Plot 3 (0 of {PEN_SIZE})"]
    pens.select_by_value("3")
    row(driver, "baby:chicken").find_element(By.CSS_SELECTOR, 'button.deal[data-sex="male"]').click()
    wait_until(driver, lambda: len(saved_farm(live).animals) == 1)
    animal = saved_farm(live).animals[0]
    assert (animal.kind, animal.sex, animal.plot) == ("chicken", "male", 3)
    toast_shown(driver, "Your new chicken is in Plot 3")
    # The pen picked last is shown first when the shop is drawn again
    pens = Select(row(driver, "baby:chicken").find_element(By.CSS_SELECTOR, "select.shop-pen"))
    assert pens.first_selected_option.text == f"Plot 3 (1 of {PEN_SIZE})"
    assert not problems(driver)


def test_feed_a_tool_and_a_look_are_bought_at_the_stall(driver, live):
    big_can, hat = CANS[1], COSMETICS["straw_hat"]
    start_farm(live, level=CHICKEN.level, coins=1000)
    open_shop(driver, live, "feed")
    feed = row(driver, "feed:chicken")
    type_count(feed, 3)
    deals(feed)[0].click()
    wait_until(driver, lambda: "feed:chicken" in saved_farm(live).items)
    assert saved_farm(live).items["feed:chicken"].quantity == 3
    spent = 3 * CHICKEN.feed_price
    assert saved_farm(live).coins == 1000 - spent
    show_tab(driver, "tools")
    deals(row(driver, "can:1"))[0].click()
    wait_until(driver, lambda: saved_farm(live).can_tier == 1)
    spent += big_can.price
    # A new can arrives full
    assert (saved_farm(live).water, saved_farm(live).coins) == (big_can.capacity, 1000 - spent)
    browser.wait_for(
        driver, "document.querySelector('.shop-row[data-key=\"can:1\"] .shop-owned')?.textContent === 'Yours'"
    )
    show_tab(driver, "looks")
    deals(row(driver, "cosmetic:straw_hat"))[0].click()
    wait_until(driver, lambda: saved_farm(live).outfits == {"straw_hat"})
    assert saved_farm(live).coins == 1000 - spent - hat.price
    browser.wait_for(
        driver,
        "document.querySelector('.shop-row[data-key=\"cosmetic:straw_hat\"] .shop-owned')?.textContent === 'Owned'",
    )
    assert text(driver, "coins") == str(1000 - spent - hat.price)
    assert not problems(driver)


def test_crops_are_sold_from_their_stack(driver, live):
    items = {
        "crop:wildflowers": Item("crop:wildflowers", 6, 24),
        "crop:wildflowers:x": Item("crop:wildflowers:x", 1, 8),
    }
    start_farm(live, items=items)
    open_shop(driver, live, "sell")
    stack = row(driver, "crop:wildflowers")
    assert stack.find_element(By.CSS_SELECTOR, ".shop-owned").text == "You have 6"
    assert "Wildflowers (exceptional)" in row(driver, "crop:wildflowers:x").text
    # The whole stack by default
    assert deals(stack)[0].text.endswith("24")
    type_count(stack, 4)
    assert deals(stack)[0].text.endswith(str(24 * 4 // 6))
    deals(stack)[0].click()
    wait_until(driver, lambda: saved_farm(live).crops_sold == 4)
    farm = saved_farm(live)
    assert (farm.items["crop:wildflowers"].quantity, farm.items["crop:wildflowers"].worth) == (2, 24 - 24 * 4 // 6)
    # The first crop sold also earns its badge, whose FarmCoins come on top. Its XP is too little for a level-up
    assert farm.coins == 24 * 4 // 6 + ACHIEVEMENTS["sell_crop"].coins and farm.level == 1
    toast_shown(driver, f"+{24 * 4 // 6} FarmCoins for 4 Wildflowers")
    browser.wait_for(
        driver,
        "document.querySelector('.shop-row[data-key=\"crop:wildflowers\"] .shop-owned').textContent === 'You have 2'",
    )
    assert not problems(driver)


def test_grown_animals_sell_but_an_expecting_hen_does_not(driver, live):
    start_farm(live)
    hen, rooster, chick = grown("chicken", "female"), grown("chicken", "male"), grown("chicken", "female")
    chick.adult = False
    hen.bred, hen.litter, hen.pregnant_until = True, 1, live.cog.clock() + HOUR
    on_loop(live, make_pen(live.cog, (hen, HOUR), (rooster, HOUR), (chick, 0)))
    open_shop(driver, live, "sell")
    expecting = row(driver, f"animal:{hen.id}")
    assert expecting.find_element(By.CSS_SELECTOR, ".shop-why").text == EXPECTING
    assert not deals(expecting)[0].is_enabled()
    # Babies don't sell
    assert not driver.find_elements(By.CSS_SELECTOR, f'.shop-row[data-key="animal:{chick.id}"]')
    seller = row(driver, f"animal:{rooster.id}")
    assert deals(seller)[0].text.endswith(str(rooster.value))
    deals(seller)[0].click()
    wait_until(driver, lambda: saved_farm(live).animals_sold == 1)
    toast_shown(driver, f"+{rooster.value} FarmCoins for your chicken")
    assert sorted(animal.id for animal in saved_farm(live).animals) == sorted([hen.id, chick.id])
    browser.wait_for(driver, f"!document.querySelector('.shop-row[data-key=\"animal:{rooster.id}\"]')")
    assert not problems(driver)


def test_farmcoins_turn_into_credits_at_the_bank_counter(driver, live):
    payouts(live, on=True, rate=2, cap=100, plays=3)
    start_farm(live, coins=80)
    open_bank(driver, live)
    # The box starts at the most one cash-in takes: 100 credits at 2 a FarmCoin
    browser.wait_for(driver, "document.getElementById('bank-amount')?.value === '50'")
    assert text(driver, "bank-offer") == "50 FarmCoins become 100 credits"
    assert text(driver, "bank-left") == "3 of 3 cash-ins left today"
    # A smaller amount is worth less, as the bot works it out
    box = driver.find_element(By.ID, "bank-amount")
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys("20")
    browser.wait_for(driver, "document.getElementById('bank-offer').textContent === '20 FarmCoins become 40 credits'")
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys("50")
    browser.wait_for(driver, "document.getElementById('bank-offer').textContent === '50 FarmCoins become 100 credits'")
    driver.find_element(By.ID, "bank-convert").click()
    wait_until(driver, lambda: live.cog.payouts.bank.balances.get(PLAYER_ID) == 100)
    assert saved_farm(live).coins == 30
    toast = browser.wait_for(driver, "[...document.querySelectorAll('#toasts .toast')].at(-1)?.textContent")
    assert toast.startswith("+100 credits for 50 FarmCoins")
    # The box starts again from what is left
    browser.wait_for(driver, "document.getElementById('bank-amount').value === '30'")
    browser.wait_for(driver, "document.getElementById('bank-left').textContent === '2 of 3 cash-ins left today'")
    assert text(driver, "coins") == "30"
    assert not problems(driver)


def test_a_quick_second_convert_waits_for_the_fresh_offer(driver, live):
    """Until the offer after a conversion arrives, the box and the cash-ins left show the old numbers, and a second
    press would cash in again"""
    payouts(live, on=True, rate=2, cap=100, plays=3)
    start_farm(live, coins=80)
    open_bank(driver, live)
    browser.wait_for(driver, "document.getElementById('bank-amount')?.value === '50'")
    # The bot holds the offers asked for from here on
    gate, held, offer = asyncio.Event(), [], live.cog.payouts.offer

    async def slow_offer(member, coins):
        held.append(coins)
        await gate.wait()
        return await offer(member, coins)

    live.cog.payouts.offer = slow_offer
    convert = driver.find_element(By.ID, "bank-convert")
    try:
        convert.click()
        wait_until(driver, lambda: live.cog.payouts.bank.balances.get(PLAYER_ID) == 100 and held)
        assert not convert.is_enabled()
        convert.click()
    finally:
        live.loop.call_soon_threadsafe(gate.set)
    browser.wait_for(driver, "document.getElementById('bank-left').textContent === '2 of 3 cash-ins left today'")
    browser.wait_for(driver, "document.getElementById('bank-amount').value === '30'")
    assert driver.find_element(By.ID, "bank-convert").is_enabled()
    # Anything a second press sent has had time to arrive
    driver.execute_async_script("setTimeout(arguments[arguments.length - 1], 1000)")
    assert live.cog.payouts.bank.balances == {PLAYER_ID: 100} and saved_farm(live).coins == 30
    assert not problems(driver)


def test_the_bank_counter_says_why_it_cant_convert(driver, live):
    start_farm(live, coins=80)
    open_bank(driver, live)
    why = browser.wait_for(driver, "document.getElementById('bank-why')?.textContent")
    assert why == PAYOUTS_OFF and driver.find_element(By.ID, "bank-why").is_displayed()
    assert not driver.find_element(By.ID, "bank-amount").is_displayed()
    # A player who can't change payouts never sees the settings
    assert not driver.find_elements(By.ID, "bank-gear")
    # In a DM there is no server bank
    payouts(live, on=True, rate=1, cap=1000, plays=3)
    live.location = {"guild_id": None, "channel_id": 77}
    open_bank(driver, live)
    assert browser.wait_for(driver, "document.getElementById('bank-why')?.textContent") == IN_A_SERVER
    assert not problems(driver)


def test_a_server_admin_sets_payouts_at_the_bank_counter(driver, live):
    live.user_id = fakes.MANAGER_ID
    on_loop(live, live.cog.act_open(fakes.context_for(live.hub, user_id=fakes.MANAGER_ID), {}))
    open_bank(driver, live)
    assert browser.wait_for(driver, "document.getElementById('bank-why')?.textContent") == PAYOUTS_OFF
    driver.find_element(By.ID, "bank-gear").click()
    browser.wait_for(driver, "document.getElementById('payouts').open && document.getElementById('payouts-rate').value")
    assert text(driver, "payouts-rate-label") == "Credits per FarmCoin"
    assert driver.find_element(By.ID, "payouts-global").get_attribute("hidden") is not None
    driver.find_element(By.ID, "payouts-on").click()
    driver.find_element(By.ID, "payouts-plays").send_keys(Keys.BACKSPACE, "5")
    driver.find_element(By.ID, "save-payouts").click()
    browser.wait_for(driver, "document.getElementById('payouts-status').textContent === 'Saved.'")
    saved = on_loop(live, live.cog.payouts.settings(live.hub.bot.get_guild(fakes.GUILD_ID)))
    assert saved == {"on": True, "rate": 1, "cap": 1000, "plays": 5}
    # A bad number is refused with the bot's own words, in the dialog
    driver.find_element(By.ID, "payouts-plays").send_keys(Keys.BACKSPACE)
    driver.find_element(By.ID, "save-payouts").click()
    browser.wait_for(driver, "document.getElementById('payouts-status').textContent.includes('Cash-ins a day')")
    driver.find_element(By.ID, "close-payouts").click()
    # Payouts are on now, so the counter offers a conversion. This farm has no FarmCoins yet
    browser.wait_for(driver, "document.getElementById('bank-amount')?.value === '0'")
    assert text(driver, "bank-left") == "5 of 5 cash-ins left today"
    assert not driver.find_element(By.ID, "bank-convert").is_enabled()
    assert text(driver, "bank-convert-why") == "You have no FarmCoins to convert."
    assert not problems(driver)


def test_the_free_packet_shows_only_for_a_farm_with_nothing_left(driver, live):
    start_farm(live)
    go_to(driver, live, "market")
    # A new farm has seeds to plant
    browser.wait_for(driver, "!document.getElementById('market-buttons').hidden")
    assert driver.find_element(By.ID, "free-packet").get_attribute("hidden") is not None
    # The leaderboard is on the farmhouse board, not here
    assert driver.find_elements(By.ID, "top-farms") == []
    on_loop(live, change_farm(live.cog, items={}))
    refresh(driver)
    packet = browser.wait_for(
        driver, "!document.getElementById('free-packet').hidden && document.getElementById('free-packet')"
    )
    packet.click()
    wait_until(driver, lambda: "seed:wildflowers" in saved_farm(live).items)
    assert saved_farm(live).items["seed:wildflowers"].quantity == 1
    browser.wait_for(driver, "document.getElementById('free-packet').hidden")
    assert not problems(driver)


def test_a_refusal_shows_over_the_shop(driver, live):
    start_farm(live, coins=100)
    open_shop(driver, live, "seeds")
    # The bot's farm has spent its FarmCoins since the page last heard, so the bot says no
    on_loop(live, change_farm(live.cog, coins=0))
    deals(row(driver, "seed:wildflowers"))[0].click()
    toast = browser.wait_for(driver, "document.querySelector('#toasts .toast.error')")
    assert toast.get_attribute("textContent") == NO_COINS
    # A modal box makes the rest of the page ignore taps, toasts included, so whether the toast is drawn over the shop
    # is read from the screen: the middle of its left edge shows its own background, not the shop's
    driver.execute_async_script("setTimeout(arguments[arguments.length - 1], 400)")
    color = driver.execute_script("return getComputedStyle(arguments[0]).backgroundColor", toast)
    shot = Image.open(io.BytesIO(toast.screenshot_as_png)).convert("RGB")
    drawn = shot.getpixel((6, shot.height // 2))
    assert drawn == tuple(int(part) for part in re.findall(r"\d+", color)[:3])
    assert not problems(driver)


@pytest.mark.parametrize("tab", TABS)
def test_the_shop_fits_an_upright_phone(driver, live, tab):
    start_farm(live, level=60, coins=5000, items={"crop:corn": Item("crop:corn", 3, 150)})
    on_loop(live, make_pen(live.cog, (grown("cow", "female"), HOUR)))
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", SIZES["phone"])
    try:
        go_to(driver, live, "market")
        tap(driver, "stall")
        panel_open(driver, "Shop")
        driver.find_element(By.CSS_SELECTOR, f'.shop-tab[data-tab="{tab}"]').click()
        sizes = driver.execute_script(
            """
            const panel = document.getElementById('panel');
            const boxes = [...panel.querySelectorAll('.shop-tab, .shop-row button, .shop-row input, .shop-row select')]
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
