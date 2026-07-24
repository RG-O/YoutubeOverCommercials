"""VLC Over Commercials plugin.

Runs a small Flask API used by the browser extension to show VLC during
commercial breaks. The script controls VLC through its HTTP interface and
manages the VLC window through the Windows API.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
import win32api
import win32con
import win32gui
import win32process
from flask import Flask, jsonify, request


# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------

PLUGIN_PROTOCOL_VERSION = 1  # DO NOT TOUCH
PLUGIN_NAME = "VLC Over Commercials"
PLUGIN_ID = "vlc-over-commercials"
PLUGIN_VERSION = "1.0.0"

API_HOST = "127.0.0.1"
API_PORT = 64144
VLC_HTTP_HOST = "127.0.0.1"
VLC_HTTP_PORT = 8080
VLC_HTTP_PASSWORD = "1234"
VLC_WINDOW_TITLE = "VLC"

DEFAULT_OVERLAY_WIDTH = 90.0
DEFAULT_OVERLAY_HEIGHT = 85.0
DEFAULT_VOLUME = 205
SMALL_WINDOW_PERCENT = 10.0

HTTP_TIMEOUT_SECONDS = 3.0
VLC_START_TIMEOUT_SECONDS = 60.0
SETUP_TIMEOUT_SECONDS = 30.0

VLC_STATUS_URL = (
    f"http://{VLC_HTTP_HOST}:{VLC_HTTP_PORT}/requests/status.json"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
LOGGER = logging.getLogger(__name__)

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowLayout:
    """Window size and placement expressed as screen percentages."""

    width_percent: float
    height_percent: float
    horizontal: str = "middle"
    vertical: str = "middle"


@dataclass(frozen=True)
class RequestPreferences:
    """Relevant preferences supplied by the extension."""

    overlay: WindowLayout
    pip_enabled: bool
    pip: WindowLayout

    @classmethod
    def from_payload(cls, preferences: dict[str, Any]) -> "RequestPreferences":
        return cls(
            overlay=WindowLayout(
                width_percent=float(preferences.get("videoOverlayWidth", 90)),
                height_percent=float(preferences.get("videoOverlayHeight", 75)),
                horizontal=str(
                    preferences.get("overlayVideoLocationHorizontal", "middle")
                ),
                vertical=str(
                    preferences.get("overlayVideoLocationVertical", "middle")
                ),
            ),
            pip_enabled=as_bool(preferences.get("isPiPMode", False)),
            pip=WindowLayout(
                width_percent=float(preferences.get("pipWidth", 25)),
                height_percent=float(preferences.get("pipHeight", 25)),
                horizontal=str(preferences.get("pipLocationHorizontal", "right")),
                vertical=str(preferences.get("pipLocationVertical", "bottom")),
            ),
        )


@dataclass
class PluginState:
    """Mutable state shared across extension API requests."""

    vlc_process: subprocess.Popen[Any] | None = None
    vlc_hwnd: int | None = None
    original_foreground_window: int | None = None
    original_foreground_window_is_topmost: bool = False
    setup_complete: bool = False
    saved_volume: int = DEFAULT_VOLUME
    optimized_overlay_width: float = DEFAULT_OVERLAY_WIDTH
    optimized_overlay_height: float = DEFAULT_OVERLAY_HEIGHT
    previous_overlay_width: float | None = None
    previous_overlay_height: float | None = None
    session: requests.Session = field(default_factory=requests.Session)


STATE = PluginState()


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------


def as_bool(value: Any) -> bool:
    """Convert common JSON/string values to a reliable boolean."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def get_screen_size() -> tuple[int, int]:
    return win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)


