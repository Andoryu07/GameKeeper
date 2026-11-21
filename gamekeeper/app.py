"""Application entry point."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.icon import app_icon
from .ui.style import STYLESHEET


def run() -> int:
    if sys.platform == "win32":
        # show our own icon in the taskbar instead of Python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GameKeeper.Launcher")
    app = QApplication(sys.argv)
    app.setApplicationName("GameKeeper")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())
    win = MainWindow()
    win.show()
    return app.exec()
