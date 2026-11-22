"""The page for a single game: banner, play bar, achievements, review, details."""
from __future__ import annotations

import datetime as dt
import os
import time

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPixmap, QStandardItem, QStandardItemModel,
)
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListView, QMenu,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QStackedWidget, QStyle, QStyledItemDelegate,
    QVBoxLayout, QWidget,
)

from .. import tracking
from ..runner import format_playtime
from ..storage import Achievement, AchievementSet, Game
from . import style
from .flow import FlowLayout
from .rating import StarRating

ROLE_ACH = Qt.UserRole + 1
ROW_H = 80
ICON = 60
SORTS = ["Unlocked first", "Recently unlocked", "Rarest first", "Most common first", "A - Z"]
RATING_WORDS = {1: "Terrible", 2: "Bad", 3: "Poor", 4: "Below average", 5: "Average", 6: "Decent",
                7: "Good", 8: "Great", 9: "Amazing", 10: "Masterpiece"}


def _date(ts: int, with_time: bool = True) -> str:
    if not ts:
        return "-"
    d = dt.datetime.fromtimestamp(ts)
    return d.strftime("%d %b %Y @ %H:%M") if with_time else d.strftime("%d %b %Y")


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
        return style.ACCENT
    return style.MUTED


def _card(title: str = "") -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    w.setObjectName("Card")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(18, 14, 18, 16)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setObjectName("CardTitle")
        lay.addWidget(t)
    return w, lay


