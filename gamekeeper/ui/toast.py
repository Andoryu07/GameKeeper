"""The "Achievement unlocked" popup shown over the game."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, QUrl, Signal
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
    done = Signal(object)

    def __init__(self, title: str, subtitle: str, icon: QPixmap | None, seconds: int,
                 label: str = "ACHIEVEMENT UNLOCKED"):
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
        head = QLabel(label)
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
        self._seconds = seconds
        self._closing = False

    def slide_in(self, target: QRect, screen: QRect):
        """Rise from below the bottom edge of the screen into place."""
        start = QRect(target.x(), screen.bottom() + 8, target.width(), target.height())
        self.setGeometry(start)
        self.show()
        self._animate(target, 380)
        QTimer.singleShot(self._seconds * 1000, self.fade_out)

    def move_to(self, target: QRect):
        """Slide to a new slot (when a popup below it goes away)."""
        if not self._closing:
            self._animate(target, 240)

    def _animate(self, target: QRect, ms: int):
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(ms)
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def fade_out(self):
        if self._closing:
            return
        self._closing = True
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(350)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._finish)
        self._fade.start()

    def _finish(self):
        self.done.emit(self)
        self.close()

    def mousePressEvent(self, e):   # click to dismiss
        self.fade_out()


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
    """Steam-style popups in the bottom-right corner.

    Each popup rises from the bottom edge of the screen. At most MAX_VISIBLE
    are shown at once, each new one stacked above the previous; the rest
    wait their turn. When one goes away, the ones above slide down.
    """

    MAX_VISIBLE = 3

    def __init__(self):
        self.active: list[_Toast] = []           # index 0 = lowest slot
        self.pending: list[tuple] = []
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

    @staticmethod
    def _screens() -> tuple[QRect, QRect]:
        scr = QGuiApplication.primaryScreen()
        return scr.availableGeometry(), scr.geometry()

    def _slot(self, i: int) -> QRect:
        avail, _ = self._screens()
        y = avail.bottom() - MARGIN - HEIGHT - i * (HEIGHT + 6)
        return QRect(avail.right() - MARGIN - WIDTH, y, WIDTH, HEIGHT)

    def show(self, title: str, subtitle: str = "", icon_path: Path | None = None,
             label: str = "ACHIEVEMENT UNLOCKED"):
        self.pending.append((title, subtitle, icon_path, label))
        self._pump()

    def _pump(self):
        while len(self.active) < self.MAX_VISIBLE and self.pending:
            title, subtitle, icon_path, label = self.pending.pop(0)
            icon = QPixmap(str(icon_path)) if icon_path else None
            t = _Toast(title, subtitle, icon, self.seconds, label)
            t.done.connect(self._on_done)
            self.active.append(t)
            t.slide_in(self._slot(len(self.active) - 1), self._screens()[1])
            self._play()

    def _on_done(self, toast: _Toast):
        if toast in self.active:
            self.active.remove(toast)
        for i, t in enumerate(self.active):
            t.move_to(self._slot(i))
        QTimer.singleShot(250, self._pump)
