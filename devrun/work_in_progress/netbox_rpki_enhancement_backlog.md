# NetBox RPKI Plugin: High-Priority Enhancement Backlog for Hosted-RPKI Consumers

**Prepared:** April 11, 2026  
**Last updated:** April 12, 2026  
**Target audience:** NetBox plugin developer / coding agent / platform engineering team  
**Plugin reviewed:** `netbox-rpki` `0.1.6.dev5` on TestPyPI  

---

## 1. Executive summary

The current `netbox-rpki` plugin exposes a useful **RPKI inventory and recordkeeping foundation** inside NetBox. Based on the published package description, it presently focuses on data models and forms for:

- RPKI organizations
- resource certificates
- ROAs
- ROA-to-prefix relationships
- ROA-to-ASN relationships
- certificate-to-prefix relationships
- certificate-to-ASN relationships

It is explicitly positioned as a plugin that lets an organization using either self-hosted or RIR-hosted RPKI maintain a self-hosted record of critical RPKI elements inside NetBox. citeturn301101view0turn910174search9

That is a strong starting point, but for a cloud service provider, hyperscale-adjacent operator, or highly interconnected enterprise consuming **hosted RPKI** from an RIR, the main operational problem is not storing RPKI objects. The main problem is ensuring that published ROAs and related policy stay aligned with actual routing intent as prefixes, regions, services, edges, and upstream arrangements evolve. RIPE NCC explicitly notes that in hosted RPKI, the operator mainly needs to ensure the ROAs match intended BGP routing, while the hosted system handles cryptographic operations, key rollovers, and publication. ARIN similarly documents hosted workflows and API-based management for ROAs and ASPAs. citeturn910174search4turn910174search0turn910174search6

**Bottom line:** that evolution is now underway in code. The plugin is no longer only a passive RPKI object catalog: it now has a working intent-to-ROA reconciliation core, ARIN-backed and Krill-backed provider sync paths, operator drill-down views, provider-backed ROA change-plan generation, and a verified Krill-backed preview/approve/apply write-through slice with auditable provider execution records and post-apply sync refresh. Provider accounts can now also launch sync runs from the UI, and the sync enqueue path has been corrected across UI, API, and command surfaces so it no longer tries to bind jobs to a provider-account object type that does not support NetBox job attachment. A blocking operability issue discovered during provider-account setup has also been fixed: the plugin now explicitly separates internal registry identity from public UI/API slugs, which restored Add/Edit/changelog action routing across generated plugin objects and made provider-account definition usable again. The latest reconciliation sprint also landed stable external-object-reference tracking for imported provider rows, governance metadata plus approval-record persistence on ROA change plans, and a read-only operations dashboard for sync-health and expiry visibility. The merged result is now validated by a green full plugin suite at 273 tests. The next highest-value work is broadening that write path beyond the initial Krill slice rather than inventing a second parallel workflow.

### Recently shipped sprint: provider write-through for Krill-backed ROA plans

This sprint converted the previous read-only provider workflow into a controlled write pipeline that starts from reconciliation results and ends with an auditable provider transaction. The key implementation detail is that the write path extends upward through the existing provider-facing workflow instead of stopping at a low-level Krill POST helper.

Shipped outcome:
- a provider-backed draft ROA change plan can now be previewed, approved, applied against Krill, and followed immediately by a provider sync refresh
- the provider abstraction still cleanly separates capability metadata and operation planning so later adapters can reuse the same workflow shape

Required scope for this sprint:
- preserve the newly explicit split between internal registry identity and public route/API naming so provider-backed actions do not regress when model names and public slugs intentionally differ
- add explicit provider write capability metadata and provider operation planning abstractions, so provider actions are feature-gated rather than inferred
- extend `ROAChangePlan` and `ROAChangePlanItem` with execution-oriented state, including approval/apply status, timestamps, actor attribution, and per-item provider operation details
- add a provider write execution record, ideally as a sibling to `ProviderSyncRun`, so every outbound apply attempt has status, request/response summaries, error text, and related snapshot/plan references
- implement a Krill ROA delta builder that converts create and withdraw items into the documented `POST /api/v1/cas/<ca>/routes` payload shape with `added` and `removed` arrays
- add a dry-run or preview service path that materializes the exact provider delta payload without applying it
- add an apply service path that sends the Krill delta, records execution results, and immediately refreshes provider state by triggering a follow-up provider sync
- expose the workflow at the API/UI layer through provider-based actions: preview plan, approve plan, apply plan, and re-sync after apply
- thread provider-account context all the way upward so reconciliation runs, plans, and applies are explicitly tied to the provider account and provider snapshot they target

Out of scope for this sprint:
- ASPA write support
- ARIN write support
- generic multi-provider bulk scheduling/orchestration
- rollback semantics beyond recording failed and partially applied transactions

Verified done:
- an operator can start from a provider-backed reconciliation run, create a change plan, preview the exact Krill delta, approve it, apply it, and observe a resulting provider sync snapshot
- every provider write attempt is auditable with request intent, result status, and linked plan items
- the provider abstraction cleanly separates read capability from write capability
- provider accounts now expose a UI sync action with a confirmation page, and sync jobs can be launched from UI, API, and command surfaces without invalid NetBox job-object binding
- focused tests now cover preview, approve/apply state transitions, permission checks, failure handling, provider capability exposure, and post-apply re-sync
- the full plugin suite is green at 273 passing tests

---

## 2. Current exposed functionality reviewed

From the TestPyPI project page, the plugin currently documents the following functional surface:

### 2.1 Core models

#### Organization
Represents a consumer of Regional Internet Registry RPKI services. Documented fields include:
- `org-id`
- `name`
- `ext_url`
- `parent_rir` (foreign key to NetBox IPAM ASN)

#### Resource Certificate
Represents the RPKI resource certificate. Documented fields include:
- `name`
- `issuer`
- `subject`
- `serial`
- `valid_from`
- `valid_to`
- `auto_renews`
- `public_key`
- `private_key`
- `publication_url`
- `ca_repository`
- `self_hosted`
- `rpki_org`

#### Route Origination Authorization (ROA)
Represents an RPKI ROA object. Documented fields include:
- `name`
- `origin_as`
- `valid_from`
- `valid_to`
- `auto_renews`
- `signed_by`

The package description also notes a semantic interpretation for ASN 0 ROAs, but indicates NetBox does not natively permit ASN value 0 and suggests a placeholder workaround. citeturn301101view0

#### Supporting relationship models
The project description also documents hidden relationship tables for:
- ROA prefix
- ROA ASN
- certificate prefix
- certificate ASN

These are noted as not being directly exposed through the UI menu. citeturn301101view0

### 2.2 Framing of current value

The package description explicitly says the plugin “implements data models and forms” for modeling RPKI items and allows an organization to keep a self-hosted record of critical RPKI elements, including when using an RIR-hosted service. That phrasing strongly suggests the current value is primarily **inventory, CRUD, and internal documentation**, rather than reconciliation, validation, automation, or provider synchronization. citeturn301101view0

---

## 3. Design objective for the next phase

For a hosted-RPKI consumer, the plugin should become a practical answer to these questions:

1. **What RPKI objects should exist, based on NetBox routing intent?**
2. **What RPKI objects actually exist in the hosted provider’s system?**
3. **What is missing, stale, too broad, risky, or wrong?**
4. **What would happen operationally if we published a proposed change?**
5. **How do we make safe, auditable, bulk policy changes at provider scale?**

That objective aligns with how hosted RPKI is actually consumed in operations: the RIR handles the CA and publication mechanics, while the operator remains responsible for correct policy expression. citeturn910174search4turn910174search9

---

## 4. Prioritized enhancement backlog

Below is a proposed high-priority backlog, written as an implementation handoff.

---

### Priority 1: Intent-to-ROA reconciliation engine

**Implementation status:** Substantially completed for the first operational slice. Priority 1 now has the additive schema layer, execution path, provider-imported comparison schema, dashboard/drill-down UX, draft change-planning scaffold, and the provider-account/UI routing hardening needed to use the provider-backed workflow in practice.

Completed in code:
- materialized-history models for intent derivation runs, reconciliation runs, intent rows, candidate matches, and intent-side/published-side reconciliation results at
- writable operator-policy objects for routing intent profiles, ordered rules, and explicit ROA intent overrides
- registry-driven UI/API exposure with writable surfaces for policy objects and read-only surfaces for derived/reconciliation objects
- migration-backed rollout preserving existing `Roa`/`RoaPrefix` objects as the initial published-state source
- derivation and reconciliation service logic for local ROA records
- NetBox execution surfaces for the pipeline: background job runner, synchronous management command, and authenticated API trigger on `RoutingIntentProfile`
- provider-imported comparison data model via `ProviderSnapshot` and `ImportedRoaAuthorization`
- provider-imported reconciliation scope in the service layer, command surface, API trigger, and persisted reconciliation history
- custom operator UX on top of the generated detail system: profile dashboard, reconciliation drill-down, and intent-result diff context
- draft ROA publication/change planning via `ROAChangePlan`, `ROAChangePlanItem`, and a reconciliation-run `create_plan` API action
- generated UI surfaces now suppress unsupported Add/Edit/Delete affordances for read-only registry objects across list tables, list-page controls, and generated detail views
- focused and broad regression coverage, including registry-wide UI/API surface-contract checks; current verified state is 273 passing plugin tests
- central plugin action-URL resolution for generated CRUD actions, with plugin models now resolving NetBox generic actions through registry metadata instead of assuming Django model names and public route slugs are identical
- explicit separation of internal registry keys from public UI/API/GraphQL naming in the registry contract, including provider-account as the proof case (`rpkiprovideraccount` internally, `provideraccount` publicly)

