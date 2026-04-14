# NetBox RPKI Plugin: Bulk Generation and Templating Plan

Prepared: April 13, 2026

## Objective

Implement backlog Priority 6 as a compatibility-preserving expansion of the existing routing-intent workflow.

The target is not a second authoring system. The target is a reusable template and regeneration layer that feeds the current intent pipeline:

1. authored policy
2. intent derivation
3. reconciliation
4. linting
5. simulation
6. change planning
7. approval and apply

This document carries the detailed proposed models, service contracts, surface contracts, and execution slicing. The backlog remains the short status-and-priority view.

## Relationship To Existing Architecture

This plan must stay aligned with the plugin's current architecture rules:

- Django models and migrations remain explicit.
- Standard CRUD surfaces remain registry-driven.
- Domain behavior stays in explicit services, jobs, and custom workflow actions.
- Bulk authoring must not bypass lint, simulation, approval, or provider-execution audit paths.

This plan builds directly on the current routing-intent stack rather than replacing it.

## Current-State Baseline

The plugin already has the core operator workflow substrate needed for Priority 6.

Existing authored and derived policy objects:

- `RoutingIntentProfile`
- `RoutingIntentRule`
- `ROAIntentOverride`
- `IntentDerivationRun`
- `ROAIntent`

Existing execution and governance objects:

- `ROAReconciliationRun`
- `ROAIntentResult`
- `PublishedROAResult`
- `ROALintRun`
- `ROAValidationSimulationRun`
- `ROAChangePlan`
- `ROAChangePlanItem`

Existing service entry points already provide the right execution spine:

- `netbox_rpki/services/routing_intent.py`
- `netbox_rpki/services/roa_lint.py`
- `netbox_rpki/services/rov_simulation.py`
- `netbox_rpki/services/provider_write.py`
- `netbox_rpki/jobs.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/views.py`
- `netbox_rpki/detail_specs.py`

Existing focused tests already exercise the current routing-intent and change-plan path and should be extended rather than bypassed:

- `netbox_rpki/tests/test_routing_intent_services.py`
- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_graphql.py`
- registry-driven smoke suites described in `devrun/work_in_progress/netbox_rpki_testing_strategy_matrix.md`

## Design Boundaries

The implementation should stay inside these boundaries unless a later design pass explicitly changes them.

- Keep authored policy distinct from derived state. Templates define policy. `ROAIntent` remains generated output.
- Keep the execution boundary at `RoutingIntentProfile`. Templates and bindings feed profiles instead of replacing them.
- Keep provider-facing writes downstream of reconciliation and change planning only.
- Keep the first wave ROA-specific. Generalization to ASPA or broader intent families can come later if the ROA contract proves stable.
- Prefer typed fields for common semantics and reserve JSON for small extensibility seams only.
- Avoid adding a bulk-only approval model in the first wave. Bulk workflows should fan out to ordinary `ROAChangePlan` governance.

## Resolved First-Wave Decisions

The following design questions are now considered resolved for the first implementation wave.

### 1. First-wave model names are fixed

Use these exact model names in the first wave:

- `RoutingIntentTemplate`
- `RoutingIntentTemplateRule`
- `RoutingIntentTemplateBinding`
- `RoutingIntentException`
- `BulkIntentRun`
- `BulkIntentRunScopeResult`

Do not introduce alternate names such as "policy set", "compiled template", or "bulk plan" at the model layer in the first wave. Those concepts can remain service-layer or summary vocabulary when needed.

### 2. One binding belongs to exactly one profile

`RoutingIntentTemplateBinding` is the join from one reusable template to one `RoutingIntentProfile` execution context.

That means:

- one template can be reused across many profiles
- reuse happens through multiple binding rows, not one shared binding row
- profile-specific parameterization lives on the binding
- profile-specific precedence remains local to the profile rather than becoming cross-profile shared state

This keeps `RoutingIntentProfile` as the stable execution boundary and prevents one profile's binding-state drift from becoming another profile's accidental drift.

### 3. Precedence is layered, not one global weight namespace

The compiler should not treat local rules, template rules, exceptions, and legacy overrides as one flat ordered list. The precedence contract for the first wave is:

1. template-derived rule material establishes the reusable baseline
2. profile-native `RoutingIntentRule` rows refine that baseline for one profile
3. typed `RoutingIntentException` rows apply explicit scoped divergence from the baseline-plus-local policy
4. existing `ROAIntentOverride` rows remain the final compatibility shim during the transition period

Within each layer, ordering remains deterministic and mirrors the current routing-intent style:

- lower weight or priority applies first
- higher weight or priority wins later on conflict
- tie-breaks use stable name and primary-key ordering

For the template layer specifically:

- bindings are ordered by `binding_priority`, then template name, then binding primary key
- rules inside a binding are ordered by `weight`, then name, then primary key
- when two template bindings express conflicting policy for the same prefix, the higher-priority binding wins, but the compiler must emit a warning into the compiled summary so the conflict is visible

For the local profile layer:

- local `RoutingIntentRule` rows always outrank template-derived rules when both match the same prefix and set the same semantic field
- this is deliberate: templates provide reusable defaults, while local profile rules are the per-profile refinement seam

For the exception and override layers:

- typed exceptions outrank both template and local rule material
- legacy `ROAIntentOverride` rows outrank typed exceptions only for compatibility during the transition period
- no new Priority 6 operator workflow should create `ROAIntentOverride` rows automatically; new bulk and template workflows should create `RoutingIntentException` rows instead

### 4. Template versioning is explicit and fingerprinted

The first wave uses both an explicit version number and a deterministic fingerprint.

`template_version` exists for operator-facing audit and review semantics:

- it is a monotonically increasing integer on `RoutingIntentTemplate`
- it increments only when materially relevant policy changes occur on the template or its active rule set
- non-material edits such as description or comments should not force a version bump

`template_fingerprint` exists for exact change detection:

- it is a deterministic hash of the materially relevant template fields plus active template-rule content in stable order
- it is used by regeneration logic, no-op detection, and child-run comparison
- it should ignore non-material presentation-only edits

Binding and bulk execution comparisons should use a compiled fingerprint that combines:

- the template fingerprint
- bound parameter values
- selector narrowing
- relevant exception state
- the profile's own effective selector inputs that affect derivation output

### 5. Typed exceptions become the Priority 6 extension path

`RoutingIntentException` is the first-wave model for bulk-authoring exception cases. `ROAIntentOverride` remains supported for compatibility, but it is not the preferred extension seam for new Priority 6 features.

That means:

- new traffic-engineering, anycast, mitigation, and customer-edge exceptions should be represented as `RoutingIntentException`
- the compiler still consumes `ROAIntentOverride` as a final compatibility layer so existing operator behavior remains valid
- any future migration away from `ROAIntentOverride` can happen later, after the typed exception path is proven and existing data can be mapped safely

### 6. Slice 0 is now a recorded contract, not an open design phase

The "freeze the contract" slice is complete at the design level through this document. Implementation work should treat these decisions as fixed unless a later decision log explicitly reopens one of them.

## Proposed Model Contract

### Model Overview

| Model | Purpose | Key fields or behaviors | Notes |
| --- | --- | --- | --- |
| `RoutingIntentTemplate` | Reusable authored policy template | `organization`, `name`, `status`, `enabled`, `description`, `template_version`, `template_fingerprint` | Top-level reusable policy object. Owns lifecycle and stable identity. |
| `RoutingIntentTemplateRule` | Ordered rule material beneath a template | `template`, `weight`, `action`, `address_family`, selector fragments, origin strategy, max-length strategy, `enabled` | Mirrors `RoutingIntentRule` semantics closely so compilation stays predictable. |
| `RoutingIntentTemplateBinding` | Attaches one template to one execution context | `template`, `intent_profile`, `enabled`, `binding_priority`, typed parameter fields, selector narrowing, `state`, `last_compiled_fingerprint`, `summary_json` | One binding belongs to exactly one profile. Template reuse across profiles happens through multiple bindings. |
| `RoutingIntentException` | Typed scoped exception against baseline template behavior | `organization`, optional `intent_profile`, optional `template_binding`, `exception_type`, `effect_mode`, scope fields, override fields, `starts_at`, `ends_at`, `reason`, approval metadata, `enabled` | Prefer one explicit model family over reusing free-form text on overrides. |
| `BulkIntentRun` | Aggregate bulk generation or regeneration execution record | `organization`, `status`, `trigger_mode`, target summary, `baseline_fingerprint`, `resulting_fingerprint`, `started_at`, `completed_at`, `summary_json` | Captures one operator-visible bulk action. |
| `BulkIntentRunScopeResult` | Rollup record for one operator-meaningful segment inside a bulk run | `bulk_run`, optional `intent_profile`, optional `template_binding`, grouping fields, linked `IntentDerivationRun`, linked `ROAReconciliationRun`, linked `ROAChangePlan`, counts, `summary_json` | Keeps aggregate drill-down navigable without flattening everything into one JSON blob. |

### Recommended Field Semantics

`RoutingIntentTemplate` should own reusable policy identity, explicit version state, and deterministic policy fingerprint, but not execution-state drift tracking. Drift and stale-state reporting belong on the binding or bulk-run side.

`RoutingIntentTemplateRule` should stay structurally close to `RoutingIntentRule` so the compiler can produce one effective rule set without introducing a second matching language.

`RoutingIntentTemplateBinding` should carry the typed runtime knobs that differ by profile or scope, and it should remain the only place where one template becomes profile-specific, for example:

- origin ASN source or override
- max-length mode or explicit override
- selector narrowing fragments
- human-readable binding label
- binding priority and enabled state

`RoutingIntentException` should be typed and narrow. It is the preferred Priority 6 exception seam, while `ROAIntentOverride` remains a compatibility layer. The initial exception classes should map directly to the backlog:

- traffic engineering
- anycast
- mitigation
- customer edge

Each exception should also declare its effect mode explicitly:

- broaden
- narrow
- suppress
- temporary replacement

`BulkIntentRun` and `BulkIntentRunScopeResult` should remain aggregate orchestration artifacts. They should not replace the canonical child workflow records already used elsewhere in the plugin.

### Models To Avoid In The First Wave

Do not add these in the first implementation wave unless a real gap proves them necessary:

- a persisted compiled-policy model
- a bulk-only approval model
- a free-form template DSL model
- a generic JSON-only parameter model for common binding semantics

Use service-layer dataclasses for compiled intermediate state instead.

## Proposed Service Contracts

### Service Overview

| Contract | Likely module | Inputs | Outputs | Purpose |
| --- | --- | --- | --- | --- |
| effective policy assembly | `services/routing_intent_templates.py` or `services/routing_intent.py` | profile, active bindings, active exceptions, as-of time | deterministic intermediate rule set plus fingerprint and warnings | Builds one effective authored policy before intent derivation. |
| template preview | `services/routing_intent_templates.py` | template binding or profile, optional baseline | compiled rule summary, would-emit summary, no-write or preview-write result | Lets operators preview before regeneration. |
| intent derivation extension | `services/routing_intent.py` | profile plus optional compiled policy | ordinary `IntentDerivationRun` and `ROAIntent` rows | Keeps existing pipeline entry points stable. |
| regeneration evaluation | `services/routing_intent_regeneration.py` | binding or profile, prior fingerprint, current compiled policy | no-op or intent-drift or publishable-drift classification | Prevents noisy reruns and explains why regeneration is needed. |
| exception resolution | `services/routing_intent_exceptions.py` | profile, binding, time window | active exceptions plus normalized effects | Keeps exception logic explicit and reusable. |
| bulk orchestration | `services/bulk_routing_intent.py` | target profiles or bindings, trigger mode, scope filters | `BulkIntentRun` plus `BulkIntentRunScopeResult` rows and linked child workflow artifacts | Coordinates bulk generation without inventing a second workflow path. |
| summary projection | same modules above | compiled outputs and child workflow records | stable `summary_json` payloads on binding and bulk-run records | Supports UI and API rollups without recalculating logic in views. |

### Effective Policy Assembly Contract

The compiler should resolve the final authored policy in this layered order:

1. active template bindings and their active template rules
2. active profile-native `RoutingIntentRule` rows
3. active typed exceptions
4. existing `ROAIntentOverride` rows as the final compatibility layer

The contract should return a deterministic intermediate object that includes:

- compiled rules in final evaluation order
- provenance for each compiled rule
- effective selector scope
- effective fingerprint
- warnings about precedence conflicts or invalid bindings
- a normalized summary of which layer won for each materially changed rule decision

That intermediate object should be serializable enough for focused tests to assert directly.

The intermediate object should also preserve enough structured data to answer these questions without reparsing explanation text:

- which template bindings participated
- whether a local profile rule overrode template baseline behavior
- whether an exception or legacy override changed the final outcome
- whether any conflicting bindings were present even if one won deterministically

### Regeneration Contract

The regeneration evaluator should compare current compiled-policy fingerprint against the prior compiled-policy fingerprint captured on a binding or prior run.

It should classify the outcome into one of these states:

- no-op
- intent drift only
- exception conflict drift
- publishable change-plan drift
- blocked by invalid template or binding configuration

The evaluator should also produce a normalized reason summary such as:

- template rule changed
- template version changed
- template status changed
- binding parameters changed
- selector narrowing changed
- exception expired
- inventory scope changed

It should additionally distinguish between:

- materially changed policy with the same template version not allowed in normal operation
- non-material metadata change with no compiled-policy drift

The intended rule is that materially changed template policy bumps `template_version` and changes `template_fingerprint`. If a materially changed fingerprint appears without the version incrementing, that should be treated as an invalid template state and surfaced as a warning or hard validation error depending on the write path.

### Bulk Orchestration Contract

The first-wave bulk contract should orchestrate existing child artifacts rather than replacing them.

For each target profile or binding set, the orchestrator should be able to:

1. compile effective policy
2. derive intents
3. reconcile against the requested comparison scope
4. optionally create a draft change plan
5. attach lint and simulation outputs through existing services
6. summarize the result at the bulk-run level and the scope-result level

The first version can stop at preview and draft-plan generation. It does not need a bulk apply path that skips ordinary per-plan approval.

## Proposed Surface Contract

### Registry-Driven CRUD Surfaces

The following new object families should participate in the standard generated surfaces unless a later decision narrows the first wave further:

- `RoutingIntentTemplate`
- `RoutingIntentTemplateRule`
- `RoutingIntentTemplateBinding`
- `RoutingIntentException`
- `BulkIntentRun`
- `BulkIntentRunScopeResult`

That means additions to the explicit model layer and then normal registry-driven exposure through:

- `netbox_rpki/object_registry.py`
- `netbox_rpki/forms.py`
- `netbox_rpki/filtersets.py`
- `netbox_rpki/tables.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/api/urls.py`
- `netbox_rpki/graphql/filters.py`
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/graphql/schema.py`
- `netbox_rpki/navigation.py`

