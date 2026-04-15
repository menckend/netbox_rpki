# netbox-rpki Plugin Design and Functional Objectives

## Purpose

This document defines the design and functional objectives for the netbox-rpki plugin as an evaluable checklist. Each item is a concrete requirement that can be checked against the current implementation. Objectives are grouped by functional domain and ordered by dependency.

Related documents:
- [Enhancement Backlog](netbox_rpki_enhancement_backlog.md) — active capability status and priority ordering
- [Surface Contract Checklist](netbox_rpki_surface_contract_checklist.md) — registry-driven release gate criteria

---

## A. Standards-Aligned Data Model

- [ ] A.1 Model the RPKI object graph with explicit types for resource certificates, end-entity certificates, ROAs, ASPAs, manifests, CRLs, signed objects, publication points, repositories, trust anchors, TALs, trust-anchor keys, RSCs, and router certificates.
- [ ] A.2 Converge on `SignedObject` as the shared object spine; each signed-object family attaches to it rather than duplicating publication, validity, and certificate linkage.
- [ ] A.3 Model certificate roles (resource, EE, router) with distinct creation-time constraints and display treatment.
- [ ] A.4 Model publication topology: repositories, publication points, retrieval URIs, and parent/child CA authority relationships.
- [ ] A.5 Model validated payloads (VRPs, validated ASPA payloads) as first-class objects linked to originating signed objects and validation runs.
- [ ] A.6 All models follow NetBox plugin conventions: tagged, tenant-aware, commentable, changelog-tracked where appropriate.
- [ ] A.7 Schema supports future provider and object-family expansion without requiring a reset.

## B. Registry-Driven Plugin Surfaces

- [ ] B.1 Every exposed object type is declared in the object registry with labels, routes, API spec, filterset, filter form, table, GraphQL spec, view spec, and navigation metadata.
- [ ] B.2 UI list pages, detail pages, forms, tables, and navigation entries are generated from the registry.
- [ ] B.3 API serializers, viewsets, and router registration are generated from the registry.
- [ ] B.4 GraphQL types, filters, and query fields are generated from the registry.
- [ ] B.5 Read-only objects never expose add/edit/delete affordances in page controls, row-action menus, or related-object tables.
- [ ] B.6 API read-only objects expose only GET/HEAD/OPTIONS; writable objects expose the full CRUD verb set.
- [ ] B.7 Custom per-object API actions are scoped to the correct viewsets, reject unsupported verbs, and enforce permissions.

## C. Intent-to-ROA Reconciliation

- [ ] C.1 Derive intended ROA state deterministically from NetBox IPAM and routing context (prefixes, ASNs, tenant, VRF, site, region).
- [ ] C.2 Compare intended state against both local ROA records and provider-imported authorization state.
- [ ] C.3 Classify drift with explicit types: create, withdraw, replace (exact-prefix replacement-required).
- [ ] C.4 Persist reconciliation runs, intent results, and published-ROA results as auditable first-class objects.
- [ ] C.5 Generate draft ROA change plans from reconciliation results.
- [ ] C.6 Expose the full intent-to-plan workflow through service layer, management command, background job, REST API, and web UI.

## D. ASPA Operations

- [ ] D.1 Model ASPA inventory with provider-authorization constraints.
- [ ] D.2 Import ASPA state through the provider sync layer.
- [ ] D.3 Support ASPA intent, reconciliation, and result objects analogous to the ROA workflow.
- [ ] D.4 Support provider-backed ASPA write-back (preview, approval, apply) for at least one provider.
- [ ] D.5 Expose ASPA intent, reconciliation, and change-plan surfaces through API, GraphQL, and web UI.

## E. ROA Linting and Safety Analysis

- [ ] E.1 Persist `ROALintRun` and `ROALintFinding` records from reconciliation and change-plan flows.
- [ ] E.2 Evaluate lint rules covering over-authorization, unnecessary ROAs, maxLength policy, and tenant-aware ownership context.
- [ ] E.3 Support per-organization `ROALintRuleConfig` overrides for rule-specific severity or approval-impact tuning.
- [ ] E.4 Support lint suppressions scoped to intent, profile, organization, or prefix.
- [ ] E.5 Support standalone acknowledgement workflows with `previously_acknowledged` carry-forward posture.
- [ ] E.6 Gate change-plan approval on current lint posture.
- [ ] E.7 Expose lint findings, suppression state, and acknowledgement state through API and web surfaces.

## F. ROV Impact Simulation

- [ ] F.1 Before approval, simulate predicted validation outcomes for proposed ROA changes.
- [ ] F.2 Persist simulation runs and results as first-class auditable objects.
- [ ] F.3 Gate approval on current simulation posture; require acknowledgement when simulation flags risk.
- [ ] F.4 Record structured simulation audit data on approval records.
- [ ] F.5 Roll up simulation posture into aggregate API and operations-dashboard views.

## G. Bulk Generation and Templating

- [ ] G.1 Model reusable routing-intent templates, template rules, and template bindings.
- [ ] G.2 Compile template bindings deterministically into the existing intent derivation pipeline.
- [ ] G.3 Model typed routing-intent exceptions with explicit precedence and approval requirements.
- [ ] G.4 Model ROA intent overrides with explicit action semantics.
- [ ] G.5 Support profile-level queued regeneration and organization-scoped bulk runs through job queue and management command.
- [ ] G.6 Persist `BulkIntentRun` and `BulkIntentRunScopeResult` with aggregate operator-facing summaries.
- [ ] G.7 Surface stale-binding and bulk-health rollups on the operations dashboard.

