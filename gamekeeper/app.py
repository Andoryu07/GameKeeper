"""Application entry point."""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.style import ACCENT, STYLESHEET


def _icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPixelSize(30)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "GK")
    p.end()
    return QIcon(pm)


def run() -> int:
    if sys.platform == "win32":
        # show our own icon in the taskbar instead of Python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GameKeeper.Launcher")
    app = QApplication(sys.argv)
    app.setApplicationName("GameKeeper")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(_icon())
    win = MainWindow()
    win.show()
    return app.exec()
