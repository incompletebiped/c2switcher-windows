"""Token refresh and credentials persistence."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Dict

import requests

from typing import TYPE_CHECKING

from ..constants import CLAUDE_DIR, CREDENTIALS_PATH, console
from ..core.errors import InvalidCredentials, InvalidGrant, TokenUnavailable

if TYPE_CHECKING:
    from ..core.models import Account


class CredentialStore:
    """
    Manages OAuth token refresh and credential file synchronization.

    Responsibilities:
    - Refresh access tokens via Anthropic OAuth endpoint
    - Write credentials to ~/.claude/.credentials.json
    - Provide dry-run mode for testing
    """

    OAUTH_ENDPOINT = 'https://platform.claude.com/v1/oauth/token'
    CLIENT_ID = '9d1c250a-e61b-44d9-88ed-5944d1962f5e'
    REFRESH_BUFFER_MS = 600_000  # 10 minutes

    def __init__(self, credentials_path: Path = CREDENTIALS_PATH):
        self.credentials_path = credentials_path

    def parse_credentials(self, credentials_json: str) -> Dict:
        """Parse credentials JSON with validation."""
        try:
            creds = json.loads(credentials_json)
            if not isinstance(creds, dict):
                raise InvalidCredentials('Credentials must be a JSON object')
            if 'claudeAiOauth' not in creds:
                raise InvalidCredentials('Missing claudeAiOauth field')
            return creds
        except json.JSONDecodeError as exc:
            raise InvalidCredentials(f'Invalid JSON: {exc}')

    def is_token_fresh(self, credentials: Dict, force: bool = False) -> bool:
        """Check if access token is still valid."""
        if force:
            return False

        expires_at = credentials.get('claudeAiOauth', {}).get('expiresAt', 0)
        now_ms = int(time.time() * 1000)
        return expires_at - self.REFRESH_BUFFER_MS > now_ms

    def validate_refresh_token(self, credentials_json: str) -> bool:
        """
        Test whether the refresh token is still valid by attempting a refresh.

        Returns True if valid, raises InvalidGrant if revoked/expired.
        Other errors (network, etc.) raise TokenUnavailable.
        """
        self.refresh_access_token(credentials_json, force=True)
        return True

    def refresh_access_token(self, credentials_json: str, force: bool = False) -> Dict:
        """
        Refresh OAuth access token.

        Returns updated credentials dict with new access token.
        Raises TokenUnavailable if refresh fails.
        """
        creds = self.parse_credentials(credentials_json)

        if self.is_token_fresh(creds, force):
            return creds

        oauth = creds.get('claudeAiOauth', {})
        refresh_token = oauth.get('refreshToken')

        if not refresh_token:
            raise TokenUnavailable('No refresh token available')

        from ..infrastructure.auth_log import log as _alog, tok as _tok
        console.print('[yellow]Refreshing token...[/yellow]')

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = requests.post(
                    self.OAUTH_ENDPOINT,
                    json={
                        'grant_type': 'refresh_token',
                        'refresh_token': refresh_token,
                        'client_id': self.CLIENT_ID,
                    },
                    timeout=10,
                )
            except requests.RequestException:
                if attempt < max_attempts - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise TokenUnavailable('Token refresh failed: network error (check your connection)')

            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 2 ** attempt))
                if attempt < max_attempts - 1:
                    time.sleep(min(retry_after, 30))
                    continue
                raise TokenUnavailable('Token refresh failed: rate limited by server')

            break

        if response.status_code != 200:
            error_msg = f'Token refresh failed (HTTP {response.status_code})'
            try:
                error_data = response.json()
                error_type = error_data.get('error', '')
                error_desc = error_data.get('error_description', '')
                if error_type == 'invalid_grant':
                    _alog('INVALID_GRANT', context='token_refresh', tok=_tok(refresh_token))
                    raise InvalidGrant(
                        f'Refresh token expired or revoked. Re-authenticate with: c2switcher login'
                    )
                elif error_type:
                    error_msg = f'Token refresh failed: {error_type}'
            except (ValueError, KeyError):
                pass
            raise TokenUnavailable(error_msg)

        token_data = response.json()

        new_creds = copy.deepcopy(creds)
        new_creds['claudeAiOauth']['accessToken'] = token_data['access_token']
        new_refresh = token_data.get('refresh_token', refresh_token)
        new_creds['claudeAiOauth']['refreshToken'] = new_refresh
        new_creds['claudeAiOauth']['expiresAt'] = int(time.time() * 1000) + (
            token_data.get('expires_in', 3600) * 1000
        )

        if new_refresh != refresh_token:
            _alog('TOKEN_ROTATED', old=_tok(refresh_token), new=_tok(new_refresh))

        console.print('[green]Token refreshed successfully[/green]')
        return new_creds

    def write_credentials(self, credentials: Dict):
        """Write credentials to ~/.claude/.credentials.json."""
        from ..infrastructure.auth_log import log as _alog, tok as _tok
        _refresh = credentials.get('claudeAiOauth', {}).get('refreshToken')
        _alog('CRED_FILE_WRITE', tok=_tok(_refresh))
        CLAUDE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

        try:
            import os

            os.chmod(CLAUDE_DIR, 0o700)
        except OSError:
            pass

        import secrets as _secrets
        temp_path = self.credentials_path.with_suffix(f'.{_secrets.token_hex(8)}.tmp')
        try:
            with temp_path.open('w', encoding='utf-8') as f:
                json.dump(credentials, f, indent=2)

            import os

            os.chmod(temp_path, 0o600)

            temp_path.replace(self.credentials_path)

        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def write_credentials_for_account(self, account: 'Account', oauth_credentials: Dict):
        """
        Write credentials for account, using API key format when available.

        When the account has an api_key, writes a simplified format:
        {"claudeAiOauth": {"accessToken": "<api_key>", "scopes": ["user:inference"]}}

        Otherwise writes the full OAuth credentials.
        """
        if account.api_key:
            credentials = {
                'claudeAiOauth': {
                    'accessToken': account.api_key,
                    'scopes': ['user:inference'],
                }
            }
        else:
            credentials = oauth_credentials

        self.write_credentials(credentials)

    def refresh_and_persist(self, credentials_json: str, force: bool = False, dry_run: bool = False) -> Dict:
        """
        Refresh token and write to disk.

        Args:
           credentials_json: Current credentials JSON string
           force: Force refresh even if token is fresh
           dry_run: Skip writing to disk (for testing)

        Returns:
           Updated credentials dict
        """
        refreshed = self.refresh_access_token(credentials_json, force=force)

        if not dry_run:
            self.write_credentials(refreshed)

        return refreshed

    def get_access_token(self, credentials_json: str, force: bool = False) -> str:
        """
        Extract access token, refreshing if necessary.

        Returns:
           Access token string

        Raises:
           TokenUnavailable: If token cannot be obtained
        """
        refreshed = self.refresh_access_token(credentials_json, force=force)
        token = refreshed.get('claudeAiOauth', {}).get('accessToken')

        if not token:
            raise TokenUnavailable('No access token in refreshed credentials')

        return token
