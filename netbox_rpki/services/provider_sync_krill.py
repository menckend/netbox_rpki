from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Iterable, Mapping
import json
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from netbox_rpki import models as rpki_models


class KrillSyncError(ValueError):
    pass


@dataclass(frozen=True)
class KrillResourceSetRecord:
    asn_resources: str = ''
    ipv4_resources: str = ''
    ipv6_resources: str = ''

    @property
    def is_empty(self) -> bool:
        return not any((self.asn_resources, self.ipv4_resources, self.ipv6_resources))


@dataclass(frozen=True)
class KrillExchangeRecord:
    timestamp: datetime | None = None
    uri: str = ''
    result: str = ''
    user_agent: str = ''


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


@dataclass(frozen=True)
class KrillAspaProviderRecord:
    raw_provider_text: str
    provider_as_value: int | None
    address_family: str


@dataclass(frozen=True)
class KrillAspaRecord:
    customer_as_value: int | None
    providers: list[KrillAspaProviderRecord]

    @property
    def external_object_id(self) -> str:
        if self.customer_as_value is None:
            return ''
        return f'AS{self.customer_as_value}'


@dataclass(frozen=True)
class KrillCaResourceClassRecord:
    class_name: str
    parent_handle: str
    key_identifier: str
    incoming_certificate_uri: str
    resources: KrillResourceSetRecord = field(default_factory=KrillResourceSetRecord)


@dataclass(frozen=True)
class KrillCaMetadataRecord:
    ca_handle: str
    id_cert_hash: str
    publication_uri: str
    rrdp_notification_uri: str
    parent_handles: tuple[str, ...] = ()
    child_handles: tuple[str, ...] = ()
    suspended_child_handles: tuple[str, ...] = ()
    resources: KrillResourceSetRecord = field(default_factory=KrillResourceSetRecord)
    resource_classes: tuple[KrillCaResourceClassRecord, ...] = ()

    @property
    def external_object_id(self) -> str:
        return self.ca_handle

    @property
    def parent_count(self) -> int:
        return len(self.parent_handles)

    @property
    def child_count(self) -> int:
        return len(self.child_handles)

    @property
    def suspended_child_count(self) -> int:
        return len(self.suspended_child_handles)

    @property
    def resource_class_count(self) -> int:
        return len(self.resource_classes)


@dataclass(frozen=True)
class KrillParentClassRecord:
    class_name: str
    resources: KrillResourceSetRecord = field(default_factory=KrillResourceSetRecord)
    not_after: datetime | None = None
    signing_certificate_uri: str = ''
    issued_certificate_uris: tuple[str, ...] = ()


@dataclass(frozen=True)
class KrillParentLinkRecord:
    parent_handle: str
    relationship_type: str
    service_uri: str
    last_exchange_at: datetime | None = None
    last_exchange_result: str = ''
    last_success_at: datetime | None = None
    all_resources: KrillResourceSetRecord = field(default_factory=KrillResourceSetRecord)
    classes: tuple[KrillParentClassRecord, ...] = ()
    child_handle: str = ''
    id_cert: str = ''

    @property
    def external_object_id(self) -> str:
        return self.parent_handle


@dataclass(frozen=True)
class KrillChildLinkRecord:
    child_handle: str
    state: str
    id_cert_hash: str = ''
    user_agent: str = ''
    last_exchange_at: datetime | None = None
    last_exchange_result: str = ''
    entitled_resources: KrillResourceSetRecord = field(default_factory=KrillResourceSetRecord)
    listed_as_child: bool = False
    listed_as_suspended: bool = False

    @property
    def external_object_id(self) -> str:
        return self.child_handle


