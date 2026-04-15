# ROA Signed-Object Convergence Plan

Prepared: April 15, 2026

## Objective

Replace the legacy `Roa` and `RoaPrefix` models with new models that are structurally aligned with the `SignedObject` data architecture, following the same extension pattern already established by `ASPA`/`ASPAProvider`, `RSC`/`RSCFileHash`, `Manifest`/`ManifestEntry`, and `CertificateRevocationList`.

After convergence, a ROA is no longer a freestanding object that *optionally* links to a `SignedObject`. Instead, a ROA becomes a semantic extension of a `SignedObject`—exactly the same relationship that `ASPA.signed_object` already has today.

## Current State

### Legacy `Roa` (lines 752–821 of models.py)

```
Roa(NamedRpkiStandardModel)
  origin_as          → FK ASN
  valid_from         → DateField
  valid_to           → DateField
  auto_renews        → BooleanField
  signed_by          → FK Certificate (resource certificate)
  signed_object      → OneToOne SignedObject (nullable, related_name='legacy_roa')
```

### Legacy `RoaPrefix` (lines 823–850)

```
RoaPrefix(RpkiStandardModel)
  prefix             → FK ipam.Prefix
  max_length         → IntegerField
  roa_name           → FK Roa (related_name='RoaToPrefixTable')
```

### What `ASPA` already looks like (the target pattern)

```
ASPA(NamedRpkiStandardModel)
  organization       → FK Organization
  signed_object      → OneToOne SignedObject (nullable, related_name='aspa_extension')
  customer_as        → FK ASN
  valid_from         → DateField
  valid_to           → DateField
  validation_state   → CharField

ASPAProvider(RpkiStandardModel)
  aspa               → FK ASPA
  provider_as        → FK ASN
  is_current         → BooleanField
```

### Structural differences between legacy `Roa` and the ASPA pattern

| Concern | `ASPA` (target pattern) | Legacy `Roa` |
|---------|------------------------|--------------|
| Organization link | Explicit `organization` FK | Inferred through `signed_by.rpki_org` |
| Signing certificate | Through `signed_object.resource_certificate` | Direct `signed_by` FK to `Certificate` |
| Validity dates | Own `valid_from`/`valid_to` | Own `valid_from`/`valid_to` |
| Signed-object link | `signed_object` OneToOne (nullable) | `signed_object` OneToOne (nullable) — already present |
| `auto_renews` | Not present (lifecycle managed elsewhere) | Direct field |
| Validation state | Own `validation_state` | Inferred through `signed_object.validation_state` |
| Child-row pattern | `ASPAProvider` FK → `ASPA` | `RoaPrefix` FK → `Roa` |

## Target State

### New `RoaObject` model

A new model that extends `SignedObject` in the same way `ASPA` does.

```
RoaObject(NamedRpkiStandardModel)
  organization       → FK Organization (nullable)
  signed_object      → OneToOne SignedObject (nullable, related_name='roa_extension')
  origin_as          → FK ASN (nullable)
  valid_from         → DateField (nullable)
  valid_to           → DateField (nullable)
  validation_state   → CharField (ValidationState choices)
```

Design notes:

- `signed_by` is gone. The signing certificate is accessed through `signed_object.resource_certificate` when the `SignedObject` link is populated.
- `auto_renews` is dropped entirely.
- `organization` is explicit, matching `ASPA`, `RSC`, and `SignedObject` itself.
- `validation_state` is copied from the ASPA pattern. It may be derived from `signed_object.validation_state` by provider sync or by validation import, but having it on the extension object enables independent querying.

### New `RoaObjectPrefix` model

Replaces `RoaPrefix`. Follows the same child-row pattern as `ASPAProvider`.

```
RoaObjectPrefix(RpkiStandardModel)
  roa_object         → FK RoaObject (related_name='prefix_authorizations')
  prefix             → FK ipam.Prefix (nullable)
  prefix_cidr_text   → CharField (human-readable cidr, for display when ipam.Prefix is absent)
  max_length         → PositiveSmallIntegerField
  is_current         → BooleanField (default True)
```

Design notes:

- `prefix` remains an FK to `ipam.Prefix` for objects that resolve to a known prefix.
- `prefix_cidr_text` mirrors the `ImportedRoaAuthorization` pattern and supports objects with unresolved prefixes.
- `is_current` enables soft tombstoning rather than hard-deleting prefix rows during provider sync.
- The related name `prefix_authorizations` replaces the legacy `RoaToPrefixTable`.

