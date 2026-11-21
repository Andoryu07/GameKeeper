"""Per-game achievement rules that read a game's own save files.

Each module in this package describes one game: where its saves are and how
to tell from them which achievements are earned. GameKeeper checks the saves
while the game runs and unlocks achievements as the save changes. Nothing in
the game folder is modified.

Adding a game
-------------
Create ``gamekeeper/triggers/<game>.py`` with a subclass of ``GameRules`` and
a module-level ``RULES = MyGame()``. Implement ``watch_files`` and
``evaluate``; see ``stardew_valley.py`` for a full example.
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path


class GameRules:
    #: Display name
    name: str = ""
    #: Steam app ids this applies to
    appids: set[int] = set()
    #: Executable names (lower case) for matching games not linked to Steam
    exe_names: set[str] = set()
    #: Achievements that can't be read from the save: {api name: reason}
    manual: dict[str, str] = {}

    def __init__(self):
        self._sig = None
        self._cache: dict[str, int] = {}

    def watch_files(self) -> list[Path]:
        """Files whose changes mean the game saved."""
        raise NotImplementedError

    def evaluate(self) -> dict[str, int]:
        """Return {achievement api name: unlock time (0 if unknown)}."""
        raise NotImplementedError

    def read(self) -> dict[str, int]:
        """``evaluate()``, but only re-run when a watched file changed."""
        sig = []
        for p in self.watch_files():
            try:
                st = p.stat()
                sig.append((str(p), st.st_mtime_ns, st.st_size))
            except OSError:
                pass
        sig = tuple(sorted(sig))
        if sig != self._sig:
            try:
                self._cache = self.evaluate()
            except Exception:  # noqa: BLE001 - a half-written save shouldn't stop tracking
                import traceback
                traceback.print_exc()
                return self._cache   # try again next time
            self._sig = sig
        return dict(self._cache)


_registry: list[GameRules] | None = None


def all_rules() -> list[GameRules]:
    global _registry
    if _registry is None:
        _registry = []
        for mod in pkgutil.iter_modules(__path__):
            m = importlib.import_module(f"{__name__}.{mod.name}")
            rules = getattr(m, "RULES", None)
            if isinstance(rules, GameRules):
                _registry.append(rules)
    return _registry


def rules_for(appid: int | None, exe: str = "") -> GameRules | None:
    exe_name = Path(exe).name.lower() if exe else ""
    for r in all_rules():
        if (appid and appid in r.appids) or (exe_name and exe_name in r.exe_names):
            return r
    return None
