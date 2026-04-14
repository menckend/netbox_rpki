# NetBox RPKI Plugin: ROV Impact Simulation Plan

Prepared: April 13, 2026

## Objective

Implement backlog Priority 5 as a compatibility-preserving expansion of the existing ROA change-plan workflow.

The target is not a full relying-party validator inside the plugin. The target is an operator-facing simulation layer that can explain the predicted validation impact of proposed ROA changes before approval or apply.

This document carries the detailed proposed contracts, model evolution, service expectations, workflow surfaces, and execution slicing for Priority 5. The backlog remains the short status-and-priority view.

## Relationship To Existing Architecture

This plan must stay aligned with the plugin's current architecture rules:

- Django models and migrations remain explicit.
- Standard read and CRUD surfaces remain registry-driven where they fit.
- Workflow actions and domain behavior stay in explicit services, jobs, and custom actions.
- Simulation remains attached to the existing reconciliation and change-plan pipeline rather than becoming a parallel review path.

This plan builds on the current `ROAChangePlan` flow and on the existing simulation models and service.

## Current-State Baseline

The plugin already has a first simulation substrate, but it is intentionally thin.

Existing simulation objects:

- `ROAValidationSimulationRun`
- `ROAValidationSimulationResult`

Existing simulation entry points and surfaces:

- `netbox_rpki/services/rov_simulation.py`
- `ROAChangePlanViewSet.simulate` in `netbox_rpki/api/views.py`
- generated read surfaces for simulation run and result objects through `netbox_rpki/object_registry.py`
- explicit detail specs for simulation run and result detail pages in `netbox_rpki/detail_specs.py`
- change-plan creation currently runs simulation automatically and stores `simulation_run_id` in `ROAChangePlan.summary_json`

Existing focused tests prove only the substrate exists:

- `netbox_rpki/tests/test_routing_intent_services.py` verifies that plan creation produces a simulation run and basic counts
- test builders in `netbox_rpki/tests/utils.py` can already create simulation runs and results

What the current service actually does today:

- create actions with enough target state are predicted as `valid`
- replacement or reshape semantics with a replacement target are predicted as `valid`
- standalone withdraws are predicted as `not_found`
- malformed create state falls back to `invalid`

What the current service does not do yet:

- no route-set or blast-radius modeling
- no distinction between intended route validity and collateral impact on other covered routes
- no richer scenario catalog beyond per-item heuristics
- no simulation-specific explanation contract beyond a short text string in `details_json`
- no approval gating contract based on simulation posture

## Design Boundaries

The implementation should stay inside these boundaries unless a later design pass explicitly changes them.

- Do not turn the plugin into a full validator or a complete VRP generation system.
- Keep simulation plan-scoped. The canonical input remains a `ROAChangePlan`.
- Keep simulation additive and explainable. It should enrich approval review, not silently replace it.
- Keep the first wave focused on ROA validation outcomes and blast radius. Do not expand into ASPA simulation in the same slice unless the ROA contract proves stable first.
- Prefer deterministic offline reasoning over provider-specific live calls in the first wave.
- Keep the first approval policy simple and deterministic: approval requires a current simulation run, blocking posture denies approval, and acknowledgement-required posture must be explicitly handled before approval succeeds.

## Resolved First-Wave Decisions

The following design questions are considered resolved for the first implementation wave.

### 1. Simulation remains plan-scoped

The canonical simulation input remains `ROAChangePlan`.

That means:

- no profile-level simulation model in the first wave
- no reconciliation-level simulation model in the first wave
- any simulation summary shown on reconciliation surfaces should be derived from the latest change plan, not from a second independent simulation object family

### 2. Existing simulation models remain the primary persistence layer

Do not introduce a second top-level simulation parent or scenario-set model in the first wave.

Continue using:

- `ROAValidationSimulationRun`
- `ROAValidationSimulationResult`

Enhance them additively through new fields or richer `summary_json` and `details_json` contracts where needed.

