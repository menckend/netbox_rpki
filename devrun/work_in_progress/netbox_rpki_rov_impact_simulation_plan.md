# NetBox RPKI Plugin: ROV Impact Simulation Implementation Guide

Prepared: April 13, 2026
Updated: April 14, 2026
Audience: plugin developers, especially junior developers implementing Priority 5
Status: implementation record and maintenance guide; Slices 0 through 6 are implemented in the repository

## How To Use This Document

This is no longer just a design note. It is the implementation guide and completion record for Priority 5.

If you are maintaining or extending this feature, use the document in this order:

1. read `Current Repository State` to understand what already exists
2. read `Non-Goals And Fixed Decisions` to understand what you must not change
3. read `Target Behavior` and `Data Contracts` to understand the contract the code now enforces
4. read `Implementation Status` to understand what landed in each slice
5. use `Implementation Checklist For Slice 1` only as historical build order when reviewing how the feature was introduced
6. use `Definition Of Done` as the maintained completion bar for future refactors or extensions

This guide is intentionally explicit. It should be possible to maintain or extend the feature from it without inventing missing behavior.

## Objective

Implement backlog Priority 5 as a compatibility-preserving expansion of the existing ROA change-plan workflow.

The target is not a full relying-party validator inside the plugin. The target is an operator-facing simulation layer that explains the predicted validation impact of proposed ROA changes before approval or apply.

The implementation must remain attached to the existing `ROAChangePlan` workflow. It should deepen the current simulation substrate rather than replace the workflow with a second review system.

## Current Repository State

The repository already contains a first simulation substrate. That substrate is intentionally thin and should be treated as the starting point, not the finished feature.

### Existing simulation models

- `ROAValidationSimulationRun`
- `ROAValidationSimulationResult`

### Existing code entry points

- `netbox_rpki/services/rov_simulation.py`
- `netbox_rpki/services/routing_intent.py`
- `netbox_rpki/services/provider_write.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/api/serializers.py`

### Existing workflow behavior

- change-plan creation already runs simulation automatically
- the latest simulation run id is stored in `ROAChangePlan.summary_json['simulation_run_id']`
- there is already an API action for re-running simulation
- simulation run and result objects already have generated list and detail surfaces

### Existing tests

The current tests prove the substrate exists, but they do not yet prove the richer simulation behavior this guide requires.

Relevant suites:

- `netbox_rpki/tests/test_routing_intent_services.py`
- `netbox_rpki/tests/test_provider_write.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_views.py`
- test builders in `netbox_rpki/tests/utils.py`

### What the current simulation service does today

The current service behavior is simple:

- create actions with enough target state are predicted as `valid`
- replacement or reshape semantics with a replacement target are predicted as `valid`
- standalone withdraws are predicted as `not_found`
- malformed create state falls back to `invalid`

### What is missing today

The current simulation service does not yet provide the operational behavior needed for Priority 5:

- no route-set or blast-radius modeling
- no distinction between intended route validity and collateral impact on other covered routes
- no richer scenario catalog beyond per-item heuristics
- no normalized simulation explanation contract beyond a short text string
- no plan fingerprint check to detect stale simulation runs
- no approval gating based on simulation posture

## Non-Goals And Fixed Decisions

These decisions are fixed for the first implementation wave. Do not change them during implementation unless a maintainer explicitly updates this document.

### Non-goals

- do not build a full RPKI relying-party validator
- do not require live provider or validator calls for first-wave classification
- do not introduce ASPA simulation in the same slice as the first ROA simulation expansion
- do not create a second top-level simulation family unrelated to `ROAChangePlan`
- do not widen the public outcome enum unless a maintainer explicitly approves it

### Fixed decisions

1. Simulation remains plan-scoped.
   The canonical input is `ROAChangePlan`.

2. Existing simulation models remain the primary persistence layer.
   Use `ROAValidationSimulationRun` and `ROAValidationSimulationResult`.

3. Approval becomes simulation-dependent in the first real implementation wave.
   Approval must consume simulation posture, not just lint posture.

4. The public outcome taxonomy stays:
   - `valid`
   - `invalid`
   - `not_found`

5. Approval logic must key off normalized `approval_impact`, not raw `outcome_type`.

6. The engine must reason about both:
   - intended route outcome
   - collateral impact on other coverage

7. First-wave fidelity is deterministic offline coverage reasoning, not validator parity.

