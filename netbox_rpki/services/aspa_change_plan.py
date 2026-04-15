from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from django.utils import timezone

from netbox_rpki import models as rpki_models


class ASPAChangePlanExecutionError(ValueError):
    pass


@dataclass(frozen=True)
class AspaSubjectState:
    source_kind: str
    source_key: str
    source_name: str
    customer_asn: int | None
    customer_display: str
    provider_asns: tuple[int, ...]
    provider_rows: tuple[dict, ...]
    stale: bool
    aspa: object | None = None
    imported_aspa: object | None = None


def _asn_value(value) -> int | None:
    if value is None:
        return None
    if hasattr(value, 'asn'):
        return getattr(value, 'asn', None)
    return value


def _customer_asn_value(subject) -> int | None:
    return _asn_value(getattr(subject, 'customer_as', None) or getattr(subject, 'customer_asn', None))


def _provider_asn_value(row) -> int | None:
    return _asn_value(getattr(row, 'provider_as', None) or getattr(row, 'provider_asn', None))


def _provider_rows(subject) -> list[object]:
    manager = getattr(subject, 'provider_authorizations', None)
    if manager is None:
        return []
    return list(manager.all())


def _provider_values(rows: list[object]) -> tuple[int, ...]:
    return tuple(sorted({value for value in (_provider_asn_value(row) for row in rows) if value is not None}))


def _provider_row_payload(row) -> dict:
    provider_value = _provider_asn_value(row)
    return {
        'asn': provider_value,
        'address_family': getattr(row, 'address_family', '') or '',
        'raw_provider_text': getattr(row, 'raw_provider_text', '') or '',
    }


def _customer_display(customer_asn: int | None) -> str:
    if customer_asn is None:
        return 'Unknown customer'
    return f'AS{customer_asn}'


def _is_stale_local_aspa(aspa) -> bool:
    validation_state = getattr(aspa, 'validation_state', '')
    if validation_state == rpki_models.ValidationState.STALE:
        return True
    valid_to = getattr(aspa, 'valid_to', None)
    if valid_to is None:
        return False
    return valid_to < timezone.now().date()


def _serialize_state(subject_state: AspaSubjectState | None) -> dict:
    if subject_state is None:
        return {}
    source_obj = subject_state.aspa or subject_state.imported_aspa
    return {
        'customer_asn': subject_state.customer_asn,
        'customer_display': subject_state.customer_display,
        'provider_asns': list(subject_state.provider_asns),
        'provider_rows': list(subject_state.provider_rows),
        'source_kind': subject_state.source_kind,
        'source_id': getattr(source_obj, 'pk', None),
        'source_name': subject_state.source_name,
        'stale': subject_state.stale,
    }


def _delegated_scope_summary_for_intent(intent) -> dict:
    managed_relationship = getattr(intent, 'managed_relationship', None)
    delegated_entity = getattr(intent, 'delegated_entity', None)
    provider_account = getattr(managed_relationship, 'provider_account', None)
    return {
        'ownership_scope': (
            'managed_relationship'
            if getattr(intent, 'managed_relationship_id', None) is not None
            else 'delegated_entity'
            if getattr(intent, 'delegated_entity_id', None) is not None
            else 'organization'
        ),
        'delegated_entity_id': getattr(delegated_entity, 'pk', None),
        'delegated_entity_name': getattr(delegated_entity, 'name', ''),
        'managed_relationship_id': getattr(managed_relationship, 'pk', None),
        'managed_relationship_name': getattr(managed_relationship, 'name', ''),
        'provider_account_id': getattr(provider_account, 'pk', None),
        'provider_account_name': getattr(provider_account, 'name', ''),
    }


def _delegated_scope_signature(summary: dict) -> tuple:
    return (
        summary.get('ownership_scope') or 'organization',
        summary.get('delegated_entity_id'),
        summary.get('managed_relationship_id'),
    )


