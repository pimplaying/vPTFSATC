"""
Main entry point for the ATC client.

Flow: LoginDialog -> MainWindow (departures/arrivals boards + radar tab,
all backed by the shared server via a background-thread poller so the UI
never blocks on network calls).
"""

import sys
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QTabWidget,
    QHeaderView, QMenu, QMessageBox, QInputDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

import api_client
from login_dialog import LoginDialog
from audio_settings_dialog import AudioSettingsDialog
from flightplan_dialog import FlightPlanDialog
from radar_widget import RadarWidget
from network_worker import NetworkWorker
from radio_audio import RadioAudioWorker
from radio_widget import PushToTalkKeyFilter, RadioPanel

COLUMNS = [
    ("callsign", "Callsign"),
    ("aircraft_type", "Type"),
    ("departure", "Dep"),
    ("arrival", "Arr"),
    ("altitude", "Alt"),
    ("squawk", "Squawk"),
    ("runway", "Rwy"),
    ("gate", "Gate"),
    ("heading", "Hdg"),
    ("status", "Status"),
    ("remarks", "Remarks"),
]

DEPARTURE_STATUSES = {"Filed", "Departed"}
ARRIVAL_STATUSES = {"Enroute", "Arrived"}


class FlightTable(QTableWidget):
    def __init__(self, on_edit, on_delete, on_quick_assign):
        super().__init__()
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_quick_assign = on_quick_assign

        self.setColumnCount(len(COLUMNS))
        self.setHorizontalHeaderLabels([label for _, label in COLUMNS])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.cellDoubleClicked.connect(self._handle_double_click)

    def populate(self, plans: list):
        self.setRowCount(len(plans))
        for row, plan in enumerate(plans):
            for col, (key, _label) in enumerate(COLUMNS):
                item = QTableWidgetItem(str(plan.get(key, "") or ""))
                item.setData(Qt.ItemDataRole.UserRole, plan)
                self.setItem(row, col, item)

    def _plan_at_row(self, row):
        item = self.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _handle_double_click(self, row, _col):
        plan = self._plan_at_row(row)
        if plan:
            self.on_edit(plan)

    def _show_context_menu(self, pos):
        row = self.rowAt(pos.y())
        if row < 0:
            return
        plan = self._plan_at_row(row)
        if plan is None:
            return

        menu = QMenu(self)
        menu.addAction("Edit flight plan", lambda: self.on_edit(plan))
        menu.addSeparator()
        menu.addAction("Assign runway", lambda: self.on_quick_assign(plan, "runway", "Runway"))
        menu.addAction("Assign gate", lambda: self.on_quick_assign(plan, "gate", "Gate"))
        menu.addAction("Assign heading", lambda: self.on_quick_assign(plan, "heading", "Heading"))
        menu.addSeparator()
        for status in ["Filed", "Departed", "Enroute", "Arrived", "Cancelled"]:
            menu.addAction(f"Mark as {status}", lambda s=status: self._set_status(plan, s))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self.on_delete(plan))
        menu.exec(self.mapToGlobal(pos))

    def _set_status(self, plan, status):
        api_client.update_flightplan(plan["id"], {"status": status})


