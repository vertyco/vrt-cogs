# Create a webhook for the discord channel this rig hosts and pase it below in the quotes.
import win32con

WEBHOOK_URL = ""


"""DO NOT CHANGE ANYTHING BELOW THIS LINE"""
import psutil
import os
import asyncio
import win32gui
import win32api
import win32evtlog
import datetime

from pymouse import PyMouse
from time import sleep

TEAMVIEWER = (0.59562272, 0.537674419)
START = (0.49975574, 0.863596872)
HOST = (0.143624817, 0.534317984)
RUN = (0.497313141, 0.748913988)
ACCEPT1 = (0.424035173, 0.544743701)
ACCEPT2 = (0.564240352, 0.67593397)

UPDATING = False
TIMESTAMP = ""


async def watchdog():
    """Check every 30 seconds if Ark is running, and start the server if it is not."""
    if "ShooterGame.exe" in (p.name() for p in psutil.process_iter()):
        print("Ark is Running!")
    else:
        if not UPDATING:
            print("Ark is not Running! Starting now...")
            await calc_position_click(TEAMVIEWER)
            sleep(1)
            os.system("explorer.exe shell:appsFolder\StudioWildcard.4558480580BB9_1w2mm55455e38!AppARKSurvivalEvolved")
            sleep(12)
            await calc_position_click(START)
            sleep(6)
            await calc_position_click(HOST)
            sleep(3)
            await calc_position_click(RUN)
            sleep(1)
            await calc_position_click(ACCEPT1)
            sleep(1)
            await calc_position_click(ACCEPT2)
            print(f"Ark has been started!")


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
    # print(f"Click: x = {x_click}, y = {y_click}")

    # click dat shit
    mouse = PyMouse()
    mouse.click(int(x_click), int(y_click))
    mouse.click(int(x_click), int(y_click))


async def event_watcher():
    """Gets most recent update event for ark and determines how recent it was"""
    server = 'localhost'
    logtype = 'System'
    hand = win32evtlog.OpenEventLog(server, logtype)
    flags = win32evtlog.EVENTLOG_SEQUENTIAL_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
    n = 0
    while n == 0:
        events = win32evtlog.ReadEventLog(hand, flags, 0)
        current_time = datetime.datetime.utcnow()
        for event in events:
            data = event.StringInserts
            if data:
                for msg in data:

                    # get most recent event that meets criteria
                    if msg == "9NBLGGH52XC6-StudioWildcard.4558480580BB9":
                        print('Time Generated:', event.TimeGenerated)
                        print('Source Name:', event.SourceName)
                        global UPDATING

                        if event.EventID == 44:
                            timestamp = event.TimeGenerated
                            timedifference = current_time - timestamp
                            if timedifference.seconds < 3600:
                                print("DOWNLOAD DETECTED")
                                UPDATING = True

                        elif event.EventID == 43:
                            timestamp = event.TimeGenerated
                            timedifference = current_time - timestamp
                            if timedifference.seconds < 3600:
                                print("INSTALL DETECTED")

                        elif event.EventID == 19:
                            timestamp = event.TimeGenerated
                            timedifference = current_time - timestamp
                            if timedifference.seconds < 3600:
                                print("UPDATE SUCCESS")
                                UPDATING = False
                        n += 1
                        break
        else:
            n += 1
            break

# asyncio.run(event_watcher())
# asyncio.run(watchdog_loop())

async def main():
    await event_watcher()
    await watchdog()

asyncio.run(main())


