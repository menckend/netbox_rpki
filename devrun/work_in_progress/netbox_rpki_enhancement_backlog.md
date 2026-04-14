# NetBox RPKI Plugin: High-Priority Enhancement Backlog for Hosted-RPKI Consumers

**Last updated:** April 13, 2026

## 1. Purpose

This document is the active backlog and status view for the plugin. It is intentionally focused on four questions:

- what the plugin can do now
- what the end state should look like
- what the remaining gap is
- what order that gap should be closed in

Detailed schema-normalization design, migration sequencing, and compatibility decisions are maintained separately to avoid duplicating architecture material inside the backlog:

- [Schema Normalization Plan](netbox_rpki_schema_normalization_plan.md)
- [Schema Normalization Decision Log](netbox_rpki_schema_normalization_decision_log.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)

Exact test counts are intentionally not repeated throughout this file. They drift quickly and make the backlog harder to keep accurate. This document tracks capability status, not transient verification totals.

## 2. Current-State Snapshot

| Area | Status | Current state | Main remaining gap |
| --- | --- | --- | --- |
| Intent and ROA reconciliation | Functionally complete | Real operator workflow exists for intent derivation, reconciliation, replacement-aware drift classification, draft change-plan generation, and drill-down UX across service, job, command, API, and web surfaces. | Workflow-surface parity, richer operator explanations, and exception handling around lint and simulation results. |
| Provider sync and write-through | Mostly complete | Live ARIN ROA import remains available, and the Krill slice now supports retained snapshots, durable external identity, imported object families, family rollups, stable evidence summaries, diff persistence, sync-health metadata, provider-account capability and reporting surfaces, and capability-gated ROA and ASPA preview, approve, and apply flows. | Broader provider coverage, richer publication-observation fidelity, and additional workflow depth beyond the current Krill-backed control-plane contract and ARIN's ROA-only reporting boundary. |
| ASPA operations | Mostly complete | ASPA inventory, provider import, intent, reconciliation, change planning, and Krill-backed preview, approval, and apply flows now exist, with job, command, API, web, and dashboard drill-down surfaces plus shared audit rows. | Broader provider support, richer reporting, diff, and export surfaces, and future lint or simulation support. |
| Governance and reporting | Mostly complete | ROA and ASPA change plans support preview, approval, apply, ticket or change metadata, maintenance windows, approval history, and shared provider execution audit rows. The operations dashboard now surfaces stale or failed sync state, family coverage, latest snapshot or diff links, expiry visibility, and ASPA reconciliation and change-plan attention views. | Rollback bundles, multi-stage approvals, richer publication-state semantics, exports, alerting hooks, and broader governance beyond the current Krill-backed ROA and ASPA slice. |
| Standards-aligned schema | Functionally complete | Compatibility-preserving normalization is in place around `SignedObject`, certificate roles, authored or imported publication linkage, and validation linkage. | Second-wave refinement rather than another schema reset. |

## 3. End-State Objectives

1. NetBox should express intended routing-security policy from real service context, not just store authored RPKI artifacts.
2. The plugin should ingest and normalize real provider state across multiple providers and object families, not just one provider and one object type.
3. Operators should be able to reconcile intended state, local modeled state, imported provider state, and eventually validated payload state in one coherent workflow.
4. Unsafe ROA and ASPA changes should be explainable before publication, including blast radius, over-authorization, and likely validation impact.
5. Publication workflows should be auditable, approval-aware, rollback-capable, and provider-agnostic at the contract level even when adapters differ.
6. The UI should surface operational health directly: sync drift, expiry, publication freshness, validation observations, and provider diffs.
7. The data model should remain standards-aligned enough to support repositories, signed objects, validation outputs, and future provider or object expansion without a second schema reset.
8. The plugin should support enterprise and provider operating models, including customer or downstream resources managed on behalf of another party.

## 4. Backlog Conventions

### 4.1 Status Labels

- **Functionally complete:** the dependency-critical slice is closed; remaining work is refinement rather than foundation.
- **Mostly complete:** the shared substrate is real and useful, but important breadth or reporting gaps remain.
- **Partially complete:** a meaningful first slice exists, but the end-state workflow is still clearly incomplete.
- **Not started:** no meaningful operator workflow exists yet.