def _resolve_plan_delegated_scope(scope_summaries: list[dict]) -> tuple[object | None, object | None, str]:
    non_org_summaries = [
        summary
        for summary in scope_summaries
        if summary and summary.get('ownership_scope') not in (None, '', 'organization')
    ]
    if not non_org_summaries:
        return None, None, 'organization_only'

    distinct_signatures = {
        _delegated_scope_signature(summary)
        for summary in non_org_summaries
    }
    if len(distinct_signatures) > 1:
        return None, None, 'mixed'

    summary = non_org_summaries[0]
    managed_relationship_id = summary.get('managed_relationship_id')
    delegated_entity_id = summary.get('delegated_entity_id')
    if managed_relationship_id is not None:
        managed_relationship = rpki_models.ManagedAuthorizationRelationship.objects.get(pk=managed_relationship_id)
        return managed_relationship.delegated_entity, managed_relationship, 'managed_relationship'
    if delegated_entity_id is not None:
        delegated_entity = rpki_models.DelegatedAuthorizationEntity.objects.get(pk=delegated_entity_id)
        return delegated_entity, None, 'delegated_entity'
    return None, None, 'organization_only'


def _serialize_target_state(
    customer_asn: int,
    provider_asns: tuple[int, ...],
    *,
    delegated_scope: dict | None = None,
    delegated_scope_candidates: list[dict] | None = None,
) -> dict:
    payload = {
        'customer_asn': customer_asn,
        'customer_display': _customer_display(customer_asn),
        'provider_asns': list(provider_asns),
        'provider_rows': [
            {
                'asn': provider_asn,
                'address_family': '',
                'raw_provider_text': '',
            }
            for provider_asn in provider_asns
        ],
        'source_kind': 'intent_target',
        'source_id': None,
        'source_name': f'Desired ASPA for AS{customer_asn}',
        'stale': False,
    }
    if delegated_scope:
        payload['delegated_scope'] = delegated_scope
    if delegated_scope_candidates:
        payload['delegated_scope_candidates'] = delegated_scope_candidates
    return payload


def _serialize_provider_payload(customer_asn: int, provider_asns: tuple[int, ...]) -> dict:
    return {
        'customer_asn': customer_asn,
        'customer': _customer_display(customer_asn),
        'providers': [f'AS{provider_asn}' for provider_asn in provider_asns],
        'provider_asns': list(provider_asns),
    }


def _load_expected_provider_sets(
    reconciliation_run,
) -> tuple[dict[int, tuple[int, ...]], dict[int, dict], dict[int, list[dict]], set[int]]:
    provider_sets: dict[int, set[int]] = defaultdict(set)
    delegated_scope_by_customer: dict[int, dict] = {}
    delegated_scope_candidates_by_customer: dict[int, list[dict]] = defaultdict(list)
    conflicting_customers: set[int] = set()
    intents = (
        rpki_models.ASPAIntent.objects
        .filter(organization=reconciliation_run.organization)
        .select_related('customer_as', 'provider_as', 'delegated_entity', 'managed_relationship__provider_account')
        .order_by('customer_as__asn', 'provider_as__asn', 'pk')
    )
    for intent in intents:
        customer_asn = _customer_asn_value(intent)
        provider_asn = _provider_asn_value(intent)
        if customer_asn is None or provider_asn is None:
            continue
        provider_sets[customer_asn].add(provider_asn)
        delegated_scope = _delegated_scope_summary_for_intent(intent)
        existing = delegated_scope_by_customer.get(customer_asn)
        if existing is None:
            delegated_scope_by_customer[customer_asn] = delegated_scope
            delegated_scope_candidates_by_customer[customer_asn].append(delegated_scope)
        elif _delegated_scope_signature(existing) != _delegated_scope_signature(delegated_scope):
            conflicting_customers.add(customer_asn)
            candidate_signatures = {
                _delegated_scope_signature(candidate)
                for candidate in delegated_scope_candidates_by_customer[customer_asn]
            }
            if _delegated_scope_signature(delegated_scope) not in candidate_signatures:
                delegated_scope_candidates_by_customer[customer_asn].append(delegated_scope)
    return (
        {customer_asn: tuple(sorted(provider_asns)) for customer_asn, provider_asns in provider_sets.items()},
        delegated_scope_by_customer,
        {customer_asn: list(candidates) for customer_asn, candidates in delegated_scope_candidates_by_customer.items()},
        conflicting_customers,
    )