## Reading Order Before Writing Code

If you are new to this part of the plugin, read these files in this order before changing code:

1. `netbox_rpki/services/rov_simulation.py`
2. `netbox_rpki/services/routing_intent.py`
3. `netbox_rpki/services/provider_write.py`
4. `netbox_rpki/models.py`
5. `netbox_rpki/api/views.py`
6. `netbox_rpki/api/serializers.py`
7. `netbox_rpki/detail_specs.py`
8. `netbox_rpki/tests/test_routing_intent_services.py`
9. `netbox_rpki/tests/test_provider_write.py`
10. `netbox_rpki/tests/utils.py`

The purpose of that reading order is:

- understand the current simulation service
- understand where change-plan creation triggers simulation
- understand where approval currently happens
- understand how plan summary data is surfaced
- understand what tests already exist and what patterns the repo uses

## Target Behavior

For every ROA change plan, the simulation layer must answer these operator-facing questions:

1. Will the intended route remain valid after the plan is applied?
2. Will the intended route become invalid or not found?
3. Does the plan broaden authorization more than intended?
4. Does the plan remove coverage that still matters to other prefixes or routes?
5. What is the expected blast radius by prefix, origin ASN, and plan item?
6. Which results are merely informational, which require acknowledgement, and which block approval?

## First-Wave Scenario Catalog

The first richer rule catalog must support at least these scenario families:

- `exact_create_validates`
- `replacement_preserves_coverage`
- `withdraw_without_replacement_not_found`
- `replacement_broadens_authorization`
- `withdraw_removes_unrelated_coverage`
- `reshape_drops_specific_coverage`
- `insufficient_state_requires_review`
- `provider_backed_transition_risk`

These scenarios must be deterministic from plan data plus reconciliation context. They must not require live provider round trips.

## Approval Policy

The first approval policy is intentionally narrow and deterministic:

1. approval requires a completed simulation run for the exact plan state being approved
2. if any simulation result is `blocking`, approval must fail
3. if any simulation result is `acknowledgement_required`, approval must fail unless those specific results are acknowledged in the approval action
4. if all simulation results are `informational`, approval may proceed

Lint posture still matters, but simulation posture must no longer be ignored.

## Data Contracts

This section defines the contracts that the service must emit. These contracts are the main source of truth for Slice 1 implementation.

### Approval impact enum

Use exactly these values:

- `informational`
- `acknowledgement_required`
- `blocking`

### Plan fingerprint contract

Approval cannot trust an arbitrary simulation run for the same plan. It must trust a run for the exact plan contents being approved.

Build a deterministic fingerprint from:

- plan primary key
- ordered plan item primary keys
- each item's `action_type`
- each item's `plan_semantic`
- each item's `before_state_json`
- each item's `after_state_json`
- each item's `provider_operation`

Store that fingerprint in:

- `ROAValidationSimulationRun.summary_json['plan_fingerprint']`
- `ROAValidationSimulationResult.details_json['plan_fingerprint']`
- `ROAChangePlan.summary_json['simulation_plan_fingerprint']`

`simulate_roa_change_plan()` must continue to mirror the latest run id into `ROAChangePlan.summary_json['simulation_run_id']`.

### Result detail contract

Each `ROAValidationSimulationResult.details_json` must contain, at minimum, these normalized keys:

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

These keys are required even if some values are empty or `null`. The goal is stable structure for API, UI, and tests.

### Result detail contract: meaning of each field

Use the fields consistently:

- `scenario_type`
  The normalized scenario family, such as `replacement_preserves_coverage`.

- `impact_scope`
  A short description of scope such as `intended_only`, `intended_and_collateral`, or `unknown`.

- `approval_impact`
  One of `informational`, `acknowledgement_required`, or `blocking`.

- `plan_fingerprint`
  The deterministic fingerprint of the plan at simulation time.

- `operator_message`
  One short sentence that tells the operator the practical result.

- `why_it_matters`
  One short sentence that explains operational risk or significance.

- `operator_action`
  One short sentence telling the operator what to do next.

- `before_coverage`
  A normalized summary of coverage facts before the plan.

- `after_coverage`
  A normalized summary of coverage facts after the plan.

- `affected_prefixes`
  Prefixes impacted by the change. Include intended and collateral prefixes if known.

- `affected_origin_asns`
  Origin ASNs impacted by the change.

- `collateral_impact_count`
  Integer count of collateral routes or coverage facts impacted.

