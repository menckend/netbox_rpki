from __future__ import annotations

from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from netbox_rpki import models as rpki_models


VALIDATOR_RUN_STALE_AFTER = timedelta(hours=24)
RUN_HISTORY_SUMMARY_SCHEMA_VERSION = 1
RUN_COMPARISON_SCHEMA_VERSION = 1
CROSS_VALIDATOR_COMPARISON_SCHEMA_VERSION = 1
MAX_TIMELINE_ITEMS = 5
MAX_CROSS_COMPARISON_DISAGREEMENTS = 1000


def build_validator_run_history_summary(validator: rpki_models.ValidatorInstance, *, limit: int = MAX_TIMELINE_ITEMS) -> dict[str, object]:
    runs = list(validator.validation_runs.order_by('-completed_at', '-started_at', '-pk')[:limit])
    latest = runs[0] if runs else None
    previous = runs[1] if len(runs) > 1 else None
    return _build_run_history_summary(
        source_kind='validator_instance',
        latest=latest,
        previous=previous,
        runs=runs,
        stale_after=VALIDATOR_RUN_STALE_AFTER,
    )


def build_telemetry_run_history_summary(source: rpki_models.TelemetrySource, *, limit: int = MAX_TIMELINE_ITEMS) -> dict[str, object]:
    runs = list(source.telemetry_runs.order_by('-completed_at', '-started_at', '-pk')[:limit])
    latest = runs[0] if runs else None
    previous = runs[1] if len(runs) > 1 else None
    return _build_run_history_summary(
        source_kind='telemetry_source',
        latest=latest,
        previous=previous,
        runs=runs,
        stale_after=source.sync_health_interval,
    )


def build_validation_run_comparison(run: rpki_models.ValidationRun) -> dict[str, object]:
    previous = (
        run.validator.validation_runs.exclude(pk=run.pk)
        .order_by('-completed_at', '-started_at', '-pk')
        .first()
    )
    return _build_run_comparison(
        current=run,
        previous=previous,
        stale_after=VALIDATOR_RUN_STALE_AFTER,
    )


def build_telemetry_run_comparison(run: rpki_models.TelemetryRun) -> dict[str, object]:
    previous = (
        run.source.telemetry_runs.exclude(pk=run.pk)
        .order_by('-completed_at', '-started_at', '-pk')
        .first()
    )
    return _build_run_comparison(
        current=run,
        previous=previous,
        stale_after=run.source.sync_health_interval,
    )


def _build_run_history_summary(*, source_kind: str, latest, previous, runs, stale_after: timedelta) -> dict[str, object]:
    latest_comparison = _build_run_comparison(current=latest, previous=previous, stale_after=stale_after)
    return {
        'summary_schema_version': RUN_HISTORY_SUMMARY_SCHEMA_VERSION,
        'source_kind': source_kind,
        'run_count': len(runs),
        'latest_run_id': getattr(latest, 'pk', None),
        'previous_run_id': getattr(previous, 'pk', None),
        'latest_comparison': latest_comparison,
        'timeline': [
            _serialize_run_timeline_item(run, stale_after=stale_after)
            for run in runs
        ],
    }


def _build_run_comparison(*, current, previous, stale_after: timedelta) -> dict[str, object]:
    if current is None:
        return {
            'comparison_schema_version': RUN_COMPARISON_SCHEMA_VERSION,
            'comparison_state': 'missing_history',
            'changed_summary_fields': {},
            'timeline_freshness': 'missing',
        }

    current_summary = dict(current.summary_json or {})
    previous_summary = dict(previous.summary_json or {}) if previous is not None else {}
    changed_summary_fields = _build_summary_field_deltas(current_summary, previous_summary)

    if previous is None:
        comparison_state = 'initial'
    elif changed_summary_fields:
        comparison_state = 'changed'
    else:
        comparison_state = 'unchanged'

    return {
        'comparison_schema_version': RUN_COMPARISON_SCHEMA_VERSION,
        'comparison_state': comparison_state,
        'current_run_id': current.pk,
        'current_run_name': current.name,
        'current_status': current.status,
        'current_observed_at': _run_time_text(current),
        'previous_run_id': getattr(previous, 'pk', None),
        'previous_run_name': getattr(previous, 'name', ''),
        'previous_status': getattr(previous, 'status', ''),
        'previous_observed_at': _run_time_text(previous),
        'timeline_freshness': _freshness_status(_run_time(current), stale_after),
        'changed_summary_fields': changed_summary_fields,
        'repository_serial_changed': _field_changed(current, previous, 'repository_serial'),
        'observation_gap_seconds': _observation_gap_seconds(current, previous),
    }


def _serialize_run_timeline_item(run, *, stale_after: timedelta) -> dict[str, object]:
    summary = dict(run.summary_json or {})
    summary_excerpt = {
        key: value
        for key, value in summary.items()
        if isinstance(value, int)
    }
    return {
        'run_id': run.pk,
        'run_name': run.name,
        'status': run.status,
        'observed_at': _run_time_text(run),
        'freshness_status': _freshness_status(_run_time(run), stale_after),
        'repository_serial': getattr(run, 'repository_serial', ''),
        'summary_excerpt': summary_excerpt,
    }


