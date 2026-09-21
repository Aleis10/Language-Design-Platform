
import os
from PySide6.QtWidgets import QToolButton, QWidget
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QPainter, QColor, QPixmap, QPen, QBrush

def _keyboard_icon(size: int = 28) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor("#007acc"), max(2, size * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    w = int(size * 0.76)
    h = int(size * 0.5)
    x0 = int((size - w) / 2.0)
    y0 = int((size - h) / 2.0)
    p.drawRoundedRect(x0, y0, w, h, int(size * 0.08), int(size * 0.08))
    dot = max(1, int(size * 0.045))
    p.setBrush(QBrush(QColor("#007acc")))
    p.setPen(Qt.PenStyle.NoPen)
    for row in range(2):
        for col in range(4):
            dx = x0 + int(w * (0.14 + col * 0.24))
            dy = y0 + int(h * (0.28 + row * 0.44))
            p.drawEllipse(dx - dot // 2, dy - dot // 2, dot, dot)
    p.end()
    return QIcon(pm)

class FloatingKeyboardButton(QToolButton):

    toggled_on = Signal()

    def __init__(self, parent: QWidget = None, diameter: int = 52):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self.setIcon(_keyboard_icon(int(diameter * 0.56)))
        self.setIconSize(QSize(int(diameter * 0.56), int(diameter * 0.56)))
        self.setToolTip("Activate Digital Keyboard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self._update_style()
        self.toggled.connect(self._on_toggled)

    def _update_style(self):
        on = self.isChecked()
        self.setStyleSheet(
            f"""
            QToolButton {{
                background-color: {"#007acc" if on else "#ffffff"};
                border: {(2 if on else 1)}px solid {"#007acc" if on else "#b0b0b0"};
                border-radius: {self.width() // 2}px;
            }}
            QToolButton:hover {{
                background-color: {"#2196f3" if on else "#eef4fd"};
                border: 1px solid {"#007acc" if on else "#007acc"};
            }}
            """
        )

    def _on_toggled(self, checked: bool):
        self._update_style()
        if checked:
            self.toggled_on.emit()