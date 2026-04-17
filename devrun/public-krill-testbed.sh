#!/usr/bin/env bash
set -euo pipefail

DEVRUN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LIVE_PROVIDER_ENABLE_ENV="${LIVE_PROVIDER_ENABLE_ENV:-NETBOX_RPKI_ENABLE_LIVE_PROVIDER_TESTS}"
LIVE_PROVIDER_NAME_ENV="${LIVE_PROVIDER_NAME_ENV:-NETBOX_RPKI_LIVE_PROVIDER}"
LIVE_KRILL_API_BASE_URL_ENV="${LIVE_KRILL_API_BASE_URL_ENV:-NETBOX_RPKI_LIVE_KRILL_API_BASE_URL}"
LIVE_KRILL_CA_HANDLE_ENV="${LIVE_KRILL_CA_HANDLE_ENV:-NETBOX_RPKI_LIVE_KRILL_CA_HANDLE}"
LIVE_KRILL_API_TOKEN_ENV="${LIVE_KRILL_API_TOKEN_ENV:-NETBOX_RPKI_LIVE_KRILL_API_TOKEN}"
LIVE_KRILL_ORG_HANDLE_ENV="${LIVE_KRILL_ORG_HANDLE_ENV:-NETBOX_RPKI_LIVE_KRILL_ORG_HANDLE}"

DEFAULT_LIVE_KRILL_API_BASE_URL="https://localhost:3001"
DEFAULT_LIVE_KRILL_CA_HANDLE="netbox-rpki-dev"
DEFAULT_LIVE_KRILL_ORG_HANDLE="PUBLIC-TESTBED"

usage() {
    cat <<EOF
Usage: ./public-krill-testbed.sh [env|check|run] [extra ./test.sh args]

  env    Print the live-provider environment expected by the public Krill testbed path
  check  Validate the environment and probe the configured Krill CA endpoint read-only
  run    Export the live-provider environment and run ./test.sh live-provider (default)

Required:
  ${LIVE_KRILL_API_TOKEN_ENV}

Optional:
  ${LIVE_KRILL_API_BASE_URL_ENV}  default: ${DEFAULT_LIVE_KRILL_API_BASE_URL}
  ${LIVE_KRILL_CA_HANDLE_ENV}     default: ${DEFAULT_LIVE_KRILL_CA_HANDLE}
  ${LIVE_KRILL_ORG_HANDLE_ENV}    default: ${DEFAULT_LIVE_KRILL_ORG_HANDLE}

This helper is intended for the documented local public-testbed path:
  1. Run a local or disposable Krill CA
  2. Register it under the NLnet Labs public testbed
  3. Export the resulting CA handle and API token
  4. Use this helper to run the live-provider lane safely
EOF
}

current_api_base_url() {
    printf '%s' "${!LIVE_KRILL_API_BASE_URL_ENV:-$DEFAULT_LIVE_KRILL_API_BASE_URL}"
}

current_ca_handle() {
    printf '%s' "${!LIVE_KRILL_CA_HANDLE_ENV:-$DEFAULT_LIVE_KRILL_CA_HANDLE}"
}

current_org_handle() {
    printf '%s' "${!LIVE_KRILL_ORG_HANDLE_ENV:-$DEFAULT_LIVE_KRILL_ORG_HANDLE}"
}

require_token() {
    if [ -z "${!LIVE_KRILL_API_TOKEN_ENV:-}" ]; then
        printf 'Missing required environment variable: %s\n' "$LIVE_KRILL_API_TOKEN_ENV" >&2
        exit 1
    fi
}

print_env() {
    cat <<EOF
export ${LIVE_PROVIDER_ENABLE_ENV}=1
export ${LIVE_PROVIDER_NAME_ENV}=krill
export ${LIVE_KRILL_API_BASE_URL_ENV}="$(current_api_base_url)"
export ${LIVE_KRILL_CA_HANDLE_ENV}="$(current_ca_handle)"
export ${LIVE_KRILL_ORG_HANDLE_ENV}="$(current_org_handle)"
export ${LIVE_KRILL_API_TOKEN_ENV}="<krill-api-token>"
EOF
}

probe_live_krill() {
    local api_base_url ca_handle
    require_token
    api_base_url="$(current_api_base_url)"
    ca_handle="$(current_ca_handle)"

    curl --fail --silent --show-error \
        --insecure \
        --header "Authorization: Bearer ${!LIVE_KRILL_API_TOKEN_ENV}" \
        --header "Accept: application/json" \
        "${api_base_url%/}/api/v1/cas/${ca_handle}" \
        >/dev/null
}

run_live_provider_lane() {
    require_token
    export "${LIVE_PROVIDER_ENABLE_ENV}=1"
    export "${LIVE_PROVIDER_NAME_ENV}=krill"
    export "${LIVE_KRILL_API_BASE_URL_ENV}=$(current_api_base_url)"
    export "${LIVE_KRILL_CA_HANDLE_ENV}=$(current_ca_handle)"
    export "${LIVE_KRILL_ORG_HANDLE_ENV}=$(current_org_handle)"

    probe_live_krill

    exec "$DEVRUN_DIR/test.sh" live-provider "$@"
}

main() {
    local command="${1:-run}"
    case "$command" in
        -h|--help|help)
            usage
            ;;
        env)
            print_env
            ;;
        check)
            shift || true
            probe_live_krill
            printf 'Live Krill probe succeeded for %s at %s\n' "$(current_ca_handle)" "$(current_api_base_url)"
            ;;
        run)
            shift || true
            run_live_provider_lane "$@"
            ;;
        *)
            usage >&2
            exit 1
            ;;
    esac
}

main "$@"
