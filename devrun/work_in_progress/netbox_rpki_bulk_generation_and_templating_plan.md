# NetBox RPKI Plugin: Bulk Generation and Templating Plan

Prepared: April 14, 2026

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

### Current Repository Implementation State

Priority 6 is no longer greenfield in this repository. The current codebase already contains a meaningful first implementation slice that this plan should treat as the baseline, not as aspirational future work.

Implemented model layer in `netbox_rpki/models.py`:

- `RoutingIntentTemplate`
- `RoutingIntentTemplateRule`
- `RoutingIntentTemplateBinding`
- `RoutingIntentException`
- `BulkIntentRun`
- `BulkIntentRunScopeResult`

Implemented service-layer behavior in `netbox_rpki/services/routing_intent.py` and `netbox_rpki/services/bulk_routing_intent.py`:

- compiled template-binding assembly through `CompiledTemplateBinding`
- compiled exception capture through `CompiledRoutingIntentException`
- full effective-policy compilation through `CompiledRoutingIntentPolicy`
- preview output through `RoutingIntentDerivationPreview`
- binding regeneration state evaluation through `RoutingIntentBindingRegenerationAssessment`
- profile-level template binding execution through `run_routing_intent_template_binding_pipeline()`
- organization-scoped bulk orchestration through `run_bulk_routing_intent_pipeline()`
- baseline fingerprinting through `build_bulk_routing_intent_baseline_fingerprint()`

Implemented operator surfaces:

- registry-driven CRUD exposure for the new model families through `object_registry.py`
- binding preview and regenerate API actions in `netbox_rpki/api/views.py`
- exception approval API action in `netbox_rpki/api/views.py`
- organization-level bulk-run creation API action in `netbox_rpki/api/views.py`
- binding preview and regenerate web actions in `netbox_rpki/views.py`
- exception approval web action in `netbox_rpki/views.py`
- organization-level bulk-run creation web action in `netbox_rpki/views.py`
- explicit detail cards and action buttons in `netbox_rpki/detail_specs.py`

Implemented queued execution path:

- `RunBulkRoutingIntentJob` already exists in `netbox_rpki/jobs.py`
- the job already handles deduplication by normalized request fingerprint and running-state checks
- the job persists `job.data` pointing at the resulting `BulkIntentRun`

This means the document should now focus on:

- freezing and clarifying the contract that already exists
- identifying where the current implementation shape should be preserved intentionally
- identifying remaining hardening, reporting, and refinement work without pretending the feature family is still only proposed

### Current Staging Status Of This Planning Pass

This planning pass also staged focused Priority 6 contract tests in the repository, but verification did not complete cleanly and should not yet be treated as a finished validation result.

What was staged during this pass:

- focused registry assertions for the exact first-wave Priority 6 filter and search contract
- focused registry assertions for the exact first-wave Priority 6 table field and default-column contract
- focused API or surface assertions that `BulkIntentRun` and `BulkIntentRunScopeResult` remain read-only generated workflow records
- focused routing-intent service assertions for binding summary payload keys, invalid selector error-only persistence, and bulk-run success or failure summary payload shapes

Current verification status:

- one initial focused test invocation from the NetBox checkout failed before executing any assertions because the plugin was not enabled in that process
- the failure mode was the expected Django startup error when `NETBOX_RPKI_ENABLE=1` was not present
- no clean rerun of that focused test subset was completed afterward in this planning pass

Planning implication:

- treat those staged tests as unverified scaffolding for the next isolated verification pass
- while other agents are actively editing the codebase, keep this slice in documentation and contract-freeze mode rather than continuing with more repo-wide code churn

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

### 7. Bulk target modes are fixed to profiles, bindings, and mixed runs

The first-wave bulk aggregation model should use these exact target-mode values:

- `profiles`
- `bindings`
- `mixed`

Reason:

- these values already match the implemented model and orchestration logic
- they are operator-comprehensible in UI summaries and job payloads
- they avoid inventing separate one-off mode names for what is really the same orchestration pipeline with different target sets

