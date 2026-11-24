"""Achievement tracking through a Steam API emulator.

Steam games unlock achievements by calling ``steam_api.dll`` /
``steam_api64.dll``. A Steam API emulator (the open-source ``gbe_fork``,
built from source as described in EMULATOR.md) is a drop-in replacement for
that DLL that runs without Steam and writes unlocks to a local
``achievements.json``. GameKeeper:

1. backs up the game's original DLL(s) and copies in the emulator DLL(s)
   from the folder set in Settings,
2. writes ``steam_settings/`` next to each DLL (app id + achievement list),
3. watches the emulator's save file while the game runs and shows a popup
   for each new unlock.

``restore`` puts the original DLLs back. Games protected by Steam's DRM
wrapper won't start with an emulator; GameKeeper doesn't handle that.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .storage import AchievementSet, Game, read_json, write_json

DLL_NAMES = ("steam_api.dll", "steam_api64.dll")
BACKUP_SUFFIX = ".gamekeeper-original"


class EmulatorError(Exception):
    pass


def find_steam_dlls(game_dir: Path) -> list[Path]:
    found = []
    for dirpath, _dirs, files in os.walk(game_dir):
        for fn in files:
            if fn.lower() in DLL_NAMES:
                found.append(Path(dirpath) / fn)
    return found


def is_installed(game: Game) -> bool:
    dlls = find_steam_dlls(game.game_dir)
    return bool(dlls) and all(_backup(d).exists() for d in dlls)


def _backup(dll: Path) -> Path:
    return dll.with_name(dll.name + BACKUP_SUFFIX)


def install(game: Game, emulator_dir: str) -> list[Path]:
    """Swap the game's Steam DLLs for the emulator's. Returns DLLs replaced."""
    if not game.appid:
        raise EmulatorError("Link the game to Steam first (the emulator needs its app id).")
    emu = Path(emulator_dir)
    if not emulator_dir or not emu.is_dir():
        raise EmulatorError("Set the emulator folder in Settings first.")
    dlls = find_steam_dlls(game.game_dir)
    if not dlls:
        raise EmulatorError("No steam_api.dll or steam_api64.dll found in the game folder.\n"
                            "This game may not use Steam achievements.")

    replaced = []
    for dll in dlls:
        src = _find_emu_dll(emu, dll.name.lower())
        if src is None:
            raise EmulatorError(f"The emulator folder has no {dll.name}.")
        backup = _backup(dll)
        if not backup.exists():           # never overwrite the real original
            shutil.copy2(dll, backup)
        shutil.copy2(src, dll)
        write_steam_settings(game, dll.parent)
        replaced.append(dll)
    return replaced


def _find_emu_dll(emu: Path, name: str) -> Path | None:
    direct = emu / name
    if direct.exists():
        return direct
    # release archives keep the DLLs in sub-folders (e.g. regular/x64/)
    matches = [p for p in emu.rglob("*") if p.name.lower() == name]
    matches.sort(key=lambda p: ("experimental" in str(p).lower(), "debug" in str(p).lower(), len(p.parts)))
    return matches[0] if matches else None


def restore(game: Game) -> int:
    """Put the original Steam DLLs back. Returns how many were restored."""
    count = 0
    for dll in find_steam_dlls(game.game_dir):
        backup = _backup(dll)
        if backup.exists():
            shutil.copy2(backup, dll)
            backup.unlink()
            count += 1
    return count


def write_steam_settings(game: Game, dll_dir: Path) -> None:
    """Write steam_settings/ so the emulator knows the app id and achievements."""
    settings_dir = dll_dir / "steam_settings"
    settings_dir.mkdir(exist_ok=True)
    (dll_dir / "steam_appid.txt").write_text(str(game.appid))
    (settings_dir / "steam_appid.txt").write_text(str(game.appid))

    achset = AchievementSet(game.id)
    if not achset.items:
        return
    images = settings_dir / "images"
    images.mkdir(exist_ok=True)
    out = []
    for a in achset.items:     # permanently deleted ones aren't in the list at all
        entry = {
            "name": a.api_name,
            "displayName": a.name or a.api_name,
            "description": a.description,
            "hidden": 1 if a.hidden else 0,
        }
        for key, fn in (("icon", a.icon), ("icon_gray", a.icon_gray)):
            if fn and (achset.icons_dir / fn).exists():
                shutil.copy2(achset.icons_dir / fn, images / fn)
                entry[key] = f"images/{fn}"
        if "icon_gray" in entry:
            entry["icongray"] = entry["icon_gray"]  # older emulator builds use this key
        out.append(entry)
    with open(settings_dir / "achievements.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Reading unlocks
# --------------------------------------------------------------------------- #
def save_file_candidates(game: Game) -> list[Path]:
    """Places the emulator may write its achievements.json to."""
    paths: list[Path] = []
    if game.appid:
        appdata = os.environ.get("APPDATA")
        if appdata:
            for folder in ("GSE Saves", "Goldberg SteamEmu Saves"):
                paths.append(Path(appdata) / folder / str(game.appid) / "achievements.json")
        # a custom save folder set in the emulator's steam_settings/configs.user.ini
        for dll in find_steam_dlls(game.game_dir):
            local = _local_save_path(dll.parent)
            if local:
                paths.append(local / str(game.appid) / "achievements.json")
    return paths


def _local_save_path(dll_dir: Path) -> Path | None:
    ini = dll_dir / "steam_settings" / "configs.user.ini"
    try:
        text = ini.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    section = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
        elif section == "user::saves" and line.lower().startswith("local_save_path") and "=" in line:
            value = line.split("=", 1)[1].strip()
            if value:
                p = Path(value)
                return p if p.is_absolute() else dll_dir / p
    return None


def save_folder(game: Game) -> Path | None:
    """Where the emulator keeps this game's data (achievements and Steam-cloud saves)."""
    if not game.appid:
        return None
    for dll in find_steam_dlls(game.game_dir):
        local = _local_save_path(dll.parent)
        if local:
            return local / str(game.appid)
    appdata = os.environ.get("APPDATA")
    return Path(appdata) / "GSE Saves" / str(game.appid) if appdata else None


def read_unlocks(game: Game) -> dict[str, int]:
    """Return {api_name: unlock_time} from every emulator save file found."""
    unlocks: dict[str, int] = {}
    for path in save_file_candidates(game):
        data = read_json(path, None)
        if not isinstance(data, dict):
            continue
        for name, info in data.items():
            if isinstance(info, dict) and info.get("earned"):
                unlocks[name] = int(info.get("earned_time") or 0)
    return unlocks


def push_unlocks(game: Game) -> None:
    """Write GameKeeper's unlocks into the emulator's save file.

    Keeps the game's own achievement list in sync with unlocks imported
    from Steam or set by hand, so it won't pop them again.
    """
    if not game.appid:
        return
    achset = AchievementSet(game.id)
    existing = [p for p in save_file_candidates(game) if p.exists()]
    if existing:
        path = existing[0]
    elif os.environ.get("APPDATA"):
        path = Path(os.environ["APPDATA"]) / "GSE Saves" / str(game.appid) / "achievements.json"
    else:
        return
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    for a in achset.items:
        if a.unlocked and not data.get(a.api_name, {}).get("earned"):
            data[a.api_name] = {"earned": True, "earned_time": a.unlock_time}
    write_json(path, data)
