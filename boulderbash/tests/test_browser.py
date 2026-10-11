import asyncio
import contextlib
import re
import time

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait

from boulderbash.common.rules import MAX_COLORS, board_origin, tile_size
from boulderbash.main import BoulderBash

browser = pytest.importorskip("activityhub.tests.browser")
fakes = pytest.importorskip("activityhub.tests.fakes")

CARD = '#games .card[data-key="boulderbash"]'
KEY = (fakes.GUILD_ID, fakes.MEMBER_ID)
DESKTOP = (1280, 800, 1, False)
UPRIGHT = (390, 844, 2, True)
SIDEWAYS = (844, 390, 2, True)
# A window too narrow beside the boards for a column, where the strip goes in a row under the score
SQUARE = (1024, 768, 1, False)
# A phone held upright with little room above the boards
SHORT_UPRIGHT = (390, 560, 2, True)
SIZES = [
    pytest.param(DESKTOP, id="desktop"),
    pytest.param(UPRIGHT, id="upright"),
    pytest.param(SIDEWAYS, id="sideways"),
]
# Longer than 12 characters as a person sees them, so cut to 11 and an ellipsis. Its 9th is a family of four: seven
# code points that make one picture, which a cut by code points would break apart
LONG_NAME = "\U0001f996\U0001f995 Rock \U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 Smasher of Bedrock"
LONG_NAME_CUT = "\U0001f996\U0001f995 Rock \U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 S…"
# How many others are in the window, from the people button: the page has the newest list once it shows
OTHERS_ON_BUTTON = "document.querySelector('#people .hub-count')?.textContent"
# Records every passing note as it shows, so a test needn't catch the 1.6 s it stays up
RECORD_NOTES = """
window.notes = [];
const box = document.getElementById('pass');
new MutationObserver(() => {
  if (!box.hidden && box.textContent) window.notes.push(box.textContent);
}).observe(box, { childList: true, attributes: true, attributeFilter: ['hidden'] });
"""


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
def live(tmp_path, driver):
    hub = fakes.make_hub()
    cog = BoulderBash(bot=hub.bot)
    cog.payouts.bank = fakes.FakeBank()
    assert fakes.register(hub, cog) is not None
    server = browser.LiveHub(hub, browser.hub_web_copy(tmp_path))
    server.start()
    driver.set_window_size(1280, 800)
    browser.fresh(driver, server)
    server.cog = cog
    yield server
    # Stopped on the server's own event loop, so no game loop is left running when it closes
    asyncio.run_coroutine_threadsafe(cog.cog_unload(), server.loop).result(5)
    server.stop()


def run(live, coro):
    """Run a coroutine on the server's own event loop, where the cog's Config is used"""
    return asyncio.run_coroutine_threadsafe(coro, live.loop).result(5)


async def read(value):
    # A Config value's read is awaitable but not a coroutine, which run_coroutine_threadsafe needs
    return await value()


def open_game(driver, live):
    driver.get(f"{live.url}/{browser.DISCORD_QUERY}")
    browser.wait_for(driver, f"document.querySelector('{CARD}')")
    driver.find_element(By.CSS_SELECTOR, CARD).click()
    browser.wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    browser.wait_for(driver, "!!document.querySelector('#scene canvas')", timeout=20)


def start_mode(driver, mode_name):
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'modes'")
    driver.find_element(By.XPATH, f"//button[@data-mode][text()='{mode_name}']").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'play'", timeout=10)


def pause(driver, ms: int) -> None:
    driver.execute_script(f"return new Promise((done) => setTimeout(done, {ms}))")


def wait_idle(live, driver):
    game = live.cog.games[KEY]
    for _ in range(100):
        # A little past the bot's idle time, since the page plays the same motion a moment later
        if game.idle_at[0] + 150 <= live.cog.clock():
            return game
        pause(driver, 100)
    raise AssertionError("the board never went idle")


def find_pair(board) -> tuple[int, int]:
    """A plain block with a plain neighbor of the same color, so tapping it picks a group"""
    for row in range(board.rows):
        for col in range(board.cols - 1):
            a, b = board.grid[row][col], board.grid[row][col + 1]
            if a and b and not a.special and not b.special and a.color == b.color and a.color < MAX_COLORS:
                return row, col
    raise AssertionError("no pair on the board")


def tap_cell(driver, mode, level, row, col):
    """Click a cell's middle, working out where the page drew it from the stage's transform"""
    transform = driver.execute_script("return document.getElementById('stage').style.transform")
    x, y, scale = (float(n) for n in re.findall(r"[-0-9.]+", transform)[:3])
    left, top = board_origin(mode, level, 0)
    tile_w, tile_h = tile_size(mode, level)
    sx = x + (left + col * tile_w + tile_w / 2) * scale
    sy = y + (top + row * tile_h + tile_h / 2) * scale
    canvas = driver.find_element(By.CSS_SELECTOR, "#scene canvas")
    offset_x = int(sx - canvas.size["width"] / 2)
    offset_y = int(sy - canvas.size["height"] / 2)
    ActionChains(driver).move_to_element_with_offset(canvas, offset_x, offset_y).click().perform()


