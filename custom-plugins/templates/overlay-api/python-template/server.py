
from flask import Flask, request, jsonify

app = Flask(__name__)


#TODO: delete to keep all in one
@app.route("/init", methods=["POST"])
def init():
    data = request.json

    print(data)

    return jsonify({"status": "ok"})

@app.route("/custom-plugin-overlay-api", methods=["POST"])
def custom_plugin_overlay():
    data = request.json

    if data["type"] == "state_change":
        is_commercial = data["data"]["isCommercialState"]

        if is_commercial:
            print("START overlay")
        else:
            print("STOP overlay")
    elif data["type"] == "init":
        print(data)
    elif data["type"] == "end":
        print(data)


    return jsonify({"status": "ok"})

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})

if __name__ == "__main__":
    print("API running on http://localhost:64144")
    app.run(port=64144)
