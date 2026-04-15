from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_sync_evidence import (
    build_certificate_observation_attention_summary,
    build_publication_point_attention_summary,
    build_signed_object_attention_summary,
)


LIFECYCLE_HEALTH_SUMMARY_SCHEMA_VERSION = 1
LIFECYCLE_TIMELINE_SCHEMA_VERSION = 1
PUBLICATION_HEALTH_SUMMARY_SCHEMA_VERSION = 1
PUBLICATION_DIFF_TIMELINE_SCHEMA_VERSION = 1

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

    roa_count = rpki_models.Roa.objects.filter(
        signed_by__rpki_org=organization,
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
