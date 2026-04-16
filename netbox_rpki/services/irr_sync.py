from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from ipaddress import ip_network
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from netbox_rpki import models as rpki_models


IRR_FAMILY_ORDER = (
    'route',
    'route6',
    'route_set',
    'route_set_member',
    'as_set',
    'as_set_member',
    'aut_num',
    'mntner',
)

IRRD_GRAPHQL_QUERY = """
query Slice1Inventory($sources: [String!], $objectClass: [String!], $recordLimit: Int) {
  rpslObjects(sources: $sources, objectClass: $objectClass, recordLimit: $recordLimit) {
    objectClass
    rpslPk
    source
    objectText
    updated
    ... on RPSLRoute {
      route
      origin
      memberOf
      mntBy
    }
    ... on RPSLRoute6 {
      route6
      origin
      memberOf
      mntBy
    }
    ... on RPSLRouteSet {
      routeSet
      members
      mpMembers
      mntBy
      adminC
      techC
    }
    ... on RPSLAsSet {
      asSet
      members
      mntBy
      adminC
      techC
    }
    ... on RPSLAutNum {
      autNum
      asName
      import
      export
      mntBy
      adminC
      techC
    }
    ... on RPSLMntner {
      mntner
      auth
      adminC
      updTo
      mntBy
    }
  }
}
""".strip()


class IrrSyncError(Exception):
    pass


@dataclass(frozen=True)
class ParsedRpslObject:
    object_class: str
    rpsl_pk: str
    attributes: dict[str, list[str]]
    object_text: str