def _build_summary_field_deltas(current_summary: dict[str, object], previous_summary: dict[str, object]) -> dict[str, dict[str, int]]:
    changed: dict[str, dict[str, int]] = {}
    for key in sorted(set(current_summary) | set(previous_summary)):
        current_value = current_summary.get(key)
        previous_value = previous_summary.get(key)
        if not isinstance(current_value, int) and not isinstance(previous_value, int):
            continue
        current_int = int(current_value or 0)
        previous_int = int(previous_value or 0)
        if current_int == previous_int:
            continue
        changed[key] = {
            'current': current_int,
            'previous': previous_int,
            'delta': current_int - previous_int,
        }
    return changed


def _field_changed(current, previous, field_name: str) -> bool:
    if current is None or previous is None:
        return False
    return getattr(current, field_name, '') != getattr(previous, field_name, '')


def _observation_gap_seconds(current, previous) -> int | None:
    if current is None or previous is None:
        return None
    current_time = _run_time(current)
    previous_time = _run_time(previous)
    if current_time is None or previous_time is None:
        return None
    return int((current_time - previous_time).total_seconds())


def _run_time(run) -> timezone.datetime | None:
    if run is None:
        return None
    return run.completed_at or run.started_at


def _run_time_text(run) -> str:
    run_time = _run_time(run)
    return run_time.isoformat() if run_time is not None else ''


def _freshness_status(run_time, stale_after: timedelta) -> str:
    if run_time is None:
        return 'missing'
    if run_time + stale_after <= timezone.now():
        return 'stale'
    return 'current'


# ---------------------------------------------------------------------------
# Cross-validator comparison
# ---------------------------------------------------------------------------

_STATE_RANK: dict[str, int] = {'invalid': 2, 'valid': 1, 'unknown': 0, '': -1}


def _state_rank(state: str) -> int:
    return _STATE_RANK.get(state, 0)


def _build_payload_state_map(run: rpki_models.ValidationRun | None) -> dict[tuple, str]:
    """Return {(observed_prefix, origin_asn_value) -> validation_state} for a run."""
    if run is None:
        return {}
    rows = (
        rpki_models.ValidatedRoaPayload.objects
        .filter(validation_run=run)
        .annotate(origin_asn_value=F('origin_as__asn'))
        .values('observed_prefix', 'origin_asn_value', 'object_validation_result__validation_state')
    )
    result: dict[tuple, str] = {}
    for row in rows:
        key = (row['observed_prefix'] or '', row['origin_asn_value'])
        state = row['object_validation_result__validation_state'] or ''
        existing = result.get(key)
        if existing is None or _state_rank(state) > _state_rank(existing):
            result[key] = state
    return result


def build_cross_validator_comparison(
    primary: rpki_models.ValidatorInstance,
    secondary: rpki_models.ValidatorInstance,
    *,
    limit_disagreements: int = 100,
) -> dict[str, object]:
    """Compare the latest completed validation runs of two validators.

    Returns a dict with agreement/disagreement counts and per-prefix details.
    """
    limit_disagreements = min(limit_disagreements, MAX_CROSS_COMPARISON_DISAGREEMENTS)

    primary_run = (
        primary.validation_runs.filter(status='completed')
        .order_by('-completed_at', '-pk')
        .first()
    )
    secondary_run = (
        secondary.validation_runs.filter(status='completed')
        .order_by('-completed_at', '-pk')
        .first()
    )

    primary_map = _build_payload_state_map(primary_run)
    secondary_map = _build_payload_state_map(secondary_run)

    all_keys = sorted(set(primary_map) | set(secondary_map))
    agreements = 0
    disagreements: list[dict] = []
    only_primary_count = 0
    only_secondary_count = 0

    for key in all_keys:
        p_state = primary_map.get(key)
        s_state = secondary_map.get(key)
        if p_state is None:
            only_secondary_count += 1
        elif s_state is None:
            only_primary_count += 1
        elif p_state == s_state:
            agreements += 1
        else:
            disagreements.append({
                'prefix': key[0],
                'origin_asn': key[1],
                'primary_state': p_state,
                'secondary_state': s_state,
            })

    return {
        'schema_version': CROSS_VALIDATOR_COMPARISON_SCHEMA_VERSION,
        'primary_validator_id': primary.pk,
        'primary_validator_name': primary.name,
        'secondary_validator_id': secondary.pk,
        'secondary_validator_name': secondary.name,
        'primary_run_id': getattr(primary_run, 'pk', None),
        'secondary_run_id': getattr(secondary_run, 'pk', None),
        'primary_freshness': _freshness_status(_run_time(primary_run), VALIDATOR_RUN_STALE_AFTER),
        'secondary_freshness': _freshness_status(_run_time(secondary_run), VALIDATOR_RUN_STALE_AFTER),
        'total_entries': len(all_keys),
        'common_entries': agreements + len(disagreements),
        'only_primary_count': only_primary_count,
        'only_secondary_count': only_secondary_count,
        'agreement_count': agreements,
        'disagreement_count': len(disagreements),
        'disagreements': disagreements[:limit_disagreements],
        'disagreements_truncated': len(disagreements) > limit_disagreements,
    }
