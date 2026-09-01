#!/usr/bin/env bash
# PostToolUse(Edit|Write) advisory: fast hygiene check on the file just edited.
#
# ADVISORY ONLY — always exits 0, never blocks an edit. The authoritative gate is
# pre-commit (ruff, cspell, ty, pytest) at commit time; this hook exists to surface
# the cheap problems immediately instead of at the end of a long session.
#
# For Python files it runs ruff check + ruff format --check on that single file
# (measured ~0.35s, fast enough per-edit). For every file it runs `git diff --check`
# to catch leftover conflict markers and whitespace errors.
#
# See agent-behavioral-guidelines.md § "Surgical changes".
set -uo pipefail

f=$(printf '%s' "$(cat)" | python3 -c "import json,sys
try: print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))
except Exception: pass" 2>/dev/null)

[ -z "$f" ] || [ ! -f "$f" ] && exit 0

repo=$(git -C "$(dirname "$f")" rev-parse --show-toplevel 2>/dev/null) || exit 0
rel=${f#"$repo"/}

findings=""

# Whitespace errors and merge-conflict markers (cheap, applies to any file type).
ws=$(git -C "$repo" diff --check -- "$rel" 2>/dev/null || true)
[ -n "$ws" ] && findings+="whitespace / conflict markers:
$ws
"

# Python: lint + format check on just this file.
case "$f" in
  *.py)
    lint=$(cd "$repo" && uv run ruff check --quiet "$rel" 2>/dev/null || true)
    [ -n "$lint" ] && findings+="ruff check:
$lint
"
    if ! (cd "$repo" && uv run ruff format --check --quiet "$rel" >/dev/null 2>&1); then
      findings+="ruff format: file is not formatted — run 'uv run ruff format $rel'
"
    fi
    ;;
esac

if [ -n "$findings" ]; then
  {
    echo "lint advisory — $rel"
    printf '%s' "$findings"
    echo "(advisory only; pre-commit is the authoritative gate)"
  } >&2
fi

exit 0
