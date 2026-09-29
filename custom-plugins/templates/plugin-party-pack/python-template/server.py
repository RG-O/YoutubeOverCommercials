import asyncio
import json
import time

import websockets


PLUGIN_PROTOCOL_VERSION = 1 # DO NOT TOUCH

BUNDLE_NAME = "Official Plugin Party Pack"
BUNDLE_ID = "official-plugin-party-pack"
BUNDLE_VERSION = "1.0.0"

PORT = 64147

clients = set()

# Current state reported by the extension. These are global because the Party
# Pack normally serves one active browser session at a time.
is_commercial = False
is_fullscreen = True

# Each demo trigger owns its own task collection. The plugins do not share
# timing/state with each other; they only observe extension-reported global state.
trigger_10_second_tasks = {}
trigger_21_second_tasks = {}


# ---------------------------------------------------------------------------
# BUNDLED PLUGINS
#
# Each bundled plugin has one normal plugin manifest. The bundle-level manifest
# below only advertises which plugins exist and their capabilities.
#
# Add/remove bundled plugins by editing BUNDLED_PLUGIN_MANIFESTS and then add
# the corresponding handler functions farther down in this file.
# ---------------------------------------------------------------------------

BUNDLED_PLUGIN_MANIFESTS = {
    "party-pack-trigger-example": {
        "name": "Party Pack Trigger Example - 10 Seconds",
        "id": "party-pack-trigger-example",
        "version": "1.0.0",
        "description": "Demo trigger plugin that switches commercial mode every 10 seconds.",
        "informationalURL": "https://github.com/RG-O/YoutubeOverCommercials/tree/main/custom-plugins",
        "primaryColor": "#12384d",
        "secondaryColor": "#dadcdc",
        "capabilities": ["trigger"],
        "preferences": [
            {
                "key": "trigger-message",
                "label": "Trigger Message",
                "tooltip": "Example setting belonging only to this bundled trigger plugin.",
                "type": "text",
                "default": "10-second demo trigger is ready",
            },
        ],
    },
    "party-pack-trigger-example-2": {
        "name": "Party Pack Trigger Example - 21 Seconds",
        "id": "party-pack-trigger-example-2",
        "version": "1.0.0",
        "description": "Second demo trigger plugin that switches commercial mode every 21 seconds.",
        "informationalURL": "https://github.com/RG-O/YoutubeOverCommercials/tree/main/custom-plugins",
        "primaryColor": "#12384d",
        "secondaryColor": "#dadcdc",
        "capabilities": ["trigger"],
        "preferences": [
            {
                "key": "trigger-message",
                "label": "Trigger Message",
                "tooltip": "Example setting belonging only to this bundled trigger plugin.",
                "type": "text",
                "default": "21-second demo trigger is ready",
            },
        ],
    },
    "party-pack-overlay-example": {
        "name": "Party Pack Overlay Example",
        "id": "party-pack-overlay-example",
        "version": "1.0.0",
        "description": "Example overlay-only plugin bundled with the Official Plugin Party Pack.",
        "informationalURL": "https://github.com/RG-O/YoutubeOverCommercials/tree/main/custom-plugins",
        "primaryColor": "#12384d",
        "secondaryColor": "#dadcdc",
        "capabilities": ["overlay"],
        "preferences": [
            {
                "key": "overlay-message",
                "label": "Overlay Message",
                "tooltip": "Example setting belonging only to this bundled overlay plugin.",
                "type": "text",
                "default": "Party Pack overlay is ready",
            },
        ],
    },
    "party-pack-overlay-example-2": {
        "name": "Party Pack Overlay Example 2",
        "id": "party-pack-overlay-example-2",
        "version": "1.0.0",
        "description": "Second example overlay-only plugin bundled with the Official Plugin Party Pack.",
        "informationalURL": "https://github.com/RG-O/YoutubeOverCommercials/tree/main/custom-plugins",
        "primaryColor": "#12384d",
        "secondaryColor": "#dadcdc",
        "capabilities": ["overlay"],
        "preferences": [
            {
                "key": "overlay-message",
                "label": "Overlay Message",
                "tooltip": "Example setting belonging only to this second bundled overlay plugin.",
                "type": "text",
                "default": "Party Pack overlay 2 is ready",
            },
            {
                "key": "show-status",
                "label": "Show Status",
                "tooltip": "Example checkbox preference for the second overlay plugin.",
                "type": "checkbox",
                "default": True,
            },
        ],
    },
    "party-pack-dual-example": {
        "name": "Party Pack Dual Example",
        "id": "party-pack-dual-example",
        "version": "1.0.0",
        "description": "Example bundled plugin that can act as both a trigger and an overlay.",
        "informationalURL": "https://github.com/RG-O/YoutubeOverCommercials/tree/main/custom-plugins",
        "primaryColor": "#12384d",
        "secondaryColor": "#dadcdc",
        "capabilities": ["trigger", "overlay"],
        "preferences": [
            {
                "key": "enabled-message",
                "label": "Enabled Message",
                "tooltip": "The same settings object is used whether this plugin is enabled as a trigger, overlay, or both.",
                "type": "text",
                "default": "Party Pack dual plugin is ready",
            },
            {
                "key": "show-status",
                "label": "Show Status",
                "tooltip": "Example checkbox setting.",
                "type": "checkbox",
                "default": True,
            },
        ],
    },
}


