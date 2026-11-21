"""The page for a single game: play button, stats and achievements."""
from __future__ import annotations

import datetime as dt
import time

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListView, QMenu,
    QProgressBar, QPushButton, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from .. import tracking
from ..runner import format_playtime
from ..storage import Achievement, AchievementSet, Game
from . import style
from .flow import FlowLayout
from .library_view import cover_pixmap

ROLE_ACH = Qt.UserRole + 1
ROW_H = 76
ICON = 52
SORTS = ["Unlocked first", "Recently unlocked", "Rarest first", "Most common first", "A - Z"]


def _date(ts: int, with_time: bool = True) -> str:
    if not ts:
        return "-"
    return dt.datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M" if with_time else "%d %b %Y")


def _clock(seconds: int) -> str:
    h, rem = divmod(max(seconds, 0), 3600)
    return f"{h}:{rem // 60:02d}:{rem % 60:02d}"


def rarity_color(pct: float | None) -> str:
    if pct is None:
        return style.MUTED
    if pct < 5:
        return style.GOLD
    if pct < 15:
        return "#b78cff"
    if pct < 35:
        return "#6fb3ff"
    return style.MUTED


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
class Hero(QWidget):
    """Wide banner with the game's artwork faded into the background."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = QPixmap()
        self._scaled = QPixmap()

    def set_image(self, path):
        self.pm = QPixmap(str(path)) if path and path.exists() else QPixmap()
        self._scaled = QPixmap()
        self.update()

    def resizeEvent(self, e):
        self._scaled = QPixmap()
        super().resizeEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor(style.PANEL))
        if not self.pm.isNull():
            if self._scaled.isNull():   # scale once per size, not on every repaint
                self._scaled = self.pm.scaled(r.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            pm = self._scaled
            p.drawPixmap(0, 0, pm, (pm.width() - r.width()) // 2, (pm.height() - r.height()) // 3,
                         r.width(), r.height())
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, QColor(15, 18, 24, 50))
        g.setColorAt(0.5, QColor(15, 18, 24, 150))
        g.setColorAt(1, QColor(style.BG))
        p.fillRect(r, g)


class Stat(QLabel):
    def __init__(self, label: str):
        super().__init__()
        self.label = label
        self.setTextFormat(Qt.RichText)
        self.setStyleSheet("background: rgba(10,12,18,150); border-radius: 8px; padding: 6px 12px;")

    def set_value(self, value: str):
        self.setText(f"<div style='font-size:10px; color:{style.MUTED}; font-weight:600; letter-spacing:1px'>"
                     f"{self.label}</div><div style='font-size:14px; color:white; font-weight:600'>{value}</div>")


# --------------------------------------------------------------------------- #
# Achievement list (only visible rows are painted)
# --------------------------------------------------------------------------- #
class AchievementDelegate(QStyledItemDelegate):
    def __init__(self, page: "GamePage"):
        super().__init__(page)
        self.page = page
        self._icons: dict[str, QPixmap] = {}

    def clear_cache(self):
        self._icons.clear()

    def _icon(self, ach: Achievement) -> QPixmap | None:
        path = self.page.achset.icon_path(ach) if self.page.achset else None
        if not path:
            return None
        key = str(path)
        if key not in self._icons:
            pm = QPixmap(key)
            self._icons[key] = pm.scaled(ICON, ICON, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pm.isNull() else pm
        return self._icons[key]

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_H)

    def paint(self, p: QPainter, option, index):
        ach: Achievement = index.data(ROLE_ACH)
        if ach is None:
            return
        page = self.page
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect.adjusted(0, 3, -4, -3)
        hovered = option.state & QStyle.State_MouseOver
        locked = not ach.unlocked

        p.setPen(QPen(QColor("#3a465a" if hovered else style.BORDER), 1))
        p.setBrush(QColor(style.PANEL_2 if hovered else style.PANEL))
        p.drawRoundedRect(r, 8, 8)
        if ach.unlocked:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(style.GOLD))
            p.drawRoundedRect(QRect(r.x(), r.y() + 10, 3, r.height() - 20), 1.5, 1.5)

        # icon
        ir = QRect(r.x() + 12, r.y() + (r.height() - ICON) // 2, ICON, ICON)
        pm = self._icon(ach)
        path = QPainterPath()
        path.addRoundedRect(ir, 6, 6)
        p.setClipPath(path)
        if pm and not pm.isNull():
            p.drawPixmap(ir, pm)
        else:
            p.fillRect(ir, QColor(style.PANEL_2))
            f = p.font()
            f.setPixelSize(22)
            p.setFont(f)
            p.setPen(QColor(style.MUTED))
            p.drawText(ir, Qt.AlignCenter, "\U0001F512" if locked else "\U0001F3C6")
        p.setClipping(False)

        # right column
        right_w = 190 if r.width() > 560 else 120
        rr = QRect(r.right() - right_w - 12, r.y() + 10, right_w, r.height() - 20)
        small = QFont(p.font())
        small.setPixelSize(11)
        p.setFont(small)
        lines: list[tuple[str, str]] = []
        if ach.unlocked:
            lines.append((_date(ach.unlock_time, with_time=right_w > 150), style.GOLD))
            if ach.source in ("steam", "manual"):
                lines.append(({"steam": "imported from Steam", "manual": "unlocked by hand"}[ach.source], style.MUTED))
        elif ach.api_name in page.manual and page.tracked:
            lines.append(("unlock by hand", style.MUTED))
        if ach.global_percent is not None:
            lines.append((f"{ach.global_percent:.1f}% of players", rarity_color(ach.global_percent)))
        lh = 16
        y = rr.y() + (rr.height() - lh * len(lines)) // 2
        for text, color in lines:
            p.setPen(QColor(color))
            p.drawText(QRect(rr.x(), y, rr.width(), lh), Qt.AlignRight | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(text, Qt.ElideRight, rr.width()))
            y += lh

        # title + description
        secret = ach.hidden and locked and not page.reveal.isChecked()
        tx = ir.right() + 14
        tw = rr.x() - tx - 10
        title = QFont(p.font())
        title.setPixelSize(14)
        title.setBold(True)
        p.setFont(title)
        p.setPen(QColor(style.MUTED if locked else style.TEXT))
        t = "Hidden achievement" if secret else ach.title
        p.drawText(QRect(tx, r.y() + 12, tw, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(t, Qt.ElideRight, tw))
        desc = QFont(p.font())
        desc.setPixelSize(12)
        desc.setBold(False)
        p.setFont(desc)
        p.setPen(QColor(style.MUTED))
        d = "Keep playing to find out." if secret else (ach.description or "")
        dr = QRect(tx, r.y() + 34, tw, r.height() - 40)
        p.setClipRect(dr)
        p.drawText(dr, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, d)
        p.restore()


class AchievementList(QListView):
    context = Signal(object, object)    # Achievement, global pos

    def __init__(self, page: "GamePage"):
        super().__init__(page)
        self.setObjectName("AchList")
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(26)
        self.setSelectionMode(QListView.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.model_ = QStandardItemModel(self)
        self.setModel(self.model_)
        self.delegate = AchievementDelegate(page)
        self.setItemDelegate(self.delegate)
        self.setStyleSheet("QListView#AchList { background: transparent; border: none; }")

    def set_items(self, items: list[Achievement]):
        self.model_.clear()
        for a in items:
            it = QStandardItem()
            it.setData(a, ROLE_ACH)
            it.setEditable(False)
            self.model_.appendRow(it)

    def contextMenuEvent(self, e):
        idx = self.indexAt(e.pos())
        if idx.isValid():
            self.context.emit(idx.data(ROLE_ACH), e.globalPos())


# --------------------------------------------------------------------------- #
class GamePage(QWidget):
    back = Signal()
    play = Signal(str)
    edit = Signal(str)
    fetch_data = Signal(str)
    import_steam = Signal(str)
    remove = Signal(str)
    toggle_favorite = Signal(str)
    open_folder = Signal(str)
    achievement_toggled = Signal(str, str, bool)   # game id, api name, unlocked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game: Game | None = None
        self.achset: AchievementSet | None = None
        self.manual: dict[str, str] = {}
        self.tracked = False
        self.session_start_fn = lambda game_id: 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- header ----
        self.hero = Hero()
        hl = QVBoxLayout(self.hero)
        hl.setContentsMargins(28, 16, 28, 16)
        backbtn = QPushButton("←  Library")
        backbtn.setToolTip("Back to library (Esc)")
        backbtn.setCursor(Qt.PointingHandCursor)
        backbtn.setStyleSheet("QPushButton { background: rgba(0,0,0,110); color: white; border: none; "
                              "border-radius: 6px; padding: 6px 12px; } QPushButton:hover { background: rgba(0,0,0,170); }")
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
        info.setSpacing(12)
        info.addStretch()
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 32px; font-weight: 800; background: transparent; color: white;")
        self.title.setWordWrap(True)
        info.addWidget(self.title)

        bar = QWidget()
        bar.setObjectName("HeroBar")
        bar.setStyleSheet("#HeroBar { background: transparent; }")
        self.flow = FlowLayout(bar, spacing=10)
        self.play_btn = QPushButton("▶  PLAY")
        self.play_btn.setObjectName("Play")
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setMinimumWidth(170)
        self.play_btn.clicked.connect(lambda: self.game and self.play.emit(self.game.id))
        self.stat_time = Stat("PLAY TIME")
        self.stat_last = Stat("LAST PLAYED")
        self.stat_ach = Stat("ACHIEVEMENTS")
        self.more_btn = QPushButton("⚙  Manage")
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.setFixedHeight(44)
        self.more_btn.clicked.connect(self._manage_menu)
        for w in (self.play_btn, self.stat_time, self.stat_last, self.stat_ach, self.more_btn):
            self.flow.addWidget(w)
        info.addWidget(bar)
        head.addLayout(info, 1)
        hl.addLayout(head)
        outer.addWidget(self.hero)

        # ---- achievements ----
        sec = QWidget()
        sl = QVBoxLayout(sec)
        sl.setContentsMargins(28, 14, 24, 0)
        sl.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.ach_title = QLabel("Achievements")
        self.ach_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        top.addWidget(self.ach_title)
        top.addStretch()
        self.tools = QWidget()
        tl = QHBoxLayout(self.tools)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        self.seg = QButtonGroup(self)
        seg_box = QWidget()
        seg_box.setObjectName("Segmented")
        sbl = QHBoxLayout(seg_box)
        sbl.setContentsMargins(3, 3, 3, 3)
        sbl.setSpacing(2)
        for i, name in enumerate(("All", "Unlocked", "Locked")):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.seg.addButton(b, i)
            sbl.addWidget(b)
        self.seg.button(0).setChecked(True)
        self.seg.idClicked.connect(lambda _: self.refresh_achievements())
        tl.addWidget(seg_box)
        self.sort = QComboBox()
        self.sort.addItems(SORTS)
        self.sort.currentIndexChanged.connect(self.refresh_achievements)
        tl.addWidget(self.sort)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find achievement...")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(190)
        self.search.textChanged.connect(self.refresh_achievements)
        tl.addWidget(self.search)
        self.reveal = QCheckBox("Show hidden")
        self.reveal.toggled.connect(lambda _: self.list.viewport().update())
        tl.addWidget(self.reveal)
        top.addWidget(self.tools)
        sl.addLayout(top)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        sl.addWidget(self.bar)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet(f"color: {style.MUTED}; padding: 2px 0;")
        sl.addWidget(self.notice)
        self.notice_btn = QPushButton()
        self.notice_btn.setObjectName("Primary")
        self.notice_btn.clicked.connect(self._notice_action)
        sl.addWidget(self.notice_btn, 0, Qt.AlignLeft)
        self.list = AchievementList(self)
        self.list.context.connect(self._ach_menu)
        sl.addWidget(self.list, 1)
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(f"color: {style.MUTED}; padding: 30px;")
        sl.addWidget(self.empty, 1)
        outer.addWidget(sec, 1)

    # ------------------------------------------------------------------ #
    # responsive layout
    # ------------------------------------------------------------------ #
    def resizeEvent(self, e):
        super().resizeEvent(e)
        w, h = self.width(), self.height()
        self.hero.setFixedHeight(int(min(320, max(220, h * 0.36))))
        self.cover.setVisible(w > 820)
        self.title.setStyleSheet(f"font-size: {32 if w > 900 else 24}px; font-weight: 800; "
                                 "background: transparent; color: white;")
        self.search.setVisible(w > 980)
        self.sort.setVisible(w > 760)

    # ------------------------------------------------------------------ #
    def show_game(self, game: Game):
        changed = self.game is None or self.game.id != game.id
        self.game = game
        if changed:
            self.seg.button(0).setChecked(True)
            self.sort.setCurrentIndex(0)
            self.search.clear()
            self.reveal.setChecked(False)
            self.list.delegate.clear_cache()
            self.hero.set_image(game.hero_path if game.hero_path.exists() else game.cover_path)
            self.list.scrollToTop()
        self.cover.setPixmap(cover_pixmap(game, 120, 180))
        self.title.setText(game.name)
        self.manual = tracking.manual_only(game)
        self.tracked = bool(tracking.describe(game))
        self.refresh_stats()
        self.achset = AchievementSet(game.id)
        self.refresh_achievements()

    def set_running(self, running: bool):
        self.play_btn.setEnabled(not running)
        if running:
            self._timer.start()
            self._tick()
        else:
            self._timer.stop()
            self.play_btn.setText("▶  PLAY")

    def _tick(self):
        start = self.session_start_fn(self.game.id) if self.game else 0.0
        if start:
            self.play_btn.setText(f"●  PLAYING  {_clock(int(time.time() - start))}")
        else:
            self.play_btn.setText("●  STARTING...")

    def refresh_stats(self):
        g = self.game
        if not g:
            return
        t = format_playtime(g.total_playtime)
        if g.steam_playtime:
            t += f"<span style='color:{style.MUTED}; font-size:10px'>  incl. {format_playtime(g.steam_playtime)} on Steam</span>"
        self.stat_time.set_value(t)
        self.stat_last.set_value(_date(g.last_played, with_time=False) if g.last_played else "Never")
        if g.achievements_total:
            pct = 100 * g.achievements_unlocked // g.achievements_total
            self.stat_ach.set_value(f"{g.achievements_unlocked} / {g.achievements_total}  ·  {pct}%")
            self.stat_ach.show()
        else:
            self.stat_ach.hide()
        self.flow.invalidate()

    def refresh_achievements(self):
        g, a = self.game, self.achset
        if not g or a is None:
            return
        a.load()
        has = a.total > 0
        for w in (self.bar, self.tools, self.list):
            w.setVisible(has)
        self.reveal.setVisible(has and any(x.hidden for x in a.items))
        self.notice_btn.hide()
        self.empty.hide()

        if not has:
            self.ach_title.setText("Achievements")
            if not g.appid:
                self._notice("This game isn't linked to Steam, so it has no achievement list. "
                             "Link it under Manage → Edit if it's on Steam.", "Edit game", "edit")
            else:
                self._notice("No achievement data yet. Pull it from Steam when you're ready to start.",
                             "Pull achievements from Steam", "fetch")
            return

        pct = 100 * a.unlocked_count // a.total
        self.ach_title.setText(f"Achievements  ·  {a.unlocked_count} / {a.total}  ·  {pct}%")
        self.bar.setMaximum(a.total)
        self.bar.setValue(a.unlocked_count)
        if self.tracked:
            text = "✔  Automatic unlocks are on: " + " and ".join(tracking.describe(g)) + "."
            if self.manual:
                text += f"  {len(self.manual)} marked “unlock by hand” can't be detected; right-click them when earned."
            self._notice(text)
        else:
            self._notice("Automatic unlocks aren't set up for this game yet. "
                         "Right-click an achievement to unlock it by hand.")

        items = list(a.items)
        mode = self.seg.checkedId()
        if mode == 1:
            items = [x for x in items if x.unlocked]
        elif mode == 2:
            items = [x for x in items if not x.unlocked]
        q = self.search.text().strip().lower()
        if q:
            reveal = self.reveal.isChecked()
            items = [x for x in items
                     if (not x.hidden or x.unlocked or reveal) and (q in x.title.lower() or q in x.description.lower())]
        sort = self.sort.currentText()
        if sort == "Recently unlocked":
            items.sort(key=lambda x: (not x.unlocked, -x.unlock_time))
        elif sort == "Rarest first":
            items.sort(key=lambda x: x.global_percent if x.global_percent is not None else 101)
        elif sort == "Most common first":
            items.sort(key=lambda x: -(x.global_percent or 0))
        elif sort == "A - Z":
            items.sort(key=lambda x: x.title.lower())
        else:
            items.sort(key=lambda x: not x.unlocked)   # stable: keeps the game's order
        self.list.set_items(items)
        if not items:
            self.list.hide()
            self.empty.setText("Nothing here." if not q else f"No achievements match “{q}”.")
            self.empty.show()

    def _notice(self, text: str, button: str = "", action: str = ""):
        self.notice.setText(text)
        self.notice.show()
        if button:
            self.notice_btn.setText(button)
            self.notice_btn.setProperty("action", action)
            self.notice_btn.show()

    def _notice_action(self):
        if self.game:
            {"fetch": self.fetch_data, "edit": self.edit}[self.notice_btn.property("action")].emit(self.game.id)

    def _ach_menu(self, ach: Achievement, pos):
        if not self.game:
            return
        m = QMenu(self)
        act = m.addAction("Mark as locked" if ach.unlocked else "\U0001F3C6  Unlock")
        if m.exec(pos) == act:
            self.achievement_toggled.emit(self.game.id, ach.api_name, not ach.unlocked)

    def _manage_menu(self):
        g = self.game
        if not g:
            return
        m = QMenu(self)
        m.addAction("Edit game...", lambda: self.edit.emit(g.id))
        m.addAction("Remove from favorites" if g.favorite else "Add to favorites", lambda: self.toggle_favorite.emit(g.id))
        m.addAction("Open game folder", lambda: self.open_folder.emit(g.id))
        m.addSeparator()
        sm = m.addMenu("Steam data")
        a1 = sm.addAction("Pull / refresh cover art and achievements", lambda: self.fetch_data.emit(g.id))
        a2 = sm.addAction("Import my unlocks and playtime from Steam", lambda: self.import_steam.emit(g.id))
        a1.setEnabled(bool(g.appid))
        a2.setEnabled(bool(g.appid))
        m.addSeparator()
        m.addAction("Remove from library...", lambda: self.remove.emit(g.id))
        m.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))
