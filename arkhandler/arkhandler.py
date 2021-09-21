import psutil
import os
import asyncio
import win32gui
import win32api
import win32con
import win32evtlog
import datetime
import requests
import configparser
import colorama
import shutil

from colorama import Fore
from pywinauto.application import Application
from pymouse import PyMouse

TEAMVIEWER = (0.59562272, 0.537674419)
START = (0.49975574, 0.863596872)
HOST = (0.143624817, 0.534317984)
RUN = (0.497313141, 0.748913988)
ACCEPT1 = (0.424035173, 0.544743701)
ACCEPT2 = (0.564240352, 0.67593397)

user = os.environ['USERPROFILE']
appdata = "\\AppData\\Local\\Packages\\StudioWildcard.4558480580BB9_1w2mm55455e38\\LocalState\\Saved\\UWPConfig\\UWP"
TARGET = f"{user}{appdata}"

UPDATING = False
INSTALLING = False
RUNNING = False
TIMESTAMP = ""
LOGO = """
                _    _    _                 _ _           
     /\        | |  | |  | |               | | |          
    /  \   _ __| | _| |__| | __ _ _ __   __| | | ___ _ __ 
   / /\ \ | '__| |/ /  __  |/ _` | '_ \ / _` | |/ _ \ '__|
  / ____ \| |  |   <| |  | | (_| | | | | (_| | |  __/ |   
 /_/    \_\_|  |_|\_\_|  |_|\__,_|_| |_|\__,_|_|\___|_|   
                                                          
                                                          
  ___       __   __       _               
 | _ )_  _  \ \ / /__ _ _| |_ _  _ __ ___ 
 | _ \ || |  \ V / -_) '_|  _| || / _/ _ \\
 |___/\_, |   \_/\___|_|  \__|\_, \__\___/
      |__/                    |__/        
"""
colorama.init()
print(Fore.GREEN + LOGO)


async def watchdog():
    """Check every 30 seconds if Ark is running, and start the server if it is not."""
    global RUNNING
    if "ShooterGame.exe" in (p.name() for p in psutil.process_iter()):
        if not RUNNING:
            print(Fore.GREEN + "Ark is Running.")
            RUNNING = True
    else:
        RUNNING = False
        if not UPDATING:
            print(Fore.RED + "Ark is not Running! Beginning reboot sequence...")
            await asyncio.sleep(1)
            # sync Game.ini file
            if GAME_SOURCE != "":
                if os.path.exists(GAME_SOURCE) and os.path.exists(TARGET):
                    s_file = os.path.join(GAME_SOURCE, "Game.ini")
                    t_file = os.path.join(TARGET, "Game.ini")
                    try:
                        os.remove(t_file)
                        shutil.copyfile(s_file, t_file)
                        print(Fore.CYAN + "Game.ini synced.")
                    except Exception as ex:
                        print(Fore.RED + f"Failed to sync Game.ini\nError: {ex}")

            # sync GameUserSettings.ini file
            if GAMEUSERSETTINGS_SOURCE != "":
                if os.path.exists(GAMEUSERSETTINGS_SOURCE) and os.path.exists(TARGET):
                    s_file = os.path.join(GAMEUSERSETTINGS_SOURCE, "GameUserSettings.ini")
                    t_file = os.path.join(TARGET, "GameUserSettings.ini")
                    try:
                        os.remove(t_file)
                        shutil.copyfile(s_file, t_file)
                        print(Fore.CYAN + "GameUserSettings.ini synced.")
                    except Exception as ex:
                        print(Fore.RED + f"Failed to sync GameUserSettings.ini\nError: {ex}")

            await calc_position_click(TEAMVIEWER)
            await asyncio.sleep(1)
            os.system("explorer.exe shell:appsFolder\StudioWildcard.4558480580BB9_1w2mm55455e38!AppARKSurvivalEvolved")
            await asyncio.sleep(12)
            await calc_position_click(START)
            await asyncio.sleep(5)
            await calc_position_click(HOST)
            await asyncio.sleep(2)
            await calc_position_click(RUN)
            await asyncio.sleep(0.5)
            await calc_position_click(ACCEPT1)
            await asyncio.sleep(0.5)
            await calc_position_click(ACCEPT2)
            await asyncio.sleep(8)
            print(Fore.MAGENTA)
            os.system("net stop LicenseManager")
            await asyncio.sleep(5)
            await send_hook("Reboot Complete", "Server should be back online shortly.", 65314)
            return


async def calc_position_click(clicktype):
    # get clicktype ratios
    x = clicktype[0]
    y = clicktype[1]

    # grab ark window
    if "ShooterGame.exe" in (p.name() for p in psutil.process_iter()):
        window_handle = win32gui.FindWindow(None, "ARK: Survival Evolved")
        window_rect = win32gui.GetWindowRect(window_handle)
        # check if window is maximized and maximize it if not
        tup = win32gui.GetWindowPlacement(window_handle)
        if tup[1] != win32con.SW_SHOWMAXIMIZED:
            window = win32gui.GetForegroundWindow()
            win32gui.ShowWindow(window, win32con.SW_MAXIMIZE)
            window_handle = win32gui.FindWindow(None, "ARK: Survival Evolved")
            window_rect = win32gui.GetWindowRect(window_handle)

        # sort window borders
        right = window_rect[2]
        bottom = window_rect[3] + 20

    else:
        # get screen resolution
        w = win32api.GetSystemMetrics(0)
        bottom = win32api.GetSystemMetrics(1)
        window_rect = (0, 0, w, bottom)

        # sort window borders
        right = window_rect[2]

    # get click positions
    x_click = right * x
    y_click = bottom * y

    # click dat shit
    mouse = PyMouse()
    mouse.click(int(x_click), int(y_click))
    mouse.click(int(x_click), int(y_click))