Still pending in later work:
- actual provider connector implementations and scheduled import/sync workflows
- mixed local-plus-imported reconciliation and richer source selection semantics
- richer remediation planning beyond the current create/withdraw and Krill-backed approval/apply slice, including replacement flows, rollback, multi-stage governance, and non-Krill write-back/publication execution
- dedicated dashboard widgets and summary/report views beyond the current detail-page-driven operator flow and the new read-only operations dashboard
- linting, simulation, and IRR/validator overlays that should consume the reconciliation outputs

**Problem solved**  
The plugin currently appears to store RPKI artifacts, but a provider-grade operator needs to know whether NetBox routing intent and published hosted-RPKI state are aligned.

**Why this matters**  
The biggest operational value lies in detecting:
- missing ROAs
- stale ROAs
- wrong-origin ROAs
- over-broad ROAs
- ROAs covering prefixes not intended for Internet advertisement

RPKI origin validation determines whether a route is considered valid, invalid, or not found, so drift between intended routing and ROA state is directly tied to risk. citeturn910174search9turn910174search0

**Recommended functionality**
- derive expected ROA candidates from NetBox data
- compare expected objects to plugin-recorded objects and, later, provider-imported objects
- classify drift as:
  - missing
  - stale
  - ASN mismatch
  - prefix-length mismatch
  - over-authorized (`maxLength` too broad)
  - orphaned policy object
- expose a reconciliation dashboard and detail views
- allow filtering by site, region, tenant, ASN, prefix family, or service role

**Likely data-model additions**
- implemented under the current names `RoutingIntentProfile`, `RoutingIntentRule`, `ROAIntentOverride`, `IntentDerivationRun`, `ROAIntent`, `ROAIntentMatch`, `ROAReconciliationRun`, `ROAIntentResult`, and `PublishedROAResult`
- additionally implemented for the next comparison/planning step: `ProviderSnapshot`, `ImportedRoaAuthorization`, `ROAChangePlan`, and `ROAChangePlanItem`

**Suggested NetBox bindings**
- prefixes
- ASNs
- tenant
- VRF
- site / region / location
- tags / custom fields

**Implementation notes**
- initial rollout no longer stops at read-only scaffolding: policy objects are writable, derived objects remain read-only, and recomputation is available through service code, a NetBox job, a management command, and an authenticated API action
- current derivation computes expected state from NetBox IPAM prefixes plus ASN selectors, rules, overrides, and common scope bindings such as tenant, VRF, site, region, tags, and custom fields
- current reconciliation now supports both locally modeled `Roa`/`RoaPrefix` state and normalized provider-imported authorization snapshots
- current change planning is intentionally narrow: plans only create missing active ROAs and withdraw orphaned published ROAs, but provider-backed plans now carry explicit approval/apply lifecycle state, preview/apply Krill payloads, and auditable write execution history; richer replacement logic, rollback, and non-Krill write adapters remain future work
- remaining follow-on work is now mostly real provider ingestion, richer workflow state, and higher-order analysis rather than first-pass execution plumbing

**Delivery complexity**: Medium  
**Operational value**: Extremely high

---

### Priority 2: Hosted-RPKI provider synchronization layer

**Implementation status:** Partially completed with real connector slices, operator-triggerable sync surfaces, interval-based scheduling, stable external-object-reference tracking, and the core operability fixes needed to use them. The plugin now has `RpkiProviderAccount`, `ProviderSyncRun`, `ProviderSnapshot`, `ImportedRoaAuthorization`, `ExternalObjectReference`, provider-backed `ROAChangePlan`/`ROAChangePlanItem` execution metadata, and `ProviderWriteExecution`, plus import-only ARIN sync, end-to-end Krill ROA sync/write flows, a provider-account detail-page sync action, scheduled due-account sync orchestration, computed provider sync-health visibility, and a read-only operations dashboard for stale/failed sync and expiry review. Provider-account creation and generated object CRUD routing are now working again after the registry/public-slug split and action-URL fixes, and sync enqueue paths were corrected so they no longer try to bind jobs to a provider-account object type that lacks NetBox job support. It still lacks multi-provider support beyond ARIN import and Krill ROA write-through, richer provider diff/reporting surfaces, and non-ROA provider ingestion.

**Problem solved**  
Hosted-RPKI consumers should not have to manually duplicate RIR portal state into NetBox.

**Why this matters**  
ARIN documents RESTful API support for listing and managing ROAs and ASPAs. RIPE NCC documents an RPKI Management API that supports the same kinds of activities available in its management portal. Hosted-RPKI users benefit most when NetBox can import and compare against real provider state. citeturn910174search0turn910174search1turn910174search6turn910174search18

**Recommended functionality**
- pluggable provider connectors:
  - nlnet Krill (for self-hosted RPKI)
  - ARIN Hosted RPKI connector
  - RIPE Hosted RPKI connector
  - APNIC connector if feasible in a later phase
- scheduled sync of:
  - organizations/accounts
  - resource certificates where exposed
  - ROAs
  - ASPAs where exposed
- snapshot retention for diff/history
- credential management via secrets or NetBox config plugin settings
- “last synced” timestamps and sync health reporting

Completed in code:
- `RpkiProviderAccount` writable model for provider credentials and sync settings
- `ProviderSyncRun` read-only execution history for provider imports
- ARIN import-only connector using ARIN's RPKI RESTful ROA list endpoint
- Krill import-only connector using the documented `GET /api/v1/cas/<ca>/routes` route-authorization endpoint and bearer-token authentication
- production vs OT&E transport selection on provider accounts
- synchronous management command and NetBox background job for provider sync
- interval-based sync scheduling on provider accounts via `sync_interval`
- due-account orchestration through the `sync_provider_accounts` management command
- duplicate-enqueue protection so scheduled/manual sync requests reuse queued work or skip when a sync is already running
- authenticated API action on provider accounts to enqueue a sync
- provider-account detail-page sync action and confirmation view for launching provider sync from the UI
- provider snapshots now link back to the provider account that produced them
- normalized ARIN ROA XML ingestion into `ImportedRoaAuthorization`
- normalized Krill route-authorization JSON ingestion into `ImportedRoaAuthorization`, including CA handle tracking and ROA-object metadata capture
- explicit provider ROA write capability metadata, currently enabling Krill route-delta writes while leaving ARIN write support disabled
- provider-backed change plans now bind to both the target `RpkiProviderAccount` and the source `ProviderSnapshot`
- provider-backed ROA change plans now support preview, approve, applying/applied/failed lifecycle tracking, actor attribution, and exact Krill `added`/`removed` payload materialization
- `ProviderWriteExecution` audit rows record preview/apply attempts, request payloads, provider responses, errors, and follow-up sync/snapshot references
- authenticated API and UI custom actions for ROA change-plan preview, approve, and apply
- post-apply Krill refresh path that triggers a follow-up provider sync and captures the resulting snapshot linkage
- sync enqueue paths in the UI view, API action, and management command now intentionally omit object binding because `RpkiProviderAccount` does not support NetBox job attachment
- computed provider sync health and next-due visibility are now exposed on provider accounts in the model, UI detail view, table output, and API serializer
- provider-account Add/Edit/list action routing fixed across the plugin, and read-only generated objects now suppress unsupported Add/Edit/Delete affordances instead of rendering broken `/None` links or missing edit routes
- registry contract refactor separating internal `registry_key` identity from public route slug, path prefix, API basename, and GraphQL field naming, eliminating the root cause of the generated action-link bug
- focused regression coverage for the sync service, command, API action, registry/API surfacing, generated action links, registry-wide UI surface contracts, and provider-account list rendering
- full plugin suite currently green at 273 tests

**Likely data-model additions**
- `ProviderAccount` implemented as `RpkiProviderAccount`
- `ProviderSyncJob` implemented as `ProviderSyncRun`
- `ProviderSnapshot` implemented
- `ExternalObjectReference`
- `SyncErrorLog`

**Implementation notes**
- phase 1: import only
- current repo state includes ARIN import-only ROA sync plus Krill-backed ROA import and preview/approve/apply with follow-up sync; provider-account CRUD, generated plugin action links, operator-initiated UI sync, and sync enqueue semantics are operational after the latest routing and job-binding fixes
- current repo state now includes scheduled sync orchestration, sync-health computation, duplicate-enqueue handling, stable external object references for imported ROA rows, and a read-only operations dashboard on top of ARIN import-only ROA sync plus Krill-backed ROA import and preview/approve/apply with follow-up sync; multi-provider abstraction depth beyond ARIN/Krill, richer provider diff/reporting, and non-Krill provider write adapters are still pending
- phase 2: preview/apply export payloads
- phase 2 is now implemented for the initial Krill route-delta slice; the next write-path work should extend the same audited contract to other providers rather than redesign the workflow
- phase 3: extend the same controlled write-back flow to additional providers after the Krill write contract is proven
- keep provider abstraction clean to avoid hard-coding ARIN-specific assumptions into core models

**Delivery complexity**: Medium to high  
**Operational value**: Extremely high

---

### Priority 3: ASPA support

**Problem solved**  
The currently documented plugin surface does not expose ASPA objects, but hosted-RPKI ecosystems now include ASPA workflows.

**Why this matters**  
ARIN documents ASPA support and API methods, and RIPE NCC has also introduced ASPA support in its operational tooling. ASPA adds authorization for provider relationships and is relevant to route-leak defense, which is especially valuable to providers and large multi-homed operators. citeturn910174search6turn910174search7

