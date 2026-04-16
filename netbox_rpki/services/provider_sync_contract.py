from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from django.db.models import Count

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_adapters import get_provider_adapter
from netbox_rpki.services.lifecycle_reporting import (
    build_provider_lifecycle_health_summary,
    build_publication_health_rollup,
)


PROVIDER_SYNC_SUMMARY_SCHEMA_VERSION = 1
PROVIDER_SYNC_COUNT_KEYS = (
    'records_fetched',
    'records_imported',
    'records_unchanged',
    'records_added',
    'records_removed',
    'records_changed',
    'records_stale',
    'records_failed',
    'warning_count',
    'error_count',
)
PROVIDER_SYNC_FAMILY_ORDER = tuple(choice.value for choice in rpki_models.ProviderSyncFamily)
PROVIDER_SYNC_FAMILY_LABELS = {
    choice.value: choice.label
    for choice in rpki_models.ProviderSyncFamily
}

PROVIDER_SYNC_FAMILY_METADATA = {
    rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS: {
        'family_kind': 'control_plane',
        'evidence_source': 'provider_control_plane',
    },
    rpki_models.ProviderSyncFamily.ASPAS: {
        'family_kind': 'control_plane',
        'evidence_source': 'provider_control_plane',
    },
    rpki_models.ProviderSyncFamily.CA_METADATA: {
        'family_kind': 'control_plane',
        'evidence_source': 'provider_control_plane',
    },
    rpki_models.ProviderSyncFamily.PARENT_LINKS: {
        'family_kind': 'control_plane',
        'evidence_source': 'provider_control_plane',
    },
    rpki_models.ProviderSyncFamily.CHILD_LINKS: {
        'family_kind': 'control_plane',
        'evidence_source': 'provider_control_plane',
    },
    rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS: {
        'family_kind': 'control_plane',
        'evidence_source': 'provider_control_plane',
    },
    rpki_models.ProviderSyncFamily.PUBLICATION_POINTS: {
        'family_kind': 'publication_observation',
        'evidence_source': 'repository_publication',
    },
    rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY: {
        'family_kind': 'publication_observation',
        'evidence_source': 'repository_publication',
    },
    rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY: {
        'family_kind': 'publication_observation',
        'evidence_source': 'repository_publication',
    },
}

def empty_sync_counts() -> dict[str, int]:
    return {key: 0 for key in PROVIDER_SYNC_COUNT_KEYS}


def supported_sync_families(provider_account: rpki_models.RpkiProviderAccount | None) -> tuple[str, ...]:
    if provider_account is None:
        return ()
    return get_provider_adapter(provider_account).supported_sync_families()


def family_capability_extra(
    provider_account: rpki_models.RpkiProviderAccount | None,
    family: str,
) -> dict[str, object]:
    if provider_account is None:
        return {}
    return get_provider_adapter(provider_account).family_capability_extra(family)


def family_default_status(
    provider_account: rpki_models.RpkiProviderAccount | None,
    family: str,
) -> str | None:
    if provider_account is None:
        return None
    return get_provider_adapter(provider_account).family_default_status(family)


def family_metadata(family: str) -> dict[str, object]:
    return dict(PROVIDER_SYNC_FAMILY_METADATA[family])


