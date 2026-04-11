#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

REPO_ROOT="$(cd "$DEVRUN_DIR/.." && pwd)"
NODE_LTS_BIN="${NODE_LTS_BIN:-$HOME/.local/node-lts/bin}"
PLAYWRIGHT_CACHE_DIR="${PLAYWRIGHT_CACHE_DIR:-$HOME/.cache/ms-playwright}"
PLAYWRIGHT_LIB_ROOT="${PLAYWRIGHT_LIB_ROOT:-$HOME/.local/playwright-system-libs}"
PLAYWRIGHT_LIB_DIR="${PLAYWRIGHT_LIB_DIR:-$PLAYWRIGHT_LIB_ROOT/root/usr/lib/x86_64-linux-gnu}"
NETBOX_E2E_BASE_URL="${NETBOX_E2E_BASE_URL:-http://127.0.0.1:8000}"

usage() {
    cat <<'EOF'
Usage: ./e2e.sh [run|headed|ui|install] [playwright args...]

  run       Run the Playwright suite headlessly (default)
  headed    Run the Playwright suite in headed mode
  ui        Run the Playwright suite in Playwright UI mode
  install   Install npm dependencies, Playwright Chromium, and local Linux libs if needed

Examples:
  ./e2e.sh
  ./e2e.sh headed
  ./e2e.sh tests/e2e/netbox-rpki/roas.spec.js --project=chromium
  ./e2e.sh install
EOF
}

prepend_path() {
    local dir="$1"
    [ -d "$dir" ] || return 0
    case ":$PATH:" in
        *":$dir:"*)
            ;;
        *)
            export PATH="$dir:$PATH"
            ;;
    esac
}

find_chromium_binary() {
    find "$PLAYWRIGHT_CACHE_DIR" -path '*/chrome-linux64/chrome' -type f 2>/dev/null | head -n 1
}

missing_chromium_libs() {
    local chromium_binary="$1"

    ldd "$chromium_binary" 2>/dev/null | awk '/not found/ { print $1 }' | sort -u
}

enable_local_browser_libs() {
    [ -d "$PLAYWRIGHT_LIB_DIR" ] || return 0

    case ":${LD_LIBRARY_PATH:-}:" in
        *":$PLAYWRIGHT_LIB_DIR:"*)
            ;;
        *)
            export LD_LIBRARY_PATH="$PLAYWRIGHT_LIB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
            ;;
    esac
}

bootstrap_local_browser_libs() {
    local asound_package="libasound2t64"
    local deb_dir="$PLAYWRIGHT_LIB_ROOT/debs"

    require_command apt
    require_command apt-cache
    require_command dpkg-deb

    if ! apt-cache show "$asound_package" >/dev/null 2>&1; then
        asound_package="libasound2"
    fi

    mkdir -p "$deb_dir"
    rm -rf "$PLAYWRIGHT_LIB_ROOT/root"
    mkdir -p "$PLAYWRIGHT_LIB_ROOT/root"

    (
        cd "$deb_dir"
        rm -f ./*.deb
        apt download libnspr4 libnss3 "$asound_package" >/dev/null
        for deb in ./*.deb; do
            dpkg-deb -x "$deb" "$PLAYWRIGHT_LIB_ROOT/root"
        done
    )
}

ensure_node_runtime() {
    prepend_path "$NODE_LTS_BIN"
    require_command node
    require_command npm
    require_command npx
}

ensure_npm_dependencies() {
    if [ ! -d "$REPO_ROOT/node_modules/@playwright/test" ]; then
        printf 'Installing npm dependencies for Playwright E2E...\n'
        (
            cd "$REPO_ROOT"
            npm install
        )
    fi
}

ensure_playwright_browser() {
    if [ -z "$(find_chromium_binary)" ]; then
        printf 'Installing Playwright Chromium runtime...\n'
        (
            cd "$REPO_ROOT"
            npx playwright install chromium
        )
    fi
}

ensure_chromium_runtime() {
    local chromium_binary
    local missing_libs

    chromium_binary="$(find_chromium_binary)"
    [ -n "$chromium_binary" ] || return 0

    enable_local_browser_libs
    missing_libs="$(missing_chromium_libs "$chromium_binary")"
    if [ -z "$missing_libs" ]; then
        return 0
    fi

    case "$missing_libs" in
        *libasound.so.2*|*libnspr4.so*|*libnss3.so*|*libnssutil3.so*|*libsmime3.so*)
            printf 'Bootstrapping local Chromium shared libraries...\n'
            bootstrap_local_browser_libs
            enable_local_browser_libs
            missing_libs="$(missing_chromium_libs "$chromium_binary")"
            if [ -n "$missing_libs" ]; then
                printf 'Chromium still has missing shared libraries:\n%s\n' "$missing_libs" >&2
                exit 1
            fi
            ;;
        *)
            printf 'Chromium is missing unsupported shared libraries:\n%s\n' "$missing_libs" >&2
            exit 1
            ;;
    esac
}

ensure_netbox_reachable() {
    require_command curl

    local http_code
    http_code="$(curl -sS -o /dev/null -w '%{http_code}' "$NETBOX_E2E_BASE_URL/login/" || true)"
    case "$http_code" in
        200|301|302|303|307|308)
            ;;
        *)
            printf 'NetBox is not reachable at %s (HTTP %s). Start it with ./dev.sh start before running E2E.\n' \
                "$NETBOX_E2E_BASE_URL" "$http_code" >&2
            exit 1
            ;;
    esac
}

prepare_e2e_runtime() {
    ensure_node_runtime
    ensure_npm_dependencies
    ensure_playwright_browser
    ensure_chromium_runtime
}

run_playwright() {
    local mode="$1"
    shift || true

    local extra_args=()
    case "$mode" in
        headed)
            extra_args+=(--headed)
            ;;
        ui)
            extra_args+=(--ui)
            ;;
        run)
            ;;
        *)
            printf 'Unexpected mode: %s\n' "$mode" >&2
            exit 1
            ;;
    esac

    prepare_e2e_runtime
    ensure_netbox_reachable

    (
        cd "$REPO_ROOT"
        export NETBOX_E2E_BASE_URL
        exec npx playwright test "${extra_args[@]}" "$@"
    )
}

command_name="${1:-run}"
case "$command_name" in
    run)
        if [ "$#" -gt 0 ]; then
            shift
        fi
        run_playwright run "$@"
        ;;
    headed)
        if [ "$#" -gt 0 ]; then
            shift
        fi
        run_playwright headed "$@"
        ;;
    ui)
        if [ "$#" -gt 0 ]; then
            shift
        fi
        run_playwright ui "$@"
        ;;
    install)
        if [ "$#" -gt 0 ]; then
            shift
        fi
        prepare_e2e_runtime
        printf 'Playwright E2E runtime is ready.\n'
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        run_playwright run "$@"
        ;;
esac