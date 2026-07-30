-- Issue #1033: DeveloperApiKeys — user-owned API keys for programmatic access to the LDE /exports API.
--
-- Keys are minted / listed / revoked via the MDR API (Cognito-authed) and stored HASHED
-- (the raw key is returned to the caller exactly once, never persisted). A key is scoped to a
-- workspace by living in that tenant's schema (request-time search_path), and to a user by OwnerSub
-- (the Cognito `sub`).
--
-- Idempotent per the CLAUDE.md "MDR Schema Migrations (V1.2+)" convention (safe to replay).
--   1. Create the table in `public` so future clone_lif_schema() runs copy it into new tenant
--      schemas automatically (clone_lif_schema copies every public table via LIKE ... INCLUDING ALL).
--   2. Back-fill tenant schemas already provisioned before this table existed (e.g. tenant_lif_team) —
--      clone_lif_schema already ran for them, so they won't retroactively get the new table.

CREATE TABLE IF NOT EXISTS public."DeveloperApiKeys" (
    "Id"             integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "OwnerSub"       varchar     NOT NULL,
    "Label"          varchar     NOT NULL,
    "KeyPrefix"      varchar     NOT NULL,
    "KeyHash"        varchar     NOT NULL,
    "CreationDate"   timestamptz NOT NULL DEFAULT now(),
    "LastUsedDate"   timestamptz,
    "RevokedDate"    timestamptz,
    "ExpirationDate" timestamptz
);

CREATE INDEX IF NOT EXISTS "ix_DeveloperApiKeys_OwnerSub" ON public."DeveloperApiKeys" ("OwnerSub");
CREATE INDEX IF NOT EXISTS "ix_DeveloperApiKeys_KeyHash"  ON public."DeveloperApiKeys" ("KeyHash");

-- Back-fill existing tenant_* schemas (cloned before this table existed).
DO $$
DECLARE
    schema_name text;
BEGIN
    FOR schema_name IN SELECT nspname FROM pg_namespace WHERE nspname ~ '^tenant_'
    LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I."DeveloperApiKeys" (LIKE public."DeveloperApiKeys" INCLUDING ALL)',
            schema_name
        );
    END LOOP;
END $$;
