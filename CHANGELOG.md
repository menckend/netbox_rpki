# Changelog

## Unreleased

* Provider sync: enrich Krill hosted-publication imports with stable evidence summaries for publication points, signed objects, and certificate observations, and expose those summaries through the standard REST, GraphQL, and detail-view reporting surfaces.
* Provider sync: preserve family capability metadata in shared rollups, expose provider-account rollups through dashboard and reporting surfaces, and clarify that ARIN currently supports hosted ROA synchronization only, while repeated ARIN syncs now have explicit regression coverage for stable external identity and zero-churn diffs.

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
