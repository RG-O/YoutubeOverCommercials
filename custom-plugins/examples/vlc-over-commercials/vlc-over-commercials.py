
import os
import re
import subprocess
import time
from pathlib import Path

import requests
import win32api
import win32con
import win32gui
import win32process
from flask import Flask, jsonify, request


# -----------------------------------------------------------------------------
# Plugin information
# -----------------------------------------------------------------------------

PLUGIN_PROTOCOL_VERSION = 1  # DO NOT TOUCH

PLUGIN_NAME = "VLC Over Commercials"
PLUGIN_ID = "vlc-over-commercials"
PLUGIN_VERSION = "1.0.0"


# -----------------------------------------------------------------------------
# VLC settings
# -----------------------------------------------------------------------------

VLC_HTTP_URL = "http://localhost:8080/requests/status.json"
VLC_HTTP_PASSWORD = "1234"
VLC_HTTP_AUTH = ("", VLC_HTTP_PASSWORD)

DEFAULT_MEDIA_URL = "file:///C:/Users/user/Downloads/video.mp4"
DEFAULT_VOLUME = 256
FALLBACK_VOLUME = 205


# -----------------------------------------------------------------------------
# Runtime state
# -----------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

optimized_width_percentage = 90
optimized_height_percentage = 85
previous_overlay_width_percentage = 0
previous_overlay_height_percentage = 0

vlc_process = None
vlc_window_handle = None
original_foreground_window = None
is_original_foreground_window_topmost = False
is_setup_complete = False
saved_volume = DEFAULT_VOLUME


# -----------------------------------------------------------------------------
# General helpers
# -----------------------------------------------------------------------------


def find_main_window_for_process(process_id):
    """Return the first usable visible window owned by process_id."""
    matching_window = None

    def enum_handler(hwnd, _):
        nonlocal matching_window

        if matching_window is not None:
            return

        if not win32gui.IsWindowVisible(hwnd):
            return

        _, window_process_id = win32process.GetWindowThreadProcessId(hwnd)

        if window_process_id != process_id:
            return

        title = win32gui.GetWindowText(hwnd).strip()
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)

        width = right - left
        height = bottom - top

        if title and width > 0 and height > 0:
            matching_window = hwnd

    win32gui.EnumWindows(enum_handler, None)
    return matching_window


def wait_for_process_window(process_id, timeout=15):
    """Wait for the main window belonging to process_id."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        hwnd = find_main_window_for_process(process_id)
        if hwnd and win32gui.IsWindow(hwnd):
            return hwnd

        time.sleep(0.1)

    return None


def find_vlc_exe():
    """Find VLC in its usual Windows installation folders."""
    possible_paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None


def get_vlc_status(command=None, params=None, timeout=3):
    """Send a request to VLC and return its JSON response."""
    request_params = dict(params or {})

    if command:
        request_params["command"] = command

    response = requests.get(
        VLC_HTTP_URL,
        params=request_params,
        auth=VLC_HTTP_AUTH,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def send_vlc_command(command, params=None, timeout=3):
    """Send a command to VLC."""
    get_vlc_status(command=command, params=params, timeout=timeout)


def set_vlc_volume(volume):
    """Set VLC's volume."""
    send_vlc_command("volume", {"val": int(volume)})


def get_vlc_window():
    """Return the main window owned by the VLC process this script opened."""
    global vlc_window_handle

    if vlc_window_handle and win32gui.IsWindow(vlc_window_handle):
        return vlc_window_handle

    if vlc_process and vlc_process.poll() is None:
        vlc_window_handle = find_main_window_for_process(vlc_process.pid)
        return vlc_window_handle

    return None


def safely_minimize_window(hwnd):
    if hwnd and win32gui.IsWindow(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)


# -----------------------------------------------------------------------------
# VLC startup and media information
# -----------------------------------------------------------------------------


