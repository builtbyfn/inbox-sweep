# Gmail Cleanup — Claude Code Project

Target: `fahad.mnoor97@gmail.com` · ~140K message backlog · drain in 4–6 sweeps

## Canonical plan
`~/.claude/plans/c-users-fahad-documents-gmail-cleanup-c-indexed-hippo.md` —
authoritative step-by-step for this project. Consult before any run.

## Thinking Protocol
Before any cleanup action, answer internally:
1. What's the actual scope — categories, date range, volume?
2. What's the failure mode if this runs without cluster-report first?
3. Are STARRED / IMPORTANT / SENT / DRAFTS protected?

Never execute without **both** a fresh dry-run AND a fresh cluster-report from today (< 4h old).

---

## Operating Rules

### Safety Guardrails — NEVER touch
- `STARRED` messages
- `IMPORTANT` messages
- `SENT`, `DRAFTS`
- Any message with a **user-created label** (auto-QUARANTINE via cluster-report)
- Any message matching a **keeper keyword** (financial/legal/recovery/travel/medical — see `keeper_keywords.txt`)
- Any message in an **active thread** (≥ 3 messages OR ≥ 2 distinct senders — auto-QUARANTINE)
- Any sender or subject pattern listed in `whitelist.yaml`

### Default Cleanup Targets
| Category | Query | Default cutoff |
|---|---|---|
| `promotions`  | `category:promotions`  | 1 year |
| `social`      | `category:social`      | 1 year |
| `spam`        | `in:spam`              | 30 days |
| `newsletters` | unsubscribe-pattern    | 6 months |
| `inbox`       | `in:inbox -is:starred` | 3 years |

**For the 2018-and-prior sweep, use `--before-date 2019/01/01`** (overrides cutoff-years).

### Execute escalation
- Batches > 500 → interactive `yes/no` confirmation
- `--permanent` → type `DELETE` to confirm (never used in routine runs)
- No cluster-report in last 4h → execute is hard-blocked (use `--skip-freshness-check` only for small pilots)
- STARRED/IMPORTANT overlap in cluster-report > 0 → hard-fail, investigate IDs

---

## Workflow (3-phase gate for every category)

### Phase A — Dry run (fast, metadata only)
```bash
python gmail_cleanup.py --dry-run --category spam --before-date 2019/01/01
```
Produces: `reports/cleanup-YYYY-MM-DD_HHMM-dry-run.md` with counts + sampled top senders.

### Phase B — Cluster report (deep, slow, mandatory before execute)
```bash
python gmail_cleanup.py --cluster-report --category spam --before-date 2019/01/01
```
Produces: `reports/clusters-YYYY-MM-DD_HHMM.md` with:
- **Safety gate** at top: STARRED / IMPORTANT overlap counts (must be 0)
- **Keeper-keyword hits** (QUARANTINE list) — tax, receipt, warranty, etc.
- **Custom-labeled candidates** (QUARANTINE) — any user label
- **Active threads** (QUARANTINE) — conversations, not blasts
- **Personal-sender hits** (QUARANTINE) — name@freemail pattern
- **Domain clusters** (top 30) — mark DELETE/KEEP/REVIEW in `whitelist.yaml`
- **Subject-pattern clusters** (top 30)

Review, then edit `whitelist.yaml` to persist KEEP decisions.

### Phase C — Execute (trash, whitelist-filtered)
```bash
python gmail_cleanup.py --category spam --before-date 2019/01/01
```
Moves to Trash (30-day recovery). Whitelist filter runs per-message before any `batchModify`.

### Phase D — Verify
```bash
python gmail_cleanup.py --report-only
```
Inbox total count.

---

## Script knobs

| Flag | Default | Notes |
|---|---|---|
| `--before-date YYYY/MM/DD` | (none) | Overrides `--cutoff-years` |
| `--cutoff-years N` | 2 | Legacy |
| `--category NAME` | (repeatable) | `promotions`, `social`, `spam`, `newsletters`, `inbox` |
| `--max-messages N` | 25000 | Per category per run |
| `--permanent` | off | IRREVERSIBLE — never in routine |
| `--skip-freshness-check` | off | Pilots only |
| `--dry-run` | — | Fast preview |
| `--cluster-report` | — | Deep pre-execute analysis |
| `--report-only` | — | Inbox stats only |

### Retry / rate limits
- Gmail API 429 / 503 → exponential backoff, 5 attempts (~2, 4, 8, 16, 32s)
- Batch size: 100 messages per `batchModify`
- 0.1s sleep between batches (~10 req/sec ceiling)

---

## Gmail MCP notes

The operations plugin's Gmail MCP (`mcp__plugin_operations_gmail__*`) can be authed for quick inbox inspection from Claude Code. The batch-mutation path uses this Python script (OAuth2 + `credentials.json`) because bulk `batchModify` is the fast way to drain 140K — the MCP may or may not expose it.

**Setup for standalone:**
1. Google Cloud Console → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID (Desktop App)
3. Download as `credentials.json` in this folder
4. First run opens browser; token cached in `token.json`

Both `credentials.json` and `token.json` are in `.gitignore`.

---

## Memory
Learnings + corrections → `.claude/memory/cleanup-log.md`
After each run: date, mode, categories, message count, status.

---

## Anti-Patterns (Never Do)
- Never `--permanent` on the first pass
- Never skip `--cluster-report` on runs > 100 messages
- Never delete without a fresh cluster-report (< 4h old)
- Never parallelize deletes faster than 10 req/sec
- Never ignore a STARRED/IMPORTANT overlap — always investigate first
