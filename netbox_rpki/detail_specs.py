from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils import timezone

from netbox_rpki import models
from netbox_rpki.services import build_roa_change_plan_lint_posture
from netbox_rpki.services.overlay_correlation import (
    build_aspa_overlay_summary,
    build_imported_certificate_observation_overlay_summary,
    build_imported_signed_object_overlay_summary,
    build_roa_overlay_summary,
    build_signed_object_overlay_summary,
)
from netbox_rpki.services.overlay_reporting import (
    build_aspa_change_plan_overlay_summary,
    build_aspa_reconciliation_overlay_summary,
    build_roa_change_plan_overlay_summary,
    build_roa_reconciliation_overlay_summary,
)
from netbox_rpki.services.publication_state import (
    derive_change_plan_publication_state,
    derive_rollback_bundle_publication_state,
)
from netbox_rpki.services.governance_summary import (
    build_change_plan_governance_summary,
    build_rollback_bundle_governance_summary,
)
from netbox_rpki.services.governance_rollup import build_organization_governance_rollup
from netbox_rpki.services.delegated_workflow import (
    build_authored_ca_relationship_delegated_summary,
    build_delegated_authorization_entity_summary,
    build_delegated_publication_workflow_summary,
    build_managed_authorization_relationship_summary,
    matching_authored_relationships_for_workflow,
    matching_workflows_for_authored_relationship,
)
from netbox_rpki.services.provider_sync_evidence import (
    get_certificate_observation_evidence_summary,
    get_certificate_observation_is_ambiguous,
    get_certificate_observation_publication_linkage_status,
    get_certificate_observation_signed_object_linkage_status,
    get_certificate_observation_source_count,
    get_certificate_observation_source_labels,
    get_publication_point_authored_linkage_status,
    get_publication_point_evidence_summary,
    get_signed_object_authored_linkage_status,
    get_signed_object_evidence_summary,
    get_signed_object_publication_linkage_status,
)


ValueGetter = Callable[[Any], Any]


def get_pk(instance: Any) -> Any:
    return instance.pk


def get_imported_publication_point_evidence_summary(obj: models.ImportedPublicationPoint) -> str | None:
    return get_pretty_json(get_publication_point_evidence_summary(obj))


def get_imported_signed_object_evidence_summary(obj: models.ImportedSignedObject) -> str | None:
    return get_pretty_json(get_signed_object_evidence_summary(obj))


def get_imported_certificate_observation_evidence_summary(obj: models.ImportedCertificateObservation) -> str | None:
    return get_pretty_json(get_certificate_observation_evidence_summary(obj))


def get_signed_object_external_overlay_summary(obj: models.SignedObject) -> str | None:
    return get_pretty_json(build_signed_object_overlay_summary(obj))


def get_roa_external_overlay_summary(obj: models.Roa) -> str | None:
    return get_pretty_json(build_roa_overlay_summary(obj))


def get_aspa_external_overlay_summary(obj: models.ASPA) -> str | None:
    return get_pretty_json(build_aspa_overlay_summary(obj))


def get_imported_signed_object_external_overlay_summary(obj: models.ImportedSignedObject) -> str | None:
    return get_pretty_json(build_imported_signed_object_overlay_summary(obj))


def get_imported_certificate_observation_external_overlay_summary(obj: models.ImportedCertificateObservation) -> str | None:
    return get_pretty_json(build_imported_certificate_observation_overlay_summary(obj))


@dataclass(frozen=True)
class DetailFieldSpec:
    label: str
    value: ValueGetter
    kind: str = 'text'
    url: ValueGetter | None = None
    use_header: bool = True
    empty_text: str | None = None


@dataclass(frozen=True)
class DetailActionSpec:
    permission: str
    label: str
    url_name: str | None = None
    query_param: str | None = None
    value: ValueGetter = get_pk
    direct_url: ValueGetter | None = None
    visible: ValueGetter | None = None


@dataclass(frozen=True)
class DetailTableSpec:
    title: str
    table_class_name: str
    queryset: ValueGetter


@dataclass(frozen=True)
class DetailSpec:
    model: type
    list_url_name: str
    breadcrumb_label: str
    card_title: str
    fields: tuple[DetailFieldSpec, ...]
    actions: tuple[DetailActionSpec, ...] = ()
    side_tables: tuple[DetailTableSpec, ...] = ()
    bottom_tables: tuple[DetailTableSpec, ...] = ()


ORGANIZATION_DETAIL_SPEC = DetailSpec(
    model=models.Organization,
    list_url_name='plugins:netbox_rpki:organization_list',
    breadcrumb_label='RPKI Customer Organizations',
    card_title='RPKI Organization',
    fields=(
        DetailFieldSpec(label='Organization ID', value=lambda obj: obj.org_id),
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(label='Organizaton Name', value=lambda obj: obj.name),
        DetailFieldSpec(
            label='Parent Regional Internet Registry',
            value=lambda obj: obj.parent_rir,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='External URL',
            value=lambda obj: obj.ext_url,
            kind='url',
        ),
        DetailFieldSpec(
            label='Governance Roll-up',
            value=lambda obj: get_pretty_json(build_organization_governance_rollup(obj)),
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_organization',
            label='RPKI Certificate',
            url_name='plugins:netbox_rpki:certificate_add',
            query_param='rpki_org',
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_organization',
            label='Run ASPA Reconciliation',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:organization_run_aspa_reconciliation', kwargs={'pk': obj.pk}),
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_organization',
            label='Create Bulk Intent Run',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:organization_create_bulk_intent_run', kwargs={'pk': obj.pk}),
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Certificates',
            table_class_name='CertificateTable',
            queryset=lambda obj: obj.certificates.all(),
        ),
        DetailTableSpec(
            title='ASPA Intents',
            table_class_name='ASPAIntentTable',
            queryset=lambda obj: obj.aspa_intents.all(),
        ),
        DetailTableSpec(
            title='ASPA Reconciliation Runs',
            table_class_name='ASPAReconciliationRunTable',
            queryset=lambda obj: obj.aspa_reconciliation_runs.all(),
        ),
        DetailTableSpec(
            title='ASPA Change Plans',
            table_class_name='ASPAChangePlanTable',
            queryset=lambda obj: obj.aspa_change_plans.all(),
        ),
        DetailTableSpec(
            title='ROA Lint Rule Configs',
            table_class_name='ROALintRuleConfigTable',
            queryset=lambda obj: obj.roa_lint_rule_configs.all(),
        ),
    ),
)


def get_related_count(attribute_name: str) -> ValueGetter:
    return lambda obj, attr=attribute_name: getattr(obj, attr).count()


def get_pretty_json(value: Any) -> str | None:
    if not value:
        return None
    return json.dumps(value, indent=2, sort_keys=True)


def get_profile_description(profile: models.RoutingIntentProfile) -> str | None:
    return profile.description or None


def get_profile_prefix_selector(profile: models.RoutingIntentProfile) -> str | None:
    return profile.prefix_selector_query or None


def get_profile_asn_selector(profile: models.RoutingIntentProfile) -> str | None:
    return profile.asn_selector_query or None


def get_binding_prefix_selector(binding: models.RoutingIntentTemplateBinding) -> str | None:
    return binding.prefix_selector_query or None


def get_binding_asn_selector(binding: models.RoutingIntentTemplateBinding) -> str | None:
    return binding.asn_selector_query or None


def get_binding_summary(binding: models.RoutingIntentTemplateBinding) -> str | None:
    return get_pretty_json(binding.summary_json)


def get_context_group_summary(context_group: models.RoutingIntentContextGroup) -> str | None:
    return get_pretty_json(context_group.summary_json)


def get_context_group_labels(context_group: models.RoutingIntentContextGroup) -> str | None:
    labels = [criterion.name for criterion in context_group.criteria.filter(enabled=True).order_by('weight', 'name')]
    return ', '.join(labels) or None


def get_exception_lifecycle_status(exception: models.RoutingIntentException) -> str:
    now = timezone.now()
    if not exception.enabled:
        return 'Disabled'
    if not exception.approved_at or not exception.approved_by:
        return 'Pending Approval'
    if exception.starts_at and exception.starts_at > now:
        return 'Scheduled'
    if exception.ends_at and exception.ends_at < now:
        return 'Expired'
    return 'Active'


def get_exception_scope_summary(exception: models.RoutingIntentException) -> str:
    parts = []
    if exception.intent_profile_id:
        parts.append(f'Profile: {exception.intent_profile}')
    if exception.template_binding_id:
        parts.append(f'Binding: {exception.template_binding}')
    if exception.prefix_id:
        parts.append(f'Prefix: {exception.prefix}')
    elif exception.prefix_cidr_text:
        parts.append(f'Prefix: {exception.prefix_cidr_text}')
    if exception.origin_asn_id:
        parts.append(f'Origin ASN: {exception.origin_asn}')
    elif exception.origin_asn_value:
        parts.append(f'Origin ASN: AS{exception.origin_asn_value}')
    return ', '.join(parts) or 'Organization-scoped exception'


def get_exception_summary(exception: models.RoutingIntentException) -> str | None:
    return get_pretty_json(exception.summary_json)


def exception_can_approve(exception: models.RoutingIntentException) -> bool:
    return bool(exception.enabled and (not exception.approved_at or not exception.approved_by))


def get_bulk_run_summary(bulk_run: models.BulkIntentRun) -> str | None:
    return get_pretty_json(bulk_run.summary_json)


def get_irr_run_scope_summary(run: models.IrrCoordinationRun) -> str | None:
    return get_pretty_json(run.scope_summary_json)


def get_irr_run_summary(run: models.IrrCoordinationRun) -> str | None:
    return get_pretty_json(run.summary_json)


def get_irr_plan_summary(plan: models.IrrChangePlan) -> str | None:
    return get_pretty_json(plan.summary_json)


def get_irr_execution_request_summary(execution: models.IrrWriteExecution) -> str | None:
    return get_pretty_json(execution.request_payload_json)


def get_irr_execution_response_summary(execution: models.IrrWriteExecution) -> str | None:
    return get_pretty_json(execution.response_payload_json)


def get_bulk_scope_result_summary(scope_result: models.BulkIntentRunScopeResult) -> str | None:
    return get_pretty_json(scope_result.summary_json)


def binding_can_regenerate(binding: models.RoutingIntentTemplateBinding) -> bool:
    return (
        binding.enabled
        and binding.template.enabled
        and binding.template.status == models.RoutingIntentTemplateStatus.ACTIVE
        and binding.intent_profile.enabled
    )


def get_run_result_summary(run: models.ROAReconciliationRun) -> str | None:
    return get_pretty_json(run.result_summary_json)


def get_result_details(result: models.ROAIntentResult) -> str | None:
    return get_pretty_json(result.details_json)


def get_aspa_run_result_summary(run: models.ASPAReconciliationRun) -> str | None:
    return get_pretty_json(run.result_summary_json)


def get_roa_reconciliation_external_overlay_summary(run: models.ROAReconciliationRun) -> str | None:
    return get_pretty_json(build_roa_reconciliation_overlay_summary(run))


def get_aspa_reconciliation_external_overlay_summary(run: models.ASPAReconciliationRun) -> str | None:
    return get_pretty_json(build_aspa_reconciliation_overlay_summary(run))


def get_aspa_result_details(result: models.ASPAIntentResult) -> str | None:
    return get_pretty_json(result.details_json)


def get_aspa_published_result_details(result: models.PublishedASPAResult) -> str | None:
    return get_pretty_json(result.details_json)


def get_published_result_details(result: models.PublishedROAResult) -> str | None:
    return get_pretty_json(result.details_json)


def get_result_expected_origin(result: models.ROAIntentResult) -> Any:
    return result.roa_intent.origin_asn or result.roa_intent.origin_asn_value


def get_result_published_origin(result: models.ROAIntentResult) -> Any:
    if result.best_roa_id is None:
        return None
    return result.best_roa.origin_as


def get_result_best_roa_prefixes(result: models.ROAIntentResult) -> str | None:
    if result.best_roa_id is None:
        return None
    prefixes = [str(prefix.prefix) for prefix in result.best_roa.RoaToPrefixTable.all()]
    return ', '.join(prefixes) or None


def get_result_best_roa_max_lengths(result: models.ROAIntentResult) -> str | None:
    if result.best_roa_id is None:
        return None
    max_lengths = [str(prefix.max_length) for prefix in result.best_roa.RoaToPrefixTable.all()]
    return ', '.join(max_lengths) or None


def get_plan_summary(plan: models.ROAChangePlan) -> str | None:
    summary = dict(plan.summary_json or {})
    if isinstance(plan, models.ROAChangePlan):
        summary['lint_posture'] = build_roa_change_plan_lint_posture(plan)
    return get_pretty_json(summary)


def get_roa_change_plan_external_overlay_summary(plan: models.ROAChangePlan) -> str | None:
    return get_pretty_json(build_roa_change_plan_overlay_summary(plan))


def get_aspa_change_plan_external_overlay_summary(plan: models.ASPAChangePlan) -> str | None:
    return get_pretty_json(build_aspa_change_plan_overlay_summary(plan))


def get_change_plan_publication_state(plan) -> str | None:
    result = derive_change_plan_publication_state(plan)
    return get_pretty_json(result.as_dict())


def get_rollback_bundle_publication_state(bundle) -> str | None:
    result = derive_rollback_bundle_publication_state(bundle)
    return get_pretty_json(result.as_dict())


def get_lint_run_summary(run: models.ROALintRun) -> str | None:
    return get_pretty_json(run.summary_json)


def get_lint_run_lifecycle_summary(run: models.ROALintRun) -> str | None:
    from netbox_rpki.services.roa_lint import build_roa_lint_lifecycle_summary
    return get_pretty_json(build_roa_lint_lifecycle_summary(run))


def get_latest_reconciliation_lint_lifecycle_summary(run: models.ROAReconciliationRun) -> str | None:
    lint_run = run.lint_runs.order_by('-started_at', '-created').first()
    if lint_run is None:
        return None
    from netbox_rpki.services.roa_lint import build_roa_lint_lifecycle_summary
    return get_pretty_json(build_roa_lint_lifecycle_summary(lint_run))


def get_plan_lint_posture(plan: models.ROAChangePlan) -> str | None:
    from netbox_rpki.services.roa_lint import build_roa_change_plan_lint_posture
    return get_pretty_json(build_roa_change_plan_lint_posture(plan))


def get_lint_finding_details(finding: models.ROALintFinding) -> str | None:
    return get_pretty_json(finding.details_json)


def get_lint_finding_rule_label(finding: models.ROALintFinding) -> str | None:
    return finding.details_json.get('rule_label')


def get_lint_finding_approval_impact(finding: models.ROALintFinding) -> str | None:
    return finding.details_json.get('approval_impact')


def get_lint_finding_operator_message(finding: models.ROALintFinding) -> str | None:
    return finding.details_json.get('operator_message')


def get_lint_finding_why_it_matters(finding: models.ROALintFinding) -> str | None:
    return finding.details_json.get('why_it_matters')


def get_lint_finding_operator_action(finding: models.ROALintFinding) -> str | None:
    return finding.details_json.get('operator_action')


def get_lint_suppression_fact_context(suppression: models.ROALintSuppression) -> str | None:
    return get_pretty_json(suppression.fact_context_json)


def get_lint_suppression_is_active(suppression: models.ROALintSuppression) -> str:
    return 'Yes' if suppression.is_active else 'No'


def get_simulation_run_summary(run: models.ROAValidationSimulationRun) -> str | None:
    summary = dict(run.summary_json or {})
    summary.setdefault('plan_fingerprint', run.plan_fingerprint)
    summary.setdefault('overall_approval_posture', run.overall_approval_posture)
    summary.setdefault('is_current_for_plan', run.is_current_for_plan)
    summary.setdefault('partially_constrained', run.partially_constrained)
    return get_pretty_json(summary)


def get_simulation_result_details(result: models.ROAValidationSimulationResult) -> str | None:
    details = dict(result.details_json or {})
    details.setdefault('approval_impact', result.approval_impact)
    details.setdefault('scenario_type', result.scenario_type)
    return get_pretty_json(details)


