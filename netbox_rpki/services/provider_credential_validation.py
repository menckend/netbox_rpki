from __future__ import annotations

import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.structured_logging import emit_structured_log
from netbox_rpki.services import provider_sync_krill
from netbox_rpki.services.provider_adapters import get_provider_adapter


PROVIDER_CREDENTIAL_VALIDATION_SCHEMA_VERSION = 1


def _capability_summary(provider_account: rpki_models.RpkiProviderAccount) -> dict[str, object]:
    adapter = get_provider_adapter(provider_account)
    profile = adapter.profile
    return {
        'supports_roa_read': profile.supports_roa_read,
        'supports_aspa_read': profile.supports_aspa_read,
        'supports_certificate_inventory': profile.supports_certificate_inventory,
        'supports_repository_metadata': profile.supports_repository_metadata,
        'supports_bulk_operations': profile.supports_bulk_operations,
        'supported_sync_families': list(profile.supported_sync_families),
        'roa_write_mode': profile.roa_write_mode,
        'aspa_write_mode': profile.aspa_write_mode,
    }


def _build_result(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    status: str,
    result_kind: str,
    summary: str,
    remediation: str,
    checks: list[dict[str, object]],
) -> dict[str, object]:
    return {
        'schema_version': PROVIDER_CREDENTIAL_VALIDATION_SCHEMA_VERSION,
        'provider_account_id': provider_account.pk,
        'provider_account_name': provider_account.name,
        'provider_type': provider_account.provider_type,
        'status': status,
        'result_kind': result_kind,
        'summary': summary,
        'remediation': remediation,
        'checked_at': timezone.now().isoformat(),
        'mutates_provider_state': False,
        'capability_summary': _capability_summary(provider_account),
        'checks': checks,
    }


def _credential_field_check(
    provider_account: rpki_models.RpkiProviderAccount,
) -> tuple[dict[str, object], list[object]]:
    adapter = get_provider_adapter(provider_account)
    issues = adapter.credential_issues(provider_account)
    if not issues:
        return {
            'code': 'credential_fields',
            'status': 'passed',
            'result_kind': 'ok',
            'summary': 'Required provider credential fields are present.',
            'remediation': '',
            'missing_fields': [],
        }, issues

    return {
        'code': 'credential_fields',
        'status': 'failed',
        'result_kind': 'configuration_error',
        'summary': 'Required provider credential fields are missing.',
        'remediation': 'Populate the missing fields before running a live credential test.',
        'missing_fields': [
            {
                'field_name': issue.field_name,
                'issue_text': issue.issue_text,
                'remediation': issue.remediation,
            }
            for issue in issues
        ],
    }, issues


