# nuq-postgres pg_cron bootstrap pitfall

## Symptom

During first boot of `firecrawl-nuq-postgres-1`, the container exits and the logs show:

```
2026-06-21 18:18:24.187 UTC [48] ERROR:  can only create extension in database postgres
2026-06-21 18:18:24.187 UTC [48] DETAIL:  Jobs must be scheduled from the database configured in cron.database_name,
           since the pg_cron background worker reads job descriptions from this database.
2026-06-21 18:18:24.187 UTC [48] HINT:   Add cron.database_name = 'firecrawl' in postgresql.conf to use the current database.
2026-06-21 18:18:24.187 UTC [48] STATEMENT: CREATE EXTENSION IF NOT EXISTS pg_cron;
```

## Root cause

The Firecrawl `nuq-postgres` image contains an initialization script at
`/docker-entrypoint-initdb.d/010-nuq.sql`. The first two statements are:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_cron;
```

The init script runs as the `postgres` user, connected to the database named by
`POSTGRES_DB`. When `POSTGRES_DB=firecrawl`, the `CREATE EXTENSION pg_cron;`
statement is executed against the `firecrawl` database. However, pg_cron has a
restriction: the extension must be created in the database configured by the
`cron.database_name` GUC. On the first server start, that parameter defaults to
`postgres`. The `ALTER SYSTEM SET cron.database_name = 'firecrawl'` must take
effect *before* the server starts, otherwise `CREATE EXTENSION pg_cron;` in the
`firecrawl` database fails.

A further complication: the official Postgres Docker image ships with
`include_dir = 'conf.d'` commented out in `postgresql.conf`, so dropping a
`conf.d/*.conf` file alone is insufficient. The parameter must be explicitly
enabled in `postgresql.conf`.

## Fix

Use a custom entrypoint wrapper (see `templates/nuq-postgres-entrypoint.sh`) that:

1. Sources the upstream `/usr/local/bin/docker-entrypoint.sh` functions.
2. Detects the first-time-initialization path (`PG_VERSION` absent).
3. Switches to the `postgres` user when running as root, because `initdb` refuses
to run as root.
4. Calls `docker_init_database_dir` to create the cluster.
5. Enables `include_dir = 'conf.d'` in `postgresql.conf` if it is not already enabled.
6. Writes `cron.database_name = '${POSTGRES_DB}'` to
   `${PGDATA}/conf.d/zz-firecrawl-cron.conf`.
7. Continues the normal upstream flow: `pg_setup_hba_conf`, temporary server
   start, optional `CREATE DATABASE`, init scripts, temporary server stop.

Because `cron.database_name` is now configured before the temporary init server
starts, the bundled `010-nuq.sql` successfully creates `pg_cron` in the
`firecrawl` database.

## How to verify the fix worked

After the stack starts:

```bash
docker exec -it firecrawl-nuq-postgres-1 psql -U firecrawl -d firecrawl -c "\dx" | grep -E 'pgcrypto|pg_cron'
```

Both extensions should appear under the `firecrawl` database.

## Historical context

- PostgreSQL version in image at time of workaround: 17.9 (Debian build).
- Firecrawl image tag tested: `ghcr.io/firecrawl/nuq-postgres:latest` (digest
  varied, pulled 2026-06-21).
- The issue only reproduces on first boot when `POSTGRES_DB` is set to a value
  other than `postgres`. With `POSTGRES_DB=postgres`, the bundled init script
  succeeds without the workaround.
