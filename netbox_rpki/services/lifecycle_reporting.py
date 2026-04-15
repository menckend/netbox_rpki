from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Mapping
import hashlib
import hmac
import json
from datetime import date, datetime, time, timedelta
from django.utils.text import slugify

from django.http import HttpResponse, JsonResponse
from django.db.models import Count, Q
from django.utils import timezone
from urllib.request import Request, urlopen

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_sync_evidence import (
    build_certificate_observation_attention_summary,
    build_publication_point_attention_summary,
    build_signed_object_attention_summary,
)


LIFECYCLE_HEALTH_SUMMARY_SCHEMA_VERSION = 1
LIFECYCLE_TIMELINE_SCHEMA_VERSION = 1
LIFECYCLE_EXPORT_SCHEMA_VERSION = 1
PUBLICATION_HEALTH_SUMMARY_SCHEMA_VERSION = 1
PUBLICATION_DIFF_TIMELINE_SCHEMA_VERSION = 1

LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY = 'provider_account_lifecycle_summary'
LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE = 'provider_account_timeline'
LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY = 'provider_account_summary'
LIFECYCLE_EXPORT_KIND_PROVIDER_PUBLICATION_DIFF_TIMELINE = 'provider_publication_diff_timeline'
LIFECYCLE_HOOK_PAYLOAD_SCHEMA_VERSION = 1

LIFECYCLE_EXPORT_CSV_HEADERS = {
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY: (
        'summary_schema_version',
        'provider_account_id',
        'policy_id',
        'policy_source',
        'sync_status',
        'sync_status_display',
        'publication_status',
        'publication_attention_count',
        'records_added',
        'records_removed',
        'records_changed',
        'latest_snapshot_id',
        'latest_diff_id',
        'total_attention_count',
    ),
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE: (
        'timeline_schema_version',
        'snapshot_id',
        'snapshot_name',
        'snapshot_status',
        'fetched_at',
        'completed_at',
        'lifecycle_status',
        'publication_status',
        'publication_attention_count',
        'latest_diff_id',
        'latest_diff_name',
        'records_added',
        'records_removed',
        'records_changed',
        'publication_changes',
    ),
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY: (
        'provider_account_id',
        'provider_account_name',
        'organization_id',
        'organization_name',
        'provider_type',
        'transport',
        'sync_enabled',
        'sync_health',
        'sync_health_display',
        'sync_due',
        'summary_schema_version',
        'summary_status',
        'records_added',
        'records_removed',
        'records_changed',
        'latest_snapshot_id',
        'latest_snapshot_name',
        'latest_diff_id',
        'latest_diff_name',
        'total_attention_count',
    ),
    LIFECYCLE_EXPORT_KIND_PROVIDER_PUBLICATION_DIFF_TIMELINE: (
        'timeline_schema_version',
        'snapshot_diff_id',
        'snapshot_diff_name',
        'status',
        'compared_at',
        'base_snapshot_id',
        'comparison_snapshot_id',
        'records_added',
        'records_removed',
        'records_changed',
        'records_stale',
        'publication_changes',
        'item_count',
    ),
}

LIFECYCLE_HEALTH_DEFAULTS = {
    'sync_stale_after_minutes': 120,
    'roa_expiry_warning_days': 30,
    'certificate_expiry_warning_days': 30,
    'exception_expiry_warning_days': 30,
    'publication_exchange_failure_threshold': 1,
    'publication_stale_after_minutes': 180,
    'certificate_expired_grace_minutes': 0,
    'alert_repeat_after_minutes': 360,
}

PUBLICATION_HEALTH_EMPTY_SUMMARY = {
    'summary_schema_version': PUBLICATION_HEALTH_SUMMARY_SCHEMA_VERSION,
    'status': 'healthy',
    'publication_points': {
        'total': 0,
        'stale': 0,
        'exchange_failed': 0,
        'exchange_overdue': 0,
        'authored_linkage_missing': 0,
        'attention_item_count': 0,
    },
    'signed_objects': {
        'total': 0,
        'stale': 0,
        'authored_linkage_missing': 0,
        'publication_linkage_missing': 0,
        'by_type': {},
        'attention_item_count': 0,
    },
    'certificate_observations': {
        'total': 0,
        'stale': 0,
        'expiring_soon': 0,
        'expired': 0,
        'ambiguous': 0,
        'publication_linkage_missing': 0,
        'signed_object_linkage_missing': 0,
        'attention_item_count': 0,
    },
    'attention_item_count': 0,
}


def _datetime_text(value) -> str:
    if value in (None, ''):
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _sanitize_related_reference(value: object, *, visible_ids: set[object] | None) -> object:
    if value in (None, '') or visible_ids is None:
        return value
    if value in visible_ids:
        return value
    return None


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    return int(summary.get(key, 0) or 0)


def _export_kind_slug(kind: str) -> str:
    return kind.replace('_', '-')


def _export_provider_account_slug(provider_account: rpki_models.RpkiProviderAccount | None) -> str:
    if provider_account is None:
        return 'all-provider-accounts'
    name_slug = slugify(provider_account.name) or 'provider-account'
    return f'provider-account-{provider_account.pk}-{name_slug}'


def _lifecycle_summary_export_row(summary: Mapping[str, object]) -> dict[str, object]:
    policy = dict(summary.get('policy') or {})
    sync = dict(summary.get('sync') or {})
    publication_health = dict(summary.get('publication_health') or {})
    publication = dict(summary.get('publication') or {})
    diff = dict(summary.get('diff') or {})
    attention_summary = dict(summary.get('attention_summary') or {})
    return {
        'summary_schema_version': int(summary.get('summary_schema_version', 0) or 0),
        'provider_account_id': summary.get('provider_account_id'),
        'policy_id': policy.get('policy_id'),
        'policy_source': policy.get('source', ''),
        'sync_status': sync.get('status', ''),
        'sync_status_display': sync.get('status_display', ''),
        'publication_status': publication_health.get('status', publication.get('status', '')),
        'publication_attention_count': int(publication_health.get('attention_item_count', publication.get('attention_count', 0)) or 0),
        'records_added': _summary_int(diff, 'records_added'),
        'records_removed': _summary_int(diff, 'records_removed'),
        'records_changed': _summary_int(diff, 'records_changed'),
        'latest_snapshot_id': diff.get('latest_snapshot_id'),
        'latest_diff_id': diff.get('latest_diff_id'),
        'total_attention_count': int(attention_summary.get('total_attention_count', 0) or 0),
    }


