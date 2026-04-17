# Gmail Cleanup — Claude Code Autopilot Routine
# Paste into Claude Code → Routines (or claude.ai/code/routines)
# Recommended schedule: Weekly, Sunday 2 AM
# Compatible with claude-autopilot nightly-improvement-routine pattern

---

## Routine Prompt (paste exactly as-is)

```
Run the Gmail cleanup routine for fahad.mnoor97@gmail.com.

## Step 1 — Dry Run
Execute:
  python gmail_cleanup.py --dry-run --cutoff-years 2

Read the report generated in reports/. Do not proceed past this step without summarizing the report.

## Step 2 — Report Summary
Summarize the dry-run report in this format:
- Total messages targeted: N
- By category: [table]
- Top 5 bulk senders: [list]
- Any unexpected categories or counts that warrant review: [yes/no + detail]

If total > 10,000 messages: pause and surface the summary for human review before proceeding.
If total ≤ 10,000 messages: proceed to Step 3.

## Step 3 — Category Cleanup (sequential, safest-first order)
Execute each in order, waiting for completion before the next:
  python gmail_cleanup.py --category spam --cutoff-years 0.08
  python gmail_cleanup.py --category promotions --cutoff-years 1
  python gmail_cleanup.py --category social --cutoff-years 1
  python gmail_cleanup.py --category newsletters --cutoff-years 1

Do NOT run --all or --inbox in this routine without explicit human confirmation.

## Step 4 — Log
Confirm the memory log in .claude/memory/cleanup-log.md was updated.
Report total messages trashed this session.

## Guardrails (enforce always)
- Never use --permanent in routine runs
- Never touch STARRED, IMPORTANT, SENT, or DRAFTS
- If any single category exceeds 5,000 messages, pause and surface for review
- If Gmail API returns rate-limit errors, back off 60 seconds and retry once
```

---

## Setup Instructions

1. Open Claude Code → **Routines** (claude.ai/code/routines or in-app)
2. Click **New Routine**
3. Name: `Gmail Weekly Cleanup`
4. Schedule: `Weekly — Sunday 2:00 AM`
5. Paste the prompt block above (between the triple backticks)
6. Save

## Plan Limits Reference
- Pro: 5 plans/day
- Max: 15 plans/day
- Team/Enterprise: 25 plans/day

This routine counts as 1 plan per weekly run.

---

## Manual Triggers

For one-off deep cleanups (e.g., first-time run on years of backlog):

```bash
# Phase 1 — Preview everything
python gmail_cleanup.py --dry-run --cutoff-years 3

# Phase 2 — Clean oldest backlog first
python gmail_cleanup.py --category promotions --cutoff-years 3
python gmail_cleanup.py --category social --cutoff-years 3
python gmail_cleanup.py --category newsletters --cutoff-years 2

# Phase 3 — General inbox (most conservative, manual confirm required)
python gmail_cleanup.py --category inbox --cutoff-years 3
```