### 4.2 Closure Criteria

Treat a backlog item as closed only when all of the following are true:

- the schema or registry contract exists and is migration-safe
- the service layer performs the actual work rather than leaving the feature as passive inventory
- operators can reach it through an intentional UI, API, command, or job surface as appropriate
- the result is explainable in operator terms and fits the audit model
- focused regression tests exist and the plugin suite remains green

### 4.3 Scope Guardrails

- Do not turn the plugin into a full certificate authority implementation.
- Do not treat a full relying-party validator as a prerequisite for useful operator workflows.
- Do not expand write-back automation provider by provider until the shared diff, planning, and governance surfaces are stable.
- Do not let BGP telemetry or IRR coordination substitute for a missing core intent and reconciliation loop.
- Do not represent every RFC corner case ahead of the control-plane features operators need day to day.

## 5. Preferred Dependency Order

The closure order should stay dependency-driven rather than milestone-driven.

1. Complete provider synchronization as a reusable substrate.
2. Mature the safety-analysis layers already attached to existing plans.
3. Mature governance around those safer plan objects.
4. Finish ASPA parity on the shared workflow substrate.
5. Deepen service-context binding and bulk authoring.
6. Add external evidence and coordination layers.
7. Finish provider-scale and downstream operating models.

## 6. Capability Gap Backlog

The priority labels below are stable backlog buckets rather than the literal execution sequence; use Section 5 for dependency order.

### Priority 1: Intent-to-ROA Reconciliation

- **Status:** Functionally complete
- **End state:** deterministic derivation of intended ROA state from NetBox service context, with clear drift classification, operator drill-down, and actionable remediation planning
- **Current state:** the core intent and reconciliation stack exists, compares both local ROA state and provider-imported authorization state, classifies replacement-required exact-prefix drift, generates paired replacement create and withdraw actions, persists analysis objects, and exposes operator drill-down through service, job, command, API, and web surfaces
- **Remaining gap:** operator exception and acknowledgement flows for lint findings, richer simulation explanations and scenario coverage, broader roll-up reporting, and finer-grained local-model reshape semantics beyond the current `create` or `replace` or `withdraw` contract
- **Closure order:** treat Priority 1 as dependency-closed; only take follow-on work here when it unblocks later provider, governance, or bulk-authoring work

#### Active refinement slice: workflow-surface parity

The main remaining Priority 1 work is not new domain modeling. It is parity between operator workflow surfaces.

Action surfaces to add:

- add a web-UI action for `routingintentprofile.run`
- add a web-UI action for `roareconciliationrun.create_plan`
- add a web-UI action for `roachangeplan.simulate`

Summary surfaces to expose through existing UI reporting:

- surface `roareconciliationrun.summary` in list-page headers, dashboard cards, or similar roll-up surfaces rather than as a standalone page
- surface `roachangeplan.summary` the same way

Close this refinement slice when:

- every custom API workflow action representing a human operator step is reachable from the web UI or explicitly documented as API-only by design
- reconciliation and change-plan aggregate health data are visible somewhere in the web UI
- tests prove route presence, permission enforcement, and expected UI affordances together

### Priority 2: Hosted-Provider Synchronization

- **Status:** Mostly complete
- **End state:** provider-agnostic synchronization of ROAs, ASPAs, publication-topology metadata, published certificates, published signed objects, and related provider control-plane metadata with durable identity, retained snapshots, meaningful diffs, and health visibility
- **Current state:** the foundational Krill slice is materially implemented. The codebase has a family-oriented sync contract, provider-specific Krill adapter logic, durable external object identity, retained snapshot-diff artifacts, imported-family reporting surfaces, provider-account rollups, explicit ROA and ASPA write-capability reporting, capability-gated ROA and ASPA write-through flows, operations-dashboard coverage, and continued ARIN ROA import compatibility
- **Delivered slice today:** Krill imports now cover ROA authorizations, ASPAs, CA metadata, parent links, child links, resource entitlements, publication points, signed-object inventory, and repository-derived certificate observations. Those records feed `ProviderSnapshot`, `ProviderSnapshotDiff`, and `ProviderSnapshotDiffItem` reporting through UI, REST, GraphQL, provider-account detail surfaces, and the operations dashboard. Krill-backed ROA and ASPA change plans can now preview, approve, apply, and record shared execution audit data through UI and REST surfaces. ARIN shares the same reporting contract within its current ROA-only support boundary
- **Remaining gap:** broader provider coverage, deeper publication-observation fidelity for certificate and signed-object inventory, richer alerting and export surfaces, and additional workflow depth beyond the current Krill-backed control-plane contract plus ARIN's ROA-only reporting boundary
- **Closure order:** keep Priority 2 second, but treat it as a maturity and completion track rather than a greenfield architecture item

