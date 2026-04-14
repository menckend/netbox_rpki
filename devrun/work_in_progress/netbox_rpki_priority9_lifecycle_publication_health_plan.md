# Priority 9: Lifecycle, Expiry, and Publication Health Reporting — Implementation Plan

**Created:** April 14, 2026
**Status:** Planned implementation track for the remaining Priority 9 reporting gaps
**Depends on:** Priority 2 provider-sync maturation slices 1-4 already in place
**Out of scope:** External validator ingest and BGP telemetry overlays remain Priority 11 work

---

## 1. Purpose

This document is the implementation runbook for backlog Priority 9.

It addresses the remaining gap recorded in the backlog:

> "exports, thresholds, alerting hooks, publication-observation data, and richer timeline or diff-oriented reporting"

The current repository already has the basic dashboard and provider-sync evidence substrate.
Priority 9 is now a reporting-maturity track, not a greenfield reporting feature.

This plan closes the remaining gap through five implementation slices:

1. **Slice A** — configurable lifecycle-health thresholds and a normalized reporting contract
2. **Slice B** — deeper publication-observation rollups and dashboard attention signals
3. **Slice C** — timeline and diff-oriented reporting surfaces built on retained snapshots and diffs
4. **Slice D** — explicit export surfaces for dashboard, provider-account, and publication-health views
5. **Slice E** — alerting hooks with audited event persistence and deduplicated delivery

The target is not a second monitoring platform.
The target is a coherent operator-facing reporting layer that answers five practical questions:

1. what is stale or approaching expiry
2. which provider accounts or publication families need attention first
3. how the situation changed over time
4. how to export the same evidence outside the UI
5. how to emit state-change alerts without scraping HTML

---

## 2. Current State (read before writing any code)

The codebase already has the core substrate needed for Priority 9.

### Existing reporting and evidence components

| Component | File | Current role |
|-----------|------|--------------|
| `OperationsDashboardView` | `netbox_rpki/views.py` | Renders stale or failed provider syncs, ROA and certificate expiry, stale template bindings, expiring routing-intent exceptions, recent bulk-run health, and reconciliation attention sections |
| `build_provider_account_rollup()` | `netbox_rpki/services/provider_sync_contract.py` | Produces provider-account sync-health and family-rollup summaries reused by UI, REST, and GraphQL |
| `build_provider_account_pub_obs_rollup()` | `netbox_rpki/services/provider_sync_contract.py` | Produces a shallow publication-observation summary from the latest completed snapshot |
| `ProviderSnapshot` | `netbox_rpki/models.py` | Retains completed provider-sync snapshots and summary JSON |
| `ProviderSnapshotDiff` | `netbox_rpki/models.py` | Retains comparison results between snapshots and diff summary JSON |
| `ProviderSnapshotDiffItem` | `netbox_rpki/models.py` | Persists per-family diff items, including publication-observation families |
| `ImportedPublicationPoint` | `netbox_rpki/models.py` | Stores imported publication-point state and exchange timing fields |
| `ImportedSignedObject` | `netbox_rpki/models.py` | Stores imported signed-object inventory, authored linkage, and evidence payload |
| `ImportedCertificateObservation` | `netbox_rpki/models.py` | Stores certificate-observation timing, linkage, and evidence payload |
| `provider_sync_evidence.py` helpers | `netbox_rpki/services/provider_sync_evidence.py` | Build evidence summaries and linkage status for imported publication objects |

### Existing operator coverage

The current implementation already provides:

- provider-account rollups through UI, REST, and GraphQL
- snapshot and diff retention with family rollups and churn summaries
- dashboard visibility for stale or failed sync and near-term expiry windows
- publication-evidence detail pages for imported publication points, signed objects, and certificate observations
- retained diff items that already distinguish control-plane families from publication-observation families

### Current limitations that keep Priority 9 open

These are the remaining gaps this plan is intended to close.