### 8. Binding state remains a first-class model field, not only derived display text

The first-wave binding state contract should continue to use explicit stored state on `RoutingIntentTemplateBinding` rather than recalculating stale or current status only at render time.

The fixed first-wave stored values are:

- `current`
- `stale`
- `pending`
- `invalid`

Reason:

- the compiler already persists meaningful regeneration state on the binding row
- dashboard and list views need direct filtering without replaying the compiler
- this keeps stale-binding reporting queryable and auditable

### 9. `summary_json` remains the rollup seam for bindings, exceptions, bulk runs, and scope results

The first wave should keep `summary_json` on these models as the additive reporting seam:

- `RoutingIntentTemplateBinding`
- `RoutingIntentException`
- `BulkIntentRun`
- `BulkIntentRunScopeResult`

Reason:

- the current implementation already uses those fields for rollup reporting
- they provide a stable operator-summary seam without requiring one new model for every explanation row
- they fit the plugin's broader pattern of explicit historical rows plus additive summary JSON

### 10. Operator workflow actions remain explicit rather than hidden in CRUD

The first-wave action contract should continue to use explicit workflow actions for meaningful operator steps.

Current fixed action families:

- template-binding preview
- template-binding regenerate
- routing-intent exception approval
- organization-scoped bulk-run creation

This should remain true for follow-on slices. Important workflow transitions should not be hidden behind generic edit forms or inferred from passive CRUD state changes.

### 11. Bulk orchestration remains a fan-out over child workflows, not a replacement workflow

The current implementation choice is correct and should remain fixed:

- bulk runs orchestrate derivation, reconciliation, and optional change-plan creation
- child `IntentDerivationRun`, `ROAReconciliationRun`, and `ROAChangePlan` artifacts remain canonical
- `BulkIntentRun` and `BulkIntentRunScopeResult` are aggregate orchestration and drill-down objects only

This preserves the existing audit model and avoids creating a second publication workflow universe for bulk operations.

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

### Predefined First-Wave Choice And State Contract

The following values should be treated as fixed for the first implementation wave unless a maintainer explicitly changes this plan.

| Concept | Stored values | Notes |
| --- | --- | --- |
| `RoutingIntentTemplate.status` | `draft`, `active`, `archived` | Matches the current template lifecycle contract. |
| `RoutingIntentTemplateBinding.state` | `current`, `stale`, `pending`, `invalid` | Binding regeneration and validity state. |
| `RoutingIntentException.exception_type` | `traffic_engineering`, `anycast`, `mitigation`, `customer_edge` | First-wave typed exception classes. |
| `RoutingIntentException.effect_mode` | `broaden`, `narrow`, `suppress`, `temporary_replacement` | First-wave exception effect semantics. |
| `BulkIntentRun.status` | `pending`, `running`, `completed`, `failed` | Reuses the plugin's general validation-run status posture. |
| `BulkIntentRun.trigger_mode` | `manual`, `scheduled`, `netbox_change`, `sync_followup` | Reuses the existing trigger contract. |
| `BulkIntentRun.target_mode` | `profiles`, `bindings`, `mixed` | Fixed bulk targeting modes. |
| `BulkIntentRunScopeResult.status` | `pending`, `running`, `completed`, `failed` | Scope-result execution status. |
| `BulkIntentRunScopeResult.scope_kind` | `profile`, `binding` | First-wave scope-result families. |

Predefined identity rules:

- `RoutingIntentTemplate` remains unique by `(organization, name)`
- `RoutingIntentTemplateRule` remains unique by `(template, name)`
- `RoutingIntentTemplateBinding` remains unique by `(intent_profile, name)`
- `BulkIntentRunScopeResult.scope_key` remains unique inside one `BulkIntentRun`
- bulk profile scope keys should use `profile:<pk>`
- bulk binding scope keys should use `binding:<pk>`
- template, binding, and bulk fingerprints should remain deterministic hashes of materially relevant ordered inputs

