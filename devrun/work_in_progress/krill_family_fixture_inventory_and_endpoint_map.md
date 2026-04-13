# Krill Family Fixture Inventory and Endpoint Map

Last updated: April 12, 2026

## Scope

This packet inventories the next Krill sync families after routes and ASPAs, using only:

- repo evidence already present in this workspace
- public Krill 0.16.0 documentation
- public Krill testbed documentation where it confirms test-surface availability

This packet does not implement importer behavior. It only lands deterministic fixture support and a written endpoint map for follow-on parser and importer work.

## Current repo baseline

- Current live Krill sync support is limited to routes and ASPAs.
- Existing adapter endpoints are in `netbox_rpki/services/provider_sync_krill.py`.
- Existing deterministic Krill route and ASPA payloads were previously inline in `netbox_rpki/tests/test_provider_sync.py` and are now centralized in `netbox_rpki/tests/krill_payloads.py`.

## Public evidence used

- Krill CLI/API manual, stable 0.16.0: `https://krill.docs.nlnetlabs.nl/en/stable/cli.html`
- Krill child-management guide: `https://krill.docs.nlnetlabs.nl/en/stable/manage-children.html`
- Krill ASPA guide: `https://krill.docs.nlnetlabs.nl/en/stable/manage-aspas.html`
- Krill testbed guide: `https://krill.docs.nlnetlabs.nl/en/stable/testbed.html`
- Public testbed landing page referenced by the official docs: `https://testbed.krill.cloud/index.html#/testbed`
- Public Krill source references for API type shapes and route dispatch in `NLnetLabs/krill`

## Tier split

### Tier 1: actionable now

These families are exposed directly enough by the current public Krill surface to justify deterministic parser fixtures now.

| Family | Why Tier 1 now |
| --- | --- |
| `ca_metadata` | Public docs show `krillc show --api` with a stable CA JSON payload at `GET /api/v1/cas/{ca}`. |
| `parent_links` | Public docs show both parent status inventory and per-parent contact detail endpoints. |
| `child_links` | Public docs show child handles in CA detail plus child info and child connection-status endpoints. |
| `resource_entitlements` | Public docs expose entitlement data directly in parent status responses and child info responses, even though there is no dedicated entitlement-only endpoint. |
| `publication_points` | Public docs show both configured repository metadata and repository sync status with published-object summaries. |

### Tier 2: staged / not yet confirmed enough

| Family | Why not Tier 1 in this packet |
| --- | --- |
| `certificate_inventory` | No public dedicated certificate-inventory endpoint is documented. Certificate material exists only as nested data inside CA detail, parent status, and repo-status payloads. That is enough to plan derived inventory work, but not enough to claim a clean first-class inventory surface yet. No standalone fixture is added here. |

## Endpoint map

### `ca_metadata`

- Primary endpoint: `GET /api/v1/cas/{ca}`
- Public evidence: `krillc show --ca <ca> --api`
- Fixture: `KRILL_CA_METADATA_JSON`
- Current actionable fields confirmed in docs/source:
  - `handle`
  - `id_cert`
  - `repo_info`
  - `parents`
  - `resources`
  - `resource_classes`
  - `children`
  - `suspended_children`
- Notes:
  - This is the best current root payload for the synced CA.
  - It also supplies child-handle discovery for follow-on child-link fetches.

### `parent_links`

- Inventory/status endpoint: `GET /api/v1/cas/{ca}/parents`
- Detail/contact endpoint: `GET /api/v1/cas/{ca}/parents/{parent}`
- Public evidence:
  - `krillc parents statuses --ca <ca> --api`
  - `krillc parents contact --ca <ca> --parent <parent> --api`
- Fixtures:
  - `KRILL_PARENT_STATUSES_JSON`
  - `KRILL_PARENT_CONTACT_JSON`
- Current actionable fields confirmed in docs/source:
  - parent handle map key
  - `last_exchange`
  - `last_success`
  - `all_resources`
  - `classes[*].class_name`
  - `classes[*].resource_set`
  - `classes[*].not_after`
  - `classes[*].signing_cert`
  - `classes[*].issued_certs`
  - contact payload `type`, `tag`, `id_cert`, `parent_handle`, `child_handle`, `service_uri`

### `child_links`

- Child-handle discovery endpoint: `GET /api/v1/cas/{ca}`
- Per-child info endpoint: `GET /api/v1/cas/{ca}/children/{child}`
- Child connection-status endpoint: `GET /api/v1/cas/{ca}/stats/children/connections`
- Public evidence:
  - `krillc show --ca <ca> --api`
  - `krillc children info --ca <ca> --child <child> --api`
  - `krillc children connections --ca <ca> --api`
