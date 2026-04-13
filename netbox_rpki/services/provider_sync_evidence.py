from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import base64
import binascii
import hashlib

from netbox_rpki import models as rpki_models


CERTIFICATE_OBSERVATION_SOURCE_LABELS = {
    choice.value: choice.label
    for choice in rpki_models.CertificateObservationSource
}
SIGNED_OBJECT_TYPE_LABELS = {
    choice.value: choice.label
    for choice in rpki_models.SignedObjectType
}


def _mapping(value) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _sequence(value) -> list[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _normalized_text(value) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _dedupe_texts(values: Sequence[object]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _normalized_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def certificate_observation_source_label(value: str) -> str:
    return CERTIFICATE_OBSERVATION_SOURCE_LABELS.get(value, value)


def signed_object_type_label(value: str) -> str:
    return SIGNED_OBJECT_TYPE_LABELS.get(value, value)


def _source_identity(source: Mapping[str, object]) -> str:
    for key in ('signed_object_uri', 'certificate_uri', 'publication_uri', 'related_handle', 'class_name'):
        text = _normalized_text(source.get(key))
        if text:
            return text
    return _normalized_text(source.get('observation_source'))


def _infer_signed_object_type(uri: str) -> str:
    normalized_uri = uri.lower()
    if normalized_uri.endswith('.roa'):
        return rpki_models.SignedObjectType.ROA
    if normalized_uri.endswith('.mft'):
        return rpki_models.SignedObjectType.MANIFEST
    if normalized_uri.endswith('.crl'):
        return rpki_models.SignedObjectType.CRL
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


def _fallback_certificate_sources(obj: rpki_models.ImportedCertificateObservation) -> list[dict[str, object]]:
    source = {
        'observation_source': obj.observation_source,
        'observation_source_label': certificate_observation_source_label(obj.observation_source),
        'certificate_uri': obj.certificate_uri,
        'publication_uri': obj.publication_uri,
        'signed_object_uri': obj.signed_object_uri,
        'related_handle': obj.related_handle,
        'class_name': obj.class_name,
        'freshness_status': 'stale' if obj.is_stale else '',
    }
    source['source_identity'] = _source_identity(source)
    return [source]


def build_publication_point_payload(
    provider_account: rpki_models.RpkiProviderAccount,
    record,
    *,
    authored_publication_point: rpki_models.PublicationPoint | None,
) -> dict[str, object]:
    published_objects = []
    for object_record in tuple(getattr(record, 'published_objects', ()) or ()):
        uri = _normalized_text(getattr(object_record, 'uri', ''))
        body_base64 = _normalized_text(getattr(object_record, 'body_base64', ''))
        signed_object_type = _normalized_text(getattr(object_record, 'signed_object_type', '')) or _infer_signed_object_type(uri)
        published_objects.append(
            {
                'uri': uri,
                'body_base64': body_base64,
                'signed_object_type': signed_object_type,
                'signed_object_type_label': signed_object_type_label(signed_object_type),
                'object_hash': _normalized_text(getattr(object_record, 'object_hash', '')) or _published_object_hash(body_base64),
            }
        )

    published_object_type_counts = dict(
        Counter(
            entry['signed_object_type']
            for entry in published_objects
            if _normalized_text(entry.get('signed_object_type'))
        )
    )
    authored_linkage_status = 'linked' if authored_publication_point is not None else 'unmatched'
    evidence_summary = {
        'published_object_count': len(published_objects),
        'published_object_type_counts': published_object_type_counts,
        'published_object_uris': [entry['uri'] for entry in published_objects if entry['uri']],
        'authored_linkage_status': authored_linkage_status,
    }

    return {
        'provider_type': provider_account.provider_type,
        'ca_handle': provider_account.ca_handle,
        'source_identity': {
            'service_uri': _normalized_text(getattr(record, 'service_uri', '')),
            'publication_uri': _normalized_text(getattr(record, 'publication_uri', '')),
            'rrdp_notification_uri': _normalized_text(getattr(record, 'rrdp_notification_uri', '')),
            'external_object_id': _normalized_text(getattr(record, 'external_object_id', '')),
        },
        'authored_linkage': {
            'status': authored_linkage_status,
            'authored_publication_point_id': getattr(authored_publication_point, 'pk', None),
            'authored_publication_point_name': getattr(authored_publication_point, 'name', ''),
        },
        'published_objects': published_objects,
        'published_object_type_counts': published_object_type_counts,
        'evidence_summary': evidence_summary,
    }


def build_signed_object_payload(
    provider_account: rpki_models.RpkiProviderAccount,
    record,
    *,
    publication_point: rpki_models.ImportedPublicationPoint | None,
    publication_linkage_status: str,
    publication_linkage_reason: str,
    authored_signed_object: rpki_models.SignedObject | None,
    manifest_metadata: Mapping[str, object] | None,
    crl_metadata: Mapping[str, object] | None,
) -> dict[str, object]:
    signed_object_type = _normalized_text(getattr(record, 'signed_object_type', ''))
    authored_linkage_status = 'linked' if authored_signed_object is not None else 'unmatched'
    manifest_summary = _mapping(manifest_metadata)
    crl_summary = _mapping(crl_metadata)

    return {
        'provider_type': provider_account.provider_type,
        'ca_handle': provider_account.ca_handle,
        'publication_uri': _normalized_text(getattr(record, 'publication_uri', '')),
        'signed_object_uri': _normalized_text(getattr(record, 'signed_object_uri', '')),
        'signed_object_type': signed_object_type,
        'signed_object_type_label': signed_object_type_label(signed_object_type),
        'object_hash': _normalized_text(getattr(record, 'object_hash', '')),
        'body_base64': _normalized_text(getattr(record, 'body_base64', '')),
        'source_identity': {
            'signed_object_uri': _normalized_text(getattr(record, 'signed_object_uri', '')),
            'publication_uri': _normalized_text(getattr(record, 'publication_uri', '')),
            'object_hash': _normalized_text(getattr(record, 'object_hash', '')),
        },
        'publication_linkage': {
            'status': publication_linkage_status,
            'reason': publication_linkage_reason,
            'publication_point_key': getattr(publication_point, 'publication_key', ''),
        },
        'authored_linkage': {
            'status': authored_linkage_status,
            'authored_signed_object_id': getattr(authored_signed_object, 'pk', None),
            'authored_signed_object_name': getattr(authored_signed_object, 'name', ''),
        },
        'manifest': manifest_summary,
        'crl': crl_summary,
        'evidence_summary': {
            'signed_object_type': signed_object_type,
            'signed_object_type_label': signed_object_type_label(signed_object_type),
            'publication_linkage_status': publication_linkage_status,
            'authored_linkage_status': authored_linkage_status,
            'manifest_entry_count': len(_sequence(manifest_summary.get('file_entries'))),
            'crl_freshness_status': _normalized_text(crl_summary.get('freshness_status')),
        },
    }


def build_certificate_observation_payload(
    observation_record,
    *,
    publication_point: rpki_models.ImportedPublicationPoint | None,
    publication_linkage_status: str,
    publication_linkage_reason: str,
    signed_object: rpki_models.ImportedSignedObject | None,
    signed_object_linkage_status: str,
    signed_object_linkage_reason: str,
) -> dict[str, object]:
    sources = []
    for source_record in tuple(getattr(observation_record, 'source_records', ()) or ()):
        source = {
            'observation_source': _normalized_text(getattr(source_record, 'observation_source', '')),
            'observation_source_label': certificate_observation_source_label(
                _normalized_text(getattr(source_record, 'observation_source', ''))
            ),
            'certificate_uri': _normalized_text(getattr(source_record, 'certificate_uri', '')),
            'publication_uri': _normalized_text(getattr(source_record, 'publication_uri', '')),
            'signed_object_uri': _normalized_text(getattr(source_record, 'signed_object_uri', '')),
            'related_handle': _normalized_text(getattr(source_record, 'related_handle', '')),
            'class_name': _normalized_text(getattr(source_record, 'class_name', '')),
            'freshness_status': _normalized_text(getattr(source_record, 'freshness_status', '')),
        }
        source['source_identity'] = _source_identity(source)
        sources.append(source)

    unique_publication_uris = _dedupe_texts([source.get('publication_uri') for source in sources])
    unique_signed_object_uris = _dedupe_texts([source.get('signed_object_uri') for source in sources])
    unique_related_handles = _dedupe_texts([source.get('related_handle') for source in sources])
    unique_class_names = _dedupe_texts([source.get('class_name') for source in sources])
    source_labels = _dedupe_texts([source.get('observation_source_label') for source in sources])
    source_identities = _dedupe_texts([source.get('source_identity') for source in sources])
    ambiguity_reasons = []
    if len(unique_publication_uris) > 1:
        ambiguity_reasons.append('multiple_publication_uris')
    if len(unique_signed_object_uris) > 1:
        ambiguity_reasons.append('multiple_signed_object_uris')
    if len(unique_related_handles) > 1:
        ambiguity_reasons.append('multiple_related_handles')
    if len(unique_class_names) > 1:
        ambiguity_reasons.append('multiple_class_names')

    source_summary = {
        'source_count': len(sources),
        'source_labels': source_labels,
        'source_identities': source_identities,
        'has_multiple_sources': len(sources) > 1,
        'is_ambiguous': bool(ambiguity_reasons),
        'ambiguity_reasons': ambiguity_reasons,
        'primary_source': sources[0]['observation_source'] if sources else '',
        'primary_source_label': sources[0]['observation_source_label'] if sources else '',
    }

    return {
        'certificate_uri': _normalized_text(getattr(observation_record, 'certificate_uri', '')),
        'publication_uri': _normalized_text(getattr(observation_record, 'publication_uri', '')),
        'signed_object_uri': _normalized_text(getattr(observation_record, 'signed_object_uri', '')),
        'related_handle': _normalized_text(getattr(observation_record, 'related_handle', '')),
        'class_name': _normalized_text(getattr(observation_record, 'class_name', '')),
        'subject': _normalized_text(getattr(observation_record, 'subject', '')),
        'issuer': _normalized_text(getattr(observation_record, 'issuer', '')),
        'serial_number': _normalized_text(getattr(observation_record, 'serial_number', '')),
        'not_before': getattr(getattr(observation_record, 'not_before', None), 'isoformat', lambda: '')(),
        'not_after': getattr(getattr(observation_record, 'not_after', None), 'isoformat', lambda: '')(),
        'sources': sources,
        'source_summary': source_summary,
        'publication_linkage': {
            'status': publication_linkage_status,
            'reason': publication_linkage_reason,
            'publication_point_key': getattr(publication_point, 'publication_key', ''),
        },
        'signed_object_linkage': {
            'status': signed_object_linkage_status,
            'reason': signed_object_linkage_reason,
            'signed_object_key': getattr(signed_object, 'signed_object_key', ''),
        },
        'evidence_summary': {
            'source_count': source_summary['source_count'],
            'source_labels': source_labels,
            'has_multiple_sources': source_summary['has_multiple_sources'],
            'is_ambiguous': source_summary['is_ambiguous'],
            'publication_linkage_status': publication_linkage_status,
            'signed_object_linkage_status': signed_object_linkage_status,
        },
        'certificate_pem': _normalized_text(getattr(observation_record, 'certificate_pem', '')),
        'certificate_der_base64': _normalized_text(getattr(observation_record, 'certificate_der_base64', '')),
    }


def get_publication_point_evidence_summary(obj: rpki_models.ImportedPublicationPoint) -> dict[str, object]:
    payload = _mapping(obj.payload_json)
    summary = _mapping(payload.get('evidence_summary'))
    if summary:
        return summary
    published_objects = _sequence(payload.get('published_objects'))
    return {
        'published_object_count': len(published_objects),
        'published_object_type_counts': _mapping(payload.get('published_object_type_counts')),
        'published_object_uris': [
            _normalized_text(_mapping(entry).get('uri'))
            for entry in published_objects
            if _normalized_text(_mapping(entry).get('uri'))
        ],
        'authored_linkage_status': get_publication_point_authored_linkage_status(obj),
    }


def get_publication_point_authored_linkage_status(obj: rpki_models.ImportedPublicationPoint) -> str:
    payload = _mapping(obj.payload_json)
    linkage = _mapping(payload.get('authored_linkage'))
    return _normalized_text(linkage.get('status')) or ('linked' if obj.authored_publication_point_id else 'unmatched')


def get_signed_object_evidence_summary(obj: rpki_models.ImportedSignedObject) -> dict[str, object]:
    payload = _mapping(obj.payload_json)
    summary = _mapping(payload.get('evidence_summary'))
    if summary:
        return summary
    return {
        'signed_object_type': obj.signed_object_type,
        'signed_object_type_label': signed_object_type_label(obj.signed_object_type),
        'publication_linkage_status': get_signed_object_publication_linkage_status(obj),
        'authored_linkage_status': get_signed_object_authored_linkage_status(obj),
        'manifest_entry_count': len(_sequence(_mapping(payload.get('manifest')).get('file_entries'))),
        'crl_freshness_status': _normalized_text(_mapping(payload.get('crl')).get('freshness_status')),
    }


def get_signed_object_publication_linkage_status(obj: rpki_models.ImportedSignedObject) -> str:
    payload = _mapping(obj.payload_json)
    linkage = _mapping(payload.get('publication_linkage'))
    return _normalized_text(linkage.get('status')) or ('linked' if obj.publication_point_id else 'unmatched')


def get_signed_object_authored_linkage_status(obj: rpki_models.ImportedSignedObject) -> str:
    payload = _mapping(obj.payload_json)
    linkage = _mapping(payload.get('authored_linkage'))
    return _normalized_text(linkage.get('status')) or ('linked' if obj.authored_signed_object_id else 'unmatched')


def get_certificate_observation_source_count(obj: rpki_models.ImportedCertificateObservation) -> int:
    payload = _mapping(obj.payload_json)
    summary = _mapping(payload.get('source_summary'))
    if 'source_count' in summary:
        return int(summary.get('source_count') or 0)
    if payload.get('sources'):
        return len(_sequence(payload.get('sources')))
    return len(_fallback_certificate_sources(obj))


def get_certificate_observation_source_labels(obj: rpki_models.ImportedCertificateObservation) -> list[str]:
    payload = _mapping(obj.payload_json)
    summary = _mapping(payload.get('source_summary'))
    labels = _dedupe_texts(_sequence(summary.get('source_labels')))
    if labels:
        return labels
    sources = [
        _mapping(entry)
        for entry in _sequence(payload.get('sources'))
    ] or _fallback_certificate_sources(obj)
    return _dedupe_texts([entry.get('observation_source_label') for entry in sources])


def get_certificate_observation_is_ambiguous(obj: rpki_models.ImportedCertificateObservation) -> bool:
    payload = _mapping(obj.payload_json)
    summary = _mapping(payload.get('source_summary'))
    if 'is_ambiguous' in summary:
        return bool(summary.get('is_ambiguous'))
    return False


def get_certificate_observation_publication_linkage_status(obj: rpki_models.ImportedCertificateObservation) -> str:
    payload = _mapping(obj.payload_json)
    linkage = _mapping(payload.get('publication_linkage'))
    if linkage.get('status'):
        return _normalized_text(linkage.get('status'))
    return 'linked' if obj.publication_point_id else 'unmatched'


def get_certificate_observation_signed_object_linkage_status(obj: rpki_models.ImportedCertificateObservation) -> str:
    payload = _mapping(obj.payload_json)
    linkage = _mapping(payload.get('signed_object_linkage'))
    if linkage.get('status'):
        return _normalized_text(linkage.get('status'))
    return 'linked' if obj.signed_object_id else 'unmatched'


def get_certificate_observation_evidence_summary(obj: rpki_models.ImportedCertificateObservation) -> dict[str, object]:
    payload = _mapping(obj.payload_json)
    summary = _mapping(payload.get('evidence_summary'))
    if summary:
        return summary
    return {
        'source_count': get_certificate_observation_source_count(obj),
        'source_labels': get_certificate_observation_source_labels(obj),
        'has_multiple_sources': get_certificate_observation_source_count(obj) > 1,
        'is_ambiguous': get_certificate_observation_is_ambiguous(obj),
        'publication_linkage_status': get_certificate_observation_publication_linkage_status(obj),
        'signed_object_linkage_status': get_certificate_observation_signed_object_linkage_status(obj),
    }