def get_latest_plan_simulation_run(plan: models.ROAChangePlan) -> models.ROAValidationSimulationRun | None:
    return plan.simulation_runs.order_by('-started_at', '-created').first()


def get_latest_plan_simulation_posture(plan: models.ROAChangePlan) -> str | None:
    simulation_run = get_latest_plan_simulation_run(plan)
    if simulation_run is None:
        return None
    return simulation_run.overall_approval_posture


def get_latest_plan_simulation_is_current(plan: models.ROAChangePlan) -> bool | None:
    simulation_run = get_latest_plan_simulation_run(plan)
    if simulation_run is None:
        return None
    return simulation_run.is_current_for_plan


def get_latest_plan_simulation_partially_constrained(plan: models.ROAChangePlan) -> bool | None:
    simulation_run = get_latest_plan_simulation_run(plan)
    if simulation_run is None:
        return None
    return simulation_run.partially_constrained


def get_latest_plan_simulation_summary(plan: models.ROAChangePlan) -> str | None:
    simulation_run = get_latest_plan_simulation_run(plan)
    if simulation_run is None:
        return None
    return get_simulation_run_summary(simulation_run)


def get_simulation_run_approval_impact_counts(run: models.ROAValidationSimulationRun) -> str | None:
    return get_pretty_json((run.summary_json or {}).get('approval_impact_counts') or {})


def get_simulation_run_scenario_type_counts(run: models.ROAValidationSimulationRun) -> str | None:
    return get_pretty_json((run.summary_json or {}).get('scenario_type_counts') or {})


def get_simulation_result_operator_message(result: models.ROAValidationSimulationResult) -> str | None:
    return (result.details_json or {}).get('operator_message')


def get_simulation_result_why_it_matters(result: models.ROAValidationSimulationResult) -> str | None:
    return (result.details_json or {}).get('why_it_matters')


def get_simulation_result_operator_action(result: models.ROAValidationSimulationResult) -> str | None:
    return (result.details_json or {}).get('operator_action')


def get_simulation_result_impact_scope(result: models.ROAValidationSimulationResult) -> str | None:
    return (result.details_json or {}).get('impact_scope')


def get_simulation_result_before_coverage(result: models.ROAValidationSimulationResult) -> str | None:
    return get_pretty_json((result.details_json or {}).get('before_coverage') or {})


def get_simulation_result_after_coverage(result: models.ROAValidationSimulationResult) -> str | None:
    return get_pretty_json((result.details_json or {}).get('after_coverage') or {})


def get_simulation_result_affected_prefixes(result: models.ROAValidationSimulationResult) -> str | None:
    prefixes = (result.details_json or {}).get('affected_prefixes') or []
    return ', '.join(str(prefix) for prefix in prefixes) or None


def get_simulation_result_affected_origin_asns(result: models.ROAValidationSimulationResult) -> str | None:
    origin_asns = (result.details_json or {}).get('affected_origin_asns') or []
    return ', '.join(str(asn) for asn in origin_asns) or None


def get_approval_record_simulation_review(record: models.ApprovalRecord) -> str | None:
    return get_pretty_json(record.simulation_review_json)


def get_plan_provider_capability(plan) -> str | None:
    if not plan.provider_account_id:
        return None
    if isinstance(plan, models.ASPAChangePlan):
        return get_pretty_json(plan.provider_account.aspa_write_capability)
    return get_pretty_json(plan.provider_account.roa_write_capability)


def get_write_execution_request_payload(execution: models.ProviderWriteExecution) -> str | None:
    return get_pretty_json(execution.request_payload_json)


def get_write_execution_response_payload(execution: models.ProviderWriteExecution) -> str | None:
    return get_pretty_json(execution.response_payload_json)


def get_change_plan_item_provider_payload(item: models.ROAChangePlanItem) -> str | None:
    return get_pretty_json(item.provider_payload_json)


def get_change_plan_item_before_state(item: models.ROAChangePlanItem) -> str | None:
    return get_pretty_json(item.before_state_json)


def get_change_plan_item_after_state(item: models.ROAChangePlanItem) -> str | None:
    return get_pretty_json(item.after_state_json)


def get_provider_last_sync_summary(account: models.RpkiProviderAccount) -> str | None:
    return get_pretty_json(account.last_sync_summary_json)


def get_provider_account_family_rollups(account: models.RpkiProviderAccount) -> str | None:
    from netbox_rpki.services.provider_sync_contract import build_provider_account_rollup

    if not account.last_sync_summary_json:
        return None
    return get_pretty_json(build_provider_account_rollup(account).get('family_rollups'))


def get_provider_account_pub_obs_rollup(account: models.RpkiProviderAccount) -> str | None:
    from netbox_rpki.services.provider_sync_contract import build_provider_account_pub_obs_rollup

    return get_pretty_json(build_provider_account_pub_obs_rollup(account))


def get_provider_account_health_timeline(account: models.RpkiProviderAccount) -> str | None:
    from netbox_rpki.services.lifecycle_reporting import build_provider_lifecycle_timeline

    return get_pretty_json(build_provider_lifecycle_timeline(account))


def get_provider_account_publication_diff_timeline(account: models.RpkiProviderAccount) -> str | None:
    from netbox_rpki.services.lifecycle_reporting import build_provider_publication_diff_timeline

    return get_pretty_json(build_provider_publication_diff_timeline(account))


def get_provider_sync_run_summary(run: models.ProviderSyncRun) -> str | None:
    return get_pretty_json(run.summary_json)


def get_provider_snapshot_summary(snapshot: models.ProviderSnapshot) -> str | None:
    return get_pretty_json(snapshot.summary_json)


def get_provider_snapshot_family_rollups(snapshot: models.ProviderSnapshot) -> str | None:
    from netbox_rpki.services.provider_sync_contract import build_provider_snapshot_rollup

    return get_pretty_json(build_provider_snapshot_rollup(snapshot)['family_rollups'])


def get_provider_snapshot_signed_object_type_breakdown(snapshot: models.ProviderSnapshot) -> str | None:
    from netbox_rpki.services.provider_sync_contract import build_snapshot_signed_object_type_breakdown

    breakdown = build_snapshot_signed_object_type_breakdown(snapshot)
    return get_pretty_json(breakdown)


def get_provider_snapshot_latest_diff_summary(snapshot: models.ProviderSnapshot) -> str | None:
    from netbox_rpki.services.provider_sync_contract import build_provider_snapshot_rollup

    return get_pretty_json(build_provider_snapshot_rollup(snapshot)['latest_diff_summary'])


def get_provider_snapshot_publication_health(snapshot: models.ProviderSnapshot) -> str | None:
    from netbox_rpki.services.lifecycle_reporting import build_snapshot_publication_health_rollup

    return get_pretty_json(build_snapshot_publication_health_rollup(snapshot))


def get_provider_snapshot_diff_summary(snapshot_diff: models.ProviderSnapshotDiff) -> str | None:
    return get_pretty_json(snapshot_diff.summary_json)


def get_provider_snapshot_diff_family_rollups(snapshot_diff: models.ProviderSnapshotDiff) -> str | None:
    from netbox_rpki.services.provider_sync_contract import build_provider_snapshot_diff_rollup

    return get_pretty_json(build_provider_snapshot_diff_rollup(snapshot_diff)['family_rollups'])


def get_provider_snapshot_diff_publication_health(snapshot_diff: models.ProviderSnapshotDiff) -> str | None:
    from netbox_rpki.services.lifecycle_reporting import build_diff_publication_health_rollup

    return get_pretty_json(build_diff_publication_health_rollup(snapshot_diff))


def get_provider_snapshot_diff_before_state(item: models.ProviderSnapshotDiffItem) -> str | None:
    return get_pretty_json(item.before_state_json)


def get_provider_snapshot_diff_after_state(item: models.ProviderSnapshotDiffItem) -> str | None:
    return get_pretty_json(item.after_state_json)


def get_router_certificate_extension(ee_certificate: models.EndEntityCertificate):
    try:
        return ee_certificate.router_certificate_extension
    except models.RouterCertificate.DoesNotExist:
        return None


def get_optional_related(instance: Any, attribute_name: str):
    try:
        return getattr(instance, attribute_name)
    except (AttributeError, ObjectDoesNotExist):
        return None


def get_signed_object_legacy_roa(signed_object: models.SignedObject):
    return get_optional_related(signed_object, 'legacy_roa')


def get_signed_object_crl(signed_object: models.SignedObject):
    return get_optional_related(signed_object, 'crl_extension')


def get_signed_object_manifest(signed_object: models.SignedObject):
    return get_optional_related(signed_object, 'manifest_extension')


def get_signed_object_trust_anchor_key(signed_object: models.SignedObject):
    return get_optional_related(signed_object, 'trust_anchor_key_extension')


def get_signed_object_aspa(signed_object: models.SignedObject):
    return get_optional_related(signed_object, 'aspa_extension')


def get_signed_object_rsc(signed_object: models.SignedObject):
    return get_optional_related(signed_object, 'rsc_extension')


def get_provider_snapshot_sync_run(snapshot: models.ProviderSnapshot):
    try:
        return snapshot.sync_run
    except models.ProviderSyncRun.DoesNotExist:
        return None


def get_latest_provider_snapshot_diff(snapshot: models.ProviderSnapshot):
    return snapshot.diffs_as_comparison.order_by('-compared_at', '-pk').first()


IMPORTED_ASPA_DETAIL_SPEC = DetailSpec(
    model=models.ImportedAspa,
    list_url_name='plugins:netbox_rpki:importedaspa_list',
    breadcrumb_label='Imported ASPAs',
    card_title='Imported ASPA',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link'),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(
            label='Customer ASN',
            value=lambda obj: obj.customer_as or obj.customer_as_value,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Authorization Key', value=lambda obj: obj.authorization_key),
        DetailFieldSpec(label='External Object ID', value=lambda obj: obj.external_object_id, empty_text='None'),
        DetailFieldSpec(label='External Reference', value=lambda obj: obj.external_reference, kind='link', empty_text='None'),
        DetailFieldSpec(label='Is Stale', value=lambda obj: obj.is_stale),
        DetailFieldSpec(label='Imported Providers', value=get_related_count('provider_authorizations')),
        DetailFieldSpec(
            label='Payload',
            value=lambda obj: get_pretty_json(obj.payload_json),
            kind='code',
            empty_text='None',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Imported Provider Authorizations',
            table_class_name='ImportedAspaProviderTable',
            queryset=lambda obj: obj.provider_authorizations.select_related('provider_as', 'tenant').all(),
        ),
    ),
)


IMPORTED_CA_METADATA_DETAIL_SPEC = DetailSpec(
    model=models.ImportedCaMetadata,
    list_url_name='plugins:netbox_rpki:importedcametadata_list',
    breadcrumb_label='Imported CA Metadata',
    card_title='Imported CA Metadata',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link'),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Metadata Key', value=lambda obj: obj.metadata_key),
        DetailFieldSpec(label='CA Handle', value=lambda obj: obj.ca_handle),
        DetailFieldSpec(label='ID Certificate Hash', value=lambda obj: obj.id_cert_hash, empty_text='None'),
        DetailFieldSpec(label='Publication URI', value=lambda obj: obj.publication_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='RRDP Notification URI', value=lambda obj: obj.rrdp_notification_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Parent Count', value=lambda obj: obj.parent_count),
        DetailFieldSpec(label='Child Count', value=lambda obj: obj.child_count),
        DetailFieldSpec(label='Suspended Child Count', value=lambda obj: obj.suspended_child_count),
        DetailFieldSpec(label='Resource Class Count', value=lambda obj: obj.resource_class_count),
        DetailFieldSpec(label='External Object ID', value=lambda obj: obj.external_object_id, empty_text='None'),
        DetailFieldSpec(label='External Reference', value=lambda obj: obj.external_reference, kind='link', empty_text='None'),
        DetailFieldSpec(label='Is Stale', value=lambda obj: obj.is_stale),
        DetailFieldSpec(label='Payload', value=lambda obj: get_pretty_json(obj.payload_json), kind='code', empty_text='None'),
    ),
)


IMPORTED_PARENT_LINK_DETAIL_SPEC = DetailSpec(
    model=models.ImportedParentLink,
    list_url_name='plugins:netbox_rpki:importedparentlink_list',
    breadcrumb_label='Imported Parent Links',
    card_title='Imported Parent Link',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link'),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Link Key', value=lambda obj: obj.link_key),
        DetailFieldSpec(label='Parent Handle', value=lambda obj: obj.parent_handle),
        DetailFieldSpec(label='Relationship Type', value=lambda obj: obj.relationship_type, empty_text='None'),
        DetailFieldSpec(label='Service URI', value=lambda obj: obj.service_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Last Exchange At', value=lambda obj: obj.last_exchange_at, empty_text='None'),
        DetailFieldSpec(label='Last Exchange Result', value=lambda obj: obj.last_exchange_result, empty_text='None'),
        DetailFieldSpec(label='Last Success At', value=lambda obj: obj.last_success_at, empty_text='None'),
        DetailFieldSpec(label='External Object ID', value=lambda obj: obj.external_object_id, empty_text='None'),
        DetailFieldSpec(label='External Reference', value=lambda obj: obj.external_reference, kind='link', empty_text='None'),
        DetailFieldSpec(label='Is Stale', value=lambda obj: obj.is_stale),
        DetailFieldSpec(label='Payload', value=lambda obj: get_pretty_json(obj.payload_json), kind='code', empty_text='None'),
    ),
)


IMPORTED_CHILD_LINK_DETAIL_SPEC = DetailSpec(
    model=models.ImportedChildLink,
    list_url_name='plugins:netbox_rpki:importedchildlink_list',
    breadcrumb_label='Imported Child Links',
    card_title='Imported Child Link',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link'),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Link Key', value=lambda obj: obj.link_key),
        DetailFieldSpec(label='Child Handle', value=lambda obj: obj.child_handle),
        DetailFieldSpec(label='State', value=lambda obj: obj.state),
        DetailFieldSpec(label='ID Certificate Hash', value=lambda obj: obj.id_cert_hash, empty_text='None'),
        DetailFieldSpec(label='User Agent', value=lambda obj: obj.user_agent, empty_text='None'),
        DetailFieldSpec(label='Last Exchange At', value=lambda obj: obj.last_exchange_at, empty_text='None'),
        DetailFieldSpec(label='Last Exchange Result', value=lambda obj: obj.last_exchange_result, empty_text='None'),
        DetailFieldSpec(label='External Object ID', value=lambda obj: obj.external_object_id, empty_text='None'),
        DetailFieldSpec(label='External Reference', value=lambda obj: obj.external_reference, kind='link', empty_text='None'),
        DetailFieldSpec(label='Is Stale', value=lambda obj: obj.is_stale),
        DetailFieldSpec(label='Payload', value=lambda obj: get_pretty_json(obj.payload_json), kind='code', empty_text='None'),
    ),
)


IMPORTED_RESOURCE_ENTITLEMENT_DETAIL_SPEC = DetailSpec(
    model=models.ImportedResourceEntitlement,
    list_url_name='plugins:netbox_rpki:importedresourceentitlement_list',
    breadcrumb_label='Imported Resource Entitlements',
    card_title='Imported Resource Entitlement',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link'),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Entitlement Key', value=lambda obj: obj.entitlement_key),
        DetailFieldSpec(label='Entitlement Source', value=lambda obj: obj.entitlement_source),
        DetailFieldSpec(label='Related Handle', value=lambda obj: obj.related_handle, empty_text='None'),
        DetailFieldSpec(label='Class Name', value=lambda obj: obj.class_name, empty_text='None'),
        DetailFieldSpec(label='ASN Resources', value=lambda obj: obj.asn_resources, empty_text='None'),
        DetailFieldSpec(label='IPv4 Resources', value=lambda obj: obj.ipv4_resources, empty_text='None'),
        DetailFieldSpec(label='IPv6 Resources', value=lambda obj: obj.ipv6_resources, empty_text='None'),
        DetailFieldSpec(label='Not After', value=lambda obj: obj.not_after, empty_text='None'),
        DetailFieldSpec(label='External Object ID', value=lambda obj: obj.external_object_id, empty_text='None'),
        DetailFieldSpec(label='External Reference', value=lambda obj: obj.external_reference, kind='link', empty_text='None'),
        DetailFieldSpec(label='Is Stale', value=lambda obj: obj.is_stale),
        DetailFieldSpec(label='Payload', value=lambda obj: get_pretty_json(obj.payload_json), kind='code', empty_text='None'),
    ),
)


