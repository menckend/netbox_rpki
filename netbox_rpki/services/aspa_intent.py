from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.external_management import (
    list_active_external_management_exceptions,
    match_aspa_intent_exception,
    match_published_aspa_exception,
)


ASPA_COMPARISON_SCOPE_LOCAL = 'local_aspa_records'
ASPA_COMPARISON_SCOPE_IMPORTED = 'provider_imported'

ASPA_INTENT_RESULT_MATCH = 'match'
ASPA_INTENT_RESULT_MISSING = 'missing'
ASPA_INTENT_RESULT_MISSING_PROVIDER = 'missing_provider'
ASPA_INTENT_RESULT_STALE = 'stale'

ASPA_PUBLISHED_RESULT_MATCH = 'matched'
ASPA_PUBLISHED_RESULT_ORPHANED = 'orphaned'
ASPA_PUBLISHED_RESULT_EXTRA_PROVIDER = 'extra_provider'
ASPA_PUBLISHED_RESULT_MISSING_PROVIDER = 'missing_provider'
ASPA_PUBLISHED_RESULT_STALE = 'stale'

ASPA_SEVERITY_INFO = 'info'
ASPA_SEVERITY_WARNING = 'warning'
ASPA_SEVERITY_ERROR = 'error'


class ASPAReconciliationExecutionError(ValueError):
    pass


@dataclass(frozen=True)
class PublishedAspaRecord:
    source_key: str
    source_name: str
    aspa: object | None
    imported_aspa: object | None
    customer_asn_value: int | None
    provider_values: tuple[int, ...]
    provider_objects: tuple[object, ...]
    stale: bool


def _model_class(model_name: str):
    model = getattr(rpki_models, model_name, None)
    if model is None:
        raise ASPAReconciliationExecutionError(f'{model_name} is not available in the current schema.')
    return model


@lru_cache(maxsize=None)
def _model_field_names(model_name: str) -> frozenset[str]:
    model = _model_class(model_name)
    return frozenset(
        field.name
        for field in model._meta.get_fields()
        if getattr(field, 'concrete', False) and not getattr(field, 'auto_created', False)
    )


def _create_record(model_name: str, **values):
    model = _model_class(model_name)
    allowed = _model_field_names(model_name)
    payload = {key: value for key, value in values.items() if key in allowed}
    return model.objects.create(**payload)


def _field_value(instance, *names, default=None):
    for name in names:
        if hasattr(instance, name):
            value = getattr(instance, name)
            if value is not None:
                return value
    return default


def _asn_value(value) -> int | None:
    if value is None:
        return None
    if hasattr(value, 'asn'):
        return getattr(value, 'asn', None)
    return value


def _customer_asn_value(row) -> int | None:
    return _asn_value(_field_value(row, 'customer_asn', 'customer_as'))


def _provider_asn_value(row) -> int | None:
    return _asn_value(_field_value(row, 'provider_asn', 'provider_as'))


def _intent_customer_asn_value(intent) -> int | None:
    return _asn_value(_field_value(intent, 'customer_asn', 'customer_as'))


def _intent_provider_asn_value(intent) -> int | None:
    return _asn_value(_field_value(intent, 'provider_asn', 'provider_as'))


def _intent_is_active(intent) -> bool:
    value = _field_value(intent, 'is_active', 'enabled', default=True)
    return bool(value)


def _intent_delegated_scope(intent) -> dict:
    managed_relationship = _field_value(intent, 'managed_relationship')
    delegated_entity = _field_value(intent, 'delegated_entity')
    provider_account = _field_value(managed_relationship, 'provider_account')
    return {
        'ownership_scope': (
            'managed_relationship'
            if _field_value(intent, 'managed_relationship_id') is not None
            else 'delegated_entity'
            if _field_value(intent, 'delegated_entity_id') is not None
            else 'organization'
        ),
        'delegated_entity_id': _field_value(delegated_entity, 'pk'),
        'delegated_entity_name': _field_value(delegated_entity, 'name', default=''),
        'managed_relationship_id': _field_value(managed_relationship, 'pk'),
        'managed_relationship_name': _field_value(managed_relationship, 'name', default=''),
        'provider_account_id': _field_value(provider_account, 'pk'),
        'provider_account_name': _field_value(provider_account, 'name', default=''),
    }


