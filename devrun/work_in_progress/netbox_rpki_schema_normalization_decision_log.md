# NetBox RPKI Plugin: Schema Normalization Decision Log

Prepared: April 13, 2026

## Purpose

This document records the field-mapping and compatibility decisions made so far while implementing the section 9.11 normalization plan.

The goal is to keep the lead agent and future workers aligned on what has already been decided, what has already been implemented, what has intentionally been deferred, and which compatibility rules are in force.

## Progress Snapshot

Implemented through this checkpoint:

1. `0024_schema_normalization_phase0.py`
   - `CertificateRevocationList.signed_object`
   - `ImportedCertificateObservation.publication_point`
   - `ImportedCertificateObservation.signed_object`
   - provider-sync population of those imported observation links
2. `0025_router_certificate_ee_link.py`
   - `RouterCertificate.ee_certificate`
   - best-effort backfill for compatible existing rows
3. `0026_roa_signed_object_normalization.py`
   - intentional `Roa.signed_object` backfill and guardrails
4. `0027_validated_payload_object_validation_links.py`
   - `ValidatedRoaPayload.object_validation_result`
   - `ValidatedAspaPayload.object_validation_result`
5. `0028_imported_publication_authored_links.py`
   - `ImportedPublicationPoint.authored_publication_point`
   - `ImportedSignedObject.authored_signed_object`
6. certificate-role cleanup without a new migration
   - `EndEntityCertificate.clean()` and `SignedObject.clean()` guardrails
   - explicit generated-surface exposure for certificate role relationships
   - explicit detail semantics for `Certificate` and `EndEntityCertificate`
7. broader `SignedObject` surface cleanup without a new migration
   - explicit `SignedObject` detail semantics
   - additive API exposure of normalized reverse relationships
   - additive GraphQL exposure of normalized reverse relationships

Verification status at this checkpoint:

- focused model, provider-sync, API, GraphQL, and view suites have been exercised repeatedly as each slice landed
- `manage.py makemigrations --check --dry-run netbox_rpki` is clean after the latest slice
- the full plugin suite most recently passed with 401 tests after certificate-role cleanup
- the latest `SignedObject` surface slice passed focused view/API/GraphQL verification and then a broader API/GraphQL/view run with 270 tests
- the first-wave release-gate rerun is now clean:
  - `manage.py makemigrations --check --dry-run netbox_rpki`
  - `manage.py test --keepdb --noinput netbox_rpki --verbosity 1`
  - full plugin suite result: 412 tests passed

## Phase 0 Decisions

### 1. Legacy `Roa` remains in place for the first normalization wave

Decision:

- keep `Roa` and `RoaPrefix` as active legacy objects
- do not rename routes, API basenames, or GraphQL field names in the first wave
- use additive normalization around `SignedObject` rather than replacing `Roa` immediately

Reason:

- this keeps the first schema slice migration-safe
- it avoids destabilizing the generated surface contract while the shared object semantics are still being normalized

### 2. CRLs should follow the same extension pattern as other `SignedObject` families

Decision:

- add an optional `CertificateRevocationList.signed_object` relationship
- treat this as the first concrete step toward bringing CRLs onto the same extension pattern already used by `Manifest`, `ASPA`, `RSC`, and `TrustAnchorKey`

Reason:

- section 9.6 identified CRLs as one of the remaining seams where the generic signed-object framework is not yet uniform
- this is a low-risk additive change that improves architectural consistency immediately

Compatibility rule:

- existing CRL rows remain valid even when `signed_object` is null
- best-effort backfill is acceptable; hard failure is not

### 3. Imported certificate observations should stop being free-floating rows

Decision:

- add optional `ImportedCertificateObservation.publication_point`
- add optional `ImportedCertificateObservation.signed_object`

Reason:

- section 9.11 explicitly calls for tighter linkage between authored publication state, imported observation, and validation overlays
- imported certificate observations already carry `publication_uri` and `signed_object_uri`, so promoting those inferred relationships to explicit foreign keys is the smallest useful substrate change

Compatibility rule:

- `publication_uri` and `signed_object_uri` remain in place for compatibility and searchability
- the new foreign keys are additive and nullable
- best-effort backfill should link rows when the match is unambiguous within the same provider snapshot

