
import win32gui
import win32con
import win32api
import pyautogui
import time
import requests
import os
import subprocess

from flask import Flask, request, jsonify

is_vlc_http_api_control_mode = True
vlc_http_api_auth = ("", "1234")
my_file_path = "file:///C:/Users/user/Downloads/video.mp4"


def find_window_by_title(partial_title):
    def enum_handler(hwnd, result):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if partial_title in title:
                print(title)
                result.append(hwnd)

    result = []
    win32gui.EnumWindows(enum_handler, result)
    return result[0] if result else None

def find_vlc_exe():
    possible_paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    print("Could not find vlc.exe in Program Files or Program Files (x86).")

def open_vlc_with_specific_file(file_path):
    global vlc_http_api_auth

    vlc_path = find_vlc_exe()

    subprocess.Popen([
        vlc_path,

        # Main UI/interface: no normal VLC window controls
        #"--intf", "dummy",
        "--qt-start-minimized",
        "--qt-minimal-view",

        # Still enable HTTP remote control
        "--extraintf", "http",
        "--http-password", "1234",

        # Optional quality-of-life flags
        "--no-video-title-show",
        "--no-qt-privacy-ask",
        "--no-qt-error-dialogs",
    ])

    requests.get(
        "http://localhost:8080/requests/status.json",
        params={"command": "in_play", "input": file_path},
        auth=vlc_http_api_auth
    )

def center_and_resize_window(hwnd, width_percent=90, height_percent=75):
    # Get screen resolution
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    # Calculate target size
    target_width = int(screen_width * (width_percent / 100))
    target_height = int(screen_height * (height_percent / 100))

    # Calculate centered position
    x = (screen_width - target_width) // 2
    y = (screen_height - target_height) // 2

    # Restore window if minimized/maximized
    # win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)

    # Move and resize window

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,  # Giving TOPMOST status so it shows over top of fullscreen browser
        #win32con.HWND_TOP,
        x,
        y,
        target_width,
        target_height,
        win32con.SWP_NOACTIVATE, #TODO: bring other one back?
    )

    #time.sleep(0.05) #TODO: is this necessary?

    # # instantly removing TOPMOST status so user can easily minimize it, but keeping it on top of the fullscreen browser
    # win32gui.SetWindowPos(
    #     hwnd,
    #     #win32con.HWND_TOPMOST,  # Always on top #TODO: remove?
    #     #win32con.HWND_TOP,
    #     win32con.HWND_NOTOPMOST, 
    #     x,
    #     y,
    #     target_width,
    #     target_height,
    #     win32con.SWP_NOACTIVATE, #TODO: bring other one back?
    # )

    # pyautogui.press("playpause")

def remove_topmost(hwnd, width_percent=90, height_percent=75):
    # Get screen resolution
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    # Calculate target size
    target_width = int(screen_width * (width_percent / 100))
    target_height = int(screen_height * (height_percent / 100))

    # Calculate centered position
    x = (screen_width - target_width) // 2
    y = (screen_height - target_height) // 2

    # removing TOPMOST status so user can easily minimize it, but keeping it on top of the fullscreen browser
    win32gui.SetWindowPos(
        hwnd,
        #win32con.HWND_TOPMOST,  # Always on top #TODO: remove?
        #win32con.HWND_TOP,
        #win32con.HWND_NOTOPMOST, 
        win32con.HWND_BOTTOM,
        x,
        y,
        target_width,
        target_height,
        win32con.SWP_NOACTIVATE, #TODO: bring other one back?
    )

def minimize_window(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)


def make_borderless(hwnd):
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)

    # Remove title bar + borders
    style &= ~(
        win32con.WS_CAPTION |
        win32con.WS_THICKFRAME |
        win32con.WS_MINIMIZE |
        win32con.WS_MAXIMIZE |
        win32con.WS_SYSMENU
    )

    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

    # Apply changes
    win32gui.SetWindowPos(
        hwnd,
        None,
        0, 0, 0, 0,
        win32con.SWP_NOMOVE |
        win32con.SWP_NOSIZE |
        win32con.SWP_NOZORDER |
        win32con.SWP_FRAMECHANGED
    )


def restore_borders(hwnd):
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)

    style |= (
        win32con.WS_CAPTION |
        win32con.WS_THICKFRAME |
        win32con.WS_MINIMIZE |
        win32con.WS_MAXIMIZE |
        win32con.WS_SYSMENU
    )

    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

    win32gui.SetWindowPos(
        hwnd,
        None,
        0, 0, 0, 0,
        win32con.SWP_FRAMECHANGED |
        win32con.SWP_NOMOVE |
        win32con.SWP_NOSIZE |
        win32con.SWP_NOZORDER
    )


