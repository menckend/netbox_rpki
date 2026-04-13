from __future__ import annotations

from collections.abc import Mapping

from netbox_rpki import models as rpki_models


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


def empty_sync_counts() -> dict[str, int]:
    return {key: 0 for key in PROVIDER_SYNC_COUNT_KEYS}


def supported_sync_families(provider_account: rpki_models.RpkiProviderAccount) -> tuple[str, ...]:
    if provider_account.provider_type == rpki_models.ProviderType.KRILL:
        return (
            rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,
            rpki_models.ProviderSyncFamily.ASPAS,
            rpki_models.ProviderSyncFamily.CA_METADATA,
            rpki_models.ProviderSyncFamily.PARENT_LINKS,
            rpki_models.ProviderSyncFamily.CHILD_LINKS,
            rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS,
            rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
        )
    if provider_account.provider_type == rpki_models.ProviderType.ARIN:
        return (rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,)
    return ()


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
            resolved_family_summaries[family] = dict(family_summaries[family])
            continue

        if family in supported_families:
            resolved_status = default_supported_status or rpki_models.ProviderSyncFamilyStatus.PENDING
        else:
            resolved_status = rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED
        resolved_family_summaries[family] = build_family_summary(family, status=resolved_status)

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

    if provider_account.provider_type == rpki_models.ProviderType.KRILL:
        summary['route_records_fetched'] = roa_family['records_fetched']
        summary['route_records_imported'] = roa_family['records_imported']
        aspa_family = resolved_family_summaries[rpki_models.ProviderSyncFamily.ASPAS]
        summary['aspa_records_fetched'] = aspa_family['records_fetched']
        summary['aspa_records_imported'] = aspa_family['records_imported']

    if extra:
        summary.update(dict(extra))
    return summary