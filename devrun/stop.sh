#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command docker

stop_runserver || true
docker_compose down