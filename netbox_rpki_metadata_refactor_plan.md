# NetBox RPKI Plugin: Metadata-Driven Refactor Plan

Prepared: April 11, 2026

## Objective

Refactor the existing `netbox_rpki` plugin so that the current object families are described once in a central registry/specification layer, and the repetitive UI/API/GraphQL/navigation/test wiring is generated from that metadata.

This plan deliberately postpones adding the new standards-based RPKI objects from section 9 of the backlog. The goal is to reduce structural duplication first, then add Trust Anchors, TALs, and rollover artifacts on top of a saner foundation.

## What The Current Codebase Actually Does

Today, each plugin object family is hand-defined across nearly every surface:

- model in `netbox_rpki/models.py`
- form in `netbox_rpki/forms.py`
- filterset in `netbox_rpki/filtersets.py`
- table in `netbox_rpki/tables.py`
- UI CRUD views in `netbox_rpki/views.py`
- UI routes in `netbox_rpki/urls.py`
- API serializer in `netbox_rpki/api/serializers.py`
- API viewset in `netbox_rpki/api/views.py`
- API router registration in `netbox_rpki/api/urls.py`
- GraphQL filter in `netbox_rpki/graphql/filters.py`
- GraphQL type in `netbox_rpki/graphql/types.py`
- GraphQL query fields in `netbox_rpki/graphql/schema.py`
- navigation entry in `netbox_rpki/navigation.py`
- object detail template in `netbox_rpki/templates/netbox_rpki/*.html`
- test helpers and factory functions in `netbox_rpki/tests/utils.py`
- per-surface tests in `netbox_rpki/tests/test_*.py`

That methodology works, but it scales badly. Adding one new object family means touching a large number of files, mostly with repetitive code. It also raises the risk of partial implementations where one surface is forgotten.

## Better Approach

Yes, there is a better approach, but it needs to be disciplined.

The reasonable target is:

1. Keep Django models explicit.
2. Keep migrations explicit.
3. Define all non-model object metadata once.
4. Generate the repetitive NetBox surfaces from that metadata.
5. Keep escape hatches for object-specific behavior.

The unreasonable target would be trying to generate Django model classes dynamically. That will fight Django migrations, relationship declarations, reverse names, and IDE support. It is not worth it.

The sane split is:

- model layer remains explicit Python classes
- everything around the model becomes registry-driven where practical

## Proposed Architecture

### 1. Add an object registry

Create a central registry module, for example:

- `netbox_rpki/object_specs.py`
- `netbox_rpki/object_registry.py`

Each existing object family gets one spec entry, for example:

- `organization`
- `certificate`
- `roa`
- `roaprefix`
- `certificateprefix`
- `certificateasn`

Each spec should capture metadata such as:

- object key
- model class
- singular and plural labels
- URL segment and route names
- menu grouping metadata
- form field order
- filterset fields
- search fields
- table columns and default columns
- serializer fields and brief fields
- GraphQL filterable fields
- object detail layout metadata
- related tables shown on detail view
- add-button prefill rules
- test factory name or factory callable

Suggested shape:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RelatedTableSpec:
    context_name: str
    table_class_name: str
    queryset_attr: str
    title: str
    add_url_name: str | None = None
    prefill_param: str | None = None


@dataclass(frozen=True)
class ObjectSpec:
    key: str
    model: type
    label: str
    label_plural: str
    url_slug: str
    menu_group: str | None
    menu_label: str | None
    form_fields: tuple[str, ...]
    filter_fields: tuple[str, ...]
    search_fields: tuple[str, ...]
    table_fields: tuple[str, ...]
    table_default_columns: tuple[str, ...]
    serializer_fields: tuple[str, ...]
    serializer_brief_fields: tuple[str, ...]
    graphql_filter_fields: tuple[str, ...]
    detail_fields: tuple[str, ...]
    related_tables: tuple[RelatedTableSpec, ...] = field(default_factory=tuple)
