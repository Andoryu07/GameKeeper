"""Where a game's unlocks come from: save-file rules and/or an emulator."""
from __future__ import annotations

from . import emulator, triggers
from .storage import Game


def describe(game: Game) -> list[str]:
    """Human-readable list of active unlock sources."""
    out = []
    rules = triggers.rules_for(game.appid, game.exe)
    if rules:
        out.append(f"{rules.name} save files")
    if game.emulator_installed:
        out.append("Steam API emulator")
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
    if game.emulator_installed:
        for k, v in emulator.read_unlocks(game).items():
            found.setdefault(k, v)
    return found
