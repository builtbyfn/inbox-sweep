# Setup — Google OAuth `credentials.json`

One-time, ~10 minutes. Result: a `credentials.json` file on disk that lets Inbox Sweep call the Gmail API on *your* account. Because you're the OAuth app owner, you skip Google's CASA verification — your account is always first-party.

## Steps

### 1. Create (or reuse) a Google Cloud project
1. Go to https://console.cloud.google.com
2. Top bar → project dropdown → **New Project**
3. Name it something like `inbox-sweep-<yourname>`. Location: No organization. Click **Create**.

### 2. Enable the Gmail API
1. Left nav → **APIs & Services** → **Library**
2. Search "Gmail API" → click → **Enable**

### 3. Configure the OAuth consent screen
1. Left nav → **APIs & Services** → **OAuth consent screen**
2. User Type: **External** → Create
3. Fill in:
   - App name: `Inbox Sweep` (or anything)
   - User support email: your Gmail
   - Developer contact: your Gmail
4. Save and continue through Scopes (leave empty, we'll use the script's declared scope at runtime) and Test users.
5. **Test users**: Add your own Gmail address. As long as you only use your own account, staying in "Testing" mode is fine indefinitely — no verification needed.

### 4. Create the OAuth 2.0 Client ID
1. Left nav → **APIs & Services** → **Credentials**
2. **+ Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: `Inbox Sweep Desktop`
5. **Create** → a dialog shows your client ID + secret. Click **Download JSON**.

### 5. Place the file
Save the downloaded file as **`credentials.json`** in the directory where you plan to run Inbox Sweep. Most users put it in the repo root:

```
inbox-sweep/
├── credentials.json    ← here
├── plugin/
└── ...
```

Or in a per-user workspace dir — wherever you `cd` before asking Claude to run the cleanup. The script resolves it from the CWD.

**Never commit this file.** It's in `.gitignore`.

### 6. First run triggers the browser auth flow
```bash
python plugin/scripts/gmail_cleanup.py --report-only
```
A browser opens → you sign into Gmail → approve the "read + modify" scope → done. A `token.json` appears next to `credentials.json` caching your refresh token; subsequent runs are silent.

If the browser shows a "Google hasn't verified this app" warning: click **Advanced** → **Go to Inbox Sweep (unsafe)**. This is expected — *you* are the app owner, and the warning is meant for strangers running someone else's restricted-scope app.

## Scope declared by the script
`https://www.googleapis.com/auth/gmail.modify` — read messages + move to Trash. **Not** `gmail.readonly` (can't delete) and **not** full `gmail` (can't read passwords/security settings — we don't need them).

## Revoking access
Any time, go to https://myaccount.google.com/permissions → find Inbox Sweep → Remove access. Kills the refresh token; next run requires a new browser flow.

## Common setup errors
See `docs/troubleshooting.md`.
