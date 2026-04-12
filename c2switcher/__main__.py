"""Single entry point — dispatches to tray app or CLI based on arguments.

Usage:
  c2switcher.exe            → start system tray app (default)
  c2switcher.exe tray       → same as above (explicit)
  c2switcher.exe <command>  → run CLI command (e.g. login, ls, usage, switch)
"""

import sys


def _attach_console():
    """Attach to parent process console so CLI output works when the EXE is
    built as a GUI application (console=False in PyInstaller spec)."""
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.kernel32.AttachConsole(-1)  # ATTACH_PARENT_PROCESS = -1
            # Reopen stdout/stderr so print() and rich output reach the terminal
            sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
            sys.stderr = open('CONOUT$', 'w', encoding='utf-8')
        except Exception:
            pass


def main():
    args = sys.argv[1:]
    tray_mode = len(args) == 0 or args[0] in ('tray', '--tray')

    if tray_mode:
        from c2switcher.presentation.tray.app import TrayApp
        TrayApp().run()
    else:
        _attach_console()
        from c2switcher.cli import cli
        cli(standalone_mode=True)


if __name__ == '__main__':
    main()