### 4. Imported publication and observation linkage remains provider-snapshot-scoped

Decision:

- all new imported-observation links must resolve within the same `ProviderSnapshot`

Reason:

- that matches the existing imported-object identity model
- it avoids accidental cross-snapshot joins that would blur retained historical state

## Completed Normalization Slices

### Initial schema substrate

Included in this slice:

1. `CertificateRevocationList.signed_object`
2. `ImportedCertificateObservation.publication_point`
3. `ImportedCertificateObservation.signed_object`
4. best-effort migration backfills for the new links
5. provider-sync population of the new imported observation links
6. focused tests proving the new relationships are actually populated

Explicitly deferred from this slice:

- route or API contract changes exposing the new fields
- detail-page or serializer changes centered on the new fields
- legacy `Roa` surface convergence
- broader certificate-role taxonomy cleanup
- validator-overlay linkage beyond the imported observation substrate

### Subsequent landed slices

After the initial schema substrate, the following slices were also implemented:

1. router-certificate to EE-certificate normalization
   - additive `RouterCertificate.ee_certificate`
   - best-effort migration backfill
   - generated-surface exposure and focused tests
2. legacy ROA normalization through `SignedObject`
   - intentional `Roa.signed_object` validation and backfill
   - generated-surface exposure and focused tests
3. validation-overlay linkage
   - additive validated-payload links to `ObjectValidationResult`
   - best-effort migration backfill
4. authored-to-imported publication linkage
   - additive authored-link foreign keys on imported publication rows
   - provider-sync population using conservative same-organization URI matching
   - generated-surface exposure and focused tests
5. certificate-role cleanup
   - model-level relationship guardrails for `EndEntityCertificate` and `SignedObject`
   - clearer certificate detail rendering
   - explicit exposure of existing certificate role links through the generated surface
6. broader `SignedObject` surface cleanup
   - explicit `SignedObject` detail rendering for normalized reverse links
   - additive API exposure for family-specific reverse objects and normalized observation or validation collections
   - additive GraphQL exposure for those same normalized reverse relationships

## Active Compatibility Rules

Until a later normalization phase says otherwise:

- legacy public object names remain stable
- additive migrations are preferred over rewrites
- null-compatible links are acceptable during normalization
- imported observation rows may still be partially linked if source evidence is incomplete
- generated surfaces must not drift accidentally just because internal linkages improved
- legacy top-level objects remain in place even when newer normalized relationships now exist beside them
- current validation guardrails remain presence-based; sparsely populated legacy rows are still acceptable
- best-effort backfill is preferred over hard migration failure when legacy data does not match a unique normalized target

## Next Decisions To Make

The first normalization wave is now implementation-complete and release-gate clean. Any next decisions are post-wave refinement decisions rather than blockers:

1. whether the current certificate-role guardrails should tighten for newly created data in a later phase
2. whether any additional authored-to-validation direct linkage is still worth adding beyond the current object-validation and validated-payload joins
3. whether compatibility links that are now proven in practice should become stronger creation-time defaults in factories, sample data, or future import paths

## Subsequent Decisions

### 5. Router certificates should normalize through `EndEntityCertificate`, not directly through `SignedObject`

Decision:

- add optional `RouterCertificate.ee_certificate`
- treat `RouterCertificate` as a role-specific extension of an EE certificate rather than as another direct `SignedObject` extension

Reason:

- section 9.11 calls for clearer certificate-role boundaries
- router certificates are semantically specialized EE certificates, so the cleanest additive normalization step is to link them to `EndEntityCertificate`
- this preserves the existing `RouterCertificate` surface while making the certificate taxonomy more explicit

Compatibility rule:

- existing router certificate rows remain valid when `ee_certificate` is null
- best-effort backfill is acceptable only when a single EE certificate matches the same organization, resource certificate, publication point, and available certificate identity fields

### 6. Legacy `Roa` should normalize through its existing `SignedObject` compatibility link

Decision:

- keep `Roa` as a legacy top-level object
- treat `Roa.signed_object` as the normalization seam for shared object semantics
- add validation and best-effort backfill around that existing relationship rather than replacing `Roa`

Reason:

- section 9.11 explicitly calls for `SignedObject` convergence while keeping legacy `Roa` usable in the first wave
- the field already exists, so the next useful step is to make it intentional data instead of an optional, mostly-unused pointer