def open_vlc_with_media(media_url):
    """Start VLC and remember the main window owned by that process."""
    global vlc_process
    global vlc_window_handle

    vlc_path = find_vlc_exe()
    if not vlc_path:
        raise FileNotFoundError(
            "Could not find vlc.exe in Program Files or Program Files (x86)."
        )

    vlc_process = subprocess.Popen(
        [
            vlc_path,
            "--qt-start-minimized",
            "--qt-minimal-view",
            "--extraintf",
            "http",
            "--http-password",
            VLC_HTTP_PASSWORD,
            "--qt-continue=2",
            "--qt-notification=0",
            "--no-video-title-show",
            "--no-qt-privacy-ask",
            "--no-qt-error-dialogs",
            "--no-qt-updates-notif",
            "--no-one-instance",
            "--no-one-instance-when-started-from-file",
            "--loop",
        ]
    )

    print(f"Started VLC process with PID {vlc_process.pid}.")

    # VLC's HTTP server may need a moment to start.
    start_time = time.time()
    while time.time() - start_time < 10:
        try:
            send_vlc_command("in_play", {"input": media_url})
            break
        except requests.RequestException:
            time.sleep(0.25)
    else:
        vlc_process.terminate()
        vlc_process = None
        raise RuntimeError("VLC opened, but its HTTP interface did not respond.")

    vlc_window_handle = wait_for_process_window(vlc_process.pid)
    if not vlc_window_handle:
        vlc_process.terminate()
        vlc_process = None
        raise RuntimeError(
            "VLC started, but its main window could not be found."
        )

    title = win32gui.GetWindowText(vlc_window_handle)
    print(
        f"Using VLC window hwnd={vlc_window_handle}, title={title!r}."
    )


def get_vlc_video_dimensions():
    """Return the current video's width and height."""
    status = get_vlc_status()
    categories = status.get("information", {}).get("category", {})

    for stream_info in categories.values():
        if not isinstance(stream_info, dict):
            continue

        stream_type = str(stream_info.get("Type", "")).lower()
        if stream_type != "video":
            continue

        resolution = (
            stream_info.get("Video_resolution")
            or stream_info.get("Buffer_dimensions")
            or stream_info.get("Resolution")
        )

        if resolution:
            match = re.search(r"(\d+)\s*x\s*(\d+)", str(resolution))
            if match:
                return int(match.group(1)), int(match.group(2))

        width = stream_info.get("Width") or stream_info.get("width")
        height = stream_info.get("Height") or stream_info.get("height")

        if width and height:
            return int(width), int(height)

    return None


def wait_for_vlc_playing(timeout=60):
    """Wait until VLC is playing and has displayed at least one new frame."""
    start_time = time.time()
    last_displayed_count = None

    while time.time() - start_time < timeout:
        try:
            status = get_vlc_status()
        except requests.RequestException:
            time.sleep(0.2)
            continue

        if status.get("state") != "playing":
            time.sleep(0.2)
            continue

        displayed_count = status.get("stats", {}).get("displayedpictures", 0)

        if (
            last_displayed_count is not None
            and displayed_count > last_displayed_count
        ):
            return True

        last_displayed_count = displayed_count
        time.sleep(0.2)

    return False


def wait_for_setup_complete(timeout=30):
    """Wait until the init request has finished setting up VLC."""
    if is_setup_complete:
        return True

    start_time = time.time()

    while time.time() - start_time < timeout:
        if is_setup_complete:
            return True
        time.sleep(0.5)

    return False


def is_live_media(status):
    """Treat media without a known duration as a live stream."""
    length = status.get("length", 0)
    print(f"Media length: {length}")
    return not length or length <= 0


# -----------------------------------------------------------------------------
# Window sizing and styling
# -----------------------------------------------------------------------------


def calculate_largest_aspect_fit(max_width_percent=90, max_height_percent=75):
    """Fit the video inside a percentage-based box without stretching it."""
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    max_width_pixels = int(screen_width * max_width_percent / 100)
    max_height_pixels = int(screen_height * max_height_percent / 100)

    dimensions = get_vlc_video_dimensions()
    if not dimensions:
        return max_width_percent, max_height_percent

    video_width, video_height = dimensions
    video_aspect_ratio = video_width / video_height
    max_box_aspect_ratio = max_width_pixels / max_height_pixels

    if video_aspect_ratio > max_box_aspect_ratio:
        final_width_pixels = max_width_pixels
        final_height_pixels = int(final_width_pixels / video_aspect_ratio)
    else:
        final_height_pixels = max_height_pixels
        final_width_pixels = int(final_height_pixels * video_aspect_ratio)

    final_width_percent = final_width_pixels / screen_width * 100
    final_height_percent = final_height_pixels / screen_height * 100

    return final_width_percent, final_height_percent


