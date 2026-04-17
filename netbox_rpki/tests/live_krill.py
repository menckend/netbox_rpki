from __future__ import annotations

import os
from unittest import skipUnless


LIVE_KRILL_API_BASE_URL_ENV = 'NETBOX_RPKI_LIVE_KRILL_API_BASE_URL'
LIVE_KRILL_CA_HANDLE_ENV = 'NETBOX_RPKI_LIVE_KRILL_CA_HANDLE'
LIVE_KRILL_API_TOKEN_ENV = 'NETBOX_RPKI_LIVE_KRILL_API_TOKEN'
LIVE_KRILL_ORG_HANDLE_ENV = 'NETBOX_RPKI_LIVE_KRILL_ORG_HANDLE'


def configured_live_krill_api_base_url() -> str:
    return os.getenv(LIVE_KRILL_API_BASE_URL_ENV, 'https://localhost:3001').strip()


def configured_live_krill_ca_handle() -> str:
    return os.getenv(LIVE_KRILL_CA_HANDLE_ENV, 'netbox-rpki-dev').strip()


def configured_live_krill_api_token() -> str:
    return os.getenv(LIVE_KRILL_API_TOKEN_ENV, '').strip()


def configured_live_krill_org_handle() -> str:
    return os.getenv(LIVE_KRILL_ORG_HANDLE_ENV, 'PUBLIC-TESTBED').strip()


def missing_live_krill_env() -> tuple[str, ...]:
    missing = []
    if not configured_live_krill_api_token():
        missing.append(LIVE_KRILL_API_TOKEN_ENV)
    return tuple(missing)


def live_krill_env_configured() -> bool:
    return not missing_live_krill_env()


def skip_unless_live_krill_env(reason: str | None = None):
    return skipUnless(
        live_krill_env_configured(),
        reason or (
            'Set '
            f'{LIVE_KRILL_API_TOKEN_ENV} and optionally '
            f'{LIVE_KRILL_API_BASE_URL_ENV}, {LIVE_KRILL_CA_HANDLE_ENV}, and {LIVE_KRILL_ORG_HANDLE_ENV} '
            'to run live Krill integration tests.'
        ),
    )
