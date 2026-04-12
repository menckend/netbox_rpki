from __future__ import annotations

from django.utils import timezone

from netbox_rpki import models as rpki_models


def _normalize_plan(plan: rpki_models.ROAChangePlan | int) -> rpki_models.ROAChangePlan:
    if isinstance(plan, rpki_models.ROAChangePlan):
        return plan
    return rpki_models.ROAChangePlan.objects.get(pk=plan)


def _simulate_plan_item(
    item: rpki_models.ROAChangePlanItem,
) -> tuple[str, dict]:
    semantic = item.plan_semantic or item.action_type
    after_state = dict(item.after_state_json or {})
    before_state = dict(item.before_state_json or {})

    details = {
        'action_type': item.action_type,
        'plan_semantic': semantic,
        'before_state': before_state,
        'after_state': after_state,
        'reason': item.reason,
        'provider_operation': item.provider_operation,
    }

    if item.action_type == rpki_models.ROAChangePlanAction.CREATE:
        if after_state.get('prefix_cidr_text') and after_state.get('origin_asn_value') is not None:
            details['explanation'] = 'Planned authorization should produce a valid outcome for the intended route.'
            return rpki_models.ROAValidationSimulationOutcome.VALID, details
        details['explanation'] = 'Create action is missing enough target state to project a valid authorization outcome.'
        return rpki_models.ROAValidationSimulationOutcome.INVALID, details

    if semantic in {
        rpki_models.ROAChangePlanItemSemantic.REPLACE,
        rpki_models.ROAChangePlanItemSemantic.RESHAPE,
    } and after_state.get('prefix_cidr_text'):
        details['explanation'] = 'Withdrawal is paired with a replacement target, so the intended route should remain valid.'
        return rpki_models.ROAValidationSimulationOutcome.VALID, details

    details['explanation'] = 'Withdrawal removes authorization without a replacement target, leading to a predicted not-found outcome.'
    return rpki_models.ROAValidationSimulationOutcome.NOT_FOUND, details


def simulate_roa_change_plan(
    plan: rpki_models.ROAChangePlan | int,
    *,
    run_name: str | None = None,
) -> rpki_models.ROAValidationSimulationRun:
    plan = _normalize_plan(plan)
    now = timezone.now()
    simulation_run = rpki_models.ROAValidationSimulationRun.objects.create(
        name=run_name or f'{plan.name} Simulation {now:%Y-%m-%d %H:%M:%S}',
        change_plan=plan,
        tenant=plan.tenant,
        status=rpki_models.ValidationRunStatus.RUNNING,
        started_at=now,
    )

    outcome_counts = {
        rpki_models.ROAValidationSimulationOutcome.VALID: 0,
        rpki_models.ROAValidationSimulationOutcome.INVALID: 0,
        rpki_models.ROAValidationSimulationOutcome.NOT_FOUND: 0,
    }
    semantic_counts: dict[str, int] = {}

    for item in plan.items.all():
        outcome_type, details = _simulate_plan_item(item)
        rpki_models.ROAValidationSimulationResult.objects.create(
            name=f'{item.name} Simulation',
            simulation_run=simulation_run,
            tenant=plan.tenant,
            change_plan_item=item,
            outcome_type=outcome_type,
            details_json=details,
            computed_at=timezone.now(),
        )
        outcome_counts[outcome_type] = outcome_counts.get(outcome_type, 0) + 1
        semantic_key = item.plan_semantic or item.action_type
        semantic_counts[semantic_key] = semantic_counts.get(semantic_key, 0) + 1

    simulation_run.status = rpki_models.ValidationRunStatus.COMPLETED
    simulation_run.completed_at = timezone.now()
    simulation_run.result_count = sum(outcome_counts.values())
    simulation_run.predicted_valid_count = outcome_counts[rpki_models.ROAValidationSimulationOutcome.VALID]
    simulation_run.predicted_invalid_count = outcome_counts[rpki_models.ROAValidationSimulationOutcome.INVALID]
    simulation_run.predicted_not_found_count = outcome_counts[rpki_models.ROAValidationSimulationOutcome.NOT_FOUND]
    simulation_run.summary_json = {
        'predicted_outcome_counts': outcome_counts,
        'plan_semantic_counts': semantic_counts,
        'comparison_scope': plan.source_reconciliation_run.comparison_scope,
        'provider_backed': plan.is_provider_backed,
        'change_plan_id': plan.pk,
    }
    simulation_run.save(
        update_fields=(
            'status',
            'completed_at',
            'result_count',
            'predicted_valid_count',
            'predicted_invalid_count',
            'predicted_not_found_count',
            'summary_json',
        )
    )
    return simulation_run