## H. Provider Synchronization

- [ ] H.1 Implement a provider-agnostic sync contract organized by object family (ROA, ASPA, CA metadata, parent/child links, resource entitlements, publication points, signed objects, certificate observations).
- [ ] H.2 Implement provider-specific adapters behind the shared contract; at minimum Krill and ARIN ROA import.
- [ ] H.3 Maintain durable external object identity across sync runs.
- [ ] H.4 Retain `ProviderSnapshot`, `ProviderSnapshotDiff`, and `ProviderSnapshotDiffItem` records with churn and freshness metadata.
- [ ] H.5 Expose imported-family reporting, sync health, and diff summaries through REST, GraphQL, and web UI.
- [ ] H.6 Implement an explicit provider capability matrix in code (`supports_roa_read`, `supports_roa_write`, `supports_aspa_read`, `supports_aspa_write`, `supports_certificate_inventory`, `supports_repository_metadata`, `supports_bulk_operations`, etc.) to prevent the core model from becoming provider-shaped.
- [ ] H.7 Provider-gated test environments (ARIN OT&E, RIPE test) are optimization, not prerequisite; day-to-day development uses local fixtures and a Krill backend.

## I. Change Control and Governance

- [ ] I.1 ROA and ASPA change plans support multi-stage lifecycle: draft, approved, applying, applied, failed.
- [ ] I.2 Support secondary approval with distinct actors.
- [ ] I.3 Capture maintenance-window metadata, ticket references, and actor attribution on change plans.
- [ ] I.4 Persist approval history as `ApprovalRecord` objects.
- [ ] I.5 Persist provider write execution audit rows linking back to sync runs and snapshots.
- [ ] I.6 Support provider-backed rollback bundles with their own approve-and-apply lifecycle.
- [ ] I.7 Routing-intent exceptions require explicit approval before affecting derived policy.
- [ ] I.8 Surface governance rollups (approval posture, plan status, rollback availability) on the operations dashboard.

## J. Lifecycle, Expiry, and Publication Health

- [ ] J.1 Model lifecycle health policies with configurable thresholds.
- [ ] J.2 Model lifecycle health hooks and events with severity and status tracking.
- [ ] J.3 Surface provider lifecycle summaries, publication-observation health, and provider-account timelines.
- [ ] J.4 Expose publication-diff timelines and sync-age visibility.
- [ ] J.5 Support JSON and CSV export for lifecycle and health reporting.
- [ ] J.6 Surface expiry risk, stale publication, and provider health on the operations dashboard.

## K. IRR Coordination

- [ ] K.1 Model IRR sources, snapshots, and imported IRR objects (route objects, route sets, AS sets, aut-nums, maintainers).
- [ ] K.2 Model IRR coordination runs and results to compare ROA intent with IRR route-object state.
- [ ] K.3 Model IRR change plans and change plan items for proposed IRR modifications.
- [ ] K.4 Support IRR write execution with audit tracking.
- [ ] K.5 Surface IRR coordination mismatches without blocking core RPKI workflows.

## L. External Validator and Telemetry Overlays

- [ ] L.1 Model validator instances, validation runs, and per-object validation results.
- [ ] L.2 Model telemetry sources, telemetry runs, and BGP path observations.
- [ ] L.3 Correlate authored objects, imported provider objects, and relying-party observations in a unified operational view.
- [ ] L.4 Surface validation and telemetry evidence in dashboards, drill-downs, and change reviews.

## M. Service Context and Topology Binding

- [ ] M.1 Intent layer binds to NetBox prefixes, ASNs, tenant, VRF, site, region, tags, and custom fields.
- [ ] M.2 Routing-intent profiles, context groups, and context criteria support flexible operator-defined scoping.
- [ ] M.3 Support grouping and inheritance semantics for policy reuse at operator scale.

## N. Downstream and Delegated Authorization

- [ ] N.1 Model resources or policy operated on behalf of downstream customers or delegated entities without blurring ownership.
- [ ] N.2 Support explicit downstream or managed-authorization relationships as first-class constructs.
- [ ] N.3 Support upstream-managed publication workflows.

---

## Testing Strategy Summary

### Local fixture tests must prove

- All model migrations apply cleanly.
- Every registered object's UI list and detail pages render.
- Add/edit/delete affordances match each object's mutability contract.
- API method exposure matches read-only versus writable declarations.
- GraphQL detail and list queries succeed for every exposed type.
- Reconciliation, linting, simulation, and bulk-run logic produce deterministic results from fixtures.
- Governance workflows enforce their lifecycle constraints.
- Registry-driven surface contract tests iterate every object spec and verify the above.

### Live-backend tests must prove

- Provider sync creates, polls, and diffs real objects against a Krill backend.
- Parent/child CA relationships, publication metadata, and multi-family imports behave correctly under real API timing.
- Provider write-through (preview, approve, apply) completes end-to-end.

### Provider-gated tests prove only the delta

- Provider-specific adapter behavior (authentication, payload shape, pagination, error semantics) for ARIN or RIPE.
- Not required for day-to-day development velocity.

### Release gate

A green suite requires (per `netbox_rpki_surface_contract_checklist.md`):

1. Registry-wide list-view and detail-view surface tests pass.
2. Registry-wide row-action contract tests pass.
3. Registry-wide API method-contract tests pass.
4. Registry-wide GraphQL queryability tests pass.
5. Custom per-object API action tests pass.
6. Full plugin suite passes.