def _delegated_scope_signature(summary: dict) -> tuple:
    return (
        summary.get('ownership_scope') or 'organization',
        summary.get('delegated_entity_id'),
        summary.get('managed_relationship_id'),
    )


def _provider_rows(aspa) -> list[object]:
    manager = getattr(aspa, 'provider_authorizations', None)
    if manager is None:
        return []
    return list(manager.all())


def _provider_values(rows: list[object]) -> tuple[int, ...]:
    values = sorted({value for value in (_provider_asn_value(row) for row in rows) if value is not None})
    return tuple(values)


def _is_stale_local_aspa(aspa) -> bool:
    validation_state = _field_value(aspa, 'validation_state')
    if validation_state == getattr(rpki_models.ValidationState, 'STALE', 'stale'):
        return True

    valid_to = _field_value(aspa, 'valid_to')
    if valid_to is None:
        return False
    return valid_to < timezone.now().date()


def _is_stale_imported_aspa(imported_aspa) -> bool:
    return bool(_field_value(imported_aspa, 'is_stale', default=False))


def _resolve_organization(scope_owner):
    organization_model = _model_class('Organization')
    if isinstance(scope_owner, organization_model):
        return scope_owner
    organization = _field_value(scope_owner, 'organization')
    if isinstance(organization, organization_model):
        return organization
    return None


def _resolve_provider_snapshot(intent_profile, provider_snapshot):
    provider_snapshot_model = _model_class('ProviderSnapshot')
    organization = _resolve_organization(intent_profile)
    if organization is None:
        raise ASPAReconciliationExecutionError('ASPA reconciliation requires an organization context.')

    if isinstance(provider_snapshot, provider_snapshot_model):
        return provider_snapshot
    if provider_snapshot is not None:
        return provider_snapshot_model.objects.get(pk=provider_snapshot, organization=organization)

    snapshot = (
        organization.provider_snapshots
        .filter(status=getattr(rpki_models.ValidationRunStatus, 'COMPLETED', 'completed'))
        .order_by('-completed_at', '-fetched_at', '-pk')
        .first()
    )
    if snapshot is None:
        raise ASPAReconciliationExecutionError(
            f'No completed provider snapshot is available for organization {organization.name}.'
        )
    return snapshot


def _intent_queryset(intent_profile):
    intent_model = _model_class('ASPAIntent')
    organization = _resolve_organization(intent_profile)
    if organization is None:
        raise ASPAReconciliationExecutionError('ASPA reconciliation requires an organization context.')

    queryset = intent_model.objects.filter(organization=organization).select_related(
        'customer_as',
        'provider_as',
        'delegated_entity',
        'managed_relationship__provider_account',
    )
    if 'intent_profile' in _model_field_names('ASPAIntent'):
        queryset = queryset.filter(intent_profile=intent_profile)
    if 'is_active' in _model_field_names('ASPAIntent'):
        queryset = queryset.filter(is_active=True)
    return queryset


def _load_local_published_records(organization) -> dict[int | None, list[PublishedAspaRecord]]:
    aspa_model = _model_class('ASPA')
    published: dict[int | None, list[PublishedAspaRecord]] = defaultdict(list)
    queryset = aspa_model.objects.filter(organization=organization)
    for aspa in queryset.order_by('name', 'pk').prefetch_related('provider_authorizations'):
        customer_value = _customer_asn_value(aspa)
        provider_rows = tuple(_provider_rows(aspa))
        published[customer_value].append(
            PublishedAspaRecord(
                source_key=f'aspa:{aspa.pk}',
                source_name=aspa.name,
                aspa=aspa,
                imported_aspa=None,
                customer_asn_value=customer_value,
                provider_values=_provider_values(list(provider_rows)),
                provider_objects=provider_rows,
                stale=_is_stale_local_aspa(aspa),
            )
        )
    return published


