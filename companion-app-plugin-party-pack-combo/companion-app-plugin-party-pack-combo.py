# Official Plugin Party Pack - Combined Server
#
# This single script contains:
#   * Advanced Logo Analyzer Flask service on port 64143
#   * Official Plugin Party Pack WebSocket service on port 64147
#
# Each bundled plugin is included below as normal Python code with a unique
# prefix for its globals/functions. This keeps plugin state independent while
# allowing PyInstaller to discover imports normally. Plugin *activation* stays
# lazy: cameras, microphones, Ollama work, VLC, etc. start only when enabled.

import asyncio
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

import websockets
import pystray
from PIL import Image, ImageDraw

PLUGIN_PROTOCOL_VERSION = 1
BUNDLE_NAME = "Official Plugin Party Pack"
BUNDLE_ID = "official-plugin-party-pack"
BUNDLE_VERSION = "1.0.0"
PARTY_PACK_PORT = 64147
LOGO_ANALYZER_PORT = 64143

# APP_DIR is the permanent folder containing the executable (or this .py file
# when running from source). Store downloaded models and other persistent files
# here so they survive between launches.
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

# RESOURCE_DIR is where read-only files bundled by PyInstaller are extracted.
# In a normal Python run it is the same folder as the script.
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

# Backwards-compatible name for any outer code that still expects SCRIPT_DIR.
SCRIPT_DIR = APP_DIR

# Runtime state is kept per browser WebSocket connection.
client_states = {}
loaded_plugins = {}
party_pack_loop = None
party_pack_shutdown_event = None
shutdown_requested = threading.Event()

PLUGIN_DEFINITIONS = {
    "ntfy-commercial-notifications": {
        "source_key": "ntfy",
        "name": "Commercial Push Notifications",
        "version": "1.0.0",
        "description": "Sends ntfy notifications when commercial breaks start and end.",
        "capabilities": ["overlay"],
        "adapter": "standard_ws",
    },
    "ai-commercial-detector-ws": {
        "source_key": "ai",
        "name": "AI Commercial Detector",
        "version": "1.8.1",
        "description": "Uses a local Ollama vision model to detect transitions into and out of commercials.",
        "capabilities": ["trigger"],
        "adapter": "ai_ws",
    },
    "overlay-any-window": {
        "source_key": "window",
        "name": "Overlay Any Window",
        "version": "1.1.0",
        "description": "Uses any visible Windows application window as the commercial overlay.",
        "capabilities": ["overlay"],
        "adapter": "standard_ws",
    },
    "speak-keyword-trigger-plugin": {
        "source_key": "voice",
        "name": "Say NO to Commercials",
        "version": "1.0.1",
        "description": "Uses offline Vosk speech recognition to trigger commercial/content state changes.",
        "capabilities": ["trigger"],
        "adapter": "standard_ws",
    },
    "gesture-trigger-plugin": {
        "source_key": "gesture",
        "name": "Peace Out Commercials",
        "version": "1.1.0",
        "description": "Uses MediaPipe hand gestures to trigger commercial/content state changes.",
        "capabilities": ["trigger"],
        "adapter": "standard_ws",
    },
    "vlc-over-commercials": {
        "source_key": "vlc",
        "name": "VLC Over Commercials",
        "version": "1.0.1",
        "description": "Automatically plays VLC media over commercial breaks.",
        "capabilities": ["overlay"],
        "adapter": "standard_ws",
    },
}


class PluginSocketProxy:
    """Give one bundled plugin a WebSocket-like object tied to its plugin ID."""

    def __init__(self, websocket, plugin_id):
        self.websocket = websocket
        self.plugin_id = plugin_id

    async def send(self, raw_message):
        """Add Party Pack metadata and safely forward a plugin message."""
        try:
            if isinstance(raw_message, bytes):
                await self.websocket.send(raw_message)
                return

            message = json.loads(raw_message) if isinstance(raw_message, str) else raw_message
            if not isinstance(message, dict):
                await self.websocket.send(raw_message)
                return

            message.setdefault("pluginProtocolVersion", PLUGIN_PROTOCOL_VERSION)
            data = message.setdefault("data", {})
            if not isinstance(data, dict):
                data = {}
                message["data"] = data
            data.setdefault("pluginId", self.plugin_id)

            # Trigger plugins are only allowed to request a commercial-state
            # change while they are actually enabled as triggers.
            if message.get("type") == "commercial_state_change":
                state = client_states.get(self.websocket, {})
                if self.plugin_id not in state.get("triggerPluginIds", []):
                    return

            # Trigger/dual status displays are persistent corner indicators in
            # the extension, so display timing/type is intentionally omitted.
            if message.get("type") == "status":
                capabilities = PLUGIN_DEFINITIONS[self.plugin_id]["capabilities"]
                meta = message.setdefault("meta", {})
                if "trigger" in capabilities:
                    meta.pop("displayTime", None)
                    meta.pop("displayType", None)

            await self.websocket.send(json.dumps(message))

        except websockets.exceptions.ConnectionClosed:
            return
        except Exception:
            # A malformed outgoing plugin message must not take down the pack.
            await safe_send_status(
                self.websocket,
                self.plugin_id,
                "Plugin could not send a message",
                traceback.format_exc(),
            )


async def safe_send_status(websocket, plugin_id, display, debug, display_type="error", display_time=7000):
    """Party Pack error boundary: simple display, complete details in debug."""
    capabilities = PLUGIN_DEFINITIONS.get(plugin_id, {}).get("capabilities", [])
    meta = {"display": str(display), "debug": str(debug)}
    if "overlay" in capabilities and "trigger" not in capabilities:
        meta["displayType"] = display_type
        meta["displayTime"] = display_time

    message = {
        "type": "status",
        "timestamp": time.time(),
        "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
        "data": {"pluginId": plugin_id},
        "meta": meta,
    }
    try:
        await websocket.send(json.dumps(message))
    except Exception:
        # There is nothing useful left to do if the browser itself is gone.
        pass


def full_error(prefix=None):
    details = traceback.format_exc()
    return f"{prefix}\n\n{details}" if prefix else details


class PluginRuntime:
    """Small module-like view over one plugin's prefixed globals/functions.

    The plugin code itself is normal Python below; this adapter only lets the
    existing Party Pack dispatcher keep its clean module-style calls.
    """

    def __init__(self, prefix):
        object.__setattr__(self, "prefix", prefix)

    def __getattr__(self, name):
        key = f"{self.prefix}{name}"
        if key not in globals():
            raise AttributeError(name)
        return globals()[key]

    def __setattr__(self, name, value):
        if name == "prefix":
            object.__setattr__(self, name, value)
            return
        globals()[f"{self.prefix}{name}"] = value


async def get_plugin_module(websocket, plugin_id):
    """Return the already-imported plugin runtime.

    Code loading is no longer lazy or dynamic. Only plugin activation is lazy.
    """
    module = loaded_plugins.get(plugin_id)
    if module is not None:
        return module

    await safe_send_status(
        websocket,
        plugin_id,
        "Unknown bundled plugin",
        f"No runtime exists for bundled plugin ID: {plugin_id}",
    )
    return None


def configure_client_from_init(websocket, preferences):
    preferences = preferences if isinstance(preferences, dict) else {}
    party_pack = preferences.get("officialPluginPartyPack", {})
    if not isinstance(party_pack, dict):
        party_pack = {}

    trigger_ids = validate_enabled_ids(party_pack.get("triggerPluginIds", []), "trigger")
    overlay_ids = validate_enabled_ids(party_pack.get("overlayPluginIds", []), "overlay")

    previous = client_states.get(websocket, {})
    client_states[websocket] = {
        "triggerPluginIds": trigger_ids,
        "overlayPluginIds": overlay_ids,
        "pluginPreferencesById": preferences.get("pluginPreferencesById", {}),
        "previousEnabledPluginIds": get_enabled_ids_from_state(previous),
    }


def validate_enabled_ids(plugin_ids, capability):
    if not isinstance(plugin_ids, list):
        return []
    result = []
    for plugin_id in plugin_ids:
        definition = PLUGIN_DEFINITIONS.get(plugin_id)
        if definition and capability in definition["capabilities"] and plugin_id not in result:
            result.append(plugin_id)
    return result


def get_enabled_ids_from_state(state):
    if not isinstance(state, dict):
        return []
    return list(dict.fromkeys(state.get("triggerPluginIds", []) + state.get("overlayPluginIds", [])))


def get_enabled_plugin_ids(websocket):
    return get_enabled_ids_from_state(client_states.get(websocket, {}))


async def send_bundle_manifest(websocket):
    plugins = []
    for plugin_id, definition in PLUGIN_DEFINITIONS.items():
        plugins.append({
            "name": definition["name"],
            "id": plugin_id,
            "version": definition["version"],
            "description": definition["description"],
            "capabilities": definition["capabilities"],
        })

    try:
        await websocket.send(json.dumps({
            "type": "plugin_bundle_manifest",
            "timestamp": time.time(),
            "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
            "data": {
                "name": BUNDLE_NAME,
                "id": BUNDLE_ID,
                "version": BUNDLE_VERSION,
                "plugins": plugins,
            },
            "meta": {
                "display": "Sending Party Pack Manifest",
                "debug": "Sending Party Pack Manifest",
            },
        }))
    except Exception:
        pass


async def send_plugin_manifest(websocket, plugin_id):
    if plugin_id not in PLUGIN_DEFINITIONS:
        await safe_send_status(websocket, plugin_id, "Unknown bundled plugin", f"No manifest exists for bundled plugin ID: {plugin_id}")
        return

    module = await get_plugin_module(websocket, plugin_id)
    if module is None:
        return

    proxy = PluginSocketProxy(websocket, plugin_id)
    adapter = PLUGIN_DEFINITIONS[plugin_id]["adapter"]

    try:
        if adapter == "ai_ws":
            module.websocket = proxy
            await module.send_manifest()
        else:
            await module.send_manifest(proxy)
    except Exception:
        await safe_send_status(websocket, plugin_id, "Could not build plugin settings", traceback.format_exc())


async def dispatch_standard_ws(websocket, plugin_id, module, message):
    proxy = PluginSocketProxy(websocket, plugin_id)
    await module.handle_message(proxy, message)


async def dispatch_ai_ws(websocket, plugin_id, module, message):
    proxy = PluginSocketProxy(websocket, plugin_id)
    module.websocket = proxy
    await module.handle_message(message)


async def dispatch_to_plugin(websocket, plugin_id, message):
    """Call one plugin behind a hard error boundary."""
    module = await get_plugin_module(websocket, plugin_id)
    if module is None:
        return

    try:
        adapter = PLUGIN_DEFINITIONS[plugin_id]["adapter"]
        if adapter == "standard_ws":
            await dispatch_standard_ws(websocket, plugin_id, module, message)
        elif adapter == "ai_ws":
            await dispatch_ai_ws(websocket, plugin_id, module, message)
        else:
            raise RuntimeError(f"Unknown Party Pack adapter: {adapter}")
    except asyncio.CancelledError:
        raise
    except Exception:
        await safe_send_status(
            websocket,
            plugin_id,
            f"{PLUGIN_DEFINITIONS[plugin_id]['name']} had a problem",
            traceback.format_exc(),
        )


async def cleanup_plugin(websocket, plugin_id):
    """Stop one plugin without allowing cleanup failures to affect others."""
    module = loaded_plugins.get(plugin_id)
    if module is None:
        return

    try:
        adapter = PLUGIN_DEFINITIONS[plugin_id]["adapter"]
        if adapter == "ai_ws":
            await module.cancel_analysis_task()
            try:
                await websocket.send(json.dumps({
                    "type": "request_screenshots",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "pluginId": plugin_id,
                        "shouldSendScreenshots": False,
                    },
                    "meta": {},
                }))
            except Exception:
                pass
            module.websocket = None

        elif plugin_id == "speak-keyword-trigger-plugin":
            module.listening_active.clear()
            task = getattr(module, "listening_task", None)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                module.listening_task = None

        elif plugin_id == "gesture-trigger-plugin":
            module.camera_active.clear()
            task = getattr(module, "camera_task", None)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                module.camera_task = None

        elif plugin_id == "vlc-over-commercials":
            # On an unexpected browser disconnect there may be no normal "end"
            # message, so make sure VLC is still shut down. If the normal end
            # handler already ran, these state checks prevent duplicate cleanup.
            if getattr(module, "is_setup_complete", False) or getattr(module, "vlc_process", None):
                await asyncio.to_thread(module.end_plugin)

        elif adapter == "standard_ws":
            # Overlay Any Window has important cleanup in its normal end handler.
            if plugin_id == "overlay-any-window":
                state = client_states.get(websocket, {})
                prefs = {
                    "pluginPreferencesById": state.get("pluginPreferencesById", {})
                }
                await dispatch_standard_ws(
                    websocket,
                    plugin_id,
                    module,
                    {"type": "end", "data": {"preferences": prefs}},
                )
    except Exception:
        await safe_send_status(websocket, plugin_id, "Plugin cleanup had a problem", traceback.format_exc())


async def handle_screenshot(websocket, screenshot_bytes):
    # At present the AI detector is the browser-screenshot consumer in this pack.
    plugin_id = "ai-commercial-detector-ws"
    if plugin_id not in get_enabled_plugin_ids(websocket):
        return

    module = await get_plugin_module(websocket, plugin_id)
    if module is None:
        return

    try:
        module.websocket = PluginSocketProxy(websocket, plugin_id)
        await module.handle_screenshot(screenshot_bytes)
    except Exception:
        await safe_send_status(websocket, plugin_id, "AI screenshot processing had a problem", traceback.format_exc())


async def handle_message(websocket, message):
    """Party Pack message router. No plugin exception is allowed through it."""
    try:
        if not isinstance(message, dict):
            await safe_send_status(websocket, BUNDLE_ID, "Invalid Party Pack message", "Incoming JSON was not an object.")
            return

        message_type = message.get("type")
        if message_type == "plugin_bundle_manifest":
            await send_bundle_manifest(websocket)
            return

        if message_type == "plugin_manifest":
            plugin_id = message.get("data", {}).get("pluginId")
            await send_plugin_manifest(websocket, plugin_id)
            return

        if message_type == "init":
            preferences = message.get("data", {}).get("preferences", {})
            previous_enabled = get_enabled_plugin_ids(websocket)
            configure_client_from_init(websocket, preferences)
            new_enabled = get_enabled_plugin_ids(websocket)

            # Stop plugins that were enabled on an earlier init but are no longer selected.
            for plugin_id in previous_enabled:
                if plugin_id not in new_enabled:
                    await cleanup_plugin(websocket, plugin_id)

            for plugin_id in new_enabled:
                await dispatch_to_plugin(websocket, plugin_id, message)
            return

        if message_type in ("commercial_state_change", "browser_fullscreen_state_change"):
            for plugin_id in get_enabled_plugin_ids(websocket):
                await dispatch_to_plugin(websocket, plugin_id, message)
            return

        if message_type == "end":
            for plugin_id in get_enabled_plugin_ids(websocket):
                # Give plugins their normal end event first where applicable.
                if PLUGIN_DEFINITIONS[plugin_id]["adapter"] == "standard_ws":
                    await dispatch_to_plugin(websocket, plugin_id, message)
                await cleanup_plugin(websocket, plugin_id)
            client_states.pop(websocket, None)
            return

    except asyncio.CancelledError:
        raise
    except Exception:
        await safe_send_status(websocket, BUNDLE_ID, "Party Pack message could not be processed", traceback.format_exc())


async def handle_client(websocket):
    client_states[websocket] = {
        "triggerPluginIds": [],
        "overlayPluginIds": [],
        "pluginPreferencesById": {},
    }
    print("Party Pack client connected")

    try:
        async for raw_message in websocket:
            if isinstance(raw_message, bytes):
                await handle_screenshot(websocket, raw_message)
                continue

            try:
                message = json.loads(raw_message)
            except Exception:
                await safe_send_status(websocket, BUNDLE_ID, "Invalid Party Pack message", traceback.format_exc())
                continue

            await handle_message(websocket, message)

    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception:
        # Keep the process alive even if the connection itself behaves unexpectedly.
        print("Party Pack WebSocket connection error:\n" + traceback.format_exc())
    finally:
        for plugin_id in get_enabled_plugin_ids(websocket):
            await cleanup_plugin(websocket, plugin_id)
        client_states.pop(websocket, None)
        print("Party Pack client disconnected")


def start_advanced_logo_analyzer():
    """Run the Advanced Logo Analyzer Flask app on port 64143."""
    try:
        logo_app.run(
            host="127.0.0.1",
            port=LOGO_ANALYZER_PORT,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
    except Exception:
        print("Advanced Logo Analyzer could not start:\n" + traceback.format_exc())


def build_tray_image():
    """Load the original icon.png, with a simple fallback if it is missing."""
    icon_path = RESOURCE_DIR / "icon.png"

    try:
        if icon_path.is_file():
            return Image.open(icon_path)
    except Exception:
        print("Could not load icon.png:\n" + traceback.format_exc())

    # A fallback keeps the application usable even when icon.png was not copied.
    image = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 54, 54), outline="black", width=4)
    draw.rectangle((20, 20, 44, 44), fill="black")
    return image


def request_combined_shutdown(icon=None, item=None):
    """Ask the WebSocket server to close, then allow the whole process to exit."""
    shutdown_requested.set()

    if icon is not None:
        icon.stop()

    loop = party_pack_loop
    shutdown_event = party_pack_shutdown_event

    if loop is not None and shutdown_event is not None and loop.is_running():
        loop.call_soon_threadsafe(shutdown_event.set)


def start_tray():
    """Run the combined Advanced Logo Analyzer / Party Pack tray icon."""
    tray_menu = pystray.Menu(
        pystray.MenuItem("Exit", request_combined_shutdown),
    )
    icon = pystray.Icon(
        "Live Commercial Blocker - Official Plugin Party Pack",
        build_tray_image(),
        "Live Commercial Blocker - Official Plugin Party Pack",
        tray_menu,
    )
    icon.run()


async def main():
    """Run both servers until the tray Exit command requests shutdown."""
    global party_pack_loop, party_pack_shutdown_event

    party_pack_loop = asyncio.get_running_loop()
    party_pack_shutdown_event = asyncio.Event()
    if shutdown_requested.is_set():
        party_pack_shutdown_event.set()

    logo_thread = threading.Thread(
        target=start_advanced_logo_analyzer,
        name="AdvancedLogoAnalyzer",
        daemon=True,
    )
    logo_thread.start()

    async with websockets.serve(handle_client, "localhost", PARTY_PACK_PORT, max_size=None):
        print(f"Official Plugin Party Pack running on ws://localhost:{PARTY_PACK_PORT}")
        print(f"Advanced Logo Analyzer configured for http://127.0.0.1:{LOGO_ANALYZER_PORT}")
        await party_pack_shutdown_event.wait()

        # Closing each browser socket runs handle_client()'s normal finally block,
        # which lets every enabled plugin clean up its independent background work.
        connected_websockets = list(client_states.keys())
        if connected_websockets:
            await asyncio.gather(
                *(
                    websocket.close(code=1001, reason="Party Pack shutting down")
                    for websocket in connected_websockets
                ),
                return_exceptions=True,
            )
            await asyncio.sleep(0)

    print("Official Plugin Party Pack stopped.")

# =============================================================================
# Bundled plugin source: advanced_logo_analyzer.py
# Prefix: logo_
# =============================================================================

"""
Advanced Logo Analyzer - Flask service

This module exposes two endpoints used by the consuming app:
 - POST /advanced-logo-analysis
 - GET  /ping-advanced-logo-analysis
"""


import base64
import os
import sys
import threading
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from flask import Flask, jsonify, request
from PIL import Image
import pystray
from pystray import Menu as menu, MenuItem as item

logo___version__ = "1.0"
logo_PORT = 64143

logo_app = Flask(__name__)

# -----------------------------------------------------------------------------
# Global state
# -----------------------------------------------------------------------------
logo_logo_edges: List[np.ndarray] = []
logo_avg_edge_mask: Optional[np.ndarray] = None

logo_logo_edges_from_eroded: List[np.ndarray] = []
logo_avg_edge_mask_from_eroded: Optional[np.ndarray] = None

logo_color_imgs: List[np.ndarray] = []
logo_avg_color_img: Optional[np.ndarray] = None

logo_contours: List[np.ndarray] = []