**Recommended functionality**
- ASPA object model
- customer ASN to provider ASN relationship sets
- import/export support through provider sync layer
- reconciliation of intended provider relationships vs published ASPAs
- association of ASPAs with upstream providers/circuits/policy groups

**Likely data-model additions**
- `ASPA`
- `ASPAProviderASN`
- `ASPAIntent`
- `ASPAReconciliationResult`

**Implementation notes**
- support multiple providers per customer ASN
- support planned vs published provider relationships
- expose graph-style relationship views in UI where practical

**Delivery complexity**: Medium  
**Operational value**: Very high

---

### Priority 4: ROA policy linting and safety analysis

**Problem solved**  
Operators frequently create ROAs that are syntactically valid but operationally risky.

**Why this matters**  
RFC 9319 recommends minimal ROAs and advises operators to avoid using `maxLength` unless needed, because over-broad authorization increases exposure to forged-origin subprefix hijacks. A useful plugin should detect bad or risky ROA design, not merely store it. citeturn910174search2turn910174search11

**Recommended functionality**
- detect unnecessary `maxLength`
- recommend minimal ROAs from observed or intended announcements
- identify over-broad authorization windows
- warn when a ROA covers non-advertised space
- detect inconsistent aggregate vs more-specific ROA sets
- support exception categories such as:
  - DDoS mitigation
  - traffic engineering
  - anycast
  - temporary migration

**Likely data-model additions**
- `ROALintResult`
- `ROAPolicyException`
- `ROATemplateRule`

**Implementation notes**
- build as deterministic rules first
- later add policy profiles per operator or per service class
- provide explainable warnings, not black-box scoring

**Delivery complexity**: Low to medium  
**Operational value**: Very high

---

### Priority 5: ROV impact simulation

**Implementation status:** Not implemented, but a precursor now exists. The plugin has draft `ROAChangePlan` and `ROAChangePlanItem` generation from reconciliation results, which is a useful substrate for later dry-run validity simulation, but there is no actual ROV outcome engine yet.

**Problem solved**  
Operators need to know whether a proposed ROA change could make real routes invalid.

**Why this matters**  
Origin validation outcomes are operationally significant. A plugin that can preview validity outcomes before publication becomes much more valuable than one that simply stores desired state. citeturn910174search9turn910174search0

**Recommended functionality**
- simulate route-origin-validation outcomes for proposed changes
- classify impacts as:
  - would become valid
  - would become invalid
  - would remain not found
- show reason codes:
  - no covering ROA
  - ASN mismatch
  - prefix-length mismatch
- summarize blast radius by:
  - prefix count
  - service
  - region
  - tenant
  - edge role

**Likely data-model additions**
- `ROAChangePlan` implemented in a ROA-specific draft form
- `ROVSimulationResult`
- `SimulationEvidence`

**Implementation notes**
- phase 1 can operate on intended route-origin tuples from NetBox
- later phases can ingest external BGP observation or validator data
- include dry-run views before export/write-back

**Delivery complexity**: Medium  
**Operational value**: Very high

---

### Priority 6: Bulk ROA generation and templating

**Problem solved**  
Provider-scale operators manage large prefix estates and need deterministic, repeatable workflows.

**Why this matters**  
Hosted RPKI removes cryptographic housekeeping from the customer, but it does not remove the need to efficiently express correct routing authorization across many prefixes and ASNs. Bulk workflows are essential at scale. citeturn910174search4turn910174search0

**Recommended functionality**
- generate candidate ROAs in bulk from selected prefixes/ASNs
- policy templates by use case:
  - backbone/transit
  - regional edge
  - anycast
  - DDoS mitigation
  - customer delegated edge
- preview and validate before save/export
- regenerate candidates when NetBox inventory changes
- support idempotent operations

**Likely data-model additions**
- `ROATemplate`
- `ROABulkPlan`
- `ROAGenerationRule`

**Implementation notes**
- make templating declarative
- support tag-based scoping
- allow partial overrides per prefix or ASN

**Delivery complexity**: Medium  
**Operational value**: High

---

### Priority 7: Deeper NetBox object binding and service-context awareness

**Problem solved**  
RPKI intent is rarely flat across a provider estate.

**Why this matters**  
Operators need to understand RPKI policy in the context of where and why a prefix is announced, not just which prefix and ASN are involved.

**Recommended functionality**
- bind RPKI policy and reconciliation to:
  - tenant
  - VRF
  - site / region / POP
  - cluster / edge role
  - provider / circuit / exchange context
  - custom tags and custom fields
- filtered views by topology or service domain
- inheritance or policy profile support for common deployment patterns

**Likely data-model additions**
- foreign keys or generic relations to NetBox service-context objects
- `RPKIPolicyProfile`
- `AnnouncementIntentGroup`

**Implementation notes**
- do not over-normalize too early
- use generic relation patterns carefully where NetBox conventions allow
- preserve good API ergonomics for automation clients

**Delivery complexity**: Medium  
**Operational value**: High

---

### Priority 8: Change control, approvals, and auditability

**Implementation status:** Partially completed through the initial governed execution slice. The plugin now has `ROAChangePlan` and `ROAChangePlanItem`, preview/approve/apply lifecycle state, actor attribution, `ProviderWriteExecution` audit rows, persisted ticket/change references, maintenance-window metadata, and `ApprovalRecord` history, and can drive Krill provider write-back from approved plans. Rollback bundles, multi-stage approvals, and broader governance workflows are still pending.

**Problem solved**  
RPKI mistakes can have significant blast radius, so operators need reviewable and auditable workflows.

**Why this matters**  
ARIN documents ROA management workflows and change visibility in its hosted environment. A NetBox-based operational layer should track local intent, approval, and publication state with more context than the provider portal alone. citeturn910174search3turn910174search15

**Recommended functionality**
- candidate vs published object states
- approval workflow for high-risk changes
- diff history and change reasons
- ticket/change-request references
- rollback bundles
- maintenance-window metadata
- two-person integrity option for destructive changes

**Likely data-model additions**
- `RPKIChangeRequest`
- `ApprovalRecord`
- `PublicationState`
- `RollbackBundle`
- current narrower precursor: `ROAChangePlan` and `ROAChangePlanItem`

**Implementation notes**
- phase 1 can be internal-only workflow state
- later generalize approved-plan publication beyond the current Krill write-back slice
- preserve immutable history for audit trails

**Delivery complexity**: Medium  
**Operational value**: High

---

### Priority 9: Expiry, renewal, and publication health dashboarding

**Implementation status:** Partially completed through the first reporting slice. The plugin now exposes computed provider sync-health and next-due metadata on provider accounts plus a read-only operations dashboard covering failed or stale provider sync state and ROA/certificate expiry windows. Alerting thresholds, publication-health observations, exports, and broader lifecycle reporting remain future work.

**Problem solved**  
Existing fields like `valid_from`, `valid_to`, and `auto_renews` are useful, but raw fields are not enough for operations.

**Why this matters**  
Hosted RPKI still has lifecycle visibility needs. Operators need dashboards and alerts around expiration, renewal expectations, publication state, and synchronization freshness. ARIN documents ROA lifecycle and hosted-RPKI management behaviors, including API and service changes affecting ROA management. citeturn301101view0turn910174search15turn910174search3

**Recommended functionality**
- “expiring soon” views for ROAs and certificates
- alerting thresholds
- auto-renew expected vs observed tracking
- stale sync detection
- provider publication health / sync age indicators
- summary widgets and report exports

**Likely data-model additions**
- `LifecycleStatus`
- `HealthCheckResult`
- `ProviderPublicationObservation`

**Implementation notes**
- could be delivered partly as computed properties and reports
- pair well with NetBox jobs and background tasks

**Delivery complexity**: Low to medium  
**Operational value**: High

---

### Priority 10: IRR coordination and ROA/IRR consistency checks

**Problem solved**  
Operators often need ROA policy and IRR route object policy to stay in sync.

**Why this matters**  
ARIN’s hosted-RPKI workflow notes the option to create a corresponding IRR route object when creating a ROA. This is a practical clue that real operators care about consistent ROA + IRR expression. citeturn910174search3

**Recommended functionality**
- track related route/route6 intent
- detect ROA vs IRR inconsistency
- export reports for missing or mismatched IRR objects
- optionally integrate with external IRR tooling in later phases

**Likely data-model additions**
- `IRRRouteIntent`
- `ROAIRRConsistencyResult`

**Implementation notes**
- phase 1 can be metadata + report only
- do not block core RPKI workflow on IRR integration

**Delivery complexity**: Medium  
**Operational value**: Medium to high

---

### Priority 11: External validator and telemetry overlays

**Problem solved**  
Operators need to see not only intended policy, but also observed validation state and external evidence.

**Why this matters**  
A relying-party ecosystem exists precisely so validated payloads can be consumed operationally. Even if the plugin is not a validator, it should be able to ingest and display validation-related evidence from external systems. citeturn910174search9

**Recommended functionality**
- import validation state from external validators or telemetry systems
- annotate prefixes with current status:
  - valid
  - invalid
  - not found
- trend changes after ROA modifications
- surface exceptions by region, tenant, or service

**Likely data-model additions**
- `ValidationObservation`
- `VRPSnapshot`
- `ObservedAnnouncement`

**Implementation notes**
- keep integrations optional
- separate observed state from intended state clearly in UI

**Delivery complexity**: Medium to high  
**Operational value**: Medium to high

---

### Priority 12: Customer / downstream / on-behalf-of authorization modeling

**Problem solved**  
Cloud and service-provider operators frequently announce or manage policy on behalf of downstream customers.

