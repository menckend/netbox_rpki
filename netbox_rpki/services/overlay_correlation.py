from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_sync_evidence import (
    get_certificate_observation_evidence_summary,
    get_signed_object_evidence_summary,
)


EVIDENCE_STALE_AFTER = timedelta(hours=24)


def build_signed_object_overlay_summary(obj: rpki_models.SignedObject) -> dict[str, object]:
    validation_results = list(
        obj.validation_results.select_related('validation_run').order_by('-validation_run__completed_at', '-observed_at', '-pk')[:5]
    )
    latest_validation = _latest_validation_summary(validation_results)

    imported_count = obj.imported_signed_object_observations.count()
    provider_linkage = {
        'imported_signed_object_count': imported_count,
        'latest_imported_signed_object_id': obj.imported_signed_object_observations.order_by('-pk').values_list('pk', flat=True).first(),
    }

    telemetry_summary = {}
    if obj.object_type == rpki_models.SignedObjectType.ROA:
        try:
            telemetry_summary = build_roa_overlay_summary(obj.roa_extension).get('telemetry', {})
        except rpki_models.RoaObject.DoesNotExist:
            telemetry_summary = {}
    elif obj.object_type == rpki_models.SignedObjectType.ASPA:
        try:
            telemetry_summary = build_aspa_overlay_summary(obj.aspa_extension).get('telemetry', {})
        except rpki_models.ASPA.DoesNotExist:
            telemetry_summary = {}

    return {
        'summary_schema_version': 1,
        'object_kind': 'signed_object',
        'object_type': obj.object_type,
        'latest_validator_posture': latest_validation,
        'latest_telemetry_posture': telemetry_summary or {'status': 'not_applicable'},
        'provider_evidence_linkage_status': 'linked' if imported_count else 'unmatched',
        'evidence_freshness': _merge_freshness(
            latest_validation.get('freshness_status') or '',
            telemetry_summary.get('freshness_status') or '',
        ),
        'evidence_confidence': 'high' if latest_validation.get('status') == 'observed' else 'low',
        'notable_mismatch_categories': _collect_mismatch_categories(
            latest_validation=latest_validation,
            telemetry_summary=telemetry_summary,
        ),
        'drill_down': {
            'validation_run_id': latest_validation.get('validation_run_id'),
            'telemetry_run_id': telemetry_summary.get('telemetry_run_id'),
        },
    }


def build_roa_overlay_summary(obj: rpki_models.RoaObject) -> dict[str, object]:
    payloads = list(
        obj.validated_payloads.select_related('validation_run', 'object_validation_result').order_by('-validation_run__completed_at', '-pk')[:10]
    )
    latest_validation = _latest_payload_validation_summary(payloads)
    telemetry_observations = _roa_telemetry_queryset(obj)
    latest_telemetry = _telemetry_summary(telemetry_observations)

    imported_support_count = obj.signed_object.imported_signed_object_observations.count() if obj.signed_object_id else 0
    return {
        'summary_schema_version': 1,
        'object_kind': 'roa',
        'latest_validator_posture': latest_validation,
        'telemetry': latest_telemetry,
        'provider_evidence_linkage_status': 'linked' if imported_support_count else 'unmatched',
        'evidence_freshness': _merge_freshness(
            latest_validation.get('freshness_status') or '',
            latest_telemetry.get('freshness_status') or '',
        ),
        'evidence_confidence': 'high' if latest_telemetry.get('matched_observation_count') else 'medium' if latest_validation.get('status') == 'observed' else 'low',
        'notable_mismatch_categories': _collect_mismatch_categories(
            latest_validation=latest_validation,
            telemetry_summary=latest_telemetry,
        ),
        'drill_down': {
            'validation_run_id': latest_validation.get('validation_run_id'),
            'telemetry_run_id': latest_telemetry.get('telemetry_run_id'),
        },
    }


