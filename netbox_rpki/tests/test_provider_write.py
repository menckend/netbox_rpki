from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from netbox_rpki import models as rpki_models
from netbox_rpki.services import (
    ProviderWriteError,
    apply_roa_change_plan_provider_write,
    approve_roa_change_plan,
    build_roa_change_plan_delta,
    create_roa_change_plan,
    derive_roa_intents,
    preview_roa_change_plan_provider_write,
    reconcile_roa_intents,
)
from netbox_rpki.tests.base import PluginAPITestCase, PluginViewTestCase
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_imported_roa_authorization,
    create_test_organization,
    create_test_prefix,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_provider_sync_run,
    create_test_roa_change_plan,
    create_test_routing_intent_profile,
)


class ProviderWriteServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-write-org', name='Provider Write Org')
        cls.primary_prefix = create_test_prefix('10.77.0.0/24')
        cls.primary_asn = create_test_asn(65077)
        cls.profile = create_test_routing_intent_profile(
            name='Provider Write Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.primary_prefix.pk}',
            asn_selector_query=f'id={cls.primary_asn.pk}',
        )
        cls.derivation_run = derive_roa_intents(cls.profile)
        cls.provider_account = create_test_provider_account(
            name='Krill Write Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-WRITE',
            ca_handle='ca-write',
            api_base_url='https://krill.example.invalid',
            api_key='krill-write-token',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Krill Write Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.orphaned_prefix = create_test_prefix('10.99.0.0/24')
        cls.orphaned_asn = create_test_asn(65099)
        cls.orphaned_import = create_test_imported_roa_authorization(
            name='Krill Orphaned Authorization',
            provider_snapshot=cls.provider_snapshot,
            organization=cls.organization,
            prefix=cls.orphaned_prefix,
            origin_asn=cls.orphaned_asn,
            max_length=24,
            payload_json={'comment': 'orphaned test route'},
        )
        cls.reconciliation_run = reconcile_roa_intents(
            cls.derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.plan = create_roa_change_plan(cls.reconciliation_run)

    def test_provider_backed_plan_targets_provider_and_populates_item_metadata(self):
        self.assertEqual(self.plan.provider_account, self.provider_account)
        self.assertEqual(self.plan.provider_snapshot, self.provider_snapshot)

        create_item = self.plan.items.get(action_type=rpki_models.ROAChangePlanAction.CREATE)
        withdraw_item = self.plan.items.get(action_type=rpki_models.ROAChangePlanAction.WITHDRAW)

        self.assertEqual(create_item.provider_operation, rpki_models.ProviderWriteOperation.ADD_ROUTE)
        self.assertEqual(
            create_item.provider_payload_json,
            {'asn': self.primary_asn.asn, 'prefix': '10.77.0.0/24', 'max_length': 24},
        )
        self.assertEqual(withdraw_item.provider_operation, rpki_models.ProviderWriteOperation.REMOVE_ROUTE)
        self.assertEqual(
            withdraw_item.provider_payload_json,
            {
                'asn': self.orphaned_asn.asn,
                'prefix': '10.99.0.0/24',
                'max_length': 24,
                'comment': 'orphaned test route',
            },
        )

    def test_build_krill_delta_translates_create_and_withdraw_items(self):
        delta = build_roa_change_plan_delta(self.plan)

        self.assertEqual(
            delta,
            {
                'added': [
                    {'asn': self.primary_asn.asn, 'prefix': '10.77.0.0/24', 'max_length': 24},
                ],
                'removed': [
                    {
                        'asn': self.orphaned_asn.asn,
                        'prefix': '10.99.0.0/24',
                        'max_length': 24,
                        'comment': 'orphaned test route',
                    },
                ],
            },
        )

    def test_preview_records_audit_without_applying(self):
        execution, delta = preview_roa_change_plan_provider_write(self.plan, requested_by='preview-user')

        self.assertEqual(execution.execution_mode, rpki_models.ProviderWriteExecutionMode.PREVIEW)
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(execution.requested_by, 'preview-user')
        self.assertEqual(execution.request_payload_json, delta)
        self.assertEqual(self.plan.status, rpki_models.ROAChangePlanStatus.DRAFT)

    def test_approve_transitions_plan_to_approved(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Approval Plan')

        approve_roa_change_plan(plan, approved_by='approval-user')
        plan.refresh_from_db()

        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.APPROVED)
        self.assertIsNotNone(plan.approved_at)
        self.assertEqual(plan.approved_by, 'approval-user')

    def test_apply_submits_delta_records_execution_and_triggers_followup_sync(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Apply Plan')
        approve_roa_change_plan(plan, approved_by='apply-approver')
        followup_snapshot = create_test_provider_snapshot(
            name='Follow-Up Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_sync_run = create_test_provider_sync_run(
            name='Follow-Up Sync Run',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=followup_snapshot,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_route_delta',
            return_value={'message': 'accepted'},
        ) as submit_mock:
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                return_value=(followup_sync_run, followup_snapshot),
            ) as sync_mock:
                execution, delta = apply_roa_change_plan_provider_write(plan, requested_by='apply-user')

        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.APPLIED)
        self.assertIsNotNone(plan.apply_started_at)
        self.assertEqual(plan.apply_requested_by, 'apply-user')
        self.assertIsNotNone(plan.applied_at)
        self.assertEqual(execution.execution_mode, rpki_models.ProviderWriteExecutionMode.APPLY)
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(execution.followup_sync_run, followup_sync_run)
        self.assertEqual(execution.followup_provider_snapshot, followup_snapshot)
        self.assertEqual(execution.request_payload_json, delta)
        self.assertEqual(execution.response_payload_json['provider_response'], {'message': 'accepted'})
        submit_mock.assert_called_once_with(self.provider_account, delta)
        sync_mock.assert_called_once_with(
            self.provider_account,
            snapshot_name=sync_mock.call_args.kwargs['snapshot_name'],
        )

    def test_apply_rejects_repeat_apply(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Repeat Apply Plan')
        approve_roa_change_plan(plan, approved_by='repeat-approver')

        with patch('netbox_rpki.services.provider_write._submit_krill_route_delta', return_value={}):
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                return_value=(
                    create_test_provider_sync_run(
                        name='Repeat Apply Sync Run',
                        organization=self.organization,
                        provider_account=self.provider_account,
                        provider_snapshot=create_test_provider_snapshot(
                            name='Repeat Apply Snapshot',
                            organization=self.organization,
                            provider_account=self.provider_account,
                            provider_name='Krill',
                            status=rpki_models.ValidationRunStatus.COMPLETED,
                        ),
                    ),
                    create_test_provider_snapshot(
                        name='Repeat Apply Snapshot 2',
                        organization=self.organization,
                        provider_account=self.provider_account,
                        provider_name='Krill',
                        status=rpki_models.ValidationRunStatus.COMPLETED,
                    ),
                ),
            ):
                apply_roa_change_plan_provider_write(plan)

        with self.assertRaisesMessage(ProviderWriteError, 'already been applied'):
            apply_roa_change_plan_provider_write(plan)

    def test_apply_failure_marks_plan_failed_and_records_error(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Failed Apply Plan')
        approve_roa_change_plan(plan, approved_by='failure-approver')

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_route_delta',
            side_effect=RuntimeError('krill rejected delta'),
        ):
            with self.assertRaisesMessage(ProviderWriteError, 'krill rejected delta'):
                apply_roa_change_plan_provider_write(plan, requested_by='failed-apply-user')

        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.FAILED)
        self.assertIsNotNone(plan.apply_started_at)
        self.assertEqual(plan.apply_requested_by, 'failed-apply-user')
        self.assertIsNotNone(plan.failed_at)
        execution = plan.provider_write_executions.get(execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY)
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.FAILED)
        self.assertEqual(execution.error, 'krill rejected delta')

    def test_capability_gating_rejects_unsupported_provider(self):
        unsupported_account = create_test_provider_account(
            name='ARIN Unsupported Write Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            org_handle='ORG-ARIN-WRITE',
        )
        unsupported_snapshot = create_test_provider_snapshot(
            name='ARIN Unsupported Snapshot',
            organization=self.organization,
            provider_account=unsupported_account,
            provider_name='ARIN',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        unsupported_plan = create_test_roa_change_plan(
            name='Unsupported Provider Plan',
            organization=self.organization,
            source_reconciliation_run=self.reconciliation_run,
            provider_account=unsupported_account,
            provider_snapshot=unsupported_snapshot,
        )

        with self.assertRaisesMessage(ProviderWriteError, 'does not support ROA write operations'):
            build_roa_change_plan_delta(unsupported_plan)


class ROAChangePlanActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-write-api-org', name='Provider Write API Org')
        cls.primary_prefix = create_test_prefix('10.88.0.0/24')
        cls.primary_asn = create_test_asn(65088)
        cls.profile = create_test_routing_intent_profile(
            name='Provider Write API Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.primary_prefix.pk}',
            asn_selector_query=f'id={cls.primary_asn.pk}',
        )
        cls.derivation_run = derive_roa_intents(cls.profile)
        cls.provider_account = create_test_provider_account(
            name='Provider Write API Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-API-WRITE',
            ca_handle='ca-api-write',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Provider Write API Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_imported_roa_authorization(
            name='Provider Write API Orphaned',
            provider_snapshot=cls.provider_snapshot,
            organization=cls.organization,
            prefix=create_test_prefix('10.188.0.0/24'),
            origin_asn=create_test_asn(65188),
            max_length=24,
        )
        cls.reconciliation_run = reconcile_roa_intents(
            cls.derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.plan = create_roa_change_plan(cls.reconciliation_run)

    def test_preview_action_returns_delta_and_execution(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-preview', kwargs={'pk': self.plan.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('delta', response.data)
        self.assertIn('execution', response.data)
        self.assertEqual(response.data['status'], rpki_models.ROAChangePlanStatus.DRAFT)

    def test_approve_action_transitions_plan(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-approve', kwargs={'pk': self.plan.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, rpki_models.ROAChangePlanStatus.APPROVED)
        self.assertIsNotNone(self.plan.approved_at)
        self.assertEqual(self.plan.approved_by, self.user.username)

    def test_apply_action_runs_provider_write_flow(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        approve_roa_change_plan(self.plan, approved_by='api-approver')
        followup_snapshot = create_test_provider_snapshot(
            name='Provider Write API Follow-Up Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_sync_run = create_test_provider_sync_run(
            name='Provider Write API Follow-Up Sync',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=followup_snapshot,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-apply', kwargs={'pk': self.plan.pk})

        with patch('netbox_rpki.services.provider_write._submit_krill_route_delta', return_value={'ok': True}):
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                return_value=(followup_sync_run, followup_snapshot),
            ):
                response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, rpki_models.ROAChangePlanStatus.APPLIED)
        self.assertEqual(self.plan.apply_requested_by, self.user.username)
        self.assertEqual(response.data['execution']['status'], rpki_models.ValidationRunStatus.COMPLETED)

    def test_provider_account_api_exposes_write_capability_metadata(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount')
        url = reverse('plugins-api:netbox_rpki-api:provideraccount-detail', kwargs={'pk': self.provider_account.pk})

        response = self.client.get(url, **self.header)

        self.assertHttpStatus(response, 200)
        self.assertTrue(response.data['supports_roa_write'])
        self.assertEqual(response.data['roa_write_mode'], rpki_models.ProviderRoaWriteMode.KRILL_ROUTE_DELTA)
        self.assertEqual(
            response.data['roa_write_capability']['supported_roa_plan_actions'],
            [rpki_models.ROAChangePlanAction.CREATE, rpki_models.ROAChangePlanAction.WITHDRAW],
        )

    def test_custom_actions_require_change_permission(self):
        self.add_permissions('netbox_rpki.view_roachangeplan')
        for action in ('preview', 'approve', 'apply'):
            url = reverse(f'plugins-api:netbox_rpki-api:roachangeplan-{action}', kwargs={'pk': self.plan.pk})
            response = self.client.post(url, {}, format='json', **self.header)
            with self.subTest(action=action):
                self.assertHttpStatus(response, 404)


class ROAChangePlanActionViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-write-view-org', name='Provider Write View Org')
        cls.primary_prefix = create_test_prefix('10.89.0.0/24')
        cls.primary_asn = create_test_asn(65089)
        cls.profile = create_test_routing_intent_profile(
            name='Provider Write View Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.primary_prefix.pk}',
            asn_selector_query=f'id={cls.primary_asn.pk}',
        )
        cls.derivation_run = derive_roa_intents(cls.profile)
        cls.provider_account = create_test_provider_account(
            name='Provider Write View Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-VIEW-WRITE',
            ca_handle='ca-view-write',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Provider Write View Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_imported_roa_authorization(
            name='Provider Write View Orphaned',
            provider_snapshot=cls.provider_snapshot,
            organization=cls.organization,
            prefix=create_test_prefix('10.189.0.0/24'),
            origin_asn=create_test_asn(65189),
            max_length=24,
        )
        cls.reconciliation_run = reconcile_roa_intents(
            cls.derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.plan = create_roa_change_plan(cls.reconciliation_run)

    def test_change_plan_detail_shows_preview_and_approve_buttons(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')

        response = self.client.get(self.plan.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, reverse('plugins:netbox_rpki:roachangeplan_preview', kwargs={'pk': self.plan.pk}))
        self.assertContains(response, reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': self.plan.pk}))
        self.assertNotContains(response, reverse('plugins:netbox_rpki:roachangeplan_apply', kwargs={'pk': self.plan.pk}))

    def test_preview_view_renders_delta(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')

        response = self.client.get(reverse('plugins:netbox_rpki:roachangeplan_preview', kwargs={'pk': self.plan.pk}))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Preview Provider Delta')
        self.assertContains(response, '10.89.0.0/24')

    def test_unsupported_provider_plan_hides_write_buttons(self):
        unsupported_account = create_test_provider_account(
            name='Provider Write View Unsupported Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            org_handle='ORG-VIEW-ARIN',
        )
        unsupported_snapshot = create_test_provider_snapshot(
            name='Provider Write View Unsupported Snapshot',
            organization=self.organization,
            provider_account=unsupported_account,
            provider_name='ARIN',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        unsupported_plan = create_test_roa_change_plan(
            name='Unsupported View Plan',
            organization=self.organization,
            source_reconciliation_run=self.reconciliation_run,
            provider_account=unsupported_account,
            provider_snapshot=unsupported_snapshot,
        )
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')

        response = self.client.get(unsupported_plan.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertNotContains(response, reverse('plugins:netbox_rpki:roachangeplan_preview', kwargs={'pk': unsupported_plan.pk}))
        self.assertNotContains(response, reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': unsupported_plan.pk}))
        self.assertNotContains(response, reverse('plugins:netbox_rpki:roachangeplan_apply', kwargs={'pk': unsupported_plan.pk}))