def find_main_window_for_process(
    process: subprocess.Popen[Any] | None,
    timeout: float = 15.0,
) -> int | None:
    """Find the main visible top-level window owned by process.

    This prevents the plugin from accidentally selecting a window belonging
    to another VLC instance merely because its title contains "VLC".
    """

    if process is None:
        return None

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        matches: list[tuple[int, str]] = []

        def enum_handler(hwnd: int, _: Any) -> None:
            if not win32gui.IsWindow(hwnd):
                return

            _, window_process_id = win32process.GetWindowThreadProcessId(hwnd)
            if window_process_id != process.pid:
                return

            if not win32gui.IsWindowVisible(hwnd):
                return

            # Ignore child windows and owned helper/dialog windows.
            if win32gui.GetParent(hwnd):
                return
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                return

            extended_style = win32gui.GetWindowLong(
                hwnd,
                win32con.GWL_EXSTYLE,
            )
            if extended_style & win32con.WS_EX_TOOLWINDOW:
                return

            matches.append((hwnd, win32gui.GetWindowText(hwnd).strip()))

        win32gui.EnumWindows(enum_handler, None)

        if matches:
            # VLC may briefly create more than one top-level Qt window. Prefer
            # the titled VLC window, then fall back to the first valid match.
            for hwnd, title in matches:
                if "vlc" in title.lower():
                    LOGGER.info(
                        "Matched VLC window %s to process ID %s: %s",
                        hwnd,
                        process.pid,
                        title,
                    )
                    return hwnd

            hwnd, title = matches[0]
            LOGGER.info(
                "Matched window %s to VLC process ID %s: %s",
                hwnd,
                process.pid,
                title or "<untitled>",
            )
            return hwnd

        if process.poll() is not None:
            LOGGER.error(
                "VLC process ID %s exited before its main window appeared.", #TODO: update this message because this isn't always the case?
                process.pid,
            )
            return None

        time.sleep(0.1)

    LOGGER.error(
        "Could not find a main window for VLC process ID %s.",
        process.pid,
    )
    return None


def get_vlc_window() -> int | None:
    """Return only the cached window belonging to this plugin's VLC process."""

    if STATE.vlc_hwnd and win32gui.IsWindow(STATE.vlc_hwnd):
        return STATE.vlc_hwnd

    # Do not fall back to a title search because that could select a different
    # VLC instance. Re-resolve the window from the process launched by us.
    STATE.vlc_hwnd = find_main_window_for_process(STATE.vlc_process, timeout=2.0)
    return STATE.vlc_hwnd


def require_vlc_window() -> int:
    hwnd = get_vlc_window()
    if not hwnd:
        raise RuntimeError("The VLC window could not be found.")
    return hwnd