def _live_probe_check(
    provider_account: rpki_models.RpkiProviderAccount,
    *,
    endpoint_label: str,
    request: Request,
    tls_context=None,
    success_summary: str,
    success_remediation: str = '',
) -> dict[str, object]:
    urlopen_kwargs = {'timeout': 15}
    if tls_context is not None:
        urlopen_kwargs['context'] = tls_context

    emit_structured_log(
        'provider_credentials.validation.start',
        subsystem='provider_sync',
        debug=True,
        provider_account_id=provider_account.pk,
        provider_type=provider_account.provider_type,
        endpoint_label=endpoint_label,
        method=request.get_method(),
        url=request.full_url,
        headers=dict(request.header_items()),
        tls_verification='disabled' if tls_context is not None else 'enabled',
    )
    try:
        with urlopen(request, **urlopen_kwargs) as response:
            response.read(256)
            content_type = response.headers.get('Content-Type', '')
            http_status = getattr(response, 'status', 200)
    except HTTPError as exc:
        if exc.code == 401:
            result_kind = 'auth_failure'
            summary = f'{endpoint_label} rejected the supplied credentials with HTTP 401.'
            remediation = 'Verify the provider API key or bearer token.'
        elif exc.code == 403:
            result_kind = 'permission_failure'
            summary = f'{endpoint_label} rejected the request with HTTP 403.'
            remediation = 'Verify the account or token has permission to read provider inventory.'
        elif exc.code == 404:
            result_kind = 'configuration_error'
            summary = f'{endpoint_label} returned HTTP 404 for the configured target.'
            remediation = 'Verify api_base_url and provider handle values such as org_handle or ca_handle.'
        else:
            result_kind = 'provider_error'
            summary = f'{endpoint_label} returned HTTP {exc.code}.'
            remediation = 'Review the provider endpoint configuration and provider-side logs.'
        emit_structured_log(
            'provider_credentials.validation.failure',
            subsystem='provider_sync',
            level='warning',
            provider_account_id=provider_account.pk,
            provider_type=provider_account.provider_type,
            endpoint_label=endpoint_label,
            method=request.get_method(),
            url=request.full_url,
            error=str(exc),
            error_type=type(exc).__name__,
            http_status=exc.code,
            result_kind=result_kind,
        )
        return {
            'code': 'live_probe',
            'status': 'failed',
            'result_kind': result_kind,
            'summary': summary,
            'remediation': remediation,
            'endpoint_label': endpoint_label,
            'method': request.get_method(),
            'url': request.full_url,
            'http_status': exc.code,
            'error_type': type(exc).__name__,
        }
    except (URLError, TimeoutError, socket.timeout, ssl.SSLError, ConnectionError) as exc:
        emit_structured_log(
            'provider_credentials.validation.failure',
            subsystem='provider_sync',
            level='warning',
            provider_account_id=provider_account.pk,
            provider_type=provider_account.provider_type,
            endpoint_label=endpoint_label,
            method=request.get_method(),
            url=request.full_url,
            error=str(exc),
            error_type=type(exc).__name__,
            result_kind='network_failure',
        )
        return {
            'code': 'live_probe',
            'status': 'failed',
            'result_kind': 'network_failure',
            'summary': f'{endpoint_label} could not be reached over the network.',
            'remediation': 'Verify api_base_url, DNS resolution, TLS trust, and firewall reachability.',
            'endpoint_label': endpoint_label,
            'method': request.get_method(),
            'url': request.full_url,
            'error_type': type(exc).__name__,
        }
    except ValueError as exc:
        emit_structured_log(
            'provider_credentials.validation.failure',
            subsystem='provider_sync',
            level='warning',
            provider_account_id=provider_account.pk,
            provider_type=provider_account.provider_type,
            endpoint_label=endpoint_label,
            method=request.get_method(),
            url=request.full_url,
            error=str(exc),
            error_type=type(exc).__name__,
            result_kind='configuration_error',
        )
        return {
            'code': 'live_probe',
            'status': 'failed',
            'result_kind': 'configuration_error',
            'summary': f'{endpoint_label} could not be probed with the configured URL or handle values.',
            'remediation': 'Verify api_base_url and provider handle values such as org_handle or ca_handle.',
            'endpoint_label': endpoint_label,
            'method': request.get_method(),
            'url': request.full_url,
            'error_type': type(exc).__name__,
        }
    except Exception as exc:
        emit_structured_log(
            'provider_credentials.validation.failure',
            subsystem='provider_sync',
            level='warning',
            provider_account_id=provider_account.pk,
            provider_type=provider_account.provider_type,
            endpoint_label=endpoint_label,
            method=request.get_method(),
            url=request.full_url,
            error=str(exc),
            error_type=type(exc).__name__,
            result_kind='provider_error',
        )
        return {
            'code': 'live_probe',
            'status': 'failed',
            'result_kind': 'provider_error',
            'summary': f'{endpoint_label} returned an unexpected provider-side failure.',
            'remediation': 'Review the provider endpoint configuration and provider-side logs.',
            'endpoint_label': endpoint_label,
            'method': request.get_method(),
            'url': request.full_url,
            'error_type': type(exc).__name__,
        }

    emit_structured_log(
        'provider_credentials.validation.success',
        subsystem='provider_sync',
        debug=True,
        provider_account_id=provider_account.pk,
        provider_type=provider_account.provider_type,
        endpoint_label=endpoint_label,
        method=request.get_method(),
        url=request.full_url,
        http_status=http_status,
        response_content_type=content_type,
    )
    return {
        'code': 'live_probe',
        'status': 'passed',
        'result_kind': 'ok',
        'summary': success_summary,
        'remediation': success_remediation,
        'endpoint_label': endpoint_label,
        'method': request.get_method(),
        'url': request.full_url,
        'http_status': http_status,
        'response_content_type': content_type,
    }


