# NetBox RPKI Plugin: High-Priority Enhancement Backlog for Hosted-RPKI Consumers

**Last updated:** April 12, 2026

## 1. Executive summary

This backlog now reflects the plugin as it actually exists, not as a hypothetical first-cut scope. The codebase already has a working replacement-aware ROA control loop, provider sync and provider-backed Krill write-through flows, stable provider-object identity tracking, governance metadata and approval history, a first operational dashboard, first operational ASPA inventory/import/reconciliation support, and a validated full plugin test suite at 296 tests. The remaining work is therefore not “make the plugin real”; it is to close the gap between this real current state and the desired end state of a provider-grade routing-security control plane.

The sections that follow are organized around three questions only: what the plugin can do now, what the end state should look like, and the preferred dependency order for closing the remaining gap.

## 2. Current-state implementation

The plugin is already beyond simple RPKI inventory. The current codebase now has a real operator workflow in four layers.

### 2.1 Inventory and standards-aligned schema

Implemented now:
- legacy inventory models for organizations, certificates, ROAs, and supporting entitlement relationships
- additive standards-aligned schema work for repository, publication, signed-object, trust-anchor, validation, and ASPA-related model families, documented later in this file
- registry-driven generation for UI, API, filter, table, detail, navigation, and GraphQL surfaces
- explicit separation of internal registry identity from public route, API, and GraphQL naming so generated surfaces remain stable even when internal model names and public slugs intentionally differ

### 2.2 Intent, reconciliation, and planning

Implemented now:
- writable operator policy objects for routing intent profiles, rules, and ROA intent overrides
- derived and historical reconciliation objects for derivation runs, intent rows, match rows, reconciliation runs, and result rows
- service, job, command, and API execution paths for deriving intent and running reconciliation
- comparison against both local ROA state and normalized provider-imported authorization snapshots
- replacement-aware drift classification for exact-prefix wrong-origin and maxLength mismatches across local and provider-imported state
- operator drill-down UX for intent, reconciliation, published-result, and change-plan-item detail pages
- replacement-aware ROA change-plan generation with paired create and withdraw actions plus before-state and after-state reporting

### 2.3 Provider sync, provider identity, and write-through

Implemented now:
- provider-account configuration and execution history via `RpkiProviderAccount`, `ProviderSyncRun`, `ProviderSnapshot`, `ImportedRoaAuthorization`, and `ProviderWriteExecution`
- live ARIN ROA import and live Krill ROA import
- scheduled due-sync orchestration via `sync_interval`, duplicate-enqueue protection, background jobs, management commands, API actions, and UI actions
- stable external provider-object identity tracking via `ExternalObjectReference`
- Krill-backed ROA preview, approve, apply, and post-apply re-sync flows, including replacement-aware add and remove deltas
- provider capability metadata so write support is explicit rather than inferred

### 2.4 Governance, reporting, and operator visibility

Implemented now:
- change-plan lifecycle state, actor attribution, ticket and change references, maintenance-window metadata, and approval history through `ApprovalRecord`
- read-only operations dashboard for failed or stale provider sync state plus ROA and certificate expiry visibility
- computed provider sync-health and next-due metadata in model, table, detail, API, and action surfaces
- focused and full regression coverage validating the merged implementation at 124 focused ROA-slice tests and 296 passing plugin tests overall

---

## 3. End-state objectives

This backlog should now be read against the desired end state, not against incremental short-term slices.

1. NetBox should express intended routing-security policy from real service context, not just store authored RPKI artifacts.
2. The plugin should ingest and normalize real provider state across multiple providers and object families, not just one provider and one object type.
3. Operators should be able to reconcile intended state, local modeled state, imported provider state, and eventually validated payload state in one coherent workflow.
4. Unsafe ROA and ASPA changes should be explainable before publication, including blast radius, over-authorization, and likely validation impact.
5. Publication workflows should be auditable, approval-aware, rollback-capable, and provider-agnostic at the contract level even when adapters differ.
6. The UI should surface operational health directly: sync drift, expiry, publication freshness, validation observations, and provider diffs.
7. The data model should remain standards-aligned enough to support repositories, signed objects, validation outputs, and future provider/object expansion without a second schema reset.
8. The plugin should support enterprise and provider operating models, including customer or downstream resources managed on behalf of another party.

---

## 4. Capability gap backlog

Each priority below now describes three things only: the desired end state, the current implementation, and the remaining gap.

### Priority 1: Intent-to-ROA reconciliation

- End-state objective: deterministic derivation of intended ROA state from NetBox service context, with clear drift classification, operator drill-down, and actionable remediation planning.
- Current-state implementation: the core intent and reconciliation stack exists, runs through service, job, command, and API surfaces, compares both local and provider-imported ROA state, classifies replacement-required exact-prefix drift, exposes richer reconciliation and plan drill-down, generates paired replacement create and withdraw plan actions, persists lint and simulation analysis objects, records draft-plan semantics for `create`, `replace`, and `withdraw`, and exposes aggregate API and operations-dashboard roll-ups for reconciliation and change-plan health.
- Gap to close: the core Priority 1 dependency slice is now complete. Remaining work is refinement work rather than foundational work: operator exception and acknowledgement flows for lint findings, richer simulation explanations and scenario coverage, broader scoped roll-up reporting, and finer-grained local-model reshape semantics beyond the current `create` or `replace` or `withdraw` contract.
- Preferred closure order: treat Priority 1 as functionally complete for dependency purposes. Any additional work here should be taken only as follow-on refinement that unblocks later provider, governance, or bulk-authoring work.

#### Immediate follow-on slice: close web-UI and API workflow-surface gaps

The best way to represent this work in the backlog is as a **Priority 1 refinement slice**, not as a separate top-level priority. These gaps sit directly inside the already-built intent/reconciliation/change-plan workflow, and closing them is mostly a matter of operator-surface parity rather than new domain modeling.

Treat the remaining gaps in two categories:

- **Action-surface parity gaps:** custom API actions that represent real operator workflow steps and therefore should gain an explicit web-UI affordance.
- **Summary-surface parity gaps:** custom API summary endpoints that should not necessarily become one-off web pages, but should instead feed list-page summary cards, dashboard roll-ups, or other existing operator reporting surfaces.

Use that distinction to avoid the wrong closure pattern. The goal is not naive one-route-per-route parity. The goal is to ensure every meaningful workflow step is reachable from the web UI and every meaningful roll-up is visible to operators somewhere in the UI.

##### Action-surface parity items to add

- Add a web-UI action for `routingintentprofile.run`.
  The API already exposes `POST routingintentprofile/{pk}/run/`, but the Routing Intent Profile detail UI currently has no corresponding action button or execution form. Add a profile-detail action that lets an operator trigger a run from the UI and supply the same execution inputs now accepted by the API, especially `comparison_scope` and optional `provider_snapshot`.
- Add a web-UI action for `roareconciliationrun.create_plan`.
  The API already exposes `POST roareconciliationrun/{pk}/create_plan/`, but the ROA Reconciliation Run detail UI currently exposes drill-down tables only. Add a create-plan action from the reconciliation-run detail view so an operator can move from completed reconciliation directly into change-plan generation without dropping to the API.
- Add a web-UI action for `roachangeplan.simulate`.
  The API already exposes `POST roachangeplan/{pk}/simulate/`, but the ROA Change Plan detail UI currently exposes only `preview`, `approve`, and `apply`. Add a simulation action and render its latest result summary in the same operator flow as preview and lint output.

##### Summary-surface parity items to add

- Surface `roareconciliationrun.summary` in the web UI, but not as a standalone `summary/` page by default.
  The API already exposes `GET roareconciliationrun/summary/`. The preferred UI closure is to feed the same aggregate counts into existing reconciliation list pages, dashboard cards, or other roll-up surfaces rather than create a disconnected summary endpoint page.
- Surface `roachangeplan.summary` in the web UI, but not as a standalone `summary/` page by default.
  The API already exposes `GET roachangeplan/summary/`. The preferred UI closure is to reuse those aggregates in change-plan list headers, operations dashboard cards, or similar reporting surfaces so operators can see fleet state without calling the API directly.

##### Explicit implementation guidance for this slice

- Keep the API summary endpoints as the machine-readable contract even if the UI consumes them indirectly.
- Prefer adding UI actions to existing detail pages over creating isolated new pages when the operator is already in the relevant workflow object.
- Reuse the existing metadata-driven detail action pattern so new buttons remain registry- and permission-aware.
- Make any new UI execution forms carry the same input contract as the matching API action wherever practical, especially for `comparison_scope`, `provider_snapshot`, and future execution flags.
- Decide explicitly whether a surface is intentionally API-only. If it remains API-only, record the reason in the backlog or implementation notes rather than leaving the asymmetry accidental.

##### Acceptance criteria for closing this gap

- Every custom API workflow action that represents a human operator step is either reachable from the web UI or explicitly documented as API-only by design.
- Routing Intent Profile, ROA Reconciliation Run, and ROA Change Plan detail pages expose the missing operator actions needed to complete the intended workflow without dropping to the API.
- Reconciliation and change-plan aggregate health data become visible somewhere in the web UI, even if the underlying API summary endpoints remain the canonical data source.
- Tests prove that custom action parity is intentional: route presence, permission enforcement, and expected UI affordances should all be covered together.

### Priority 2: Hosted-provider synchronization

- End-state objective: provider-agnostic synchronization of ROAs, ASPAs, publication-topology metadata, published certificates, published signed objects, and related provider control-plane metadata with durable identity, retained snapshots, meaningful diffs, and health visibility.
- Current-state implementation: ARIN and Krill ROA sync exist; Krill ASPA sync and the first broader Krill family/reporting slice now exist; scheduled orchestration, sync-health, external object references, operator-triggered sync surfaces, and retained diff artifacts are in place.
- Gap to close: broader provider coverage, broader object-family coverage, richer snapshot diff or report views, a cleaner common provider contract beyond the current ROA-focused flows, and an explicit split between provider control-plane synchronization and repository/publication observation.
- Preferred closure order: second. This is the highest-value gap directly adjacent to what already works.

#### Detailed implementation plan for Priority 2: Krill-only execution slice

This implementation plan deliberately narrows delivery scope to **Krill** because that is the only provider path we can test end to end right now. The shared sync substrate should still be refactored to remain provider-neutral at the contract level, but no new ARIN work should be taken in this slice beyond preserving current behavior.

##### Architectural correction for this slice

The provider account should be treated as the operational anchor for synchronization, not as the authoritative source of every published RPKI artifact. For standards-aligned inventory, the authoritative published-state evidence should come from repository publication points and the objects attested there, especially manifests, CRLs, EE certificates, and published signed objects. Provider-management payloads still matter, but they should be treated as control-plane metadata and auxiliary linkage evidence rather than as the canonical published certificate inventory.

