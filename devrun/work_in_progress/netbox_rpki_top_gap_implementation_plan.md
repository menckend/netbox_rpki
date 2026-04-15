# netbox_rpki Top Gap Implementation Plan

## Purpose

This plan turns the current gap analysis into an implementation sequence. It focuses on the highest-value remaining gaps:

1. Domain `N`: downstream and delegated authorization is modeled but not operationally integrated.
2. Domain `K`: IRR coordination is still centered on route-object drift rather than richer IRR policy families.
3. Domain `A`: model-convention consistency is uneven in older/core models.
4. Domain `H`: provider-gated live-backend behavior is documented, but test-lane enforcement is still mostly social.

This plan is intentionally incremental. Each phase should land in a reviewable PR-sized slice with tests and clear operator-visible outcomes.

## Recommended Priority Order

### P0. Decide the first operational meaning of delegated authorization

Why first:

- Domain `N` is the only remaining strategic gap that is mostly schema-only.
- It also affects how later work should treat provider scoping, authored CA relationships, and publication workflows.
- Without this decision, implementation risks adding more passive models without behavior.

Decision checkpoint for you:

- Choose the first workflow where delegated/downstream entities must matter.
- Recommended first choice: make delegated authorization affect authored policy and publication workflows before changing intent derivation semantics.

Recommended choice details:

- Treat `DelegatedAuthorizationEntity` as an operational ownership subject for authored CA/publication relationships.
- Treat `ManagedAuthorizationRelationship` as the governance and scoping bridge from local organization to delegated entity.
- Treat `DelegatedPublicationWorkflow` as the first executable workflow surface.
- Defer changing ROA/ASPA intent derivation semantics until the publication and ownership model is proven.

Why this recommendation:

- It is the smallest change that makes domain `N` real.
- It aligns with the existing `AuthoredCaRelationship` and delegated-publication models.
- It avoids destabilizing the already large routing-intent and reconciliation pipeline too early.

## Phase 1: Make Domain N Operational

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

- At least one delegated-domain service module exists and is exercised by tests.
- Delegated workflow state is visible in UI/API detail payloads.
- Domain `N` can be reclassified from `Partial` to at least `Mostly implemented`.

## Phase 2: Extend Domain N Into Intent and Publication Semantics

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

### Risk

- This phase touches the highest-complexity service code in the repo.
- It should not begin until Phase 1 establishes a clear ownership model and vocabulary.

## Phase 3: Expand IRR Coordination Beyond Route Objects

### Goal

Bring route-set and AS-set coordination from modeled inventory into actionable coordination behavior.

### Why this is third

- The current route-object path already provides operational value.
- This is important, but less foundational than making domain `N` real.
- It can be scoped cleanly without destabilizing existing ROA/ASPA governance.

### Suggested slice order

1. Add read-only coordination results for `ROUTE_SET_MEMBERSHIP`.
   First land comparison and reporting only.

2. Add read-only coordination results for `AS_SET_MEMBERSHIP`.
   Again, comparison/reporting before write plans.

3. Add actionable change-plan generation only after read-only comparison is stable.
   Start with `NOOP` and advisory output if source capability is limited.

4. Leave `AUT_NUM_CONTEXT` and maintainer-supportability as advisory unless a clear write contract is available.

### Proposed code areas

- `netbox_rpki/services/irr_coordination.py`
- `netbox_rpki/services/irr_write.py`
- `netbox_rpki/views.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/tests/test_irr_coordination.py`
- `netbox_rpki/tests/test_irr_change_plan.py`
- `netbox_rpki/tests/test_irr_write_execution.py`

### Deliverables

1. Coordination results created for route-set and AS-set families.
2. Summary JSON and dashboard attention counts include those families meaningfully.
3. If write automation is supported, draft change-plan items can be generated.
4. If write automation is not supported, plans still explain why the result is advisory-only.

### Exit criteria

- Domain `K` can be reclassified from “mostly implemented, route-object-centric” to “implemented with advisory/write breadth clearly capability-gated.”

## Phase 4: Normalize Older/Core Models Around Shared Conventions

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

### Risk

- This may require careful migration generation and surface regression checks.
- It should be done as small batches, not a repo-wide mechanical rewrite.

## Phase 5: Enforce Provider-Gated Test Separation More Explicitly

### Goal

Make the documented local-fixture-first workflow mechanically visible in test commands and CI lanes.

### Scope

1. Define explicit test categories:
   - local fixture / structural
   - live Krill backend
   - provider-gated delta tests

2. Ensure `devrun` command paths keep provider-gated lanes optional.

3. Document and, if useful, enforce skip behavior for unavailable live/provider credentials.

### Proposed code areas

- `LOCAL_DEV_SETUP.md`
- `CONTRIBUTING.md`
- `devrun/dev.sh` or related wrappers if present
- test settings or lane-selection helpers
- CI configuration if housed in-repo

### Deliverables

1. Clear lane names and explicit skip/opt-in behavior.
2. Less ambiguity around what “full” means in local development.
3. Lower chance of accidental coupling between core development and provider-gated environments.

## Concrete Delivery Sequence

Recommended PR order:

1. `PR1`: Domain N phase 1
   Outcome:
   delegated workflow posture becomes real and test-backed.

2. `PR2`: Domain K route-set coordination read path
   Outcome:
   IRR coordination covers another family without write-risk.

3. `PR3`: Domain K AS-set coordination read path
   Outcome:
   broader IRR policy visibility.

4. `PR4`: Domain N phase 2
   Outcome:
   delegated ownership starts affecting policy semantics.

5. `PR5`: Domain A convention cleanup batch 1
   Outcome:
   reduce oldest model-layer inconsistencies.

6. `PR6`: Domain H test-lane enforcement/docs alignment
   Outcome:
   better development and CI discipline.

## Test Strategy Per Phase

Use the existing project workflow from `LOCAL_DEV_SETUP.md`:

- structural and contract checks via `./dev.sh test fast`
- registry/UI/API/GraphQL contract coverage via `./dev.sh test contract`
- focused Django test labels for the touched domain
- `./dev.sh test full` before merging larger service-layer phases

Suggested focused lanes:

- Phase 1 and 2:
  `./dev.sh test netbox_rpki.tests.test_models netbox_rpki.tests.test_views netbox_rpki.tests.test_api`

- Phase 3:
  `./dev.sh test netbox_rpki.tests.test_irr_coordination netbox_rpki.tests.test_irr_change_plan netbox_rpki.tests.test_irr_write_execution`

- Phase 4:
  `./dev.sh test netbox_rpki.tests.test_models netbox_rpki.tests.test_api netbox_rpki.tests.test_views`

- Phase 5:
  targeted wrapper and lane verification, plus doc updates

## Decision Points That Require Your Check-In

Per your instruction, these are the points where implementation should pause for confirmation:

1. Before Phase 1:
   confirm the first operational meaning of delegated authorization.

2. Before Phase 2:
   confirm whether delegated ownership should first affect publication ownership or routing intent semantics.

3. Before any Phase 4 refactor that changes inheritance on existing models:
   confirm whether you want migration churn now or prefer exception documentation first.

4. Before Phase 5 if CI changes are needed:
   confirm whether you want only local wrapper/documentation changes or CI policy changes too.

## Recommended Immediate Next Step

Start with `PR1`: Domain N phase 1, using delegated publication workflows as the first operational slice.

That is the smallest change that closes the largest remaining strategic gap without destabilizing the existing ROA/ASPA and IRR machinery.
