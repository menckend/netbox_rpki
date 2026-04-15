# netbox_rpki Gap Analysis Against Feature Strategy Matrix

Source matrix: `devrun/work_in_progress/netbox_rpki_feature_strategy_matrix.md`

> **Last updated**: All previously identified gaps (C.6, H.6, G/I, A.4, M.3, N) have been closed.
> See the "Closed Gaps" section for what was added in each area.

## Scope and Method

This analysis compares the matrix objectives to the current codebase, using the actual implementation surfaces in:

- `netbox_rpki/models.py`
- `netbox_rpki/object_registry.py`
- `netbox_rpki/views.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/graphql/schema.py`
- `netbox_rpki/services/*`
- `netbox_rpki/jobs.py`
- `netbox_rpki/management/commands/*`
- `netbox_rpki/tests/*`

The plugin is materially broader than an early-stage RPKI inventory plugin. The registry currently drives ~100 object specs, with the majority of A-N implemented across real code, tests, and operator surfaces.

## Executive Summary

As of the most recent implementation pass, all identified structural gaps have been closed:

- **C.6**: ROA change-plan creation now has a dedicated management command (`create_roa_change_plan`) and background job (`CreateROAChangePlanJob`).
- **H.6**: Provider capability matrix is now explicit on `RpkiProviderAccount` with `supports_roa_read`, `supports_aspa_read`, `supports_certificate_inventory`, `supports_repository_metadata`, `supports_bulk_operations`, and a composite `capability_matrix` property.
- **G/I**: Bulk intent governance is now fully operator-surfaced via REST (`approve`, `approve-secondary` POST actions on `/api/plugins/rpki/bulkintentruns/<pk>/`) and Web UI (`BulkIntentRunApproveView`, `BulkIntentRunApproveSecondaryView`).
- **A.4**: Authored parent/child CA authority relationships are now a first-class model (`AuthoredCaRelationship`) with full registry coverage.
- **M.3**: Context group inheritance is now explicit via `RoutingIntentContextGroup.inherits_from` (self-referential FK). A `RoutingIntentPolicyBundle` model provides named, reusable policy composition as a first-class surface.
- **N**: Downstream/delegated authorization is now fully modeled via `DelegatedAuthorizationEntity`, `ManagedAuthorizationRelationship`, and `DelegatedPublicationWorkflow`, all with REST, GraphQL, and Web UI surfaces in the "Delegated" navigation group.

## Section-by-Section Assessment

| Matrix Section | Status | Evidence in Code | Primary Gap |
| --- | --- | --- | --- |
| A. Standards-Aligned Data Model | **Implemented** | All prior model coverage remains. `AuthoredCaRelationship` (A.4) was added with registry/REST/UI/GraphQL surfaces, migration `0050`. | **Closed.** A.4 now has first-class authored CA hierarchy model parity with imported topology. |
| B. Registry-Driven Plugin Surfaces | Implemented | No change. | No gap. |
| C. Intent-to-ROA Reconciliation | **Implemented** | `create_roa_change_plan` management command and `CreateROAChangePlanJob` added. C.6 surface parity is now symmetric across service, CLI, job, API, and UI. | **Closed.** |
| D. ASPA Operations | Mostly implemented | No change. | Provider-backed write is Krill-only by design; ARIN remains ROA-import-only. Not a structural gap. |
| E. ROA Linting and Safety Analysis | Implemented | No change. | No gap. |
| F. ROV Impact Simulation | Implemented | No change. | No gap. |
| G. Bulk Generation and Templating | **Implemented** | `BulkIntentRunViewSet` with `approve`/`approve_secondary` REST actions added. `BulkIntentRunApproveView`/`BulkIntentRunApproveSecondaryView` UI views added. | **Closed.** Governance is now fully operator-surfaced in both REST and UI. |
| H. Provider Synchronization | **Implemented** | `capability_matrix` property added to `RpkiProviderAccount` with explicit read/write/feature flags. Exposed via `RpkiProviderAccountSerializer.capability_matrix`. | **Closed.** H.6 is now explicit. |
| I. Change Control and Governance | **Implemented** | Bulk intent approval/secondary-approval operator surfaces are now present (see G). | **Closed.** |
| J. Lifecycle, Expiry, and Publication Health | Implemented | No change. | No gap. |
| K. IRR Coordination | Mostly implemented | No change. | Write-path breadth is intentionally limited by source capability mode. Not a structural gap. |
| L. External Validator and Telemetry Overlays | Implemented | No change. | No gap. |
| M. Service Context and Topology Binding | **Implemented** | `RoutingIntentContextGroup.inherits_from` FK added. `RoutingIntentPolicyBundle` model added with context_groups M2M, registry/REST/UI/GraphQL surfaces, migration `0050`. | **Closed.** M.3 inheritance and policy reuse are now first-class. |
| N. Downstream and Delegated Authorization | **Implemented** | `DelegatedAuthorizationEntity`, `ManagedAuthorizationRelationship`, `DelegatedPublicationWorkflow` models added with registry/REST/UI/GraphQL surfaces in "Delegated" navigation group, migration `0050`. | **Closed.** N.1, N.2, N.3 are all addressed. |

