#!/usr/bin/env bash
#
# setup-graphql-api-keys.sh — Manage GraphQL org1 API keys in AWS SSM Parameter Store
#
# Modes:
#   Service mode (default): Sets up the semantic-search service key (server + client SSM params)
#   Workshop mode: Generates keys for workshop participants (server SSM only, keys printed to stdout)
#
# Usage:
#   # Service key setup
#   AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh <env>           # Preview
#   AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh <env> --apply   # Create/update
#
#   # Workshop key generation
#   AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh <env> --workshop <count> [--prefix <label>] [--apply]
#
# Examples:
#   AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo
#   AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo --apply
#   AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo --workshop 10 --apply
#   AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh dev --workshop 5 --prefix attendee --apply

set -euo pipefail

# ----------- Configuration -----------

GRAPHQL_SERVICE_NAME="graphql-org1"
CLIENT_SERVICE_NAME="semantic-search"
CLIENT_LABEL="semantic-search"

# ----------- Argument parsing -----------

ENV="${1:-}"
APPLY=false
WORKSHOP_COUNT=""
WORKSHOP_PREFIX="workshop"

if [[ -z "$ENV" ]]; then
    echo "Usage: $0 <env> [options]"
    echo ""
    echo "  Service mode (default):"
    echo "    $0 <env> [--apply]"
    echo ""
    echo "  Workshop mode:"
    echo "    $0 <env> --workshop <count> [--prefix <label>] [--apply]"
    echo ""
    echo "  Options:"
    echo "    <env>               Environment name (e.g., dev, demo)"
    echo "    --apply             Actually create/update SSM parameters (default: preview only)"
    echo "    --workshop <count>  Generate <count> workshop user keys"
    echo "    --prefix <label>    Label prefix for workshop keys (default: workshop)"
    exit 1
fi

shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            APPLY=true
            shift
            ;;
        --workshop)
            WORKSHOP_COUNT="$2"
            shift 2
            ;;
        --prefix)
            WORKSHOP_PREFIX="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ----------- SSM parameter paths -----------

SERVER_PARAM="/${ENV}/${GRAPHQL_SERVICE_NAME}/ApiKeys"
CLIENT_PARAM="/${ENV}/${CLIENT_SERVICE_NAME}/GraphqlApiKey"

# ----------- Helper functions -----------

generate_key() {
    python3 -c "import secrets; print(secrets.token_urlsafe(32))"
}

get_ssm_param() {
    local param_name="$1"
    aws ssm get-parameter \
        --name "$param_name" \
        --with-decryption \
        --query "Parameter.Value" \
        --output text 2>/dev/null || echo ""
}

put_ssm_param() {
    local param_name="$1"
    local param_value="$2"
    local description="$3"

    aws ssm put-parameter \
        --name "$param_name" \
        --value "$param_value" \
        --type "SecureString" \
        --description "$description" \
        --overwrite
}

# ----------- Workshop mode -----------

run_workshop_mode() {
    echo "=== GraphQL Workshop Key Generation ==="
    echo "Environment: ${ENV}"
    echo "Server param: ${SERVER_PARAM}"
    echo "Key count: ${WORKSHOP_COUNT}"
    echo "Label prefix: ${WORKSHOP_PREFIX}"
    echo ""

    existing_server_value=$(get_ssm_param "$SERVER_PARAM")

    # Generate keys
    declare -a WORKSHOP_KEYS
    declare -a WORKSHOP_LABELS
    NEW_ENTRIES=""

    if [[ "$WORKSHOP_COUNT" -gt 0 ]]; then
        for i in $(seq 1 "$WORKSHOP_COUNT"); do
            label="${WORKSHOP_PREFIX}-$(printf '%02d' "$i")"
            key=$(generate_key)
            WORKSHOP_KEYS+=("$key")
            WORKSHOP_LABELS+=("$label")
            entry="${key}:${label}"
            if [[ -n "$NEW_ENTRIES" ]]; then
                NEW_ENTRIES="${NEW_ENTRIES},${entry}"
            else
                NEW_ENTRIES="${entry}"
            fi
        done
    fi

    # Build combined server value — remove existing entries with matching prefix
    if [[ -n "$existing_server_value" ]]; then
        FILTERED_VALUE=$(echo "$existing_server_value" | tr ',' '\n' | grep -v ":${WORKSHOP_PREFIX}-" | tr '\n' ',' | sed 's/,$//')
        if [[ -n "$NEW_ENTRIES" ]]; then
            if [[ -n "$FILTERED_VALUE" ]]; then
                SERVER_VALUE="${FILTERED_VALUE},${NEW_ENTRIES}"
            else
                SERVER_VALUE="${NEW_ENTRIES}"
            fi
            echo "Existing server ApiKeys found — replacing any '${WORKSHOP_PREFIX}-*' entries"
        else
            SERVER_VALUE="${FILTERED_VALUE}"
            echo "Existing server ApiKeys found — removing all '${WORKSHOP_PREFIX}-*' entries"
        fi
    else
        SERVER_VALUE="${NEW_ENTRIES}"
        if [[ -n "$NEW_ENTRIES" ]]; then
            echo "No existing server ApiKeys — will create with workshop entries"
        else
            echo "No existing server ApiKeys and nothing to remove"
            exit 0
        fi
    fi

    echo ""
    if [[ "$WORKSHOP_COUNT" -gt 0 ]]; then
        echo "--- Generated keys ---"
        for i in $(seq 0 $((WORKSHOP_COUNT - 1))); do
            printf "  %-20s %s\n" "${WORKSHOP_LABELS[$i]}" "${WORKSHOP_KEYS[$i]}"
        done
    fi

    echo ""
    echo "--- Server param update ---"
    if [[ "$WORKSHOP_COUNT" -gt 0 ]]; then
        echo "  ${SERVER_PARAM}: ${WORKSHOP_COUNT} workshop entries (+ existing service keys)"
    else
        echo "  ${SERVER_PARAM}: removing all workshop entries (service keys preserved)"
    fi

    if [[ "$APPLY" != "true" ]]; then
        echo ""
        echo "DRY RUN — pass --apply to create/update parameters"
        exit 0
    fi

    echo ""
    echo "Applying..."
    put_ssm_param "$SERVER_PARAM" "$SERVER_VALUE" "GraphQL org1 API keys (key:client-name format)"
    echo "  Created/updated: ${SERVER_PARAM}"

    echo ""
    echo "Done. Redeploy GraphQL org1 to pick up the new keys:"
    echo "  ./aws-deploy.sh -s ${ENV} --only-stack ${ENV}-lif-graphql-org1"

    if [[ "$WORKSHOP_COUNT" -gt 0 ]]; then
        echo ""
        echo "=== Keys for distribution ==="
        for i in $(seq 0 $((WORKSHOP_COUNT - 1))); do
            echo "${WORKSHOP_KEYS[$i]}"
        done
    fi
}

