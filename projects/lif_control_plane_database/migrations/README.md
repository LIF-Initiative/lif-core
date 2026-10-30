# Control-plane database migrations

SQL migrations for the control plane's own database (ADR 0006 decision 1: its own logical
database, login and migration set, separate from MDR's).

There are none yet. The first one, the developer-key table, waits on the workspace and owner
questions in #1190.

**Local compose** mounts this folder as the `lif-control-plane-database` container's
`/docker-entrypoint-initdb.d`, so the Postgres image runs every `*.sql` file here, in file-name
order, when the database is first created. (Other files, like this README, are skipped.) There is no
data volume, so a fresh `up` always starts from these files.

**Dev and demo** (Aurora) don't run these yet. Creating the database and login there, and running
these files against it, is the AWS half of #1182.

Conventions for a new file:
- Name it `V<major>.<minor>__<description>.sql`, and keep the numbers sortable by file name
  (`V1.10` sorts before `V1.2`, so zero-pad if the list gets that long).
- Make it idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE`), as MDR's V1.2+
  migrations are, so it can be re-applied safely.
