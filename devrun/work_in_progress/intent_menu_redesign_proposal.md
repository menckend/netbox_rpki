# Intent Menu Redesign Proposal

## Problem

The `"Intent"` navigation group currently contains **49 menu items**, making it the largest
group by a large margin and effectively unusable as a navigation aid.  Users must scroll a
very long list to reach unrelated objects (e.g. "Routing Intent Rules" and "Imported
Certificate Observations" live side-by-side).

## Constraint: No Hierarchical Sub-Groups in NetBox

NetBox v4.5.7 `PluginMenu` groups are flat.  `PluginMenu(label, groups)` accepts a list
of `(label, items)` tuples where each becomes a `MenuGroup(label, items)` — a flat label
+ flat list of `MenuItem`s.  There is no nesting or accordion within a group.

The only viable structural fix is **splitting "Intent" into multiple peer top-level
groups**.

---

## Current State

| Order | Label | Writable? |
|------:|-------|-----------|
| 10 | Routing Intent Profiles | ✓ |
| 15 | Routing Intent Context Groups | ✓ |
| 16 | Routing Intent Context Criteria | ✓ |
| 17 | Routing Intent Policy Bundles | ✓ |
| 20 | Routing Intent Rules | ✓ |
| 25 | Routing Intent Templates | ✓ |
| 26 | Routing Intent Template Rules | ✓ |
| 27 | Routing Intent Template Bindings | ✓ |
| 28 | Routing Intent Exceptions | ✓ |
| 30 | ROA Intent Overrides | ✓ |
| 35 | Bulk Intent Runs | read-only |
| 36 | Bulk Intent Scope Results | read-only |
| 40 | Intent Derivation Runs | read-only |
| 50 | ROA Intents | read-only |
| 60 | ROA Intent Matches | read-only |
| 65 | ASPA Intents | ✓ |
| 66 | ASPA Intent Matches | read-only |
| 67 | ASPA Reconciliation Runs | read-only |
| 68 | ASPA Intent Results | read-only |
| 69 | Published ASPA Results | read-only |
| 70 | ROA Reconciliation Runs | read-only |
| 75 | ROA Lint Runs | read-only |
| 80 | ROA Intent Results | read-only |
| 85 | ROA Lint Findings | read-only |
| 86 | ROA Lint Acknowledgements | read-only |
| 87 | ROA Lint Suppressions | read-only |
| 90 | Published ROA Results | read-only |
| 95 | Provider Accounts | ✓ |
| 100 | Provider Snapshots | read-only |
| 101 | Provider Snapshot Diffs | read-only |
| 102 | Provider Snapshot Diff Items | read-only |
| 105 | Provider Sync Runs | read-only |
| 107 | Provider Write Executions | read-only |
| 110 | Imported ROA Authorizations | read-only |
| 112 | Imported ASPAs | read-only |
| 114 | Imported CA Metadata | read-only |
| 115 | Imported Parent Links | read-only |
| 116 | Imported Child Links | read-only |
| 117 | Authored CA Relationships | ✓ |
| 117 | Imported Resource Entitlements | read-only |
| 118 | Imported Publication Points | read-only |
| 119 | Imported Signed Objects | read-only |
| 120 | Imported Certificate Observations | read-only |
| 120 | ROA Change Plans | read-only |
| 121 | ASPA Change Plans | read-only |
| 125 | ROA Validation Simulation Runs | read-only |
| 126 | ROA Validation Simulation Results | read-only |
| 130 | ROA Change Plan Items | read-only |
| 131 | ASPA Change Plan Items | read-only |

**Total: 49 items**

---

## Proposed Split: 1 section → 5 sections

### Section A — "Intent" (keep label, 11 items)

The writable, user-maintained configuration objects.  These are the things operators
actually *author*.

| registry_key | Label | Notes |
|---|---|---|
| routingintentprofile | Routing Intent Profiles | |
| routingintentcontextgroup | Routing Intent Context Groups | |
| routingintentcontextcriterion | Routing Intent Context Criteria | |
| routingintentpolicybundle | Routing Intent Policy Bundles | |
| routingintentrule | Routing Intent Rules | |
| routingintenttemplate | Routing Intent Templates | |
| routingintenttemplaterule | Routing Intent Template Rules | |
| routingintenttemplatebinding | Routing Intent Template Bindings | |
| routingintentexception | Routing Intent Exceptions | |
| roaintentoverride | ROA Intent Overrides | |
| aspaintent | ASPA Intents | writable, currently lost mid-list |

---

### Section B — "Derivation" (new label, 6 items)

The derivation pipeline: bulk runs, scope results, and the derived ROA/ASPA intent
objects produced by those runs.

| registry_key | Label |
|---|---|
| bulkintentrun | Bulk Intent Runs |
| bulkintentrunscoperesult | Bulk Intent Scope Results |
| intentderivationrun | Intent Derivation Runs |
| roaintent | ROA Intents |
| roaintentmatch | ROA Intent Matches |
| aspaintentmatch | ASPA Intent Matches |

---

### Section C — "Reconciliation" (new label, 10 items)

Reconciliation runs, intent results, published results, and the lint pipeline.

| registry_key | Label |
|---|---|
| roareconciliationrun | ROA Reconciliation Runs |
| aspareconciliationrun | ASPA Reconciliation Runs |
| roaintentresult | ROA Intent Results |
| aspaintentresult | ASPA Intent Results |
| publishedroaresult | Published ROA Results |
| publishedasparesult | Published ASPA Results |
| roalintrun | ROA Lint Runs |
| roalintfinding | ROA Lint Findings |
| roalintacknowledgement | ROA Lint Acknowledgements |
| roalintsuppression | ROA Lint Suppressions |

Note: `ROALintRuleConfig` is already in the separate `"Linting"` group — leave it there.

---

### Section D — "Provider" (new label, 12 items)

Everything touching the RPKI provider: accounts, snapshots, syncs, write executions, and
the change-plan / simulation workflow that produces writes.

| registry_key | Label |
|---|---|
| rpkiprovideraccount | Provider Accounts |
| providersnapshot | Provider Snapshots |
| providersnapshotdiff | Provider Snapshot Diffs |
| providersnapshotdiffitem | Provider Snapshot Diff Items |
| providersyncrun | Provider Sync Runs |
| providerwriteexecution | Provider Write Executions |
| roachangeplan | ROA Change Plans |
| aspachangeplan | ASPA Change Plans |
| roachangeplanitem | ROA Change Plan Items |
| aspachangeplanitem | ASPA Change Plan Items |
| roavalidationsimulationrun | ROA Validation Simulation Runs |
| roavalidationsimulationresult | ROA Validation Simulation Results |

Rationale: change plans, write executions, and simulation runs are all part of the
provider-write workflow and naturally belong alongside the provider data they act on.

---

### Section E — "Imported" (new label, 10 items)

Read-only mirror data imported from provider snapshots.  These are rarely navigated
directly but need to exist for filtering and inspection.

| registry_key | Label |
|---|---|
| importedroaauthorization | Imported ROA Authorizations |
| importedaspa | Imported ASPAs |
| importedcametadata | Imported CA Metadata |
| importedparentlink | Imported Parent Links |
| importedchildlink | Imported Child Links |
| authoredcarelationship | Authored CA Relationships |
| importedresourceentitlement | Imported Resource Entitlements |
| importedpublicationpoint | Imported Publication Points |
| importedsignedobject | Imported Signed Objects |
| importedcertificateobservation | Imported Certificate Observations |

---

## Result Summary

| Before | After | Items |
|---|---|---|
| Intent (49) | Intent | 11 |
| | Derivation | 6 |
| | Reconciliation | 10 |
| | Provider | 12 |
| | Imported | 10 |

49 items across 1 section → 49 items across 5 sections.
All other groups (Resources, Trust, Objects, Validation, Linting, Delegated, Governance,
IRR) are unchanged.

Total top-level groups: 9 → 13.

---

## Implementation Notes

### What changes

1. **`object_registry.py`**: Update `navigation_group=` on the 38 entries being moved.
   The 11 items staying in `"Intent"` are unchanged.
2. **`navigation.py`**: No structural changes needed.  `get_navigation_groups()` already
   assembles groups dynamically from the registry.
3. **`tests/test_navigation.py`** and **`tests/registry_scenarios.py`**: The
   `EXPECTED_NAVIGATION_GROUPS` constant is computed at import time from
   `get_navigation_groups()`, so no test fixtures need manual edits — the tests will
   automatically pick up the new group names.
4. **`tests/test_navigation.py` `test_default_navigation_exports_top_level_menu`**:
   Verifies group labels.  This will continue to pass as long as the registry generates
   the same labels the test expects dynamically.

### Navigation order within each new section

Keep the existing `navigation_order` values as-is.  They still produce correct relative
ordering within each new section because the values were chosen per-section anyway (they
cluster as 10–30, 35–40, 50–69, 67–90, 95–120+, 110–120 respectively, which maps cleanly
to the proposed sections).

### No hierarchical sub-groups

As noted above, NetBox v4.5.7 does not support sub-groups within a `PluginMenu` group.
This design does not attempt to work around that limit.  If a future NetBox version adds
collapsible groups or nested navigation, the 5 sections could be folded back under a
single "Intent" parent.

---

## Open Questions / Trade-offs

- **"Provider" section overlap**: `Provider Accounts` and `Provider Sync Runs` are
  already surfaced via the Operations dashboard and the `Resources` group's "Operations"
  link.  Moving them into a dedicated "Provider" section makes them doubly-reachable,
  which is fine, but if there is a desire to consolidate, `Provider Accounts` could be
  promoted to the existing `Resources` group instead.

- **Section count**: 13 total groups is on the high end for a sidebar menu.  If that
  feels like too many, `Derivation` (6 items) and `Reconciliation` (10 items) could be
  merged into a single `"Pipeline"` section (16 items), bringing the total back to 12.

- **"Imported" label**: The `Imported *` objects are low-traffic inspection objects.
  An alternative label is `"Snapshot Data"` or `"Provider Mirror"` to make clear these
  are passively-populated read-only mirrors.