In practical terms, that means this slice should distinguish two kinds of synchronized family:

- control-plane families such as `ca_metadata`, `parent_links`, `child_links`, and `resource_entitlements`
- publication-observation families such as `publication_points`, `certificate_inventory`, and `signed_object_inventory`

The current contract name `certificate_inventory` can remain for compatibility if needed, but its semantics should be corrected: it should mean repository-derived published certificate observation scoped by the synced provider account, not an imagined first-class Krill management endpoint returning certificate rows.

##### Scope guardrails for this slice

- Keep existing ARIN import code functional, but treat it as compatibility-only during this effort.
- Require every new provider-sync behavior to be acceptance-tested against a Krill-backed development instance or deterministic Krill fixtures.
- Treat snapshot retention, diffing, and reporting as first-class deliverables, not as cleanup work after ingestion.
- Extend the existing provider sync pipeline instead of introducing a second side-channel import system for repository observation, certificates, or ASPA-specific reporting.
- Preserve the current external identity model and expand it rather than replacing it.
- Keep provider control-plane sync and publication observation in one coherent workflow, but do not collapse them into the same semantic family.
- Do not treat certificate-bearing management payload fragments as the canonical certificate inventory when repository-derived evidence is the stronger standards-aligned source.

##### End-state for the Krill slice

By the end of this slice, a Krill provider account should produce a retained, queryable snapshot that covers both provider control-plane metadata and repository/publication observation families, carries per-family summary counts, can be compared against the immediately previous snapshot and an arbitrary prior snapshot, and drives operator-facing report views that explain what changed, what disappeared, what is newly stale, and what requires follow-on reconciliation. The result should feel like a real provider-state control plane backed by repository evidence, not a raw import log.

##### Object-family coverage to implement in this slice

The current sync covers Krill ROA routes and ASPAs only. The next slice should be intentionally broad.

Implement or harden these Krill-backed families:

- ROA authorizations: keep the current import path, but enrich imported rows with stronger per-object metadata, source timestamps when available, and stable snapshot-level family summaries.
- ASPAs: keep the current import path, but add richer provider-authorization metadata, stronger identity normalization, and first-class diff reporting at both ASPA and provider-member levels.
- CA account metadata: import Krill CA handle, CA state, publication mode, repository linkage, and operational status so the provider account detail page can explain what control plane is actually being synced.
- Parent relationships: import parent CA relationships, service URIs, last-known exchange state, and status so parent drift or broken parent linkage can be reported.
- Child and delegated-customer relationships: import child handles, resource delegation summaries, and status so the plugin can reason about downstream or on-behalf-of inventory later without another sync substrate rewrite.
- Resource entitlement summaries: import Krill resource-class or entitlement summaries for prefixes and ASNs held by the synced CA so operators can compare provider-held resources against NetBox intent scope.
- Repository and publication-point metadata: import repository endpoint, RRDP or rsync publication metadata, notify URI, and publication-state summaries so snapshot reporting can expose publication freshness and topology.
- Published certificate observation: derive certificate inventory from repository/publication evidence available to the synced Krill account, using manifests, CRLs, publication-point membership, published object metadata, and certificate-bearing auxiliary payloads where available. Treat provider-management certificate fields as linkage hints, not as the canonical inventory source.
- Signed-object inventory: record summary-level visibility into emitted ROA objects, ASPA objects, manifests, CRLs, and additional published object families when the Krill dev instance exposes them cleanly enough to support deterministic parsing.

The plan should assume that some of these families may arrive in two tiers:

- Tier 1: control-plane objects and publication metadata exposed directly by current Krill API endpoints, plus any repository object stream we can parse deterministically from the current Krill development instance.
- Tier 2: objects that require fuller repository-observation parsing, richer fixture support, or additional Krill/repository evidence before we can claim end-to-end importer support. For Tier 2, land the schema hooks, capability flags, and report placeholders in this slice even if one or two importer implementations remain gated behind fixture availability.

##### Shared architecture changes required before parallel work opens up

The current `provider_sync.py` flow is still a largely monolithic importer with ROA-first assumptions. Before sending many sub-agents into the codebase, land a narrow enabling refactor that creates stable ownership boundaries.

1. Introduce a family-oriented sync contract.
   Define explicit sync-family identities such as `roa_authorizations`, `aspas`, `ca_metadata`, `parent_links`, `child_links`, `resource_entitlements`, `publication_points`, `certificate_inventory`, and `signed_object_inventory`. Each family should declare whether it is a control-plane or publication-observation family, along with capabilities, fetch order, summary keys, and import responsibility.
2. Separate provider control-plane synchronization from publication-point observation without creating separate operator workflows.
   The same provider snapshot should be allowed to carry both kinds of family, but the contract should make their evidence source explicit so reporting and later validator correlation do not confuse management state with published state.
3. Split transport, parsing, persistence, and diffing into separate modules.
   Move Krill HTTP fetch logic into a Krill adapter module, keep orchestration in the shared provider sync service, and isolate diff generation into its own service so report work is not blocked on importer internals.
4. Make snapshot summaries family-aware.
   `ProviderSnapshot.summary_json` and `ProviderSyncRun.summary_json` should stop being a shallow count blob and become a stable per-family summary contract with fetched, imported, unchanged, added, removed, changed, stale, failed, and warning counts.
5. Expand external identity handling by object family.
   `ExternalObjectReference` already gives durable identity. Extend it so each imported family can bind to a stable provider identity and so diffing can reason about persistence, churn, and disappearance across snapshots.
6. Add first-class diff artifacts.
   Do not compute diffs only on the fly in views. Persist snapshot comparison objects so the UI, API, GraphQL, and later governance/reporting layers all share one explanation source.

##### Proposed model additions for this slice

Use additive migrations and compatibility shims. A likely model shape for this slice is:

- `ProviderSnapshotDiff`: one row per snapshot comparison, typically latest-versus-previous but also usable for arbitrary compare operations.
- `ProviderSnapshotDiffItem`: one row per changed, added, removed, reappeared, or stale object identity, with family, change type, before-state JSON, after-state JSON, and summary fields for table filtering.
- `ImportedProviderCertificate`: repository-derived published-certificate observation row linked to a snapshot and, when possible, to existing certificate, EE-certificate, manifest, CRL, publication-point, or signed-object models. The compatibility-friendly name is acceptable, but the stored semantics should be publication-backed, not management-plane-backed.
- `ImportedProviderPublicationPoint`: imported repository or publication metadata row linked to a snapshot.
- `ImportedProviderParentLink`: imported parent-relationship row linked to a snapshot.
- `ImportedProviderChildLink`: imported child or delegation row linked to a snapshot.
- `ImportedProviderResourceEntitlement`: imported provider-held resource summary row for prefix and ASN entitlement visibility.
- `ImportedProviderSignedObject`: imported summary row for provider-visible signed objects beyond the existing ROA and ASPA records, with room for manifest and CRL classification as publication observation matures.

Exact names can still be tuned, but the separation matters:

- raw imported state by family
- durable cross-snapshot identity
- persisted diff artifacts
- roll-up summary views built on top of those artifacts

##### Snapshot diff and reporting enhancements to deliver in this slice

Do not stop at a single “records imported” count. The operator-facing reporting target should be much richer.

Implement these report surfaces:

- Provider account detail roll-up showing latest sync health, next due sync, last successful sync, family-by-family counts, last diff summary, and last error summary.
- Provider snapshot detail page with per-family summary cards, retained raw summary JSON, and related tables for imported families.
- Snapshot comparison detail page showing added, removed, changed, unchanged, reappeared, and now-stale counts by family.
- Diff-item table views filterable by family, change type, object identity, prefix, ASN, child handle, certificate identifier, and publication point.
- Family-specific delta drill-down views:
   - ROA diff view with prefix, ASN, maxLength, external identity, and replacement classification.
   - ASPA diff view with customer ASN plus provider-set additions and removals.
   - Published-certificate diff view with validity-window changes, issuer or subject changes, publication-point movement, and newly expired or soon-expiring state.
   - Parent or child relationship diff view with status and endpoint changes.
   - Publication-point diff view with notify URI, publication URI, and freshness changes.
- “What disappeared from Krill?” report that surfaces objects missing from the latest snapshot but present in the prior retained snapshot.
- “What is newly stale?” report that highlights imported rows whose identity persists but whose linked local object resolution now fails or no longer matches provider reality.
- Snapshot timeline summary for a provider account showing per-run churn volume so operators can distinguish steady state from large provider-side events.
- Operations dashboard expansion so stale or failed sync is only the first layer; add large-change warnings, repeated family import failures, publication freshness warnings, and certificate-expiry roll-ups.

##### Immediate single-sub-agent implementation slice: publication-backed inventory correction

This is the next architectural correction slice that a single **gpt5.4-mini** sub-agent should be able to handle without fighting the broader provider-sync codebase.

Goal:
- realign the provider-sync contract and reporting language so `certificate_inventory` explicitly means repository-derived published-certificate observation scoped by a provider account and its publication points

Non-goals:
- do not implement a full manifest parser
- do not implement a full CRL parser
- do not rename database tables or public routes in this slice
- do not expand ARIN support

Primary files:
- `netbox_rpki/services/provider_sync_contract.py`
- `netbox_rpki/services/provider_sync_diff.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/tests/test_provider_sync.py`
- this backlog document and any closely related implementation notes

Implementation steps:
1. Update the family contract so `certificate_inventory` is explicitly labeled as a publication-observation family rather than a generic provider-management family.
2. Update capability metadata and placeholder reasons so the limitation is described as “repository-derived certificate observation not yet fully implemented from Krill-backed publication evidence,” rather than as “Krill lacks a certificate endpoint.”
3. Update provider snapshot and diff reporting language so certificate-family cards, summaries, and placeholder text consistently refer to published-certificate observation and publication evidence.
4. Preserve the existing family key and summary shape for compatibility, but add enough metadata such as `family_kind` and `evidence_source` for later slices to distinguish control-plane families from publication-observation families.
5. Update focused tests so the contract explicitly guards this semantic distinction.

Acceptance criteria:
- the summary contract exposes enough metadata to tell whether a family is control-plane or publication-observation
- `certificate_inventory` remains present for compatibility but is no longer described as a provider-management certificate API
- provider snapshot reporting and diff summaries use publication-observation language consistently
- focused provider-sync tests prove the new family metadata and limitation wording

Suggested sub-agent prompt:
- "Update the Priority 2 provider-sync contract and reporting language so the existing `certificate_inventory` family is explicitly treated as repository-derived published-certificate observation, not as a Krill management-plane certificate endpoint. Preserve compatibility of the current family key and summary schema, limit changes to contract/reporting/tests/docs, do not implement manifest or CRL parsing in this slice, and keep the full meaning aligned with publication-point-backed observation. Return a concise summary of code changes, test coverage added or updated, and any follow-on blockers."

