#!/bin/bash
# Pre-cleanup safety hook
# Fires before any gmail_cleanup.py execution via Claude Code hooks

# Warn if --permanent flag detected in the command
if echo "$CLAUDE_TOOL_INPUT" | grep -q '"--permanent"'; then
    echo "⚠️  SAFETY HOOK: --permanent flag detected."
    echo "    This will PERMANENTLY DELETE emails with no recovery."
    echo "    Ensure you have reviewed the dry-run report first."
    echo "    Proceed only if the report confirms expected scope."
fi

# Warn if no dry-run report exists from today
TODAY=$(date +%Y-%m-%d)
REPORTS_DIR="$(dirname "$0")/../../reports"
if ! ls "$REPORTS_DIR"/cleanup-"$TODAY"*dry-run* 2>/dev/null | grep -q .; then
    echo "⚠️  SAFETY HOOK: No dry-run report found for today."
    echo "    Run with --dry-run first to preview scope."
fi
