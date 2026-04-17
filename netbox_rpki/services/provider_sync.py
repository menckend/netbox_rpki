from __future__ import annotations

from collections.abc import Iterable as IterableCollection
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.db import transaction
from django.utils import timezone
from netaddr import IPNetwork

from ipam.models.asns import ASN
from ipam.models.ip import Prefix

from netbox_rpki import models as rpki_models
from netbox_rpki.structured_logging import emit_structured_log
from netbox_rpki.services.provider_adapters import (
    ProviderAdapterLookupError,
    get_provider_adapter,
)
from netbox_rpki.services.lifecycle_reporting import (
    build_snapshot_publication_health_rollup,
    evaluate_lifecycle_health_events,
)
from . import provider_sync_krill
from .provider_sync_contract import build_family_summary, build_provider_sync_summary, family_capability_extra
from .provider_sync_diff import build_latest_provider_snapshot_diff
from .provider_sync_evidence import (
    build_certificate_observation_payload,
    build_publication_point_payload,
    build_signed_object_payload,
)


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
    url = _arin_roa_list_url(provider_account)
    request = Request(
        url,
        headers={'Accept': 'application/xml'},
        method='GET',
    )
    emit_structured_log(
        'provider_sync.arin.fetch.start',
        subsystem='provider_sync',
        debug=True,
        provider_account_id=provider_account.pk,
        provider_type=provider_account.provider_type,
        method='GET',
        url=url,
        headers=dict(request.header_items()),
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode('utf-8')
    except Exception as exc:
        emit_structured_log(
            'provider_sync.arin.fetch.error',
            subsystem='provider_sync',
            level='warning',
            provider_account_id=provider_account.pk,
            provider_type=provider_account.provider_type,
            method='GET',
            url=url,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise
    emit_structured_log(
        'provider_sync.arin.fetch.success',
        subsystem='provider_sync',
        debug=True,
        provider_account_id=provider_account.pk,
        provider_type=provider_account.provider_type,
        method='GET',
        url=url,
        response_text=payload,
    )
    return payload


def _build_unique_uri_lookup(rows: IterableCollection[object], *field_names: str) -> dict[str, object]:
    lookup: dict[str, object] = {}
    ambiguous: set[str] = set()
    for row in rows:
        for field_name in field_names:
            value = getattr(row, field_name, '')
            if not isinstance(value, str):
                continue
            normalized = value.strip()
            if not normalized or normalized in ambiguous:
                continue
            existing = lookup.get(normalized)
            if existing is not None and existing != row:
                ambiguous.add(normalized)
                lookup.pop(normalized, None)
                continue
            lookup[normalized] = row
    return lookup


def _index_unique_match(
    lookup: dict[str, object],
    ambiguous: set[str],
    value: str,
    row: object,
) -> None:
    normalized = value.strip()
    if not normalized or normalized in ambiguous:
        return
    existing = lookup.get(normalized)
    if existing is not None and existing != row:
        ambiguous.add(normalized)
        lookup.pop(normalized, None)
        return
    lookup[normalized] = row


def _match_status(
    value: str,
    *,
    lookup: dict[str, object],
    ambiguous: set[str],
) -> tuple[object | None, str, str]:
    normalized = value.strip()
    if not normalized:
        return None, 'unknown', 'No source identity was available.'
    if normalized in ambiguous:
        return None, 'ambiguous', f'Multiple imported objects matched {normalized}.'
    match = lookup.get(normalized)
    if match is not None:
        return match, 'linked', f'Matched {normalized}.'
    return None, 'unmatched', f'No imported object matched {normalized}.'


def _resolve_authored_publication_point(
    publication_point_record,
    *,
    authored_publication_points_by_uri: dict[str, rpki_models.PublicationPoint],
) -> rpki_models.PublicationPoint | None:
    for candidate in (
        publication_point_record.publication_uri,
        publication_point_record.service_uri,
        publication_point_record.rrdp_notification_uri,
    ):
        normalized = candidate.strip()
        if not normalized:
            continue
        authored_publication_point = authored_publication_points_by_uri.get(normalized)
        if authored_publication_point is not None:
            return authored_publication_point
    return None


def _resolve_authored_signed_object(
    signed_object_record,
    *,
    authored_signed_objects_by_uri: dict[str, rpki_models.SignedObject],
) -> rpki_models.SignedObject | None:
    signed_object_uri = signed_object_record.signed_object_uri.strip()
    if not signed_object_uri:
        return None
    return authored_signed_objects_by_uri.get(signed_object_uri)


def _krill_ssl_context(provider_account: rpki_models.RpkiProviderAccount):
    return provider_sync_krill.krill_ssl_context(provider_account)


def _krill_routes_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    return provider_sync_krill.krill_routes_url(provider_account)


def _krill_aspas_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    return provider_sync_krill.krill_aspas_url(provider_account)


def _fetch_krill_routes_json(provider_account: rpki_models.RpkiProviderAccount) -> list[dict]:
    return provider_sync_krill.fetch_krill_routes_json(provider_account)


def _fetch_krill_aspas_json(provider_account: rpki_models.RpkiProviderAccount) -> list[dict]:
    return provider_sync_krill.fetch_krill_aspas_json(provider_account)


def _fetch_krill_ca_metadata_json(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    return provider_sync_krill.fetch_krill_ca_metadata_json(provider_account)


def _fetch_krill_parent_statuses_json(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    return provider_sync_krill.fetch_krill_parent_statuses_json(provider_account)


def _fetch_krill_parent_contact_payloads(
    provider_account: rpki_models.RpkiProviderAccount,
    parent_handles: Iterable[str],
) -> dict[str, dict[str, object]]:
    return provider_sync_krill.fetch_krill_parent_contact_payloads(provider_account, parent_handles)


def _fetch_krill_child_info_payloads(
    provider_account: rpki_models.RpkiProviderAccount,
    child_handles: Iterable[str],
) -> dict[str, dict[str, object]]:
    return provider_sync_krill.fetch_krill_child_info_payloads(provider_account, child_handles)


def _fetch_krill_child_connections_json(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    return provider_sync_krill.fetch_krill_child_connections_json(provider_account)


def _fetch_krill_repo_details_json(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    return provider_sync_krill.fetch_krill_repo_details_json(provider_account)


def _fetch_krill_repo_status_json(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    return provider_sync_krill.fetch_krill_repo_status_json(provider_account)


def _parse_krill_route_records(route_payload: list[dict]) -> list[provider_sync_krill.KrillRouteAuthorizationRecord]:
    return provider_sync_krill.parse_krill_route_records(route_payload)


def _parse_krill_aspa_records(aspa_payload: list[dict]) -> list[provider_sync_krill.KrillAspaRecord]:
    return provider_sync_krill.parse_krill_aspa_records(aspa_payload)


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


def _resolve_asn(asn_value: int | None):
    if asn_value is None:
        return None
    return ASN.objects.filter(asn=asn_value).first()


def _resource_set_payload(resource_set: provider_sync_krill.KrillResourceSetRecord) -> dict[str, str]:
    return {
        'asn': resource_set.asn_resources,
        'ipv4': resource_set.ipv4_resources,
        'ipv6': resource_set.ipv6_resources,
    }


def _parent_class_payload(class_record: provider_sync_krill.KrillParentClassRecord) -> dict[str, object]:
    return {
        'class_name': class_record.class_name,
        'resources': _resource_set_payload(class_record.resources),
        'not_after': class_record.not_after.isoformat() if class_record.not_after else '',
        'signing_certificate_uri': class_record.signing_certificate_uri,
        'issued_certificate_uris': list(class_record.issued_certificate_uris),
    }


def _published_object_payload(object_record: provider_sync_krill.KrillPublishedObjectRecord) -> dict[str, str]:
    return {
        'uri': object_record.uri,
        'body_base64': object_record.body_base64,
    }


def _bind_signed_object_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    imported_signed_object: rpki_models.ImportedSignedObject,
) -> rpki_models.ExternalObjectReference | None:
    provider_identity = imported_signed_object.signed_object_uri.strip()
    if not provider_identity:
        provider_identity = imported_signed_object.object_hash
    return _bind_external_reference(
        provider_account=provider_account,
        snapshot=snapshot,
        object_type=rpki_models.ExternalObjectType.SIGNED_OBJECT,
        provider_identity=provider_identity,
        external_object_id=imported_signed_object.external_object_id,
        imported_object=imported_signed_object,
    )


def _build_import_name(provider_account: rpki_models.RpkiProviderAccount, record: ArinRoaRecord) -> str:
    label = record.roa_name or record.roa_handle or record.prefix_cidr_text
    asn_value = f'AS{record.origin_asn_value}' if record.origin_asn_value is not None else 'AS?'
    return f'{provider_account.org_handle} {label} {record.prefix_cidr_text} {asn_value}'


def _build_roa_external_reference_identity(
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


def _build_aspa_external_reference_identity(
    *,
    external_object_id: str,
    customer_as_value: int | None,
) -> str:
    normalized_external_id = external_object_id.strip()
    if normalized_external_id:
        return normalized_external_id
    if customer_as_value is None:
        return ''
    return f'AS{customer_as_value}'


def _build_external_reference_name(
    provider_account: rpki_models.RpkiProviderAccount,
    provider_identity: str,
) -> str:
    return f'{provider_account.name} {provider_account.get_provider_type_display()} {provider_identity}'


def _build_generic_external_reference_identity(
    external_object_id: str,
    *fallback_parts: object,
) -> str:
    normalized_external_id = external_object_id.strip()
    if normalized_external_id:
        return normalized_external_id

    normalized_parts = []
    for value in fallback_parts:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            normalized_parts.append(text)
    return '|'.join(normalized_parts)


def _bind_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    object_type: str,
    provider_identity: str,
    external_object_id: str,
    imported_object,
    imported_field_name: str | None = None,
) -> rpki_models.ExternalObjectReference | None:
    if not provider_identity:
        return None

    defaults = {
        'name': _build_external_reference_name(provider_account, provider_identity),
        'organization': provider_account.organization,
        'external_object_id': external_object_id,
        'last_seen_provider_snapshot': snapshot,
        'last_seen_at': snapshot.fetched_at,
    }
    if imported_field_name:
        defaults[imported_field_name] = imported_object

    reference, _ = rpki_models.ExternalObjectReference.objects.update_or_create(
        provider_account=provider_account,
        object_type=object_type,
        provider_identity=provider_identity,
        defaults=defaults,
    )
    imported_object.external_reference = reference
    imported_object.save(update_fields=('external_reference',))
    return reference


def _bind_roa_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    imported_authorization: rpki_models.ImportedRoaAuthorization,
) -> rpki_models.ExternalObjectReference | None:
    provider_identity = _build_roa_external_reference_identity(
        provider_account,
        external_object_id=imported_authorization.external_object_id,
        prefix_cidr_text=imported_authorization.prefix_cidr_text,
        origin_asn_value=imported_authorization.origin_asn_value,
        max_length=imported_authorization.max_length,
    )
    return _bind_external_reference(
        provider_account=provider_account,
        snapshot=snapshot,
        object_type=rpki_models.ExternalObjectType.ROA_AUTHORIZATION,
        provider_identity=provider_identity,
        external_object_id=imported_authorization.external_object_id,
        imported_object=imported_authorization,
        imported_field_name='last_seen_imported_authorization',
    )


def _bind_aspa_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    imported_aspa: rpki_models.ImportedAspa,
) -> rpki_models.ExternalObjectReference | None:
    provider_identity = _build_aspa_external_reference_identity(
        external_object_id=imported_aspa.external_object_id,
        customer_as_value=imported_aspa.customer_as_value,
    )
    return _bind_external_reference(
        provider_account=provider_account,
        snapshot=snapshot,
        object_type=rpki_models.ExternalObjectType.ASPA,
        provider_identity=provider_identity,
        external_object_id=imported_aspa.external_object_id,
        imported_object=imported_aspa,
        imported_field_name='last_seen_imported_aspa',
    )


def _bind_ca_metadata_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    imported_ca_metadata: rpki_models.ImportedCaMetadata,
) -> rpki_models.ExternalObjectReference | None:
    provider_identity = _build_generic_external_reference_identity(
        imported_ca_metadata.external_object_id,
        imported_ca_metadata.ca_handle,
    )
    return _bind_external_reference(
        provider_account=provider_account,
        snapshot=snapshot,
        object_type=rpki_models.ExternalObjectType.CA_METADATA,
        provider_identity=provider_identity,
        external_object_id=imported_ca_metadata.external_object_id,
        imported_object=imported_ca_metadata,
    )


def _bind_parent_link_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    imported_parent_link: rpki_models.ImportedParentLink,
) -> rpki_models.ExternalObjectReference | None:
    provider_identity = _build_generic_external_reference_identity(
        imported_parent_link.external_object_id,
        imported_parent_link.parent_handle,
    )
    return _bind_external_reference(
        provider_account=provider_account,
        snapshot=snapshot,
        object_type=rpki_models.ExternalObjectType.PARENT_LINK,
        provider_identity=provider_identity,
        external_object_id=imported_parent_link.external_object_id,
        imported_object=imported_parent_link,
    )


def _bind_child_link_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    imported_child_link: rpki_models.ImportedChildLink,
) -> rpki_models.ExternalObjectReference | None:
    provider_identity = _build_generic_external_reference_identity(
        imported_child_link.external_object_id,
        imported_child_link.child_handle,
    )
    return _bind_external_reference(
        provider_account=provider_account,
        snapshot=snapshot,
        object_type=rpki_models.ExternalObjectType.CHILD_LINK,
        provider_identity=provider_identity,
        external_object_id=imported_child_link.external_object_id,
        imported_object=imported_child_link,
    )


def _bind_resource_entitlement_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    imported_resource_entitlement: rpki_models.ImportedResourceEntitlement,
) -> rpki_models.ExternalObjectReference | None:
    provider_identity = _build_generic_external_reference_identity(
        imported_resource_entitlement.external_object_id,
        imported_resource_entitlement.entitlement_source,
        imported_resource_entitlement.related_handle,
        imported_resource_entitlement.class_name,
    )
    return _bind_external_reference(
        provider_account=provider_account,
        snapshot=snapshot,
        object_type=rpki_models.ExternalObjectType.RESOURCE_ENTITLEMENT,
        provider_identity=provider_identity,
        external_object_id=imported_resource_entitlement.external_object_id,
        imported_object=imported_resource_entitlement,
    )


