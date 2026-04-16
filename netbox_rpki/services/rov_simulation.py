from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from django.utils import timezone
from netaddr import AddrFormatError, IPNetwork

from netbox_rpki import models as rpki_models

SIMULATION_APPROVAL_IMPACT_INFORMATIONAL = rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL
SIMULATION_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED = (
    rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED
)
SIMULATION_APPROVAL_IMPACT_BLOCKING = rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING
SIMULATION_OUTCOME_VALID = rpki_models.ROAValidationSimulationOutcome.VALID
SIMULATION_OUTCOME_INVALID = rpki_models.ROAValidationSimulationOutcome.INVALID
SIMULATION_OUTCOME_NOT_FOUND = rpki_models.ROAValidationSimulationOutcome.NOT_FOUND

SIMULATION_OUTCOME_LABELS = {
    SIMULATION_OUTCOME_VALID: "Valid",
    SIMULATION_OUTCOME_INVALID: "Invalid",
    SIMULATION_OUTCOME_NOT_FOUND: "Not Found",
}


@dataclass(slots=True)
class AuthorizationFact:
    prefix_cidr_text: str
    origin_asn_value: int | None
    max_length: int | None
    source: str
    source_id: int | None = None

    @property
    def network(self) -> IPNetwork | None:
        try:
            return IPNetwork(self.prefix_cidr_text)
        except (AddrFormatError, TypeError, ValueError):
            return None

    @property
    def prefix_length(self) -> int | None:
        network = self.network
        return None if network is None else network.prefixlen


@dataclass(slots=True)
class PlanSimulationContext:
    plan_id: int
    plan_fingerprint: str
    comparison_scope: str
    provider_backed: bool
    before_authorizations: list[AuthorizationFact]
    after_authorizations: list[AuthorizationFact]


@dataclass(slots=True)
class SimulationScenario:
    scenario_type: str
    intended_fact: AuthorizationFact | None
    before_fact: AuthorizationFact | None
    after_fact: AuthorizationFact | None
    collateral_impact_count: int = 0
    impact_scope: str = 'unknown'
    transition_risk: str = 'none'
    explanation: str = ''


@dataclass(slots=True)
class ClassifiedSimulationResult:
    outcome_type: str
    approval_impact: str
    scenario_type: str
    operator_message: str
    operator_action: str
    why_it_matters: str
    details_json: dict


def _normalize_plan(plan: rpki_models.ROAChangePlan | int) -> rpki_models.ROAChangePlan:
    if isinstance(plan, rpki_models.ROAChangePlan):
        return plan
    return rpki_models.ROAChangePlan.objects.select_related('source_reconciliation_run').get(pk=plan)


def _canonical_json(value) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(',', ':'))


def _build_plan_fingerprint(plan: rpki_models.ROAChangePlan) -> str:
    item_rows = []
    for item in plan.items.order_by('pk'):
        item_rows.append({
            'pk': item.pk,
            'action_type': item.action_type,
            'plan_semantic': item.plan_semantic,
            'before_state_json': item.before_state_json or {},
            'after_state_json': item.after_state_json or {},
            'provider_operation': item.provider_operation,
        })
    payload = {
        'plan_pk': plan.pk,
        'items': item_rows,
    }
    return hashlib.sha256(_canonical_json(payload).encode('utf-8')).hexdigest()


def normalize_roa_validation_simulation_run_summary(
    run: rpki_models.ROAValidationSimulationRun,
) -> dict:
    summary = dict(run.summary_json or {})
    summary.setdefault('plan_fingerprint', run.plan_fingerprint)
    summary.setdefault('overall_approval_posture', run.overall_approval_posture)
    summary.setdefault('is_current_for_plan', run.is_current_for_plan)
    summary.setdefault('partially_constrained', run.partially_constrained)
    summary.setdefault('predicted_outcome_counts', {
        SIMULATION_OUTCOME_VALID: run.predicted_valid_count,
        SIMULATION_OUTCOME_INVALID: run.predicted_invalid_count,
        SIMULATION_OUTCOME_NOT_FOUND: run.predicted_not_found_count,
    })
    return summary


def normalize_roa_validation_simulation_result_details(
    result: rpki_models.ROAValidationSimulationResult,
) -> dict:
    details = dict(result.details_json or {})
    details.setdefault('approval_impact', result.approval_impact)
    details.setdefault('scenario_type', result.scenario_type)
    details.setdefault('affected_prefixes', [])
    details.setdefault('affected_origin_asns', [])
    return details


