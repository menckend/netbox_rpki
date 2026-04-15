# NetBox RPKI Plugin: High-Priority Enhancement Backlog for Hosted-RPKI Consumers

**Last updated:** April 14, 2026 (P8 status refreshed)

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
| Intent and ROA reconciliation | Functionally complete | Real operator workflow exists for intent derivation, reconciliation, replacement-aware drift classification, draft change-plan generation, lint and simulation-aware approval gating, simulation audit persistence, aggregate reporting, and drill-down UX across service, job, command, API, and web surfaces. | Follow-on refinement rather than missing baseline capability. |
| Provider sync and write-through | Mostly complete | Live ARIN ROA import remains available, and the Krill slice now supports retained snapshots, durable external identity, imported object families, diff persistence, sync-health metadata, and ROA preview, approve, and apply flows. | Broader provider coverage, deeper family-specific diff reporting, better freshness and churn visibility, and richer publication-observation fidelity. |
| ASPA operations | Partially complete | ASPA inventory, provider import, intent, reconciliation, and operator drill-down surfaces now exist and share the core workflow shape used for ROAs. | Provider-backed ASPA write-back, broader provider support, richer reporting, and future lint or simulation support. |
| Governance and reporting | Mostly complete | ROA and ASPA change plans now support preview, approval, secondary approval, apply, maintenance-window and ticket metadata, approval history, provider execution audit rows, publication-state rollups, and provider-backed rollback bundles with explicit approve and apply actions. Routing-intent exceptions also have explicit approval workflow surfaces, and governance rollups plus operations-dashboard views surface stale bindings, expiring exceptions, recent bulk-run health, stale or failed sync state, and expiry visibility. | Cross-family governance breadth, export polish, alerting expansion, and deeper policy-driven governance beyond the current ROA, ASPA, rollback-bundle, and typed-exception slices. |
| Standards-aligned schema | Functionally complete for the first normalization wave | Compatibility-preserving normalization is in place around `SignedObject`, certificate roles, authored or imported publication linkage, and validation linkage. | Second-wave refinement rather than another schema reset. |

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
4. Expand the same workflow shape to ASPA.
5. Deepen service-context binding and bulk authoring.
6. Add external evidence and coordination layers.
7. Finish provider-scale and downstream operating models.

## 6. Capability Gap Backlog

### Priority 1: Intent-to-ROA Reconciliation

- **Status:** Functionally complete
- **End state:** deterministic derivation of intended ROA state from NetBox service context, with clear drift classification, operator drill-down, and actionable remediation planning
- **Current state:** the core intent and reconciliation stack exists, compares both local ROA state and provider-imported authorization state, classifies replacement-required exact-prefix drift, generates paired replacement create and withdraw actions, persists analysis objects, and exposes operator drill-down through service, job, command, API, and web surfaces; web-UI actions exist for `routingintentprofile.run`, `roareconciliationrun.create_plan`, and `roachangeplan.simulate`; reconciliation and change-plan aggregate health data are visible in the web UI
- **Remaining gap:** operator exception and acknowledgement flows for lint findings, richer simulation explanations and scenario coverage, broader roll-up reporting, and finer-grained local-model reshape semantics beyond the current `create` or `replace` or `withdraw` contract
- **Closure order:** treat Priority 1 as dependency-closed; only take follow-on work here when it unblocks later provider, governance, or bulk-authoring work

### Priority 2: Hosted-Provider Synchronization

- **Status:** Mostly complete
- **End state:** provider-agnostic synchronization of ROAs, ASPAs, publication-topology metadata, published certificates, published signed objects, and related provider control-plane metadata with durable identity, retained snapshots, meaningful diffs, and health visibility
- **Current state:** the foundational Krill slice is materially implemented. The codebase has a family-oriented sync contract, provider-specific Krill adapter logic, durable external object identity, retained snapshot-diff artifacts, imported-family reporting surfaces, and continued ARIN ROA import compatibility
- **Delivered slice today:** Krill imports now cover ROA authorizations, ASPAs, CA metadata, parent links, child links, resource entitlements, publication points, signed-object inventory, and repository-derived certificate observations. Those records feed `ProviderSnapshot`, `ProviderSnapshotDiff`, and `ProviderSnapshotDiffItem` reporting through UI, REST, and GraphQL surfaces
- **Remaining gap:** broader provider coverage, richer family-specific reporting and dashboard roll-ups, deeper publication-observation fidelity for certificate and signed-object inventory, and clearer operator-facing explanation of churn and freshness at the provider-account level
- **Closure order:** keep Priority 2 second, but treat it as a maturity and completion track rather than a greenfield architecture item