def _load_imported_published_records(
    provider_snapshot,
) -> tuple[object, dict[int | None, list[PublishedAspaRecord]]]:
    imported_aspa_model = _model_class('ImportedAspa')
    snapshot = provider_snapshot
    published: dict[int | None, list[PublishedAspaRecord]] = defaultdict(list)
    rows = imported_aspa_model.objects.filter(provider_snapshot=snapshot).prefetch_related('provider_authorizations')
    for imported_aspa in rows.order_by('name', 'pk'):
        customer_value = _customer_asn_value(imported_aspa)
        provider_rows = tuple(_provider_rows(imported_aspa))
        published[customer_value].append(
            PublishedAspaRecord(
                source_key=f'imported:{imported_aspa.pk}',
                source_name=imported_aspa.name,
                aspa=None,
                imported_aspa=imported_aspa,
                customer_asn_value=customer_value,
                provider_values=_provider_values(list(provider_rows)),
                provider_objects=provider_rows,
                stale=_is_stale_imported_aspa(imported_aspa),
            )
        )
    return snapshot, published


def _published_records(
    intent_profile,
    comparison_scope: str,
    provider_snapshot=None,
) -> tuple[object | None, dict[int | None, list[PublishedAspaRecord]]]:
    organization = _resolve_organization(intent_profile)
    if organization is None:
        raise ASPAReconciliationExecutionError('ASPA reconciliation requires an organization context.')
    if comparison_scope == ASPA_COMPARISON_SCOPE_LOCAL:
        return None, _load_local_published_records(organization)
    if comparison_scope == ASPA_COMPARISON_SCOPE_IMPORTED:
        snapshot = _resolve_provider_snapshot(intent_profile, provider_snapshot)
        return _load_imported_published_records(snapshot)
    raise ASPAReconciliationExecutionError(
        f'Unsupported ASPA comparison scope: {comparison_scope!r}.'
    )


def _best_published_candidate(
    customer_candidates: list[PublishedAspaRecord],
    provider_value: int,
) -> PublishedAspaRecord | None:
    if not customer_candidates:
        return None

    def candidate_key(record: PublishedAspaRecord):
        provider_values = set(record.provider_values)
        contains_provider = provider_value in provider_values
        exact_provider_set = provider_values == {provider_value}
        return (
            0 if contains_provider else 1,
            0 if not record.stale else 1,
            0 if exact_provider_set else 1,
            abs(len(provider_values) - 1),
            len(provider_values),
            record.source_key,
        )

    return sorted(customer_candidates, key=candidate_key)[0]


def _intent_result_type_and_severity(
    customer_candidates: list[PublishedAspaRecord],
    provider_value: int,
) -> tuple[str, str, PublishedAspaRecord | None]:
    best_candidate = _best_published_candidate(customer_candidates, provider_value)
    if not customer_candidates:
        return ASPA_INTENT_RESULT_MISSING, ASPA_SEVERITY_ERROR, None
    matching_candidates = [record for record in customer_candidates if provider_value in record.provider_values]
    if matching_candidates:
        if all(record.stale for record in matching_candidates):
            return ASPA_INTENT_RESULT_STALE, ASPA_SEVERITY_WARNING, best_candidate
        return ASPA_INTENT_RESULT_MATCH, ASPA_SEVERITY_INFO, best_candidate
    return ASPA_INTENT_RESULT_MISSING_PROVIDER, ASPA_SEVERITY_ERROR, best_candidate


