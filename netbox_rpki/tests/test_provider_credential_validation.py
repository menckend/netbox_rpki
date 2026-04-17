from urllib.error import HTTPError, URLError
from unittest.mock import MagicMock, patch

from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_credential_validation import validate_provider_account_credentials
from netbox_rpki.tests.utils import create_test_organization, create_test_provider_account


def _mock_urlopen_response(*, status=200, content_type='application/json', body=b'{}'):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.status = status
    response.headers = {'Content-Type': content_type}
    response.read.return_value = body
    return response


class ProviderCredentialValidationServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='provider-credential-validation-org',
            name='Provider Credential Validation Org',
        )
        cls.arin_account = create_test_provider_account(
            name='ARIN Credential Validation',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            org_handle='ORG-CREDENTIAL-ARIN',
            api_key='arin-token',
            api_base_url='https://reg.arin.net',
        )
        cls.krill_account = create_test_provider_account(
            name='Krill Credential Validation',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-CREDENTIAL-KRILL',
            ca_handle='krill-ca',
            api_key='krill-token',
            api_base_url='https://krill.example.invalid',
        )

    def test_credential_validation_skips_live_probe_when_required_fields_are_missing(self):
        missing_account = create_test_provider_account(
            name='Missing Provider Credentials',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='',
            ca_handle='',
            api_key='',
            api_base_url='',
        )

        with patch('netbox_rpki.services.provider_credential_validation.urlopen') as urlopen_mock:
            result = validate_provider_account_credentials(missing_account)

        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['result_kind'], 'configuration_error')
        self.assertEqual(result['checks'][0]['code'], 'credential_fields')
        self.assertEqual(result['checks'][0]['status'], 'failed')
        self.assertEqual(result['checks'][1]['status'], 'skipped')
        urlopen_mock.assert_not_called()

    def test_arin_credential_validation_reports_successful_safe_probe(self):
        with patch(
            'netbox_rpki.services.provider_credential_validation.urlopen',
            return_value=_mock_urlopen_response(
                content_type='application/xml',
                body=b'<roaSpecs/>',
            ),
        ) as urlopen_mock:
            result = validate_provider_account_credentials(self.arin_account)

        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['result_kind'], 'ok')
        self.assertEqual(result['checks'][1]['endpoint_label'], 'ARIN hosted ROA authorization endpoint')
        self.assertEqual(result['checks'][1]['http_status'], 200)
        self.assertEqual(result['checks'][1]['response_content_type'], 'application/xml')
        urlopen_mock.assert_called_once()

    def test_krill_credential_validation_reports_successful_safe_probe(self):
        with patch(
            'netbox_rpki.services.provider_credential_validation.urlopen',
            return_value=_mock_urlopen_response(
                content_type='application/json',
                body=b'{"ca":"ok"}',
            ),
        ) as urlopen_mock:
            result = validate_provider_account_credentials(self.krill_account)

        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['result_kind'], 'ok')
        self.assertEqual(result['checks'][1]['endpoint_label'], 'Krill CA metadata endpoint')
        self.assertIn('/api/v1/cas/krill-ca', result['checks'][1]['url'])
        urlopen_mock.assert_called_once()

    def test_credential_validation_distinguishes_auth_permission_and_network_failures(self):
        scenarios = (
            (
                HTTPError(
                    url='https://reg.arin.net/rest/roa/ORG',
                    code=401,
                    msg='Unauthorized',
                    hdrs=None,
                    fp=None,
                ),
                'auth_failure',
            ),
            (
                HTTPError(
                    url='https://reg.arin.net/rest/roa/ORG',
                    code=403,
                    msg='Forbidden',
                    hdrs=None,
                    fp=None,
                ),
                'permission_failure',
            ),
            (
                URLError('connection refused'),
                'network_failure',
            ),
        )

        for exception, expected_kind in scenarios:
            with self.subTest(expected_kind=expected_kind):
                with patch(
                    'netbox_rpki.services.provider_credential_validation.urlopen',
                    side_effect=exception,
                ):
                    result = validate_provider_account_credentials(self.arin_account)
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['result_kind'], expected_kind)
                self.assertEqual(result['checks'][1]['result_kind'], expected_kind)
