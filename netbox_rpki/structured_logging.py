from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings


LOGGER_NAME = 'netbox_rpki'
REDACTED_VALUE = '<redacted>'

_SECRET_FIELD_NAMES = {
    'api_key',
    'apikey',
    'authorization',
    'http_password',
    'override',
    'password',
    'secret',
    'signature',
    'token',
    'x_netbox_rpki_signature',
}
_SENSITIVE_PAYLOAD_FIELD_NAMES = {
    'body',
    'body_base64',
    'certificate_der_base64',
    'certificate_pem',
    'delta',
    'object_text',
    'objects',
    'payload',
    'payload_json',
    'request_body',
    'response_body',
    'rollback_delta_json',
}
_SENSITIVE_URL_QUERY_KEYS = {
    'api_key',
    'apikey',
    'override',
    'password',
    'secret',
    'signature',
    'token',
}

_BASIC_AUTH_PATTERN = re.compile(r'Basic\s+[A-Za-z0-9+/=]+')
_BEARER_TOKEN_PATTERN = re.compile(r'Bearer\s+\S+')


def _plugin_config() -> dict:
    config = getattr(settings, 'PLUGINS_CONFIG', {}).get('netbox_rpki', {})
    return config if isinstance(config, dict) else {}


def _structured_logging_config() -> dict:
    config = _plugin_config().get('structured_logging', {})
    return config if isinstance(config, dict) else {}


def subsystem_debug_enabled(subsystem: str) -> bool:
    debug_subsystems = _structured_logging_config().get('debug_subsystems', ())
    if isinstance(debug_subsystems, Mapping):
        return bool(
            debug_subsystems.get(subsystem)
            or debug_subsystems.get('*')
            or debug_subsystems.get('all')
        )
    if isinstance(debug_subsystems, str):
        enabled = {item.strip() for item in debug_subsystems.split(',') if item.strip()}
        return bool({subsystem, '*', 'all'} & enabled)
    if isinstance(debug_subsystems, Sequence) and not isinstance(debug_subsystems, (bytes, bytearray)):
        enabled = {str(item).strip() for item in debug_subsystems if str(item).strip()}
        return bool({subsystem, '*', 'all'} & enabled)
    return bool(debug_subsystems)


def sanitize_url(url: str) -> str:
    if not isinstance(url, str) or not url:
        return url
    parts = urlsplit(url)
    if not parts.query:
        return _redact_auth_tokens(url)
    sanitized_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if _normalized_field_name(key) in _SENSITIVE_URL_QUERY_KEYS:
            sanitized_pairs.append((key, REDACTED_VALUE))
        else:
            sanitized_pairs.append((key, value))
    sanitized = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(sanitized_pairs, doseq=True), parts.fragment)
    )
    return _redact_auth_tokens(sanitized)


def sanitize_log_data(value, *, field_name: str | None = None):
    normalized_field_name = _normalized_field_name(field_name)
    if normalized_field_name in _SECRET_FIELD_NAMES:
        return REDACTED_VALUE
    if normalized_field_name in _SENSITIVE_PAYLOAD_FIELD_NAMES:
        return _summarize_sensitive_value(value)
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_log_data(item, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_log_data(item) for item in value]
    if isinstance(value, str):
        if _looks_like_url(value):
            return sanitize_url(value)
        return _redact_auth_tokens(value)
    return value


def emit_structured_log(
    event: str,
    *,
    subsystem: str,
    level: str = 'info',
    logger=None,
    debug: bool = False,
    **fields,
) -> dict | None:
    if debug and not subsystem_debug_enabled(subsystem):
        return None
    payload = {
        'event': event,
        'subsystem': subsystem,
    }
    for key, value in fields.items():
        payload[key] = sanitize_log_data(value, field_name=key)
    message = json.dumps(payload, sort_keys=True, default=_json_default)
    target_logger = logger or logging.getLogger(LOGGER_NAME)
    getattr(target_logger, level)(message)
    return payload


def _normalized_field_name(field_name: str | None) -> str:
    if not field_name:
        return ''
    return str(field_name).strip().lower().replace('-', '_')


def _looks_like_url(value: str) -> bool:
    return value.startswith(('http://', 'https://'))


def _redact_auth_tokens(value: str) -> str:
    value = _BASIC_AUTH_PATTERN.sub('Basic <redacted>', value)
    value = _BEARER_TOKEN_PATTERN.sub('Bearer <redacted>', value)
    return value


def _summarize_sensitive_value(value) -> dict[str, object]:
    if isinstance(value, Mapping):
        fingerprint_source = json.dumps(value, sort_keys=True, default=str)
        return {
            'redacted': True,
            'kind': 'mapping',
            'key_count': len(value),
            'keys': sorted(str(key) for key in value.keys())[:8],
            'sha256': _fingerprint(fingerprint_source),
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        fingerprint_source = json.dumps(list(value), sort_keys=True, default=str)
        return {
            'redacted': True,
            'kind': 'sequence',
            'item_count': len(value),
            'sha256': _fingerprint(fingerprint_source),
        }
    text = str(value)
    return {
        'redacted': True,
        'kind': 'text',
        'length': len(text),
        'sha256': _fingerprint(text),
    }


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]


def _json_default(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)
