"""Pulls game data from Steam: search, cover art and achievement lists.

Search, cover art and global unlock percentages need no account. Achievement
names, descriptions and icons need a free Steam Web API key
(https://steamcommunity.com/dev/apikey). Importing your own unlocks and
playtime also needs your SteamID and a public "Game details" privacy setting.
"""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import requests

from .storage import Achievement, AchievementSet, Game, Settings

API = "https://api.steampowered.com"
STORE = "https://store.steampowered.com"
CDN = "https://cdn.akamai.steamstatic.com/steam/apps"
TIMEOUT = 20

session = requests.Session()
session.headers["User-Agent"] = "GameKeeper/0.1"


class SteamError(Exception):
    pass


def _get(url: str, **params) -> dict:
    try:
        r = session.get(url, params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise SteamError(f"Could not reach Steam: {e}") from e
    if r.status_code == 403:
        raise SteamError("Steam refused the request (403). Check your API key, "
                         "and that your profile's game details are public.")
    if r.status_code != 200:
        raise SteamError(f"Steam returned HTTP {r.status_code} for {url.split('?')[0]}")
    try:
        return r.json()
    except ValueError as e:
        raise SteamError("Steam returned an unexpected response.") from e


# --------------------------------------------------------------------------- #
# Search and artwork
# --------------------------------------------------------------------------- #
def search(term: str) -> list[dict]:
    """Search the Steam store. Returns [{'appid', 'name', 'image'}]."""
    term = term.strip()
    if term.isdigit():  # typed an app id directly
        info = app_details(int(term))
        return [{"appid": int(term), "name": info.get("name", term), "image": info.get("header_image", "")}] if info else []
    data = _get(f"{STORE}/api/storesearch/", term=term, cc="us", l="english")
    return [{"appid": it["id"], "name": it["name"], "image": it.get("tiny_image", "")}
            for it in data.get("items", []) if it.get("type") == "app"]


def app_details(appid: int) -> dict:
    data = _get(f"{STORE}/api/appdetails", appids=appid, filters="basic")
    entry = data.get(str(appid), {})
    return entry.get("data", {}) if entry.get("success") else {}


def _download(url: str, dest: Path) -> bool:
    try:
        r = session.get(url, timeout=TIMEOUT)
    except requests.RequestException:
        return False
    if r.status_code != 200 or not r.content or not r.headers.get("content-type", "").startswith("image"):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return True


def download_artwork(game: Game) -> None:
    if not game.appid:
        return
    a = game.appid
    if not _download(f"{CDN}/{a}/library_600x900_2x.jpg", game.cover_path):
        if not _download(f"{CDN}/{a}/library_600x900.jpg", game.cover_path):
            _download(f"{CDN}/{a}/header.jpg", game.cover_path)
    _download(f"{CDN}/{a}/library_hero.jpg", game.hero_path) or \
        _download(f"{CDN}/{a}/page_bg_generated_v6b.jpg", game.hero_path)


# --------------------------------------------------------------------------- #
# Achievements
# --------------------------------------------------------------------------- #
def global_percentages(appid: int) -> dict[str, float]:
    try:
        data = _get(f"{API}/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/", gameid=appid)
    except SteamError:
        return {}
    return {a["name"]: float(a["percent"])
            for a in data.get("achievementpercentages", {}).get("achievements", [])}


def _icon_file(url: str) -> str:
    """Stable local file name for an icon URL."""
    ext = Path(url.split("?")[0]).suffix or ".jpg"
    return hashlib.sha1(url.encode()).hexdigest()[:16] + ext


def fetch_achievements(game: Game, settings: Settings, progress=None) -> AchievementSet:
    """Download the achievement list (and icons) for a game.

    Keeps any unlocks already recorded, so re-fetching is safe.
    ``progress(done, total)`` is called while icons download.
    """
    if not game.appid:
        raise SteamError("This game isn't linked to a Steam app yet.")

    achset = AchievementSet(game.id)
    old = achset.by_name()
    percents = global_percentages(game.appid)
    items: list[Achievement] = []
    icon_jobs: list[tuple[str, Path]] = []

    if settings.steam_api_key:
        data = _get(f"{API}/ISteamUserStats/GetSchemaForGame/v2/",
                    key=settings.steam_api_key, appid=game.appid, l=settings.language)
        schema = data.get("game", {}).get("availableGameStats", {}).get("achievements", [])
        for s in schema:
            icon = _icon_file(s["icon"]) if s.get("icon") else ""
            gray = _icon_file(s["icongray"]) if s.get("icongray") else ""
            if icon:
                icon_jobs.append((s["icon"], achset.icons_dir / icon))
            if gray:
                icon_jobs.append((s["icongray"], achset.icons_dir / gray))
            items.append(Achievement(
                api_name=s["name"],
                name=s.get("displayName", ""),
                description=s.get("description", ""),
                hidden=bool(s.get("hidden")),
                icon=icon, icon_gray=gray,
                global_percent=percents.get(s["name"]),
            ))
    else:
        # Without a key we only get the internal names. Still enough to track.
        for name, pct in percents.items():
            items.append(Achievement(api_name=name, name=_pretty(name), global_percent=pct))

    if not items:
        raise SteamError("Steam has no achievements listed for this game."
                         + ("" if settings.steam_api_key else
                            " (Add a Steam API key in Settings for full achievement data.)"))

    # carry over unlock state
    for a in items:
        prev = old.get(a.api_name)
        if prev and prev.unlocked:
            a.unlocked, a.unlock_time, a.source = True, prev.unlock_time, prev.source

    total = len(icon_jobs)
    for i, (url, dest) in enumerate(icon_jobs, 1):
        if not dest.exists():
            _download(url, dest)
        if progress:
            progress(i, total)

    achset.items = items
    achset.fetched_at = int(time.time())
    achset.save()
    return achset


def _pretty(api_name: str) -> str:
    s = re.sub(r"^(ACH(IEVEMENT)?|NEW_ACHIEVEMENT)_?", "", api_name, flags=re.I)
    s = re.sub(r"[_\-]+", " ", s).strip()
    return s.title() if s else api_name


# --------------------------------------------------------------------------- #
# Importing your own Steam progress
# --------------------------------------------------------------------------- #
def resolve_steam_id(settings: Settings) -> str:
    sid = settings.steam_id.strip()
    m = re.search(r"steamcommunity\.com/(id|profiles)/([^/]+)", sid)
    if m:
        sid = m.group(2)
    if sid.isdigit() and len(sid) == 17:
        return sid
    if not settings.steam_api_key:
        raise SteamError("An API key is needed to look up a custom profile name.")
    data = _get(f"{API}/ISteamUser/ResolveVanityURL/v1/", key=settings.steam_api_key, vanityurl=sid)
    resp = data.get("response", {})
    if resp.get("success") != 1:
        raise SteamError(f"Couldn't find a Steam profile called '{sid}'.")
    return resp["steamid"]


def import_progress(game: Game, settings: Settings) -> tuple[list[Achievement], int]:
    """Copy unlocks and playtime from your Steam account.

    Returns (newly unlocked achievements, imported playtime in seconds).
    """
    if not (settings.steam_api_key and settings.steam_id):
        raise SteamError("Set your Steam API key and Steam ID in Settings first.")
    if not game.appid:
        raise SteamError("This game isn't linked to a Steam app yet.")
    sid = resolve_steam_id(settings)
    key = settings.steam_api_key

    achset = AchievementSet(game.id)
    new: list[Achievement] = []
    if achset.items:
        data = _get(f"{API}/ISteamUserStats/GetPlayerAchievements/v1/",
                    key=key, steamid=sid, appid=game.appid)
        stats = data.get("playerstats", {})
        if not stats.get("success", True):
            raise SteamError(stats.get("error", "Steam couldn't return your achievements."))
        for a in stats.get("achievements", []):
            if a.get("achieved"):
                got = achset.unlock(a["apiname"], a.get("unlocktime") or None, source="steam")
                if got:
                    new.append(got)
        achset.save()

    playtime = 0
    data = _get(f"{API}/IPlayerService/GetOwnedGames/v1/", key=key, steamid=sid,
                include_played_free_games=1, **{"appids_filter[0]": game.appid})
    for g in data.get("response", {}).get("games", []):
        if g.get("appid") == game.appid:
            playtime = int(g.get("playtime_forever", 0)) * 60
            if g.get("rtime_last_played") and not game.last_played:
                game.last_played = int(g["rtime_last_played"])
    return new, playtime
