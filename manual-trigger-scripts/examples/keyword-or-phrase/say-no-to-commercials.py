import asyncio
from tracemalloc import start
from asyncio.windows_events import NULL
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

# Phrases to detect
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

COOLDOWN = 1.0  # seconds between triggers

# --------------------------------------------------
# WebSocket server
# --------------------------------------------------

# connected_clients = set()

# async def handler(websocket):
#     connected_clients.add(websocket)
#     print("Extension connected")
#     try:
#         await websocket.wait_closed()
#     finally:
#         connected_clients.remove(websocket)
#         print("Extension disconnected")

# async def send_event(event):
#     if connected_clients:
#         message = json.dumps(event)
#         await asyncio.gather(*(ws.send(message) for ws in connected_clients))

# --------------------------------------------------
# Audio setup
# --------------------------------------------------

audio_queue = queue.Queue()

def get_all_emojis_for_action(action):
    return " ".join(
        config["emoji"] 
        for config in TARGET_PHRASES.values()
        if config.get("action") == action
    )


def audio_callback(indata, frames, time_info, status):
    """Called continuously by sounddevice to collect microphone audio"""
    if status:
        print("Audio status:", status)
    audio_queue.put(bytes(indata))

# --------------------------------------------------
# Main voice loop
# --------------------------------------------------

async def listen_loop(ws):
    global last_trigger_time

    if not os.path.exists(MODEL_PATH):
        print("Model not found at:", MODEL_PATH)
        return

    print("Loading Vosk model...")
    model = Model(MODEL_PATH)

    recognizer = KaldiRecognizer(model, 16000)

    print("Listening for voice commands...")

    last_trigger_time = 0
    last_partial_text = ""

    # Start microphone stream
    with sd.RawInputStream(
        samplerate=16000,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=audio_callback
    ):

        while True:
            data = audio_queue.get()
            now = time.time()

            if recognizer.AcceptWaveform(data):
                # Final result (you can ignore or keep for debugging)
                result = json.loads(recognizer.Result())
                text = result.get("text", "").lower().strip()
                if text:
                    print(f"[FINAL] {text}")

            else:
                # Partial (REAL-TIME)
                partial = json.loads(recognizer.PartialResult())
                text = partial.get("partial", "").lower().strip()

                if text and text != last_partial_text:
                    print(f"[PARTIAL] {text}")
                    last_partial_text = text

                    #TODO: set this to only do it in debug mode #TODO: have some sort of queue so messages sent at the same time don't mess eachother up
                    # await send_status(ws, None, text)

                    # Check for trigger words immediately
                    for phrase, config in TARGET_PHRASES.items():
                        if phrase in text:
                            if now - last_trigger_time > COOLDOWN:
                                print(f"TRIGGERED: {config["action"]}")

                                # await send_event({
                                #     "type": "gesture",
                                #     "gesture": mapped_name,
                                #     "timestamp": now,
                                #     "source": "voice"
                                # })

                                is_commercial = False

                                if config["action"] == "commercial":
                                    is_commercial = True

                                print("sending is_commercial as")
                                print(is_commercial)

                                display = "\uD83D\uDDE3 \u2705"

                                # await ws.send(json.dumps({
                                #     "type": "state_update",
                                #     "timestamp": time.time(),
                                #     "data": {
                                #         "isCommercial": is_commercial
                                #     },
                                #     "meta": {
                                #         "display": display,
                                #         "debug": "Toggled for demo"
                                #     }
                                # }))

                                await send_commercial_state_change(ws, is_commercial, display, "Keyword Detected")

                                # new_display = "\uD83D\uDDE3 " + get_all_emojis_for_action("content")

                                # if is_commercial:
                                #     new_display = "\uD83D\uDDE3 " + get_all_emojis_for_action("commercial")

                                # #delayed_update_display_with_emojis(ws, new_display, "update display")
                                # await asyncio.sleep(1) #TODO: do this here? can I run this asyncronusly?
                                # await send_status(ws, new_display, "update display")

                                last_trigger_time = now

            await asyncio.sleep(0)

# --------------------------------------------------
# Main
# --------------------------------------------------

# async def main():
#     server = await websockets.serve(handler, "localhost", 8765)
#     print("WebSocket server running on ws://localhost:8765")

#     await listen_loop()

#     server.close()
#     await server.wait_closed()

# if __name__ == "__main__":
#     asyncio.run(main())





async def delayed_update_display_with_emojis(ws, display, debug):
    await asyncio.sleep(1)
    await send_status(ws, display, debug)



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
    print(msg)

    message_type = msg["type"]

    if message_type == "init":
        print(msg)

        # Send initial message
        await send_status(ws, "\uD83D\uDDE3 " + get_all_emojis_for_action("commercial"), "Ready")

        # Start detection loop
        #asyncio.create_task(demo_loop(ws))
        asyncio.create_task(listen_loop(ws))

    elif message_type == "commercial_state_change":
        is_commercial = msg["data"]["isCommercialState"]
        commercial_state_trigger = msg["data"]["utilities"]["triggerOfLastCommercialStateChange"]

        #TODO: delete this note?
        
        new_display = "\uD83D\uDDE3 " + get_all_emojis_for_action("commercial")

        if is_commercial:
            new_display = "\uD83D\uDDE3 " + get_all_emojis_for_action("content")

        #delayed_update_display_with_emojis(ws, new_display, "update display")
        #await asyncio.sleep(1) #TODO: do this here? can I run this asyncronusly?
        await send_status(ws, new_display, "update display")
        # Note: Commercial state triggers coming from this plugin should be suppressed from comming back around, but the will if two plugins are being used at once
        if commercial_state_trigger != "plugin":
            print("Commercial state changed in extension. is_commercial = ", is_commercial, ", commercial_state_trigger = ", commercial_state_trigger)

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
    #try:
    await ws.send(json.dumps({
        "type": "commercial_state_change",
        "timestamp": time.time(),
        "data": {
            "isCommercial": is_commercial
        },
        "meta": {
            "display": display,
            "debug": debug
        }
    }))
    #except websockets.exceptions.ConnectionClosed:
    #    print("send_commercial_state_change stopped: client disconnected")

# This can be used to disable or enable any auto commercial detection that the browser extension is doing
async def send_auto_commercial_blocked_state_change(ws, is_auto_commercial_blocked, display, debug):
    try:
        await ws.send(json.dumps({
            "type": "auto_commercial_blocked_state_change",
            "timestamp": time.time(),
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
        print("send_status send stopped: client disconnected")

async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"Server running on ws://localhost:{PORT}")
        await asyncio.Future()

asyncio.run(main())
