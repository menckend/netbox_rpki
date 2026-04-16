from __future__ import annotations

import importlib.util
import json
import sys
from typing import Any

from django.apps import apps
from django.conf import settings
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from netbox_rpki import __version__, models as rpki_models
from netbox_rpki.compatibility import classify_runtime
from netbox_rpki.services.provider_adapters import get_provider_adapter


CHECK_STATUS_OK = 'ok'
CHECK_STATUS_ADVISORY = 'advisory'
CHECK_STATUS_FATAL = 'fatal'
CHECK_STATUS_ORDER = {
    CHECK_STATUS_FATAL: 0,
    CHECK_STATUS_ADVISORY: 1,
    CHECK_STATUS_OK: 2,
}

DIAGNOSTIC_SCHEMA_VERSION = 1


def _build_check(
    *,
    code: str,
    status: str,
    summary: str,
    remediation: str = '',
    scope: str = 'global',
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        'code': code,
        'status': status,
        'scope': scope,
        'summary': summary,
        'remediation': remediation,
        'details': details or {},
    }


def _sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(config)
    for sensitive_key in ('PASSWORD', 'USERNAME'):
        if sanitized.get(sensitive_key):
            sanitized[sensitive_key] = '***'
    return sanitized


def _pending_plugin_migrations() -> list[str]:
    connection = connections['default']
    executor = MigrationExecutor(connection)
    targets = [
        node
        for node in executor.loader.graph.leaf_nodes()
        if node[0] == 'netbox_rpki'
    ]
    plan = executor.migration_plan(targets)
    return [
        migration.name
        for migration, backwards in plan
        if migration.app_label == 'netbox_rpki' and not backwards
    ]


