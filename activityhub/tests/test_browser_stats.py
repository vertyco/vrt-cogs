import asyncio
import time

import pytest
from piccolo.engine.sqlite import SQLiteEngine
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select

from activityhub.db.tables import TABLES, Play
from activityhub.tests.browser import DISCORD_QUERY, LiveHub, fresh, hub_web_copy, start_chrome, wait_for
from activityhub.tests.fakes import GUILD_ID, MANAGER_ID, OWNER_ID, DemoCog, make_hub, register, write_demo_web

ROWS = "return [...document.querySelectorAll('.stats-table tbody tr')].map((row) => [...row.cells].map((c) => c.textContent))"
HOUR_TOTAL = (
    "return [...document.querySelectorAll('.stats-chart')[1].querySelectorAll('.stats-bar')]"
    ".reduce((sum, bar) => sum + Number(bar.dataset.plays), 0)"
)
PHONE = {"width": 375, "height": 740, "deviceScaleFactor": 1, "mobile": True}
# Two quick choices whose answers arrive out of order: the second choice's answer first
LATE_ANSWER = r"""
const done = arguments[0];
import('./stats.js').then(async ({ StatsPanel }) => {
  const asked = [];
  const panel = new StatsPanel((query) => new Promise((resolve) => asked.push(resolve)), () => {});
  const data = (plays) => ({
    server: '500', servers: null, overall: { plays, players: 1, phone: null },
    games: [{ key: 'demo', name: 'Demo', plays, players: 1, typical: 5, phone: null }],
    bars: { kind: 'day', starts: ['2026-10-16'] },
    charts: { '': { bars: [plays], hours: Array(24).fill(0) } },
  });
  panel.days = 30;
  panel.refresh();
  asked[1](data(30));
  await new Promise((resolve) => setTimeout(resolve));
  asked[0](data(7));
  await new Promise((resolve) => setTimeout(resolve));
  done(panel.root.querySelector('.stats-overall').textContent);
});
"""


@pytest.fixture(scope="module")
def driver():
    chrome = start_chrome()
    if chrome is None:
        pytest.skip("Chrome can't start on this machine")
    chrome.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
    yield chrome
    chrome.quit()


def fill(live, rows):
    """Make the tables and write the rows on the server's own loop, where the database is used"""

    async def write():
        for table in TABLES:
            await table.create_table(if_not_exists=True)
        if rows:
            await Play.insert(*[Play(**row) for row in rows])
        live.hub.playlog.opened()

    asyncio.run_coroutine_threadsafe(write(), live.loop).result(10)


def sample_rows():
    now = time.time()
    return [
        dict(guild_id=GUILD_ID, user_id=2, game="demo", platform="mobile", started_at=now - 3600, seconds=120),
        dict(guild_id=GUILD_ID, user_id=3, game="demo", platform="desktop", started_at=now - 90000, seconds=60),
        dict(guild_id=GUILD_ID, user_id=2, game="second", platform="mobile", started_at=now - 7200, seconds=30),
        dict(guild_id=600, user_id=4, game="demo", platform="mobile", started_at=now - 600, seconds=10),
    ]


def make_live(tmp_path, driver, rows):
    hub = make_hub()
    hub.config.globals["look"] = {"theme": "standard"}
    register(hub, DemoCog(write_demo_web(tmp_path / "demo")))
    register(hub, DemoCog(write_demo_web(tmp_path / "second"), key="second", name="Alpha Game", cog_name="Second"))
    db = SQLiteEngine(path=str(tmp_path / "play.sqlite"))
    for table in TABLES:
        table._meta.db = db
    server = LiveHub(hub, hub_web_copy(tmp_path))
    server.start()
    fill(server, rows)
    driver.set_window_size(1280, 800)
    fresh(driver, server)
    return server


@pytest.fixture
def live(tmp_path, driver):
    server = make_live(tmp_path, driver, sample_rows())
    yield server
    server.stop()


@pytest.fixture
def empty(tmp_path, driver):
    server = make_live(tmp_path, driver, [])
    yield server
    server.stop()


