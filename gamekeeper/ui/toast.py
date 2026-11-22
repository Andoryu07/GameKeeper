"""The "Achievement unlocked" popup shown over the game."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..storage import DATA_DIR
from . import style

try:
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # multimedia module missing on some installs
    QSoundEffect = None

WIDTH, HEIGHT, MARGIN = 360, 92, 18
SOUND_FILE = DATA_DIR / "unlock.wav"


def _make_chime(path: Path) -> None:
    """Generate a short two-note chime so no audio file has to ship with the app."""
    rate = 44100
    frames = bytearray()
    total = int(rate * 0.6)
    notes = ((880.0, 0.0, 0.35), (1318.5, 0.09, 0.5))
    for i in range(total):
        t = i / rate
        v = 0.0
        for freq, start, length in notes:
            if start <= t < start + length:
                lt = t - start
                env = min(lt / 0.01, 1.0) * math.exp(-lt * 7)
                v += env * (math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(4 * math.pi * freq * t))
        frames += struct.pack("<h", int(max(-1, min(1, v * 0.3)) * 32767))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


class _Toast(QWidget):
    def __init__(self, title: str, subtitle: str, icon: QPixmap | None, seconds: int):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedSize(WIDTH, HEIGHT)

        card = QWidget(self)
        card.setObjectName("ToastCard")
        card.setGeometry(6, 6, WIDTH - 12, HEIGHT - 12)
        card.setStyleSheet(f"""
            #ToastCard {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a3f5a, stop:1 {style.BG_DEEP});
                          border: 1px solid #3d5a78; border-radius: 3px; }}
            QLabel {{ background: transparent; }}
        """)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 160))
        card.setGraphicsEffect(shadow)

        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 10, 14, 10)
        lay.setSpacing(12)
        ic = QLabel()
        ic.setFixedSize(56, 56)
        ic.setPixmap(_rounded(icon, 56) if icon and not icon.isNull() else _trophy(56))
        lay.addWidget(ic)
        text = QVBoxLayout()
        text.setSpacing(2)
        head = QLabel("ACHIEVEMENT UNLOCKED")
        head.setStyleSheet(f"color: {style.GOLD}; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        name = QLabel(title)
        name.setStyleSheet(f"color: {style.TEXT_BRIGHT}; font-size: 14px; font-weight: 600;")
        sub = QLabel(subtitle)
        sub.setStyleSheet(f"color: {style.MUTED}; font-size: 11px;")
        for w in (name, sub):
            w.setWordWrap(False)
            w.setText(w.fontMetrics().elidedText(w.text(), Qt.ElideRight, WIDTH - 120))
        text.addStretch()
        text.addWidget(head)
        text.addWidget(name)
        text.addWidget(sub)
        text.addStretch()
        lay.addLayout(text, 1)

        self._anim = None
        QTimer.singleShot(seconds * 1000, self.fade_out)

    def slide_in(self, target: QRect):
        start = QRect(target.x(), target.y() + 40, target.width(), target.height())
        self.setGeometry(start)
        self.setWindowOpacity(0.0)
        self.show()
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(260)
        self._anim.setStartValue(start)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(220)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def fade_out(self):
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(400)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self.close)
        self._fade.start()


def _rounded(pm: QPixmap, size: int) -> QPixmap:
    pm = pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, 2, 2)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


def _trophy(size: int) -> QPixmap:
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(style.PANEL))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, size, size, 2, 2)
    p.setPen(QColor(style.GOLD))
    f = p.font()
    f.setPixelSize(int(size * 0.55))
    p.setFont(f)
    p.drawText(out.rect(), Qt.AlignCenter, "\U0001F3C6")
    p.end()
    return out


class ToastManager:
    """Stacks popups in the bottom-right corner of the main screen."""

    def __init__(self):
        self.active: list[_Toast] = []
        self.sound = None
        self.enabled_sound = True
        self.seconds = 6

    def _play(self):
        if not (self.enabled_sound and QSoundEffect):
            return
        if self.sound is None:
            try:
                if not SOUND_FILE.exists():
                    _make_chime(SOUND_FILE)
                self.sound = QSoundEffect()
                self.sound.setSource(QUrl.fromLocalFile(str(SOUND_FILE)))
                self.sound.setVolume(0.6)
            except Exception:  # noqa: BLE001 - sound is optional
                self.sound = False
                return
        if self.sound:
            self.sound.play()

    def show(self, title: str, subtitle: str = "", icon_path: Path | None = None):
        icon = QPixmap(str(icon_path)) if icon_path else None
        t = _Toast(title, subtitle, icon, self.seconds)
        self.active = [x for x in self.active if x.isVisible()]
        screen = QGuiApplication.primaryScreen().availableGeometry()
        y = screen.bottom() - MARGIN - HEIGHT - len(self.active) * (HEIGHT + 6)
        target = QRect(screen.right() - MARGIN - WIDTH, y, WIDTH, HEIGHT)
        t.destroyed.connect(lambda *_: self.active.remove(t) if t in self.active else None)
        self.active.append(t)
        t.slide_in(target)
        self._play()