class MainWindow(QMainWindow):
    def __init__(self, username: str):
        super().__init__()
        self.username = username
        self.setWindowTitle(f"ATC Client - logged in as {username}")
        self.resize(1050, 600)

        self._build_ui()

        self.worker = NetworkWorker(self.username)
        self.worker.flightplans_updated.connect(self._on_flightplans_updated)
        self.worker.positions_updated.connect(self._on_positions_updated)
        self.worker.connection_error.connect(self._on_connection_error)
        self.worker.station_status.connect(self.radio_panel.set_station_status)
        self.worker.start()

        self.radio_worker = None
        self.radio_panel.station_changed.connect(self._on_station_changed)
        self.radio_panel.transmit_changed.connect(self._on_transmit_changed)
        self.ptt_key_filter = PushToTalkKeyFilter(self.radio_panel, self)
        QApplication.instance().installEventFilter(self.ptt_key_filter)
        QApplication.instance().applicationStateChanged.connect(
            self.ptt_key_filter.release_key
        )

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel(f"Logged in as: {self.username}"))
        top_bar.addStretch(1)

        new_plan_btn = QPushButton("New Flight Plan")
        new_plan_btn.setObjectName("connectButton")
        new_plan_btn.clicked.connect(self.new_flight_plan)
        top_bar.addWidget(new_plan_btn)

        audio_btn = QPushButton("Audio Settings")
        audio_btn.clicked.connect(self.open_audio_settings)
        top_bar.addWidget(audio_btn)

        root.addLayout(top_bar)

        self.tabs = QTabWidget()

        self.departures_table = FlightTable(self.edit_plan, self.delete_plan, self.quick_assign)
        self.tabs.addTab(self.departures_table, "Departures")

        self.arrivals_table = FlightTable(self.edit_plan, self.delete_plan, self.quick_assign)
        self.tabs.addTab(self.arrivals_table, "Arrivals")

        self.all_table = FlightTable(self.edit_plan, self.delete_plan, self.quick_assign)
        self.tabs.addTab(self.all_table, "All Flight Plans")

        self.radar_widget = RadarWidget()
        self.tabs.addTab(self.radar_widget, "Radar")

        self.radio_panel = RadioPanel(self.username)
        self.tabs.addTab(self.radio_panel, "Radio")

        root.addWidget(self.tabs, stretch=1)

    # ---------- Background worker callbacks (run on the UI thread via signals) ----------

    def _on_flightplans_updated(self, plans: list):
        departures = [p for p in plans if p.get("status") in DEPARTURE_STATUSES]
        arrivals = [p for p in plans if p.get("status") in ARRIVAL_STATUSES]
        self.departures_table.populate(departures)
        self.arrivals_table.populate(arrivals)
        self.all_table.populate(plans)

    def _on_positions_updated(self, positions: list):
        self.radar_widget.update_positions(positions)

    def _on_connection_error(self, message: str):
        self.setWindowTitle(f"ATC Client - {message}")

    # ---------- User actions ----------

    def new_flight_plan(self):
        dialog = FlightPlanDialog(self)
        dialog.exec()

    def edit_plan(self, plan: dict):
        dialog = FlightPlanDialog(self, plan=plan)
        dialog.exec()

    def delete_plan(self, plan: dict):
        confirm = QMessageBox.question(
            self, "Delete flight plan",
            f"Delete flight plan for {plan.get('callsign', '')}?"
        )
        if confirm == QMessageBox.StandardButton.Yes:
            api_client.delete_flightplan(plan["id"])

    def quick_assign(self, plan: dict, field: str, label: str):
        current = plan.get(field, "") or ""
        value, ok = QInputDialog.getText(self, f"Assign {label}", f"{label}:", text=current)
        if ok:
            api_client.update_flightplan(plan["id"], {field: value.strip().upper()})

    def open_audio_settings(self):
        AudioSettingsDialog(self).exec()

    def _on_station_changed(self, station):
        if station is None:
            self.worker.set_station(None)
            if self.radio_worker is not None:
                self.radio_worker.stop()
                self.radio_worker.wait(2000)
                self.radio_worker = None
            return

        self.worker.set_station(station)
        self.radio_worker = RadioAudioWorker(
            station["frequency"], self.username
        )
        self.radio_worker.status_changed.connect(self.radio_panel.set_status)
        self.radio_worker.error.connect(self.radio_panel.set_status)
        self.radio_worker.start()

    def _on_transmit_changed(self, active):
        if self.radio_worker is not None:
            self.radio_worker.set_transmitting(active)

    def closeEvent(self, event):
        QApplication.instance().removeEventFilter(self.ptt_key_filter)
        if self.radio_worker is not None:
            self.radio_worker.stop()
            self.radio_worker.wait(2000)
        self.worker.stop()
        self.worker.wait(8000)
        event.accept()


def resource_path(filename: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


def main():
    app = QApplication(sys.argv)

    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    style_path = resource_path("style.qss")
    if os.path.exists(style_path):
        with open(style_path) as f:
            app.setStyleSheet(f.read())

    login = LoginDialog()
    if login.exec():
        window = MainWindow(login.username)
        if os.path.exists(icon_path):
            window.setWindowIcon(QIcon(icon_path))
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