IMPORTED_PUBLICATION_POINT_DETAIL_SPEC = DetailSpec(
    model=models.ImportedPublicationPoint,
    list_url_name='plugins:netbox_rpki:importedpublicationpoint_list',
    breadcrumb_label='Imported Publication Points',
    card_title='Imported Publication Point',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link'),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Publication Key', value=lambda obj: obj.publication_key),
        DetailFieldSpec(label='Service URI', value=lambda obj: obj.service_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Publication URI', value=lambda obj: obj.publication_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='RRDP Notification URI', value=lambda obj: obj.rrdp_notification_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Last Exchange At', value=lambda obj: obj.last_exchange_at, empty_text='None'),
        DetailFieldSpec(label='Last Exchange Result', value=lambda obj: obj.last_exchange_result, empty_text='None'),
        DetailFieldSpec(label='Next Exchange Before', value=lambda obj: obj.next_exchange_before, empty_text='None'),
        DetailFieldSpec(label='Published Object Count', value=lambda obj: obj.published_object_count),
        DetailFieldSpec(label='External Object ID', value=lambda obj: obj.external_object_id, empty_text='None'),
        DetailFieldSpec(label='External Reference', value=lambda obj: obj.external_reference, kind='link', empty_text='None'),
        DetailFieldSpec(
            label='Authored Publication Point',
            value=lambda obj: obj.authored_publication_point,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Authored Linkage Status', value=get_publication_point_authored_linkage_status),
        DetailFieldSpec(label='Is Stale', value=lambda obj: obj.is_stale),
        DetailFieldSpec(
            label='Evidence Summary',
            value=get_imported_publication_point_evidence_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Payload', value=lambda obj: get_pretty_json(obj.payload_json), kind='code', empty_text='None'),
    ),
)


IMPORTED_SIGNED_OBJECT_DETAIL_SPEC = DetailSpec(
    model=models.ImportedSignedObject,
    list_url_name='plugins:netbox_rpki:importedsignedobject_list',
    breadcrumb_label='Imported Signed Objects',
    card_title='Imported Signed Object',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link'),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Publication Point', value=lambda obj: obj.publication_point, kind='link'),
        DetailFieldSpec(label='Signed Object Key', value=lambda obj: obj.signed_object_key),
        DetailFieldSpec(label='Signed Object Type', value=lambda obj: obj.signed_object_type),
        DetailFieldSpec(label='Publication URI', value=lambda obj: obj.publication_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Signed Object URI', value=lambda obj: obj.signed_object_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Object Hash', value=lambda obj: obj.object_hash, empty_text='None'),
        DetailFieldSpec(label='Body Base64', value=lambda obj: obj.body_base64, kind='code', empty_text='None'),
        DetailFieldSpec(label='External Object ID', value=lambda obj: obj.external_object_id, empty_text='None'),
        DetailFieldSpec(label='External Reference', value=lambda obj: obj.external_reference, kind='link', empty_text='None'),
        DetailFieldSpec(
            label='Authored Signed Object',
            value=lambda obj: obj.authored_signed_object,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Publication Linkage Status', value=get_signed_object_publication_linkage_status),
        DetailFieldSpec(label='Authored Linkage Status', value=get_signed_object_authored_linkage_status),
        DetailFieldSpec(label='Is Stale', value=lambda obj: obj.is_stale),
        DetailFieldSpec(
            label='Evidence Summary',
            value=get_imported_signed_object_evidence_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='External Overlay Summary',
            value=get_imported_signed_object_external_overlay_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Payload', value=lambda obj: get_pretty_json(obj.payload_json), kind='code', empty_text='None'),
    ),
)


IMPORTED_CERTIFICATE_OBSERVATION_DETAIL_SPEC = DetailSpec(
    model=models.ImportedCertificateObservation,
    list_url_name='plugins:netbox_rpki:importedcertificateobservation_list',
    breadcrumb_label='Imported Certificate Observations',
    card_title='Imported Certificate Observation',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link'),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Publication Point', value=lambda obj: obj.publication_point, kind='link', empty_text='None'),
        DetailFieldSpec(label='Signed Object', value=lambda obj: obj.signed_object, kind='link', empty_text='None'),
        DetailFieldSpec(label='Certificate Key', value=lambda obj: obj.certificate_key),
        DetailFieldSpec(label='Observation Source', value=lambda obj: obj.observation_source),
        DetailFieldSpec(label='Certificate URI', value=lambda obj: obj.certificate_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Publication URI', value=lambda obj: obj.publication_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Signed Object URI', value=lambda obj: obj.signed_object_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Related Handle', value=lambda obj: obj.related_handle, empty_text='None'),
        DetailFieldSpec(label='Class Name', value=lambda obj: obj.class_name, empty_text='None'),
        DetailFieldSpec(label='Subject', value=lambda obj: obj.subject, empty_text='None'),
        DetailFieldSpec(label='Issuer', value=lambda obj: obj.issuer, empty_text='None'),
        DetailFieldSpec(label='Serial Number', value=lambda obj: obj.serial_number, empty_text='None'),
        DetailFieldSpec(label='Not Before', value=lambda obj: obj.not_before, empty_text='None'),
        DetailFieldSpec(label='Not After', value=lambda obj: obj.not_after, empty_text='None'),
        DetailFieldSpec(label='Source Count', value=get_certificate_observation_source_count),
        DetailFieldSpec(label='Source Labels', value=lambda obj: ', '.join(get_certificate_observation_source_labels(obj)) or 'None'),
        DetailFieldSpec(label='Is Ambiguous', value=get_certificate_observation_is_ambiguous),
        DetailFieldSpec(label='Publication Linkage Status', value=get_certificate_observation_publication_linkage_status),
        DetailFieldSpec(label='Signed Object Linkage Status', value=get_certificate_observation_signed_object_linkage_status),
        DetailFieldSpec(label='External Object ID', value=lambda obj: obj.external_object_id, empty_text='None'),
        DetailFieldSpec(label='External Reference', value=lambda obj: obj.external_reference, kind='link', empty_text='None'),
        DetailFieldSpec(label='Is Stale', value=lambda obj: obj.is_stale),
        DetailFieldSpec(
            label='Evidence Summary',
            value=get_imported_certificate_observation_evidence_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='External Overlay Summary',
            value=get_imported_certificate_observation_external_overlay_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Payload', value=lambda obj: get_pretty_json(obj.payload_json), kind='code', empty_text='None'),
    ),
)


ASPA_DETAIL_SPEC = DetailSpec(
    model=models.ASPA,
    list_url_name='plugins:netbox_rpki:aspa_list',
    breadcrumb_label='ASPAs',
    card_title='ASPA',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Organization',
            value=lambda obj: obj.organization,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Signed Object',
            value=lambda obj: obj.signed_object,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Customer ASN',
            value=lambda obj: obj.customer_as,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Valid From', value=lambda obj: obj.valid_from, empty_text='None'),
        DetailFieldSpec(label='Valid To', value=lambda obj: obj.valid_to, empty_text='None'),
        DetailFieldSpec(label='Validation State', value=lambda obj: obj.validation_state),
        DetailFieldSpec(label='Authorized Providers', value=get_related_count('provider_authorizations')),
        DetailFieldSpec(label='Validated Payloads', value=get_related_count('validated_payloads')),
        DetailFieldSpec(
            label='External Overlay Summary',
            value=get_aspa_external_overlay_summary,
            kind='code',
            empty_text='None',
        ),
    ),
    side_tables=(
        DetailTableSpec(
            title='Authorized Provider ASNs',
            table_class_name='ASPAProviderAuthorizationTable',
            queryset=lambda obj: obj.provider_authorizations.select_related('provider_as', 'tenant').all(),
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Validated ASPA Payloads',
            table_class_name='ValidatedAspaPayloadTable',
            queryset=lambda obj: obj.validated_payloads.select_related('validation_run', 'object_validation_result', 'customer_as', 'provider_as').all(),
        ),
    ),
)


ROA_CHANGE_PLAN_DETAIL_SPEC = DetailSpec(
    model=models.ROAChangePlan,
    list_url_name='plugins:netbox_rpki:roachangeplan_list',
    breadcrumb_label='ROA Change Plans',
    card_title='ROA Change Plan',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Source Reconciliation Run', value=lambda obj: obj.source_reconciliation_run, kind='link'),
        DetailFieldSpec(
            label='Provider Account',
            value=lambda obj: obj.provider_account,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Provider Snapshot',
            value=lambda obj: obj.provider_snapshot,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(
            label='Publication State',
            value=get_change_plan_publication_state,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Requires Secondary Approval', value=lambda obj: obj.requires_secondary_approval),
        DetailFieldSpec(label='Ticket Reference', value=lambda obj: obj.ticket_reference, empty_text='None'),
        DetailFieldSpec(label='Change Reference', value=lambda obj: obj.change_reference, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window Start', value=lambda obj: obj.maintenance_window_start, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window End', value=lambda obj: obj.maintenance_window_end, empty_text='None'),
        DetailFieldSpec(label='Approved At', value=lambda obj: obj.approved_at, empty_text='None'),
        DetailFieldSpec(label='Approved By', value=lambda obj: obj.approved_by, empty_text='None'),
        DetailFieldSpec(label='Secondary Approved At', value=lambda obj: obj.secondary_approved_at, empty_text='None'),
        DetailFieldSpec(label='Secondary Approved By', value=lambda obj: obj.secondary_approved_by, empty_text='None'),
        DetailFieldSpec(label='Apply Started At', value=lambda obj: obj.apply_started_at, empty_text='None'),
        DetailFieldSpec(label='Apply Requested By', value=lambda obj: obj.apply_requested_by, empty_text='None'),
        DetailFieldSpec(label='Applied At', value=lambda obj: obj.applied_at, empty_text='None'),
        DetailFieldSpec(label='Failed At', value=lambda obj: obj.failed_at, empty_text='None'),
        DetailFieldSpec(
            label='Latest Simulation Run',
            value=get_latest_plan_simulation_run,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Latest Simulation Posture',
            value=get_latest_plan_simulation_posture,
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Latest Simulation Is Current',
            value=get_latest_plan_simulation_is_current,
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Latest Simulation Partially Constrained',
            value=get_latest_plan_simulation_partially_constrained,
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Latest Simulation Summary',
            value=get_latest_plan_simulation_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Provider Write Capability',
            value=get_plan_provider_capability,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Plan Summary',
            value=get_plan_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='External Overlay Summary',
            value=get_roa_change_plan_external_overlay_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Lint Posture',
            value=get_plan_lint_posture,
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplan',
            label='Simulate',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplan_simulate', kwargs={'pk': obj.pk}),
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplan',
            label='Preview',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplan_preview', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_preview,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplan',
            label='Acknowledge Lint',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplan_acknowledge_lint', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_acknowledge_lint,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplan',
            label='Approve',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_approve,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplan',
            label='Secondary Approval',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplan_approve_secondary', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_approve_secondary,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplan',
            label='Apply',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplan_apply', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_apply,
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='ROA Change Plan Items',
            table_class_name='ROAChangePlanItemTable',
            queryset=lambda obj: obj.items.all(),
        ),
        DetailTableSpec(
            title='Approval Records',
            table_class_name='ApprovalRecordTable',
            queryset=lambda obj: obj.approval_records.all(),
        ),
        DetailTableSpec(
            title='ROA Lint Acknowledgements',
            table_class_name='ROALintAcknowledgementTable',
            queryset=lambda obj: obj.lint_acknowledgements.all(),
        ),
        DetailTableSpec(
            title='Provider Write Executions',
            table_class_name='ProviderWriteExecutionTable',
            queryset=lambda obj: obj.provider_write_executions.all(),
        ),
        DetailTableSpec(
            title='Rollback Bundles',
            table_class_name='ROAChangePlanRollbackBundleTable',
            queryset=lambda obj: models.ROAChangePlanRollbackBundle.objects.filter(source_plan=obj),
        ),
        DetailTableSpec(
            title='ROA Lint Runs',
            table_class_name='ROALintRunTable',
            queryset=lambda obj: obj.lint_runs.all(),
        ),
        DetailTableSpec(
            title='ROA Validation Simulation Runs',
            table_class_name='ROAValidationSimulationRunTable',
            queryset=lambda obj: obj.simulation_runs.all(),
        ),
    ),
)


PROVIDER_WRITE_EXECUTION_DETAIL_SPEC = DetailSpec(
    model=models.ProviderWriteExecution,
    list_url_name='plugins:netbox_rpki:providerwriteexecution_list',
    breadcrumb_label='Provider Write Executions',
    card_title='Provider Write Execution',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Provider Account', value=lambda obj: obj.provider_account, kind='link'),
        DetailFieldSpec(
            label='Provider Snapshot',
            value=lambda obj: obj.provider_snapshot,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Change Plan', value=lambda obj: obj.target_change_plan, kind='link'),
        DetailFieldSpec(label='Execution Mode', value=lambda obj: obj.execution_mode),
        DetailFieldSpec(label='Object Family', value=lambda obj: obj.object_family),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Requested By', value=lambda obj: obj.requested_by, empty_text='None'),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Item Count', value=lambda obj: obj.item_count),
        DetailFieldSpec(
            label='Follow-Up Sync Run',
            value=lambda obj: obj.followup_sync_run,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Follow-Up Provider Snapshot',
            value=lambda obj: obj.followup_provider_snapshot,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Error', value=lambda obj: obj.error, empty_text='None'),
        DetailFieldSpec(
            label='Request Payload',
            value=get_write_execution_request_payload,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Response Payload',
            value=get_write_execution_response_payload,
            kind='code',
            empty_text='None',
        ),
    ),
)


ROA_CHANGE_PLAN_ROLLBACK_BUNDLE_DETAIL_SPEC = DetailSpec(
    model=models.ROAChangePlanRollbackBundle,
    list_url_name='plugins:netbox_rpki:roachangeplanrollbackbundle_list',
    breadcrumb_label='ROA Change Plan Rollback Bundles',
    card_title='ROA Rollback Bundle',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Source Plan', value=lambda obj: obj.source_plan, kind='link'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(
            label='Publication State',
            value=get_rollback_bundle_publication_state,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Item Count', value=lambda obj: obj.item_count),
        DetailFieldSpec(label='Ticket Reference', value=lambda obj: obj.ticket_reference, empty_text='None'),
        DetailFieldSpec(label='Change Reference', value=lambda obj: obj.change_reference, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window Start', value=lambda obj: obj.maintenance_window_start, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window End', value=lambda obj: obj.maintenance_window_end, empty_text='None'),
        DetailFieldSpec(label='Approved By', value=lambda obj: obj.approved_by, empty_text='None'),
        DetailFieldSpec(label='Approved At', value=lambda obj: obj.approved_at, empty_text='None'),
        DetailFieldSpec(label='Apply Requested By', value=lambda obj: obj.apply_requested_by, empty_text='None'),
        DetailFieldSpec(label='Apply Started At', value=lambda obj: obj.apply_started_at, empty_text='None'),
        DetailFieldSpec(label='Applied At', value=lambda obj: obj.applied_at, empty_text='None'),
        DetailFieldSpec(label='Failed At', value=lambda obj: obj.failed_at, empty_text='None'),
        DetailFieldSpec(label='Notes', value=lambda obj: obj.notes, empty_text='None'),
        DetailFieldSpec(label='Apply Error', value=lambda obj: obj.apply_error, empty_text='None'),
        DetailFieldSpec(label='Rollback Delta', value=lambda obj: obj.rollback_delta_json, kind='code', empty_text='None'),
        DetailFieldSpec(label='Apply Response', value=lambda obj: obj.apply_response_json, kind='code', empty_text='None'),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplanrollbackbundle',
            label='Approve Rollback',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplanrollbackbundle_approve', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_approve,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplanrollbackbundle',
            label='Apply Rollback',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplanrollbackbundle_apply', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_apply,
        ),
    ),
)


