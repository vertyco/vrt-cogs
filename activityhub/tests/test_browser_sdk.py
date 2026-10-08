import pytest
from selenium.webdriver.common.by import By

from activityhub.tests.browser import (
    DISCORD_QUERY,
    TEST_HOST_PAGE,
    LiveHub,
    fresh,
    hub_web_copy,
    start_chrome,
    wait_for,
)
from activityhub.tests.fakes import GUILD_ID, MEMBER_ID, DemoCog, make_hub, register, write_demo_web


@pytest.fixture(scope="module")
def driver():
    chrome = start_chrome()
    if chrome is None:
        pytest.skip("Chrome can't start on this machine")
    yield chrome
    chrome.quit()


@pytest.fixture
def live(tmp_path, driver):
    hub = make_hub()
    register(hub, DemoCog(write_demo_web(tmp_path / "demo")))
    server = LiveHub(hub, hub_web_copy(tmp_path, index=TEST_HOST_PAGE))
    server.start()
    fresh(driver, server)
    yield server
    server.stop()


def open_host(driver, live, query=DISCORD_QUERY):
    driver.get(f"{live.url}/{query}")
    return wait_for(driver, "document.body.dataset.login")


def open_game_in_host(driver, live):
    assert open_host(driver, live) == "online"
    driver.execute_script("window.testHost.openGame('demo')")
    wait_for(driver, "document.body.classList.contains('playing')")
    driver.switch_to.frame(driver.find_element(By.ID, "game-frame"))
    wait_for(driver, "window.demo && window.demo.done")


def test_game_opened_directly_in_a_browser_is_offline(driver, live):
    driver.get(f"{live.url}/games/demo/")
    wait_for(driver, "window.demo && window.demo.done")
    assert driver.execute_script("return [window.demo.offline, window.demo.player]") == [True, None]
    driver.find_element(By.ID, "back").click()
    wait_for(driver, "location.pathname === '/'")


def test_host_logs_in_once(driver, live):
    assert open_host(driver, live) == "online"
    calls = driver.execute_script("return window.fakeDiscord")
    assert calls == {"created": 1, "authorize": 1, "authenticate": 1}
    player = driver.execute_script("return window.testHost.login.player")
    assert player["id"] == str(MEMBER_ID) and player["guildId"] == str(GUILD_ID)


def test_host_outside_discord_is_offline(driver, live):
    assert open_host(driver, live, query="") == "offline"
    assert driver.execute_script("return window.fakeDiscord === undefined")


def test_game_in_the_frame_borrows_the_login(driver, live):
    open_game_in_host(driver, live)
    demo = driver.execute_script("return window.demo")
    assert demo["offline"] is False and demo.get("error") is None
    assert demo["player"]["guildId"] == str(GUILD_ID)
    assert demo["echo"] == {"user": MEMBER_ID, "guild": GUILD_ID, "instance": "i-1", "data": {"n": 1}}
    wait_for(driver, "window.demo.messages.length >= 2")
    messages = driver.execute_script("return window.demo.messages")
    assert messages[0] == {"joined": MEMBER_ID, "peers": 0}
    assert messages[1] == {"echo": {"ping": 1}}
    assert driver.execute_script("return window.fakeDiscord === undefined")
    assert driver.execute_script("return window.parent.fakeDiscord.created") == 1


def test_back_to_menu_closes_the_game_frame(driver, live):
    open_game_in_host(driver, live)
    driver.find_element(By.ID, "back").click()
    driver.switch_to.default_content()
    wait_for(driver, "document.body.dataset.closed === '1'")
    assert driver.find_elements(By.ID, "game-frame") == []
    assert driver.execute_script("return document.body.classList.contains('playing')") is False


def test_a_missing_page_in_the_frame_leads_back_to_the_menu(driver, live):
    # A router path is gone after a reload, and a bare 404 would leave the player stuck in the frame
    open_game_in_host(driver, live)
    driver.execute_script("setTimeout(() => { history.pushState({}, '', 'play'); location.reload(); }, 0)")
    wait_for(driver, "document.body.innerText.includes('part of the game.')")
    driver.find_element(By.ID, "back").click()
    driver.switch_to.default_content()
    wait_for(driver, "document.body.dataset.closed === '1'")
    assert driver.find_elements(By.ID, "game-frame") == []


def test_game_page_alone_in_discord_goes_to_the_menu(driver, live):
    driver.get(f"{live.url}/games/demo/{DISCORD_QUERY}")
    wait_for(driver, "location.pathname === '/' && document.body.dataset.login === 'online'")
    assert driver.execute_script("return location.search") == DISCORD_QUERY
    assert driver.execute_script("return window.fakeDiscord.created") == 1


def test_expired_session_is_handed_to_the_host(driver, live):
    assert open_host(driver, live) == "online"
    live.hub.sessions.sessions.clear()
    driver.execute_script("window.testHost.openGame('demo')")
    wait_for(driver, "document.body.dataset.expired === '1'")
    assert driver.find_elements(By.ID, "game-frame") == []
