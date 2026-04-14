from django.test import TestCase

from netbox_rpki import detail_specs
from netbox_rpki import models as rpki_models
from netbox_rpki.tests.utils import (
    create_test_imported_certificate_observation,
    create_test_imported_publication_point,
    create_test_imported_signed_object,
    create_test_provider_account,
    create_test_provider_snapshot,
)


class DetailSpecsHelperTestCase(TestCase):
    def test_get_provider_account_family_rollups_returns_none_without_last_sync_summary(self):
        account = create_test_provider_account(last_sync_summary_json={})

        self.assertIsNone(detail_specs.get_provider_account_family_rollups(account))


class DetailSpecsProviderSyncTestCase(TestCase):
    def test_get_provider_account_family_rollups_returns_json_when_summary_exists(self):
        account = create_test_provider_account(
            last_sync_summary_json={
                'families': {
                    rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS: {
                        'status': rpki_models.ProviderSyncFamilyStatus.COMPLETED,
                    },
                },
            },
        )

        rendered = detail_specs.get_provider_account_family_rollups(account)

        self.assertIsNotNone(rendered)
        self.assertIn('roa_authorizations', rendered)

    def test_get_provider_account_pub_obs_rollup_returns_none_without_snapshot(self):
        account = create_test_provider_account(
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='netbox-rpki-dev',
        )

        self.assertIsNone(detail_specs.get_provider_account_pub_obs_rollup(account))

    def test_get_provider_account_pub_obs_rollup_returns_json_for_completed_snapshot(self):
        account = create_test_provider_account(
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='netbox-rpki-dev',
        )
        snapshot = create_test_provider_snapshot(provider_account=account, organization=account.organization)
        create_test_imported_certificate_observation(
            provider_snapshot=snapshot,
            organization=account.organization,
            certificate_key='detail-spec-cert',
        )
        create_test_imported_publication_point(
            provider_snapshot=snapshot,
            organization=account.organization,
            publication_uri='rsync://example.invalid/repo/detail-spec/',
            last_exchange_result='failed',
        )

        rendered = detail_specs.get_provider_account_pub_obs_rollup(account)

        self.assertIsNotNone(rendered)
        self.assertIn('certificate_observations', rendered)
        self.assertIn('publication_points', rendered)

    def test_get_provider_snapshot_signed_object_type_breakdown_returns_none_without_signed_objects(self):
        snapshot = create_test_provider_snapshot()

        self.assertIsNone(detail_specs.get_provider_snapshot_signed_object_type_breakdown(snapshot))

    def test_get_provider_snapshot_signed_object_type_breakdown_returns_json_when_present(self):
        snapshot = create_test_provider_snapshot()
        create_test_imported_signed_object(
            provider_snapshot=snapshot,
            organization=snapshot.organization,
            publication_uri='rsync://example.invalid/repo/breakdown/',
            signed_object_uri='rsync://example.invalid/repo/breakdown/object-1.mft',
            signed_object_type=rpki_models.SignedObjectType.MANIFEST,
        )

        rendered = detail_specs.get_provider_snapshot_signed_object_type_breakdown(snapshot)

        self.assertIsNotNone(rendered)
        self.assertIn('manifest', rendered)
