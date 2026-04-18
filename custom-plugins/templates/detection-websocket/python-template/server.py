
import asyncio
import websockets
import json
import time

PORT = 8765

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
    if msg["type"] == "init":
        prefs = msg["data"]["preferences"]
        print("Received preferences")

        # Send initial message
        await send_status(ws, "Connected", "Ready")

        # Start detection loop
        asyncio.create_task(detection_loop(ws))

    elif msg["type"] == "manual_override":
        print("Manual override:", msg["data"]["isCommercial"])

async def detection_loop(ws):
    is_commercial = False

    while True:
        await asyncio.sleep(2)

        # Example toggle logic
        is_commercial = not is_commercial

        await ws.send(json.dumps({
            "type": "state_update",
            "timestamp": time.time(),
            "data": {
                "isCommercial": is_commercial
            },
            "meta": {
                "display": "Commercial" if is_commercial else "Content",
                "debug": "Toggled for demo"
            }
        }))

async def send_status(ws, display, debug):
    await ws.send(json.dumps({
        "type": "status",
        "timestamp": time.time(),
        "data": {},
        "meta": {
            "display": display,
            "debug": debug
        }
    }))

async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"Server running on ws://localhost:{PORT}")
        await asyncio.Future()

asyncio.run(main())