### 3. Simulation is approval-dependent from the first implementation wave

Approval should depend on simulation posture as soon as the richer contract lands.

The first approval policy is intentionally narrow:

1. approval requires a completed, current simulation run for the exact plan state being approved
2. any blocking simulation result denies approval
3. acknowledgement-required simulation results must be explicitly acknowledged as part of approval
4. informational results never block approval

This keeps the approval contract deterministic without forcing the first wave to model every possible validator nuance.

### 4. Outcome taxonomy stays stable in the first wave, while explanation depth expands

Keep the current top-level outcome categories as the stable first-wave public result type:

- `valid`
- `invalid`
- `not_found`

Do not add a wider public outcome enum in the first wave unless the current three-way split becomes an actual blocker.

Instead, express richer semantics through normalized summary and detail fields such as:

- scenario type
- impact classification
- blast-radius counts
- collateral-risk indicators
- operator explanation fields

### 5. Approval policy keys off normalized approval impact, not raw outcome type

The public outcome enum remains:

- `valid`
- `invalid`
- `not_found`

Approval logic must not infer policy directly from those outcome types.

Instead, policy keys off normalized `approval_impact` values produced by the simulation classifier. That keeps approval behavior stable even when multiple scenario families map to the same public outcome.

### 6. The simulation engine should reason about both intended and collateral outcomes

The current item-by-item heuristic is too narrow. The richer simulation contract must answer two separate questions:

- what happens to the intended route or authorization after the plan is applied
- what other routes or authorizations might lose coverage, gain unexpected coverage, or shift outcome class because of the same plan

That distinction should be explicit in result details and run summaries.

### 7. The first fidelity target is deterministic route-coverage reasoning, not live validator parity

The first useful fidelity upgrade is offline coverage reasoning against:

- before-state ROA coverage implied by the current change plan context
- after-state ROA coverage implied by proposed plan items
- matched intended authorizations from the reconciliation substrate

Do not wait for full external validator integration to make Priority 5 operationally useful.

## Proposed Simulation Contract

### Simulation Questions The Service Must Answer

For every change plan, the simulation layer should be able to answer:

1. Will the intended route remain valid after this plan?
2. Will the intended route become invalid or not found at any point in the transition?
3. Does the plan broaden authorization more than intended?
4. Does the plan withdraw authorization that still covers unrelated or additional routes?
5. What is the expected blast radius by prefix, origin ASN, and plan item?
6. Which results are informational, acknowledgement-required, or blocking for approval?

### Result Granularity Contract

The first wave should keep two granularities only:

- run-level summary for operator review and aggregate reporting
- plan-item-level result rows for drill-down and direct explanation

Do not add per-prefix child rows in the first wave unless the item-level contract proves insufficient. Instead, encode route- or prefix-level affected facts in normalized detail payloads on `ROAValidationSimulationResult`.

### Run-Level Summary Contract

`ROAValidationSimulationRun.summary_json` should evolve from simple outcome counts into a stable operator summary that includes:

- predicted outcome counts
- counts by plan semantic
- comparison scope
- provider-backed versus local plan indicator
- blast-radius totals
- counts of affected intended routes
- counts of affected collateral routes
- counts by scenario family
- counts by approval impact classification
- overall approval posture for the run
- whether the run is current for the plan fingerprint being reviewed

### Result-Level Detail Contract

`ROAValidationSimulationResult.details_json` should evolve into a normalized structure with fields such as:

- `scenario_type`
- `impact_scope`
- `approval_impact`
- `plan_fingerprint`
- `operator_message`
- `why_it_matters`
- `operator_action`
- `before_coverage`
- `after_coverage`
- `affected_prefixes`
- `affected_origin_asns`
- `collateral_impact_count`
- `transition_risk`
- `explanation`

The current free-form explanation text can remain, but the richer fields should become the canonical contract for UI, API, and future export surfaces.

