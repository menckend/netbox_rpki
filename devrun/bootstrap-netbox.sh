#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command docker
require_command python3
require_command pg_isready
require_command redis-cli

generate_password() {
    python3 - <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits + '._-'
print(''.join(secrets.choice(alphabet) for _ in range(40)))
PY
}

generate_secret() {
    python3 - <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits + '._-'
print(''.join(secrets.choice(alphabet) for _ in range(64)))
PY
}

is_safe_token() {
    local value="$1"
    local expected_length="$2"
    [[ "$value" =~ ^[A-Za-z0-9._-]+$ ]] || return 1
    [ "${#value}" -eq "$expected_length" ]
}

ensure_credentials() {
    ensure_state_dir
    load_credentials

    if [ -z "${NETBOX_DATABASE_PASSWORD:-}" ]; then
        NETBOX_DATABASE_PASSWORD="$(generate_password)"
    fi
    if [ -z "${NETBOX_ADMIN_PASSWORD:-}" ]; then
        NETBOX_ADMIN_PASSWORD="$(python3 - <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits + '._-'
print(''.join(secrets.choice(alphabet) for _ in range(24)))
PY
)"
    fi
    if ! is_safe_token "${NETBOX_SECRET_KEY:-}" 64; then
        NETBOX_SECRET_KEY="$(generate_secret)"
    fi
    if ! is_safe_token "${NETBOX_API_TOKEN_PEPPER:-}" 64; then
        NETBOX_API_TOKEN_PEPPER="$(generate_secret)"
    fi

    printf 'NETBOX_DATABASE_PASSWORD=%q\n' "$NETBOX_DATABASE_PASSWORD" > "$CREDENTIALS_FILE"
    printf 'NETBOX_ADMIN_PASSWORD=%q\n' "$NETBOX_ADMIN_PASSWORD" >> "$CREDENTIALS_FILE"
    printf 'NETBOX_SECRET_KEY=%q\n' "$NETBOX_SECRET_KEY" >> "$CREDENTIALS_FILE"
    printf 'NETBOX_API_TOKEN_PEPPER=%q\n' "$NETBOX_API_TOKEN_PEPPER" >> "$CREDENTIALS_FILE"
    chmod 600 "$CREDENTIALS_FILE"
}

ensure_compose_env() {
    POSTGRES_DB="netbox"
    POSTGRES_USER="netbox"
    POSTGRES_PASSWORD="$NETBOX_DATABASE_PASSWORD"

    if [ -f "$ENV_FILE" ]; then
        while IFS='=' read -r key value; do
            key="${key%$'\r'}"
            value="${value%$'\r'}"
            case "$key" in
                POSTGRES_DB|POSTGRES_USER|POSTGRES_PASSWORD)
                    export "$key=$value"
                    ;;
            esac
        done < "$ENV_FILE"

        POSTGRES_DB="${POSTGRES_DB:-netbox}"
        POSTGRES_USER="${POSTGRES_USER:-netbox}"
        POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$NETBOX_DATABASE_PASSWORD}"
    fi

    cat > "$ENV_FILE" <<EOF
POSTGRES_DB=$POSTGRES_DB
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
EOF
    chmod 600 "$ENV_FILE"
}

ensure_netbox_source_link() {
    local site_packages
    site_packages="$("$VENV_DIR/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
    printf '%s\n' "$NETBOX_PROJECT_DIR" > "$site_packages/netbox.pth"
}