def sync_irr_source(
    irr_source: rpki_models.IrrSource,
    *,
    fetch_mode: str = rpki_models.IrrFetchMode.LIVE_QUERY,
    snapshot_file: str | None = None,
):
    started_at = timezone.now()
    snapshot = rpki_models.IrrSnapshot.objects.create(
        name=_build_snapshot_name(irr_source, started_at),
        source=irr_source,
        status=rpki_models.IrrSnapshotStatus.RUNNING,
        fetch_mode=fetch_mode,
        started_at=started_at,
    )
    rpki_models.IrrSource.objects.filter(pk=irr_source.pk).update(
        last_attempted_at=started_at,
        last_sync_status=rpki_models.IrrSnapshotStatus.RUNNING,
    )

    try:
        batch = build_irr_inventory_batch(
            irr_source,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        snapshot = persist_irr_snapshot(snapshot, batch)
    except Exception as exc:
        completed_at = timezone.now()
        error_text = str(exc)
        snapshot.status = rpki_models.IrrSnapshotStatus.FAILED
        snapshot.completed_at = completed_at
        snapshot.error_text = error_text
        snapshot.summary_json = _build_failed_snapshot_summary(
            irr_source=irr_source,
            fetch_mode=fetch_mode,
            error_text=error_text,
        )
        snapshot.save(update_fields=('status', 'completed_at', 'error_text', 'summary_json'))
        irr_source.last_attempted_at = started_at
        irr_source.last_sync_status = rpki_models.IrrSnapshotStatus.FAILED
        irr_source.last_sync_summary_json = snapshot.summary_json
        irr_source.save(update_fields=('last_attempted_at', 'last_sync_status', 'last_sync_summary_json'))
        raise

    return snapshot


def build_irr_inventory_batch(
    irr_source: rpki_models.IrrSource,
    *,
    fetch_mode: str,
    snapshot_file: str | None = None,
) -> dict:
    if fetch_mode == rpki_models.IrrFetchMode.LIVE_QUERY:
        if irr_source.source_family == rpki_models.IrrSourceFamily.IRRD_COMPATIBLE:
            return _fetch_irrd_compatible_live_batch(irr_source)
        raise IrrSyncError(f'IRR source family {irr_source.source_family} is not implemented yet.')
    if fetch_mode == rpki_models.IrrFetchMode.SNAPSHOT_IMPORT:
        if not snapshot_file:
            raise IrrSyncError('snapshot_file is required when fetch_mode=snapshot_import.')
        return _build_snapshot_import_batch(irr_source, snapshot_file=snapshot_file)
    raise IrrSyncError(f'Unknown fetch mode: {fetch_mode}')


def persist_irr_snapshot(snapshot: rpki_models.IrrSnapshot, batch: dict):
    snapshot_metadata = batch['snapshot_metadata']
    completed_at = timezone.now()
    summary_json = _build_snapshot_summary(batch)
    errors = list(snapshot_metadata.get('errors') or [])
    partial = bool(errors)
    snapshot_status = rpki_models.IrrSnapshotStatus.PARTIAL if partial else rpki_models.IrrSnapshotStatus.COMPLETED

    with transaction.atomic():
        snapshot.status = snapshot_status
        snapshot.completed_at = completed_at
        snapshot.source_serial = str(snapshot_metadata.get('source_serial') or '')
        snapshot.source_last_modified = _parse_timestamp(snapshot_metadata.get('source_last_modified'))
        snapshot.source_fingerprint = snapshot_metadata.get('source_fingerprint') or ''
        snapshot.error_text = '\n'.join(errors)
        snapshot.summary_json = summary_json
        snapshot.save(
            update_fields=(
                'status',
                'completed_at',
                'source_serial',
                'source_last_modified',
                'source_fingerprint',
                'error_text',
                'summary_json',
            )
        )
        persisted = _persist_imported_rows(snapshot, batch)

        source = snapshot.source
        source.last_attempted_at = snapshot.started_at
        source.last_sync_status = snapshot.status
        source.summary_json = batch.get('source_metadata') or {}
        source.last_sync_summary_json = summary_json
        if snapshot.status in {
            rpki_models.IrrSnapshotStatus.COMPLETED,
            rpki_models.IrrSnapshotStatus.PARTIAL,
        }:
            source.last_successful_snapshot = snapshot
        source.save(
            update_fields=(
                'last_attempted_at',
                'last_sync_status',
                'summary_json',
                'last_sync_summary_json',
                'last_successful_snapshot',
            )
        )

    summary_json['persisted_counts'] = persisted
    snapshot.summary_json = summary_json
    snapshot.save(update_fields=('summary_json',))
    return snapshot


def _fetch_irrd_compatible_live_batch(irr_source: rpki_models.IrrSource) -> dict:
    sources = [irr_source.default_database_label] if irr_source.default_database_label else None
    graphql_payload = {
        'query': IRRD_GRAPHQL_QUERY,
        'variables': {
            'sources': sources,
            'objectClass': ['route', 'route6', 'route-set', 'as-set', 'aut-num', 'mntner'],
            'recordLimit': 5000,
        },
    }
    response = _http_json_request(
        _join_url(irr_source.query_base_url, 'graphql/'),
        method='POST',
        payload=graphql_payload,
        username=irr_source.http_username or None,
        password=irr_source.http_password or None,
    )
    if response.get('errors'):
        raise IrrSyncError(f'IRRd GraphQL query failed: {response["errors"]}')

    status_payload = _http_text_request(
        _join_url(
            irr_source.query_base_url,
            f'v1/whois/?q=!J{(irr_source.default_database_label or "-*")}',
        ),
        username=irr_source.http_username or None,
        password=irr_source.http_password or None,
    )
    try:
        status_data = json.loads(status_payload)
    except json.JSONDecodeError as exc:
        raise IrrSyncError('IRRd status query did not return valid JSON.') from exc

    parsed_objects = response.get('data', {}).get('rpslObjects', [])
    source_status = _select_irrd_source_status(status_data, irr_source.default_database_label)
    return _normalize_graphql_batch(
        irr_source=irr_source,
        parsed_objects=parsed_objects,
        fetch_mode=rpki_models.IrrFetchMode.LIVE_QUERY,
        source_status=source_status,
    )


def _build_snapshot_import_batch(irr_source: rpki_models.IrrSource, *, snapshot_file: str) -> dict:
    snapshot_path = Path(snapshot_file)
    if not snapshot_path.is_file():
        raise IrrSyncError(f'Snapshot file does not exist: {snapshot_file}')
    parsed_objects = [
        _parsed_object_to_graphql_shape(parsed)
        for parsed in _parse_rpsl_objects(snapshot_path.read_text())
    ]
    return _normalize_graphql_batch(
        irr_source=irr_source,
        parsed_objects=parsed_objects,
        fetch_mode=rpki_models.IrrFetchMode.SNAPSHOT_IMPORT,
        source_status={},
    )


def _normalize_graphql_batch(
    *,
    irr_source: rpki_models.IrrSource,
    parsed_objects: list[dict],
    fetch_mode: str,
    source_status: dict,
) -> dict:
    batch = _build_empty_batch(irr_source=irr_source, fetch_mode=fetch_mode, source_status=source_status)
    route_set_member_map: dict[str, dict] = {}
    as_set_member_map: dict[str, dict] = {}
    route_set_records: dict[str, dict] = {}
    as_set_records: dict[str, dict] = {}
    fingerprint_parts: list[str] = []

    for obj in parsed_objects:
        object_class = (obj.get('objectClass') or '').replace('-', '_')
        object_text = obj.get('objectText') or ''
        if not object_class or object_class not in {'route', 'route6', 'route_set', 'as_set', 'aut_num', 'mntner'}:
            continue
        fingerprint_parts.append(object_text)
        if object_class in {'route', 'route6'}:
            route_record = _normalize_route_object(obj)
            batch['families'][object_class].append(route_record)
            for route_set_name in route_record['summary']['route_set_names_json']:
                member_stable_key = f'route_set:{route_set_name}|{route_record["summary"]["prefix"]}'
                route_set_member_map[member_stable_key] = {
                    'rpsl_object_class': 'route-set-member',
                    'rpsl_pk': member_stable_key.split(':', 1)[1],
                    'stable_key': member_stable_key,
                    'source_database_label': route_record['source_database_label'],
                    'object_text': route_record['object_text'],
                    'payload_json': {
                        'derived_from_route': route_record['stable_key'],
                    },
                    'summary': {
                        'parent_set_name': route_set_name,
                        'member_text': route_record['summary']['prefix'],
                        'member_type': rpki_models.IrrMemberType.PREFIX,
                        'normalized_prefix': route_record['summary']['prefix'],
                        'normalized_set_name': '',
                    },
                }
        elif object_class == 'route_set':
            route_set_record = _normalize_route_set(obj)
            route_set_records[route_set_record['summary']['set_name']] = route_set_record
            batch['families']['route_set'].append(route_set_record)
            for member_text in (obj.get('members') or []) + (obj.get('mpMembers') or []):
                normalized = _normalize_member(member_text)
                member_stable_key = f'{route_set_record["stable_key"]}|{member_text}'
                route_set_member_map[member_stable_key] = {
                    'rpsl_object_class': 'route-set-member',
                    'rpsl_pk': member_stable_key.split(':', 1)[1],
                    'stable_key': member_stable_key,
                    'source_database_label': route_set_record['source_database_label'],
                    'object_text': route_set_record['object_text'],
                    'payload_json': {
                        'derived_from_route_set': route_set_record['stable_key'],
                    },
                    'summary': {
                        'parent_set_name': route_set_record['summary']['set_name'],
                        'member_text': member_text,
                        'member_type': normalized['member_type'],
                        'normalized_prefix': normalized.get('normalized_prefix', ''),
                        'normalized_set_name': normalized.get('normalized_set_name', ''),
                    },
                }
        elif object_class == 'as_set':
            as_set_record = _normalize_as_set(obj)
            as_set_records[as_set_record['summary']['set_name']] = as_set_record
            batch['families']['as_set'].append(as_set_record)
            for member_text in obj.get('members') or []:
                normalized = _normalize_member(member_text)
                member_stable_key = f'{as_set_record["stable_key"]}|{member_text}'
                as_set_member_map[member_stable_key] = {
                    'rpsl_object_class': 'as-set-member',
                    'rpsl_pk': member_stable_key.split(':', 1)[1],
                    'stable_key': member_stable_key,
                    'source_database_label': as_set_record['source_database_label'],
                    'object_text': as_set_record['object_text'],
                    'payload_json': {
                        'derived_from_as_set': as_set_record['stable_key'],
                    },
                    'summary': {
                        'parent_set_name': as_set_record['summary']['set_name'],
                        'member_text': member_text,
                        'member_type': normalized['member_type'],
                        'normalized_asn': normalized.get('normalized_asn', ''),
                        'normalized_set_name': normalized.get('normalized_set_name', ''),
                    },
                }
        elif object_class == 'aut_num':
            batch['families']['aut_num'].append(_normalize_aut_num(obj))
        elif object_class == 'mntner':
            batch['families']['mntner'].append(_normalize_maintainer(obj))

    batch['families']['route_set_member'].extend(route_set_member_map.values())
    batch['families']['as_set_member'].extend(as_set_member_map.values())

    for route_set_record in batch['families']['route_set']:
        set_name = route_set_record['summary']['set_name']
        route_set_record['summary']['member_count'] = sum(
            1 for member in batch['families']['route_set_member']
            if member['summary']['parent_set_name'] == set_name
        )
    for as_set_record in batch['families']['as_set']:
        set_name = as_set_record['summary']['set_name']
        as_set_record['summary']['member_count'] = sum(
            1 for member in batch['families']['as_set_member']
            if member['summary']['parent_set_name'] == set_name
        )

    batch['snapshot_metadata']['source_fingerprint'] = hashlib.sha256(
        ''.join(sorted(fingerprint_parts)).encode('utf-8')
    ).hexdigest() if fingerprint_parts else ''
    return batch


def _persist_imported_rows(snapshot: rpki_models.IrrSnapshot, batch: dict) -> dict[str, int]:
    source = snapshot.source
    persisted_counts: dict[str, int] = {}

    route_sets_by_name: dict[str, rpki_models.ImportedIrrRouteSet] = {}
    as_sets_by_name: dict[str, rpki_models.ImportedIrrAsSet] = {}

    persisted_counts['route'] = 0
    for record in batch['families']['route']:
        rpki_models.ImportedIrrRouteObject.objects.create(
            name=record['stable_key'],
            snapshot=snapshot,
            source=source,
            rpsl_object_class=record['rpsl_object_class'],
            rpsl_pk=record['rpsl_pk'],
            stable_key=record['stable_key'],
            object_text=record['object_text'],
            payload_json=record['payload_json'],
            source_database_label=record['source_database_label'],
            address_family=record['summary']['address_family'],
            prefix=record['summary']['prefix'],
            origin_asn=record['summary']['origin_asn'],
            route_set_names_json=record['summary']['route_set_names_json'],
            maintainer_names_json=record['summary']['maintainer_names_json'],
        )
        persisted_counts['route'] += 1

    persisted_counts['route6'] = 0
    for record in batch['families']['route6']:
        rpki_models.ImportedIrrRouteObject.objects.create(
            name=record['stable_key'],
            snapshot=snapshot,
            source=source,
            rpsl_object_class=record['rpsl_object_class'],
            rpsl_pk=record['rpsl_pk'],
            stable_key=record['stable_key'],
            object_text=record['object_text'],
            payload_json=record['payload_json'],
            source_database_label=record['source_database_label'],
            address_family=record['summary']['address_family'],
            prefix=record['summary']['prefix'],
            origin_asn=record['summary']['origin_asn'],
            route_set_names_json=record['summary']['route_set_names_json'],
            maintainer_names_json=record['summary']['maintainer_names_json'],
        )
        persisted_counts['route6'] += 1

    persisted_counts['route_set'] = 0
    for record in batch['families']['route_set']:
        instance = rpki_models.ImportedIrrRouteSet.objects.create(
            name=record['stable_key'],
            snapshot=snapshot,
            source=source,
            rpsl_object_class=record['rpsl_object_class'],
            rpsl_pk=record['rpsl_pk'],
            stable_key=record['stable_key'],
            object_text=record['object_text'],
            payload_json=record['payload_json'],
            source_database_label=record['source_database_label'],
            set_name=record['summary']['set_name'],
            maintainer_names_json=record['summary']['maintainer_names_json'],
            member_count=record['summary']['member_count'],
        )
        route_sets_by_name[instance.set_name] = instance
        persisted_counts['route_set'] += 1

    persisted_counts['route_set_member'] = 0
    for record in batch['families']['route_set_member']:
        rpki_models.ImportedIrrRouteSetMember.objects.create(
            name=record['stable_key'],
            snapshot=snapshot,
            source=source,
            parent_route_set=route_sets_by_name[record['summary']['parent_set_name']],
            rpsl_object_class=record['rpsl_object_class'],
            rpsl_pk=record['rpsl_pk'],
            stable_key=record['stable_key'],
            object_text=record['object_text'],
            payload_json=record['payload_json'],
            source_database_label=record['source_database_label'],
            member_text=record['summary']['member_text'],
            member_type=record['summary']['member_type'],
            normalized_prefix=record['summary'].get('normalized_prefix', ''),
            normalized_set_name=record['summary'].get('normalized_set_name', ''),
        )
        persisted_counts['route_set_member'] += 1

    persisted_counts['as_set'] = 0
    for record in batch['families']['as_set']:
        instance = rpki_models.ImportedIrrAsSet.objects.create(
            name=record['stable_key'],
            snapshot=snapshot,
            source=source,
            rpsl_object_class=record['rpsl_object_class'],
            rpsl_pk=record['rpsl_pk'],
            stable_key=record['stable_key'],
            object_text=record['object_text'],
            payload_json=record['payload_json'],
            source_database_label=record['source_database_label'],
            set_name=record['summary']['set_name'],
            maintainer_names_json=record['summary']['maintainer_names_json'],
            member_count=record['summary']['member_count'],
        )
        as_sets_by_name[instance.set_name] = instance
        persisted_counts['as_set'] += 1

    persisted_counts['as_set_member'] = 0
    for record in batch['families']['as_set_member']:
        rpki_models.ImportedIrrAsSetMember.objects.create(
            name=record['stable_key'],
            snapshot=snapshot,
            source=source,
            parent_as_set=as_sets_by_name[record['summary']['parent_set_name']],
            rpsl_object_class=record['rpsl_object_class'],
            rpsl_pk=record['rpsl_pk'],
            stable_key=record['stable_key'],
            object_text=record['object_text'],
            payload_json=record['payload_json'],
            source_database_label=record['source_database_label'],
            member_text=record['summary']['member_text'],
            member_type=record['summary']['member_type'],
            normalized_asn=record['summary'].get('normalized_asn', ''),
            normalized_set_name=record['summary'].get('normalized_set_name', ''),
        )
        persisted_counts['as_set_member'] += 1

    persisted_counts['aut_num'] = 0
    for record in batch['families']['aut_num']:
        rpki_models.ImportedIrrAutNum.objects.create(
            name=record['stable_key'],
            snapshot=snapshot,
            source=source,
            rpsl_object_class=record['rpsl_object_class'],
            rpsl_pk=record['rpsl_pk'],
            stable_key=record['stable_key'],
            object_text=record['object_text'],
            payload_json=record['payload_json'],
            source_database_label=record['source_database_label'],
            asn=record['summary']['asn'],
            as_name=record['summary']['as_name'],
            import_policy_summary=record['summary']['import_policy_summary'],
            export_policy_summary=record['summary']['export_policy_summary'],
            maintainer_names_json=record['summary']['maintainer_names_json'],
            admin_contact_handles_json=record['summary']['admin_contact_handles_json'],
            tech_contact_handles_json=record['summary']['tech_contact_handles_json'],
        )
        persisted_counts['aut_num'] += 1

    persisted_counts['mntner'] = 0
    for record in batch['families']['mntner']:
        rpki_models.ImportedIrrMaintainer.objects.create(
            name=record['stable_key'],
            snapshot=snapshot,
            source=source,
            rpsl_object_class=record['rpsl_object_class'],
            rpsl_pk=record['rpsl_pk'],
            stable_key=record['stable_key'],
            object_text=record['object_text'],
            payload_json=record['payload_json'],
            source_database_label=record['source_database_label'],
            maintainer_name=record['summary']['maintainer_name'],
            auth_summary_json=record['summary']['auth_summary_json'],
            admin_contact_handles_json=record['summary']['admin_contact_handles_json'],
            upd_to_addresses_json=record['summary']['upd_to_addresses_json'],
        )
        persisted_counts['mntner'] += 1

    return persisted_counts


def _build_empty_batch(*, irr_source: rpki_models.IrrSource, fetch_mode: str, source_status: dict) -> dict:
    source_serial = source_status.get('serial_newest_journal') or source_status.get('serialNewestJournal')
    source_last_modified = source_status.get('rpsl_data_updated') or source_status.get('rpslDataUpdated')
    return {
        'source_metadata': {
            'source_family': irr_source.source_family,
            'default_database_label': irr_source.default_database_label,
            'write_support_mode': irr_source.write_support_mode,
        },
        'snapshot_metadata': {
            'fetch_mode': fetch_mode,
            'source_serial': source_serial,
            'source_last_modified': source_last_modified,
            'source_fingerprint': '',
            'warnings': [],
            'errors': [],
        },
        'families': {family: [] for family in IRR_FAMILY_ORDER},
        'capability': {
            'route': 'full',
            'route6': 'full',
            'route_set': 'full',
            'route_set_member': 'full',
            'as_set': 'full',
            'as_set_member': 'full',
            'aut_num': 'summary_only',
            'mntner': 'summary_only',
        },
    }


def _normalize_route_object(obj: dict) -> dict:
    object_class = obj['objectClass']
    prefix = obj.get('route') or obj.get('route6') or ''
    rpsl_pk = _build_route_rpsl_pk(prefix, obj.get('origin') or '')
    stable_key = f'{object_class}:{rpsl_pk}'
    address_family = rpki_models.AddressFamily.IPV6 if object_class == 'route6' else rpki_models.AddressFamily.IPV4
    return {
        'rpsl_object_class': object_class,
        'rpsl_pk': rpsl_pk,
        'stable_key': stable_key,
        'source_database_label': obj.get('source') or '',
        'object_text': obj.get('objectText') or '',
        'payload_json': obj,
        'summary': {
            'address_family': address_family,
            'prefix': prefix,
            'origin_asn': obj.get('origin') or '',
            'route_set_names_json': list(obj.get('memberOf') or []),
            'maintainer_names_json': list(obj.get('mntBy') or []),
        },
    }


def _normalize_route_set(obj: dict) -> dict:
    stable_key = f'route_set:{obj["rpslPk"]}'
    return {
        'rpsl_object_class': obj['objectClass'],
        'rpsl_pk': obj['rpslPk'],
        'stable_key': stable_key,
        'source_database_label': obj.get('source') or '',
        'object_text': obj.get('objectText') or '',
        'payload_json': obj,
        'summary': {
            'set_name': obj.get('routeSet') or obj['rpslPk'],
            'maintainer_names_json': list(obj.get('mntBy') or []),
            'member_count': 0,
        },
    }


def _normalize_as_set(obj: dict) -> dict:
    stable_key = f'as_set:{obj["rpslPk"]}'
    return {
        'rpsl_object_class': obj['objectClass'],
        'rpsl_pk': obj['rpslPk'],
        'stable_key': stable_key,
        'source_database_label': obj.get('source') or '',
        'object_text': obj.get('objectText') or '',
        'payload_json': obj,
        'summary': {
            'set_name': obj.get('asSet') or obj['rpslPk'],
            'maintainer_names_json': list(obj.get('mntBy') or []),
            'member_count': 0,
        },
    }


def _normalize_aut_num(obj: dict) -> dict:
    stable_key = f'aut_num:{obj["rpslPk"]}'
    return {
        'rpsl_object_class': obj['objectClass'],
        'rpsl_pk': obj['rpslPk'],
        'stable_key': stable_key,
        'source_database_label': obj.get('source') or '',
        'object_text': obj.get('objectText') or '',
        'payload_json': obj,
        'summary': {
            'asn': obj.get('autNum') or obj['rpslPk'],
            'as_name': obj.get('asName') or '',
            'import_policy_summary': ' | '.join(obj.get('import') or []),
            'export_policy_summary': ' | '.join(obj.get('export') or []),
            'maintainer_names_json': list(obj.get('mntBy') or []),
            'admin_contact_handles_json': list(obj.get('adminC') or []),
            'tech_contact_handles_json': list(obj.get('techC') or []),
        },
    }


def _normalize_maintainer(obj: dict) -> dict:
    stable_key = f'mntner:{obj["rpslPk"]}'
    auth_summary = []
    for entry in obj.get('auth') or []:
        if entry.startswith('BCRYPT-PW'):
            auth_summary.append('BCRYPT-PW filtered')
        else:
            auth_summary.append(entry)
    return {
        'rpsl_object_class': obj['objectClass'],
        'rpsl_pk': obj['rpslPk'],
        'stable_key': stable_key,
        'source_database_label': obj.get('source') or '',
        'object_text': obj.get('objectText') or '',
        'payload_json': obj,
        'summary': {
            'maintainer_name': obj.get('mntner') or obj['rpslPk'],
            'auth_summary_json': auth_summary,
            'admin_contact_handles_json': list(obj.get('adminC') or []),
            'upd_to_addresses_json': list(obj.get('updTo') or []),
        },
    }


def _normalize_member(member_text: str) -> dict:
    candidate = (member_text or '').strip()
    if not candidate:
        return {'member_type': rpki_models.IrrMemberType.UNKNOWN}
    try:
        ip_network(candidate, strict=False)
        return {
            'member_type': rpki_models.IrrMemberType.PREFIX,
            'normalized_prefix': candidate,
        }
    except ValueError:
        pass
    if candidate.upper().startswith('AS') and ':' not in candidate:
        return {
            'member_type': rpki_models.IrrMemberType.ASN,
            'normalized_asn': candidate.upper(),
        }
    if ':RS-' in candidate.upper() or candidate.upper().startswith('RS-'):
        return {
            'member_type': rpki_models.IrrMemberType.ROUTE_SET,
            'normalized_set_name': candidate,
        }
    if ':AS-' in candidate.upper() or candidate.upper().startswith('AS-'):
        return {
            'member_type': rpki_models.IrrMemberType.AS_SET,
            'normalized_set_name': candidate,
        }
    return {
        'member_type': rpki_models.IrrMemberType.SET_NAME,
        'normalized_set_name': candidate,
    }


def _select_irrd_source_status(status_payload: dict, default_database_label: str) -> dict:
    if default_database_label and default_database_label in status_payload:
        return status_payload[default_database_label]
    if len(status_payload) == 1:
        return next(iter(status_payload.values()))
    return {}


def _build_snapshot_summary(batch: dict) -> dict:
    metadata = batch['snapshot_metadata']
    summary = {
        'source_family': batch['source_metadata']['source_family'],
        'fetch_mode': metadata['fetch_mode'],
        'source_serial': metadata.get('source_serial'),
        'source_last_modified': metadata.get('source_last_modified'),
        'source_fingerprint': metadata.get('source_fingerprint'),
        'families': {},
        'degraded': bool(metadata.get('errors')),
        'errors': list(metadata.get('errors') or []),
    }
    for family in IRR_FAMILY_ORDER:
        count = len(batch['families'][family])
        summary['families'][family] = {
            'found': count,
            'imported': count,
            'failed': 0,
            'limited': batch['capability'].get(family) == 'summary_only',
        }
    return summary


def _build_failed_snapshot_summary(*, irr_source: rpki_models.IrrSource, fetch_mode: str, error_text: str) -> dict:
    summary = {
        'source_family': irr_source.source_family,
        'fetch_mode': fetch_mode,
        'source_serial': None,
        'source_last_modified': None,
        'source_fingerprint': None,
        'families': {},
        'degraded': True,
        'errors': [error_text],
    }
    for family in IRR_FAMILY_ORDER:
        summary['families'][family] = {'found': 0, 'imported': 0, 'failed': 0, 'limited': False}
    return summary


def _build_snapshot_name(irr_source: rpki_models.IrrSource, started_at) -> str:
    return f'{irr_source.name} Snapshot {started_at.strftime("%Y-%m-%d %H:%M:%S")}'


def _parse_timestamp(value: str | None):
    if not value:
        return None
    if value.endswith('Z'):
        value = value[:-1] + '+00:00'
    parsed = datetime.fromisoformat(value)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.utc)
    return parsed