def _provider_account_summary_export_row(account: Mapping[str, object]) -> dict[str, object]:
    lifecycle_summary = dict(account.get('lifecycle_health_summary') or {})
    attention_summary = dict(lifecycle_summary.get('attention_summary') or {})
    return {
        'provider_account_id': account.get('provider_account_id'),
        'provider_account_name': account.get('provider_account_name', ''),
        'organization_id': account.get('organization_id'),
        'organization_name': account.get('organization_name', ''),
        'provider_type': account.get('provider_type', ''),
        'transport': account.get('transport', ''),
        'sync_enabled': bool(account.get('sync_enabled', False)),
        'sync_health': account.get('sync_health', ''),
        'sync_health_display': account.get('sync_health_display', ''),
        'sync_due': bool(account.get('sync_due', False)),
        'summary_schema_version': account.get('summary_schema_version'),
        'summary_status': account.get('summary_status', ''),
        'records_added': int(account.get('records_added', 0) or 0),
        'records_removed': int(account.get('records_removed', 0) or 0),
        'records_changed': int(account.get('records_changed', 0) or 0),
        'latest_snapshot_id': account.get('latest_snapshot_id'),
        'latest_snapshot_name': account.get('latest_snapshot_name', ''),
        'latest_diff_id': account.get('latest_diff_id'),
        'latest_diff_name': account.get('latest_diff_name', ''),
        'total_attention_count': int(attention_summary.get('total_attention_count', 0) or 0),
    }


def _lifecycle_timeline_export_row(item: Mapping[str, object]) -> dict[str, object]:
    return {
        'timeline_schema_version': int(item.get('timeline_schema_version', 0) or 0),
        'snapshot_id': item.get('snapshot_id'),
        'snapshot_name': item.get('snapshot_name', ''),
        'snapshot_status': item.get('snapshot_status', ''),
        'fetched_at': item.get('fetched_at', ''),
        'completed_at': item.get('completed_at', ''),
        'lifecycle_status': item.get('lifecycle_status', ''),
        'publication_status': item.get('publication_status', ''),
        'publication_attention_count': int(item.get('publication_attention_count', 0) or 0),
        'latest_diff_id': item.get('latest_diff_id'),
        'latest_diff_name': item.get('latest_diff_name', ''),
        'records_added': int(item.get('records_added', 0) or 0),
        'records_removed': int(item.get('records_removed', 0) or 0),
        'records_changed': int(item.get('records_changed', 0) or 0),
        'publication_changes': int(item.get('publication_changes', 0) or 0),
    }


def _publication_diff_timeline_export_row(item: Mapping[str, object]) -> dict[str, object]:
    return {
        'timeline_schema_version': int(item.get('timeline_schema_version', 0) or 0),
        'snapshot_diff_id': item.get('snapshot_diff_id'),
        'snapshot_diff_name': item.get('snapshot_diff_name', ''),
        'status': item.get('status', ''),
        'compared_at': item.get('compared_at', ''),
        'base_snapshot_id': item.get('base_snapshot_id'),
        'comparison_snapshot_id': item.get('comparison_snapshot_id'),
        'records_added': int(item.get('records_added', 0) or 0),
        'records_removed': int(item.get('records_removed', 0) or 0),
        'records_changed': int(item.get('records_changed', 0) or 0),
        'records_stale': int(item.get('records_stale', 0) or 0),
        'publication_changes': int(item.get('publication_changes', 0) or 0),
        'item_count': int(item.get('item_count', 0) or 0),
    }


def build_lifecycle_export_payload(
    kind: str,
    data: Mapping[str, object],
    *,
    filters: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        'export_schema_version': LIFECYCLE_EXPORT_SCHEMA_VERSION,
        'kind': kind,
        'format': 'json',
        'exported_at': _datetime_text(timezone.now()),
        'filters': dict(filters or {}),
        'data': dict(data),
    }


def iter_lifecycle_export_rows(kind: str, data: Mapping[str, object]):
    if kind == LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY:
        yield _lifecycle_summary_export_row(data)
        return

    if kind == LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE:
        for item in data.get('items') or []:
            yield _lifecycle_timeline_export_row(item)
        return

    if kind == LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY:
        for item in data.get('accounts') or []:
            yield _provider_account_summary_export_row(item)
        return

    if kind == LIFECYCLE_EXPORT_KIND_PROVIDER_PUBLICATION_DIFF_TIMELINE:
        for item in data.get('items') or []:
            yield _publication_diff_timeline_export_row(item)
        return

    raise ValueError(f'Unsupported lifecycle export kind: {kind}')


def get_lifecycle_export_filename(
    kind: str,
    fmt: str,
    *,
    provider_account: rpki_models.RpkiProviderAccount | None = None,
) -> str:
    return f"{_export_provider_account_slug(provider_account)}-{_export_kind_slug(kind)}.{fmt}"


