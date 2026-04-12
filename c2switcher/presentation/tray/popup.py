"""Tray popup window — borderless PySide6 QWidget.

Appears near the system tray when the tray icon is clicked.
Closes when focus is lost or Escape is pressed.
Rebuilt on every data refresh.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .themes import THEMES, load_theme_pref, save_theme_pref, DEFAULT_THEME
from .widgets import (
    AccountCard,
    HeaderBar,
    LegendRow,
    UsageBar,
    _run_service,
    _svc_optimal,
    _svc_reorder,
)


POPUP_WIDTH = 400


class TrayPopup(QWidget):
    """Main tray popup window.

    Thread safety: all methods must be called from the Qt main thread.
    Use Qt signals to dispatch from background threads.
    """

    # Emitted when any action (switch, reorder, etc.) should trigger a data refresh
    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)

        self._theme_name = load_theme_pref()
        self._theme = THEMES[self._theme_name]
        self._accounts: list[dict] = []
        self._session_active = False

        self.setFixedWidth(POPUP_WIDTH)
        self._build_shell()

    # ── Public API ────────────────────────────────────────────────────────────

    @Slot(list)
    def update_data(self, accounts: list[dict]):
        """Called from the monitor (via Qt signal) when new data arrives."""
        self._accounts = accounts
        self._rebuild_content()

    @Slot(bool)
    def set_processing(self, active: bool):
        self._session_active = active
        if self._header:
            self._header.set_processing(active)

    def toggle(self):
        """Show near tray or hide if already visible."""
        if self.isVisible():
            self.hide()
        else:
            self._position_near_tray()
            self.show()
            self.raise_()
            self.activateWindow()

    def show_popup(self):
        self._position_near_tray()
        self.show()
        self.raise_()
        self.activateWindow()

    # ── Shell layout (built once) ─────────────────────────────────────────────

    def _build_shell(self):
        t = self._theme
        self.setStyleSheet(
            f'TrayPopup {{ background-color: {t["bg"]}; border: 1px solid {t["separator"]};'
            f' border-radius: 8px; }}'
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        self._header = HeaderBar(t)
        self._header.refresh_clicked.connect(self.refresh_requested)
        self._header.optimal_clicked.connect(self._on_optimal_clicked)
        self._header.title_clicked.connect(self._on_title_clicked)
        outer.addWidget(self._header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f'color: {t["separator"]};')
        outer.addWidget(sep)

        # Scroll area for dynamic content
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            'QScrollArea { background: transparent; border: none; }'
            'QScrollBar:vertical { background: transparent; width: 6px; }'
            f'QScrollBar::handle:vertical {{ background: {t["separator"]}; border-radius: 3px; }}'
        )
        outer.addWidget(self._scroll)

        # Initial placeholder
        self._content: Optional[QWidget] = None
        self._show_placeholder()

    def _show_placeholder(self):
        ph = QWidget()
        ph.setStyleSheet(f'background-color: {self._theme["bg"]};')
        vl = QVBoxLayout(ph)
        lbl = QLabel('Loading usage data…')
        lbl.setStyleSheet(f'color: {self._theme["textSecondary"]}; padding: 20px;')
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(lbl)
        self._scroll.setWidget(ph)
        self.setFixedHeight(120)

    # ── Content rebuild ───────────────────────────────────────────────────────

    def _rebuild_content(self):
        t = self._theme
        accounts = self._accounts

        content = QWidget()
        content.setStyleSheet(f'background-color: {t["bg"]};')
        vl = QVBoxLayout(content)
        vl.setContentsMargins(8, 6, 8, 8)
        vl.setSpacing(6)

        if not accounts:
            lbl = QLabel('No accounts found.\nRun: c2switcher login')
            lbl.setStyleSheet(f'color: {t["textSecondary"]}; padding: 16px;')
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vl.addWidget(lbl)
            self._scroll.setWidget(content)
            self.setFixedHeight(140)
            return

        # ── Usage bars ────────────────────────────────────────────────────────
        sonnet_bar = UsageBar('Sonnet 7d', 'seven_day_sonnet', t)
        sonnet_bar.update_data(accounts)
        vl.addWidget(sonnet_bar)

        overall_bar = UsageBar('Overall 7d', 'seven_day', t)
        overall_bar.update_data(accounts)
        vl.addWidget(overall_bar)

        # Legend
        legend = LegendRow(t)
        legend.update_data(accounts)
        vl.addWidget(legend)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f'color: {t["separator"]};')
        vl.addWidget(sep)

        # ── Account cards ─────────────────────────────────────────────────────
        for i, acc in enumerate(accounts):
            card = AccountCard(
                account=acc,
                array_idx=i,
                total_accounts=len(accounts),
                theme=t,
                session_active=self._session_active,
            )
            card.action_requested.connect(self._on_card_action)
            vl.addWidget(card)

        vl.addStretch()

        old = self._content
        self._content = content
        self._scroll.setWidget(content)
        if old:
            old.deleteLater()

        # Compute height: header(~40) + sep(1) + content
        content_h = content.sizeHint().height()
        screen_h = QApplication.primaryScreen().availableGeometry().height()
        max_h = int(screen_h * 0.7)
        total_h = min(40 + 1 + content_h + 16, max_h)
        self.setFixedHeight(max(total_h, 200))

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_optimal_clicked(self):
        if self._session_active:
            return
        _run_service(_svc_optimal, on_done=self.refresh_requested.emit)

    def _on_title_clicked(self):
        self._theme_name = 'classic' if self._theme_name == 'retro' else 'retro'
        self._theme = THEMES[self._theme_name]
        save_theme_pref(self._theme_name)
        self._apply_theme()
        self._rebuild_content()

    def _on_card_action(self):
        """After any card action (switch, remove, nickname), request a refresh."""
        # Check for reorder intent
        sender = self.sender()
        if hasattr(sender, '_reorder_delta'):
            self._do_reorder(sender._array_idx, sender._reorder_delta)
            del sender._reorder_delta
        else:
            self.refresh_requested.emit()

    def _do_reorder(self, array_idx: int, delta: int):
        accounts = list(self._accounts)
        new_idx = array_idx + delta
        if new_idx < 0 or new_idx >= len(accounts):
            return
        accounts[array_idx], accounts[new_idx] = accounts[new_idx], accounts[array_idx]
        emails = [a.get('email', '') for a in accounts]
        _run_service(_svc_reorder, emails, on_done=self.refresh_requested.emit)

    def _apply_theme(self):
        t = self._theme
        self.setStyleSheet(
            f'TrayPopup {{ background-color: {t["bg"]}; border: 1px solid {t["separator"]};'
            f' border-radius: 8px; }}'
        )
        self._scroll.setStyleSheet(
            'QScrollArea { background: transparent; border: none; }'
            'QScrollBar:vertical { background: transparent; width: 6px; }'
            f'QScrollBar::handle:vertical {{ background: {t["separator"]}; border-radius: 3px; }}'
        )
        if self._header:
            self._header.update_theme(t)

    # ── Window behaviour ──────────────────────────────────────────────────────

    def focusOutEvent(self, event):
        # Close popup when it loses focus (click outside)
        QTimer.singleShot(150, self._hide_if_unfocused)
        super().focusOutEvent(event)

    def _hide_if_unfocused(self):
        if not self.isActiveWindow():
            self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        super().keyPressEvent(event)

    # ── Positioning ───────────────────────────────────────────────────────────

    def _position_near_tray(self):
        """Place the popup at the bottom-right corner of the primary screen."""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        x = geom.right() - self.width() - 8
        y = geom.bottom() - self.height() - 8
        self.move(x, y)
