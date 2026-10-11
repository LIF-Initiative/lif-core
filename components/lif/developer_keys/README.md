# developer_keys

Issuance, listing and revocation of **developer API keys**: user-owned keys for programmatic
access to the Learner Data Export `/exports` API (#1033). Extracted from the MDR-domain bricks in
#1180 so the control plane (EPIC #1041, ADR 0002) can package it without inheriting the MDR
domain.

## Public surface

- `create_developer_api_key(session, owner_sub, data)` — generates a `lifk_` key, stores only its
  SHA-256 hash and a display prefix, and returns the raw key exactly once.
- `list_developer_api_keys(session, owner_sub)` — the owner's keys, never the raw key.
- `revoke_developer_api_key(session, owner_sub, key_id)` — soft revoke (`RevokedDate`); 404 when
  the key isn't the caller's, so other users' key ids aren't revealed.
- `DeveloperApiKey` — the SQLModel table (`DeveloperApiKeys`, created by the MDR Flyway migration
  `V1.5__developer_api_keys.sql`).
- `CreateDeveloperApiKeyDTO`, `DeveloperApiKeyDTO`, `CreatedDeveloperApiKeyDTO` — request and
  response models.

## Scoping

Keys are scoped to a user by `OwnerSub` (the Cognito `sub`). **Workspace scoping is the host's
job**: the functions run against whatever the caller's `AsyncSession` is scoped to. Today the only
host is MDR, which reaches the table in the request's tenant schema via `search_path`. ADR 0006
moves keys to a single workspace-scoped table in the control plane's own database (#1183).

The brick imports nothing from `mdr_dto`, `mdr_services`, `mdr_utils` or `mdr_auth`
(`test/components/lif/developer_keys/test_brick_imports.py`). It does depend on FastAPI, because
revocation raises `HTTPException(404)`, as MDR's services do.

## Consumers

- `bases/lif/mdr_restapi/developer_api_key_endpoints.py` — the `/api-keys` routes (MDR is the
  interim host).
