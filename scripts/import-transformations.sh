#!/usr/bin/env bash
#
# Import the versioned LIF transformation definitions into an environment's MDR.
#
# Loads every reference_data/transformations/*.json into the target env's MDR via
# POST /transformation_groups/ (the same portable /export -> POST flow the API's
# import/export uses). This is the tracked, reproducible replacement for creating
# transforms by hand in the MDR UI.
#
# Usage:
#   AWS_PROFILE=lif ./scripts/import-transformations.sh <env>        # e.g. dev | demo
#   AWS_PROFILE=lif ./scripts/import-transformations.sh dev --dry-run
#
# Prereqs / caveats:
#   - The env's MDR must already have the source + target DataModels the transforms
#     reference (by name/id) — this loads transformation GROUPS, not the models.
#   - NOT idempotent: each run creates new groups. To refresh, soft-delete the old
#     groups first (DELETE /transformation_groups/{id}) or you'll get duplicates.
#   - The MDR service key is read from SSM at runtime; never hard-coded.
#
set -euo pipefail

ENV_NAME="${1:?usage: $0 <env> [--dry-run]   (env = dev|demo)}"
DRY_RUN="${2:-}"
AWS_PROFILE="${AWS_PROFILE:-lif}"
AWS_REGION="${AWS_REGION:-us-east-1}"

MDR_URL="https://mdr-api.${ENV_NAME}.lif.unicon.net"
KEY_PARAM="/${ENV_NAME}/learner-data-export-api/MdrApiKey"
XFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../reference_data/transformations" && pwd)"

echo "Env:        ${ENV_NAME}"
echo "MDR:        ${MDR_URL}"
echo "Transforms: ${XFORM_DIR}"

if [[ "${DRY_RUN}" == "--dry-run" ]]; then
  echo "[DRY RUN] would import:"
  for f in "${XFORM_DIR}"/*.json; do echo "  - $(basename "$f")"; done
  exit 0
fi

KEY=$(AWS_PROFILE="${AWS_PROFILE}" AWS_REGION="${AWS_REGION}" \
  aws ssm get-parameter --name "${KEY_PARAM}" --with-decryption --query Parameter.Value --output text)

fail=0
for f in "${XFORM_DIR}"/*.json; do
  name=$(basename "$f")
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 60 -X POST \
    -H "X-API-Key: ${KEY}" -H "Content-Type: application/json" \
    --data @"$f" "${MDR_URL}/transformation_groups/")
  echo "  ${name} -> HTTP ${code}"
  [[ "${code}" =~ ^20 ]] || fail=1
done

exit "${fail}"
