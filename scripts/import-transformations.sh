#!/usr/bin/env bash
#
# Import the versioned LIF transformation definitions into an environment's MDR.
#
# Loads every portable mapping group file in reference_data/transformations/*.json into the
# target env's MDR via POST /portable/mapping_groups (#1408, #1511). A portable file names each
# mapping's target and sources by path, with no database ids, so it imports into any schema whose
# models have those paths. This is the tracked, reproducible replacement for creating transforms
# by hand in the MDR UI.
#
# Usage:
#   AWS_PROFILE=lif ./scripts/import-transformations.sh <env>        # e.g. dev | demo
#   AWS_PROFILE=lif ./scripts/import-transformations.sh dev --dry-run
#
# Prereqs / caveats:
#   - The env's MDR must already have the source + target DataModels each file names (by Name,
#     Version and ContributorOrganization) — this loads mapping GROUPS, not the models.
#   - Safe to re-run: a group that is already installed is refused with 409 (GROUP_EXISTS)
#     and reported as such.
#   - An imported group arrives inactive (#1350); activate it in the MDR to use it.
#   - Files still in the old /transformation_groups/ format are skipped. The README in
#     reference_data/transformations/ says how to load them by hand.
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

command -v jq > /dev/null || { echo "jq is required" >&2; exit 1; }

is_portable() {
  jq -e '.Format.Type == "lif-mdr-mapping-group"' "$1" > /dev/null
}

if [[ "${DRY_RUN}" == "--dry-run" ]]; then
  echo "[DRY RUN] would import:"
  for f in "${XFORM_DIR}"/*.json; do
    if is_portable "$f"; then echo "  - $(basename "$f")"; else echo "  - $(basename "$f") (skip: old format)"; fi
  done
  exit 0
fi

KEY=$(AWS_PROFILE="${AWS_PROFILE}" AWS_REGION="${AWS_REGION}" \
  aws ssm get-parameter --name "${KEY_PARAM}" --with-decryption --query Parameter.Value --output text)

fail=0
body=$(mktemp)
trap 'rm -f "${body}"' EXIT
for f in "${XFORM_DIR}"/*.json; do
  name=$(basename "$f")
  if ! is_portable "$f"; then
    echo "  ${name} -> skipped: old format, see reference_data/transformations/README.md"
    continue
  fi
  code=$(curl -s -o "${body}" -w "%{http_code}" -m 60 -X POST \
    -H "X-API-Key: ${KEY}" -H "Content-Type: application/json" \
    --data @"$f" "${MDR_URL}/portable/mapping_groups")
  case "${code}" in
    201) echo "  ${name} -> imported, group $(jq -r '.Id' "${body}")" ;;
    409) echo "  ${name} -> already installed" ;;
    *)   echo "  ${name} -> HTTP ${code}: $(cat "${body}")"; fail=1 ;;
  esac
done

exit "${fail}"