async def event_puller():
    """Gets most recent update event for ark and determines how recent it was"""
    server = 'localhost'
    logtype = 'System'
    hand = win32evtlog.OpenEventLog(server, logtype)
    flags = win32evtlog.EVENTLOG_SEQUENTIAL_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
    current_time = datetime.datetime.utcnow()
    n = 0
    while n == 0:
        events = win32evtlog.ReadEventLog(hand, flags, 0)
        for event in events:
            data = event.StringInserts
            if data:
                for msg in data:
                    # get most recent event that meets criteria
                    if msg == "9NBLGGH52XC6-StudioWildcard.4558480580BB9":
                        global UPDATING
                        global INSTALLING
                        timestamp = event.TimeGenerated
                        timedifference = current_time - timestamp
                        recent = False

                        # check how recent the last event was and determine if it just happened
                        if timedifference.days < 1:
                            if timedifference.seconds < 1800:
                                recent = True

                        if not UPDATING:
                            if event.EventID == 44:
                                if recent:
                                    print(Fore.RED + "DOWNLOAD DETECTED")
                                    await send_hook("Download Detected!", DOWNLOAD_MESSAGE, 14177041)
                                    UPDATING = True

                        else:
                            if not INSTALLING:
                                if event.EventID == 43:
                                    if recent:
                                        print(Fore.MAGENTA + "INSTALL DETECTED")
                                        await send_hook("Installing", INSTALL_MESSAGE, 1127128)
                                        INSTALLING = True

                            if event.EventID == 19:
                                if recent:
                                    print(Fore.GREEN + "UPDATE SUCCESS")
                                    await send_hook("Update Complete", COMPLETED_MESSAGE, 65314)
                                    UPDATING = False
                                    INSTALLING = False
                                    await asyncio.sleep(5)
                                    for p in psutil.process_iter():
                                        if p.name() == "ShooterGame.exe":
                                            p.kill()

                        n += 1
                        break


async def send_hook(title, message, color):
    if WEBHOOK_URL == "":
        return
    data = {"username": "ArkHandler", "avatar_url": "https://i.imgur.com/Wv5SsBo.png", "embeds": [
        {
            "description": message,
            "title": title,
            "color": color
        }
    ]}

    result = requests.post(WEBHOOK_URL, json=data)
    if result.status_code == 200:
        print(f"{title} Webhook sent!")
    else:
        print(f"{title} Webhook not sent!")


async def update_checker():
    processes = []
    for p in psutil.process_iter():
        if p.status() == "running":
            processes.append(p.name())
    if "WinStore.App.exe" not in processes:
        os.system("explorer.exe shell:appsFolder\Microsoft.WindowsStore_8wekyb3d8bbwe!App")
        await asyncio.sleep(3)

    else:
        def window_enumeration_handler(hwnd, top_windows):
            top_windows.append((hwnd, win32gui.GetWindowText(hwnd)))

        program = "microsoft store"
        top_windows = []
        win32gui.EnumWindows(window_enumeration_handler, top_windows)
        for window in top_windows:
            if program in window[1].lower():
                win32gui.ShowWindow(window[0], win32con.SW_MAXIMIZE)

    app = Application(backend="uia").connect(title="Microsoft Store")
    for button in app.windows()[0].descendants(control_type="Button"):
        if "See More" in str(button):
            button.click()
            await asyncio.sleep(1)
            for button2 in app.windows()[0].descendants(control_type="Button"):
                if "Downloads and updates" in str(button2):
                    button2.click()
                    await asyncio.sleep(1)
                    for button3 in app.windows()[0].descendants(control_type="Button"):
                        if "Get updates" in str(button3):
                            button3.click()
                            window = win32gui.GetForegroundWindow()
                            win32gui.ShowWindow(window, win32con.SW_MINIMIZE)
                            return


async def main():
    update_timer = 0
    while True:
        await event_puller()
        await watchdog()
        if update_timer == 30:
            if not UPDATING:
                for p in psutil.process_iter():
                    if p.name() == "WinStore.App.exe":
                        p.kill()
        if update_timer == 60:
            if not UPDATING:
                await update_checker()
            update_timer = 0

        update_timer += 1
        await asyncio.sleep(30)

try:
    Config = configparser.ConfigParser()
    Config.read("config.ini")
    url = Config.get("UserSettings", "webhookurl")
    WEBHOOK_URL = url.strip('\"')
    DOWNLOAD_MESSAGE = Config.get("UserSettings", "downloadmessage")
    INSTALL_MESSAGE = Config.get("UserSettings", "installmessage")
    COMPLETED_MESSAGE = Config.get("UserSettings", "completedmessage")
    g_source = Config.get("UserSettings", "gameinipath")
    GAME_SOURCE = g_source.strip('\"')
    gus_source = Config.get("UserSettings", "gameusersettingsinipath")
    GAMEUSERSETTINGS_SOURCE = gus_source.strip('\"')
    print(Fore.CYAN + "Config imported")
except Exception as e:
    print(Fore.RED + f"Config failed to import!\nError: {e}")


asyncio.run(main())


