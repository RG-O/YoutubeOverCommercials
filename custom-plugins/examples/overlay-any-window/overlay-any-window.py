import asyncio
import json
import time

import websockets
import win32api
import win32con
import win32gui
import win32process

from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume


PORT = 64146
SPACEBAR_KEY = 0x20


def get_window_dropdown_options():
    """Return visible titled windows as dropdown options."""
    window_titles = set()

    def enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd).strip()
        if title:
            window_titles.add(title)

    win32gui.EnumWindows(enum_handler, None)

    return [
        {"label": title, "value": title}
        for title in sorted(window_titles, key=str.lower)
    ]


def find_window_by_title(title):
    """Find a visible window whose title exactly matches the selected title."""
    matching_windows = []

    def enum_handler(hwnd, result):
        if not win32gui.IsWindowVisible(hwnd):
            return

        if win32gui.GetWindowText(hwnd).strip() == title:
            result.append(hwnd)

    win32gui.EnumWindows(enum_handler, matching_windows)
    return matching_windows[0] if matching_windows else None


def mute_application_of_window(hwnd, mute=True):
    """Mute or unmute every audio session owned by the window's process."""
    _, process_id = win32process.GetWindowThreadProcessId(hwnd)
    window_title = win32gui.GetWindowText(hwnd)

    found_audio_session = False

    for session in AudioUtilities.GetAllSessions():
        if not session.Process or session.Process.pid != process_id:
            continue

        volume = session._ctl.QueryInterface(ISimpleAudioVolume)
        volume.SetMute(1 if mute else 0, None)

        action = "Muted" if mute else "Unmuted"
        print(f'{action} window "{window_title}" ({session.Process.name()})')
        found_audio_session = True

    if not found_audio_session:
        print(f'No active audio session found for "{window_title}".')


def send_spacebar(hwnd):
    """Send a spacebar press to a window without activating it."""
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, SPACEBAR_KEY, 0)
    time.sleep(0.05)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, SPACEBAR_KEY, 0)


def calculate_window_position(
    width_percent,
    height_percent,
    horizontal,
    vertical,
):
    """Calculate a window's size and screen position."""
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    target_width = int(screen_width * width_percent / 100)
    target_height = int(screen_height * height_percent / 100)

    if horizontal == "left":
        x = 0
    elif horizontal == "right":
        x = screen_width - target_width
    else:
        x = (screen_width - target_width) // 2

    if vertical == "top":
        y = 0
    elif vertical == "bottom":
        y = screen_height - target_height
    else:
        y = (screen_height - target_height) // 2

    return x, y, target_width, target_height


def position_and_resize_window(
    hwnd,
    width_percent=90,
    height_percent=75,
    vertical="middle",
    horizontal="middle",
):
    """Show, resize, position, and temporarily keep a window on top."""
    x, y, width, height = calculate_window_position(
        width_percent,
        height_percent,
        horizontal,
        vertical,
    )

    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,
        x,
        y,
        width,
        height,
        win32con.SWP_NOACTIVATE,
    )


def remove_topmost(hwnd, width_percent=90, height_percent=75):
    """Remove topmost status and place the window near the bottom of the stack."""
    x, y, width, height = calculate_window_position(
        width_percent,
        height_percent,
        horizontal="middle",
        vertical="middle",
    )

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_BOTTOM,
        x,
        y,
        width,
        height,
        win32con.SWP_NOACTIVATE,
    )


def minimize_window(hwnd):
    """Minimize a window."""
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)


def make_borderless(hwnd):
    """Remove the window title bar and resize borders."""
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)

    style &= ~(
        win32con.WS_CAPTION
        | win32con.WS_THICKFRAME
        | win32con.WS_MINIMIZE
        | win32con.WS_MAXIMIZE
        | win32con.WS_SYSMENU
    )

    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

    win32gui.SetWindowPos(
        hwnd,
        None,
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE
        | win32con.SWP_NOSIZE
        | win32con.SWP_NOZORDER
        | win32con.SWP_FRAMECHANGED,
    )


def restore_borders(hwnd):
    """Restore the normal title bar and resize borders."""
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)

    style |= (
        win32con.WS_CAPTION
        | win32con.WS_THICKFRAME
        | win32con.WS_MINIMIZE
        | win32con.WS_MAXIMIZE
        | win32con.WS_SYSMENU
    )

    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

    win32gui.SetWindowPos(
        hwnd,
        None,
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE
        | win32con.SWP_NOSIZE
        | win32con.SWP_NOZORDER
        | win32con.SWP_FRAMECHANGED,
    )


def get_overlay_settings(message):
    """Read the extension and plugin preferences from a message."""
    preferences = message.get("data", {}).get("preferences", {})

    plugin_preferences = (
        preferences.get("pluginOverlayPreferences", {})
        .get("preferences", {})
    )

    return {
        "window_title": plugin_preferences.get("window-title", ""),
        "should_mute": bool(
            plugin_preferences.get("should-mute-window", True)
        ),
        "should_send_spacebar": bool(
            plugin_preferences.get("should-send-spacebar", False)
        ),
        "overlay_width": float(preferences.get("videoOverlayWidth", 90)),
        "overlay_height": float(preferences.get("videoOverlayHeight", 75)),
        "overlay_horizontal": preferences.get(
            "overlayVideoLocationHorizontal",
            "middle",
        ),
        "overlay_vertical": preferences.get(
            "overlayVideoLocationVertical",
            "middle",
        ),
        "is_pip_mode": bool(preferences.get("isPiPMode", False)),
        "pip_horizontal": preferences.get(
            "pipLocationHorizontal",
            "right",
        ),
        "pip_vertical": preferences.get(
            "pipLocationVertical",
            "bottom",
        ),
        "pip_width": float(preferences.get("pipWidth", 30)),
        "pip_height": float(preferences.get("pipHeight", 30)),
    }