def _bind_publication_point_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    imported_publication_point: rpki_models.ImportedPublicationPoint,
) -> rpki_models.ExternalObjectReference | None:
    provider_identity = _build_generic_external_reference_identity(
        imported_publication_point.external_object_id,
        imported_publication_point.service_uri,
        imported_publication_point.publication_uri,
    )
    return _bind_external_reference(
        provider_account=provider_account,
        snapshot=snapshot,
        object_type=rpki_models.ExternalObjectType.PUBLICATION_POINT,
        provider_identity=provider_identity,
        external_object_id=imported_publication_point.external_object_id,
        imported_object=imported_publication_point,
    )


def _bind_certificate_observation_external_reference(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
    imported_certificate_observation: rpki_models.ImportedCertificateObservation,
) -> rpki_models.ExternalObjectReference | None:
    provider_identity = imported_certificate_observation.certificate_key.strip()
    return _bind_external_reference(
        provider_account=provider_account,
        snapshot=snapshot,
        object_type=rpki_models.ExternalObjectType.CERTIFICATE,
        provider_identity=provider_identity,
        external_object_id=imported_certificate_observation.external_object_id,
        imported_object=imported_certificate_observation,
    )


def _certificate_observation_payload(
    observation_record: provider_sync_krill.KrillCertificateObservationRecord,
) -> dict[str, object]:
    return {
        'certificate_uri': observation_record.certificate_uri,
        'publication_uri': observation_record.publication_uri,
        'signed_object_uri': observation_record.signed_object_uri,
        'related_handle': observation_record.related_handle,
        'class_name': observation_record.class_name,
        'subject': observation_record.subject,
        'issuer': observation_record.issuer,
        'serial_number': observation_record.serial_number,
        'not_before': observation_record.not_before.isoformat() if observation_record.not_before else '',
        'not_after': observation_record.not_after.isoformat() if observation_record.not_after else '',
        'sources': [
            {
                'observation_source': source_record.observation_source,
                'certificate_uri': source_record.certificate_uri,
                'publication_uri': source_record.publication_uri,
                'signed_object_uri': source_record.signed_object_uri,
                'related_handle': source_record.related_handle,
                'class_name': source_record.class_name,
                'freshness_status': source_record.freshness_status,
            }
            for source_record in observation_record.source_records
        ],
        'certificate_pem': observation_record.certificate_pem,
        'certificate_der_base64': observation_record.certificate_der_base64,
    }