## Closed Gaps (detail)

### C.6 — ROA Change-Plan Creation CLI/Job Surface

- **Added**: `netbox_rpki/management/commands/create_roa_change_plan.py` — CLI entry point for creating an ROA change plan from a completed reconciliation run. Accepts `--reconciliation-run PK`, optional `--name`, optional `--enqueue`.
- **Added**: `CreateROAChangePlanJob` class in `jobs.py` — background job counterpart following the same pattern as `CreateIrrChangePlansJob`.

### H.6 — Explicit Provider Capability Matrix

- **Added** to `RpkiProviderAccount` in `models.py`:
  - `supports_roa_read` (bool property)
  - `supports_aspa_read` (bool property)
  - `supports_certificate_inventory` (bool property)
  - `supports_repository_metadata` (bool property)
  - `supports_bulk_operations` (bool property)
  - `capability_matrix` (dict property, composite of all flags)
- **Added** `capability_matrix = serializers.ReadOnlyField()` to `RpkiProviderAccountSerializer`.

### G/I — Bulk Intent Governance Operator Surfaces

- **Added** `BulkIntentRunViewSet` in `api/views.py` with `approve` and `approve_secondary` POST actions.
- **Added** `BulkIntentRunApproveActionSerializer` and `BulkIntentRunApproveSecondaryActionSerializer` in `api/serializers.py`.
- **Added** `BulkIntentRunApproveView` and `BulkIntentRunApproveSecondaryView` in `views.py`.
- **Added** URL patterns `bulkintentrun_approve` and `bulkintentrun_approve_secondary` in `urls.py`.
- **Added** template `netbox_rpki/templates/netbox_rpki/bulkintentrun_approve.html`.

### A.4 — Authored CA Hierarchy Relationship Model

- **Added** `AuthoredCaRelationshipType` and `AuthoredCaRelationshipStatus` choices in `models.py`.
- **Added** `AuthoredCaRelationship` model with org, provider_account, child/parent CA handles, relationship_type, status, service_uri, and FK links back to imported parent/child links.
- **Added** registry spec (`authoredcarelationship`) in `object_registry.py`.
- **Migration**: `0050_routingintentcontextgroup_inherits_from_and_more`.

### M.3 — Context Group Inheritance and Policy Reuse

- **Added** `RoutingIntentContextGroup.inherits_from` (nullable FK to self) with cross-organization validation in `clean()`.
- **Added** `RoutingIntentPolicyBundle` model with organization FK, `context_groups` M2M to `RoutingIntentContextGroup`, `enabled` flag, and `description`.
- **Added** registry specs (`routingintentpolicybundle`) in `object_registry.py`.
- **Updated** `routingintentcontextgroup` registry spec to include `inherits_from` in api_fields and filter_fields.
- **Migration**: `0050_routingintentcontextgroup_inherits_from_and_more`.