- `transition_risk`
  A short value such as `none`, `ordering_sensitive`, `ambiguous_state`, or `coverage_loss`.

- `explanation`
  A longer human-readable explanation. This can be composed from the normalized fields.

### Result detail example

```json
{
  "scenario_type": "replacement_broadens_authorization",
  "impact_scope": "intended_and_collateral",
  "approval_impact": "acknowledgement_required",
  "plan_fingerprint": "3d8c5d0d4d4e...",
  "operator_message": "The intended route remains covered, but the replacement broadens authorization.",
  "why_it_matters": "A broader ROA may validate routes you did not intend to authorize.",
  "operator_action": "Review the replacement prefix and max length before approving the plan.",
  "before_coverage": {
    "matching_authorization_count": 1,
    "covers_intended_route": true
  },
  "after_coverage": {
    "matching_authorization_count": 1,
    "covers_intended_route": true
  },
  "affected_prefixes": ["203.0.113.0/24", "203.0.113.0/23"],
  "affected_origin_asns": [64496],
  "collateral_impact_count": 1,
  "transition_risk": "ordering_sensitive",
  "explanation": "The plan preserves intended coverage but broadens the authorization scope beyond the current route."
}
```

### Run summary contract

`ROAValidationSimulationRun.summary_json` must contain, at minimum, these stable keys:

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

### Run summary contract: meaning of each field

- `plan_fingerprint`
  Fingerprint used to detect staleness.

- `comparison_scope`
  Copied from the source reconciliation run.

- `provider_backed`
  Boolean indicating whether the plan targets a provider-backed workflow.

- `predicted_outcome_counts`
  Counts of public outcomes: `valid`, `invalid`, `not_found`.

- `plan_semantic_counts`
  Counts by plan semantic such as `create`, `withdraw`, `replace`, `reshape`.

- `approval_impact_counts`
  Counts by approval impact class.

- `scenario_type_counts`
  Counts by normalized scenario type.

- `affected_intended_route_count`
  Count of intended route outcomes materially affected.

- `affected_collateral_route_count`
  Count of collateral routes or coverage facts materially affected.

- `overall_approval_posture`
  Run-level posture resolved by severity:
  - `blocking` if any result is blocking
  - `acknowledgement_required` if none are blocking and at least one requires acknowledgement
  - `informational` otherwise

- `is_current_for_plan`
  Boolean. `true` only if this run matches the current plan fingerprint.

- `partially_constrained`
  Boolean. `true` if the service had to fall back because plan input was incomplete or ambiguous.

### Run summary example

```json
{
  "plan_fingerprint": "3d8c5d0d4d4e...",
  "comparison_scope": "provider_imported",
  "provider_backed": true,
  "predicted_outcome_counts": {
    "valid": 2,
    "invalid": 0,
    "not_found": 1
  },
  "plan_semantic_counts": {
    "replace": 1,
    "withdraw": 1,
    "create": 1
  },
  "approval_impact_counts": {
    "informational": 1,
    "acknowledgement_required": 1,
    "blocking": 1
  },
  "scenario_type_counts": {
    "replacement_preserves_coverage": 1,
    "replacement_broadens_authorization": 1,
    "withdraw_without_replacement_not_found": 1
  },
  "affected_intended_route_count": 2,
  "affected_collateral_route_count": 1,
  "overall_approval_posture": "blocking",
  "is_current_for_plan": true,
  "partially_constrained": false
}
```

## Internal Service Design

Slice 1 should prefer service-layer helpers and dataclasses. Do not add new Django models in Slice 1 unless a maintainer explicitly decides the JSON contract is not sufficient.

### Public entry point

Keep the current public entry point:

```python
def simulate_roa_change_plan(
    plan: rpki_models.ROAChangePlan | int,
    *,
    run_name: str | None = None,
) -> rpki_models.ROAValidationSimulationRun:
```

### Internal helpers to add

Add internal helpers shaped like this:

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

### Recommended dataclasses

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

These dataclasses are recommendations, not a required exact shape. The important requirement is that the service logic becomes explicit and testable.

## Classification Rules

Each `ROAChangePlanItem` must produce exactly one persisted `ROAValidationSimulationResult`.

When multiple scenarios apply, classify with this priority order:

1. any scenario that causes loss of intended coverage or leaves no covering authorization
   - `outcome_type='invalid'` or `outcome_type='not_found'`
   - `approval_impact='blocking'`

