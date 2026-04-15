# NetBox RPKI Plugin

Netbox plugin for adding BGP RPKI elements.

* Free software: Apache-2.0
* [Documentation](https://menckend.github.io/netbox_rpki)
* [Repository](https://github.com/menckend/netbox_rpki)
* [Python Package](https://pypi.org/project/netbox_rpki/)

## Features

Implements NetBox models, forms, API endpoints, GraphQL types, tables, and standard UI views for modeling Resource Public Key Infrastructure (RPKI) data.

The plugin still covers the original core inventory objects for organizations, resource certificates, ROAs, and their prefix or ASN relationships, and now also includes the implemented standards-aligned data-model expansion for:

- repositories and publication points
- trust anchors, trust anchor locators, and trust anchor keys
- end-entity certificates and a generic signed-object layer
- certificate revocation lists, revoked certificate references, manifests, and manifest entries
- ASPAs, RSCs, and router certificates
- validator instances, validation runs, object validation results, and validated ROA or ASPA payload views
- routing-intent profiles, rules, overrides, and the initial ROA intent and reconciliation result model family
- reusable routing-intent templates, template rules, template bindings, typed routing-intent exceptions, and bulk intent-run orchestration artifacts

This newer model layer is implemented as schema plus registry-driven plugin surfaces. The writable intent-policy objects are available now, while derivation and reconciliation run or result objects are currently read-only reporting surfaces.

The routing-intent workflow now also includes operator-facing template preview and regeneration actions, organization-scoped queued bulk regeneration, typed exception handling during derivation, and operations-dashboard rollups for stale bindings, expiring exceptions, and recent bulk-run health.

The plugin also includes hosted-provider synchronization and reporting surfaces for Krill and ARIN accounts, including imported publication points, signed-object inventory, certificate observations, provider snapshot or diff summaries, and provider-account rollups used by the API, GraphQL, detail views, and operations dashboard. Current hosted-provider coverage is intentionally limited to Krill and ARIN, and ARIN currently supports hosted ROA synchronization only while the shared reporting contract preserves that capability boundary explicitly.

The latest provider-sync reporting work adds stable evidence summaries so imported publication-observation surfaces can explain publication linkage, authored linkage, source ambiguity, freshness, and family-level churn without creating false diffs across unchanged snapshots.

The first IRR coordination slice now adds source-backed IRR import surfaces for configured `IrrSource` records, retained `IrrSnapshot` history, and normalized imported IRR inventory for `route`, `route6`, `route-set`, `as-set`, `aut-num`, and `mntner` families. The initial live adapter targets IRRd-compatible sources through the local IRRd lab, while snapshot-file import remains available for deterministic tests and disconnected development.

The external-validator import slice now extends the existing validation model family with run summaries, object-level evidence details, imported signed-object correlation, and unmatched payload retention. The first concrete adapter targets Routinator `jsonext` data through either the live API or exported snapshot files, and normalizes both validated ROA and ASPA observations into the shared validator run history.

The telemetry substrate slice now adds `TelemetrySource`, retained `TelemetryRun` history, and `BgpPathObservation` persistence for imported MRT-derived JSON snapshots. Each observation preserves raw AS-path text, normalized ASN-sequence JSON, and a stable `path_hash`, so later overlay and historical-comparison slices can correlate route visibility without redesigning the storage contract.

### Models / DB tables

#### Core inventory models

#### Organization
   - Represents a customer or consumer of Regional Internet Registry (RIR) RPKI services.
   - Fields include `org_id`, `name`, `ext_url`, and `parent_rir`.

#### Resource Certificate
   - Represents the resource certificate element of the RPKI architecture.
   - Tracks certificate identity and lifecycle fields such as `issuer`, `subject`, `serial`, `valid_from`, `valid_to`, `auto_renews`, `public_key`, `publication_url`, `ca_repository`, `self_hosted`, and `rpki_org`.
   - Now links into the newer architecture through optional trust-anchor and publication-point references.

#### Route Origination Authorization (ROA)
   - Represents an RPKI ROA authorizing origination of one or more prefixes by an ASN.
   - Tracks `origin_as`, validity dates, `auto_renews`, and the signing resource certificate.
   - Now links into the generic signed-object layer through an optional signed-object reference.

#### ROA Prefix
   - Represents the attestation relationship between a ROA and a prefix, including `max_length`.
   - This model is available through the plugin but is not a top-level menu item.

#### Certificate Prefix
   - Represents the relationship between a resource certificate and a prefix.
   - This model is available through the plugin but is not a top-level menu item.

#### Certificate ASN
   - Represents the relationship between a resource certificate and an ASN.
   - This model is available through the plugin but is not a top-level menu item.

#### Repository and publication models

#### Repository
   - Represents an rsync, RRDP, or mixed repository endpoint used to hold RPKI publication data.

#### Publication Point
   - Represents a publication location within a repository and tracks retrieval and validation state.

#### Trust and certificate hierarchy models

#### Trust Anchor
   - Represents a trust anchor and its rollover state.

#### Trust Anchor Locator
   - Stores TAL-style discovery information for a trust anchor.

#### Trust Anchor Key
   - Represents a published trust-anchor key object and rollover relationships.

#### End-Entity Certificate
   - Represents the EE certificate used to sign individual RPKI signed objects.

#### Signed object and repository-integrity models

#### Signed Object
   - Generic model for published RPKI signed objects such as ROAs, manifests, ASPAs, RSCs, and trust-anchor keys.
   - Tracks object type, publication metadata, manifest linkage, CMS metadata, validity, and validation state.

#### Certificate Revocation List
   - Represents a CRL issued by a resource certificate and linked to publication and manifest state.

#### Revoked Certificate
   - Represents an individual revoked certificate or EE certificate reference carried by a CRL.

#### Manifest
   - Represents an RPKI manifest object.

#### Manifest Entry
   - Represents an individual manifest member and can link to the referenced signed object, certificate, EE certificate, or CRL.

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
   - Represents an external validator and its current run state.

#### Validation Run
   - Represents one validation execution against repository content.

#### Object Validation Result
   - Stores validation outcome and disposition for an individual signed object.

#### Validated ROA Payload
   - Represents a validated prefix-origin payload produced from a ROA.

#### Validated ASPA Payload
   - Represents a validated customer-provider authorization payload produced from an ASPA.

#### Intent and reconciliation models

#### Routing Intent Profile
   - Defines routing-intent policy defaults and prefix or ASN selection behavior.

#### Routing Intent Rule
   - Represents an ordered rule used to include, exclude, or modify derived ROA intent.

#### ROA Intent Override
   - Represents an explicit per-prefix or per-scope exception to derived ROA intent.

#### Intent Derivation Run
   - Stores metadata for a derived-intent calculation run.
   - This is currently exposed as a read-only reporting surface.

#### ROA Intent
   - Represents a derived ROA intent row tied to a derivation run, profile, scope, and optional override.
   - This is currently exposed as a read-only reporting surface.

#### ROA Intent Match
   - Stores a candidate match between a derived intent row and a locally recorded ROA.
   - This is currently exposed as a read-only reporting surface.

#### ROA Reconciliation Run
   - Stores metadata for a reconciliation comparison between intent and published ROA records.
   - This is currently exposed as a read-only reporting surface.

#### ROA Intent Result
   - Stores the intent-side reconciliation result for a derived ROA intent row.
   - This is currently exposed as a read-only reporting surface.

#### Published ROA Result
   - Stores the published-side reconciliation result for a recorded ROA.
   - This is currently exposed as a read-only reporting surface.





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

The plugin currently declares NetBox compatibility for the 4.5.x release line.

Validation completed against real development installs of:

- NetBox 4.5.0
- NetBox 4.5.7

Validation evidence for both versions includes successful plugin bootstrap and `manage.py check` with the plugin enabled. Recent verification against NetBox 4.5.7 also covered the provider-sync, models, imported-provider-registry, API, GraphQL, and view suites together, and browser smoke coverage was run successfully against the NetBox 4.5.0 environment.
Recent NetBox 4.5.7 verification also covers the routing-intent templating and bulk-authoring workflow through focused service, API, view, job, and dashboard tests plus the full plugin suite in the documented non-interactive environment.


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
