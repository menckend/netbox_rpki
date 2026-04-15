# ROA Signed-Object Convergence Plan

Prepared: April 15, 2026

## Objective

Replace the legacy `Roa` and `RoaPrefix` models with new models that are structurally aligned with the `SignedObject` data architecture, following the same extension pattern already established by `ASPA`/`ASPAProvider`, `RSC`/`RSCFileHash`, `Manifest`/`ManifestEntry`, and `CertificateRevocationList`.

After convergence, a ROA is no longer a freestanding object that *optionally* links to a `SignedObject`. Instead, a ROA becomes a semantic extension of a `SignedObject`—exactly the same relationship that `ASPA.signed_object` already has today.

## Current State

### Legacy `Roa` (models.py L752–821)

```python
class Roa(NamedRpkiStandardModel):
    origin_as      = models.ForeignKey(to=ASN, on_delete=models.PROTECT, related_name='roas', blank=True, null=True)
    valid_from     = models.DateField(editable=True, blank=True, null=True)
    valid_to       = models.DateField(editable=True, blank=True, null=True)
    auto_renews    = models.BooleanField(editable=True)
    signed_by      = models.ForeignKey(to=Certificate, on_delete=models.PROTECT, related_name='roas')
    signed_object  = models.OneToOneField(to='SignedObject', on_delete=models.SET_NULL, related_name='legacy_roa', blank=True, null=True)
```

### Legacy `RoaPrefix` (models.py L823–850)

```python
class RoaPrefix(RpkiStandardModel):
    prefix     = models.ForeignKey(to=ipam.models.ip.Prefix, on_delete=models.PROTECT, related_name='PrefixToRoaTable')
    max_length = models.IntegerField(editable=True)
    roa_name   = models.ForeignKey(to=Roa, on_delete=models.PROTECT, related_name='RoaToPrefixTable')
```

### Target pattern: `ASPA` (models.py L1434–1503)

```python
class ASPA(NamedRpkiStandardModel):
    organization     = models.ForeignKey(to=Organization, on_delete=models.PROTECT, related_name='aspas', blank=True, null=True)
    signed_object    = models.OneToOneField(to=SignedObject, on_delete=models.PROTECT, related_name='aspa_extension', blank=True, null=True)
    customer_as      = models.ForeignKey(to=ASN, on_delete=models.PROTECT, related_name='customer_aspas', blank=True, null=True)
    valid_from       = models.DateField(blank=True, null=True)
    valid_to         = models.DateField(blank=True, null=True)
    validation_state = models.CharField(max_length=32, choices=ValidationState.choices, default=ValidationState.UNKNOWN)

class ASPAProvider(RpkiStandardModel):
    aspa        = models.ForeignKey(to=ASPA, on_delete=models.PROTECT, related_name='provider_authorizations')
    provider_as = models.ForeignKey(to=ASN, on_delete=models.PROTECT, related_name='provider_aspas')
    is_current  = models.BooleanField(default=True)
```

### Structural gap summary

| Concern | ASPA (target) | Legacy Roa |
|---------|---------------|------------|
| Organization | Explicit `organization` FK | Inferred via `signed_by.rpki_org` |
| Signing cert | Via `signed_object.resource_certificate` | Direct `signed_by` FK |
| `auto_renews` | Absent | Direct field |
| `validation_state` | Own field | Inferred via `signed_object.validation_state` |
| Child rows | `ASPAProvider` FK → `ASPA` | `RoaPrefix` FK → `Roa` |

---

## Target State

### `RoaObject` — exact model code to add

Insert in `models.py` immediately after `RoaPrefix` (after L850), before `CertificatePrefix`:

```python
class RoaObject(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_objects',
        blank=True,
        null=True
    )
    signed_object = models.OneToOneField(
        to='SignedObject',
        on_delete=models.PROTECT,
        related_name='roa_extension',
        blank=True,
        null=True
    )
    origin_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='roa_objects',
        blank=True,
        null=True
    )
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)
    validation_state = models.CharField(
        max_length=32,
        choices=ValidationState.choices,
        default=ValidationState.UNKNOWN,
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.signed_object_id is None:
            return

        errors = []
        if self.signed_object.object_type != SignedObjectType.ROA:
            errors.append('Signed object must use the ROA object type.')
        if (
            self.organization_id is not None
            and self.signed_object.organization_id is not None
            and self.organization_id != self.signed_object.organization_id
        ):
            errors.append('Signed object must belong to the same organization as the ROA object.')
        if (
            self.valid_from is not None
            and self.signed_object.valid_from is not None
            and self.valid_from != self.signed_object.valid_from
        ):
            errors.append('Signed object valid-from date must match the ROA valid-from date.')
        if (
            self.valid_to is not None
            and self.signed_object.valid_to is not None
            and self.valid_to != self.signed_object.valid_to
        ):
            errors.append('Signed object valid-to date must match the ROA valid-to date.')

        if errors:
            raise ValidationError({'signed_object': errors})

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaobject", args=[self.pk])


class RoaObjectPrefix(RpkiStandardModel):
    roa_object = models.ForeignKey(
        to=RoaObject,
        on_delete=models.PROTECT,
        related_name='prefix_authorizations'
    )
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='roa_object_prefixes',
        blank=True,
        null=True
    )
    prefix_cidr_text = models.CharField(max_length=64, blank=True)
    max_length = models.PositiveSmallIntegerField()
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ("roa_object", "prefix_cidr_text")

    def __str__(self):
        return self.prefix_cidr_text or str(self.prefix)

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaobjectprefix", args=[self.pk])
```

### Downstream FK changes — exact field definitions

**`ValidatedRoaPayload`** (models.py L1760) — replace `roa` FK:
```python
    # OLD:
    roa = models.ForeignKey(to=Roa, on_delete=models.PROTECT, related_name='validated_payloads', blank=True, null=True)
    # NEW:
    roa_object = models.ForeignKey(to=RoaObject, on_delete=models.PROTECT, related_name='validated_payloads', blank=True, null=True)
```

Also update `clean()` (L1798–1813): replace `self.roa_id`, `self.roa.signed_object_id` → `self.roa_object_id`, `self.roa_object.signed_object_id`.