def position_and_resize_window(
    hwnd,
    width_percent=90,
    height_percent=75,
    vertical="middle",
    horizontal="middle",
):
    """Show, position, resize, and keep a window above fullscreen apps."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return

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

    print(
        f"Positioning VLC: {target_width}x{target_height} at ({x}, {y})"
    )

    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,
        x,
        y,
        target_width,
        target_height,
        win32con.SWP_NOACTIVATE,
    )


def remove_topmost(hwnd, width_percent=90, height_percent=75):
    """Remove a window's topmost state and leave it centered."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return

    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    target_width = int(screen_width * width_percent / 100)
    target_height = int(screen_height * height_percent / 100)

    x = (screen_width - target_width) // 2
    y = (screen_height - target_height) // 2

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_NOTOPMOST,
        x,
        y,
        target_width,
        target_height,
        win32con.SWP_NOACTIVATE,
    )


def make_borderless(hwnd):
    """Remove the title bar and resize borders from a window."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return

    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style &= ~(
        win32con.WS_CAPTION
        | win32con.WS_THICKFRAME
        | win32con.WS_MINIMIZEBOX
        | win32con.WS_MAXIMIZEBOX
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
    if not hwnd or not win32gui.IsWindow(hwnd):
        return

    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style |= (
        win32con.WS_CAPTION
        | win32con.WS_THICKFRAME
        | win32con.WS_MINIMIZEBOX
        | win32con.WS_MAXIMIZEBOX
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
        win32con.SWP_FRAMECHANGED
        | win32con.SWP_NOMOVE
        | win32con.SWP_NOSIZE
        | win32con.SWP_NOZORDER,
    )


def close_window_by_hwnd(hwnd):
    """Ask a window to close, like clicking its X button."""
    if hwnd and win32gui.IsWindow(hwnd):
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)


def set_original_window_topmost(make_topmost):
    """Temporarily change the original foreground window's topmost state."""
    global is_original_foreground_window_topmost

    if not original_foreground_window:
        return

    insert_after = (
        win32con.HWND_TOPMOST if make_topmost else win32con.HWND_NOTOPMOST
    )

    win32gui.SetWindowPos(
        original_foreground_window,
        insert_after,
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE
        | win32con.SWP_NOSIZE
        | win32con.SWP_NOACTIVATE,
    )

    is_original_foreground_window_topmost = make_topmost


def hide_vlc_and_clear_taskbar(hwnd, make_original_topmost=True):
    """Use the original two-step minimize behavior for Windows 10 and 11."""
    safely_minimize_window(hwnd)
    time.sleep(0.2)
    position_and_resize_window(hwnd, width_percent=10, height_percent=10)
    time.sleep(0.2)
    safely_minimize_window(hwnd)
    time.sleep(0.2)

    if make_original_topmost and original_foreground_window:
        time.sleep(0.4)
        set_original_window_topmost(True)


# -----------------------------------------------------------------------------
# Plugin request handlers
# -----------------------------------------------------------------------------


def read_preferences(data):
    """Read and convert the preferences used by all request types."""
    preferences = data.get("data", {}).get("preferences", {})

    return {
        "overlay_width": float(preferences.get("videoOverlayWidth", 90)),
        "overlay_height": float(preferences.get("videoOverlayHeight", 75)),
        "overlay_horizontal": preferences.get(
            "overlayVideoLocationHorizontal", "middle"
        ),
        "overlay_vertical": preferences.get(
            "overlayVideoLocationVertical", "middle"
        ),
        "is_pip_mode": bool(preferences.get("isPiPMode", False)),
        "pip_width": float(preferences.get("pipWidth", 30)),
        "pip_height": float(preferences.get("pipHeight", 30)),
        "pip_horizontal": preferences.get("pipLocationHorizontal", "right"),
        "pip_vertical": preferences.get("pipLocationVertical", "bottom"),
        "raw": preferences,
    }


