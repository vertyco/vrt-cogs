"""The art kit: every shared piece draws, every animation finishes within the time it's given, and the art stays
within its size budget"""

from pathlib import Path

import pytest
from PIL import Image

from vegas.common.catalog import GAMES
from vegas.tests import test_browser
from vegas.tests.test_browser import open_casino, problems

driver = test_browser.driver
live = test_browser.live
WEB = Path(__file__).resolve().parents[1] / "web"
MB = 1024 * 1024
SLACK_MS = 120

# Runs inside the casino's page: loads the kit, makes one of everything, and times each animation
CHECK = """
const done = arguments[arguments.length - 1];
(async () => {
  const pixi = await import(new URL("vendor/pixi.min.mjs", document.baseURI).href);
  const art = await import(new URL("scenes/art.js", document.baseURI).href);
  const app = new pixi.Application();
  await app.init({ width: 900, height: 600, backgroundAlpha: 0 });
  await art.loadArt();
  const root = new pixi.Container();
  app.stage.addChild(root);
  const timings = {};
  async function timed(name, ms, run) {
    const start = performance.now();
    await run();
    timings[name] = [performance.now() - start, ms];
  }
  const card = art.cardSprite(null);
  root.addChild(card);
  art.showCard(card, ["10", "hearts"]);
  await timed("dealCard", 400, () => art.dealCard(card, { x: 450, y: 40 }, { x: 300, y: 300 }, 400));
  await timed("flipCard", 500, () => art.flipCard(card, ["A", "spades"], 500));
  await timed("flipCard back", 500, () => art.flipCard(card, null, 500));
  const chips = art.DENOMINATIONS.map((value) => art.chipSprite(value));
  chips.forEach((chip) => root.addChild(chip));
  const stack = art.chipStack(1234);
  root.addChild(stack);
  await timed("moveChips", 400, () => art.moveChips(stack, { x: 600, y: 500 }, 400));
  const dice = [art.dieSprite(1), art.dieSprite(6)];
  dice.forEach((die) => root.addChild(die));
  await timed("rollDice", 1600, () => art.rollDice(dice, [3, 4], { x: 100, y: 500 }, { x: 600, y: 250 }, 1600));
  const coin = art.coinSprite("heads");
  root.addChild(coin);
  await timed("flipCoin", 1600, () => art.flipCoin(coin, "tails", 1600));
  await timed("sparkle", 800, () => art.sparkle(root, 450, 300, 800));
  const sizes = {
    card: [card.width, card.height],
    chip: [chips[0].width, chips[0].height],
    die: [dice[0].width, dice[0].height],
    coin: [coin.width, coin.height],
  };
  app.destroy(true, { children: true });
  done({ timings, sizes, card: art.CARD });
})().catch((e) => done({ error: String((e && e.stack) || e) }));
"""


def folder_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def test_the_kit_draws_everything_and_keeps_time(driver, live):  # noqa: F811
    open_casino(driver, live)
    driver.set_script_timeout(30)
    report = driver.execute_async_script(CHECK)
    assert "error" not in report, report.get("error")
    for name, (took, allowed) in report["timings"].items():
        assert took <= allowed + SLACK_MS, f"{name} took {took:.0f} ms of its {allowed}"
    card_width, card_height = report["sizes"]["card"]
    assert abs(card_width - report["card"]["width"]) < 2 and abs(card_height - report["card"]["height"]) < 2
    for name, (width, height) in report["sizes"].items():
        assert width > 20 and height > 20, f"{name} is {width}x{height}"
    assert problems(driver) == []


def test_the_art_stays_within_its_budget():
    art = WEB / "art"
    for path in art.rglob("*"):
        if path.is_file():
            assert path.suffix in (".png", ".jpg"), f"{path.name}: only PNG and JPEG (the hub has no WebP type)"
    assert folder_size(art / "kit") <= 2 * MB
    for game in GAMES:
        if (art / game).is_dir():
            assert folder_size(art / game) <= 1 * MB, f"{game}'s art is over 1 MB"
    assert folder_size(WEB) <= 20 * MB


def test_card_pictures_have_their_sizes_and_budget():
    cards = WEB / "art" / "cards"
    found = {path.stem: Image.open(path).size for path in cards.glob("*.jpg")}
    assert found.pop("holdem") == (1200, 500)
    assert set(found) == {"blackjack", "craps", "slots", "allin", "war", "hilo", "double", "coin", "cups", "dice"}
    assert set(found.values()) == {(480, 320)}
    assert (cards / "holdem.jpg").stat().st_size <= 160 * 1024
    assert all((cards / f"{key}.jpg").stat().st_size <= 70 * 1024 for key in found)
    assert folder_size(cards) <= 1 * MB
    assert Image.open(WEB / "thumb.jpg").size == (640, 360) and (WEB / "thumb.jpg").stat().st_size <= 100 * 1024


def test_slots_and_wheel_pictures_have_their_sizes_and_budget():
    slots, allin = WEB / "art" / "slots", WEB / "art" / "allin"
    pictures = {"seven": slots / "seven.png", "blank": slots / "blank.png"}
    pictures |= {"hall": allin / "hall.jpg", "stand": allin / "stand.png"}
    found = {name: Image.open(path).size for name, path in pictures.items()}
    # The blank stop is drawn smaller than the other symbols, so its picture is half their size
    assert found == {"seven": (205, 220), "blank": (103, 110), "hall": (1200, 800), "stand": (640, 456)}
    budgets = {"seven": 60, "blank": 16, "hall": 240, "stand": 50}
    for name, path in pictures.items():
        assert path.stat().st_size <= budgets[name] * 1024, f"{name} is over {budgets[name]} KB"
    assert folder_size(slots) <= 600 * 1024


@pytest.mark.parametrize("game", GAMES)
def test_each_finished_scene_uses_the_kit_not_the_stand_in(game):
    scene = (WEB / "scenes" / f"{game}.js").read_text(encoding="utf-8")
    if "plain.js" in scene:
        pytest.skip(f"{game}'s art task hasn't run yet")
    assert "export async function createScene" in scene
