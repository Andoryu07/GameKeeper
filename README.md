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

Cover art and global unlock percentages work out of the box. For achievement
names, descriptions and icons, add a free Steam Web API key in **Settings**
(get one at <https://steamcommunity.com/dev/apikey>; any domain name works).

To bring over achievements you've already earned and your Steam playtime, also
add your Steam ID in Settings and use **Manage → Steam data → Import my
unlocks and playtime**. Your Steam profile's *Game details* need to be public.

### Automatic unlocks while playing

Steam games report achievements through `steam_api.dll` / `steam_api64.dll`.
GameKeeper can swap that file for a Steam API emulator, which records unlocks
locally instead of sending them to Steam. GameKeeper watches that record while
you play and shows the popup.

1. Download a Steam API emulator release, for example
   [gbe_fork](https://github.com/Detanup01/gbe_fork/releases) (the maintained
   fork of the Goldberg emulator), and extract it anywhere.
2. In **Settings → Emulator folder**, pick the extracted folder.
3. On a game's page: pull the achievement list first, then
   **Manage → Achievement tracking → Set up automatic tracking**.

GameKeeper backs up the original DLLs (`*.gamekeeper-original`) and writes the
emulator's `steam_settings/` folder with the app id and achievement list.
**Restore original Steam files** puts everything back.

Limitations:

- Only for offline, single-player games. Don't use it on anything with online
  play or anti-cheat.
- Games protected by Steam's DRM wrapper won't start with an emulator.
- Unlocks stay in GameKeeper and don't sync back to your Steam profile.

Games that can't use the emulator can still have their achievement list:
right-click an achievement to unlock it by hand.

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
  emulator.py           DLL swap/restore, steam_settings, reading unlocks
  runner.py             launching games, playtime, watching for unlocks
  ui/                   the Qt interface
```
