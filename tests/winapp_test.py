
import unittest
from appium import webdriver

desired_caps = {}
desired_caps["app"] = "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
desired_caps["platformName"] = "Windows"
desired_caps["deviceName"] = "WindowsPC"
driver = webdriver.Remote("http://127.0.0.1:4723/", desired_caps)