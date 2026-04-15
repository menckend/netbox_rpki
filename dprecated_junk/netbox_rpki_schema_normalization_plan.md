# NetBox RPKI Plugin: Schema Normalization Plan

Prepared: April 13, 2026

## Objective

Implement the backlog section 9.11 direction as a compatibility-preserving normalization effort rather than a second schema reset.

The goal is to make the existing standards-aligned model families behave as one coherent architecture across:

- legacy authored objects such as `Certificate` and `Roa`
- standards-oriented object families such as `SignedObject`, `EndEntityCertificate`, `Manifest`, `CertificateRevocationList`, `TrustAnchorKey`, `ASPA`, `RSC`, and `RouterCertificate`
- imported publication-observation families such as `ImportedPublicationPoint`, `ImportedSignedObject`, and `ImportedCertificateObservation`
- validation-overlay families such as `ValidationRun`, `ObjectValidationResult`, `ValidatedRoaPayload`, and `ValidatedAspaPayload`

The execution target is a schema and surface model that cleanly expresses the five-layer architecture already emerging in the codebase:

1. authority
2. publication
3. object
4. integrity
5. validation

## Status Snapshot

Current execution status as of April 13, 2026:

- Phase 0 is complete.
- Phase 1 is complete and has expanded into several additive schema slices rather than one monolithic migration.
- Phase 2 has been executed in serialized lead-owned slices instead of true parallel sub-agent waves because the shared surface files proved too conflict-prone.
- Phase 3 is complete for the first normalization wave.
- Phase 4 is complete for the first normalization wave.

Landed normalization slices:

1. `0024_schema_normalization_phase0.py`
   - `CertificateRevocationList.signed_object`
   - `ImportedCertificateObservation.publication_point`
   - `ImportedCertificateObservation.signed_object`
2. `0025_router_certificate_ee_link.py`
   - `RouterCertificate.ee_certificate`
3. `0026_roa_signed_object_normalization.py`
   - intentional `Roa.signed_object` normalization
4. `0027_validated_payload_object_validation_links.py`
   - `ValidatedRoaPayload.object_validation_result`
   - `ValidatedAspaPayload.object_validation_result`
5. `0028_imported_publication_authored_links.py`
   - `ImportedPublicationPoint.authored_publication_point`
   - `ImportedSignedObject.authored_signed_object`
6. non-migration certificate-role cleanup
   - model-level `EndEntityCertificate` and `SignedObject` guardrails
   - explicit generated-surface exposure of certificate role relationships
   - explicit detail semantics for `Certificate` and `EndEntityCertificate`
7. non-migration `SignedObject` surface cleanup
   - explicit `SignedObject` detail semantics
   - additive API exposure for normalized reverse relationships
   - additive GraphQL exposure for normalized reverse relationships

Current next seam:

- no remaining code seam is required to close the first normalization wave
- any next work is post-wave refinement or a second normalization wave, not a release-gate blocker

## Scope

In scope:

- additive schema normalization in `netbox_rpki/models.py`
- additive migrations, backfills, and compatibility shims
- convergence of shared object semantics around `SignedObject`
- cleaner certificate-role boundaries across `Certificate`, `EndEntityCertificate`, and `RouterCertificate`
- clearer linkage between authored publication state, imported publication observation, and validation overlays
- registry, UI, API, GraphQL, and test-surface updates required to keep the plugin contract coherent
- updates to backlog and implementation notes that explain the normalized target state

## Non-Goals

Not in scope for this plan:

- destructive renames of public routes, API basenames, or GraphQL field names in the first wave
- removal of legacy `Certificate` or `Roa` in the first wave
- a full relying-party validator implementation
- new provider adapters beyond the normalization needed to support authored/imported/validated linkage
- a full RRDP session-history subsystem unless it is directly required by the normalization work
- a monolithic rewrite that lands all schema cleanup in one change

## Current-State Baseline

The current codebase already contains most of the target architecture.

Legacy anchors:

- `Certificate` in `netbox_rpki/models.py`
- `Roa` and `RoaPrefix` in `netbox_rpki/models.py`

