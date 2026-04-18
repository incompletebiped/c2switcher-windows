"""Diagnostic logging for OAuth token lifecycle events.

Log file: %APPDATA%\\c2switcher\\auth.log
Rotates at 500 KB (old file renamed to auth.1.log).

Event types:
  TOKEN_ROTATED   - refresh token changed during a successful token refresh
  INVALID_GRANT   - server rejected the refresh token
  NEEDS_REAUTH    - account marked needs_reauth=True in DB
  CRED_FILE_WRITE - .credentials.json was written
  SWITCH_TO       - explicit account switch requested
  RECOVERY_OK     - recovered stale DB token from .credentials.json
  RECOVERY_FAIL   - could not recover; no matching token in .credentials.json
"""
from __future__ import annotations

import datetime
from typing import Any

_LOG_MAX_BYTES = 512 * 1024  # 500 KB


def _log_path():
    from ..constants import C2SWITCHER_DIR
    return C2SWITCHER_DIR / 'auth.log'


def log(event: str, **fields: Any) -> None:
    """Append one timestamped line to auth.log.  Never raises."""
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if path.exists() and path.stat().st_size > _LOG_MAX_BYTES:
                path.replace(path.with_suffix('.1.log'))
        except Exception:
            pass
        parts = [datetime.datetime.now().isoformat(timespec='seconds'), event]
        parts += [f'{k}={v}' for k, v in fields.items()]
        with path.open('a', encoding='utf-8') as fh:
            fh.write(' '.join(parts) + '\n')
    except Exception:
        pass


def tok(token: str | None) -> str:
    """Return last 8 chars of a token — enough to identify it without exposing it."""
    if not token:
        return '(none)'
    s = str(token)
    return f'...{s[-8:]}' if len(s) > 8 else s
