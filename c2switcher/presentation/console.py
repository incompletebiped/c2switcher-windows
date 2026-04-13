"""Shared console instance for c2switcher output.

CLI mode: writes to stderr so output doesn't interfere with stdout integrations.
Tray mode: quiet=True suppresses all output AND skips Windows console API calls
(SetConsoleMode / GetStdHandle) that would flash a console window in a windowed exe.
"""

import os
from rich.console import Console

if os.environ.get('C2SWITCHER_TRAY_MODE'):
    console = Console(quiet=True)
else:
    console = Console(stderr=True)
