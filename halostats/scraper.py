import logging

import discord
from redbot.core.utils.chat_formatting import box
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tabulate import tabulate
from webdriver_manager.chrome import ChromeDriverManager

log = logging.getLogger("red.vrt.halostats.scraper")

MODES = ["Overall", "Ranked Arena", "Tactical Slayer", "Team Slayer", "Quick Play", "Big Team Battle"]


def get_profile_data(gamertag: str) -> list:
    embeds = []
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    driver.get("https://halotracker.com")
    search = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located(
            (By.XPATH, "//*[@aria-label='Enter Xbox Live Username']")
        )
    )
    search.send_keys(gamertag)
    search.send_keys(Keys.RETURN)
    # GET PFP IMAGE
    images = WebDriverWait(driver, 10).until(
        EC.visibility_of_all_elements_located(
            (By.XPATH, "//div[@class='ph-avatar']/img")
        )
    )
    pfp = None
    for img in images:
        alt = str(img.get_attribute("alt"))
        if gamertag.lower() in alt.lower():
            pfp = str(img.get_attribute("src"))
            break

    # GET STATS FOR EACH GAME MODE
    for mode_name in MODES:
        page_num = MODES.index(mode_name)
        try:
            mode = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable(
                    (By.XPATH, f"//span[contains(text(), '{mode_name}')]")
                )
            )
        except Exception as e:
            log.warning(f"Scraper failed to change modes for {gamertag}. Error: {e}")
            driver.quit()
            return embeds
        driver.execute_script("arguments[0].click();", mode)
        # GET MAIN STATS
        main_stats = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located(
                (By.CLASS_NAME, "giant-stats")
            )
        ).text
        main_stats = main_stats.split("\n")
        main_stats = tabulate_stats(main_stats)

        # GET SECONDARY STATS
        secondary_stats = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located(
                (By.CLASS_NAME, "main")
            )
        ).text
        secondary_stats = secondary_stats.split("\n")
        secondary_stats = tabulate_stats(secondary_stats)

        # GET ACCURACY
        accuracy = WebDriverWait(driver, 10).until(
            EC.visibility_of_all_elements_located(
                (By.CLASS_NAME, "percentage-stat__details")
            )
        )
        shot_accuracy = accuracy[0].text
        headshot_accuracy = accuracy[1].text

        embed = discord.Embed(
            title=f"{gamertag}'s Halo Infinite Stats",
            description=f"**{mode_name.upper()}**\n"
                        f"{main_stats}\n",
            color=discord.Color.random()
        )
        if pfp:
            embed.set_thumbnail(url=pfp)
        embed.add_field(name="Details", value=secondary_stats, inline=False)
        if shot_accuracy:
            embed.add_field(name="Shot Accuracy", value=box(shot_accuracy, lang='python'), inline=False)
        if headshot_accuracy:
            embed.add_field(name="Headshot Accuracy", value=box(headshot_accuracy, lang='python'), inline=False)
        embed.set_footer(text=f"Pages {page_num + 1}/{len(MODES)}")
        embeds.append(embed)
    driver.quit()
    return embeds


# Returns a box of tabulated stats
def tabulate_stats(stats: list) -> str:
    left = []
    right = []
    num = 1
    for stat in stats:
        if num == 1:
            left.append(stat)
            num = 2
        else:
            right.append(stat)
            num = 1
    table = list(zip(left, right))
    tabulated = tabulate(table, tablefmt="presto")
    return box(tabulated, lang='python')
