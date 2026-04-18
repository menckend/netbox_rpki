from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from django.db.models import Q
from django.utils.text import Truncator

from netbox_rpki import models as rpki_models


DRIFT_STATE_UNKNOWN = 'unknown'
RUN_STATE_UNRECONCILED = 'unreconciled'
RUN_STATE_RECONCILED_CURRENT = 'reconciled_current'
RUN_STATE_RECONCILED_WITH_DRIFT = 'reconciled_with_drift'
RUN_STATE_RECONCILIATION_FAILED = 'reconciliation_failed'

DRIFT_STATE_BY_RESULT_TYPE = {
    rpki_models.ROAIntentResultType.MATCH: 'match',
    rpki_models.ROAIntentResultType.MISSING: 'missing',
    rpki_models.ROAIntentResultType.ASN_MISMATCH: 'origin_mismatch',
    rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_OVERBROAD: 'origin_and_length_mismatch',
    rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_TOO_NARROW: 'origin_and_length_mismatch',
    rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_MISMATCH: 'origin_and_length_mismatch',
    rpki_models.ROAIntentResultType.PREFIX_MISMATCH: 'prefix_mismatch',
    rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD: 'max_length_overbroad',
    rpki_models.ROAIntentResultType.MAX_LENGTH_TOO_NARROW: 'max_length_too_narrow',
    rpki_models.ROAIntentResultType.STALE: 'stale',
    rpki_models.ROAIntentResultType.INACTIVE_INTENT: 'inactive_intent',
    rpki_models.ROAIntentResultType.SUPPRESSED_BY_POLICY: 'suppressed_by_policy',
}


@dataclass(frozen=True)
class RoaAuthorityMapFilters:
    organization: rpki_models.Organization | None = None
    intent_profile: rpki_models.RoutingIntentProfile | None = None
    address_family: str = ''
    derived_state: str = ''
    exposure_state: str = ''
    delegated_entity: rpki_models.DelegatedAuthorizationEntity | None = None
    managed_relationship: rpki_models.ManagedAuthorizationRelationship | None = None
    provider_account: rpki_models.RpkiProviderAccount | None = None
    run_state: str = ''
    drift_state: str = ''
    q: str = ''


@dataclass(frozen=True)
class RoaAuthorityMapRow:
    authority_key: str
    subject_label: str
    prefix_cidr_text: str
    origin_asn_value: int | None
    max_length: int | None
    address_family: str
    is_as0: bool
    organization: rpki_models.Organization
    delegated_entity: rpki_models.DelegatedAuthorizationEntity | None
    managed_relationship: rpki_models.ManagedAuthorizationRelationship | None
    intent_profile: rpki_models.RoutingIntentProfile
    derivation_run: rpki_models.IntentDerivationRun
    source_rule: rpki_models.RoutingIntentRule | None
    applied_override: rpki_models.ROAIntentOverride | None
    template_binding_names: tuple[str, ...]
    profile_context_group_names: tuple[str, ...]
    binding_context_group_names: tuple[str, ...]
    scope_tenant: object | None
    scope_vrf: object | None
    scope_site: object | None
    scope_region: object | None
    derived_state: str
    exposure_state: str
    reconciliation_run: rpki_models.ROAReconciliationRun | None
    comparison_scope: str
    run_state: str
    drift_state: str
    severity: str
    latest_intent_result: rpki_models.ROAIntentResult | None
    latest_change_plan: rpki_models.ROAChangePlan | None
    change_plan_status: str
    provider_account: rpki_models.RpkiProviderAccount | None
    binding_freshness: str
    authority_reason_summary: str
    reconciliation_summary: str
    publication_summary: str
    overlap_warning: str
    roa_intent: rpki_models.ROAIntent


@dataclass(frozen=True)
class RoaAuthorityMapResult:
    rows: list[RoaAuthorityMapRow]
    total_row_count: int
    authority_counts: dict[str, int]
    exposure_counts: dict[str, int]
    run_state_counts: dict[str, int]
    drift_counts: dict[str, int]
    overlap_count: int
    excluded_profile_count: int
    no_derivation_profile_count: int
    profiles_with_stale_bindings: list[str]