def _join_url(base_url: str, path: str) -> str:
    return f'{base_url.rstrip("/")}/{path.lstrip("/")}'


def _http_text_request(url: str, *, username: str | None = None, password: str | None = None) -> str:
    request = Request(url, method='GET')
    _add_basic_auth(request, username=username, password=password)
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode('utf-8')
    except (HTTPError, URLError) as exc:
        raise IrrSyncError(f'HTTP request failed for {url}: {exc}') from exc


def _http_json_request(
    url: str,
    *,
    method: str = 'GET',
    payload: dict | None = None,
    username: str | None = None,
    password: str | None = None,
) -> dict:
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = Request(url, data=data, headers=headers, method=method)
    _add_basic_auth(request, username=username, password=password)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        raise IrrSyncError(f'JSON request failed for {url}: {exc}') from exc


def _add_basic_auth(request: Request, *, username: str | None = None, password: str | None = None) -> None:
    if not username:
        return
    token = base64.b64encode(f'{username}:{password or ""}'.encode('utf-8')).decode('ascii')
    request.add_header('Authorization', f'Basic {token}')


def _parse_rpsl_objects(text: str) -> list[ParsedRpslObject]:
    objects = []
    for block in [entry.strip() for entry in text.split('\n\n') if entry.strip()]:
        attributes: dict[str, list[str]] = {}
        current_key = None
        for line in block.splitlines():
            if not line.strip():
                continue
            if line.startswith((' ', '\t')) and current_key:
                attributes[current_key][-1] = f'{attributes[current_key][-1]} {line.strip()}'
                continue
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            normalized_key = key.strip().lower()
            attributes.setdefault(normalized_key, []).append(value.strip())
            current_key = normalized_key
        try:
            object_class, rpsl_pk = _identify_rpsl_primary_key(attributes)
        except IrrSyncError:
            continue
        objects.append(
            ParsedRpslObject(
                object_class=object_class,
                rpsl_pk=rpsl_pk,
                attributes=attributes,
                object_text=f'{block}\n',
            )
        )
    return objects


