# Priority 7: Deeper NetBox Binding and Service Context — Maturity Plan

**Created:** April 14, 2026
**Status:** Planned execution track for moving Priority 7 from partially complete to mostly complete
**Depends on:** Existing routing-intent profile, rule, template, binding, exception, and bulk-run substrate already landed
**Out of scope:** External telemetry overlays, provider-publication reporting, and a full service-inventory system inside the plugin

---

## 1. Purpose

This document defines the remaining implementation work needed to move backlog Priority 7
from **Partially complete** to **Mostly complete**.

The current repository already has a usable first-wave intent engine:

- `RoutingIntentProfile` selector-based scoping over prefixes and ASNs
- `RoutingIntentRule` and `RoutingIntentTemplateRule` matching for tenant, VRF, site, region, role, tag, and custom-field context
- `RoutingIntentTemplateBinding` for reusable policy application and regeneration
- `RoutingIntentException` and `ROAIntentOverride` for scoped exceptions and operator overrides
- derived `ROAIntent` rows that already persist tenant, VRF, site, and region scope on emitted intent

Priority 7 is therefore not a greenfield intent-policy problem.
The remaining gap is that the plugin still lacks a coherent way to express policy in deeper operating context such as provider, circuit, exchange, or reusable service grouping.

The target is not to reproduce all of NetBox inside the plugin.
The target is to make routing-intent policy legible and reusable in the operating dimensions network teams actually use when they ask:

1. which customer or tenant this applies to
2. which routing domain or site context it lives in
3. which service or service group it belongs to
4. which provider, circuit, or exchange relationship it depends on
5. how profile-level and template-level policy should inherit and compose across those contexts

---

## 2. Current State

Priority 7 is partially implemented through the routing-intent subsystem.

### Landed substrate

| Capability | Current state |
|-----------|---------------|
| Profile scoping | `RoutingIntentProfile` already supports prefix and ASN selector queries |
| Rule matching | `RoutingIntentRule` and `RoutingIntentTemplateRule` already match on tenant, VRF, site, region, role, tag, and custom-field expressions |
| Derived scope persistence | `ROAIntent` already stores `scope_tenant`, `scope_vrf`, `scope_site`, and `scope_region` |
| Reuse | templates, bindings, regeneration logic, exceptions, and bulk runs already exist |
| Operator surfaces | object registry, detail specs, filters, tables, API, and tests already cover the first routing-intent implementation wave |

### What still keeps Priority 7 open

The backlog end state is broader than the currently landed scope.

Observed gaps in the current implementation:

- no first-class context binding for provider, circuit, exchange, or reusable service grouping
- selector strings are useful but too implicit for operator-scale service-context modeling
- inheritance semantics are still shallow: profile selectors, local rules, template rules, bindings, exceptions, and overrides compose, but the composition contract is not yet explicit enough for larger estates
- the plugin can persist site and region context on emitted intent, but cannot yet explain intent membership in higher-order service groupings
- there is no stable read-only summary contract that tells an operator why an intent belonged to a given service-context slice

---

## 3. Definition Of "Mostly Complete"

Priority 7 should move to **Mostly complete** once the plugin can do all of the following:

1. express routing-intent policy in first-class service-context terms beyond tenant, VRF, site, and region
2. support reusable grouping so operators can author policy for sets of prefixes or services without hand-maintaining raw selector queries everywhere
3. define and expose a clear inheritance order across profile, group, template, binding, local rule, exception, and override layers
4. persist enough derived context on emitted intent to explain why a prefix matched a given policy slice
5. expose the above consistently across UI, REST/API, and focused tests

This threshold intentionally does **not** require:

- a full CMDB or service-catalog replacement inside the plugin
- every possible NetBox object relationship in the first wave
- provider-side apply logic changing based on deep service context

---

## 4. Architectural Decisions

These decisions should be treated as resolved for the first maturity wave unless implementation evidence forces a change.

