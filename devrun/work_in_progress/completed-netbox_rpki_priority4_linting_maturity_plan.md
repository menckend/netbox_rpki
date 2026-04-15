# Priority 4: ROA Linting and Safety Analysis — Maturity Plan

**Created:** April 14, 2026
**Status:** Planned execution track for moving Priority 4 from partially complete to mostly complete
**Depends on:** Existing ROA linting substrate, acknowledgement workflow, suppression scopes, and ownership-context rules already landed
**Out of scope:** New provider-sync substrate, external validator overlays, and a second approval system

---

## 1. Purpose

This document defines the remaining implementation work needed to move backlog Priority 4
from **Partially complete** to **Mostly complete**.

The current repository already has the foundational linting substrate:

- persisted `ROALintRun`, `ROALintFinding`, `ROALintAcknowledgement`, `ROALintSuppression`, and `ROALintRuleConfig` models
- intent, published-state, plan-risk, and ownership-context rule families
- org-level severity and approval-impact overrides
- intent, profile, organization, and prefix suppression scopes
- change-plan approval and standalone acknowledgement flows, including `previously_acknowledged` carry-forward posture
- baseline dashboard, API, and detail-surface exposure for lint posture

Priority 4 is therefore no longer a rule-engine buildout problem.
The remaining gap is maturity work in four areas:

1. normalize how suppression and acknowledgement lifecycle state rolls up across services and surfaces
2. improve operator reporting and drill-down so users can explain why a plan is blocked, acknowledged, or suppressed without reading raw JSON
3. make suppression lifecycle easier to govern and audit at scale
4. decide and implement the minimum additional governance semantics worth adding on top of the current acknowledgement contract

The target is not a second change-control framework.
The target is a coherent linting layer that operators can trust, review, and audit across reconciliation, plan review, API, and dashboard workflows.

---

## 2. Current State

Priority 4 is already materially implemented.

### Landed substrate

| Capability | Current state |
|-----------|---------------|
| Rule engine | `netbox_rpki/services/roa_lint.py` already evaluates four lint rule families and persists findings with operator-facing explanation fields |
| Overrides | `ROALintRuleConfig` exists and is already wired into finding creation |
| Suppressions | `ROALintSuppression` already supports `INTENT`, `PROFILE`, `ORG`, and `PREFIX` scopes plus lift and expiry lifecycle fields |
| Acknowledgement posture | `build_roa_change_plan_lint_posture()` already distinguishes `blocked`, `acknowledgement_required`, `previously_acknowledged`, and `clear` |
| Approval wiring | approval and standalone acknowledgement flows already accept current plus previously acknowledged findings |
| Surface coverage | detail specs, forms, API serializers, dashboard rollups, and focused tests already cover the first implementation wave |

### What still keeps Priority 4 open

The backlog text is still accurate in one important way:
the remaining work is mostly about reporting, lifecycle visibility, and governance semantics.

Observed gaps in the current implementation:

- rollups focus on counts, but not enough on lifecycle explanation
- dashboard and aggregate views show acknowledged and suppressed totals, but not enough distinction between current, carried-forward, expiring, and lifted states
- suppression review is workflow-capable, but not yet mature as an operator reporting surface
- there is no explicit first-class contract for lint posture summaries outside the current plan-centric helper path
- the project has not yet resolved whether to stop at the current acknowledgement model or add a light policy layer for acknowledgement review expectations

---

## 3. Definition Of "Mostly Complete"

Priority 4 should move to **Mostly complete** once the plugin can do all of the following without introducing a second governance system:

1. produce a normalized lint posture summary that clearly separates active, suppressed, acknowledged, and previously acknowledged findings
2. expose suppression and acknowledgement lifecycle state through plan, run, dashboard, and API surfaces without relying on raw `details_json`
3. let operators review suppression inventory and ageing in a way that scales beyond single-finding drill-down
4. record and explain the limited governance semantics the first wave supports, including the exact meaning of carried-forward acknowledgements
5. back the above with focused tests covering reporting, posture rollups, and lifecycle transitions

This threshold intentionally does **not** require:

- a separate waiver or exception approval workflow
- cross-object policy inheritance beyond the current organization rule-config and suppression scopes
- external alerting or external validator correlation

---

## 4. Architectural Decisions

These decisions should be treated as resolved for the maturity wave unless implementation evidence forces a change.

| ID | Decision |
|----|----------|
| AD-1 | Priority 4 maturity remains additive. Reuse the current lint models, finding persistence, and approval contract rather than replacing them. |
| AD-2 | `build_roa_change_plan_lint_posture()` remains the canonical plan-approval gate, but a broader read-only summary helper should be introduced for reporting surfaces. |
| AD-3 | Suppression and acknowledgement reporting must be derived from persisted first-class fields and normalized summary keys, not from templates interpreting arbitrary `details_json` ad hoc. |
| AD-4 | The first maturity wave stops short of introducing a separate waiver model. Existing acknowledgement rows remain the operator-confirmation record. |
| AD-5 | If extra governance semantics are added, they must stay lightweight: explicit policy flags, summary fields, or lifecycle timestamps are acceptable; a new approval queue is not. |
| AD-6 | Reporting changes should cover UI, REST/API, and test contracts together. Do not land HTML-only explanations. |

---

## 5. Proposed Work Slices

### Slice A — Normalized lint posture and lifecycle summary contract

**Goal**

Create a reusable read-only summary helper that expands the current plan posture into a fuller reporting contract for both change plans and lint runs.

