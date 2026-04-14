# NetBox RPKI Plugin: IRR Coordination Plan

Prepared: April 14, 2026

## Objective

Implement backlog Priority 10 as an additive IRR coordination layer that lets operators compare, explain, and eventually coordinate NetBox policy and IRR policy across multiple external sources.

The target is not a full IRR mirror, not a general-purpose whois server, and not a generic routing-policy platform inside the plugin.

The target is an operator workflow that can answer three practical questions in one place:

1. what NetBox policy currently expresses
2. what one or more IRR sources currently publish
3. what source-specific IRR changes would be required to bring those views into a deliberate coordinated state

This document carries the proposed models, service contracts, workflow boundaries, and execution slicing for Priority 10. The backlog remains the short status-and-priority view.

## Relationship To Existing Architecture

This plan must stay aligned with the plugin's current architecture rules:

- Django models and migrations remain explicit.
- Standard read and CRUD surfaces remain registry-driven where they fit.
- Workflow behavior stays in explicit services, jobs, commands, and custom actions.
- IRR coordination must plug into the existing routing-intent, reconciliation, reporting, and governance surfaces instead of creating a second operator universe.
- Direct writeback must reuse the same deliberate audit and change-review posture already established elsewhere in the plugin rather than hiding remote mutations behind simple CRUD screens.

This plan builds on four existing substrates that already exist in the codebase:

1. authored routing and ROA policy objects:
   - `RoutingIntentProfile`
   - `RoutingIntentRule`
   - `ROAIntentOverride`
   - `IntentDerivationRun`
   - `ROAIntent`
2. existing ROA and ASPA reconciliation and change workflow objects:
   - `ROAReconciliationRun`
   - `ROAIntentResult`
   - `PublishedROAResult`
   - `ROAChangePlan`
   - `ROAChangePlanItem`
3. snapshot-oriented import and diff patterns already used for provider synchronization
4. operator-facing dashboard, review, and governance surfaces that already summarize sync state, lint, simulation, bulk intent health, and provider execution state

## Current-State Baseline

The plugin already has the policy and workflow substrate needed to host IRR coordination, but it has no IRR-specific implementation today.

### Existing Policy Groundwork

The plugin already has real operator-facing policy and reconciliation workflows for ROA intent.

Existing authored and derived policy objects:

- `RoutingIntentProfile`
- `RoutingIntentRule`
- `ROAIntentOverride`
- `IntentDerivationRun`
- `ROAIntent`

Existing execution and review objects:

- `ROAReconciliationRun`
- `ROAIntentResult`
- `PublishedROAResult`
- `ROALintRun`
- `ROAValidationSimulationRun`
- `ROAChangePlan`
- `ROAChangePlanItem`

Existing template and bulk-authoring substrate:

- `RoutingIntentTemplate`
- `RoutingIntentTemplateRule`
- `RoutingIntentTemplateBinding`
- `RoutingIntentException`
- `BulkIntentRun`
- `BulkIntentRunScopeResult`

This means Priority 10 does not start from zero. It can reuse the existing idea of:

- historical runs
- summary-oriented workflow artifacts
- operator drill-down
- preview-before-apply governance

### Existing Import And History Groundwork

The provider-sync layer already establishes a useful pattern for:

- source identity
- retained snapshots
- imported family-specific records
- snapshot diffs
- run summaries and rollups
- explicit status and failure handling

That pattern is directly relevant to IRR because the first wave needs retained historical IRR imports rather than only the latest flattened state.

### Existing Dashboard And Governance Groundwork

The plugin already has:

- an operations dashboard with attention-oriented rollups
- plan preview and approval semantics
- provider execution audit rows
- queue-backed jobs and management commands for workflow execution

Priority 10 should extend those surfaces, not replace them.

### Missing Capability At Priority 10

Priority 10 remains open because the plugin still lacks:

- IRR source identity and credential models
- imported IRR inventory and historical snapshot retention
- multi-source comparison of IRR state against NetBox policy
- family-specific coordination logic for route objects and broader IRR policy objects
- source-specific IRR change plans and write execution records
- operator surfaces that present IRR mismatches and pending coordination work in reviewable terms

## Design Boundaries

The implementation should stay inside these boundaries unless a later design pass explicitly changes them.

- Do not turn the plugin into a full IRR database or a general-purpose RPSL management platform.
- Do not assume one IRR source is authoritative for all operators or all organizations.
- Do not collapse NetBox policy and IRR policy into silent bidirectional merge behavior.
- Keep historical IRR imports and coordination runs from the first wave so operators can reason about freshness and drift.
- Keep first-wave coordination explainable in operator terms. A mismatch should say what differs, in which source, and what draft action the plugin is proposing.
- Even with direct writeback in scope, keep the write path behind source-specific adapters, explicit plans, and audit rows.
- Preserve the plugin's current governance posture. IRR coordination can add new workflow artifacts, but it should not bypass preview, review, or execution audit concepts.

## Resolved First-Wave Decisions

The following design questions are considered resolved for the first implementation wave.

### 1. First-wave IRR scope is broad inventory, not route-only reporting

The first-wave contract covers these IRR object families:

- `route`
- `route6`
- `route-set`
- `as-set`
- `aut-num`
- `mntner`

That means the plan must not stop at prefix-origin comparison only. It must also preserve enough policy and administrative context to explain why a route object exists, how it relates to set membership, and which maintainer or autonomous-system objects participate in coordination.

### 2. The first wave compares multiple IRR sources

The first implementation wave must support multi-source comparison rather than a single canonical IRR source.

Implications:

- imported IRR state must remain source-scoped
- comparison results must remain source-aware
- dashboards and reviews must distinguish source-specific mismatches rather than flattening them into one undifferentiated IRR state

### 3. IRR ingest supports both live queries and snapshot imports, with live preferred

The first implementation wave should support both:

- live source queries as the preferred operational path
- snapshot imports as an additive fallback and fixture-friendly path

Reason:

- live queries best match the intended operator workflow
- snapshot imports are the stable way to build deterministic tests and disconnected development flows
- supporting both early avoids baking a one-path adapter contract into the model family

### 4. Historical IRR runs are required in the first wave

The first wave must retain historical IRR imports and coordination runs.

That is required so operators can answer:

- whether an IRR mismatch is current or stale
- when a source diverged from NetBox policy
- whether a write or review action changed the external IRR posture
- whether one source is drifting more often than others

### 5. The first wave prepares drafts for every compared source

The first implementation wave should not stop at one canonical target source.

If multiple sources are in scope for comparison, the coordination layer should be able to produce source-specific draft actions for each compared source.

That means:

- change planning must remain per-source
- write capability must be declared per source
- the review model must clearly separate one source's draft from another source's draft

### 6. Direct IRR writeback is in scope in the first wave

The first wave must go beyond reporting and draft generation.

It should include a real write path through source-specific adapters where the source family supports it.

That does not mean all sources will have identical write capabilities in slice 1. It means the first-wave architecture must include:

- write-capability discovery
- source-specific request construction
- execution audit rows
- explicit failure and partial-support semantics

### 7. NetBox and IRR are peer policy sources in the first wave

The first-wave coordination contract should not treat existing NetBox ROA intent as the only canonical policy source.

Instead:

- NetBox policy and imported IRR policy are compared as peer operator-relevant sources
- mismatches must be modeled explicitly rather than auto-resolved silently
- workflow surfaces should allow operators to see which side the plugin is proposing to change and why

