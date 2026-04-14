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
2. **Slice B** — Family-kind filtering and freshness/staleness table columns across imported
   object tables. No model migrations.
3. **Slice C** — Publication-observation evidence surface depth: rollup service functions and
   detail-spec wiring for cert expiry, signed-object type breakdown, and pub-point health.
   No model migrations.

All three slices read from fields and JSON blobs that already exist. No schema changes or
new model migrations are required at any point in this plan.

The plan is derived from a review of `detail_specs.py`, `tables.py`, `filtersets.py`,
`services/provider_sync_contract.py`, `services/provider_sync_diff.py`,
`services/provider_sync_evidence.py`, and `services/provider_sync.py`
as they stand on April 14, 2026.

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
| `build_provider_snapshot_rollup()` | `services/provider_sync_contract.py` | Returns `family_rollups` and `latest_diff_summary` from a snapshot's `summary_json` |
| `build_provider_snapshot_diff_rollup()` | `services/provider_sync_contract.py` | Returns `family_rollups` from a diff's `summary_json` |
| `PROVIDER_SYNC_FAMILY_METADATA` | `services/provider_sync_contract.py:28` | Maps every family to `family_kind` (`control_plane` or `publication_observation`) and `evidence_source` |
| `family_capability_extra()` | `services/provider_sync_contract.py` | Returns limitation text for LIMITED or NOT_SUPPORTED families |
| `PROVIDER_ACCOUNT_DETAIL_SPEC` | `detail_specs.py:2225` | Shows "Last Sync Summary" as a raw JSON code dump; no per-family rollup card |
| `PROVIDER_SNAPSHOT_DETAIL_SPEC` | `detail_specs.py:2317` | Shows "Family Rollups" and "Latest Diff Summary" as code dumps (via rollup helpers) |
| `PROVIDER_SNAPSHOT_DIFF_DETAIL_SPEC` | `detail_specs.py:2404` | Shows "Family Rollups" and "Summary" as code dumps |
| `PROVIDER_SNAPSHOT_DIFF_ITEM_DETAIL_SPEC` | `detail_specs.py:2430` | Full item fields; no family-kind display column |
| `IMPORTED_CERTIFICATE_OBSERVATION_DETAIL_SPEC` | `detail_specs.py:764` | Detail page is complete with source count, linkage status, evidence summary |
| `IMPORTED_SIGNED_OBJECT_DETAIL_SPEC` | `detail_specs.py:726` | Detail page exists |
| `IMPORTED_PUBLICATION_POINT_DETAIL_SPEC` | `detail_specs.py:688` | Detail page exists |
| `build_certificate_observation_payload()` | `services/provider_sync_evidence.py` | Builds rich evidence payload including sources, linkage status, ambiguity flag |
| `build_signed_object_payload()` | `services/provider_sync_evidence.py` | Builds signed-object payload including manifest/CRL metadata, publication linkage |
| `build_publication_point_payload()` | `services/provider_sync_evidence.py` | Builds pub-point payload including published-object list, authored linkage |
| `get_certificate_observation_*` helpers | `detail_specs.py:15–20` | Imported from `provider_sync_evidence.py`; wired into detail spec but not into list table columns or filtersets |

What does **not** exist today:

| Missing capability | Notes |
|----|---|
| Per-family rollup card on provider account detail | `PROVIDER_ACCOUNT_DETAIL_SPEC` has only raw JSON dump; no `get_provider_account_family_rollups` helper |
| Churn columns on `ProviderSnapshotDiffTable` | diff table shows name, status, compared_at; no `records_added`/`records_removed`/`records_changed` |
| `family_kind` filter on `ProviderSnapshotDiffItemFilterSet` | no way to filter diff items to control_plane or publication_observation families only |
| `is_stale`, `observation_source` filters on `ImportedCertificateObservationFilterSet` | filters exist for other fields but not these |
| `signed_object_type`, `is_stale` filters on `ImportedSignedObjectFilterSet` | no type or staleness filtering |
| `last_exchange_result` filter on `ImportedPublicationPointFilterSet` | no health-status filtering |
| Freshness/staleness columns in imported-family list tables | `ImportedCertificateObservationTable` has no `not_after` or `is_stale` column; `ImportedSignedObjectTable` has no `signed_object_type`; `ImportedPublicationPointTable` has no `last_exchange_result` or `published_object_count` |
| Publication-observation rollup on provider account detail | no cert expiry counts, no pub-point health badge, no signed-object type distribution |
| Signed-object type breakdown on snapshot detail | no per-type count card on `PROVIDER_SNAPSHOT_DETAIL_SPEC` |

