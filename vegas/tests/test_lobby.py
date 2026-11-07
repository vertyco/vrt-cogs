"""The menu at every screen size: a tap anywhere on a card reaches that game and no other, the cards sit 2 or 5
across, and every name is readable and stays inside its card"""

import pytest

from vegas.common.catalog import GAME_NAMES, GAMES
from vegas.tests import test_browser
from vegas.tests.test_browser import at_size, open_casino, problems

driver = test_browser.driver
live = test_browser.live
SIZES = {"desktop": (1280, 800, 1, False), "phone": (390, 844, 2, True), "sideways": (844, 390, 2, True)}
# How many rows the small cards make: 2 across on an upright phone, 5 across otherwise
ROWS = {"desktop": 2, "phone": 5, "sideways": 2}

# For each card: bring it to the middle of the menu, then ask what a tap at the middle of its picture and at the
# middle of its band would land on
WHAT_A_TAP_HITS = """
const card = document.querySelector(`.game-card[data-key="${arguments[0]}"]`);
card.scrollIntoView({ block: "center" });
function hit(node) {
  const box = node.getBoundingClientRect();
  const x = box.left + box.width / 2;
  const y = box.top + box.height / 2;
  const inside = x >= 0 && y >= 0 && x < innerWidth && y < innerHeight;
  const found = document.elementFromPoint(x, y);
  return { inside, key: found?.closest(".game-card")?.dataset.key ?? null };
}
return { picture: hit(card.querySelector(".card-art")), band: hit(card.querySelector(".label")) };
"""

# Where the cards sit, from their layout boxes, so a card lifted under the mouse doesn't count as a row of its own
GRID = """
const menu = document.getElementById("menu");
const style = getComputedStyle(menu);
const small = [...menu.querySelectorAll(".game-card:not(.banner)")];
return {
  rows: new Set(small.map((card) => Math.round(card.offsetTop))).size,
  banner: menu.querySelector(".game-card.banner").offsetWidth,
  grid: menu.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
};
"""

NAMES = """
const box = (node) => node.getBoundingClientRect();
const inside = (a, b) =>
  a.left >= b.left - 0.5 && a.right <= b.right + 0.5 && a.top >= b.top - 0.5 && a.bottom <= b.bottom + 0.5;
const lobby = document.getElementById("lobby");
return {
  cards: [...document.querySelectorAll("#menu .game-card")].map((card) => {
    const label = card.querySelector(".label");
    const name = label.firstElementChild;
    return {
      key: card.dataset.key,
      size: parseFloat(getComputedStyle(label).fontSize),
      inside: inside(box(label), box(card)),
      whole: Boolean(name && name.textContent) && name.scrollWidth <= name.clientWidth,
    };
  }),
  sideways: document.documentElement.scrollWidth > innerWidth || lobby.scrollWidth > lobby.clientWidth,
};
"""


# A menu of its own, drawn the way the page first draws it, before the casino's facts arrive: what each card's
# button is called
UNNAMED_MENU = """
const done = arguments[arguments.length - 1];
import(new URL("lobby.js", document.baseURI).href).then(({ Lobby }) => {
  const box = document.createElement("div");
  box.innerHTML = '<main><div></div></main><div class="lobby-foot"><div class="lobby-crowd" hidden></div></div>';
  document.body.append(box);
  const lobby = new Lobby(box.firstElementChild, box.querySelector("main > div"), () => {});
  lobby.render(null, null);
  const cards = [...box.querySelectorAll(".game-card")];
  box.remove();
  done(Object.fromEntries(cards.map((card) => [card.dataset.key, card.getAttribute("aria-label")])));
}).catch((e) => done(String(e)));
"""


def test_a_card_says_its_game_before_the_casino_arrives(driver, live):  # noqa: F811
    open_casino(driver, live)
    assert driver.execute_async_script(UNNAMED_MENU) == GAME_NAMES
    assert problems(driver) == []


