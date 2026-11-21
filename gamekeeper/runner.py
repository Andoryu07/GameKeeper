"""Launching games, tracking playtime and watching for achievement unlocks."""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

import psutil
from PySide6.QtCore import QThread, Signal

from . import emulator
from .storage import Game

POLL_SECONDS = 2
CHECKPOINT_SECONDS = 60
HANDOFF_GRACE = 10      # seconds to wait for a launcher to hand off to the real game


def _under(path: str, folder: Path) -> bool:
    try:
        return Path(path).resolve().is_relative_to(folder)
    except (OSError, ValueError):
        return False


class GameSession(QThread):
    """Runs one game and reports back to the UI thread through signals.

    Playtime counts while *any* process started from the game's folder is
    alive, so games whose .exe is just a small launcher (Unreal games,
    publisher launchers) are still timed correctly.
    """

    checkpoint = Signal(str, int)          # game id, seconds since last checkpoint
    unlocked = Signal(str, str, int)       # game id, achievement api name, unlock time
    ended = Signal(str, int)               # game id, seconds since last checkpoint
    failed = Signal(str, str)              # game id, error message

    def __init__(self, game: Game, parent=None):
        super().__init__(parent)
        self.game = game
        self.started_at = 0.0
        self.last_checkpoint = 0.0
        self._stop = False

    def stop_tracking(self):
        self._stop = True

    def run(self):
        g = self.game
        try:
            args = shlex.split(g.args, posix=(os.name != "nt")) if g.args else []
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            proc = subprocess.Popen([g.exe, *args], cwd=g.run_dir, creationflags=flags)
        except OSError as e:
            self.failed.emit(g.id, f"Couldn't start {Path(g.exe).name}: {e}")
            return

        self.started_at = time.time()
        last_cp = self.last_checkpoint = self.started_at
        root_pid = proc.pid
        folders = {Path(g.exe).resolve().parent, g.game_dir.resolve()}
        known = set(emulator.read_unlocks(g))   # unlocks that existed before launch

        while not self._stop:
            time.sleep(POLL_SECONDS)
            now = time.time()

            # achievements
            current = emulator.read_unlocks(g)
            for name, when in current.items():
                if name not in known:
                    known.add(name)
                    self.unlocked.emit(g.id, name, when or int(now))

            if now - last_cp >= CHECKPOINT_SECONDS:
                self.checkpoint.emit(g.id, int(now - last_cp))
                last_cp = self.last_checkpoint = now

            if not self._game_alive(root_pid, folders, now - self.started_at):
                break

        # one last check, games often write the file right before exiting
        for name, when in emulator.read_unlocks(g).items():
            if name not in known:
                self.unlocked.emit(g.id, name, when or int(time.time()))
        self.ended.emit(g.id, int(time.time() - last_cp))

    def _game_alive(self, root_pid: int, folders: set[Path], elapsed: float) -> bool:
        if psutil.pid_exists(root_pid):
            try:
                if psutil.Process(root_pid).status() != psutil.STATUS_ZOMBIE:
                    return True
            except psutil.Error:
                pass
        for p in psutil.process_iter(["exe"]):
            exe = p.info.get("exe")
            if exe and any(_under(exe, f) for f in folders):
                return True
        # a launcher may exit a moment before the real game shows up
        return elapsed < HANDOFF_GRACE


def format_playtime(seconds: int) -> str:
    if seconds <= 0:
        return "Never played"
    minutes = seconds // 60
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    hours = seconds / 3600
    return f"{hours:.1f} hours" if hours < 100 else f"{int(hours)} hours"
