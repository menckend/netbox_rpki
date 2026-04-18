from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.intent_authority_map import (
    DRIFT_STATE_UNKNOWN,
    RUN_STATE_RECONCILED_CURRENT,
    RUN_STATE_RECONCILED_WITH_DRIFT,
    RUN_STATE_RECONCILIATION_FAILED,
    RUN_STATE_UNRECONCILED,
    RoaAuthorityMapFilters,
    build_publication_summary,
    build_reconciliation_summary,
    build_roa_authority_map,
    build_subject_label,
    classify_row,
    detect_prefix_overlaps,
)
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_intent_derivation_run,
    create_test_organization,
    create_test_prefix,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_roa_change_plan,
    create_test_roa_intent,
    create_test_roa_intent_result,
    create_test_roa_reconciliation_run,
    create_test_routing_intent_profile,
    create_test_routing_intent_template,
    create_test_routing_intent_template_binding,
)


class IntentAuthorityMapServiceTestCase(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.organization = create_test_organization(org_id='authority-map-org', name='Authority Map Org')
        self.profile = create_test_routing_intent_profile(
            name='Production Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            enabled=True,
        )

    def test_selects_latest_completed_derivation_per_profile(self):
        older = create_test_intent_derivation_run(
            name='Older Run',
            organization=self.organization,
            intent_profile=self.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now - timedelta(days=1),
        )
        newer = create_test_intent_derivation_run(
            name='Newer Run',
            organization=self.organization,
            intent_profile=self.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        create_test_roa_intent(
            name='Older Intent',
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=older,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64496,
            max_length=24,
        )
        create_test_roa_intent(
            name='Newer Intent',
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=newer,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64497,
            max_length=24,
        )

        result = build_roa_authority_map(filters=RoaAuthorityMapFilters())

        self.assertEqual(result.total_row_count, 1)
        self.assertEqual(result.rows[0].derivation_run.pk, newer.pk)
        self.assertEqual(result.rows[0].origin_asn_value, 64497)

    def test_excludes_draft_disabled_and_no_derivation_profiles_from_rows(self):
        disabled_profile = create_test_routing_intent_profile(
            name='Disabled Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            enabled=False,
        )
        create_test_routing_intent_profile(
            name='Draft Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.DRAFT,
            enabled=True,
        )
        completed_run = create_test_intent_derivation_run(
            organization=self.organization,
            intent_profile=self.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        create_test_roa_intent(
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=completed_run,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64496,
            max_length=24,
        )

        result = build_roa_authority_map(filters=RoaAuthorityMapFilters())

        self.assertEqual(result.total_row_count, 1)
        self.assertEqual(result.excluded_profile_count, 2)
        self.assertEqual(result.no_derivation_profile_count, 0)
        self.assertEqual(disabled_profile.name, 'Disabled Profile')

    def test_prefers_provider_imported_reconciliation_when_available(self):
        derivation_run = create_test_intent_derivation_run(
            organization=self.organization,
            intent_profile=self.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        intent = create_test_roa_intent(
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=derivation_run,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64496,
            max_length=24,
        )
        provider_account = create_test_provider_account(organization=self.organization, org_handle='ORG-AUTHORITY')
        provider_snapshot = create_test_provider_snapshot(
            organization=self.organization,
            provider_account=provider_account,
            completed_at=self.now,
        )
        local_run = create_test_roa_reconciliation_run(
            organization=self.organization,
            intent_profile=self.profile,
            basis_derivation_run=derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now - timedelta(minutes=5),
        )
        provider_run = create_test_roa_reconciliation_run(
            organization=self.organization,
            intent_profile=self.profile,
            basis_derivation_run=derivation_run,
            provider_snapshot=provider_snapshot,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now - timedelta(minutes=10),
        )
        create_test_roa_intent_result(
            reconciliation_run=local_run,
            roa_intent=intent,
            result_type=rpki_models.ROAIntentResultType.MISSING,
        )
        create_test_roa_intent_result(
            reconciliation_run=provider_run,
            roa_intent=intent,
            result_type=rpki_models.ROAIntentResultType.MATCH,
        )

        result = build_roa_authority_map(filters=RoaAuthorityMapFilters())

        self.assertEqual(result.rows[0].comparison_scope, rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED)
        self.assertEqual(result.rows[0].run_state, RUN_STATE_RECONCILED_CURRENT)

    def test_marks_failed_when_latest_reconciliation_failed(self):
        derivation_run = create_test_intent_derivation_run(
            organization=self.organization,
            intent_profile=self.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        intent = create_test_roa_intent(
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=derivation_run,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64496,
            max_length=24,
        )
        completed_run = create_test_roa_reconciliation_run(
            organization=self.organization,
            intent_profile=self.profile,
            basis_derivation_run=derivation_run,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now - timedelta(hours=1),
        )
        create_test_roa_intent_result(
            reconciliation_run=completed_run,
            roa_intent=intent,
            result_type=rpki_models.ROAIntentResultType.MATCH,
        )
        create_test_roa_reconciliation_run(
            organization=self.organization,
            intent_profile=self.profile,
            basis_derivation_run=derivation_run,
            status=rpki_models.ValidationRunStatus.FAILED,
            completed_at=self.now,
        )

        result = build_roa_authority_map(filters=RoaAuthorityMapFilters())

        self.assertEqual(result.rows[0].run_state, RUN_STATE_RECONCILIATION_FAILED)
        self.assertEqual(result.rows[0].drift_state, DRIFT_STATE_UNKNOWN)

    def test_filters_by_run_state_and_search(self):
        derivation_run = create_test_intent_derivation_run(
            organization=self.organization,
            intent_profile=self.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        drift_intent = create_test_roa_intent(
            name='Drift Intent',
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=derivation_run,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64496,
            max_length=24,
            explanation='Production edge prefix',
        )
        current_intent = create_test_roa_intent(
            name='Current Intent',
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=derivation_run,
            prefix_cidr_text='198.51.100.0/24',
            origin_asn_value=64497,
            max_length=24,
        )
        reconciliation_run = create_test_roa_reconciliation_run(
            organization=self.organization,
            intent_profile=self.profile,
            basis_derivation_run=derivation_run,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        create_test_roa_intent_result(
            reconciliation_run=reconciliation_run,
            roa_intent=drift_intent,
            result_type=rpki_models.ROAIntentResultType.MISSING,
        )
        create_test_roa_intent_result(
            reconciliation_run=reconciliation_run,
            roa_intent=current_intent,
            result_type=rpki_models.ROAIntentResultType.MATCH,
        )

        result = build_roa_authority_map(
            filters=RoaAuthorityMapFilters(run_state=RUN_STATE_RECONCILED_WITH_DRIFT, q='production')
        )

        self.assertEqual(result.total_row_count, 1)
        self.assertEqual(result.rows[0].drift_state, 'missing')

    def test_detects_overlap_across_profiles(self):
        other_profile = create_test_routing_intent_profile(
            name='Backup Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            enabled=True,
        )
        primary_run = create_test_intent_derivation_run(
            organization=self.organization,
            intent_profile=self.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        backup_run = create_test_intent_derivation_run(
            organization=self.organization,
            intent_profile=other_profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        row_a = build_roa_authority_map(filters=RoaAuthorityMapFilters()).rows
        self.assertEqual(row_a, [])
        intent_a = create_test_roa_intent(
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=primary_run,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64496,
            max_length=24,
        )
        intent_b = create_test_roa_intent(
            organization=self.organization,
            intent_profile=other_profile,
            derivation_run=backup_run,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64497,
            max_length=24,
        )

        result = build_roa_authority_map(filters=RoaAuthorityMapFilters())
        overlaps = detect_prefix_overlaps(result.rows)

        self.assertIn(intent_a.intent_key, overlaps)
        self.assertIn(intent_b.intent_key, overlaps)
        self.assertEqual(result.overlap_count, 2)

    def test_parse_binding_freshness_and_profile_warning(self):
        derivation_run = create_test_intent_derivation_run(
            organization=self.organization,
            intent_profile=self.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        template = create_test_routing_intent_template(organization=self.organization)
        binding = create_test_routing_intent_template_binding(
            name='Edge Binding',
            template=template,
            intent_profile=self.profile,
            state=rpki_models.RoutingIntentTemplateBindingState.STALE,
        )
        create_test_roa_intent(
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=derivation_run,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64496,
            max_length=24,
            summary_json={
                'profile_context_group_names': ['Edge Services'],
                'binding_context_groups': {str(binding.pk): ['Binding Edge Group']},
            },
        )

        result = build_roa_authority_map(filters=RoaAuthorityMapFilters())

        self.assertEqual(result.rows[0].binding_freshness, rpki_models.RoutingIntentTemplateBindingState.STALE)
        self.assertEqual(result.rows[0].template_binding_names, ('Edge Binding',))
        self.assertEqual(result.profiles_with_stale_bindings, ['Production Profile'])

    def test_build_subject_label_and_summaries(self):
        intent = create_test_roa_intent(
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=create_test_intent_derivation_run(
                organization=self.organization,
                intent_profile=self.profile,
                status=rpki_models.ValidationRunStatus.COMPLETED,
                completed_at=self.now,
            ),
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64496,
            max_length=24,
        )
        self.assertEqual(build_subject_label(intent), '192.0.2.0/24 -> AS64496 /24')
        as0_intent = create_test_roa_intent(
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=intent.derivation_run,
            prefix_cidr_text='198.51.100.0/24',
            is_as0=True,
        )
        self.assertEqual(build_subject_label(as0_intent), '198.51.100.0/24 -> AS0')
        self.assertEqual(build_reconciliation_summary(None), 'Not reconciled')

    def test_publication_summary_for_plan_statuses(self):
        derivation_run = create_test_intent_derivation_run(
            organization=self.organization,
            intent_profile=self.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        reconciliation_run = create_test_roa_reconciliation_run(
            organization=self.organization,
            intent_profile=self.profile,
            basis_derivation_run=derivation_run,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        plan = create_test_roa_change_plan(
            organization=self.organization,
            source_reconciliation_run=reconciliation_run,
            status=rpki_models.ROAChangePlanStatus.APPROVED,
            requires_secondary_approval=True,
        )
        self.assertEqual(build_publication_summary(plan), 'Plan: APPROVED (dual-approval)')
        plan.status = rpki_models.ROAChangePlanStatus.APPLIED
        plan.applied_at = self.now
        self.assertEqual(build_publication_summary(plan), f'Plan: APPLIED {self.now.date().isoformat()}')
        self.assertEqual(build_publication_summary(None), 'No plan')

    def test_classify_row_maps_result_types(self):
        derivation_run = create_test_intent_derivation_run(
            organization=self.organization,
            intent_profile=self.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        intent = create_test_roa_intent(
            organization=self.organization,
            intent_profile=self.profile,
            derivation_run=derivation_run,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64496,
            max_length=24,
        )
        self.assertEqual(classify_row(intent=intent, intent_result=None, reconciliation_run=None), (RUN_STATE_UNRECONCILED, 'unknown', ''))
        reconciliation_run = create_test_roa_reconciliation_run(
            organization=self.organization,
            intent_profile=self.profile,
            basis_derivation_run=derivation_run,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=self.now,
        )
        result = create_test_roa_intent_result(
            reconciliation_run=reconciliation_run,
            roa_intent=intent,
            result_type=rpki_models.ROAIntentResultType.MATCH,
            severity=rpki_models.ReconciliationSeverity.INFO,
        )
        self.assertEqual(classify_row(intent=intent, intent_result=result, reconciliation_run=reconciliation_run), (RUN_STATE_RECONCILED_CURRENT, 'match', 'info'))
        result.result_type = rpki_models.ROAIntentResultType.ASN_MISMATCH
        result.severity = rpki_models.ReconciliationSeverity.CRITICAL
        self.assertEqual(classify_row(intent=intent, intent_result=result, reconciliation_run=reconciliation_run), (RUN_STATE_RECONCILED_WITH_DRIFT, 'origin_mismatch', 'critical'))
