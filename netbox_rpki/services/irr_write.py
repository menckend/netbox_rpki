from __future__ import annotations

from collections import Counter

from django.db import transaction
from django.utils import timezone

from netbox_rpki import models as rpki_models


class IrrChangePlanError(ValueError):
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
        if item.action == rpki_models.IrrChangePlanAction.NOOP and result.result_type in ACTIONABLE_RESULT_TYPES:
            capability_warnings.append(
                f'{result.coordination_family} change {result.stable_object_key or result.name} is blocked by source write capability.'
            )

    summary_json = _build_plan_summary(
        plan=plan,
        item_counts=item_counts,
        family_counts=family_counts,
        capability_warnings=capability_warnings,
    )
    plan.summary_json = summary_json
    plan.save(update_fields=('summary_json',))
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
    if result.imported_route_object_id is not None:
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


def result_key_for_route(*, prefix: str, origin_asn: str) -> str:
    object_class = 'route6' if ':' in prefix else 'route'
    return f'{object_class}:{prefix}{origin_asn.upper()}'
