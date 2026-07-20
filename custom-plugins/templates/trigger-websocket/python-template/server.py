
import asyncio
import websockets
import json
import time

plugin_protocol_version = 1 # DO NOT TOUCH

plugin_name = "My Trigger Plugin"
plugin_id = "my-trigger-plugin-ws" # Must be unique
plugin_version = "1.0.0"

PORT = 64145

clients = set()

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
    message_type = msg["type"]
    preferences = msg["data"]["preferences"]
    custom_trigger_plugin_preferences = preferences.get("pluginTriggerPreferences", {}).get("preferences", {}) # First time plugin users might not have this when they call for manifest

    if message_type == "plugin_manifest":
        print("Plugin Manifest Requested. Sending Manifest.")
        await send_manifest(ws)

    if message_type == "init":
        print("Extension initiated")
        print("Full message:")
        print(msg)
        print("Full preferences:")
        print(preferences)
        print("Your custom requested plugin preferences:")
        print(custom_trigger_plugin_preferences)

        # Send initial message
        print("Returning connected status")
        await send_status(ws, plugin_name + " connected!", plugin_name + " ready")

        # Start detection loop
        asyncio.create_task(demo_loop(ws))

    elif message_type == "commercial_state_change":
        is_commercial = msg["data"]["isCommercialState"]
        commercial_state_trigger = msg["data"]["utilities"]["triggerOfLastCommercialStateChange"]

        if commercial_state_trigger != "plugin":
            print("Confirmed commercial state changed in extension. is_commercial = ", is_commercial, ", commercial_state_trigger = ", commercial_state_trigger)
        else:
            print("Commercial state changed by extension. is_commercial = ", is_commercial, ", commercial_state_trigger = ", commercial_state_trigger)

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = msg["data"]["isFullscreen"]

        print("Fullscreen state changed on browser. is_fullscreen = ", is_fullscreen)

async def demo_loop(ws):
    is_commercial = False

    while not ws.close_code is not None:
        await asyncio.sleep(7)

        # Example toggle logic
        is_commercial = not is_commercial

        display = "Commercial" if is_commercial else "Content"
        debug = "Toggled for demo"

        print("sending extension commercial_state_change. isCommercial = ", is_commercial)

        await send_commercial_state_change(ws, is_commercial, display, debug)

async def send_commercial_state_change(ws, is_commercial, display, debug):
    global plugin_protocol_version

    try:
        await ws.send(json.dumps({
            "type": "commercial_state_change",
            "timestamp": time.time(),
            "pluginProtocolVersion": plugin_protocol_version,
            "data": {
                "isCommercial": is_commercial
            },
            "meta": {
                "display": display,
                "debug": debug
            }
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_commercial_state_change stopped: client disconnected")

# This can be used to disable or enable any auto commercial detection that the browser extension is doing
async def send_auto_commercial_blocked_state_change(ws, is_auto_commercial_blocked, display, debug):
    global plugin_protocol_version

    try:
        await ws.send(json.dumps({
            "type": "auto_commercial_blocked_state_change",
            "timestamp": time.time(),
            "pluginProtocolVersion": plugin_protocol_version,
            "data": {
                "isAutoCommercialBlocked": is_auto_commercial_blocked
            },
            "meta": {
                "display": display,
                "debug": debug
            }
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_auto_commercial_blocked_state_change stopped: client disconnected")

async def send_status(ws, display, debug):
    global plugin_protocol_version

    try:
        await ws.send(json.dumps({
            "type": "status",
            "timestamp": time.time(),
            "pluginProtocolVersion": plugin_protocol_version,
            "data": {},
            "meta": {
                "display": display,
                "debug": debug
            }
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_status send stopped: client disconnected")

async def send_manifest(ws):
    global plugin_name
    global plugin_id
    global plugin_version
    global plugin_protocol_version

    try:
        await ws.send(json.dumps({
            "type": "plugin_manifest",
            "timestamp": time.time(),
            "pluginProtocolVersion": plugin_protocol_version,
            "data": {
                "name": plugin_name,
                "id": plugin_id,
                "version": plugin_version,
                "description": "My trigger plugin description.", # Optional
                "primaryColor": "#12384d", # Optional
                "secondaryColor": "#dadcdc", # Optional
                "capabilities": ["trigger"],
                "preferences": [
                    {
                        "key": "text-field-example",
                        "label": "Text",
                        "description": "Example of a text field.", # Optional
                        "type": "text",
                        "default": "Default Text", # Optional
                    },
                    {
                        "key": "number-field-example",
                        "label": "Number",
                        "description": "Example of a number field.", # Optional
                        "type": "number",
                        "default": 50, # Optional
                    },
                    {
                        "key": "checkbox-field-example",
                        "label": "Checkbox",
                        "description": "Example of a checkbox field.", # Optional
                        "type": "checkbox",
                        "default": False, # Optional
                    },
                    {
                        "key": "dropdown-field-example",
                        "label": "Dropdown",
                        "description": "Example of a dropdown field.", # Optional
                        "type": "select",
                        "options": [
                            { "label": "Value 1", "value": "value-1" },
                            { "label": "Value 2", "value": "value-2" },
                        ],
                        "default": "value-1",
                    },
                    {
                        "key": "radio-field-example",
                        "label": "Radio",
                        "description": "Example of a radio field.", # Optional
                        "type": "radio",
                        "options": [
                            { "label": "Value 1", "value": "value-1" },
                            { "label": "Value 2", "value": "value-2" },
                        ],
                        "default": "value-2",
                    },
                    {
                        "key": "textarea-field-example",
                        "label": "Text Area",
                        "description": "Example of a text area field.", # Optional
                        "type": "textarea",
                        "default": "Default Text", # Optional
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

async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"Server running on ws://localhost:{PORT}")
        await asyncio.Future()

asyncio.run(main())
