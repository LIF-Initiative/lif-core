#!/usr/bin/env bash
# PreToolUse(Bash) guard: block blanket git staging (`git add -A`, `--all`, `.`).
#
# Why: blanket staging turns a scoped change into a wide diff, and this repo's
# working tree routinely carries untracked files that must never be committed —
# credential inventories, workshop key dumps, exported artifacts. One `git add -A`
# is all it takes. Stage explicit paths instead: `git add path/to/file`.
#
# See agent-behavioral-guidelines.md § "Surgical changes".
#
# Exit 2 blocks the tool call and feeds stderr back to the agent; exit 0 allows.
# Uses python3 (guaranteed in this repo's toolchain) rather than jq.
set -uo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | python3 -c "import json,sys
try: print(json.load(sys.stdin).get('tool_input',{}).get('command',''))
except Exception: pass" 2>/dev/null)

[ -z "$cmd" ] && exit 0

if printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])git[[:space:]]+(-[A-Za-z]+[[:space:]]+)*add[[:space:]]+([^;&|]*[[:space:]])?(-A|--all|\.)([[:space:]]|$)'; then
  echo "Blocked: avoid blanket staging (git add -A / git add . / --all). This repo's tree carries untracked credential and export files. Stage explicit paths: git add <path1> <path2> … — review 'git status' first." >&2
  exit 2
fi

exit 0