#### Recommended next slices

1. deeper publication-observation parsing and evidence handling for certificate and signed-object inventory
2. broader provider coverage once the shared reporting and evidence model is stable
3. alerting, export, and threshold-oriented reporting on top of the current provider-account and dashboard rollups

### Priority 3: ASPA Operational Support

- **Status:** Mostly complete
- **End state:** ASPA intent, provider synchronization, reconciliation, change planning, provider preview, approval, apply, and reporting should be first-class alongside ROAs
- **Current state:** `ASPA` inventory is hardened with provider-authorization constraints and detail UX, Krill-backed imported ASPA state is normalized through the provider-sync layer, and ASPA intent, reconciliation, change-plan, preview, approve, and apply workflows now exist with job, command, API, web, and dashboard surfaces plus shared approval and provider-execution audit rows
- **Remaining gap:** broader provider coverage beyond the current Krill-backed ASPA write path, richer reporting, diff, and export surfaces, and eventual lint or simulation workflows analogous to the ROA roadmap
- **Closure order:** treat the Krill-backed operational substrate as real and extend it through shared provider, reporting, and analysis layers rather than building an ASPA-specific side path

### Priority 4: ROA Linting and Safety Analysis

- **Status:** Partially complete
- **End state:** operators can see when intended or published ROAs are too broad, unnecessary, risky, or inconsistent with routing intent
- **Current state:** reconciliation and change-plan flows can persist `ROALintRun` and `ROALintFinding` records, expose summary counts in API and UI surfaces, and present operator drill-down from reconciliation and plan detail pages
- **Remaining gap:** deepen the rule set, add clearer operator explanations and exception handling, and decide how acknowledgements or suppressions should feed approval and reporting workflows
- **Closure order:** iterate here before adding heavier governance on top of the same plan objects

#### Closure plan

Treat Priority 4 as four dependency-ordered slices built on the existing `ROAReconciliationRun` -> `ROALintRun` -> `ROALintFinding` contract rather than as a new workflow.

1. expand the rule contract
2. make findings explainable in operator terms
3. add acknowledgement and suppression workflow
4. feed lint state into approval and reporting surfaces

#### Slice 1: expand the rule contract

The current `netbox_rpki.services.roa_lint` implementation mostly mirrors existing reconciliation result types. The first gap to close is breadth.

Add rules in three buckets:

- intent safety rules: overbroad `maxLength`, redundant duplicate intent, inactive or suppressed intent still matched by published state, and intent that would broaden an existing published authorization during replacement
- published-state hygiene rules: orphaned authorization, stale authorization, duplicate coverage for the same prefix or origin tuple, and broader-than-needed coverage that is not justified by current intent
- plan-risk rules: replacement pair, reshape pair, net-new broadened authorization, high-withdraw concentration, and provider-backed remove operations that would leave no remaining covering authorization

Implementation notes:

- keep `finding_code` stable and versioned as the public rule identifier
- normalize a small rule catalog in code so each rule has severity defaults, short label text, and a deterministic details schema
- extend `ROALintRun.summary_json` with counts by rule family and blocking-vs-informational totals, not just severity counts

Close Slice 1 when:

- each supported rule is generated deterministically from reconciliation or plan state without requiring manual interpretation
- rule outputs are stable enough to assert directly in service tests
- the summary contract distinguishes informational hygiene findings from approval-relevant safety findings

#### Slice 2: make findings explainable

Once rule coverage is broader, the next gap is operator comprehension. Today most meaning is buried in `details_json`.

Add an explanation contract for every finding:

- what is wrong
- why it matters
- what object or plan item triggered it
- what the expected operator action is
- whether the issue is advisory, approval-blocking, or approval-requires-acknowledgement

Surface that explanation through existing API and web detail views rather than inventing a separate report page first.

