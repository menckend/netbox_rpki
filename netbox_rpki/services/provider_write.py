from __future__ import annotations

import json
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.structured_logging import emit_structured_log
from netbox_rpki.services.provider_adapters import (
    ProviderAdapterLookupError,
    get_provider_adapter,
)
from netbox_rpki.services.provider_sync import sync_provider_account
from netbox_rpki.services.provider_sync_krill import krill_aspas_url, krill_routes_url, krill_ssl_context
from netbox_rpki.services.roa_lint import build_roa_change_plan_lint_posture, refresh_roa_change_plan_lint_posture
from netbox_rpki.services.rov_simulation import require_roa_change_plan_simulation_approvable


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


def _aspa_delta_sort_key(payload: dict) -> tuple:
    return (
        -1 if payload.get('customer_asn') is None else int(payload['customer_asn']),
        tuple(int(value) for value in (payload.get('provider_asns') or [])),
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


def _normalize_aspa_plan(plan: rpki_models.ASPAChangePlan | int) -> rpki_models.ASPAChangePlan:
    if isinstance(plan, rpki_models.ASPAChangePlan):
        return plan
    return rpki_models.ASPAChangePlan.objects.select_related(
        'organization',
        'provider_account',
        'provider_snapshot',
    ).get(pk=plan)


def _plan_family(plan) -> str:
    if isinstance(plan, rpki_models.ASPAChangePlan):
        return 'ASPA'
    return 'ROA'


def _require_provider_write_capability(plan: rpki_models.ROAChangePlan) -> rpki_models.RpkiProviderAccount:
    if not plan.is_provider_backed:
        raise ProviderWriteError('This ROA change plan is not provider-backed.')

    provider_account = plan.provider_account
    if provider_account is None:
        raise ProviderWriteError('This ROA change plan does not target a provider account.')

    try:
        get_provider_adapter(provider_account).ensure_roa_write_supported(provider_account)
    except (ProviderAdapterLookupError, ValueError) as exc:
        raise ProviderWriteError(str(exc)) from exc

    return provider_account


def _require_aspa_provider_write_capability(plan: rpki_models.ASPAChangePlan) -> rpki_models.RpkiProviderAccount:
    if not plan.is_provider_backed:
        raise ProviderWriteError('This ASPA change plan is not provider-backed.')

    provider_account = plan.provider_account
    if provider_account is None:
        raise ProviderWriteError('This ASPA change plan does not target a provider account.')

    try:
        get_provider_adapter(provider_account).ensure_aspa_write_supported(provider_account)
    except (ProviderAdapterLookupError, ValueError) as exc:
        raise ProviderWriteError(str(exc)) from exc

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


def _require_aspa_previewable(plan: rpki_models.ASPAChangePlan) -> rpki_models.RpkiProviderAccount:
    provider_account = _require_aspa_provider_write_capability(plan)
    if plan.status not in {
        rpki_models.ASPAChangePlanStatus.DRAFT,
        rpki_models.ASPAChangePlanStatus.APPROVED,
        rpki_models.ASPAChangePlanStatus.FAILED,
    }:
        raise ProviderWriteError('ASPA change plans can only be previewed while draft, approved, or failed.')
    return provider_account


def _require_approvable(plan: rpki_models.ROAChangePlan) -> None:
    _require_provider_write_capability(plan)
    if plan.status != rpki_models.ROAChangePlanStatus.DRAFT:
        raise ProviderWriteError('Only draft ROA change plans can be approved.')


def _require_aspa_approvable(plan: rpki_models.ASPAChangePlan) -> None:
    _require_aspa_provider_write_capability(plan)
    if plan.status != rpki_models.ASPAChangePlanStatus.DRAFT:
        raise ProviderWriteError('Only draft ASPA change plans can be approved.')


def _require_applicable(plan: rpki_models.ROAChangePlan) -> rpki_models.RpkiProviderAccount:
    provider_account = _require_provider_write_capability(plan)
    if plan.status == rpki_models.ROAChangePlanStatus.APPLIED:
        raise ProviderWriteError('This ROA change plan has already been applied.')
    if plan.status == rpki_models.ROAChangePlanStatus.APPLYING:
        raise ProviderWriteError('This ROA change plan is already being applied.')
    if plan.status not in {
        rpki_models.ROAChangePlanStatus.APPROVED,
        rpki_models.ROAChangePlanStatus.FAILED,
    }:
        raise ProviderWriteError('ROA change plans must be approved before they can be applied.')
    return provider_account


def _require_aspa_applicable(plan: rpki_models.ASPAChangePlan) -> rpki_models.RpkiProviderAccount:
    provider_account = _require_aspa_provider_write_capability(plan)
    if plan.status == rpki_models.ASPAChangePlanStatus.APPLIED:
        raise ProviderWriteError('This ASPA change plan has already been applied.')
    if plan.status == rpki_models.ASPAChangePlanStatus.APPLYING:
        raise ProviderWriteError('This ASPA change plan is already being applied.')
    if plan.status not in {
        rpki_models.ASPAChangePlanStatus.APPROVED,
        rpki_models.ASPAChangePlanStatus.FAILED,
    }:
        raise ProviderWriteError('ASPA change plans must be approved before they can be applied.')
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


def build_aspa_change_plan_delta(
    plan: rpki_models.ASPAChangePlan | int,
) -> dict[str, list[dict]]:
    plan = _normalize_aspa_plan(plan)
    _require_aspa_provider_write_capability(plan)

    added = []
    removed = []
    items = plan.items.exclude(provider_operation='').order_by('pk')
    for item in items:
        payload = dict(item.provider_payload_json or {})
        if item.provider_operation == rpki_models.ProviderWriteOperation.ADD_PROVIDER_SET:
            if item.plan_semantic in {
                rpki_models.ASPAChangePlanItemSemantic.CREATE,
                rpki_models.ASPAChangePlanItemSemantic.REPLACE,
                rpki_models.ASPAChangePlanItemSemantic.RESHAPE,
            }:
                added.append(payload)
        elif item.provider_operation == rpki_models.ProviderWriteOperation.REMOVE_PROVIDER_SET:
            if item.plan_semantic in {
                rpki_models.ASPAChangePlanItemSemantic.WITHDRAW,
                rpki_models.ASPAChangePlanItemSemantic.REMOVE_PROVIDER,
            }:
                removed.append(payload)

    return {
        'added': sorted(added, key=_aspa_delta_sort_key),
        'removed': sorted(removed, key=_aspa_delta_sort_key),
    }


def _normalize_preview_state(value: dict | None) -> dict:
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in sorted(value)}


def _build_preview_state_diff(before_state: dict, after_state: dict) -> list[dict[str, object]]:
    state_diff = []
    for key in sorted(set(before_state) | set(after_state)):
        before_value = before_state.get(key)
        after_value = after_state.get(key)
        if before_value == after_value:
            continue
        state_diff.append({
            'field': key,
            'before': before_value,
            'after': after_value,
        })
    return state_diff


def _serialize_provider_request_payload(
    provider_account: rpki_models.RpkiProviderAccount,
    delta: dict[str, list[dict]],
    *,
    family: str,
) -> dict[str, list[dict]]:
    if provider_account.provider_type == rpki_models.ProviderType.KRILL and family == 'ASPA':
        return _serialize_krill_aspa_delta(delta)
    return {
        'added': [dict(entry) for entry in delta.get('added', [])],
        'removed': [dict(entry) for entry in delta.get('removed', [])],
    }


def _build_roa_preview_item(item: rpki_models.ROAChangePlanItem) -> dict[str, object]:
    before_state = _normalize_preview_state(item.before_state_json)
    after_state = _normalize_preview_state(item.after_state_json)
    plan_semantic = item.plan_semantic or item.action_type or ''
    dangerous_reasons = []
    attention_level = 'info'
    if before_state:
        dangerous_reasons.append('Removes or mutates currently published Krill state.')
        attention_level = 'danger'
    elif plan_semantic == rpki_models.ROAChangePlanItemSemantic.RESHAPE:
        dangerous_reasons.append('Adjusts an existing authorization shape before it is re-published.')
        attention_level = 'warning'
    return {
        'id': item.pk,
        'name': item.name,
        'object_family': 'ROA',
        'object_key': '|'.join(
            str(value or '')
            for value in (
                before_state.get('prefix_cidr_text') or after_state.get('prefix_cidr_text'),
                before_state.get('origin_asn_value') or after_state.get('origin_asn_value'),
                before_state.get('max_length_value') or after_state.get('max_length_value'),
            )
        ),
        'action_type': item.action_type,
        'plan_semantic': plan_semantic,
        'provider_operation': item.provider_operation,
        'provider_payload': dict(item.provider_payload_json or {}),
        'before_state': before_state,
        'after_state': after_state,
        'state_diff': _build_preview_state_diff(before_state, after_state),
        'reason': item.reason,
        'is_dangerous': bool(dangerous_reasons),
        'attention_level': attention_level,
        'dangerous_reasons': dangerous_reasons,
    }


