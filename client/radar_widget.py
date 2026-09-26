"""
Draws live aircraft positions fed by the position tracker app (via the
shared server's /positions endpoint).

Positions arrive in the SAME pixel coordinate space as the tracker's
reference map image (src/reference_map.png in the tracker project). If you
copy that exact file to client/reference_map.png here, blips will be drawn
in their correct real position over the actual map. Without it, this falls
back to auto-fitting whatever positions are currently known into the
widget - useful for testing, but not spatially accurate.
"""

import os

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPixmap
from PyQt6.QtCore import Qt, QRectF

REFERENCE_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference_map.png")


class RadarWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.positions = []  # list of dicts: callsign, aircraft_type, x, y, confidence
        self.setMinimumSize(500, 400)

        self.reference_pixmap = None
        if os.path.exists(REFERENCE_MAP_PATH):
            self.reference_pixmap = QPixmap(REFERENCE_MAP_PATH)

    def update_positions(self, positions: list):
        self.positions = positions
        self.update()  # triggers a repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d1014"))

        if not self.positions:
            painter.setPen(QColor("#5a636c"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                              "No live positions yet")
            painter.end()
            return

        if self.reference_pixmap is not None:
            self._paint_with_reference_map(painter)
        else:
            self._paint_auto_fit(painter)

        painter.end()

    def _paint_with_reference_map(self, painter):
        pixmap = self.reference_pixmap
        widget_rect = self.rect()
        scale = min(widget_rect.width() / pixmap.width(),
                    widget_rect.height() / pixmap.height())
        draw_w, draw_h = pixmap.width() * scale, pixmap.height() * scale
        offset_x = (widget_rect.width() - draw_w) / 2
        offset_y = (widget_rect.height() - draw_h) / 2

        painter.drawPixmap(QRectF(offset_x, offset_y, draw_w, draw_h), pixmap,
                            QRectF(0, 0, pixmap.width(), pixmap.height()))

        for pos in self.positions:
            screen_x = offset_x + pos["x"] * scale
            screen_y = offset_y + pos["y"] * scale
            self._draw_blip(painter, screen_x, screen_y, pos)

    def _paint_auto_fit(self, painter):
        xs = [p["x"] for p in self.positions]
        ys = [p["y"] for p in self.positions]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1)
        span_y = max(max_y - min_y, 1)

        margin = 40
        w = self.width() - 2 * margin
        h = self.height() - 2 * margin

        painter.setPen(QColor("#5a636c"))
        painter.drawText(10, 20, "No reference map on this client - showing "
                                  "auto-fit relative positions (not to scale)")

        for pos in self.positions:
            nx = (pos["x"] - min_x) / span_x
            ny = (pos["y"] - min_y) / span_y
            screen_x = margin + nx * w
            screen_y = margin + ny * h
            self._draw_blip(painter, screen_x, screen_y, pos)

    def _draw_blip(self, painter, x, y, pos):
        confidence = pos.get("confidence", 1.0) or 1.0
        color = QColor("#4fd67a") if confidence >= 0.5 else QColor("#e3c34f")

        painter.setPen(QPen(color, 2))
        painter.setBrush(color)
        painter.drawEllipse(int(x) - 5, int(y) - 5, 10, 10)

        painter.setPen(QColor("#d7dde3"))
        painter.setFont(QFont("Consolas", 9))
        label = f"{pos.get('callsign', '')} ({pos.get('aircraft_type', '')})"
        painter.drawText(int(x) + 8, int(y) - 8, label)
