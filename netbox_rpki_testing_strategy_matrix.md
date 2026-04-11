# netbox-rpki Plugin Testing Strategy Matrix

## Purpose

This document proposes a practical testing strategy for a NetBox RPKI plugin that aims to support cloud-service providers, highly interconnected enterprises, and other operators consuming hosted RPKI services. The central objective is to separate:

1. **standards and data-model validation**, which can be developed and exercised without any specific Regional Internet Registry (RIR) account relationship, from
2. **provider-specific hosted-RPKI adapter validation**, which often depends on access to gated non-production environments.

This distinction is especially important because current public documentation indicates that ARIN's OT&E environment is not a general-purpose anonymous sandbox. ARIN documents prerequisites including an ARIN Online account, authority over resources in ARIN Online, and an API key. RIPE's publicly available training and test-environment materials likewise point toward testing tied to an LIR account and that LIR's resources. By contrast, NLnet Labs documents a public Krill-based RPKI testbed intended for experimentation, including use without proof of ownership inside the test hierarchy. citeturn0search0turn0search1turn0search2turn0search4

---

## Core Testing Lanes

A useful strategy is to divide validation into four lanes.

### Lane A: Local and Offline Fixture Tests

This lane uses static fixtures, mocks, and deterministic test data. It should carry the bulk of model, migration, reconciliation, and linting coverage.

Use this lane for:
- Django/NetBox model migrations
- serializers and API schema behavior
- import/export transforms
- reconciliation logic between NetBox intent and stored RPKI objects
- ROA linting and maxLength policy analysis
- RBAC, approvals, audit trail, and workflow logic
- negative tests and malformed object handling

This lane is the safest place to exercise logic derived from standards documents such as ROA semantics, validation-state interpretation, and repository object relationships. It is also the most stable foundation for CI.

### Lane B: Public Non-Production RPKI Environment

This lane uses a real but public non-production backend. The best documented candidate is the NLnet Labs Krill public testbed. Krill documentation states that the public testbed exists for experimentation and is not tied to any particular RIR or NIR, and that users can claim resources in the test hierarchy without proof of ownership. citeturn0search0

Use this lane for:
- real object lifecycle testing
- parent/child CA relationship exploration
- publication and repository behavior
- end-to-end sync jobs against a live backend
- exercising generic signed-object abstractions against a real RPKI stack

This is the best available substitute when ARIN or RIPE gated test environments are unavailable.

### Lane C: RIR-Hosted Test Environments

This lane exists to validate provider-specific assumptions and adapters. It should not be your primary day-to-day development lane.

Use this lane for:
- ARIN Hosted RPKI adapter validation
- RIPE Hosted RPKI adapter validation
- authentication flows
- provider-specific field mapping
- provider-specific error semantics
- conformance with each provider's business rules and API shape

ARIN's current OT&E documentation describes prerequisites including a linked ARIN Online user account, authority over resources, and an API key. RIPE public materials indicate use of the test environment with an LIR account and that LIR's prefixes. citeturn0search1turn0search2

### Lane D: Production-Like Manual Validation

This lane should be rare and carefully controlled. It is suitable only for final smoke tests performed with a cooperating organization, sponsor account, or other approved real-world arrangement.

Use this lane for:
- final adapter smoke testing
- last-mile provider workflow confirmation
- operational sanity checks before broader deployment

This lane should never be required for ordinary development velocity.

---

## Feature Validation Matrix

