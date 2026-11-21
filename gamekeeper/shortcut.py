"""Creating Windows shortcuts that start GameKeeper without a console window."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .storage import ROOT_DIR


class ShortcutError(Exception):
    pass


def supported() -> bool:
    return sys.platform == "win32"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return w if w.exists() else exe


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def create(location: str, icon: Path) -> Path:
    """Create a shortcut. ``location`` is "desktop" or "startmenu"."""
    if not supported():
        raise ShortcutError("Shortcuts can only be created on Windows.")
    folder = {"desktop": "Desktop", "startmenu": "Programs"}[location]
    main = ROOT_DIR / "main.py"
    script = f"""
$dir = [Environment]::GetFolderPath({_ps_quote(folder)})
$path = Join-Path $dir 'GameKeeper.lnk'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
$s.TargetPath = {_ps_quote(_pythonw())}
$s.Arguments = {_ps_quote(f'"{main}"')}
$s.WorkingDirectory = {_ps_quote(ROOT_DIR)}
$s.IconLocation = {_ps_quote(f"{icon},0")}
$s.Description = 'GameKeeper game launcher'
$s.Save()
Write-Output $path
"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ShortcutError(f"Couldn't run PowerShell: {e}") from e
    if out.returncode != 0:
        raise ShortcutError(out.stderr.strip() or "PowerShell couldn't create the shortcut.")
    return Path(out.stdout.strip().splitlines()[-1])
