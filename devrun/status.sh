#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command docker
require_command pg_isready
require_command redis-cli
require_command curl

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

if worker_is_running; then
	mapfile -t worker_pids < <(find_worker_pids)
	printf 'Worker: running ('
	printf '%s' "${worker_pids[*]}" | tr ' ' ','
	printf ')\n\n'
else
	printf 'Worker: stopped\n\n'
fi

if krill_is_installed; then
	if krill_is_running; then
		mapfile -t krill_pids < <(find_krill_pids)
		printf 'Krill: running ('
		printf '%s' "${krill_pids[*]}" | tr ' ' ','
		printf ')\n\n'
	else
		printf 'Krill: installed but stopped\n\n'
	fi
else
	printf 'Krill: not installed under %s\n\n' "$KRILL_ROOT"
fi

case "$(routinator_status_http_code)" in
	200)
		printf 'Routinator: ready at %s\n\n' "$ROUTINATOR_BASE_URL"
		;;
	503)
		printf 'Routinator: reachable at %s (initial validation ongoing)\n\n' "$ROUTINATOR_BASE_URL"
		;;
	000|'')
		printf 'Routinator: unreachable at %s\n\n' "$ROUTINATOR_BASE_URL"
		;;
	*)
		printf 'Routinator: reachable at %s (HTTP %s)\n\n' "$ROUTINATOR_BASE_URL" "$(routinator_status_http_code)"
		;;
esac

docker_compose ps
printf '\nPostgreSQL: '
pg_isready -h 127.0.0.1 -p 5432 || true
printf 'Redis: '
redis-cli -h 127.0.0.1 -p 6379 ping || true
