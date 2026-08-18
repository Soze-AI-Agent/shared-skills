#!/usr/bin/env bash
set -Eeo pipefail

# Firecrawl's nuq-postgres image bundles /docker-entrypoint-initdb.d/010-nuq.sql
# which creates the pg_cron extension. pg_cron must be created in the database
# configured by cron.database_name. If POSTGRES_DB is not 'postgres', configure
# the application DB as cron.database_name *before* PostgreSQL starts so the
# init script succeeds.
#
# Usage: bind-mount this script into the nuq-postgres container as /app/nuq-postgres-entrypoint.sh
# and override the container entrypoint with:
#   entrypoint: ["/bin/bash", "/app/nuq-postgres-entrypoint.sh"]

PGCONFIGDIR="${PGDATA:-/var/lib/postgresql/data}"

# Source upstream entrypoint functions
. /usr/local/bin/docker-entrypoint.sh

# If application DB is not postgres, patch postgresql.conf to include conf.d
# and set cron.database_name. The init script runs after initdb but before the
# first real server start.
configure_pg_cron() {
	if [ -n "${POSTGRES_DB:-}" ] && [ "${POSTGRES_DB:-}" != "postgres" ]; then
		mkdir -p "$PGCONFIGDIR/conf.d"
		cat > "$PGCONFIGDIR/conf.d/zz-firecrawl-cron.conf" <<EOF
# Firecrawl self-host: pg_cron must use the application database
cron.database_name = '${POSTGRES_DB}'
EOF
		# Ensure postgresql.conf includes conf.d. Default PG image leaves this
		# commented out, so we enable it if not already enabled.
		if ! grep -qxE "^[[:space:]]*include_dir\s*=\s*['\"]?conf.d['\"]?" "$PGCONFIGDIR/postgresql.conf"; then
			sed -i "s/^[#[:space:]]*include_dir\s*=\s*['\"]conf.d['\"].*/include_dir = 'conf.d'/" "$PGCONFIGDIR/postgresql.conf"
			if ! grep -qxE "^[[:space:]]*include_dir\s*=\s*['\"]?conf.d['\"]?" "$PGCONFIGDIR/postgresql.conf"; then
				echo "include_dir = 'conf.d'" >> "$PGCONFIGDIR/postgresql.conf"
			fi
		fi
	fi
}

if [ "$1" = 'postgres' ]; then
	shift
fi

docker_setup_env

declare -g DATABASE_ALREADY_EXISTS
: "${DATABASE_ALREADY_EXISTS:=}"
if [ -s "$PGDATA/PG_VERSION" ]; then
	DATABASE_ALREADY_EXISTS='true'
fi

if [ -z "$DATABASE_ALREADY_EXISTS" ]; then
	# Upstream entrypoint normally calls docker_init_database_dir as postgres.
	# We need to perform setup as postgres, so switch before init.
	if [ "$(id -u)" = '0' ]; then
		exec gosu postgres "$0" postgres "$@"
	fi

	docker_init_database_dir
	configure_pg_cron
	pg_setup_hba_conf "$@"

	docker_temp_server_start "$@"

	if [ -n "${POSTGRES_DB:-}" ] && [ "${POSTGRES_DB:-}" != "postgres" ]; then
		POSTGRES_DB= psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --no-password --no-psqlrc --dbname postgres --set db="$POSTGRES_DB" <<-'EOSQL'
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

# Final server startup must run as postgres. If we somehow got here as root
# (e.g. on a restart after the volume already contains a database), drop
# privileges before exec'ing postgres.
if [ "$(id -u)" = '0' ]; then
	exec gosu postgres postgres "$@"
fi

exec postgres "$@"