| Missing capability | Why current code is insufficient |
|--------------------|----------------------------------|
| Configurable thresholds | `OperationsDashboardView` currently hardcodes `expiry_window_days = 30`, and there is no explicit policy object for stale-sync, stale-publication, or alert cooldown thresholds |
| A single normalized lifecycle-health summary | Current rollups are split across dashboard helpers and provider-sync summaries; there is no one contract that UI, REST, GraphQL, exports, and hooks all reuse |
| Deeper publication-observation reporting | Current publication rollup is intentionally shallow: certificate counts and publication-point exchange failures only |
| Timeline reporting | Snapshots and diffs are retained, but there is no intentional timeline view or export built from them |
| Export surfaces | Operators can inspect data in the UI, but cannot cleanly export dashboard or provider-health reporting as JSON or CSV |
| Alerting hooks | There is no durable alert event model, no outgoing hook contract, and no state-change evaluator |

### Scope boundary relative to Priority 11

Priority 9 must stay provider-side and publication-side.

Do not absorb these into this plan:

- external validator ingest
- BGP telemetry ingest
- approval gating driven by external overlays

Those remain Priority 11 work and should later attach to the reporting substrate created here.

---

## 3. Architectural Decisions

All decisions below are considered resolved for the first implementation wave.

| ID | Decision |
|----|----------|
| AD-1 | Priority 9 reporting stays additive and read-only. It must not bypass reconciliation, change planning, approval, or provider-write workflows. |
| AD-2 | Existing `ProviderSnapshot`, `ProviderSnapshotDiff`, `ProviderSnapshotDiffItem`, `ImportedPublicationPoint`, `ImportedSignedObject`, and `ImportedCertificateObservation` remain the canonical reporting evidence store. Do not create a second reporting warehouse. |
| AD-3 | Introduce one explicit writable policy model named `LifecycleHealthPolicy`. It is the threshold contract for dashboard, exports, and alert evaluation. |
| AD-4 | `LifecycleHealthPolicy` is resolved at two scopes only in the first wave: organization default and optional provider-account override. Do not add per-user or per-object policies in the first wave. |
| AD-5 | Add a dedicated reporting service module, `netbox_rpki/services/lifecycle_reporting.py`, rather than continuing to expand `provider_sync_contract.py` into a mixed reporting and sync-orchestration module. Existing provider-sync rollup helpers can delegate into the new module where appropriate. |
| AD-6 | Add one explicit writable hook model named `LifecycleHealthHook` and one read-only event audit model named `LifecycleHealthEvent`. Hooks define destinations; events record open, repeated, and resolved alert state. |
| AD-7 | Alert delivery is state-change driven and service-driven. Alerts are evaluated on successful provider-sync completion and by a scheduled periodic job for pure time-based expiry conditions. Alert emission must not happen during page rendering. |
| AD-8 | Exports are generated from the same normalized summary contract used by UI, REST, and GraphQL. There must be no HTML-scrape export path and no export-only business logic. |
| AD-9 | Timeline reporting is built from retained snapshots and diffs plus persisted summary fields. Do not introduce a time-series database or a separate history model in the first wave. |
| AD-10 | Publication-observation reporting should deepen by extracting stable summary fields from existing imported publication objects and their evidence helpers. Prefer first-class summary keys over raw JSON dumps where operator attention depends on them. |
| AD-11 | First-wave Priority 9 reporting is informational. It may highlight elevated risk and emit alerts, but it does not block provider apply or plan approval. |

---

## 4. Proposed Model Additions

Only two new model families are required in the first wave.

### 4.1 `LifecycleHealthPolicy`

Purpose:
persist threshold settings so dashboard rendering, API summaries, exports, and alert hooks all evaluate health consistently.

Proposed fields:

- `organization` — required `ForeignKey(Organization)`
- `provider_account` — optional `ForeignKey(RpkiProviderAccount)` for one-account override
- `enabled` — boolean
- `name` — standard named-model field
- `sync_stale_after_minutes`
- `roa_expiry_warning_days`
- `certificate_expiry_warning_days`
- `exception_expiry_warning_days`
- `publication_exchange_failure_threshold`
- `publication_stale_after_minutes`
- `certificate_expired_grace_minutes`
- `alert_repeat_after_minutes`
- `notes`

Required constraints:

- one enabled default policy per organization where `provider_account IS NULL`
- at most one override policy per provider account
- provider-account override must belong to the same organization as the provider account

Expected behavior:

- if an organization has no explicit policy yet, service code falls back to built-in defaults
- provider-account override wins over organization default
- the effective policy is resolved once per rollup evaluation, not inline per subquery

Expected registry treatment:

- normal CRUD through the registry
- top-level navigation under a reporting or operations group
- standard API and GraphQL exposure

### 4.2 `LifecycleHealthHook`

Purpose:
define where lifecycle-health alerts are delivered.

Proposed fields:

- `organization` — required `ForeignKey(Organization)`
- `provider_account` — optional `ForeignKey(RpkiProviderAccount)` for one-account scoping
- `policy` — optional `ForeignKey(LifecycleHealthPolicy)` to pin a hook to a threshold contract when needed
- `enabled` — boolean
- `name`
- `target_url`
- `secret`
- `headers_json`
- `event_kinds_json` — explicit opt-in list of alert kinds to deliver
- `send_resolved` — boolean
- `notes`

Expected behavior:

- organization-scoped hooks receive events for all matching provider accounts unless narrowed by `provider_account`
- hook delivery stays explicit and plugin-local; do not rely on page-render callbacks or undocumented NetBox internals

Expected registry treatment:

- CRUD through the registry
- hidden from top-level navigation if the reporting menu becomes too noisy; otherwise place under reporting

### 4.3 `LifecycleHealthEvent`

Purpose:
persist alert state and delivery audit so hooks can deduplicate, recover, and explain what was emitted.

Proposed fields:

- `organization`
- `provider_account`
- `policy`
- `hook`
- `related_snapshot` — optional `ForeignKey(ProviderSnapshot)`
- `related_snapshot_diff` — optional `ForeignKey(ProviderSnapshotDiff)`
- `event_kind` — for example `sync_stale`, `publication_exchange_failed`, `certificate_expiring`, `publication_observation_stale`
- `severity`
- `status` — `open`, `repeated`, `resolved`, `delivery_failed`
- `dedupe_key`
- `first_seen_at`
- `last_seen_at`
- `last_emitted_at`
- `resolved_at`
- `payload_json`
- `delivery_error`

Required behavior:

- read-only in both UI and API
- unique active event dedupe by `hook + dedupe_key + resolved_at IS NULL`
- detail view must render the emitted payload and linked snapshot or diff when present

Expected registry treatment:

- read-only reporting object
- list and detail surfaces only
- REST read-only and GraphQL read-only

---

## 5. Normalized Reporting Contract

Priority 9 needs one summary contract shared across UI, REST, GraphQL, exports, and hooks.

Add `netbox_rpki/services/lifecycle_reporting.py` with these primary entry points:

```python
def resolve_lifecycle_health_policy(
    *,
    organization: Organization,
    provider_account: RpkiProviderAccount | None = None,
) -> LifecycleHealthPolicy | None:
    ...


def build_provider_lifecycle_health_summary(
    provider_account: RpkiProviderAccount,
    *,
    policy: LifecycleHealthPolicy | None = None,
    now=None,
    visible_snapshot_ids: set[object] | None = None,
    visible_diff_ids: set[object] | None = None,
) -> dict[str, object]:
    ...


def build_provider_lifecycle_timeline(
    provider_account: RpkiProviderAccount,
    *,
    limit: int = 20,
    policy: LifecycleHealthPolicy | None = None,
) -> list[dict[str, object]]:
    ...
```

First-wave summary shape:

```python
{
    "policy": {
        "policy_id": 12,
        "source": "provider_override",
        "thresholds": {...},
    },
    "sync": {
        "status": "stale",
        "last_successful_sync": "...",
        "next_sync_due_at": "...",
        "minutes_since_last_success": 143,
        "attention_reason": "Sync overdue by threshold",
    },
    "expiry": {
        "roas": {"warning": 4, "expired": 0, "threshold_days": 30},
        "certificates": {"warning": 2, "expired": 1, "threshold_days": 30},
        "exceptions": {"warning": 1, "expired": 0, "threshold_days": 30},
    },
    "publication": {
        "status": "attention",
        "publication_points": {...},
        "signed_objects": {...},
        "certificate_observations": {...},
        "attention_items": [...],
    },
    "diff": {
        "latest_diff_id": 91,
        "records_added": 4,
        "records_removed": 2,
        "records_changed": 7,
        "publication_changes": 3,
    },
    "attention_summary": {
        "highest_severity": "warning",
        "open_issue_count": 6,
        "attention_kinds": [...],
    },
}
```

Important implementation rule:

- dashboard, serializer, GraphQL resolver, export view, and alert evaluator must all call this service rather than each rebuilding their own counts

---

## 6. Slice Ordering

```text
Slice A  ->  Slice B  ->  Slice C  ->  Slice D
   \                         \
    \                         -> Slice E
     -> Slice E after A + B
```

Recommended order:

1. **Slice A** — lifecycle-health policy and normalized summary contract
2. **Slice B** — deeper publication-observation reporting
3. **Slice C** — timeline and diff-oriented reporting surfaces
4. **Slice D** — exports
5. **Slice E** — alerting hooks and event audit

Each slice is independently verifiable. Do not collapse them into one commit-sized rewrite.

---

## 7. Slice A — Lifecycle-Health Policy and Threshold Evaluation

### Goal

Replace hardcoded reporting thresholds with an explicit policy object and one service-owned summary contract.

### Changes

#### `models.py`

Add `LifecycleHealthPolicy` with the fields and constraints listed above.

#### `object_registry.py`

Register `LifecycleHealthPolicy` as a standard writable object family.

#### `services/lifecycle_reporting.py`

Implement:

- `resolve_lifecycle_health_policy()`
- `build_provider_lifecycle_health_summary()`
- helper functions for expiry-window and stale-threshold evaluation

#### `views.py`

Refactor `OperationsDashboardView` to stop using the hardcoded class-level `expiry_window_days` as the canonical threshold source.

Expected view-level change:

- the dashboard reads the effective organization or provider policy once and renders counts from the normalized lifecycle summary
- the view may still use a presentation-only default window while a migration path exists, but the service contract becomes authoritative

#### REST and GraphQL

Extend provider-account REST and GraphQL surfaces with `lifecycle_health_summary`.

Do not remove the existing provider rollup fields immediately. Priority 9 should be additive and compatibility-preserving.

### Tests

Add focused coverage for:

- organization default policy resolution
- provider-account override resolution
- fallback to built-in defaults when no policy exists
- dashboard and REST summary output using policy thresholds rather than fixed literals

### Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_provider_sync \
  netbox_rpki.tests.test_views \
  netbox_rpki.tests.test_api \
  netbox_rpki.tests.test_graphql \
  netbox_rpki.tests.test_models