def _identify_rpsl_primary_key(attributes: dict[str, list[str]]) -> tuple[str, str]:
    for key in ('route', 'route6', 'route-set', 'as-set', 'aut-num', 'mntner'):
        if key not in attributes:
            continue
        primary_value = attributes[key][0]
        if key in {'route', 'route6'}:
            origin = (attributes.get('origin') or [''])[0]
            return key, _build_route_rpsl_pk(primary_value, origin)
        return key, primary_value
    raise IrrSyncError(f'Unsupported RPSL object class in snapshot import: {sorted(attributes)}')


def _build_route_rpsl_pk(prefix: str, origin: str) -> str:
    normalized_prefix = prefix.strip().lower()
    normalized_origin = origin.strip().upper().replace(' ', '')
    return f'{normalized_prefix}{normalized_origin}'


def _parsed_object_to_graphql_shape(parsed: ParsedRpslObject) -> dict:
    attrs = parsed.attributes
    object_class = parsed.object_class
    result = {
        'objectClass': object_class,
        'rpslPk': parsed.rpsl_pk,
        'source': (attrs.get('source') or [''])[0],
        'objectText': parsed.object_text,
        'updated': (attrs.get('last-modified') or [None])[0],
    }
    if object_class == 'route':
        result.update(
            {
                'route': (attrs.get('route') or [''])[0],
                'origin': (attrs.get('origin') or [''])[0],
                'memberOf': attrs.get('member-of') or [],
                'mntBy': attrs.get('mnt-by') or [],
            }
        )
    elif object_class == 'route6':
        result.update(
            {
                'route6': (attrs.get('route6') or [''])[0],
                'origin': (attrs.get('origin') or [''])[0],
                'memberOf': attrs.get('member-of') or [],
                'mntBy': attrs.get('mnt-by') or [],
            }
        )
    elif object_class == 'route-set':
        result.update(
            {
                'routeSet': (attrs.get('route-set') or [''])[0],
                'members': attrs.get('members') or [],
                'mpMembers': attrs.get('mp-members') or [],
                'mntBy': attrs.get('mnt-by') or [],
                'adminC': attrs.get('admin-c') or [],
                'techC': attrs.get('tech-c') or [],
            }
        )
    elif object_class == 'as-set':
        result.update(
            {
                'asSet': (attrs.get('as-set') or [''])[0],
                'members': attrs.get('members') or [],
                'mntBy': attrs.get('mnt-by') or [],
                'adminC': attrs.get('admin-c') or [],
                'techC': attrs.get('tech-c') or [],
            }
        )
    elif object_class == 'aut-num':
        result.update(
            {
                'autNum': (attrs.get('aut-num') or [''])[0],
                'asName': (attrs.get('as-name') or [''])[0],
                'import': attrs.get('import') or [],
                'export': attrs.get('export') or [],
                'mntBy': attrs.get('mnt-by') or [],
                'adminC': attrs.get('admin-c') or [],
                'techC': attrs.get('tech-c') or [],
            }
        )
    elif object_class == 'mntner':
        result.update(
            {
                'mntner': (attrs.get('mntner') or [''])[0],
                'auth': attrs.get('auth') or [],
                'adminC': attrs.get('admin-c') or [],
                'updTo': attrs.get('upd-to') or [],
                'mntBy': attrs.get('mnt-by') or [],
            }
        )
    return result
