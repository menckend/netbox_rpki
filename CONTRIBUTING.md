# Contributing

Contributions are welcome, and they are greatly appreciated! Every little bit
helps, and credit will always be given.

We love your input! We want to make contributing to this project as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## General Tips for Working on GitHub

* Register for a free [GitHub account](https://github.com/signup) if you haven't already.
* You can use [GitHub Markdown](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax) for formatting text and adding images.
* To help mitigate notification spam, please avoid "bumping" issues with no activity. (To vote an issue up or down, use a :thumbsup: or :thumbsdown: reaction.)
* Please avoid pinging members with `@` unless they've previously expressed interest or involvement with that particular issue.
* Familiarize yourself with [this list of discussion anti-patterns](https://github.com/bradfitz/issue-tracker-behaviors) and make every effort to avoid them.

## Types of Contributions

### Report Bugs

Report bugs at https://github.com/menckend/netbox_rpki/issues.

If you are reporting a bug, please include:

* Your operating system name and version.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help
wanted" is open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features. Anything tagged with "enhancement"
and "help wanted" is open to whoever wants to implement it.

### Write Documentation

NetBox RPKI Plugin could always use more documentation, whether as part of the
official NetBox RPKI Plugin docs, in docstrings, or even on the web in blog posts,
articles, and such.

### Submit Feedback

The best way to send feedback is to file an issue at https://github.com/menckend/netbox_rpki/issues.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

## Get Started!

Ready to contribute? Here's how to set up `netbox_rpki` for local development.

1. Fork the `netbox_rpki` repo on GitHub.
2. Clone your fork locally

    ```
    $ git clone git@github.com:your_name_here/netbox_rpki.git
    ```

3. Activate the NetBox virtual environment (see the NetBox documentation under [Setting up a Development Environment](https://docs.netbox.dev/en/stable/development/getting-started/)):

    ```
    $ source ~/.venv/netbox/bin/activate
    ```

4. Add the plugin to NetBox virtual environment in Develop mode (see [Plugins Development](https://docs.netbox.dev/en/stable/plugins/development/)):

    To ease development, install the plugin in editable mode from the plugin root directory:

    ```
    $ python -m pip install -e .
    ```

5. Create a branch for local development:

    ```
    $ git checkout -b name-of-your-bugfix-or-feature
    ```

    Now you can make your changes locally.

6. Commit your changes and push your branch to GitHub:

    ```
    $ git add .
    $ git commit -m "Your detailed description of your changes."
    $ git push origin name-of-your-bugfix-or-feature
    ```

7. Submit a pull request through the GitHub website.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring, and add the
   feature to the list in README.md.
3. The pull request should work for Python 3.12, 3.13 and 3.14. Check
    https://github.com/menckend/netbox_rpki/actions
   and make sure that the tests pass for all supported Python versions.


## Registry-Based Architecture

This section is the implementation-facing guide for the registry-based architecture in this plugin. It explains what is generated, what must stay explicit, and the exact wiring required when you add new models or extend an existing object family.

Read this together with these source-of-truth files when you are doing architecture work:

- `netbox_rpki/object_specs.py`
- `netbox_rpki/object_registry.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/views.py`
- `netbox_rpki/urls.py`
- `netbox_rpki/forms.py`
- `netbox_rpki/filtersets.py`
- `netbox_rpki/tables.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/api/urls.py`
- `netbox_rpki/graphql/filters.py`
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/graphql/schema.py`
- `netbox_rpki/tests/registry_scenarios.py`
- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_graphql.py`
- `devrun/work_in_progress/netbox_rpki_metadata_refactor_plan.md`
- `devrun/work_in_progress/netbox_rpki_surface_contract_checklist.md`

### Core architecture

The plugin has a deliberate split between the explicit Django model layer and the generated plugin-surface layer.

Keep explicit:

- Django models
- Django migrations
- domain rules and business logic
- jobs and services
- complex validation
- any detail page that cannot be described cleanly with metadata
- any API action that is not standard CRUD

Keep registry-driven:

- standard REST serializers
- standard REST viewsets
- API router registration
- standard forms
- filter forms
- filtersets
- tables
- standard list, detail, edit, and delete views
- standard UI URL registration
- navigation/menu registration
- GraphQL filters, types, and query field registration
- shared smoke and surface-contract tests

The registry exists to eliminate repeated plumbing. It does not exist to hide domain behavior or to dynamically invent the model layer.

### The spec contract

`netbox_rpki/object_specs.py` defines the active metadata contract.

Each `ObjectSpec` has these major parts:

- `registry_key`: the plugin-internal identity for the object family
- `model`: the explicit Django model class
- `labels`: singular and plural UI labels
- `routes`: public UI naming and path metadata
- `api`: serializer, viewset, and REST basename metadata
- `filterset`: filter and search configuration
- `graphql`: GraphQL filter, type, and query-field metadata
- `navigation`: menu group, label, ordering, and add-button visibility
- `form`: standard edit-form class metadata
- `filter_form`: list filter-form class metadata
- `table`: standard list/detail related-table metadata
- `view`: standard list/detail/edit/delete class metadata and mutability

The important point is that `ObjectSpec` is not a loose suggestion. The generator modules build real classes and routes from it.

### Internal identity versus public naming

This plugin used to overload one identifier for too many jobs. That caused route mismatches, broken reverse lookups, GraphQL drift, and UI links that pointed at routes which did not actually exist.

Do not reintroduce that mistake.

There are now separate naming layers:

- `registry_key`: internal plugin identity used for maps and generator lookups
- `RouteSpec.slug`: public UI route name stem
- `RouteSpec.path_prefix`: public UI path segment when the path must not be derived from the slug
- `ApiSpec.basename`: public REST router basename
- `GraphQLSpec.detail_field_name`: public singular GraphQL field name
- `GraphQLSpec.list_field_name`: public list GraphQL field name

Rules:

- `registry_key` should be stable and internal.
- Public names should be set explicitly whenever there is any chance of collision, drift, or future rename pressure.
- Do not assume that model class names are safe public names.
- Do not assume that pluralized URLs can be derived mechanically.

Current examples:

- `RpkiProviderAccount` keeps a plugin-specific model name to avoid collisions, but its public slug, API basename, and GraphQL fields are exposed as `provideraccount`.
- Legacy inventory objects keep exact path prefixes such as `orgs`, `roaprefixes`, `certificateprefixes`, and `certificateasns` even though their slugs are not those exact strings.

If you are tempted to collapse these fields back into one identifier, stop. The split is intentional and was added to fix real breakage.

### Generation pipeline

The registry feeds nearly every standard surface in the plugin.

#### UI generation

`netbox_rpki/views.py` generates standard list, detail, edit, and delete view classes.

Important behavior:

- list actions are built from `ViewSpec.supports_create`
- detail actions are built from `ViewSpec.supports_create` and `ViewSpec.supports_delete`
- read-only objects do not get generated clone, edit, delete, or add actions
- simple detail pages are generated from `spec.api.fields`
- richer detail pages are pulled from `detail_specs.py`

`netbox_rpki/urls.py` registers the generated routes using `spec.routes.slug` and `spec.routes.resolved_path_prefix`.

`netbox_rpki/navigation.py` builds the plugin menu from `NavigationSpec` and suppresses the add button unless the object is actually creatable.

`netbox_rpki/tables.py` builds standard tables and row actions. Row-action menus are also derived from mutability. This matters because NetBox table defaults otherwise assume edit and delete routes exist.

#### Form and filter generation

`netbox_rpki/forms.py` generates:

- standard model forms from `spec.form`
- standard filter forms from `spec.filter_form`

The standard generated model form injects `tenant` and `comments`, and the standard generated filter form injects `q`, `tenant`, and `tag`.

`netbox_rpki/filtersets.py` generates standard filtersets from `spec.filterset` and implements the shared text-search behavior using `spec.filterset.search_fields`.

#### REST API generation

`netbox_rpki/api/serializers.py` generates standard `NetBoxModelSerializer` subclasses and exposes them through `SERIALIZER_CLASS_MAP` keyed by `registry_key`.

`netbox_rpki/api/views.py` generates standard `NetBoxModelViewSet` subclasses and exposes them through `VIEWSET_CLASS_MAP` keyed by `registry_key`.

Important behavior:

- read-only objects get `http_method_names = ["get", "head", "options"]`
- writable objects use the normal NetBox model viewset behavior
- custom actions are implemented by subclassing the generated viewset and replacing the relevant entry in `VIEWSET_CLASS_MAP`

`netbox_rpki/api/urls.py` registers every API object through the NetBox router using `spec.api.basename`.

#### GraphQL generation

`netbox_rpki/graphql/filters.py` generates filter classes and exposes `GRAPHQL_FILTER_CLASS_MAP`.

`netbox_rpki/graphql/types.py` generates types and exposes `GRAPHQL_TYPE_CLASS_MAP`.

`netbox_rpki/graphql/schema.py` generates the query type and exposes `GRAPHQL_FIELD_NAME_MAP` so tests can assert stable public field names.

Important behavior:

- GraphQL field names are explicit metadata, not derived from model names
- the plugin GraphQL package must continue to re-export `schema` from `netbox_rpki/graphql/__init__.py`
- stable public field names matter more than saving a few metadata lines

### Rich detail pages versus simple generated detail pages

There are two detail-view paths.

Use the simple generated path when:

- a straight field list is enough
- field ordering can follow `spec.api.fields`
- no curated related tables are needed
- no prefilled add actions are needed
- no custom rendering beyond relation links and URL fields is needed

Use `netbox_rpki/detail_specs.py` when:

- the object is a top-level workflow or dashboard page
- related tables are part of the main value of the page
- you need custom field ordering
- you need action buttons that prefill child forms
- a field should render as code or with special formatting

Do not force every object into the rich-detail system. Most objects should stay simple.

Also do not rely on old assumptions about NetBox defaults. Generated detail pages now explicitly control their action buttons because inherited defaults caused broken links on read-only surfaces.

### Model-side action URL resolution

`netbox_rpki/models.py` attaches `_get_action_url` to concrete plugin `NetBoxModel` subclasses. That helper first tries registry-aware route names and only falls back to NetBox's generic view-name resolver if the registry route is not available.

This matters whenever public route names differ from model names.

Implications:

- every model that participates in plugin surfaces should have a correct registry entry
- route slugs and API basenames must be right before you trust action URLs
- missing or wrong registry metadata will surface as incorrect add, edit, delete, changelog, or API links

### Adding a new model: required wiring

This is the checklist to follow when you add a new data-model object.

#### Step 1: add the model explicitly

Add the Django model in `netbox_rpki/models.py`.

Also add or confirm:

- `Meta.ordering` if needed
- `__str__`
- `get_absolute_url`
- any validation or clean methods
- any managers or queryset behavior
- the migration

Do not dynamically generate Django models.

#### Step 2: decide whether the model belongs in the registry

Ask these questions:

- Does it need a normal list/detail page?
- Does it need add/edit/delete UI?
- Does it need a standard REST API surface?
- Does it need GraphQL exposure?
- Does it need a standard filterset, form, and table?

If yes, it belongs in `netbox_rpki/object_registry.py`.

If no, keep it explicit and local.

The default for standard object families is to use the registry.

#### Step 3: create the `ObjectSpec`

Prefer `build_standard_object_spec(...)` when the object can use the shared pattern.

Provide:

- `registry_key`
- `model`
- `class_prefix`
- `label_singular`
- `label_plural`
- `api_fields`
- `brief_fields`
- `filter_fields`
- `search_fields`
- `graphql_fields`
- optional menu metadata
- optional naming overrides
- optional read-only flags

Use a fully explicit `ObjectSpec(...)` when:

- the object has legacy path compatibility requirements
- the object predates the builder and has intentionally custom metadata
- the standard builder would obscure an important exception

#### Step 4: choose the public names deliberately

For every new object, decide whether the defaults are safe for:

- UI route names
- UI path prefixes
- API basename
- GraphQL singular field name
- GraphQL list field name

Override them in the spec when needed.

Do this up front. Do not wait for tests or runtime errors to tell you the defaults were unsafe.

#### Step 5: decide whether the object is writable or read-only

Use `ui_read_only=True` when the object should not expose add, edit, clone, or delete surfaces.

Use `api_read_only=True` when the object should not expose create, update, partial-update, or delete through the REST API.

When `ui_read_only=True`, the shared builder omits:

- the generated form metadata
- edit view class generation
- delete view class generation
- add buttons in navigation

The generated list, detail, and row-action surfaces now honor that metadata. This is a critical contract, not an optional cosmetic hint.

Examples of current read-only reporting families include:

- `IntentDerivationRun`
- `ROAIntent`
- `ROAIntentMatch`
- `ROAReconciliationRun`
- `ROAIntentResult`
- `PublishedROAResult`
- `ImportedRoaAuthorization`
- `ROAChangePlan`
- `ProviderSnapshot`
- `ROAChangePlanItem`
- `ProviderSyncRun`

#### Step 6: decide whether it belongs in navigation

If the object should be a top-level menu item, add `navigation_group`, `navigation_label`, and `navigation_order`.

If it should not be a top-level menu item, leave navigation metadata out.

Do not fake a hidden menu entry just to get routes generated. Routes, tables, forms, and APIs do not require a menu item.

#### Step 7: decide whether it needs a rich detail page

If the generated detail page is enough, stop here.

If the object needs related tables, action buttons, custom field ordering, or code-style field rendering, add a `DetailSpec` in `netbox_rpki/detail_specs.py` and register it in `DETAIL_SPEC_BY_MODEL`.

Only top-level objects should usually get this treatment.

#### Step 8: add explicit object-specific behavior where required

The registry does not replace real behavior.

Add explicit code for things like:

- custom API actions
- service-layer orchestration
- jobs
- business validation
- computed summaries
- object-specific detail rendering helpers

Current examples:

- routing-intent profile `run` action
- provider-account `sync` action
- reconciliation-run `create_plan` action

Custom API actions belong in `netbox_rpki/api/views.py` as subclasses of the generated viewsets, plus matching tests.

#### Step 9: add test builders and scenario support

If the object participates in registry-driven surfaces, it must be constructible in shared tests.

That usually means adding or extending:

- a `create_test_*` helper in `netbox_rpki/tests/utils.py`
- scenario hooks in `netbox_rpki/tests/registry_scenarios.py`
- any read-only instance builder coverage used by surface-contract tests

If the object has special behavior, keep the special tests explicit. Do not bury meaningful behavior inside generic loops just to make the test file shorter.

#### Step 9a: avoid cross-test data collisions in shared builders

This plugin now relies heavily on shared builders in `netbox_rpki/tests/utils.py` and `netbox_rpki/tests/registry_scenarios.py`. That makes it easy to add coverage quickly, but it also creates a specific failure mode: a builder that looks correct in one focused test can still collide with rows created elsewhere in the full suite.

The most common pattern is:

- a read-only or reporting object builder returns a fixed `name`
- the generated filterset tests use `q` with a `name__icontains` search field
- another builder or scenario creates the same or nearly the same name
- the focused test passes in isolation, but the full suite fails because the filter returns multiple rows

Treat this as a real contract issue, not as random test flakiness.

Rules:

- Any shared builder used by registry-driven tests must generate unique values for every field that can participate in search or filtering.
- If a builder creates nested workflow objects, the nested object names must also be unique. It is not enough for only the top-level object to have a unique name.
- Prefer `unique_token(...)`, `uuid4()`, or explicit token parameters threaded through helper functions over hard-coded names such as `Provider Plan`, `Provider Snapshot`, or `Imported Authorization`.
- Pay special attention to `_READONLY_INSTANCE_BUILDERS` in `netbox_rpki/tests/registry_scenarios.py`. Those builders are exercised broadly by generic list, filterset, API, and GraphQL tests.
- Pay special attention to helpers that manufacture multi-row scenarios such as reconciliation matrices, change-plan matrices, and imported-provider fixture sets. These often create several related rows with repeated labels and are the easiest place to introduce collisions.
- Do not assume a focused test run is sufficient. A builder change is only safe once the full plugin suite is green.

Recommended design pattern:

- Let every shared test helper accept a name or token override.
- Derive child-object names from that same token.
- Keep search-visible fields deterministic but unique enough that unrelated tests will not match them accidentally.

When a collision does happen, debug it in this order:

1. Identify which `object_key` and filter case failed.
2. Check the failing object's `search_fields` in `netbox_rpki/object_registry.py`.
3. Inspect the corresponding shared builder in `netbox_rpki/tests/registry_scenarios.py`.
4. Inspect any nested helper in `netbox_rpki/tests/utils.py` that the builder calls.
5. Make names and other search-visible values tokenized all the way down, not just at the top level.
6. Re-run the focused failing test.
7. Re-run the full plugin suite.

#### Step 10: update documentation

If the object changes user-facing functionality, update the relevant docs at the same time.

Typical places:

- `README.md`
- `CHANGELOG.md`
- `TEST_SUITE_PLAN.md` when the new surface changes the intended coverage inventory
- the Sphinx docs under `docs/` when user-facing documentation is affected

### Adding specific categories of objects

#### Writable top-level object

Use the standard builder with writable defaults.

Expected result:

- list page
- detail page
- add page
- edit page
- delete page
- menu add button if the object has navigation metadata
- standard REST CRUD
- GraphQL type and query fields

#### Read-only reporting object

Use:

- `ui_read_only=True`
- `api_read_only=True`
- `show_add_button=False`

Expected result:

- list page still exists
- detail page still exists
- no add page
- no edit page
- no delete page
- no clone action
- no row edit/delete actions
- no bogus add button or `/None` link
- REST API is read-only unless you add a deliberate custom action

#### Supporting relation object

If the object is useful as a routed and queryable entity but should not clutter the menu, keep it in the registry with no navigation metadata.

Examples in the plugin include assignment and supporting relation models that are real objects but not top-level menu entries.

#### Object needing stable public names different from the model name

Keep the model name explicit and safe for Django and NetBox internals, then override the public names in the spec.

This is the pattern for `RpkiProviderAccount`.

Do not rename the model just to get a prettier slug.

### Testing and the definition of green

The plugin now treats surface contracts as part of correctness.

"Green" does not mean only that a broad test command passed. It also means the generated surfaces actually match the registry contract.

At minimum, a new or changed object family must prove:

- list-view actions match whether the object is creatable
- detail-view actions match whether the object is editable and deletable
- table row-action menus match whether edit and delete routes exist
- API methods match read-only versus writable intent
- custom actions are exposed only where intended
- GraphQL fields are registered with the intended stable names
- the object can be built in shared scenario-driven tests

Registry-wide contract coverage already lives in:

- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_graphql.py`
- `netbox_rpki/tests/registry_scenarios.py`

Do not add a new registry object and skip the contract tests. That is how false greens happen.

#### Required verification habits

- Run focused tests while iterating.
- Run the full plugin suite before claiming the work is done.
- Use non-interactive test commands only.
- Treat browser coverage as a separate confirmation lane, not as a substitute for Python-level contract tests.

Known-good full-suite command:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput netbox_rpki.tests
```

Focused contract command used during this refactor:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
    netbox_rpki.tests.test_forms \
    netbox_rpki.tests.test_filtersets \
    netbox_rpki.tests.test_tables \
    netbox_rpki.tests.test_urls \
    netbox_rpki.tests.test_navigation \
    netbox_rpki.tests.test_graphql
```

For local development and browser testing, prefer the wrappers in `devrun/`:

- `./dev.sh start`
- `./dev.sh status`
- `./dev.sh seed`
- `./dev.sh e2e`
- `./dev.sh stop`

### Lessons learned

These are not abstract style preferences. They were learned by breaking the plugin and then fixing the root cause.

- Do not overload one identifier to serve as registry key, URL stem, API basename, and GraphQL field name.
- Do not assume NetBox defaults are safe for generated read-only objects. Explicitly control list actions, detail actions, menu buttons, and row-action menus.
- Structural smoke coverage is not enough. Surface-contract tests are required.
- Public names must be stable and explicit.
- Generated code should be inspectable and boring. Stable named classes and exported maps are better than clever metaprogramming.
- Rich detail pages should be reserved for objects that genuinely need curated related tables or action buttons.
- Compatibility shims must be deliberate and narrow. Preserve public URLs intentionally rather than by accident.
- Keep business logic out of surface metadata.
- Do not name plugin models after existing NetBox core models. Collisions can show up in generated reverse accessors, GraphQL types, and other derived names even if routes are different.
- The plugin GraphQL package must continue to export `schema`; GraphQL registration depends on that package-level contract.
- Browser tests are useful, but they do not replace registry-wide Python contract tests.
- Use non-interactive test commands. Interactive `manage.py test` prompts are friction, not validation.
- Keep source checkouts on the Linux filesystem and use the existing WSL-native `devrun/` workflow instead of ad hoc environment setup.
- When functionality changes, update the docs in the same slice. Code and documentation drifting apart is how future contributors reintroduce fixed bugs.

### Practical decision rules

When you are unsure how to add something, follow these defaults:

- Add the model and migration explicitly.
- Put standard surfaces in the registry.
- Keep custom workflow logic explicit.
- Use explicit public naming metadata early.
- Mark reporting objects read-only in both UI and API metadata.
- Add a rich detail spec only when the simple generated detail page is insufficient.
- Extend shared registry-driven tests in the same change.
- Do not call work complete until the full plugin suite and the surface-contract expectations are both green.

## Deploying

A reminder for the maintainers on how to deploy.

Make sure all your changes are committed, the changelog is updated, and the docs build and test suite pass.

1. Push changes to `main` to publish the Sphinx documentation site to GitHub Pages.
2. Create and push a release tag such as `v0.1.6` to build the package, publish it to PyPI, sign the artifacts, and create the GitHub release.
3. Use the manual `Publish Release Artifacts` workflow with the `testpypi` target when you want a TestPyPI dry run before cutting a release tag.
