"""Daily zip backups of everything that can't be downloaded again.

Each backup holds the library (playtime, categories, ratings, reviews),
settings, and every game's achievement record, including archived games.
Covers and icons are left out; they can be pulled from Steam again.
"""
from __future__ import annotations

import time
import zipfile
from pathlib import Path

from .storage import ARCHIVE_DIR, DATA_DIR, GAMES_DIR, LIBRARY_FILE, SETTINGS_FILE, Settings

KEEP = 30
DAY = 24 * 3600


def backup_dir(settings: Settings) -> Path:
    return Path(settings.backup_dir) if settings.backup_dir else DATA_DIR / "backups"


def make_backup(settings: Settings) -> Path:
    folder = backup_dir(settings)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / time.strftime("gamekeeper-%Y-%m-%d_%H-%M-%S.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (LIBRARY_FILE, SETTINGS_FILE):
            if f.exists():
                z.write(f, f.relative_to(DATA_DIR))
        for base in (GAMES_DIR, ARCHIVE_DIR):
            if not base.is_dir():
                continue
            for name in ("achievements.json", "game.json"):
                for f in base.glob(f"*/{name}"):
                    z.write(f, f.relative_to(DATA_DIR))
    for old in sorted(folder.glob("gamekeeper-*.zip"))[:-KEEP]:
        old.unlink(missing_ok=True)
    settings.last_backup = int(time.time())
    settings.save()
    return path


def backup_if_due(settings: Settings) -> Path | None:
    if time.time() - settings.last_backup < DAY:
        return None
    return make_backup(settings)