def _published_result_type_and_severity(
    desired_provider_values: set[int],
    published_record: PublishedAspaRecord,
) -> tuple[str, str, dict]:
    published_provider_values = set(published_record.provider_values)
    if not desired_provider_values:
        return (
            ASPA_PUBLISHED_RESULT_ORPHANED,
            ASPA_SEVERITY_WARNING,
            {
                'matched_intent_provider_values': [],
                'desired_provider_values': [],
                'published_provider_values': sorted(published_provider_values),
            },
        )
    if published_record.stale:
        return (
            ASPA_PUBLISHED_RESULT_STALE,
            ASPA_SEVERITY_WARNING,
            {
                'matched_intent_provider_values': sorted(desired_provider_values & published_provider_values),
                'desired_provider_values': sorted(desired_provider_values),
                'published_provider_values': sorted(published_provider_values),
            },
        )
    if published_provider_values == desired_provider_values:
        return (
            ASPA_PUBLISHED_RESULT_MATCH,
            ASPA_SEVERITY_INFO,
            {
                'matched_intent_provider_values': sorted(desired_provider_values),
                'desired_provider_values': sorted(desired_provider_values),
                'published_provider_values': sorted(published_provider_values),
            },
        )
    if published_provider_values - desired_provider_values:
        return (
            ASPA_PUBLISHED_RESULT_EXTRA_PROVIDER,
            ASPA_SEVERITY_WARNING,
            {
                'matched_intent_provider_values': sorted(desired_provider_values & published_provider_values),
                'desired_provider_values': sorted(desired_provider_values),
                'published_provider_values': sorted(published_provider_values),
            },
        )
    return (
        ASPA_PUBLISHED_RESULT_MISSING_PROVIDER,
        ASPA_SEVERITY_ERROR,
        {
            'matched_intent_provider_values': sorted(desired_provider_values & published_provider_values),
            'desired_provider_values': sorted(desired_provider_values),
            'published_provider_values': sorted(published_provider_values),
        },
    )


def _create_intent_match_record(
    reconciliation_run,
    intent,
    best_published: PublishedAspaRecord | None,
    result_type: str,
    severity: str,
    details_json: dict,
):
    match_model = getattr(rpki_models, 'ASPAIntentMatch', None)
    if match_model is None or best_published is None:
        return None

    payload = {
        'name': f'{getattr(intent, "name", "ASPA Intent")} Match',
        'aspa_intent': intent,
        'aspa': best_published.aspa,
        'imported_aspa': best_published.imported_aspa,
        'match_kind': {
            ASPA_INTENT_RESULT_MATCH: getattr(rpki_models.ASPAIntentMatchKind, 'EXACT', 'exact'),
            ASPA_INTENT_RESULT_STALE: getattr(rpki_models.ASPAIntentMatchKind, 'STALE_CANDIDATE', 'stale_candidate'),
            ASPA_INTENT_RESULT_MISSING_PROVIDER: getattr(rpki_models.ASPAIntentMatchKind, 'PROVIDER_MISMATCH', 'provider_mismatch'),
        }.get(result_type, getattr(rpki_models.ASPAIntentMatchKind, 'EXACT', 'exact')),
        'is_best_match': True,
        'details_json': {
            **details_json,
            'severity': severity,
            'best_published_source': best_published.source_key,
        },
    }

    allowed = _model_field_names('ASPAIntentMatch')
    create_payload = {key: value for key, value in payload.items() if key in allowed}
    try:
        return match_model.objects.create(**create_payload)
    except Exception:
        return None


