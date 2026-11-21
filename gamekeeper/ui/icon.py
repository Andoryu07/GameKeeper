"""GameKeeper's icon, drawn in code so no image files need to ship."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap

from ..storage import DATA_DIR

ICO_FILE = DATA_DIR / "gamekeeper.ico"


def app_pixmap(size: int = 256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    m = size * 0.06
    rect = QRectF(m, m, size - 2 * m, size - 2 * m)
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0, QColor("#5b9bff"))
    g.setColorAt(1, QColor("#2f5fd0"))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(rect, size * 0.22, size * 0.22)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPixelSize(int(size * 0.44))
    f.setBold(True)
    p.setFont(f)
    p.drawText(rect, Qt.AlignCenter, "GK")
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_pixmap(s))
    return icon


def ico_file() -> Path:
    """Write the icon as a .ico file (for Windows shortcuts) and return its path."""
    ICO_FILE.parent.mkdir(parents=True, exist_ok=True)
    app_pixmap(256).save(str(ICO_FILE), "ICO")
    return ICO_FILE
