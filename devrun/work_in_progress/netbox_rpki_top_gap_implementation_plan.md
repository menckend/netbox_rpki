# netbox_rpki Top Gap Implementation Plan

## Purpose

This plan turned the current gap analysis into an implementation sequence. As of 2026-04-15, the planned gaps from domains `N`, `K`, `A`, and `H` have been closed.

Completion summary:

1. Domain `N`: delegated/downstream authorization is operational in authored policy scope, delegated publication workflow services, approval actions, and delegated summaries.
2. Domain `K`: IRR coordination now includes route-set and AS-set authored-policy comparison plus actionable drafting.
3. Domain `A`: model-convention drift is no longer an active gap; the direct `NetBoxModel` inconsistency called out in the earlier analysis is no longer present.
4. Domain `H`: provider-gated testing now has an explicit opt-in `live-provider` lane and default-skip helpers for real-backend tests.

This plan was intentionally incremental. Each phase landed in reviewable slices with tests and operator-visible outcomes.

## Status

All phases below are now complete. No implementation items remain open in this plan.

## Recommended Priority Order

### P0. Decide the first operational meaning of delegated authorization

Status: complete

Retrospective outcome:

- `DelegatedAuthorizationEntity` is now an operational ownership subject.
- `ManagedAuthorizationRelationship` is now the scoping bridge between the local organization and delegated policy/workflow objects.
- `DelegatedPublicationWorkflow` became the first executable delegated workflow surface.
- Delegated scope also now carries into ROA/ASPA intent and change-plan semantics.

## Phase 1: Make Domain N Operational

Status: complete

### Goal

Move delegated/downstream authorization from “modeled and exposed” to “used by at least one service workflow.”

### Scope

Implement the first workflow slice as:

- delegated publication workflow lifecycle and validation
- authored CA relationship linkage to delegated workflow state
- operator-visible status summaries on delegated objects
- minimal governance around workflow approval/readiness

### Proposed code areas

