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


def _start_console_hider():
    """Daemon thread that detects any console window in our process and
    immediately sends it behind all other windows.

    We can't always prevent a console window from being created (some library
    or Windows initialisation path does it), but we can suppress it visually
    by moving it to the bottom of the z-order as soon as it appears.
    """
    if sys.platform != 'win32':
        return

    import os
    import ctypes
    import ctypes.wintypes
    import threading
    import time

    user32 = ctypes.windll.user32
    pid = os.getpid()

    HWND_BOTTOM = 1
    SWP_NOMOVE     = 0x0002
    SWP_NOSIZE     = 0x0001
    SWP_NOACTIVATE = 0x0010
    SWP_FLAGS = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
    SW_HIDE = 0

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.wintypes.HWND,
        ctypes.wintypes.LPARAM,
    )

    def _enum(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid_buf = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
        if pid_buf.value != pid:
            return True
        cls_buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls_buf, 64)
        if cls_buf.value == 'ConsoleWindowClass':
            # Hide it completely — it's an unwanted console window
            user32.ShowWindow(hwnd, SW_HIDE)
        return True

    enum_proc = WNDENUMPROC(_enum)

    def _run():
        while True:
            user32.EnumWindows(enum_proc, 0)
            time.sleep(0.02)   # 20 ms poll — imperceptible to the user

    t = threading.Thread(target=_run, daemon=True, name='c2s-console-hider')
    t.start()


def main():
    args = sys.argv[1:]
    tray_mode = len(args) == 0 or args[0] in ('tray', '--tray')

    if tray_mode:
        # Must be set before importing any c2switcher modules so that the
        # Rich Console singleton (created at import time in console.py) uses
        # quiet=True.  This prevents Rich from calling SetConsoleMode() via
        # ctypes, which causes Windows to briefly allocate and flash a console
        # window even in a windowed (console=False) PyInstaller build.
        import os
        os.environ['C2SWITCHER_TRAY_MODE'] = '1'
        _nul = open(os.devnull, 'w')
        sys.stdout = _nul
        sys.stderr = _nul

        # Start the console hider before any imports — some library
        # initialisation paths create a console window during import.
        _start_console_hider()

        from c2switcher.presentation.tray.app import TrayApp
        TrayApp().run()
    else:
        _attach_console()
        from c2switcher.cli import cli
        cli(standalone_mode=True)


if __name__ == '__main__':
    main()
