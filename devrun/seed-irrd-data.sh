#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command docker
require_command curl
require_command python3

FIXTURE_TEMPLATE="$DEVRUN_DIR/irrd/fixtures/local-authoritative.rpsl"

escape_sed_replacement() {
    printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

if [ ! -f "$ENV_FILE" ]; then
    printf 'Missing %s. Run ./dev.sh start once to generate the local compose environment.\n' "$ENV_FILE" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

if [ -z "${IRRD_OVERRIDE_PASSWORD:-}" ]; then
    printf 'Missing IRRD_OVERRIDE_PASSWORD in %s. Run ./dev.sh start to refresh the local dev environment.\n' "$ENV_FILE" >&2
    exit 1
fi

if ! wait_for_irrd; then
    printf 'IRRd is not reachable at %s. Start it with ./dev.sh irrd start first.\n' "$IRRD_BASE_URL" >&2
    exit 1
fi

maintainer_auth_hash="$(docker_compose exec -T irrd python - "$IRRD_OVERRIDE_PASSWORD" <<'PY'
import bcrypt
import sys

print(bcrypt.hashpw(sys.argv[1].encode('utf-8'), bcrypt.gensalt()).decode('utf-8'))
PY
)"

rendered_fixture="$(mktemp)"
response_json="$(mktemp)"
trap 'rm -f "$rendered_fixture" "$response_json"' EXIT

sed \
    -e "s|{{IRRD_SOURCE}}|$(escape_sed_replacement "$IRRD_SOURCE")|g" \
    -e "s|{{MNTNER_AUTH_HASH}}|$(escape_sed_replacement "$maintainer_auth_hash")|g" \
    "$FIXTURE_TEMPLATE" > "$rendered_fixture"

python3 - "$rendered_fixture" "$response_json" "$IRRD_BASE_URL" "$IRRD_OVERRIDE_PASSWORD" <<'PY'
import json
import pathlib
import sys
import urllib.request

fixture_path = pathlib.Path(sys.argv[1])
response_path = pathlib.Path(sys.argv[2])
base_url = sys.argv[3].rstrip('/')
override_password = sys.argv[4]

payload = {
    'objects': [
        {
            'object_text': object_text,
        }
        for object_text in fixture_path.read_text().strip().split('\n\n')
        if object_text.strip()
    ],
    'override': override_password,
}

request = urllib.request.Request(
    url=f'{base_url}/v1/submit/',
    data=json.dumps(payload).encode(),
    headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
    method='POST',
)

with urllib.request.urlopen(request, timeout=30) as response:
    response_path.write_bytes(response.read())
PY

python3 - "$response_json" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text())
summary = data.get('summary', {})

print('IRRD_SEED_SOURCE', 'LOCAL-IRR')
print('IRRD_SEED_OBJECTS_FOUND', summary.get('objects_found', 0))
print('IRRD_SEED_SUCCESSFUL', summary.get('successful', 0))
print('IRRD_SEED_FAILED', summary.get('failed', 0))

for obj in data.get('objects', []):
    status = 'OK' if obj.get('successful') else 'FAILED'
    print('IRRD_SEED_OBJECT', status, obj.get('object_class'), obj.get('rpsl_pk'))
    for message in obj.get('error_messages', []):
        print('IRRD_SEED_ERROR', obj.get('object_class'), obj.get('rpsl_pk'), message)

if summary.get('failed'):
    raise SystemExit(1)
PY