"""Main window: sidebar with lists, the library grid and the game page."""
from __future__ import annotations

import os
import subprocess
import sys
import time

from PySide6.QtCore import QByteArray, QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGraphicsOpacityEffect, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QApplication, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QSlider, QStackedWidget,
    QStyle, QSystemTrayIcon,
    QStyledItemDelegate, QVBoxLayout, QWidget,
)

from .. import backup, shortcut, steam, tracking
from ..runner import GameSession
from ..storage import AchievementSet, Game, Library, Settings
from . import style
from .dialogs import AddGameDialog, ArchiveDialog, EditGameDialog, SettingsDialog
from .game_page import GamePage
from .icon import app_icon, app_pixmap
from .library_view import LibraryView, icon_pixmap
from .toast import ToastManager
from .workers import run_async

ALL, FAVORITES, RECENT, UNCATEGORIZED = "__all__", "__fav__", "__recent__", "__none__"
SORTS = ["Name", "Recently played", "Most played", "Recently added", "Achievement progress", "Your rating"]
ROLE_COUNT = Qt.UserRole + 2


class SidebarDelegate(QStyledItemDelegate):
    """Sidebar entry with its game count right-aligned."""

    def paint(self, p, option, index):
        super().paint(p, option, index)
        n = index.data(ROLE_COUNT)
        if n is None:
            return
        p.save()
        selected = bool(option.state & QStyle.State_Selected)
        p.setPen(QColor("white" if selected else style.MUTED))
        f = p.font()
        f.setPixelSize(11)
        p.setFont(f)
        r = option.rect.adjusted(0, 0, -22, 0)
        p.drawText(r, Qt.AlignRight | Qt.AlignVCenter, str(n))
        p.restore()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GameKeeper")
        self.resize(1280, 820)
        self.setMinimumSize(820, 560)
        self.library = Library()
        self.settings = Settings.load()
        self.sessions: dict[str, GameSession] = {}
        self.toasts = ToastManager()
        self._apply_settings()
        self.current_filter = ALL
        self._art_checked: set[str] = set()

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_topbar())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_library_page())
        self.page = GamePage()
        self._wire_game_page()
        self.stack.addWidget(self.page)
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        self.page.session_start_fn = lambda gid: self.sessions[gid].started_at if gid in self.sessions else 0.0
        self.grid.set_cover_size(self.settings.cover_size)
        self.cover_slider.setValue(self.settings.cover_size)
        self.refresh_sidebar()
        self.refresh_grid()
        self._shortcuts()
        self._build_tray()
        if self.settings.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.settings.window_geometry.encode()))
        settings = self.settings
        run_async(lambda: backup.backup_if_due(settings))
        if shortcut.supported() and not self.settings.shortcut_offered:
            QTimer.singleShot(800, self._offer_shortcut)

    def _shortcuts(self):
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("Ctrl+N"), self, self.add_game)
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self._escape)
        QShortcut(QKeySequence(Qt.Key_Backspace), self, self._escape)

    def _focus_search(self):
        if self.stack.currentIndex() == 1:
            self.page.search.setFocus()
        else:
            self.search.setFocus()
            self.search.selectAll()

    def _escape(self):
        if self.focusWidget() in (self.search, self.page.search) and self.focusWidget().text():
            self.focusWidget().clear()
        elif self.stack.currentIndex() == 1:
            self.show_library()

    def _offer_shortcut(self):
        self.settings.shortcut_offered = True
        self.settings.save()
        if QMessageBox.question(
                self, "Desktop shortcut",
                "Create a GameKeeper shortcut on your desktop?\n\n"
                "You can also do this later in Settings.") == QMessageBox.Yes:
            from .icon import ico_file
            try:
                path = shortcut.create("desktop", ico_file())
                self.statusBar().showMessage(f"Shortcut created: {path}", 8000)
            except shortcut.ShortcutError as e:
                QMessageBox.warning(self, "Shortcut", str(e))

    def _switch_page(self, index: int):
        """Change page with a quick fade-in."""
        if self.stack.currentIndex() == index:
            return
        self.stack.setCurrentIndex(index)
        w = self.stack.currentWidget()
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", w)
        anim.setDuration(160)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: w.setGraphicsEffect(None))   # effects slow painting; drop it after
        anim.start()
        self._page_anim = anim

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w = self.width()
        self.sidebar.setFixedWidth(260 if w > 1100 else 210)
        self.sort.setVisible(w > 900)
        self.cover_slider.setVisible(w > 1000)
        self.size_icon.setVisible(w > 1000)

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(6)
        logo = QLabel()
        logo.setPixmap(app_pixmap(26))
        h.addWidget(logo)
        mark = QLabel("GAMEKEEPER")
        mark.setObjectName("Wordmark")
        h.addWidget(mark)
        h.addSpacing(26)
        self.nav: dict[str, QPushButton] = {}
        for key, label, slot in (("library", "LIBRARY", self.show_library),
                                 ("archive", "ARCHIVE", self.open_archive),
                                 ("settings", "SETTINGS", self.open_settings)):
            b = QPushButton(label)
            b.setObjectName("NavLink")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot)
            self.nav[key] = b
            h.addWidget(b)
        self.nav["library"].setProperty("active", True)
        h.addStretch()
        add = QPushButton("+  ADD GAME")
        add.setObjectName("Primary")
        add.setToolTip("Add a game (Ctrl+N)")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self.add_game)
        h.addWidget(add)
        return bar

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(260)
        self.sidebar = side
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_grid)
        v.addWidget(self.search)

        self.views = QListWidget()
        self.views.setObjectName("SideList")
        self.views.setItemDelegate(SidebarDelegate(self.views))
        self.views.setCursor(Qt.PointingHandCursor)
        self.views.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.views.itemClicked.connect(lambda it: self._select_filter(it.data(Qt.UserRole), self.views))
        v.addWidget(self.views)

        row = QHBoxLayout()
        row.setSpacing(0)
        lbl2 = QLabel("COLLECTIONS")
        lbl2.setObjectName("SectionLabel")
        row.addWidget(lbl2)
        row.addStretch()
        add = QPushButton("+")
        add.setObjectName("AddCategory")
        add.setToolTip("New collection")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self.new_category)
        row.addWidget(add)
        v.addLayout(row)
        self.cats = QListWidget()
        self.cats.setObjectName("SideList")
        self.cats.setItemDelegate(SidebarDelegate(self.cats))
        self.cats.setCursor(Qt.PointingHandCursor)
        self.cats.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cats.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cats.customContextMenuRequested.connect(self._category_menu)
        self.cats.itemClicked.connect(lambda it: self._select_filter(it.data(Qt.UserRole), self.cats))
        v.addWidget(self.cats)

        self.games_label = QLabel("GAMES")
        self.games_label.setObjectName("SectionLabel")
        v.addWidget(self.games_label)
        self.game_list = QListWidget()
        self.game_list.setObjectName("SideList")
        self.game_list.setIconSize(QSize(24, 24))
        self.game_list.setCursor(Qt.PointingHandCursor)
        self.game_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_list.customContextMenuRequested.connect(
            lambda pos: (it := self.game_list.itemAt(pos)) and self._game_menu(
                it.data(Qt.UserRole), self.game_list.viewport().mapToGlobal(pos)))
        self.game_list.itemClicked.connect(lambda it: self.open_game(it.data(Qt.UserRole)))
        v.addWidget(self.game_list, 1)
        return side

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 18, 16, 0)
        v.setSpacing(12)
        top = QHBoxLayout()
        self.heading = QLabel("ALL GAMES")
        self.heading.setStyleSheet(f"font-size: 14px; font-weight: 700; letter-spacing: 1px; color: {style.TEXT_BRIGHT};")
        self.count = QLabel()
        self.count.setStyleSheet(f"color: {style.MUTED}; font-size: 14px;")
        top.addWidget(self.heading)
        top.addWidget(self.count)
        top.addStretch()
        self.sort = QComboBox()
        self.sort.addItems(SORTS)
        self.sort.setToolTip("Sort by")
        self.sort.currentIndexChanged.connect(self.refresh_grid)
        self.size_icon = QLabel("SIZE")
        self.size_icon.setStyleSheet(f"color: {style.MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        self.cover_slider = QSlider(Qt.Horizontal)
        self.cover_slider.setRange(110, 240)
        self.cover_slider.setFixedWidth(110)
        self.cover_slider.setToolTip("Cover size")
        self.cover_slider.valueChanged.connect(self._cover_size_changed)
        top.addWidget(self.size_icon)
        top.addWidget(self.cover_slider)
        top.addSpacing(14)
        sort_lbl = QLabel("SORT BY")
        sort_lbl.setStyleSheet(f"color: {style.MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        self.sort_label = sort_lbl
        top.addWidget(sort_lbl)
        top.addWidget(self.sort)
        v.addLayout(top)
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {style.BORDER};")
        v.addWidget(line)

        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(f"color: {style.MUTED}; font-size: 15px;")
        v.addWidget(self.empty, 1)
        self.grid = LibraryView()
        self.grid.open_game.connect(self.open_game)
        self.grid.context_requested.connect(self._game_menu)
        v.addWidget(self.grid, 1)
        return page

    def _wire_game_page(self):
        p = self.page
        p.back.connect(self.show_library)
        p.play.connect(self.play)
        p.edit.connect(self.edit_game)
        p.fetch_data.connect(self.fetch_steam_data)
        p.import_steam.connect(self.import_steam)
        p.remove.connect(self.remove_game)
        p.toggle_favorite.connect(self.toggle_favorite)
        p.open_folder.connect(self.open_folder)
        p.achievement_toggled.connect(self.set_achievement)
        p.achievements_set.connect(self.set_achievements)
        p.achievements_excluded.connect(self.exclude_achievements)
        p.achievements_deleted.connect(self.delete_achievements)
        p.restore_deleted.connect(self.restore_deleted)
        p.reset_achievements.connect(self.reset_achievements)
        p.review_saved.connect(self.save_review)
        p.notes_saved.connect(self.save_notes)
        p.set_artwork.connect(self.set_artwork)
        p.reset_artwork.connect(self.reset_artwork)

    # ------------------------------------------------------------------ #
    # sidebar + grid
    # ------------------------------------------------------------------ #
    def refresh_sidebar(self):
        games = self.library.games
        self.views.clear()
        for key, label, n in (
            (ALL, "All games", len(games)),
            (FAVORITES, "Favorites", sum(g.favorite for g in games)),
            (RECENT, "Recently played", sum(1 for g in games if g.last_played)),
            (UNCATEGORIZED, "Uncategorized", sum(1 for g in games if not g.categories)),
        ):
            it = QListWidgetItem(label)
            it.setData(ROLE_COUNT, n)
            it.setData(Qt.UserRole, key)
            it.setSizeHint(QSize(0, 30))
            self.views.addItem(it)
        self.views.setFixedHeight(self.views.count() * 30 + 4)
        self.cats.clear()
        for c in self.library.categories:
            n = sum(1 for g in games if c in g.categories)
            it = QListWidgetItem(c)
            it.setData(ROLE_COUNT, n)
            it.setData(Qt.UserRole, c)
            it.setSizeHint(QSize(0, 30))
            self.cats.addItem(it)
        if not self.library.categories:
            it = QListWidgetItem("Click + to make one")
            it.setFlags(Qt.NoItemFlags)
            it.setForeground(QColor(style.MUTED))
            it.setSizeHint(QSize(0, 30))
            self.cats.addItem(it)
        self.cats.setFixedHeight(min(self.cats.count(), 8) * 30 + 4)
        for lst in (self.views, self.cats):
            for i in range(lst.count()):
                if lst.item(i).data(Qt.UserRole) == self.current_filter:
                    lst.setCurrentRow(i)

    def refresh_game_list(self, games: list[Game]):
        """The compact list of games in the sidebar, like Steam's library list."""
        self.game_list.clear()
        current = self.page.game.id if self.stack.currentIndex() == 1 and self.page.game else None
        for g in sorted(games, key=lambda g: g.name.lower()):
            it = QListWidgetItem(QIcon(icon_pixmap(g, 24)), g.name)
            it.setData(Qt.UserRole, g.id)
            it.setSizeHint(QSize(0, 34))
            if g.id in self.sessions:
                it.setText(f"{g.name}  -  Running")
                it.setForeground(QColor(style.GREEN))
            elif getattr(g, "missing", False):
                it.setForeground(QColor(style.MUTED))
                it.setToolTip("Game files not found")
            self.game_list.addItem(it)
            if g.id == current:
                it.setSelected(True)
        self.games_label.setText(f"GAMES ({len(games)})")

    def _select_filter(self, key: str, source: QListWidget):
        other = self.cats if source is self.views else self.views
        other.clearSelection()
        other.setCurrentRow(-1)
        self.current_filter = key
        self.show_library()
        self.refresh_grid()

    def _filtered(self) -> list[Game]:
        f = self.current_filter
        games = self.library.games
        if f == FAVORITES:
            games = [g for g in games if g.favorite]
        elif f == RECENT:
            games = sorted((g for g in games if g.last_played), key=lambda g: -g.last_played)[:30]
        elif f == UNCATEGORIZED:
            games = [g for g in games if not g.categories]
        elif f != ALL:
            games = [g for g in games if f in g.categories]
        q = self.search.text().strip().lower()
        if q:
            games = [g for g in games if q in g.name.lower()]
        sort = self.sort.currentText()
        if f == RECENT and sort == "Name":
            return games
        key = {
            "Name": lambda g: g.name.lower(),
            "Recently played": lambda g: -g.last_played,
            "Most played": lambda g: -g.total_playtime,
            "Recently added": lambda g: -g.added,
            "Achievement progress": lambda g: -(g.achievements_unlocked / g.achievements_total if g.achievements_total else -1),
            "Your rating": lambda g: (-g.rating, g.name.lower()),
        }[sort]
        return sorted(games, key=key)

    def refresh_grid(self):
        names = {ALL: "All games", FAVORITES: "Favorites", RECENT: "Recently played", UNCATEGORIZED: "Uncategorized"}
        self.heading.setText(names.get(self.current_filter, self.current_filter).upper())
        for g in self.library.games:     # flag games whose files are gone (shown greyed out)
            g.missing = not os.path.exists(g.exe)
        games = self._filtered()
        self.grid.set_games(games)
        self.refresh_game_list(games)
        self.count.setText(f"({len(games)})")
        if not self.library.games:
            self.empty.setText("Your library is empty.\nClick  \u201c+ ADD GAME\u201d  at the top and pick a game's folder to get started.")
        elif not games:
            self.empty.setText("No games here yet.\nRight-click a game to add it to a collection.")
        self.empty.setVisible(not games)
        self.grid.setVisible(bool(games))

    def _cover_size_changed(self, w: int):
        self.grid.set_cover_size(w)
        self.refresh_grid()
        self.settings.cover_size = w
        self._save_settings_later()

    def _save_settings_later(self):
        if not hasattr(self, "_save_timer"):
            self._save_timer = QTimer(self, singleShot=True, interval=800, timeout=self.settings.save)
        self._save_timer.start()

    def show_library(self):
        self._switch_page(0)
        self.refresh_grid()
        self.game_list.clearSelection()

    def open_game(self, game_id: str):
        g = self.library.get(game_id)
        if not g:
            return
        self.page.show_game(g)
        self._update_running_ui()
        self._switch_page(1)
        for i in range(self.game_list.count()):
            it = self.game_list.item(i)
            it.setSelected(it.data(Qt.UserRole) == game_id)
        if game_id not in self.sessions:
            self._sync_unlocks_async(g)
        self._fill_missing_artwork(g)

    def _refresh_game(self, g: Game):
        """Re-render whatever is showing this game."""
        self.library.save()
        self.refresh_sidebar()
        if self.stack.currentIndex() == 1 and self.page.game and self.page.game.id == g.id:
            self.page.show_game(g)
        else:
            self.grid.viewport().update()
            self.refresh_grid()

    # ------------------------------------------------------------------ #
    # categories
    # ------------------------------------------------------------------ #
    def new_category(self):
        name, ok = QInputDialog.getText(self, "New collection", "Name (e.g. Retro, Emulated, Backlog):")
        if ok and name.strip():
            if not self.library.add_category(name):
                QMessageBox.information(self, "New collection", "A collection with that name already exists.")
            self.refresh_sidebar()

    def _category_menu(self, pos):
        it = self.cats.itemAt(pos)
        if not it or it.data(Qt.UserRole) is None:
            m = QMenu(self)
            m.addAction("New collection...", self.new_category)
            m.exec(self.cats.viewport().mapToGlobal(pos))
            return
        name = it.data(Qt.UserRole)
        m = QMenu(self)
        ren = m.addAction("Rename...")
        dele = m.addAction("Delete collection")
        act = m.exec(self.cats.viewport().mapToGlobal(pos))
        if act == ren:
            new, ok = QInputDialog.getText(self, "Rename collection", "New name:", text=name)
            if ok and self.library.rename_category(name, new):
                if self.current_filter == name:
                    self.current_filter = new.strip()
        elif act == dele:
            if QMessageBox.question(self, "Delete collection",
                                    f"Delete '{name}'? The games stay in your library.") == QMessageBox.Yes:
                self.library.delete_category(name)
                if self.current_filter == name:
                    self.current_filter = ALL
        self._art_checked: set[str] = set()
        self.refresh_sidebar()
        self.refresh_grid()

    def _game_menu(self, game_id: str, pos):
        g = self.library.get(game_id)
        if not g:
            return
        m = QMenu(self)
        m.addAction("▶  Play", lambda: self.play(g.id)).setEnabled(g.id not in self.sessions)
        m.addAction("Open", lambda: self.open_game(g.id))
        m.addSeparator()
        cm = m.addMenu("Collections")
        for c in self.library.categories:
            a = cm.addAction(c)
            a.setCheckable(True)
            a.setChecked(c in g.categories)
            a.toggled.connect(lambda on, c=c: self._set_category(g, c, on))
        if self.library.categories:
            cm.addSeparator()
        cm.addAction("New collection...", lambda: self._new_category_for(g))
        m.addAction("Unfavorite" if g.favorite else "Add to favorites", lambda: self.toggle_favorite(g.id))
        m.addAction("Edit...", lambda: self.edit_game(g.id))
        m.addSeparator()
        m.addAction("Remove from library...", lambda: self.remove_game(g.id))
        m.exec(pos)

    def _set_category(self, g: Game, cat: str, on: bool):
        if on and cat not in g.categories:
            g.categories.append(cat)
        elif not on and cat in g.categories:
            g.categories.remove(cat)
        self.library.save()
        self.refresh_sidebar()
        self.refresh_grid()

    def _new_category_for(self, g: Game):
        name, ok = QInputDialog.getText(self, "New collection", "Name:")
        if ok and name.strip():
            self.library.add_category(name)
            self._set_category(g, name.strip(), True)

    # ------------------------------------------------------------------ #
    # games
    # ------------------------------------------------------------------ #
    def add_game(self):
        cat = self.current_filter if self.current_filter in self.library.categories else None
        dlg = AddGameDialog(self.library, cat, self)
        if not dlg.exec() or not dlg.game:
            return
        g = dlg.game
        self.library.add(g)
        self.refresh_sidebar()
        self.refresh_grid()
        self.open_game(g.id)
        if dlg.fetch_now:
            self.fetch_steam_data(g.id)

    def edit_game(self, game_id: str):
        g = self.library.get(game_id)
        if not g:
            return
        dlg = EditGameDialog(g, self.library, self)
        if dlg.exec():
            self._refresh_game(g)
            if dlg.appid_changed and g.appid:
                if QMessageBox.question(self, "Steam link changed",
                                        "Pull cover art and achievements for the new Steam link now?") == QMessageBox.Yes:
                    self.fetch_steam_data(g.id)

    def toggle_favorite(self, game_id: str):
        g = self.library.get(game_id)
        if g:
            g.favorite = not g.favorite
            self._refresh_game(g)

    def remove_game(self, game_id: str):
        g = self.library.get(game_id)
        if not g:
            return
        if QMessageBox.question(
                self, "Remove game",
                f"Remove '{g.name}' from the library?\n\nIts playtime, achievements, rating and review are "
                "kept in the archive (sidebar \u2192 Archived games), so you can restore it any time. "
                "The game's own files are not touched.") != QMessageBox.Yes:
            return
        self.library.remove(g)
        self.refresh_sidebar()
        self.show_library()
        self.statusBar().showMessage(f"{g.name} moved to the archive.", 8000)

    def save_review(self, game_id: str, rating: int, text: str):
        g = self.library.get(game_id)
        if not g:
            return
        g.rating, g.review = rating, text
        g.review_updated = int(time.time()) if (rating or text) else 0
        self.library.save()
        if self.page.game and self.page.game.id == g.id:
            self.page.refresh_stats()
            self.page.load_review()
        self.grid.viewport().update()
        self.statusBar().showMessage("Review saved." if (rating or text) else "Review deleted.", 5000)

    def _fill_missing_artwork(self, g: Game):
        """Quietly download any artwork a Steam-linked game is missing (once per run)."""
        if not g.appid or g.id in self._art_checked:
            return
        self._art_checked.add(g.id)
        if all(g.art_path(k).exists() or k in g.custom_art for k in ("cover", "hero", "logo", "icon")):
            return
        run_async(lambda: steam.download_artwork(g), lambda got: got and self._artwork_changed(g))

    def _artwork_changed(self, g: Game):
        self.refresh_grid()
        if self.page.game and self.page.game.id == g.id:
            self.page.show_game(g)

    def set_artwork(self, game_id: str, kind: str):
        g = self.library.get(game_id)
        if not g:
            return
        names = {"cover": "cover (portrait, e.g. 600x900)", "hero": "background (wide)",
                 "logo": "logo (ideally a transparent PNG)", "icon": "icon (square)"}
        path, _ = QFileDialog.getOpenFileName(self, f"Choose a {names[kind]}", "",
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Artwork", "That file couldn't be opened as an image.")
            return
        g.folder.mkdir(parents=True, exist_ok=True)
        dest = g.art_path(kind)
        img.save(str(dest), "PNG" if dest.suffix == ".png" else "JPG", 92)
        if kind not in g.custom_art:
            g.custom_art.append(kind)
        self.library.save()
        self._artwork_changed(g)

    def reset_artwork(self, game_id: str):
        g = self.library.get(game_id)
        if not g:
            return
        kinds, g.custom_art = list(g.custom_art), []
        for k in kinds:
            g.art_path(k).unlink(missing_ok=True)
        self.library.save()
        run_async(lambda: steam.download_artwork(g), lambda _: self._artwork_changed(g))

    def save_notes(self, game_id: str, notes: str):
        g = self.library.get(game_id)
        if g:
            g.notes = notes
            self.library.save()
            self.statusBar().showMessage("Notes saved.", 4000)

    def open_archive(self):
        dlg = ArchiveDialog(self.library, self)
        dlg.exec()
        if dlg.restored:
            self.refresh_sidebar()
            self.refresh_grid()
            self.statusBar().showMessage(f"Restored {len(dlg.restored)} game(s).", 6000)

    def reset_achievements(self, game_id: str, which: str):
        """which: 'manual' = only those unlocked by hand, 'all' = everything."""
        g = self.library.get(game_id)
        if not g:
            return
        achset = AchievementSet(g.id)
        targets = [a for a in achset.items if a.unlocked and (which == "all" or a.source == "manual")]
        if not targets:
            QMessageBox.information(self, "Reset achievements",
                                    "No achievements unlocked by hand." if which == "manual" else "Nothing is unlocked.")
            return
        if which == "manual":
            text = (f"Lock the {len(targets)} achievement(s) you unlocked by hand in {g.name}?\n\n"
                    "Automatic unlocks and ones imported from Steam stay.")
        else:
            text = (f"Lock all {len(targets)} unlocked achievement(s) in {g.name}?\n\n"
                    "Achievements the game's saves still show as earned will unlock again "
                    "the next time GameKeeper checks them.")
        if QMessageBox.question(self, "Reset achievements", text) != QMessageBox.Yes:
            return
        for a in targets:
            achset.lock(a.api_name)
        achset.save()
        self._update_counts(g, achset)
        self._refresh_game(g)
        self.statusBar().showMessage(f"Locked {len(targets)} achievement(s).", 6000)

    def open_folder(self, game_id: str):
        g = self.library.get(game_id)
        if not g:
            return
        path = str(g.game_dir)
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    # ------------------------------------------------------------------ #
    # playing
    # ------------------------------------------------------------------ #
    def play(self, game_id: str):
        g = self.library.get(game_id)
        if not g or game_id in self.sessions:
            return
        if not os.path.exists(g.exe):
            QMessageBox.warning(self, "Can't start game",
                                f"The executable wasn't found:\n{g.exe}\n\nUse Edit to point to its new location.")
            return
        self._sync_unlocks(g)
        now = int(time.time())
        g.last_played = now
        g.first_played = g.first_played or now
        self.library.save()
        s = GameSession(g, self)
        s.checkpoint.connect(self._on_checkpoint)
        s.unlocked.connect(self._on_unlock)
        s.ended.connect(self._on_ended)
        s.failed.connect(self._on_failed)
        s.needs_admin.connect(self._on_needs_admin)
        s.cancelled.connect(self._on_cancelled)
        self.sessions[game_id] = s
        s.start()
        self._update_running_ui()
        self.statusBar().showMessage(f"Playing {g.name}...")

    def _on_checkpoint(self, game_id: str, secs: int):
        g = self.library.get(game_id)
        if g:
            g.playtime += secs
            self.library.save()

    def _on_ended(self, game_id: str, secs: int):
        s = self.sessions.pop(game_id, None)
        g = self.library.get(game_id)
        if g:
            g.playtime += secs
            g.last_played = int(time.time())
            self._refresh_game(g)
            session_len = int(time.time() - s.started_at) if s else secs
            self.statusBar().showMessage(f"Finished {g.name} - played {session_len // 60} min this session.", 10000)
        self._update_running_ui()

    def _update_running_ui(self):
        self._update_tray_tooltip()
        self.grid.running = set(self.sessions)
        self.grid.viewport().update()
        self.refresh_game_list(self._filtered())
        if self.page.game:
            self.page.set_running(self.page.game.id in self.sessions)

    def _on_failed(self, game_id: str, msg: str):
        self.sessions.pop(game_id, None)
        self._update_running_ui()
        QMessageBox.warning(self, "Can't start game", msg)

    def _on_needs_admin(self, game_id: str):
        self.sessions.pop(game_id, None)
        self._update_running_ui()
        g = self.library.get(game_id)
        if not g:
            return
        if QMessageBox.question(
                self, "Administrator rights needed",
                f"{g.name} asks to be run as administrator.\n\n"
                "Start it as administrator? Windows will ask for permission each time. "
                "This is remembered for this game (change it under Edit).") == QMessageBox.Yes:
            g.run_as_admin = True
            self.library.save()
            self.play(game_id)

    def _on_cancelled(self, game_id: str):
        self.sessions.pop(game_id, None)
        self._update_running_ui()
        self.statusBar().showMessage("Launch cancelled.", 6000)

    def _on_unlock(self, game_id: str, api_name: str, when: int):
        g = self.library.get(game_id)
        if not g:
            return
        achset = AchievementSet(game_id)
        ach = achset.unlock(api_name, when, source="auto")
        if not ach:
            return
        achset.save()
        self._update_counts(g, achset)
        if not ach.excluded:     # still recorded, but no popup for achievements you excluded
            self.toasts.show(ach.title, g.name, achset.icon_path(ach))
        self._refresh_game(g)

    def exclude_achievements(self, game_id: str, names: list, excluded: bool):
        g = self.library.get(game_id)
        if not g:
            return
        achset = AchievementSet(game_id)
        n = achset.set_excluded(names, excluded)
        if not n:
            return
        achset.save()
        self._update_counts(g, achset)
        self._refresh_game(g)
        self.statusBar().showMessage(
            f"Excluded {n} achievement(s). Find them under the Excluded filter." if excluded
            else f"Included {n} achievement(s) again.", 7000)

    def delete_achievements(self, game_id: str, names: list):
        g = self.library.get(game_id)
        if not g or not names:
            return
        n = len(names)
        if QMessageBox.question(
                self, "Delete permanently",
                f"Permanently delete {n} achievement(s) from {g.name}?\n\n"
                "They disappear from the list and your progress, and won't come back when "
                "refreshing data from Steam.") != QMessageBox.Yes:
            return
        achset = AchievementSet(game_id)
        achset.delete(names)
        achset.save()
        self._update_counts(g, achset)
        self._refresh_game(g)
        self.statusBar().showMessage(f"Deleted {n} achievement(s) from {g.name}.", 7000)

    def restore_deleted(self, game_id: str):
        g = self.library.get(game_id)
        if not g:
            return
        achset = AchievementSet(game_id)
        n = len(achset.deleted)
        if not n or QMessageBox.question(
                self, "Restore deleted achievements",
                f"Bring back the {n} achievement(s) you deleted from {g.name}?\n\n"
                "They're downloaded from Steam again.") != QMessageBox.Yes:
            return
        achset.deleted = []
        achset.save()
        self.fetch_steam_data(g.id)

    def set_achievements(self, game_id: str, names: list, unlocked: bool):
        g = self.library.get(game_id)
        if not g:
            return
        achset = AchievementSet(game_id)
        for name in names:
            if unlocked:
                achset.unlock(name, source="manual")
            else:
                achset.lock(name)
        achset.save()
        self._update_counts(g, achset)
        self._refresh_game(g)

    def set_achievement(self, game_id: str, api_name: str, unlocked: bool):
        g = self.library.get(game_id)
        if not g:
            return
        achset = AchievementSet(game_id)
        if unlocked:
            achset.unlock(api_name, source="manual")
        else:
            achset.lock(api_name)
        achset.save()
        self._update_counts(g, achset)
        self._refresh_game(g)

    def _sync_unlocks_async(self, g: Game):
        """Check the game's saves in the background, then apply any new unlocks."""
        if not tracking.describe(g):
            return
        run_async(lambda: tracking.read_unlocks(g), lambda found: self._apply_unlocks(g, found))

    def _apply_unlocks(self, g: Game, found: dict, refresh: bool = True):
        achset = AchievementSet(g.id)
        if not achset.total:
            return
        changed = False
        for name, when in found.items():
            changed |= achset.unlock(name, when or None, source="auto") is not None
        if changed:
            achset.save()
            self._update_counts(g, achset)
            if refresh:
                self._refresh_game(g)
            else:
                self.library.save()

    def _sync_unlocks(self, g: Game, refresh: bool = True):
        """Quietly import unlocks made while GameKeeper wasn't watching
        (e.g. progress from before the game was added)."""
        if tracking.describe(g):
            self._apply_unlocks(g, tracking.read_unlocks(g), refresh)

    @staticmethod
    def _update_counts(g: Game, achset: AchievementSet):
        g.achievements_total = achset.total
        g.achievements_unlocked = achset.unlocked_count

    # ------------------------------------------------------------------ #
    # steam
    # ------------------------------------------------------------------ #
    def fetch_steam_data(self, game_id: str):
        g = self.library.get(game_id)
        if not g or not g.appid:
            return
        self.statusBar().showMessage(f"Pulling Steam data for {g.name}...")
        settings = self.settings

        def job(progress):
            steam.download_artwork(g, force=True)
            try:
                achset = steam.fetch_achievements(g, settings, progress)
                return achset.total, achset.unlocked_count, None
            except steam.SteamError as e:
                return 0, 0, str(e)

        def done(result):
            total, unlocked, err = result
            if total:
                g.achievements_total, g.achievements_unlocked = total, unlocked
            self._sync_unlocks(g, refresh=False)
            self._refresh_game(g)
            msg = f"{g.name}: cover art updated" + (f", {total} achievements." if total else ".")
            self.statusBar().showMessage(msg, 8000)
            if err:
                QMessageBox.information(self, "Achievements", err)

        def progress(d, t):
            self.statusBar().showMessage(f"Downloading achievement icons for {g.name}... {d}/{t}")

        run_async(job, done, lambda e: self._error("Couldn't pull Steam data", e), progress)

    def import_steam(self, game_id: str):
        g = self.library.get(game_id)
        if not g:
            return
        self.statusBar().showMessage("Importing from Steam...")
        settings = self.settings

        def done(result):
            new, playtime = result
            g.steam_playtime = playtime
            achset = AchievementSet(g.id)
            self._update_counts(g, achset)
            self._refresh_game(g)
            self.statusBar().clearMessage()
            QMessageBox.information(
                self, "Imported from Steam",
                f"{len(new)} achievement(s) newly marked as unlocked.\n"
                f"Steam playtime: {playtime // 3600} h {playtime % 3600 // 60} min "
                "(shown on top of time played here).")

        run_async(lambda: steam.import_progress(g, settings), done,
                  lambda e: self._error("Import failed", e))

    # ------------------------------------------------------------------ #
    def open_settings(self):
        def test(sound, secs):
            old = (self.toasts.enabled_sound, self.toasts.seconds)
            self.toasts.enabled_sound, self.toasts.seconds = sound, secs
            self.toasts.show("Test achievement", "This is how unlocks will look")
            self.toasts.enabled_sound, self.toasts.seconds = old

        if SettingsDialog(self.settings, self, test_popup=test).exec():
            self._apply_settings()

    def _apply_settings(self):
        self.toasts.enabled_sound = self.settings.toast_sound
        self.toasts.seconds = self.settings.toast_seconds

    def _error(self, title: str, msg: str):
        self.statusBar().clearMessage()
        QMessageBox.warning(self, title, msg)

    # ------------------------------------------------------------------ #
    # system tray
    # ------------------------------------------------------------------ #
    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("GameKeeper")
        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(self._fill_tray_menu)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _fill_tray_menu(self):
        m = self.tray_menu
        m.clear()
        m.addAction("Open GameKeeper", self.bring_to_front)
        recent = sorted((g for g in self.library.games if g.last_played), key=lambda g: -g.last_played)[:6]
        if recent:
            m.addSeparator()
            head = m.addAction("PLAY")
            head.setEnabled(False)
            for g in recent:
                label = f"{g.name}  (running)" if g.id in self.sessions else g.name
                a = m.addAction(QIcon(icon_pixmap(g, 16)), label, lambda gid=g.id: self.play(gid))
                a.setEnabled(g.id not in self.sessions)
        m.addSeparator()
        m.addAction("Quit GameKeeper", self.quit_app)

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.bring_to_front()

    def bring_to_front(self):
        self.show()
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.raise_()
        self.activateWindow()

    def _update_tray_tooltip(self):
        if self.tray:
            names = [self.library.get(i).name for i in self.sessions if self.library.get(i)]
            self.tray.setToolTip("GameKeeper" + (f" - playing {', '.join(names)}" if names else ""))

    def quit_app(self):
        self._quitting = True
        self.close()

    def closeEvent(self, e):
        self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode()
        self.settings.save()
        if self.tray and self.settings.close_to_tray and not getattr(self, "_quitting", False):
            e.ignore()
            self.hide()
            if not self.settings.tray_hint_shown:
                self.settings.tray_hint_shown = True
                self.settings.save()
                self.tray.showMessage("GameKeeper is still running",
                                      "It keeps tracking your games from the tray. Right-click the "
                                      "tray icon to quit.", app_icon(), 6000)
            return
        if self.sessions:
            names = ", ".join(self.library.get(i).name for i in self.sessions if self.library.get(i))
            if QMessageBox.question(
                    self, "Game still running",
                    f"{names} is still running. Quitting GameKeeper stops tracking its playtime "
                    "and achievements for this session.\n\nQuit anyway?") != QMessageBox.Yes:
                e.ignore()
                self._quitting = False
                return
            for gid, s in self.sessions.items():
                s.blockSignals(True)
                s.stop_tracking()
                s.wait(3000)
                g = self.library.get(gid)
                if g and s.last_checkpoint:   # keep the time since the last checkpoint
                    g.playtime += int(time.time() - s.last_checkpoint)
        self.library.save()
        e.accept()
        if self.tray:
            self.tray.hide()
        QApplication.quit()
