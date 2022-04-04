
from pywinauto.application import Application
from time import sleep
import win32gui
import win32con
import psutil
import os


def main():
    # for p in psutil.process_iter():
    #     print(p)
    #     if "WinStore.App.exe" not in p.name() or p.status() == "stopped":
    #         os.system("explorer.exe shell:appsFolder\Microsoft.WindowsStore_8wekyb3d8bbwe!App")
    #         sleep(3)
    #         break
    # else:
    def window_enumeration_handler(hwnd, top_windows):
        top_windows.append((hwnd, win32gui.GetWindowText(hwnd)))

    program = "sponsored session"
    top_windows = []
    win32gui.EnumWindows(window_enumeration_handler, top_windows)
    for window in top_windows:
        if program in window[1].lower():
            print(window[1])
            handle = win32gui.FindWindow(None, window[1])
            win32gui.SetForegroundWindow(handle)
            win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
            # win32gui.ShowWindow(window[0], win32con.SW_MAXIMIZE)



main()

# app = Application(backend="uia").connect(title="Sponsored session")
# dlg = app.window(title='Sponsored session')
#
# for button in app.windows()[0].descendants(control_type="Button"):
#     print(button)
#     if "See More" in str(button):
#         button.click()
#         sleep(1)
#         for button2 in app.windows()[0].descendants(control_type="Button"):
#             if "Downloads and updates" in str(button2):
#                 button2.click()
#                 sleep(1)
#                 for button3 in app.windows()[0].descendants(control_type="Button"):
#                     if "Get updates" in str(button3):
#                         button3.click()
#                         window_handle = win32gui.FindWindow(None, "Microsoft Store")
#                         window = win32gui.GetForegroundWindow()
#                         win32gui.ShowWindow(window, win32con.SW_MINIMIZE)
#                         break


