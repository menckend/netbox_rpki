#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="/etc/irrd.yaml"
DATA_DIR="/var/lib/irrd"
PID_DIR="${DATA_DIR}/pids"
GPG_DIR="${DATA_DIR}/gnupg"
IRRD_RUN_USER="irrd"
IRRD_RUN_GROUP="irrd"

mkdir -p "$PID_DIR" "$GPG_DIR"
chmod 700 "$GPG_DIR"
chown -R "${IRRD_RUN_USER}:${IRRD_RUN_GROUP}" "$DATA_DIR"

wait_for_tcp() {
    local host="$1"
    local port="$2"
    local label="$3"
    local attempt

    for attempt in $(seq 1 60); do
        if python - "$host" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(1)
    sock.connect((host, port))
PY
        then
            return 0
        fi
        sleep 1
    done

    printf '%s did not become reachable at %s:%s in time.\n' "$label" "$host" "$port" >&2
    return 1
}

ensure_database() {
    export PGPASSWORD="$POSTGRES_PASSWORD"

    if ! psql -h postgres -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='${IRRD_DATABASE_USER}'" | grep -q 1; then
        psql -h postgres -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
            -c "CREATE ROLE ${IRRD_DATABASE_USER} WITH LOGIN PASSWORD '${IRRD_DATABASE_PASSWORD}';"
    else
        psql -h postgres -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
            -c "ALTER ROLE ${IRRD_DATABASE_USER} WITH LOGIN PASSWORD '${IRRD_DATABASE_PASSWORD}';"
    fi

    if ! psql -h postgres -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${IRRD_DATABASE_NAME}'" | grep -q 1; then
        psql -h postgres -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
            -c "CREATE DATABASE ${IRRD_DATABASE_NAME} OWNER ${IRRD_DATABASE_USER};"
    fi

    psql -h postgres -U "$POSTGRES_USER" -d "$IRRD_DATABASE_NAME" -v ON_ERROR_STOP=1 \
        -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" \
        -c "ALTER SCHEMA public OWNER TO ${IRRD_DATABASE_USER};" \
        -c "GRANT ALL ON SCHEMA public TO ${IRRD_DATABASE_USER};" \
        -c "GRANT ALL PRIVILEGES ON DATABASE ${IRRD_DATABASE_NAME} TO ${IRRD_DATABASE_USER};"
}

write_config() {
  local override_password_hash=""
  local override_password_line=""

  if [ -n "${IRRD_OVERRIDE_PASSWORD:-}" ]; then
    override_password_hash="$(python - "$IRRD_OVERRIDE_PASSWORD" <<'PY'
from passlib.hash import bcrypt
import sys

print(bcrypt.hash(sys.argv[1]))
PY
)"
    override_password_line="    override_password: '${override_password_hash}'"
  fi

    cat > "$CONFIG_PATH" <<EOF
irrd:
  database_url: "postgresql://${IRRD_DATABASE_USER}:${IRRD_DATABASE_PASSWORD}@postgres:5432/${IRRD_DATABASE_NAME}"
  redis_url: "redis://redis:6379/2"
  piddir: ${PID_DIR}
  user: ${IRRD_RUN_USER}
  group: ${IRRD_RUN_GROUP}
  access_lists:
    local_status:
      - 0.0.0.0/0
      - ::/0
  server:
    http:
      status_access_list: local_status
      interface: "0.0.0.0"
      port: ${IRRD_HTTP_PORT}
      workers: 1
      url: "${IRRD_EXTERNAL_HTTP_URL}"
    whois:
      interface: "0.0.0.0"
      port: ${IRRD_WHOIS_PORT}
      max_connections: 2
  auth:
    gnupg_keyring: ${GPG_DIR}
${override_password_line}
  email:
    footer: "Local IRRd development instance"
    from: "irrd-dev@example.invalid"
    recipient_override: "irrd-dev@example.invalid"
    smtp: localhost
  rpki:
    roa_source: null
  compatibility:
    inetnum_search_disabled: true
  sources_default:
    - ${IRRD_SOURCE}
  sources:
    ${IRRD_SOURCE}:
      authoritative: true
      keep_journal: true
      object_class_filter:
        - person
        - route
        - route6
        - route-set
        - as-set
        - aut-num
        - mntner
EOF
}

wait_for_tcp postgres 5432 PostgreSQL
wait_for_tcp redis 6379 Redis
ensure_database
write_config
irrd_database_upgrade --config="$CONFIG_PATH"
exec irrd --foreground --config="$CONFIG_PATH"