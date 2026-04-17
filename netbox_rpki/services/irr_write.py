from __future__ import annotations

import base64
import hashlib
import json
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.structured_logging import emit_structured_log


class IrrChangePlanError(ValueError):
    pass


class IrrWriteExecutionError(ValueError):
    pass


ACTIONABLE_RESULT_TYPES = {
    rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
    rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE,
    rpki_models.IrrCoordinationResultType.SOURCE_CONFLICT,
}

REVIEW_ONLY_RESULT_TYPES = {
    rpki_models.IrrCoordinationResultType.UNSUPPORTED_WRITE,
    rpki_models.IrrCoordinationResultType.AMBIGUOUS_LINKAGE,
    rpki_models.IrrCoordinationResultType.POLICY_CONTEXT_GAP,
}


def describe_irr_coordination_result_remediation(
    result: rpki_models.IrrCoordinationResult,
    *,
    source: rpki_models.IrrSource | None = None,
) -> dict[str, str]:
    target_source = source or result.source
    action = (
        _derive_action(result=result, source=target_source)
        if target_source is not None
        else rpki_models.IrrChangePlanAction.NOOP
    )
    action_display = (
        rpki_models.IrrChangePlanAction(action).label
        if action in rpki_models.IrrChangePlanAction.values
        else 'No-op'
    )
    return {
        'action': action,
        'action_display': action_display,
        'reason': _build_item_reason(result=result, action=action),
    }


def create_irr_change_plans(
    coordination_run: rpki_models.IrrCoordinationRun,
    *,
    sources: list[rpki_models.IrrSource] | None = None,
) -> list[rpki_models.IrrChangePlan]:
    if coordination_run.status != rpki_models.IrrCoordinationRunStatus.COMPLETED:
        raise IrrChangePlanError('IRR change plans can only be created from completed coordination runs.')

    selected_sources = list(sources) if sources is not None else list(
        coordination_run.compared_sources.order_by('name', 'pk')
    )
    if not selected_sources:
        selected_sources = list(
            rpki_models.IrrSource.objects.filter(
                coordination_results__coordination_run=coordination_run,
            ).distinct().order_by('name', 'pk')
        )
    if not selected_sources:
        raise IrrChangePlanError('No IRR sources are available on the coordination run for draft generation.')

    plans: list[rpki_models.IrrChangePlan] = []
    with transaction.atomic():
        for source in selected_sources:
            plan = _build_change_plan_for_source(coordination_run=coordination_run, source=source)
            if plan is not None:
                plans.append(plan)

        summary_json = dict(coordination_run.summary_json or {})
        summary_json['latest_plan_ids'] = [plan.pk for plan in plans]
        coordination_run.summary_json = summary_json
        coordination_run.save(update_fields=('summary_json',))
    return plans


def _build_change_plan_for_source(
    *,
    coordination_run: rpki_models.IrrCoordinationRun,
    source: rpki_models.IrrSource,
) -> rpki_models.IrrChangePlan | None:
    source_results = list(
        coordination_run.results.filter(
            source=source,
        ).select_related(
            'snapshot',
            'roa_intent',
            'imported_route_object',
            'imported_aut_num',
            'imported_maintainer',
        ).order_by(
            'coordination_family',
            'stable_object_key',
            'name',
            'pk',
        )
    )
    relevant_results = [
        result for result in source_results
        if result.result_type in ACTIONABLE_RESULT_TYPES | REVIEW_ONLY_RESULT_TYPES
    ]
    if not relevant_results:
        return None

    now = timezone.now()
    snapshot = next((result.snapshot for result in relevant_results if result.snapshot_id is not None), None)
    plan = rpki_models.IrrChangePlan.objects.create(
        name=f'{coordination_run.name} {source.name} Draft {now:%Y-%m-%d %H:%M:%S}',
        organization=coordination_run.organization,
        coordination_run=coordination_run,
        source=source,
        snapshot=snapshot,
        tenant=coordination_run.tenant,
        status=rpki_models.IrrChangePlanStatus.DRAFT,
        write_support_mode=source.write_support_mode,
    )

    item_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    capability_warnings: list[str] = []

    if source.write_support_mode == rpki_models.IrrWriteSupportMode.UNSUPPORTED:
        capability_warnings.append('Target source does not currently support automated IRR preview or apply.')
    elif source.write_support_mode == rpki_models.IrrWriteSupportMode.PREVIEW_ONLY:
        capability_warnings.append('Target source supports preview only; apply will remain blocked until a write adapter is available.')
    if source.sync_health == rpki_models.IrrSyncHealth.STALE:
        capability_warnings.append('Target source snapshot is stale; review imported state before execution.')

    for result in relevant_results:
        item = _create_change_plan_item(plan=plan, source=source, result=result)
        item_counts[item.action] += 1
        family_counts[item.object_family] += 1
        if _family_is_advisory_only(result.coordination_family):
            capability_warnings.append(_advisory_only_warning_for_family(result.coordination_family))
        if item.action == rpki_models.IrrChangePlanAction.NOOP and result.result_type in ACTIONABLE_RESULT_TYPES:
            capability_warnings.append(item.reason)

    summary_json = _build_plan_summary(
        plan=plan,
        item_counts=item_counts,
        family_counts=family_counts,
        capability_warnings=capability_warnings,
    )
    actionable_item_count = sum(
        count for action, count in item_counts.items()
        if action != rpki_models.IrrChangePlanAction.NOOP
    )
    plan.status = (
        rpki_models.IrrChangePlanStatus.READY
        if actionable_item_count and source.write_support_mode != rpki_models.IrrWriteSupportMode.UNSUPPORTED
        else rpki_models.IrrChangePlanStatus.DRAFT
    )
    plan.summary_json = summary_json
    plan.save(update_fields=('status', 'summary_json'))
    return plan


def _create_change_plan_item(*, plan, source, result):
    action = _derive_action(result=result, source=source)
    before_state_json, after_state_json = _derive_plan_states(result)
    request_payload_json = (
        _build_request_payload(source=source, result=result, action=action, before_state_json=before_state_json, after_state_json=after_state_json)
        if action != rpki_models.IrrChangePlanAction.NOOP
        else {}
    )
    return rpki_models.IrrChangePlanItem.objects.create(
        name=_build_item_name(result=result, action=action),
        change_plan=plan,
        coordination_result=result,
        tenant=plan.tenant,
        object_family=result.coordination_family,
        action=action,
        stable_object_key=result.stable_object_key,
        source_object_key=result.source_object_key,
        roa_intent=result.roa_intent,
        imported_route_object=result.imported_route_object,
        imported_aut_num=result.imported_aut_num,
        imported_maintainer=result.imported_maintainer,
        before_state_json=before_state_json,
        after_state_json=after_state_json,
        request_payload_json=request_payload_json,
        reason=_build_item_reason(result=result, action=action),
    )