### Priority 3: ASPA Operational Support

- **Status:** Mostly complete
- **End state:** ASPA intent, provider synchronization, reconciliation, approval, and reporting should be first-class alongside ROAs
- **Current state:** `ASPA` inventory is hardened with provider-authorization constraints and detail UX, Krill-backed imported ASPA state is normalized through the provider-sync layer, and ASPA intent and reconciliation objects and services exist with job, command, API, and operator drill-down surfaces. The first provider-backed ASPA write-back slice is now complete for Krill-backed plans, including preview, approval, secondary approval, and apply lifecycle support through service, API, and web actions, provider execution audit rows, Krill ASPA delta serialization and submission, governance metadata capture, rollback-bundle support, and focused provider-write regression coverage for the ASPA path across service, API, and view failure and success paths.
- **Remaining gap:** broader provider and object-family coverage beyond the current Krill ASPA path, richer reporting and diffing, and eventual lint or simulation workflows analogous to the ROA roadmap
- **Closure order:** extend the shared control-plane surfaces rather than building an ASPA-specific side path

### Priority 4: ROA Linting and Safety Analysis

- **Status:** Mostly complete
- **End state:** operators can see when intended or published ROAs are too broad, unnecessary, risky, or inconsistent with routing intent
- **Current state:** reconciliation and change-plan flows can persist `ROALintRun` and `ROALintFinding` records, expose summary counts in API and UI surfaces, and present operator drill-down from reconciliation and plan detail pages. Per-organization `ROALintRuleConfig` overrides now allow rule-specific severity or approval-impact tuning without changing global defaults. Lint suppressions now support intent, profile, organization-wide, and prefix-scoped workflows, and the rule set has expanded into tenant-aware ownership-context analysis for intent, published ROA state, and create-plan authorization checks. Findings now carry operator-facing explanation fields, and approval plus standalone acknowledgement workflows now support `previously_acknowledged` carry-forward posture with explicit re-confirmation before approval gates pass. Focused linting, provider-write, view, API, and full plugin-suite verification are green for this implementation wave.
- **Remaining gap:** deepen the rule set further, broaden roll-up or reporting treatment of suppressions and acknowledgement state, and decide whether additional governance or acknowledgement lifecycle semantics should sit on top of the current lint posture contract
- **Closure order:** iterate here before adding heavier governance on top of the same plan objects

### Priority 5: ROV Impact Simulation

- **Status:** Functionally complete
- **End state:** before approval or apply, operators can see predicted validation outcomes and blast radius for proposed changes
- **Current state:** deterministic ROA simulation now emits normalized result and run contracts, persists first-class posture fields, gates approval on current simulation posture, supports acknowledgement-required simulation review during approval, records structured simulation audit data on approval records, exposes posture and explanation through API and detail surfaces, and rolls posture up into aggregate API and operations-dashboard views
- **Remaining gap:** follow-on refinement only, such as deeper scenario catalogs, future ASPA simulation, or broader reporting polish
- **Closure order:** complete for the first implementation wave; further work should be incremental rather than another foundational rewrite

### Priority 6: Bulk Generation and Templating

- **Status:** Mostly complete
- **End state:** large estates can generate and maintain ROA intent through reusable policy templates, regeneration logic, and bulk workflows
- **Current state:** reusable `RoutingIntentTemplate`, `RoutingIntentTemplateRule`, `RoutingIntentTemplateBinding`, `RoutingIntentException`, `BulkIntentRun`, and `BulkIntentRunScopeResult` objects now exist with registry-driven CRUD surfaces. Template bindings compile into the existing derivation pipeline, binding preview and regeneration are reachable through API and web actions, profile-level queued run or regenerate workflow is reachable from `RoutingIntentProfile`, organization-scoped bulk runs execute through the NetBox job queue, and a matching `run_bulk_routing_intent` management command now exists for synchronous or queued CLI execution. Typed exceptions require explicit approval before they participate in compilation, stale-binding or bulk-health rollups appear on the operations dashboard, and focused contract coverage now exists for the first-wave filter, table, API action, service-summary, and read-only workflow-record surfaces.
- **Remaining gap:** richer operator explanation of template conflicts, deeper exception lifecycle reporting beyond the current approve or pending model, exports and broader reporting surfaces, and any deeper provider-backed authoring semantics that should sit on top of the current queue-backed orchestration contract
- **Closure order:** the first implementation wave is materially landed; further work here should be hardening and refinement rather than another foundational rewrite