Compatibility rule:

- existing ROA rows remain valid when `signed_object` is null
- best-effort backfill is acceptable only when a single ROA-type signed object matches the same signing certificate and any available date constraints

### 7. Validated payload rows should link to the object-level validation result that evaluated the same signed object

Decision:

- add optional `ValidatedRoaPayload.object_validation_result`
- add optional `ValidatedAspaPayload.object_validation_result`

Reason:

- section 9.11 calls for authored publication state and validation overlays to connect through intentional relationships
- `ValidatedRoaPayload` and `ValidatedAspaPayload` already identify the authored object and the validation run, while `ObjectValidationResult` identifies the signed object and the same run
- explicit linkage removes the need to infer “which object validation row evaluated the object behind this payload”

Compatibility rule:

- existing validated payload rows remain valid when `object_validation_result` is null
- best-effort backfill is acceptable only when the validation run and authored object's signed object identify a single object validation result

### 8. Imported publication-observation rows should link directly to authored publication objects when identity is clear

Decision:

- add optional `ImportedPublicationPoint.authored_publication_point`
- add optional `ImportedSignedObject.authored_signed_object`
- populate those links in provider sync when a unique authored object matches the same organization and repository identity
- keep imported rows distinct from authored rows; this is linkage, not deduplication

Reason:

- section 9.11 calls for authored publication state, imported publication observation, and validation overlays to connect through intentional relationships
- the imported layer already has stable URI-based identity that can often be matched safely to authored `PublicationPoint` and `SignedObject` rows
- explicit linkage makes it possible to traverse from authored publication objects to imported repository evidence without inferring that relationship indirectly through loose URI comparisons

Compatibility rule:

- existing imported rows remain valid when `authored_publication_point` or `authored_signed_object` is null
- best-effort backfill is acceptable only when a unique authored publication point or signed object matches the same organization and URI-based identity
- URI identity fields remain in place for compatibility, diffing, and forensic inspection even when the explicit authored link is populated

### 9. Certificate-role cleanup should prefer relationship guardrails and surface clarity over a new certificate-purpose discriminator

Decision:

- keep the current multi-model split among `Certificate`, `EndEntityCertificate`, and `RouterCertificate`
- do not add a new certificate-purpose enum or discriminator field in the first normalization wave
- add model-level guardrails so `EndEntityCertificate` and `SignedObject` must stay consistent with their linked resource certificate, publication point, and organization when those links are populated
- expose existing `Certificate.trust_anchor` and `Certificate.publication_point` relationships through the generated plugin surface
- give `Certificate` and `EndEntityCertificate` explicit detail semantics that show their role relationships rather than relying only on generic generated details

Reason:

- section 9.11 calls for clearer certificate-role boundaries, but the repo already has the essential role split in separate models
- the main remaining problem is not missing taxonomy objects; it is that the relationships among those objects are only partly enforced and only partly visible at the surface layer
- additive guardrails and clearer detail surfaces improve correctness and navigability without forcing a schema reset or a new discriminator migration

Compatibility rule:

- existing top-level object names, URLs, API basenames, and GraphQL field names remain stable
- no new certificate-purpose field is introduced in this phase
- validation only constrains rows when the relevant related objects are already present; sparse legacy rows remain usable

### 10. `SignedObject` surface cleanup should expose normalized reverse relationships explicitly rather than relying on generic rendering

Decision:

- give `SignedObject` an explicit detail spec
- expose family-specific reverse relationships such as legacy ROA, manifest, CRL, trust-anchor-key, ASPA, and RSC links through additive API and GraphQL fields
- expose normalized observation and validation traversal from `SignedObject` to imported signed-object observations and object-validation results
- keep the existing route names, list views, filter contract, and editable form contract stable

Reason:

- section 9.11 calls for object-family semantics to converge around `SignedObject`, but before this slice the signed-object record itself still behaved like a generic bucket in the UI and API
- the schema links already existed; the missing piece was first-class traversal from the normalized object outward to its family-specific and observation or validation relationships
- additive surface exposure makes the normalization visible and testable without forcing a contract reset

Compatibility rule:

- no public names are renamed
- the new API and GraphQL fields are additive only
- editable forms and route structure remain unchanged in this slice