**Why this matters**  
ARIN notes hosted RPKI is limited to direct resource holders and that downstream organizations may need an upstream provider to submit ROAs on their behalf. That makes on-behalf-of modeling important for hosted-service consumers. citeturn910174search4

**Recommended functionality**
- model provider-managed customer authorizations
- distinguish customer-owned vs provider-originated resources
- support downstream service contracts / tenancy relationships
- represent delegated operational responsibility separately from legal resource holding

**Likely data-model additions**
- `ManagedAuthorizationRelationship`
- `DownstreamResourceHolder`
- `OnBehalfOfPolicy`

**Implementation notes**
- likely follows after core reconciliation and provider sync are stable
- keep trust and ownership semantics explicit in schema and UI

**Delivery complexity**: Medium  
**Operational value**: Medium to high

---

## 5. Suggested delivery sequence

### Phase 1: Make the plugin operationally informative
1. Intent-to-ROA reconciliation
  Status: largely delivered for local and normalized imported comparison, including operator detail UX and draft change plans
2. ROA policy linting
3. Lifecycle/expiry/health reporting
4. deeper NetBox object binding

### Phase 2: Connect to reality outside NetBox
5. provider synchronization layer
  Status: ARIN ROA import and Krill ROA import/write are implemented, including provider-account config, sync-run history, UI/job/command/API execution surfaces, interval-based due-sync orchestration, normalized snapshot ingestion, stable external-object-reference mapping, provider write execution auditing, a read-only operations dashboard, computed sync-health visibility, and the registry/action-routing plus enqueue fixes needed for provider-account operability; broader provider coverage and richer provider reporting remain pending
6. bulk generation and templating
7. change control / approvals
  Status: partially delivered for the initial Krill-backed slice through change-plan preview, approval, apply, audit history, maintenance-window metadata, ticket/change references, and approval-record persistence; rollback bundles, multi-stage approvals, and broader governance are still pending

### Phase 3: Expand routing-security scope
8. ASPA support
9. ROV impact simulation
10. IRR coordination
11. external validator overlays
12. downstream / on-behalf-of modeling

---

## 6. Recommended schema and architecture direction

### 6.1 Separate core object inventory from derived state
Keep a clean distinction between:
- **source objects**: ROAs, certificates, ASPAs, provider accounts
- **derived objects**: expected ROAs, lint results, reconciliation results, simulations
- **workflow objects**: plans, approvals, sync jobs, rollback bundles

This prevents the schema from turning into a plate of relational spaghetti.

### 6.2 Keep provider abstraction clean
Create an internal provider interface such as:
- `list_roas()`
- `list_aspas()`
- `get_certificates()`
- `create_change_plan()`
- `apply_change_plan()`

Even if only ARIN is implemented first, the abstraction should avoid provider-specific leakage into core business logic.

### 6.3 Prefer read-only synchronization before broad write-back
The safest sequence is:
1. import provider state
2. compare and report drift
3. generate proposed change plans
4. add approvals and dry-run simulation
5. only then expand write-back automation provider by provider

The plugin has now crossed that threshold for the initial Krill ROA slice: preview/approve/apply and post-apply re-sync are implemented. Additional provider write adapters should follow the same staged sequence rather than bypassing it.

### 6.4 Make results explainable
Operator trust improves when findings are plain and deterministic.

Good example:
- “ROA X authorizes 203.0.113.0/24 maxLength 28, but NetBox intent shows only 203.0.113.0/24 announced. RFC 9319 recommends minimal ROAs; this object is broader than necessary.” citeturn910174search2turn910174search11

Bad example:
- “Policy risk score = 73.”

---

## 7. Minimum viable implementation backlog

If engineering capacity is constrained, the best minimum viable implementation path is:

### MVP-1
- expected ROA derivation from NetBox prefixes + ASNs
- reconciliation report against locally stored ROAs
- ROA linting for `maxLength`
- lifecycle/expiry dashboard

**Current status:** mostly delivered except linting. Expected intent derivation, local reconciliation, operator drill-down views, draft change-plan generation, and an initial lifecycle/dashboard reporting slice are implemented.

### MVP-2
- ARIN import connector
- external object references
- sync history and diffs
- candidate change-plan object model

**Current status:** materially delivered for the first import slice and subsequent connector expansion. The candidate change-plan object model is implemented; normalized provider-import comparison state exists via `ProviderSnapshot` and `ImportedRoaAuthorization`; there are now live ARIN and Krill ROA import paths with provider-account configuration, sync history, operator-triggered UI/API/job/command execution surfaces, interval-based due-sync orchestration, stable external-object-reference tracking, provider sync-health visibility, and a read-only operations dashboard; and provider-account CRUD is operational again after the explicit registry/public-slug split. Krill-backed preview/approve/apply write-through and provider execution auditing are also now in place. Richer diff history and broader provider/object coverage are still pending.

### MVP-3
- ASPA model
- provider-relationship modeling
- dry-run validity simulation
- approval workflow

**Current status:** partially delivered for ROA change governance. A Krill-backed preview/approve/apply workflow exists for provider-backed ROA plans, and it now persists ticket/change references, maintenance-window metadata, and `ApprovalRecord` history; ASPA models, dry-run ROV simulation, rollback bundles, and broader governance workflows remain future work.

This sequence offers a good ratio of effort to operator value.

---

## 8. Explicit non-goals for the first implementation wave

To avoid scope creep, the following should probably **not** be first-wave goals:

- building a full RPKI CA implementation inside NetBox
- acting as a full relying-party validator
- deep BGP collector integration before core intent/reconciliation exists
- full multi-RIR write-back automation before import/diff is stable
- trying to represent every corner case in RFC semantics before delivering basic operator value

Hosted RPKI already outsources the cryptographic machinery; the plugin should focus on operator workflow and correctness. citeturn910174search4turn910174search9

---

## 9. Missing standards-based RPKI architecture elements to add to the data model

**Implementation status:** Implemented in the plugin data model and registry-driven scaffolding.

The section 9 schema work has been completed as an additive standards-aligned expansion of the existing plugin. The implementation introduced explicit model support for:

- repositories and publication points
- trust anchors, trust anchor locators, and trust anchor keys
- end-entity certificates
- a generic signed-object framework
- certificate revocation lists and revoked-certificate references
- manifests and manifest entries
- ASPAs and ASPA provider relationships
- RSCs and RSC file-hash members
- router certificates
- validator instances, validation runs, object validation results, and validated ROA/ASPA payload views

The implementation also added compatibility links from the legacy `Certificate` and `Roa` models into the newer architecture so the standards-based model can coexist with the original object families during the transition.

The current plugin models organizations, resource certificates, ROAs, and supporting prefix/ASN relationship tables. That is enough to represent a useful slice of origin-authorization inventory, but it is still much smaller than the standards-defined RPKI architecture. RFC 6480 defines the RPKI as both a certificate hierarchy for Internet number resources and a distributed repository system for storing and disseminating the data objects that comprise the RPKI and other signed objects needed for routing security. In other words, a complete model needs to capture not just “who owns what resources and what ROAs exist,” but also revocation, publication, object packaging, retrieval, rollover, and the broader family of signed objects that sit beside ROAs. See RFC 6480, RFC 6481, RFC 6488, the IANA RPKI registries, and the newer signed-object RFCs for the authoritative standards frame.  
**Defining references:** RFC 6480, RFC 6481, RFC 6488, IANA RPKI registries.

### 9.1 Certificate Revocation Lists (CRLs)
**Defining reference:** RFC 6481, Section 2; RFC 6487; RFC 8897, Section 3.

CRLs are not optional wallpaper in the RPKI repository model. RFC 6481 defines a publication point as containing certificates, CRLs, manifests, and signed objects, and RFC 8897 spells out relying-party requirements for validating and processing CRLs. A certificate-centric plugin that omits CRLs can say that a certificate exists, but it cannot faithfully represent whether that certificate remains trustworthy or has been revoked. For an operator-facing NetBox plugin, that means the current `Resource Certificate` model is carrying too much semantic weight by itself. Adding CRL support should spur a shift from treating certificates as standalone durable facts to treating them as revocable repository artifacts with freshness, issuance lineage, CRL number semantics, next-update expectations, and consistency relationships to publication points and manifests. Concretely, the model should gain a `CertificateRevocationList` object keyed to the issuing CA certificate, with fields for CRL number, thisUpdate, nextUpdate, publication URI, retrieval state, validation state, and relationship tables that allow certificates and EE certificates to be marked revoked by reference rather than by ad hoc status flags.

### 9.2 Manifests
**Defining reference:** RFC 6486; RFC 6481, Section 2; RFC 8897, Section 4.

A manifest is the repository’s table of contents with teeth. RFC 6486 defines the manifest signed object used to enumerate the objects expected at a CA publication point, along with hashes, so relying parties can detect missing, stale, substituted, or otherwise inconsistent repository contents. Without a manifest model, the plugin has no way to describe repository completeness or to answer whether the set of published ROAs and certificates is coherent as a published unit. Including manifests should therefore push the schema away from isolated object rows and toward publication-set semantics. In practice, that means adding a `Manifest` signed-object model, a `ManifestEntry` child table for filename and hash members, and explicit relationships from manifests to publication points, EE certificates, CRLs, and signed objects. It also means existing ROA and certificate models should stop assuming publication is implicit and instead carry references to the manifest and publication point that currently attest to their presence.

### 9.3 End-entity (EE) certificates for signed objects
**Defining reference:** RFC 6487; RFC 6488; RFC 9582 for ROAs.