##### API and query-surface enhancements to deliver in this slice

The richer snapshot and diff layer should be available everywhere the existing registry-based surfaces already operate.

Add or extend these surfaces:

- REST serializers and viewsets for each new imported family model and for snapshot diff models.
- summary endpoints for provider accounts and provider snapshots, mirroring the existing reconciliation summary pattern.
- a compare action on `ProviderSnapshot` that either returns an existing persisted diff or creates one on demand and returns its identifier.
- GraphQL types and list fields for new imported families and diff objects so the reporting layer can be consumed programmatically.
- filtersets and tables that make family, change type, status, and object identity first-class query inputs.

##### Parallel execution plan for multiple gpt5.4-mini sub-agents

The main risk to parallelization is file conflict density in `models.py`, `object_registry.py`, `detail_specs.py`, and the provider sync service. Avoid that by using a short integration lead phase followed by clearly partitioned tracks.

###### Phase 0: one integration lead agent only

This agent owns the enabling refactor and lands the shared contract first.

- Define the sync-family enumeration and shared summary contract.
- Carve Krill adapter code out of the monolithic provider sync service.
- Introduce placeholder diff models and wire them into the registry as read-only objects if the registry path is chosen.
- Freeze naming for summary keys, diff types, and object-family labels so parallel agents do not invent conflicting contracts.

Once that branch lands, split follow-on work across parallel agents.

###### Track A: Krill control-plane and publication-observation parser agent

Primary responsibility: fetch and parse the additional Krill object families.

- Own the Krill adapter module plus repository-observation parsing helpers and any new publication-evidence fixtures.
- Add fetchers and parsers for CA metadata, parent links, child links, entitlement summaries, publication metadata, and repository-artifact observation rooted in publication points and their contents.
- Return normalized record objects without owning model persistence logic.

###### Track B: persistence and identity agent

Primary responsibility: persist imported family rows and bind stable external identities.

- Own model additions for the new imported families.
- Extend `ExternalObjectReference.object_type` coverage and provider identity builders.
- Implement idempotent import routines for each new family.
- Ensure all imported rows link cleanly to `ProviderSnapshot` and, where applicable, existing local models.

###### Track C: diff engine agent

Primary responsibility: build retained snapshot comparison artifacts.

- Own `ProviderSnapshotDiff` and `ProviderSnapshotDiffItem` generation logic.
- Implement family-specific diff classification rules.
- Produce family-by-family summary JSON used by UI, API, and dashboard surfaces.
- Add compare-latest-versus-previous behavior and arbitrary snapshot compare support.

###### Track D: reporting and detail-page agent

Primary responsibility: make the new data understandable to operators.

- Own detail specs, tables, list views, and any new report templates.
- Upgrade provider account, provider snapshot, and operations dashboard views.
- Add diff-focused detail pages and family-specific related tables.
- Keep surfaces read-only unless there is a clear operator action already justified by current workflow.

###### Track E: API and GraphQL agent

Primary responsibility: expose the new imported families and diff artifacts programmatically.

- Own `api/serializers.py`, `api/views.py`, `api/urls.py`, and GraphQL type or filter updates.
- Add compare and summary actions.
- Keep method exposure aligned with the read-only reporting contract.

###### Track F: test and publication-evidence fixture agent

Primary responsibility: keep the slice verifiable while other agents move fast.

- Build deterministic publication-point and repository-artifact fixtures for each new family and change scenario.
- Expand unit tests for publication-observation parsing, import, identity reuse, diff generation, and summary roll-ups.
- Extend registry-driven view, API, and GraphQL contract tests for each new routed object.
- Add targeted dashboard and detail-page tests for the new reporting slices.

###### Track G: documentation and operator-workflow agent

Primary responsibility: keep the documentation, test plan, and contributor guidance aligned.

- Update this backlog as milestones land.
- Update `README.md`, `TEST_SUITE_PLAN.md`, and contributor guidance for the richer Krill sync contract.
- Document which Krill families are fully synced, partially synced, or schema-only pending fixture support.

##### Merge choreography and conflict management

To keep parallel execution practical, enforce these ownership rules:

- Only the integration lead edits the initial family contract and baseline model additions before the first merge.
- After that merge, Track A owns Krill fetch and parse modules; Track B owns imported-family persistence; Track C owns diff services; Track D owns tables, detail specs, and dashboard views; Track E owns API and GraphQL files; Track F owns fixtures and tests.
- Avoid having more than one active branch editing `models.py` or `object_registry.py` at the same time. If more model additions are required, batch them through the persistence agent.
- Prefer new service modules over repeatedly growing `provider_sync.py` so multiple agents are not forced into the same file.

##### Dependency-ordered issue and PR breakdown for sub-agents

Phase 0 is now complete. The dependency ladder below assumes the following substrate is already merged and stable:

- family-oriented summary contract
- extracted Krill adapter module
- persisted `ProviderSnapshotDiff` and `ProviderSnapshotDiffItem`
- registry exposure for the Phase 0 diff objects
- a green full plugin suite at the Phase 0 baseline

Use the issue titles as tracking units and the PR titles as merge units. Each sub-agent should own exactly one PR at a time.

###### Wave 1: unblock the next persistence and import slice

Issue 1 / PR 1: Publication-point evidence fixture inventory and repository artifact map

- Owner: Track F with Track A support
- Depends on: Phase 0 only
- Goal: capture deterministic publication-point and repository-artifact fixtures plus a written evidence map for the Krill families we can actually support next: `ca_metadata`, `parent_links`, `child_links`, `resource_entitlements`, `publication_points`, repository-backed `certificate_inventory`, and `signed_object_inventory`
- Primary files: `netbox_rpki/tests/`, `devrun/`, and any new fixture directories or fixture helper modules
- Deliverables:
   - deterministic publication-point and repository-artifact fixtures for each Tier 1 family
   - explicit notes on which evidence sources are Tier 1 versus Tier 2 on the current Krill dev instance
   - parser-input fixtures rich enough to drive publication-observation import and diff tests later
- Acceptance criteria:
   - every claimed Tier 1 family has at least one stable standards-aligned fixture source
   - fixture naming and layout are documented well enough that later PRs do not need to rediscover publication topology or repository artifact shape
   - no schema or importer behavior changes land in this PR

Issue 2 / PR 2: Imported-family schema and registry substrate

- Owner: Track B
- Depends on: Phase 0 only
- Goal: land the additive model layer for the next imported families so later importer work does not fight over `models.py` and `object_registry.py`
- Primary files: `netbox_rpki/models.py`, `netbox_rpki/object_registry.py`, `netbox_rpki/migrations/`, `netbox_rpki/tests/utils.py`, `netbox_rpki/tests/registry_scenarios.py`
- Deliverables:
   - explicit imported-family models for the Tier 1 Krill families, with publication-observation semantics made explicit for certificate and signed-object families
   - any needed `ExternalObjectType` extensions or supporting enums not already present
   - read-only registry wiring, test builders, and shared scenario support for the new models
- Acceptance criteria:
   - migration is additive and `makemigrations --check --dry-run` is clean
   - registry-driven view, API, and GraphQL smoke/contract tests can construct the new read-only families
   - this PR does not yet fetch or import live Krill data

###### Wave 2: fetch and normalize the new Krill families and publication evidence

Issue 3 / PR 3: Krill adapter and publication-observation parser expansion for Tier 1 families

- Owner: Track A
- Depends on: PR 1
- Goal: extend the Krill adapter with fetchers, parsers, and normalized record classes for the Tier 1 families confirmed by the evidence inventory, including deterministic publication-point and repository-artifact evidence available from the Krill development instance
- Primary files: `netbox_rpki/services/provider_sync_krill.py` and new fixture-backed parser tests
- Deliverables:
   - family-specific dataclasses or normalized record shapes
   - fetch helpers for the supported Krill control-plane endpoints and publication-evidence discovery points
   - parser helpers that return normalized records from publication points and repository artifacts but do not persist them
- Acceptance criteria:
   - parser coverage exists for success, missing-field, and minimal-payload cases
   - adapter code stays provider-specific and does not take over orchestration or persistence responsibilities
   - no edits to `models.py` or `object_registry.py`

Issue 4 / PR 4: Persistence and external identity binding for new families

- Owner: Track B
- Depends on: PR 2 and PR 3
- Goal: persist the new imported-family rows during sync and bind them to durable external identities
- Primary files: `netbox_rpki/services/provider_sync.py`, new persistence helper modules if needed, and any targeted model helpers
- Deliverables:
   - idempotent import routines for each Tier 1 family
   - stable provider-identity builders per family
   - family-aware summary-count population in snapshot and sync-run summaries
- Acceptance criteria:
   - repeated syncs do not duplicate imported rows for unchanged provider objects
   - imported rows link cleanly to `ProviderSnapshot` and to local models where resolution is available
   - the new families appear in summary JSON with correct counts and statuses

###### Wave 3: extend retained diff behavior beyond ROAs and ASPAs

Issue 5 / PR 5: Diff engine expansion for additional families

- Owner: Track C
- Depends on: PR 4
- Goal: extend retained snapshot diff generation to every newly imported Tier 1 family
- Primary files: `netbox_rpki/services/provider_sync_diff.py` plus focused diff tests
- Deliverables:
   - family-specific identity normalization and state serialization
   - added, removed, changed, unchanged, and stale classification where meaningful
   - family-level diff summary rollups that feed the existing summary schema
- Acceptance criteria:
   - back-to-back identical snapshots produce unchanged counts and no diff items for those families
   - changed snapshots produce family-appropriate diff items with usable table fields
   - no UI or API work is bundled into this PR beyond what the tests need for model construction

###### Wave 4: expose and explain the richer data

Issue 6 / PR 6: Reporting and detail-page expansion

- Owner: Track D
- Depends on: PR 5
- Goal: make the expanded imported families and diffs understandable in the UI
- Primary files: `netbox_rpki/detail_specs.py`, `netbox_rpki/tables.py`, `netbox_rpki/views.py`, templates, and any dashboard helpers
- Deliverables:
   - richer provider account and provider snapshot detail views
   - snapshot comparison and diff-item list/detail surfaces
   - family-specific tables or related-table sections where the generic view is not sufficient
   - operations dashboard expansion for large-change, repeated-family-failure, and freshness warnings
- Acceptance criteria:
   - operators can answer what changed, what disappeared, and what is stale from the UI without reading raw JSON
   - reporting remains read-only
   - focused view/table tests cover the new report surfaces

Issue 7 / PR 7: REST and GraphQL exposure for expanded sync families and diffs

