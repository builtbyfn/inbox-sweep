---
name: FN-gmail-cleanup
description: Safely drain a Gmail backlog. Use when the user asks to clean their Gmail, empty their inbox, delete old emails, drain a backlog, or tackle years of unread. Walks the 3-phase dry-run → cluster-report → execute workflow with STARRED/IMPORTANT hard-fail, keeper-keyword auto-quarantine, custom-label protection, and whitelist-filtered trash (30-day recovery, never permanent).
---

# Inbox Sweep — Gmail backlog drain

## When to trigger this skill
The user says something like:
- "clean my gmail"
- "drain my inbox"
- "delete old emails"
- "I have 50K/100K/140K emails to clear"
- "help me tackle my email backlog"
- "set up weekly gmail cleanup"

## Prerequisites (verify before Phase A)
1. **Python ≥ 3.9** installed and on PATH.
2. **`credentials.json`** — user's Google OAuth 2.0 Desktop client credentials in the CWD or in the plugin dir. If missing, walk them through `docs/setup-google-oauth.md` first (one-time, ~10 min).
3. **Dependencies**: `pip install -r $(dirname this plugin)/requirements.txt` (or the bundled `requirements.txt` path).

## The 3-phase workflow — NEVER skip a phase

### Phase A — Dry run (fast, metadata only)
```bash
python <plugin>/scripts/gmail_cleanup.py --dry-run --category <name> --before-date <YYYY/MM/DD>
```
Produces `reports/cleanup-<timestamp>-dry-run.md` with counts + sampled top senders. Use this to size the job and pick a cutoff.

### Phase B — Cluster report (deep, mandatory before execute)
```bash
python <plugin>/scripts/gmail_cleanup.py --cluster-report --category <name> --before-date <YYYY/MM/DD>
```
Produces `reports/clusters-<timestamp>.md` with:
- **Safety gate** (top): STARRED / IMPORTANT overlap must be 0 or script aborts.
- **Keeper-keyword hits** (QUARANTINE): tax, receipt, warranty, 2FA, etc.
- **Custom-labeled candidates** (QUARANTINE): any user label like "Tax 2017".
- **Active threads** (QUARANTINE): ≥3 messages or ≥2 distinct senders.
- **Domain clusters** (top 30) — present to user to mark DELETE / KEEP / REVIEW.
- **Subject-pattern clusters** (top 30).

**STOP HERE.** Have the user review the report and edit `whitelist.yaml` in their CWD with any `KEEP` decisions. Do NOT proceed to Phase C without explicit user confirmation.

### Phase C — Execute (trash, whitelist-filtered)
```bash
python <plugin>/scripts/gmail_cleanup.py --category <name> --before-date <YYYY/MM/DD>
```
Moves to Trash (30-day recovery). Whitelist filter applies per-message before `batchModify`. Hard-blocks if no cluster-report is < 4 hours old. Interactive confirm on batches > 500.

### Phase D — Verify
```bash
python <plugin>/scripts/gmail_cleanup.py --report-only
```
Shows remaining inbox total + spot-check links to `in:trash` view.

## Safety rules (refuse to violate)
- **Never use `--permanent`** on the first pass or in any routine run. Only if user types `DELETE` to confirm an irreversible purge.
- **Never skip Phase B** when the delete count exceeds 100.
- **Never proceed past Phase B** if STARRED or IMPORTANT overlap is > 0 — treat as user data corruption risk, investigate the IDs.
- **Never parallelize** deletes — the script's 100-msg batches + 0.1s sleep are the rate limit.
- **Always recommend Trash over permanent** — 30-day recovery is the backup.

## Recommended first-run cutoffs
| Age | Flag | Notes |
|---|---|---|
| 7+ years old | `--before-date 2019/01/01` | Safest first sweep; minimal false-positive surface |
| 4+ years old | `--before-date 2022/01/01` | After first sweep proves clean |
| 2+ years old | `--cutoff-years 2` (default) | Steady-state weekly routine |

## Categories
`promotions`, `social`, `spam`, `newsletters`, `inbox`. Sweep safest-first: `spam` → `promotions` → `social` → `newsletters` → `inbox`.

## Output artifacts
All reports land in `./reports/` relative to the user's CWD (not the plugin dir). They're markdown, grep-friendly, and worth keeping for audit trail.

## Escalation
If the user hits a "STARRED overlap > 0" hard-fail, do NOT try to bypass it. Show them the offending message IDs, have them open each in Gmail, and decide per-message whether to un-star (allowing delete) or add to `whitelist.yaml` (keeping forever).