def smash_a_group(live, driver):
    game = wait_idle(live, driver)
    board = game.boards[0]
    row, col = find_pair(board)
    tap_cell(driver, game.mode, board.level, row, col)
    for _ in range(50):
        if board.selection:
            break
        pause(driver, 50)
    assert (row, col) in board.selection
    tap_cell(driver, game.mode, board.level, row, col)
    browser.wait_for(driver, "document.getElementById('score').textContent !== '0'", timeout=5)
    return game


def problems(driver):
    return [line for line in browser.console_lines(driver) if "Uncaught" in line or "Boulder Bash" in line]


def test_the_title_and_how_to_play_work(driver, live):
    open_game(driver, live)
    assert driver.find_element(By.ID, "start").is_displayed()
    assert not driver.find_element(By.ID, "open-payouts").is_displayed()
    driver.find_element(By.ID, "how").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'help'")
    for page in (2, 3, 4, 1):
        driver.find_element(By.ID, "help-more").click()
        assert driver.find_element(By.CSS_SELECTOR, f'.help-page[data-page="{page}"]').is_displayed()
    driver.find_element(By.ID, "help-back").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'title'")
    assert not problems(driver)


def test_a_normal_game_selects_then_smashes(driver, live):
    open_game(driver, live)
    start_mode(driver, "Normal")
    game = smash_a_group(live, driver)
    assert game.score > 0
    assert driver.find_element(By.ID, "score").text == str(game.score)
    assert "of 100" in driver.find_element(By.ID, "next-0").text
    assert not problems(driver)


def test_an_extreme_x2_game_draws_two_boards(driver, live):
    open_game(driver, live)
    start_mode(driver, "Extreme x2")
    game = wait_idle(live, driver)
    assert len(game.boards) == 2
    assert "of 75" in driver.find_element(By.ID, "next-1").text
    driver.find_element(By.ID, "end").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'over'", timeout=10)
    assert not problems(driver)


def test_the_finished_game_cashes_in_from_the_game_over_tablet(driver, live):
    on = {"on": True, "rate": 1, "cap": 1000, "plays": 3}
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set(on))
    run(live, live.cog.config.member_from_ids(fakes.GUILD_ID, fakes.MEMBER_ID).cashed.set({}))
    open_game(driver, live)
    start_mode(driver, "Normal")
    game = smash_a_group(live, driver)
    driver.find_element(By.ID, "end").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'over'", timeout=10)
    browser.wait_for(driver, "!document.getElementById('cashin').hidden", timeout=10)
    assert f"Worth {game.score} credits" in driver.find_element(By.ID, "cashin-text").text
    assert "New best! #1 on this server" in driver.find_element(By.ID, "standing").text
    driver.find_element(By.ID, "cashin-button").click()
    browser.wait_for(driver, "document.getElementById('cashin').hidden")
    assert f"+{game.score} credits" in driver.find_element(By.ID, "toast").text
    assert live.cog.payouts.bank.balances[fakes.MEMBER_ID] == game.score
    driver.find_element(By.ID, "restart").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'title'")


def test_a_server_admin_sets_payouts_from_the_title(driver, live):
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).payouts.set({}))
    # Saved data lasts across tests, and an earlier one may have cashed in today
    run(live, live.cog.config.guild_from_id(fakes.GUILD_ID).tally.set({}))
    live.user_id = fakes.MANAGER_ID
    open_game(driver, live)
    browser.wait_for(driver, "!document.getElementById('open-payouts').hidden")
    driver.find_element(By.ID, "open-payouts").click()
    assert driver.find_element(By.ID, "payouts-rate-label").text == "Credits per point"
    assert "at most 3,000 credits a day" in driver.find_element(By.ID, "payouts-day").text
    assert "Today: 0 credits paid to 0 players" in driver.find_element(By.ID, "payouts-today").text
    driver.find_element(By.ID, "payouts-on").click()
    driver.find_element(By.ID, "payouts-plays").send_keys(Keys.BACKSPACE, "5")
    driver.find_element(By.ID, "save-payouts").click()
    browser.wait_for(driver, "document.getElementById('payouts-status').textContent === 'Saved.'")
    saved = run(live, read(live.cog.config.guild_from_id(fakes.GUILD_ID).payouts))
    assert saved == {"on": True, "rate": 0.2, "cap": 1000, "plays": 5}
    driver.find_element(By.ID, "payouts-plays").send_keys(Keys.BACKSPACE)
    driver.find_element(By.ID, "save-payouts").click()
    browser.wait_for(driver, "document.getElementById('payouts-status').textContent.includes('Cash-ins a day')")