def _derive_action(*, result, source):
    if result.coordination_family == rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP:
        return _derive_route_set_action(result=result, source=source)
    if result.coordination_family == rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP:
        return _derive_as_set_action(result=result, source=source)
    if _family_is_advisory_only(result.coordination_family):
        return rpki_models.IrrChangePlanAction.NOOP
    if result.result_type in REVIEW_ONLY_RESULT_TYPES:
        return rpki_models.IrrChangePlanAction.NOOP
    if source.write_support_mode == rpki_models.IrrWriteSupportMode.UNSUPPORTED:
        return rpki_models.IrrChangePlanAction.NOOP
    if result.result_type == rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE:
        return rpki_models.IrrChangePlanAction.CREATE
    if result.result_type == rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE:
        return rpki_models.IrrChangePlanAction.DELETE
    if result.result_type == rpki_models.IrrCoordinationResultType.SOURCE_CONFLICT:
        return rpki_models.IrrChangePlanAction.REPLACE
    return rpki_models.IrrChangePlanAction.NOOP


def _derive_plan_states(result):
    before_state_json = {}
    after_state_json = {}
    if result.coordination_family == rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP:
        before_state_json, after_state_json = _derive_route_set_plan_states(result)
    elif result.coordination_family == rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP:
        before_state_json, after_state_json = _derive_as_set_plan_states(result)
    elif result.imported_route_object_id is not None:
        before_state_json = _serialize_imported_route(result.imported_route_object)
    elif result.imported_aut_num_id is not None:
        before_state_json = _serialize_imported_aut_num(result.imported_aut_num)
    elif result.imported_maintainer_id is not None:
        before_state_json = _serialize_imported_maintainer(result.imported_maintainer)

    if result.roa_intent_id is not None and result.coordination_family == rpki_models.IrrCoordinationFamily.ROUTE_OBJECT:
        after_state_json = _serialize_roa_intent_route(result.roa_intent)
    return before_state_json, after_state_json


def _serialize_roa_intent_route(roa_intent: rpki_models.ROAIntent) -> dict:
    address_family = (
        rpki_models.AddressFamily.IPV6
        if ':' in (roa_intent.prefix_cidr_text or '')
        else rpki_models.AddressFamily.IPV4
    )
    object_class = 'route6' if address_family == rpki_models.AddressFamily.IPV6 else 'route'
    return {
        'address_family': address_family,
        'object_class': object_class,
        'prefix': roa_intent.prefix_cidr_text,
        'origin_asn': f'AS{roa_intent.origin_asn_value}',
        'max_length': roa_intent.max_length,
        'stable_key': result_key_for_route(
            prefix=roa_intent.prefix_cidr_text,
            origin_asn=f'AS{roa_intent.origin_asn_value}',
        ),
    }


def _serialize_imported_route(imported_route: rpki_models.ImportedIrrRouteObject) -> dict:
    return {
        'address_family': imported_route.address_family,
        'object_class': imported_route.rpsl_object_class,
        'prefix': imported_route.prefix,
        'origin_asn': imported_route.origin_asn,
        'route_set_names': list(imported_route.route_set_names_json),
        'maintainer_names': list(imported_route.maintainer_names_json),
        'source_database_label': imported_route.source_database_label,
        'stable_key': imported_route.stable_key,
        'rpsl_pk': imported_route.rpsl_pk,
    }


def _serialize_imported_aut_num(imported_aut_num: rpki_models.ImportedIrrAutNum) -> dict:
    return {
        'asn': imported_aut_num.asn,
        'as_name': imported_aut_num.as_name,
        'import_policy_summary': imported_aut_num.import_policy_summary,
        'export_policy_summary': imported_aut_num.export_policy_summary,
        'maintainer_names': list(imported_aut_num.maintainer_names_json),
        'stable_key': imported_aut_num.stable_key,
    }


def _serialize_imported_maintainer(imported_maintainer: rpki_models.ImportedIrrMaintainer) -> dict:
    return {
        'maintainer_name': imported_maintainer.maintainer_name,
        'auth_summary': list(imported_maintainer.auth_summary_json),
        'admin_contacts': list(imported_maintainer.admin_contact_handles_json),
        'upd_to_addresses': list(imported_maintainer.upd_to_addresses_json),
        'stable_key': imported_maintainer.stable_key,
    }


def _build_request_payload(*, source, result, action, before_state_json, after_state_json) -> dict:
    if result.coordination_family == rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP:
        if action == rpki_models.IrrChangePlanAction.CREATE:
            target = after_state_json
        elif action == rpki_models.IrrChangePlanAction.DELETE:
            target = before_state_json
        else:
            target = after_state_json or before_state_json
        if not target:
            return {}
        return {
            'operation': action,
            'object_family': result.coordination_family,
            'source_slug': source.slug,
            'database': source.default_database_label,
            'rpsl_pk': target.get('rpsl_pk', ''),
            'stable_key': target.get('stable_key', result.stable_object_key),
            'attributes': {
                'route-set': target.get('set_name', ''),
                'members': list(target.get('members', [])),
                'mp-members': list(target.get('mp_members', [])),
                'source': source.default_database_label,
            },
            'existing_object': before_state_json,
            'replacement_object': after_state_json,
        }
    if result.coordination_family == rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP:
        target = after_state_json or before_state_json
        if not target:
            return {}
        return {
            'operation': action,
            'object_family': result.coordination_family,
            'source_slug': source.slug,
            'database': source.default_database_label,
            'rpsl_pk': target.get('rpsl_pk', ''),
            'stable_key': target.get('stable_key', result.stable_object_key),
            'attributes': {
                'as-set': target.get('set_name', ''),
                'members': list(target.get('members', [])),
                'source': source.default_database_label,
            },
            'existing_object': before_state_json,
            'replacement_object': after_state_json,
        }
    if result.coordination_family != rpki_models.IrrCoordinationFamily.ROUTE_OBJECT:
        return {}

    if action == rpki_models.IrrChangePlanAction.CREATE:
        target = after_state_json
    elif action == rpki_models.IrrChangePlanAction.DELETE:
        target = before_state_json
    else:
        target = after_state_json or before_state_json

    if not target:
        return {}

    attributes = {
        target.get('object_class', 'route'): target.get('prefix', ''),
        'origin': target.get('origin_asn', ''),
        'source': source.default_database_label,
    }
    if source.maintainer_name:
        attributes['mnt-by'] = [source.maintainer_name]

    payload = {
        'operation': action,
        'object_family': result.coordination_family,
        'source_slug': source.slug,
        'database': source.default_database_label,
        'rpsl_pk': target.get('rpsl_pk', ''),
        'stable_key': target.get('stable_key', result.stable_object_key),
        'attributes': attributes,
    }
    if action == rpki_models.IrrChangePlanAction.REPLACE:
        payload['existing_object'] = before_state_json
        payload['replacement_object'] = after_state_json
    return payload


