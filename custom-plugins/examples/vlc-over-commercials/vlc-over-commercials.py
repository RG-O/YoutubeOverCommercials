
import win32gui
import win32con
import win32api
import pyautogui
import time

from flask import Flask, request, jsonify

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

    time.sleep(0.05) #TODO: is this necessary?

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
            time.sleep(0.5)
            send_spacebar(hwnd)
            return jsonify({"status": "ok"})
        else:
            #TODO: somhow globally define hwnd
            window_title = "VLC"  # Change this to your target window
            hwnd = find_window_by_title(window_title)
            send_spacebar(hwnd)
            time.sleep(0.5)
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
        print("Extension Stopped")

    return jsonify({"status": "ok"})


    

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})

if __name__ == "__main__":
    print("API running on http://localhost:64144")
    app.run(port=64144)