def show_commercial_overlay(hwnd, preferences):
    global optimized_width_percentage
    global optimized_height_percentage
    global previous_overlay_width_percentage
    global previous_overlay_height_percentage

    dimensions_changed = (
        preferences["overlay_width"] != previous_overlay_width_percentage
        or preferences["overlay_height"] != previous_overlay_height_percentage
    )

    previous_overlay_width_percentage = preferences["overlay_width"]
    previous_overlay_height_percentage = preferences["overlay_height"]

    if dimensions_changed:
        (
            optimized_width_percentage,
            optimized_height_percentage,
        ) = calculate_largest_aspect_fit(
            max_width_percent=preferences["overlay_width"],
            max_height_percent=preferences["overlay_height"],
        )

    position_and_resize_window(
        hwnd,
        width_percent=optimized_width_percentage,
        height_percent=optimized_height_percentage,
        vertical=preferences["overlay_vertical"],
        horizontal=preferences["overlay_horizontal"],
    )

    time.sleep(0.1)
    send_vlc_command("pl_forceresume")

    status = get_vlc_status()
    if is_live_media(status):
        set_vlc_volume(saved_volume)


def hide_commercial_overlay(hwnd, preferences):
    global saved_volume

    status = get_vlc_status()
    current_volume = int(status.get("volume", FALLBACK_VOLUME))
    saved_volume = current_volume or FALLBACK_VOLUME

    if not is_live_media(status):
        send_vlc_command("pl_forcepause")
        safely_minimize_window(hwnd)
        return

    set_vlc_volume(0)

    if preferences["is_pip_mode"]:
        pip_width, pip_height = calculate_largest_aspect_fit(
            max_width_percent=preferences["pip_width"],
            max_height_percent=preferences["pip_height"],
        )
        position_and_resize_window(
            hwnd,
            width_percent=pip_width,
            height_percent=pip_height,
            vertical=preferences["pip_vertical"],
            horizontal=preferences["pip_horizontal"],
        )
    else:
        safely_minimize_window(hwnd)


def initialize_plugin(preferences):
    global original_foreground_window
    global is_setup_complete
    global saved_volume

    is_setup_complete = False
    original_foreground_window = win32gui.GetForegroundWindow()

    if original_foreground_window:
        title = win32gui.GetWindowText(original_foreground_window)
        print(f"Original foreground window: {title}")

    plugin_preferences = (
        preferences["raw"]
        .get("pluginOverlayPreferences", {})
        .get("preferences", {})
    )
    media_url = plugin_preferences.get("url", DEFAULT_MEDIA_URL)

    open_vlc_with_media(media_url)

    print("Waiting for VLC to begin playing...")
    if not wait_for_vlc_playing():
        raise RuntimeError("VLC did not begin displaying video before timeout.")

    time.sleep(0.5)

    hwnd = get_vlc_window()
    if not hwnd:
        raise RuntimeError("VLC could not be opened.")

    make_borderless(hwnd)

    # Bring VLC forward briefly so the Windows taskbar appears now instead of
    # unexpectedly appearing later when the first commercial begins.
    time.sleep(0.2)
    position_and_resize_window(hwnd, width_percent=10, height_percent=10)
    time.sleep(0.2)

    status = get_vlc_status()
    current_volume = int(status.get("volume", FALLBACK_VOLUME))
    saved_volume = current_volume or FALLBACK_VOLUME

    if not is_live_media(status):
        send_vlc_command("pl_forcepause")
        time.sleep(0.2)
        hide_vlc_and_clear_taskbar(hwnd)
    else:
        set_vlc_volume(0)

        if preferences["is_pip_mode"]:
            pip_width, pip_height = calculate_largest_aspect_fit(
                max_width_percent=preferences["pip_width"],
                max_height_percent=preferences["pip_height"],
            )
            position_and_resize_window(
                hwnd,
                width_percent=pip_width,
                height_percent=pip_height,
                vertical=preferences["pip_vertical"],
                horizontal=preferences["pip_horizontal"],
            )
        else:
            hide_vlc_and_clear_taskbar(hwnd)

    is_setup_complete = True


def end_plugin():
    global vlc_process
    global vlc_window_handle
    global is_setup_complete

    if is_original_foreground_window_topmost:
        set_original_window_topmost(False)

    hwnd = get_vlc_window()
    remove_topmost(
        hwnd,
        width_percent=optimized_width_percentage,
        height_percent=optimized_height_percentage,
    )
    restore_borders(hwnd)

    try:
        status = get_vlc_status()
        if is_live_media(status):
            set_vlc_volume(saved_volume)

        send_vlc_command("pl_stop")
    except requests.RequestException as error:
        print(f"Could not send final command to VLC: {error}")

    close_window_by_hwnd(hwnd)

    if vlc_process and vlc_process.poll() is None:
        vlc_process.terminate()
        print("Terminated VLC process.")

    vlc_process = None
    vlc_window_handle = None
    is_setup_complete = False
    print("Extension stopped.")


