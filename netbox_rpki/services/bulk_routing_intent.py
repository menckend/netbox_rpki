from __future__ import annotations

import hashlib

from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.routing_intent import (
    RoutingIntentExecutionError,
    run_routing_intent_pipeline,
    run_routing_intent_template_binding_pipeline,
    create_roa_change_plan,
)


def _resolve_target_mode(profile_targets, binding_targets) -> str:
    if profile_targets and binding_targets:
        return rpki_models.BulkIntentTargetMode.MIXED
    if profile_targets:
        return rpki_models.BulkIntentTargetMode.PROFILES
    return rpki_models.BulkIntentTargetMode.BINDINGS


def _ensure_single_organization(
    *,
    organization: rpki_models.Organization | None,
    profiles: tuple[rpki_models.RoutingIntentProfile, ...],
    bindings: tuple[rpki_models.RoutingIntentTemplateBinding, ...],
):
    organization_ids = {
        profile.organization_id
        for profile in profiles
    } | {
        binding.intent_profile.organization_id
        for binding in bindings
    }
    if organization is not None:
        organization_ids.add(organization.pk)

    if not organization_ids:
        raise RoutingIntentExecutionError('Bulk routing-intent execution requires at least one profile or template binding target.')
    if len(organization_ids) != 1:
        raise RoutingIntentExecutionError('All bulk routing-intent targets must belong to the same organization.')

    if organization is not None:
        return organization
    organization_id = next(iter(organization_ids))
    return rpki_models.Organization.objects.get(pk=organization_id)


def _build_fingerprint(parts: list[str]) -> str:
    payload = '|'.join(parts)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def build_bulk_routing_intent_baseline_fingerprint(
    *,
    profiles: tuple[rpki_models.RoutingIntentProfile | int, ...] | None = None,
    bindings: tuple[rpki_models.RoutingIntentTemplateBinding | int, ...] | None = None,
    comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
    provider_snapshot: rpki_models.ProviderSnapshot | int | None = None,
    create_change_plans: bool = False,
) -> str:
    profile_targets = tuple(profiles or ())
    binding_targets = tuple(bindings or ())
    baseline_parts = [
        f'comparison_scope:{comparison_scope}',
        f'provider_snapshot:{getattr(provider_snapshot, "pk", provider_snapshot) or ""}',
        f'create_change_plans:{create_change_plans}',
        *[f'profile:{getattr(profile, "pk", profile)}' for profile in profile_targets],
        *[f'binding:{getattr(binding, "pk", binding)}' for binding in binding_targets],
    ]
    return _build_fingerprint(baseline_parts)