```

---

## 8. Slice B — Publication-Observation Reporting Depth

### Goal

Promote publication evidence from shallow counts into actionable reporting.

### Required summary additions

At minimum, first-wave publication rollups should expose these operator-facing counts:

- publication points with failing or non-success exchange state
- publication points overdue for exchange based on policy threshold
- stale imported publication observations
- imported signed objects missing authored linkage
- imported signed objects missing publication linkage
- signed-object counts by object type
- certificate observations expiring within policy window
- certificate observations already expired
- certificate observations with ambiguous or weak evidence linkage

### Changes

#### `services/provider_sync_evidence.py`

Keep this file as the evidence parser and linkage-status helper layer.

Add or extend pure helpers for:

- signed-object authored-linkage attention
- publication-point exchange attention
- certificate-observation expiry buckets
- evidence ambiguity or weak-link counts

#### `services/lifecycle_reporting.py`

Add:

- `build_publication_health_rollup(provider_account, *, policy=None)`
- `build_snapshot_publication_health_rollup(snapshot, *, policy=None)`
- `build_diff_publication_health_rollup(snapshot_diff)`

#### `services/provider_sync.py`

On successful sync completion, enrich `ProviderSnapshot.summary_json` and `provider_account.last_sync_summary_json` with normalized publication-health summary keys.

Do not persist raw model primary keys inside these summary sections. Continue the current provider-sync discipline of storing stable summary data rather than snapshot-local IDs.

#### UI, REST, GraphQL surfaces

Expose the deeper publication rollup in:

- provider-account detail
- operations dashboard provider attention cards
- snapshot detail
- snapshot-diff detail
- provider-account REST summary action and GraphQL summary fields

### Tests

Add focused coverage for:

- stale publication-point counts
- failing publication exchange counts
- expiring and expired certificate-observation buckets
- authored-linkage and publication-linkage attention counts for imported signed objects
- stable summary persistence across repeated syncs with unchanged data

### Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_provider_sync \
  netbox_rpki.tests.test_provider_sync_krill \
  netbox_rpki.tests.test_views \
  netbox_rpki.tests.test_api \
  netbox_rpki.tests.test_graphql
```

---

## 9. Slice C — Timeline and Diff-Oriented Reporting

### Goal

Let operators understand change over time without leaving the plugin or manually traversing raw snapshots and diffs.

### Required surface behavior

Provide a provider-account level timeline that includes:

- snapshot timestamps and sync status
- top-level lifecycle-health posture for each point
- churn counts from the latest diff tied to each snapshot where available
- publication-health attention counts
- direct links to snapshot and diff detail pages

### Changes

#### `services/lifecycle_reporting.py`

Add timeline builders that return compact summary points from retained snapshots and diffs.

#### `views.py`

Add custom read-only views or detail-page cards for:

- provider-account health timeline
- recent publication-observation diffs
- recent expiry posture transitions

#### REST and GraphQL

Add provider-account custom actions or fields for:

- `health_timeline`
- `publication_diff_summary`

Important rule:

- timeline payloads should be built from persisted snapshot and diff summaries, not by recomputing heavy per-snapshot counts from scratch on every request

### Tests

Add focused coverage for:

- provider timeline ordering
- visibility filtering when some snapshots or diffs are not viewable
- publication-family diff counts surfacing in the timeline payload
- stable JSON shape for REST and GraphQL timeline output

### Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_provider_sync \
  netbox_rpki.tests.test_views \
  netbox_rpki.tests.test_api \
  netbox_rpki.tests.test_graphql
```

---

## 10. Slice D — Export Surfaces

### Goal

Make the same lifecycle and publication reporting available outside the HTML UI in stable machine-readable forms.

### First-wave export scope

Support both `json` and `csv` for:

- operations dashboard summary
- provider-account lifecycle-health summary
- provider-account timeline
- snapshot-diff publication attention items

### Changes

#### `views.py`

Add download actions from the dashboard and provider-account detail pages.

#### `api/views.py`

Add explicit export actions instead of requiring users to scrape list endpoints manually.

Recommended actions:

- provider-account lifecycle summary export
- provider-account timeline export
- operations dashboard summary export

#### Export contract rules

- JSON exports mirror the service-layer summary structure directly
- CSV exports flatten only stable, operator-meaningful fields
- every export payload includes a schema version string
- exports must honor object visibility and permission filtering

### Tests

Add focused coverage for:

- JSON export schema keys
- CSV header stability
- permission filtering
- provider-account export using effective policy thresholds

### Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_views \
  netbox_rpki.tests.test_api
```

---

## 11. Slice E — Alerting Hooks and Event Audit

