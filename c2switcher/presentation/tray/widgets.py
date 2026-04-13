"""Tray popup UI widgets — PySide6 port of applet.js layout.

All widget actions (switch, nickname, reorder, remove) run the corresponding
ServiceFactory call on a QThreadPool worker so the UI stays responsive.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QBrush, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .themes import THEMES


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rgba_css_to_qt(rgba_str: str) -> QColor:
    """Parse 'rgba(r,g,b,a)' CSS string to QColor."""
    try:
        s = rgba_str.strip()
        if s.startswith('rgba('):
            parts = s[5:-1].split(',')
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            a = float(parts[3])
            return QColor(r, g, b, int(a * 255))
        if s.startswith('#'):
            return QColor(s)
    except Exception:
        pass
    return QColor(128, 128, 128, 40)


def _time_remaining(resets_at: Optional[str]) -> str:
    """Return compact time-remaining string like '4h' or '2d'."""
    if not resets_at:
        return ''
    try:
        dt = datetime.fromisoformat(resets_at.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        remaining = (dt - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            return 'soon'
        hours = remaining / 3600
        if hours >= 24:
            return f'{round(hours / 24)}d'
        return f'{round(hours)}h'
    except Exception:
        return ''


def _calculate_overuse_rate(usage: Optional[dict]) -> Optional[int]:
    """Port of applet.js _calculateOveruseRate."""
    if not usage:
        return None
    week_s = 7 * 24 * 3600
    min_elapsed = week_s * 0.10
    worst = 0.0
    now = datetime.now(timezone.utc)

    for key in ('seven_day_sonnet', 'seven_day'):
        w = usage.get(key)
        if not w or w.get('utilization') is None or not w.get('resets_at'):
            continue
        try:
            resets = datetime.fromisoformat(w['resets_at'].replace('Z', '+00:00'))
            if resets.tzinfo is None:
                resets = resets.replace(tzinfo=timezone.utc)
            remaining_s = (resets - now).total_seconds()
            if remaining_s <= 0:
                continue
            elapsed_s = week_s - remaining_s
            if elapsed_s < min_elapsed:
                continue
            expected = (elapsed_s / week_s) * 100
            rate = (w['utilization'] / expected) * 100
            worst = max(worst, rate)
        except Exception:
            pass

    return round(worst) if worst > 0 else None


class _WorkerSignals(QObject):
    done = Signal()


class _Worker(QRunnable):
    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = _WorkerSignals()

    def run(self):
        try:
            self._fn(*self._args, **self._kwargs)
        except Exception:
            pass
        self.signals.done.emit()


def _run_service(fn: Callable, *args, on_done: Optional[Callable] = None, **kwargs):
    """Execute fn(*args) on a thread-pool worker; call on_done() when complete."""
    worker = _Worker(fn, *args, **kwargs)
    if on_done:
        worker.signals.done.connect(on_done)
    QThreadPool.globalInstance().start(worker)


# ── Service calls (thin wrappers so widgets stay independent of services) ────

def _svc_switch(index: int):
    from ...infrastructure.factory import ServiceFactory
    from ...infrastructure.locking import acquire_lock
    acquire_lock()
    with ServiceFactory() as f:
        f.get_switching_service().switch_to(str(index))


def _svc_optimal():
    from ...infrastructure.factory import ServiceFactory
    from ...infrastructure.locking import acquire_lock
    acquire_lock()
    with ServiceFactory() as f:
        f.get_switching_service().select_optimal(dry_run=False)


def _svc_nickname(index: int, name: str):
    from ...infrastructure.factory import ServiceFactory
    from ...infrastructure.locking import acquire_lock
    acquire_lock()
    with ServiceFactory() as f:
        f.get_account_service().set_nickname(str(index), name)


def _svc_remove(index: int):
    from ...infrastructure.factory import ServiceFactory
    from ...infrastructure.locking import acquire_lock
    acquire_lock()
    with ServiceFactory() as f:
        f.get_account_service().remove_account(str(index))


def _svc_reorder(emails: list[str]):
    """Reorder accounts by resolving each email to a UUID, then calling store.reorder_accounts."""
    from ...infrastructure.factory import ServiceFactory
    from ...infrastructure.locking import acquire_lock
    acquire_lock()
    with ServiceFactory() as f:
        svc = f.get_account_service()
        uuids = []
        for email in emails:
            try:
                acc = svc.get_account(email)
                uuids.append(acc.uuid)
            except Exception:
                pass
        if uuids:
            f.get_store().reorder_accounts(uuids)


# ── UsageBar ──────────────────────────────────────────────────────────────────

class UsageBar(QWidget):
    """Stacked horizontal bar showing per-account usage segments.

    Mirrors applet.js _addBar() + _addLegend().
    """

    def __init__(self, label: str, usage_key: str, theme: dict, parent=None):
        super().__init__(parent)
        self._label = label
        self._usage_key = usage_key
        self._theme = theme
        self._segments: list[tuple[float, str]] = []  # (usage%, color)
        self._total_pct = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)

        self._label_widget = QLabel(label)
        self._label_widget.setStyleSheet(
            f"color: {theme['textSecondary']}; font-size: 10px; font-weight: 500;"
        )
        layout.addWidget(self._label_widget)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(4)

        self._bar = _SegmentBar(theme)
        self._bar.setFixedHeight(14)
        bar_row.addWidget(self._bar, stretch=1)

        self._pct_label = QLabel('0%')
        self._pct_label.setStyleSheet(
            f"color: {theme['textSecondary']}; font-size: 10px; min-width: 28px;"
        )
        self._pct_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bar_row.addWidget(self._pct_label)

        layout.addLayout(bar_row)

    def update_data(self, accounts: list[dict]):
        max_possible = len(accounts) * 100
        segments = []
        total = 0.0

        for i, acc in enumerate(accounts):
            usage = 0.0
            u = (acc.get('usage') or {}).get(self._usage_key)
            if u and u.get('utilization') is not None:
                usage = float(u['utilization'])
            color = self._theme['accountColors'][i % len(self._theme['accountColors'])]
            segments.append((usage, color))
            total += usage

        pct = (total / max_possible * 100) if max_possible > 0 else 0
        self._segments = segments
        self._total_pct = pct
        self._bar.set_segments(segments, max_possible)
        self._pct_label.setText(f'{round(pct)}%')

    def update_theme(self, theme: dict):
        self._theme = theme
        self._label_widget.setStyleSheet(
            f"color: {theme['textSecondary']}; font-size: 10px; font-weight: 500;"
        )
        self._pct_label.setStyleSheet(
            f"color: {theme['textSecondary']}; font-size: 10px; min-width: 28px;"
        )
        self._bar.update_theme(theme)


class _SegmentBar(QWidget):
    """Custom painted horizontal bar with colored segments."""

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self._segments: list[tuple[float, str]] = []
        self._max_possible = 100.0
        self._bg = theme['separator']

    def set_segments(self, segments: list[tuple[float, str]], max_possible: float):
        self._segments = segments
        self._max_possible = max(max_possible, 1)
        self.update()

    def update_theme(self, theme: dict):
        self._bg = theme['separator']
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = h // 2

        # Background
        bg = QColor(self._bg)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)
        painter.fillPath(path, QBrush(bg))

        # Segments
        x = 0.0
        for usage, color in self._segments:
            seg_w = w * usage / self._max_possible
            if seg_w < 1:
                continue
            seg_path = QPainterPath()
            seg_path.addRoundedRect(x, 0, seg_w, h, r, r)
            c = QColor(color)
            c.setAlpha(191)
            painter.fillPath(seg_path, QBrush(c))
            x += seg_w


# ── LegendRow ──────────────────────────────────────────────────────────────────

class LegendRow(QWidget):
    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(0)

    def update_data(self, accounts: list[dict]):
        # Clear existing children
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for i, acc in enumerate(accounts):
            if i > 0:
                spacer = QWidget()
                spacer.setFixedWidth(10)
                self._layout.addWidget(spacer)

            item = QWidget()
            row = QHBoxLayout(item)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(3)

            # Color swatch
            swatch = QWidget()
            swatch.setFixedSize(10, 8)
            color = self._theme['accountColors'][i % len(self._theme['accountColors'])]
            swatch.setStyleSheet(
                f"background-color: {color}; border-radius: 2px;"
            )
            row.addWidget(swatch)

            is_active = acc.get('is_active', False)
            name = acc.get('nickname') or acc.get('email') or f'Account {i + 1}'
            if is_active:
                name = '▶ ' + name

            lbl = QLabel(name)
            lbl.setStyleSheet(
                f"color: {self._theme['textPrimary'] if is_active else self._theme['textSecondary']};"
                f" font-size: 10px;"
                + (' font-weight: bold;' if is_active else '')
            )
            row.addWidget(lbl)

            self._layout.addWidget(item)

        self._layout.addStretch()

    def update_theme(self, theme: dict):
        self._theme = theme


# ── UsageIndicator ────────────────────────────────────────────────────────────

class UsageIndicator(QWidget):
    """Single usage indicator box — port of applet.js _buildIndicator()."""

    def __init__(self, label: str, highlight: bool = False, is_rate: bool = False, parent=None):
        super().__init__(parent)
        self._highlight = highlight
        self._is_rate = is_rate
        self._theme: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        self._label_w = QLabel(label)
        self._label_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_w.setStyleSheet('font-size: 9px;')
        layout.addWidget(self._label_w)

        self._value_w = QLabel('—')
        self._value_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_w.setFixedWidth(46)
        self._value_w.setStyleSheet(
            'font-size: 11px; font-weight: 600; padding: 2px 4px; border-radius: 3px;'
        )
        layout.addWidget(self._value_w)

    def update_value(self, value: Optional[int], theme: dict):
        self._theme = theme
        t = theme

        if value is None:
            bg = _rgba_css_to_qt(t['indNull']['bg'])
            border = _rgba_css_to_qt(t['indNull']['border'])
            self._value_w.setText('—')
        elif self._is_rate:
            if value >= 120:
                bg = _rgba_css_to_qt(t['indErr']['bg'])
                border = _rgba_css_to_qt(t['indErr']['border'])
            elif value >= 100:
                bg = _rgba_css_to_qt(t['indWarn']['bg'])
                border = _rgba_css_to_qt(t['indWarn']['border'])
            else:
                bg = _rgba_css_to_qt(t['indOk']['bg'])
                border = _rgba_css_to_qt(t['indOk']['border'])
            self._value_w.setText(f'{value}%')
        else:
            if value >= 90:
                bg = _rgba_css_to_qt(t['indErr']['bg'])
                border = _rgba_css_to_qt(t['indErr']['border'])
            elif value >= 70:
                bg = _rgba_css_to_qt(t['indWarn']['bg'])
                border = _rgba_css_to_qt(t['indWarn']['border'])
            else:
                bg = _rgba_css_to_qt(t['indOk']['bg'])
                border = _rgba_css_to_qt(t['indOk']['border'])
            self._value_w.setText(f'{value}%')

        if self._highlight:
            border = _rgba_css_to_qt(t['indHighlight'])

        self._label_w.setStyleSheet(
            f'font-size: 9px; color: {t["textSecondary"]};'
        )
        self._value_w.setStyleSheet(
            f'font-size: 11px; font-weight: 600; padding: 2px 4px; border-radius: 3px;'
            f' background-color: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});'
            f' border: 1px solid rgba({border.red()},{border.green()},{border.blue()},{border.alpha()});'
        )


# ── AccountCard ───────────────────────────────────────────────────────────────

class AccountCard(QWidget):
    """Full account row card — port of applet.js _addAccountCard()."""

    action_requested = Signal()  # emitted after any action so popup can refresh

    def __init__(
        self,
        account: dict,
        array_idx: int,
        total_accounts: int,
        theme: dict,
        session_active: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._account = account
        self._array_idx = array_idx
        self._total = total_accounts
        self._theme = theme
        self._session_active = session_active
        self._build_ui()

    def _build_ui(self):
        acc = self._account
        t = self._theme
        is_active = acc.get('is_active', False)
        needs_reauth = acc.get('needs_reauth', False)
        index = acc.get('index', self._array_idx + 1)

        bg = t['cardActiveBg'] if is_active else t['cardBg']
        dot_color = t['activeDot'] if is_active else 'transparent'

        self.setStyleSheet(
            f'AccountCard {{ background-color: {bg}; border-radius: 6px;'
            f' border: 1px solid {t["separator"]}; }}'
            f' AccountCard:hover {{ border-color: {t["accountColors"][self._array_idx % len(t["accountColors"])]}; }}'
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor if not needs_reauth else Qt.CursorShape.ArrowCursor)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 6, 6, 6)
        outer.setSpacing(6)

        # Active dot
        dot = QWidget()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f'background-color: {dot_color}; border-radius: 4px;')
        outer.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)

        # Account info (nickname + email)
        info = QVBoxLayout()
        info.setSpacing(1)
        info.setContentsMargins(0, 0, 0, 0)

        name_row = QHBoxLayout()
        name_row.setSpacing(4)

        idx_lbl = QLabel(f'#{index}')
        idx_lbl.setStyleSheet(f'color: {t["textSecondary"]}; font-size: 10px;')
        name_row.addWidget(idx_lbl)

        # Nickname: stacked (label / entry)
        self._nick_stack = QStackedWidget()
        self._nick_stack.setFixedHeight(18)

        nick_text = acc.get('nickname') or 'No nickname'
        self._nick_label = QLabel(nick_text)
        self._nick_label.setStyleSheet(
            f'color: {t["textPrimary"]}; font-size: 12px; font-weight: 600;'
        )
        self._nick_stack.addWidget(self._nick_label)

        self._nick_entry = QLineEdit(acc.get('nickname') or '')
        self._nick_entry.setPlaceholderText('Enter nickname…')
        self._nick_entry.setStyleSheet(
            f'background: {t["bg"]}; color: {t["textPrimary"]}; border: 1px solid {t["separator"]};'
            f' border-radius: 3px; padding: 0 4px; font-size: 11px;'
        )
        self._nick_entry.returnPressed.connect(self._commit_nickname)
        self._nick_stack.addWidget(self._nick_entry)

        name_row.addWidget(self._nick_stack)

        # Edit (pencil) button
        edit_btn = QPushButton('✎')
        edit_btn.setFixedSize(18, 18)
        edit_btn.setToolTip('Edit nickname')
        edit_btn.setStyleSheet(self._btn_style(t))
        edit_btn.clicked.connect(self._start_edit)
        name_row.addWidget(edit_btn)

        name_row.addStretch()
        info.addLayout(name_row)

        email_lbl = QLabel(acc.get('email') or '')
        email_lbl.setStyleSheet(f'color: {t["textSecondary"]}; font-size: 10px;')
        info.addWidget(email_lbl)

        outer.addLayout(info, stretch=1)

        if needs_reauth:
            # Re-auth panel
            ra_box = QVBoxLayout()
            ra_box.setSpacing(2)
            exp_lbl = QLabel('Token expired')
            exp_lbl.setStyleSheet(f'color: {t["panelErr"]}; font-size: 10px;')
            ra_box.addWidget(exp_lbl)
            reauth_btn = QPushButton('🔓 Re-auth')
            reauth_btn.setFixedHeight(22)
            reauth_btn.setStyleSheet(self._btn_style(t, accent=True))
            reauth_btn.clicked.connect(self._do_reauth)
            ra_box.addWidget(reauth_btn)
            outer.addLayout(ra_box)
        else:
            # Usage indicators
            usage = acc.get('usage') or {}
            ind_layout = QHBoxLayout()
            ind_layout.setSpacing(3)

            fh_val = (usage.get('five_hour') or {}).get('utilization')
            fh_label = _time_remaining((usage.get('five_hour') or {}).get('resets_at')) or '5h'
            fh_ind = UsageIndicator(fh_label, highlight=False, is_rate=False)
            fh_ind.update_value(round(fh_val) if fh_val is not None else None, self._theme)
            ind_layout.addWidget(fh_ind)

            sd_val = (usage.get('seven_day') or {}).get('utilization')
            sd_label = _time_remaining((usage.get('seven_day') or {}).get('resets_at')) or '7d'
            sd_ind = UsageIndicator(sd_label, highlight=False, is_rate=False)
            sd_ind.update_value(round(sd_val) if sd_val is not None else None, self._theme)
            ind_layout.addWidget(sd_ind)

            sn_val = (usage.get('seven_day_sonnet') or {}).get('utilization')
            sn_raw_label = _time_remaining((usage.get('seven_day_sonnet') or {}).get('resets_at'))
            sn_label = (sn_raw_label + ' (S)') if sn_raw_label else 'Sonnet'
            sn_ind = UsageIndicator(sn_label, highlight=True, is_rate=False)
            sn_ind.update_value(round(sn_val) if sn_val is not None else None, self._theme)
            ind_layout.addWidget(sn_ind)

            ov_val = _calculate_overuse_rate(usage)
            ov_ind = UsageIndicator('Overuse', highlight=False, is_rate=True)
            ov_ind.update_value(ov_val, self._theme)
            ind_layout.addWidget(ov_ind)

            outer.addLayout(ind_layout)

        # Reorder buttons (up/down)
        reorder = QVBoxLayout()
        reorder.setSpacing(1)
        reorder.setContentsMargins(0, 0, 0, 0)

        up_btn = QPushButton('▲')
        up_btn.setFixedSize(16, 14)
        up_btn.setStyleSheet(self._btn_style(t))
        up_btn.setEnabled(self._array_idx > 0)
        up_btn.setVisible(self._array_idx > 0)
        up_btn.clicked.connect(self._move_up)
        reorder.addWidget(up_btn)

        dn_btn = QPushButton('▼')
        dn_btn.setFixedSize(16, 14)
        dn_btn.setStyleSheet(self._btn_style(t))
        dn_btn.setEnabled(self._array_idx < self._total - 1)
        dn_btn.setVisible(self._array_idx < self._total - 1)
        dn_btn.clicked.connect(self._move_down)
        reorder.addWidget(dn_btn)

        outer.addLayout(reorder)

        # Remove button
        rm_btn = QPushButton('✕')
        rm_btn.setFixedSize(18, 18)
        rm_btn.setToolTip('Remove account')
        rm_btn.setStyleSheet(self._btn_style(t, danger=True))
        rm_btn.clicked.connect(self._remove)
        outer.addWidget(rm_btn, 0, Qt.AlignmentFlag.AlignTop)

        # Install escape key handler on entry
        self._nick_entry.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self._nick_entry and event.type() == QEvent.Type.KeyPress:
            from PySide6.QtCore import Qt as _Qt
            if event.key() == _Qt.Key.Key_Escape:
                self._cancel_edit()
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        # Manual card clicks always work — only the optimal button locks during processing
        if not self._account.get('needs_reauth'):
            index = self._account.get('index', self._array_idx + 1)
            _run_service(_svc_switch, index, on_done=self.action_requested.emit)
        super().mousePressEvent(event)

    # ── Nickname editing ──────────────────────────────────────────────────────

    def _start_edit(self):
        self._nick_stack.setCurrentIndex(1)
        self._nick_entry.selectAll()
        self._nick_entry.setFocus()

    def _commit_nickname(self):
        name = self._nick_entry.text().strip()
        if name:
            index = self._account.get('index', self._array_idx + 1)
            _run_service(_svc_nickname, index, name, on_done=self.action_requested.emit)
            self._nick_label.setText(name)
        self._nick_stack.setCurrentIndex(0)

    def _cancel_edit(self):
        self._nick_entry.setText(self._account.get('nickname') or '')
        self._nick_stack.setCurrentIndex(0)

    # ── Account actions ───────────────────────────────────────────────────────

    def _do_reauth(self):
        import subprocess, sys
        try:
            subprocess.Popen([sys.executable, '-m', 'c2switcher', 'login'])
        except Exception:
            pass

    def _move_up(self):
        self._reorder_with_delta(-1)

    def _move_down(self):
        self._reorder_with_delta(1)

    def _reorder_with_delta(self, delta: int):
        # We need the full account list — the popup will rebuild, so just emit
        # a signal carrying the (array_idx, delta) intent.  PopupWindow connects
        # this to its own reorder handler.
        self._reorder_delta = delta
        # Signal carries no args; popup inspects _reorder_delta
        self.action_requested.emit()

    def _remove(self):
        index = self._account.get('index', self._array_idx + 1)
        _run_service(_svc_remove, index, on_done=self.action_requested.emit)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _btn_style(t: dict, danger: bool = False, accent: bool = False) -> str:
        if danger:
            return (
                f'QPushButton {{ background: transparent; color: {t["panelErr"]}; border: none;'
                f' border-radius: 3px; font-size: 11px; }}'
                f' QPushButton:hover {{ background: rgba(226,75,74,0.15); }}'
            )
        if accent:
            return (
                f'QPushButton {{ background: transparent; color: {t["textPrimary"]}; border: 1px solid {t["separator"]};'
                f' border-radius: 3px; font-size: 11px; padding: 0 6px; }}'
                f' QPushButton:hover {{ background: rgba(127,119,221,0.15); }}'
            )
        return (
            f'QPushButton {{ background: transparent; color: {t["textSecondary"]}; border: none;'
            f' border-radius: 3px; font-size: 11px; }}'
            f' QPushButton:hover {{ background: rgba(255,255,255,0.08); }}'
        )


# ── HeaderBar ─────────────────────────────────────────────────────────────────

class HeaderBar(QWidget):
    """Title + refresh + star/lock buttons — port of applet.js _buildStaticMenu header."""

    refresh_clicked = Signal()
    optimal_clicked = Signal()
    title_clicked = Signal()  # theme toggle

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._session_active = False
        self._build_ui()

    def _build_ui(self):
        t = self._theme
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        title_btn = QPushButton('Claude Switcher')
        title_btn.setFlat(True)
        title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        title_btn.setStyleSheet(
            f'QPushButton {{ color: {t["titleColor"]}; font-size: 13px; font-weight: bold;'
            f' background: transparent; border: none; text-align: left; }}'
            f' QPushButton:hover {{ color: {t["textPrimary"]}; }}'
        )
        title_btn.clicked.connect(self.title_clicked)
        layout.addWidget(title_btn, stretch=1)

        refresh_btn = QPushButton('↻')
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.setToolTip('Refresh usage data')
        refresh_btn.setStyleSheet(self._icon_btn_style(t))
        refresh_btn.clicked.connect(self.refresh_clicked)
        layout.addWidget(refresh_btn)

        self._optimal_btn = QPushButton('★')
        self._optimal_btn.setFixedSize(24, 24)
        self._optimal_btn.setToolTip('Switch to optimal account')
        self._optimal_btn.setStyleSheet(self._icon_btn_style(t))
        self._optimal_btn.clicked.connect(self.optimal_clicked)
        layout.addWidget(self._optimal_btn)

    def set_processing(self, active: bool):
        self._session_active = active
        self._optimal_btn.setText('🔒' if active else '★')
        self._optimal_btn.setToolTip(
            'Claude is processing — switching blocked' if active
            else 'Switch to optimal account'
        )

    def update_theme(self, theme: dict):
        self._theme = theme
        # Delete the old layout and all its children, then rebuild
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                child = old_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            from PySide6.QtWidgets import QWidget as _QW
            _QW().setLayout(old_layout)  # reparent old layout so it gets collected
        self._build_ui()

    @staticmethod
    def _icon_btn_style(t: dict) -> str:
        return (
            f'QPushButton {{ background: transparent; color: {t["textSecondary"]}; border: none;'
            f' border-radius: 4px; font-size: 14px; }}'
            f' QPushButton:hover {{ background: rgba(255,255,255,0.08); color: {t["textPrimary"]}; }}'
        )
