# C2Switcher (Windows Edition)

> Manage multiple Claude Code accounts with usage tracking, load balancing, and a system tray app

**This project is derived from [can1357/c2switcher](https://github.com/can1357/c2switcher)**, the original multi-account Claude Code manager created by [@can1357](https://github.com/can1357). The core concept, load-balancing algorithm, and CLI design all originate there. All credit for the original idea and implementation belongs to them.

The lineage is:

```
can1357/c2switcher  (original — KDE Plasma widget + CLI)
       ↓
incompletebiped/c2switcher-mint  (Linux port — Cinnamon panel applet)
       ↓
incompletebiped/c2switcher-windows  (this repo — Windows system tray app)
```

This Windows edition is a substantial adaptation rather than a direct code fork — the system tray UI was rewritten from scratch in PySide6, and Windows-specific changes were made throughout — but the foundational ideas, API approach, and load-balancing logic are entirely derived from the original work. The original is released under the MIT License.

## Features

- **Multi-account management** — Add, remove, reorder, and nickname accounts
- **Auto-detect new logins** — Tray app monitors `~\.claude\.credentials.json` and auto-imports new accounts
- **Usage tracking** — Monitor 5-hour, 7-day, and Sonnet usage limits with color-coded indicators
- **Smart load balancing** — Automatically picks the optimal account based on usage, drain rates, and active sessions
- **Session-safe switching** — Detects when Claude Code is actively processing and blocks switching mid-request
- **Auto-switch on rate limit** — When your current account hits 95%+ usage, automatically swaps to the optimal account between prompts or after the session ends
- **Active account indicator** — Shows which account Claude Code is currently using
- **Session tracking** — See which accounts are actively being used and where
- **Light/dark themes** — Toggle between themes from the tray popup
- **Windows system tray app** — Monitor all accounts from the system tray with one-click switching
- **Usage caching** — Respects rate limits with 5-minute cache
- **Wrapper script** — `c2claude` PowerShell command for seamless account switching
- **Start with Windows** — Optional registry entry to launch the tray app at login
- **Single executable** — Builds to a standalone `c2switcher.exe` via PyInstaller

## Disclaimer

_This tool uses undocumented OAuth API endpoints to fetch usage data and authenticate accounts. While Anthropic allows users to create multiple accounts (confirmed by multiple people who asked Anthropic Staff), this implementation relies on reverse-engineered API endpoints that may change without notice._

_If Anthropic would prefer this tool not exist, please reach out and I'll gladly take it down._

---

## Installation

### Prerequisites

- **Windows 10/11**
- **Python 3.10+**
- **Claude Code** CLI installed and configured

### Option 1: Install from source

```bash
git clone https://github.com/incompletebiped/c2switcher-windows.git
cd c2switcher-windows
pip install -e .
```

### Option 2: Build standalone executable

```bash
pip install -e .[build]
pyinstaller build.spec
# produces dist/c2switcher.exe
```

Place `c2switcher.exe` somewhere on your PATH, or keep it alongside `c2claude.ps1`.

### Setup the PowerShell wrapper

Copy `c2claude.ps1` to a directory on your PATH, or create a PowerShell alias:

```powershell
Set-Alias c2claude "C:\path\to\c2claude.ps1"
```

### Add your accounts

```bash
# Recommended: OAuth login (opens browser)
c2switcher login

# Add more accounts
c2switcher login

# Or import existing credentials from ~/.claude/.credentials.json
c2switcher add
```

### Nickname your accounts

```bash
c2switcher nickname 0 main
c2switcher nickname 1 work
```

### Verify it works

```bash
# Check that accounts are registered
c2switcher ls

# Fetch usage
c2switcher usage

# Launch Claude with the optimal account
c2claude
```

---

## System Tray App

Run `c2switcher` with no arguments (or double-click `c2switcher.exe`) to launch the system tray app.

### What it shows

**Tray icon:** Color-coded by overall usage status:
- **Green** (< 70%) — Plenty of headroom
- **Yellow** (70–90%) — Getting close
- **Red** (> 90%) — Nearly exhausted

**Popup (click the tray icon):**
- **Header** with refresh and optimal-switch buttons
- **Usage bars** showing per-account utilization
- **Account cards** — one per account, showing:
  - Active indicator for the currently active account
  - Index, nickname, and email
  - Usage indicators: 5-hour, 7-day, and Sonnet
  - Time-until-reset countdown
- **Light/dark theme toggle**

### Session-safe switching

The tray app detects whether Claude Code is actively processing by checking for established TCP connections from Claude's PIDs via `psutil`:

| State | Optimal button | Manual card click |
|---|---|---|
| Claude idle at prompt | Unlocked | Works |
| Claude streaming a response | Locked | Works (use at your own risk) |
| No Claude process running | Unlocked | Works |

### Auto-switch on rate limit

When the current account's usage reaches 95%+ (on either the 5-hour or 7-day window), the tray app automatically switches to the optimal account:

- **Between prompts** — If Claude is open but idle, credentials are swapped seamlessly
- **After session ends** — If Claude Code is closed, credentials are pre-positioned for the next session
- **During processing** — Auto-switch waits until the current request finishes
- **5-minute cooldown** between auto-switches to prevent rapid back-and-forth
- Only triggers when there are 2+ accounts registered

### Auto-detect new logins

The tray app monitors `~\.claude\.credentials.json` for changes. When a new login is detected (refresh token changes), the new account is automatically imported. Regular token refreshes are ignored.

### Start with Windows

The tray app can register itself in the Windows startup registry (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`) to launch automatically at login.

### Optional: Claude Code Status Line

Show the active account, nickname, and live usage in the Claude Code status bar.

**What it looks like:**
```
[1] BxB Media  5h:20%  7d:3%
```

The label `[index] nickname` is purple. Each percentage is color-coded green/yellow/red matching the tray thresholds (< 70% / 70–90% / > 90%).

**Why this approach:** `c2switcher.exe` takes ~3–4 seconds to start (PyInstaller + SQLite + DPAPI) — far too slow for a status line. Instead, the tray app writes `%APPDATA%\c2switcher\current_account.txt` on every refresh (every 60s and on each switch), and the status line reads that file directly via PowerShell (~800ms).

**Prerequisite:** The tray app must be running. It writes the cache file; the status line just reads it. The file is created on the tray's first refresh after launch.

**Setup:**

Add to `%USERPROFILE%\.claude\settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "powershell -NoProfile -NonInteractive -Command \"$f='C:\\Users\\YOUR_USERNAME\\AppData\\Roaming\\c2switcher\\current_account.txt';if(Test-Path $f){(gc $f -Raw).Trim()}\""
  }
}
```

Replace `YOUR_USERNAME` with your Windows username. Restart Claude Code for the setting to take effect.

**Troubleshooting:**

| Symptom | Fix |
|---|---|
| Nothing shows | Confirm the tray app is running and `%APPDATA%\c2switcher\current_account.txt` exists |
| Plain text `[1] nickname` with no usage or color | Tray app is running an old build — rebuild with `.\build.ps1` and restart |
| Escape codes show as literal text (`[38;5;141m...`) | Claude Code version doesn't support ANSI in the statusline — upgrade Claude Code |

**Rebuilding after source changes:**

Always use `build.ps1` — it installs to the correct location and creates the Start Menu shortcut:

```powershell
.\build.ps1
```

Do **not** run `pyinstaller build.spec` directly (that outputs to `dist/` and won't update the installed exe). After rebuilding, restart the tray app for changes to take effect.

---

## CLI Usage

### Adding Accounts

**Option 1: OAuth Login (Recommended)**

```bash
c2switcher login
```

**Option 2: Import Existing Credentials**

```bash
c2switcher add                                            # Add current account
c2switcher add --nickname work                            # With a nickname
c2switcher add --creds-file ~/path/to/credentials.json    # From a specific file
```

### Viewing Accounts

```bash
c2switcher ls
```

### Editing Nicknames

```bash
c2switcher nickname 0 "My Work Account"    # By index
c2switcher nickname work "Work Pro"        # By current nickname
c2switcher nickname user@email.com "Main"  # By email
```

### Removing Accounts

```bash
c2switcher remove 0                        # By index (prompts for confirmation)
c2switcher remove work                     # By nickname
c2switcher remove user@email.com           # By email
c2switcher remove 0 --yes                  # Skip confirmation
```

If the removed account is currently active in `~\.claude\.credentials.json`, the credentials file is also cleared.

### Checking Usage

```bash
c2switcher usage            # Rich table output
c2switcher usage --force    # Bypass 5-minute cache
c2switcher usage --json     # JSON output for scripting
```

Color indicators:
- **Green** (< 70%) — Plenty of headroom
- **Yellow** (70–90%) — Getting close
- **Red** (> 90%) — Nearly exhausted

### Switching Accounts

```bash
c2switcher switch 0                    # By index
c2switcher switch work                 # By nickname
c2switcher switch user@example.com     # By email
```

### Finding the Optimal Account

```bash
c2switcher optimal                       # Auto-switch to best account
c2switcher optimal --dry-run             # Show best without switching
c2switcher optimal --token-only --quiet  # Get token for scripts
```

### Cycling Through Accounts

```bash
c2switcher cycle       # Rotate to next account
```

### Checking Current Account

```bash
c2switcher current
c2switcher current --format=prompt     # For shell prompts: [0] main
c2switcher current --json
```

### Generating Analytics Reports

```bash
# Session insights (top projects, daily cadence, heatmaps)
c2switcher report-sessions --output ~/c2switcher_session_report.png --days 30

# Usage risk forecast (burn rates, reset timeline)
c2switcher report-usage --output ~/c2switcher_usage_report.png --window-hours 24
```

---

## The `c2claude` Wrapper

PowerShell script that combines account selection with running Claude Code:

```powershell
c2claude                   # Use optimal account (default)
c2claude -0                # Use account 0
c2claude -1                # Use account 1
c2claude -a work           # Use account by name/email/index
c2claude --cycle           # Cycle to next account
c2claude -p "explain this" # Pass arguments to claude
```

The wrapper handles session registration, load balancing, account stickiness, and cleanup on exit.

---

## Command Reference

### Core Commands

| Command           | Aliases                 | Description                              |
| ----------------- | ----------------------- | ---------------------------------------- |
| `login`           |                         | OAuth login and add account              |
| `add`             |                         | Import existing account credentials      |
| `remove`          |                         | Remove an account from c2switcher        |
| `nickname`        |                         | Set or update an account nickname        |
| `reorder-accounts`|                         | Reorder accounts by specifying new order |
| `ls`              | `list`, `list-accounts` | List all accounts                        |
| `usage`           |                         | Show usage across accounts               |
| `current`         |                         | Show currently active account            |
| `force-refresh`   |                         | Force token refresh for account(s)       |
| `report-sessions` |                         | Generate session analytics report        |
| `report-usage`    |                         | Generate usage risk forecast report      |
| `optimal`         | `pick`                  | Find and switch to optimal account       |
| `switch`          | `use`                   | Switch to specific account               |
| `cycle`           |                         | Rotate to next account                   |
| `list-sessions`   |                         | List active sessions                     |
| `session-history` | `history`               | Show past sessions with usage deltas     |
| `apikey`          |                         | Manage API keys                          |

### Session Commands (used by `c2claude`, not typically manual)

| Command         | Description                   |
| --------------- | ----------------------------- |
| `start-session` | Register a new Claude session |
| `end-session`   | Mark a session as ended       |

---

## How It Works

### Database

All data is stored in `%APPDATA%\c2switcher\store.db` (SQLite):
- Account credentials and metadata
- Usage history with timestamps
- Session tracking (PID, working directory, duration)

### Token Refresh

Tokens are automatically refreshed when within 10 minutes of expiry. Force a manual refresh:

```bash
c2switcher force-refresh          # All accounts
c2switcher force-refresh work     # Specific account
```

### Usage Caching

API calls are cached for 5 minutes to avoid rate limiting. Use `--force` to bypass.

### Load Balancing Algorithm

The optimal account selection uses a multi-factor scoring system:

1. **Drain rate** (core metric) — `headroom / hours_until_reset` where headroom = 99% − current utilization. Higher drain rate = more capacity available per hour = better candidate.
2. **Five-hour throttling** — Penalizes accounts with high short-term usage to prevent burst rate limits. Score is halved at 90%+ five-hour utilization.
3. **Burst protection** — Skips accounts where current usage + expected burst (based on historical deltas) >= 94%.
4. **Pace alignment** — Adjusts score based on whether usage is ahead of or behind the expected pace for the reset window.
5. **Session awareness** — Among similar candidates, prefers accounts with fewer active and recent sessions.
6. **Round-robin** — Accounts within 0.05 %/hr of each other are treated as equivalent and rotated fairly.

Accounts at 99%+ utilization are excluded entirely.

### Session Tracking

Each `c2claude` invocation registers a session, selects an account, runs Claude, and cleans up on exit. Dead sessions are auto-cleaned via multi-factor liveness checks using `psutil`.

---

## Files and Paths

| Path | Purpose |
| ---- | ------- |
| `%APPDATA%\c2switcher\store.db` | SQLite database (accounts, usage, sessions) |
| `%APPDATA%\c2switcher\load_balancer_state.json` | Round-robin state for fair rotation |
| `%APPDATA%\c2switcher\.lock` | File lock for concurrent operation safety |
| `%APPDATA%\c2switcher\theme.json` | Theme preference (light/dark) |
| `%APPDATA%\c2switcher\headers.json` | HTTP header configuration |
| `%APPDATA%\c2switcher\current_account.txt` | Cache file for status line (written by tray app) |
| `~\.claude\.credentials.json` | Active Claude Code credentials |

## Environment Variables

| Variable | Description |
| -------- | ----------- |
| `DEBUG_SESSIONS=1` | Enable verbose session tracking logs |
| `C2SWITCHER_DEBUG_BALANCER=1` | Show detailed load balancer scoring |

---

## Differences from c2switcher-mint

| | Mint (Linux) | Windows |
|---|---|---|
| **Desktop integration** | Cinnamon panel applet (JavaScript) | System tray app (PySide6 + pystray) |
| **Process detection** | `ss` (socket statistics) | `psutil` |
| **Data directory** | `~/.c2switcher/` | `%APPDATA%\c2switcher\` |
| **Wrapper script** | `c2claude` (Bash) | `c2claude.ps1` (PowerShell) |
| **Startup** | Desktop autostart | Windows registry (`HKCU\...\Run`) |
| **Distribution** | `pipx install` | `pip install` or standalone `.exe` via PyInstaller |
| **Installer** | `setup.sh` | Manual |

---

## Troubleshooting

### "c2switcher: command not found"

Ensure the install location is on your PATH. If installed via pip:

```powershell
# Check where it was installed
pip show c2switcher
# Or for the exe build, add dist/ to your PATH
```

### Token refresh fails

```bash
c2switcher login
```

Log in with the affected account — the existing account record is updated automatically by UUID match.

Verify Claude works: `claude -p hi --model haiku`

### Sessions not tracked properly

Dead sessions auto-cleanup, but you can check manually:

```bash
c2switcher list-sessions
```

### Tray app doesn't show usage

Make sure `c2switcher` is on your PATH and that accounts have been added:

```bash
c2switcher ls
c2switcher usage
```

---

## Development

```bash
git clone https://github.com/incompletebiped/c2switcher-windows.git
cd c2switcher-windows
pip install -e .
c2switcher --help
```

The CLI entry point is `c2switcher`, and the Python package lives under `c2switcher/`. The system tray app source is in `c2switcher/presentation/tray/`.

## Credits

Based on [c2switcher-mint](https://github.com/incompletebiped/c2switcher-mint), itself a fork of [can1357/c2switcher](https://github.com/can1357/c2switcher).

---

**Tip**: Add `c2claude.ps1` to your PowerShell profile as an alias for maximum laziness.
