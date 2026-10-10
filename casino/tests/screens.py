"""Screenshots of the casino for checking art by eye. Not collected with the tests; run it by name:

    pytest casino/tests/screens.py -k war

It saves the lobby and each game's table (waiting, mid-round, and with its result) at desktop, upright phone
and sideways phone sizes, to the folder in the CASINO_SHOTS environment variable (default: ./casino-shots)
"""

import os
from pathlib import Path

import pytest
from selenium.webdriver.common.by import By

from casino.common.catalog import GAMES
from casino.tests import test_browser
from casino.tests.test_browser import QUICK_MOVE, browser, open_casino, walk_up

driver = test_browser.driver
live = test_browser.live
SIZES = {"desktop": (1280, 800, 1, False), "phone": (390, 844, 2, True), "sideways": (844, 390, 2, True)}


def folder() -> Path:
    path = Path(os.environ.get("CASINO_SHOTS", "casino-shots"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def shoot(chrome, name: str) -> None:
    chrome.switch_to.default_content()
    chrome.save_screenshot(str(folder() / f"{name}.png"))
    chrome.switch_to.frame(chrome.find_element(By.ID, "game-frame"))


def pause(chrome, ms: int) -> None:
    chrome.execute_script(f"return new Promise((resolve) => setTimeout(resolve, {ms}))")


def play_to_result(chrome, game: str, name: str) -> None:
    if game == "blackjack":
        chrome.find_element(By.ID, "sit").click()
        browser.wait_for(chrome, "!document.getElementById('stand').hidden")
    choices = chrome.find_elements(By.CSS_SELECTOR, "#choices button")
    if choices:
        choices[0].click()
    browser.wait_for(chrome, "!document.getElementById('place').disabled && !document.getElementById('place').hidden")
    shoot(chrome, f"{name}-1-waiting")
    chrome.find_element(By.ID, "place").click()
    pause(chrome, 700)
    shoot(chrome, f"{name}-2-playing")
    for _ in range(120):
        if chrome.execute_script("return !document.getElementById('result').hidden"):
            break
        move = QUICK_MOVE.get(game)
        buttons = chrome.find_elements(By.CSS_SELECTOR, f'#moves [data-move="{move}"]') if move else []
        if buttons and buttons[0].is_displayed():
            buttons[0].click()
        pause(chrome, 250)
    shoot(chrome, f"{name}-3-result")


@pytest.mark.parametrize("size", list(SIZES))
@pytest.mark.parametrize("game", ["lobby", *GAMES])
def test_screens(driver, live, game, size):  # noqa: F811
    width, height, scale, mobile = SIZES[size]
    metrics = {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": mobile}
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", metrics)
    try:
        open_casino(driver, live)
        if game == "lobby":
            pause(driver, 800)
            shoot(driver, f"lobby-{size}")
            return
        walk_up(driver, game)
        play_to_result(driver, game, f"{game}-{size}")
    finally:
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
