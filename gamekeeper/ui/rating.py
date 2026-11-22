"""A clickable 1-10 star rating."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import style


def star_path(cx: float, cy: float, r: float) -> QPainterPath:
    p = QPainterPath()
    for i in range(10):
        rad = r if i % 2 == 0 else r * 0.45
        a = math.radians(-90 + i * 36)
        pt = QPointF(cx + rad * math.cos(a), cy + rad * math.sin(a))
        p.moveTo(pt) if i == 0 else p.lineTo(pt)
    p.closeSubpath()
    return p


def paint_stars(p: QPainter, rect: QRectF, value: int, count: int = 10, gap: float = 3.0,
                empty: str | None = None):
    size = min(rect.height(), (rect.width() - gap * (count - 1)) / count)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    for i in range(count):
        cx = rect.x() + i * (size + gap) + size / 2
        path = star_path(cx, rect.center().y(), size / 2)
        if i < value:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(style.GOLD))
        else:
            p.setPen(QPen(QColor(empty or "#4b5463"), 1.2))
            p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    p.restore()


class StarRating(QWidget):
    changed = Signal(int)

    def __init__(self, star_size: int = 26, parent=None):
        super().__init__(parent)
        self.value = 0
        self._hover = 0
        self.star = star_size
        self.gap = 5
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setToolTip("Click a star to rate. Click the same star again to clear.")

    def sizeHint(self):
        return QSize(self.star * 10 + self.gap * 9 + 2, self.star + 2)

    def set_value(self, v: int):
        self.value = max(0, min(10, v))
        self.update()

    def _star_at(self, x: float) -> int:
        n = int(x // (self.star + self.gap)) + 1
        return max(1, min(10, n))

    def mouseMoveEvent(self, e):
        self._hover = self._star_at(e.position().x())
        self.update()

    def leaveEvent(self, e):
        self._hover = 0
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            n = self._star_at(e.position().x())
            self.value = 0 if n == self.value else n
            self.changed.emit(self.value)
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        paint_stars(p, QRectF(1, 1, self.width() - 2, self.star), self._hover or self.value, gap=self.gap,
                    empty="#6b7682" if self._hover else None)