ASPA_CHANGE_PLAN_ROLLBACK_BUNDLE_DETAIL_SPEC = DetailSpec(
    model=models.ASPAChangePlanRollbackBundle,
    list_url_name='plugins:netbox_rpki:aspachangeplanrollbackbundle_list',
    breadcrumb_label='ASPA Change Plan Rollback Bundles',
    card_title='ASPA Rollback Bundle',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Source Plan', value=lambda obj: obj.source_plan, kind='link'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(
            label='Publication State',
            value=get_rollback_bundle_publication_state,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Item Count', value=lambda obj: obj.item_count),
        DetailFieldSpec(label='Ticket Reference', value=lambda obj: obj.ticket_reference, empty_text='None'),
        DetailFieldSpec(label='Change Reference', value=lambda obj: obj.change_reference, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window Start', value=lambda obj: obj.maintenance_window_start, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window End', value=lambda obj: obj.maintenance_window_end, empty_text='None'),
        DetailFieldSpec(label='Approved By', value=lambda obj: obj.approved_by, empty_text='None'),
        DetailFieldSpec(label='Approved At', value=lambda obj: obj.approved_at, empty_text='None'),
        DetailFieldSpec(label='Apply Requested By', value=lambda obj: obj.apply_requested_by, empty_text='None'),
        DetailFieldSpec(label='Apply Started At', value=lambda obj: obj.apply_started_at, empty_text='None'),
        DetailFieldSpec(label='Applied At', value=lambda obj: obj.applied_at, empty_text='None'),
        DetailFieldSpec(label='Failed At', value=lambda obj: obj.failed_at, empty_text='None'),
        DetailFieldSpec(label='Notes', value=lambda obj: obj.notes, empty_text='None'),
        DetailFieldSpec(label='Apply Error', value=lambda obj: obj.apply_error, empty_text='None'),
        DetailFieldSpec(label='Rollback Delta', value=lambda obj: obj.rollback_delta_json, kind='code', empty_text='None'),
        DetailFieldSpec(label='Apply Response', value=lambda obj: obj.apply_response_json, kind='code', empty_text='None'),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_aspachangeplanrollbackbundle',
            label='Approve Rollback',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:aspachangeplanrollbackbundle_approve', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_approve,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_aspachangeplanrollbackbundle',
            label='Apply Rollback',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:aspachangeplanrollbackbundle_apply', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_apply,
        ),
    ),
)


ROUTING_INTENT_PROFILE_DETAIL_SPEC = DetailSpec(
    model=models.RoutingIntentProfile,
    list_url_name='plugins:netbox_rpki:routingintentprofile_list',
    breadcrumb_label='Routing Intent Profiles',
    card_title='Routing Intent Profile Dashboard',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Default Profile', value=lambda obj: obj.is_default),
        DetailFieldSpec(label='Enabled', value=lambda obj: obj.enabled),
        DetailFieldSpec(label='Selector Mode', value=lambda obj: obj.selector_mode),
        DetailFieldSpec(label='Default Max Length Policy', value=lambda obj: obj.default_max_length_policy),
        DetailFieldSpec(label='Allow AS0', value=lambda obj: obj.allow_as0),
        DetailFieldSpec(label='Context Groups', value=get_related_count('context_groups')),
        DetailFieldSpec(label='Rules', value=get_related_count('rules')),
        DetailFieldSpec(label='Overrides', value=get_related_count('overrides')),
        DetailFieldSpec(label='Derived Intents', value=get_related_count('roa_intents')),
        DetailFieldSpec(label='Derivation Runs', value=get_related_count('derivation_runs')),
        DetailFieldSpec(label='Reconciliation Runs', value=get_related_count('reconciliation_runs')),
        DetailFieldSpec(
            label='Prefix Selector Query',
            value=get_profile_prefix_selector,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='ASN Selector Query',
            value=get_profile_asn_selector,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Description',
            value=get_profile_description,
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_routingintentprofile',
            label='Run Profile',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:routingintentprofile_run', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.enabled,
        ),
    ),
    side_tables=(
        DetailTableSpec(
            title='Context Groups',
            table_class_name='RoutingIntentContextGroupTable',
            queryset=lambda obj: obj.context_groups.all(),
        ),
        DetailTableSpec(
            title='Routing Intent Rules',
            table_class_name='RoutingIntentRuleTable',
            queryset=lambda obj: obj.rules.all(),
        ),
        DetailTableSpec(
            title='ROA Intent Overrides',
            table_class_name='ROAIntentOverrideTable',
            queryset=lambda obj: obj.overrides.all(),
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Intent Derivation Runs',
            table_class_name='IntentDerivationRunTable',
            queryset=lambda obj: obj.derivation_runs.all(),
        ),
        DetailTableSpec(
            title='ROA Reconciliation Runs',
            table_class_name='ROAReconciliationRunTable',
            queryset=lambda obj: obj.reconciliation_runs.all(),
        ),
        DetailTableSpec(
            title='Derived ROA Intents',
            table_class_name='ROAIntentTable',
            queryset=lambda obj: obj.roa_intents.all(),
        ),
    ),
)


ROUTING_INTENT_CONTEXT_GROUP_DETAIL_SPEC = DetailSpec(
    model=models.RoutingIntentContextGroup,
    list_url_name='plugins:netbox_rpki:routingintentcontextgroup_list',
    breadcrumb_label='Routing Intent Context Groups',
    card_title='Routing Intent Context Group',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Context Type', value=lambda obj: obj.context_type),
        DetailFieldSpec(label='Priority', value=lambda obj: obj.priority),
        DetailFieldSpec(label='Enabled', value=lambda obj: obj.enabled),
        DetailFieldSpec(label='Criteria', value=get_related_count('criteria')),
        DetailFieldSpec(label='Profiles', value=get_related_count('intent_profiles')),
        DetailFieldSpec(label='Template Bindings', value=get_related_count('template_bindings')),
        DetailFieldSpec(label='Description', value=lambda obj: obj.description or None, kind='code', empty_text='None'),
        DetailFieldSpec(label='Enabled Criteria', value=get_context_group_labels, empty_text='None'),
        DetailFieldSpec(label='Summary', value=get_context_group_summary, kind='code', empty_text='None'),
    ),
    side_tables=(
        DetailTableSpec(
            title='Context Criteria',
            table_class_name='RoutingIntentContextCriterionTable',
            queryset=lambda obj: obj.criteria.all(),
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Intent Profiles',
            table_class_name='RoutingIntentProfileTable',
            queryset=lambda obj: obj.intent_profiles.all(),
        ),
        DetailTableSpec(
            title='Template Bindings',
            table_class_name='RoutingIntentTemplateBindingTable',
            queryset=lambda obj: obj.template_bindings.all(),
        ),
    ),
)


ROUTING_INTENT_EXCEPTION_DETAIL_SPEC = DetailSpec(
    model=models.RoutingIntentException,
    list_url_name='plugins:netbox_rpki:routingintentexception_list',
    breadcrumb_label='Routing Intent Exceptions',
    card_title='Routing Intent Exception',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Intent Profile', value=lambda obj: obj.intent_profile, kind='link', empty_text='None'),
        DetailFieldSpec(label='Template Binding', value=lambda obj: obj.template_binding, kind='link', empty_text='None'),
        DetailFieldSpec(label='Exception Type', value=lambda obj: obj.exception_type),
        DetailFieldSpec(label='Effect Mode', value=lambda obj: obj.effect_mode),
        DetailFieldSpec(label='Lifecycle Status', value=get_exception_lifecycle_status),
        DetailFieldSpec(label='Enabled', value=lambda obj: obj.enabled),
        DetailFieldSpec(label='Scope Summary', value=get_exception_scope_summary, kind='code'),
        DetailFieldSpec(label='Starts At', value=lambda obj: obj.starts_at, empty_text='None'),
        DetailFieldSpec(label='Ends At', value=lambda obj: obj.ends_at, empty_text='None'),
        DetailFieldSpec(label='Approved At', value=lambda obj: obj.approved_at, empty_text='None'),
        DetailFieldSpec(label='Approved By', value=lambda obj: obj.approved_by or None, empty_text='None'),
        DetailFieldSpec(label='Reason', value=lambda obj: obj.reason or None, kind='code', empty_text='None'),
        DetailFieldSpec(label='Summary', value=get_exception_summary, kind='code', empty_text='None'),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_routingintentexception',
            label='Approve Exception',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:routingintentexception_approve', kwargs={'pk': obj.pk}),
            visible=exception_can_approve,
        ),
    ),
)


ROUTING_INTENT_TEMPLATE_BINDING_DETAIL_SPEC = DetailSpec(
    model=models.RoutingIntentTemplateBinding,
    list_url_name='plugins:netbox_rpki:routingintenttemplatebinding_list',
    breadcrumb_label='Routing Intent Template Bindings',
    card_title='Routing Intent Template Binding',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Template', value=lambda obj: obj.template, kind='link'),
        DetailFieldSpec(label='Intent Profile', value=lambda obj: obj.intent_profile, kind='link'),
        DetailFieldSpec(label='Enabled', value=lambda obj: obj.enabled),
        DetailFieldSpec(label='Binding Priority', value=lambda obj: obj.binding_priority),
        DetailFieldSpec(label='Binding Label', value=lambda obj: obj.binding_label or None, empty_text='None'),
        DetailFieldSpec(label='State', value=lambda obj: obj.state),
        DetailFieldSpec(
            label='Origin ASN Override',
            value=lambda obj: obj.origin_asn_override,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Max Length Mode', value=lambda obj: obj.max_length_mode),
        DetailFieldSpec(label='Max Length Value', value=lambda obj: obj.max_length_value, empty_text='None'),
        DetailFieldSpec(label='Last Compiled Fingerprint', value=lambda obj: obj.last_compiled_fingerprint or None, empty_text='None'),
        DetailFieldSpec(label='Context Groups', value=get_related_count('context_groups')),
        DetailFieldSpec(
            label='Prefix Selector Query',
            value=get_binding_prefix_selector,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='ASN Selector Query',
            value=get_binding_asn_selector,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Summary',
            value=get_binding_summary,
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_routingintenttemplatebinding',
            label='Preview Binding',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:routingintenttemplatebinding_preview', kwargs={'pk': obj.pk}),
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_routingintenttemplatebinding',
            label='Regenerate Binding',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:routingintenttemplatebinding_regenerate', kwargs={'pk': obj.pk}),
            visible=binding_can_regenerate,
        ),
    ),
    side_tables=(
        DetailTableSpec(
            title='Context Groups',
            table_class_name='RoutingIntentContextGroupTable',
            queryset=lambda obj: obj.context_groups.all(),
        ),
        DetailTableSpec(
            title='Binding Exceptions',
            table_class_name='RoutingIntentExceptionTable',
            queryset=lambda obj: obj.exceptions.all(),
        ),
    ),
)


BULK_INTENT_RUN_DETAIL_SPEC = DetailSpec(
    model=models.BulkIntentRun,
    list_url_name='plugins:netbox_rpki:bulkintentrun_list',
    breadcrumb_label='Bulk Intent Runs',
    card_title='Bulk Intent Run',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Trigger Mode', value=lambda obj: obj.trigger_mode),
        DetailFieldSpec(label='Target Mode', value=lambda obj: obj.target_mode),
        DetailFieldSpec(label='Baseline Fingerprint', value=lambda obj: obj.baseline_fingerprint or None, empty_text='None'),
        DetailFieldSpec(label='Resulting Fingerprint', value=lambda obj: obj.resulting_fingerprint or None, empty_text='None'),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Summary', value=get_bulk_run_summary, kind='code', empty_text='None'),
        DetailFieldSpec(label='Requested By', value=lambda obj: obj.requested_by or None, empty_text='None'),
        DetailFieldSpec(label='Ticket Reference', value=lambda obj: obj.ticket_reference or None, empty_text='None'),
        DetailFieldSpec(label='Change Reference', value=lambda obj: obj.change_reference or None, empty_text='None'),
        DetailFieldSpec(label='Requires Secondary Approval', value=lambda obj: obj.requires_secondary_approval),
        DetailFieldSpec(label='Approved At', value=lambda obj: obj.approved_at, empty_text='None'),
        DetailFieldSpec(label='Approved By', value=lambda obj: obj.approved_by or None, empty_text='None'),
        DetailFieldSpec(label='Secondary Approved At', value=lambda obj: obj.secondary_approved_at, empty_text='None'),
        DetailFieldSpec(label='Secondary Approved By', value=lambda obj: obj.secondary_approved_by or None, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window Start', value=lambda obj: obj.maintenance_window_start, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window End', value=lambda obj: obj.maintenance_window_end, empty_text='None'),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Scope Results',
            table_class_name='BulkIntentRunScopeResultTable',
            queryset=lambda obj: obj.scope_results.all(),
        ),
    ),
)


BULK_INTENT_RUN_SCOPE_RESULT_DETAIL_SPEC = DetailSpec(
    model=models.BulkIntentRunScopeResult,
    list_url_name='plugins:netbox_rpki:bulkintentrunscoperesult_list',
    breadcrumb_label='Bulk Intent Run Scope Results',
    card_title='Bulk Intent Scope Result',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Bulk Run', value=lambda obj: obj.bulk_run, kind='link'),
        DetailFieldSpec(label='Intent Profile', value=lambda obj: obj.intent_profile, kind='link', empty_text='None'),
        DetailFieldSpec(label='Template Binding', value=lambda obj: obj.template_binding, kind='link', empty_text='None'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Scope Kind', value=lambda obj: obj.scope_kind or None, empty_text='None'),
        DetailFieldSpec(label='Scope Key', value=lambda obj: obj.scope_key or None, empty_text='None'),
        DetailFieldSpec(label='Derivation Run', value=lambda obj: obj.derivation_run, kind='link', empty_text='None'),
        DetailFieldSpec(label='Reconciliation Run', value=lambda obj: obj.reconciliation_run, kind='link', empty_text='None'),
        DetailFieldSpec(label='Change Plan', value=lambda obj: obj.change_plan, kind='link', empty_text='None'),
        DetailFieldSpec(label='Prefixes Scanned', value=lambda obj: obj.prefix_count_scanned),
        DetailFieldSpec(label='Intents Emitted', value=lambda obj: obj.intent_count_emitted),
        DetailFieldSpec(label='Planned Items', value=lambda obj: obj.plan_item_count),
        DetailFieldSpec(label='Summary', value=get_bulk_scope_result_summary, kind='code', empty_text='None'),
    ),
)


ROA_RECONCILIATION_RUN_DETAIL_SPEC = DetailSpec(
    model=models.ROAReconciliationRun,
    list_url_name='plugins:netbox_rpki:roareconciliationrun_list',
    breadcrumb_label='ROA Reconciliation Runs',
    card_title='ROA Reconciliation Run',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Intent Profile', value=lambda obj: obj.intent_profile, kind='link'),
        DetailFieldSpec(label='Basis Derivation Run', value=lambda obj: obj.basis_derivation_run, kind='link'),
        DetailFieldSpec(
            label='Provider Snapshot',
            value=lambda obj: obj.provider_snapshot,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Comparison Scope', value=lambda obj: obj.comparison_scope),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Published ROA Count', value=lambda obj: obj.published_roa_count),
        DetailFieldSpec(label='Intent Count', value=lambda obj: obj.intent_count),
        DetailFieldSpec(label='Intent Results', value=get_related_count('intent_results')),
        DetailFieldSpec(label='Published ROA Results', value=get_related_count('published_roa_results')),
        DetailFieldSpec(label='Lint Runs', value=get_related_count('lint_runs')),
        DetailFieldSpec(
            label='Result Summary',
            value=get_run_result_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Latest Lint Lifecycle Summary',
            value=get_latest_reconciliation_lint_lifecycle_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='External Overlay Summary',
            value=get_roa_reconciliation_external_overlay_summary,
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_routingintentprofile',
            label='Create Plan',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roareconciliationrun_create_plan', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.status == models.ValidationRunStatus.COMPLETED,
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='ROA Intent Results',
            table_class_name='ROAIntentResultTable',
            queryset=lambda obj: obj.intent_results.all(),
        ),
        DetailTableSpec(
            title='Published ROA Results',
            table_class_name='PublishedROAResultTable',
            queryset=lambda obj: obj.published_roa_results.all(),
        ),
        DetailTableSpec(
            title='ROA Lint Runs',
            table_class_name='ROALintRunTable',
            queryset=lambda obj: obj.lint_runs.all(),
        ),
    ),
)