### N — Downstream and Delegated Authorization Models

- **Added** choices: `DelegatedAuthorizationEntityKind`, `ManagedAuthorizationRelationshipRole`, `ManagedAuthorizationRelationshipStatus`, `DelegatedPublicationWorkflowStatus`.
- **Added** `DelegatedAuthorizationEntity` model — downstream customer/partner/delegated entity as authorization subject.
- **Added** `ManagedAuthorizationRelationship` model — org-to-entity mapping with role, status, service_uri; cross-org validation.
- **Added** `DelegatedPublicationWorkflow` model — upstream-managed publication workflow with CA handles, approval tracking, and status.
- **Added** registry specs in `object_registry.py` under navigation group "Delegated" (orders 201–203).
- **Migration**: `0050_routingintentcontextgroup_inherits_from_and_more`.

## Bottom Line

All matrix gaps are now closed at the model, registry, REST API, GraphQL, and Web UI surface level. The plugin covers A–N with explicit first-class objects and operator workflows. Remaining provider breadth limitations (ARIN as ROA-import-only, IRR write breadth) are intentional scope decisions, not structural gaps.

This analysis compares the matrix objectives to the current codebase, using the actual implementation surfaces in:

- `netbox_rpki/models.py`
- `netbox_rpki/object_registry.py`
- `netbox_rpki/views.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/graphql/schema.py`
- `netbox_rpki/services/*`
- `netbox_rpki/jobs.py`
- `netbox_rpki/management/commands/*`
- `netbox_rpki/tests/*`

The plugin is materially broader than an early-stage RPKI inventory plugin. The registry currently drives 95 object specs, with 56 explicitly read-only reporting surfaces. Most of sections A-L are present in code, but several matrix items still overstate completeness.

## Executive Summary

The codebase is strongest in these areas:

- registry-driven UI, REST, and GraphQL surfaces
- standards-aligned schema expansion beyond certificates and ROAs
- ROA and ASPA reconciliation/change-plan workflows
- ROA linting, approval gating, and ROV simulation
- lifecycle reporting and export
- IRR import/coordination/change-plan/write scaffolding
- external validator, telemetry, and overlay reporting

The main remaining gaps are:

1. Section N is effectively unimplemented. No first-class downstream, delegated-authorization, or upstream-managed publication model was found.
2. Provider abstraction is still Krill-first. ARIN remains ROA-import-only, and the capability matrix is only partially explicit in code.
3. Publication topology is broad, but authored parent/child CA authority relationships are not modeled the same way imported provider relationships are.
4. The ROA intent-to-plan workflow is not fully symmetric across service, CLI, job, API, and UI surfaces.
5. Context grouping exists, but inheritance and policy-reuse semantics are still priority-based rather than first-class.

## Section-by-Section Assessment