# State is per WebSocket connection because different browser-extension
# instances could theoretically connect with different Party Pack selections.
client_states = {}


async def handle_client(websocket):
    print("Client connected")
    clients.add(websocket)
    client_states[websocket] = {
        "triggerPluginIds": [],
        "overlayPluginIds": [],
        "pluginPreferencesById": {},
    }

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                await handle_screenshot(websocket, message)
            else:
                msg = json.loads(message)
                await handle_message(websocket, msg)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        cancel_all_demo_trigger_tasks_for_websocket(websocket)
        clients.discard(websocket)
        client_states.pop(websocket, None)
        print("Client disconnected")


async def handle_message(ws, msg):
    global is_commercial, is_fullscreen

    message_type = msg.get("type")

    # Popup asks for the lightweight list first. No individual plugin settings
    # are built in the popup until the user checks one of these plugins.
    if message_type == "plugin_bundle_manifest":
        print("Plugin Party Pack manifest requested.")
        await send_bundle_manifest(ws)
        return

    # Popup asks for one specific plugin manifest only after that plugin is
    # selected. This is the lazy-loading behavior.
    if message_type == "plugin_manifest":
        plugin_id = msg.get("data", {}).get("pluginId")
        print("Individual bundled plugin manifest requested:", plugin_id)
        await send_plugin_manifest(ws, plugin_id)
        return

    preferences = msg.get("data", {}).get("preferences", {})

    if message_type == "init":
        configure_client_from_init(ws, preferences)

        is_commercial = msg.get("data", {}).get("isCommercialState", False)
        is_fullscreen = msg.get("data", {}).get("isFullscreen", False)

        print("Extension initiated with Official Plugin Party Pack")
        print("Trigger plugins:", client_states[ws]["triggerPluginIds"])
        print("Overlay plugins:", client_states[ws]["overlayPluginIds"])

        # Initialize only the bundled plugins the user actually enabled.
        for plugin_id in get_enabled_plugin_ids(ws):
            await bundled_plugin_init(ws, plugin_id)


    elif message_type == "commercial_state_change":
        is_commercial = msg["data"]["isCommercialState"]

        # Only enabled overlay/dual plugins receive overlay work.
        for plugin_id in client_states[ws]["overlayPluginIds"]:
            await bundled_plugin_commercial_state_change(
                ws,
                plugin_id,
                is_commercial,
                msg,
            )

        # Trigger plugins can also be told about state changes so they can keep
        # themselves synchronized when another source caused the change.
        for plugin_id in client_states[ws]["triggerPluginIds"]:
            if plugin_id not in client_states[ws]["overlayPluginIds"]:
                await bundled_plugin_commercial_state_change(
                    ws,
                    plugin_id,
                    is_commercial,
                    msg,
                )

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = msg["data"]["isFullscreen"]

        for plugin_id in get_enabled_plugin_ids(ws):
            await bundled_plugin_fullscreen_state_change(
                ws,
                plugin_id,
                is_fullscreen,
                msg,
            )

    elif message_type == "end":
        for plugin_id in get_enabled_plugin_ids(ws):
            await bundled_plugin_end(ws, plugin_id)

        cancel_all_demo_trigger_tasks_for_websocket(ws)
        print("Extension stopped")


