"""Starting games on Windows, including "Run as administrator"."""
from __future__ import annotations

import os
import shlex
import subprocess

ERROR_ELEVATION_REQUIRED = 740
ERROR_CANCELLED = 1223


class NeedsAdmin(Exception):
    """The game's exe asks for administrator rights."""


class LaunchCancelled(Exception):
    """The user said no to the Windows permission (UAC) prompt."""


class Launched:
    """A started game. ``alive()`` works even for elevated processes."""

    def __init__(self, pid: int, popen: subprocess.Popen | None = None, handle=None):
        self.pid = pid
        self._popen = popen
        self._handle = handle

    def alive(self) -> bool:
        if self._popen is not None:
            return self._popen.poll() is None
        if self._handle is not None:
            import ctypes
            WAIT_TIMEOUT = 0x102
            return ctypes.windll.kernel32.WaitForSingleObject(self._handle, 0) == WAIT_TIMEOUT
        return False

    def close(self):
        if self._handle is not None:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None


def launch(exe: str, args: str, cwd: str, as_admin: bool = False) -> Launched:
    if as_admin and os.name == "nt":
        return _launch_elevated(exe, args, cwd)
    argv = [exe, *(shlex.split(args, posix=(os.name != "nt")) if args else [])]
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(argv, cwd=cwd, creationflags=flags)
    except OSError as e:
        if getattr(e, "winerror", None) == ERROR_ELEVATION_REQUIRED:
            raise NeedsAdmin() from e
        raise
    return Launched(proc.pid, popen=proc)


def _launch_elevated(exe: str, args: str, cwd: str) -> Launched:
    """ShellExecuteEx with the "runas" verb: shows the UAC prompt."""
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NOASYNC = 0x00000100
    SW_SHOWNORMAL = 1

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    info.lpVerb = "runas"
    info.lpFile = exe
    info.lpParameters = args or None
    info.lpDirectory = cwd or None
    info.nShow = SW_SHOWNORMAL

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32 = ctypes.windll.kernel32
    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessId.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        err = ctypes.get_last_error()
        if err == ERROR_CANCELLED:
            raise LaunchCancelled()
        raise OSError(f"Windows couldn't start the game as administrator (error {err}).")
    if not info.hProcess:
        raise OSError("Windows started the game but gave no process to track.")
    return Launched(kernel32.GetProcessId(info.hProcess), handle=info.hProcess)