def _import_arin_records(
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
) -> dict[str, dict[str, object]]:
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
            _bind_roa_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_authorization=imported_authorization,
            )
            imported_count += 1
    return {
        rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS: build_family_summary(
            rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,
            status=rpki_models.ProviderSyncFamilyStatus.COMPLETED,
            counts={
                'records_fetched': len(records),
                'records_imported': imported_count,
            },
        )
    }


def _import_krill_records(
    provider_account: rpki_models.RpkiProviderAccount,
    snapshot: rpki_models.ProviderSnapshot,
) -> dict[str, dict[str, object]]:
    route_payload = _fetch_krill_routes_json(provider_account)
    records = _parse_krill_route_records(route_payload)
    aspa_payload = _fetch_krill_aspas_json(provider_account)
    aspa_records = _parse_krill_aspa_records(aspa_payload)
    ca_metadata_payload = _fetch_krill_ca_metadata_json(provider_account)
    ca_metadata_record = provider_sync_krill.parse_krill_ca_metadata_record(ca_metadata_payload)
    parent_status_payload = _fetch_krill_parent_statuses_json(provider_account)
    parent_handles = list(getattr(ca_metadata_record, 'parent_handles', ()) or ())
    if isinstance(parent_status_payload, dict):
        parent_handles.extend(parent_status_payload.keys())
    parent_contact_payloads = {}
    if parent_handles:
        parent_contact_payloads = _fetch_krill_parent_contact_payloads(provider_account, parent_handles)
    parent_records = provider_sync_krill.parse_krill_parent_link_records(
        parent_status_payload,
        parent_contact_payloads=parent_contact_payloads,
    )
    child_handles = tuple(getattr(ca_metadata_record, 'child_handles', ()) or ())
    child_info_payloads = {}
    if child_handles:
        child_info_payloads = _fetch_krill_child_info_payloads(provider_account, child_handles)
    child_connections_payload = _fetch_krill_child_connections_json(provider_account)
    child_records = provider_sync_krill.parse_krill_child_link_records(
        ca_metadata_payload,
        child_info_payloads=child_info_payloads,
        child_connections_payload=child_connections_payload,
    )
    resource_entitlement_records = provider_sync_krill.parse_krill_resource_entitlement_records(
        ca_metadata_payload=ca_metadata_payload,
        parent_status_payload=parent_status_payload,
        child_info_payloads=child_info_payloads,
    )
    repo_details_payload = _fetch_krill_repo_details_json(provider_account)
    repo_status_payload = _fetch_krill_repo_status_json(provider_account)
    publication_point_records = provider_sync_krill.parse_krill_publication_point_records(
        repo_details_payload=repo_details_payload,
        repo_status_payload=repo_status_payload,
    )
    signed_object_records = provider_sync_krill.parse_krill_signed_object_records(
        repo_details_payload=repo_details_payload,
        repo_status_payload=repo_status_payload,
    )
    certificate_observation_records = provider_sync_krill.parse_krill_certificate_observation_records(
        route_payload=route_payload,
        repo_status_payload=repo_status_payload,
        ca_metadata_payload=ca_metadata_payload,
        parent_status_payload=parent_status_payload,
    )

    imported_count = 0
    imported_aspa_count = 0
    imported_ca_metadata_count = 0
    imported_parent_link_count = 0
    imported_child_link_count = 0
    imported_resource_entitlement_count = 0
    imported_publication_point_count = 0
    imported_signed_object_count = 0
    imported_certificate_observation_count = 0
    authored_publication_points_by_uri: dict[str, rpki_models.PublicationPoint] = {}
    authored_signed_objects_by_uri: dict[str, rpki_models.SignedObject] = {}
    if provider_account.organization_id is not None:
        authored_publication_points_by_uri = _build_unique_uri_lookup(
            rpki_models.PublicationPoint.objects.filter(organization=provider_account.organization).all(),
            'publication_uri',
            'rsync_base_uri',
            'rrdp_notify_uri',
        )
        authored_signed_objects_by_uri = _build_unique_uri_lookup(
            rpki_models.SignedObject.objects.filter(organization=provider_account.organization).all(),
            'object_uri',
        )
    imported_publication_points: dict[str, rpki_models.ImportedPublicationPoint] = {}
    ambiguous_publication_point_uris: set[str] = set()
    imported_signed_objects_by_uri: dict[str, rpki_models.ImportedSignedObject] = {}
    ambiguous_signed_object_uris: set[str] = set()
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
                name=provider_sync_krill.build_krill_import_name(provider_account, record),
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
            _bind_roa_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_authorization=imported_authorization,
            )
            imported_count += 1

        for record in aspa_records:
            customer_as = _resolve_asn(record.customer_as_value)
            authorization_key = rpki_models.ImportedAspa.build_authorization_key(
                customer_as_value=record.customer_as_value,
                external_object_id=record.external_object_id,
            )
            imported_aspa = rpki_models.ImportedAspa.objects.create(
                name=provider_sync_krill.build_krill_aspa_import_name(provider_account, record),
                provider_snapshot=snapshot,
                organization=provider_account.organization,
                authorization_key=authorization_key,
                customer_as=customer_as,
                customer_as_value=record.customer_as_value,
                external_object_id=record.external_object_id,
                payload_json={
                    'provider_type': provider_account.provider_type,
                    'ca_handle': provider_account.ca_handle,
                    'provider_count': len(record.providers),
                },
            )
            _bind_aspa_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_aspa=imported_aspa,
            )
            for provider in record.providers:
                rpki_models.ImportedAspaProvider.objects.create(
                    imported_aspa=imported_aspa,
                    provider_as=_resolve_asn(provider.provider_as_value),
                    provider_as_value=provider.provider_as_value,
                    address_family=provider.address_family,
                    raw_provider_text=provider.raw_provider_text,
                )
            imported_aspa_count += 1

        if ca_metadata_record is not None:
            imported_ca_metadata = rpki_models.ImportedCaMetadata.objects.create(
                name=f'{provider_account.name} {ca_metadata_record.ca_handle} CA Metadata',
                provider_snapshot=snapshot,
                organization=provider_account.organization,
                metadata_key=rpki_models.ImportedCaMetadata.build_metadata_key(
                    ca_handle=ca_metadata_record.ca_handle,
                    external_object_id=ca_metadata_record.external_object_id,
                ),
                ca_handle=ca_metadata_record.ca_handle,
                id_cert_hash=ca_metadata_record.id_cert_hash,
                publication_uri=ca_metadata_record.publication_uri,
                rrdp_notification_uri=ca_metadata_record.rrdp_notification_uri,
                parent_count=ca_metadata_record.parent_count,
                child_count=ca_metadata_record.child_count,
                suspended_child_count=ca_metadata_record.suspended_child_count,
                resource_class_count=ca_metadata_record.resource_class_count,
                external_object_id=ca_metadata_record.external_object_id,
                payload_json={
                    'provider_type': provider_account.provider_type,
                    'ca_handle': provider_account.ca_handle,
                    'parent_handles': list(ca_metadata_record.parent_handles),
                    'child_handles': list(ca_metadata_record.child_handles),
                    'suspended_child_handles': list(ca_metadata_record.suspended_child_handles),
                    'resources': _resource_set_payload(ca_metadata_record.resources),
                    'resource_classes': [
                        {
                            'class_name': class_record.class_name,
                            'parent_handle': class_record.parent_handle,
                            'key_identifier': class_record.key_identifier,
                            'incoming_certificate_uri': class_record.incoming_certificate_uri,
                            'resources': _resource_set_payload(class_record.resources),
                        }
                        for class_record in ca_metadata_record.resource_classes
                    ],
                },
            )
            _bind_ca_metadata_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_ca_metadata=imported_ca_metadata,
            )
            imported_ca_metadata_count += 1

        for record in parent_records:
            imported_parent_link = rpki_models.ImportedParentLink.objects.create(
                name=f'{provider_account.name} Parent {record.parent_handle}',
                provider_snapshot=snapshot,
                organization=provider_account.organization,
                link_key=rpki_models.ImportedParentLink.build_link_key(
                    parent_handle=record.parent_handle,
                    external_object_id=record.external_object_id,
                ),
                parent_handle=record.parent_handle,
                relationship_type=record.relationship_type,
                service_uri=record.service_uri,
                last_exchange_at=record.last_exchange_at,
                last_exchange_result=record.last_exchange_result,
                last_success_at=record.last_success_at,
                external_object_id=record.external_object_id,
                payload_json={
                    'provider_type': provider_account.provider_type,
                    'ca_handle': provider_account.ca_handle,
                    'child_handle': record.child_handle,
                    'id_cert': record.id_cert,
                    'all_resources': _resource_set_payload(record.all_resources),
                    'classes': [_parent_class_payload(class_record) for class_record in record.classes],
                },
            )
            _bind_parent_link_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_parent_link=imported_parent_link,
            )
            imported_parent_link_count += 1

        for record in child_records:
            imported_child_link = rpki_models.ImportedChildLink.objects.create(
                name=f'{provider_account.name} Child {record.child_handle}',
                provider_snapshot=snapshot,
                organization=provider_account.organization,
                link_key=rpki_models.ImportedChildLink.build_link_key(
                    child_handle=record.child_handle,
                    external_object_id=record.external_object_id,
                ),
                child_handle=record.child_handle,
                state=record.state,
                id_cert_hash=record.id_cert_hash,
                user_agent=record.user_agent,
                last_exchange_at=record.last_exchange_at,
                last_exchange_result=record.last_exchange_result,
                external_object_id=record.external_object_id,
                payload_json={
                    'provider_type': provider_account.provider_type,
                    'ca_handle': provider_account.ca_handle,
                    'entitled_resources': _resource_set_payload(record.entitled_resources),
                    'listed_as_child': record.listed_as_child,
                    'listed_as_suspended': record.listed_as_suspended,
                },
            )
            _bind_child_link_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_child_link=imported_child_link,
            )
            imported_child_link_count += 1

        for record in resource_entitlement_records:
            imported_resource_entitlement = rpki_models.ImportedResourceEntitlement.objects.create(
                name=(
                    f'{provider_account.name} Entitlement {record.entitlement_source} '
                    f'{record.related_handle or provider_account.ca_handle}'
                    f'{f" {record.class_name}" if record.class_name else ""}'
                ),
                provider_snapshot=snapshot,
                organization=provider_account.organization,
                entitlement_key=rpki_models.ImportedResourceEntitlement.build_entitlement_key(
                    entitlement_source=record.entitlement_source,
                    related_handle=record.related_handle,
                    class_name=record.class_name,
                    external_object_id=record.external_object_id,
                ),
                entitlement_source=record.entitlement_source,
                related_handle=record.related_handle,
                class_name=record.class_name,
                asn_resources=record.asn_resources,
                ipv4_resources=record.ipv4_resources,
                ipv6_resources=record.ipv6_resources,
                not_after=record.not_after,
                external_object_id=record.external_object_id,
                payload_json={
                    'provider_type': provider_account.provider_type,
                    'ca_handle': provider_account.ca_handle,
                    'resources': {
                        'asn': record.asn_resources,
                        'ipv4': record.ipv4_resources,
                        'ipv6': record.ipv6_resources,
                    },
                },
            )
            _bind_resource_entitlement_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_resource_entitlement=imported_resource_entitlement,
            )
            imported_resource_entitlement_count += 1

        for record in publication_point_records:
            authored_publication_point = _resolve_authored_publication_point(
                record,
                authored_publication_points_by_uri=authored_publication_points_by_uri,
            )
            imported_publication_point = rpki_models.ImportedPublicationPoint.objects.create(
                name=f'{provider_account.name} Publication Point {record.external_object_id or provider_account.ca_handle}',
                provider_snapshot=snapshot,
                organization=provider_account.organization,
                publication_key=rpki_models.ImportedPublicationPoint.build_publication_key(
                    service_uri=record.service_uri,
                    publication_uri=record.publication_uri,
                    external_object_id=record.external_object_id,
                ),
                service_uri=record.service_uri,
                publication_uri=record.publication_uri,
                rrdp_notification_uri=record.rrdp_notification_uri,
                last_exchange_at=record.last_exchange_at,
                last_exchange_result=record.last_exchange_result,
                next_exchange_before=record.next_exchange_before,
                published_object_count=record.published_object_count,
                external_object_id=record.external_object_id,
                authored_publication_point=authored_publication_point,
                payload_json=build_publication_point_payload(
                    provider_account,
                    record,
                    authored_publication_point=authored_publication_point,
                ),
            )
            _bind_publication_point_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_publication_point=imported_publication_point,
            )
            _index_unique_match(
                imported_publication_points,
                ambiguous_publication_point_uris,
                imported_publication_point.publication_uri,
                imported_publication_point,
            )
            _index_unique_match(
                imported_publication_points,
                ambiguous_publication_point_uris,
                imported_publication_point.service_uri,
                imported_publication_point,
            )
            imported_publication_point_count += 1

        for record in signed_object_records:
            publication_point, publication_linkage_status, publication_linkage_reason = _match_status(
                record.publication_uri,
                lookup=imported_publication_points,
                ambiguous=ambiguous_publication_point_uris,
            )
            if publication_point is None and publication_linkage_status != 'ambiguous' and imported_publication_point_count == 1:
                publication_point = next(iter({row.pk: row for row in imported_publication_points.values()}.values()))
                publication_linkage_status = 'singleton_fallback'
                publication_linkage_reason = 'Used the only imported publication point in the snapshot.'
            if publication_point is None:
                raise ProviderSyncError('Krill signed object inventory could not be linked to a publication point.')
            authored_signed_object = _resolve_authored_signed_object(
                record,
                authored_signed_objects_by_uri=authored_signed_objects_by_uri,
            )
            manifest_metadata = (
                provider_sync_krill._parse_cms_manifest_metadata(record.body_base64)
                if record.signed_object_type == rpki_models.SignedObjectType.MANIFEST
                else {}
            )
            crl_metadata = (
                provider_sync_krill._parse_cms_crl_metadata(record.body_base64)
                if record.signed_object_type == rpki_models.SignedObjectType.CRL
                else {}
            )
            imported_signed_object = rpki_models.ImportedSignedObject.objects.create(
                name=f'{provider_account.name} Signed Object {record.signed_object_uri or record.object_hash or record.publication_uri}',
                provider_snapshot=snapshot,
                organization=provider_account.organization,
                publication_point=publication_point,
                signed_object_key=rpki_models.ImportedSignedObject.build_signed_object_key(
                    publication_uri=record.publication_uri,
                    signed_object_uri=record.signed_object_uri,
                    object_hash=record.object_hash,
                ),
                signed_object_type=record.signed_object_type,
                publication_uri=record.publication_uri,
                signed_object_uri=record.signed_object_uri,
                object_hash=record.object_hash,
                body_base64=record.body_base64,
                external_object_id=record.external_object_id,
                authored_signed_object=authored_signed_object,
                payload_json=build_signed_object_payload(
                    provider_account,
                    record,
                    publication_point=publication_point,
                    publication_linkage_status=publication_linkage_status,
                    publication_linkage_reason=publication_linkage_reason,
                    authored_signed_object=authored_signed_object,
                    manifest_metadata=manifest_metadata,
                    crl_metadata=crl_metadata,
                ),
            )
            _bind_signed_object_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_signed_object=imported_signed_object,
            )
            _index_unique_match(
                imported_signed_objects_by_uri,
                ambiguous_signed_object_uris,
                imported_signed_object.signed_object_uri,
                imported_signed_object,
            )
            imported_signed_object_count += 1

        for record in certificate_observation_records:
            is_stale = bool(record.not_after and snapshot.fetched_at and record.not_after <= snapshot.fetched_at)
            linked_signed_object, signed_object_linkage_status, signed_object_linkage_reason = _match_status(
                record.signed_object_uri,
                lookup=imported_signed_objects_by_uri,
                ambiguous=ambiguous_signed_object_uris,
            )
            linked_publication_point, publication_linkage_status, publication_linkage_reason = _match_status(
                record.publication_uri,
                lookup=imported_publication_points,
                ambiguous=ambiguous_publication_point_uris,
            )
            if linked_publication_point is None and linked_signed_object is not None:
                linked_publication_point = linked_signed_object.publication_point
                publication_linkage_status = 'derived_from_signed_object'
                publication_linkage_reason = 'Inherited the imported publication point from the linked signed object.'
            imported_certificate_observation = rpki_models.ImportedCertificateObservation.objects.create(
                name=f'{provider_account.name} Certificate {record.subject or record.certificate_key[:12]}',
                provider_snapshot=snapshot,
                organization=provider_account.organization,
                certificate_key=record.certificate_key,
                observation_source=(
                    record.source_records[0].observation_source
                    if record.source_records
                    else rpki_models.CertificateObservationSource.SIGNED_OBJECT_EE
                ),
                publication_point=linked_publication_point,
                signed_object=linked_signed_object,
                certificate_uri=record.certificate_uri,
                publication_uri=record.publication_uri,
                signed_object_uri=record.signed_object_uri,
                related_handle=record.related_handle,
                class_name=record.class_name,
                subject=record.subject,
                issuer=record.issuer,
                serial_number=record.serial_number,
                not_before=record.not_before,
                not_after=record.not_after,
                external_object_id=record.certificate_key,
                payload_json=build_certificate_observation_payload(
                    record,
                    publication_point=linked_publication_point,
                    publication_linkage_status=publication_linkage_status,
                    publication_linkage_reason=publication_linkage_reason,
                    signed_object=linked_signed_object,
                    signed_object_linkage_status=signed_object_linkage_status,
                    signed_object_linkage_reason=signed_object_linkage_reason,
                ),
                is_stale=is_stale,
            )
            _bind_certificate_observation_external_reference(
                provider_account=provider_account,
                snapshot=snapshot,
                imported_certificate_observation=imported_certificate_observation,
            )
            imported_certificate_observation_count += 1

    return {
        rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS: build_family_summary(
            rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,
            status=rpki_models.ProviderSyncFamilyStatus.COMPLETED,
            counts={
                'records_fetched': len(records),
                'records_imported': imported_count,
            },
        ),
        rpki_models.ProviderSyncFamily.ASPAS: build_family_summary(
            rpki_models.ProviderSyncFamily.ASPAS,
            status=rpki_models.ProviderSyncFamilyStatus.COMPLETED,
            counts={
                'records_fetched': len(aspa_records),
                'records_imported': imported_aspa_count,
            },
        ),
        rpki_models.ProviderSyncFamily.CA_METADATA: build_family_summary(
            rpki_models.ProviderSyncFamily.CA_METADATA,
            status=rpki_models.ProviderSyncFamilyStatus.COMPLETED,
            counts={
                'records_fetched': imported_ca_metadata_count,
                'records_imported': imported_ca_metadata_count,
            },
        ),
        rpki_models.ProviderSyncFamily.PARENT_LINKS: build_family_summary(
            rpki_models.ProviderSyncFamily.PARENT_LINKS,
            status=rpki_models.ProviderSyncFamilyStatus.COMPLETED,
            counts={
                'records_fetched': len(parent_records),
                'records_imported': imported_parent_link_count,
            },
        ),
        rpki_models.ProviderSyncFamily.CHILD_LINKS: build_family_summary(
            rpki_models.ProviderSyncFamily.CHILD_LINKS,
            status=rpki_models.ProviderSyncFamilyStatus.COMPLETED,
            counts={
                'records_fetched': len(child_records),
                'records_imported': imported_child_link_count,
            },
        ),
        rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS: build_family_summary(
            rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS,
            status=rpki_models.ProviderSyncFamilyStatus.COMPLETED,
            counts={
                'records_fetched': len(resource_entitlement_records),
                'records_imported': imported_resource_entitlement_count,
            },
        ),
        rpki_models.ProviderSyncFamily.PUBLICATION_POINTS: build_family_summary(
            rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
            status=rpki_models.ProviderSyncFamilyStatus.COMPLETED,
            counts={
                'records_fetched': len(publication_point_records),
                'records_imported': imported_publication_point_count,
            },
        ),
        rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY: build_family_summary(
            rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY,
            status=rpki_models.ProviderSyncFamilyStatus.COMPLETED,
            counts={
                'records_fetched': len(signed_object_records),
                'records_imported': imported_signed_object_count,
            },
        ),
        rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY: build_family_summary(
            rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY,
            status=rpki_models.ProviderSyncFamilyStatus.LIMITED,
            counts={
                'records_fetched': len(certificate_observation_records),
                'records_imported': imported_certificate_observation_count,
            },
            extra=family_capability_extra(provider_account, rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY),
        ),
    }


