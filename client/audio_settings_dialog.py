"""
Audio input/output device selection. Saved locally per machine (not synced
to the server - it's a personal hardware setting, not shared ATC data).
"""

import json
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QMessageBox,
)

AUDIO_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "audio_config.json"
)


def _list_devices():
    """
    Returns (input_names, output_names). Uses sounddevice if available;
    falls back to empty lists (with a message) if it's not installed or no
    audio devices are found - the app still works without this.
    """
    try:
        import sounddevice as sd
        devices = sd.query_devices()
    except Exception:
        return [], []

    inputs = [d["name"] for d in devices if d["max_input_channels"] > 0]
    outputs = [d["name"] for d in devices if d["max_output_channels"] > 0]
    return inputs, outputs


def load_audio_config() -> dict:
    if os.path.exists(AUDIO_CONFIG_PATH):
        try:
            with open(AUDIO_CONFIG_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_audio_config(config: dict):
    with open(AUDIO_CONFIG_PATH, "w") as f:
        json.dump(config, f)


class AudioSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Audio Settings")
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)

        input_names, output_names = _list_devices()
        current = load_audio_config()

        if not input_names and not output_names:
            layout.addWidget(QLabel(
                "No audio devices detected (or 'sounddevice' isn't installed).\n"
                "Install it with: pip install sounddevice"
            ))

        layout.addWidget(QLabel("Input device (microphone):"))
        self.input_combo = QComboBox()
        self.input_combo.addItems(input_names)
        if current.get("input_device") in input_names:
            self.input_combo.setCurrentText(current["input_device"])
        layout.addWidget(self.input_combo)

        layout.addWidget(QLabel("Output device (speakers/headset):"))
        self.output_combo = QComboBox()
        self.output_combo.addItems(output_names)
        if current.get("output_device") in output_names:
            self.output_combo.setCurrentText(current["output_device"])
        layout.addWidget(self.output_combo)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("connectButton")
        save_btn.clicked.connect(self.save_settings)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def save_settings(self):
        save_audio_config({
            "input_device": self.input_combo.currentText(),
            "output_device": self.output_combo.currentText(),
        })
        QMessageBox.information(self, "Saved", "Audio settings saved.")
        self.accept()