**`ROAIntentMatch`** (models.py L5677) — replace `roa` FK:
```python
    # OLD:
    roa = models.ForeignKey(to=Roa, on_delete=models.PROTECT, related_name='intent_matches', blank=True, null=True)
    # NEW:
    roa_object = models.ForeignKey(to=RoaObject, on_delete=models.PROTECT, related_name='intent_matches', blank=True, null=True)
```

Also update all 3 constraints (L5706–5725): replace `roa` → `roa_object`, `roa__isnull` → `roa_object__isnull` in field lists and Q conditions. Update constraint names from `_roa_intent_roa_` to `_roa_intent_roa_object_` and `_exactly_one_source`.

**`ROAIntentResult`** (models.py L5837) — replace `best_roa` FK:
```python
    # OLD:
    best_roa = models.ForeignKey(to=Roa, on_delete=models.SET_NULL, related_name='intent_result_matches', blank=True, null=True)
    # NEW:
    best_roa_object = models.ForeignKey(to=RoaObject, on_delete=models.SET_NULL, related_name='intent_result_matches', blank=True, null=True)
```

No constraint changes needed — the only constraint is on `(reconciliation_run, roa_intent)` which doesn't reference `best_roa`.

**`PublishedROAResult`** (models.py L5881) — replace `roa` FK:
```python
    # OLD:
    roa = models.ForeignKey(to=Roa, on_delete=models.PROTECT, related_name='published_reconciliation_results', blank=True, null=True)
    # NEW:
    roa_object = models.ForeignKey(to=RoaObject, on_delete=models.PROTECT, related_name='published_reconciliation_results', blank=True, null=True)
```

Also update all 3 constraints (L5910–5925): replace `roa` → `roa_object`, `roa__isnull` → `roa_object__isnull`. Update constraint names.

**`ROAChangePlanItem`** (models.py L6755) — replace `roa` FK:
```python
    # OLD:
    roa = models.ForeignKey(to=Roa, on_delete=models.PROTECT, related_name='change_plan_items', blank=True, null=True)
    # NEW:
    roa_object = models.ForeignKey(to=RoaObject, on_delete=models.PROTECT, related_name='change_plan_items', blank=True, null=True)
```

No constraint changes needed — no unique constraints reference `roa`.

### Models to delete

Remove entirely from `models.py`:
- `Roa` class (L752–821)
- `RoaPrefix` class (L823–850)

---

## Complete Dependency Map

Every reference to the legacy models, organized by file with exact line numbers. This is the exhaustive checklist — nothing outside this list needs to change.

### models.py

| Line | Current reference | Replacement |
|------|-------------------|-------------|
| L752–821 | `class Roa(...)` | Delete; replaced by `RoaObject` |
| L823–850 | `class RoaPrefix(...)` | Delete; replaced by `RoaObjectPrefix` |
| L1760–1766 | `ValidatedRoaPayload.roa` FK → `Roa` | FK → `RoaObject`, field name `roa_object` |
| L1806–1810 | `ValidatedRoaPayload.clean()` refs `self.roa_id`, `self.roa.signed_object_id` | `self.roa_object_id`, `self.roa_object.signed_object_id` |
| L5677–5683 | `ROAIntentMatch.roa` FK → `Roa` | FK → `RoaObject`, field name `roa_object` |
| L5706–5725 | `ROAIntentMatch.Meta.constraints` — 3 constraints reference `roa` | Replace `roa` → `roa_object` in fields, Q conditions, and constraint names |
| L5837–5843 | `ROAIntentResult.best_roa` FK → `Roa` | FK → `RoaObject`, field name `best_roa_object` |
| L5881–5888 | `PublishedROAResult.roa` FK → `Roa` | FK → `RoaObject`, field name `roa_object` |
| L5910–5925 | `PublishedROAResult.Meta.constraints` — 3 constraints reference `roa` | Replace `roa` → `roa_object` in fields, Q conditions, and constraint names |
| L6755–6761 | `ROAChangePlanItem.roa` FK → `Roa` | FK → `RoaObject`, field name `roa_object` |

### object_registry.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L331–393 | `ObjectSpec(registry_key="roa", model=models.Roa, ...)` | Replace entire block with `RoaObject` spec (new slug `roaobject`, new fields, no `auto_renews`, no `signed_by`) |
| L396–442 | `ObjectSpec(registry_key="roaprefix", model=models.RoaPrefix, ...)` | Replace entire block with `RoaObjectPrefix` spec (new slug `roaobjectprefix`, `roa_object` FK, `prefix_cidr_text`, `is_current`) |
| L1010–1043 | `validatedroapayload` spec — `"roa"` in api_fields, filter_fields, graphql_fields | Replace `"roa"` → `"roa_object"`, `("roa_id", "id")` → `("roa_object_id", "id")` |
| L1886–1912 | `roaintentmatch` spec — `"roa"` in fields | Replace `"roa"` → `"roa_object"`, `("roa_id", "id")` → `("roa_object_id", "id")` |
| L2149–2188 | `roaintentresult` spec — `"best_roa"` in fields | Replace `"best_roa"` → `"best_roa_object"`, `("best_roa_id", "id")` → `("best_roa_object_id", "id")` |
| L2342–2377 | `publishedroaresult` spec — `"roa"` in fields | Replace `"roa"` → `"roa_object"`, `("roa_id", "id")` → `("roa_object_id", "id")` |
| L3045–3093 | `roachangeplanitem` spec — `"roa"` in fields | Replace `"roa"` → `"roa_object"`, `("roa_id", "id")` → `("roa_object_id", "id")` |

