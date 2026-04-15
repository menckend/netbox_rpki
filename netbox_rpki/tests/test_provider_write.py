from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.api.serializers import ASPAChangePlanApproveActionSerializer
from netbox_rpki.forms import ASPAChangePlanApprovalForm
from netbox_rpki.services import (
    ProviderWriteError,
    acknowledge_roa_lint_findings,
    apply_aspa_change_plan_provider_write,
    apply_roa_change_plan_provider_write,
    approve_aspa_change_plan,
    approve_roa_change_plan,
    build_aspa_change_plan_delta,
    build_roa_change_plan_delta,
    create_aspa_change_plan,
    create_roa_change_plan,
    derive_roa_intents,
    preview_aspa_change_plan_provider_write,
    preview_roa_change_plan_provider_write,
    reconcile_aspa_intents,
    reconcile_roa_intents,
    simulate_roa_change_plan,
)
from netbox_rpki.services.provider_write import _serialize_krill_aspa_delta
from netbox_rpki.services.roa_lint import build_roa_change_plan_lint_posture, run_roa_lint
from netbox_rpki.tests.base import PluginAPITestCase, PluginViewTestCase
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa_change_plan,
    create_test_aspa_intent,
    create_test_aspa_reconciliation_run,
    create_test_imported_aspa,
    create_test_imported_aspa_provider,
    create_test_imported_roa_authorization,
    create_test_organization,
    create_test_prefix,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_provider_sync_run,
    create_test_provider_write_execution,
    create_test_roa_change_plan,
    create_test_roa_change_plan_item,
    create_test_roa_change_plan_matrix,
    create_test_roa_lint_run,
    create_test_routing_intent_profile,
)


def current_ack_required_finding_ids(plan):
    lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
    if lint_run is None:
        return []
    return [
        finding.pk
        for finding in lint_run.findings.all()
        if finding.details_json.get('approval_impact') == 'acknowledgement_required'
        and not finding.details_json.get('suppressed')
    ]


def current_previously_acknowledged_finding_ids(plan):
    return build_roa_change_plan_lint_posture(plan).get('previously_acknowledged_finding_ids', [])


def current_ack_required_simulation_result_ids(plan):
    simulation_run = plan.simulation_runs.order_by('-started_at', '-created').first()
    if simulation_run is None:
        return []
    return [
        result.pk
        for result in simulation_run.results.all()
        if result.approval_impact == 'acknowledgement_required'
    ]


