"""The page for a single game: play button, stats and achievements."""
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ..runner import format_playtime
from ..storage import Achievement, AchievementSet, Game
from . import style
from .library_view import cover_pixmap


def _date(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M") if ts else "-"


class Hero(QWidget):
    """Wide banner with the game's artwork faded into the background."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = QPixmap()
        self.setFixedHeight(300)

    def set_image(self, path):
        self.pm = QPixmap(str(path)) if path and path.exists() else QPixmap()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor(style.PANEL))
        if not self.pm.isNull():
            pm = self.pm.scaled(r.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap(0, 0, pm, (pm.width() - r.width()) // 2, (pm.height() - r.height()) // 3,
                         r.width(), r.height())
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, QColor(15, 18, 24, 60))
        g.setColorAt(0.55, QColor(15, 18, 24, 170))
        g.setColorAt(1, QColor(style.BG))
        p.fillRect(r, g)


class AchievementRow(QFrame):
    context = Signal(str, object)

    def __init__(self, ach: Achievement, achset: AchievementSet, reveal: bool):
        super().__init__()
        self.ach = ach
        self.setObjectName("AchRow")
        locked = not ach.unlocked
        self.setStyleSheet(f"""
            #AchRow {{ background: {style.PANEL}; border: 1px solid {style.BORDER}; border-radius: 8px; }}
            #AchRow:hover {{ border-color: #3a465a; }}
            QLabel {{ background: transparent; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 14, 8)
        lay.setSpacing(12)

        icon = QLabel()
        icon.setFixedSize(52, 52)
        path = achset.icon_path(ach)
        if path:
            icon.setPixmap(QPixmap(str(path)).scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon.setText("\U0001F3C6" if not locked else "\U0001F512")
            icon.setAlignment(Qt.AlignCenter)
            icon.setStyleSheet(f"background: {style.PANEL_2}; border-radius: 6px; font-size: 22px;")
        lay.addWidget(icon)

        secret = ach.hidden and locked and not reveal
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel("Hidden achievement" if secret else ach.title)
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {style.MUTED if locked else style.TEXT};")
        desc = QLabel("Keep playing to find out." if secret else (ach.description or ""))
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {style.MUTED}; font-size: 12px;")
        text.addWidget(title)
        if desc.text():
            text.addWidget(desc)
        lay.addLayout(text, 1)

        right = QVBoxLayout()
        right.setSpacing(2)
        if ach.unlocked:
            when = QLabel(f"Unlocked {_date(ach.unlock_time)}")
            when.setStyleSheet(f"color: {style.GOLD}; font-size: 11px;")
            when.setAlignment(Qt.AlignRight)
            right.addWidget(when)
            if ach.source and ach.source != "emulator":
                src = QLabel({"steam": "imported from Steam", "manual": "set manually"}.get(ach.source, ach.source))
                src.setStyleSheet(f"color: {style.MUTED}; font-size: 10px;")
                src.setAlignment(Qt.AlignRight)
                right.addWidget(src)
        if ach.global_percent is not None:
            pct = QLabel(f"{ach.global_percent:.1f}% of players")
            pct.setStyleSheet(f"color: {style.MUTED}; font-size: 11px;")
            pct.setAlignment(Qt.AlignRight)
            right.addWidget(pct)
        lay.addLayout(right)

    def contextMenuEvent(self, e):
        self.context.emit(self.ach.api_name, e.globalPos())


class GamePage(QWidget):
    back = Signal()
    play = Signal(str)
    edit = Signal(str)
    fetch_data = Signal(str)
    import_steam = Signal(str)
    setup_emulator = Signal(str)
    restore_emulator = Signal(str)
    remove = Signal(str)
    toggle_favorite = Signal(str)
    open_folder = Signal(str)
    achievement_toggled = Signal(str, str, bool)   # game id, api name, unlocked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game: Game | None = None
        self.achset: AchievementSet | None = None
        self.running_since = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(0, 0, 0, 30)
        self.body.setSpacing(0)

        # hero with overlaid header
        self.hero = Hero()
        hl = QVBoxLayout(self.hero)
        hl.setContentsMargins(28, 16, 28, 18)
        backbtn = QPushButton("←  Library")
        backbtn.setObjectName("Flat")
        backbtn.setStyleSheet("background: rgba(0,0,0,90); color: white; border-radius: 6px; padding: 6px 12px;")
        backbtn.clicked.connect(self.back)
        hl.addWidget(backbtn, 0, Qt.AlignLeft)
        hl.addStretch()
        head = QHBoxLayout()
        head.setSpacing(22)
        self.cover = QLabel()
        self.cover.setFixedSize(120, 180)
        self.cover.setStyleSheet("background: transparent;")
        head.addWidget(self.cover, 0, Qt.AlignBottom)
        info = QVBoxLayout()
        info.setSpacing(10)
        info.addStretch()
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 32px; font-weight: 800; background: transparent; color: white;")
        self.title.setWordWrap(True)
        info.addWidget(self.title)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.play_btn = QPushButton("▶  PLAY")
        self.play_btn.setObjectName("Play")
        self.play_btn.clicked.connect(lambda: self.game and self.play.emit(self.game.id))
        row.addWidget(self.play_btn)
        self.stat_time = self._stat("PLAY TIME")
        self.stat_last = self._stat("LAST PLAYED")
        self.stat_ach = self._stat("ACHIEVEMENTS")
        for s in (self.stat_time, self.stat_last, self.stat_ach):
            row.addWidget(s)
        row.addStretch()

        self.more_btn = QPushButton("⚙  Manage")
        self.more_btn.clicked.connect(self._manage_menu)
        row.addWidget(self.more_btn)
        info.addLayout(row)
        head.addLayout(info, 1)
        hl.addLayout(head)
        self.body.addWidget(self.hero)

        # achievements
        sec = QWidget()
        self.sec = QVBoxLayout(sec)
        self.sec.setContentsMargins(28, 18, 28, 0)
        self.sec.setSpacing(10)
        top = QHBoxLayout()
        self.ach_title = QLabel("Achievements")
        self.ach_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        top.addWidget(self.ach_title)
        top.addStretch()
        self.reveal = QCheckBox("Show hidden")
        self.reveal.toggled.connect(self.refresh_achievements)
        self.filter = QComboBox()
        self.filter.addItems(["All", "Unlocked", "Locked", "Rarest first"])
        self.filter.currentIndexChanged.connect(self.refresh_achievements)
        top.addWidget(self.reveal)
        top.addWidget(self.filter)
        self.sec.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.sec.addWidget(self.bar)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet(f"color: {style.MUTED}; padding: 8px 0;")
        self.sec.addWidget(self.notice)
        self.notice_btn = QPushButton()
        self.notice_btn.setObjectName("Primary")
        self.notice_btn.clicked.connect(self._notice_action)
        self.sec.addWidget(self.notice_btn, 0, Qt.AlignLeft)
        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(6)
        self.sec.addLayout(self.list_box)
        self.body.addWidget(sec)
        self.body.addStretch()

    def _stat(self, label: str) -> QLabel:
        w = QLabel()
        w.setProperty("label", label)
        w.setStyleSheet("background: rgba(0,0,0,110); border-radius: 6px; padding: 5px 12px;")
        w.setTextFormat(Qt.RichText)
        return w

    @staticmethod
    def _set_stat(w: QLabel, value: str):
        w.setText(f"<div style='font-size:10px; color:{style.MUTED}; font-weight:600'>{w.property('label')}</div>"
                  f"<div style='font-size:13px; color:white'>{value}</div>")

    # ------------------------------------------------------------------ #
    def show_game(self, game: Game):
        changed = self.game is None or self.game.id != game.id
        self.game = game
        if changed:
            self.filter.setCurrentIndex(0)
            self.reveal.setChecked(False)
        self.hero.set_image(game.hero_path if game.hero_path.exists() else game.cover_path)
        self.cover.setPixmap(cover_pixmap(game, 120, 180))
        self.title.setText(game.name)
        self.refresh_stats()
        self.achset = AchievementSet(game.id)
        self.refresh_achievements()

    def set_running(self, running: bool):
        self.play_btn.setEnabled(not running)
        self.play_btn.setText("RUNNING" if running else "▶  PLAY")

    def refresh_stats(self):
        g = self.game
        if not g:
            return
        t = format_playtime(g.total_playtime)
        if g.steam_playtime:
            t += f"<span style='color:{style.MUTED}; font-size:10px'> (incl. {format_playtime(g.steam_playtime)} on Steam)</span>"
        self._set_stat(self.stat_time, t)
        self._set_stat(self.stat_last, dt.datetime.fromtimestamp(g.last_played).strftime("%d %b %Y") if g.last_played else "Never")
        if g.achievements_total:
            pct = 100 * g.achievements_unlocked // g.achievements_total
            self._set_stat(self.stat_ach, f"{g.achievements_unlocked} / {g.achievements_total}  ({pct}%)")
            self.stat_ach.show()
        else:
            self.stat_ach.hide()

    def refresh_achievements(self):
        while self.list_box.count():
            w = self.list_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        g, a = self.game, self.achset
        if not g or a is None:
            return
        a.load()
        has = a.total > 0
        self.bar.setVisible(has)
        self.filter.setVisible(has)
        self.reveal.setVisible(has and any(x.hidden for x in a.items))
        self.notice_btn.hide()
        self.notice.hide()

        if not has:
            self.ach_title.setText("Achievements")
            if not g.appid:
                self._notice("This game isn't linked to Steam, so there are no achievements to track. "
                             "Link it from Manage → Edit if it's a Steam game.", "Edit game", "edit")
            else:
                self._notice("No achievement data yet. Pull it from Steam when you're ready to start.",
                             "Pull achievements from Steam", "fetch")
            return

        self.ach_title.setText(f"Achievements  ·  {a.unlocked_count} / {a.total}")
        self.bar.setMaximum(a.total)
        self.bar.setValue(a.unlocked_count)
        if not g.emulator_installed:
            self._notice("Automatic unlocks are off for this game. Set up tracking under "
                         "Manage → Achievement tracking, or right-click an achievement to unlock it by hand.")

        items = list(a.items)
        mode = self.filter.currentText()
        if mode == "Unlocked":
            items = [x for x in items if x.unlocked]
            items.sort(key=lambda x: -x.unlock_time)
        elif mode == "Locked":
            items = [x for x in items if not x.unlocked]
        elif mode == "Rarest first":
            items.sort(key=lambda x: x.global_percent if x.global_percent is not None else 101)
        else:
            items.sort(key=lambda x: (not x.unlocked, -x.unlock_time if x.unlocked else 0))
        for ach in items:
            row = AchievementRow(ach, a, self.reveal.isChecked())
            row.context.connect(self._ach_menu)
            self.list_box.addWidget(row)

    def _notice(self, text: str, button: str = "", action: str = ""):
        self.notice.setText(text)
        self.notice.show()
        if button:
            self.notice_btn.setText(button)
            self.notice_btn.setProperty("action", action)
            self.notice_btn.show()

    def _notice_action(self):
        if not self.game:
            return
        action = self.notice_btn.property("action")
        {"fetch": self.fetch_data, "edit": self.edit}[action].emit(self.game.id)

    def _ach_menu(self, api_name: str, pos):
        ach = self.achset.by_name().get(api_name) if self.achset else None
        if not ach or not self.game:
            return
        m = QMenu(self)
        if ach.unlocked:
            act = m.addAction("Mark as locked")
        else:
            act = m.addAction("Unlock manually")
        if m.exec(pos) == act:
            self.achievement_toggled.emit(self.game.id, api_name, not ach.unlocked)

    def _manage_menu(self):
        g = self.game
        if not g:
            return
        m = QMenu(self)
        m.addAction("Edit game...", lambda: self.edit.emit(g.id))
        m.addAction("Unfavorite" if g.favorite else "Add to favorites", lambda: self.toggle_favorite.emit(g.id))
        m.addAction("Open game folder", lambda: self.open_folder.emit(g.id))
        m.addSeparator()
        sm = m.addMenu("Steam data")
        a1 = sm.addAction("Pull / refresh cover art and achievements", lambda: self.fetch_data.emit(g.id))
        a2 = sm.addAction("Import my unlocks and playtime from Steam", lambda: self.import_steam.emit(g.id))
        a1.setEnabled(bool(g.appid))
        a2.setEnabled(bool(g.appid))
        em = m.addMenu("Achievement tracking")
        b1 = em.addAction("Set up automatic tracking (install emulator)", lambda: self.setup_emulator.emit(g.id))
        b2 = em.addAction("Restore original Steam files", lambda: self.restore_emulator.emit(g.id))
        b1.setEnabled(bool(g.appid))
        b2.setEnabled(g.emulator_installed)
        m.addSeparator()
        m.addAction("Remove from library...", lambda: self.remove.emit(g.id))
        m.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))
