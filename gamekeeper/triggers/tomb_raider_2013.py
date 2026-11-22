"""Tomb Raider (2013) achievement rules.

The save (a 4 MB binary file) isn't encrypted or compressed. Fields were
found by comparing saves made before and after known events:

* A table of per-area records starting at 0x30C, 0x24 bytes each, each
  beginning with -1. Inside a record: +0x04 relics, +0x08 documents,
  +0x10 challenges completed, +0x14 GPS caches. Summed over all areas these
  matched the in-game totals exactly (13 relics, 15 documents, 15 caches,
  3 challenges).
* A stats block of 32-bit counters:
    0x2C04 total salvage collected (confirmed against every salvage change)
    0x2C10 enemies looted (rises with salvage after kills)
    0x2C24 large animals killed and looted (+1 on a boar kill)
    0x2C30 headshots, 0x2C34 bow kills, 0x2C4C finishers (confirmed)
    0x2C3C shotgun kills, 0x2C40 handgun kills (one matching observation each)
    0x2C50 / 0x2C58 optional tombs raided (both read 2 with 2 tombs raided;
    the smaller is used until it's clear which one it is)

Game-wide totals (relics 42, GPS caches 75, challenges 13, tombs 7) come from
fan guides. Documents are 54 if Lara's journals count and 44 if not; 54 is
used so percentage unlocks are never early.

The save lives somewhere unusual depending on the version, so the user picks
it under Edit game -> Save file.
"""
from __future__ import annotations

import math
import struct
from pathlib import Path

from . import GameRules

SAVE_SIZE = 4 * 1024 * 1024
AREA_TABLE = 0x30C
AREA_STRIDE = 0x24
MAX_AREAS = 40

TOTAL_RELICS = 42
TOTAL_GPS = 75
TOTAL_DOCUMENTS = 54
TOTAL_CHALLENGES = 13
TOTAL_TOMBS = 7

STAT = {
    "salvage_collected": 0x2C04,
    "looted": 0x2C10,
    "large_animals": 0x2C24,
    "headshots": 0x2C30,
    "bow_kills": 0x2C34,
    "shotgun_kills": 0x2C3C,
    "handgun_kills": 0x2C40,
    "finishers": 0x2C4C,
    "tombs_a": 0x2C50,
    "tombs_b": 0x2C58,
}


def _pct(total: int, fraction: float) -> int:
    return math.ceil(total * fraction)


def read_save(path: Path) -> dict[str, int] | None:
    """Parse the numbers GameKeeper uses; None if this doesn't look like a TR save."""
    data = path.read_bytes()
    if len(data) != SAVE_SIZE:
        return None
    year = struct.unpack_from("<H", data, 8)[0]
    if not 2013 <= year <= 2200:          # the save starts with its date
        return None
    out = {k: struct.unpack_from("<i", data, off)[0] for k, off in STAT.items()}
    relics = documents = challenges = gps = 0
    for i in range(MAX_AREAS):
        base = AREA_TABLE + i * AREA_STRIDE
        if struct.unpack_from("<i", data, base)[0] != -1:
            break
        relics += struct.unpack_from("<i", data, base + 0x04)[0]
        documents += struct.unpack_from("<i", data, base + 0x08)[0]
        challenges += struct.unpack_from("<i", data, base + 0x10)[0]
        gps += struct.unpack_from("<i", data, base + 0x14)[0]
    out.update(relics=relics, documents=documents, challenges=challenges, gps=gps,
               tombs=min(out["tombs_a"], out["tombs_b"]))
    return out