---

## 3. Architectural Decisions

All decisions below were made on April 14, 2026.

| ID | Decision |
|----|----------|
| AD-1 | All new rollup computations are **pure service functions** reading from existing model fields (`last_sync_summary_json`, `summary_json`, type/staleness fields). No new model fields, no new migrations. |
| AD-2 | The `family_kind` filter on `ProviderSnapshotDiffItemFilterSet` is a **custom filter method** that maps `control_plane` or `publication_observation` to `object_family__in=[...]` by inspecting `PROVIDER_SYNC_FAMILY_METADATA`. It does not add a `family_kind` column to the database. |
| AD-3 | Churn columns on `ProviderSnapshotDiffTable` (`records_added`, `records_removed`, `records_changed`) are sourced from `instance.summary_json` using a `Column(accessor=...)` approach. They are added as optional table columns, not forced display. |
| AD-4 | The `get_provider_account_family_rollups()` helper in `detail_specs.py` reads `account.last_sync_summary_json` and formats it through `build_provider_snapshot_rollup`-equivalent logic. It does **not** hit the database for the related snapshot; it reads the already-denormalized summary written by `sync_provider_account()`. |
| AD-5 | The publication-observation rollup (`build_provider_account_pub_obs_rollup()`) **queries the database** for the latest completed snapshot, but uses `filter().values().annotate()` form to keep the query lean. It is a service function in `provider_sync_contract.py`, not inline in `detail_specs.py`. |
| AD-6 | The CERTIFICATE_INVENTORY status remains `LIMITED` in the summary contract. The limitation note (already in `KRILL_CERTIFICATE_INVENTORY_LIMITATION_REASON`) will become **operator-visible** via the family rollup card added in Slice A, rather than being buried in the raw JSON dump. No status promotion occurs in this plan. |
| AD-7 | Table columns added in Slice B use the **existing `tables.py` column pattern** (django-tables2 `Column` or `BooleanColumn`). They are not forced to the default display set if the existing tables already have many columns; they are added as available extras. |
| AD-8 | No new URL patterns are required. All changes are to detail specs, table definitions, filterset classes, and service functions. |
| AD-9 | The signed-object type breakdown is computed as a `Counter` over `ImportedSignedObject.objects.filter(provider_snapshot=snapshot).values_list('signed_object_type', flat=True)`. This avoids a join and reuses the existing `signed_object_type` choice field. |

---

## 4. Slice Ordering

```
Slice A  ─── (no deps)
Slice B  ─── (no deps, can run alongside A)
Slice C  ─── depends on Slice A (uses the rollup pattern introduced in A)
```

Recommended order:

1. **Slice A** — Provider-account family health card + diff table churn columns. Self-contained.
   No service-layer changes beyond a helper in `detail_specs.py`. ~2 hours.
2. **Slice B** — Filterset additions and freshness table columns. Self-contained; runs
   independently of Slice A. ~2 hours.
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

- `get_provider_snapshot_family_rollups(snapshot)` in `detail_specs.py` → calls
  `build_provider_snapshot_rollup(snapshot)` from `provider_sync_contract.py`.
- `build_provider_snapshot_rollup` reads `snapshot.summary_json` and returns
  `{'family_rollups': [...], 'latest_diff_summary': {...}}`.
- `RpkiProviderAccount.last_sync_summary_json` — a JSON field that stores the same summary
  structure produced by `sync_provider_account()` on success.

### Changes

#### `detail_specs.py`

