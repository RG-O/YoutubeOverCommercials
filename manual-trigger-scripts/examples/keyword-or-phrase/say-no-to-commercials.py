import asyncio
import websockets
import json
import time
import queue
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import os

# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "vosk-model-small-en-us-0.15")

# Phrases to detect
TARGET_PHRASES = {
    "banana": "Thumb_Up",
    "hate commercials": "Thumb_Down"
}

COOLDOWN = 1.0  # seconds between triggers

# --------------------------------------------------
# WebSocket server
# --------------------------------------------------

connected_clients = set()

async def handler(websocket):
    connected_clients.add(websocket)
    print("Extension connected")
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)
        print("Extension disconnected")

async def send_event(event):
    if connected_clients:
        message = json.dumps(event)
        await asyncio.gather(*(ws.send(message) for ws in connected_clients))

# --------------------------------------------------
# Audio setup
# --------------------------------------------------

audio_queue = queue.Queue()

def audio_callback(indata, frames, time_info, status):
    """Called continuously by sounddevice to collect microphone audio"""
    if status:
        print("Audio status:", status)
    audio_queue.put(bytes(indata))

# --------------------------------------------------
# Main voice loop
# --------------------------------------------------

async def listen_loop():
    global last_trigger_time

    if not os.path.exists(MODEL_PATH):
        print("Model not found at:", MODEL_PATH)
        return

    print("Loading Vosk model...")
    model = Model(MODEL_PATH)

    recognizer = KaldiRecognizer(model, 16000)

    print("Listening for voice commands...")

    last_trigger_time = 0

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

            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").lower().strip()

                if text:
                    now = time.time()
                    print(f"Heard: {text}")

                    # Check phrases
                    for phrase, mapped_name in TARGET_PHRASES.items():
                        if phrase in text:
                            if now - last_trigger_time > COOLDOWN:
                                print(f"TRIGGERED: {mapped_name}")

                                await send_event({
                                    "type": "gesture",
                                    "gesture": mapped_name,
                                    "timestamp": now,
                                    "source": "voice"
                                })

                                last_trigger_time = now

            await asyncio.sleep(0)

# --------------------------------------------------
# Main
# --------------------------------------------------

async def main():
    server = await websockets.serve(handler, "localhost", 8765)
    print("WebSocket server running on ws://localhost:8765")

    await listen_loop()

    server.close()
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())