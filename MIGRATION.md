<!-- markdownlint-disable MD024 MD036 -->

# Migration Guide

This document provides step-by-step instructions for upgrading between versions
of lif-core when breaking changes are introduced.

## Overview

Breaking changes are modifications that require action from users to maintain
compatibility. This includes:

- Database schema changes that require migrations
- API endpoint changes (removed, renamed, or modified parameters)
- Configuration format changes
- Dependency version requirements
- Changes to expected input/output formats

## How to Use This Guide

1. Identify your current version
2. Read all migration sections between your current version and target version
3. Follow the steps in order
4. Test thoroughly in a non-production environment first

---

## Upcoming Changes (Unreleased)

### Breaking Changes

#### Identity Mapper: three key columns narrowed from 255 to 191 characters

- **Action Required:** a local docker-compose MariaDB volume keeps the old schema, because
  `02-ddl.sql` only runs on an empty datadir. Either recreate the volumes
  (`docker compose -f deployments/advisor-demo-docker/docker-compose.yml down -v`) or apply the
  change in place, which keeps existing rows and is safe to re-run:

  ```sql
  ALTER TABLE identity_mappings
    MODIFY lif_organization_id        VARCHAR(191) NOT NULL,
    MODIFY lif_organization_person_id VARCHAR(191) NOT NULL,
    MODIFY target_system_id           VARCHAR(191) NOT NULL,
    DROP INDEX IF EXISTS idx_org_person;
  ```

  dev and demo need nothing: their MariaDB datadir is ephemeral, so every task start replays the
  new DDL.
- **Impact:** a mapping whose `lif_organization_id`, `lif_organization_person_id` or
  `target_system_id` is longer than 191 characters is now rejected (previously 255). No value in
  the repo's sample data is longer than 22.
- **Related:** #1258, CHANGELOG.md "Changed", `docs/design/components/identity-mapper.md`

#### GraphQL: a Query Planner failure is now a GraphQL error, not an empty result

- **Action Required:** callers of the GraphQL API must read the `errors` entry in the response
  to detect a backend failure. Code that treats an empty list as the only possible "no results"
  outcome keeps working; code that relied on a failure *also* arriving as an empty list will now
  see `data` null for the queried field plus an `errors` entry.
- **Impact:** any GraphQL consumer. In this repo that is the semantic search MCP server (via
  `graphql_client`) and the `lif-to-lif` adapter, which already checks `errors` and will now
  raise when an upstream org's planner fails instead of contributing empty fragments. Learner
  Data Export is unaffected — it calls the Query Planner directly.
- **Related:** #1264, CHANGELOG.md "Changed", `bases/lif/api_graphql/README.md` → Error contract

#### Auth: one `lif.auth` brick; secrets and MDR service keys have no defaults

- **Action Required:**
  1. Set `MDR__AUTH__JWT_SECRET_KEY` to a strong secret. It previously defaulted to `change4`, and
     MDR now refuses to start without it. Local docker-compose won't even parse without it: copy
     the value line from `deployments/advisor-demo-docker/.env.example` into your `.env`. In AWS it
     comes from `/{env}/mdr-api/MdrAuthJwtSecretKey`. No script creates it; see
     `docs/operations/guides/auth-configuration.md` → Creating secrets without a script.
  2. Make sure no signing secret (`SECRET_KEY` for the Advisor, `MDR__AUTH__JWT_SECRET_KEY` for MDR)
     is a value published in this repo (`changeme`, `changeme1`–`6`, `change4`, `replace`, …).
     Those now stop the service at import, with an error naming the variable.
  3. Set `API_TOKEN` for the Example Data Source API. An unset token now stops it at startup,
     instead of making it reject every request.
  4. Set each `MDR__AUTH__SERVICE_API_KEY__*` that a caller in your deployment uses. The
     `changeme1`–`6` code defaults are gone, and an unset key is simply not accepted (a startup
     warning names it). Local compose still supplies the `changeme*` values. In AWS,
     `scripts/setup-mdr-api-keys.sh <env> --apply` writes each server key and its client copy.
  5. Run the read-only SSM check in `docs/operations/guides/auth-configuration.md` for each
     environment before deploying.
- **Impact:**
  - MDR rejects an unknown `X-API-Key` with 401, even if a valid Bearer token is also sent. It
    previously fell through to the Bearer token.
  - Response changes:
    - MDR with no credentials: `{"detail": "Missing or invalid credentials"}` (was
      `Authentication required: …`).
    - Advisor with a missing token: 401 instead of 403.
  - Code importing `lif.api_key_auth`, `lif.api_token_auth`, `lif.cognito_auth`,
    `lif.auth.core`, or MDR's `create_access_token` / `create_refresh_token` / `decode_jwt` /
    `AuthMiddleware` must move to `lif.auth` (middleware, strategies) and `lif.auth.jwt`
    (`JwtConfig`, `mint_access`, `mint_refresh`, `verify`). MDR bases use
    `lif.mdr_auth.add_mdr_auth(app)`.
- **Related:** #548, CHANGELOG.md "Changed" / "Removed" / "Security", ADR 0007
  (`docs/design/adr/general/0007-single-auth-brick-with-provider-adapters.md`),
  `docs/operations/guides/auth-configuration.md`

### Deprecation Notices

*No deprecations currently pending*

---

## Version History

### Version X.Y.Z (YYYY-MM-DD)

**Breaking Changes:**

- Description of breaking change
- **Action Required:** Step-by-step migration instructions
- **Impact:** Who is affected and how
- **Related:** Link to CHANGELOG.md entry, relevant issue, or documentation

**Example:**

### Version 1.2.0 (2025-01-15)

**Breaking Changes:**

#### Database: Added required `user_role` column to users table

- **Action Required:**
  1. Run migration script: `python scripts/migrate.py --version 1.2.0`
  2. Update any code that inserts users to include `user_role` parameter
- **Impact:** All deployments with existing user data
- **Related:** [CHANGELOG.md](CHANGELOG.md#120---2025-01-15), Issue #123

#### API: Removed deprecated `/v1/learner` endpoint

- **Action Required:**
  1. Update all client code to use `/v2/learner` instead
  2. Note: `/v2/learner` returns data in a different format (see API docs)
- **Impact:** Any external systems calling the v1 endpoint
- **Related:** [API Documentation](docs/api/learner-v2.md)

#### Configuration: Changed environment variable naming convention

- **Action Required:**
  1. Rename `LIF_DB_HOST` → `LIF_DATABASE_HOST`
  2. Rename `LIF_DB_PORT` → `LIF_DATABASE_PORT`
  3. Update all deployment configurations and docker-compose files
- **Impact:** All deployment configurations
- **Related:** [Configuration Guide](docs/configuration.md)

---

## Need Help?

If you encounter issues during migration:

1. Check the [CHANGELOG.md](CHANGELOG.md) for additional context
2. Review relevant documentation in the [/docs](docs/) directory
3. Search existing [GitHub Discussions](https://github.com/lif-initiative/lif-core/discussions)
4. Open a new discussion with the `migration` label if applicable
5. Search existing [GitHub Issues](https://github.com/lif-initiative/lif-core/issues)
6. Open a new issue with the `migration` label if needed