1. Add helper `get_provider_account_family_rollups(account: models.RpkiProviderAccount)`:

   ```python
   def get_provider_account_family_rollups(account: models.RpkiProviderAccount) -> str | None:
       from netbox_rpki.services.provider_sync_contract import build_provider_family_rollups
       summary = account.last_sync_summary_json
       if not summary:
           return None
       return get_pretty_json(build_provider_family_rollups(summary))
   ```

   Note: `build_provider_family_rollups(summary_dict)` already exists in
   `provider_sync_contract.py` and is imported in `provider_sync_diff.py`. Confirm its
   signature takes a raw summary dict before wiring.

2. Add helper `get_provider_account_latest_diff_churn(account: models.RpkiProviderAccount)`:

   ```python
   def get_provider_account_latest_diff_churn(account: models.RpkiProviderAccount) -> str | None:
       summary = account.last_sync_summary_json
       if not summary:
           return None
       added = summary.get('records_added', 0)
       removed = summary.get('records_removed', 0)
       changed = summary.get('records_changed', 0)
       total = added + removed + changed
       if total == 0:
           return 'No churn in latest sync'
       return f'+{added} added, -{removed} removed, ~{changed} changed ({total} total)'
   ```

3. In `PROVIDER_ACCOUNT_DETAIL_SPEC`, after the existing "Last Sync Summary" field, add:

   ```python
   DetailFieldSpec(
       label='Family Rollups',
       value=get_provider_account_family_rollups,
       kind='code',
       empty_text='None',
   ),
   DetailFieldSpec(
       label='Latest Sync Churn',
       value=get_provider_account_latest_diff_churn,
       empty_text='None',
   ),
   ```

#### `tables.py`

4. In `ProviderSnapshotDiffTable`, add three columns that read from `summary_json`:

   ```python
   records_added = tables.Column(
       accessor=lambda record: (record.summary_json or {}).get('records_added', 0),
       verbose_name='Added',
   )
   records_removed = tables.Column(
       accessor=lambda record: (record.summary_json or {}).get('records_removed', 0),
       verbose_name='Removed',
   )
   records_changed = tables.Column(
       accessor=lambda record: (record.summary_json or {}).get('records_changed', 0),
       verbose_name='Changed',
   )
   ```

   These are optional columns. Add them to the `Meta.fields` tuple after the existing
   `status` and `compared_at` columns.

### Tests

5. In `tests/test_detail_specs.py` (create or extend):
   - Build a minimal `RpkiProviderAccount` with a hand-crafted `last_sync_summary_json`
     containing `family_summaries` and churn counts; assert `get_provider_account_family_rollups`
     returns a non-None string containing the expected family key.
   - Assert `get_provider_account_latest_diff_churn` returns the expected churn text.

6. In `tests/test_tables.py` (create or extend):
   - Instantiate `ProviderSnapshotDiffTable` with a queryset containing one diff; assert
     `records_added`, `records_removed`, `records_changed` column accessors resolve without
     error.

### Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python \
  manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_detail_specs \
  netbox_rpki.tests.test_tables
