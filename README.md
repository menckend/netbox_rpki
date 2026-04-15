# NetBox RPKI Plugin

Netbox plugin for adding BGP RPKI elements.

* Free software: Apache-2.0
* [Documentation](https://menckend.github.io/netbox_rpki)
* [Repository](https://github.com/menckend/netbox_rpki)
* [Python Package](https://pypi.org/project/netbox_rpki/)

## Features

Implements NetBox models, API endpoints, GraphQL types, tables, and UI views across the following functional areas:

**RPKI inventory** covers organizations, resource certificates, ROAs, ROA prefixes, certificate prefixes, and certificate ASNs. Resource certificates and ROAs carry optional links into the broader RPKI object hierarchy through trust-anchor, publication-point, and signed-object references.

**Repository and publication infrastructure** models the full RPKI signed-object and publication hierarchy: repositories, publication points, trust anchors, trust anchor locators, trust anchor keys, end-entity certificates, a generic signed-object type, CRLs, revoked certificate references, manifests, manifest entries, ASPAs, ASPA providers, RSCs, RSC file hashes, and BGPsec router certificates.

**External validator import** captures and retains normalized output from external RPKI validators. Validator instances, validation runs, object validation results, and validated ROA and ASPA payload records hold imported observations. The included Routinator adapter ingests `jsonext` output from either the live API or exported snapshot files.

**Routing intent** lets operators define and manage publication intent for ROAs and ASPAs. Routing intent profiles, rules, context groups, context criteria, and policy bundles express derivation policy. ROA intent overrides handle explicit per-prefix exceptions. Reusable templates, template rules, template bindings, and typed exceptions support scalable policy authoring across organizations. Bulk intent runs with per-scope results drive organization-scoped derivation, and the operations dashboard surfaces stale bindings, expiring exceptions, and recent bulk-run health.

**ROA and ASPA reconciliation** compares derived intent against published objects. Intent derivation runs, ROA intent rows, match records, reconciliation runs, intent results, and published results form the ROA reconciliation pipeline. A parallel family covers ASPA reconciliation. All derivation and reconciliation run and result objects are read-only reporting surfaces.

**ROA lint** provides configurable quality analysis of locally recorded ROA inventory through lint runs, findings, acknowledgements, suppressions, and per-rule configurations.

**ROA and ASPA change planning and write-back** supports reviewed, approved, and rollback-capable publication of ROA and ASPA changes to hosted providers. ROA change plans, change plan items, approval records, provider write executions, and rollback bundles implement the ROA write-back workflow. A parallel ASPA change plan family covers ASPA write-back. ROA validation simulation runs and results let operators preview approval impact before committing.

**Hosted provider synchronization** imports and tracks publication state for Krill and ARIN accounts. Provider accounts, sync runs, snapshots, snapshot diffs, and diff items manage import lifecycle. Imported families include ROA authorizations, ASPAs, CA metadata, parent and child CA links, resource entitlements, publication points, signed objects, and certificate observations. Stable evidence summaries on imported objects support publication-linkage, authored-linkage, freshness, and family-level churn reporting without generating false diffs across unchanged snapshots. ARIN currently supports ROA synchronization only; the shared reporting contract preserves that capability boundary explicitly.

**IRR snapshot import** provides a read-only correlation substrate for validating plugin-managed RPKI intent against externally managed IRR/RPSL intent. IRR sources and retained snapshots hold normalized imported objects (`route`, `route6`, `route-set`, `as-set`, `aut-num`, `mntner`) from configured external IRR sources. Coordination runs and results compare RPKI-derived intent against observed IRR state. IRR change plans and write executions model planned corrections to external IRR records based on coordination findings. The included adapter targets IRRd-compatible sources; snapshot-file import is also supported.

**Delegated authorization** models operator posture for delegated RPKI entities. Delegated authorization entities, managed authorization relationships, authored CA relationships, authored AS-sets, and delegated publication workflows track delegated topology and publication state. Delegation workflows support API and web-UI approval, and detail views expose readiness, approval state, and authored-topology linkage summaries.

**BGP telemetry** captures imported MRT-derived route-visibility data through telemetry sources, telemetry runs, and BGP path observations. Each observation stores raw AS-path text, normalized ASN-sequence JSON, and a stable path hash for correlation and historical comparison against intent and reconciliation surfaces.

**Lifecycle health** provides a structured event substrate for tracking certificate and object lifecycle health through policies, hooks, and events.

### Models / DB tables

#### Core inventory models

#### Organization
   - Represents a customer or consumer of RIR RPKI services.
   - Fields include `org_id`, `name`, `ext_url`, and `parent_rir`.

#### Resource Certificate
   - Represents an RPKI resource certificate.
   - Tracks identity and lifecycle fields including `issuer`, `subject`, `serial`, `valid_from`, `valid_to`, `auto_renews`, `public_key`, `publication_url`, `ca_repository`, `self_hosted`, and `rpki_org`.
   - Links optionally to a trust anchor and a publication point.

#### Route Origination Authorization (ROA)
   - Represents an RPKI ROA authorizing origination of one or more prefixes by an ASN.
   - Tracks `origin_as`, validity dates, `auto_renews`, and the signing resource certificate.
   - Links optionally to a signed object record.

#### ROA Prefix
   - Represents the attestation relationship between a ROA and a prefix, including `max_length`.
   - Available through the plugin but not a top-level menu item.

#### Certificate Prefix
   - Represents the relationship between a resource certificate and a prefix.
   - Available through the plugin but not a top-level menu item.

#### Certificate ASN
   - Represents the relationship between a resource certificate and an ASN.
   - Available through the plugin but not a top-level menu item.

#### Repository and publication models

#### Repository
   - Represents an rsync, RRDP, or mixed repository endpoint.

#### Publication Point
   - Represents a publication location within a repository and tracks retrieval and validation state.

#### Trust and certificate hierarchy models

#### Trust Anchor
   - Represents a trust anchor and its rollover state.

#### Trust Anchor Locator
   - Stores TAL-style discovery information for a trust anchor.

#### Trust Anchor Key
   - Represents a published trust-anchor key object and its rollover relationships.

#### End-Entity Certificate
   - Represents the EE certificate used to sign individual RPKI signed objects.

#### Signed object and repository-integrity models

#### Signed Object
   - Generic record for published RPKI signed objects including ROAs, manifests, ASPAs, RSCs, and trust-anchor keys.
   - Tracks object type, publication metadata, manifest linkage, CMS metadata, validity, and validation state.

#### Certificate Revocation List
   - Represents a CRL issued by a resource certificate, linked to publication and manifest state.

#### Revoked Certificate
   - Represents an individual revoked certificate or EE certificate reference carried by a CRL.

#### Manifest
   - Represents an RPKI manifest object.

#### Manifest Entry
   - Represents an individual manifest member, with optional links to the referenced signed object, certificate, EE certificate, or CRL.

#### Additional signed-object families

#### ASPA
   - Represents an Autonomous System Provider Authorization object.

#### ASPA Provider
   - Represents a provider ASN authorized by an ASPA.

#### RSC
   - Represents an RPKI Signed Checklist object.

#### RSC File Hash
   - Represents an individual file-hash member of an RSC.

#### Router Certificate
   - Represents a BGPsec router certificate tied to an ASN, resource certificate, and publication point.

#### Validation and validated-payload models

#### Validator Instance
   - Represents an external RPKI validator and its current run state.

#### Validation Run
   - Represents one validation execution against repository content.

#### Object Validation Result
   - Stores validation outcome and disposition for an individual signed object.

#### Validated ROA Payload
   - Represents a validated prefix-origin payload imported from a validator run.

#### Validated ASPA Payload
   - Represents a validated customer-provider authorization payload imported from a validator run.

#### Routing intent authoring models

#### Routing Intent Profile
   - Defines routing-intent policy defaults, derivation trigger mode, and prefix or ASN selection behavior for an organization.

#### Routing Intent Rule
   - Represents an ordered rule used to include, exclude, or modify ROA or ASPA intent during derivation.

#### Routing Intent Context Group
   - Groups related context criteria for scoped rule evaluation.

#### Routing Intent Context Criterion
   - Represents an individual matching criterion within a context group.

#### Routing Intent Policy Bundle
   - Collects a set of profiles and their associated rules into a reusable policy bundle.

#### ROA Intent Override
   - Represents an explicit per-prefix or per-scope exception to derived ROA intent.

#### Routing Intent Template
   - Represents a reusable routing-intent template that can be bound to organizations to generate profiles and rules.

#### Routing Intent Template Rule
   - Represents an ordered rule within a routing intent template.

#### Routing Intent Template Binding
   - Represents the association between a template and a target organization, including binding state and generated profile references.

#### Routing Intent Exception
   - Represents a typed exception encountered during intent derivation, with configurable effect modes.

#### Bulk Intent Run
   - Represents an organization-scoped bulk derivation run, including trigger mode, target scope, and overall run health.

#### Bulk Intent Run Scope Result
   - Stores the per-scope result of a single organization within a bulk intent run.

#### ROA reconciliation models

#### Intent Derivation Run
   - Stores metadata for a derived-intent calculation run.
   - Read-only reporting surface.

#### ROA Intent
   - Represents a derived ROA intent row tied to a derivation run, profile, scope, and optional override.
   - Read-only reporting surface.

#### ROA Intent Match
   - Stores a candidate match between a derived intent row and a locally recorded ROA.
   - Read-only reporting surface.

#### ROA Reconciliation Run
   - Stores metadata for a reconciliation comparison between ROA intent and published ROA records.
   - Read-only reporting surface.

#### ROA Intent Result
   - Stores the intent-side reconciliation result for a derived ROA intent row.
   - Read-only reporting surface.

#### Published ROA Result
   - Stores the published-side reconciliation result for a recorded ROA.
   - Read-only reporting surface.

#### ASPA reconciliation models

#### ASPA Intent
   - Represents a derived ASPA intent row tied to a derivation run, profile, and scope.
   - Read-only reporting surface.

#### ASPA Intent Match
   - Stores a candidate match between a derived ASPA intent row and a locally recorded ASPA.
   - Read-only reporting surface.

#### ASPA Reconciliation Run
   - Stores metadata for a reconciliation comparison between ASPA intent and published ASPA records.
   - Read-only reporting surface.

#### ASPA Intent Result
   - Stores the intent-side reconciliation result for a derived ASPA intent row.
   - Read-only reporting surface.

#### Published ASPA Result
   - Stores the published-side reconciliation result for a recorded ASPA.
   - Read-only reporting surface.

#### ROA lint models

#### ROA Lint Run
   - Represents one execution of the ROA lint analysis against locally recorded ROA inventory.

#### ROA Lint Finding
   - Represents an individual quality finding produced during a lint run.

#### ROA Lint Acknowledgement
   - Records an operator acknowledgement of a lint finding.

#### ROA Lint Suppression
   - Represents a configured suppression rule that mutes specific lint finding types.

#### ROA Lint Rule Config
   - Stores per-rule configuration controlling lint severity and enablement.

#### ROA change plan and write-back models

#### ROA Change Plan
   - Represents a set of planned ROA create, update, or delete operations against a hosted provider, including approval and execution state.

#### ROA Change Plan Item
   - Represents an individual ROA operation within a change plan.

#### Approval Record
   - Records an approval decision for a change plan, including approver identity and timestamp.

#### Provider Write Execution
   - Represents one execution of a change plan against the target hosted provider, including per-item outcomes.

#### ROA Change Plan Rollback Bundle
   - Stores the rollback state for a completed ROA change plan execution.

#### ASPA change plan and write-back models

#### ASPA Change Plan
   - Represents a set of planned ASPA create, update, or delete operations against a hosted provider, including approval and execution state.

#### ASPA Change Plan Item
   - Represents an individual ASPA operation within an ASPA change plan.

#### ASPA Change Plan Rollback Bundle
   - Stores the rollback state for a completed ASPA change plan execution.

#### ROA validation simulation models

#### ROA Validation Simulation Run
   - Represents a simulation run that evaluates how a set of planned ROA changes would affect RPKI validation outcomes for observed routes.

#### ROA Validation Simulation Result
   - Stores the per-route validation outcome and approval impact produced by a simulation run.

#### Provider account and sync models

#### RPKI Provider Account
   - Represents a Krill or ARIN hosted-provider account, including connection parameters, sync state, and capability metadata.

#### Provider Sync Run
   - Represents one import execution against a provider account.

#### Provider Snapshot
   - Represents the normalized state of a provider account's published objects at the time of a sync run, with family-level rollup summaries.

#### Provider Snapshot Diff
   - Represents the diff between two consecutive provider snapshots, with family-level churn summaries.

#### Provider Snapshot Diff Item
   - Represents an individual create, update, or delete change between two snapshots.

#### Imported provider inventory models

#### External Object Reference
   - Stores a stable external identity reference linking an imported object to its provider-assigned identifier.

#### Imported ROA Authorization
   - Represents an imported ROA authorization record from a hosted provider, including evidence summaries for publication linkage, authored linkage, and source ambiguity.

#### Imported ASPA
   - Represents an imported ASPA record from a hosted provider.

#### Imported ASPA Provider
   - Represents an individual provider ASN within an imported ASPA.

#### Imported CA Metadata
   - Represents imported metadata about a CA instance within a hosted provider account.

#### Imported Parent Link
   - Represents an imported parent CA relationship observed on a provider account.

#### Imported Child Link
   - Represents an imported child CA relationship observed on a provider account.

#### Imported Resource Entitlement
   - Represents an imported IP prefix or ASN resource entitlement associated with a CA within a provider account.

#### Imported Publication Point
   - Represents an imported publication point observation from a hosted provider, with evidence summaries for publication linkage and freshness.

#### Imported Signed Object
   - Represents an imported signed object observation from a hosted provider, with evidence summaries for manifest linkage and publication state.

#### Imported Certificate Observation
   - Represents an imported certificate observation associated with a CA within a provider account.

#### IRR import models

#### IRR Source
   - Represents a configured external IRR source used to import RPSL objects for RPKI intent correlation.

#### IRR Snapshot
   - Represents a retained snapshot of imported IRR data from a source, including import status and object counts by family.

#### Imported IRR Route Object
   - Represents an imported `route` or `route6` RPSL object from an IRR snapshot.

#### Imported IRR Route Set
   - Represents an imported `route-set` RPSL object from an IRR snapshot.

#### Imported IRR Route Set Member
   - Represents an individual member of an imported route set.

#### Imported IRR AS Set
   - Represents an imported `as-set` RPSL object from an IRR snapshot.

#### Imported IRR AS Set Member
   - Represents an individual ASN or nested set reference within an imported AS set.

#### Imported IRR Aut-Num
   - Represents an imported `aut-num` RPSL object from an IRR snapshot.

#### Imported IRR Maintainer
   - Represents an imported `mntner` RPSL object from an IRR snapshot.

#### IRR Coordination Run
   - Represents one execution of RPKI-vs-IRR coordination analysis, comparing plugin-managed RPKI intent against imported IRR data.

#### IRR Coordination Result
   - Stores the per-object comparison result from a coordination run.

#### IRR Change Plan
   - Represents a set of planned corrections to external IRR records based on coordination findings.

#### IRR Change Plan Item
   - Represents an individual IRR object operation within a change plan.

#### IRR Write Execution
   - Represents one execution of an IRR change plan against the target IRR source.

#### Delegated authorization models

#### Delegated Authorization Entity
   - Represents an operator or organization that holds delegated RPKI authority, including posture and readiness state.

#### Managed Authorization Relationship
   - Represents a managed authorization relationship between a delegating authority and a delegated entity, including role and approval state.

#### Delegated Publication Workflow
   - Represents a publication workflow initiated by a delegated entity, including approval state and authored object references.

#### Authored CA Relationship
   - Represents a modeled CA relationship between two entities in the plugin's delegated topology, including relationship type and status.

#### Authored AS Set
   - Represents an AS-set authored by a delegated entity, used for routing-intent and delegation scope purposes.

#### Authored AS Set Member
   - Represents an individual ASN or nested set reference within an authored AS set.

#### BGP telemetry models

#### Telemetry Source
   - Represents a configured source of MRT-derived BGP telemetry data.

#### Telemetry Run
   - Represents one import execution against a telemetry source.

#### BGP Path Observation
   - Represents an observed BGP path from an imported telemetry snapshot.
   - Stores raw AS-path text, normalized ASN-sequence JSON, and a stable path hash for correlation and historical comparison.

#### Lifecycle health models

#### Lifecycle Health Policy
   - Defines a set of lifecycle health rules applied to a monitored RPKI object family.

#### Lifecycle Health Hook
   - Represents a configured hook within a lifecycle health policy that triggers on specific lifecycle events or conditions.

#### Lifecycle Health Event
   - Represents a recorded lifecycle health event produced by a hook evaluation.


## Screencaps

### RPKI Organizations/Certificates/Resources

![image](/images/rpki-org-detail.png)

![image](/images/rpki-cert-detail.png)

![image](/images/rpki-certasn-detail.png)

![image](/images/rpki-certprefix-detail.png)

### RPKI ROAs

![image](/images/rpki-roa-detail.png)

![image](/images/rpki-roaprefix-detail.png)




## Compatibility

[netbox-plugin.yaml](netbox-plugin.yaml)

The plugin declares NetBox compatibility for the 4.5.x release line. Verification has been completed against real development installs of NetBox 4.5.0 and NetBox 4.5.7, covering plugin bootstrap, `manage.py check`, provider-sync, models, API, GraphQL, view, and navigation suites, browser smoke testing, and the full routing-intent and bulk-authoring workflow.


## Installing

For adding to a NetBox Docker setup see
[the general instructions for using netbox-docker with plugins](https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins).

Install using pip:

```bash
pip install netbox_rpki
```

or by adding to your `local_requirements.txt` or `plugin_requirements.txt` (netbox-docker):

```bash
netbox_rpki
```

Enable the plugin in `/opt/netbox/netbox/netbox/configuration.py`,
 or if you use netbox-docker, your `/configuration/plugins.py` file :

```python
PLUGINS = [
    'netbox_rpki'
]

PLUGINS_CONFIG = {
    "netbox_rpki": {'top_level_menu': False},
}
```

Run  `python -m manage.py migrate` from the .../netbox/netbox/ directory in your netbox installation. (or include the manage.py migrate command in Dockerfile-Plugins if using netbox-docker.)

## Browser E2E Tests

The repo includes a minimal Playwright suite under `tests/e2e/` for real plugin Web UI CRUD coverage.

- It targets a running local NetBox dev instance, defaulting to `http://127.0.0.1:8000`
- It logs in as the local `admin` user created by `devrun/dev.sh start`
- It prepares only the core NetBox prerequisites the plugin forms depend on and cleans up prior E2E-marked plugin objects
- It does not require `dev.sh seed`, though seeded data remains compatible with the suite
- The recommended entry point in WSL is `cd devrun && ./dev.sh e2e`

See `tests/e2e/README.md` for setup, environment variables, and exact commands.