def _build_aspa_preview_item(item: rpki_models.ASPAChangePlanItem) -> dict[str, object]:
    before_state = _normalize_preview_state(item.before_state_json)
    after_state = _normalize_preview_state(item.after_state_json)
    plan_semantic = item.plan_semantic or item.action_type or ''
    dangerous_reasons = []
    attention_level = 'info'
    if plan_semantic in {
        rpki_models.ASPAChangePlanItemSemantic.WITHDRAW,
        rpki_models.ASPAChangePlanItemSemantic.REMOVE_PROVIDER,
        rpki_models.ASPAChangePlanItemSemantic.REPLACE,
        rpki_models.ASPAChangePlanItemSemantic.RESHAPE,
    } or before_state:
        dangerous_reasons.append('Withdraws or rewrites currently published ASPA provider authorization state.')
        attention_level = 'danger'
    elif plan_semantic == rpki_models.ASPAChangePlanItemSemantic.ADD_PROVIDER:
        dangerous_reasons.append('Expands the allowed upstream provider set for this customer ASN.')
        attention_level = 'warning'
    return {
        'id': item.pk,
        'name': item.name,
        'object_family': 'ASPA',
        'object_key': str(
            before_state.get('customer_asn')
            or after_state.get('customer_asn')
            or ''
        ),
        'action_type': item.action_type,
        'plan_semantic': plan_semantic,
        'provider_operation': item.provider_operation,
        'provider_payload': dict(item.provider_payload_json or {}),
        'before_state': before_state,
        'after_state': after_state,
        'state_diff': _build_preview_state_diff(before_state, after_state),
        'reason': item.reason,
        'is_dangerous': bool(dangerous_reasons),
        'attention_level': attention_level,
        'dangerous_reasons': dangerous_reasons,
    }


def _build_preview_summary(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    family: str,
    delta: dict[str, list[dict]],
    items: list[dict[str, object]],
) -> dict[str, object]:
    dangerous_items = [item for item in items if item['is_dangerous']]
    attention_counts = {'danger': 0, 'warning': 0, 'info': 0}
    for item in items:
        attention_level = str(item.get('attention_level') or 'info')
        attention_counts[attention_level] = attention_counts.get(attention_level, 0) + 1
    return {
        'schema_version': 1,
        'family': family.lower(),
        'family_display': family,
        'provider_account_id': provider_account.pk,
        'provider_account_name': provider_account.name,
        'provider_type': provider_account.provider_type,
        'provider_type_display': provider_account.get_provider_type_display(),
        'item_count': len(items),
        'added_count': len(delta.get('added', [])),
        'removed_count': len(delta.get('removed', [])),
        'has_dangerous_changes': bool(dangerous_items),
        'dangerous_change_count': len(dangerous_items),
        'attention_counts': attention_counts,
        'provider_request': _serialize_provider_request_payload(
            provider_account,
            delta,
            family=family,
        ),
        'items': items,
    }


def build_roa_change_plan_preview_report(
    plan: rpki_models.ROAChangePlan | int,
) -> dict[str, object]:
    plan = _normalize_plan(plan)
    provider_account = _require_previewable(plan)
    delta = build_roa_change_plan_delta(plan)
    items = [
        _build_roa_preview_item(item)
        for item in plan.items.exclude(provider_operation='').order_by('pk')
    ]
    preview_report = _build_preview_summary(
        provider_account=provider_account,
        family='ROA',
        delta=delta,
        items=items,
    )
    preview_report['change_plan_id'] = plan.pk
    preview_report['change_plan_name'] = plan.name
    preview_report['governance'] = _get_plan_governance_metadata(plan)
    return preview_report


def build_aspa_change_plan_preview_report(
    plan: rpki_models.ASPAChangePlan | int,
) -> dict[str, object]:
    plan = _normalize_aspa_plan(plan)
    provider_account = _require_aspa_previewable(plan)
    delta = build_aspa_change_plan_delta(plan)
    items = [
        _build_aspa_preview_item(item)
        for item in plan.items.exclude(provider_operation='').order_by('pk')
    ]
    preview_report = _build_preview_summary(
        provider_account=provider_account,
        family='ASPA',
        delta=delta,
        items=items,
    )
    preview_report['change_plan_id'] = plan.pk
    preview_report['change_plan_name'] = plan.name
    preview_report['governance'] = _get_plan_governance_metadata(plan)
    preview_report['delegated_scope'] = _get_plan_delegated_scope_metadata(plan)
    return preview_report


def _empty_delta() -> dict[str, list[dict]]:
    return {
        'added': [],
        'removed': [],
    }


def _payload_identity(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def _merge_delta(target: dict[str, list[dict]], delta: dict[str, list[dict]]) -> dict[str, list[dict]]:
    merged = {
        'added': [dict(entry) for entry in target.get('added', [])],
        'removed': [dict(entry) for entry in target.get('removed', [])],
    }
    for key in ('added', 'removed'):
        seen = {_payload_identity(entry) for entry in merged[key]}
        for entry in delta.get(key, []):
            candidate = dict(entry)
            candidate_key = _payload_identity(candidate)
            if candidate_key in seen:
                continue
            merged[key].append(candidate)
            seen.add(candidate_key)
    return merged


def _delta_item_count(delta: dict[str, list[dict]]) -> int:
    return sum(len(values) for values in delta.values())


def _build_roa_item_batch(item: rpki_models.ROAChangePlanItem) -> dict[str, object] | None:
    payload = dict(item.provider_payload_json or {})
    if item.provider_operation == rpki_models.ProviderWriteOperation.ADD_ROUTE:
        request_delta = {'added': [payload], 'removed': []}
    elif item.provider_operation == rpki_models.ProviderWriteOperation.REMOVE_ROUTE:
        request_delta = {'added': [], 'removed': [payload]}
    else:
        return None

    before_state = _normalize_preview_state(item.before_state_json)
    after_state = _normalize_preview_state(item.after_state_json)
    return {
        'item_id': item.pk,
        'item_name': item.name,
        'plan_semantic': item.plan_semantic or item.action_type or '',
        'provider_operation': item.provider_operation,
        'provider_payload': payload,
        'request_delta': request_delta,
        'before_state': before_state,
        'after_state': after_state,
        'state_diff': _build_preview_state_diff(before_state, after_state),
        'reason': item.reason,
    }


def _build_aspa_item_batch(item: rpki_models.ASPAChangePlanItem) -> dict[str, object] | None:
    payload = dict(item.provider_payload_json or {})
    if item.provider_operation == rpki_models.ProviderWriteOperation.ADD_PROVIDER_SET:
        request_delta = {'added': [payload], 'removed': []}
    elif item.provider_operation == rpki_models.ProviderWriteOperation.REMOVE_PROVIDER_SET:
        request_delta = {'added': [], 'removed': [payload]}
    else:
        return None

    before_state = _normalize_preview_state(item.before_state_json)
    after_state = _normalize_preview_state(item.after_state_json)
    return {
        'item_id': item.pk,
        'item_name': item.name,
        'plan_semantic': item.plan_semantic or item.action_type or '',
        'provider_operation': item.provider_operation,
        'provider_payload': payload,
        'request_delta': request_delta,
        'before_state': before_state,
        'after_state': after_state,
        'state_diff': _build_preview_state_diff(before_state, after_state),
        'reason': item.reason,
    }


def _build_plan_item_batches(plan) -> list[dict[str, object]]:
    item_batches: list[dict[str, object]] = []
    items = plan.items.exclude(provider_operation='').order_by('pk')
    for item in items:
        if isinstance(plan, rpki_models.ASPAChangePlan):
            batch = _build_aspa_item_batch(item)
        else:
            batch = _build_roa_item_batch(item)
        if batch is not None:
            item_batches.append(batch)
    return item_batches


def _request_item_signatures(item_batches: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            'item_id': batch.get('item_id'),
            'provider_operation': batch.get('provider_operation'),
            'provider_payload': dict(batch.get('provider_payload') or {}),
        }
        for batch in item_batches
    ]


def _latest_apply_execution(plan) -> rpki_models.ProviderWriteExecution | None:
    return (
        plan.provider_write_executions
        .filter(execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY)
        .order_by('-started_at', '-created')
        .first()
    )