This is deliberately more ambitious than a ROA-derived IRR export layer.

### 8. Direct writeback uses a source-specific adapter contract

The write path must not assume one universal IRR update mechanism.

The first-wave contract should treat direct writeback as a source-specific adapter problem, where each source family can define:

- query mechanics
- authentication semantics
- draft or preview semantics
- update or submission mechanics
- response parsing and failure handling

### 9. The first live adapter families are IRRd-compatible servers and RIPE-style HTTP APIs

The first-wave architecture should explicitly support two live adapter families without redesign:

- IRRd-compatible servers
- RIPE-style HTTP APIs

That means the adapter registry, source configuration model, and write execution model should not assume only one transport or one response shape.

### 10. A local IRRd-style test lab is the first concrete development target

The first concrete implementation slice should be grounded in a local IRRd-style lab so the import and write contracts are locally testable.

Implications:

- the first adapter slice should be runnable in a local development environment
- deterministic fixtures should still exist for Lane A tests
- public live source support should be an additive adapter expansion, not the first place the contract is exercised

### 11. The first named public sources after the local IRRd lab are RIPE TEST and RIPE production REST APIs

After the local IRRd-style development target, the first named public source rollout should be:

- RIPE TEST via the RIPE Database REST API for non-production live query and write validation
- RIPE production via the RIPE Database REST API once the TEST contract is stable

Reason:

- RIPE exposes documented read, search, metadata, dry-run, create, update, and delete semantics over one HTTP contract
- RIPE TEST gives the first public non-production target for validating live query and direct write behavior without forcing the first real write path onto production data
- the same adapter family then scales naturally to RIPE production without redesign

Implications:

- the first public HTTP-backed adapter should target RIPE TEST before RIPE production
- public IRRd-compatible support should remain part of the architecture, but not depend on one hard-coded public IRRd service in slice 1
- IRRd-compatible public rollout should use operator-configured source definitions after the local lab contract is proven

### 12. `IrrSource` follows the current plugin deployment model with model-backed source-specific credentials

In the current plugin deployment model, the first wave should use model-backed credential fields on `IrrSource` rather than external secret-manager indirection.

Reason:

- existing external integrations such as `RpkiProviderAccount` already store source credentials directly on the model
- no generic secret-reference subsystem exists in the plugin today
- introducing a separate secret-management architecture would expand Priority 10 beyond the current codebase's operating model

Guardrails for that choice:

- credentials should remain source-family-specific rather than becoming one generic free-form secret blob
- ordinary read surfaces should avoid exposing raw secret values even if the model stores them directly
- a future migration seam can still be preserved by keeping the credential fields narrow and explicit

### 13. Slice 1 fully normalizes route and set families first, while `aut-num` and `mntner` land as contextual records

The first import slice should fully normalize these families:

- `route`
- `route6`
- `route-set`
- `route-set` membership
- `as-set`
- `as-set` membership

The same slice should import `aut-num` and `mntner` as stable contextual records with:

- source-scoped identity
- key operator-facing summary fields
- maintainership and policy-summary metadata where available
- raw payload preservation for deeper semantics not yet normalized

Reason:

- route and set families are the most direct inputs to comparison, draft generation, and write correctness
- `aut-num` and `mntner` are essential context, but fully normalizing their source-specific semantics would materially expand the first-wave parsing surface
- this preserves broad-family visibility without forcing slice 1 to become a full RPSL semantic engine

## Proposed Coordination Architecture

Priority 10 should land as three additive pipelines joined by a shared coordination layer.

### Pipeline A: IRR Source Import

Purpose:

- fetch or import source-scoped IRR inventory
- persist retained source snapshots and imported object families
- expose source freshness, capability, and error state

Primary persistence:

- explicit IRR source and snapshot models
- imported family-specific IRR object models

### Pipeline B: IRR Coordination Comparison

Purpose:

- compare NetBox policy and IRR policy as peer sources
- classify mismatches, missing records, stale records, policy-context gaps, and write-capability limitations
- generate stable source-aware summaries for review surfaces

Primary persistence:

- historical coordination runs
- result rows and summary JSON structured for dashboards and review pages

### Pipeline C: IRR Change Planning And Write Execution

Purpose:

- build source-specific IRR change plans from coordination results
- preview and eventually apply direct writes through source adapters
- record source-specific execution audit state

Primary persistence:

- IRR change plans and plan items
- IRR write execution rows

### Shared Coordination Layer

Purpose:

- join NetBox policy, imported IRR inventory, coordination results, and write execution state
- project those joins into:
  - object detail pages
  - coordination-run detail
  - change-plan review
  - dashboard rollups

This layer should be service-driven and summary-oriented. Views should not do ad hoc cross-source comparison in templates.

## Proposed Model Contract

### Model Overview

| Model | Purpose | Key fields or behaviors | Notes |
| --- | --- | --- | --- |
| `IrrSource` | One configured IRR source identity | source family, display name, enabled state, query config, write capability, credential references, freshness metadata | Source-scoped anchor for import, comparison, and write execution. |
| `IrrSnapshot` | One historical IRR import boundary | source, status, fetched window, mode, summary, source serial or fingerprint | Retained historical source snapshot. |
| `ImportedIrrRouteObject` | Imported `route` or `route6` record | source snapshot, address family, prefix, origin ASN, maintainer refs, object text, payload JSON | Primary route-object comparison row. |
| `ImportedIrrRouteSet` | Imported `route-set` record | source snapshot, set name, member summary, maintainers, payload JSON | Explicit policy-group object. |
| `ImportedIrrRouteSetMember` | Imported `route-set` membership row | parent set, member text, normalized member type | Keeps membership queryable without burying it in JSON. |
| `ImportedIrrAsSet` | Imported `as-set` record | source snapshot, set name, member summary, maintainers, payload JSON | Explicit policy-group object. |
| `ImportedIrrAsSetMember` | Imported `as-set` membership row | parent set, member text, normalized member type | Keeps AS-set membership queryable. |
| `ImportedIrrAutNum` | Imported `aut-num` record | source snapshot, ASN, import/export policy summaries, maintainer refs, payload JSON | Policy context object. |
| `ImportedIrrMaintainer` | Imported `mntner` record | source snapshot, maintainer name, auth summary, admin contact summary, payload JSON | Administrative context object. |
| `IrrCoordinationRun` | One historical comparison run | status, compared sources, scope, summary, started and completed timestamps | Main comparison boundary. |
| `IrrCoordinationResult` | One source-aware mismatch or match row | coordination family, source, result type, severity, linkage to imported and NetBox objects, summary JSON | Flexible but explicit result row. |
| `IrrChangePlan` | One source-specific draft or execution plan | target source, source coordination run, status, scope summary, preview metadata, governance metadata | One plan per source and review context. |
| `IrrChangePlanItem` | One source-specific planned IRR action | family, action, object key, before and after summaries, request payload, response summary | Reviewable unit of planned change. |
| `IrrWriteExecution` | One write or preview attempt | change plan, target source, execution mode, status, request payload, response payload, error, timing | Mirrors provider execution audit style. |

### Predefined First-Wave Choice And Identity Contract

The following names should be treated as fixed for the first implementation wave unless a maintainer explicitly changes this plan.

Recommended choice sets and stored values:

| Concept | Stored values | Notes |
| --- | --- | --- |
| `IrrSource.source_family` | `irrd_compatible`, `ripe_rest` | First-wave adapter families. |
| `IrrSource.write_support_mode` | `unsupported`, `preview_only`, `apply_supported` | Source capability declaration, not execution state. |
| `IrrSnapshot.fetch_mode` | `live_query`, `snapshot_import` | Live is preferred; snapshot remains fixture and fallback path. |
| `IrrSnapshot.status` | `pending`, `running`, `completed`, `failed`, `partial` | `partial` is required for degraded imports that still persist useful families. |
| `IrrImportedFamily` logical names | `route`, `route6`, `route_set`, `route_set_member`, `as_set`, `as_set_member`, `aut_num`, `mntner` | First-wave normalized inventory families. |
| Membership row `member_type` | `prefix`, `prefix_range`, `route_set`, `as_set`, `asn`, `set_name`, `unknown` | Keep conservative parsing instead of over-normalizing. |
| `IrrCoordinationRun.status` | `pending`, `running`, `completed`, `failed` | Historical comparison state. |
| `IrrCoordinationResult.coordination_family` | `route_object`, `route_set_membership`, `as_set_membership`, `aut_num_context`, `maintainer_supportability` | First-wave comparison families. |
| `IrrCoordinationResult.result_type` | `match`, `missing_in_source`, `extra_in_source`, `source_conflict`, `unsupported_write`, `ambiguous_linkage`, `stale_source`, `policy_context_gap` | Keep these stable for workflow summaries and tests. |
| `IrrCoordinationResult.severity` | `info`, `warning`, `error` | First-wave attention scale. |
| `IrrChangePlan.status` | `draft`, `ready`, `approved`, `executing`, `completed`, `failed`, `canceled` | Mirrors the plugin's existing plan-oriented workflow posture. |
| `IrrChangePlanItem.action` | `create`, `modify`, `replace`, `delete`, `noop` | `noop` is allowed only for explicit review visibility or blocked actions. |
| `IrrWriteExecution.execution_mode` | `preview`, `apply` | First-wave write modes. |
| `IrrWriteExecution.status` | `pending`, `running`, `completed`, `failed`, `partial` | `partial` is required for multi-item execution with mixed outcomes. |

Predefined natural-key and stable-key rules:

- `IrrSource` should use a stable slug-like key unique within its ownership scope.
- every imported record should preserve both `rpsl_object_class` and `rpsl_pk` from the source where available
- every imported record should also expose a computed stable key for summaries and test assertions in the form `<family>:<rpsl_pk>`
- route-object stable keys should preserve IRR route-object semantics, for example `route:203.0.113.0/24AS64500` and `route6:2001:db8:fbf4::/48AS64500`
- set-object stable keys should use the set name exactly as published, for example `route_set:AS64500:RS-LOCAL-EDGE`
- contextual-object stable keys should use source-scoped RPSL primary keys, for example `aut_num:AS64500` and `mntner:LOCAL-IRR-MNT`
- membership-row stable keys should be `<parent_stable_key>|<member_text>` so they can be asserted deterministically in tests even when deep normalization is intentionally conservative

### Predefined Slice-1 Object Structures

The following field shapes are intentionally more concrete than the earlier model overview. They should be treated as the working first-wave contract.

#### `IrrSource`

Minimum first-wave fields:

- ownership scope field compatible with the plugin's current organization-scoped integration style where applicable
- `name`
- `slug`
- `enabled`
- `source_family`
- `write_support_mode`
- `default_database_label`
- `query_base_url`
- `whois_host`
- `whois_port`
- `http_username`
- `http_password`
- `api_key`
- `maintainer_name`
- `summary_json`
- `last_successful_snapshot`, `last_attempted_at`, and `sync_health` style freshness metadata

Field intent:

- keep credentials explicit and narrow instead of using one opaque secret blob
- allow unused source-family fields to remain null when a source family does not need them
- preserve enough metadata on the source row that dashboards can report source health without joining deeply into snapshot tables for every view

#### `IrrSnapshot`

Minimum first-wave fields:

- `source`
- `status`
- `fetch_mode`
- `started_at`
- `completed_at`
- `source_serial`
- `source_last_modified`
- `source_fingerprint`
- `error_text`
- `summary_json`

`IrrSnapshot.summary_json` should use a stable top-level shape:

```json
{
   "source_family": "irrd_compatible",
   "fetch_mode": "live_query",
   "source_serial": null,
   "source_last_modified": null,
   "source_fingerprint": null,
   "families": {
      "route": {"found": 1, "imported": 1, "failed": 0, "limited": false},
      "route6": {"found": 1, "imported": 1, "failed": 0, "limited": false},
      "route_set": {"found": 1, "imported": 1, "failed": 0, "limited": false},
      "route_set_member": {"found": 2, "imported": 2, "failed": 0, "limited": false},
      "as_set": {"found": 1, "imported": 1, "failed": 0, "limited": false},
      "as_set_member": {"found": 1, "imported": 1, "failed": 0, "limited": false},
      "aut_num": {"found": 1, "imported": 1, "failed": 0, "limited": false},
      "mntner": {"found": 1, "imported": 1, "failed": 0, "limited": false}
   },
   "degraded": false,
   "errors": []
}
```

#### Imported inventory rows

Every first-wave imported inventory model should share these common semantics:

- foreign key to `IrrSnapshot`
- denormalized `source` link or derived source path for easy filtering
- `rpsl_object_class`
- `rpsl_pk`
- `stable_key`
- `object_text`
- `payload_json`
- `source_database_label`

Recommended family-specific first-wave fields:

`ImportedIrrRouteObject`

- `address_family`
- `prefix`
- `origin_asn`
- `route_set_names_json`
- `maintainer_names_json`

`ImportedIrrRouteSet`

- `set_name`
- `maintainer_names_json`
- `member_count`

`ImportedIrrRouteSetMember`

- `parent_route_set`
- `member_text`
- `member_type`
- `normalized_prefix`
- `normalized_set_name`

`ImportedIrrAsSet`

- `set_name`
- `maintainer_names_json`
- `member_count`

`ImportedIrrAsSetMember`

- `parent_as_set`
- `member_text`
- `member_type`
- `normalized_asn`
- `normalized_set_name`

`ImportedIrrAutNum`

- `asn`
- `as_name`
- `import_policy_summary`
- `export_policy_summary`
- `maintainer_names_json`

`ImportedIrrMaintainer`

- `maintainer_name`
- `auth_summary_json`
- `admin_contact_handles_json`
- `upd_to_addresses_json`

The first wave should not introduce a separate `ImportedIrrPerson` model.

Reason:

- the first-wave goal is route and set normalization plus contextual `aut-num` and `mntner`
- person data is required for fixture validity and operator explanation, but not yet for a full first-wave query model
- contact handles referenced from imported rows should therefore be preserved in raw payload and summarized handle lists rather than normalized into a first-wave model family

### Predefined Adapter Batch Contract

The internal adapter registry output should be fixed now so later implementation and tests target one batch shape.

Recommended normalized batch structure:

```json
{
   "source_metadata": {
      "source_family": "irrd_compatible",
      "default_database_label": "LOCAL-IRR",
      "write_support_mode": "apply_supported"
   },
   "snapshot_metadata": {
      "fetch_mode": "live_query",
      "source_serial": null,
      "source_last_modified": null,
      "source_fingerprint": null,
      "warnings": [],
      "errors": []
   },
   "families": {
      "route": [],
      "route6": [],
      "route_set": [],
      "route_set_member": [],
      "as_set": [],
      "as_set_member": [],
      "aut_num": [],
      "mntner": []
   },
   "capability": {
      "route": "full",
      "route6": "full",
      "route_set": "full",
      "route_set_member": "full",
      "as_set": "full",
      "as_set_member": "full",
      "aut_num": "summary_only",
      "mntner": "summary_only"
   }
}
```

Each object in a family list should use these minimum keys:

```json
{
   "rpsl_object_class": "route",
   "rpsl_pk": "203.0.113.0/24AS64500",
   "stable_key": "route:203.0.113.0/24AS64500",
   "source_database_label": "LOCAL-IRR",
   "object_text": "...",
   "payload_json": {},
   "summary": {}
}
```

`summary` should carry the normalized fields that the import layer needs immediately, while `payload_json` keeps fuller source detail for later slices.

### Predefined Coordination And Plan Summary Structures

`IrrCoordinationRun.summary_json` should use a shape that is stable enough for dashboards and tests:

```json
{
   "source_count": 1,
   "sources": ["local-irrd"],
   "result_counts": {
      "route_object": {"match": 0, "missing_in_source": 0, "extra_in_source": 0, "source_conflict": 0},
      "route_set_membership": {"match": 0, "missing_in_source": 0, "extra_in_source": 0, "source_conflict": 0},
      "as_set_membership": {"match": 0, "missing_in_source": 0, "extra_in_source": 0, "source_conflict": 0},
      "aut_num_context": {"match": 0, "policy_context_gap": 0},
      "maintainer_supportability": {"match": 0, "unsupported_write": 0}
   },
   "severity_counts": {"info": 0, "warning": 0, "error": 0},
   "draftable_source_count": 0,
   "non_draftable_source_count": 0,
   "stale_source_count": 0,
   "cross_source_conflict_count": 0,
   "latest_plan_ids": []
}
```

`IrrChangePlan.summary_json` should use this top-level shape:

```json
{
   "target_source": "local-irrd",
   "write_support_mode": "apply_supported",
   "previewable": true,
   "applyable": true,
   "item_counts": {
      "create": 0,
      "modify": 0,
      "replace": 0,
      "delete": 0,
      "noop": 0
   },
   "family_counts": {
      "route_object": 0,
      "route_set_membership": 0,
      "as_set_membership": 0,
      "aut_num_context": 0,
      "maintainer_supportability": 0
   },
   "capability_warnings": [],
   "latest_execution": null
}
```

### Source And Snapshot Models

`IrrSource` should capture everything needed to support source-scoped import and source-scoped write capability without hard-coding one transport.

Recommended fields or semantics:

- `source_family` such as IRRd-compatible or RIPE-style HTTP
- `organization` when source configuration is org-scoped
- display label and stable slug or key
- enabled state
- query base URL or endpoint metadata
- write capability mode and preview capability mode
- source-default IRR database or registry label where relevant
- source-specific credential fields that match the adapter family, with future migration room for secret indirection if the plugin later grows a shared secret subsystem
- `summary_json` for small source-family-specific capability details

For the first wave specifically, prefer explicit source-family fields over one generic credential blob. The current plugin deployment model already stores provider credentials directly on model-backed integration objects, so IRR should follow that pattern rather than inventing a separate secret-reference subsystem inside Priority 10.

`IrrSnapshot` should behave much more like `ProviderSnapshot` than like a simple cache record.

Recommended additive semantics:

- one row per import attempt or retained source state boundary
- explicit fetch mode such as live or snapshot
- source-provided serial, fingerprint, or last-modified metadata where available
- imported-record counts by family
- source freshness and error summaries

### Imported IRR Inventory Models

The first wave needs explicit imported IRR families rather than one giant JSON blob because comparison and write planning must stay queryable and reviewable.

Recommended semantics by family:

- `ImportedIrrRouteObject` should capture prefix, address family, origin ASN, route-object key, route-object text, maintainers, source database label, and stable object identity
- `ImportedIrrRouteSet` and `ImportedIrrAsSet` should capture set identity and normalized membership through child rows rather than only flat text blobs
- `ImportedIrrAutNum` should capture enough import or export policy summary to explain route-set or as-set references and operator mismatches, while preserving raw payload detail for deeper semantics deferred beyond slice 1
- `ImportedIrrMaintainer` should capture enough identity and authorization summary to explain write targetability and operator review, while preserving raw payload detail for attributes that are not fully normalized in slice 1

### Coordination Models

`IrrCoordinationRun` should be the historical comparison boundary across one or more sources and one chosen scope.

Recommended semantics:

- compared source set
- comparison scope
- route-object summary counts
- policy-context family summary counts
- mismatch totals by type and severity
- draftable source count and non-draftable source count
- latest related change-plan references

`IrrCoordinationResult` should be explicit about what kind of thing is being compared and why it matters.

Recommended fields or semantics:

- `coordination_family` such as route object, route-set membership, as-set membership, aut-num context, or maintainer supportability
- `result_type` such as match, missing_in_source, extra_in_source, source_conflict, unsupported_write, ambiguous_linkage, stale_source, or policy_context_gap
- severity or attention level
- optional linkage to NetBox-side policy objects such as `ROAIntent`, routing-intent profiles, or later IRR policy objects if added
- optional linkage to imported IRR rows
- source-scoped summary JSON for operator explanation and draft generation

### Change Planning And Write Models

`IrrChangePlan` should be source-specific, not global.

Reason:

- the user selected draft generation for every compared source
- different sources may disagree, may support different write mechanisms, or may only be partially writable

Recommended fields or semantics:

- target source
- parent coordination run
- status and governance state
- source-family capability summary
- plan summary JSON including per-family counts and capability warnings

`IrrChangePlanItem` should be the unit operators review.

Recommended fields or semantics:

- object family
- action type such as create, modify, replace, or delete
- stable object identity within the target source
- before and after normalized summaries
- request payload JSON and response-summary JSON
- explicit unsupported or degraded-execution notes where a source cannot do the desired operation cleanly

`IrrWriteExecution` should record preview and apply attempts similarly to provider write execution audit rows.

## Proposed Service Contracts

### Service Overview

| Contract | Likely module | Inputs | Outputs | Purpose |
| --- | --- | --- | --- | --- |
| IRR adapter registry | `services/irr_sync.py` | IRR source, query mode, credentials | normalized inventory batch | Supports multiple source families without changing workflow code. |
| IRR import orchestration | `services/irr_sync.py` | source or source list, live or snapshot mode | `IrrSnapshot` plus imported family rows | Persists retained historical IRR inventory. |
| IRR coordination builder | `services/irr_coordination.py` | NetBox policy scope, imported IRR snapshots | `IrrCoordinationRun` plus result rows | Compares peer policy views and emits stable mismatch records. |
| IRR draft builder | `services/irr_write.py` | coordination run or explicit scope, target source | `IrrChangePlan` plus plan items | Produces source-specific draft changes. |
| IRR write executor | `services/irr_write.py` | change plan, execution mode | `IrrWriteExecution` | Performs preview or apply against a source-specific adapter. |
| IRR reporting builder | `services/irr_reporting.py` | visible sources, runs, plans | rollups and summaries | Feeds dashboard cards and detail summaries. |

