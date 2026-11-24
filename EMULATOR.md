# Automatic achievements with a Steam API emulator

Steam games unlock achievements by calling `steam_api.dll` /
`steam_api64.dll`. GameKeeper can swap that DLL for the one from
[gbe_fork](https://github.com/Detanup01/gbe_fork), an open-source (LGPL-3.0)
Steam API emulator. The emulator records every achievement the game reports,
and GameKeeper shows the popup. This works for any game that talks to Steam
through those DLLs, with no per-game setup.

You build the DLLs yourself, on GitHub's own build servers, straight from the
project's public code. That way you know exactly where they came from, rather
than trusting a downloaded file.

## Build the DLLs (about 30-60 minutes, mostly waiting)

1. Sign in to GitHub and open <https://github.com/Detanup01/gbe_fork>.
   Click **Fork**. On the fork page, **untick "Copy the `dev` branch only"**,
   then click **Create fork**. The build needs the project's
   `third-party/...` branches; with that box ticked (the default), every
   build job fails.
2. In your fork, open the **Actions** tab and click **I understand my
   workflows, go ahead and enable them**.
3. In the list on the left, pick **Build emu (Windows)**, click **Run
   workflow**, keep the default branch and click the green **Run workflow**.
   *All jobs failed?* Your fork is probably missing the `third-party/...`
   branches (check the branch list). Delete the fork (its **Settings** →
   bottom of the page → **Delete this repository**) and fork again with the
   box unticked.
4. Wait for the run to finish. The first run builds the dependencies too, so
   it takes a while. A few optional parts may fail; that's fine as long as
   the `api_regular` release builds succeed.
5. Open the finished run and scroll to **Artifacts**. Download these two:
   - `emu-win-api_regular-release-x64-...`
   - `emu-win-api_regular-release-Win32-...`

   GitHub deletes these after one day, so download them soon after the run.
6. Extract both into **one** folder, for example `C:\GameKeeper\emulator`.
   You'll end up with an `x64` folder (64-bit, `steam_api64.dll`) and an
   `x86` folder (32-bit, `steam_api.dll`; x86 is the same as 32-bit/Win32).
   Point GameKeeper at the folder that contains both. It picks the right DLL
   for each game by checking whether the game's own DLL is 32- or 64-bit.

## Antivirus

Antivirus software often flags Steam API emulators, including ones built from
source, because of what they do (stand in for Steam). If it does:

- Check the detection name. Generic names like `HackTool`, `PUA` or ones
  ending in `!ml` are expected for this kind of tool. A name like
  `Trojan:...Stealer`, `Backdoor` or `Ransom` is not; stop and don't use it.
- If you're comfortable, allow it for the emulator folder only (Windows
  Security → Virus & threat protection → Manage settings → Exclusions).
  Don't turn your antivirus off. GameKeeper also copies the DLL into each game
  folder you set up, so you may need to allow it there too.

## Turn it on in GameKeeper

1. **Settings → Automatic tracking → Emulator folder**: pick the folder from
   step 6.
2. On a game's page, pull its achievements from Steam if you haven't yet.
3. **⚙ → Automatic tracking (emulator) → Set up for this game**.

GameKeeper backs up the game's original DLLs (`*.gamekeeper-original`), copies
in the emulator, and writes the emulator's `steam_settings` folder (app id and
achievement list). **Restore original Steam files** in the same menu undoes it.

## Things to know

- **Saves made through Steam Cloud** go to the emulator's folder instead,
  `%APPDATA%\GSE Saves\<app id>\remote`. If a game doesn't find your existing
  progress after setup, copy its saves there.
- **Games with Steam's DRM wrapper won't start with the emulator.** Restore
  the original files for those. GameKeeper doesn't remove DRM.
- Only use it for offline, single-player games.
- If a game also has save-file rules in GameKeeper (like Stardew Valley), both
  are used; achievements count once either way.