## Proposed Model Evolution

### Existing Models To Extend

Keep `ROAValidationSimulationRun` and `ROAValidationSimulationResult` as the primary persistence layer.

Recommended additive evolution for `ROAValidationSimulationRun`:

- optional count fields or stable summary keys for blast-radius and approval-impact rollups
- optional run metadata describing simulation engine version or ruleset version
- optional status detail for failed or partial runs if the engine becomes more complex

Recommended additive evolution for `ROAValidationSimulationResult`:

- optional direct linkage remains only to `ROAChangePlanItem` in the first wave
- richer normalized detail payload contract for scenario type, collateral impact, and operator guidance
- optional stable short classification fields if repeated filtering in list views becomes awkward through JSON only

### Models To Avoid In The First Wave

Do not add these in the first implementation wave unless a concrete gap proves them necessary:

- a separate simulation scenario catalog model
- a per-prefix simulation child model
- a simulation-only approval model
- a dedicated validator snapshot dependency for basic simulation operation

Use service-layer dataclasses and normalized JSON contracts first.

## Proposed Service Contracts

### Service Overview

| Contract | Likely module | Inputs | Outputs | Purpose |
| --- | --- | --- | --- | --- |
| plan normalization | `services/rov_simulation.py` | `ROAChangePlan` | normalized before and after state view | Keeps simulation input deterministic. |
| scenario builder | `services/rov_simulation.py` or helper module | plan items plus current plan context | simulation scenarios | Converts plan semantics into explainable validation scenarios. |
| coverage analyzer | helper inside `services/rov_simulation.py` | before and after effective authorization sets | affected-route facts | Determines intended versus collateral coverage changes. |
| result classifier | same module | scenario facts | outcome type, approval impact, explanation fields | Produces stable operator-facing result semantics. |
| run summarizer | same module | result rows | run summary contract | Builds list/detail/dashboard rollups from normalized results. |

### Scenario Families

The first richer rule catalog should cover at least these scenario families:

- exact intended-create validation
- replacement continuity validation
- withdraw-without-replacement not-found outcome
- broadened authorization risk
- overbroad replacement risk
- high-withdraw concentration risk
- uncovered-specific after withdraw risk
- provider-backed transition risk when create and withdraw ordering matters

These scenario families should be deterministic from the plan and current reconciliation context. They should not require live provider round trips.

### Coverage Analysis Contract

The richer simulation engine should build a simple before and after authorization view using:

- the plan's `before_state_json` and `after_state_json`
- the linked `ROAIntent` state on plan items where present
- current reconciliation context from `plan.source_reconciliation_run`
- any matched published authorization state already serialized into plan or reconciliation details

The analyzer should answer:

- which intended authorizations remain covered
- which intended authorizations become uncovered
- which broader prefixes or alternate specifics remain covered only accidentally
- which unaffected routes might lose coverage because of a withdraw or reshape

### Approval-Impact Contract

The first-wave simulation contract should normalize result posture into three classes:

- informational
- acknowledgement_required
- blocking

Approval behavior should consume those classes directly.

The approval contract for `ROAChangePlan` becomes:

- a plan without a completed current simulation run cannot be approved
- a plan with one or more blocking results cannot be approved
- a plan with acknowledgement-required results can be approved only when those results are explicitly acknowledged during the approval action
- a plan with only informational results can be approved normally

The simulation service must therefore produce both per-result `approval_impact` and run-level approval summary data that the approval service can consume without rerunning the simulation classifier.

### Failure Contract

If the simulation engine cannot classify a plan item confidently because input state is incomplete, it should not silently mark the result `valid`.

Instead it should:

- produce a deterministic fallback outcome based on the current public enum
- record why confidence is limited in normalized detail fields
- surface the run as partially constrained in `summary_json`
- classify the result as at least `acknowledgement_required` unless the scenario is clearly blocking

## Proposed Surface Contract

### Existing Surfaces To Deepen