- `netbox_rpki/models.py`
- `netbox_rpki/services/publication_state.py`
- `netbox_rpki/services/governance_summary.py`
- `netbox_rpki/services/governance_rollup.py`
- `netbox_rpki/views.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/tests/test_models.py`
- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/test_api.py`

### Deliverables

1. Add service-layer readiness/effectiveness logic for `DelegatedPublicationWorkflow`.
   Example outputs:
   - workflow state summary
   - missing prerequisites
   - linked authored CA relationships
   - linked provider account/publication touchpoints if present

2. Add explicit status rollups to delegated entities and managed relationships.
   Example:
   - active workflow count
   - draft workflow count
   - approval-required count
   - broken linkage count

3. Expose delegated workflow posture in the web detail view and REST serializer payloads.

4. Add tests that prove these models are no longer only registry objects.

### Non-goals for Phase 1

- No change yet to ROA/ASPA intent derivation.
- No provider write path branching on delegated ownership.
- No bulk migration of existing authored objects to delegated entities.

### Exit criteria

- Delegated-domain service modules exist and are exercised by tests.
- Delegated workflow state is visible in UI/API detail payloads.
- Domain `N` is operational rather than schema-only.

## Phase 2: Extend Domain N Into Intent and Publication Semantics

Status: complete

### Goal

Make delegated ownership affect policy behavior, not just metadata and workflow tracking.

### Decision checkpoint for you

Before coding this phase, confirm which semantic should come first:

- Recommended: publication/authorization ownership scoping
- Alternative: routing intent / ROA intent scoping

### Recommended implementation order

1. Add delegated ownership references to authored-policy-bearing objects where appropriate.
   Candidate objects:
   - `ROAIntent`
   - `ASPAIntent`
   - `ROAChangePlan`
   - `ASPAChangePlan`
   - possibly authored publication-side objects if ownership should attach there instead

2. Add service rules that keep delegated ownership distinct from local organization ownership.

3. Update summaries and dashboards to show when policy is operated on behalf of downstream entities.

4. Add API/UI filters for delegated ownership.

### Proposed code areas

- `netbox_rpki/models.py`
- `netbox_rpki/services/routing_intent.py`
- `netbox_rpki/services/aspa_intent.py`
- `netbox_rpki/services/provider_write.py`
- `netbox_rpki/forms.py`
- `netbox_rpki/filtersets.py`
- `netbox_rpki/tests/test_routing_intent_services.py`
- `netbox_rpki/tests/test_aspa_intent_services.py`
- `netbox_rpki/tests/test_provider_write.py`

### Outcome

- Delegated scope is carried through ROA/ASPA intent and change-plan semantics with validation and tests.

## Phase 3: Expand IRR Coordination Beyond Route Objects

Status: complete

### Goal

Complete IRR set-family work beyond the original route-object-centric path.

### Why this is third

- The current route-object path already provides operational value.
- Route-set and AS-set read-path coverage is already in place, so the remaining work is narrower than when this plan was first drafted.
- This is important, but still less foundational than making domain `N` real.
- It can be scoped cleanly without destabilizing existing ROA/ASPA governance.

### Suggested slice order

Completed scope:

1. `ROUTE_SET_MEMBERSHIP` read-only coordination and actionable drafting are implemented and tested.
2. `AS_SET_MEMBERSHIP` now compares imported IRR state against authored AS-set policy and supports actionable drafting.
3. Set-family plan items are carried through the existing reporting surfaces; `AUT_NUM_CONTEXT` and maintainer-supportability remain advisory where no safe write contract exists.

### Proposed code areas

- `netbox_rpki/services/irr_coordination.py`
- `netbox_rpki/services/irr_write.py`
- `netbox_rpki/views.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/tests/test_irr_coordination.py`
- `netbox_rpki/tests/test_irr_change_plan.py`
- `netbox_rpki/tests/test_irr_write_execution.py`

### Deliverables

1. Keep coordination results and summary JSON for route-set and AS-set families as first-class outputs.
2. Preserve advisory-only `NOOP` behavior when a family or source capability is not safely writable.
3. Add capability-gated draft change-plan generation for set-family deltas where automation is supported.
4. Carry set-family results through the existing plan/detail/reporting surfaces.

### Exit criteria

- Domain `K` is implemented with set-family authored-policy coverage and capability-gated write breadth.

## Phase 4: Normalize Older/Core Models Around Shared Conventions

Status: complete

### Goal

Reduce architectural drift in the model layer without changing user-facing behavior.

### Why this is fourth

- This is useful cleanup, but it is not the highest-value operator gap.
- It should follow workflow work, because it may touch many generated surfaces and migration behavior.

### Scope

1. Inventory models still inheriting directly from `NetBoxModel` while duplicating `tenant` and `comments`.
2. Decide whether to:
   - migrate them onto `RpkiStandardModel` / `NamedRpkiStandardModel`, or
   - explicitly document why they remain exceptions.
3. Add tests or assertions around model convention consistency where realistic.

### Proposed code areas

- `netbox_rpki/models.py`
- `netbox_rpki/tests/test_models.py`
- possibly `netbox_rpki/tests/test_api.py` and `test_views.py` if serializer/form output changes

### Outcome

- The previously noted direct `NetBoxModel` convention drift is no longer an active implementation gap.

## Phase 5: Enforce Provider-Gated Test Separation More Explicitly

Status: complete

### Goal

Make the documented local-fixture-first workflow mechanically visible in test commands and CI lanes.

### Scope

1. Define explicit test categories:
   - local fixture / structural
   - fixture-backed provider workflows
   - opt-in live-provider backend workflows

2. Ensure `devrun` command paths keep live/provider-gated lanes optional.

3. Enforce default-skip behavior for unavailable live/provider credentials.

### Proposed code areas

- `LOCAL_DEV_SETUP.md`
- `CONTRIBUTING.md`
- `devrun/dev.sh` or related wrappers if present
- test settings or lane-selection helpers
- CI configuration if housed in-repo

### Deliverables

1. Clear lane names and explicit skip/opt-in behavior.
2. Less ambiguity around what `full` means in local development.
3. Lower chance of accidental coupling between core development and provider-gated environments.

## Completion Sequence

Implemented slice order:

1. Domain `N` operational delegated workflow services and summaries.
2. Domain `K` route-set actionable drafting.
3. Domain `K` authored AS-set model plus AS-set actionable drafting.
4. Domain `N` delegated scope carry-through into intent and change-plan semantics.
5. Domain `A` cleanup reclassified as closed after model inventory confirmed the earlier direct-`NetBoxModel` drift was no longer present.
6. Domain `H` live-provider test-lane enforcement and documentation alignment.

## Validation

The plan was validated incrementally with:

- `./dev.sh test fast`
- `./dev.sh test contract`
- focused delegated, IRR, and provider-lane tests for the touched slices
- explicit live-provider helper tests and wrapper-lane verification

## Current State

This document is now a completion record, not an active backlog. If new work is added later, it should start from a fresh gap analysis rather than reopening these already-closed plan items.