def reconcile_aspa_intents(
    intent_profile,
    *,
    comparison_scope: str = ASPA_COMPARISON_SCOPE_LOCAL,
    provider_snapshot=None,
    run_name: str | None = None,
):
    now = timezone.now()
    snapshot, published_by_customer = _published_records(intent_profile, comparison_scope, provider_snapshot)
    organization = _resolve_organization(intent_profile)
    if organization is None:
        raise ASPAReconciliationExecutionError('ASPA reconciliation requires an organization context.')
    run_field_names = _model_field_names('ASPAReconciliationRun')
    run = _create_record(
        'ASPAReconciliationRun',
        name=run_name or f'{getattr(intent_profile, "name", organization.name)} ASPA Reconciliation {now:%Y-%m-%d %H:%M:%S}',
        organization=organization,
        provider_snapshot=snapshot,
        comparison_scope=comparison_scope,
        status=getattr(rpki_models.ValidationRunStatus, 'RUNNING', 'running'),
        started_at=now,
        completed_at=None,
        intent_count=0,
        published_aspa_count=0,
        result_summary_json={},
        summary_json={},
    )

    intent_result_counts: Counter[str] = Counter()
    published_result_counts: Counter[str] = Counter()
    active_intents = 0
    published_records_seen: set[str] = set()
    intent_records = list(_intent_queryset(intent_profile).order_by('pk'))
    external_management_exceptions = list_active_external_management_exceptions(organization)
    matched_external_intent_count = 0
    matched_external_published_count = 0
    matched_external_review_due_count = 0
    intent_provider_values_by_customer: dict[int | None, set[int]] = defaultdict(set)
    delegated_scope_counts: Counter[str] = Counter()
    customer_scope_signatures: dict[int | None, set[tuple]] = defaultdict(set)
    for intent in intent_records:
        customer_value = _intent_customer_asn_value(intent)
        provider_value = _intent_provider_asn_value(intent)
        if customer_value is None or provider_value is None:
            raise ASPAReconciliationExecutionError(
                'ASPA intents must resolve both customer ASN and provider ASN values.'
            )
        intent_provider_values_by_customer[customer_value].add(provider_value)
        delegated_scope = _intent_delegated_scope(intent)
        delegated_scope_counts[delegated_scope['ownership_scope']] += 1
        customer_scope_signatures[customer_value].add(_delegated_scope_signature(delegated_scope))

    ownership_scope_conflict_customer_asns = sorted(
        customer_value
        for customer_value, signatures in customer_scope_signatures.items()
        if customer_value is not None and len(signatures) > 1
    )

    for intent in intent_records:
        if not _intent_is_active(intent):
            continue
        active_intents += 1
        customer_value = _intent_customer_asn_value(intent)
        provider_value = _intent_provider_asn_value(intent)
        customer_candidates = published_by_customer.get(customer_value, [])
        result_type, severity, best_candidate = _intent_result_type_and_severity(customer_candidates, provider_value)
        intent_result_counts[result_type] += 1
        delegated_scope = _intent_delegated_scope(intent)
        details_json = {
            'comparison_scope': comparison_scope,
            'customer_asn_value': customer_value,
            'provider_asn_value': provider_value,
            'candidate_count': len(customer_candidates),
            'candidate_source_keys': [candidate.source_key for candidate in customer_candidates],
            'published_provider_values': sorted(
                {value for candidate in customer_candidates for value in candidate.provider_values}
            ),
            'best_published_source': getattr(best_candidate, 'source_key', None),
            'best_published_provider_values': list(getattr(best_candidate, 'provider_values', ())),
            'best_published_stale': getattr(best_candidate, 'stale', None),
            'delegated_scope': delegated_scope,
            'ownership_scope_conflict_for_customer': customer_value in ownership_scope_conflict_customer_asns,
        }
        external_management_exception = match_aspa_intent_exception(
            organization,
            customer_asn_value=customer_value,
            provider_asn_value=provider_value,
            exceptions=external_management_exceptions,
        )
        if external_management_exception:
            matched_external_intent_count += 1
            if external_management_exception.get('is_review_due'):
                matched_external_review_due_count += 1
            details_json['external_management_exception'] = external_management_exception
        result_kwargs = {
            'name': f'{getattr(intent, "name", "ASPA Intent")} Result',
            'reconciliation_run': run,
            'aspa_intent': intent,
            'result_type': result_type,
            'severity': severity,
            'best_aspa': getattr(best_candidate, 'aspa', None),
            'best_imported_aspa': getattr(best_candidate, 'imported_aspa', None),
            'match_count': len(customer_candidates),
            'details_json': details_json,
            'summary_json': details_json,
            'computed_at': now,
        }
        _create_record('ASPAIntentResult', **result_kwargs)
        _create_intent_match_record(run, intent, best_candidate, result_type, severity, details_json)

    for customer_value, published_rows in published_by_customer.items():
        desired_provider_values = intent_provider_values_by_customer.get(customer_value, set())
        for published_record in published_rows:
            published_records_seen.add(published_record.source_key)
            result_type, severity, details_json = _published_result_type_and_severity(
                desired_provider_values,
                published_record,
            )
            external_management_exception = match_published_aspa_exception(
                organization,
                aspa_id=getattr(published_record.aspa, 'pk', None),
                imported_aspa_id=getattr(published_record.imported_aspa, 'pk', None),
                customer_asn_value=customer_value,
                provider_values=tuple(published_record.provider_values),
                exceptions=external_management_exceptions,
            )
            if external_management_exception:
                matched_external_published_count += 1
                if external_management_exception.get('is_review_due'):
                    matched_external_review_due_count += 1
            published_result_counts[result_type] += 1
            _create_record(
                'PublishedASPAResult',
                name=f'{published_record.source_name} Published Result',
                reconciliation_run=run,
                aspa=published_record.aspa,
                imported_aspa=published_record.imported_aspa,
                result_type=result_type,
                severity=severity,
                matched_intent_count=len(desired_provider_values & set(published_record.provider_values)),
                details_json={
                    'comparison_scope': comparison_scope,
                    'customer_asn_value': customer_value,
                    'source_key': published_record.source_key,
                    'stale': published_record.stale,
                    'matched_intent_delegated_scopes': [
                        _intent_delegated_scope(intent)
                        for intent in intent_records
                        if _intent_is_active(intent) and _intent_customer_asn_value(intent) == customer_value
                    ],
                    'external_management_exception': external_management_exception,
                    **details_json,
                },
                summary_json={
                    'comparison_scope': comparison_scope,
                    'customer_asn_value': customer_value,
                    'source_key': published_record.source_key,
                    'stale': published_record.stale,
                    'matched_intent_delegated_scopes': [
                        _intent_delegated_scope(intent)
                        for intent in intent_records
                        if _intent_is_active(intent) and _intent_customer_asn_value(intent) == customer_value
                    ],
                    'external_management_exception': external_management_exception,
                    **details_json,
                },
                computed_at=now,
            )

    run_kwargs = {
        'status': getattr(rpki_models.ValidationRunStatus, 'COMPLETED', 'completed'),
        'completed_at': timezone.now(),
        'intent_count': active_intents,
        'published_aspa_count': sum(len(rows) for rows in published_by_customer.values()),
        'result_summary_json': {
            'comparison_scope': comparison_scope,
            'provider_snapshot_id': getattr(snapshot, 'pk', None),
            'intent_result_types': dict(intent_result_counts),
            'published_result_types': dict(published_result_counts),
            'intent_count': active_intents,
            'published_aspa_count': sum(len(rows) for rows in published_by_customer.values()),
            'published_source_count': len(published_records_seen),
            'delegated_scope_counts': dict(delegated_scope_counts),
            'ownership_scope_conflict_customer_asns': ownership_scope_conflict_customer_asns,
            'ownership_scope_conflict_customer_count': len(ownership_scope_conflict_customer_asns),
            'external_management_matched_intent_count': matched_external_intent_count,
            'external_management_matched_published_count': matched_external_published_count,
            'external_management_review_due_match_count': matched_external_review_due_count,
        },
        'summary_json': {
            'comparison_scope': comparison_scope,
            'provider_snapshot_id': getattr(snapshot, 'pk', None),
            'intent_result_types': dict(intent_result_counts),
            'published_result_types': dict(published_result_counts),
            'intent_count': active_intents,
            'published_aspa_count': sum(len(rows) for rows in published_by_customer.values()),
            'published_source_count': len(published_records_seen),
            'delegated_scope_counts': dict(delegated_scope_counts),
            'ownership_scope_conflict_customer_asns': ownership_scope_conflict_customer_asns,
            'ownership_scope_conflict_customer_count': len(ownership_scope_conflict_customer_asns),
            'external_management_matched_intent_count': matched_external_intent_count,
            'external_management_matched_published_count': matched_external_published_count,
            'external_management_review_due_match_count': matched_external_review_due_count,
        },
    }
    for field_name, value in run_kwargs.items():
        if field_name in run_field_names:
            setattr(run, field_name, value)
    update_fields = [field_name for field_name in run_kwargs if field_name in run_field_names]
    if update_fields:
        run.save(update_fields=tuple(update_fields))
    else:
        run.save()
    return run


def run_aspa_reconciliation_pipeline(
    intent_profile,
    *,
    comparison_scope: str = ASPA_COMPARISON_SCOPE_LOCAL,
    provider_snapshot=None,
    run_name: str | None = None,
):
    return reconcile_aspa_intents(
        intent_profile,
        comparison_scope=comparison_scope,
        provider_snapshot=provider_snapshot,
        run_name=run_name,
    )
