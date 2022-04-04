import xmltojson
import xmltodict
import json
import xml.etree.ElementTree as ET
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.chrome.options import Options

chrome_options = Options()
chrome_options.add_argument("--headless")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

driver.get("https://halotracker.com")
print(driver.title)

gamertag = "whatupgmane"
# search = driver.find_element(By.CSS_SELECTOR, "[aria-label=Enter Xbox Live Username]")
search = WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.XPATH, "//*[@aria-label='Enter Xbox Live Username']")))
search.send_keys(gamertag)
search.send_keys(Keys.RETURN)

# print("looking for pfp")
# pfp = WebDriverWait(driver, 10).until(EC.visibility_of_all_elements_located((By.XPATH, "//div[@class='ph-avatar']/img")))
# for image in pfp:
#     alt = image.get_attribute("alt")
#     print(alt)
#     if gamertag in str(alt):
#         print(image.get_attribute("src"))

# print(pfp.text)
# modes
# modes = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "multi-switch__items")))
# overall = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Overall')]")))
# driver.execute_script("arguments[0].click();", overall)
# time.sleep(3)
# WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "multi-switch__items"))).click()



main_stats = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "giant-stats"))).text
# print(main_stats)
stats = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "main"))).text
# print(stats)

shots = WebDriverWait(driver, 10).until(EC.visibility_of_all_elements_located((By.CLASS_NAME, "percentage-stat__details")))
for shot in shots:
    print(shot.text)
hs = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "percentage-stat"))).text
print(hs)
# kd = driver.find_element(By.NAME, "K/D Ratio")
# print(kd)
time.sleep(10)


