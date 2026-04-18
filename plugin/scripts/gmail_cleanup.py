#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gmail Cleanup Script — Claude Code Native

Modes:
    --dry-run          Fast preview (counts + sampled top senders, metadata only)
    --cluster-report   Deep analysis: keeper keywords, domain/subject/thread
                       clusters, STARRED/IMPORTANT hard-fail gate, custom-label
                       callout. REQUIRED before any execute against old backlogs.
    (no flag)          Execute trash — requires a fresh cluster-report from today

Cutoff:
    --before-date 2019/01/01   Exact Gmail date operator (preferred for backlogs)
    --cutoff-years 2           Fuzzy years-old (legacy)

Examples:
    python gmail_cleanup.py --cluster-report --category spam --before-date 2019/01/01
    python gmail_cleanup.py --category spam --before-date 2019/01/01
    python gmail_cleanup.py --report-only
"""

import argparse
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows so em-dashes, arrows, and checkmarks
# in reports/CLI output render correctly regardless of the terminal code page.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, Exception):
    pass

# ── Constants ────────────────────────────────────────────────────────────────

SAFE_LABELS = {"STARRED", "IMPORTANT", "SENT", "DRAFTS"}

# Gmail system labels. Anything outside this set (and not matching r"^Label_\d+$"
# auto-system) is a user-created label → keeper signal.
GMAIL_SYSTEM_LABELS = {
    "INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFTS",
    "TRASH", "SPAM", "CHAT",
    "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS",
    "CATEGORY_UPDATES", "CATEGORY_FORUMS",
}

CATEGORY_QUERIES = {
    "promotions":  "category:promotions",
    "social":      "category:social",
    "spam":        "in:spam",
    "newsletters": (
        "(unsubscribe OR newsletter OR \"email preferences\" OR \"manage preferences\" "
        "OR \"you are receiving this\" OR list-unsubscribe)"
    ),
    "inbox":       "in:inbox -is:starred -is:important",
}

CATEGORY_CUTOFFS_YEARS = {
    "promotions":  1,
    "social":      1,
    "spam":        0.08,
    "newsletters": 0.5,
    "inbox":       3,
}

# Path resolution strategy (Inbox Sweep plugin layout):
#   SCRIPT_DIR    = <plugin>/scripts/
#   PLUGIN_DIR    = <plugin>/
#   TEMPLATES_DIR = <plugin>/templates/  (ships defaults for whitelist + keeper keywords)
#   PROJECT_DIR   = CWD at invocation — where reports/ and .claude/memory/ land so the
#                   user's run artifacts stay in their own workspace, not the plugin dir.
# Config files resolve CWD-first (user copied/edited) → templates fallback (first-run default).
SCRIPT_DIR    = Path(__file__).resolve().parent
PLUGIN_DIR    = SCRIPT_DIR.parent
TEMPLATES_DIR = PLUGIN_DIR / "templates"
PROJECT_DIR   = Path.cwd()
REPORTS_DIR   = PROJECT_DIR / "reports"
MEMORY_FILE   = PROJECT_DIR / ".claude" / "memory" / "cleanup-log.md"

def _resolve_config(name: str) -> Path:
    """CWD-first, bundled-templates fallback. Lets users override per-workspace."""
    cwd_candidate = PROJECT_DIR / name
    if cwd_candidate.exists():
        return cwd_candidate
    return TEMPLATES_DIR / name

WHITELIST_FILE       = _resolve_config("whitelist.yaml")
KEEPER_KEYWORDS_FILE = _resolve_config("keeper_keywords.txt")

DRY_RUN_FRESHNESS_HOURS = 4

FREEMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "icloud.com", "outlook.com"}


# ── Retry decorator (Gmail 429/503) ──────────────────────────────────────────

def with_retry(fn):
    """Exponential backoff for Gmail API 429/503. 5 attempts: ~2,4,8,16,32s."""
    def wrapper(*args, **kwargs):
        try:
            from googleapiclient.errors import HttpError
        except ImportError:
            return fn(*args, **kwargs)

        for attempt in range(5):
            try:
                return fn(*args, **kwargs)
            except HttpError as e:
                status = getattr(e.resp, "status", None)
                if status in (429, 503) and attempt < 4:
                    wait = (2 ** (attempt + 1)) + random.random()
                    print(f"  ⏳ Rate-limited ({status}) — sleeping {wait:.1f}s "
                          f"(attempt {attempt + 1}/5)")
                    time.sleep(wait)
                    continue
                raise
        return fn(*args, **kwargs)
    return wrapper


# ── Gmail API Setup ──────────────────────────────────────────────────────────

def get_gmail_service():
    """OAuth2 via credentials.json → token.json."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError:
        print("Installing required packages...")
        os.system("pip install google-api-python-client google-auth-httplib2 "
                  "google-auth-oauthlib pyyaml -q")
        return get_gmail_service()

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]
    creds = None
    token_path = PROJECT_DIR / "token.json"
    creds_path = PROJECT_DIR / "credentials.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                print(f"ERROR: credentials.json not found at {creds_path}")
                print("")
                print("Setup (one-time, ~8 min):")
                print("  1. https://console.cloud.google.com → New Project 'inbox-sweep-<you>'")
                print("  2. APIs & Services → Library → enable 'Gmail API'")
                print("  3. OAuth consent screen → External → add your Gmail as Test User")
                print("  4. Credentials → Create Credentials → OAuth client ID")
                print("     → Application type: Desktop app")
                print("  5. Download JSON → rename to 'credentials.json' → drop here:")
                print(f"     {creds_path.parent}")
                print("")
                print("Full walkthrough: docs/setup-google-oauth.md")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ── Whitelist + Keeper keyword loaders ───────────────────────────────────────

