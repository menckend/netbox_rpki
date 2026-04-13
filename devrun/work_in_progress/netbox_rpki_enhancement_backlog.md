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
- Current-state implementation: the foundational Krill-only expansion is now materially implemented. The codebase has a family-oriented sync contract with explicit `family_kind` and `evidence_source` metadata, a provider-specific Krill adapter module, durable external object identity, persisted snapshot diff artifacts, and read-only registry surfaces for the expanded imported families. ARIN ROA import remains functional as a compatibility path. Krill now imports ROA authorizations, ASPAs, CA metadata, parent links, child links, resource entitlements, publication points, signed-object inventory, and repository-derived certificate observations; those records feed `ProviderSnapshot`, `ProviderSnapshotDiff`, and `ProviderSnapshotDiffItem` reporting through UI, REST, and GraphQL surfaces.
- Gap to close: Priority 2 is no longer a speculative architecture item, but it is not fully closed against the end-state objective. The remaining gap is now concentrated in broader provider coverage, richer family-specific reporting and dashboard roll-ups, deeper publication-observation fidelity for certificate and signed-object inventory, and fuller operator-facing explanation of churn and freshness at the provider-account level.
- Preferred closure order: keep Priority 2 second, but treat it as a maturity and completion track rather than as a foundational greenfield build. The next work here should deepen reporting and provider breadth before adding more adjacent automation.

#### Status update against section 7 closure criteria

Against the closure standard in section 7, Priority 2 is now substantially farther along than this backlog previously described.

- The schema or registry contract exists and is migration-safe.
  The provider-sync data model now includes durable provider and snapshot envelopes, external identity rows, retained diff artifacts, and explicit imported-family models for the delivered Krill slice. The registry-driven UI, API, filter, table, navigation, and GraphQL surfaces are wired for the new read-only reporting families, including the supporting `ExternalObjectReference` surface needed by imported-object detail pages.
- The service layer performs the actual work.
  This is no longer passive inventory. The service layer fetches and imports live or fixture-backed provider state, normalizes provider identities, binds imported rows to durable external references, builds stable per-family summaries, and persists snapshot comparison artifacts rather than leaving comparison as ad hoc view logic.
- Operators can reach it through intentional UI, API, command, and job surfaces.
  Provider-account sync remains available through UI, API, command, and scheduled job paths. Provider snapshots, snapshot diffs, diff items, and imported-family detail pages are routed and queryable. REST and GraphQL reporting surfaces now expose summary JSON, latest diff lookup, retained comparison data, and imported publication-observation children alongside the existing provider objects.
- The result is explainable in operator terms and fits the existing audit model.
  Snapshot and diff objects now provide a shared explanation source for what changed between retained provider states, and imported-family detail pages render as intentional reporting surfaces instead of raw storage. This is still thinner than the full end-state reporting vision: provider-account roll-ups, dashboard warning depth, and some family-specific delta views remain incomplete.
- Focused regression tests exist, and the full plugin suite is green.
  The provider-sync contract, importer behavior, diff persistence, reporting surfaces, and linked imported-object detail pages now have focused regression coverage. The full plugin suite is currently green at 333 tests.

#### Delivered Krill-only slice

The current delivered slice now includes all of the following:

- explicit family-oriented provider-sync summaries with control-plane versus publication-observation metadata
- retained `ProviderSnapshotDiff` and `ProviderSnapshotDiffItem` artifacts used by reporting surfaces
- durable `ExternalObjectReference` binding across imported families
- Krill-backed imported-family persistence for:
  - ROA authorizations
  - ASPAs
  - CA metadata
  - parent links
  - child links
  - resource entitlements
  - publication points
  - signed-object inventory
  - repository-derived certificate observations
- repository-observation parsing in the Krill adapter for published signed objects and certificate-bearing evidence
- provider snapshot reporting through detail pages, REST serializers, compare actions, and GraphQL reporting fields
- regression coverage that now exercises populated imported-object relation links, preventing false-green UI detail tests

