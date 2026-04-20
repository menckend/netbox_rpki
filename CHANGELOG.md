# Changelog

## Unreleased

### Added

* Snapshot retention policies (closes #70): new `SnapshotRetentionPolicy` model configures automated purge behaviour for `ValidatorRun` snapshots — max age (days), minimum runs to retain, and dry-run mode. `SnapshotPurgeRun` records each purge execution with a count of deleted snapshots and elapsed time. The `PurgeSnapshotRunJob` background job (queued via `POST /api/plugins/netbox-rpki/snapshot-retention-policies/{id}/run-purge/`) enqueues the purge service and defaults to dry-run. The `GET …/storage-impact/` action returns the current snapshot count, estimated age distribution, and projected deletion counts for a policy. Both models are registered in the RPKI subsystem maturity map under the Governance group.
* Golden signed-object fixture corpus and parser tests (closes #62): new `signed_object_corpus.py` module provides 16 pre-built DER/CMS/CRL/cert constants covering VALID, STALE, EDGE_CASE, and MALFORMED categories. `test_signed_object_corpus.py` adds 62 `SimpleTestCase` assertions that drive `_load_der_certificate`, `_parse_cms_crl_metadata`, `_parse_cms_manifest_metadata`, `_load_cms_signed_data`, `_load_cms_certificates`, `_infer_signed_object_type`, and `parse_krill_signed_object_records` against the corpus. During test implementation a bug was found and fixed in `_normalized_text` — it now correctly converts pyasn1 simple types (IA5String, GeneralizedTime, OID) to strings, enabling manifest filename and timestamp extraction from DER payloads.
* Provider-scale load-test scenarios (closes #65): new `load_scenarios.py` defines SMALL (100 ROA payloads), MEDIUM (500), and PROVIDER (5 000) scale tiers with per-tier import, purge, and query time budgets. `test_load_scenarios.py` adds 21 `TestCase` tests across three scenario families — single-snapshot import throughput (`persist_validation_run`), snapshot-purge scale (`run_snapshot_purge` dry-run over bulk-created `ValidationRun` records), and aggregate dashboard query throughput — at all three estate sizes. SMALL always runs when the `load` test lane is invoked; MEDIUM and PROVIDER are opt-in via `NETBOX_RPKI_ENABLE_LOAD_TESTS=medium|provider|all`. The `load` lane is exposed as `./devrun/test.sh load` and `make test-load`, satisfying the CI-or-scheduled-benchmark requirement. The `_normalized_text` fix committed for #62 was also needed for correct manifest parsing at provider scale.

## 0.2.4 (2026-04-19)

This release adds UX improvements, first-class tenant scoping, and a new cross-validator comparison API.

### Added

* Subsystem maturity badges (closes #7): every navigation group is now tagged with a maturity level (GA, Beta, or Experimental). Beta and Experimental badges appear inline in navigation menu labels. The new `hide_experimental` plugin setting removes Experimental groups from navigation when set to `True`.
* Navigation: Linting, Delegated, and Governance subsystems unhidden from `MENU_GROUP_ORDER` and now appear in the plugin navigation menu.
* Documentation: new Subsystem Maturity page in the Sphinx site with level definitions, the current subsystem map, and configuration guidance. README updated with a maturity table and `hide_experimental` example.
* Progressive disclosure fieldsets (closes #15): forms with 14+ fields are now organized into named, collapsible fieldsets (General, Routing, Validation, Administrative, etc.). Applies to Certificate, IRR Source, and 13 additional dynamically-built forms. A structural test verifies fieldset field lists stay in sync with form field declarations.
* Tenant scoping (closes #69): all model forms now include a `tenant_group` selector that dynamically scopes the `tenant` dropdown, matching the standard NetBox tenancy UI pattern. All filter forms expose `tenant_group_id` alongside `tenant_id`.
* Cross-validator ROA payload comparison (closes #49): new `GET /api/plugins/netbox-rpki/validator-instances/{id}/compare/?other={id2}` endpoint compares the most recent completed runs of two validator instances by `(observed_prefix, origin_ASN)` key and returns agreement count, disagreement count, per-entry disagreement records, and freshness status for each run. The `limit_disagreements` query parameter (default 100, max 1000) caps the returned detail rows.

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