### Rich Detail And Custom Action Surfaces

The top-level objects that most likely need explicit `DetailSpec` coverage and custom actions are:

- `RoutingIntentTemplate`
- `RoutingIntentTemplateBinding`
- `BulkIntentRun`

The most likely first custom operator actions are:

- preview a template binding
- regenerate one binding
- regenerate one profile across all active bindings
- create a bulk run for a filtered set of profiles or bindings

These should be implemented as explicit custom actions in the current pattern used for routing-intent and change-plan workflow actions, not hidden inside the generic CRUD builders.

### Reporting Contract

At minimum, the reporting layer should surface:

- active template count
- active binding count
- stale binding count
- regeneration-pending binding count
- active exception count by class
- near-expiry exception count
- latest bulk-run outcome per profile or binding
- bulk plans blocked by lint or simulation versus merely awaiting review

## Execution Model

### Ownership Rules

This work touches the same high-conflict files called out elsewhere in the repo's working documents. Use these ownership rules during implementation:

- one owner at a time for `netbox_rpki/models.py` and `netbox_rpki/migrations/`
- one owner at a time for the shared surface files: `object_registry.py`, `detail_specs.py`, `api/views.py`, `api/serializers.py`, `graphql/types.py`, and the registry-driven test files
- service-layer work can be split only if the write sets are clearly disjoint
- docs and checklist updates can run in parallel only if they do not also edit the active shared surface window