### Priority 7: Deeper NetBox Binding and Service Context

- [Implementation Plan](netbox_rpki_priority7_service_context_plan.md)

- **Status:** Mostly complete
- **End state:** policy can be expressed and explained in terms of tenant, VRF, site, region, service role, provider, circuit, exchange, or other operating context
- **Current state:** the existing intent layer already binds to prefixes, ASNs, tenant, VRF, site, region, tags, and custom fields
- **Remaining gap:** broader topology and service-context binding, better inheritance or profile semantics, and more expressive grouping for operator-scale policy reuse
- **Closure order:** in parallel with bulk templating and ASPA expansion where dependencies allow

### Priority 8: Change Control and Auditability

- **Status:** Functionally complete for the first governance wave
- **End state:** publication workflows are policy-aware, multi-stage, rollback-capable, and fully auditable across providers
- **Current state:** the first governance wave is materially landed. ROA and ASPA change plans now support preview, approval, secondary approval with distinct actors, apply, actor attribution, maintenance-window metadata, ticket and change references, approval history, provider execution audit rows, and provider-backed rollback bundles captured automatically on successful apply. Rollback bundles are first-class records with their own approve and apply actions, and publication-state derivation now surfaces lifecycle states such as awaiting approval, awaiting secondary approval, approved, applied, rollback-available, rollback-approved, and rolled back through service, API, and web surfaces. Governance rollups and dashboard surfaces now summarize approval posture across bulk runs and plan families. The newer routing-intent workflow also has explicit approval metadata and operator actions for typed exceptions before they affect derived policy.
- **Remaining gap:** broader extension of the governance contract beyond the current ROA, ASPA, rollback-bundle, bulk-run, and typed-exception slices; more policy-driven governance controls; and future reporting or export polish on top of the now-landed governance substrate
- **Closure order:** treat Priority 8 as dependency-closed for the first wave; future work here should build incrementally on the completed plan and current maturity backlog

### Priority 9: Lifecycle, Expiry, and Publication Health Reporting

- [Implementation Plan](netbox_rpki_priority9_lifecycle_publication_health_plan.md)

- **Status:** Functionally complete
- **End state:** operators can see expiry risk, stale publication, sync age, provider health, publication freshness, exportable reporting, and alerting hooks from a single reporting layer
- **Current state:** the lifecycle reporting stack now covers policy-driven thresholds, provider lifecycle summaries, publication-observation health, provider-account timelines, publication-diff timelines, dashboard and provider-account detail drill-downs, explicit UI and API export surfaces for JSON and CSV, and lifecycle-health alerting hooks with event audit records
- **Remaining gap:** follow-on refinement only, such as additional presentation polish or new reporting dimensions that build on the completed contract rather than replacing it
- **Closure order:** closed; future work should be incremental and should reuse the shared lifecycle reporting and export contracts

### Priority 10: IRR Coordination

- [IRR Coordination Plan](netbox_rpki_irr_coordination_plan.md)

- **Status:** Not started
- **End state:** ROA intent and IRR route-object intent can be compared, reported, and eventually coordinated
- **Current state:** no active IRR coordination workflow exists
- **Remaining gap:** model IRR intent and consistency results, then surface mismatches without blocking core RPKI workflows
- **Closure order:** after reconciliation, linting, and provider diff surfaces are mature

### Priority 11: External Validator and Telemetry Overlays

- [External Validator and Telemetry Overlays Plan](netbox_rpki_external_validator_and_telemetry_overlays_plan.md)

- **Status:** Not started as an operator workflow
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

- [CONTRIBUTING.md](../../CONTRIBUTING.md)

These documents carry the detailed migration, compatibility, and field-level architectural material that used to be duplicated inside this backlog. Keep this file focused on active capability status and priority ordering.