#### Remaining work before Priority 2 can reasonably be called closed

Priority 2 should still be treated as open because the delivered slice does not yet satisfy the full end-state objective for hosted-provider synchronization.

The highest-value remaining items are:

1. Broaden provider support beyond the current ARIN-ROA compatibility path and the Krill-focused implementation.
2. Deepen provider-account and operations-dashboard reporting so family churn, repeated import failures, publication freshness, and large-change warnings are visible without drilling into raw snapshot detail.
3. Improve certificate and signed-object observation fidelity so the publication-observation families are less dependent on limited derived evidence and move closer to full repository-backed inventory.
4. Expand family-specific diff presentation for certificate, publication-point, parent-link, and child-link changes so operators can answer what changed without reading raw JSON payloads.
5. Keep docs and test guidance aligned with the actual shipped provider-sync contract as the slice matures.

#### Recommended next execution slices

The next practical execution order for Priority 2 is now:

1. provider-account roll-up and operations-dashboard reporting depth
2. richer family-specific diff and freshness views for the already-imported Krill families
3. deeper publication-observation parsing and evidence handling for certificate and signed-object inventory
4. broader provider coverage once the shared reporting and evidence model is stable

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

## 9. Standards-based RPKI architecture elements in the data model: implemented vs. not yet implemented

The strategic backlog above is about closing the operator-workflow gap. The sections below now reflect the current codebase more precisely. Per `CONTRIBUTING.md`, the explicit Django model layer is the source of truth for whether something is implemented in the data model, while UI/API/GraphQL surfaces and operator workflows are separate concerns. Read the status markers below narrowly: they describe the data model as it exists today, not whether each area is already complete in provider sync, operator workflow, or reporting.

### 9.1 Certificate Revocation Lists (CRLs)
**Defining reference:** RFC 6481, Section 2; RFC 6487; RFC 8897, Section 3.

**Data-model status:** Implemented already.

The current explicit model layer already includes `CertificateRevocationList` and `RevokedCertificate`. Those models capture issuing-certificate linkage, publication-point linkage, manifest linkage, CRL number, update windows, retrieval and validation state, and per-certificate revocation records for both `Certificate` and `EndEntityCertificate`. This item should therefore no longer be described as missing from the data model, although broader workflow, sync, and reporting use of CRL data is still incomplete.

### 9.2 Manifests
**Defining reference:** RFC 6486; RFC 6481, Section 2; RFC 8897, Section 4.

**Data-model status:** Implemented already.

The data model already contains `Manifest` and `ManifestEntry`, plus the supporting relationships needed to use them: `Manifest.signed_object`, `Manifest.current_crl`, `SignedObject.current_manifest`, and `ManifestEntry` links to `SignedObject`, `Certificate`, `EndEntityCertificate`, and `CertificateRevocationList`. This means manifest membership and publication-set semantics are already modeled, even if those relationships are not yet fully exploited throughout the active operator workflow.

### 9.3 End-entity (EE) certificates for signed objects
**Defining reference:** RFC 6487; RFC 6488; RFC 9582 for ROAs.

**Data-model status:** Partially implemented.

`EndEntityCertificate` already exists as a first-class model, and `SignedObject.ee_certificate` already gives signed objects an explicit EE-certificate relationship. The model also captures issuer, serial, SKI, AKI, validity dates, publication point, resource-certificate linkage, and revocation linkage via `RevokedCertificate.ee_certificate`. What is still not clearly modeled are fuller EE-profile details such as inherited-vs.-enumerated resource constraints and other deeper certificate-profile semantics. This item is therefore no longer absent, but it is not fully realized.

### 9.4 Repository publication points and retrieval topology
**Defining reference:** RFC 6480; RFC 6481; RFC 8182.

**Data-model status:** Partially implemented.

