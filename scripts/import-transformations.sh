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
#   AWS_PROFILE=lif ./scripts/import-transformations.sh dev --schema tenant_lif_team
#
# Options:
#   --dry-run          List what would be imported, and stop. Needs no AWS access.
#   --schema <name>    Import into that tenant schema instead of the default (`public`). The script
#                      sends it as X-API-Tenant-Schema, which the MDR honors for a service key.
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

USAGE="usage: $0 <env> [--dry-run] [--schema <tenant_schema>]   (env = dev|demo)"
ENV_NAME="${1:?${USAGE}}"
shift
DRY_RUN=""
SCHEMA=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    --schema)  [[ $# -ge 2 ]] || { echo "${USAGE}" >&2; exit 2; }; SCHEMA="$2"; shift 2 ;;
    *)         echo "${USAGE}" >&2; exit 2 ;;
  esac
done
if [[ -n "${SCHEMA}" && ! "${SCHEMA}" =~ ^tenant_[a-z][a-z0-9_]*$ ]]; then
  echo "--schema must name a tenant schema (tenant_...), got: ${SCHEMA}" >&2
  exit 2
fi
AWS_PROFILE="${AWS_PROFILE:-lif}"
AWS_REGION="${AWS_REGION:-us-east-1}"

MDR_URL="https://mdr-api.${ENV_NAME}.lif.unicon.net"
KEY_PARAM="/${ENV_NAME}/learner-data-export-api/MdrApiKey"
XFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../reference_data/transformations" && pwd)"

echo "Env:        ${ENV_NAME}"
echo "MDR:        ${MDR_URL}"
echo "Schema:     ${SCHEMA:-public (default)}"
echo "Transforms: ${XFORM_DIR}"

command -v jq > /dev/null || { echo "jq is required" >&2; exit 1; }

# Exit status: 0 = portable, 1 = valid JSON in another format, 2 = jq can't read the file.
is_portable() {
  local rc=0
  jq -e '.Format.Type == "lif-mdr-mapping-group"' "$1" > /dev/null 2>&1 || rc=$?
  if (( rc > 1 )); then return 2; fi
  return "${rc}"
}

if [[ "${DRY_RUN}" == "--dry-run" ]]; then
  echo "[DRY RUN] would import:"
  for f in "${XFORM_DIR}"/*.json; do
    rc=0; is_portable "$f" || rc=$?
    case "${rc}" in
      0) echo "  - $(basename "$f")" ;;
      1) echo "  - $(basename "$f") (skip: old format)" ;;
      *) echo "  - $(basename "$f") (error: not valid JSON)" ;;
    esac
  done
  exit 0
fi

KEY=$(AWS_PROFILE="${AWS_PROFILE}" AWS_REGION="${AWS_REGION}" \
  aws ssm get-parameter --name "${KEY_PARAM}" --with-decryption --query Parameter.Value --output text)

headers=(-H "X-API-Key: ${KEY}" -H "Content-Type: application/json")
if [[ -n "${SCHEMA}" ]]; then headers+=(-H "X-API-Tenant-Schema: ${SCHEMA}"); fi

fail=0
body=$(mktemp)
trap 'rm -f "${body}"' EXIT
for f in "${XFORM_DIR}"/*.json; do
  name=$(basename "$f")
  rc=0; is_portable "$f" || rc=$?
  if (( rc == 1 )); then
    echo "  ${name} -> skipped: old format, see reference_data/transformations/README.md"
    continue
  elif (( rc > 1 )); then
    echo "  ${name} -> error: not valid JSON"; fail=1
    continue
  fi
  # A curl failure (timeout, DNS, TLS) reports as HTTP 000 instead of ending the run under set -e.
  : > "${body}"
  code=$(curl -s -o "${body}" -w "%{http_code}" -m 60 -X POST "${headers[@]}" \
    --data @"$f" "${MDR_URL}/portable/mapping_groups") || code=000
  case "${code}" in
    201) echo "  ${name} -> imported, group $(jq -r '.Id' "${body}")" ;;
    409) echo "  ${name} -> already installed ($(jq -r 'if (.detail | type) == "array" then [.detail[].code] | unique | join(", ") else .detail end' "${body}" 2> /dev/null))" ;;
    *)   echo "  ${name} -> HTTP ${code}: $(cat "${body}")"; fail=1 ;;
  esac
done

exit "${fail}"
