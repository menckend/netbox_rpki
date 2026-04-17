from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tenancy.models import Tenant

from netbox_rpki import models as rpki_models
from netbox_rpki.api.serializers import SERIALIZER_CLASS_MAP
from netbox_rpki.services import (
    compile_routing_intent_policy,
    create_roa_change_plan,
    derive_roa_intents,
    lift_roa_lint_suppression,
    preview_routing_intent_template_binding,
    refresh_routing_intent_template_binding_state,
    reconcile_roa_intents,
    RoutingIntentExecutionError,
    run_bulk_routing_intent_pipeline,
    run_roa_lint,
    run_routing_intent_template_binding_pipeline,
    simulate_roa_change_plan,
    suppress_roa_lint_finding,
)
from netbox_rpki.tests.base import PluginAPITestCase
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_certificate,
    create_test_external_management_exception,
    create_test_imported_roa_authorization,
    create_test_organization,
    create_test_prefix,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_roa,
    create_test_roa_change_plan,
    create_test_roa_change_plan_item,
    create_test_roa_change_plan_matrix,
    create_test_roa_intent,
    create_test_roa_prefix,
    create_test_routing_intent_profile,
    create_test_routing_intent_exception,
    create_test_routing_intent_context_criterion,
    create_test_routing_intent_context_group,
    create_test_routing_intent_rule,
    create_test_routing_intent_template,
    create_test_routing_intent_template_binding,
    create_test_routing_intent_template_rule,
    create_test_roa_intent_override,
)


class RoutingIntentServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='intent-org', name='Intent Org')
        cls.tenant = Tenant.objects.create(name='Intent Tenant', slug='intent-tenant')
        cls.primary_prefix = create_test_prefix('10.55.0.0/24', tenant=cls.tenant, status='active')
        cls.secondary_prefix = create_test_prefix('10.56.0.0/24', tenant=cls.tenant, status='active')
        cls.origin_asn = create_test_asn(65551)
        cls.profile = create_test_routing_intent_profile(
            name='Intent Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query='tenant_id={tenant_id}'.format(tenant_id=cls.tenant.pk),
            asn_selector_query='id={asn_id}'.format(asn_id=cls.origin_asn.pk),
        )
        cls.suppress_override = create_test_roa_intent_override(
            name='Suppress Secondary',
            organization=cls.organization,
            intent_profile=cls.profile,
            action=rpki_models.ROAIntentOverrideAction.SUPPRESS,
            prefix=cls.secondary_prefix,
        )

    def test_derivation_creates_active_and_suppressed_intents(self):
        derivation_run = derive_roa_intents(self.profile)

        intents = list(derivation_run.roa_intents.order_by('prefix_cidr_text'))
        self.assertEqual(derivation_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(derivation_run.prefix_count_scanned, 2)
        self.assertEqual(len(intents), 2)

        self.assertEqual(intents[0].prefix, self.primary_prefix)
        self.assertEqual(intents[0].derived_state, rpki_models.ROAIntentDerivedState.ACTIVE)
        self.assertEqual(intents[0].origin_asn, self.origin_asn)
        self.assertEqual(intents[0].max_length, 24)

        self.assertEqual(intents[1].prefix, self.secondary_prefix)
        self.assertEqual(intents[1].derived_state, rpki_models.ROAIntentDerivedState.SUPPRESSED)
        self.assertEqual(intents[1].applied_override, self.suppress_override)

    def test_template_binding_derivation_applies_selector_narrowing_and_persists_binding_state(self):
        profile = create_test_routing_intent_profile(
            name='Template Binding Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'tenant_id={self.tenant.pk}',
            asn_selector_query='id=999999999',
        )
        template = create_test_routing_intent_template(
            name='Reusable Tenant Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Template Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Primary Prefix Binding',
            template=template,
            intent_profile=profile,
            origin_asn_override=self.origin_asn,
            max_length_mode=rpki_models.RoutingIntentRuleMaxLengthMode.EXPLICIT,
            max_length_value=25,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )

        derivation_run = derive_roa_intents(profile)
        intents = {intent.prefix_id: intent for intent in derivation_run.roa_intents.all()}
        binding.refresh_from_db()

        self.assertEqual(intents[self.primary_prefix.pk].derived_state, rpki_models.ROAIntentDerivedState.ACTIVE)
        self.assertEqual(intents[self.primary_prefix.pk].origin_asn, self.origin_asn)
        self.assertEqual(intents[self.primary_prefix.pk].max_length, 25)
        self.assertEqual(intents[self.secondary_prefix.pk].derived_state, rpki_models.ROAIntentDerivedState.SHADOWED)
        self.assertEqual(binding.state, rpki_models.RoutingIntentTemplateBindingState.CURRENT)
        self.assertTrue(binding.last_compiled_fingerprint)
        self.assertEqual(binding.summary_json['scoped_prefix_count'], 1)
        self.assertEqual(binding.summary_json['template_id'], template.pk)
        self.assertEqual(binding.summary_json['regeneration_reason_summary'], 'Binding has not been regenerated yet.')

    def test_local_profile_rules_override_template_derived_policy(self):
        profile = create_test_routing_intent_profile(
            name='Template Override Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
            asn_selector_query='id=999999999',
        )
        template_origin = create_test_asn(65581)
        local_origin = create_test_asn(65582)
        template = create_test_routing_intent_template(
            name='Template Override Source',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Template Set Origin',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.SET_ORIGIN,
            origin_asn=template_origin,
        )
        create_test_routing_intent_template_binding(
            name='Template Binding',
            template=template,
            intent_profile=profile,
            max_length_mode=rpki_models.RoutingIntentRuleMaxLengthMode.EXPLICIT,
            max_length_value=24,
        )
        local_rule = create_test_routing_intent_rule(
            name='Local Set Origin',
            intent_profile=profile,
            action=rpki_models.RoutingIntentRuleAction.SET_ORIGIN,
            origin_asn=local_origin,
            match_tenant=self.tenant,
        )

        derivation_run = derive_roa_intents(profile)
        intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)

        self.assertEqual(intent.origin_asn, local_origin)
        self.assertEqual(intent.source_rule, local_rule)
        self.assertIn('Applied template rule Template Set Origin', intent.explanation)
        self.assertIn('Applied rule Local Set Origin', intent.explanation)

    def test_typed_exception_suppresses_prefix_after_local_rules(self):
        local_origin = create_test_asn(65587)
        create_test_routing_intent_rule(
            name='Include Local Prefix',
            intent_profile=self.profile,
            action=rpki_models.RoutingIntentRuleAction.SET_ORIGIN,
            origin_asn=local_origin,
            match_tenant=self.tenant,
        )
        create_test_routing_intent_exception(
            name='Suppress Primary Prefix',
            organization=self.organization,
            intent_profile=self.profile,
            prefix=self.primary_prefix,
            exception_type=rpki_models.RoutingIntentExceptionType.MITIGATION,
            effect_mode=rpki_models.RoutingIntentExceptionEffectMode.SUPPRESS,
            approved_at=timezone.now(),
            approved_by='approver',
        )

        derivation_run = derive_roa_intents(self.profile)
        primary_intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)

        self.assertEqual(primary_intent.derived_state, rpki_models.ROAIntentDerivedState.SUPPRESSED)
        self.assertIn('Applied exception Suppress Primary Prefix (suppress).', primary_intent.explanation)

    def test_binding_scoped_temporary_replacement_updates_origin_and_max_length(self):
        profile = create_test_routing_intent_profile(
            name='Exception Binding Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
            asn_selector_query='id=999999999',
        )
        template = create_test_routing_intent_template(
            name='Exception Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Exception Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Exception Binding',
            template=template,
            intent_profile=profile,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )
        replacement_origin = create_test_asn(65588)
        create_test_routing_intent_exception(
            name='Temporary Replacement',
            organization=self.organization,
            intent_profile=profile,
            template_binding=binding,
            prefix=self.primary_prefix,
            exception_type=rpki_models.RoutingIntentExceptionType.TRAFFIC_ENGINEERING,
            effect_mode=rpki_models.RoutingIntentExceptionEffectMode.TEMPORARY_REPLACEMENT,
            origin_asn=replacement_origin,
            max_length=27,
            approved_at=timezone.now(),
            approved_by='approver',
        )

        derivation_run = derive_roa_intents(profile)
        primary_intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)

        self.assertEqual(primary_intent.origin_asn, replacement_origin)
        self.assertEqual(primary_intent.max_length, 27)
        self.assertIn('Applied exception Temporary Replacement (temporary_replacement).', primary_intent.explanation)

    def test_profile_context_groups_narrow_candidate_prefixes_and_persist_summary(self):
        self.primary_prefix.custom_field_data = {'service_context': 'edge'}
        self.primary_prefix.save()
        self.secondary_prefix.custom_field_data = {'service_context': 'core'}
        self.secondary_prefix.save()

        context_group = create_test_routing_intent_context_group(
            name='Edge Services',
            organization=self.organization,
        )
        create_test_routing_intent_context_criterion(
            name='Edge Service Context',
            context_group=context_group,
            criterion_type=rpki_models.RoutingIntentContextCriterionType.CUSTOM_FIELD,
            match_value='service_context=edge',
        )
        self.profile.context_groups.add(context_group)

        derivation_run = derive_roa_intents(self.profile)
        primary_intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)
        secondary_intent = derivation_run.roa_intents.get(prefix=self.secondary_prefix)

        self.assertEqual(primary_intent.derived_state, rpki_models.ROAIntentDerivedState.ACTIVE)
        self.assertEqual(secondary_intent.derived_state, rpki_models.ROAIntentDerivedState.SUPPRESSED)
        self.assertIn('Matched profile context groups: Edge Services.', primary_intent.explanation)
        self.assertEqual(primary_intent.summary_json['profile_context_group_names'], ['Edge Services'])
        self.assertEqual(secondary_intent.summary_json['profile_context_group_names'], [])

    def test_binding_context_groups_gate_binding_application(self):
        self.primary_prefix.custom_field_data = {'service_context': 'edge'}
        self.primary_prefix.save()
        self.secondary_prefix.custom_field_data = {'service_context': 'core'}
        self.secondary_prefix.save()

        profile = create_test_routing_intent_profile(
            name='Binding Context Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'tenant_id={self.tenant.pk}',
            asn_selector_query='id=999999999',
        )
        template = create_test_routing_intent_template(
            name='Binding Context Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Binding Context Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Edge Binding',
            template=template,
            intent_profile=profile,
            origin_asn_override=self.origin_asn,
        )
        context_group = create_test_routing_intent_context_group(
            name='Binding Edge Group',
            organization=self.organization,
        )
        create_test_routing_intent_context_criterion(
            name='Binding Edge Criterion',
            context_group=context_group,
            criterion_type=rpki_models.RoutingIntentContextCriterionType.CUSTOM_FIELD,
            match_value='service_context=edge',
        )
        binding.context_groups.add(context_group)

        derivation_run = derive_roa_intents(profile)
        primary_intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)
        secondary_intent = derivation_run.roa_intents.get(prefix=self.secondary_prefix)

        self.assertEqual(primary_intent.origin_asn, self.origin_asn)
        self.assertEqual(secondary_intent.derived_state, rpki_models.ROAIntentDerivedState.SHADOWED)
        self.assertIn('Binding context groups: Binding Edge Group.', primary_intent.explanation)
        self.assertIn('Skipped template binding Edge Binding because no binding context group matched.', secondary_intent.explanation)
        self.assertEqual(primary_intent.summary_json['binding_context_groups'][str(binding.pk)], ['Binding Edge Group'])

    def test_unresolved_provider_account_context_emits_warning(self):
        provider_account = create_test_provider_account(
            organization=self.organization,
            org_handle='ORG-INTENT',
        )
        context_group = create_test_routing_intent_context_group(
            name='Provider Scoped',
            organization=self.organization,
        )
        create_test_routing_intent_context_criterion(
            name='Provider Criterion',
            context_group=context_group,
            criterion_type=rpki_models.RoutingIntentContextCriterionType.PROVIDER_ACCOUNT,
            match_provider_account=provider_account,
        )
        self.profile.context_groups.add(context_group)

        derivation_run = derive_roa_intents(self.profile)

        self.assertIn('Unable to resolve provider-account context', derivation_run.error_summary)

    def test_provider_account_context_resolves_delegated_ownership(self):
        provider_account = create_test_provider_account(
            name='Delegated Intent Provider',
            organization=self.organization,
            org_handle='ORG-INTENT-DELEGATED',
        )
        delegated_entity = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='Delegated Intent Entity',
            organization=self.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.CUSTOMER,
        )
        managed_relationship = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='Delegated Intent Relationship',
            organization=self.organization,
            delegated_entity=delegated_entity,
            provider_account=provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        context_group = create_test_routing_intent_context_group(
            name='Delegated Provider Scoped',
            organization=self.organization,
        )
        create_test_routing_intent_context_criterion(
            name='Delegated Provider Criterion',
            context_group=context_group,
            criterion_type=rpki_models.RoutingIntentContextCriterionType.PROVIDER_ACCOUNT,
            match_provider_account=provider_account,
        )
        self.profile.context_groups.add(context_group)
        self.primary_prefix.custom_field_data = {'provider_account_id': provider_account.pk}
        self.primary_prefix.save(update_fields=['custom_field_data'])

        derivation_run = derive_roa_intents(self.profile)
        primary_intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)

        self.assertEqual(primary_intent.delegated_entity, delegated_entity)
        self.assertEqual(primary_intent.managed_relationship, managed_relationship)
        self.assertEqual(primary_intent.summary_json['delegated_scope']['ownership_scope'], 'managed_relationship')
        self.assertEqual(primary_intent.summary_json['delegated_scope']['provider_account_id'], provider_account.pk)
        self.assertEqual(primary_intent.summary_json['delegated_scope']['managed_relationship_id'], managed_relationship.pk)
        self.assertIn('Delegated ownership resolved via managed relationship', primary_intent.explanation)

    def test_provider_account_context_with_multiple_relationships_stays_unscoped(self):
        provider_account = create_test_provider_account(
            name='Ambiguous Delegated Provider',
            organization=self.organization,
            org_handle='ORG-INTENT-AMBIGUOUS',
        )
        delegated_entity_a = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='Ambiguous Delegated Entity A',
            organization=self.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.CUSTOMER,
        )
        delegated_entity_b = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='Ambiguous Delegated Entity B',
            organization=self.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.DOWNSTREAM,
        )
        rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='Ambiguous Delegated Relationship A',
            organization=self.organization,
            delegated_entity=delegated_entity_a,
            provider_account=provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='Ambiguous Delegated Relationship B',
            organization=self.organization,
            delegated_entity=delegated_entity_b,
            provider_account=provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        context_group = create_test_routing_intent_context_group(
            name='Ambiguous Provider Scoped',
            organization=self.organization,
        )
        create_test_routing_intent_context_criterion(
            name='Ambiguous Provider Criterion',
            context_group=context_group,
            criterion_type=rpki_models.RoutingIntentContextCriterionType.PROVIDER_ACCOUNT,
            match_provider_account=provider_account,
        )
        self.profile.context_groups.add(context_group)
        self.primary_prefix.custom_field_data = {'provider_account_id': provider_account.pk}
        self.primary_prefix.save(update_fields=['custom_field_data'])

        derivation_run = derive_roa_intents(self.profile)
        primary_intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)

        self.assertIsNone(primary_intent.delegated_entity)
        self.assertIsNone(primary_intent.managed_relationship)
        self.assertEqual(
            primary_intent.summary_json['delegated_scope']['resolution_status'],
            'ambiguous_managed_relationships',
        )
        self.assertIn('multiple active managed authorization relationships', derivation_run.error_summary)

    def test_delegated_scope_carries_into_reconciliation_and_change_plan(self):
        provider_account = create_test_provider_account(
            name='Delegated Flow Provider',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-INTENT-FLOW',
            ca_handle='ca-intent-flow',
            api_base_url='https://krill.example.invalid',
        )
        delegated_entity = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='Delegated Flow Entity',
            organization=self.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.CUSTOMER,
        )
        managed_relationship = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='Delegated Flow Relationship',
            organization=self.organization,
            delegated_entity=delegated_entity,
            provider_account=provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        context_group = create_test_routing_intent_context_group(
            name='Delegated Flow Scoped',
            organization=self.organization,
        )
        create_test_routing_intent_context_criterion(
            name='Delegated Flow Provider Criterion',
            context_group=context_group,
            criterion_type=rpki_models.RoutingIntentContextCriterionType.PROVIDER_ACCOUNT,
            match_provider_account=provider_account,
        )
        self.profile.context_groups.add(context_group)
        self.primary_prefix.custom_field_data = {'provider_account_id': provider_account.pk}
        self.primary_prefix.save(update_fields=['custom_field_data'])

        derivation_run = derive_roa_intents(self.profile)
        provider_snapshot = create_test_provider_snapshot(
            name='Delegated Flow Snapshot',
            organization=self.organization,
            provider_account=provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        plan = create_roa_change_plan(reconciliation_run)

        intent_result = reconciliation_run.intent_results.get(roa_intent__prefix=self.primary_prefix)
        create_item = plan.items.get(action_type=rpki_models.ROAChangePlanAction.CREATE)

        self.assertEqual(
            intent_result.details_json['delegated_scope']['managed_relationship_id'],
            managed_relationship.pk,
        )
        self.assertEqual(
            create_item.after_state_json['delegated_scope']['delegated_entity_id'],
            delegated_entity.pk,
        )
        self.assertEqual(plan.summary_json['delegated_scoped_item_count'], 1)
        self.assertEqual(plan.delegated_entity, delegated_entity)
        self.assertEqual(plan.managed_relationship, managed_relationship)
        self.assertEqual(plan.summary_json['delegated_scope_status'], 'managed_relationship')

    def test_expired_exception_does_not_apply(self):
        create_test_routing_intent_exception(
            name='Expired Suppression',
            organization=self.organization,
            intent_profile=self.profile,
            prefix=self.primary_prefix,
            effect_mode=rpki_models.RoutingIntentExceptionEffectMode.SUPPRESS,
            starts_at=timezone.now() - timedelta(days=2),
            ends_at=timezone.now() - timedelta(days=1),
            approved_at=timezone.now() - timedelta(days=3),
            approved_by='approver',
        )

        derivation_run = derive_roa_intents(self.profile)
        primary_intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)

        self.assertEqual(primary_intent.derived_state, rpki_models.ROAIntentDerivedState.ACTIVE)
        self.assertNotIn('Expired Suppression', primary_intent.explanation)

    def test_legacy_override_still_outranks_typed_exception(self):
        replacement_origin = create_test_asn(65589)
        create_test_routing_intent_exception(
            name='Exception Replacement',
            organization=self.organization,
            intent_profile=self.profile,
            prefix=self.primary_prefix,
            effect_mode=rpki_models.RoutingIntentExceptionEffectMode.TEMPORARY_REPLACEMENT,
            origin_asn=replacement_origin,
            max_length=28,
            approved_at=timezone.now(),
            approved_by='approver',
        )
        override_origin = create_test_asn(65590)
        override = create_test_roa_intent_override(
            name='Override Replacement',
            organization=self.organization,
            intent_profile=self.profile,
            prefix=self.primary_prefix,
            action=rpki_models.ROAIntentOverrideAction.REPLACE_ORIGIN,
            origin_asn=override_origin,
        )

        derivation_run = derive_roa_intents(self.profile)
        primary_intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)

        self.assertEqual(primary_intent.origin_asn, override_origin)
        self.assertEqual(primary_intent.applied_override, override)

    def test_unapproved_exception_does_not_apply_until_approved(self):
        create_test_routing_intent_exception(
            name='Pending Approval Suppression',
            organization=self.organization,
            intent_profile=self.profile,
            prefix=self.primary_prefix,
            effect_mode=rpki_models.RoutingIntentExceptionEffectMode.SUPPRESS,
        )

        derivation_run = derive_roa_intents(self.profile)
        primary_intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)

        self.assertEqual(primary_intent.derived_state, rpki_models.ROAIntentDerivedState.ACTIVE)
        self.assertNotIn('Pending Approval Suppression', primary_intent.explanation)

    def test_refresh_binding_state_reports_noop_when_fingerprint_is_unchanged(self):
        template = create_test_routing_intent_template(
            name='Refresh Noop Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Refresh Noop Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Refresh Noop Binding',
            template=template,
            intent_profile=self.profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )

        run_routing_intent_template_binding_pipeline(binding)
        assessment = refresh_routing_intent_template_binding_state(binding)
        binding.refresh_from_db()

        self.assertEqual(assessment.state, rpki_models.RoutingIntentTemplateBindingState.CURRENT)
        self.assertFalse(assessment.changed)
        self.assertEqual(assessment.reason_summary, 'No material drift detected.')
        self.assertEqual(binding.state, rpki_models.RoutingIntentTemplateBindingState.CURRENT)

    def test_refresh_binding_state_marks_stale_when_template_policy_changes(self):
        template = create_test_routing_intent_template(
            name='Refresh Stale Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        rule = create_test_routing_intent_template_rule(
            name='Refresh Stale Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Refresh Stale Binding',
            template=template,
            intent_profile=self.profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )

        run_routing_intent_template_binding_pipeline(binding)
        rule.origin_asn = create_test_asn(65591)
        rule.action = rpki_models.RoutingIntentRuleAction.SET_ORIGIN
        rule.save()

        assessment = refresh_routing_intent_template_binding_state(binding)
        binding.refresh_from_db()

        self.assertEqual(assessment.state, rpki_models.RoutingIntentTemplateBindingState.STALE)
        self.assertTrue(assessment.changed)
        self.assertIn('template_policy_changed', assessment.reason_codes)
        self.assertEqual(binding.state, rpki_models.RoutingIntentTemplateBindingState.STALE)

    def test_refresh_binding_state_marks_pending_before_first_regeneration(self):
        template = create_test_routing_intent_template(
            name='Refresh Pending Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Refresh Pending Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Refresh Pending Binding',
            template=template,
            intent_profile=self.profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )

        assessment = refresh_routing_intent_template_binding_state(binding)
        binding.refresh_from_db()

        self.assertEqual(assessment.state, rpki_models.RoutingIntentTemplateBindingState.PENDING)
        self.assertFalse(assessment.changed)
        self.assertIn('never_compiled', assessment.reason_codes)
        self.assertEqual(binding.state, rpki_models.RoutingIntentTemplateBindingState.PENDING)

    def test_non_material_template_comment_change_does_not_mark_binding_stale(self):
        template = create_test_routing_intent_template(
            name='Refresh Comment Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Refresh Comment Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Refresh Comment Binding',
            template=template,
            intent_profile=self.profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )

        run_routing_intent_template_binding_pipeline(binding)
        template.comments = 'presentation-only note'
        template.save(update_fields=('comments',))

        assessment = refresh_routing_intent_template_binding_state(binding)

        self.assertEqual(assessment.state, rpki_models.RoutingIntentTemplateBindingState.CURRENT)

    def test_higher_priority_template_binding_wins_and_emits_warning(self):
        profile = create_test_routing_intent_profile(
            name='Binding Priority Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
            asn_selector_query='id=999999999',
        )
        lower_origin = create_test_asn(65583)
        higher_origin = create_test_asn(65584)
        lower_template = create_test_routing_intent_template(
            name='Lower Priority Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        higher_template = create_test_routing_intent_template(
            name='Higher Priority Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Lower Origin Rule',
            template=lower_template,
            action=rpki_models.RoutingIntentRuleAction.SET_ORIGIN,
            origin_asn=lower_origin,
        )
        create_test_routing_intent_template_rule(
            name='Higher Origin Rule',
            template=higher_template,
            action=rpki_models.RoutingIntentRuleAction.SET_ORIGIN,
            origin_asn=higher_origin,
        )
        create_test_routing_intent_template_binding(
            name='Lower Binding',
            template=lower_template,
            intent_profile=profile,
            binding_priority=100,
        )
        create_test_routing_intent_template_binding(
            name='Higher Binding',
            template=higher_template,
            intent_profile=profile,
            binding_priority=200,
        )

        derivation_run = derive_roa_intents(profile)
        intent = derivation_run.roa_intents.get(prefix=self.primary_prefix)

        self.assertEqual(intent.origin_asn, higher_origin)
        self.assertGreaterEqual(derivation_run.warning_count, 1)
        self.assertIn('overrode template-derived policy', derivation_run.error_summary)

    def test_preview_template_binding_compiles_without_writing_derivation_rows(self):
        profile = create_test_routing_intent_profile(
            name='Preview Binding Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
            asn_selector_query='id=999999999',
        )
        template = create_test_routing_intent_template(
            name='Preview Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.DRAFT,
            enabled=False,
        )
        create_test_routing_intent_template_rule(
            name='Preview Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Preview Binding',
            template=template,
            intent_profile=profile,
            origin_asn_override=self.origin_asn,
        )

        preview = preview_routing_intent_template_binding(binding)

        self.assertEqual(rpki_models.IntentDerivationRun.objects.filter(intent_profile=profile).count(), 0)
        self.assertEqual(len(preview.results), 1)
        self.assertEqual(preview.results[0].origin_asn, self.origin_asn)
        self.assertEqual(preview.results[0].derived_state, rpki_models.ROAIntentDerivedState.ACTIVE)
        self.assertEqual(preview.compiled_policy.template_bindings[0].binding.pk, binding.pk)

    def test_binding_regeneration_persists_stable_summary_contract_keys(self):
        template = create_test_routing_intent_template(
            name='Summary Contract Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Summary Contract Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Summary Contract Binding',
            template=template,
            intent_profile=self.profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )

        run_routing_intent_template_binding_pipeline(binding)
        binding.refresh_from_db()
        summary = binding.summary_json

        self.assertEqual(binding.state, rpki_models.RoutingIntentTemplateBindingState.CURRENT)
        self.assertTrue(
            {
                'template_id',
                'template_version',
                'template_fingerprint',
                'binding_fingerprint',
                'scoped_prefix_count',
                'scoped_asn_count',
                'active_rule_count',
                'warning_count',
                'warnings',
                'previous_binding_fingerprint',
                'regeneration_reason_codes',
                'regeneration_reason_summary',
                'candidate_binding_fingerprint',
            }.issubset(summary)
        )
        self.assertEqual(summary['template_id'], template.pk)
        self.assertEqual(summary['template_version'], template.template_version)
        self.assertEqual(summary['scoped_prefix_count'], 1)
        self.assertEqual(summary['scoped_asn_count'], 1)
        self.assertEqual(summary['warning_count'], 0)
        self.assertEqual(summary['warnings'], [])
        self.assertIsNone(summary['previous_binding_fingerprint'])
        self.assertEqual(summary['regeneration_reason_codes'], ['never_compiled'])
        self.assertEqual(summary['candidate_binding_fingerprint'], binding.last_compiled_fingerprint)

    def test_invalid_binding_selector_persists_error_only_summary_payload(self):
        template = create_test_routing_intent_template(
            name='Invalid Selector Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Invalid Selector Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Invalid Selector Binding',
            template=template,
            intent_profile=self.profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query='not_a_real_filter=value',
        )

        assessment = refresh_routing_intent_template_binding_state(binding)

        binding.refresh_from_db()

        self.assertEqual(assessment.state, rpki_models.RoutingIntentTemplateBindingState.PENDING)
        self.assertEqual(binding.state, rpki_models.RoutingIntentTemplateBindingState.PENDING)
        self.assertIn('template_id', binding.summary_json)
        self.assertIn('candidate_binding_fingerprint', binding.summary_json)
        self.assertNotIn('error', binding.summary_json)

    def test_bulk_pipeline_persists_stable_summary_contract_on_mixed_success(self):
        binding_profile = create_test_routing_intent_profile(
            name='Mixed Bulk Binding Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
            asn_selector_query='id=999999999',
        )
        template = create_test_routing_intent_template(
            name='Mixed Bulk Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Mixed Bulk Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Mixed Bulk Binding',
            template=template,
            intent_profile=binding_profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )

        bulk_run = run_bulk_routing_intent_pipeline(
            organization=self.organization,
            profiles=(self.profile,),
            bindings=(binding,),
            create_change_plans=True,
        )

        bulk_summary = bulk_run.summary_json
        scope_results = {scope.scope_kind: scope for scope in bulk_run.scope_results.all()}
        profile_scope = scope_results['profile']
        binding_scope = scope_results['binding']

        self.assertEqual(bulk_run.target_mode, rpki_models.BulkIntentTargetMode.MIXED)
        self.assertTrue(
            {
                'comparison_scope',
                'provider_snapshot_id',
                'create_change_plans',
                'profile_target_count',
                'binding_target_count',
                'scope_result_count',
                'change_plan_count',
                'failed_scope_count',
                'completed_scope_keys',
            }.issubset(bulk_summary)
        )
        self.assertEqual(bulk_summary['comparison_scope'], rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS)
        self.assertEqual(bulk_summary['profile_target_count'], 1)
        self.assertEqual(bulk_summary['binding_target_count'], 1)
        self.assertEqual(bulk_summary['scope_result_count'], 2)
        self.assertEqual(bulk_summary['change_plan_count'], 2)
        self.assertEqual(bulk_summary['failed_scope_count'], 0)
        self.assertEqual(set(bulk_summary['completed_scope_keys']), {f'profile:{self.profile.pk}', f'binding:{binding.pk}'})

        self.assertTrue(
            {'comparison_scope', 'provider_snapshot_id', 'warning_count', 'reconciliation_status', 'change_plan_id'}.issubset(
                profile_scope.summary_json
            )
        )
        self.assertNotIn('binding_fingerprint', profile_scope.summary_json)
        self.assertIsNotNone(profile_scope.summary_json['change_plan_id'])

        self.assertTrue(
            {
                'comparison_scope',
                'provider_snapshot_id',
                'warning_count',
                'reconciliation_status',
                'change_plan_id',
                'binding_fingerprint',
            }.issubset(binding_scope.summary_json)
        )
        self.assertEqual(binding_scope.summary_json['binding_fingerprint'], binding.last_compiled_fingerprint)
        self.assertIsNotNone(binding_scope.summary_json['change_plan_id'])

    def test_bulk_pipeline_persists_failed_summary_contract_before_reraising(self):
        profile = create_test_routing_intent_profile(
            name='Failed Bulk Binding Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
            asn_selector_query='id=999999999',
        )
        template = create_test_routing_intent_template(
            name='Failed Bulk Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.DRAFT,
        )
        create_test_routing_intent_template_rule(
            name='Failed Bulk Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Failed Bulk Binding',
            template=template,
            intent_profile=profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )

        with self.assertRaisesMessage(RoutingIntentExecutionError, 'must be active before regeneration'):
            run_bulk_routing_intent_pipeline(
                organization=self.organization,
                bindings=(binding,),
                run_name='Failed Bulk Contract Run',
            )

        bulk_run = rpki_models.BulkIntentRun.objects.get(name='Failed Bulk Contract Run')
        bulk_summary = bulk_run.summary_json

        self.assertEqual(bulk_run.status, rpki_models.ValidationRunStatus.FAILED)
        self.assertTrue(
            {
                'comparison_scope',
                'provider_snapshot_id',
                'create_change_plans',
                'profile_target_count',
                'binding_target_count',
                'scope_result_count',
                'change_plan_count',
                'failed_scope_count',
                'error',
            }.issubset(bulk_summary)
        )
        self.assertEqual(bulk_summary['profile_target_count'], 0)
        self.assertEqual(bulk_summary['binding_target_count'], 1)
        self.assertEqual(bulk_summary['scope_result_count'], 0)
        self.assertEqual(bulk_summary['change_plan_count'], 0)
        self.assertEqual(bulk_summary['failed_scope_count'], 1)
        self.assertIn('must be active before regeneration', bulk_summary['error'])

    def test_compiled_policy_accepts_explicit_binding_subset(self):
        profile = create_test_routing_intent_profile(
            name='Compiled Binding Subset Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
            asn_selector_query='id=999999999',
        )
        template = create_test_routing_intent_template(
            name='Subset Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.DRAFT,
            enabled=False,
        )
        binding = create_test_routing_intent_template_binding(
            name='Subset Binding',
            template=template,
            intent_profile=profile,
            origin_asn_override=self.origin_asn,
        )

        compiled_policy = compile_routing_intent_policy(
            profile,
            bindings=(binding,),
            include_inactive_bindings=True,
            persist_state=False,
        )

        self.assertEqual(len(compiled_policy.template_bindings), 1)
        self.assertEqual(compiled_policy.template_bindings[0].binding.pk, binding.pk)

    def test_bulk_pipeline_runs_across_profiles_and_creates_scope_results(self):
        second_prefix = create_test_prefix('10.57.0.0/24', tenant=self.tenant, status='active')
        second_profile = create_test_routing_intent_profile(
            name='Bulk Profile Two',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={second_prefix.pk}',
            asn_selector_query=f'id={self.origin_asn.pk}',
        )

        bulk_run = run_bulk_routing_intent_pipeline(
            organization=self.organization,
            profiles=(self.profile, second_profile),
        )

        self.assertEqual(bulk_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(bulk_run.target_mode, rpki_models.BulkIntentTargetMode.PROFILES)
        self.assertEqual(bulk_run.scope_results.count(), 2)
        self.assertEqual(bulk_run.summary_json['scope_result_count'], 2)
        self.assertTrue(bulk_run.resulting_fingerprint)
        self.assertEqual(
            set(bulk_run.scope_results.values_list('scope_key', flat=True)),
            {f'profile:{self.profile.pk}', f'profile:{second_profile.pk}'},
        )

    def test_bulk_pipeline_runs_across_bindings_and_can_create_change_plans(self):
        profile = create_test_routing_intent_profile(
            name='Bulk Binding Profile',
            organization=self.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
            asn_selector_query='id=999999999',
        )
        template = create_test_routing_intent_template(
            name='Bulk Binding Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Bulk Binding Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Bulk Binding',
            template=template,
            intent_profile=profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )

        bulk_run = run_bulk_routing_intent_pipeline(
            bindings=(binding,),
            create_change_plans=True,
        )

        scope_result = bulk_run.scope_results.get()
        self.assertEqual(bulk_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(bulk_run.target_mode, rpki_models.BulkIntentTargetMode.BINDINGS)
        self.assertEqual(scope_result.template_binding, binding)
        self.assertIsNotNone(scope_result.change_plan)
        self.assertEqual(bulk_run.summary_json['change_plan_count'], 1)
        self.assertEqual(scope_result.scope_key, f'binding:{binding.pk}')

    def test_bulk_pipeline_rejects_cross_organization_targets(self):
        other_org = create_test_organization(org_id='bulk-other-org', name='Bulk Other Org')
        other_profile = create_test_routing_intent_profile(
            name='Cross Org Profile',
            organization=other_org,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        )

        with self.assertRaisesMessage(ValueError, 'same organization'):
            run_bulk_routing_intent_pipeline(
                profiles=(self.profile, other_profile),
            )

    def test_reconciliation_flags_overbroad_roa(self):
        derivation_run = derive_roa_intents(self.profile)
        certificate = create_test_certificate(name='Intent Cert', rpki_org=self.organization)
        roa = create_test_roa(name='Published ROA', signed_by=certificate, origin_as=self.origin_asn)
        create_test_roa_prefix(prefix=self.primary_prefix, roa=roa, max_length=26)

        reconciliation_run = reconcile_roa_intents(derivation_run)
        intent_result = reconciliation_run.intent_results.get(roa_intent__prefix=self.primary_prefix)
        published_result = reconciliation_run.published_roa_results.get(roa_object=roa)
        best_match = derivation_run.roa_intents.get(prefix=self.primary_prefix).candidate_matches.get(is_best_match=True)

        self.assertEqual(best_match.match_kind, rpki_models.ROAIntentMatchKind.LENGTH_BROADER)
        self.assertEqual(intent_result.result_type, rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD)
        self.assertEqual(published_result.result_type, rpki_models.PublishedROAResultType.BROADER_THAN_NEEDED)
        lint_run = reconciliation_run.lint_runs.get()
        finding_codes = list(lint_run.findings.values_list('finding_code', flat=True))
        self.assertIn('intent_max_length_overbroad', finding_codes)
        self.assertIn('published_broader_than_needed', finding_codes)
        self.assertEqual(finding_codes.count('replacement_required'), 2)
        self.assertIn('intent_suppressed', finding_codes)
        self.assertEqual(
            lint_run.summary_json['rule_family_counts'],
            {
                'intent_safety': 2,
                'published_hygiene': 1,
                'plan_risk': 2,
            },
        )
        self.assertEqual(lint_run.summary_json['approval_impact_counts']['blocking'], 0)
        self.assertEqual(lint_run.summary_json['informational_finding_count'], 5)

    def test_reconciliation_supports_provider_imported_scope(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_snapshot = create_test_provider_snapshot(
            name='Provider Snapshot',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        imported_authorization = create_test_imported_roa_authorization(
            name='Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=self.origin_asn,
            max_length=24,
        )

        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )

        intent_result = reconciliation_run.intent_results.get(roa_intent__prefix=self.primary_prefix)
        published_result = reconciliation_run.published_roa_results.get(imported_authorization=imported_authorization)
        best_match = derivation_run.roa_intents.get(prefix=self.primary_prefix).candidate_matches.get(is_best_match=True)

        self.assertEqual(reconciliation_run.provider_snapshot, provider_snapshot)
        self.assertEqual(intent_result.result_type, rpki_models.ROAIntentResultType.MATCH)
        self.assertEqual(intent_result.best_imported_authorization, imported_authorization)
        self.assertEqual(best_match.imported_authorization, imported_authorization)
        self.assertEqual(published_result.result_type, rpki_models.PublishedROAResultType.MATCHED)

    def test_reconciliation_records_matching_external_management_exception_without_hiding_result(self):
        derivation_run = derive_roa_intents(self.profile)
        create_test_external_management_exception(
            name='Primary Prefix Managed Elsewhere',
            organization=self.organization,
            scope_type=rpki_models.ExternalManagementScope.ROA_PREFIX,
            prefix=self.primary_prefix,
            origin_asn=self.origin_asn,
            max_length=24,
            owner='adoption-owner',
            reason='Still managed through the legacy provider workflow.',
            starts_at=timezone.now() - timedelta(days=2),
            review_at=timezone.now() + timedelta(days=7),
        )

        reconciliation_run = reconcile_roa_intents(derivation_run)
        intent_result = reconciliation_run.intent_results.get(roa_intent__prefix=self.primary_prefix)

        self.assertEqual(intent_result.result_type, rpki_models.ROAIntentResultType.MISSING)
        self.assertEqual(
            intent_result.details_json['external_management_exception']['owner'],
            'adoption-owner',
        )
        self.assertEqual(reconciliation_run.result_summary_json['external_management_matched_intent_count'], 1)

    def test_reconciliation_marks_same_prefix_provider_mismatch_as_replacement(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_snapshot = create_test_provider_snapshot(
            name='Replacement Snapshot',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        replacement_import = create_test_imported_roa_authorization(
            name='Replacement Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65561),
            max_length=26,
            payload_json={'comment': 'replace me'},
        )

        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )

        intent_result = reconciliation_run.intent_results.get(roa_intent__prefix=self.primary_prefix)
        published_result = reconciliation_run.published_roa_results.get(imported_authorization=replacement_import)

        self.assertEqual(intent_result.result_type, rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_OVERBROAD)
        self.assertEqual(intent_result.best_imported_authorization, replacement_import)
        self.assertTrue(intent_result.details_json['replacement_required'])
        self.assertEqual(intent_result.details_json['replacement_reason_code'], 'origin_and_max_length_overbroad')
        self.assertEqual(intent_result.details_json['mismatch_axes'], ['origin_asn', 'max_length'])

        self.assertEqual(
            published_result.result_type,
            rpki_models.PublishedROAResultType.WRONG_ORIGIN_AND_MAX_LENGTH_OVERBROAD,
        )
        self.assertTrue(published_result.details_json['replacement_required'])
        self.assertEqual(published_result.details_json['replacement_reason_code'], 'origin_and_max_length_overbroad')
        self.assertEqual(reconciliation_run.result_summary_json['replacement_required_intent_count'], 1)
        self.assertEqual(reconciliation_run.result_summary_json['replacement_required_published_count'], 1)
        self.assertTrue(reconciliation_run.lint_runs.exists())
        self.assertIn('lint_run_id', reconciliation_run.result_summary_json)
        lint_run = reconciliation_run.lint_runs.get()
        finding_codes = list(lint_run.findings.values_list('finding_code', flat=True))
        self.assertIn('intent_inconsistent_with_published', finding_codes)
        self.assertIn('intent_max_length_overbroad', finding_codes)
        self.assertIn('published_inconsistent_with_intent', finding_codes)
        self.assertIn('replacement_required', finding_codes)
        self.assertIn('intent_suppressed', finding_codes)
        self.assertEqual(finding_codes.count('replacement_required'), 2)
        self.assertEqual(lint_run.summary_json['rule_family_counts']['intent_safety'], 3)
        self.assertEqual(lint_run.summary_json['rule_family_counts']['published_hygiene'], 1)
        self.assertEqual(lint_run.summary_json['rule_family_counts']['plan_risk'], 2)
        self.assertEqual(lint_run.summary_json['blocking_finding_count'], 2)

    def test_direct_plan_lint_flags_broadening_and_uncovered_withdraw(self):
        derivation_run = derive_roa_intents(self.profile)
        reconciliation_run = reconcile_roa_intents(derivation_run)
        plan = create_test_roa_change_plan(
            organization=self.organization,
            source_reconciliation_run=reconciliation_run,
        )

        create_test_roa_change_plan_item(
            name='Broadening Create',
            change_plan=plan,
            action_type=rpki_models.ROAChangePlanAction.CREATE,
            plan_semantic=rpki_models.ROAChangePlanItemSemantic.CREATE,
            after_state_json={
                'prefix_cidr_text': '10.55.0.0/24',
                'origin_asn_value': self.origin_asn.asn,
                'max_length': 26,
            },
        )
        create_test_roa_change_plan_item(
            name='Standalone Withdraw',
            change_plan=plan,
            action_type=rpki_models.ROAChangePlanAction.WITHDRAW,
            plan_semantic=rpki_models.ROAChangePlanItemSemantic.WITHDRAW,
            before_state_json={
                'prefix_cidr_text': '10.56.0.0/24',
                'origin_asn_value': self.origin_asn.asn,
                'max_length': 24,
            },
        )

        lint_run = run_roa_lint(reconciliation_run, change_plan=plan)

        finding_codes = list(lint_run.findings.values_list('finding_code', flat=True))
        self.assertIn('plan_broadens_authorization', finding_codes)
        self.assertIn('plan_withdraw_without_replacement', finding_codes)
        self.assertIn('intent_suppressed', finding_codes)
        self.assertEqual(lint_run.summary_json['summary_schema_version'], 3)
        self.assertEqual(
            lint_run.summary_json['rule_family_counts'],
            {'intent_safety': 1, 'plan_risk': 2},
        )
        self.assertEqual(
            lint_run.summary_json['approval_impact_counts'],
            {'informational': 1, 'acknowledgement_required': 2, 'blocking': 0},
        )

    def test_lint_finding_exposes_operator_explanation_contract(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_snapshot = create_test_provider_snapshot(
            name='Explanation Snapshot',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        replacement_import = create_test_imported_roa_authorization(
            name='Explanation Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65571),
            max_length=26,
        )

        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        lint_run = reconciliation_run.lint_runs.get()
        finding = lint_run.findings.get(
            finding_code='published_inconsistent_with_intent',
            published_roa_result__imported_authorization=replacement_import,
        )

        self.assertEqual(finding.details_json['rule_label'], 'Published ROA inconsistent with intent')
        self.assertEqual(finding.details_json['approval_impact'], 'blocking')
        self.assertIn('disagrees with current intent', finding.details_json['operator_message'])
        self.assertIn('publishing state', finding.details_json['why_it_matters'].lower())
        self.assertIn('replace the published authorization', finding.details_json['operator_action'].lower())
        self.assertEqual(finding.details_json['source_kind'], 'published_roa_result')
        self.assertEqual(finding.details_json['source_name'], finding.published_roa_result.name)

        serializer = SERIALIZER_CLASS_MAP['roalintfinding'](finding, context={'request': None})
        self.assertEqual(
            serializer.data['details_json']['rule_label'],
            'Published ROA inconsistent with intent',
        )
        self.assertEqual(serializer.data['details_json']['approval_impact'], 'blocking')

    def test_suppression_marks_rerun_findings_and_lift_reopens_them(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_snapshot = create_test_provider_snapshot(
            name='Suppression Snapshot',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        replacement_import = create_test_imported_roa_authorization(
            name='Suppression Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65572),
            max_length=26,
        )

        initial_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        initial_finding = initial_run.lint_runs.get().findings.get(
            finding_code='published_inconsistent_with_intent',
            published_roa_result__imported_authorization=replacement_import,
        )
        suppression = suppress_roa_lint_finding(
            initial_finding,
            scope_type=rpki_models.ROALintSuppressionScope.PROFILE,
            reason='Known operator exception.',
            created_by='lint-user',
        )

        suppressed_run = reconcile_roa_intents(
            derive_roa_intents(self.profile),
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        suppressed_finding = suppressed_run.lint_runs.order_by('-started_at', '-created').first().findings.get(
            finding_code='published_inconsistent_with_intent',
            published_roa_result__imported_authorization=replacement_import,
        )
        self.assertTrue(suppressed_finding.details_json['suppressed'])
        self.assertEqual(suppressed_finding.details_json['suppression_id'], suppression.pk)
        self.assertGreaterEqual(suppressed_run.lint_runs.order_by('-started_at', '-created').first().summary_json['suppressed_finding_count'], 1)

        lift_roa_lint_suppression(suppression, lifted_by='lint-user', lift_reason='Issue changed.')

        reopened_run = reconcile_roa_intents(
            derive_roa_intents(self.profile),
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        reopened_finding = reopened_run.lint_runs.order_by('-started_at', '-created').first().findings.get(
            finding_code='published_inconsistent_with_intent',
            published_roa_result__imported_authorization=replacement_import,
        )
        self.assertFalse(reopened_finding.details_json['suppressed'])

    def test_suppression_reopens_when_finding_facts_change(self):
        derivation_run = derive_roa_intents(self.profile)
        initial_snapshot = create_test_provider_snapshot(
            name='Suppression Fingerprint Snapshot One',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_imported_roa_authorization(
            name='Suppression Fingerprint Imported Authorization One',
            provider_snapshot=initial_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65573),
            max_length=26,
        )

        initial_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=initial_snapshot,
        )
        initial_finding = initial_run.lint_runs.get().findings.get(
            finding_code='published_inconsistent_with_intent',
        )
        suppress_roa_lint_finding(
            initial_finding,
            scope_type=rpki_models.ROALintSuppressionScope.PROFILE,
            reason='Known operator exception.',
            created_by='lint-user',
        )

        changed_snapshot = create_test_provider_snapshot(
            name='Suppression Fingerprint Snapshot Two',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        changed_import = create_test_imported_roa_authorization(
            name='Suppression Fingerprint Imported Authorization Two',
            provider_snapshot=changed_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65574),
            max_length=25,
        )

        changed_run = reconcile_roa_intents(
            derive_roa_intents(self.profile),
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=changed_snapshot,
        )
        changed_finding = changed_run.lint_runs.order_by('-started_at', '-created').first().findings.get(
            finding_code='published_inconsistent_with_intent',
            published_roa_result__imported_authorization=changed_import,
        )

        self.assertFalse(changed_finding.details_json['suppressed'])

    def test_change_plan_creates_create_and_withdraw_actions(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_account = create_test_provider_account(
            name='Plan Provider Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-PLAN',
            ca_handle='ca-plan',
            api_base_url='https://krill.example.invalid',
        )
        provider_snapshot = create_test_provider_snapshot(
            name='Plan Snapshot',
            organization=self.organization,
            provider_account=provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        orphaned_prefix = create_test_prefix('10.99.0.0/24')
        orphaned_asn = create_test_asn(65599)
        create_test_imported_roa_authorization(
            name='Orphaned Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=orphaned_prefix,
            origin_asn=orphaned_asn,
            max_length=24,
        )

        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        plan = create_roa_change_plan(reconciliation_run)

        self.assertEqual(plan.items.filter(action_type=rpki_models.ROAChangePlanAction.CREATE).count(), 1)
        self.assertEqual(plan.items.filter(action_type=rpki_models.ROAChangePlanAction.WITHDRAW).count(), 1)
        self.assertEqual(plan.summary_json['create_count'], 1)
        self.assertEqual(plan.summary_json['withdraw_count'], 1)

    def test_change_plan_creates_replacement_items_for_local_mismatch(self):
        derivation_run = derive_roa_intents(self.profile)
        certificate = create_test_certificate(name='Replacement Local Cert', rpki_org=self.organization)
        replacement_roa = create_test_roa(
            name='Replacement Local ROA',
            signed_by=certificate,
            origin_as=create_test_asn(65562),
        )
        create_test_roa_prefix(prefix=self.primary_prefix, roa=replacement_roa, max_length=26)

        reconciliation_run = reconcile_roa_intents(derivation_run)
        plan = create_roa_change_plan(reconciliation_run)

        create_item = plan.items.get(action_type=rpki_models.ROAChangePlanAction.CREATE)
        withdraw_item = plan.items.get(action_type=rpki_models.ROAChangePlanAction.WITHDRAW)

        self.assertEqual(plan.summary_json['replacement_count'], 1)
        self.assertEqual(plan.summary_json['replacement_create_count'], 1)
        self.assertEqual(plan.summary_json['replacement_withdraw_count'], 1)
        self.assertEqual(
            plan.summary_json['replacement_reason_counts'],
            {'origin_and_max_length_overbroad': 1},
        )
        self.assertIn('wrong origin ASN and an overbroad maxLength', create_item.reason)
        self.assertEqual(withdraw_item.roa, replacement_roa)
        self.assertEqual(withdraw_item.provider_operation, '')
        self.assertEqual(withdraw_item.before_state_json['source'], 'local_roa')
        self.assertEqual(withdraw_item.after_state_json['prefix_cidr_text'], '10.55.0.0/24')

    def test_change_plan_creates_replacement_items_for_provider_mismatch(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_account = create_test_provider_account(
            name='Replacement Provider Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-PLAN-REPLACE',
            ca_handle='ca-plan-replace',
            api_base_url='https://krill.example.invalid',
        )
        provider_snapshot = create_test_provider_snapshot(
            name='Replacement Provider Snapshot',
            organization=self.organization,
            provider_account=provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        replacement_import = create_test_imported_roa_authorization(
            name='Replacement Imported Authorization 2',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65563),
            max_length=26,
            payload_json={'comment': 'replacement target'},
        )

        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        plan = create_roa_change_plan(reconciliation_run)

        create_item = plan.items.get(action_type=rpki_models.ROAChangePlanAction.CREATE)
        withdraw_item = plan.items.get(action_type=rpki_models.ROAChangePlanAction.WITHDRAW)

        self.assertEqual(plan.summary_json['create_count'], 1)
        self.assertEqual(plan.summary_json['withdraw_count'], 1)
        self.assertEqual(plan.summary_json['replacement_count'], 1)
        self.assertEqual(create_item.provider_operation, rpki_models.ProviderWriteOperation.ADD_ROUTE)
        self.assertEqual(
            create_item.provider_payload_json,
            {'asn': self.origin_asn.asn, 'prefix': '10.55.0.0/24', 'max_length': 24},
        )
        self.assertEqual(withdraw_item.imported_authorization, replacement_import)
        self.assertEqual(withdraw_item.provider_operation, rpki_models.ProviderWriteOperation.REMOVE_ROUTE)
        self.assertEqual(
            withdraw_item.provider_payload_json,
            {
                'asn': replacement_import.origin_asn_value,
                'prefix': '10.55.0.0/24',
                'max_length': 26,
                'comment': 'replacement target',
            },
        )
        self.assertEqual(withdraw_item.before_state_json['replacement_reason_code'], 'origin_and_max_length_overbroad')

    def test_change_plan_creation_runs_lint_and_simulation_analysis(self):
        derivation_run = derive_roa_intents(self.profile)
        certificate = create_test_certificate(name='Analysis Local Cert', rpki_org=self.organization)
        replacement_roa = create_test_roa(
            name='Analysis Local ROA',
            signed_by=certificate,
            origin_as=create_test_asn(65564),
        )
        create_test_roa_prefix(prefix=self.primary_prefix, roa=replacement_roa, max_length=26)

        reconciliation_run = reconcile_roa_intents(derivation_run)
        plan = create_roa_change_plan(reconciliation_run)

        self.assertTrue(reconciliation_run.lint_runs.exists())
        self.assertTrue(plan.lint_runs.exists())
        self.assertTrue(plan.simulation_runs.exists())
        self.assertIn('lint_run_id', reconciliation_run.result_summary_json)
        self.assertIn('lint_run_id', plan.summary_json)
        self.assertIn('simulation_run_id', plan.summary_json)
        self.assertIn('simulation_plan_fingerprint', plan.summary_json)
        self.assertIn('latest_simulation_summary', plan.summary_json)

        lint_run = plan.lint_runs.get()
        simulation_run = plan.simulation_runs.get()
        self.assertGreater(lint_run.finding_count, 0)
        self.assertEqual(simulation_run.result_count, plan.items.count())
        self.assertGreaterEqual(simulation_run.predicted_valid_count, 1)
        self.assertIn('approval_impact_counts', simulation_run.summary_json)
        self.assertIn('scenario_type_counts', simulation_run.summary_json)
        self.assertEqual(
            simulation_run.summary_json['plan_fingerprint'],
            plan.summary_json['simulation_plan_fingerprint'],
        )
        self.assertEqual(plan.summary_json['latest_simulation_summary'], simulation_run.summary_json)
        self.assertEqual(simulation_run.plan_fingerprint, simulation_run.summary_json['plan_fingerprint'])
        self.assertEqual(
            simulation_run.overall_approval_posture,
            simulation_run.summary_json['overall_approval_posture'],
        )
        self.assertEqual(simulation_run.is_current_for_plan, simulation_run.summary_json['is_current_for_plan'])
        self.assertEqual(
            simulation_run.partially_constrained,
            simulation_run.summary_json['partially_constrained'],
        )
        self.assertIn(
            simulation_run.summary_json['overall_approval_posture'],
            {'informational', 'acknowledgement_required', 'blocking'},
        )
        result = simulation_run.results.order_by('pk').first()
        self.assertIn('scenario_type', result.details_json)
        self.assertIn('approval_impact', result.details_json)
        self.assertIn('operator_message', result.details_json)
        self.assertIn('before_coverage', result.details_json)
        self.assertIn('after_coverage', result.details_json)
        self.assertEqual(result.scenario_type, result.details_json['scenario_type'])
        self.assertEqual(result.approval_impact, result.details_json['approval_impact'])
        self.assertEqual(
            result.details_json['plan_fingerprint'],
            simulation_run.summary_json['plan_fingerprint'],
        )

    def test_simulation_marks_incomplete_create_state_as_acknowledgement_required(self):
        plan = create_test_roa_change_plan(
            name='Incomplete Simulation Plan',
            organization=self.organization,
        )
        create_test_roa_change_plan_item(
            name='Incomplete Simulation Item',
            change_plan=plan,
            action_type=rpki_models.ROAChangePlanAction.CREATE,
            plan_semantic=rpki_models.ROAChangePlanItemSemantic.CREATE,
            after_state_json={'prefix_cidr_text': str(self.primary_prefix.prefix)},
        )

        simulation_run = simulate_roa_change_plan(plan)
        result = simulation_run.results.get()

        self.assertEqual(result.outcome_type, rpki_models.ROAValidationSimulationOutcome.INVALID)
        self.assertEqual(result.details_json['scenario_type'], 'insufficient_state_requires_review')
        self.assertEqual(result.details_json['approval_impact'], 'acknowledgement_required')
        self.assertTrue(simulation_run.summary_json['partially_constrained'])

    def test_simulation_marks_withdraw_without_replacement_as_blocking(self):
        derivation_run = derive_roa_intents(self.profile)
        plan = create_test_roa_change_plan(
            name='Blocking Simulation Plan',
            organization=self.organization,
        )
        intent = create_test_roa_intent(
            name='Blocking Simulation Intent',
            organization=self.organization,
            derivation_run=derivation_run,
            intent_profile=self.profile,
            prefix=self.primary_prefix,
            prefix_cidr_text=str(self.primary_prefix.prefix),
            origin_asn=self.origin_asn,
            origin_asn_value=self.origin_asn.asn,
            max_length=24,
        )
        create_test_roa_change_plan_item(
            name='Blocking Withdraw Item',
            change_plan=plan,
            action_type=rpki_models.ROAChangePlanAction.WITHDRAW,
            plan_semantic=rpki_models.ROAChangePlanItemSemantic.WITHDRAW,
            roa_intent=intent,
            before_state_json={
                'prefix_cidr_text': str(self.primary_prefix.prefix),
                'origin_asn_value': self.origin_asn.asn,
                'max_length_value': 24,
            },
            after_state_json={},
        )

        simulation_run = simulate_roa_change_plan(plan)
        result = simulation_run.results.get()

        self.assertEqual(result.outcome_type, rpki_models.ROAValidationSimulationOutcome.NOT_FOUND)
        self.assertEqual(result.details_json['approval_impact'], 'blocking')
        self.assertEqual(simulation_run.summary_json['overall_approval_posture'], 'blocking')

    def test_change_plan_items_record_plan_semantics(self):
        scenario = create_test_roa_change_plan_matrix()

        local_semantics = list(
            scenario.local_plan.items.order_by('name').values_list('plan_semantic', flat=True)
        )
        provider_semantics = list(
            scenario.provider_plan.items.order_by('name').values_list('plan_semantic', flat=True)
        )

        self.assertEqual(local_semantics.count(rpki_models.ROAChangePlanItemSemantic.CREATE), 1)
        self.assertEqual(local_semantics.count(rpki_models.ROAChangePlanItemSemantic.WITHDRAW), 1)
        self.assertEqual(local_semantics.count(rpki_models.ROAChangePlanItemSemantic.REPLACE), 2)
        self.assertEqual(provider_semantics.count(rpki_models.ROAChangePlanItemSemantic.CREATE), 1)
        self.assertEqual(provider_semantics.count(rpki_models.ROAChangePlanItemSemantic.WITHDRAW), 1)
        self.assertEqual(provider_semantics.count(rpki_models.ROAChangePlanItemSemantic.REPLACE), 2)
        self.assertEqual(
            scenario.provider_plan.summary_json['plan_semantic_counts'],
            {
                rpki_models.ROAChangePlanItemSemantic.CREATE: 1,
                rpki_models.ROAChangePlanItemSemantic.REPLACE: 2,
                rpki_models.ROAChangePlanItemSemantic.WITHDRAW: 1,
            },
        )

    def test_reconciliation_summary_stays_consistent_across_local_and_provider_scopes(self):
        scenario = create_test_roa_change_plan_matrix()

        local_summary = scenario.local_reconciliation_run.result_summary_json
        provider_summary = scenario.provider_reconciliation_run.result_summary_json

        self.assertEqual(local_summary['comparison_scope'], rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS)
        self.assertEqual(provider_summary['comparison_scope'], rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED)
        self.assertIsNone(local_summary['provider_snapshot_id'])
        self.assertEqual(provider_summary['provider_snapshot_id'], scenario.provider_snapshot.pk)

        self.assertEqual(local_summary['intent_result_types'], provider_summary['intent_result_types'])
        self.assertEqual(local_summary['published_result_types'], provider_summary['published_result_types'])
        self.assertEqual(local_summary['best_match_kinds'], provider_summary['best_match_kinds'])
        self.assertEqual(local_summary['replacement_required_intent_count'], 1)
        self.assertEqual(local_summary['replacement_required_published_count'], 1)
        self.assertEqual(provider_summary['replacement_required_intent_count'], 1)
        self.assertEqual(provider_summary['replacement_required_published_count'], 1)

    def test_mixed_change_plan_counts_cover_create_withdraw_and_replacement_combinations(self):
        scenario = create_test_roa_change_plan_matrix()

        local_plan = scenario.local_plan
        provider_plan = scenario.provider_plan

        self.assertEqual(local_plan.summary_json['create_count'], 2)
        self.assertEqual(local_plan.summary_json['withdraw_count'], 2)
        self.assertEqual(local_plan.summary_json['replacement_count'], 1)
        self.assertEqual(local_plan.summary_json['replacement_create_count'], 1)
        self.assertEqual(local_plan.summary_json['replacement_withdraw_count'], 1)
        self.assertEqual(local_plan.summary_json['replacement_reason_counts'], {'origin_and_max_length_overbroad': 1})
        self.assertEqual(local_plan.items.filter(action_type=rpki_models.ROAChangePlanAction.CREATE).count(), 2)
        self.assertEqual(local_plan.items.filter(action_type=rpki_models.ROAChangePlanAction.WITHDRAW).count(), 2)

        self.assertEqual(provider_plan.summary_json['create_count'], 2)
        self.assertEqual(provider_plan.summary_json['withdraw_count'], 2)
        self.assertEqual(provider_plan.summary_json['replacement_count'], 1)
        self.assertEqual(provider_plan.summary_json['replacement_create_count'], 1)
        self.assertEqual(provider_plan.summary_json['replacement_withdraw_count'], 1)
        self.assertEqual(provider_plan.summary_json['replacement_reason_counts'], {'origin_and_max_length_overbroad': 1})
        self.assertTrue(provider_plan.summary_json['provider_backed'])
        self.assertEqual(provider_plan.summary_json['provider_account_id'], scenario.provider_account.pk)
        self.assertEqual(provider_plan.summary_json['provider_snapshot_id'], scenario.provider_snapshot.pk)
        self.assertEqual(provider_plan.items.filter(action_type=rpki_models.ROAChangePlanAction.CREATE).count(), 2)
        self.assertEqual(provider_plan.items.filter(action_type=rpki_models.ROAChangePlanAction.WITHDRAW).count(), 2)

    def test_management_command_runs_pipeline_synchronously(self):
        call_command('run_routing_intent_profile', '--profile', str(self.profile.pk))
        self.assertTrue(rpki_models.IntentDerivationRun.objects.filter(intent_profile=self.profile).exists())
        self.assertTrue(rpki_models.ROAReconciliationRun.objects.filter(intent_profile=self.profile).exists())

    def test_management_command_supports_provider_imported_scope(self):
        provider_snapshot = create_test_provider_snapshot(
            name='Command Snapshot',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_imported_roa_authorization(
            name='Command Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=self.origin_asn,
            max_length=24,
        )

        call_command(
            'run_routing_intent_profile',
            '--profile',
            str(self.profile.pk),
            '--comparison-scope',
            rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            '--provider-snapshot',
            str(provider_snapshot.pk),
        )
        self.assertTrue(
            rpki_models.ROAReconciliationRun.objects.filter(
                intent_profile=self.profile,
                provider_snapshot=provider_snapshot,
                comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            ).exists()
        )

    def test_bulk_management_command_runs_pipeline_synchronously(self):
        template = create_test_routing_intent_template(
            name='CLI Bulk Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='CLI Bulk Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='CLI Bulk Binding',
            template=template,
            intent_profile=self.profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )
        stdout = StringIO()

        call_command(
            'run_bulk_routing_intent',
            '--organization',
            str(self.organization.pk),
            '--profiles',
            str(self.profile.pk),
            '--bindings',
            str(binding.pk),
            '--create-change-plans',
            '--run-name',
            'CLI Bulk Run',
            stdout=stdout,
        )

        bulk_run = rpki_models.BulkIntentRun.objects.get(name='CLI Bulk Run')
        self.assertEqual(bulk_run.organization, self.organization)
        self.assertEqual(bulk_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(bulk_run.summary_json['scope_result_count'], 2)
        self.assertEqual(bulk_run.summary_json['change_plan_count'], 2)
        self.assertTrue(
            rpki_models.BulkIntentRunScopeResult.objects.filter(
                bulk_run=bulk_run,
                scope_key=f'profile:{self.profile.pk}',
            ).exists()
        )
        self.assertTrue(
            rpki_models.BulkIntentRunScopeResult.objects.filter(
                bulk_run=bulk_run,
                scope_key=f'binding:{binding.pk}',
            ).exists()
        )
        self.assertIn(f'Completed bulk intent run {bulk_run.pk}', stdout.getvalue())

    def test_bulk_management_command_supports_provider_imported_scope(self):
        template = create_test_routing_intent_template(
            name='Bulk Command Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Bulk Command Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Bulk Command Binding',
            template=template,
            intent_profile=self.profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )
        provider_snapshot = create_test_provider_snapshot(
            name='Bulk Command Snapshot',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_imported_roa_authorization(
            name='Bulk Command Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=self.origin_asn,
            max_length=24,
        )

        call_command(
            'run_bulk_routing_intent',
            '--organization',
            str(self.organization.pk),
            '--bindings',
            str(binding.pk),
            '--comparison-scope',
            rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            '--provider-snapshot',
            str(provider_snapshot.pk),
        )

        bulk_run = rpki_models.BulkIntentRun.objects.order_by('-pk').first()
        self.assertEqual(
            bulk_run.summary_json['provider_snapshot_id'],
            provider_snapshot.pk,
        )
        self.assertTrue(
            rpki_models.BulkIntentRunScopeResult.objects.filter(
                bulk_run=bulk_run,
                reconciliation_run__provider_snapshot=provider_snapshot,
                summary_json__provider_snapshot_id=provider_snapshot.pk,
            ).exists()
        )

    def test_bulk_management_command_can_enqueue_job(self):
        template = create_test_routing_intent_template(
            name='Queued CLI Bulk Template',
            organization=self.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Queued CLI Bulk Include',
            template=template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        binding = create_test_routing_intent_template_binding(
            name='Queued CLI Bulk Binding',
            template=template,
            intent_profile=self.profile,
            origin_asn_override=self.origin_asn,
            prefix_selector_query=f'id={self.primary_prefix.pk}',
        )
        stdout = StringIO()

        class StubJob:
            pk = 991

        with patch(
            'netbox_rpki.management.commands.run_bulk_routing_intent.RunBulkRoutingIntentJob.enqueue_for_organization',
            return_value=(StubJob(), True),
        ) as enqueue_mock:
            call_command(
                'run_bulk_routing_intent',
                '--organization',
                str(self.organization.pk),
                '--bindings',
                str(binding.pk),
                '--enqueue',
                '--run-name',
                'Queued CLI Bulk Run',
                stdout=stdout,
            )

        enqueue_mock.assert_called_once_with(
            organization=self.organization,
            profiles=(),
            bindings=(binding,),
            comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
            provider_snapshot=None,
            create_change_plans=False,
            run_name='Queued CLI Bulk Run',
        )
        self.assertIn('Enqueued job 991', stdout.getvalue())


class RoutingIntentProfileRunActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='intent-api-org', name='Intent API Org')
        cls.profile = create_test_routing_intent_profile(
            name='Intent API Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        )

    def test_run_action_enqueues_job(self):
        self.add_permissions(
            'netbox_rpki.view_routingintentprofile',
            'netbox_rpki.change_routingintentprofile',
        )
        url = reverse('plugins-api:netbox_rpki-api:routingintentprofile-run', kwargs={'pk': self.profile.pk})

        class StubJob:
            pk = 321
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/321/'

        with patch('netbox_rpki.api.views.RunRoutingIntentProfileJob.enqueue_for_profile', return_value=(StubJob(), True)) as enqueue_mock:
            response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['job']['id'], 321)
        self.assertFalse(response.data['reconciliation_in_progress'])
        enqueue_mock.assert_called_once_with(
            self.profile,
            user=self.user,
            comparison_scope='local_roa_records',
            provider_snapshot=None,
        )

    def test_run_action_passes_provider_snapshot_parameters(self):
        self.add_permissions(
            'netbox_rpki.view_routingintentprofile',
            'netbox_rpki.change_routingintentprofile',
        )
        provider_snapshot = create_test_provider_snapshot(
            name='API Snapshot',
            organization=self.organization,
        )
        url = reverse('plugins-api:netbox_rpki-api:routingintentprofile-run', kwargs={'pk': self.profile.pk})

        class StubJob:
            pk = 654
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/654/'

        with patch('netbox_rpki.api.views.RunRoutingIntentProfileJob.enqueue_for_profile', return_value=(StubJob(), True)) as enqueue_mock:
            response = self.client.post(
                url,
                {
                    'comparison_scope': rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
                    'provider_snapshot': provider_snapshot.pk,
                },
                format='json',
                **self.header,
            )

        self.assertHttpStatus(response, 200)
        enqueue_mock.assert_called_once_with(
            self.profile,
            user=self.user,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )


class ROAReconciliationRunCreatePlanAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='intent-plan-api-org', name='Intent Plan API Org')
        cls.profile = create_test_routing_intent_profile(
            name='Intent Plan Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        )
        cls.derivation_run = derive_roa_intents(cls.profile)
        cls.reconciliation_run = reconcile_roa_intents(cls.derivation_run)

    def test_create_plan_action_creates_plan(self):
        self.add_permissions(
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.change_routingintentprofile',
        )
        url = reverse('plugins-api:netbox_rpki-api:roareconciliationrun-create-plan', kwargs={'pk': self.reconciliation_run.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertTrue(rpki_models.ROAChangePlan.objects.filter(source_reconciliation_run=self.reconciliation_run).exists())
        self.assertIn('item_count', response.data)

    def test_summary_action_returns_aggregate_counts(self):
        self.add_permissions('netbox_rpki.view_roareconciliationrun')
        url = reverse('plugins-api:netbox_rpki-api:roareconciliationrun-summary')

        response = self.client.get(url, **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('total_runs', response.data)
        self.assertIn('replacement_required_intent_total', response.data)
        self.assertIn('lint_warning_total', response.data)