def build_aspa_overlay_summary(obj: rpki_models.ASPA) -> dict[str, object]:
    payloads = list(
        obj.validated_payloads.select_related('validation_run', 'object_validation_result').order_by('-validation_run__completed_at', '-pk')[:20]
    )
    latest_validation = _latest_payload_validation_summary(payloads)
    telemetry_observations = _aspa_telemetry_queryset(obj)
    latest_telemetry = _telemetry_summary(telemetry_observations)
    supported_provider_asns = sorted(set(obj.provider_authorizations.filter(is_current=True).values_list('provider_as__asn', flat=True)))

    imported_support_count = obj.signed_object.imported_signed_object_observations.count() if obj.signed_object_id else 0
    latest_telemetry['supported_provider_asns'] = supported_provider_asns
    return {
        'summary_schema_version': 1,
        'object_kind': 'aspa',
        'latest_validator_posture': latest_validation,
        'telemetry': latest_telemetry,
        'provider_evidence_linkage_status': 'linked' if imported_support_count else 'unmatched',
        'evidence_freshness': _merge_freshness(
            latest_validation.get('freshness_status') or '',
            latest_telemetry.get('freshness_status') or '',
        ),
        'evidence_confidence': 'high' if latest_telemetry.get('matched_observation_count') else 'medium' if latest_validation.get('status') == 'observed' else 'low',
        'notable_mismatch_categories': _collect_mismatch_categories(
            latest_validation=latest_validation,
            telemetry_summary=latest_telemetry,
        ),
        'drill_down': {
            'validation_run_id': latest_validation.get('validation_run_id'),
            'telemetry_run_id': latest_telemetry.get('telemetry_run_id'),
        },
    }


def build_imported_signed_object_overlay_summary(obj: rpki_models.ImportedSignedObject) -> dict[str, object]:
    validation_results = list(
        obj.validation_results.select_related('validation_run').order_by('-validation_run__completed_at', '-observed_at', '-pk')[:5]
    )
    latest_validation = _latest_validation_summary(validation_results)
    authored_overlay = (
        build_signed_object_overlay_summary(obj.authored_signed_object)
        if obj.authored_signed_object_id is not None
        else {}
    )
    return {
        'summary_schema_version': 1,
        'object_kind': 'imported_signed_object',
        'latest_validator_posture': latest_validation,
        'latest_telemetry_posture': authored_overlay.get('latest_telemetry_posture') or {'status': 'unmatched'},
        'provider_evidence_linkage_status': get_signed_object_evidence_summary(obj).get('authored_linkage_status') or 'unmatched',
        'evidence_freshness': _merge_freshness(
            latest_validation.get('freshness_status') or '',
            (authored_overlay.get('latest_telemetry_posture') or {}).get('freshness_status') or '',
        ),
        'evidence_confidence': 'high' if latest_validation.get('status') == 'observed' else 'medium' if obj.authored_signed_object_id else 'low',
        'notable_mismatch_categories': _collect_mismatch_categories(
            latest_validation=latest_validation,
            telemetry_summary=authored_overlay.get('latest_telemetry_posture') or {},
        ),
        'drill_down': {
            'validation_run_id': latest_validation.get('validation_run_id'),
            'telemetry_run_id': (authored_overlay.get('latest_telemetry_posture') or {}).get('telemetry_run_id'),
            'authored_signed_object_id': obj.authored_signed_object_id,
        },
    }


def build_imported_certificate_observation_overlay_summary(obj: rpki_models.ImportedCertificateObservation) -> dict[str, object]:
    imported_overlay = (
        build_imported_signed_object_overlay_summary(obj.signed_object)
        if obj.signed_object_id is not None
        else {}
    )
    evidence_summary = get_certificate_observation_evidence_summary(obj)
    return {
        'summary_schema_version': 1,
        'object_kind': 'imported_certificate_observation',
        'latest_validator_posture': imported_overlay.get('latest_validator_posture') or {'status': 'unmatched'},
        'latest_telemetry_posture': imported_overlay.get('latest_telemetry_posture') or {'status': 'unmatched'},
        'provider_evidence_linkage_status': evidence_summary.get('publication_linkage_status') or 'unmatched',
        'evidence_freshness': imported_overlay.get('evidence_freshness') or 'unknown',
        'evidence_confidence': imported_overlay.get('evidence_confidence') or 'low',
        'notable_mismatch_categories': imported_overlay.get('notable_mismatch_categories') or [],
        'drill_down': imported_overlay.get('drill_down') or {},
    }


def _latest_validation_summary(results: list[rpki_models.ObjectValidationResult]) -> dict[str, object]:
    if not results:
        return {'status': 'unmatched', 'freshness_status': 'missing', 'result_count': 0}
    latest = results[0]
    latest_time = latest.observed_at or latest.validation_run.completed_at or latest.validation_run.started_at
    return {
        'status': 'observed',
        'validation_run_id': latest.validation_run_id,
        'validation_result_id': latest.pk,
        'validation_state': latest.validation_state,
        'disposition': latest.disposition,
        'match_status': latest.match_status or '',
        'observed_at': latest_time.isoformat() if latest_time else '',
        'result_count': len(results),
        'freshness_status': _freshness_status(latest_time),
    }


