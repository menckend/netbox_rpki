from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from netbox_rpki.tests.live_backend import (
    LIVE_PROVIDER_ENABLE_ENV,
    LIVE_PROVIDER_NAME_ENV,
    configured_live_provider_name,
    live_provider_tests_enabled,
)
from netbox_rpki.tests.live_krill import (
    LIVE_KRILL_API_BASE_URL_ENV,
    LIVE_KRILL_API_TOKEN_ENV,
    configured_live_krill_api_base_url,
    live_krill_env_configured,
    missing_live_krill_env,
)


class LiveBackendHelperTestCase(SimpleTestCase):
    def test_live_provider_tests_enabled_recognizes_truthy_values(self):
        with patch.dict(os.environ, {LIVE_PROVIDER_ENABLE_ENV: 'true'}, clear=False):
            self.assertTrue(live_provider_tests_enabled())

    def test_live_provider_tests_enabled_defaults_to_false(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(live_provider_tests_enabled())

    def test_configured_live_provider_name_is_normalized(self):
        with patch.dict(os.environ, {LIVE_PROVIDER_NAME_ENV: ' KrIlL '}, clear=False):
            self.assertEqual(configured_live_provider_name(), 'krill')

    def test_live_krill_env_defaults_use_local_dev_values(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(configured_live_krill_api_base_url(), 'https://localhost:3001')
            self.assertEqual(missing_live_krill_env(), (LIVE_KRILL_API_TOKEN_ENV,))
            self.assertFalse(live_krill_env_configured())

    def test_live_krill_env_is_configured_when_token_is_present(self):
        with patch.dict(
            os.environ,
            {
                LIVE_KRILL_API_TOKEN_ENV: ' krill-live-token ',
                LIVE_KRILL_API_BASE_URL_ENV: ' https://krill.example.invalid ',
            },
            clear=False,
        ):
            self.assertEqual(configured_live_krill_api_base_url(), 'https://krill.example.invalid')
            self.assertEqual(missing_live_krill_env(), ())
            self.assertTrue(live_krill_env_configured())
