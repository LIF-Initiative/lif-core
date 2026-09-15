#!/usr/bin/env python
"""
Wall-clock bench for the Identity Mapper HTTP API (issue #13, extended in #1219).

The figures in docs/design/components/identity-mapper.md came from an ad-hoc run that
was not committed, so they could not be reproduced when the batching changed. This is
that harness, committed so the next person can re-run it.

The original harness sweeps BATCH SIZE (n mappings per request); that was the #13/#1178
study. Issue #1219 adds the other half of the Performance requirement - the volume of
identity mapping records held in the table. `--seeds` grows the table to the listed
target row counts (cumulatively, spread across many orgs and persons) and re-times each
operation at a FIXED batch size to draw the table-size curve:

    uv run development/scripts/bench_lif_identity_mapper.py \
        --seeds 0,10000,100000,1000000 --batch 100 --seed-batch 500 --repeats 5

Seeding is cumulative and there is no reset endpoint, so re-runs must start from a
known table: recreate the db container (or truncate identity_mappings) between runs.

Requires a running Identity Mapper and its MariaDB:

    docker compose -f development/docker-compose.yml up -d lif-identity-mapper-db
    development/scripts/run_lif_identity_mapper_restapi.sh

Then:

    uv run development/scripts/bench_lif_identity_mapper.py
    uv run development/scripts/bench_lif_identity_mapper.py --base-url http://localhost:8006 --sizes 1,10,100,500

Prints two markdown tables ready to paste into the design doc: the batch-size sweep
(fresh org/person per size, so runs do not contaminate each other) and the table-size
sweep (batch size held constant, seeding tracked and reported so it can be re-run).
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


class SeedState:
    """Rows inserted by this run so far, and the next person index to fill."""

    def __init__(self) -> None:
        self.inserted = 0
        self.person = 0


def seed_to(
    client: httpx.Client, base_url: str, target: int, batch: int, org_count: int, state: SeedState
) -> tuple[int, float]:
    """
    POST mapping batches until the table holds at least `target` rows.

    Each batch fills a fresh (org, person) pair, so the seeds spread across many orgs
    and people rather than piling up under one key (issue #1219). Returns the number of
    POST requests and the wall-clock seconds the extra rows took.
    """
    start = time.perf_counter()
    requests = 0
    while state.inserted < target:
        want = min(batch, target - state.inserted)
        org = f"seed-org-{state.person % org_count:05d}"
        person = f"seed-person-{state.person:07d}"
        url = f"{base_url}/organizations/{org}/persons/{person}/mappings"
        response = client.post(url, json=_mappings(org, person, want))
        response.raise_for_status()
        state.inserted += len(response.json())
        state.person += 1
        requests += 1
    elapsed = time.perf_counter() - start
    return requests, elapsed


def bench_table(
    client: httpx.Client,
    base_url: str,
    targets: List[int],
    batch: int,
    seed_batch: int,
    org_count: int,
    repeats: int,
    state: SeedState,
) -> List[dict]:
    """
    Time each operation at a fixed batch size across growing table sizes.

    Targets are cumulative: the table is extended to each target in turn and benched,
    never reset, so a sweep is one monotonic run. A target at or below the current
    count is benched as-is.
    """
    rows = []
    for target in targets:
        if target > state.inserted:
            requests, elapsed = seed_to(client, base_url, target, seed_batch, org_count, state)
            print(f"seeded to {state.inserted:,} rows ({requests} POSTs, {elapsed:.0f}s)", flush=True)
        row = bench_size(client, base_url, batch, repeats)
        row["rows"] = state.inserted
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8006")
    parser.add_argument("--sizes", default="1,10,100,500")
    parser.add_argument("--repeats", type=int, default=5, help="runs per size; the median is reported")
    parser.add_argument(
        "--seeds",
        default="",
        help="comma-separated cumulative table-size targets for the #1219 sweep, e.g. '0,10000,100000,1000000'",
    )
    parser.add_argument("--batch", type=int, default=100, help="fixed batch size for the table-size sweep")
    parser.add_argument("--seed-batch", type=int, default=500, help="rows POSTed per request while seeding")
    parser.add_argument("--org-count", type=int, default=10, help="distinct org ids the seed rows are spread across")
    args = parser.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    with httpx.Client(timeout=300.0) as client:
        # There is no /health route; a GET for an org that owns nothing is the cheapest
        # readiness probe that exercises the same stack the bench measures.
        client.get(f"{args.base_url}/organizations/bench-probe/persons/probe/mappings").raise_for_status()
        rows = [bench_size(client, args.base_url, n, args.repeats) for n in sizes]
        sweep = None
        if seeds:
            sweep = bench_table(
                client, args.base_url, seeds, args.batch, args.seed_batch, args.org_count, args.repeats, SeedState()
            )

    print(f"\nMedian of {args.repeats} runs, milliseconds:\n")
    print("| operation | n=" + " | n=".join(str(r["n"]) for r in rows) + " |")
    print("|---|" + "---|" * len(rows))
    for label, key in (("POST save", "post"), ("GET", "get"), ("DELETE (per-row)", "delete")):
        print(f"| {label} | " + " | ".join(f"{r[key]:.1f}" for r in rows) + " |")

    if sweep:
        print(f"\nMedian of {args.repeats} runs, batch n={args.batch} fixed, milliseconds:\n")
        print("| operation | rows=" + " | rows=".join(f"{r['rows']:,}" for r in sweep) + " |")
        print("|---|" + "---|" * len(sweep))
        for label, key in (("POST save", "post"), ("GET", "get"), ("DELETE (per-row)", "delete")):
            print(f"| {label} | " + " | ".join(f"{r[key]:.1f}" for r in sweep) + " |")


if __name__ == "__main__":
    main()