### IRR Import Contract

Import should produce one historical `IrrSnapshot` per source and then project that snapshot into imported family-specific rows.

The import service should handle:

- source authentication
- live query or snapshot ingestion
- stable source-object identity
- family-specific normalization
- source error and partial-support summaries
- source serial or freshness metadata where available

The contract should stay conservative. If an adapter cannot fully normalize one family, it should preserve raw payload detail and mark the family status explicitly rather than pretending it is complete.

### IRR Coordination Contract

The coordination service must be able to answer these questions for one or more sources:

1. what matches between NetBox policy and IRR policy
2. what is missing on either side
3. where sources disagree with each other
4. which mismatches are draftable and which are blocked by capability or ambiguity
5. what policy-context objects such as sets, aut-num records, or maintainers explain or constrain the route-object result

Because the user chose peer-source semantics, the coordination service must not assume one automatic winner. It should emit explicit mismatch categories and recommended draft directions rather than silently rewriting one side into the other.

### Draft And Write Contract

The draft builder should produce one `IrrChangePlan` per source.

It should handle:

- route-object deltas
- related policy-context deltas needed for a coherent source-specific submission
- capability warnings where a source cannot support one planned change through the adapter contract
- plan summaries suitable for operator review

The write executor should support at least two modes:

- preview
- apply

It should record:

- request payloads or transaction bodies
- source responses
- partial failure or unsupported-operation semantics
- timing and actor attribution

## Proposed Surface Contract

### New Read Surfaces

The following model families should gain ordinary registry-driven read surfaces:

- `IrrSource`
- `IrrSnapshot`
- imported IRR inventory models
- `IrrCoordinationRun`
- `IrrCoordinationResult`
- `IrrChangePlan`
- `IrrChangePlanItem`
- `IrrWriteExecution`

Standard list and detail pages should be sufficient for the raw inventory families in the first wave, while coordination and change-plan objects will likely need curated detail semantics and related tables.

### Coordination And Review Surfaces

Priority 10 should enrich, not replace, existing operator review flows.

Recommended additions:

- routing-intent and ROA reconciliation surfaces should gain IRR coordination summaries where the policy scope overlaps
- IRR coordination-run detail should provide source-aware related tables for matches, mismatches, unsupported writes, and stale imports
- IRR change-plan detail should show per-source deltas, capability notes, and execution audit rows
- first-wave review surfaces should keep existing RPKI workflows visible instead of hiding them behind an IRR-only page

### Operations Dashboard

The operations dashboard should gain an IRR section rather than hiding Priority 10 only in low-level inventory pages.

Recommended new dashboard rollups:

- stale or failed IRR sources
- coordination runs requiring attention
- multi-source conflicts requiring operator review
- IRR change plans blocked by capability gaps
- recent IRR write failures

### API And GraphQL

The first wave should preserve the plugin's current style:

- new inventory models should get ordinary registry-driven read surfaces
- coordination and change-plan summaries should expose stable JSON summaries first
- workflow actions should be explicit rather than implied by generic CRUD

## Proposed Summary Contracts

### IRR Snapshot Summary

`IrrSnapshot.summary_json` should include fields such as:

- source freshness
- fetch mode
- imported counts by family
- capability summary by family
- degraded or partial-import indicators
- source serial or last-modified markers where available

### IRR Coordination Summary

`IrrCoordinationRun.summary_json` should include fields such as:

- compared source count
- result counts by family and result type
- draftable source count
- non-draftable source count
- stale-source count
- cross-source conflict count
- latest related plan IDs

### IRR Change Plan Summary

`IrrChangePlan.summary_json` should include fields such as:

- target source identity
- plan item counts by family and action
- previewability and applyability flags
- capability warnings
- write support mode
- latest execution result

## Execution Slices

### Slice 0: Contract Freeze

Use this document as the initial contract freeze for Priority 10.

Closed by this document:

- broader first-wave IRR family scope
- multi-source comparison requirement
- live plus snapshot ingest with live preferred
- historical retention requirement
- per-source draft generation across compared sources
- direct writeback in first-wave scope
- peer-source policy semantics between NetBox and IRR
- source-specific adapter contract for query and write paths
- IRRd-compatible and RIPE-style HTTP adapter families in first-wave architecture
- local IRRd-style lab as the first concrete development target
- RIPE TEST and RIPE production REST APIs as the first named public sources after the local lab
- model-backed source-specific credential fields for the first-wave deployment model
- full normalization of route and set families first, with `aut-num` and `mntner` landing as contextual records in slice 1

### Slice 1: IRR Source And Snapshot Substrate

Land the source and import substrate first.

Expected outcomes:

- `IrrSource`
- `IrrSnapshot`
- imported IRR inventory models
- live query and snapshot import through one normalized adapter contract
- local IRRd-style development target for the first adapter slice
- RIPE TEST-ready HTTP adapter expansion path immediately after the local lab slice
- retained snapshot summaries and freshness reporting
- full normalization of route and set families plus contextual `aut-num` and `mntner` imports

#### Slice 1 local IRRd-style devrun and seed-data plan

The first adapter slice should use the local IRRd lab that now exists under `devrun/` as the contract anchor, not just as an optional convenience environment.

Current local-lab assets that should be treated as part of the slice-1 development contract:

- `devrun/docker-compose.yml` defines the `irrd` service
- `devrun/irrd/Dockerfile` and `devrun/irrd/entrypoint.sh` build and start the local IRRd-compatible server
- `devrun/irrd-service.sh` provides the user-facing `./dev.sh irrd ...` wrapper
- `devrun/seed-irrd-data.sh` loads deterministic authoritative fixture data
- `devrun/irrd/fixtures/local-authoritative.rpsl` defines the first-wave authoritative dataset

The slice-1 adapter contract should assume one fixed authoritative local source at first:

- source key: `LOCAL-IRR`
- transport family: IRRd-compatible HTTP and whois surfaces
- write support in local lab: yes, through the local submit API
- purpose in slice 1: prove source configuration, import normalization, snapshot retention, and later write-path correctness before any public-source rollout

The deterministic fixture set for the first adapter slice should remain intentionally small and stable. It should continue to seed exactly the families that slice 1 must normalize or preserve as context:

- one `mntner`: `LOCAL-IRR-MNT`
- one `person`: `LOCAL-IRR-PERSON`
- one `aut-num`: `AS64500`
- one `as-set`: `AS64500:AS-LOCAL-CUSTOMERS`
- one `route-set`: `AS64500:RS-LOCAL-EDGE`
- one IPv4 `route`: `203.0.113.0/24` origin `AS64500`
- one IPv6 `route6`: `2001:db8:fbf4::/48` origin `AS64500`

That fixture is sufficient to prove the first adapter slice can correctly handle:

- source-scoped route and route6 identity
- set-object import and membership expansion
- contextual `aut-num` and `mntner` import
- maintainer and contact references needed for later write planning
- raw-object preservation for families not fully normalized beyond slice 1

Expected local-lab operator flow for slice-1 development:

1. `./dev.sh irrd start`
2. `./dev.sh irrd seed`
3. verify the seeded objects through `http://127.0.0.1:6080/v1/whois/`
4. run the future slice-1 IRR import command or job against the configured `IrrSource`
5. inspect the resulting `IrrSnapshot` and imported inventory rows through ordinary read surfaces

