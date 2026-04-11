#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command python3

HOST="${NETBOX_RUN_HOST:-0.0.0.0}"
PORT="${NETBOX_RUN_PORT:-8000}"
ENABLE_PLUGIN="${NETBOX_RPKI_ENABLE:-1}"

if [ ! -d "$VENV_DIR" ]; then
    printf 'Missing virtual environment: %s\n' "$VENV_DIR" >&2
    exit 1
fi

if [ ! -d "$NETBOX_PROJECT_DIR" ]; then
    printf 'Missing NetBox project directory: %s\n' "$NETBOX_PROJECT_DIR" >&2
    exit 1
fi

cd "$NETBOX_PROJECT_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

NETBOX_RPKI_ENABLE="$ENABLE_PLUGIN" exec python manage.py runserver "$HOST:$PORT"