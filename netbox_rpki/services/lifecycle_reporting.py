from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from netbox_rpki import models as rpki_models


LIFECYCLE_HEALTH_SUMMARY_SCHEMA_VERSION = 1

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
) -> dict[str, object]:
    latest_snapshot = (
        provider_account.snapshots
        .filter(status=rpki_models.ValidationRunStatus.COMPLETED)
        .order_by('-fetched_at', '-pk')
        .first()
    )
    if latest_snapshot is None:
        return {
            'available': False,
            'snapshot_id': None,
            'snapshot_name': '',
            'snapshot_fetched_at': '',
            'publication_points': {
                'total': 0,
                'exchange_not_ok': 0,
                'stale': 0,
                'attention_threshold': int(thresholds['publication_exchange_failure_threshold']),
            },
            'certificate_observations': {
                'total': 0,
                'stale': 0,
                'expiring_soon': 0,
            },
            'attention_count': 0,
            'placeholder': True,
        }

    now = timezone.now()
    expiry_window = now + timedelta(days=int(thresholds['certificate_expiry_warning_days']))
    certificate_counts = rpki_models.ImportedCertificateObservation.objects.filter(
        provider_snapshot=latest_snapshot,
    ).aggregate(
        total=Count('pk'),
        stale=Count('pk', filter=Q(is_stale=True)),
        expiring_soon=Count(
            'pk',
            filter=Q(
                is_stale=False,
                not_after__isnull=False,
                not_after__gt=now,
                not_after__lte=expiry_window,
            ),
        ),
    )
    publication_point_counts = rpki_models.ImportedPublicationPoint.objects.filter(
        provider_snapshot=latest_snapshot,
    ).aggregate(
        total=Count('pk'),
        stale=Count('pk', filter=Q(is_stale=True)),
        exchange_not_ok=Count(
            'pk',
            filter=(
                Q(last_exchange_result__isnull=False)
                & ~Q(last_exchange_result='')
                & ~Q(last_exchange_result__iexact='success')
            ),
        ),
    )
    attention_count = 0
    if int(publication_point_counts['exchange_not_ok'] or 0) >= int(thresholds['publication_exchange_failure_threshold']):
        attention_count += 1
    if int(publication_point_counts['stale'] or 0) > 0:
        attention_count += 1
    if int(certificate_counts['stale'] or 0) > 0:
        attention_count += 1

    return {
        'available': True,
        'snapshot_id': latest_snapshot.pk,
        'snapshot_name': latest_snapshot.name,
        'snapshot_fetched_at': _datetime_text(latest_snapshot.fetched_at),
        'publication_points': {
            'total': int(publication_point_counts['total'] or 0),
            'stale': int(publication_point_counts['stale'] or 0),
            'exchange_not_ok': int(publication_point_counts['exchange_not_ok'] or 0),
            'attention_threshold': int(thresholds['publication_exchange_failure_threshold']),
            'stale_after_minutes': int(thresholds['publication_stale_after_minutes']),
        },
        'certificate_observations': {
            'total': int(certificate_counts['total'] or 0),
            'stale': int(certificate_counts['stale'] or 0),
            'expiring_soon': int(certificate_counts['expiring_soon'] or 0),
        },
        'attention_count': attention_count,
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
    diff_section = dict(summary.get('diff') or {})

    expiry_attention_count = sum(
        int((expiry_section.get(key) or {}).get('count', 0) or 0)
        for key in ('roas', 'certificates', 'exceptions')
    )
    publication_attention_count = int(publication_section.get('attention_count', 0) or 0)
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
        'publication': _build_publication_section(provider_account, thresholds=thresholds),
        'diff': _build_diff_section(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        ),
    }
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