ROAs and other RPKI signed objects are not signed directly by the long-lived resource certificate in the casual way a business application might imagine. The standards structure uses end-entity certificates to sign individual CMS-protected signed objects, and those EE certificates have their own profile constraints and validation significance. The plugin description hints at this relationship in prose, but it does not expose EE certificates as first-class data. That omission flattens an important layer of the architecture and makes it hard to express lifecycle, revocation, and signing relationships correctly. Adding EE certificates should spur a deliberate split between resource-holding CA certificates and object-signing EE certificates. The existing `Resource Certificate` model should remain the CA-layer object, while new signed-object records such as ROAs, manifests, ASPAs, RSCs, and Trust Anchor Keys should link to a dedicated `EndEntityCertificate` model carrying SKI/AKI, serial, validity, inherited-vs-enumerated resource constraints where applicable, issuer reference, and revocation linkage. This change would cleanly separate “certificate that delegates authority” from “certificate that signed this object instance.”

### 9.4 Repository publication points and retrieval topology
**Defining reference:** RFC 6480; RFC 6481; RFC 8182.

The standards architecture is emphatically not just a bag of signed objects. RFC 6480 and RFC 6481 define a distributed repository system with publication points, while RFC 8182 defines RRDP as a scaling-oriented retrieval protocol for repository content. If the plugin does not model publication points, object URIs, repository endpoints, or retrieval metadata, it cannot represent where authoritative objects live, how they are grouped, or how relying parties are expected to fetch them. For hosted-RPKI consumers this still matters, because hosted service does not erase publication mechanics; it merely outsources them. Adding this layer should push the plugin from a pure policy/inventory model toward a repository-aware one. The data model should gain entities such as `Repository`, `PublicationPoint`, `PublishedObjectLocation`, and optionally `RrdpSession`/`RrdpSnapshot` metadata. Existing certificate and ROA objects should then reference publication points and object URIs explicitly, rather than storing publication-related strings as loosely typed attributes on the certificate row.

### 9.5 Trust anchors, TALs, and trust-anchor rollover artifacts
**Defining reference:** RFC 6490; RFC 8630; RFC 9691.

The top of the RPKI tree is not just an abstract “signed by an RIR” notion. Trust anchors are distributed and consumed through specific artifacts and rollover procedures. RFC 6490 defines the Trust Anchor Locator (TAL), RFC 8630 updates the TAL format, and RFC 9691 defines the Trust Anchor Key signed object to support planned trust-anchor rollover without invalidating the tree. A data model that stops at resource certificates misses the root-of-trust mechanics that explain why and how a given certificate chain is grounded. Including this layer should spur two shifts. First, certificates should no longer carry only an `issuer` string but should be able to chain upward to an explicit `TrustAnchor` or parent CA object. Second, rollover should stop being an out-of-band concept and become modeled state. The plugin should add `TrustAnchor`, `TrustAnchorLocator`, and `TrustAnchorKey` entities, plus successor/predecessor relationships and publication metadata. That would let the schema represent not only today’s trust root but also staged rollover state and the repository locations that relying parties need to discover it.

### 9.6 Generic signed-object framework
**Defining reference:** RFC 6488; IANA RPKI Signed Objects registry.

The plugin today appears to privilege ROAs as a bespoke top-level object type. Standards-wise, that is too narrow. RFC 6488 defines the general signed-object template for the RPKI, and the IANA registry now enumerates multiple signed-object families including ROAs, manifests, RSCs, Trust Anchor Keys, and ASPAs. If the schema continues to model each one as a one-off special case, the plugin will accrue repetitive logic and structural inconsistency every time the standards family grows. Adding a generic signed-object abstraction should therefore cause a refactor of the existing ROA model, not merely the addition of new tables beside it. A parent `SignedObject` entity should capture content type, EE certificate, CMS/signature metadata, publication URI, filename, manifest membership, validation status, and parsed-vs-raw payload references. `ROA` would then become a typed child or extension record rather than the sole architectural pattern. That shift would make it much easier to add ASPA, Manifest, RSC, Ghostbusters, or future object types without re-laying the track each time.

### 9.7 Autonomous System Provider Authorizations (ASPAs)
**Defining reference:** IANA RPKI registries; draft-ietf-sidrops-aspa-profile (current SIDROPS working-group definition).

ASPA is the clearest standards-track object family absent from the current plugin and the one with the most immediate architectural relevance after ROAs. The current SIDROPS ASPA profile defines a CMS-protected object through which the holder of an AS authorizes one or more other ASes as transit providers, with the goal of improving route-leak detection and mitigation. For a cloud or other highly interconnected operator, ASPA models the commercial and topological reality of provider relationships in a way ROAs never can. Its inclusion should do more than add an `ASPA` table. It should prompt the plugin to elevate AS-relationship intent into the schema: customer ASN, authorized provider ASN set, validity intervals, publication metadata, and reconciliation against NetBox provider/circuit constructs. Existing ASN-related models should stop assuming ASNs matter only as ROA origins or certificate resources and start supporting provider-role semantics, planned-vs-published authorization state, and many-to-many provider relationship history.

### 9.8 RPKI Signed Checklists (RSCs)
**Defining reference:** RFC 9323.

RSCs extend the RPKI beyond routing origination and into attestation of arbitrary digital artifacts via resource-backed signatures. RFC 9323 defines them as signed checklists of hashes for one or more digital objects. Even if a hosted-RPKI consumer never deploys RSCs in the first implementation wave, they matter architecturally because they prove the plugin’s future should not be “ROAs plus a few odd extras,” but a common signed-object framework that can represent resource-backed attestations beyond route origination. Adding RSC support should therefore reinforce the refactor described above: a generic signed-object layer, a typed payload extension for checklist content, and manifest/publication relationships that parallel the rest of the repository model. It should also encourage the schema to support hash-set child tables and artifact references, which are different from prefix/ASN child rows and therefore useful pressure tests for whether the signed-object abstraction is truly general.

### 9.9 BGPsec Router Certificates
**Defining reference:** RFC 8209.

BGPsec router certificates sit at the edge of what many operators actually deploy today, but they are unquestionably part of the standards-based RPKI architecture. RFC 8209 defines the certificate profile used to validate Autonomous System path signatures in BGPsec. Their absence means the plugin currently models RPKI only as a route-origin authorization system and not as a broader routing-security PKI. Including router certificates should prompt a useful broadening of the certificate taxonomy. Instead of treating every certificate as a generic “resource certificate,” the data model should distinguish at least CA resource certificates, EE certificates for signed objects, and router certificates for BGPsec. This suggests introducing a certificate superclass or type discriminator, plus router-key-specific fields, ASN associations at the router-certificate layer, and links to device or logical-router inventory where appropriate. Even if implementation priority remains low, modeling the type cleanly would keep the schema aligned with the standards family rather than hard-coding today’s most common deployment pattern.

### 9.10 Relying-party and validated-payload view
**Defining reference:** RFC 8897; RFC 8210 / 8210bis family for cache-to-router exchange.

A publication-only model is still missing half the architecture that operators actually depend on in production: the relying-party view. RFC 8897 consolidates requirements for relying-party software, and the RPKI-to-router standards describe how validated payloads are exposed downstream to routers. The plugin does not need to become a full validator, but if it aims to represent the architecture rather than just object inventory, it should be able to model what a relying party believes about the published data. Including this element should shift the schema from “object exists” to “object validates, produces payloads, and has observable downstream effect.” That implies entities such as `ValidatorInstance`, `ValidationRun`, `ValidatedRoaPayload`, `ValidatedAspaPayload`, and `ObjectValidationResult`, along with timestamps, reason codes, local-policy outcomes, and optional router/cache export metadata. Existing ROA and certificate tables would then relate not only to authored objects but also to validation outcomes, which is where operational truth actually bites.

### 9.11 What this should change in the plugin’s core schema direction

Taken together, these missing elements argue for a broader schema refactor rather than a simple pile-on of new tables. The existing model is centered on three ideas: organization, resource certificate, and ROA. A more standards-aligned architecture would center on five layers instead:

1. **Authority layer:** trust anchors, parent/child CAs, resource certificates, router certificates.  
2. **Publication layer:** repositories, publication points, URIs, RRDP/rsync metadata.  
3. **Object layer:** generic signed objects plus typed payload extensions such as ROA, Manifest, ASPA, RSC, and Trust Anchor Key.  
4. **Integrity layer:** EE certificates, CRLs, manifest membership, revocation and freshness state.  
5. **Validation layer:** relying-party observations, validated payloads, and reconciliation results.

That five-layer shape would make the plugin much more faithful to the standards architecture and far more extensible for real operator workflows.

---

## 10. Final recommendation

The current plugin is already useful as a structured **RPKI object inventory extension** for NetBox. The highest-value evolution is to make it useful for the actual day job of a hosted-RPKI consumer:

- expressing routing-security intent
- checking that intent against published provider state
- identifying drift and unsafe policy
- scaling ROA/ASPA operations across a large prefix estate
- supporting safe, auditable change workflows

If only three follow-on features are implemented next, they should be:

1. **provider synchronization**
2. **ROA linting and safety analysis**
3. **change-plan maturation, approvals, and publication execution**

Within provider synchronization itself, the next increment should be:

1. external object references and stable provider-object identity tracking
2. richer provider dashboard/reporting surfaces built on the new sync-health and due-sync metadata
3. expansion from ARIN ROA import to additional provider/object families

Those three together would transform the plugin from a tidy cabinet of RPKI artifacts into something much closer to a routing-security control console.

---

## 11. Sources