| Feature / capability | Lane A: local fixtures | Lane B: Krill public testbed | Lane C: ARIN OT&E | Lane C: RIPE test env | Notes |
|---|---:|---:|---:|---:|---|
| Core Django/NetBox model migrations | Yes | No | No | No | Pure application/schema work |
| Generic signed-object abstraction | Yes | Partial | Partial | Partial | Parse and normalize locally; confirm behavior live |
| Organization / CA hierarchy modeling | Yes | Yes | Partial | Partial | Krill is well suited for hierarchy semantics |
| Resource certificate inventory | Yes | Yes | Yes | Yes | Provider field mapping varies |
| ROA CRUD data model | Yes | Yes | Yes | Yes | First cross-provider target |
| ROA import/export transforms | Yes | Yes | Yes | Yes | Live provider details differ |
| NetBox intent-to-ROA reconciliation | Yes | Yes | Yes | Yes | Mostly plugin-side logic |
| ROA maxLength linting and policy analysis | Yes | Yes | Partial | Partial | Primarily offline logic |
| Bulk ROA generation | Yes | Yes | Partial | Partial | Provider limits and workflow differ |
| ROA lifecycle state sync | Mock first | Yes | Yes | Yes | Adapter-specific pagination and status fields |
| ASPA data model | Yes | Likely Yes | Partial / evolving | Partial / likely test-first | Provider availability and maturity may vary |
| ASPA provider adapter | Mock first | Partial | Partial | Partial | Treat as capability-gated |
| CRL model and ingest | Yes | Yes | Partial | Partial | Repository-oriented capability |
| Manifest model and ingest | Yes | Yes | Partial | Partial | Repository-oriented capability |
| EE certificate tracking | Yes | Yes | Partial | Partial | Strong fixture coverage recommended |
| Publication point / repository URI model | Yes | Yes | Partial | Partial | Best exercised with real object trees |
| Validator / relying-party cache import | Mock first | Partial | No | No | Best with local validator lab |
| Validated payload / VRP import | Yes | Partial | No | No | Best against local validator instances |
| ARIN Hosted API adapter | Mock first | No | Yes | No | Needs ARIN-qualified access |
| RIPE Hosted API adapter | Mock first | No | No | Yes | Needs RIPE-qualified access |
| RBAC / approvals / audit trail | Yes | No | No | No | Pure application behavior |
| Webhooks / background jobs | Yes | Partial | Partial | Partial | Provider callback story may vary |
| Validation-impact simulation | Yes | Yes | Partial | Partial | Mostly local logic; live sync improves realism |

---

## Lane-by-Lane Guidance

### What Lane A should prove

Lane A should prove that the plugin can represent and manipulate the standards-based object graph cleanly, including:
- resource certificates
- end-entity certificates
- ROAs
- ASPAs
- manifests
- CRLs
- publication-point relationships
- validated-payload overlays, when modeled

It should also prove that the plugin can reconcile NetBox routing and IPAM intent to externally visible RPKI state without needing a real hosted provider.

### What Lane B should prove

Lane B should prove that the plugin's generic integration layer works against a live RPKI implementation:
- object creation and deletion
- state polling and synchronization
- handling of parent/child authority relationships
- publication metadata ingestion
- repository-oriented object handling
- resilience to real API timing and object lifecycle behavior

### What Lane C should prove

Lane C should prove only the delta between the generic model and each provider's actual implementation:
- authentication and account assumptions
- provider payload shape
- supported object classes
- pagination and filtering semantics
- provider-specific validation or workflow rules
- lifecycle race conditions and status interpretation

### What Lane D should prove

Lane D should prove only final production-like viability. It should not be necessary to make progress on core design or broad functional testing.

---

## Recommended Implementation and Validation Sequence

### Phase 1: Schema and Logic First

Build and validate locally:
- normalized models
- generic signed-object framework
- reconciliation engine
- linting and policy analysis
- RBAC, approvals, and audit behavior
- import/export abstraction layer

No external dependency should block this phase.

### Phase 2: Live Generic Backend

Add a generic live integration path using the Krill public testbed:
- sync jobs
- object lifecycle polling
- publication-point and repository metadata
- basic certificate and signed-object handling
- live create/update/delete flows where supported

Krill is the best currently documented public backend for this purpose. citeturn0search0

### Phase 3: Provider-Specific Adapters

Add ARIN and RIPE adapters:
- auth flows
- field mapping
- provider capability discovery
- error normalization
- hosted-RPKI workflow translation

Validate these only when access exists to the relevant provider environment. ARIN's OT&E prerequisites make it unsuitable as a default open development dependency. citeturn0search1