def load_whitelist() -> dict:
    if not WHITELIST_FILE.exists():
        return {
            "keep_senders": [],
            "keep_subject_patterns": [],
            "keep_labels": list(SAFE_LABELS),
            "keep_threads_with_min_messages": 3,
        }
    try:
        import yaml
    except ImportError:
        os.system("pip install pyyaml -q")
        import yaml
    with open(WHITELIST_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "keep_senders": [s.lower() for s in data.get("keep_senders", [])],
        "keep_subject_patterns": data.get("keep_subject_patterns", []),
        "keep_labels": data.get("keep_labels", list(SAFE_LABELS)),
        "keep_threads_with_min_messages": data.get("keep_threads_with_min_messages", 3),
    }


def load_keeper_keywords() -> list:
    if not KEEPER_KEYWORDS_FILE.exists():
        return []
    return [
        l.strip().lower()
        for l in KEEPER_KEYWORDS_FILE.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    ]


# ── Query Helpers ────────────────────────────────────────────────────────────

def date_cutoff_query(years: float = None, before_date: str = None) -> str:
    if before_date:
        return f"before:{before_date}"
    cutoff = datetime.now() - timedelta(days=int(years * 365))
    return f"before:{cutoff.strftime('%Y/%m/%d')}"


def build_query(category: str, cutoff_years: float = None, before_date: str = None) -> str:
    base = CATEGORY_QUERIES.get(category, "")
    date_q = date_cutoff_query(years=cutoff_years, before_date=before_date)
    safe_exclusions = " ".join(f"-label:{lbl.lower()}" for lbl in SAFE_LABELS)
    return " ".join(p for p in [base, date_q, safe_exclusions] if p)


@with_retry
def _list_page(service, kwargs):
    return service.users().messages().list(**kwargs).execute()


def fetch_messages(service, query: str, max_results: int = 25000) -> list:
    messages, page_token = [], None
    while len(messages) < max_results:
        batch = min(500, max_results - len(messages))
        kwargs = {
            "userId": "me", "q": query, "maxResults": batch,
            "fields": "messages(id,threadId),nextPageToken",
        }
        if page_token:
            kwargs["pageToken"] = page_token
        result = _list_page(service, kwargs)
        chunk = result.get("messages", [])
        messages.extend(chunk)
        page_token = result.get("nextPageToken")
        if not page_token or not chunk:
            break
    return messages


