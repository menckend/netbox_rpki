#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command python3

SEED_LOG="$STATE_DIR/seed.log"

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
    NETBOX_RPKI_ENABLE=1 python manage.py shell >"$SEED_LOG" 2>&1 <<'PY'
from netbox_rpki.sample_data import DEV_SEED_MARKER, count_seed_sample_data, seed_sample_data


dataset = seed_sample_data(
    item_count=12,
    label_prefix='Dev Seed',
    marker=DEV_SEED_MARKER,
    cleanup=True,
)
counts = count_seed_sample_data(DEV_SEED_MARKER)

print('SEED_MARKER', DEV_SEED_MARKER)
for model_name, count in counts.items():
    print(f'{model_name.upper()} {count}')
print('PRIMARY_COLLECTIONS', ','.join(
    f'{key}:{len(value)}'
    for key, value in sorted(dataset.items())
))
PY
)

printf 'SEED_LOG=%s\n' "$SEED_LOG"
cat "$SEED_LOG"