def _get_change_plan_simulation_run(
    plan: rpki_models.ROAChangePlan,
) -> rpki_models.ROAValidationSimulationRun | None:
    simulation_runs = plan.simulation_runs.prefetch_related('results__change_plan_item')
    simulation_run_id = (plan.summary_json or {}).get('simulation_run_id')
    if simulation_run_id:
        simulation_run = simulation_runs.filter(pk=simulation_run_id).first()
        if simulation_run is not None:
            return simulation_run
    return simulation_runs.order_by('-started_at', '-created').first()


def _serialize_simulation_result_review(
    result: rpki_models.ROAValidationSimulationResult,
) -> dict:
    details = normalize_roa_validation_simulation_result_details(result)
    change_plan_item = result.change_plan_item
    return {
        'id': result.pk,
        'name': result.name,
        'object_url': result.get_absolute_url(),
        'approval_impact': details.get('approval_impact'),
        'scenario_type': details.get('scenario_type'),
        'impact_scope': details.get('impact_scope'),
        'operator_message': details.get('operator_message'),
        'why_it_matters': details.get('why_it_matters'),
        'operator_action': details.get('operator_action'),
        'affected_prefixes': [str(prefix) for prefix in details.get('affected_prefixes') or []],
        'affected_origin_asns': [str(asn) for asn in details.get('affected_origin_asns') or []],
        'change_plan_item': None if change_plan_item is None else {
            'id': change_plan_item.pk,
            'name': str(change_plan_item),
            'object_url': change_plan_item.get_absolute_url(),
        },
    }


def build_roa_change_plan_simulation_review(
    plan: rpki_models.ROAChangePlan | int,
) -> dict | None:
    plan = _normalize_plan(plan)
    simulation_run = _get_change_plan_simulation_run(plan)
    if simulation_run is None:
        return None

    summary = normalize_roa_validation_simulation_run_summary(simulation_run)
    grouped_results = {
        SIMULATION_OUTCOME_VALID: {
            'label': SIMULATION_OUTCOME_LABELS[SIMULATION_OUTCOME_VALID],
            'count': 0,
            'results': [],
        },
        SIMULATION_OUTCOME_INVALID: {
            'label': SIMULATION_OUTCOME_LABELS[SIMULATION_OUTCOME_INVALID],
            'count': 0,
            'results': [],
        },
        SIMULATION_OUTCOME_NOT_FOUND: {
            'label': SIMULATION_OUTCOME_LABELS[SIMULATION_OUTCOME_NOT_FOUND],
            'count': 0,
            'results': [],
        },
    }

    for result in simulation_run.results.all():
        outcome_type = result.outcome_type or SIMULATION_OUTCOME_NOT_FOUND
        group = grouped_results.setdefault(
            outcome_type,
            {'label': outcome_type.replace('_', ' ').title(), 'count': 0, 'results': []},
        )
        group['results'].append(_serialize_simulation_result_review(result))
        group['count'] += 1

    return {
        'run': {
            'id': simulation_run.pk,
            'name': str(simulation_run),
            'object_url': simulation_run.get_absolute_url(),
            'status': simulation_run.status,
        },
        'plan_fingerprint': summary.get('plan_fingerprint'),
        'overall_approval_posture': summary.get('overall_approval_posture'),
        'is_current_for_plan': summary.get('is_current_for_plan'),
        'partially_constrained': summary.get('partially_constrained'),
        'predicted_outcome_counts': summary.get('predicted_outcome_counts') or {},
        'approval_impact_counts': summary.get('approval_impact_counts') or {},
        'grouped_results': grouped_results,
    }


def _extract_authorization_fact(
    state: dict,
    *,
    fallback_source: str,
    source_id: int | None = None,
) -> AuthorizationFact | None:
    prefix_cidr_text = state.get('prefix_cidr_text') or state.get('prefix')
    origin_asn_value = state.get('origin_asn_value')
    if origin_asn_value is None:
        origin_asn_value = state.get('asn')
    max_length = state.get('max_length')
    if max_length is None:
        max_length = state.get('max_length_value')
    source = state.get('source') or fallback_source
    if not prefix_cidr_text:
        return None
    return AuthorizationFact(
        prefix_cidr_text=prefix_cidr_text,
        origin_asn_value=origin_asn_value,
        max_length=max_length,
        source=source,
        source_id=source_id,
    )