def build_clean_simulation_plan(
    *,
    organization,
    reconciliation_run,
    provider_account,
    provider_snapshot,
    prefix_text,
    origin_asn_value,
    max_length_value,
    plan_name,
):
    plan = create_test_roa_change_plan(
        name=plan_name,
        organization=organization,
        source_reconciliation_run=reconciliation_run,
        provider_account=provider_account,
        provider_snapshot=provider_snapshot,
    )
    create_test_roa_change_plan_item(
        name=f'{plan_name} Item',
        change_plan=plan,
        action_type=rpki_models.ROAChangePlanAction.CREATE,
        plan_semantic=rpki_models.ROAChangePlanItemSemantic.CREATE,
        provider_operation=rpki_models.ProviderWriteOperation.ADD_ROUTE,
        after_state_json={
            'prefix_cidr_text': prefix_text,
            'origin_asn_value': origin_asn_value,
            'max_length_value': max_length_value,
        },
    )
    create_test_roa_lint_run(
        name=f'{plan_name} Clean Lint',
        reconciliation_run=reconciliation_run,
        change_plan=plan,
    )
    simulate_roa_change_plan(plan)
    return plan


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

    def test_build_krill_delta_translates_replacement_items(self):
        replacement_snapshot = create_test_provider_snapshot(
            name='Replacement Delta Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        replacement_import = create_test_imported_roa_authorization(
            name='Replacement Delta Imported Authorization',
            provider_snapshot=replacement_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65177),
            max_length=26,
            payload_json={'comment': 'replace this route'},
        )
        replacement_reconciliation = reconcile_roa_intents(
            self.derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=replacement_snapshot,
        )
        replacement_plan = create_roa_change_plan(replacement_reconciliation, name='Replacement Delta Plan')

        delta = build_roa_change_plan_delta(replacement_plan)

        self.assertEqual(replacement_plan.summary_json['replacement_count'], 1)
        self.assertEqual(
            delta,
            {
                'added': [
                    {'asn': self.primary_asn.asn, 'prefix': '10.77.0.0/24', 'max_length': 24},
                ],
                'removed': [
                    {
                        'asn': replacement_import.origin_asn_value,
                        'prefix': '10.77.0.0/24',
                        'max_length': 26,
                        'comment': 'replace this route',
                    },
                ],
            },
        )

    def test_build_krill_delta_translates_mixed_create_withdraw_and_replacement_items(self):
        scenario = create_test_roa_change_plan_matrix(
            organization=self.organization,
            provider_account=self.provider_account,
        )

        delta = build_roa_change_plan_delta(scenario.provider_plan)

        self.assertEqual(scenario.provider_plan.summary_json['create_count'], 2)
        self.assertEqual(scenario.provider_plan.summary_json['withdraw_count'], 2)
        self.assertEqual(scenario.provider_plan.summary_json['replacement_count'], 1)
        self.assertTrue(scenario.provider_plan.summary_json['provider_backed'])
        self.assertEqual(
            delta,
            {
                'added': [
                    {'asn': 66110, 'prefix': '10.210.1.0/24', 'max_length': 24},
                    {'asn': 66110, 'prefix': '10.210.2.0/24', 'max_length': 24},
                ],
                'removed': [
                    {
                        'asn': 66111,
                        'prefix': '10.210.1.0/24',
                        'max_length': 26,
                        'comment': 'replacement target',
                    },
                    {
                        'asn': 66112,
                        'prefix': '10.210.99.0/24',
                        'max_length': 24,
                        'comment': 'orphaned target',
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

        approve_roa_change_plan(
            plan,
            approved_by='approval-user',
            acknowledged_finding_ids=current_ack_required_finding_ids(plan),
        )
        plan.refresh_from_db()

        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.APPROVED)
        self.assertIsNotNone(plan.approved_at)
        self.assertEqual(plan.approved_by, 'approval-user')

    def test_approve_records_governance_metadata_and_approval_record(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Governed Approval Plan')
        window_start = timezone.now()
        window_end = window_start + timedelta(hours=2)

        approve_roa_change_plan(
            plan,
            approved_by='approval-user',
            ticket_reference='CHG-1234',
            change_reference='CAB-77',
            maintenance_window_start=window_start,
            maintenance_window_end=window_end,
            approval_notes='Scheduled change approval.',
            acknowledged_finding_ids=current_ack_required_finding_ids(plan),
        )
        plan.refresh_from_db()
        approval_record = plan.approval_records.get()

        self.assertEqual(plan.ticket_reference, 'CHG-1234')
        self.assertEqual(plan.change_reference, 'CAB-77')
        self.assertEqual(plan.maintenance_window_start, window_start)
        self.assertEqual(plan.maintenance_window_end, window_end)
        self.assertEqual(approval_record.disposition, rpki_models.ValidationDisposition.ACCEPTED)
        self.assertEqual(approval_record.recorded_by, 'approval-user')
        self.assertEqual(approval_record.ticket_reference, 'CHG-1234')
        self.assertEqual(approval_record.change_reference, 'CAB-77')
        self.assertEqual(approval_record.notes, 'Scheduled change approval.')

    def test_approve_records_lint_acknowledgements_for_selected_ack_required_findings(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Acknowledged Approval Plan')
        ack_required_finding = plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')

        approve_roa_change_plan(
            plan,
            approved_by='approval-user',
            acknowledged_finding_ids=[ack_required_finding.pk],
            lint_acknowledgement_notes='Accepted for this change plan.',
        )
        acknowledgement = plan.lint_acknowledgements.get()

        self.assertEqual(acknowledgement.finding, ack_required_finding)
        self.assertEqual(acknowledgement.lint_run, plan.lint_runs.get())
        self.assertEqual(acknowledgement.acknowledged_by, 'approval-user')
        self.assertEqual(acknowledgement.notes, 'Accepted for this change plan.')

    def test_approve_denies_unresolved_blocking_findings(self):
        provider_snapshot = create_test_provider_snapshot(
            name='Blocking Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_imported_roa_authorization(
            name='Blocking Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65078),
            max_length=26,
        )
        reconciliation_run = reconcile_roa_intents(
            self.derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        plan = create_roa_change_plan(reconciliation_run, name='Blocked Approval Plan')

        with self.assertRaisesMessage(ProviderWriteError, 'unresolved blocking lint finding'):
            approve_roa_change_plan(plan, approved_by='approval-user')

    def test_approve_denies_acknowledgement_required_simulation_results_until_acknowledged(self):
        plan = build_clean_simulation_plan(
            organization=self.organization,
            reconciliation_run=self.reconciliation_run,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
            prefix_text=str(self.primary_prefix.prefix),
            origin_asn_value=self.primary_asn.asn,
            max_length_value=26,
            plan_name='Simulation Ack Approval Plan',
        )

        self.assertGreater(len(current_ack_required_simulation_result_ids(plan)), 0)
        with self.assertRaisesMessage(ProviderWriteError, 'acknowledgement-required simulation results'):
            approve_roa_change_plan(
                plan,
                approved_by='approval-user',
                acknowledged_finding_ids=current_ack_required_finding_ids(plan),
            )

    def test_approve_accepts_acknowledged_simulation_results(self):
        plan = build_clean_simulation_plan(
            organization=self.organization,
            reconciliation_run=self.reconciliation_run,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
            prefix_text=str(self.primary_prefix.prefix),
            origin_asn_value=self.primary_asn.asn,
            max_length_value=26,
            plan_name='Simulation Ack Accepted Plan',
        )

        approve_roa_change_plan(
            plan,
            approved_by='approval-user',
            acknowledged_finding_ids=current_ack_required_finding_ids(plan),
            acknowledged_simulation_result_ids=current_ack_required_simulation_result_ids(plan),
        )
        plan.refresh_from_db()
        approval_record = plan.approval_records.get()

        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.APPROVED)
        self.assertEqual(
            plan.summary_json['approved_simulation_result_ids'],
            current_ack_required_simulation_result_ids(plan),
        )
        self.assertEqual(
            approval_record.simulation_review_json['acknowledged_result_ids'],
            current_ack_required_simulation_result_ids(plan),
        )
        self.assertEqual(
            approval_record.simulation_review_json['overall_approval_posture'],
            rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED,
        )
        self.assertEqual(
            approval_record.simulation_review_json['acknowledged_result_count'],
            len(current_ack_required_simulation_result_ids(plan)),
        )
        self.assertEqual(
            approval_record.simulation_review_json,
            plan.summary_json['approved_simulation_review'],
        )

    def test_approve_denies_stale_simulation_fingerprint(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Stale Simulation Approval Plan')
        create_item = plan.items.filter(action_type=rpki_models.ROAChangePlanAction.CREATE).first()
        create_item.after_state_json['max_length_value'] = 25
        create_item.save(update_fields=('after_state_json',))

        with self.assertRaisesMessage(ProviderWriteError, 'simulation run is refreshed for the current plan state'):
            approve_roa_change_plan(
                plan,
                approved_by='approval-user',
                acknowledged_finding_ids=current_ack_required_finding_ids(plan),
            )

    def test_acknowledge_records_lint_acknowledgements_without_approving_plan(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Standalone Ack Plan')
        ack_required_finding = plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')

        acknowledgements = acknowledge_roa_lint_findings(
            plan,
            acknowledged_by='review-user',
            ticket_reference='ACK-123',
            change_reference='ACK-CHANGE',
            acknowledged_finding_ids=[ack_required_finding.pk],
            notes='Reviewed before approval.',
        )
        plan.refresh_from_db()

        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.DRAFT)
        self.assertEqual(len(acknowledgements), 1)
        self.assertEqual(plan.lint_acknowledgements.count(), 1)
        acknowledgement = plan.lint_acknowledgements.get()
        self.assertEqual(acknowledgement.finding, ack_required_finding)
        self.assertEqual(acknowledgement.ticket_reference, 'ACK-123')
        self.assertEqual(acknowledgement.change_reference, 'ACK-CHANGE')
        self.assertEqual(acknowledgement.notes, 'Reviewed before approval.')

    def test_prior_ack_same_fingerprint_shows_previously_acknowledged(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Previously Ack Plan')
        original_finding = plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')

        acknowledge_roa_lint_findings(
            plan,
            acknowledged_by='review-user',
            acknowledged_finding_ids=[original_finding.pk],
        )
        run_roa_lint(self.reconciliation_run, change_plan=plan)

        posture = build_roa_change_plan_lint_posture(plan)

        self.assertEqual(posture['previously_acknowledged_finding_count'], 1)
        self.assertEqual(len(posture['previously_acknowledged_finding_ids']), 1)
        self.assertEqual(posture['status'], 'previously_acknowledged')

    def test_approve_blocked_on_previously_acknowledged(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Previously Ack Blocked Plan')
        original_finding = plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')

        acknowledge_roa_lint_findings(
            plan,
            acknowledged_by='review-user',
            acknowledged_finding_ids=[original_finding.pk],
        )
        run_roa_lint(self.reconciliation_run, change_plan=plan)

        with self.assertRaisesMessage(ProviderWriteError, 'previously acknowledged lint findings'):
            approve_roa_change_plan(plan, approved_by='approval-user')

    def test_approve_passes_after_reconfirmation(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Previously Ack Approved Plan')
        original_finding = plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')

        acknowledge_roa_lint_findings(
            plan,
            acknowledged_by='review-user',
            acknowledged_finding_ids=[original_finding.pk],
        )
        run_roa_lint(self.reconciliation_run, change_plan=plan)

        approve_roa_change_plan(
            plan,
            approved_by='approval-user',
            previously_acknowledged_finding_ids=current_previously_acknowledged_finding_ids(plan),
        )
        plan.refresh_from_db()

        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.APPROVED)

    def test_apply_submits_delta_records_execution_and_triggers_followup_sync(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Apply Plan')
        window_start = timezone.now()
        window_end = window_start + timedelta(hours=1)
        approve_roa_change_plan(
            plan,
            approved_by='apply-approver',
            ticket_reference='CHG-APPLY',
            change_reference='CR-APPLY',
            maintenance_window_start=window_start,
            maintenance_window_end=window_end,
            acknowledged_finding_ids=current_ack_required_finding_ids(plan),
        )
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
        self.assertEqual(
            execution.response_payload_json['governance'],
            {
                'ticket_reference': 'CHG-APPLY',
                'change_reference': 'CR-APPLY',
                'maintenance_window_start': window_start.isoformat(),
                'maintenance_window_end': window_end.isoformat(),
            },
        )
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
        sync_mock.assert_called_once_with(
            self.provider_account,
            snapshot_name=sync_mock.call_args.kwargs['snapshot_name'],
        )

    def test_apply_rejects_repeat_apply(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='Repeat Apply Plan')
        approve_roa_change_plan(
            plan,
            approved_by='repeat-approver',
            acknowledged_finding_ids=current_ack_required_finding_ids(plan),
        )

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
        approve_roa_change_plan(
            plan,
            approved_by='failure-approver',
            acknowledged_finding_ids=current_ack_required_finding_ids(plan),
        )

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
        self.assertFalse(rpki_models.ROAChangePlanRollbackBundle.objects.filter(source_plan=plan).exists())

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


class ASPAProviderWriteServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='aspa-write-org', name='ASPA Write Org')
        cls.customer_as = create_test_asn(65200)
        cls.provider_as_a = create_test_asn(65201)
        cls.provider_as_b = create_test_asn(65202)
        cls.orphaned_customer_as = create_test_asn(65299)
        cls.orphaned_provider_as = create_test_asn(65300)

        cls.provider_account = create_test_provider_account(
            name='ASPA Krill Write Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-ASPA-WRITE',
            ca_handle='ca-aspa-write',
            api_base_url='https://krill.example.invalid',
            api_key='aspa-krill-token',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='ASPA Krill Write Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

        cls.intent_a = create_test_aspa_intent(
            name='ASPA Write Intent A',
            organization=cls.organization,
            customer_as=cls.customer_as,
            provider_as=cls.provider_as_a,
        )
        cls.intent_b = create_test_aspa_intent(
            name='ASPA Write Intent B',
            organization=cls.organization,
            customer_as=cls.customer_as,
            provider_as=cls.provider_as_b,
        )

        cls.orphaned_imported_aspa = create_test_imported_aspa(
            name='Orphaned Imported ASPA',
            provider_snapshot=cls.provider_snapshot,
            organization=cls.organization,
            customer_as=cls.orphaned_customer_as,
            customer_as_value=cls.orphaned_customer_as.asn,
        )
        create_test_imported_aspa_provider(
            imported_aspa=cls.orphaned_imported_aspa,
            provider_as=cls.orphaned_provider_as,
            provider_as_value=cls.orphaned_provider_as.asn,
        )

        cls.reconciliation_run = reconcile_aspa_intents(
            cls.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.plan = create_aspa_change_plan(cls.reconciliation_run)

    def test_build_aspa_delta_separates_create_and_withdraw_by_semantic(self):
        delta = build_aspa_change_plan_delta(self.plan)

        self.assertIn('added', delta)
        self.assertIn('removed', delta)

        added_customers = {entry['customer_asn'] for entry in delta['added']}
        removed_customers = {entry['customer_asn'] for entry in delta['removed']}

        self.assertIn(self.customer_as.asn, added_customers)
        self.assertIn(self.orphaned_customer_as.asn, removed_customers)

    def test_build_aspa_delta_replace_lands_in_added_only(self):
        replace_customer = create_test_asn(65210)
        replace_provider = create_test_asn(65211)
        create_test_aspa_intent(
            name='Imported Stale Intent',
            organization=self.organization,
            customer_as=replace_customer,
            provider_as=replace_provider,
        )
        replace_imported_aspa = create_test_imported_aspa(
            name='Imported Stale ASPA',
            provider_snapshot=self.provider_snapshot,
            organization=self.organization,
            customer_as=replace_customer,
            customer_as_value=replace_customer.asn,
            is_stale=True,
        )
        create_test_imported_aspa_provider(
            imported_aspa=replace_imported_aspa,
            provider_as=replace_provider,
            provider_as_value=replace_provider.asn,
        )

        replace_reconciliation = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        replace_plan = create_aspa_change_plan(replace_reconciliation, name='ASPA Replace Plan')
        delta = build_aspa_change_plan_delta(replace_plan)

        replace_item = replace_plan.items.get(plan_semantic=rpki_models.ASPAChangePlanItemSemantic.REPLACE)
        self.assertEqual(replace_item.provider_operation, rpki_models.ProviderWriteOperation.ADD_PROVIDER_SET)
        added_customers = {entry['customer_asn'] for entry in delta.get('added', [])}
        removed_customers = {entry['customer_asn'] for entry in delta.get('removed', [])}
        self.assertIn(replace_customer.asn, added_customers)
        self.assertNotIn(replace_customer.asn, removed_customers)

    def test_serialize_krill_aspa_delta_converts_asn_integers_to_as_prefixed_strings(self):
        internal = {
            'added': [{'customer_asn': 65001, 'provider_asns': [65002, 65003]}],
            'removed': [{'customer_asn': 65004, 'provider_asns': [65005]}],
        }

        wire = _serialize_krill_aspa_delta(internal)

        self.assertEqual(
            wire,
            {
                'add': [{'customer': 'AS65001', 'providers': ['AS65002', 'AS65003']}],
                'remove': [{'customer': 'AS65004', 'providers': ['AS65005']}],
            },
        )

    def test_preview_records_execution_without_applying(self):
        execution, delta = preview_aspa_change_plan_provider_write(self.plan, requested_by='preview-user')

        self.assertEqual(execution.execution_mode, rpki_models.ProviderWriteExecutionMode.PREVIEW)
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(execution.requested_by, 'preview-user')
        self.assertEqual(execution.request_payload_json, delta)
        self.assertEqual(
            execution.response_payload_json['delegated_scope'],
            {
                'delegated_scoped_item_count': 0,
                'ownership_scope_conflict_customer_count': 0,
                'ownership_scope_conflict_customer_asns': [],
            },
        )
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, rpki_models.ASPAChangePlanStatus.DRAFT)

    def test_approve_transitions_plan_to_approved(self):
        plan = create_aspa_change_plan(self.reconciliation_run, name='ASPA Approval Plan')

        approve_aspa_change_plan(plan, approved_by='aspa-approver')
        plan.refresh_from_db()

        self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.APPROVED)
        self.assertIsNotNone(plan.approved_at)
        self.assertEqual(plan.approved_by, 'aspa-approver')

    def test_approve_records_governance_metadata_and_approval_record(self):
        plan = create_aspa_change_plan(self.reconciliation_run, name='Governed ASPA Approval Plan')
        window_start = timezone.now()
        window_end = window_start + timedelta(hours=2)

        approve_aspa_change_plan(
            plan,
            approved_by='aspa-approver',
            ticket_reference='ASPA-CHG-1',
            change_reference='ASPA-CAB-1',
            maintenance_window_start=window_start,
            maintenance_window_end=window_end,
            approval_notes='ASPA window note.',
        )
        plan.refresh_from_db()
        approval_record = plan.approval_records.get()

        self.assertEqual(plan.ticket_reference, 'ASPA-CHG-1')
        self.assertEqual(plan.change_reference, 'ASPA-CAB-1')
        self.assertEqual(plan.maintenance_window_start, window_start)
        self.assertEqual(plan.maintenance_window_end, window_end)
        self.assertEqual(approval_record.disposition, rpki_models.ValidationDisposition.ACCEPTED)
        self.assertEqual(approval_record.recorded_by, 'aspa-approver')
        self.assertEqual(approval_record.ticket_reference, 'ASPA-CHG-1')
        self.assertEqual(approval_record.notes, 'ASPA window note.')

    def test_approve_rejects_already_approved_plan(self):
        plan = create_aspa_change_plan(self.reconciliation_run, name='ASPA Repeat Approval Plan')
        approve_aspa_change_plan(plan, approved_by='first-approver')

        with self.assertRaisesMessage(ProviderWriteError, 'Only draft ASPA change plans can be approved'):
            approve_aspa_change_plan(plan, approved_by='second-approver')

    def test_approve_rejects_non_provider_backed_plan(self):
        local_reconciliation_run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
        )
        local_plan = create_aspa_change_plan(local_reconciliation_run, name='ASPA Local Plan')

        with self.assertRaisesMessage(ProviderWriteError, 'not provider-backed'):
            approve_aspa_change_plan(local_plan, approved_by='approver')

    def test_apply_submits_delta_records_execution_and_triggers_followup_sync(self):
        plan = create_aspa_change_plan(self.reconciliation_run, name='ASPA Apply Plan')
        window_start = timezone.now()
        window_end = window_start + timedelta(hours=1)
        approve_aspa_change_plan(
            plan,
            approved_by='apply-approver',
            ticket_reference='ASPA-APPLY-CHG',
            change_reference='ASPA-APPLY-CR',
            maintenance_window_start=window_start,
            maintenance_window_end=window_end,
        )
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
        self.assertIsNotNone(plan.apply_started_at)
        self.assertEqual(plan.apply_requested_by, 'apply-user')
        self.assertIsNotNone(plan.applied_at)
        self.assertIsNone(plan.failed_at)
        self.assertEqual(execution.execution_mode, rpki_models.ProviderWriteExecutionMode.APPLY)
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(execution.followup_sync_run, followup_sync_run)
        self.assertEqual(execution.followup_provider_snapshot, followup_snapshot)
        self.assertEqual(execution.request_payload_json, delta)
        self.assertEqual(execution.response_payload_json['provider_response'], {'message': 'accepted'})
        self.assertEqual(
            execution.response_payload_json['delta_summary'],
            {
                'customer_count': len(delta['added']) + len(delta['removed']),
                'create_count': len(delta['added']),
                'withdraw_count': len(delta['removed']),
                'provider_add_count': sum(len(entry.get('provider_asns') or []) for entry in delta['added']),
                'provider_remove_count': sum(len(entry.get('provider_asns') or []) for entry in delta['removed']),
            },
        )
        self.assertEqual(
            execution.response_payload_json['delegated_scope'],
            {
                'delegated_scoped_item_count': 0,
                'ownership_scope_conflict_customer_count': 0,
                'ownership_scope_conflict_customer_asns': [],
            },
        )
        submit_mock.assert_called_once_with(self.provider_account, delta)
        sync_mock.assert_called_once_with(
            self.provider_account,
            snapshot_name=sync_mock.call_args.kwargs['snapshot_name'],
        )
        rollback_bundle = plan.rollback_bundle
        self.assertEqual(rollback_bundle.status, rpki_models.RollbackBundleStatus.AVAILABLE)

    def test_apply_rejects_repeat_apply(self):
        plan = create_aspa_change_plan(self.reconciliation_run, name='ASPA Repeat Apply Plan')
        approve_aspa_change_plan(plan, approved_by='repeat-approver')

        with patch('netbox_rpki.services.provider_write._submit_krill_aspa_delta', return_value={}):
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                return_value=(
                    create_test_provider_sync_run(
                        name='ASPA Repeat Apply Sync Run',
                        organization=self.organization,
                        provider_account=self.provider_account,
                        provider_snapshot=create_test_provider_snapshot(
                            name='ASPA Repeat Apply Snapshot',
                            organization=self.organization,
                            provider_account=self.provider_account,
                            provider_name='Krill',
                            status=rpki_models.ValidationRunStatus.COMPLETED,
                        ),
                    ),
                    create_test_provider_snapshot(
                        name='ASPA Repeat Apply Snapshot 2',
                        organization=self.organization,
                        provider_account=self.provider_account,
                        provider_name='Krill',
                        status=rpki_models.ValidationRunStatus.COMPLETED,
                    ),
                ),
            ):
                apply_aspa_change_plan_provider_write(plan)

        with self.assertRaisesMessage(ProviderWriteError, 'already been applied'):
            apply_aspa_change_plan_provider_write(plan)

    def test_apply_failure_marks_plan_failed_and_records_error(self):
        plan = create_aspa_change_plan(self.reconciliation_run, name='Failed ASPA Apply Plan')
        approve_aspa_change_plan(plan, approved_by='failure-approver')

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_aspa_delta',
            side_effect=RuntimeError('krill rejected aspa delta'),
        ):
            with self.assertRaisesMessage(ProviderWriteError, 'krill rejected aspa delta'):
                apply_aspa_change_plan_provider_write(plan, requested_by='failed-apply-user')

        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.FAILED)
        self.assertIsNotNone(plan.apply_started_at)
        self.assertEqual(plan.apply_requested_by, 'failed-apply-user')
        self.assertIsNotNone(plan.failed_at)
        execution = plan.provider_write_executions.get(execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY)
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.FAILED)
        self.assertEqual(execution.error, 'krill rejected aspa delta')
        self.assertFalse(rpki_models.ASPAChangePlanRollbackBundle.objects.filter(source_plan=plan).exists())

    def test_apply_failure_during_followup_sync_records_partial_success(self):
        plan = create_aspa_change_plan(self.reconciliation_run, name='ASPA Followup Failure Plan')
        approve_aspa_change_plan(plan, approved_by='sync-failure-approver')

        with patch(
            'netbox_rpki.services.provider_write._submit_krill_aspa_delta',
            return_value={'message': 'accepted'},
        ):
            with patch(
                'netbox_rpki.services.provider_write.sync_provider_account',
                side_effect=RuntimeError('provider unreachable during followup'),
            ):
                execution, _ = apply_aspa_change_plan_provider_write(plan, requested_by='sync-failed-user')

        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.APPLIED)
        self.assertEqual(execution.status, rpki_models.ValidationRunStatus.FAILED)
        self.assertEqual(execution.error, 'provider unreachable during followup')
        self.assertEqual(
            execution.response_payload_json['followup_sync']['status'],
            rpki_models.ValidationRunStatus.FAILED,
        )

    def test_capability_gating_rejects_unsupported_provider_type(self):
        unsupported_account = create_test_provider_account(
            name='ARIN ASPA Unsupported Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            org_handle='ORG-ARIN-ASPA',
        )
        unsupported_snapshot = create_test_provider_snapshot(
            name='ARIN ASPA Unsupported Snapshot',
            organization=self.organization,
            provider_account=unsupported_account,
            provider_name='ARIN',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        unsupported_reconciliation = create_test_aspa_reconciliation_run(
            name='Unsupported ASPA Reconciliation',
            organization=self.organization,
            provider_snapshot=unsupported_snapshot,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
        )
        unsupported_plan = create_test_aspa_change_plan(
            name='Unsupported ASPA Plan',
            organization=self.organization,
            source_reconciliation_run=unsupported_reconciliation,
            provider_account=unsupported_account,
            provider_snapshot=unsupported_snapshot,
        )

        with self.assertRaisesMessage(ProviderWriteError, 'does not support ASPA write operations'):
            build_aspa_change_plan_delta(unsupported_plan)


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
        self.add_permissions(
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.change_roachangeplan',
            'netbox_rpki.view_approvalrecord',
        )
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-preview', kwargs={'pk': self.plan.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('delta', response.data)
        self.assertIn('execution', response.data)
        self.assertIn('latest_lint_posture', response.data)
        self.assertEqual(response.data['status'], rpki_models.ROAChangePlanStatus.DRAFT)
        self.assertIn('latest_simulation_summary', response.data)

    def test_approve_action_transitions_plan(self):
        self.add_permissions(
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.change_roachangeplan',
            'netbox_rpki.view_approvalrecord',
        )
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-approve', kwargs={'pk': self.plan.pk})

        response = self.client.post(
            url,
            {'acknowledged_finding_ids': current_ack_required_finding_ids(self.plan)},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, rpki_models.ROAChangePlanStatus.APPROVED)
        self.assertIsNotNone(self.plan.approved_at)
        self.assertEqual(self.plan.approved_by, self.user.username)

    def test_approve_action_records_governance_metadata(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-approve', kwargs={'pk': self.plan.pk})

        response = self.client.post(
            url,
            {
                'ticket_reference': 'API-CHG-100',
                'change_reference': 'API-CAB-10',
                'maintenance_window_start': '2026-04-12T22:00:00Z',
                'maintenance_window_end': '2026-04-12T23:00:00Z',
                'approval_notes': 'API approval note',
                'acknowledged_finding_ids': current_ack_required_finding_ids(self.plan),
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.ticket_reference, 'API-CHG-100')
        self.assertEqual(self.plan.change_reference, 'API-CAB-10')
        self.assertIn('approval_record', response.data)
        self.assertEqual(response.data['approval_record']['ticket_reference'], 'API-CHG-100')
        self.assertEqual(response.data['approval_record']['notes'], 'API approval note')

    def test_approve_action_records_lint_acknowledgements(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='API Ack Approval Plan')
        ack_required_finding = plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-approve', kwargs={'pk': plan.pk})

        response = self.client.post(
            url,
            {
                'acknowledged_finding_ids': [ack_required_finding.pk],
                'lint_acknowledgement_notes': 'Accepted via API.',
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(plan.lint_acknowledgements.count(), 1)
        self.assertEqual(plan.lint_acknowledgements.get().notes, 'Accepted via API.')

    def test_approve_action_accepts_previously_acknowledged_findings(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='API Previously Ack Approval Plan')
        original_finding = plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')
        acknowledge_roa_lint_findings(
            plan,
            acknowledged_by='api-review-user',
            acknowledged_finding_ids=[original_finding.pk],
        )
        run_roa_lint(self.reconciliation_run, change_plan=plan)
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-approve', kwargs={'pk': plan.pk})

        response = self.client.post(
            url,
            {
                'previously_acknowledged_finding_ids': current_previously_acknowledged_finding_ids(plan),
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.APPROVED)

    def test_approve_action_denies_unresolved_blocking_findings(self):
        mismatch_snapshot = create_test_provider_snapshot(
            name='API Blocking Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_imported_roa_authorization(
            name='API Blocking Imported Authorization',
            provider_snapshot=mismatch_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65179),
            max_length=26,
        )
        reconciliation_run = reconcile_roa_intents(
            self.derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=mismatch_snapshot,
        )
        plan = create_roa_change_plan(reconciliation_run, name='API Blocking Approval Plan')
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-approve', kwargs={'pk': plan.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 400)
        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.DRAFT)

    def test_approve_action_denies_ack_required_simulation_results_until_acknowledged(self):
        plan = build_clean_simulation_plan(
            organization=self.organization,
            reconciliation_run=self.reconciliation_run,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
            prefix_text=str(self.primary_prefix.prefix),
            origin_asn_value=self.primary_asn.asn,
            max_length_value=26,
            plan_name='API Simulation Ack Approval Plan',
        )
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-approve', kwargs={'pk': plan.pk})

        response = self.client.post(
            url,
            {'acknowledged_finding_ids': []},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.DRAFT)

    def test_approve_action_accepts_acknowledged_simulation_results(self):
        plan = build_clean_simulation_plan(
            organization=self.organization,
            reconciliation_run=self.reconciliation_run,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
            prefix_text=str(self.primary_prefix.prefix),
            origin_asn_value=self.primary_asn.asn,
            max_length_value=26,
            plan_name='API Simulation Ack Accepted Plan',
        )
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-approve', kwargs={'pk': plan.pk})

        response = self.client.post(
            url,
            {
                'acknowledged_simulation_result_ids': current_ack_required_simulation_result_ids(plan),
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.APPROVED)
        self.assertEqual(
            response.data['approval_record']['simulation_review_json'],
            plan.summary_json['approved_simulation_review'],
        )
        self.assertEqual(
            response.data['approval_record']['simulation_review_json']['acknowledged_result_ids'],
            current_ack_required_simulation_result_ids(plan),
        )

    def test_apply_action_runs_provider_write_flow(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        approve_roa_change_plan(
            self.plan,
            approved_by='api-approver',
            acknowledged_finding_ids=current_ack_required_finding_ids(self.plan),
        )
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

    def test_simulate_action_returns_simulation_run(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-simulate', kwargs={'pk': self.plan.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('simulation_run', response.data)
        self.assertIn('latest_simulation_summary', response.data)
        self.assertEqual(response.data['simulation_run']['result_count'], self.plan.items.count())

    def test_summary_action_returns_aggregate_counts(self):
        self.add_permissions('netbox_rpki.view_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-summary')

        response = self.client.get(url, **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('total_plans', response.data)
        self.assertIn('by_status', response.data)
        self.assertIn('simulated_plan_count', response.data)
        self.assertIn('lint_blocking_total', response.data)
        self.assertIn('lint_acknowledgement_required_total', response.data)
        self.assertIn('lint_acknowledged_total', response.data)

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
        for action in ('preview', 'acknowledge-findings', 'approve', 'apply', 'simulate'):
            url = reverse(f'plugins-api:netbox_rpki-api:roachangeplan-{action}', kwargs={'pk': self.plan.pk})
            response = self.client.post(url, {}, format='json', **self.header)
            with self.subTest(action=action):
                self.assertHttpStatus(response, 404)

    def test_acknowledge_findings_action_records_lint_acknowledgements(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='API Standalone Ack Plan')
        ack_required_finding = plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-acknowledge-findings', kwargs={'pk': plan.pk})

        response = self.client.post(
            url,
            {
                'ticket_reference': 'API-ACK-200',
                'change_reference': 'API-ACK-CR',
                'acknowledged_finding_ids': [ack_required_finding.pk],
                'lint_acknowledgement_notes': 'Accepted via review API.',
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(plan.lint_acknowledgements.count(), 1)
        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.DRAFT)
        self.assertEqual(response.data['acknowledgements'][0]['ticket_reference'], 'API-ACK-200')
        self.assertEqual(response.data['acknowledgements'][0]['notes'], 'Accepted via review API.')

    def test_acknowledge_findings_action_accepts_previously_acknowledged_findings(self):
        plan = create_roa_change_plan(self.reconciliation_run, name='API Previously Ack Plan')
        original_finding = plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')
        acknowledge_roa_lint_findings(
            plan,
            acknowledged_by='api-review-user',
            acknowledged_finding_ids=[original_finding.pk],
        )
        run_roa_lint(self.reconciliation_run, change_plan=plan)
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-acknowledge-findings', kwargs={'pk': plan.pk})

        response = self.client.post(
            url,
            {
                'previously_acknowledged_finding_ids': current_previously_acknowledged_finding_ids(plan),
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        latest_lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
        self.assertEqual(plan.lint_acknowledgements.filter(lint_run=latest_lint_run).count(), 1)

    def test_lint_suppress_and_lift_api_actions(self):
        finding = self.plan.lint_runs.get().findings.first()
        self.add_permissions(
            'netbox_rpki.view_roalintfinding',
            'netbox_rpki.change_roalintfinding',
            'netbox_rpki.view_roalintsuppression',
            'netbox_rpki.change_roalintsuppression',
        )
        suppress_url = reverse('plugins-api:netbox_rpki-api:roalintfinding-suppress', kwargs={'pk': finding.pk})

        suppress_response = self.client.post(
            suppress_url,
            {
                'scope_type': rpki_models.ROALintSuppressionScope.PROFILE,
                'reason': 'Suppress from API test.',
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(suppress_response, 200)
        suppression_id = suppress_response.data['id']
        lift_url = reverse('plugins-api:netbox_rpki-api:roalintsuppression-lift', kwargs={'pk': suppression_id})

        lift_response = self.client.post(
            lift_url,
            {'lift_reason': 'Lift from API test.'},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(lift_response, 200)
        self.assertIsNotNone(lift_response.data['lifted_at'])


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
        self.assertContains(response, reverse('plugins:netbox_rpki:roachangeplan_simulate', kwargs={'pk': self.plan.pk}))
        self.assertContains(response, reverse('plugins:netbox_rpki:roachangeplan_preview', kwargs={'pk': self.plan.pk}))
        self.assertContains(response, reverse('plugins:netbox_rpki:roachangeplan_acknowledge_lint', kwargs={'pk': self.plan.pk}))
        self.assertContains(response, reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': self.plan.pk}))
        self.assertNotContains(response, reverse('plugins:netbox_rpki:roachangeplan_apply', kwargs={'pk': self.plan.pk}))

    def test_change_plan_detail_shows_acknowledge_button_after_approval(self):
        self.plan.status = rpki_models.ROAChangePlanStatus.APPROVED
        self.plan.save(update_fields=('status',))
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')

        response = self.client.get(self.plan.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, reverse('plugins:netbox_rpki:roachangeplan_acknowledge_lint', kwargs={'pk': self.plan.pk}))

    def test_change_plan_detail_hides_simulate_button_without_change_permission(self):
        self.add_permissions('netbox_rpki.view_roachangeplan')

        response = self.client.get(self.plan.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertNotContains(response, reverse('plugins:netbox_rpki:roachangeplan_simulate', kwargs={'pk': self.plan.pk}))

    def test_acknowledge_view_records_lint_acknowledgements_without_approval(self):
        ack_required_finding = self.plan.lint_runs.get().findings.filter(
            details_json__approval_impact='acknowledgement_required',
            details_json__suppressed=False,
        ).first()
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins:netbox_rpki:roachangeplan_acknowledge_lint', kwargs={'pk': self.plan.pk})

        get_response = self.client.get(url)
        self.assertHttpStatus(get_response, 200)
        self.assertContains(get_response, 'Acknowledge Approval-Required Lint Findings')

        post_response = self.client.post(
            url,
            {
                'confirm': True,
                'ticket_reference': 'UI-ACK-12',
                'change_reference': 'UI-ACK-CR',
                'acknowledged_findings': [ack_required_finding.pk],
                'lint_acknowledgement_notes': 'Reviewed in UI.',
            },
        )

        self.plan.refresh_from_db()
        self.assertRedirects(post_response, self.plan.get_absolute_url())
        self.assertEqual(self.plan.status, rpki_models.ROAChangePlanStatus.DRAFT)
        self.assertEqual(self.plan.lint_acknowledgements.count(), 1)
        self.assertEqual(self.plan.lint_acknowledgements.get().ticket_reference, 'UI-ACK-12')

    def test_acknowledge_view_shows_and_accepts_previously_acknowledged_findings(self):
        original_finding = self.plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')
        acknowledge_roa_lint_findings(
            self.plan,
            acknowledged_by='view-user',
            acknowledged_finding_ids=[original_finding.pk],
        )
        run_roa_lint(self.reconciliation_run, change_plan=self.plan)
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins:netbox_rpki:roachangeplan_acknowledge_lint', kwargs={'pk': self.plan.pk})

        get_response = self.client.get(url)

        self.assertHttpStatus(get_response, 200)
        self.assertContains(get_response, 'Re-Confirm Previously Acknowledged Lint Findings')

        post_response = self.client.post(
            url,
            {
                'confirm': True,
                'previously_acknowledged_findings': current_previously_acknowledged_finding_ids(self.plan),
            },
        )

        self.assertRedirects(post_response, self.plan.get_absolute_url())
        latest_lint_run = self.plan.lint_runs.order_by('-started_at', '-created').first()
        self.assertEqual(self.plan.lint_acknowledgements.filter(lint_run=latest_lint_run).count(), 1)

    def test_preview_view_renders_delta(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')

        response = self.client.get(reverse('plugins:netbox_rpki:roachangeplan_preview', kwargs={'pk': self.plan.pk}))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Preview Provider Delta')
        self.assertContains(response, '10.89.0.0/24')

    def test_simulate_view_creates_run_and_redirects(self):
        self.add_permissions(
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.change_roachangeplan',
            'netbox_rpki.view_roavalidationsimulationrun',
        )
        url = reverse('plugins:netbox_rpki:roachangeplan_simulate', kwargs={'pk': self.plan.pk})

        get_response = self.client.get(url)

        self.assertHttpStatus(get_response, 200)
        self.assertContains(get_response, 'Run ROA Validation Simulation')

        post_response = self.client.post(url, {'confirm': True})

        simulation_run = self.plan.simulation_runs.order_by('-started_at', '-created').first()
        self.assertIsNotNone(simulation_run)
        self.assertRedirects(post_response, simulation_run.get_absolute_url())

    def test_simulate_view_requires_change_permission(self):
        self.add_permissions('netbox_rpki.view_roachangeplan')

        response = self.client.get(reverse('plugins:netbox_rpki:roachangeplan_simulate', kwargs={'pk': self.plan.pk}))

        self.assertHttpStatus(response, 403)

    def test_approve_view_renders_and_persists_governance_fields(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': self.plan.pk})

        get_response = self.client.get(url)

        self.assertHttpStatus(get_response, 200)
        self.assertContains(get_response, 'Ticket Reference')
        self.assertContains(get_response, 'Change Reference')

        response = self.client.post(
            url,
            {
                'confirm': True,
                'ticket_reference': 'UI-CHG-88',
                'change_reference': 'UI-CAB-12',
                'maintenance_window_start': '2026-04-13T01:00',
                'maintenance_window_end': '2026-04-13T02:00',
                'approval_notes': 'Window approved in UI.',
                'acknowledged_findings': current_ack_required_finding_ids(self.plan),
            },
        )

        self.assertRedirects(response, self.plan.get_absolute_url())
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.ticket_reference, 'UI-CHG-88')
        self.assertEqual(self.plan.change_reference, 'UI-CAB-12')
        self.assertEqual(self.plan.approval_records.count(), 1)

    def test_approve_view_shows_and_accepts_previously_acknowledged_findings(self):
        original_finding = self.plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')
        acknowledge_roa_lint_findings(
            self.plan,
            acknowledged_by='view-user',
            acknowledged_finding_ids=[original_finding.pk],
        )
        run_roa_lint(self.reconciliation_run, change_plan=self.plan)
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': self.plan.pk})

        get_response = self.client.get(url)

        self.assertHttpStatus(get_response, 200)
        self.assertContains(get_response, 'Re-Confirm Previously Acknowledged Lint Findings')

        post_response = self.client.post(
            url,
            {
                'confirm': True,
                'previously_acknowledged_findings': current_previously_acknowledged_finding_ids(self.plan),
            },
        )

        self.plan.refresh_from_db()
        self.assertRedirects(post_response, self.plan.get_absolute_url())
        self.assertEqual(self.plan.status, rpki_models.ROAChangePlanStatus.APPROVED)

    def test_approve_view_shows_and_accepts_acknowledgement_required_simulation_results(self):
        plan = build_clean_simulation_plan(
            organization=self.organization,
            reconciliation_run=self.reconciliation_run,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
            prefix_text=str(self.primary_prefix.prefix),
            origin_asn_value=self.primary_asn.asn,
            max_length_value=26,
            plan_name='UI Simulation Ack Plan',
        )
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': plan.pk})

        get_response = self.client.get(url)

        self.assertHttpStatus(get_response, 200)
        self.assertContains(get_response, 'Acknowledge Approval-Required Simulation Results')

        post_response = self.client.post(
            url,
            {
                'confirm': True,
                'acknowledged_simulation_results': current_ack_required_simulation_result_ids(plan),
            },
        )

        plan.refresh_from_db()
        self.assertRedirects(post_response, plan.get_absolute_url())
        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.APPROVED)
        approval_record = plan.approval_records.get()
        self.assertEqual(
            approval_record.simulation_review_json['acknowledged_result_ids'],
            current_ack_required_simulation_result_ids(plan),
        )

    def test_lint_finding_suppress_and_lift_views(self):
        finding = self.plan.lint_runs.get().findings.first()
        self.add_permissions(
            'netbox_rpki.view_roalintfinding',
            'netbox_rpki.change_roalintfinding',
            'netbox_rpki.view_roalintsuppression',
            'netbox_rpki.change_roalintsuppression',
        )
        suppress_url = reverse('plugins:netbox_rpki:roalintfinding_suppress', kwargs={'pk': finding.pk})

        get_response = self.client.get(suppress_url)
        self.assertHttpStatus(get_response, 200)
        self.assertContains(get_response, 'Suppression Scope')

        post_response = self.client.post(
            suppress_url,
            {
                'confirm': True,
                'scope_type': rpki_models.ROALintSuppressionScope.PROFILE,
                'reason': 'Suppress from UI test.',
            },
        )

        suppression = rpki_models.ROALintSuppression.objects.get(reason='Suppress from UI test.')
        self.assertRedirects(post_response, suppression.get_absolute_url())

        lift_url = reverse('plugins:netbox_rpki:roalintsuppression_lift', kwargs={'pk': suppression.pk})
        lift_response = self.client.post(lift_url, {'confirm': True, 'lift_reason': 'Lift from UI test.'})
        suppression.refresh_from_db()

        self.assertRedirects(lift_response, suppression.get_absolute_url())
        self.assertIsNotNone(suppression.lifted_at)

    def test_apply_view_shows_governance_metadata_after_approval(self):
        approve_roa_change_plan(
            self.plan,
            approved_by='view-approver',
            ticket_reference='UI-APPLY-1',
            change_reference='UI-APPLY-CR',
            acknowledged_finding_ids=current_ack_required_finding_ids(self.plan),
        )
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')

        response = self.client.get(reverse('plugins:netbox_rpki:roachangeplan_apply', kwargs={'pk': self.plan.pk}))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Governance Metadata')
        self.assertContains(response, 'UI-APPLY-1')
        self.assertContains(response, 'UI-APPLY-CR')

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
        self.assertContains(response, reverse('plugins:netbox_rpki:roachangeplan_simulate', kwargs={'pk': unsupported_plan.pk}))
        self.assertNotContains(response, reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': unsupported_plan.pk}))
        self.assertNotContains(response, reverse('plugins:netbox_rpki:roachangeplan_apply', kwargs={'pk': unsupported_plan.pk}))


class ASPAChangePlanActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-write-aspa-api-org', name='Provider Write ASPA API Org')
        cls.provider_account = create_test_provider_account(
            name='Provider Write ASPA API Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-API-ASPA-WRITE',
            ca_handle='ca-api-aspa-write',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Provider Write ASPA API Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.customer_as = create_test_asn(65880)
        cls.provider_as = create_test_asn(65881)
        create_test_aspa_intent(
            name='Provider Write ASPA API Intent',
            organization=cls.organization,
            customer_as=cls.customer_as,
            provider_as=cls.provider_as,
        )
        cls.reconciliation_run = reconcile_aspa_intents(
            cls.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.plan = create_aspa_change_plan(cls.reconciliation_run)

    def test_create_plan_action_returns_plan(self):
        self.add_permissions('netbox_rpki.view_aspareconciliationrun', 'netbox_rpki.change_aspareconciliationrun')
        url = reverse('plugins-api:netbox_rpki-api:aspareconciliationrun-create-plan', kwargs={'pk': self.reconciliation_run.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('item_count', response.data)
        self.assertEqual(response.data['source_reconciliation_run'], self.reconciliation_run.pk)

    def test_preview_action_returns_delta_and_execution(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-preview', kwargs={'pk': self.plan.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('delta', response.data)
        self.assertIn('execution', response.data)
        self.assertEqual(response.data['status'], rpki_models.ASPAChangePlanStatus.DRAFT)

    def test_approve_action_transitions_plan(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-approve', kwargs={'pk': self.plan.pk})

        response = self.client.post(url, {'ticket_reference': 'ASPA-CHG-100'}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, rpki_models.ASPAChangePlanStatus.APPROVED)
        self.assertEqual(self.plan.approved_by, self.user.username)
        self.assertEqual(response.data['approval_record']['ticket_reference'], 'ASPA-CHG-100')

    def test_approve_action_rejects_invalid_maintenance_window(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-approve', kwargs={'pk': self.plan.pk})

        response = self.client.post(
            url,
            {
                'ticket_reference': 'ASPA-CHG-101',
                'maintenance_window_start': '2026-04-13T02:00:00Z',
                'maintenance_window_end': '2026-04-13T01:00:00Z',
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, rpki_models.ASPAChangePlanStatus.DRAFT)

    def test_approve_serializer_exposes_only_governance_fields(self):
        serializer = ASPAChangePlanApproveActionSerializer()

        self.assertEqual(
            list(serializer.fields.keys()),
            [
                'requires_secondary_approval',
                'ticket_reference',
                'change_reference',
                'maintenance_window_start',
                'maintenance_window_end',
                'approval_notes',
            ],
        )

    def test_approve_serializer_drops_roa_only_acknowledgement_inputs(self):
        serializer = ASPAChangePlanApproveActionSerializer(
            data={
                'ticket_reference': 'ASPA-CHG-102',
                'acknowledged_finding_ids': [1],
                'acknowledged_simulation_result_ids': [2],
                'lint_acknowledgement_notes': 'ignored',
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data,
            {
                'requires_secondary_approval': False,
                'ticket_reference': 'ASPA-CHG-102',
            },
        )

    def test_apply_action_runs_provider_write_flow(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
        approve_aspa_change_plan(self.plan, approved_by='api-approver')
        followup_snapshot = create_test_provider_snapshot(
            name='Provider Write ASPA API Follow-Up Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_sync_run = create_test_provider_sync_run(
            name='Provider Write ASPA API Follow-Up Sync',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=followup_snapshot,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-apply', kwargs={'pk': self.plan.pk})

        with patch('netbox_rpki.api.views.apply_aspa_change_plan_provider_write', return_value=(
            create_test_provider_write_execution(
                name='Provider Write ASPA API Execution',
                organization=self.organization,
                provider_account=self.provider_account,
                provider_snapshot=self.provider_snapshot,
                change_plan=None,
                aspa_change_plan=self.plan,
                execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
                status=rpki_models.ValidationRunStatus.COMPLETED,
                followup_sync_run=followup_sync_run,
                followup_provider_snapshot=followup_snapshot,
            ),
            {'added': [], 'removed': []},
        )):
            response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['execution']['status'], rpki_models.ValidationRunStatus.COMPLETED)

    def test_apply_action_marks_plan_failed_on_krill_error(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
        approve_aspa_change_plan(self.plan, approved_by='api-approver')
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-apply', kwargs={'pk': self.plan.pk})

        with patch(
            'netbox_rpki.api.views.apply_aspa_change_plan_provider_write',
            side_effect=ProviderWriteError('krill rejected aspa delta'),
        ):
            response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 400)
        self.assertEqual(str(response.data[0]), 'krill rejected aspa delta')

    def test_summary_action_returns_aggregate_counts(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-summary')

        response = self.client.get(url, **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('total_plans', response.data)
        self.assertIn('by_status', response.data)
        self.assertIn('provider_add_count_total', response.data)

    def test_custom_actions_require_change_permission(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan')
        for action in ('preview', 'approve', 'apply'):
            url = reverse(f'plugins-api:netbox_rpki-api:aspachangeplan-{action}', kwargs={'pk': self.plan.pk})
            response = self.client.post(url, {}, format='json', **self.header)
            with self.subTest(action=action):
                self.assertHttpStatus(response, 404)


class ASPAChangePlanActionViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-write-aspa-view-org', name='Provider Write ASPA View Org')
        cls.provider_account = create_test_provider_account(
            name='Provider Write ASPA View Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-VIEW-ASPA-WRITE',
            ca_handle='ca-view-aspa-write',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Provider Write ASPA View Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.customer_as = create_test_asn(65890)
        cls.provider_as = create_test_asn(65891)
        create_test_aspa_intent(
            name='Provider Write ASPA View Intent',
            organization=cls.organization,
            customer_as=cls.customer_as,
            provider_as=cls.provider_as,
        )
        cls.reconciliation_run = reconcile_aspa_intents(
            cls.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.plan = create_aspa_change_plan(cls.reconciliation_run)

    def test_reconciliation_run_detail_shows_create_plan_button(self):
        self.add_permissions('netbox_rpki.view_aspareconciliationrun', 'netbox_rpki.change_aspareconciliationrun')

        response = self.client.get(self.reconciliation_run.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, reverse('plugins:netbox_rpki:aspareconciliationrun_create_plan', kwargs={'pk': self.reconciliation_run.pk}))

    def test_reconciliation_run_create_plan_view_creates_plan(self):
        self.add_permissions('netbox_rpki.view_aspareconciliationrun', 'netbox_rpki.change_aspareconciliationrun')

        response = self.client.post(
            reverse('plugins:netbox_rpki:aspareconciliationrun_create_plan', kwargs={'pk': self.reconciliation_run.pk}),
            {'confirm': True},
        )

        self.assertEqual(response.status_code, 302)
        self.assertGreaterEqual(rpki_models.ASPAChangePlan.objects.filter(source_reconciliation_run=self.reconciliation_run).count(), 2)

    def test_change_plan_detail_shows_preview_and_approve_buttons(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')

        response = self.client.get(self.plan.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, reverse('plugins:netbox_rpki:aspachangeplan_preview', kwargs={'pk': self.plan.pk}))
        self.assertContains(response, reverse('plugins:netbox_rpki:aspachangeplan_approve', kwargs={'pk': self.plan.pk}))
        self.assertNotContains(response, reverse('plugins:netbox_rpki:aspachangeplan_apply', kwargs={'pk': self.plan.pk}))

    def test_preview_view_renders_delta(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')

        response = self.client.get(reverse('plugins:netbox_rpki:aspachangeplan_preview', kwargs={'pk': self.plan.pk}))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'AS65890')

    def test_approve_view_renders_and_persists_governance_fields(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
        url = reverse('plugins:netbox_rpki:aspachangeplan_approve', kwargs={'pk': self.plan.pk})

        get_response = self.client.get(url)

        self.assertHttpStatus(get_response, 200)
        self.assertContains(get_response, 'Ticket Reference')
        self.assertContains(get_response, 'Change Reference')

        response = self.client.post(
            url,
            {
                'confirm': True,
                'ticket_reference': 'UI-ASPA-CHG-88',
                'change_reference': 'UI-ASPA-CAB-12',
                'maintenance_window_start': '2026-04-13T01:00',
                'maintenance_window_end': '2026-04-13T02:00',
                'approval_notes': 'ASPA window approved in UI.',
            },
        )

        self.assertRedirects(response, self.plan.get_absolute_url())
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.ticket_reference, 'UI-ASPA-CHG-88')
        self.assertEqual(self.plan.change_reference, 'UI-ASPA-CAB-12')
        self.assertEqual(self.plan.approval_records.count(), 1)

    def test_approve_form_exposes_only_governance_fields(self):
        form = ASPAChangePlanApprovalForm(plan=self.plan)

        self.assertEqual(
            list(form.fields.keys()),
            [
                'return_url',
                'confirm',
                'requires_secondary_approval',
                'ticket_reference',
                'change_reference',
                'maintenance_window_start',
                'maintenance_window_end',
                'approval_notes',
            ],
        )

    def test_approve_view_hides_roa_only_acknowledgement_inputs(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
        url = reverse('plugins:netbox_rpki:aspachangeplan_approve', kwargs={'pk': self.plan.pk})

        response = self.client.get(url)

        self.assertHttpStatus(response, 200)
        self.assertNotContains(response, 'Acknowledge Approval-Required Lint Findings')
        self.assertNotContains(response, 'Acknowledge Approval-Required Simulation Results')
        self.assertNotContains(
            response,
            'No current unsuppressed acknowledgement-required lint findings remain to acknowledge.',
        )

    def test_apply_view_shows_governance_metadata_after_approval(self):
        approve_aspa_change_plan(
            self.plan,
            approved_by='view-approver',
            ticket_reference='UI-ASPA-APPLY-1',
            change_reference='UI-ASPA-APPLY-CR',
        )
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')

        response = self.client.get(reverse('plugins:netbox_rpki:aspachangeplan_apply', kwargs={'pk': self.plan.pk}))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'UI-ASPA-APPLY-1')
        self.assertContains(response, 'UI-ASPA-APPLY-CR')

    def test_unsupported_provider_plan_hides_write_buttons(self):
        unsupported_account = create_test_provider_account(
            name='Provider Write ASPA View Unsupported Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            org_handle='ORG-VIEW-ASPA-ARIN',
        )
        unsupported_snapshot = create_test_provider_snapshot(
            name='Provider Write ASPA View Unsupported Snapshot',
            organization=self.organization,
            provider_account=unsupported_account,
            provider_name='ARIN',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        unsupported_plan = create_test_aspa_change_plan(
            name='Unsupported ASPA View Plan',
            organization=self.organization,
            source_reconciliation_run=self.reconciliation_run,
            provider_account=unsupported_account,
            provider_snapshot=unsupported_snapshot,
        )
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')

        response = self.client.get(unsupported_plan.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertNotContains(response, reverse('plugins:netbox_rpki:aspachangeplan_preview', kwargs={'pk': unsupported_plan.pk}))
        self.assertNotContains(response, reverse('plugins:netbox_rpki:aspachangeplan_approve', kwargs={'pk': unsupported_plan.pk}))
        self.assertNotContains(response, reverse('plugins:netbox_rpki:aspachangeplan_apply', kwargs={'pk': unsupported_plan.pk}))