def configure_client_from_init(ws, preferences):
    party_pack_preferences = preferences.get("officialPluginPartyPack", {})

    trigger_plugin_ids = validate_enabled_plugin_ids(
        party_pack_preferences.get("triggerPluginIds", []),
        "trigger",
    )
    overlay_plugin_ids = validate_enabled_plugin_ids(
        party_pack_preferences.get("overlayPluginIds", []),
        "overlay",
    )

    client_states[ws] = {
        "triggerPluginIds": trigger_plugin_ids,
        "overlayPluginIds": overlay_plugin_ids,
        "pluginPreferencesById": preferences.get("pluginPreferencesById", {}),
    }


def validate_enabled_plugin_ids(plugin_ids, required_capability):
    valid_plugin_ids = []

    for plugin_id in plugin_ids:
        manifest = BUNDLED_PLUGIN_MANIFESTS.get(plugin_id)

        if (
            manifest
            and required_capability in manifest.get("capabilities", [])
            and plugin_id not in valid_plugin_ids
        ):
            valid_plugin_ids.append(plugin_id)

    return valid_plugin_ids


def get_enabled_plugin_ids(ws):
    state = client_states.get(ws, {})

    return list(dict.fromkeys(
        state.get("triggerPluginIds", []) +
        state.get("overlayPluginIds", [])
    ))


def get_bundled_plugin_preferences(ws, plugin_id):
    # This is the important part of the new preference model:
    # settings are looked up by plugin ID, not by trigger/overlay role.
    return (
        client_states
        .get(ws, {})
        .get("pluginPreferencesById", {})
        .get(plugin_id, {})
        .get("preferences", {})
    )


# ---------------------------------------------------------------------------
# PARTY PACK TRIGGER EXAMPLE - 10 SECONDS
# ---------------------------------------------------------------------------

def start_trigger_10_second_task(ws):
    existing_task = trigger_10_second_tasks.get(ws)

    if existing_task and not existing_task.done():
        return

    trigger_10_second_tasks[ws] = asyncio.create_task(
        trigger_10_second_loop(ws)
    )


def cancel_trigger_10_second_task(ws):
    task = trigger_10_second_tasks.pop(ws, None)
    if task and not task.done():
        task.cancel()


async def trigger_10_second_loop(ws):
    try:
        while True:
            await asyncio.sleep(10)

            # Ask the extension to switch away from its most recently reported
            # state. Do NOT update is_commercial here. The extension is the
            # source of truth and will report the new state back if successful.
            requested_is_commercial = not is_commercial

            await send_bundled_commercial_state_change(
                ws,
                "party-pack-trigger-example",
                requested_is_commercial,
                f"10-second demo requested commercial mode {requested_is_commercial}",
                "10-second trigger demo fired",
            )

    except asyncio.CancelledError:
        pass
    finally:
        trigger_10_second_tasks.pop(ws, None)


# ---------------------------------------------------------------------------
# PARTY PACK TRIGGER EXAMPLE - 21 SECONDS
# ---------------------------------------------------------------------------

