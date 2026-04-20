
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
            if partial_title.lower() in title.lower():
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
        win32con.HWND_TOPMOST,  # Always on top #TODO: remove?
        x,
        y,
        target_width,
        target_height,
        win32con.SWP_NOACTIVATE, #TODO: bring other one back?
    )

    # pyautogui.press("playpause")


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




app = Flask(__name__)


@app.route("/init", methods=["POST"])
def init():
    data = request.json

    print(data)

    return jsonify({"status": "ok"})

@app.route("/custom-plugin-overlay-api", methods=["POST"])
def custom_plugin_overlay():
    data = request.json

    if data["type"] == "state_change":
        is_commercial = data["data"]["isCommercialState"]

        if is_commercial:
            print("START overlay")
            #TODO: somhow globally define hwnd
            window_title = "VLC"  # Change this to your target window
            hwnd = find_window_by_title(window_title)
            center_and_resize_window(hwnd, width_percent=90, height_percent=85)
            time.sleep(0.5)
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, 0x20, 0)  # spacebar down #TODO: move to function
            time.sleep(0.05)
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, 0x20, 0)  # spacebar up
        else:
            #TODO: somhow globally define hwnd
            window_title = "VLC"  # Change this to your target window
            hwnd = find_window_by_title(window_title)
            time.sleep(0.5)
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, 0x20, 0)  # spacebar down #TODO: move to function
            time.sleep(0.05)
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, 0x20, 0)  # spacebar up
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            print("STOP overlay")
    elif data["type"] == "init":
        #TODO: somhow globally define hwnd
        window_title = "VLC"  # Change this to your target window
        hwnd = find_window_by_title(window_title)
        make_borderless(hwnd) #TODO: do this only once
        print(data)


    return jsonify({"status": "ok"})

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})

if __name__ == "__main__":
    print("API running on http://localhost:64144")
    app.run(port=64144)