2. any scenario that preserves intended coverage but introduces broadened or collateral risk
   - `outcome_type='valid'`
   - `approval_impact='acknowledgement_required'`

3. straightforward create or replacement continuity with no collateral concern
   - `outcome_type='valid'`
   - `approval_impact='informational'`

4. incomplete or ambiguous input state
   - use the safest public fallback outcome supported by facts
   - mark `approval_impact='acknowledgement_required'`
   - set `partially_constrained=true` at run level if any item used this path

### Scenario-to-classification mapping

Use this table as the initial rule set:

| Scenario type | Intended outcome | Approval impact | Notes |
| --- | --- | --- | --- |
| `exact_create_validates` | `valid` | `informational` | Intended new authorization is well formed. |
| `replacement_preserves_coverage` | `valid` | `informational` | Intended route remains covered. |
| `withdraw_without_replacement_not_found` | `not_found` | `blocking` | Intended route loses authorization. |
| `replacement_broadens_authorization` | `valid` | `acknowledgement_required` | Intended route is safe, collateral scope is larger. |
| `withdraw_removes_unrelated_coverage` | `valid` or `not_found` | `acknowledgement_required` or `blocking` | Blocking if intended route also loses coverage. |
| `reshape_drops_specific_coverage` | `invalid` or `not_found` | `blocking` | Specific coverage is lost after reshape. |
| `insufficient_state_requires_review` | fallback | `acknowledgement_required` | Never silently mark as safe. |
| `provider_backed_transition_risk` | usually `valid` | `acknowledgement_required` | Used when ordering matters during provider-backed apply. |

## Coverage Analysis Contract

The simulation engine must build a simple before-and-after authorization view using:

- each plan item's `before_state_json`
- each plan item's `after_state_json`
- linked `ROAIntent` state when present
- the source reconciliation run
- any already-serialized published authorization state available from the plan context

The analysis must answer:

- which intended authorizations are covered before the plan
- which intended authorizations are covered after the plan
- which intended authorizations become uncovered
- which broader prefixes or specifics gain or lose coverage
- whether unaffected collateral routes could lose coverage due to a withdraw or reshape

Do not overbuild this. First-wave coverage reasoning can be conservative and deterministic. It does not need full validator behavior.

## Approval Integration Contract

Approval service changes are mandatory for Slice 1.

### New approval parameter

Extend `approve_roa_change_plan()` with:

```python
acknowledged_simulation_result_ids: list[int] | None = None
```

### Required approval checks

Before a draft ROA change plan becomes `APPROVED`, the service must:

1. load the latest simulation run using `plan.summary_json['simulation_run_id']`
2. fail if there is no recorded simulation run
3. fail if the run is not completed
4. compute the current plan fingerprint
5. fail if the run fingerprint does not match the current plan fingerprint
6. fail if any simulation result for that run is `blocking`
7. fail if any `acknowledgement_required` result is not covered by `acknowledged_simulation_result_ids`
8. allow approval only after the above checks pass

### Persistence for acknowledgements in Slice 1

Slice 1 should avoid creating new acknowledgement models unless required.

Acceptable temporary persistence options:

- mirror acknowledged simulation result ids into `plan.summary_json`
- include acknowledged simulation posture in `ApprovalRecord.notes`
- include a lightweight structured JSON fragment in approval notes if that is the least invasive path

The important requirement is behavioral:

- approval must enforce simulation posture
- accepted acknowledgements must be auditable enough to understand why approval succeeded

If this lightweight persistence proves awkward, promote it in a later slice.

## Failure Contract

If the simulation engine cannot classify a plan item confidently because input state is incomplete, it must not silently mark the item `valid`.

Instead it must:

- choose a deterministic fallback public outcome
- explain the uncertainty in normalized detail fields
- mark the item at least `acknowledgement_required` unless facts clearly support `blocking`
- mark the run as `partially_constrained`

## Surface Expectations

The first wave should deepen existing surfaces rather than invent a new UI family.

### Primary surfaces

- `ROAChangePlanViewSet.simulate`
- generated list and detail pages for `ROAValidationSimulationRun`
- generated list and detail pages for `ROAValidationSimulationResult`
- change-plan detail and summary surfaces

### Expected behavior by surface

- API simulate action returns the fresh simulation run and the latest summary
- change-plan detail surfaces can show the latest simulation posture
- approval surfaces explain why approval is blocked or what must be acknowledged
- run and result detail pages render operator-meaningful normalized explanation, not just raw JSON blobs

