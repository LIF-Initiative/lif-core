# `resources/` — Bundled OpenAPI schema

Ships the most recent known-good LIF OpenAPI schema as a static file. Used by [`mdr_client`](../) when `USE_OPENAPI_DATA_MODEL_FROM_FILE=true` (dev only) or when MDR is unreachable in deliberately-offline test setups.

## Files

| File | Purpose |
|---|---|
| `openapi_constrained_with_interactions.json` | Snapshot of the LIF V1.1 OpenAPI schema with interaction-mode constraints applied |

Kept in sync with MDR's V1.1 baseline; not the source of truth. Production services should always load schema from MDR, not from this file — see CLAUDE.md § "Schema Loading Pattern" for the no-silent-fallback policy.
