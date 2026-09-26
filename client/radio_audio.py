"""Push-to-talk PCM audio client for the shared radio relay."""

import asyncio
import base64
import json
import queue
import threading
from urllib.parse import urlsplit

from PyQt6.QtCore import QThread, pyqtSignal

import config
from audio_settings_dialog import load_audio_config


SAMPLE_RATE = 16000
FRAME_SAMPLES = 320


def _radio_url():
    server = urlsplit(config.SERVER_URL)
    scheme = "wss" if server.scheme == "https" else "ws"
    base_port = server.port or (443 if server.scheme == "https" else 80)
    radio_port = base_port + 1 if server.port else 5051
    return f"{scheme}://{server.hostname}:{radio_port}"


class RadioAudioWorker(QThread):
    status_changed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, frequency: str, callsign: str):
        super().__init__()
        self.frequency = frequency
        self.callsign = callsign
        self._running = False
        self._transmitting = threading.Event()
        self._outgoing = queue.Queue(maxsize=10)
        self._incoming = queue.Queue(maxsize=25)
        self._loop = None
        self._stop_event = None
        self._stop_requested = threading.Event()

    def set_transmitting(self, active: bool):
        if active:
            self._transmitting.set()
        else:
            self._transmitting.clear()
            self._clear_outgoing()

    def _clear_outgoing(self):
        while True:
            try:
                self._outgoing.get_nowait()
            except queue.Empty:
                break

    def stop(self):
        self._running = False
        self._stop_requested.set()
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)

    def run(self):
        if self._stop_requested.is_set():
            return
        self._running = True
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._stream())
        except Exception as exc:
            if self._running:
                self.error.emit(str(exc))
        finally:
            self._running = False
            self._loop.close()
            self._loop = None
            self.status_changed.emit("Radio disconnected")

    async def _stream(self):
        import sounddevice as sd
        import websockets

        devices = load_audio_config()
        output_stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            channels=1,
            dtype="int16",
            device=devices.get("output_device") or None,
            callback=self._output_callback,
        )
        input_stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            channels=1,
            dtype="int16",
            device=devices.get("input_device") or None,
            callback=self._input_callback,
        )

        try:
            async with websockets.connect(_radio_url(), max_size=4096) as connection:
                await connection.send(json.dumps({
                    "type": "tune",
                    "frequency": self.frequency,
                }))
                output_stream.start()
                input_stream.start()
                self._stop_event = asyncio.Event()
                if self._stop_requested.is_set():
                    self._stop_event.set()
                self.status_changed.emit(f"Radio tuned to {self.frequency}")

                receive_task = asyncio.create_task(
                    self._receive_audio(connection, output_stream)
                )
                send_task = asyncio.create_task(self._send_audio(connection))
                stop_task = asyncio.create_task(self._stop_event.wait())
                tasks = (receive_task, send_task, stop_task)
                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                if stop_task not in done:
                    for task in done:
                        task.result()
                    raise ConnectionError("Radio relay closed the connection")
        finally:
            self._stop_event = None
            for stream in (input_stream, output_stream):
                try:
                    if stream.active:
                        stream.stop()
                    stream.close()
                except Exception:
                    pass

    def _input_callback(self, input_data, _frames, _time_info, _status):
        if not self._transmitting.is_set():
            return
        try:
            self._outgoing.put_nowait(bytes(input_data))
        except queue.Full:
            try:
                self._outgoing.get_nowait()
                self._outgoing.put_nowait(bytes(input_data))
            except queue.Empty:
                pass

    def _output_callback(self, output_data, _frames, _time_info, _status):
        try:
            output_data[:] = self._incoming.get_nowait()
        except queue.Empty:
            output_data[:] = bytes(len(output_data))

    async def _send_audio(self, connection):
        while self._running:
            try:
                frame = self._outgoing.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.005)
                continue
            await connection.send(json.dumps({
                "type": "audio",
                "audio": base64.b64encode(frame).decode("ascii"),
                "callsign": self.callsign,
            }))

    async def _receive_audio(self, connection, output_stream):
        async for raw_message in connection:
            message = json.loads(raw_message)
            if message.get("type") != "audio":
                continue
            frame = base64.b64decode(message.get("audio", ""), validate=True)
            if len(frame) != FRAME_SAMPLES * 2:
                continue
            try:
                self._incoming.put_nowait(frame)
            except queue.Full:
                try:
                    self._incoming.get_nowait()
                    self._incoming.put_nowait(frame)
                except queue.Empty:
                    pass