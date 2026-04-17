# Safety model

Inbox Sweep's design assumption: **a backlog always hides non-junk**. Tax docs from 2015. A warranty email you'll need in 2027. A password-reset link for an account you forgot you had. The safety model is defense-in-depth against ever deleting those.

## Layers

### 1. Query-level exclusion
Every Gmail query the script generates includes `-label:starred -label:important`. STARRED and IMPORTANT messages never enter the candidate set at the query layer.

### 2. Defense-in-depth label re-verification
During the cluster-report phase, the script re-fetches every candidate's `labelIds` and cross-checks against STARRED / IMPORTANT. If even one candidate slipped through the query (Gmail has had indexing lag bugs), the script aborts with the offending message IDs printed. No execute.

### 3. Keeper-keyword auto-quarantine
Defined in `templates/keeper_keywords.txt` — ~50 curated substrings across 6 categories:
- **Financial:** receipt, invoice, refund, tax, 1099, W-2, W2, statement, transaction, wire transfer, chargeback
- **Legal:** contract, agreement, legal, NDA, subpoena, settlement, court
- **Account recovery:** recovery code, 2FA, backup code, verify your identity, password reset, security alert, unusual sign-in, new device signed in
- **Travel / warranty / orders:** confirmation, booking, itinerary, reservation, warranty, serial number, tracking number, order confirmed, order shipped
- **Medical / insurance:** policy, claim, prescription, diagnosis, insurance, copay, deductible, lab results
- **Employment / school:** offer letter, W-4, W4, transcript, diploma, certification, paystub

Any candidate whose Subject OR snippet contains one of these substrings (case-insensitive) lands in the QUARANTINE list and is excluded from the delete set. Users can edit `keeper_keywords.txt` — it's a plain text file, one keyword per line.

### 4. Custom-label quarantine
Gmail users apply labels like "Tax 2017", "Receipts", "Family" as a keeper signal. The script enumerates all non-system labels (via Gmail API `users.labels.list`, excluding `GMAIL_SYSTEM_LABELS`) and auto-quarantines any candidate carrying any of them. Called out in the report as `## Custom-labeled candidates` with `label | count | sample subject`.

### 5. Active-thread quarantine
Any `threadId` with **≥ 3 messages** OR **≥ 2 distinct `From` addresses** is treated as a conversation (not a blast) and quarantined. Conversations look like relationships; the script doesn't touch them.

### 6. whitelist.yaml — persistent KEEP
The user's explicit KEEP list. Cumulative across runs. Structure:
```yaml
keep_senders:
  - "notifications@mybank.com"
keep_subject_patterns:
  - "Your.*tax statement.*"        # Python regex
keep_labels: [STARRED, IMPORTANT, SENT, DRAFTS]
keep_threads_with_min_messages: 3
keeper_keywords_file: "keeper_keywords.txt"
```
Applied **per-message** right before `batchModify`. A sender marked KEEP stays protected on every future run.

### 7. Freshness gate
Execute refuses to run unless a cluster-report file from the last 4 hours exists. Prevents "I ran cluster-report 3 weeks ago, let me just delete" mistakes. Override: `--skip-freshness-check` (for small pilots only, documented in CLAUDE.md).

### 8. Batch-size interactive confirm
Candidate set > 500 → script prompts `yes/no` before the first `batchModify`. Prevents accidentally running execute on the wrong category.

### 9. Trash-by-default
`batchModify` moves messages to Trash (30-day recovery). `--permanent` requires typing `DELETE` manually on stdin.

### 10. Rate-limit safety
- Batch size: 100 messages per `batchModify`
- 0.1s sleep between batches (~10 req/sec ceiling)
- 429/503 → exponential backoff, 5 attempts (~2, 4, 8, 16, 32s)

## What the safety model does NOT protect against
- **User explicitly whitelists wrong sender → doesn't delete junk.** Fine, recoverable — just fix `whitelist.yaml` and re-run.
- **User edits `keeper_keywords.txt` too narrowly** → a real keeper gets deleted. 30-day Trash recovery mitigates.
- **Gmail API bug returns wrong message IDs.** Defense-in-depth re-fetch catches mislabeled; for truly corrupt responses, the 30-day Trash is the backstop.
- **User runs `--permanent` and types `DELETE`.** No recovery. This is why it's off by default.

## Threat model (what an attacker can / cannot do)
Inbox Sweep runs locally with your OAuth token. It has `gmail.modify` scope — read + move to trash. It cannot:
- Read your Google password
- Change your 2FA settings
- Send email as you
- Access Drive / Calendar / Photos

If the script or any of its dependencies is compromised, an attacker could at worst: read your Gmail, move messages to Trash. They cannot permanently delete (that's a separate scope) or impersonate you.