# Defensive defaults so later comparisons won't raise NameError if mask hasn't
# been built yet. The consuming app should call "build-mask-first" or equivalent
# before relying on detection, but we avoid crashes.
logo_avg_edge_mask_boolean_mask: np.ndarray = np.zeros((1, 1), dtype=bool)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def logo_image_to_base64(img_np: np.ndarray) -> str:
    """Encode a numpy image (H x W x C) or (H x W) to a PNG data URL."""
    img_pil = Image.fromarray(img_np)
    buf = BytesIO()
    img_pil.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def logo_decode_request_image(data_url: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    Decode an incoming 'data:image/...;base64,...' string into two representations:
      - gray_np: single-channel uint8 grayscale (used for edge detection)
      - color_bgr: 3-channel BGR uint8 (OpenCV native ordering)
    """
    b64 = data_url.split(",", 1)[1]
    img_bytes = base64.b64decode(b64)

    # PIL grayscale (preserve aspect and single channel)
    pil_gray = Image.open(BytesIO(img_bytes)).convert("L")
    gray_np = np.array(pil_gray)

    # cv2 decode to get BGR image (preserves colors)
    buf = np.frombuffer(img_bytes, dtype=np.uint8)
    color_bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if color_bgr is None:
        # Fallback: convert PIL RGB to BGR if decoding failed
        pil_rgb = Image.open(BytesIO(img_bytes)).convert("RGB")
        color_rgb = np.array(pil_rgb)
        color_bgr = cv2.cvtColor(color_rgb, cv2.COLOR_RGB2BGR)

    return gray_np, color_bgr


def logo_build_styled_mask_preview(edge_mask: np.ndarray) -> np.ndarray:
    """
    Convert a single-channel edge mask into a 3-channel stylized preview where
    edge pixels are colored with a specified 'edge' color and background is
    a light styled background. Returns an uint8 BGR image.
    """
    styled_background_color = (236, 238, 240)  # BGR
    styled_edge_color = (18, 56, 77)  # BGR

    h, w = edge_mask.shape
    background = np.full((h, w, 3), styled_background_color, dtype=np.uint8)

    # normalize mask to [0,1] for blending (float operations for smoothness)
    mask_norm = (edge_mask / 255.0)[:, :, None]
    blended = (background.astype(np.float32) * (1 - mask_norm)) + (
        np.array(styled_edge_color, dtype=np.float32) * mask_norm
    )
    return blended.astype(np.uint8)


def logo_get_logo_bounding_box(edge_mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """Return (x, y, w, h) of largest contour bounding box or None when none found."""
    cnts, _ = cv2.findContours(edge_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    largest = max(cnts, key=cv2.contourArea)
    return cv2.boundingRect(largest)


def logo_bgr_to_hsv_tuple(bgr: Tuple[float, float, float]) -> Tuple[int, int, int]:
    """
    Convert a single BGR tuple (B, G, R) into HSV (H, S, V).
    Helpful for reporting average colors.
    """
    color_uint8 = np.uint8([[list(map(int, bgr))]])  # shape (1,1,3)
    hsv = cv2.cvtColor(color_uint8, cv2.COLOR_BGR2HSV)[0][0]
    return int(hsv[0]), int(hsv[1]), int(hsv[2])


def logo_average_hsv_and_rgb_outside_contours(image_bgr: np.ndarray, contours_list: List[np.ndarray]) -> Dict[str, Optional[Tuple[float, float, float]]]:
    """
    Compute average HSV and RGB of the region outside the provided contours.
    Returns dict {'avg_hsv': (H,S,V) | None, 'avg_rgb': (R,G,B) | None}
    """
    if image_bgr is None or image_bgr.size == 0:
        return {"avg_hsv": None, "avg_rgb": None}

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    mask = np.zeros_like(gray)
    if contours_list:
        cv2.drawContours(mask, contours_list, -1, 255, thickness=cv2.FILLED)

    outside_mask = cv2.bitwise_not(mask)

    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    h_out = h[outside_mask == 255]
    s_out = s[outside_mask == 255]
    v_out = v[outside_mask == 255]

    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    r, g, b = cv2.split(rgb)
    r_out = r[outside_mask == 255]
    g_out = g[outside_mask == 255]
    b_out = b[outside_mask == 255]

    if h_out.size == 0 or r_out.size == 0:
        return {"hsv": None, "rgb": None}

    avg_hsv = (float(h_out.mean()), float(s_out.mean()), float(v_out.mean()))
    avg_rgb = (float(r_out.mean()), float(g_out.mean()), float(b_out.mean()))

    return {"hsv": avg_hsv, "rgb": avg_rgb}


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@logo_app.route("/advanced-logo-analysis", methods=["POST"])
def logo_advanced_logo_analysis():
    """
    Main endpoint that accepts a JSON payload:
      {
        "image": "data:image/png;base64,...",
        "request": "<action>",
        "commercial": <bool>
      }

    Supported 'request' values:
      - "build-mask-first": initialize masks and previews
      - "build-mask": add a frame to the average mask
      - "build-mask-last": finalize mask and compute averages / contours
      - any other value: perform detection/compare using previously-built mask
    """
    global logo_logo_edges, logo_avg_edge_mask
    global logo_logo_edges_from_eroded, logo_avg_edge_mask_from_eroded
    global logo_color_imgs, logo_avg_color_img
    global logo_contours, logo_avg_edge_mask_boolean_mask
    global ground_truth_total

    data = request.json
    img_field = data.get("image")
    if not img_field:
        return jsonify({"error": "missing image"}), 400

    gray_np, color_bgr = logo_decode_request_image(img_field)
    # small morphological kernel used for erosion (shrinks shapes slightly)
    kernel = np.ones((5, 5), np.uint8)
    img_eroded = cv2.erode(gray_np, kernel)

    req = data.get("request", "")
    commercial_flag = bool(data.get("commercial", False))

    # -------------------------
    # Mask building entrypoints
    # -------------------------
    if req == "build-mask-first":
        # Start fresh with initial statistics
        img_blur = cv2.GaussianBlur(gray_np, (5, 5), 0)
        current_edge = cv2.Canny(img_blur, 20, 50)

        logo_logo_edges = [current_edge]
        logo_avg_edge_mask = np.mean(logo_logo_edges, axis=0).astype(np.uint8)

        img_blur_eroded = cv2.GaussianBlur(img_eroded, (5, 5), 0)
        current_edge_from_eroded = cv2.Canny(img_blur_eroded, 20, 50)
        logo_logo_edges_from_eroded = [current_edge_from_eroded]
        logo_avg_edge_mask_from_eroded = np.mean(logo_logo_edges_from_eroded, axis=0).astype(np.uint8)

        logo_color_imgs = [color_bgr]
        logo_avg_color_img = np.mean(logo_color_imgs, axis=0).astype(np.uint8)

        logo_contours = []

        styled_preview = logo_build_styled_mask_preview(logo_avg_edge_mask)

        return jsonify(
            {
                "request": req,
                "version": logo___version__,
                "maskBuildPreviewImage": logo_image_to_base64(styled_preview),
            }
        )

    if req == "build-mask":
        # Add a frame to the running average used as the mask
        img_blur = cv2.GaussianBlur(gray_np, (5, 5), 0)
        current_edge = cv2.Canny(img_blur, 30, 70)

        logo_logo_edges.append(current_edge)
        logo_avg_edge_mask = np.mean(logo_logo_edges, axis=0).astype(np.uint8)

        img_blur_eroded = cv2.GaussianBlur(img_eroded, (5, 5), 0)
        current_edge_from_eroded = cv2.Canny(img_blur_eroded, 30, 70)
        logo_logo_edges_from_eroded.append(current_edge_from_eroded)
        logo_avg_edge_mask_from_eroded = np.mean(logo_logo_edges_from_eroded, axis=0).astype(np.uint8)

        logo_color_imgs.append(color_bgr)
        logo_avg_color_img = np.mean(logo_color_imgs, axis=0).astype(np.uint8)

        styled_preview = logo_build_styled_mask_preview(logo_avg_edge_mask)

        return jsonify(
            {
                "request": req,
                "maskBuildPreviewImage": logo_image_to_base64(styled_preview),
            }
        )

    if req == "build-mask-last":
        # Finalize mask and compute contour-based statistics
        img_blur = cv2.GaussianBlur(gray_np, (5, 5), 0)
        current_edge = cv2.Canny(img_blur, 20, 50)

        logo_logo_edges.append(current_edge)
        logo_avg_edge_mask = np.mean(logo_logo_edges, axis=0).astype(np.uint8)

        img_blur_eroded = cv2.GaussianBlur(img_eroded, (5, 5), 0)
        current_edge_from_eroded = cv2.Canny(img_blur_eroded, 20, 50)
        logo_logo_edges_from_eroded.append(current_edge_from_eroded)
        logo_avg_edge_mask_from_eroded = np.mean(logo_logo_edges_from_eroded, axis=0).astype(np.uint8)

        logo_color_imgs.append(color_bgr)
        logo_avg_color_img = np.mean(logo_color_imgs, axis=0).astype(np.uint8)

        avg_edge_mask_boolean_mask_from_eroded = logo_avg_edge_mask_from_eroded > 180
        logo_contours, _ = cv2.findContours(
            (avg_edge_mask_boolean_mask_from_eroded.astype(np.uint8)), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Average color of the eroded-edge mask region (B,G,R)
        masked_pixels = logo_avg_color_img[avg_edge_mask_boolean_mask_from_eroded]
        if masked_pixels.size > 0:
            eroded_edges_avg_bgr = tuple(float(x) for x in masked_pixels.mean(axis=0))
            eroded_edges_avg_hsv = tuple(float(x) for x in logo_bgr_to_hsv_tuple(eroded_edges_avg_bgr))
        else:
            eroded_edges_avg_bgr = (255.0, 255.0, 255.0) # White
            eroded_edges_avg_hsv = (0.0, 0.0, 255.0) # White

        # Visual overlay: color red the location of pixels used to get average logo color
        overlay_img = logo_avg_color_img.copy()
        red_overlay = np.zeros_like(overlay_img)
        red_overlay[:, :, 2] = 255
        mask_3ch = np.stack([avg_edge_mask_boolean_mask_from_eroded] * 3, axis=-1)
        overlay_img = np.where(mask_3ch, cv2.addWeighted(overlay_img, 0.5, red_overlay, 0.5, 0), overlay_img)
        overlay_img_rgb = cv2.cvtColor(overlay_img, cv2.COLOR_BGR2RGB)

        # Create preview
        styled_preview = logo_build_styled_mask_preview(logo_avg_edge_mask)

        # Outer color for white background behind white or transparent logo protection
        outer_hsv_and_rgb = logo_average_hsv_and_rgb_outside_contours(logo_avg_color_img, logo_contours)

        # Ground truth mask for comparisons
        logo_avg_edge_mask_boolean_mask = logo_avg_edge_mask > 180
        ground_truth_total = logo_avg_edge_mask_boolean_mask.sum()

        # Return error if no logo is detected
        if ground_truth_total < 1:
            return jsonify({"error": "no logo detected"}), 400

        return jsonify(
            {
                "request": req,
                "edgeSum": float(ground_truth_total),
                "maskBuildPreviewImage": logo_image_to_base64(styled_preview),
                "finalMaskImage": logo_image_to_base64((logo_avg_edge_mask_boolean_mask.astype(np.uint8)) * 255),
                "averageColorInsideLogoHSV": eroded_edges_avg_hsv,
                "averageColorInsideLogoBGR": eroded_edges_avg_bgr,
                "averageColorInsideLogoCaptureRegionImage": logo_image_to_base64(overlay_img_rgb),
                "averageColorOutsideLogo": outer_hsv_and_rgb,
            }
        )

    # -------------------------
    # Detection / compare path
    # -------------------------
    # If caller flags 'commercial', we adjust edge thresholds to be less/ more sensitive
    if commercial_flag:
        img_blur = cv2.GaussianBlur(gray_np, (5, 5), 0)
        current_edge = cv2.Canny(img_blur, 40, 100)
    else:
        # more sensitive detection on non-commercial content
        current_edge = cv2.Canny(gray_np, 8, 12)

    current_edge_boolean_mask = current_edge > 20

    # True positives where both mask and current edge indicate an edge
    true_positive = np.logical_and(logo_avg_edge_mask_boolean_mask, current_edge_boolean_mask).sum()
    precision = float(true_positive / ground_truth_total) if ground_truth_total != 0 else 0.0

    # Visual diff: color-code pixels for inspection
    edge1 = logo_avg_edge_mask_boolean_mask.astype(bool)
    edge2 = current_edge_boolean_mask.astype(bool)
    styled_background_color = (236, 238, 240)
    visual = np.full((*logo_avg_edge_mask.shape, 3), styled_background_color, dtype=np.uint8)

    visual[edge1 & ~edge2] = [158, 52, 46]   # RED = edge in avg mask only
    visual[~edge1 & edge2] = [94, 136, 158]  # BLUE = edge in current only
    visual[edge1 & edge2] = [56, 122, 76]    # GREEN = both

    outer_hsv_and_rgb = logo_average_hsv_and_rgb_outside_contours(color_bgr, logo_contours)

    return jsonify(
        {
            "request": req,
            "edgeMatchConfidence": precision,
            "edgeMatchVisualImage": logo_image_to_base64(visual.astype(np.uint8)),
            "averageColorOutsideLogo": outer_hsv_and_rgb,
        }
    )


@logo_app.route("/ping-advanced-logo-analysis", methods=["GET"])
def logo_ping():
    """Simple healthcheck used by the tray and other tools."""
    return jsonify({"ok": True, "version": logo___version__})


# -----------------------------------------------------------------------------
# Tray helpers
# -----------------------------------------------------------------------------
def logo_run_server() -> None:
    """Run the Flask server in the background thread."""
    logo_app.run(port=logo_PORT)


def logo_on_restart(icon, item) -> None:
    """Restart the Python process."""
    icon.stop()
    os.execl(sys.executable, sys.executable, *sys.argv)


def logo_on_exit(icon, item) -> None:
    """Stop tray icon and forcibly exit the process."""
    icon.stop()
    os._exit(0)


def logo_start_tray() -> None:
    """Create system tray icon with Restart and Exit options."""
    #image = Image.open("icon.png")
    base_path = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_path, "icon.png")
    image = Image.open(icon_path)
    tray_menu = menu(item("Exit", logo_on_exit))
    icon = pystray.Icon("Live Commercial Blocker - Advanced Logo Analyzer", image, "Live Commercial Blocker - Advanced Logo Analyzer", tray_menu)
    icon.run()


# -----------------------------------------------------------------------------
# CLI entrypoint
# -----------------------------------------------------------------------------


# for exe creation:
# py -m PyInstaller --noconsole --icon=icon.ico advanced_logo_analyzer.py
# and then copy/paste icon.png into generated _internal folder
# lastly, compile into setup exe with Inno


# =============================================================================
# Bundled plugin source: commercial-push-notifications.py
# Prefix: ntfy_
# =============================================================================
import asyncio
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import websockets


ntfy_PLUGIN_PROTOCOL_VERSION = 1  # DO NOT TOUCH

ntfy_PLUGIN_NAME = "Commercial Push Notifications"
ntfy_PLUGIN_ID = "ntfy-commercial-notifications"  # Must be unique
ntfy_PLUGIN_VERSION = "1.0.0"

ntfy_PORT = 64146

ntfy_clients = set()


async def ntfy_handle_client(websocket):
    print("Client connected")
    ntfy_clients.add(websocket)

    try:
        async for message in websocket:
            try:
                # Messages from the extension should be JSON.
                msg = json.loads(message)
                await ntfy_handle_message(websocket, msg)

            except json.JSONDecodeError as error:
                print("Received invalid JSON:", error)

                await ntfy_send_status(
                    websocket,
                    "Plugin received an invalid message",
                    f"Could not decode the message as JSON: {error}",
                    display_type="error",
                )

            except Exception as error:
                # Catch unexpected message-processing errors so the plugin
                # stays running instead of crashing.
                print("Error while handling message:", error)

                await ntfy_send_status(
                    websocket,
                    "Plugin message error",
                    f"An unexpected error occurred while handling a message: {error}",
                    display_type="error",
                )

    except websockets.exceptions.ConnectionClosed:
        pass

    except Exception as error:
        print("WebSocket error:", error)

    finally:
        ntfy_clients.discard(websocket)
        print("Client disconnected")


async def ntfy_handle_message(ws, msg):
    # Make sure the message contains the fields we expect.
    if not isinstance(msg, dict):
        await ntfy_send_status(
            ws,
            "Invalid plugin message",
            "The message received from the extension was not a JSON object.",
            display_type="error",
        )
        return

    message_type = msg.get("type")

    if not message_type:
        await ntfy_send_status(
            ws,
            "Invalid plugin message",
            "The message did not contain a 'type' field.",
            display_type="error",
        )
        return

    data = msg.get("data", {})

    if not isinstance(data, dict):
        data = {}

    preferences = data.get("preferences", {})

    if not isinstance(preferences, dict):
        preferences = {}

    # Plugin settings are keyed by the plugin's own ID so another plugin
    # can never overwrite them.
    custom_overlay_plugin_preferences = (
        preferences
        .get("pluginPreferencesById", {})
        .get(ntfy_PLUGIN_ID, {})
        .get("preferences", {})
    )

    if not isinstance(custom_overlay_plugin_preferences, dict):
        custom_overlay_plugin_preferences = {}

    if message_type == "plugin_manifest":
        print("Plugin Manifest Requested. Sending Manifest.")
        await ntfy_send_manifest(ws)
        return

    if message_type == "init":
        print("Extension initiated")
        print("Full message:")
        print(msg)
        print("Full preferences:")
        print(preferences)
        print("Your custom requested plugin preferences:")
        print(custom_overlay_plugin_preferences)

        topic = custom_overlay_plugin_preferences.get("ntfy-topic", "").strip()

        if not topic:
            await ntfy_send_status(
                ws,
                "ntfy topic is not set",
                "Enter an ntfy topic in the plugin preferences before notifications can be sent.",
                display_type="error",
            )
        else:
            await ntfy_send_status(
                ws,
                "ntfy notifications ready",
                f"Connected and ready to send notifications to ntfy topic '{topic}'.",
            )

    elif message_type == "commercial_state_change":
        is_commercial = data.get("isCommercialState")

        utilities = data.get("utilities", {})
        if not isinstance(utilities, dict):
            utilities = {}

        commercial_state_trigger = utilities.get(
            "triggerOfLastCommercialStateChange"
        )

        print(
            "Commercial state change. is_commercial =",
            is_commercial,
            ", commercial_state_trigger =",
            commercial_state_trigger,
        )

        if is_commercial is True:
            # Commercials just started.
            should_notify = custom_overlay_plugin_preferences.get(
                "notify-commercial-start",
                True,
            )

            if should_notify:
                title = custom_overlay_plugin_preferences.get(
                    "commercial-start-title",
                    "Commercial Break Started",
                )

                description = custom_overlay_plugin_preferences.get(
                    "commercial-start-description",
                    "A commercial break has started.",
                )

                await ntfy_send_ntfy_notification(
                    ws,
                    custom_overlay_plugin_preferences,
                    title,
                    description,
                    notification_name="commercial start",
                )

        elif is_commercial is False:
            # Commercials just ended.
            should_notify = custom_overlay_plugin_preferences.get(
                "notify-commercial-end",
                True,
            )

            if should_notify:
                title = custom_overlay_plugin_preferences.get(
                    "commercial-end-title",
                    "Commercial Break Ended",
                )

                description = custom_overlay_plugin_preferences.get(
                    "commercial-end-description",
                    "The commercial break has ended.",
                )

                await ntfy_send_ntfy_notification(
                    ws,
                    custom_overlay_plugin_preferences,
                    title,
                    description,
                    notification_name="commercial end",
                )

        else:
            # This should normally never happen, but it is safer to handle it.
            await ntfy_send_status(
                ws,
                "Invalid commercial state received",
                (
                    "The commercial_state_change message did not contain "
                    "a valid True or False isCommercialState value."
                ),
                display_type="error",
            )

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = data.get("isFullscreen")

        print(
            "Fullscreen state changed on browser. is_fullscreen =",
            is_fullscreen,
        )


async def ntfy_send_ntfy_notification(
    ws,
    plugin_preferences,
    title,
    description,
    notification_name,
):
    """
    Validate the ntfy settings and send a notification.

    The actual HTTP request is run in another thread using asyncio.to_thread().
    This prevents a slow ntfy server from blocking the plugin's WebSocket.
    """

    topic = str(
        plugin_preferences.get("ntfy-topic", "")
    ).strip()

    server = str(
        plugin_preferences.get("ntfy-server", "https://ntfy.sh")
    ).strip()

    title = str(title or "")
    description = str(description or "")

    # Make sure a topic was entered.
    if not topic:
        await ntfy_send_status(
            ws,
            "Could not send ntfy notification",
            (
                f"The {notification_name} notification was not sent because "
                "the ntfy topic is empty. Enter a topic in the plugin preferences."
            ),
            display_type="error",
        )
        return

    # Make sure a server was entered.
    if not server:
        await ntfy_send_status(
            ws,
            "Could not send ntfy notification",
            (
                f"The {notification_name} notification was not sent because "
                "the ntfy server is empty."
            ),
            display_type="error",
        )
        return

    # Add https:// if somebody enters something like "ntfy.sh".
    if not server.startswith(("http://", "https://")):
        server = "https://" + server

    # Remove a trailing slash so we don't create a URL containing "//".
    server = server.rstrip("/")

    # URL-encode the topic in case it contains characters that need escaping.
    encoded_topic = urllib.parse.quote(topic, safe="")

    notification_url = f"{server}/{encoded_topic}"

    print(f"Sending {notification_name} ntfy notification")
    print("Server:", server)
    print("Topic:", topic)
    print("Title:", title)
    print("Description:", description)

    try:
        # urllib is a blocking library, so run it in another thread.
        response_code = await asyncio.to_thread(
            ntfy_send_ntfy_http_request,
            notification_url,
            title,
            description,
        )

        print(
            f"ntfy {notification_name} notification sent. "
            f"HTTP status: {response_code}"
        )

        await ntfy_send_status(
            ws,
            f"ntfy notification sent: {title}",
            (
                f"Successfully sent the {notification_name} notification "
                f"to topic '{topic}'. HTTP status: {response_code}"
            ),
        )

    except urllib.error.HTTPError as error:
        # ntfy responded, but with an HTTP error such as 400, 401, 403, etc.
        error_body = ""

        try:
            error_body = error.read().decode("utf-8", errors="replace")
        except Exception:
            pass

        debug_message = (
            f"ntfy returned HTTP {error.code} {error.reason} while sending "
            f"the {notification_name} notification."
        )

        if error_body:
            debug_message += f" Response: {error_body}"

        print(debug_message)

        await ntfy_send_status(
            ws,
            f"ntfy error: HTTP {error.code}",
            debug_message,
            display_type="error",
        )

    except urllib.error.URLError as error:
        # Usually DNS problems, server unavailable, refused connection, etc.
        debug_message = (
            f"Could not connect to the ntfy server '{server}' while sending "
            f"the {notification_name} notification. Error: {error.reason}"
        )

        print(debug_message)

        await ntfy_send_status(
            ws,
            "Could not connect to ntfy",
            debug_message,
            display_type="error",
        )

    except TimeoutError:
        debug_message = (
            f"The ntfy server '{server}' took too long to respond while "
            f"sending the {notification_name} notification."
        )

        print(debug_message)

        await ntfy_send_status(
            ws,
            "ntfy request timed out",
            debug_message,
            display_type="error",
        )

    except Exception as error:
        # Catch anything unexpected so a notification problem cannot crash
        # the whole plugin.
        debug_message = (
            f"An unexpected error occurred while sending the "
            f"{notification_name} ntfy notification: {error}"
        )

        print(debug_message)

        await ntfy_send_status(
            ws,
            "Could not send ntfy notification",
            debug_message,
            display_type="error",
        )


def ntfy_send_ntfy_http_request(notification_url, title, description):
    """
    Send the actual HTTP POST request to ntfy.

    This is a normal synchronous function because it is called with
    asyncio.to_thread() above.
    """

    # ntfy uses the request body as the notification message.
    body = description.encode("utf-8")

    headers = {
        "Title": title,
        "Content-Type": "text/plain; charset=utf-8",
        "User-Agent": f"{ntfy_PLUGIN_ID}/{ntfy_PLUGIN_VERSION}",
    }

    request = urllib.request.Request(
        notification_url,
        data=body,
        headers=headers,
        method="POST",
    )

    # The timeout prevents a bad/unavailable server from hanging forever.
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status


async def ntfy_send_status(
    ws,
    display,
    debug,
    display_type="info",
    display_time=7000,
):
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "status",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": ntfy_PLUGIN_PROTOCOL_VERSION,
                    "data": {},
                    "meta": {
                        "display": display,
                        "displayType": display_type,
                        # Time until the message disappears.
                        "displayTime": display_time,
                        "debug": debug,
                    },
                }
            )
        )

    except websockets.exceptions.ConnectionClosed:
        print("send_status send stopped: client disconnected")

    except Exception as error:
        # There is nowhere else to report this error if send_status itself
        # fails, so just print it instead of crashing the plugin.
        print("Could not send plugin status:", error)


async def ntfy_send_manifest(ws):
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "plugin_manifest",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": ntfy_PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "name": ntfy_PLUGIN_NAME,
                        "id": ntfy_PLUGIN_ID,
                        "version": ntfy_PLUGIN_VERSION,
                        "description": (
                            "Sends ntfy notifications when commercial breaks "
                            "start and end. Download the ntfy app on your phone "
                            "and subscribe to your topic."
                        ),
                        "primaryColor": "#317f6f",
                        "secondaryColor": "#ffffff",
                        "capabilities": ["overlay"],
                        "preferences": [
                            {
                                "key": "ntfy-topic",
                                "label": "ntfy Topic",
                                "description": "Must be unique! Try to not match anybody else's in the world.",
                                "tooltip": (
                                    "The ntfy topic that should receive the "
                                    "commercial notifications."
                                ),
                                "type": "text",
                                "default": "",
                            },
                            {
                                "key": "ntfy-server",
                                "label": "ntfy Server",
                                "tooltip": (
                                    "The ntfy server to send notifications to. "
                                    "Leave this at the default when using the "
                                    "public ntfy service."
                                ),
                                "type": "text",
                                "default": "https://ntfy.sh",
                            },
                            {
                                "key": "notify-commercial-start",
                                "label": "Notify When Commercials Start",
                                "tooltip": (
                                    "Send an ntfy notification when a commercial "
                                    "break begins."
                                ),
                                "type": "checkbox",
                                "default": True,
                            },
                            {
                                "key": "commercial-start-title",
                                "label": "Commercial Start Notification Title",
                                "tooltip": (
                                    "The title used for the notification when "
                                    "commercials begin."
                                ),
                                "type": "text",
                                "default": "Commercial Break Started",
                            },
                            {
                                "key": "commercial-start-description",
                                "label": "Commercial Start Notification Description",
                                "tooltip": (
                                    "The message shown in the notification when "
                                    "commercials begin."
                                ),
                                "type": "textarea",
                                "default": "A commercial break has started.",
                            },
                            {
                                "key": "notify-commercial-end",
                                "label": "Notify When Commercials End",
                                "tooltip": (
                                    "Send an ntfy notification when a commercial "
                                    "break ends."
                                ),
                                "type": "checkbox",
                                "default": True,
                            },
                            {
                                "key": "commercial-end-title",
                                "label": "Commercial End Notification Title",
                                "tooltip": (
                                    "The title used for the notification when "
                                    "commercials end."
                                ),
                                "type": "text",
                                "default": "Commercial Break Ended",
                            },
                            {
                                "key": "commercial-end-description",
                                "label": "Commercial End Notification Description",
                                "tooltip": (
                                    "The message shown in the notification when "
                                    "commercials end."
                                ),
                                "type": "textarea",
                                "default": "The commercial break has ended.",
                            },
                        ],
                    },
                    "meta": {
                        "display": "Sending Manifest",
                        "debug": "Sending ntfy Commercial Notifications manifest",
                    },
                }
            )
        )

    except websockets.exceptions.ConnectionClosed:
        print("send_manifest stopped: client disconnected")

    except Exception as error:
        print("Could not send plugin manifest:", error)


async def ntfy_main():
    try:
        async with websockets.serve(ntfy_handle_client, "localhost", ntfy_PORT):
            print(f"{ntfy_PLUGIN_NAME} v{ntfy_PLUGIN_VERSION}")
            print(f"Server running on ws://localhost:{ntfy_PORT}")
            print("Press Ctrl+C to stop.")
            await asyncio.Future()

    except OSError as error:
        # A common example is that another program is already using PORT.
        print()
        print("Could not start the WebSocket server.")
        print(f"Error: {error}")
        print()
        print(
            f"Make sure another program is not already using port {ntfy_PORT}."
        )

    except Exception as error:
        print()
        print("The plugin could not start.")
        print(f"Error: {error}")


# =============================================================================
# Bundled plugin source: local-ai-commercial-detector.py
# Prefix: ai_
# =============================================================================
import asyncio
import json
import re
import subprocess
import time
from collections import deque

import ollama
import websockets

ai_PLUGIN_PROTOCOL_VERSION = 1  # DO NOT TOUCH

ai_PLUGIN_NAME = "AI Commercial Detector"
ai_PLUGIN_ID = "ai-commercial-detector-ws"  # Must be unique
ai_PLUGIN_VERSION = "1.8.1"

ai_PORT = 64145

# Ollama settings.
# Install the Python package with: pip install ollama
# Make sure the Ollama desktop/service is running.
ai_DEFAULT_OLLAMA_MODEL = "qwen2.5vl:7b"
ai_DEFAULT_OLLAMA_CONTEXT_SIZE = None  # None = let the Ollama runtime decide
ai_OLLAMA_HOST = "http://127.0.0.1:11434"

# Regular-programming and commercial defaults intentionally match. They are
# separate preferences so users can tune the two states independently.
ai_DEFAULT_REGULAR_LLM_CALL_FREQUENCY_SECONDS = 0
ai_DEFAULT_COMMERCIAL_LLM_CALL_FREQUENCY_SECONDS = 0

ai_DEFAULT_REGULAR_CONSECUTIVE_YES_REQUIRED = 1
ai_DEFAULT_COMMERCIAL_CONSECUTIVE_YES_REQUIRED = 1

ai_DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE = 3
ai_DEFAULT_COMMERCIAL_SCREENSHOT_BATCH_SIZE = 3

ai_DEFAULT_REGULAR_SCREENSHOT_FREQUENCY_MILLISECONDS = 1500
ai_DEFAULT_COMMERCIAL_SCREENSHOT_FREQUENCY_MILLISECONDS = 1500

# Screenshot dimensions are state-specific, while trim settings are shared.
ai_DEFAULT_REGULAR_SCREENSHOT_MAX_WIDTH = 500
ai_DEFAULT_COMMERCIAL_SCREENSHOT_MAX_WIDTH = 500
ai_DEFAULT_REGULAR_SCREENSHOT_MAX_HEIGHT = 300
ai_DEFAULT_COMMERCIAL_SCREENSHOT_MAX_HEIGHT = 300

# Cooldowns begin after a confirmed state change. Ollama still runs during the
# cooldown, but its decisions are ignored for state-change logic.
ai_DEFAULT_INTO_COMMERCIAL_COOLDOWN_SECONDS = 6
ai_DEFAULT_OUT_OF_COMMERCIAL_COOLDOWN_SECONDS = 6

ai_DEFAULT_SCREENSHOT_TRIM_TOP_PERCENT = 0
ai_DEFAULT_SCREENSHOT_TRIM_RIGHT_PERCENT = 0
ai_DEFAULT_SCREENSHOT_TRIM_BOTTOM_PERCENT = 0
ai_DEFAULT_SCREENSHOT_TRIM_LEFT_PERCENT = 0

# These prompts are user-editable. The response-format instruction is included
# directly in each default prompt rather than appended elsewhere in the script.
ai_DEFAULT_COMMERCIAL_PROMPT = (
    "You are examining consecutive screenshots from a TV broadcast. "
    "Determine if all these screenshots are showing advertisements and/or commercials. "
    "Respond on one line. Response with YES or NO followed by a dash and then "
    "one short reason for the decision. Keep the reason concise."
)

#TODO: Add option to grab a few screenshots at the beging and have it summarize what the user is watching so it can check specifically for that
ai_DEFAULT_NON_COMMERCIAL_PROMPT = (
    "You are examining consecutive screenshots from a TV broadcast. "
    "Do all of these screenshots appear to NOT be part of a commercial "
    "and instead seem to be part of regular programming? "
    "Respond on one line. Response with YES or NO followed by a dash and then "
    "one short reason for the decision. Keep the reason concise."
)

# One shared async Ollama client is enough for this plugin.
ai_ollama_client = ollama.AsyncClient(host=ai_OLLAMA_HOST)

# This plugin is intentionally designed for one WebSocket connection at a time.
# handle_client() stores the active connection here so it does not need to be
# passed through every function.
ai_websocket = None

# Current plugin state.
ai_commercial_state = False

ai_regular_llm_call_frequency_seconds = ai_DEFAULT_REGULAR_LLM_CALL_FREQUENCY_SECONDS
ai_commercial_llm_call_frequency_seconds = ai_DEFAULT_COMMERCIAL_LLM_CALL_FREQUENCY_SECONDS

ai_regular_consecutive_yes_required = ai_DEFAULT_REGULAR_CONSECUTIVE_YES_REQUIRED
ai_commercial_consecutive_yes_required = ai_DEFAULT_COMMERCIAL_CONSECUTIVE_YES_REQUIRED

ai_regular_screenshot_batch_size = ai_DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE
ai_commercial_screenshot_batch_size = ai_DEFAULT_COMMERCIAL_SCREENSHOT_BATCH_SIZE

ai_regular_screenshot_frequency_milliseconds = (
    ai_DEFAULT_REGULAR_SCREENSHOT_FREQUENCY_MILLISECONDS
)
ai_commercial_screenshot_frequency_milliseconds = (
    ai_DEFAULT_COMMERCIAL_SCREENSHOT_FREQUENCY_MILLISECONDS
)

ai_regular_screenshot_max_width = ai_DEFAULT_REGULAR_SCREENSHOT_MAX_WIDTH
ai_commercial_screenshot_max_width = ai_DEFAULT_COMMERCIAL_SCREENSHOT_MAX_WIDTH
ai_regular_screenshot_max_height = ai_DEFAULT_REGULAR_SCREENSHOT_MAX_HEIGHT
ai_commercial_screenshot_max_height = ai_DEFAULT_COMMERCIAL_SCREENSHOT_MAX_HEIGHT

ai_into_commercial_cooldown_seconds = ai_DEFAULT_INTO_COMMERCIAL_COOLDOWN_SECONDS
ai_out_of_commercial_cooldown_seconds = ai_DEFAULT_OUT_OF_COMMERCIAL_COOLDOWN_SECONDS
ai_cooldown_until = 0.0

ai_screenshot_trim_top_percent = ai_DEFAULT_SCREENSHOT_TRIM_TOP_PERCENT
ai_screenshot_trim_right_percent = ai_DEFAULT_SCREENSHOT_TRIM_RIGHT_PERCENT
ai_screenshot_trim_bottom_percent = ai_DEFAULT_SCREENSHOT_TRIM_BOTTOM_PERCENT
ai_screenshot_trim_left_percent = ai_DEFAULT_SCREENSHOT_TRIM_LEFT_PERCENT

ai_screenshot_buffer = deque(maxlen=ai_DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE)
ai_consecutive_yes_count = 0
ai_last_llm_call_time = 0.0
ai_analysis_task = None
ai_screenshot_version = 0
ai_last_analyzed_screenshot_version = -1

ai_ollama_model = ai_DEFAULT_OLLAMA_MODEL
ai_ollama_context_size = ai_DEFAULT_OLLAMA_CONTEXT_SIZE
ai_commercial_prompt = ai_DEFAULT_COMMERCIAL_PROMPT
ai_non_commercial_prompt = ai_DEFAULT_NON_COMMERCIAL_PROMPT
ai_gpu_checked = False

# Incremented whenever runtime preferences change. An LLM result created with an
# older preference version is ignored so it cannot affect the new configuration.
ai_preference_version = 0


async def ai_handle_client(connection):
    """Handle the one WebSocket connection used by this plugin."""
    global ai_websocket

    # The plugin is only intended to have one active extension connection.
    # Refuse an unexpected second connection rather than replacing the global
    # websocket underneath the current one.
    if ai_websocket is not None:
        print("Second WebSocket connection rejected; plugin already has a client")
        await connection.close(code=1013, reason="Plugin already has an active client")
        return

    ai_websocket = connection
    ai_reset_runtime_state()
    print("Client connected")

    try:
        async for message in connection:
            if isinstance(message, bytes):
                await ai_handle_screenshot(message)
            else:
                msg = json.loads(message)
                await ai_handle_message(msg)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await ai_cancel_analysis_task()
        ai_websocket = None
        print("Client disconnected")


def ai_reset_runtime_state():
    """Reset connection-specific runtime state back to plugin defaults."""
    global ai_commercial_state
    global ai_regular_llm_call_frequency_seconds
    global ai_commercial_llm_call_frequency_seconds
    global ai_regular_consecutive_yes_required
    global ai_commercial_consecutive_yes_required
    global ai_regular_screenshot_batch_size
    global ai_commercial_screenshot_batch_size
    global ai_regular_screenshot_frequency_milliseconds
    global ai_commercial_screenshot_frequency_milliseconds
    global ai_regular_screenshot_max_width
    global ai_commercial_screenshot_max_width
    global ai_regular_screenshot_max_height
    global ai_commercial_screenshot_max_height
    global ai_into_commercial_cooldown_seconds
    global ai_out_of_commercial_cooldown_seconds
    global ai_cooldown_until
    global ai_screenshot_trim_top_percent
    global ai_screenshot_trim_right_percent
    global ai_screenshot_trim_bottom_percent
    global ai_screenshot_trim_left_percent
    global ai_screenshot_buffer
    global ai_consecutive_yes_count
    global ai_last_llm_call_time
    global ai_analysis_task
    global ai_screenshot_version
    global ai_last_analyzed_screenshot_version
    global ai_ollama_model
    global ai_ollama_context_size
    global ai_commercial_prompt
    global ai_non_commercial_prompt
    global ai_gpu_checked
    global ai_preference_version

    ai_commercial_state = False

    ai_regular_llm_call_frequency_seconds = ai_DEFAULT_REGULAR_LLM_CALL_FREQUENCY_SECONDS
    ai_commercial_llm_call_frequency_seconds = ai_DEFAULT_COMMERCIAL_LLM_CALL_FREQUENCY_SECONDS

    ai_regular_consecutive_yes_required = ai_DEFAULT_REGULAR_CONSECUTIVE_YES_REQUIRED
    ai_commercial_consecutive_yes_required = ai_DEFAULT_COMMERCIAL_CONSECUTIVE_YES_REQUIRED

    ai_regular_screenshot_batch_size = ai_DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE
    ai_commercial_screenshot_batch_size = ai_DEFAULT_COMMERCIAL_SCREENSHOT_BATCH_SIZE

    ai_regular_screenshot_frequency_milliseconds = (
        ai_DEFAULT_REGULAR_SCREENSHOT_FREQUENCY_MILLISECONDS
    )
    ai_commercial_screenshot_frequency_milliseconds = (
        ai_DEFAULT_COMMERCIAL_SCREENSHOT_FREQUENCY_MILLISECONDS
    )

    ai_regular_screenshot_max_width = ai_DEFAULT_REGULAR_SCREENSHOT_MAX_WIDTH
    ai_commercial_screenshot_max_width = ai_DEFAULT_COMMERCIAL_SCREENSHOT_MAX_WIDTH
    ai_regular_screenshot_max_height = ai_DEFAULT_REGULAR_SCREENSHOT_MAX_HEIGHT
    ai_commercial_screenshot_max_height = ai_DEFAULT_COMMERCIAL_SCREENSHOT_MAX_HEIGHT

    ai_into_commercial_cooldown_seconds = ai_DEFAULT_INTO_COMMERCIAL_COOLDOWN_SECONDS
    ai_out_of_commercial_cooldown_seconds = ai_DEFAULT_OUT_OF_COMMERCIAL_COOLDOWN_SECONDS
    ai_cooldown_until = 0.0

    ai_screenshot_trim_top_percent = ai_DEFAULT_SCREENSHOT_TRIM_TOP_PERCENT
    ai_screenshot_trim_right_percent = ai_DEFAULT_SCREENSHOT_TRIM_RIGHT_PERCENT
    ai_screenshot_trim_bottom_percent = ai_DEFAULT_SCREENSHOT_TRIM_BOTTOM_PERCENT
    ai_screenshot_trim_left_percent = ai_DEFAULT_SCREENSHOT_TRIM_LEFT_PERCENT

    ai_screenshot_buffer = deque(maxlen=ai_DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE)
    ai_consecutive_yes_count = 0
    ai_last_llm_call_time = 0.0
    ai_analysis_task = None
    ai_screenshot_version = 0
    ai_last_analyzed_screenshot_version = -1

    ai_ollama_model = ai_DEFAULT_OLLAMA_MODEL
    ai_ollama_context_size = ai_DEFAULT_OLLAMA_CONTEXT_SIZE
    ai_commercial_prompt = ai_DEFAULT_COMMERCIAL_PROMPT
    ai_non_commercial_prompt = ai_DEFAULT_NON_COMMERCIAL_PROMPT
    ai_gpu_checked = False
    ai_preference_version = 0


async def ai_cancel_analysis_task():
    """Cancel the current Ollama analysis task, if one is running."""
    global ai_analysis_task

    if ai_analysis_task and not ai_analysis_task.done():
        ai_analysis_task.cancel()
        try:
            await ai_analysis_task
        except asyncio.CancelledError:
            pass

    ai_analysis_task = None


async def ai_handle_message(msg):
    global ai_commercial_state
    global ai_consecutive_yes_count

    message_type = msg["type"]
    data = msg.get("data", {})
    preferences = data.get("preferences", {})
    custom_trigger_plugin_preferences = preferences.get("pluginPreferencesById", {}).get(ai_PLUGIN_ID, {}).get("preferences", {})

    if message_type == "plugin_manifest":
        print("Plugin Manifest Requested. Sending Manifest.")
        await ai_send_manifest()

    elif message_type == "init":
        print("Extension initiated")
        print("Full preferences:")
        print(preferences)
        print("Your custom requested plugin preferences:")
        print(custom_trigger_plugin_preferences)

        ai_apply_plugin_preferences(
            custom_trigger_plugin_preferences,
            initialize=True,
        )

        # If the init message provides the current commercial state, use it.
        if "isCommercialState" in data:
            ai_commercial_state = bool(data["isCommercialState"])

        ai_resize_screenshot_buffer_for_current_state()
        ai_print_current_preferences()

        await ai_send_status(
            "Initializing local AI model...",
            ai_build_current_preferences_debug(),
        )

        print("Requesting extension starts sending screenshots")
        await ai_request_screenshots()

    elif message_type == "commercial_state_change":
        is_commercial = bool(data["isCommercialState"])
        commercial_state_trigger = data["utilities"][
            "triggerOfLastCommercialStateChange"
        ]

        old_state = ai_commercial_state
        ai_commercial_state = is_commercial

        # Any confirmed state change starts a fresh YES streak and the cooldown
        # associated with the direction of that state change. This also covers
        # state changes initiated by triggers outside this plugin.
        if old_state != is_commercial:
            ai_consecutive_yes_count = 0
            ai_start_state_change_cooldown(is_commercial)
            ai_resize_screenshot_buffer_for_current_state()
            await ai_request_screenshots()

        print(
            "Commercial state confirmed by extension. "
            f"is_commercial={is_commercial}, "
            f"commercial_state_trigger={commercial_state_trigger}"
        )

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = bool(data["isFullscreen"])
        print(f"Fullscreen state changed on browser. is_fullscreen={is_fullscreen}")

        # The extension sends the latest plugin preferences again when entering
        # fullscreen. Apply any changes without requiring the plugin to restart.
        if is_fullscreen and custom_trigger_plugin_preferences:
            changed_keys, screenshot_preferences_changed = ai_apply_plugin_preferences(
                custom_trigger_plugin_preferences,
                initialize=False,
            )

            if changed_keys:
                print("Plugin preferences updated while running:")
                for key in changed_keys:
                    print(f"  - {key}")

                await ai_send_status(
                    "AI commercial detector preferences updated",
                    (
                        "Updated preferences: "
                        + ", ".join(changed_keys)
                        + "\n"
                        + ai_build_current_preferences_debug()
                    ),
                )

            # Re-send screenshot settings whenever any screenshot-related
            # preference changes, including an inactive state's settings.
            if screenshot_preferences_changed:
                ai_resize_screenshot_buffer_for_current_state()
                print("Screenshot preferences changed. Requesting screenshots again.")
                await ai_request_screenshots()

            # If a new batch size is smaller, the preserved rolling buffer may
            # already be large enough for another analysis.
            await ai_maybe_start_analysis()


def ai_get_float_preference(preferences, key, default, minimum=None, maximum=None):
    """Read a numeric preference safely and fall back to its default."""
    try:
        value = float(preferences.get(key, default))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(minimum, value)

    if maximum is not None:
        value = min(maximum, value)

    return value


def ai_get_int_preference(preferences, key, default, minimum=None, maximum=None):
    """Read an integer preference safely and fall back to its default."""
    try:
        value = int(float(preferences.get(key, default)))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(minimum, value)

    if maximum is not None:
        value = min(maximum, value)

    return value


def ai_get_string_preference(preferences, key, default):
    """Read a text preference safely and fall back to its default."""
    value = preferences.get(key, default)

    if value is None:
        return default

    value = str(value).strip()
    return value if value else default


def ai_get_context_size_preference(preferences, key, default):
    """Read the optional Ollama context size preference. None means runtime default."""
    value = preferences.get(key, default)

    if value is None:
        return None

    value = str(value).strip().lower()
    if value in ("", "runtime-default", "default", "none"):
        return None

    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def ai_format_context_size(value):
    """Return a readable context-size label for status/debug output."""
    if value is None:
        return "Runtime Default"
    return f"{value:,} tokens"


def ai_apply_plugin_preferences(preferences, initialize=False):
    """Apply initial or updated plugin preferences and report what changed."""
    global ai_regular_llm_call_frequency_seconds
    global ai_commercial_llm_call_frequency_seconds
    global ai_regular_consecutive_yes_required
    global ai_commercial_consecutive_yes_required
    global ai_regular_screenshot_batch_size
    global ai_commercial_screenshot_batch_size
    global ai_regular_screenshot_frequency_milliseconds
    global ai_commercial_screenshot_frequency_milliseconds
    global ai_regular_screenshot_max_width
    global ai_commercial_screenshot_max_width
    global ai_regular_screenshot_max_height
    global ai_commercial_screenshot_max_height
    global ai_into_commercial_cooldown_seconds
    global ai_out_of_commercial_cooldown_seconds
    global ai_cooldown_until
    global ai_screenshot_trim_top_percent
    global ai_screenshot_trim_right_percent
    global ai_screenshot_trim_bottom_percent
    global ai_screenshot_trim_left_percent
    global ai_consecutive_yes_count
    global ai_last_llm_call_time
    global ai_screenshot_version
    global ai_last_analyzed_screenshot_version
    global ai_ollama_model
    global ai_ollama_context_size
    global ai_commercial_prompt
    global ai_non_commercial_prompt
    global ai_gpu_checked
    global ai_preference_version

    if initialize:
        current_values = {
            "regular-llm-call-frequency-seconds": ai_DEFAULT_REGULAR_LLM_CALL_FREQUENCY_SECONDS,
            "commercial-llm-call-frequency-seconds": ai_DEFAULT_COMMERCIAL_LLM_CALL_FREQUENCY_SECONDS,
            "regular-consecutive-yes-required": ai_DEFAULT_REGULAR_CONSECUTIVE_YES_REQUIRED,
            "commercial-consecutive-yes-required": ai_DEFAULT_COMMERCIAL_CONSECUTIVE_YES_REQUIRED,
            "regular-screenshot-batch-size": ai_DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE,
            "commercial-screenshot-batch-size": ai_DEFAULT_COMMERCIAL_SCREENSHOT_BATCH_SIZE,
            "regular-screenshot-frequency-milliseconds": ai_DEFAULT_REGULAR_SCREENSHOT_FREQUENCY_MILLISECONDS,
            "commercial-screenshot-frequency-milliseconds": ai_DEFAULT_COMMERCIAL_SCREENSHOT_FREQUENCY_MILLISECONDS,
            "regular-screenshot-max-width": ai_DEFAULT_REGULAR_SCREENSHOT_MAX_WIDTH,
            "commercial-screenshot-max-width": ai_DEFAULT_COMMERCIAL_SCREENSHOT_MAX_WIDTH,
            "regular-screenshot-max-height": ai_DEFAULT_REGULAR_SCREENSHOT_MAX_HEIGHT,
            "commercial-screenshot-max-height": ai_DEFAULT_COMMERCIAL_SCREENSHOT_MAX_HEIGHT,
            "into-commercial-cooldown-seconds": ai_DEFAULT_INTO_COMMERCIAL_COOLDOWN_SECONDS,
            "out-of-commercial-cooldown-seconds": ai_DEFAULT_OUT_OF_COMMERCIAL_COOLDOWN_SECONDS,
            "screenshot-trim-top-percent": ai_DEFAULT_SCREENSHOT_TRIM_TOP_PERCENT,
            "screenshot-trim-right-percent": ai_DEFAULT_SCREENSHOT_TRIM_RIGHT_PERCENT,
            "screenshot-trim-bottom-percent": ai_DEFAULT_SCREENSHOT_TRIM_BOTTOM_PERCENT,
            "screenshot-trim-left-percent": ai_DEFAULT_SCREENSHOT_TRIM_LEFT_PERCENT,
            "ollama-model": ai_DEFAULT_OLLAMA_MODEL,
            "ollama-context-size": ai_DEFAULT_OLLAMA_CONTEXT_SIZE,
            "commercial-prompt": ai_DEFAULT_COMMERCIAL_PROMPT,
            "non-commercial-prompt": ai_DEFAULT_NON_COMMERCIAL_PROMPT,
        }
    else:
        current_values = {
            "regular-llm-call-frequency-seconds": ai_regular_llm_call_frequency_seconds,
            "commercial-llm-call-frequency-seconds": ai_commercial_llm_call_frequency_seconds,
            "regular-consecutive-yes-required": ai_regular_consecutive_yes_required,
            "commercial-consecutive-yes-required": ai_commercial_consecutive_yes_required,
            "regular-screenshot-batch-size": ai_regular_screenshot_batch_size,
            "commercial-screenshot-batch-size": ai_commercial_screenshot_batch_size,
            "regular-screenshot-frequency-milliseconds": ai_regular_screenshot_frequency_milliseconds,
            "commercial-screenshot-frequency-milliseconds": ai_commercial_screenshot_frequency_milliseconds,
            "regular-screenshot-max-width": ai_regular_screenshot_max_width,
            "commercial-screenshot-max-width": ai_commercial_screenshot_max_width,
            "regular-screenshot-max-height": ai_regular_screenshot_max_height,
            "commercial-screenshot-max-height": ai_commercial_screenshot_max_height,
            "into-commercial-cooldown-seconds": ai_into_commercial_cooldown_seconds,
            "out-of-commercial-cooldown-seconds": ai_out_of_commercial_cooldown_seconds,
            "screenshot-trim-top-percent": ai_screenshot_trim_top_percent,
            "screenshot-trim-right-percent": ai_screenshot_trim_right_percent,
            "screenshot-trim-bottom-percent": ai_screenshot_trim_bottom_percent,
            "screenshot-trim-left-percent": ai_screenshot_trim_left_percent,
            "ollama-model": ai_ollama_model,
            "ollama-context-size": ai_ollama_context_size,
            "commercial-prompt": ai_commercial_prompt,
            "non-commercial-prompt": ai_non_commercial_prompt,
        }

    new_values = {
        "regular-llm-call-frequency-seconds": ai_get_float_preference(
            preferences,
            "regular-llm-call-frequency-seconds",
            current_values["regular-llm-call-frequency-seconds"],
            minimum=0,
        ),
        "commercial-llm-call-frequency-seconds": ai_get_float_preference(
            preferences,
            "commercial-llm-call-frequency-seconds",
            current_values["commercial-llm-call-frequency-seconds"],
            minimum=0,
        ),
        "regular-consecutive-yes-required": ai_get_int_preference(
            preferences,
            "regular-consecutive-yes-required",
            current_values["regular-consecutive-yes-required"],
            minimum=1,
        ),
        "commercial-consecutive-yes-required": ai_get_int_preference(
            preferences,
            "commercial-consecutive-yes-required",
            current_values["commercial-consecutive-yes-required"],
            minimum=1,
        ),
        "regular-screenshot-batch-size": ai_get_int_preference(
            preferences,
            "regular-screenshot-batch-size",
            current_values["regular-screenshot-batch-size"],
            minimum=1,
        ),
        "commercial-screenshot-batch-size": ai_get_int_preference(
            preferences,
            "commercial-screenshot-batch-size",
            current_values["commercial-screenshot-batch-size"],
            minimum=1,
        ),
        "regular-screenshot-frequency-milliseconds": ai_get_int_preference(
            preferences,
            "regular-screenshot-frequency-milliseconds",
            current_values["regular-screenshot-frequency-milliseconds"],
            minimum=1,
        ),
        "commercial-screenshot-frequency-milliseconds": ai_get_int_preference(
            preferences,
            "commercial-screenshot-frequency-milliseconds",
            current_values["commercial-screenshot-frequency-milliseconds"],
            minimum=1,
        ),
        "regular-screenshot-max-width": ai_get_int_preference(
            preferences,
            "regular-screenshot-max-width",
            current_values["regular-screenshot-max-width"],
            minimum=1,
        ),
        "commercial-screenshot-max-width": ai_get_int_preference(
            preferences,
            "commercial-screenshot-max-width",
            current_values["commercial-screenshot-max-width"],
            minimum=1,
        ),
        "regular-screenshot-max-height": ai_get_int_preference(
            preferences,
            "regular-screenshot-max-height",
            current_values["regular-screenshot-max-height"],
            minimum=1,
        ),
        "commercial-screenshot-max-height": ai_get_int_preference(
            preferences,
            "commercial-screenshot-max-height",
            current_values["commercial-screenshot-max-height"],
            minimum=1,
        ),
        "into-commercial-cooldown-seconds": ai_get_float_preference(
            preferences,
            "into-commercial-cooldown-seconds",
            current_values["into-commercial-cooldown-seconds"],
            minimum=0,
        ),
        "out-of-commercial-cooldown-seconds": ai_get_float_preference(
            preferences,
            "out-of-commercial-cooldown-seconds",
            current_values["out-of-commercial-cooldown-seconds"],
            minimum=0,
        ),
        "screenshot-trim-top-percent": ai_get_float_preference(
            preferences,
            "screenshot-trim-top-percent",
            current_values["screenshot-trim-top-percent"],
            minimum=0,
            maximum=100,
        ),
        "screenshot-trim-right-percent": ai_get_float_preference(
            preferences,
            "screenshot-trim-right-percent",
            current_values["screenshot-trim-right-percent"],
            minimum=0,
            maximum=100,
        ),
        "screenshot-trim-bottom-percent": ai_get_float_preference(
            preferences,
            "screenshot-trim-bottom-percent",
            current_values["screenshot-trim-bottom-percent"],
            minimum=0,
            maximum=100,
        ),
        "screenshot-trim-left-percent": ai_get_float_preference(
            preferences,
            "screenshot-trim-left-percent",
            current_values["screenshot-trim-left-percent"],
            minimum=0,
            maximum=100,
        ),
        "ollama-model": ai_get_string_preference(
            preferences,
            "ollama-model",
            current_values["ollama-model"],
        ),
        "ollama-context-size": ai_get_context_size_preference(
            preferences,
            "ollama-context-size",
            current_values["ollama-context-size"],
        ),
        "commercial-prompt": ai_get_string_preference(
            preferences,
            "commercial-prompt",
            current_values["commercial-prompt"],
        ),
        "non-commercial-prompt": ai_get_string_preference(
            preferences,
            "non-commercial-prompt",
            current_values["non-commercial-prompt"],
        ),
    }

    changed_keys = [
        key
        for key, new_value in new_values.items()
        if initialize or new_value != current_values[key]
    ]

    if initialize:
        ai_preference_version = 0
    elif changed_keys:
        ai_preference_version += 1

    ai_regular_llm_call_frequency_seconds = new_values[
        "regular-llm-call-frequency-seconds"
    ]
    ai_commercial_llm_call_frequency_seconds = new_values[
        "commercial-llm-call-frequency-seconds"
    ]
    ai_regular_consecutive_yes_required = new_values[
        "regular-consecutive-yes-required"
    ]
    ai_commercial_consecutive_yes_required = new_values[
        "commercial-consecutive-yes-required"
    ]
    ai_regular_screenshot_batch_size = new_values["regular-screenshot-batch-size"]
    ai_commercial_screenshot_batch_size = new_values["commercial-screenshot-batch-size"]
    ai_regular_screenshot_frequency_milliseconds = new_values[
        "regular-screenshot-frequency-milliseconds"
    ]
    ai_commercial_screenshot_frequency_milliseconds = new_values[
        "commercial-screenshot-frequency-milliseconds"
    ]
    ai_regular_screenshot_max_width = new_values["regular-screenshot-max-width"]
    ai_commercial_screenshot_max_width = new_values["commercial-screenshot-max-width"]
    ai_regular_screenshot_max_height = new_values["regular-screenshot-max-height"]
    ai_commercial_screenshot_max_height = new_values["commercial-screenshot-max-height"]
    ai_into_commercial_cooldown_seconds = new_values["into-commercial-cooldown-seconds"]
    ai_out_of_commercial_cooldown_seconds = new_values["out-of-commercial-cooldown-seconds"]
    ai_screenshot_trim_top_percent = new_values["screenshot-trim-top-percent"]
    ai_screenshot_trim_right_percent = new_values["screenshot-trim-right-percent"]
    ai_screenshot_trim_bottom_percent = new_values["screenshot-trim-bottom-percent"]
    ai_screenshot_trim_left_percent = new_values["screenshot-trim-left-percent"]
    ai_ollama_model = new_values["ollama-model"]
    ai_ollama_context_size = new_values["ollama-context-size"]
    ai_commercial_prompt = new_values["commercial-prompt"]
    ai_non_commercial_prompt = new_values["non-commercial-prompt"]

    if initialize:
        ai_consecutive_yes_count = 0
        ai_last_llm_call_time = 0.0
        ai_screenshot_version = 0
        ai_last_analyzed_screenshot_version = -1
        ai_gpu_checked = False

    # Do not carry a YES streak across a model, prompt, confirmation threshold,
    # or batch-size change because the decisions are no longer directly
    # comparable.
    decision_keys = {
        "ollama-model",
        "ollama-context-size",
        "commercial-prompt",
        "non-commercial-prompt",
        "regular-consecutive-yes-required",
        "commercial-consecutive-yes-required",
        "regular-screenshot-batch-size",
        "commercial-screenshot-batch-size",
    }
    if not initialize and decision_keys.intersection(changed_keys):
        ai_consecutive_yes_count = 0

    if "ollama-model" in changed_keys:
        # The next Ollama request can use the newly selected model immediately.
        # Re-check the new model's processor split after it loads.
        ai_gpu_checked = False

    screenshot_keys = {
        "regular-screenshot-batch-size",
        "commercial-screenshot-batch-size",
        "regular-screenshot-frequency-milliseconds",
        "commercial-screenshot-frequency-milliseconds",
        "regular-screenshot-max-width",
        "commercial-screenshot-max-width",
        "regular-screenshot-max-height",
        "commercial-screenshot-max-height",
        "screenshot-trim-top-percent",
        "screenshot-trim-right-percent",
        "screenshot-trim-bottom-percent",
        "screenshot-trim-left-percent",
    }
    screenshot_preferences_changed = bool(screenshot_keys.intersection(changed_keys))

    return changed_keys, screenshot_preferences_changed


def ai_get_active_llm_call_frequency():
    if ai_commercial_state:
        return ai_commercial_llm_call_frequency_seconds
    return ai_regular_llm_call_frequency_seconds


def ai_get_active_consecutive_yes_required():
    if ai_commercial_state:
        return ai_commercial_consecutive_yes_required
    return ai_regular_consecutive_yes_required


def ai_get_active_screenshot_batch_size():
    if ai_commercial_state:
        return ai_commercial_screenshot_batch_size
    return ai_regular_screenshot_batch_size


def ai_get_active_screenshot_frequency_milliseconds():
    if ai_commercial_state:
        return ai_commercial_screenshot_frequency_milliseconds
    return ai_regular_screenshot_frequency_milliseconds


def ai_get_active_screenshot_max_width():
    if ai_commercial_state:
        return ai_commercial_screenshot_max_width
    return ai_regular_screenshot_max_width


def ai_get_active_screenshot_max_height():
    if ai_commercial_state:
        return ai_commercial_screenshot_max_height
    return ai_regular_screenshot_max_height


def ai_start_state_change_cooldown(new_commercial_state):
    """Start the cooldown for the direction of a confirmed state change."""
    global ai_cooldown_until

    if new_commercial_state:
        cooldown_seconds = ai_into_commercial_cooldown_seconds
        direction = "into commercial"
    else:
        cooldown_seconds = ai_out_of_commercial_cooldown_seconds
        direction = "out of commercial"

    ai_cooldown_until = time.monotonic() + cooldown_seconds
    print(f"Starting {direction} cooldown for {cooldown_seconds:g} second(s)")


def ai_get_cooldown_remaining_seconds():
    """Return the remaining state-change cooldown, or zero when it has expired."""
    return max(0.0, ai_cooldown_until - time.monotonic())


def ai_resize_screenshot_buffer_for_current_state():
    """Resize the rolling buffer while preserving the newest screenshots."""
    global ai_screenshot_buffer

    new_batch_size = ai_get_active_screenshot_batch_size()

    if ai_screenshot_buffer.maxlen == new_batch_size:
        return

    ai_screenshot_buffer = deque(
        list(ai_screenshot_buffer)[-new_batch_size:],
        maxlen=new_batch_size,
    )


def ai_print_current_preferences():
    """Print the current plugin settings in a compact form."""
    print(f"Ollama model: {ai_ollama_model}")
    print(f"Ollama context size: {ai_format_context_size(ai_ollama_context_size)}")
    print(
        "Regular programming: "
        f"LLM frequency={ai_regular_llm_call_frequency_seconds:g}s, "
        f"YES required={ai_regular_consecutive_yes_required}, "
        f"batch size={ai_regular_screenshot_batch_size}, "
        f"screenshot frequency={ai_regular_screenshot_frequency_milliseconds}ms, "
        f"max dimensions={ai_regular_screenshot_max_width}x{ai_regular_screenshot_max_height}"
    )
    print(
        "Commercial: "
        f"LLM frequency={ai_commercial_llm_call_frequency_seconds:g}s, "
        f"YES required={ai_commercial_consecutive_yes_required}, "
        f"batch size={ai_commercial_screenshot_batch_size}, "
        f"screenshot frequency={ai_commercial_screenshot_frequency_milliseconds}ms, "
        f"max dimensions={ai_commercial_screenshot_max_width}x{ai_commercial_screenshot_max_height}"
    )
    print(
        f"Cooldowns: into commercial={ai_into_commercial_cooldown_seconds:g}s, "
        f"out of commercial={ai_out_of_commercial_cooldown_seconds:g}s"
    )
    print(
        "Screenshot trim percentages: "
        f"top={ai_screenshot_trim_top_percent:g}, "
        f"right={ai_screenshot_trim_right_percent:g}, "
        f"bottom={ai_screenshot_trim_bottom_percent:g}, "
        f"left={ai_screenshot_trim_left_percent:g}"
    )


def ai_build_current_preferences_debug():
    """Return the current settings as readable debug text."""
    return (
        f"Model: {ai_ollama_model}\n"
        f"Ollama context size: {ai_format_context_size(ai_ollama_context_size)}\n"
        f"Current state: {'commercial' if ai_commercial_state else 'regular programming'}\n"
        f"Regular LLM minimum interval: {ai_regular_llm_call_frequency_seconds:g}s\n"
        f"Commercial LLM minimum interval: {ai_commercial_llm_call_frequency_seconds:g}s\n"
        f"Regular consecutive YES required: {ai_regular_consecutive_yes_required}\n"
        f"Commercial consecutive YES required: {ai_commercial_consecutive_yes_required}\n"
        f"Regular screenshot batch size: {ai_regular_screenshot_batch_size}\n"
        f"Commercial screenshot batch size: {ai_commercial_screenshot_batch_size}\n"
        f"Regular screenshot frequency: {ai_regular_screenshot_frequency_milliseconds}ms\n"
        f"Commercial screenshot frequency: {ai_commercial_screenshot_frequency_milliseconds}ms\n"
        f"Regular screenshot max dimensions: {ai_regular_screenshot_max_width}x{ai_regular_screenshot_max_height}\n"
        f"Commercial screenshot max dimensions: {ai_commercial_screenshot_max_width}x{ai_commercial_screenshot_max_height}\n"
        f"Going into commercial cooldown: {ai_into_commercial_cooldown_seconds:g}s\n"
        f"Going out of commercial cooldown: {ai_out_of_commercial_cooldown_seconds:g}s\n"
        "Screenshot trim percentages: "
        f"top={ai_screenshot_trim_top_percent:g}, "
        f"right={ai_screenshot_trim_right_percent:g}, "
        f"bottom={ai_screenshot_trim_bottom_percent:g}, "
        f"left={ai_screenshot_trim_left_percent:g}"
    )


async def ai_handle_screenshot(screenshot_bytes):
    global ai_screenshot_version

    print(f"Received screenshot as JPEG: {len(screenshot_bytes)} bytes")

    ai_screenshot_buffer.append(screenshot_bytes)
    ai_screenshot_version += 1

    batch_size = ai_get_active_screenshot_batch_size()
    print(f"Screenshot buffer: {len(ai_screenshot_buffer)}/{batch_size}")

    # We cannot analyze until the first full rolling batch exists.
    if len(ai_screenshot_buffer) < batch_size:
        return

    await ai_maybe_start_analysis()


async def ai_maybe_start_analysis():
    global ai_last_llm_call_time
    global ai_last_analyzed_screenshot_version
    global ai_analysis_task

    batch_size = ai_get_active_screenshot_batch_size()
    if len(ai_screenshot_buffer) < batch_size:
        return

    # Never allow more than one Ollama request at a time.
    if ai_analysis_task and not ai_analysis_task.done():
        return

    # Require at least one newly received screenshot since the previous LLM
    # analysis started. This prevents frequency=0 from re-analyzing the exact
    # same batch repeatedly.
    if ai_screenshot_version <= ai_last_analyzed_screenshot_version:
        return

    # Respect the active state's configured minimum time between call starts.
    now = time.monotonic()
    call_frequency = ai_get_active_llm_call_frequency()

    if now - ai_last_llm_call_time < call_frequency:
        return

    screenshots = list(ai_screenshot_buffer)
    state_at_start = ai_commercial_state
    preference_version_at_start = ai_preference_version

    ai_last_llm_call_time = now
    ai_last_analyzed_screenshot_version = ai_screenshot_version
    ai_analysis_task = asyncio.create_task(
        ai_analyze_screenshot_batch(
            screenshots,
            state_at_start,
            preference_version_at_start,
        )
    )


async def ai_analyze_screenshot_batch(
    screenshots,
    state_at_start,
    preference_version_at_start,
):
    global ai_analysis_task
    global ai_consecutive_yes_count
    global ai_commercial_state
    global ai_gpu_checked

    try:
        print(
            f"Sending {len(screenshots)} screenshots to Ollama. "
            f"Current commercial state={state_at_start}"
        )

        # Snapshot values used by this request. If preferences change while the
        # request is running, the result is reported but ignored for state logic.
        selected_model = ai_ollama_model
        selected_context_size = ai_ollama_context_size
        selected_commercial_prompt = ai_commercial_prompt
        selected_non_commercial_prompt = ai_non_commercial_prompt

        decision, llm_response, ai_stats = await ai_ask_ollama_about_transition(
            screenshots,
            state_at_start,
            selected_model,
            selected_context_size,
            selected_commercial_prompt,
            selected_non_commercial_prompt,
        )

        ai_debug_header = ai_build_ai_debug_header(ai_stats)
        full_debug = ai_debug_header + "\n\nAI response:\n" + llm_response

        # Check the Ollama CLI once after the selected model has successfully
        # loaded. This gives the same CPU/GPU split shown by `ollama ps`.
        if not ai_gpu_checked:
            ai_gpu_checked = await ai_warn_if_not_full_gpu(selected_model)

        print(f"Ollama response: {llm_response!r}")
        print(ai_debug_header)

        # A response generated using old preferences is useful for debugging but
        # must not affect the current commercial state or YES streak.
        if ai_preference_version != preference_version_at_start:
            print(
                "Ignoring Ollama response because plugin preferences changed "
                "during analysis"
            )
            await ai_send_status(
                "AI decision ignored because preferences changed",
                full_debug,
            )
            ai_consecutive_yes_count = 0
            return

        # The commercial state may have changed while Ollama was thinking. If
        # so, this answer was produced for the opposite question and is ignored.
        if ai_commercial_state != state_at_start:
            print(
                "Ignoring Ollama response because commercial state changed "
                "during analysis"
            )
            await ai_send_status(
                "AI decision ignored because commercial state changed",
                full_debug,
            )
            ai_consecutive_yes_count = 0
            return

        # Ollama continues running during cooldowns, but every decision is
        # deliberately ignored so it cannot increment/reset the YES streak or
        # trigger another state change too soon.
        cooldown_remaining = ai_get_cooldown_remaining_seconds()
        if cooldown_remaining > 0:
            print(
                f"Ignoring AI decision during state-change cooldown "
                f"({cooldown_remaining:.2f}s remaining)"
            )
            cooldown_display = (
                f"AI decision ignored during cooldown ({cooldown_remaining:.1f}s remaining): "
                f"{decision}"
            )
            if decision == "YES":
                cooldown_display += f" - {llm_response}"

            await ai_send_status(
                cooldown_display,
                full_debug,
            )
            return

        yes_required = ai_get_active_consecutive_yes_required()

        if decision == "YES":
            ai_consecutive_yes_count += 1
        elif decision == "NO":
            # A NO breaks the streak.
            ai_consecutive_yes_count = 0
        else:
            # UNKNOWN neither counts toward nor resets the current YES streak.
            pass

        yes_count = ai_consecutive_yes_count

        print(
            f"Transition answer={decision}; "
            f"consecutive YES count={yes_count}/{yes_required}"
        )
        
        display_question = "is this not commercial" if ai_commercial_state else "is this a commercial"

        # Always send the result of every completed analysis. If the answer is
        # YES, append the entire LLM response to the end of the display.
        status_display = f"AI, {display_question}? AI: {decision} ({yes_count}/{yes_required} YES)"
        if decision == "YES":
            status_display += f" - {llm_response}"

        await ai_send_status(
            status_display,
            full_debug,
        )

        if decision != "YES" or yes_count < yes_required:
            return

        # Enough consecutive YES responses were received. A YES means the
        # desired transition depends on our current state:
        #   regular program -> commercial
        #   commercial      -> regular program
        new_commercial_state = not state_at_start

        # Update immediately so another analysis cannot send the same change
        # again before the extension echoes the confirmed state back.
        ai_commercial_state = new_commercial_state
        ai_consecutive_yes_count = 0
        ai_start_state_change_cooldown(new_commercial_state)

        # The active screenshot batch/frequency/dimensions can change with commercial state.
        ai_resize_screenshot_buffer_for_current_state()

        if new_commercial_state:
            display = "AI detected commercial break"
        else:
            display = "AI detected return to programming"

        # This state change was caused by a YES, so include the complete response
        # at the end of the display as well.
        display += f" - {llm_response}"

        print(f"Sending commercial state change: {new_commercial_state}")
        await ai_send_commercial_state_change(
            new_commercial_state,
            display,
            full_debug,
        )

        # Immediately tell the browser to use the screenshot frequency and
        # dimensions for the newly active state. Shared trim values are included too.
        await ai_request_screenshots()

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"Ollama analysis failed: {exc}")

        if ai_websocket is not None:
            context_error = ai_get_context_size_error_details(exc)

            if context_error is not None:
                required_tokens, available_tokens = context_error
                required_text = (
                    f"{required_tokens:,}" if required_tokens is not None else "unknown"
                )
                available_text = (
                    f"{available_tokens:,}" if available_tokens is not None else "unknown"
                )

                await ai_send_status(
                    (
                        "AI request is too large for Ollama's context window. "
                        "Increase the Ollama Context Size preference or reduce the "
                        "screenshot batch size/resolution."
                    ),
                    (
                        "Ollama context-size error\n"
                        f"Request tokens: {required_text}\n"
                        f"Available context: {available_text}\n"
                        f"Configured preference: {ai_format_context_size(ai_ollama_context_size)}\n\n"
                        "If Ollama Context Size is set to Runtime Default, try 8,192 "
                        "or a larger value supported by your model/hardware. You can "
                        "also reduce Screenshot Batch Size or screenshot dimensions.\n\n"
                        f"Original Ollama error: {exc}"
                    ),
                )
            else:
                await ai_send_status(
                    "AI commercial detection error",
                    f"Ollama analysis failed: {exc}",
                )
    finally:
        # Only clear the task slot if this coroutine is still the registered
        # analysis task.
        current_task = asyncio.current_task()
        if ai_analysis_task is current_task:
            ai_analysis_task = None

        # Important for frequency=0: if at least one screenshot arrived while
        # Ollama was working, immediately check whether another analysis can be
        # started using the newest rolling batch.
        if ai_websocket is not None:
            await ai_maybe_start_analysis()


async def ai_ask_ollama_about_transition(
    screenshots,
    currently_commercial,
    model,
    context_size,
    selected_commercial_prompt,
    selected_non_commercial_prompt,
):
    if currently_commercial:
        question = selected_non_commercial_prompt.strip()
    else:
        question = selected_commercial_prompt.strip()

    options = {
        "temperature": 0,
    }

    # When Runtime Default is selected, do not send num_ctx at all and let
    # Ollama choose its normal runtime context.
    if context_size is not None:
        options["num_ctx"] = context_size

    call_started = time.monotonic()
    response = await ai_ollama_client.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": question,
                # Ollama's Python client accepts raw image bytes here, so the
                # JPEGs received from the browser do not need manual base64 work.
                "images": screenshots,
            }
        ],
        options=options,
    )
    wall_time_seconds = time.monotonic() - call_started

    llm_response = response.message.content.strip()
    decision = ai_parse_yes_no_response(llm_response)

    prompt_tokens = getattr(response, "prompt_eval_count", None)
    response_tokens = getattr(response, "eval_count", None)
    total_tokens = None
    if prompt_tokens is not None and response_tokens is not None:
        total_tokens = prompt_tokens + response_tokens

    ai_stats = {
        "model": model,
        "context_size": context_size,
        "screenshots": len(screenshots),
        "wall_time_seconds": wall_time_seconds,
        "total_duration_ns": getattr(response, "total_duration", None),
        "load_duration_ns": getattr(response, "load_duration", None),
        "prompt_eval_duration_ns": getattr(response, "prompt_eval_duration", None),
        "eval_duration_ns": getattr(response, "eval_duration", None),
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }

    return decision, llm_response, ai_stats


def ai_parse_yes_no_response(response):
    """Return YES, NO, or UNKNOWN based on the first value in the response."""
    stripped = response.strip()

    if not stripped:
        return "UNKNOWN"

    # Reasons are expected on the same line, e.g.:
    #   YES The screenshots are clearly advertisements.
    # Only the first word/value controls the decision.
    first_value = stripped.split(maxsplit=1)[0]
    cleaned = first_value.upper().strip(" .,!?:;\"'`\n\r\t")

    if cleaned == "YES":
        return "YES"

    if cleaned == "NO":
        return "NO"

    # Anything else is deliberately allowed and treated as UNKNOWN. UNKNOWN
    # neither increments nor resets the consecutive-YES counter.
    return "UNKNOWN"


def ai_format_nanoseconds_as_seconds(value):
    """Format an Ollama nanosecond duration without failing on missing values."""
    if value is None:
        return "n/a"

    try:
        return f"{float(value) / 1_000_000_000:.3f}s"
    except (TypeError, ValueError):
        return "n/a"


def ai_format_token_count(value):
    """Format a token count returned by Ollama."""
    if value is None:
        return "n/a"

    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def ai_build_ai_debug_header(stats):
    """Build the performance/token section placed at the top of debug output."""
    return (
        "AI call details:\n"
        f"Model: {stats['model']}\n"
        f"Requested context: {ai_format_context_size(stats['context_size'])}\n"
        f"Screenshots: {stats['screenshots']}\n"
        f"Wall-clock time: {stats['wall_time_seconds']:.3f}s\n"
        f"Ollama total duration: "
        f"{ai_format_nanoseconds_as_seconds(stats['total_duration_ns'])}\n"
        f"Model load duration: "
        f"{ai_format_nanoseconds_as_seconds(stats['load_duration_ns'])}\n"
        f"Prompt/image evaluation: "
        f"{ai_format_nanoseconds_as_seconds(stats['prompt_eval_duration_ns'])}\n"
        f"Response generation: "
        f"{ai_format_nanoseconds_as_seconds(stats['eval_duration_ns'])}\n"
        f"Prompt tokens: {ai_format_token_count(stats['prompt_tokens'])}\n"
        f"Response tokens: {ai_format_token_count(stats['response_tokens'])}\n"
        f"Total tokens: {ai_format_token_count(stats['total_tokens'])}"
    )


def ai_get_context_size_error_details(exc):
    """Return (required_tokens, available_tokens) for Ollama context overflow errors."""
    error_text = str(exc)
    error_text_lower = error_text.lower()

    if (
        "exceed_context_size_error" not in error_text_lower
        and "exceeds the available context size" not in error_text_lower
    ):
        return None

    required_match = re.search(r'"n_prompt_tokens"\s*:\s*(\d+)', error_text)
    context_match = re.search(r'"n_ctx"\s*:\s*(\d+)', error_text)

    # Fall back to the human-readable message if the JSON fields are unavailable.
    if required_match is None:
        required_match = re.search(r"request \((\d+) tokens\)", error_text, re.IGNORECASE)

    if context_match is None:
        context_match = re.search(
            r"available context size \((\d+) tokens\)",
            error_text,
            re.IGNORECASE,
        )

    required_tokens = int(required_match.group(1)) if required_match else None
    available_tokens = int(context_match.group(1)) if context_match else None

    return required_tokens, available_tokens


def ai_get_ollama_processor_status():
    """Return the text output from `ollama ps`."""
    try:
        startupinfo = None
        creationflags = 0

        # Avoid flashing a console window on Windows when this script is packaged.
        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        result = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            check=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        return result.stdout.strip()

    except Exception as exc:
        print(f"Could not run ollama ps: {exc}")
        return ""


def ai_get_ollama_model_processor_line(status, model):
    """Find the row for a model in `ollama ps` output."""
    model_lower = model.lower()

    for line in status.splitlines():
        if model_lower in line.lower():
            return line.strip()

    return ""


async def ai_warn_if_not_full_gpu(model):
    """Warn the extension if Ollama reports any CPU offload for the model."""
    status = await asyncio.to_thread(ai_get_ollama_processor_status)

    if not status:
        print("Could not determine Ollama processor status")
        return False

    model_line = ai_get_ollama_model_processor_line(status, model)

    if not model_line:
        print(f"Could not find {model!r} in ollama ps output")
        print(status)
        return False

    print(f"Ollama processor status: {model_line}")

    if "100% GPU" not in model_line.upper():
        await ai_send_status(
            "Warning: Ollama is not fully using the GPU.",
            (
                f"Ollama is using CPU offload for {model}. Performance may be reduced. "
                f"Restarting Ollama may allow the model to load fully into VRAM.\n"
                f"{model_line}"
            ),
        )

    return True


async def ai_send_commercial_state_change(is_commercial, display, debug):
    if ai_websocket is None:
        return

    try:
        await ai_websocket.send(
            json.dumps(
                {
                    "type": "commercial_state_change",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": ai_PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "isCommercial": is_commercial,
                    },
                    "meta": {
                        "display": display,
                        "debug": debug,
                    },
                }
            )
        )
    except websockets.exceptions.ConnectionClosed:
        print("send_commercial_state_change stopped: client disconnected")


# This can be used to disable or enable any auto commercial detection that the
# browser extension is doing.
async def ai_send_auto_commercial_blocked_state_change(
    is_auto_commercial_blocked,
    display,
    debug,
):
    if ai_websocket is None:
        return

    try:
        await ai_websocket.send(
            json.dumps(
                {
                    "type": "auto_commercial_blocked_state_change",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": ai_PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "isAutoCommercialBlocked": is_auto_commercial_blocked,
                    },
                    "meta": {
                        "display": display,
                        "debug": debug,
                    },
                }
            )
        )
    except websockets.exceptions.ConnectionClosed:
        print("send_auto_commercial_blocked_state_change stopped: client disconnected")


async def ai_send_status(display, debug):
    if ai_websocket is None:
        return

    try:
        await ai_websocket.send(
            json.dumps(
                {
                    "type": "status",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": ai_PLUGIN_PROTOCOL_VERSION,
                    "data": {},
                    "meta": {
                        "display": display,
                        "debug": debug,
                    },
                }
            )
        )
    except websockets.exceptions.ConnectionClosed:
        print("send_status stopped: client disconnected")


async def ai_request_screenshots():
    if ai_websocket is None:
        return

    try:
        await ai_websocket.send(
            json.dumps(
                {
                    "type": "request_screenshots",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": ai_PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "shouldSendScreenshots": True,
                        "frequencyMilliseconds": (
                            ai_get_active_screenshot_frequency_milliseconds()
                        ),
                        "maxDimensionsPixels": {
                            "height": ai_get_active_screenshot_max_height(),
                            "width": ai_get_active_screenshot_max_width(),
                        },
                        "trimOptionsPercentages": {
                            "top": ai_screenshot_trim_top_percent,
                            "right": ai_screenshot_trim_right_percent,
                            "bottom": ai_screenshot_trim_bottom_percent,
                            "left": ai_screenshot_trim_left_percent,
                        },
                    },
                    "meta": {},
                }
            )
        )
    except websockets.exceptions.ConnectionClosed:
        print("request_screenshots stopped: client disconnected")


async def ai_get_local_ollama_models():
    """Return the names of models currently installed in the local Ollama library."""
    try:
        response = await ai_ollama_client.list()
        models = []

        for model in response.models:
            model_name = getattr(model, "model", None) or getattr(model, "name", None)
            if model_name:
                models.append(str(model_name))

        return sorted(set(models), key=str.lower)

    except Exception as exc:
        print(f"Could not get local Ollama models: {exc}")
        return []


async def ai_send_manifest():
    if ai_websocket is None:
        return

    local_models = await ai_get_local_ollama_models()
    model_options = [
        {"label": model_name, "value": model_name}
        for model_name in local_models
    ]

    # The manifest schema expects at least one option. If Ollama is unavailable
    # or no models are installed, keep the preferred default visible so the
    # manifest can still render and the user gets a useful model name to install.
    if not model_options:
        model_options = [
            {"label": ai_DEFAULT_OLLAMA_MODEL, "value": ai_DEFAULT_OLLAMA_MODEL}
        ]

    model_default = (
        ai_DEFAULT_OLLAMA_MODEL
        if ai_DEFAULT_OLLAMA_MODEL in local_models
        else model_options[0]["value"]
    )

    try:
        await ai_websocket.send(
            json.dumps(
                {
                    "type": "plugin_manifest",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": ai_PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "name": ai_PLUGIN_NAME,
                        "id": ai_PLUGIN_ID,
                        "version": ai_PLUGIN_VERSION,
                        "description": (
                            "Uses Ollama and a rolling screenshot window to detect "
                            "TV commercial transitions."
                        ),
                        "primaryColor": "#000000",
                        "secondaryColor": "#FFFFFF",
                        "capabilities": [
                            "trigger",
                            "screenshots",
                        ],
                        "preferences": [
                            {
                                "key": "ollama-model",
                                "label": "Ollama Model",
                                "tooltip": (
                                    "Local Ollama model used for screenshot analysis. "
                                    "Only models currently installed in Ollama are listed."
                                ),
                                "type": "select",
                                "options": model_options,
                                "default": model_default,
                            },
                            {
                                "key": "ollama-context-size",
                                "label": "Ollama Context Size",
                                "description": (
                                    "Maximum context window requested from Ollama. Runtime "
                                    "Default does not send num_ctx and lets Ollama decide. "
                                    "Larger values can use more memory."
                                ),
                                "type": "select",
                                "options": [
                                    {"label": "Runtime Default", "value": "runtime-default"},
                                    {"label": "4,096 tokens", "value": "4096"},
                                    {"label": "5K tokens", "value": "5000"},
                                    {"label": "6K tokens", "value": "6000"},
                                    {"label": "7K tokens", "value": "7000"},
                                    {"label": "8,192 tokens", "value": "8192"},
                                    {"label": "12K tokens", "value": "12000"},
                                    {"label": "16,384 tokens", "value": "16384"},
                                    {"label": "32,768 tokens", "value": "32768"},
                                    {"label": "65,536 tokens", "value": "65536"},
                                ],
                                "default": "runtime-default",
                            },
                            {
                                "key": "commercial-prompt",
                                "label": "Commercial Prompt",
                                "tooltip": (
                                    "Prompt used while regular programming is active to "
                                    "decide whether the screenshots indicate a commercial. "
                                    "Try to have answer start with YES or NO."
                                ),
                                "type": "textarea",
                                "default": ai_DEFAULT_COMMERCIAL_PROMPT,
                            },
                            {
                                "key": "non-commercial-prompt",
                                "label": "Non-Commercial Prompt",
                                "tooltip": (
                                    "Prompt used while a commercial is active to decide "
                                    "whether regular programming has returned. "
                                    "Try to have answer start with YES or NO."
                                ),
                                "type": "textarea",
                                "default": ai_DEFAULT_NON_COMMERCIAL_PROMPT,
                            },
                            {
                                "key": "regular-llm-call-frequency-seconds",
                                "label": "Regular Programming LLM Call Frequency (Seconds)",
                                "tooltip": (
                                    "Minimum seconds between Ollama call starts while "
                                    "regular programming is active. Set to 0 to run again "
                                    "as soon as the prior call finishes and fresh screenshots exist."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_REGULAR_LLM_CALL_FREQUENCY_SECONDS,
                                "min": 0,
                            },
                            {
                                "key": "commercial-llm-call-frequency-seconds",
                                "label": "Commercial LLM Call Frequency (Seconds)",
                                "tooltip": (
                                    "Minimum seconds between Ollama call starts while a "
                                    "commercial is active. Set to 0 to run again as soon as "
                                    "the prior call finishes and fresh screenshots exist."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_COMMERCIAL_LLM_CALL_FREQUENCY_SECONDS,
                                "min": 0,
                            },
                            {
                                "key": "regular-consecutive-yes-required",
                                "label": "Regular Programming Consecutive YES Responses Required",
                                "tooltip": (
                                    "YES responses required in a row before entering a "
                                    "commercial. NO resets the count; UNKNOWN leaves it unchanged."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_REGULAR_CONSECUTIVE_YES_REQUIRED,
                                "min": 1,
                            },
                            {
                                "key": "commercial-consecutive-yes-required",
                                "label": "Commercial Consecutive YES Responses Required",
                                "tooltip": (
                                    "YES responses required in a row before returning to "
                                    "regular programming. NO resets the count; UNKNOWN leaves it unchanged."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_COMMERCIAL_CONSECUTIVE_YES_REQUIRED,
                                "min": 1,
                            },
                            {
                                "key": "regular-screenshot-batch-size",
                                "label": "Regular Programming Screenshot Batch Size",
                                "tooltip": (
                                    "Number of rolling screenshots sent to Ollama while "
                                    "regular programming is active."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE,
                                "min": 1,
                            },
                            {
                                "key": "commercial-screenshot-batch-size",
                                "label": "Commercial Screenshot Batch Size",
                                "tooltip": (
                                    "Number of rolling screenshots sent to Ollama while a "
                                    "commercial is active."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_COMMERCIAL_SCREENSHOT_BATCH_SIZE,
                                "min": 1,
                            },
                            {
                                "key": "regular-screenshot-frequency-milliseconds",
                                "label": "Regular Programming Screenshot Frequency (Milliseconds)",
                                "tooltip": (
                                    "How frequently the browser captures screenshots while "
                                    "regular programming is active."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_REGULAR_SCREENSHOT_FREQUENCY_MILLISECONDS,
                                "min": 1,
                            },
                            {
                                "key": "commercial-screenshot-frequency-milliseconds",
                                "label": "Commercial Screenshot Frequency (Milliseconds)",
                                "tooltip": (
                                    "How frequently the browser captures screenshots while "
                                    "a commercial is active."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_COMMERCIAL_SCREENSHOT_FREQUENCY_MILLISECONDS,
                                "min": 1,
                            },
                            {
                                "key": "regular-screenshot-max-width",
                                "label": "Regular Programming Screenshot Max Width (Pixels)",
                                "tooltip": (
                                    "Maximum screenshot width while regular programming is active. "
                                    "The extension should preserve the screenshot aspect ratio."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_REGULAR_SCREENSHOT_MAX_WIDTH,
                                "min": 1,
                            },
                            {
                                "key": "regular-screenshot-max-height",
                                "label": "Regular Programming Screenshot Max Height (Pixels)",
                                "tooltip": (
                                    "Maximum screenshot height while regular programming is active. "
                                    "The extension should preserve the screenshot aspect ratio."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_REGULAR_SCREENSHOT_MAX_HEIGHT,
                                "min": 1,
                            },
                            {
                                "key": "commercial-screenshot-max-width",
                                "label": "Commercial Screenshot Max Width (Pixels)",
                                "tooltip": (
                                    "Maximum screenshot width while a commercial is active. The "
                                    "extension should preserve the screenshot aspect ratio."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_COMMERCIAL_SCREENSHOT_MAX_WIDTH,
                                "min": 1,
                            },
                            {
                                "key": "commercial-screenshot-max-height",
                                "label": "Commercial Screenshot Max Height (Pixels)",
                                "tooltip": (
                                    "Maximum screenshot height while a commercial is active. The "
                                    "extension should preserve the screenshot aspect ratio."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_COMMERCIAL_SCREENSHOT_MAX_HEIGHT,
                                "min": 1,
                            },
                            {
                                "key": "into-commercial-cooldown-seconds",
                                "label": "Going Into Commercial Cooldown (Seconds)",
                                "tooltip": (
                                    "After entering a commercial, AI analysis continues but its "
                                    "decisions are ignored for this many seconds."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_INTO_COMMERCIAL_COOLDOWN_SECONDS,
                                "min": 0,
                            },
                            {
                                "key": "out-of-commercial-cooldown-seconds",
                                "label": "Going Out of Commercial Cooldown (Seconds)",
                                "tooltip": (
                                    "After returning to regular programming, AI analysis continues "
                                    "but its decisions are ignored for this many seconds."
                                ),
                                "type": "number",
                                "default": ai_DEFAULT_OUT_OF_COMMERCIAL_COOLDOWN_SECONDS,
                                "min": 0,
                            },
                            {
                                "key": "screenshot-trim-top-percent",
                                "label": "Screenshot Trim Top (%)",
                                "tooltip": "Percentage to trim from the top of each screenshot.",
                                "type": "number",
                                "default": ai_DEFAULT_SCREENSHOT_TRIM_TOP_PERCENT,
                                "min": 0,
                                "max": 100,
                            },
                            {
                                "key": "screenshot-trim-right-percent",
                                "label": "Screenshot Trim Right (%)",
                                "tooltip": "Percentage to trim from the right of each screenshot.",
                                "type": "number",
                                "default": ai_DEFAULT_SCREENSHOT_TRIM_RIGHT_PERCENT,
                                "min": 0,
                                "max": 100,
                            },
                            {
                                "key": "screenshot-trim-bottom-percent",
                                "label": "Screenshot Trim Bottom (%)",
                                "tooltip": "Percentage to trim from the bottom of each screenshot.",
                                "type": "number",
                                "default": ai_DEFAULT_SCREENSHOT_TRIM_BOTTOM_PERCENT,
                                "min": 0,
                                "max": 100,
                            },
                            {
                                "key": "screenshot-trim-left-percent",
                                "label": "Screenshot Trim Left (%)",
                                "tooltip": "Percentage to trim from the left of each screenshot.",
                                "type": "number",
                                "default": ai_DEFAULT_SCREENSHOT_TRIM_LEFT_PERCENT,
                                "min": 0,
                                "max": 100,
                            },
                        ],
                    },
                    "meta": {
                        "display": "Sending Manifest",
                        "debug": "Sending Manifest",
                    },
                }
            )
        )
    except websockets.exceptions.ConnectionClosed:
        print("send_manifest stopped: client disconnected")


async def ai_main():
    async with websockets.serve(ai_handle_client, "localhost", ai_PORT):
        print(f"Server running on ws://localhost:{ai_PORT}")
        print(f"Ollama host: {ai_OLLAMA_HOST}")
        print(f"Default Ollama model: {ai_DEFAULT_OLLAMA_MODEL}")
        print("Default Ollama context size: Runtime Default")
        await asyncio.Future()


# Standalone plugin entrypoint intentionally disabled in the combined Party Pack.


# =============================================================================
# Bundled plugin source: overlay-any-window.py
# Prefix: window_
# =============================================================================
import asyncio
import json
import time

import websockets
import win32api
import win32con
import win32gui
import win32process

from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

window_PLUGIN_PROTOCOL_VERSION = 1 # DO NOT TOUCH

window_PLUGIN_NAME = "Overlay Any Window"
window_PLUGIN_ID = "overlay-any-window" # Must be unique
window_PLUGIN_VERSION = "1.1.0"

window_PORT = 64146
window_SPACEBAR_KEY = 0x20


def window_get_window_dropdown_options():
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


def window_find_window_by_title(title):
    """Find a visible window whose title exactly matches the selected title."""
    matching_windows = []

    def enum_handler(hwnd, result):
        if not win32gui.IsWindowVisible(hwnd):
            return

        if win32gui.GetWindowText(hwnd).strip() == title:
            result.append(hwnd)

    win32gui.EnumWindows(enum_handler, matching_windows)
    return matching_windows[0] if matching_windows else None


def window_mute_application_of_window(hwnd, mute=True):
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


def window_send_spacebar(hwnd):
    """Send a spacebar press to a window without activating it."""
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, window_SPACEBAR_KEY, 0)
    time.sleep(0.05)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, window_SPACEBAR_KEY, 0)


def window_calculate_window_position(
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


def window_position_and_resize_window(
    hwnd,
    width_percent=90,
    height_percent=75,
    vertical="middle",
    horizontal="middle",
):
    """Show, resize, position, and temporarily keep a window on top."""
    x, y, width, height = window_calculate_window_position(
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


def window_remove_topmost(hwnd, width_percent=90, height_percent=75):
    """Remove topmost status and place the window near the bottom of the stack."""
    x, y, width, height = window_calculate_window_position(
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


def window_minimize_window(hwnd):
    """Minimize a window."""
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)


def window_make_borderless(hwnd):
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


def window_restore_borders(hwnd):
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


def window_get_overlay_settings(message):
    """Read the extension and plugin preferences from a message."""
    preferences = message.get("data", {}).get("preferences", {})
    plugin_preferences = preferences.get("pluginPreferencesById", {}).get(window_PLUGIN_ID, {}).get("preferences", {})

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


def window_show_pip_window(hwnd, settings):
    """Show the selected window using the configured picture-in-picture size."""
    window_position_and_resize_window(
        hwnd,
        width_percent=settings["pip_width"],
        height_percent=settings["pip_height"],
        vertical=settings["pip_vertical"],
        horizontal=settings["pip_horizontal"],
    )


def window_show_overlay_window(hwnd, settings):
    """Show the selected window using the configured overlay size."""
    window_position_and_resize_window(
        hwnd,
        width_percent=settings["overlay_width"],
        height_percent=settings["overlay_height"],
        vertical=settings["overlay_vertical"],
        horizontal=settings["overlay_horizontal"],
    )


async def window_handle_client(websocket):
    print("Client connected")

    try:
        async for raw_message in websocket:
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await window_send_status(
                    websocket,
                    "Invalid message",
                    "The plugin received invalid JSON.",
                )
                continue

            await window_handle_message(websocket, message)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        print("Client disconnected")


async def window_handle_message(websocket, message):
    message_type = message.get("type")
    print(f"Received message: {message_type}")

    if message_type == "plugin_manifest":
        await window_send_manifest(websocket)
        return

    settings = window_get_overlay_settings(message)
    window_title = settings["window_title"]

    if not window_title:
        await window_send_status(
            websocket,
            "No window selected",
            "The window-title preference is empty.",
        )
        return

    hwnd = window_find_window_by_title(window_title)

    if hwnd is None:
        await window_send_status(
            websocket,
            f'Could not find "{window_title}"',
            f'Could not find a visible window titled "{window_title}".',
        )
        return

    if message_type == "init":
        window_make_borderless(hwnd)
        window_remove_topmost(hwnd, width_percent=90, height_percent=85) # For some reason running this at the begining helps the window come forward later
        time.sleep(0.5)

        if settings["is_pip_mode"]:
            window_show_pip_window(hwnd, settings)
        else:
            window_minimize_window(hwnd)

        if settings["should_mute"]:
            window_mute_application_of_window(hwnd, mute=True)

        print("Extension initiated.")
        return

    if message_type == "commercial_state_change":
        is_commercial = bool(
            message.get("data", {}).get("isCommercialState", False)
        )

        if is_commercial:
            print("Starting overlay.")
            window_show_overlay_window(hwnd, settings)

            if settings["should_mute"]:
                window_mute_application_of_window(hwnd, mute=False)

            if settings["should_send_spacebar"]:
                time.sleep(0.5)
                window_send_spacebar(hwnd)

        else:
            print("Stopping overlay.")

            if settings["should_send_spacebar"]:
                window_send_spacebar(hwnd)
                time.sleep(0.4)

            if settings["should_mute"]:
                window_mute_application_of_window(hwnd, mute=True)

            if settings["is_pip_mode"]:
                window_show_pip_window(hwnd, settings)
            else:
                window_minimize_window(hwnd)

        return

    if message_type == "browser_fullscreen_state_change":
        is_fullscreen = bool(
            message.get("data", {}).get("isFullscreen", False)
        )

        if is_fullscreen:
            print("Browser entered fullscreen.")

            if settings["should_mute"]:
                window_mute_application_of_window(hwnd, mute=True)

            window_make_borderless(hwnd)

            if settings["is_pip_mode"]:
                window_show_pip_window(hwnd, settings)

        else:
            print("Browser exited fullscreen.")

            if settings["should_mute"]:
                window_mute_application_of_window(hwnd, mute=False)

            window_remove_topmost(hwnd, width_percent=90, height_percent=85)
            window_restore_borders(hwnd)

        return

    if message_type == "end":
        print("Extension stopped.")

        # Always unmute during cleanup in case the preference changed while
        # the extension was running.
        window_mute_application_of_window(hwnd, mute=False)
        window_remove_topmost(hwnd, width_percent=90, height_percent=75)
        window_restore_borders(hwnd)
        return

    await window_send_status(
        websocket,
        "Unknown message",
        f'Unsupported message type: "{message_type}".',
    )


async def window_send_status(websocket, display, debug):
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


async def window_send_manifest(websocket):
    window_options = window_get_window_dropdown_options()

    manifest = {
        "type": "plugin_manifest",
        "timestamp": time.time(),
        "pluginProtocolVersion": window_PLUGIN_PROTOCOL_VERSION,
        "data": {
            "name": window_PLUGIN_NAME,
            "id": window_PLUGIN_ID,
            "version": window_PLUGIN_VERSION,
            "description": (
                "Overlay any window from any open application. This plugin uses the "
                "overlay and picture-in-picture size and location settings "
                "from the extension's additional settings."
            ),
            "primaryColor": "#ffffff",
            "secondaryColor": "#0078D7",
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


async def window_main():
    async with websockets.serve(window_handle_client, "localhost", window_PORT):
        print(f"Server running on ws://localhost:{window_PORT}")
        await asyncio.Future()


# =============================================================================
# Bundled plugin source: say-no-to-commercials.py
# Prefix: voice_
# =============================================================================
import asyncio
import websockets
import json
import time
import queue
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import os
import re
import shutil
import urllib.request
import zipfile

voice_PLUGIN_PROTOCOL_VERSION = 1 # DO NOT TOUCH

voice_PLUGIN_NAME = "Say NO to Commercials"
voice_PLUGIN_ID = "speak-keyword-trigger-plugin" # Must be unique
voice_PLUGIN_VERSION = "1.0.1"

voice_PORT = 64145

voice_clients = set()

# --------------------------------------------------
# Configuration
# --------------------------------------------------

voice_BASE_DIR = str(APP_DIR)
voice_MODEL_DIR = os.path.join(voice_BASE_DIR, "model")
voice_MODEL_NAME = "vosk-model-small-en-us-0.15"
voice_MODEL_PATH = os.path.join(voice_MODEL_DIR, voice_MODEL_NAME)
voice_MODEL_URL = f"https://alphacephei.com/vosk/models/{voice_MODEL_NAME}.zip"
voice_MODEL_ZIP_PATH = os.path.join(voice_MODEL_DIR, f"{voice_MODEL_NAME}.zip")

voice_DEFAULT_COMMERCIAL_PHRASE = "tomato"
voice_DEFAULT_COMMERCIAL_EMOJI = "\U0001F345"
voice_DEFAULT_CONTENT_PHRASE = "banana"
voice_DEFAULT_CONTENT_EMOJI = "\U0001F34C"

voice_TARGET_PHRASES = {}

voice_COOLDOWN = 3.0

# --------------------------------------------------
# Global state
# --------------------------------------------------

voice_listening_task = None
voice_listening_active = asyncio.Event()
voice_audio_queue = queue.Queue()

voice_current_is_commercial = None

# --------------------------------------------------
# Helpers
# --------------------------------------------------

async def voice_ensure_vosk_model(ws):
    """Create, download, and extract the Vosk model when it is missing."""
    if os.path.isdir(voice_MODEL_PATH):
        return True

    os.makedirs(voice_MODEL_DIR, exist_ok=True)

    await voice_send_status(
        ws,
        "Downloading voice model: 0%",
        f"Vosk model not found at {voice_MODEL_PATH}",
    )

    loop = asyncio.get_running_loop()
    last_reported_percent = -1

    def download_progress(block_number, block_size, total_size):
        """Report download progress from urllib's worker thread."""
        nonlocal last_reported_percent

        if total_size <= 0:
            return

        downloaded = block_number * block_size
        percent = min(100, int(downloaded * 100 / total_size))

        # Updating every 5% avoids flooding the WebSocket with messages.
        report_percent = min(100, (percent // 5) * 5)
        if report_percent == last_reported_percent:
            return

        last_reported_percent = report_percent
        print(
            f"\rDownloading Vosk model: {percent:3d}%",
            end="",
            flush=True,
        )

        loop.call_soon_threadsafe(
            asyncio.create_task,
            voice_send_status(
                ws,
                f"Downloading voice model: {report_percent}%",
                f"Downloading {voice_MODEL_NAME}",
            ),
        )

    try:
        print(f"Vosk model not found at: {voice_MODEL_PATH}")
        print(f"Downloading {voice_MODEL_NAME}...")

        # urlretrieve is blocking, so run it outside the asyncio event loop.
        await asyncio.to_thread(
            urllib.request.urlretrieve,
            voice_MODEL_URL,
            voice_MODEL_ZIP_PATH,
            download_progress,
        )
        print()

        await voice_send_status(
            ws,
            "Extracting voice model...",
            f"Extracting {voice_MODEL_NAME}",
        )
        print("Extracting Vosk model...")

        def extract_model():
            with zipfile.ZipFile(voice_MODEL_ZIP_PATH, "r") as archive:
                archive.extractall(voice_MODEL_DIR)

        await asyncio.to_thread(extract_model)

        if not os.path.isdir(voice_MODEL_PATH):
            raise FileNotFoundError(
                f"The archive was extracted, but {voice_MODEL_PATH} was not created."
            )

        print("Vosk model is ready.")
        await voice_send_status(
            ws,
            "Voice model downloaded",
            f"{voice_MODEL_NAME} is ready",
        )
        return True

    except Exception as error:
        print(f"Could not download or extract the Vosk model: {error}")
        await voice_send_status(
            ws,
            "Voice model download failed",
            str(error),
        )

        # Remove an incomplete model folder so the next run can retry cleanly.
        if os.path.isdir(voice_MODEL_PATH):
            await asyncio.to_thread(shutil.rmtree, voice_MODEL_PATH, True)

        return False

    finally:
        if os.path.isfile(voice_MODEL_ZIP_PATH):
            try:
                os.remove(voice_MODEL_ZIP_PATH)
            except OSError:
                pass


def voice_normalize_unicode(value):
    """Combine UTF-16 surrogate pairs into normal Unicode characters."""
    if not isinstance(value, str):
        return value

    try:
        return value.encode("utf-16", "surrogatepass").decode("utf-16")
    except UnicodeError:
        return value


def voice_clean_preference(value, default):
    """Return a trimmed preference value, or its default when blank/missing."""
    if not isinstance(value, str):
        return default

    value = voice_normalize_unicode(value).strip()
    return value if value else default


def voice_apply_preferences(preferences):
    """Build the active phrase configuration from plugin preferences."""
    global voice_TARGET_PHRASES

    commercial_phrase = voice_clean_preference(
        preferences.get("commercial-trigger-phrase"),
        voice_DEFAULT_COMMERCIAL_PHRASE,
    ).lower()
    commercial_emoji = voice_clean_preference(
        preferences.get("commercial-trigger-emoji"),
        voice_DEFAULT_COMMERCIAL_EMOJI,
    )
    content_phrase = voice_clean_preference(
        preferences.get("content-trigger-phrase"),
        voice_DEFAULT_CONTENT_PHRASE,
    ).lower()
    content_emoji = voice_clean_preference(
        preferences.get("content-trigger-emoji"),
        voice_DEFAULT_CONTENT_EMOJI,
    )

    voice_TARGET_PHRASES = {
        commercial_phrase: {
            "action": "commercial",
            "emoji": commercial_emoji,
        },
        content_phrase: {
            "action": "content",
            "emoji": content_emoji,
        },
    }

    print("Active voice triggers:")
    print(f"  Commercial: {commercial_phrase!r} {commercial_emoji}")
    print(f"  Content:    {content_phrase!r} {content_emoji}")


def voice_get_all_emojis_for_action(action):
    return " ".join(
        config["emoji"]
        for config in voice_TARGET_PHRASES.values()
        if config.get("action") == action
    )

def voice_audio_callback(indata, frames, time_info, status):
    if status:
        print("Audio status:", status)
    voice_audio_queue.put(bytes(indata))

def voice_find_trigger_config(text):
    """Find a configured word or multi-word phrase in recognized speech."""
    normalized_text = " ".join(text.lower().split())

    # Check longer phrases first in case one trigger is contained in another.
    sorted_phrases = sorted(voice_TARGET_PHRASES, key=len, reverse=True)

    for phrase in sorted_phrases:
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
        if re.search(pattern, normalized_text):
            return phrase, voice_TARGET_PHRASES[phrase]

    return None, None

async def voice_handle_trigger(ws, phrase, config, now, last_trigger_time, source):
    global voice_current_is_commercial

    if now - last_trigger_time <= voice_COOLDOWN:
        return last_trigger_time

    # Determine desired state
    new_is_commercial = config["action"] == "commercial"

    # Only trigger if state would change
    if voice_current_is_commercial is not None and new_is_commercial == voice_current_is_commercial:
        print(f"IGNORED ({source}): already in desired state")
        return last_trigger_time

    print(f"TRIGGERED ({source}):", config["action"])

    display = "\U0001F5E3 \u2705"

    await voice_send_commercial_state_change(
        ws,
        new_is_commercial,
        display,
        f"Keyword Detected ({source})"
    )

    voice_current_is_commercial = new_is_commercial

    return now

async def voice_process_text(ws, text, now, last_trigger_time, source, last_partial_text):
    if not text:
        return last_trigger_time, last_partial_text

    if source == "partial":
        if text == last_partial_text:
            return last_trigger_time, last_partial_text

        print("[PARTIAL]", text)
        last_partial_text = text

        #await send_status(ws, None, text)

    else:
        print("[FINAL]", text)

    await voice_send_status(ws, None, source + ":" + text) #TODO: does this make sense here?

    phrase, config = voice_find_trigger_config(text)

    if config:
        last_trigger_time = await voice_handle_trigger(
            ws,
            phrase,
            config,
            now,
            last_trigger_time,
            source
        )

    return last_trigger_time, last_partial_text

# --------------------------------------------------
# Voice loop
# --------------------------------------------------

async def voice_listen_loop(ws):
    try:
        if not await voice_ensure_vosk_model(ws):
            return

        print("Loading Vosk model...")
        await voice_send_status(
            ws,
            "Loading Voice model...",
            "Loading Vosk model...",
        )
        model = Model(voice_MODEL_PATH)

        recognizer = KaldiRecognizer(model, 16000)

        last_trigger_time = 0
        last_partial_text = ""

        while True:
            await voice_listening_active.wait()
            print("Listening started")
            await voice_send_status(
                ws,
                "\U0001F5E3 " + voice_get_all_emojis_for_action("commercial"),
                "Ready"
            )

            with sd.RawInputStream(
                samplerate=16000,
                blocksize=4000,
                dtype="int16",
                channels=1,
                callback=voice_audio_callback
            ):
                while voice_listening_active.is_set():
                    data = voice_audio_queue.get()
                    now = time.time()

                    if recognizer.AcceptWaveform(data):
                        result = json.loads(recognizer.Result())
                        text = result.get("text", "").lower().strip()

                        last_trigger_time, last_partial_text = await voice_process_text(
                            ws, text, now, last_trigger_time, "final", last_partial_text
                        )

                    else:
                        partial = json.loads(recognizer.PartialResult())
                        text = partial.get("partial", "").lower().strip()

                        last_trigger_time, last_partial_text = await voice_process_text(
                            ws, text, now, last_trigger_time, "partial", last_partial_text
                        )

                    await asyncio.sleep(0)

            print("Listening stopped")

    except asyncio.CancelledError:
        print("listen_loop shutting down")
        raise

# --------------------------------------------------
# WebSocket handling
# --------------------------------------------------

async def voice_handle_client(websocket):
    global voice_listening_task

    print("Client connected")
    voice_clients.add(websocket)

    try:
        async for message in websocket:
            msg = json.loads(message)
            await voice_handle_message(websocket, msg)

    except websockets.exceptions.ConnectionClosed:
        pass

    finally:
        voice_clients.remove(websocket)

        if len(voice_clients) == 0:
            print("Stopping listener (no clients)")
            voice_listening_active.clear()

            if voice_listening_task:
                voice_listening_task.cancel()
                try:
                    await voice_listening_task
                except asyncio.CancelledError:
                    print("Listening task cancelled")

                voice_listening_task = None

        print("Client disconnected")

# --------------------------------------------------
# Message handling
# --------------------------------------------------

async def voice_handle_message(ws, msg):
    global voice_listening_task, voice_current_is_commercial

    message_type = msg.get("type")
    data = msg.get("data", {})
    full_preferences = data.get("preferences", {})
    custom_trigger_plugin_preferences = full_preferences.get("pluginPreferencesById", {}).get(voice_PLUGIN_ID, {}).get("preferences", {})

    # Preference values are normally returned with init, but applying them
    # whenever present also supports preference updates without restarting.
    if custom_trigger_plugin_preferences:
        voice_apply_preferences(custom_trigger_plugin_preferences)

    if message_type == "plugin_manifest":
        await voice_send_manifest(ws)

    elif message_type == "init":
        # Initialize global state if provided
        voice_current_is_commercial = msg.get("data", {}).get("isCommercialState")

        await voice_send_status(
            ws,
            "\U0001F5E3 " + voice_get_all_emojis_for_action("commercial"),
            "Ready"
        )

        voice_listening_active.set()

        if not voice_listening_task:
            print("Starting listening task")
            voice_listening_task = asyncio.create_task(voice_listen_loop(ws))

    elif message_type == "commercial_state_change":
        voice_current_is_commercial = msg["data"]["isCommercialState"]

        new_display = "\U0001F5E3 " + voice_get_all_emojis_for_action("commercial")

        if voice_current_is_commercial:
            new_display = "\U0001F5E3 " + voice_get_all_emojis_for_action("content")

        await voice_send_status(ws, new_display, "update display")

    elif message_type == "browser_fullscreen_state_change":
        print("Fullscreen:", msg["data"]["isFullscreen"])

# --------------------------------------------------
# Send helpers
# --------------------------------------------------

async def voice_send_commercial_state_change(ws, is_commercial, display, debug):
    try:
        await ws.send(json.dumps({
            "type": "commercial_state_change",
            "timestamp": time.time(),
            "data": {"isCommercial": is_commercial},
            "meta": {"display": display, "debug": debug}
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_commercial_state_change failed")

async def voice_send_status(ws, display, debug):
    try:
        await ws.send(json.dumps({
            "type": "status",
            "timestamp": time.time(),
            "data": {},
            "meta": {"display": display, "debug": debug}
        }))
    except websockets.exceptions.ConnectionClosed:
        pass

async def voice_send_manifest(ws):
    try:
        await ws.send(json.dumps({
            "type": "plugin_manifest",
            "timestamp": time.time(),
            "pluginProtocolVersion": voice_PLUGIN_PROTOCOL_VERSION,
            "data": {
                "name": voice_PLUGIN_NAME,
                "id": voice_PLUGIN_ID,
                "version": voice_PLUGIN_VERSION,
                "description": (
                    "Use keywords and/or phrases to block out commercials! Note: If mic is "
                    "close to TV speakers, it is best to set as single words that are not "
                    "commonly used in the broadcast and to shout the word three times "
                    "to guarantee trigger. Otherwise, set mic away from TV speakers for better results."
                ),
                "primaryColor": "#8B0000", # Optional
                "secondaryColor": "#FFFFE0", # Optional
                "capabilities": ["detection"],
                "preferences": [
                    {
                        "key": "commercial-trigger-phrase",
                        "label": "Commercial Trigger Word or Phrase",
                        "tooltip": "Say this word or phrase to mark a commercial break.",
                        "type": "text",
                        "default": voice_DEFAULT_COMMERCIAL_PHRASE,
                    },
                    {
                        "key": "commercial-trigger-emoji",
                        "label": "Commercial Trigger Emoji",
                        "tooltip": "Emoji shown while waiting for the commercial trigger.",
                        "type": "text",
                        "default": voice_DEFAULT_COMMERCIAL_EMOJI,
                    },
                    {
                        "key": "content-trigger-phrase",
                        "label": "Content Trigger Word or Phrase",
                        "tooltip": "Say this word or phrase when regular content resumes.",
                        "type": "text",
                        "default": voice_DEFAULT_CONTENT_PHRASE,
                    },
                    {
                        "key": "content-trigger-emoji",
                        "label": "Content Trigger Emoji",
                        "tooltip": "Emoji shown while waiting for the content trigger.",
                        "type": "text",
                        "default": voice_DEFAULT_CONTENT_EMOJI,
                    },
                ], # Optional
            },
            "meta": {
                "display": "Sending Manifest",
                "debug": "Sending Manifest",
            },
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_status send stopped: client disconnected")


# Start with defaults until preferences arrive from the extension.
voice_apply_preferences({})

# --------------------------------------------------
# Main
# --------------------------------------------------

async def voice_main():
    async with websockets.serve(voice_handle_client, "localhost", voice_PORT):
        print(f"Server running on ws://localhost:{voice_PORT}")
        await asyncio.Future()

# Standalone plugin entrypoint intentionally disabled in the combined Party Pack.


# =============================================================================
# Bundled plugin source: thumbs-down-commercials.py
# Prefix: gesture_
# =============================================================================

import asyncio
import websockets
import json
import time
import os
import cv2
import base64
import platform
import aiohttp

from pygrabber.dshow_graph import FilterGraph
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import mediapipe as mp

gesture_PLUGIN_PROTOCOL_VERSION = 1 # DO NOT TOUCH

gesture_PLUGIN_NAME = "Peace Out Commercials"
gesture_PLUGIN_ID = "gesture-trigger-plugin"
gesture_PLUGIN_VERSION = "1.1.0"

# --------------------------------------------------
# Configuration
# --------------------------------------------------

gesture_PORT = 64145

gesture_BASE_DIR = str(APP_DIR)
gesture_MODEL_PATH = os.path.join(gesture_BASE_DIR, "gesture_recognizer.task")
gesture_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "gesture_recognizer/gesture_recognizer/float16/latest/"
    "gesture_recognizer.task"
)

gesture_is_debug_mode = False
gesture_CAMERA_INDEX = 0
gesture_MIRROR_CAMERA = True

# default values
gesture_COMMERCIAL_GESTURE = "Victory"
gesture_CONTENT_GESTURE = "ILoveYou"
gesture_COMMERCIAL_GESTURE_COUNT = 1
gesture_CONTENT_GESTURE_COUNT = 1
gesture_TOTAL_HANDS_PROCESSED = 4

# MediaPipe Gesture Recognizer canned gesture names.
gesture_GESTURE_OPTIONS = {
    "Closed_Fist": {"label": "Closed Fist \u270A", "emoji": "\u270A"},
    "Open_Palm": {"label": "Open Palm \u270B", "emoji": "\u270B"},
    "Pointing_Up": {"label": "Pointing Up \u261D\uFE0F", "emoji": "\u261D\uFE0F"},
    "Thumb_Down": {"label": "Thumb Down \uD83D\uDC4E", "emoji": "\uD83D\uDC4E"},
    "Thumb_Up": {"label": "Thumb Up \uD83D\uDC4D", "emoji": "\uD83D\uDC4D"},
    "Victory": {"label": "Victory \u270C\uFE0F", "emoji": "\u270C\uFE0F"},
    "ILoveYou": {"label": "I Love You \uD83E\uDD1F", "emoji": "\uD83E\uDD1F"},
}

gesture_REQUIRED_GESTURE_COUNTS = {}
gesture_TARGET_GESTURES = {}

gesture_GREEN_SQUARE = "\uD83D\uDFE9"
gesture_CHECK_BUTTON = "\u2705"
gesture_HAND_PREFIX = ""
gesture_DEBUG_TRIGGER_DISPLAY_DURATION = 2.0

gesture_THRESHOLDS = [
    (0.90, 0.1),
    (0.80, 0.3),
    (0.57, 0.8),
]

gesture_CAMERA_RESOLUTION = "native"

# Sensitivity scale: 1 = less sensitive, 5 = more sensitive.
# A value of 3 uses THRESHOLDS exactly as defined above.
gesture_COMMERCIAL_SENSITIVITY = 3
gesture_CONTENT_SENSITIVITY = 3

gesture_COOLDOWN = 1.0

gesture_SNAPSHOT_MAX_WIDTH = 400
gesture_SNAPSHOT_MAX_HEIGHT = 400

# --------------------------------------------------
# Global state
# --------------------------------------------------

gesture_clients = set()

gesture_camera_task = None
gesture_camera_active = asyncio.Event()

gesture_camera_options = None
gesture_default_camera = None

gesture_current_is_commercial = None
gesture_last_status_display = None

gesture_gesture_group_states = {}

gesture_any_trigger_display_until = time.time()

# --------------------------------------------------
# Model management
# --------------------------------------------------

async def gesture_ensure_model_exists(ws):
    """
    Download the MediaPipe gesture model if it is not already present.

    Returns:
        True if the model exists and appears valid.
        False if the download or validation fails.
    """

    if os.path.isfile(gesture_MODEL_PATH) and os.path.getsize(gesture_MODEL_PATH) > 0:
        print(f"Model found: {gesture_MODEL_PATH}")
        return True

    await gesture_send_status(
        ws,
        "Downloading AI model...",
        "Downloading MediaPipe Gesture Recognizer model..."
    )

    print("Gesture recognizer model was not found.")
    print("Downloading MediaPipe model...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(gesture_MODEL_URL) as response:
                response.raise_for_status()

                with open(gesture_MODEL_PATH, "wb") as f:
                    total = int(response.headers.get("Content-Length", 0))
                    downloaded = 0

                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        downloaded += len(chunk)
                        f.write(chunk)

                        if total:
                            percent = int(downloaded * 100 / total)

                            await gesture_send_status(
                                ws,
                                f"Downloading AI model... {percent}%",
                                f"Downloaded {downloaded:,} / {total:,} bytes"
                            )

        return True

    except Exception as error:
        print(f"Failed to download gesture model: {error}")

        return False

# --------------------------------------------------
# Preference helpers
# --------------------------------------------------

def gesture_clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def gesture_rebuild_target_gestures():
    """Rebuild runtime gesture mappings from the current preferences."""
    global gesture_TARGET_GESTURES
    global gesture_REQUIRED_GESTURE_COUNTS
    global gesture_gesture_group_states

    gesture_TARGET_GESTURES = {
        gesture_COMMERCIAL_GESTURE: {
            "action": "commercial",
            "emoji": gesture_GESTURE_OPTIONS[gesture_COMMERCIAL_GESTURE]["emoji"],
        },
        gesture_CONTENT_GESTURE: {
            "action": "content",
            "emoji": gesture_GESTURE_OPTIONS[gesture_CONTENT_GESTURE]["emoji"],
        },
    }

    gesture_REQUIRED_GESTURE_COUNTS = {
        gesture_COMMERCIAL_GESTURE: gesture_COMMERCIAL_GESTURE_COUNT,
        gesture_CONTENT_GESTURE: gesture_CONTENT_GESTURE_COUNT,
    }

    gesture_gesture_group_states.clear()


def gesture_get_video_capture_backend():
    # DirectShow generally avoids slow camera probing on Windows.
    if platform.system() == "Windows":
        return cv2.CAP_DSHOW
    return cv2.CAP_ANY


def gesture_get_available_cameras(max_index=10):
    """
    Return available cameras for the manifest.

    On Windows, pygrabber is used to get each camera's DirectShow-friendly
    device name. The stored value remains the numeric camera index expected
    by OpenCV.
    """
    cameras = []

    if platform.system() == "Windows":
        try:
            graph = FilterGraph()
            camera_names = graph.get_input_devices()

            for index, name in enumerate(camera_names):
                cameras.append({
                    "label": f"{name} (Camera {index})",
                    "value": str(index),
                })

            if cameras:
                return cameras

        except Exception as error:
            print(f"Could not get camera names with pygrabber: {error}")

    # Fallback for non-Windows systems or if pygrabber enumeration fails.
    backend = gesture_get_video_capture_backend()

    for index in range(max_index):
        cap = cv2.VideoCapture(index, backend)

        try:
            if cap.isOpened():
                success, _ = cap.read()

                if success:
                    cameras.append({
                        "label": f"Camera {index}",
                        "value": str(index),
                    })

        finally:
            cap.release()

    # Always provide a usable option even if probing is blocked by another app.
    if not cameras:
        cameras.append({
            "label": "Camera 0",
            "value": "0",
        })

    return cameras


def gesture_apply_plugin_preferences(preferences):
    global gesture_CAMERA_INDEX
    global gesture_CAMERA_RESOLUTION
    global gesture_MIRROR_CAMERA
    global gesture_COMMERCIAL_GESTURE
    global gesture_CONTENT_GESTURE
    global gesture_COMMERCIAL_GESTURE_COUNT
    global gesture_CONTENT_GESTURE_COUNT
    global gesture_COMMERCIAL_SENSITIVITY
    global gesture_CONTENT_SENSITIVITY
    global gesture_COOLDOWN
    global gesture_TOTAL_HANDS_PROCESSED

    print(preferences)

    available_gestures = set(gesture_GESTURE_OPTIONS)

    try:
        gesture_CAMERA_INDEX = max(0, int(preferences.get("cameraIndex", gesture_CAMERA_INDEX)))
    except (TypeError, ValueError):
        print("Invalid cameraIndex preference; keeping", gesture_CAMERA_INDEX)

    try:
        gesture_CAMERA_RESOLUTION = preferences.get(
            "cameraResolution",
            "native"
        )
    except (TypeError, ValueError):
        print("Invalid cameraIndex preference; keeping", gesture_CAMERA_INDEX)

    gesture_MIRROR_CAMERA = bool(preferences.get("mirrorCamera", gesture_MIRROR_CAMERA))

    commercial_gesture = preferences.get(
        "commercialGesture",
        gesture_COMMERCIAL_GESTURE,
    )
    content_gesture = preferences.get(
        "contentGesture",
        gesture_CONTENT_GESTURE,
    )

    if commercial_gesture in available_gestures:
        gesture_COMMERCIAL_GESTURE = commercial_gesture

    if content_gesture in available_gestures:
        gesture_CONTENT_GESTURE = content_gesture

    # Using the same gesture for both actions would make state changes ambiguous.
    if gesture_CONTENT_GESTURE == gesture_COMMERCIAL_GESTURE:
        fallback = "Thumb_Up" if gesture_COMMERCIAL_GESTURE != "Thumb_Up" else "Thumb_Down"
        print(
            "Commercial and content gestures matched; "
            f"using {fallback} for content instead."
        )
        gesture_CONTENT_GESTURE = fallback

    try:
        gesture_COMMERCIAL_GESTURE_COUNT = int(gesture_clamp(
            int(preferences.get(
                "commercialGestureCount",
                gesture_COMMERCIAL_GESTURE_COUNT,
            )),
            1,
            4,
        ))
    except (TypeError, ValueError):
        print("Invalid commercialGestureCount preference")

    try:
        gesture_CONTENT_GESTURE_COUNT = int(gesture_clamp(
            int(preferences.get(
                "contentGestureCount",
                gesture_CONTENT_GESTURE_COUNT,
            )),
            1,
            4,
        ))
    except (TypeError, ValueError):
        print("Invalid contentGestureCount preference")

    try:
        gesture_TOTAL_HANDS_PROCESSED = int(preferences.get("totalHandsProcessed", gesture_TOTAL_HANDS_PROCESSED))
    except (TypeError, ValueError):
        print("Invalid totalHandsProcessed preference")

    try:
        gesture_COMMERCIAL_SENSITIVITY = int(gesture_clamp(
            int(preferences.get(
                "commercialSensitivity",
                gesture_COMMERCIAL_SENSITIVITY,
            )),
            1,
            5,
        ))
    except (TypeError, ValueError):
        print("Invalid commercialSensitivity preference")

    try:
        gesture_CONTENT_SENSITIVITY = int(gesture_clamp(
            int(preferences.get(
                "contentSensitivity",
                gesture_CONTENT_SENSITIVITY,
            )),
            1,
            5,
        ))
    except (TypeError, ValueError):
        print("Invalid contentSensitivity preference")

    try:
        gesture_COOLDOWN = float(gesture_clamp(
            float(preferences.get("cooldownSeconds", gesture_COOLDOWN)),
            0.0,
            10.0,
        ))
    except (TypeError, ValueError):
        print("Invalid cooldownSeconds preference")

    gesture_rebuild_target_gestures()

    print(
        "Applied plugin preferences:",
        {
            "cameraIndex": gesture_CAMERA_INDEX,
            "mirrorCamera": gesture_MIRROR_CAMERA,
            "commercialGesture": gesture_COMMERCIAL_GESTURE,
            "commercialGestureCount": gesture_COMMERCIAL_GESTURE_COUNT,
            "contentGesture": gesture_CONTENT_GESTURE,
            "contentGestureCount": gesture_CONTENT_GESTURE_COUNT,
            "commercialSensitivity": gesture_COMMERCIAL_SENSITIVITY,
            "contentSensitivity": gesture_CONTENT_SENSITIVITY,
            "cooldownSeconds": gesture_COOLDOWN,
        },
    )


gesture_rebuild_target_gestures()

# --------------------------------------------------
# Display helpers
# --------------------------------------------------

def gesture_get_gesture_for_action(action):
    for gesture_name, config in gesture_TARGET_GESTURES.items():
        if config["action"] == action:
            return gesture_name
    return None

def gesture_get_expected_action():
    # If currently commercial, expect content action.
    # If currently content or unknown, expect commercial action.
    if gesture_current_is_commercial is True:
        return "content"
    return "commercial"

def gesture_get_expected_gesture_name():
    return gesture_get_gesture_for_action(gesture_get_expected_action())

def gesture_build_gesture_display(gesture_name, detected_count=0, triggered=False):
    config = gesture_TARGET_GESTURES[gesture_name]
    required_count = gesture_REQUIRED_GESTURE_COUNTS.get(gesture_name, 1)

    detected_count = max(0, min(detected_count, required_count))

    if triggered:
        slots = [gesture_CHECK_BUTTON] * required_count
    else:
        slots = (
            [gesture_GREEN_SQUARE] * detected_count +
            [config["emoji"]] * (required_count - detected_count)
        )

    return gesture_HAND_PREFIX + " " + " ".join(slots)

async def gesture_send_expected_resting_status(ws, debug="Ready"):
    expected_gesture = gesture_get_expected_gesture_name()

    if not expected_gesture:
        return

    display = gesture_build_gesture_display(
        expected_gesture,
        detected_count=0,
        triggered=False
    )

    await gesture_send_status_if_changed(ws, display, debug)

async def gesture_send_progress_status(ws, gesture_name, detected_count):
    display = gesture_build_gesture_display(
        gesture_name,
        detected_count=detected_count,
        triggered=False
    )

    await gesture_send_status_if_changed(
        ws,
        display,
        f"Detected {detected_count} of {gesture_REQUIRED_GESTURE_COUNTS.get(gesture_name, 1)} required {gesture_name}"
    )

async def gesture_send_trigger_status(ws, gesture_name):
    display = gesture_build_gesture_display(
        gesture_name,
        detected_count=gesture_REQUIRED_GESTURE_COUNTS.get(gesture_name, 1),
        triggered=True
    )

    await gesture_send_status_if_changed(
        ws,
        display,
        f"{gesture_name} trigger confirmed"
    )

async def gesture_send_status_if_changed(ws, display, debug):
    global gesture_last_status_display

    if display == gesture_last_status_display:
        return

    gesture_last_status_display = display
    await gesture_send_status(ws, display, debug)

# --------------------------------------------------
# Image helpers
# --------------------------------------------------

def gesture_frame_to_base64(frame, max_width=gesture_SNAPSHOT_MAX_WIDTH, max_height=gesture_SNAPSHOT_MAX_HEIGHT):
    if frame is None:
        return None

    frame = frame.copy()

    height, width = frame.shape[:2]

    scale = min(
        max_width / width,
        max_height / height,
        1.0
    )

    new_width = int(width * scale)
    new_height = int(height * scale)

    if scale < 1.0:
        frame = cv2.resize(
            frame,
            (new_width, new_height),
            interpolation=cv2.INTER_AREA
        )

    success, buffer = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, 98]
    )

    if not success or buffer is None:
        return None

    base64_data = base64.b64encode(
        buffer.tobytes()
    ).decode("utf-8")

    return f"data:image/jpeg;base64,{base64_data}"

# --------------------------------------------------
# Gesture helpers
# --------------------------------------------------

def gesture_find_gesture_config(gesture_name):
    return gesture_TARGET_GESTURES.get(gesture_name)

def gesture_get_sensitivity_thresholds(sensitivity):
    """
    Shift only the confidence values in THRESHOLDS.

    Sensitivity 1 is the least sensitive, 5 is the most sensitive,
    and 3 reproduces THRESHOLDS exactly. Timing values are never changed.
    """
    sensitivity = int(gesture_clamp(sensitivity, 1, 5))

    if sensitivity < 3:
        # 1 -> +0.09, 2 -> +0.045
        confidence_shift = (3 - sensitivity) * 0.045
    else:
        # 3 -> 0.00, 4 -> -0.04, 5 -> -0.08
        confidence_shift = -(sensitivity - 3) * 0.04

    return [
        (
            float(gesture_clamp(min_confidence + confidence_shift, 0.01, 0.99)),
            min_duration,
        )
        for min_confidence, min_duration in gesture_THRESHOLDS
    ]

def gesture_get_gesture_sensitivity(config):
    if config["action"] == "commercial":
        return gesture_COMMERCIAL_SENSITIVITY

    return gesture_CONTENT_SENSITIVITY


def gesture_passes_threshold(confidence, duration, sensitivity):
    for min_confidence, min_duration in gesture_get_sensitivity_thresholds(sensitivity):
        if confidence >= min_confidence and duration >= min_duration:
            return True

    return False

# --------------------------------------------------
# Trigger handling
# --------------------------------------------------

async def gesture_handle_trigger(ws, gesture_name, config, confidence, duration, frame):
    global gesture_current_is_commercial

    new_is_commercial = config["action"] == "commercial"

    if gesture_current_is_commercial is not None and gesture_current_is_commercial == new_is_commercial:
        print(f"IGNORED: {gesture_name} already matches current state")
        return False

    print(
        f"TRIGGERED: {gesture_name} | "
        f"confidence={confidence:.2f} | "
        f"duration={duration:.2f}s"
    )

    gesture_current_is_commercial = new_is_commercial

    debug_text = f"{gesture_name} detected"

    if gesture_is_debug_mode:
        debug_text = gesture_frame_to_base64(frame)

    trigger_display = gesture_build_gesture_display(
        gesture_name,
        detected_count=gesture_REQUIRED_GESTURE_COUNTS.get(gesture_name, 1),
        triggered=True
    )

    await gesture_send_commercial_state_change(
        ws,
        new_is_commercial,
        trigger_display,
        debug_text,
    )

    #await send_trigger_status(ws, gesture_name)

    return True

# --------------------------------------------------
# Gesture processing
# --------------------------------------------------

async def gesture_process_gesture_group(ws, gesture_name, hands, now, frame):
    global gesture_any_trigger_display_until
    config = gesture_find_gesture_config(gesture_name)

    if not config:
        return

    expected_gesture = gesture_get_expected_gesture_name()

    # Only show progress and trigger for the gesture that would change state.
    if gesture_name != expected_gesture:
        return

    required_count = gesture_REQUIRED_GESTURE_COUNTS.get(gesture_name, 1)

    matching_hands = [
        hand for hand in hands
        if hand["gesture_name"] == gesture_name
    ]

    current_count = len(matching_hands)

    if gesture_name not in gesture_gesture_group_states:
        gesture_gesture_group_states[gesture_name] = {
            "start_time": now,
            "triggered": False,
            "visible": False,
            "last_trigger_time": 0,
            "last_count": 0,
        }

    state = gesture_gesture_group_states[gesture_name]

    if current_count < required_count:
        if state["visible"]:
            print(f"HIDDEN GROUP: {gesture_name} count={current_count}")

        state["visible"] = False
        state["start_time"] = now
        state["triggered"] = False
        state["last_count"] = current_count

        if current_count > 0:

            await gesture_send_progress_status(
                ws,
                gesture_name,
                current_count
            )

        else:

            # Keep showing trigger checkmarks briefly
            if (
                gesture_is_debug_mode and
                now < gesture_any_trigger_display_until
            ):
                return

            await gesture_send_expected_resting_status(
                ws,
                "Waiting for gesture"
            )

        return

    avg_confidence = sum(
        hand["confidence"] for hand in matching_hands
    ) / current_count

    if not state["visible"]:
        state["visible"] = True
        state["start_time"] = now
        state["triggered"] = False

        print(
            f"VISIBLE GROUP: {gesture_name} "
            f"count={current_count} "
            f"confidence={avg_confidence:.2f}"
        )

    if state["last_count"] != current_count:
        await gesture_send_progress_status(ws, gesture_name, current_count)
        state["last_count"] = current_count

    duration = now - state["start_time"]

    if state["triggered"]:
        return

    if now - state["last_trigger_time"] < gesture_COOLDOWN:
        return

    sensitivity = gesture_get_gesture_sensitivity(config)

    if gesture_passes_threshold(avg_confidence, duration, sensitivity):
        did_trigger = await gesture_handle_trigger(
            ws,
            gesture_name,
            config,
            avg_confidence,
            duration,
            frame
        )

        if did_trigger:
            state["triggered"] = True
            state["last_trigger_time"] = now
            gesture_any_trigger_display_until = (now + gesture_DEBUG_TRIGGER_DISPLAY_DURATION)

# --------------------------------------------------
# Camera loop
# --------------------------------------------------

async def gesture_camera_loop(ws):
    cap = None
    recognizer = None
    debug_window_created = False

    try:
        if not await gesture_ensure_model_exists(ws):
            await gesture_send_status(
                ws,
                "Model unavailable",
                "The gesture recognition model could not be downloaded."
            )
            return

        print("Loading MediaPipe model...")
        await gesture_send_status(
            ws,
            "Loading MediaPipe model...",
            "Loading MediaPipe model..."
        )

        base_options = python.BaseOptions(
            model_asset_path=gesture_MODEL_PATH
        )

        options = vision.GestureRecognizerOptions(
            base_options=base_options,
            num_hands=max(
                gesture_TOTAL_HANDS_PROCESSED,
                gesture_COMMERCIAL_GESTURE_COUNT,
                gesture_CONTENT_GESTURE_COUNT,
            )
        )

        recognizer = vision.GestureRecognizer.create_from_options(options)

        cap = cv2.VideoCapture(gesture_CAMERA_INDEX, gesture_get_video_capture_backend())

        #TODO: add advanced/troubleshooting option for this
        # cap.set(
        #     cv2.CAP_PROP_FOURCC,
        #     cv2.VideoWriter_fourcc(*"MJPG")
        # )

        if gesture_CAMERA_RESOLUTION != "native":
            width, height = map(int, gesture_CAMERA_RESOLUTION.split("x"))

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        #TODO: add advanced/troubleshooting option for this
        # cap.set(cv2.CAP_PROP_FPS, 30)

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"Camera resolution: {width}x{height}")

        if not cap.isOpened():
            print("Failed to open webcam")
            return

        print("Camera started")

        if gesture_is_debug_mode:
            cv2.namedWindow(
                "MediaPipe Gesture Debug",
                cv2.WINDOW_NORMAL
            )
            debug_window_created = True

        await gesture_send_expected_resting_status(ws, "Ready")

        while True:
            await gesture_camera_active.wait()

            success, frame = cap.read()

            if not success:
                await asyncio.sleep(0.01)
                continue

            if gesture_MIRROR_CAMERA:
                frame = cv2.flip(frame, 1)

            #TODO: add option for this
            # display_frame = frame

            # processing_frame = cv2.resize(
            #     frame,
            #     None,
            #     fx=0.5,
            #     fy=0.5,
            #     interpolation=cv2.INTER_AREA
            # )

            # rgb_frame = cv2.cvtColor(
            #     processing_frame,
            #     cv2.COLOR_BGR2RGB
            # )

            rgb_frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb_frame
            )

            result = recognizer.recognize(mp_image)

            now = time.time()
            detected_hands = []

            if result.gestures:
                for hand_index, gesture_list in enumerate(result.gestures):
                    if not gesture_list:
                        continue

                    top_gesture = gesture_list[0]

                    gesture_name = top_gesture.category_name
                    confidence = top_gesture.score

                    landmarks = result.hand_landmarks[hand_index]

                    xs = [lm.x for lm in landmarks]
                    ys = [lm.y for lm in landmarks]

                    h, w, _ = frame.shape

                    x1 = int(min(xs) * w)
                    y1 = int(min(ys) * h)
                    x2 = int(max(xs) * w)
                    y2 = int(max(ys) * h)

                    if gesture_is_debug_mode:
                        cv2.rectangle(
                            frame,
                            (x1, y1),
                            (x2, y2),
                            (0, 255, 0),
                            2
                        )

                        cv2.putText(
                            frame,
                            f"{gesture_name} {confidence:.2f}",
                            (x1, max(y1 - 10, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 255, 0),
                            2
                        )

                    detected_hands.append({
                        "gesture_name": gesture_name,
                        "confidence": confidence
                    })

            expected_gesture = gesture_get_expected_gesture_name()

            if expected_gesture:
                await gesture_process_gesture_group(
                    ws,
                    expected_gesture,
                    detected_hands,
                    now,
                    frame
                )

            if gesture_is_debug_mode:
                cv2.imshow(
                    "MediaPipe Gesture Debug",
                    frame
                )

                if cv2.waitKey(1) & 0xFF == 27:
                    break

            await asyncio.sleep(0)

    except asyncio.CancelledError:
        print("camera_loop shutting down")
        raise

    except Exception as error:
        print(f"Camera loop error: {error}")

    finally:
        print("Cleaning up camera resources")

        if cap is not None:
            cap.release()

        if debug_window_created:
            try:
                cv2.destroyAllWindows()

                # Let OpenCV process the window-close event.
                cv2.waitKey(1)

            except cv2.error:
                pass

        if recognizer is not None:
            try:
                recognizer.close()
                print("Recognizer closed")
            except Exception:
                pass

        print("Camera resources released")

# --------------------------------------------------
# WebSocket handling
# --------------------------------------------------

async def gesture_handle_client(websocket):
    global gesture_camera_task

    print("Client connected")
    gesture_clients.add(websocket)

    try:
        async for message in websocket:
            msg = json.loads(message)
            await gesture_handle_message(websocket, msg)

    except websockets.exceptions.ConnectionClosed:
        pass

    finally:
        gesture_clients.discard(websocket)

        if len(gesture_clients) == 0:
            print("Stopping camera")

            gesture_camera_active.clear()

            if gesture_camera_task:
                gesture_camera_task.cancel()

                try:
                    await gesture_camera_task
                except asyncio.CancelledError:
                    print("Camera task cancelled")

                gesture_camera_task = None

        print("Client disconnected")

# --------------------------------------------------
# Message handling
# --------------------------------------------------

async def gesture_handle_message(ws, msg):
    global gesture_camera_task
    global gesture_current_is_commercial
    global gesture_last_status_display
    global gesture_is_debug_mode

    message_type = msg["type"]

    if message_type == "plugin_manifest":
        await gesture_send_manifest(ws)

    if message_type == "init":
        data = msg.get("data", {})
        general_preferences = data.get("preferences", {})

        gesture_is_debug_mode = bool(
            general_preferences.get(
                "isDebugMode",
                data.get("isDebugMode", False),
            )
        )

        custom_trigger_plugin_preferences = general_preferences.get("pluginPreferencesById", {}).get(gesture_PLUGIN_ID, {}).get("preferences", {})
        gesture_apply_plugin_preferences(custom_trigger_plugin_preferences)

        gesture_current_is_commercial = data.get("isCommercialState")

        gesture_last_status_display = None

        await gesture_send_status(
            ws,
            "Starting up...",
            "Starting up..."
        )

        gesture_camera_active.set()

        # Restart the camera task so camera, hand-count, and related settings
        # are guaranteed to take effect if a second init message is received.
        if gesture_camera_task:
            gesture_camera_task.cancel()
            try:
                await gesture_camera_task
            except asyncio.CancelledError:
                pass
            gesture_camera_task = None

        print("Starting camera task")
        gesture_camera_task = asyncio.create_task(
            gesture_camera_loop(ws)
        )

    elif message_type == "commercial_state_change":
        gesture_current_is_commercial = msg["data"]["isCommercialState"]

        gesture_last_status_display = None

        if gesture_is_debug_mode:
            print("waiting to send Commercial state updated")
            await asyncio.sleep(3)

        print("sending Commercial state updated")
        await gesture_send_expected_resting_status(
            ws,
            "Commercial state updated"
        )

    elif message_type == "browser_fullscreen_state_change":
        print("Fullscreen:", msg["data"]["isFullscreen"])

# --------------------------------------------------
# Send helpers
# --------------------------------------------------

async def gesture_send_commercial_state_change(
    ws,
    is_commercial,
    display,
    debug,
):
    global gesture_PLUGIN_PROTOCOL_VERSION

    try:
        await ws.send(json.dumps({
            "type": "commercial_state_change",
            "timestamp": time.time(),
            "data": {
                "isCommercial": is_commercial
            },
            "meta": {
                "display": display,
                "debug": debug,
            }
        }))

    except websockets.exceptions.ConnectionClosed:
        print("send_commercial_state_change failed")

async def gesture_send_status(ws, display, debug):
    global gesture_PLUGIN_PROTOCOL_VERSION

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
        pass

async def gesture_send_manifest(ws):
    global gesture_camera_options
    global gesture_default_camera

    # only get list of cameras if not already running and if it is, only set it if it isn't already cached
    if not gesture_camera_task:
        gesture_camera_options = gesture_get_available_cameras()
    elif not gesture_camera_options:
        gesture_camera_options = [{"label": "Camera 0", "value": "0"}]

    if not gesture_default_camera:
        gesture_default_camera = gesture_camera_options[-1]["value"]

    gesture_options = [
        {"label": config["label"], "value": gesture_name}
        for gesture_name, config in gesture_GESTURE_OPTIONS.items()
    ]

    try:
        await ws.send(json.dumps({
            "type": "plugin_manifest",
            "timestamp": time.time(),
            "pluginProtocolVersion": gesture_PLUGIN_PROTOCOL_VERSION,
            "data": {
                "name": gesture_PLUGIN_NAME,
                "id": gesture_PLUGIN_ID,
                "version": gesture_PLUGIN_VERSION,
                "tooltip": (
                    "Use configurable MediaPipe hand gestures to switch "
                    "between commercial and content states."
                ),
                "primaryColor": "#2a5ac0",
                "secondaryColor": "#FFDE34", ##FFDE34 ##FFCC22
                "capabilities": ["detection"],
                "preferences": [
                    {
                        "key": "cameraIndex",
                        "label": "Camera",
                        "tooltip": "Camera used for gesture recognition.",
                        "type": "select",
                        "options": gesture_camera_options,
                        "default": gesture_default_camera,
                    },
                    {
                        "key": "commercialGesture",
                        "label": "Commercial Gesture",
                        "tooltip": (
                            "Gesture that changes the stream state to commercial."
                        ),
                        "type": "select",
                        "options": gesture_options,
                        "default": gesture_COMMERCIAL_GESTURE,
                    },
                    {
                        "key": "commercialSensitivity",
                        "label": "Commercial Gesture Sensitivity",
                        "tooltip": (
                            "How sensitive commercial gesture detection should be. "
                            "1 is least sensitive, 5 is most sensitive."
                        ),
                        "type": "select",
                        "options": [
                            {"label": "1 - Least Sensitive", "value": "1"},
                            {"label": "2", "value": "2"},
                            {"label": "3 - Default", "value": "3"},
                            {"label": "4", "value": "4"},
                            {"label": "5 - Most Sensitive", "value": "5"},
                        ],
                        "default": "3",
                    },
                    {
                        "key": "commercialGestureCount",
                        "label": "Commercial Gesture Count",
                        "tooltip": (
                            "Number of matching hands required to trigger commercial (1-5)."
                        ),
                        "type": "number",
                        "default": gesture_COMMERCIAL_GESTURE_COUNT,
                        "min": 1,
                        "max": 4,
                    },
                    {
                        "key": "contentGesture",
                        "label": "Content Gesture",
                        "tooltip": (
                            "Gesture that changes the stream state back to content."
                        ),
                        "type": "select",
                        "options": gesture_options,
                        "default": gesture_CONTENT_GESTURE,
                    },
                    {
                        "key": "contentSensitivity",
                        "label": "Content Gesture Sensitivity",
                        "tooltip": (
                            "How sensitive content gesture detection should be. "
                            "1 is least sensitive, 5 is most sensitive."
                        ),
                        "type": "select",
                        "options": [
                            {"label": "1 - Least Sensitive", "value": "1"},
                            {"label": "2", "value": "2"},
                            {"label": "3 - Default", "value": "3"},
                            {"label": "4", "value": "4"},
                            {"label": "5 - Most Sensitive", "value": "5"},
                        ],
                        "default": "3",
                    },
                    {
                        "key": "contentGestureCount",
                        "label": "Content Gesture Count",
                        "tooltip": (
                            "Number of matching hands required to trigger content (1-5)."
                        ),
                        "type": "number",
                        "default": gesture_CONTENT_GESTURE_COUNT,
                        "min": 1,
                        "max": 4,
                    },
                    {
                        "key": "totalHandsProcessed",
                        "label": "Total Hands Processed",
                        "tooltip": (
                            "Total number of hands the model will recognize at a time (Recommended use less if can. Use more for crowded room.)."
                        ),
                        "type": "number",
                        "default": gesture_TOTAL_HANDS_PROCESSED,
                    },
                    {
                        "key": "cameraResolution",
                        "label": "Camera Resolution",
                        "tooltip": "Resolution used when capturing frames for gesture recognition.",
                        "type": "select",
                        "options": [
                            {
                                "label": "Native",
                                "value": "native"
                            },
                            {
                                "label": "1920x1080",
                                "value": "1920x1080"
                            },
                            {
                                "label": "1280x720",
                                "value": "1280x720"
                            }
                        ],
                        "default": gesture_CAMERA_RESOLUTION
                    },
                    {
                        "key": "mirrorCamera",
                        "label": "Mirror Camera",
                        "tooltip": (
                            "Flip the camera horizontally like a selfie preview."
                        ),
                        "type": "checkbox",
                        "default": gesture_MIRROR_CAMERA,
                    },
                    {
                        "key": "cooldownSeconds",
                        "label": "Trigger Cooldown (Seconds)",
                        "tooltip": (
                            "Minimum delay before the same gesture group can "
                            "trigger again."
                        ),
                        "type": "number",
                        "default": gesture_COOLDOWN,
                        "min": 0.0,
                        "max": 10.0,
                        "step": 0.1,
                    },
                ],
            },
            "meta": {
                "display": "Sending Manifest",
                "debug": "Sending Manifest",
            },
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_manifest stopped: client disconnected")

# --------------------------------------------------
# Main
# --------------------------------------------------

async def gesture_main():
    async with websockets.serve(
        gesture_handle_client,
        "localhost",
        gesture_PORT
    ):
        print(f"Server running on ws://localhost:{gesture_PORT}")
        await asyncio.Future()

# Standalone plugin entrypoint intentionally disabled in the combined Party Pack.


# =============================================================================
# Bundled plugin source: vlc-over-commercials.py
# Prefix: vlc_
# =============================================================================

import os
import re
import subprocess
import threading
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

vlc_PLUGIN_PROTOCOL_VERSION = 1  # DO NOT TOUCH

vlc_PLUGIN_NAME = "VLC Over Commercials"
vlc_PLUGIN_ID = "vlc-over-commercials"
vlc_PLUGIN_VERSION = "1.0.1"


# -----------------------------------------------------------------------------
# VLC settings
# -----------------------------------------------------------------------------

vlc_VLC_HTTP_URL = "http://localhost:8080/requests/status.json"
vlc_VLC_HTTP_PASSWORD = "1234"
vlc_VLC_HTTP_AUTH = ("", vlc_VLC_HTTP_PASSWORD)

vlc_DEFAULT_MEDIA_URL = "file:///C:/Users/user/Downloads/video.mp4"
vlc_DEFAULT_VOLUME = 256
vlc_FALLBACK_VOLUME = 205
vlc_FREEZE_TIMEOUT_SECONDS = 20
vlc_AUDIO_TIMEOUT_SECONDS = 20
vlc_HEALTH_CHECK_INTERVAL_SECONDS = 1
vlc_WINDOW_SIZE_TOLERANCE_PIXELS = 2


# -----------------------------------------------------------------------------
# Runtime state
# -----------------------------------------------------------------------------

vlc_SCRIPT_DIR = APP_DIR

vlc_optimized_width_percentage = 90
vlc_optimized_height_percentage = 85
vlc_previous_overlay_width_percentage = 0
vlc_previous_overlay_height_percentage = 0

vlc_vlc_process = None
vlc_vlc_window_handle = None
vlc_original_foreground_window = None
vlc_is_original_foreground_window_topmost = False
vlc_is_setup_complete = False
vlc_saved_volume = vlc_DEFAULT_VOLUME
vlc_current_media_url = None
vlc_current_media_has_audio = False
vlc_is_commercial_state = False
vlc_expected_commercial_window_rect = None

vlc_health_monitor_thread = None
vlc_health_monitor_stop_event = threading.Event()
vlc_vlc_command_lock = threading.Lock()
# Prevent media URL changes and health-triggered reloads from overlapping.
# RLock lets reset_unhealthy_media() safely call switch_vlc_media(), which also
# uses this same lock.
vlc_media_reload_lock = threading.RLock()


# -----------------------------------------------------------------------------
# General helpers
# -----------------------------------------------------------------------------


def vlc_find_main_window_for_process(process_id):
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


def vlc_wait_for_process_window(process_id, timeout=15):
    """Wait for the main window belonging to process_id."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        hwnd = vlc_find_main_window_for_process(process_id)
        if hwnd and win32gui.IsWindow(hwnd):
            return hwnd

        time.sleep(0.1)

    return None


def vlc_find_vlc_exe():
    """Find VLC in its usual Windows installation folders."""
    possible_paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None


def vlc_get_vlc_status(command=None, params=None, timeout=3):
    """Send a request to VLC and return its JSON response."""
    request_params = dict(params or {})

    if command:
        request_params["command"] = command

    with vlc_vlc_command_lock:
        response = requests.get(
            vlc_VLC_HTTP_URL,
            params=request_params,
            auth=vlc_VLC_HTTP_AUTH,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()


def vlc_send_vlc_command(command, params=None, timeout=3):
    """Send a command to VLC."""
    vlc_get_vlc_status(command=command, params=params, timeout=timeout)


def vlc_set_vlc_volume(volume):
    """Set VLC's volume."""
    vlc_send_vlc_command("volume", {"val": int(volume)})


def vlc_get_vlc_window():
    """Return the main window owned by the VLC process this script opened."""
    global vlc_vlc_window_handle

    if vlc_vlc_window_handle and win32gui.IsWindow(vlc_vlc_window_handle):
        return vlc_vlc_window_handle

    if vlc_vlc_process and vlc_vlc_process.poll() is None:
        vlc_vlc_window_handle = vlc_find_main_window_for_process(vlc_vlc_process.pid)
        return vlc_vlc_window_handle

    return None


def vlc_safely_minimize_window(hwnd):
    if hwnd and win32gui.IsWindow(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)


# -----------------------------------------------------------------------------
# VLC startup and media information
# -----------------------------------------------------------------------------


def vlc_get_media_url_from_preferences(preferences, use_default=False):
    """Return the configured media URL, or None when it was not supplied."""
    media_url = (
        preferences.get("custom_overlay_plugin_preferences", {})
        .get("url")
    )

    if media_url:
        return media_url

    return vlc_DEFAULT_MEDIA_URL if use_default else None


def vlc_status_has_video(status):
    """Return True when VLC reports at least one video stream."""
    categories = status.get("information", {}).get("category", {})

    for stream_info in categories.values():
        if not isinstance(stream_info, dict):
            continue

        if str(stream_info.get("Type", "")).lower() == "video":
            return True

    return False


def vlc_status_has_audio(status):
    """Return True when VLC reports at least one audio stream."""
    categories = status.get("information", {}).get("category", {})

    for stream_info in categories.values():
        if not isinstance(stream_info, dict):
            continue

        if str(stream_info.get("Type", "")).lower() == "audio":
            return True

    return False


def vlc_update_current_media_audio_status(timeout=5):
    """Check whether the newly loaded media actually contains an audio stream."""
    global vlc_current_media_has_audio

    start_time = time.time()
    latest_status = {}

    while time.time() - start_time < timeout:
        try:
            latest_status = vlc_get_vlc_status()
        except requests.RequestException:
            time.sleep(0.25)
            continue

        if vlc_status_has_audio(latest_status):
            vlc_current_media_has_audio = True
            print("Current media contains an audio stream.")
            return True

        # Once VLC is playing video, give its stream metadata a little time to
        # populate before deciding that this source is intentionally video-only.
        time.sleep(0.25)

    vlc_current_media_has_audio = vlc_status_has_audio(latest_status)

    if vlc_current_media_has_audio:
        print("Current media contains an audio stream.")
    else:
        print("Current media does not report an audio stream. Audio monitoring disabled.")

    return vlc_current_media_has_audio


def vlc_switch_vlc_media(media_url, preserve_state=True):
    """Replace VLC's current media without opening another VLC process."""
    global vlc_current_media_url
    global vlc_previous_overlay_width_percentage
    global vlc_previous_overlay_height_percentage

    if not media_url:
        return False

    # Keep the entire stop/load/wait sequence together so another request or
    # health check cannot start a second reload before this one finishes.
    with vlc_media_reload_lock:
        old_status = {}
        if preserve_state:
            try:
                old_status = vlc_get_vlc_status()
            except requests.RequestException:
                pass

        old_state = old_status.get("state")
        old_volume = old_status.get("volume")

        print(f"Switching VLC media to: {media_url}")
        vlc_send_vlc_command("pl_stop")
        vlc_send_vlc_command("in_play", {"input": media_url})

        vlc_current_media_url = media_url
        vlc_previous_overlay_width_percentage = 0
        vlc_previous_overlay_height_percentage = 0

        vlc_wait_for_vlc_playing(timeout=30)
        vlc_update_current_media_audio_status()

        if old_volume is not None:
            vlc_set_vlc_volume(int(old_volume))

        if preserve_state and old_state == "paused":
            vlc_send_vlc_command("pl_forcepause")

        return True


def vlc_update_media_url_if_changed(preferences):
    """Switch media when a later request contains a different URL."""
    media_url = vlc_get_media_url_from_preferences(preferences)

    if not media_url:
        return False

    if not vlc_is_setup_complete or not vlc_current_media_url:
        return False

    if media_url == vlc_current_media_url:
        return False

    return vlc_switch_vlc_media(media_url, preserve_state=True)


def vlc_reset_unhealthy_media(reason):
    """Restart the current media after a video or audio playback failure."""
    # Hold the reload lock for the whole health recovery. This prevents a URL
    # change or another recovery from being started at the same time.
    with vlc_media_reload_lock:
        if not vlc_current_media_url:
            return

        try:
            status = vlc_get_vlc_status()
            volume = int(status.get("volume", vlc_saved_volume))
            media_url = vlc_current_media_url

            print(f"{reason} Restarting the media.")
            vlc_switch_vlc_media(media_url, preserve_state=False)
            vlc_set_vlc_volume(volume)
        except requests.RequestException as error:
            print(f"Could not reset VLC media: {error}")


def vlc_window_rect_changed(current_rect, expected_rect):
    """Return True when a window moved or resized beyond the small tolerance."""
    if not current_rect or not expected_rect:
        return False

    return any(
        abs(current - expected) > vlc_WINDOW_SIZE_TOLERANCE_PIXELS
        for current, expected in zip(current_rect, expected_rect)
    )


def vlc_restore_expected_commercial_window(hwnd):
    """Put VLC back at the commercial overlay position and size."""
    if not hwnd or not vlc_expected_commercial_window_rect:
        return

    left, top, right, bottom = vlc_expected_commercial_window_rect
    width = right - left
    height = bottom - top

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,
        left,
        top,
        width,
        height,
        win32con.SWP_NOACTIVATE,
    )


def vlc_monitor_vlc_health():
    """Monitor VLC for frozen video, dropped audio, and window size changes."""
    last_displayed_count = None
    last_frame_time = time.monotonic()

    last_audio_count = None
    last_audio_time = time.monotonic()

    while not vlc_health_monitor_stop_event.wait(vlc_HEALTH_CHECK_INTERVAL_SECONDS):
        if not vlc_is_setup_complete or not vlc_current_media_url:
            last_displayed_count = None
            last_audio_count = None
            last_frame_time = time.monotonic()
            last_audio_time = time.monotonic()
            continue

        try:
            status = vlc_get_vlc_status()
        except requests.RequestException:
            continue

        if status.get("state") != "playing":
            last_displayed_count = None
            last_audio_count = None
            last_frame_time = time.monotonic()
            last_audio_time = time.monotonic()
            continue

        # VLC can sometimes resize its own window after a stream reload. While
        # commercials are playing, keep it at the exact overlay rectangle that
        # the plugin most recently requested.
        if vlc_is_commercial_state and vlc_expected_commercial_window_rect:
            hwnd = vlc_get_vlc_window()

            if hwnd:
                try:
                    current_rect = win32gui.GetWindowRect(hwnd)
                    if vlc_window_rect_changed(
                        current_rect,
                        vlc_expected_commercial_window_rect,
                    ):
                        print("VLC window changed size or position. Restoring overlay.")
                        vlc_restore_expected_commercial_window(hwnd)
                except win32gui.error:
                    pass

        stats = status.get("stats", {})

        # Video freeze detection
        if vlc_status_has_video(status):
            displayed_count = int(stats.get("displayedpictures", 0) or 0)

            if (
                last_displayed_count is None
                or displayed_count > last_displayed_count
            ):
                last_displayed_count = displayed_count
                last_frame_time = time.monotonic()
            elif time.monotonic() - last_frame_time >= vlc_FREEZE_TIMEOUT_SECONDS:
                vlc_reset_unhealthy_media(
                    f"No new VLC video frames for {vlc_FREEZE_TIMEOUT_SECONDS} seconds."
                )
                last_displayed_count = None
                last_audio_count = None
                last_frame_time = time.monotonic()
                last_audio_time = time.monotonic()
                continue
        else:
            last_displayed_count = None
            last_frame_time = time.monotonic()

        # Audio failure detection. Only monitor audio when this media source was
        # confirmed to contain an audio stream when it began playing.
        if vlc_current_media_has_audio:
            played_audio_buffers = int(stats.get("playedabuffers", 0) or 0)
            decoded_audio = int(stats.get("decodedaudio", 0) or 0)
            audio_count = max(played_audio_buffers, decoded_audio)

            if last_audio_count is None or audio_count > last_audio_count:
                last_audio_count = audio_count
                last_audio_time = time.monotonic()
            elif time.monotonic() - last_audio_time >= vlc_AUDIO_TIMEOUT_SECONDS:
                vlc_reset_unhealthy_media(
                    f"No new VLC audio data for {vlc_AUDIO_TIMEOUT_SECONDS} seconds."
                )
                last_displayed_count = None
                last_audio_count = None
                last_frame_time = time.monotonic()
                last_audio_time = time.monotonic()
        else:
            last_audio_count = None
            last_audio_time = time.monotonic()


def vlc_start_health_monitor():
    """Start the VLC health-monitor thread once."""
    global vlc_health_monitor_thread

    if vlc_health_monitor_thread and vlc_health_monitor_thread.is_alive():
        return

    vlc_health_monitor_stop_event.clear()
    vlc_health_monitor_thread = threading.Thread(
        target=vlc_monitor_vlc_health,
        name="vlc-health-monitor",
        daemon=True,
    )
    vlc_health_monitor_thread.start()


def vlc_stop_health_monitor():
    """Tell the VLC health-monitor thread to stop."""
    vlc_health_monitor_stop_event.set()

def vlc_open_vlc_with_media(media_url):
    """Start VLC and remember the main window owned by that process."""
    global vlc_vlc_process
    global vlc_vlc_window_handle
    global vlc_current_media_url

    vlc_path = vlc_find_vlc_exe()
    if not vlc_path:
        raise FileNotFoundError(
            "Could not find vlc.exe in Program Files or Program Files (x86)."
        )

    vlc_vlc_process = subprocess.Popen(
        [
            vlc_path,
            "--qt-start-minimized",
            "--qt-minimal-view",
            "--extraintf",
            "http",
            "--http-password",
            vlc_VLC_HTTP_PASSWORD,
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

    print(f"Started VLC process with PID {vlc_vlc_process.pid}.")
    vlc_current_media_url = media_url

    # VLC's HTTP server may need a moment to start.
    start_time = time.time()
    while time.time() - start_time < 10:
        try:
            vlc_send_vlc_command("in_play", {"input": media_url})
            break
        except requests.RequestException:
            time.sleep(0.25)
    else:
        vlc_vlc_process.terminate()
        vlc_vlc_process = None
        raise RuntimeError("VLC opened, but its HTTP interface did not respond.")

    vlc_vlc_window_handle = vlc_wait_for_process_window(vlc_vlc_process.pid)
    if not vlc_vlc_window_handle:
        vlc_vlc_process.terminate()
        vlc_vlc_process = None
        raise RuntimeError(
            "VLC started, but its main window could not be found."
        )

    title = win32gui.GetWindowText(vlc_vlc_window_handle)
    print(
        f"Using VLC window hwnd={vlc_vlc_window_handle}, title={title!r}."
    )


def vlc_get_vlc_video_dimensions():
    """Return the current video's width and height."""
    status = vlc_get_vlc_status()
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


def vlc_wait_for_vlc_playing(timeout=60):
    """Wait until VLC is playing and has displayed at least one new frame."""
    start_time = time.time()
    last_displayed_count = None

    while time.time() - start_time < timeout:
        try:
            status = vlc_get_vlc_status()
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


def vlc_wait_for_setup_complete(timeout=30):
    """Wait until the init request has finished setting up VLC."""
    if vlc_is_setup_complete:
        return True

    start_time = time.time()

    while time.time() - start_time < timeout:
        if vlc_is_setup_complete:
            return True
        time.sleep(0.5)

    return False


def vlc_is_live_media(status):
    """Treat media without a known duration as a live stream."""
    length = status.get("length", 0)
    print(f"Media length: {length}")
    return not length or length <= 0


# -----------------------------------------------------------------------------
# Window sizing and styling
# -----------------------------------------------------------------------------


def vlc_calculate_largest_aspect_fit(max_width_percent=90, max_height_percent=75):
    """Fit the video inside a percentage-based box without stretching it."""
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    max_width_pixels = int(screen_width * max_width_percent / 100)
    max_height_pixels = int(screen_height * max_height_percent / 100)

    dimensions = vlc_get_vlc_video_dimensions()
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


def vlc_position_and_resize_window(
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


def vlc_remove_topmost(hwnd, width_percent=90, height_percent=75):
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


def vlc_make_borderless(hwnd):
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


def vlc_restore_borders(hwnd):
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


def vlc_close_window_by_hwnd(hwnd):
    """Ask a window to close, like clicking its X button."""
    if hwnd and win32gui.IsWindow(hwnd):
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)


def vlc_set_original_window_topmost(make_topmost):
    """Temporarily change the original foreground window's topmost state."""
    global vlc_is_original_foreground_window_topmost

    if not vlc_original_foreground_window:
        return

    insert_after = (
        win32con.HWND_TOPMOST if make_topmost else win32con.HWND_NOTOPMOST
    )

    win32gui.SetWindowPos(
        vlc_original_foreground_window,
        insert_after,
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE
        | win32con.SWP_NOSIZE
        | win32con.SWP_NOACTIVATE,
    )

    vlc_is_original_foreground_window_topmost = make_topmost
    #TODO: add thread to monitor when original_foreground_window is back to foreground window


def vlc_hide_vlc_and_clear_taskbar(hwnd, should_clear_taskbar=True):
    """Use the original two-step minimize behavior for Windows 10 and 11."""
    vlc_safely_minimize_window(hwnd)
    if should_clear_taskbar:
        time.sleep(0.2)
        vlc_position_and_resize_window(hwnd, width_percent=10, height_percent=10)
        time.sleep(0.2)
        vlc_safely_minimize_window(hwnd)
        time.sleep(0.2)

        if vlc_original_foreground_window:
            time.sleep(0.4)
            vlc_set_original_window_topmost(True)


# -----------------------------------------------------------------------------
# Plugin request handlers
# -----------------------------------------------------------------------------


def vlc_read_preferences(data):
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
        "custom_overlay_plugin_preferences": preferences.get("pluginPreferencesById", {}).get(vlc_PLUGIN_ID, {}).get("preferences", {})
    }


def vlc_show_commercial_overlay(hwnd, preferences):
    global vlc_optimized_width_percentage
    global vlc_optimized_height_percentage
    global vlc_previous_overlay_width_percentage
    global vlc_previous_overlay_height_percentage
    global vlc_expected_commercial_window_rect

    dimensions_changed = (
        preferences["overlay_width"] != vlc_previous_overlay_width_percentage
        or preferences["overlay_height"] != vlc_previous_overlay_height_percentage
    )

    vlc_previous_overlay_width_percentage = preferences["overlay_width"]
    vlc_previous_overlay_height_percentage = preferences["overlay_height"]

    if dimensions_changed:
        (
            vlc_optimized_width_percentage,
            vlc_optimized_height_percentage,
        ) = vlc_calculate_largest_aspect_fit(
            max_width_percent=preferences["overlay_width"],
            max_height_percent=preferences["overlay_height"],
        )

    vlc_position_and_resize_window(
        hwnd,
        width_percent=vlc_optimized_width_percentage,
        height_percent=vlc_optimized_height_percentage,
        vertical=preferences["overlay_vertical"],
        horizontal=preferences["overlay_horizontal"],
    )

    if hwnd and win32gui.IsWindow(hwnd):
        vlc_expected_commercial_window_rect = win32gui.GetWindowRect(hwnd)

    time.sleep(0.1)
    vlc_send_vlc_command("pl_forceresume")

    #status = get_vlc_status()
    #if is_live_media(status):
    vlc_set_vlc_volume(vlc_saved_volume)


def vlc_hide_commercial_overlay(hwnd, preferences):
    global vlc_saved_volume

    status = vlc_get_vlc_status()
    current_volume = int(status.get("volume", vlc_FALLBACK_VOLUME))
    vlc_saved_volume = current_volume or vlc_FALLBACK_VOLUME

    if not vlc_is_live_media(status):
        vlc_send_vlc_command("pl_forcepause")
        vlc_safely_minimize_window(hwnd)
        return

    vlc_set_vlc_volume(0)

    if preferences["is_pip_mode"]:
        pip_width, pip_height = vlc_calculate_largest_aspect_fit(
            max_width_percent=preferences["pip_width"],
            max_height_percent=preferences["pip_height"],
        )
        vlc_position_and_resize_window(
            hwnd,
            width_percent=pip_width,
            height_percent=pip_height,
            vertical=preferences["pip_vertical"],
            horizontal=preferences["pip_horizontal"],
        )
    else:
        vlc_safely_minimize_window(hwnd)


def vlc_resume_fullscreen(hwnd, preferences):
    vlc_make_borderless(hwnd)

    status = vlc_get_vlc_status()

    if vlc_is_live_media(status):
        vlc_set_vlc_volume(0)

        if preferences["is_pip_mode"]:
            pip_width, pip_height = vlc_calculate_largest_aspect_fit(
                max_width_percent=preferences["pip_width"],
                max_height_percent=preferences["pip_height"],
            )
            vlc_position_and_resize_window(
                hwnd,
                width_percent=pip_width,
                height_percent=pip_height,
                vertical=preferences["pip_vertical"],
                horizontal=preferences["pip_horizontal"],
            )


def vlc_initialize_plugin(preferences):
    global vlc_original_foreground_window
    global vlc_is_setup_complete
    global vlc_saved_volume

    vlc_is_setup_complete = False
    vlc_original_foreground_window = win32gui.GetForegroundWindow()

    if vlc_original_foreground_window:
        title = win32gui.GetWindowText(vlc_original_foreground_window)
        print(f"Original foreground window: {title}")

    should_clear_taskbar = (
        preferences.get("custom_overlay_plugin_preferences", {})
        .get("shouldClearTaskbar", False)
    )

    media_url = vlc_get_media_url_from_preferences(preferences, use_default=True)
    vlc_open_vlc_with_media(media_url)

    print("Waiting for VLC to begin playing...")
    if not vlc_wait_for_vlc_playing():
        raise RuntimeError("VLC did not begin displaying video before timeout.")

    vlc_update_current_media_audio_status()
    time.sleep(0.5)

    hwnd = vlc_get_vlc_window()
    if not hwnd:
        raise RuntimeError("VLC could not be opened.")

    vlc_make_borderless(hwnd)

    # Bring VLC forward briefly so the Windows taskbar appears now instead of
    # unexpectedly appearing later when the first commercial begins.
    time.sleep(0.2)
    vlc_position_and_resize_window(hwnd, width_percent=10, height_percent=10)
    time.sleep(0.2)

    status = vlc_get_vlc_status()
    current_volume = int(status.get("volume", vlc_FALLBACK_VOLUME))
    vlc_saved_volume = current_volume or vlc_FALLBACK_VOLUME

    if not vlc_is_live_media(status):
        vlc_send_vlc_command("pl_forcepause")
        time.sleep(0.2)
        vlc_set_vlc_volume(vlc_saved_volume) # in case VLC opened with volume as 0, this should set it to the fallback
        vlc_hide_vlc_and_clear_taskbar(hwnd, should_clear_taskbar)
    else:
        vlc_set_vlc_volume(0)

        if preferences["is_pip_mode"]:
            pip_width, pip_height = vlc_calculate_largest_aspect_fit(
                max_width_percent=preferences["pip_width"],
                max_height_percent=preferences["pip_height"],
            )
            vlc_position_and_resize_window(
                hwnd,
                width_percent=pip_width,
                height_percent=pip_height,
                vertical=preferences["pip_vertical"],
                horizontal=preferences["pip_horizontal"],
            )
            #TODO: add ability to clear taskbar while in pip mode
        else:
            vlc_hide_vlc_and_clear_taskbar(hwnd, should_clear_taskbar)

    vlc_is_setup_complete = True
    vlc_start_health_monitor()


def vlc_end_plugin():
    global vlc_vlc_process
    global vlc_vlc_window_handle
    global vlc_is_setup_complete
    global vlc_current_media_url
    global vlc_current_media_has_audio
    global vlc_is_commercial_state
    global vlc_expected_commercial_window_rect

    vlc_stop_health_monitor()

    if vlc_is_original_foreground_window_topmost:
        vlc_set_original_window_topmost(False)

    hwnd = vlc_get_vlc_window()
    vlc_remove_topmost(
        hwnd,
        width_percent=vlc_optimized_width_percentage,
        height_percent=vlc_optimized_height_percentage,
    )
    vlc_restore_borders(hwnd)

    try:
        status = vlc_get_vlc_status()
        if vlc_is_live_media(status):
            vlc_set_vlc_volume(vlc_saved_volume)

        vlc_send_vlc_command("pl_stop")
    except requests.RequestException as error:
        print(f"Could not send final command to VLC: {error}")

    vlc_close_window_by_hwnd(hwnd)

    if vlc_vlc_process and vlc_vlc_process.poll() is None:
        vlc_vlc_process.terminate()
        print("Terminated VLC process.")

    vlc_vlc_process = None
    vlc_vlc_window_handle = None
    vlc_current_media_url = None
    vlc_current_media_has_audio = False
    vlc_is_commercial_state = False
    vlc_expected_commercial_window_rect = None
    vlc_is_setup_complete = False
    print("Extension stopped.")


# -----------------------------------------------------------------------------
# Party Pack WebSocket interface
# -----------------------------------------------------------------------------

async def vlc_send_status(websocket, display, debug=None, display_type="info", display_time=7000):
    """Send a normal overlay-plugin status message through the Party Pack WS."""
    await websocket.send(json.dumps({
        "type": "status",
        "timestamp": time.time(),
        "pluginProtocolVersion": vlc_PLUGIN_PROTOCOL_VERSION,
        "data": {},
        "meta": {
            "display": str(display),
            "debug": str(debug if debug is not None else display),
            "displayType": display_type,
            "displayTime": display_time,
        },
    }))


async def vlc_send_manifest(websocket):
    """Send VLC's manifest the same way as every other bundled WS plugin."""
    await websocket.send(json.dumps({
        "type": "plugin_manifest",
        "timestamp": time.time(),
        "pluginProtocolVersion": vlc_PLUGIN_PROTOCOL_VERSION,
        "data": {
            "name": vlc_PLUGIN_NAME,
            "id": vlc_PLUGIN_ID,
            "version": vlc_PLUGIN_VERSION,
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
                    "default": "https://upload.wikimedia.org/wikipedia/commons/8/88/Big_Buck_Bunny_alt.webm",
                },
                {
                    "key": "shouldClearTaskbar",
                    "label": "Should Attempt to Hide Taskbar",
                    "description": (
                        "When VLC opens, it sometimes has the Windows taskbar display. "
                        "This can quickly be fixed by clicking on the browser stream, "
                        "but this setting attempts to dismiss it for you to save a click. "
                    ),
                    "type": "checkbox",
                    "default": True,
                },
            ],
        },
        "meta": {},
    }))


async def vlc_handle_message(websocket, message):
    """Handle Party Pack messages directly over WebSocket.

    VLC is now a first-class WS plugin. Its old Flask/API transport is no
    longer used; only the underlying VLC/window-control functions remain.
    """
    global vlc_is_commercial_state

    message_type = message.get("type")

    if message_type == "plugin_manifest":
        await vlc_send_manifest(websocket)
        return

    preferences = vlc_read_preferences(message)

    if message_type == "init":
        await asyncio.to_thread(vlc_initialize_plugin, preferences)
        await vlc_send_status(
            websocket,
            "VLC Over Commercials is ready",
            "VLC initialized successfully and is ready to display during commercials.",
            "success",
            7000,
        )
        return

    if message_type == "commercial_state_change":
        if not await asyncio.to_thread(vlc_wait_for_setup_complete):
            raise RuntimeError("VLC setup did not complete before timeout.")

        hwnd = vlc_get_vlc_window()
        if not hwnd:
            raise RuntimeError("Could not find VLC window.")

        is_commercial = bool(message.get("data", {}).get("isCommercialState", False))
        vlc_is_commercial_state = is_commercial

        if is_commercial:
            print("Starting VLC overlay.")
            await asyncio.to_thread(vlc_update_media_url_if_changed, preferences)
            await asyncio.to_thread(vlc_show_commercial_overlay, hwnd, preferences)
        else:
            print("Stopping VLC overlay.")
            await asyncio.to_thread(vlc_hide_commercial_overlay, hwnd, preferences)
        return

    if message_type == "browser_fullscreen_state_change":
        hwnd = vlc_get_vlc_window()
        is_fullscreen = bool(message.get("data", {}).get("isFullscreen", False))

        if is_fullscreen:
            print("User entered browser fullscreen.")
            await asyncio.to_thread(vlc_update_media_url_if_changed, preferences)
            if hwnd:
                await asyncio.to_thread(vlc_resume_fullscreen, hwnd, preferences)
        else:
            print("User exited browser fullscreen.")
            if vlc_is_original_foreground_window_topmost:
                await asyncio.to_thread(vlc_set_original_window_topmost, False)
            if hwnd:
                await asyncio.to_thread(vlc_safely_minimize_window, hwnd)
                await asyncio.sleep(0.1)
                await asyncio.to_thread(
                    vlc_remove_topmost,
                    hwnd,
                    width_percent=vlc_optimized_width_percentage,
                    height_percent=vlc_optimized_height_percentage,
                )
                await asyncio.to_thread(vlc_restore_borders, hwnd)
        return

    if message_type == "end":
        await asyncio.to_thread(vlc_end_plugin)
        return

    # Other Party Pack messages are intentionally ignored, matching the
    # behavior of the other bundled plugins for messages they don't use.


# -----------------------------------------------------------------------------
# Direct plugin runtime mapping
# -----------------------------------------------------------------------------
# All plugin code above has already been imported normally. These lightweight
# adapters expose each prefixed section through the same module-style API used
# by the Party Pack dispatcher. No exec(), compressed source, or lazy importing
# remains.
loaded_plugins.update({
    "ntfy-commercial-notifications": PluginRuntime("ntfy_"),
    "ai-commercial-detector-ws": PluginRuntime("ai_"),
    "overlay-any-window": PluginRuntime("window_"),
    "speak-keyword-trigger-plugin": PluginRuntime("voice_"),
    "gesture-trigger-plugin": PluginRuntime("gesture_"),
    "vlc-over-commercials": PluginRuntime("vlc_"),
})


if __name__ == "__main__":
    def run_async_services():
        try:
            asyncio.run(main())
        except Exception:
            print("Combined server error:\n" + traceback.format_exc())

    services_thread = threading.Thread(
        target=run_async_services,
        name="OfficialPluginPartyPack",
        daemon=False,
    )
    services_thread.start()

    try:
        start_tray()
    except KeyboardInterrupt:
        request_combined_shutdown()
    except Exception:
        print("Tray icon error:\n" + traceback.format_exc())
