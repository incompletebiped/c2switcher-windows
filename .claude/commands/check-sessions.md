Show active and recent Claude Code sessions tracked by c2switcher, and flag any cleanup issues.

## Steps

### 1. List active sessions
Run:
```
c2switcher list-sessions
```
Show the output. For each active session note: account assigned, PID, working directory, how long it's been running.

If no active sessions: say so — this is normal when Claude Code isn't currently running.

### 2. Check for stale sessions
Run:
```
powershell -NoProfile -Command "Get-Process | Where-Object {$_.Name -like '*claude*'} | Select-Object Name, Id, StartTime | Format-Table -AutoSize"
```
Cross-reference the PIDs from `list-sessions` against running processes:
- A session with a PID that no longer exists = **stale session** (should have been cleaned up)
- If stale sessions exist, note how many — they'll be cleaned up automatically on the next c2switcher operation, but can be cleared now by running a switch or optimal command.

### 3. Session history (last 10)
Run:
```
c2switcher session-history
```
Show the output. This gives a picture of recent usage patterns across accounts.

### 4. Active session counts per account
From the `list-sessions` output, summarize:

| Account | Active Sessions | Notes |
|---------|----------------|-------|
| #0 email | 0 | — |
| #1 email | 2 | 2 PIDs running |
| #2 email | 1 | 1 PID running |

### 5. Flag any anomalies
- **More than 5 active sessions for one account:** unusual, may indicate sessions didn't clean up properly
- **Sessions older than 24 hours:** almost certainly stale — psutil liveness check should have caught these; worth noting
- **Sessions with no account assigned:** session was registered before an account was selected (normal for very short sessions)

### 6. Summary
State: how many active sessions total, which accounts are in use, and whether any cleanup action is needed.
