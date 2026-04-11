#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command python3

BASELINE_LOG="$STATE_DIR/check.log"
PLUGIN_LOG="$STATE_DIR/plugin_check.log"

ensure_state_dir

if [ ! -d "$VENV_DIR" ]; then
    printf 'Missing virtual environment: %s\n' "$VENV_DIR" >&2
    exit 1
fi

if [ ! -d "$NETBOX_PROJECT_DIR" ]; then
    printf 'Missing NetBox project directory: %s\n' "$NETBOX_PROJECT_DIR" >&2
    exit 1
fi

set +e
(
    cd "$NETBOX_PROJECT_DIR"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    python manage.py check >"$BASELINE_LOG" 2>&1
)
BASELINE_RC=$?
(
    cd "$NETBOX_PROJECT_DIR"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    NETBOX_RPKI_ENABLE=1 python manage.py check >"$PLUGIN_LOG" 2>&1
)
PLUGIN_RC=$?
set -e

printf 'BASELINE_RC=%s\n' "$BASELINE_RC"
printf 'PLUGIN_RC=%s\n' "$PLUGIN_RC"
printf 'PLUGIN_BLOCKER=%s\n' "$(extract_plugin_blocker "$PLUGIN_LOG")"
printf 'BASELINE_LOG=%s\n' "$BASELINE_LOG"
printf 'PLUGIN_LOG=%s\n' "$PLUGIN_LOG"