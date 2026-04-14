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

### File-by-file implementation checklist

Use this sequence for Slice A. The point is to land the threshold contract first, then thread it through one normalized reporting path before touching UI and API surfaces.

#### 1. `netbox_rpki/models.py`

Mandatory work:

- add `LifecycleHealthPolicy` as an explicit Django model
- use the same standard model base pattern already used by other writable reporting or configuration objects in the plugin
- implement `get_absolute_url()` and `__str__()`
- add `clean()` validation for organization and provider-account consistency
- enforce first-wave scope rules:
    - organization default policy: `provider_account` is null
    - provider override policy: `provider_account.organization == organization`
    - only one policy row per provider account
- keep the first wave bounded to threshold configuration only; do not add hook or event fields here

Acceptance check:

- the model can stand alone as a normal registry-backed CRUD object without any custom workflow behavior yet

#### 2. `netbox_rpki/migrations/`

Mandatory work:

- create a migration named along the lines of `add_lifecycle_health_policy`
- make sure the constraints match the model rules instead of relying only on UI validation
- do not bundle later Slice E hook or event tables into this migration

Acceptance check:

- the migration is self-contained and reversible

#### 3. `netbox_rpki/object_registry.py`

Mandatory work:

- register `LifecycleHealthPolicy` with standard writable metadata
- choose public names deliberately up front:
    - route slug
    - path prefix if needed
    - API basename
    - GraphQL singular and list field names
- place it under an operations or reporting navigation group only if the resulting menu placement is actually useful
- keep the generated detail page path for the first wave unless a real detail-spec need appears

Acceptance check:

- the object gets standard form, filter, table, REST, GraphQL, and CRUD surfaces without any custom view code

#### 4. `netbox_rpki/services/lifecycle_reporting.py`

Mandatory work:

- create the new service module introduced by the plan
- define built-in default threshold constants in one place
- implement `resolve_lifecycle_health_policy()`
- implement `build_provider_lifecycle_health_summary()`
- keep the first implementation focused on these summary sections:
    - `policy`
    - `sync`
    - `expiry`
    - `diff`
    - `attention_summary`
- leave deeper publication rollups for Slice B, but provide a stable placeholder structure so the contract does not change shape later
- ensure the service accepts `visible_snapshot_ids` and `visible_diff_ids` so permission-aware surfaces can reuse it safely

Acceptance check:

- one function call returns the same lifecycle summary shape needed by dashboard, REST, and GraphQL consumers

#### 5. `netbox_rpki/services/provider_sync_contract.py`

Mandatory work:

- audit the current provider-account rollup helpers and delegate to `lifecycle_reporting.py` where Slice A fields overlap
- do not delete `build_provider_account_rollup()` or break existing callers
- keep compatibility by adding lifecycle summary alongside current rollup output, not instead of it

Acceptance check:

- existing provider-sync reporting tests keep passing while the new lifecycle summary becomes available to callers

#### 6. `netbox_rpki/views.py`

Mandatory work:

- refactor `OperationsDashboardView` so `expiry_window_days = 30` stops being the authoritative threshold source
- resolve effective policy per organization or provider account through the new service layer
- keep the current dashboard sections intact in Slice A
- source expiry-window values and attention posture from the lifecycle summary contract instead of hardcoding them locally wherever the contract now provides the answer
- preserve existing permission filtering and visible snapshot or diff handling

Acceptance check:

- the dashboard still renders the same sections, but the expiry and stale-state logic is now policy-driven

#### 7. `netbox_rpki/api/serializers.py`

Mandatory work:

- extend `RpkiProviderAccountSerializer` with a new `lifecycle_health_summary` field
- build it from `build_provider_lifecycle_health_summary()` rather than recomputing dashboard logic inline
- preserve `last_sync_rollup` for backward compatibility

Acceptance check:

- provider-account detail serialization exposes both the legacy rollup and the new lifecycle summary in one response

#### 8. `netbox_rpki/graphql/types.py`

Mandatory work:

- extend `ProviderAccountReportingMixin` with a new `lifecycle_health_summary` field
- reuse the same permission-aware visibility handling already present for `last_sync_rollup`
- call the new reporting service directly; do not duplicate serializer logic here

Acceptance check:

- GraphQL provider-account detail exposes the same normalized lifecycle summary shape as REST

#### 9. `netbox_rpki/api/views.py`

Audit first, edit only if needed:

- check whether the existing provider-account summary action should also surface lifecycle summary data in Slice A
- if the summary action already returns provider-account rows built from shared service output, prefer extending that shared output rather than adding action-specific code
- avoid adding a new custom action in Slice A unless the existing summary route cannot expose the new field cleanly

Acceptance check:

- no view-specific divergence appears between provider-account detail and provider-account summary payloads

#### 10. `netbox_rpki/graphql/schema.py`

Audit first, no default edit expected:

- verify whether the new provider-account field lands automatically through the existing generated type wiring
- only touch schema code if a new top-level aggregate query is explicitly added to Slice A, which is not required by this plan

Acceptance check:

- the provider-account detail query exposes the new field without introducing a new top-level query surface

#### 11. `netbox_rpki/detail_specs.py`

Audit first, no default edit expected:

- the first-wave policy object should generally be able to use the simple generated detail page
- only add a custom detail helper if reviewers decide the provider-account detail page must display `lifecycle_health_summary` in Slice A instead of waiting for later reporting slices

Acceptance check:

- no rich detail spec is added unless it clearly improves operator workflow in this slice

#### 12. `netbox_rpki/jobs.py`

No Slice A change expected:

- do not add periodic reporting or alert jobs yet
- those belong to Slice E once hooks and event audit are in scope

Acceptance check:

- Slice A remains a policy and read-path change only

#### 13. `netbox_rpki/tests/test_models.py`

Mandatory coverage:

- `LifecycleHealthPolicy.clean()` validation
- organization default versus provider override behavior
- uniqueness or constraint behavior where testable at the model layer

#### 14. `netbox_rpki/tests/test_provider_sync.py`

Mandatory coverage:

- `resolve_lifecycle_health_policy()` fallback behavior
- `build_provider_lifecycle_health_summary()` output shape
- visibility-aware handling of hidden snapshots and diffs
- compatibility of existing provider-account rollups after the Slice A refactor

#### 15. `netbox_rpki/tests/test_views.py`

Mandatory coverage:

- dashboard uses policy thresholds rather than an implicit fixed 30-day rule
- at least one view test proves a non-default threshold changes what the dashboard reports

#### 16. `netbox_rpki/tests/test_api.py`

Mandatory coverage:

- `RpkiProviderAccountSerializer` exposes `lifecycle_health_summary`
- provider-account API responses remain backward compatible with `last_sync_rollup`
- summary payload behavior remains aligned if the summary action is extended in Slice A

#### 17. `netbox_rpki/tests/test_graphql.py`

Mandatory coverage:

- provider-account GraphQL detail exposes `lifecycle_health_summary`
- the field respects restricted snapshot and diff visibility just like existing rollup fields

#### 18. Focused execution order

Use this working order while implementing:

1. model and migration
2. registry wiring
3. new reporting service
4. provider-sync compatibility delegation
5. dashboard refactor
6. REST serializer field
7. GraphQL field
8. focused tests
9. full Slice A verification command

#### 19. Explicit non-goals for Slice A

Do not pull these into the first slice while implementing the checklist above:

- publication-evidence deepening
- timeline views
- export endpoints
- alert hooks
- event audit rows
- scheduled reporting jobs
- approval gating or other governance changes

### Execution packets and estimated commit boundaries

Use the checklist above as the source of truth for what belongs in Slice A, but execute it in these smaller packets so each packet can be reviewed and verified on its own.

#### Packet A1 — Policy model and registry substrate

Goal:
land the new threshold object as a normal first-class plugin object before any reporting logic depends on it.

Files expected to change:

- `netbox_rpki/models.py`
- `netbox_rpki/object_registry.py`
- `netbox_rpki/migrations/*add_lifecycle_health_policy*.py`
- `netbox_rpki/tests/test_models.py`
- registry-wide smoke suites only if the new object needs scenario support

What belongs in this packet:

- `LifecycleHealthPolicy` model definition
- model validation and constraints
- migration
- registry metadata and generated surface wiring
- minimal model and registry test coverage

What does not belong in this packet:

- lifecycle summary service code
- dashboard changes
- REST serializer changes
- GraphQL changes

Estimated size:

- about one compact commit
- roughly 1 to 2 hours if no registry naming conflict appears

Recommended verification:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
    netbox_rpki.tests.test_models \
    netbox_rpki.tests.test_forms \
    netbox_rpki.tests.test_filtersets \
    netbox_rpki.tests.test_tables \
    netbox_rpki.tests.test_urls \
    netbox_rpki.tests.test_navigation \
    netbox_rpki.tests.test_graphql
