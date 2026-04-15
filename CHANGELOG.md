# Changelog

## 0.8.0 (2026-04-15)

* Core inventory: expand the plugin from basic organization, certificate, and ROA tracking into a broader RPKI inventory surface that also covers publication points, repositories, trust-anchor hierarchy, generic signed objects, CRLs, manifests, ASPAs, RSCs, router certificates, and related object-linkage views.
* External validator import: add retained validator instances, validation runs, object validation results, and validated ROA and ASPA payload models, including Routinator `jsonext` import support from either the live API or exported snapshot files.
* Routing intent: introduce organization-scoped routing intent authoring with profiles, rules, context groups, policy bundles, overrides, reusable templates, template bindings, typed exceptions, and bulk intent runs.
* ROA and ASPA reconciliation: add read-only derivation, match, reconciliation, intent-result, and published-result pipelines so operators can compare authored intent against locally recorded or provider-imported publication state.
* External management exceptions: add explicit, time-bounded exception records so ROA and ASPA reconciliation can account for prefixes or objects that are intentionally managed outside the plugin.
* ROA lint: add lint runs, findings, acknowledgements, suppressions, and per-rule configuration to support reviewable quality analysis of locally recorded ROA inventory.
* Change planning and write-back: add reviewed, approval-aware, rollback-capable ROA and ASPA change-plan workflows, including provider write execution audit records and validation-simulation support ahead of apply.
* Hosted provider synchronization: add provider accounts, sync runs, snapshots, snapshot diffs, and imported publication families for Krill and ARIN, with stable evidence summaries for publication points, signed objects, and certificate observations exposed through REST, GraphQL, dashboard, and detail reporting surfaces.
* IRR coordination: add IRR source and snapshot retention, coordination runs and result objects, IRR change plans, and write-execution tracking for correlating plugin-managed RPKI intent with externally managed IRR state.
* Delegated authorization and publication workflows: add delegated entities, managed authorization relationships, authored CA topology records, delegated publication workflows, readiness summaries, and approval tracking for delegated RPKI operations.
* BGP telemetry and lifecycle reporting: add MRT-derived telemetry import, BGP path observation history, lifecycle-health policy and event scaffolding, and organization or provider roll-up views that tie operational health back to publication state.
* Platform surfaces: broaden the plugin’s standard NetBox integration with consistent web UI, REST API, GraphQL, navigation, shared detail rendering, and registry-driven surface generation across the expanded model set, while validating compatibility against NetBox 4.5.0 and 4.5.7.

## 0.1.6.2 (2026-04-11)

* Documentation: expand the README feature and model coverage summary to describe the implemented standards-aligned object families and Priority 1 intent/reconciliation model layer.
* Release metadata: align the plugin manifest with the `0.1.6.2` patch release.

## 0.1.6.1 (2026-04-11)

* Dev/test fixtures: seed the devrun NetBox database and fixture-backed test helpers with at least a dozen rows across core NetBox dependency tables and plugin tables.
* Tests: add regression coverage asserting the shared sample dataset populates every targeted table at the expected minimum volume.
* Release metadata: align package-facing release notes and plugin manifest with the `0.1.6.1` patch release.

## 0.1.6 (2026-04-11)

* Refactor: move plugin UI, API, GraphQL, navigation, and standard test surfaces to a metadata-driven object registry.
* UI: replace repeated Organization, Certificate, and ROA detail templates with a shared metadata-driven detail renderer.
* Tests: parameterize repeated CRUD, form, filterset, table, URL, navigation, and GraphQL coverage around the shared registry contract.
* Compatibility: validate plugin load and test-suite execution against NetBox 4.5.0 and 4.5.7.

## 0.1.0 (2024-10-11)

* First release on PyPI.