The explicit model layer already includes `Repository` and `PublicationPoint`, and `SignedObject` carries `object_uri`, `repository_uri`, `filename`, publication status, and validation metadata. The provider-sync side also now includes `ImportedPublicationPoint`, `ImportedSignedObject`, and `ImportedCertificateObservation`. That means repository and publication-point semantics are already present in the schema. What remains not yet implemented in the data model are some of the more specialized structures called out here, especially a separate `PublishedObjectLocation` abstraction and distinct `RrdpSession` or `RrdpSnapshot` history models.

### 9.5 Trust anchors, TALs, and trust-anchor rollover artifacts
**Defining reference:** RFC 6490; RFC 8630; RFC 9691.

**Data-model status:** Implemented already.

The current schema already contains `TrustAnchor`, `TrustAnchorLocator`, and `TrustAnchorKey`, along with explicit rollover relationships (`TrustAnchor.superseded_by` and `TrustAnchorKey.supersedes`) and publication metadata such as TAL URIs and trust-anchor-key publication URI. `Certificate` also already has a `trust_anchor` foreign key. This item should therefore be treated as implemented in the data model, even though the surrounding operator workflow is still much thinner than the schema now allows.

### 9.6 Generic signed-object framework
**Defining reference:** RFC 6488; IANA RPKI Signed Objects registry.

**Data-model status:** Partially implemented.

The schema already has a generic `SignedObject` model with content type, EE-certificate linkage, publication-point linkage, URI and filename fields, manifest linkage, CMS metadata, validity windows, and validation status. Several object families already attach to it directly: `Manifest`, `ASPA`, `RSC`, and `TrustAnchorKey`, while legacy `Roa` has a compatibility `signed_object` link. However, the abstraction is not yet uniform across every family: CRLs are still modeled separately rather than as typed `SignedObject` extensions, and the legacy ROA model still reflects the earlier architecture. This item is therefore partly done, not missing.

### 9.7 Autonomous System Provider Authorizations (ASPAs)
**Defining reference:** IANA RPKI registries; draft-ietf-sidrops-aspa-profile (current SIDROPS working-group definition).

**Data-model status:** Implemented already.

This item is no longer absent. The data model already includes `ASPA` and `ASPAProvider`, plus the broader ASPA control-plane and observation family: `ImportedAspa`, `ImportedAspaProvider`, `ASPAIntent`, `ASPAIntentMatch`, `ASPAReconciliationRun`, `ASPAIntentResult`, `PublishedASPAResult`, and `ValidatedAspaPayload`. ASPA is now a real modeled object family in both the standards-oriented schema and the operational reconciliation layer.

### 9.8 RPKI Signed Checklists (RSCs)
**Defining reference:** RFC 9323.

**Data-model status:** Implemented already.

The current schema already includes `RSC` and `RSCFileHash`, and `RSC` already links into the generic `SignedObject` layer through `RSC.signed_object`. That means the checklist object family and its hash-set child table are already present in the data model. The remaining gap here is workflow and operational use, not core schema presence.

### 9.9 BGPsec Router Certificates
**Defining reference:** RFC 8209.

**Data-model status:** Partially implemented.

`RouterCertificate` already exists as a first-class model with resource-certificate linkage, publication-point linkage, ASN association, subject and issuer fields, serial, SKI, router public key, validity dates, and validation status. That means router certificates are already represented in the data model. What remains not yet implemented here are some of the broader taxonomy and integration concerns mentioned in this section, especially a cleaner certificate-type hierarchy and optional links to device or logical-router inventory.

### 9.10 Relying-party and validated-payload view
**Defining reference:** RFC 8897; RFC 8210 / 8210bis family for cache-to-router exchange.

**Data-model status:** Implemented already.

The schema already includes `ValidatorInstance`, `ValidationRun`, `ObjectValidationResult`, `ValidatedRoaPayload`, and `ValidatedAspaPayload`, with timestamps, status, disposition, reason text, and links back to modeled ROA, ASPA, and signed-object records. This means the relying-party and validated-payload view is already present in the data model. What is still incomplete is the broader operator overlay around that data, plus any optional router or cache export metadata that may be worth adding later.