def _latest_payload_validation_summary(payloads) -> dict[str, object]:
    if not payloads:
        return {'status': 'unmatched', 'freshness_status': 'missing', 'payload_count': 0}
    latest = payloads[0]
    latest_time = latest.validation_run.completed_at or latest.validation_run.started_at
    validation_state = ''
    if latest.object_validation_result_id is not None:
        validation_state = latest.object_validation_result.validation_state
    return {
        'status': 'observed',
        'validation_run_id': latest.validation_run_id,
        'payload_id': latest.pk,
        'validation_state': validation_state,
        'payload_count': len(payloads),
        'observed_at': latest_time.isoformat() if latest_time else '',
        'freshness_status': _freshness_status(latest_time),
    }


def _telemetry_summary(queryset) -> dict[str, object]:
    observations = list(queryset.order_by('-last_observed_at', '-pk')[:20])
    if not observations:
        return {'status': 'unmatched', 'freshness_status': 'missing', 'matched_observation_count': 0}
    latest = observations[0]
    collector_counts = Counter(obs.collector_id or 'unknown' for obs in observations)
    return {
        'status': 'observed',
        'telemetry_run_id': latest.telemetry_run_id,
        'latest_observation_id': latest.pk,
        'matched_observation_count': len(observations),
        'latest_observed_at': latest.last_observed_at.isoformat() if latest.last_observed_at else '',
        'freshness_status': _freshness_status(latest.last_observed_at),
        'collector_counts': dict(collector_counts),
        'visibility_statuses': sorted({obs.visibility_status for obs in observations if obs.visibility_status}),
        'latest_path_hash': latest.path_hash,
    }


def _roa_telemetry_queryset(obj: rpki_models.RoaObject):
    if obj.origin_as_id is None:
        return rpki_models.BgpPathObservation.objects.none()
    prefixes = list(obj.prefix_authorizations.values_list('prefix__prefix', flat=True))
    if not prefixes:
        return rpki_models.BgpPathObservation.objects.none()
    return rpki_models.BgpPathObservation.objects.filter(
        observed_prefix__in=[str(prefix) for prefix in prefixes],
        observed_origin_asn=obj.origin_as.asn,
        telemetry_run__status=rpki_models.ValidationRunStatus.COMPLETED,
    ).select_related('telemetry_run')


def _aspa_telemetry_queryset(obj: rpki_models.ASPA):
    if obj.customer_as_id is None:
        return rpki_models.BgpPathObservation.objects.none()
    provider_asns = list(obj.provider_authorizations.filter(is_current=True).values_list('provider_as__asn', flat=True))
    if not provider_asns:
        return rpki_models.BgpPathObservation.objects.none()
    candidate_ids: list[int] = []
    for observation in rpki_models.BgpPathObservation.objects.filter(
        telemetry_run__status=rpki_models.ValidationRunStatus.COMPLETED,
    ).select_related('telemetry_run'):
        if _path_supports_aspa(observation.path_asns_json or [], customer_asn=obj.customer_as.asn, provider_asns=provider_asns):
            candidate_ids.append(observation.pk)
    return rpki_models.BgpPathObservation.objects.filter(pk__in=candidate_ids).select_related('telemetry_run')


def _path_supports_aspa(path_asns: list[int], *, customer_asn: int, provider_asns: list[int]) -> bool:
    if not path_asns:
        return False
    for index in range(len(path_asns) - 1):
        left = path_asns[index]
        right = path_asns[index + 1]
        if right == customer_asn and left in provider_asns:
            return True
    return False


def _freshness_status(reference_time) -> str:
    if reference_time is None:
        return 'missing'
    if reference_time + EVIDENCE_STALE_AFTER <= timezone.now():
        return 'stale'
    return 'current'


def _merge_freshness(validation_status: str, telemetry_status: str) -> str:
    statuses = {status for status in (validation_status, telemetry_status) if status}
    if not statuses:
        return 'unknown'
    if 'stale' in statuses:
        return 'stale'
    if statuses == {'missing'}:
        return 'missing'
    if 'current' in statuses:
        return 'current'
    return sorted(statuses)[0]


def _collect_mismatch_categories(*, latest_validation: dict[str, object], telemetry_summary: dict[str, object]) -> list[str]:
    categories: list[str] = []
    if latest_validation.get('status') == 'unmatched':
        categories.append('missing_validator_evidence')
    elif latest_validation.get('validation_state') == rpki_models.ValidationState.INVALID:
        categories.append('validator_invalid')
    if telemetry_summary.get('status') == 'unmatched':
        categories.append('missing_telemetry_evidence')
    if telemetry_summary.get('freshness_status') == 'stale':
        categories.append('stale_telemetry')
    return categories
