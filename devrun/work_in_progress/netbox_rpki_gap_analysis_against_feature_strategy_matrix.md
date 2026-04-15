# netbox_rpki Gap Analysis Against Feature Strategy Matrix

## Scope

This is a code-inspection gap analysis of the current `netbox_rpki` repository against [netbox_rpki_feature_strategy_matrix.md](./netbox_rpki_feature_strategy_matrix.md).

Primary evidence reviewed:

- `netbox_rpki/models.py`
- `netbox_rpki/object_registry.py`
- `netbox_rpki/views.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/graphql/{schema,types,filters}.py`
- `netbox_rpki/services/*.py`
- `netbox_rpki/jobs.py`
- `netbox_rpki/tests/*.py`
- `LOCAL_DEV_SETUP.md`
- `CONTRIBUTING.md`

Status meanings used here:

- `Implemented`: code, surfaces, and tests appear to cover the objective end-to-end.
- `Mostly implemented`: the objective is largely present, but there is an architectural, workflow, or completeness gap.
- `Partial`: the schema or some surfaces exist, but the operational/service-layer behavior is not yet there.
- `Gap`: I did not find meaningful implementation evidence.

## Executive Summary

The plugin is already far beyond a narrow ROA reconciliation tool. Domains B through M are broadly present, with especially strong end-to-end coverage for registry-driven surfaces, ROA/ASPA workflows, governance, lifecycle reporting, external validation, telemetry overlays, and IRR coordination.

The main remaining strategic gap is domain N, where delegated/downstream authorization is modeled and exposed through the generated surfaces, but is not yet integrated into the service layer or operator workflows. There are also a few secondary completeness gaps: the standards-aligned model layer has some convention inconsistency in older/core models, provider-gated development guidance is documented more than enforced, and IRR coordination is still operationally centered on route-object drift rather than richer IRR set policy automation.

## Domain Summary

| Domain | Status | Notes |
|---|---|---|
| A. Standards-Aligned Data Model | Mostly implemented | The object graph is extensive and includes `Certificate`, `EndEntityCertificate`, `SignedObject`, `Manifest`, `CertificateRevocationList`, `ASPA`, `RSC`, `RouterCertificate`, `Repository`, `PublicationPoint`, `TrustAnchor`, `TrustAnchorLocator`, `TrustAnchorKey`, validated payloads, and delegated-auth models. The main gap is convention consistency rather than missing object families. |
| B. Registry-Driven Plugin Surfaces | Implemented | `object_registry.py` drives UI, API, GraphQL, filters, forms, tables, navigation, and mutability. Contract tests in `test_views.py`, `test_api.py`, `test_graphql.py`, `test_urls.py`, and `test_navigation.py` explicitly iterate the registry. |
| C. Intent-to-ROA Reconciliation | Implemented | `services/routing_intent.py`, ROA reconciliation models, commands, jobs, API actions, and UI flows cover intent derivation through change-plan generation. |
| D. ASPA Operations | Implemented | ASPA inventory, import, intent/reconciliation, change plans, provider-backed write flow, API actions, and UI views are all present. |
| E. ROA Linting and Safety Analysis | Implemented | Lint runs/findings, suppressions, acknowledgements, rule config overrides, approval gating, and API/UI exposure are implemented and heavily tested. |
| F. ROV Impact Simulation | Implemented | `services/rov_simulation.py` plus approval integration, persisted runs/results, and dashboard rollups cover this domain end-to-end. |
| G. Bulk Generation and Templating | Implemented | Templates, bindings, exceptions, overrides, queued regeneration, bulk runs, governance, and dashboard rollups are present. |
| H. Provider Synchronization | Mostly implemented | The provider contract, Krill adapter, ARIN ROA import, durable external identities, diffs, summaries, and capability matrix are all implemented. The remaining gap is more about real live-backend enforcement and broader provider depth than core architecture. |
| I. Change Control and Governance | Implemented | Multi-stage change plans, secondary approval, ticket/maintenance metadata, approval records, write audit rows, rollback bundles, exception approval, and dashboard rollups are in place. |
| J. Lifecycle, Expiry, and Publication Health | Implemented | Policies, hooks, events, lifecycle summaries, publication timelines, diff visibility, exports, and dashboard surfacing are implemented. |
| K. IRR Coordination | Mostly implemented | IRR sources, snapshots, imported objects, coordination runs/results, change plans, and write executions are present. Current automation is strong for route-object coordination, with richer IRR set automation still limited. |
| L. External Validator and Telemetry Overlays | Implemented | Validator sync, telemetry sync, unified overlay correlation, and dashboard/change-review surfacing are implemented. |
| M. Service Context and Topology Binding | Implemented | Intent derivation binds to tenant/VRF/site/region/tag/custom-field-like selectors, context groups, criteria, and inheritance semantics. |
| N. Downstream and Delegated Authorization | Partial | The schema and generated surfaces exist, but I did not find service-layer behavior that uses these models in intent, provider sync/write, or publication workflows. |

