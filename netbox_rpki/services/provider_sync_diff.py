from __future__ import annotations

import json

from django.db import transaction
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_sync_contract import (
    build_family_summary,
    combine_family_counts,
    empty_sync_counts,
)


def _roa_identity(row: rpki_models.ImportedRoaAuthorization) -> str:
    if row.external_reference_id and row.external_reference is not None:
        return row.external_reference.provider_identity
    if row.external_object_id:
        return row.external_object_id
    return row.authorization_key


def _roa_state(row: rpki_models.ImportedRoaAuthorization) -> dict[str, object]:
    return {
        'prefix_cidr_text': row.prefix_cidr_text,
        'address_family': row.address_family,
        'origin_asn_value': row.origin_asn_value,
        'max_length': row.max_length,
        'external_object_id': row.external_object_id,
        'is_stale': row.is_stale,
        'payload_json': dict(row.payload_json or {}),
    }


def _aspa_identity(row: rpki_models.ImportedAspa) -> str:
    if row.external_reference_id and row.external_reference is not None:
        return row.external_reference.provider_identity
    if row.external_object_id:
        return row.external_object_id
    return row.authorization_key


def _aspa_provider_values(row: rpki_models.ImportedAspa) -> list[dict[str, object]]:
    return [
        {
            'provider_as_value': provider.provider_as_value,
            'address_family': provider.address_family,
            'raw_provider_text': provider.raw_provider_text,
        }
        for provider in row.provider_authorizations.order_by('provider_as_value', 'address_family', 'raw_provider_text')
    ]


def _aspa_state(row: rpki_models.ImportedAspa) -> dict[str, object]:
    return {
        'customer_as_value': row.customer_as_value,
        'external_object_id': row.external_object_id,
        'is_stale': row.is_stale,
        'payload_json': dict(row.payload_json or {}),
        'providers': _aspa_provider_values(row),
    }


def _normalized_json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _create_diff_item(
    snapshot_diff: rpki_models.ProviderSnapshotDiff,
    *,
    family: str,
    change_type: str,
    name: str,
    provider_identity: str,
    external_reference=None,
    external_object_id: str = '',
    before_state: dict[str, object] | None = None,
    after_state: dict[str, object] | None = None,
    prefix_cidr_text: str = '',
    origin_asn_value: int | None = None,
    customer_as_value: int | None = None,
    provider_as_value: int | None = None,
    related_handle: str = '',
    certificate_identifier: str = '',
    publication_uri: str = '',
    signed_object_uri: str = '',
    is_stale: bool = False,
):
    rpki_models.ProviderSnapshotDiffItem.objects.create(
        name=name,
        snapshot_diff=snapshot_diff,
        object_family=family,
        change_type=change_type,
        external_reference=external_reference,
        provider_identity=provider_identity,
        external_object_id=external_object_id,
        before_state_json=before_state or {},
        after_state_json=after_state or {},
        prefix_cidr_text=prefix_cidr_text,
        origin_asn_value=origin_asn_value,
        customer_as_value=customer_as_value,
        provider_as_value=provider_as_value,
        related_handle=related_handle,
        certificate_identifier=certificate_identifier,
        publication_uri=publication_uri,
        signed_object_uri=signed_object_uri,
        is_stale=is_stale,
    )


def _diff_family(
    snapshot_diff: rpki_models.ProviderSnapshotDiff,
    *,
    family: str,
    before_rows: dict[str, object],
    after_rows: dict[str, object],
    state_builder,
    item_builder,
) -> dict[str, object]:
    counts = empty_sync_counts()
    all_identities = sorted(set(before_rows) | set(after_rows))
    for identity in all_identities:
        before = before_rows.get(identity)
        after = after_rows.get(identity)
        if before is None and after is not None:
            counts['records_added'] += 1
            item_builder(
                snapshot_diff,
                family=family,
                change_type=rpki_models.ProviderSnapshotDiffChangeType.ADDED,
                before=None,
                after=after,
            )
            continue
        if before is not None and after is None:
            counts['records_removed'] += 1
            item_builder(
                snapshot_diff,
                family=family,
                change_type=rpki_models.ProviderSnapshotDiffChangeType.REMOVED,
                before=before,
                after=None,
            )
            continue

        before_state = state_builder(before)
        after_state = state_builder(after)
        if _normalized_json(before_state) == _normalized_json(after_state):
            counts['records_unchanged'] += 1
        else:
            counts['records_changed'] += 1
            item_builder(
                snapshot_diff,
                family=family,
                change_type=rpki_models.ProviderSnapshotDiffChangeType.CHANGED,
                before=before,
                after=after,
            )
        if after is not None and getattr(after, 'is_stale', False):
            counts['records_stale'] += 1

    counts['records_fetched'] = len(after_rows)
    counts['records_imported'] = len(after_rows)
    return build_family_summary(family, status=rpki_models.ProviderSyncFamilyStatus.COMPLETED, counts=counts)


