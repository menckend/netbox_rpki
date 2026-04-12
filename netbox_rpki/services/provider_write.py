from __future__ import annotations

import json
from urllib.request import Request, urlopen

from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_sync import (
    _krill_routes_url,
    _krill_ssl_context,
    sync_provider_account,
)


class ProviderWriteError(ValueError):
    pass


def _serialize_route_payload(*, asn: int | None, prefix: str, max_length: int | None, comment: str | None = None) -> dict:
    payload = {
        'asn': asn,
        'prefix': prefix,
        'max_length': max_length,
    }
    if comment:
        payload['comment'] = comment
    return payload


def _route_sort_key(payload: dict) -> tuple:
    return (
        str(payload.get('prefix') or ''),
        -1 if payload.get('asn') is None else int(payload['asn']),
        -1 if payload.get('max_length') is None else int(payload['max_length']),
        str(payload.get('comment') or ''),
    )


def _normalize_plan(plan: rpki_models.ROAChangePlan | int) -> rpki_models.ROAChangePlan:
    if isinstance(plan, rpki_models.ROAChangePlan):
        return plan
    return rpki_models.ROAChangePlan.objects.select_related(
        'organization',
        'provider_account',
        'provider_snapshot',
    ).get(pk=plan)


def _require_provider_write_capability(plan: rpki_models.ROAChangePlan) -> rpki_models.RpkiProviderAccount:
    if not plan.is_provider_backed:
        raise ProviderWriteError('This ROA change plan is not provider-backed.')

    provider_account = plan.provider_account
    if provider_account is None:
        raise ProviderWriteError('This ROA change plan does not target a provider account.')

    if not provider_account.supports_roa_write:
        raise ProviderWriteError(
            f'Provider account {provider_account.name} does not support ROA write operations.'
        )

    if provider_account.provider_type != rpki_models.ProviderType.KRILL:
        raise ProviderWriteError(
            f'Provider type {provider_account.provider_type} is not supported for ROA write operations.'
        )

    return provider_account


def _require_previewable(plan: rpki_models.ROAChangePlan) -> rpki_models.RpkiProviderAccount:
    provider_account = _require_provider_write_capability(plan)
    if plan.status not in {
        rpki_models.ROAChangePlanStatus.DRAFT,
        rpki_models.ROAChangePlanStatus.APPROVED,
        rpki_models.ROAChangePlanStatus.FAILED,
    }:
        raise ProviderWriteError('ROA change plans can only be previewed while draft, approved, or failed.')
    return provider_account


def _require_approvable(plan: rpki_models.ROAChangePlan) -> None:
    _require_provider_write_capability(plan)
    if plan.status != rpki_models.ROAChangePlanStatus.DRAFT:
        raise ProviderWriteError('Only draft ROA change plans can be approved.')


def _require_applicable(plan: rpki_models.ROAChangePlan) -> rpki_models.RpkiProviderAccount:
    provider_account = _require_provider_write_capability(plan)
    if plan.status == rpki_models.ROAChangePlanStatus.APPLIED:
        raise ProviderWriteError('This ROA change plan has already been applied.')
    if plan.status == rpki_models.ROAChangePlanStatus.APPLYING:
        raise ProviderWriteError('This ROA change plan is already being applied.')
    if plan.status != rpki_models.ROAChangePlanStatus.APPROVED:
        raise ProviderWriteError('ROA change plans must be approved before they can be applied.')
    return provider_account


def build_roa_change_plan_delta(
    plan: rpki_models.ROAChangePlan | int,
) -> dict[str, list[dict]]:
    plan = _normalize_plan(plan)
    _require_provider_write_capability(plan)

    added = []
    removed = []
    items = plan.items.exclude(provider_operation='').order_by('pk')
    for item in items:
        payload = dict(item.provider_payload_json or {})
        if item.provider_operation == rpki_models.ProviderWriteOperation.ADD_ROUTE:
            added.append(payload)
        elif item.provider_operation == rpki_models.ProviderWriteOperation.REMOVE_ROUTE:
            removed.append(payload)

    return {
        'added': sorted(added, key=_route_sort_key),
        'removed': sorted(removed, key=_route_sort_key),
    }


def approve_roa_change_plan(
    plan: rpki_models.ROAChangePlan | int,
    *,
    approved_by: str = '',
) -> rpki_models.ROAChangePlan:
    plan = _normalize_plan(plan)
    _require_approvable(plan)

    approved_at = timezone.now()
    plan.status = rpki_models.ROAChangePlanStatus.APPROVED
    plan.approved_at = approved_at
    plan.approved_by = approved_by
    plan.save(update_fields=('status', 'approved_at', 'approved_by'))
    return plan


def _create_execution(
    *,
    plan: rpki_models.ROAChangePlan,
    provider_account: rpki_models.RpkiProviderAccount,
    execution_mode: str,
    requested_by: str,
    status: str,
    started_at,
    completed_at=None,
    item_count: int = 0,
    request_payload_json: dict | None = None,
    response_payload_json: dict | None = None,
    error: str = '',
    followup_sync_run: rpki_models.ProviderSyncRun | None = None,
    followup_provider_snapshot: rpki_models.ProviderSnapshot | None = None,
) -> rpki_models.ProviderWriteExecution:
    return rpki_models.ProviderWriteExecution.objects.create(
        name=f'{plan.name} {execution_mode.title()} {started_at:%Y-%m-%d %H:%M:%S}',
        organization=plan.organization,
        provider_account=provider_account,
        provider_snapshot=plan.provider_snapshot,
        change_plan=plan,
        tenant=plan.tenant,
        execution_mode=execution_mode,
        status=status,
        requested_by=requested_by,
        started_at=started_at,
        completed_at=completed_at,
        item_count=item_count,
        request_payload_json=request_payload_json or {},
        response_payload_json=response_payload_json or {},
        error=error,
        followup_sync_run=followup_sync_run,
        followup_provider_snapshot=followup_provider_snapshot,
    )


