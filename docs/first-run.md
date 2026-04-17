# First run — walk through a 2018-and-prior spam sweep

Assumes you've already completed `docs/setup-google-oauth.md` (credentials.json in place) and installed deps (`pip install -r plugin/requirements.txt`).

The safest first sweep is **spam, older than 7 years** — minimal false-positive surface. We'll do that end-to-end.

## Phase A — Dry run

```bash
python plugin/scripts/gmail_cleanup.py --dry-run --category spam --before-date 2019/01/01
```

Expected output: a summary table + a report file in `./reports/cleanup-<timestamp>-dry-run.md`. No messages are touched.

What to look for:
- **Total candidates**: a number (could be hundreds or thousands)
- **Top senders**: sanity-check — does this look like junk? If you see `notifications@yourbank.com`, stop and investigate.

## Phase B — Cluster report (mandatory before execute)

```bash
python plugin/scripts/gmail_cleanup.py --cluster-report --category spam --before-date 2019/01/01
```

This takes longer — the script pulls per-message metadata for clustering. Output: `reports/clusters-<timestamp>.md`.

Open the report. The **top of the file** is the safety gate:

```
## Safety Gate
Pre-2019 STARRED messages in mailbox: 3
Pre-2019 IMPORTANT messages in mailbox: 17
Delete candidates overlapping STARRED: 0 ✓
Delete candidates overlapping IMPORTANT: 0 ✓
```

If either overlap is > 0, the script will have already aborted with the offending message IDs printed. Stop, open each in Gmail, and decide: un-star (allow delete) or add the sender to `whitelist.yaml`.

Below the safety gate, sections you'll review:
1. **Keeper-keyword hits** — any email whose subject/snippet matched `receipt`, `tax`, `2FA`, etc. Already quarantined; skim to confirm no false quarantines.
2. **Custom-labeled candidates** — if you've ever applied a label, those messages are here. Quarantined by default.
3. **Active threads** — conversations with ≥3 messages. Quarantined.
4. **Domain clusters (top 30)** — the most frequent sender domains. This is your decision point:

```
| count | domain                    | sample subject                         |
|-------|---------------------------|----------------------------------------|
| 412   | notifications@linkedin.com| "New connection request"               |
| 287   | no-reply@groupon.com      | "50% off at restaurants near you"      |
| ...   | ...                       | ...                                    |
```

Mark your calls: DELETE / KEEP / REVIEW. Then edit `whitelist.yaml` in your CWD:

```yaml
keep_senders:
  - "notifications@mybank.com"     # add any KEEP domains from the cluster report
  - "hr@mycompany.com"
keep_subject_patterns:
  - "Your.*tax statement.*"         # regex — survives even if the sender changes
```

## Phase C — Execute

```bash
python plugin/scripts/gmail_cleanup.py --category spam --before-date 2019/01/01
```

Hard-blocks if:
- No cluster-report from the last 4 hours exists (safety freshness gate)
- Batch size > 500 without interactive `yes` confirmation

Otherwise: messages move to Trash in 100-msg batches with 0.1s between batches. Final count printed on exit.

## Phase D — Verify

```bash
python plugin/scripts/gmail_cleanup.py --report-only
```

Compare inbox total before/after. Then in Gmail web UI: search `in:trash before:2019/01/01` — should show the deleted set. 30-day recovery: re-label back to INBOX if you catch a mistake.

## Next sweeps

After spam proves clean, walk the other categories safest-first:

```bash
# promotions (newsletters/offers)
python plugin/scripts/gmail_cleanup.py --cluster-report --category promotions --before-date 2019/01/01
python plugin/scripts/gmail_cleanup.py --category promotions --before-date 2019/01/01

# social
python plugin/scripts/gmail_cleanup.py --cluster-report --category social --before-date 2019/01/01
python plugin/scripts/gmail_cleanup.py --category social --before-date 2019/01/01

# newsletters (unsubscribe-pattern)
python plugin/scripts/gmail_cleanup.py --cluster-report --category newsletters --before-date 2019/01/01
python plugin/scripts/gmail_cleanup.py --category newsletters --before-date 2019/01/01

# inbox last (highest false-positive risk — review carefully)
python plugin/scripts/gmail_cleanup.py --cluster-report --category inbox --before-date 2019/01/01
python plugin/scripts/gmail_cleanup.py --category inbox --before-date 2019/01/01
```

Edit `whitelist.yaml` between categories — a domain like `linkedin.com` might be DELETE for social but KEEP elsewhere.

After 2018-and-prior drains clean, repeat with a tighter cutoff (`2021/01/01`, `2023/01/01`) reusing the accumulated `whitelist.yaml`.
