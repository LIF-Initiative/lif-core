#!/usr/bin/env bash
set -euo pipefail
#
# provision-mdr-tenant.sh — Create a tenant_{name} PostgreSQL schema in the
# MDR database by cloning DDL (and optionally data) from a source schema.
#
# Phase 2 (issue #883) infrastructure for MDR self-serve. Pure ops tool —
# no runtime behavior changes. The caller is responsible for providing
# network connectivity to the target PostgreSQL instance (local
# docker-compose, VPN, SSH tunnel, etc.).
#
# Run with --help for full usage, options, env vars, and examples.
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN=true
CLONE_DATA=false
FORCE=false
TENANT_NAME=""
SOURCE_SCHEMA="public"

usage() {
    cat <<EOF
Usage: $0 <tenant-name> [OPTIONS]

Creates a tenant_{name} PostgreSQL schema by cloning DDL from the public
schema. Optionally copies data as well.

Arguments:
  <tenant-name>      Tenant identifier (lowercase, digits, underscores;
                     must start with a letter; max 55 chars so the full
                     "tenant_" prefix + name fits in PG's 63-char identifier limit)

Options:
  --apply            Execute (default is dry-run — prints planned actions only)
  --clone-data       Also copy all rows from the source schema into the new
                     schema (used for the one-time public → tenant_lif_team
                     migration). Default: DDL only.
  --source <name>    Source schema to clone from. Default: public
  --force            If the target schema already exists, DROP it first.
                     WARNING: destroys any existing tenant data.
  --help, -h         Show this help

Environment:
  PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE — libpq connection params
  (POSTGRESQL_HOST, POSTGRESQL_PORT, POSTGRESQL_USER, POSTGRESQL_PASSWORD,
  POSTGRESQL_DB accepted as fallback to match the MDR API's env var naming)

Examples:
  # Preview what would happen
  PGHOST=localhost PGUSER=postgres PGPASSWORD=postgres PGDATABASE=LIF \\
    $0 lif_team

  # One-time data migration: clone public into tenant_lif_team with all rows
  PGHOST=... $0 lif_team --clone-data --apply

  # Provision an empty tenant for a new self-serve user
  PGHOST=... $0 eval_jsmith --apply
EOF
}

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1" >&2; }

main() {
    parse_args "$@"
    validate_tenant_name "$TENANT_NAME"
    normalize_env
    check_dependencies

    local target_schema="tenant_${TENANT_NAME}"

    log_info "Verifying PostgreSQL connection to ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
    psql -Atc 'SELECT 1' >/dev/null || {
        log_error "Unable to connect to PostgreSQL. Check PG* / POSTGRESQL_* env vars and network access."
        exit 1
    }
    log_success "Connected"

    verify_source_schema "$SOURCE_SCHEMA"

    local target_exists
    target_exists=$(schema_exists "$target_schema")

    if [[ "$target_exists" == "1" && "$FORCE" != "true" ]]; then
        log_error "Schema ${target_schema} already exists. Use --force to drop and re-create."
        exit 1
    fi

    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN — no changes will be made (use --apply to execute)"
    else
        log_warn "Applying changes to ${PGDATABASE} on ${PGHOST}"
    fi

    echo ""
    echo -e "  ${BLUE}Source schema:${NC}   ${SOURCE_SCHEMA}"
    echo -e "  ${BLUE}Target schema:${NC}   ${target_schema}"
    echo -e "  ${BLUE}Clone data:${NC}      ${CLONE_DATA}"
    echo -e "  ${BLUE}Force (drop):${NC}    ${FORCE}"
    echo ""

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  Steps that would be performed:"
        [[ "$target_exists" == "1" && "$FORCE" == "true" ]] && \
            echo "    - DROP SCHEMA ${target_schema} CASCADE"
        echo "    - CREATE SCHEMA ${target_schema}"
        echo "    - Clone DDL from ${SOURCE_SCHEMA} (pg_dump --schema-only + rewrite)"
        [[ "$CLONE_DATA" == "true" ]] && \
            echo "    - Copy data from ${SOURCE_SCHEMA} (pg_dump --data-only + rewrite)"
        echo ""
        log_info "Run with --apply to execute"
        return 0
    fi

    if [[ "$target_exists" == "1" && "$FORCE" == "true" ]]; then
        log_warn "Dropping existing schema ${target_schema}"
        psql -v ON_ERROR_STOP=1 -c "DROP SCHEMA ${target_schema} CASCADE" >/dev/null
    fi

    log_info "Creating schema ${target_schema}"
    psql -v ON_ERROR_STOP=1 -c "CREATE SCHEMA ${target_schema}" >/dev/null

    log_info "Cloning DDL from ${SOURCE_SCHEMA} → ${target_schema}"
    clone_schema_ddl "$SOURCE_SCHEMA" "$target_schema"

    if [[ "$CLONE_DATA" == "true" ]]; then
        log_info "Cloning data from ${SOURCE_SCHEMA} → ${target_schema}"
        clone_schema_data "$SOURCE_SCHEMA" "$target_schema"
    fi

    echo ""
    log_success "Tenant schema ${target_schema} provisioned"
}

# Pipe pg_dump's DDL output through the rewriter into psql. The rewrite
# rules live with rewrite_schema_ddl below.
clone_schema_ddl() {
    local source=$1
    local target=$2

    pg_dump \
        --schema-only \
        --schema="${source}" \
        --no-owner \
        --no-privileges \
        --no-comments \
        | rewrite_schema_ddl "$source" "$target" \
        | psql -v ON_ERROR_STOP=1 --quiet >/dev/null
}

clone_schema_data() {
    local source=$1
    local target=$2

    pg_dump \
        --data-only \
        --schema="${source}" \
        --no-owner \
        --no-privileges \
        --disable-triggers \
        | rewrite_schema_data "$source" "$target" \
        | psql -v ON_ERROR_STOP=1 --quiet --single-transaction >/dev/null
}

# Rewrite a pg_dump DDL stream so fully-qualified references to $source become
# $target, and schema-management statements (CREATE SCHEMA, search_path) are
# stripped — we manage those ourselves and the fully-qualified rewrites route
# every statement to the target schema.
#
# Schema names are matched with a word boundary to avoid false positives in
# column values, string literals, or identifiers that happen to contain the
# schema name as a substring.
rewrite_schema_ddl() {
    local source=$1
    local target=$2

    sed -E \
        -e "/^CREATE SCHEMA (IF NOT EXISTS )?${source};?$/d" \
        -e "/^SELECT pg_catalog\.set_config\('search_path'/d" \
        -e "/^SET search_path = /d" \
        -e "s/(^|[^A-Za-z0-9_\"])${source}\./\1${target}./g"
}

# Rewrite a pg_dump data stream. Unlike the DDL rewriter, this is restricted
# to specific statement-header lines so that raw COPY data rows — which are
# tab-delimited user data and may legitimately contain the string "public."
# as a value — pass through untouched.
#
# pg_dump's default data-section output contains: SET directives, ALTER TABLE
# ... DISABLE/ENABLE TRIGGER (with --disable-triggers), COPY headers with
# tab-delimited data rows terminated by \\., and setval() calls. We rewrite
# the schema prefix only on those statement-header lines. INSERT statements
# are intentionally not rewritten — pg_dump doesn't emit them by default, and
# rewriting a full INSERT line would corrupt string-literal values.
rewrite_schema_data() {
    local source=$1
    local target=$2

    sed -E \
        -e "/^SELECT pg_catalog\.set_config\('search_path'/d" \
        -e "/^SET search_path = /d" \
        -e "/^COPY /s/(^|[^A-Za-z0-9_\"])${source}\./\1${target}./g" \
        -e "/^SELECT pg_catalog\.setval/s/(^|[^A-Za-z0-9_\"])${source}\./\1${target}./g" \
        -e "/^ALTER TABLE /s/(^|[^A-Za-z0-9_\"])${source}\./\1${target}./g"
}

# Returns "1" if the schema exists, empty string otherwise.
schema_exists() {
    local schema=$1
    psql -Atc "SELECT 1 FROM information_schema.schemata WHERE schema_name = '${schema}'"
}

verify_source_schema() {
    local schema=$1
    if [[ "$(schema_exists "$schema")" != "1" ]]; then
        log_error "Source schema '${schema}' does not exist in ${PGDATABASE}"
        exit 1
    fi
}

validate_tenant_name() {
    local name=$1
    if [[ ! "$name" =~ ^[a-z][a-z0-9_]{0,54}$ ]]; then
        log_error "Invalid tenant name: '${name}'"
        log_error "Must start with a lowercase letter, contain only [a-z0-9_],"
        log_error "and be ≤55 chars (so tenant_{name} fits PG's 63-char limit)."
        exit 1
    fi
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
    local missing=()
    command -v psql    >/dev/null || missing+=("psql")
    command -v pg_dump >/dev/null || missing+=("pg_dump")
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing[*]}"
        log_error "Install the PostgreSQL client (matching the server major version)."
        exit 1
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --apply)       DRY_RUN=false;    shift ;;
            --clone-data)  CLONE_DATA=true;  shift ;;
            --force)       FORCE=true;       shift ;;
            --source)      SOURCE_SCHEMA="$2"; shift 2 ;;
            --help|-h)     usage; exit 0 ;;
            -*)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
            *)
                if [[ -z "$TENANT_NAME" ]]; then
                    TENANT_NAME="$1"
                else
                    log_error "Unexpected argument: $1"
                    usage
                    exit 1
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$TENANT_NAME" ]]; then
        log_error "Tenant name is required"
        echo ""
        usage
        exit 1
    fi
}

main "$@"
