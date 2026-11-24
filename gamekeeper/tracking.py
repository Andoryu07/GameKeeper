"""Where a game's unlocks come from: per-game save-file rules."""
from __future__ import annotations

from . import triggers
from pathlib import Path

from .storage import Game


def describe(game: Game) -> list[str]:
    """Human-readable list of active unlock sources."""
    out = []
    rules = triggers.rules_for(game.appid, game.exe)
    if rules and (not rules.needs_save_path or game.save_path):
        out.append(f"{rules.name} save files")
    return out


def needs_save_path(game: Game) -> bool:
    """Rules exist for this game but can't run until its save file is chosen."""
    rules = triggers.rules_for(game.appid, game.exe)
    return bool(rules and rules.needs_save_path and not game.save_path)


def manual_only(game: Game) -> dict[str, str]:
    rules = triggers.rules_for(game.appid, game.exe)
    return dict(rules.manual) if rules else {}


def read_unlocks(game: Game) -> dict[str, int]:
    """{api name: unlock time} from every source that applies to the game."""
    found: dict[str, int] = {}
    rules = triggers.rules_for(game.appid, game.exe)
    if rules and (not rules.needs_save_path or game.save_path):
        rules.save_path = Path(game.save_path) if game.save_path else None
        found.update(rules.read())
    return found
