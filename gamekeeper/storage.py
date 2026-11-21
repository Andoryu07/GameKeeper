"""Where GameKeeper keeps its data, and the data model for the library.

Everything lives in one ``data`` folder next to ``main.py`` so the whole
launcher (games list, covers, achievements, playtime) can be copied or backed
up as a single folder.

Layout::

    data/
      settings.json
      library.json              games + categories
      games/<game id>/
        cover.jpg               portrait cover (600x900)
        hero.jpg                wide banner for the detail page
        achievements.json       schema + unlock state
        icons/                  achievement icons
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("GAMEKEEPER_DATA", ROOT_DIR / "data"))
GAMES_DIR = DATA_DIR / "games"
SETTINGS_FILE = DATA_DIR / "settings.json"
LIBRARY_FILE = DATA_DIR / "library.json"


def ensure_dirs() -> None:
    GAMES_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    """Write JSON atomically so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _from_dict(cls, data: dict):
    """Build a dataclass from a dict, ignoring unknown keys (forward compatible)."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@dataclass
class Settings:
    steam_api_key: str = ""
    steam_id: str = ""              # SteamID64 or custom profile name
    language: str = "english"
    toast_sound: bool = True
    toast_seconds: int = 6
    shortcut_offered: bool = False
    window_geometry: str = ""       # saved window size/position
    cover_size: int = 160

    @classmethod
    def load(cls) -> "Settings":
        return _from_dict(cls, read_json(SETTINGS_FILE, {}))

    def save(self) -> None:
        write_json(SETTINGS_FILE, asdict(self))


# --------------------------------------------------------------------------- #
# Achievements
# --------------------------------------------------------------------------- #
@dataclass
class Achievement:
    api_name: str
    name: str = ""
    description: str = ""
    hidden: bool = False
    icon: str = ""                  # file name inside icons/
    icon_gray: str = ""
    global_percent: float | None = None
    unlocked: bool = False
    unlock_time: int = 0            # unix timestamp
    source: str = ""                # "auto" (save files), "steam", "manual"

    @property
    def title(self) -> str:
        return self.name or self.api_name


class AchievementSet:
    """All achievements for one game, stored in its achievements.json."""

    def __init__(self, game_id: str):
        self.game_id = game_id
        self.path = GAMES_DIR / game_id / "achievements.json"
        self.icons_dir = GAMES_DIR / game_id / "icons"
        self.items: list[Achievement] = []
        self.fetched_at: int = 0
        self.load()

    def load(self) -> None:
        data = read_json(self.path, {})
        self.fetched_at = data.get("fetched_at", 0)
        self.items = [_from_dict(Achievement, a) for a in data.get("achievements", [])]

    def save(self) -> None:
        write_json(self.path, {
            "fetched_at": self.fetched_at,
            "achievements": [asdict(a) for a in self.items],
        })

    def by_name(self) -> dict[str, Achievement]:
        return {a.api_name: a for a in self.items}

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def unlocked_count(self) -> int:
        return sum(1 for a in self.items if a.unlocked)

    def unlock(self, api_name: str, when: int | None = None, source: str = "manual") -> Achievement | None:
        """Mark one unlocked. Returns it if it was newly unlocked, else None."""
        ach = self.by_name().get(api_name)
        if ach is None or ach.unlocked:
            return None
        ach.unlocked = True
        ach.unlock_time = int(when or time.time())
        ach.source = source
        return ach

    def lock(self, api_name: str) -> None:
        ach = self.by_name().get(api_name)
        if ach:
            ach.unlocked, ach.unlock_time, ach.source = False, 0, ""

    def icon_path(self, ach: Achievement) -> Path | None:
        name = ach.icon if ach.unlocked else (ach.icon_gray or ach.icon)
        if not name:
            return None
        p = self.icons_dir / name
        return p if p.exists() else None


# --------------------------------------------------------------------------- #
# Games and library
# --------------------------------------------------------------------------- #
@dataclass
class Game:
    name: str
    exe: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    args: str = ""
    working_dir: str = ""           # empty = folder of the exe
    install_dir: str = ""           # the folder picked when adding the game
    appid: int | None = None        # Steam app id, if linked
    categories: list[str] = field(default_factory=list)
    favorite: bool = False
    playtime: int = 0               # seconds played through GameKeeper
    steam_playtime: int = 0         # seconds imported from Steam
    first_played: int = 0
    last_played: int = 0
    added: int = field(default_factory=lambda: int(time.time()))
    achievements_total: int = 0     # cached for the grid
    achievements_unlocked: int = 0
    run_as_admin: bool = False
    notes: str = ""

    @property
    def folder(self) -> Path:
        return GAMES_DIR / self.id

    @property
    def cover_path(self) -> Path:
        return self.folder / "cover.jpg"

    @property
    def hero_path(self) -> Path:
        return self.folder / "hero.jpg"

    @property
    def total_playtime(self) -> int:
        return self.playtime + self.steam_playtime

    @property
    def game_dir(self) -> Path:
        return Path(self.install_dir or Path(self.exe).parent)

    @property
    def run_dir(self) -> str:
        return self.working_dir or str(Path(self.exe).parent)


class Library:
    def __init__(self):
        ensure_dirs()
        data = read_json(LIBRARY_FILE, {})
        self.games: list[Game] = [_from_dict(Game, g) for g in data.get("games", [])]
        self.categories: list[str] = data.get("categories", [])

    def save(self) -> None:
        write_json(LIBRARY_FILE, {
            "version": 1,
            "categories": self.categories,
            "games": [asdict(g) for g in self.games],
        })

    def get(self, game_id: str) -> Game | None:
        return next((g for g in self.games if g.id == game_id), None)

    def add(self, game: Game) -> None:
        self.games.append(game)
        game.folder.mkdir(parents=True, exist_ok=True)
        self.save()

    def remove(self, game: Game, delete_data: bool = True) -> None:
        self.games = [g for g in self.games if g.id != game.id]
        if delete_data:
            shutil.rmtree(game.folder, ignore_errors=True)
        self.save()

    # categories ------------------------------------------------------------
    def add_category(self, name: str) -> bool:
        name = name.strip()
        if not name or name in self.categories:
            return False
        self.categories.append(name)
        self.save()
        return True

    def rename_category(self, old: str, new: str) -> bool:
        new = new.strip()
        if not new or new in self.categories or old not in self.categories:
            return False
        self.categories[self.categories.index(old)] = new
        for g in self.games:
            g.categories = [new if c == old else c for c in g.categories]
        self.save()
        return True

    def delete_category(self, name: str) -> None:
        if name in self.categories:
            self.categories.remove(name)
        for g in self.games:
            if name in g.categories:
                g.categories.remove(name)
        self.save()