def send_ctrl_h(hwnd):
    # Press CTRL down
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_CONTROL, 0)

    # Press H down
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, ord('H'), 0)

    time.sleep(0.05)

    # Release H
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, ord('H'), 0)

    # Release CTRL
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_CONTROL, 0)


# if __name__ == "__main__":
#     time.sleep(1)

#     window_title = "VLC"  # Change this to your target window

#     hwnd = find_window_by_title(window_title)

#     if hwnd:
#         center_and_resize_window(hwnd, width_percent=40, height_percent=40)
#         time.sleep(0.5)
#         make_borderless(hwnd) #TODO: do this only once
#         win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, 0x20, 0)  # spacebar down #TODO: move to function
#         win32gui.PostMessage(hwnd, win32con.WM_KEYUP, 0x20, 0)  # spacebar up
#         send_ctrl_h(hwnd) #TODO: make work
#         print("Window positioned successfully.")
#     else:
#         print("Window not found.")

def send_spacebar(hwnd):
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, 0x20, 0)  # spacebar down
    time.sleep(0.05)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, 0x20, 0)  # spacebar up


app = Flask(__name__)


@app.route("/custom-plugin-overlay-api", methods=["POST"])
def custom_plugin_overlay():
    global is_vlc_http_api_control_mode
    global vlc_http_api_auth
    global my_file_path

    data = request.json
    request_type = data["type"]

    if request_type == "commercial_state_change":
        is_commercial = data["data"]["isCommercialState"]

        if is_commercial:
            print("START overlay")
            #TODO: somhow globally define hwnd
            window_title = "VLC"  # Change this to your target window
            hwnd = find_window_by_title(window_title)
            center_and_resize_window(hwnd, width_percent=90, height_percent=85)
            if is_vlc_http_api_control_mode:
                time.sleep(0.25)
                requests.get("http://localhost:8080/requests/status.json?command=pl_play", auth=vlc_http_api_auth)
            else:
                time.sleep(0.5)
                send_spacebar(hwnd)
            return jsonify({"status": "ok"})
        else:
            #TODO: somhow globally define hwnd
            window_title = "VLC"  # Change this to your target window
            hwnd = find_window_by_title(window_title)
            if is_vlc_http_api_control_mode:
                requests.get("http://localhost:8080/requests/status.json?command=pl_pause", auth=vlc_http_api_auth)
                time.sleep(0.25)
            else:
                send_spacebar(hwnd)
                time.sleep(1)
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            print("STOP overlay")
    elif request_type == "browser_fullscreen_state_change":
        is_fullscreen = data["data"]["isFullscreen"]

        window_title = "VLC"  # Change this to your target window
        hwnd = find_window_by_title(window_title)

        if is_fullscreen:
            print("User entered fullscreen on browser")
            make_borderless(hwnd)
        else:
            print("User exited fullscreen on browser")
            remove_topmost(hwnd, width_percent=90, height_percent=85)
            restore_borders(hwnd)
    elif request_type == "init":
        if is_vlc_http_api_control_mode:
            open_vlc_with_specific_file(my_file_path)
            time.sleep(5) #todo: better way to wait?
            requests.get("http://localhost:8080/requests/status.json?command=pl_pause", auth=vlc_http_api_auth)

        window_title = "VLC"  # Change this to your target window
        hwnd = find_window_by_title(window_title)
        if hwnd is None:
            return jsonify({"status": "error", "error": "No VLC window found."})
        make_borderless(hwnd)
        print("Extension Initiated. Tip: Click on VLC and hit Ctrl + H to hide VLC UI")
        print(data)
    elif request_type == "end":
        #TODO: somhow globally define hwnd
        window_title = "VLC"  # Change this to your target window
        hwnd = find_window_by_title(window_title)
        remove_topmost(hwnd, width_percent=90, height_percent=75)
        restore_borders(hwnd)

        if is_vlc_http_api_control_mode:
            requests.get("http://localhost:8080/requests/status.json?command=quit", auth=vlc_http_api_auth) #todo: should use pl_stop?
        print("Extension Stopped")

    return jsonify({"status": "ok"})


    

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})

if __name__ == "__main__":
    print("API running on http://localhost:64144")
    app.run(port=64144)
