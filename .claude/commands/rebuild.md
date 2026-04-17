Rebuild the c2switcher executable using build.ps1 and report the result.

## Steps

1. **Run the build** from the project root:
   ```
   powershell -ExecutionPolicy Bypass -File build.ps1
   ```
   Stream output so the user can see progress. This takes 60–90 seconds.

2. **Check the result:**
   - If the last lines contain `Build complete` and `OK  ...c2switcher.exe` — success.
   - If PyInstaller prints `ERROR` or exits non-zero — show the relevant error lines and stop.

3. **On success, tell the user:**
   - The exe path: `C:\Users\<username>\AppData\Local\Programs\Common\c2switcher.exe`
   - **Restart the tray app** for the new binary to take effect: quit via the right-click tray menu, then relaunch `c2switcher.exe`.
   - If the statusline is configured, it will update automatically after the first 60-second refresh cycle.

4. **On failure**, show the error and suggest:
   - Check that the virtual environment is active and dependencies are installed (`pip install -e .[build]`)
   - Check for Python/PyInstaller version issues in the output
