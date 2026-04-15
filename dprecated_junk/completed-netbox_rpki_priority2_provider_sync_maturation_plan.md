# Priority 2: Provider Sync Maturation — Implementation Plan

**Created:** April 14, 2026
**Status:** Active maturity track for existing Krill and ARIN adapters only
**Scope constraint:** Krill and ARIN only. Does not introduce new provider modules.

---

## 1. Purpose

This document is the implementation runbook for the Priority 2 provider-sync maturation
work. It addresses the remaining gap in the backlog:

> *"Broader provider coverage, richer family-specific reporting and dashboard roll-ups, deeper
> publication-observation fidelity for certificate and signed-object inventory, and clearer
> operator-facing explanation of churn and freshness at the provider-account level."*

The "broader provider coverage" item is explicitly out of scope per the user constraint. This
plan addresses the remaining three:

1. **Slice A** — Provider-account family health card and diff-table churn columns. No model
   migrations.
2. **Slice B** — Family-kind virtual filter on diff items and promotion of `not_after` and
   `last_exchange_result` to default table columns. No model migrations.
3. **Slice C** — Publication-observation evidence surface depth: two new service functions and
   detail-spec wiring for cert expiry, signed-object type breakdown, and pub-point health.
   No model migrations.

All three slices read from fields and JSON blobs that already exist. No schema changes or
new model migrations are required at any point in this plan.

The plan is derived from a review of `detail_specs.py`, `tables.py`, `filtersets.py`,
`object_registry.py`, `services/provider_sync_contract.py`,
`services/provider_sync_diff.py`, `services/provider_sync_evidence.py`, and
`services/provider_sync.py` as they stand on April 14, 2026.

---

## 2. Current State (read before writing any code)

These components already exist and are complete. Do not recreate or restructure them.

| Component | File | Status |
|-----------|------|--------|
| `_import_krill_records()` | `services/provider_sync.py:726` | Imports all 9 families: ROA_AUTHORIZATIONS, ASPAS, CA_METADATA, PARENT_LINKS, CHILD_LINKS, RESOURCE_ENTITLEMENTS, PUBLICATION_POINTS, SIGNED_OBJECT_INVENTORY, CERTIFICATE_INVENTORY |
| `_import_arin_records()` | `services/provider_sync.py:662` | Imports ROA_AUTHORIZATIONS only; other families return NOT_SUPPORTED summary entries |
| `sync_provider_account()` | `services/provider_sync.py:1273` | Top-level entry; stores per-family summaries in `snapshot.summary_json` and `provider_account.last_sync_summary_json` |
| `build_latest_provider_snapshot_diff()` | `services/provider_sync_diff.py:736` | Auto-builds `ProviderSnapshotDiff` + `ProviderSnapshotDiffItem` records for all families on every completed sync |
| `_diff_family()` | `services/provider_sync_diff.py:122` | Generic family diff: ADDED / REMOVED / CHANGED / UNCHANGED with full before/after state |
| `build_provider_family_rollups(provider_account, *, summary)` | `services/provider_sync_contract.py:348` | Returns enriched per-family rollup list; requires `provider_account` as first positional arg |
| `build_provider_account_rollup(provider_account, *, summary, ...)` | `services/provider_sync_contract.py` | Full account-level rollup including `family_rollups`, `records_added/removed/changed`, `sync_health`, latest snapshot/diff references; reads from `last_sync_summary_json` |
| `build_provider_snapshot_rollup()` | `services/provider_sync_contract.py:408` | Returns `family_rollups` and `latest_diff_summary` from a snapshot |
| `build_provider_snapshot_diff_rollup()` | `services/provider_sync_contract.py:372` | Returns `family_rollups` and top-level churn counts from a diff |
| `PROVIDER_SYNC_FAMILY_METADATA` | `services/provider_sync_contract.py:28` | Maps every family to `family_kind` (`control_plane` or `publication_observation`) and `evidence_source` |
| `family_capability_extra()` | `services/provider_sync_contract.py:102` | Returns limitation text for LIMITED or NOT_SUPPORTED families |
| `ProviderSnapshotDiff.summary_json` | model field | Stores `{'status', 'families', 'totals', 'family_rollups', ...}` where `totals` contains `records_added`, `records_removed`, `records_changed` |
| `PROVIDER_ACCOUNT_DETAIL_SPEC` | `detail_specs.py:2225` | Shows "Last Sync Summary" as a raw JSON code dump; `build_provider_account_rollup` not wired |
| `PROVIDER_SNAPSHOT_DETAIL_SPEC` | `detail_specs.py:2317` | Shows "Family Rollups" and "Latest Diff Summary" as code dumps (via rollup helpers) |
| `PROVIDER_SNAPSHOT_DIFF_DETAIL_SPEC` | `detail_specs.py:2404` | Shows "Family Rollups" and "Summary" as code dumps |
| `IMPORTED_CERTIFICATE_OBSERVATION_DETAIL_SPEC` | `detail_specs.py:764` | Detail page is complete with source count, linkage status, evidence summary |
| `IMPORTED_SIGNED_OBJECT_DETAIL_SPEC` | `detail_specs.py:726` | Detail page exists |
| `IMPORTED_PUBLICATION_POINT_DETAIL_SPEC` | `detail_specs.py:688` | Detail page exists |
| `is_stale`, `observation_source`, `signed_object_type`, `last_exchange_result` filters | `object_registry.py` `filter_fields` | All four are already in their respective `filter_fields`; the registry auto-generates `Meta.fields` entries. `observation_source` and `signed_object_type` are generated as `CharFilter` (exact match), not `MultipleChoiceFilter`. |
| `is_stale`, `signed_object_type`, `published_object_count` table columns | `object_registry.py` `brief_fields` | All are already in `brief_fields` → default-visible in their tables |
| `not_after` table column (`ImportedCertificateObservation`) | `object_registry.py` `api_fields` | In `api_fields` (column available) but **not** in `brief_fields` (not default-visible) |
| `last_exchange_result` table column (`ImportedPublicationPoint`) | `object_registry.py` `api_fields` | In `api_fields` (column available) but **not** in `brief_fields` (not default-visible) |

