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

COOLDOWN = 1.0

# --------------------------------------------------
# Global control state
# --------------------------------------------------

listening_task = None
listening_active = asyncio.Event()

# --------------------------------------------------
# Helpers
# --------------------------------------------------

audio_queue = queue.Queue()

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
                        if text:
                            print("[FINAL]", text)

                    else:
                        partial = json.loads(recognizer.PartialResult())
                        text = partial.get("partial", "").lower().strip()

                        if text and text != last_partial_text:
                            print("[PARTIAL]", text)
                            last_partial_text = text

                            await send_status(ws, None, text)

                            for phrase, config in TARGET_PHRASES.items():
                                if phrase in text:
                                    if now - last_trigger_time > COOLDOWN:
                                        print("TRIGGERED:", config["action"])

                                        is_commercial = config["action"] == "commercial"

                                        display = "\uD83D\uDDE3 \u2705"

                                        await send_commercial_state_change(
                                            ws,
                                            is_commercial,
                                            display,
                                            "Keyword Detected"
                                        )

                                        last_trigger_time = now

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

        # Stop listening ONLY if no clients remain
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
# Message handler
# --------------------------------------------------

async def handle_message(ws, msg):
    global listening_task

    message_type = msg["type"]

    if message_type == "init":
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
        is_commercial = msg["data"]["isCommercialState"]

        new_display = "\uD83D\uDDE3 " + get_all_emojis_for_action("commercial")

        if is_commercial:
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
        print("send_commercial_state_change failed: disconnected")

async def send_status(ws, display, debug):
    try:
        await ws.send(json.dumps({
            "type": "status",
            "timestamp": time.time(),
            "data": {},
            "meta": {"display": display, "debug": debug}
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_commercial_state_change failed: disconnected")

# --------------------------------------------------
# Main
# --------------------------------------------------

async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"Server running on ws://localhost:{PORT}")
        await asyncio.Future()

asyncio.run(main())