Implementation notes:

- generate explanation text in the service layer so API, UI, and future exports share one contract
- keep raw facts in `details_json`, but add normalized summary fields such as `rule_label`, `operator_message`, `operator_action`, and `approval_impact`
- group lint findings in plan and reconciliation views by severity and rule family so operators can understand the shape of risk quickly

Close Slice 2 when:

- a reviewer can understand any finding from API or UI output without reading internal result-type enums
- plan and reconciliation detail pages surface the same explanation and severity semantics
- regression tests cover both serialized output and rendered operator affordances

#### Slice 3: add acknowledgement and suppression workflow

The main unresolved design gap is exception handling. The plugin already has approval records for plans, so lint exceptions should attach to that workflow instead of becoming a parallel audit model.

Model two separate operator actions:

- acknowledgement: a human reviewed a finding for this reconciliation run or change plan and accepts the risk for the current artifact
- suppression: a scoped rule exception prevents the same finding from reopening until an explicit expiry, scope change, or intent change invalidates it

Recommended scope order:

1. per-change-plan acknowledgement with actor, timestamp, reason, and optional ticket reference
2. per-profile or per-intent suppression for stable false-positive-style cases
3. explicit expiry and reevaluation semantics before allowing indefinite suppressions

Implementation notes:

- do not overload `ApprovalRecord`; either link lint acknowledgements to it or create a sibling audit model with the same actor and metadata shape
- keep suppression matching narrow and explicit: rule code plus the minimum stable object identity needed to avoid broad accidental silence
- invalidate suppressions automatically when the triggering facts materially change

Close Slice 3 when:

- operators can acknowledge findings during review without editing raw data
- suppressions are auditable, scope-limited, and reversible
- rerunning reconciliation or plan creation reopens findings unless an active matching suppression still applies

#### Slice 4: feed lint state into approval and reporting

Lint only becomes operationally useful when it changes approval behavior and roll-up visibility.

Integrate lint into workflow surfaces:

- show blocking, acknowledged, and suppressed lint counts in change-plan list and detail summaries
- expose the latest unresolved lint posture in dashboard or aggregate reporting surfaces
- enforce a clear policy on approval: blocking findings stop approval, acknowledgement-required findings require explicit operator action, and advisory findings remain informational

Implementation notes:

- keep the first policy simple: approval gating should read from normalized lint summary data, not re-run rule logic inside the form or view layer
- add API and UI affordances for "approve with acknowledgements" only after the blocking-vs-acknowledgement contract exists
- record approval decisions against the lint posture that was reviewed so later reporting can distinguish ignored from newly introduced risk

Close Slice 4 when:

- approval behavior is deterministic from lint status
- list, detail, API, and dashboard surfaces all agree on unresolved vs acknowledged vs suppressed counts
- tests cover approval denial, approval with acknowledgement, and post-rerun reopening behavior

#### Suggested execution order

1. land the rule catalog and expanded summary contract in `services/roa_lint.py`
2. expose normalized explanation fields in serializers and detail templates
3. add acknowledgement persistence and UI or API actions on `ROAChangePlan`
4. add scoped suppression persistence and invalidation rules
5. wire approval gating and dashboard or list roll-ups
6. backfill focused tests across services, API, views, and approval workflow

#### Priority 4 closure criteria

Treat Priority 4 as closed only when all of the following are true:

- lint rules cover both hygiene findings and materially unsafe plan outcomes
- operators can understand why a finding exists and what action is expected
- acknowledgement and suppression flows are auditable and rerun-safe
- approval logic consumes lint posture explicitly rather than ignoring it
- aggregate reporting can distinguish blocking, acknowledged, and suppressed risk at a glance

### Priority 5: ROV Impact Simulation

- **Status:** Partially complete
- **End state:** before approval or apply, operators can see predicted validation outcomes and blast radius for proposed changes
- **Current state:** change-plan creation can persist `ROAValidationSimulationRun` and `ROAValidationSimulationResult` records, API surfaces expose the latest simulation summary, and operators can review predicted valid, invalid, and not-found counts from plan detail and aggregate surfaces
- **Remaining gap:** improve simulation fidelity and explanation quality, add richer scenario coverage and blast-radius reasoning, and wire deterministic approval behavior onto the resulting simulation posture
- **Closure order:** continue iterating after linting, keeping the work attached to the same reconciliation and plan contracts

