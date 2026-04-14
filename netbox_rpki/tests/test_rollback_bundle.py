from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from netbox_rpki import models as rpki_models
from netbox_rpki.services import (
    ProviderWriteError,
    apply_aspa_rollback_bundle,
    apply_roa_rollback_bundle,
    approve_rollback_bundle,
)
from netbox_rpki.tests.base import PluginAPITestCase, PluginViewTestCase
from netbox_rpki.tests.utils import (
    create_test_aspa_change_plan,
    create_test_aspa_change_plan_rollback_bundle,
    create_test_organization,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_provider_sync_run,
    create_test_roa_change_plan,
    create_test_roa_change_plan_rollback_bundle,
)


class RollbackBundleServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='rollback-org', name='Rollback Org')
        cls.provider_account = create_test_provider_account(
            name='Rollback Krill Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-ROLLBACK',
            ca_handle='ca-rollback',
            api_base_url='https://krill.example.invalid',
            api_key='rollback-token',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Rollback Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

    def test_approve_rollback_bundle_records_governance_metadata(self):
        plan = create_test_roa_change_plan(
            name='Rollback Source Plan',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
        )
        bundle = create_test_roa_change_plan_rollback_bundle(
            name='Rollback Bundle',
            source_plan=plan,
            rollback_delta_json={'added': [], 'removed': []},
        )

        approve_rollback_bundle(
            bundle,
            approved_by='rollback-approver',
            ticket_reference='RB-123',
            change_reference='CAB-RB',
            notes='Approved rollback.',
        )
        bundle.refresh_from_db()

        self.assertEqual(bundle.status, rpki_models.RollbackBundleStatus.APPROVED)
        self.assertEqual(bundle.approved_by, 'rollback-approver')
        self.assertEqual(bundle.ticket_reference, 'RB-123')
        self.assertEqual(bundle.change_reference, 'CAB-RB')
        self.assertEqual(bundle.notes, 'Approved rollback.')

    def test_apply_roa_rollback_bundle_submits_delta_and_records_followup_sync(self):
        plan = create_test_roa_change_plan(
            name='ROA Rollback Source Plan',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
        )
        bundle = create_test_roa_change_plan_rollback_bundle(
            name='ROA Rollback Bundle',
            source_plan=plan,
            status=rpki_models.RollbackBundleStatus.APPROVED,
            rollback_delta_json={
                'added': [{'asn': 65001, 'prefix': '10.0.0.0/24', 'max_length': 24}],
                'removed': [],
            },
            item_count=1,
        )
        followup_snapshot = create_test_provider_snapshot(
            name='ROA Rollback Follow-Up Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_sync_run = create_test_provider_sync_run(
            name='ROA Rollback Follow-Up Sync Run',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=followup_snapshot,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_route_delta',
            return_value={'message': 'rollback accepted'},
        ) as submit_mock:
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                return_value=(followup_sync_run, followup_snapshot),
            ):
                bundle = apply_roa_rollback_bundle(bundle, requested_by='rollback-user')

        bundle.refresh_from_db()
        self.assertEqual(bundle.status, rpki_models.RollbackBundleStatus.APPLIED)
        self.assertEqual(bundle.apply_requested_by, 'rollback-user')
        self.assertEqual(bundle.apply_response_json['provider_response'], {'message': 'rollback accepted'})
        self.assertEqual(bundle.apply_response_json['followup_sync']['provider_sync_run_id'], followup_sync_run.pk)
        submit_mock.assert_called_once_with(self.provider_account, bundle.rollback_delta_json)

    def test_apply_aspa_rollback_bundle_submits_delta_and_records_followup_sync(self):
        plan = create_test_aspa_change_plan(
            name='ASPA Rollback Source Plan',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
        )
        bundle = create_test_aspa_change_plan_rollback_bundle(
            name='ASPA Rollback Bundle',
            source_plan=plan,
            status=rpki_models.RollbackBundleStatus.APPROVED,
            rollback_delta_json={
                'added': [{'customer_asn': 65010, 'provider_asns': [65011]}],
                'removed': [],
            },
            item_count=1,
        )
        followup_snapshot = create_test_provider_snapshot(
            name='ASPA Rollback Follow-Up Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_sync_run = create_test_provider_sync_run(
            name='ASPA Rollback Follow-Up Sync Run',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=followup_snapshot,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_aspa_delta',
            return_value={'message': 'rollback accepted'},
        ) as submit_mock:
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                return_value=(followup_sync_run, followup_snapshot),
            ):
                bundle = apply_aspa_rollback_bundle(bundle, requested_by='rollback-user')

        bundle.refresh_from_db()
        self.assertEqual(bundle.status, rpki_models.RollbackBundleStatus.APPLIED)
        self.assertEqual(bundle.apply_requested_by, 'rollback-user')
        self.assertEqual(bundle.apply_response_json['provider_response'], {'message': 'rollback accepted'})
        self.assertEqual(bundle.apply_response_json['followup_sync']['provider_sync_run_id'], followup_sync_run.pk)
        submit_mock.assert_called_once_with(self.provider_account, bundle.rollback_delta_json)

    def test_apply_rollback_bundle_requires_approved_status(self):
        plan = create_test_roa_change_plan(
            name='Unapproved Rollback Source Plan',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
        )
        bundle = create_test_roa_change_plan_rollback_bundle(
            name='Unapproved Rollback Bundle',
            source_plan=plan,
            status=rpki_models.RollbackBundleStatus.AVAILABLE,
        )

        with self.assertRaisesMessage(ProviderWriteError, 'cannot be applied'):
            apply_roa_rollback_bundle(bundle, requested_by='rollback-user')


class RollbackBundleViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='rollback-view-org', name='Rollback View Org')
        cls.provider_account = create_test_provider_account(
            name='Rollback View Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-ROLLBACK-VIEW',
            ca_handle='ca-rollback-view',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Rollback View Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.roa_plan = create_test_roa_change_plan(
            name='Rollback View Source Plan',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.roa_bundle = create_test_roa_change_plan_rollback_bundle(
            name='Rollback View Bundle',
            source_plan=cls.roa_plan,
            rollback_delta_json={'added': [{'asn': 65001, 'prefix': '10.1.0.0/24', 'max_length': 24}], 'removed': []},
        )

    def test_detail_view_shows_approve_button(self):
        self.add_permissions(
            'netbox_rpki.view_roachangeplanrollbackbundle',
            'netbox_rpki.change_roachangeplanrollbackbundle',
        )

        response = self.client.get(self.roa_bundle.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Approve Rollback')

    def test_approve_view_updates_bundle(self):
        self.add_permissions(
            'netbox_rpki.view_roachangeplanrollbackbundle',
            'netbox_rpki.change_roachangeplanrollbackbundle',
        )
        url = reverse('plugins:netbox_rpki:roachangeplanrollbackbundle_approve', kwargs={'pk': self.roa_bundle.pk})

        response = self.client.post(
            url,
            {
                'confirm': True,
                'ticket_reference': 'UI-RB-1',
                'notes': 'Approved in UI.',
            },
        )

        self.assertRedirects(response, self.roa_bundle.get_absolute_url())
        self.roa_bundle.refresh_from_db()
        self.assertEqual(self.roa_bundle.status, rpki_models.RollbackBundleStatus.APPROVED)
        self.assertEqual(self.roa_bundle.ticket_reference, 'UI-RB-1')

    def test_apply_view_updates_bundle(self):
        self.add_permissions(
            'netbox_rpki.view_roachangeplanrollbackbundle',
            'netbox_rpki.change_roachangeplanrollbackbundle',
        )
        self.roa_bundle.status = rpki_models.RollbackBundleStatus.APPROVED
        self.roa_bundle.save(update_fields=('status',))
        followup_snapshot = create_test_provider_snapshot(
            name='Rollback View Follow-Up Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_sync_run = create_test_provider_sync_run(
            name='Rollback View Follow-Up Sync Run',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=followup_snapshot,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_route_delta',
            return_value={'message': 'rollback accepted'},
        ):
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                return_value=(followup_sync_run, followup_snapshot),
            ):
                response = self.client.post(
                    reverse('plugins:netbox_rpki:roachangeplanrollbackbundle_apply', kwargs={'pk': self.roa_bundle.pk}),
                    {'confirm': True},
                )

        self.assertRedirects(response, self.roa_bundle.get_absolute_url())
        self.roa_bundle.refresh_from_db()
        self.assertEqual(self.roa_bundle.status, rpki_models.RollbackBundleStatus.APPLIED)


class RollbackBundleAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='rollback-api-org', name='Rollback API Org')
        cls.provider_account = create_test_provider_account(
            name='Rollback API Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-ROLLBACK-API',
            ca_handle='ca-rollback-api',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Rollback API Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.roa_plan = create_test_roa_change_plan(
            name='Rollback API Source Plan',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.roa_bundle = create_test_roa_change_plan_rollback_bundle(
            name='Rollback API Bundle',
            source_plan=cls.roa_plan,
            rollback_delta_json={'added': [{'asn': 65001, 'prefix': '10.2.0.0/24', 'max_length': 24}], 'removed': []},
        )
        cls.aspa_plan = create_test_aspa_change_plan(
            name='ASPA Rollback API Source Plan',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.aspa_bundle = create_test_aspa_change_plan_rollback_bundle(
            name='ASPA Rollback API Bundle',
            source_plan=cls.aspa_plan,
            rollback_delta_json={'added': [{'customer_asn': 65010, 'provider_asns': [65011]}], 'removed': []},
            status=rpki_models.RollbackBundleStatus.APPROVED,
        )

    def test_roa_rollback_bundle_approve_action(self):
        self.add_permissions(
            'netbox_rpki.view_roachangeplanrollbackbundle',
            'netbox_rpki.change_roachangeplanrollbackbundle',
        )
        url = reverse('plugins-api:netbox_rpki-api:roachangeplanrollbackbundle-approve', kwargs={'pk': self.roa_bundle.pk})

        response = self.client.post(
            url,
            {'ticket_reference': 'API-RB-1', 'notes': 'Approved via API.'},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.roa_bundle.refresh_from_db()
        self.assertEqual(self.roa_bundle.status, rpki_models.RollbackBundleStatus.APPROVED)
        self.assertEqual(response.data['ticket_reference'], 'API-RB-1')

    def test_aspa_rollback_bundle_apply_action(self):
        self.add_permissions(
            'netbox_rpki.view_aspachangeplanrollbackbundle',
            'netbox_rpki.change_aspachangeplanrollbackbundle',
        )
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplanrollbackbundle-apply', kwargs={'pk': self.aspa_bundle.pk})
        followup_snapshot = create_test_provider_snapshot(
            name='Rollback API Follow-Up Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_sync_run = create_test_provider_sync_run(
            name='Rollback API Follow-Up Sync Run',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=followup_snapshot,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_aspa_delta',
            return_value={'message': 'rollback accepted'},
        ):
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                return_value=(followup_sync_run, followup_snapshot),
            ):
                response = self.client.post(
                    url,
                    {},
                    format='json',
                    **self.header,
                )

        self.assertHttpStatus(response, 200)
        self.aspa_bundle.refresh_from_db()
        self.assertEqual(self.aspa_bundle.status, rpki_models.RollbackBundleStatus.APPLIED)
        self.assertEqual(response.data['apply_requested_by'], self.user.username)