Standards-oriented schema spine:

- `Repository`
- `PublicationPoint`
- `TrustAnchor`
- `TrustAnchorLocator`
- `EndEntityCertificate`
- `SignedObject`
- `CertificateRevocationList`
- `RevokedCertificate`
- `Manifest`
- `ManifestEntry`
- `TrustAnchorKey`
- `ASPA`
- `RSC`
- `RouterCertificate`
- `ValidatorInstance`
- `ValidationRun`
- `ObjectValidationResult`
- `ValidatedRoaPayload`
- `ValidatedAspaPayload`

Imported observation and sync layer:

- `ImportedPublicationPoint`
- `ImportedSignedObject`
- `ImportedCertificateObservation`
- provider-sync family contracts in `netbox_rpki/services/provider_sync_contract.py`
- provider-sync diff logic in `netbox_rpki/services/provider_sync_diff.py`

Primary seams to normalize:

1. `Roa` now has an intentional compatibility path through `SignedObject`, but broader object-family rendering is still not consistently centered on normalized signed-object semantics.
2. `Certificate`, `EndEntityCertificate`, and `RouterCertificate` now have clearer additive role boundaries, but the surface layer still needs more deliberate `SignedObject`-family presentation.
3. Publication, import, and validation now have several explicit joins, but the final traversal model still needs polish so the relationships feel intentional everywhere they are rendered.
4. The plugin surface layer is generated from explicit model metadata, so every remaining normalization step must keep the registry contract intact.

Execution constraint:

- `netbox_rpki/models.py` is still monolithic. Only one worker should own `models.py` and `netbox_rpki/migrations/` in any single phase.

## Coordination Model

This plan is designed for one GPT-5.4 Codex lead agent orchestrating a flock of GPT-5.4-mini sub-agents.

Lead agent responsibilities:

- hold the overall target-state contract
- make all cross-track schema decisions
- own `netbox_rpki/models.py` and `netbox_rpki/migrations/` during schema phases
- sequence merges so that worker changes do not conflict on the critical path
- review each worker result before integration
- keep the backlog, docs, and contract checklist aligned

Mini-agent contract:

- each mini-agent gets one narrow track with a bounded write set
- each mini-agent must treat itself as not alone in the codebase and must not revert the work of others
- each mini-agent returns:
  - files changed
  - tests run
  - open risks
  - any assumptions that the lead must confirm

Parallelism rule:

- no parallel edits to `netbox_rpki/models.py`
- no parallel migration authoring
- parallel work opens only after the lead lands the schema substrate for the phase

Secondary ownership rule:

- `netbox_rpki/object_registry.py`, `netbox_rpki/detail_specs.py`, `netbox_rpki/api/serializers.py`, and `netbox_rpki/graphql/types.py` are also shared, high-conflict files
- only one worker should own that surface-file set in any active execution window
- if the lead wants to split work inside that set, the lead must first carve the change into clearly non-overlapping slices

Recommended file-ownership windows:

1. schema window
   - owner: lead agent
   - files: `netbox_rpki/models.py`, `netbox_rpki/migrations/`, `netbox_rpki/tests/utils.py`, `netbox_rpki/tests/registry_scenarios.py`
2. surface window
   - owner: one designated mini-agent or the lead
   - files: `netbox_rpki/object_registry.py`, `netbox_rpki/detail_specs.py`, `netbox_rpki/api/serializers.py`, `netbox_rpki/graphql/types.py`, related surface tests
3. provider-observation window
   - owner: one designated mini-agent
   - files: `netbox_rpki/services/provider_sync_contract.py`, `netbox_rpki/services/provider_sync_diff.py`, `netbox_rpki/tests/test_provider_sync.py`
4. docs window
   - owner: one designated mini-agent
   - files: backlog, plan, checklist, and related notes

Required handoff format for every worker:

1. scope completed
2. changed files
3. verification performed
4. blockers or follow-up items

## Workstreams

### Track A: Target-State Contract and Schema Substrate

Status:

- largely complete for the first wave
- the lead has already landed the additive schema substrate and follow-on schema slices through `0028`
- remaining work is limited to any final schema hooks needed by the next `SignedObject` surface-cleanup seam

