#!/bin/bash
export AWS_REGION=$USE_AWS_REGION
export AWS_DEFAULT_REGION=$USE_AWS_REGION

function error() {
    ERROR="{\"errorMessage\" : \"$1\", \"errorType\" : \"InvalidFunctionException\"}"
    ERROR_URL=http://${AWS_LAMBDA_RUNTIME_API}/2018-06-01/runtime/init/error
    echo "error url is $ERROR_URL"
    curl -X POST "http://${AWS_LAMBDA_RUNTIME_API}/2018-06-01/runtime/init/error" -d "$ERROR" --header "Lambda-Runtime-Function-Error-Type: Unhandled"
    exit
}
function respond() {
    RESPONSE_URL="http://${AWS_LAMBDA_RUNTIME_API}/2018-06-01/runtime/invocation/$1/response"
    echo "response url is $RESPONSE_URL"
    curl -X POST "$RESPONSE_URL" -d "{}"
}

set -e
echo "Retreiving input from http://${AWS_LAMBDA_RUNTIME_API}/2018-06-01/runtime/invocation/next"
INPUT_URL=http://${AWS_LAMBDA_RUNTIME_API}/2018-06-01/runtime/invocation/next
INPUT=$(curl -D /tmp/headers.txt $INPUT_URL)
echo "Received input: $INPUT"
REQUEST_ID=$(cat /tmp/headers.txt | grep 'Lambda-Runtime-Aws-Request-Id' | sed -n 's/^.*: \([[:alnum:]-]*\).*/\1/p')
REQUEST_TYPE=$(echo $INPUT | jq -r '.RequestType')
set +e

if [ $REQUEST_TYPE == "Delete" ]
then
    respond $REQUEST_ID
fi
SECRET=$(aws secretsmanager get-secret-value --secret-id $MASTER_SECRET_ARN --version-stage AWSCURRENT --query 'SecretString' --output text) || error 'failed to retrieve master secret'
export FLYWAY_USER=$(echo $SECRET | jq -r '.username') || error 'failed to retrieve master secret username'
export FLYWAY_PASSWORD=$(echo $SECRET | jq -r '.password') || error 'failed to retrieve master secret password'

if [ $REQUEST_TYPE == "Reset" ]
then
    export FLYWAY_CLEAN_DISABLED=false
    flyway clean -X || error "failed to successfully execute 'flyway clean' command"
fi
flyway info -X || error "flyway info before migrate command"
# Repair before migrate: aligns schema_history checksums + descriptions
# with the current migration files, and clears records for failed migrations
# so they can be retried. Repair does NOT touch user data — only the Flyway
# bookkeeping table. Idempotent + a no-op when checksums already match, so
# it's safe to leave in the steady-state path.
flyway repair -X || error "failed to successfully execute 'flyway repair' command"
flyway migrate -X || error "failed to successfully execute 'flyway migrate' command"
flyway info -X || error "flyway info after migrate command"
respond $REQUEST_ID
