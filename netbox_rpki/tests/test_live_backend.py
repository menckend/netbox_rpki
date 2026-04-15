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
