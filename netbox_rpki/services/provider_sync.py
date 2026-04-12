from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.db import transaction
from django.utils import timezone
from netaddr import IPNetwork

from ipam.models.asns import ASN
from ipam.models.ip import Prefix

from netbox_rpki import models as rpki_models


class ProviderSyncError(Exception):
    pass


@dataclass(frozen=True)
class ArinRoaRecord:
    roa_handle: str
    roa_name: str
    origin_asn_value: int | None
    not_valid_before: str
    not_valid_after: str
    auto_renewed: bool | None
    start_address: str
    end_address: str
    cidr_length: int
    ip_version: int | None
    max_length: int | None
    auto_linked: bool | None

    @property
    def prefix_cidr_text(self) -> str:
        return str(IPNetwork(f'{self.start_address}/{self.cidr_length}').cidr)

    @property
    def address_family(self) -> str:
        if self.ip_version == 6:
            return rpki_models.AddressFamily.IPV6
        return rpki_models.AddressFamily.IPV4


@dataclass(frozen=True)
class KrillRouteAuthorizationRecord:
    asn: int | None
    prefix: str
    max_length: int | None
    comment: str | None
    roa_objects: list[dict]

    @property
    def address_family(self) -> str:
        return rpki_models.AddressFamily.IPV6 if ':' in self.prefix else rpki_models.AddressFamily.IPV4

    @property
    def external_object_id(self) -> str:
        max_length = self.max_length if self.max_length is not None else ''
        asn = self.asn if self.asn is not None else ''
        return f'{self.prefix}|{max_length}|{asn}'


def _strip_namespace(tag: str) -> str:
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def _child_text(element: ElementTree.Element, child_name: str) -> str:
    for child in list(element):
        if _strip_namespace(child.tag) == child_name:
            return (child.text or '').strip()
    return ''


def _child_bool(element: ElementTree.Element, child_name: str) -> bool | None:
    value = _child_text(element, child_name)
    if not value:
        return None
    return value.lower() == 'true'


def _child_int(element: ElementTree.Element, child_name: str) -> int | None:
    value = _child_text(element, child_name)
    if not value:
        return None
    return int(value)


def _iter_roa_specs(root: ElementTree.Element) -> Iterable[ElementTree.Element]:
    if _strip_namespace(root.tag) == 'roaSpec':
        yield root
    for element in root.iter():
        if element is root:
            continue
        if _strip_namespace(element.tag) == 'roaSpec':
            yield element


def _iter_roa_resources(roa_spec: ElementTree.Element) -> Iterable[ElementTree.Element]:
    for child in list(roa_spec):
        if _strip_namespace(child.tag) != 'resources':
            continue
        grandchildren = list(child)
        if grandchildren:
            for grandchild in grandchildren:
                if _strip_namespace(grandchild.tag) in {'roaSpecResource', 'resources'}:
                    yield grandchild
            continue
        yield child


def _parse_arin_roa_records(xml_text: str) -> list[ArinRoaRecord]:
    root = ElementTree.fromstring(xml_text)
    records = []
    for roa_spec in _iter_roa_specs(root):
        for resource in _iter_roa_resources(roa_spec):
            start_address = _child_text(resource, 'startAddress')
            cidr_length = _child_int(resource, 'cidrLength')
            if not start_address or cidr_length is None:
                continue
            records.append(
                ArinRoaRecord(
                    roa_handle=_child_text(roa_spec, 'roaHandle'),
                    roa_name=_child_text(roa_spec, 'name'),
                    origin_asn_value=_child_int(roa_spec, 'asNumber'),
                    not_valid_before=_child_text(roa_spec, 'notValidBefore'),
                    not_valid_after=_child_text(roa_spec, 'notValidAfter'),
                    auto_renewed=_child_bool(roa_spec, 'autoRenewed'),
                    start_address=start_address,
                    end_address=_child_text(resource, 'endAddress'),
                    cidr_length=cidr_length,
                    ip_version=_child_int(resource, 'ipVersion'),
                    max_length=_child_int(resource, 'maxLength'),
                    auto_linked=_child_bool(resource, 'autoLinked'),
                )
            )
    return records


def _arin_roa_list_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    base_url = provider_account.api_base_url.rstrip('/')
    query = urlencode({'apikey': provider_account.api_key})
    return f'{base_url}/rest/roa/{provider_account.org_handle}?{query}'


