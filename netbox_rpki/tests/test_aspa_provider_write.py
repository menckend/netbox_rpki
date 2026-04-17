from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services import (
    ProviderWriteError,
    apply_aspa_change_plan_provider_write,
    approve_aspa_change_plan,
    build_aspa_change_plan_delta,
    create_aspa_change_plan,
    preview_aspa_change_plan_provider_write,
    reconcile_aspa_intents,
)
from netbox_rpki.services.provider_write import _serialize_krill_aspa_delta
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa_intent,
    create_test_imported_aspa,
    create_test_imported_aspa_provider,
    create_test_organization,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_provider_sync_run,
)


class AspaProviderWriteServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='aspa-write-org', name='ASPA Write Org')
        cls.provider_account = create_test_provider_account(
            name='ASPA Krill Write Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-ASPA-WRITE',
            ca_handle='ca-aspa-write',
            api_base_url='https://krill.example.invalid',
            api_key='krill-aspa-token',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='ASPA Krill Write Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

    def test_build_aspa_change_plan_delta_serializes_create_payloads(self):
        customer = create_test_asn(64700)
        provider = create_test_asn(64701)
        create_test_aspa_intent(
            name='ASPA Create Intent',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider,
        )

        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        plan = create_aspa_change_plan(run, name='ASPA Create Plan')

        delta = build_aspa_change_plan_delta(plan)

        self.assertEqual(
            delta,
            {
                'added': [
                    {
                        'customer_asn': 64700,
                        'customer': 'AS64700',
                        'providers': ['AS64701'],
                        'provider_asns': [64701],
                    },
                ],
                'removed': [],
            },
        )

    def test_build_aspa_change_plan_delta_serializes_withdraw_payloads(self):
        customer = create_test_asn(64710)
        provider = create_test_asn(64711)
        imported_aspa = create_test_imported_aspa(
            name='ASPA Withdraw Import',
            provider_snapshot=self.provider_snapshot,
            organization=self.organization,
            customer_as=customer,
        )
        create_test_imported_aspa_provider(imported_aspa=imported_aspa, provider_as=provider)

        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        plan = create_aspa_change_plan(run, name='ASPA Withdraw Plan')

        delta = build_aspa_change_plan_delta(plan)

        self.assertEqual(
            delta,
            {
                'added': [],
                'removed': [
                    {
                        'customer_asn': 64710,
                        'customer': 'AS64710',
                        'providers': ['AS64711'],
                        'provider_asns': [64711],
                    },
                ],
            },
        )

    def test_build_aspa_change_plan_delta_uses_anchor_and_remove_items_for_reshape(self):
        customer = create_test_asn(64720)
        provider_a = create_test_asn(64721)
        provider_b = create_test_asn(64722)
        create_test_aspa_intent(
            name='ASPA Reshape Intent A',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider_a,
        )
        imported_aspa = create_test_imported_aspa(
            name='ASPA Reshape Import',
            provider_snapshot=self.provider_snapshot,
            organization=self.organization,
            customer_as=customer,
        )
        create_test_imported_aspa_provider(imported_aspa=imported_aspa, provider_as=provider_a)
        create_test_imported_aspa_provider(imported_aspa=imported_aspa, provider_as=provider_b)

        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        plan = create_aspa_change_plan(run, name='ASPA Reshape Plan')

        delta = build_aspa_change_plan_delta(plan)

        self.assertEqual(
            delta,
            {
                'added': [
                    {
                        'customer_asn': 64720,
                        'customer': 'AS64720',
                        'providers': ['AS64721'],
                        'provider_asns': [64721],
                    },
                ],
                'removed': [
                    {
                        'customer_asn': 64720,
                        'customer': 'AS64720',
                        'providers': ['AS64722'],
                        'provider_asns': [64722],
                    },
                ],
            },
        )

    def test_serialize_krill_aspa_delta_uses_asn_strings_and_wire_keys(self):
        self.assertEqual(
            _serialize_krill_aspa_delta(
                {
                    'added': [
                        {'customer_asn': 64725, 'provider_asns': [64726, 64727]},
                    ],
                    'removed': [
                        {'customer_asn': 64728, 'provider_asns': [64729]},
                    ],
                }
            ),
            {
                'add': [
                    {'customer': 'AS64725', 'providers': ['AS64726', 'AS64727']},
                ],
                'remove': [
                    {'customer': 'AS64728', 'providers': ['AS64729']},
                ],
            },
        )

    def test_preview_records_non_mutating_execution(self):
        customer = create_test_asn(64730)
        provider = create_test_asn(64731)
        create_test_aspa_intent(
            name='ASPA Preview Intent',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider,
        )
        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        plan = create_aspa_change_plan(run, name='ASPA Preview Plan')

        execution, delta = preview_aspa_change_plan_provider_write(plan, requested_by='preview-user')

        self.assertEqual(execution.execution_mode, rpki_models.ProviderWriteExecutionMode.PREVIEW)
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(execution.request_payload_json, delta)
        self.assertEqual(
            execution.response_payload_json['provider_request'],
            {'add': [{'customer': 'AS64730', 'providers': ['AS64731']}], 'remove': []},
        )
        self.assertEqual(execution.response_payload_json['preview_report']['dangerous_change_count'], 0)
        self.assertEqual(execution.aspa_change_plan, plan)
        self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.DRAFT)

    def test_approve_transitions_plan_to_approved_and_records_approval(self):
        customer = create_test_asn(64740)
        provider = create_test_asn(64741)
        create_test_aspa_intent(
            name='ASPA Approve Intent',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider,
        )
        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        plan = create_aspa_change_plan(run, name='ASPA Approve Plan')

        approve_aspa_change_plan(
            plan,
            approved_by='approve-user',
            ticket_reference='ASPA-CHG-1',
            change_reference='ASPA-CAB-1',
            approval_notes='ASPA approval note',
        )
        plan.refresh_from_db()

        self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.APPROVED)
        self.assertEqual(plan.approved_by, 'approve-user')
        approval_record = plan.approval_records.get()
        self.assertEqual(approval_record.aspa_change_plan, plan)
        self.assertEqual(approval_record.ticket_reference, 'ASPA-CHG-1')
        self.assertEqual(approval_record.notes, 'ASPA approval note')

    def test_apply_submits_delta_records_execution_and_triggers_followup_sync(self):
        customer = create_test_asn(64750)
        provider = create_test_asn(64751)
        create_test_aspa_intent(
            name='ASPA Apply Intent',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider,
        )
        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        plan = create_aspa_change_plan(run, name='ASPA Apply Plan')
        approve_aspa_change_plan(plan, approved_by='apply-approver')
        followup_snapshot = create_test_provider_snapshot(
            name='ASPA Follow-Up Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_sync_run = create_test_provider_sync_run(
            name='ASPA Follow-Up Sync Run',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=followup_snapshot,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_aspa_delta',
            return_value={'message': 'accepted'},
        ) as submit_mock:
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                return_value=(followup_sync_run, followup_snapshot),
            ) as sync_mock:
                execution, delta = apply_aspa_change_plan_provider_write(plan, requested_by='apply-user')

        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.APPLIED)
        self.assertEqual(plan.apply_requested_by, 'apply-user')
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(execution.aspa_change_plan, plan)
        self.assertEqual(execution.request_payload_json, delta)
        self.assertEqual(execution.response_payload_json['provider_response'], {'message': 'accepted'})
        self.assertEqual(execution.followup_sync_run, followup_sync_run)
        self.assertEqual(execution.followup_provider_snapshot, followup_snapshot)
        rollback_bundle = plan.rollback_bundle
        self.assertEqual(rollback_bundle.status, rpki_models.RollbackBundleStatus.AVAILABLE)
        self.assertEqual(
            rollback_bundle.rollback_delta_json,
            {
                'added': delta['removed'],
                'removed': delta['added'],
            },
        )
        self.assertEqual(rollback_bundle.item_count, len(delta['added']) + len(delta['removed']))
        submit_mock.assert_called_once_with(self.provider_account, delta)
        sync_mock.assert_called_once()

    def test_apply_failure_marks_plan_failed_and_records_error(self):
        customer = create_test_asn(64760)
        provider = create_test_asn(64761)
        create_test_aspa_intent(
            name='ASPA Failed Intent',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider,
        )
        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        plan = create_aspa_change_plan(run, name='ASPA Failed Apply Plan')
        approve_aspa_change_plan(plan, approved_by='failure-approver')

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_aspa_delta',
            side_effect=RuntimeError('krill rejected aspa delta'),
        ):
            with self.assertRaisesMessage(ProviderWriteError, 'krill rejected aspa delta'):
                apply_aspa_change_plan_provider_write(plan, requested_by='failed-user')

        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.FAILED)
        execution = plan.provider_write_executions.get(execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY)
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.FAILED)
        self.assertEqual(execution.error, 'krill rejected aspa delta')
        self.assertFalse(rpki_models.ASPAChangePlanRollbackBundle.objects.filter(source_plan=plan).exists())

    def test_apply_records_partial_failure_on_followup_sync_failure(self):
        customer = create_test_asn(64770)
        provider = create_test_asn(64771)
        create_test_aspa_intent(
            name='ASPA Partial Failure Intent',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider,
        )
        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        plan = create_aspa_change_plan(run, name='ASPA Partial Failure Plan')
        approve_aspa_change_plan(plan, approved_by='partial-approver')

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_aspa_delta',
            return_value={'message': 'accepted'},
        ):
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                side_effect=RuntimeError('follow-up sync failed'),
            ):
                execution, _ = apply_aspa_change_plan_provider_write(plan, requested_by='partial-user')

        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.APPLIED)
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.FAILED)
        self.assertEqual(execution.error, 'follow-up sync failed')
        self.assertEqual(execution.response_payload_json['followup_sync']['status'], rpki_models.ValidationRunStatus.FAILED)

    def test_apply_rejects_already_applied_plan(self):
        customer = create_test_asn(64780)
        provider = create_test_asn(64781)
        create_test_aspa_intent(
            name='ASPA Repeat Apply Intent',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider,
        )
        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        plan = create_aspa_change_plan(run, name='ASPA Repeat Apply Plan')
        plan.status = rpki_models.ASPAChangePlanStatus.APPLIED
        plan.applied_at = timezone.now()
        plan.save(update_fields=('status', 'applied_at'))

        with self.assertRaisesMessage(ProviderWriteError, 'already been applied'):
            apply_aspa_change_plan_provider_write(plan, requested_by='repeat-user')

    def test_capability_gating_rejects_unsupported_provider(self):
        unsupported_account = create_test_provider_account(
            name='ARIN Unsupported ASPA Write Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            org_handle='ORG-ARIN-ASPA-WRITE',
        )
        unsupported_snapshot = create_test_provider_snapshot(
            name='ARIN Unsupported ASPA Snapshot',
            organization=self.organization,
            provider_account=unsupported_account,
            provider_name='ARIN',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        run = rpki_models.ASPAReconciliationRun.objects.create(
            name='Unsupported ASPA Run',
            organization=self.organization,
            provider_snapshot=unsupported_snapshot,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        plan = create_aspa_change_plan(run, name='Unsupported ASPA Provider Plan')
        plan.provider_account = unsupported_account
        plan.provider_snapshot = unsupported_snapshot
        plan.save(update_fields=('provider_account', 'provider_snapshot'))

        with self.assertRaisesMessage(ProviderWriteError, 'does not support ASPA write operations'):
            build_aspa_change_plan_delta(plan)
