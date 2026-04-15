from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from ipam.models.asns import ASN
from ipam.models.ip import Prefix

from netbox_rpki import models as rpki_models


TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT = 'snapshot_import'


class BgpTelemetryError(Exception):
    pass


def sync_telemetry_source(
    source: rpki_models.TelemetrySource,
    *,
    snapshot_file: str,
) -> rpki_models.TelemetryRun:
    started_at = timezone.now()
    run = rpki_models.TelemetryRun.objects.create(
        name=_build_telemetry_run_name(source, started_at),
        source=source,
        status=rpki_models.ValidationRunStatus.RUNNING,
        started_at=started_at,
        summary_json={
            'source_name': source.name,
            'source_type': source.source_type,
            'fetch_mode': TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT,
            'status': rpki_models.ValidationRunStatus.RUNNING,
        },
    )
    rpki_models.TelemetrySource.objects.filter(pk=source.pk).update(
        last_attempted_at=started_at,
        last_run_status=rpki_models.ValidationRunStatus.RUNNING,
    )

    try:
        batch = build_telemetry_import_batch(source, snapshot_file=snapshot_file)
        run = persist_telemetry_run(run, batch)
    except Exception as exc:
        completed_at = timezone.now()
        summary_json = {
            'source_name': source.name,
            'source_type': source.source_type,
            'fetch_mode': TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT,
            'status': rpki_models.ValidationRunStatus.FAILED,
            'error_text': str(exc),
        }
        run.status = rpki_models.ValidationRunStatus.FAILED
        run.completed_at = completed_at
        run.error_text = str(exc)
        run.summary_json = summary_json
        run.save(update_fields=('status', 'completed_at', 'error_text', 'summary_json'))
        source.last_attempted_at = started_at
        source.last_run_status = rpki_models.ValidationRunStatus.FAILED
        source.last_run_summary_json = summary_json
        source.save(update_fields=('last_attempted_at', 'last_run_status', 'last_run_summary_json'))
        raise

    return run


def build_telemetry_import_batch(
    source: rpki_models.TelemetrySource,
    *,
    snapshot_file: str,
) -> dict:
    payload = json.loads(Path(snapshot_file).read_text())
    metadata = dict(payload.get('metadata') or {})
    observations = []
    for index, record in enumerate(payload.get('observations') or [], start=1):
        observations.append(_normalize_observation(source, record, index=index))
    metadata.setdefault('fetch_mode', TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT)
    metadata.setdefault('observation_count', len(observations))
    return {
        'metadata': metadata,
        'observations': observations,
    }


def persist_telemetry_run(run: rpki_models.TelemetryRun, batch: dict) -> rpki_models.TelemetryRun:
    metadata = dict(batch.get('metadata') or {})
    completed_at = timezone.now()
    summary_json = _build_run_summary(run, batch, completed_at=completed_at)
    observed_window_start = _parse_timestamp(metadata.get('observed_window_start'))
    observed_window_end = _parse_timestamp(metadata.get('observed_window_end'))

    with transaction.atomic():
        run.status = rpki_models.ValidationRunStatus.COMPLETED
        run.completed_at = completed_at
        run.observed_window_start = observed_window_start
        run.observed_window_end = observed_window_end
        run.source_fingerprint = metadata.get('source_fingerprint') or ''
        run.summary_json = summary_json
        run.save(
            update_fields=(
                'status',
                'completed_at',
                'observed_window_start',
                'observed_window_end',
                'source_fingerprint',
                'summary_json',
            )
        )

        persisted_count = 0
        for item in batch.get('observations') or []:
            rpki_models.BgpPathObservation.objects.create(
                name=_build_observation_name(run, item['stable_key']),
                telemetry_run=run,
                source=run.source,
                prefix=item.get('prefix'),
                observed_prefix=item.get('observed_prefix') or '',
                origin_as=item.get('origin_as'),
                observed_origin_asn=item.get('observed_origin_asn'),
                peer_as=item.get('peer_as'),
                observed_peer_asn=item.get('observed_peer_asn'),
                collector_id=item.get('collector_id') or '',
                vantage_point_label=item.get('vantage_point_label') or '',
                raw_as_path=item.get('raw_as_path') or '',
                path_hash=item.get('path_hash') or '',
                path_asns_json=item.get('path_asns_json') or [],
                first_observed_at=_parse_timestamp(item.get('first_observed_at')),
                last_observed_at=_parse_timestamp(item.get('last_observed_at')),
                visibility_status=item.get('visibility_status') or '',
                details_json=item.get('details_json') or {},
            )
            persisted_count += 1

        summary_json['persisted_counts'] = {'path_observations': persisted_count}
        run.summary_json = summary_json
        run.save(update_fields=('summary_json',))

        source = run.source
        source.last_attempted_at = run.started_at
        source.last_run_status = run.status
        source.summary_json = {
            'source_type': source.source_type,
            'endpoint_label': source.endpoint_label,
            'collector_scope': source.collector_scope,
        }
        source.last_run_summary_json = summary_json
        source.last_successful_run = run
        source.save(
            update_fields=(
                'last_attempted_at',
                'last_run_status',
                'summary_json',
                'last_run_summary_json',
                'last_successful_run',
            )
        )

    return run


