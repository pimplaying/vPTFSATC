"""
Create or edit a flight plan / strip. Covers all the fields a controller
needs to manage: route info, altitude, squawk, runway, gate, assigned
heading, status, and remarks.
"""

from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox, QTextEdit,
    QHBoxLayout, QPushButton, QMessageBox,
)

import api_client

STATUS_OPTIONS = ["Filed", "Departed", "Enroute", "Arrived", "Cancelled"]


class FlightPlanDialog(QDialog):
    def __init__(self, parent=None, plan: dict = None):
        """
        plan: existing flight plan dict to edit, or None to create a new one.
        """
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Edit Flight Plan" if plan else "New Flight Plan")
        self.setFixedWidth(380)

        form = QFormLayout(self)

        self.callsign_input = QLineEdit(plan.get("callsign", "") if plan else "")
        form.addRow("Callsign:", self.callsign_input)

        self.aircraft_input = QLineEdit(plan.get("aircraft_type", "") if plan else "")
        form.addRow("Aircraft (ICAO):", self.aircraft_input)

        self.departure_input = QLineEdit(plan.get("departure", "") if plan else "")
        form.addRow("Departure:", self.departure_input)

        self.arrival_input = QLineEdit(plan.get("arrival", "") if plan else "")
        form.addRow("Arrival:", self.arrival_input)

        self.route_input = QLineEdit(plan.get("route", "") if plan else "")
        form.addRow("Route:", self.route_input)

        self.altitude_input = QLineEdit(plan.get("altitude", "") if plan else "")
        form.addRow("Altitude:", self.altitude_input)

        self.squawk_input = QLineEdit(plan.get("squawk", "") if plan else "")
        form.addRow("Squawk:", self.squawk_input)

        self.runway_input = QLineEdit(plan.get("runway", "") if plan else "")
        form.addRow("Runway:", self.runway_input)

        self.gate_input = QLineEdit(plan.get("gate", "") if plan else "")
        form.addRow("Gate:", self.gate_input)

        self.heading_input = QLineEdit(plan.get("heading", "") if plan else "")
        form.addRow("Assigned heading:", self.heading_input)

        self.status_combo = QComboBox()
        self.status_combo.addItems(STATUS_OPTIONS)
        if plan and plan.get("status") in STATUS_OPTIONS:
            self.status_combo.setCurrentText(plan["status"])
        form.addRow("Status:", self.status_combo)

        self.remarks_input = QTextEdit(plan.get("remarks", "") if plan else "")
        self.remarks_input.setFixedHeight(60)
        form.addRow("Remarks:", self.remarks_input)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("connectButton")
        save_btn.clicked.connect(self.save_plan)
        btn_row.addWidget(save_btn)

        form.addRow(btn_row)

    def _collect(self) -> dict:
        return {
            "callsign": self.callsign_input.text().strip().upper(),
            "aircraft_type": self.aircraft_input.text().strip().upper(),
            "departure": self.departure_input.text().strip().upper(),
            "arrival": self.arrival_input.text().strip().upper(),
            "route": self.route_input.text().strip(),
            "altitude": self.altitude_input.text().strip(),
            "squawk": self.squawk_input.text().strip(),
            "runway": self.runway_input.text().strip().upper(),
            "gate": self.gate_input.text().strip().upper(),
            "heading": self.heading_input.text().strip(),
            "status": self.status_combo.currentText(),
            "remarks": self.remarks_input.toPlainText().strip(),
        }

    def save_plan(self):
        data = self._collect()
        if not data["callsign"]:
            QMessageBox.warning(self, "Missing callsign", "A callsign is required.")
            return

        if self.plan:
            ok, result = api_client.update_flightplan(self.plan["id"], data)
        else:
            ok, result = api_client.create_flightplan(data)

        if ok:
            self.accept()
        else:
            QMessageBox.warning(self, "Save failed", str(result))
