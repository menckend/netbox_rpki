from unittest.mock import patch

from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_adapters import (
    ProviderAdapterLookupError,
    get_provider_adapter,
    get_provider_adapter_by_type,
)
from netbox_rpki.tests.utils import (
    create_test_organization,
    create_test_provider_account,
    create_test_provider_snapshot,
)


class ProviderAdapterContractTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='provider-adapter-org',
            name='Provider Adapter Org',
        )
        cls.arin_account = create_test_provider_account(
            name='ARIN Adapter Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            org_handle='ORG-ARIN-ADAPTER',
            api_key='arin-token',
            api_base_url='https://reg.arin.net',
        )
        cls.krill_account = create_test_provider_account(
            name='Krill Adapter Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-KRILL-ADAPTER',
            ca_handle='ca-adapter',
            api_key='krill-token',
            api_base_url='https://krill.example.invalid',
        )

    def test_registry_resolves_supported_provider_types(self):
        self.assertEqual(get_provider_adapter(self.arin_account).provider_type, rpki_models.ProviderType.ARIN)
        self.assertEqual(get_provider_adapter(self.krill_account).provider_type, rpki_models.ProviderType.KRILL)

    def test_registry_rejects_unknown_provider_types(self):
        with self.assertRaisesMessage(ProviderAdapterLookupError, 'Provider type mystery is not supported.'):
            get_provider_adapter_by_type('mystery')

    def test_capability_contract_is_published_per_adapter(self):
        scenarios = (
            (
                self.arin_account,
                {
                    'sync_target_handle': 'ORG-ARIN-ADAPTER',
                    'supports_roa_read': True,
                    'supports_aspa_read': False,
                    'supports_certificate_inventory': False,
                    'supports_repository_metadata': False,
                    'supports_bulk_operations': False,
                    'roa_write_mode': rpki_models.ProviderRoaWriteMode.UNSUPPORTED,
                    'aspa_write_mode': rpki_models.ProviderAspaWriteMode.UNSUPPORTED,
                    'supported_sync_families': (rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,),
                },
            ),
            (
                self.krill_account,
                {
                    'sync_target_handle': 'ca-adapter',
                    'supports_roa_read': True,
                    'supports_aspa_read': True,
                    'supports_certificate_inventory': True,
                    'supports_repository_metadata': True,
                    'supports_bulk_operations': True,
                    'roa_write_mode': rpki_models.ProviderRoaWriteMode.KRILL_ROUTE_DELTA,
                    'aspa_write_mode': rpki_models.ProviderAspaWriteMode.KRILL_ASPA_DELTA,
                    'supported_sync_families': (
                        rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,
                        rpki_models.ProviderSyncFamily.ASPAS,
                        rpki_models.ProviderSyncFamily.CA_METADATA,
                        rpki_models.ProviderSyncFamily.PARENT_LINKS,
                        rpki_models.ProviderSyncFamily.CHILD_LINKS,
                        rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS,
                        rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
                        rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY,
                        rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY,
                    ),
                },
            ),
        )

        for provider_account, expected in scenarios:
            adapter = get_provider_adapter(provider_account)
            profile = adapter.profile
            with self.subTest(provider_type=provider_account.provider_type):
                self.assertEqual(adapter.sync_target_handle(provider_account), expected['sync_target_handle'])
                self.assertEqual(profile.supports_roa_read, expected['supports_roa_read'])
                self.assertEqual(profile.supports_aspa_read, expected['supports_aspa_read'])
                self.assertEqual(
                    profile.supports_certificate_inventory,
                    expected['supports_certificate_inventory'],
                )
                self.assertEqual(
                    profile.supports_repository_metadata,
                    expected['supports_repository_metadata'],
                )
                self.assertEqual(profile.supports_bulk_operations, expected['supports_bulk_operations'])
                self.assertEqual(profile.roa_write_mode, expected['roa_write_mode'])
                self.assertEqual(profile.aspa_write_mode, expected['aspa_write_mode'])
                self.assertEqual(profile.supported_sync_families, expected['supported_sync_families'])

    def test_credential_validation_hooks_are_adapter_specific(self):
        arin_account = create_test_provider_account(
            name='ARIN Missing Credentials',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            org_handle='',
            api_key='',
            api_base_url='',
        )
        krill_account = create_test_provider_account(
            name='Krill Missing Credentials',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='',
            ca_handle='',
            api_key='',
            api_base_url='',
        )

        arin_issues = get_provider_adapter(arin_account).credential_issues(arin_account)
        krill_issues = get_provider_adapter(krill_account).credential_issues(krill_account)

        self.assertEqual([issue.field_name for issue in arin_issues], ['org_handle', 'api_key', 'api_base_url'])
        self.assertEqual(
            [issue.field_name for issue in krill_issues],
            ['org_handle', 'api_key', 'api_base_url', 'ca_handle'],
        )

    def test_sync_validation_requires_krill_ca_handle(self):
        krill_account = create_test_provider_account(
            name='Krill Missing CA Handle',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-KRILL-NO-CA',
            ca_handle='',
        )

        with self.assertRaisesMessage(ValueError, 'missing a Krill CA handle'):
            get_provider_adapter(krill_account).validate_sync_account(krill_account)

    def test_sync_dispatch_uses_provider_specific_importer(self):
        arin_snapshot = create_test_provider_snapshot(
            name='ARIN Adapter Snapshot',
            organization=self.organization,
            provider_account=self.arin_account,
        )
        krill_snapshot = create_test_provider_snapshot(
            name='Krill Adapter Snapshot',
            organization=self.organization,
            provider_account=self.krill_account,
        )

        with patch(
            'netbox_rpki.services.provider_sync._import_arin_records',
            return_value={'arin': {'records_imported': 1}},
        ) as arin_mock:
            result = get_provider_adapter(self.arin_account).sync_inventory(self.arin_account, arin_snapshot)
        self.assertEqual(result, {'arin': {'records_imported': 1}})
        arin_mock.assert_called_once_with(self.arin_account, arin_snapshot, sync_run=None)

        with patch(
            'netbox_rpki.services.provider_sync._import_krill_records',
            return_value={'krill': {'records_imported': 2}},
        ) as krill_mock:
            result = get_provider_adapter(self.krill_account).sync_inventory(self.krill_account, krill_snapshot)
        self.assertEqual(result, {'krill': {'records_imported': 2}})
        krill_mock.assert_called_once_with(self.krill_account, krill_snapshot, sync_run=None)

    def test_standardized_unsupported_write_handling(self):
        adapter = get_provider_adapter(self.arin_account)

        with self.assertRaisesMessage(ValueError, 'does not support ROA write operations'):
            adapter.ensure_roa_write_supported(self.arin_account)
        with self.assertRaisesMessage(ValueError, 'does not support ASPA write operations'):
            adapter.ensure_aspa_write_supported(self.arin_account)

    def test_krill_write_hooks_delegate_to_existing_transport_helpers(self):
        adapter = get_provider_adapter(self.krill_account)
        roa_delta = {'added': [{'asn': 64496, 'prefix': '192.0.2.0/24', 'max_length': 24}], 'removed': []}
        aspa_delta = {'added': [{'customer_asn': 64496, 'provider_asns': [64497]}], 'removed': []}

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_route_delta',
            return_value={'roa': 'ok'},
        ) as route_mock:
            self.assertEqual(adapter.apply_roa_delta(self.krill_account, roa_delta), {'roa': 'ok'})
        route_mock.assert_called_once_with(self.krill_account, roa_delta)

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_aspa_delta',
            return_value={'aspa': 'ok'},
        ) as aspa_mock:
            self.assertEqual(adapter.apply_aspa_delta(self.krill_account, aspa_delta), {'aspa': 'ok'})
        aspa_mock.assert_called_once_with(self.krill_account, aspa_delta)
