
import asyncio
import websockets
import json
import time

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
    print(msg)

    message_type = msg["type"]

    if message_type == "init":
        print(msg)

        # Optionally send status to present it to user
        # await send_status(ws, "Connected", "Ready")

    elif message_type == "commercial_state_change":
        is_commercial = msg["data"]["isCommercialState"]
        commercial_state_trigger = msg["data"]["utilities"]["triggerOfLastCommercialStateChange"]
        
        print("Commercial state change. is_commercial = ", is_commercial, ", commercial_state_trigger = ", commercial_state_trigger)

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = msg["data"]["isFullscreen"]

        print("Fullscreen state changed on browser. is_fullscreen = ", is_fullscreen)

    elif message_type == "end": #TODO: is this needed or can I go by disconnect?
        print("Extension Stopped")

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