What does **not** exist today:

| Missing capability | Notes |
|----|---|
| Per-family rollup card on provider account detail | `PROVIDER_ACCOUNT_DETAIL_SPEC` has only a raw JSON dump; `build_provider_account_rollup` is not wired into any detail-spec helper |
| Churn columns on `ProviderSnapshotDiffTable` | These cannot come from the registry because they derive from `summary_json['totals']`, not direct model columns. No manual table subclass exists for this model yet. |
| `family_kind` virtual filter on `ProviderSnapshotDiffItemFilterSet` | Partitioning diff items by control_plane vs publication_observation has no filter; `object_family` is filterable but operators would need to know the raw family strings |
| `not_after` as a **default-visible** column on `ImportedCertificateObservationTable` | Column is available (in `api_fields`) but hidden by default (not in `brief_fields`) |
| `last_exchange_result` as a **default-visible** column on `ImportedPublicationPointTable` | Column is available (in `api_fields`) but hidden by default (not in `brief_fields`) |
| Publication-observation rollup on provider account detail | No cert expiry counts, no pub-point health summary |
| Signed-object type breakdown on snapshot detail | No per-type count on `PROVIDER_SNAPSHOT_DETAIL_SPEC` |

---

## 3. Architectural Decisions

All decisions below were made on April 14, 2026.

| ID | Decision |
|----|----------|
| AD-1 | All new rollup computations are **pure service functions** reading from existing model fields (`last_sync_summary_json`, `summary_json`, type/staleness fields). No new model fields, no new migrations. |
| AD-2 | The `family_kind` filter on `ProviderSnapshotDiffItemFilterSet` is a **custom filter method** that maps `control_plane` or `publication_observation` to `object_family__in=[...]` by inspecting `PROVIDER_SYNC_FAMILY_METADATA`. It does not add a `family_kind` column to the database. The filterset class must be extended by hand in `filtersets.py` since the registry only generates `Meta.fields`-style filters. |
| AD-3 | Churn columns on `ProviderSnapshotDiffTable` (`records_added`, `records_removed`, `records_changed`) are sourced from `summary_json['totals']` using a `Column(accessor=...)` approach. A manual `ProviderSnapshotDiffTable` subclass must be added to `tables.py` following the same pattern as the existing `RpkiProviderAccountTable` subclass. |
| AD-4 | The `get_provider_account_family_rollups()` helper in `detail_specs.py` uses the existing `build_provider_account_rollup(provider_account)` service function (which already reads `last_sync_summary_json` and returns a complete rollup). It does **not** re-implement rollup logic. |
| AD-5 | The publication-observation rollup (`build_provider_account_pub_obs_rollup()`) **queries the database** for the latest completed snapshot, but uses `aggregate()` to keep the queries to two. It is a service function in `provider_sync_contract.py`, not inline in `detail_specs.py`. |
| AD-6 | The CERTIFICATE_INVENTORY status remains `LIMITED` in the summary contract. The limitation note (already in `KRILL_CERTIFICATE_INVENTORY_LIMITATION_REASON`) becomes **operator-visible** via the family rollup card added in Slice A. No status promotion occurs in this plan. |
| AD-7 | Promoting `not_after` and `last_exchange_result` to default-visible table columns is done by adding them to `brief_fields` in their respective `build_standard_object_spec` calls in `object_registry.py`. This makes them default in both the table and the API brief representation. |
| AD-8 | No new URL patterns are required. All changes are to `object_registry.py`, `detail_specs.py`, `tables.py`, `filtersets.py`, and `services/provider_sync_contract.py`. |
| AD-9 | The signed-object type breakdown queries `ImportedSignedObject` with `.values('signed_object_type').annotate(count=Count('pk'))`. This avoids a join and reuses the existing `signed_object_type` choice field. |