# ----------- Service mode -----------

run_service_mode() {
    echo "=== GraphQL API Key Setup ==="
    echo "Environment: ${ENV}"
    echo "Server param: ${SERVER_PARAM}"
    echo "Client param: ${CLIENT_PARAM}"
    echo ""

    # Check existing state
    existing_server_value=$(get_ssm_param "$SERVER_PARAM")
    existing_client_value=$(get_ssm_param "$CLIENT_PARAM")

    if [[ -n "$existing_client_value" ]]; then
        echo "Existing client key found in ${CLIENT_PARAM}"
        KEY="$existing_client_value"
        echo "  Will reuse existing key"
    else
        echo "No existing client key found — will generate a new one"
        KEY=$(generate_key)
        echo "  Generated key: ${KEY:0:8}..."
    fi

    # Build the server-side value (format: "key:client-name")
    NEW_ENTRY="${KEY}:${CLIENT_LABEL}"

    if [[ -n "$existing_server_value" ]]; then
        echo ""
        echo "Existing server ApiKeys value found in ${SERVER_PARAM}"
        # Check if our client label already has an entry
        if echo "$existing_server_value" | grep -q ":${CLIENT_LABEL}"; then
            echo "  Entry for '${CLIENT_LABEL}' already exists — will replace it"
            # Remove existing entry for this client and append updated one
            UPDATED_VALUE=$(echo "$existing_server_value" | tr ',' '\n' | grep -v ":${CLIENT_LABEL}$" | tr '\n' ',' | sed 's/,$//')
            if [[ -n "$UPDATED_VALUE" ]]; then
                SERVER_VALUE="${UPDATED_VALUE},${NEW_ENTRY}"
            else
                SERVER_VALUE="${NEW_ENTRY}"
            fi
        else
            echo "  Appending new entry for '${CLIENT_LABEL}'"
            SERVER_VALUE="${existing_server_value},${NEW_ENTRY}"
        fi
    else
        echo "No existing server ApiKeys — will create with single entry"
        SERVER_VALUE="${NEW_ENTRY}"
    fi

    echo ""
    echo "--- Planned changes ---"
    echo "Server ${SERVER_PARAM}:"
    echo "  Value: ${SERVER_VALUE}"
    echo ""
    echo "Client ${CLIENT_PARAM}:"
    echo "  Value: ${KEY:0:8}..."
    echo ""

    if [[ "$APPLY" != "true" ]]; then
        echo "DRY RUN — pass --apply to create/update parameters"
        exit 0
    fi

    echo "Applying..."
    echo ""

    put_ssm_param "$SERVER_PARAM" "$SERVER_VALUE" "GraphQL org1 API keys (key:client-name format)"
    echo "  Created/updated: ${SERVER_PARAM}"

    put_ssm_param "$CLIENT_PARAM" "$KEY" "GraphQL API key for ${CLIENT_SERVICE_NAME}"
    echo "  Created/updated: ${CLIENT_PARAM}"

    echo ""
    echo "Done. Redeploy affected services to pick up the new keys:"
    echo "  ./aws-deploy.sh -s ${ENV} --only-stack ${ENV}-lif-semantic-search"
    echo "  ./aws-deploy.sh -s ${ENV} --only-stack ${ENV}-lif-graphql-org1"
}

# ----------- Main -----------

if [[ -n "$WORKSHOP_COUNT" ]]; then
    run_workshop_mode
else
    run_service_mode
fi