| ID | Decision |
|----|----------|
| AD-1 | Priority 7 should build on the existing routing-intent object family rather than introducing a second parallel policy engine. |
| AD-2 | New service-context support should be explicit and model-driven where operators need stable reuse or reporting. Raw selector strings remain useful, but they should not be the only expression mechanism for deeper context. |
| AD-3 | The first wave should introduce a small number of reusable context objects rather than binding directly to every NetBox model ad hoc. |
| AD-4 | Derived intent explanation matters as much as rule matching. Any new context dimension must be reflected in emitted summaries and operator drill-down. |
| AD-5 | Inheritance must stay deterministic and testable. The implementation should define one precedence order and reuse it everywhere. |
| AD-6 | Provider, circuit, exchange, and service context should be additive selectors for intent derivation, not approval gates in the first wave. |

---

## 5. Proposed Model Direction

The current gap is not best solved by adding many more `match_*` fields directly onto every existing rule object.

The recommended first-wave expansion is to add a small service-context layer that the routing-intent engine can resolve into concrete prefix membership.

### 5.1 `RoutingIntentContextGroup`

Purpose:
represent a reusable named operating-context group for one organization.

Suggested responsibilities:

- group prefixes or policy targets by service meaning, not just by raw selector syntax
- act as the reusable anchor for provider, circuit, exchange, role, or custom taxonomy membership
- support profile- and template-level reuse

Suggested fields:

- `organization`
- `name`
- `enabled`
- `context_type`
  - examples: `service`, `provider_edge`, `transit`, `ix`, `customer`, `backbone`
- `description`
- `priority`
- `summary_json`

This should stay generic enough to avoid a model explosion, but explicit enough to support durable reuse and reporting.

### 5.2 `RoutingIntentContextCriterion`

Purpose:
define how a context group selects or matches operating context.

Suggested first-wave criteria families:

- tenant
- VRF
- site
- region
- prefix role
- tag
- custom-field expression
- provider account
- circuit provider
- circuit
- provider network or exchange endpoint where NetBox relationships make that practical

Suggested fields:

- `context_group`
- `criterion_type`
- direct foreign keys where stable and practical
- fallback `match_value`
- `enabled`
- `weight`

The point is to avoid burying all service-context semantics inside opaque query strings.

### 5.3 `RoutingIntentProfile` and rule/binding links

Recommended additions:

- optional `parent_profile` or an equivalent lightweight inheritance pointer
- optional many-to-many or ordered relation from profile to `RoutingIntentContextGroup`
- optional binding or rule targeting by context group

The first wave only needs enough inheritance to support “base profile plus service-context refinements”.
Do not implement arbitrary multi-parent policy graphs.

### 5.4 Derived intent reporting fields

The emitted `ROAIntent` row should gain enough summary metadata to explain service-context membership.

Recommended additions:

- stable summary keys in `explanation` or a new `summary_json`
- related context-group identifiers or labels
- rule-source trace data showing whether membership came from profile selectors, context groups, template bindings, or local rules

Prefer explicit derived summary fields over free-form explanation text alone.

---

## 6. Proposed Work Slices

### Slice A — Service-context domain model and matching substrate

**Goal**

Introduce a minimal but explicit model layer for reusable service-context grouping.

**Scope**

- add `RoutingIntentContextGroup`
- add `RoutingIntentContextCriterion`
- register CRUD surfaces for both objects
- add detail/table/filter/API coverage through the existing registry-driven patterns
- define first-wave supported criterion families and document which NetBox relationships are in scope now

**Initial support target**

The first wave should cover at least:

- tenant
- VRF
- site
- region
- role
- tag
- custom-field expression
- provider-account adjacency
- circuit or circuit-provider context where a prefix-to-circuit linkage can be resolved conservatively

If exchange linkage is not robust enough for the first slice, include it as a criterion family placeholder and defer full matching to a follow-on slice.

**Deliverables**

- new context-group models and migrations
- registry, forms, filters, tables, serializers, and detail specs
- tests for model validation and basic object-surface wiring

### Slice B — Compile-time inheritance and precedence contract

**Goal**

Make profile, group, template, binding, local rule, exception, and override precedence explicit and deterministic.

**Scope**

- formalize the routing-intent precedence order in `services/routing_intent.py`
- decide whether a lightweight `parent_profile` relationship is necessary for the first wave
- allow profiles and template bindings to target context groups explicitly
- persist summary metadata describing which layers contributed to the final decision

