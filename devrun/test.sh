#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

FAST_TEST_LABELS=(
    netbox_rpki.tests.test_urls
    netbox_rpki.tests.test_navigation
    netbox_rpki.tests.test_graphql.GraphQLSchemaRegistrationTestCase
    netbox_rpki.tests.test_api.ObjectRegistrySmokeTestCase
    netbox_rpki.tests.test_api.Priority6GeneratedWorkflowSurfaceContractTestCase
    netbox_rpki.tests.test_api.GraphQLSmokeTestCase
    netbox_rpki.tests.test_api.SerializerSmokeTestCase
    netbox_rpki.tests.test_api.ViewSetSmokeTestCase
    netbox_rpki.tests.test_views.ViewRegistrySmokeTestCase
    netbox_rpki.tests.test_filtersets.FilterSetRegistrySmokeTestCase
    netbox_rpki.tests.test_forms.FormStructureSmokeTestCase
    netbox_rpki.tests.test_tables.TableRegistrySmokeTestCase
    netbox_rpki.tests.test_tables.Priority6TableContractTestCase
)

CONTRACT_TEST_LABELS=(
    netbox_rpki.tests.test_views
    netbox_rpki.tests.test_api
    netbox_rpki.tests.test_forms
    netbox_rpki.tests.test_filtersets
    netbox_rpki.tests.test_tables
    netbox_rpki.tests.test_urls
    netbox_rpki.tests.test_navigation
    netbox_rpki.tests.test_graphql
    netbox_rpki.tests.test_signed_object_corpus
)

PROVIDER_TEST_LABELS=(
    netbox_rpki.tests.test_provider_sync
    netbox_rpki.tests.test_provider_write
    netbox_rpki.tests.test_aspa_provider_write
    netbox_rpki.tests.test_rollback_bundle
)

LIVE_PROVIDER_TEST_GLOB='test_live_*.py'

usage() {
    cat <<'EOF'
Usage: ./test.sh [fast|contract|provider|live-provider|full|<test labels...>] [extra manage.py test args]

  fast        Run the low-cost structural smoke lane under dedicated test settings
  contract    Run the registry/UI/API/GraphQL surface-contract lane (default)
  provider    Run the fixture-backed provider sync/write lane used for hosted-provider features
  live-provider
              Run opt-in real-backend integration tests discovered from netbox_rpki/tests/test_live_*.py
  full        Run the full plugin suite
  <labels>    Run explicit Django test labels under the same dedicated test settings

Examples:
  ./test.sh
  ./test.sh fast
  ./test.sh contract --verbosity 2
  ./test.sh provider
  ./test.sh live-provider
  ./test.sh full
  ./test.sh netbox_rpki.tests.test_provider_sync --verbosity 2
EOF
}

is_truthy() {
    case "${1:-}" in
        1|true|TRUE|True|yes|YES|Yes|on|ON|On)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

discover_live_provider_test_labels() {
    find "$DEVRUN_DIR/../netbox_rpki/tests" -maxdepth 1 -type f -name "$LIVE_PROVIDER_TEST_GLOB" \
        | sort \
        | while IFS= read -r path; do
            [ -n "$path" ] || continue
            printf 'netbox_rpki.tests.%s\n' "$(basename "$path" .py)"
        done
}

load_compose_env() {
    if [ -f "$ENV_FILE" ]; then
        set -a
        # shellcheck disable=SC1090
        . "$ENV_FILE"
        set +a
    fi
}

ensure_runtime_paths() {
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        printf 'Missing Python executable: %s\n' "$VENV_DIR/bin/python" >&2
        exit 1
    fi

    if [ ! -f "$NETBOX_PROJECT_DIR/manage.py" ]; then
        printf 'Missing NetBox manage.py: %s\n' "$NETBOX_PROJECT_DIR/manage.py" >&2
        exit 1
    fi
}

