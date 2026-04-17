from __future__ import annotations

import base64
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from ipam.models.asns import ASN
from ipam.models.ip import Prefix

from netbox_rpki import models as rpki_models
from netbox_rpki.structured_logging import emit_structured_log


VALIDATOR_FETCH_MODE_LIVE_API = 'live_api'
VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT = 'snapshot_import'
VALIDATOR_FETCH_MODES = (
    VALIDATOR_FETCH_MODE_LIVE_API,
    VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT,
)


class ExternalValidationError(Exception):
    pass


@dataclass(frozen=True)
class MatchResult:
    signed_object: rpki_models.SignedObject | None = None
    imported_signed_object: rpki_models.ImportedSignedObject | None = None
    match_status: str = 'unmatched'


def sync_validator_instance(
    validator: rpki_models.ValidatorInstance,
    *,
    fetch_mode: str = VALIDATOR_FETCH_MODE_LIVE_API,
    snapshot_file: str | None = None,
) -> rpki_models.ValidationRun:
    started_at = timezone.now()
    run = rpki_models.ValidationRun.objects.create(
        name=_build_validation_run_name(validator, started_at),
        validator=validator,
        status=rpki_models.ValidationRunStatus.RUNNING,
        started_at=started_at,
        summary_json={
            'validator_name': validator.name,
            'fetch_mode': fetch_mode,
            'status': rpki_models.ValidationRunStatus.RUNNING,
        },
    )
    rpki_models.ValidatorInstance.objects.filter(pk=validator.pk).update(
        status=rpki_models.ValidationRunStatus.RUNNING,
        last_run_at=started_at,
    )

    try:
        batch = build_validation_import_batch(
            validator,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        run = persist_validation_run(run, batch)
    except Exception as exc:
        completed_at = timezone.now()
        summary_json = {
            'validator_name': validator.name,
            'fetch_mode': fetch_mode,
            'status': rpki_models.ValidationRunStatus.FAILED,
            'error_text': str(exc),
        }
        run.status = rpki_models.ValidationRunStatus.FAILED
        run.completed_at = completed_at
        run.summary_json = summary_json
        run.save(update_fields=('status', 'completed_at', 'summary_json'))
        validator.status = rpki_models.ValidationRunStatus.FAILED
        validator.last_run_at = started_at
        validator.summary_json = summary_json
        validator.save(update_fields=('status', 'last_run_at', 'summary_json'))
        raise

    return run


def build_validation_import_batch(
    validator: rpki_models.ValidatorInstance,
    *,
    fetch_mode: str,
    snapshot_file: str | None = None,
) -> dict:
    if fetch_mode == VALIDATOR_FETCH_MODE_LIVE_API:
        return _fetch_routinator_live_batch(validator)
    if fetch_mode == VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT:
        if not snapshot_file:
            raise ExternalValidationError('snapshot_file is required when fetch_mode=snapshot_import.')
        payload = json.loads(Path(snapshot_file).read_text())
        return _normalize_routinator_jsonext_batch(validator, payload, fetch_mode=fetch_mode)
    raise ExternalValidationError(f'Unknown fetch mode: {fetch_mode}')


def persist_validation_run(run: rpki_models.ValidationRun, batch: dict) -> rpki_models.ValidationRun:
    metadata = dict(batch.get('metadata') or {})
    completed_at = timezone.now()
    summary_json = _build_run_summary(run, batch, completed_at=completed_at)

    with transaction.atomic():
        run.status = rpki_models.ValidationRunStatus.COMPLETED
        run.completed_at = completed_at
        run.repository_serial = str(metadata.get('repository_serial') or '')
        run.summary_json = summary_json
        run.save(update_fields=('status', 'completed_at', 'repository_serial', 'summary_json'))

        object_rows = _persist_object_results(run, batch)
        payload_counts = _persist_payload_rows(run, batch, object_rows)
        summary_json['persisted_counts'] = {
            'object_results': len(object_rows),
            **payload_counts,
        }
        run.summary_json = summary_json
        run.save(update_fields=('summary_json',))

        validator = run.validator
        validator.status = rpki_models.ValidationRunStatus.COMPLETED
        validator.last_run_at = run.completed_at
        validator.summary_json = {
            'latest_run_id': run.pk,
            'latest_run_status': run.status,
            'latest_completed_at': run.completed_at.isoformat() if run.completed_at else '',
            'latest_summary': summary_json,
        }
        validator.save(update_fields=('status', 'last_run_at', 'summary_json'))

    return run


def _persist_object_results(run: rpki_models.ValidationRun, batch: dict) -> dict[str, rpki_models.ObjectValidationResult]:
    object_rows: dict[str, rpki_models.ObjectValidationResult] = {}
    for item in batch.get('object_observations') or []:
        object_rows[item['object_key']] = rpki_models.ObjectValidationResult.objects.create(
            name=_build_object_result_name(run, item['object_key']),
            validation_run=run,
            signed_object=item.get('signed_object'),
            imported_signed_object=item.get('imported_signed_object'),
            validation_state=item.get('validation_state') or rpki_models.ValidationState.UNKNOWN,
            disposition=item.get('disposition') or rpki_models.ValidationDisposition.NOTED,
            observed_at=_parse_timestamp(item.get('observed_at')),
            match_status=item.get('match_status') or '',
            external_object_uri=item.get('external_object_uri') or '',
            external_content_hash=item.get('external_content_hash') or '',
            external_object_key=item['object_key'],
            reason=item.get('reason') or '',
            details_json=item.get('details_json') or {},
        )
    return object_rows


def _persist_payload_rows(
    run: rpki_models.ValidationRun,
    batch: dict,
    object_rows: dict[str, rpki_models.ObjectValidationResult],
) -> dict[str, int]:
    roa_count = 0
    for index, item in enumerate(batch.get('roa_payloads') or (), start=1):
        rpki_models.ValidatedRoaPayload.objects.create(
            name=_build_payload_name(run, 'roa', index),
            validation_run=run,
            roa_object=item.get('roa_object'),
            object_validation_result=object_rows.get(item['object_key']),
            prefix=item.get('prefix'),
            origin_as=item.get('origin_as'),
            max_length=item.get('max_length'),
            observed_prefix=item.get('observed_prefix') or '',
            details_json=item.get('details_json') or {},
        )
        roa_count += 1

    aspa_count = 0
    for index, item in enumerate(batch.get('aspa_payloads') or (), start=1):
        rpki_models.ValidatedAspaPayload.objects.create(
            name=_build_payload_name(run, 'aspa', index),
            validation_run=run,
            aspa=item.get('aspa'),
            object_validation_result=object_rows.get(item['object_key']),
            customer_as=item.get('customer_as'),
            provider_as=item.get('provider_as'),
            details_json=item.get('details_json') or {},
        )
        aspa_count += 1

    return {
        'validated_roa_payloads': roa_count,
        'validated_aspa_payloads': aspa_count,
    }


def _fetch_routinator_live_batch(validator: rpki_models.ValidatorInstance) -> dict:
    if not validator.base_url:
        raise ExternalValidationError('Validator base_url is required for live API imports.')
    payload = _http_json_request(_join_url(validator.base_url, 'jsonext'))
    return _normalize_routinator_jsonext_batch(
        validator,
        payload,
        fetch_mode=VALIDATOR_FETCH_MODE_LIVE_API,
    )


def _normalize_routinator_jsonext_batch(
    validator: rpki_models.ValidatorInstance,
    payload: dict,
    *,
    fetch_mode: str,
) -> dict:
    metadata = dict(payload.get('metadata') or {})
    observed_at = (
        metadata.get('generated')
        or metadata.get('generated_at')
        or metadata.get('generatedAt')
        or metadata.get('time')
        or timezone.now().isoformat()
    )
    roa_records = payload.get('roas') or payload.get('validated_roas') or payload.get('vrps') or []
    aspa_records = payload.get('aspas') or payload.get('validated_aspas') or []

    object_observations: dict[str, dict] = {}
    roa_payloads = []
    aspa_payloads = []

    for record in roa_records:
        normalized = _normalize_roa_record(validator, record, observed_at=observed_at)
        _merge_object_observation(object_observations, normalized['object_observation'])
        roa_payloads.append(normalized['payload'])

    for record in aspa_records:
        for normalized in _normalize_aspa_record(validator, record, observed_at=observed_at):
            _merge_object_observation(object_observations, normalized['object_observation'])
            aspa_payloads.append(normalized['payload'])

    metadata.setdefault('fetch_mode', fetch_mode)
    metadata.setdefault('object_result_count', len(object_observations))
    metadata.setdefault('validated_roa_payload_count', len(roa_payloads))
    metadata.setdefault('validated_aspa_payload_count', len(aspa_payloads))
    metadata.setdefault('validator_software', validator.software_name or 'Routinator')
    return {
        'metadata': metadata,
        'object_observations': list(object_observations.values()),
        'roa_payloads': roa_payloads,
        'aspa_payloads': aspa_payloads,
    }


def _normalize_roa_record(
    validator: rpki_models.ValidatorInstance,
    record: dict,
    *,
    observed_at: str,
) -> dict:
    observed_prefix = str(record.get('prefix') or record.get('vrp') or '').strip()
    origin_value = record.get('asn')
    if origin_value is None:
        origin_value = record.get('origin_as') or record.get('origin')
    max_length = _as_int(record.get('max_length'))
    if max_length is None:
        max_length = _as_int(record.get('maxLength'))
    uri = str(record.get('uri') or record.get('source_uri') or record.get('object_uri') or '').strip()
    content_hash = str(record.get('hash') or record.get('content_hash') or record.get('object_hash') or '').strip()
    object_key = _build_external_object_key('roa', uri=uri, content_hash=content_hash, fallback=f'{observed_prefix}:{origin_value}:{max_length}')
    match = _match_signed_objects(
        validator,
        uri=uri,
        content_hash=content_hash,
    )
    prefix = _resolve_prefix(observed_prefix)
    origin_as = _resolve_asn(origin_value)
    roa_object = _match_roa_object(prefix=prefix, origin_as=origin_as, max_length=max_length)
    if match.match_status == 'unmatched' and roa_object is not None:
        match = MatchResult(match_status='payload_level')
    details_json = {
        'source_record': _extract_source_record(record),
        'ta': record.get('ta') or record.get('tal'),
        'expires': record.get('expires'),
        'not_before': record.get('not_before') or record.get('notBefore'),
        'not_after': record.get('not_after') or record.get('notAfter'),
        'vrp_kind': 'roa',
    }
    return {
        'object_observation': {
            'object_key': object_key,
            'signed_object': match.signed_object,
            'imported_signed_object': match.imported_signed_object,
            'match_status': match.match_status,
            'validation_state': rpki_models.ValidationState.VALID,
            'disposition': rpki_models.ValidationDisposition.ACCEPTED,
            'observed_at': observed_at,
            'external_object_uri': uri,
            'external_content_hash': content_hash,
            'reason': f'Validated ROA payload for {observed_prefix} origin AS{origin_as.asn if origin_as else _parse_asn(origin_value) or ""}'.strip(),
            'details_json': details_json,
        },
        'payload': {
            'object_key': object_key,
            'roa_object': roa_object,
            'prefix': prefix,
            'origin_as': origin_as,
            'max_length': max_length,
            'observed_prefix': observed_prefix,
            'details_json': details_json,
        },
    }


def _normalize_aspa_record(
    validator: rpki_models.ValidatorInstance,
    record: dict,
    *,
    observed_at: str,
) -> list[dict]:
    customer_value = record.get('customer_asn')
    if customer_value is None:
        customer_value = record.get('customer')
    providers = record.get('providers') or record.get('provider_asns') or record.get('providerASNs') or []
    uri = str(record.get('uri') or record.get('source_uri') or record.get('object_uri') or '').strip()
    content_hash = str(record.get('hash') or record.get('content_hash') or record.get('object_hash') or '').strip()
    provider_tokens = ','.join(str(provider) for provider in providers)
    object_key = _build_external_object_key('aspa', uri=uri, content_hash=content_hash, fallback=f'{customer_value}:{provider_tokens}')
    match = _match_signed_objects(
        validator,
        uri=uri,
        content_hash=content_hash,
    )
    customer_as = _resolve_asn(customer_value)
    results = []
    for provider_value in providers:
        provider_as = _resolve_asn(provider_value)
        aspa = _match_aspa(customer_as=customer_as, provider_as=provider_as)
        provider_match = match
        if provider_match.match_status == 'unmatched' and aspa is not None:
            provider_match = MatchResult(match_status='payload_level')
        details_json = {
            'source_record': _extract_source_record(record),
            'ta': record.get('ta') or record.get('tal'),
            'expires': record.get('expires'),
            'provider_count': len(providers),
            'vrp_kind': 'aspa',
        }
        results.append(
            {
                'object_observation': {
                    'object_key': object_key,
                    'signed_object': provider_match.signed_object,
                    'imported_signed_object': provider_match.imported_signed_object,
                    'match_status': provider_match.match_status,
                    'validation_state': rpki_models.ValidationState.VALID,
                    'disposition': rpki_models.ValidationDisposition.ACCEPTED,
                    'observed_at': observed_at,
                    'external_object_uri': uri,
                    'external_content_hash': content_hash,
                    'reason': f'Validated ASPA payload for AS{customer_as.asn if customer_as else _parse_asn(customer_value) or ""}',
                    'details_json': details_json,
                },
                'payload': {
                    'object_key': object_key,
                    'aspa': aspa,
                    'customer_as': customer_as,
                    'provider_as': provider_as,
                    'details_json': details_json,
                },
            }
        )
    return results


def _merge_object_observation(observations: dict[str, dict], item: dict) -> None:
    existing = observations.get(item['object_key'])
    if existing is None:
        observations[item['object_key']] = item
        return

    details_json = dict(existing.get('details_json') or {})
    details_json['payload_count'] = int(details_json.get('payload_count') or 1) + 1
    existing['details_json'] = details_json
    if existing.get('signed_object') is None and item.get('signed_object') is not None:
        existing['signed_object'] = item['signed_object']
    if existing.get('imported_signed_object') is None and item.get('imported_signed_object') is not None:
        existing['imported_signed_object'] = item['imported_signed_object']
    if existing.get('match_status') in {'', 'unmatched'} and item.get('match_status'):
        existing['match_status'] = item['match_status']


def _match_signed_objects(
    validator: rpki_models.ValidatorInstance,
    *,
    uri: str,
    content_hash: str,
) -> MatchResult:
    signed_match = _find_signed_object_match(validator, uri=uri, content_hash=content_hash)
    if isinstance(signed_match, rpki_models.SignedObject):
        return MatchResult(signed_object=signed_match, match_status='authored_signed_object')
    if signed_match == 'ambiguous':
        return MatchResult(match_status='ambiguous')

    imported_match = _find_imported_signed_object_match(validator, uri=uri, content_hash=content_hash)
    if isinstance(imported_match, rpki_models.ImportedSignedObject):
        return MatchResult(imported_signed_object=imported_match, match_status='imported_signed_object')
    if imported_match == 'ambiguous':
        return MatchResult(match_status='ambiguous')

    if uri or content_hash:
        return MatchResult(match_status='unmatched')
    return MatchResult(match_status='synthetic')


def _find_signed_object_match(
    validator: rpki_models.ValidatorInstance,
    *,
    uri: str,
    content_hash: str,
) -> rpki_models.SignedObject | str | None:
    queryset = rpki_models.SignedObject.objects.all()
    if validator.organization_id is not None:
        queryset = queryset.filter(organization=validator.organization)

    clause = Q()
    if uri:
        clause |= Q(object_uri=uri)
    if content_hash:
        clause |= Q(content_hash=content_hash)
    if not clause:
        return None

    matches = list(queryset.filter(clause).distinct()[:2])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return 'ambiguous'
    return None


def _find_imported_signed_object_match(
    validator: rpki_models.ValidatorInstance,
    *,
    uri: str,
    content_hash: str,
) -> rpki_models.ImportedSignedObject | str | None:
    queryset = rpki_models.ImportedSignedObject.objects.filter(is_stale=False)
    if validator.organization_id is not None:
        queryset = queryset.filter(organization=validator.organization)

    clause = Q()
    if uri:
        clause |= Q(signed_object_uri=uri)
    if content_hash:
        clause |= Q(object_hash=content_hash)
    if not clause:
        return None

    matches = list(queryset.filter(clause).order_by('-pk').distinct()[:2])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return 'ambiguous'
    return None


def _match_roa_object(
    *,
    prefix: Prefix | None,
    origin_as: ASN | None,
    max_length: int | None,
) -> rpki_models.RoaObject | None:
    if prefix is None:
        return None
    queryset = rpki_models.RoaObject.objects.filter(
        origin_as=origin_as,
        prefix_authorizations__prefix=prefix,
    )
    if max_length is not None:
        queryset = queryset.filter(prefix_authorizations__max_length=max_length)
    matches = list(queryset.distinct()[:2])
    return matches[0] if len(matches) == 1 else None


def _match_aspa(
    *,
    customer_as: ASN | None,
    provider_as: ASN | None,
) -> rpki_models.ASPA | None:
    if customer_as is None or provider_as is None:
        return None
    matches = list(
        rpki_models.ASPA.objects.filter(
            customer_as=customer_as,
            provider_authorizations__provider_as=provider_as,
            provider_authorizations__is_current=True,
        ).distinct()[:2]
    )
    return matches[0] if len(matches) == 1 else None


def _resolve_prefix(prefix_text: str) -> Prefix | None:
    if not prefix_text:
        return None
    return Prefix.objects.filter(prefix=prefix_text).first()


def _resolve_asn(value) -> ASN | None:
    asn_value = _parse_asn(value)
    if asn_value is None:
        return None
    return ASN.objects.filter(asn=asn_value).first()


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


def _build_run_summary(run: rpki_models.ValidationRun, batch: dict, *, completed_at) -> dict:
    observations = batch.get('object_observations') or []
    payloads = (batch.get('roa_payloads') or []) + (batch.get('aspa_payloads') or [])
    state_counts = Counter(item.get('validation_state') or rpki_models.ValidationState.UNKNOWN for item in observations)
    disposition_counts = Counter(item.get('disposition') or rpki_models.ValidationDisposition.NOTED for item in observations)
    match_counts = Counter(item.get('match_status') or 'unmatched' for item in observations)
    metadata = dict(batch.get('metadata') or {})
    observed_window = {
        'start': metadata.get('generated') or metadata.get('generated_at') or metadata.get('generatedAt') or '',
        'end': metadata.get('generated') or metadata.get('generated_at') or metadata.get('generatedAt') or '',
    }
    return {
        'status': rpki_models.ValidationRunStatus.COMPLETED,
        'validator_id': run.validator_id,
        'validator_name': run.validator.name,
        'software_name': run.validator.software_name or 'Routinator',
        'fetch_mode': metadata.get('fetch_mode') or '',
        'repository_serial': str(metadata.get('repository_serial') or ''),
        'generated_at': observed_window['end'],
        'completed_at': completed_at.isoformat(),
        'object_result_count': len(observations),
        'validated_roa_payload_count': len(batch.get('roa_payloads') or []),
        'validated_aspa_payload_count': len(batch.get('aspa_payloads') or []),
        'validation_state_counts': dict(state_counts),
        'disposition_counts': dict(disposition_counts),
        'matched_authored_object_count': match_counts.get('authored_signed_object', 0),
        'matched_imported_object_count': match_counts.get('imported_signed_object', 0),
        'payload_level_match_count': match_counts.get('payload_level', 0),
        'ambiguous_match_count': match_counts.get('ambiguous', 0),
        'unmatched_object_count': match_counts.get('unmatched', 0) + match_counts.get('synthetic', 0),
        'observed_window': observed_window,
        'source_metadata': metadata,
        'source_identifiers': {
            'base_url': run.validator.base_url,
            'validator_software': run.validator.software_name or 'Routinator',
        },
        'payload_identity_count': len(payloads),
    }


def _build_validation_run_name(validator: rpki_models.ValidatorInstance, started_at) -> str:
    stamp = started_at.strftime('%Y%m%d-%H%M%S')
    return f'{validator.name} Import {stamp}'


def _build_object_result_name(run: rpki_models.ValidationRun, object_key: str) -> str:
    token = slugify(object_key)[:48] or base64.urlsafe_b64encode(object_key.encode('utf-8')).decode('ascii')[:24]
    return f'{run.name} {token}'


def _build_payload_name(run: rpki_models.ValidationRun, family: str, index: int) -> str:
    return f'{run.name} {family.upper()} {index}'


def _build_external_object_key(family: str, *, uri: str, content_hash: str, fallback: str) -> str:
    if uri:
        return f'{family}:{uri}'
    if content_hash:
        return f'{family}:hash:{content_hash}'
    return f'{family}:synthetic:{fallback}'


def _extract_source_record(record: dict) -> dict:
    keys = (
        'uri',
        'hash',
        'ta',
        'tal',
        'expires',
        'notBefore',
        'notAfter',
        'generated',
        'asn',
        'prefix',
        'maxLength',
        'customer',
        'providers',
    )
    return {key: record[key] for key in keys if key in record}


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


def _as_int(value) -> int | None:
    if value in {None, ''}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _join_url(base_url: str, path: str) -> str:
    return f'{base_url.rstrip("/")}/{path.lstrip("/")}'


def _http_json_request(url: str):
    request = Request(url, headers={'Accept': 'application/json'})
    emit_structured_log(
        'external_validation.http.request',
        subsystem='external_validation',
        debug=True,
        method='GET',
        url=url,
        headers=dict(request.header_items()),
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        emit_structured_log(
            'external_validation.http.error',
            subsystem='external_validation',
            level='warning',
            method='GET',
            url=url,
            error=str(exc),
            error_type=type(exc).__name__,
            http_status=exc.code,
        )
        raise ExternalValidationError(f'HTTP error {exc.code} while fetching validator data from {url}.') from exc
    except URLError as exc:
        emit_structured_log(
            'external_validation.http.error',
            subsystem='external_validation',
            level='warning',
            method='GET',
            url=url,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise ExternalValidationError(f'Could not connect to validator endpoint {url}.') from exc
    except json.JSONDecodeError as exc:
        emit_structured_log(
            'external_validation.http.error',
            subsystem='external_validation',
            level='warning',
            method='GET',
            url=url,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise ExternalValidationError(f'Validator endpoint {url} did not return valid JSON.') from exc
    emit_structured_log(
        'external_validation.http.response',
        subsystem='external_validation',
        debug=True,
        method='GET',
        url=url,
        response_body=payload,
    )
    return payload