## Detailed Gap Notes

### A. Standards-Aligned Data Model

Status call:

- `A.1` through `A.5`: `Implemented`
- `A.6`: `Mostly implemented`
- `A.7`: `Implemented`

Evidence:

- `models.py` contains explicit classes for the matrix’s required object families, including trust-anchor and signed-object related types.
- `SignedObjectType` and dependent model relationships indicate a deliberate shared signed-object spine.
- Distinct certificate-role models exist, including `Certificate`, `EndEntityCertificate`, and `RouterCertificate`.
- Publication topology is represented by `Repository`, `PublicationPoint`, authored/imported CA metadata, parent/child links, and authored CA relationship models.
- `ValidatedRoaPayload` and `ValidatedAspaPayload` are first-class objects linked to validation artifacts.

Gap:

- `A.6` is not perfectly uniform. Many models use `RpkiStandardModel` / `NamedRpkiStandardModel`, but some earlier/core models still inherit `NetBoxModel` directly and manually repeat `comments`/`tenant`. That is not a user-facing feature gap, but it is still an architectural inconsistency against the “all models follow conventions” objective.

### B. Registry-Driven Plugin Surfaces

Status call:

- `B.1` through `B.7`: `Implemented`

Evidence:

- `object_registry.py` defines the object-spec inventory and derived spec subsets.
- `views.py`, `urls.py`, `navigation.py`, `forms.py`, `filtersets.py`, `tables.py`, `api/serializers.py`, `api/views.py`, `api/urls.py`, `graphql/types.py`, `graphql/filters.py`, and `graphql/schema.py` all consume the registry.
- Read-only mutability rules are explicitly enforced in generated views and API viewsets.
- Registry-loop tests in `test_views.py`, `test_api.py`, `test_graphql.py`, `test_urls.py`, and `test_navigation.py` validate surface behavior.

No significant strategic gap found in this domain.

### C. Intent-to-ROA Reconciliation

Status call:

- `C.1` through `C.6`: `Implemented`

Evidence:

- `services/routing_intent.py` covers deterministic derivation from NetBox IPAM and routing context.
- Reconciliation compares against local authored ROAs and imported provider state.
- Drift classification and persistence models exist for reconciliation runs, intent results, and published results.
- Draft change-plan creation exists in the service layer and is exposed through commands, jobs, API actions, and UI templates/views.

No significant strategic gap found in this domain.

### D. ASPA Operations

Status call:

- `D.1` through `D.5`: `Implemented`

Evidence:

- ASPA authored/imported models and provider constraints exist in `models.py`.
- Import is handled through provider sync.
- `services/aspa_intent.py`, `services/aspa_change_plan.py`, and `services/provider_write.py` cover intent, reconciliation, change-plan generation, preview, approval, apply, and rollback.
- API and UI actions are present in `api/views.py` and `views.py`.

No significant strategic gap found in this domain.

### E. ROA Linting and Safety Analysis

Status call:

- `E.1` through `E.7`: `Implemented`

Evidence:

- `ROALintRun`, `ROALintFinding`, `ROALintAcknowledgement`, `ROALintSuppression`, and `ROALintRuleConfig` exist in `models.py`.
- `services/roa_lint.py` implements lint evaluation, suppression and acknowledgement posture, carry-forward handling, and approval gating.
- Forms, API serializers/actions, and UI templates exist for acknowledgement and suppression workflows.
- `test_roa_lint.py` and `test_provider_write.py` provide broad behavioral coverage.

No significant strategic gap found in this domain.

### F. ROV Impact Simulation

Status call:

- `F.1` through `F.5`: `Implemented`

Evidence:

- `services/rov_simulation.py` persists runs/results, computes predicted outcomes, records approval impacts, and blocks approval when necessary.
- `ApprovalRecord.simulation_review_json` is exercised in API/UI approval tests.
- Dashboard and aggregate summaries in `views.py` surface simulation posture and counts.

No significant strategic gap found in this domain.

### G. Bulk Generation and Templating

Status call:

- `G.1` through `G.7`: `Implemented`

Evidence:

- Template, rule, binding, exception, override, bulk-run, and scope-result models are present.
- `services/routing_intent.py`, `services/bulk_routing_intent.py`, and `services/bulk_intent_governance.py` cover compilation, queueing, and approval behavior.
- Commands, jobs, UI actions, and dashboard rollups are present and tested.

No significant strategic gap found in this domain.

### H. Provider Synchronization

Status call:

- `H.1` through `H.6`: `Implemented`
- `H.7`: `Mostly implemented`

Evidence:

- `services/provider_sync_contract.py` defines family metadata and rollups.
- `services/provider_sync.py` and `services/provider_sync_krill.py` implement Krill family imports and ARIN ROA import.
- Durable external identity is represented by `ExternalObjectReference`.
- `ProviderSnapshot`, `ProviderSnapshotDiff`, and `ProviderSnapshotDiffItem` are modeled and used.
- REST/GraphQL/web surfacing is covered by the registry and summary/detail code.
- `RpkiProviderAccount.capability_matrix` explicitly exposes the provider capability matrix required by `H.6`.

