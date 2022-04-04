
from pywinauto.application import Application
from time import sleep
import win32gui
import win32con
import psutil
import os
import re


class Updater:
    def __init__(self):
        self._hwnd = None

    def BringToTop(self):
        win32gui.BringWindowToTop(self._hwnd)

    def SetAsForegroundWindow(self):
        win32gui.SetForegroundWindow(self._hwnd)

    def Maximize(self):
        win32gui.ShowWindow(self._hwnd, win32con.SW_MAXIMIZE)

    def setActWin(self):
        win32gui.SetActiveWindow(self._hwnd)

    def _window_enum_callback(self, hwnd, wildcard):
        """Pass to win32gui.EnumWindows() to check all the opened windows"""
        if re.match(wildcard, str(win32gui.GetWindowText(hwnd))) is not None:
            self._hwnd = hwnd

    def find_window_wildcard(self, wildcard):
        self._hwnd = None
        win32gui.EnumWindows(self._window_enum_callback, wildcard)


def main():
    if "WinStore.App.exe" not in (p.name() for p in psutil.process_iter()):
        os.system("explorer.exe shell:appsFolder\Microsoft.WindowsStore_8wekyb3d8bbwe!App")
    sleep(5)
    up = Updater()
    try:
        program = "Microsoft Store"
        up.find_window_wildcard(program)
        up.Maximize()
        up.BringToTop()
        up.SetAsForegroundWindow()
    except Exception as e:
        print(f"ERROR: {e}")


main()


app = Application(backend="uia").connect(title="Microsoft Store")
dlg = app.window(title='Microsoft Store')

for button in app.windows()[0].descendants(control_type="Button"):
    if "See More" in str(button):
        print(button)
        button.click()
        sleep(1)
        for button2 in app.windows()[0].descendants(control_type="Button"):
            if "Downloads and updates" in str(button2):
                print(button2)
                button2.click()
                sleep(1)
                for button3 in app.windows()[0].descendants(control_type="Button"):
                    if "Get updates" in str(button3):
                        print(button3)
                        button3.click()
                        window_handle = win32gui.FindWindow(None, "Microsoft Store")
                        window = win32gui.GetForegroundWindow()
                        win32gui.ShowWindow(window, win32con.SW_MINIMIZE)