def start_trigger_21_second_task(ws):
    existing_task = trigger_21_second_tasks.get(ws)

    if existing_task and not existing_task.done():
        return

    trigger_21_second_tasks[ws] = asyncio.create_task(
        trigger_21_second_loop(ws)
    )


def cancel_trigger_21_second_task(ws):
    task = trigger_21_second_tasks.pop(ws, None)
    if task and not task.done():
        task.cancel()


async def trigger_21_second_loop(ws):
    try:
        while True:
            await asyncio.sleep(21)

            # This plugin independently asks the extension for the opposite of
            # the extension's most recently reported state. It does not alter
            # the shared state itself.
            requested_is_commercial = not is_commercial

            await send_bundled_commercial_state_change(
                ws,
                "party-pack-trigger-example-2",
                requested_is_commercial,
                f"21-second demo requested commercial mode {requested_is_commercial}",
                "21-second trigger demo fired",
            )

    except asyncio.CancelledError:
        pass
    finally:
        trigger_21_second_tasks.pop(ws, None)


def cancel_all_demo_trigger_tasks_for_websocket(ws):
    cancel_trigger_10_second_task(ws)
    cancel_trigger_21_second_task(ws)


async def handle_screenshot(ws, screenshot_bytes):
    # A real bundle can route screenshots only to enabled plugins whose
    # manifest includes the "screenshots" capability.
    for plugin_id in get_enabled_plugin_ids(ws):
        manifest = BUNDLED_PLUGIN_MANIFESTS[plugin_id]

        if "screenshots" in manifest.get("capabilities", []):
            await bundled_plugin_screenshot(ws, plugin_id, screenshot_bytes)


# ---------------------------------------------------------------------------
# BUNDLED PLUGIN HANDLERS
#
# These generic example handlers make it obvious where to branch into the real
# code for each bundled plugin. You can replace their bodies with per-plugin
# functions/classes later without changing the bundle protocol.
# ---------------------------------------------------------------------------

async def bundled_plugin_init(ws, plugin_id):
    if plugin_id == "party-pack-trigger-example":
        await trigger_10_second_init(ws)
    elif plugin_id == "party-pack-trigger-example-2":
        await trigger_21_second_init(ws)
    elif plugin_id == "party-pack-overlay-example":
        await overlay_example_init(ws)
    elif plugin_id == "party-pack-overlay-example-2":
        await overlay_example_2_init(ws)
    elif plugin_id == "party-pack-dual-example":
        await dual_example_init(ws)


async def bundled_plugin_commercial_state_change(ws, plugin_id, current_is_commercial, full_message):
    if plugin_id == "party-pack-trigger-example":
        await trigger_10_second_commercial_state_change(ws, current_is_commercial, full_message)
    elif plugin_id == "party-pack-trigger-example-2":
        await trigger_21_second_commercial_state_change(ws, current_is_commercial, full_message)
    elif plugin_id == "party-pack-overlay-example":
        await overlay_example_commercial_state_change(ws, current_is_commercial, full_message)
    elif plugin_id == "party-pack-overlay-example-2":
        await overlay_example_2_commercial_state_change(ws, current_is_commercial, full_message)
    elif plugin_id == "party-pack-dual-example":
        await dual_example_commercial_state_change(ws, current_is_commercial, full_message)


async def bundled_plugin_fullscreen_state_change(ws, plugin_id, current_is_fullscreen, full_message):
    if plugin_id == "party-pack-trigger-example":
        await trigger_10_second_fullscreen_state_change(ws, current_is_fullscreen, full_message)
    elif plugin_id == "party-pack-trigger-example-2":
        await trigger_21_second_fullscreen_state_change(ws, current_is_fullscreen, full_message)
    elif plugin_id == "party-pack-overlay-example":
        await overlay_example_fullscreen_state_change(ws, current_is_fullscreen, full_message)
    elif plugin_id == "party-pack-overlay-example-2":
        await overlay_example_2_fullscreen_state_change(ws, current_is_fullscreen, full_message)
    elif plugin_id == "party-pack-dual-example":
        await dual_example_fullscreen_state_change(ws, current_is_fullscreen, full_message)