## Implementation Slices

The work is divided into slices so it can land incrementally without losing correctness.

### Slice 0: Freeze The Contract

Status:

- implemented

Objective:

- treat this guide as the fixed first-wave contract for implementation

Write set:

- this document
- `devrun/work_in_progress/netbox_rpki_enhancement_backlog.md` if summary wording needs to match

Outputs:

- fixed first-wave scenario catalog
- fixed approval-impact contract
- fixed summary and detail JSON contract

Verification:

- consistency review only

## Implementation Status

The first implementation wave described by this guide is complete.

- `Slice 0` landed as the fixed contract in this document and the aligned backlog wording.
- `Slice 1` landed as deterministic simulation classification, normalized summary and detail contracts, and simulation-aware approval enforcement.
- `Slice 2` landed as first-class model fields for run posture and result classification plus migration and backfill.
- `Slice 3` landed as richer API and detail surfaces for change plans, simulation runs, and simulation results.
- `Slice 4` landed as aggregate simulation posture rollups in summary and dashboard surfaces.
- `Slice 5` landed as structured simulation acknowledgement and approval audit persistence on approval records.
- `Slice 6` landed as cross-surface contract-alignment tests covering services, approval, API, UI, and reporting.

Repository readers should treat the remaining sections of this guide as the maintained contract for the implemented feature, not as an unstarted proposal.

### Slice 1: Deepen Simulation Service And Enforce Approval Posture

Status:

- implemented

Objective:

- replace the current item-by-item heuristic with deterministic scenario and coverage analysis
- emit normalized run and result contracts
- make approval consume current simulation posture

Primary files:

- `netbox_rpki/services/rov_simulation.py`
- `netbox_rpki/services/provider_write.py`
- `netbox_rpki/services/routing_intent.py`
- `netbox_rpki/tests/test_routing_intent_services.py`
- `netbox_rpki/tests/test_provider_write.py`

Expected outputs:

- plan fingerprint generation
- scenario builder
- classifier
- run summarizer
- simulation-aware approval enforcement

Verification:

- existing simple cases still classify correctly
- replacement continuity is explicitly tested
- broadened authorization is explicitly tested
- uncovered withdraw is explicitly tested
- incomplete input does not silently classify as safe
- approval denies missing, stale, or blocking simulation
- approval allows acknowledged acknowledgement-required results

Dependency rule:

- this is the first real implementation slice and should land before later UI refinements

### Slice 2: Add First-Class Model Fields Only If Needed

Status:

- implemented

Objective:

- add additive fields on simulation run or result models only if JSON-only storage proves too awkward for filtering, reporting, or audit

Primary files:

- `netbox_rpki/models.py`
- `netbox_rpki/migrations/`
- `netbox_rpki/tests/utils.py`
- targeted model tests

Verification:

- `manage.py makemigrations --check --dry-run netbox_rpki`
- focused model and factory tests

### Slice 3: Expose Richer API And Detail Surfaces

Status:

- implemented

Objective:

- expose normalized simulation explanation and posture through existing API and UI surfaces

Primary files:

- `netbox_rpki/detail_specs.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_views.py`

Verification:

- change-plan surfaces show latest simulation posture
- run and result surfaces show normalized explanation fields
- API and UI present consistent posture

### Slice 4: Add Aggregate Rollups

Status:

- implemented

Objective:

- make simulation posture visible above the individual plan level

Primary files:

- aggregate API summary surfaces
- dashboard or reporting surfaces already used for change-plan posture
- focused API and view tests

Verification:

- aggregate counts match simulation run data
- plans awaiting review because of simulation posture are visible

### Slice 5: Harden Acknowledgement And Audit Treatment

Status:

- implemented

Objective:

- improve how simulation acknowledgements are persisted and audited if Slice 1 lightweight persistence is not enough

Primary files:

- `netbox_rpki/services/provider_write.py`
- `netbox_rpki/views.py`
- `netbox_rpki/api/views.py`
- detail and summary surfaces
- focused approval tests

Verification:

- acknowledgement behavior is deterministic across web and API approval paths
- audit metadata is preserved and visible enough for operations review

### Slice 6: Release-Gate Hardening

Status:

- implemented

Objective:

- prove the richer simulation contract stays aligned across services, API, UI, and reporting

