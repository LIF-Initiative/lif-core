#!/usr/bin/env bash
#
# setup-graphql-api-keys.sh — Manage GraphQL org1 API keys in AWS SSM Parameter Store
#
# Run with --help for usage details.

set -euo pipefail

# ----------- Configuration -----------

GRAPHQL_SERVICE_NAME="graphql-org1"
CLIENT_SERVICE_NAME="semantic-search"
CLIENT_LABEL="semantic-search"

# ----------- Argument parsing -----------

ENV="${1:-}"
APPLY=false
TEMPORARY_COUNT=""
TEMPORARY_PREFIX="temporary"

usage() {
    echo "Usage: $0 <env> [options]"
    echo ""
    echo "Manage GraphQL org1 API keys in AWS SSM Parameter Store."
    echo ""
    echo "Modes:"
    echo "  Service mode (default): Sets up the semantic-search service key (server + client SSM params)"
    echo "  Temporary key mode:     Generates temporary keys for external users (server SSM only, keys printed to stdout)"
    echo ""
    echo "  Service mode:"
    echo "    $0 <env> [--apply]"
    echo ""
    echo "  Temporary key mode:"
    echo "    $0 <env> --temporary <count> [--prefix <label>] [--apply]"
    echo ""
    echo "  Options:"
    echo "    <env>                Environment name (e.g., dev, demo)"
    echo "    --apply              Actually create/update SSM parameters (default: preview only)"
    echo "    --temporary <count>  Generate <count> temporary keys for external users"
    echo "    --prefix <label>     Label prefix for temporary keys (default: temporary)"
    echo "    --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "    $0 demo                                              # Preview service key setup"
    echo "    $0 demo --apply                                      # Create/update service key"
    echo "    $0 demo --temporary 10 --apply                       # Generate 10 temporary keys"
    echo "    $0 dev --temporary 5 --prefix attendee --apply       # Generate 5 keys with custom prefix"
    echo "    $0 demo --temporary 0 --apply                        # Remove all temporary keys"
}

if [[ -z "$ENV" || "$ENV" == "--help" || "$ENV" == "-h" ]]; then
    usage
    exit "${ENV:+1}"
fi

shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            APPLY=true
            shift
            ;;
        --temporary)
            TEMPORARY_COUNT="$2"
            shift 2
            ;;
        --prefix)
            TEMPORARY_PREFIX="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
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
    local value
    value=$(aws ssm get-parameter \
        --name "$param_name" \
        --with-decryption \
        --query "Parameter.Value" \
        --output text 2>/dev/null || echo "")
    # Trim whitespace and strip leading/trailing commas
    value=$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^,*//;s/,*$//')
    echo "$value"
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

# Clean a comma-separated value: remove empty entries, leading/trailing commas
clean_csv() {
    echo "$1" | tr ',' '\n' | (sed '/^[[:space:]]*$/d' || true) | tr '\n' ',' | sed 's/,$//'
}

# ----------- Temporary key mode -----------

run_temporary_mode() {
    echo "=== GraphQL Temporary Key Generation ==="
    echo "Environment: ${ENV}"
    echo "Server param: ${SERVER_PARAM}"
    echo "Key count: ${TEMPORARY_COUNT}"
    echo "Label prefix: ${TEMPORARY_PREFIX}"
    echo ""

    existing_server_value=$(get_ssm_param "$SERVER_PARAM")

    # Generate keys
    declare -a TEMPORARY_KEYS
    declare -a TEMPORARY_LABELS
    NEW_ENTRIES=""

    if [[ "$TEMPORARY_COUNT" -gt 0 ]]; then
        for i in $(seq 1 "$TEMPORARY_COUNT"); do
            label="${TEMPORARY_PREFIX}-$(printf '%02d' "$i")"
            key=$(generate_key)
            TEMPORARY_KEYS+=("$key")
            TEMPORARY_LABELS+=("$label")
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
        FILTERED_VALUE=$(echo "$existing_server_value" | tr ',' '\n' | (grep -v ":${TEMPORARY_PREFIX}-" || true) | tr '\n' ',' | sed 's/,$//')
        FILTERED_VALUE=$(clean_csv "$FILTERED_VALUE")
        if [[ -n "$NEW_ENTRIES" ]]; then
            if [[ -n "$FILTERED_VALUE" ]]; then
                SERVER_VALUE="${FILTERED_VALUE},${NEW_ENTRIES}"
            else
                SERVER_VALUE="${NEW_ENTRIES}"
            fi
            echo "Existing server ApiKeys found — replacing any '${TEMPORARY_PREFIX}-*' entries"
        else
            SERVER_VALUE="${FILTERED_VALUE}"
            echo "Existing server ApiKeys found — removing all '${TEMPORARY_PREFIX}-*' entries"
        fi
    else
        SERVER_VALUE="${NEW_ENTRIES}"
        if [[ -n "$NEW_ENTRIES" ]]; then
            echo "No existing server ApiKeys — will create with temporary entries"
        else
            echo "No existing server ApiKeys and nothing to remove"
            exit 0
        fi
    fi

    echo ""
    if [[ "$TEMPORARY_COUNT" -gt 0 ]]; then
        echo "--- Generated keys ---"
        for i in $(seq 0 $((TEMPORARY_COUNT - 1))); do
            printf "  %-20s %s\n" "${TEMPORARY_LABELS[$i]}" "${TEMPORARY_KEYS[$i]}"
        done
    fi

    echo ""
    echo "--- Server param update ---"
    if [[ "$TEMPORARY_COUNT" -gt 0 ]]; then
        echo "  ${SERVER_PARAM}: ${TEMPORARY_COUNT} temporary entries (+ existing service keys)"
    else
        echo "  ${SERVER_PARAM}: removing all temporary entries (service keys preserved)"
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

    if [[ "$TEMPORARY_COUNT" -gt 0 ]]; then
        echo ""
        echo "=== Keys for distribution ==="
        for i in $(seq 0 $((TEMPORARY_COUNT - 1))); do
            echo "${TEMPORARY_KEYS[$i]}"
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
            UPDATED_VALUE=$(echo "$existing_server_value" | tr ',' '\n' | (grep -v ":${CLIENT_LABEL}$" || true) | tr '\n' ',' | sed 's/,$//')
            UPDATED_VALUE=$(clean_csv "$UPDATED_VALUE")
            if [[ -n "$UPDATED_VALUE" ]]; then
                SERVER_VALUE="${UPDATED_VALUE},${NEW_ENTRY}"
            else
                SERVER_VALUE="${NEW_ENTRY}"
            fi
        else
            echo "  Appending new entry for '${CLIENT_LABEL}'"
            SERVER_VALUE=$(clean_csv "${existing_server_value},${NEW_ENTRY}")
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

if [[ -n "$TEMPORARY_COUNT" ]]; then
    run_temporary_mode
else
    run_service_mode
fi