```

Stop condition:

- the new object is fully generated and stable, with no reporting consumers using it yet

##### Exact Packet A1 model recommendation

Recommended base class:

- inherit from `NamedRpkiStandardModel`

Reason:

- it matches the plugin convention for writable configuration objects such as `ROALintRuleConfig`, `RoutingIntentTemplate`, and `RpkiProviderAccount`
- it automatically aligns the new object with generated forms, tables, comments, and tenant support

Recommended model shape:

```python
class LifecycleHealthPolicy(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='lifecycle_health_policies',
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='lifecycle_health_policies',
        blank=True,
        null=True,
    )
    enabled = models.BooleanField(default=True)
    sync_stale_after_minutes = models.PositiveIntegerField(default=120)
    roa_expiry_warning_days = models.PositiveIntegerField(default=30)
    certificate_expiry_warning_days = models.PositiveIntegerField(default=30)
    exception_expiry_warning_days = models.PositiveIntegerField(default=30)
    publication_exchange_failure_threshold = models.PositiveIntegerField(default=1)
    publication_stale_after_minutes = models.PositiveIntegerField(default=180)
    certificate_expired_grace_minutes = models.PositiveIntegerField(default=0)
    alert_repeat_after_minutes = models.PositiveIntegerField(default=360)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('organization__name', 'provider_account__name', 'name')
        constraints = (
            models.UniqueConstraint(
                fields=('provider_account',),
                condition=models.Q(provider_account__isnull=False),
                name='netbox_rpki_lhpolicy_provider_unique',
            ),
            models.UniqueConstraint(
                fields=('organization',),
                condition=models.Q(provider_account__isnull=True),
                name='netbox_rpki_lhpolicy_org_default_unique',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_rpki:lifecyclehealthpolicy', args=[self.pk])

    def clean(self):
        super().clean()
        errors = {}
        if self.provider_account_id is not None:
            if self.provider_account.organization_id != self.organization_id:
                errors['provider_account'] = (
                    'Provider-account override must belong to the same organization as the policy.'
                )
        if self.enabled and self.provider_account_id is None and not self.organization_id:
            errors['organization'] = 'Organization is required.'
        for field_name in (
            'sync_stale_after_minutes',
            'roa_expiry_warning_days',
            'certificate_expiry_warning_days',
            'exception_expiry_warning_days',
            'publication_exchange_failure_threshold',
            'publication_stale_after_minutes',
            'certificate_expired_grace_minutes',
            'alert_repeat_after_minutes',
        ):
            if getattr(self, field_name) is not None and getattr(self, field_name) < 0:
                errors[field_name] = 'Value must be zero or greater.'
        if errors:
            raise ValidationError(errors)
```

Field recommendations to keep fixed in Packet A1:

- keep all threshold fields as integer counts, not timedeltas or JSON
- keep `notes` separate from inherited `comments`; `notes` is operator intent, `comments` remains generic NetBox object commentary
- keep `enabled` so a provider-account override can be retained but not applied
- do not add severity enums, webhook fields, summary caches, or timestamps yet

Recommended default semantics:

- `sync_stale_after_minutes=120`
- `roa_expiry_warning_days=30`
- `certificate_expiry_warning_days=30`
- `exception_expiry_warning_days=30`
- `publication_exchange_failure_threshold=1`
- `publication_stale_after_minutes=180`
- `certificate_expired_grace_minutes=0`
- `alert_repeat_after_minutes=360`

Rationale for these defaults:

- they preserve today’s rough operator posture where 30-day expiry windows already drive dashboard visibility
- they introduce sync and publication staleness thresholds without forcing a same-day operational alert posture
- they are easy to reason about and safe to override later

##### Exact Packet A1 registry recommendation

Recommended public naming:

- `registry_key="lifecyclehealthpolicy"`
- `class_prefix="LifecycleHealthPolicy"`
- `route_slug="lifecyclehealthpolicy"`
- `api_basename="lifecyclehealthpolicy"`
- `graphql_detail_field_name="netbox_rpki_lifecyclehealthpolicy"`
- `graphql_list_field_name="netbox_rpki_lifecyclehealthpolicy_list"`

Reason:

- no collision pressure is visible for this model family, so the standard public naming pattern is acceptable
- using the full explicit name keeps the purpose obvious in UI, API, and GraphQL surfaces

Recommended object-spec block:

```python
build_standard_object_spec(
    registry_key='lifecyclehealthpolicy',
    model=models.LifecycleHealthPolicy,
    class_prefix='LifecycleHealthPolicy',
    label_singular='Lifecycle Health Policy',
    label_plural='Lifecycle Health Policies',
    api_fields=(
        'name',
        'organization',
        'provider_account',
        'enabled',
        'sync_stale_after_minutes',
        'roa_expiry_warning_days',
        'certificate_expiry_warning_days',
        'exception_expiry_warning_days',
        'publication_exchange_failure_threshold',
        'publication_stale_after_minutes',
        'certificate_expired_grace_minutes',
        'alert_repeat_after_minutes',
        'notes',
    ),
    brief_fields=('name', 'organization', 'provider_account', 'enabled'),
    filter_fields=(
        'name',
        'organization',
        'provider_account',
        'enabled',
        'tenant',
    ),
    search_fields=('name__icontains', 'notes__icontains', 'comments__icontains'),
    graphql_fields=(
        ('name', 'str'),
        ('organization_id', 'id'),
        ('provider_account_id', 'id'),
        ('enabled', 'bool'),
    ),
    navigation_group='Governance',
    navigation_label='Lifecycle Health Policies',
    navigation_order=115,
)
```

Navigation recommendation:

- use `Governance` rather than inventing a new group for Packet A1

Reason:

- the plugin currently has no generated `Operations` object group in `object_registry.py`
- the dashboard itself already lives as a special menu item under `Resources`
- `LifecycleHealthPolicy` is closer to an operator control and policy object than a resource inventory object

If reviewers dislike the menu density under `Governance`, the fallback recommendation is:

- keep the object registry-backed but remove navigation metadata for Packet A1

##### Exact Packet A1 scaffolding recommendation

Add these helper and registry-test hooks in the same packet if the new object is added to the registry.

`netbox_rpki/tests/utils.py`:

- add `create_test_lifecycle_health_policy(...)`
- default it to a fresh organization and optional provider account in the same organization
- give it a unique `name` override path just like other shared builders

Recommended helper signature:

```python
def create_test_lifecycle_health_policy(
    name='Lifecycle Health Policy 1',
    organization=None,
    provider_account=None,
    enabled=True,
    sync_stale_after_minutes=120,
    roa_expiry_warning_days=30,
    certificate_expiry_warning_days=30,
    exception_expiry_warning_days=30,
    publication_exchange_failure_threshold=1,
    publication_stale_after_minutes=180,
    certificate_expired_grace_minutes=0,
    alert_repeat_after_minutes=360,
    notes='',
    **kwargs,
):
    ...
```

`netbox_rpki/tests/registry_scenarios.py`:

- add a form scenario builder entry for `lifecyclehealthpolicy`
- add a readonly-instance builder entry even though the object is writable; that is how the shared smoke suites construct instances broadly
- ensure the generated names and any search-visible values are unique-token based

`netbox_rpki/tests/test_models.py`:

- add a focused `LifecycleHealthPolicyTestCase`
- cover provider-account organization mismatch
- cover default-policy uniqueness behavior
- cover provider-account uniqueness behavior

Registry-surface coverage expectation:

- because Packet A1 adds a new standard object family, the normal form, filterset, table, URL, navigation, API, and GraphQL smoke lanes should all run in this packet

##### Exact Packet A1 migration recommendation

Keep the migration intentionally small:

- create the model
- add only the two uniqueness constraints above
- do not seed rows automatically in the migration
- do not add data-migration logic to manufacture organization defaults yet

Reason:

- Slice A service code can safely fall back to built-in defaults when no policy row exists
- avoiding seeded rows keeps the migration reversible and low-risk in mixed environments

#### Packet A2 — Lifecycle summary service and compatibility delegation

Goal:
introduce the normalized lifecycle summary contract and wire it into existing provider reporting without changing the dashboard or public API fields yet.

Files expected to change:

- `netbox_rpki/services/lifecycle_reporting.py`
- `netbox_rpki/services/provider_sync_contract.py`
- `netbox_rpki/tests/test_provider_sync.py`

What belongs in this packet:

- built-in default thresholds
- policy resolution helper
- `build_provider_lifecycle_health_summary()`
- visibility-aware summary handling for snapshots and diffs
- compatibility delegation from existing provider rollup helpers where appropriate

What does not belong in this packet:

- `OperationsDashboardView` refactor
- REST serializer fields
- GraphQL fields

Estimated size:

- one medium commit
- roughly 2 to 3 hours because this is the contract-defining packet

Recommended verification:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
    netbox_rpki.tests.test_provider_sync \
    netbox_rpki.tests.test_models
```

Stop condition:

- one service call returns the stable lifecycle summary shape and existing provider rollup tests remain green

##### Exact Packet A2 service recommendation

Keep all first-wave lifecycle summary logic in `netbox_rpki/services/lifecycle_reporting.py`.

Recommended constants:

```python
LIFECYCLE_HEALTH_SUMMARY_SCHEMA_VERSION = 1

LIFECYCLE_HEALTH_DEFAULTS = {
    'sync_stale_after_minutes': 120,
    'roa_expiry_warning_days': 30,
    'certificate_expiry_warning_days': 30,
    'exception_expiry_warning_days': 30,
    'publication_exchange_failure_threshold': 1,
    'publication_stale_after_minutes': 180,
    'certificate_expired_grace_minutes': 0,
    'alert_repeat_after_minutes': 360,
}
```

Recommended helper layout:

- `resolve_lifecycle_health_policy(...)`
- `get_effective_lifecycle_thresholds(...)`
- `_serialize_lifecycle_policy(policy, thresholds, source)`
- `_build_sync_health_section(provider_account, *, thresholds, now)`
- `_build_expiry_health_section(provider_account, *, thresholds, now)`
- `_build_diff_health_section(provider_account, *, visible_diff_ids=None)`
- `_build_attention_summary(summary)`
- `build_provider_lifecycle_health_summary(...)`

Recommended resolution contract:

1. enabled provider-account override if present
2. enabled organization default if present
3. built-in defaults with `policy_id=None` and `source='built_in_default'`

Recommended summary contract for Packet A2:

```python
{
    'summary_schema_version': 1,
    'policy': {
        'policy_id': 12,
        'policy_name': 'Default Policy',
        'source': 'organization_default',
        'thresholds': {...},
    },
    'sync': {
        'status': 'stale',
        'health': provider_account.sync_health,
        'last_successful_sync': '...',
        'last_sync_status': 'completed',
        'next_sync_due_at': '...',
        'minutes_since_last_success': 181,
        'threshold_minutes': 120,
        'attention_reason': 'Last successful sync exceeds stale threshold.',
    },
    'expiry': {
        'roas': {'warning': 4, 'expired': 0, 'threshold_days': 30},
        'certificates': {'warning': 2, 'expired': 1, 'threshold_days': 30},
        'exceptions': {'warning': 1, 'expired': 0, 'threshold_days': 30},
    },
    'publication': {
        'status': 'pending',
        'summary_schema_version': None,
        'attention_item_count': 0,
    },
    'diff': {
        'latest_diff_id': 91,
        'latest_diff_name': 'Provider Snapshot Diff 91',
        'records_added': 4,
        'records_removed': 2,
        'records_changed': 7,
        'publication_changes': 0,
    },
    'attention_summary': {
        'highest_severity': 'warning',
        'open_issue_count': 6,
        'attention_kinds': ['sync_stale', 'certificate_expiring'],
    },
}
```

Important Packet A2 design choice:

- include the `publication` key now with a placeholder shape even though Slice B will deepen it later

Reason:

- it keeps the lifecycle summary schema stable across later slices
- clients can safely treat publication reporting as additive rather than structurally breaking

Compatibility recommendation for `provider_sync_contract.py`:

- do not replace `build_provider_account_rollup()`
- add `lifecycle_health_summary` to the account-level payload returned by `build_provider_account_rollup()` and by `build_provider_account_summary()`
- keep the old fields untouched so existing tests and clients still pass

Recommended tests for Packet A2:

- no-policy fallback uses built-in defaults
- provider override beats organization default
- disabled override falls back to organization default
- hidden latest diff IDs are nulled or omitted in the diff section just like existing rollups hide invisible related objects
- `summary_schema_version` is stable and asserted in tests

#### Packet A3 — Dashboard refactor onto the policy-driven summary

Goal:
move the operations dashboard from hardcoded threshold logic to the lifecycle reporting service while keeping the existing sections and behavior shape intact.

Files expected to change:

- `netbox_rpki/views.py`
- `netbox_rpki/templates/netbox_rpki/operations_dashboard.html` only if presentation variables must change
- `netbox_rpki/tests/test_views.py`

What belongs in this packet:

- removal of the hard dependency on the fixed `expiry_window_days = 30` value as business logic
- policy-aware threshold selection in the dashboard view
- minimal template adjustments if the rendered context changes shape
- view tests proving non-default policy thresholds affect rendered output

What does not belong in this packet:

- new export actions
- new hook behavior
- API serializer fields
- GraphQL fields

Estimated size:

- one compact to medium commit
- roughly 1 to 2 hours unless the template context needs more reshaping than expected

Recommended verification:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
    netbox_rpki.tests.test_views \
    netbox_rpki.tests.test_provider_sync
```

Stop condition:

- dashboard behavior is policy-driven and existing attention sections still render correctly

##### Exact Packet A3 dashboard recommendation

Do not try to force one global threshold across the entire dashboard once policies become per-organization or per-provider.

Recommended view-level approach:

- keep `OperationsDashboardView` as the only HTML dashboard entry point
- add a small internal helper such as `get_effective_thresholds_for_object(obj)` only if the service call cannot be reused directly
- prefer calling `build_provider_lifecycle_health_summary()` for provider cards and a shared threshold-resolution helper for expiry lists

Important Packet A3 UI decision:

- remove any wording that implies one global `expiry_threshold` date is authoritative for the whole dashboard
- replace it with text such as: `Thresholds follow the effective lifecycle policy for each object or provider account.`

Reason:

- once multiple organizations or provider overrides are visible in one dashboard response, a single threshold date is misleading

Recommended dashboard behavior changes:

- provider-account cards should show lifecycle summary-derived `attention_summary` counts and sync threshold text
- expiring ROA, certificate, and exception sections should include items only if they violate the effective policy for their owning organization or provider context
- keep the current section layout intact in Slice A; do not redesign the dashboard during the threshold refactor

Recommended implementation boundary:

- do not compute threshold rules directly inside `get_expiring_roas()`, `get_expiring_certificates()`, or `get_expiring_exceptions()` if the same logic can live in a shared helper
- move threshold comparison logic into reusable reporting helpers, then have the view consume those helpers

Recommended view tests for Packet A3:

- a 7-day policy excludes an item that would have appeared under the old 30-day window
- a provider-account override can make one provider stale while another provider in the same response is still healthy
- dashboard text no longer claims a single universal expiry threshold when multiple policy scopes are possible

#### Packet A4 — REST and GraphQL surface exposure

Goal:
expose the normalized lifecycle summary through provider-account REST and GraphQL surfaces without breaking existing clients that use `last_sync_rollup`.

Files expected to change:

- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py` only if summary-action payloads need a shared-output extension
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/graphql/schema.py` only if field exposure does not arrive automatically
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_graphql.py`

What belongs in this packet:

- `lifecycle_health_summary` in `RpkiProviderAccountSerializer`
- `lifecycle_health_summary` in `ProviderAccountReportingMixin`
- any minimal provider-account summary-action alignment work if needed
- REST and GraphQL tests for payload shape and visibility filtering

What does not belong in this packet:

- export endpoints
- timeline queries
- alert evaluation

Estimated size:

- one compact commit
- roughly 1 to 2 hours

Recommended verification:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
    netbox_rpki.tests.test_api \
    netbox_rpki.tests.test_graphql \
    netbox_rpki.tests.test_provider_sync
```

Stop condition:

- provider-account REST and GraphQL both expose the same lifecycle summary contract while keeping existing rollup fields intact

##### Exact Packet A4 surface recommendation

REST recommendation:

- add `lifecycle_health_summary = serializers.SerializerMethodField()` to `RpkiProviderAccountSerializer`
- compute it with the same visible snapshot and diff ID filtering already used by `get_last_sync_rollup()`
- if `build_provider_account_summary()` is extended in Packet A2, ensure the provider-account summary action returns per-account `lifecycle_health_summary` in the `accounts` rows too

GraphQL recommendation:

- add `@strawberry.field def lifecycle_health_summary(self, info: Info) -> JSON:` to `ProviderAccountReportingMixin`
- reuse the same permission filtering logic now used by `last_sync_rollup`
- do not add a new top-level query in Slice A; the detail field is sufficient

Recommended alignment rule:

- `RpkiProviderAccountSerializer.get_lifecycle_health_summary()` and `ProviderAccountReportingMixin.lifecycle_health_summary()` should both call the same service function directly
- avoid a serializer-to-GraphQL or GraphQL-to-serializer dependency

Recommended API summary-action shape:

- each row in `provideraccount-summary` should gain a `lifecycle_health_summary` key if Packet A2 already added it to `build_provider_account_summary()`
- do not create a second summary action just for lifecycle data in Slice A

Recommended tests for Packet A4:

- serializer output includes `summary_schema_version`
- GraphQL output includes the same `summary_schema_version`
- hidden snapshot or diff visibility behaves the same in both REST and GraphQL
- old rollup fields remain present and unchanged for backward compatibility

#### Packet A5 — Slice A consolidation and full-lane verification

Goal:
run the full Slice A verification lane, fix any integration regressions, and freeze Slice A as the stable base for Slice B.

Files expected to change:

- only files already touched by Packets A1 through A4
- avoid opportunistic refactors

What belongs in this packet:

- fixing integration breakage from the earlier packets
- tightening tests where contract drift is discovered
- small doc clarifications inside this plan if implementation decisions changed materially

What does not belong in this packet:

- any new capability from Slice B or later

Estimated size:

- one cleanup commit or no-op if all earlier packets are already clean
- roughly 30 to 90 minutes depending on integration fallout

Recommended verification:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
    netbox_rpki.tests.test_provider_sync \
    netbox_rpki.tests.test_views \
    netbox_rpki.tests.test_api \
    netbox_rpki.tests.test_graphql \
    netbox_rpki.tests.test_models
```

Optional final gate before claiming Slice A done:

```bash
cd /home/mencken/src/netbox_rpki/devrun
./dev.sh test contract
```

#### Recommended branchless working rhythm

If you are executing Slice A directly in the shared tree, use this review rhythm:

1. finish Packet A1 and verify before touching service code
2. finish Packet A2 and verify before touching the dashboard
3. finish Packet A3 and verify before touching API and GraphQL
4. finish Packet A4 and verify before running the full Slice A lane
5. use Packet A5 only for integration fallout, not new scope

That sequencing keeps schema, service contract, UI behavior, and surface exposure failures isolated enough to debug without dragging later reporting work into the same pass.

##### Exact Packet A5 consolidation recommendation

Use Packet A5 to freeze the Slice A contract, not to add capability.

Required checks before calling Slice A complete:

- `LifecycleHealthPolicy` CRUD surfaces are stable under registry smoke coverage
- `build_provider_lifecycle_health_summary()` has an asserted schema version and stable top-level keys
- dashboard tests prove policy-driven behavior rather than fixed-threshold behavior
- provider-account REST and GraphQL detail surfaces expose the same lifecycle summary shape
- provider-account summary aggregates still pass existing tests

Recommended documentation cleanup in Packet A5 only if implementation drift occurred:

- update the Packet A2 recommended payload shape if field names changed for legitimate reasons
- update the verification commands if the actual focused test lanes ended up slightly different

Do not use Packet A5 for:

- publication rollup deepening
- export routes
- timeline UI
- hooks or event delivery

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

### Execution packets and exact recommendations

#### Packet B1 — Publication evidence helper enrichment

Goal:
add the missing pure helper functions needed to classify publication attention without changing persisted snapshot summaries yet.

Files expected to change:

- `netbox_rpki/services/provider_sync_evidence.py`
- `netbox_rpki/tests/test_provider_sync.py`

Recommended helpers:

- `build_publication_point_attention_summary(obj, *, now, thresholds)`
- `build_signed_object_attention_summary(obj)`
- `build_certificate_observation_attention_summary(obj, *, now, thresholds)`

Recommended helper output contract:

- compact dicts only
- stable booleans or counts, not localized strings
- no model primary keys inside summary blobs

Important rule:

- keep evidence parsing and linkage-state extraction in `provider_sync_evidence.py`; do not move raw evidence logic into `lifecycle_reporting.py`

#### Packet B2 — Publication-health rollup builders and persisted summary keys

Goal:
compute provider-account, snapshot, and diff publication-health summaries and persist the stable parts into snapshot summary JSON.

Files expected to change:

- `netbox_rpki/services/lifecycle_reporting.py`
- `netbox_rpki/services/provider_sync.py`
- `netbox_rpki/services/provider_sync_contract.py`
- `netbox_rpki/tests/test_provider_sync.py`
- `netbox_rpki/tests/test_provider_sync_krill.py`

Recommended constant:

```python
PUBLICATION_HEALTH_SUMMARY_SCHEMA_VERSION = 1
```

Recommended summary shape:

```python
{
    'summary_schema_version': 1,
    'status': 'attention',
    'publication_points': {
        'total': 4,
        'stale': 1,
        'exchange_failed': 1,
        'exchange_overdue': 2,
        'authored_linkage_missing': 0,
    },
    'signed_objects': {
        'total': 12,
        'stale': 0,
        'authored_linkage_missing': 2,
        'publication_linkage_missing': 1,
        'by_type': {'manifest': 4, 'crl': 4, 'roa': 4},
    },
    'certificate_observations': {
        'total': 9,
        'stale': 1,
        'expiring_soon': 2,
        'expired': 1,
        'ambiguous': 1,
        'publication_linkage_missing': 0,
        'signed_object_linkage_missing': 1,
    },
    'attention_item_count': 6,
}
```

Persistence recommendation:

- write `publication_health` into `ProviderSnapshot.summary_json`
- mirror the latest completed snapshot’s `publication_health` into `provider_account.last_sync_summary_json`
- do not embed imported-object primary keys or snapshot-local IDs in those persisted summaries

Diff recommendation:

- `build_diff_publication_health_rollup(snapshot_diff)` should summarize publication-family churn counts from `ProviderSnapshotDiffItem`
- keep it aggregate-only in the persisted summary; item-level detail stays on the diff-item rows

#### Packet B3 — UI, REST, and GraphQL publication-health exposure

Goal:
surface the richer publication-health rollups through existing provider account, snapshot, and diff pages and APIs.

Files expected to change:

- `netbox_rpki/detail_specs.py`
- `netbox_rpki/views.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/graphql/schema.py` only if a top-level summary query changes
- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_graphql.py`

Recommended surface approach:

- provider-account detail keeps `Publication Observation Health` but now renders the richer schema
- snapshot detail gains a separate publication-health card rather than burying it inside raw summary JSON
- snapshot-diff detail gains a publication-diff summary card built from publication-family diff items
- operations dashboard provider cards show a compact publication attention count or status text, not the full JSON blob

API recommendation:

- extend provider-account summary rows with `publication_health`
- add a snapshot summary field if the object serializer already exposes other derived rollups

GraphQL recommendation:

- extend `ProviderAccountReportingMixin`, `ProviderSnapshotReportingMixin`, and `ProviderSnapshotDiffReportingMixin` with publication-health JSON fields

#### Packet B4 — Slice B consolidation

Goal:
verify stable persistence, stable schema versions, and unchanged data producing unchanged summaries.

Required checks:

- repeated syncs with unchanged publication data do not produce noisy summary drift
- publication-health summary keys carry explicit schema versioning
- dashboard and provider-account views surface attention counts without breaking existing provider summary tests

---

## 9. Slice C — Timeline and Diff-Oriented Reporting

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

### Execution packets and exact recommendations

#### Packet C1 — Timeline summary builders

Goal:
build stable timeline payloads from retained snapshots and diffs without recomputing heavy raw counts every request.

Files expected to change:

- `netbox_rpki/services/lifecycle_reporting.py`
- `netbox_rpki/tests/test_provider_sync.py`

Recommended constants:

```python
LIFECYCLE_TIMELINE_SCHEMA_VERSION = 1
PUBLICATION_DIFF_TIMELINE_SCHEMA_VERSION = 1
```

Recommended builders:

- `build_provider_lifecycle_timeline(provider_account, *, limit=20, visible_snapshot_ids=None, visible_diff_ids=None)`
- `build_provider_publication_diff_timeline(provider_account, *, limit=20, visible_diff_ids=None)`

Recommended timeline row shape:

```python
{
        'timeline_schema_version': 1,
        'snapshot_id': 91,
        'snapshot_name': 'Provider Snapshot 91',
        'snapshot_status': 'completed',
        'fetched_at': '...',
        'completed_at': '...',
        'lifecycle_status': 'attention',
        'publication_status': 'attention',
        'latest_diff_id': 92,
        'records_added': 4,
        'records_removed': 2,
        'records_changed': 7,
        'publication_changes': 3,
}
```

Important rule:

- derive rows from persisted `summary_json` and diff rollups first; only fall back to lightweight queries where persisted data is absent

#### Packet C2 — Detail-page timeline exposure

Goal:
surface timelines through existing detail pages before adding any new standalone HTML view.

Files expected to change:

- `netbox_rpki/detail_specs.py`
- `netbox_rpki/tests/test_views.py`

Recommended UI approach:

- add a `Lifecycle Health Timeline` code-style field or curated summary card to `PROVIDER_ACCOUNT_DETAIL_SPEC`
- add a `Publication Diff Timeline` field or card to `PROVIDER_ACCOUNT_DETAIL_SPEC`
- keep the existing snapshot and snapshot-diff bottom tables; do not add a new HTML template in first-wave Slice C unless the detail card proves unreadable

Reason:

- the provider-account detail page already acts as the operator drill-down hub for snapshots, diffs, and write executions

#### Packet C3 — REST and GraphQL timeline exposure

Goal:
expose the same timeline payloads through machine-readable surfaces.

Files expected to change:

- `netbox_rpki/api/views.py`
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_graphql.py`

Recommended REST approach:

- add detail actions on `RpkiProviderAccountViewSet`:
    - `timeline`
    - `publication-diff-summary`

Recommended GraphQL approach:

- add JSON fields on `ProviderAccountReportingMixin`:
    - `health_timeline`
    - `publication_diff_timeline`

Do not add a new top-level GraphQL query unless provider-account detail field performance becomes a real issue.

#### Packet C4 — Slice C consolidation

Required checks:

- timeline order is deterministic and newest-first
- hidden snapshots or diffs are omitted cleanly
- timeline schema versions are asserted in tests
- provider-account detail remains usable without a new custom HTML template

---

## 10. Slice D — Export Surfaces

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

### Execution packets and exact recommendations

#### Packet D1 — Shared export formatters

Goal:
add one shared export formatting layer that reuses lifecycle reporting builders for both UI download views and API actions.

Files expected to change:

- `netbox_rpki/services/lifecycle_reporting.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_views.py`

Recommended standard-library implementation:

- use `json` for JSON serialization
- use `csv.DictWriter` for CSV generation
- use `HttpResponse` or `JsonResponse` at the view layer

Reason:

- the repo already uses standard-library HTTP client patterns instead of adding extra dependencies
- export formatting does not justify a new third-party dependency

Recommended constants:

```python
LIFECYCLE_EXPORT_SCHEMA_VERSION = 1
```

Recommended helpers:

- `build_lifecycle_export_payload(kind, data, *, filters=None)`
- `iter_lifecycle_export_rows(kind, data)`
- `get_lifecycle_export_filename(kind, fmt, *, provider_account=None)`

Recommended JSON envelope:

```python
{
        'export_schema_version': 1,
        'kind': 'provider_account_lifecycle_summary',
        'format': 'json',
        'exported_at': '...',
        'filters': {...},
        'data': {...},
}
```

#### Packet D2 — UI download endpoints

Goal:
let operators download dashboard and provider-account reporting from the plugin UI without needing token-based API access.

Files expected to change:

- `netbox_rpki/views.py`
- `netbox_rpki/urls.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/tests/test_views.py`

Recommended endpoints:

- `operations/export/` with `format=json|csv`
- `provider-accounts/<pk>/export/lifecycle/` with `format=json|csv`
- `provider-accounts/<pk>/export/timeline/` with `format=json|csv`

Recommended behavior:

- download views call the same shared export helpers as the API
- set `Content-Disposition` with a deterministic filename
- reject unsupported formats with a normal validation response

#### Packet D3 — API export actions

Goal:
offer explicit export actions on provider-account APIs and keep aggregate dashboard export reachable through the provider-account collection route.

Files expected to change:

- `netbox_rpki/api/views.py`
- `netbox_rpki/tests/test_api.py`

Recommended actions:

- `provideraccount-export-summary`
- `provideraccount-export-timeline`
- `provideraccount-summary-export` on the collection route for aggregate dashboard-style provider reporting

Recommended response behavior:

- JSON exports return the envelope directly
- CSV exports return a file download response with stable headers

#### Packet D4 — Slice D consolidation

Required checks:

- CSV headers are explicitly asserted and versioned by test expectation
- export payloads honor filtered querysets and permission restrictions
- JSON export envelopes include `export_schema_version`

---

## 11. Slice E — Alerting Hooks and Event Audit

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

### Execution packets and exact recommendations

#### Packet E1 — Hook and event model substrate

Goal:
introduce the hook configuration object and the event audit object before adding evaluation or delivery logic.

Files expected to change:

- `netbox_rpki/models.py`
- `netbox_rpki/object_registry.py`
- `netbox_rpki/migrations/*lifecycle_health_hook*.py`
- `netbox_rpki/tests/test_models.py`
- registry smoke scaffolding files

Recommended enum additions:

- `LifecycleHealthEventKind`
- `LifecycleHealthEventSeverity`
- `LifecycleHealthEventStatus`

Recommended `LifecycleHealthHook` fields:

- `organization`
- `provider_account`
- `policy`
- `enabled`
- `target_url`
- `secret`
- `headers_json`
- `event_kinds_json`
- `send_resolved`
- `notes`

Recommended `LifecycleHealthEvent` fields:

- `organization`
- `provider_account`
- `policy`
- `hook`
- `related_snapshot`
- `related_snapshot_diff`
- `event_kind`
- `severity`
- `status`
- `dedupe_key`
- `first_seen_at`
- `last_seen_at`
- `last_emitted_at`
- `resolved_at`
- `payload_json`
- `delivery_error`

Recommended model-pattern alignment:

- follow `ProviderWriteExecution` for JSON payload and error-field treatment
- keep `LifecycleHealthEvent` read-only in UI and API from day one

#### Packet E2 — Event evaluation engine

Goal:
open, repeat, and resolve event rows deterministically from lifecycle summaries.

Files expected to change:

- `netbox_rpki/services/lifecycle_reporting.py`
- `netbox_rpki/tests/test_provider_sync.py`
- `netbox_rpki/tests/test_models.py`

Recommended helpers:

- `build_lifecycle_event_candidates(provider_account, *, summary, snapshot=None, snapshot_diff=None)`
- `evaluate_lifecycle_health_events(provider_account, *, summary=None, snapshot=None, snapshot_diff=None)`

Recommended dedupe key shape:

- deterministic text derived from `provider_account_id + event_kind + scoped object identity`
- no raw timestamps in the dedupe key

Recommended evaluation rules:

- open one active event per hook and dedupe key
- update `last_seen_at` when condition still holds
- only mark `repeated` and re-emit after `alert_repeat_after_minutes`
- mark `resolved` when the condition disappears and `send_resolved=True` or the audit model should still record the resolution locally

#### Packet E3 — Hook payload and delivery engine

Goal:
deliver hook payloads using the same standard-library HTTP style already used elsewhere in the plugin.

Files expected to change:

- `netbox_rpki/services/lifecycle_reporting.py`
- `netbox_rpki/tests/test_provider_sync.py`

Recommended delivery implementation:

- use `urllib.request.Request` and `urlopen`
- send JSON with `Content-Type: application/json`
- compute `X-NetBox-RPKI-Signature` as HMAC-SHA256 of the request body using `hook.secret`
- also include `X-NetBox-RPKI-Event` with the event kind

Recommended payload envelope:

```python
{
        'schema_version': 1,
        'event': {...},
        'provider_account': {...},
        'policy': {...},
        'summary': {...},
        'links': {...},
}
```

Recommended delivery failure behavior:

- never delete or suppress the event row because a hook call failed
- store delivery failure text in `delivery_error`
- leave the event available for later repeat or manual inspection

#### Packet E4 — Trigger points, job, and command

Goal:
evaluate events both after sync completion and on a periodic schedule for pure time-based expiry conditions.

Files expected to change:

- `netbox_rpki/services/provider_sync.py`
- `netbox_rpki/jobs.py`
- `netbox_rpki/management/commands/evaluate_lifecycle_health.py`
- `netbox_rpki/tests/test_provider_sync.py`

Recommended trigger points:

1. call `evaluate_lifecycle_health_events(...)` after provider sync completion and summary persistence
2. add `EvaluateLifecycleHealthJob(JobRunner)` for queued execution when needed
3. add `manage.py evaluate_lifecycle_health` with `--dry-run`, `--provider-account`, and `--limit` following the style of `sync_provider_accounts`

Important rule:

- the management command should evaluate accounts and optionally enqueue jobs; it should not duplicate the evaluation logic itself

#### Packet E5 — Slice E surface exposure and consolidation

Goal:
make hooks configurable and event audit visible through normal plugin surfaces.

Files expected to change:

- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/detail_specs.py` only if event payload cards improve usability
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_graphql.py`

Recommended UI and API posture:

- `LifecycleHealthHook` is normal CRUD
- `LifecycleHealthEvent` is read-only and should expose payload plus linked snapshot or diff
- no approval gating, retry queue UI, or delivery dashboard is required in the first wave

Required checks:

- hook scoping works at organization and provider-account level
- open or repeat or resolve semantics are stable under repeated evaluations
- command dry-run behavior is covered just like existing provider-account scheduling commands

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
- `netbox_rpki/management/commands/evaluate_lifecycle_health.py`
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