The first slice should keep both live-query and fixture-friendly modes, but the deterministic local seed data should be the required contract gate for lane-A style adapter tests and local development verification.

The first public live-source expansion should only begin after the slice-1 import path can repeatedly:

- create an `IrrSnapshot` from the local lab
- import all seeded route and set families correctly
- preserve `aut-num` and `mntner` as contextual records
- report stable per-family counts and no false freshness failures

#### Implementation Checklist For Slice 1

Build slice 1 in this order. Do not start slice 2 coordination work until this checklist is complete.

1. Add the source and snapshot models.
   Create `IrrSource` and `IrrSnapshot` in `models.py` with migrations, status fields, source-family fields, source-specific credential fields, freshness metadata, and `summary_json` contracts.

2. Add imported IRR inventory models for the normalized first-wave families.
   Create explicit imported models for route objects, route-sets, route-set members, as-sets, as-set members, `aut-num`, and `mntner`, with source-snapshot linkage and stable source-scoped keys.

3. Register the new read models in the standard plugin surfaces.
   Wire the slice-1 models through `object_registry.py`, `tables.py`, `filtersets.py`, `forms.py`, `views.py`, `detail_specs.py`, `urls.py`, and API or GraphQL read surfaces so operators can inspect sources, snapshots, and imported objects without custom debugging code.

4. Define the normalized adapter batch contract in `services/irr_sync.py`.
   Add a small internal contract for adapter outputs covering source metadata, snapshot metadata, normalized object families, membership rows, contextual objects, raw payload preservation, and per-family capability flags.

5. Implement the adapter registry and source-family dispatch.
   Add an adapter registry that chooses the right read path from `IrrSource.source_family`, starting with the local IRRd-compatible adapter and preserving a clean seam for the RIPE-style HTTP adapter family.

6. Implement the local IRRd-compatible read adapter first.
   Use the local IRRd lab as the first live adapter target. The first adapter should read the seeded `LOCAL-IRR` dataset, normalize the route and set families, preserve raw object text, and surface contextual `aut-num` and `mntner` summaries.

7. Implement family-specific normalization helpers.
   Add parsers or normalizers for `route`, `route6`, `route-set`, `route-set` membership, `as-set`, `as-set` membership, `aut-num`, and `mntner`, keeping route and set families deeply queryable while storing wider source payload detail for contextual families.

8. Implement snapshot persistence and replacement semantics.
   Add the import orchestration logic that creates one `IrrSnapshot` per run, writes imported family rows linked to that snapshot, records per-family counts and failures in `summary_json`, and keeps historical snapshots rather than flattening into one mutable latest-state table.

9. Add explicit execution entry points.
   Add a management command and queued job for IRR import or sync so slice 1 is reachable the same way other plugin workflows are reachable. The first command should accept one or more `IrrSource` records and support live-query mode plus deterministic local-lab use.

10. Add first-slice local verification helpers.
   Reuse the existing `./dev.sh irrd start` and `./dev.sh irrd seed` flow as the local adapter bootstrap. Add a concise import-smoke command path that proves the plugin can import the seeded `LOCAL-IRR` data into `IrrSnapshot` and imported inventory models.

11. Add focused model and service tests.
   Cover model validation, snapshot summary generation, source-family dispatch, route and set normalization, contextual `aut-num` and `mntner` preservation, and imported membership-row creation.

12. Add command, job, API, and view smoke tests.
   Prove the new import entry point runs, prove ordinary read surfaces expose the imported data, and prove at least one end-to-end slice-1 path from seeded local data to persisted imported rows.

13. Add lane-A deterministic fixture coverage.
   Keep the local IRRd fixture small and stable, and add deterministic tests that assert expected imported counts and keys for the seeded objects instead of relying only on live query success.

14. Close slice 1 only when these outcomes are true.
   A configured `IrrSource` can import from the local `LOCAL-IRR` lab, produce a retained `IrrSnapshot`, persist normalized route and set families plus contextual `aut-num` and `mntner` records, expose those rows through normal read surfaces, and pass focused tests for the local adapter contract.

#### Parallel pre-work and staging while unrelated refactoring is in flight

If the codebase is temporarily unstable because of unrelated refactoring, the following work can still proceed with low merge risk. The goal is to front-load contract clarity, test fixtures, and execution notes without starting the highest-conflict model and service edits too early.

Safe pre-work to do before the refactor settles:

1. Freeze the slice-1 naming matrix.
   Record the intended model names, table labels, route names, registry labels, and source-family enum values before code lands so later implementation does not drift or collide with existing NetBox or plugin model names.

2. Draft the `summary_json` and adapter payload schemas.
   Write the exact keys expected for `IrrSnapshot.summary_json` and the internal normalized adapter batch contract so service and test work can begin from one stable shape.

3. Build deterministic fixture expectations from the existing `LOCAL-IRR` dataset.
   Capture the expected imported counts, stable keys, membership rows, and contextual-link expectations for the seeded `LOCAL-IRR` objects so the slice-1 tests can be written as contract tests instead of ad hoc assertions.

4. Stage test-scenario helpers for the new registry-driven read models.
   Prepare the scenario matrix for forms, tables, filtersets, navigation, URLs, API, and GraphQL read-surface smoke coverage in the same style the repo already uses for registry-driven object tests.

5. Stage local-lab verification commands and expected outputs.
   Keep one concise verification path for `./dev.sh irrd start`, `./dev.sh irrd seed`, and the HTTP whois queries so every future slice-1 branch can prove the same environment assumptions before debugging import code.

6. Draft the import command and job interface.
   Decide the operator-facing command names, likely arguments, and queued-job inputs now, even if the implementation waits. That avoids late workflow churn once the model layer starts landing.

7. Prepare adapter-family sample payload corpus notes.
   Save small representative IRRd-compatible and RIPE-style response examples or field maps so normalization work can proceed from known shapes once implementation starts.

8. Identify the ordinary read surfaces that will be registry-driven versus curated.
   Mark which slice-1 models should use the standard registry path unchanged and which later workflow models will need richer curated detail pages. This reduces churn in `detail_specs.py`, `object_registry.py`, and UI wiring once code work begins.

9. Pre-stage migration sequencing notes.
   Write down the intended migration grouping for sources, snapshots, and imported inventory models so the implementation branch can avoid noisy migration rewrites while the refactor branch is still moving.

10. Define the merge gate for starting code changes.
    Treat the refactor as cleared for slice-1 implementation only when `models.py`, registry wiring files, and shared test helpers are no longer changing underneath the branch. Until then, keep the work to contracts, fixture expectations, and command-shape planning.

Work that should wait until the unrelated refactor stabilizes:

- edits to `models.py` and migrations
- registry wiring across forms, filtersets, tables, views, URLs, and detail specs
- import service persistence code that depends on the final model shapes
- new API or GraphQL surfaces that may overlap with ongoing shared-surface changes
- broad test-suite edits that depend on final registry or model names

This staging split should let the team keep reducing uncertainty now while avoiding the highest-churn merge conflicts.

### Slice 2: Multi-Source Coordination Core

Build the comparison layer that treats NetBox policy and IRR policy as peer sources.

Expected outcomes:

- `IrrCoordinationRun`
- `IrrCoordinationResult`
- stable mismatch and conflict categories
- source-aware rollups and summaries
- route-object comparison plus policy-context linkage sufficient to explain why route results differ

