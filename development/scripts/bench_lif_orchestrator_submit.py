#!/usr/bin/env python
"""
Wall-clock bench for Orchestrator API job submission (issue #572).

#572 reported an `httpx.ReadTimeout` on the Query Planner's `POST /jobs` to the
Orchestrator during the R1 demo. That timeout was httpx's silent 5s default, replaced by
#571/#1172 with `LIF_SERVICE_REQUEST_TIMEOUT_SECONDS`. Nobody had measured how long the
submission actually takes, so the replacement was a doubling of a number that failed
rather than a number read off a distribution. This is that measurement.

What is timed is the Query Planner's view: wall clock around `POST /jobs`, covering

    OrchestratorService.submit_job -> DagsterClient.post_job -> submit_job_execution
    -> dagster-webserver GraphQL -> code-location gRPC -> postgres run write

Submission returns once the run is queued, so `dagster-daemon` is not required and is
deliberately left out of the stack; it only dequeues and launches.

The distribution is **bimodal**, which is the point of the exercise: most submissions land
around a few hundred ms, and an intermittent minority cost several seconds. Report the
percentiles *and* `--slow-threshold`'s share; a mean would hide the mode that actually
caused #572.

Minimum stack (from deployments/advisor-demo-docker):

    docker compose up -d --no-deps postgres-dagster dagster-code-location \
        dagster-webserver lif-orchestrator-api-org1

`--no-deps` matters: `lif-orchestrator-api-org1` declares `depends_on:
lif-query-planner-org1`, which would otherwise drag in most of the compose file.

Then:

    uv run development/scripts/bench_lif_orchestrator_submit.py
    uv run development/scripts/bench_lif_orchestrator_submit.py --samples 20 --gap 10

`--gap` spaces submissions out to imitate the sporadic traffic the Query Planner actually
sends, as opposed to the back-to-back default.

Every submission enqueues a real Dagster run that nothing dequeues (no daemon), so runs
accumulate in the postgres run storage over a sweep. Recreate `postgres-dagster` between
runs if that matters to what is being compared.

Prints a markdown table ready to paste into docs/design/components/lif-orchestrator.md.
"""

import argparse
import math
import statistics
import time
from typing import List

import httpx

PERSON_ID_TYPE = "School-assigned number"


def _plan(parts: int) -> dict:
    """A query plan shaped like the one in #572's report: N lif-to-lif parts."""
    return {
        "lif_query_plan": [
            {
                "information_source_id": f"org{i + 2}",
                "adapter_id": "lif-to-lif",
                "person_id": {"identifier": "100001", "identifierType": PERSON_ID_TYPE},
                "lif_fragment_paths": ["person.name"],
                "translation": None,
            }
            for i in range(parts)
        ],
        "async": True,
    }


def _percentile(values: List[float], pct: float) -> float:
    """Nearest-rank percentile. Honest at small N, where interpolation invents precision."""
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def sample(client: httpx.Client, base_url: str, payload: dict, n: int, gap: float) -> List[float]:
    """Submit n jobs, returning elapsed milliseconds for each."""
    samples = []
    for i in range(n):
        start = time.perf_counter()
        response = client.post(f"{base_url}/jobs", json=payload)
        samples.append((time.perf_counter() - start) * 1000)
        response.raise_for_status()
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{n}", flush=True)
        if gap and i + 1 < n:
            time.sleep(gap)
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8005")
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--gap", type=float, default=0.0, help="seconds between submissions; 0 is back-to-back")
    parser.add_argument("--parts", type=int, default=3, help="query plan parts; 3 matches the #572 report")
    parser.add_argument("--slow-threshold", type=float, default=1000.0, help="ms above which a sample counts as slow")
    args = parser.parse_args()

    with httpx.Client(timeout=300.0) as client:
        client.get(f"{args.base_url}/health").raise_for_status()
        samples = sample(client, args.base_url, _plan(args.parts), args.samples, args.gap)

    slow = [s for s in samples if s >= args.slow_threshold]
    slow_p50 = f"{statistics.median(slow):.0f}" if slow else "-"
    print(f"\nPOST /jobs, {args.parts}-part plan, {args.gap}s gap, milliseconds:\n")
    print("| N | min | p50 | p95 | p99 | max | slow share | slow p50 |")
    print("|---|---|---|---|---|---|---|---|")
    print(
        f"| {len(samples)} | {min(samples):.0f} | {statistics.median(samples):.0f} | "
        f"{_percentile(samples, 95):.0f} | {_percentile(samples, 99):.0f} | {max(samples):.0f} | "
        f"{len(slow) / len(samples):.0%} | {slow_p50} |"
    )
    print(f"\n(slow = >= {args.slow_threshold:.0f} ms)")


if __name__ == "__main__":
    main()