def open_stats(driver, live, user_id, ready=".stats-table"):
    live.user_id = user_id
    driver.get(f"{live.url}/{DISCORD_QUERY}")
    wait_for(driver, "document.querySelectorAll('#games .card').length > 0")
    driver.find_element(By.ID, "gear").click()
    wait_for(driver, "getComputedStyle(document.getElementById('panel')).transform === 'none'")
    driver.find_element(By.CSS_SELECTOR, '#tabs .tab[data-tab="stats"]').click()
    wait_for(driver, f"document.querySelector('{ready}')")


def test_an_admin_sees_their_server_without_a_picker(driver, live):
    open_stats(driver, live, MANAGER_ID)
    assert driver.execute_script(ROWS) == [
        ["Demo", "2", "2", "1m 00s", "50%"],
        ["Alpha Game", "1", "1", "30s", "100%"],
    ]
    assert driver.find_element(By.CSS_SELECTOR, ".stats-overall").text == "3 plays · 2 players · 67% on phones"
    assert not driver.find_elements(By.ID, "stats-server")
    assert not driver.find_element(By.ID, "save").is_displayed()
    assert not driver.find_element(By.ID, "reset").is_displayed()
    assert len(driver.find_elements(By.CSS_SELECTOR, ".stats-chart:first-of-type .stats-bar")) == 7


def test_the_chart_picker_switches_both_charts(driver, live):
    open_stats(driver, live, MANAGER_ID)
    assert driver.execute_script(HOUR_TOTAL) == 3
    Select(driver.find_element(By.ID, "stats-game")).select_by_value("second")
    assert driver.execute_script(HOUR_TOTAL) == 1
    driver.find_element(By.CSS_SELECTOR, '.stats-chart .stats-bar[data-plays="1"]').click()
    assert driver.find_element(By.CSS_SELECTOR, ".stats-chart .stats-tip").text.endswith(": 1 play")


def test_the_owner_picks_a_server(driver, live):
    open_stats(driver, live, OWNER_ID)
    picker = Select(driver.find_element(By.ID, "stats-server"))
    assert picker.first_selected_option.get_attribute("value") == str(GUILD_ID)
    assert [option.text for option in picker.options] == ["All servers", "Test Server", "600"]
    picker.select_by_value("all")
    wait_for(driver, "document.querySelector('.stats-overall')?.textContent.startsWith('4 plays')")
    assert Select(driver.find_element(By.ID, "stats-server")).first_selected_option.get_attribute("value") == "all"


def test_the_orb_theme_shows_the_stats_tab(driver, live):
    # The Orb is the menu's default theme, with Settings as its last pill in place of the gear
    live.hub.config.globals["look"] = {"theme": "orb"}
    live.user_id = MANAGER_ID
    driver.get(f"{live.url}/{DISCORD_QUERY}")
    wait_for(driver, "document.querySelectorAll('#games .pill').length > 0")
    driver.find_element(By.CSS_SELECTOR, "#games .settings-pill").click()
    wait_for(driver, "getComputedStyle(document.getElementById('panel')).transform === 'none'")
    driver.find_element(By.CSS_SELECTOR, '#tabs .tab[data-tab="stats"]').click()
    wait_for(driver, "document.querySelector('.stats-table')")
    assert driver.execute_script("return document.body.dataset.theme") == "orb"
    assert len(driver.execute_script(ROWS)) == 2
    assert not driver.find_element(By.ID, "save").is_displayed()


def test_no_plays_says_so(driver, empty):
    open_stats(driver, empty, MANAGER_ID, ready=".stats-note.stats-empty")
    assert driver.find_element(By.CSS_SELECTOR, ".stats-empty").text == "No plays in this period yet."
    assert not driver.find_elements(By.CSS_SELECTOR, ".stats-chart")


def test_the_stats_tab_fits_a_phone(driver, live):
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", PHONE)
    try:
        open_stats(driver, live, OWNER_ID)
        assert driver.execute_script(
            "const b = document.getElementById('tab-body'); return b.scrollWidth <= b.clientWidth"
        )
        assert driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth")
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})


def test_a_late_answer_to_an_earlier_choice_is_ignored(driver, live):
    driver.get(f"{live.url}/{DISCORD_QUERY}")
    wait_for(driver, "document.querySelectorAll('#games .card').length > 0")
    assert driver.execute_async_script(LATE_ANSWER).startswith("30 plays")
