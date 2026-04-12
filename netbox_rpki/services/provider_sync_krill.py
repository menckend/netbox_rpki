from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_sync_contract import build_family_summary


class KrillSyncError(ValueError):
    pass


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


def krill_routes_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    base_url = provider_account.api_base_url.rstrip('/')
    ca_handle = provider_account.sync_target_handle
    return f'{base_url}/api/v1/cas/{ca_handle}/routes'


def krill_aspas_url(provider_account: rpki_models.RpkiProviderAccount) -> str:
    base_url = provider_account.api_base_url.rstrip('/')
    ca_handle = provider_account.sync_target_handle
    return f'{base_url}/api/v1/cas/{ca_handle}/aspas'


def krill_ssl_context(provider_account: rpki_models.RpkiProviderAccount):
    parsed_url = urlparse(provider_account.api_base_url)
    if parsed_url.hostname in {'localhost', '127.0.0.1', '::1'}:
        return ssl._create_unverified_context()
    return None


def _load_json(request: Request, provider_account: rpki_models.RpkiProviderAccount) -> list[dict]:
    urlopen_kwargs = {'timeout': 30}
    ssl_context = krill_ssl_context(provider_account)
    if ssl_context is not None:
        urlopen_kwargs['context'] = ssl_context
    with urlopen(request, **urlopen_kwargs) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if not isinstance(payload, list):
        raise KrillSyncError('Krill response must be a JSON list.')
    return payload


def fetch_krill_routes_json(provider_account: rpki_models.RpkiProviderAccount) -> list[dict]:
    request = Request(
        krill_routes_url(provider_account),
        headers={
            'Accept': 'application/json',
            'Authorization': f'Bearer {provider_account.api_key}',
        },
        method='GET',
    )
    return _load_json(request, provider_account)


def fetch_krill_aspas_json(provider_account: rpki_models.RpkiProviderAccount) -> list[dict]:
    request = Request(
        krill_aspas_url(provider_account),
        headers={
            'Accept': 'application/json',
            'Authorization': f'Bearer {provider_account.api_key}',
        },
        method='GET',
    )
    return _load_json(request, provider_account)


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