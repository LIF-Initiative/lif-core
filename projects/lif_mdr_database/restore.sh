#!/bin/bash
echo "Waiting for Postgres ( $POSTGRES_HOST:$POSTGRES_PORT@$POSTGRES_USER for database $POSTGRES_DB ) to be ready..."
until pg_isready --host=$POSTGRES_HOST --port=$POSTGRES_PORT --username=$POSTGRES_USER --dbname=$POSTGRES_DB; do
sleep 2
done
echo "Restoring SQL backup to $POSTGRES_HOST:$POSTGRES_PORT@$POSTGRES_USER for database $POSTGRES_DB..."
psql --host=$POSTGRES_HOST --port=$POSTGRES_PORT --username=$POSTGRES_USER --dbname=$POSTGRES_DB -f /backup.sql
echo 'SQL Backup restored successfully!'

# Apply incremental Flyway migrations (V1.2+) on top of the baseline.
# backup.sql is a pg_dump snapshot of V1.1's content, so V1.1 is skipped
# here to avoid re-running it. The migrations directory is mounted read-only
# by docker-compose from sam/mdr-database/flyway/flyway-files/flyway/sql/mdr.
# Every V1.2+ migration added to that directory will automatically apply to
# local dev — no edits to this script needed per migration.
MIGRATIONS_DIR=/flyway-migrations
if [ -d "$MIGRATIONS_DIR" ]; then
    for sql in $(ls "$MIGRATIONS_DIR"/V1.*.sql 2>/dev/null | sort); do
        name=$(basename "$sql")
        case "$name" in
            V1.1__*) continue ;;
        esac
        echo "Applying Flyway migration: $name"
        psql --host=$POSTGRES_HOST --port=$POSTGRES_PORT --username=$POSTGRES_USER --dbname=$POSTGRES_DB -f "$sql"
    done
fi
# echo 'Waiting for Postgres to be ready...'
# until pg_isready --host=$POSTGRES_HOST --username=$POSTGRES_USER --dbname=$POSTGRES_DB; do
#   sleep 2
# done
# pg_restore -l /backup.tar
# echo 'Restoring backup...'
# pg_restore --host=$POSTGRES_HOST --username=$POSTGRES_USER --dbname=$POSTGRES_DB --clean -F c /backup.tar
# echo 'Backup restored successfully!'