async def bundled_plugin_screenshot(ws, plugin_id, screenshot_bytes):
    if plugin_id == "party-pack-trigger-example":
        await trigger_10_second_screenshot(ws, screenshot_bytes)
    elif plugin_id == "party-pack-trigger-example-2":
        await trigger_21_second_screenshot(ws, screenshot_bytes)
    elif plugin_id == "party-pack-overlay-example":
        await overlay_example_screenshot(ws, screenshot_bytes)
    elif plugin_id == "party-pack-overlay-example-2":
        await overlay_example_2_screenshot(ws, screenshot_bytes)
    elif plugin_id == "party-pack-dual-example":
        await dual_example_screenshot(ws, screenshot_bytes)


async def bundled_plugin_end(ws, plugin_id):
    if plugin_id == "party-pack-trigger-example":
        await trigger_10_second_end(ws)
    elif plugin_id == "party-pack-trigger-example-2":
        await trigger_21_second_end(ws)
    elif plugin_id == "party-pack-overlay-example":
        await overlay_example_end(ws)
    elif plugin_id == "party-pack-overlay-example-2":
        await overlay_example_2_end(ws)
    elif plugin_id == "party-pack-dual-example":
        await dual_example_end(ws)


# ---------------------------------------------------------------------------
# PARTY PACK TRIGGER EXAMPLE - 10 SECONDS
# ---------------------------------------------------------------------------

async def trigger_10_second_init(ws):
    plugin_id = "party-pack-trigger-example"
    preferences = get_bundled_plugin_preferences(ws, plugin_id)
    print("[party-pack-trigger-example] init")
    print("[party-pack-trigger-example] preferences:", preferences)

    await send_status(
        ws,
        plugin_id,
        preferences.get("trigger-message", "10-second demo trigger is ready"),
        "10-second trigger plugin initialized",
    )

    start_trigger_10_second_task(ws)


async def trigger_10_second_commercial_state_change(ws, current_is_commercial, full_message):
    print("[party-pack-trigger-example] extension reported commercial state:", current_is_commercial)


async def trigger_10_second_fullscreen_state_change(ws, current_is_fullscreen, full_message):
    print("[party-pack-trigger-example] extension reported fullscreen state:", current_is_fullscreen)


async def trigger_10_second_screenshot(ws, screenshot_bytes):
    print("[party-pack-trigger-example] received screenshot:", len(screenshot_bytes), "bytes")


async def trigger_10_second_end(ws):
    cancel_trigger_10_second_task(ws)
    print("[party-pack-trigger-example] end")


# ---------------------------------------------------------------------------
# PARTY PACK TRIGGER EXAMPLE - 21 SECONDS
# ---------------------------------------------------------------------------

async def trigger_21_second_init(ws):
    plugin_id = "party-pack-trigger-example-2"
    preferences = get_bundled_plugin_preferences(ws, plugin_id)
    print("[party-pack-trigger-example-2] init")
    print("[party-pack-trigger-example-2] preferences:", preferences)

    await send_status(
        ws,
        plugin_id,
        preferences.get("trigger-message", "21-second demo trigger is ready"),
        "21-second trigger plugin initialized",
    )

    start_trigger_21_second_task(ws)


async def trigger_21_second_commercial_state_change(ws, current_is_commercial, full_message):
    print("[party-pack-trigger-example-2] extension reported commercial state:", current_is_commercial)


async def trigger_21_second_fullscreen_state_change(ws, current_is_fullscreen, full_message):
    print("[party-pack-trigger-example-2] extension reported fullscreen state:", current_is_fullscreen)


async def trigger_21_second_screenshot(ws, screenshot_bytes):
    print("[party-pack-trigger-example-2] received screenshot:", len(screenshot_bytes), "bytes")