- Owner: Track E
- Depends on: PR 5
- Goal: expose the richer imported-family and diff artifacts programmatically
- Primary files: `netbox_rpki/api/serializers.py`, `netbox_rpki/api/views.py`, `netbox_rpki/api/urls.py`, `netbox_rpki/graphql/filters.py`, `netbox_rpki/graphql/types.py`, `netbox_rpki/graphql/schema.py`
- Deliverables:
   - serializers and viewsets for the new imported families
   - compare and summary actions for provider snapshots where justified by the existing API shape
   - GraphQL types and fields for the new reporting objects
- Acceptance criteria:
   - API and GraphQL coverage match the read-only reporting contract
   - compare surfaces return persisted diff artifacts rather than ad hoc recalculations
   - this PR can merge in parallel with PR 6 once PR 5 is in

###### Wave 5: stabilization and closure

Issue 8 / PR 8: Full-slice hardening, docs, and release-gate closure

- Owner: Track F and Track G
- Depends on: PR 6 and PR 7
- Goal: turn the expanded Krill sync slice into a release-ready, documented, and fully validated increment
- Primary files: test suites, `README.md`, `TEST_SUITE_PLAN.md`, this backlog, and contributor guidance as needed
- Deliverables:
   - focused regression coverage for parsing, import, identity reuse, diff generation, reporting, API, and GraphQL
   - any missing fixture refinements needed after the implementation PRs settle
   - updated docs describing which Krill families are fully supported, partially supported, or schema-only
- Acceptance criteria:
   - focused provider-sync and report-surface commands are green
   - the full plugin suite is green
   - docs and test plan reflect the actual delivered family coverage

###### Recommended sub-agent assignment pattern after Phase 0

Use this merge order unless fixture discovery forces a narrower first slice:

1. Run PR 1 and PR 2 in parallel.
2. Start PR 3 after PR 1 lands.
3. Start PR 4 after PR 2 and PR 3 land.
4. Start PR 5 after PR 4 lands.
5. Start PR 6 and PR 7 in parallel after PR 5 lands.
6. Finish with PR 8 as the closure and hardening lane.

If the Krill dev instance only exposes a subset of the planned Tier 1 families cleanly, keep the PR numbering and ownership the same, but narrow PR 2 through PR 7 to the confirmed family subset instead of inventing speculative importer behavior.

##### Recommended delivery milestones

1. Land the family-oriented sync contract and baseline diff models.
2. Expand Krill ingestion beyond ROAs and ASPAs to at least CA metadata, parent links, child links, publication metadata, and certificate inventory.
3. Persist durable snapshot diffs and expose family-level summary counts.
4. Ship provider account, provider snapshot, and snapshot-compare report views with rich tables and filters.
5. Expose the same capabilities via REST and GraphQL.
6. Harden the slice with fixture-backed regression coverage and updated docs.

##### Closure criteria for Priority 2 in this Krill-only slice

Consider this priority closed for the current execution window only when all of the following are true:

- Krill sync covers materially more than ROAs and ASPAs and does so through explicit family contracts.
- Retained snapshots can be compared and the comparison is explainable through persisted diff artifacts rather than ad hoc view code.
- Provider account and provider snapshot surfaces show meaningful family-aware health and churn reporting.
- External object identity is durable across snapshots for every imported family implemented in this slice.
- REST, UI, and GraphQL surfaces exist for the new reporting objects where appropriate.
- Focused provider-sync and report-surface tests are green, and the full plugin suite remains green.
- No net-new ARIN work is required to declare the slice complete.

### Priority 3: ASPA operational support

- End-state objective: ASPA intent, provider synchronization, reconciliation, approval, and reporting should be first-class alongside ROAs.
- Current-state implementation: the first operational ASPA slice is now in place. `ASPA` inventory is hardened with provider-authorization constraints and detail UX, Krill-backed imported ASPA state is normalized through the provider-sync layer, and ASPA intent/reconciliation objects and services now exist with job, command, API, and drill-down/operator surfaces.
- Gap to close: provider-backed ASPA write-back, broader provider and object-family coverage beyond the current Krill ASPA import path, richer reporting/diffing, and eventual lint/simulation workflows analogous to the ROA roadmap.
- Preferred closure order: extend the now-shared control-plane surfaces rather than building an ASPA-specific side path.

### Priority 4: ROA linting and safety analysis

- End-state objective: operators can see when intended or published ROAs are too broad, unnecessary, risky, or inconsistent with routing intent.
- Current-state implementation: a first dedicated lint-result layer now exists. Reconciliation and change-plan flows can persist `ROALintRun` and `ROALintFinding` records, expose summary counts in API and UI surfaces, and present operator drill-down from reconciliation and plan detail pages.
- Gap to close: deepen the rule set, add operator explanations and exception handling, and decide how lint acknowledgements or suppressions should feed approval and reporting workflows.
- Preferred closure order: treat the current implementation as the first delivered slice, then iterate here before adding heavier governance on top of the same plan objects.

### Priority 5: ROV impact simulation

- End-state objective: before approval or apply, operators can see predicted validation outcomes and blast radius for proposed changes.
- Current-state implementation: a first plan-level simulation layer now exists. Change-plan creation can persist `ROAValidationSimulationRun` and `ROAValidationSimulationResult` records, API surfaces expose the latest simulation summary, and operators can review predicted valid, invalid, and not-found counts from plan detail and aggregate surfaces.
- Gap to close: improve simulation fidelity and operator explanation quality, add richer scenario coverage and blast-radius reasoning, and decide whether simulation should become a gated approval input rather than an informational analysis artifact.
- Preferred closure order: continue iterating after linting, with simulation refinement kept aligned to the same reconciliation and plan contracts rather than branching into a separate workflow.

### Priority 6: Bulk generation and templating

- End-state objective: large estates can generate and maintain ROA intent through reusable policy templates, regeneration logic, and bulk workflows.
- Current-state implementation: reconciliation can already derive expected state and create narrow change plans, but there is no templating or bulk policy authoring layer yet.
- Gap to close: declarative templates, bulk planning objects, regeneration semantics, and scoped exceptions for traffic engineering, anycast, mitigation, and customer edge use cases.
- Preferred closure order: after linting and simulation basics. Bulk authoring without safety rails would just accelerate mistakes.

### Priority 7: Deeper NetBox binding and service context

- End-state objective: policy can be expressed and explained in terms of tenant, VRF, site, region, service role, provider, circuit, exchange, or other operating context.
- Current-state implementation: the existing intent layer already binds to core NetBox context such as prefixes, ASNs, tenant, VRF, site, region, tags, and custom fields.
- Gap to close: broader topology and service-context binding, better inheritance or profile semantics, and more expressive grouping for operator-scale policy reuse.
- Preferred closure order: in parallel with bulk templating and ASPA expansion where dependencies allow.

### Priority 8: Change control and auditability

- End-state objective: publication workflows are policy-aware, multi-stage, rollback-capable, and fully auditable across providers.
- Current-state implementation: ROA change plans now support preview, approval, apply, actor attribution, maintenance-window metadata, ticket and change references, approval history, and provider execution audit rows.
- Gap to close: rollback bundles, multi-stage approvals, richer publication-state semantics, and extension of the governance contract beyond the current Krill-backed ROA slice.
- Preferred closure order: after linting and simulation are available for the same plan objects. Governance should wrap a safer decision surface, not precede it.

### Priority 9: Lifecycle, expiry, and publication health reporting

- End-state objective: operators can see expiry risk, stale publication, sync age, provider health, and publication freshness from a single reporting layer.
- Current-state implementation: the operations dashboard and computed provider sync-health cover stale or failed syncs plus ROA and certificate expiry windows.
- Gap to close: exports, thresholds, alerting hooks, publication-observation data, and richer timeline or diff-oriented reporting.
- Preferred closure order: alongside provider sync maturation. Reporting is only as good as the underlying sync and publication evidence.

### Priority 10: IRR coordination

- End-state objective: ROA intent and IRR route-object intent can be compared, reported, and eventually coordinated.
- Current-state implementation: no active IRR coordination workflow exists yet.
- Gap to close: model IRR intent and consistency results, then surface mismatches without blocking core RPKI workflows.
- Preferred closure order: after reconciliation, linting, and provider diff surfaces are mature. IRR is valuable, but not on the critical path for current provider-write maturity.

### Priority 11: External validator and telemetry overlays

- End-state objective: authored objects, imported provider objects, and relying-party observations can all be correlated in one operational view.
- Current-state implementation: standards-oriented validation-model groundwork exists in the architecture layer, but active operator overlays are not yet wired into the main workflow.
- Gap to close: import validation observations, connect them to existing ROA and ASPA objects, and expose evidence in dashboards, drill-downs, and change reviews.
- Preferred closure order: after provider sync and lifecycle reporting mature. External evidence is most useful once authored and imported state are already coherent.

### Priority 12: Downstream and on-behalf-of authorization modeling

- End-state objective: the plugin can represent resources or policy operated on behalf of downstream customers or delegated entities without blurring ownership and responsibility.
- Current-state implementation: organization and tenancy concepts exist, but downstream authorization relationships are not modeled as first-class operating constructs.
- Gap to close: explicit downstream or managed-authorization relationships, clearer ownership semantics, and workflow support for upstream-managed publication.
- Preferred closure order: late. This matters for provider-scale operating models, but it builds on a mature core rather than defining it.

---

## 5. Preferred closure order

The preferred order for closing the current gap is dependency-driven rather than milestone-driven. The ROA control-loop foundation is now in place, so the active order starts with the next dependent layers.

1. Complete provider synchronization as a reusable substrate.
   Add broader provider coverage, broader object-family coverage, and more useful snapshot and health reporting before widening automation further.
2. Mature the safety-analysis layers already attached to existing plans.
   Deepen linting and validation-impact simulation so approval and apply decisions are backed by better operator evidence, explanations, and operator workflow hooks.
3. Mature governance around the safer plan objects.
   Add rollback, multi-stage approval, and broader provider write adapters after the analysis surfaces are in place.
4. Expand the same proven workflow shape to ASPA.
   Reuse provider sync, reconciliation, planning, approval, and reporting patterns rather than creating a second control plane.
5. Deepen service-context binding and bulk authoring.
   Once the safety loop is real, make policy generation and maintenance more ergonomic at scale.
6. Add external evidence and coordination layers.
   Validation overlays, IRR consistency, and publication observations should enrich an already coherent operator workflow, not compensate for a missing one.
7. Finish provider-scale and downstream operating models.
   On-behalf-of authorization and broader provider/object coverage should close the remaining gap between enterprise use and provider use.

---

## 6. Architecture constraints for closing the gap

### 6.1 Extend the existing workflow instead of creating parallel ones

The current ROA workflow already spans intent, reconciliation, sync, planning, approval, apply, and audit. Future work should extend that pipeline instead of creating side channels for ASPA, provider reporting, or governance.

### 6.2 Keep source, derived, workflow, and observation layers separate