def build_roa_authority_map(*, filters: RoaAuthorityMapFilters) -> RoaAuthorityMapResult:
    profile_queryset = rpki_models.RoutingIntentProfile.objects.select_related('organization').all()
    if filters.organization is not None:
        profile_queryset = profile_queryset.filter(organization=filters.organization)
    if filters.intent_profile is not None:
        profile_queryset = profile_queryset.filter(pk=filters.intent_profile.pk)

    excluded_profile_count = profile_queryset.exclude(
        status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        enabled=True,
    ).count()

    active_profiles = tuple(
        profile_queryset.filter(
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            enabled=True,
        ).order_by('name', 'pk')
    )
    authoritative_runs = get_authoritative_derivation_runs(filters=filters)
    active_profile_ids = {profile.pk for profile in active_profiles}
    no_derivation_profile_count = len(active_profile_ids.difference(authoritative_runs.keys()))

    if not authoritative_runs:
        return RoaAuthorityMapResult(
            rows=[],
            total_row_count=0,
            authority_counts={},
            exposure_counts={},
            run_state_counts={},
            drift_counts={},
            overlap_count=0,
            excluded_profile_count=excluded_profile_count,
            no_derivation_profile_count=no_derivation_profile_count,
            profiles_with_stale_bindings=[],
        )

    intent_queryset = (
        rpki_models.ROAIntent.objects
        .filter(derivation_run_id__in=[run.pk for run in authoritative_runs.values()])
        .select_related(
            'organization',
            'intent_profile',
            'derivation_run',
            'delegated_entity',
            'managed_relationship',
            'source_rule',
            'applied_override',
            'scope_tenant',
            'scope_vrf',
            'scope_site',
            'scope_region',
        )
        .order_by('prefix_cidr_text', 'origin_asn_value', 'max_length', 'pk')
    )
    if filters.organization is not None:
        intent_queryset = intent_queryset.filter(organization=filters.organization)
    if filters.intent_profile is not None:
        intent_queryset = intent_queryset.filter(intent_profile=filters.intent_profile)
    if filters.address_family:
        intent_queryset = intent_queryset.filter(address_family=filters.address_family)
    if filters.derived_state:
        intent_queryset = intent_queryset.filter(derived_state=filters.derived_state)
    if filters.exposure_state:
        intent_queryset = intent_queryset.filter(exposure_state=filters.exposure_state)
    if filters.delegated_entity is not None:
        intent_queryset = intent_queryset.filter(delegated_entity=filters.delegated_entity)
    if filters.managed_relationship is not None:
        intent_queryset = intent_queryset.filter(managed_relationship=filters.managed_relationship)
    if filters.q:
        query = filters.q.strip()
        q_filter = (
            Q(prefix_cidr_text__icontains=query)
            | Q(intent_profile__name__icontains=query)
            | Q(explanation__icontains=query)
        )
        if (source_rule_query := query):
            q_filter |= Q(source_rule__name__icontains=source_rule_query)
        try:
            q_filter |= Q(origin_asn_value=int(query.removeprefix('AS').removeprefix('as')))
        except ValueError:
            pass
        intent_queryset = intent_queryset.filter(q_filter)

    intents = list(intent_queryset)
    derivation_run_ids = {intent.derivation_run_id for intent in intents}
    reconciliation_runs = get_reconciliation_runs_for_derivations(derivation_run_ids=derivation_run_ids)
    intent_results = get_intent_results_for_reconciliations(
        reconciliation_run_ids={run.pk for run in reconciliation_runs.values()}
    )
    change_plans = get_latest_change_plans_for_reconciliations(
        reconciliation_run_ids={run.pk for run in reconciliation_runs.values()}
    )
    binding_parse = _bulk_parse_summary_json(intents)
    profiles_with_stale_bindings = sorted(
        {
            intent.intent_profile.name
            for intent in intents
            if binding_parse[intent.pk][3] in {
                rpki_models.RoutingIntentTemplateBindingState.STALE,
                rpki_models.RoutingIntentTemplateBindingState.PENDING,
                rpki_models.RoutingIntentTemplateBindingState.INVALID,
            }
        }
    )

    rows: list[RoaAuthorityMapRow] = []
    for intent in intents:
        reconciliation_run = reconciliation_runs.get(intent.derivation_run_id)
        latest_intent_result = intent_results.get(intent.pk)
        latest_change_plan = None
        if reconciliation_run is not None:
            latest_change_plan = change_plans.get(reconciliation_run.pk)
        run_state, drift_state, severity = classify_row(
            intent=intent,
            intent_result=latest_intent_result,
            reconciliation_run=reconciliation_run,
        )
        template_binding_names, profile_context_group_names, binding_context_group_names, binding_freshness = (
            binding_parse[intent.pk]
        )
        provider_account = None
        if latest_change_plan is not None and latest_change_plan.provider_account_id is not None:
            provider_account = latest_change_plan.provider_account
        elif (
            reconciliation_run is not None
            and reconciliation_run.provider_snapshot_id is not None
            and reconciliation_run.provider_snapshot.provider_account_id is not None
        ):
            provider_account = reconciliation_run.provider_snapshot.provider_account

        rows.append(
            RoaAuthorityMapRow(
                authority_key=intent.intent_key,
                subject_label=build_subject_label(intent),
                prefix_cidr_text=intent.prefix_cidr_text,
                origin_asn_value=intent.origin_asn_value,
                max_length=intent.max_length,
                address_family=intent.address_family,
                is_as0=intent.is_as0,
                organization=intent.organization,
                delegated_entity=intent.delegated_entity,
                managed_relationship=intent.managed_relationship,
                intent_profile=intent.intent_profile,
                derivation_run=intent.derivation_run,
                source_rule=intent.source_rule,
                applied_override=intent.applied_override,
                template_binding_names=template_binding_names,
                profile_context_group_names=profile_context_group_names,
                binding_context_group_names=binding_context_group_names,
                scope_tenant=intent.scope_tenant,
                scope_vrf=intent.scope_vrf,
                scope_site=intent.scope_site,
                scope_region=intent.scope_region,
                derived_state=intent.derived_state,
                exposure_state=intent.exposure_state,
                reconciliation_run=reconciliation_run,
                comparison_scope=getattr(reconciliation_run, 'comparison_scope', ''),
                run_state=run_state,
                drift_state=drift_state,
                severity=severity,
                latest_intent_result=latest_intent_result,
                latest_change_plan=latest_change_plan,
                change_plan_status=getattr(latest_change_plan, 'status', ''),
                provider_account=provider_account,
                binding_freshness=binding_freshness,
                authority_reason_summary=build_authority_reason_summary(intent),
                reconciliation_summary=build_reconciliation_summary(latest_intent_result, reconciliation_run),
                publication_summary=build_publication_summary(latest_change_plan),
                overlap_warning='',
                roa_intent=intent,
            )
        )

    overlap_map = detect_prefix_overlaps(rows)
    rows = [
        RoaAuthorityMapRow(
            **{
                **row.__dict__,
                'overlap_warning': (
                    ''
                    if not overlap_map.get(row.authority_key)
                    else f"Also covered by profile: {', '.join(overlap_map[row.authority_key])}"
                ),
            }
        )
        for row in rows
    ]

    if filters.provider_account is not None:
        rows = [
            row for row in rows
            if row.provider_account is not None and row.provider_account.pk == filters.provider_account.pk
        ]
    if filters.run_state:
        rows = [row for row in rows if row.run_state == filters.run_state]
    if filters.drift_state:
        rows = [row for row in rows if row.drift_state == filters.drift_state]

    authority_counts = Counter(row.derived_state for row in rows)
    exposure_counts = Counter(row.exposure_state for row in rows)
    run_state_counts = Counter(row.run_state for row in rows)
    drift_counts = Counter(row.drift_state for row in rows)
    overlap_count = sum(1 for row in rows if row.overlap_warning)

    return RoaAuthorityMapResult(
        rows=rows,
        total_row_count=len(rows),
        authority_counts=dict(authority_counts),
        exposure_counts=dict(exposure_counts),
        run_state_counts=dict(run_state_counts),
        drift_counts=dict(drift_counts),
        overlap_count=overlap_count,
        excluded_profile_count=excluded_profile_count,
        no_derivation_profile_count=no_derivation_profile_count,
        profiles_with_stale_bindings=profiles_with_stale_bindings,
    )