def sync_provider_account(
    provider_account: rpki_models.RpkiProviderAccount | int,
    *,
    snapshot_name: str | None = None,
) -> tuple[rpki_models.ProviderSyncRun, rpki_models.ProviderSnapshot]:
    if not isinstance(provider_account, rpki_models.RpkiProviderAccount):
        provider_account = rpki_models.RpkiProviderAccount.objects.select_related('organization').get(pk=provider_account)

    if not provider_account.sync_enabled:
        raise ProviderSyncError(f'Provider account {provider_account.name} is disabled for sync.')
    try:
        adapter = get_provider_adapter(provider_account)
        adapter.validate_sync_account(provider_account)
    except ProviderAdapterLookupError as exc:
        raise ProviderSyncError(str(exc)) from exc
    except ValueError as exc:
        raise ProviderSyncError(str(exc)) from exc

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
        summary_json=build_provider_sync_summary(
            provider_account,
            status=rpki_models.ValidationRunStatus.RUNNING,
            default_supported_status=rpki_models.ProviderSyncFamilyStatus.PENDING,
        ),
    )
    sync_run.provider_snapshot = snapshot
    sync_run.save(update_fields=('provider_snapshot',))

    snapshot_diff = None
    try:
        family_summaries = adapter.sync_inventory(provider_account, snapshot)

        completed_at = timezone.now()
        summary = build_provider_sync_summary(
            provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            family_summaries=family_summaries,
        )
        summary['latest_snapshot_id'] = snapshot.pk
        summary['latest_snapshot_name'] = snapshot.name
        summary['latest_snapshot_completed_at'] = completed_at.isoformat()
        summary['latest_snapshot_status'] = rpki_models.ValidationRunStatus.COMPLETED
        summary['publication_health'] = build_snapshot_publication_health_rollup(snapshot)
        snapshot.status = rpki_models.ValidationRunStatus.COMPLETED
        snapshot.completed_at = completed_at
        snapshot.summary_json = summary
        snapshot.save(update_fields=('status', 'completed_at', 'summary_json'))

        snapshot_diff = build_latest_provider_snapshot_diff(snapshot)
        if snapshot_diff is not None:
            summary['latest_diff_id'] = snapshot_diff.pk
            summary['latest_diff_name'] = snapshot_diff.name
            snapshot.summary_json = summary
            snapshot.save(update_fields=('summary_json',))

        sync_run.status = rpki_models.ValidationRunStatus.COMPLETED
        sync_run.completed_at = completed_at
        sync_run.records_fetched = summary['records_fetched']
        sync_run.records_imported = summary['records_imported']
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
        evaluate_lifecycle_health_events(
            provider_account,
            summary=summary,
            snapshot=snapshot,
            snapshot_diff=snapshot_diff,
        )
        return sync_run, snapshot
    except Exception as exc:
        completed_at = timezone.now()
        error_text = str(exc)
        error_summary = build_provider_sync_summary(
            provider_account,
            status=rpki_models.ValidationRunStatus.FAILED,
            error=error_text,
            default_supported_status=rpki_models.ProviderSyncFamilyStatus.FAILED,
        )
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
