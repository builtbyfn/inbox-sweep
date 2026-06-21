# Inbox Sweep

**A safety-first Gmail backlog drainer — installed as a Claude Code plugin.**

Tens of thousands of old emails. Tax documents, receipts, warranties, recovery codes, and personal threads hiding in the noise. Blind "select all → delete" loses what matters. Inbox Sweep walks you through a 3-phase workflow — dry-run, cluster-report, whitelist-filtered execute — so you delete the junk and keep the signal.

---

## What makes it safe

| Gate | Behavior |
|---|---|
| **STARRED / IMPORTANT hard-fail** | If any delete candidate overlaps STARRED or IMPORTANT, the script aborts with the offending IDs. Zero exceptions. |
| **Custom-label quarantine** | Any message with a user-created label (e.g. `Tax 2017`, `Receipts`, `Family`) is auto-quarantined. |
| **Keeper-keyword auto-quarantine** | ~50 curated substrings (tax, receipt, 1099, W-2, contract, 2FA, warranty, prescription, offer letter, …) pull matching emails out of the delete set. |
| **Active-thread quarantine** | Conversations (≥3 messages or ≥2 distinct senders) are never deleted — those look like relationships, not blasts. |
| **whitelist.yaml** | Persistent KEEP list of senders + subject patterns that survives every run. |
| **4-hour freshness gate** | Execute refuses to run unless a cluster-report from the last 4 hours exists. |
| **Trash by default** | 30-day recovery window. `--permanent` requires typing `DELETE` manually. |

---

## Quickstart

### 1. Prereqs
- [Claude Code](https://docs.claude.com/en/docs/claude-code) installed
- Python ≥ 3.9 on PATH
- A Gmail account you want to clean

### 2. One-time Google OAuth setup (~10 min)
Follow `docs/setup-google-oauth.md`. TL;DR:
1. Create a Google Cloud project → enable Gmail API → create OAuth 2.0 Desktop client
2. Download `credentials.json`

Because **you** are the OAuth app owner, you skip Google's CASA verification entirely — your own account is always "internal."

### 3. Install the plugin
```bash
git clone https://github.com/builtbyfn/inbox-sweep.git
cd inbox-sweep
pip install -r plugin/requirements.txt
```
Then symlink the plugin into your Claude Code plugins directory:

**Windows (pwsh):**
```powershell
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\plugins\FN-gmail-cleanup" -Target "$PWD\plugin"
```

**macOS / Linux:**
```bash
ln -s "$PWD/plugin" ~/.claude/plugins/FN-gmail-cleanup
```

### 4. First run
In a new Claude Code session, say:

> "clean my gmail — start with spam, anything before 2019"

Claude walks the 3-phase workflow. Full walkthrough with screenshots: `docs/first-run.md`.

---

## The 3-phase workflow

```
┌──────────────┐    ┌────────────────────┐    ┌──────────────────────┐
│  Phase A     │ →  │  Phase B           │ →  │  Phase C             │
│  --dry-run   │    │  --cluster-report  │    │  (whitelist-filtered │
│  (fast count)│    │  (deep analysis)   │    │   trash)             │
└──────────────┘    └────────────────────┘    └──────────────────────┘
    minutes              minutes-to-hour             minutes
    no risk              no risk                     Trash (30d recovery)
```

Each phase writes a markdown report to `./reports/`. You grep, you read, you decide. The executor refuses to run without a fresh cluster-report + clean STARRED/IMPORTANT gate.

---

## Why a plugin, not a web app?

Gmail scopes (`gmail.modify`) are "restricted" — hosting a public app requires Google's CASA security assessment (4–6 weeks, $3K–15K). A Claude Code plugin sidesteps the entire gate: **you run it against your own Google Cloud project**, so your account is always first-party. No verification, no data leaves your machine, no trust required.

---

## Project structure

```
inbox-sweep/
├── plugin/              ← the Claude Code plugin (symlink this)
│   ├── plugin.json
│   ├── skills/FN-gmail-cleanup/SKILL.md
│   ├── scripts/gmail_cleanup.py
│   ├── templates/       ← whitelist.yaml, keeper_keywords.txt defaults
│   ├── hooks/           ← pre-cleanup-check.sh safety hook
│   └── CLAUDE.md        ← operating rules Claude Code reads
├── docs/                ← setup, first-run, safety model, troubleshooting
├── dogfood/             ← live proof: author's own 140K drain reports
└── website/             ← marketing site (deferred)
```

---

## Safety model deep-dive
See `docs/safety-model.md`.

## Troubleshooting
See `docs/troubleshooting.md`.

## License
MIT — see `LICENSE`.

## Author
Fahad Noor — [github.com/builtbyfn](https://github.com/builtbyfn)