### Slice 0: Freeze The Contract

Objective:

- record the resolved naming, precedence, versioning, and compatibility decisions in the implementation notes and treat them as fixed input for code work

Likely write set:

- this plan
- `devrun/work_in_progress/netbox_rpki_enhancement_backlog.md`
- optional decision-log follow-up notes if the lead wants one

Outputs:

- one recorded naming and precedence contract
- one recorded minimal first-wave model set
- one recorded vertical-slice sequence

Verification:

- no code verification required beyond consistency review

Dependency rule:

- design-complete in this document; no code slice should reopen these questions without an explicit later decision

### Slice 1: Land The Template And Bulk Schema Substrate

Objective:

- add the explicit authored-policy and orchestration models needed for later slices
- extend factories and test helpers so later slices can build the new shape intentionally

Likely write set:

- `netbox_rpki/models.py`
- `netbox_rpki/migrations/`
- `netbox_rpki/tests/utils.py`
- `netbox_rpki/tests/registry_scenarios.py`
- targeted model tests

Outputs:

- `RoutingIntentTemplate`
- `RoutingIntentTemplateRule`
- `RoutingIntentTemplateBinding`
- `RoutingIntentException`
- `BulkIntentRun`
- `BulkIntentRunScopeResult`
- any required enums or choices