### 9.11 What this should change in the plugin’s core schema direction

**Implementation status:** First-wave compatibility-preserving normalization is now implemented and release-gate verified.

Taken together, the current section 9 status pointed to a more specific conclusion than “add more tables.” The codebase already contained most of the major standards-aligned model families. The remaining task was to normalize the schema so the older legacy objects and the newer standards-oriented objects formed one coherent architecture.

That work has now been executed as a **compatibility-preserving normalization** effort rather than a second schema reset.

The completed first wave delivered three things.

1. **Object semantics were moved further toward `SignedObject`.**  
   The plugin already had a generic `SignedObject` layer plus typed extensions such as `Manifest`, `ASPA`, `RSC`, and `TrustAnchorKey`, and the legacy `Roa` model already had a compatibility link to it. The first wave made that normalization path more explicit by tightening ROA linkage, exposing `SignedObject`-centric reverse relationships through the generated UI/API/GraphQL surfaces, and making the normalized object layer visible rather than implicit.
2. **Certificate-role boundaries were cleaned up.**  
   The schema already distinguished legacy resource certificates, `EndEntityCertificate`, and `RouterCertificate`, but those roles were not expressed as cleanly or consistently as they should be. The first wave kept the existing multi-model split, added additive guardrails, linked router certificates more explicitly through EE certificates, and exposed certificate-role relationships more intentionally in the generated surfaces.
3. **Publication, imported observation, and validation linkage were tightened.**  
   The schema already had `Repository`, `PublicationPoint`, provider-imported publication-observation families, and validator-output families. The first wave aligned authored state, imported state, and validated state through explicit foreign-key linkage so one object can now be followed more cleanly across publication, sync, and validation views.

The most useful way to think about the target architecture is still as five layers, but now as an implemented first-wave normalization target built on top of what already existed rather than as a hypothetical redesign:

1. **Authority layer:** trust anchors, parent or child CA relationships, resource certificates, router certificates.  
2. **Publication layer:** repositories, publication points, URIs, RRDP or rsync metadata, and imported publication observation.  
3. **Object layer:** generic signed objects plus typed payload extensions such as ROA, Manifest, ASPA, RSC, and Trust Anchor Key.  
4. **Integrity layer:** EE certificates, CRLs, manifest membership, revocation state, freshness state, and related certificate observations.  
5. **Validation layer:** relying-party observations, validated payloads, reconciliation artifacts, and related operator evidence.

The first wave followed these implementation rules:

- additive migrations and compatibility shims rather than destructive renames
- keeping the explicit Django model layer as the source of truth
- preserving stable UI, API, and GraphQL contracts while the internals are normalized
- reducing special-case legacy ROA and certificate assumptions over time instead of trying to replace them in one pass

The implemented first wave includes, at minimum:

- additive schema slices for CRL-to-`SignedObject`, router-certificate-to-EE-certificate, legacy ROA-to-`SignedObject`, validated-payload-to-object-validation, and authored-to-imported publication linkage
- provider-sync updates that populate the new imported-observation relationships
- certificate-role guardrails and clearer certificate-role surfaces
- explicit `SignedObject` detail, API, and GraphQL exposure for normalized reverse relationships
- release-gate verification with clean schema-drift checks and a full plugin-suite pass

What remains after this point is no longer first-wave 9.11 implementation. Remaining work is second-wave refinement, such as:

- deciding whether certificate-role guardrails should tighten further for newly created data
- deciding whether any additional authored-to-validation linkage is worth adding beyond the current joins
- deciding whether some now-proven compatibility links should become stronger creation-time defaults
- continuing longer-term convergence where CRLs and other legacy seams still do not follow a perfectly uniform typed-`SignedObject` extension model

In short, section 9.11 should now be read as **first-wave completed**: the existing standards-aligned layers have been materially normalized into a more coherent architecture without a schema reset, and any remaining work is follow-on refinement rather than the initial normalization push itself.

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
