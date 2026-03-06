#!/usr/bin/env bash
set -euo pipefail
#
# Setup MDR API Keys
# Generates and stores MDR service API keys in AWS SSM Parameter Store.
# Each key is shared between the MDR API (server) and the client service(s) that use it.
#
# Usage:
#   ./scripts/setup-mdr-api-keys.sh <env>             # Dry-run (preview)
#   ./scripts/setup-mdr-api-keys.sh <env> --apply      # Generate and store keys
#   ./scripts/setup-mdr-api-keys.sh --help              # Show help
#

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN=true
ENV_NAME=""
FORCE=false

usage() {
    echo "Usage: $0 <env> [OPTIONS]"
    echo ""
    echo "Generates MDR service API keys and stores them in SSM Parameter Store."
    echo "Keys are shared between the MDR API and each client service."
    echo ""
    echo "Arguments:"
    echo "  <env>         Environment name (e.g., dev, demo)"
    echo ""
    echo "Options:"
    echo "  --apply       Generate and store keys (default is dry-run)"
    echo "  --force       Overwrite existing keys (default is skip existing)"
    echo "  --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 dev                     # Preview what would be created for dev"
    echo "  $0 demo --apply            # Generate and store keys for demo"
    echo "  $0 dev --apply --force     # Regenerate all keys for dev"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

generate_key() {
    openssl rand -hex 32
}

# Check if an SSM parameter exists and return its value
# Returns 0 and prints value if exists, returns 1 if not found
get_param() {
    local name=$1
    aws ssm get-parameter --name "$name" --with-decryption --query 'Parameter.Value' --output text 2>/dev/null
}

put_param() {
    local name=$1
    local value=$2

    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "    ${YELLOW}Would create:${NC} $name"
        return 0
    fi

    if ! aws ssm put-parameter \
        --name "$name" \
        --value "$value" \
        --type SecureString \
        --overwrite 1>/dev/null; then
        log_error "Failed to create parameter: $name"
        return 1
    fi
    echo -e "    ${GREEN}Created:${NC} $name"
}

# Set up one key group: generate a key and store it in the server and all client parameters
setup_key_group() {
    local label=$1
    local server_param=$2
    shift 2
    local client_params=("$@")

    echo ""
    log_info "$label"

    # Check if key already exists on the server side
    local existing_value
    if existing_value=$(get_param "$server_param"); then
        if [[ "$FORCE" == "true" ]]; then
            log_warn "Key exists — regenerating (--force)"
        else
            log_info "Server key exists — checking client parameters"
            echo -e "    ${BLUE}Server:${NC}  $server_param"
            local mismatches=0
            for param in "${client_params[@]}"; do
                local client_value
                if client_value=$(get_param "$param"); then
                    if [[ "$client_value" == "$existing_value" ]]; then
                        echo -e "    ${GREEN}Match:${NC}   $param"
                    else
                        echo -e "    ${RED}MISMATCH:${NC} $param"
                        ((++mismatches))
                        if [[ "$DRY_RUN" == "false" ]]; then
                            put_param "$param" "$existing_value"
                        else
                            echo -e "    ${YELLOW}Would fix:${NC} $param"
                        fi
                    fi
                else
                    echo -e "    ${YELLOW}Missing:${NC} $param"
                    put_param "$param" "$existing_value"
                fi
            done
            if [[ $mismatches -gt 0 && "$DRY_RUN" == "true" ]]; then
                log_warn "$mismatches client key(s) do not match server — use --apply to fix"
            fi
            return 0
        fi
    fi

    # Generate new key
    local key
    key=$(generate_key)

    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "    ${YELLOW}Would generate new key${NC}"
    else
        echo -e "    ${BLUE}Generated new key${NC}"
    fi

    # Store server side
    put_param "$server_param" "$key"

    # Store client side
    for param in "${client_params[@]}"; do
        put_param "$param" "$key"
    done
}

main() {
    parse_args "$@"
    check_dependencies

    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN for environment: $ENV_NAME (use --apply to create parameters)"
    else
        log_info "Setting up MDR API keys for environment: $ENV_NAME"
    fi

    if [[ "$DRY_RUN" == "false" ]]; then
        verify_aws_credentials
    fi

    # GraphQL key: shared by all graphql org instances
    setup_key_group \
        "GraphQL service key" \
        "/${ENV_NAME}/mdr-api/MdrAuthServiceApiKeyGraphql" \
        "/${ENV_NAME}/graphql-org1/MdrApiKey" \
        "/${ENV_NAME}/graphql-org2/MdrApiKey" \
        "/${ENV_NAME}/graphql-org3/MdrApiKey"

    # Semantic search key
    setup_key_group \
        "Semantic Search service key" \
        "/${ENV_NAME}/mdr-api/MdrAuthServiceApiKeySemanticSearch" \
        "/${ENV_NAME}/semantic-search/MdrApiKey"

    # Translator key
    setup_key_group \
        "Translator service key" \
        "/${ENV_NAME}/mdr-api/MdrAuthServiceApiKeyTranslator" \
        "/${ENV_NAME}/translator-org1/MdrApiKey"

    echo ""
    echo "─────────────────────────────────────────"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Run with --apply to create these parameters"
    else
        log_success "All MDR API keys configured for $ENV_NAME"
        echo ""
        log_info "Restart affected services to pick up new keys:"
        echo "  ./aws-deploy.sh -s $ENV_NAME --update-ecs"
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --apply)
                DRY_RUN=false
                shift
                ;;
            --force)
                FORCE=true
                shift
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
    local missing=()

    if ! command -v aws &> /dev/null; then
        missing+=("aws")
    fi
    if ! command -v openssl &> /dev/null; then
        missing+=("openssl")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing[*]}"
        exit 1
    fi
}

verify_aws_credentials() {
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured or expired"
        exit 1
    fi
}

main "$@"
