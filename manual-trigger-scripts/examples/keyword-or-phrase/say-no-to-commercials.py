import asyncio
import websockets
import json
import time
import queue
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import os

PORT = 64145

clients = set()

# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model/vosk-model-small-en-us-0.15")

TARGET_PHRASES = {
    "banana": {
        "action": "content", 
        "emoji": "\uD83C\uDF4C",
        },
    "tomato": {
        "action": "commercial", 
        "emoji": "\uD83C\uDF45"
        }
}

COOLDOWN = 3.0

# --------------------------------------------------
# Global state
# --------------------------------------------------

listening_task = None
listening_active = asyncio.Event()
audio_queue = queue.Queue()

current_is_commercial = None

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def get_all_emojis_for_action(action):
    return " ".join(
        config["emoji"]
        for config in TARGET_PHRASES.values()
        if config.get("action") == action
    )

def audio_callback(indata, frames, time_info, status):
    if status:
        print("Audio status:", status)
    audio_queue.put(bytes(indata))

def find_trigger_config(text):
    words = text.split()
    for phrase, config in TARGET_PHRASES.items():
        if phrase in words:
            return phrase, config
    return None, None

async def handle_trigger(ws, phrase, config, now, last_trigger_time, source):
    global current_is_commercial

    if now - last_trigger_time <= COOLDOWN:
        return last_trigger_time

    # Determine desired state
    new_is_commercial = config["action"] == "commercial"

    # Only trigger if state would change
    if current_is_commercial is not None and new_is_commercial == current_is_commercial:
        print(f"IGNORED ({source}): already in desired state")
        return last_trigger_time

    print(f"TRIGGERED ({source}):", config["action"])

    display = "\uD83D\uDDE3 \u2705"

    await send_commercial_state_change(
        ws,
        new_is_commercial,
        display,
        f"Keyword Detected ({source})"
    )

    current_is_commercial = new_is_commercial

    return now

async def process_text(ws, text, now, last_trigger_time, source, last_partial_text):
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

    await send_status(ws, None, source + ":" + text) #TODO: does this make sense here?

    phrase, config = find_trigger_config(text)

    if config:
        last_trigger_time = await handle_trigger(
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

async def listen_loop(ws):
    try:
        if not os.path.exists(MODEL_PATH):
            print("Model not found:", MODEL_PATH)
            return

        print("Loading Vosk model...")
        model = Model(MODEL_PATH)

        recognizer = KaldiRecognizer(model, 16000)

        last_trigger_time = 0
        last_partial_text = ""

        while True:
            await listening_active.wait()
            print("Listening started")

            with sd.RawInputStream(
                samplerate=16000,
                blocksize=4000,
                dtype="int16",
                channels=1,
                callback=audio_callback
            ):
                while listening_active.is_set():
                    data = audio_queue.get()
                    now = time.time()

                    if recognizer.AcceptWaveform(data):
                        result = json.loads(recognizer.Result())
                        text = result.get("text", "").lower().strip()

                        last_trigger_time, last_partial_text = await process_text(
                            ws, text, now, last_trigger_time, "final", last_partial_text
                        )

                    else:
                        partial = json.loads(recognizer.PartialResult())
                        text = partial.get("partial", "").lower().strip()

                        last_trigger_time, last_partial_text = await process_text(
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

async def handle_client(websocket):
    global listening_task

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

        if len(clients) == 0:
            print("Stopping listener (no clients)")
            listening_active.clear()

            if listening_task:
                listening_task.cancel()
                try:
                    await listening_task
                except asyncio.CancelledError:
                    print("Listening task cancelled")

                listening_task = None

        print("Client disconnected")

# --------------------------------------------------
# Message handling
# --------------------------------------------------

async def handle_message(ws, msg):
    global listening_task, current_is_commercial

    message_type = msg["type"]

    if message_type == "plugin_manifest":
        await send_manifest(ws)

    elif message_type == "init":
        # Initialize global state if provided
        current_is_commercial = msg.get("data", {}).get("isCommercialState")

        await send_status(
            ws,
            "\uD83D\uDDE3 " + get_all_emojis_for_action("commercial"),
            "Ready"
        )

        listening_active.set()

        if not listening_task:
            print("Starting listening task")
            listening_task = asyncio.create_task(listen_loop(ws))

    elif message_type == "commercial_state_change":
        current_is_commercial = msg["data"]["isCommercialState"]

        new_display = "\uD83D\uDDE3 " + get_all_emojis_for_action("commercial")

        if current_is_commercial:
            new_display = "\uD83D\uDDE3 " + get_all_emojis_for_action("content")

        await send_status(ws, new_display, "update display")

    elif message_type == "browser_fullscreen_state_change":
        print("Fullscreen:", msg["data"]["isFullscreen"])

# --------------------------------------------------
# Send helpers
# --------------------------------------------------

async def send_commercial_state_change(ws, is_commercial, display, debug):
    try:
        await ws.send(json.dumps({
            "type": "commercial_state_change",
            "timestamp": time.time(),
            "data": {"isCommercial": is_commercial},
            "meta": {"display": display, "debug": debug}
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_commercial_state_change failed")

async def send_status(ws, display, debug):
    try:
        await ws.send(json.dumps({
            "type": "status",
            "timestamp": time.time(),
            "data": {},
            "meta": {"display": display, "debug": debug}
        }))
    except websockets.exceptions.ConnectionClosed:
        pass

async def send_manifest(ws):
    try:
        await ws.send(json.dumps({
            "type": "plugin_manifest",
            "timestamp": time.time(),
            "data": {
                "name": "Say NO to Commercials",
                "id": "my-trigger-plugin-ws", # Must be unique
                "version": "1.0.0",
                "description": "My trigger plugin description.", # Optional
                "primaryColor": "#12384d", # Optional
                "secondaryColor": "#dadcdc", # Optional
                "capabilities": ["detection"], #TODO: delete this?
            },
            "meta": {
                "display": "Sending Manifest",
                "debug": "Sending Manifest",
            },
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_status send stopped: client disconnected")

# --------------------------------------------------
# Main
# --------------------------------------------------

async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"Server running on ws://localhost:{PORT}")
        await asyncio.Future()

asyncio.run(main())