def run_bulk_routing_intent_pipeline(
    *,
    organization: rpki_models.Organization | None = None,
    profiles: tuple[rpki_models.RoutingIntentProfile, ...] | None = None,
    bindings: tuple[rpki_models.RoutingIntentTemplateBinding, ...] | None = None,
    trigger_mode: str = rpki_models.IntentRunTriggerMode.MANUAL,
    comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
    provider_snapshot: rpki_models.ProviderSnapshot | int | None = None,
    create_change_plans: bool = False,
    run_name: str | None = None,
) -> rpki_models.BulkIntentRun:
    profile_targets = tuple(profiles or ())
    binding_targets = tuple(bindings or ())
    resolved_organization = _ensure_single_organization(
        organization=organization,
        profiles=profile_targets,
        bindings=binding_targets,
    )
    if provider_snapshot is not None and getattr(provider_snapshot, 'organization_id', resolved_organization.pk) != resolved_organization.pk:
        raise RoutingIntentExecutionError('Provider snapshot must belong to the same organization as the bulk targets.')

    now = timezone.now()
    target_mode = _resolve_target_mode(profile_targets, binding_targets)
    bulk_run = rpki_models.BulkIntentRun.objects.create(
        name=run_name or f'Bulk Intent Run {now:%Y-%m-%d %H:%M:%S}',
        organization=resolved_organization,
        status=rpki_models.ValidationRunStatus.RUNNING,
        trigger_mode=trigger_mode,
        target_mode=target_mode,
        baseline_fingerprint=build_bulk_routing_intent_baseline_fingerprint(
            profiles=profile_targets,
            bindings=binding_targets,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot,
            create_change_plans=create_change_plans,
        ),
        started_at=now,
        summary_json={
            'comparison_scope': comparison_scope,
            'provider_snapshot_id': getattr(provider_snapshot, 'pk', provider_snapshot),
            'create_change_plans': create_change_plans,
            'profile_target_count': len(profile_targets),
            'binding_target_count': len(binding_targets),
            'scope_result_count': 0,
            'change_plan_count': 0,
            'failed_scope_count': 0,
        },
    )

    result_fingerprint_parts = []
    scope_results = []
    failed_scope_count = 0
    change_plan_count = 0

    try:
        for profile in profile_targets:
            derivation_run, reconciliation_run = run_routing_intent_pipeline(
                profile,
                trigger_mode=trigger_mode,
                comparison_scope=comparison_scope,
                provider_snapshot=provider_snapshot,
            )
            change_plan = create_roa_change_plan(reconciliation_run) if create_change_plans else None
            if change_plan is not None:
                change_plan_count += 1
            scope_result = rpki_models.BulkIntentRunScopeResult.objects.create(
                name=f'Profile {profile.name}',
                bulk_run=bulk_run,
                intent_profile=profile,
                status=rpki_models.ValidationRunStatus.COMPLETED,
                scope_kind='profile',
                scope_key=f'profile:{profile.pk}',
                derivation_run=derivation_run,
                reconciliation_run=reconciliation_run,
                change_plan=change_plan,
                prefix_count_scanned=derivation_run.prefix_count_scanned,
                intent_count_emitted=derivation_run.intent_count_emitted,
                plan_item_count=change_plan.items.count() if change_plan is not None else 0,
                summary_json={
                    'comparison_scope': comparison_scope,
                    'provider_snapshot_id': getattr(provider_snapshot, 'pk', provider_snapshot),
                    'warning_count': derivation_run.warning_count,
                    'reconciliation_status': reconciliation_run.status,
                    'change_plan_id': getattr(change_plan, 'pk', None),
                },
            )
            scope_results.append(scope_result)
            result_fingerprint_parts.append(derivation_run.input_fingerprint)

        for binding in binding_targets:
            derivation_run, reconciliation_run = run_routing_intent_template_binding_pipeline(
                binding,
                trigger_mode=trigger_mode,
                comparison_scope=comparison_scope,
                provider_snapshot=provider_snapshot,
            )
            change_plan = create_roa_change_plan(reconciliation_run) if create_change_plans else None
            if change_plan is not None:
                change_plan_count += 1
            scope_result = rpki_models.BulkIntentRunScopeResult.objects.create(
                name=f'Binding {binding.name}',
                bulk_run=bulk_run,
                intent_profile=binding.intent_profile,
                template_binding=binding,
                status=rpki_models.ValidationRunStatus.COMPLETED,
                scope_kind='binding',
                scope_key=f'binding:{binding.pk}',
                derivation_run=derivation_run,
                reconciliation_run=reconciliation_run,
                change_plan=change_plan,
                prefix_count_scanned=derivation_run.prefix_count_scanned,
                intent_count_emitted=derivation_run.intent_count_emitted,
                plan_item_count=change_plan.items.count() if change_plan is not None else 0,
                summary_json={
                    'comparison_scope': comparison_scope,
                    'provider_snapshot_id': getattr(provider_snapshot, 'pk', provider_snapshot),
                    'warning_count': derivation_run.warning_count,
                    'reconciliation_status': reconciliation_run.status,
                    'change_plan_id': getattr(change_plan, 'pk', None),
                    'binding_fingerprint': binding.last_compiled_fingerprint,
                },
            )
            scope_results.append(scope_result)
            result_fingerprint_parts.append(derivation_run.input_fingerprint)
    except Exception as exc:
        failed_scope_count += 1
        bulk_run.status = rpki_models.ValidationRunStatus.FAILED
        bulk_run.completed_at = timezone.now()
        bulk_run.summary_json = {
            **(bulk_run.summary_json or {}),
            'scope_result_count': len(scope_results),
            'change_plan_count': change_plan_count,
            'failed_scope_count': failed_scope_count,
            'error': str(exc),
        }
        bulk_run.save(update_fields=('status', 'completed_at', 'summary_json'))
        raise

    bulk_run.status = rpki_models.ValidationRunStatus.COMPLETED
    bulk_run.completed_at = timezone.now()
    bulk_run.resulting_fingerprint = _build_fingerprint(result_fingerprint_parts)
    bulk_run.summary_json = {
        **(bulk_run.summary_json or {}),
        'scope_result_count': len(scope_results),
        'change_plan_count': change_plan_count,
        'failed_scope_count': failed_scope_count,
        'completed_scope_keys': [scope.scope_key for scope in scope_results],
    }
    bulk_run.save(update_fields=('status', 'completed_at', 'resulting_fingerprint', 'summary_json'))
    return bulk_run