Primary files:

- docs
- testing matrices or release checklist updates
- broad focused tests

Verification:

- focused routing-intent, provider-write, API, and view suites
- broader plugin regression in the documented non-interactive NetBox environment

## Implementation Checklist For Slice 1

This is the recommended working order for a junior developer. Follow it unless your reviewer instructs otherwise.

### Step 1: Document the current baseline in tests

Before changing behavior, confirm you can identify the current tests and add or update tests that describe the desired new behavior.

Tasks:

- locate current simulation-related tests
- decide which tests need to be expanded versus added
- avoid changing approval behavior before adding failing tests for it

Deliverable:

- a clear failing test or test set for simulation posture and approval posture

### Step 2: Add plan fingerprint support

Tasks:

- implement `_build_plan_fingerprint(plan)`
- use deterministic serialization for item state
- store the fingerprint in run summary, result details, and plan summary

Deliverable:

- simulation runs can be identified as current or stale for the current plan contents

### Step 3: Build plan-level simulation context

Tasks:

- extract before and after authorization facts from plan items and linked context
- normalize those facts into a stable internal structure
- keep helper logic side-effect free where possible

Deliverable:

- one context object that can be reused across item classification

### Step 4: Build scenario detection

Tasks:

- add `_build_plan_item_scenarios()`
- detect at least the first-wave scenario catalog
- return deterministic scenarios from plan item state plus context

Deliverable:

- each plan item yields one or more normalized scenarios before classification

### Step 5: Build result classification

Tasks:

- add `_classify_plan_item_scenarios()`
- classify to one public outcome plus one approval impact
- generate normalized explanation fields

Deliverable:

- one `ClassifiedSimulationResult` per plan item

### Step 6: Build run summary generation

Tasks:

- count outcomes, semantics, approval impacts, and scenario types
- compute overall run posture
- compute whether the run is current for the plan
- compute `partially_constrained`

Deliverable:

- stable `summary_json` contract

### Step 7: Wire persistence in `simulate_roa_change_plan()`

Tasks:

- create the run in `RUNNING`
- classify all items
- persist one result per item
- persist the richer summary
- mirror the run id and fingerprint into plan summary

Deliverable:

- simulation run persistence matches the new contract

### Step 8: Enforce simulation posture during approval

Tasks:

- add `require_roa_change_plan_simulation_approvable()`
- call it from `approve_roa_change_plan()`
- add `acknowledged_simulation_result_ids`
- fail approval when the latest run is missing, stale, blocking, or unacknowledged

Deliverable:

- approval is simulation-dependent

### Step 9: Expose the new posture in existing payloads

Tasks:

- ensure latest plan serializer output includes the richer latest simulation summary
- ensure API simulate output remains stable
- do not overbuild UI work in the same commit if Slice 1 is already large

Deliverable:

- the service contract is visible enough for tests and reviewers

### Step 10: Verify and clean up

Tasks:

- remove dead helper logic if the old heuristic path is no longer needed
- verify no accidental model changes slipped in
- run focused tests

Deliverable:

- small, reviewable Slice 1 patch set

## Suggested Pseudocode For Slice 1

This pseudocode is intentionally high-level. It shows the intended control flow, not exact implementation details.

### Simulation flow

```python
def simulate_roa_change_plan(plan, *, run_name=None):
    plan = _normalize_plan(plan)
    fingerprint = _build_plan_fingerprint(plan)
    context = _build_plan_simulation_context(plan)

    run = ROAValidationSimulationRun.objects.create(
        ...,
        status=RUNNING,
        summary_json={"plan_fingerprint": fingerprint},
    )

    classified_results = []
    for item in plan.items.all():
        scenarios = _build_plan_item_scenarios(item, context)
        classified = _classify_plan_item_scenarios(item, scenarios, context)
        persist_result(run, item, classified, fingerprint)
        classified_results.append(classified)

    summary = _summarize_simulation_results(
        classified_results,
        plan=plan,
        plan_fingerprint=fingerprint,
    )

    persist_completed_run(run, summary)
    mirror_simulation_metadata_to_plan(plan, run, fingerprint)
    return run
```

### Approval flow