# -----------------------------------------------------------------------------
# Flask API
# -----------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/custom-plugin-overlay-api", methods=["POST"])
def custom_plugin_overlay():
    try:
        data = request.get_json(silent=True) or {}
        request_type = data.get("type")
        preferences = read_preferences(data)

        print(f"Received request: {request_type}")

        if request_type == "commercial_state_change":
            if not wait_for_setup_complete():
                return jsonify(
                    {
                        "status": "error",
                        "message": "VLC setup did not complete before timeout.",
                    }
                ), 500

            hwnd = get_vlc_window()
            if not hwnd:
                return jsonify(
                    {"status": "error", "message": "Could not find VLC window."}
                ), 500

            is_commercial = bool(
                data.get("data", {}).get("isCommercialState", False)
            )

            if is_commercial:
                print("Starting overlay.")
                show_commercial_overlay(hwnd, preferences)
            else:
                print("Stopping overlay.")
                hide_commercial_overlay(hwnd, preferences)

        elif request_type == "browser_fullscreen_state_change":
            hwnd = get_vlc_window()
            is_fullscreen = bool(
                data.get("data", {}).get("isFullscreen", False)
            )

            if is_fullscreen:
                print("User entered browser fullscreen.")
                make_borderless(hwnd)
            else:
                print("User exited browser fullscreen.")

                if is_original_foreground_window_topmost:
                    set_original_window_topmost(False)

                safely_minimize_window(hwnd)
                time.sleep(0.1)
                remove_topmost(
                    hwnd,
                    width_percent=optimized_width_percentage,
                    height_percent=optimized_height_percentage,
                )
                restore_borders(hwnd)

        elif request_type == "init":
            initialize_plugin(preferences)
            return jsonify(
                {
                    "status": "info",
                    "message": (
                        "Message from VLC Over Commercials plugin: Success! "
                        "Click in this window to return focus and you are good to go!"
                    ),
                }
            )

        elif request_type == "end":
            end_plugin()

        else:
            return jsonify(
                {
                    "status": "error",
                    "message": f"Unknown request type: {request_type}",
                }
            ), 400

        return jsonify({"status": "ok"})

    except (requests.RequestException, RuntimeError, FileNotFoundError) as error:
        print(f"Plugin error: {error}")
        return jsonify({"status": "error", "message": str(error)}), 500
    except (KeyError, TypeError, ValueError) as error:
        print(f"Invalid request data: {error}")
        return jsonify(
            {"status": "error", "message": f"Invalid request data: {error}"}
        ), 400


@app.route("/plugin-manifest", methods=["GET"])
def plugin_manifest():
    return jsonify(
        {
            "type": "plugin_manifest",
            "timestamp": time.time(),
            "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
            "data": {
                "name": PLUGIN_NAME,
                "id": PLUGIN_ID,
                "version": PLUGIN_VERSION,
                "description": (
                    "Automatically plays VLC media over commercial breaks. "
                    "Install the latest VLC version and close VLC before "
                    "starting the plugin. Note: This plugin uses the overlay "
                    "and pip size and location settings in additional "
                    "settings above. VLC is a trademark of the VideoLAN "
                    "organization. This plugin is not affiliated with VLC or "
                    "VideoLAN."
                ),
                "primaryColor": "#E85E00",
                "secondaryColor": "#f2c7aa",
                "capabilities": ["overlay"],
                "preferences": [
                    {
                        "key": "url",
                        "label": "Video URL",
                        "description": (
                            "A show/movie stream URL, live-stream URL, or local "
                            "file URL. Local file URL format example: "
                            "file:///C:/Users/user/Downloads/video.mp4"
                        ),
                        "type": "text",
                        "default": (
                            "https://upload.wikimedia.org/wikipedia/commons/"
                            "8/88/Big_Buck_Bunny_alt.webm"
                        ),
                    }
                ],
            },
        }
    )


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})


if __name__ == "__main__":
    print("API running on http://localhost:64144")
    app.run(port=64144)