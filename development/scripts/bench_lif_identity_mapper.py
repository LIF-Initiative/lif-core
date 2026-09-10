#!/usr/bin/env python
"""
Wall-clock bench for the Identity Mapper HTTP API (issue #13).

The figures in docs/design/components/identity-mapper.md came from an ad-hoc run that
was not committed, so they could not be reproduced when the batching changed. This is
that harness, committed so the next person can re-run it.

Requires a running Identity Mapper and its MariaDB:

    docker compose -f development/docker-compose.yml up -d lif-identity-mapper-db
    development/scripts/run_lif_identity_mapper_restapi.sh

Then:

    uv run development/scripts/bench_lif_identity_mapper.py
    uv run development/scripts/bench_lif_identity_mapper.py --base-url http://localhost:8006 --sizes 1,10,100,500

Prints a markdown table ready to paste into the design doc. Each size uses a fresh
org/person so runs do not contaminate each other.
"""

import argparse
import statistics
import time
import uuid
from typing import List

import httpx

ID_TYPE = "School-assigned number"


def _mappings(org: str, person: str, n: int) -> List[dict]:
    return [
        {
            "lif_organization_id": org,
            "lif_organization_person_id": person,
            "target_system_id": f"sys-{i}",
            "target_system_person_id_type": ID_TYPE,
            "target_system_person_id": f"ext-{i}",
        }
        for i in range(n)
    ]


def _timed(fn) -> tuple[float, object]:
    start = time.perf_counter()
    result = fn()
    return (time.perf_counter() - start) * 1000, result


def bench_size(client: httpx.Client, base_url: str, n: int, repeats: int) -> dict:
    """POST a batch of n, GET them back, then DELETE them one by one."""
    posts, gets, deletes = [], [], []
    for _ in range(repeats):
        org, person = f"bench-{uuid.uuid4()}", "person-1"
        url = f"{base_url}/organizations/{org}/persons/{person}/mappings"

        elapsed, response = _timed(lambda: client.post(url, json=_mappings(org, person, n)))
        response.raise_for_status()
        posts.append(elapsed)
        saved = response.json()

        elapsed, response = _timed(lambda: client.get(url))
        response.raise_for_status()
        gets.append(elapsed)

        def delete_all():
            for mapping in saved:
                client.delete(f"{url}/{mapping['mapping_id']}").raise_for_status()

        elapsed, _ = _timed(delete_all)
        deletes.append(elapsed)

    return {
        "n": n,
        "post": statistics.median(posts),
        "get": statistics.median(gets),
        "delete": statistics.median(deletes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8006")
    parser.add_argument("--sizes", default="1,10,100,500")
    parser.add_argument("--repeats", type=int, default=5, help="runs per size; the median is reported")
    args = parser.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    with httpx.Client(timeout=120.0) as client:
        # There is no /health route; a GET for an org that owns nothing is the cheapest
        # readiness probe that exercises the same stack the bench measures.
        client.get(f"{args.base_url}/organizations/bench-probe/persons/probe/mappings").raise_for_status()
        rows = [bench_size(client, args.base_url, n, args.repeats) for n in sizes]

    print(f"\nMedian of {args.repeats} runs, milliseconds:\n")
    print("| operation | n=" + " | n=".join(str(r["n"]) for r in rows) + " |")
    print("|---|" + "---|" * len(rows))
    for label, key in (("POST save", "post"), ("GET", "get"), ("DELETE (per-row)", "delete")):
        print(f"| {label} | " + " | ".join(f"{r[key]:.1f}" for r in rows) + " |")


if __name__ == "__main__":
    main()