ROA_INTENT_RESULT_DETAIL_SPEC = DetailSpec(
    model=models.ROAIntentResult,
    list_url_name='plugins:netbox_rpki:roaintentresult_list',
    breadcrumb_label='ROA Intent Results',
    card_title='ROA Intent Result Diff',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Reconciliation Run', value=lambda obj: obj.reconciliation_run, kind='link'),
        DetailFieldSpec(label='ROA Intent', value=lambda obj: obj.roa_intent, kind='link'),
        DetailFieldSpec(label='Result Type', value=lambda obj: obj.result_type),
        DetailFieldSpec(label='Severity', value=lambda obj: obj.severity),
        DetailFieldSpec(label='Match Count', value=lambda obj: obj.match_count),
        DetailFieldSpec(
            label='Best Published ROA',
            value=lambda obj: obj.best_roa,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Best Imported Authorization',
            value=lambda obj: obj.best_imported_authorization,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Computed At', value=lambda obj: obj.computed_at, empty_text='None'),
        DetailFieldSpec(label='Expected Prefix', value=lambda obj: obj.roa_intent.prefix_cidr_text, empty_text='None'),
        DetailFieldSpec(label='Expected Origin ASN', value=get_result_expected_origin, kind='link', empty_text='None'),
        DetailFieldSpec(label='Expected Max Length', value=lambda obj: obj.roa_intent.max_length, empty_text='None'),
        DetailFieldSpec(label='Published Prefixes', value=get_result_best_roa_prefixes, empty_text='None'),
        DetailFieldSpec(label='Published Origin ASN', value=get_result_published_origin, kind='link', empty_text='None'),
        DetailFieldSpec(label='Published Max Lengths', value=get_result_best_roa_max_lengths, empty_text='None'),
        DetailFieldSpec(
            label='Diff Details',
            value=get_result_details,
            kind='code',
            empty_text='None',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Candidate Matches',
            table_class_name='ROAIntentMatchTable',
            queryset=lambda obj: obj.roa_intent.candidate_matches.all(),
        ),
    ),
)


PUBLISHED_ROA_RESULT_DETAIL_SPEC = DetailSpec(
    model=models.PublishedROAResult,
    list_url_name='plugins:netbox_rpki:publishedroaresult_list',
    breadcrumb_label='Published ROA Results',
    card_title='Published ROA Result Diff',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Reconciliation Run', value=lambda obj: obj.reconciliation_run, kind='link'),
        DetailFieldSpec(label='Published ROA', value=lambda obj: obj.roa, kind='link', empty_text='None'),
        DetailFieldSpec(
            label='Imported Authorization',
            value=lambda obj: obj.imported_authorization,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Result Type', value=lambda obj: obj.result_type),
        DetailFieldSpec(label='Severity', value=lambda obj: obj.severity),
        DetailFieldSpec(label='Matched Intent Count', value=lambda obj: obj.matched_intent_count),
        DetailFieldSpec(label='Computed At', value=lambda obj: obj.computed_at, empty_text='None'),
        DetailFieldSpec(
            label='Diff Details',
            value=get_published_result_details,
            kind='code',
            empty_text='None',
        ),
    ),
)


ASPA_RECONCILIATION_RUN_DETAIL_SPEC = DetailSpec(
    model=models.ASPAReconciliationRun,
    list_url_name='plugins:netbox_rpki:aspareconciliationrun_list',
    breadcrumb_label='ASPA Reconciliation Runs',
    card_title='ASPA Reconciliation Run',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link', empty_text='None'),
        DetailFieldSpec(label='Comparison Scope', value=lambda obj: obj.comparison_scope),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Intent Count', value=lambda obj: obj.intent_count),
        DetailFieldSpec(label='Published ASPA Count', value=lambda obj: obj.published_aspa_count),
        DetailFieldSpec(
            label='Result Summary',
            value=get_aspa_run_result_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='External Overlay Summary',
            value=get_aspa_reconciliation_external_overlay_summary,
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_aspareconciliationrun',
            label='Create Plan',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:aspareconciliationrun_create_plan', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.status == models.ValidationRunStatus.COMPLETED,
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='ASPA Intent Results',
            table_class_name='ASPAIntentResultTable',
            queryset=lambda obj: obj.intent_results.all(),
        ),
        DetailTableSpec(
            title='Published ASPA Results',
            table_class_name='PublishedASPAResultTable',
            queryset=lambda obj: obj.published_aspa_results.all(),
        ),
    ),
)


ASPA_INTENT_RESULT_DETAIL_SPEC = DetailSpec(
    model=models.ASPAIntentResult,
    list_url_name='plugins:netbox_rpki:aspaintentresult_list',
    breadcrumb_label='ASPA Intent Results',
    card_title='ASPA Intent Result Diff',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Reconciliation Run', value=lambda obj: obj.reconciliation_run, kind='link'),
        DetailFieldSpec(label='ASPA Intent', value=lambda obj: obj.aspa_intent, kind='link'),
        DetailFieldSpec(label='Result Type', value=lambda obj: obj.result_type),
        DetailFieldSpec(label='Severity', value=lambda obj: obj.severity),
        DetailFieldSpec(label='Match Count', value=lambda obj: obj.match_count),
        DetailFieldSpec(label='Best Published ASPA', value=lambda obj: obj.best_aspa, kind='link', empty_text='None'),
        DetailFieldSpec(
            label='Best Imported ASPA',
            value=lambda obj: obj.best_imported_aspa,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Computed At', value=lambda obj: obj.computed_at, empty_text='None'),
        DetailFieldSpec(label='Customer ASN', value=lambda obj: obj.aspa_intent.customer_as, kind='link'),
        DetailFieldSpec(label='Expected Provider ASN', value=lambda obj: obj.aspa_intent.provider_as, kind='link'),
        DetailFieldSpec(
            label='Diff Details',
            value=get_aspa_result_details,
            kind='code',
            empty_text='None',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Candidate Matches',
            table_class_name='ASPAIntentMatchTable',
            queryset=lambda obj: obj.aspa_intent.candidate_matches.all(),
        ),
    ),
)


PUBLISHED_ASPA_RESULT_DETAIL_SPEC = DetailSpec(
    model=models.PublishedASPAResult,
    list_url_name='plugins:netbox_rpki:publishedasparesult_list',
    breadcrumb_label='Published ASPA Results',
    card_title='Published ASPA Result Diff',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Reconciliation Run', value=lambda obj: obj.reconciliation_run, kind='link'),
        DetailFieldSpec(label='Published ASPA', value=lambda obj: obj.aspa, kind='link', empty_text='None'),
        DetailFieldSpec(label='Imported ASPA', value=lambda obj: obj.imported_aspa, kind='link', empty_text='None'),
        DetailFieldSpec(label='Result Type', value=lambda obj: obj.result_type),
        DetailFieldSpec(label='Severity', value=lambda obj: obj.severity),
        DetailFieldSpec(label='Matched Intent Count', value=lambda obj: obj.matched_intent_count),
        DetailFieldSpec(label='Computed At', value=lambda obj: obj.computed_at, empty_text='None'),
        DetailFieldSpec(
            label='Diff Details',
            value=get_aspa_published_result_details,
            kind='code',
            empty_text='None',
        ),
    ),
)


ASPA_CHANGE_PLAN_DETAIL_SPEC = DetailSpec(
    model=models.ASPAChangePlan,
    list_url_name='plugins:netbox_rpki:aspachangeplan_list',
    breadcrumb_label='ASPA Change Plans',
    card_title='ASPA Change Plan',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Source Reconciliation Run', value=lambda obj: obj.source_reconciliation_run, kind='link'),
        DetailFieldSpec(label='Provider Account', value=lambda obj: obj.provider_account, kind='link', empty_text='None'),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link', empty_text='None'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(
            label='Publication State',
            value=get_change_plan_publication_state,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Requires Secondary Approval', value=lambda obj: obj.requires_secondary_approval),
        DetailFieldSpec(label='Ticket Reference', value=lambda obj: obj.ticket_reference, empty_text='None'),
        DetailFieldSpec(label='Change Reference', value=lambda obj: obj.change_reference, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window Start', value=lambda obj: obj.maintenance_window_start, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window End', value=lambda obj: obj.maintenance_window_end, empty_text='None'),
        DetailFieldSpec(label='Approved At', value=lambda obj: obj.approved_at, empty_text='None'),
        DetailFieldSpec(label='Approved By', value=lambda obj: obj.approved_by, empty_text='None'),
        DetailFieldSpec(label='Secondary Approved At', value=lambda obj: obj.secondary_approved_at, empty_text='None'),
        DetailFieldSpec(label='Secondary Approved By', value=lambda obj: obj.secondary_approved_by, empty_text='None'),
        DetailFieldSpec(label='Apply Started At', value=lambda obj: obj.apply_started_at, empty_text='None'),
        DetailFieldSpec(label='Apply Requested By', value=lambda obj: obj.apply_requested_by, empty_text='None'),
        DetailFieldSpec(label='Applied At', value=lambda obj: obj.applied_at, empty_text='None'),
        DetailFieldSpec(label='Failed At', value=lambda obj: obj.failed_at, empty_text='None'),
        DetailFieldSpec(
            label='Provider Write Capability',
            value=get_plan_provider_capability,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Plan Summary', value=get_plan_summary, kind='code', empty_text='None'),
        DetailFieldSpec(
            label='External Overlay Summary',
            value=get_aspa_change_plan_external_overlay_summary,
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_aspachangeplan',
            label='Preview',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:aspachangeplan_preview', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_preview,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_aspachangeplan',
            label='Approve',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:aspachangeplan_approve', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_approve,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_aspachangeplan',
            label='Secondary Approval',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:aspachangeplan_approve_secondary', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_approve_secondary,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_aspachangeplan',
            label='Apply',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:aspachangeplan_apply', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_apply,
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='ASPA Change Plan Items',
            table_class_name='ASPAChangePlanItemTable',
            queryset=lambda obj: obj.items.all(),
        ),
        DetailTableSpec(
            title='Approval Records',
            table_class_name='ApprovalRecordTable',
            queryset=lambda obj: obj.approval_records.all(),
        ),
        DetailTableSpec(
            title='Provider Write Executions',
            table_class_name='ProviderWriteExecutionTable',
            queryset=lambda obj: obj.provider_write_executions.all(),
        ),
        DetailTableSpec(
            title='Rollback Bundles',
            table_class_name='ASPAChangePlanRollbackBundleTable',
            queryset=lambda obj: models.ASPAChangePlanRollbackBundle.objects.filter(source_plan=obj),
        ),
    ),
)


ROA_CHANGE_PLAN_ITEM_DETAIL_SPEC = DetailSpec(
    model=models.ROAChangePlanItem,
    list_url_name='plugins:netbox_rpki:roachangeplanitem_list',
    breadcrumb_label='ROA Change Plan Items',
    card_title='ROA Change Plan Item',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Change Plan', value=lambda obj: obj.change_plan, kind='link'),
        DetailFieldSpec(label='Action Type', value=lambda obj: obj.action_type),
        DetailFieldSpec(label='Plan Semantic', value=lambda obj: obj.plan_semantic, empty_text='None'),
        DetailFieldSpec(label='ROA Intent', value=lambda obj: obj.roa_intent, kind='link', empty_text='None'),
        DetailFieldSpec(label='Published ROA', value=lambda obj: obj.roa, kind='link', empty_text='None'),
        DetailFieldSpec(
            label='Imported Authorization',
            value=lambda obj: obj.imported_authorization,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Provider Operation', value=lambda obj: obj.provider_operation, empty_text='None'),
        DetailFieldSpec(label='Reason', value=lambda obj: obj.reason, empty_text='None'),
        DetailFieldSpec(
            label='Provider Payload',
            value=get_change_plan_item_provider_payload,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Before State',
            value=get_change_plan_item_before_state,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='After State',
            value=get_change_plan_item_after_state,
            kind='code',
            empty_text='None',
        ),
    ),
)


IRR_COORDINATION_RUN_DETAIL_SPEC = DetailSpec(
    model=models.IrrCoordinationRun,
    list_url_name='plugins:netbox_rpki:irr_coordination_run_list',
    breadcrumb_label='IRR Coordination Runs',
    card_title='IRR Coordination Run',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Compared Sources', value=get_related_count('compared_sources')),
        DetailFieldSpec(label='Change Plans', value=get_related_count('change_plans')),
        DetailFieldSpec(label='Results', value=get_related_count('results')),
        DetailFieldSpec(label='Scope Summary', value=get_irr_run_scope_summary, kind='code', empty_text='None'),
        DetailFieldSpec(label='Run Summary', value=get_irr_run_summary, kind='code', empty_text='None'),
        DetailFieldSpec(label='Error', value=lambda obj: obj.error_text or None, empty_text='None'),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='IRR Coordination Results',
            table_class_name='IrrCoordinationResultTable',
            queryset=lambda obj: obj.results.all(),
        ),
        DetailTableSpec(
            title='IRR Change Plans',
            table_class_name='IrrChangePlanTable',
            queryset=lambda obj: obj.change_plans.all(),
        ),
    ),
)


IRR_CHANGE_PLAN_DETAIL_SPEC = DetailSpec(
    model=models.IrrChangePlan,
    list_url_name='plugins:netbox_rpki:irr_change_plan_list',
    breadcrumb_label='IRR Change Plans',
    card_title='IRR Change Plan',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Coordination Run', value=lambda obj: obj.coordination_run, kind='link'),
        DetailFieldSpec(label='Source', value=lambda obj: obj.source, kind='link'),
        DetailFieldSpec(label='Snapshot', value=lambda obj: obj.snapshot, kind='link', empty_text='None'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Write Support Mode', value=lambda obj: obj.write_support_mode),
        DetailFieldSpec(label='Ticket Reference', value=lambda obj: obj.ticket_reference or None, empty_text='None'),
        DetailFieldSpec(label='Change Reference', value=lambda obj: obj.change_reference or None, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window Start', value=lambda obj: obj.maintenance_window_start, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window End', value=lambda obj: obj.maintenance_window_end, empty_text='None'),
        DetailFieldSpec(label='Approved At', value=lambda obj: obj.approved_at, empty_text='None'),
        DetailFieldSpec(label='Approved By', value=lambda obj: obj.approved_by or None, empty_text='None'),
        DetailFieldSpec(label='Execution Requested By', value=lambda obj: obj.execution_requested_by or None, empty_text='None'),
        DetailFieldSpec(label='Execution Started At', value=lambda obj: obj.execution_started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Failed At', value=lambda obj: obj.failed_at, empty_text='None'),
        DetailFieldSpec(label='Plan Summary', value=get_irr_plan_summary, kind='code', empty_text='None'),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='IRR Change Plan Items',
            table_class_name='IrrChangePlanItemTable',
            queryset=lambda obj: obj.items.all(),
        ),
        DetailTableSpec(
            title='IRR Write Executions',
            table_class_name='IrrWriteExecutionTable',
            queryset=lambda obj: obj.write_executions.all(),
        ),
    ),
)