### `SignedObject` related-name change

The new `RoaObject` uses `related_name='roa_extension'`, consistent with `aspa_extension`, `rsc_extension`, `crl_extension`. The old `legacy_roa` reverse relationship is removed along with the `Roa` table.

## Downstream FK References to `Roa` (must migrate)

| Model | Old FK field | New FK field | On-delete |
|-------|-------------|-------------|-----------|
| `ValidatedRoaPayload` | `roa` → `Roa` | `roa_object` → `RoaObject` | PROTECT |
| `ROAIntentMatch` | `roa` → `Roa` | `roa_object` → `RoaObject` | PROTECT |
| `ROAIntentResult` | `best_roa` → `Roa` | `best_roa_object` → `RoaObject` | SET_NULL |
| `PublishedROAResult` | `roa` → `Roa` | `roa_object` → `RoaObject` | PROTECT |
| `ROAChangePlanItem` | `roa` → `Roa` | `roa_object` → `RoaObject` | PROTECT |

Unique constraints on these models that reference the old `roa` column must be replaced with equivalents referencing the new column.

## Service Files That Reference `Roa` or `RoaPrefix` (must update)

| File | Nature of reference |
|------|-------------------|
| `services/routing_intent.py` | Heaviest consumer — queries `RoaPrefix` for intent derivation, writes `roa` FKs on matches/results, builds change plans |
| `services/overlay_reporting.py` | Builds overlay summaries from `result.roa` / `item.roa` |
| `services/overlay_correlation.py` | Type checks `isinstance(obj, Roa)`, builds ROA overlay summaries |
| `services/external_validation.py` | Matches validated payloads to `Roa` objects |
| `services/lifecycle_reporting.py` | Counts `Roa` objects for lifecycle reports |
| `services/roa_lint.py` | Lint rules reference ROA (string labels only, but queries will change) |
| `services/provider_write.py` | ROA change plan validation/apply logic |
| `services/governance_summary.py` | Queries `ROAChangePlan` ecosystem |
| `services/provider_sync_evidence.py` | Detects `.roa` URI suffix |
| `services/provider_sync_krill.py` | Detects `.roa` URI suffix |

## Implementation Slices

All slices ship in a single release. Each slice is a self-contained unit of work that can be handed to an agentic coding assistant. Slices must be executed in order — each depends on the prior slice being complete.

### Slice 1: New models and migration

**Owner**: lead agent (schema window)

**Files changed**:
- `netbox_rpki/models.py` — add `RoaObject` and `RoaObjectPrefix` model classes
- `netbox_rpki/migrations/0029_roa_object_convergence.py` — single migration that:
  1. Creates `RoaObject` and `RoaObjectPrefix` tables
  2. `RunPython` backfill: for each `Roa`, create a `RoaObject` (org from `signed_by.rpki_org`, signed_object, origin_as, dates, validation_state); for each `RoaPrefix`, create a `RoaObjectPrefix`
  3. Adds `roa_object` FK to `ValidatedRoaPayload`, `ROAIntentMatch`, `PublishedROAResult`, `ROAChangePlanItem`; adds `best_roa_object` FK to `ROAIntentResult`
  4. `RunPython` backfill: populate new FK columns from old FK columns via the `Roa` → `RoaObject` mapping
  5. Replaces unique constraints that reference old `roa` columns with equivalents using new columns
  6. Drops old `roa`/`best_roa` FK columns from the five downstream models
  7. Drops `RoaPrefix` table, then drops `Roa` table

**Backfill rules**:
- If `roa.signed_by.rpki_org` is null, set `roa_object.organization` to null
- If `roa.signed_object` is null, set `roa_object.signed_object` to null and `validation_state` to `UNKNOWN`
- If `roa.signed_object` is populated, derive `validation_state` from `signed_object.validation_state`
- `RoaObjectPrefix.prefix_cidr_text` = string representation of the IPAM prefix
- Backfill must be idempotent

**Verification**: `manage.py makemigrations --check --dry-run netbox_rpki` is clean after the migration.

### Slice 2: Test factories and registry scenarios

**Owner**: test window

**Files changed**:
- `netbox_rpki/tests/utils.py` — add `create_test_roa_object()` and `create_test_roa_object_prefix()` factories; remove `create_test_roa()` and `create_test_roa_prefix()`
- `netbox_rpki/tests/registry_scenarios.py` — add `roa_object` and `roa_object_prefix` scenarios; remove `roa` and `roaprefix` scenarios; update any dynamic field factories that referenced the old `roa_name` or `roa` FK fields