def _redis_ping(config: dict[str, Any]) -> tuple[bool, str]:
    if importlib.util.find_spec('redis') is None:
        return False, 'Python package "redis" is not installed.'

    import redis

    client = redis.Redis(
        host=config.get('HOST'),
        port=config.get('PORT'),
        db=config.get('DATABASE', 0),
        username=config.get('USERNAME') or None,
        password=config.get('PASSWORD') or None,
        ssl=bool(config.get('SSL')),
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        client.ping()
    except Exception as exc:  # pragma: no cover - exercised in integration, not unit behavior
        return False, str(exc)
    return True, 'ping ok'


def _provider_account_checks(provider_account: rpki_models.RpkiProviderAccount) -> list[dict[str, Any]]:
    scope = f'provider_account:{provider_account.pk}'
    details = {
        'provider_account_id': provider_account.pk,
        'provider_type': provider_account.provider_type,
        'sync_enabled': provider_account.sync_enabled,
        'capability_matrix': provider_account.capability_matrix,
    }
    if not provider_account.sync_enabled:
        return [
            _build_check(
                code='providers.credentials',
                status=CHECK_STATUS_ADVISORY,
                scope=scope,
                summary=(
                    f'Provider account "{provider_account.name}" has sync disabled; credential checks are informational only.'
                ),
                remediation='Enable sync when this account is ready for provider import or write workflows.',
                details=details,
            )
        ]

    adapter = get_provider_adapter(provider_account)
    credential_issues = adapter.credential_issues(provider_account)
    issues = [issue.issue_text for issue in credential_issues]
    remediation = [issue.remediation for issue in credential_issues]

    if issues:
        return [
            _build_check(
                code='providers.credentials',
                status=CHECK_STATUS_FATAL,
                scope=scope,
                summary=(
                    f'Provider account "{provider_account.name}" is missing required wiring: {", ".join(issues)}.'
                ),
                remediation=' '.join(remediation),
                details=details,
            )
        ]

    return [
        _build_check(
            code='providers.credentials',
            status=CHECK_STATUS_OK,
            scope=scope,
            summary=(
                f'Provider account "{provider_account.name}" is wired for its declared '
                f'{provider_account.get_provider_type_display()} capabilities.'
            ),
            details=details,
        )
    ]


def _irr_source_checks(source: rpki_models.IrrSource) -> list[dict[str, Any]]:
    scope = f'irr_source:{source.pk}'
    details = {
        'irr_source_id': source.pk,
        'enabled': source.enabled,
        'write_support_mode': source.write_support_mode,
        'supports_preview': source.supports_preview,
        'supports_apply': source.supports_apply,
    }
    if not source.enabled:
        return [
            _build_check(
                code='irr.credentials',
                status=CHECK_STATUS_ADVISORY,
                scope=scope,
                summary=f'IRR source "{source.name}" is disabled; live-source diagnostics are informational only.',
                remediation='Enable the source when IRR import or coordination workflows are needed.',
                details=details,
            )
        ]

    issues: list[str] = []
    remediation: list[str] = []
    if not (source.query_base_url or '').strip():
        issues.append('query_base_url is blank')
        remediation.append('Set query_base_url for live IRRd-compatible imports.')
    if source.supports_apply and not (source.api_key or '').strip():
        issues.append('api_key is blank for apply-capable write mode')
        remediation.append('Set api_key or lower write_support_mode to preview_only/unsupported.')

    if issues:
        return [
            _build_check(
                code='irr.credentials',
                status=CHECK_STATUS_FATAL,
                scope=scope,
                summary=f'IRR source "{source.name}" is missing required wiring: {", ".join(issues)}.',
                remediation=' '.join(remediation),
                details=details,
            )
        ]

    return [
        _build_check(
            code='irr.credentials',
            status=CHECK_STATUS_OK,
            scope=scope,
            summary=f'IRR source "{source.name}" is wired for its declared import/write capabilities.',
            details=details,
        )
    ]


def _validator_checks(validator: rpki_models.ValidatorInstance) -> list[dict[str, Any]]:
    scope = f'validator_instance:{validator.pk}'
    details = {
        'validator_instance_id': validator.pk,
        'software_name': validator.software_name,
        'base_url': validator.base_url,
    }
    if not (validator.base_url or '').strip():
        return [
            _build_check(
                code='validators.live_api',
                status=CHECK_STATUS_ADVISORY,
                scope=scope,
                summary=(
                    f'Validator instance "{validator.name}" has no base_url; live API imports are unavailable.'
                ),
                remediation='Set base_url to enable live Routinator jsonext imports, or rely on snapshot_import mode.',
                details=details,
            )
        ]

    return [
        _build_check(
            code='validators.live_api',
            status=CHECK_STATUS_OK,
            scope=scope,
            summary=f'Validator instance "{validator.name}" is configured for live API imports.',
            details=details,
        )
    ]


def build_install_diagnostic_report() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    runtime = classify_runtime(
        netbox_version=getattr(settings, 'VERSION', '0'),
        python_version=sys.version_info[:2],
    )
    runtime_status = {
        'ga': CHECK_STATUS_OK,
        'beta': CHECK_STATUS_ADVISORY,
        'best_effort': CHECK_STATUS_ADVISORY,
        'unsupported': CHECK_STATUS_FATAL,
    }[runtime.status]
    checks.append(
        _build_check(
            code='runtime.compatibility',
            status=runtime_status,
            summary=runtime.message,
            remediation='Use a NetBox 4.5.x runtime on Python 3.12-3.14, preferring a GA combination for release use.',
            details={
                'netbox_version': getattr(settings, 'VERSION', '0'),
                'python_version': f'{sys.version_info.major}.{sys.version_info.minor}',
                'compatibility_status': runtime.status,
            },
        )
    )

    configured_plugins = tuple(getattr(settings, 'PLUGINS', ()) or ())
    plugin_configured = 'netbox_rpki' in configured_plugins
    checks.append(
        _build_check(
            code='plugin.settings_registration',
            status=CHECK_STATUS_OK if plugin_configured else CHECK_STATUS_FATAL,
            summary=(
                'Plugin is present in settings.PLUGINS.'
                if plugin_configured
                else 'Plugin is missing from settings.PLUGINS.'
            ),
            remediation='Add "netbox_rpki" to PLUGINS in the NetBox configuration.',
            details={'configured_plugins': list(configured_plugins)},
        )
    )

    try:
        app_config = apps.get_app_config('netbox_rpki')
    except LookupError:
        app_config = None
    checks.append(
        _build_check(
            code='plugin.app_registry',
            status=CHECK_STATUS_OK if app_config is not None else CHECK_STATUS_FATAL,
            summary=(
                f'Plugin app registry entry is loaded as "{app_config.name}".'
                if app_config is not None
                else 'Plugin app registry entry is not loaded.'
            ),
            remediation='Restart NetBox after enabling the plugin and verify startup logs.',
            details={'app_config_name': getattr(app_config, 'name', '')},
        )
    )

    engine = settings.DATABASES['default'].get('ENGINE', '')
    checks.append(
        _build_check(
            code='database.engine',
            status=CHECK_STATUS_OK if 'postgresql' in engine else CHECK_STATUS_FATAL,
            summary=(
                f'Database engine "{engine}" is PostgreSQL-compatible.'
                if 'postgresql' in engine
                else f'Database engine "{engine}" is not PostgreSQL-compatible.'
            ),
            remediation='Run NetBox against PostgreSQL, which is required by NetBox itself.',
            details={'engine': engine},
        )
    )

    try:
        connections['default'].ensure_connection()
    except Exception as exc:
        checks.append(
            _build_check(
                code='database.connection',
                status=CHECK_STATUS_FATAL,
                summary=f'Could not connect to the default database: {exc}',
                remediation='Verify DATABASES["default"] credentials, host, port, and PostgreSQL availability.',
            )
        )
    else:
        checks.append(
            _build_check(
                code='database.connection',
                status=CHECK_STATUS_OK,
                summary='Connected to the default database successfully.',
            )
        )

        pending_migrations = _pending_plugin_migrations()
        checks.append(
            _build_check(
                code='database.migrations',
                status=CHECK_STATUS_OK if not pending_migrations else CHECK_STATUS_FATAL,
                summary=(
                    'All netbox_rpki migrations are applied.'
                    if not pending_migrations
                    else f'Pending netbox_rpki migrations detected: {", ".join(pending_migrations)}.'
                ),
                remediation='Run `manage.py migrate netbox_rpki` before using plugin workflows.',
                details={'pending_migrations': pending_migrations},
            )
        )

    redis_config = dict(getattr(settings, 'REDIS', {}) or {})
    for section_name, failure_status, remediation in (
        ('tasks', CHECK_STATUS_FATAL, 'Configure REDIS["tasks"] so NetBox background jobs can run.'),
        ('caching', CHECK_STATUS_ADVISORY, 'Configure REDIS["caching"] so cache-backed behavior is available.'),
    ):
        section_config = dict(redis_config.get(section_name) or {})
        missing_fields = [
            field for field in ('HOST', 'PORT', 'DATABASE')
            if section_config.get(field) in (None, '')
        ]
        if missing_fields:
            checks.append(
                _build_check(
                    code=f'redis.{section_name}_config',
                    status=failure_status,
                    summary=(
                        f'Redis "{section_name}" configuration is incomplete; missing {", ".join(missing_fields)}.'
                    ),
                    remediation=remediation,
                    details={'config': _sanitize_config(section_config)},
                )
            )
            continue

        checks.append(
            _build_check(
                code=f'redis.{section_name}_config',
                status=CHECK_STATUS_OK,
                summary=f'Redis "{section_name}" configuration is present.',
                details={'config': _sanitize_config(section_config)},
            )
        )
        ok, message = _redis_ping(section_config)
        checks.append(
            _build_check(
                code=f'redis.{section_name}_connectivity',
                status=CHECK_STATUS_OK if ok else failure_status,
                summary=(
                    f'Redis "{section_name}" backend responded to ping.'
                    if ok
                    else f'Redis "{section_name}" backend could not be reached: {message}'
                ),
                remediation=remediation,
                details={'config': _sanitize_config(section_config)},
            )
        )

    for provider_account in rpki_models.RpkiProviderAccount.objects.select_related('organization').order_by('name', 'pk'):
        checks.extend(_provider_account_checks(provider_account))

    for source in rpki_models.IrrSource.objects.select_related('organization').order_by('organization__name', 'name', 'pk'):
        checks.extend(_irr_source_checks(source))

    for validator in rpki_models.ValidatorInstance.objects.select_related('organization').order_by('name', 'pk'):
        checks.extend(_validator_checks(validator))

    status_counts = {
        status: sum(1 for check in checks if check['status'] == status)
        for status in (CHECK_STATUS_FATAL, CHECK_STATUS_ADVISORY, CHECK_STATUS_OK)
    }
    overall_status = CHECK_STATUS_OK
    if status_counts[CHECK_STATUS_FATAL]:
        overall_status = CHECK_STATUS_FATAL
    elif status_counts[CHECK_STATUS_ADVISORY]:
        overall_status = CHECK_STATUS_ADVISORY

    checks.sort(
        key=lambda check: (
            CHECK_STATUS_ORDER[check['status']],
            check['code'],
            check['scope'],
        )
    )
    return {
        'schema_version': DIAGNOSTIC_SCHEMA_VERSION,
        'generated_at': timezone.now().isoformat(),
        'plugin_version': __version__,
        'overall_status': overall_status,
        'summary': {
            'check_count': len(checks),
            'fatal_count': status_counts[CHECK_STATUS_FATAL],
            'advisory_count': status_counts[CHECK_STATUS_ADVISORY],
            'ok_count': status_counts[CHECK_STATUS_OK],
        },
        'checks': checks,
    }


def render_install_diagnostic_text(report: dict[str, Any]) -> str:
    summary = report.get('summary') or {}
    lines = [
        'netbox_rpki install diagnostic',
        f'Overall status: {report.get("overall_status", CHECK_STATUS_OK)}',
        (
            'Summary: '
            f'{summary.get("fatal_count", 0)} fatal, '
            f'{summary.get("advisory_count", 0)} advisory, '
            f'{summary.get("ok_count", 0)} ok'
        ),
        '',
    ]
    for check in report.get('checks') or []:
        lines.append(
            f'[{check["status"].upper()}] {check["code"]} [{check["scope"]}] {check["summary"]}'
        )
        if check.get('remediation'):
            lines.append(f'  Remediation: {check["remediation"]}')
    return '\n'.join(lines)


def render_install_diagnostic_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)
