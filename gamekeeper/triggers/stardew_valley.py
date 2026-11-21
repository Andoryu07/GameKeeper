"""Stardew Valley achievement rules.

Stardew keeps its own list of earned achievements inside each save (the game
also runs on platforms without Steam), stored as numbers in the farmer's
``<achievements>`` element. Those numbers are exactly the Steam achievement
ids ``a0``, ``1``, ``2``... so most achievements come straight from the save.

The remaining Steam achievements (named ``Achievement_*``) are only reported
to Steam, so they're worked out from other things in the save instead.

Saves live in ``%APPDATA%\\StardewValley\\Saves\\<Farm>_<id>\\``. Each farm
folder holds ``SaveGameInfo`` (the farmer, small) and a file with the folder's
name (the whole world). The game writes them when you sleep at the end of a
day, so unlocks show up when the day ends, just like in the game.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from . import GameRules

SKILLS = ("farmingLevel", "miningLevel", "combatLevel", "foragingLevel", "fishingLevel")
JOJA_PERKS = ("jojaBoilerRoom", "jojaCraftsRoom", "jojaFishTank", "jojaPantry", "jojaVault")
MAX_STAMINA_ALL_STARDROPS = 270 + 7 * 34    # base energy + 34 per stardrop, 7 stardrops


def saves_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "StardewValley" / "Saves"
    return Path.home() / ".config" / "StardewValley" / "Saves"


def _int(el: ET.Element | None, default: int = 0) -> int:
    try:
        return int(el.text) if el is not None and el.text else default
    except ValueError:
        return default


class StardewValley(GameRules):
    name = "Stardew Valley"
    appids = {413150}
    exe_names = {"stardew valley.exe", "stardewvalley.exe"}
    manual = {
        "Achievement_FectorsChallenge": "The save doesn't record whether you died in the arcade game.",
        "Achievement_KeeperOfTheMysticRings": "Monster Slayer goals aren't checked from the save yet.",
    }

    def farms(self) -> list[Path]:
        d = saves_dir()
        if not d.is_dir():
            return []
        return [f for f in d.iterdir() if f.is_dir() and (f / "SaveGameInfo").exists()]

    def watch_files(self) -> list[Path]:
        return [f / "SaveGameInfo" for f in self.farms()]

    def evaluate(self) -> dict[str, int]:
        earned: dict[str, int] = {}
        for farm in self.farms():
            info = farm / "SaveGameInfo"
            when = int(info.stat().st_mtime)
            for name in self._farm_achievements(farm, info):
                earned.setdefault(name, when)
        return earned

    def _farm_achievements(self, farm: Path, info: Path) -> set[str]:
        root = ET.parse(info).getroot()     # <Farmer>
        got: set[str] = set()

        # 1. The game's own achievement list -> Steam ids
        for el in root.findall("./achievements/int"):
            n = _int(el, -1)
            if n >= 0:
                got.add("a0" if n == 0 else str(n))

        # 2. Steam-only achievements, derived from the save
        mail = {el.text for el in root.findall("./mailReceived/string") if el.text}
        levels = [_int(root.find(s)) for s in SKILLS]

        if _int(root.find("deepestMineLevel")) >= 120:
            got.add("Achievement_TheBottom")
        if "ccIsComplete" in mail:
            got.add("Achievement_LocalLegend")
        if all(p in mail for p in JOJA_PERKS):
            got.add("Achievement_Joja")
        if "Beat_PK" in mail:
            got.add("Achievement_PrairieKing")
        if _int(root.find("maxStamina")) >= MAX_STAMINA_ALL_STARDROPS:
            got.add("Achievement_Stardrop")
        if any(lv >= 10 for lv in levels):
            got.add("Achievement_SingularTalent")
        if all(lv >= 10 for lv in levels):
            got.add("Achievement_MasterOfTheFiveWays")

        spouse = root.find("spouse")
        if spouse is not None and (spouse.text or "").strip():
            if self._children(farm) >= 2:
                got.add("Achievement_FullHouse")
        return got

    @staticmethod
    def _children(farm: Path) -> int:
        """Count children living on the farm (only stored in the big world file)."""
        world = farm / farm.name
        try:
            text = world.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return 0
        return len(re.findall(r'xsi:type="Child"', text))


RULES = StardewValley()