IRR_WRITE_EXECUTION_DETAIL_SPEC = DetailSpec(
    model=models.IrrWriteExecution,
    list_url_name='plugins:netbox_rpki:irr_write_execution_list',
    breadcrumb_label='IRR Write Executions',
    card_title='IRR Write Execution',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Source', value=lambda obj: obj.source, kind='link'),
        DetailFieldSpec(label='Change Plan', value=lambda obj: obj.change_plan, kind='link'),
        DetailFieldSpec(label='Execution Mode', value=lambda obj: obj.execution_mode),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Requested By', value=lambda obj: obj.requested_by or None, empty_text='None'),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Item Count', value=lambda obj: obj.item_count),
        DetailFieldSpec(label='Request Payload', value=get_irr_execution_request_summary, kind='code', empty_text='None'),
        DetailFieldSpec(label='Response Payload', value=get_irr_execution_response_summary, kind='code', empty_text='None'),
        DetailFieldSpec(label='Error', value=lambda obj: obj.error or None, empty_text='None'),
    ),
)


ASPA_CHANGE_PLAN_ITEM_DETAIL_SPEC = DetailSpec(
    model=models.ASPAChangePlanItem,
    list_url_name='plugins:netbox_rpki:aspachangeplanitem_list',
    breadcrumb_label='ASPA Change Plan Items',
    card_title='ASPA Change Plan Item',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Change Plan', value=lambda obj: obj.change_plan, kind='link'),
        DetailFieldSpec(label='Action Type', value=lambda obj: obj.action_type),
        DetailFieldSpec(label='Plan Semantic', value=lambda obj: obj.plan_semantic, empty_text='None'),
        DetailFieldSpec(label='ASPA Intent', value=lambda obj: obj.aspa_intent, kind='link', empty_text='None'),
        DetailFieldSpec(label='Published ASPA', value=lambda obj: obj.aspa, kind='link', empty_text='None'),
        DetailFieldSpec(label='Imported ASPA', value=lambda obj: obj.imported_aspa, kind='link', empty_text='None'),
        DetailFieldSpec(label='Provider Operation', value=lambda obj: obj.provider_operation, empty_text='None'),
        DetailFieldSpec(label='Reason', value=lambda obj: obj.reason, empty_text='None'),
        DetailFieldSpec(label='Provider Payload', value=get_change_plan_item_provider_payload, kind='code', empty_text='None'),
        DetailFieldSpec(label='Before State', value=get_change_plan_item_before_state, kind='code', empty_text='None'),
        DetailFieldSpec(label='After State', value=get_change_plan_item_after_state, kind='code', empty_text='None'),
    ),
)


ROA_LINT_RUN_DETAIL_SPEC = DetailSpec(
    model=models.ROALintRun,
    list_url_name='plugins:netbox_rpki:roalintrun_list',
    breadcrumb_label='ROA Lint Runs',
    card_title='ROA Lint Run',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Reconciliation Run', value=lambda obj: obj.reconciliation_run, kind='link'),
        DetailFieldSpec(label='Change Plan', value=lambda obj: obj.change_plan, kind='link', empty_text='None'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Finding Count', value=lambda obj: obj.finding_count),
        DetailFieldSpec(label='Info Count', value=lambda obj: obj.info_count),
        DetailFieldSpec(label='Warning Count', value=lambda obj: obj.warning_count),
        DetailFieldSpec(label='Error Count', value=lambda obj: obj.error_count),
        DetailFieldSpec(label='Critical Count', value=lambda obj: obj.critical_count),
        DetailFieldSpec(label='Summary', value=get_lint_run_summary, kind='code', empty_text='None'),
        DetailFieldSpec(label='Lifecycle Summary', value=get_lint_run_lifecycle_summary, kind='code', empty_text='None'),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='ROA Lint Findings',
            table_class_name='ROALintFindingTable',
            queryset=lambda obj: obj.findings.all(),
        ),
    ),
)


ROA_LINT_FINDING_DETAIL_SPEC = DetailSpec(
    model=models.ROALintFinding,
    list_url_name='plugins:netbox_rpki:roalintfinding_list',
    breadcrumb_label='ROA Lint Findings',
    card_title='ROA Lint Finding',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Lint Run', value=lambda obj: obj.lint_run, kind='link'),
        DetailFieldSpec(label='ROA Intent Result', value=lambda obj: obj.roa_intent_result, kind='link', empty_text='None'),
        DetailFieldSpec(
            label='Published ROA Result',
            value=lambda obj: obj.published_roa_result,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Change Plan Item', value=lambda obj: obj.change_plan_item, kind='link', empty_text='None'),
        DetailFieldSpec(label='Finding Code', value=lambda obj: obj.finding_code),
        DetailFieldSpec(label='Rule Label', value=get_lint_finding_rule_label, empty_text='None'),
        DetailFieldSpec(label='Severity', value=lambda obj: obj.severity),
        DetailFieldSpec(label='Approval Impact', value=get_lint_finding_approval_impact, empty_text='None'),
        DetailFieldSpec(label='Operator Message', value=get_lint_finding_operator_message, empty_text='None'),
        DetailFieldSpec(label='Why It Matters', value=get_lint_finding_why_it_matters, empty_text='None'),
        DetailFieldSpec(label='Operator Action', value=get_lint_finding_operator_action, empty_text='None'),
        DetailFieldSpec(label='Computed At', value=lambda obj: obj.computed_at, empty_text='None'),
        DetailFieldSpec(label='Details', value=get_lint_finding_details, kind='code', empty_text='None'),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_roalintfinding',
            label='Suppress Finding',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roalintfinding_suppress', kwargs={'pk': obj.pk}),
        ),
    ),
)


ROA_LINT_SUPPRESSION_DETAIL_SPEC = DetailSpec(
    model=models.ROALintSuppression,
    list_url_name='plugins:netbox_rpki:roalintsuppression_list',
    breadcrumb_label='ROA Lint Suppressions',
    card_title='ROA Lint Suppression',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Finding Code', value=lambda obj: obj.finding_code),
        DetailFieldSpec(label='Scope Type', value=lambda obj: obj.scope_type),
        DetailFieldSpec(label='Is Active', value=get_lint_suppression_is_active),
        DetailFieldSpec(label='Intent Profile', value=lambda obj: obj.intent_profile, kind='link', empty_text='None'),
        DetailFieldSpec(label='ROA Intent', value=lambda obj: obj.roa_intent, kind='link', empty_text='None'),
        DetailFieldSpec(label='Prefix CIDR', value=lambda obj: obj.prefix_cidr_text or None, empty_text='None'),
        DetailFieldSpec(label='Reason', value=lambda obj: obj.reason),
        DetailFieldSpec(label='Fact Fingerprint', value=lambda obj: obj.fact_fingerprint, empty_text='None'),
        DetailFieldSpec(label='Fact Context', value=get_lint_suppression_fact_context, kind='code', empty_text='None'),
        DetailFieldSpec(label='Created By', value=lambda obj: obj.created_by, empty_text='None'),
        DetailFieldSpec(label='Created At', value=lambda obj: obj.created_at, empty_text='None'),
        DetailFieldSpec(label='Expires At', value=lambda obj: obj.expires_at, empty_text='None'),
        DetailFieldSpec(label='Last Matched At', value=lambda obj: obj.last_matched_at, empty_text='None'),
        DetailFieldSpec(label='Match Count', value=lambda obj: obj.match_count),
        DetailFieldSpec(label='Lifted By', value=lambda obj: obj.lifted_by, empty_text='None'),
        DetailFieldSpec(label='Lifted At', value=lambda obj: obj.lifted_at, empty_text='None'),
        DetailFieldSpec(label='Lift Reason', value=lambda obj: obj.lift_reason, empty_text='None'),
        DetailFieldSpec(label='Notes', value=lambda obj: obj.notes, empty_text='None'),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_roalintsuppression',
            label='Lift Suppression',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roalintsuppression_lift', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.lifted_at is None,
        ),
    ),
)


ROA_LINT_RULE_CONFIG_DETAIL_SPEC = DetailSpec(
    model=models.ROALintRuleConfig,
    list_url_name='plugins:netbox_rpki:roalintruleconfig_list',
    breadcrumb_label='ROA Lint Rule Configs',
    card_title='ROA Lint Rule Config',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Finding Code', value=lambda obj: obj.finding_code),
        DetailFieldSpec(label='Severity Override', value=lambda obj: obj.severity_override or None, empty_text='Default'),
        DetailFieldSpec(
            label='Approval Impact Override',
            value=lambda obj: obj.approval_impact_override or None,
            empty_text='Default',
        ),
        DetailFieldSpec(label='Notes', value=lambda obj: obj.notes or None, empty_text='None'),
    ),
)


def get_lint_acknowledgement_carries_forward(ack: models.ROALintAcknowledgement) -> str:
    """Return whether this acknowledgement is from the latest lint run on its change plan."""
    latest_run = ack.change_plan.lint_runs.order_by('-started_at', '-created').first()
    if latest_run is None:
        return 'No current lint run'
    if ack.lint_run_id == latest_run.pk:
        return 'Current run — acknowledgement is active'
    return f'Prior run (latest run is {latest_run.name}) — may carry forward as previously acknowledged'


ROA_LINT_ACKNOWLEDGEMENT_DETAIL_SPEC = DetailSpec(
    model=models.ROALintAcknowledgement,
    list_url_name='plugins:netbox_rpki:roalintacknowledgement_list',
    breadcrumb_label='ROA Lint Acknowledgements',
    card_title='ROA Lint Acknowledgement',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Change Plan', value=lambda obj: obj.change_plan, kind='link'),
        DetailFieldSpec(label='Lint Run', value=lambda obj: obj.lint_run, kind='link'),
        DetailFieldSpec(label='Finding', value=lambda obj: obj.finding, kind='link'),
        DetailFieldSpec(label='Acknowledged By', value=lambda obj: obj.acknowledged_by, empty_text='None'),
        DetailFieldSpec(label='Acknowledged At', value=lambda obj: obj.acknowledged_at, empty_text='None'),
        DetailFieldSpec(
            label='Acknowledgement Status',
            value=get_lint_acknowledgement_carries_forward,
            empty_text='None',
        ),
        DetailFieldSpec(label='Ticket Reference', value=lambda obj: obj.ticket_reference, empty_text='None'),
        DetailFieldSpec(label='Change Reference', value=lambda obj: obj.change_reference, empty_text='None'),
        DetailFieldSpec(label='Notes', value=lambda obj: obj.notes, empty_text='None'),
    ),
)


APPROVAL_RECORD_DETAIL_SPEC = DetailSpec(
    model=models.ApprovalRecord,
    list_url_name='plugins:netbox_rpki:approvalrecord_list',
    breadcrumb_label='Approval Records',
    card_title='Approval Record',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Change Plan', value=lambda obj: obj.change_plan, kind='link', empty_text='None'),
        DetailFieldSpec(label='ASPA Change Plan', value=lambda obj: obj.aspa_change_plan, kind='link', empty_text='None'),
        DetailFieldSpec(label='Disposition', value=lambda obj: obj.disposition),
        DetailFieldSpec(label='Recorded By', value=lambda obj: obj.recorded_by, empty_text='None'),
        DetailFieldSpec(label='Recorded At', value=lambda obj: obj.recorded_at, empty_text='None'),
        DetailFieldSpec(label='Ticket Reference', value=lambda obj: obj.ticket_reference, empty_text='None'),
        DetailFieldSpec(label='Change Reference', value=lambda obj: obj.change_reference, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window Start', value=lambda obj: obj.maintenance_window_start, empty_text='None'),
        DetailFieldSpec(label='Maintenance Window End', value=lambda obj: obj.maintenance_window_end, empty_text='None'),
        DetailFieldSpec(label='Notes', value=lambda obj: obj.notes, empty_text='None'),
        DetailFieldSpec(
            label='Simulation Review',
            value=get_approval_record_simulation_review,
            kind='code',
            empty_text='None',
        ),
    ),
)


ROA_VALIDATION_SIMULATION_RUN_DETAIL_SPEC = DetailSpec(
    model=models.ROAValidationSimulationRun,
    list_url_name='plugins:netbox_rpki:roavalidationsimulationrun_list',
    breadcrumb_label='ROA Validation Simulation Runs',
    card_title='ROA Validation Simulation Run',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Change Plan', value=lambda obj: obj.change_plan, kind='link'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Result Count', value=lambda obj: obj.result_count),
        DetailFieldSpec(label='Predicted Valid Count', value=lambda obj: obj.predicted_valid_count),
        DetailFieldSpec(label='Predicted Invalid Count', value=lambda obj: obj.predicted_invalid_count),
        DetailFieldSpec(label='Predicted Not Found Count', value=lambda obj: obj.predicted_not_found_count),
        DetailFieldSpec(label='Plan Fingerprint', value=lambda obj: obj.plan_fingerprint, empty_text='None'),
        DetailFieldSpec(label='Overall Approval Posture', value=lambda obj: obj.overall_approval_posture),
        DetailFieldSpec(label='Current For Plan', value=lambda obj: obj.is_current_for_plan),
        DetailFieldSpec(label='Partially Constrained', value=lambda obj: obj.partially_constrained),
        DetailFieldSpec(
            label='Approval Impact Counts',
            value=get_simulation_run_approval_impact_counts,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Scenario Type Counts',
            value=get_simulation_run_scenario_type_counts,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Summary', value=get_simulation_run_summary, kind='code', empty_text='None'),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='ROA Validation Simulation Results',
            table_class_name='ROAValidationSimulationResultTable',
            queryset=lambda obj: obj.results.all(),
        ),
    ),
)


ROA_VALIDATION_SIMULATION_RESULT_DETAIL_SPEC = DetailSpec(
    model=models.ROAValidationSimulationResult,
    list_url_name='plugins:netbox_rpki:roavalidationsimulationresult_list',
    breadcrumb_label='ROA Validation Simulation Results',
    card_title='ROA Validation Simulation Result',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Simulation Run', value=lambda obj: obj.simulation_run, kind='link'),
        DetailFieldSpec(label='Change Plan Item', value=lambda obj: obj.change_plan_item, kind='link', empty_text='None'),
        DetailFieldSpec(label='Outcome Type', value=lambda obj: obj.outcome_type),
        DetailFieldSpec(label='Approval Impact', value=lambda obj: obj.approval_impact),
        DetailFieldSpec(label='Scenario Type', value=lambda obj: obj.scenario_type, empty_text='None'),
        DetailFieldSpec(label='Impact Scope', value=get_simulation_result_impact_scope, empty_text='None'),
        DetailFieldSpec(label='Operator Message', value=get_simulation_result_operator_message, empty_text='None'),
        DetailFieldSpec(label='Why It Matters', value=get_simulation_result_why_it_matters, empty_text='None'),
        DetailFieldSpec(label='Operator Action', value=get_simulation_result_operator_action, empty_text='None'),
        DetailFieldSpec(
            label='Before Coverage',
            value=get_simulation_result_before_coverage,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='After Coverage',
            value=get_simulation_result_after_coverage,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Affected Prefixes', value=get_simulation_result_affected_prefixes, empty_text='None'),
        DetailFieldSpec(label='Affected Origin ASNs', value=get_simulation_result_affected_origin_asns, empty_text='None'),
        DetailFieldSpec(label='Computed At', value=lambda obj: obj.computed_at, empty_text='None'),
        DetailFieldSpec(label='Details', value=get_simulation_result_details, kind='code', empty_text='None'),
    ),
)