def find_vlc_executable() -> Path:
    """Locate VLC in the standard 64-bit or 32-bit installation folders."""

    candidates = (
        Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe"),
        Path(r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"),
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        "Could not find vlc.exe. Install VLC in Program Files or Program Files (x86)."
    )


# ---------------------------------------------------------------------------
# VLC HTTP helpers
# ---------------------------------------------------------------------------


def vlc_request(
    command: str | None = None,
    *,
    timeout: float = HTTP_TIMEOUT_SECONDS,
    **params: Any,
) -> dict[str, Any]:
    """Call VLC's HTTP status endpoint and return its JSON response."""

    if command:
        params["command"] = command

    response = STATE.session.get(
        VLC_STATUS_URL,
        params=params or None,
        auth=("", VLC_HTTP_PASSWORD),
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def wait_for_vlc_http(timeout: float = 15.0) -> bool:
    """Wait until VLC's HTTP interface begins accepting requests."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            vlc_request(timeout=1.0)
            return True
        except (requests.RequestException, ValueError):
            time.sleep(0.2)
    return False


def open_vlc(media_url: str) -> None:
    """Start an isolated VLC instance and begin playing media_url."""

    vlc_path = find_vlc_executable()

    command = [
        str(vlc_path),
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

    LOGGER.info("Starting VLC: %s", vlc_path)
    STATE.vlc_process = subprocess.Popen(command)

    if not wait_for_vlc_http():
        raise RuntimeError("VLC started, but its HTTP interface did not become ready.")

    vlc_request("in_play", input=media_url)


def wait_for_vlc_playing(timeout: float = VLC_START_TIMEOUT_SECONDS) -> bool:
    """Wait until VLC is playing and has rendered at least one new frame."""

    deadline = time.monotonic() + timeout
    last_displayed: int | None = None

    while time.monotonic() < deadline:
        try:
            status = vlc_request(timeout=1.0)
        except (requests.RequestException, ValueError):
            time.sleep(0.2)
            continue

        if status.get("state") != "playing":
            time.sleep(0.2)
            continue

        displayed = int(status.get("stats", {}).get("displayedpictures", 0) or 0)
        if last_displayed is not None and displayed > last_displayed:
            return True

        last_displayed = displayed
        time.sleep(0.2)

    return False


def get_vlc_video_dimensions() -> tuple[int, int] | None:
    """Read the active video's width and height from VLC status data."""

    status = vlc_request()
    categories = status.get("information", {}).get("category", {})

    for stream_info in categories.values():
        if not isinstance(stream_info, dict):
            continue
        if str(stream_info.get("Type", "")).lower() != "video":
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


def is_live_media(status: dict[str, Any]) -> bool:
    """Treat media with no known positive duration as a live stream."""

    try:
        length = float(status.get("length", 0) or 0)
    except (TypeError, ValueError):
        length = 0

    return length <= 0


def read_and_store_volume(status: dict[str, Any] | None = None) -> int:
    """Remember VLC's current nonzero volume for later restoration."""

    status = status or vlc_request()
    try:
        volume = int(status.get("volume", DEFAULT_VOLUME))
    except (TypeError, ValueError):
        volume = DEFAULT_VOLUME

    if volume > 0:
        STATE.saved_volume = volume

    return STATE.saved_volume


def set_vlc_volume(volume: int) -> None:
    vlc_request("volume", val=int(volume))


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------


def calculate_largest_aspect_fit(
    max_width_percent: float,
    max_height_percent: float,
) -> tuple[float, float]:
    """Fit the video inside the requested screen-percentage bounding box."""

    screen_width, screen_height = get_screen_size()
    dimensions = get_vlc_video_dimensions()

    if not dimensions:
        LOGGER.warning(
            "VLC did not report video dimensions; using requested dimensions."
        )
        return max_width_percent, max_height_percent

    video_width, video_height = dimensions
    if video_width <= 0 or video_height <= 0:
        return max_width_percent, max_height_percent

    max_width_px = max(1, int(screen_width * max_width_percent / 100))
    max_height_px = max(1, int(screen_height * max_height_percent / 100))

    video_aspect = video_width / video_height
    box_aspect = max_width_px / max_height_px

    if video_aspect > box_aspect:
        final_width_px = max_width_px
        final_height_px = int(final_width_px / video_aspect)
    else:
        final_height_px = max_height_px
        final_width_px = int(final_height_px * video_aspect)

    return (
        final_width_px / screen_width * 100,
        final_height_px / screen_height * 100,
    )


def calculate_window_position(
    target_width: int,
    target_height: int,
    horizontal: str,
    vertical: str,
) -> tuple[int, int]:
    screen_width, screen_height = get_screen_size()

    horizontal = horizontal.lower()
    vertical = vertical.lower()

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

    return max(0, x), max(0, y)


def position_and_resize_window(hwnd: int, layout: WindowLayout) -> None:
    """Show VLC without activation, size it, position it, and make it topmost."""

    if not hwnd or not win32gui.IsWindow(hwnd):
        raise RuntimeError("Cannot position VLC because its window is unavailable.")

    screen_width, screen_height = get_screen_size()
    target_width = max(1, int(screen_width * layout.width_percent / 100))
    target_height = max(1, int(screen_height * layout.height_percent / 100))
    x, y = calculate_window_position(
        target_width,
        target_height,
        layout.horizontal,
        layout.vertical,
    )

    LOGGER.info(
        "Positioning VLC at (%s, %s), size %sx%s, placement %s/%s",
        x,
        y,
        target_width,
        target_height,
        layout.horizontal,
        layout.vertical,
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


def remove_topmost(hwnd: int) -> None:
    """Remove VLC's topmost status without changing its size or position."""

    if not hwnd or not win32gui.IsWindow(hwnd):
        return

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_NOTOPMOST,
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE
        | win32con.SWP_NOSIZE
        | win32con.SWP_NOACTIVATE,
    )


def minimize_window(hwnd: int | None) -> None:
    if hwnd and win32gui.IsWindow(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)


def make_borderless(hwnd: int) -> None:
    if not hwnd or not win32gui.IsWindow(hwnd):
        return

    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style &= ~(
        win32con.WS_CAPTION
        | win32con.WS_THICKFRAME
        | win32con.WS_MINIMIZE
        | win32con.WS_MAXIMIZE
        | win32con.WS_SYSMENU
    )
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    refresh_window_frame(hwnd)


def restore_borders(hwnd: int) -> None:
    if not hwnd or not win32gui.IsWindow(hwnd):
        return

    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style |= (
        win32con.WS_CAPTION
        | win32con.WS_THICKFRAME
        | win32con.WS_MINIMIZE
        | win32con.WS_MAXIMIZE
        | win32con.WS_SYSMENU
    )
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    refresh_window_frame(hwnd)


def refresh_window_frame(hwnd: int) -> None:
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
        | win32con.SWP_NOACTIVATE
        | win32con.SWP_FRAMECHANGED,
    )


def close_window_by_hwnd(hwnd: int | None) -> None:
    if hwnd and win32gui.IsWindow(hwnd):
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)


def set_original_window_topmost() -> None:
    hwnd = STATE.original_foreground_window
    if not hwnd or not win32gui.IsWindow(hwnd):
        return

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE
        | win32con.SWP_NOSIZE
        | win32con.SWP_NOOWNERZORDER,
    )
    STATE.original_foreground_window_is_topmost = True


