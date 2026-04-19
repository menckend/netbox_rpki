# Changelog

## Unreleased

### Added

* Subsystem maturity: every navigation group is now tagged with a maturity level (GA, Beta, or Experimental). Beta and Experimental badges appear in navigation menu labels.
* Navigation: Linting, Delegated, and Governance subsystems are now visible in the plugin navigation menu (previously suppressed from the menu group order).
* Plugin setting `hide_experimental`: when set to `True`, Experimental subsystems are removed from the navigation menu. REST API, GraphQL, and URL endpoints remain functional.
* Documentation: new Subsystem Maturity page in the Sphinx site with level definitions, the current subsystem map, and configuration guidance.
* README: subsystem maturity table and `hide_experimental` configuration example.
* Progressive disclosure: forms with 14+ fields are now organized into named fieldsets that group related fields under collapsible headings. Applies to Certificate, IRR Source, and all dynamically-built forms with many fields (Closes #15).
* Test coverage: structural test verifying fieldset field lists stay in sync with form field lists.
* Tenant scoping: all model forms now include a `tenant_group` selector that dynamically scopes the `tenant` dropdown, matching the standard NetBox tenancy pattern. All filter forms now expose `tenant_group_id` alongside `tenant_id` (Closes #69).
* Cross-validator comparison: new `GET /api/plugins/netbox-rpki/validator-instances/{id}/compare/?other={id2}` endpoint compares the most recent completed run of two validator instances, returning per-prefix/origin-ASN agreement and disagreement counts with detailed disagreement records (Closes #49).

## 0.2.3 (2026-04-19)

This patch release refreshes the plugin icon artwork and adjusts README rendering for certification readiness.

* Certification: update plugin icon SVG and PNG with revised artwork.
* Documentation: render the plugin icon at 512 px width in README for improved visibility.
* Release metadata: bump plugin manifest to `0.2.3`.

## 0.2.2 (2026-04-19)

This patch release updates the plugin icon and continues alignment with NetBox Plugin Certification requirements.

* Certification: replace the original plugin icon with the updated `nb_rpki-icon-new` artwork in both SVG and PNG formats.
* Documentation: update README to reference the new icon asset at 128 px width.
* Release metadata: bump plugin manifest to `0.2.2`.

## 0.2.1 (2026-04-19)

This patch release adopts NetBox Plugin Certification requirements across repository metadata, documentation, and packaging.

* Certification: align README with Plugin Certification Program criteria including icon rendering, compatibility matrix, dependency summary, screenshots, maintainer contact, and user support guidance.
* Certification: retire standalone `PLUGIN_CERTIFICATION.md` checklist now that all repository-side criteria are met and tracked in the release gate workflow.
* Documentation: render the plugin icon at a fixed 256 px width in README for consistent presentation across renderers.
* Release metadata: bump plugin manifest to `0.2.1`.

## 0.2.0 (2026-04-15)

This major release introduces substantial new feature coverage across RPKI inventory, validation, routing intent, reconciliation, provider synchronization, delegated workflows, and operational reporting, alongside broad NetBox integration enhancements.

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

This patch release focuses on documentation and release metadata updates so the published package description stays aligned with the implemented feature set.

* Documentation: expand the README feature and model coverage summary to describe the implemented standards-aligned object families and Priority 1 intent/reconciliation model layer.
* Release metadata: align the plugin manifest with the `0.1.6.2` patch release.

## 0.1.6.1 (2026-04-11)

This patch release improves development and test reliability by expanding seeded fixture coverage and adding regression checks around the shared sample dataset.

* Dev/test fixtures: seed the devrun NetBox database and fixture-backed test helpers with at least a dozen rows across core NetBox dependency tables and plugin tables.
* Tests: add regression coverage asserting the shared sample dataset populates every targeted table at the expected minimum volume.
* Release metadata: align package-facing release notes and plugin manifest with the `0.1.6.1` patch release.

## 0.1.6 (2026-04-11)

This minor release refactors the plugin’s standard NetBox surfaces around a shared registry model and expands automated compatibility validation across the supported NetBox anchors.

* Refactor: move plugin UI, API, GraphQL, navigation, and standard test surfaces to a metadata-driven object registry.
* UI: replace repeated Organization, Certificate, and ROA detail templates with a shared metadata-driven detail renderer.
* Tests: parameterize repeated CRUD, form, filterset, table, URL, navigation, and GraphQL coverage around the shared registry contract.
* Compatibility: validate plugin load and test-suite execution against NetBox 4.5.0 and 4.5.7.

## 0.1.0 (2024-10-11)

This initial release established the first PyPI-published version of the plugin with the foundational NetBox RPKI data model and packaging baseline.

* First release on PyPI.