1. TestPyPI project page for `netbox-rpki`, including current package description and documented models. citeturn301101view0
2. ARIN hosted RPKI overview and related ROA/ASPA management materials. citeturn910174search0turn910174search3turn910174search6turn910174search9turn910174search15turn910174search18
3. RIPE NCC hosted RPKI usage notes and API documentation. citeturn910174search1turn910174search4
4. RFC 9319 guidance on minimal ROAs and `maxLength`. citeturn910174search2turn910174search11
## 5. Engineering specification addendum: proposed Django/NetBox model architecture, relationship sketch, and migration order

This section reframes the backlog as an implementation-oriented specification. The goal is not to freeze every field name up front, but to give a coding agent a durable schema direction that supports the existing plugin models while opening a clean path toward standards-aligned RPKI object modeling, hosted-provider synchronization, and operator-grade reconciliation workflows.

### 5.1 Design principles for the next schema revision

#### Preserve current object identity where possible
The plugin already has recognizable top-level entities for organizations, resource certificates, and ROAs. Those should remain as stable conceptual anchors where practical so that existing records, URLs, and automation clients do not break unnecessarily. The migration strategy should therefore prefer **progressive normalization** over destructive renaming in the first major revision.

#### Separate cryptographic object identity from operator intent
The current model leans toward representing what an operator wants to keep track of. The next model needs to represent both **published cryptographic objects** and **operator intent derived from NetBox**. Those are not the same thing. A single intended authorization may correspond to multiple published signed objects over time, and a published object may become stale relative to intent without becoming invalid in a cryptographic sense.

#### Model the signed-object family explicitly
ROAs should stop being treated as an isolated special case. The RPKI standards family includes multiple signed-object types, each with common publication and signing semantics. The data model should therefore gain a generic signed-object framework so that ROAs, ASPAs, manifests, RSCs, and future object types can share common metadata and lifecycle handling.

#### Keep provider synchronization orthogonal to core RPKI semantics
Hosted-provider connectors should map external APIs into the internal schema, not define the schema. The plugin should avoid becoming “an ARIN client with some RIPE conditionals stapled on.” Provider-specific fields should live in provider-account, external-reference, and snapshot models, while the core object graph remains standards- and operator-centric.

The same separation principle now also applies inside the plugin registry: internal model/registry identity and public UI/API naming are explicit, separate contracts. That split was necessary to keep generated NetBox actions correct when Django model names intentionally differ from public route slugs.

#### Prefer additive migrations in early phases
A coding agent should bias toward additive migrations, compatibility shims, and data backfills in the first implementation wave. That reduces the chance of breaking existing plugin users while still allowing a later cleanup pass once the richer model stabilizes.

---

### 5.2 Proposed model families

The following model family layout is a suggested target architecture.

### A. Administrative / ownership layer

#### `RPKIOrganization`
Successor or compatibility-preserving evolution of the current `Organization` model.

**Purpose**  
Represents the administrative entity consuming RPKI services or owning the internal policy domain.

**Suggested key fields**
- `slug`
- `name`
- `org_id`
- `description`
- `website_url`
- `parent_rir_asn` or renamed reference to current `parent_rir`
- `status`
- `comments`

**Relationship notes**
- one-to-many to provider accounts
- one-to-many to CA/resource certificates
- one-to-many to intent profiles and change requests

**Why this is a schema pivot**  
This object should stop being just a decorative top-level record and become the root administrative namespace for provider accounts, policy profiles, trust relationships, and approvals.

#### `ProviderAccount`
Represents a hosted-RPKI account or tenancy at ARIN, RIPE NCC, APNIC, or another provider.

**Suggested key fields**
- `organization` FK to `RPKIOrganization`
- `provider_type` enum such as `arin`, `ripe`, `apnic`, `other`
- `account_identifier`
- `display_name`
- `api_base_url`
- `credentials_reference`
- `sync_enabled`
- `last_successful_sync`
- `last_sync_status`

**Relationship notes**
- one-to-many to provider snapshots
- one-to-many to external object references
- optional one-to-many to managed downstream relationships

**Why it matters**  
This keeps provider API state out of the core certificate/ROA tables and allows one organization to span multiple RIRs or multiple accounts cleanly.

#### `ManagedAuthorizationRelationship`
Represents a provider-managed or on-behalf-of relationship for downstream resources.

**Suggested key fields**
- `provider_organization` FK
- `downstream_name`
- `downstream_identifier`
- `relationship_type`
- `starts_at`
- `ends_at`
- `is_active`
- `notes`

**Why it matters**  
This adds a place to model the real-world fact that providers often manage ROAs or policy workflows on behalf of customers without collapsing legal resource ownership, cryptographic authority, and operational responsibility into one muddy field.

---

### B. Resource authority / certificate hierarchy layer

#### `CertificateAuthorityNode`
A new model representing a node in the CA hierarchy, regardless of whether it is a trust anchor, intermediate CA, or customer/resource CA.

**Suggested key fields**
- `name`
- `organization` FK nullable
- `node_type` enum: `trust_anchor`, `rir_ca`, `member_ca`, `delegated_ca`, `hosted_service_ca`
- `subject`
- `issuer`
- `serial`
- `ski`
- `aki`
- `valid_from`
- `valid_to`
- `publication_uri`
- `ca_repository_uri`
- `rrdp_notify_uri`
- `is_self_hosted`
- `status`

**Relationship notes**
- self-referential parent FK for hierarchy
- one-to-many to resource certificates
- one-to-many to CRLs
- one-to-many to manifests

**Why this should reshape the existing model**  
The current `Resource Certificate` object appears to combine CA-ish hierarchy semantics with operator bookkeeping. Introducing `CertificateAuthorityNode` gives the model a proper hierarchy backbone. Existing resource-certificate records can initially map one-to-one into CA nodes plus resource certificates, then gradually decouple if needed.

#### `ResourceCertificate`
A refined successor to the current `Resource Certificate` model, focused on the actual resource-bearing certificate rather than every possible CA concern.

**Suggested key fields**
- `ca_node` FK to `CertificateAuthorityNode`
- `organization` FK
- `name`
- `serial`
- `subject`
- `issuer`
- `public_key`
- `private_key_reference` rather than raw private key if possible
- `valid_from`
- `valid_to`
- `auto_renews`
- `publication_url`
- `status`
- `source_of_truth` enum: `manual`, `provider_sync`, `derived`, `imported`

**Relationship notes**
- many-to-many through tables to prefixes and ASNs
- one-to-many to EE certificates
- one-to-many to signed objects via EE certs or direct resource relationship

**Why this should change the existing model**  
The existing model likely stores too much directly and too little structurally. Splitting CA-node hierarchy from the resource certificate proper allows certificate lineage, publication, and delegation relationships to be represented cleanly.

#### `CertificateResourcePrefix`
Through model linking a `ResourceCertificate` to a NetBox prefix or abstract prefix range.

**Suggested key fields**
- `resource_certificate` FK
- `prefix` FK to NetBox `Prefix` when resolvable
- `prefix_cidr_text` fallback for out-of-band imported values
- `max_length_authorized` nullable
- `source`

#### `CertificateResourceASN`
Through model linking a `ResourceCertificate` to an ASN.

**Suggested key fields**
- `resource_certificate` FK
- `asn` FK to NetBox ASN or integer surrogate field
- `source`

**Why these should evolve the current hidden tables**  
The plugin already has certificate-prefix and certificate-ASN relationship objects. These should be promoted from hidden support tables into deliberate, queryable resource-entitlement models because later reconciliation, publication, and validation logic will depend on them heavily.

---

### C. Signed-object framework layer

#### `SignedObject`
A new generic superclass or concrete base model for all RPKI signed objects.

**Suggested key fields**
- `object_type` enum: `roa`, `aspa`, `manifest`, `crl`, `rsc`, `ghostbusters`, `bgpsec_router_cert`, `tak`, `other`
- `name`
- `display_label`
- `organization` FK
- `resource_certificate` FK nullable
- `ee_certificate` FK nullable
- `publication_point` FK nullable
- `filename`
- `object_uri`
- `repository_uri`
- `content_hash`
- `serial_or_version`
- `valid_from`
- `valid_to`
- `publication_status`
- `origin_source` enum: `manual`, `provider_sync`, `computed`, `validator_ingest`
- `external_reference` optional FK
- `raw_payload_reference`

**Relationship notes**
- one-to-one from concrete object models such as `ROA`, `ASPA`, `Manifest`
- one-to-many to validation observations and reconciliation artifacts

**Why this changes the data model materially**  
This is the hinge point for future-proofing. Once this exists, ROAs stop being a one-off special entity and become one signed-object species among several. That will simplify publication tracking, history, imports, and external references across all object types.

#### `EndEntityCertificate`
Represents the EE certificate associated with a signed object.

**Suggested key fields**
- `resource_certificate` FK to parent resource certificate
- `subject`
- `issuer`
- `serial`
- `ski`
- `aki`
- `valid_from`
- `valid_to`
- `public_key`
- `status`

**Relationship notes**
- one-to-one or one-to-many to `SignedObject` depending on parsing/import model

**Why it matters**  
This closes a structural gap between “resource certificate exists” and “ROA exists.” It gives the model a place to represent the actual signing identity used by each signed object and supports future validation/debug workflows.

#### `PublicationPoint`
Represents a repository publication point or retrieval locus.

**Suggested key fields**
- `name`
- `organization` FK nullable
- `provider_account` FK nullable
- `publication_uri`
- `rsync_base_uri`
- `rrdp_notify_uri`
- `repository_type`
- `status`
- `last_observed_at`

**Relationship notes**
- one-to-many to signed objects
- one-to-many to manifests and CRLs

**Why it matters**  
The current model has publication-related fields on certificates, but publication is a first-class architectural concept and should not remain smeared across unrelated objects.

#### `Manifest`
Concrete signed-object subtype.