#### Detailed working plan

The detailed Priority 5 design, proposed simulation contract, model evolution, service expectations, workflow surfaces, and execution slices now live in:

- [ROV Impact Simulation Plan](netbox_rpki_rov_impact_simulation_plan.md)

That working document breaks the effort into explicit execution slices covering:

1. simulation contract freeze
2. service-fidelity expansion
3. additive model or summary evolution only where necessary
4. richer explanation and blast-radius surfaces
5. aggregate reporting
6. approval enforcement and acknowledgement hardening
7. release-gate hardening

Keep this backlog section summary-level. Put proposed contracts, file ownership notes, execution sequencing, and detailed fidelity rules in the standalone plan.

### Priority 6: Bulk Generation and Templating

- **Status:** Not started
- **End state:** large estates can generate and maintain ROA intent through reusable policy templates, regeneration logic, and bulk workflows
- **Current state:** reconciliation can already derive expected state and create narrow change plans, but there is no templating or bulk policy-authoring layer yet
- **Remaining gap:** declarative templates, bulk planning objects, regeneration semantics, and scoped exceptions for traffic engineering, anycast, mitigation, and customer-edge use cases
- **Closure order:** after linting and simulation basics; bulk authoring without safety rails would just accelerate mistakes

#### Detailed working plan

The detailed Priority 6 design, proposed models, service and surface contracts, and execution slices now live in:

- [Bulk Generation and Templating Plan](netbox_rpki_bulk_generation_and_templating_plan.md)

That working document breaks the effort into explicit execution slices covering:

1. contract freeze and naming decisions
2. template and bulk schema substrate
3. generated CRUD surfaces for new authored objects
4. effective-policy compilation and preview
5. regeneration state and stale detection
6. typed exceptions
7. bulk run aggregation and draft-plan fan-out
8. workflow-surface rollout and release-gate hardening

Keep this backlog section summary-level. Put proposed models, field contracts, file ownership notes, and implementation sequencing in the standalone plan.

### Priority 7: Deeper NetBox Binding and Service Context

- **Status:** Partially complete
- **End state:** policy can be expressed and explained in terms of tenant, VRF, site, region, service role, provider, circuit, exchange, or other operating context
- **Current state:** the existing intent layer already binds to prefixes, ASNs, tenant, VRF, site, region, tags, and custom fields
- **Remaining gap:** broader topology and service-context binding, better inheritance or profile semantics, and more expressive grouping for operator-scale policy reuse
- **Closure order:** in parallel with bulk templating and ASPA expansion where dependencies allow

### Priority 8: Change Control and Auditability

- **Status:** Mostly complete
- **End state:** publication workflows are policy-aware, multi-stage, rollback-capable, and fully auditable across providers
- **Current state:** ROA and ASPA change plans support preview, approval, apply, actor attribution, maintenance-window metadata, ticket and change references, approval history, and shared provider execution audit rows
- **Remaining gap:** rollback bundles, multi-stage approvals, richer publication-state semantics, and extension of the governance contract beyond the current Krill-backed ROA and ASPA slice
- **Closure order:** after linting and simulation are available for the same plan objects

### Priority 9: Lifecycle, Expiry, and Publication Health Reporting

- **Status:** Partially complete
- **End state:** operators can see expiry risk, stale publication, sync age, provider health, and publication freshness from a single reporting layer
- **Current state:** the operations dashboard and computed provider sync-health surfaces cover stale or failed syncs plus ROA and certificate expiry windows
- **Remaining gap:** exports, thresholds, alerting hooks, publication-observation data, and richer timeline or diff-oriented reporting
- **Closure order:** alongside provider-sync maturation, because reporting quality depends on sync and publication evidence quality

### Priority 10: IRR Coordination

- **Status:** Not started
- **End state:** ROA intent and IRR route-object intent can be compared, reported, and eventually coordinated
- **Current state:** no active IRR coordination workflow exists
- **Remaining gap:** model IRR intent and consistency results, then surface mismatches without blocking core RPKI workflows
- **Closure order:** after reconciliation, linting, and provider diff surfaces are mature

### Priority 11: External Validator and Telemetry Overlays

