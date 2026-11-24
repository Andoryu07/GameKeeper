"""Application entry point."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.icon import app_icon, ico_file
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
    if sys.platform == "win32":
        # write the current icon and move existing shortcuts onto it, in the background
        import threading
        from . import shortcut

        def refresh_shortcuts():
            try:
                shortcut.update_existing(ico_file())
            except OSError:
                pass
        threading.Thread(target=refresh_shortcuts, daemon=True).start()
    return app.exec()