SIGNED_OBJECT_DETAIL_SPEC = DetailSpec(
    model=models.SignedObject,
    list_url_name='plugins:netbox_rpki:signedobject_list',
    breadcrumb_label='Signed Objects',
    card_title='Signed Object',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Organization',
            value=lambda obj: obj.organization,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Object Type', value=lambda obj: obj.object_type),
        DetailFieldSpec(label='Display Label', value=lambda obj: obj.display_label, empty_text='None'),
        DetailFieldSpec(
            label='Resource Certificate',
            value=lambda obj: obj.resource_certificate,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='EE Certificate',
            value=lambda obj: obj.ee_certificate,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Publication Point',
            value=lambda obj: obj.publication_point,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Current Manifest',
            value=lambda obj: obj.current_manifest,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Legacy ROA',
            value=get_signed_object_legacy_roa,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Certificate Revocation List',
            value=get_signed_object_crl,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Manifest',
            value=get_signed_object_manifest,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Trust Anchor Key',
            value=get_signed_object_trust_anchor_key,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='ASPA',
            value=get_signed_object_aspa,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='RSC',
            value=get_signed_object_rsc,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Filename', value=lambda obj: obj.filename, empty_text='None'),
        DetailFieldSpec(label='Object URI', value=lambda obj: obj.object_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Repository URI', value=lambda obj: obj.repository_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Content Hash', value=lambda obj: obj.content_hash, empty_text='None'),
        DetailFieldSpec(label='Serial or Version', value=lambda obj: obj.serial_or_version, empty_text='None'),
        DetailFieldSpec(label='CMS Digest Algorithm', value=lambda obj: obj.cms_digest_algorithm, empty_text='None'),
        DetailFieldSpec(label='CMS Signature Algorithm', value=lambda obj: obj.cms_signature_algorithm, empty_text='None'),
        DetailFieldSpec(label='Publication Status', value=lambda obj: obj.publication_status),
        DetailFieldSpec(label='Validation State', value=lambda obj: obj.validation_state),
        DetailFieldSpec(label='Valid From', value=lambda obj: obj.valid_from, empty_text='None'),
        DetailFieldSpec(label='Valid To', value=lambda obj: obj.valid_to, empty_text='None'),
        DetailFieldSpec(label='Raw Payload Reference', value=lambda obj: obj.raw_payload_reference, empty_text='None'),
        DetailFieldSpec(
            label='External Overlay Summary',
            value=get_signed_object_external_overlay_summary,
            kind='code',
            empty_text='None',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Imported Signed Object Observations',
            table_class_name='ImportedSignedObjectTable',
            queryset=lambda obj: obj.imported_signed_object_observations.select_related(
                'provider_snapshot',
                'publication_point',
            ).all(),
        ),
        DetailTableSpec(
            title='Object Validation Results',
            table_class_name='ObjectValidationResultTable',
            queryset=lambda obj: obj.validation_results.select_related('validation_run').all(),
        ),
    ),
)


CERTIFICATE_DETAIL_SPEC = DetailSpec(
    model=models.Certificate,
    list_url_name='plugins:netbox_rpki:certificate_list',
    breadcrumb_label='RPKI Customer Certificates',
    card_title='RPKI Customer Certificate',
    fields=(
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Issuer', value=lambda obj: obj.issuer),
        DetailFieldSpec(label='Subject', value=lambda obj: obj.subject),
        DetailFieldSpec(label='Serial', value=lambda obj: obj.serial),
        DetailFieldSpec(label='Valid From', value=lambda obj: obj.valid_from),
        DetailFieldSpec(label='Valid To', value=lambda obj: obj.valid_to),
        DetailFieldSpec(label='Auto-renews?', value=lambda obj: obj.auto_renews),
        DetailFieldSpec(label='Public Key', value=lambda obj: obj.public_key),
        DetailFieldSpec(label='Private Key', value=lambda obj: obj.private_key),
        DetailFieldSpec(label='Publication URL', value=lambda obj: obj.publication_url),
        DetailFieldSpec(label='CA Repository', value=lambda obj: obj.ca_repository),
        DetailFieldSpec(label='Self Hosted', value=lambda obj: obj.self_hosted),
        DetailFieldSpec(
            label='Parent RPKI customer/org',
            value=lambda obj: obj.rpki_org,
            kind='link',
        ),
        DetailFieldSpec(
            label='Trust Anchor',
            value=lambda obj: obj.trust_anchor,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Publication Point',
            value=lambda obj: obj.publication_point,
            kind='link',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_certificate',
            label='Prefix',
            url_name='plugins:netbox_rpki:certificateprefix_add',
            query_param='certificate_name',
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_certificate',
            label='ASN',
            url_name='plugins:netbox_rpki:certificateasn_add',
            query_param='certificate_name2',
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_certificate',
            label='ROA',
            url_name='plugins:netbox_rpki:roa_add',
            query_param='signed_by',
        ),
    ),
    side_tables=(
        DetailTableSpec(
            title='Attested IP Netblock Resources',
            table_class_name='CertificatePrefixTable',
            queryset=lambda obj: obj.CertificateToPrefixTable.all(),
        ),
        DetailTableSpec(
            title='Attested ASN Resource',
            table_class_name='CertificateAsnTable',
            queryset=lambda obj: obj.CertificatetoASNTable.all(),
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Issued End-Entity Certificates',
            table_class_name='EndEntityCertificateTable',
            queryset=lambda obj: obj.ee_certificates.select_related('organization', 'publication_point').all(),
        ),
        DetailTableSpec(
            title='Signed Objects',
            table_class_name='SignedObjectTable',
            queryset=lambda obj: obj.signed_objects.select_related('ee_certificate', 'publication_point').all(),
        ),
        DetailTableSpec(
            title='ROAs',
            table_class_name='RoaTable',
            queryset=lambda obj: obj.roas.all(),
        ),
    ),
)


END_ENTITY_CERTIFICATE_DETAIL_SPEC = DetailSpec(
    model=models.EndEntityCertificate,
    list_url_name='plugins:netbox_rpki:endentitycertificate_list',
    breadcrumb_label='End-Entity Certificates',
    card_title='End-Entity Certificate',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Organization',
            value=lambda obj: obj.organization,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Resource Certificate',
            value=lambda obj: obj.resource_certificate,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Publication Point',
            value=lambda obj: obj.publication_point,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Subject', value=lambda obj: obj.subject, empty_text='None'),
        DetailFieldSpec(label='Issuer', value=lambda obj: obj.issuer, empty_text='None'),
        DetailFieldSpec(label='Serial', value=lambda obj: obj.serial, empty_text='None'),
        DetailFieldSpec(label='SKI', value=lambda obj: obj.ski, empty_text='None'),
        DetailFieldSpec(label='AKI', value=lambda obj: obj.aki, empty_text='None'),
        DetailFieldSpec(label='Valid From', value=lambda obj: obj.valid_from, empty_text='None'),
        DetailFieldSpec(label='Valid To', value=lambda obj: obj.valid_to, empty_text='None'),
        DetailFieldSpec(label='Public Key', value=lambda obj: obj.public_key, empty_text='None'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(
            label='Router Certificate Extension',
            value=get_router_certificate_extension,
            kind='link',
            empty_text='None',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Signed Objects',
            table_class_name='SignedObjectTable',
            queryset=lambda obj: obj.signed_objects.select_related('resource_certificate', 'publication_point').all(),
        ),
    ),
)


ROA_DETAIL_SPEC = DetailSpec(
    model=models.Roa,
    list_url_name='plugins:netbox_rpki:roa_list',
    breadcrumb_label='RPKI ROAs',
    card_title='RPKI Route Origination Authorization (ROA)',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Origination AS Number',
            value=lambda obj: obj.origin_as,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Date Valid From', value=lambda obj: obj.valid_from),
        DetailFieldSpec(label='Date Valid To', value=lambda obj: obj.valid_to),
        DetailFieldSpec(label='Auto-renews', value=lambda obj: obj.auto_renews),
        DetailFieldSpec(
            label='Signing Certificate',
            value=lambda obj: obj.signed_by.name if obj.signed_by else None,
            kind='link',
            url=lambda obj: obj.signed_by.get_absolute_url() if obj.signed_by else None,
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Signed Object',
            value=lambda obj: obj.signed_object,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='External Overlay Summary',
            value=get_roa_external_overlay_summary,
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_roa',
            label='ROA Prefix',
            url_name='plugins:netbox_rpki:roaprefix_add',
            query_param='roa_name',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Prefixes Included in this ROA',
            table_class_name='RoaPrefixTable',
            queryset=lambda obj: obj.RoaToPrefixTable.all(),
        ),
    ),
)


PROVIDER_ACCOUNT_DETAIL_SPEC = DetailSpec(
    model=models.RpkiProviderAccount,
    list_url_name='plugins:netbox_rpki:provideraccount_list',
    breadcrumb_label='Provider Accounts',
    card_title='Provider Account',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Provider Type', value=lambda obj: obj.provider_type),
        DetailFieldSpec(label='Transport', value=lambda obj: obj.transport),
        DetailFieldSpec(label='Organization Handle', value=lambda obj: obj.org_handle),
        DetailFieldSpec(label='CA Handle', value=lambda obj: obj.ca_handle, empty_text='None'),
        DetailFieldSpec(label='API Key', value=lambda obj: obj.api_key),
        DetailFieldSpec(label='API Base URL', value=lambda obj: obj.api_base_url, kind='url'),
        DetailFieldSpec(label='Sync Enabled', value=lambda obj: obj.sync_enabled),
        DetailFieldSpec(label='Sync Interval (Minutes)', value=lambda obj: obj.sync_interval, empty_text='Manual only'),
        DetailFieldSpec(label='Next Sync Due', value=lambda obj: obj.next_sync_due_at, empty_text='Not scheduled'),
        DetailFieldSpec(label='Sync Health', value=lambda obj: obj.sync_health_display),
        DetailFieldSpec(label='Last Successful Sync', value=lambda obj: obj.last_successful_sync, empty_text='None'),
        DetailFieldSpec(label='Last Sync Status', value=lambda obj: obj.last_sync_status),
        DetailFieldSpec(
            label='ROA Write Capability',
            value=lambda obj: get_pretty_json(obj.roa_write_capability),
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='ASPA Write Capability',
            value=lambda obj: get_pretty_json(obj.aspa_write_capability),
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Last Sync Summary',
            value=get_provider_last_sync_summary,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Family Rollups',
            value=get_provider_account_family_rollups,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Publication Observation Health',
            value=get_provider_account_pub_obs_rollup,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Lifecycle Health Timeline',
            value=get_provider_account_health_timeline,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Publication Diff Timeline',
            value=get_provider_account_publication_diff_timeline,
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_rpkiprovideraccount',
            label='Sync',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:provideraccount_sync', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.sync_enabled,
        ),
        DetailActionSpec(
            permission='netbox_rpki.view_rpkiprovideraccount',
            label='Export Lifecycle JSON',
            direct_url=lambda obj: f"{reverse('plugins:netbox_rpki:provideraccount_export_lifecycle', kwargs={'pk': obj.pk})}?format=json",
        ),
        DetailActionSpec(
            permission='netbox_rpki.view_rpkiprovideraccount',
            label='Export Lifecycle CSV',
            direct_url=lambda obj: f"{reverse('plugins:netbox_rpki:provideraccount_export_lifecycle', kwargs={'pk': obj.pk})}?format=csv",
        ),
        DetailActionSpec(
            permission='netbox_rpki.view_rpkiprovideraccount',
            label='Export Timeline JSON',
            direct_url=lambda obj: f"{reverse('plugins:netbox_rpki:provideraccount_export_timeline', kwargs={'pk': obj.pk})}?format=json",
        ),
        DetailActionSpec(
            permission='netbox_rpki.view_rpkiprovideraccount',
            label='Export Timeline CSV',
            direct_url=lambda obj: f"{reverse('plugins:netbox_rpki:provideraccount_export_timeline', kwargs={'pk': obj.pk})}?format=csv",
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Provider Snapshots',
            table_class_name='ProviderSnapshotTable',
            queryset=lambda obj: obj.snapshots.all(),
        ),
        DetailTableSpec(
            title='Provider Sync Runs',
            table_class_name='ProviderSyncRunTable',
            queryset=lambda obj: obj.sync_runs.all(),
        ),
        DetailTableSpec(
            title='Provider Snapshot Diffs',
            table_class_name='ProviderSnapshotDiffTable',
            queryset=lambda obj: obj.snapshot_diffs.select_related('base_snapshot', 'comparison_snapshot').all(),
        ),
        DetailTableSpec(
            title='Provider Write Executions',
            table_class_name='ProviderWriteExecutionTable',
            queryset=lambda obj: obj.write_executions.select_related('provider_snapshot', 'change_plan').all(),
        ),
    ),
)


PROVIDER_SYNC_RUN_DETAIL_SPEC = DetailSpec(
    model=models.ProviderSyncRun,
    list_url_name='plugins:netbox_rpki:providersyncrun_list',
    breadcrumb_label='Provider Sync Runs',
    card_title='Provider Sync Run',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Provider Account', value=lambda obj: obj.provider_account, kind='link'),
        DetailFieldSpec(label='Provider Snapshot', value=lambda obj: obj.provider_snapshot, kind='link', empty_text='None'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Records Fetched', value=lambda obj: obj.records_fetched),
        DetailFieldSpec(label='Records Imported', value=lambda obj: obj.records_imported),
        DetailFieldSpec(label='Error', value=lambda obj: obj.error, empty_text='None'),
        DetailFieldSpec(label='Summary', value=get_provider_sync_run_summary, kind='code', empty_text='None'),
    ),
)


PROVIDER_SNAPSHOT_DETAIL_SPEC = DetailSpec(
    model=models.ProviderSnapshot,
    list_url_name='plugins:netbox_rpki:providersnapshot_list',
    breadcrumb_label='Provider Snapshots',
    card_title='Provider Snapshot',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Provider Account', value=lambda obj: obj.provider_account, kind='link', empty_text='None'),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Provider Name', value=lambda obj: obj.provider_name),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Fetched At', value=lambda obj: obj.fetched_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Sync Run', value=get_provider_snapshot_sync_run, kind='link', empty_text='None'),
        DetailFieldSpec(label='Latest Diff', value=get_latest_provider_snapshot_diff, kind='link', empty_text='None'),
        DetailFieldSpec(label='Latest Diff Summary', value=get_provider_snapshot_latest_diff_summary, kind='code', empty_text='None'),
        DetailFieldSpec(label='Family Rollups', value=get_provider_snapshot_family_rollups, kind='code', empty_text='None'),
        DetailFieldSpec(
            label='Signed Object Type Breakdown',
            value=get_provider_snapshot_signed_object_type_breakdown,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Publication Health',
            value=get_provider_snapshot_publication_health,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Summary', value=get_provider_snapshot_summary, kind='code', empty_text='None'),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Snapshot Comparison Diffs',
            table_class_name='ProviderSnapshotDiffTable',
            queryset=lambda obj: obj.diffs_as_comparison.select_related('base_snapshot', 'comparison_snapshot').all(),
        ),
        DetailTableSpec(
            title='Later Snapshot Diffs',
            table_class_name='ProviderSnapshotDiffTable',
            queryset=lambda obj: obj.diffs_as_base.select_related('base_snapshot', 'comparison_snapshot').all(),
        ),
        DetailTableSpec(
            title='Imported ROA Authorizations',
            table_class_name='ImportedRoaAuthorizationTable',
            queryset=lambda obj: obj.imported_roa_authorizations.select_related('prefix', 'origin_asn', 'external_reference').all(),
        ),
        DetailTableSpec(
            title='Imported ASPAs',
            table_class_name='ImportedAspaTable',
            queryset=lambda obj: obj.imported_aspas.select_related('customer_as', 'external_reference').all(),
        ),
        DetailTableSpec(
            title='Imported CA Metadata',
            table_class_name='ImportedCaMetadataTable',
            queryset=lambda obj: obj.imported_ca_metadata_records.select_related('external_reference').all(),
        ),
        DetailTableSpec(
            title='Imported Parent Links',
            table_class_name='ImportedParentLinkTable',
            queryset=lambda obj: obj.imported_parent_links.select_related('external_reference').all(),
        ),
        DetailTableSpec(
            title='Imported Child Links',
            table_class_name='ImportedChildLinkTable',
            queryset=lambda obj: obj.imported_child_links.select_related('external_reference').all(),
        ),
        DetailTableSpec(
            title='Imported Resource Entitlements',
            table_class_name='ImportedResourceEntitlementTable',
            queryset=lambda obj: obj.imported_resource_entitlements.select_related('external_reference').all(),
        ),
        DetailTableSpec(
            title='Imported Publication Points',
            table_class_name='ImportedPublicationPointTable',
            queryset=lambda obj: obj.imported_publication_points.select_related(
                'external_reference',
                'authored_publication_point',
            ).all(),
        ),
        DetailTableSpec(
            title='Imported Signed Objects',
            table_class_name='ImportedSignedObjectTable',
            queryset=lambda obj: obj.imported_signed_objects.select_related(
                'external_reference',
                'publication_point',
                'authored_signed_object',
            ).all(),
        ),
        DetailTableSpec(
            title='Imported Certificate Observations',
            table_class_name='ImportedCertificateObservationTable',
            queryset=lambda obj: obj.imported_certificate_observations.select_related('external_reference', 'publication_point', 'signed_object').all(),
        ),
    ),
)