def build_lifecycle_export_response(
    kind: str,
    data: Mapping[str, object],
    fmt: str,
    *,
    filters: Mapping[str, object] | None = None,
    provider_account: rpki_models.RpkiProviderAccount | None = None,
) -> HttpResponse:
    fmt = fmt.lower()
    if fmt not in {'json', 'csv'}:
        raise ValueError(f'Unsupported export format: {fmt}')

    filename = get_lifecycle_export_filename(kind, fmt, provider_account=provider_account)
    if fmt == 'json':
        response = JsonResponse(
            build_lifecycle_export_payload(kind, data, filters=filters),
            json_dumps_params={'indent': 2, 'sort_keys': True},
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    rows = list(iter_lifecycle_export_rows(kind, data))
    header = LIFECYCLE_EXPORT_CSV_HEADERS.get(kind)
    if header is None:
        header = tuple(rows[0].keys()) if rows else ()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    response = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _copy_publication_health_summary(summary: Mapping[str, object] | None) -> dict[str, object] | None:
    if not summary:
        return None
    return {
        'summary_schema_version': int(summary.get('summary_schema_version', PUBLICATION_HEALTH_SUMMARY_SCHEMA_VERSION) or PUBLICATION_HEALTH_SUMMARY_SCHEMA_VERSION),
        'status': summary.get('status', 'healthy'),
        'publication_points': dict(summary.get('publication_points') or {}),
        'signed_objects': dict(summary.get('signed_objects') or {}),
        'certificate_observations': dict(summary.get('certificate_observations') or {}),
        'attention_item_count': int(summary.get('attention_item_count', 0) or 0),
    }


def _empty_publication_health_summary() -> dict[str, object]:
    return {
        'summary_schema_version': PUBLICATION_HEALTH_SUMMARY_SCHEMA_VERSION,
        'status': 'healthy',
        'publication_points': dict(PUBLICATION_HEALTH_EMPTY_SUMMARY['publication_points']),
        'signed_objects': dict(PUBLICATION_HEALTH_EMPTY_SUMMARY['signed_objects']),
        'certificate_observations': dict(PUBLICATION_HEALTH_EMPTY_SUMMARY['certificate_observations']),
        'attention_item_count': 0,
    }


def _latest_completed_snapshot(provider_account: rpki_models.RpkiProviderAccount) -> rpki_models.ProviderSnapshot | None:
    return (
        provider_account.snapshots
        .filter(status=rpki_models.ValidationRunStatus.COMPLETED)
        .order_by('-fetched_at', '-pk')
        .first()
    )


def _aggregate_publication_health(snapshot: rpki_models.ProviderSnapshot, *, thresholds: Mapping[str, int], now) -> dict[str, object]:
    publication_points_qs = rpki_models.ImportedPublicationPoint.objects.filter(provider_snapshot=snapshot)
    signed_objects_qs = rpki_models.ImportedSignedObject.objects.filter(provider_snapshot=snapshot)
    certificate_observations_qs = rpki_models.ImportedCertificateObservation.objects.filter(provider_snapshot=snapshot)

    publication_points = {
        'total': 0,
        'stale': 0,
        'exchange_failed': 0,
        'exchange_overdue': 0,
        'authored_linkage_missing': 0,
        'attention_item_count': 0,
    }
    signed_objects = {
        'total': 0,
        'stale': 0,
        'authored_linkage_missing': 0,
        'publication_linkage_missing': 0,
        'by_type': Counter(),
        'attention_item_count': 0,
    }
    certificate_observations = {
        'total': 0,
        'stale': 0,
        'expiring_soon': 0,
        'expired': 0,
        'ambiguous': 0,
        'publication_linkage_missing': 0,
        'signed_object_linkage_missing': 0,
        'attention_item_count': 0,
    }

    for publication_point in publication_points_qs:
        summary = build_publication_point_attention_summary(publication_point, now=now, thresholds=thresholds)
        publication_points['total'] += 1
        publication_points['stale'] += int(bool(summary['stale']))
        publication_points['exchange_failed'] += int(bool(summary['exchange']['failed']))
        publication_points['exchange_overdue'] += int(bool(summary['exchange']['overdue']))
        publication_points['authored_linkage_missing'] += int(bool(summary['authored_linkage']['missing']))
        publication_points['attention_item_count'] += int(summary['attention_count'])

    for signed_object in signed_objects_qs:
        summary = build_signed_object_attention_summary(signed_object)
        signed_objects['total'] += 1
        signed_objects['stale'] += int(bool(summary['stale']))
        signed_objects['authored_linkage_missing'] += int(bool(summary['authored_linkage']['missing']))
        signed_objects['publication_linkage_missing'] += int(bool(summary['publication_linkage']['missing']))
        signed_objects['by_type'][summary['signed_object_type']] += 1
        signed_objects['attention_item_count'] += int(summary['attention_count'])

    for certificate_observation in certificate_observations_qs:
        summary = build_certificate_observation_attention_summary(
            certificate_observation,
            now=now,
            thresholds=thresholds,
        )
        certificate_observations['total'] += 1
        certificate_observations['stale'] += int(bool(summary['stale']))
        certificate_observations['expiring_soon'] += int(bool(summary['expiry']['expiring_soon']))
        certificate_observations['expired'] += int(bool(summary['expiry']['expired']))
        certificate_observations['ambiguous'] += int(bool(summary['evidence']['is_ambiguous']))
        certificate_observations['publication_linkage_missing'] += int(bool(summary['publication_linkage']['missing']))
        certificate_observations['signed_object_linkage_missing'] += int(bool(summary['signed_object_linkage']['missing']))
        certificate_observations['attention_item_count'] += int(summary['attention_count'])

    publication_health = {
        'summary_schema_version': PUBLICATION_HEALTH_SUMMARY_SCHEMA_VERSION,
        'status': 'attention',
        'publication_points': publication_points,
        'signed_objects': signed_objects,
        'certificate_observations': certificate_observations,
    }
    publication_health['signed_objects']['by_type'] = dict(signed_objects['by_type'])
    publication_health['attention_item_count'] = (
        publication_points['attention_item_count']
        + signed_objects['attention_item_count']
        + certificate_observations['attention_item_count']
    )
    publication_health['status'] = 'healthy' if publication_health['attention_item_count'] == 0 else 'attention'
    return publication_health


def build_snapshot_publication_health_rollup(
    snapshot: rpki_models.ProviderSnapshot,
    *,
    policy: rpki_models.LifecycleHealthPolicy | None = None,
    now=None,
) -> dict[str, object]:
    persisted = _copy_publication_health_summary((snapshot.summary_json or {}).get('publication_health'))
    if persisted is not None:
        return persisted

    now = now or timezone.now()
    _, thresholds, _ = get_effective_lifecycle_thresholds(
        organization=snapshot.organization,
        provider_account=snapshot.provider_account,
        policy=policy,
    )
    return _aggregate_publication_health(snapshot, thresholds=thresholds, now=now)


def build_publication_health_rollup(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    policy: rpki_models.LifecycleHealthPolicy | None = None,
    now=None,
) -> dict[str, object] | None:
    latest_snapshot = _latest_completed_snapshot(provider_account)
    if latest_snapshot is None:
        return None

    now = now or timezone.now()
    publication_health = build_snapshot_publication_health_rollup(
        latest_snapshot,
        policy=policy,
        now=now,
    )
    return {
        'snapshot_id': latest_snapshot.pk,
        'snapshot_name': latest_snapshot.name,
        'snapshot_fetched_at': _datetime_text(latest_snapshot.fetched_at),
        'snapshot_completed_at': _datetime_text(latest_snapshot.completed_at),
        'publication_health': publication_health,
        'publication_points': dict(publication_health['publication_points']),
        'signed_objects': dict(publication_health['signed_objects']),
        'certificate_observations': dict(publication_health['certificate_observations']),
        'attention_item_count': int(publication_health['attention_item_count']),
    }


def build_diff_publication_health_rollup(
    snapshot_diff: rpki_models.ProviderSnapshotDiff,
) -> dict[str, object]:
    families = (
        rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
        rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY,
        rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY,
    )
    rows = snapshot_diff.items.filter(object_family__in=families)
    family_counts: dict[str, dict[str, int]] = {
        family: {'added': 0, 'removed': 0, 'changed': 0, 'stale': 0}
        for family in families
    }
    totals = {'added': 0, 'removed': 0, 'changed': 0, 'stale': 0}
    for row in rows:
        family_summary = family_counts[row.object_family]
        change_key = row.change_type.lower()
        if change_key in family_summary:
            family_summary[change_key] += 1
            totals[change_key] += 1
        if row.is_stale:
            family_summary['stale'] += 1
            totals['stale'] += 1

    publication_change_count = totals['added'] + totals['removed'] + totals['changed']
    return {
        'summary_schema_version': PUBLICATION_HEALTH_SUMMARY_SCHEMA_VERSION,
        'status': 'attention' if publication_change_count or totals['stale'] else 'healthy',
        'publication_family_counts': family_counts,
        'records_added': totals['added'],
        'records_removed': totals['removed'],
        'records_changed': totals['changed'],
        'records_stale': totals['stale'],
        'publication_changes': publication_change_count,
        'item_count': rows.count(),
    }


def _snapshot_timeline_status(
    *,
    snapshot: rpki_models.ProviderSnapshot,
    summary: Mapping[str, object],
    publication_health: Mapping[str, object],
    latest_diff_publication_rollup: Mapping[str, object] | None,
) -> str:
    status = str(summary.get('status') or snapshot.status or '').lower()
    if status == str(rpki_models.ValidationRunStatus.FAILED):
        return 'critical'

    attention_count = (
        _summary_int(summary, 'records_stale')
        + _summary_int(summary, 'records_failed')
        + int(publication_health.get('attention_item_count', 0) or 0)
    )
    if latest_diff_publication_rollup is not None:
        attention_count += int(latest_diff_publication_rollup.get('publication_changes', 0) or 0)
        attention_count += int(latest_diff_publication_rollup.get('records_stale', 0) or 0)

    return 'healthy' if attention_count == 0 else 'warning'


def _build_snapshot_timeline_row(
    snapshot: rpki_models.ProviderSnapshot,
    *,
    visible_diff_ids: set[object] | None = None,
) -> dict[str, object]:
    summary = dict(snapshot.summary_json or {})
    publication_health = _copy_publication_health_summary(summary.get('publication_health'))
    if publication_health is None:
        publication_health = build_snapshot_publication_health_rollup(snapshot)

    latest_diff_id = _sanitize_related_reference(summary.get('latest_diff_id'), visible_ids=visible_diff_ids)
    latest_diff = None
    latest_diff_publication_rollup: dict[str, object] | None = None
    latest_diff_summary: dict[str, object] = {}

    if latest_diff_id is not None:
        latest_diff = (
            snapshot.diffs_as_comparison
            .select_related('base_snapshot', 'comparison_snapshot')
            .filter(pk=latest_diff_id)
            .first()
        )
    elif visible_diff_ids is None:
        latest_diff = (
            snapshot.diffs_as_comparison
            .select_related('base_snapshot', 'comparison_snapshot')
            .order_by('-compared_at', '-created', '-pk')
            .first()
        )
    else:
        latest_diff = (
            snapshot.diffs_as_comparison
            .select_related('base_snapshot', 'comparison_snapshot')
            .filter(pk__in=visible_diff_ids)
            .order_by('-compared_at', '-created', '-pk')
            .first()
        )

    if latest_diff is not None:
        latest_diff_summary = dict(latest_diff.summary_json or {})
        latest_diff_publication_rollup = build_diff_publication_health_rollup(latest_diff)
        latest_diff_id = latest_diff.pk
    latest_diff_totals = dict(latest_diff_summary.get('totals') or {})
    records_added = _summary_int(latest_diff_totals, 'records_added')
    records_removed = _summary_int(latest_diff_totals, 'records_removed')
    records_changed = _summary_int(latest_diff_totals, 'records_changed')
    publication_changes = int((latest_diff_publication_rollup or {}).get('publication_changes', 0) or 0)
    records_stale = int((latest_diff_publication_rollup or {}).get('records_stale', 0) or 0)

    return {
        'timeline_schema_version': LIFECYCLE_TIMELINE_SCHEMA_VERSION,
        'snapshot_id': snapshot.pk,
        'snapshot_name': snapshot.name,
        'snapshot_url': snapshot.get_absolute_url(),
        'snapshot_status': snapshot.status,
        'fetched_at': _datetime_text(snapshot.fetched_at),
        'completed_at': _datetime_text(snapshot.completed_at),
        'lifecycle_status': _snapshot_timeline_status(
            snapshot=snapshot,
            summary=summary,
            publication_health=publication_health,
            latest_diff_publication_rollup=latest_diff_publication_rollup,
        ),
        'publication_status': 'healthy' if int(publication_health.get('attention_item_count', 0) or 0) == 0 else 'attention',
        'publication_attention_count': int(publication_health.get('attention_item_count', 0) or 0),
        'latest_diff_id': latest_diff_id,
        'latest_diff_name': latest_diff.name if latest_diff is not None else '',
        'latest_diff_url': latest_diff.get_absolute_url() if latest_diff is not None else '',
        'records_added': records_added,
        'records_removed': records_removed,
        'records_changed': records_changed,
        'records_churned': records_added + records_removed + records_changed,
        'records_stale': records_stale,
        'publication_changes': publication_changes,
        'publication_family_counts': dict((latest_diff_publication_rollup or {}).get('publication_family_counts', {})),
    }


def build_provider_lifecycle_timeline(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    limit: int = 20,
    visible_snapshot_ids: set[object] | None = None,
    visible_diff_ids: set[object] | None = None,
) -> dict[str, object]:
    snapshots = provider_account.snapshots.order_by('-completed_at', '-fetched_at', '-created', '-pk')
    if visible_snapshot_ids is not None:
        snapshots = snapshots.filter(pk__in=visible_snapshot_ids)

    items = [
        _build_snapshot_timeline_row(snapshot, visible_diff_ids=visible_diff_ids)
        for snapshot in snapshots[:limit]
    ]
    return {
        'timeline_schema_version': LIFECYCLE_TIMELINE_SCHEMA_VERSION,
        'provider_account_id': provider_account.pk,
        'provider_account_name': provider_account.name,
        'limit': int(limit),
        'item_count': len(items),
        'items': items,
    }


def _build_diff_timeline_row(
    snapshot_diff: rpki_models.ProviderSnapshotDiff,
) -> dict[str, object]:
    summary = dict(snapshot_diff.summary_json or {})
    totals = dict(summary.get('totals') or {})
    publication_rollup = build_diff_publication_health_rollup(snapshot_diff)
    return {
        'timeline_schema_version': PUBLICATION_DIFF_TIMELINE_SCHEMA_VERSION,
        'snapshot_diff_id': snapshot_diff.pk,
        'snapshot_diff_name': snapshot_diff.name,
        'snapshot_diff_url': snapshot_diff.get_absolute_url(),
        'base_snapshot_id': snapshot_diff.base_snapshot_id,
        'base_snapshot_name': snapshot_diff.base_snapshot.name,
        'base_snapshot_url': snapshot_diff.base_snapshot.get_absolute_url(),
        'comparison_snapshot_id': snapshot_diff.comparison_snapshot_id,
        'comparison_snapshot_name': snapshot_diff.comparison_snapshot.name,
        'comparison_snapshot_url': snapshot_diff.comparison_snapshot.get_absolute_url(),
        'status': summary.get('status', snapshot_diff.status),
        'compared_at': _datetime_text(snapshot_diff.compared_at),
        'records_added': _summary_int(totals, 'records_added'),
        'records_removed': _summary_int(totals, 'records_removed'),
        'records_changed': _summary_int(totals, 'records_changed'),
        'records_stale': _summary_int(totals, 'records_stale'),
        'publication_changes': int(publication_rollup['publication_changes']),
        'publication_family_counts': dict(publication_rollup['publication_family_counts']),
        'item_count': int(publication_rollup['item_count']),
    }


def build_provider_publication_diff_timeline(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    limit: int = 20,
    visible_diff_ids: set[object] | None = None,
) -> dict[str, object]:
    diffs = provider_account.snapshot_diffs.order_by('-compared_at', '-created', '-pk')
    if visible_diff_ids is not None:
        diffs = diffs.filter(pk__in=visible_diff_ids)

    items = [
        _build_diff_timeline_row(snapshot_diff)
        for snapshot_diff in diffs[:limit]
    ]
    return {
        'timeline_schema_version': PUBLICATION_DIFF_TIMELINE_SCHEMA_VERSION,
        'provider_account_id': provider_account.pk,
        'provider_account_name': provider_account.name,
        'limit': int(limit),
        'item_count': len(items),
        'items': items,
    }


def resolve_lifecycle_health_policy(
    *,
    organization: rpki_models.Organization | None = None,
    provider_account: rpki_models.RpkiProviderAccount | None = None,
) -> rpki_models.LifecycleHealthPolicy | None:
    if provider_account is not None:
        override = (
            rpki_models.LifecycleHealthPolicy.objects.filter(
                provider_account=provider_account,
                enabled=True,
            )
            .select_related('organization', 'provider_account')
            .first()
        )
        if override is not None:
            return override
        organization = organization or provider_account.organization

    if organization is None:
        return None

    return (
        rpki_models.LifecycleHealthPolicy.objects.filter(
            organization=organization,
            provider_account__isnull=True,
            enabled=True,
        )
        .select_related('organization')
        .first()
    )


def get_effective_lifecycle_thresholds(
    *,
    organization: rpki_models.Organization | None = None,
    provider_account: rpki_models.RpkiProviderAccount | None = None,
    policy: rpki_models.LifecycleHealthPolicy | None = None,
) -> tuple[rpki_models.LifecycleHealthPolicy | None, dict[str, int], str]:
    resolved_policy = policy or resolve_lifecycle_health_policy(
        organization=organization,
        provider_account=provider_account,
    )

    thresholds = dict(LIFECYCLE_HEALTH_DEFAULTS)
    source = 'built_in_default'
    if resolved_policy is not None:
        source = 'organization_default'
        if resolved_policy.provider_account_id is not None:
            source = 'provider_account_override'
        for key in LIFECYCLE_HEALTH_DEFAULTS:
            thresholds[key] = int(getattr(resolved_policy, key))

    return resolved_policy, thresholds, source


def _serialize_lifecycle_policy(
    policy: rpki_models.LifecycleHealthPolicy | None,
    thresholds: Mapping[str, int],
    source: str,
) -> dict[str, object]:
    return {
        'policy_id': getattr(policy, 'pk', None),
        'policy_name': getattr(policy, 'name', ''),
        'organization_id': getattr(policy, 'organization_id', None),
        'provider_account_id': getattr(policy, 'provider_account_id', None),
        'enabled': bool(getattr(policy, 'enabled', False)) if policy is not None else False,
        'source': source,
        'thresholds': dict(thresholds),
        'notes': getattr(policy, 'notes', ''),
    }


def _compute_sync_state(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    thresholds: Mapping[str, int],
    now,
) -> dict[str, object]:
    stale_after_minutes = int(thresholds['sync_stale_after_minutes'])
    stale_after_delta = timedelta(minutes=stale_after_minutes)
    last_successful_sync = provider_account.last_successful_sync
    minutes_since_success = None
    next_stale_at = None
    state = rpki_models.ProviderSyncHealth.HEALTHY

    if not provider_account.sync_enabled:
        state = rpki_models.ProviderSyncHealth.DISABLED
    elif provider_account.last_sync_status == rpki_models.ValidationRunStatus.RUNNING:
        state = rpki_models.ProviderSyncHealth.IN_PROGRESS
    elif provider_account.last_sync_status == rpki_models.ValidationRunStatus.FAILED:
        state = rpki_models.ProviderSyncHealth.FAILED
    elif last_successful_sync is None:
        state = rpki_models.ProviderSyncHealth.NEVER_SYNCED
    else:
        next_stale_at = last_successful_sync + stale_after_delta
        minutes_since_success = int(max((now - last_successful_sync).total_seconds(), 0) // 60)
        if next_stale_at <= now:
            state = rpki_models.ProviderSyncHealth.STALE

    return {
        'status': state,
        'status_display': rpki_models.ProviderSyncHealth(state).label,
        'sync_enabled': provider_account.sync_enabled,
        'last_sync_status': provider_account.last_sync_status,
        'last_successful_sync': _datetime_text(last_successful_sync),
        'next_sync_due_at': _datetime_text(provider_account.next_sync_due_at),
        'stale_after_minutes': stale_after_minutes,
        'minutes_since_success': minutes_since_success,
        'next_stale_at': _datetime_text(next_stale_at),
        'is_attention': state in {
            rpki_models.ProviderSyncHealth.FAILED,
            rpki_models.ProviderSyncHealth.STALE,
            rpki_models.ProviderSyncHealth.NEVER_SYNCED,
        },
    }


def _count_expiring_objects(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    thresholds: Mapping[str, int],
    now,
) -> dict[str, object]:
    organization = provider_account.organization
    today = now.date()
    roa_threshold = today + timedelta(days=int(thresholds['roa_expiry_warning_days']))
    certificate_threshold = today + timedelta(days=int(thresholds['certificate_expiry_warning_days']))
    exception_threshold = now + timedelta(days=int(thresholds['exception_expiry_warning_days']))

    roa_count = rpki_models.RoaObject.objects.filter(
        organization=organization,
        valid_to__isnull=False,
        valid_to__lte=roa_threshold,
    ).count()
    certificate_count = rpki_models.Certificate.objects.filter(
        rpki_org=organization,
        valid_to__isnull=False,
        valid_to__lte=certificate_threshold,
    ).count()
    exception_count = rpki_models.RoutingIntentException.objects.filter(
        organization=organization,
        enabled=True,
        ends_at__isnull=False,
        ends_at__lte=exception_threshold,
    ).count()

    return {
        'roas': {
            'warning_days': int(thresholds['roa_expiry_warning_days']),
            'count': roa_count,
            'threshold_date': roa_threshold.isoformat(),
        },
        'certificates': {
            'warning_days': int(thresholds['certificate_expiry_warning_days']),
            'count': certificate_count,
            'threshold_date': certificate_threshold.isoformat(),
            'expired_grace_minutes': int(thresholds['certificate_expired_grace_minutes']),
        },
        'exceptions': {
            'warning_days': int(thresholds['exception_expiry_warning_days']),
            'count': exception_count,
            'threshold_at': _datetime_text(exception_threshold),
        },
    }


def _build_publication_section(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    thresholds: Mapping[str, int],
    now,
) -> dict[str, object]:
    latest_snapshot = _latest_completed_snapshot(provider_account)
    if latest_snapshot is None:
        return {
            'available': False,
            'snapshot_id': None,
            'snapshot_name': '',
            'snapshot_fetched_at': '',
            'publication_health': _empty_publication_health_summary(),
            'publication_points': {
                'total': 0,
                'exchange_failed': 0,
                'exchange_overdue': 0,
                'stale': 0,
                'authored_linkage_missing': 0,
                'attention_threshold': int(thresholds['publication_exchange_failure_threshold']),
            },
            'signed_objects': {
                'total': 0,
                'stale': 0,
                'authored_linkage_missing': 0,
                'publication_linkage_missing': 0,
                'by_type': {},
            },
            'certificate_observations': {
                'total': 0,
                'stale': 0,
                'expiring_soon': 0,
                'expired': 0,
                'ambiguous': 0,
                'publication_linkage_missing': 0,
                'signed_object_linkage_missing': 0,
            },
            'attention_count': 0,
            'placeholder': True,
        }

    publication_health = build_snapshot_publication_health_rollup(latest_snapshot, now=now)

    return {
        'available': True,
        'snapshot_id': latest_snapshot.pk,
        'snapshot_name': latest_snapshot.name,
        'snapshot_fetched_at': _datetime_text(latest_snapshot.fetched_at),
        'publication_health': publication_health,
        'publication_points': {
            'total': int(publication_health['publication_points']['total']),
            'stale': int(publication_health['publication_points']['stale']),
            'exchange_failed': int(publication_health['publication_points']['exchange_failed']),
            'exchange_overdue': int(publication_health['publication_points']['exchange_overdue']),
            'authored_linkage_missing': int(publication_health['publication_points']['authored_linkage_missing']),
            'attention_threshold': int(thresholds['publication_exchange_failure_threshold']),
            'stale_after_minutes': int(thresholds['publication_stale_after_minutes']),
        },
        'signed_objects': {
            'total': int(publication_health['signed_objects']['total']),
            'stale': int(publication_health['signed_objects']['stale']),
            'authored_linkage_missing': int(publication_health['signed_objects']['authored_linkage_missing']),
            'publication_linkage_missing': int(publication_health['signed_objects']['publication_linkage_missing']),
            'by_type': dict(publication_health['signed_objects']['by_type']),
        },
        'certificate_observations': {
            'total': int(publication_health['certificate_observations']['total']),
            'stale': int(publication_health['certificate_observations']['stale']),
            'expiring_soon': int(publication_health['certificate_observations']['expiring_soon']),
            'expired': int(publication_health['certificate_observations']['expired']),
            'ambiguous': int(publication_health['certificate_observations']['ambiguous']),
            'publication_linkage_missing': int(publication_health['certificate_observations']['publication_linkage_missing']),
            'signed_object_linkage_missing': int(publication_health['certificate_observations']['signed_object_linkage_missing']),
        },
        'attention_count': int(publication_health['attention_item_count']),
        'placeholder': True,
    }


def _build_diff_section(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    visible_snapshot_ids: set[object] | None,
    visible_diff_ids: set[object] | None,
) -> dict[str, object]:
    summary = dict(provider_account.last_sync_summary_json or {})
    latest_snapshot_id = _sanitize_related_reference(
        summary.get('latest_snapshot_id'),
        visible_ids=visible_snapshot_ids,
    )
    latest_diff_id = _sanitize_related_reference(
        summary.get('latest_diff_id'),
        visible_ids=visible_diff_ids,
    )
    return {
        'latest_snapshot_id': latest_snapshot_id,
        'latest_snapshot_name': summary.get('latest_snapshot_name', '') if latest_snapshot_id is not None else '',
        'latest_snapshot_completed_at': summary.get('latest_snapshot_completed_at', '') if latest_snapshot_id is not None else '',
        'latest_diff_id': latest_diff_id,
        'latest_diff_name': summary.get('latest_diff_name', '') if latest_diff_id is not None else '',
        'records_added': int(summary.get('records_added', 0) or 0),
        'records_removed': int(summary.get('records_removed', 0) or 0),
        'records_changed': int(summary.get('records_changed', 0) or 0),
    }


def _build_attention_summary(summary: Mapping[str, object]) -> dict[str, object]:
    sync_section = dict(summary.get('sync') or {})
    expiry_section = dict(summary.get('expiry') or {})
    publication_section = dict(summary.get('publication') or {})
    publication_health = dict(summary.get('publication_health') or {})
    diff_section = dict(summary.get('diff') or {})

    expiry_attention_count = sum(
        int((expiry_section.get(key) or {}).get('count', 0) or 0)
        for key in ('roas', 'certificates', 'exceptions')
    )
    publication_attention_count = int(
        publication_health.get('attention_item_count', publication_section.get('attention_count', 0)) or 0
    )
    diff_attention_count = sum(
        int(diff_section.get(key, 0) or 0)
        for key in ('records_added', 'records_removed', 'records_changed')
    )
    sync_attention = bool(sync_section.get('is_attention'))

    status = 'healthy'
    if sync_section.get('status') == rpki_models.ProviderSyncHealth.FAILED:
        status = 'critical'
    elif sync_attention or expiry_attention_count or publication_attention_count or diff_attention_count:
        status = 'warning'

    total_attention_count = (
        (1 if sync_attention else 0)
        + expiry_attention_count
        + publication_attention_count
        + diff_attention_count
    )
    return {
        'status': status,
        'sync_attention': sync_attention,
        'expiry_attention_count': expiry_attention_count,
        'publication_attention_count': publication_attention_count,
        'diff_attention_count': diff_attention_count,
        'total_attention_count': total_attention_count,
    }


def build_provider_lifecycle_health_summary(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    policy: rpki_models.LifecycleHealthPolicy | None = None,
    visible_snapshot_ids: set[object] | None = None,
    visible_diff_ids: set[object] | None = None,
) -> dict[str, object]:
    now = timezone.now()
    resolved_policy, thresholds, source = get_effective_lifecycle_thresholds(
        organization=provider_account.organization,
        provider_account=provider_account,
        policy=policy,
    )

    summary = {
        'summary_schema_version': LIFECYCLE_HEALTH_SUMMARY_SCHEMA_VERSION,
        'provider_account_id': provider_account.pk,
        'policy': _serialize_lifecycle_policy(resolved_policy, thresholds, source),
        'sync': _compute_sync_state(provider_account, thresholds=thresholds, now=now),
        'expiry': _count_expiring_objects(provider_account, thresholds=thresholds, now=now),
        'diff': _build_diff_section(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        ),
    }
    publication_rollup = build_publication_health_rollup(
        provider_account,
        policy=resolved_policy,
        now=now,
    )
    publication_health = (
        dict(publication_rollup['publication_health'])
        if publication_rollup is not None
        else _empty_publication_health_summary()
    )
    summary['publication_health'] = publication_health
    summary['publication'] = _build_publication_section(
        provider_account,
        thresholds=thresholds,
        now=now,
    )
    summary['attention_summary'] = _build_attention_summary(summary)
    return summary


_LIFECYCLE_EVENT_ACTIVE_STATUSES = {
    rpki_models.LifecycleHealthEventStatus.OPEN,
    rpki_models.LifecycleHealthEventStatus.REPEATED,
}


def _lifecycle_event_summary_excerpt(summary: Mapping[str, object]) -> dict[str, object]:
    return {
        'summary_schema_version': int(summary.get('summary_schema_version', 0) or 0),
        'policy': dict(summary.get('policy') or {}),
        'sync': dict(summary.get('sync') or {}),
        'expiry': dict(summary.get('expiry') or {}),
        'publication': dict(summary.get('publication') or {}),
        'publication_health': dict(summary.get('publication_health') or {}),
        'diff': dict(summary.get('diff') or {}),
        'attention_summary': dict(summary.get('attention_summary') or {}),
    }


def _lifecycle_event_candidate(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    event_kind: str,
    severity: str,
    dedupe_suffix: str,
    title: str,
    details: Mapping[str, object],
    active: bool,
    summary: Mapping[str, object],
    related_snapshot_id=None,
    related_snapshot_diff_id=None,
) -> dict[str, object]:
    summary_excerpt = _lifecycle_event_summary_excerpt(summary)
    return {
        'provider_account_id': provider_account.pk,
        'organization_id': provider_account.organization_id,
        'policy_id': summary_excerpt['policy'].get('policy_id'),
        'event_kind': event_kind,
        'severity': severity,
        'dedupe_key': f'provider-account:{provider_account.pk}:{dedupe_suffix}',
        'title': title,
        'details': dict(details),
        'active': bool(active),
        'related_snapshot_id': related_snapshot_id,
        'related_snapshot_diff_id': related_snapshot_diff_id,
        'summary_excerpt': summary_excerpt,
        'payload_json': {
            'schema_version': 1,
            'event': {
                'event_kind': event_kind,
                'severity': severity,
                'dedupe_key': f'provider-account:{provider_account.pk}:{dedupe_suffix}',
                'title': title,
                'active': bool(active),
                'details': dict(details),
            },
            'provider_account': {
                'provider_account_id': provider_account.pk,
                'organization_id': provider_account.organization_id,
                'name': provider_account.name,
            },
            'policy': dict(summary_excerpt['policy']),
            'summary': summary_excerpt,
            'links': {
                'provider_account_url': provider_account.get_absolute_url(),
            },
        },
    }


def build_lifecycle_event_candidates(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    summary: Mapping[str, object],
    snapshot: rpki_models.ProviderSnapshot | None = None,
    snapshot_diff: rpki_models.ProviderSnapshotDiff | None = None,
) -> list[dict[str, object]]:
    sync = dict(summary.get('sync') or {})
    expiry = dict(summary.get('expiry') or {})
    publication = dict(summary.get('publication') or {})
    diff = dict(summary.get('diff') or {})

    publication_snapshot_id = publication.get('snapshot_id')
    if snapshot is not None:
        publication_snapshot_id = snapshot.pk

    latest_diff_id = diff.get('latest_diff_id')
    if snapshot_diff is not None:
        latest_diff_id = snapshot_diff.pk

    candidates: list[dict[str, object]] = []

    sync_status = sync.get('status', '')
    if sync_status in {rpki_models.ProviderSyncHealth.FAILED, rpki_models.ProviderSyncHealth.STALE, rpki_models.ProviderSyncHealth.NEVER_SYNCED}:
        event_kind = (
            rpki_models.LifecycleHealthEventKind.SYNC_FAILED
            if sync_status == rpki_models.ProviderSyncHealth.FAILED
            else rpki_models.LifecycleHealthEventKind.SYNC_STALE
        )
        candidates.append(
            _lifecycle_event_candidate(
                provider_account=provider_account,
                event_kind=event_kind,
                severity=(
                    rpki_models.LifecycleHealthEventSeverity.CRITICAL
                    if sync_status == rpki_models.ProviderSyncHealth.FAILED
                    else rpki_models.LifecycleHealthEventSeverity.WARNING
                ),
                dedupe_suffix=f"sync:{sync_status}",
                title=sync.get('status_display', 'Provider sync attention'),
                details=sync,
                active=True,
                summary=summary,
            )
        )

    for expiry_kind, event_kind in (
        ('roas', rpki_models.LifecycleHealthEventKind.ROA_EXPIRING),
        ('certificates', rpki_models.LifecycleHealthEventKind.CERTIFICATE_EXPIRING),
        ('exceptions', rpki_models.LifecycleHealthEventKind.EXCEPTION_EXPIRING),
    ):
        section = dict(expiry.get(expiry_kind) or {})
        count = int(section.get('count', 0) or 0)
        if count <= 0:
            continue
        candidates.append(
            _lifecycle_event_candidate(
                provider_account=provider_account,
                event_kind=event_kind,
                severity=rpki_models.LifecycleHealthEventSeverity.WARNING,
                dedupe_suffix=f'expiry:{expiry_kind}',
                title=f'{expiry_kind.title()} nearing expiry',
                details=section,
                active=True,
                summary=summary,
                related_snapshot_id=publication_snapshot_id,
            )
        )

    publication_attention_count = int(publication.get('attention_count', 0) or 0)
    if publication_attention_count > 0:
        candidates.append(
            _lifecycle_event_candidate(
                provider_account=provider_account,
                event_kind=rpki_models.LifecycleHealthEventKind.PUBLICATION_ATTENTION,
                severity=rpki_models.LifecycleHealthEventSeverity.WARNING,
                dedupe_suffix=f'publication:{publication_snapshot_id or "none"}',
                title='Publication health attention',
                details=publication,
                active=True,
                summary=summary,
                related_snapshot_id=publication_snapshot_id,
            )
        )

    diff_attention_count = int(summary.get('attention_summary', {}).get('diff_attention_count', 0) or 0)
    if diff_attention_count > 0 or any(int(diff.get(key, 0) or 0) > 0 for key in ('records_added', 'records_removed', 'records_changed')):
        candidates.append(
            _lifecycle_event_candidate(
                provider_account=provider_account,
                event_kind=rpki_models.LifecycleHealthEventKind.PUBLICATION_DIFF,
                severity=rpki_models.LifecycleHealthEventSeverity.WARNING,
                dedupe_suffix=f'diff:{latest_diff_id or "none"}',
                title='Publication diff attention',
                details=diff,
                active=True,
                summary=summary,
                related_snapshot_diff_id=latest_diff_id,
            )
        )

    return candidates


def evaluate_lifecycle_health_events(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    summary: Mapping[str, object] | None = None,
    snapshot: rpki_models.ProviderSnapshot | None = None,
    snapshot_diff: rpki_models.ProviderSnapshotDiff | None = None,
) -> dict[str, object]:
    if summary is None:
        visible_snapshot_ids = {snapshot.pk} if snapshot is not None else None
        visible_diff_ids = {snapshot_diff.pk} if snapshot_diff is not None else None
        summary = build_provider_lifecycle_health_summary(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )

    now = timezone.now()
    candidates = build_lifecycle_event_candidates(
        provider_account,
        summary=summary,
        snapshot=snapshot,
        snapshot_diff=snapshot_diff,
    )
    repeat_after_minutes = int(((summary.get('policy') or {}).get('thresholds') or {}).get('alert_repeat_after_minutes', 0) or 0)
    repeat_after_delta = timedelta(minutes=repeat_after_minutes)
    hooks = list(
        rpki_models.LifecycleHealthHook.objects.filter(
            organization=provider_account.organization,
            enabled=True,
        )
        .select_related('organization', 'provider_account', 'policy')
        .order_by('name', 'pk')
    )

    opened = repeated = resolved = 0
    events: list[rpki_models.LifecycleHealthEvent] = []
    for hook in hooks:
        if hook.provider_account_id is not None and hook.provider_account_id != provider_account.pk:
            continue
        if hook.policy_id is not None and hook.policy_id != ((summary.get('policy') or {}).get('policy_id')):
            continue
        allowed_kinds = set(hook.event_kinds_json or [])
        matched_dedupe_keys: set[str] = set()
        for candidate in candidates:
            if allowed_kinds and candidate['event_kind'] not in allowed_kinds:
                continue

            active_event = (
            hook.events.filter(
                    dedupe_key=candidate['dedupe_key'],
                    status__in=_LIFECYCLE_EVENT_ACTIVE_STATUSES,
                )
                .order_by('-last_seen_at', '-created')
                .first()
            )

            if candidate['active']:
                matched_dedupe_keys.add(candidate['dedupe_key'])
                if active_event is None:
                    event = rpki_models.LifecycleHealthEvent.objects.create(
                        name=candidate['title'],
                        organization=provider_account.organization,
                        provider_account=provider_account,
                        policy=hook.policy,
                        hook=hook,
                        related_snapshot_id=candidate['related_snapshot_id'],
                        related_snapshot_diff_id=candidate['related_snapshot_diff_id'],
                        event_kind=candidate['event_kind'],
                        severity=candidate['severity'],
                        status=rpki_models.LifecycleHealthEventStatus.OPEN,
                        dedupe_key=candidate['dedupe_key'],
                        first_seen_at=now,
                        last_seen_at=now,
                        last_emitted_at=now,
                        payload_json=candidate['payload_json'],
                    )
                    opened += 1
                else:
                    event = active_event
                    status = rpki_models.LifecycleHealthEventStatus.OPEN
                    if event.last_emitted_at is None or now - event.last_emitted_at >= repeat_after_delta:
                        status = rpki_models.LifecycleHealthEventStatus.REPEATED
                        event.last_emitted_at = now
                        repeated += 1
                    event.name = candidate['title']
                    event.event_kind = candidate['event_kind']
                    event.severity = candidate['severity']
                    event.status = status
                    event.last_seen_at = now
                    event.related_snapshot_id = candidate['related_snapshot_id']
                    event.related_snapshot_diff_id = candidate['related_snapshot_diff_id']
                    event.payload_json = candidate['payload_json']
                    event.delivery_error = ''
                    event.save(
                        update_fields=(
                            'name',
                            'event_kind',
                            'severity',
                            'status',
                            'last_seen_at',
                            'last_emitted_at',
                            'related_snapshot',
                            'related_snapshot_diff',
                            'payload_json',
                            'delivery_error',
                            'last_updated',
                        )
                    )
                deliver_lifecycle_health_event(event)
                events.append(event)
                continue

        for active_event in hook.events.filter(status__in=_LIFECYCLE_EVENT_ACTIVE_STATUSES).order_by('-last_seen_at', '-created'):
            if active_event.dedupe_key in matched_dedupe_keys:
                continue
            active_event.status = rpki_models.LifecycleHealthEventStatus.RESOLVED
            active_event.resolved_at = now
            active_event.last_seen_at = now
            active_event.delivery_error = ''
            active_event.save(
                update_fields=(
                    'status',
                    'resolved_at',
                    'last_seen_at',
                    'delivery_error',
                    'last_updated',
                )
            )
            deliver_lifecycle_health_event(active_event)
            resolved += 1
            events.append(active_event)

    return {
        'candidate_count': len(candidates),
        'event_count': len(events),
        'opened_count': opened,
        'repeated_count': repeated,
        'resolved_count': resolved,
        'events': events,
    }


def build_lifecycle_health_hook_payload(event: rpki_models.LifecycleHealthEvent) -> dict[str, object]:
    payload_json = dict(event.payload_json or {})
    summary = dict(payload_json.get('summary') or {})
    provider_account = event.provider_account
    policy = dict(summary.get('policy') or {})
    links = dict(payload_json.get('links') or {})
    if provider_account is not None:
        links.setdefault('provider_account_url', provider_account.get_absolute_url())
    if event.related_snapshot is not None:
        links.setdefault('snapshot_url', event.related_snapshot.get_absolute_url())
    if event.related_snapshot_diff is not None:
        links.setdefault('snapshot_diff_url', event.related_snapshot_diff.get_absolute_url())

    return {
        'schema_version': LIFECYCLE_HOOK_PAYLOAD_SCHEMA_VERSION,
        'event': {
            'event_id': event.pk,
            'name': event.name,
            'event_kind': event.event_kind,
            'severity': event.severity,
            'status': event.status,
            'dedupe_key': event.dedupe_key,
            'first_seen_at': _datetime_text(event.first_seen_at),
            'last_seen_at': _datetime_text(event.last_seen_at),
            'last_emitted_at': _datetime_text(event.last_emitted_at),
            'resolved_at': _datetime_text(event.resolved_at),
        },
        'organization': {
            'organization_id': event.organization_id,
            'name': event.organization.name,
        },
        'provider_account': {
            'provider_account_id': provider_account.pk if provider_account is not None else None,
            'name': provider_account.name if provider_account is not None else '',
            'url': provider_account.get_absolute_url() if provider_account is not None else '',
        },
        'policy': policy,
        'summary': summary,
        'links': links,
    }


def deliver_lifecycle_health_event(event: rpki_models.LifecycleHealthEvent) -> dict[str, object]:
    hook = event.hook
    payload = build_lifecycle_health_hook_payload(event)
    body = json.dumps(payload, sort_keys=True, default=str).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'X-NetBox-RPKI-Event': event.event_kind,
        'X-NetBox-RPKI-Signature': hmac.new(
            (hook.secret or '').encode('utf-8'),
            body,
            hashlib.sha256,
        ).hexdigest(),
    }
    request = Request(hook.target_url, data=body, headers=headers, method='POST')

    if event.status == rpki_models.LifecycleHealthEventStatus.RESOLVED and not hook.send_resolved:
        return {'delivered': False, 'skipped': True, 'error': ''}

    try:
        with urlopen(request, timeout=30):
            pass
    except Exception as exc:  # pragma: no cover - exercised via focused tests
        event.delivery_error = str(exc)
        event.save(update_fields=('delivery_error', 'last_updated'))
        return {'delivered': False, 'skipped': False, 'error': event.delivery_error}

    if event.delivery_error:
        event.delivery_error = ''
        event.save(update_fields=('delivery_error', 'last_updated'))
    return {'delivered': True, 'skipped': False, 'error': ''}


def _normalize_date_or_datetime(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            return value
        return timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.make_aware(datetime.combine(value, time.min), timezone.get_current_timezone())


def is_within_lifecycle_expiry_threshold(
    *,
    expires_at: date | datetime | None,
    warning_days: int,
    reference_time: datetime | None = None,
) -> bool:
    normalized_expiry = _normalize_date_or_datetime(expires_at)
    if normalized_expiry is None:
        return False
    reference = reference_time or timezone.now()
    return normalized_expiry <= reference + timedelta(days=int(warning_days))