@dataclass(frozen=True)
class KrillResourceEntitlementRecord:
    entitlement_source: str
    related_handle: str
    class_name: str = ''
    resources: KrillResourceSetRecord = field(default_factory=KrillResourceSetRecord)
    not_after: datetime | None = None
    external_object_id: str = ''

    @property
    def asn_resources(self) -> str:
        return self.resources.asn_resources

    @property
    def ipv4_resources(self) -> str:
        return self.resources.ipv4_resources

    @property
    def ipv6_resources(self) -> str:
        return self.resources.ipv6_resources


@dataclass(frozen=True)
class KrillPublishedObjectRecord:
    uri: str
    body_base64: str


@dataclass(frozen=True)
class KrillSignedObjectRecord:
    publication_uri: str
    signed_object_uri: str
    signed_object_type: str
    object_hash: str
    body_base64: str

    @property
    def external_object_id(self) -> str:
        return self.signed_object_uri or self.object_hash


@dataclass(frozen=True)
class KrillPublicationPointRecord:
    service_uri: str = ''
    publication_uri: str = ''
    rrdp_notification_uri: str = ''
    last_exchange_at: datetime | None = None
    last_exchange_result: str = ''
    next_exchange_before: datetime | None = None
    published_objects: tuple[KrillPublishedObjectRecord, ...] = ()

    @property
    def external_object_id(self) -> str:
        return self.service_uri or self.publication_uri

    @property
    def published_object_count(self) -> int:
        return len(self.published_objects)


def _normalized_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value).strip()
    return ''


