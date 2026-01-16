#!/usr/bin/env python3
"""
cf_env_check.py

Pairs dev-* and demo-* files and compares them to catch env mixups.
- Normal diff: diff -u demo-file dev-file
- Normalized diff: normalizes dev/demo tokens + normalizes ECR tags to :__TAG__
  so expected tag differences don't cause non-env diffs.
- Always prints non-env diffs to help troubleshoot.
- Only warns/fails on non-env diffs that match suspicious heuristics.
- Enforces docker tag policy:
    dev-* must use :latest
    demo-* must NOT use :latest
- Flags cross-env leftovers (e.g., 'dev' inside demo file) with line numbers,
  excluding allowlisted patterns.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

# -----------------------------
# Config
# -----------------------------

DEFAULT_ALLOWLIST = [
    re.compile(r"dkr\.ecr\.[^/]+/lif/dev/"),  # shared ECR repo path example
    re.compile(r"arn:aws:[^:]+:[^:]*:[^:]*:"),  # generic ARN noise
]

ECR_IMAGE_REF_RE = re.compile(
    r'([0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[A-Za-z0-9._\-/]+):([A-Za-z0-9._-]+)'
)

# Heuristic: only count a non-env diff as a "warning" if it hits any of these.
SUSPICIOUS_NONENV_PATTERNS = [
    re.compile(r"\.lif\.unicon\.net"),
    re.compile(r"\.demo\."),
    re.compile(r"\.dev\."),
    re.compile(r"s3://[^ \n]*/(dev|demo)[^ \n]*"),
    re.compile(r"/(dev|demo)/"),
    re.compile(r"arn:aws:iam::.*:oidc-provider/"),
    re.compile(r"AssumeRole"),
    re.compile(r"Principal"),
]

# -----------------------------
# Data types
# -----------------------------

@dataclass(frozen=True)
class Pair:
    key: str
    dev: Path
    demo: Path

@dataclass
class CheckResult:
    key: str
    dev: Path
    demo: Path
    env_only: bool
    has_nonenv_diff: bool
    suspicious_nonenv: bool
    normalized_diff_text: str
    full_diff_text: str
    docker_warnings: List[str]
    cross_env_warnings: List[str]

# -----------------------------
# Helpers
# -----------------------------

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def split_lines_keepends(s: str) -> List[str]:
    # difflib wants lists of lines *with* newline endings to preserve formatting
    return s.splitlines(keepends=True)

def canonicalize_env(s: str) -> str:
    """
    Normalize common dev/demo markers -> __ENV__ so only unexpected diffs remain.
    Also normalize ECR image tags to :__TAG__ (keep repo/path).
    Docker policy is checked separately.
    """
    s = re.sub(r"\bdev\b", "__ENV__", s)
    s = re.sub(r"\bdemo\b", "__ENV__", s)

    s = s.replace("/dev/", "/__ENV__/")
    s = s.replace("/demo/", "/__ENV__/")

    s = s.replace(".dev.", ".__ENV__.")
    s = s.replace(".demo.", ".__ENV__.")

    s = re.sub(r"\bdev-", "__ENV__-", s)
    s = re.sub(r"\bdemo-", "__ENV__-", s)

    # Normalize ECR tags: repo/path stays, tag becomes __TAG__
    s = ECR_IMAGE_REF_RE.sub(r"\1:__TAG__", s)
    return s

def unified_diff(a_text: str, b_text: str, a_name: str, b_name: str) -> str:
    a_lines = split_lines_keepends(a_text)
    b_lines = split_lines_keepends(b_text)
    diff_lines = difflib.unified_diff(
        a_lines,
        b_lines,
        fromfile=a_name,
        tofile=b_name,
        lineterm="",
        n=3,
    )
    # difflib.unified_diff already provides lines without trailing newline when lineterm=""
    return "\n".join(diff_lines)

def diff_changed_lines(diff_text: str) -> List[str]:
    """
    Return only changed lines from a unified diff:
    lines starting with + or -, excluding headers +++/---.
    """
    out: List[str] = []
    for line in diff_text.splitlines():
        if (line.startswith("+") or line.startswith("-")) and not (line.startswith("+++") or line.startswith("---")):
            out.append(line)
    return out

def is_suspicious_nonenv(diff_text: str) -> bool:
    changed = diff_changed_lines(diff_text)
    for line in changed:
        for pat in SUSPICIOUS_NONENV_PATTERNS:
            if pat.search(line):
                return True
    return False

def any_allowlisted(line: str, allowlist: Sequence[re.Pattern]) -> bool:
    return any(p.search(line) for p in allowlist)

def find_cross_env_leftovers(lines: Sequence[str], forbidden_token: str, allowlist: Sequence[re.Pattern]) -> List[Tuple[int, str]]:
    """
    Find occurrences of forbidden_token as a whole word in lines that are not allowlisted.
    Returns list of (lineno, line).
    """
    token_re = re.compile(rf"\b{re.escape(forbidden_token)}\b")
    hits: List[Tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        if token_re.search(line) and not any_allowlisted(line, allowlist):
            hits.append((i, line.rstrip("\n")))
    return hits

def extract_ecr_images(content: str) -> List[Tuple[str, str]]:
    """
    Return list of (image_repo, tag)
    """
    hits = []
    for m in ECR_IMAGE_REF_RE.finditer(content):
        hits.append((m.group(1), m.group(2)))
    return hits

def check_docker_policy(env: str, filename: str, content: str) -> List[str]:
    """
    env: 'dev' or 'demo'
    """
    warnings: List[str] = []
    for image, tag in extract_ecr_images(content):
        if env == "dev" and tag != "latest":
            warnings.append(f"{filename}: dev files should use :latest but found :{tag} ({image}:{tag})")
        if env == "demo" and tag == "latest":
            warnings.append(f"{filename}: demo files must NOT use :latest but found :latest ({image}:{tag})")
    return warnings

def list_env_files(directory: Path) -> List[Path]:
    out: List[Path] = []
    for p in directory.iterdir():
        if p.is_file():
            name = p.name
            if name.startswith("dev-") or name.startswith("demo-"):
                out.append(p)
    return out

def pair_files(paths: Sequence[Path]) -> Tuple[List[Pair], List[str]]:
    dev_map = {}
    demo_map = {}
    for p in paths:
        if p.name.startswith("dev-"):
            dev_map[p.name[len("dev-"):]] = p
        elif p.name.startswith("demo-"):
            demo_map[p.name[len("demo-"):]] = p

    keys = sorted(set(dev_map) | set(demo_map))
    pairs: List[Pair] = []
    orphans: List[str] = []

    for k in keys:
        d = dev_map.get(k)
        m = demo_map.get(k)
        if d and m:
            pairs.append(Pair(key=k, dev=d, demo=m))
        else:
            orphans.append(f"{k}  dev={str(d) if d else '<missing>'}  demo={str(m) if m else '<missing>'}")

    return pairs, orphans

def print_section(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

# -----------------------------
# Main check logic
# -----------------------------

def check_pair(pair: Pair, allowlist: Sequence[re.Pattern], show_full_diff: bool) -> CheckResult:
    dev_text = read_text(pair.dev)
    demo_text = read_text(pair.demo)

    # Full diff (demo vs dev) to match your usual reading order
    full = unified_diff(
        demo_text,
        dev_text,
        a_name=pair.demo.name,
        b_name=pair.dev.name,
    )

    # Normalized diff
    demo_norm = canonicalize_env(demo_text)
    dev_norm = canonicalize_env(dev_text)
    norm = unified_diff(
        demo_norm,
        dev_norm,
        a_name=pair.demo.name + ".norm",
        b_name=pair.dev.name + ".norm",
    )

    env_only = (full != "" and norm == "")
    has_nonenv = (norm != "")
    suspicious = is_suspicious_nonenv(norm) if has_nonenv else False

    # Docker policy warnings
    docker_warnings = []
    docker_warnings.extend(check_docker_policy("dev", pair.dev.name, dev_text))
    docker_warnings.extend(check_docker_policy("demo", pair.demo.name, demo_text))

    # Cross-env leftovers (word-boundary checks)
    dev_lines = dev_text.splitlines()
    demo_lines = demo_text.splitlines()
    cross_env_warnings: List[str] = []
    cross_in_demo = find_cross_env_leftovers(demo_lines, "dev", allowlist)
    cross_in_dev = find_cross_env_leftovers(dev_lines, "demo", allowlist)

    if cross_in_demo:
        cross_env_warnings.append(f"{pair.demo.name}: contains 'dev' outside allowlist")
    if cross_in_dev:
        cross_env_warnings.append(f"{pair.dev.name}: contains 'demo' outside allowlist")

    # Attach detailed cross hits as additional messages (printed by caller)
    # We'll store them in cross_env_warnings with a prefix; caller can re-scan if desired.
    for ln, line in cross_in_demo[:8]:
        cross_env_warnings.append(f"  {pair.demo.name}:{ln} | {line}")
    if len(cross_in_demo) > 8:
        cross_env_warnings.append(f"  ... ({len(cross_in_demo) - 8} more)")

    for ln, line in cross_in_dev[:8]:
        cross_env_warnings.append(f"  {pair.dev.name}:{ln} | {line}")
    if len(cross_in_dev) > 8:
        cross_env_warnings.append(f"  ... ({len(cross_in_dev) - 8} more)")

    return CheckResult(
        key=pair.key,
        dev=pair.dev,
        demo=pair.demo,
        env_only=env_only,
        has_nonenv_diff=has_nonenv,
        suspicious_nonenv=suspicious,
        normalized_diff_text=norm,
        full_diff_text=full if show_full_diff else "",
        docker_warnings=docker_warnings,
        cross_env_warnings=cross_env_warnings,
    )

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--dir", default=".", help="Directory to scan for dev-* and demo-* files")
    ap.add_argument("--no-diff", action="store_true", help="Do not print full diffs; still prints normalized diffs for non-env cases")
    ap.add_argument("--allow", action="append", default=[], help="Regex allowlist for cross-env leftovers (can repeat)")
    ap.add_argument("--show-env-only", action="store_true", help="Also print env-only full diffs (can be noisy)")

    args = ap.parse_args(argv)

    allowlist = list(DEFAULT_ALLOWLIST)
    for s in args.allow:
        allowlist.append(re.compile(s))

    directory = Path(args.dir).resolve()
    if not directory.exists() or not directory.is_dir():
        print(f"ERROR: --dir is not a directory: {directory}", file=sys.stderr)
        return 1

    paths = list_env_files(directory)
    if not paths:
        print(f"No dev-* or demo-* files found in: {directory}")
        return 0

    pairs, orphans = pair_files(paths)

    print_section(f"CloudFormation env-pair check ({directory})")

    warnings: List[str] = []

    if orphans:
        warnings.append("Orphans found (missing counterpart)")
        print("\nOrphans (missing counterpart):")
        for o in orphans:
            print(" -", o)

    for pair in pairs:
        res = check_pair(pair, allowlist=allowlist, show_full_diff=(not args.no_diff))

        print_section(f"Pair: {res.demo.name}  <->  {res.dev.name}")
        print(f"PAIR_KEY: {res.key}")

        if res.full_diff_text == "" and not args.no_diff:
            # Shouldn't happen, but just in case
            pass

        if res.full_diff_text == "" and args.no_diff:
            # no-diff mode: still print classification
            if res.has_nonenv_diff:
                label = "SUSPICIOUS" if res.suspicious_nonenv else "INFO"
                print(f"DIFF: NON-ENV (after normalization) [{label}]")
                print("\nFocused NON-ENV diff (normalized):")
                print(res.normalized_diff_text)
            elif res.env_only:
                print("DIFF: env-only (after normalization: no diffs)")
            elif res.full_diff_text == "" and not res.env_only:
                # full diff not shown; decide by re-checking quickly
                # If normalized is empty and not env_only, likely identical
                print("DIFF: none")
        else:
            # diff mode
            if res.has_nonenv_diff:
                label = "SUSPICIOUS" if res.suspicious_nonenv else "INFO"
                print(f"DIFF: NON-ENV (after normalization) [{label}]")
                print("\nNON-ENV DIFF (normalized) — start here:")
                print(res.normalized_diff_text)
                print("\nFull diff (original files) — context:")
                print(res.full_diff_text)
            else:
                # No non-env differences
                if res.full_diff_text.strip() == "":
                    print("DIFF: none")
                else:
                    print("DIFF: env-only (after normalization: no diffs)")
                    if args.show_env_only:
                        print("\nEnv-only full diff:")
                        print(res.full_diff_text)

        # Docker warnings always count
        for w in res.docker_warnings:
            warnings.append(w)
            print("DOCKER TAG WARNING:", w)

        # Cross-env warnings always count
        if res.cross_env_warnings:
            # First line(s) are the summary markers
            for w in res.cross_env_warnings:
                if w.strip():
                    # Count only the summary lines as warnings, not the per-line details
                    if ": contains" in w:
                        warnings.append(w)
                    print("CROSS-ENV:", w)

        # Non-env diffs: only count as warnings if suspicious (avoid rabbit holes)
        if res.has_nonenv_diff and res.suspicious_nonenv:
            warnings.append(f"{res.key}: suspicious non-env differences detected")

    print_section("Summary")
    if not warnings:
        print("No warnings found.")
        return 0

    print(f"Warnings found: {len(warnings)}")
    for w in warnings:
        print(" -", w)
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