### Predefined First-Wave Summary JSON Contract

The current implementation already uses summary payloads heavily enough that the top-level keys should be fixed now.

#### `RoutingIntentTemplateBinding.summary_json`

Expected stable top-level keys:

```json
{
	"template_id": 0,
	"template_version": 1,
	"template_fingerprint": "",
	"binding_fingerprint": "",
	"scoped_prefix_count": 0,
	"scoped_asn_count": 0,
	"active_rule_count": 0,
	"warning_count": 0,
	"warnings": [],
	"previous_binding_fingerprint": null,
	"regeneration_reason_codes": [],
	"regeneration_reason_summary": "",
	"candidate_binding_fingerprint": ""
}
```

The first-wave regeneration reason codes should remain:

- `never_compiled`
- `template_policy_changed`
- `template_version_changed`
- `prefix_scope_changed`
- `asn_scope_changed`
- `warning_profile_changed`
- `binding_parameters_changed`

#### `RoutingIntentException.summary_json`

The current implementation keeps this light. The first-wave contract should still standardize a minimal top-level shape:

```json
{
	"approval_state": "pending|approved",
	"lifecycle_state": "pending|scheduled|active|expired|disabled",
	"scope_summary": "",
	"effect_summary": "",
	"warnings": []
}
```

#### `BulkIntentRun.summary_json`

Expected stable top-level keys:

```json
{
	"comparison_scope": "local_roa_records",
	"provider_snapshot_id": null,
	"create_change_plans": false,
	"profile_target_count": 0,
	"binding_target_count": 0,
	"scope_result_count": 0,
	"change_plan_count": 0,
	"failed_scope_count": 0,
	"completed_scope_keys": [],
	"error": null
}
```

#### `BulkIntentRunScopeResult.summary_json`

Expected stable top-level keys:

```json
{
	"comparison_scope": "local_roa_records",
	"provider_snapshot_id": null,
	"warning_count": 0,
	"reconciliation_status": "completed",
	"change_plan_id": null,
	"binding_fingerprint": null
}
```

### Recommended Field Semantics

`RoutingIntentTemplate` should own reusable policy identity, explicit version state, and deterministic policy fingerprint, but not execution-state drift tracking. Drift and stale-state reporting belong on the binding or bulk-run side.

`RoutingIntentTemplateRule` should stay structurally close to `RoutingIntentRule` so the compiler can produce one effective rule set without introducing a second matching language.

`RoutingIntentTemplateBinding` should carry the typed runtime knobs that differ by profile or scope, and it should remain the only place where one template becomes profile-specific, for example:

- origin ASN source or override
- max-length mode or explicit override
- selector narrowing fragments
- human-readable binding label
- binding priority and enabled state

The first-wave binding object should continue to be the canonical place for:

- stale-state tracking
- last compiled fingerprint tracking
- preview summary projection
- per-profile selector narrowing

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

The first-wave `BulkIntentRunScopeResult` structure should continue to use:

- `scope_kind` to distinguish profile versus binding fan-out
- `scope_key` as the stable rollup identity inside a run
- direct foreign keys to child derivation, reconciliation, and change-plan records
- denormalized count fields for list and dashboard reporting

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

This layering is already materially present in the current implementation and should now be treated as the fixed evaluation order for Priority 6.

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

### Predefined Action And Job Interfaces

The first-wave operator-facing action and queued-execution contracts should be treated as fixed unless a maintainer reopens them.

Current API and web action names:

- `routingintenttemplatebinding_preview`
- `routingintenttemplatebinding_regenerate`
- `routingintentexception_approve`
- `organization_create_bulk_intent_run`

Current API action payload contracts:

- binding preview returns serialized binding data plus `compiled_policy`, `preview_result_count`, and `preview_results`
- binding regenerate accepts `comparison_scope` plus optional `provider_snapshot`
- organization bulk-run creation accepts `run_name`, `comparison_scope`, optional `provider_snapshot`, `create_change_plans`, `profiles`, and `bindings`