**Suggested key fields**
- `signed_object_ptr` one-to-one to `SignedObject`
- `manifest_number`
- `this_update`
- `next_update`

#### `ManifestEntry`
Files enumerated by a manifest.

**Suggested key fields**
- `manifest` FK
- `filename`
- `hash_algorithm`
- `file_hash`
- `object_type_guess`
- `linked_signed_object` nullable FK

**Why these matter**  
Adding manifests should spur movement away from thinking of repository state as “whatever rows happen to exist in our ROA table” and toward explicit modeling of publication completeness and object membership.

#### `CertificateRevocationList`
Concrete signed-object subtype for CRLs.

**Suggested key fields**
- `signed_object_ptr` one-to-one to `SignedObject`
- `crl_number`
- `this_update`
- `next_update`
- `issuer`

#### `RevokedCertificateEntry`
Represents a serial revoked by a CRL.

**Suggested key fields**
- `crl` FK
- `revoked_serial`
- `revocation_date`
- `reason_code`
- `linked_resource_certificate` nullable FK
- `linked_ee_certificate` nullable FK

**Why these matter**  
CRLs should force the plugin to stop treating certificate rows as implicitly valid until `valid_to`. Revocation creates a parallel lifecycle dimension that should be queryable and visible.

---

### D. Routing authorization layer

#### `ROA`
Refactor the current ROA model into a concrete subtype hanging from `SignedObject`.

**Suggested key fields**
- `signed_object_ptr` one-to-one to `SignedObject`
- `origin_asn` FK or integer field supporting ASN 0 policy representation via explicit handling
- `signed_by_resource_certificate` FK retained for convenience if helpful
- `is_as0`
- `remarks`

**Relationship notes**
- one-to-many to `ROAPrefixAuthorization`
- many-to-one to intent and reconciliation objects

**Why this should alter the current model**  
The current model likely stores validity and signing information directly on the ROA row. That can remain for compatibility during migration, but the durable shape is for publication/lifecycle/signature metadata to move to `SignedObject`, leaving ROA-specific semantics on the ROA subtype.

#### `ROAPrefixAuthorization`
Successor to the current ROA prefix relationship model.

**Suggested key fields**
- `roa` FK
- `prefix` FK to NetBox `Prefix` nullable
- `prefix_cidr_text`
- `max_length`
- `address_family`

#### `ROAIntent`
Represents a desired authorization derived from NetBox intent.

**Suggested key fields**
- `organization` FK
- `prefix` FK to NetBox Prefix
- `origin_asn` FK or integer
- `max_length`
- `intent_profile` FK
- `scope_site` nullable FK
- `scope_region` nullable FK
- `scope_tenant` nullable FK
- `scope_vrf` nullable FK
- `is_active`
- `derived_from_rule`

#### `ROAReconciliationResult`
Stores comparison outcomes between intended and published state.

**Suggested key fields**
- `roa_intent` FK
- `matched_roa` nullable FK
- `result_type` enum: `match`, `missing`, `asn_mismatch`, `prefix_mismatch`, `max_length_risky`, `orphaned`, `stale`
- `severity`
- `details_json`
- `computed_at`

**Why these should reshape the schema**  
Introducing explicit intent rows means the plugin can stop overloading the ROA table with both “what exists” and “what we wish existed.” That separation is essential for sane reconciliation logic.

---

### E. ASPA / provider-authorization layer

#### `ASPA`
Concrete signed-object subtype.

**Suggested key fields**
- `signed_object_ptr` one-to-one to `SignedObject`
- `customer_asn`
- `remarks`

#### `ASPAProviderAuthorization`
Represents each provider ASN authorized by the ASPA.

**Suggested key fields**
- `aspa` FK
- `provider_asn`
- `provider_name` optional denormalized field
- `sequence_index` optional

#### `ASPAIntent`
Derived or operator-authored desired provider authorization set.

**Suggested key fields**
- `organization` FK
- `customer_asn`
- `provider_asn`
- `provider_account` nullable FK
- `circuit` nullable FK if NetBox circuits binding is added
- `intent_profile` FK
- `is_active`

#### `ASPAReconciliationResult`
Comparison of intended vs published provider relationships.

**Why these matter**  
ASPA support should not be bolted onto ROA tables as an ASN-to-ASN side table. It deserves a first-class family because its semantics are relationship-set based, not prefix-authorization based.

---

### F. Validation / observation / external evidence layer

#### `ProviderSnapshot`
Stores a sync-time snapshot envelope from a hosted provider.

**Suggested key fields**
- `provider_account` FK
- `snapshot_type`
- `fetched_at`
- `source_etag`
- `source_version`
- `status`
- `raw_response_reference`

#### `ExternalObjectReference`
Maps internal objects to provider-side or imported identifiers.

**Suggested key fields**
- `provider_account` FK
- `external_id`
- `external_type`
- `internal_content_type`
- `internal_object_id`
- `last_seen_at`

#### `VRPSnapshot`
Represents validated ROA payload snapshots ingested from a validator or external pipeline.

**Suggested key fields**
- `snapshot_label`
- `source_system`
- `fetched_at`
- `status`

#### `ValidatedPayload`
Represents an individual validated prefix-origin tuple.

**Suggested key fields**
- `vrp_snapshot` FK
- `prefix_cidr_text`
- `origin_asn`
- `max_length`
- `source_signed_object` nullable FK

#### `ValidationObservation`
Observed validation state for a route, prefix, or object.

**Suggested key fields**
- `observed_prefix` FK or text
- `observed_origin_asn`
- `validation_state` enum: `valid`, `invalid`, `not_found`
- `reason_code`
- `evidence_source`
- `observed_at`
- `linked_roa` nullable FK
- `linked_signed_object` nullable FK

**Why these should reshape the existing model**  
Once observed and validated state exists, the current object tables can stop pretending that local inventory is the full truth. The plugin becomes capable of showing intended, published, and validated realities side by side.

---

### G. Workflow / planning / audit layer

#### `IntentProfile`
Policy profile used to derive ROA or ASPA intent.

**Suggested key fields**
- `name`
- `organization` FK
- `profile_type` enum
- `rule_expression` or reference
- `is_default`
- `notes`

#### `ChangePlan`
A generic umbrella for proposed modifications to published RPKI state.

**Suggested key fields**
- `organization` FK
- `provider_account` nullable FK
- `plan_type` enum: `roa`, `aspa`, `mixed`
- `status` enum: `draft`, `proposed`, `approved`, `rejected`, `published`, `rolled_back`
- `created_by`
- `submitted_at`
- `approved_at`
- `ticket_reference`
- `maintenance_window`
- `summary`

#### `ChangePlanItem`
Individual create/update/delete actions inside a plan.

**Suggested key fields**
- `change_plan` FK
- `action_type`
- `target_object_type`
- `target_object_id`
- `before_state_json`
- `after_state_json`
- `impact_summary`

#### `ApprovalRecord`
Review / approval evidence.

#### `LintResult`
Reusable linting table applicable to ROAs, ASPAs, or future objects.

#### `SimulationResult`
Stores dry-run ROV outcome estimates.

**Why this matters**  
These workflow tables prevent the core object tables from turning into a swamp of status flags and partial publication metadata. Plans, linting, and approvals deserve their own layer.

---

### 5.3 Suggested foreign-key sketch

Below is the core relationship shape in prose.

- `RPKIOrganization` owns many `ProviderAccount`, `CertificateAuthorityNode`, `ResourceCertificate`, `IntentProfile`, and `ChangePlan` rows.
- `CertificateAuthorityNode` forms a parent/child tree and owns many `ResourceCertificate`, `Manifest`, and `CertificateRevocationList` rows.
- `ResourceCertificate` owns many `CertificateResourcePrefix`, `CertificateResourceASN`, and `EndEntityCertificate` rows.
- `EndEntityCertificate` signs one or more `SignedObject` rows.
- `SignedObject` is the generic parent of `ROA`, `ASPA`, `Manifest`, `CertificateRevocationList`, `RSC`, and later object types.
- `PublicationPoint` owns many `SignedObject` rows and is optionally linked to `ProviderAccount`.
- `ROA` owns many `ROAPrefixAuthorization` rows.
- `ASPA` owns many `ASPAProviderAuthorization` rows.
- `ROAIntent` and `ASPAIntent` derive from NetBox state and are compared to published `ROA` and `ASPA` rows via reconciliation tables.
- `ProviderSnapshot` and `ExternalObjectReference` connect hosted-provider APIs to internal objects without polluting the core object model.
- `VRPSnapshot`, `ValidatedPayload`, and `ValidationObservation` represent validator or telemetry evidence.
- `ChangePlan`, `ChangePlanItem`, `LintResult`, and `SimulationResult` capture human workflow and pre-publication analysis.

---

### 5.4 Migration order

A coding agent should not attempt to build every table in one dramatic schema meteor strike. The safer path is phased.

#### Phase 1: Normalize the current core without breaking existing records

**Objective**  
Preserve the current `Organization`, `Resource Certificate`, and `ROA` functionality while introducing compatibility-friendly successor structures.

**Recommended migrations**
1. Add `RPKIOrganization` as either a rename target or compatibility alias of the current `Organization` table.
2. Add `ProviderAccount`.
3. Add `CertificateAuthorityNode`.
4. Extend `ResourceCertificate` with explicit linkage to `CertificateAuthorityNode` and add `source_of_truth` metadata.
5. Promote certificate-prefix and certificate-ASN support tables into explicitly modeled resources if they are not already first-class ORM models.
6. Add `PublicationPoint`.