```

---

## 6. Slice B — Family-Kind Filtering and Freshness Table Columns

### Goal

Give operators filterable access to diff items by family kind (control-plane vs
publication-observation), and expose staleness / freshness / type columns in list tables
for imported certificate observations, signed objects, and publication points.

### What already exists

- `ProviderSnapshotDiffItem.object_family` — stores the raw family choice value
  (e.g., `'roa_authorizations'`, `'certificate_inventory'`).
- `PROVIDER_SYNC_FAMILY_METADATA` — maps each family to `family_kind`.
- `ImportedCertificateObservation.is_stale`, `not_after`, `observation_source` — all
  stored fields on the model.
- `ImportedSignedObject.signed_object_type`, `is_stale` — stored fields.
- `ImportedPublicationPoint.last_exchange_result`, `published_object_count` — stored fields.

### Changes

#### `filtersets.py`

1. In `ProviderSnapshotDiffItemFilterSet`, add a custom `family_kind` filter:

   ```python
   family_kind = django_filters.ChoiceFilter(
       choices=[
           ('control_plane', 'Control Plane'),
           ('publication_observation', 'Publication Observation'),
       ],
       method='filter_family_kind',
       label='Family Kind',
   )

   def filter_family_kind(self, queryset, name, value):
       from netbox_rpki.services.provider_sync_contract import PROVIDER_SYNC_FAMILY_METADATA
       matching_families = [
           family
           for family, meta in PROVIDER_SYNC_FAMILY_METADATA.items()
           if meta.get('family_kind') == value
       ]
       return queryset.filter(object_family__in=matching_families)
   ```

2. In `ImportedCertificateObservationFilterSet`, add:

   ```python
   is_stale = django_filters.BooleanFilter(label='Is Stale')
   observation_source = django_filters.MultipleChoiceFilter(
       choices=models.CertificateObservationSource.choices,
       label='Observation Source',
   )
   ```

   Ensure `is_stale` and `observation_source` appear in `Meta.fields`.

3. In `ImportedSignedObjectFilterSet`, add:

   ```python
   signed_object_type = django_filters.MultipleChoiceFilter(
       choices=models.SignedObjectType.choices,
       label='Signed Object Type',
   )
   is_stale = django_filters.BooleanFilter(label='Is Stale')
   ```

4. In `ImportedPublicationPointFilterSet`, add:

   ```python
   last_exchange_result = django_filters.CharFilter(
       label='Last Exchange Result',
       lookup_expr='icontains',
   )
   ```

#### `tables.py`

5. In `ImportedCertificateObservationTable`, add:

   ```python
   not_after = tables.DateTimeColumn(verbose_name='Not After')
   is_stale = tables.BooleanColumn(verbose_name='Stale')
   ```

   Add both to `Meta.fields` after the existing `observation_source` column.

6. In `ImportedSignedObjectTable`, add:

   ```python
   signed_object_type = tables.Column(verbose_name='Type')
   is_stale = tables.BooleanColumn(verbose_name='Stale')
   ```

7. In `ImportedPublicationPointTable`, add:

   ```python
   last_exchange_result = tables.Column(verbose_name='Last Exchange Result')
   published_object_count = tables.Column(verbose_name='Published Objects')
   ```

8. In `ProviderSnapshotDiffItemTable`, add:

   ```python
   object_family = tables.Column(verbose_name='Family')
   ```

   This is already a model field; just confirm it is included in `Meta.fields`.

### Tests

9. In `tests/test_filtersets.py`:
   - `ProviderSnapshotDiffItemFilterSet`: create two diff items — one ROA_AUTHORIZATIONS
     (control_plane), one CERTIFICATE_INVENTORY (publication_observation); assert `family_kind`
     filter correctly partitions them.
   - `ImportedCertificateObservationFilterSet`: create one stale and one non-stale record;
     assert `is_stale=True` returns only the stale record.
   - `ImportedSignedObjectFilterSet`: create records of two types; assert `signed_object_type`
     filter returns only the matching type.

### Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python \
  manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_filtersets \
  netbox_rpki.tests.test_tables
```

---

## 7. Slice C — Publication-Observation Evidence Surface Depth

### Goal

Add two new service functions that aggregate publication-observation health at the provider
account and snapshot levels, and wire them into the detail specs so operators can see:

- Cert observation expiry counts (expiring soon, already expired) on the account detail page.
- Signed-object type distribution on the snapshot detail page.
- Publication-point exchange health on the account detail page.

No model changes. No table or filterset changes (those are done in Slice B).

### What already exists

- `ImportedCertificateObservation.not_after` and `is_stale` — stored on each record.
- `ImportedSignedObject.signed_object_type` — stored on each record.
- `ImportedPublicationPoint.last_exchange_result` — stored on each record.
- `KRILL_CERTIFICATE_INVENTORY_LIMITATION_REASON` — already in
  `provider_sync_contract.py`; referenced by `family_capability_extra()` but not operator-
  visible until the family rollup card from Slice A is wired.

### Changes

#### `services/provider_sync_contract.py`

