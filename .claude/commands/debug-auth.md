Diagnose OAuth token health across all c2switcher accounts to identify stale or invalidated credentials.

## Steps

### 1. Get account list and reauth flags
Run:
```
c2switcher usage --json
```
For each account, extract and display:
- `index`, `email`, `nickname`
- `needs_reauth` flag
- Whether `usage` is null (null = token may be stale even if not yet flagged)

### 2. Read the active credentials file
Run:
```
powershell -NoProfile -Command "$f='$env:USERPROFILE\.claude\.credentials.json'; if(Test-Path $f){ Get-Content $f -Raw } else { Write-Host 'MISSING' }"
```
Parse the JSON and extract:
- `claudeAiOauth.refreshToken` (first 12 chars only — never show the full token)
- `claudeAiOauth.expiresAt` — convert from epoch ms to a readable datetime and show time remaining
- `claudeAiOauth.accessToken` (first 12 chars only)

### 3. Read each account's stored credentials from the DB
Run:
```
c2switcher current --json
```
and also check the DB file age:
```
powershell -NoProfile -Command "$f='$env:APPDATA\c2switcher\store.db'; if(Test-Path $f){ $age=[int]((Get-Date)-(Get-Item $f).LastWriteTime).TotalSeconds; Write-Host \"DB last modified: ${age}s ago\" }"
```

### 4. Cross-reference active credentials with registered accounts
Compare the refresh token prefix from `.credentials.json` against what we know about which account is active (from `c2switcher current`). Flag if there's a mismatch — it means the credentials file has been updated but the active account assignment hasn't caught up.

### 5. Summary report

Print a table:

| Account | needs_reauth | Usage null | Credentials match | Action needed |
|---------|-------------|------------|-------------------|---------------|
| #0 email | No | No | Yes (active) | None |
| #1 email | Yes | Yes | — | Re-auth required |
| #2 email | No | Yes | — | Monitor (may self-resolve) |

**For each account with `needs_reauth: true`:**
Tell the user to either:
- Click the **Re-auth** button in the tray popup for that account, OR
- Run `c2switcher login` and complete the OAuth flow for that email address

**If all accounts look healthy but the user is still experiencing issues:**
- Check if they've logged into claude.ai in a browser recently — that externally invalidates tokens and c2switcher cannot prevent it
- Confirm the tray app has been restarted since the last rebuild (old binary won't persist rotated tokens)