**Verification**: factories create valid objects; registry scenarios for the new keys are syntactically complete.

### Slice 3: Object registry and surface layer

**Owner**: surface window

**Files changed**:
- `netbox_rpki/object_registry.py` — add `roa_object` and `roa_object_prefix` specs; remove `roa` and `roaprefix` specs; update any other specs whose `api_fields` / `filter_fields` / `brief_fields` reference the old `roa` or `best_roa` field names (replace with `roa_object` / `best_roa_object`)
- `netbox_rpki/detail_specs.py` — add `RoaObject` detail spec (modeled after `ASPA`'s); add `RoaObjectPrefix` detail spec; remove `Roa` and `RoaPrefix` detail specs; update helper functions (`get_roa_external_overlay_summary`, `get_result_best_roa_prefixes`, `get_result_best_roa_max_lengths`, `get_signed_object_legacy_roa`) to use `RoaObject`/`RoaObjectPrefix`; update any other detail specs that render `obj.roa`, `obj.best_roa`, or `signed_object.legacy_roa` fields
- `netbox_rpki/api/serializers.py` — add `RoaObject` serializer (replace old `RoaSerializer` extension); update `SignedObject` serializer to expose `roa_extension` instead of `legacy_roa`; remove `RoaSerializer` and `RoaPrefixSerializer` custom extensions
- `netbox_rpki/graphql/types.py` — update `SignedObjectSurfaceMixin` to resolve `roa_extension` instead of `legacy_roa`; update `RoaOverlayMixin` to work with `RoaObject`; remove old `Roa.DoesNotExist` catch
- `netbox_rpki/views.py` — update operations dashboard queries from `models.Roa.objects` to `models.RoaObject.objects`; update field access (`roa.signed_by` → traversal through `roa_object.signed_object.resource_certificate`, `roa.origin_as` → `roa_object.origin_as`, `roa.valid_to` → `roa_object.valid_to`)
- `netbox_rpki/navigation.py` — update permission string from `view_roa` to `view_roaobject`; update menu group label if needed
- `netbox_rpki/sample_data.py` — replace `Roa`/`RoaPrefix` seed creation with `RoaObject`/`RoaObjectPrefix`; update deletion order list
- `netbox_rpki/forms.py` — update imports (remove `Roa`, `RoaPrefix`; add `RoaObject`, `RoaObjectPrefix`)
- `netbox_rpki/templates/netbox_rpki/roaprefix.html` — remove (or rename to `roaobjectprefix.html` if custom template is still needed)

**Public surface contract**:
- New URL slugs: `roaobject`, `roaobjectprefix`
- New API basenames: `roaobject`, `roaobjectprefix`
- New GraphQL fields: `netbox_rpki_roa_object`, `netbox_rpki_roa_object_list`, `netbox_rpki_roa_object_prefix`, `netbox_rpki_roa_object_prefix_list`
- Old slugs, basenames, and GraphQL fields (`roa`, `roaprefix`, `netbox_rpki_roa`, `netbox_rpki_roa_list`, `netbox_rpki_roa_prefix`, `netbox_rpki_roa_prefix_list`) are removed

**Verification**: `./dev.sh test contract` passes.

### Slice 4: Service layer switchover

**Owner**: services window (one file at a time, serialized)

**Files changed** (in recommended order):

1. `netbox_rpki/services/routing_intent.py` — replace all `Roa`/`RoaPrefix` queries and FK writes with `RoaObject`/`RoaObjectPrefix`; update dataclass fields (`roa: RoaObject | None`, `roa_prefix: RoaObjectPrefix | None`); update source-key construction; update change-plan item creation
2. `netbox_rpki/services/external_validation.py` — switch `_match_roa()` to query `RoaObject`; update validated-payload creation to write `roa_object=` instead of `roa=`
3. `netbox_rpki/services/overlay_correlation.py` — replace `isinstance(obj, Roa)` with `isinstance(obj, RoaObject)`; update overlay builder function signatures
4. `netbox_rpki/services/overlay_reporting.py` — update overlay summary builders to use `RoaObject`
5. `netbox_rpki/services/roa_lint.py` — update lint rule queries (if any query the model directly)
6. `netbox_rpki/services/lifecycle_reporting.py` — replace `Roa.objects.filter(...)` with `RoaObject.objects.filter(...)`
7. `netbox_rpki/services/governance_summary.py` — update summary queries
8. `netbox_rpki/services/provider_write.py` — update change-plan validation/apply to reference `RoaObject`
9. `netbox_rpki/services/provider_sync_krill.py` — no model change needed (`.roa` URI suffix detection stays as-is since it refers to the file extension, not the model)
10. `netbox_rpki/services/provider_sync_evidence.py` — same as above

**Verification**: `./dev.sh test full` passes.

### Slice 5: Test suite update

**Owner**: test window

**Files changed**:
- `netbox_rpki/tests/test_models.py` — replace `Roa`/`RoaPrefix` model tests with `RoaObject`/`RoaObjectPrefix` tests; update `signed_object` link and validation tests
- `netbox_rpki/tests/test_views.py` — replace all `Roa`/`RoaPrefix` view test fixtures and assertions with `RoaObject`/`RoaObjectPrefix`; update operations dashboard tests
- `netbox_rpki/tests/test_api.py` — replace `roa`/`roaprefix` API test scenarios with `roa_object`/`roa_object_prefix`; update scenario dicts and test classes
- `netbox_rpki/tests/test_graphql.py` — replace `RoaPrefix` GraphQL test with `RoaObjectPrefix`
- `netbox_rpki/tests/test_routing_intent_services.py` — replace `create_test_roa`/`create_test_roa_prefix` calls with new factories
- `netbox_rpki/tests/test_overlay_correlation.py` — replace `Roa`/`RoaPrefix` fixtures with `RoaObject`/`RoaObjectPrefix`
- `netbox_rpki/tests/test_external_validation.py` — replace `Roa`/`RoaPrefix` fixtures with `RoaObject`/`RoaObjectPrefix`

**Verification**: `./dev.sh test full` passes with zero references to the old `Roa`/`RoaPrefix` models in test code.

### Slice 6: E2E tests and cleanup

**Owner**: test window

**Files changed**:
- `tests/e2e/scripts/prepare_netbox_rpki_e2e.py` — replace `Roa`/`RoaPrefix` imports and cleanup with `RoaObject`/`RoaObjectPrefix`
- `tests/e2e/helpers/netbox-rpki.js` — replace path constants, `createRoaFromCertificate()` → `createRoaObject()`, `createRoaPrefixFromRoa()` → `createRoaObjectPrefix()`
- `tests/e2e/netbox-rpki/roas.spec.js` — update ROA CRUD E2E test for new URLs and form fields
- `tests/e2e/netbox-rpki/relations.spec.js` — update ROA prefix E2E test

**Verification**: `./dev.sh e2e` passes.

## Backfill Rules

- If `roa.signed_by.rpki_org` is null, `roa_object.organization` is set to null
- If `roa.signed_object` is null, `roa_object.signed_object` is null and `validation_state` is `UNKNOWN`
- If `roa.signed_object` is populated, `validation_state` is copied from `signed_object.validation_state`
- `RoaObjectPrefix.prefix_cidr_text` = string representation of the IPAM prefix
- Downstream FK backfill maps old `roa_id` → new `roa_object_id` through the `Roa` → `RoaObject` name-match mapping
- Best-effort: migration must not fail if legacy data is incomplete

## File Ownership

Only one worker touches a given file group at a time:

| Window | Files |
|--------|-------|
| Schema | `models.py`, `migrations/` |
| Surface | `object_registry.py`, `detail_specs.py`, `api/serializers.py`, `graphql/types.py`, `forms.py`, `filtersets.py`, `tables.py`, `views.py`, `navigation.py`, `sample_data.py` |
| Services | `services/routing_intent.py`, `services/overlay_*.py`, `services/external_validation.py`, `services/roa_lint.py`, `services/lifecycle_reporting.py`, `services/governance_summary.py`, `services/provider_write.py` |
| Tests | `tests/utils.py`, `tests/registry_scenarios.py`, `tests/test_*.py`, `tests/e2e/` |

## Resolved Questions

1. **Final model name**: `RoaObject` / `RoaObjectPrefix`. No rename planned.
2. **`auto_renews` disposition**: Dropped entirely. Not carried forward.
3. **Release strategy**: All slices ship in a single release.
4. **URL slugs**: New permanent slugs `roaobject` / `roaobjectprefix`. Old slugs removed.