def get_authoritative_derivation_runs(
    *,
    filters: RoaAuthorityMapFilters,
) -> dict[int, rpki_models.IntentDerivationRun]:
    profile_queryset = rpki_models.RoutingIntentProfile.objects.filter(
        status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        enabled=True,
    )
    if filters.organization is not None:
        profile_queryset = profile_queryset.filter(organization=filters.organization)
    if filters.intent_profile is not None:
        profile_queryset = profile_queryset.filter(pk=filters.intent_profile.pk)

    derivations = (
        rpki_models.IntentDerivationRun.objects
        .select_related('intent_profile')
        .filter(
            intent_profile_id__in=profile_queryset.values('pk'),
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        .order_by('intent_profile_id', '-completed_at', '-started_at', '-created', '-pk')
    )
    latest_by_profile: dict[int, rpki_models.IntentDerivationRun] = {}
    for run in derivations:
        latest_by_profile.setdefault(run.intent_profile_id, run)
    return latest_by_profile


def get_reconciliation_runs_for_derivations(
    *,
    derivation_run_ids: set[int],
) -> dict[int, rpki_models.ROAReconciliationRun]:
    if not derivation_run_ids:
        return {}

    runs = list(
        rpki_models.ROAReconciliationRun.objects
        .select_related('provider_snapshot', 'provider_snapshot__provider_account')
        .filter(
            basis_derivation_run_id__in=derivation_run_ids,
            status__in=(
                rpki_models.ValidationRunStatus.COMPLETED,
                rpki_models.ValidationRunStatus.FAILED,
            ),
        )
        .order_by('-completed_at', '-started_at', '-created', '-pk')
    )
    grouped: dict[int, list[rpki_models.ROAReconciliationRun]] = defaultdict(list)
    for run in runs:
        grouped[run.basis_derivation_run_id].append(run)

    selected: dict[int, rpki_models.ROAReconciliationRun] = {}
    for derivation_run_id, derivation_runs in grouped.items():
        latest_run = derivation_runs[0]
        if latest_run.status == rpki_models.ValidationRunStatus.FAILED:
            selected[derivation_run_id] = latest_run
            continue

        provider_backed = any(
            run.provider_snapshot_id is not None
            and getattr(run.provider_snapshot, 'completed_at', None) is not None
            and getattr(getattr(run.provider_snapshot, 'provider_account', None), 'sync_enabled', False)
            for run in derivation_runs
        )
        if provider_backed:
            provider_runs = [
                run
                for run in derivation_runs
                if run.status == rpki_models.ValidationRunStatus.COMPLETED
                and run.comparison_scope == rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED
            ]
            if provider_runs:
                selected[derivation_run_id] = provider_runs[0]
                continue

        completed_runs = [
            run for run in derivation_runs
            if run.status == rpki_models.ValidationRunStatus.COMPLETED
        ]
        if completed_runs:
            local_runs = [
                run for run in completed_runs
                if run.comparison_scope == rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS
            ]
            selected[derivation_run_id] = local_runs[0] if local_runs else completed_runs[0]
    return selected


def get_intent_results_for_reconciliations(
    *,
    reconciliation_run_ids: set[int],
) -> dict[int, rpki_models.ROAIntentResult]:
    if not reconciliation_run_ids:
        return {}
    return {
        result.roa_intent_id: result
        for result in rpki_models.ROAIntentResult.objects.filter(
            reconciliation_run_id__in=reconciliation_run_ids
        ).select_related('roa_intent')
    }


def get_latest_change_plans_for_reconciliations(
    *,
    reconciliation_run_ids: set[int],
) -> dict[int, rpki_models.ROAChangePlan]:
    if not reconciliation_run_ids:
        return {}
    plans = (
        rpki_models.ROAChangePlan.objects
        .filter(source_reconciliation_run_id__in=reconciliation_run_ids)
        .select_related('provider_account')
        .order_by('source_reconciliation_run_id', '-created', '-pk')
    )
    latest_by_reconciliation: dict[int, rpki_models.ROAChangePlan] = {}
    for plan in plans:
        latest_by_reconciliation.setdefault(plan.source_reconciliation_run_id, plan)
    return latest_by_reconciliation


def classify_row(
    *,
    intent: rpki_models.ROAIntent,
    intent_result: rpki_models.ROAIntentResult | None,
    reconciliation_run: rpki_models.ROAReconciliationRun | None,
) -> tuple[str, str, str]:
    if reconciliation_run is None:
        return RUN_STATE_UNRECONCILED, DRIFT_STATE_UNKNOWN, ''
    if reconciliation_run.status == rpki_models.ValidationRunStatus.FAILED:
        return RUN_STATE_RECONCILIATION_FAILED, DRIFT_STATE_UNKNOWN, ''
    if intent_result is None:
        return RUN_STATE_UNRECONCILED, DRIFT_STATE_UNKNOWN, ''

    drift_state = DRIFT_STATE_BY_RESULT_TYPE.get(intent_result.result_type, DRIFT_STATE_UNKNOWN)
    if intent_result.result_type == rpki_models.ROAIntentResultType.MATCH:
        run_state = RUN_STATE_RECONCILED_CURRENT
    else:
        run_state = RUN_STATE_RECONCILED_WITH_DRIFT
    return run_state, drift_state, intent_result.severity.lower()


def detect_prefix_overlaps(rows: list[RoaAuthorityMapRow]) -> dict[str, list[str]]:
    profiles_by_prefix: dict[str, list[RoaAuthorityMapRow]] = defaultdict(list)
    for row in rows:
        profiles_by_prefix[row.prefix_cidr_text].append(row)

    overlaps: dict[str, list[str]] = {}
    for same_prefix_rows in profiles_by_prefix.values():
        profile_names = {row.intent_profile.name for row in same_prefix_rows}
        if len(profile_names) < 2:
            continue
        for row in same_prefix_rows:
            other_profiles = sorted(name for name in profile_names if name != row.intent_profile.name)
            if other_profiles:
                overlaps[row.authority_key] = other_profiles
    return overlaps


def build_subject_label(intent: rpki_models.ROAIntent) -> str:
    if intent.is_as0:
        return f'{intent.prefix_cidr_text} -> AS0'
    asn_text = f'AS{intent.origin_asn_value}' if intent.origin_asn_value is not None else 'AS?'
    max_length_text = f' /{intent.max_length}' if intent.max_length is not None else ''
    return f'{intent.prefix_cidr_text} -> {asn_text}{max_length_text}'


def parse_summary_json(
    summary_json: dict,
    *,
    bindings_by_id: dict[int, rpki_models.RoutingIntentTemplateBinding],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], str]:
    summary = summary_json or {}
    profile_context_group_names = tuple(summary.get('profile_context_group_names') or ())
    binding_context_groups = summary.get('binding_context_groups') or {}
    binding_context_group_names = tuple(
        group_name
        for group_names in binding_context_groups.values()
        for group_name in group_names
    )
    template_binding_names = []
    binding_states = []
    for binding_id_text in binding_context_groups.keys():
        try:
            binding_id = int(binding_id_text)
        except (TypeError, ValueError):
            continue
        binding = bindings_by_id.get(binding_id)
        if binding is None:
            continue
        template_binding_names.append(binding.name)
        binding_states.append(binding.state)
    binding_freshness = ''
    if binding_states:
        for candidate in (
            rpki_models.RoutingIntentTemplateBindingState.INVALID,
            rpki_models.RoutingIntentTemplateBindingState.STALE,
            rpki_models.RoutingIntentTemplateBindingState.PENDING,
            rpki_models.RoutingIntentTemplateBindingState.CURRENT,
        ):
            if candidate in binding_states:
                binding_freshness = candidate
                break
    return (
        tuple(template_binding_names),
        profile_context_group_names,
        binding_context_group_names,
        binding_freshness,
    )


