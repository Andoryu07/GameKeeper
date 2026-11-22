# GameKeeper

A personal game launcher for Windows with its own achievement system, built
for keeping a game collection playable and tracked without depending on a
store client.

- **Library**: add games one at a time by picking their folder. GameKeeper
  finds the right `.exe` and skips installers, crash handlers and redistributables.
- **Collections**: make your own lists (Retro, Emulated, Backlog...). A game
  can be in several. Also built in: Favorites, Recently played and Uncategorized.
- **Ratings and reviews**: rate games 1-10 stars and write your thoughts.
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

3. Start it with `py main.py`, or double-click `GameKeeper.bat`.
4. On first start GameKeeper offers to put a shortcut on your desktop. After
   that, just double-click the shortcut. You can also create desktop and
   Start menu shortcuts any time in **Settings → Shortcuts**.

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

### Run as administrator

Tick **Run as administrator** when adding a game or under **Edit**. Windows
shows its permission prompt each time the game starts. If a game needs admin
rights and the box isn't ticked, GameKeeper notices and offers to turn it on.

### Popups

The popup appears in the bottom-right corner over windowed and borderless
games. Exclusive fullscreen games draw over everything, so switch those to
borderless to see it. Sound and duration are in Settings.

## Artwork

Linking a game to Steam downloads its cover, background, logo and small icon,
the same artwork Steam's library uses. Games added before an artwork type was
supported get it automatically the next time you open their page.

To use your own images (handy for retro and non-Steam games), use
**⚙ → Artwork → Set custom cover / background / logo / icon**. Custom artwork
is never overwritten by Steam data; **Use Steam artwork again** undoes it.

## Ratings and reviews

On a game's page, open the **REVIEW** tab to rate it from 1 to 10 stars and
write a review. Your rating shows on the game's page and under its cover, and
the library can be sorted by it. The **DETAILS** tab has the game's info and a
notes box.

## Your records are kept safe

- **Removing a game** moves it to the **Archive** (top bar) with its playtime,
  achievements, rating and review. Restore it any time, exactly as it was.
- **If a game's files disappear**, it stays in your library, greyed out and
  marked *Files not found*, with nothing lost. Use **Locate game** to point
  GameKeeper to its new location.
- **Daily backups**: once a day GameKeeper zips up all your records (keeping
  the last 30). Set the folder in **Settings → Backups**, ideally on another
  drive or a cloud-synced folder.

## Excluding achievements

For achievements you can't or won't do (multiplayer, online, removed DLC),
right-click them and choose **Exclude from this game**. Excluded achievements
leave the list and stop counting toward your progress, so 100% means 100% of
what's left. They're kept in the background: the **Excluded** filter shows
them, and **Include again** brings one back. Refreshing data from Steam keeps
your exclusions.

To exclude several at once, Ctrl+click or Shift+click to select them. Or type
in the achievement search (e.g. *multiplayer*), right-click a result and
choose **Exclude all matching**.

### Deleting achievements permanently

If you'd rather not see them at all, right-click and choose **Delete
permanently** (also works on a selection, on everything matching a search, or
on all excluded ones via ⚙). Deleted achievements vanish from the list and
the counts, and refreshing from Steam won't bring them back. If you ever
change your mind, **⚙ → Restore deleted achievements** downloads them again.

## Resetting achievements

Under the ⚙ button on a game's page:

- **Lock achievements unlocked by hand** locks only the ones you unlocked
  yourself, and keeps automatic unlocks and Steam imports.
- **Lock all achievements** starts fresh. Ones the game's saves still show as
  earned unlock again at the next check.

## Changing the look

All styling lives in `gamekeeper/ui/theme.qss`, written in Qt Style Sheets
(Qt's version of CSS). The colour variables at the top (`@bg`, `@accent`,
`@gold`...) are used everywhere, including the parts drawn in code, so
changing one there recolours the whole app. Restart GameKeeper to see changes.

## Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+F | Search games, or achievements on a game's page |
| Ctrl+N | Add a game |
| Ctrl+, | Settings |
| Esc / Backspace | Back to the library (or clear the search box) |

## Project layout

```
main.py                 entry point
gamekeeper/
  storage.py            data folder, library, games, achievements
  scanner.py            finding the game .exe in a folder
  steam.py              Steam search, artwork, achievement data, imports
  triggers/             per-game rules that read save files for unlocks
  tracking.py           combines unlock sources for a game
  runner.py             launching games, playtime, watching for unlocks
  winlaunch.py          starting games, including as administrator
  shortcut.py           creating desktop / Start menu shortcuts
  backup.py             daily zip backups of your records
  ui/                   the Qt interface
  ui/theme.qss          all colours and styling (Qt's CSS)
```