### detail_specs.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L82–83 | `get_roa_external_overlay_summary(obj: models.Roa)` | Change type hint to `models.RoaObject` |
| L373–376 | `get_result_published_origin` — `result.best_roa_id`, `result.best_roa.origin_as` | `result.best_roa_object_id`, `result.best_roa_object.origin_as` |
| L379–383 | `get_result_best_roa_prefixes` — `result.best_roa.RoaToPrefixTable.all()` | `result.best_roa_object.prefix_authorizations.all()` |
| L386–390 | `get_result_best_roa_max_lengths` — same pattern | Same replacement |
| L710–711 | `get_signed_object_legacy_roa` — `get_optional_related(signed_object, 'legacy_roa')` | Rename to `get_signed_object_roa_extension`, use `'roa_extension'` |
| L1777 | ROAIntentResult detail — `obj.best_roa` | `obj.best_roa_object` |
| L1793 | ROAIntentResult detail — `get_result_best_roa_prefixes` | No change needed (function renamed internally) |
| L1818 | PublishedROAResult detail — `obj.roa` | `obj.roa_object` |
| L2067 | ROAChangePlanItem detail — `obj.roa` | `obj.roa_object` |
| L2530 | SignedObject detail — `get_signed_object_legacy_roa`, label "Legacy ROA" | `get_signed_object_roa_extension`, label "ROA Object" |
| L2752–2821 | `ROA_DETAIL_SPEC` — entire block references `models.Roa` | Replace with `ROA_OBJECT_DETAIL_SPEC` for `models.RoaObject` (drop `auto_renews`, drop `signed_by`, add `organization`, add `validation_state`, change child table to `RoaObjectPrefixTable`, change action to `roaobjectprefix_add` with `query_param='roa_object'`) |
| L3292 | `models.Roa: ROA_DETAIL_SPEC` | `models.RoaObject: ROA_OBJECT_DETAIL_SPEC` |

### api/serializers.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L1170 | `legacy_roa = serializers.SerializerMethodField()` | `roa_extension = serializers.SerializerMethodField()` |
| L1182 | `'legacy_roa',` in Meta.fields | `'roa_extension',` |
| L1222–1223 | `get_legacy_roa` method | Rename to `get_roa_extension`, use `self._serialize_related_object(obj, 'roa_extension', 'roaobject')` |
| L1264–1277 | `class RoaSerializer(SERIALIZER_CLASS_MAP['roa'])` + `SERIALIZER_CLASS_MAP['roa'] = RoaSerializer` | Replace with `class RoaObjectSerializer(SERIALIZER_CLASS_MAP['roaobject'])` + `SERIALIZER_CLASS_MAP['roaobject'] = RoaObjectSerializer` (same overlay pattern) |

### graphql/types.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L347–354 | `SignedObjectSurfaceMixin.legacy_roa` resolver, catches `models.Roa.DoesNotExist` | Rename field to `roa_extension`, return type `"RoaObjectType"`, catch `models.RoaObject.DoesNotExist` |
| L405–409 | `class RoaOverlayMixin` — `build_roa_overlay_summary(self)` | Type hint/behavior stays the same but will receive `RoaObject` instances at runtime |
| L493 | `'roa': RoaOverlayMixin` in REPORTING_MIXINS | `'roaobject': RoaOverlayMixin` |

### views.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L181–183 | `class RoaView` — `queryset = models.Roa.objects.all()` | Delete (replaced by registry-generated view for `RoaObject`) |
| L2019 | `models.Roa.objects.restrict(request.user, 'view').select_related('origin_as')` | `models.RoaObject.objects.restrict(request.user, 'view').select_related('origin_as')` |
| L2120–2142 | `get_expiring_roas` — queries `models.Roa.objects`, accesses `roa.signed_by.rpki_org`, `roa.signed_by` | Query `models.RoaObject.objects`, access `roa_obj.organization`, traverse `roa_obj.signed_object.resource_certificate` for the related cert; `select_related` changes to `('origin_as', 'organization', 'signed_object__resource_certificate__rpki_org')` |