def build_authority_reason_summary(intent: rpki_models.ROAIntent) -> str:
    parts = []
    if intent.explanation:
        parts.append(Truncator(intent.explanation).chars(120))
    if intent.applied_override is not None:
        parts.append(f'Override: {intent.applied_override.name}')
    if intent.source_rule is not None:
        parts.append(f'Rule: {intent.source_rule.name}')
    return ' '.join(part for part in parts if part)


def build_reconciliation_summary(
    intent_result: rpki_models.ROAIntentResult | None,
    reconciliation_run: rpki_models.ROAReconciliationRun | None = None,
) -> str:
    if reconciliation_run is not None and reconciliation_run.status == rpki_models.ValidationRunStatus.FAILED:
        return 'Reconciliation failed'
    if intent_result is None:
        return 'Not reconciled'

    details = dict(intent_result.details_json or {})
    if intent_result.result_type == rpki_models.ROAIntentResultType.MATCH:
        return 'Match'
    if intent_result.result_type == rpki_models.ROAIntentResultType.MISSING:
        return 'Missing - no runtime ROA'
    if intent_result.result_type == rpki_models.ROAIntentResultType.ASN_MISMATCH:
        expected = details.get('intent_origin_asn') or details.get('expected_origin_asn')
        found = details.get('published_origin_asn') or details.get('runtime_origin_asn')
        if expected or found:
            return f'ASN mismatch (expected {expected}, found {found})'
        return 'ASN mismatch'
    if intent_result.result_type == rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD:
        return 'maxLength overbroad'
    if intent_result.result_type == rpki_models.ROAIntentResultType.MAX_LENGTH_TOO_NARROW:
        return 'maxLength too narrow'
    if intent_result.result_type == rpki_models.ROAIntentResultType.PREFIX_MISMATCH:
        return 'Prefix mismatch'
    if intent_result.result_type == rpki_models.ROAIntentResultType.STALE:
        return 'Evidence stale'
    if intent_result.result_type == rpki_models.ROAIntentResultType.INACTIVE_INTENT:
        return 'Inactive intent'
    if intent_result.result_type == rpki_models.ROAIntentResultType.SUPPRESSED_BY_POLICY:
        return 'Suppressed by policy'
    return intent_result.get_result_type_display()