PROVIDER_SNAPSHOT_DIFF_DETAIL_SPEC = DetailSpec(
    model=models.ProviderSnapshotDiff,
    list_url_name='plugins:netbox_rpki:providersnapshotdiff_list',
    breadcrumb_label='Provider Snapshot Diffs',
    card_title='Provider Snapshot Diff',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Provider Account', value=lambda obj: obj.provider_account, kind='link'),
        DetailFieldSpec(label='Base Snapshot', value=lambda obj: obj.base_snapshot, kind='link'),
        DetailFieldSpec(label='Comparison Snapshot', value=lambda obj: obj.comparison_snapshot, kind='link'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Compared At', value=lambda obj: obj.compared_at, empty_text='None'),
        DetailFieldSpec(label='Error', value=lambda obj: obj.error, empty_text='None'),
        DetailFieldSpec(label='Family Rollups', value=get_provider_snapshot_diff_family_rollups, kind='code', empty_text='None'),
        DetailFieldSpec(
            label='Publication Diff Summary',
            value=get_provider_snapshot_diff_publication_health,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(label='Summary', value=get_provider_snapshot_diff_summary, kind='code', empty_text='None'),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Provider Snapshot Diff Items',
            table_class_name='ProviderSnapshotDiffItemTable',
            queryset=lambda obj: obj.items.select_related('external_reference').all(),
        ),
    ),
)


PROVIDER_SNAPSHOT_DIFF_ITEM_DETAIL_SPEC = DetailSpec(
    model=models.ProviderSnapshotDiffItem,
    list_url_name='plugins:netbox_rpki:providersnapshotdiffitem_list',
    breadcrumb_label='Provider Snapshot Diff Items',
    card_title='Provider Snapshot Diff Item',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Snapshot Diff', value=lambda obj: obj.snapshot_diff, kind='link'),
        DetailFieldSpec(label='Object Family', value=lambda obj: obj.object_family),
        DetailFieldSpec(label='Change Type', value=lambda obj: obj.change_type),
        DetailFieldSpec(label='External Reference', value=lambda obj: obj.external_reference, kind='link', empty_text='None'),
        DetailFieldSpec(label='Provider Identity', value=lambda obj: obj.provider_identity, empty_text='None'),
        DetailFieldSpec(label='External Object ID', value=lambda obj: obj.external_object_id, empty_text='None'),
        DetailFieldSpec(label='Prefix', value=lambda obj: obj.prefix_cidr_text, empty_text='None'),
        DetailFieldSpec(label='Origin ASN Value', value=lambda obj: obj.origin_asn_value, empty_text='None'),
        DetailFieldSpec(label='Customer ASN Value', value=lambda obj: obj.customer_as_value, empty_text='None'),
        DetailFieldSpec(label='Provider ASN Value', value=lambda obj: obj.provider_as_value, empty_text='None'),
        DetailFieldSpec(label='Related Handle', value=lambda obj: obj.related_handle, empty_text='None'),
        DetailFieldSpec(label='Certificate Identifier', value=lambda obj: obj.certificate_identifier, empty_text='None'),
        DetailFieldSpec(label='Publication URI', value=lambda obj: obj.publication_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Signed Object URI', value=lambda obj: obj.signed_object_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Is Stale', value=lambda obj: obj.is_stale),
        DetailFieldSpec(label='Before State', value=get_provider_snapshot_diff_before_state, kind='code', empty_text='None'),
        DetailFieldSpec(label='After State', value=get_provider_snapshot_diff_after_state, kind='code', empty_text='None'),
    ),
)


def get_delegated_authorization_entity_summary(obj: models.DelegatedAuthorizationEntity) -> str | None:
    return get_pretty_json(build_delegated_authorization_entity_summary(obj))


def get_managed_authorization_relationship_summary(obj: models.ManagedAuthorizationRelationship) -> str | None:
    return get_pretty_json(build_managed_authorization_relationship_summary(obj))


def get_delegated_publication_workflow_summary(obj: models.DelegatedPublicationWorkflow) -> str | None:
    return get_pretty_json(build_delegated_publication_workflow_summary(obj))


def get_authored_ca_relationship_delegated_summary(obj: models.AuthoredCaRelationship) -> str | None:
    return get_pretty_json(build_authored_ca_relationship_delegated_summary(obj))


AUTHORED_CA_RELATIONSHIP_DETAIL_SPEC = DetailSpec(
    model=models.AuthoredCaRelationship,
    list_url_name='plugins:netbox_rpki:authoredcarelationship_list',
    breadcrumb_label='Authored CA Relationships',
    card_title='Authored CA Relationship',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Provider Account', value=lambda obj: obj.provider_account, kind='link', empty_text='None'),
        DetailFieldSpec(label='Delegated Entity', value=lambda obj: obj.delegated_entity, kind='link', empty_text='None'),
        DetailFieldSpec(label='Managed Relationship', value=lambda obj: obj.managed_relationship, kind='link', empty_text='None'),
        DetailFieldSpec(label='Child CA Handle', value=lambda obj: obj.child_ca_handle),
        DetailFieldSpec(label='Parent CA Handle', value=lambda obj: obj.parent_ca_handle, empty_text='None'),
        DetailFieldSpec(label='Relationship Type', value=lambda obj: obj.relationship_type),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Service URI', value=lambda obj: obj.service_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Delegated Workflow Summary', value=get_authored_ca_relationship_delegated_summary, kind='code', empty_text='None'),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Linked Delegated Publication Workflows',
            table_class_name='DelegatedPublicationWorkflowTable',
            queryset=lambda obj: matching_workflows_for_authored_relationship(obj),
        ),
    ),
)


DELEGATED_AUTHORIZATION_ENTITY_DETAIL_SPEC = DetailSpec(
    model=models.DelegatedAuthorizationEntity,
    list_url_name='plugins:netbox_rpki:delegatedauthorizationentity_list',
    breadcrumb_label='Delegated Authorization Entities',
    card_title='Delegated Authorization Entity',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Kind', value=lambda obj: obj.kind),
        DetailFieldSpec(label='Contact Name', value=lambda obj: obj.contact_name, empty_text='None'),
        DetailFieldSpec(label='Contact Email', value=lambda obj: obj.contact_email, empty_text='None'),
        DetailFieldSpec(label='ASN', value=lambda obj: obj.asn, empty_text='None'),
        DetailFieldSpec(label='Enabled', value=lambda obj: obj.enabled),
        DetailFieldSpec(label='Entity Summary', value=get_delegated_authorization_entity_summary, kind='code', empty_text='None'),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Managed Authorization Relationships',
            table_class_name='ManagedAuthorizationRelationshipTable',
            queryset=lambda obj: obj.managed_authorization_relationships.all(),
        ),
        DetailTableSpec(
            title='Delegated Publication Workflows',
            table_class_name='DelegatedPublicationWorkflowTable',
            queryset=lambda obj: models.DelegatedPublicationWorkflow.objects.filter(
                managed_relationship__delegated_entity=obj,
            ),
        ),
    ),
)


MANAGED_AUTHORIZATION_RELATIONSHIP_DETAIL_SPEC = DetailSpec(
    model=models.ManagedAuthorizationRelationship,
    list_url_name='plugins:netbox_rpki:managedauthorizationrelationship_list',
    breadcrumb_label='Managed Authorization Relationships',
    card_title='Managed Authorization Relationship',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Delegated Entity', value=lambda obj: obj.delegated_entity, kind='link'),
        DetailFieldSpec(label='Provider Account', value=lambda obj: obj.provider_account, kind='link', empty_text='None'),
        DetailFieldSpec(label='Role', value=lambda obj: obj.role),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Service URI', value=lambda obj: obj.service_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Relationship Summary', value=get_managed_authorization_relationship_summary, kind='code', empty_text='None'),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Delegated Publication Workflows',
            table_class_name='DelegatedPublicationWorkflowTable',
            queryset=lambda obj: obj.publication_workflows.all(),
        ),
    ),
)


DELEGATED_PUBLICATION_WORKFLOW_DETAIL_SPEC = DetailSpec(
    model=models.DelegatedPublicationWorkflow,
    list_url_name='plugins:netbox_rpki:delegatedpublicationworkflow_list',
    breadcrumb_label='Delegated Publication Workflows',
    card_title='Delegated Publication Workflow',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Managed Relationship', value=lambda obj: obj.managed_relationship, kind='link'),
        DetailFieldSpec(label='Parent CA Handle', value=lambda obj: obj.parent_ca_handle, empty_text='None'),
        DetailFieldSpec(label='Child CA Handle', value=lambda obj: obj.child_ca_handle, empty_text='None'),
        DetailFieldSpec(label='Publication Server URI', value=lambda obj: obj.publication_server_uri, kind='url', empty_text='None'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Requires Approval', value=lambda obj: obj.requires_approval),
        DetailFieldSpec(label='Approved At', value=lambda obj: obj.approved_at, empty_text='None'),
        DetailFieldSpec(label='Approved By', value=lambda obj: obj.approved_by, empty_text='None'),
        DetailFieldSpec(label='Workflow Summary', value=get_delegated_publication_workflow_summary, kind='code', empty_text='None'),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_delegatedpublicationworkflow',
            label='Approve Workflow',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:delegatedpublicationworkflow_approve', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.requires_approval and obj.approved_at is None,
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Linked Authored CA Relationships',
            table_class_name='AuthoredCaRelationshipTable',
            queryset=lambda obj: matching_authored_relationships_for_workflow(obj),
        ),
    ),
)


DETAIL_SPEC_BY_MODEL = {
    models.Organization: ORGANIZATION_DETAIL_SPEC,
    models.SignedObject: SIGNED_OBJECT_DETAIL_SPEC,
    models.Certificate: CERTIFICATE_DETAIL_SPEC,
    models.EndEntityCertificate: END_ENTITY_CERTIFICATE_DETAIL_SPEC,
    models.Roa: ROA_DETAIL_SPEC,
    models.ASPA: ASPA_DETAIL_SPEC,
    models.ImportedAspa: IMPORTED_ASPA_DETAIL_SPEC,
    models.ImportedCaMetadata: IMPORTED_CA_METADATA_DETAIL_SPEC,
    models.ImportedParentLink: IMPORTED_PARENT_LINK_DETAIL_SPEC,
    models.ImportedChildLink: IMPORTED_CHILD_LINK_DETAIL_SPEC,
    models.ImportedResourceEntitlement: IMPORTED_RESOURCE_ENTITLEMENT_DETAIL_SPEC,
    models.ImportedPublicationPoint: IMPORTED_PUBLICATION_POINT_DETAIL_SPEC,
    models.ImportedSignedObject: IMPORTED_SIGNED_OBJECT_DETAIL_SPEC,
    models.ImportedCertificateObservation: IMPORTED_CERTIFICATE_OBSERVATION_DETAIL_SPEC,
    models.RpkiProviderAccount: PROVIDER_ACCOUNT_DETAIL_SPEC,
    models.ProviderSyncRun: PROVIDER_SYNC_RUN_DETAIL_SPEC,
    models.ProviderSnapshot: PROVIDER_SNAPSHOT_DETAIL_SPEC,
    models.ProviderSnapshotDiff: PROVIDER_SNAPSHOT_DIFF_DETAIL_SPEC,
    models.ProviderSnapshotDiffItem: PROVIDER_SNAPSHOT_DIFF_ITEM_DETAIL_SPEC,
    models.AuthoredCaRelationship: AUTHORED_CA_RELATIONSHIP_DETAIL_SPEC,
    models.DelegatedAuthorizationEntity: DELEGATED_AUTHORIZATION_ENTITY_DETAIL_SPEC,
    models.ManagedAuthorizationRelationship: MANAGED_AUTHORIZATION_RELATIONSHIP_DETAIL_SPEC,
    models.DelegatedPublicationWorkflow: DELEGATED_PUBLICATION_WORKFLOW_DETAIL_SPEC,
    models.RoutingIntentProfile: ROUTING_INTENT_PROFILE_DETAIL_SPEC,
    models.RoutingIntentContextGroup: ROUTING_INTENT_CONTEXT_GROUP_DETAIL_SPEC,
    models.RoutingIntentTemplateBinding: ROUTING_INTENT_TEMPLATE_BINDING_DETAIL_SPEC,
    models.RoutingIntentException: ROUTING_INTENT_EXCEPTION_DETAIL_SPEC,
    models.BulkIntentRun: BULK_INTENT_RUN_DETAIL_SPEC,
    models.BulkIntentRunScopeResult: BULK_INTENT_RUN_SCOPE_RESULT_DETAIL_SPEC,
    models.ASPAReconciliationRun: ASPA_RECONCILIATION_RUN_DETAIL_SPEC,
    models.ASPAIntentResult: ASPA_INTENT_RESULT_DETAIL_SPEC,
    models.PublishedASPAResult: PUBLISHED_ASPA_RESULT_DETAIL_SPEC,
    models.ROAReconciliationRun: ROA_RECONCILIATION_RUN_DETAIL_SPEC,
    models.IrrCoordinationRun: IRR_COORDINATION_RUN_DETAIL_SPEC,
    models.ROALintRun: ROA_LINT_RUN_DETAIL_SPEC,
    models.ROAChangePlan: ROA_CHANGE_PLAN_DETAIL_SPEC,
    models.IrrChangePlan: IRR_CHANGE_PLAN_DETAIL_SPEC,
    models.ASPAChangePlan: ASPA_CHANGE_PLAN_DETAIL_SPEC,
    models.ROAChangePlanRollbackBundle: ROA_CHANGE_PLAN_ROLLBACK_BUNDLE_DETAIL_SPEC,
    models.ASPAChangePlanRollbackBundle: ASPA_CHANGE_PLAN_ROLLBACK_BUNDLE_DETAIL_SPEC,
    models.ROALintFinding: ROA_LINT_FINDING_DETAIL_SPEC,
    models.ROALintAcknowledgement: ROA_LINT_ACKNOWLEDGEMENT_DETAIL_SPEC,
    models.ROALintSuppression: ROA_LINT_SUPPRESSION_DETAIL_SPEC,
    models.ROALintRuleConfig: ROA_LINT_RULE_CONFIG_DETAIL_SPEC,
    models.ApprovalRecord: APPROVAL_RECORD_DETAIL_SPEC,
    models.ROAIntentResult: ROA_INTENT_RESULT_DETAIL_SPEC,
    models.PublishedROAResult: PUBLISHED_ROA_RESULT_DETAIL_SPEC,
    models.ROAChangePlanItem: ROA_CHANGE_PLAN_ITEM_DETAIL_SPEC,
    models.ASPAChangePlanItem: ASPA_CHANGE_PLAN_ITEM_DETAIL_SPEC,
    models.ROAValidationSimulationRun: ROA_VALIDATION_SIMULATION_RUN_DETAIL_SPEC,
    models.ROAValidationSimulationResult: ROA_VALIDATION_SIMULATION_RESULT_DETAIL_SPEC,
    models.ProviderWriteExecution: PROVIDER_WRITE_EXECUTION_DETAIL_SPEC,
    models.IrrWriteExecution: IRR_WRITE_EXECUTION_DETAIL_SPEC,
}
