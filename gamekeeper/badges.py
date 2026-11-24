"""Badges: 5 levels per game, crafted with achievement points.

Points
------
Every achievement is worth points based on how rare it is (global unlock
percentage), so hard achievements level a badge faster than easy ones:

    under 5% of players  50      under 20%  30      50% or more  10
    under 10%            40      under 50%  20      rarity unknown 20

A game's points only come from its own achievements (excluded and deleted
ones don't count). Badge levels cost 1/5 of the game's total points each, so
unlocking every achievement is exactly enough for level 5.

Each crafted level gives 100 profile XP, like Steam. Profile levels need
100 XP each for levels 1-10, 200 each for 11-20, 300 for 21-30, and so on.

Badge art
---------
Names and images for games with Steam trading cards come from
SteamCardExchange (a fan site that lists every game's badges; the images
themselves are hosted by Steam). Other games get a GameKeeper badge drawn
in code.
"""
from __future__ import annotations

import html
import math
import re

import requests

from .storage import AchievementSet, Game, read_json, write_json

MAX_LEVEL = 5
XP_PER_LEVEL = 100
SCE_URL = "https://www.steamcardexchange.net/index.php?gamepage-appid-{appid}"
TIMEOUT = 20


def achievement_points(global_percent: float | None) -> int:
    if global_percent is None:
        return 20
    if global_percent < 5:
        return 50
    if global_percent < 10:
        return 40
    if global_percent < 20:
        return 30
    if global_percent < 50:
        return 20
    return 10


class BadgeProgress:
    """Points and level for one game."""

    def __init__(self, game: Game, achset: AchievementSet | None = None):
        self.game = game
        achset = achset or AchievementSet(game.id)
        counted = [a for a in achset.items if not a.excluded]
        self.total = sum(achievement_points(a.global_percent) for a in counted)
        self.earned = sum(achievement_points(a.global_percent) for a in counted if a.unlocked)
        self.level = min(game.badge_level, MAX_LEVEL)

    def cost_to_reach(self, level: int) -> int:
        """Total points spent once the badge is at ``level``."""
        return math.ceil(self.total * level / MAX_LEVEL)

    @property
    def spent(self) -> int:
        return self.cost_to_reach(self.level)

    @property
    def available(self) -> int:
        return self.earned - self.spent

    @property
    def next_cost(self) -> int:
        return self.cost_to_reach(self.level + 1) - self.spent if self.level < MAX_LEVEL else 0

    @property
    def can_craft(self) -> bool:
        return self.total > 0 and self.level < MAX_LEVEL and self.available >= self.next_cost


def craftable_levels(game: Game) -> int:
    """How many levels could be crafted right now (for the 'ready' markers)."""
    p = BadgeProgress(game)
    n = 0
    while p.level + n < MAX_LEVEL and p.earned >= p.cost_to_reach(p.level + n + 1) and p.total:
        n += 1
    return n


# --------------------------------------------------------------------------- #
# Profile level
# --------------------------------------------------------------------------- #
def profile_xp(games: list[Game]) -> int:
    return sum(min(g.badge_level, MAX_LEVEL) for g in games) * XP_PER_LEVEL


def xp_for_next(level: int) -> int:
    """XP needed to go from ``level`` to ``level + 1``."""
    return 100 * (level // 10 + 1)


def profile_level(xp: int) -> tuple[int, int, int]:
    """Returns (level, xp into this level, xp needed for the next level)."""
    level = 0
    while xp >= xp_for_next(level):
        xp -= xp_for_next(level)
        level += 1
    return level, xp, xp_for_next(level)


# --------------------------------------------------------------------------- #
# Badge art
# --------------------------------------------------------------------------- #
def badge_file(game: Game):
    return game.folder / "badge.json"


def badge_info(game: Game) -> dict:
    """{'source': 'steam' | 'generic', 'levels': [{'level', 'name', 'image'}]}."""
    return read_json(badge_file(game), {})


def level_name(game: Game, level: int) -> str:
    for lv in badge_info(game).get("levels", []):
        if lv.get("level") == level:
            return lv.get("name", "")
    return f"{game.name} - Level {level}"


def level_image(game: Game, level: int):
    for lv in badge_info(game).get("levels", []):
        if lv.get("level") == level and lv.get("image"):
            p = game.folder / lv["image"]
            return p if p.exists() else None
    return None


def parse_sce(page: str) -> list[dict]:
    """Pull the regular (non-foil) badge levels out of a SteamCardExchange page."""
    start = page.find('id="series-1-badges"')
    if start < 0:
        return []
    section = page[start:start + 20000]
    items = re.findall(
        r'<img[^>]+src="(https://[^"]+/items/\d+/[0-9a-f]+\.png)"[^>]*>\s*'
        r'<div[^>]*>([^<]+)</div>\s*<div[^>]*>\s*<div[^>]*>Level (\d+)</div>', section)
    levels = []
    for url, name, lvl in items:
        lvl = int(lvl)
        if 1 <= lvl <= MAX_LEVEL and all(x["level"] != lvl for x in levels):
            levels.append({"level": lvl, "name": html.unescape(name).strip(), "url": url})
    return sorted(levels, key=lambda x: x["level"])


def fetch_badge(game: Game, session: requests.Session | None = None) -> dict:
    """Download the game's badge names and images (or set up a generic badge)."""
    info = {"source": "generic", "levels": []}
    if game.appid:
        s = session or requests.Session()
        try:
            r = s.get(SCE_URL.format(appid=game.appid), timeout=TIMEOUT,
                      headers={"User-Agent": "GameKeeper/0.1"})
            levels = parse_sce(r.text) if r.status_code == 200 else []
        except requests.RequestException:
            levels = None          # offline: try again another time
        if levels is None:
            return badge_info(game)
        if len(levels) == MAX_LEVEL:
            game.folder.mkdir(parents=True, exist_ok=True)
            got = []
            for lv in levels:
                fn = f"badge_{lv['level']}.png"
                try:
                    img = s.get(lv["url"], timeout=TIMEOUT)
                    if img.status_code == 200 and img.content:
                        (game.folder / fn).write_bytes(img.content)
                    else:
                        fn = ""
                except requests.RequestException:
                    fn = ""
                got.append({"level": lv["level"], "name": lv["name"], "image": fn})
            info = {"source": "steam", "levels": got}
    game.folder.mkdir(parents=True, exist_ok=True)
    write_json(badge_file(game), info)
    return info