### Phase 4: Advanced Objects and Operational Overlays

Add:
- ASPA
- validated-payload / VRP import
- relying-party cache import
- validation-impact simulation
- advanced publication and repository health views

Much of this can still be developed locally or partially exercised against Krill and local validator labs.

---

## Provider Capability Abstraction

The plugin should implement an explicit provider capability matrix in code. Suggested flags include:

- `supports_roa_read`
- `supports_roa_write`
- `supports_aspa_read`
- `supports_aspa_write`
- `supports_certificate_inventory`
- `supports_manifest_inventory`
- `supports_crl_inventory`
- `supports_repository_metadata`
- `supports_test_environment`
- `requires_resource_bound_account`
- `supports_bulk_operations`

This prevents the core model from becoming ARIN-shaped, RIPE-shaped, or Krill-shaped. Public documentation already shows that these environments differ substantially in openness, eligibility, and feature rollout posture. ARIN OT&E is gated by account and resource authority; Krill's public testbed is intentionally more open for experimentation. citeturn0search0turn0search1

---

## Recommended Test Harness Components

To make the strategy concrete, the implementation should include the following harness components.

### 1. Fixture Library

A versioned library of:
- certificates
- CRLs
- manifests
- ROAs
- ASPAs
- repository metadata samples
- provider-specific API response fixtures

This library should include both happy-path and malformed cases.

### 2. Mock Provider Adapters

Provider mocks for:
- ARIN-style hosted RPKI APIs
- RIPE-style hosted RPKI APIs
- generic Krill-style live integration

These mocks should simulate pagination, rate limiting, stale state, unsupported-object errors, and authorization failures.

### 3. Local Validator Lab

A local relying-party / validator lab using one or more common open-source validators should be added when validated-payload overlays are implemented. This is the best place to test:
- VRP import
- validation-state transitions
- cache snapshot ingestion
- "would this become invalid?" analysis

### 4. Contract Tests

A suite of contract tests should validate that each provider adapter implements a shared internal interface even when provider features differ. This is essential if the plugin intends to support multiple hosted-RPKI providers over time.

---

## Practical Recommendation for This Project

Given the likely lack of ARIN-qualified access in the current context, the most effective path is:

1. build the full schema and logic locally first
2. use the Krill public testbed as the primary live backend
3. keep ARIN and RIPE integrations behind provider adapters
4. treat access to ARIN OT&E and RIPE test environments as optimization, not prerequisite
5. avoid making any provider-specific test environment the linchpin of day-to-day engineering

This approach preserves forward motion even when provider-gated environments are unavailable.

---

## Go / No-Go Guidance

### Safe to build immediately without ARIN or RIPE access

The following can and should proceed immediately:
- generic core models
- ROA workflows
- ASPA schema
- CRL, manifest, and EE certificate models
- reconciliation engine
- policy linting
- approvals and audit trail
- provider abstraction layer
- fixture-driven imports and exports

### Should not be considered complete without provider-qualified access

The following should be treated as incomplete until validated against real provider environments:
- exact ARIN Hosted adapter behavior
- exact RIPE Hosted adapter behavior
- provider-specific edge-case handling
- assumptions about supported non-ROA object classes in each provider's hosted offering
- final operator workflow fit for a specific RIR portal and API

---

## Citations

- ARIN OT&E overview and prerequisites: current ARIN OT&E documentation describes account, resource-authority, and API-key prerequisites for testing. citeturn0search1
- ARIN hosted RPKI documentation: ARIN documents hosted RPKI offerings and the availability of OT&E for experimentation, but current OT&E eligibility details remain account/resource-bound. citeturn0search3turn0search1
- RIPE test-environment references: RIPE training and presentation materials point to use of the test environment with an LIR account and that LIR's prefixes/resources. citeturn0search2turn0search4
- NLnet Labs Krill public testbed: Krill documentation describes a public testbed for experimentation, independent of any specific RIR/NIR, with no proof-of-ownership requirement in the test hierarchy. citeturn0search0
