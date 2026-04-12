#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command docker

stop_runserver || true
stop_worker || true
stop_krill || true
docker_compose down
