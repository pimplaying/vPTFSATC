"""ATC station selector and hold-to-talk controls."""

import json
import os
import re

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QRegularExpressionValidator
from PyQt6.QtCore import QRegularExpression
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QKeySequenceEdit,
    QLineEdit, QPlainTextEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)


RADIO_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "radio_config.json"
)
POSITIONS = [
    "Center", "Approach", "Departure", "Tower", "Ground", "Ramp",
    "Clearance Delivery", "ATIS", "Observer",
]


def _load_radio_config():
    try:
        with open(RADIO_CONFIG_PATH, encoding="utf-8") as settings_file:
            data = json.load(settings_file)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class PushToTalkMouseFilter(QObject):
    def __init__(self, button, on_transmit, parent=None):
        super().__init__(parent)
        self.button = button
        self.on_transmit = on_transmit
        self._mouse_down = False

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.Type.MouseButtonPress
                and watched is self.button
                and event.button() == Qt.MouseButton.LeftButton):
            self._mouse_down = True
            self.on_transmit(True)
        elif (event.type() == QEvent.Type.MouseButtonRelease
              and self._mouse_down
              and event.button() == Qt.MouseButton.LeftButton):
            self._mouse_down = False
            self.on_transmit(False)
        return False


class RadioPanel(QWidget):
    station_changed = pyqtSignal(object)
    transmit_changed = pyqtSignal(bool)

    def __init__(self, username: str, parent=None):
        super().__init__(parent)
        self.username = username
        self.station_active = False
        self.transmitting = False
        self._button_transmitting = False
        self._key_transmitting = False
        saved = _load_radio_config()

        layout = QVBoxLayout(self)
        fields = QHBoxLayout()
        fields.addWidget(QLabel("Island"))
        self.island_combo = QComboBox()
        self.island_combo.setEditable(True)
        self.island_combo.addItems(["Mainland", "Peril Islands"])
        self.island_combo.setCurrentText(saved.get("island", "Mainland"))
        fields.addWidget(self.island_combo)

        fields.addWidget(QLabel("Position"))
        self.position_combo = QComboBox()
        self.position_combo.addItems(POSITIONS)
        self.position_combo.setCurrentText(saved.get("position", "Center"))
        fields.addWidget(self.position_combo)

        fields.addWidget(QLabel("Frequency"))
        self.frequency_input = QLineEdit(saved.get("frequency", ""))
        self.frequency_input.setPlaceholderText("123.450")
        self.frequency_input.setFixedWidth(86)
        self.frequency_input.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"\d{0,3}(\.\d{0,3})?"), self.frequency_input
        ))
        fields.addWidget(self.frequency_input)

        self.station_button = QPushButton("Take Position")
        self.station_button.setCheckable(True)
        self.station_button.toggled.connect(self._toggle_station)
        fields.addWidget(self.station_button)
        layout.addLayout(fields)

        radio_row = QHBoxLayout()
        self.ptt_button = QPushButton("PTT")
        self.ptt_button.setObjectName("connectButton")
        self.ptt_button.setToolTip("Hold to transmit on the selected frequency")
        self.ptt_button.setEnabled(False)
        self._mouse_ptt_filter = PushToTalkMouseFilter(
            self.ptt_button, self.set_button_transmitting, self
        )
        QApplication.instance().installEventFilter(self._mouse_ptt_filter)
        radio_row.addWidget(self.ptt_button)

        radio_row.addWidget(QLabel("PTT key"))
        self.key_binding = QKeySequenceEdit(
            QKeySequence(saved.get("ptt_key", "V"))
        )
        self.key_binding.setToolTip("Press a key or key combination to bind PTT")
        self.key_binding.setMaximumWidth(150)
        radio_row.addWidget(self.key_binding)

        self.status_label = QLabel("No ATC position selected")
        self.status_label.setObjectName("statusLabel")
        radio_row.addWidget(self.status_label, stretch=1)
        layout.addLayout(radio_row)

        for widget in (self.island_combo, self.position_combo,
                       self.frequency_input, self.key_binding):
            signal = getattr(widget, "currentTextChanged", None)
            if signal is not None:
                signal.connect(self._save_settings)
        self.frequency_input.textChanged.connect(self._save_settings)
        self.key_binding.keySequenceChanged.connect(self._save_settings)

    def _save_settings(self, *_args):
        data = {
            "island": self.island_combo.currentText().strip(),
            "position": self.position_combo.currentText(),
            "frequency": self.frequency_input.text().strip(),
            "ptt_key": self.key_binding.keySequence().toString(
                QKeySequence.SequenceFormat.PortableText
            ),
        }
        with open(RADIO_CONFIG_PATH, "w", encoding="utf-8") as settings_file:
            json.dump(data, settings_file, indent=2)

    def _toggle_station(self, active):
        if active:
            island = self.island_combo.currentText().strip()
            frequency = self.frequency_input.text().strip()
            if (not island or not re.fullmatch(r"\d{3}\.\d{3}", frequency)):
                self.station_button.setChecked(False)
                self.status_label.setText("Enter an island and frequency (123.450)")
                return
            self.station_active = True
            self.station_button.setText("Release Position")
            self.island_combo.setEnabled(False)
            self.position_combo.setEnabled(False)
            self.frequency_input.setEnabled(False)
            self.ptt_button.setEnabled(True)
            self.status_label.setText("Connecting radio...")
            self._save_settings()
            self.station_changed.emit({
                "island": island,
                "position": self.position_combo.currentText(),
                "frequency": frequency,
            })
            return

        self.station_active = False
        self.set_button_transmitting(False)
        self.set_key_transmitting(False)
        self.station_button.setText("Take Position")
        self.island_combo.setEnabled(True)
        self.position_combo.setEnabled(True)
        self.frequency_input.setEnabled(True)
        self.ptt_button.setEnabled(False)
        self.status_label.setText("No ATC position selected")
        self.station_changed.emit(None)

    def set_button_transmitting(self, active):
        self._button_transmitting = bool(active and self.station_active)
        self._update_transmitting()

    def set_key_transmitting(self, active):
        self._key_transmitting = bool(active and self.station_active)
        self._update_transmitting()

    def _update_transmitting(self):
        active = self.station_active and (
            self._button_transmitting or self._key_transmitting
        )
        if active == self.transmitting:
            self.ptt_button.setDown(active)
            return
        self.transmitting = active
        self.ptt_button.setDown(active)
        self.status_label.setText(
            "TRANSMITTING" if active else f"Tuned to {self.frequency_input.text()}"
        )
        self.transmit_changed.emit(active)

    def set_status(self, message: str):
        if not self.transmitting:
            self.status_label.setText(message)

    def set_station_status(self, message: str):
        self.set_status(message)


class PushToTalkKeyFilter(QObject):
    def __init__(self, radio_panel: RadioPanel, parent=None):
        super().__init__(parent)
        self.radio_panel = radio_panel
        self._key_down = False
        self._pressed_key = None

    def eventFilter(self, watched, event):
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False

        if event.isAutoRepeat():
            return self._key_down and event.key() == self._pressed_key
        if (event.type() == QEvent.Type.KeyRelease and self._key_down
                and event.key() == self._pressed_key):
            self.release_key()
            return True

        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit,
                      QKeySequenceEdit)):
            return False

        binding = self.radio_panel.key_binding.keySequence()
        if not binding or len(binding) != 1:
            return False
        pressed_sequence = QKeySequence(
            int(event.key()) | event.modifiers().value
        )
        if pressed_sequence != binding:
            return False

        self._key_down = True
        self._pressed_key = event.key()
        self.radio_panel.set_key_transmitting(
            event.type() == QEvent.Type.KeyPress
        )
        return True

    def release_key(self, *_args):
        if self._key_down:
            self._key_down = False
            self._pressed_key = None
            self.radio_panel.set_key_transmitting(False)