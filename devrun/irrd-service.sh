#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command docker
require_command curl

usage() {
    cat <<'EOF'
Usage: ./dev.sh irrd <start|stop|status|logs|seed>
EOF
}

start_irrd() {
    if [ ! -f "$ENV_FILE" ]; then
        printf 'Missing %s. Run ./dev.sh start once to generate the local compose environment.\n' "$ENV_FILE" >&2
        exit 1
    fi

    docker_compose up -d --build irrd
    if ! wait_for_irrd; then
        printf 'IRRd is still starting in the background at %s.\n' "$IRRD_BASE_URL" >&2
    fi
    docker_compose ps irrd
}

stop_irrd() {
    docker_compose stop irrd
}

status_irrd() {
    case "$(irrd_status_http_code)" in
        200)
            printf 'IRRd: ready at %s (whois on port %s)\n' "$IRRD_BASE_URL" "$IRRD_WHOIS_PORT"
            ;;
        000|'')
            printf 'IRRd: unreachable at %s\n' "$IRRD_BASE_URL"
            ;;
        *)
            printf 'IRRd: reachable at %s (HTTP %s)\n' "$IRRD_BASE_URL" "$(irrd_status_http_code)"
            ;;
    esac
    docker_compose ps irrd
}

logs_irrd() {
    docker_compose logs --tail=100 irrd
}

seed_irrd() {
    "$DEVRUN_DIR/seed-irrd-data.sh"
}

case "${1:-start}" in
    start)
        start_irrd
        ;;
    stop)
        stop_irrd
        ;;
    status)
        status_irrd
        ;;
    logs)
        logs_irrd
        ;;
    seed)
        seed_irrd
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        printf 'Unknown IRRd command: %s\n\n' "$1" >&2
        usage >&2
        exit 1
        ;;
esac