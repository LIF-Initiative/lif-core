#!/usr/bin/env bash
#
# Release to Demo
# Updates demo CloudFormation parameter files with the latest image tags from dev ECR.
#
# Author: LIF Initiative
# Date: 2026-02-05
# Version: 1.0.0
#
# Usage:
#   ./scripts/release-demo.sh              # Dry-run (preview changes)
#   ./scripts/release-demo.sh --apply      # Apply changes to files
#   ./scripts/release-demo.sh --help       # Show help
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

# Global variables for inter-function communication
_CURR_URL=""
_NEW_URL=""
_REPO=""
_TAG=""

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

    # Extract current ImageUrl value (guarded against jq failure)
    local curr_val
    if ! curr_val=$(jq -er '.[] | select(.ParameterKey == "ImageUrl") | .ParameterValue' "$file" 2>/dev/null); then
        log_error "Could not extract ImageUrl from $file (jq failed or value is null)"
        return 1
    fi

    if [[ -z "$curr_val" ]]; then
        log_error "Could not extract ImageUrl from $file"
        return 1
    fi

    # Extract repository name from URL with validation
    # Example: <account-id>.dkr.ecr.us-east-1.amazonaws.com/lif/dev/lif_graphql_api:tag
    #       -> lif/dev/lif_graphql_api
    local repo

    # Strip optional tag (everything after the first ':')
    local repo_url_no_tag="${curr_val%%:*}"

    # Remove registry domain (everything up to and including the first '/')
    local repo_path="${repo_url_no_tag#*/}"

    # Validate that a '/' was present; if not, the format is unexpected
    if [[ "$repo_path" == "$repo_url_no_tag" ]]; then
        log_error "Unexpected ImageUrl format (missing repository path): $curr_val"
        return 1
    fi

    repo="$repo_path"

    if [[ -z "$repo" ]]; then
        log_error "Could not extract repository name from $curr_val"
        return 1
    fi

    # Extract AWS region from image URL
    local region
    region=$(echo "$curr_val" | sed -n 's/.*\.ecr\.\([^.]*\)\.amazonaws.*/\1/p')

    if [[ -z "$region" ]]; then
        log_error "Could not extract AWS region from $curr_val"
        return 1
    fi

    # Query ECR for the image tagged "latest"
    # The "latest" tag is an alias; we want the actual version tag
    local ecr_output
    local ecr_exit_code
    local tag

    # Guard against -e exit by capturing exit code separately
    # Use --output json to ensure consistent output format regardless of AWS_DEFAULT_OUTPUT
    # Use --image-ids to query only the "latest" tag for efficiency
    ecr_output=$(aws ecr describe-images \
        --repository-name "$repo" \
        --region "$region" \
        --image-ids imageTag=latest \
        --output json 2>&1) || ecr_exit_code=$?

    if [[ -n "${ecr_exit_code:-}" ]]; then
        if echo "$ecr_output" | grep -q "AccessDeniedException"; then
            log_error "Access denied to ECR (repo: $repo, region: $region)"
            log_error "Ensure you're authenticated to the correct AWS account"
            return 1
        fi

        if echo "$ecr_output" | grep -q "RepositoryNotFoundException"; then
            log_error "Repository not found: $repo (region: $region)"
            return 1
        fi

        if echo "$ecr_output" | grep -q "ImageNotFoundException"; then
            log_error "No image tagged 'latest' found in repository: $repo"
            return 1
        fi

        # Generic error
        log_error "ECR query failed for $repo (region: $region): $ecr_output"
        return 1
    fi

    # Extract the version tag (the non-"latest" tag on this image)
    # Sort and select the most recent (lexicographically largest for timestamp-based tags)
    tag=$(echo "$ecr_output" | jq -r '.imageDetails[0].imageTags | map(select(. != "latest")) | sort | last' 2>/dev/null)

    if [[ -z "$tag" || "$tag" == "null" ]]; then
        log_error "Image tagged 'latest' in $repo has no version tag to resolve"
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

    # Initialize global variables to avoid stale values from previous iterations
    _CURR_URL=""
    _NEW_URL=""
    _REPO=""
    _TAG=""

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

    # Apply the change - validate old value to ensure we're updating the expected value
    local contents
    if ! contents=$(jq --arg old "$_CURR_URL" --arg new "$_NEW_URL" \
        '(.[] | select(.ParameterKey == "ImageUrl" and .ParameterValue == $old) | .ParameterValue) |= $new' "$file" 2>/dev/null); then
        log_error "Failed to parse or update JSON for $file"
        ERRORS+=("$file")
        return 1
    fi

    if [[ -z "$contents" ]]; then
        log_error "Failed to generate updated JSON for $file"
        ERRORS+=("$file")
        return 1
    fi

    # Verify the update actually happened (old value was found and replaced)
    if echo "$contents" | jq -e --arg old "$_CURR_URL" '.[] | select(.ParameterKey == "ImageUrl" and .ParameterValue == $old)' &>/dev/null; then
        log_error "ImageUrl value was not updated in $file (old value still present)"
        ERRORS+=("$file")
        return 1
    fi

    # Safely write updated JSON to a temporary file, then move it into place
    local temp_file
    temp_file=$(mktemp) || {
        log_error "Failed to create temporary file for $file"
        ERRORS+=("$file")
        return 1
    }

    if echo "$contents" | jq '.' > "$temp_file"; then
        if mv "$temp_file" "$file"; then
            log_success "Updated $(basename "$file")"
        else
            log_error "Failed to move temporary file into place for $file"
            ERRORS+=("$file")
            rm -f "$temp_file"
            return 1
        fi
    else
        log_error "Failed to write updated JSON to temporary file for $file"
        ERRORS+=("$file")
        rm -f "$temp_file"
        return 1
    fi
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

    # Find param files using arrays for proper handling of filenames
    shopt -s nullglob
    local -a all_param_files=(cloudformation/demo*.params)
    shopt -u nullglob

    if [[ ${#all_param_files[@]} -eq 0 ]]; then
        log_warn "No demo param files found"
        exit 0
    fi

    # Filter to only files containing ImageUrl
    local -a param_files=()
    for f in "${all_param_files[@]}"; do
        if grep -q ImageUrl "$f" 2>/dev/null; then
            param_files+=("$f")
        fi
    done

    if [[ ${#param_files[@]} -eq 0 ]]; then
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

    for file in "${param_files[@]}"; do
        if update_params_file "$file"; then
            if [[ "$_CURR_URL" != "$_NEW_URL" ]]; then
                ((++updated))
            else
                ((++skipped))
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
