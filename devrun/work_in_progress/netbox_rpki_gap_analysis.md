# netbox_rpki Gap Analysis Against Feature Strategy Matrix

Source matrix: `devrun/work_in_progress/netbox_rpki_feature_strategy_matrix.md`

> **Last updated**: 2026-04-15
> All previously tracked matrix gaps are closed.

## Current Status

This older gap-analysis document is retained as a historical companion to
`netbox_rpki_gap_analysis_against_feature_strategy_matrix.md`, but its earlier
open-gap narrative is now stale.

As of the current implementation state:

- delegated/downstream authorization is operational
- IRR coordination includes route-set and AS-set authored-policy handling
- earlier model-convention drift is no longer an active gap
- provider-gated live-backend testing now has explicit opt-in mechanics

## Domain Summary

| Matrix Section | Status | Notes |
| --- | --- | --- |
| A. Standards-Aligned Data Model | Implemented | Earlier convention-drift concerns are no longer active gaps. |
| B. Registry-Driven Plugin Surfaces | Implemented | Registry-driven UI, REST, GraphQL, forms, filters, and tables are in place and contract-tested. |
| C. Intent-to-ROA Reconciliation | Implemented | Intent derivation through reconciliation and change-plan generation is covered across service and operator surfaces. |
| D. ASPA Operations | Implemented | ASPA inventory, intent, reconciliation, provider-backed plan/apply flow, and operator surfaces are present. |
| E. ROA Linting and Safety Analysis | Implemented | Linting, suppressions, acknowledgements, approval gating, and operator surfaces are present. |
| F. ROV Impact Simulation | Implemented | Persisted simulation runs/results and approval integration are present. |
| G. Bulk Generation and Templating | Implemented | Templates, exceptions, bulk runs, governance, and operator surfaces are present. |
| H. Provider Synchronization | Implemented | Capability matrix, sync/diff/reporting, and explicit fixture-vs-live test-lane separation are present. |
| I. Change Control and Governance | Implemented | Change-plan lifecycle, approvals, rollback bundles, audit rows, and rollups are present. |
| J. Lifecycle, Expiry, and Publication Health | Implemented | Policies, hooks, events, exports, and dashboard/reporting surfaces are present. |
| K. IRR Coordination | Implemented | Route-object, route-set, and AS-set coordination and drafting are present with capability-gated breadth. |
| L. External Validator and Telemetry Overlays | Implemented | Validator sync, telemetry sync, overlay correlation, and reporting are present. |
| M. Service Context and Topology Binding | Implemented | Context groups, criteria, inheritance semantics, and policy binding are present. |
| N. Downstream and Delegated Authorization | Implemented | Delegated entities, managed relationships, publication workflows, summaries, and delegated policy scope are present. |

## Closed Gaps

The previously open items that motivated this document are now closed:

- authored CA relationship topology
- ROA change-plan CLI/job parity
- bulk intent governance operator surfaces
- provider capability matrix normalization
- context-group inheritance and reusable policy layering
- delegated/downstream authorization modeling and operational use
- IRR set-family authored-policy coordination
- provider-gated live-backend test-lane enforcement

## Bottom Line

There are no remaining matrix-gap items to implement from this analysis. Any
further work should be treated as feature expansion or refinement, not gap
closure against the current strategy matrix.
