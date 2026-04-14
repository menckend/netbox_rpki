#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command docker
require_command pg_isready
require_command redis-cli
require_command curl

if [ ! -f "$ENV_FILE" ]; then
    printf 'Missing %s. Run ./bootstrap-netbox.sh to generate it, or copy .env.example to .env and set POSTGRES_PASSWORD.\n' "$ENV_FILE" >&2
    exit 1
fi

docker_compose up -d
wait_for_postgres
wait_for_redis
if ! wait_for_routinator; then
    printf 'Routinator is still starting in the background at %s.\n' "$ROUTINATOR_BASE_URL" >&2
fi
docker_compose ps