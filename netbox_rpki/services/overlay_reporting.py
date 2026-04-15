from __future__ import annotations

from collections import Counter
from datetime import timedelta
from itertools import chain

from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.overlay_correlation import (
    build_aspa_overlay_summary,
    build_roa_overlay_summary,
)


VALIDATION_STALE_AFTER = timedelta(hours=24)


def build_roa_reconciliation_overlay_summary(run: rpki_models.ROAReconciliationRun) -> dict[str, object]:
    roas = []
    unresolved_reference_count = 0

    for result in run.intent_results.select_related('best_roa').all():
        if result.best_roa_id is not None:
            roas.append(result.best_roa)
        else:
            unresolved_reference_count += 1

    for result in run.published_roa_results.select_related('roa').all():
        if result.roa_id is not None:
            roas.append(result.roa)
        else:
            unresolved_reference_count += 1

    return _summarize_authored_objects(
        object_family='roa',
        source_kind='roa_reconciliation_run',
        objects=roas,
        unresolved_reference_count=unresolved_reference_count,
        item_count=run.intent_results.count() + run.published_roa_results.count(),
        build_overlay_summary=build_roa_overlay_summary,
    )


def build_aspa_reconciliation_overlay_summary(run: rpki_models.ASPAReconciliationRun) -> dict[str, object]:
    aspas = []
    unresolved_reference_count = 0

    for result in run.intent_results.select_related('best_aspa').all():
        if result.best_aspa_id is not None:
            aspas.append(result.best_aspa)
        else:
            unresolved_reference_count += 1

    for result in run.published_aspa_results.select_related('aspa').all():
        if result.aspa_id is not None:
            aspas.append(result.aspa)
        else:
            unresolved_reference_count += 1

    return _summarize_authored_objects(
        object_family='aspa',
        source_kind='aspa_reconciliation_run',
        objects=aspas,
        unresolved_reference_count=unresolved_reference_count,
        item_count=run.intent_results.count() + run.published_aspa_results.count(),
        build_overlay_summary=build_aspa_overlay_summary,
    )


def build_roa_change_plan_overlay_summary(plan: rpki_models.ROAChangePlan) -> dict[str, object]:
    roas = []
    unresolved_reference_count = 0

    for item in plan.items.select_related('roa').all():
        if item.roa_id is not None:
            roas.append(item.roa)
        else:
            unresolved_reference_count += 1

    summary = _summarize_authored_objects(
        object_family='roa',
        source_kind='roa_change_plan',
        objects=roas,
        unresolved_reference_count=unresolved_reference_count,
        item_count=plan.items.count(),
        build_overlay_summary=build_roa_overlay_summary,
    )
    summary['source_reconciliation_run_id'] = plan.source_reconciliation_run_id
    return summary


def build_aspa_change_plan_overlay_summary(plan: rpki_models.ASPAChangePlan) -> dict[str, object]:
    aspas = []
    unresolved_reference_count = 0

    for item in plan.items.select_related('aspa').all():
        if item.aspa_id is not None:
            aspas.append(item.aspa)
        else:
            unresolved_reference_count += 1

    summary = _summarize_authored_objects(
        object_family='aspa',
        source_kind='aspa_change_plan',
        objects=aspas,
        unresolved_reference_count=unresolved_reference_count,
        item_count=plan.items.count(),
        build_overlay_summary=build_aspa_overlay_summary,
    )
    summary['source_reconciliation_run_id'] = plan.source_reconciliation_run_id
    return summary


def build_validator_instance_attention_items(validators) -> list[dict[str, object]]:
    items = []
    for validator in validators:
        latest_run = validator.validation_runs.order_by('-completed_at', '-started_at', '-pk').first()
        freshness_status = _validation_run_freshness_status(latest_run)
        status = validator.status or rpki_models.ValidationRunStatus.PENDING
        needs_attention = (
            status == rpki_models.ValidationRunStatus.FAILED
            or freshness_status in {'stale', 'missing'}
        )
        if not needs_attention:
            continue
        items.append({
            'object': validator,
            'status': status,
            'freshness_status': freshness_status,
            'latest_run': latest_run,
        })
    return items


def build_validation_run_attention_items(runs, *, limit: int = 20) -> list[dict[str, object]]:
    items = []
    for run in runs.order_by('-completed_at', '-started_at', '-pk')[:limit]:
        freshness_status = _validation_run_freshness_status(run)
        if run.status != rpki_models.ValidationRunStatus.FAILED and freshness_status != 'stale':
            continue
        items.append({
            'object': run,
            'status': run.status,
            'freshness_status': freshness_status,
            'validator': run.validator,
        })
    return items