### Slice 3: Source-Specific Draft Generation

Project coordination results into source-specific plans.

Expected outcomes:

- `IrrChangePlan`
- `IrrChangePlanItem`
- one plan per compared source when drafts are possible
- preview summaries and capability warnings

### Slice 4: Direct Write Execution

Land the first real write path through source adapters.

Expected outcomes:

- `IrrWriteExecution`
- preview and apply execution modes
- explicit failure and unsupported-operation semantics
- local IRRd lab write path first
- source-family expansion path for RIPE-style HTTP adapters

### Slice 5: Dashboard And Workflow Integration

Project IRR coordination into the operator workflows that already matter.

Expected outcomes:

- operations-dashboard IRR rollups
- additive summaries on related reconciliation and review surfaces
- focused UI, API, and permission tests proving operator reachability

## Testing And Verification Expectations

The first implementation wave should extend the plugin's current test strategy instead of inventing a separate one.

Required coverage areas:

- model validation for new IRR source, inventory, coordination, and write models
- service tests for import, comparison, draft generation, and write execution
- management-command and job tests for the new execution entry points
- detail-page rendering tests for coordination and change-plan surfaces
- API and GraphQL tests for new read models and workflow actions
- registry-driven smoke coverage for new ordinary read surfaces

Testing lanes should stay consistent with the existing strategy matrix:

- Lane A for deterministic import, comparison, and write-adapter contract tests
- local IRRd-style lab for concrete adapter and write-path validation
- public live sources only after the local contract is already stable

## Risks And Implementation Notes

Main risks:

- the selected scope is materially broader than a route-only IRR reporting slice and can sprawl if family boundaries are not enforced carefully
- multi-source comparison can produce operator noise if source disagreement is flattened into one generic mismatch label
- peer-source semantics can become ambiguous if the plugin silently chooses one side as the winner without explicit operator review
- direct writeback increases the need for careful source capability reporting, preview semantics, and audit trails
- broader IRR families such as `aut-num` and `mntner` can become parsing-heavy if the first wave tries to fully normalize every source-specific nuance

Implementation notes:

- keep source family support explicit and capability-scoped
- prefer normalized summaries plus raw payload preservation over premature full-RPSL parsing for every attribute in every family
- keep route-object coordination explainable first, then deepen broader family semantics where they directly improve review and write correctness
- treat local-lab validation as a contract gate before public live source expansion

## Implementation Kickoff State

No additional architecture decisions currently block the first implementation slice.

The remaining work is execution sequencing inside the contract already recorded here:

1. land the local IRRd-style import and write contract first
2. expand the HTTP-backed adapter family through RIPE TEST next
3. keep slice 1 normalization deep on route and set families while carrying `aut-num` and `mntner` as contextual records until later refinement proves necessary

## Appendices

### Appendix A: Slice-1 Naming Matrix

Unless a maintainer explicitly changes this plan, Slice 1 should use the following names across models, registry keys, routes, API basenames, and generated surface classes.

