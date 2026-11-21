"""Main window: sidebar with lists, the library grid and the game page."""
from __future__ import annotations

import os
import subprocess
import sys
import time

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import emulator, steam, tracking
from ..runner import GameSession
from ..storage import AchievementSet, Game, Library, Settings
from . import style
from .dialogs import AddGameDialog, EditGameDialog, SettingsDialog
from .game_page import GamePage
from .library_view import LibraryView
from .toast import ToastManager
from .workers import run_async

ALL, FAVORITES, RECENT, UNCATEGORIZED = "__all__", "__fav__", "__recent__", "__none__"
SORTS = ["Name", "Recently played", "Most played", "Recently added", "Achievement progress"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GameKeeper")
        self.resize(1280, 820)
        self.setMinimumSize(900, 600)
        self.library = Library()
        self.settings = Settings.load()
        self.sessions: dict[str, GameSession] = {}
        self.toasts = ToastManager()
        self._apply_settings()
        self.current_filter = ALL

        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_library_page())
        self.page = GamePage()
        self._wire_game_page()
        self.stack.addWidget(self.page)
        lay.addWidget(self.stack, 1)

        self.statusBar().setStyleSheet(f"color: {style.MUTED}; background: {style.PANEL}; border-top: 1px solid {style.BORDER};")
        self.refresh_sidebar()
        self.refresh_grid()

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(230)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 8)
        v.setSpacing(0)
        brand = QLabel("\U0001F3AE  GameKeeper")
        brand.setObjectName("Brand")
        v.addWidget(brand)

        lbl = QLabel("LIBRARY")
        lbl.setObjectName("SectionLabel")
        v.addWidget(lbl)
        self.views = QListWidget()
        self.views.setObjectName("Categories")
        self.views.setFixedHeight(4 * 36 + 6)
        self.views.itemClicked.connect(lambda it: self._select_filter(it.data(Qt.UserRole), self.views))
        v.addWidget(self.views)

        row = QHBoxLayout()
        lbl2 = QLabel("CATEGORIES")
        lbl2.setObjectName("SectionLabel")
        row.addWidget(lbl2)
        add = QPushButton("+")
        add.setToolTip("New category")
        add.setFixedSize(26, 22)
        add.setStyleSheet(f"padding: 0; font-size: 15px; color: {style.MUTED}; background: transparent; border: none;")
        add.clicked.connect(self.new_category)
        row.addWidget(add)
        row.addSpacing(10)
        v.addLayout(row)
        self.cats = QListWidget()
        self.cats.setObjectName("Categories")
        self.cats.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cats.customContextMenuRequested.connect(self._category_menu)
        self.cats.itemClicked.connect(lambda it: self._select_filter(it.data(Qt.UserRole), self.cats))
        v.addWidget(self.cats, 1)

        settings = QPushButton("⚙   Settings")
        settings.setObjectName("Flat")
        settings.clicked.connect(self.open_settings)
        v.addWidget(settings)
        return side

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 18, 16, 0)
        top = QHBoxLayout()
        self.heading = QLabel("All games")
        self.heading.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.count = QLabel()
        self.count.setStyleSheet(f"color: {style.MUTED}; padding-top: 6px;")
        top.addWidget(self.heading)
        top.addWidget(self.count)
        top.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search...")
        self.search.setFixedWidth(220)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_grid)
        self.sort = QComboBox()
        self.sort.addItems(SORTS)
        self.sort.currentIndexChanged.connect(self.refresh_grid)
        addbtn = QPushButton("+  Add game")
        addbtn.setObjectName("Primary")
        addbtn.clicked.connect(self.add_game)
        top.addWidget(self.search)
        top.addWidget(self.sort)
        top.addWidget(addbtn)
        v.addLayout(top)

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
        p.setup_emulator.connect(self.setup_emulator)
        p.restore_emulator.connect(self.restore_emulator)
        p.remove.connect(self.remove_game)
        p.toggle_favorite.connect(self.toggle_favorite)
        p.open_folder.connect(self.open_folder)
        p.achievement_toggled.connect(self.set_achievement)

    # ------------------------------------------------------------------ #
    # sidebar + grid
    # ------------------------------------------------------------------ #
    def refresh_sidebar(self):
        games = self.library.games
        self.views.clear()
        for key, label, n in (
            (ALL, "\U0001F4DA   All games", len(games)),
            (FAVORITES, "★   Favorites", sum(g.favorite for g in games)),
            (RECENT, "\U0001F552   Recently played", sum(1 for g in games if g.last_played)),
            (UNCATEGORIZED, "\U0001F4C2   Uncategorized", sum(1 for g in games if not g.categories)),
        ):
            it = QListWidgetItem(f"{label}   {n}")
            it.setData(Qt.UserRole, key)
            it.setSizeHint(QSize(0, 34))
            self.views.addItem(it)
        self.cats.clear()
        for c in self.library.categories:
            n = sum(1 for g in games if c in g.categories)
            it = QListWidgetItem(f"{c}   {n}")
            it.setData(Qt.UserRole, c)
            it.setSizeHint(QSize(0, 34))
            self.cats.addItem(it)
        for lst in (self.views, self.cats):
            for i in range(lst.count()):
                if lst.item(i).data(Qt.UserRole) == self.current_filter:
                    lst.setCurrentRow(i)

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
        }[sort]
        return sorted(games, key=key)

    def refresh_grid(self):
        names = {ALL: "All games", FAVORITES: "Favorites", RECENT: "Recently played", UNCATEGORIZED: "Uncategorized"}
        self.heading.setText(names.get(self.current_filter, self.current_filter))
        games = self._filtered()
        self.grid.set_games(games)
        self.count.setText(f"  {len(games)} game{'s' if len(games) != 1 else ''}")
        if not self.library.games:
            self.empty.setText("Your library is empty.\nClick  “+  Add game”  and pick a game's folder to get started.")
        elif not games:
            self.empty.setText("No games here yet.\nRight-click a game to add it to a category.")
        self.empty.setVisible(not games)
        self.grid.setVisible(bool(games))

    def show_library(self):
        self.stack.setCurrentIndex(0)
        self.refresh_grid()

    def open_game(self, game_id: str):
        g = self.library.get(game_id)
        if not g:
            return
        if game_id not in self.sessions:
            self._sync_unlocks(g, refresh=False)
        self.page.show_game(g)
        self.page.set_running(game_id in self.sessions)
        self.stack.setCurrentIndex(1)

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
        name, ok = QInputDialog.getText(self, "New category", "Name (e.g. Retro, Emulated, Backlog):")
        if ok and name.strip():
            if not self.library.add_category(name):
                QMessageBox.information(self, "New category", "A category with that name already exists.")
            self.refresh_sidebar()

    def _category_menu(self, pos):
        it = self.cats.itemAt(pos)
        if not it:
            m = QMenu(self)
            m.addAction("New category...", self.new_category)
            m.exec(self.cats.viewport().mapToGlobal(pos))
            return
        name = it.data(Qt.UserRole)
        m = QMenu(self)
        ren = m.addAction("Rename...")
        dele = m.addAction("Delete category")
        act = m.exec(self.cats.viewport().mapToGlobal(pos))
        if act == ren:
            new, ok = QInputDialog.getText(self, "Rename category", "New name:", text=name)
            if ok and self.library.rename_category(name, new):
                if self.current_filter == name:
                    self.current_filter = new.strip()
        elif act == dele:
            if QMessageBox.question(self, "Delete category",
                                    f"Delete '{name}'? The games stay in your library.") == QMessageBox.Yes:
                self.library.delete_category(name)
                if self.current_filter == name:
                    self.current_filter = ALL
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
        cm = m.addMenu("Categories")
        for c in self.library.categories:
            a = cm.addAction(c)
            a.setCheckable(True)
            a.setChecked(c in g.categories)
            a.toggled.connect(lambda on, c=c: self._set_category(g, c, on))
        if self.library.categories:
            cm.addSeparator()
        cm.addAction("New category...", lambda: self._new_category_for(g))
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
        name, ok = QInputDialog.getText(self, "New category", "Name:")
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
                f"Remove '{g.name}' from GameKeeper?\n\nThis deletes its playtime and achievement records "
                "in GameKeeper. The game's own files are not touched.") != QMessageBox.Yes:
            return
        self.library.remove(g)
        self.refresh_sidebar()
        self.show_library()

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
        self.page.set_running(self.page.game is not None and self.page.game.id in self.sessions)
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
        if self.page.game and self.page.game.id == game_id:
            self.page.set_running(False)

    def _on_failed(self, game_id: str, msg: str):
        self.sessions.pop(game_id, None)
        self.page.set_running(False)
        QMessageBox.warning(self, "Can't start game", msg)

    def _on_needs_admin(self, game_id: str):
        self.sessions.pop(game_id, None)
        self.page.set_running(False)
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
        self.page.set_running(False)
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
        self.toasts.show(ach.title, g.name, achset.icon_path(ach))
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

    def _sync_unlocks(self, g: Game, refresh: bool = True):
        """Quietly import unlocks made while GameKeeper wasn't watching
        (e.g. progress from before the game was added)."""
        if not tracking.describe(g):
            return
        achset = AchievementSet(g.id)
        if not achset.total:
            return
        changed = False
        for name, when in tracking.read_unlocks(g).items():
            changed |= achset.unlock(name, when or None, source="auto") is not None
        if changed:
            achset.save()
            self._update_counts(g, achset)
            if refresh:
                self._refresh_game(g)
            else:
                self.library.save()

    @staticmethod
    def _update_counts(g: Game, achset: AchievementSet):
        g.achievements_total = achset.total
        g.achievements_unlocked = achset.unlocked_count

    # ------------------------------------------------------------------ #
    # steam + emulator
    # ------------------------------------------------------------------ #
    def fetch_steam_data(self, game_id: str):
        g = self.library.get(game_id)
        if not g or not g.appid:
            return
        self.statusBar().showMessage(f"Pulling Steam data for {g.name}...")
        settings = self.settings

        def job(progress):
            steam.download_artwork(g)
            try:
                achset = steam.fetch_achievements(g, settings, progress)
                return achset.total, achset.unlocked_count, None
            except steam.SteamError as e:
                return 0, 0, str(e)

        def done(result):
            total, unlocked, err = result
            if total:
                g.achievements_total, g.achievements_unlocked = total, unlocked
            if g.emulator_installed:   # keep the emulator's list in sync
                for dll in emulator.find_steam_dlls(g.game_dir):
                    emulator.write_steam_settings(g, dll.parent)
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
            if g.emulator_installed:
                emulator.push_unlocks(g)
            self._refresh_game(g)
            self.statusBar().clearMessage()
            QMessageBox.information(
                self, "Imported from Steam",
                f"{len(new)} achievement(s) newly marked as unlocked.\n"
                f"Steam playtime: {playtime // 3600} h {playtime % 3600 // 60} min "
                "(shown on top of time played here).")

        run_async(lambda: steam.import_progress(g, settings), done,
                  lambda e: self._error("Import failed", e))

    def setup_emulator(self, game_id: str):
        g = self.library.get(game_id)
        if not g:
            return
        if not self.settings.emulator_dir:
            QMessageBox.information(
                self, "Achievement tracking",
                "First download a Steam API emulator (e.g. gbe_fork) and set its folder in Settings.")
            self.open_settings()
            if not self.settings.emulator_dir:
                return
        dlls = emulator.find_steam_dlls(g.game_dir)
        if not dlls:
            QMessageBox.warning(self, "Achievement tracking",
                                "No steam_api.dll / steam_api64.dll found in this game's folder, "
                                "so it can't be tracked this way.")
            return
        if AchievementSet(g.id).total == 0:
            QMessageBox.information(self, "Achievement tracking",
                                    "Pull the achievement list from Steam first (Manage → Steam data).")
            return
        listing = "\n".join(f"  • {d.relative_to(g.game_dir)}" for d in dlls)
        if QMessageBox.question(
                self, "Set up achievement tracking",
                f"GameKeeper will back up and replace:\n{listing}\n\n"
                "with the emulator's DLL, so the game reports achievements to GameKeeper instead of Steam. "
                "You can undo this any time with 'Restore original Steam files'.\n\nContinue?") != QMessageBox.Yes:
            return
        try:
            emulator.install(g, self.settings.emulator_dir)
            emulator.push_unlocks(g)
        except (emulator.EmulatorError, OSError) as e:
            self._error("Setup failed", str(e))
            return
        g.emulator_installed = True
        self._refresh_game(g)
        self.statusBar().showMessage(f"Achievement tracking is on for {g.name}.", 8000)

    def restore_emulator(self, game_id: str):
        g = self.library.get(game_id)
        if not g:
            return
        try:
            n = emulator.restore(g)
        except OSError as e:
            self._error("Restore failed", str(e))
            return
        g.emulator_installed = False
        self._refresh_game(g)
        self.statusBar().showMessage(f"Restored {n} original file(s) for {g.name}.", 8000)

    # ------------------------------------------------------------------ #
    def open_settings(self):
        if SettingsDialog(self.settings, self).exec():
            self._apply_settings()

    def _apply_settings(self):
        self.toasts.enabled_sound = self.settings.toast_sound
        self.toasts.seconds = self.settings.toast_seconds

    def _error(self, title: str, msg: str):
        self.statusBar().clearMessage()
        QMessageBox.warning(self, title, msg)

    def closeEvent(self, e):
        if self.sessions:
            names = ", ".join(self.library.get(i).name for i in self.sessions if self.library.get(i))
            if QMessageBox.question(
                    self, "Game still running",
                    f"{names} is still running. Closing GameKeeper stops tracking its playtime "
                    "and achievements for this session.\n\nClose anyway?") != QMessageBox.Yes:
                e.ignore()
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
