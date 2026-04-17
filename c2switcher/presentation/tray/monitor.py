"""Background monitor thread.

Replaces the Cinnamon applet's Mainloop timer + Gio.FileMonitor with a plain
daemon thread that:
  - Refreshes usage data every 60 seconds
  - Detects Claude processing via psutil (replacing Linux `ss`)
  - Monitors credentials file for new logins
  - Auto-switches when the current account hits ≥95% usage
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import psutil

from ...constants import CREDENTIALS_PATH, CREDENTIALS_PATH as _CRED_PATH, STATUS_CACHE_PATH
from ...infrastructure.factory import ServiceFactory
from ...infrastructure.locking import acquire_lock

# ── Tuning constants ─────────────────────────────────────────────────────────

UPDATE_INTERVAL_SECONDS = 60
CRED_POLL_INTERVAL_SECONDS = 2
PROCESSING_LOCK_DECAY_SECONDS = 15
AUTO_SWITCH_COOLDOWN_SECONDS = 300  # 5 minutes
RATE_LIMIT_THRESHOLD = 95.0         # % that triggers auto-switch
CRED_DEBOUNCE_SECONDS = 1.5         # wait after mtime change before reading


def _get_claude_pids() -> list[int]:
    """Return PIDs of all running claude / claude-code processes."""
    pids = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = (proc.info.get('name') or '').lower()
                cmdline = proc.info.get('cmdline') or []
                cmdline_str = ' '.join(cmdline).lower()
                if 'claude' in name or 'claude' in cmdline_str:
                    pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return pids


def is_claude_processing(
    claude_pids: list[int],
    prev_connections: frozenset,
) -> tuple[bool, frozenset]:
    """True if Claude's TCP connection set changed since last poll.

    HTTP/2 keeps connections ESTABLISHED even while idle, so checking for
    *any* established connection produces a permanent lock.  Instead we
    trigger only when the connection set changes (new connection, dropped
    connection, or a transitional state like SYN_SENT / CLOSE_WAIT).

    Returns (is_active, current_connection_set).
    """
    if not claude_pids:
        return False, frozenset()

    pid_set = set(claude_pids)
    _TRANSITIONAL = {'SYN_SENT', 'SYN_RECV', 'CLOSE_WAIT',
                     'FIN_WAIT1', 'FIN_WAIT2', 'TIME_WAIT', 'LAST_ACK', 'CLOSING'}
    established: set[tuple] = set()
    has_transitional = False

    try:
        for conn in psutil.net_connections(kind='tcp'):
            if conn.pid not in pid_set:
                continue
            raddr = conn.raddr
            if not raddr:
                continue
            ip = raddr.ip
            if ip.startswith('127.') or ip == '::1':
                continue
            if conn.status in _TRANSITIONAL:
                has_transitional = True
            elif conn.status == 'ESTABLISHED':
                established.add((conn.pid, ip, raddr.port))
    except (psutil.AccessDenied, PermissionError):
        return False, prev_connections
    except Exception:
        return False, prev_connections

    current = frozenset(established)
    changed = current != prev_connections
    is_active = has_transitional or changed
    return is_active, current


def _read_refresh_token(cred_path: Path) -> Optional[str]:
    """Read the OAuth refresh token from the credentials file."""
    try:
        with open(cred_path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data.get('claudeAiOauth', {}).get('refreshToken')
    except Exception:
        return None


def _fetch_usage_data() -> list[dict]:
    """Fetch usage for all accounts via the service layer. Returns list of dicts
    matching the `c2switcher usage --json` output schema."""
    from datetime import datetime, timezone
    from ...infrastructure.api import ClaudeAPI
    from ...data.credential_store import CredentialStore
    from ...constants import CREDENTIALS_PATH as CPATH

    results = []
    with ServiceFactory() as factory:
        try:
            session_svc = factory.get_session_service()
            session_svc.maybe_cleanup()
            account_svc = factory.get_account_service()
            accounts = account_svc.list_accounts()
            store = factory.get_store()
            session_counts = store.get_active_session_counts()

            # Detect active account
            active_uuid = None
            try:
                if CPATH.exists():
                    cred_store = CredentialStore(CPATH)
                    raw = json.loads(CPATH.read_text(encoding='utf-8'))
                    current_refresh = raw.get('claudeAiOauth', {}).get('refreshToken')
                    current_token = raw.get('claudeAiOauth', {}).get('accessToken')
                    for acc in accounts:
                        try:
                            acc_creds = acc.get_credentials()
                            acc_refresh = acc_creds.get('claudeAiOauth', {}).get('refreshToken')
                            if acc_refresh and acc_refresh == current_refresh:
                                active_uuid = acc.uuid
                                break
                            if acc.api_key and acc.api_key == current_token:
                                active_uuid = acc.uuid
                                break
                        except Exception:
                            pass
            except Exception:
                pass

            for acc in accounts:
                usage_info = None
                needs_reauth = acc.needs_reauth

                try:
                    # Use cached usage (up to 5 min old) to avoid hammering the API
                    cached = store.get_recent_usage(acc.uuid, max_age_seconds=300)
                    if cached:
                        usage_info = {
                            'five_hour': {'utilization': cached.five_hour.utilization},
                            'seven_day': {
                                'utilization': cached.seven_day.utilization,
                                'resets_at': cached.seven_day.resets_at,
                            },
                            'seven_day_opus': {
                                'utilization': cached.seven_day_opus.utilization,
                                'resets_at': cached.seven_day_opus.resets_at,
                            },
                            'seven_day_sonnet': {
                                'utilization': cached.seven_day_sonnet.utilization,
                                'resets_at': cached.seven_day_sonnet.resets_at,
                            },
                        }
                    else:
                        # Fetch live — refresh token first
                        cred_store = CredentialStore(CPATH)
                        refreshed = cred_store.refresh_access_token(acc.credentials_json)
                        token = refreshed.get('claudeAiOauth', {}).get('accessToken')
                        if token:
                            usage_info = ClaudeAPI.get_usage(token)
                            store.save_usage(acc.uuid, usage_info)
                except Exception:
                    pass

                results.append({
                    'index': acc.index_num,
                    'uuid': acc.uuid,
                    'nickname': acc.nickname,
                    'email': acc.email,
                    'usage': usage_info,
                    'sessions': session_counts.get(acc.uuid, 0),
                    'needs_reauth': needs_reauth,
                    'is_active': acc.uuid == active_uuid,
                })

        except Exception:
            pass

    return results


def _write_status_cache(accounts: list) -> None:
    """Write active account + usage to STATUS_CACHE_PATH for fast statusline reads."""
    RESET  = '\033[00m'
    PURPLE = '\033[38;5;141m'
    GREEN  = '\033[38;5;82m'
    YELLOW = '\033[38;5;226m'
    RED    = '\033[38;5;196m'

    def _usage_color(pct: float) -> str:
        if pct >= 90:
            return RED
        if pct >= 70:
            return YELLOW
        return GREEN

    try:
        line = ''
        for acc in accounts:
            if not acc.get('is_active'):
                continue
            nickname = acc.get('nickname') or (acc.get('email', '').split('@')[0])
            line = f"{PURPLE}[{acc['index']}] {nickname}{RESET}"

            usage = acc.get('usage') or {}
            fh_util = (usage.get('five_hour') or {}).get('utilization')
            sd_util = (usage.get('seven_day') or {}).get('utilization')

            parts = []
            if fh_util is not None:
                parts.append(f"5h:{_usage_color(fh_util)}{round(fh_util)}%{RESET}")
            if sd_util is not None:
                parts.append(f"7d:{_usage_color(sd_util)}{round(sd_util)}%{RESET}")
            if parts:
                line += ' ' + ' '.join(parts)
            break
        STATUS_CACHE_PATH.write_text(line, encoding='utf-8')
    except Exception:
        pass


def _try_import_credentials() -> bool:
    """Try to import the current credentials file as a new account.

    Returns True if an account was added or updated. Retries on transient errors
    (e.g., profile fetch network failure) so stale credentials don't persist.
    """
    for attempt in range(3):
        try:
            cred_path = CREDENTIALS_PATH
            if not cred_path.exists():
                return False
            creds_json = cred_path.read_text(encoding='utf-8')
            with ServiceFactory() as factory:
                account_svc = factory.get_account_service()
                _account, is_new = account_svc.add_account(creds_json)
                return True
        except Exception:
            if attempt < 2:
                time.sleep(1)
    return False


def _do_auto_switch():
    """Switch to the optimal account via the service layer."""
    try:
        with ServiceFactory() as factory:
            svc = factory.get_switching_service()
            svc.select_optimal(dry_run=False)
    except Exception:
        pass


class TrayMonitor:
    """Background daemon thread managing all periodic tasks for the tray app.

    Callbacks (all called from the monitor thread — UI code must be thread-safe):
        on_data_updated(accounts: list[dict])
        on_processing_changed(is_processing: bool)
        on_new_account_detected()
        on_auto_switched()
    """

    def __init__(
        self,
        on_data_updated: Callable[[list[dict]], None],
        on_processing_changed: Optional[Callable[[bool], None]] = None,
        on_new_account_detected: Optional[Callable[[], None]] = None,
        on_auto_switched: Optional[Callable[[], None]] = None,
    ):
        self._on_data_updated = on_data_updated
        self._on_processing_changed = on_processing_changed
        self._on_new_account_detected = on_new_account_detected
        self._on_auto_switched = on_auto_switched

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name='c2s-monitor')

        # State
        self._last_refresh_time: float = 0
        self._last_auto_switch_time: float = 0
        self._last_processing_detected_at: float = 0
        self._session_active: bool = False
        self._last_known_refresh_token: Optional[str] = _read_refresh_token(CREDENTIALS_PATH)
        self._last_cred_mtime: float = 0
        self._cred_changed_at: float = 0  # debounce timestamp
        self._pending_cred_check: bool = False

        self._prev_connections: frozenset = frozenset()

        # Latest data snapshot (read from tray app, written from monitor thread)
        self._lock = threading.Lock()
        self._accounts: list[dict] = []

        # Force-refresh flag (set by UI to trigger immediate update)
        self._force_refresh = threading.Event()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._thread.join(timeout=5)

    def force_refresh(self):
        """Request an immediate data refresh (called from UI thread)."""
        self._force_refresh.set()

    def get_accounts(self) -> list[dict]:
        with self._lock:
            return list(self._accounts)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run(self):
        # On first launch, if credentials exist but no accounts are registered,
        # auto-import so the user doesn't have to run `c2switcher add` manually.
        _try_import_credentials()

        # Initial fetch
        self._do_refresh()

        cred_path = CREDENTIALS_PATH
        try:
            self._last_cred_mtime = cred_path.stat().st_mtime
        except Exception:
            self._last_cred_mtime = 0

        while not self._stop_event.is_set():
            now = time.monotonic()

            # ── Force-refresh requested by UI ─────────────────────────────────
            if self._force_refresh.is_set():
                self._force_refresh.clear()
                self._do_refresh()
                self._last_refresh_time = now

            # ── Periodic 60-second refresh ────────────────────────────────────
            elif now - self._last_refresh_time >= UPDATE_INTERVAL_SECONDS:
                self._do_refresh()
                self._last_refresh_time = now

            # ── Session / processing detection ────────────────────────────────
            pids = _get_claude_pids()
            active_now, self._prev_connections = is_claude_processing(pids, self._prev_connections)
            if active_now:
                self._last_processing_detected_at = now

            sticky_locked = (now - self._last_processing_detected_at) < PROCESSING_LOCK_DECAY_SECONDS
            new_processing_state = active_now or sticky_locked

            if new_processing_state != self._session_active:
                self._session_active = new_processing_state
                if self._on_processing_changed:
                    self._on_processing_changed(self._session_active)

            # ── Credential file monitoring (new login detection) ──────────────
            try:
                mtime = cred_path.stat().st_mtime
                if mtime != self._last_cred_mtime:
                    self._last_cred_mtime = mtime
                    self._cred_changed_at = now
                    self._pending_cred_check = True
            except Exception:
                pass

            if self._pending_cred_check and (now - self._cred_changed_at) >= CRED_DEBOUNCE_SECONDS:
                self._pending_cred_check = False
                self._check_for_new_login()

            # ── Auto-switch on rate limit ─────────────────────────────────────
            cooldown_ok = (now - self._last_auto_switch_time) >= AUTO_SWITCH_COOLDOWN_SECONDS
            no_session = len(pids) == 0

            if cooldown_ok and (no_session or not self._session_active):
                if self._current_account_maxed() and self._has_other_accounts():
                    self._last_auto_switch_time = now
                    _do_auto_switch()
                    if self._on_auto_switched:
                        self._on_auto_switched()
                    self._do_refresh()
                    self._last_refresh_time = time.monotonic()

            time.sleep(CRED_POLL_INTERVAL_SECONDS)

    def _do_refresh(self):
        try:
            data = _fetch_usage_data()
        except Exception:
            data = []
        with self._lock:
            self._accounts = data
        _write_status_cache(data)
        self._on_data_updated(data)

    def _check_for_new_login(self):
        """Compare current refresh token to last known — import if different."""
        new_token = _read_refresh_token(CREDENTIALS_PATH)
        if new_token and new_token != self._last_known_refresh_token:
            self._last_known_refresh_token = new_token
            # Actually import the account into the database
            _try_import_credentials()
            if self._on_new_account_detected:
                self._on_new_account_detected()
            # Refresh data so the new account shows up
            self._do_refresh()

    def _current_account_maxed(self) -> bool:
        with self._lock:
            accounts = self._accounts
        for acc in accounts:
            if not acc.get('is_active'):
                continue
            usage = acc.get('usage') or {}
            fh = (usage.get('five_hour') or {}).get('utilization')
            sn = (usage.get('seven_day_sonnet') or {}).get('utilization')
            if fh is not None and fh >= RATE_LIMIT_THRESHOLD:
                return True
            if sn is not None and sn >= RATE_LIMIT_THRESHOLD:
                return True
        return False

    def _has_other_accounts(self) -> bool:
        with self._lock:
            return len(self._accounts) > 1
