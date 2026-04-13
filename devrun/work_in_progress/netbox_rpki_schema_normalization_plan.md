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

1. `Roa` still carries legacy object semantics even though it already has a compatibility link to `SignedObject`.
2. `Certificate`, `EndEntityCertificate`, and `RouterCertificate` express distinct roles, but the taxonomy is still only partly normalized.
3. Publication and observation exist in parallel but do not yet follow one clean identity and linkage model.
4. The plugin surface layer is generated from explicit model metadata, so schema changes must keep the registry contract intact.

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

Lead-owned implementation slice:

1. Add the minimum normalization fields, constraints, and compatibility hooks.
2. Add or adjust factory helpers and registry scenarios so later workers can use the new shape.
3. Keep all public naming stable.

Exit criteria:

- migrations apply cleanly
- object factories and registry scenarios can build the new shape
- no surface contract has been widened accidentally

### Phase 2: Open Parallel Surface Work

Parallel worker slices:

1. Track B: `SignedObject` convergence at the surface layer.
2. Track C: certificate-role cleanup at the surface layer.
3. Track D: publication/import/validation linkage normalization.
4. Track F: contract-test expansion and doc updates for the slices above.

Exit criteria:

- each worker returns a bounded patch set with tests
- no worker edits `models.py` or migrations unless reassigned by the lead

### Phase 3: Integration and Hardening

Lead-owned integration slice:

1. Merge the worker outputs.
2. Resolve any conflicts in detail specs, serializers, GraphQL types, or tests.
3. Finish Track E migration and compatibility hardening.
4. Update the backlog and supporting docs.

Exit criteria:

- the normalized relationships are reflected consistently in model, service, and surface layers
- compatibility behavior is explicit, not accidental

### Phase 4: Release-Gate Verification

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