def _build_roa_item(snapshot_diff, *, family, change_type, before, after):
    row = after or before
    before_state = _roa_state(before) if before is not None else {}
    after_state = _roa_state(after) if after is not None else {}
    _create_diff_item(
        snapshot_diff,
        family=family,
        change_type=change_type,
        name=f'{row.name} {change_type.title()}',
        provider_identity=_roa_identity(row),
        external_reference=getattr(row, 'external_reference', None),
        external_object_id=row.external_object_id,
        before_state=before_state,
        after_state=after_state,
        prefix_cidr_text=row.prefix_cidr_text,
        origin_asn_value=row.origin_asn_value,
        is_stale=row.is_stale,
    )


def _build_aspa_item(snapshot_diff, *, family, change_type, before, after):
    row = after or before
    before_state = _aspa_state(before) if before is not None else {}
    after_state = _aspa_state(after) if after is not None else {}
    _create_diff_item(
        snapshot_diff,
        family=family,
        change_type=change_type,
        name=f'{row.name} {change_type.title()}',
        provider_identity=_aspa_identity(row),
        external_reference=getattr(row, 'external_reference', None),
        external_object_id=row.external_object_id,
        before_state=before_state,
        after_state=after_state,
        customer_as_value=row.customer_as_value,
        is_stale=row.is_stale,
    )


def build_provider_snapshot_diff(
    *,
    base_snapshot: rpki_models.ProviderSnapshot,
    comparison_snapshot: rpki_models.ProviderSnapshot,
) -> rpki_models.ProviderSnapshotDiff:
    if base_snapshot.pk == comparison_snapshot.pk:
        raise ValueError('Provider snapshot diffs require two distinct snapshots.')
    if base_snapshot.organization_id != comparison_snapshot.organization_id:
        raise ValueError('Provider snapshot diffs require snapshots from the same organization.')
    if base_snapshot.provider_account_id != comparison_snapshot.provider_account_id:
        raise ValueError('Provider snapshot diffs require snapshots from the same provider account.')

    diff, _ = rpki_models.ProviderSnapshotDiff.objects.get_or_create(
        base_snapshot=base_snapshot,
        comparison_snapshot=comparison_snapshot,
        defaults={
            'name': (
                f'{comparison_snapshot.name} vs {base_snapshot.name}'
            ),
            'organization': comparison_snapshot.organization,
            'provider_account': comparison_snapshot.provider_account,
            'status': rpki_models.ValidationRunStatus.RUNNING,
        },
    )

    with transaction.atomic():
        diff.status = rpki_models.ValidationRunStatus.RUNNING
        diff.error = ''
        diff.save(update_fields=('status', 'error'))
        diff.items.all().delete()

        before_roas = {
            _roa_identity(row): row
            for row in base_snapshot.imported_roa_authorizations.select_related('external_reference').all()
        }
        after_roas = {
            _roa_identity(row): row
            for row in comparison_snapshot.imported_roa_authorizations.select_related('external_reference').all()
        }
        before_aspas = {
            _aspa_identity(row): row
            for row in base_snapshot.imported_aspas.select_related('external_reference').prefetch_related('provider_authorizations').all()
        }
        after_aspas = {
            _aspa_identity(row): row
            for row in comparison_snapshot.imported_aspas.select_related('external_reference').prefetch_related('provider_authorizations').all()
        }

        family_summaries = {
            rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS: _diff_family(
                diff,
                family=rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,
                before_rows=before_roas,
                after_rows=after_roas,
                state_builder=_roa_state,
                item_builder=_build_roa_item,
            ),
            rpki_models.ProviderSyncFamily.ASPAS: _diff_family(
                diff,
                family=rpki_models.ProviderSyncFamily.ASPAS,
                before_rows=before_aspas,
                after_rows=after_aspas,
                state_builder=_aspa_state,
                item_builder=_build_aspa_item,
            ),
        }

        for family in (
            rpki_models.ProviderSyncFamily.CA_METADATA,
            rpki_models.ProviderSyncFamily.PARENT_LINKS,
            rpki_models.ProviderSyncFamily.CHILD_LINKS,
            rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS,
            rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
            rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY,
            rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY,
        ):
            family_summaries[family] = build_family_summary(
                family,
                status=rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED,
            )

        diff.status = rpki_models.ValidationRunStatus.COMPLETED
        diff.compared_at = timezone.now()
        diff.summary_json = {
            'base_snapshot_id': base_snapshot.pk,
            'comparison_snapshot_id': comparison_snapshot.pk,
            'families': family_summaries,
            'totals': combine_family_counts(family_summaries),
        }
        diff.save(update_fields=('status', 'compared_at', 'summary_json'))
    return diff


def build_latest_provider_snapshot_diff(
    comparison_snapshot: rpki_models.ProviderSnapshot,
) -> rpki_models.ProviderSnapshotDiff | None:
    if comparison_snapshot.provider_account_id is None:
        return None
    previous_snapshot = (
        comparison_snapshot.provider_account.snapshots
        .filter(status=rpki_models.ValidationRunStatus.COMPLETED)
        .exclude(pk=comparison_snapshot.pk)
        .order_by('-completed_at', '-fetched_at', '-pk')
        .first()
    )
    if previous_snapshot is None:
        return None
    return build_provider_snapshot_diff(
        base_snapshot=previous_snapshot,
        comparison_snapshot=comparison_snapshot,
    )