| Matrix Section | Status | Evidence in Code | Primary Gap |
| --- | --- | --- | --- |
| A. Standards-Aligned Data Model | Mostly implemented | `models.py` now includes `Repository`, `PublicationPoint`, `TrustAnchor`, `TrustAnchorLocator`, `TrustAnchorKey`, `EndEntityCertificate`, `SignedObject`, `Manifest`, `CertificateRevocationList`, `ASPA`, `RSC`, `RouterCertificate`, validator payload models, and imported provider families. | A.4 is only partial: authored parent/child CA authority relationships are not modeled as first-class authored objects; they exist only as imported provider observations (`ImportedParentLink`, `ImportedChildLink`). |
| B. Registry-Driven Plugin Surfaces | Implemented | `object_registry.py` defines the object-spec registry; `views.py`, `api/serializers.py`, `api/views.py`, and `graphql/schema.py` generate surfaces from it; `tests/test_api.py` includes registry contract checks. | No material structural gap found. |
| C. Intent-to-ROA Reconciliation | Mostly implemented | `services/routing_intent.py` covers derivation, reconciliation, drift classification, and `create_roa_change_plan`; surfaces exist in REST and UI; `run_routing_intent_profile.py` and `RunRoutingIntentProfileJob` cover execution. | C.6 is partial: the run pipeline has command/job coverage, but ROA change-plan creation itself is surfaced only through service, REST, UI, and bulk-run orchestration, not a dedicated management command or job. |
| D. ASPA Operations | Mostly implemented | `ASPA`, `ASPAIntent`, `ASPAReconciliationRun`, `ASPAChangePlan`, `ASPAChangePlanItem`, provider sync, provider write, REST, GraphQL, and UI surfaces are present. | The workflow is structurally present, but provider-backed write support is effectively Krill-only, so D.4 and D.5 inherit the provider limitations from section H. |
| E. ROA Linting and Safety Analysis | Implemented | `ROALintRun`, `ROALintFinding`, `ROALintAcknowledgement`, `ROALintSuppression`, `ROALintRuleConfig`, `services/roa_lint.py`, approval gating in `services/provider_write.py`, and REST/UI actions are present. | No major matrix gap found. |
| F. ROV Impact Simulation | Implemented | `ROAValidationSimulationRun`, `ROAValidationSimulationResult`, `services/rov_simulation.py`, API/UI simulate actions, approval gating, approval audit capture, and dashboard/API rollups are present. | No major matrix gap found for the ROA-specific scope defined in section F. |
| G. Bulk Generation and Templating | Mostly implemented | `RoutingIntentTemplate*`, `RoutingIntentException`, `BulkIntentRun*`, `services/routing_intent.py`, `services/bulk_routing_intent.py`, API/UI organization actions, and dashboard rollups are present. | Governance is only partially surfaced: `services/bulk_intent_governance.py` exists, but equivalent API/UI approval actions for bulk runs were not found. |
| H. Provider Synchronization | Partial | Shared sync family model is present, with `ProviderSnapshot`, `ProviderSnapshotDiff`, `ExternalObjectReference`, imported family models, `services/provider_sync.py`, `provider_sync_krill.py`, and `provider_sync_contract.py`. | H.2 and H.6 are only partial: Krill is broad, ARIN is ROA-import-only, and the capability matrix is split between `supported_sync_families()` and a few write flags instead of an explicit per-account capability surface like `supports_roa_read`, `supports_aspa_read`, `supports_repository_metadata`, `supports_bulk_operations`, etc. |
| I. Change Control and Governance | Mostly implemented | ROA/ASPA change-plan lifecycles, approval records, secondary approval, maintenance metadata, provider write executions, rollback bundles, exception approvals, governance rollups, and dashboard coverage are present. | Bulk intent governance is counted in rollups but not fully operator-surfaced; this is the main remaining governance mismatch. |
| J. Lifecycle, Expiry, and Publication Health | Implemented | `LifecycleHealthPolicy`, `LifecycleHealthHook`, `LifecycleHealthEvent`, lifecycle reporting services, JSON/CSV export, provider timelines, publication-diff summaries, and operations dashboard sections are present. | No major matrix gap found. |
| K. IRR Coordination | Mostly implemented | `IrrSource`, `IrrSnapshot`, imported IRR object families, `IrrCoordinationRun`, `IrrCoordinationResult`, `IrrChangePlan`, `IrrWriteExecution`, services, jobs, management commands, REST, and UI coverage are present. | The write path is capability-gated by source mode, so full automation depends on adapter support; the audit model exists, but execution breadth is intentionally limited by source capability. |
| L. External Validator and Telemetry Overlays | Implemented | `ValidatorInstance`, `ValidationRun`, `ObjectValidationResult`, `TelemetrySource`, `TelemetryRun`, `BgpPathObservation`, overlay correlation/reporting services, REST serializers, GraphQL overlay summaries, and dashboard attention items are present. | No major matrix gap found. |
| M. Service Context and Topology Binding | Partial | Context scoping exists across tenant, VRF, site, region, provider account, circuit/provider, tags, and custom fields; `RoutingIntentContextGroup` and `RoutingIntentContextCriterion` are implemented and used in `services/routing_intent.py`. | M.3 is not fully met: grouping and precedence exist, but inheritance and reusable policy layering are not modeled as first-class semantics. |
| N. Downstream and Delegated Authorization | Missing | No downstream/delegated authorization model family, managed-customer relationship model, or upstream-managed publication workflow was found in `models.py` or service surfaces. | N.1, N.2, and N.3 remain open. |