```python
def approve_roa_change_plan(..., acknowledged_simulation_result_ids=None):
    plan = _normalize_plan(plan)
    _require_approvable(plan)

    # Existing lint posture checks remain.
    posture = build_roa_change_plan_lint_posture(...)
    validate_lint_posture(posture)

    # New simulation posture checks are mandatory.
    simulation_run = require_roa_change_plan_simulation_approvable(
        plan,
        acknowledged_simulation_result_ids=acknowledged_simulation_result_ids,
    )

    with transaction.atomic():
        persist_plan_approval(...)
        persist_simulation_ack_if_needed(...)
        refresh_posture(...)
    return plan
```

## Test Matrix For Slice 1

At minimum, add or expand tests for these cases:

1. create item with complete after-state
   Expected result:
   - result outcome `valid`
   - approval impact `informational`

2. replacement pair preserving coverage
   Expected result:
   - result outcome `valid`
   - approval impact `informational`

3. withdraw with no replacement
   Expected result:
   - result outcome `not_found`
   - approval impact `blocking`
   - approval denied

4. broadened replacement
   Expected result:
   - result outcome `valid`
   - approval impact `acknowledgement_required`
   - approval denied until acknowledged

5. stale simulation fingerprint after plan mutation
   Expected result:
   - run marked not current
   - approval denied

6. incomplete simulation state
   Expected result:
   - no silent success
   - `acknowledgement_required`
   - run summary `partially_constrained=true`

7. latest simulation run summary reflects scenario and approval counts
   Expected result:
   - run summary contains stable keys from this guide

8. API simulate action returns richer summary contract
   Expected result:
   - plan payload includes `latest_simulation_summary`

9. plan creation still auto-runs simulation
   Expected result:
   - `simulation_run_id` and `simulation_plan_fingerprint` are mirrored into plan summary

## Practical Review Checklist

Before opening a PR or asking for review, verify:

- exactly one persisted simulation result exists per plan item
- result details use the normalized keys from this guide
- run summary uses the normalized keys from this guide
- approval checks simulation posture before status becomes `APPROVED`
- stale simulation runs are rejected
- acknowledgement-required simulation results are enforced
- old simple scenarios still work
- tests describe behavior, not just object existence

## Common Mistakes To Avoid

- do not key approval directly off `outcome_type`; use `approval_impact`
- do not silently treat incomplete input as safe
- do not create multiple simulation results per plan item in Slice 1
- do not add new top-level simulation models in Slice 1
- do not forget to mirror the current fingerprint into plan summary
- do not replace lint posture; add simulation posture alongside it
- do not depend on live provider requests for simulation classification

## Recommended Verification Commands

Use the smallest focused verification set that proves the slice.

For Slice 1:

- `pytest netbox_rpki/tests/test_routing_intent_services.py -q`
- `pytest netbox_rpki/tests/test_provider_write.py -q`

When API or view surfaces change:

- `pytest netbox_rpki/tests/test_api.py -q`
- `pytest netbox_rpki/tests/test_views.py -q`

If models or migrations change in later slices:

- `python manage.py makemigrations --check --dry-run netbox_rpki`

Release-gate verification should use the same documented non-interactive NetBox environment already used elsewhere in the repository.

## Recommended First Vertical Slice

The safest first implementation cut is intentionally narrow:

1. deepen `services/rov_simulation.py` to reason about replacement continuity, uncovered withdraws, broadened authorization, and incomplete state
2. keep the existing public outcome enum stable
3. add normalized explanation, approval-impact, and blast-radius facts in `details_json` and `summary_json`
4. make `approve_roa_change_plan()` consume current simulation posture
5. expose richer summary facts in existing payloads without inventing a second UI family

That cut is large enough to make Priority 5 operationally useful and small enough to keep the approval contract deterministic.

## Definition Of Done

Priority 5 should be considered implementation-complete only when all of the following are true:

1. simulation results explain predicted route-validation outcomes in operator terms rather than only counting `valid`, `invalid`, or `not_found`
2. the engine can reason about intended outcome and collateral blast radius for common ROA change-plan scenarios
3. approval requires a current simulation run and consumes normalized simulation posture deterministically
4. API and detail surfaces expose the latest simulation posture clearly enough for operators and tests
5. focused regression suites and broader plugin verification remain green

## Final Note For Implementers

If you are unsure whether a change belongs in Slice 1, use this rule:

- if it is required to make simulation posture correct and enforceable during approval, it belongs in Slice 1
- if it is mainly about nicer display, reporting, or cleaner audit storage, it probably belongs in a later slice

Start with correctness, determinism, and tests. Improve presentation after the core contract is trustworthy.