Gap:

- `H.7` is satisfied in repo guidance and test philosophy more than through strong code-level enforcement. `LOCAL_DEV_SETUP.md` clearly centers local fixtures and a Krill backend, but I did not find a strong in-repo separation that mechanically guarantees provider-gated lanes stay optional.

### I. Change Control and Governance

Status call:

- `I.1` through `I.8`: `Implemented`

Evidence:

- ROA and ASPA change plans support draft, approval, apply, failure, and rollback states.
- Secondary approval is implemented for bulk runs and change plans.
- Maintenance windows, ticket references, change references, and actor attribution are present on plans and approvals.
- `ApprovalRecord` and provider write execution models persist governance and audit metadata.
- Rollback bundles exist for ROA and ASPA.
- Routing-intent exceptions require approval before taking effect in `services/routing_intent.py`.
- Dashboard rollups in `views.py` and governance summary services expose aggregate posture.

No significant strategic gap found in this domain.

### J. Lifecycle, Expiry, and Publication Health

Status call:

- `J.1` through `J.6`: `Implemented`

Evidence:

- `LifecycleHealthPolicy`, `LifecycleHealthHook`, and `LifecycleHealthEvent` exist and are surfaced through generated/plugin-specific views and APIs.
- `services/lifecycle_reporting.py` implements lifecycle summaries, timelines, publication-health rollups, and JSON/CSV export responses.
- The operations dashboard consumes lifecycle and provider-health rollups.

No significant strategic gap found in this domain.

### K. IRR Coordination

Status call:

- `K.1` through `K.5`: `Mostly implemented`

Evidence:

- `IrrSource`, `IrrSnapshot`, imported IRR object models, `IrrCoordinationRun`, `IrrCoordinationResult`, `IrrChangePlan`, `IrrChangePlanItem`, and `IrrWriteExecution` are all modeled.
- `services/irr_sync.py`, `services/irr_coordination.py`, and `services/irr_write.py` implement import, mismatch analysis, draft planning, preview, and apply.
- Commands, jobs, tests, and dashboard attention surfacing exist.
- The IRR workflow is not wired as a blocker for the ROA/ASPA approval path, which matches `K.5`.

Gap:

- Current coordination and write automation is strongest for route-object drift. Imported route-set and AS-set inventory exists, and those families are represented in enums/summary shapes, but I did not find equivalent operational logic producing coordination results or actionable change-plan items for those set families.

### L. External Validator and Telemetry Overlays

Status call:

- `L.1` through `L.4`: `Implemented`

Evidence:

- `ValidatorInstance`, `ValidationRun`, `ObjectValidationResult`, `TelemetrySource`, `TelemetryRun`, and `BgpPathObservation` are modeled.
- `services/external_validation.py`, `services/bgp_telemetry.py`, `services/overlay_correlation.py`, `services/overlay_history.py`, and `services/overlay_reporting.py` provide correlation and operational summaries.
- Dashboard and serializer/view coverage expose these overlays in operator-facing surfaces.

No significant strategic gap found in this domain.

### M. Service Context and Topology Binding

Status call:

- `M.1` through `M.3`: `Implemented`

Evidence:

- Routing intent binds to tenant, VRF, site, region, tags, selector queries, and scoped exceptions/overrides.
- `RoutingIntentContextGroup` and `RoutingIntentContextCriterion` provide reusable context scoping.
- Context-group inheritance exists and is validated in the model layer.

No significant strategic gap found in this domain.

### N. Downstream and Delegated Authorization

Status call:

- `N.1` through `N.3`: `Partial`

Evidence:

- `DelegatedAuthorizationEntity`, `ManagedAuthorizationRelationship`, `DelegatedPublicationWorkflow`, and `AuthoredCaRelationship` are modeled.
- They are also registered in `object_registry.py`, which means they inherit generated UI/API/GraphQL surfaces.

Gap:

- I did not find service-layer consumers for these models in routing intent, provider sync, provider write, lifecycle, IRR, or validation workflows.
- I did not find targeted behavioral tests beyond registry scenario coverage.
- As implemented today, this domain looks like a schema-and-surface foundation for future work rather than an operationally integrated capability.

## Recommended Backlog Focus

Highest-value gaps exposed by this analysis:

1. Integrate domain N into actual workflows.
   Start by deciding whether delegated/downstream entities should affect intent derivation, provider-account scoping, authored CA relationships, or publication workflows first.

2. Decide whether IRR coordination should expand beyond route-object drift.
   Route-set and AS-set support is modeled, but not yet operationally coordinated.

3. Tighten model-convention consistency in domain A.
   This is lower urgency than the workflow gaps, but it would reduce architectural drift.

4. Decide whether provider-gated live-backend lanes need stronger enforcement.
   The development guidance is clear, but the enforcement is mostly social/documentary.