## Highest-Priority Gaps

### 1. Downstream and Delegated Authorization Is Missing

This is the clearest matrix-to-code gap. The current schema models organizations, providers, intent, and publication state, but it does not model:

- downstream customers as delegated authorization subjects distinct from the local organization
- managed-authorization relationships
- upstream-managed publication workflows

Impact:

- Section N is still open.
- Some real-world hosted or delegated RPKI operating models cannot be represented cleanly.

### 2. Provider Capability Modeling Is Incomplete

The code has useful capability signals:

- `RpkiProviderAccount.supports_roa_write`
- `RpkiProviderAccount.supports_aspa_write`
- `services/provider_sync_contract.py::supported_sync_families()`
- family-specific limitation metadata in `family_capability_extra()`

What is still missing relative to the matrix:

- a single explicit capability matrix on the provider account or adapter contract
- explicit read capabilities parallel to the write capabilities
- stable capability flags for repository metadata, certificate inventory quality, and bulk operations

Impact:

- Section H is functionally implemented but not fully normalized.
- Some provider-specific behavior still leaks into core logic and reporting semantics.

### 3. Authored CA Relationship Topology Is Weaker Than Imported Topology

The plugin now models repositories, publication points, and imported parent/child CA relationships. What it does not model equally well is authored parent/child CA authority as a first-class local graph.

Impact:

- A.4 is only partially met.
- The provider-imported topology is richer than the authored topology.

### 4. ROA Workflow Surface Parity Is Not Complete

For ROA intent and reconciliation:

- service layer exists
- REST exists
- web UI exists
- a management command and background job exist for running derivation and reconciliation

What is missing:

- equivalent dedicated CLI/job entry points for single-run change-plan creation and later operator stages

Impact:

- C.6 is only mostly true, not fully true.

### 5. Policy Reuse Relies on Grouping and Priority, Not Inheritance

The context system is substantial, but it does not yet expose explicit inheritance or layered reuse semantics.

Impact:

- M.1 and M.2 are in good shape.
- M.3 remains partial.

## Secondary Gaps

- Bulk intent governance is modeled and summarized, but approval/secondary-approval workflows are service-only rather than fully exposed through operator surfaces.
- Provider breadth is intentionally narrow. Krill is the real backend; ARIN remains a limited adapter rather than a peer implementation.
- IRR write support is structurally present, but practical execution breadth depends on source capability mode and adapter maturity.

## Recommended Next Steps

1. Add a first-class downstream/delegation model family before expanding more provider workflows. This is the largest structural omission.
2. Normalize provider capabilities into a single adapter/account contract with explicit read/write/family flags.
3. Add authored parent/child CA relationship models or an authored CA hierarchy abstraction aligned with the imported topology.
4. Close the ROA workflow parity gap with a dedicated change-plan creation command and, if needed, a queued job path.
5. Decide whether bulk intent approval is intended to remain internal/service-only or should be surfaced in REST and web UI.
6. Define whether M.3 requires true inheritance, template composition, or reusable policy bundles, then model that explicitly instead of relying only on priority ordering.

## Bottom Line

The matrix should not be read as mostly aspirational anymore. The current plugin already implements most of A-L and much of M in real code, tests, and operator surfaces. The remaining work is concentrated in a smaller number of structural gaps: delegated/downstream authorization, provider capability normalization, authored CA topology completeness, workflow surface parity, and explicit policy inheritance semantics.