**Recommended precedence**

1. profile selectors define the outer candidate set
2. context groups narrow or label operating-context subsets
3. template bindings contribute reusable baseline policy
4. local profile rules refine or override template-derived policy
5. approved exceptions adjust scoped behavior
6. explicit overrides remain the last operator escape hatch

This ordering matches the current mental model and keeps the current engine recognizable.

**Deliverables**

- service-layer refactor for explicit precedence
- context-aware compile summary contract
- focused tests proving deterministic inheritance and override behavior

### Slice C — Derived-intent explanation and reporting

**Goal**

Make service-context membership explainable from emitted intent, not only inferable from rule configuration.

**Scope**

- enrich emitted `ROAIntent` rows with context-group or source-trace summary data
- expose service-context membership on detail, table, and API surfaces
- add read-only helper summaries for profiles and bindings showing:
  - matched context groups
  - unmatched or ambiguous groups
  - compilation warnings
  - derived prefix counts by context type
- ensure bulk runs and regeneration views surface context-aware summaries instead of only raw counts

**Deliverables**

- updated derivation summaries
- UI/API projection of context membership
- tests for explanation contract and summary payloads

### Slice D — Provider, circuit, and exchange-aware binding expansion

**Goal**

Close the biggest remaining backlog gap by extending the first-wave context engine into topology and service-provider dimensions.

**Scope**

- implement conservative provider-context resolution using existing provider-account and provider-import data where relevant
- implement circuit-aware matching where a prefix can be tied to a circuit termination, provider, or tagged service edge through NetBox data
- implement exchange-aware grouping only where a clear NetBox relationship exists; otherwise keep exchange as a group taxonomy rather than unreliable automatic inference
- add explicit warnings when requested context cannot be resolved from current NetBox data

**Important guardrail**

Do not fake precision.
When provider, circuit, or exchange linkage is ambiguous, the system should emit warnings and skip the match rather than silently guessing.

**Deliverables**

- routing-intent matcher support for the new criterion families
- warning and summary coverage for unresolved context
- focused service tests for positive and ambiguous matches

---

## 7. Suggested Execution Order

Recommended order:

1. **Slice A** — create the reusable context model layer
2. **Slice B** — formalize precedence and inheritance on top of it
3. **Slice C** — project the resulting context trace into operator reporting
4. **Slice D** — finish the deeper provider/circuit/exchange binding slice

Slices C and D can overlap after Slice B lands.
If implementation pressure is high, exchange-aware matching can remain narrower than provider and circuit matching while still meeting the “Mostly complete” threshold.

---

## 8. Verification Strategy

Each slice should end with focused verification before moving on.

### Test emphasis

- `netbox_rpki.tests.test_routing_intent_services`
- `netbox_rpki.tests.test_models`
- `netbox_rpki.tests.test_forms`
- `netbox_rpki.tests.test_filtersets`
- `netbox_rpki.tests.test_tables`
- `netbox_rpki.tests.test_detail_specs`

### Minimum verification outcomes

- context-group membership resolves deterministically for supported criteria
- profile and template inheritance stays stable across reruns and regeneration
- emitted intents persist enough context summary to explain membership decisions
- ambiguous provider/circuit/exchange context produces warnings rather than silent misclassification
- UI and API surfaces expose the same context meaning consistently

---

## 9. Exit Criteria

Priority 7 should be updated to **Mostly complete** once all of the following are true:

- reusable service-context groups exist and are operator-manageable
- routing-intent derivation can bind policy to deeper context than tenant, VRF, site, and region alone
- precedence across profile, group, template, binding, exception, and override layers is explicit and test-covered
- emitted intent and related summaries explain service-context membership clearly
- provider, circuit, and at least a conservative first-wave exchange or exchange-taxonomy model are supported without relying only on raw selector strings

At that point, any remaining Priority 7 work should be treated as refinement:

- broader NetBox object coverage
- richer topology inference
- deeper visualization or reporting polish
- tighter integration with future ASPA and external-overlay workflows
