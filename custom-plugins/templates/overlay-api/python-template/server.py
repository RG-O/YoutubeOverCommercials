
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.route("/custom-plugin-overlay-api", methods=["POST"])
def custom_plugin_overlay():
    data = request.json
    request_type = data["type"]

    if request_type == "commercial_state_change":
        is_commercial = data["data"]["isCommercialState"]

        if is_commercial:
            print("Commercial State Started")
        else:
            print("Commercial State Ended")
    if request_type == "browser_fullscreen_state_change":
        is_fullscreen = data["data"]["isFullscreen"]

        if is_fullscreen:
            print("User entered fullscreen on browser")
            # Note: This does not get called before user initiates the extension
        else:
            print("User exited fullscreen on browser")
            # Note: commercial_state_change: is_commercial = false usually gets sent directly before this if user exited fullscreen during commercial
    elif request_type == "init":
        print("Extension Initiated")
        print(data)
    elif request_type == "end":
        print("Extension Stopped")

    return jsonify({"status": "ok"})
    # If error you would like to display over main video on browser:
    # return jsonify({"status": "error", "error": "Error message goes here."})

@app.route("/ping", methods=["GET"])
def ping():
    print("ping")
    return jsonify({"status": "alive"})

if __name__ == "__main__":
    print("API running on http://localhost:64144")
    app.run(port=64144)