@with_retry
def get_message_metadata(service, msg_id: str, include_snippet: bool = False) -> dict:
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="metadata",
        metadataHeaders=["From", "Subject", "Date"],
    ).execute()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": msg_id,
        "thread_id": msg.get("threadId", ""),
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "labels": msg.get("labelIds", []),
        "size_estimate": msg.get("sizeEstimate", 0),
        "snippet": msg.get("snippet", "") if include_snippet else "",
    }


@with_retry
def get_labels_map(service) -> dict:
    result = service.users().labels().list(userId="me").execute()
    return {l["id"]: l["name"] for l in result.get("labels", [])}


# ── Subject normalization (for clustering) ───────────────────────────────────

_DATE_RE   = re.compile(r"\b(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4})\b", re.I)
_NUM_RE    = re.compile(r"\b\d+\b")
_ID_RE     = re.compile(r"\b[A-Z0-9]{8,}\b")
_PREFIX_RE = re.compile(r"^((re|fwd|fw)\s*:\s*)+", re.I)


def normalize_subject(subject: str) -> str:
    s = _PREFIX_RE.sub("", subject or "")
    s = _DATE_RE.sub("DATE", s)
    s = _ID_RE.sub("ID", s)
    s = _NUM_RE.sub("#", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def subject_cluster_key(subject: str, n_words: int = 5) -> str:
    return " ".join(normalize_subject(subject).split()[:n_words]) or "(empty)"


def sender_domain(from_header: str) -> str:
    if "@" not in from_header:
        return from_header.strip().lower()
    dom = from_header.split("@")[-1].replace(">", "").strip().lower()
    return dom.split()[0] if dom else dom


def is_custom_label(label_id: str, labels_map: dict) -> bool:
    name = labels_map.get(label_id, label_id)
    if name in GMAIL_SYSTEM_LABELS:
        return False
    if re.match(r"^Label_\d+$", name):
        return False
    if name.startswith("CATEGORY_"):
        return False
    return True


# ── Dry Run (fast) ───────────────────────────────────────────────────────────

def dry_run(service, cutoff_years, before_date, categories, max_messages) -> dict:
    print(f"\n{'='*60}\n  DRY RUN\n  Cutoff: "
          f"{before_date or f'{cutoff_years}yr'} | "
          f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n{'='*60}\n")

    summary = {}
    for cat in categories:
        cat_cutoff = CATEGORY_CUTOFFS_YEARS.get(cat, cutoff_years or 2)
        effective = min(cutoff_years, cat_cutoff) if cutoff_years else cat_cutoff
        query = build_query(cat, cutoff_years=None if before_date else effective,
                            before_date=before_date)

        print(f"[{cat.upper()}] {query[:80]}{'...' if len(query) > 80 else ''}")
        messages = fetch_messages(service, query, max_results=max_messages)
        count = len(messages)

        sender_counts = defaultdict(int)
        sample_size = min(50, count)
        for i, m in enumerate(messages[:sample_size]):
            meta = get_message_metadata(service, m["id"])
            sender_counts[sender_domain(meta["from"])] += 1
            if i % 10 == 0:
                print(f"  Sampling {i+1}/{sample_size}...", end="\r")

        top_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        summary[cat] = {
            "count": count, "query": query,
            "cutoff": before_date or f"{effective}yr",
            "top_senders": top_senders,
        }
        print(f"  → {count:,} messages | top: {', '.join(d for d,_ in top_senders[:5])}\n")
    return summary


# ── Cluster Report (deep) ────────────────────────────────────────────────────

def cluster_report(service, cutoff_years, before_date, categories, max_messages) -> dict:
    print(f"\n{'='*60}\n  CLUSTER REPORT\n  Cutoff: "
          f"{before_date or f'{cutoff_years}yr'} | "
          f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n{'='*60}\n")

    labels_map = get_labels_map(service)
    keeper_keywords = load_keeper_keywords()
    whitelist = load_whitelist()
    per_cat = {}

    for cat in categories:
        cat_cutoff = CATEGORY_CUTOFFS_YEARS.get(cat, cutoff_years or 2)
        effective = min(cutoff_years, cat_cutoff) if cutoff_years else cat_cutoff
        query = build_query(cat, cutoff_years=None if before_date else effective,
                            before_date=before_date)

        print(f"[{cat.upper()}] fetching candidates ({query[:80]}...)")
        candidates = fetch_messages(service, query, max_results=max_messages)
        total = len(candidates)
        print(f"  → {total:,} candidates. Deep-analyzing (this takes a minute)...")

        domain_counts   = defaultdict(int)
        domain_samples  = {}
        subject_counts  = defaultdict(int)
        subject_samples = {}
        thread_msg_counts = defaultdict(int)
        thread_senders    = defaultdict(set)
        starred_overlap, important_overlap = [], []
        custom_label_hits = defaultdict(list)
        keeper_hits = []
        personal_sender_hits = []

        for i, msg in enumerate(candidates):
            if i % 50 == 0:
                print(f"  Analyzing {i:,}/{total:,}...", end="\r")
            meta = get_message_metadata(service, msg["id"], include_snippet=True)

            if "STARRED" in meta["labels"]:
                starred_overlap.append(meta)
            if "IMPORTANT" in meta["labels"]:
                important_overlap.append(meta)

            for lbl_id in meta["labels"]:
                if is_custom_label(lbl_id, labels_map):
                    custom_label_hits[labels_map.get(lbl_id, lbl_id)].append(meta)

            blob = (meta["subject"] + " " + meta["snippet"]).lower()
            matched = [kw for kw in keeper_keywords if kw in blob]
            if matched:
                keeper_hits.append({**meta, "matched_keywords": matched})

            from_hdr = meta["from"]
            dom = sender_domain(from_hdr)
            name_part = from_hdr.split("<")[0].strip().strip('"')
            if dom in FREEMAIL_DOMAINS and name_part and " " in name_part and "@" not in name_part:
                personal_sender_hits.append(meta)

            domain_counts[dom] += 1
            if dom not in domain_samples:
                domain_samples[dom] = {"subject": meta["subject"], "first": meta["date"],
                                       "last": meta["date"]}
            else:
                domain_samples[dom]["last"] = meta["date"]

            key = subject_cluster_key(meta["subject"])
            subject_counts[key] += 1
            subject_samples.setdefault(key, meta["subject"])

            thread_msg_counts[meta["thread_id"]] += 1
            thread_senders[meta["thread_id"]].add(dom)

        # Baselines across the window (not just candidates)
        starred_base_q = f"label:starred {date_cutoff_query(years=cutoff_years, before_date=before_date)}"
        important_base_q = f"label:important {date_cutoff_query(years=cutoff_years, before_date=before_date)}"
        starred_baseline = len(fetch_messages(service, starred_base_q, max_results=1000))
        important_baseline = len(fetch_messages(service, important_base_q, max_results=1000))

        min_msgs = whitelist["keep_threads_with_min_messages"]
        active_threads = {tid: c for tid, c in thread_msg_counts.items()
                          if c >= min_msgs or len(thread_senders[tid]) >= 2}

        per_cat[cat] = {
            "query": query, "total": total,
            "starred_baseline": starred_baseline,
            "important_baseline": important_baseline,
            "starred_overlap": starred_overlap,
            "important_overlap": important_overlap,
            "custom_label_hits": dict(custom_label_hits),
            "keeper_hits": keeper_hits,
            "personal_sender_hits": personal_sender_hits,
            "domain_counts": dict(domain_counts),
            "domain_samples": domain_samples,
            "subject_counts": dict(subject_counts),
            "subject_samples": subject_samples,
            "active_threads": active_threads,
        }
        print(f"\n  ✓ {cat}: starred-overlap={len(starred_overlap)} "
              f"important-overlap={len(important_overlap)} "
              f"keepers={len(keeper_hits)} "
              f"custom-labels={sum(len(v) for v in custom_label_hits.values())}")

    return per_cat


def write_cluster_report(per_cat: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = REPORTS_DIR / f"clusters-{date_str}.md"

    total_starred = sum(len(c["starred_overlap"]) for c in per_cat.values())
    total_important = sum(len(c["important_overlap"]) for c in per_cat.values())
    total_keepers = sum(len(c["keeper_hits"]) for c in per_cat.values())
    total_custom = sum(sum(len(v) for v in c["custom_label_hits"].values())
                       for c in per_cat.values())

    lines = [
        f"# Cluster Report — {datetime.now().strftime('%B %d, %Y %H:%M')}",
        "",
        "## Safety Gate (top-of-report)",
        "",
        f"- Delete candidates overlapping **STARRED**: **{total_starred}** "
        f"{'✓' if total_starred == 0 else '🛑 HARD-FAIL — execute blocked'}",
        f"- Delete candidates overlapping **IMPORTANT**: **{total_important}** "
        f"{'✓' if total_important == 0 else '🛑 HARD-FAIL — execute blocked'}",
        f"- Keeper-keyword hits (auto-QUARANTINE): **{total_keepers}**",
        f"- Custom-labeled candidates (auto-QUARANTINE): **{total_custom}**",
        "",
    ]
    for cat, data in per_cat.items():
        lines.append(f"- {cat}: STARRED baseline {data['starred_baseline']:,} / "
                     f"IMPORTANT baseline {data['important_baseline']:,} in window")
    lines += ["", "---", ""]

    for cat, data in per_cat.items():
        lines += [f"## {cat.upper()} — {data['total']:,} candidates", "",
                  f"Query: `{data['query']}`", ""]

        lines += ["### Keeper-keyword hits (QUARANTINE — will NOT delete)", ""]
        if data["keeper_hits"]:
            lines += ["| Subject | From | Keywords |", "|---|---|---|"]
            for h in data["keeper_hits"][:50]:
                subj = (h["subject"] or "(no subject)")[:60].replace("|", "/")
                frm = h["from"][:40].replace("|", "/")
                lines.append(f"| {subj} | {frm} | {', '.join(h['matched_keywords'][:4])} |")
            if len(data["keeper_hits"]) > 50:
                lines.append(f"| … +{len(data['keeper_hits']) - 50} more | | |")
        else:
            lines.append("(none)")
        lines.append("")

        lines += ["### Custom-labeled candidates (QUARANTINE)", ""]
        if data["custom_label_hits"]:
            lines += ["| Label | Count | Sample subject |", "|---|---|---|"]
            for lbl, msgs in sorted(data["custom_label_hits"].items(), key=lambda x: -len(x[1])):
                subj = (msgs[0]["subject"] or "(no subject)")[:60].replace("|", "/")
                lines.append(f"| `{lbl}` | {len(msgs)} | {subj} |")
        else:
            lines.append("(none)")
        lines.append("")

        if data["starred_overlap"] or data["important_overlap"]:
            lines += ["### ⚠️ STARRED/IMPORTANT OVERLAP (HARD-FAIL — INVESTIGATE)", ""]
            for m in data["starred_overlap"][:20]:
                lines.append(f"- STARRED: `{m['id']}` | {m['from'][:40]} | "
                             f"{(m['subject'] or '')[:60]}")
            for m in data["important_overlap"][:20]:
                lines.append(f"- IMPORTANT: `{m['id']}` | {m['from'][:40]} | "
                             f"{(m['subject'] or '')[:60]}")
            lines.append("")

        lines += [f"### Active threads (QUARANTINE) — {len(data['active_threads']):,} threads", ""]
        if data["active_threads"]:
            lines += ["| Thread ID | Msg count |", "|---|---|"]
            for tid, c in sorted(data["active_threads"].items(), key=lambda x: -x[1])[:15]:
                lines.append(f"| `{tid}` | {c} |")
        else:
            lines.append("(none)")
        lines.append("")

        lines += [f"### Personal-sender hits (QUARANTINE) — "
                  f"{len(data['personal_sender_hits'])} messages", ""]
        if data["personal_sender_hits"]:
            for m in data["personal_sender_hits"][:15]:
                lines.append(f"- {m['from'][:50]} | {(m['subject'] or '')[:50]}")
        else:
            lines.append("(none)")
        lines.append("")

        lines += ["### Domain clusters (top 30) — mark DELETE / KEEP / REVIEW in whitelist.yaml",
                  "", "| Domain | Count | Sample subject |", "|---|---|---|"]
        for dom, count in sorted(data["domain_counts"].items(), key=lambda x: -x[1])[:30]:
            sample = (data["domain_samples"].get(dom, {}).get("subject", "")[:60]
                      ).replace("|", "/")
            lines.append(f"| `{dom}` | {count} | {sample} |")
        lines.append("")

        lines += ["### Subject-pattern clusters (top 30)", "",
                  "| Pattern | Count | Sample |", "|---|---|---|"]
        for key, count in sorted(data["subject_counts"].items(), key=lambda x: -x[1])[:30]:
            sample = (data["subject_samples"].get(key, "") or "")[:60].replace("|", "/")
            lines.append(f"| `{key[:50]}` | {count} | {sample} |")
        lines.append("")

    lines += [
        "---", "", "## Next Steps", "",
        "1. Review keeper-keyword + custom-labeled + active-thread clusters above.",
        "2. Edit `whitelist.yaml` — add `keep_senders` or `keep_subject_patterns`.",
        "3. If STARRED/IMPORTANT overlap > 0 — DO NOT EXECUTE. Investigate IDs.",
        "4. When clean → `python gmail_cleanup.py --category <name> --before-date <YYYY/MM/DD>`",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nCluster report → {path}")
    return path


# ── Report writer (fast dry-run) ─────────────────────────────────────────────

def write_report(summary: dict, dry_run_mode: bool = True) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    mode_str = "dry-run" if dry_run_mode else "completed"
    path = REPORTS_DIR / f"cleanup-{date_str}-{mode_str}.md"
    total = sum(v["count"] for v in summary.values())

    lines = [
        f"# Gmail Cleanup Report — {datetime.now().strftime('%B %d, %Y %H:%M')}",
        f"**Mode:** {'DRY RUN' if dry_run_mode else 'EXECUTED'}",
        f"**Total targeted:** {total:,}", "", "## Summary", "",
        "| Category | Messages | Cutoff | Top Sender |", "|---|---|---|---|",
    ]
    for cat, data in summary.items():
        top = data["top_senders"][0][0] if data["top_senders"] else "—"
        lines.append(f"| {cat.title()} | {data['count']:,} | {data['cutoff']} | {top} |")

    lines += ["", "## Top senders by category", ""]
    for cat, data in summary.items():
        lines.append(f"### {cat.title()}")
        for dom, c in (data["top_senders"] or [("—", 0)]):
            lines.append(f"- `{dom}` — {c} sampled")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report → {path}")
    return path


# ── Whitelist filter (pre-delete) ────────────────────────────────────────────

def apply_whitelist_filter(service, message_ids: list, whitelist: dict,
                           keeper_keywords: list, labels_map: dict) -> tuple:
    """Return (kept_ids, quarantined_meta)."""
    kept, quarantined = [], []
    thread_sizes = defaultdict(int)
    metas = {}

    print(f"  Applying whitelist filter on {len(message_ids):,} messages...")
    for i, mid in enumerate(message_ids):
        if i % 100 == 0:
            print(f"    Metadata {i}/{len(message_ids)}...", end="\r")
        try:
            meta = get_message_metadata(service, mid, include_snippet=True)
            metas[mid] = meta
            thread_sizes[meta["thread_id"]] += 1
        except Exception as e:
            print(f"\n    Skipping {mid}: {e}")
            kept.append(mid)

    for mid, meta in metas.items():
        reason = None
        if any(lbl in whitelist["keep_labels"] for lbl in meta["labels"]):
            reason = f"label:{next(l for l in meta['labels'] if l in whitelist['keep_labels'])}"
        elif any(is_custom_label(lbl, labels_map) for lbl in meta["labels"]):
            reason = "custom-label"
        else:
            blob = (meta["subject"] + " " + meta["snippet"]).lower()
            kw_hit = next((kw for kw in keeper_keywords if kw in blob), None)
            if kw_hit:
                reason = f"keeper:{kw_hit}"
            elif any(s in meta["from"].lower() for s in whitelist["keep_senders"]):
                reason = "sender-whitelist"
            elif any(re.search(pat, meta["subject"] or "", re.I)
                     for pat in whitelist["keep_subject_patterns"]):
                reason = "subject-whitelist"
            elif thread_sizes[meta["thread_id"]] >= whitelist["keep_threads_with_min_messages"]:
                reason = f"thread-size>={whitelist['keep_threads_with_min_messages']}"

        if reason:
            quarantined.append({**meta, "reason": reason})
        else:
            kept.append(mid)

    print(f"\n  → Kept: {len(kept):,} | Quarantined: {len(quarantined):,}")
    return kept, quarantined


# ── Deletion ─────────────────────────────────────────────────────────────────

@with_retry
def _batch_modify(service, body):
    return service.users().messages().batchModify(userId="me", body=body).execute()


@with_retry
def _batch_delete(service, body):
    return service.users().messages().batchDelete(userId="me", body=body).execute()


def trash_messages(service, message_ids: list, permanent: bool = False,
                   batch_size: int = 100) -> int:
    total = len(message_ids)
    if total == 0:
        print("  Nothing to delete (all filtered by whitelist).")
        return 0
    action = "Permanently deleting" if permanent else "Trashing"
    print(f"\n{action} {total:,} messages...")

    if total > 500 and not permanent:
        if input(f"\n⚠️  About to trash {total:,}. Continue? [yes/no]: ").strip().lower() != "yes":
            print("Aborted.")
            return 0
    elif permanent:
        if input(f"\n⚠️  PERMANENT DELETE of {total:,} — type 'DELETE': ").strip() != "DELETE":
            print("Aborted.")
            return 0

    done = 0
    for i in range(0, total, batch_size):
        chunk = message_ids[i:i + batch_size]
        if permanent:
            _batch_delete(service, {"ids": chunk})
        else:
            _batch_modify(service, {
                "ids": chunk,
                "addLabelIds": ["TRASH"],
                "removeLabelIds": ["INBOX", "UNREAD"],
            })
        done += len(chunk)
        print(f"  {done:,}/{total:,} ({done/total*100:.0f}%)", end="\r")
        time.sleep(0.1)
    print(f"\n  ✓ {done:,} processed")
    return done


# ── Memory Log ───────────────────────────────────────────────────────────────

def log_to_memory(summary: dict, executed: bool, permanent: bool, mode_label: str = None):
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    total = sum(v.get("count", v.get("total", 0)) for v in summary.values())
    mode = mode_label or ("PERMANENT" if permanent else "TRASH" if executed else "DRY RUN")
    entry = (
        f"\n## Run — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"- Mode: {mode}\n"
        f"- Categories: {', '.join(summary.keys())}\n"
        f"- Targeted: {total:,}\n"
        f"- Status: {'Executed' if executed else 'Preview'}\n"
    )
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


# ── Freshness gate ───────────────────────────────────────────────────────────

def check_freshness_gate(required_prefix: str) -> bool:
    if not REPORTS_DIR.exists():
        return False
    cutoff = datetime.now() - timedelta(hours=DRY_RUN_FRESHNESS_HOURS)
    for p in REPORTS_DIR.glob(f"{required_prefix}*.md"):
        if datetime.fromtimestamp(p.stat().st_mtime) > cutoff:
            return True
    return False


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Gmail Cleanup — Claude Code Native",
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="Fast preview")
    p.add_argument("--cluster-report", action="store_true",
                   help="Deep analysis required before execute")
    p.add_argument("--report-only", action="store_true", help="Inbox stats only")
    p.add_argument("--all", action="store_true", help="Run all categories")
    p.add_argument("--category", action="append", dest="categories",
                   choices=list(CATEGORY_QUERIES.keys()), help="Repeatable")
    p.add_argument("--before-date", type=str, default=None,
                   help="Gmail before: operator (YYYY/MM/DD)")
    p.add_argument("--cutoff-years", type=float, default=None,
                   help="Legacy years-old cutoff")
    p.add_argument("--permanent", action="store_true", help="IRREVERSIBLE")
    p.add_argument("--max-messages", type=int, default=25000,
                   help="Max per category per run (default 25000)")
    p.add_argument("--skip-freshness-check", action="store_true",
                   help="Bypass the cluster-report freshness gate")
    args = p.parse_args()

    if args.cutoff_years is None and args.before_date is None:
        args.cutoff_years = 2.0

    execute = bool(args.categories or args.all) and not args.dry_run and not args.cluster_report

    categories = (list(CATEGORY_QUERIES.keys()) if args.all
                  else (args.categories or list(CATEGORY_QUERIES.keys())))

    print("Connecting to Gmail...")
    service = get_gmail_service()
    print("Connected ✓\n")

    if args.report_only:
        result = service.users().labels().get(userId="me", id="INBOX").execute()
        print(f"Inbox — Total: {result.get('messagesTotal', '?'):,} | "
              f"Unread: {result.get('messagesUnread', '?'):,}")
        return

    if args.cluster_report:
        per_cat = cluster_report(service, args.cutoff_years, args.before_date,
                                 categories, args.max_messages)
        report_path = write_cluster_report(per_cat)
        log_to_memory({c: {"count": d["total"]} for c, d in per_cat.items()},
                      executed=False, permanent=False, mode_label="CLUSTER REPORT")

        overlap = sum(len(c["starred_overlap"]) + len(c["important_overlap"])
                      for c in per_cat.values())
        if overlap > 0:
            print(f"\n🛑 HARD-FAIL: {overlap} STARRED/IMPORTANT overlaps. Execute blocked.")
            sys.exit(2)
        print(f"\n✓ Clean. Review {report_path}, update whitelist.yaml, then execute.")
        return

    if args.dry_run or not execute:
        summary = dry_run(service, args.cutoff_years, args.before_date,
                          categories, args.max_messages)
        write_report(summary, dry_run_mode=True)
        log_to_memory(summary, executed=False, permanent=False)
        print("\n── DRY RUN COMPLETE ──")
        print("Next: `python gmail_cleanup.py --cluster-report --category <cat> "
              "--before-date <YYYY/MM/DD>` before any execute.")
        return

    # EXECUTE — freshness gate
    if not args.skip_freshness_check and not check_freshness_gate("clusters-"):
        print(f"🛑 No cluster-report from the last {DRY_RUN_FRESHNESS_HOURS}h. "
              "Run --cluster-report first (or --skip-freshness-check for small pilots).")
        sys.exit(3)

    summary = dry_run(service, args.cutoff_years, args.before_date,
                      categories, args.max_messages)
    write_report(summary, dry_run_mode=False)

    whitelist = load_whitelist()
    keeper_keywords = load_keeper_keywords()
    labels_map = get_labels_map(service)

    print(f"\n{'='*60}\n  EXECUTING — "
          f"{'PERMANENT DELETE' if args.permanent else 'TRASH'}\n{'='*60}")

    total_deleted = 0
    for cat, data in summary.items():
        if data["count"] == 0:
            continue
        print(f"\n[{cat.upper()}] — {data['count']:,} candidates")
        messages = fetch_messages(service, data["query"], max_results=args.max_messages)
        ids = [m["id"] for m in messages]

        kept, quarantined = apply_whitelist_filter(service, ids, whitelist,
                                                   keeper_keywords, labels_map)
        if quarantined:
            reasons = set(q["reason"].split(":")[0] for q in quarantined)
            print(f"  Quarantined {len(quarantined)} ({', '.join(sorted(reasons))})")

        n = trash_messages(service, kept, permanent=args.permanent)
        total_deleted += n

    log_to_memory(summary, executed=True, permanent=args.permanent)
    print(f"\n{'='*60}\n  COMPLETE — {total_deleted:,} messages "
          f"{'permanently deleted' if args.permanent else 'moved to Trash (30-day recovery)'}"
          f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
