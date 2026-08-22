"""Windows startup registry helpers.

Manages the HKCU Run key so the tray app can optionally start with Windows.
Uses only stdlib winreg — no extra dependencies.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = 'c2switcher'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def startup_command(executable: str | None = None) -> str:
    """The command Windows should run at login.

    sys.executable is c2switcher.exe in a PyInstaller build, but a bare python.exe
    for a pip install — registering that on its own opens a Python prompt at login
    instead of the tray, so prefer the console script pip installed.
    """
    exe = Path(executable or sys.executable)
    if getattr(sys, 'frozen', False):
        return f'"{exe}"'

    for candidate in (exe.parent / 'c2switcher.exe', exe.parent / 'Scripts' / 'c2switcher.exe'):
        if candidate.exists():
            return f'"{candidate}"'

    return f'"{exe}" -m c2switcher'


def is_startup_enabled() -> bool:
    """Return True if the app is registered to start with Windows."""
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False


def set_startup(enabled: bool) -> None:
    """Enable or disable start-with-Windows."""
    if sys.platform != 'win32':
        return
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
    )
    try:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)