@pytest.mark.parametrize("size", list(SIZES))
def test_every_card_takes_its_own_taps(driver, live, size):  # noqa: F811
    with at_size(driver, *SIZES[size]):
        open_casino(driver, live)
        for game in GAMES:
            taps = driver.execute_script(WHAT_A_TAP_HITS, game)
            for part, tap in taps.items():
                assert tap["inside"], f"{size}: {game}'s {part} can't be brought into view"
                assert tap["key"] == game, f"{size}: a tap on {game}'s {part} lands on {tap['key']}"
        assert problems(driver) == []


@pytest.mark.parametrize("size", list(SIZES))
def test_the_cards_sit_2_across_upright_and_5_across_otherwise(driver, live, size):  # noqa: F811
    with at_size(driver, *SIZES[size]):
        open_casino(driver, live)
        found = driver.execute_script(GRID)
        assert found["rows"] == ROWS[size], found
        assert abs(found["banner"] - found["grid"]) <= 2, found
        assert problems(driver) == []


@pytest.mark.parametrize("size", list(SIZES))
def test_card_names_are_readable_and_inside_their_card(driver, live, size):  # noqa: F811
    with at_size(driver, *SIZES[size]):
        open_casino(driver, live)
        found = driver.execute_script(NAMES)
        assert sorted(card["key"] for card in found["cards"]) == sorted(GAMES)
        for card in found["cards"]:
            assert card["size"] >= 10, f"{size}: {card['key']}'s name is {card['size']} px"
            assert card["inside"], f"{size}: {card['key']}'s name leaves its card"
            assert card["whole"], f"{size}: {card['key']}'s name is cut"
        assert not found["sideways"]
        assert problems(driver) == []


# The Slots pot's box against its card's picture, its dark band and the name in the band, and the first row of small
# cards' bands against the part of the menu on screen without scrolling
POT_AND_FIRST_ROW = """
const box = (node) => node.getBoundingClientRect();
const card = document.querySelector('.game-card[data-key="slots"]');
const pot = box(card.querySelector(".jackpot"));
const art = box(card.querySelector(".card-art"));
const band = box(card.querySelector(".label"));
const name = box(card.querySelector(".label").firstElementChild);
const lobby = box(document.getElementById("lobby"));
const first = [...document.querySelectorAll("#menu .game-card:not(.banner) .label")].slice(0, 5).map(box);
return {
  pot: [pot.left, pot.top, pot.right, pot.bottom],
  art: [art.left, art.top, art.right, art.bottom],
  band: [band.left, band.top, band.right, band.bottom],
  name: [name.left, name.top, name.right, name.bottom],
  banner: box(document.querySelector(".game-card.banner")).height,
  lowest: Math.max(...first.map((row) => row.bottom)),
  shown: lobby.bottom,
};
"""


def inside(a, b):
    return a[0] >= b[0] - 0.5 and a[1] >= b[1] - 0.5 and a[2] <= b[2] + 0.5 and a[3] <= b[3] + 0.5


def apart(a, b):
    return a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3]


@pytest.mark.parametrize("size", list(SIZES))
def test_the_slots_pot_sits_in_its_cards_dark_band(driver, live, size):  # noqa: F811
    with at_size(driver, *SIZES[size]):
        open_casino(driver, live)
        browser_wait = test_browser.browser.wait_for
        browser_wait(driver, "document.querySelector('.game-card[data-key=\"slots\"] .jackpot')?.textContent")
        found = driver.execute_script(POT_AND_FIRST_ROW)
        assert inside(found["pot"], found["band"]), found
        assert apart(found["pot"], found["art"]) and apart(found["pot"], found["name"]), found
        assert problems(driver) == []


def test_a_short_screen_shows_the_first_row_of_names_without_scrolling(driver, live):  # noqa: F811
    with at_size(driver, *SIZES["sideways"]):
        open_casino(driver, live)
        found = driver.execute_script(POT_AND_FIRST_ROW)
        assert found["banner"] <= 112, found
        assert found["lowest"] <= found["shown"], found
        assert problems(driver) == []
