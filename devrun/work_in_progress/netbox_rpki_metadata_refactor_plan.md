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

## ASPA Implementation Note

The revised enhancement backlog now makes the intended ASPA shape explicit enough that the first implementation wave should follow it directly rather than inventing a parallel structure.

Recommended standards-aligned ASPA family:

- `ASPA` remains the published signed-object subtype keyed by `customer_asn`
- `ASPAProviderAuthorization` remains the child relationship row carrying each authorized provider ASN
- `ASPAIntent` should be modeled as an operator-intent relationship row, not a separate parent-plus-child tree; one row represents one intended `customer_asn` to `provider_asn` authorization
- `ASPAReconciliationResult` should compare intended vs published provider relationships and remain distinct from provider-specific import artifacts

Recommended first implementation sequence:

1. Harden the current inventory layer:
- keep `ASPA` as a stable top-level object
- treat provider authorizations as child rows beneath the ASPA detail flow
- enforce uniqueness and basic semantic validation on provider-authorizations
- add intentional operator detail UX showing authorized providers and validated ASPA payloads

2. Add provider-imported ASPA state:
- keep provider sync orthogonal to core ASPA semantics
- add imported ASPA objects and provider-side identity tracking rather than overloading local published ASPA rows
- start with Krill as the first ASPA adapter

3. Add operator intent and reconciliation:
- add `ASPAIntent`
- add `ASPAReconciliationResult`
- derive intent explicitly from ASN-centered operator input first; do not try to infer v1 intent automatically from circuits or provider metadata

This matches the revised backlog’s separation of:

- published cryptographic objects
- operator intent
- provider snapshots and external references
- reconciliation and workflow artifacts

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

## Post-Implementation Addendum

This section documents what was actually implemented after the original plan was written, and how future section 9 work should build on it.

The short version is that the plugin now has a real metadata-driven extension pattern for standard non-model surfaces. A follow-on developer or agent should not reintroduce hand-wired duplication for new standards-based RPKI object families unless there is a specific reason a surface cannot fit the shared pattern.

## What Was Actually Implemented

The following parts of the refactor are complete:

- explicit spec dataclasses in `netbox_rpki/object_specs.py`
- a canonical registry in `netbox_rpki/object_registry.py`
- generated API serializers, viewsets, and router registration
- generated forms, filter forms, filtersets, and tables
- generated navigation
- generated standard CRUD UI views and most UI route registration
- metadata-driven GraphQL filters, types, and query registration
- a shared detail-view metadata layer in `netbox_rpki/detail_specs.py`
- a shared detail template in `netbox_rpki/templates/netbox_rpki/object_detail.html`
- registry-driven and scenario-driven smoke tests across most repeated surfaces

The Django model layer and migrations remain explicit by design.

## Canonical Files And Their Roles

Use these files as the architectural source of truth when adding new object families.

### `netbox_rpki/object_specs.py`

This file defines the spec contract. It is no longer a proposal. It is the active interface for metadata-driven generation.

Key responsibilities:

- label metadata
- route metadata
- API metadata
- form and filter metadata
- GraphQL metadata
- table metadata
- view metadata

If a new standard surface needs repeatable configuration, add it to the spec layer instead of scattering one-off constants around the codebase.

### `netbox_rpki/object_registry.py`

This is the canonical registry of object families. Existing plugin families are declared here and the registry exports filtered subsets for the surfaces that generate code from it.

Important implementation lesson:

- preserve explicit public names here rather than deriving everything from model names

That includes serializer class names, viewset class names, GraphQL class names, GraphQL query field names, UI class names, and menu labels. Stable external names matter more than deduplication purity.

### `netbox_rpki/detail_specs.py`

This file is the canonical metadata layer for richer detail pages. It is currently used for top-level objects whose detail views need curated field ordering, related tables, and prefilled add actions.

Current pattern:

- richer top-level objects use explicit `DetailSpec` entries
- simpler objects use the lightweight generated detail path from the registry view metadata

Future section 9 objects should follow that same split. Do not force every object into the rich detail system if a simple generated detail page is enough.

### Generated surface modules

The following modules now consume the registry and should continue to do so:

- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/api/urls.py`
- `netbox_rpki/forms.py`
- `netbox_rpki/filtersets.py`
- `netbox_rpki/tables.py`
- `netbox_rpki/views.py`
- `netbox_rpki/urls.py`
- `netbox_rpki/navigation.py`
- `netbox_rpki/graphql/filters.py`
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/graphql/schema.py`

When a new object family is added, the default expectation is that these modules pick it up from registry metadata rather than requiring hand-authored class declarations.

### Shared tests

The following test files now encode the reusable verification pattern:

