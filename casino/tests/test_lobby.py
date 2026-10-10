"""The lobby at every screen size: a tap on any table, or on its medallion, reaches that table and no other"""

import pytest

from casino.common.catalog import GAMES
from casino.tests import test_browser
from casino.tests.test_browser import open_casino, problems

driver = test_browser.driver
live = test_browser.live
SIZES = {"desktop": (1280, 800, 1, False), "phone": (390, 844, 2, True), "sideways": (844, 390, 2, True)}

# For each table: bring it into view, then ask what a tap at the middle of its table top and at the middle of its
# medallion would land on
WHAT_A_TAP_HITS = """
const key = arguments[0];
const station = document.querySelector(`.station[data-key="${key}"]`);
station.scrollIntoView({ block: "center", inline: "center" });
function hit(node) {
  const box = node.getBoundingClientRect();
  const x = box.left + box.width / 2;
  const y = box.top + box.height / 2;
  const inside = x >= 0 && y >= 0 && x < innerWidth && y < innerHeight;
  const found = document.elementFromPoint(x, y);
  return { inside, key: found && found.closest(".station") ? found.closest(".station").dataset.key : null };
}
return { table: hit(station), medallion: hit(station.querySelector(".medallion")) };
"""


@pytest.mark.parametrize("size", list(SIZES))
def test_every_table_and_medallion_takes_its_own_taps(driver, live, size):  # noqa: F811
    width, height, scale, mobile = SIZES[size]
    metrics = {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": mobile}
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", metrics)
    try:
        open_casino(driver, live)
        for game in GAMES:
            taps = driver.execute_script(WHAT_A_TAP_HITS, game)
            for part, tap in taps.items():
                assert tap["inside"], f"{size}: {game}'s {part} can't be scrolled into view"
                assert tap["key"] == game, f"{size}: a tap on {game}'s {part} lands on {tap['key']}"
        assert problems(driver) == []
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
