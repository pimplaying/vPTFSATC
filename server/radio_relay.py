"""Frequency-isolated PCM relay for the tracker and ATC desktop clients."""

import asyncio
import json
import threading

import websockets


def start_radio_server(host="0.0.0.0", port=5051):
    channels = {}

    async def handle_connection(websocket, _path=None):
        channels[websocket] = None
        try:
            async for raw_message in websocket:
                try:
                    message = json.loads(raw_message)
                except (TypeError, json.JSONDecodeError):
                    continue

                if message.get("type") == "tune":
                    channels[websocket] = str(message.get("frequency", "")).strip()
                    await websocket.send(json.dumps({"type": "ready"}))
                    continue

                if message.get("type") != "audio" or not channels[websocket]:
                    continue

                audio = message.get("audio")
                if not isinstance(audio, str) or len(audio) > 2048:
                    continue

                packet = json.dumps({
                    "type": "audio",
                    "audio": audio,
                    "callsign": str(message.get("callsign", ""))[:32],
                })
                peers = [peer for peer, frequency in channels.items()
                         if peer is not websocket and frequency == channels[websocket]]
                if peers:
                    await asyncio.gather(
                        *(peer.send(packet) for peer in peers),
                        return_exceptions=True,
                    )
        finally:
            channels.pop(websocket, None)

    async def serve():
        async with websockets.serve(
            handle_connection,
            host,
            port,
            max_size=4096,
            ping_interval=20,
            ping_timeout=20,
        ):
            print(f"Radio relay listening on ws://{host}:{port}")
            await asyncio.Future()

    def run():
        asyncio.run(serve())

    thread = threading.Thread(target=run, name="radio-relay", daemon=True)
    thread.start()
    return thread