def _mapping(value) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _sequence(value) -> list[object]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _dedupe_texts(values: Iterable[object]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _normalized_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return tuple(ordered)


def _extract_handles(values) -> tuple[str, ...]:
    handles = []
    for value in _sequence(values):
        if isinstance(value, Mapping):
            handles.append(value.get('handle'))
            continue
        handles.append(value)
    return _dedupe_texts(handles)


def _parse_datetime_text(value) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    if text.endswith('Z'):
        text = f'{text[:-1]}+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_unix_timestamp(value) -> datetime | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _parse_resource_set(value) -> KrillResourceSetRecord:
    resource_mapping = _mapping(value)
    return KrillResourceSetRecord(
        asn_resources=_normalized_text(resource_mapping.get('asn')),
        ipv4_resources=_normalized_text(resource_mapping.get('ipv4')),
        ipv6_resources=_normalized_text(resource_mapping.get('ipv6')),
    )


def _parse_exchange(value) -> KrillExchangeRecord:
    exchange_mapping = _mapping(value)
    return KrillExchangeRecord(
        timestamp=_parse_unix_timestamp(exchange_mapping.get('timestamp')),
        uri=_normalized_text(exchange_mapping.get('uri')),
        result=_normalized_text(exchange_mapping.get('result')),
        user_agent=_normalized_text(exchange_mapping.get('user_agent')),
    )


def _quoted_api_segment(value: str) -> str:
    return quote(str(value).strip(), safe='')


def _krill_ca_api_url(
    provider_account: rpki_models.RpkiProviderAccount,
    *segments: str,
) -> str:
    base_url = provider_account.api_base_url.rstrip('/')
    ca_handle = _quoted_api_segment(provider_account.sync_target_handle)
    api_url = f'{base_url}/api/v1/cas/{ca_handle}'
    if not segments:
        return api_url
    suffix = '/'.join(_quoted_api_segment(segment) for segment in segments)
    return f'{api_url}/{suffix}'


def _krill_get_request(
    provider_account: rpki_models.RpkiProviderAccount,
    url: str,
) -> Request:
    return Request(
        url,
        headers={
            'Accept': 'application/json',
            'Authorization': f'Bearer {provider_account.api_key}',
        },
        method='GET',
    )


def krill_routes_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    return _krill_ca_api_url(provider_account, 'routes')


def krill_aspas_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    return _krill_ca_api_url(provider_account, 'aspas')


def krill_ca_metadata_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    return _krill_ca_api_url(provider_account)


def krill_parent_statuses_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    return _krill_ca_api_url(provider_account, 'parents')


def krill_parent_contact_url(
    provider_account: rpki_models.RpkiProviderAccount,
    parent_handle: str,
) -> str:
    return _krill_ca_api_url(provider_account, 'parents', parent_handle)


def krill_child_info_url(
    provider_account: rpki_models.RpkiProviderAccount,
    child_handle: str,
) -> str:
    return _krill_ca_api_url(provider_account, 'children', child_handle)


def krill_child_connections_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    return _krill_ca_api_url(provider_account, 'stats', 'children', 'connections')


def krill_repo_details_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    return _krill_ca_api_url(provider_account, 'repo')


def krill_repo_status_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    return _krill_ca_api_url(provider_account, 'repo', 'status')


def krill_ssl_context(provider_account: rpki_models.RpkiProviderAccount):
    parsed_url = urlparse(provider_account.api_base_url)
    if parsed_url.hostname in {'localhost', '127.0.0.1', '::1'}:
        return ssl._create_unverified_context()
    return None


def _load_json(request: Request, provider_account: rpki_models.RpkiProviderAccount):
    urlopen_kwargs = {'timeout': 30}
    ssl_context = krill_ssl_context(provider_account)
    if ssl_context is not None:
        urlopen_kwargs['context'] = ssl_context
    with urlopen(request, **urlopen_kwargs) as response:
        return json.loads(response.read().decode('utf-8'))


def _load_json_list(request: Request, provider_account: rpki_models.RpkiProviderAccount) -> list[dict]:
    payload = _load_json(request, provider_account)
    if not isinstance(payload, list):
        raise KrillSyncError('Krill response must be a JSON list.')
    return payload


def _load_json_mapping(request: Request, provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    payload = _load_json(request, provider_account)
    if not isinstance(payload, dict):
        raise KrillSyncError('Krill response must be a JSON object.')
    return payload


def fetch_krill_routes_json(provider_account: rpki_models.RpkiProviderAccount) -> list[dict]:
    return _load_json_list(
        _krill_get_request(provider_account, krill_routes_url(provider_account)),
        provider_account,
    )


def fetch_krill_aspas_json(provider_account: rpki_models.RpkiProviderAccount) -> list[dict]:
    return _load_json_list(
        _krill_get_request(provider_account, krill_aspas_url(provider_account)),
        provider_account,
    )


def fetch_krill_ca_metadata_json(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    return _load_json_mapping(
        _krill_get_request(provider_account, krill_ca_metadata_url(provider_account)),
        provider_account,
    )


def fetch_krill_parent_statuses_json(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    return _load_json_mapping(
        _krill_get_request(provider_account, krill_parent_statuses_url(provider_account)),
        provider_account,
    )


def fetch_krill_parent_contact_json(
    provider_account: rpki_models.RpkiProviderAccount,
    parent_handle: str,
) -> dict[str, object]:
    return _load_json_mapping(
        _krill_get_request(provider_account, krill_parent_contact_url(provider_account, parent_handle)),
        provider_account,
    )


def fetch_krill_parent_contact_payloads(
    provider_account: rpki_models.RpkiProviderAccount,
    parent_handles: Iterable[str],
) -> dict[str, dict[str, object]]:
    payloads: dict[str, dict[str, object]] = {}
    for parent_handle in _dedupe_texts(parent_handles):
        payloads[parent_handle] = fetch_krill_parent_contact_json(provider_account, parent_handle)
    return payloads


def fetch_krill_child_info_json(
    provider_account: rpki_models.RpkiProviderAccount,
    child_handle: str,
) -> dict[str, object]:
    return _load_json_mapping(
        _krill_get_request(provider_account, krill_child_info_url(provider_account, child_handle)),
        provider_account,
    )


def fetch_krill_child_info_payloads(
    provider_account: rpki_models.RpkiProviderAccount,
    child_handles: Iterable[str],
) -> dict[str, dict[str, object]]:
    payloads: dict[str, dict[str, object]] = {}
    for child_handle in _dedupe_texts(child_handles):
        payloads[child_handle] = fetch_krill_child_info_json(provider_account, child_handle)
    return payloads


def fetch_krill_child_connections_json(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    return _load_json_mapping(
        _krill_get_request(provider_account, krill_child_connections_url(provider_account)),
        provider_account,
    )


def fetch_krill_repo_details_json(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    return _load_json_mapping(
        _krill_get_request(provider_account, krill_repo_details_url(provider_account)),
        provider_account,
    )


def fetch_krill_repo_status_json(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    return _load_json_mapping(
        _krill_get_request(provider_account, krill_repo_status_url(provider_account)),
        provider_account,
    )


def parse_krill_route_records(route_payload: list[dict]) -> list[KrillRouteAuthorizationRecord]:
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


def _parse_asn_token(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().upper()
    if not text:
        return None
    if text.startswith('AS'):
        text = text[2:]
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _parse_krill_aspa_provider(provider_value) -> KrillAspaProviderRecord | None:
    raw_text = str(provider_value or '').strip()
    if not raw_text or raw_text == '<none>':
        return None

    address_family = ''
    normalized = raw_text
    if raw_text.endswith('(v4)'):
        address_family = rpki_models.AddressFamily.IPV4
        normalized = raw_text[:-4]
    elif raw_text.endswith('(v6)'):
        address_family = rpki_models.AddressFamily.IPV6
        normalized = raw_text[:-4]

    return KrillAspaProviderRecord(
        raw_provider_text=raw_text,
        provider_as_value=_parse_asn_token(normalized),
        address_family=address_family,
    )


def parse_krill_aspa_records(aspa_payload: list[dict]) -> list[KrillAspaRecord]:
    records = []
    for aspa in aspa_payload:
        if not isinstance(aspa, dict):
            continue
        customer_as_value = _parse_asn_token(aspa.get('customer'))
        providers = []
        for provider in list(aspa.get('providers') or []):
            parsed_provider = _parse_krill_aspa_provider(provider)
            if parsed_provider is not None:
                providers.append(parsed_provider)
        records.append(
            KrillAspaRecord(
                customer_as_value=customer_as_value,
                providers=providers,
            )
        )
    return records


def _parse_krill_ca_resource_classes(payload) -> tuple[KrillCaResourceClassRecord, ...]:
    class_mapping = _mapping(payload)
    records = []
    for fallback_class_name, raw_class_payload in class_mapping.items():
        class_payload = _mapping(raw_class_payload)
        active_key = _mapping(_mapping(class_payload.get('keys')).get('active')).get('active_key')
        active_key_payload = _mapping(active_key)
        incoming_cert = _mapping(active_key_payload.get('incoming_cert'))
        records.append(
            KrillCaResourceClassRecord(
                class_name=_normalized_text(class_payload.get('name_space')) or _normalized_text(fallback_class_name),
                parent_handle=_normalized_text(class_payload.get('parent_handle')),
                key_identifier=_normalized_text(active_key_payload.get('key_id')),
                incoming_certificate_uri=_normalized_text(incoming_cert.get('uri')),
                resources=_parse_resource_set(incoming_cert.get('resources')),
            )
        )
    return tuple(records)


def parse_krill_ca_metadata_record(payload) -> KrillCaMetadataRecord | None:
    ca_payload = _mapping(payload)
    if not ca_payload:
        return None

    repo_info = _mapping(ca_payload.get('repo_info'))
    return KrillCaMetadataRecord(
        ca_handle=_normalized_text(ca_payload.get('handle')),
        id_cert_hash=_normalized_text(_mapping(ca_payload.get('id_cert')).get('hash')),
        publication_uri=_normalized_text(repo_info.get('sia_base')),
        rrdp_notification_uri=_normalized_text(repo_info.get('rrdp_notification_uri')),
        parent_handles=_extract_handles(ca_payload.get('parents')),
        child_handles=_dedupe_texts(_sequence(ca_payload.get('children'))),
        suspended_child_handles=_dedupe_texts(_sequence(ca_payload.get('suspended_children'))),
        resources=_parse_resource_set(ca_payload.get('resources')),
        resource_classes=_parse_krill_ca_resource_classes(ca_payload.get('resource_classes')),
    )


def _parse_krill_parent_classes(payload) -> tuple[KrillParentClassRecord, ...]:
    records = []
    for raw_class_payload in _sequence(payload):
        class_payload = _mapping(raw_class_payload)
        if not class_payload:
            continue
        signing_cert = _mapping(class_payload.get('signing_cert'))
        issued_certificate_uris = []
        for raw_certificate in _sequence(class_payload.get('issued_certs')):
            certificate = _mapping(raw_certificate)
            issued_uri = _normalized_text(certificate.get('uri'))
            if issued_uri:
                issued_certificate_uris.append(issued_uri)
        records.append(
            KrillParentClassRecord(
                class_name=_normalized_text(class_payload.get('class_name')),
                resources=_parse_resource_set(class_payload.get('resource_set')),
                not_after=_parse_datetime_text(class_payload.get('not_after')),
                signing_certificate_uri=_normalized_text(signing_cert.get('url')),
                issued_certificate_uris=tuple(issued_certificate_uris),
            )
        )
    return tuple(records)


def parse_krill_parent_link_records(
    parent_status_payload,
    parent_contact_payloads: Mapping[str, object] | None = None,
) -> list[KrillParentLinkRecord]:
    status_by_handle = _mapping(parent_status_payload)
    contact_by_handle = {
        _normalized_text(handle): value
        for handle, value in dict(parent_contact_payloads or {}).items()
    }

    handles = list(status_by_handle.keys())
    handles.extend(contact_by_handle.keys())
    records = []
    for handle in _dedupe_texts(handles):
        status = _mapping(status_by_handle.get(handle))
        contact = _mapping(contact_by_handle.get(handle))
        parent_handle = handle or _normalized_text(contact.get('parent_handle'))
        if not parent_handle:
            continue
        exchange = _parse_exchange(status.get('last_exchange'))
        records.append(
            KrillParentLinkRecord(
                parent_handle=parent_handle,
                relationship_type=_normalized_text(contact.get('type')),
                service_uri=_normalized_text(contact.get('service_uri')) or exchange.uri,
                last_exchange_at=exchange.timestamp,
                last_exchange_result=exchange.result,
                last_success_at=_parse_unix_timestamp(status.get('last_success')),
                all_resources=_parse_resource_set(status.get('all_resources')),
                classes=_parse_krill_parent_classes(status.get('classes')),
                child_handle=_normalized_text(contact.get('child_handle')),
                id_cert=_normalized_text(contact.get('id_cert')),
            )
        )
    return records


def _child_connection_map(child_connections_payload) -> dict[str, dict[str, object]]:
    payload = _mapping(child_connections_payload)
    children = payload.get('children')
    connections: dict[str, dict[str, object]] = {}
    for raw_child in _sequence(children):
        child = _mapping(raw_child)
        handle = _normalized_text(child.get('handle'))
        if handle:
            connections[handle] = child
    return connections


def parse_krill_child_link_records(
    ca_metadata_payload,
    child_info_payloads: Mapping[str, object] | None = None,
    child_connections_payload=None,
) -> list[KrillChildLinkRecord]:
    ca_metadata = parse_krill_ca_metadata_record(ca_metadata_payload)
    active_handles = ca_metadata.child_handles if ca_metadata is not None else ()
    suspended_handles = ca_metadata.suspended_child_handles if ca_metadata is not None else ()
    info_by_handle = {
        _normalized_text(handle): value
        for handle, value in dict(child_info_payloads or {}).items()
    }
    connection_by_handle = _child_connection_map(child_connections_payload)

    handles = list(active_handles)
    handles.extend(suspended_handles)
    handles.extend(info_by_handle.keys())
    handles.extend(connection_by_handle.keys())

    records = []
    for child_handle in _dedupe_texts(handles):
        info = _mapping(info_by_handle.get(child_handle))
        connection = _mapping(connection_by_handle.get(child_handle))
        exchange = _parse_exchange(connection.get('last_exchange'))
        state = (
            _normalized_text(info.get('state'))
            or _normalized_text(connection.get('state'))
            or ('suspended' if child_handle in suspended_handles else '')
            or ('active' if child_handle in active_handles else '')
        )
        records.append(
            KrillChildLinkRecord(
                child_handle=child_handle,
                state=state,
                id_cert_hash=_normalized_text(_mapping(info.get('id_cert')).get('hash')),
                user_agent=exchange.user_agent,
                last_exchange_at=exchange.timestamp,
                last_exchange_result=exchange.result,
                entitled_resources=_parse_resource_set(info.get('entitled_resources')),
                listed_as_child=child_handle in active_handles,
                listed_as_suspended=child_handle in suspended_handles,
            )
        )
    return records


def parse_krill_resource_entitlement_records(
    ca_metadata_payload=None,
    parent_status_payload=None,
    child_info_payloads: Mapping[str, object] | None = None,
) -> list[KrillResourceEntitlementRecord]:
    records = []

    ca_metadata = parse_krill_ca_metadata_record(ca_metadata_payload)
    if ca_metadata is not None and not ca_metadata.resources.is_empty:
        records.append(
            KrillResourceEntitlementRecord(
                entitlement_source=rpki_models.ImportedResourceEntitlementSource.CA,
                related_handle=ca_metadata.ca_handle,
                resources=ca_metadata.resources,
                external_object_id=ca_metadata.external_object_id,
            )
        )

    for parent_record in parse_krill_parent_link_records(parent_status_payload):
        if not parent_record.all_resources.is_empty:
            records.append(
                KrillResourceEntitlementRecord(
                    entitlement_source=rpki_models.ImportedResourceEntitlementSource.PARENT,
                    related_handle=parent_record.parent_handle,
                    resources=parent_record.all_resources,
                    external_object_id=parent_record.external_object_id,
                )
            )
        for class_record in parent_record.classes:
            if class_record.resources.is_empty and class_record.not_after is None:
                continue
            records.append(
                KrillResourceEntitlementRecord(
                    entitlement_source=rpki_models.ImportedResourceEntitlementSource.PARENT_CLASS,
                    related_handle=parent_record.parent_handle,
                    class_name=class_record.class_name,
                    resources=class_record.resources,
                    not_after=class_record.not_after,
                    external_object_id=f'{parent_record.parent_handle}:{class_record.class_name}',
                )
            )

    child_records = parse_krill_child_link_records({}, child_info_payloads=child_info_payloads)
    for child_record in child_records:
        if child_record.entitled_resources.is_empty:
            continue
        records.append(
            KrillResourceEntitlementRecord(
                entitlement_source=rpki_models.ImportedResourceEntitlementSource.CHILD,
                related_handle=child_record.child_handle,
                resources=child_record.entitled_resources,
                external_object_id=child_record.external_object_id,
            )
        )

    return records


def parse_krill_publication_point_records(
    repo_details_payload=None,
    repo_status_payload=None,
) -> list[KrillPublicationPointRecord]:
    repo_details = _mapping(repo_details_payload)
    repo_status = _mapping(repo_status_payload)
    repo_info = _mapping(repo_details.get('repo_info'))
    exchange = _parse_exchange(repo_status.get('last_exchange'))

    published_objects = []
    for raw_object in _sequence(repo_status.get('published')):
        published_object = _mapping(raw_object)
        publication_uri = _normalized_text(published_object.get('uri'))
        body_base64 = _normalized_text(published_object.get('base64'))
        if not publication_uri and not body_base64:
            continue
        published_objects.append(
            KrillPublishedObjectRecord(
                uri=publication_uri,
                body_base64=body_base64,
            )
        )

    service_uri = _normalized_text(repo_details.get('service_uri')) or exchange.uri
    publication_uri = _normalized_text(repo_info.get('sia_base'))
    rrdp_notification_uri = _normalized_text(repo_info.get('rrdp_notification_uri'))
    next_exchange_before = _parse_unix_timestamp(repo_status.get('next_exchange_before'))
    if not any((service_uri, publication_uri, rrdp_notification_uri, exchange.timestamp, next_exchange_before, published_objects)):
        return []

    return [
        KrillPublicationPointRecord(
            service_uri=service_uri,
            publication_uri=publication_uri,
            rrdp_notification_uri=rrdp_notification_uri,
            last_exchange_at=exchange.timestamp,
            last_exchange_result=exchange.result,
            next_exchange_before=next_exchange_before,
            published_objects=tuple(published_objects),
        )
    ]


def _infer_signed_object_type(uri: str) -> str:
    normalized_uri = uri.lower()
    if normalized_uri.endswith('.roa'):
        return rpki_models.SignedObjectType.ROA
    if normalized_uri.endswith('.mft'):
        return rpki_models.SignedObjectType.MANIFEST
    if normalized_uri.endswith('.asa') or normalized_uri.endswith('.aspa'):
        return rpki_models.SignedObjectType.ASPA
    if normalized_uri.endswith('.rsc'):
        return rpki_models.SignedObjectType.RSC
    if normalized_uri.endswith('.tak'):
        return rpki_models.SignedObjectType.TAK
    return rpki_models.SignedObjectType.OTHER


def _published_object_hash(body_base64: str) -> str:
    if not body_base64:
        return ''
    try:
        decoded_body = base64.b64decode(body_base64.encode('ascii'), validate=True)
    except (ValueError, UnicodeEncodeError, binascii.Error):
        decoded_body = body_base64.encode('utf-8')
    return hashlib.sha256(decoded_body).hexdigest()


def parse_krill_signed_object_records(
    repo_details_payload=None,
    repo_status_payload=None,
) -> list[KrillSignedObjectRecord]:
    repo_details = _mapping(repo_details_payload)
    repo_status = _mapping(repo_status_payload)
    repo_info = _mapping(repo_details.get('repo_info'))
    publication_uri = _normalized_text(repo_info.get('sia_base'))
    published_objects = []
    for raw_object in _sequence(repo_status.get('published')):
        published_object = _mapping(raw_object)
        signed_object_uri = _normalized_text(published_object.get('uri'))
        body_base64 = _normalized_text(published_object.get('base64'))
        if not signed_object_uri and not body_base64:
            continue
        published_objects.append(
            KrillSignedObjectRecord(
                publication_uri=publication_uri,
                signed_object_uri=signed_object_uri,
                signed_object_type=_infer_signed_object_type(signed_object_uri),
                object_hash=_published_object_hash(body_base64),
                body_base64=body_base64,
            )
        )
    return published_objects


def build_krill_import_name(
    provider_account: rpki_models.RpkiProviderAccount,
    record: KrillRouteAuthorizationRecord,
) -> str:
    label = record.comment or record.prefix
    asn_value = f'AS{record.asn}' if record.asn is not None else 'AS?'
    return f'{provider_account.sync_target_handle} {label} {record.prefix} {asn_value}'


def build_krill_aspa_import_name(
    provider_account: rpki_models.RpkiProviderAccount,
    record: KrillAspaRecord,
) -> str:
    customer = f'AS{record.customer_as_value}' if record.customer_as_value is not None else 'AS?'
    return f'{provider_account.sync_target_handle} ASPA {customer}'