---

## 4. Slice Ordering

```
Slice A  ─── (no deps)
Slice B  ─── (no deps, can run alongside A)
Slice C  ─── depends on Slice A (uses the rollup pattern introduced in A)
```

Recommended order:

1. **Slice A** — Provider-account family health card + diff table churn columns. Self-contained.
   Changes to `detail_specs.py` and `tables.py`. ~2 hours.
2. **Slice B** — Family-kind virtual filter + `brief_fields` promotions. Self-contained; runs
   independently of Slice A. ~1 hour.
3. **Slice C** — Publication-observation rollup service functions and wiring. Depends on the
   rollup card pattern established in Slice A. ~3 hours.

Each slice has a focused verification command at the bottom. Do not proceed to the next
slice on the same review cycle until the verification is green.

---

## 5. Slice A — Provider-Account Family Health Card and Diff Table Churn Columns

### Goal

Elevate the provider account detail page from a single raw-JSON dump to a structured per-family
health card. Add churn count columns to the `ProviderSnapshotDiff` list table so operators can
see at a glance which diffs contain material changes without opening each record.

### What already exists

- `build_provider_account_rollup(provider_account, *, summary, ...)` in
  `provider_sync_contract.py` — already computes and returns `family_rollups`,
  `records_added`, `records_removed`, `records_changed`, `sync_health`, latest snapshot/diff
  references, etc. from `last_sync_summary_json`. This is the function to use; do not
  re-implement rollup logic in `detail_specs.py`.
- `ProviderSnapshotDiff.summary_json` — already stores `{'totals': {'records_added': N, ...},
  'family_rollups': [...], ...}` populated by `build_provider_snapshot_diff()`.
- `RpkiProviderAccountTable` in `tables.py` — already a manual subclass of the registry-
  generated table, which is the correct pattern to follow for `ProviderSnapshotDiffTable`.

### Changes

#### `detail_specs.py`

1. Add helper `get_provider_account_family_rollups(account: models.RpkiProviderAccount)`:

   ```python
   def get_provider_account_family_rollups(account: models.RpkiProviderAccount) -> str | None:
       from netbox_rpki.services.provider_sync_contract import build_provider_account_rollup
       if not account.last_sync_summary_json:
           return None
       return get_pretty_json(build_provider_account_rollup(account).get('family_rollups'))
   ```

2. In `PROVIDER_ACCOUNT_DETAIL_SPEC`, after the existing "Last Sync Summary" field, add:

   ```python
   DetailFieldSpec(
       label='Family Rollups',
       value=get_provider_account_family_rollups,
       kind='code',
       empty_text='None',
   ),
   ```

#### `tables.py`

3. Add a `ProviderSnapshotDiffTable` manual subclass following the same pattern as the
   existing `RpkiProviderAccountTable` subclass:

   ```python
   _BaseProviderSnapshotDiffTable = ProviderSnapshotDiffTable


   class ProviderSnapshotDiffTable(_BaseProviderSnapshotDiffTable):
       records_added = tables.Column(
           accessor=lambda record: (record.summary_json or {}).get('totals', {}).get('records_added', 0),
           verbose_name='Added',
           orderable=False,
       )
       records_removed = tables.Column(
           accessor=lambda record: (record.summary_json or {}).get('totals', {}).get('records_removed', 0),
           verbose_name='Removed',
           orderable=False,
       )
       records_changed = tables.Column(
           accessor=lambda record: (record.summary_json or {}).get('totals', {}).get('records_changed', 0),
           verbose_name='Changed',
           orderable=False,
       )

       class Meta(_BaseProviderSnapshotDiffTable.Meta):
           fields = _BaseProviderSnapshotDiffTable.Meta.fields + (
               'records_added', 'records_removed', 'records_changed',
           )
   ```

   Place this block after the `ImportedAspaProviderTable` class, following the same
   "capture base, then subclass" pattern used for `RpkiProviderAccountTable`.

