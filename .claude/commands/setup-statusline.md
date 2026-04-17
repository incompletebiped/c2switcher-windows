Configure the Claude Code status line to show the active c2switcher account, nickname, and live usage percentages.

## What this does

Writes a `statusLine` entry to `~/.claude/settings.json` that reads from the c2switcher cache file (`%APPDATA%\c2switcher\current_account.txt`). The tray app writes that file on every refresh; the status line reads it instantly via `cat` (bash path syntax).

**Why not PowerShell:** PowerShell startup overhead (~800ms) is noticeable. Using `cat` with a Unix-style path (Git Bash / Claude Code's built-in shell) is near-instant.

**Prerequisite:** The c2switcher tray app must be running. It creates the cache file on first launch.

## Steps

1. **Detect the Windows username** by running:
   ```
   powershell -NoProfile -Command "$env:USERNAME"
   ```

2. **Read the current settings file** at `C:\Users\<username>\.claude\settings.json`. If it doesn't exist, treat it as `{}`.

3. **Build the statusLine command** using the detected username, converting the Windows path to Unix-style (forward slashes, `/c/` prefix):
   ```
   cat /c/Users/<username>/AppData/Roaming/c2switcher/current_account.txt
   ```

4. **Merge the statusLine config** into the settings JSON:
   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "cat /c/Users/<username>/AppData/Roaming/c2switcher/current_account.txt"
     }
   }
   ```
   Preserve all other existing keys. If a `statusLine` key already exists, overwrite it.

5. **Write the merged JSON** back to `~/.claude/settings.json` with 2-space indentation.

6. **Tell the user:**
   - The settings file path that was written
   - That they need to restart Claude Code for the change to take effect
   - That the status line will show `[index] nickname  5h:X%  7d:X%` in color once the tray app has run its first refresh

## Troubleshooting hints to mention

- **Nothing shows:** Confirm the tray app is running and the cache file exists at `%APPDATA%\c2switcher\current_account.txt`
- **Plain text with no color:** Running an old build — rebuild with `.\build.ps1` and restart the tray
- **Escape codes show as literal text:** Claude Code version doesn't support ANSI in the status line — upgrade Claude Code