1. Add `build_provider_account_pub_obs_rollup(provider_account)` service function:

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

       from django.db.models import Value
       pub_point_count = rpki_models.ImportedPublicationPoint.objects.filter(
           provider_snapshot=latest_snapshot,
       ).count()
       pub_point_exchange_failed = rpki_models.ImportedPublicationPoint.objects.filter(
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
               'exchange_not_ok': pub_point_exchange_failed,
           },
       }
   ```

   Import `timedelta` from `datetime` at the top of the function or the module.

2. Add `build_snapshot_signed_object_type_breakdown(snapshot)` service function:

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

3. Add `get_provider_account_pub_obs_rollup(account)`:

   ```python
   def get_provider_account_pub_obs_rollup(account: models.RpkiProviderAccount) -> str | None:
       from netbox_rpki.services.provider_sync_contract import build_provider_account_pub_obs_rollup
       return get_pretty_json(build_provider_account_pub_obs_rollup(account))
   ```

4. In `PROVIDER_ACCOUNT_DETAIL_SPEC`, add after the "Family Rollups" field added in Slice A:

   ```python
   DetailFieldSpec(
       label='Publication Observation Health',
       value=get_provider_account_pub_obs_rollup,
       kind='code',
       empty_text='None',
   ),
   ```

5. Add `get_provider_snapshot_signed_object_type_breakdown(snapshot)`:

   ```python
   def get_provider_snapshot_signed_object_type_breakdown(snapshot: models.ProviderSnapshot) -> str | None:
       from netbox_rpki.services.provider_sync_contract import build_snapshot_signed_object_type_breakdown
       breakdown = build_snapshot_signed_object_type_breakdown(snapshot)
       if not breakdown:
           return None
       return get_pretty_json(breakdown)
   ```

6. In `PROVIDER_SNAPSHOT_DETAIL_SPEC`, add after the "Family Rollups" field:

   ```python
   DetailFieldSpec(
       label='Signed Object Type Breakdown',
       value=get_provider_snapshot_signed_object_type_breakdown,
       kind='code',
       empty_text='None',
   ),
   ```

### Tests

7. In `tests/test_provider_sync_contract.py` (create or extend):
   - `build_provider_account_pub_obs_rollup`: create a provider account, a completed snapshot,
     and cert observation + pub point records; assert the rollup returns correct total, stale,
     and expiring-soon counts.
   - `build_snapshot_signed_object_type_breakdown`: create a snapshot with signed objects of
     two types; assert the breakdown dict contains both keys with correct counts.

8. In `tests/test_detail_specs.py`:
   - Assert `get_provider_account_pub_obs_rollup` returns `None` when no snapshot exists.
   - Assert `get_provider_snapshot_signed_object_type_breakdown` returns `None` for a snapshot
     with no signed objects.

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
| Operations dashboard churn card | Overlaps with the P9 lifecycle and publication health reporting work; dashboard is the P9 surface layer |
| `ProviderSnapshotDiffItem` cross-snapshot trend queries | P9 territory; requires additional aggregation/timeseries models beyond what this plan adds |
| Promoting `CERTIFICATE_INVENTORY` status from `LIMITED` to `COMPLETED` | The limitation text is accurate; this plan surfaces it via the family rollup card, but does not reclassify it |
| Provider-backed ASPA write-back | Priority 3 work |
| ROA or ASPA change plan governance | Priority 8 work |

---

## 10. Closure Criteria

This plan is complete when all of the following are true:

- `PROVIDER_ACCOUNT_DETAIL_SPEC` shows a structured family rollup card and a publication
  observation health card, not just a raw JSON dump.
- `ProviderSnapshotDiffTable` shows `records_added`, `records_removed`, `records_changed`
  columns populated from `summary_json`.
- `ProviderSnapshotDiffItemFilterSet` accepts a `family_kind` parameter and correctly
  partitions diff items between control-plane and publication-observation families.
- `ImportedCertificateObservationFilterSet` accepts `is_stale` and `observation_source`
  filters.
- `ImportedSignedObjectFilterSet` accepts `signed_object_type` and `is_stale` filters.
- `ImportedPublicationPointFilterSet` accepts `last_exchange_result` filter.
- `ImportedCertificateObservationTable`, `ImportedSignedObjectTable`, and
  `ImportedPublicationPointTable` each expose the new columns described in Slice B.
- `PROVIDER_SNAPSHOT_DETAIL_SPEC` shows a "Signed Object Type Breakdown" field.
- Focused tests for each slice are green.
- Full plugin suite (`netbox_rpki`) is green with `--keepdb --noinput`.
- No new model migrations were created.
