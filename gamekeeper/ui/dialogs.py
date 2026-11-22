"""Add game, edit game and settings dialogs."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from .. import backup, scanner, shortcut, snapshots, steam
from ..storage import Game, Library, Settings
from . import icon, style
from .workers import run_async


def open_path(path) -> None:
    """Open a folder in Explorer (or the platform's file manager)."""
    import os
    import subprocess
    import sys
    path = str(path)
    os.makedirs(path, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {style.MUTED}; font-size: 11px;")
    lbl.setOpenExternalLinks(True)
    return lbl


class SteamLinker(QWidget):
    """Search Steam and pick which app a game is."""

    def __init__(self, appid: int | None = None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Game name or Steam app id")
        self.query.returnPressed.connect(self.search)
        self.btn = QPushButton("Search")
        self.btn.clicked.connect(self.search)
        row.addWidget(self.query, 1)
        row.addWidget(self.btn)
        lay.addLayout(row)
        self.results = QListWidget()
        self.results.setMinimumHeight(130)
        lay.addWidget(self.results)
        self.status = _hint("")
        lay.addWidget(self.status)
        self._reset(appid)

    def _reset(self, appid: int | None):
        self.results.clear()
        none = QListWidgetItem("Not a Steam game (no achievements / emulated / retro)")
        none.setData(Qt.UserRole, None)
        self.results.addItem(none)
        if appid:
            cur = QListWidgetItem(f"Current link - app {appid}")
            cur.setData(Qt.UserRole, appid)
            self.results.addItem(cur)
            self.results.setCurrentItem(cur)
        else:
            self.results.setCurrentItem(none)

    def search(self):
        term = self.query.text().strip()
        if not term:
            return
        self.btn.setEnabled(False)
        self.status.setText("Searching Steam...")
        run_async(lambda: steam.search(term), self._show, self._error)

    def _show(self, items):
        self.btn.setEnabled(True)
        keep = self.appid
        self._reset(None)
        for it in items:
            li = QListWidgetItem(f"{it['name']}   (app {it['appid']})")
            li.setData(Qt.UserRole, it["appid"])
            self.results.addItem(li)
        self.status.setText(f"{len(items)} result(s)." if items else "No results. Try a shorter name or the app id.")
        if items:
            self.results.setCurrentRow(1)
        elif keep:
            self._reset(keep)

    def _error(self, msg):
        self.btn.setEnabled(True)
        self.status.setText(msg)

    @property
    def appid(self) -> int | None:
        item = self.results.currentItem()
        return item.data(Qt.UserRole) if item else None

    @property
    def app_name(self) -> str:
        item = self.results.currentItem()
        if not item or item.data(Qt.UserRole) is None:
            return ""
        return item.text().rsplit("   (app", 1)[0]


class CategoryPicker(QListWidget):
    def __init__(self, library: Library, selected: list[str], parent=None):
        super().__init__(parent)
        self.setMaximumHeight(110)
        for c in library.categories:
            it = QListWidgetItem(c)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if c in selected else Qt.Unchecked)
            self.addItem(it)
        if not library.categories:
            it = QListWidgetItem("No collections yet - create them with + in the sidebar")
            it.setFlags(Qt.NoItemFlags)
            self.addItem(it)

    def selected(self) -> list[str]:
        return [self.item(i).text() for i in range(self.count())
                if self.item(i).flags() & Qt.ItemIsUserCheckable and self.item(i).checkState() == Qt.Checked]


# --------------------------------------------------------------------------- #
class AddGameDialog(QDialog):
    def __init__(self, library: Library, preset_category: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add game")
        self.resize(660, 800)
        self.library = library
        self.game: Game | None = None
        self.fetch_now = True

        lay = QVBoxLayout(self)

        # 1. folder + exe
        box1 = QGroupBox("1. Game folder")
        b1 = QVBoxLayout(box1)
        row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Pick the folder the game is installed in")
        self.folder.setReadOnly(True)
        browse = QPushButton("Browse...")
        browse.setObjectName("Primary")
        browse.clicked.connect(self.pick_folder)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        b1.addLayout(row)
        b1.addWidget(QLabel("Which file starts the game?"))
        self.exes = QListWidget()
        self.exes.setMinimumHeight(110)
        b1.addWidget(self.exes)
        other = QPushButton("Pick a different file...")
        other.clicked.connect(self.pick_exe)
        b1.addWidget(other, 0, Qt.AlignLeft)
        lay.addWidget(box1)

        # 2. details
        box2 = QGroupBox("2. Details")
        form = QFormLayout(box2)
        self.name = QLineEdit()
        self.args = QLineEdit()
        self.args.setPlaceholderText("Optional, e.g. -windowed  (for retro emulators: the ROM path)")
        self.cats = CategoryPicker(library, [preset_category] if preset_category else [])
        form.addRow("Name", self.name)
        form.addRow("Launch options", self.args)
        self.admin = QCheckBox("Run as administrator")
        self.admin.setToolTip("Windows will ask for permission each time the game starts.")
        form.addRow("", self.admin)
        form.addRow("Collections", self.cats)
        lay.addWidget(box2)

        # 3. steam
        box3 = QGroupBox("3. Link to Steam (for cover art and achievements)")
        b3 = QVBoxLayout(box3)
        self.linker = SteamLinker()
        b3.addWidget(self.linker)
        self.fetch = QCheckBox("Download cover art and achievements now")
        self.fetch.setChecked(True)
        b3.addWidget(self.fetch)
        b3.addWidget(_hint("You can also leave this off and pull the data later from the game's page, "
                           "e.g. when you're about to start a new playthrough."))
        lay.addWidget(box3, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Add to library")
        buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose the game's folder")
        if folder:
            self.set_folder(folder)

    def set_folder(self, folder: str):
        self.folder.setText(folder)
        self.exes.clear()
        root = Path(folder)
        for p in scanner.find_executables(root)[:40]:
            it = QListWidgetItem(str(p.relative_to(root)))
            it.setData(Qt.UserRole, str(p))
            self.exes.addItem(it)
        if self.exes.count():
            self.exes.setCurrentRow(0)
        else:
            it = QListWidgetItem("No .exe found here - use 'Pick a different file'")
            it.setFlags(Qt.NoItemFlags)
            self.exes.addItem(it)
        name = scanner.guess_name(folder)
        self.name.setText(name)
        self.linker.query.setText(name)
        self.linker.search()

    def pick_exe(self):
        start = self.folder.text() or ""
        path, _ = QFileDialog.getOpenFileName(self, "Choose the game's executable", start,
                                              "Programs (*.exe *.bat *.cmd *.lnk);;All files (*)")
        if not path:
            return
        if not self.folder.text():
            self.folder.setText(str(Path(path).parent))
            self.name.setText(scanner.guess_name(Path(path).parent))
        it = QListWidgetItem(path)
        it.setData(Qt.UserRole, path)
        self.exes.insertItem(0, it)
        self.exes.setCurrentItem(it)

    def accept(self):
        item = self.exes.currentItem()
        exe = item.data(Qt.UserRole) if item else None
        if not exe:
            QMessageBox.warning(self, "Add game", "Choose the game's folder and executable first.")
            return
        name = self.name.text().strip() or self.linker.app_name or Path(exe).stem
        self.game = Game(name=name, exe=exe, args=self.args.text().strip(),
                         install_dir=self.folder.text(), appid=self.linker.appid,
                         categories=self.cats.selected(), run_as_admin=self.admin.isChecked())
        self.fetch_now = self.fetch.isChecked() and self.game.appid is not None
        super().accept()


# --------------------------------------------------------------------------- #
class EditGameDialog(QDialog):
    def __init__(self, game: Game, library: Library, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit - {game.name}")
        self.resize(640, 780)
        self.game = game
        self.appid_changed = False

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(game.name)
        self.exe = QLineEdit(game.exe)
        exe_btn = QPushButton("...")
        exe_btn.setFixedWidth(36)
        exe_btn.clicked.connect(self._pick_exe)
        exe_row = QHBoxLayout()
        exe_row.addWidget(self.exe, 1)
        exe_row.addWidget(exe_btn)
        self.install = QLineEdit(game.install_dir)
        self.args = QLineEdit(game.args)
        self.workdir = QLineEdit(game.working_dir)
        self.workdir.setPlaceholderText("Default: the executable's folder")
        self.cats = CategoryPicker(library, game.categories)
        self.notes = QPlainTextEdit(game.notes)
        self.notes.setMaximumHeight(70)
        form.addRow("Name", self.name)
        form.addRow("Executable", exe_row)
        form.addRow("Game folder", self.install)
        form.addRow("Launch options", self.args)
        self.admin = QCheckBox("Run as administrator")
        self.admin.setChecked(game.run_as_admin)
        self.admin.setToolTip("Windows will ask for permission each time the game starts.")
        form.addRow("", self.admin)
        form.addRow("Start in", self.workdir)
        self.save_file = QLineEdit(game.save_path)
        self.save_file.setPlaceholderText("Only needed for some games' automatic achievements")
        save_btn = QPushButton("...")
        save_btn.setFixedWidth(36)
        save_btn.clicked.connect(self._pick_save)
        save_row = QHBoxLayout()
        save_row.addWidget(self.save_file, 1)
        save_row.addWidget(save_btn)
        form.addRow("Save file", save_row)
        self.keep_copies = QCheckBox("Keep a copy of every save while playing")
        self.keep_copies.setChecked(game.keep_save_copies)
        self.keep_copies.setToolTip("Helps work out automatic achievements for new games. "
                                    "Copies go to data/save_copies.")
        copies_row = QHBoxLayout()
        copies_row.addWidget(self.keep_copies)
        open_copies = QPushButton("Open copies folder")
        open_copies.clicked.connect(lambda: open_path(snapshots.folder(game)))
        copies_row.addWidget(open_copies)
        copies_row.addStretch()
        form.addRow("", copies_row)
        form.addRow("Collections", self.cats)
        form.addRow("Notes", self.notes)
        lay.addLayout(form)

        box = QGroupBox("Steam link")
        b = QVBoxLayout(box)
        self.linker = SteamLinker(game.appid)
        self.linker.query.setText(game.name)
        b.addWidget(self.linker)
        lay.addWidget(box, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName("Primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _pick_save(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the game's save file", self.save_file.text())
        if path:
            self.save_file.setText(path)

    def _pick_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the game's executable", self.exe.text())
        if path:
            self.exe.setText(path)

    def accept(self):
        g = self.game
        g.name = self.name.text().strip() or g.name
        g.exe = self.exe.text().strip()
        g.install_dir = self.install.text().strip()
        g.args = self.args.text().strip()
        g.run_as_admin = self.admin.isChecked()
        g.working_dir = self.workdir.text().strip()
        g.save_path = self.save_file.text().strip()
        g.keep_save_copies = self.keep_copies.isChecked()
        g.categories = self.cats.selected()
        g.notes = self.notes.toPlainText()
        if self.linker.appid != g.appid:
            g.appid = self.linker.appid
            self.appid_changed = True
        super().accept()


# --------------------------------------------------------------------------- #
class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None, test_popup=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(580, 780)
        self.settings = settings
        lay = QVBoxLayout(self)

        box = QGroupBox("Steam account (optional)")
        f = QFormLayout(box)
        self.key = QLineEdit(settings.steam_api_key)
        self.key.setEchoMode(QLineEdit.Password)
        self.sid = QLineEdit(settings.steam_id)
        self.sid.setPlaceholderText("SteamID64, profile name or profile URL")
        self.lang = QLineEdit(settings.language)
        f.addRow("Web API key", self.key)
        f.addRow("", _hint('Not needed for cover art or achievement lists. Only for importing '
                           'your existing unlocks and playtime from Steam. Free key from '
                           '<a href="https://steamcommunity.com/dev/apikey">steamcommunity.com/dev/apikey</a>.'))
        f.addRow("Steam ID", self.sid)
        f.addRow("", _hint("Also only for importing. Your profile's 'Game details' must be public."))
        f.addRow("Language", self.lang)
        f.addRow("", _hint("Language for achievement names, e.g. english, german, czech."))
        lay.addWidget(box)

        box2 = QGroupBox("Achievement popups")
        f2 = QFormLayout(box2)
        self.sound = QCheckBox("Play a sound on unlock")
        self.sound.setChecked(settings.toast_sound)
        self.secs = QSpinBox()
        self.secs.setRange(2, 30)
        self.secs.setValue(settings.toast_seconds)
        self.secs.setSuffix(" s")
        f2.addRow("", self.sound)
        f2.addRow("Popup duration", self.secs)
        if test_popup:
            test = QPushButton("Show a test popup")
            test.clicked.connect(lambda: test_popup(self.sound.isChecked(), self.secs.value()))
            f2.addRow("", test)
        lay.addWidget(box2)

        boxb = QGroupBox("Backups")
        fb = QFormLayout(boxb)
        brow = QHBoxLayout()
        self.backup_dir = QLineEdit(settings.backup_dir)
        self.backup_dir.setPlaceholderText(str(backup.backup_dir(Settings())))
        bpick = QPushButton("Browse...")
        bpick.clicked.connect(self._pick_backup_dir)
        brow.addWidget(self.backup_dir, 1)
        brow.addWidget(bpick)
        fb.addRow("Folder", brow)
        brow2 = QHBoxLayout()
        now = QPushButton("Back up now")
        now.clicked.connect(self._backup_now)
        openb = QPushButton("Open folder")
        openb.clicked.connect(lambda: open_path(backup.backup_dir(self._current_backup_settings())))
        brow2.addWidget(now)
        brow2.addWidget(openb)
        brow2.addStretch()
        fb.addRow("", brow2)
        fb.addRow("", _hint("GameKeeper backs up playtime, achievements, ratings and reviews once a day "
                            "and keeps the last 30. Pick a folder on another drive or a cloud-synced "
                            "folder for extra safety."))
        lay.addWidget(boxb)

        box3 = QGroupBox("Shortcuts")
        b3 = QVBoxLayout(box3)
        row = QHBoxLayout()
        for label, where in (("Create desktop shortcut", "desktop"), ("Add to Start menu", "startmenu")):
            btn = QPushButton(label)
            btn.setEnabled(shortcut.supported())
            btn.clicked.connect(lambda _=False, w=where: self._make_shortcut(w))
            row.addWidget(btn)
        row.addStretch()
        b3.addLayout(row)
        b3.addWidget(_hint("Starts GameKeeper with a double-click, without a console window."
                           if shortcut.supported() else "Shortcuts can only be created on Windows."))
        lay.addWidget(box3)
        lay.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName("Primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _current_backup_settings(self) -> Settings:
        s = Settings(**{**self.settings.__dict__})
        s.backup_dir = self.backup_dir.text().strip()
        return s

    def _pick_backup_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Backup folder", self.backup_dir.text())
        if d:
            self.backup_dir.setText(d)

    def _backup_now(self):
        self.settings.backup_dir = self.backup_dir.text().strip()
        try:
            path = backup.make_backup(self.settings)
        except OSError as e:
            QMessageBox.warning(self, "Backup", f"Backup failed: {e}")
            return
        QMessageBox.information(self, "Backup", f"Saved:\n{path}")

    def _make_shortcut(self, where: str):
        try:
            path = shortcut.create(where, icon.ico_file())
        except shortcut.ShortcutError as e:
            QMessageBox.warning(self, "Shortcut", str(e))
            return
        QMessageBox.information(self, "Shortcut", f"Created:\n{path}")

    def accept(self):
        s = self.settings
        s.steam_api_key = self.key.text().strip()
        s.steam_id = self.sid.text().strip()
        s.language = self.lang.text().strip() or "english"
        s.toast_sound = self.sound.isChecked()
        s.toast_seconds = self.secs.value()
        s.backup_dir = self.backup_dir.text().strip()
        s.save()
        super().accept()


# --------------------------------------------------------------------------- #
class ArchiveDialog(QDialog):
    """Games removed from the library, with everything they had recorded."""

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Archived games")
        self.resize(560, 440)
        self.library = library
        self.restored: list[str] = []
        lay = QVBoxLayout(self)
        lay.addWidget(_hint("Games you remove from the library are kept here with their playtime, "
                            "achievements, rating and review. Restore one to put it back exactly as it was."))
        self.list = QListWidget()
        self.list.setObjectName("ArchiveList")
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.restore_btn = QPushButton("Restore to library")
        self.restore_btn.setObjectName("Primary")
        self.restore_btn.clicked.connect(self.restore)
        self.delete_btn = QPushButton("Delete permanently")
        self.delete_btn.setObjectName("Danger")
        self.delete_btn.clicked.connect(self.delete)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(self.restore_btn)
        row.addWidget(self.delete_btn)
        row.addStretch()
        row.addWidget(close)
        lay.addLayout(row)
        self.reload()

    def reload(self):
        from ..runner import format_playtime
        import datetime as dt
        self.list.clear()
        for e in Library.archived():
            g = e["game"]
            when = dt.datetime.fromtimestamp(e["archived_at"]).strftime("%d %b %Y") if e["archived_at"] else "?"
            parts = [format_playtime(g.total_playtime)]
            if e["total"]:
                parts.append(f"{e['unlocked']}/{e['total']} achievements")
            if g.rating:
                parts.append(f"rated {g.rating}/10")
            parts.append(f"removed {when}")
            it = QListWidgetItem(g.name + "\n" + "  \u00b7  ".join(parts))
            it.setData(Qt.UserRole, g.id)
            self.list.addItem(it)
        empty = self.list.count() == 0
        if empty:
            it = QListWidgetItem("No archived games.")
            it.setFlags(Qt.NoItemFlags)
            self.list.addItem(it)
        else:
            self.list.setCurrentRow(0)
        self.restore_btn.setEnabled(not empty)
        self.delete_btn.setEnabled(not empty)

    def _selected(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def restore(self):
        gid = self._selected()
        if gid and self.library.restore(gid):
            self.restored.append(gid)
        self.reload()

    def delete(self):
        gid = self._selected()
        if not gid:
            return
        name = self.list.currentItem().text().split("\n")[0]
        if QMessageBox.question(self, "Delete permanently",
                                f"Permanently delete everything recorded for '{name}'?\n\n"
                                "Older copies stay in your backups.") == QMessageBox.Yes:
            Library.delete_archived(gid)
            self.reload()
