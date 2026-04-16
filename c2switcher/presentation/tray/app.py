"""Tray application — pystray Icon + PySide6 popup.

TrayApp.run() blocks until the user chooses "Quit" from the right-click menu.
All UI runs on the Qt main thread; the pystray icon runs on its own thread.
"""

from __future__ import annotations

import sys
import threading
from typing import Optional

import pystray
from PySide6.QtCore import QMetaObject, Qt, QTimer, Signal, QObject, Slot
from PySide6.QtWidgets import QApplication

from .icons import render_tray_icon, worst_usage_status
from .monitor import TrayMonitor
from .popup import TrayPopup
from .startup import is_startup_enabled, set_startup


# ── Signal bridge: cross-thread callbacks → Qt signals ───────────────────────

class _Bridge(QObject):
    """Carries signals from the monitor thread to the Qt main thread."""
    data_updated = Signal(list)
    processing_changed = Signal(bool)
    new_account_detected = Signal()
    auto_switched = Signal()


# ── TrayApp ───────────────────────────────────────────────────────────────────

class TrayApp:
    """Main tray application controller."""

    def __init__(self):
        self._app: Optional[QApplication] = None
        self._popup: Optional[TrayPopup] = None
        self._icon: Optional[pystray.Icon] = None
        self._monitor: Optional[TrayMonitor] = None
        self._bridge = _Bridge()
        self._accounts: list[dict] = []
        self._session_active: bool = False

    def run(self):
        """Start the application. Blocks until quit."""
        # Qt app must be created on the main thread before anything else
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # Popup window (hidden initially)
        self._popup = TrayPopup()
        self._popup.refresh_requested.connect(self._on_refresh_requested)

        # Wire bridge signals to popup slots (all on Qt main thread)
        self._bridge.data_updated.connect(self._on_data_updated)
        self._bridge.processing_changed.connect(self._on_processing_changed)
        self._bridge.new_account_detected.connect(self._on_new_account)
        self._bridge.auto_switched.connect(self._on_auto_switched)

        # Monitor (daemon thread) — created here but started from the pystray
        # setup callback so it never fires before pystray's win32 backend is ready.
        self._monitor = TrayMonitor(
            on_data_updated=lambda data: self._bridge.data_updated.emit(data),
            on_processing_changed=lambda active: self._bridge.processing_changed.emit(active),
            on_new_account_detected=lambda: self._bridge.new_account_detected.emit(),
            on_auto_switched=lambda: self._bridge.auto_switched.emit(),
        )

        # pystray icon — start it first; monitor starts inside setup() once
        # pystray has registered the tray icon and set _running = True.
        # This prevents the first icon update from being silently dropped.
        self._icon = self._build_pystray_icon()

        def _pystray_setup(icon):
            icon.visible = True
            self._monitor.start()

        icon_thread = threading.Thread(
            target=lambda: self._icon.run(setup=_pystray_setup),
            daemon=True,
            name='c2s-tray-icon',
        )
        icon_thread.start()

        # Enter Qt event loop
        exit_code = self._app.exec()
        self._monitor.stop()
        self._icon.stop()
        sys.exit(exit_code)

    # ── pystray icon setup ────────────────────────────────────────────────────

    def _build_pystray_icon(self) -> pystray.Icon:
        """Build the pystray.Icon with right-click menu."""
        from PIL import Image
        # render_tray_icon uses QSvgRenderer — safe here because QApplication
        # is already created before _build_pystray_icon is called.
        placeholder_img = render_tray_icon(-1, 'ok', 0)

        def on_left_click(icon, item):
            # pystray calls this on its own thread — dispatch to Qt main thread
            QMetaObject.invokeMethod(
                self._popup,
                'toggle',
                Qt.ConnectionType.QueuedConnection,
            )

        startup_item = pystray.MenuItem(
            lambda _: ('✓ Start with Windows' if is_startup_enabled() else 'Start with Windows'),
            self._on_toggle_startup,
        )

        menu = pystray.Menu(
            pystray.MenuItem('Open', on_left_click, default=True),
            pystray.Menu.SEPARATOR,
            startup_item,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', self._on_quit),
        )

        icon = pystray.Icon(
            'c2switcher',
            placeholder_img,
            'Claude Switcher',
            menu=menu,
        )
        return icon

    def _update_tray_icon(self):
        """Redraw the tray icon based on current account state."""
        if not self._icon:
            return
        try:
            active_idx = -1
            for i, acc in enumerate(self._accounts):
                if acc.get('is_active'):
                    active_idx = i
                    break

            active_acc = next((a for a in self._accounts if a.get('is_active')), None)
            status = worst_usage_status([active_acc.get('usage') or {}] if active_acc else [])
            img = render_tray_icon(active_idx, status, len(self._accounts))

            self._icon.icon = img

            # Update tooltip with active account info
            active = next((a for a in self._accounts if a.get('is_active')), None)
            if active:
                name = active.get('nickname') or active.get('email') or 'Unknown'
                usage = active.get('usage') or {}
                sn = (usage.get('seven_day_sonnet') or {}).get('utilization')
                tip = f'Claude Switcher — {name}'
                if sn is not None:
                    tip += f' ({round(sn)}% Sonnet)'
                self._icon.title = tip
            else:
                self._icon.title = 'Claude Switcher'
        except Exception:
            pass

    # ── Slots (Qt main thread) ────────────────────────────────────────────────

    @Slot(list)
    def _on_data_updated(self, accounts: list[dict]):
        self._accounts = accounts
        self._popup.update_data(accounts)
        self._update_tray_icon()

    @Slot(bool)
    def _on_processing_changed(self, active: bool):
        self._session_active = active
        self._popup.set_processing(active)

    @Slot()
    def _on_new_account(self):
        # Trigger a full refresh to pick up the new account
        if self._monitor:
            self._monitor.force_refresh()

    @Slot()
    def _on_auto_switched(self):
        # Monitor already triggers a refresh after auto-switch; just update icon
        self._update_tray_icon()

    @Slot()
    def _on_refresh_requested(self):
        if self._monitor:
            self._monitor.force_refresh()

    # ── pystray callbacks (non-Qt thread) ─────────────────────────────────────

    def _on_toggle_startup(self, icon, item):
        enabled = not is_startup_enabled()
        set_startup(enabled)
        # Rebuild the menu so the checkmark updates
        icon.update_menu()

    def _on_quit(self, icon, item):
        icon.stop()
        QMetaObject.invokeMethod(
            self._app,
            'quit',
            Qt.ConnectionType.QueuedConnection,
        )