def show_pip_window(hwnd, settings):
    """Show the selected window using the configured picture-in-picture size."""
    position_and_resize_window(
        hwnd,
        width_percent=settings["pip_width"],
        height_percent=settings["pip_height"],
        vertical=settings["pip_vertical"],
        horizontal=settings["pip_horizontal"],
    )


def show_overlay_window(hwnd, settings):
    """Show the selected window using the configured overlay size."""
    position_and_resize_window(
        hwnd,
        width_percent=settings["overlay_width"],
        height_percent=settings["overlay_height"],
        vertical=settings["overlay_vertical"],
        horizontal=settings["overlay_horizontal"],
    )


async def handle_client(websocket):
    print("Client connected")

    try:
        async for raw_message in websocket:
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await send_status(
                    websocket,
                    "Invalid message",
                    "The plugin received invalid JSON.",
                )
                continue

            await handle_message(websocket, message)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        print("Client disconnected")


async def handle_message(websocket, message):
    message_type = message.get("type")
    print(f"Received message: {message_type}")

    if message_type == "plugin_manifest":
        await send_manifest(websocket)
        return

    settings = get_overlay_settings(message)
    window_title = settings["window_title"]

    if not window_title:
        await send_status(
            websocket,
            "No window selected",
            "The window-title preference is empty.",
        )
        return

    hwnd = find_window_by_title(window_title)

    if hwnd is None:
        await send_status(
            websocket,
            f'Could not find "{window_title}"',
            f'Could not find a visible window titled "{window_title}".',
        )
        return

    if message_type == "init":
        make_borderless(hwnd)

        if settings["is_pip_mode"]:
            show_pip_window(hwnd, settings)
        else:
            minimize_window(hwnd)

        if settings["should_mute"]:
            mute_application_of_window(hwnd, mute=True)

        print("Extension initiated.")
        return

    if message_type == "commercial_state_change":
        is_commercial = bool(
            message.get("data", {}).get("isCommercialState", False)
        )

        if is_commercial:
            print("Starting overlay.")
            show_overlay_window(hwnd, settings)

            if settings["should_mute"]:
                mute_application_of_window(hwnd, mute=False)

            if settings["should_send_spacebar"]:
                time.sleep(0.3)
                send_spacebar(hwnd)

        else:
            print("Stopping overlay.")

            if settings["should_send_spacebar"]:
                send_spacebar(hwnd)
                time.sleep(0.3)

            if settings["should_mute"]:
                mute_application_of_window(hwnd, mute=True)

            if settings["is_pip_mode"]:
                show_pip_window(hwnd, settings)
            else:
                minimize_window(hwnd)

        return

    if message_type == "browser_fullscreen_state_change":
        is_fullscreen = bool(
            message.get("data", {}).get("isFullscreen", False)
        )

        if is_fullscreen:
            print("Browser entered fullscreen.")

            if settings["should_mute"]:
                mute_application_of_window(hwnd, mute=True)

            make_borderless(hwnd)

            if settings["is_pip_mode"]:
                show_pip_window(hwnd, settings)

        else:
            print("Browser exited fullscreen.")

            if settings["should_mute"]:
                mute_application_of_window(hwnd, mute=False)

            remove_topmost(hwnd, width_percent=90, height_percent=85)
            restore_borders(hwnd)

        return

    if message_type == "end":
        print("Extension stopped.")

        # Always unmute during cleanup in case the preference changed while
        # the extension was running.
        mute_application_of_window(hwnd, mute=False)
        remove_topmost(hwnd, width_percent=90, height_percent=75)
        restore_borders(hwnd)
        return

    await send_status(
        websocket,
        "Unknown message",
        f'Unsupported message type: "{message_type}".',
    )


async def send_status(websocket, display, debug):
    message = {
        "type": "status",
        "timestamp": time.time(),
        "data": {},
        "meta": {
            "display": display,
            "debug": debug,
        },
    }

    try:
        await websocket.send(json.dumps(message))
    except websockets.exceptions.ConnectionClosed:
        print("Could not send status because the client disconnected.")


async def send_manifest(websocket):
    window_options = get_window_dropdown_options()

    manifest = {
        "type": "plugin_manifest",
        "timestamp": time.time(),
        "data": {
            "name": "Overlay Any Window",
            "id": "overlay-any-window",
            "version": "1.0.0",
            "description": (
                "Overlay any open Windows application. This plugin uses the "
                "overlay and picture-in-picture size and location settings "
                "from the extension's additional settings."
            ),
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
                },
                {
                    "key": "should-mute-window",
                    "label": "Mute window program during commercials",
                    "description": (
                        "This mutes the entire application that owns the "
                        "selected window. If the application has multiple "
                        "windows open, all of them may be muted."
                    ),
                    "type": "checkbox",
                    "default": True,
                },
                {
                    "key": "should-send-spacebar",
                    "label": "Send spacebar keypress to window",
                    "description": (
                        "Send a spacebar command to try to play the selected "
                        "window's media when commercials begin and pause it "
                        "when commercials end. Start with the media paused."
                    ),
                    "type": "checkbox",
                    "default": False,
                },
            ],
        },
        "meta": {
            "display": "Sending Manifest",
            "debug": "Sending Manifest",
        },
    }

    try:
        await websocket.send(json.dumps(manifest))
    except websockets.exceptions.ConnectionClosed:
        print("Could not send manifest because the client disconnected.")


async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"Server running on ws://localhost:{PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")