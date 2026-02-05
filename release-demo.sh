#!/bin/bash
#
# Release to Demo
# Updates demo CloudFormation parameter files with the latest image tags from dev ECR.
#
# Usage:
#   ./release-demo.sh              # Dry-run (preview changes)
#   ./release-demo.sh --apply      # Apply changes to files
#   ./release-demo.sh --help       # Show help
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

DRY_RUN=true
VERBOSE=false
ERRORS=()

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Updates demo CloudFormation parameter files with latest image tags from dev ECR."
    echo ""
    echo "Options:"
    echo "  --apply     Apply changes (default is dry-run)"
    echo "  --verbose   Show detailed output"
    echo "  --help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0              # Preview changes (dry-run)"
    echo "  $0 --apply      # Apply changes to param files"
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

# Get the latest release tag for an image
# Returns: image URL with resolved tag, or empty string on failure
get_release_tag() {
    local file=$1

    # Extract current ImageUrl value
    local curr_val
    curr_val=$(jq -r '.[] | select(.ParameterKey == "ImageUrl") | .ParameterValue' "$file")

    if [[ -z "$curr_val" ]]; then
        log_error "Could not extract ImageUrl from $file"
        return 1
    fi

    # Extract repository name from URL
    # Example: 381492161417.dkr.ecr.us-east-1.amazonaws.com/lif/dev/lif_graphql_api:tag
    #       -> lif/dev/lif_graphql_api
    local repo
    repo=$(echo "$curr_val" | sed 's#[^/]*/##' | sed 's#:.*##')

    if [[ -z "$repo" ]]; then
        log_error "Could not extract repository name from $curr_val"
        return 1
    fi

    # Query ECR for the tag associated with "latest"
    # The "latest" tag is an alias; we want the actual version tag
    local ecr_output
    local tag

    ecr_output=$(aws ecr describe-images --repository-name "$repo" 2>&1)

    if echo "$ecr_output" | grep -q "AccessDeniedException"; then
        log_error "Access denied to ECR (repo: $repo)"
        log_error "Ensure you're authenticated to the correct AWS account"
        return 1
    fi

    if echo "$ecr_output" | grep -q "RepositoryNotFoundException"; then
        log_error "Repository not found: $repo"
        return 1
    fi

    tag=$(echo "$ecr_output" | jq -r '.imageDetails[] | select(has("imageTags")) | select(.imageTags | any(. == "latest")) | .imageTags - ["latest"] | .[0]' 2>/dev/null)

    if [[ -z "$tag" || "$tag" == "null" ]]; then
        log_error "No 'latest' tag found for repository: $repo"
        return 1
    fi

    # Build new image URL with resolved tag
    local new_url
    new_url=$(echo "$curr_val" | sed "s/:.*/:$tag/")

    # Return values via global variables (bash limitation)
    _CURR_URL="$curr_val"
    _NEW_URL="$new_url"
    _REPO="$repo"
    _TAG="$tag"

    return 0
}

# Update a single params file
update_params_file() {
    local file=$1

    if ! get_release_tag "$file"; then
        ERRORS+=("$file")
        return 1
    fi

    # Check if update is needed
    if [[ "$_CURR_URL" == "$_NEW_URL" ]]; then
        if [[ "$VERBOSE" == "true" ]]; then
            log_info "$(basename "$file"): Already up to date ($_TAG)"
        fi
        return 0
    fi

    # Show what will change
    echo ""
    echo -e "  ${BLUE}File:${NC} $(basename "$file")"
    echo -e "  ${YELLOW}From:${NC} $_CURR_URL"
    echo -e "  ${GREEN}To:${NC}   $_NEW_URL"

    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi

    # Apply the change
    local contents
    contents=$(jq --arg old "$_CURR_URL" --arg new "$_NEW_URL" \
        '(.[] | select(.ParameterKey == "ImageUrl") | .ParameterValue) |= $new' "$file")

    if [[ -z "$contents" ]]; then
        log_error "Failed to generate updated JSON for $file"
        ERRORS+=("$file")
        return 1
    fi

    echo "$contents" | jq '.' > "$file"
    log_success "Updated $(basename "$file")"
}

# Main
main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --apply)
                DRY_RUN=false
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    # Check dependencies
    if ! command -v jq &> /dev/null; then
        log_error "jq is required but not installed"
        exit 1
    fi

    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is required but not installed"
        exit 1
    fi

    # Verify AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured or expired"
        exit 1
    fi

    # Find param files
    local param_files
    param_files=$(ls -1 cloudformation/demo*.params 2>/dev/null | xargs -I {} grep -l ImageUrl {} 2>/dev/null || true)

    if [[ -z "$param_files" ]]; then
        log_warn "No demo param files with ImageUrl found"
        exit 0
    fi

    # Header
    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN - No changes will be made (use --apply to apply changes)"
    else
        log_info "Applying changes to demo param files"
    fi
    echo ""
    log_info "Checking for updates..."

    # Process each file
    local updated=0
    local skipped=0

    for file in $param_files; do
        if update_params_file "$file"; then
            if [[ "$_CURR_URL" != "$_NEW_URL" ]]; then
                ((updated++))
            else
                ((skipped++))
            fi
        fi
    done

    # Summary
    echo ""
    echo "─────────────────────────────────────────"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Summary (dry-run):"
    else
        log_info "Summary:"
    fi
    echo "  Files to update: $updated"
    echo "  Already current: $skipped"
    echo "  Errors: ${#ERRORS[@]}"

    if [[ ${#ERRORS[@]} -gt 0 ]]; then
        echo ""
        log_error "Failed files:"
        for f in "${ERRORS[@]}"; do
            echo "  - $f"
        done
        exit 1
    fi

    if [[ "$DRY_RUN" == "true" && $updated -gt 0 ]]; then
        echo ""
        log_info "Run with --apply to apply these changes"
    fi
}

main "$@"
