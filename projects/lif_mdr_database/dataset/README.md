# `dataset/` — MDR database seed/init

Legacy initialization SQL for the MDR Postgres database. Loaded once when the database is first brought up; subsequent schema changes flow through Flyway migrations under [`../../../sam/mdr-database/flyway/`](../../../sam/mdr-database/flyway/).

## Files

| File | Purpose |
|---|---|
| `init.sql` | Drops + recreates Postgres types and the V1.0 baseline schema. Effectively the "pre-Flyway" starting point. |

## When this runs

- **Local docker-compose:** `restore.sh` loads `backup.sql` first (a pg_dump snapshot of the V1.1 content), then applies every `V1.*.sql` migration via `psql`. `init.sql` is not used directly by the compose flow.
- **Deployed envs (dev/demo):** Flyway manages the schema from V1.1 onward; `init.sql` is not used in deployed environments.

See [`../README.md`](../README.md) for the broader database-management story including the Flyway flow and the idempotent-migration convention.
