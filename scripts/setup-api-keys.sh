#!/usr/bin/env bash
#
# setup-api-keys.sh — Generate/manage inbound API keys for a LIF service in AWS SSM.
#
# Service-agnostic generalization of the GraphQL temporary-key flow. Writes a
# "key:label" CSV to /<env>/<service>/ApiKeys (SecureString), which the service's
# task definition injects as <PREFIX>__API_KEYS for the api_key_auth middleware.
#
# Existing entries whose label matches the prefix are replaced; other entries are
# preserved (so service keys and prior batches survive). The raw keys are printed
# to stdout for one-time distribution to downstream/integrator callers.
#
# Run with --help for usage details.

set -euo pipefail

# ----------- Argument parsing -----------

SERVICE="${1:-}"
ENV="${2:-}"
APPLY=false
TEMPORARY_COUNT=""
TEMPORARY_PREFIX="temporary"

usage() {
    echo "Usage: $0 <service> <env> --temporary <count> [options]"
    echo ""
    echo "Generate/manage inbound API keys for a LIF service in AWS SSM Parameter Store."
    echo ""
    echo "  <service>            ECS service / SSM namespace (e.g. learner-data-export-api, graphql-org1)"
    echo "  <env>                Environment name (e.g. dev, demo)"
    echo "  --temporary <count>  Generate <count> keys (0 removes all keys with the given prefix)"
    echo "  --prefix <label>     Label prefix for generated keys (default: temporary)"
    echo "  --apply              Actually create/update the SSM parameter (default: preview only)"
    echo "  --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "    $0 learner-data-export-api dev --temporary 5 --apply         # 5 keys for LDE dev"
    echo "    $0 learner-data-export-api demo --temporary 10 --prefix integrator --apply"
    echo "    $0 learner-data-export-api demo --temporary 0 --apply        # remove all 'temporary-*' keys"
    echo ""
    echo "After applying, redeploy the service to pick up the new keys:"
    echo "    ./aws-deploy.sh -s <env> --only-stack <env>-lif-<service>"
}

if [[ -z "$SERVICE" || "$SERVICE" == "--help" || "$SERVICE" == "-h" ]]; then
    usage
    exit "${SERVICE:+1}"
fi

if [[ -z "$ENV" || "$ENV" == --* ]]; then
    echo "Error: <env> is required as the second argument" >&2
    echo "" >&2
    usage
    exit 1
fi

shift 2
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
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$TEMPORARY_COUNT" ]]; then
    echo "Error: --temporary <count> is required" >&2
    echo "" >&2
    usage
    exit 1
fi

if ! [[ "$TEMPORARY_COUNT" =~ ^[0-9]+$ ]]; then
    echo "Error: --temporary expects a non-negative integer, got: $TEMPORARY_COUNT" >&2
    exit 1
fi

# ----------- SSM parameter path -----------

SERVER_PARAM="/${ENV}/${SERVICE}/ApiKeys"

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

# ----------- Main -----------

echo "=== API Key Generation: ${SERVICE} (${ENV}) ==="
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
        echo "Existing ApiKeys found — replacing any '${TEMPORARY_PREFIX}-*' entries (others preserved)"
    else
        SERVER_VALUE="${FILTERED_VALUE}"
        echo "Existing ApiKeys found — removing all '${TEMPORARY_PREFIX}-*' entries (others preserved)"
    fi
else
    SERVER_VALUE="${NEW_ENTRIES}"
    if [[ -n "$NEW_ENTRIES" ]]; then
        echo "No existing ApiKeys — will create with the generated entries"
    else
        echo "No existing ApiKeys and nothing to remove"
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
    echo "  ${SERVER_PARAM}: ${TEMPORARY_COUNT} '${TEMPORARY_PREFIX}-*' entries (+ any preserved entries)"
else
    echo "  ${SERVER_PARAM}: removing all '${TEMPORARY_PREFIX}-*' entries"
fi

if [[ "$APPLY" != "true" ]]; then
    echo ""
    echo "DRY RUN — pass --apply to create/update the parameter"
    exit 0
fi

echo ""
echo "Applying..."
put_ssm_param "$SERVER_PARAM" "$SERVER_VALUE" "${SERVICE} inbound API keys (key:label format)"
echo "  Created/updated: ${SERVER_PARAM}"

echo ""
echo "Done. Redeploy ${SERVICE} to pick up the new keys:"
echo "  ./aws-deploy.sh -s ${ENV} --only-stack ${ENV}-lif-${SERVICE}"

if [[ "$TEMPORARY_COUNT" -gt 0 ]]; then
    echo ""
    echo "=== Keys for distribution (store securely; shown once) ==="
    for i in $(seq 0 $((TEMPORARY_COUNT - 1))); do
        echo "${TEMPORARY_KEYS[$i]}"
    done
fi