### Tests

4. In `tests/test_detail_specs.py` (create or extend):
   - Build a provider account with a `last_sync_summary_json` containing a non-empty
     `families` dict; assert `get_provider_account_family_rollups` returns a non-None string.
   - Assert it returns `None` when `last_sync_summary_json` is empty.

5. In `tests/test_tables.py` (create or extend):
   - Instantiate `ProviderSnapshotDiffTable` with a queryset containing one diff that has a
     `summary_json` with `totals`; assert `records_added`, `records_removed`,
     `records_changed` column accessors resolve to the expected integers.

### Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python \
  manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_detail_specs \
  netbox_rpki.tests.test_tables
```

---

## 6. Slice B — Family-Kind Virtual Filter and Default-Column Promotions

### Goal

Give operators a single `family_kind` filter to partition diff items by control-plane vs
publication-observation without needing to know the raw family string values. Also make
`not_after` and `last_exchange_result` default-visible in their respective list tables,
which are the two columns currently in `api_fields` but not promoted to `brief_fields`.

### What already exists

- `ProviderSnapshotDiffItem.object_family` — the raw family value; already filterable by
  exact match via the auto-generated filterset.
- `PROVIDER_SYNC_FAMILY_METADATA` — maps each family to `family_kind`.
- `is_stale`, `observation_source`, `signed_object_type`, `last_exchange_result` — all
  already in their respective `filter_fields` and auto-generated as filterset fields.
  `observation_source` and `signed_object_type` are `CharFilter` (exact match), which is
  sufficient; no upgrade is required by this plan.
- `is_stale`, `signed_object_type`, `published_object_count` — already in `brief_fields`
  for their respective objects, making them default-visible table columns.
- `not_after` — in `api_fields` for `ImportedCertificateObservation`, so the column toggle
  can reveal it, but it is not in `brief_fields`.
- `last_exchange_result` — in `api_fields` for `ImportedPublicationPoint`, but not in
  `brief_fields`.

### Changes

#### `filtersets.py`

1. Extend `ProviderSnapshotDiffItemFilterSet` after the auto-generated class is registered
   by adding a custom `family_kind` filter. Because `filtersets.py` uses `globals()` to
   register registry-generated classes, subclass after the loop:

   ```python
   import django_filters as _django_filters

   _BaseProviderSnapshotDiffItemFilterSet = ProviderSnapshotDiffItemFilterSet


   class ProviderSnapshotDiffItemFilterSet(_BaseProviderSnapshotDiffItemFilterSet):
       family_kind = _django_filters.ChoiceFilter(
           choices=[
               ('control_plane', 'Control Plane'),
               ('publication_observation', 'Publication Observation'),
           ],
           method='filter_family_kind',
           label='Family Kind',
       )

       def filter_family_kind(self, queryset, name, value):
           from netbox_rpki.services.provider_sync_contract import PROVIDER_SYNC_FAMILY_METADATA
           matching = [
               family
               for family, meta in PROVIDER_SYNC_FAMILY_METADATA.items()
               if meta.get('family_kind') == value
           ]
           return queryset.filter(object_family__in=matching)
   ```

   Reassign `globals()['ProviderSnapshotDiffItemFilterSet']` after the class definition if
   the views import from `filtersets` by name rather than by lookup.

#### `object_registry.py`

2. In the `importedcertificateobservation` `build_standard_object_spec` call, add
   `'not_after'` to `brief_fields`:

   ```python
   brief_fields=(
       "name", "provider_snapshot", "observation_source",
       "certificate_uri", "not_after", "signed_object_uri", "is_stale"
   ),
   ```

3. In the `importedpublicationpoint` `build_standard_object_spec` call, add
   `'last_exchange_result'` to `brief_fields`:

   ```python
   brief_fields=(
       "name", "provider_snapshot", "service_uri", "publication_uri",
       "last_exchange_result", "published_object_count", "is_stale"
   ),
   ```

### Tests

4. In `tests/test_filtersets.py`:
   - `ProviderSnapshotDiffItemFilterSet`: create two diff items — one `ROA_AUTHORIZATIONS`
     (control_plane) and one `CERTIFICATE_INVENTORY` (publication_observation); assert that
     filtering with `family_kind='control_plane'` returns only the first, and
     `family_kind='publication_observation'` returns only the second.

### Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python \
  manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_filtersets
```

