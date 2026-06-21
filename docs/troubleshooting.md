# Troubleshooting

## OAuth / auth errors

### `credentials.json` not found
The script resolves it from the CWD. Either `cd` to the directory containing `credentials.json` before running, or pass the file via environment variable if the script supports it. Usually easiest: put `credentials.json` in the repo root and run from there.

### `Error: access_denied` in the browser
You're signed into a Gmail account that isn't listed as a Test User on your OAuth consent screen. Options:
1. Sign out of all Google accounts, sign into only the target account, retry.
2. Add the target account to Test Users: Google Cloud Console → APIs & Services → OAuth consent screen → Test users → Add.

### `403 Request had insufficient authentication scopes`
Your cached `token.json` was granted a narrower scope than the script now requests. Fix: delete `token.json` and re-run — the browser flow will re-prompt for the full `gmail.modify` scope.

### `invalid_grant` / refresh token expired
Happens if your OAuth consent is in "Testing" status and hasn't been used for 7 days (Google auto-expires test tokens). Fix: delete `token.json` and re-auth.

### "Google hasn't verified this app"
Expected — *you* are the app owner, not a verified vendor. Click **Advanced** → **Go to Inbox Sweep (unsafe)**. This warning is meant for strangers running a random third-party app against their Gmail; it's noise when you're running your own code against your own account.

## Runtime errors

### `429 Too Many Requests`
The script's `with_retry` decorator handles this — exponential backoff, 5 attempts. If you see it surfaced as an unhandled error, something is wrong — file an issue with the stack trace.

### `503 Service Unavailable`
Gmail is having a bad moment. Same retry logic applies. If it persists beyond 5 attempts, wait 10 minutes and re-run.

### `cluster-report stale — execute blocked`
Freshness gate is working as intended. Re-run:
```bash
python plugin/scripts/gmail_cleanup.py --cluster-report --category <name> --before-date <date>
```
Then re-try execute within 4 hours.

Override (pilots only, not routine):
```bash
python plugin/scripts/gmail_cleanup.py --category <name> --before-date <date> --skip-freshness-check
```

### `STARRED overlap > 0 — execute blocked`
**Do not bypass this.** It means a message tagged STARRED made it into the delete candidate set. Options:
1. Open each offending ID in Gmail (they're printed in the error). Decide per-message: un-star (to allow delete) or add sender to `whitelist.yaml`.
2. If you want *all* of them preserved, the existing STARRED exclusion already does that — just retry and they should now be out of the candidate set.

### `Python module not found: googleapiclient`
```bash
pip install -r plugin/requirements.txt
```
If you use multiple Python versions, be explicit: `python3 -m pip install -r plugin/requirements.txt`.

## Windows-specific

### `pre-cleanup-check.sh: command not found`
Claude Code runs bash hooks via Git Bash on Windows. If Git Bash isn't installed: `winget install Git.Git`.

### Symlink creation failed
`New-Item -ItemType SymbolicLink` needs Developer Mode enabled (Settings → Privacy & Security → For developers → Developer Mode ON) OR an elevated pwsh. Alternative: copy the plugin dir instead of symlinking (you'll need to re-copy after every code change — symlink is better for dogfooding).

## Gmail behavior questions

### "I deleted 500 messages but only 470 show in Trash"
Gmail dedupes threads in some views. Search `in:trash` directly (not just "Trash" in the sidebar) to see all deleted messages. Count via URL: `https://mail.google.com/mail/u/0/#search/in%3Atrash+before%3A2019%2F01%2F01`.

### "I trashed messages but my storage didn't go down"
Gmail storage is tied to the total account size including Trash. Messages count against your quota until they're permanently deleted (after 30 days, or manually via `in:trash` → Empty Trash now).

### "Can I recover after 30 days?"
No. Trash is purged automatically. If you need a longer recovery window, export to `.mbox` via Google Takeout before running Inbox Sweep.

## Still stuck?
Open an issue at https://github.com/builtbyfn/inbox-sweep/issues — include the exact command, the error message, Python version (`python --version`), and OS.