### Goal

Emit deduplicated lifecycle-health alerts and persist an audit trail of what was emitted and why.

### Changes

#### `models.py`

Add `LifecycleHealthHook` and `LifecycleHealthEvent`.

#### `object_registry.py`

- `LifecycleHealthHook`: writable standard registry object
- `LifecycleHealthEvent`: read-only registry object

#### `services/lifecycle_reporting.py`

Add:

- `evaluate_lifecycle_health_events(provider_account, *, summary=None, snapshot=None, snapshot_diff=None)`
- `deliver_lifecycle_health_event(event)`
- `build_lifecycle_health_hook_payload(event)`

Required behavior:

- open a new event when a threshold is crossed
- update `last_seen_at` when the condition persists
- emit repeat notifications only after `alert_repeat_after_minutes`
- resolve the active event when the condition clears
- store delivery failures without dropping the event row

#### Trigger points

Use two trigger paths:

1. after successful provider sync completes and the lifecycle summary is refreshed
2. a scheduled job or management command for purely time-based expiry windows that can become actionable without a new sync

Suggested job or command names:

- `EvaluateLifecycleHealthJob`
- `manage.py evaluate_lifecycle_health`

### Hook payload shape

First-wave payload should include:

- event identity and status
- organization and provider-account identity
- severity and event kind
- effective policy identifiers and threshold values
- linked snapshot and diff identifiers when present
- normalized lifecycle summary excerpt
- direct UI URLs for the provider account and relevant snapshot or diff

### Tests

Add focused coverage for:

- event open, dedupe, repeat, and resolve behavior
- hook scoping at organization and provider-account level
- scheduled evaluation of expiry-only events without a fresh sync
- delivery failure persistence

### Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_models \
  netbox_rpki.tests.test_provider_sync \
  netbox_rpki.tests.test_views \
  netbox_rpki.tests.test_api
```

---

## 12. Files Expected To Change During Implementation

The implementation should stay concentrated in these files unless a concrete need appears.

- `netbox_rpki/models.py`
- `netbox_rpki/object_registry.py`
- `netbox_rpki/views.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/graphql/schema.py`
- `netbox_rpki/services/lifecycle_reporting.py`
- `netbox_rpki/services/provider_sync_contract.py`
- `netbox_rpki/services/provider_sync_evidence.py`
- `netbox_rpki/services/provider_sync.py`
- `netbox_rpki/jobs.py`
- `netbox_rpki/tests/test_models.py`
- `netbox_rpki/tests/test_provider_sync.py`
- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_graphql.py`

Do not create a parallel reporting module tree if the existing service layout is sufficient.
The new code should look like a reporting maturity pass on the existing plugin, not a second subsystem.

---

## 13. Release Gate

Priority 9 should not be called complete until all of the following are true:

1. threshold evaluation is policy-driven rather than hardcoded in the dashboard
2. publication-observation rollups expose actionable attention counts beyond the current shallow summary
3. provider-account timeline and diff-oriented views exist in UI plus API or GraphQL form
4. operators can export dashboard or provider-account lifecycle reporting without scraping HTML
5. alert hooks emit deduplicated open and resolve events with durable audit rows
6. focused reporting tests are green and the full plugin suite remains green

Known-good full-suite command remains:

```bash
cd /home/mencken/src/netbox_rpki/devrun
./dev.sh test full
```

---

## 14. Relationship To Later Priorities

This plan intentionally creates a reusable reporting substrate for later work.

- Priority 11 should reuse `LifecycleHealthPolicy`, export contracts, timeline surfaces, and alert hooks once validator and telemetry overlays land.
- Priority 10 can reuse the same export and alert channels for IRR mismatch reporting if that work later becomes operator-visible.
- Priority 8 governance remains separate. Priority 9 surfaces inform operators; they do not become approval gates in the first wave.

Keep that separation intact. Priority 9 is a reporting maturity pass, not a stealth governance rewrite.