def validate_arin_provider_credentials(
    provider_account: rpki_models.RpkiProviderAccount,
) -> dict[str, object]:
    field_check, issues = _credential_field_check(provider_account)
    checks = [field_check]
    if issues:
        checks.append(
            {
                'code': 'live_probe',
                'status': 'skipped',
                'result_kind': 'not_run',
                'summary': 'Live provider probe was skipped because required credential fields are missing.',
                'remediation': 'Populate the missing fields and rerun the test.',
            }
        )
        return _build_result(
            provider_account,
            status='failed',
            result_kind='configuration_error',
            summary='Provider credential validation cannot run until the required fields are populated.',
            remediation='Populate the missing provider credential fields and rerun the test.',
            checks=checks,
        )

    base_url = provider_account.api_base_url.rstrip('/')
    query = urlencode({'apikey': provider_account.api_key})
    url = f'{base_url}/rest/roa/{provider_account.org_handle}?{query}'
    request = Request(
        url,
        headers={'Accept': 'application/xml'},
        method='GET',
    )
    live_check = _live_probe_check(
        provider_account,
        endpoint_label='ARIN hosted ROA authorization endpoint',
        request=request,
        success_summary='ARIN hosted ROA authorization endpoint accepted the configured credentials.',
    )
    checks.append(live_check)
    return _build_result(
        provider_account,
        status='passed' if live_check['status'] == 'passed' else 'failed',
        result_kind=str(live_check['result_kind']),
        summary=str(live_check['summary']),
        remediation=str(live_check.get('remediation', '')),
        checks=checks,
    )


def validate_krill_provider_credentials(
    provider_account: rpki_models.RpkiProviderAccount,
) -> dict[str, object]:
    field_check, issues = _credential_field_check(provider_account)
    checks = [field_check]
    if issues:
        checks.append(
            {
                'code': 'live_probe',
                'status': 'skipped',
                'result_kind': 'not_run',
                'summary': 'Live provider probe was skipped because required credential fields are missing.',
                'remediation': 'Populate the missing fields and rerun the test.',
            }
        )
        return _build_result(
            provider_account,
            status='failed',
            result_kind='configuration_error',
            summary='Provider credential validation cannot run until the required fields are populated.',
            remediation='Populate the missing provider credential fields and rerun the test.',
            checks=checks,
        )

    request = provider_sync_krill._krill_get_request(
        provider_account,
        provider_sync_krill.krill_ca_metadata_url(provider_account),
    )
    live_check = _live_probe_check(
        provider_account,
        endpoint_label='Krill CA metadata endpoint',
        request=request,
        tls_context=provider_sync_krill.krill_ssl_context(provider_account),
        success_summary='Krill CA metadata endpoint accepted the configured credentials.',
    )
    checks.append(live_check)
    return _build_result(
        provider_account,
        status='passed' if live_check['status'] == 'passed' else 'failed',
        result_kind=str(live_check['result_kind']),
        summary=str(live_check['summary']),
        remediation=str(live_check.get('remediation', '')),
        checks=checks,
    )


def validate_provider_account_credentials(
    provider_account: rpki_models.RpkiProviderAccount,
) -> dict[str, object]:
    adapter = get_provider_adapter(provider_account)
    return adapter.validate_credentials(provider_account)