def _build_item_name(*, result, action) -> str:
    target = result.stable_object_key or result.source_object_key or result.name
    return f'{action.title()} {target}'


def _build_item_reason(*, result, action) -> str:
    if result.coordination_family == rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP:
        if action == rpki_models.IrrChangePlanAction.CREATE:
            return 'NetBox policy expects a route-set object that is currently missing from the target IRR source.'
        if action == rpki_models.IrrChangePlanAction.MODIFY:
            if result.result_type == rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE:
                return 'Target IRR source route-set is missing a member implied by the coordinated route object.'
            if result.result_type == rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE:
                return 'Target IRR source route-set contains a member that is not declared by the coordinated route object.'
            return 'Target IRR source route-set membership needs an updated draft.'
        if action == rpki_models.IrrChangePlanAction.DELETE:
            return 'Target IRR source route-set no longer has any members implied by NetBox policy and can be removed.'
        return 'Route-set membership delta could not be synthesized automatically because no imported parent route-set object was available for a safe draft.'
    if result.coordination_family == rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP:
        if action == rpki_models.IrrChangePlanAction.CREATE:
            return 'Authored AS-set policy expects an AS-set object that is currently missing from the target IRR source.'
        if action == rpki_models.IrrChangePlanAction.MODIFY:
            if result.result_type == rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE:
                return 'Target IRR source AS-set is missing a member required by authored policy.'
            if result.result_type == rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE:
                return 'Target IRR source AS-set contains a member that is not present in authored policy.'
            return 'Target IRR source AS-set needs an updated membership draft.'
        return 'AS-set membership delta could not be synthesized automatically because no authored AS-set policy was available for a safe draft.'
    if action == rpki_models.IrrChangePlanAction.CREATE:
        return 'NetBox policy expects a route object that is currently missing from the target IRR source.'
    if action == rpki_models.IrrChangePlanAction.DELETE:
        return 'Target IRR source currently publishes a route object that is no longer represented by NetBox policy.'
    if action == rpki_models.IrrChangePlanAction.REPLACE:
        return 'Target IRR source publishes a conflicting route object and needs a source-specific replacement draft.'
    if result.result_type == rpki_models.IrrCoordinationResultType.POLICY_CONTEXT_GAP:
        return 'The route object delta depends on additional policy-context work that is not synthesized automatically.'
    if result.result_type == rpki_models.IrrCoordinationResultType.UNSUPPORTED_WRITE:
        return 'The target source exposes context needed for review, but this change is not safely writable through the current adapter.'
    if result.result_type == rpki_models.IrrCoordinationResultType.AMBIGUOUS_LINKAGE:
        return 'The linkage between NetBox policy and imported IRR state is ambiguous and requires operator review.'
    return 'Review-only IRR coordination result.'


def _build_plan_summary(*, plan, item_counts, family_counts, capability_warnings):
    actionable_item_count = sum(
        count for action, count in item_counts.items()
        if action != rpki_models.IrrChangePlanAction.NOOP
    )
    capability_warning_list = list(dict.fromkeys(capability_warnings))
    return {
        'target_source': plan.source.slug,
        'write_support_mode': plan.write_support_mode,
        'previewable': bool(plan.supports_preview and actionable_item_count),
        'applyable': bool(plan.supports_apply and actionable_item_count),
        'item_counts': {
            rpki_models.IrrChangePlanAction.CREATE: item_counts.get(rpki_models.IrrChangePlanAction.CREATE, 0),
            rpki_models.IrrChangePlanAction.MODIFY: item_counts.get(rpki_models.IrrChangePlanAction.MODIFY, 0),
            rpki_models.IrrChangePlanAction.REPLACE: item_counts.get(rpki_models.IrrChangePlanAction.REPLACE, 0),
            rpki_models.IrrChangePlanAction.DELETE: item_counts.get(rpki_models.IrrChangePlanAction.DELETE, 0),
            rpki_models.IrrChangePlanAction.NOOP: item_counts.get(rpki_models.IrrChangePlanAction.NOOP, 0),
        },
        'family_counts': {
            rpki_models.IrrCoordinationFamily.ROUTE_OBJECT: family_counts.get(rpki_models.IrrCoordinationFamily.ROUTE_OBJECT, 0),
            rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP: family_counts.get(rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP, 0),
            rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP: family_counts.get(rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP, 0),
            rpki_models.IrrCoordinationFamily.AUT_NUM_CONTEXT: family_counts.get(rpki_models.IrrCoordinationFamily.AUT_NUM_CONTEXT, 0),
            rpki_models.IrrCoordinationFamily.MAINTAINER_SUPPORTABILITY: family_counts.get(rpki_models.IrrCoordinationFamily.MAINTAINER_SUPPORTABILITY, 0),
        },
        'capability_warnings': capability_warning_list,
        'latest_execution': None,
    }


def _family_is_advisory_only(coordination_family: str) -> bool:
    return False


def _advisory_only_warning_for_family(coordination_family: str) -> str:
    return 'This coordination family is currently advisory-only.'


def preview_irr_change_plan(
    plan: rpki_models.IrrChangePlan | int,
    *,
    requested_by: str = '',
    replay_safe: bool = False,
) -> tuple[rpki_models.IrrWriteExecution, dict]:
    plan = _normalize_change_plan(plan)
    payload = _build_execution_payload(plan)
    request_fingerprint = _build_execution_request_fingerprint(
        plan=plan,
        execution_mode=rpki_models.IrrWriteExecutionMode.PREVIEW,
        payload=payload,
    )
    payload['request_fingerprint'] = request_fingerprint
    if replay_safe:
        replayed_execution = _find_replay_safe_execution(
            plan=plan,
            execution_mode=rpki_models.IrrWriteExecutionMode.PREVIEW,
            request_fingerprint=request_fingerprint,
        )
        if replayed_execution is not None:
            replay_payload = dict(replayed_execution.response_payload_json or replayed_execution.request_payload_json or payload)
            replay_payload['replayed'] = True
            replay_payload['replayed_execution_pk'] = replayed_execution.pk
            replay_payload['request_fingerprint'] = request_fingerprint
            return replayed_execution, replay_payload

    if not plan.can_preview:
        raise IrrWriteExecutionError('IRR change plan is not previewable in its current state.')

    started_at = timezone.now()
    execution = rpki_models.IrrWriteExecution.objects.create(
        name=f'{plan.name} Preview {started_at:%Y-%m-%d %H:%M:%S}',
        organization=plan.organization,
        source=plan.source,
        change_plan=plan,
        tenant=plan.tenant,
        execution_mode=rpki_models.IrrWriteExecutionMode.PREVIEW,
        status=rpki_models.IrrWriteExecutionStatus.COMPLETED,
        requested_by=requested_by,
        started_at=started_at,
        completed_at=started_at,
        item_count=payload['actionable_item_count'],
        request_fingerprint=request_fingerprint,
        request_payload_json=payload,
        response_payload_json={
            'preview_only': True,
            'write_support_mode': plan.write_support_mode,
            'request_fingerprint': request_fingerprint,
            'item_results': payload['item_results'],
        },
    )
    _update_plan_latest_execution(plan, execution)
    return execution, payload