```

This should become the single source of truth for all non-model definitions.

### 2. Add surface factories

Create a small set of factories/builders that consume `ObjectSpec` entries:

- `build_model_form(spec)`
- `build_filterset(spec)`
- `build_filter_form(spec)`
- `build_table(spec)`
- `build_serializer(spec)`
- `build_viewset(spec)`
- `build_list_view(spec)`
- `build_edit_view(spec)`
- `build_delete_view(spec)`
- `build_graphql_filter(spec)`
- `build_graphql_type(spec)`

These do not need to be magical. They just need to eliminate repeated boilerplate.

### 3. Replace custom detail templates with a generic detail renderer

The current object detail templates are mostly repeated attribute tables with a few related tables and add buttons.

That should become a reusable detail view/template layer driven by metadata such as:

- primary attribute rows
- related table sections
- add buttons with prefilled query parameters
- which fields should link to related objects

Add something like:

- `netbox_rpki/templates/netbox_rpki/object_detail.html`
- `netbox_rpki/detail_specs.py`

Each `ObjectSpec` can point to a detail layout definition. For objects that eventually need unusual rendering, keep an override hook such as:

- `detail_template_name=None` means use generic template
- `detail_context_builder=None` means no custom extra context

### 4. Centralize URL and menu registration

`urls.py`, `api/urls.py`, and `navigation.py` should iterate the registry instead of hard-coding every object.

That allows one new object family to become routable and visible by adding one registry entry.

### 5. Parameterize tests off the same registry

The current tests also duplicate per-object behavior.

After the refactor, most of these should become spec-driven:

- serializer smoke tests
- viewset smoke tests
- navigation tests
- GraphQL schema field registration tests
- ordering and `get_absolute_url()` tests
- generic CRUD smoke tests for list/create/edit/delete

Keep object-specific tests only where the object genuinely has custom behavior.

## What Should Stay Explicit

Not everything should be generated.

The following should remain explicit or semi-explicit:

- Django model classes
- database migrations
- model methods with real behavior
- complex detail context builders where related data is unusual
- factory functions for creating test instances with real foreign-key semantics
- future business logic such as reconciliation, provider sync, linting, and simulations

The point is not to replace readable code with metaclass soup. The point is to move repeated declarations into one place.

## Recommended Supporting Refactors

Before or during the registry work, introduce a few small abstractions that reduce repetition in the model layer without becoming clever:

### Abstract model mixins

Useful candidates:

- `TenantScopedModelMixin`
- `NamedObjectMixin`
- `ValidityWindowMixin`
- `CommentsModelMixin`

This is optional, but it can clean up the current model file and make future model families more regular.

### Naming normalization

Some current field names should be normalized before the registry becomes canonical:

- `roa_name` should eventually become `roa`
- `certificate_name` should eventually become `certificate`
- `certificate_name2` should eventually become `certificate`

Do not do those renames in the same step as the first registry introduction unless compatibility shims are in place. They are worth doing, but they will touch tests, templates, filters, and serializers.

### Module layout cleanup

Once the registry exists, the current flat module layout can stay, but a more maintainable structure would be:

- `netbox_rpki/models/`
- `netbox_rpki/ui/`
- `netbox_rpki/api/`
- `netbox_rpki/graphql/`
- `netbox_rpki/specs/`

This is secondary. The registry is the important change.

## Migration Strategy

The safest implementation path is incremental.

### Phase 0: Freeze behavior with tests

Before changing surface generation, make sure the existing object families have enough coverage to catch regressions in:

- URLs
- menus
- list views
- detail views
- create/edit/delete flows
- API routes
- GraphQL fields

The current test suite is already a decent base for this.

### Phase 1: Introduce the registry without changing behavior

Add:

- object spec dataclasses
- registry entries for the six existing object families
- basic helper functions for naming and route generation

At this stage, the existing manual classes can still exist. The first goal is just to establish the canonical metadata layer.

Deliverable:

- one place where object metadata is defined once

### Phase 2: Migrate low-risk surfaces first

Generate the following from the registry first:

- navigation entries
- API router registration
- serializer smoke mappings
- viewset querysets and class declarations

These are low-risk because they are mostly structural.

Recommended first objects:

- `certificateasn`
- `certificateprefix`
- `roaprefix`

They have the least custom detail behavior.

### Phase 3: Migrate forms, filtersets, and tables

Generate:

- `NetBoxModelForm` subclasses
- filtersets with common search behavior
- filter forms
- table classes with common tenant/tags columns

At the end of this phase, most of the repetitive code in:

- `forms.py`
- `filtersets.py`
- `tables.py`
- `api/serializers.py`
- `api/views.py`
- `api/urls.py`
- `navigation.py`

should be spec-driven.

### Phase 4: Replace detail templates and UI views

Introduce a generic object detail view and generic detail template.

Migrate in this order:

1. `Organization`
2. `Roa`
3. `Certificate`

That order follows rising complexity.

At this phase, `views.py`, `urls.py`, and `templates/netbox_rpki/*.html` should shrink meaningfully.

### Phase 5: Refactor GraphQL generation

GraphQL is a good candidate for registry-driven generation, but it is also where too much magic becomes hard to debug.

Use a conservative approach:

- spec-driven filter field definitions
- thin generated Strawberry types
- query field registration from the registry

Avoid forcing everything through one huge dynamic metaprogram. Keep the generated output inspectable.

### Phase 6: Parameterize tests

Convert repeated smoke tests into registry-driven test mixins and factory lookups.

Keep custom tests for:

- detail page related-table rendering
- prefill button query parameters
- any model-specific validation behavior

### Phase 7: Clean up legacy names and dead code

Only after the generated pattern is stable should you remove:

- duplicated manual classes
- obsolete templates
- hard-coded registration tables
- compatibility aliases introduced during migration

## Recommended File Additions

These are the most likely new files/modules:

- `netbox_rpki/object_specs.py`
- `netbox_rpki/object_registry.py`
- `netbox_rpki/surface_builders.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/templates/netbox_rpki/object_detail.html`
- `netbox_rpki/tests/spec_registry.py`

Optional:

- `netbox_rpki/model_mixins.py`

## Design Rules For The Registry

To keep this maintainable, follow these rules:

1. One registry entry per object family.
2. No duplicate field lists outside the registry unless there is a strong reason.
3. Factories must be predictable and readable.
4. Public route names should stay stable unless there is a deliberate migration.
5. Generated classes should have stable names for debugging and tests.
6. Any object-specific override should live next to the registry entry, not in scattered special cases.
7. Do not generate Django models dynamically.

## Concrete First Implementation Slice

The first slice should be intentionally small.

### Slice A

Implement:

- `ObjectSpec`
- registry entries for existing six objects
- generated API router/viewset/serializer classes
- generated navigation

Keep UI views/templates/forms/filtersets/tables/manual for the first slice.

This gives immediate value with low blast radius.

### Slice B

Implement:

- generated filtersets
- generated forms
- generated tables

Start with:

- `CertificateAsn`
- `CertificatePrefix`
- `RoaPrefix`

### Slice C

Implement:

- generic detail template
- generic object detail view
- spec-defined related-table blocks and add buttons

Finish with:

- `Organization`
- `Roa`
- `Certificate`

## Why This Refactor Should Happen Before Trust Anchors

Trust anchors, TALs, and rollover artifacts will add another wave of object families and linked detail views.

If they are added to the current plugin shape, the codebase will get materially more repetitive.

If they are added after the refactor:

- the model classes still need to be written explicitly
- most UI/API/GraphQL/menu/route/test surfaces become one new spec entry plus targeted overrides
- future section 9 work becomes much cheaper and less error-prone

## Risks

### Over-engineering risk

If the factories become too dynamic, debugging will get worse. Keep the generated surfaces simple and inspectable.

### Naming migration risk

The current inconsistent relation field names are awkward but stable. Renaming them too early will create unnecessary churn.

### GraphQL metaprogramming risk

Strawberry can support generation, but this is the place where cleverness becomes fragile fastest. Prefer thin wrappers over aggressive reflection.

### Template generalization risk

The generic detail renderer should cover 80 to 90 percent of cases. Keep a per-object template override path for exceptions.

## Success Criteria

The refactor is successful when:

1. Existing six object families still behave the same from the user perspective.
2. Route names and API endpoints remain stable.
3. New object family introduction no longer requires hand-editing most top-level surface files.
4. The majority of repeated definitions live in one spec registry.
5. The next Trust Anchor and TAL implementation can be added mostly by defining models plus registry entries.

## Recommended Next Step

Start with Slice A only.

That means:

1. introduce the registry and spec dataclasses
2. move the six existing object definitions into that registry
3. generate API viewsets, serializers, router registrations, and navigation from the registry
4. keep everything else stable

That gives a real structural win without trying to refactor the whole plugin in one jump.