Current queued execution contract:

- `RunBulkRoutingIntentJob.get_job_name(organization, profiles=..., bindings=..., comparison_scope=..., provider_snapshot=..., create_change_plans=...)`
- `RunBulkRoutingIntentJob.enqueue_for_organization(...)`
- `RunBulkRoutingIntentJob.run(organization_pk, profile_pks=(), binding_pks=(), comparison_scope='local_roa_records', provider_snapshot_pk=None, create_change_plans=False, run_name=None)`

The `job.data` payload should continue to expose:

```json
{
	"organization_pk": 0,
	"bulk_intent_run_pk": 0,
	"profile_pks": [],
	"binding_pks": [],
	"comparison_scope": "local_roa_records",
	"provider_snapshot_pk": null,
	"create_change_plans": false
}
```

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

The current implementation already supports enough data to keep these additional first-wave reporting seams fixed:

- bulk baseline fingerprint versus resulting fingerprint
- scope-result counts split by profile and binding targets
- warning-count rollups from derivation results
- binding-state rollups from `current`, `stale`, `pending`, and `invalid`

## Execution Model

The slice list below remains useful as dependency and ownership sequencing, but it should now be read against the current repository baseline.

Current practical interpretation:

- Slices 1 and 2 are materially landed in the repository and should now be treated as baseline substrate plus hardening work
- Slice 3 is materially landed for binding preview and regeneration and should now be treated as a refinement and explanation-hardening slice
- Slice 5 is materially landed at the model and basic workflow level and should now be treated as deeper lifecycle and reporting refinement
- Slice 6 is materially landed for organization-scoped job orchestration and optional draft-plan fan-out and should now be treated as reporting, deduplication, and operator-explanation hardening
- Slice 7 is materially landed for the core web and API actions listed earlier and should now be treated as coverage and surface-parity refinement

Future implementation work should therefore use the remaining slices as a guide for tightening, explaining, and extending the existing contract rather than re-landing the same substrate from scratch.

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

### Slice 1: Template And Bulk Schema Substrate

Objective:

- preserve and harden the authored-policy and orchestration models that now exist in the repository
- extend factories and test helpers so later slices can build the current shape intentionally

Likely write set:

- `netbox_rpki/models.py`
- `netbox_rpki/migrations/`
- `netbox_rpki/tests/utils.py`
- `netbox_rpki/tests/registry_scenarios.py`
- targeted model tests

Outputs:

- the existing template, binding, exception, and bulk-run models remain stable and migration-safe
- any follow-on enum, constraint, or field refinements stay additive and compatibility-preserving

Verification:

- `manage.py makemigrations --check --dry-run netbox_rpki`
- focused model and factory tests

Dependency rule:

- already materially present; treat this slice as historical substrate plus refinement-only work

### Slice 2: Standard CRUD Surfaces For Authored Objects

Objective:

- keep the new authored objects visible and manageable through the standard generated surface family without route, mutability, or navigation drift

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

- stable list, detail, create, edit, delete, API, GraphQL, and navigation exposure for the new models
- parity between registry-driven mutability contracts and the actual route and permission behavior

Verification:

- focused `test_forms`, `test_filtersets`, `test_tables`, `test_urls`, `test_navigation`, and `test_graphql`
- registry-wide surface-contract checks for mutability and route presence

Dependency rule:

- already materially present; future work here is surface hardening and parity verification

### Slice 3: Effective-Policy Compilation And Preview

Objective:

- preserve and deepen compilation of template and local rule material into the existing derivation path without changing the downstream workflow contract

Likely write set:

- `netbox_rpki/services/routing_intent.py`
- new helper module such as `netbox_rpki/services/routing_intent_templates.py`
- `netbox_rpki/services/__init__.py`
- `netbox_rpki/tests/test_routing_intent_services.py`

Outputs:

- stable effective-policy assembly service
- stable template preview service contract
- provenance capture on emitted intent or derivation summary output
- layered precedence behavior matching the resolved contract in this document

Verification:

- local-rule-only profiles still match current derivation output
- template-only profiles derive deterministically
- mixed local-plus-template profiles honor the documented precedence contract
- typed exceptions and legacy overrides can be asserted as later layers in focused tests even if their dedicated surface slices land afterward

Dependency rule:

- materially present; future work is explanation, determinism, and regression-hardening

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

### Slice 5: Typed Exceptions

Objective:

- preserve and deepen the common operator exception cases already modeled explicitly, and feed them through the compiler without dissolving baseline policy structure

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

- stable typed exception classes and effect modes
- expiry-aware exception evaluation
- narrow scope matching and invalidation behavior
- explicit compatibility with existing `ROAIntentOverride` rows as the final precedence layer

Verification:

- exceptions attach only to intended scope
- expired exceptions reopen review
- exception effects remain visible in generated intent explanation and summaries

Dependency rule:

- materially present; future work is lifecycle, reporting, and operator-explanation refinement

### Slice 6: Bulk Run Aggregation And Draft-Plan Fan-Out

Objective:

- preserve and deepen multiple binding or profile executions in one operator-visible bulk workflow while preserving the child workflow artifacts

Likely write set:

- new helper module such as `netbox_rpki/services/bulk_routing_intent.py`
- `netbox_rpki/services/__init__.py`
- `netbox_rpki/services/routing_intent.py`
- `netbox_rpki/jobs.py`
- management command additions if command coverage is desired in the same slice
- `netbox_rpki/tests/test_routing_intent_services.py`

Outputs:

- stable `BulkIntentRun` orchestration service
- stable `BulkIntentRunScopeResult` rollup population
- optional draft `ROAChangePlan` creation for each qualifying child reconciliation result

Verification:

- bulk run can stop at preview without applying
- aggregate counts match underlying child derivation, reconciliation, lint, simulation, and plan outputs
- provider-backed and local scopes stay distinguishable in summaries

Dependency rule:

- materially present; future work is bulk summary richness, edge-case handling, and drill-down polish

### Slice 7: Custom Workflow Actions And Rich Detail Surfaces

Objective:

- keep the new bulk and template workflow reachable through intentional operator surfaces and close any remaining API/UI parity gaps

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

- materially present for the core actions listed earlier; future work is parity, permissions, and explanation refinement

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

NetBox-process note for this repository:

- when invoking plugin tests from the NetBox checkout, enable the plugin explicitly with `NETBOX_RPKI_ENABLE=1`
- do not treat a failed startup caused by the missing plugin flag as feature-level regression signal for Priority 6

Release-gate verification should use the same non-interactive NetBox environment and commands already documented elsewhere in the repo.

## Appendices

### Appendix A: Fixed Naming Matrix

The following names should be treated as fixed for Priority 6 unless a maintainer explicitly changes this plan.

| Model | Registry key | Route slug | API basename | GraphQL detail field | GraphQL list field | Suggested navigation group |
| --- | --- | --- | --- | --- | --- | --- |
| `RoutingIntentTemplate` | `routingintenttemplate` | `routingintenttemplate` | `routingintenttemplate` | `netbox_rpki_routingintenttemplate` | `netbox_rpki_routingintenttemplate_list` | `Intent` |
| `RoutingIntentTemplateRule` | `routingintenttemplaterule` | `routingintenttemplaterule` | `routingintenttemplaterule` | `netbox_rpki_routingintenttemplaterule` | `netbox_rpki_routingintenttemplaterule_list` | `Intent` |
| `RoutingIntentTemplateBinding` | `routingintenttemplatebinding` | `routingintenttemplatebinding` | `routingintenttemplatebinding` | `netbox_rpki_routingintenttemplatebinding` | `netbox_rpki_routingintenttemplatebinding_list` | `Intent` |
| `RoutingIntentException` | `routingintentexception` | `routingintentexception` | `routingintentexception` | `netbox_rpki_routingintentexception` | `netbox_rpki_routingintentexception_list` | `Intent` |
| `BulkIntentRun` | `bulkintentrun` | `bulkintentrun` | `bulkintentrun` | `netbox_rpki_bulkintentrun` | `netbox_rpki_bulkintentrun_list` | `Intent` |
| `BulkIntentRunScopeResult` | `bulkintentrunscoperesult` | `bulkintentrunscoperesult` | `bulkintentrunscoperesult` | `netbox_rpki_bulkintentrunscoperesult` | `netbox_rpki_bulkintentrunscoperesult_list` | `Intent` |

