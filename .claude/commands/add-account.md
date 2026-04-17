Guide the user through adding a new Claude account to c2switcher.

## Steps

### 1. Start the OAuth login flow
Tell the user:
> "This will open a browser window for authentication. Complete the login for the account you want to add, then return here."

Run:
```
c2switcher login
```
Wait for it to complete. On success it prints `✓ Account added` or `✓ Account updated` with the index and email.

If it fails, show the error and stop.

### 2. Set a nickname (optional but recommended)
Ask the user: **"What nickname do you want for this account? (press Enter to skip)"**

If they provide one, run:
```
c2switcher nickname <index> "<nickname>"
```
where `<index>` is from the login output.

### 3. Verify the account is registered
Run:
```
c2switcher ls
```
Show the output so the user can confirm the new account appears with the right email and nickname.

### 4. Verify usage fetch works
Run:
```
c2switcher usage
```
- **Pass:** the new account shows up with usage data (or `—` if Anthropic's API returns null, which is normal for fresh accounts).
- **Fail:** `needs_reauth` shown — something went wrong during login. Tell user to try `c2switcher login` again.

### 5. Done
Tell the user:
- The account is registered and will appear in the tray popup on its next refresh (up to 60 seconds).
- If the tray is running, click the refresh button (↻) in the popup header to see it immediately.
- To switch to this account: click its card in the tray popup, or run `c2switcher switch <index>`.