write_configuration() {
    cat > "$CONFIG_FILE" <<EOF
import os

ALLOWED_HOSTS = ['*']
DEBUG = True
DEVELOPER = True

DATABASES = {
    'default': {
        'NAME': 'netbox',
        'USER': 'netbox',
        'PASSWORD': '$NETBOX_DATABASE_PASSWORD',
        'HOST': '127.0.0.1',
        'PORT': '5432',
        'CONN_MAX_AGE': 300,
    }
}

REDIS = {
    'tasks': {
        'HOST': '127.0.0.1',
        'PORT': 6379,
        'PASSWORD': '',
        'DATABASE': 0,
        'SSL': False,
    },
    'caching': {
        'HOST': '127.0.0.1',
        'PORT': 6379,
        'PASSWORD': '',
        'DATABASE': 1,
        'SSL': False,
    },
}

SECRET_KEY = '$NETBOX_SECRET_KEY'
API_TOKEN_PEPPERS = {
    1: '$NETBOX_API_TOKEN_PEPPER',
}

PLUGINS = ['netbox_rpki'] if os.getenv('NETBOX_RPKI_ENABLE') == '1' else []

PLUGINS_CONFIG = {
    'netbox_rpki': {
        'top_level_menu': True,
    },
}
EOF
    chmod 600 "$CONFIG_FILE"
}

ensure_database_permissions() {
    docker_compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
        -c "ALTER SCHEMA public OWNER TO $POSTGRES_USER;" >/dev/null
    docker_compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
        -c "GRANT CREATE ON SCHEMA public TO $POSTGRES_USER;" >/dev/null
}

run_manage_tasks() {
    local migrate_log="$STATE_DIR/migrate.log"
    local check_log="$STATE_DIR/check.log"
    local collectstatic_log="$STATE_DIR/collectstatic.log"
    local superuser_log="$STATE_DIR/superuser.log"
    local plugin_log="$STATE_DIR/plugin_check.log"

    : > "$migrate_log"
    : > "$check_log"
    : > "$collectstatic_log"
    : > "$superuser_log"
    : > "$plugin_log"

    (
        cd "$NETBOX_PROJECT_DIR"
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
        NETBOX_RPKI_ENABLE=1 python manage.py migrate --noinput >"$migrate_log" 2>&1
        NETBOX_RPKI_ENABLE=1 python manage.py collectstatic --noinput >"$collectstatic_log" 2>&1
        python manage.py check >"$check_log" 2>&1
        NETBOX_ADMIN_PASSWORD="$NETBOX_ADMIN_PASSWORD" python manage.py shell -c "import os; from django.contrib.auth import get_user_model; User = get_user_model(); user, created = User.objects.get_or_create(username='admin', defaults={'email': 'admin@example.com', 'is_superuser': True, 'is_active': True}); user.email = 'admin@example.com'; user.is_superuser = True; user.is_active = True; user.set_password(os.environ['NETBOX_ADMIN_PASSWORD']); user.save(); print('SUPERUSER_' + ('CREATED' if created else 'UPDATED'))" >"$superuser_log" 2>&1
        NETBOX_RPKI_ENABLE=1 python manage.py check >"$plugin_log" 2>&1 || true
    )

    printf 'MIGRATE_LOG=%s\n' "$migrate_log"
    printf 'CHECK_LOG=%s\n' "$check_log"
    printf 'COLLECTSTATIC_LOG=%s\n' "$collectstatic_log"
    printf 'SUPERUSER_LOG=%s\n' "$superuser_log"
    printf 'PLUGIN_LOG=%s\n' "$plugin_log"
    printf 'PLUGIN_BLOCKER=%s\n' "$(extract_plugin_blocker "$plugin_log")"
}

if [ ! -d "$VENV_DIR" ]; then
    printf 'Missing virtual environment: %s\n' "$VENV_DIR" >&2
    exit 1
fi

if [ ! -d "$NETBOX_PROJECT_DIR" ]; then
    printf 'Missing NetBox project directory: %s\n' "$NETBOX_PROJECT_DIR" >&2
    exit 1
fi

ensure_credentials
ensure_compose_env
docker_compose up -d
wait_for_postgres
wait_for_redis
ensure_database_permissions
ensure_netbox_source_link
write_configuration
run_manage_tasks

printf 'CREDENTIALS_FILE=%s\n' "$CREDENTIALS_FILE"
printf 'ENV_FILE=%s\n' "$ENV_FILE"
printf 'CONFIG_FILE=%s\n' "$CONFIG_FILE"