Fixed supporting module names:

- `services/routing_intent.py`
- `services/bulk_routing_intent.py`
- optional future helpers: `services/routing_intent_templates.py`, `services/routing_intent_regeneration.py`, `services/routing_intent_exceptions.py`

### Appendix B: Deterministic First Vertical Slice Contract

The smallest meaningful end-to-end template slice should be treated as a fixed proof path for future refactors and tests.

Recommended deterministic scenario:

1. create one `RoutingIntentTemplate` in `active` state
2. create one enabled `RoutingIntentTemplateRule` that sets or includes a deterministic origin and max-length posture
3. create one `RoutingIntentTemplateBinding` attached to one `RoutingIntentProfile`
4. preview the binding and assert:
	- `compiled_policy.input_fingerprint` is populated
	- exactly one compiled binding is reported
	- `preview_result_count` is deterministic for the fixture scope
5. regenerate the binding and assert:
	- `last_compiled_fingerprint` is populated
	- `state` becomes `current`
	- derivation and reconciliation artifacts are created
6. enqueue one organization-scoped bulk run over that binding and assert:
	- one `BulkIntentRun` is created
	- one `BulkIntentRunScopeResult` is created
	- `scope_kind=binding`
	- `scope_key=binding:<pk>`

That scenario is the recommended contract test for proving the template layer still feeds the existing derivation and reconciliation spine correctly.

### Appendix C: Pre-Work And Staging While Shared Files Are In Flux

If unrelated refactoring is still moving shared files, the following low-risk work can proceed in parallel:

1. freeze summary JSON keys and state values from this document in tests and notes
2. stage registry-driven scenario coverage for the six Priority 6 model families
3. add deterministic vertical-slice fixtures and expectations around template, binding, and bulk-run fingerprints
4. document exact action payloads and response keys for preview, regenerate, approve, and bulk-run creation
5. pre-stage migration grouping notes for model or field refinements that remain open

Work that should wait until shared-file churn settles:

- broad edits to `models.py` and migrations
- shared surface edits in `object_registry.py`, `detail_specs.py`, `api/views.py`, and GraphQL types when another branch is actively rewriting them
- large refactors of `services/routing_intent.py` while other routing-intent work is landing

Current status note:

- items 1 and 2 above were partially staged in this planning pass through focused test additions, but they still need a clean verification run before they should be considered closed

### Appendix D: Exact First-Wave Filter And Table Contract

The current repository uses `build_standard_object_spec()` in `netbox_rpki/object_registry.py` to derive first-wave table defaults from each object's `brief_fields`.

Fixed table-default rule:

- every Priority 6 standard table defaults to `brief_fields + ('comments', 'tenant', 'tags')`
- every Priority 6 standard table still exposes the larger generated field set `('pk', 'id') + api_fields + ('comments', 'tenant', 'tags')`
- unless a maintainer makes an explicit cross-cutting registry decision, future Priority 6 work should preserve this generated-table rule rather than introducing one-off table definitions for these objects

Exact current first-wave filter fields and default columns:

| Model | Exact filter fields | Exact default table columns |
| --- | --- | --- |
| `RoutingIntentTemplate` | `name`, `organization`, `status`, `enabled`, `template_version`, `tenant` | `name`, `organization`, `status`, `enabled`, `comments`, `tenant`, `tags` |
| `RoutingIntentTemplateRule` | `name`, `template`, `action`, `address_family`, `match_tenant`, `match_vrf`, `match_site`, `match_region`, `origin_asn`, `enabled`, `tenant` | `name`, `template`, `action`, `enabled`, `comments`, `tenant`, `tags` |
| `RoutingIntentTemplateBinding` | `name`, `template`, `intent_profile`, `enabled`, `binding_priority`, `state`, `origin_asn_override`, `tenant` | `name`, `template`, `intent_profile`, `state`, `enabled`, `comments`, `tenant`, `tags` |
| `RoutingIntentException` | `name`, `organization`, `intent_profile`, `template_binding`, `exception_type`, `effect_mode`, `prefix`, `origin_asn`, `tenant_scope`, `vrf_scope`, `site_scope`, `region_scope`, `enabled`, `tenant` | `name`, `organization`, `exception_type`, `effect_mode`, `enabled`, `comments`, `tenant`, `tags` |
| `BulkIntentRun` | `name`, `organization`, `status`, `trigger_mode`, `target_mode`, `tenant` | `name`, `organization`, `status`, `target_mode`, `started_at`, `comments`, `tenant`, `tags` |
| `BulkIntentRunScopeResult` | `name`, `bulk_run`, `intent_profile`, `template_binding`, `status`, `scope_kind`, `derivation_run`, `reconciliation_run`, `change_plan`, `tenant` | `name`, `bulk_run`, `intent_profile`, `template_binding`, `status`, `comments`, `tenant`, `tags` |

Priority 6 search contract that should remain stable unless a maintainer intentionally widens or narrows it:

- `RoutingIntentTemplate`: `name`, `description`, `template_fingerprint`, `comments`
- `RoutingIntentTemplateRule`: `name`, `match_role`, `match_tag`, `match_custom_field`, `comments`
- `RoutingIntentTemplateBinding`: `name`, `binding_label`, `prefix_selector_query`, `asn_selector_query`, `comments`
- `RoutingIntentException`: `name`, `prefix_cidr_text`, `reason`, `approved_by`, `comments`
- `BulkIntentRun`: `name`, `baseline_fingerprint`, `resulting_fingerprint`, `comments`
- `BulkIntentRunScopeResult`: `name`, `scope_key`, `scope_kind`, `comments`

### Appendix E: Example Summary JSON Payloads

The examples below are intentionally grounded in the current service-layer writers in `services/routing_intent.py` and `services/bulk_routing_intent.py`.

They should be treated as additive contracts:

- the listed keys are the first-wave stable minimum
- future work may add keys
- future work should not silently rename or remove these keys without an explicit compatibility decision

Example successful `RoutingIntentTemplateBinding.summary_json` after regeneration:

```json
{
	"template_id": 12,
	"template_version": 4,
	"template_fingerprint": "tmpl_8f8f1f7c2f4a",
	"binding_fingerprint": "bind_b2f4b5a44422",
	"scoped_prefix_count": 18,
	"scoped_asn_count": 1,
	"active_rule_count": 3,
	"warning_count": 0,
	"warnings": [],
	"previous_binding_fingerprint": "bind_7c9d901113ab",
	"regeneration_reason_codes": [
		"template_policy_changed",
		"template_version_changed"
	],
	"regeneration_reason_summary": "Template policy fingerprint changed. Template version changed.",
	"candidate_binding_fingerprint": "bind_b2f4b5a44422"
}
```

Example degraded `RoutingIntentTemplateBinding.summary_json` while stale or invalid:

```json
{
	"template_id": 12,
	"template_version": 4,
	"template_fingerprint": "tmpl_8f8f1f7c2f4a",
	"binding_fingerprint": "bind_9d55d28f88f0",
	"scoped_prefix_count": 0,
	"scoped_asn_count": 2,
	"active_rule_count": 3,
	"warning_count": 2,
	"warnings": [
		"Binding selector matched no prefixes.",
		"Multiple ASNs matched and no explicit origin override was supplied."
	],
	"previous_binding_fingerprint": "bind_b2f4b5a44422",
	"regeneration_reason_codes": [
		"prefix_scope_changed",
		"warning_profile_changed"
	],
	"regeneration_reason_summary": "Scoped prefix selection changed. Compilation warnings changed.",
	"candidate_binding_fingerprint": "bind_9d55d28f88f0"
}
```

If selector parsing fails before normal summary assembly, the current code path may persist the narrower invalid-state payload below. Keep this behavior explicit in tests because it is intentionally different from ordinary stale-state drift:

```json
{
	"error": "Invalid selector query: unsupported filter field 'foo'"
}
```

Example successful `BulkIntentRun.summary_json` after completion:

```json
{
	"comparison_scope": "local_roa_records",
	"provider_snapshot_id": null,
	"create_change_plans": true,
	"profile_target_count": 1,
	"binding_target_count": 2,
	"scope_result_count": 3,
	"change_plan_count": 3,
	"failed_scope_count": 0,
	"completed_scope_keys": [
		"profile:41",
		"binding:77",
		"binding:78"
	]
}
```

Example degraded `BulkIntentRun.summary_json` after failure:

```json
{
	"comparison_scope": "provider_imported",
	"provider_snapshot_id": 305,
	"create_change_plans": false,
	"profile_target_count": 0,
	"binding_target_count": 2,
	"scope_result_count": 1,
	"change_plan_count": 0,
	"failed_scope_count": 1,
	"error": "Routing intent template must be active before regeneration."
}
```

Example successful `BulkIntentRunScopeResult.summary_json` for a binding target:

```json
{
	"comparison_scope": "local_roa_records",
	"provider_snapshot_id": null,
	"warning_count": 1,
	"reconciliation_status": "completed",
	"change_plan_id": 901,
	"binding_fingerprint": "bind_b2f4b5a44422"
}
```

Example successful `BulkIntentRunScopeResult.summary_json` for a profile target:

```json
{
	"comparison_scope": "local_roa_records",
	"provider_snapshot_id": null,
	"warning_count": 0,
	"reconciliation_status": "completed",
	"change_plan_id": 902
}
```

### Appendix F: Frozen Follow-On Decisions For Priority 6

The items below are no longer open design questions for the current wave. Treat them as fixed unless a maintainer explicitly reopens one.

1. The generated filterset and table contract for the six Priority 6 objects is part of the supported operator surface and should be tested directly rather than treated as incidental registry output.
2. `RoutingIntentTemplateBinding.summary_json` remains the authoritative persistence seam for regeneration explanation, including `previous_binding_fingerprint`, `regeneration_reason_codes`, `regeneration_reason_summary`, and `candidate_binding_fingerprint`.
3. Invalid selector parsing on a binding may continue to persist the narrow `{"error": ...}` payload instead of the full regeneration summary; callers and tests should treat that as a distinct invalid-state contract rather than a partial stale-state contract.
4. `BulkIntentRun.summary_json` remains the authoritative rollup seam for operator-facing bulk-run health. At minimum it must continue to expose `comparison_scope`, `provider_snapshot_id`, target counts, scope-result counts, change-plan counts, failed-scope counts, and terminal `error` text when the run fails.
5. `BulkIntentRunScopeResult.summary_json` remains intentionally small and execution-oriented. It should continue to summarize comparison scope, provider snapshot context, derivation warning count, reconciliation status, optional change-plan linkage, and binding fingerprint only for binding-scoped rows.
6. `BulkIntentRun` and `BulkIntentRunScopeResult` remain read-only generated workflow records on the standard UI and API CRUD surfaces. New operator-trigger behavior belongs in explicit custom actions or jobs, not direct create or edit CRUD endpoints.
7. The Priority 6 plan should remain the detailed contract document, while the backlog should only carry the short current-state and remaining-gap summary plus a link back to this plan.