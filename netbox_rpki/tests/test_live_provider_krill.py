from __future__ import annotations

from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_credential_validation import validate_provider_account_credentials
from netbox_rpki.tests.live_backend import skip_unless_live_provider
from netbox_rpki.tests.live_krill import (
    configured_live_krill_api_base_url,
    configured_live_krill_api_token,
    configured_live_krill_ca_handle,
    configured_live_krill_org_handle,
    skip_unless_live_krill_env,
)
from netbox_rpki.tests.utils import create_test_organization, create_test_provider_account


@skip_unless_live_provider('krill')
@skip_unless_live_krill_env()
class LiveKrillProviderIntegrationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='live-krill-provider-org',
            name='Live Krill Provider Org',
        )

    def test_live_krill_credential_validation_passes_against_configured_target(self):
        provider_account = create_test_provider_account(
            name='Live Krill Provider Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle=configured_live_krill_org_handle(),
            ca_handle=configured_live_krill_ca_handle(),
            api_key=configured_live_krill_api_token(),
            api_base_url=configured_live_krill_api_base_url(),
        )

        result = validate_provider_account_credentials(provider_account)

        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['result_kind'], 'ok')
        self.assertFalse(result['mutates_provider_state'])
        self.assertEqual(result['checks'][0]['status'], 'passed')
        self.assertEqual(result['checks'][1]['status'], 'passed')