def _fetch_arin_roa_xml(provider_account: rpki_models.RpkiProviderAccount) -> str:
    request = Request(
        _arin_roa_list_url(provider_account),
        headers={'Accept': 'application/xml'},
        method='GET',
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode('utf-8')


def _krill_routes_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    base_url = provider_account.api_base_url.rstrip('/')
    ca_handle = provider_account.sync_target_handle
    return f'{base_url}/api/v1/cas/{ca_handle}/routes'


def _krill_ssl_context(provider_account: rpki_models.RpkiProviderAccount):
    parsed_url = urlparse(provider_account.api_base_url)
    if parsed_url.hostname in {'localhost', '127.0.0.1', '::1'}:
        return ssl._create_unverified_context()
    return None


def _fetch_krill_routes_json(provider_account: rpki_models.RpkiProviderAccount) -> list[dict]:
    request = Request(
        _krill_routes_url(provider_account),
        headers={
            'Accept': 'application/json',
            'Authorization': f'Bearer {provider_account.api_key}',
        },
        method='GET',
    )
    urlopen_kwargs = {'timeout': 30}
    ssl_context = _krill_ssl_context(provider_account)
    if ssl_context is not None:
        urlopen_kwargs['context'] = ssl_context
    with urlopen(request, **urlopen_kwargs) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if not isinstance(payload, list):
        raise ProviderSyncError('Krill routes response must be a JSON list.')
    return payload


def _parse_krill_route_records(route_payload: list[dict]) -> list[KrillRouteAuthorizationRecord]:
    records = []
    for route in route_payload:
        if not isinstance(route, dict):
            continue
        prefix = str(route.get('prefix') or '').strip()
        if not prefix:
            continue
        asn_value = route.get('asn')
        try:
            origin_asn_value = int(asn_value) if asn_value is not None else None
        except (TypeError, ValueError):
            origin_asn_value = None
        max_length = route.get('max_length')
        try:
            max_length_value = int(max_length) if max_length is not None else None
        except (TypeError, ValueError):
            max_length_value = None
        comment = route.get('comment')
        records.append(
            KrillRouteAuthorizationRecord(
                asn=origin_asn_value,
                prefix=prefix,
                max_length=max_length_value,
                comment=comment.strip() if isinstance(comment, str) else None,
                roa_objects=list(route.get('roa_objects') or []),
            )
        )
    return records


def _resolve_prefix(prefix_cidr_text: str):
    try:
        network = IPNetwork(prefix_cidr_text).cidr
    except Exception:
        return None
    return Prefix.objects.filter(prefix=network).first()


def _resolve_origin_asn(origin_asn_value: int | None):
    if origin_asn_value is None:
        return None
    return ASN.objects.filter(asn=origin_asn_value).first()


def _build_import_name(provider_account: rpki_models.RpkiProviderAccount, record: ArinRoaRecord) -> str:
    label = record.roa_name or record.roa_handle or record.prefix_cidr_text
    asn_value = f'AS{record.origin_asn_value}' if record.origin_asn_value is not None else 'AS?'
    return f'{provider_account.org_handle} {label} {record.prefix_cidr_text} {asn_value}'


def _build_krill_import_name(
    provider_account: rpki_models.RpkiProviderAccount,
    record: KrillRouteAuthorizationRecord,
) -> str:
    label = record.comment or record.prefix
    asn_value = f'AS{record.asn}' if record.asn is not None else 'AS?'
    return f'{provider_account.sync_target_handle} {label} {record.prefix} {asn_value}'


def _build_snapshot_summary(provider_account: rpki_models.RpkiProviderAccount) -> dict:
    summary = {
        'provider_account_id': provider_account.pk,
        'provider_type': provider_account.provider_type,
        'transport': provider_account.transport,
    }
    if provider_account.org_handle:
        summary['org_handle'] = provider_account.org_handle
    if provider_account.ca_handle:
        summary['ca_handle'] = provider_account.ca_handle
    if provider_account.api_base_url:
        summary['api_base_url'] = provider_account.api_base_url
    return summary


def _build_external_reference_identity(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    external_object_id: str,
    prefix_cidr_text: str,
    origin_asn_value: int | None,
    max_length: int | None,
) -> str:
    normalized_external_id = external_object_id.strip()
    normalized_prefix = prefix_cidr_text.strip().lower()
    if provider_account.provider_type == rpki_models.ProviderType.ARIN and normalized_external_id:
        return f'{normalized_external_id}|{normalized_prefix}'

    if normalized_external_id:
        return normalized_external_id

    return '|'.join(
        str(value)
        for value in (
            normalized_prefix,
            origin_asn_value if origin_asn_value is not None else '',
            max_length if max_length is not None else '',
        )
    )


def _build_external_reference_name(
    provider_account: rpki_models.RpkiProviderAccount,
    provider_identity: str,
) -> str:
    return f'{provider_account.name} {provider_account.get_provider_type_display()} {provider_identity}'


def _bind_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    imported_authorization: rpki_models.ImportedRoaAuthorization,
) -> rpki_models.ExternalObjectReference | None:
    provider_identity = _build_external_reference_identity(
        provider_account,
        external_object_id=imported_authorization.external_object_id,
        prefix_cidr_text=imported_authorization.prefix_cidr_text,
        origin_asn_value=imported_authorization.origin_asn_value,
        max_length=imported_authorization.max_length,
    )
    if not provider_identity:
        return None

    reference, _ = rpki_models.ExternalObjectReference.objects.update_or_create(
        provider_account=provider_account,
        object_type=rpki_models.ExternalObjectType.ROA_AUTHORIZATION,
        provider_identity=provider_identity,
        defaults={
            'name': _build_external_reference_name(provider_account, provider_identity),
            'organization': provider_account.organization,
            'external_object_id': imported_authorization.external_object_id,
            'last_seen_provider_snapshot': snapshot,
            'last_seen_imported_authorization': imported_authorization,
            'last_seen_at': snapshot.fetched_at,
        },
    )
    imported_authorization.external_reference = reference
    imported_authorization.save(update_fields=('external_reference',))
    return reference


