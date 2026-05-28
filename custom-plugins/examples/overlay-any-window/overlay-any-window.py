
import asyncio
import websockets
import json
import time

import win32gui
import win32con
import win32api

PORT = 64146

clients = set()

window_title = "Mozilla Firefox"

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


def position_and_resize_window(
    hwnd,
    width_percent=90,
    height_percent=75,
    vertical="middle",   # "top", "middle", "bottom"
    horizontal="middle"  # "left", "middle", "right"
):
    # Get screen resolution
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    # Calculate target size
    target_width = int(screen_width * (width_percent / 100))
    target_height = int(screen_height * (height_percent / 100))

    # Calculate horizontal position
    if horizontal == "left":
        x = 0
    elif horizontal == "right":
        x = screen_width - target_width
    else:  # "middle"
        x = (screen_width - target_width) // 2

    # Calculate vertical position
    if vertical == "top":
        y = 0
    elif vertical == "bottom":
        y = screen_height - target_height
    else:  # "middle"
        y = (screen_height - target_height) // 2

    # Restore/show window without activating it
    # win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)

    # Move and resize window
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,  # Keeps window above fullscreen apps
        x,
        y,
        target_width,
        target_height,
        win32con.SWP_NOACTIVATE,
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
#         position_and_resize_window(hwnd, width_percent=40, height_percent=40)
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


async def handle_client(websocket):
    print("Client connected")
    clients.add(websocket)

    try:
        async for message in websocket:
            msg = json.loads(message)
            await handle_message(websocket, msg)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.remove(websocket)
        print("Client disconnected")

async def handle_message(ws, msg):
    global window_title
    print(msg)

    message_type = msg["type"]
    preferences = msg["data"]["preferences"]

    overlay_video_width = float(preferences["videoOverlayWidth"])
    overlay_video_height = float(preferences["videoOverlayHeight"])
    overlay_video_location_horizontal = preferences["overlayVideoLocationHorizontal"]
    overlay_video_location_vertical = preferences["overlayVideoLocationVertical"]
    is_pip_mode = preferences["isPiPMode"]
    pip_location_horizontal = preferences["pipLocationHorizontal"]
    pip_location_vertical = preferences["pipLocationHorizontal"]
    pip_height = float(preferences["pipHeight"])
    pip_width = float(preferences["pipWidth"])


    if message_type == "init":
        print(msg)

        hwnd = find_window_by_title(window_title)
        if hwnd is None:
            await send_status(ws, "Window not found", "Window not found")
        make_borderless(hwnd)
        print("Extension Initiated.")

        # Optionally send status to present it to user
        # await send_status(ws, "Connected", "Ready")

    elif message_type == "commercial_state_change":
        is_commercial = msg["data"]["isCommercialState"]

        if is_commercial:
            print("START overlay")
            hwnd = find_window_by_title(window_title)
            position_and_resize_window(hwnd, width_percent=overlay_video_width, height_percent=overlay_video_height, vertical=overlay_video_location_vertical, horizontal=overlay_video_location_horizontal)
            # time.sleep(0.5)
            # send_spacebar(hwnd)
        else:
            hwnd = find_window_by_title(window_title)
            if is_pip_mode:
                # send_spacebar(hwnd)
                # time.sleep(0.5)
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            else:
                position_and_resize_window(hwnd, width_percent=pip_height, height_percent=pip_width, vertical=pip_location_vertical, horizontal=pip_location_horizontal)
            
            print("STOP overlay")

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = msg["data"]["isFullscreen"]

        hwnd = find_window_by_title(window_title)

        if is_fullscreen:
            print("User entered fullscreen on browser")
            make_borderless(hwnd)
        else:
            print("User exited fullscreen on browser")
            remove_topmost(hwnd, width_percent=90, height_percent=85)
            restore_borders(hwnd)

        print("Fullscreen state changed on browser. is_fullscreen = ", is_fullscreen)

    elif message_type == "end": #TODO: is this needed or can I go by disconnect?
        print("Extension Stopped")

        hwnd = find_window_by_title(window_title)
        remove_topmost(hwnd, width_percent=90, height_percent=75)
        restore_borders(hwnd)
        print("Extension Stopped")

async def send_status(ws, display, debug):
    try:
        await ws.send(json.dumps({
            "type": "status",
            "timestamp": time.time(),
            "data": {},
            "meta": {
                "display": display,
                "debug": debug
            }
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_status send stopped: client disconnected")

async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"Server running on ws://localhost:{PORT}")
        await asyncio.Future()

asyncio.run(main())
