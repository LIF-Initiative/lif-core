#!/usr/bin/env bash
set -euo pipefail
#
# Setup Demo User Password — run with --help for usage details.
#

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN=true
ENV_NAME=""

# SSM parameter paths (one per service)
SSM_PARAMS=()

usage() {
    echo "Usage: $0 <env> [OPTIONS]"
    echo ""
    echo "Stores a shared demo user password in SSM Parameter Store for"
    echo "the Advisor API and MDR API services."
    echo ""
    echo "The password is read interactively (not echoed) so it never"
    echo "appears in shell history."
    echo ""
    echo "Arguments:"
    echo "  <env>         Environment name (e.g., dev, demo)"
    echo ""
    echo "Options:"
    echo "  --apply       Store the password (default is dry-run)"
    echo "  --help        Show this help message"
    echo ""
    echo "SSM parameters created:"
    echo "  /{env}/advisor-api/DemoUserPassword    (SecureString)"
    echo "  /{env}/mdr-api/DemoUserPassword        (SecureString)"
    echo ""
    echo "Examples:"
    echo "  AWS_PROFILE=lif $0 dev                 # Preview what would be created"
    echo "  AWS_PROFILE=lif $0 demo --apply        # Store password for demo"
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

    SSM_PARAMS=(
        "/${ENV_NAME}/advisor-api/DemoUserPassword"
        "/${ENV_NAME}/mdr-api/DemoUserPassword"
    )
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

# Check if an SSM parameter exists
param_exists() {
    local name=$1
    aws ssm get-parameter --name "$name" --with-decryption &>/dev/null
}

show_status() {
    echo ""
    log_info "Current status for environment: ${ENV_NAME}"
    echo ""

    for param in "${SSM_PARAMS[@]}"; do
        if param_exists "$param"; then
            echo -e "  ${GREEN}Exists:${NC}  $param"
        else
            echo -e "  ${YELLOW}Missing:${NC} $param"
        fi
    done
}

main() {
    parse_args "$@"
    check_dependencies

    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN for environment: ${ENV_NAME} (use --apply to store password)"
        show_status
        echo ""
        log_info "Run with --apply to set the password"
    else
        log_info "Setting demo user password for environment: ${ENV_NAME}"
        verify_aws_credentials
        show_status

        echo ""
        read -r -s -p "Enter demo user password: " PASSWORD
        echo ""
        read -r -s -p "Confirm password: " PASSWORD_CONFIRM
        echo ""

        if [[ "$PASSWORD" != "$PASSWORD_CONFIRM" ]]; then
            log_error "Passwords do not match"
            exit 1
        fi

        if [[ -z "$PASSWORD" ]]; then
            log_error "Password cannot be empty"
            exit 1
        fi

        echo ""
        for param in "${SSM_PARAMS[@]}"; do
            if ! aws ssm put-parameter \
                --name "$param" \
                --value "$PASSWORD" \
                --type SecureString \
                --overwrite 1>/dev/null; then
                log_error "Failed to store: $param"
                exit 1
            fi
            log_ok "Stored: $param"
        done

        echo ""
        echo "─────────────────────────────────────────"
        log_ok "Demo user password configured for ${ENV_NAME}"
        echo ""
        log_info "Restart affected services to pick up the new password:"
        echo "  ./aws-deploy.sh -s ${ENV_NAME} --only-stack ${ENV_NAME}-lif-advisor-api"
        echo "  ./aws-deploy.sh -s ${ENV_NAME} --only-stack ${ENV_NAME}-lif-mdr-api"
    fi
}

main "$@"