# --------------------------------------------------------------------------- #
# Banner
# --------------------------------------------------------------------------- #
class Hero(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = QPixmap()
        self._scaled = QPixmap()
        self.title = ""

    def set_image(self, path):
        self.pm = QPixmap(str(path)) if path and path.exists() else QPixmap()
        self._scaled = QPixmap()
        self.update()

    def resizeEvent(self, e):
        self._scaled = QPixmap()
        super().resizeEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        p.fillRect(r, QColor(style.BG_DEEP))
        if not self.pm.isNull():
            if self._scaled.isNull():
                self._scaled = self.pm.scaled(r.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            pm = self._scaled
            p.drawPixmap(0, 0, pm, (pm.width() - r.width()) // 2, (pm.height() - r.height()) // 3,
                         r.width(), r.height())
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, QColor(0, 0, 0, 30))
        g.setColorAt(0.6, QColor(0, 0, 0, 60))
        g.setColorAt(1, QColor(0, 0, 0, 170))
        p.fillRect(r, g)
        if self.title:
            f = QFont(self.font())
            f.setPixelSize(40 if r.width() > 900 else 30)
            f.setBold(True)
            p.setFont(f)
            tr = QRect(32, r.height() - 90, r.width() - 64, 70)
            p.setPen(QColor(0, 0, 0, 160))
            p.drawText(tr.translated(0, 2), Qt.AlignLeft | Qt.AlignBottom, self.title)
            p.setPen(QColor("white"))
            p.drawText(tr, Qt.AlignLeft | Qt.AlignBottom, self.title)


class Stat(QWidget):
    def __init__(self, label: str):
        super().__init__()
        self.setObjectName("Stat")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 0, 14, 0)
        lay.setSpacing(2)
        self.label = QLabel(label)
        self.label.setStyleSheet(f"color: {style.MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        self.value = QLabel()
        self.value.setStyleSheet(f"color: {style.TEXT}; font-size: 13px;")
        self.value.setTextFormat(Qt.RichText)
        lay.addWidget(self.label)
        lay.addWidget(self.value)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(120, 4)
        self.bar.hide()
        lay.addWidget(self.bar)


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
        r = option.rect.adjusted(0, 2, -6, -2)
        hovered = option.state & QStyle.State_MouseOver
        locked = not ach.unlocked
        p.fillRect(r, QColor(style.PANEL_2 if hovered else style.PANEL))

        # rarity bar along the bottom
        if ach.global_percent is not None:
            w = int(r.width() * min(ach.global_percent, 100) / 100)
            c = QColor(style.ACCENT)
            c.setAlpha(60)
            p.fillRect(QRect(r.x(), r.bottom() - 2, w, 3), c)

        ir = QRect(r.x() + 10, r.y() + (r.height() - ICON) // 2, ICON, ICON)
        pm = self._icon(ach)
        if pm and not pm.isNull():
            p.drawPixmap(ir, pm)
        else:
            p.fillRect(ir, QColor(style.BG_DEEP))
            f = p.font()
            f.setPixelSize(22)
            p.setFont(f)
            p.setPen(QColor(style.MUTED))
            p.drawText(ir, Qt.AlignCenter, "?" if locked else "★")

        right_w = 200 if r.width() > 600 else 120
        rr = QRect(r.right() - right_w - 14, r.y() + 8, right_w, r.height() - 16)
        small = QFont(p.font())
        small.setPixelSize(12)
        p.setFont(small)
        lines: list[tuple[str, str]] = []
        if ach.unlocked:
            lines.append(("Unlocked " + _date(ach.unlock_time, with_time=right_w > 150), style.TEXT))
            if ach.source in ("steam", "manual"):
                lines.append(({"steam": "imported from Steam", "manual": "unlocked by hand"}[ach.source], style.MUTED))
        elif ach.api_name in page.manual and page.tracked:
            lines.append(("unlock by hand", style.MUTED))
        if ach.global_percent is not None:
            lines.append((f"{ach.global_percent:.1f}% of players", rarity_color(ach.global_percent)))
        lh = 17
        y = rr.y() + (rr.height() - lh * len(lines)) // 2
        for text, color in lines:
            p.setPen(QColor(color))
            p.drawText(QRect(rr.x(), y, rr.width(), lh), Qt.AlignRight | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(text, Qt.ElideRight, rr.width()))
            y += lh

        secret = ach.hidden and locked and not page.reveal.isChecked()
        tx = ir.right() + 16
        tw = rr.x() - tx - 10
        title = QFont(p.font())
        title.setPixelSize(15)
        title.setBold(True)
        p.setFont(title)
        p.setPen(QColor(style.MUTED if locked else style.TEXT_BRIGHT))
        t = "Hidden achievement" if secret else ach.title
        p.drawText(QRect(tx, r.y() + 14, tw, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(t, Qt.ElideRight, tw))
        desc = QFont(p.font())
        desc.setPixelSize(13)
        desc.setBold(False)
        p.setFont(desc)
        p.setPen(QColor(style.MUTED))
        d = "Details are revealed once unlocked." if secret else (ach.description or "")
        dr = QRect(tx, r.y() + 37, tw, r.height() - 44)
        p.setClipRect(dr)
        p.drawText(dr, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, d)
        p.restore()


class AchievementList(QListView):
    context = Signal(object, object)

    def __init__(self, page: "GamePage"):
        super().__init__(page)
        self.setObjectName("AchList")
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(28)
        self.setSelectionMode(QListView.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.model_ = QStandardItemModel(self)
        self.setModel(self.model_)
        self.delegate = AchievementDelegate(page)
        self.setItemDelegate(self.delegate)

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
    reset_achievements = Signal(str, str)          # game id, "manual" | "all"
    review_saved = Signal(str, int, str)           # game id, rating, review text
    notes_saved = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game: Game | None = None
        self.achset: AchievementSet | None = None
        self.manual: dict[str, str] = {}
        self.tracked = False
        self.session_start_fn = lambda game_id: 0.0
        self._timer = QTimer(self, interval=1000, timeout=self._tick)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- banner ----
        self.hero = Hero()
        hl = QVBoxLayout(self.hero)
        hl.setContentsMargins(20, 14, 20, 14)
        backbtn = QPushButton("‹  Back")
        backbtn.setToolTip("Back to library (Esc)")
        backbtn.setCursor(Qt.PointingHandCursor)
        backbtn.setStyleSheet("QPushButton { background: rgba(0,0,0,120); color: white; padding: 6px 12px; }"
                              "QPushButton:hover { background: rgba(0,0,0,190); }")
        backbtn.clicked.connect(self.back)
        hl.addWidget(backbtn, 0, Qt.AlignLeft)
        hl.addStretch()
        outer.addWidget(self.hero)

        # ---- play bar ----
        self.playbar = QWidget()
        self.playbar.setObjectName("PlayBar")
        pb = QHBoxLayout(self.playbar)
        pb.setContentsMargins(24, 14, 24, 14)
        pb.setSpacing(18)
        self.play_btn = QPushButton("▶  PLAY")
        self.play_btn.setObjectName("Play")
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setMinimumWidth(180)
        self.play_btn.clicked.connect(lambda: self.game and self.play.emit(self.game.id))
        self.locate_btn = QPushButton("LOCATE GAME")
        self.locate_btn.setObjectName("Locate")
        self.locate_btn.setToolTip("The game's files weren't found. Point GameKeeper to their new location.")
        self.locate_btn.setCursor(Qt.PointingHandCursor)
        self.locate_btn.clicked.connect(lambda: self.game and self.edit.emit(self.game.id))
        pb.addWidget(self.play_btn)
        pb.addWidget(self.locate_btn)
        stats = QWidget()
        stats.setObjectName("StatsRow")
        stats.setStyleSheet("#StatsRow { background: transparent; }")
        self.flow = FlowLayout(stats, spacing=14)
        self.stat_last = Stat("LAST PLAYED")
        self.stat_time = Stat("PLAY TIME")
        self.stat_ach = Stat("ACHIEVEMENTS")
        self.stat_rating = Stat("YOUR RATING")
        for w in (self.stat_last, self.stat_time, self.stat_ach, self.stat_rating):
            w.setStyleSheet("#Stat { background: transparent; }")
            self.flow.addWidget(w)
        pb.addWidget(stats, 1)
        self.fav_btn = QPushButton("☆")
        self.fav_btn.setObjectName("IconButton")
        self.fav_btn.setCursor(Qt.PointingHandCursor)
        self.fav_btn.clicked.connect(lambda: self.game and self.toggle_favorite.emit(self.game.id))
        self.more_btn = QPushButton("⚙")
        self.more_btn.setObjectName("IconButton")
        self.more_btn.setToolTip("Manage")
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.clicked.connect(self._manage_menu)
        pb.addWidget(self.fav_btn, 0, Qt.AlignVCenter)
        pb.addWidget(self.more_btn, 0, Qt.AlignVCenter)
        outer.addWidget(self.playbar)

        # ---- tabs ----
        tabs = QWidget()
        tabs.setObjectName("Tabs")
        tl = QHBoxLayout(tabs)
        tl.setContentsMargins(24, 6, 24, 0)
        tl.setSpacing(0)
        self.tab_group = QButtonGroup(self)
        for i, name in enumerate(("ACHIEVEMENTS", "REVIEW", "DETAILS")):
            b = QPushButton(name)
            b.setObjectName("Tab")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.tab_group.addButton(b, i)
            tl.addWidget(b)
        tl.addStretch()
        self.tab_group.button(0).setChecked(True)
        self.tab_group.idClicked.connect(lambda i: self.pages.setCurrentIndex(i))
        outer.addWidget(tabs)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_achievements())
        self.pages.addWidget(self._build_review())
        self.pages.addWidget(self._build_details())
        outer.addWidget(self.pages, 1)

    # ------------------------------------------------------------------ #
    def _build_achievements(self) -> QWidget:
        sec = QWidget()
        sl = QVBoxLayout(sec)
        sl.setContentsMargins(24, 14, 18, 0)
        sl.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.ach_title = QLabel()
        self.ach_title.setTextFormat(Qt.RichText)
        top.addWidget(self.ach_title)
        top.addStretch()
        self.tools = QWidget()
        tl = QHBoxLayout(self.tools)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        seg_box = QWidget()
        seg_box.setObjectName("Segmented")
        sbl = QHBoxLayout(seg_box)
        sbl.setContentsMargins(3, 3, 3, 3)
        sbl.setSpacing(2)
        self.seg = QButtonGroup(self)
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
        self.bar.setFixedHeight(6)
        sl.addWidget(self.bar)
        self.notice = QLabel()
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
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
        return sec

    def _build_review(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(24, 16, 24, 24)
        v.setSpacing(14)
        card, cl = _card("YOUR RATING")
        row = QHBoxLayout()
        self.stars = StarRating(28)
        self.stars.changed.connect(self._rating_preview)
        self.rating_word = QLabel()
        self.rating_word.setStyleSheet(f"color: {style.TEXT_BRIGHT}; font-size: 16px; font-weight: 700;")
        row.addWidget(self.stars)
        row.addSpacing(14)
        row.addWidget(self.rating_word)
        row.addStretch()
        cl.addLayout(row)
        v.addWidget(card)

        card2, cl2 = _card("YOUR REVIEW")
        self.review_edit = QPlainTextEdit()
        self.review_edit.setPlaceholderText("What did you think? What stood out, what didn't, would you replay it?")
        self.review_edit.setMinimumHeight(180)
        cl2.addWidget(self.review_edit, 1)
        brow = QHBoxLayout()
        save = QPushButton("Save review")
        save.setObjectName("Primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save_review)
        clear = QPushButton("Delete review")
        clear.clicked.connect(self._delete_review)
        self.review_status = QLabel()
        self.review_status.setStyleSheet(f"color: {style.MUTED}; font-size: 12px;")
        brow.addWidget(save)
        brow.addWidget(clear)
        brow.addSpacing(10)
        brow.addWidget(self.review_status)
        brow.addStretch()
        cl2.addLayout(brow)
        v.addWidget(card2, 1)
        return scroll

    def _build_details(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(24, 16, 24, 24)
        v.setSpacing(14)
        card, cl = _card("GAME INFO")
        self.info = QFormLayout()
        self.info.setHorizontalSpacing(24)
        self.info.setVerticalSpacing(8)
        self.info_labels: dict[str, QLabel] = {}
        for key in ("Added", "First played", "Last played", "Played in GameKeeper", "Imported from Steam",
                    "Collections", "Steam app", "Executable", "Folder"):
            val = QLabel()
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lbl = QLabel(key)
            lbl.setStyleSheet(f"color: {style.MUTED};")
            self.info.addRow(lbl, val)
            self.info_labels[key] = val
        cl.addLayout(self.info)
        brow = QHBoxLayout()
        b1 = QPushButton("Open game folder")
        b1.clicked.connect(lambda: self.game and self.open_folder.emit(self.game.id))
        b2 = QPushButton("Edit game...")
        b2.clicked.connect(lambda: self.game and self.edit.emit(self.game.id))
        brow.addWidget(b1)
        brow.addWidget(b2)
        brow.addStretch()
        cl.addLayout(brow)
        v.addWidget(card)

        card2, cl2 = _card("NOTES")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Mod lists, save locations, what you were doing last time...")
        self.notes_edit.setMinimumHeight(120)
        cl2.addWidget(self.notes_edit)
        nrow = QHBoxLayout()
        nsave = QPushButton("Save notes")
        nsave.clicked.connect(lambda: self.game and self.notes_saved.emit(self.game.id, self.notes_edit.toPlainText()))
        nrow.addWidget(nsave)
        nrow.addStretch()
        cl2.addLayout(nrow)
        v.addWidget(card2)
        v.addStretch()
        return scroll

    # ------------------------------------------------------------------ #
    # responsive layout
    # ------------------------------------------------------------------ #
    def resizeEvent(self, e):
        super().resizeEvent(e)
        w, h = self.width(), self.height()
        self.hero.setFixedHeight(int(min(300, max(170, h * 0.30))))
        self.search.setVisible(w > 1000)
        self.sort.setVisible(w > 780)

    # ------------------------------------------------------------------ #
    def show_game(self, game: Game):
        changed = self.game is None or self.game.id != game.id
        self.game = game
        if changed:
            self.tab_group.button(0).setChecked(True)
            self.pages.setCurrentIndex(0)
            self.seg.button(0).setChecked(True)
            self.sort.setCurrentIndex(0)
            self.search.clear()
            self.reveal.setChecked(False)
            self.list.delegate.clear_cache()
            self.hero.set_image(game.hero_path if game.hero_path.exists() else game.cover_path)
            self.list.scrollToTop()
            self.load_review()
            self.notes_edit.setPlainText(game.notes)
        self.hero.title = game.name
        self.hero.update()
        missing = not os.path.exists(game.exe)
        self.play_btn.setVisible(not missing)
        self.locate_btn.setVisible(missing)
        self.manual = tracking.manual_only(game)
        self.tracked = bool(tracking.describe(game))
        self.refresh_stats()
        self.refresh_details()
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
        self.play_btn.setText(f"RUNNING  {_clock(int(time.time() - start))}" if start else "STARTING...")

    def refresh_stats(self):
        g = self.game
        if not g:
            return
        self.stat_last.value.setText(_date(g.last_played, with_time=False) if g.last_played else "Never")
        t = format_playtime(g.total_playtime)
        self.stat_time.value.setText(t)
        if g.achievements_total:
            self.stat_ach.value.setText(f"{g.achievements_unlocked}/{g.achievements_total}")
            self.stat_ach.bar.setMaximum(g.achievements_total)
            self.stat_ach.bar.setValue(g.achievements_unlocked)
            self.stat_ach.bar.show()
            self.stat_ach.show()
        else:
            self.stat_ach.hide()
        if g.rating:
            self.stat_rating.value.setText(f"<span style='color:{style.GOLD}'>★</span> {g.rating}/10")
            self.stat_rating.show()
        else:
            self.stat_rating.hide()
        self.fav_btn.setText("★" if g.favorite else "☆")
        self.fav_btn.setStyleSheet(f"color: {style.GOLD};" if g.favorite else "")
        self.fav_btn.setToolTip("Remove from favorites" if g.favorite else "Add to favorites")
        self.flow.invalidate()

    def refresh_details(self):
        g = self.game
        if not g:
            return
        L = self.info_labels
        L["Added"].setText(_date(g.added, with_time=False))
        L["First played"].setText(_date(g.first_played, with_time=False) if g.first_played else "Never")
        L["Last played"].setText(_date(g.last_played) if g.last_played else "Never")
        L["Played in GameKeeper"].setText(format_playtime(g.playtime))
        L["Imported from Steam"].setText(format_playtime(g.steam_playtime) if g.steam_playtime else "-")
        L["Collections"].setText(", ".join(g.categories) or "-")
        L["Steam app"].setText(str(g.appid) if g.appid else "Not linked")
        exe_ok = os.path.exists(g.exe)
        L["Executable"].setText(g.exe + ("" if exe_ok else f"  <span style='color:{style.DANGER}'>(not found)</span>"))
        L["Executable"].setTextFormat(Qt.RichText)
        L["Folder"].setText(str(g.game_dir))

    # ------------------------------------------------------------------ #
    # review
    # ------------------------------------------------------------------ #
    def load_review(self):
        g = self.game
        if not g:
            return
        self.stars.set_value(g.rating)
        self._rating_preview(g.rating)
        self.review_edit.setPlainText(g.review)
        self.review_status.setText(f"Last updated {_date(g.review_updated)}" if g.review_updated else "")

    def _rating_preview(self, v: int):
        self.rating_word.setText(f"{v}/10  ·  {RATING_WORDS[v]}" if v else "Not rated")

    def _save_review(self):
        if self.game:
            self.review_saved.emit(self.game.id, self.stars.value, self.review_edit.toPlainText().strip())

    def _delete_review(self):
        if self.game:
            self.stars.set_value(0)
            self.review_edit.clear()
            self.review_saved.emit(self.game.id, 0, "")

    # ------------------------------------------------------------------ #
    # achievements
    # ------------------------------------------------------------------ #
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
            self.empty.setText("")
            self.empty.show()      # takes up the free space so the notice stays at the top
            self.ach_title.setText(f"<span style='font-size:15px; color:{style.TEXT_BRIGHT}; font-weight:700'>Achievements</span>")
            if not g.appid:
                self._notice("This game isn't linked to Steam, so it has no achievement list. "
                             "Link it under ⚙ → Edit game if it's on Steam.", "Edit game", "edit")
            else:
                self._notice("No achievement data yet. Pull it from Steam when you're ready to start.",
                             "Pull achievements from Steam", "fetch")
            return

        pct = 100 * a.unlocked_count // a.total
        self.ach_title.setText(
            f"<span style='font-size:15px; color:{style.TEXT_BRIGHT}; font-weight:700'>Achievements</span>"
            f"<span style='color:{style.MUTED}'>&nbsp;&nbsp;You've unlocked "
            f"<b style='color:{style.TEXT}'>{a.unlocked_count}</b>/{a.total} ({pct}%)</span>")
        self.bar.setMaximum(a.total)
        self.bar.setValue(a.unlocked_count)
        if self.tracked:
            text = "Automatic unlocks: on (" + ", ".join(tracking.describe(g)) + ")."
            if self.manual:
                text += f" {len(self.manual)} marked “unlock by hand” can't be detected; right-click them when earned."
        else:
            text = "Automatic unlocks aren't set up for this game. Right-click an achievement to unlock it by hand."
        self._notice(text)

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
            items.sort(key=lambda x: not x.unlocked)
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
        act = m.addAction("Lock achievement" if ach.unlocked else "Unlock achievement")
        if m.exec(pos) == act:
            self.achievement_toggled.emit(self.game.id, ach.api_name, not ach.unlocked)

    def _manage_menu(self):
        g = self.game
        if not g:
            return
        m = QMenu(self)
        m.addAction("Edit game...", lambda: self.edit.emit(g.id))
        m.addAction("Open game folder", lambda: self.open_folder.emit(g.id))
        m.addSeparator()
        a1 = m.addAction("Pull / refresh Steam data", lambda: self.fetch_data.emit(g.id))
        a2 = m.addAction("Import my unlocks and playtime from Steam", lambda: self.import_steam.emit(g.id))
        a1.setEnabled(bool(g.appid))
        a2.setEnabled(bool(g.appid))
        m.addSeparator()
        r1 = m.addAction("Lock achievements unlocked by hand...", lambda: self.reset_achievements.emit(g.id, "manual"))
        r2 = m.addAction("Lock all achievements...", lambda: self.reset_achievements.emit(g.id, "all"))
        has = bool(g.achievements_unlocked)
        r1.setEnabled(has)
        r2.setEnabled(has)
        m.addSeparator()
        m.addAction("Remove from library...", lambda: self.remove.emit(g.id))
        m.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))