- Fixtures:
  - `KRILL_CA_METADATA_JSON` for `children` and `suspended_children`
  - `KRILL_CHILD_INFO_JSON`
  - `KRILL_CHILD_CONNECTIONS_JSON`
- Current actionable fields confirmed in docs/source:
  - child handles as simple arrays on CA detail
  - child `state`
  - child `id_cert`
  - child `entitled_resources`
  - child connection `last_exchange`, `result`, `user_agent`
- Notes:
  - There is no documented `GET /api/v1/cas/{ca}/children` list endpoint for inventory.
  - Child-link inventory is still Tier 1 because the documented surface is sufficient when composed from the three endpoints above.

### `resource_entitlements`

- Aggregate CA resources: `GET /api/v1/cas/{ca}`
- Parent-issued entitlements: `GET /api/v1/cas/{ca}/parents`
- Delegated child entitlements: `GET /api/v1/cas/{ca}/children/{child}`
- Public evidence:
  - `krillc show --ca <ca> --api`
  - `krillc parents statuses --ca <ca> --api`
  - `krillc children info --ca <ca> --child <child> --api`
- Fixtures reused:
  - `KRILL_CA_METADATA_JSON`
  - `KRILL_PARENT_STATUSES_JSON`
  - `KRILL_CHILD_INFO_JSON`
- Current actionable fields confirmed in docs/source:
  - total CA `resources`
  - parent-side `all_resources`
  - per-class `resource_set`
  - child-side `entitled_resources`
- Notes:
  - This family is Tier 1 even though it does not have a dedicated entitlement-only endpoint.
  - Follow-on parser work should treat this as a derived family sourced from documented CA, parent, and child payloads.

### `publication_points`

- Repository metadata endpoint: `GET /api/v1/cas/{ca}/repo`
- Repository status endpoint: `GET /api/v1/cas/{ca}/repo/status`
- Public evidence:
  - `krillc repo show --ca <ca> --api`
  - `krillc repo status --ca <ca> --api`
- Fixtures:
  - `KRILL_REPO_DETAILS_JSON`
  - `KRILL_REPO_STATUS_JSON`
- Current actionable fields confirmed in docs/source:
  - `service_uri`
  - `repo_info.sia_base`
  - `repo_info.rrdp_notification_uri`
  - `last_exchange`
  - `next_exchange_before`
  - `published[*].uri`
  - `published[*].base64`
- Notes:
  - This is the cleanest current source for publication topology and freshness.
  - The `published` list is also the only currently documented object stream that hints at repository contents beyond ROA and ASPA configuration intent.

### `certificate_inventory`

- Candidate derived sources only, not a confirmed first-class endpoint:
  - nested certificate material inside `GET /api/v1/cas/{ca}` resource-class keys
  - nested certificate material inside `GET /api/v1/cas/{ca}/parents` class status entries
  - published repository objects inside `GET /api/v1/cas/{ca}/repo/status`
- Public evidence:
  - `krillc show --ca <ca> --api`
  - `krillc parents statuses --ca <ca> --api`
  - `krillc repo status --ca <ca> --api`
- Status in this packet: Tier 2
- Reason:
  - The public docs do not present a dedicated certificate inventory endpoint or a documented top-level JSON list for certificates comparable to routes, ASPAs, parents, or repo status.
  - Public source confirms certificate-bearing structures exist, but the importer contract for a normalized inventory would still be derived and opinionated.
- Decision:
  - Do not add standalone certificate inventory fixtures in this packet.
  - Revisit in the parser wave only after either live captures or a stronger source-backed normalization decision exists.

## Fixture inventory added in this packet

All deterministic payloads landed under `netbox_rpki/tests/krill_payloads.py`.

- Confirmed Tier 1 fixture payloads:
  - `KRILL_CA_METADATA_JSON`
  - `KRILL_PARENT_STATUSES_JSON`
  - `KRILL_PARENT_CONTACT_JSON`
  - `KRILL_CHILD_INFO_JSON`
  - `KRILL_CHILD_CONNECTIONS_JSON`
  - `KRILL_REPO_DETAILS_JSON`
  - `KRILL_REPO_STATUS_JSON`
- Existing baseline payloads retained and centralized for completeness:
  - `KRILL_ROUTES_JSON`
  - `KRILL_ASPAS_JSON`

## Assumptions and blockers

- Assumption: synthetic fixture values are acceptable as long as field names and top-level shape are constrained to documented Krill payloads.
- Assumption: future parser work can treat `resource_entitlements` as a composed family sourced from multiple documented endpoints.
- Blocker for `certificate_inventory`: public docs and public testbed material do not expose a dedicated inventory endpoint, so claiming a first-class certificate family now would force an opinionated derived model too early.
- Public testbed docs confirm that a shared Krill testbed exists for experimentation, but they do not add extra anonymous JSON inventory endpoints beyond the normal documented API surface.