def _normalize_observation(source: rpki_models.TelemetrySource, record: dict, *, index: int) -> dict:
    observed_prefix = str(record.get('prefix') or '').strip()
    observed_origin_asn = _parse_asn(record.get('origin_asn'))
    observed_peer_asn = _parse_asn(record.get('peer_asn'))
    raw_as_path = ' '.join(str(token) for token in (record.get('as_path') or [])).strip()
    if not raw_as_path:
        raw_as_path = str(record.get('as_path_text') or '').strip()
    path_asns_json = _normalize_as_path_sequence(record, raw_as_path=raw_as_path)
    path_hash = str(record.get('path_hash') or '').strip() or _build_path_hash(raw_as_path=raw_as_path, path_asns_json=path_asns_json)
    collector_id = str(record.get('collector_id') or record.get('collector') or '').strip()
    vantage_point_label = str(record.get('vantage_point_label') or record.get('vantage_point') or '').strip()
    stable_key = f'{observed_prefix}|{observed_origin_asn or 0}|{path_hash[:16]}|{index}'
    return {
        'stable_key': stable_key,
        'prefix': Prefix.objects.filter(prefix=observed_prefix).first() if observed_prefix else None,
        'observed_prefix': observed_prefix,
        'origin_as': ASN.objects.filter(asn=observed_origin_asn).first() if observed_origin_asn else None,
        'observed_origin_asn': observed_origin_asn,
        'peer_as': ASN.objects.filter(asn=observed_peer_asn).first() if observed_peer_asn else None,
        'observed_peer_asn': observed_peer_asn,
        'collector_id': collector_id,
        'vantage_point_label': vantage_point_label,
        'raw_as_path': raw_as_path,
        'path_hash': path_hash,
        'path_asns_json': path_asns_json,
        'first_observed_at': record.get('first_observed_at'),
        'last_observed_at': record.get('last_observed_at'),
        'visibility_status': str(record.get('visibility_status') or '').strip(),
        'details_json': {
            'source_kind': source.source_type,
            'collector_peer_count': record.get('collector_peer_count'),
            'rib_source': record.get('rib_source'),
            'source_record': {
                key: record[key]
                for key in (
                    'prefix',
                    'origin_asn',
                    'peer_asn',
                    'collector_id',
                    'vantage_point_label',
                    'visibility_status',
                    'first_observed_at',
                    'last_observed_at',
                )
                if key in record
            },
        },
    }


def _normalize_as_path_sequence(record: dict, *, raw_as_path: str) -> list[int]:
    tokens = record.get('as_path')
    if isinstance(tokens, list):
        parsed = [_parse_asn(token) for token in tokens]
        return [asn for asn in parsed if asn is not None]
    if not raw_as_path:
        return []
    parsed = [_parse_asn(token) for token in raw_as_path.split()]
    return [asn for asn in parsed if asn is not None]


def _build_path_hash(*, raw_as_path: str, path_asns_json: list[int]) -> str:
    normalized = raw_as_path.strip() or ' '.join(str(asn) for asn in path_asns_json)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _build_run_summary(run: rpki_models.TelemetryRun, batch: dict, *, completed_at) -> dict:
    observations = batch.get('observations') or []
    metadata = dict(batch.get('metadata') or {})
    collector_counts = Counter(item.get('collector_id') or 'unknown' for item in observations)
    peer_counts = Counter(str(item.get('observed_peer_asn') or 'unknown') for item in observations)
    unique_prefixes = {item.get('observed_prefix') for item in observations if item.get('observed_prefix')}
    unique_origins = {item.get('observed_origin_asn') for item in observations if item.get('observed_origin_asn') is not None}
    unique_paths = {item.get('path_hash') for item in observations if item.get('path_hash')}
    return {
        'status': rpki_models.ValidationRunStatus.COMPLETED,
        'source_id': run.source_id,
        'source_name': run.source.name,
        'source_type': run.source.source_type,
        'fetch_mode': metadata.get('fetch_mode') or TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT,
        'source_fingerprint': metadata.get('source_fingerprint') or '',
        'observed_window': {
            'start': metadata.get('observed_window_start') or '',
            'end': metadata.get('observed_window_end') or '',
        },
        'completed_at': completed_at.isoformat(),
        'observation_count': len(observations),
        'collector_counts': dict(collector_counts),
        'peer_counts': dict(peer_counts),
        'unique_prefix_count': len(unique_prefixes),
        'unique_origin_asn_count': len(unique_origins),
        'unique_path_count': len(unique_paths),
        'matched_roa_support_count': 0,
        'matched_aspa_support_count': 0,
        'unmatched_observation_count': len(observations),
        'stale_or_partial_import': False,
        'source_metadata': metadata,
    }


def _build_telemetry_run_name(source: rpki_models.TelemetrySource, started_at) -> str:
    stamp = started_at.strftime('%Y%m%d-%H%M%S')
    return f'{source.name} Import {stamp}'


def _build_observation_name(run: rpki_models.TelemetryRun, stable_key: str) -> str:
    token = slugify(stable_key)[:48] or stable_key[:48]
    return f'{run.name} {token}'


def _parse_asn(value) -> int | None:
    if value in {None, ''}:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().upper()
    if text.startswith('AS'):
        text = text[2:]
    if not text.isdigit():
        return None
    return int(text)


def _parse_timestamp(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith('Z'):
        text = f'{text[:-1]}+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed
