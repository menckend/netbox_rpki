# NetBox RPKI Plugin: External Validator and Telemetry Overlays Plan

Prepared: April 14, 2026

## Objective

Implement backlog Priority 11 as an additive operator-overlay layer that correlates:

1. authored ROA and ASPA objects
2. imported provider state and publication evidence
3. external relying-party validator observations
4. external BGP telemetry observations

The target is not a full relying-party validator or a full routing-telemetry platform inside the plugin.

The target is an operator-facing evidence layer that lets a user answer three practical questions in one workflow:

1. what the plugin intended or authored
2. what the provider appears to have published
3. what outside validators and route-visibility sources appear to observe

This document carries the detailed proposed contracts, model evolution, service expectations, surface contracts, and execution slicing for Priority 11. The backlog remains the short status-and-priority view.

## Relationship To Existing Architecture

This plan must stay aligned with the plugin's current architecture rules:

- Django models and migrations remain explicit.
- Standard read and CRUD surfaces remain registry-driven where they fit.
- Workflow behavior stays in explicit services, jobs, commands, and custom actions.
- Imported provider evidence, authored objects, and validation overlays should connect through intentional relationships rather than loose string matching in views.
- External overlays should enrich existing reconciliation, dashboard, and change-review workflows instead of creating a second operator universe.

This plan builds on four existing substrates that already exist in the codebase:

1. standards-oriented validation models:
   - `ValidatorInstance`
   - `ValidationRun`
   - `ObjectValidationResult`
   - `ValidatedRoaPayload`
   - `ValidatedAspaPayload`
2. authored and normalized object linkage around `SignedObject`, `Roa`, and `ASPA`
3. imported provider-publication evidence:
   - `ImportedPublicationPoint`
   - `ImportedSignedObject`
   - `ImportedCertificateObservation`
4. operator-facing dashboard, reconciliation, and change-review surfaces that already summarize sync, intent drift, lint, simulation, and provider execution state

## Current-State Baseline

The plugin already has useful schema groundwork, but it does not yet have an operator workflow for external overlays.

### Existing Validation Groundwork

Existing validation objects:

- `ValidatorInstance`
- `ValidationRun`
- `ObjectValidationResult`
- `ValidatedRoaPayload`
- `ValidatedAspaPayload`

Existing validation surfaces:

- registry-driven list, detail, API, and GraphQL exposure for all five validation object families
- `SignedObject` detail pages already render related `ObjectValidationResult` rows
- `ROA` and `ASPA` detail pages already render related validated payload tables
- factories and focused tests already prove the validation-link substrate exists

Current limitations of that substrate:

- no validator adapter or import service exists
- no normalized summary contract exists for validator runs beyond basic status fields
- no workflow ties validator data into reconciliation, dashboard, or change review
- no conservative matching contract exists for imported provider objects that do not already map cleanly to authored signed objects

### Existing Provider-Evidence Groundwork

The provider-sync layer already imports and retains publication evidence for:

- publication points
- signed-object inventory
- certificate observations

That evidence already exposes linkage and evidence summaries through UI, REST, and GraphQL surfaces.

Current limitation:

- provider evidence is visible, but not yet correlated with validator observations or route-visibility evidence in a single operator review flow

### Existing Dashboard and Workflow Groundwork

The plugin already has operator-facing surfaces for:

- operations dashboard health rollups
- ROA reconciliation detail and plan review
- ASPA reconciliation detail and plan review
- lint and simulation review for ROA change plans

Current limitation:

- those surfaces do not yet answer whether published or intended state is visible and valid from external observation points

### Missing Capability At Priority 11

Priority 11 remains open because the plugin still lacks:

- validator-run ingestion
- BGP telemetry ingestion
- historical retention and freshness reporting for those external evidence feeds
- stable cross-source correlation across authored objects, imported provider evidence, validator results, and route observations
- dashboard and change-review overlays that present the result in operator terms

## Design Boundaries

The implementation should stay inside these boundaries unless a later design pass explicitly changes them.

- Do not build a full validator engine inside the plugin.
- Do not make live provider calls a prerequisite for external overlay usefulness.
- Do not turn Priority 11 into a streaming telemetry warehouse or time-series platform.
- Keep validator import and telemetry import additive. They should enrich existing workflows, not replace reconciliation or provider sync.
- Keep first-wave approval semantics informational. External overlays should inform operators in the first wave, but they should not block approval or apply.
- Retain historical runs from the first wave so operators can reason about freshness, churn, and change over time.
- Keep both ROA and ASPA in scope for the first wave. Do not land a ROA-only external-overlay contract that would force an ASPA-specific redesign later.
- Preserve peer and AS-path detail for first-wave BGP telemetry. ASPA usefulness depends on more than aggregate prefix-origin visibility.

## Resolved First-Wave Decisions

The following design questions are considered resolved for the first implementation wave.

### 1. Priority 11 includes both validator observations and BGP telemetry

The first wave covers both:

- external relying-party validator observations
- external BGP telemetry overlays

That means the plan must not stop at VRP import alone. It must also provide an additive route-observation substrate that can be correlated back to ROA and ASPA posture.

### 2. ROA and ASPA are both in scope in the first wave

Do not plan a ROA-only contract.

The first implementation wave must preserve a common operator shape across both object families:

- validator payload evidence for ROA and ASPA
- route-visibility evidence relevant to ROA and ASPA review
- dashboard and drill-down correlation for both families

The exact level of UI polish can still land incrementally, but the model and service contracts should not assume ASPA is a later redesign.

### 3. Existing validation models remain the primary validator-ingest persistence layer

The first wave should continue using these as the canonical validator-ingest records:

- `ValidatorInstance`
- `ValidationRun`
- `ObjectValidationResult`
- `ValidatedRoaPayload`
- `ValidatedAspaPayload`

Do not introduce a second parallel validator-run hierarchy unless a concrete mismatch proves it necessary.

### 4. Historical validator and telemetry runs are required in the first wave

The first wave must retain historical runs rather than only projecting the latest external state.

That is required so operators can answer:

- is this external observation current
- when did the posture change
- is the observed issue stable, stale, or transient
- did a recent provider or change-plan action improve or worsen external posture

### 5. First-wave BGP telemetry preserves peer and path detail

The canonical telemetry contract for the first wave must retain more than aggregate prefix-origin visibility.

At minimum, first-wave telemetry must preserve:

- prefix
- origin ASN
- peer or vantage identity where available
- collector identity or source label
- AS path text and normalized path components where available
- observation timestamps and freshness data

This is necessary because ASPA analysis depends on path context, not only origin visibility.

### 6. External overlays remain informational in the first wave

In the first implementation wave, external validator and telemetry findings are operator evidence, not approval gates.

That means:

- change review should surface external posture clearly
- dashboards should highlight concerning observations clearly
- APIs and GraphQL should expose the evidence cleanly
- approval and apply flows should not block on this data in the first wave

### 7. Routinator is the first validator adapter

The first validator-ingest slice should target Routinator.

Reason:

- it matches the current operator direction for Priority 11 kickoff
- it is already present in the local Docker images used for plugin development
- it lets the first validator-import slice land against a concrete, locally testable source instead of a placeholder adapter abstraction only

Implications for the first implementation slice:

- `ValidatorInstance` rows should explicitly support Routinator as the first concrete validator source
- the first validator adapter in `services/external_validation.py` should normalize Routinator output into the existing validation-run model family
- the adapter should support both live Routinator API ingestion and exported snapshot ingestion, with the live API path treated as the preferred first-wave operating mode
- focused tests should include a Routinator-specific fixture or adapter payload contract rather than only generic validator mocks

### 8. Routinator ingest supports both live API and exported snapshots, with live API preferred

The first Routinator implementation should support both:

- live Routinator API ingestion as the preferred first-wave path
- exported snapshot ingestion as an additive fallback and fixture-friendly import path

Reason:

- the live API path best matches the intended operator workflow and the local Docker-based development environment
- exported snapshots provide a lower-friction fixture source for tests and a fallback path when direct API access is not the right integration mode
- supporting both early avoids baking a one-path adapter contract into the validation model family

Implications for Slice 1:

- design the Routinator adapter around one normalized internal payload contract, with both live API and snapshot loaders feeding that same normalization path
- treat live API polling or fetch as the preferred operational mode in jobs and UI wording
- keep snapshot import available for fixtures, deterministic tests, and environments where live API access is not the chosen operating model

### 9. The canonical Routinator first-wave normalization target is the bulk `jsonext` feed

The first live Routinator normalization target should be the bulk `GET /jsonext` response shape, with the exported `vrps --format jsonext` output treated as the equivalent snapshot form of the same contract.

Reason:

- the first wave requires full validation-run import rather than per-route point queries
- `jsonext` is the documented bulk shape that carries both ROA and ASPA payload families in one response object when the validator is configured to expose them
- `jsonext` includes source-provenance details such as TAL, object URI, validity, chain-validity, and stale timing, which gives the plugin a conservative basis for linking observations back to authored `SignedObject` rows and imported `ImportedSignedObject` evidence
- the lighter `json` shape is useful, but it drops the source detail needed for the object-level correlation contract this plan expects
- `/api/v1/validity` is useful for spot checks, but it is a per-announcement query surface rather than a full-run import contract
- `/json-delta` is a later optimization for ROA churn polling, but it is not the right first-wave canonical import target for full historical runs and combined ROA-plus-ASPA coverage

Operational implications:

- the first adapter should request or normalize the `jsonext` object shape and persist ROA and ASPA payload families from that document
- router keys should remain out of first-wave scope even if Routinator includes `routerKeys`; the adapter can ignore them until BGPsec support is intentionally added
- `GET /json` should remain an explicitly degraded fallback shape for fixtures or constrained environments, with the tradeoff that correlation may fall back to payload-level linkage when source provenance is absent
- `GET /api/v1/status` remains useful as additive run-health metadata, but it should not be treated as the primary validation-import contract

## Proposed Overlay Architecture

Priority 11 should land as two additive evidence pipelines that join in a shared correlation layer.

### Pipeline A: Validator Import

Purpose:

- ingest external validator runs and per-object validation outcomes
- persist validated ROA and ASPA payload observations
- correlate those runs back to authored and imported object families

Primary persistence:

- existing validation models with additive summary and matching fields where needed

### Pipeline B: BGP Telemetry Import

Purpose:

- ingest external route-observation evidence with peer and path detail
- retain enough detail for both ROA visibility review and ASPA path review
- expose current posture plus historical change over time

Primary persistence:

- a new additive telemetry model family

### Shared Correlation Layer

Purpose:

- connect authored objects, imported provider objects, validator observations, and route telemetry into one operator-facing evidence model
- project those correlations into:
  - object detail pages
  - provider evidence drill-down
  - reconciliation runs
  - change-plan review
  - operations dashboard rollups

The correlation layer should be service-driven and summary-oriented. Views should not perform cross-source evidence joining ad hoc.

## Proposed Model Contract

### Model Overview

| Model | Purpose | Key fields or behaviors | Notes |
| --- | --- | --- | --- |
| `ValidatorInstance` | External validator source identity | existing fields plus additive source-summary metadata | Keep current model as validator identity anchor. |
| `ValidationRun` | One imported external validator run | existing status and timing plus additive summary and freshness fields | Remains the historical run boundary. |
| `ObjectValidationResult` | Per-object validator outcome | existing signed-object linkage plus additive imported-object correlation and detail payloads | Main per-object observation row. |
| `ValidatedRoaPayload` | Observed validated ROA payload | existing model remains primary ROA payload contract | Extend summaries if filtering or rollups require it. |
| `ValidatedAspaPayload` | Observed validated ASPA payload | existing model remains primary ASPA payload contract | Extend summaries if filtering or rollups require it. |
| `TelemetrySource` | External route-observation source identity | source type, endpoint or label, enabled state, collection metadata | New additive source anchor. |
| `TelemetryRun` | One route-telemetry collection run | status, observed window, source metadata, summary, freshness | Historical run boundary for telemetry. |
| `BgpPathObservation` | One observed route-plus-path fact | prefix, origin ASN, peer or vantage fields, collector fields, path text, path hash, timestamps, detail payload | First-wave canonical telemetry row. |

### Existing Models To Extend

Keep the current validator model family as the primary persistence layer.

Recommended additive evolution for `ValidatorInstance`:

- optional validator kind or adapter label if `software_name` alone proves too free-form
- optional import capability metadata or summary payload
- optional scheduling metadata if jobs need source-specific polling defaults

Recommended additive evolution for `ValidationRun`:

- run-level `summary_json`
- source run identifier or external serial where available
- observation window timestamps when the source can provide them
- matched versus unmatched object and payload counts
- freshness metadata and ingest-fingerprint data

Recommended additive evolution for `ObjectValidationResult`:

- normalized `details_json`
- optional link to `ImportedSignedObject` when external evidence matches provider-imported inventory more precisely than authored `SignedObject`
- stable object identity fields such as object URI, content hash, or validator object key where needed for matching and forensic review
- explicit match-status fields if JSON-only filtering becomes awkward

Recommended additive evolution for `ValidatedRoaPayload` and `ValidatedAspaPayload`:

- preserve current authored-object linkage
- add summary or provenance fields only when they directly improve filtering, correlation, or historical comparison
- avoid duplicating full validator details already stored on the parent run or object-validation row

### New Telemetry Models

The first wave needs a distinct telemetry family because no BGP telemetry substrate exists today.

Recommended new models:

1. `TelemetrySource`
   - represents one external route-observation source
   - examples include collector APIs, imported MRT or BMP feeds, or manually imported observation sets
   - should capture source type, display label, endpoint metadata, enabled state, and optional organization scope

2. `TelemetryRun`
   - represents one collected telemetry snapshot or bounded collection window
   - should capture status, started and completed timestamps, observed window start and end, ingest metadata, and stable summary payloads

3. `BgpPathObservation`
   - represents one observed route-plus-path fact for the first wave
   - should capture:
     - `telemetry_run`
     - prefix
     - origin ASN
     - optional peer ASN
     - optional collector identifier
     - optional vantage-point label
     - raw AS path text
     - normalized path ASN sequence or equivalent summary payload
     - path fingerprint or hash
     - first and last observed timestamps where the source can provide them
     - visibility or acceptance status if the source semantics expose it
     - `details_json` for source-specific payload fragments

The first wave does not need per-hop child models if normalized path text, hash, and parsed ASN sequence are sufficient for correlation and review.

### Correlation Rules

The overlay layer should follow an explicit matching priority instead of relying on UI-only heuristics.

Recommended matching order for validator objects:

1. exact authored `SignedObject` match by explicit external identity, URI, or content hash
2. exact imported `ImportedSignedObject` match within the relevant evidence window
3. payload-level correlation through `ValidatedRoaPayload` or `ValidatedAspaPayload`
4. unmatched external observation retained as evidence, but clearly marked unmatched

Recommended matching order for telemetry observations:

1. correlate to validated ROA payloads by prefix, origin ASN, and timing window
2. correlate to validated ASPA payloads or ASPA objects by path-derived customer-provider evidence where the path data supports it
3. correlate to authored ROA or ASPA intent or publication objects when validated payload linkage is absent but the object match is still clear
4. preserve unmatched route observations for forensic review, but mark them as not yet linked to plugin-managed objects

### Models To Avoid In The First Wave

Do not add these in the first implementation wave unless a concrete gap proves them necessary:

- a second validator-run parent model parallel to `ValidationRun`
- a generic event-bus or streaming-ingest subsystem
- per-hop AS-path child tables for every observation
- a full route-state history warehouse optimized for arbitrary analytics queries
- approval-gating models tied to external overlays

Use additive summary fields and service-layer correlation first.

## Proposed Service Contracts

### Service Overview

| Contract | Likely module | Inputs | Outputs | Purpose |
| --- | --- | --- | --- | --- |
| validator adapter registry | `services/external_validation.py` | validator instance, credentials or endpoint config | normalized external run payload | Makes multiple validator adapters possible without changing workflows. |
| validator import orchestration | `services/external_validation.py` | validator instance or run request | `ValidationRun` plus object and payload rows | Persists external validation observations into existing models. |
| telemetry adapter registry | `services/bgp_telemetry.py` | telemetry source, source config | normalized telemetry batch | Normalizes different collector or feed shapes. |
| telemetry import orchestration | `services/bgp_telemetry.py` | telemetry source or run request | `TelemetryRun` plus `BgpPathObservation` rows | Persists historical route-observation evidence. |
| overlay correlation builder | `services/overlay_correlation.py` | authored objects, imported evidence, validation runs, telemetry runs | normalized overlay summaries | Produces stable cross-source evidence summaries for views and APIs. |
| dashboard rollup builder | `services/overlay_reporting.py` | visible validator and telemetry data | operations rollups | Feeds dashboard cards and attention lists. |
| change-review overlay builder | `services/overlay_reporting.py` | ROA or ASPA change plan | summarized external posture | Surfaces evidence during preview or approval review without gating. |

### Validator Import Contract

Validator import should produce one authoritative imported run and then project that run into existing validation rows.

The import service should handle:

- source authentication and fetch
- run identity and idempotency
- per-object normalization
- payload extraction for ROA and ASPA
- conservative linkage to authored `SignedObject`, `Roa`, and `ASPA`
- optional linkage to `ImportedSignedObject` where authored linkage is not sufficient
- stable run-level summaries and mismatch counts

The service should prefer conservative matching over aggressive auto-linking. Ambiguous evidence should remain visible and explicitly ambiguous.

### Telemetry Import Contract

Telemetry import should remain source-agnostic at the service boundary.

The first-wave telemetry contract should normalize incoming evidence into path-aware observations with enough fidelity for:

- route-visibility review for ROA
- path review relevant to ASPA
- freshness and history analysis
- cross-source correlation by prefix, origin ASN, and AS path

The service should support both pull-style sources and imported batches, but the first implementation slices can start with one adapter if the model contract stays generic.

### Overlay Correlation Contract

The correlation service must be able to answer these questions for a given object or workflow:

1. what is the latest visible validator posture
2. what was the prior visible validator posture
3. what route telemetry corroborates or conflicts with that posture
4. does the provider-imported evidence align with authored and externally observed state
5. is the evidence current, stale, ambiguous, or unmatched

The service should emit stable summary structures rather than view-specific ad hoc strings.

## Proposed Surface Contract

### Object Detail Surfaces

The following objects should gain additive external-overlay summaries or related tables:

- `SignedObject`
- `Roa`
- `ASPA`
- `ImportedSignedObject`
- `ImportedCertificateObservation` where it improves publication-to-validation drill-down
- `ValidationRun`
- `TelemetryRun`

Recommended detail-surface behavior:

- show latest validator posture and freshness summary
- show latest telemetry posture and freshness summary
- show matched versus unmatched external evidence counts
- provide drill-down tables for related validation results, payload observations, and telemetry observations where row counts remain reasonable

### Reconciliation and Change-Review Surfaces

Priority 11 should enrich, not replace, existing operator review flows.

Recommended additions:

- ROA reconciliation summary should expose whether external validation and route telemetry corroborate or conflict with reconciliation findings
- ASPA reconciliation summary should expose equivalent external posture, especially where path evidence suggests provider relationships that differ from intended ASPA state
- ROA and ASPA change-plan review should show external evidence summaries and freshness indicators
- first-wave review surfaces should remain informational only

### Operations Dashboard

The operations dashboard should gain an external-evidence section rather than hiding Priority 11 only in low-level detail pages.

Recommended new dashboard rollups:

- validator instances requiring attention
- stale or failed validator runs
- stale or failed telemetry sources or runs
- authored objects with external-invalid posture
- authored or imported objects with external-observation mismatches
- route observations lacking corresponding authored or imported support where that gap appears operationally interesting

### API and GraphQL

The first wave should preserve the plugin's current surface style:

- new telemetry models should get ordinary registry-driven read surfaces
- validator and telemetry summary fields should expose stable JSON summaries first, with typed expansion only when the contract proves stable
- change-review and dashboard summary helpers should be available through explicit API or GraphQL query fields where aggregate reporting makes sense

## Proposed Summary Contracts

### Validation Run Summary

`ValidationRun.summary_json` should evolve into a stable operator summary with fields such as:

- run freshness
- external source identifiers
- object result counts by validation state and disposition
- matched authored object counts
- matched imported object counts
- unmatched object counts
- validated ROA payload counts
- validated ASPA payload counts
- ambiguous match counts

### Telemetry Run Summary

`TelemetryRun.summary_json` should include fields such as:

- source freshness and observed window
- observation counts by collector and peer
- unique prefix counts
- unique origin-ASN counts
- unique path counts
- matched ROA-support counts
- matched ASPA-support counts
- unmatched observation counts
- stale or partial-import indicators

### Overlay Correlation Summary

Object-level or workflow-level overlay summaries should answer:

- latest validator posture
- latest telemetry posture
- provider-evidence linkage status
- evidence freshness
- evidence confidence or ambiguity state
- notable mismatch categories
- direct drill-down references to the latest relevant runs

## Execution Slices

### Slice 0: Contract Freeze

Use this document as the initial contract freeze for the first implementation wave.

Closed by this document:

- validator plus telemetry scope
- ROA plus ASPA scope
- historical retention requirement
- peer and path telemetry fidelity requirement
- informational-only first-wave approval posture
- Routinator as the first validator adapter
- Routinator live API plus exported snapshot support, with live API preferred
- Routinator `jsonext` as the canonical first-wave live and snapshot normalization target

Still intentionally open for implementation kickoff:

- exact first telemetry source adapter to implement first
- whether path parsing in slice 1 stores normalized ASN sequences as JSON only or also stores an indexed hash or derived searchable fields

### Slice 1: Validator Import Maturity

Land a Routinator-backed validator-ingest service using the existing validation models as the primary persistence layer.

Expected outcomes:

- import job or command for a concrete Routinator adapter
- live Routinator API ingestion as the preferred operator path
- exported Routinator snapshot ingestion through the same normalized adapter contract
- `GET /jsonext` and `vrps --format jsonext` treated as equivalent external source shapes feeding one normalization path
- explicit Routinator normalization rules for object-level and payload-level observations
- run summaries and matching summaries on `ValidationRun`
- richer `ObjectValidationResult` detail payloads
- additive detail, API, and GraphQL exposure for the new summary fields
- focused tests for conservative authored and imported-object matching using Routinator-shaped fixtures

### Slice 2: Telemetry Substrate

Land the new telemetry model family and one concrete telemetry adapter.

Expected outcomes:

- `TelemetrySource`
- `TelemetryRun`
- `BgpPathObservation`
- import service and normalization rules
- registry-driven surfaces for the new telemetry objects
- focused tests for peer, collector, and AS-path persistence

### Slice 3: Cross-Source Correlation

Build the correlation service that joins:

- authored ROA and ASPA objects
- imported provider evidence
- validator observations
- telemetry observations

Expected outcomes:

- stable overlay summary builders
- explicit ambiguity and unmatched-evidence semantics
- object detail enrichment for `SignedObject`, `Roa`, `ASPA`, and imported evidence objects

### Slice 4: Dashboard and Workflow Integration

Project the overlay layer into the operator workflows that already matter.

Expected outcomes:

- new operations-dashboard sections or cards for external evidence
- additive reconciliation summaries for ROA and ASPA runs
- additive change-review summaries for ROA and ASPA plans
- focused view and API tests proving operator reachability and permissions

### Slice 5: Historical Comparison and Reporting Polish

Use the retained runs to improve operator explanations.

Expected outcomes:

- prior-versus-latest comparison helpers
- timeline-oriented freshness and drift explanation
- optional export or summary query surfaces once the core operator contract is stable

## Testing And Verification Expectations

The first implementation wave should extend the plugin's existing test style instead of inventing a new one.

Required coverage areas:

- model validation for new telemetry objects and additive validator-link fields
- service tests for validator import, telemetry import, and correlation logic
- detail-page rendering tests for object overlay summaries and drill-down tables
- API tests for new models, summary fields, and aggregate-reporting helpers
- GraphQL tests for new models and new summary fields or aggregate queries
- dashboard tests covering rendered attention text rather than only transport details

Focused verification should remain aligned with the existing plugin test strategy matrix and registry-driven surface-contract checks.

## Risks And Implementation Notes

Main risks:

- overly aggressive object matching could create false correlation confidence
- peer and path telemetry can grow quickly in volume if the first adapter does not bound collection windows carefully
- external evidence freshness can drift independently of provider sync freshness, so dashboard language must distinguish those failure modes clearly
- ROA and ASPA external posture can disagree for valid reasons; the UI must explain that the sources and semantics differ rather than flattening everything into one risk label

Implementation notes:

- prefer conservative matching and explicit ambiguity over silent auto-linking
- keep operator summaries stable and normalized so they can be reused across UI, REST, and GraphQL
- avoid source-specific field sprawl on core models when adapter-specific data can remain in `details_json`
- treat imported provider evidence as an equal correlation participant, not as an afterthought behind authored objects only

## Open Questions For Implementation Kickoff

These do not block the plan document, but they should be confirmed before coding begins on the first adapter slice.

1. Which telemetry source should land first: a collector API, imported MRT data, BMP-derived feeds, or another source already available to the team?
2. Should the first telemetry adapter prioritize bounded snapshot imports, rolling windows, or scheduled incremental refreshes?

The model and service contracts above are written so those source choices can remain implementation-slice decisions without forcing a redesign.
