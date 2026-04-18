
import asyncio
import websockets
import json

PORT = 8766

async def handle_client(ws):
    print("Overlay WS connected")

    try:
        async for message in ws:
            msg = json.loads(message)

            if msg["type"] == "state_change":
                is_commercial = msg["data"]["isCommercial"]

                if is_commercial:
                    print("START overlay")
                else:
                    print("STOP overlay")

    except websockets.exceptions.ConnectionClosed:
        print("Overlay WS disconnected")

async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"Overlay WS running on {PORT}")
        await asyncio.Future()

asyncio.run(main())
