"""The cover grid of games."""
from __future__ import annotations

import hashlib

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QImageReader, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate

from ..runner import format_playtime
from ..storage import Game
from . import style

ROLE_GAME = Qt.UserRole + 1
DEFAULT_COVER_W = 160

_cache: dict[str, QPixmap] = {}


def cover_pixmap(game: Game, w: int = DEFAULT_COVER_W, h: int | None = None) -> QPixmap:
    h = h or int(w * 1.5)
    path = game.cover_path
    try:
        stamp = path.stat().st_mtime if path.exists() else 0
    except OSError:
        stamp = 0
    key = f"{game.id}:{stamp}:{w}x{h}"
    if key in _cache:
        return _cache[key]
    pm = _load_scaled(str(path), w, h) if stamp else QPixmap()
    pm = _fit(pm, w, h) if not pm.isNull() else placeholder(game.name, w, h)
    _cache[key] = pm
    return pm


def _load_scaled(path: str, w: int, h: int) -> QPixmap:
    """Decode the image straight at (about) the size it's shown at. Much faster
    than loading the full image and shrinking it afterwards."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() > w * 2:
        size.scale(w * 2, h * 2, Qt.KeepAspectRatioByExpanding)   # 2x for sharp high-DPI screens
        reader.setScaledSize(size)
    img = reader.read()
    return QPixmap.fromImage(img) if not img.isNull() else QPixmap()


def _fit(pm: QPixmap, w: int, h: int) -> QPixmap:
    pm = pm.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x, y = (pm.width() - w) // 2, (pm.height() - h) // 2
    return pm.copy(x, y, w, h)


def placeholder(name: str, w: int, h: int) -> QPixmap:
    """Generated cover for games without artwork."""
    hue = int(hashlib.md5(name.encode()).hexdigest()[:4], 16) % 360
    pm = QPixmap(w, h)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor.fromHsl(hue, 90, 70))
    g.setColorAt(1, QColor.fromHsl((hue + 40) % 360, 80, 30))
    p.fillRect(0, 0, w, h, g)
    p.setPen(QColor(255, 255, 255, 230))
    f = QFont()
    f.setPixelSize(max(14, w // 9))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRect(10, 10, w - 20, h - 20), Qt.AlignCenter | Qt.TextWordWrap, name)
    p.end()
    return pm


class GameDelegate(QStyledItemDelegate):
    def __init__(self, view: "LibraryView"):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index):
        return QSize(self.view.cover_w + 16, self.view.cover_h + 62)

    def paint(self, p: QPainter, option, index):
        game: Game = index.data(ROLE_GAME)
        if game is None:
            return
        COVER_W, COVER_H = self.view.cover_w, self.view.cover_h
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect
        x = r.x() + (r.width() - COVER_W) // 2
        cover = QRect(x, r.y() + 6, COVER_W, COVER_H)
        hovered = option.state & QStyle.State_MouseOver
        selected = option.state & QStyle.State_Selected

        path = QPainterPath()
        path.addRoundedRect(cover, 8, 8)
        p.setClipPath(path)
        p.drawPixmap(cover, cover_pixmap(game, COVER_W, COVER_H))
        if game.id in self.view.running:
            p.fillRect(QRect(cover.x(), cover.y(), COVER_W, 26), QColor(63, 191, 127, 225))
            f = p.font()
            f.setPixelSize(11)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(QRect(cover.x(), cover.y(), COVER_W, 26), Qt.AlignCenter, "●  PLAYING")
        if hovered:
            p.fillRect(cover, QColor(255, 255, 255, 22))
        p.setClipping(False)
        if selected or hovered:
            p.setPen(QPen(QColor(style.ACCENT if selected else "#5d6b82"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(cover.adjusted(-1, -1, 1, 1), 9, 9)

        # achievement badge
        if game.achievements_total:
            done = game.achievements_unlocked == game.achievements_total
            txt = "★ 100%" if done else f"{game.achievements_unlocked}/{game.achievements_total}"
            f = p.font()
            f.setPixelSize(11)
            f.setBold(True)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(txt) + 12
            badge = QRect(cover.right() - tw - 6, cover.bottom() - 26, tw, 20)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(style.GOLD) if done else QColor(0, 0, 0, 170))
            p.drawRoundedRect(badge, 10, 10)
            p.setPen(QColor("#1a1a1a") if done else QColor("white"))
            p.drawText(badge, Qt.AlignCenter, txt)

        if game.favorite:
            f = p.font()
            f.setPixelSize(16)
            p.setFont(f)
            p.setPen(QColor(style.GOLD))
            top = cover.y() + (30 if game.id in self.view.running else 6)
            p.drawText(QRect(cover.x() + 8, top, 24, 24), Qt.AlignCenter, "★")

        # title + playtime
        f = p.font()
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(style.TEXT))
        title_r = QRect(cover.x(), cover.bottom() + 8, COVER_W, 18)
        p.drawText(title_r, Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(game.name, Qt.ElideRight, COVER_W))
        f.setBold(False)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(style.MUTED))
        p.drawText(QRect(cover.x(), title_r.bottom() + 2, COVER_W, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   format_playtime(game.total_playtime))
        p.restore()


class LibraryView(QListView):
    open_game = Signal(str)
    context_requested = Signal(str, object)   # game id, global pos

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Grid")
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(10)
        self.setMouseTracking(True)
        self.setSelectionMode(QListView.SingleSelection)
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cover_w, self.cover_h = DEFAULT_COVER_W, int(DEFAULT_COVER_W * 1.5)
        self.running: set[str] = set()
        self.model_ = QStandardItemModel(self)
        self.setModel(self.model_)
        self.setItemDelegate(GameDelegate(self))
        self.doubleClicked.connect(lambda idx: self.open_game.emit(idx.data(ROLE_GAME).id))
        self.clicked.connect(lambda idx: self.open_game.emit(idx.data(ROLE_GAME).id))
        self.setCursor(Qt.PointingHandCursor)
        self.customContextMenuRequested.connect(self._ctx)

    def set_cover_size(self, w: int):
        self.cover_w, self.cover_h = w, int(w * 1.5)
        self.setGridSize(QSize())
        self.scheduleDelayedItemsLayout()
        self.viewport().update()

    def set_games(self, games: list[Game]):
        self.model_.clear()
        for g in games:
            it = QStandardItem()
            it.setData(g, ROLE_GAME)
            it.setEditable(False)
            self.model_.appendRow(it)

    def _ctx(self, pos):
        idx = self.indexAt(pos)
        if idx.isValid():
            self.context_requested.emit(idx.data(ROLE_GAME).id, self.viewport().mapToGlobal(pos))
