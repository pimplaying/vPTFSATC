"""
Polls the ATC server on a background thread and emits Qt signals with the
results. This is what fixes the earlier laggy feel — the old code made
blocking HTTP requests directly on the UI thread every refresh tick, which
stalls the whole window on any network hiccup.
"""

import time
import threading

from PyQt6.QtCore import QThread, pyqtSignal

import api_client

FLIGHTPLAN_POLL_SECONDS = 5
POSITION_POLL_SECONDS = 2


class NetworkWorker(QThread):
    flightplans_updated = pyqtSignal(list)
    positions_updated = pyqtSignal(list)
    connection_error = pyqtSignal(str)
    station_status = pyqtSignal(str)

    def __init__(self, username: str):
        super().__init__()
        self.username = username
        self._running = False
        self._stop_event = threading.Event()
        self._station_lock = threading.Lock()
        self._station = None
        self._station_dirty = False
        self._station_published = False
        self._last_station_update = 0.0

    def set_station(self, station):
        with self._station_lock:
            self._station = dict(station) if station else None
            self._station_dirty = True

    def run(self):
        self._running = True
        last_flightplan_poll = 0.0
        last_position_poll = 0.0

        while self._running:
            now = time.time()

            if now - last_flightplan_poll >= FLIGHTPLAN_POLL_SECONDS:
                ok, result = api_client.list_flightplans()
                if ok:
                    self.flightplans_updated.emit(result)
                else:
                    self.connection_error.emit(str(result))
                last_flightplan_poll = now

            if now - last_position_poll >= POSITION_POLL_SECONDS:
                ok, result = api_client.list_positions()
                if ok:
                    self.positions_updated.emit(result)
                else:
                    self.connection_error.emit(str(result))
                last_position_poll = now

            with self._station_lock:
                station = dict(self._station) if self._station else None
                station_dirty = self._station_dirty
                self._station_dirty = False

            if station_dirty or (
                station and now - self._last_station_update >= 10
            ):
                if station:
                    station["username"] = self.username
                    ok, result = api_client.publish_controller(station)
                    self._station_published = ok
                    self._last_station_update = now
                    self.station_status.emit(
                        "ATC position shared" if ok else str(result)
                    )
                elif self._station_published:
                    api_client.release_controller(self.username)
                    self._station_published = False

            self._stop_event.wait(POSITION_POLL_SECONDS)

        if self._station_published:
            api_client.release_controller(self.username)

    def stop(self):
        self._running = False
        self._stop_event.set()