- **Status:** Not started
- **End state:** authored objects, imported provider objects, and relying-party observations can all be correlated in one operational view
- **Current state:** standards-oriented validation-model groundwork exists in the schema, but active operator overlays are not yet wired into the main workflow
- **Remaining gap:** import validation observations, connect them to existing ROA and ASPA objects, and expose evidence in dashboards, drill-downs, and change reviews
- **Closure order:** after provider sync and lifecycle reporting mature

### Priority 12: Downstream and On-Behalf-Of Authorization Modeling

- **Status:** Not started
- **End state:** the plugin can represent resources or policy operated on behalf of downstream customers or delegated entities without blurring ownership and responsibility
- **Current state:** organization and tenancy concepts exist, but downstream authorization relationships are not modeled as first-class operating constructs
- **Remaining gap:** explicit downstream or managed-authorization relationships, clearer ownership semantics, and workflow support for upstream-managed publication
- **Closure order:** late; this matters for provider-scale operating models, but it builds on a mature core rather than defining it

## 7. Architecture Coverage Snapshot

This section is intentionally narrower than the backlog above. It describes data-model coverage only. It does not imply that each area is already complete in provider sync, operator workflow, or reporting.

| Architecture element | Data-model status | Notes |
| --- | --- | --- |
| Certificate Revocation Lists | Implemented | `CertificateRevocationList` and `RevokedCertificate` exist with issuing-certificate, publication-point, manifest, and revocation linkage. |
| Manifests | Implemented | `Manifest` and `ManifestEntry` exist with the supporting relationships needed to model publication-set semantics. |
| End-entity certificates for signed objects | Partially implemented | `EndEntityCertificate` exists and `SignedObject.ee_certificate` is present, but deeper EE-profile semantics are still thinner than the rest of the object model. |
| Repository publication points and retrieval topology | Partially implemented | `Repository`, `PublicationPoint`, `ImportedPublicationPoint`, `ImportedSignedObject`, and `ImportedCertificateObservation` exist, but more specialized RRDP or retrieval-history structures are still thin. |
| Trust anchors, TALs, and rollover artifacts | Implemented | `TrustAnchor`, `TrustAnchorLocator`, and `TrustAnchorKey` are present, along with explicit rollover relationships and certificate linkage. |
| Generic signed-object framework | Partially implemented | `SignedObject` exists and several object families already attach to it, but some legacy seams remain, especially around older ROA and CRL treatment. |
| ASPAs | Implemented | `ASPA`, provider rows, imported ASPA families, reconciliation objects, and validated ASPA payloads are all modeled. |
| RPKI Signed Checklists | Implemented | `RSC` and `RSCFileHash` exist and attach to the generic signed-object layer. |
| BGPsec router certificates | Partially implemented | `RouterCertificate` exists, but the broader taxonomy and optional links to device or logical-router inventory remain incomplete. |
| Relying-party and validated-payload view | Implemented | validator instances, validation runs, object validation results, and validated ROA or ASPA payload families are present in the schema. |

### 7.1 First-Wave Normalization Status

The first compatibility-preserving normalization wave is complete.

It delivered three structural outcomes:

1. stronger convergence on `SignedObject` as the shared object spine
2. clearer certificate-role boundaries across resource, EE, and router certificate families
3. tighter linkage across authored state, imported observation, and validation evidence

The most useful architectural view remains a five-layer model:

1. authority
2. publication
3. object
4. integrity
5. validation

Remaining normalization work is second-wave refinement rather than another schema reset. The main open questions are whether certificate-role guardrails should tighten for newly created data, whether stronger creation-time defaults are now justified, and whether any additional authored-to-validation direct linkage is still worth adding.

## 8. Related Working Documents

- [ROV Impact Simulation Plan](netbox_rpki_rov_impact_simulation_plan.md)
- [Bulk Generation and Templating Plan](netbox_rpki_bulk_generation_and_templating_plan.md)
- [Schema Normalization Plan](netbox_rpki_schema_normalization_plan.md)
- [Schema Normalization Decision Log](netbox_rpki_schema_normalization_decision_log.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)

These documents carry the more detailed design, execution, migration, compatibility, and field-level architectural material that used to be duplicated inside this backlog. Keep this file focused on active capability status and priority ordering.