Keep a clean distinction between:
- source objects such as ROAs, certificates, ASPAs, and provider accounts
- derived objects such as intent rows, lint results, reconciliation results, and simulations
- workflow objects such as plans, approvals, sync runs, and rollback bundles
- observation objects such as provider snapshots, validator results, and publication-health evidence

This keeps the schema extensible and avoids turning operational state into a pile of flags on core objects.

### 6.3 Keep the provider abstraction narrow and explicit

Provider adapters should continue to expose explicit capability and operation contracts such as read state, diff state, preview change, and apply change. Provider-specific behavior belongs in adapters, not in the shared plan or governance model.

### 6.4 Define backlog closure by end-to-end behavior

A backlog item is not closed because a model exists. It is closed when the data model, service layer, operator surface, migration story, and regression coverage all exist together.

---

## 7. Gap closure criteria

When deciding whether a gap is actually closed, use the same standard for every backlog item.

- The schema or registry contract exists and is migration-safe.
- The service layer performs the actual work rather than leaving the feature as passive inventory.
- Operators can reach it through an intentional UI, API, command, or job surface as appropriate.
- The result is explainable in operator terms and fits the existing audit model.
- Focused regression tests exist, and the full plugin suite remains green.

---

## 8. Scope guardrails

The plugin should stay focused on operator workflow and correctness rather than absorbing adjacent systems wholesale.

- Do not turn the plugin into a full certificate authority implementation.
- Do not treat a full relying-party validator as a prerequisite for useful operator workflows.
- Do not expand write-back automation provider by provider until the shared diff, planning, and governance surfaces are stable.
- Do not let BGP telemetry or IRR coordination substitute for a missing core intent and reconciliation loop.
- Do not represent every RFC corner case ahead of the control-plane features operators need day to day.

---

## 9. Missing standards-based RPKI architecture elements to add to the data model

The strategic backlog above is about closing the operator-workflow gap. The sections below capture a second, related gap: the remaining architectural distance between the current plugin and a fuller standards-aligned RPKI object model. Some additive schema work is already present in the codebase, but these areas are not yet uniformly integrated into the active operator workflow, provider surfaces, or reporting layers.

### 9.1 Certificate Revocation Lists (CRLs)
**Defining reference:** RFC 6481, Section 2; RFC 6487; RFC 8897, Section 3.

CRLs are not optional wallpaper in the RPKI repository model. A certificate-centric plugin that omits CRLs can say that a certificate exists, but it cannot faithfully represent whether that certificate remains trustworthy or has been revoked. Adding CRL support should shift the model from standalone certificate facts toward revocable repository artifacts with freshness, issuance lineage, CRL number semantics, next-update expectations, and consistency relationships to publication points and manifests.

### 9.2 Manifests
**Defining reference:** RFC 6486; RFC 6481, Section 2; RFC 8897, Section 4.

A manifest is the repository’s table of contents with teeth. RFC 6486 defines the manifest signed object used to enumerate the objects expected at a CA publication point, along with hashes, so relying parties can detect missing, stale, substituted, or otherwise inconsistent repository contents. Without a manifest model, the plugin has no way to describe repository completeness or to answer whether the set of published ROAs and certificates is coherent as a published unit. Including manifests should therefore push the schema away from isolated object rows and toward publication-set semantics. In practice, that means adding a `Manifest` signed-object model, a `ManifestEntry` child table for filename and hash members, and explicit relationships from manifests to publication points, EE certificates, CRLs, and signed objects. It also means existing ROA and certificate models should stop assuming publication is implicit and instead carry references to the manifest and publication point that currently attest to their presence.

### 9.3 End-entity (EE) certificates for signed objects
**Defining reference:** RFC 6487; RFC 6488; RFC 9582 for ROAs.

ROAs and other RPKI signed objects are not signed directly by the long-lived resource certificate in the casual way a business application might imagine. The standards structure uses end-entity certificates to sign individual CMS-protected signed objects, and those EE certificates have their own profile constraints and validation significance. The plugin description hints at this relationship in prose, but it does not expose EE certificates as first-class data. That omission flattens an important layer of the architecture and makes it hard to express lifecycle, revocation, and signing relationships correctly. Adding EE certificates should spur a deliberate split between resource-holding CA certificates and object-signing EE certificates. The existing `Resource Certificate` model should remain the CA-layer object, while new signed-object records such as ROAs, manifests, ASPAs, RSCs, and Trust Anchor Keys should link to a dedicated `EndEntityCertificate` model carrying SKI/AKI, serial, validity, inherited-vs-enumerated resource constraints where applicable, issuer reference, and revocation linkage. This change would cleanly separate “certificate that delegates authority” from “certificate that signed this object instance.”

### 9.4 Repository publication points and retrieval topology
**Defining reference:** RFC 6480; RFC 6481; RFC 8182.

The standards architecture is emphatically not just a bag of signed objects. RFC 6480 and RFC 6481 define a distributed repository system with publication points, while RFC 8182 defines RRDP as a scaling-oriented retrieval protocol for repository content. If the plugin does not model publication points, object URIs, repository endpoints, or retrieval metadata, it cannot represent where authoritative objects live, how they are grouped, or how relying parties are expected to fetch them. For hosted-RPKI consumers this still matters, because hosted service does not erase publication mechanics; it merely outsources them. Adding this layer should push the plugin from a pure policy/inventory model toward a repository-aware one. The data model should gain entities such as `Repository`, `PublicationPoint`, `PublishedObjectLocation`, and optionally `RrdpSession`/`RrdpSnapshot` metadata. Existing certificate and ROA objects should then reference publication points and object URIs explicitly, rather than storing publication-related strings as loosely typed attributes on the certificate row.

### 9.5 Trust anchors, TALs, and trust-anchor rollover artifacts
**Defining reference:** RFC 6490; RFC 8630; RFC 9691.

The top of the RPKI tree is not just an abstract “signed by an RIR” notion. Trust anchors are distributed and consumed through specific artifacts and rollover procedures. RFC 6490 defines the Trust Anchor Locator (TAL), RFC 8630 updates the TAL format, and RFC 9691 defines the Trust Anchor Key signed object to support planned trust-anchor rollover without invalidating the tree. A data model that stops at resource certificates misses the root-of-trust mechanics that explain why and how a given certificate chain is grounded. Including this layer should spur two shifts. First, certificates should no longer carry only an `issuer` string but should be able to chain upward to an explicit `TrustAnchor` or parent CA object. Second, rollover should stop being an out-of-band concept and become modeled state. The plugin should add `TrustAnchor`, `TrustAnchorLocator`, and `TrustAnchorKey` entities, plus successor/predecessor relationships and publication metadata. That would let the schema represent not only today’s trust root but also staged rollover state and the repository locations that relying parties need to discover it.

### 9.6 Generic signed-object framework
**Defining reference:** RFC 6488; IANA RPKI Signed Objects registry.

The plugin today appears to privilege ROAs as a bespoke top-level object type. Standards-wise, that is too narrow. RFC 6488 defines the general signed-object template for the RPKI, and the IANA registry now enumerates multiple signed-object families including ROAs, manifests, RSCs, Trust Anchor Keys, and ASPAs. If the schema continues to model each one as a one-off special case, the plugin will accrue repetitive logic and structural inconsistency every time the standards family grows. Adding a generic signed-object abstraction should therefore cause a refactor of the existing ROA model, not merely the addition of new tables beside it. A parent `SignedObject` entity should capture content type, EE certificate, CMS/signature metadata, publication URI, filename, manifest membership, validation status, and parsed-vs-raw payload references. `ROA` would then become a typed child or extension record rather than the sole architectural pattern. That shift would make it much easier to add ASPA, Manifest, RSC, Ghostbusters, or future object types without re-laying the track each time.

### 9.7 Autonomous System Provider Authorizations (ASPAs)
**Defining reference:** IANA RPKI registries; draft-ietf-sidrops-aspa-profile (current SIDROPS working-group definition).

ASPA is the clearest standards-track object family absent from the current plugin and the one with the most immediate architectural relevance after ROAs. The current SIDROPS ASPA profile defines a CMS-protected object through which the holder of an AS authorizes one or more other ASes as transit providers, with the goal of improving route-leak detection and mitigation. For a cloud or other highly interconnected operator, ASPA models the commercial and topological reality of provider relationships in a way ROAs never can. Its inclusion should do more than add an `ASPA` table. It should prompt the plugin to elevate AS-relationship intent into the schema: customer ASN, authorized provider ASN set, validity intervals, publication metadata, and reconciliation against NetBox provider/circuit constructs. Existing ASN-related models should stop assuming ASNs matter only as ROA origins or certificate resources and start supporting provider-role semantics, planned-vs-published authorization state, and many-to-many provider relationship history.

### 9.8 RPKI Signed Checklists (RSCs)
**Defining reference:** RFC 9323.

RSCs extend the RPKI beyond routing origination and into attestation of arbitrary digital artifacts via resource-backed signatures. RFC 9323 defines them as signed checklists of hashes for one or more digital objects. Even if a hosted-RPKI consumer never deploys RSCs in the first implementation wave, they matter architecturally because they prove the plugin’s future should not be “ROAs plus a few odd extras,” but a common signed-object framework that can represent resource-backed attestations beyond route origination. Adding RSC support should therefore reinforce the refactor described above: a generic signed-object layer, a typed payload extension for checklist content, and manifest/publication relationships that parallel the rest of the repository model. It should also encourage the schema to support hash-set child tables and artifact references, which are different from prefix/ASN child rows and therefore useful pressure tests for whether the signed-object abstraction is truly general.

### 9.9 BGPsec Router Certificates
**Defining reference:** RFC 8209.

BGPsec router certificates sit at the edge of what many operators actually deploy today, but they are unquestionably part of the standards-based RPKI architecture. RFC 8209 defines the certificate profile used to validate Autonomous System path signatures in BGPsec. Their absence means the plugin currently models RPKI only as a route-origin authorization system and not as a broader routing-security PKI. Including router certificates should prompt a useful broadening of the certificate taxonomy. Instead of treating every certificate as a generic “resource certificate,” the data model should distinguish at least CA resource certificates, EE certificates for signed objects, and router certificates for BGPsec. This suggests introducing a certificate superclass or type discriminator, plus router-key-specific fields, ASN associations at the router-certificate layer, and links to device or logical-router inventory where appropriate. Even if implementation priority remains low, modeling the type cleanly would keep the schema aligned with the standards family rather than hard-coding today’s most common deployment pattern.

### 9.10 Relying-party and validated-payload view
**Defining reference:** RFC 8897; RFC 8210 / 8210bis family for cache-to-router exchange.

A publication-only model is still missing half the architecture that operators actually depend on in production: the relying-party view. RFC 8897 consolidates requirements for relying-party software, and the RPKI-to-router standards describe how validated payloads are exposed downstream to routers. The plugin does not need to become a full validator, but if it aims to represent the architecture rather than just object inventory, it should be able to model what a relying party believes about the published data. Including this element should shift the schema from “object exists” to “object validates, produces payloads, and has observable downstream effect.” That implies entities such as `ValidatorInstance`, `ValidationRun`, `ValidatedRoaPayload`, `ValidatedAspaPayload`, and `ObjectValidationResult`, along with timestamps, reason codes, local-policy outcomes, and optional router/cache export metadata. Existing ROA and certificate tables would then relate not only to authored objects but also to validation outcomes, which is where operational truth actually bites.

### 9.11 What this should change in the plugin’s core schema direction

Taken together, these missing elements argue for a broader schema refactor rather than a simple pile-on of new tables. The existing model is centered on three ideas: organization, resource certificate, and ROA. A more standards-aligned architecture would center on five layers instead:

1. **Authority layer:** trust anchors, parent/child CAs, resource certificates, router certificates.  
2. **Publication layer:** repositories, publication points, URIs, RRDP/rsync metadata.  
3. **Object layer:** generic signed objects plus typed payload extensions such as ROA, Manifest, ASPA, RSC, and Trust Anchor Key.  
4. **Integrity layer:** EE certificates, CRLs, manifest membership, revocation and freshness state.  
5. **Validation layer:** relying-party observations, validated payloads, and reconciliation results.

That five-layer shape would make the plugin much more faithful to the standards architecture and far more extensible for real operator workflows.

---

## 10. Final recommendation

The current plugin is already useful as a structured **RPKI object inventory extension** for NetBox. The highest-value evolution is to make it useful for the actual day job of a hosted-RPKI consumer:

- expressing routing-security intent
- checking that intent against published provider state
- identifying drift and unsafe policy
- scaling ROA/ASPA operations across a large prefix estate
- supporting safe, auditable change workflows

If only three follow-on features are implemented next, they should be:

1. **provider synchronization expansion and diff reporting**
2. **ROA linting and safety analysis**
3. **ROV simulation plus governance maturation**

Within provider synchronization itself, the next increment should be:

1. richer provider snapshot diff and reporting surfaces built on the new sync-health and due-sync metadata
2. expansion from ARIN and Krill ROA import to additional provider and object families
3. reuse of that broader provider substrate for ASPA and later non-Krill write workflows

Those three together would transform the plugin from a tidy cabinet of RPKI artifacts into something much closer to a routing-security control console.

---

## 11. Sources

1. TestPyPI project page for `netbox-rpki`, including current package description and documented models. citeturn301101view0
2. ARIN hosted RPKI overview and related ROA/ASPA management materials. citeturn910174search0turn910174search3turn910174search6turn910174search9turn910174search15turn910174search18
3. RIPE NCC hosted RPKI usage notes and API documentation. citeturn910174search1turn910174search4
4. RFC 9319 guidance on minimal ROAs and `maxLength`. citeturn910174search2turn910174search11
## Engineering specification addendum: proposed Django/NetBox model architecture, relationship sketch, and migration order

This section reframes the backlog as an implementation-oriented specification. The goal is not to freeze every field name up front, but to give a coding agent a durable schema direction that supports the existing plugin models while opening a clean path toward standards-aligned RPKI object modeling, hosted-provider synchronization, and operator-grade reconciliation workflows.

### 5.1 Design principles for the next schema revision

#### Preserve current object identity where possible
The plugin already has recognizable top-level entities for organizations, resource certificates, and ROAs. Those should remain as stable conceptual anchors where practical so that existing records, URLs, and automation clients do not break unnecessarily. The migration strategy should therefore prefer **progressive normalization** over destructive renaming in the first major revision.

#### Separate cryptographic object identity from operator intent
The current model leans toward representing what an operator wants to keep track of. The next model needs to represent both **published cryptographic objects** and **operator intent derived from NetBox**. Those are not the same thing. A single intended authorization may correspond to multiple published signed objects over time, and a published object may become stale relative to intent without becoming invalid in a cryptographic sense.

#### Model the signed-object family explicitly
ROAs should stop being treated as an isolated special case. The RPKI standards family includes multiple signed-object types, each with common publication and signing semantics. The data model should therefore gain a generic signed-object framework so that ROAs, ASPAs, manifests, RSCs, and future object types can share common metadata and lifecycle handling.

#### Keep provider synchronization orthogonal to core RPKI semantics
Hosted-provider connectors should map external APIs into the internal schema, not define the schema. The plugin should avoid becoming “an ARIN client with some RIPE conditionals stapled on.” Provider-specific fields should live in provider-account, external-reference, and snapshot models, while the core object graph remains standards- and operator-centric.

The same separation principle now also applies inside the plugin registry: internal model/registry identity and public UI/API naming are explicit, separate contracts. That split was necessary to keep generated NetBox actions correct when Django model names intentionally differ from public route slugs.

#### Prefer additive migrations in early phases
A coding agent should bias toward additive migrations, compatibility shims, and data backfills in the first implementation wave. That reduces the chance of breaking existing plugin users while still allowing a later cleanup pass once the richer model stabilizes.

---

### 5.2 Proposed model families

The following model family layout is a suggested target architecture.

### A. Administrative / ownership layer

#### `RPKIOrganization`
Successor or compatibility-preserving evolution of the current `Organization` model.

**Purpose**  
Represents the administrative entity consuming RPKI services or owning the internal policy domain.

**Suggested key fields**
- `slug`
- `name`
- `org_id`
- `description`
- `website_url`
- `parent_rir_asn` or renamed reference to current `parent_rir`
- `status`
- `comments`

**Relationship notes**
- one-to-many to provider accounts
- one-to-many to CA/resource certificates
- one-to-many to intent profiles and change requests

**Why this is a schema pivot**  
This object should stop being just a decorative top-level record and become the root administrative namespace for provider accounts, policy profiles, trust relationships, and approvals.

#### `ProviderAccount`
Represents a hosted-RPKI account or tenancy at ARIN, RIPE NCC, APNIC, or another provider.

**Suggested key fields**
- `organization` FK to `RPKIOrganization`
- `provider_type` enum such as `arin`, `ripe`, `apnic`, `other`
- `account_identifier`
- `display_name`
- `api_base_url`
- `credentials_reference`
- `sync_enabled`
- `last_successful_sync`
- `last_sync_status`

**Relationship notes**
- one-to-many to provider snapshots
- one-to-many to external object references
- optional one-to-many to managed downstream relationships

**Why it matters**  
This keeps provider API state out of the core certificate/ROA tables and allows one organization to span multiple RIRs or multiple accounts cleanly.

#### `ManagedAuthorizationRelationship`
Represents a provider-managed or on-behalf-of relationship for downstream resources.

**Suggested key fields**
- `provider_organization` FK
- `downstream_name`
- `downstream_identifier`
- `relationship_type`
- `starts_at`
- `ends_at`
- `is_active`
- `notes`

**Why it matters**  
This adds a place to model the real-world fact that providers often manage ROAs or policy workflows on behalf of customers without collapsing legal resource ownership, cryptographic authority, and operational responsibility into one muddy field.

---

### B. Resource authority / certificate hierarchy layer

#### `CertificateAuthorityNode`
A new model representing a node in the CA hierarchy, regardless of whether it is a trust anchor, intermediate CA, or customer/resource CA.

**Suggested key fields**
- `name`
- `organization` FK nullable
- `node_type` enum: `trust_anchor`, `rir_ca`, `member_ca`, `delegated_ca`, `hosted_service_ca`
- `subject`
- `issuer`
- `serial`
- `ski`
- `aki`
- `valid_from`
- `valid_to`
- `publication_uri`
- `ca_repository_uri`
- `rrdp_notify_uri`
- `is_self_hosted`
- `status`

**Relationship notes**
- self-referential parent FK for hierarchy
- one-to-many to resource certificates
- one-to-many to CRLs
- one-to-many to manifests

**Why this should reshape the existing model**  
The current `Resource Certificate` object appears to combine CA-ish hierarchy semantics with operator bookkeeping. Introducing `CertificateAuthorityNode` gives the model a proper hierarchy backbone. Existing resource-certificate records can initially map one-to-one into CA nodes plus resource certificates, then gradually decouple if needed.

#### `ResourceCertificate`
A refined successor to the current `Resource Certificate` model, focused on the actual resource-bearing certificate rather than every possible CA concern.

**Suggested key fields**
- `ca_node` FK to `CertificateAuthorityNode`
- `organization` FK
- `name`
- `serial`
- `subject`
- `issuer`
- `public_key`
- `private_key_reference` rather than raw private key if possible
- `valid_from`
- `valid_to`
- `auto_renews`
- `publication_url`
- `status`
- `source_of_truth` enum: `manual`, `provider_sync`, `derived`, `imported`

**Relationship notes**
- many-to-many through tables to prefixes and ASNs
- one-to-many to EE certificates
- one-to-many to signed objects via EE certs or direct resource relationship

**Why this should change the existing model**  
The existing model likely stores too much directly and too little structurally. Splitting CA-node hierarchy from the resource certificate proper allows certificate lineage, publication, and delegation relationships to be represented cleanly.

#### `CertificateResourcePrefix`
Through model linking a `ResourceCertificate` to a NetBox prefix or abstract prefix range.

**Suggested key fields**
- `resource_certificate` FK
- `prefix` FK to NetBox `Prefix` when resolvable
- `prefix_cidr_text` fallback for out-of-band imported values
- `max_length_authorized` nullable
- `source`

#### `CertificateResourceASN`
Through model linking a `ResourceCertificate` to an ASN.

**Suggested key fields**
- `resource_certificate` FK
- `asn` FK to NetBox ASN or integer surrogate field
- `source`

**Why these should evolve the current hidden tables**  
The plugin already has certificate-prefix and certificate-ASN relationship objects. These should be promoted from hidden support tables into deliberate, queryable resource-entitlement models because later reconciliation, publication, and validation logic will depend on them heavily.

---

### C. Signed-object framework layer

#### `SignedObject`
A new generic superclass or concrete base model for all RPKI signed objects.

**Suggested key fields**
- `object_type` enum: `roa`, `aspa`, `manifest`, `crl`, `rsc`, `ghostbusters`, `bgpsec_router_cert`, `tak`, `other`
- `name`
- `display_label`
- `organization` FK
- `resource_certificate` FK nullable
- `ee_certificate` FK nullable
- `publication_point` FK nullable
- `filename`
- `object_uri`
- `repository_uri`
- `content_hash`
- `serial_or_version`
- `valid_from`
- `valid_to`
- `publication_status`
- `origin_source` enum: `manual`, `provider_sync`, `computed`, `validator_ingest`
- `external_reference` optional FK
- `raw_payload_reference`

**Relationship notes**
- one-to-one from concrete object models such as `ROA`, `ASPA`, `Manifest`
- one-to-many to validation observations and reconciliation artifacts

