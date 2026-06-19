#!/usr/bin/env python3
"""
import_transformation_group.py

POSTs a reversed transformation group JSON to the MDR API.

Steps:
  1. POST /transformation_groups/         → creates the group, returns its ID
  2. POST /transformation_groups/add_transformation/{id}  → bulk-adds transformations

Usage:
    python scripts/import_transformation_group.py \\
        --input  StateU_LIF_v1.0_Ed-Fi_v5.json \\
        --mdr-url http://localhost:8001

    # For demo/production:
    python scripts/import_transformation_group.py \\
        --input  StateU_LIF_v1.0_Ed-Fi_v5.json \\
        --mdr-url https://your-demo-mdr-url \\
        --batch-size 25 \\
        --dry-run       # Print what would be sent, don't actually POST

Pre-requisites:
    pip install httpx
"""

import argparse
import json
import sys
from copy import deepcopy


def import_group(
    mdr_url: str,
    data: dict,
    batch_size: int = 50,
    dry_run: bool = False,
) -> None:
    try:
        import httpx
    except ImportError:
        sys.exit("httpx is required: pip install httpx")

    data = deepcopy(data)
    transformations: list[dict] = data.pop("Transformations", [])

    # Sanity-check for NEEDS_REVIEW markers before sending
    flagged = [
        t.get("Name", "unknown")
        for t in transformations
        if "NEEDS_REVIEW" in (t.get("Expression") or "")
    ]
    if flagged:
        print(f"⚠️  {len(flagged)} transformation(s) still contain NEEDS_REVIEW expressions:")
        for name in flagged:
            print(f"   • {name}")
        answer = input("\nContinue anyway? [y/N] ").strip().lower()
        if answer != "y":
            sys.exit("Aborted. Fix the flagged expressions first.")

    base = mdr_url.rstrip("/")

    # -----------------------------------------------------------------------
    # Step 1: Create the transformation group
    # -----------------------------------------------------------------------
    group_payload = {k: v for k, v in data.items() if v is not None}

    print(f"\nPOST {base}/transformation_groups/")
    print(f"     SourceDataModelId = {data.get('SourceDataModelId')}")
    print(f"     TargetDataModelId = {data.get('TargetDataModelId')}")
    print(f"     GroupVersion      = {data.get('GroupVersion')}")

    if dry_run:
        print("[dry-run] Would create group with payload:")
        print(json.dumps(group_payload, indent=2))
        print(f"[dry-run] Would add {len(transformations)} transformation(s) in batches of {batch_size}.")
        return

    resp = httpx.post(f"{base}/transformation_groups/", json=group_payload, timeout=30)
    if resp.status_code not in (200, 201):
        sys.exit(f"Error creating group: {resp.status_code}\n{resp.text}")

    group = resp.json()
    group_id: int = group["Id"]
    print(f"✓  Created TransformationGroup  Id={group_id}\n")

    # -----------------------------------------------------------------------
    # Step 2: Add transformations in batches
    # -----------------------------------------------------------------------
    total = len(transformations)
    url = f"{base}/transformation_groups/add_transformation/{group_id}"

    for i in range(0, total, batch_size):
        batch = transformations[i : i + batch_size]
        end = min(i + len(batch), total)
        print(f"   POST {url}  [{i+1}–{end} of {total}]")

        resp = httpx.post(url, json=batch, timeout=60)
        if resp.status_code not in (200, 201):
            print(f"\n   ERROR on batch {i+1}–{end}: {resp.status_code}")
            print(f"   {resp.text[:500]}")
            print(
                "\n   The transformation group was created (Id={group_id}) but "
                "some transformations failed to import.\n"
                "   Fix the failing transformations and re-run with a narrowed batch."
            )
            sys.exit(1)

    print(f"\n✓  All {total} transformation(s) imported into group Id={group_id}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import a reversed transformation group JSON into the MDR API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input", required=True, help="Path to the reversed JSON file")
    parser.add_argument(
        "--mdr-url", default="http://localhost:8001",
        help="MDR API base URL (default: http://localhost:8001)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="Number of transformations per API call (default: 50)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be sent without making any API calls",
    )
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    import_group(
        mdr_url=args.mdr_url,
        data=data,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
