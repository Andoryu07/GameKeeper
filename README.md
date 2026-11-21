# GameKeeper

A personal game launcher for Windows with its own achievement system, built
for keeping a game collection playable and tracked without depending on a
store client.

- **Library**: add games one at a time by picking their folder. GameKeeper
  finds the right `.exe` and skips installers, crash handlers and redistributables.
- **Categories**: make your own lists (Retro, Emulated, Backlog...). A game
  can be in several. Also built in: Favorites, Recently played and Uncategorized.
- **Playtime**: tracked like Steam does, per game, saved every minute so a
  crash doesn't lose it. Your existing Steam playtime can be imported.
- **Achievements**: pulled from Steam for a game when you choose to (e.g. when
  you start a new playthrough). Unlocks pop up over the game, with icons,
  unlock dates and global rarity.

## Getting started

1. Install [Python 3.11+](https://www.python.org/downloads/). Tick "Add python.exe to PATH".
2. In this folder, run:

   ```bash
   py -m pip install -r requirements.txt
   ```

3. Start it with `py main.py`, or double-click `GameKeeper.bat` (no console window).

If `python` or `py` gives "The system cannot find the path specified", Windows is
using its Microsoft Store placeholder instead of a real Python. Install Python
from python.org, then turn off *App Installer (python.exe / python3.exe)* under
Settings → *Manage app execution aliases*, and open a new terminal.

Everything GameKeeper stores (library, covers, achievements, playtime,
settings) goes in the `data/` folder next to `main.py`. Back up that folder
and you've backed up everything.

## Adding a game

Click **+ Add game**, pick the game's folder, and check the suggested
executable. Search Steam to link the game if it's a Steam game; that's what
gives it cover art and achievements. For emulated or retro games, choose
"Not a Steam game" and put the ROM path or emulator flags in **Launch options**.

Untick "Download cover art and achievements now" if you'd rather pull the data
later from the game's page (**Manage → Steam data**).

## Achievements

### Getting the achievement list

Pulling a game's data from Steam needs no Steam account or API key. You get
cover art and the full achievement list: names, descriptions, icons, hidden
flags and how many players have each one.

Optional: to bring over achievements you've already earned and your Steam
playtime, add a free Steam Web API key (<https://steamcommunity.com/dev/apikey>)
and your Steam ID in **Settings**, then use **Manage → Steam data → Import my
unlocks and playtime**. Your Steam profile's *Game details* need to be public.

### Automatic unlocks while playing

GameKeeper reads a supported game's own save files while you play and unlocks
achievements when the save shows you've earned them. It doesn't change any
game files. Progress you made before adding the game is picked up too, quietly,
without popups.

Supported games:

| Game | Automatic | By hand | Notes |
|---|---|---|---|
| Stardew Valley | 47 of 49 | Fector's Challenge, Protector Of The Valley | Unlocks appear when the day ends and the game saves. |

Each game's rules live in `gamekeeper/triggers/` (one file per game; see
`stardew_valley.py`). For games without rules, right-click an achievement to
unlock it by hand.

#### Optional: Steam API emulator

For Steam games with no save-file rules, GameKeeper can also swap the game's
`steam_api.dll` / `steam_api64.dll` for a Steam API emulator, which records
unlocks locally. Set the emulator's folder in **Settings**, pull the
achievement list, then use **Manage → Achievement tracking → Set up automatic
tracking**. The original DLLs are backed up (`*.gamekeeper-original`) and
**Restore original Steam files** puts them back.

> **Antivirus warning:** antivirus software often flags Steam API emulators,
> and downloads of them have been flagged as trojans. GameKeeper doesn't ship
> or download one. Only use an emulator you trust and never disable your
> antivirus for it. This is entirely optional.

Emulators only suit offline, single-player games, won't start games protected
by Steam's DRM wrapper, and their unlocks don't sync back to Steam.

### Run as administrator

Tick **Run as administrator** when adding a game or under **Edit**. Windows
shows its permission prompt each time the game starts. If a game needs admin
rights and the box isn't ticked, GameKeeper notices and offers to turn it on.

### Popups

The popup appears in the bottom-right corner over windowed and borderless
games. Exclusive fullscreen games draw over everything, so switch those to
borderless to see it. Sound and duration are in Settings.

## Project layout

```
main.py                 entry point
gamekeeper/
  storage.py            data folder, library, games, achievements
  scanner.py            finding the game .exe in a folder
  steam.py              Steam search, artwork, achievement data, imports
  triggers/             per-game rules that read save files for unlocks
  tracking.py           combines unlock sources for a game
  emulator.py           optional DLL swap/restore for a Steam API emulator
  runner.py             launching games, playtime, watching for unlocks
  winlaunch.py          starting games, including as administrator
  ui/                   the Qt interface
```