def restore_original_window_z_order() -> None:
    hwnd = STATE.original_foreground_window
    if not STATE.original_foreground_window_is_topmost:
        return

    if hwnd and win32gui.IsWindow(hwnd):
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_NOTOPMOST,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE
            | win32con.SWP_NOSIZE
            | win32con.SWP_NOACTIVATE,
        )

    STATE.original_foreground_window_is_topmost = False


def clear_taskbar_side_effect(hwnd: int, restore_foreground: bool = True) -> None:
    """Preserve the original two-pass workaround for Windows 10/11 taskbar popups."""

    small_layout = WindowLayout(SMALL_WINDOW_PERCENT, SMALL_WINDOW_PERCENT)
    minimize_window(hwnd)
    time.sleep(0.2)
    position_and_resize_window(hwnd, small_layout)
    time.sleep(0.2)
    minimize_window(hwnd)
    time.sleep(0.2)

    if restore_foreground and STATE.original_foreground_window:
        time.sleep(0.4)
        set_original_window_topmost()


# ---------------------------------------------------------------------------
# Plugin behavior
# ---------------------------------------------------------------------------


def wait_for_setup_complete(timeout: float = SETUP_TIMEOUT_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if STATE.setup_complete:
            return True
        time.sleep(0.2)
    return STATE.setup_complete


def optimized_layout(layout: WindowLayout) -> WindowLayout:
    width, height = calculate_largest_aspect_fit(
        layout.width_percent,
        layout.height_percent,
    )
    return WindowLayout(width, height, layout.horizontal, layout.vertical)


def get_overlay_layout(preferences: RequestPreferences) -> WindowLayout:
    """Return a cached aspect-correct overlay layout."""

    width_changed = (
        preferences.overlay.width_percent != STATE.previous_overlay_width
    )
    height_changed = (
        preferences.overlay.height_percent != STATE.previous_overlay_height
    )

    if width_changed or height_changed:
        (
            STATE.optimized_overlay_width,
            STATE.optimized_overlay_height,
        ) = calculate_largest_aspect_fit(
            preferences.overlay.width_percent,
            preferences.overlay.height_percent,
        )
        STATE.previous_overlay_width = preferences.overlay.width_percent
        STATE.previous_overlay_height = preferences.overlay.height_percent

    return WindowLayout(
        STATE.optimized_overlay_width,
        STATE.optimized_overlay_height,
        preferences.overlay.horizontal,
        preferences.overlay.vertical,
    )


def handle_commercial_state_change(
    payload: dict[str, Any],
    preferences: RequestPreferences,
) -> None:
    if not wait_for_setup_complete():
        raise RuntimeError("VLC setup did not complete before the timeout.")

    hwnd = require_vlc_window()
    is_commercial = as_bool(payload.get("isCommercialState"))

    if is_commercial:
        LOGGER.info("Starting VLC overlay")
        position_and_resize_window(hwnd, get_overlay_layout(preferences))
        time.sleep(0.1)
        vlc_request("pl_forceresume")

        status = vlc_request()
        if is_live_media(status):
            set_vlc_volume(STATE.saved_volume)
        return

    LOGGER.info("Stopping VLC overlay")
    status = vlc_request()
    read_and_store_volume(status)

    if is_live_media(status):
        set_vlc_volume(0)
        if preferences.pip_enabled:
            position_and_resize_window(hwnd, optimized_layout(preferences.pip))
        else:
            minimize_window(hwnd)
    else:
        vlc_request("pl_forcepause")
        minimize_window(hwnd)


def handle_fullscreen_state_change(
    payload: dict[str, Any],
    preferences: RequestPreferences,
) -> None:
    hwnd = require_vlc_window()
    is_fullscreen = as_bool(payload.get("isFullscreen"))

    if is_fullscreen:
        LOGGER.info("Browser entered fullscreen")
        make_borderless(hwnd)

        status = vlc_request()
        read_and_store_volume(status)

        if is_live_media(status):
            set_vlc_volume(0)
            if preferences.pip_enabled:
                LOGGER.info("Setting VLC back to PiP")
                position_and_resize_window(hwnd, optimized_layout(preferences.pip))

        return

    LOGGER.info("Browser exited fullscreen")
    restore_original_window_z_order()
    minimize_window(hwnd)
    time.sleep(0.1)
    remove_topmost(hwnd)
    restore_borders(hwnd)


def get_media_url(preferences: dict[str, Any]) -> str:
    """Extract the plugin's URL preference from the init payload."""

    plugin_preferences = preferences.get("pluginOverlayPreferences", {})
    values = plugin_preferences.get("preferences", {})
    media_url = str(values.get("url", "")).strip()
    if not media_url:
        raise ValueError("The VLC media URL preference is empty.")
    return media_url


def handle_init(
    raw_preferences: dict[str, Any],
    preferences: RequestPreferences,
) -> dict[str, str]:
    STATE.setup_complete = False
    STATE.original_foreground_window = win32gui.GetForegroundWindow()

    if STATE.original_foreground_window:
        LOGGER.info(
            "Original foreground window: %s",
            win32gui.GetWindowText(STATE.original_foreground_window),
        )

    open_vlc(get_media_url(raw_preferences))

    if not wait_for_vlc_playing():
        raise RuntimeError("VLC did not begin rendering video before the timeout.")

    # Capture the main window belonging specifically to the VLC process that
    # this plugin launched.
    STATE.vlc_hwnd = find_main_window_for_process(STATE.vlc_process)
    hwnd = STATE.vlc_hwnd

    if not hwnd:
        raise RuntimeError(
            "VLC began playing, but the window belonging to the launched "
            "VLC process could not be found."
        )

    make_borderless(hwnd)
    time.sleep(0.2)

    # Bring VLC forward briefly so Windows handles the taskbar transition now,
    # rather than when the first commercial starts.
    position_and_resize_window(
        hwnd,
        WindowLayout(SMALL_WINDOW_PERCENT, SMALL_WINDOW_PERCENT),
    )
    time.sleep(0.2)

    status = vlc_request()
    read_and_store_volume(status)

    if is_live_media(status):
        set_vlc_volume(0)
        if preferences.pip_enabled:
            position_and_resize_window(hwnd, optimized_layout(preferences.pip))
        else:
            clear_taskbar_side_effect(hwnd)
    else:
        vlc_request("pl_forcepause")
        clear_taskbar_side_effect(hwnd)

    STATE.setup_complete = True
    return {
        "status": "info",
        "message": (
            "Message from VLC Over Commercials plugin: Success! "
            "Click in this window to return focus and you are good to go!"
        ),
    }


def handle_end() -> None:
    STATE.setup_complete = False
    restore_original_window_z_order()

    hwnd = get_vlc_window()
    if hwnd:
        remove_topmost(hwnd)
        restore_borders(hwnd)

    try:
        status = vlc_request()
        if is_live_media(status):
            set_vlc_volume(STATE.saved_volume)
        vlc_request("pl_stop")
    except (requests.RequestException, ValueError) as exc:
        LOGGER.warning("Could not fully stop VLC through its HTTP API: %s", exc)

    close_window_by_hwnd(hwnd)

    process = STATE.vlc_process
    if process and process.poll() is None:
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.kill()

    STATE.vlc_process = None
    STATE.vlc_hwnd = None
    LOGGER.info("Extension stopped")


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------


@app.route("/custom-plugin-overlay-api", methods=["POST"])
def custom_plugin_overlay():
    try:
        body = request.get_json(silent=False)
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")

        request_type = str(body.get("type", "")).strip()
        payload = body.get("data", {})
        if not isinstance(payload, dict):
            raise ValueError("The request data field must be an object.")

        raw_preferences = payload.get("preferences", {})
        if not isinstance(raw_preferences, dict):
            raw_preferences = {}

        preferences = RequestPreferences.from_payload(raw_preferences)
        LOGGER.info("Received request type: %s", request_type)

        if request_type == "commercial_state_change":
            handle_commercial_state_change(payload, preferences)
        elif request_type == "browser_fullscreen_state_change":
            handle_fullscreen_state_change(payload, preferences)
        elif request_type == "init":
            return jsonify(handle_init(raw_preferences, preferences))
        elif request_type == "end":
            handle_end()
        else:
            return jsonify(
                {
                    "status": "error",
                    "message": f"Unsupported request type: {request_type!r}",
                }
            ), 400

        return jsonify({"status": "ok"})

    except (KeyError, TypeError, ValueError) as exc:
        LOGGER.warning("Invalid plugin request: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 400
    except (requests.RequestException, OSError, RuntimeError) as exc:
        LOGGER.exception("Plugin request failed")
        return jsonify({"status": "error", "message": str(exc)}), 500


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
                            "file URL, such as "
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
    LOGGER.info("API running on http://localhost:%s", API_PORT)
    app.run(host=API_HOST, port=API_PORT, threaded=True)