def _load_observed_states(reconciliation_run) -> dict[int, list[AspaSubjectState]]:
    observed: dict[int, list[AspaSubjectState]] = defaultdict(list)
    if reconciliation_run.comparison_scope == rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED:
        if reconciliation_run.provider_snapshot_id is None:
            raise ASPAChangePlanExecutionError(
                'Provider-imported ASPA reconciliation runs must reference a provider snapshot.'
            )
        queryset = (
            rpki_models.ImportedAspa.objects
            .filter(provider_snapshot=reconciliation_run.provider_snapshot)
            .select_related('customer_as')
            .prefetch_related('provider_authorizations__provider_as')
            .order_by('name', 'pk')
        )
        for imported_aspa in queryset:
            customer_asn = _customer_asn_value(imported_aspa)
            if customer_asn is None:
                continue
            rows = _provider_rows(imported_aspa)
            observed[customer_asn].append(
                AspaSubjectState(
                    source_kind='imported_aspa',
                    source_key=f'imported:{imported_aspa.pk}',
                    source_name=imported_aspa.name,
                    customer_asn=customer_asn,
                    customer_display=_customer_display(customer_asn),
                    provider_asns=_provider_values(rows),
                    provider_rows=tuple(_provider_row_payload(row) for row in rows),
                    stale=bool(imported_aspa.is_stale),
                    imported_aspa=imported_aspa,
                    aspa=None,
                )
            )
    else:
        queryset = (
            rpki_models.ASPA.objects
            .filter(organization=reconciliation_run.organization)
            .select_related('customer_as')
            .prefetch_related('provider_authorizations__provider_as')
            .order_by('name', 'pk')
        )
        for aspa in queryset:
            customer_asn = _customer_asn_value(aspa)
            if customer_asn is None:
                continue
            rows = _provider_rows(aspa)
            observed[customer_asn].append(
                AspaSubjectState(
                    source_kind='local_aspa',
                    source_key=f'aspa:{aspa.pk}',
                    source_name=aspa.name,
                    customer_asn=customer_asn,
                    customer_display=_customer_display(customer_asn),
                    provider_asns=_provider_values(rows),
                    provider_rows=tuple(_provider_row_payload(row) for row in rows),
                    stale=_is_stale_local_aspa(aspa),
                    imported_aspa=None,
                    aspa=aspa,
                )
            )
    return observed


def _best_observed_state(expected_provider_asns: tuple[int, ...], candidates: list[AspaSubjectState]) -> AspaSubjectState | None:
    if not candidates:
        return None
    expected_set = set(expected_provider_asns)
    return sorted(
        candidates,
        key=lambda state: (
            0 if set(state.provider_asns) == expected_set else 1,
            0 if not state.stale else 1,
            abs(len(state.provider_asns) - len(expected_set)),
            state.source_key,
        ),
    )[0]


