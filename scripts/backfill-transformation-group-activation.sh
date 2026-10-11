#!/usr/bin/env bash
set -euo pipefail
#
# backfill-transformation-group-activation.sh — One-time backfill of
# TransformationsGroup.ActivationDate for issue #1350.
#
# Since #1350, a transformation group with no ActivationDate is not active,
# so the groups that predate it (almost all of them) would stop being served
# to the Translator. Run this once per environment, after the MDR with #1350
# is deployed and before the Translator switches to the active-set read.
#
# Pure ops tool. The caller is responsible for providing network
# connectivity to the target PostgreSQL instance (local docker-compose, VPN,
# SSH tunnel, etc.).
#
# Run with --help for full usage, options, env vars, and examples.
#

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN=true

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Backfills TransformationsGroup.ActivationDate in public and every tenant_*
schema (issue #1350). For each (source, target) data model pair, among the
non-deleted groups that have no ActivationDate and are not already
deprecated:
  - the highest version gets ActivationDate = now()
  - the older versions get DeprecationDate = now()

Versions compare numerically with trailing zeros dropped ("1.10" > "1.9",
"1" = "1.0"), the same order the MDR's active-set read uses. Groups that
already have an ActivationDate are never touched. These are reported and
left alone:
  - free-text versions (the active-set read ignores them)
  - pairs whose highest version is tied, e.g. "1" and "1.0" (choose one by
    hand with POST /transformation_groups/{id}/activate)

Idempotent: a second --apply changes 0 rows.

Options:
  --apply            Commit the changes (default is dry-run: the same updates
                     run in a transaction that is rolled back)
  --help, -h         Show this help

Environment:
  PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE — libpq connection params
  (POSTGRESQL_HOST, POSTGRESQL_PORT, POSTGRESQL_USER, POSTGRESQL_PASSWORD,
  POSTGRESQL_DB accepted as fallback to match the MDR API's env var naming)

Examples:
  # Preview: prints every change per schema, then rolls back
  PGHOST=localhost PGUSER=postgres PGPASSWORD=postgres PGDATABASE=LIF $0

  # Apply
  PGHOST=... $0 --apply
EOF
}

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1" >&2; }

main() {
    parse_args "$@"
    normalize_env
    check_dependencies

    log_info "Verifying PostgreSQL connection to ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
    psql -Atc 'SELECT 1' >/dev/null || {
        log_error "Unable to connect to PostgreSQL. Check PG* / POSTGRESQL_* env vars and network access."
        exit 1
    }
    log_success "Connected"

    local schemas
    schemas=$(psql -Atc "
        SELECT table_schema FROM information_schema.tables
        WHERE table_name = 'TransformationsGroup'
          AND (table_schema = 'public' OR table_schema LIKE 'tenant\_%')
        ORDER BY table_schema <> 'public', table_schema")
    if [[ -z "$schemas" ]]; then
        log_error "No schema in ${PGDATABASE} has a TransformationsGroup table"
        exit 1
    fi

    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN — the updates run and are rolled back (use --apply to commit)"
    else
        log_warn "Applying changes to ${PGDATABASE} on ${PGHOST}"
    fi
    echo ""

    local end_statement="ROLLBACK;"
    [[ "$DRY_RUN" == "true" ]] || end_statement="COMMIT;"

    {
        echo "BEGIN;"
        # Every change in the run carries this timestamp; it is what an undo matches on.
        echo "SELECT now() AS run_timestamp;"
        local schema
        for schema in $schemas; do
            echo "\\set schema '${schema}'"
            echo "\\echo === :schema"
            backfill_sql
        done
        echo "$end_statement"
    } | psql -v ON_ERROR_STOP=1 --quiet -X -P footer=on

    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Rolled back. Run with --apply to commit"
    else
        log_success "Committed"
    fi
}

# Runs once per schema; psql interpolates :"schema" as a quoted identifier
# and :'schema' as a literal. now() is the transaction's start time, so every
# row in a run gets the same timestamp.
backfill_sql() {
    cat <<'SQL'
WITH candidates AS (
    SELECT "Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion",
           string_to_array(regexp_replace("GroupVersion", '(\.0+)+$', ''), '.')::numeric[] AS version_key
    FROM :"schema"."TransformationsGroup"
    WHERE "Deleted" IS NOT TRUE
      AND "ActivationDate" IS NULL
      AND ("DeprecationDate" IS NULL OR "DeprecationDate" > now())
      AND "GroupVersion" ~ '^[0-9]+(\.[0-9]+)*$'
), ranked AS (
    SELECT *, max(version_key) OVER pair AS top_key
    FROM candidates
    WINDOW pair AS (PARTITION BY "SourceDataModelId", "TargetDataModelId")
), counted AS (
    SELECT *, count(*) FILTER (WHERE version_key = top_key)
                  OVER (PARTITION BY "SourceDataModelId", "TargetDataModelId") AS top_count
    FROM ranked
), skipped AS (
    SELECT "Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion",
           'skipped: highest version is tied' AS action
    FROM counted WHERE top_count > 1
    UNION ALL
    SELECT "Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion",
           'skipped: GroupVersion is not dotted integers'
    FROM :"schema"."TransformationsGroup"
    WHERE "Deleted" IS NOT TRUE
      AND "ActivationDate" IS NULL
      AND ("DeprecationDate" IS NULL OR "DeprecationDate" > now())
      AND ("GroupVersion" IS NULL OR "GroupVersion" !~ '^[0-9]+(\.[0-9]+)*$')
), updated AS (
    UPDATE :"schema"."TransformationsGroup" AS g
    SET "ActivationDate"  = CASE WHEN c.version_key = c.top_key THEN now() ELSE g."ActivationDate" END,
        "DeprecationDate" = CASE WHEN c.version_key < c.top_key THEN now() ELSE g."DeprecationDate" END
    FROM counted AS c
    WHERE g."Id" = c."Id" AND c.top_count = 1
    RETURNING g."Id", g."SourceDataModelId", g."TargetDataModelId", g."GroupVersion",
              CASE WHEN c.version_key = c.top_key THEN 'activated' ELSE 'deprecated' END AS action
)
SELECT :'schema' AS schema, "SourceDataModelId" AS source, "TargetDataModelId" AS target,
       "Id" AS group_id, "GroupVersion" AS version, action
FROM (SELECT * FROM updated UNION ALL SELECT * FROM skipped) AS changes
ORDER BY source, target, action, group_id;
SQL
}

# Accept POSTGRESQL_* env vars as a fallback (matches the MDR API's naming
# convention in docker-compose.yml). PG* takes precedence if both are set.
normalize_env() {
    : "${PGHOST:=${POSTGRESQL_HOST:-}}"
    : "${PGPORT:=${POSTGRESQL_PORT:-5432}}"
    : "${PGUSER:=${POSTGRESQL_USER:-}}"
    : "${PGPASSWORD:=${POSTGRESQL_PASSWORD:-}}"
    : "${PGDATABASE:=${POSTGRESQL_DB:-}}"
    export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE

    local missing=()
    [[ -z "$PGHOST" ]] && missing+=("PGHOST")
    [[ -z "$PGUSER" ]] && missing+=("PGUSER")
    [[ -z "$PGDATABASE" ]] && missing+=("PGDATABASE")
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required env vars: ${missing[*]}"
        log_error "Set PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE (or the POSTGRESQL_* equivalents)."
        exit 1
    fi
}

check_dependencies() {
    command -v psql >/dev/null || {
        log_error "Missing required tool: psql"
        log_error "Install the PostgreSQL client (matching the server major version)."
        exit 1
    }
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --apply)   DRY_RUN=false; shift ;;
            --help|-h) usage; exit 0 ;;
            *)
                log_error "Unknown argument: $1"
                usage
                exit 1
                ;;
        esac
    done
}

main "$@"
