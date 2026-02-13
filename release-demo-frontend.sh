#!/bin/bash -eu
#
# Release MDR Frontend to Demo
# Builds the MDR frontend from a specific git ref and deploys to the demo S3 bucket.
#
# Usage:
#   ./release-demo-frontend.sh <git-ref>              # Dry-run (preview)
#   ./release-demo-frontend.sh <git-ref> --apply      # Build and deploy
#   ./release-demo-frontend.sh --help                  # Show help
#

set -o pipefail

# Configuration
ENV_NAME=demo
SERVICE_NAME=mdr
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=381492161417
S3_BUCKET="${ENV_NAME}-${SERVICE_NAME}-${AWS_ACCOUNT_ID}-${AWS_REGION}"
SSM_DISTRIBUTION_ID="/${ENV_NAME}/${SERVICE_NAME}/DistributionId"
VITE_API_URL="https://mdr-api.${ENV_NAME}.lif.unicon.net"
FRONTEND_DIR="frontends/mdr-frontend"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN=true
GIT_REF=""
WORKTREE_DIR=""

usage() {
    echo "Usage: $0 <git-ref> [OPTIONS]"
    echo ""
    echo "Builds the MDR frontend from a specific git ref and deploys to the demo S3 bucket."
    echo ""
    echo "Arguments:"
    echo "  <git-ref>     Git commit SHA, tag, or branch name to build from"
    echo ""
    echo "Options:"
    echo "  --apply       Build and deploy (default is dry-run)"
    echo "  --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 main                    # Preview deploying from main"
    echo "  $0 abc1234 --apply         # Deploy from a specific commit"
    echo "  $0 v1.2.0 --apply          # Deploy from a tag"
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

cleanup() {
    if [[ -n "$WORKTREE_DIR" && -d "$WORKTREE_DIR" ]]; then
        log_info "Cleaning up worktree..."
        git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
    fi
}

trap cleanup EXIT

main() {
    parse_args "$@"
    check_dependencies
    validate_git_ref

    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN - No changes will be made (use --apply to build and deploy)"
    else
        log_info "Building and deploying MDR frontend to demo"
    fi

    local resolved_sha
    resolved_sha=$(git rev-parse "$GIT_REF")
    local short_sha="${resolved_sha:0:7}"

    echo ""
    echo -e "  ${BLUE}Git ref:${NC}     $GIT_REF"
    echo -e "  ${BLUE}Commit:${NC}      $resolved_sha"
    echo -e "  ${BLUE}API URL:${NC}     $VITE_API_URL"
    echo -e "  ${BLUE}S3 bucket:${NC}   s3://$S3_BUCKET"
    echo -e "  ${BLUE}Source dir:${NC}  $FRONTEND_DIR"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo ""
        log_info "Run with --apply to build and deploy"
        return 0
    fi

    verify_aws_credentials
    checkout_worktree "$resolved_sha"
    build_frontend
    deploy_to_s3
    invalidate_cloudfront

    echo ""
    echo -e "${GREEN}─────────────────────────────────────────${NC}"
    log_success "MDR frontend deployed to demo from $short_sha"
    echo -e "  ${BLUE}URL:${NC} https://${SERVICE_NAME}.${ENV_NAME}.lif.unicon.net"
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
                if [[ -z "$GIT_REF" ]]; then
                    GIT_REF="$1"
                else
                    log_error "Unexpected argument: $1"
                    usage
                    exit 1
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$GIT_REF" ]]; then
        log_error "Git ref is required"
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
    if ! command -v node &> /dev/null; then
        missing+=("node")
    fi
    if ! command -v npm &> /dev/null; then
        missing+=("npm")
    fi
    if ! command -v git &> /dev/null; then
        missing+=("git")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing[*]}"
        exit 1
    fi
}

validate_git_ref() {
    if ! git rev-parse --verify "$GIT_REF" &> /dev/null; then
        log_error "Invalid git ref: $GIT_REF"
        log_error "Provide a valid commit SHA, tag, or branch name"
        exit 1
    fi
}

verify_aws_credentials() {
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured or expired"
        exit 1
    fi
}

checkout_worktree() {
    local sha=$1

    WORKTREE_DIR=$(mktemp -d)
    log_info "Checking out $sha into temporary worktree..."

    if ! git worktree add --detach "$WORKTREE_DIR" "$sha" 2>/dev/null; then
        log_error "Failed to create git worktree for $sha"
        exit 1
    fi

    if [[ ! -d "$WORKTREE_DIR/$FRONTEND_DIR" ]]; then
        log_error "Directory $FRONTEND_DIR not found at ref $GIT_REF"
        exit 1
    fi
}

build_frontend() {
    local build_dir="$WORKTREE_DIR/$FRONTEND_DIR"

    log_info "Installing dependencies..."
    (cd "$build_dir" && npm ci --silent) || {
        log_error "npm ci failed"
        exit 1
    }

    log_info "Building with VITE_API_URL=$VITE_API_URL..."
    echo "VITE_API_URL=$VITE_API_URL" > "$build_dir/.env"
    (cd "$build_dir" && npm run build --silent) || {
        log_error "npm run build failed"
        exit 1
    }

    if [[ ! -d "$build_dir/dist" ]]; then
        log_error "Build did not produce a dist/ directory"
        exit 1
    fi

    log_success "Build complete ($(find "$build_dir/dist" -type f | wc -l | tr -d ' ') files)"
}

deploy_to_s3() {
    local dist_dir="$WORKTREE_DIR/$FRONTEND_DIR/dist"

    log_info "Syncing to s3://$S3_BUCKET..."
    if ! aws s3 sync --delete "$dist_dir" "s3://$S3_BUCKET"; then
        log_error "S3 sync failed"
        exit 1
    fi
    log_success "S3 sync complete"
}

invalidate_cloudfront() {
    log_info "Fetching CloudFront distribution ID from SSM..."

    local distribution_id
    distribution_id=$(aws ssm get-parameter \
        --name "$SSM_DISTRIBUTION_ID" \
        --query "Parameter.Value" \
        --output text 2>/dev/null) || {
        log_warn "Could not fetch distribution ID from SSM ($SSM_DISTRIBUTION_ID)"
        log_warn "Skipping CloudFront invalidation — content is deployed but may be cached"
        return 0
    }

    log_info "Invalidating CloudFront distribution $distribution_id..."
    if ! aws cloudfront create-invalidation \
        --distribution-id "$distribution_id" \
        --paths "/" > /dev/null; then
        log_warn "CloudFront invalidation failed — content is deployed but may be cached"
        return 0
    fi
    log_success "CloudFront invalidation created"
}

main "$@"
