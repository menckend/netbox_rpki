Subsystem Maturity
==================

The ``netbox_rpki`` plugin spans multiple functional subsystems at different
stages of maturity.  Each subsystem is tagged with one of three levels so
operators can evaluate stability expectations before relying on a feature in
production.

Maturity Levels
---------------

.. list-table::
   :header-rows: 1
   :widths: 15 15 70

   * - Level
     - Badge
     - Meaning
   * - **GA**
     - *(none)*
     - Generally available.  The subsystem is stable, covered by the contract
       test suite, and its data model and public API surface are not expected
       to break within the current release line.
   * - **Beta**
     - β
     - Feature-complete and tested but still settling.  The subsystem may
       evolve across minor releases.  Breaking changes are documented in the
       changelog.
   * - **Experimental**
     - ⚠
     - Early-stage or recently introduced.  The subsystem may change
       significantly, be restructured, or be removed.  Use cautiously in
       production.

Current Subsystem Map
---------------------

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Subsystem
     - Maturity
     - Scope
   * - Resources
     - GA
     - Organizations, certificates, ROA objects, provider accounts, and
       supporting RPKI inventory.
   * - ROAs
     - GA
     - ROA object management and prefix bindings.
   * - Objects
     - GA
     - Generic RPKI signed objects, manifests, CRLs, ASPAs, RSCs, and router
       certificates.
   * - Trust
     - GA
     - Trust anchors, publication points, and certificate hierarchy.
   * - Validation
     - GA
     - Validator instances, validation runs, validated ROA and ASPA payloads,
       and object validation results.
   * - Intent
     - Beta
     - Routing-intent profiles, rules, context groups, policy bundles,
       overrides, templates, template bindings, exceptions, and bulk intent
       runs.
   * - Derivation
     - Beta
     - Intent-derivation runs, derived ROA and ASPA intents, and match
       analysis.
   * - Reconciliation
     - Beta
     - ROA and ASPA reconciliation runs, intent results, published results,
       change plans, change-plan items, and validation simulation.
   * - Provider
     - Beta
     - Provider sync runs, snapshots, snapshot diffs, write executions, and
       provider-account operational reporting.
   * - Imported
     - Beta
     - Imported ROA authorizations, ASPA authorizations, resource entitlements,
       and provider evidence objects.
   * - IRR
     - Experimental
     - IRR source and snapshot retention, coordination runs, coordination
       results, IRR change plans, and write-execution tracking.
   * - Linting
     - Experimental
     - ROA lint rule configuration.
   * - Delegated
     - Experimental
     - Delegated authorization entities, managed authorization relationships,
       and delegated publication workflows.
   * - Governance
     - Experimental
     - ROA and ASPA change-plan rollback bundles.


Hiding Experimental Subsystems
------------------------------

Operators who want to suppress experimental navigation entries can set
``hide_experimental`` in the plugin configuration::

   PLUGINS_CONFIG = {
       "netbox_rpki": {
           "hide_experimental": True,
       },
   }

When enabled, subsystems at the *Experimental* level are removed from the
plugin navigation menu.  Their REST API, GraphQL, and URL endpoints remain
functional — only the menu entry is suppressed.

Tracking Maturity Changes
-------------------------

Maturity promotions and demotions are recorded in the project changelog
(``CHANGELOG.md``).  The single source of truth for current maturity
assignments is ``netbox_rpki/maturity.py``.
