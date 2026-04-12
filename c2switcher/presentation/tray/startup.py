"""Windows startup registry helpers.

Manages the HKCU Run key so the tray app can optionally start with Windows.
Uses only stdlib winreg — no extra dependencies.
"""

from __future__ import annotations

import sys

APP_NAME = 'c2switcher'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


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
    """Enable or disable start-with-Windows.

    Uses sys.executable as the target binary — when run as a PyInstaller EXE
    this is the path to c2switcher.exe itself.
    """
    if sys.platform != 'win32':
        return
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
    )
    try:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, sys.executable)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)