def _resolve_apply_item_batches(
    plan,
    item_batches: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    context = {
        'retry_mode': 'full',
        'retry_source_execution_id': None,
        'safe_retry': False,
        'automatic_failed_only': False,
        'failed_item_ids': [],
        'successful_item_count_previous': 0,
    }
    if plan.status != rpki_models.ROAChangePlanStatus.FAILED and plan.status != rpki_models.ASPAChangePlanStatus.FAILED:
        return item_batches, context

    latest_execution = _latest_apply_execution(plan)
    if latest_execution is None:
        raise ProviderWriteError(
            f'{_plan_family(plan)} change plan retries require an earlier apply execution record.'
        )

    previous_request = dict(latest_execution.request_payload_json or {})
    previous_item_batches = list(previous_request.get('item_batches') or [])
    if not previous_item_batches:
        raise ProviderWriteError(
            f'{_plan_family(plan)} change plan retries are only supported for executions with per-item batch audit.'
        )

    current_signatures = _request_item_signatures(item_batches)
    previous_signatures = _request_item_signatures(previous_item_batches)
    if current_signatures != previous_signatures:
        raise ProviderWriteError(
            f'{_plan_family(plan)} change plan payload changed since the failed execution; review or regenerate before retrying.'
        )

    previous_results = list((latest_execution.response_payload_json or {}).get('item_results') or [])
    failed_item_ids = [
        item_result.get('item_id')
        for item_result in previous_results
        if item_result.get('status') != 'completed'
    ]
    failed_item_ids = [
        item_id
        for item_id in failed_item_ids
        if isinstance(item_id, int)
    ]
    if not failed_item_ids:
        raise ProviderWriteError(
            f'No failed {_plan_family(plan)} provider-write items remain to retry for this plan.'
        )

    selected_batches = [
        batch
        for batch in item_batches
        if batch['item_id'] in failed_item_ids
    ]
    if not selected_batches:
        raise ProviderWriteError(
            f'No failed {_plan_family(plan)} provider-write items remain to retry for this plan.'
        )

    context.update({
        'retry_mode': 'failed_only',
        'retry_source_execution_id': latest_execution.pk,
        'safe_retry': True,
        'automatic_failed_only': len(selected_batches) != len(item_batches),
        'failed_item_ids': failed_item_ids,
        'successful_item_count_previous': sum(
            1 for item_result in previous_results
            if item_result.get('status') == 'completed'
        ),
    })
    return selected_batches, context


def _build_apply_request_payload(
    *,
    family: str,
    delta: dict[str, list[dict]],
    item_batches: list[dict[str, object]],
    retry_context: dict[str, object],
) -> dict[str, object]:
    return {
        'schema_version': 1,
        'family': family.lower(),
        'family_display': family,
        'delta': delta,
        'item_batches': [
            {
                key: value
                for key, value in batch.items()
                if key != 'request_delta'
            } | {'request_delta': batch['request_delta']}
            for batch in item_batches
        ],
        'retry_mode': retry_context['retry_mode'],
        'retry_source_execution_id': retry_context['retry_source_execution_id'],
        'failed_item_ids': list(retry_context.get('failed_item_ids') or []),
        'automatic_failed_only': bool(retry_context.get('automatic_failed_only')),
    }


def _build_item_rollback_advice(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    family: str,
    request_delta: dict[str, list[dict]],
    successful: bool,
) -> dict[str, object]:
    inverse_delta = _invert_delta(request_delta)
    if not successful:
        return {
            'rollback_required': False,
            'summary': 'No rollback is recorded for this item because the provider did not confirm it as applied.',
            'inverse_delta': _empty_delta(),
            'inverse_provider_request': _serialize_provider_request_payload(
                provider_account,
                _empty_delta(),
                family=family,
            ),
        }
    return {
        'rollback_required': True,
        'summary': 'Rollback this item with the inverse provider delta, or apply the accumulated rollback bundle for the plan.',
        'inverse_delta': inverse_delta,
        'inverse_provider_request': _serialize_provider_request_payload(
            provider_account,
            inverse_delta,
            family=family,
        ),
    }


def _build_apply_item_result(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    family: str,
    batch: dict[str, object],
    provider_response: dict | None,
    error_text: str = '',
) -> dict[str, object]:
    successful = not error_text
    request_delta = batch['request_delta']
    return {
        'item_id': batch['item_id'],
        'item_name': batch['item_name'],
        'plan_semantic': batch['plan_semantic'],
        'provider_operation': batch['provider_operation'],
        'provider_payload': dict(batch.get('provider_payload') or {}),
        'before_state': dict(batch.get('before_state') or {}),
        'after_state': dict(batch.get('after_state') or {}),
        'state_diff': list(batch.get('state_diff') or []),
        'reason': batch.get('reason') or '',
        'status': 'failed' if error_text else 'completed',
        'request_delta': request_delta,
        'provider_request': _serialize_provider_request_payload(
            provider_account,
            request_delta,
            family=family,
        ),
        'provider_response': provider_response or {},
        'error': error_text,
        'rollback_advice': _build_item_rollback_advice(
            provider_account=provider_account,
            family=family,
            request_delta=request_delta,
            successful=successful,
        ),
    }


def _build_batch_summary(
    *,
    item_results: list[dict[str, object]],
    retry_context: dict[str, object],
) -> dict[str, object]:
    successful_item_ids = [
        item_result['item_id']
        for item_result in item_results
        if item_result['status'] == 'completed'
    ]
    failed_item_ids = [
        item_result['item_id']
        for item_result in item_results
        if item_result['status'] != 'completed'
    ]
    return {
        'requested_item_count': len(item_results),
        'successful_item_count': len(successful_item_ids),
        'failed_item_count': len(failed_item_ids),
        'successful_item_ids': successful_item_ids,
        'failed_item_ids': failed_item_ids,
        'partial_success': bool(successful_item_ids and failed_item_ids),
        'retry_mode': retry_context['retry_mode'],
        'retry_source_execution_id': retry_context['retry_source_execution_id'],
        'safe_retry': bool(failed_item_ids),
    }


def _build_rerun_advice(
    *,
    batch_summary: dict[str, object],
    retry_context: dict[str, object],
) -> dict[str, object]:
    failed_item_ids = list(batch_summary.get('failed_item_ids') or [])
    if failed_item_ids:
        if retry_context['retry_mode'] == 'failed_only':
            reason = 'Retry this plan again to rerun only the remaining failed provider-write items.'
        else:
            reason = 'Retry this plan again to rerun only the failed provider-write items while the plan payload is unchanged.'
    else:
        reason = 'No failed provider-write items remain to retry.'
    return {
        'can_retry_failed_items': bool(failed_item_ids),
        'failed_item_ids': failed_item_ids,
        'retry_mode': 'failed_only' if failed_item_ids else 'none',
        'reason': reason,
    }


def _invert_delta(delta: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {
        'added': list(delta.get('removed', [])),
        'removed': list(delta.get('added', [])),
    }


def _create_roa_rollback_bundle(
    plan: rpki_models.ROAChangePlan,
    delta: dict[str, list[dict]],
) -> rpki_models.ROAChangePlanRollbackBundle:
    rollback_delta = _invert_delta(delta)
    try:
        bundle = plan.rollback_bundle
    except rpki_models.ROAChangePlanRollbackBundle.DoesNotExist:
        bundle = rpki_models.ROAChangePlanRollbackBundle(
            name=f'{plan.name} Rollback',
            organization=plan.organization,
            source_plan=plan,
            tenant=plan.tenant,
            rollback_delta_json=_empty_delta(),
            item_count=0,
        )
    bundle.rollback_delta_json = _merge_delta(bundle.rollback_delta_json or _empty_delta(), rollback_delta)
    bundle.item_count = _delta_item_count(bundle.rollback_delta_json)
    bundle.full_clean(validate_unique=False)
    bundle.save()
    return bundle


def _create_aspa_rollback_bundle(
    plan: rpki_models.ASPAChangePlan,
    delta: dict[str, list[dict]],
) -> rpki_models.ASPAChangePlanRollbackBundle:
    rollback_delta = _invert_delta(delta)
    try:
        bundle = plan.rollback_bundle
    except rpki_models.ASPAChangePlanRollbackBundle.DoesNotExist:
        bundle = rpki_models.ASPAChangePlanRollbackBundle(
            name=f'{plan.name} Rollback',
            organization=plan.organization,
            source_plan=plan,
            tenant=plan.tenant,
            rollback_delta_json=_empty_delta(),
            item_count=0,
        )
    bundle.rollback_delta_json = _merge_delta(bundle.rollback_delta_json or _empty_delta(), rollback_delta)
    bundle.item_count = _delta_item_count(bundle.rollback_delta_json)
    bundle.full_clean(validate_unique=False)
    bundle.save()
    return bundle


def approve_rollback_bundle(
    bundle,
    *,
    approved_by: str = '',
    ticket_reference: str = '',
    change_reference: str = '',
    maintenance_window_start=None,
    maintenance_window_end=None,
    notes: str = '',
):
    if not bundle.can_approve:
        raise ProviderWriteError(f'Rollback bundle cannot be approved in status "{bundle.status}".')

    approved_at = timezone.now()
    bundle.status = rpki_models.RollbackBundleStatus.APPROVED
    bundle.approved_by = approved_by
    bundle.approved_at = approved_at
    bundle.ticket_reference = ticket_reference
    bundle.change_reference = change_reference
    bundle.maintenance_window_start = maintenance_window_start
    bundle.maintenance_window_end = maintenance_window_end
    bundle.notes = notes
    bundle.full_clean(validate_unique=False)
    bundle.save(update_fields=(
        'status',
        'approved_by',
        'approved_at',
        'ticket_reference',
        'change_reference',
        'maintenance_window_start',
        'maintenance_window_end',
        'notes',
    ))
    return bundle


def apply_roa_rollback_bundle(
    bundle: rpki_models.ROAChangePlanRollbackBundle,
    *,
    requested_by: str = '',
) -> rpki_models.ROAChangePlanRollbackBundle:
    if not bundle.can_apply:
        raise ProviderWriteError(f'Rollback bundle cannot be applied in status "{bundle.status}".')

    provider_account = bundle.source_plan.provider_account
    if provider_account is None or not provider_account.supports_roa_write:
        raise ProviderWriteError('Source plan has no provider account capable of ROA writes.')
    adapter = get_provider_adapter(provider_account)

    started_at = timezone.now()
    bundle.status = rpki_models.RollbackBundleStatus.APPLYING
    bundle.apply_started_at = started_at
    bundle.apply_requested_by = requested_by
    bundle.failed_at = None
    bundle.save(update_fields=('status', 'apply_started_at', 'apply_requested_by', 'failed_at'))

    try:
        provider_response = adapter.apply_roa_delta(provider_account, bundle.rollback_delta_json)
        applied_at = timezone.now()
        bundle.status = rpki_models.RollbackBundleStatus.APPLIED
        bundle.applied_at = applied_at
        bundle.apply_response_json = {
            'provider_response': provider_response,
            'roa_write_mode': provider_account.roa_write_mode,
            'source_plan_id': bundle.source_plan_id,
        }
        bundle.apply_error = ''
        try:
            followup_sync_run, followup_snapshot = sync_provider_account(
                provider_account,
                snapshot_name=f'{provider_account.name} Post-Rollback Snapshot {applied_at:%Y-%m-%d %H:%M:%S}',
            )
            bundle.apply_response_json['followup_sync'] = {
                'provider_sync_run_id': followup_sync_run.pk,
                'provider_snapshot_id': followup_snapshot.pk,
                'status': followup_sync_run.status,
            }
        except Exception as exc:
            bundle.apply_response_json['followup_sync'] = {
                'status': rpki_models.ValidationRunStatus.FAILED,
                'error': str(exc),
            }
        bundle.save(update_fields=('status', 'applied_at', 'apply_response_json', 'apply_error'))
    except Exception as exc:
        completed_at = timezone.now()
        bundle.status = rpki_models.RollbackBundleStatus.FAILED
        bundle.failed_at = completed_at
        bundle.apply_error = str(exc)
        bundle.apply_response_json = {'error': str(exc)}
        bundle.save(update_fields=('status', 'failed_at', 'apply_error', 'apply_response_json'))
        raise ProviderWriteError(str(exc)) from exc

    return bundle


def apply_aspa_rollback_bundle(
    bundle: rpki_models.ASPAChangePlanRollbackBundle,
    *,
    requested_by: str = '',
) -> rpki_models.ASPAChangePlanRollbackBundle:
    if not bundle.can_apply:
        raise ProviderWriteError(f'Rollback bundle cannot be applied in status "{bundle.status}".')

    provider_account = bundle.source_plan.provider_account
    if provider_account is None or not provider_account.supports_aspa_write:
        raise ProviderWriteError('Source plan has no provider account capable of ASPA writes.')
    adapter = get_provider_adapter(provider_account)

    started_at = timezone.now()
    bundle.status = rpki_models.RollbackBundleStatus.APPLYING
    bundle.apply_started_at = started_at
    bundle.apply_requested_by = requested_by
    bundle.failed_at = None
    bundle.save(update_fields=('status', 'apply_started_at', 'apply_requested_by', 'failed_at'))

    try:
        provider_response = adapter.apply_aspa_delta(provider_account, bundle.rollback_delta_json)
        applied_at = timezone.now()
        bundle.status = rpki_models.RollbackBundleStatus.APPLIED
        bundle.applied_at = applied_at
        bundle.apply_response_json = {
            'provider_response': provider_response,
            'aspa_write_mode': provider_account.aspa_write_mode,
            'source_plan_id': bundle.source_plan_id,
        }
        bundle.apply_error = ''
        try:
            followup_sync_run, followup_snapshot = sync_provider_account(
                provider_account,
                snapshot_name=f'{provider_account.name} Post-Rollback Snapshot {applied_at:%Y-%m-%d %H:%M:%S}',
            )
            bundle.apply_response_json['followup_sync'] = {
                'provider_sync_run_id': followup_sync_run.pk,
                'provider_snapshot_id': followup_snapshot.pk,
                'status': followup_sync_run.status,
            }
        except Exception as exc:
            bundle.apply_response_json['followup_sync'] = {
                'status': rpki_models.ValidationRunStatus.FAILED,
                'error': str(exc),
            }
        bundle.save(update_fields=('status', 'applied_at', 'apply_response_json', 'apply_error'))
    except Exception as exc:
        completed_at = timezone.now()
        bundle.status = rpki_models.RollbackBundleStatus.FAILED
        bundle.failed_at = completed_at
        bundle.apply_error = str(exc)
        bundle.apply_response_json = {'error': str(exc)}
        bundle.save(update_fields=('status', 'failed_at', 'apply_error', 'apply_response_json'))
        raise ProviderWriteError(str(exc)) from exc

    return bundle


def _get_plan_governance_metadata(plan) -> dict[str, str]:
    return plan.get_governance_metadata()


def _get_plan_delegated_scope_metadata(plan) -> dict:
    summary = dict(getattr(plan, 'summary_json', {}) or {})
    return {
        'delegated_scope_status': summary.get('delegated_scope_status', 'organization_only'),
        'delegated_entity_id': getattr(getattr(plan, 'delegated_entity', None), 'pk', None),
        'delegated_entity_name': getattr(getattr(plan, 'delegated_entity', None), 'name', ''),
        'managed_relationship_id': getattr(getattr(plan, 'managed_relationship', None), 'pk', None),
        'managed_relationship_name': getattr(getattr(plan, 'managed_relationship', None), 'name', ''),
        'delegated_scoped_item_count': summary.get('delegated_scoped_item_count', 0),
        'ownership_scope_conflict_customer_count': summary.get('ownership_scope_conflict_customer_count', 0),
        'ownership_scope_conflict_customer_asns': list(summary.get('ownership_scope_conflict_customer_asns') or []),
    }


def _build_approval_record_name(plan, approved_at) -> str:
    return f'{plan.name} Approval {approved_at:%Y-%m-%d %H:%M:%S}'


def _create_approval_record_for_plan(
    *,
    plan,
    approved_by: str,
    approved_at,
    ticket_reference: str,
    change_reference: str,
    maintenance_window_start,
    maintenance_window_end,
    approval_notes: str,
    simulation_review_json: dict | None = None,
) -> rpki_models.ApprovalRecord:
    payload = {
        'name': _build_approval_record_name(plan, approved_at),
        'organization': plan.organization,
        'tenant': plan.tenant,
        'disposition': rpki_models.ValidationDisposition.ACCEPTED,
        'recorded_by': approved_by,
        'recorded_at': approved_at,
        'ticket_reference': ticket_reference,
        'change_reference': change_reference,
        'maintenance_window_start': maintenance_window_start,
        'maintenance_window_end': maintenance_window_end,
        'notes': approval_notes,
        'simulation_review_json': simulation_review_json or {},
    }
    if isinstance(plan, rpki_models.ASPAChangePlan):
        payload['aspa_change_plan'] = plan
    else:
        payload['change_plan'] = plan
    approval_record = rpki_models.ApprovalRecord(**payload)
    approval_record.full_clean(validate_unique=False)
    approval_record.save()
    return approval_record


def _build_simulation_review_audit(
    *,
    simulation_run: rpki_models.ROAValidationSimulationRun,
    acknowledged_simulation_result_ids: list[int],
) -> dict:
    summary = dict(simulation_run.summary_json or {})
    acknowledged_id_set = set(acknowledged_simulation_result_ids or [])
    ack_required_results = []
    acknowledged_results = []
    for result in simulation_run.results.order_by('pk'):
        approval_impact = result.approval_impact or (result.details_json or {}).get('approval_impact')
        if approval_impact != rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED:
            continue
        ack_required_results.append(result)
        if result.pk in acknowledged_id_set:
            details = dict(result.details_json or {})
            acknowledged_results.append({
                'id': result.pk,
                'name': result.name,
                'change_plan_item_id': result.change_plan_item_id,
                'approval_impact': approval_impact,
                'scenario_type': result.scenario_type or details.get('scenario_type'),
                'operator_message': details.get('operator_message'),
                'why_it_matters': details.get('why_it_matters'),
                'operator_action': details.get('operator_action'),
            })

    ack_required_ids = [result.pk for result in ack_required_results]
    return {
        'simulation_run_id': simulation_run.pk,
        'simulation_plan_fingerprint': simulation_run.plan_fingerprint or summary.get('plan_fingerprint'),
        'overall_approval_posture': simulation_run.overall_approval_posture or summary.get('overall_approval_posture'),
        'is_current_for_plan': simulation_run.is_current_for_plan,
        'partially_constrained': simulation_run.partially_constrained,
        'approval_impact_counts': dict(summary.get('approval_impact_counts') or {}),
        'scenario_type_counts': dict(summary.get('scenario_type_counts') or {}),
        'acknowledgement_required_result_ids': ack_required_ids,
        'acknowledged_result_ids': sorted(acknowledged_id_set),
        'acknowledged_result_count': len(acknowledged_results),
        'acknowledged_results': acknowledged_results,
    }


def _create_lint_acknowledgements_for_plan(
    *,
    plan: rpki_models.ROAChangePlan,
    acknowledged_finding_ids: list[int],
    acknowledged_by: str,
    acknowledged_at,
    notes: str,
    ticket_reference: str,
    change_reference: str,
) -> list[rpki_models.ROALintAcknowledgement]:
    if not acknowledged_finding_ids:
        return []
    lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
    if lint_run is None:
        raise ProviderWriteError('This ROA change plan has no lint run to acknowledge findings against.')

    findings = list(lint_run.findings.filter(pk__in=acknowledged_finding_ids))
    if len(findings) != len(set(acknowledged_finding_ids)):
        raise ProviderWriteError('One or more acknowledged lint findings do not belong to the latest lint run for this change plan.')

    acknowledgements = []
    for finding in findings:
        if finding.details_json.get('suppressed'):
            raise ProviderWriteError(f'Lint finding {finding.pk} is suppressed and does not need acknowledgement.')
        if finding.details_json.get('approval_impact') != 'acknowledgement_required':
            raise ProviderWriteError(
                f'Lint finding {finding.pk} is not acknowledgement-required and cannot be acknowledged here.'
            )
        acknowledgement, _ = rpki_models.ROALintAcknowledgement.objects.get_or_create(
            change_plan=plan,
            finding=finding,
            defaults={
                'name': f'Lint Ack {finding.pk} for Plan {plan.pk}',
                'organization': plan.organization,
                'tenant': plan.tenant,
                'lint_run': lint_run,
                'acknowledged_by': acknowledged_by,
                'acknowledged_at': acknowledged_at,
                'ticket_reference': ticket_reference,
                'change_reference': change_reference,
                'notes': notes,
            },
        )
        acknowledgements.append(acknowledgement)
    return acknowledgements


def acknowledge_roa_lint_findings(
    plan: rpki_models.ROAChangePlan | int,
    *,
    acknowledged_finding_ids: list[int] | None = None,
    previously_acknowledged_finding_ids: list[int] | None = None,
    acknowledged_by: str = '',
    ticket_reference: str = '',
    change_reference: str = '',
    notes: str = '',
) -> list[rpki_models.ROALintAcknowledgement]:
    plan = _normalize_plan(plan)
    _require_approvable(plan)
    acknowledged_finding_ids = list(acknowledged_finding_ids or [])
    acknowledged_finding_ids.extend(previously_acknowledged_finding_ids or [])
    if not acknowledged_finding_ids:
        raise ProviderWriteError('Select at least one current blocking lint finding to acknowledge.')

    acknowledged_at = timezone.now()
    with transaction.atomic():
        acknowledgements = _create_lint_acknowledgements_for_plan(
            plan=plan,
            acknowledged_finding_ids=acknowledged_finding_ids,
            acknowledged_by=acknowledged_by,
            acknowledged_at=acknowledged_at,
            notes=notes,
            ticket_reference=ticket_reference,
            change_reference=change_reference,
        )
        refresh_roa_change_plan_lint_posture(plan)
    return acknowledgements


def approve_roa_change_plan(
    plan: rpki_models.ROAChangePlan | int,
    *,
    approved_by: str = '',
    requires_secondary_approval: bool | None = None,
    ticket_reference: str = '',
    change_reference: str = '',
    maintenance_window_start=None,
    maintenance_window_end=None,
    approval_notes: str = '',
    acknowledged_finding_ids: list[int] | None = None,
    previously_acknowledged_finding_ids: list[int] | None = None,
    acknowledged_simulation_result_ids: list[int] | None = None,
    lint_acknowledgement_notes: str = '',
) -> rpki_models.ROAChangePlan:
    plan = _normalize_plan(plan)
    _require_approvable(plan)
    acknowledged_finding_ids = list(acknowledged_finding_ids or [])
    acknowledged_finding_ids.extend(previously_acknowledged_finding_ids or [])
    acknowledged_simulation_result_ids = acknowledged_simulation_result_ids or []
    posture = build_roa_change_plan_lint_posture(
        plan,
        acknowledged_finding_ids=acknowledged_finding_ids,
    )
    if not posture['has_lint_run']:
        raise ProviderWriteError('This ROA change plan cannot be approved until a lint run has been recorded.')
    if posture['unresolved_blocking_finding_count'] > 0:
        raise ProviderWriteError(
            f'This ROA change plan has {posture["unresolved_blocking_finding_count"]} unresolved blocking lint finding(s).'
        )
    if posture['unresolved_acknowledgement_required_finding_count'] > 0:
        raise ProviderWriteError(
            'This ROA change plan has acknowledgement-required lint findings that must be acknowledged before approval.'
        )
    if posture['previously_acknowledged_finding_count'] > 0:
        raise ProviderWriteError(
            'This ROA change plan has previously acknowledged lint findings that must be re-confirmed before approval.'
        )
    try:
        simulation_run = require_roa_change_plan_simulation_approvable(
            plan,
            acknowledged_simulation_result_ids=acknowledged_simulation_result_ids,
        )
    except ValueError as exc:
        raise ProviderWriteError(str(exc)) from exc

    approved_at = timezone.now()
    with transaction.atomic():
        if requires_secondary_approval is not None:
            plan.requires_secondary_approval = requires_secondary_approval
        simulation_review_json = _build_simulation_review_audit(
            simulation_run=simulation_run,
            acknowledged_simulation_result_ids=acknowledged_simulation_result_ids,
        )
        plan.status = (
            rpki_models.ROAChangePlanStatus.AWAITING_2ND
            if plan.requires_secondary_approval
            else rpki_models.ROAChangePlanStatus.APPROVED
        )
        plan.ticket_reference = ticket_reference
        plan.change_reference = change_reference
        plan.maintenance_window_start = maintenance_window_start
        plan.maintenance_window_end = maintenance_window_end
        plan.approved_at = approved_at
        plan.approved_by = approved_by
        plan.summary_json['approved_simulation_run_id'] = simulation_run.pk
        plan.summary_json['approved_simulation_plan_fingerprint'] = (
            simulation_run.plan_fingerprint or (simulation_run.summary_json or {}).get('plan_fingerprint')
        )
        plan.summary_json['approved_simulation_overall_approval_posture'] = (
            simulation_run.overall_approval_posture or (simulation_run.summary_json or {}).get('overall_approval_posture')
        )
        plan.summary_json['approved_simulation_result_ids'] = acknowledged_simulation_result_ids
        plan.summary_json['approved_simulation_review'] = simulation_review_json
        plan.full_clean(validate_unique=False)
        plan.save(update_fields=(
            'status',
            'requires_secondary_approval',
            'ticket_reference',
            'change_reference',
            'maintenance_window_start',
            'maintenance_window_end',
            'approved_at',
            'approved_by',
            'summary_json',
        ))
        _create_approval_record_for_plan(
            plan=plan,
            approved_by=approved_by,
            approved_at=approved_at,
            ticket_reference=ticket_reference,
            change_reference=change_reference,
            maintenance_window_start=maintenance_window_start,
            maintenance_window_end=maintenance_window_end,
            approval_notes=approval_notes,
            simulation_review_json=simulation_review_json,
        )
        _create_lint_acknowledgements_for_plan(
            plan=plan,
            acknowledged_finding_ids=acknowledged_finding_ids,
            acknowledged_by=approved_by,
            acknowledged_at=approved_at,
            notes=lint_acknowledgement_notes,
            ticket_reference=ticket_reference,
            change_reference=change_reference,
        )
        refresh_roa_change_plan_lint_posture(plan)
    return plan


def approve_aspa_change_plan(
    plan: rpki_models.ASPAChangePlan | int,
    *,
    approved_by: str = '',
    requires_secondary_approval: bool | None = None,
    ticket_reference: str = '',
    change_reference: str = '',
    maintenance_window_start=None,
    maintenance_window_end=None,
    approval_notes: str = '',
) -> rpki_models.ASPAChangePlan:
    plan = _normalize_aspa_plan(plan)
    _require_aspa_approvable(plan)

    approved_at = timezone.now()
    with transaction.atomic():
        if requires_secondary_approval is not None:
            plan.requires_secondary_approval = requires_secondary_approval
        plan.status = (
            rpki_models.ASPAChangePlanStatus.AWAITING_2ND
            if plan.requires_secondary_approval
            else rpki_models.ASPAChangePlanStatus.APPROVED
        )
        plan.ticket_reference = ticket_reference
        plan.change_reference = change_reference
        plan.maintenance_window_start = maintenance_window_start
        plan.maintenance_window_end = maintenance_window_end
        plan.approved_at = approved_at
        plan.approved_by = approved_by
        plan.full_clean(validate_unique=False)
        plan.save(update_fields=(
            'status',
            'requires_secondary_approval',
            'ticket_reference',
            'change_reference',
            'maintenance_window_start',
            'maintenance_window_end',
            'approved_at',
            'approved_by',
        ))
        _create_approval_record_for_plan(
            plan=plan,
            approved_by=approved_by,
            approved_at=approved_at,
            ticket_reference=ticket_reference,
            change_reference=change_reference,
            maintenance_window_start=maintenance_window_start,
            maintenance_window_end=maintenance_window_end,
            approval_notes=approval_notes,
        )
    return plan


def approve_roa_change_plan_secondary(
    plan: rpki_models.ROAChangePlan | int,
    *,
    secondary_approved_by: str = '',
    approval_notes: str = '',
) -> rpki_models.ROAChangePlan:
    plan = _normalize_plan(plan)
    if plan.status != rpki_models.ROAChangePlanStatus.AWAITING_2ND:
        raise ProviderWriteError(
            f'Plan is not awaiting secondary approval (current status: {plan.status}).'
        )
    if (
        secondary_approved_by
        and plan.approved_by
        and secondary_approved_by.strip().lower() == plan.approved_by.strip().lower()
    ):
        raise ProviderWriteError(
            'The secondary approver must be a different person than the primary approver '
            f'("{plan.approved_by}").'
        )

    secondary_approved_at = timezone.now()
    with transaction.atomic():
        plan.status = rpki_models.ROAChangePlanStatus.APPROVED
        plan.secondary_approved_by = secondary_approved_by
        plan.secondary_approved_at = secondary_approved_at
        plan.save(update_fields=('status', 'secondary_approved_by', 'secondary_approved_at'))
        _create_approval_record_for_plan(
            plan=plan,
            approved_by=secondary_approved_by,
            approved_at=secondary_approved_at,
            ticket_reference=plan.ticket_reference,
            change_reference=plan.change_reference,
            maintenance_window_start=plan.maintenance_window_start,
            maintenance_window_end=plan.maintenance_window_end,
            approval_notes=f'[Secondary approval] {approval_notes}'.strip(),
        )
    return plan


def approve_aspa_change_plan_secondary(
    plan: rpki_models.ASPAChangePlan | int,
    *,
    secondary_approved_by: str = '',
    approval_notes: str = '',
) -> rpki_models.ASPAChangePlan:
    plan = _normalize_aspa_plan(plan)
    if plan.status != rpki_models.ASPAChangePlanStatus.AWAITING_2ND:
        raise ProviderWriteError(
            f'Plan is not awaiting secondary approval (current status: {plan.status}).'
        )
    if (
        secondary_approved_by
        and plan.approved_by
        and secondary_approved_by.strip().lower() == plan.approved_by.strip().lower()
    ):
        raise ProviderWriteError(
            'The secondary approver must be a different person than the primary approver '
            f'("{plan.approved_by}").'
        )

    secondary_approved_at = timezone.now()
    with transaction.atomic():
        plan.status = rpki_models.ASPAChangePlanStatus.APPROVED
        plan.secondary_approved_by = secondary_approved_by
        plan.secondary_approved_at = secondary_approved_at
        plan.save(update_fields=('status', 'secondary_approved_by', 'secondary_approved_at'))
        _create_approval_record_for_plan(
            plan=plan,
            approved_by=secondary_approved_by,
            approved_at=secondary_approved_at,
            ticket_reference=plan.ticket_reference,
            change_reference=plan.change_reference,
            maintenance_window_start=plan.maintenance_window_start,
            maintenance_window_end=plan.maintenance_window_end,
            approval_notes=f'[Secondary approval] {approval_notes}'.strip(),
        )
    return plan


def _create_execution(
    *,
    plan,
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
    payload = {
        'name': f'{plan.name} {execution_mode.title()} {started_at:%Y-%m-%d %H:%M:%S}',
        'organization': plan.organization,
        'provider_account': provider_account,
        'provider_snapshot': plan.provider_snapshot,
        'tenant': plan.tenant,
        'execution_mode': execution_mode,
        'status': status,
        'requested_by': requested_by,
        'started_at': started_at,
        'completed_at': completed_at,
        'item_count': item_count,
        'request_payload_json': request_payload_json or {},
        'response_payload_json': response_payload_json or {},
        'error': error,
        'followup_sync_run': followup_sync_run,
        'followup_provider_snapshot': followup_provider_snapshot,
    }
    if isinstance(plan, rpki_models.ASPAChangePlan):
        payload['aspa_change_plan'] = plan
    else:
        payload['change_plan'] = plan
    return rpki_models.ProviderWriteExecution.objects.create(**payload)


def preview_roa_change_plan_provider_write(
    plan: rpki_models.ROAChangePlan | int,
    *,
    requested_by: str = '',
) -> tuple[rpki_models.ProviderWriteExecution, dict[str, list[dict]]]:
    plan = _normalize_plan(plan)
    provider_account = _require_previewable(plan)
    delta = build_roa_change_plan_delta(plan)
    preview_report = build_roa_change_plan_preview_report(plan)
    started_at = timezone.now()
    execution = _create_execution(
        plan=plan,
        provider_account=provider_account,
        execution_mode=rpki_models.ProviderWriteExecutionMode.PREVIEW,
        requested_by=requested_by,
        status=rpki_models.ProviderWriteExecutionStatus.COMPLETED,
        started_at=started_at,
        completed_at=started_at,
        item_count=sum(len(values) for values in delta.values()),
        request_payload_json=delta,
        response_payload_json={
            'preview_only': True,
            'roa_write_mode': provider_account.roa_write_mode,
            'governance': _get_plan_governance_metadata(plan),
            'provider_request': preview_report['provider_request'],
            'preview_report': preview_report,
        },
    )
    return execution, delta


def preview_aspa_change_plan_provider_write(
    plan: rpki_models.ASPAChangePlan | int,
    *,
    requested_by: str = '',
) -> tuple[rpki_models.ProviderWriteExecution, dict[str, list[dict]]]:
    plan = _normalize_aspa_plan(plan)
    provider_account = _require_aspa_previewable(plan)
    delta = build_aspa_change_plan_delta(plan)
    preview_report = build_aspa_change_plan_preview_report(plan)
    started_at = timezone.now()
    execution = _create_execution(
        plan=plan,
        provider_account=provider_account,
        execution_mode=rpki_models.ProviderWriteExecutionMode.PREVIEW,
        requested_by=requested_by,
        status=rpki_models.ProviderWriteExecutionStatus.COMPLETED,
        started_at=started_at,
        completed_at=started_at,
        item_count=sum(len(values) for values in delta.values()),
        request_payload_json=delta,
        response_payload_json={
            'preview_only': True,
            'aspa_write_mode': provider_account.aspa_write_mode,
            'governance': _get_plan_governance_metadata(plan),
            'delegated_scope': _get_plan_delegated_scope_metadata(plan),
            'provider_request': preview_report['provider_request'],
            'preview_report': preview_report,
        },
    )
    return execution, delta


def _submit_krill_json_delta(
    *,
    provider_account: rpki_models.RpkiProviderAccount,
    url: str,
    delta: dict,
) -> dict:
    request = Request(
        url,
        data=json.dumps(delta).encode('utf-8'),
        headers={
            'Accept': 'application/json',
            'Authorization': f'Bearer {provider_account.api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    urlopen_kwargs = {'timeout': 30}
    ssl_context = krill_ssl_context(provider_account)
    if ssl_context is not None:
        urlopen_kwargs['context'] = ssl_context

    emit_structured_log(
        'provider_write.krill.submit.start',
        subsystem='provider_write',
        debug=True,
        provider_account_id=provider_account.pk,
        provider_type=provider_account.provider_type,
        method=request.get_method(),
        url=url,
        headers=dict(request.header_items()),
        delta=delta,
        tls_verification='disabled' if ssl_context is not None else 'enabled',
    )
    try:
        with urlopen(request, **urlopen_kwargs) as response:
            raw_body = response.read().decode('utf-8').strip()
    except Exception as exc:
        emit_structured_log(
            'provider_write.krill.submit.error',
            subsystem='provider_write',
            level='warning',
            provider_account_id=provider_account.pk,
            provider_type=provider_account.provider_type,
            method=request.get_method(),
            url=url,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise

    if not raw_body:
        emit_structured_log(
            'provider_write.krill.submit.success',
            subsystem='provider_write',
            debug=True,
            provider_account_id=provider_account.pk,
            provider_type=provider_account.provider_type,
            method=request.get_method(),
            url=url,
            response_body={},
        )
        return {}

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        emit_structured_log(
            'provider_write.krill.submit.success',
            subsystem='provider_write',
            debug=True,
            provider_account_id=provider_account.pk,
            provider_type=provider_account.provider_type,
            method=request.get_method(),
            url=url,
            response_body=raw_body,
        )
        return {'raw': raw_body}

    emit_structured_log(
        'provider_write.krill.submit.success',
        subsystem='provider_write',
        debug=True,
        provider_account_id=provider_account.pk,
        provider_type=provider_account.provider_type,
        method=request.get_method(),
        url=url,
        response_body=payload,
    )
    if isinstance(payload, dict):
        return payload
    return {'raw': payload}


def _submit_krill_route_delta(
    provider_account: rpki_models.RpkiProviderAccount,
    delta: dict[str, list[dict]],
) -> dict:
    return _submit_krill_json_delta(
        provider_account=provider_account,
        url=krill_routes_url(provider_account),
        delta=delta,
    )


def _serialize_krill_aspa_delta(delta: dict[str, list[dict]]) -> dict[str, list[dict]]:
    def _serialize_entries(entries: list[dict]) -> list[dict]:
        serialized = []
        for entry in entries:
            customer_asn = entry.get('customer_asn')
            provider_asns = list(entry.get('provider_asns') or [])
            serialized.append(
                {
                    'customer': f'AS{customer_asn}' if customer_asn is not None else '',
                    'providers': [f'AS{provider_asn}' for provider_asn in provider_asns],
                }
            )
        return serialized

    return {
        'add': _serialize_entries(delta.get('added', [])),
        'remove': _serialize_entries(delta.get('removed', [])),
    }


def _submit_krill_aspa_delta(
    provider_account: rpki_models.RpkiProviderAccount,
    delta: dict[str, list[dict]],
) -> dict:
    return _submit_krill_json_delta(
        provider_account=provider_account,
        url=krill_aspas_url(provider_account),
        delta=_serialize_krill_aspa_delta(delta),
    )


def apply_roa_change_plan_provider_write(
    plan: rpki_models.ROAChangePlan | int,
    *,
    requested_by: str = '',
) -> tuple[rpki_models.ProviderWriteExecution, dict[str, list[dict]]]:
    plan = _normalize_plan(plan)
    provider_account = _require_applicable(plan)
    adapter = get_provider_adapter(provider_account)
    all_item_batches = _build_plan_item_batches(plan)
    item_batches, retry_context = _resolve_apply_item_batches(plan, all_item_batches)
    delta = _empty_delta()
    for batch in item_batches:
        delta = _merge_delta(delta, batch['request_delta'])
    started_at = timezone.now()
    plan.status = rpki_models.ROAChangePlanStatus.APPLYING
    plan.apply_started_at = started_at
    plan.apply_requested_by = requested_by
    plan.failed_at = None
    plan.save(update_fields=('status', 'apply_started_at', 'apply_requested_by', 'failed_at'))
    request_payload_json = _build_apply_request_payload(
        family='ROA',
        delta=delta,
        item_batches=item_batches,
        retry_context=retry_context,
    )
    execution = _create_execution(
        plan=plan,
        provider_account=provider_account,
        execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
        requested_by=requested_by,
        status=rpki_models.ProviderWriteExecutionStatus.RUNNING,
        started_at=started_at,
        item_count=len(item_batches),
        request_payload_json=request_payload_json,
    )

    try:
        response_payload_json = {
            'schema_version': 1,
            'family': 'roa',
            'roa_write_mode': provider_account.roa_write_mode,
            'governance': _get_plan_governance_metadata(plan),
            'delta': delta,
            'item_results': [],
            'provider_response': {},
            'provider_responses': [],
        }
        successful_delta = _empty_delta()
        encountered_errors: list[str] = []
        for batch in item_batches:
            try:
                provider_response = adapter.apply_roa_delta(provider_account, batch['request_delta'])
                successful_delta = _merge_delta(successful_delta, batch['request_delta'])
                response_payload_json['item_results'].append(
                    _build_apply_item_result(
                        provider_account=provider_account,
                        family='ROA',
                        batch=batch,
                        provider_response=provider_response,
                    )
                )
                response_payload_json['provider_responses'].append(provider_response)
                response_payload_json['provider_response'] = provider_response
            except Exception as exc:
                encountered_errors.append(str(exc))
                response_payload_json['item_results'].append(
                    _build_apply_item_result(
                        provider_account=provider_account,
                        family='ROA',
                        batch=batch,
                        provider_response=None,
                        error_text=str(exc),
                    )
                )

        batch_summary = _build_batch_summary(
            item_results=response_payload_json['item_results'],
            retry_context=retry_context,
        )
        response_payload_json['batch_summary'] = batch_summary
        response_payload_json['rerun_advice'] = _build_rerun_advice(
            batch_summary=batch_summary,
            retry_context=retry_context,
        )

        successful_item_count = batch_summary['successful_item_count']
        failed_item_count = batch_summary['failed_item_count']
        if successful_item_count:
            rollback_bundle = _create_roa_rollback_bundle(plan, successful_delta)
            response_payload_json['rollback_guidance'] = {
                'rollback_bundle_id': rollback_bundle.pk,
                'rollback_bundle_name': rollback_bundle.name,
                'rollback_bundle_url': rollback_bundle.get_absolute_url(),
                'successful_delta': successful_delta,
                'inverse_delta': _invert_delta(successful_delta),
                'successful_item_ids': batch_summary['successful_item_ids'],
            }
        else:
            rollback_bundle = None
            response_payload_json['rollback_guidance'] = {
                'rollback_bundle_id': None,
                'rollback_bundle_name': '',
                'rollback_bundle_url': '',
                'successful_delta': _empty_delta(),
                'inverse_delta': _empty_delta(),
                'successful_item_ids': [],
            }

        followup_sync_run = None
        followup_snapshot = None
        followup_error = ''
        if successful_item_count:
            applied_at = timezone.now()
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
            except Exception as exc:
                followup_error = str(exc)
                response_payload_json['followup_sync'] = {
                    'status': rpki_models.ValidationRunStatus.FAILED,
                    'error': followup_error,
                }
        else:
            applied_at = None
            response_payload_json['followup_sync'] = {
                'status': 'not_run',
                'reason': 'No provider changes were confirmed as applied.',
            }

        if failed_item_count:
            completed_at = timezone.now()
            plan.status = rpki_models.ROAChangePlanStatus.FAILED
            plan.failed_at = completed_at
            plan.save(update_fields=('status', 'failed_at'))
            execution.status = (
                rpki_models.ProviderWriteExecutionStatus.PARTIAL
                if successful_item_count
                else rpki_models.ProviderWriteExecutionStatus.FAILED
            )
            execution.error = '; '.join(encountered_errors)[:4000]
        else:
            plan.status = rpki_models.ROAChangePlanStatus.APPLIED
            plan.applied_at = applied_at
            plan.failed_at = None
            plan.save(update_fields=('status', 'applied_at', 'failed_at'))
            if followup_error:
                execution.status = rpki_models.ProviderWriteExecutionStatus.FAILED
                execution.error = followup_error
            else:
                execution.status = rpki_models.ProviderWriteExecutionStatus.COMPLETED
                execution.error = ''

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
        execution.status = rpki_models.ProviderWriteExecutionStatus.FAILED
        execution.completed_at = completed_at
        execution.error = str(exc)
        execution.response_payload_json = {
            'roa_write_mode': provider_account.roa_write_mode,
            'governance': _get_plan_governance_metadata(plan),
        }
        execution.save(update_fields=('status', 'completed_at', 'error', 'response_payload_json'))
        raise ProviderWriteError(str(exc)) from exc


def apply_aspa_change_plan_provider_write(
    plan: rpki_models.ASPAChangePlan | int,
    *,
    requested_by: str = '',
) -> tuple[rpki_models.ProviderWriteExecution, dict[str, list[dict]]]:
    plan = _normalize_aspa_plan(plan)
    provider_account = _require_aspa_applicable(plan)
    adapter = get_provider_adapter(provider_account)
    all_item_batches = _build_plan_item_batches(plan)
    item_batches, retry_context = _resolve_apply_item_batches(plan, all_item_batches)
    delta = _empty_delta()
    for batch in item_batches:
        delta = _merge_delta(delta, batch['request_delta'])
    started_at = timezone.now()
    plan.status = rpki_models.ASPAChangePlanStatus.APPLYING
    plan.apply_started_at = started_at
    plan.apply_requested_by = requested_by
    plan.failed_at = None
    plan.save(update_fields=('status', 'apply_started_at', 'apply_requested_by', 'failed_at'))
    request_payload_json = _build_apply_request_payload(
        family='ASPA',
        delta=delta,
        item_batches=item_batches,
        retry_context=retry_context,
    )
    execution = _create_execution(
        plan=plan,
        provider_account=provider_account,
        execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
        requested_by=requested_by,
        status=rpki_models.ProviderWriteExecutionStatus.RUNNING,
        started_at=started_at,
        item_count=len(item_batches),
        request_payload_json=request_payload_json,
    )

    try:
        response_payload_json = {
            'schema_version': 1,
            'family': 'aspa',
            'aspa_write_mode': provider_account.aspa_write_mode,
            'governance': _get_plan_governance_metadata(plan),
            'delegated_scope': _get_plan_delegated_scope_metadata(plan),
            'delta': delta,
            'item_results': [],
            'provider_response': {},
            'provider_responses': [],
            'delta_summary': {
                'customer_count': len(delta.get('added', [])) + len(delta.get('removed', [])),
                'create_count': len(delta.get('added', [])),
                'withdraw_count': len(delta.get('removed', [])),
                'provider_add_count': sum(len(entry.get('provider_asns') or []) for entry in delta.get('added', [])),
                'provider_remove_count': sum(len(entry.get('provider_asns') or []) for entry in delta.get('removed', [])),
            },
        }
        successful_delta = _empty_delta()
        encountered_errors: list[str] = []
        for batch in item_batches:
            try:
                provider_response = adapter.apply_aspa_delta(provider_account, batch['request_delta'])
                successful_delta = _merge_delta(successful_delta, batch['request_delta'])
                response_payload_json['item_results'].append(
                    _build_apply_item_result(
                        provider_account=provider_account,
                        family='ASPA',
                        batch=batch,
                        provider_response=provider_response,
                    )
                )
                response_payload_json['provider_responses'].append(provider_response)
                response_payload_json['provider_response'] = provider_response
            except Exception as exc:
                encountered_errors.append(str(exc))
                response_payload_json['item_results'].append(
                    _build_apply_item_result(
                        provider_account=provider_account,
                        family='ASPA',
                        batch=batch,
                        provider_response=None,
                        error_text=str(exc),
                    )
                )

        batch_summary = _build_batch_summary(
            item_results=response_payload_json['item_results'],
            retry_context=retry_context,
        )
        response_payload_json['batch_summary'] = batch_summary
        response_payload_json['rerun_advice'] = _build_rerun_advice(
            batch_summary=batch_summary,
            retry_context=retry_context,
        )

        successful_item_count = batch_summary['successful_item_count']
        failed_item_count = batch_summary['failed_item_count']
        if successful_item_count:
            rollback_bundle = _create_aspa_rollback_bundle(plan, successful_delta)
            response_payload_json['rollback_guidance'] = {
                'rollback_bundle_id': rollback_bundle.pk,
                'rollback_bundle_name': rollback_bundle.name,
                'rollback_bundle_url': rollback_bundle.get_absolute_url(),
                'successful_delta': successful_delta,
                'inverse_delta': _invert_delta(successful_delta),
                'successful_item_ids': batch_summary['successful_item_ids'],
            }
        else:
            rollback_bundle = None
            response_payload_json['rollback_guidance'] = {
                'rollback_bundle_id': None,
                'rollback_bundle_name': '',
                'rollback_bundle_url': '',
                'successful_delta': _empty_delta(),
                'inverse_delta': _empty_delta(),
                'successful_item_ids': [],
            }

        followup_sync_run = None
        followup_snapshot = None
        followup_error = ''
        if successful_item_count:
            applied_at = timezone.now()
            try:
                followup_sync_run, followup_snapshot = sync_provider_account(
                    provider_account,
                    snapshot_name=(
                        f'{provider_account.name} Post-ASPA-Apply Snapshot {applied_at:%Y-%m-%d %H:%M:%S}'
                    ),
                )
                response_payload_json['followup_sync'] = {
                    'provider_sync_run_id': followup_sync_run.pk,
                    'provider_snapshot_id': followup_snapshot.pk,
                    'status': followup_sync_run.status,
                }
            except Exception as exc:
                followup_error = str(exc)
                response_payload_json['followup_sync'] = {
                    'status': rpki_models.ValidationRunStatus.FAILED,
                    'error': followup_error,
                }
        else:
            applied_at = None
            response_payload_json['followup_sync'] = {
                'status': 'not_run',
                'reason': 'No provider changes were confirmed as applied.',
            }

        if failed_item_count:
            completed_at = timezone.now()
            plan.status = rpki_models.ASPAChangePlanStatus.FAILED
            plan.failed_at = completed_at
            plan.save(update_fields=('status', 'failed_at'))
            execution.status = (
                rpki_models.ProviderWriteExecutionStatus.PARTIAL
                if successful_item_count
                else rpki_models.ProviderWriteExecutionStatus.FAILED
            )
            execution.error = '; '.join(encountered_errors)[:4000]
        else:
            plan.status = rpki_models.ASPAChangePlanStatus.APPLIED
            plan.applied_at = applied_at
            plan.failed_at = None
            plan.save(update_fields=('status', 'applied_at', 'failed_at'))
            if followup_error:
                execution.status = rpki_models.ProviderWriteExecutionStatus.FAILED
                execution.error = followup_error
            else:
                execution.status = rpki_models.ProviderWriteExecutionStatus.COMPLETED
                execution.error = ''

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
        plan.status = rpki_models.ASPAChangePlanStatus.FAILED
        plan.failed_at = completed_at
        plan.save(update_fields=('status', 'failed_at'))
        execution.status = rpki_models.ProviderWriteExecutionStatus.FAILED
        execution.completed_at = completed_at
        execution.error = str(exc)
        execution.response_payload_json = {
            'aspa_write_mode': provider_account.aspa_write_mode,
            'governance': _get_plan_governance_metadata(plan),
            'delegated_scope': _get_plan_delegated_scope_metadata(plan),
        }
        execution.save(update_fields=('status', 'completed_at', 'error', 'response_payload_json'))
        raise ProviderWriteError(str(exc)) from exc