**Backfill steps**
- create a `CertificateAuthorityNode` row for each existing resource certificate if no better CA hierarchy data exists yet
- backfill publication URI fields from current certificate attributes
- map current organization rows to the new naming/namespace scheme

**Compatibility rule**  
Do not yet refactor the current ROA table into a subtype if that would break forms or API consumers immediately.

#### Phase 2: Introduce signed-object generalization

**Objective**  
Create a common base for ROAs and future signed objects.

**Recommended migrations**
1. Add `SignedObject`.
2. Add `EndEntityCertificate`.
3. Add nullable one-to-one from existing `ROA` rows to `SignedObject`.
4. Migrate validity, publication, and external-reference style metadata from ROA into `SignedObject` where possible.
5. Add `ROAPrefixAuthorization` as the explicit successor to any hidden ROA prefix table.

**Backfill steps**
- create one `SignedObject` per existing ROA
- create placeholder `EndEntityCertificate` rows only if the source data supports it; otherwise allow null and mark as unknown

**Compatibility rule**  
Keep old ROA fields readable during this phase even if the canonical values begin moving to the signed-object layer.

#### Phase 3: Add standards-missing architectural objects

**Objective**  
Close the largest gaps against the broader RPKI architecture.

**Recommended migrations**
1. Add `Manifest` and `ManifestEntry`.
2. Add `CertificateRevocationList` and `RevokedCertificateEntry`.
3. Add trust-anchor-related modeling if implemented as `CertificateAuthorityNode(node_type='trust_anchor')` plus optional TAL artifact table.
4. Add `RSC` and other signed-object subclasses only after the generic base is stable.

**Backfill steps**
- no speculative backfill for manifests/CRLs if data is unavailable
- allow import-only population first

#### Phase 4: Add operator intent and reconciliation

**Objective**  
Make the plugin useful as an operational policy layer, not just a repository of imported objects.

**Implementation status:** Largely completed for the first operational slice. The Priority 1 operator-intent layer is present under the names `RoutingIntentProfile`, `RoutingIntentRule`, `ROAIntentOverride`, `IntentDerivationRun`, `ROAIntent`, `ROAIntentMatch`, `ROAReconciliationRun`, `ROAIntentResult`, and `PublishedROAResult`; execution is implemented through a service layer, NetBox job runner, management command, and API trigger; provider-backed comparison is implemented against normalized imported snapshot rows; custom detail UX exists for dashboard/drill-down/diff flows; and draft ROA change plans can now be created from completed reconciliation runs. ASPA intent/reconciliation, live provider ingestion, richer approvals/write-back, and lint/simulation workflows remain future work.

**Recommended migrations**
1. Add `IntentProfile`.
2. Add `ROAIntent` and `ROAReconciliationResult`.
3. Add `ASPA`, `ASPAProviderAuthorization`, `ASPAIntent`, and `ASPAReconciliationResult`.
4. Add `LintResult` and `SimulationResult`.

**Backfill steps**
- derive initial ROA intent from selected NetBox prefixes, ASNs, tags, and policy defaults
- leave ASPA intent empty until provider/upstream relationships are modeled or imported

#### Phase 5: Add provider sync and validation evidence

**Objective**  
Bind the schema to real hosted-provider state and validator observations.

**Implementation status:** Partially completed with live ARIN ROA import and Krill ROA import/write paths. `RpkiProviderAccount`, `ProviderSyncRun`, `ProviderSnapshot`, `ExternalObjectReference`, and `ProviderWriteExecution` now support normalized provider snapshots, stable provider-object identity tracking, operator-triggered sync from UI/API/command/job surfaces, interval-based due-sync orchestration, computed sync-health visibility, a read-only operations dashboard, and auditable Krill change-plan preview/apply flows; the provider-account UI path is operational after the generated-action routing fix, and the sync enqueue path now correctly avoids invalid job-object binding. Validator evidence, richer provider-reporting surfaces, and broader provider/object coverage remain to be built.

**Recommended migrations**
1. Add `ProviderSnapshot` and `ExternalObjectReference`.
2. Add `VRPSnapshot`, `ValidatedPayload`, and `ValidationObservation`.
3. Add sync-job and health-check tracking models if implemented separately.

#### Phase 6: Add workflow and approval semantics

**Objective**  
Support safe publication pipelines and operator governance.

**Implementation status:** Partially completed through the first provider-backed execution slice. `ROAChangePlan`, `ROAChangePlanItem`, and `ApprovalRecord` exist, can be generated or populated from reconciliation and approval results, and now support preview/approve/apply state transitions plus `ProviderWriteExecution` audit history, ticket/change references, and maintenance-window semantics for Krill-backed writes; rollback, multi-stage approvals, and broader governance workflows are still pending.

**Recommended migrations**
1. Add `ChangePlan`, `ChangePlanItem`, and `ApprovalRecord`.
2. Add rollback and publication-state support if distinct from plan status.
3. Integrate with NetBox permissions and object-level change logging.

---

### 5.5 Compatibility and deprecation guidance

#### Existing `Resource Certificate` model
Keep it, but progressively refocus it on actual resource-bearing certificate semantics. Fields that really describe repository structure or provider integration should migrate outward into `CertificateAuthorityNode`, `PublicationPoint`, and `ExternalObjectReference`.

#### Existing `ROA` model
Keep it as a stable user-facing concept, but make it a concrete subtype hanging from `SignedObject`. Over time, fields like validity and publication URI should become inherited or delegated from the signed-object layer.

#### Existing hidden relation tables
The current hidden ROA/certificate prefix/ASN support tables should be promoted into explicit first-class ORM models with clear API exposure, because later reconciliation logic will depend on them as more than mere implementation details.

#### Private key storage
The existing package description includes a `private_key` field on resource certificates. A coding agent should treat that as a design smell for hosted-RPKI-oriented deployments. The schema should move toward `private_key_reference`, secret-store integration, or explicit nullability where keys are provider-managed and never locally present.

---

### 5.6 Suggested implementation sequence for a coding agent

If the coding agent needs an opinionated order of attack, use this one:

1. stabilize current models and add tests around existing CRUD behavior
2. add `ProviderAccount`, `CertificateAuthorityNode`, and `PublicationPoint`
3. promote prefix/ASN relation tables into explicit resource-entitlement models
4. add `SignedObject` and connect existing ROAs to it
5. add `EndEntityCertificate`
6. add `ROAIntent` and read-only reconciliation views
  Status: completed for the initial ROA intent/reconciliation data-model layer, generated surfaces, derivation/reconciliation execution service, NetBox job runner, management command, API trigger, provider-backed comparison schema, custom detail UX, and draft change-plan generation
7. add hosted-provider import and external object references
  Status: partially completed. The repo now has `RpkiProviderAccount`, `ProviderSyncRun`, `ProviderSnapshot`, `ImportedRoaAuthorization`, `ExternalObjectReference`, real ARIN and Krill ROA import connectors with command/job/API execution, interval-based due-sync orchestration, provider sync-health visibility, and an initial operations dashboard; provider-account CRUD is operational after the generated-action routing fix; broader multi-provider/object coverage and richer provider diff/reporting are still pending
8. add `ASPA` object family
9. add manifests and CRLs
10. add linting, simulation, and change-plan workflows
  Status: partially completed. ROA-specific draft change plans exist, along with approval persistence and governed Krill write-through, but linting, simulation, rollback, and generalized workflow state do not
11. add validator/VRP observation support
12. clean up deprecated fields only after at least one stable release with compatibility shims

---

### 5.7 NetBox integration notes

#### Prefer NetBox-native references where semantically correct
Use NetBox `Prefix`, `ASN`, `Tenant`, `VRF`, `Site`, `Region`, `Provider`, and `Circuit` references where those objects express operator intent directly. Avoid duplicating those domains inside the plugin unless external imported values cannot be mapped cleanly.

#### Use denormalized text fallback fields for imported-but-unmapped values
Hosted-provider imports and validator evidence will sometimes refer to objects not yet present in NetBox. For those cases, dual-field patterns such as `prefix` FK plus `prefix_cidr_text` fallback are preferable to forcing lossy imports.

#### Be careful with generic foreign keys
Generic relations may be tempting for “bind anything to anything” policy scope, but they make API and query ergonomics worse. Prefer explicit FK scope fields for the first wave: `tenant`, `vrf`, `site`, `region`, and perhaps `provider`.

---

### 5.8 Testing expectations

A coding agent implementing this design should build test coverage in the following layers:

- migration/backfill tests for existing data
- model validation tests for ROA, ASPA, CRL, and manifest relationships
- reconciliation tests comparing intent vs published state
- provider import mapping tests with mocked ARIN/RIPE payloads
- API surface-contract tests proving each registered object exposes only the list/detail/custom methods its spec allows
- permission tests for approval and change-plan workflows
- registry-wide UI surface-contract tests proving every generated list/detail page and row-action set matches the object's supported Add/Edit/Delete affordances
- the dedicated release gate in `devrun/work_in_progress/netbox_rpki_surface_contract_checklist.md` should be updated and satisfied for any registry or generated-surface refactor

---

### 5.9 Final architectural recommendation

The most important structural shift is this: stop treating the plugin as “a few forms for ROAs and certificates” and start treating it as a layered model with distinct domains for:

1. administrative ownership and provider accounts
2. certificate/resource authority hierarchy
3. generic signed objects and repository publication
4. routing authorization semantics such as ROAs and ASPAs
5. operator intent and reconciliation
6. external validation evidence
7. workflow, change control, and approvals

Once that separation exists, the plugin can grow in a controlled way instead of accreting special-purpose fields onto the current ROA and certificate tables like barnacles on a tugboat.