def _dedupe_authorizations(facts: list[AuthorizationFact]) -> list[AuthorizationFact]:
    seen = set()
    result = []
    for fact in facts:
        key = (
            fact.prefix_cidr_text,
            fact.origin_asn_value,
            fact.max_length,
            fact.source,
            fact.source_id,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(fact)
    return result


def _build_plan_simulation_context(plan: rpki_models.ROAChangePlan) -> PlanSimulationContext:
    fingerprint = _build_plan_fingerprint(plan)
    before_authorizations = []
    after_authorizations = []
    for item in plan.items.select_related('roa_intent').order_by('pk'):
        before_fact = _extract_authorization_fact(
            dict(item.before_state_json or {}),
            fallback_source='before_state',
            source_id=item.pk,
        )
        after_fact = _extract_authorization_fact(
            dict(item.after_state_json or {}),
            fallback_source='after_state',
            source_id=item.pk,
        )
        if before_fact is not None:
            before_authorizations.append(before_fact)
        if after_fact is not None:
            after_authorizations.append(after_fact)
        if item.roa_intent_id and after_fact is None:
            after_authorizations.append(AuthorizationFact(
                prefix_cidr_text=item.roa_intent.prefix_cidr_text,
                origin_asn_value=item.roa_intent.origin_asn_value,
                max_length=item.roa_intent.max_length,
                source='roa_intent',
                source_id=item.roa_intent_id,
            ))
    return PlanSimulationContext(
        plan_id=plan.pk,
        plan_fingerprint=fingerprint,
        comparison_scope=plan.source_reconciliation_run.comparison_scope,
        provider_backed=plan.is_provider_backed,
        before_authorizations=_dedupe_authorizations(before_authorizations),
        after_authorizations=_dedupe_authorizations(after_authorizations),
    )


def _covers(target: AuthorizationFact, authorization: AuthorizationFact) -> bool:
    if target.origin_asn_value is None or authorization.origin_asn_value != target.origin_asn_value:
        return False
    target_network = target.network
    authorization_network = authorization.network
    if target_network is None or authorization_network is None:
        return False
    if target_network.version != authorization_network.version:
        return False
    if target_network.first < authorization_network.first or target_network.last > authorization_network.last:
        return False
    if authorization.max_length is None:
        return target_network.prefixlen == authorization_network.prefixlen
    return target_network.prefixlen <= authorization.max_length


def _matching_authorizations(
    target: AuthorizationFact | None,
    authorizations: list[AuthorizationFact],
) -> list[AuthorizationFact]:
    if target is None:
        return []
    return [authorization for authorization in authorizations if _covers(target, authorization)]


def _is_broader_authorization(before_fact: AuthorizationFact | None, after_fact: AuthorizationFact | None) -> bool:
    if after_fact is None:
        return False
    after_network = after_fact.network
    if after_network is None or after_fact.origin_asn_value is None:
        return False
    if after_fact.max_length is not None and after_fact.max_length > after_network.prefixlen:
        return True
    if before_fact is None or before_fact.origin_asn_value != after_fact.origin_asn_value:
        return False
    before_network = before_fact.network
    if before_network is None or before_fact.max_length is None and after_fact.max_length is None:
        return False
    if after_network.first <= before_network.first and after_network.last >= before_network.last:
        if after_network.prefixlen < before_network.prefixlen:
            return True
        before_max_length = before_fact.max_length or before_network.prefixlen
        after_max_length = after_fact.max_length or after_network.prefixlen
        return after_max_length > before_max_length
    return False


def _collateral_impact_count(before_fact: AuthorizationFact | None, after_fact: AuthorizationFact | None) -> int:
    if before_fact is None:
        return 0
    before_prefix_length = before_fact.prefix_length
    if before_prefix_length is None:
        return 0
    before_max_length = before_fact.max_length or before_prefix_length
    after_prefix_length = after_fact.prefix_length if after_fact is not None else None
    after_max_length = (
        after_fact.max_length or after_prefix_length
        if after_fact is not None and after_prefix_length is not None
        else before_prefix_length
    )
    if after_fact is None:
        return max(0, before_max_length - before_prefix_length)
    if before_fact.origin_asn_value != after_fact.origin_asn_value:
        return max(0, before_max_length - before_prefix_length)
    return max(0, before_max_length - after_max_length)


def _build_intended_fact(item: rpki_models.ROAChangePlanItem) -> AuthorizationFact | None:
    after_state = dict(item.after_state_json or {})
    before_state = dict(item.before_state_json or {})
    fact = _extract_authorization_fact(after_state, fallback_source='after_state', source_id=item.pk)
    if fact is not None:
        return fact
    if item.roa_intent_id:
        return AuthorizationFact(
            prefix_cidr_text=item.roa_intent.prefix_cidr_text,
            origin_asn_value=item.roa_intent.origin_asn_value,
            max_length=item.roa_intent.max_length,
            source='roa_intent',
            source_id=item.roa_intent_id,
        )
    return _extract_authorization_fact(before_state, fallback_source='before_state', source_id=item.pk)


def _build_plan_item_scenarios(
    item: rpki_models.ROAChangePlanItem,
    context: PlanSimulationContext,
) -> list[SimulationScenario]:
    before_state = dict(item.before_state_json or {})
    after_state = dict(item.after_state_json or {})
    semantic = item.plan_semantic or item.action_type
    intended_fact = _build_intended_fact(item)
    before_fact = _extract_authorization_fact(before_state, fallback_source='before_state', source_id=item.pk)
    after_fact = _extract_authorization_fact(after_state, fallback_source='after_state', source_id=item.pk)

    scenarios: list[SimulationScenario] = []

    if intended_fact is None or intended_fact.origin_asn_value is None:
        scenarios.append(SimulationScenario(
            scenario_type='insufficient_state_requires_review',
            intended_fact=intended_fact,
            before_fact=before_fact,
            after_fact=after_fact,
            impact_scope='unknown',
            transition_risk='ambiguous_state',
            explanation='The plan item does not carry enough normalized authorization state for confident simulation.',
        ))
        return scenarios

    if item.action_type == rpki_models.ROAChangePlanAction.CREATE and (
        not after_state.get('prefix_cidr_text') or after_state.get('origin_asn_value') is None
    ):
        scenarios.append(SimulationScenario(
            scenario_type='insufficient_state_requires_review',
            intended_fact=intended_fact,
            before_fact=before_fact,
            after_fact=after_fact,
            impact_scope='unknown',
            transition_risk='ambiguous_state',
            explanation='Create action is missing required target authorization fields.',
        ))
        return scenarios

    if semantic in {
        rpki_models.ROAChangePlanItemSemantic.REPLACE,
        rpki_models.ROAChangePlanItemSemantic.RESHAPE,
    } and after_fact is not None:
        collateral_impact_count = _collateral_impact_count(before_fact, after_fact)
        if _is_broader_authorization(before_fact, after_fact):
            scenarios.append(SimulationScenario(
                scenario_type='replacement_broadens_authorization',
                intended_fact=intended_fact,
                before_fact=before_fact,
                after_fact=after_fact,
                collateral_impact_count=max(1, collateral_impact_count),
                impact_scope='intended_and_collateral',
                transition_risk='coverage_broadened',
                explanation='The replacement preserves intended coverage but broadens authorization scope.',
            ))
        elif collateral_impact_count > 0:
            scenarios.append(SimulationScenario(
                scenario_type=(
                    'reshape_drops_specific_coverage'
                    if semantic == rpki_models.ROAChangePlanItemSemantic.RESHAPE
                    else 'withdraw_removes_unrelated_coverage'
                ),
                intended_fact=intended_fact,
                before_fact=before_fact,
                after_fact=after_fact,
                collateral_impact_count=collateral_impact_count,
                impact_scope='intended_and_collateral',
                transition_risk='coverage_loss',
                explanation='The reshape narrows authorization and may drop coverage for more specific routes.',
            ))
        else:
            scenarios.append(SimulationScenario(
                scenario_type='replacement_preserves_coverage',
                intended_fact=intended_fact,
                before_fact=before_fact,
                after_fact=after_fact,
                impact_scope='intended_only',
                explanation='The replacement keeps an authorization for the intended route.',
            ))
        return scenarios

    if item.action_type == rpki_models.ROAChangePlanAction.WITHDRAW and after_fact is None:
        collateral_impact_count = _collateral_impact_count(before_fact, after_fact)
        if item.roa_intent_id:
            scenarios.append(SimulationScenario(
                scenario_type='withdraw_without_replacement_not_found',
                intended_fact=intended_fact,
                before_fact=before_fact,
                after_fact=after_fact,
                impact_scope='intended_only',
                transition_risk='coverage_loss',
                explanation='The withdraw removes authorization for the intended route without a replacement.',
            ))
        elif collateral_impact_count > 0:
            scenarios.append(SimulationScenario(
                scenario_type='withdraw_removes_unrelated_coverage',
                intended_fact=intended_fact,
                before_fact=before_fact,
                after_fact=after_fact,
                collateral_impact_count=collateral_impact_count,
                impact_scope='collateral_only',
                transition_risk='coverage_loss',
                explanation='The withdraw removes a broader authorization that may still cover more specific routes.',
            ))
        else:
            scenarios.append(SimulationScenario(
                scenario_type='exact_create_validates',
                intended_fact=intended_fact,
                before_fact=before_fact,
                after_fact=after_fact,
                impact_scope='intended_only',
                explanation='The withdraw removes an authorization with no modeled collateral impact.',
            ))
        return scenarios

    if _is_broader_authorization(before_fact, after_fact):
        scenarios.append(SimulationScenario(
            scenario_type='replacement_broadens_authorization',
            intended_fact=intended_fact,
            before_fact=before_fact,
            after_fact=after_fact,
            collateral_impact_count=max(1, _collateral_impact_count(before_fact, after_fact)),
            impact_scope='intended_and_collateral',
            transition_risk='coverage_broadened',
            explanation='The authorization remains valid but broader than the intended route specification.',
        ))
    else:
        scenarios.append(SimulationScenario(
            scenario_type='exact_create_validates',
            intended_fact=intended_fact,
            before_fact=before_fact,
            after_fact=after_fact,
            impact_scope='intended_only',
            explanation='The planned authorization should validate the intended route.',
        ))
    return scenarios


def _scenario_priority(scenario: SimulationScenario) -> tuple[int, int]:
    if scenario.scenario_type in {'withdraw_without_replacement_not_found', 'reshape_drops_specific_coverage'}:
        return (0, 0)
    if scenario.scenario_type in {'replacement_broadens_authorization', 'withdraw_removes_unrelated_coverage'}:
        return (1, -scenario.collateral_impact_count)
    if scenario.scenario_type == 'insufficient_state_requires_review':
        return (2, 0)
    return (3, 0)


def _build_coverage_summary(matches: list[AuthorizationFact], target: AuthorizationFact | None) -> dict:
    return {
        'matching_authorization_count': len(matches),
        'covers_intended_route': bool(matches) if target is not None else False,
        'matched_authorizations': [
            {
                'prefix_cidr_text': match.prefix_cidr_text,
                'origin_asn_value': match.origin_asn_value,
                'max_length': match.max_length,
                'source': match.source,
            }
            for match in matches
        ],
    }


def _classify_plan_item_scenarios(
    item: rpki_models.ROAChangePlanItem,
    scenarios: list[SimulationScenario],
    context: PlanSimulationContext,
) -> ClassifiedSimulationResult:
    scenario = sorted(scenarios, key=_scenario_priority)[0]
    intended_fact = scenario.intended_fact
    before_matches = _matching_authorizations(intended_fact, context.before_authorizations)
    after_matches = _matching_authorizations(intended_fact, context.after_authorizations)

    outcome_type = rpki_models.ROAValidationSimulationOutcome.VALID
    approval_impact = SIMULATION_APPROVAL_IMPACT_INFORMATIONAL
    operator_message = 'The intended route should remain valid after the plan is applied.'
    why_it_matters = 'The simulated authorization set still covers the intended route.'
    operator_action = 'Review the simulation details and continue with normal approval.'

    if scenario.scenario_type == 'withdraw_without_replacement_not_found':
        outcome_type = rpki_models.ROAValidationSimulationOutcome.NOT_FOUND
        approval_impact = SIMULATION_APPROVAL_IMPACT_BLOCKING
        operator_message = 'The intended route is predicted to become not found.'
        why_it_matters = 'Removing this authorization without replacement leaves the intended route uncovered.'
        operator_action = 'Add a replacement authorization or do not approve the withdraw.'
    elif scenario.scenario_type == 'reshape_drops_specific_coverage':
        outcome_type = rpki_models.ROAValidationSimulationOutcome.INVALID
        approval_impact = SIMULATION_APPROVAL_IMPACT_BLOCKING
        operator_message = 'The reshape is predicted to drop required specific-route coverage.'
        why_it_matters = 'Narrowing the authorization may invalidate routes that currently depend on the broader entry.'
        operator_action = 'Revise the replacement so required specific coverage remains authorized.'
    elif scenario.scenario_type in {'replacement_broadens_authorization', 'withdraw_removes_unrelated_coverage'}:
        outcome_type = rpki_models.ROAValidationSimulationOutcome.VALID
        approval_impact = SIMULATION_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED
        if scenario.scenario_type == 'replacement_broadens_authorization':
            operator_message = 'The intended route remains covered, but the plan broadens authorization.'
            why_it_matters = 'A broader ROA may validate routes that were not intended to be authorized.'
            operator_action = 'Acknowledge the broader authorization risk before approval.'
        else:
            operator_message = 'The withdraw removes authorization that may still affect collateral coverage.'
            why_it_matters = 'Removing a broader authorization can change validity for more specific routes.'
            operator_action = 'Acknowledge the collateral coverage change before approval.'
    elif scenario.scenario_type == 'insufficient_state_requires_review':
        outcome_type = (
            rpki_models.ROAValidationSimulationOutcome.INVALID
            if item.action_type == rpki_models.ROAChangePlanAction.CREATE
            else rpki_models.ROAValidationSimulationOutcome.NOT_FOUND
        )
        approval_impact = SIMULATION_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED
        operator_message = 'The simulation could not fully classify this plan item from the available state.'
        why_it_matters = 'Incomplete simulation input reduces confidence in the predicted validation outcome.'
        operator_action = 'Review the plan item state and acknowledge the ambiguity before approval.'

    details_json = {
        'action_type': item.action_type,
        'plan_semantic': item.plan_semantic or item.action_type,
        'before_state': dict(item.before_state_json or {}),
        'after_state': dict(item.after_state_json or {}),
        'reason': item.reason,
        'provider_operation': item.provider_operation,
        'scenario_type': scenario.scenario_type,
        'impact_scope': scenario.impact_scope,
        'approval_impact': approval_impact,
        'plan_fingerprint': context.plan_fingerprint,
        'operator_message': operator_message,
        'why_it_matters': why_it_matters,
        'operator_action': operator_action,
        'before_coverage': _build_coverage_summary(before_matches, intended_fact),
        'after_coverage': _build_coverage_summary(after_matches, intended_fact),
        'affected_prefixes': sorted({
            value
            for value in (
                getattr(intended_fact, 'prefix_cidr_text', None),
                getattr(scenario.before_fact, 'prefix_cidr_text', None),
                getattr(scenario.after_fact, 'prefix_cidr_text', None),
            )
            if value
        }),
        'affected_origin_asns': sorted({
            value
            for value in (
                getattr(intended_fact, 'origin_asn_value', None),
                getattr(scenario.before_fact, 'origin_asn_value', None),
                getattr(scenario.after_fact, 'origin_asn_value', None),
            )
            if value is not None
        }),
        'collateral_impact_count': scenario.collateral_impact_count,
        'transition_risk': scenario.transition_risk,
        'explanation': scenario.explanation,
    }
    return ClassifiedSimulationResult(
        outcome_type=outcome_type,
        approval_impact=approval_impact,
        scenario_type=scenario.scenario_type,
        operator_message=operator_message,
        operator_action=operator_action,
        why_it_matters=why_it_matters,
        details_json=details_json,
    )


def _summarize_simulation_results(
    results: list[ClassifiedSimulationResult],
    *,
    plan: rpki_models.ROAChangePlan,
    plan_fingerprint: str,
) -> dict:
    outcome_counts = {
        rpki_models.ROAValidationSimulationOutcome.VALID: 0,
        rpki_models.ROAValidationSimulationOutcome.INVALID: 0,
        rpki_models.ROAValidationSimulationOutcome.NOT_FOUND: 0,
    }
    impact_counts = {
        SIMULATION_APPROVAL_IMPACT_INFORMATIONAL: 0,
        SIMULATION_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED: 0,
        SIMULATION_APPROVAL_IMPACT_BLOCKING: 0,
    }
    semantic_counts: dict[str, int] = {}
    scenario_counts: dict[str, int] = {}
    affected_intended_route_count = 0
    affected_collateral_route_count = 0
    partially_constrained = False

    for item, result in zip(plan.items.order_by('pk'), results):
        outcome_counts[result.outcome_type] = outcome_counts.get(result.outcome_type, 0) + 1
        impact_counts[result.approval_impact] = impact_counts.get(result.approval_impact, 0) + 1
        semantic_key = item.plan_semantic or item.action_type
        semantic_counts[semantic_key] = semantic_counts.get(semantic_key, 0) + 1
        scenario_counts[result.scenario_type] = scenario_counts.get(result.scenario_type, 0) + 1
        if result.details_json['after_coverage']['covers_intended_route'] != result.details_json['before_coverage']['covers_intended_route']:
            affected_intended_route_count += 1
        if result.details_json.get('collateral_impact_count', 0):
            affected_collateral_route_count += result.details_json['collateral_impact_count']
        if result.scenario_type == 'insufficient_state_requires_review':
            partially_constrained = True

    overall_approval_posture = SIMULATION_APPROVAL_IMPACT_INFORMATIONAL
    if impact_counts[SIMULATION_APPROVAL_IMPACT_BLOCKING] > 0:
        overall_approval_posture = SIMULATION_APPROVAL_IMPACT_BLOCKING
    elif impact_counts[SIMULATION_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED] > 0:
        overall_approval_posture = SIMULATION_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED

    return {
        'plan_fingerprint': plan_fingerprint,
        'comparison_scope': plan.source_reconciliation_run.comparison_scope,
        'provider_backed': plan.is_provider_backed,
        'predicted_outcome_counts': outcome_counts,
        'plan_semantic_counts': semantic_counts,
        'approval_impact_counts': impact_counts,
        'scenario_type_counts': scenario_counts,
        'affected_intended_route_count': affected_intended_route_count,
        'affected_collateral_route_count': affected_collateral_route_count,
        'overall_approval_posture': overall_approval_posture,
        'is_current_for_plan': True,
        'partially_constrained': partially_constrained,
        'change_plan_id': plan.pk,
    }


def build_roa_change_plan_simulation_posture(
    plan: rpki_models.ROAChangePlan | int,
) -> dict:
    plan = _normalize_plan(plan)
    simulation_run_id = (plan.summary_json or {}).get('simulation_run_id')
    simulation_run = None
    if simulation_run_id:
        simulation_run = plan.simulation_runs.filter(pk=simulation_run_id).first()
    if simulation_run is None:
        simulation_run = plan.simulation_runs.order_by('-started_at', '-created').first()

    base_counts = {
        SIMULATION_APPROVAL_IMPACT_INFORMATIONAL: 0,
        SIMULATION_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED: 0,
        SIMULATION_APPROVAL_IMPACT_BLOCKING: 0,
    }
    posture = {
        'status': 'missing',
        'awaiting_review': True,
        'has_simulation': False,
        'run_id': None,
        'run_status': None,
        'overall_approval_posture': None,
        'is_current_for_plan': False,
        'partially_constrained': False,
        'approval_impact_counts': dict(base_counts),
        'scenario_type_counts': {},
        'predicted_outcome_counts': {},
    }
    if simulation_run is None:
        return posture

    summary = dict(simulation_run.summary_json or {})
    posture.update({
        'has_simulation': True,
        'run_id': simulation_run.pk,
        'run_status': simulation_run.status,
        'overall_approval_posture': simulation_run.overall_approval_posture or summary.get('overall_approval_posture'),
        'is_current_for_plan': simulation_run.is_current_for_plan,
        'partially_constrained': simulation_run.partially_constrained,
        'approval_impact_counts': dict(base_counts | dict(summary.get('approval_impact_counts') or {})),
        'scenario_type_counts': dict(summary.get('scenario_type_counts') or {}),
        'predicted_outcome_counts': dict(summary.get('predicted_outcome_counts') or {}),
    })
    if simulation_run.status != rpki_models.ValidationRunStatus.COMPLETED:
        posture['status'] = 'pending'
        return posture

    expected_fingerprint = _build_plan_fingerprint(plan)
    actual_fingerprint = simulation_run.plan_fingerprint or summary.get('plan_fingerprint')
    is_current_for_plan = actual_fingerprint == expected_fingerprint
    posture['is_current_for_plan'] = is_current_for_plan
    if not is_current_for_plan:
        posture['status'] = 'stale'
        return posture

    status = posture['overall_approval_posture'] or SIMULATION_APPROVAL_IMPACT_INFORMATIONAL
    posture['status'] = status
    posture['awaiting_review'] = status in {
        SIMULATION_APPROVAL_IMPACT_BLOCKING,
        SIMULATION_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED,
    }
    return posture


def require_roa_change_plan_simulation_approvable(
    plan: rpki_models.ROAChangePlan | int,
    *,
    acknowledged_simulation_result_ids: list[int] | None = None,
) -> rpki_models.ROAValidationSimulationRun:
    plan = _normalize_plan(plan)
    acknowledged_simulation_result_ids = set(acknowledged_simulation_result_ids or [])
    simulation_run_id = (plan.summary_json or {}).get('simulation_run_id')
    if not simulation_run_id:
        raise ValueError('This ROA change plan cannot be approved until a simulation run has been recorded.')

    simulation_run = plan.simulation_runs.prefetch_related('results').filter(pk=simulation_run_id).first()
    if simulation_run is None:
        raise ValueError('The latest simulation run recorded on this ROA change plan could not be found.')
    if simulation_run.status != rpki_models.ValidationRunStatus.COMPLETED:
        raise ValueError('This ROA change plan cannot be approved until the latest simulation run has completed.')

    expected_fingerprint = _build_plan_fingerprint(plan)
    actual_fingerprint = simulation_run.plan_fingerprint or (simulation_run.summary_json or {}).get('plan_fingerprint')
    if actual_fingerprint != expected_fingerprint:
        raise ValueError('This ROA change plan cannot be approved until the simulation run is refreshed for the current plan state.')

    blocking_results = []
    ack_required_results = []
    for result in simulation_run.results.all():
        approval_impact = result.approval_impact or (result.details_json or {}).get('approval_impact')
        if approval_impact == SIMULATION_APPROVAL_IMPACT_BLOCKING:
            blocking_results.append(result)
        elif approval_impact == SIMULATION_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED:
            ack_required_results.append(result)

    if blocking_results:
        raise ValueError(
            f'This ROA change plan has {len(blocking_results)} blocking simulation result(s).'
        )

    unresolved_ack_required = [
        result for result in ack_required_results if result.pk not in acknowledged_simulation_result_ids
    ]
    if unresolved_ack_required:
        raise ValueError(
            'This ROA change plan has acknowledgement-required simulation results that must be acknowledged before approval.'
        )
    return simulation_run


def simulate_roa_change_plan(
    plan: rpki_models.ROAChangePlan | int,
    *,
    run_name: str | None = None,
) -> rpki_models.ROAValidationSimulationRun:
    plan = _normalize_plan(plan)
    context = _build_plan_simulation_context(plan)
    now = timezone.now()
    simulation_run = rpki_models.ROAValidationSimulationRun.objects.create(
        name=run_name or f'{plan.name} Simulation {now:%Y-%m-%d %H:%M:%S}',
        change_plan=plan,
        tenant=plan.tenant,
        status=rpki_models.ValidationRunStatus.RUNNING,
        started_at=now,
        summary_json={'plan_fingerprint': context.plan_fingerprint},
    )

    classified_results: list[ClassifiedSimulationResult] = []
    for item in plan.items.order_by('pk'):
        scenarios = _build_plan_item_scenarios(item, context)
        classified_result = _classify_plan_item_scenarios(item, scenarios, context)
        rpki_models.ROAValidationSimulationResult.objects.create(
            name=f'{item.name} Simulation',
            simulation_run=simulation_run,
            tenant=plan.tenant,
            change_plan_item=item,
            outcome_type=classified_result.outcome_type,
            approval_impact=classified_result.approval_impact,
            scenario_type=classified_result.scenario_type,
            details_json=classified_result.details_json,
            computed_at=timezone.now(),
        )
        classified_results.append(classified_result)

    summary_json = _summarize_simulation_results(
        classified_results,
        plan=plan,
        plan_fingerprint=context.plan_fingerprint,
    )
    simulation_run.status = rpki_models.ValidationRunStatus.COMPLETED
    simulation_run.completed_at = timezone.now()
    simulation_run.result_count = len(classified_results)
    simulation_run.predicted_valid_count = summary_json['predicted_outcome_counts'][rpki_models.ROAValidationSimulationOutcome.VALID]
    simulation_run.predicted_invalid_count = summary_json['predicted_outcome_counts'][rpki_models.ROAValidationSimulationOutcome.INVALID]
    simulation_run.predicted_not_found_count = summary_json['predicted_outcome_counts'][rpki_models.ROAValidationSimulationOutcome.NOT_FOUND]
    simulation_run.plan_fingerprint = context.plan_fingerprint
    simulation_run.overall_approval_posture = summary_json['overall_approval_posture']
    simulation_run.is_current_for_plan = summary_json['is_current_for_plan']
    simulation_run.partially_constrained = summary_json['partially_constrained']
    simulation_run.summary_json = summary_json
    simulation_run.save(
        update_fields=(
            'status',
            'completed_at',
            'result_count',
            'predicted_valid_count',
            'predicted_invalid_count',
            'predicted_not_found_count',
            'plan_fingerprint',
            'overall_approval_posture',
            'is_current_for_plan',
            'partially_constrained',
            'summary_json',
        )
    )

    plan.summary_json['simulation_run_id'] = simulation_run.pk
    plan.summary_json['simulation_plan_fingerprint'] = context.plan_fingerprint
    plan.summary_json['latest_simulation_summary'] = summary_json
    plan.save(update_fields=('summary_json',))
    return simulation_run
