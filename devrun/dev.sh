#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

usage() {
    cat <<'EOF'
Usage: ./dev.sh <start|stop|status|validator|irrd|seed|e2e>

    start   Ensure containers, Routinator, config, migrations, worker, optional Krill, and run the NetBox dev server
    stop    Stop the NetBox dev server, worker, optional Krill, and container stack
        status  Show the current NetBox dev environment and process status
        validator  Create or update the local Routinator validator instance inside NetBox
    irrd    Manage the local IRRd lab service (start|stop|status|logs|seed)
    seed    Populate the local dev database with reusable RPKI sample data
    e2e     Run Playwright browser tests through the local WSL wrapper
EOF
}

start_dev() {
    if runserver_is_running; then
        printf 'NetBox development server is already running for %s\n' "$NETBOX_PROJECT_DIR"
        exec "$DEVRUN_DIR/status.sh"
    fi

    "$DEVRUN_DIR/bootstrap-netbox.sh"
    ensure_state_dir
    if krill_is_installed && ! krill_is_running; then
        "$KRILL_START_SCRIPT"
    fi
    if ! worker_is_running; then
        nohup "$DEVRUN_DIR/worker.sh" >"$STATE_DIR/worker.log" 2>&1 &
    fi
    exec "$DEVRUN_DIR/runserver.sh"
}

stop_dev() {
    "$DEVRUN_DIR/stop.sh"
}

status_dev() {
    "$DEVRUN_DIR/status.sh"
}

validator_dev() {
    "$DEVRUN_DIR/configure-routinator-validator.sh"
}

irrd_dev() {
    "$DEVRUN_DIR/irrd-service.sh" "$@"
}

seed_dev() {
    "$DEVRUN_DIR/seed-data.sh"
}

e2e_dev() {
    exec "$DEVRUN_DIR/e2e.sh" "$@"
}

case "${1:-}" in
    start)
        start_dev
        ;;
    stop)
        stop_dev
        ;;
    status)
        status_dev
        ;;
    validator)
        validator_dev
        ;;
    irrd)
        shift
        irrd_dev "$@"
        ;;
    seed)
        seed_dev
        ;;
    e2e)
        shift
        e2e_dev "$@"
        ;;
    -h|--help|help|'')
        usage
        ;;
    *)
        printf 'Unknown command: %s\n\n' "$1" >&2
        usage >&2
        exit 1
        ;;
esac
