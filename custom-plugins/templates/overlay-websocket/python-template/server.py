
import asyncio
import websockets
import json
import time

PLUGIN_PROTOCOL_VERSION = 1 # DO NOT TOUCH

PLUGIN_NAME = "My Overlay Plugin (WS)"
PLUGIN_ID = "my-overlay-plugin-ws" # Must be unique
PLUGIN_VERSION = "1.0.0"

PORT = 64146

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
    custom_overlay_plugin_preferences = preferences.get("pluginOverlayPreferences", {}).get("preferences", {}) # First time plugin users might not have this when they call for manifest

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
        print(custom_overlay_plugin_preferences)

        # Optionally send status to present it to user
        await send_status(ws, "Connected", "Ready")

    elif message_type == "commercial_state_change":
        is_commercial = msg["data"]["isCommercialState"]
        commercial_state_trigger = msg["data"]["utilities"]["triggerOfLastCommercialStateChange"]
        
        print("Commercial state change. is_commercial = ", is_commercial, ", commercial_state_trigger = ", commercial_state_trigger)

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = msg["data"]["isFullscreen"]

        print("Fullscreen state changed on browser. is_fullscreen = ", is_fullscreen)

async def send_status(ws, display, debug, display_type="info", display_time=7000):
    try:
        await ws.send(json.dumps({
            "type": "status",
            "timestamp": time.time(),
            "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
            "data": {},
            "meta": {
                "display": display,
                "displayType": display_type, # optional - "info" for blue and "error" for red.
                "displayTime": display_time, # optional - time until message disapears. disapears after 7 seconds if not sent.
                "debug": debug,
            },
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_status send stopped: client disconnected")

async def send_manifest(ws):
    try:
        await ws.send(json.dumps({
            "type": "plugin_manifest",
            "timestamp": time.time(),
            "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
            "data": {
                "name": PLUGIN_NAME,
                "id": PLUGIN_ID,
                "version": PLUGIN_VERSION,
                "description": "My overlay plugin description.", # Optional
                "informationalURL": "https://github.com/RG-O/YoutubeOverCommercials/tree/main/custom-plugins", # Optional
                "primaryColor": "#12384d", # Optional
                "secondaryColor": "#dadcdc", # Optional
                "capabilities": ["overlay"],
                "preferences": [ # Optional
                    {
                        "key": "text-field-example",
                        "label": "Text",
                        "tooltip": "Example of a text field.", # Optional
                        "description": "Example of a text field.", # Optional
                        "type": "text",
                        "default": "Default Text", # Optional
                    },
                    {
                        "key": "number-field-example",
                        "label": "Number",
                        "tooltip": "Example of a number field.", # Optional
                        "description": "Example of a number field.", # Optional
                        "type": "number",
                        "default": 50, # Optional
                    },
                    {
                        "key": "checkbox-field-example",
                        "label": "Checkbox",
                        "tooltip": "Example of a checkbox field.", # Optional
                        "description": "Example of a checkbox field.", # Optional
                        "type": "checkbox",
                        "default": False, # Optional
                    },
                    {
                        "key": "dropdown-field-example",
                        "label": "Dropdown",
                        "tooltip": "Example of a dropdown field.", # Optional
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
                        "tooltip": "Example of a radio field.", # Optional
                        "description": "Example of a radio field.", # Optional
                        "type": "radio",
                        "options": [
                            {
                                "label": "Value 1",
                                "tooltip": "Example of a radio button option - value 1", # Optional
                                "value": "value-1"
                            },
                            {
                                "label": "Value 2",
                                "tooltip": "Example of a radio button option - value 2", # Optional
                                "value": "value-2"
                            },
                        ],
                        "default": "value-2",
                    },
                    {
                        "key": "textarea-field-example",
                        "label": "Text Area",
                        "tooltip": "Example of a text area field.", # Optional
                        "description": "Example of a text area field.", # Optional
                        "type": "textarea",
                        "default": "Default Text", # Optional
                    },
                ],
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