---

## 7. Slice C — Publication-Observation Evidence Surface Depth

### Goal

Add two new service functions that aggregate publication-observation health at the provider
account and snapshot levels, and wire them into the detail specs so operators can see:

- Cert observation expiry counts (total, stale, expiring within 30 days) on the provider
  account detail page.
- Signed-object type distribution on the snapshot detail page.
- Publication-point exchange health on the provider account detail page.

No model changes. No table or filterset changes (those are done in Slice B).

### What already exists

- `ImportedCertificateObservation.not_after` and `is_stale` — stored on each record.
- `ImportedSignedObject.signed_object_type` — stored on each record.
- `ImportedPublicationPoint.last_exchange_result` — stored on each record.
- `KRILL_CERTIFICATE_INVENTORY_LIMITATION_REASON` — already in
  `provider_sync_contract.py`; referenced by `family_capability_extra()` and now
  operator-visible via the family rollup card wired in Slice A.

### Changes

#### `services/provider_sync_contract.py`

1. Add `from datetime import timedelta` to the module-level imports (if not already present).

2. Add `build_provider_account_pub_obs_rollup(provider_account)` service function:

   ```python
   def build_provider_account_pub_obs_rollup(
       provider_account: rpki_models.RpkiProviderAccount,
   ) -> dict[str, object] | None:
       from django.db.models import Count, Q
       from django.utils import timezone

       latest_snapshot = (
           provider_account.snapshots
           .filter(status=rpki_models.ValidationRunStatus.COMPLETED)
           .order_by('-fetched_at')
           .first()
       )
       if latest_snapshot is None:
           return None

       now = timezone.now()
       expiry_window = now + timedelta(days=30)

       cert_counts = rpki_models.ImportedCertificateObservation.objects.filter(
           provider_snapshot=latest_snapshot,
       ).aggregate(
           total=Count('pk'),
           stale=Count('pk', filter=Q(is_stale=True)),
           expiring_soon=Count('pk', filter=Q(
               is_stale=False,
               not_after__isnull=False,
               not_after__lte=expiry_window,
               not_after__gt=now,
           )),
       )

       pub_point_count = rpki_models.ImportedPublicationPoint.objects.filter(
           provider_snapshot=latest_snapshot,
       ).count()
       pub_point_exchange_not_ok = rpki_models.ImportedPublicationPoint.objects.filter(
           provider_snapshot=latest_snapshot,
           last_exchange_result__isnull=False,
       ).exclude(last_exchange_result='').exclude(last_exchange_result='success').count()

       return {
           'snapshot_name': latest_snapshot.name,
           'snapshot_fetched_at': latest_snapshot.fetched_at.isoformat() if latest_snapshot.fetched_at else '',
           'certificate_observations': {
               'total': cert_counts['total'],
               'stale': cert_counts['stale'],
               'expiring_soon': cert_counts['expiring_soon'],
           },
           'publication_points': {
               'total': pub_point_count,
               'exchange_not_ok': pub_point_exchange_not_ok,
           },
       }
   ```

3. Add `build_snapshot_signed_object_type_breakdown(snapshot)` service function:

   ```python
   def build_snapshot_signed_object_type_breakdown(
       snapshot: rpki_models.ProviderSnapshot,
   ) -> dict[str, int]:
       from django.db.models import Count
       rows = (
           rpki_models.ImportedSignedObject.objects
           .filter(provider_snapshot=snapshot)
           .values('signed_object_type')
           .annotate(count=Count('pk'))
           .order_by('signed_object_type')
       )
       return {row['signed_object_type']: row['count'] for row in rows}
   ```

#### `detail_specs.py`

4. Add `get_provider_account_pub_obs_rollup(account)`:

   ```python
   def get_provider_account_pub_obs_rollup(account: models.RpkiProviderAccount) -> str | None:
       from netbox_rpki.services.provider_sync_contract import build_provider_account_pub_obs_rollup
       return get_pretty_json(build_provider_account_pub_obs_rollup(account))
   ```

