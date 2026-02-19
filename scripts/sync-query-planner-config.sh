#!/usr/bin/env bash
set -euo pipefail
#
# Sync Query Planner Information Sources Config to SSM — run with --help for usage details.
#

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN=true
ENV_NAME=""
TARGET_ORG=""
ALL_ORGS=(org1 org2 org3)

# Resolve repo root from script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
    echo "Usage: $0 <env> [OPTIONS]"
    echo ""
    echo "Syncs query planner information_sources_config YAML files from the repo"
    echo "to SSM Parameter Store."
    echo ""
    echo "Source files:"
    echo "  deployments/advisor-demo-docker/volumes/lif_query_planner/{org}/information_sources_config_{org}.yml"
    echo ""
    echo "SSM parameters:"
    echo "  /{env}/{org}/LIFQueryPlannerInformationSourcesConfig"
    echo ""
    echo "Arguments:"
    echo "  <env>           Environment name (e.g., dev, demo)"
    echo ""
    echo "Options:"
    echo "  --apply         Write changes to SSM (default is dry-run)"
    echo "  --org <org>     Sync only this org (default: org1, org2, org3)"
    echo "  --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  AWS_PROFILE=lif $0 dev                     # Preview all orgs"
    echo "  AWS_PROFILE=lif $0 demo --apply             # Sync all orgs to demo"
    echo "  AWS_PROFILE=lif $0 demo --org org1 --apply  # Sync org1 only"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_diff() {
    echo -e "${YELLOW}[DIFF]${NC} $1"
}

log_missing() {
    echo -e "${YELLOW}[MISSING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --apply)
                DRY_RUN=false
                shift
                ;;
            --org)
                if [[ -z "${2:-}" ]]; then
                    log_error "--org requires a value (e.g., org1)"
                    exit 1
                fi
                TARGET_ORG="$2"
                shift 2
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            -*)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
            *)
                if [[ -z "$ENV_NAME" ]]; then
                    ENV_NAME="$1"
                else
                    log_error "Unexpected argument: $1"
                    usage
                    exit 1
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$ENV_NAME" ]]; then
        log_error "Environment name is required"
        echo ""
        usage
        exit 1
    fi
}

check_dependencies() {
    if ! command -v aws &> /dev/null; then
        log_error "Missing required tool: aws"
        exit 1
    fi
}

verify_aws_credentials() {
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured or expired"
        exit 1
    fi
}

# Get SSM parameter value. Returns 0 and prints value if exists, returns 1 if not found.
get_ssm_param() {
    local name=$1
    aws ssm get-parameter --name "$name" --query 'Parameter.Value' --output text 2>/dev/null
}

# Put SSM parameter value (String type, not SecureString — this is config, not a secret).
put_ssm_param() {
    local name=$1
    local value=$2

    if ! aws ssm put-parameter \
        --name "$name" \
        --value "$value" \
        --type String \
        --overwrite 1>/dev/null; then
        log_error "Failed to write parameter: $name"
        return 1
    fi
}

sync_org() {
    local org=$1
    local ssm_path="/${ENV_NAME}/${org}/LIFQueryPlannerInformationSourcesConfig"
    local local_file="${REPO_ROOT}/deployments/advisor-demo-docker/volumes/lif_query_planner/${org}/information_sources_config_${org}.yml"

    echo ""
    log_info "Checking ${org}: ${ssm_path}"

    # Verify local file exists
    if [[ ! -f "$local_file" ]]; then
        log_error "Local file not found: ${local_file}"
        return 1
    fi

    local local_value
    local_value="$(cat "$local_file")"

    # Try to read current SSM value
    local ssm_value
    if ssm_value=$(get_ssm_param "$ssm_path"); then
        # Compare trimmed values
        local local_trimmed ssm_trimmed
        local_trimmed="$(echo "$local_value" | sed -e 's/[[:space:]]*$//')"
        ssm_trimmed="$(echo "$ssm_value" | sed -e 's/[[:space:]]*$//')"

        if [[ "$local_trimmed" == "$ssm_trimmed" ]]; then
            log_ok "${ssm_path} is in sync"
            return 0
        else
            log_diff "${ssm_path} differs from local file"
            echo ""
            # Show diff (SSM current vs local/desired)
            diff --color=auto -u \
                <(echo "$ssm_value") \
                <(echo "$local_value") \
                --label "SSM (current)" \
                --label "Local (desired)" || true
            echo ""

            if [[ "$DRY_RUN" == "true" ]]; then
                log_warn "Use --apply to update SSM"
                return 2
            else
                put_ssm_param "$ssm_path" "$local_value"
                log_ok "Updated ${ssm_path}"
                return 3
            fi
        fi
    else
        log_missing "${ssm_path} does not exist in SSM"

        if [[ "$DRY_RUN" == "true" ]]; then
            log_warn "Use --apply to create it"
            return 4
        else
            put_ssm_param "$ssm_path" "$local_value"
            log_ok "Created ${ssm_path}"
            return 5
        fi
    fi
}

main() {
    parse_args "$@"
    check_dependencies

    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN for environment: ${ENV_NAME} (use --apply to write changes)"
    else
        log_info "Syncing query planner config for environment: ${ENV_NAME}"
        verify_aws_credentials
    fi

    # Determine which orgs to process
    local orgs=()
    if [[ -n "$TARGET_ORG" ]]; then
        orgs=("$TARGET_ORG")
    else
        orgs=("${ALL_ORGS[@]}")
    fi

    local count_sync=0
    local count_updated=0
    local count_created=0
    local count_diff=0
    local count_missing=0
    local count_error=0

    for org in "${orgs[@]}"; do
        local rc=0
        sync_org "$org" || rc=$?

        case $rc in
            0) ((++count_sync)) ;;
            1) ((++count_error)) ;;
            2) ((++count_diff)) ;;
            3) ((++count_updated)) ;;
            4) ((++count_missing)) ;;
            5) ((++count_created)) ;;
        esac
    done

    echo ""
    echo "─────────────────────────────────────────"
    log_info "Summary (${ENV_NAME}):"

    if [[ $count_sync -gt 0 ]]; then
        echo -e "  ${GREEN}In sync:${NC}  ${count_sync}"
    fi
    if [[ $count_updated -gt 0 ]]; then
        echo -e "  ${GREEN}Updated:${NC}  ${count_updated}"
    fi
    if [[ $count_created -gt 0 ]]; then
        echo -e "  ${GREEN}Created:${NC}  ${count_created}"
    fi
    if [[ $count_diff -gt 0 ]]; then
        echo -e "  ${YELLOW}Differ:${NC}   ${count_diff} (use --apply to update)"
    fi
    if [[ $count_missing -gt 0 ]]; then
        echo -e "  ${YELLOW}Missing:${NC}  ${count_missing} (use --apply to create)"
    fi
    if [[ $count_error -gt 0 ]]; then
        echo -e "  ${RED}Errors:${NC}   ${count_error}"
    fi

    if [[ "$DRY_RUN" == "true" && $((count_diff + count_missing)) -gt 0 ]]; then
        echo ""
        log_info "Run with --apply to write changes to SSM"
    fi

    if [[ "$DRY_RUN" == "false" && $((count_updated + count_created)) -gt 0 ]]; then
        echo ""
        log_info "Restart affected services to pick up changes:"
        for org in "${orgs[@]}"; do
            echo "  ./aws-deploy.sh -s ${ENV_NAME} --only-stack ${ENV_NAME}-lif-query-planner-${org}"
        done
    fi
}

main "$@"