- `netbox_rpki/tests/registry_scenarios.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_forms.py`
- `netbox_rpki/tests/test_filtersets.py`
- `netbox_rpki/tests/test_tables.py`
- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/test_navigation.py`
- `netbox_rpki/tests/test_graphql.py`
- `netbox_rpki/tests/test_urls.py`

Add new object families to the shared scenarios and loops where they fit. Keep tests explicit only where the new object has genuinely object-specific behavior.

## Rules For Adding New Section 9 Objects

The extension rule is now:

1. add explicit Django models and migrations
2. add one `ObjectSpec` entry per object family that should participate in the standard generated surfaces
3. add `DetailSpec` entries only for objects that need richer curated detail pages
4. add or extend shared registry-driven tests
5. keep object-specific business logic explicit and local

This is the intended split:

- models, migrations, and real business logic stay explicit
- repeated UI/API/GraphQL/list/filter/table plumbing should be metadata-driven

Do not dynamically generate Django models.

Do not let new standards-based objects bypass the registry unless they are truly exceptional.

## Current Architectural Boundaries

Another developer or agent should assume these boundaries unless there is a compelling reason to change them.

### Keep explicit

- Django models
- migrations
- complex object-specific validation
- complex detail-page composition when it cannot be expressed cleanly in metadata
- provider sync, reconciliation, linting, simulation, and similar domain logic

### Keep registry-driven

- serializer class generation
- API viewset generation
- API router registration
- forms
- filter forms
- filtersets
- tables
- navigation
- standard list, edit, and delete views
- standard URL registration
- GraphQL filters, types, and query fields
- smoke-style repeated tests

## Lessons Learned From The Refactor

These are the practical rules that should guide future work.

### Preserve stable public names

The registry should store explicit names for generated classes and GraphQL fields. This is not accidental duplication. It protects compatibility and makes generated output inspectable.

### Favor inspectable generation over clever metaprogramming

The factories should stay boring. The successful pattern here was to generate plain classes with stable names and expose module-level maps such as serializer, viewset, GraphQL filter, and GraphQL type maps for tests and debugging.

### Use the rich detail system sparingly

Not every object needs a custom-feeling detail page. Reserve `detail_specs.py` for top-level objects where field ordering, related tables, and prefilled add actions matter. Simpler objects can keep the generic detail behavior.

### Keep compatibility shims intentional and small

The refactor preserved exact legacy UI path prefixes in `urls.py` through a focused compatibility map. That was a deliberate compromise to keep routes stable while moving other metadata into the registry.

If a future cleanup moves path metadata into the registry, do it deliberately and with tests. Do not silently change public URLs while adding new section 9 models.

### Parameterize tests where behavior is actually shared

The test suite now has a clear split:

- common smoke and structure checks are shared and registry-driven
- truly object-specific behavior remains explicit

Do not collapse meaningful behavior tests into generic loops just for neatness.

### Use non-interactive test commands only

For this repo, test runs should use the NetBox 4.5.7 environment and non-interactive flags. The known-good full-suite command is:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput netbox_rpki.tests
```

Interactive `manage.py test` prompts caused avoidable friction earlier in the work and should not be used for normal verification.

## How Section 9 Work Should Start Now

The original implementation objective was to begin adding the missing standards-based RPKI architecture elements from section 9 of `netbox_rpki_enhancement_backlog.md`, starting with:

- Trust Anchors
- TALs
- trust-anchor rollover artifacts

That work should now proceed in this order.

### Step 1: design the explicit model layer first

For the first slice, define the models and migrations explicitly. Do not try to force a generic standards supermodel prematurely at the Django model layer.

For example, the initial slice can reasonably introduce explicit models for:

- `TrustAnchor`
- `TrustAnchorLocator`
- `TrustAnchorKey`

Potential shared abstractions can be extracted later if they become obvious.

### Step 2: decide which of those models belong in the standard generated surfaces

For each new model, ask:

- does it need a normal list/add/edit/delete/API/GraphQL surface now?
- does it need a curated rich detail page now?
- is it a supporting relation object better handled with simpler generated views?

If the answer is yes to standard CRUD surfaces, add an `ObjectSpec` entry immediately.

If the answer is yes to a curated detail view, add a `DetailSpec` entry.

### Step 3: preserve stable naming from the first commit

Do not rely on implicit naming conventions for new standards-based objects if those names might later leak into public URLs, GraphQL fields, or serializer class names. Put the intended stable names into the metadata up front.

### Step 4: extend the shared test scenarios at the same time

Any new object that uses the standard generated surfaces should also be added to the registry-driven smoke and scenario coverage in the same implementation slice.

### Step 5: keep domain logic out of surface metadata

Validation of TAL format, trust-anchor rollover semantics, artifact linkage, publication behavior, and future reconciliation logic should stay in explicit model or service-layer code. The registry is for surface metadata, not business rules.

## Practical Starting Pattern For Trust Anchor Work

If another developer or agent picks up the original section 9 objective, the practical first implementation slice should look like this:

1. add explicit models and migrations for `TrustAnchor`, `TrustAnchorLocator`, and `TrustAnchorKey`
2. add matching registry entries for any of those that need standard CRUD, API, navigation, and GraphQL surfaces
3. add a rich `DetailSpec` only for whichever top-level trust-anchor object actually benefits from curated related-table rendering
4. extend shared tests and scenario definitions for every registry-participating object
5. run the full non-interactive NetBox plugin test suite

That is the intended continuation path.

## Bottom Line

Before this addendum, the implemented pattern was only partially documented: the original plan described the intended architecture, and the code embodied the final result, but there was not a single explicit prose handoff connecting the two.

After this addendum, `netbox_rpki_metadata_refactor_plan.md` should be treated as that handoff document for continuing section 9 work on top of the new registry-driven architecture.
