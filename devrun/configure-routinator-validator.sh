#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command python3

VALIDATOR_LOG="$STATE_DIR/validator.log"
VALIDATOR_NAME="${ROUTINATOR_VALIDATOR_NAME:-Local Routinator}"

ensure_state_dir

if [ ! -d "$VENV_DIR" ]; then
    printf 'Missing virtual environment: %s\n' "$VENV_DIR" >&2
    exit 1
fi

if [ ! -d "$NETBOX_PROJECT_DIR" ]; then
    printf 'Missing NetBox project directory: %s\n' "$NETBOX_PROJECT_DIR" >&2
    exit 1
fi

(
    cd "$NETBOX_PROJECT_DIR"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    NETBOX_RPKI_ENABLE=1 \
    ROUTINATOR_BASE_URL="$ROUTINATOR_BASE_URL" \
    ROUTINATOR_VALIDATOR_NAME="$VALIDATOR_NAME" \
    python manage.py shell >"$VALIDATOR_LOG" 2>&1 <<'PY'
import os

from netbox_rpki.models import ValidatorInstance


validator, created = ValidatorInstance.objects.update_or_create(
    name=os.environ["ROUTINATOR_VALIDATOR_NAME"],
    defaults={
        "software_name": "Routinator",
        "base_url": os.environ["ROUTINATOR_BASE_URL"],
    },
)

print("VALIDATOR_%s" % ("CREATED" if created else "UPDATED"))
print("VALIDATOR_ID", validator.pk)
print("VALIDATOR_NAME", validator.name)
print("VALIDATOR_BASE_URL", validator.base_url)
print("VALIDATOR_STATUS", validator.status)
PY
)

printf 'VALIDATOR_LOG=%s\n' "$VALIDATOR_LOG"
cat "$VALIDATOR_LOG"