async def trigger_21_second_end(ws):
    cancel_trigger_21_second_task(ws)
    print("[party-pack-trigger-example-2] end")


# ---------------------------------------------------------------------------
# PARTY PACK OVERLAY EXAMPLE
# ---------------------------------------------------------------------------

async def overlay_example_init(ws):
    plugin_id = "party-pack-overlay-example"
    preferences = get_bundled_plugin_preferences(ws, plugin_id)
    print("[party-pack-overlay-example] init")
    print("[party-pack-overlay-example] preferences:", preferences)

    await send_status(
        ws,
        plugin_id,
        preferences.get("overlay-message", "Party Pack overlay is ready"),
        "Overlay example initialized",
        display_type="info",
        display_time=7000,
    )


async def overlay_example_commercial_state_change(ws, current_is_commercial, full_message):
    print("[party-pack-overlay-example] extension reported commercial state:", current_is_commercial)


async def overlay_example_fullscreen_state_change(ws, current_is_fullscreen, full_message):
    print("[party-pack-overlay-example] extension reported fullscreen state:", current_is_fullscreen)


async def overlay_example_screenshot(ws, screenshot_bytes):
    print("[party-pack-overlay-example] received screenshot:", len(screenshot_bytes), "bytes")


async def overlay_example_end(ws):
    print("[party-pack-overlay-example] end")


# ---------------------------------------------------------------------------
# PARTY PACK OVERLAY EXAMPLE 2
# ---------------------------------------------------------------------------

async def overlay_example_2_init(ws):
    plugin_id = "party-pack-overlay-example-2"
    preferences = get_bundled_plugin_preferences(ws, plugin_id)
    print("[party-pack-overlay-example-2] init")
    print("[party-pack-overlay-example-2] preferences:", preferences)

    if preferences.get("show-status", True):
        await send_status(
            ws,
            plugin_id,
            preferences.get("overlay-message", "Party Pack overlay 2 is ready"),
            "Overlay example 2 initialized",
            display_type="info",
            display_time=7000,
        )


async def overlay_example_2_commercial_state_change(ws, current_is_commercial, full_message):
    print("[party-pack-overlay-example-2] extension reported commercial state:", current_is_commercial)


async def overlay_example_2_fullscreen_state_change(ws, current_is_fullscreen, full_message):
    print("[party-pack-overlay-example-2] extension reported fullscreen state:", current_is_fullscreen)


async def overlay_example_2_screenshot(ws, screenshot_bytes):
    print("[party-pack-overlay-example-2] received screenshot:", len(screenshot_bytes), "bytes")


async def overlay_example_2_end(ws):
    print("[party-pack-overlay-example-2] end")


# ---------------------------------------------------------------------------
# PARTY PACK DUAL EXAMPLE
# ---------------------------------------------------------------------------

async def dual_example_init(ws):
    plugin_id = "party-pack-dual-example"
    preferences = get_bundled_plugin_preferences(ws, plugin_id)
    print("[party-pack-dual-example] init")
    print("[party-pack-dual-example] preferences:", preferences)

    if preferences.get("show-status", True):
        await send_status(
            ws,
            plugin_id,
            preferences.get("enabled-message", "Party Pack dual plugin is ready"),
            "Dual plugin initialized",
        )


async def dual_example_commercial_state_change(ws, current_is_commercial, full_message):
    print("[party-pack-dual-example] extension reported commercial state:", current_is_commercial)


async def dual_example_fullscreen_state_change(ws, current_is_fullscreen, full_message):
    print("[party-pack-dual-example] extension reported fullscreen state:", current_is_fullscreen)


async def dual_example_screenshot(ws, screenshot_bytes):
    print("[party-pack-dual-example] received screenshot:", len(screenshot_bytes), "bytes")


async def dual_example_end(ws):
    print("[party-pack-dual-example] end")


