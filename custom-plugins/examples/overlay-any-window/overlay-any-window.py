import asyncio
import ctypes
import json
import time

import websockets
import win32api
import win32con
import win32gui
import win32process

from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

PLUGIN_PROTOCOL_VERSION = 1 # DO NOT TOUCH

PLUGIN_NAME = "Overlay Any Window"
PLUGIN_ID = "overlay-any-window" # Must be unique
PLUGIN_VERSION = "1.1.0"

PORT = 64146
SPACEBAR_KEY = 0x20
DWMWA_CLOAKED = 14
GA_ROOT = 2
FRONT_CHECK_ATTEMPTS = 5
FRONT_CHECK_DELAY_SECONDS = 0.1
FOCUS_MESSAGE_DISPLAY_MILLISECONDS = 12000

# Results of trying to show the overlay window in front of the browser.
WINDOW_IN_FRONT = "in_front"
WINDOW_IN_FRONT_BY_ACTIVATING = "in_front_by_activating"
WINDOW_NOT_IN_FRONT = "not_in_front"
# Note: WS_MINIMIZEBOX/WS_MAXIMIZEBOX are the title bar buttons.
# WS_MINIMIZE/WS_MAXIMIZE are the window's actual minimized/maximized state
# and must never be changed when adding or removing borders.
BORDER_STYLES = (
    win32con.WS_CAPTION
    | win32con.WS_THICKFRAME
    | win32con.WS_MINIMIZEBOX
    | win32con.WS_MAXIMIZEBOX
    | win32con.WS_SYSMENU
)

# The window found at init, so it can still be found if its title changes
# later (for example a media player showing the name of what is playing).
selected_window_title = None
selected_window_hwnd = None

# How the selected window looked before the plugin changed it, so it can be
# put back the same way. Some windows (like Firefox's Picture-in-Picture
# window) start always on top, and once that is removed their app won't let
# another program make them always on top again.
original_window_state = None

# The browser window that had keyboard focus before this plugin had to
# activate the overlay window, so focus can be given back once it is hidden.
focus_taken_from_window = None

# The lost-focus message is only shown the first time it happens each time
# the extension is started.
has_sent_focus_message = False


def is_window_cloaked(hwnd):
    """Return True for windows Windows reports as visible but hides from view.

    Windows 10 and 11 keep hidden "ghost" copies of many app windows, often
    with the same title as the real window.
    """
    cloaked = ctypes.c_int(0)
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd,
        DWMWA_CLOAKED,
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked),
    )
    return result == 0 and cloaked.value != 0


def get_window_dropdown_options():
    """Return visible titled windows as dropdown options."""
    window_titles = set()

    def enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or is_window_cloaked(hwnd):
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

    # Prefer a real window over a hidden ghost copy with the same title.
    for hwnd in matching_windows:
        if not is_window_cloaked(hwnd):
            return hwnd

    return matching_windows[0] if matching_windows else None


def find_selected_window(title):
    """Find the selected window, reusing the one found before if it still exists."""
    global selected_window_title
    global selected_window_hwnd

    if (
        title == selected_window_title
        and selected_window_hwnd
        and win32gui.IsWindow(selected_window_hwnd)
    ):
        return selected_window_hwnd

    hwnd = find_window_by_title(title)
    if hwnd:
        selected_window_title = title
        selected_window_hwnd = hwnd

    return hwnd


def remember_original_window_state(hwnd):
    """Save how the window looks before the plugin changes it."""
    global original_window_state

    # Keep the first state saved for this window until the extension stops,
    # so a second init doesn't save the plugin's own changes as "original".
    if original_window_state and original_window_state["hwnd"] == hwnd:
        return

    original_window_state = {
        "hwnd": hwnd,
        "is_topmost": is_window_topmost(hwnd),
        "rect": win32gui.GetWindowRect(hwnd),
        "style": win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE),
    }


def get_original_window_state(hwnd):
    """Return the saved original state for this window, if there is one."""
    if original_window_state and original_window_state["hwnd"] == hwnd:
        return original_window_state

    return None


def was_window_originally_topmost(hwnd):
    """Return True when the window was always on top before the plugin started."""
    state = get_original_window_state(hwnd)
    return bool(state and state["is_topmost"])