def build_telemetry_source_attention_items(sources) -> list[dict[str, object]]:
    items = []
    for source in sources:
        if source.sync_health == rpki_models.TelemetrySyncHealth.HEALTHY:
            continue
        items.append({
            'object': source,
            'sync_health': source.sync_health,
            'sync_health_display': source.sync_health_display,
            'latest_run': source.last_successful_run,
        })
    return items


def build_external_mismatch_items(roas, aspas, *, limit: int = 20) -> list[dict[str, object]]:
    items = []
    for obj in chain(roas, aspas):
        if isinstance(obj, rpki_models.Roa):
            overlay_summary = build_roa_overlay_summary(obj)
            object_family = 'roa'
        else:
            overlay_summary = build_aspa_overlay_summary(obj)
            object_family = 'aspa'

        mismatch_categories = list(overlay_summary.get('notable_mismatch_categories') or [])
        validator_posture = overlay_summary.get('latest_validator_posture') or {}
        telemetry_posture = overlay_summary.get('telemetry') or {}
        validator_state = validator_posture.get('validation_state') or ''
        has_observed_evidence = (
            validator_posture.get('status') == 'observed'
            or telemetry_posture.get('status') == 'observed'
        )
        if not has_observed_evidence:
            continue
        if not mismatch_categories and validator_state != rpki_models.ValidationState.INVALID:
            continue
        items.append({
            'object': obj,
            'object_family': object_family,
            'overlay_summary': overlay_summary,
            'mismatch_categories': mismatch_categories,
            'validator_state': validator_state,
            'evidence_freshness': overlay_summary.get('evidence_freshness') or 'unknown',
        })

    items.sort(
        key=lambda item: (
            0 if item['evidence_freshness'] == 'stale' else 1,
            -len(item['mismatch_categories']),
            str(item['object']),
        )
    )
    return items[:limit]


def _summarize_authored_objects(*, object_family: str, source_kind: str, objects, unresolved_reference_count: int, item_count: int, build_overlay_summary):
    unique_objects = _dedupe_objects(objects)
    overlay_summaries = [build_overlay_summary(obj) for obj in unique_objects]

    validator_status_counts = Counter()
    validator_state_counts = Counter()
    telemetry_status_counts = Counter()
    freshness_counts = Counter()
    provider_linkage_status_counts = Counter()
    mismatch_category_counts = Counter()

    for summary in overlay_summaries:
        validator_posture = summary.get('latest_validator_posture') or {}
        telemetry_posture = summary.get('telemetry') or summary.get('latest_telemetry_posture') or {}

        validator_status = validator_posture.get('status') or 'unknown'
        telemetry_status = telemetry_posture.get('status') or 'unknown'
        validator_status_counts[validator_status] += 1
        telemetry_status_counts[telemetry_status] += 1

        validator_state = validator_posture.get('validation_state')
        if validator_state:
            validator_state_counts[validator_state] += 1

        evidence_freshness = summary.get('evidence_freshness') or 'unknown'
        freshness_counts[evidence_freshness] += 1

        provider_linkage = summary.get('provider_evidence_linkage_status') or 'unknown'
        provider_linkage_status_counts[provider_linkage] += 1

        mismatch_category_counts.update(summary.get('notable_mismatch_categories') or [])

    return {
        'summary_schema_version': 1,
        'source_kind': source_kind,
        'object_family': object_family,
        'item_count': item_count,
        'referenced_object_count': len(unique_objects),
        'unresolved_reference_count': unresolved_reference_count,
        'validator_status_counts': dict(validator_status_counts),
        'validator_state_counts': dict(validator_state_counts),
        'telemetry_status_counts': dict(telemetry_status_counts),
        'provider_evidence_linkage_status_counts': dict(provider_linkage_status_counts),
        'freshness_counts': dict(freshness_counts),
        'mismatch_category_counts': dict(mismatch_category_counts),
        'stale_evidence_count': freshness_counts.get('stale', 0),
        'missing_validator_count': validator_status_counts.get('unmatched', 0),
        'missing_telemetry_count': telemetry_status_counts.get('unmatched', 0),
    }


def _dedupe_objects(objects):
    unique_objects = []
    seen = set()
    for obj in objects:
        key = (type(obj), obj.pk)
        if obj.pk is None or key in seen:
            continue
        seen.add(key)
        unique_objects.append(obj)
    return unique_objects


def _validation_run_freshness_status(run: rpki_models.ValidationRun | None) -> str:
    if run is None:
        return 'missing'
    reference_time = run.completed_at or run.started_at
    if reference_time is None:
        return 'missing'
    if reference_time + VALIDATION_STALE_AFTER <= timezone.now():
        return 'stale'
    return 'fresh'
