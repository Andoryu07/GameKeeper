"""GameKeeper's icon, drawn in code so no image files need to ship.

A gold trophy on a blue shield, on a dark tile. Small sizes drop the fine
detail so the icon stays readable in taskbars and file lists.
"""
from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
)

from ..storage import DATA_DIR

# Bump the version whenever the design changes: Windows caches shortcut icons
# by file path, so a new name is what makes it show the new design.
ICON_VERSION = 2
ICO_FILE = DATA_DIR / f"gamekeeper-v{ICON_VERSION}.ico"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _shield(s: float) -> QPainterPath:
    p = QPainterPath()
    p.moveTo(s * 0.50, s * 0.13)
    p.cubicTo(s * 0.62, s * 0.20, s * 0.74, s * 0.22, s * 0.84, s * 0.22)
    p.cubicTo(s * 0.85, s * 0.52, s * 0.76, s * 0.74, s * 0.50, s * 0.89)
    p.cubicTo(s * 0.24, s * 0.74, s * 0.15, s * 0.52, s * 0.16, s * 0.22)
    p.cubicTo(s * 0.26, s * 0.22, s * 0.38, s * 0.20, s * 0.50, s * 0.13)
    p.closeSubpath()
    return p


def _trophy(s: float) -> QPainterPath:
    cup = QPainterPath()
    # bowl
    cup.moveTo(s * 0.37, s * 0.31)
    cup.lineTo(s * 0.63, s * 0.31)
    cup.cubicTo(s * 0.63, s * 0.47, s * 0.58, s * 0.55, s * 0.50, s * 0.56)
    cup.cubicTo(s * 0.42, s * 0.55, s * 0.37, s * 0.47, s * 0.37, s * 0.31)
    cup.closeSubpath()
    # stem and base
    cup.addRect(QRectF(s * 0.475, s * 0.555, s * 0.05, s * 0.09))
    cup.addRoundedRect(QRectF(s * 0.41, s * 0.64, s * 0.18, s * 0.06), s * 0.015, s * 0.015)
    return cup


def _handles(s: float) -> QPainterPath:
    h = QPainterPath()
    h.addEllipse(QRectF(s * 0.305, s * 0.33, s * 0.11, s * 0.12))
    h.addEllipse(QRectF(s * 0.585, s * 0.33, s * 0.11, s * 0.12))
    return h


def app_pixmap(size: int = 256) -> QPixmap:
    s = float(size)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    detailed = size >= 40

    # tile
    m = s * 0.04
    tile = QRectF(m, m, s - 2 * m, s - 2 * m)
    bg = QLinearGradient(tile.topLeft(), tile.bottomRight())
    bg.setColorAt(0, QColor("#2a475e"))
    bg.setColorAt(1, QColor("#0e141b"))
    p.setPen(Qt.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(tile, s * 0.2, s * 0.2)
    if detailed:   # soft glow behind the shield
        glow = QRadialGradient(QPointF(s * 0.5, s * 0.42), s * 0.45)
        glow.setColorAt(0, QColor(102, 192, 244, 70))
        glow.setColorAt(1, QColor(102, 192, 244, 0))
        p.setBrush(glow)
        p.drawRoundedRect(tile, s * 0.2, s * 0.2)

    # shield
    shield = _shield(s)
    sg = QLinearGradient(QPointF(0, s * 0.13), QPointF(0, s * 0.89))
    sg.setColorAt(0, QColor("#66c0f4"))
    sg.setColorAt(1, QColor("#1f5f99"))
    p.setBrush(sg)
    p.setPen(QPen(QColor("#a9dcfb"), max(1.0, s * 0.012)) if detailed else Qt.NoPen)
    p.drawPath(shield)
    if detailed:   # darker inner face
        inner = QPainterPath(shield)
        p.save()
        p.translate(s * 0.5, s * 0.5)
        p.scale(0.86, 0.86)
        p.translate(-s * 0.5, -s * 0.5)
        ig = QLinearGradient(QPointF(0, s * 0.15), QPointF(0, s * 0.85))
        ig.setColorAt(0, QColor("#1b3a55"))
        ig.setColorAt(1, QColor("#0f2133"))
        p.setPen(Qt.NoPen)
        p.setBrush(ig)
        p.drawPath(inner)
        p.restore()

    # trophy
    gold = QLinearGradient(QPointF(s * 0.37, s * 0.3), QPointF(s * 0.63, s * 0.7))
    gold.setColorAt(0, QColor("#ffe7a3"))
    gold.setColorAt(0.45, QColor("#f2c14e"))
    gold.setColorAt(1, QColor("#b8862a"))
    if detailed:
        p.setPen(QPen(QColor("#f2c14e"), s * 0.022))
        p.setBrush(Qt.NoBrush)
        p.drawPath(_handles(s))
    p.setPen(Qt.NoPen)
    p.setBrush(gold)
    p.drawPath(_trophy(s))
    if detailed:   # highlight on the bowl
        p.setBrush(QColor(255, 255, 255, 90))
        hl = QPainterPath()
        hl.moveTo(s * 0.40, s * 0.33)
        hl.lineTo(s * 0.45, s * 0.33)
        hl.cubicTo(s * 0.45, s * 0.43, s * 0.47, s * 0.49, s * 0.49, s * 0.53)
        hl.cubicTo(s * 0.43, s * 0.50, s * 0.40, s * 0.43, s * 0.40, s * 0.33)
        p.drawPath(hl)
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in ICO_SIZES:
        icon.addPixmap(app_pixmap(s))
    return icon


def _png_bytes(pm: QPixmap) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    return bytes(data)


def ico_file() -> Path:
    """Write a multi-size .ico (for Windows shortcuts) and return its path.

    Every size is drawn separately, so small icons stay sharp instead of
    being a blurry shrunken copy of the big one.
    """
    images = [(s, _png_bytes(app_pixmap(s))) for s in ICO_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for s, png in images:
        dim = 0 if s >= 256 else s     # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    ICO_FILE.parent.mkdir(parents=True, exist_ok=True)
    ICO_FILE.write_bytes(header + entries + blobs)
    return ICO_FILE