def build_family_summary(
    family: str,
    *,
    status: str,
    counts: Mapping[str, int] | None = None,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    summary: dict[str, object] = {
        'family': family,
        'label': PROVIDER_SYNC_FAMILY_LABELS[family],
        'status': status,
    }
    summary.update(family_metadata(family))
    summary.update(empty_sync_counts())
    if counts:
        for key in PROVIDER_SYNC_COUNT_KEYS:
            if key in counts:
                summary[key] = int(counts[key])
    if extra:
        summary.update(dict(extra))
    return summary


def combine_family_counts(family_summaries: Mapping[str, Mapping[str, object]]) -> dict[str, int]:
    totals = empty_sync_counts()
    for summary in family_summaries.values():
        for key in PROVIDER_SYNC_COUNT_KEYS:
            totals[key] += int(summary.get(key, 0) or 0)
    return totals


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    return int(summary.get(key, 0) or 0)


def _datetime_text(value) -> str:
    if value in (None, ''):
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _family_rollup(summary: Mapping[str, object], family: str) -> dict[str, object]:
    rollup = dict(summary)
    rollup.update(
        {
            'family': family,
            'label': summary.get('label', PROVIDER_SYNC_FAMILY_LABELS[family]),
            'status': summary.get('status', rpki_models.ProviderSyncFamilyStatus.PENDING),
            'family_kind': summary.get('family_kind', ''),
            'evidence_source': summary.get('evidence_source', ''),
            'records_fetched': _summary_int(summary, 'records_fetched'),
            'records_imported': _summary_int(summary, 'records_imported'),
            'records_unchanged': _summary_int(summary, 'records_unchanged'),
            'records_added': _summary_int(summary, 'records_added'),
            'records_removed': _summary_int(summary, 'records_removed'),
            'records_changed': _summary_int(summary, 'records_changed'),
            'records_stale': _summary_int(summary, 'records_stale'),
            'records_failed': _summary_int(summary, 'records_failed'),
            'warning_count': _summary_int(summary, 'warning_count'),
            'error_count': _summary_int(summary, 'error_count'),
        }
    )
    return rollup


def _resolved_rollup_family_summary(
    provider_account: rpki_models.RpkiProviderAccount | None,
    family: str,
    family_summaries: Mapping[str, object],
    *,
    supported_families: tuple[str, ...],
) -> Mapping[str, object]:
    family_summary = family_summaries.get(family)
    if isinstance(family_summary, Mapping):
        return family_summary

    default_family_status = family_default_status(provider_account, family)
    if default_family_status is not None:
        return build_family_summary(
            family,
            status=default_family_status,
            extra=family_capability_extra(provider_account, family),
        )

    resolved_status = (
        rpki_models.ProviderSyncFamilyStatus.PENDING
        if family in supported_families
        else rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED
    )
    return build_family_summary(
        family,
        status=resolved_status,
        extra=family_capability_extra(provider_account, family),
    )


def _normalized_family_summary(
    provider_account: rpki_models.RpkiProviderAccount,
    family: str,
    summary: Mapping[str, object],
    *,
    supported_families: tuple[str, ...],
    default_supported_status: str | None,
) -> dict[str, object]:
    counts = {
        key: _summary_int(summary, key)
        for key in PROVIDER_SYNC_COUNT_KEYS
        if key in summary
    }
    extra = family_capability_extra(provider_account, family)
    extra.update(
        {
            key: value
            for key, value in summary.items()
            if key not in {'family', 'label', 'status'} and key not in PROVIDER_SYNC_COUNT_KEYS
        }
    )

    status = summary.get('status')
    if not status:
        if family in supported_families and any(counts.values()):
            status = rpki_models.ProviderSyncFamilyStatus.COMPLETED
        elif family in supported_families:
            status = default_supported_status or rpki_models.ProviderSyncFamilyStatus.PENDING
        else:
            status = rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED

    return build_family_summary(family, status=str(status), counts=counts, extra=extra)


def _family_freshness_status(records_imported: int, records_stale: int) -> str:
    if records_imported <= 0:
        return 'empty'
    if records_stale <= 0:
        return 'fresh'
    if records_stale >= records_imported:
        return 'stale'
    return 'mixed'


def _family_freshness_text(records_imported: int, records_stale: int) -> str:
    if records_imported <= 0:
        return 'No imported records'
    if records_stale <= 0:
        return f'All {records_imported} imported records are fresh'
    if records_stale >= records_imported:
        return f'All {records_imported} imported records are stale'
    return f'{records_imported - records_stale} fresh, {records_stale} stale'


def _family_churn_status(records_churned: int) -> str:
    return 'steady' if records_churned <= 0 else 'active'


def _family_churn_text(summary: Mapping[str, object]) -> str:
    records_added = _summary_int(summary, 'records_added')
    records_removed = _summary_int(summary, 'records_removed')
    records_changed = _summary_int(summary, 'records_changed')
    records_churned = records_added + records_removed + records_changed
    if records_churned <= 0:
        return 'No churn'
    return f'{records_added} added, {records_removed} removed, {records_changed} changed'


def _enrich_family_rollup(rollup: Mapping[str, object]) -> dict[str, object]:
    family_rollup = dict(rollup)
    family_rollup['records_active'] = max(
        _summary_int(family_rollup, 'records_imported') - _summary_int(family_rollup, 'records_stale'),
        0,
    )
    family_rollup['records_churned'] = (
        _summary_int(family_rollup, 'records_added')
        + _summary_int(family_rollup, 'records_removed')
        + _summary_int(family_rollup, 'records_changed')
    )
    family_rollup['freshness_status'] = _family_freshness_status(
        _summary_int(family_rollup, 'records_imported'),
        _summary_int(family_rollup, 'records_stale'),
    )
    family_rollup['freshness_text'] = _family_freshness_text(
        _summary_int(family_rollup, 'records_imported'),
        _summary_int(family_rollup, 'records_stale'),
    )
    family_rollup['churn_status'] = _family_churn_status(_summary_int(family_rollup, 'records_churned'))
    family_rollup['churn_text'] = _family_churn_text(family_rollup)
    return family_rollup


def _family_status_counts(family_rollups: list[Mapping[str, object]]) -> dict[str, int]:
    return dict(Counter(str(rollup['status']) for rollup in family_rollups))


def _sanitize_related_reference(value: object, *, visible_ids: set[object] | None) -> object:
    if value in (None, '') or visible_ids is None:
        return value
    if value in visible_ids:
        return value
    return None


def build_provider_family_rollups(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    summary: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    summary = dict(summary or {})
    family_summaries = summary.get('families') or {}
    supported_families = tuple(summary.get('supported_families') or supported_sync_families(provider_account))
    family_order = list(summary.get('family_order') or PROVIDER_SYNC_FAMILY_ORDER)
    family_rollups: list[dict[str, object]] = []

    for family in family_order:
        family_summary = _resolved_rollup_family_summary(
            provider_account,
            family,
            family_summaries,
            supported_families=supported_families,
        )
        rollup = _family_rollup(family_summary, family)
        family_rollups.append(_enrich_family_rollup(rollup))

    return family_rollups


def build_provider_snapshot_diff_rollup(
    snapshot_diff: rpki_models.ProviderSnapshotDiff,
    *,
    summary: Mapping[str, object] | None = None,
) -> dict[str, object]:
    summary = dict(summary or snapshot_diff.summary_json or {})
    family_rollups = build_provider_family_rollups(snapshot_diff.provider_account, summary=summary)
    totals = dict(summary.get('totals') or combine_family_counts(summary.get('families') or {}))

    return {
        'snapshot_diff_id': snapshot_diff.pk,
        'snapshot_diff_name': snapshot_diff.name,
        'provider_account_id': snapshot_diff.provider_account_id,
        'base_snapshot_id': snapshot_diff.base_snapshot_id,
        'comparison_snapshot_id': snapshot_diff.comparison_snapshot_id,
        'status': summary.get('status', snapshot_diff.status),
        'family_order': list(summary.get('family_order') or PROVIDER_SYNC_FAMILY_ORDER),
        'supported_families': list(summary.get('supported_families') or supported_sync_families(snapshot_diff.provider_account)),
        'family_count': len(family_rollups),
        'family_rollups': family_rollups,
        'family_status_counts': _family_status_counts(family_rollups),
        'totals': totals,
        'records_fetched': _summary_int(totals, 'records_fetched'),
        'records_imported': _summary_int(totals, 'records_imported'),
        'records_unchanged': _summary_int(totals, 'records_unchanged'),
        'records_added': _summary_int(totals, 'records_added'),
        'records_removed': _summary_int(totals, 'records_removed'),
        'records_changed': _summary_int(totals, 'records_changed'),
        'records_stale': _summary_int(totals, 'records_stale'),
        'records_failed': _summary_int(totals, 'records_failed'),
        'warning_count': _summary_int(totals, 'warning_count'),
        'error_count': _summary_int(totals, 'error_count'),
        'item_count': snapshot_diff.items.count(),
    }


def build_provider_snapshot_rollup(
    snapshot: rpki_models.ProviderSnapshot,
    *,
    summary: Mapping[str, object] | None = None,
    visible_diff_ids: set[object] | None = None,
) -> dict[str, object]:
    summary = dict(summary or snapshot.summary_json or {})
    family_rollups = build_provider_family_rollups(snapshot.provider_account, summary=summary)
    totals = dict(summary.get('totals') or combine_family_counts(summary.get('families') or {}))
    latest_diff = snapshot.diffs_as_comparison.order_by('-compared_at', '-created').first()
    latest_diff_summary = None

    if latest_diff is not None and (visible_diff_ids is None or latest_diff.pk in visible_diff_ids):
        latest_diff_summary = build_provider_snapshot_diff_rollup(latest_diff)

    return {
        'snapshot_id': snapshot.pk,
        'snapshot_name': snapshot.name,
        'provider_account_id': snapshot.provider_account_id,
        'status': summary.get('status', snapshot.status),
        'summary_schema_version': summary.get('summary_schema_version'),
        'family_order': list(summary.get('family_order') or PROVIDER_SYNC_FAMILY_ORDER),
        'supported_families': list(summary.get('supported_families') or supported_sync_families(snapshot.provider_account)),
        'family_count': len(family_rollups),
        'family_rollups': family_rollups,
        'family_status_counts': _family_status_counts(family_rollups),
        'totals': totals,
        'records_fetched': _summary_int(totals, 'records_fetched'),
        'records_imported': _summary_int(totals, 'records_imported'),
        'records_unchanged': _summary_int(totals, 'records_unchanged'),
        'records_added': _summary_int(totals, 'records_added'),
        'records_removed': _summary_int(totals, 'records_removed'),
        'records_changed': _summary_int(totals, 'records_changed'),
        'records_stale': _summary_int(totals, 'records_stale'),
        'records_failed': _summary_int(totals, 'records_failed'),
        'warning_count': _summary_int(totals, 'warning_count'),
        'error_count': _summary_int(totals, 'error_count'),
        'latest_diff_summary': latest_diff_summary,
    }


def build_provider_account_rollup(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    summary: Mapping[str, object] | None = None,
    visible_snapshot_ids: set[object] | None = None,
    visible_diff_ids: set[object] | None = None,
) -> dict[str, object]:
    summary = dict(summary or provider_account.last_sync_summary_json or {})
    supported_families = tuple(summary.get('supported_families') or supported_sync_families(provider_account))
    family_order = list(summary.get('family_order') or PROVIDER_SYNC_FAMILY_ORDER)
    family_rollups = build_provider_family_rollups(provider_account, summary=summary)
    family_status_counts = _family_status_counts(family_rollups)

    latest_snapshot_id = _sanitize_related_reference(
        summary.get('latest_snapshot_id'),
        visible_ids=visible_snapshot_ids,
    )
    latest_diff_id = _sanitize_related_reference(
        summary.get('latest_diff_id'),
        visible_ids=visible_diff_ids,
    )
    latest_snapshot_name = summary.get('latest_snapshot_name', '') if latest_snapshot_id is not None else ''
    latest_snapshot_completed_at = summary.get('latest_snapshot_completed_at', '') if latest_snapshot_id is not None else ''
    latest_diff_name = summary.get('latest_diff_name', '') if latest_diff_id is not None else ''
    publication_health = dict(summary.get('publication_health') or {})
    if not publication_health:
        publication_rollup = build_publication_health_rollup(provider_account)
        if publication_rollup is not None:
            publication_health = dict(publication_rollup['publication_health'])

    return {
        'provider_account_id': provider_account.pk,
        'provider_account_name': provider_account.name,
        'organization_id': provider_account.organization_id,
        'organization_name': str(provider_account.organization),
        'provider_type': provider_account.provider_type,
        'transport': provider_account.transport,
        'org_handle': provider_account.org_handle,
        'ca_handle': provider_account.ca_handle,
        'sync_enabled': provider_account.sync_enabled,
        'sync_health': provider_account.sync_health,
        'sync_health_display': provider_account.sync_health_display,
        'sync_due': provider_account.is_sync_due(),
        'last_sync_status': provider_account.last_sync_status,
        'last_successful_sync': _datetime_text(provider_account.last_successful_sync),
        'next_sync_due_at': _datetime_text(provider_account.next_sync_due_at),
        'summary_schema_version': summary.get('summary_schema_version'),
        'summary_status': summary.get('status'),
        'summary_error': summary.get('error', ''),
        'records_fetched': _summary_int(summary, 'records_fetched'),
        'records_imported': _summary_int(summary, 'records_imported'),
        'records_unchanged': _summary_int(summary, 'records_unchanged'),
        'records_added': _summary_int(summary, 'records_added'),
        'records_removed': _summary_int(summary, 'records_removed'),
        'records_changed': _summary_int(summary, 'records_changed'),
        'records_stale': _summary_int(summary, 'records_stale'),
        'records_failed': _summary_int(summary, 'records_failed'),
        'warning_count': _summary_int(summary, 'warning_count'),
        'error_count': _summary_int(summary, 'error_count'),
        'supported_families': list(supported_families),
        'supported_family_count': len(supported_families),
        'family_order': family_order,
        'family_count': len(family_rollups),
        'family_rollups': family_rollups,
        'family_status_counts': dict(family_status_counts),
        'latest_snapshot_id': latest_snapshot_id,
        'latest_snapshot_name': latest_snapshot_name,
        'latest_snapshot_completed_at': latest_snapshot_completed_at,
        'latest_diff_id': latest_diff_id,
        'latest_diff_name': latest_diff_name,
        'publication_health': publication_health,
        'lifecycle_health_summary': build_provider_lifecycle_health_summary(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        ),
    }


def build_provider_account_pub_obs_rollup(
    provider_account: rpki_models.RpkiProviderAccount,
) -> dict[str, object] | None:
    rollup = build_publication_health_rollup(provider_account)
    if rollup is None:
        return None

    return {
        'snapshot_id': rollup['snapshot_id'],
        'snapshot_name': rollup['snapshot_name'],
        'snapshot_fetched_at': rollup['snapshot_fetched_at'],
        'snapshot_completed_at': rollup['snapshot_completed_at'],
        'publication_health': dict(rollup['publication_health']),
        'publication_points': dict(rollup['publication_points']),
        'signed_objects': dict(rollup['signed_objects']),
        'certificate_observations': {
            **dict(rollup['certificate_observations']),
        },
        'attention_item_count': int(rollup['attention_item_count']),
    }


def build_snapshot_signed_object_type_breakdown(
    snapshot: rpki_models.ProviderSnapshot,
) -> dict[str, int]:
    rows = (
        rpki_models.ImportedSignedObject.objects
        .filter(provider_snapshot=snapshot)
        .values('signed_object_type')
        .annotate(count=Count('pk'))
        .order_by('signed_object_type')
    )
    return {
        str(row['signed_object_type']): int(row['count'])
        for row in rows
        if row['signed_object_type']
    }


def build_provider_account_summary(
    provider_accounts,
    *,
    visible_snapshot_ids: set[object] | None = None,
    visible_diff_ids: set[object] | None = None,
) -> dict[str, object]:
    by_provider_type: dict[str, int] = {}
    by_sync_health: dict[str, int] = {}
    by_family_status: dict[str, int] = {}
    sync_due_count = 0
    roa_write_supported_count = 0
    aspa_write_supported_count = 0
    latest_snapshot_count = 0
    latest_diff_count = 0
    accounts = []

    for provider_account in provider_accounts:
        by_provider_type[provider_account.provider_type] = by_provider_type.get(provider_account.provider_type, 0) + 1
        by_sync_health[provider_account.sync_health] = by_sync_health.get(provider_account.sync_health, 0) + 1
        if provider_account.is_sync_due():
            sync_due_count += 1
        if provider_account.supports_roa_write:
            roa_write_supported_count += 1
        if provider_account.supports_aspa_write:
            aspa_write_supported_count += 1
        rollup = build_provider_account_rollup(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        accounts.append(rollup)
        if rollup['latest_snapshot_id'] is not None:
            latest_snapshot_count += 1
        if rollup['latest_diff_id'] is not None:
            latest_diff_count += 1
        for status, count in rollup['family_status_counts'].items():
            by_family_status[status] = by_family_status.get(status, 0) + count

    return {
        'total_accounts': len(accounts),
        'by_provider_type': by_provider_type,
        'by_sync_health': by_sync_health,
        'by_family_status': by_family_status,
        'sync_due_count': sync_due_count,
        'roa_write_supported_count': roa_write_supported_count,
        'aspa_write_supported_count': aspa_write_supported_count,
        'latest_snapshot_count': latest_snapshot_count,
        'latest_diff_count': latest_diff_count,
        'accounts': accounts,
    }


def build_provider_sync_summary(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    status: str,
    family_summaries: Mapping[str, Mapping[str, object]] | None = None,
    error: str = '',
    default_supported_status: str | None = None,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    family_summaries = dict(family_summaries or {})
    supported_families = supported_sync_families(provider_account)
    resolved_family_summaries: dict[str, dict[str, object]] = {}
    for family in PROVIDER_SYNC_FAMILY_ORDER:
        if family in family_summaries:
            resolved_family_summaries[family] = _normalized_family_summary(
                provider_account,
                family,
                family_summaries[family],
                supported_families=supported_families,
                default_supported_status=default_supported_status,
            )
            continue

        default_family_status = family_default_status(provider_account, family)
        if default_family_status is not None:
            resolved_family_summaries[family] = build_family_summary(
                family,
                status=default_family_status,
                extra=family_capability_extra(provider_account, family),
            )
            continue

        if family in supported_families:
            resolved_status = default_supported_status or rpki_models.ProviderSyncFamilyStatus.PENDING
        else:
            resolved_status = rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED
        resolved_family_summaries[family] = build_family_summary(
            family,
            status=resolved_status,
            extra=family_capability_extra(provider_account, family),
        )

    family_rollups = build_provider_family_rollups(
        provider_account,
        summary={
            'families': resolved_family_summaries,
            'family_order': PROVIDER_SYNC_FAMILY_ORDER,
            'supported_families': supported_families,
        },
    )
    family_status_counts = _family_status_counts(family_rollups)
    totals = combine_family_counts(resolved_family_summaries)
    summary: dict[str, object] = {
        'summary_schema_version': PROVIDER_SYNC_SUMMARY_SCHEMA_VERSION,
        'provider_account_id': provider_account.pk,
        'provider_type': provider_account.provider_type,
        'transport': provider_account.transport,
        'status': status,
        'supported_families': list(supported_families),
        'family_order': list(PROVIDER_SYNC_FAMILY_ORDER),
        'families': resolved_family_summaries,
        'family_rollups': family_rollups,
        'family_status_counts': family_status_counts,
        'totals': totals,
    }
    if provider_account.org_handle:
        summary['org_handle'] = provider_account.org_handle
    if provider_account.ca_handle:
        summary['ca_handle'] = provider_account.ca_handle
    if provider_account.api_base_url:
        summary['api_base_url'] = provider_account.api_base_url
    if error:
        summary['error'] = error
    summary.update(totals)

    roa_family = resolved_family_summaries[rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS]
    summary['roa_authorization_records_fetched'] = roa_family['records_fetched']
    summary['roa_authorization_records_imported'] = roa_family['records_imported']
    get_provider_adapter(provider_account).augment_sync_summary(summary, resolved_family_summaries)

    if extra:
        summary.update(dict(extra))
    return summary
