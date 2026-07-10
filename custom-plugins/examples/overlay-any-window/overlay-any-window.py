
import asyncio
import websockets
import json
import time

import win32gui
import win32con
import win32api
import win32process

from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

PORT = 64146

clients = set()

window_title = "Picture"

def get_window_dropdown_options():
    windows = []

    def enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd).strip()

        # Ignore windows without a visible title.
        if not title:
            return

        windows.append({
            "label": title,
            "value": title,
        })

    win32gui.EnumWindows(enum_handler, None)

    # Sort alphabetically and remove duplicate titles.
    unique_windows = {
        window["value"]: window
        for window in windows
    }

    return sorted(
        unique_windows.values(),
        key=lambda window: window["label"].lower()
    )

#TODO: rename partial_title variable to just title
def find_window_by_title(partial_title):
    def enum_handler(hwnd, result):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if partial_title == title:
                print(title)
                result.append(hwnd)

    result = []
    win32gui.EnumWindows(enum_handler, result)
    return result[0] if result else None

def mute_application_of_window(hwnd, mute=True):
    _, pid = win32process.GetWindowThreadProcessId(hwnd)

    found_audio = False

    # Find audio session for PID
    sessions = AudioUtilities.GetAllSessions()

    for session in sessions:
        if session.Process and session.Process.pid == pid:
            volume = session._ctl.QueryInterface(ISimpleAudioVolume)
            volume.SetMute(1 if mute else 0, None)

            process_name = session.Process.name()

            print(
                f'{"Muted" if mute else "Unmuted"} '
                f'window "{win32gui.GetWindowText(hwnd)}" '
                f'({process_name})'
            )

            found_audio = True

    if not found_audio:
        print("No active audio session found for that window.")

def position_and_resize_window(
    hwnd,
    width_percent=90,
    height_percent=75,
    vertical="middle",   # "top", "middle", "bottom"
    horizontal="middle"  # "left", "middle", "right"
):
    print("hwnd = ", hwnd, ", ", "width_percent = ", width_percent, ", ", "height_percent = ", height_percent, ", ", "vertical = ", vertical, ", ", "horizontal = ", horizontal, ", ")
    # Get screen resolution
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    # Calculate target size
    target_width = int(screen_width * (width_percent / 100))
    target_height = int(screen_height * (height_percent / 100))

    print("screen_width = ", screen_width, ", ", "screen_height = ", screen_height, ", ", "target_width = ", target_width, ", ", "target_height = ", target_height)

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

    print("x = ", x, ", ", "y = ", y)

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

    if message_type == "plugin_manifest":
        await send_manifest(ws)
        return

    preferences = msg["data"]["preferences"]
    plugin_preferences = preferences["pluginOverlayPreferences"]["preferences"]
    print(plugin_preferences)

    window_title = plugin_preferences.get("window-title", "")
    print(window_title)

    if not window_title:
        await send_status(
            ws,
            "No window selected",
            "The window-title preference is empty."
        )
        return

    overlay_video_width = float(preferences["videoOverlayWidth"])
    overlay_video_height = float(preferences["videoOverlayHeight"])
    overlay_video_location_horizontal = preferences["overlayVideoLocationHorizontal"]
    overlay_video_location_vertical = preferences["overlayVideoLocationVertical"]
    is_pip_mode = preferences["isPiPMode"]
    pip_location_horizontal = preferences["pipLocationHorizontal"]
    pip_location_vertical = preferences["pipLocationVertical"]
    pip_height = float(preferences["pipHeight"])
    pip_width = float(preferences["pipWidth"])

    hwnd = find_window_by_title(window_title)
    if hwnd is None:
        await send_status(
            ws,
            f'Could not find a window matching "{window_title}".',
            f'Could not find a window matching "{window_title}".'
        )
        return
    else:
        if message_type == "init":
            print(msg)

            make_borderless(hwnd)

            if is_pip_mode:
                position_and_resize_window(hwnd, width_percent=pip_height, height_percent=pip_width, vertical=pip_location_vertical, horizontal=pip_location_horizontal)

            mute_application_of_window(hwnd, mute=True)

            print("Extension Initiated.")

        elif message_type == "commercial_state_change":
            is_commercial = msg["data"]["isCommercialState"]

            if is_commercial:
                print("START overlay")
                position_and_resize_window(hwnd, width_percent=overlay_video_width, height_percent=overlay_video_height, vertical=overlay_video_location_vertical, horizontal=overlay_video_location_horizontal)
                mute_application_of_window(hwnd, mute=False)
            else:
                hwnd = find_window_by_title(window_title)
                mute_application_of_window(hwnd, mute=True)
                if is_pip_mode:
                    position_and_resize_window(hwnd, width_percent=pip_height, height_percent=pip_width, vertical=pip_location_vertical, horizontal=pip_location_horizontal)
                else:
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            
                print("STOP overlay")

        elif message_type == "browser_fullscreen_state_change":
            is_fullscreen = msg["data"]["isFullscreen"]

            hwnd = find_window_by_title(window_title)

            if is_fullscreen:
                print("User entered fullscreen on browser")
                mute_application_of_window(hwnd, mute=True)
                make_borderless(hwnd)
                if is_pip_mode:
                    position_and_resize_window(hwnd, width_percent=pip_height, height_percent=pip_width, vertical=pip_location_vertical, horizontal=pip_location_horizontal)
            else:
                print("User exited fullscreen on browser")
                mute_application_of_window(hwnd, mute=False)
                remove_topmost(hwnd, width_percent=90, height_percent=85)
                restore_borders(hwnd)

            print("Fullscreen state changed on browser. is_fullscreen = ", is_fullscreen)

        elif message_type == "end": #TODO: is this needed or can I go by disconnect?
            print("Extension Stopped")

            mute_application_of_window(hwnd, mute=False)
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

async def send_manifest(ws):
    try:
        window_options = get_window_dropdown_options()

        await ws.send(json.dumps({
            "type": "plugin_manifest",
            "timestamp": time.time(),
            "data": {
                "name": "Overlay Any Window",
                "id": "overlay-any-window",
                "version": "1.0.0",
                "description": "Overlay any open Windows application.",
                "primaryColor": "#12384d",
                "secondaryColor": "#dadcdc",
                "capabilities": ["overlay"],
                "preferences": [
                    {
                        "key": "window-title",
                        "label": "Window",
                        "description": "Select the window to use as the overlay.",
                        "type": "select",
                        "options": window_options,
                        "default": (
                            window_options[0]["value"]
                            if window_options
                            else ""
                        ),
                        "required": True,
                    }
                ],
            },
            "meta": {
                "display": "Sending Manifest",
                "debug": "Sending Manifest",
            },
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_manifest stopped: client disconnected")

async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"Server running on ws://localhost:{PORT}")
        await asyncio.Future()

asyncio.run(main())
