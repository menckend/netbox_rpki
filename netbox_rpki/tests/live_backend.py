from __future__ import annotations

import os
from unittest import skipUnless


LIVE_PROVIDER_ENABLE_ENV = 'NETBOX_RPKI_ENABLE_LIVE_PROVIDER_TESTS'
LIVE_PROVIDER_NAME_ENV = 'NETBOX_RPKI_LIVE_PROVIDER'
_TRUTHY_VALUES = {'1', 'true', 'yes', 'on'}


def live_provider_tests_enabled() -> bool:
    value = os.getenv(LIVE_PROVIDER_ENABLE_ENV, '')
    return value.strip().lower() in _TRUTHY_VALUES


def configured_live_provider_name() -> str:
    return os.getenv(LIVE_PROVIDER_NAME_ENV, '').strip().lower()


def skip_unless_live_provider_tests_enabled(reason: str | None = None):
    return skipUnless(
        live_provider_tests_enabled(),
        reason or (
            f'Set {LIVE_PROVIDER_ENABLE_ENV}=1 to run live-provider integration tests.'
        ),
    )


def skip_unless_live_provider(provider_name: str, reason: str | None = None):
    normalized_provider = provider_name.strip().lower()
    return skipUnless(
        live_provider_tests_enabled() and configured_live_provider_name() == normalized_provider,
        reason or (
            f'Set {LIVE_PROVIDER_ENABLE_ENV}=1 and '
            f'{LIVE_PROVIDER_NAME_ENV}={normalized_provider} to run this live-provider integration test.'
        ),
    )
