#!/usr/bin/env bash
#
# Run the Query Cache integration tests (#1200) against a real MongoDB.
#
# These are not run by CI -- see the "Why this is a script and not a CI job" note in the
# PR for #1200. This script exists so that "run them" is one command rather than a
# sequence someone has to reconstruct from the README.
#
# The Query Cache needs exactly two containers: mongodb-org1 and lif-query-cache-org1.
# It depends on neither MDR, GraphQL, nor any LLM, so this is a small fraction of the
# full advisor-demo stack.
#
# Usage:
#   scripts/run-query-cache-integration-tests.sh              # up, test, leave running
#   scripts/run-query-cache-integration-tests.sh --down       # ...then tear down
#   scripts/run-query-cache-integration-tests.sh -- -k save   # extra args go to pytest
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="$REPO_ROOT/deployments/advisor-demo-docker"
SERVICES=(mongodb-org1 lif-query-cache-org1)
QUERY_CACHE_URL="http://localhost:8001/"
TEARDOWN=false
PYTEST_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --down) TEARDOWN=true; shift ;;
    --) shift; PYTEST_ARGS=("$@"); break ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1 (use -- to pass arguments to pytest)" >&2; exit 2 ;;
  esac
done

command -v docker >/dev/null || { echo "docker is required but not on PATH" >&2; exit 1; }

# compose refuses to parse this file without the #1191 secrets, even for services that
# do not use them, so a missing .env is a hard stop rather than a confusing later error.
if [[ ! -f "$COMPOSE_DIR/.env" ]]; then
  echo "No $COMPOSE_DIR/.env found."
  echo "Create one with:  cp $COMPOSE_DIR/.env.example $COMPOSE_DIR/.env"
  exit 1
fi

echo "==> Starting ${SERVICES[*]}"
docker compose --project-directory "$COMPOSE_DIR" up -d "${SERVICES[@]}"

echo "==> Waiting for the Query Cache at $QUERY_CACHE_URL"
for _ in $(seq 1 60); do
  if curl -fsS -m 2 -o /dev/null "$QUERY_CACHE_URL" 2>/dev/null; then
    echo "    ready"
    break
  fi
  sleep 2
done
curl -fsS -m 5 -o /dev/null "$QUERY_CACHE_URL" || {
  echo "Query Cache never became ready. Logs:" >&2
  docker compose --project-directory "$COMPOSE_DIR" logs --tail 40 lif-query-cache-org1 >&2
  exit 1
}

# --org org1 on purpose: org2/org3 have their own Query Cache containers that this
# script does not start, and their tests would fail rather than skip without it.
echo "==> Running the Query Cache integration tests"
set +e
(cd "$REPO_ROOT/integration_tests" && uv run pytest test_02_query_cache.py --org org1 "${PYTEST_ARGS[@]}")
STATUS=$?
set -e

if [[ "$TEARDOWN" == true ]]; then
  echo "==> Tearing down"
  docker compose --project-directory "$COMPOSE_DIR" down
else
  echo "==> Left running. Tear down with:"
  echo "    docker compose --project-directory $COMPOSE_DIR down"
fi

exit $STATUS
