from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from netbox_rpki import models as rpki_models


VALIDATOR_RUN_STALE_AFTER = timedelta(hours=24)
RUN_HISTORY_SUMMARY_SCHEMA_VERSION = 1
RUN_COMPARISON_SCHEMA_VERSION = 1
MAX_TIMELINE_ITEMS = 5


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