def build_publication_summary(change_plan: rpki_models.ROAChangePlan | None) -> str:
    if change_plan is None:
        return 'No plan'
    status = str(change_plan.status).upper()
    if (
        change_plan.status == rpki_models.ROAChangePlanStatus.APPLIED
        and change_plan.applied_at is not None
    ):
        return f'Plan: {status} {change_plan.applied_at.date().isoformat()}'
    if (
        change_plan.status == rpki_models.ROAChangePlanStatus.APPROVED
        and change_plan.requires_secondary_approval
    ):
        return 'Plan: APPROVED (dual-approval)'
    return f'Plan: {status}'


def _bulk_parse_summary_json(
    intents: list[rpki_models.ROAIntent],
) -> dict[int, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], str]]:
    binding_ids = set()
    for intent in intents:
        binding_context_groups = (intent.summary_json or {}).get('binding_context_groups') or {}
        for binding_id_text in binding_context_groups.keys():
            try:
                binding_ids.add(int(binding_id_text))
            except (TypeError, ValueError):
                continue
    bindings_by_id = {
        binding.pk: binding
        for binding in rpki_models.RoutingIntentTemplateBinding.objects.filter(pk__in=binding_ids)
    }
    return {
        intent.pk: parse_summary_json(intent.summary_json or {}, bindings_by_id=bindings_by_id)
        for intent in intents
    }
