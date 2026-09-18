#!/usr/bin/env python3
"""Report migrations in the repo that have not reached an environment's database (#1226).

Two drifts hide a migration, and each is invisible to the check for the other:

1. **It never ran.** Flyway only runs when a new image tag is deployed to the
   `mdr-database` SAM stack, which no service workflow does. A merged `V*.sql` sits
   unapplied until someone runs the procedure by hand -- six weeks, for V1.6.
2. **It ran, but not where queries land.** Migrations are `ALTER TABLE public."..."`
   while tenant schemas are point-in-time clones that never receive them.
   `flyway_schema_history` reports Success and the column is still missing from every
   schema the application serves (#1265).

Checking only (1) is what let this hide: on 2026-09-17 both environments reported
version 1.6 / Success while all 19 tenant schemas lacked the column it added.

Reads `GET /admin/schema-state` on the target MDR, which is service-principal only,
so this needs a service API key. MDR is the only component with database
credentials, which is why the check goes through it rather than connecting directly.

Usage:
    MDR_URL=https://mdr-api.dev.lif.unicon.net MDR_API_KEY=... \\
        python3 scripts/check-migration-drift.py

    --json     machine-readable output
    --quiet    only print on drift
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS = REPO / "sam" / "mdr-database" / "flyway" / "flyway-files" / "flyway" / "sql" / "mdr"
VERSION_RE = re.compile(r"^V(\d+(?:\.\d+)*)__")


def repo_versions() -> list[str]:
    """Migration versions present in the repo, ascending."""
    versions = []
    for path in MIGRATIONS.glob("V*.sql"):
        match = VERSION_RE.match(path.name)
        if match:
            versions.append(match.group(1))
    return sorted(versions, key=lambda v: [int(p) for p in v.split(".")])


def fetch_state(base_url: str, api_key: str) -> dict:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/admin/schema-state", headers={"X-API-Key": api_key})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - caller-supplied https URL
        return json.loads(response.read())


def main() -> int:
    base_url = os.environ.get("MDR_URL")
    api_key = os.environ.get("MDR_API_KEY")
    if not base_url or not api_key:
        print("check-migration-drift: set MDR_URL and MDR_API_KEY", file=sys.stderr)
        return 2

    try:
        state = fetch_state(base_url, api_key)
    except urllib.error.HTTPError as exc:
        print(f"check-migration-drift: {base_url} returned {exc.code} {exc.reason}", file=sys.stderr)
        return 2
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"check-migration-drift: cannot reach {base_url}: {exc}", file=sys.stderr)
        return 2

    in_repo = repo_versions()
    applied_ok = {m["version"] for m in state["applied_migrations"] if m["success"]}
    unapplied = [v for v in in_repo if v not in applied_ok]
    drifted = [s for s in state["schemas"] if s["missing"]]

    if "--json" in sys.argv:
        print(json.dumps({"repo_versions": in_repo, "unapplied": unapplied, "drifted_schemas": drifted}, indent=2))
        return 1 if (unapplied or drifted) else 0

    failed = False

    if unapplied:
        failed = True
        print(f"  UNAPPLIED MIGRATIONS ({len(unapplied)}): {', '.join(unapplied)}")
        print("    These exist in the repo and are not recorded as applied. Merging does not")
        print("    apply a migration -- see docs/operations/guides/applying-mdr-migrations.md.")
    elif "--quiet" not in sys.argv:
        print(f"  all {len(in_repo)} repo migrations recorded applied (latest {state['latest_version']})")

    if drifted:
        failed = True
        print(f"\n  SCHEMAS BEHIND public ({len(drifted)} of {len(state['schemas'])}):")
        for entry in drifted:
            missing = ", ".join(entry["missing"][:6])
            more = f" (+{len(entry['missing']) - 6} more)" if len(entry["missing"]) > 6 else ""
            print(f"    {entry['schema_name']}: {missing}{more}")
        print("\n    Migrations are written against public, but these schemas are clones that")
        print("    never receive later ones. Flyway reporting Success does not cover them (#1265).")
    elif "--quiet" not in sys.argv:
        print(f"  all {len(state['schemas'])} non-public schemas match public")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
