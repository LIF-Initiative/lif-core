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

**Workspace-scoped store** (`workspace_store.py`, the control plane's, ADR 0008):

- `create_workspace_developer_api_key(session, workspace, owner_sub, data)`,
  `list_workspace_developer_api_keys(session, workspace, owner_sub)`,
  `revoke_workspace_developer_api_key(session, owner_sub, key_id)`: the same operations against one
  table with an explicit `Workspace` column. Revoking is by owner alone, in any workspace.
- `WorkspaceDeveloperApiKey` — its SQLModel table (`DeveloperApiKeys` in the control plane's own
  database, created by `projects/lif_control_plane_database/migrations/V1.0__developer_api_keys.sql`).
  It's on its own SQLAlchemy registry, so it never shares `SQLModel.metadata` with `DeveloperApiKey`.

## Scoping

Keys are scoped to a user by `OwnerSub` (the Cognito `sub`). For the MDR functions, **workspace
scoping is the host's job**: they run against whatever the caller's `AsyncSession` is scoped to. Today the only
host is MDR, which reaches the table in the request's tenant schema via `search_path`. ADR 0006
moves keys to a single workspace-scoped table in the control plane's own database, which the
workspace-scoped store reads and writes. The workspace is the tenant schema name, an opaque string
(ADR 0008), and checking that the caller belongs to it is still the host's job. Copying MDR's keys
into it is #1183.

The brick imports nothing from `mdr_dto`, `mdr_services`, `mdr_utils` or `mdr_auth`
(`test/components/lif/developer_keys/test_brick_imports.py`). It does depend on FastAPI, because
revocation raises `HTTPException(404)`, as MDR's services do.

## Consumers

- `bases/lif/mdr_restapi/developer_api_key_endpoints.py` — MDR's `/api-keys` routes (MDR is the
  interim host), using the MDR functions.
- `bases/lif/control_plane_restapi/api_key_endpoints.py` — the control plane's `/api-keys` routes,
  using the workspace-scoped store.