def forget_original_window_state():
    """Clear the saved state once the window has been put back."""
    global original_window_state
    original_window_state = None


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
    """Show, resize, position, and keep a window on top of the fullscreen browser.

    Returns WINDOW_IN_FRONT, WINDOW_IN_FRONT_BY_ACTIVATING (the browser lost
    keyboard focus), or WINDOW_NOT_IN_FRONT.
    """
    x, y, width, height = calculate_window_position(
        width_percent,
        height_percent,
        horizontal,
        vertical,
    )

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
        # Some apps finish restoring a moment later and can undo a position
        # that was set too early.
        time.sleep(0.15)

    # Check it actually ended up in front, since some apps move themselves
    # again right after being restored.
    for _ in range(FRONT_CHECK_ATTEMPTS):
        set_window_topmost(hwnd, x, y, width, height)
        time.sleep(FRONT_CHECK_DELAY_SECONDS)

        if is_window_in_front(hwnd):
            return WINDOW_IN_FRONT

        # Some windows won't accept always-on-top from another program (for
        # example a Firefox Picture-in-Picture window that already lost it),
        # so trying again won't help.
        if not is_window_topmost(hwnd):
            break

    # Last resort: make it the active window, which takes keyboard focus away
    # from the browser.
    activate_overlay_window(hwnd)
    set_window_topmost(hwnd, x, y, width, height)
    time.sleep(FRONT_CHECK_DELAY_SECONDS)

    if is_window_in_front(hwnd) or win32gui.GetForegroundWindow() == hwnd:
        print(
            "Window did not come to the front on its own, so it was activated "
            "instead (the browser gets keyboard focus back once the overlay is hidden)."
        )
        return WINDOW_IN_FRONT_BY_ACTIVATING

    print("Window could not be brought to the front, even by activating it.")
    return WINDOW_NOT_IN_FRONT


def set_window_topmost(hwnd, x, y, width, height):
    """Place a window above all normal windows without activating it."""
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,
        x,
        y,
        width,
        height,
        win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
    )


def is_window_topmost(hwnd):
    """Return True when a window is marked always on top."""
    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    return bool(ex_style & win32con.WS_EX_TOPMOST)


def is_window_in_front(hwnd):
    """Return True when the window is restored, topmost, and the one seen at its center."""
    if win32gui.IsIconic(hwnd):
        return False

    if not is_window_topmost(hwnd):
        return False

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    center = ((left + right) // 2, (top + bottom) // 2)

    try:
        window_at_center = win32gui.WindowFromPoint(center)
    except win32gui.error:
        return False

    if not window_at_center:
        return False

    # The point can land on one of the window's child controls.
    return ctypes.windll.user32.GetAncestor(window_at_center, GA_ROOT) == hwnd


def activate_window(hwnd):
    """Make a window the active window.

    Windows only lets the app currently in use change the active window, so
    this briefly shares input with that app (AttachThreadInput) to be allowed.
    """
    foreground_window = win32gui.GetForegroundWindow()
    current_thread = win32api.GetCurrentThreadId()
    foreground_thread = (
        win32process.GetWindowThreadProcessId(foreground_window)[0]
        if foreground_window
        else 0
    )

    is_attached = False
    try:
        if foreground_thread and foreground_thread != current_thread:
            win32process.AttachThreadInput(current_thread, foreground_thread, True)
            is_attached = True

        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except win32gui.error as error:
        print(f"Could not activate window: {error}")
    finally:
        if is_attached:
            win32process.AttachThreadInput(current_thread, foreground_thread, False)


def activate_overlay_window(hwnd):
    """Last resort to bring a window in front: make it the active window.

    Focus is not given straight back to the browser, because activating the
    browser would put it back on top of a window that won't stay always on
    top. Instead focus is returned once the overlay is hidden.
    """
    global focus_taken_from_window

    previous_foreground_window = win32gui.GetForegroundWindow()
    if (
        focus_taken_from_window is None
        and previous_foreground_window
        and previous_foreground_window != hwnd
    ):
        focus_taken_from_window = previous_foreground_window

    activate_window(hwnd)


def return_focus_to_browser():
    """Give keyboard focus back to the browser if this plugin took it."""
    global focus_taken_from_window

    window = focus_taken_from_window
    focus_taken_from_window = None

    if window and win32gui.IsWindow(window):
        activate_window(window)


def remove_topmost(hwnd, width_percent=90, height_percent=75):
    """Remove topmost status and place the window near the bottom of the stack.

    Windows that were always on top before the plugin started are put back
    where they were instead, still always on top.
    """
    state = get_original_window_state(hwnd)
    if state and state["is_topmost"]:
        left, top, right, bottom = state["rect"]
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            left,
            top,
            right - left,
            bottom - top,
            win32con.SWP_NOACTIVATE,
        )
        return

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
    # A maximized window can't be freely sized, so restore it to normal first.
    # Note: win32gui has no IsZoomed, so it is called from user32 directly.
    if win32gui.IsWindow(hwnd) and ctypes.windll.user32.IsZoomed(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)

    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style &= ~BORDER_STYLES

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

    # Only give back the border pieces the window had before, so windows
    # that never had a title bar (like Firefox's Picture-in-Picture window)
    # don't get one.
    state = get_original_window_state(hwnd)
    if state:
        style |= state["style"] & BORDER_STYLES
    else:
        style |= BORDER_STYLES

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
    plugin_preferences = preferences.get("pluginPreferencesById", {}).get(PLUGIN_ID, {}).get("preferences", {})

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
    return position_and_resize_window(
        hwnd,
        width_percent=settings["pip_width"],
        height_percent=settings["pip_height"],
        vertical=settings["pip_vertical"],
        horizontal=settings["pip_horizontal"],
    )


