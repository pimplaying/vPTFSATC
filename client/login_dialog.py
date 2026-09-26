"""
Login dialog - authenticates via Discord OAuth and checks (server-side)
whether the user holds the required ATC role in your Discord server.
"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import QThread, pyqtSignal

import api_client
import config
from discord_auth import login_with_discord


class _DiscordLoginWorker(QThread):
    finished_ok = pyqtSignal(str)     # username
    finished_error = pyqtSignal(str)  # error message

    def run(self):
        code = login_with_discord(config.DISCORD_CLIENT_ID)
        if not code:
            self.finished_error.emit(
                "Login was cancelled or timed out. Try again."
            )
            return

        ok, result = api_client.discord_login(code)
        if ok:
            self.finished_ok.emit(result.get("username", "unknown"))
        else:
            self.finished_error.emit(str(result))


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ATC Client - Login")
        self.setFixedWidth(360)
        self.username = None
        self.worker = None

        layout = QVBoxLayout(self)

        title = QLabel("Controller Login")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(
            "You need the ATC role in our Discord server to log in. "
            "Clicking below opens Discord in your browser to confirm."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #e36f6f;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.login_btn = QPushButton("Login with Discord")
        self.login_btn.setObjectName("connectButton")
        self.login_btn.clicked.connect(self.start_login)
        layout.addWidget(self.login_btn)

    def start_login(self):
        self.login_btn.setEnabled(False)
        self.status_label.setStyleSheet("color: #8b939b;")
        self.status_label.setText("Opening Discord in your browser...")

        self.worker = _DiscordLoginWorker()
        self.worker.finished_ok.connect(self._on_success)
        self.worker.finished_error.connect(self._on_error)
        self.worker.start()

    def _on_success(self, username: str):
        self.username = username
        self.accept()

    def _on_error(self, message: str):
        self.login_btn.setEnabled(True)
        self.status_label.setStyleSheet("color: #e36f6f;")
        self.status_label.setText(message)
