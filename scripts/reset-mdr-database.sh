#!/usr/bin/env bash
set -euo pipefail
#
# Reset MDR Database
# Rebuilds the Flyway image, updates the Lambda, and invokes it with a Reset
# payload to run flyway clean + migrate. Then re-runs the full SAM deploy to
# sync CloudFormation state.
#
# This is needed when V1.1__metadata_repository_init.sql is replaced (not
# versioned incrementally). Flyway won't re-run an already-applied version,
# so the database must be cleaned and re-migrated from scratch.
#
# Usage:
#   ./scripts/reset-mdr-database.sh <env>             # Dry-run (preview)
#   ./scripts/reset-mdr-database.sh <env> --apply      # Execute reset
#   ./scripts/reset-mdr-database.sh --help              # Show help
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SAM_DIR="$REPO_ROOT/sam"
SAM_DB_DIR="$SAM_DIR/mdr-database"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN=true
ENV_NAME=""

usage() {
    echo "Usage: $0 <env> [OPTIONS]"
    echo ""
    echo "Resets the MDR database by running flyway clean + migrate."
    echo "Use this when V1.1__metadata_repository_init.sql has been replaced."
    echo ""
    echo "WARNING: This destroys all data in the MDR database and re-creates it"
    echo "from the migration files."
    echo ""
    echo "Arguments:"
    echo "  <env>         Environment name (e.g., dev, demo)"
    echo ""
    echo "Options:"
    echo "  --apply       Execute the reset (default is dry-run)"
    echo "  --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 dev                     # Preview reset steps for dev"
    echo "  $0 demo --apply            # Reset the demo MDR database"
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

main() {
    parse_args "$@"
    check_dependencies
    verify_aws_credentials

    local account
    account=$(aws sts get-caller-identity --query Account --output text)
    local region
    region=$(get_region)
    local registry="${account}.dkr.ecr.${region}.amazonaws.com"
    local ecr_repo="${ENV_NAME}-mdr-flyway"
    local lambda_fn="${ENV_NAME}-mdr-flyway"
    local image_uri="${registry}/${ecr_repo}:latest"
    local date_tag
    date_tag=$(date +%F_%H-%M-%S)

    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN — No changes will be made (use --apply to execute)"
    else
        log_warn "This will DESTROY and re-create the ${ENV_NAME} MDR database"
    fi

    echo ""
    echo -e "  ${BLUE}Environment:${NC}  $ENV_NAME"
    echo -e "  ${BLUE}ECR repo:${NC}     $ecr_repo"
    echo -e "  ${BLUE}Lambda:${NC}       $lambda_fn"
    echo -e "  ${BLUE}Region:${NC}       $region"
    echo -e "  ${BLUE}SQL dir:${NC}      sam/mdr-database/flyway/flyway-files/flyway/sql/mdr/"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo ""
        echo -e "  Steps that would be performed:"
        echo -e "    1. Build Flyway Docker image with current SQL files"
        echo -e "    2. Push to ECR as ${ecr_repo}:latest and :${date_tag}"
        echo -e "    3. Update Lambda ${lambda_fn} to use new image"
        echo -e "    4. Wait for Lambda update to complete"
        echo -e "    5. Invoke Lambda with Reset payload (flyway clean + migrate)"
        echo -e "    6. Run full SAM deploy to sync CloudFormation state"
        echo ""
        log_info "Run with --apply to execute"
        return 0
    fi

    echo ""
    build_and_push_image "$registry" "$ecr_repo" "$date_tag" "$region"
    update_lambda "$lambda_fn" "$image_uri"
    wait_for_lambda "$lambda_fn"
    invoke_reset "$lambda_fn"
    sam_deploy "$date_tag"

    echo ""
    echo -e "${GREEN}─────────────────────────────────────────${NC}"
    log_success "MDR database reset complete for $ENV_NAME"
}

get_region() {
    # Source region from the env .aws file
    local aws_file="$REPO_ROOT/${ENV_NAME}.aws"
    if [[ -f "$aws_file" ]]; then
        # shellcheck disable=SC1090
        source "$aws_file"
        echo "$AWS_REGION"
    else
        log_error "Environment file not found: $aws_file"
        exit 1
    fi
}

build_and_push_image() {
    local registry=$1
    local ecr_repo=$2
    local date_tag=$3
    local region=$4

    log_info "Step 1/6: Building Flyway Docker image..."

    local build_dir="$SAM_DB_DIR/flyway"

    (cd "$build_dir" && docker build --platform linux/amd64 . -t "$registry/$ecr_repo:latest" -q) || {
        log_error "Docker build failed"
        exit 1
    }
    log_success "Image built"

    log_info "Step 2/6: Pushing to ECR..."

    aws ecr get-login-password --region "$region" | \
        docker login --username AWS --password-stdin "$registry" 2>/dev/null || {
        log_error "ECR login failed"
        exit 1
    }

    docker push "$registry/$ecr_repo:latest" -q || {
        log_error "Failed to push :latest"
        exit 1
    }

    docker tag "$registry/$ecr_repo:latest" "$registry/$ecr_repo:$date_tag"
    docker push "$registry/$ecr_repo:$date_tag" -q || {
        log_error "Failed to push :$date_tag"
        exit 1
    }

    log_success "Pushed $ecr_repo:latest and :$date_tag"
}

update_lambda() {
    local lambda_fn=$1
    local image_uri=$2

    log_info "Step 3/6: Updating Lambda function to use new image..."

    aws lambda update-function-code \
        --function-name "$lambda_fn" \
        --image-uri "$image_uri" \
        --output text \
        --query 'FunctionArn' > /dev/null || {
        log_error "Failed to update Lambda function"
        exit 1
    }

    log_success "Lambda update initiated"
}

wait_for_lambda() {
    local lambda_fn=$1

    log_info "Step 4/6: Waiting for Lambda update to complete..."

    aws lambda wait function-updated \
        --function-name "$lambda_fn" || {
        log_error "Lambda update did not complete (timed out or failed)"
        exit 1
    }

    log_success "Lambda function updated and ready"
}

invoke_reset() {
    local lambda_fn=$1

    log_info "Step 5/6: Invoking Lambda with Reset payload (flyway clean + migrate)..."
    log_warn "This will destroy all data in the MDR database"

    local output_file payload_file
    output_file=$(mktemp)
    payload_file=$(mktemp)
    echo '{"RequestType": "Reset"}' > "$payload_file"

    aws lambda invoke \
        --function-name "$lambda_fn" \
        --payload "fileb://$payload_file" \
        --cli-read-timeout 600 \
        "$output_file" > /dev/null || {
        log_error "Lambda invocation failed"
        rm -f "$output_file" "$payload_file"
        exit 1
    }
    rm -f "$payload_file"

    # Check for errors in the response
    if grep -q "errorMessage" "$output_file" 2>/dev/null; then
        log_error "Flyway reset failed:"
        cat "$output_file"
        rm -f "$output_file"
        exit 1
    fi

    rm -f "$output_file"
    log_success "Flyway clean + migrate completed"
}

sam_deploy() {
    local date_tag=$1

    log_info "Step 6/6: Running SAM deploy to sync CloudFormation state..."

    (cd "$SAM_DIR" && bash deploy-sam.sh -s "$REPO_ROOT/$ENV_NAME" -d mdr-database) || {
        log_error "SAM deploy failed"
        exit 1
    }

    log_success "CloudFormation state synced"
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
}

check_dependencies() {
    local missing=()

    if ! command -v aws &> /dev/null; then
        missing+=("aws")
    fi
    if ! command -v docker &> /dev/null; then
        missing+=("docker")
    fi
    if ! command -v sam &> /dev/null; then
        missing+=("sam")
    fi
    if ! command -v yq &> /dev/null; then
        missing+=("yq")
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
