"""Launching games, tracking playtime and watching for achievement unlocks."""
from __future__ import annotations

import time
from pathlib import Path

import psutil
from PySide6.QtCore import QThread, Signal

from . import scanner, tracking
from .storage import Game
from .winlaunch import LaunchCancelled, NeedsAdmin, launch

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
    needs_admin = Signal(str)              # game id: exe requires administrator rights
    cancelled = Signal(str)                # game id: user declined the UAC prompt

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
            proc = launch(g.exe, g.args, g.run_dir, as_admin=g.run_as_admin)
        except NeedsAdmin:
            self.needs_admin.emit(g.id)
            return
        except LaunchCancelled:
            self.cancelled.emit(g.id)
            return
        except OSError as e:
            self.failed.emit(g.id, f"Couldn't start {Path(g.exe).name}: {e}")
            return

        self.started_at = time.time()
        last_cp = self.last_checkpoint = self.started_at
        folders = {Path(g.exe).resolve().parent, g.game_dir.resolve()}
        # Names of the game's executables. An elevated game hides its path
        # from non-elevated programs, but its name is still visible.
        exe_names = {p.name.lower() for p in scanner.find_executables(g.game_dir)} | {Path(g.exe).name.lower()}
        known = set(tracking.read_unlocks(g))   # unlocks that existed before launch

        try:
            while not self._stop:
                time.sleep(POLL_SECONDS)
                now = time.time()

                for name, when in tracking.read_unlocks(g).items():
                    if name not in known:
                        known.add(name)
                        self.unlocked.emit(g.id, name, int(now))

                if now - last_cp >= CHECKPOINT_SECONDS:
                    self.checkpoint.emit(g.id, int(now - last_cp))
                    last_cp = self.last_checkpoint = now

                if not self._game_alive(proc, folders, exe_names, now - self.started_at):
                    break

            # one last check, games often save right before exiting
            time.sleep(1)
            for name in tracking.read_unlocks(g):
                if name not in known:
                    self.unlocked.emit(g.id, name, int(time.time()))
        finally:
            proc.close()
        self.ended.emit(g.id, int(time.time() - last_cp))

    def _game_alive(self, proc, folders: set[Path], exe_names: set[str], elapsed: float) -> bool:
        if proc.alive():
            return True
        for p in psutil.process_iter(["exe", "name"]):
            exe = p.info.get("exe")
            if exe:
                if any(_under(exe, f) for f in folders):
                    return True
            elif (p.info.get("name") or "").lower() in exe_names:
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
