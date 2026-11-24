"""Application entry point."""
from __future__ import annotations

import hashlib
import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .storage import DATA_DIR
from .ui.icon import app_icon, ico_file
from .ui.main_window import MainWindow
from .ui.style import STYLESHEET

# One GameKeeper per data folder: a second launch just brings the first one back.
SERVER_NAME = "GameKeeper-" + hashlib.sha1(str(DATA_DIR.resolve()).encode()).hexdigest()[:12]


def _already_running() -> bool:
    """If GameKeeper is already running, ask it to show its window and return True."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(500):
        sock.write(b"show\n")
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return True
    return False


def _listen(win: MainWindow) -> QLocalServer:
    server = QLocalServer(win)
    QLocalServer.removeServer(SERVER_NAME)    # clean up after a crash
    server.listen(SERVER_NAME)

    def on_connect():
        conn = server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(lambda: (conn.readAll(), win.bring_to_front()))
    server.newConnection.connect(on_connect)
    return server


def run() -> int:
    if sys.platform == "win32":
        # show our own icon in the taskbar instead of Python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GameKeeper.Launcher")
    app = QApplication(sys.argv)
    app.setApplicationName("GameKeeper")
    if _already_running():
        return 0
    app.setQuitOnLastWindowClosed(False)    # closing the window can keep it in the tray
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())
    win = MainWindow()
    win._server = _listen(win)
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