**Why this changes the data model materially**  
This is the hinge point for future-proofing. Once this exists, ROAs stop being a one-off special entity and become one signed-object species among several. That will simplify publication tracking, history, imports, and external references across all object types.

#### `EndEntityCertificate`
Represents the EE certificate associated with a signed object.

**Suggested key fields**
- `resource_certificate` FK to parent resource certificate
- `subject`
- `issuer`
- `serial`
- `ski`
- `aki`
- `valid_from`
- `valid_to`
- `public_key`
- `status`

**Relationship notes**
- one-to-one or one-to-many to `SignedObject` depending on parsing/import model

**Why it matters**  
This closes a structural gap between “resource certificate exists” and “ROA exists.” It gives the model a place to represent the actual signing identity used by each signed object and supports future validation/debug workflows.

#### `PublicationPoint`
Represents a repository publication point or retrieval locus.

**Suggested key fields**
- `name`
- `organization` FK nullable
- `provider_account` FK nullable
- `publication_uri`
- `rsync_base_uri`
- `rrdp_notify_uri`
- `repository_type`
- `status`
- `last_observed_at`

**Relationship notes**
- one-to-many to signed objects
- one-to-many to manifests and CRLs

**Why it matters**  
The current model has publication-related fields on certificates, but publication is a first-class architectural concept and should not remain smeared across unrelated objects.

#### `Manifest`
Concrete signed-object subtype.

**Suggested key fields**
- `signed_object_ptr` one-to-one to `SignedObject`
- `manifest_number`
- `this_update`
- `next_update`

#### `ManifestEntry`
Files enumerated by a manifest.

**Suggested key fields**
- `manifest` FK
- `filename`
- `hash_algorithm`
- `file_hash`
- `object_type_guess`
- `linked_signed_object` nullable FK

**Why these matter**  
Adding manifests should spur movement away from thinking of repository state as “whatever rows happen to exist in our ROA table” and toward explicit modeling of publication completeness and object membership.

#### `CertificateRevocationList`
Concrete signed-object subtype for CRLs.

**Suggested key fields**
- `signed_object_ptr` one-to-one to `SignedObject`
- `crl_number`
- `this_update`
- `next_update`
- `issuer`

#### `RevokedCertificateEntry`
Represents a serial revoked by a CRL.

**Suggested key fields**
- `crl` FK
- `revoked_serial`
- `revocation_date`
- `reason_code`
- `linked_resource_certificate` nullable FK
- `linked_ee_certificate` nullable FK

**Why these matter**  
CRLs should force the plugin to stop treating certificate rows as implicitly valid until `valid_to`. Revocation creates a parallel lifecycle dimension that should be queryable and visible.

---

### D. Routing authorization layer

#### `ROA`
Refactor the current ROA model into a concrete subtype hanging from `SignedObject`.

**Suggested key fields**
- `signed_object_ptr` one-to-one to `SignedObject`
- `origin_asn` FK or integer field supporting ASN 0 policy representation via explicit handling
- `signed_by_resource_certificate` FK retained for convenience if helpful
- `is_as0`
- `remarks`

**Relationship notes**
- one-to-many to `ROAPrefixAuthorization`
- many-to-one to intent and reconciliation objects

**Why this should alter the current model**  
The current model likely stores validity and signing information directly on the ROA row. That can remain for compatibility during migration, but the durable shape is for publication/lifecycle/signature metadata to move to `SignedObject`, leaving ROA-specific semantics on the ROA subtype.

#### `ROAPrefixAuthorization`
Successor to the current ROA prefix relationship model.

**Suggested key fields**
- `roa` FK
- `prefix` FK to NetBox `Prefix` nullable
- `prefix_cidr_text`
- `max_length`
- `address_family`

#### `ROAIntent`
Represents a desired authorization derived from NetBox intent.

**Suggested key fields**
- `organization` FK
- `prefix` FK to NetBox Prefix
- `origin_asn` FK or integer
- `max_length`
- `intent_profile` FK
- `scope_site` nullable FK
- `scope_region` nullable FK
- `scope_tenant` nullable FK
- `scope_vrf` nullable FK
- `is_active`
- `derived_from_rule`

#### `ROAReconciliationResult`
Stores comparison outcomes between intended and published state.

**Suggested key fields**
- `roa_intent` FK
- `matched_roa` nullable FK
- `result_type` enum: `match`, `missing`, `asn_mismatch`, `prefix_mismatch`, `max_length_risky`, `orphaned`, `stale`
- `severity`
- `details_json`
- `computed_at`

**Why these should reshape the schema**  
Introducing explicit intent rows means the plugin can stop overloading the ROA table with both “what exists” and “what we wish existed.” That separation is essential for sane reconciliation logic.

---

### E. ASPA / provider-authorization layer

#### `ASPA`
Concrete signed-object subtype.

**Suggested key fields**
- `signed_object_ptr` one-to-one to `SignedObject`
- `customer_asn`
- `remarks`

#### `ASPAProviderAuthorization`
Represents each provider ASN authorized by the ASPA.

**Suggested key fields**
- `aspa` FK
- `provider_asn`
- `provider_name` optional denormalized field
- `sequence_index` optional

#### `ASPAIntent`
Derived or operator-authored desired provider authorization set.

**Suggested key fields**
- `organization` FK
- `customer_asn`
- `provider_asn`
- `provider_account` nullable FK
- `circuit` nullable FK if NetBox circuits binding is added
- `intent_profile` FK
- `is_active`

#### `ASPAReconciliationResult`
Comparison of intended vs published provider relationships.

**Why these matter**  
ASPA support should not be bolted onto ROA tables as an ASN-to-ASN side table. It deserves a first-class family because its semantics are relationship-set based, not prefix-authorization based.

---

### F. Validation / observation / external evidence layer

#### `ProviderSnapshot`
Stores a sync-time snapshot envelope from a hosted provider.

**Suggested key fields**
- `provider_account` FK
- `snapshot_type`
- `fetched_at`
- `source_etag`
- `source_version`
- `status`
- `raw_response_reference`

#### `ExternalObjectReference`
Maps internal objects to provider-side or imported identifiers.

**Suggested key fields**
- `provider_account` FK
- `external_id`
- `external_type`
- `internal_content_type`
- `internal_object_id`
- `last_seen_at`

#### `VRPSnapshot`
Represents validated ROA payload snapshots ingested from a validator or external pipeline.

**Suggested key fields**
- `snapshot_label`
- `source_system`
- `fetched_at`
- `status`

#### `ValidatedPayload`
Represents an individual validated prefix-origin tuple.

**Suggested key fields**
- `vrp_snapshot` FK
- `prefix_cidr_text`
- `origin_asn`
- `max_length`
- `source_signed_object` nullable FK

#### `ValidationObservation`
Observed validation state for a route, prefix, or object.

**Suggested key fields**
- `observed_prefix` FK or text
- `observed_origin_asn`
- `validation_state` enum: `valid`, `invalid`, `not_found`
- `reason_code`
- `evidence_source`
- `observed_at`
- `linked_roa` nullable FK
- `linked_signed_object` nullable FK

**Why these should reshape the existing model**  
Once observed and validated state exists, the current object tables can stop pretending that local inventory is the full truth. The plugin becomes capable of showing intended, published, and validated realities side by side.

---

### G. Workflow / planning / audit layer

#### `IntentProfile`
Policy profile used to derive ROA or ASPA intent.

**Suggested key fields**
- `name`
- `organization` FK
- `profile_type` enum
- `rule_expression` or reference
- `is_default`
- `notes`

#### `ChangePlan`
A generic umbrella for proposed modifications to published RPKI state.

**Suggested key fields**
- `organization` FK
- `provider_account` nullable FK
- `plan_type` enum: `roa`, `aspa`, `mixed`
- `status` enum: `draft`, `proposed`, `approved`, `rejected`, `published`, `rolled_back`
- `created_by`
- `submitted_at`
- `approved_at`
- `ticket_reference`
- `maintenance_window`
- `summary`

#### `ChangePlanItem`
Individual create/update/delete actions inside a plan.

**Suggested key fields**
- `change_plan` FK
- `action_type`
- `target_object_type`
- `target_object_id`
- `before_state_json`
- `after_state_json`
- `impact_summary`

#### `ApprovalRecord`
Review / approval evidence.

#### `LintResult`
Reusable linting table applicable to ROAs, ASPAs, or future objects.

#### `SimulationResult`
Stores dry-run ROV outcome estimates.

**Why this matters**  
These workflow tables prevent the core object tables from turning into a swamp of status flags and partial publication metadata. Plans, linting, and approvals deserve their own layer.

---

### 5.3 Suggested foreign-key sketch

Below is the core relationship shape in prose.

- `RPKIOrganization` owns many `ProviderAccount`, `CertificateAuthorityNode`, `ResourceCertificate`, `IntentProfile`, and `ChangePlan` rows.
- `CertificateAuthorityNode` forms a parent/child tree and owns many `ResourceCertificate`, `Manifest`, and `CertificateRevocationList` rows.
- `ResourceCertificate` owns many `CertificateResourcePrefix`, `CertificateResourceASN`, and `EndEntityCertificate` rows.
- `EndEntityCertificate` signs one or more `SignedObject` rows.
- `SignedObject` is the generic parent of `ROA`, `ASPA`, `Manifest`, `CertificateRevocationList`, `RSC`, and later object types.
- `PublicationPoint` owns many `SignedObject` rows and is optionally linked to `ProviderAccount`.
- `ROA` owns many `ROAPrefixAuthorization` rows.
- `ASPA` owns many `ASPAProviderAuthorization` rows.
- `ROAIntent` and `ASPAIntent` derive from NetBox state and are compared to published `ROA` and `ASPA` rows via reconciliation tables.
- `ProviderSnapshot` and `ExternalObjectReference` connect hosted-provider APIs to internal objects without polluting the core object model.
- `VRPSnapshot`, `ValidatedPayload`, and `ValidationObservation` represent validator or telemetry evidence.
- `ChangePlan`, `ChangePlanItem`, `LintResult`, and `SimulationResult` capture human workflow and pre-publication analysis.

---

### 5.4 Migration order

A coding agent should not attempt to build every table in one dramatic schema meteor strike. The safer path is phased.

#### Phase 1: Normalize the current core without breaking existing records

**Objective**  
Preserve the current `Organization`, `Resource Certificate`, and `ROA` functionality while introducing compatibility-friendly successor structures.

**Recommended migrations**
1. Add `RPKIOrganization` as either a rename target or compatibility alias of the current `Organization` table.
2. Add `ProviderAccount`.
3. Add `CertificateAuthorityNode`.
4. Extend `ResourceCertificate` with explicit linkage to `CertificateAuthorityNode` and add `source_of_truth` metadata.
5. Promote certificate-prefix and certificate-ASN support tables into explicitly modeled resources if they are not already first-class ORM models.
6. Add `PublicationPoint`.

