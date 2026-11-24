"""Drawing badges: Steam's badge images, or a GameKeeper badge for other games."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
)

from .. import badges
from ..storage import Game
from . import style
from .library_view import icon_pixmap

# ring colours for GameKeeper's own badges: bronze, silver, gold, platinum, diamond
TIERS = ["#b07a47", "#b9c3cc", "#e5b143", "#7fd4c9", "#9fc8ff"]
TIER_NAMES = ["Bronze", "Silver", "Gold", "Platinum", "Diamond"]

# Steam-like colours for the profile level ring, per ten levels
LEVEL_COLORS = ["#9b9b9b", "#c02942", "#d95b43", "#fecc23", "#467a3c",
                "#4e8ddb", "#7652c9", "#c252c9", "#542437", "#997c52"]

_cache: dict[tuple, QPixmap] = {}


def _generic(game: Game, level: int, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)
    ring = QColor(TIERS[level - 1])
    g = QRadialGradient(QPointF(s * 0.5, s * 0.4), s * 0.55)
    g.setColorAt(0, ring.lighter(130))
    g.setColorAt(1, ring.darker(160))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QRectF(s * 0.04, s * 0.04, s * 0.92, s * 0.92))
    p.setBrush(QColor(style.BG_DEEP))
    inner = QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68)
    p.drawEllipse(inner)
    icon = icon_pixmap(game, int(s * 0.5))
    clip = QPainterPath()
    clip.addEllipse(inner.adjusted(s * 0.04, s * 0.04, -s * 0.04, -s * 0.04))
    p.setClipPath(clip)
    p.drawPixmap(int(s * 0.25), int(s * 0.25), icon)
    p.setClipping(False)
    # level pips along the bottom of the ring
    p.setBrush(QColor("white"))
    for i in range(level):
        x = s * 0.5 + (i - (level - 1) / 2) * s * 0.09
        p.drawEllipse(QPointF(x, s * 0.9), s * 0.03, s * 0.03)
    p.end()
    return pm


def _grey(pm: QPixmap) -> QPixmap:
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            v = int(0.3 * c.red() + 0.59 * c.green() + 0.11 * c.blue())
            img.setPixelColor(x, y, QColor(v, v, v, int(c.alpha() * 0.45)))
    return QPixmap.fromImage(img)


def badge_pixmap(game: Game, level: int, size: int = 80, locked: bool = False) -> QPixmap:
    level = max(1, min(level, badges.MAX_LEVEL))
    path = badges.level_image(game, level)
    stamp = path.stat().st_mtime if path else 0
    key = (game.id, level, size, locked, stamp)
    if key in _cache:
        return _cache[key]
    pm = QPixmap(str(path)) if path else QPixmap()
    if pm.isNull():
        pm = _generic(game, level, size)
    else:
        pm = pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if locked:
        pm = _grey(pm)
    _cache[key] = pm
    return pm


def badge_image_path(game: Game, level: int) -> Path:
    """A file with the badge image (for popups); renders GameKeeper badges to disk."""
    path = badges.level_image(game, level)
    if path:
        return path
    out = game.folder / f"badge_gk_{level}.png"
    if not out.exists():
        game.folder.mkdir(parents=True, exist_ok=True)
        _generic(game, level, 128).save(str(out), "PNG")
    return out


def level_name(game: Game, level: int) -> str:
    info = badges.badge_info(game)
    if info.get("source") == "steam":
        return badges.level_name(game, level)
    return f"{TIER_NAMES[level - 1]} {game.name}"


def level_ring(level: int, size: int) -> QPixmap:
    """Steam-style circle with the profile level number."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    color = QColor(LEVEL_COLORS[min(level // 10, len(LEVEL_COLORS) - 1)])
    w = max(2.0, size * 0.08)
    p.setPen(QPen(color, w))
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawEllipse(QRectF(w / 2 + 1, w / 2 + 1, size - w - 2, size - w - 2))
    f = QFont()
    f.setPixelSize(int(size * (0.42 if level < 100 else 0.34)))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(pm.rect(), Qt.AlignCenter, str(level))
    p.end()
    return pm
