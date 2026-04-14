# netbox-rpki Surface Contract Checklist

## Purpose

Use this checklist for any change that touches one or more of the following:

- object registry metadata
- generated UI views or tables
- generated API viewsets or routes
- GraphQL schema generation
- custom per-object API actions
- route/action URL resolution

The goal is simple: a green suite must mean that every exposed object surface still matches the contract implied by its spec.

---

## Release Gate

Do not describe the plugin as "fully green" after one of these refactors unless all of the following are true:

1. Registry-wide list-view surface tests pass.
2. Registry-wide detail-view surface tests pass.
3. Registry-wide row-action contract tests pass.
4. Registry-wide API method-contract tests pass.
5. Registry-wide GraphQL minimal queryability tests pass.
6. Custom per-object API action tests pass for route presence, allowed verbs, and permission enforcement.
7. The full plugin suite passes.
8. When routing-intent operator workflows changed, the focused routing-intent service and operations-dashboard suites pass too.

---

## UI Contract Checks

For every exposed object type:

1. The list page loads successfully.
2. The detail page loads successfully.
3. The page never renders `/None` links.
4. The list-page controls expose `Add` only when create is supported.
5. The row-action menu exposes `Edit` and `Delete` only when those routes exist.
6. Read-only objects still expose `Changelog` where supported.
7. Related-object tables embedded in detail pages follow the same row-action rules.
8. Generated detail pages do not inherit clone/edit/delete controls for read-only objects.

---

## API Contract Checks

For every exposed object type:

1. The list route is present.
2. The detail route is present.
3. Read-only objects expose only the HTTP methods they actually support.
4. Writable objects expose create/update/delete methods only when intended.
5. Custom actions exist only on the viewsets that are meant to expose them.
6. Custom actions reject unsupported verbs.
7. Custom actions enforce the intended permission boundary.

---

## GraphQL Contract Checks

For every GraphQL-exposed object type:

1. The registered detail field name matches the object spec.
2. The registered list field name matches the object spec.
3. A minimal detail query succeeds.
4. A minimal list query succeeds.
5. The object remains reachable through the field names exported by the generated schema.

---

## Documentation Checks

If the refactor changes what the suite proves, update the following documents in the same change:

1. `devrun/work_in_progress/netbox_rpki_testing_strategy_matrix.md`
2. `devrun/work_in_progress/netbox_rpki_enhancement_backlog.md`
3. This checklist, if the contract itself changed

If the change touched routing-intent templates, bindings, typed exceptions, bulk runs, or dashboard rollups, also update:

4. `README.md`

---

## Suggested Verification Commands

Targeted surface verification:

```bash
cd /home/mencken/src/netbox_rpki/devrun
./dev.sh test contract --verbosity 1
```

Full plugin suite:

```bash
cd /home/mencken/src/netbox_rpki/devrun
./dev.sh test full --verbosity 1
```

---

## Current Meaning of "Green"

For this plugin, "green" should be read as:

"All registered objects still satisfy the generated UI/API/GraphQL surface contract, all custom actions satisfy their route/method/permission contract, routing-intent workflow regressions are covered by the focused service or dashboard suites, and the full plugin suite passes."