def test_the_browser_preview_shows_the_title_and_says_to_open_discord(driver, live):
    driver.get(f"{live.url}/games/boulderbash/")
    browser.wait_for(driver, "!!document.querySelector('#scene canvas')", timeout=20)
    driver.find_element(By.ID, "open-scores").click()
    browser.wait_for(driver, "document.getElementById('you').textContent.includes('Open Boulder Bash in Discord')")
    driver.find_element(By.ID, "close-scores").click()
    driver.find_element(By.ID, "start").click()
    browser.wait_for(driver, "!document.getElementById('message').hidden")
    assert "Open Boulder Bash in Discord to play" in driver.find_element(By.ID, "message-text").text
    assert driver.execute_script("return document.getElementById('stage').dataset.screen") == "title"
    assert not problems(driver)


# ---------- Who's here ----------


@contextlib.contextmanager
def at_size(driver, width, height, scale, mobile):
    """The page at a screen size, such as a phone held upright or sideways"""
    metrics = {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": mobile}
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", metrics)
    try:
        yield
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def me(live):
    """The player as the bot's people list sees them"""
    window = live.server.presence.windows.get("i-1")
    return window.people.get(fakes.MEMBER_ID) if window else None


def said(live, status, busy):
    return lambda _: me(live) is not None and me(live).status == status and me(live).busy is busy


def someone(live, user_id, name, score, state="playing", away=False):
    """Another member of the test server in the player's window, in Boulder Bash with this score"""
    guild = live.hub.bot.guilds[fakes.GUILD_ID]
    user = fakes.fake_user(user_id, name)
    member = fakes.fake_member(user, guild)
    member.display_name = name
    live.hub.bot.users[user_id] = user
    guild.members[user_id] = member
    data = {"state": state, "score": score}
    return live.add_person(user_id, where="boulderbash", status=f"Scored {score}", data=data, away=away)


def score_to(live, score):
    """Raise the page's score the way a level's bonus does, with the level complete popup"""
    popup = {"kind": "level", "left": 3, "bonus": 30, "score": score}
    run(live, live.cog.conns[KEY].send({"popup": popup}))


def score_quietly(live, score):
    """Raise the page's score with no popup in the way: a message from the bot that redraws the left board as it is"""
    game = live.cog.games[KEY]

    async def send():
        now = live.cog.clock()
        numbers = game.board_numbers(0, now)
        timer = {"board": 0, "events": [], "clear": game.clearing(0, now), "selection": [], **numbers, "score": score}
        await live.cog.conns[KEY].send({"timer": timer})

    run(live, send())


def count_sends(live, deliver=True):
    """Every people list message the player's menu link sends from now on. Undelivered, the bot never hears them, so
    the player's own entry in everyone's list stays as it was"""
    sent = []
    original = live.server.presence.update

    async def counting(conn, data):
        mine = conn.ctx.author.id == fakes.MEMBER_ID
        if mine:
            sent.append(data)
        if deliver or not mine:
            await original(conn, data)

    live.server.presence.update = counting
    return sent


def box(driver, selector):
    return driver.execute_script(f"return document.querySelector('{selector}').getBoundingClientRect().toJSON()")


def boxes(driver, selector):
    """The boxes of the shown elements matching the selector"""
    return driver.execute_script(
        f"return [...document.querySelectorAll('{selector}')]"
        ".filter((node) => node.offsetParent !== null || getComputedStyle(node).position === 'fixed')"
        ".map((node) => node.getBoundingClientRect().toJSON())"
        ".filter((rect) => rect.width > 0 && rect.height > 0)"
    )


def overlap(a, b, gap=2):
    """Whether two boxes touch, counting a small gap around b as touching"""
    return (
        a["left"] < b["right"] + gap
        and b["left"] - gap < a["right"]
        and a["top"] < b["bottom"] + gap
        and b["top"] - gap < a["bottom"]
    )


def inside_screen(driver, rect):
    width, height = driver.execute_script("return [innerWidth, innerHeight]")
    return rect["left"] >= 0 and rect["top"] >= 0 and rect["right"] <= width and rect["bottom"] <= height


def board_box(driver):
    """Where the scene drew the boards"""
    return driver.execute_script("return window.boulderbashScene.boardsBox()")


def hud_boxes(driver):
    """The score, End Game, the Next level lines and the undo and shuffle slots"""
    return boxes(driver, "#hud-top .score, #end, .next, .slot")


def clear_of(driver, rect, others):
    for other in others:
        assert not overlap(rect, other), (rect, other)


def strip(driver):
    """The strip's entries as (class, rank, name, points), "+N" as ("more", text)"""
    return driver.execute_script(
        "return [...document.querySelectorAll('#live li')].map((li) => li.classList.contains('more')"
        "  ? ['more', li.textContent]"
        "  : [li.className, li.querySelector('.rank').textContent, li.querySelector('.name').textContent,"
        "     li.querySelector('.points').textContent])"
    )


def test_the_title_says_getting_ready(driver, live):
    open_game(driver, live)
    WebDriverWait(driver, 5).until(said(live, "Getting ready", False))
    assert me(live).data == {"state": "idle", "score": None}


def test_a_game_says_its_mode_level_and_score_and_is_busy_until_it_ends(driver, live):
    open_game(driver, live)
    start_mode(driver, "Normal")
    WebDriverWait(driver, 5).until(said(live, "Normal · level 1 · 0", True))
    assert me(live).data == {"state": "playing", "score": 0}
    game = smash_a_group(live, driver)
    WebDriverWait(driver, 5).until(said(live, f"Normal · level 1 · {game.score:,}", True))
    assert me(live).data == {"state": "playing", "score": game.score}
    driver.find_element(By.ID, "end").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'over'", timeout=10)
    WebDriverWait(driver, 5).until(said(live, f"Scored {game.score:,}", False))
    assert me(live).data == {"state": "over", "score": game.score}
    driver.find_element(By.ID, "restart").click()
    WebDriverWait(driver, 5).until(said(live, "Getting ready", False))


def test_a_big_score_has_thousands_separators(driver, live):
    open_game(driver, live)
    start_mode(driver, "Extreme")
    wait_idle(live, driver)
    score_to(live, 12345)
    WebDriverWait(driver, 5).until(said(live, "Extreme · level 1 · 12,345", True))


def test_zen_has_no_score_and_no_strip(driver, live):
    someone(live, 1001, "Ann", 40)
    open_game(driver, live)
    start_mode(driver, "Zen")
    wait_idle(live, driver)
    WebDriverWait(driver, 5).until(said(live, "Playing Zen", True))
    assert me(live).data == {"state": "playing", "score": None}
    # Nobody to compare with in a game that never scores
    time.sleep(0.6)
    assert driver.execute_script("return document.getElementById('live').hidden") is True
    driver.find_element(By.ID, "end").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'over'", timeout=10)
    WebDriverWait(driver, 5).until(said(live, "Finished Zen", False))
    assert me(live).data == {"state": "over", "score": None}


def test_a_two_board_game_says_the_higher_level(driver, live):
    open_game(driver, live)
    start_mode(driver, "Normal x2")
    game = wait_idle(live, driver)
    WebDriverWait(driver, 5).until(said(live, "Normal x2 · level 1 · 0", True))

    async def right_board_up():
        game.boards[1].level = 4
        await live.cog.conns[KEY].send({"level": game.view(1, live.cog.clock())})

    run(live, right_board_up())
    WebDriverWait(driver, 5).until(said(live, "Normal x2 · level 4 · 0", True))


def test_nothing_is_sent_again_while_nothing_changes(driver, live):
    rival = someone(live, 1001, "Ann", 40)
    open_game(driver, live)
    start_mode(driver, "Normal")
    game = smash_a_group(live, driver)
    WebDriverWait(driver, 5).until(said(live, f"Normal · level 1 · {game.score:,}", True))
    # The hub passes on every call, even one that changes nothing, so a page that told it again on every redraw
    # would send the window's list around again each time
    time.sleep(0.6)
    sent = count_sends(live)
    # New people lists, and a message from the bot that redraws the numbers without changing them
    for score in (41, 42, 43):
        live.update_person(rival, where="boulderbash", status="Playing", data={"state": "playing", "score": score})
        time.sleep(0.3)
    run(live, live.cog.conns[KEY].send({"done": {"board": 0}}))
    time.sleep(1.2)
    assert sent == []
    driver.find_element(By.ID, "end").click()
    WebDriverWait(driver, 5).until(lambda _: sent)
    assert sent[-1]["busy"] is False


def test_a_closed_connection_says_not_connected(driver, live):
    open_game(driver, live)
    start_mode(driver, "Normal")
    WebDriverWait(driver, 5).until(said(live, "Normal · level 1 · 0", True))
    run(live, live.cog.conns[KEY].close(4100))
    browser.wait_for(driver, "!document.getElementById('message').hidden")
    WebDriverWait(driver, 5).until(said(live, "Not connected", False))


def test_the_browser_preview_has_a_people_button_and_says_nothing(driver, live):
    driver.get(f"{live.url}/games/boulderbash/")
    browser.wait_for(driver, "!!document.querySelector('#people .hub-people')", timeout=20)
    assert me(live) is None


def check_people_button(driver):
    button = box(driver, "#people .hub-people")
    assert inside_screen(driver, button)
    clear_of(driver, button, boxes(driver, ".sign, .icon-button, .logo, .slab, .result"))
    return button


@pytest.mark.parametrize("size", SIZES)
def test_the_people_button_keeps_clear_of_the_game_on_every_screen(driver, live, size):
    with at_size(driver, *size):
        live.user_id = fakes.MANAGER_ID
        open_game(driver, live)
        browser.wait_for(driver, "!document.getElementById('open-payouts').hidden")
        button = check_people_button(driver)
        # Next to Back, the same height as its middle
        back = box(driver, "#back")
        assert (
            button["left"] > back["right"] and abs(button["top"] + button["bottom"] - back["top"] - back["bottom"]) < 2
        )
        driver.find_element(By.ID, "how").click()
        browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'help'")
        check_people_button(driver)
        driver.find_element(By.ID, "help-back").click()
        driver.find_element(By.ID, "start").click()
        browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'modes'")
        check_people_button(driver)
        driver.find_element(By.XPATH, "//button[@data-mode][text()='Normal x2']").click()
        browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'play'", timeout=10)
        browser.wait_for(driver, "document.getElementById('next-1').textContent !== ''")
        button = check_people_button(driver)
        clear_of(driver, button, [*hud_boxes(driver), board_box(driver)])
        driver.find_element(By.ID, "end").click()
        browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'over'", timeout=10)
        check_people_button(driver)


def test_the_strip_is_hidden_when_alone(driver, live):
    open_game(driver, live)
    start_mode(driver, "Normal")
    wait_idle(live, driver)
    # Someone in the menu, someone in another game with a score of its own, and someone playing Zen, with no score,
    # are not in it
    live.add_person(fakes.ADMIN_ID)
    live.add_person(fakes.OWNER_ID, where="2048", status="Scored 9", data={"state": "over", "score": 9})
    someone(live, 1001, "Zed", None)
    browser.wait_for(driver, f"{OTHERS_ON_BUTTON} === '3'")
    assert driver.execute_script("return document.getElementById('live').hidden") is True


def test_the_strip_shows_only_while_a_game_is_on(driver, live):
    someone(live, 1001, "Ann", 40)
    open_game(driver, live)
    browser.wait_for(driver, f"{OTHERS_ON_BUTTON} === '1'")
    assert driver.execute_script("return document.getElementById('live').hidden") is True
    start_mode(driver, "Normal")
    browser.wait_for(driver, "!document.getElementById('live').hidden")
    assert strip(driver) == [["", "1", "Ann", "40"], ["mine", "2", "You", "0"]]
    driver.find_element(By.ID, "end").click()
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'over'", timeout=10)
    assert driver.execute_script("return document.getElementById('live').hidden") is True


@pytest.mark.parametrize("size", [*SIZES, pytest.param(SQUARE, id="square")])
def test_the_strip_ranks_everyone_here_and_keeps_clear_of_the_game(driver, live, size):
    with at_size(driver, *size):
        someone(live, 1001, "Ann", 2400)
        someone(live, 1002, LONG_NAME, 1800)
        someone(live, 1003, "Bob", 950, state="over", away=True)
        someone(live, 1004, "Cleopatra", 3100)
        open_game(driver, live)
        start_mode(driver, "Normal x2")
        wait_idle(live, driver)
        browser.wait_for(driver, "document.querySelectorAll('#live li').length > 0")
        if size == DESKTOP:
            assert strip(driver) == [
                ["", "1", "Cleopatra", "3,100"],
                ["", "2", "Ann", "2,400"],
                ["", "3", LONG_NAME_CUT, "1,800"],
                ["away", "4", "Bob", "950"],
                ["mine", "5", "You", "0"],
            ]
        else:
            # Three on a phone or in a row, with the player's own place last
            assert strip(driver) == [
                ["", "1", "Cleopatra", "3,100"],
                ["", "2", "Ann", "2,400"],
                ["mine", "5", "You", "0"],
                ["more", "+2"],
            ]
        rect = box(driver, "#live")
        assert inside_screen(driver, rect)
        clear_of(driver, rect, [*hud_boxes(driver), board_box(driver), box(driver, "#people .hub-people")])
        # Readable on a phone, and never in the way of a tap
        sizes = driver.execute_script(
            "return [...document.querySelectorAll('#live .name')].map((n) => parseFloat(getComputedStyle(n).fontSize))"
        )
        assert min(sizes) >= 10
        assert driver.execute_script("return getComputedStyle(document.getElementById('live')).pointerEvents") == "none"


def entries_fit(driver):
    """No two entries of the strip touch, each stays inside the strip and holds all of its own parts, and each name
    keeps about 3 letters"""
    entries = boxes(driver, "#live li")
    strip_box = box(driver, "#live")
    for i, entry in enumerate(entries):
        assert entry["left"] >= strip_box["left"] - 0.5 and entry["right"] <= strip_box["right"] + 0.5, entry
        for other in entries[i + 1 :]:
            assert not overlap(entry, other, gap=0), (entry, other)
    spill = driver.execute_script(
        "return [...document.querySelectorAll('#live li')].map((li) => li.scrollWidth - li.clientWidth)"
    )
    assert max(spill) <= 1, spill
    names = driver.execute_script(
        "return [...document.querySelectorAll('#live .name')].map((n) => n.getBoundingClientRect().width)"
    )
    assert min(names) >= 20, names


@pytest.mark.parametrize(
    "size",
    [
        pytest.param((667, 375, 2, True), id="667x375"),
        pytest.param((736, 414, 3, True), id="736x414"),
        pytest.param((800, 450, 1, False), id="800x450"),
        pytest.param((640, 480, 1, False), id="640x480"),
        pytest.param((800, 600, 1, False), id="800x600"),
    ],
)
def test_the_strip_fits_small_windows(driver, live, size):
    with at_size(driver, *size):
        someone(live, 1001, "Ann", 2400)
        someone(live, 1002, LONG_NAME, 1800)
        someone(live, 1003, "Bob", 950, state="over", away=True)
        someone(live, 1004, "Cleopatra", 3100)
        open_game(driver, live)
        start_mode(driver, "Normal x2")
        wait_idle(live, driver)
        browser.wait_for(driver, "document.querySelectorAll('#live li').length > 0")
        rows = strip(driver)
        shown = [row for row in rows if row[0] != "more"]
        more = [int(row[1][1:]) for row in rows if row[0] == "more"]
        # The player's own place is always shown, and "+N" counts everyone else
        assert shown[-1][2] == "You" and len(shown) + sum(more) == 5
        entries_fit(driver)
        rect = box(driver, "#live")
        assert inside_screen(driver, rect)
        clear_of(driver, rect, [*hud_boxes(driver), board_box(driver), box(driver, "#people .hub-people")])


def test_the_strip_shows_five_and_how_many_more_on_a_desktop(driver, live):
    for i in range(6):
        someone(live, 1001 + i, f"Player {i + 1}", 600 - 100 * i)
    open_game(driver, live)
    start_mode(driver, "Normal")
    browser.wait_for(driver, "document.querySelectorAll('#live li').length === 6")
    rows = strip(driver)
    assert [row[2] for row in rows[:4]] == ["Player 1", "Player 2", "Player 3", "Player 4"]
    assert rows[4] == ["mine", "7", "You", "0"]
    assert rows[5] == ["more", "+2"]


def test_the_players_own_entry_keeps_up_with_their_game(driver, live):
    someone(live, 1001, "Ann", 9999)
    open_game(driver, live)
    start_mode(driver, "Normal")
    wait_idle(live, driver)
    browser.wait_for(driver, "document.querySelectorAll('#live li').length === 2")
    # The bot's copy of the player's score never changes from here, so only the page's own can show the new one
    count_sends(live, deliver=False)
    score_to(live, 1234)
    browser.wait_for(driver, "document.querySelector('#live li.mine .points').textContent === '1,234'")


def test_a_list_that_changes_nothing_shown_leaves_the_strip_alone(driver, live):
    rival = someone(live, 1001, "Ann", 40)
    open_game(driver, live)
    start_mode(driver, "Normal")
    browser.wait_for(driver, "document.querySelectorAll('#live li').length === 2")
    driver.execute_script(
        "window.touched = 0;"
        "new MutationObserver((records) => { window.touched += records.length; })"
        "  .observe(document.getElementById('live'), { childList: true, subtree: true, characterData: true });"
    )
    live.update_person(rival, where="boulderbash", status="Thinking", data={"state": "playing", "score": 40})
    # Lists go out at most 4 times a second
    time.sleep(1)
    assert driver.execute_script("return window.touched") == 0
    live.update_person(rival, where="boulderbash", status="Scored 50", data={"state": "playing", "score": 50})
    browser.wait_for(driver, "document.querySelector('#live li .points').textContent === '50'")


# ---------- Passing notes ----------


def start_watching(driver, live, mode="Normal"):
    open_game(driver, live)
    start_mode(driver, mode)
    wait_idle(live, driver)
    driver.execute_script(RECORD_NOTES)


def arrival_room(driver):
    """Where the hub's arrival notes slide out, under the people button and toward the middle of the screen"""
    button = box(driver, "#people .hub-people")
    middle = driver.execute_script("return innerWidth / 2")
    if button["left"] + button["right"] < 2 * middle:
        return {
            "left": button["left"],
            "right": button["left"] + 300,
            "top": button["bottom"],
            "bottom": button["bottom"] + 36,
        }
    return {
        "left": button["right"] - 300,
        "right": button["right"],
        "top": button["bottom"],
        "bottom": button["bottom"] + 36,
    }


def note_says_all_of(driver, text):
    """The note says this, with nothing cut off, hidden or spilling out of it"""
    said_now, overflow, spill = driver.execute_script(
        "const note = document.getElementById('pass');"
        "return [note.textContent, getComputedStyle(note).overflow,"
        " Math.max(note.scrollWidth - note.clientWidth, note.scrollHeight - note.clientHeight)]"
    )
    assert said_now == text
    assert overflow == "visible" and spill <= 1, (overflow, spill)


# Small windows: a 4:3 one with no room beside the boards, and an old small phone held sideways
SMALL_43 = (640, 480, 1, False)
SMALL_SIDEWAYS = (568, 320, 2, True)


@pytest.mark.parametrize(
    "size",
    [
        *SIZES,
        pytest.param(SQUARE, id="square"),
        pytest.param(SHORT_UPRIGHT, id="short-upright"),
        pytest.param(SMALL_43, id="640x480"),
        pytest.param(SMALL_SIDEWAYS, id="568x320"),
    ],
)
def test_the_passing_note_stays_off_the_boards(driver, live, size):
    with at_size(driver, *size):
        someone(live, 1001, "Ann", 5)
        start_watching(driver, live)
        browser.wait_for(driver, "document.querySelectorAll('#live li').length === 2")
        score_quietly(live, 40)
        browser.wait_for(driver, "window.notes.length > 0")
        # Measured once the note has slid in
        time.sleep(0.4)
        note_says_all_of(driver, "You passed Ann!")
        note = box(driver, "#pass")
        assert inside_screen(driver, note)
        others = [*hud_boxes(driver), board_box(driver), box(driver, "#people .hub-people"), box(driver, "#live")]
        clear_of(driver, note, [*others, arrival_room(driver)])


@pytest.mark.parametrize(
    "size",
    [
        pytest.param(SMALL_43, id="640x480"),
        pytest.param(SMALL_SIDEWAYS, id="568x320"),
        pytest.param((667, 375, 2, True), id="667x375"),
        pytest.param(SQUARE, id="square"),
        pytest.param(DESKTOP, id="desktop"),
    ],
)
def test_long_names_in_the_passing_note_are_never_cut_off(driver, live, size):
    with at_size(driver, *size):
        # The second name is one long word, wider than the narrowest room's width at the smaller size
        someone(live, 1001, LONG_NAME, 5)
        someone(live, 1002, "Bartholomew Smith", 6)
        start_watching(driver, live)
        browser.wait_for(driver, f"{OTHERS_ON_BUTTON} === '2'")
        browser.wait_for(driver, "document.querySelectorAll('#live li').length > 0")
        # A big score leaves the least room beside it
        score_quietly(live, 1234567)
        browser.wait_for(driver, "window.notes.length > 0")
        time.sleep(0.4)
        note_says_all_of(driver, f"You passed {LONG_NAME_CUT} and Bartholomew…!")
        note = box(driver, "#pass")
        assert inside_screen(driver, note)
        others = [*hud_boxes(driver), board_box(driver), box(driver, "#people .hub-people"), box(driver, "#live")]
        clear_of(driver, note, [*others, arrival_room(driver)])


def test_on_an_upright_phone_the_passing_note_stays_above_the_level_popup(driver, live):
    with at_size(driver, *UPRIGHT):
        # Bob makes the strip taller, so the sky left between it and the popup is only just tall enough
        someone(live, 1001, "Ann", 5)
        someone(live, 1002, "Bob", 900)
        start_watching(driver, live)
        browser.wait_for(driver, "document.querySelectorAll('#live li').length === 3")
        score_to(live, 40)
        browser.wait_for(driver, "window.notes.length > 0")
        time.sleep(0.4)
        note = box(driver, "#pass")
        clear_of(driver, note, [box(driver, "#popup"), board_box(driver), box(driver, "#live")])


@pytest.mark.parametrize(
    "size", [pytest.param((360, 640, 2, True), id="360x640"), pytest.param(SHORT_UPRIGHT, id="short-upright")]
)
def test_on_a_short_upright_phone_the_passing_note_waits_for_the_level_popup(driver, live, size):
    with at_size(driver, *size):
        someone(live, 1001, "Ann", 5)
        someone(live, 1002, "Bob", 900)
        start_watching(driver, live)
        browser.wait_for(driver, "document.querySelectorAll('#live li').length === 3")
        score_to(live, 40)
        browser.wait_for(driver, "!document.getElementById('popup').hidden")
        time.sleep(0.5)
        # No room above the popup, so nothing yet
        assert driver.execute_script("return window.notes") == []
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        browser.wait_for(driver, "window.notes.length > 0")
        assert driver.execute_script("return window.notes") == ["You passed Ann!"]
        assert driver.execute_script("return document.getElementById('popup').hidden") is True
        time.sleep(0.4)
        note = box(driver, "#pass")
        assert inside_screen(driver, note)
        clear_of(driver, note, [*hud_boxes(driver), board_box(driver), box(driver, "#people .hub-people")])


def test_a_note_too_big_for_every_spot_still_shows_whole_and_off_the_boards(driver, live):
    with at_size(driver, *SMALL_43):
        names = [LONG_NAME, "Bartholomew Smith", "Maximiliana Rose", "Cleopatra the Great"]
        for i, name in enumerate(names):
            someone(live, 1001 + i, name, 5 + i)
        start_watching(driver, live)
        browser.wait_for(driver, f"{OTHERS_ON_BUTTON} === '4'")
        browser.wait_for(driver, "document.querySelectorAll('#live li').length > 0")
        score_quietly(live, 1234567)
        browser.wait_for(driver, "window.notes.length > 0")
        time.sleep(0.4)
        note_says_all_of(driver, f"You passed {LONG_NAME_CUT}, Bartholomew…, Maximiliana… and Cleopatra t…!")
        note = box(driver, "#pass")
        assert inside_screen(driver, note)
        clear_of(driver, note, [*hud_boxes(driver), board_box(driver), box(driver, "#people .hub-people")])


def test_passes_while_one_popup_is_up_share_the_note_after_it(driver, live):
    with at_size(driver, 360, 640, 2, True):
        someone(live, 1001, "Ann", 5)
        someone(live, 1002, "Bob", 50)
        start_watching(driver, live)
        browser.wait_for(driver, "document.querySelectorAll('#live li').length === 3")
        score_to(live, 40)
        browser.wait_for(driver, "!document.getElementById('popup').hidden")
        # A second pass before the popup closes
        score_quietly(live, 60)
        browser.wait_for(driver, "document.getElementById('score').textContent === '60'")
        time.sleep(0.3)
        assert driver.execute_script("return window.notes") == []
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        browser.wait_for(driver, "window.notes.length > 0")
        assert driver.execute_script("return window.notes") == ["You passed Ann and Bob!"]


def test_passing_someone_shows_a_note(driver, live):
    someone(live, 1001, "Ann", 5)
    start_watching(driver, live)
    browser.wait_for(driver, "document.querySelectorAll('#live li').length === 2")
    score_to(live, 40)
    browser.wait_for(driver, "window.notes.length > 0")
    assert driver.execute_script("return window.notes") == ["You passed Ann!"]
    note = box(driver, "#pass")
    assert driver.execute_script("return getComputedStyle(document.getElementById('pass')).pointerEvents") == "none"
    assert inside_screen(driver, note)
    browser.wait_for(driver, "document.getElementById('pass').hidden", timeout=3)


def test_passes_close_together_share_a_note(driver, live):
    someone(live, 1001, "Ann", 5)
    someone(live, 1002, LONG_NAME, 10)
    someone(live, 1003, "Cleo", 20)
    someone(live, 1004, "Dan", 50)
    start_watching(driver, live)
    browser.wait_for(driver, "document.querySelectorAll('#live li').length === 5")
    score_to(live, 7)
    time.sleep(0.3)
    score_to(live, 30)
    browser.wait_for(driver, "document.getElementById('score').textContent === '30'")
    assert driver.execute_script("return window.notes.at(-1)") == f"You passed Ann, {LONG_NAME_CUT} and Cleo!"
    # A pass more than a second later gets a note of its own
    time.sleep(1.2)
    score_to(live, 60)
    browser.wait_for(driver, "window.notes.at(-1) === 'You passed Dan!'")


def test_a_finished_score_is_passed_and_someone_already_behind_is_not(driver, live):
    start_watching(driver, live)
    score_to(live, 50)
    browser.wait_for(driver, "document.getElementById('score').textContent === '50'")
    someone(live, 1001, "Ann", 20)
    # Anyone in the strip with a score can be passed, as in the hub's own games, whether their game is on or over
    someone(live, 1002, "Bob", 70, state="over")
    browser.wait_for(driver, "document.querySelectorAll('#live li').length === 3")
    score_to(live, 100)
    browser.wait_for(driver, "document.getElementById('score').textContent === '100'")
    browser.wait_for(driver, "window.notes.length > 0")
    time.sleep(0.5)
    assert driver.execute_script("return window.notes") == ["You passed Bob!"]


def test_zen_passes_nobody(driver, live):
    someone(live, 1001, "Ann", 5)
    start_watching(driver, live, "Zen")
    # Ann is seen, though Zen shows no strip to say so
    browser.wait_for(driver, f"{OTHERS_ON_BUTTON} === '1'")
    WebDriverWait(driver, 5).until(said(live, "Playing Zen", True))
    score_to(live, 40)
    browser.wait_for(driver, "document.getElementById('score').textContent === '40'")
    time.sleep(0.5)
    assert driver.execute_script("return window.notes") == []


def test_no_note_after_a_reload(driver, live):
    open_game(driver, live)
    start_mode(driver, "Normal")
    game = smash_a_group(live, driver)
    # Behind the player's score, but ahead of the page's 0 while it loads again
    someone(live, 1001, "Ann", game.score - 1)
    open_game(driver, live)
    browser.wait_for(driver, "document.getElementById('stage').dataset.screen === 'play'", timeout=10)
    browser.wait_for(driver, "document.querySelectorAll('#live li').length === 2")
    time.sleep(0.5)
    assert driver.execute_script("return document.getElementById('pass').textContent") == ""


def test_no_note_after_a_reconnect(driver, live):
    someone(live, 1001, "Ann", 50)
    start_watching(driver, live)
    browser.wait_for(driver, "document.querySelectorAll('#live li').length === 2")
    # After a dropped connection the bot greets the page again with the game as it is now: a score past Ann's here,
    # from moves the page never saw
    game = live.cog.games[KEY]

    async def greet_again():
        snapshot = game.snapshot(live.cog.clock())
        snapshot["score"] = 80
        await live.cog.conns[KEY].send({"hello": {"game": snapshot, "result": None}})

    run(live, greet_again())
    browser.wait_for(driver, "document.getElementById('score').textContent === '80'")
    time.sleep(0.5)
    assert driver.execute_script("return window.notes") == []