Verification:

- `manage.py makemigrations --check --dry-run netbox_rpki`
- focused model and factory tests

Dependency rule:

- must land before generated surfaces or service compilation work

### Slice 2: Expose Standard CRUD Surfaces For New Authored Objects

Objective:

- make the new authored objects visible and manageable through the standard generated surface family

Likely write set:

- `netbox_rpki/object_registry.py`
- `netbox_rpki/forms.py`
- `netbox_rpki/filtersets.py`
- `netbox_rpki/tables.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/api/urls.py`
- `netbox_rpki/graphql/filters.py`
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/graphql/schema.py`
- `netbox_rpki/navigation.py`
- generated-surface smoke tests

Outputs:

- standard list, detail, create, edit, delete, API, GraphQL, and navigation exposure for the new models

Verification:

- focused `test_forms`, `test_filtersets`, `test_tables`, `test_urls`, `test_navigation`, and `test_graphql`
- registry-wide surface-contract checks for mutability and route presence

Dependency rule:

- depends on Slice 1

### Slice 3: Land Effective-Policy Compilation And Preview

Objective:

- compile template and local rule material into the existing derivation path without changing the downstream workflow contract

Likely write set:

- `netbox_rpki/services/routing_intent.py`
- new helper module such as `netbox_rpki/services/routing_intent_templates.py`
- `netbox_rpki/services/__init__.py`
- `netbox_rpki/tests/test_routing_intent_services.py`

Outputs:

- effective-policy assembly service
- template preview service contract
- provenance capture on emitted intent or derivation summary output
- layered precedence behavior matching the resolved contract in this document

Verification:

- local-rule-only profiles still match current derivation output
- template-only profiles derive deterministically
- mixed local-plus-template profiles honor the documented precedence contract
- typed exceptions and legacy overrides can be asserted as later layers in focused tests even if their dedicated surface slices land afterward

Dependency rule:

- depends on Slice 1
- can overlap with late Slice 2 read-only review but not with concurrent edits to the same service files

### Slice 4: Add Regeneration State And Stale Detection

Objective:

- make regeneration explicit, quiet when inputs have not changed, and explainable when they have

Likely write set:

- `netbox_rpki/models.py` if additional state fields are required
- additive migration if needed
- new helper module such as `netbox_rpki/services/routing_intent_regeneration.py`
- `netbox_rpki/services/routing_intent.py`
- `netbox_rpki/tests/test_routing_intent_services.py`

Outputs:

- stale or current or regeneration-pending state on bindings or bulk-run artifacts
- normalized regeneration reason summaries
- comparison to prior baseline fingerprints
- validation that version and fingerprint semantics stay aligned

Verification:

- unchanged inputs produce a no-op classification
- changed template inputs produce explainable drift classification
- regenerated outputs remain idempotent across repeated runs
- material template policy changes bump both version and fingerprint
- non-material metadata changes do not create false-positive regeneration drift

Dependency rule:

- depends on Slice 3

### Slice 5: Add Typed Exceptions

Objective:

- model the common operator exception cases explicitly and feed them into the compiler without dissolving baseline policy structure

Likely write set:

- `netbox_rpki/models.py`
- `netbox_rpki/migrations/`
- new helper module such as `netbox_rpki/services/routing_intent_exceptions.py`
- `netbox_rpki/services/routing_intent.py`
- generated surfaces for exception objects
- detail specs if a richer exception detail view is useful
- `netbox_rpki/tests/test_routing_intent_services.py`
- surface tests for exception exposure

Outputs:

- typed exception classes and effect modes
- expiry-aware exception evaluation
- narrow scope matching and invalidation behavior
- explicit compatibility with existing `ROAIntentOverride` rows as the final precedence layer

Verification:

- exceptions attach only to intended scope
- expired exceptions reopen review
- exception effects remain visible in generated intent explanation and summaries

Dependency rule:

- depends on Slice 3
- may land before or after Slice 4 if the field design is stable, but both must land before bulk orchestration is considered complete

### Slice 6: Add Bulk Run Aggregation And Draft-Plan Fan-Out

Objective:

- coordinate multiple binding or profile executions into one operator-visible bulk workflow while preserving the child workflow artifacts

Likely write set:

- new helper module such as `netbox_rpki/services/bulk_routing_intent.py`
- `netbox_rpki/services/__init__.py`
- `netbox_rpki/services/routing_intent.py`
- `netbox_rpki/jobs.py`
- management command additions if command coverage is desired in the same slice
- `netbox_rpki/tests/test_routing_intent_services.py`

Outputs:

- `BulkIntentRun` orchestration service
- `BulkIntentRunScopeResult` rollup population
- optional draft `ROAChangePlan` creation for each qualifying child reconciliation result

Verification:

- bulk run can stop at preview without applying
- aggregate counts match underlying child derivation, reconciliation, lint, simulation, and plan outputs
- provider-backed and local scopes stay distinguishable in summaries

Dependency rule:

- depends on Slices 3 through 5

### Slice 7: Expose Custom Workflow Actions And Rich Detail Surfaces

Objective:

- make the new bulk and template workflow reachable through intentional operator surfaces

Likely write set:

- `netbox_rpki/api/views.py`
- `netbox_rpki/views.py`
- `netbox_rpki/urls.py`
- `netbox_rpki/detail_specs.py`
- template updates under `netbox_rpki/templates/netbox_rpki/`
- action and permission tests in API and view suites

Outputs:

- preview binding action
- regenerate binding or profile action
- create bulk run action
- rich detail pages for template, binding, and bulk-run objects

Verification:

- action routes exist and enforce permissions correctly
- detail summaries link coherently to child derivation, reconciliation, and plan records
- UI actions and API actions express the same workflow semantics

Dependency rule:

- depends on Slices 2 through 6

### Slice 8: Reporting, Hardening, And Release-Gate Verification

Objective:

- surface stale-state and bulk health in aggregate reporting and prove that the new contract is stable enough for wider use

Likely write set:

- reporting or dashboard surfaces that already summarize operations state
- `netbox_rpki/detail_specs.py`
- list-view summary surfaces as needed
- backlog and supporting docs
- broad verification suites

Outputs:

- stale-binding and exception-expiry rollups
- bulk outcome rollups
- updated docs and testing expectations

Verification:

- focused routing-intent, API, GraphQL, and view suites
- registry-wide surface-contract suites
- full plugin suite in the documented non-interactive NetBox environment

Dependency rule:

- depends on all prior slices

## Recommended First Vertical Slice

The safest first implementation cut is intentionally narrow:

1. land `RoutingIntentTemplate`, `RoutingIntentTemplateRule`, and `RoutingIntentTemplateBinding`
2. expose standard CRUD surfaces for those three models
3. compile one bound template into one existing `RoutingIntentProfile`
4. support preview-only compilation and derivation
5. stop before typed exceptions and before bulk aggregation

That cut is large enough to prove the architecture and small enough to avoid mixing template modeling, regeneration, exceptions, bulk orchestration, and reporting in one change.

## Acceptance Criteria

Priority 6 should be considered implementation-complete only when all of the following are true:

1. reusable templates can express common ROA intent policy without forcing operators to duplicate large rule sets manually
2. template compilation feeds the existing derivation, reconciliation, lint, simulation, and change-plan workflow rather than bypassing it
3. regeneration is deterministic, audit-visible, and quiet when inputs have not changed
4. exceptions are explicit, narrow, typed, and expiry-aware
5. bulk preview and draft planning preserve the existing child approval and provider-execution audit trail
6. UI, API, job, and command surfaces expose the intended operator steps without route or permission drift
7. focused regression suites and the broader plugin suite remain green

## Recommended Verification Set

Minimum focused verification for each landing slice:

- `manage.py makemigrations --check --dry-run netbox_rpki`
- `netbox_rpki.tests.test_routing_intent_services`
- affected generated-surface suites such as `test_forms`, `test_filtersets`, `test_tables`, `test_views`, `test_api`, `test_graphql`, `test_urls`, and `test_navigation`

Release-gate verification should use the same non-interactive NetBox environment and commands already documented elsewhere in the repo.