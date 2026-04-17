# Gmail Cleanup — Claude Code Project

Drains old Gmail backlogs safely. Three-phase workflow (dry-run → cluster-report → execute) with keeper-keyword auto-quarantine, custom-label protection, active-thread preservation, and a STARRED/IMPORTANT hard-fail gate.

See `CLAUDE.md` for full operating rules and the plan file for the 140K-backlog drain sequence.

## Quick Start

```bash
# 0. Install deps (first time)
pip install -r requirements.txt

# 1. Authenticate (first time — opens browser)
python gmail_cleanup.py --report-only

# 2. Fast preview
python gmail_cleanup.py --dry-run --category spam --before-date 2019/01/01

# 3. Deep analysis (MANDATORY before execute — keeper + cluster + safety gate)
python gmail_cleanup.py --cluster-report --category spam --before-date 2019/01/01

# 4. Review reports/clusters-*.md, edit whitelist.yaml with any KEEP patterns

# 5. Execute (moves to Trash — 30-day recovery, whitelist-filtered)
python gmail_cleanup.py --category spam --before-date 2019/01/01
```

## File Structure

```
gmail-cleanup/
├── CLAUDE.md                    ← Project rules (read first)
├── gmail_cleanup.py             ← Main script
├── whitelist.yaml               ← Persistent KEEP rules (senders, subjects, labels, thread size)
├── keeper_keywords.txt          ← Auto-quarantine trigger list (financial/legal/recovery/etc.)
├── cleanup-routine.md           ← Paste into Routines (use AFTER backlog drained)
├── requirements.txt
├── credentials.json             ← OAuth (gitignored)
├── token.json                   ← Auto-generated after first auth (gitignored)
├── reports/                     ← cleanup-*.md and clusters-*.md
└── .claude/
    ├── hooks/
    │   └── pre-cleanup-check.sh ← Safety hook
    └── memory/
        └── cleanup-log.md       ← Run history
```

## Category Reference

| Category | Target | Default Cutoff |
|---|---|---|
| `promotions` | Gmail Promotions tab | 1 year |
| `social` | Gmail Social tab | 1 year |
| `spam` | Spam folder | 30 days |
| `newsletters` | Unsubscribe-pattern emails | 6 months |
| `inbox` | General inbox (unstarred) | 3 years |

## Safety

- Default **move to Trash** (30-day recovery); `--permanent` required for irreversible delete
- STARRED, IMPORTANT, SENT, DRAFTS protected by query + re-verified in cluster-report
- **Any user-created label** → auto-QUARANTINE
- **Keeper keywords** (tax, receipt, warranty, etc.) → auto-QUARANTINE
- **Active threads** (≥ 3 messages or ≥ 2 senders) → auto-QUARANTINE
- **whitelist.yaml senders/patterns** → permanent KEEP
- Cluster-report required before execute (< 4h freshness gate)
- STARRED/IMPORTANT overlap > 0 → hard-fail, execute blocked
- Batches > 500 → interactive confirmation
- 429 / 503 → exponential backoff retry (5 attempts)

## Running as Autopilot Routine

See `cleanup-routine.md` — paste the prompt into Claude Code Routines for weekly automated cleanup.