def _import_arin_records(
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
) -> tuple[int, int]:
    xml_text = _fetch_arin_roa_xml(provider_account)
    records = _parse_arin_roa_records(xml_text)

    imported_count = 0
    with transaction.atomic():
        for record in records:
            prefix = _resolve_prefix(record.prefix_cidr_text)
            origin_asn = _resolve_origin_asn(record.origin_asn_value)
            authorization_key = rpki_models.ImportedRoaAuthorization.build_authorization_key(
                prefix_cidr_text=record.prefix_cidr_text,
                address_family=record.address_family,
                origin_asn_value=record.origin_asn_value,
                max_length=record.max_length,
                external_object_id=record.roa_handle,
            )
            imported_authorization = rpki_models.ImportedRoaAuthorization.objects.create(
                name=_build_import_name(provider_account, record),
                provider_snapshot=snapshot,
                organization=provider_account.organization,
                authorization_key=authorization_key,
                prefix=prefix,
                prefix_cidr_text=record.prefix_cidr_text,
                address_family=record.address_family,
                origin_asn=origin_asn,
                origin_asn_value=record.origin_asn_value,
                max_length=record.max_length,
                external_object_id=record.roa_handle,
                payload_json={
                    'provider_type': provider_account.provider_type,
                    'org_handle': provider_account.org_handle,
                    'roa_handle': record.roa_handle,
                    'roa_name': record.roa_name,
                    'not_valid_before': record.not_valid_before,
                    'not_valid_after': record.not_valid_after,
                    'auto_renewed': record.auto_renewed,
                    'start_address': record.start_address,
                    'end_address': record.end_address,
                    'cidr_length': record.cidr_length,
                    'ip_version': record.ip_version,
                    'auto_linked': record.auto_linked,
                },
            )
            _bind_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_authorization=imported_authorization,
            )
            imported_count += 1
    return len(records), imported_count


def _import_krill_records(
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
) -> tuple[int, int]:
    route_payload = _fetch_krill_routes_json(provider_account)
    records = _parse_krill_route_records(route_payload)

    imported_count = 0
    with transaction.atomic():
        for record in records:
            prefix = _resolve_prefix(record.prefix)
            origin_asn = _resolve_origin_asn(record.asn)
            authorization_key = rpki_models.ImportedRoaAuthorization.build_authorization_key(
                prefix_cidr_text=record.prefix,
                address_family=record.address_family,
                origin_asn_value=record.asn,
                max_length=record.max_length,
                external_object_id=record.external_object_id,
            )
            imported_authorization = rpki_models.ImportedRoaAuthorization.objects.create(
                name=_build_krill_import_name(provider_account, record),
                provider_snapshot=snapshot,
                organization=provider_account.organization,
                authorization_key=authorization_key,
                prefix=prefix,
                prefix_cidr_text=record.prefix,
                address_family=record.address_family,
                origin_asn=origin_asn,
                origin_asn_value=record.asn,
                max_length=record.max_length,
                external_object_id=record.external_object_id,
                payload_json={
                    'provider_type': provider_account.provider_type,
                    'ca_handle': provider_account.ca_handle,
                    'comment': record.comment,
                    'roa_objects': record.roa_objects,
                },
            )
            _bind_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_authorization=imported_authorization,
            )
            imported_count += 1
    return len(records), imported_count


