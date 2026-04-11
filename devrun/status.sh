#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command docker
require_command pg_isready
require_command redis-cli

printf 'Release: %s\n' "$NETBOX_RELEASE"
printf 'NetBox: %s\n' "$NETBOX_PROJECT_DIR"
printf 'Virtualenv: %s\n' "$VENV_DIR"
if [ -x "$VENV_DIR/bin/python" ]; then
	printf 'Python: %s\n' "$VENV_DIR/bin/python"
fi
printf 'Credentials: %s\n' "$CREDENTIALS_FILE"
printf 'Config: %s\n\n' "$CONFIG_FILE"

if runserver_is_running; then
	mapfile -t runserver_pids < <(find_runserver_pids)
	printf 'Runserver: running ('
	printf '%s' "${runserver_pids[*]}" | tr ' ' ','
	printf ')\n\n'
else
	printf 'Runserver: stopped\n\n'
fi

docker_compose ps
printf '\nPostgreSQL: '
pg_isready -h 127.0.0.1 -p 5432 || true
printf 'Redis: '
redis-cli -h 127.0.0.1 -p 6379 ping || true