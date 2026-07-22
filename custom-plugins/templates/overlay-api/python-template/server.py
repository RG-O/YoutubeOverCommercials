
from flask import Flask, request, jsonify
import time

PLUGIN_PROTOCOL_VERSION = 1 # DO NOT TOUCH

PLUGIN_NAME = "My Overlay Plugin (API)"
PLUGIN_ID = "my-overlay-plugin-api" # Must be unique
PLUGIN_VERSION = "1.0.0"

app = Flask(__name__)


@app.route("/custom-plugin-overlay-api", methods=["POST"])
def custom_plugin_overlay():
    msg = request.json
    message_type = msg["type"]
    preferences = msg["data"]["preferences"]
    custom_overlay_plugin_preferences = preferences.get("pluginOverlayPreferences", {}).get("preferences", {}) # First time plugin users might not have this when they call for manifest

    if message_type == "commercial_state_change":
        is_commercial = msg["data"]["isCommercialState"]

        if is_commercial:
            print("Commercial State Started")
        else:
            print("Commercial State Ended")

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = msg["data"]["isFullscreen"]

        if is_fullscreen:
            print("User entered fullscreen on browser")
            # Note: This does not get called before user initiates the extension
        else:
            print("User exited fullscreen on browser")
            # Note: commercial_state_change: is_commercial = false usually gets sent directly before this if user exited fullscreen during commercial

    elif message_type == "init":
        print("Extension initiated")
        print("Full message:")
        print(msg)
        print("Full preferences:")
        print(preferences)
        print("Your custom requested plugin preferences:")
        print(custom_overlay_plugin_preferences)

    elif message_type == "end":
        print("Extension Stopped")

    return jsonify({"status": "ok"})
    # If error or info you would like to display over main video on browser:
    # return jsonify({"status": "error", "message": "Error message goes here."})
    # return jsonify({"status": "info", "message": "Informational message goes here."})

@app.route("/plugin-manifest", methods=["GET"])
def plugin_manifest():
    global PLUGIN_NAME
    global PLUGIN_ID
    global PLUGIN_VERSION
    global PLUGIN_PROTOCOL_VERSION

    return jsonify({
        "type": "plugin_manifest",
        "timestamp": time.time(),
        "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
        "data": {
            "name": PLUGIN_NAME,
            "id": PLUGIN_ID,
            "version": PLUGIN_VERSION,
            "description": "My overlay plugin description.", # Optional
            "primaryColor": "#12384d", # Optional
            "secondaryColor": "#dadcdc", # Optional
            "capabilities": ["overlay"],
            "preferences": [ # Optional
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
            ],
        },
        "meta": {},
    })

@app.route("/ping", methods=["GET"])
def ping():
    print("ping")
    return jsonify({"status": "alive"})

if __name__ == "__main__":
    print("API running on http://localhost:64144")
    app.run(port=64144)