| Model | Registry key | Route slug | API basename | GraphQL detail field | GraphQL list field | Suggested navigation group | Label singular | Label plural |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IrrSource` | `irr_source` | `irr_source` | `irr_source` | `netbox_rpki_irr_source` | `netbox_rpki_irr_source_list` | `IRR` | `IRR Source` | `IRR Sources` |
| `IrrSnapshot` | `irr_snapshot` | `irr_snapshot` | `irr_snapshot` | `netbox_rpki_irr_snapshot` | `netbox_rpki_irr_snapshot_list` | `IRR` | `IRR Snapshot` | `IRR Snapshots` |
| `ImportedIrrRouteObject` | `imported_irr_route_object` | `imported_irr_route_object` | `imported_irr_route_object` | `netbox_rpki_imported_irr_route_object` | `netbox_rpki_imported_irr_route_object_list` | `IRR` | `Imported IRR Route Object` | `Imported IRR Route Objects` |
| `ImportedIrrRouteSet` | `imported_irr_route_set` | `imported_irr_route_set` | `imported_irr_route_set` | `netbox_rpki_imported_irr_route_set` | `netbox_rpki_imported_irr_route_set_list` | `IRR` | `Imported IRR Route-Set` | `Imported IRR Route-Sets` |
| `ImportedIrrRouteSetMember` | `imported_irr_route_set_member` | `imported_irr_route_set_member` | `imported_irr_route_set_member` | `netbox_rpki_imported_irr_route_set_member` | `netbox_rpki_imported_irr_route_set_member_list` | `IRR` | `Imported IRR Route-Set Member` | `Imported IRR Route-Set Members` |
| `ImportedIrrAsSet` | `imported_irr_as_set` | `imported_irr_as_set` | `imported_irr_as_set` | `netbox_rpki_imported_irr_as_set` | `netbox_rpki_imported_irr_as_set_list` | `IRR` | `Imported IRR AS-Set` | `Imported IRR AS-Sets` |
| `ImportedIrrAsSetMember` | `imported_irr_as_set_member` | `imported_irr_as_set_member` | `imported_irr_as_set_member` | `netbox_rpki_imported_irr_as_set_member` | `netbox_rpki_imported_irr_as_set_member_list` | `IRR` | `Imported IRR AS-Set Member` | `Imported IRR AS-Set Members` |
| `ImportedIrrAutNum` | `imported_irr_aut_num` | `imported_irr_aut_num` | `imported_irr_aut_num` | `netbox_rpki_imported_irr_aut_num` | `netbox_rpki_imported_irr_aut_num_list` | `IRR` | `Imported IRR Aut-Num` | `Imported IRR Aut-Nums` |
| `ImportedIrrMaintainer` | `imported_irr_maintainer` | `imported_irr_maintainer` | `imported_irr_maintainer` | `netbox_rpki_imported_irr_maintainer` | `netbox_rpki_imported_irr_maintainer_list` | `IRR` | `Imported IRR Maintainer` | `Imported IRR Maintainers` |
| `IrrCoordinationRun` | `irr_coordination_run` | `irr_coordination_run` | `irr_coordination_run` | `netbox_rpki_irr_coordination_run` | `netbox_rpki_irr_coordination_run_list` | `IRR` | `IRR Coordination Run` | `IRR Coordination Runs` |
| `IrrCoordinationResult` | `irr_coordination_result` | `irr_coordination_result` | `irr_coordination_result` | `netbox_rpki_irr_coordination_result` | `netbox_rpki_irr_coordination_result_list` | `IRR` | `IRR Coordination Result` | `IRR Coordination Results` |
| `IrrChangePlan` | `irr_change_plan` | `irr_change_plan` | `irr_change_plan` | `netbox_rpki_irr_change_plan` | `netbox_rpki_irr_change_plan_list` | `IRR` | `IRR Change Plan` | `IRR Change Plans` |
| `IrrChangePlanItem` | `irr_change_plan_item` | `irr_change_plan_item` | `irr_change_plan_item` | `netbox_rpki_irr_change_plan_item` | `netbox_rpki_irr_change_plan_item_list` | `IRR` | `IRR Change Plan Item` | `IRR Change Plan Items` |
| `IrrWriteExecution` | `irr_write_execution` | `irr_write_execution` | `irr_write_execution` | `netbox_rpki_irr_write_execution` | `netbox_rpki_irr_write_execution_list` | `IRR` | `IRR Write Execution` | `IRR Write Executions` |

Additional naming rules:

- first-wave service modules should be `services/irr_sync.py`, `services/irr_coordination.py`, `services/irr_write.py`, and `services/irr_reporting.py`
- the first-wave job class name should be `SyncIrrSourceJob`
- the first-wave management command name should be `sync_irr_source`
- if a plural management command is later added, it should be `sync_irr_sources`
- first-wave route and API slugs should remain identical to the registry key unless a compatibility constraint emerges later

### Appendix B: Deterministic `LOCAL-IRR` Expected Import Contract

The first-wave seeded local dataset is fixed by `devrun/irrd/fixtures/local-authoritative.rpsl`. Slice-1 import tests should assert the following deterministic expectations.

Expected source metadata:

- source family: `irrd_compatible`
- source database label: `LOCAL-IRR`
- write support mode: `apply_supported`
- fetch mode for the normal local smoke path: `live_query`

Expected first-wave imported family counts from the seeded local dataset:

```json
{
   "route": 1,
   "route6": 1,
   "route_set": 1,
   "route_set_member": 2,
   "as_set": 1,
   "as_set_member": 1,
   "aut_num": 1,
   "mntner": 1
}
```

Expected imported stable keys:

```json
{
   "route": [
      "route:203.0.113.0/24AS64500"
   ],
   "route6": [
      "route6:2001:db8:fbf4::/48AS64500"
   ],
   "route_set": [
      "route_set:AS64500:RS-LOCAL-EDGE"
   ],
   "route_set_member": [
      "route_set:AS64500:RS-LOCAL-EDGE|203.0.113.0/24",
      "route_set:AS64500:RS-LOCAL-EDGE|2001:db8:fbf4::/48"
   ],
   "as_set": [
      "as_set:AS64500:AS-LOCAL-CUSTOMERS"
   ],
   "as_set_member": [
      "as_set:AS64500:AS-LOCAL-CUSTOMERS|AS64500"
   ],
   "aut_num": [
      "aut_num:AS64500"
   ],
   "mntner": [
      "mntner:LOCAL-IRR-MNT"
   ]
}
```

Expected normalized first-wave row details:

`ImportedIrrRouteObject`

- one IPv4 row with prefix `203.0.113.0/24`, origin ASN `AS64500`, and route-set membership summary including `AS64500:RS-LOCAL-EDGE`
- one IPv6 row with prefix `2001:db8:fbf4::/48`, origin ASN `AS64500`, and route-set membership summary including `AS64500:RS-LOCAL-EDGE`
- both rows should carry maintainer summary `LOCAL-IRR-MNT`

`ImportedIrrRouteSet`

- one row for `AS64500:RS-LOCAL-EDGE`
- `member_count` should be `2` in slice 1 because the local fixture expresses membership through the route and route6 objects' `member-of` attributes

`ImportedIrrRouteSetMember`

- one row connecting `AS64500:RS-LOCAL-EDGE` to `203.0.113.0/24`
- one row connecting `AS64500:RS-LOCAL-EDGE` to `2001:db8:fbf4::/48`
- both rows should use `member_type=prefix`

`ImportedIrrAsSet`

- one row for `AS64500:AS-LOCAL-CUSTOMERS`
- `member_count` should be `1`

`ImportedIrrAsSetMember`

- one row connecting `AS64500:AS-LOCAL-CUSTOMERS` to `AS64500`
- the row should use `member_type=asn`

`ImportedIrrAutNum`

- one row for `AS64500`
- `as_name` should be `AS-LOCAL-IRR`
- maintainer summary should include `LOCAL-IRR-MNT`
- contact handles should remain preserved in payload or summarized handle lists, but not as a first-wave imported person model

`ImportedIrrMaintainer`

- one row for `LOCAL-IRR-MNT`
- auth summary should indicate a filtered `BCRYPT-PW` style auth entry rather than preserving the raw hash
- admin contact handle summaries should include `LOCAL-IRR-PERSON`
- `upd-to` summary should include `irrd-dev@example.invalid`

Expected fixture-driven exclusions:

- no first-wave `ImportedIrrPerson` rows should be created
- no route-set member rows should be invented beyond the two prefixes referenced by `member-of`
- no as-set member rows should be invented beyond the single explicit `AS64500` member

The deterministic local import tests should use these counts and keys as contract assertions before any public live-source adapter is considered stable.

### Appendix C: Slice-1 Import Command And Job Signatures

The first-wave operator-facing import entry points should follow the same pattern already used for provider sync and reconciliation jobs.

#### Management command

Recommended command name:

- `sync_irr_source`

Recommended help text:

- `Import IRR state from a configured IRR source.`

Recommended arguments:

```text
--irr-source <int>                 required, IrrSource primary key
--fetch-mode <live_query|snapshot_import>
--snapshot-file <path>            optional, only valid with snapshot_import
--enqueue                         enqueue as a NetBox background job instead of running synchronously
```

Recommended synchronous contract:

- load `IrrSource` by primary key
- validate `fetch_mode`
- reject `--snapshot-file` unless `fetch_mode=snapshot_import`
- call `sync_irr_source(irr_source, fetch_mode=..., snapshot_file=...)`
- print the completed sync run and `IrrSnapshot` identifiers in the success message

Recommended enqueue contract:

- call `SyncIrrSourceJob.enqueue_for_source(...)`
- if the job is new, print a success message with the job id and source id
- if a job is already queued, print a warning message consistent with existing provider-sync commands
- if a sync is already running for the same source and input shape, print a warning rather than enqueueing another run

#### JobRunner

Recommended class name:

- `SyncIrrSourceJob`

Recommended Meta name:

- `IRR Source Import`

Recommended helper methods:

- `get_job_name(source, fetch_mode='live_query', snapshot_file=None)`
- `get_active_job_for_source(source, fetch_mode='live_query', snapshot_file=None)`
- `enqueue_for_source(source, fetch_mode='live_query', snapshot_file=None, user=None, schedule_at=None)`

Recommended `run()` signature:

```python
def run(
      self,
      irr_source_pk,
      fetch_mode='live_query',
      snapshot_file=None,
      *args,
      **kwargs,
):
```

Recommended `job.data` payload after completion:

```json
{
   "irr_source_pk": 0,
   "fetch_mode": "live_query",
   "snapshot_file": null,
   "irr_snapshot_pk": 0
}
```

Recommended duplicate-run guard:

- do not enqueue another job when an existing queued job has the same source and the same normalized input shape
- do not enqueue another job when an `IrrSnapshot` import is already running for the same source and same normalized input shape

Recommended normalized input-shape rules for deduplication:

- `snapshot_file` should be normalized to a stable string path or null
- `fetch_mode` must participate in the deduplication key
- later expansion arguments should only participate in deduplication if they materially change the imported snapshot contents

#### First-wave service signature

Recommended orchestration service entry point:

```python
def sync_irr_source(
      irr_source,
      *,
      fetch_mode='live_query',
      snapshot_file=None,
):
```

Recommended return contract:

- return the created `IrrSnapshot`
- persist imported family rows linked to that snapshot
- raise explicit validation or adapter errors for invalid source configuration, invalid snapshot-mode inputs, or unrecoverable normalization failures

The first-wave command and job contracts should stop at one source per run. Multi-source coordination belongs to later workflow layers and should not complicate the first import substrate.