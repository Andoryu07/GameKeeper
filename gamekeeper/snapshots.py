"""Keeping a copy of a game's save every time it changes.

Used to work out save-file achievement rules: comparing saves made before and
after a known event (picking up one collectible, one kill...) shows where the
game stores that number. Copies go to data/save_copies/<game id>/.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import triggers
from .storage import DATA_DIR, Game

ROOT = DATA_DIR / "save_copies"
MAX_COPIES = 300


def folder(game: Game) -> Path:
    return ROOT / game.id


def watched_files(game: Game) -> list[Path]:
    files = []
    if game.save_path:
        files.append(Path(game.save_path))
    rules = triggers.rules_for(game.appid, game.exe)
    if rules and not rules.needs_save_path:
        try:
            files += rules.watch_files()
        except Exception:  # noqa: BLE001
            pass
    return files


class Snapshotter:
    """Call ``check()`` regularly; copies any watched file whose contents changed."""

    def __init__(self, game: Game):
        self.game = game
        self._seen: dict[str, tuple] = {}

    def check(self) -> int:
        if not self.game.keep_save_copies:
            return 0
        copied = 0
        for f in watched_files(self.game):
            try:
                st = f.stat()
            except OSError:
                continue
            sig = (st.st_mtime_ns, st.st_size)
            if self._seen.get(str(f)) == sig:
                continue
            self._seen[str(f)] = sig
            dest = folder(self.game)
            dest.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(st.st_mtime))
            target = dest / f"{stamp}_{f.name}"
            if not target.exists():
                try:
                    shutil.copy2(f, target)
                    copied += 1
                except OSError:
                    continue
        old = sorted(folder(self.game).glob("*"))[:-MAX_COPIES] if folder(self.game).exists() else []
        for o in old:
            o.unlink(missing_ok=True)
        return copied
