#!/usr/bin/env bash
set -Eeo pipefail

# Firecrawl's nuq-postgres image bundles /docker-entrypoint-initdb.d/010-nuq.sql,
# which creates the pg_cron extension. pg_cron must be created in the database
# configured by cron.database_name. The image also sets POSTGRES_DB to a custom
# value (e.g. 'firecrawl'), so the init script runs in that database and fails
# because cron.database_name defaults to 'postgres'.
#
# This entrypoint enables conf.d includes and sets cron.database_name to the
# application DB before init scripts run, then falls through to the standard
# PostgreSQL startup.

PGCONFIGDIR="${PGDATA:-/var/lib/postgresql/data}"

. /usr/local/bin/docker-entrypoint.sh

configure_pg_cron() {
  if [ -n "${POSTGRES_DB:-}" ] && [ "${POSTGRES_DB:-}" != "postgres" ]; then
    mkdir -p "$PGCONFIGDIR/conf.d"
    cat > "$PGCONFIGDIR/conf.d/zz-firecrawl-cron.conf" <<EOF
# Firecrawl self-host: pg_cron must use the application database
cron.database_name = '${POSTGRES_DB}'
EOF
    if ! grep -qxE "^[[:space:]]*include_dir\s*=\s*['\"]?conf.d['\"]?" "$PGCONFIGDIR/postgresql.conf"; then
      sed -i "s/^[#[:space:]]*include_dir\s*=\s*['\"]conf.d['\"].*/include_dir = 'conf.d'/" "$PGCONFIGDIR/postgresql.conf"
      if ! grep -qxE "^[[:space:]]*include_dir\s*=\s*['\"]?conf.d['\"]?" "$PGCONFIGDIR/postgresql.conf"; then
        echo "include_dir = 'conf.d'" >> "$PGCONFIGDIR/postgresql.conf"
      fi
    fi
  fi
}

[ "$1" = 'postgres' ] && shift

docker_setup_env

declare -g DATABASE_ALREADY_EXISTS
: "${DATABASE_ALREADY_EXISTS:=}"
[ -s "$PGDATA/PG_VERSION" ] && DATABASE_ALREADY_EXISTS='true'

if [ -z "$DATABASE_ALREADY_EXISTS" ]; then
  [ "$(id -u)" = '0' ] && exec gosu postgres "$0" postgres "$@"

  docker_init_database_dir
  configure_pg_cron
  pg_setup_hba_conf "$@"
  docker_temp_server_start "$@"

  if [ -n "${POSTGRES_DB:-}" ] && [ "${POSTGRES_DB:-}" != "postgres" ]; then
    POSTGRES_DB= psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --no-password --no-psqlrc \
      --dbname postgres --set db="$POSTGRES_DB" <<-'EOSQL'
      CREATE DATABASE :"db" ;
    EOSQL
    printf '\n'
  fi

  docker_process_init_files /docker-entrypoint-initdb.d/*
  docker_temp_server_stop
else
  cat <<-'EOM'

    PostgreSQL Database directory appears to contain a database; Skipping initialization

  EOM
fi

[ "$(id -u)" = '0' ] && exec gosu postgres postgres "$@"
exec postgres "$@"