The first wave should deepen existing simulation surfaces rather than inventing a new UI family.

Primary surfaces:

- `ROAChangePlanViewSet.simulate`
- generated list and detail surfaces for `ROAValidationSimulationRun`
- generated list and detail surfaces for `ROAValidationSimulationResult`
- `ROAChangePlan` detail and summary surfaces that already expose plan summary and custom workflow actions

### Workflow Surface Expectations

Priority 5 depends on the Priority 1 workflow-parity follow-on work. The simulation contract should assume:

- API simulation action already exists
- web UI parity for `roachangeplan.simulate` should exist or land as part of the workflow-surface parity track
- simulation summaries should be visible from the plan detail view and from aggregate reporting rather than only as standalone object pages
- approval surfaces should expose why approval is blocked or what simulation results must be acknowledged

### Reporting Contract

At minimum, simulation reporting should expose:

- latest simulation run for each plan
- predicted valid or invalid or not-found counts
- blast-radius totals
- counts by approval-impact class
- overall approval posture and whether approval is currently blocked
- clear links from change plan summaries to the underlying simulation run and results

## Execution Model

### Ownership Rules

This work touches the same high-conflict files already called out elsewhere in the repo's working documents. Use these ownership rules during implementation:

- one owner at a time for `netbox_rpki/models.py` and `netbox_rpki/migrations/`
- one owner at a time for shared surface files such as `detail_specs.py`, `api/views.py`, and registry-driven serializer or GraphQL files if they need additive exposure changes
- one owner at a time for `services/rov_simulation.py`
- docs and checklist updates can run in parallel only if they do not also edit the active shared surface window

### Slice 0: Freeze The Simulation Contract

Objective:

- record the first-wave simulation questions, scenario families, summary contract, and approval-impact contract as fixed input for code work

Likely write set:

- this plan
- `devrun/work_in_progress/netbox_rpki_enhancement_backlog.md`

Outputs:

- one recorded simulation contract
- one recorded scenario-family baseline
- one recorded first-wave policy that simulation is approval-dependent

Verification:

- consistency review only

Dependency rule:

- design-complete in this document; later code slices should not silently change the public simulation contract

### Slice 1: Deepen The Simulation Service Contract

Objective:

- replace the current item-by-item heuristic with a deterministic scenario and coverage analyzer while preserving the existing run and result object family, and emit approval-ready posture data consumed by the approval service

Likely write set:

- `netbox_rpki/services/rov_simulation.py`
- `netbox_rpki/services/__init__.py` if exports change
- `netbox_rpki/services/provider_write.py`
- `netbox_rpki/tests/test_routing_intent_services.py`
- `netbox_rpki/tests/test_provider_write.py`

Outputs:

- richer scenario builder
- before and after coverage reasoning
- normalized result details and run summaries
- approval-ready summary posture for the current plan fingerprint

Verification:

- existing simple cases still classify correctly
- replacement continuity, broadened authorization, and uncovered withdraw cases are explicitly tested
- simulation no longer treats incomplete state as silently safe
- approval denies when the current simulation run is missing, stale, or blocking
- approval accepts acknowledgement-required results only when explicit acknowledgements are supplied

Dependency rule:

- depends on Slice 0 only

#### Slice 1 implementation-ready service spec

Slice 1 should be implementable without inventing new top-level simulation models. The write set should stay centered on `netbox_rpki/services/rov_simulation.py`, `netbox_rpki/services/provider_write.py`, and focused tests.

##### Service entry points

Keep the existing public entry point:

```python
def simulate_roa_change_plan(
	plan: rpki_models.ROAChangePlan | int,
	*,
	run_name: str | None = None,
) -> rpki_models.ROAValidationSimulationRun:
```

Add internal helpers in `netbox_rpki/services/rov_simulation.py` with contracts shaped like:

```python
def _build_plan_fingerprint(plan: rpki_models.ROAChangePlan) -> str: ...

def _build_plan_simulation_context(
	plan: rpki_models.ROAChangePlan,
) -> PlanSimulationContext: ...

def _build_plan_item_scenarios(
	item: rpki_models.ROAChangePlanItem,
	context: PlanSimulationContext,
) -> list[SimulationScenario]: ...

def _classify_plan_item_scenarios(
	item: rpki_models.ROAChangePlanItem,
	scenarios: list[SimulationScenario],
	context: PlanSimulationContext,
) -> ClassifiedSimulationResult: ...

def _summarize_simulation_results(
	results: list[ClassifiedSimulationResult],
	*,
	plan: rpki_models.ROAChangePlan,
	plan_fingerprint: str,
) -> dict: ...

def require_roa_change_plan_simulation_approvable(
	plan: rpki_models.ROAChangePlan | int,
	*,
	acknowledged_simulation_result_ids: list[int] | None = None,
) -> rpki_models.ROAValidationSimulationRun: ...
```

The approval helper should be called from `approve_roa_change_plan()` before the plan status flips to `APPROVED`.

##### Slice 1 data shapes

Use service-layer dataclasses first. Do not add model classes in Slice 1.

Recommended dataclasses:

```python
@dataclass(slots=True)
class AuthorizationFact:
	prefix_cidr_text: str
	origin_asn_value: int | None
	max_length: int | None
	source: str
	source_id: int | None


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
	plan_item_id: int
	intended_prefixes: list[str]
	intended_origin_asns: list[int]
	before_matches: list[AuthorizationFact]
	after_matches: list[AuthorizationFact]
	collateral_prefixes: list[str]
	transition_risk: str


@dataclass(slots=True)
class ClassifiedSimulationResult:
	outcome_type: str
	approval_impact: str
	scenario_type: str
	operator_message: str
	operator_action: str
	why_it_matters: str
	details_json: dict
```

##### Plan fingerprint contract

Approval cannot rely on any simulation run for the same plan. It must rely on a simulation run for the exact plan contents being approved.

Slice 1 should therefore compute a deterministic plan fingerprint from:

- plan primary key
- ordered plan-item primary keys
- each item's `action_type`
- each item's `plan_semantic`
- each item's `before_state_json`
- each item's `after_state_json`
- each item's `provider_operation`

Write that fingerprint into:

- `ROAValidationSimulationRun.summary_json['plan_fingerprint']`
- `ROAValidationSimulationResult.details_json['plan_fingerprint']`
- `ROAChangePlan.summary_json['simulation_plan_fingerprint']`

`simulate_roa_change_plan()` should also continue to mirror the latest simulation run identifier into `ROAChangePlan.summary_json['simulation_run_id']`.

##### Scenario-building rules for Slice 1

Slice 1 should support, at minimum, these deterministic scenario families:

1. `exact_create_validates`
2. `replacement_preserves_coverage`
3. `withdraw_without_replacement_not_found`
4. `replacement_broadens_authorization`
5. `withdraw_removes_unrelated_coverage`
6. `reshape_drops_specific_coverage`
7. `insufficient_state_requires_review`

The scenario builder should derive these from the current `ROAChangePlanItem` state plus the plan-level before and after authorization view. It should not call external providers or validators.

##### Classification rules for Slice 1

`_classify_plan_item_scenarios()` should emit exactly one persisted `ROAValidationSimulationResult` per `ROAChangePlanItem`.

Use this priority order when multiple scenarios apply:

1. any scenario that causes loss of intended coverage or leaves no remaining covering authorization => `outcome_type='invalid'` or `outcome_type='not_found'`, `approval_impact='blocking'`
2. broadened authorization or collateral-impact scenarios that keep intended coverage but increase risk => `outcome_type='valid'`, `approval_impact='acknowledgement_required'`
3. straightforward continuity scenarios => `outcome_type='valid'`, `approval_impact='informational'`
4. incomplete or ambiguous state => fallback public outcome plus `approval_impact='acknowledgement_required'`