5. In `PROVIDER_ACCOUNT_DETAIL_SPEC`, add after the "Family Rollups" field added in Slice A:

   ```python
   DetailFieldSpec(
       label='Publication Observation Health',
       value=get_provider_account_pub_obs_rollup,
       kind='code',
       empty_text='None',
   ),
   ```

6. Add `get_provider_snapshot_signed_object_type_breakdown(snapshot)`:

   ```python
   def get_provider_snapshot_signed_object_type_breakdown(snapshot: models.ProviderSnapshot) -> str | None:
       from netbox_rpki.services.provider_sync_contract import build_snapshot_signed_object_type_breakdown
       breakdown = build_snapshot_signed_object_type_breakdown(snapshot)
       if not breakdown:
           return None
       return get_pretty_json(breakdown)
   ```

7. In `PROVIDER_SNAPSHOT_DETAIL_SPEC`, add after the "Family Rollups" field:

   ```python
   DetailFieldSpec(
       label='Signed Object Type Breakdown',
       value=get_provider_snapshot_signed_object_type_breakdown,
       kind='code',
       empty_text='None',
   ),
   ```

### Tests

8. In `tests/test_provider_sync_contract.py` (create or extend):
   - `build_provider_account_pub_obs_rollup`: create a provider account, a completed
     snapshot, and cert observation + pub point records with known staleness and exchange
     result values; assert the rollup returns correct `total`, `stale`,
     `expiring_soon`, and `exchange_not_ok` counts.
   - Assert it returns `None` when the account has no completed snapshot.
   - `build_snapshot_signed_object_type_breakdown`: create a snapshot with signed objects of
     two distinct types; assert the breakdown dict contains both keys with correct counts.

9. In `tests/test_detail_specs.py`:
   - Assert `get_provider_account_pub_obs_rollup` returns `None` when no snapshot exists.
   - Assert `get_provider_snapshot_signed_object_type_breakdown` returns `None` for a
     snapshot with no signed objects.

### Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python \
  manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_provider_sync_contract \
  netbox_rpki.tests.test_detail_specs
```

---

## 8. Full Suite Verification

Run after all three slices are green individually:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python \
  manage.py test --keepdb --noinput netbox_rpki
```

Or via devrun:

```bash
cd /home/mencken/src/netbox_rpki/devrun && ./dev.sh test full
```

---

## 9. Out of Scope

The following items are **explicitly excluded** from this plan per the scope constraint
and backlog ordering rules:

| Item | Why excluded |
|------|-------------|
| New provider adapter (not Krill, not ARIN) | User constraint: "don't let scope expand to additional provider modules" |
| ARIN family expansion beyond ROA_AUTHORIZATIONS | Same constraint; ARIN import path and its NOT_SUPPORTED family summaries remain unchanged |
| Operations dashboard churn card | P9 territory; the dashboard is the P9 surface layer |
| `ProviderSnapshotDiffItem` cross-snapshot trend queries | P9 territory; requires timeseries aggregation beyond this plan |
| Upgrading `observation_source` / `signed_object_type` auto-generated filters to `MultipleChoiceFilter` | Both already work as exact-match filters; `MultipleChoiceFilter` is a UX improvement that can be a standalone trivial task, not a plan slice |
| Promoting `CERTIFICATE_INVENTORY` status from `LIMITED` to `COMPLETED` | The limitation text is accurate; this plan surfaces it via the family rollup card but does not reclassify it |
| Provider-backed ASPA write-back | Priority 3 work |
| ROA or ASPA change plan governance | Priority 8 work |

---

## 10. Closure Criteria

This plan is complete when all of the following are true:

- `PROVIDER_ACCOUNT_DETAIL_SPEC` shows a structured per-family rollup card and a publication
  observation health card, not just a raw JSON dump.
- `ProviderSnapshotDiffTable` shows `records_added`, `records_removed`, `records_changed`
  columns sourced from `summary_json['totals']`.
- `ProviderSnapshotDiffItemFilterSet` accepts a `family_kind` parameter and correctly
  partitions diff items between control-plane and publication-observation families.
- `not_after` is a default-visible column on `ImportedCertificateObservationTable`.
- `last_exchange_result` is a default-visible column on `ImportedPublicationPointTable`.
- `PROVIDER_SNAPSHOT_DETAIL_SPEC` shows a "Signed Object Type Breakdown" field.
- Focused tests for each slice are green.
- Full plugin suite (`netbox_rpki`) is green with `--keepdb --noinput`.
- No new model migrations were created.