**Why this is first**

Most remaining gaps are presentation and auditability problems.
Those should be solved once in service code before touching dashboard, API, and detail views.

**Scope**

- add a dedicated reporting helper in `netbox_rpki/services/roa_lint.py` or a small adjacent module
- return explicit counts and identifiers for:
  - active findings
  - suppressed findings
  - acknowledged findings
  - previously acknowledged findings
  - expired suppressions affecting current findings
  - lifted suppressions relevant to current rule codes where that evidence is available
- expose per-impact and per-family counts for active and non-active findings
- include a stable explanation-oriented summary block suitable for UI and API reuse
- keep `build_roa_change_plan_lint_posture()` as the approval gate, but refactor it to delegate to the broader summary helper where practical

**Deliverables**

- normalized summary helper
- summary schema version bump
- focused unit tests for count partitioning and carry-forward state

### Slice B — Operator reporting surfaces for lint runs, plans, and dashboards

**Goal**

Surface the richer lifecycle summary in the places operators already work.

**Scope**

- enrich plan and reconciliation detail surfaces with explicit sections for:
  - active blocking findings
  - acknowledgement-required findings
  - previously acknowledged findings pending re-confirmation
  - suppressed findings, grouped by scope
- extend operations dashboard and aggregate summary payloads to carry:
  - previously acknowledged totals
  - suppressed totals by scope or impact
  - plans with expiring suppressions or carried-forward acknowledgements
- expose the same summary contract via API serializers rather than only raw related collections
- review whether lightweight list filters and table columns are needed for:
  - suppression scope
  - lifted vs active suppression
  - acknowledgement state
  - finding rule family

**Deliverables**

- updated detail specs, serializers, tables, and filters as needed
- focused tests for API and UI-adjacent summary payloads

### Slice C — Suppression inventory, lifecycle, and ageing review

**Goal**

Make suppression management auditable and reviewable at scale rather than only via create/lift actions.

**Scope**

- add better list/detail exposure for suppression lifecycle metadata:
  - effective scope target
  - active vs lifted vs expired posture
  - created, expires, and lifted timestamps
  - actor and reason fields already present on the object
- add reporting helpers or queryset annotations for:
  - active suppression count by organization
  - suppressions expiring soon
  - suppressions with no current matching findings
- determine whether the first wave should add an explicit “stale suppression” signal based on age or lack of current matches
- expose suppression inventory from organization and change-review surfaces where it helps operator review

**Deliverables**

- improved suppression list/detail/reporting coverage
- tests for lifecycle-state classification and any new filters

### Slice D — Governance semantics closure for acknowledgement lifecycle

**Goal**

Resolve the backlog’s open governance question without expanding into a second approval framework.

**Decision to implement**

Land a lightweight acknowledgement-governance contract with two parts:

1. explicit operator-facing explanation of what `previously_acknowledged` means
2. optional summary fields showing when the current plan last had lint acknowledgements recorded and whether the current run still depends on carried-forward acknowledgement state

**Scope**

- document and surface the exact semantics of carried-forward acknowledgement
- add summary fields on plan detail/API payloads such as:
  - latest lint acknowledgement timestamp
  - latest lint acknowledgement actor
  - carried-forward acknowledgement count
  - whether approval is blocked specifically by re-confirmation requirements
- decide whether a simple organization-level policy flag is warranted for future tightening
  - example: require notes when re-confirming previously acknowledged findings
  - do not add this unless implementation is trivial and testable

**Explicit non-goals**

- no separate waiver object
- no multi-stage lint-specific approval workflow
- no lint-specific ticketing integration beyond existing notes and references

**Deliverables**

- clarified governance semantics in UI/API wording
- minimal additional fields or summary contract needed to make those semantics auditable

---

## 6. Suggested Execution Order

Recommended order:

1. **Slice A** — define the reporting contract once
2. **Slice B** — project that contract into UI and API
3. **Slice C** — finish suppression lifecycle review and ageing visibility
4. **Slice D** — close the governance question with the lightest viable semantics

Slices B and C can overlap after Slice A lands.
Slice D should be finalized after Slice B makes the current acknowledgement posture visible enough to judge whether extra policy is still needed.

---

## 7. Verification Strategy

Each slice should end with focused verification before moving on.

### Test emphasis

- `netbox_rpki.tests.test_roa_lint`
- `netbox_rpki.tests.test_provider_write`
- list/detail/API tests covering new summary exposure
- dashboard or service-summary tests for aggregate rollups

### Minimum verification outcomes

- posture summary counts remain correct for active, suppressed, acknowledged, and previously acknowledged findings
- approval gating remains unchanged except where new summary semantics are intentionally exposed
- suppression lifecycle state is stable for active, expired, and lifted records
- plan, detail, and API surfaces expose the same summary meaning consistently

---

## 8. Exit Criteria

Priority 4 should be updated to **Mostly complete** once all of the following are true:

- normalized lint lifecycle summary contract exists and is reused across services
- dashboard, plan, and reconciliation surfaces explain suppression and acknowledgement posture clearly
- suppression inventory and lifecycle review are first-class operator workflows rather than isolated actions
- carried-forward acknowledgement semantics are explicit, test-covered, and auditable
- no unresolved design question remains about whether a heavier lint-governance layer is required for the first wave

At that point, any further Priority 4 work should be treated as refinement:

- extra lint rules
- export polish
- richer alerting
- future governance expansion if operators later prove the current contract insufficient
