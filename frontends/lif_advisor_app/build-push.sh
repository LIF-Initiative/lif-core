#!/bin/bash
# Build and push the LIF Advisor App image for a target environment.
#
# The advisor-app is a Vite SPA: its API base URL (VITE_LIF_ADVISOR_API_URL) is
# baked into the JS bundle at BUILD time (see Dockerfile), so the image is
# environment-specific and CANNOT be promoted dev->demo like the backend
# services. Build a dedicated image per environment with this script.
#
# CI (.github/workflows/lif_advisor_app.yml) builds the dev image automatically.
# The dev CI role can push only to lif/dev/*, so the demo image must be built
# here with admin/SSO creds during the manual demo promotion.
#
# Usage:
#   ./build-push.sh <dev|demo> [tag]
#
# Then point cloudformation/<env>-lif-advisor-app.params ImageUrl at the pushed
# tag and run aws-deploy for the <env> advisor-app stack.

set -euo pipefail

ENVIRONMENT="${1:?usage: build-push.sh <dev|demo> [tag]}"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT="${AWS_ACCOUNT_ID:-381492161417}"
GA_MEASUREMENT_ID="${GA_MEASUREMENT_ID:-G-WCYGBK4XHK}"

case "$ENVIRONMENT" in
  dev)  API_URL="https://advisor-api.dev.lif.unicon.net" ;;
  demo) API_URL="https://advisor-api.demo.lif.unicon.net" ;;
  *) echo "unknown environment: $ENVIRONMENT (expected dev|demo)" >&2; exit 1 ;;
esac

REPO="lif/${ENVIRONMENT}/lif_advisor_app"
REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
TAG="${2:-$(date +%Y-%m-%d-%H-%M-%S)-$(git rev-parse --short HEAD)}"

cd "$(dirname "$0")"

echo "Building advisor-app for '${ENVIRONMENT}'"
echo "  API URL : ${API_URL}"
echo "  ECR repo: ${REGISTRY}/${REPO}"
echo "  tag     : ${TAG} (+ :latest)"

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

docker build \
  --platform linux/amd64 \
  --build-arg "LIF_ADVISOR_API_URL=${API_URL}" \
  --build-arg "GA_MEASUREMENT_ID=${GA_MEASUREMENT_ID}" \
  -t "${REGISTRY}/${REPO}:${TAG}" \
  -t "${REGISTRY}/${REPO}:latest" \
  .

docker push "${REGISTRY}/${REPO}:${TAG}"
docker push "${REGISTRY}/${REPO}:latest"

echo
echo "Pushed ${REGISTRY}/${REPO}:${TAG} (+ :latest)"
echo "Next: set cloudformation/${ENVIRONMENT}-lif-advisor-app.params ImageUrl to this tag, then aws-deploy the ${ENVIRONMENT} advisor-app stack."
