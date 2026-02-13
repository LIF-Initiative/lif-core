#!/usr/bin/env bash
set -euo pipefail
#
# Verify Demo Images
# Compares image tags in CloudFormation param files against what is actually
# running in the demo ECS cluster.
#
# Usage:
#   ./verify-demo-images.sh              # Compare all services
#   ./verify-demo-images.sh --help       # Show help
#

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CLUSTER="demo"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Compares image tags in demo param files against running ECS tasks."
    echo ""
    echo "Options:"
    echo "  --help    Show this help message"
    echo ""
    echo "Examples:"
    echo "  AWS_PROFILE=lif $0"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[MATCH]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_mismatch() {
    echo -e "${RED}[MISMATCH]${NC} $1"
}

main() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    # Check dependencies
    if ! command -v jq &> /dev/null; then
        echo "jq is required but not installed"
        exit 1
    fi

    if ! aws sts get-caller-identity &> /dev/null; then
        echo "AWS credentials not configured or expired"
        exit 1
    fi

    # Build a map of ECR repo -> running image from ECS
    log_info "Fetching running images from ECS cluster: $CLUSTER"

    local -A ecs_images=()
    local service_arns
    service_arns=$(aws ecs list-services --cluster "$CLUSTER" --query 'serviceArns[*]' --output text)

    for arn in $service_arns; do
        local svc_name="${arn##*/}"
        local taskdef
        taskdef=$(aws ecs describe-services --cluster "$CLUSTER" --services "$svc_name" \
            --query 'services[0].taskDefinition' --output text 2>/dev/null) || continue

        if [[ "$taskdef" == "None" || -z "$taskdef" ]]; then
            continue
        fi

        local image
        image=$(aws ecs describe-task-definition --task-definition "$taskdef" \
            --query 'taskDefinition.containerDefinitions[0].image' --output text 2>/dev/null) || continue

        if [[ -z "$image" || "$image" == "None" ]]; then
            continue
        fi

        # Key by ECR repo path (strip registry and tag)
        local repo="${image%%:*}"
        repo="${repo#*/}"
        ecs_images["$repo"]="$image"
    done

    log_info "Found ${#ecs_images[@]} running services"
    echo ""

    # Compare against param files
    shopt -s nullglob
    local -a param_files=(cloudformation/demo*.params)
    shopt -u nullglob

    local matches=0
    local mismatches=0
    local not_running=0

    for file in "${param_files[@]}"; do
        local param_image
        param_image=$(jq -er '.[] | select(.ParameterKey == "ImageUrl") | .ParameterValue' "$file" 2>/dev/null) || continue

        if [[ -z "$param_image" ]]; then
            continue
        fi

        # Extract repo path from param file image URL
        local param_repo="${param_image%%:*}"
        param_repo="${param_repo#*/}"
        local param_tag="${param_image##*:}"

        local base_name
        base_name=$(basename "$file")

        # Look up running image by repo
        if [[ -n "${ecs_images[$param_repo]+_}" ]]; then
            local running_image="${ecs_images[$param_repo]}"
            local running_tag="${running_image##*:}"

            if [[ "$param_tag" == "$running_tag" ]]; then
                log_success "$base_name  ($param_tag)"
                ((++matches))
            else
                log_mismatch "$base_name"
                echo -e "    ${BLUE}Param file:${NC} $param_tag"
                echo -e "    ${BLUE}Running:${NC}    $running_tag"
                ((++mismatches))
            fi
        else
            log_warn "$base_name — not running in ECS"
            ((++not_running))
        fi
    done

    # Summary
    echo ""
    echo "─────────────────────────────────────────"
    log_info "Summary:"
    echo -e "  ${GREEN}Matching:${NC}     $matches"
    echo -e "  ${RED}Mismatched:${NC}   $mismatches"
    echo -e "  ${YELLOW}Not running:${NC}  $not_running"

    if [[ $mismatches -gt 0 ]]; then
        echo ""
        log_info "To deploy mismatched stacks:"
        echo "  ./aws-deploy.sh -s demo --only-stack <stack-name>"
        exit 1
    fi
}

main "$@"