class TombRaider2013(GameRules):
    name = "Tomb Raider"
    appids = {203160}
    exe_names = {"tombraider.exe"}
    needs_save_path = True
    manual = {
        "NEW_ACHIEVEMENT_2_9": "Skill purchases aren't read from the save yet.",
        "NEW_ACHIEVEMENT_2_10": "Skill purchases aren't read from the save yet.",
        "NEW_ACHIEVEMENT_2_11": "Weapon upgrades aren't read from the save yet.",
        "NEW_ACHIEVEMENT_2_12": "Weapon upgrades aren't read from the save yet.",
        "NEW_ACHIEVEMENT_2_14": "Small animal kills aren't identified in the save yet.",
        "NEW_ACHIEVEMENT_2_15": "Flying animal kills aren't identified in the save yet.",
        "NEW_ACHIEVEMENT_2_18": "Rifle kills aren't identified in the save yet.",
        "NEW_ACHIEVEMENT_2_21": "A one-off moment the save doesn't record.",
        "NEW_ACHIEVEMENT_2_22": "Rope pulls aren't identified in the save yet.",
        "NEW_ACHIEVEMENT_2_23": "Unaware kills aren't identified in the save yet.",
        "NEW_ACHIEVEMENT_2_25": "Zip line kills aren't identified in the save yet.",
        "NEW_ACHIEVEMENT_2_26": "Dodge counters aren't identified in the save yet.",
        "NEW_ACHIEVEMENT_2_31": "Finishing the game isn't detected from the save yet.",
        "NEW_ACHIEVEMENT_3_0": "A one-off moment the save doesn't record.",
        "NEW_ACHIEVEMENT_3_1": "A one-off moment the save doesn't record.",
        "NEW_ACHIEVEMENT_3_2": "Conversations aren't identified in the save yet.",
    }

    def watch_files(self) -> list[Path]:
        return [self.save_path] if self.save_path else []

    def evaluate(self) -> dict[str, int]:
        if not self.save_path or not self.save_path.exists():
            return {}
        s = read_save(self.save_path)
        if s is None:
            return {}
        rules = {
            "NEW_ACHIEVEMENT_2_0": s["documents"] >= _pct(TOTAL_DOCUMENTS, 0.25),   # Bookworm
            "NEW_ACHIEVEMENT_2_1": s["documents"] >= _pct(TOTAL_DOCUMENTS, 0.75),   # Historian
            "NEW_ACHIEVEMENT_2_2": s["relics"] >= _pct(TOTAL_RELICS, 0.25),         # Relic Hunter
            "NEW_ACHIEVEMENT_2_3": s["relics"] >= _pct(TOTAL_RELICS, 0.75),         # Archaeologist
            "NEW_ACHIEVEMENT_2_4": s["gps"] >= _pct(TOTAL_GPS, 0.25),               # Looking for Trouble
            "NEW_ACHIEVEMENT_2_5": s["gps"] >= _pct(TOTAL_GPS, 0.75),               # Bag Full O' Cache
            "NEW_ACHIEVEMENT_2_6": (s["documents"] >= TOTAL_DOCUMENTS and s["relics"] >= TOTAL_RELICS
                                    and s["gps"] >= TOTAL_GPS),                    # No Stone Left Unturned
            "NEW_ACHIEVEMENT_2_7": s["salvage_collected"] >= 5000,                  # Scrounger
            "NEW_ACHIEVEMENT_2_8": s["looted"] >= 200,                              # Picky
            "NEW_ACHIEVEMENT_2_13": s["large_animals"] >= 10,                       # Big Game Hunter
            "NEW_ACHIEVEMENT_2_16": s["headshots"] >= 50,                           # Sharp Shooter
            "NEW_ACHIEVEMENT_2_17": s["bow_kills"] >= 50,                           # Predator
            "NEW_ACHIEVEMENT_2_19": s["shotgun_kills"] >= 40,                       # Widowmaker
            "NEW_ACHIEVEMENT_2_20": s["handgun_kills"] >= 35,                       # Gunslinger
            "NEW_ACHIEVEMENT_2_24": s["finishers"] >= 15,                           # Down and Dirty
            "NEW_ACHIEVEMENT_2_27": s["tombs"] >= 1,                                # One Smart Cookie
            "NEW_ACHIEVEMENT_2_28": s["tombs"] >= TOTAL_TOMBS,                      # Intellectually Superior
            "NEW_ACHIEVEMENT_2_29": s["challenges"] >= 1,                           # Unfinished Business
            "NEW_ACHIEVEMENT_2_30": s["challenges"] >= TOTAL_CHALLENGES,            # Inconceivable!
        }
        when = int(self.save_path.stat().st_mtime)
        return {name: when for name, earned in rules.items() if earned}


RULES = TombRaider2013()
