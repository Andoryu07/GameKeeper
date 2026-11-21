"""Where a game's unlocks come from: per-game save-file rules."""
from __future__ import annotations

from . import triggers
from .storage import Game


def describe(game: Game) -> list[str]:
    """Human-readable list of active unlock sources."""
    out = []
    rules = triggers.rules_for(game.appid, game.exe)
    if rules:
        out.append(f"{rules.name} save files")
    return out


def manual_only(game: Game) -> dict[str, str]:
    rules = triggers.rules_for(game.appid, game.exe)
    return dict(rules.manual) if rules else {}


def read_unlocks(game: Game) -> dict[str, int]:
    """{api name: unlock time} from every source that applies to the game."""
    found: dict[str, int] = {}
    rules = triggers.rules_for(game.appid, game.exe)
    if rules:
        found.update(rules.read())
    return found
