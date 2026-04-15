# Krill Publication-Point Evidence Fixture Inventory and Repository Artifact Map

Last updated: April 12, 2026

## Purpose

This note is the working inventory for Krill evidence sources that can support repository-derived observation, especially publication-point-backed artifacts. It keeps control-plane evidence separate from publication-observation evidence so later importer and test work does not confuse provider management payloads with repository contents.

This is documentation only. It does not add importer behavior and it does not invent a provider certificate inventory endpoint.

## Evidence model

### Control-plane evidence

Control-plane evidence is provider-management state returned by Krill APIs that describe the CA, its parent and child relationships, and its resource entitlements. It is useful for synchronization and linkage, but it is not the authoritative source for published certificate inventory.

Current control-plane families that are suitable Tier 1 inputs now:

| Family | Current source(s) | Current fixtures | Why Tier 1 now |
| --- | --- | --- | --- |
| `ca_metadata` | `GET /api/v1/cas/{ca}` via `krillc show --ca <ca> --api` | `KRILL_CA_METADATA_JSON` | Stable root payload for CA handle, id-cert linkage, repository linkage, resources, parents, and child-handle discovery. |
| `parent_links` | `GET /api/v1/cas/{ca}/parents` and `GET /api/v1/cas/{ca}/parents/{parent}` via `krillc parents statuses` and `krillc parents contact` | `KRILL_PARENT_STATUSES_JSON`, `KRILL_PARENT_CONTACT_JSON` | Exposes parent handle, exchange status, parent-side resources, and issuance-related certificate-bearing linkage fields. |
| `child_links` | `GET /api/v1/cas/{ca}` plus `GET /api/v1/cas/{ca}/children/{child}` and `GET /api/v1/cas/{ca}/stats/children/connections` via `krillc children info` and `krillc children connections` | `KRILL_CA_METADATA_JSON`, `KRILL_CHILD_INFO_JSON`, `KRILL_CHILD_CONNECTIONS_JSON` | Provides child handle discovery, child state, child id-cert linkage, entitlement data, and child connection freshness. |
| `resource_entitlements` | Derived from `GET /api/v1/cas/{ca}`, parent status, and child info | `KRILL_CA_METADATA_JSON`, `KRILL_PARENT_STATUSES_JSON`, `KRILL_CHILD_INFO_JSON` | These are already available as a composed view of provider-held resources and delegated resources. |

### Publication-observation evidence

Publication-observation evidence is repository-facing state that describes publication points and the objects published beneath them. This is the evidence source that should anchor repository artifact maps, signed-object inventory, and future certificate observation.

Current publication-observation families that are suitable Tier 1 inputs now:

| Family | Current source(s) | Current fixtures | Why Tier 1 now |
| --- | --- | --- | --- |
| `publication_points` | `GET /api/v1/cas/{ca}/repo` and `GET /api/v1/cas/{ca}/repo/status` via `krillc repo show` and `krillc repo status` | `KRILL_REPO_DETAILS_JSON`, `KRILL_REPO_STATUS_JSON` | This is the cleanest current source for publication topology, freshness, and the published object list. |
| `signed_object_inventory` | Derived from the publication-point payloads and their published object membership | `KRILL_REPO_STATUS_JSON` | The published list already exposes object URIs and bodies for deterministic classification of published signed objects such as manifests and CRLs. |

## Repository artifact map

The current Krill dev surface gives us a practical repository artifact map even though it does not yet give us a first-class certificate inventory endpoint.

### Publication-point metadata

Use `KRILL_REPO_DETAILS_JSON` and `KRILL_REPO_STATUS_JSON` for publication-point metadata.

Confirmed fields that matter now:

- `service_uri`
- `repo_info.sia_base`
- `repo_info.rrdp_notification_uri`
- `last_exchange`
- `next_exchange_before`
- `published`

These are the right fixtures for publication-point identity, repository endpoint linkage, and freshness reporting.

### Published object membership

Use the `published` array in `KRILL_REPO_STATUS_JSON` as the current evidence source for membership in the publication set.

Each published object record should preserve at least:

- object URI
- object body or body hash if available
- publication-point association
- signed-object type when it can be derived deterministically

This is the current anchor for future tests that need object membership, object URIs, or a retained snapshot of published content.

### Manifests

Manifests are not a fake certificate inventory surrogate. They are repository artifacts that enumerate expected published objects and therefore belong in publication-observation tests.

For future fixture work, model manifests as:

- manifest metadata
- manifest object URI
- manifest entries
- per-entry object names and hashes
- the relationship back to the publication point that emitted the manifest

The current repo-status payload already gives us the object URI and body for a manifest-like published object; the next fixture step should add explicit manifest parsing and manifest-entry coverage rather than a certificate list endpoint.

### CRLs

CRLs belong in the same repository-observation lane as manifests.

For future fixture work, model CRLs as:

- CRL metadata
- CRL object URI
- CRL number and freshness fields when available
- the relationship back to the publication point that emitted the CRL

The current repo-status payload already gives us the object URI and body for a CRL-like published object. That is enough to anchor a deterministic fixture without fabricating a certificate inventory feed.

### Certificate-bearing auxiliary payloads

Certificate-bearing auxiliary payloads are allowed only as linkage evidence.

Use them to support relationships such as:

- CA metadata to repository linkage
- parent-issued certificate references
- child entitlement references
- publication-point adjacency

Do not treat these fields as the canonical certificate inventory. The canonical inventory should come from repository evidence and published object membership.

## Tier 1, Tier 2, and blocked

### Tier 1: available now

These are already suitable for deterministic tests and repository-observation groundwork.

- `ca_metadata`
- `parent_links`
- `child_links`
- `resource_entitlements`
- `publication_points`
- `signed_object_inventory`

### Tier 2: derive next from repository evidence

These are the next standards-aligned follow-ons, but they need real repository parsing or richer fixtures before they should be treated as complete.

- manifest parsing
- manifest entries
- CRL parsing
- repository-derived certificate observation
- object-classification refinements beyond the current published-object membership list

### Blocked: not a real endpoint

`certificate_inventory` remains a compatibility family in the contract, but it is blocked as a first-class source until repository-derived observation is implemented.

Why it stays blocked:

- Krill does not expose a dedicated certificate inventory API that should be treated as the canonical source.
- The available evidence is repository-facing and must be derived from publication artifacts.
- Building a fake certificate-list fixture would hide the standards-aligned source of truth.

## Fixture strategy for future tests

Use the following rules when adding more Krill fixtures:

1. Keep control-plane fixtures and publication-observation fixtures separate.
2. Model repository evidence from publication points, published object membership, object URIs, and object bodies before inventing any derived certificate view.
3. Add explicit manifest fixtures and manifest-entry fixtures when parser coverage needs repository completeness checks.
4. Add explicit CRL fixtures when parser coverage needs revocation and freshness checks.
5. Keep certificate-bearing auxiliary payloads as linkage hints, not as the canonical inventory source.
6. Prefer deterministic fixtures built from documented Krill payload shapes over synthetic inventory endpoints.

## Current deterministic payload inventory

All current deterministic Krill payloads are centralized in `netbox_rpki/tests/krill_payloads.py`.

Confirmed current payloads:

- `KRILL_CA_METADATA_JSON`
- `KRILL_PARENT_STATUSES_JSON`
- `KRILL_PARENT_CONTACT_JSON`
- `KRILL_CHILD_INFO_JSON`
- `KRILL_CHILD_CONNECTIONS_JSON`
- `KRILL_REPO_DETAILS_JSON`
- `KRILL_REPO_STATUS_JSON`
- `KRILL_ROUTES_JSON`
- `KRILL_ASPAS_JSON`

## Current repo observations worth preserving

- The Krill provider sync implementation already treats publication points as a separate publication-observation family.
- The provider-sync contract already marks `certificate_inventory` as publication-observation metadata, but the family still needs repository-derived implementation before it can become a real inventory source.
- The current Krill tests already import publication points and signed objects from repo-status evidence, so the documentation should mirror that split instead of implying a certificate-list endpoint.