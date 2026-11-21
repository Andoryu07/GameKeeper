"""Find the most likely game executable inside a folder the user picked."""
from __future__ import annotations

import os
import re
from pathlib import Path

# Executables that are almost never the game itself.
JUNK_PATTERNS = [
    r"unins\d*", r"uninstall", r"setup", r"install", r"redist", r"vcredist",
    r"vc_redist", r"dxsetup", r"dxwebsetup", r"directx", r"dotnet", r"physx",
    r"crash", r"report", r"unitycrashhandler", r"ue4prereq", r"ueprereq",
    r"prereq", r"easyanticheat", r"battleye", r"beservice", r"cleanup",
    r"touchup", r"updater", r"update", r"patcher", r"helper", r"overlay",
    r"benchmark", r"dump", r"debug", r"server", r"editor", r"cefprocess",
    r"subprocess", r"notification", r"quicksfv", r"oalinst",
]
JUNK_RE = re.compile(r"^(" + "|".join(JUNK_PATTERNS) + r")|(" + "|".join(JUNK_PATTERNS) + r")$", re.I)
JUNK_DIRS = {"_commonredist", "redist", "redistributables", "directx", "vcredist",
             "support", "installers", "__installer", "_redist", "dotnet", "easyanticheat",
             "battleye", "engine"}

MAX_DEPTH = 4


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_executables(folder: str | Path) -> list[Path]:
    """Return .exe files under ``folder`` ranked best-first."""
    root = Path(folder)
    found: list[tuple[float, Path]] = []
    root_depth = len(root.parts)
    folder_key = _normalize(root.name)

    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - root_depth
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d.lower() not in JUNK_DIRS]
        for fn in filenames:
            if not fn.lower().endswith(".exe"):
                continue
            path = Path(dirpath) / fn
            found.append((_score(path, depth, folder_key), path))

    found.sort(key=lambda t: (-t[0], str(t[1]).lower()))
    return [p for _, p in found]


def _score(path: Path, depth: int, folder_key: str) -> float:
    stem = path.stem
    key = _normalize(stem)
    score = 0.0
    if JUNK_RE.search(stem.replace(" ", "").replace("-", "").replace("_", "")):
        score -= 100
    if folder_key and key and (key in folder_key or folder_key in key):
        score += 40
    # Unreal games: the real binary is Game-Win64-Shipping.exe deep inside,
    # but the top-level launcher is the one to start.
    if "shipping" in key:
        score -= 10
    score -= depth * 5
    try:
        score += min(path.stat().st_size / (1024 * 1024), 30)  # bigger = likelier, capped
    except OSError:
        pass
    return score


def guess_name(folder: str | Path) -> str:
    """Turn a folder name like 'Hollow_Knight' into 'Hollow Knight'."""
    name = Path(folder).name
    name = re.sub(r"[_.]+", " ", name)
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    return re.sub(r"\s+", " ", name).strip()