prepare_test_environment() {
    load_credentials
    load_compose_env

    export POSTGRES_DB="${POSTGRES_DB:-netbox}"
    export POSTGRES_USER="${POSTGRES_USER:-netbox}"
    export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-${NETBOX_DATABASE_PASSWORD:-netbox}}"
    export ROUTINATOR_RTR_PORT="${ROUTINATOR_RTR_PORT:-3323}"
    export ROUTINATOR_HTTP_PORT="${ROUTINATOR_HTTP_PORT:-8323}"
    export ROUTINATOR_METRICS_PORT="${ROUTINATOR_METRICS_PORT:-9556}"
    export IRRD_DATABASE_NAME="${IRRD_DATABASE_NAME:-irrd}"
    export IRRD_DATABASE_USER="${IRRD_DATABASE_USER:-irrd}"
    export IRRD_DATABASE_PASSWORD="${IRRD_DATABASE_PASSWORD:-netbox-irrd}"
    export IRRD_HTTP_PORT="${IRRD_HTTP_PORT:-6080}"
    export IRRD_WHOIS_PORT="${IRRD_WHOIS_PORT:-6043}"
    export IRRD_SOURCE="${IRRD_SOURCE:-LOCAL-IRR}"
    export IRRD_OVERRIDE_PASSWORD="${IRRD_OVERRIDE_PASSWORD:-netbox-irrd-override}"

    export NETBOX_CONFIGURATION="${NETBOX_CONFIGURATION:-netbox_rpki.tests.netbox_configuration}"
    export NETBOX_RPKI_ENABLE=1
    export NETBOX_TEST_DB_NAME="${NETBOX_TEST_DB_NAME:-$POSTGRES_DB}"
    export NETBOX_TEST_DB_USER="${NETBOX_TEST_DB_USER:-$POSTGRES_USER}"
    export NETBOX_TEST_DB_PASSWORD="${NETBOX_TEST_DB_PASSWORD:-$POSTGRES_PASSWORD}"
    export NETBOX_TEST_DB_HOST="${NETBOX_TEST_DB_HOST:-127.0.0.1}"
    export NETBOX_TEST_DB_PORT="${NETBOX_TEST_DB_PORT:-5433}"
    export NETBOX_TEST_DB_TEST_NAME="${NETBOX_TEST_DB_TEST_NAME:-test_${NETBOX_TEST_DB_NAME}_rpki}"
    export NETBOX_TEST_REDIS_HOST="${NETBOX_TEST_REDIS_HOST:-127.0.0.1}"
    export NETBOX_TEST_REDIS_PORT="${NETBOX_TEST_REDIS_PORT:-6380}"
    export NETBOX_TEST_REDIS_PASSWORD="${NETBOX_TEST_REDIS_PASSWORD:-}"
}

ensure_test_services() {
    docker_compose up -d postgres redis >/dev/null
    wait_for_postgres
    wait_for_redis
}

run_django_tests() {
    local -a labels=("$@")

    (
        cd "$NETBOX_PROJECT_DIR"
        exec "$VENV_DIR/bin/python" manage.py test --keepdb --noinput "${labels[@]}"
    )
}

run_live_provider_tests() {
    local -a labels=()

    if ! is_truthy "${NETBOX_RPKI_ENABLE_LIVE_PROVIDER_TESTS:-}"; then
        printf '%s\n' \
            "Skipping live-provider lane. Set NETBOX_RPKI_ENABLE_LIVE_PROVIDER_TESTS=1 to enable real-backend tests."
        return 0
    fi

    if [ "$#" -gt 0 ]; then
        run_django_tests "$@"
        return 0
    fi

    mapfile -t labels < <(discover_live_provider_test_labels)
    if [ "${#labels[@]}" -eq 0 ]; then
        printf '%s\n' \
            "No live-provider tests found under netbox_rpki/tests/${LIVE_PROVIDER_TEST_GLOB}."
        return 0
    fi

    run_django_tests "${labels[@]}"
}

main() {
    case "${1:-contract}" in
        -h|--help|help)
            usage
            return 0
            ;;
    esac

    require_command docker
    require_command pg_isready
    require_command redis-cli

    ensure_runtime_paths
    prepare_test_environment
    ensure_test_services

    case "${1:-contract}" in
        fast)
            shift || true
            run_django_tests "${FAST_TEST_LABELS[@]}" "$@"
            ;;
        contract)
            shift || true
            run_django_tests "${CONTRACT_TEST_LABELS[@]}" "$@"
            ;;
        provider)
            shift || true
            run_django_tests "${PROVIDER_TEST_LABELS[@]}" "$@"
            ;;
        live-provider)
            shift || true
            run_live_provider_tests "$@"
            ;;
        full)
            shift || true
            run_django_tests netbox_rpki.tests "$@"
            ;;
        *)
            run_django_tests "$@"
            ;;
    esac
}

main "$@"