# Call this from a bundled trigger plugin when it wants to change the
# extension's commercial state.
async def send_bundled_commercial_state_change(
    ws,
    plugin_id,
    new_is_commercial,
    display,
    debug,
):
    if plugin_id not in client_states.get(ws, {}).get("triggerPluginIds", []):
        print(f"Ignoring trigger from disabled bundled plugin: {plugin_id}")
        return

    try:
        await ws.send(json.dumps({
            "type": "commercial_state_change",
            "timestamp": time.time(),
            "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
            "data": {
                "isCommercial": new_is_commercial,
                "pluginId": plugin_id,
            },
            "meta": {
                "display": display,
                "debug": debug,
            },
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_bundled_commercial_state_change stopped: client disconnected")


async def send_status(
    ws,
    plugin_id,
    display,
    debug,
    display_type="info",
    display_time=7000,
):
    # Every Party Pack status message identifies the bundled plugin that sent
    # it. content.js uses this ID to keep trigger/dual displays separated.
    manifest = BUNDLED_PLUGIN_MANIFESTS.get(plugin_id, {})
    capabilities = manifest.get("capabilities", [])

    meta = {
        "display": display,
        "debug": debug,
    }

    # Trigger and dual plugins use persistent corner indicators in content.js,
    # so display timing/type does not apply to them. Overlay-only plugins still
    # use the normal temporary stacked screen messages.
    if "overlay" in capabilities and "trigger" not in capabilities:
        meta["displayType"] = display_type
        meta["displayTime"] = display_time

    try:
        await ws.send(json.dumps({
            "type": "status",
            "timestamp": time.time(),
            "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
            "data": {
                "pluginId": plugin_id,
            },
            "meta": meta,
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_status stopped: client disconnected")


async def request_screenshots(
    ws,
    should_send_screenshots=True,
    frequency_milliseconds=1000,
    max_width=854,
    max_height=480,
):
    try:
        await ws.send(json.dumps({
            "type": "request_screenshots",
            "timestamp": time.time(),
            "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
            "data": {
                "shouldSendScreenshots": should_send_screenshots,
                "frequencyMilliseconds": frequency_milliseconds,
                "maxDimensionsPixels": {
                    "height": max_height,
                    "width": max_width,
                },
                "trimOptionsPercentages": {
                    "top": 0,
                    "right": 0,
                    "bottom": 0,
                    "left": 0,
                },
            },
            "meta": {},
        }))
    except websockets.exceptions.ConnectionClosed:
        print("request_screenshots stopped: client disconnected")


async def send_bundle_manifest(ws):
    plugins = []

    for manifest in BUNDLED_PLUGIN_MANIFESTS.values():
        # Keep this response lightweight. The popup only needs enough
        # information to build the role-specific checkboxes.
        plugins.append({
            "name": manifest["name"],
            "id": manifest["id"],
            "version": manifest["version"],
            "description": manifest.get("description"),
            "capabilities": manifest.get("capabilities", []),
        })

    await ws.send(json.dumps({
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


async def send_plugin_manifest(ws, plugin_id):
    manifest = BUNDLED_PLUGIN_MANIFESTS.get(plugin_id)

    if not manifest:
        await ws.send(json.dumps({
            "type": "error",
            "timestamp": time.time(),
            "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
            "data": {
                "pluginId": plugin_id,
            },
            "meta": {
                "display": "Unknown bundled plugin",
                "debug": f"No manifest exists for bundled plugin ID: {plugin_id}",
            },
        }))
        return

    await ws.send(json.dumps({
        "type": "plugin_manifest",
        "timestamp": time.time(),
        "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
        "data": manifest,
        "meta": {
            "display": "Sending Manifest",
            "debug": f"Sending manifest for {plugin_id}",
        },
    }))


async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"{BUNDLE_NAME} running on ws://localhost:{PORT}")
        await asyncio.Future()


asyncio.run(main())