def apply_irr_change_plan(
    plan: rpki_models.IrrChangePlan | int,
    *,
    requested_by: str = '',
    replay_safe: bool = False,
) -> tuple[rpki_models.IrrWriteExecution, dict]:
    plan = _normalize_change_plan(plan)
    payload = _build_execution_payload(plan)
    request_fingerprint = _build_execution_request_fingerprint(
        plan=plan,
        execution_mode=rpki_models.IrrWriteExecutionMode.APPLY,
        payload=payload,
    )
    payload['request_fingerprint'] = request_fingerprint
    if replay_safe:
        replayed_execution = _find_replay_safe_execution(
            plan=plan,
            execution_mode=rpki_models.IrrWriteExecutionMode.APPLY,
            request_fingerprint=request_fingerprint,
        )
        if replayed_execution is not None:
            replay_payload = dict(replayed_execution.response_payload_json or payload)
            replay_payload['replayed'] = True
            replay_payload['replayed_execution_pk'] = replayed_execution.pk
            replay_payload['request_fingerprint'] = request_fingerprint
            return replayed_execution, replay_payload

    if not plan.can_apply:
        raise IrrWriteExecutionError('IRR change plan is not applyable in its current state.')
    if plan.source.source_family != rpki_models.IrrSourceFamily.IRRD_COMPATIBLE:
        raise IrrWriteExecutionError(f'IRR source family {plan.source.source_family} is not implemented for write execution yet.')
    if not plan.source.api_key:
        raise IrrWriteExecutionError('IRR source api_key is required for IRRd override-based write execution.')

    started_at = timezone.now()
    plan.status = rpki_models.IrrChangePlanStatus.EXECUTING
    plan.execution_started_at = started_at
    plan.execution_requested_by = requested_by
    plan.completed_at = None
    plan.failed_at = None
    plan.save(update_fields=('status', 'execution_started_at', 'execution_requested_by', 'completed_at', 'failed_at'))

    execution = rpki_models.IrrWriteExecution.objects.create(
        name=f'{plan.name} Apply {started_at:%Y-%m-%d %H:%M:%S}',
        organization=plan.organization,
        source=plan.source,
        change_plan=plan,
        tenant=plan.tenant,
        execution_mode=rpki_models.IrrWriteExecutionMode.APPLY,
        status=rpki_models.IrrWriteExecutionStatus.RUNNING,
        requested_by=requested_by,
        started_at=started_at,
        item_count=payload['actionable_item_count'],
        request_fingerprint=request_fingerprint,
        request_payload_json=payload,
    )

    final_payload: dict = {
        'write_support_mode': plan.write_support_mode,
        'item_results': [],
        'request_summary': payload['request_summary'],
        'request_fingerprint': request_fingerprint,
    }
    successful_operations = 0
    failed_operations = 0
    encountered_error_messages: list[str] = []

    try:
        for item_result in payload['item_results']:
            if item_result.get('skipped'):
                final_payload['item_results'].append(item_result)
                continue
            operation_outcomes = []
            for operation in item_result['operations']:
                response_payload = _submit_irrd_operation(plan.source, operation)
                operation_success = _operation_succeeded(response_payload)
                operation_outcomes.append(
                    {
                        'method': operation['method'],
                        'url': operation['url'],
                        'request_body': operation['body'],
                        'successful': operation_success,
                        'response': response_payload,
                    }
                )
                if operation_success:
                    successful_operations += 1
                else:
                    failed_operations += 1
                    encountered_error_messages.extend(_extract_error_messages(response_payload))
            enriched_item_result = dict(item_result)
            enriched_item_result['operation_outcomes'] = operation_outcomes
            final_payload['item_results'].append(enriched_item_result)

        completed_at = timezone.now()
        execution.completed_at = completed_at
        execution.response_payload_json = final_payload
        if failed_operations and successful_operations:
            execution.status = rpki_models.IrrWriteExecutionStatus.PARTIAL
            execution.error = '; '.join(encountered_error_messages)[:4000]
            plan.status = rpki_models.IrrChangePlanStatus.FAILED
            plan.failed_at = completed_at
            plan.completed_at = None
        elif failed_operations:
            execution.status = rpki_models.IrrWriteExecutionStatus.FAILED
            execution.error = '; '.join(encountered_error_messages)[:4000]
            plan.status = rpki_models.IrrChangePlanStatus.FAILED
            plan.failed_at = completed_at
            plan.completed_at = None
        else:
            execution.status = rpki_models.IrrWriteExecutionStatus.COMPLETED
            plan.status = rpki_models.IrrChangePlanStatus.COMPLETED
            plan.completed_at = completed_at
            plan.failed_at = None
        execution.save(update_fields=('status', 'completed_at', 'response_payload_json', 'error'))
        plan.save(update_fields=('status', 'completed_at', 'failed_at'))
        _update_plan_latest_execution(plan, execution)
        return execution, final_payload
    except Exception as exc:
        completed_at = timezone.now()
        execution.status = rpki_models.IrrWriteExecutionStatus.FAILED
        execution.completed_at = completed_at
        execution.error = str(exc)
        execution.response_payload_json = final_payload
        execution.save(update_fields=('status', 'completed_at', 'error', 'response_payload_json'))
        plan.status = rpki_models.IrrChangePlanStatus.FAILED
        plan.failed_at = completed_at
        plan.completed_at = None
        plan.save(update_fields=('status', 'failed_at', 'completed_at'))
        _update_plan_latest_execution(plan, execution)
        raise IrrWriteExecutionError(str(exc)) from exc


def _normalize_change_plan(plan: rpki_models.IrrChangePlan | int) -> rpki_models.IrrChangePlan:
    if isinstance(plan, rpki_models.IrrChangePlan):
        return plan
    return rpki_models.IrrChangePlan.objects.get(pk=plan)