**Backfill steps**
- create a `CertificateAuthorityNode` row for each existing resource certificate if no better CA hierarchy data exists yet
- backfill publication URI fields from current certificate attributes
- map current organization rows to the new naming/namespace scheme

**Compatibility rule**  
Do not yet refactor the current ROA table into a subtype if that would break forms or API consumers immediately.

#### Phase 2: Introduce signed-object generalization

**Objective**  
Create a common base for ROAs and future signed objects.

**Recommended migrations**
1. Add `SignedObject`.
2. Add `EndEntityCertificate`.
3. Add nullable one-to-one from existing `ROA` rows to `SignedObject`.
4. Migrate validity, publication, and external-reference style metadata from ROA into `SignedObject` where possible.
5. Add `ROAPrefixAuthorization` as the explicit successor to any hidden ROA prefix table.

**Backfill steps**
- create one `SignedObject` per existing ROA
- create placeholder `EndEntityCertificate` rows only if the source data supports it; otherwise allow null and mark as unknown

**Compatibility rule**  
Keep old ROA fields readable during this phase even if the canonical values begin moving to the signed-object layer.

#### Phase 3: Add standards-missing architectural objects

**Objective**  
Close the largest gaps against the broader RPKI architecture.

**Recommended migrations**
1. Add `Manifest` and `ManifestEntry`.
2. Add `CertificateRevocationList` and `RevokedCertificateEntry`.
3. Add trust-anchor-related modeling if implemented as `CertificateAuthorityNode(node_type='trust_anchor')` plus optional TAL artifact table.
4. Add `RSC` and other signed-object subclasses only after the generic base is stable.

**Backfill steps**
- no speculative backfill for manifests/CRLs if data is unavailable
- allow import-only population first

#### Phase 4: Add operator intent and reconciliation

**Objective**  
Make the plugin useful as an operational policy layer, not just a repository of imported objects.

**Implementation status:** Largely completed for the first operational slice. The Priority 1 operator-intent layer is present under the names `RoutingIntentProfile`, `RoutingIntentRule`, `ROAIntentOverride`, `IntentDerivationRun`, `ROAIntent`, `ROAIntentMatch`, `ROAReconciliationRun`, `ROAIntentResult`, and `PublishedROAResult`; execution is implemented through a service layer, NetBox job runner, management command, and API trigger; provider-backed comparison is implemented against normalized imported snapshot rows; custom detail UX exists for dashboard/drill-down/diff flows; and draft ROA change plans can now be created from completed reconciliation runs. ASPA now also has a first operational intent/reconciliation slice under `ASPAIntent`, `ASPAIntentMatch`, `ASPAReconciliationRun`, `ASPAIntentResult`, and `PublishedASPAResult`, with organization-scoped execution, imported-provider comparison, and drill-down/operator surfaces. Richer approvals/write-back, linting, simulation, and broader provider coverage remain future work.

**Recommended migrations**
1. Add `IntentProfile`.
2. Add `ROAIntent` and `ROAReconciliationResult`.
3. Add `ASPA`, `ASPAProviderAuthorization`, `ASPAIntent`, and `ASPAReconciliationResult`.
4. Add `LintResult` and `SimulationResult`.

**Backfill steps**
- derive initial ROA intent from selected NetBox prefixes, ASNs, tags, and policy defaults
- leave ASPA intent empty until provider/upstream relationships are modeled or imported

#### Phase 5: Add provider sync and validation evidence

**Objective**  
Bind the schema to real hosted-provider state and validator observations.

**Implementation status:** Partially completed with live ARIN ROA import, Krill ROA import/write paths, and Krill ASPA import. `RpkiProviderAccount`, `ProviderSyncRun`, `ProviderSnapshot`, `ExternalObjectReference`, `ImportedRoaAuthorization`, `ImportedAspa`, and `ProviderWriteExecution` now support normalized provider snapshots, stable provider-object identity tracking, operator-triggered sync from UI/API/command/job surfaces, interval-based due-sync orchestration, computed sync-health visibility, a read-only operations dashboard, auditable Krill change-plan preview/apply flows for ROAs, and imported ASPA normalization for provider-backed reconciliation. Validator evidence, richer provider-reporting surfaces, broader provider/object coverage, and ASPA write-back remain to be built.

**Recommended migrations**
1. Add `ProviderSnapshot` and `ExternalObjectReference`.
2. Add `VRPSnapshot`, `ValidatedPayload`, and `ValidationObservation`.
3. Add sync-job and health-check tracking models if implemented separately.

#### Phase 6: Add workflow and approval semantics

**Objective**  
Support safe publication pipelines and operator governance.

**Implementation status:** Partially completed through the first provider-backed execution slice. `ROAChangePlan`, `ROAChangePlanItem`, and `ApprovalRecord` exist, can be generated or populated from reconciliation and approval results, and now support preview/approve/apply state transitions plus `ProviderWriteExecution` audit history, ticket/change references, and maintenance-window semantics for Krill-backed writes; rollback, multi-stage approvals, and broader governance workflows are still pending.

**Recommended migrations**
1. Add `ChangePlan`, `ChangePlanItem`, and `ApprovalRecord`.
2. Add rollback and publication-state support if distinct from plan status.
3. Integrate with NetBox permissions and object-level change logging.

---

### 5.5 Compatibility and deprecation guidance

#### Existing `Resource Certificate` model
Keep it, but progressively refocus it on actual resource-bearing certificate semantics. Fields that really describe repository structure or provider integration should migrate outward into `CertificateAuthorityNode`, `PublicationPoint`, and `ExternalObjectReference`.

#### Existing `ROA` model
Keep it as a stable user-facing concept, but make it a concrete subtype hanging from `SignedObject`. Over time, fields like validity and publication URI should become inherited or delegated from the signed-object layer.

#### Existing hidden relation tables
The current hidden ROA/certificate prefix/ASN support tables should be promoted into explicit first-class ORM models with clear API exposure, because later reconciliation logic will depend on them as more than mere implementation details.

#### Private key storage
The existing package description includes a `private_key` field on resource certificates. A coding agent should treat that as a design smell for hosted-RPKI-oriented deployments. The schema should move toward `private_key_reference`, secret-store integration, or explicit nullability where keys are provider-managed and never locally present.

---

### 5.6 Suggested implementation sequence for a coding agent

If the coding agent needs an opinionated order of attack, use this one:

1. stabilize current models and add tests around existing CRUD behavior
2. add `ProviderAccount`, `CertificateAuthorityNode`, and `PublicationPoint`
3. promote prefix/ASN relation tables into explicit resource-entitlement models
4. add `SignedObject` and connect existing ROAs to it
5. add `EndEntityCertificate`
6. add `ROAIntent` and read-only reconciliation views
  Status: completed for the initial ROA intent/reconciliation data-model layer, generated surfaces, derivation/reconciliation execution service, NetBox job runner, management command, API trigger, provider-backed comparison schema, custom detail UX, and draft change-plan generation
7. add hosted-provider import and external object references
  Status: partially completed. The repo now has `RpkiProviderAccount`, `ProviderSyncRun`, `ProviderSnapshot`, `ImportedRoaAuthorization`, `ExternalObjectReference`, real ARIN and Krill ROA import connectors with command/job/API execution, interval-based due-sync orchestration, provider sync-health visibility, and an initial operations dashboard; provider-account CRUD is operational after the generated-action routing fix; broader multi-provider/object coverage and richer provider diff/reporting are still pending
8. add `ASPA` object family
  Status: largely completed for the first operational slice. The repo now has `ASPA`, constrained ASPA provider-authorization rows, `ImportedAspa`, `ImportedAspaProvider`, `ASPAIntent`, `ASPAIntentMatch`, `ASPAReconciliationRun`, `ASPAIntentResult`, and `PublishedASPAResult`, along with Krill ASPA import, organization-scoped reconciliation execution via service/job/command/API/UI surfaces, and ASPA detail/drill-down views; provider-backed ASPA write-back, linting, simulation, and broader provider support remain pending
9. add manifests and CRLs
10. add linting, simulation, and change-plan workflows
  Status: partially completed. ROA-specific draft change plans exist, along with approval persistence and governed Krill write-through, but linting, simulation, rollback, and generalized workflow state do not
11. add validator/VRP observation support
12. clean up deprecated fields only after at least one stable release with compatibility shims

---

### 5.7 NetBox integration notes

#### Prefer NetBox-native references where semantically correct
Use NetBox `Prefix`, `ASN`, `Tenant`, `VRF`, `Site`, `Region`, `Provider`, and `Circuit` references where those objects express operator intent directly. Avoid duplicating those domains inside the plugin unless external imported values cannot be mapped cleanly.

#### Use denormalized text fallback fields for imported-but-unmapped values
Hosted-provider imports and validator evidence will sometimes refer to objects not yet present in NetBox. For those cases, dual-field patterns such as `prefix` FK plus `prefix_cidr_text` fallback are preferable to forcing lossy imports.

#### Be careful with generic foreign keys
Generic relations may be tempting for “bind anything to anything” policy scope, but they make API and query ergonomics worse. Prefer explicit FK scope fields for the first wave: `tenant`, `vrf`, `site`, `region`, and perhaps `provider`.

---

### 5.8 Testing expectations

A coding agent implementing this design should build test coverage in the following layers:

- migration/backfill tests for existing data
- model validation tests for ROA, ASPA, CRL, and manifest relationships
- reconciliation tests comparing intent vs published state
- provider import mapping tests with mocked ARIN/RIPE payloads
- API surface-contract tests proving each registered object exposes only the list/detail/custom methods its spec allows
- permission tests for approval and change-plan workflows
- registry-wide UI surface-contract tests proving every generated list/detail page and row-action set matches the object's supported Add/Edit/Delete affordances
- workflow-surface parity tests proving each custom operator action is either intentionally exposed in both API and web UI or explicitly documented as API-only, and proving that API summary roll-ups appear in the intended dashboard or list-page reporting surfaces
- the dedicated release gate in `devrun/work_in_progress/netbox_rpki_surface_contract_checklist.md` should be updated and satisfied for any registry or generated-surface refactor

---

### 5.9 Final architectural recommendation

The most important structural shift is this: stop treating the plugin as “a few forms for ROAs and certificates” and start treating it as a layered model with distinct domains for:

1. administrative ownership and provider accounts
2. certificate/resource authority hierarchy
3. generic signed objects and repository publication
4. routing authorization semantics such as ROAs and ASPAs
5. operator intent and reconciliation
6. external validation evidence
7. workflow, change control, and approvals

Once that separation exists, the plugin can grow in a controlled way instead of accreting special-purpose fields onto the current ROA and certificate tables like barnacles on a tugboat.
