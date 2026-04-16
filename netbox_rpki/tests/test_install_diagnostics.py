import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from netbox_rpki import models as rpki_models
from netbox_rpki.services.install_diagnostics import build_install_diagnostic_report
from netbox_rpki.tests.utils import (
    create_test_irr_source,
    create_test_organization,
    create_test_provider_account,
    create_test_validator_instance,
)


class InstallDiagnosticReportTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='install-diagnostic-org',
            name='Install Diagnostic Org',
        )
        cls.arin_provider = create_test_provider_account(
            name='Diagnostic ARIN Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            org_handle='ORG-DIAG-ARIN',
            ca_handle='',
            api_key='arin-token',
            api_base_url='https://reg.arin.net',
        )
        cls.krill_provider = create_test_provider_account(
            name='Diagnostic Krill Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-DIAG-KRILL',
            ca_handle='',
            api_key='krill-token',
            api_base_url='https://krill.example.invalid',
        )
        cls.apply_capable_irr = create_test_irr_source(
            name='Diagnostic Apply IRR',
            organization=cls.organization,
            slug='diagnostic-apply-irr',
            write_support_mode=rpki_models.IrrWriteSupportMode.APPLY_SUPPORTED,
            query_base_url='https://irrd.example.invalid',
            api_key='',
        )
        cls.disabled_irr = create_test_irr_source(
            name='Diagnostic Disabled IRR',
            organization=cls.organization,
            slug='diagnostic-disabled-irr',
            enabled=False,
            query_base_url='',
            api_key='',
        )
        cls.validator = create_test_validator_instance(
            name='Diagnostic Validator',
            organization=cls.organization,
            base_url='',
        )

    @patch('netbox_rpki.services.install_diagnostics._redis_ping', return_value=(True, 'ping ok'))
    @patch('netbox_rpki.services.install_diagnostics._pending_plugin_migrations', return_value=[])
    def test_report_flags_fatal_and_advisory_issues_with_capability_aware_provider_checks(self, _migrations_mock, _redis_mock):
        report = build_install_diagnostic_report()

        self.assertEqual(report['overall_status'], 'fatal')
        self.assertGreater(report['summary']['fatal_count'], 0)
        self.assertGreater(report['summary']['advisory_count'], 0)

        checks = {(check['code'], check['scope']): check for check in report['checks']}

        self.assertEqual(
            checks[('providers.credentials', f'provider_account:{self.arin_provider.pk}')]['status'],
            'ok',
        )
        self.assertEqual(
            checks[('providers.credentials', f'provider_account:{self.krill_provider.pk}')]['status'],
            'fatal',
        )
        self.assertIn(
            'Krill CA handle is blank',
            checks[('providers.credentials', f'provider_account:{self.krill_provider.pk}')]['summary'],
        )
        self.assertEqual(
            checks[('irr.credentials', f'irr_source:{self.apply_capable_irr.pk}')]['status'],
            'fatal',
        )
        self.assertEqual(
            checks[('irr.credentials', f'irr_source:{self.disabled_irr.pk}')]['status'],
            'advisory',
        )
        self.assertEqual(
            checks[('validators.live_api', f'validator_instance:{self.validator.pk}')]['status'],
            'advisory',
        )

    @override_settings(PLUGINS=['netbox.tests.dummy_plugin'])
    @patch('netbox_rpki.services.install_diagnostics._redis_ping', return_value=(True, 'ping ok'))
    @patch('netbox_rpki.services.install_diagnostics._pending_plugin_migrations', return_value=[])
    def test_report_flags_missing_plugin_registration_in_settings(self, _migrations_mock, _redis_mock):
        report = build_install_diagnostic_report()
        plugin_check = next(
            check for check in report['checks']
            if check['code'] == 'plugin.settings_registration'
        )

        self.assertEqual(plugin_check['status'], 'fatal')
        self.assertIn('missing from settings.PLUGINS', plugin_check['summary'])


class DiagnoseNetboxRpkiCommandTestCase(TestCase):
    def test_text_output_renders_summary_and_checks(self):
        stdout = StringIO()
        with patch(
            'netbox_rpki.management.commands.diagnose_netbox_rpki.build_install_diagnostic_report',
            return_value={
                'schema_version': 1,
                'generated_at': '2026-04-16T12:00:00+00:00',
                'plugin_version': '0+test',
                'overall_status': 'advisory',
                'summary': {
                    'check_count': 2,
                    'fatal_count': 0,
                    'advisory_count': 1,
                    'ok_count': 1,
                },
                'checks': [
                    {
                        'code': 'plugin.settings_registration',
                        'status': 'ok',
                        'scope': 'global',
                        'summary': 'Plugin is present in settings.PLUGINS.',
                        'remediation': '',
                        'details': {},
                    },
                    {
                        'code': 'validators.live_api',
                        'status': 'advisory',
                        'scope': 'validator_instance:5',
                        'summary': 'Validator instance "Lab Validator" has no base_url; live API imports are unavailable.',
                        'remediation': 'Set base_url.',
                        'details': {},
                    },
                ],
            },
        ):
            call_command('diagnose_netbox_rpki', stdout=stdout)

        rendered = stdout.getvalue()
        self.assertIn('netbox_rpki install diagnostic', rendered)
        self.assertIn('Overall status: advisory', rendered)
        self.assertIn('[OK] plugin.settings_registration [global]', rendered)
        self.assertIn('[ADVISORY] validators.live_api [validator_instance:5]', rendered)

    def test_json_output_is_machine_readable(self):
        stdout = StringIO()
        with patch(
            'netbox_rpki.management.commands.diagnose_netbox_rpki.build_install_diagnostic_report',
            return_value={
                'schema_version': 1,
                'generated_at': '2026-04-16T12:00:00+00:00',
                'plugin_version': '0+test',
                'overall_status': 'fatal',
                'summary': {
                    'check_count': 1,
                    'fatal_count': 1,
                    'advisory_count': 0,
                    'ok_count': 0,
                },
                'checks': [
                    {
                        'code': 'database.migrations',
                        'status': 'fatal',
                        'scope': 'global',
                        'summary': 'Pending migrations detected.',
                        'remediation': 'Run migrate.',
                        'details': {'pending_migrations': ['0056_example']},
                    },
                ],
            },
        ):
            call_command('diagnose_netbox_rpki', '--format', 'json', stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload['overall_status'], 'fatal')
        self.assertEqual(payload['checks'][0]['code'], 'database.migrations')