def show_overlay_window(hwnd, settings):
    """Show the selected window using the configured overlay size."""
    return position_and_resize_window(
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

    hwnd = find_selected_window(window_title)

    if hwnd is None:
        await send_status(
            websocket,
            f'Could not find "{window_title}"',
            f'Could not find a visible window titled "{window_title}".',
        )
        return

    if message_type == "init":
        reset_focus_message()
        remember_original_window_state(hwnd)
        make_borderless(hwnd)

        # For some reason running this at the begining helps the window come
        # forward later. Skipped for windows that are already always on top,
        # since removing it can't be undone for some (like Firefox's
        # Picture-in-Picture window) and they are already in front.
        if not was_window_originally_topmost(hwnd):
            remove_topmost(hwnd, width_percent=90, height_percent=85)

        time.sleep(0.5)

        if settings["is_pip_mode"]:
            result = show_pip_window(hwnd, settings)
            await report_window_front_result(websocket, result, window_title)
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
            result = show_overlay_window(hwnd, settings)
            await report_window_front_result(websocket, result, window_title)

            if settings["should_mute"]:
                mute_application_of_window(hwnd, mute=False)

            if settings["should_send_spacebar"]:
                time.sleep(0.5)
                send_spacebar(hwnd)

        else:
            print("Stopping overlay.")

            if settings["should_send_spacebar"]:
                send_spacebar(hwnd)
                time.sleep(0.4)

            if settings["should_mute"]:
                mute_application_of_window(hwnd, mute=True)

            if settings["is_pip_mode"]:
                result = show_pip_window(hwnd, settings)
                await report_window_front_result(websocket, result, window_title)
            else:
                minimize_window(hwnd)
                return_focus_to_browser()

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
                result = show_pip_window(hwnd, settings)
                await report_window_front_result(websocket, result, window_title)

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
        return_focus_to_browser()
        forget_original_window_state()
        return

    await send_status(
        websocket,
        "Unknown message",
        f'Unsupported message type: "{message_type}".',
    )


def reset_focus_message():
    """Allow the lost-focus message to be shown again (once per extension start)."""
    global has_sent_focus_message
    has_sent_focus_message = False


async def report_window_front_result(websocket, result, window_title):
    """Let the user know when the overlay window took focus or couldn't be shown on top."""
    global has_sent_focus_message

    if result == WINDOW_IN_FRONT_BY_ACTIVATING and not has_sent_focus_message:
        has_sent_focus_message = True
        await send_status(
            websocket,
            (
                f'To show "{window_title}" on top, Overlay Any Window had to make it '
                "the active window, so your browser lost keyboard focus. Click your "
                "browser to give it focus again (for example to use the keyboard "
                "shortcut). This may hide the overlay window."
            ),
            "The window would not stay always on top, so it was activated instead.",
            display_type="info",
            display_time=FOCUS_MESSAGE_DISPLAY_MILLISECONDS,
        )

    elif result == WINDOW_NOT_IN_FRONT:
        await send_status(
            websocket,
            (
                f'Overlay Any Window could not show "{window_title}" on top of your '
                "browser. Try closing and reopening that window, or choose a "
                "different one."
            ),
            "The window would not stay always on top and could not be activated.",
            display_type="error",
        )


async def send_status(websocket, display, debug, display_type=None, display_time=None):
    meta = {
        "display": display,
        "debug": debug,
    }

    # Optional: "info" shows blue and "error" shows red. The message
    # disappears after displayTime milliseconds (7 seconds if not sent).
    if display_type is not None:
        meta["displayType"] = display_type
    if display_time is not None:
        meta["displayTime"] = display_time

    message = {
        "type": "status",
        "timestamp": time.time(),
        "data": {},
        "meta": meta,
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
        "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
        "data": {
            "name": PLUGIN_NAME,
            "id": PLUGIN_ID,
            "version": PLUGIN_VERSION,
            "description": (
                "Overlay any window from any open application. This plugin uses the "
                "overlay and picture-in-picture size and location settings "
                "from the extension's additional settings."
            ),
            "primaryColor": "#ffffff",
            "secondaryColor": "#3b93d9",
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
                    "tooltip": (
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
                    "tooltip": (
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