def sync_provider_account(
    provider_account: rpki_models.RpkiProviderAccount | int,
    *,
    snapshot_name: str | None = None,
) -> tuple[rpki_models.ProviderSyncRun, rpki_models.ProviderSnapshot]:
    if not isinstance(provider_account, rpki_models.RpkiProviderAccount):
        provider_account = rpki_models.RpkiProviderAccount.objects.select_related('organization').get(pk=provider_account)

    if not provider_account.sync_enabled:
        raise ProviderSyncError(f'Provider account {provider_account.name} is disabled for sync.')
    if provider_account.provider_type == rpki_models.ProviderType.KRILL and not provider_account.sync_target_handle:
        raise ProviderSyncError(f'Provider account {provider_account.name} is missing a Krill CA handle.')
    if provider_account.provider_type not in {rpki_models.ProviderType.ARIN, rpki_models.ProviderType.KRILL}:
        raise ProviderSyncError(f'Provider type {provider_account.provider_type} is not supported.')

    now = timezone.now()
    provider_account.last_sync_status = rpki_models.ValidationRunStatus.RUNNING
    provider_account.save(update_fields=('last_sync_status',))
    sync_run = rpki_models.ProviderSyncRun.objects.create(
        name=f'{provider_account.name} Sync {now:%Y-%m-%d %H:%M:%S}',
        organization=provider_account.organization,
        provider_account=provider_account,
        status=rpki_models.ValidationRunStatus.RUNNING,
        started_at=now,
    )
    snapshot = rpki_models.ProviderSnapshot.objects.create(
        name=snapshot_name or f'{provider_account.name} Snapshot {now:%Y-%m-%d %H:%M:%S}',
        provider_account=provider_account,
        organization=provider_account.organization,
        provider_name=provider_account.get_provider_type_display(),
        status=rpki_models.ValidationRunStatus.RUNNING,
        fetched_at=now,
        summary_json=_build_snapshot_summary(provider_account),
    )
    sync_run.provider_snapshot = snapshot
    sync_run.save(update_fields=('provider_snapshot',))

    try:
        if provider_account.provider_type == rpki_models.ProviderType.KRILL:
            fetched_count, imported_count = _import_krill_records(provider_account, snapshot)
        else:
            fetched_count, imported_count = _import_arin_records(provider_account, snapshot)

        completed_at = timezone.now()
        summary = _build_snapshot_summary(provider_account)
        summary.update({
            'records_fetched': fetched_count,
            'records_imported': imported_count,
        })
        snapshot.status = rpki_models.ValidationRunStatus.COMPLETED
        snapshot.completed_at = completed_at
        snapshot.summary_json = summary
        snapshot.save(update_fields=('status', 'completed_at', 'summary_json'))

        sync_run.status = rpki_models.ValidationRunStatus.COMPLETED
        sync_run.completed_at = completed_at
        sync_run.records_fetched = fetched_count
        sync_run.records_imported = imported_count
        sync_run.summary_json = summary
        sync_run.save(
            update_fields=('status', 'completed_at', 'records_fetched', 'records_imported', 'summary_json')
        )

        provider_account.last_successful_sync = completed_at
        provider_account.last_sync_status = rpki_models.ValidationRunStatus.COMPLETED
        provider_account.last_sync_summary_json = summary
        provider_account.save(
            update_fields=('last_successful_sync', 'last_sync_status', 'last_sync_summary_json')
        )
        return sync_run, snapshot
    except Exception as exc:
        completed_at = timezone.now()
        error_text = str(exc)
        error_summary = _build_snapshot_summary(provider_account)
        error_summary['error'] = error_text
        snapshot.status = rpki_models.ValidationRunStatus.FAILED
        snapshot.completed_at = completed_at
        snapshot.summary_json = error_summary
        snapshot.save(update_fields=('status', 'completed_at', 'summary_json'))

        sync_run.status = rpki_models.ValidationRunStatus.FAILED
        sync_run.completed_at = completed_at
        sync_run.error = error_text
        sync_run.summary_json = error_summary
        sync_run.save(update_fields=('status', 'completed_at', 'error', 'summary_json'))

        provider_account.last_sync_status = rpki_models.ValidationRunStatus.FAILED
        provider_account.last_sync_summary_json = error_summary
        provider_account.save(update_fields=('last_sync_status', 'last_sync_summary_json'))
        raise ProviderSyncError(error_text) from exc