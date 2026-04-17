Diagnose the health of the c2switcher installation and surface any problems.

## Checks to run (in order)

### 1. Tray process
Run:
```
powershell -NoProfile -Command "Get-Process | Where-Object {$_.Name -like '*c2switcher*'} | Select-Object Name, Id, CPU | Format-Table -AutoSize"
```
- **Pass:** process found
- **Fail:** tray is not running — statusline won't update, auto-switch won't work. Tell user to launch `c2switcher.exe`.

### 2. Status cache file
Run:
```
powershell -NoProfile -Command "$f='$env:APPDATA\c2switcher\current_account.txt'; if(Test-Path $f){ $age=[int]((Get-Date)-(Get-Item $f).LastWriteTime).TotalSeconds; Write-Host \"EXISTS age=${age}s\"; Get-Content $f -Raw } else { Write-Host 'MISSING' }"
```
- **Pass:** file exists. Show its contents and age.
- **Warn:** age > 120s — tray may be stalled or freshly started.
- **Fail:** file missing — tray hasn't run its first refresh yet, or is not running.

### 3. Registered accounts
Run:
```
c2switcher ls
```
- **Pass:** one or more accounts listed.
- **Fail:** no accounts — user needs to run `c2switcher login`.

### 4. Account health (needs_reauth + token state)
Run:
```
c2switcher usage --json
```
Parse the JSON output and for each account report:
- `needs_reauth: true` → **Token expired** — user must click Re-auth in the tray or run `c2switcher login`
- `usage: null` → usage fetch failed (may indicate a stale token not yet flagged)
- Otherwise → healthy, show utilization percentages

### 5. Credentials file
Run:
```
powershell -NoProfile -Command "$f='$env:USERPROFILE\.claude\.credentials.json'; if(Test-Path $f){ $age=[int]((Get-Date)-(Get-Item $f).LastWriteTime).TotalSeconds; Write-Host \"EXISTS age=${age}s\" } else { Write-Host 'MISSING' }"
```
- **Pass:** file exists. Show age.
- **Fail:** file missing — no active account; Claude Code will prompt for login.

## Summary

After all checks, print a summary table:

| Check | Status | Note |
|-------|--------|------|
| Tray running | ✓/✗ | ... |
| Cache file | ✓/✗/⚠ | age |
| Accounts registered | ✓/✗ | count |
| Tokens valid | ✓/✗ | any expired? |
| Credentials file | ✓/✗ | age |

Then state clearly: **All systems healthy** or list the specific actions needed to fix each failing check.