def preview_roa_change_plan_provider_write(
    plan: rpki_models.ROAChangePlan | int,
    *,
    requested_by: str = '',
) -> tuple[rpki_models.ProviderWriteExecution, dict[str, list[dict]]]:
    plan = _normalize_plan(plan)
    provider_account = _require_previewable(plan)
    delta = build_roa_change_plan_delta(plan)
    started_at = timezone.now()
    execution = _create_execution(
        plan=plan,
        provider_account=provider_account,
        execution_mode=rpki_models.ProviderWriteExecutionMode.PREVIEW,
        requested_by=requested_by,
        status=rpki_models.ValidationRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=started_at,
        item_count=sum(len(values) for values in delta.values()),
        request_payload_json=delta,
        response_payload_json={
            'preview_only': True,
            'roa_write_mode': provider_account.roa_write_mode,
        },
    )
    return execution, delta


def _submit_krill_route_delta(
    provider_account: rpki_models.RpkiProviderAccount,
    delta: dict[str, list[dict]],
) -> dict:
    request = Request(
        _krill_routes_url(provider_account),
        data=json.dumps(delta).encode('utf-8'),
        headers={
            'Accept': 'application/json',
            'Authorization': f'Bearer {provider_account.api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    urlopen_kwargs = {'timeout': 30}
    ssl_context = _krill_ssl_context(provider_account)
    if ssl_context is not None:
        urlopen_kwargs['context'] = ssl_context

    with urlopen(request, **urlopen_kwargs) as response:
        raw_body = response.read().decode('utf-8').strip()

    if not raw_body:
        return {}

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return {'raw': raw_body}

    if isinstance(payload, dict):
        return payload
    return {'raw': payload}


def apply_roa_change_plan_provider_write(
    plan: rpki_models.ROAChangePlan | int,
    *,
    requested_by: str = '',
) -> tuple[rpki_models.ProviderWriteExecution, dict[str, list[dict]]]:
    plan = _normalize_plan(plan)
    provider_account = _require_applicable(plan)
    delta = build_roa_change_plan_delta(plan)
    started_at = timezone.now()
    plan.status = rpki_models.ROAChangePlanStatus.APPLYING
    plan.apply_started_at = started_at
    plan.apply_requested_by = requested_by
    plan.failed_at = None
    plan.save(update_fields=('status', 'apply_started_at', 'apply_requested_by', 'failed_at'))
    execution = _create_execution(
        plan=plan,
        provider_account=provider_account,
        execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
        requested_by=requested_by,
        status=rpki_models.ValidationRunStatus.RUNNING,
        started_at=started_at,
        item_count=sum(len(values) for values in delta.values()),
        request_payload_json=delta,
    )

    try:
        provider_response = _submit_krill_route_delta(provider_account, delta)
        applied_at = timezone.now()
        plan.status = rpki_models.ROAChangePlanStatus.APPLIED
        plan.applied_at = applied_at
        plan.save(update_fields=('status', 'applied_at'))

        response_payload_json = {
            'provider_response': provider_response,
            'roa_write_mode': provider_account.roa_write_mode,
        }
        followup_sync_run = None
        followup_snapshot = None
        try:
            followup_sync_run, followup_snapshot = sync_provider_account(
                provider_account,
                snapshot_name=(
                    f'{provider_account.name} Post-Apply Snapshot {applied_at:%Y-%m-%d %H:%M:%S}'
                ),
            )
            response_payload_json['followup_sync'] = {
                'provider_sync_run_id': followup_sync_run.pk,
                'provider_snapshot_id': followup_snapshot.pk,
                'status': followup_sync_run.status,
            }
            execution.status = rpki_models.ValidationRunStatus.COMPLETED
        except Exception as exc:
            response_payload_json['followup_sync'] = {
                'status': rpki_models.ValidationRunStatus.FAILED,
                'error': str(exc),
            }
            execution.status = rpki_models.ValidationRunStatus.FAILED
            execution.error = str(exc)

        execution.completed_at = timezone.now()
        execution.response_payload_json = response_payload_json
        execution.followup_sync_run = followup_sync_run
        execution.followup_provider_snapshot = followup_snapshot
        execution.save(update_fields=(
            'status',
            'completed_at',
            'response_payload_json',
            'error',
            'followup_sync_run',
            'followup_provider_snapshot',
        ))
        return execution, delta
    except Exception as exc:
        completed_at = timezone.now()
        plan.status = rpki_models.ROAChangePlanStatus.FAILED
        plan.failed_at = completed_at
        plan.save(update_fields=('status', 'failed_at'))
        execution.status = rpki_models.ValidationRunStatus.FAILED
        execution.completed_at = completed_at
        execution.error = str(exc)
        execution.response_payload_json = {
            'roa_write_mode': provider_account.roa_write_mode,
        }
        execution.save(update_fields=('status', 'completed_at', 'error', 'response_payload_json'))
        raise ProviderWriteError(str(exc)) from exc