Each persisted result should include these normalized `details_json` keys at minimum:

- `scenario_type`
- `approval_impact`
- `plan_fingerprint`
- `operator_message`
- `operator_action`
- `why_it_matters`
- `before_coverage`
- `after_coverage`
- `affected_prefixes`
- `affected_origin_asns`
- `collateral_impact_count`
- `transition_risk`
- `explanation`

##### Run summary contract for Slice 1

`_summarize_simulation_results()` should populate `ROAValidationSimulationRun.summary_json` with stable keys at minimum:

- `plan_fingerprint`
- `comparison_scope`
- `provider_backed`
- `predicted_outcome_counts`
- `plan_semantic_counts`
- `approval_impact_counts`
- `scenario_type_counts`
- `affected_intended_route_count`
- `affected_collateral_route_count`
- `overall_approval_posture`
- `is_current_for_plan`
- `partially_constrained`

`overall_approval_posture` should resolve by severity:

- `blocking` if any result is blocking
- `acknowledgement_required` else if any result requires acknowledgement
- `informational` otherwise

##### Approval integration contract for Slice 1

Extend `approve_roa_change_plan()` in `netbox_rpki/services/provider_write.py` with an additional optional argument:

```python
acknowledged_simulation_result_ids: list[int] | None = None
```

The service should then:

1. read `plan.summary_json['simulation_run_id']`
2. load that `ROAValidationSimulationRun`
3. verify the run is completed
4. verify `summary_json['plan_fingerprint']` matches the current fingerprint for the plan
5. reject approval if any blocking results exist
6. reject approval if acknowledgement-required results exist that are not listed in `acknowledged_simulation_result_ids`
7. persist the acknowledged result ids and summary posture into approval metadata using the lightest compatible contract available in Slice 1

Because Slice 1 avoids new models, the temporary persistence contract may store acknowledged simulation result ids and posture summary in `ApprovalRecord.notes` plus mirrored plan summary keys. If that proves too awkward for filtering or audit, promote it to first-class fields or a sibling acknowledgement model in Slice 2.

The key requirement is behavioral, not cosmetic: approval must be denied deterministically when simulation posture requires it.

##### Focused test matrix for Slice 1

Add or expand focused tests in `netbox_rpki/tests/test_routing_intent_services.py` and `netbox_rpki/tests/test_provider_write.py` for at least these cases:

1. create item with complete after-state => informational approval posture
2. replacement pair preserving coverage => informational approval posture
3. withdraw with no replacement => blocking approval posture and approval denial
4. broadened replacement => acknowledgement-required posture and approval denial until acknowledged
5. stale simulation fingerprint after plan mutation => approval denial
6. incomplete simulation state => acknowledgement-required posture

Do not consider Slice 1 complete until the approval path proves it consumes simulation posture instead of ignoring it.

### Slice 2: Extend Model And Summary Fields Only If Proven Necessary

Objective:

- add explicit fields on simulation run or result models only when the richer contract cannot be supported cleanly through stable JSON alone

Likely write set:

- `netbox_rpki/models.py`
- `netbox_rpki/migrations/`
- affected factory helpers in `netbox_rpki/tests/utils.py`
- targeted model tests

Outputs:

- additive fields for operator-significant rollups or filtering, if needed

Verification:

- `manage.py makemigrations --check --dry-run netbox_rpki`
- focused model and factory tests

Dependency rule:

- depends on Slice 1 proving which fields actually need to become first-class

### Slice 3: Expose Richer Explanation And Blast-Radius Surfaces

Objective:

- surface the richer simulation contract through existing API and detail pages so operators can understand the result without reading raw JSON only

Likely write set:

- `netbox_rpki/detail_specs.py`
- `netbox_rpki/api/serializers.py` if additive fields are exposed
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_views.py`

Outputs:

- richer run and result detail rendering
- additive serialized summary and explanation fields where appropriate
- blast-radius and approval-impact summary visibility on change-plan surfaces

Verification:

- rendered detail pages expose operator-meaningful explanation
- API output reflects the same normalized explanation contract
- simulations remain reachable from the plan workflow surface

Dependency rule:

- depends on Slice 1 and on Slice 2 only if additional fields land

### Slice 4: Add Aggregate Reporting And Dashboard Rollups

Objective:

- make simulation posture visible above the individual plan level

Likely write set:

- `netbox_rpki/api/views.py` summary surfaces
- dashboard or aggregate reporting surfaces already used for change-plan posture
- `netbox_rpki/tests/test_api.py`
- any affected view or dashboard tests

Outputs:

- rollups for plans with significant simulation impact
- blast-radius totals in aggregate reporting
- visibility into plans awaiting review because of simulation posture

Verification:

- aggregate counts match underlying simulation runs
- list or summary surfaces remain aligned with child detail pages

Dependency rule:

- depends on Slice 3

### Slice 5: Approval Acknowledgement And Policy Hardening

Objective:

- harden the approval-dependent simulation contract after the initial service-layer enforcement lands

Likely write set:

- `netbox_rpki/services/provider_write.py` or approval helper layer
- `netbox_rpki/views.py` and `netbox_rpki/api/views.py` for approval behavior
- detail and summary surfaces for plan posture
- focused approval tests

Outputs:

- deterministic approval behavior for acknowledgement-required results across API and web approval flows
- clearer audit treatment for acknowledged simulation risk where the Slice 1 lightweight persistence contract proves too thin

Verification:

- approval behavior is deterministic from simulation posture across all approval entry points
- acknowledgement metadata is preserved and visible enough for later audit and reporting

Dependency rule:

- depends on Slices 1 through 4
- should not weaken the blocking behavior introduced in Slice 1

### Slice 6: Release-Gate Hardening

Objective:

- prove that the richer simulation contract stays aligned across service, API, UI, and aggregate reporting surfaces

Likely write set:

- docs
- testing matrix or checklist updates if needed
- broad focused tests and final regression verification

Outputs:

- updated documentation and release-gate expectations
- stable focused tests for simulation fidelity and explanation

Verification:

- focused routing-intent, API, and view suites
- registry-wide surface-contract suites where simulation objects participate
- full plugin suite in the documented non-interactive NetBox environment

Dependency rule:

- depends on all earlier slices

## Recommended First Vertical Slice

The safest first implementation cut is intentionally narrow:

1. deepen `services/rov_simulation.py` to reason about replacement continuity, uncovered withdraws, and broadened authorization risk
2. keep the existing outcome enum stable
3. add normalized explanation, approval-impact, and blast-radius facts in `details_json` and `summary_json`
4. make `approve_roa_change_plan()` consume current simulation posture before approval succeeds
5. expose those richer facts in run and result detail views

That cut is large enough to make Priority 5 materially more useful and small enough to keep the approval contract tied to one deterministic simulation summary rather than a second governance subsystem.

## Acceptance Criteria

Priority 5 should be considered implementation-complete only when all of the following are true:

1. simulation results explain predicted route-validation outcomes in operator terms rather than only counting `valid` or `invalid` or `not_found`
2. the engine can reason about both intended outcomes and collateral blast radius for common ROA change-plan scenarios
3. approval requires a current simulation run and consumes normalized simulation posture deterministically
4. plan detail and aggregate surfaces expose the latest simulation posture clearly
5. focused regression suites and the broader plugin suite remain green

## Recommended Verification Set

Minimum focused verification for each landing slice:

- `netbox_rpki.tests.test_routing_intent_services`
- affected API and view suites such as `test_api` and `test_views`
- `manage.py makemigrations --check --dry-run netbox_rpki` whenever additive fields land

Release-gate verification should use the same non-interactive NetBox environment and commands already documented elsewhere in the repo.