Owner:

- GPT-5.4 lead agent or one designated schema worker under direct lead control

Primary files:

- `netbox_rpki/models.py`
- `netbox_rpki/migrations/`
- `netbox_rpki/tests/utils.py`
- `netbox_rpki/tests/registry_scenarios.py`
- this plan and related implementation notes

Objective:

- define the normalization target in executable schema terms
- decide which legacy fields stay as compatibility bridges
- add the minimum additive schema hooks needed for later parallel work

Expected outputs:

- explicit field and relationship decisions for `SignedObject` convergence
- explicit certificate-role decision points
- additive migrations and, where needed, data backfills
- no public contract breakage in the first wave

Dependency rule:

- this track must land before any surface or provider-observation worker takes ownership of follow-on implementation

### Track B: `SignedObject` Convergence

Status:

- substantially complete for the first wave
- `Roa.signed_object` has been normalized and surfaced intentionally
- explicit `SignedObject` detail, API, and GraphQL reverse traversal is now landed
- any remaining work here is compatibility polish rather than a missing normalization seam

Owner:

- one GPT-5.4-mini worker after Track A lands, using the surface window

Primary files:

- `netbox_rpki/object_registry.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/tests/test_models.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_graphql.py`

Objective:

- move shared publication, signature, and lifecycle semantics toward `SignedObject`
- reduce legacy ROA-only assumptions at the surface layer
- keep legacy `Roa` behavior working through compatibility links while the model is normalized

Expected outputs:

- clearer surface rendering of `SignedObject`-backed object families
- tests proving the normalized relationships are queryable and stable
- no route or GraphQL-name drift

Dependency rule:

- do not edit `models.py` in this track unless the lead explicitly reassigns ownership
- this track shares high-conflict files with Track C and must therefore either:
  - be executed by the same worker, or
  - be serialized ahead of Track C

### Track C: Certificate-Role Cleanup

Status:

- substantially complete for the first wave
- `RouterCertificate.ee_certificate` is landed
- certificate-role guardrails and clearer certificate detail semantics are landed
- any remaining work here is incremental tightening, not a missing first-pass implementation

Owner:

- one GPT-5.4-mini worker after Track A lands, using the surface window

Primary files:

- `netbox_rpki/object_registry.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/tests/test_models.py`
- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/registry_scenarios.py`

Objective:

- make the role boundaries among `Certificate`, `EndEntityCertificate`, and `RouterCertificate` clearer and more consistent
- expose those distinctions more cleanly in generated surfaces without breaking existing URLs or object identity

Expected outputs:

- cleaner field groupings and detail-page semantics
- tests proving that certificate-role relationships remain stable and intentional

Dependency rule:

- model-layer changes remain owned by Track A until the lead opens a new schema phase
- this track should not run concurrently with Track B unless the lead has first split the shared surface files into non-overlapping edit slices

### Track D: Publication, Import, and Validation Linkage

Status:

- substantially complete for the current plan wave
- imported certificate observations now link to imported publication and signed-object rows
- imported publication rows now link back to authored publication objects when identity is clear
- validated payload rows now link to object-level validation results
- provider-sync contract and diff logic have already been updated to preserve the new relationships

Owner:

- one GPT-5.4-mini worker after Track A lands

Primary files:

- `netbox_rpki/services/provider_sync_contract.py`
- `netbox_rpki/services/provider_sync_diff.py`
- `netbox_rpki/tests/test_provider_sync.py`

Objective:

- align authored publication state, imported observation, and validation overlays around cleaner identity and relationship rules
- keep the explicit split between control-plane and publication-observation evidence

Expected outputs:

- clearer relationship traversal from authored publication objects to imported publication evidence
- better alignment between imported certificate observation and signed-object or publication-point identity
- test coverage proving that the linkage is deliberate rather than accidental

Dependency rule:

- do not invent a second observation model; extend the current authored/imported/validated layers coherently
- any required UI, API, or GraphQL exposure changes should be handed to the active surface-window owner rather than edited in parallel here

### Track E: Migration and Compatibility Hardening

Status:

- partially complete
- additive migrations and best-effort backfills have landed through `0028`
- the remaining work is compatibility review and any final cleanup after the next `SignedObject` surface seam

Owner:

- GPT-5.4 lead agent after Tracks B through D merge

Primary files:

- `netbox_rpki/models.py`
- `netbox_rpki/migrations/`
- `netbox_rpki/tests/test_models.py`
- `netbox_rpki/tests/utils.py`

Objective:

- finish remaining additive migrations and backfills
- remove temporary ambiguity that was acceptable during intermediate slices
- ensure compatibility shims are explicit and documented

Expected outputs:

- migration-safe normalized schema
- backfills that preserve existing data semantics
- clear compatibility notes for legacy fields and relationships

### Track F: Surface Contract, Docs, and Release-Gate Hardening

Status:

- complete for the first normalization wave
- backlog updates, the decision log, and this plan have been maintained during execution
- focused and full-plugin regression runs have already been used as release-gate checks for the currently landed slices

Owner:

- one GPT-5.4-mini worker in parallel with late integration, coordinated by the lead

Primary files:

- `devrun/work_in_progress/netbox_rpki_surface_contract_checklist.md`
- `devrun/work_in_progress/netbox_rpki_enhancement_backlog.md`
- this plan

Objective:

- ensure the normalized schema still satisfies the generated-surface contract
- update implementation notes to reflect the new normalized target state

Expected outputs:

- updated release-gate and contract-check documentation for route presence, permissions, queryability, and detail rendering
- documentation that reflects the normalized architecture

Dependency rule:

- if Track F needs code changes in shared surface files, those changes must be handed back to the active surface-window owner

## Execution Phases

### Phase 0: Freeze the Contract

Status:

- complete

Completed work:

1. section 9.11 target semantics were reframed as compatibility-preserving normalization
2. the field-mapping decision log was created
3. the first additive substrate slice was defined and landed

Lead-only tasks:

1. Reconfirm the target semantics of section 9.11.
2. Write a field-mapping decision log for:
   - legacy `Roa` versus `SignedObject`
   - `Certificate` versus `EndEntityCertificate` versus `RouterCertificate`
   - authored publication versus imported publication observation versus validation overlay
3. Define the first additive migration slice.

Exit criteria:

- no unresolved ambiguity about the first schema substrate change
- worker ownership boundaries are documented

### Phase 1: Land the Schema Substrate

Status:

- complete

Completed work:

1. landed `0024_schema_normalization_phase0.py`
2. extended the substrate in subsequent additive migrations through `0028`
3. updated factories, sample data, and registry scenarios so the normalized relationships can be built intentionally

Lead-owned implementation slice:

1. Add the minimum normalization fields, constraints, and compatibility hooks.
2. Add or adjust factory helpers and registry scenarios so later workers can use the new shape.
3. Keep all public naming stable.

Exit criteria:

- migrations apply cleanly
- object factories and registry scenarios can build the new shape
- no surface contract has been widened accidentally

### Phase 2: Open Parallel Surface Work

Status:

- effectively complete for the slices already landed, but executed serially by the lead instead of in parallel mini-agent waves

Completed work:

1. surfaced the initial substrate links through the generated contract
2. surfaced router-certificate and ROA normalization links
3. updated provider-sync contract and diff behavior for the new authored/imported/validated relationships
4. expanded API, GraphQL, view, and provider-sync coverage alongside each slice

Execution note:

- the plan originally allowed parallel mini-agent work here, but the shared ownership pressure on `object_registry.py`, `detail_specs.py`, and related surface tests made serialized lead-owned slices the safer execution model

Planned worker slices for this phase:

1. Track B: `SignedObject` convergence at the surface layer.
2. Track C: certificate-role cleanup at the surface layer.
3. Track D: publication/import/validation linkage normalization.
4. Track F: contract-test expansion and doc updates for the slices above.

Adjusted execution result:

- for the currently landed slices, the lead executed the shared surface work directly in serial order
- mini-agent delegation remains appropriate only for future bounded sidecar work on disjoint files

Exit criteria:

- each worker returns a bounded patch set with tests
- no worker edits `models.py` or migrations unless reassigned by the lead

### Phase 3: Integration and Hardening

Status:

- complete for the first normalization wave

Completed work:

1. the landed slices have been integrated across model, service, and generated-surface layers
2. certificate-role guardrails and detail semantics are now explicit
3. authored/imported/validated linkage is materially more coherent than the pre-plan baseline
4. `SignedObject` now exposes normalized reverse relationships explicitly in the UI, API, and GraphQL surfaces
5. the late-phase compatibility review found no remaining first-wave blockers

Remaining work:

- any remaining work is post-wave refinement, documentation polish, or a future second-wave normalization effort

Lead-owned integration slice:

1. Merge the worker outputs.
2. Resolve any conflicts in detail specs, serializers, GraphQL types, or tests.
3. Finish Track E migration and compatibility hardening.
4. Update the backlog and supporting docs.

Exit criteria:

- the normalized relationships are reflected consistently in model, service, and surface layers
- compatibility behavior is explicit, not accidental

### Phase 4: Release-Gate Verification

Status:

- complete for the first normalization wave

Completed work:

1. focused schema, provider-sync, UI, API, and GraphQL tests have been run repeatedly throughout implementation
2. `manage.py makemigrations --check --dry-run netbox_rpki` is clean after the latest landed slice
3. the full plugin suite most recently passed after certificate-role cleanup
4. the `SignedObject` surface slice passed focused view/API/GraphQL verification and a broader API/GraphQL/view run with 270 passing tests
5. the full first-wave release gate rerun passed with 412 tests across `netbox_rpki`

Remaining work:

- none for first-wave closure

Required closure checks:

1. targeted schema and model tests pass
2. provider-sync observation tests still pass
3. registry-wide UI/API/GraphQL surface tests pass
4. full plugin suite remains green

## Verification and Acceptance

The plan is complete only when all of the following are true:

1. The explicit Django model layer reflects the normalized authority, publication, object, integrity, and validation relationships without requiring a destructive reset.
2. Legacy `Certificate` and `Roa` remain usable through explicit compatibility paths during the first normalization wave.
3. Shared publication and lifecycle semantics are more clearly centered on `SignedObject`.
4. Certificate-role boundaries are clearer and provable in tests.
5. Authored publication state, imported publication observation, and validation overlays can be traversed through intentional relationships rather than ad hoc inference.
6. UI, API, and GraphQL contracts remain stable unless a documented contract change is explicitly approved.
7. Documentation reflects the normalized architecture.

Minimum verification set:

- targeted model tests
- targeted provider-sync tests
- targeted view, API, and GraphQL surface-contract tests
- full plugin suite

Use the verification commands and release-gate expectations already documented in:

- `devrun/work_in_progress/netbox_rpki_surface_contract_checklist.md`
- `devrun/work_in_progress/netbox_rpki_testing_strategy_matrix.md`

## Risks and Rollback

Primary risks:

- `models.py` merge conflicts caused by parallel schema work
- accidental route, serializer, or GraphQL drift from registry changes
- data migrations that over-assume how existing legacy rows are populated
- subtle provider-sync regressions when publication and certificate observation linkage changes

Mitigations:

- keep one owner for `models.py` and migrations per phase
- land additive migrations before surface refactors
- preserve legacy compatibility links until all consuming surfaces are updated
- require focused regression tests for every normalized relationship change

Rollback rule:

- if a normalization slice destabilizes the public surface contract, revert only that slice and keep the additive substrate that has already proven migration-safe

## Handoff Artifacts

Every worker should produce these artifacts for the lead agent:

1. changed files list
2. one-paragraph summary of what changed
3. tests run and outcomes
4. unresolved assumptions
5. any follow-up work that must happen in a later phase

The lead agent should maintain these running artifacts during execution:

- a field-mapping table for legacy-to-normalized relationships
- a migration-order log
- a contract-change log stating whether each surface change is compatibility-preserving or intentionally public
- a merge-order checklist for Tracks A through F