def create_aspa_change_plan(
    reconciliation_run: rpki_models.ASPAReconciliationRun,
    *,
    name: str | None = None,
) -> rpki_models.ASPAChangePlan:
    if reconciliation_run.status != rpki_models.ValidationRunStatus.COMPLETED:
        raise ASPAChangePlanExecutionError(
            'ASPA change plans can only be created from completed reconciliation runs.'
        )

    now = timezone.now()
    provider_snapshot = None
    provider_account = None
    if reconciliation_run.comparison_scope == rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED:
        provider_snapshot = reconciliation_run.provider_snapshot
        if provider_snapshot is None:
            raise ASPAChangePlanExecutionError(
                'Provider-imported ASPA reconciliation runs must reference a provider snapshot.'
            )
        provider_account = provider_snapshot.provider_account
        if provider_account is None:
            raise ASPAChangePlanExecutionError(
                'Provider-imported ASPA reconciliation runs must reference a provider account.'
            )

    plan = rpki_models.ASPAChangePlan.objects.create(
        name=name or f'{reconciliation_run.name} Change Plan {now:%Y-%m-%d %H:%M:%S}',
        organization=reconciliation_run.organization,
        source_reconciliation_run=reconciliation_run,
        provider_account=provider_account,
        provider_snapshot=provider_snapshot,
        tenant=reconciliation_run.tenant,
        status=rpki_models.ASPAChangePlanStatus.DRAFT,
    )

    (
        expected_provider_sets,
        delegated_scope_by_customer,
        delegated_scope_candidates_by_customer,
        conflicting_customers,
    ) = _load_expected_provider_sets(reconciliation_run)
    observed_states = _load_observed_states(reconciliation_run)

    create_count = 0
    withdraw_count = 0
    replacement_count = 0
    provider_add_count = 0
    provider_remove_count = 0
    plan_semantic_counts: Counter[str] = Counter()
    skipped_counts: Counter[str] = Counter()
    delegated_scoped_item_count = 0
    plan_scope_summaries: list[dict] = []

    for customer_asn in sorted(set(expected_provider_sets) | set(observed_states)):
        expected_provider_asns = expected_provider_sets.get(customer_asn, ())
        observed_state = _best_observed_state(expected_provider_asns, observed_states.get(customer_asn, []))
        observed_provider_asns = observed_state.provider_asns if observed_state is not None else ()
        expected_set = set(expected_provider_asns)
        observed_set = set(observed_provider_asns)
        delegated_scope = delegated_scope_by_customer.get(customer_asn)
        delegated_scope_candidates = delegated_scope_candidates_by_customer.get(customer_asn, [])
        target_state_json = (
            _serialize_target_state(
                customer_asn,
                expected_provider_asns,
                delegated_scope=delegated_scope,
                delegated_scope_candidates=delegated_scope_candidates if len(delegated_scope_candidates) > 1 else None,
            )
            if expected_provider_asns else {}
        )
        observed_state_json = _serialize_state(observed_state)

        if customer_asn in conflicting_customers:
            skipped_counts['ownership_scope_conflict'] += 1
            continue

        if expected_provider_asns and observed_state is None:
            rpki_models.ASPAChangePlanItem.objects.create(
                name=f'Create ASPA for AS{customer_asn}',
                change_plan=plan,
                tenant=plan.tenant,
                action_type=rpki_models.ASPAChangePlanAction.CREATE,
                plan_semantic=rpki_models.ASPAChangePlanItemSemantic.CREATE,
                aspa_intent=(
                    rpki_models.ASPAIntent.objects
                    .filter(organization=plan.organization, customer_as__asn=customer_asn)
                    .order_by('provider_as__asn', 'pk')
                    .first()
                ),
                provider_operation=(
                    rpki_models.ProviderWriteOperation.ADD_PROVIDER_SET
                    if provider_account is not None
                    else ''
                ),
                provider_payload_json=(
                    _serialize_provider_payload(customer_asn, expected_provider_asns)
                    if provider_account is not None
                    else {}
                ),
                after_state_json=target_state_json,
                reason='Active ASPA intent exists but no published ASPA was observed for this customer ASN.',
            )
            create_count += 1
            if delegated_scope and delegated_scope.get('ownership_scope') != 'organization':
                delegated_scoped_item_count += 1
                plan_scope_summaries.append(delegated_scope)
            plan_semantic_counts[rpki_models.ASPAChangePlanItemSemantic.CREATE] += 1
            continue

        if observed_state is not None and not expected_provider_asns:
            rpki_models.ASPAChangePlanItem.objects.create(
                name=f'Withdraw ASPA for AS{customer_asn}',
                change_plan=plan,
                tenant=plan.tenant,
                action_type=rpki_models.ASPAChangePlanAction.WITHDRAW,
                plan_semantic=rpki_models.ASPAChangePlanItemSemantic.WITHDRAW,
                aspa=observed_state.aspa,
                imported_aspa=observed_state.imported_aspa,
                provider_operation=(
                    rpki_models.ProviderWriteOperation.REMOVE_PROVIDER_SET
                    if provider_account is not None
                    else ''
                ),
                provider_payload_json=(
                    _serialize_provider_payload(customer_asn, observed_state.provider_asns)
                    if provider_account is not None
                    else {}
                ),
                before_state_json=observed_state_json,
                reason='Published ASPA is orphaned relative to current ASPA intent.',
            )
            withdraw_count += 1
            plan_semantic_counts[rpki_models.ASPAChangePlanItemSemantic.WITHDRAW] += 1
            continue

        added_provider_asns = tuple(sorted(expected_set - observed_set))
        removed_provider_asns = tuple(sorted(observed_set - expected_set))
        if not added_provider_asns and not removed_provider_asns and not getattr(observed_state, 'stale', False):
            skipped_counts['match'] += 1
            continue

        anchor_semantic = (
            rpki_models.ASPAChangePlanItemSemantic.REPLACE
            if observed_state is not None and observed_state.stale
            else rpki_models.ASPAChangePlanItemSemantic.RESHAPE
        )
        anchor_reason = (
            'Observed ASPA is stale and should be replaced with the current intended provider set.'
            if observed_state is not None and observed_state.stale
            else 'Published ASPA provider set differs from the current intended provider set.'
        )
        rpki_models.ASPAChangePlanItem.objects.create(
            name=f'{"Replace" if anchor_semantic == rpki_models.ASPAChangePlanItemSemantic.REPLACE else "Reshape"} ASPA for AS{customer_asn}',
            change_plan=plan,
            tenant=plan.tenant,
            action_type=rpki_models.ASPAChangePlanAction.CREATE,
            plan_semantic=anchor_semantic,
            aspa_intent=(
                rpki_models.ASPAIntent.objects
                .filter(organization=plan.organization, customer_as__asn=customer_asn)
                .order_by('provider_as__asn', 'pk')
                .first()
            ),
            aspa=observed_state.aspa if observed_state is not None else None,
            imported_aspa=observed_state.imported_aspa if observed_state is not None else None,
            provider_operation=(
                rpki_models.ProviderWriteOperation.ADD_PROVIDER_SET
                if provider_account is not None
                else ''
            ),
            provider_payload_json=(
                _serialize_provider_payload(customer_asn, expected_provider_asns)
                if provider_account is not None
                else {}
            ),
            before_state_json=observed_state_json,
            after_state_json=target_state_json,
            reason=anchor_reason,
        )
        if anchor_semantic == rpki_models.ASPAChangePlanItemSemantic.REPLACE:
            replacement_count += 1
        if delegated_scope and delegated_scope.get('ownership_scope') != 'organization':
            delegated_scoped_item_count += 1
            plan_scope_summaries.append(delegated_scope)
        plan_semantic_counts[anchor_semantic] += 1

        for provider_asn in added_provider_asns:
            rpki_models.ASPAChangePlanItem.objects.create(
                name=f'Add provider AS{provider_asn} to AS{customer_asn}',
                change_plan=plan,
                tenant=plan.tenant,
                action_type=rpki_models.ASPAChangePlanAction.CREATE,
                plan_semantic=rpki_models.ASPAChangePlanItemSemantic.ADD_PROVIDER,
                aspa_intent=(
                    rpki_models.ASPAIntent.objects
                    .filter(organization=plan.organization, customer_as__asn=customer_asn, provider_as__asn=provider_asn)
                    .first()
                ),
                aspa=observed_state.aspa if observed_state is not None else None,
                imported_aspa=observed_state.imported_aspa if observed_state is not None else None,
                provider_operation=(
                    rpki_models.ProviderWriteOperation.ADD_PROVIDER_SET
                    if provider_account is not None
                    else ''
                ),
                provider_payload_json=(
                    _serialize_provider_payload(customer_asn, (provider_asn,))
                    if provider_account is not None
                    else {}
                ),
                before_state_json=observed_state_json,
                after_state_json=target_state_json,
                reason=f'Provider AS{provider_asn} is required by intent but missing from the published ASPA.',
            )
            provider_add_count += 1
            if delegated_scope and delegated_scope.get('ownership_scope') != 'organization':
                delegated_scoped_item_count += 1
                plan_scope_summaries.append(delegated_scope)
            plan_semantic_counts[rpki_models.ASPAChangePlanItemSemantic.ADD_PROVIDER] += 1

        for provider_asn in removed_provider_asns:
            rpki_models.ASPAChangePlanItem.objects.create(
                name=f'Remove provider AS{provider_asn} from AS{customer_asn}',
                change_plan=plan,
                tenant=plan.tenant,
                action_type=rpki_models.ASPAChangePlanAction.WITHDRAW,
                plan_semantic=rpki_models.ASPAChangePlanItemSemantic.REMOVE_PROVIDER,
                aspa=observed_state.aspa if observed_state is not None else None,
                imported_aspa=observed_state.imported_aspa if observed_state is not None else None,
                provider_operation=(
                    rpki_models.ProviderWriteOperation.REMOVE_PROVIDER_SET
                    if provider_account is not None
                    else ''
                ),
                provider_payload_json=(
                    _serialize_provider_payload(customer_asn, (provider_asn,))
                    if provider_account is not None
                    else {}
                ),
                before_state_json=observed_state_json,
                after_state_json=target_state_json,
                reason=f'Provider AS{provider_asn} is present in the published ASPA but no longer required by intent.',
            )
            provider_remove_count += 1
            if delegated_scope and delegated_scope.get('ownership_scope') != 'organization':
                delegated_scoped_item_count += 1
                plan_scope_summaries.append(delegated_scope)
            plan_semantic_counts[rpki_models.ASPAChangePlanItemSemantic.REMOVE_PROVIDER] += 1

    plan.summary_json = {
        'create_count': create_count,
        'withdraw_count': withdraw_count,
        'replacement_count': replacement_count,
        'provider_add_count': provider_add_count,
        'provider_remove_count': provider_remove_count,
        'provider_backed': provider_account is not None,
        'provider_account_id': getattr(provider_account, 'pk', None),
        'provider_snapshot_id': getattr(provider_snapshot, 'pk', None),
        'comparison_scope': reconciliation_run.comparison_scope,
        'plan_semantic_counts': dict(plan_semantic_counts),
        'skipped_counts': dict(skipped_counts),
        'delegated_scoped_item_count': delegated_scoped_item_count,
        'ownership_scope_conflict_customer_count': len(conflicting_customers),
        'ownership_scope_conflict_customer_asns': sorted(conflicting_customers),
    }
    delegated_entity, managed_relationship, delegated_scope_status = _resolve_plan_delegated_scope(plan_scope_summaries)
    plan.delegated_entity = delegated_entity
    plan.managed_relationship = managed_relationship
    plan.summary_json['delegated_scope_status'] = delegated_scope_status
    plan.summary_json['delegated_entity_id'] = getattr(delegated_entity, 'pk', None)
    plan.summary_json['managed_relationship_id'] = getattr(managed_relationship, 'pk', None)
    plan.save(update_fields=('delegated_entity', 'managed_relationship', 'summary_json'))
    return plan