def _build_execution_request_fingerprint(
    *,
    plan: rpki_models.IrrChangePlan,
    execution_mode: str,
    payload: dict,
) -> str:
    serialized = json.dumps(
        {
            'change_plan_pk': plan.pk,
            'execution_mode': execution_mode,
            'payload': payload,
        },
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _find_replay_safe_execution(
    *,
    plan: rpki_models.IrrChangePlan,
    execution_mode: str,
    request_fingerprint: str,
) -> rpki_models.IrrWriteExecution | None:
    replayable_statuses = (
        (rpki_models.IrrWriteExecutionStatus.COMPLETED,)
        if execution_mode == rpki_models.IrrWriteExecutionMode.PREVIEW
        else (
            rpki_models.IrrWriteExecutionStatus.RUNNING,
            rpki_models.IrrWriteExecutionStatus.COMPLETED,
            rpki_models.IrrWriteExecutionStatus.PARTIAL,
        )
    )
    return plan.write_executions.filter(
        execution_mode=execution_mode,
        request_fingerprint=request_fingerprint,
        status__in=replayable_statuses,
    ).order_by('-started_at', '-pk').first()


def _build_execution_payload(plan: rpki_models.IrrChangePlan) -> dict:
    item_results = []
    request_summary = {
        'create_requests': 0,
        'modify_requests': 0,
        'replace_requests': 0,
        'delete_requests': 0,
        'noop_items': 0,
    }
    actionable_item_count = 0
    for item in plan.items.select_related('imported_route_object').order_by('name', 'pk'):
        operations = _build_item_operations(plan.source, item)
        skipped = item.action == rpki_models.IrrChangePlanAction.NOOP or not operations
        if skipped:
            request_summary['noop_items'] += 1
        else:
            actionable_item_count += 1
            if item.action == rpki_models.IrrChangePlanAction.CREATE:
                request_summary['create_requests'] += 1
            elif item.action == rpki_models.IrrChangePlanAction.MODIFY:
                request_summary['modify_requests'] += 1
            elif item.action == rpki_models.IrrChangePlanAction.REPLACE:
                request_summary['replace_requests'] += 1
            elif item.action == rpki_models.IrrChangePlanAction.DELETE:
                request_summary['delete_requests'] += 1
        item_results.append(
            {
                'item_id': item.pk,
                'item_name': item.name,
                'action': item.action,
                'object_family': item.object_family,
                'stable_object_key': item.stable_object_key,
                'skipped': skipped,
                'operations': operations,
            }
        )
    return {
        'source_slug': plan.source.slug,
        'source_family': plan.source.source_family,
        'write_support_mode': plan.write_support_mode,
        'actionable_item_count': actionable_item_count,
        'request_summary': request_summary,
        'item_results': item_results,
    }


def _build_item_operations(source: rpki_models.IrrSource, item: rpki_models.IrrChangePlanItem) -> list[dict]:
    if item.action == rpki_models.IrrChangePlanAction.NOOP:
        return []
    if item.object_family == rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP:
        if item.action in {rpki_models.IrrChangePlanAction.CREATE, rpki_models.IrrChangePlanAction.MODIFY}:
            object_text = _render_route_set_object_text(source=source, state_json=item.after_state_json)
            return [_build_submit_operation(source=source, method='POST', object_texts=[object_text])]
        if item.action == rpki_models.IrrChangePlanAction.DELETE:
            object_text = _existing_route_set_object_text(item)
            return [_build_submit_operation(source=source, method='DELETE', object_texts=[object_text], delete_reason=item.reason or 'Deleted by netbox_rpki IRR coordination.')]
        return []
    if item.object_family == rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP:
        if item.action == rpki_models.IrrChangePlanAction.CREATE:
            object_text = _render_as_set_object_text(source=source, state_json=item.after_state_json)
            return [_build_submit_operation(source=source, method='POST', object_texts=[object_text])]
        if item.action == rpki_models.IrrChangePlanAction.MODIFY:
            object_text = _render_as_set_object_text(source=source, state_json=item.after_state_json)
            return [_build_submit_operation(source=source, method='POST', object_texts=[object_text])]
        return []
    if item.object_family != rpki_models.IrrCoordinationFamily.ROUTE_OBJECT:
        return []
    if item.action in {rpki_models.IrrChangePlanAction.CREATE, rpki_models.IrrChangePlanAction.MODIFY}:
        object_text = _render_route_object_text(source=source, state_json=item.after_state_json)
        return [_build_submit_operation(source=source, method='POST', object_texts=[object_text])]
    if item.action == rpki_models.IrrChangePlanAction.DELETE:
        object_text = _existing_route_object_text(item)
        return [_build_submit_operation(source=source, method='DELETE', object_texts=[object_text], delete_reason=item.reason or 'Deleted by netbox_rpki IRR coordination.')]
    if item.action == rpki_models.IrrChangePlanAction.REPLACE:
        create_text = _render_route_object_text(source=source, state_json=item.after_state_json)
        delete_text = _existing_route_object_text(item)
        return [
            _build_submit_operation(source=source, method='POST', object_texts=[create_text]),
            _build_submit_operation(source=source, method='DELETE', object_texts=[delete_text], delete_reason=item.reason or 'Replaced by netbox_rpki IRR coordination.'),
        ]
    return []


def _render_route_object_text(*, source: rpki_models.IrrSource, state_json: dict) -> str:
    object_class = state_json.get('object_class') or 'route'
    prefix = state_json.get('prefix') or ''
    origin_asn = (state_json.get('origin_asn') or '').upper()
    lines = [
        f'{object_class}:        {prefix}',
        f'descr:           Generated by netbox_rpki',
        f'origin:          {origin_asn}',
    ]
    if source.maintainer_name:
        lines.append(f'mnt-by:          {source.maintainer_name}')
    if source.default_database_label:
        lines.append(f'source:          {source.default_database_label}')
    return '\n'.join(lines)


def _existing_route_object_text(item: rpki_models.IrrChangePlanItem) -> str:
    if item.imported_route_object_id is not None and item.imported_route_object.object_text:
        return item.imported_route_object.object_text
    state_json = item.before_state_json or {}
    lines = [
        f'{state_json.get("object_class", "route")}:        {state_json.get("prefix", "")}',
        f'origin:          {(state_json.get("origin_asn") or "").upper()}',
    ]
    if state_json.get('source_database_label'):
        lines.append(f'source:          {state_json["source_database_label"]}')
    return '\n'.join(lines)


def _derive_route_set_action(*, result, source):
    if result.result_type in REVIEW_ONLY_RESULT_TYPES:
        return rpki_models.IrrChangePlanAction.NOOP
    if source.write_support_mode == rpki_models.IrrWriteSupportMode.UNSUPPORTED:
        return rpki_models.IrrChangePlanAction.NOOP
    if result.result_type not in {
        rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
        rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE,
    }:
        return rpki_models.IrrChangePlanAction.NOOP
    if not _is_primary_route_set_result(result):
        return rpki_models.IrrChangePlanAction.NOOP
    target_member = _route_set_target_member_text(result)
    if not target_member:
        return rpki_models.IrrChangePlanAction.NOOP
    route_set = _resolve_route_set_for_result(result)
    desired_state_json = _desired_route_set_state(result=result, route_set=route_set)
    before_state_json = _serialize_imported_route_set(route_set) if route_set is not None else {}
    if route_set is None:
        return (
            rpki_models.IrrChangePlanAction.CREATE
            if desired_state_json
            else rpki_models.IrrChangePlanAction.NOOP
        )
    if not desired_state_json:
        return rpki_models.IrrChangePlanAction.DELETE
    after_state_json = dict(desired_state_json)
    if (
        before_state_json.get('members') == after_state_json.get('members')
        and before_state_json.get('mp_members') == after_state_json.get('mp_members')
    ):
        return rpki_models.IrrChangePlanAction.NOOP
    return rpki_models.IrrChangePlanAction.MODIFY


def _derive_as_set_action(*, result, source):
    if result.result_type in REVIEW_ONLY_RESULT_TYPES:
        return rpki_models.IrrChangePlanAction.NOOP
    if source.write_support_mode == rpki_models.IrrWriteSupportMode.UNSUPPORTED:
        return rpki_models.IrrChangePlanAction.NOOP
    if result.result_type not in {
        rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
        rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE,
    }:
        return rpki_models.IrrChangePlanAction.NOOP
    authored_as_set = _resolve_authored_as_set_for_result(result)
    if authored_as_set is None:
        return rpki_models.IrrChangePlanAction.NOOP
    if result.result_type == rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE and _resolve_as_set_for_result(result) is None:
        return rpki_models.IrrChangePlanAction.CREATE
    return rpki_models.IrrChangePlanAction.MODIFY


def _derive_route_set_plan_states(result) -> tuple[dict, dict]:
    route_set = _resolve_route_set_for_result(result)
    before_state_json = _serialize_imported_route_set(route_set) if route_set is not None else {}
    desired_state_json = _desired_route_set_state(result=result, route_set=route_set)
    after_state_json = dict(desired_state_json)
    if route_set is None and not after_state_json:
        return {}, {}
    target_member = _route_set_target_member_text(result)
    if target_member:
        after_state_json['target_member_text'] = target_member
        after_state_json['membership_change'] = (
            'add'
            if result.result_type == rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE
            else 'remove'
        )
    return before_state_json, after_state_json


def _desired_route_set_state(*, result, route_set: rpki_models.ImportedIrrRouteSet | None) -> dict:
    route_set_name = _route_set_name_for_result(result)
    if not route_set_name:
        return {}
    members: list[str] = []
    mp_members: list[str] = []
    declared_member_found = False
    canonical_set_name = route_set_name.strip().upper()
    queryset = rpki_models.ImportedIrrRouteObject.objects.filter(source=result.source)
    if result.snapshot_id is not None:
        queryset = queryset.filter(snapshot_id=result.snapshot_id)
    for imported_route in queryset.order_by('prefix', 'pk'):
        declared_names = {
            (name or '').strip().upper()
            for name in imported_route.route_set_names_json or []
            if (name or '').strip()
        }
        if canonical_set_name not in declared_names:
            continue
        prefix = (imported_route.prefix or '').strip()
        if not prefix:
            continue
        declared_member_found = True
        if _is_ipv6_member_text(prefix):
            mp_members.append(prefix)
        else:
            members.append(prefix)
    if not declared_member_found:
        members, mp_members = _fallback_route_set_members(result=result, route_set=route_set)
    members = sorted(dict.fromkeys(members), key=str.lower)
    mp_members = sorted(dict.fromkeys(mp_members), key=str.lower)
    if not members and not mp_members:
        return {}
    return {
        'object_class': 'route-set',
        'set_name': route_set_name,
        'rpsl_pk': getattr(route_set, 'rpsl_pk', '') or route_set_name,
        'stable_key': getattr(route_set, 'stable_key', '') or f'route_set:{route_set_name}',
        'maintainer_names': (
            list(getattr(route_set, 'maintainer_names_json', []) or [])
            or ([result.source.maintainer_name] if result.source.maintainer_name else [])
        ),
        'source_database_label': (
            getattr(route_set, 'source_database_label', '')
            or result.source.default_database_label
        ),
        'member_count': len(members) + len(mp_members),
        'members': members,
        'mp_members': mp_members,
        'existing_object_text': getattr(route_set, 'object_text', ''),
    }


def _fallback_route_set_members(
    *,
    result,
    route_set: rpki_models.ImportedIrrRouteSet | None,
) -> tuple[list[str], list[str]]:
    before_state_json = _serialize_imported_route_set(route_set) if route_set is not None else {}
    members = list(before_state_json.get('members', []))
    mp_members = list(before_state_json.get('mp_members', []))
    target_member = _route_set_target_member_text(result)
    if not target_member:
        return members, mp_members
    member_list = mp_members if _is_ipv6_member_text(target_member) else members
    member_list[:] = [member for member in member_list if member.lower() != target_member.lower()]
    if result.result_type == rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE:
        member_list.append(target_member)
    return members, mp_members


def _route_set_name_for_result(result) -> str:
    return ((result.summary_json or {}).get('route_set_name') or '').strip()


def _is_primary_route_set_result(result) -> bool:
    route_set_name = _route_set_name_for_result(result)
    if not route_set_name:
        return False
    queryset = result.coordination_run.results.filter(
        source=result.source,
        coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
    )
    if result.snapshot_id is None:
        queryset = queryset.filter(snapshot__isnull=True)
    else:
        queryset = queryset.filter(snapshot_id=result.snapshot_id)
    primary = None
    canonical_target = route_set_name.upper()
    for candidate in queryset.order_by('stable_object_key', 'pk'):
        candidate_name = _route_set_name_for_result(candidate).upper()
        if candidate_name == canonical_target:
            primary = candidate
            break
    return primary is not None and primary.pk == result.pk


def _derive_as_set_plan_states(result) -> tuple[dict, dict]:
    authored_as_set = _resolve_authored_as_set_for_result(result)
    if authored_as_set is None:
        return dict(result.summary_json or {}), {}

    imported_as_set = _resolve_as_set_for_result(result)
    before_state_json = _serialize_imported_as_set(imported_as_set) if imported_as_set is not None else {}
    after_state_json = _serialize_authored_as_set(authored_as_set)
    return before_state_json, after_state_json


def _resolve_route_set_for_result(result) -> rpki_models.ImportedIrrRouteSet | None:
    summary_json = result.summary_json or {}
    route_set_stable_key = summary_json.get('route_set_stable_key') or ''
    queryset = rpki_models.ImportedIrrRouteSet.objects.filter(source=result.source)
    if result.snapshot_id is not None:
        queryset = queryset.filter(snapshot_id=result.snapshot_id)
    if route_set_stable_key:
        return queryset.filter(stable_key=route_set_stable_key).order_by('pk').first()
    route_set_name = summary_json.get('route_set_name') or ''
    if not route_set_name:
        return None
    return queryset.filter(set_name__iexact=route_set_name).order_by('pk').first()


def _resolve_as_set_for_result(result) -> rpki_models.ImportedIrrAsSet | None:
    summary_json = result.summary_json or {}
    as_set_stable_key = summary_json.get('as_set_stable_key') or ''
    queryset = rpki_models.ImportedIrrAsSet.objects.filter(source=result.source)
    if result.snapshot_id is not None:
        queryset = queryset.filter(snapshot_id=result.snapshot_id)
    if as_set_stable_key:
        return queryset.filter(stable_key=as_set_stable_key).order_by('pk').first()
    as_set_name = summary_json.get('as_set_name') or ''
    if not as_set_name:
        return None
    return queryset.filter(set_name__iexact=as_set_name).order_by('pk').first()


def _resolve_authored_as_set_for_result(result) -> rpki_models.AuthoredAsSet | None:
    summary_json = result.summary_json or {}
    authored_as_set_id = summary_json.get('authored_as_set_id')
    if authored_as_set_id:
        return rpki_models.AuthoredAsSet.objects.filter(pk=authored_as_set_id).first()
    as_set_name = summary_json.get('as_set_name') or ''
    if not as_set_name or result.coordination_run.organization_id is None:
        return None
    return rpki_models.AuthoredAsSet.objects.filter(
        organization_id=result.coordination_run.organization_id,
        set_name__iexact=as_set_name,
    ).first()


def _serialize_imported_route_set(imported_route_set: rpki_models.ImportedIrrRouteSet) -> dict:
    members: list[str] = []
    mp_members: list[str] = []
    for membership in imported_route_set.members.order_by('member_text', 'pk'):
        member_text = (membership.member_text or '').strip()
        if not member_text:
            continue
        if _is_ipv6_member_text(member_text):
            mp_members.append(member_text)
        else:
            members.append(member_text)
    return {
        'object_class': imported_route_set.rpsl_object_class or 'route-set',
        'set_name': imported_route_set.set_name,
        'rpsl_pk': imported_route_set.rpsl_pk,
        'stable_key': imported_route_set.stable_key,
        'maintainer_names': list(imported_route_set.maintainer_names_json),
        'source_database_label': imported_route_set.source_database_label,
        'member_count': len(members) + len(mp_members),
        'members': members,
        'mp_members': mp_members,
        'existing_object_text': imported_route_set.object_text,
    }


def _serialize_imported_as_set(imported_as_set: rpki_models.ImportedIrrAsSet) -> dict:
    members: list[str] = []
    for membership in imported_as_set.members.order_by('member_text', 'pk'):
        member_text = (membership.member_text or '').strip()
        if member_text:
            members.append(member_text.upper() if member_text.upper().startswith('AS') else member_text)
    return {
        'object_class': imported_as_set.rpsl_object_class or 'as-set',
        'set_name': imported_as_set.set_name,
        'rpsl_pk': imported_as_set.rpsl_pk,
        'stable_key': imported_as_set.stable_key,
        'maintainer_names': list(imported_as_set.maintainer_names_json),
        'source_database_label': imported_as_set.source_database_label,
        'member_count': len(members),
        'members': members,
        'existing_object_text': imported_as_set.object_text,
    }


def _serialize_authored_as_set(authored_as_set: rpki_models.AuthoredAsSet) -> dict:
    members: list[str] = []
    for membership in authored_as_set.members.filter(enabled=True).order_by('name', 'pk'):
        member_text = membership.member_text
        if member_text:
            members.append(member_text)
    return {
        'object_class': 'as-set',
        'set_name': authored_as_set.set_name,
        'rpsl_pk': authored_as_set.set_name,
        'stable_key': f'authored_as_set:{authored_as_set.pk}',
        'authored_as_set_id': authored_as_set.pk,
        'member_count': len(members),
        'members': members,
        'existing_object_text': '',
    }


def _route_set_target_member_text(result) -> str:
    summary_json = result.summary_json or {}
    return (
        summary_json.get('route_prefix')
        or summary_json.get('member_text')
        or summary_json.get('target_member_text')
        or ''
    )


def _is_ipv6_member_text(member_text: str) -> bool:
    return ':' in (member_text or '') and '/' in (member_text or '')


def _render_route_set_object_text(*, source: rpki_models.IrrSource, state_json: dict) -> str:
    existing_object_text = (state_json.get('existing_object_text') or '').strip('\n')
    if existing_object_text:
        preserved_lines: list[str] = []
        current_key = ''
        for raw_line in existing_object_text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                if current_key not in {'members', 'mp-members', 'source'}:
                    preserved_lines.append(line)
                continue
            if line.startswith((' ', '\t')):
                if current_key not in {'members', 'mp-members', 'source'}:
                    preserved_lines.append(line)
                continue
            if ':' not in line:
                if current_key not in {'members', 'mp-members', 'source'}:
                    preserved_lines.append(line)
                continue
            key, _value = line.split(':', 1)
            current_key = key.strip().lower()
            if current_key in {'members', 'mp-members', 'source'}:
                continue
            preserved_lines.append(line)
        lines = preserved_lines
    else:
        lines = [
            f'route-set:       {state_json.get("set_name", "")}',
            'descr:           Generated by netbox_rpki',
        ]
        for maintainer_name in state_json.get('maintainer_names', []) or []:
            lines.append(f'mnt-by:          {maintainer_name}')

    if state_json.get('members'):
        lines.append(f'members:         {", ".join(state_json["members"])}')
    if state_json.get('mp_members'):
        lines.append(f'mp-members:      {", ".join(state_json["mp_members"])}')
    if source.default_database_label:
        lines.append(f'source:          {source.default_database_label}')
    return '\n'.join(lines)


def _existing_route_set_object_text(item: rpki_models.IrrChangePlanItem) -> str:
    state_json = item.before_state_json or {}
    existing_object_text = (state_json.get('existing_object_text') or '').strip()
    if existing_object_text:
        return existing_object_text
    return _render_route_set_object_text(source=item.change_plan.source, state_json=state_json)


def _render_as_set_object_text(*, source: rpki_models.IrrSource, state_json: dict) -> str:
    existing_object_text = (state_json.get('existing_object_text') or '').strip('\n')
    if existing_object_text:
        preserved_lines: list[str] = []
        current_key = ''
        for raw_line in existing_object_text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                if current_key not in {'members', 'source'}:
                    preserved_lines.append(line)
                continue
            if line.startswith((' ', '\t')):
                if current_key not in {'members', 'source'}:
                    preserved_lines.append(line)
                continue
            if ':' not in line:
                if current_key not in {'members', 'source'}:
                    preserved_lines.append(line)
                continue
            key, _value = line.split(':', 1)
            current_key = key.strip().lower()
            if current_key in {'members', 'source'}:
                continue
            preserved_lines.append(line)
        lines = preserved_lines
    else:
        lines = [
            f'as-set:          {state_json.get("set_name", "")}',
            'descr:           Generated by netbox_rpki',
        ]
        if source.maintainer_name:
            lines.append(f'mnt-by:          {source.maintainer_name}')

    if state_json.get('members'):
        lines.append(f'members:         {", ".join(state_json["members"])}')
    if source.default_database_label:
        lines.append(f'source:          {source.default_database_label}')
    return '\n'.join(lines)


def _build_submit_operation(
    *,
    source: rpki_models.IrrSource,
    method: str,
    object_texts: list[str],
    delete_reason: str | None = None,
) -> dict:
    body = {
        'objects': [{'object_text': object_text} for object_text in object_texts],
        'override': source.api_key,
    }
    if delete_reason:
        body['delete_reason'] = delete_reason
    return {
        'method': method,
        'url': _submit_url(source),
        'body': body,
    }


def _submit_url(source: rpki_models.IrrSource) -> str:
    base_url = (source.query_base_url or '').rstrip('/')
    return f'{base_url}/v1/submit/'


def _submit_irrd_operation(source: rpki_models.IrrSource, operation: dict) -> dict:
    request = Request(
        operation['url'],
        data=json.dumps(operation['body']).encode('utf-8'),
        headers={
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        method=operation['method'],
    )
    _add_basic_auth(
        request,
        username=source.http_username or None,
        password=source.http_password or None,
    )
    emit_structured_log(
        'irr_write.submit.start',
        subsystem='irr_write',
        debug=True,
        irr_source_id=source.pk,
        irr_source_name=source.name,
        method=operation['method'],
        url=operation['url'],
        headers=dict(request.header_items()),
        request_body=operation['body'],
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw_body = response.read().decode('utf-8').strip()
    except HTTPError as exc:
        error_body = exc.read().decode('utf-8', errors='replace')
        emit_structured_log(
            'irr_write.submit.error',
            subsystem='irr_write',
            level='warning',
            irr_source_id=source.pk,
            irr_source_name=source.name,
            method=operation['method'],
            url=operation['url'],
            error=error_body or str(exc),
            error_type=type(exc).__name__,
            http_status=exc.code,
        )
        return {
            'http_status': exc.code,
            'error': error_body or str(exc),
        }
    except URLError as exc:
        emit_structured_log(
            'irr_write.submit.error',
            subsystem='irr_write',
            level='warning',
            irr_source_id=source.pk,
            irr_source_name=source.name,
            method=operation['method'],
            url=operation['url'],
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise IrrWriteExecutionError(f'IRRd submit request failed: {exc}') from exc

    if not raw_body:
        emit_structured_log(
            'irr_write.submit.success',
            subsystem='irr_write',
            debug=True,
            irr_source_id=source.pk,
            irr_source_name=source.name,
            method=operation['method'],
            url=operation['url'],
            response_body={},
        )
        return {}
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        emit_structured_log(
            'irr_write.submit.success',
            subsystem='irr_write',
            debug=True,
            irr_source_id=source.pk,
            irr_source_name=source.name,
            method=operation['method'],
            url=operation['url'],
            response_body=raw_body,
        )
        return {'raw': raw_body}
    emit_structured_log(
        'irr_write.submit.success',
        subsystem='irr_write',
        debug=True,
        irr_source_id=source.pk,
        irr_source_name=source.name,
        method=operation['method'],
        url=operation['url'],
        response_body=payload,
    )
    if isinstance(payload, dict):
        return payload
    return {'raw': payload}


def _operation_succeeded(response_payload: dict) -> bool:
    if response_payload.get('http_status', 200) >= 400:
        return False
    summary = response_payload.get('summary')
    if isinstance(summary, dict):
        return not summary.get('failed')
    return 'error' not in response_payload


def _extract_error_messages(response_payload: dict) -> list[str]:
    if response_payload.get('error'):
        return [str(response_payload['error'])]
    messages: list[str] = []
    for obj in response_payload.get('objects', []) if isinstance(response_payload.get('objects'), list) else []:
        for message in obj.get('error_messages', []) or []:
            messages.append(str(message))
    if not messages and isinstance(response_payload.get('summary'), dict) and response_payload['summary'].get('failed'):
        messages.append('IRRd reported one or more failed object submissions.')
    return messages


def _update_plan_latest_execution(plan: rpki_models.IrrChangePlan, execution: rpki_models.IrrWriteExecution) -> None:
    summary_json = dict(plan.summary_json or {})
    summary_json['latest_execution'] = {
        'id': execution.pk,
        'mode': execution.execution_mode,
        'status': execution.status,
        'completed_at': execution.completed_at.isoformat() if execution.completed_at else None,
        'error': execution.error,
    }
    summary_json['previewable'] = bool(plan.supports_preview and plan.items.exclude(action=rpki_models.IrrChangePlanAction.NOOP).exists())
    summary_json['applyable'] = bool(plan.supports_apply and plan.items.exclude(action=rpki_models.IrrChangePlanAction.NOOP).exists())
    plan.summary_json = summary_json
    plan.save(update_fields=('summary_json',))


def _add_basic_auth(request: Request, *, username: str | None = None, password: str | None = None) -> None:
    if not username:
        return
    token = base64.b64encode(f'{username}:{password or ""}'.encode('utf-8')).decode('ascii')
    request.add_header('Authorization', f'Basic {token}')


def result_key_for_route(*, prefix: str, origin_asn: str) -> str:
    object_class = 'route6' if ':' in prefix else 'route'
    return f'{object_class}:{prefix}{origin_asn.upper()}'