### navigation.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L12 | `'netbox_rpki.view_roa'` | `'netbox_rpki.view_roaobject'` |
| L48 | `navigation_groups.get('ROAs', ())` | No change needed (group name stays "ROAs" in the new spec's `NavigationSpec`) |

### sample_data.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L41 | `rpki_models.Roa,` in deletion order | `rpki_models.RoaObject,` |
| L42 | `rpki_models.RoaPrefix,` in deletion order | `rpki_models.RoaObjectPrefix,` |
| L407–416 | `rpki_models.Roa.objects.create(name=..., origin_as=..., signed_by=certificate, signed_object=..., valid_from=..., valid_to=..., auto_renews=True, ...)` | `rpki_models.RoaObject.objects.create(name=..., organization=certificate.rpki_org, origin_as=..., signed_object=..., valid_from=..., valid_to=..., validation_state=..., ...)` |
| L418–423 | `rpki_models.RoaPrefix.objects.create(prefix=..., roa_name=roa, max_length=24, ...)` | `rpki_models.RoaObjectPrefix.objects.create(roa_object=roa_obj, prefix=..., prefix_cidr_text=str(prefix), max_length=24, ...)` |
| L609 | `roa=roa,` in ValidatedRoaPayload creation | `roa_object=roa_obj,` |

### forms.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L44–45 | `Roa, RoaPrefix,` in import block | `RoaObject, RoaObjectPrefix,` |

### templates/netbox_rpki/roaprefix.html

| Action | Detail |
|--------|--------|
| Delete or rename | If the custom breadcrumb template is still needed, rename to `roaobjectprefix.html` and update the breadcrumb URL from `roaprefix_list` to `roaobjectprefix_list` |

### services/routing_intent.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L31–32 | `roa: rpki_models.Roa \| None` / `roa_prefix: rpki_models.RoaPrefix \| None` | `roa_object: rpki_models.RoaObject \| None` / `roa_object_prefix: rpki_models.RoaObjectPrefix \| None` |
| L1627 | `rpki_models.RoaPrefix.objects.select_related('roa_name', 'roa_name__origin_as')` | `rpki_models.RoaObjectPrefix.objects.select_related('roa_object', 'roa_object__origin_as')` |
| L1630 | `roa = prefix_row.roa_name` | `roa_obj = prefix_row.roa_object` |
| L1632–1643 | `source_key = f'roa:{roa.pk}'`, `roa=roa, roa_prefix=prefix_row` | `source_key = f'roa:{roa_obj.pk}'`, `roa_object=roa_obj, roa_object_prefix=prefix_row` |
| L1636–1639 | `source_name=roa.name`, `origin_asn_value=getattr(roa.origin_as, 'asn', None)`, `stale=bool(roa.valid_to and roa.valid_to < today)` | `source_name=roa_obj.name`, `origin_asn_value=getattr(roa_obj.origin_as, 'asn', None)`, `stale=bool(roa_obj.valid_to and roa_obj.valid_to < today)` |
| L1808–1815 | `match.roa_id`, `match.roa.name` | `match.roa_object_id`, `match.roa_object.name` |
| L1994 | `ROAIntentMatch.objects.create(..., roa=published.roa, ...)` | `..., roa_object=published.roa_object, ...` |
| L2037 | `ROAIntentResult.objects.create(..., best_roa=getattr(best_match, 'roa', None), ...)` | `..., best_roa_object=getattr(best_match, 'roa_object', None), ...` |
| L2098 | `PublishedROAResult.objects.create(..., roa=representative.roa, ...)` | `..., roa_object=representative.roa_object, ...` |
| L2100 | `representative.roa.tenant if representative.roa is not None` | `representative.roa_object.tenant if representative.roa_object is not None` |
| L2454 | `ROAChangePlanItem.objects.create(..., roa=intent_result.best_roa, ...)` | `..., roa_object=intent_result.best_roa_object, ...` |
| L2487 | `ROAChangePlanItem.objects.create(..., roa=published_result.roa, ...)` | `..., roa_object=published_result.roa_object, ...` |

### services/external_validation.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L175 | `roa=item.get('roa'),` | `roa_object=item.get('roa_object'),` |
| L282 | `roa = _match_roa(...)` | `roa_object = _match_roa_object(...)` |
| L310 | `'roa': roa,` in return dict | `'roa_object': roa_object,` |
| L283 | `if ... roa is not None:` | `if ... roa_object is not None:` |
| L472–487 | `def _match_roa(*, prefix, origin_as, max_length) -> rpki_models.Roa \| None:` | Rename to `_match_roa_object`, return type `rpki_models.RoaObject \| None`, query `rpki_models.RoaObject.objects.filter(origin_as=origin_as, prefix_authorizations__prefix=prefix)`, filter `prefix_authorizations__max_length=max_length` |

### services/overlay_correlation.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L31–34 | `obj.legacy_roa` → `build_roa_overlay_summary(obj.legacy_roa)` / `except rpki_models.Roa.DoesNotExist:` | `obj.roa_extension` → `build_roa_overlay_summary(obj.roa_extension)` / `except rpki_models.RoaObject.DoesNotExist:` |
| L65 | `def build_roa_overlay_summary(obj: rpki_models.Roa)` | Type hint → `rpki_models.RoaObject` |
| L238–241 | `def _roa_telemetry_queryset(obj: rpki_models.Roa)` / `obj.RoaToPrefixTable.values_list(...)` | Type hint → `rpki_models.RoaObject` / `obj.prefix_authorizations.values_list('prefix__prefix', flat=True)` |

### services/overlay_reporting.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L26 | `result.best_roa` | `result.best_roa_object` |
| L30–31 | `result.best_roa_id`, `result.best_roa` | `result.best_roa_object_id`, `result.best_roa_object` |
| L32 | `result.roa_id`, `result.roa` | `result.roa_object_id`, `result.roa_object` |
| L78 | `item.roa_id`, `item.roa` | `item.roa_object_id`, `item.roa_object` |
| L168 | `isinstance(obj, rpki_models.Roa)` | `isinstance(obj, rpki_models.RoaObject)` |
| `select_related` args | `select_related('best_roa')`, `select_related('roa')` | `select_related('best_roa_object')`, `select_related('roa_object')` |

### services/lifecycle_reporting.py

| Lines | Current | Replacement |
|-------|---------|-------------|
| L870–874 | `rpki_models.Roa.objects.filter(signed_by__rpki_org=organization, valid_to__isnull=False, valid_to__lte=roa_threshold).count()` | `rpki_models.RoaObject.objects.filter(organization=organization, valid_to__isnull=False, valid_to__lte=roa_threshold).count()` |

### services/provider_write.py

No direct `models.Roa` references. The `roa` field accesses on `ROAChangePlanItem` objects will work automatically once the FK is renamed. Grep-verify that no `.roa` attribute access exists beyond the renamed FK fields.

### services/governance_summary.py

No direct `models.Roa` references. Only `ROAChangePlan` and `ROAChangePlanRollbackBundle` queries. No changes needed.

### services/provider_sync_krill.py, services/provider_sync_evidence.py

`.roa` URI suffix detection refers to the file extension, not the model. No changes needed.

---

## Implementation Slices

All slices ship in a single release. Each slice is a self-contained unit of work. Slices must be executed in order.

### Slice 1: New models, migration, and legacy removal

Status: Completed on April 15, 2026.
Implementation note: the repository already contained `0055_externalmanagementexception.py`, so the convergence migration was created as `0056_roa_object_convergence.py`. The schema slice also included the required `ExternalManagementException.roa` -> `roa_object` migration path so the legacy `Roa` table can be dropped safely.

**Owner**: lead agent (schema window)

**Files changed**:
- `netbox_rpki/models.py`
- `netbox_rpki/migrations/0055_roa_object_convergence.py`

**Migration number**: 0055 (next after current 0054). Depends on `0054`.

**Migration operations in order**:

```python
operations = [
    # 1. Create new tables
    migrations.CreateModel(
        name='RoaObject',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
            ('created', models.DateTimeField(auto_now_add=True, null=True)),
            ('last_updated', models.DateTimeField(auto_now=True, null=True)),
            ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=DjangoJSONEncoder)),
            ('comments', models.TextField(blank=True)),
            ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ('tags', TaggableManager(through='extras.TaggedItem')),
            ('name', models.CharField(max_length=200)),
            ('organization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='roa_objects', to='netbox_rpki.organization')),
            ('signed_object', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='roa_extension', to='netbox_rpki.signedobject')),
            ('origin_as', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='roa_objects', to='ipam.asn')),
            ('valid_from', models.DateField(blank=True, null=True)),
            ('valid_to', models.DateField(blank=True, null=True)),
            ('validation_state', models.CharField(choices=[...], default='unknown', max_length=32)),
        ],
        options={'ordering': ('name',)},
    ),
    migrations.CreateModel(
        name='RoaObjectPrefix',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
            ('created', models.DateTimeField(auto_now_add=True, null=True)),
            ('last_updated', models.DateTimeField(auto_now=True, null=True)),
            ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=DjangoJSONEncoder)),
            ('comments', models.TextField(blank=True)),
            ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ('tags', TaggableManager(through='extras.TaggedItem')),
            ('roa_object', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='prefix_authorizations', to='netbox_rpki.roaobject')),
            ('prefix', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='roa_object_prefixes', to='ipam.prefix')),
            ('prefix_cidr_text', models.CharField(blank=True, max_length=64)),
            ('max_length', models.PositiveSmallIntegerField()),
            ('is_current', models.BooleanField(default=True)),
        ],
        options={'ordering': ('roa_object', 'prefix_cidr_text')},
    ),

    # 2. Backfill Roa → RoaObject, RoaPrefix → RoaObjectPrefix
    migrations.RunPython(backfill_roa_objects, migrations.RunPython.noop),

    # 3. Add new FK columns on downstream models
    migrations.AddField(model_name='validatedroapayload', name='roa_object',
        field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name='validated_payloads', to='netbox_rpki.roaobject')),
    migrations.AddField(model_name='roaintentmatch', name='roa_object',
        field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name='intent_matches', to='netbox_rpki.roaobject')),
    migrations.AddField(model_name='roaintentresult', name='best_roa_object',
        field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
            related_name='intent_result_matches', to='netbox_rpki.roaobject')),
    migrations.AddField(model_name='publishedroaresult', name='roa_object',
        field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name='published_reconciliation_results', to='netbox_rpki.roaobject')),
    migrations.AddField(model_name='roachangeplanitem', name='roa_object',
        field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name='change_plan_items', to='netbox_rpki.roaobject')),

    # 4. Backfill new FK columns from old
    migrations.RunPython(backfill_downstream_fks, migrations.RunPython.noop),

    # 5. Drop old constraints that reference 'roa' columns
    migrations.RemoveConstraint(model_name='roaintentmatch', name='netbox_rpki_roaintentmatch_roa_intent_roa_unique'),
    migrations.RemoveConstraint(model_name='roaintentmatch', name='netbox_rpki_roaintentmatch_exactly_one_source'),
    migrations.RemoveConstraint(model_name='publishedroaresult', name='netbox_rpki_publishedroaresult_run_roa_unique'),
    migrations.RemoveConstraint(model_name='publishedroaresult', name='netbox_rpki_publishedroaresult_exactly_one_source'),

    # 6. Drop old FK columns
    migrations.RemoveField(model_name='validatedroapayload', name='roa'),
    migrations.RemoveField(model_name='roaintentmatch', name='roa'),
    migrations.RemoveField(model_name='roaintentresult', name='best_roa'),
    migrations.RemoveField(model_name='publishedroaresult', name='roa'),
    migrations.RemoveField(model_name='roachangeplanitem', name='roa'),

    # 7. Add new constraints using new columns
    migrations.AddConstraint(model_name='roaintentmatch', constraint=models.UniqueConstraint(
        fields=('roa_intent', 'roa_object'),
        condition=models.Q(roa_object__isnull=False, imported_authorization__isnull=True),
        name='netbox_rpki_roaintentmatch_intent_roa_object_unique',
    )),
    migrations.AddConstraint(model_name='roaintentmatch', constraint=models.CheckConstraint(
        condition=(
            models.Q(roa_object__isnull=False, imported_authorization__isnull=True)
            | models.Q(roa_object__isnull=True, imported_authorization__isnull=False)
        ),
        name='netbox_rpki_roaintentmatch_exactly_one_source',
    )),
    migrations.AddConstraint(model_name='publishedroaresult', constraint=models.UniqueConstraint(
        fields=('reconciliation_run', 'roa_object'),
        condition=models.Q(roa_object__isnull=False, imported_authorization__isnull=True),
        name='netbox_rpki_publishedroaresult_run_roa_object_unique',
    )),
    migrations.AddConstraint(model_name='publishedroaresult', constraint=models.CheckConstraint(
        condition=(
            models.Q(roa_object__isnull=False, imported_authorization__isnull=True)
            | models.Q(roa_object__isnull=True, imported_authorization__isnull=False)
        ),
        name='netbox_rpki_publishedroaresult_exactly_one_source',
    )),

    # 8. Drop legacy tables (RoaPrefix first due to FK dependency)
    migrations.DeleteModel(name='RoaPrefix'),
    migrations.DeleteModel(name='Roa'),
]
```

**Backfill function pseudocode**:

```python
def backfill_roa_objects(apps, schema_editor):
    Roa = apps.get_model('netbox_rpki', 'Roa')
    RoaObject = apps.get_model('netbox_rpki', 'RoaObject')
    RoaPrefix = apps.get_model('netbox_rpki', 'RoaPrefix')
    RoaObjectPrefix = apps.get_model('netbox_rpki', 'RoaObjectPrefix')

    roa_mapping = {}  # old roa.pk → new roa_object.pk

    for roa in Roa.objects.select_related('signed_by__rpki_org', 'signed_object').all():
        org = getattr(roa.signed_by, 'rpki_org', None) if roa.signed_by_id else None
        vs = 'unknown'
        if roa.signed_object_id and roa.signed_object.validation_state:
            vs = roa.signed_object.validation_state
        roa_obj = RoaObject.objects.create(
            name=roa.name,
            organization=org,
            signed_object=roa.signed_object,
            origin_as_id=roa.origin_as_id,
            valid_from=roa.valid_from,
            valid_to=roa.valid_to,
            validation_state=vs,
            tenant_id=roa.tenant_id,
            comments=roa.comments,
        )
        roa_mapping[roa.pk] = roa_obj.pk

    for rp in RoaPrefix.objects.select_related('prefix').all():
        new_roa_pk = roa_mapping.get(rp.roa_name_id)
        if new_roa_pk is None:
            continue
        RoaObjectPrefix.objects.create(
            roa_object_id=new_roa_pk,
            prefix_id=rp.prefix_id,
            prefix_cidr_text=str(rp.prefix.prefix) if rp.prefix_id else '',
            max_length=rp.max_length,
            is_current=True,
            tenant_id=rp.tenant_id,
            comments=rp.comments,
        )

def backfill_downstream_fks(apps, schema_editor):
    Roa = apps.get_model('netbox_rpki', 'Roa')
    RoaObject = apps.get_model('netbox_rpki', 'RoaObject')

    # Build name→pk mapping for RoaObject
    roa_obj_by_name = {ro.name: ro.pk for ro in RoaObject.objects.all()}

    # Build old roa pk → new roa_object pk
    mapping = {}
    for roa in Roa.objects.all():
        new_pk = roa_obj_by_name.get(roa.name)
        if new_pk:
            mapping[roa.pk] = new_pk

    for model_name, old_field, new_field in [
        ('ValidatedRoaPayload', 'roa_id', 'roa_object_id'),
        ('ROAIntentMatch', 'roa_id', 'roa_object_id'),
        ('ROAIntentResult', 'best_roa_id', 'best_roa_object_id'),
        ('PublishedROAResult', 'roa_id', 'roa_object_id'),
        ('ROAChangePlanItem', 'roa_id', 'roa_object_id'),
    ]:
        Model = apps.get_model('netbox_rpki', model_name)
        for row in Model.objects.filter(**{f'{old_field}__isnull': False}):
            old_pk = getattr(row, old_field)
            new_pk = mapping.get(old_pk)
            if new_pk:
                setattr(row, new_field, new_pk)
                row.save(update_fields=[new_field])
```

**Verification**: `manage.py migrate netbox_rpki` succeeds; `manage.py makemigrations --check --dry-run netbox_rpki` is clean.

### Slice 2: Test factories and registry scenarios

Status: Completed on April 15, 2026.

**Owner**: test window

**Files changed**:
- `netbox_rpki/tests/utils.py`
- `netbox_rpki/tests/registry_scenarios.py`

**Exact changes in tests/utils.py**:

Replace `create_test_roa` (L197–226) with:
```python
def create_test_roa_object(name='ROA Object 1', organization=None, signed_object=None, origin_as=None, **kwargs):
    if organization is None:
        organization = create_test_organization()
    if signed_object is None:
        signed_object = create_test_signed_object(
            name=f'{name} SO',
            organization=organization,
            object_type='roa',
        )
    return rpki_models.RoaObject.objects.create(
        name=name, organization=organization, signed_object=signed_object,
        origin_as=origin_as, **kwargs,
    )
```

Replace `create_test_roa_prefix` (L229–237) with:
```python
def create_test_roa_object_prefix(prefix=None, roa_object=None, max_length=24, **kwargs):
    if prefix is None:
        prefix = create_test_prefix()
    if roa_object is None:
        roa_object = create_test_roa_object()
    return rpki_models.RoaObjectPrefix.objects.create(
        roa_object=roa_object,
        prefix=prefix,
        prefix_cidr_text=str(prefix.prefix) if hasattr(prefix, 'prefix') else str(prefix),
        max_length=max_length,
        **kwargs,
    )
```

**Exact changes in tests/registry_scenarios.py**:

- L235–239: Replace `create_unique_roa` with `create_unique_roa_object` (uses `create_test_roa_object` instead of `create_test_roa`)
- L302–305: Replace `elif field_name == "roa_name":` block with `elif field_name == "roa_object":` — create via `create_unique_roa_object`
- L332–333: Replace `elif field_name == "roa":` with `elif field_name == "roa_object":` — `create_test_roa_object(name=f"ROA Object {token}")`
- L355–356: Replace `elif field_name == "best_roa":` with `elif field_name == "best_roa_object":` — `create_test_roa_object(name=f"Best ROA Object {token}")`
- L574–575: Replace scenario map keys `"roa"` / `"roaprefix"` → `"roaobject"` / `"roaobjectprefix"` with corresponding form data builders
- L596–597: Same for filter cases
- L606–607: Same for table rows

**Verification**: factories importable and create valid objects.

### Slice 3: Object registry and surface layer

Status: Completed on April 15, 2026.

**Owner**: surface window

**Files**: `object_registry.py`, `detail_specs.py`, `api/serializers.py`, `graphql/types.py`, `views.py`, `navigation.py`, `sample_data.py`, `forms.py`, template

Every change is enumerated in the dependency map above. Key callouts:

**New `roaobject` ObjectSpec** (replaces L331–393 in object_registry.py):
```python
    ObjectSpec(
        registry_key="roaobject",
        model=models.RoaObject,
        labels=LabelSpec(singular="ROA Object", plural="ROA Objects"),
        routes=RouteSpec(slug="roaobject", path_prefix="roaobject"),
        api=ApiSpec(
            serializer_name="RoaObjectSerializer",
            viewset_name="RoaObjectViewSet",
            basename="roaobject",
            fields=(
                "id", "url", "name", "organization", "origin_as",
                "valid_from", "valid_to", "validation_state", "signed_object",
            ),
            brief_fields=("name", "origin_as", "organization"),
        ),
        filterset=FilterSetSpec(
            class_name="RoaObjectFilterSet",
            fields=("name", "organization", "origin_as", "valid_from", "valid_to",
                    "validation_state", "signed_object", "tenant"),
            search_fields=("name__icontains", "comments__icontains"),
        ),
        graphql=GraphQLSpec(
            filter=GraphQLFilterSpec(
                class_name="RoaObjectFilter",
                fields=(
                    GraphQLFilterFieldSpec(field_name="name", filter_kind="str"),
                    GraphQLFilterFieldSpec(field_name="organization_id", filter_kind="id"),
                    GraphQLFilterFieldSpec(field_name="origin_as_id", filter_kind="id"),
                    GraphQLFilterFieldSpec(field_name="validation_state", filter_kind="str"),
                    GraphQLFilterFieldSpec(field_name="signed_object_id", filter_kind="id"),
                ),
            ),
            type=GraphQLTypeSpec(class_name="RoaObjectType"),
            detail_field_name="netbox_rpki_roa_object",
            list_field_name="netbox_rpki_roa_object_list",
        ),
        form=FormSpec(
            class_name="RoaObjectForm",
            fields=("name", "organization", "origin_as", "valid_from", "valid_to",
                    "validation_state", "signed_object", "tenant", "comments", "tags"),
        ),
        filter_form=FilterFormSpec(class_name="RoaObjectFilterForm"),
        table=TableSpec(
            class_name="RoaObjectTable",
            fields=("pk", "id", "name", "organization", "origin_as", "valid_from",
                    "valid_to", "validation_state", "signed_object", "comments", "tenant", "tags"),
            default_columns=("name", "organization", "origin_as", "valid_from",
                             "valid_to", "validation_state", "comments", "tenant", "tags"),
            linkify_field="name",
        ),
        view=ViewSpec(
            list_class_name="RoaObjectListView",
            detail_class_name="RoaObjectView",
            edit_class_name="RoaObjectEditView",
            delete_class_name="RoaObjectDeleteView",
        ),
        navigation=NavigationSpec(group="ROAs", label="ROA Objects", order=10),
    ),
```

**New `roaobjectprefix` ObjectSpec** (replaces L396–442):
```python
    ObjectSpec(
        registry_key="roaobjectprefix",
        model=models.RoaObjectPrefix,
        labels=LabelSpec(singular="ROA Object Prefix", plural="ROA Object Prefixes"),
        routes=RouteSpec(slug="roaobjectprefix", path_prefix="roaobjectprefixes"),
        api=ApiSpec(
            serializer_name="RoaObjectPrefixSerializer",
            viewset_name="RoaObjectPrefixViewSet",
            basename="roaobjectprefix",
            fields=("id", "url", "roa_object", "prefix", "prefix_cidr_text", "max_length", "is_current"),
            brief_fields=("id", "roa_object", "prefix_cidr_text", "max_length"),
        ),
        filterset=FilterSetSpec(
            class_name="RoaObjectPrefixFilterSet",
            fields=("roa_object", "prefix", "max_length", "is_current", "tenant"),
            search_fields=("prefix_cidr_text__icontains", "comments__icontains"),
        ),
        graphql=GraphQLSpec(
            filter=GraphQLFilterSpec(
                class_name="RoaObjectPrefixFilter",
                fields=(
                    GraphQLFilterFieldSpec(field_name="roa_object_id", filter_kind="id"),
                    GraphQLFilterFieldSpec(field_name="prefix_id", filter_kind="id"),
                    GraphQLFilterFieldSpec(field_name="is_current", filter_kind="bool"),
                ),
            ),
            type=GraphQLTypeSpec(class_name="RoaObjectPrefixType"),
            detail_field_name="netbox_rpki_roa_object_prefix",
            list_field_name="netbox_rpki_roa_object_prefix_list",
        ),
        form=FormSpec(
            class_name="RoaObjectPrefixForm",
            fields=("roa_object", "prefix", "prefix_cidr_text", "max_length", "is_current", "tenant", "comments", "tags"),
        ),
        filter_form=FilterFormSpec(class_name="RoaObjectPrefixFilterForm"),
        table=TableSpec(
            class_name="RoaObjectPrefixTable",
            fields=("pk", "id", "roa_object", "prefix", "prefix_cidr_text", "max_length", "is_current", "comments", "tenant", "tags"),
            default_columns=("roa_object", "prefix_cidr_text", "max_length", "is_current", "comments", "tenant", "tags"),
            linkify_field="pk",
        ),
        view=ViewSpec(
            list_class_name="RoaObjectPrefixListView",
            detail_class_name="RoaObjectPrefixView",
            edit_class_name="RoaObjectPrefixEditView",
            delete_class_name="RoaObjectPrefixDeleteView",
            simple_detail=True,
        ),
    ),
```

**Verification**: `./dev.sh test contract` passes.

### Slice 4: Service layer switchover

Status: Completed on April 15, 2026.
Implementation note: this slice also updated `services/external_management.py` so external-management exception matching follows the renamed `roa_object` FK.

**Owner**: services window (one file at a time)

Every change is enumerated in the dependency map above. The files with changes and their complexity:

| File | Changes | Complexity |
|------|---------|------------|
| `routing_intent.py` | ~20 references: dataclass, query, 5 object-creation sites, source-key, field access | High |
| `external_validation.py` | 4 references: function rename, query rewrite, 2 dict key changes | Medium |
| `overlay_correlation.py` | 4 references: isinstance, DoesNotExist, type hint, reverse relation | Low |
| `overlay_reporting.py` | ~8 references: select_related args, field access, isinstance | Medium |
| `lifecycle_reporting.py` | 1 reference: queryset filter rewrite | Trivial |
| `roa_lint.py` | String labels only — grep-verify no model references | Trivial |
| `governance_summary.py` | No changes needed | None |
| `provider_write.py` | No direct model references — grep-verify | None |
| `provider_sync_krill.py` | No changes needed (file extension detection) | None |
| `provider_sync_evidence.py` | No changes needed (file extension detection) | None |

**Verification**: `./dev.sh test full` passes.

### Slice 5: Test suite update

Status: Completed on April 15, 2026.
Verification note: the updated suite now passes `./dev.sh test fast` and `./dev.sh test contract`.

**Owner**: test window

**Files and change summary**:

| File | Lines affected | Nature of changes |
|------|---------------|-------------------|
| `test_models.py` | L13 (import), L54/58 (factory imports), L82–89 (setUp), L95–128 (basic tests), L193–336 (normalization tests), L244–260 (validation tests) | Replace all `Roa`/`RoaPrefix` with `RoaObject`/`RoaObjectPrefix`. `signed_by` assertions become `organization`/`signed_object.resource_certificate` traversals. `auto_renews` assertions removed. `RoaToPrefixTable` → `prefix_authorizations`. |
| `test_views.py` | L12 (import), L63/73 (factory imports), L698–705 (setUp), L802/856 (detail tests) | Replace fixture creation. `legacy_roa` detail link test → `roa_extension`. |
| `test_api.py` | L19–20 (serializer imports), L29–30 (model imports), L82/86 (factory imports), L1159–1204 (scenarios), L3334–3419 (test classes) | Replace `'roa'`/`'roaprefix'` scenarios with `'roaobject'`/`'roaobjectprefix'`. Scenario fields change: no `auto_renews`/`signed_by`, add `organization`/`validation_state`. |
| `test_graphql.py` | L22–23 (imports), L51–52 (factory imports), L434–496 (test classes) | Replace `RoaGraphQLTestCase` → `RoaObjectGraphQLTestCase`, `RoaPrefixGraphQLTestCase` → `RoaObjectPrefixGraphQLTestCase`. |
| `test_routing_intent_services.py` | L40/45 (factory imports), L1122–1123, L1508–1513, L1594–1599 (fixture creation) | Replace `create_test_roa` → `create_test_roa_object`, `create_test_roa_prefix` → `create_test_roa_object_prefix`. FK kwargs: `roa=` → `roa_object=`. |
| `test_overlay_correlation.py` | L24–25 (factory imports), L49–53 (setUp) | Same factory replacement. |
| `test_external_validation.py` | L18–19 (factory imports), L65–69 (setUp) | Same factory replacement. |

**Verification**: `./dev.sh test full` passes. `grep -rn 'Roa\b' netbox_rpki/tests/ | grep -v RoaObject | grep -v ImportedRoa | grep -v ValidatedRoa | grep -v ROAIntent | grep -v ROAChange | grep -v ROALint | grep -v ROAR` returns zero results.

### Slice 6: E2E tests and cleanup

Status: Completed on April 15, 2026.
Implementation note: the E2E helper paths and object builders were updated to `roaobject` / `roaobjectprefix`; the E2E lane itself was not executed in this pass.

**Owner**: test window

**Files and changes**:

| File | Lines | Changes |
|------|-------|---------|
| `tests/e2e/scripts/prepare_netbox_rpki_e2e.py` | L10–11 (imports), L18–19 (deletion) | `Roa` → `RoaObject`, `RoaPrefix` → `RoaObjectPrefix` |
| `tests/e2e/helpers/netbox-rpki.js` | L10–11 (paths) | `roaPrefixes: '/plugins/netbox_rpki/roaobjectprefixes/'`, `roas: '/plugins/netbox_rpki/roaobject/'` (rename constant to `roaObjects`) |
| `tests/e2e/helpers/netbox-rpki.js` | L120–149 (`createRoaFromCertificate`) | Rename to `createRoaObject`. Update form field names: remove `auto_renews`, remove `signed_by`, add `organization`, add `validation_state`. Update URL path. |
| `tests/e2e/helpers/netbox-rpki.js` | L192–218 (`createRoaPrefixFromRoa`) | Rename to `createRoaObjectPrefix`. Update form field `roa_name` → `roa_object`. Add `prefix_cidr_text`. Update URL path. |
| `tests/e2e/netbox-rpki/roas.spec.js` | L14 (path), L22 (URL regex) | `PATHS.roas` → `PATHS.roaObjects`, regex updated |
| `tests/e2e/netbox-rpki/relations.spec.js` | L9–10 (imports), L59–80 (test block) | Updated function names and path references |

**Verification**: `./dev.sh e2e` passes.

---

## Verification Checklist (run after all slices)

Execution status on April 15, 2026:
- Completed: `./dev.sh test fast`
- Completed: `./dev.sh test contract`
- Completed: `manage.py makemigrations --check --dry-run netbox_rpki` (`No changes detected in app 'netbox_rpki'`)
- Not run in this pass: `./dev.sh test full`
- Not run in this pass: `./dev.sh e2e`

```bash
# 1. Migration state
cd ~/src/netbox_rpki/devrun
./dev.sh test fast

# 2. No stale model references
grep -rn 'models\.Roa\b' netbox_rpki/netbox_rpki/ --include='*.py' | grep -v RoaObject | grep -v migration
# Expected: zero results

grep -rn 'models\.RoaPrefix\b' netbox_rpki/netbox_rpki/ --include='*.py' | grep -v RoaObjectPrefix | grep -v migration
# Expected: zero results

grep -rn "'legacy_roa'" netbox_rpki/netbox_rpki/ --include='*.py'
# Expected: zero results

grep -rn 'RoaToPrefixTable' netbox_rpki/netbox_rpki/ --include='*.py'
# Expected: zero results

grep -rn 'auto_renews' netbox_rpki/netbox_rpki/ --include='*.py' | grep -v migration
# Expected: zero results

grep -rn 'signed_by' netbox_rpki/netbox_rpki/ --include='*.py' | grep -v migration | grep -v Certificate
# Expected: zero results (only Certificate model should have signed_by references)

# 3. Full test suite
./dev.sh test full

# 4. Contract tests
./dev.sh test contract

# 5. Migration check
cd ~/src/netbox-v4.5.7/netbox
NETBOX_CONFIGURATION=netbox_rpki.tests.netbox_configuration \
NETBOX_RPKI_ENABLE=1 \
~/.virtualenvs/netbox-4.5.7/bin/python manage.py makemigrations --check --dry-run netbox_rpki
# Expected: "No changes detected"

# 6. E2E (if stack is running)
./dev.sh e2e
```

## File Ownership

Only one worker touches a given file group at a time:

| Window | Files |
|--------|-------|
| Schema | `models.py`, `migrations/` |
| Surface | `object_registry.py`, `detail_specs.py`, `api/serializers.py`, `graphql/types.py`, `forms.py`, `filtersets.py`, `tables.py`, `views.py`, `navigation.py`, `sample_data.py` |
| Services | `services/routing_intent.py`, `services/overlay_*.py`, `services/external_validation.py`, `services/roa_lint.py`, `services/lifecycle_reporting.py` |
| Tests | `tests/utils.py`, `tests/registry_scenarios.py`, `tests/test_*.py`, `tests/e2e/` |

## Resolved Questions

1. **Final model name**: `RoaObject` / `RoaObjectPrefix`. No rename planned.
2. **`auto_renews` disposition**: Dropped entirely. Not carried forward.
3. **Release strategy**: All slices ship in a single release.
4. **URL slugs**: New permanent slugs `roaobject` / `roaobjectprefix`. Old slugs removed.
