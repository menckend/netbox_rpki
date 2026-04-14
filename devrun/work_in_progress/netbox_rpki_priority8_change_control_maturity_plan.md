# Priority 8: Change Control and Auditability — Maturity Plan

**Created:** April 14, 2026
**Status:** Planned execution track for moving Priority 8 from partially complete to mostly complete
**Depends on:** Existing ROA and ASPA approval, apply, rollback, lint, and simulation substrate already landed
**Out of scope:** External alerting, external validator evidence, and a general-purpose enterprise CAB platform inside the plugin

---

## 1. Purpose

This document defines the remaining implementation work needed to move backlog Priority 8
from **Partially complete** to **Mostly complete**.

The current repository already has substantial change-control coverage:

- ROA and ASPA change plans with preview, approval, apply, and provider execution audit
- governance metadata on plans and approval records
- optional dual approval with distinct secondary approver
- provider-backed rollback bundles for ROA and ASPA
- typed routing-intent exceptions with explicit approval state

Priority 8 is therefore no longer missing foundational approval workflow.
The remaining gap is maturity work in two areas:

1. richer publication-state semantics after approval and apply
2. broader extension of the governance contract beyond the current ROA plan, ASPA plan, and typed-exception slice

The target is not a second workflow engine.
The target is a coherent governance and audit layer that answers three practical questions:

1. what was approved, by whom, and under which governance metadata
2. what publication state that approved change is actually in now
3. which adjacent high-impact workflows also need first-class governance treatment

---

## 2. Current State

Priority 8 is materially implemented for the core provider-backed change-plan path.

### Landed substrate

| Capability | Current state |
|-----------|---------------|
| ROA plan governance | `ROAChangePlan` already supports approval metadata, dual approval, apply tracking, provider write audit, lint acknowledgement, and simulation review |
| ASPA plan governance | `ASPAChangePlan` mirrors the same approval and apply shape |
| Approval audit | `ApprovalRecord` persists approval metadata for both change-plan families |
| Provider execution audit | `ProviderWriteExecution` records preview and apply request/response plus follow-up sync linkage |
| Rollback | ROA and ASPA rollback bundles are auto-created on successful apply and support approve/apply flows |
| Exception approval | `RoutingIntentException` already has approval actions and approval timestamps |

### What still keeps Priority 8 open

The backlog’s remaining-gap text is still accurate.

Observed gaps in the current implementation:

- plan status stops at workflow state, not publication meaning
- successful provider apply and follow-up sync are recorded, but there is no normalized operator-facing publication posture such as “accepted by provider, awaiting verification”, “verified”, or “verification drift detected”
- rollback bundles exist, but plan and execution surfaces do not yet roll publication verification and rollback posture into one clear state model
- the governance contract is still concentrated on ROA plans, ASPA plans, and typed exceptions
- adjacent high-impact workflows like organization-scoped bulk intent runs still lack comparable first-class governance metadata and approval semantics

---

## 3. Definition Of "Mostly Complete"

Priority 8 should move to **Mostly complete** once the plugin can do all of the following:

1. expose a normalized publication-state contract for provider-backed change plans and rollback bundles
2. distinguish workflow state from publication verification state in UI, API, and summaries
3. show operators whether an applied plan is merely submitted, sync-verified, drifted, failed verification, or superseded by rollback
4. extend first-class governance metadata and approval semantics to at least one additional high-impact workflow family beyond change plans and typed exceptions
5. back the above with focused service, API, and view coverage

This threshold intentionally does **not** require:

- full cross-provider transactional orchestration
- external notifications or alert delivery
- governance expansion to every plugin object in the first wave

---

## 4. Architectural Decisions

These decisions should be treated as resolved for the first maturity wave unless implementation evidence forces a change.

| ID | Decision |
|----|----------|
| AD-1 | Existing `ROAChangePlan`, `ASPAChangePlan`, `ApprovalRecord`, `ProviderWriteExecution`, and rollback-bundle models remain the canonical governance substrate. Do not replace them. |
| AD-2 | Publication state must be a read-only derived contract layered on top of current workflow and sync evidence, not a second independent state machine operators update manually. |
| AD-3 | Workflow state and publication state are different concepts and should be exposed separately. `APPROVED` or `APPLIED` alone is not enough operator meaning. |
| AD-4 | The first governance-expansion target should be a workflow that already has operational blast radius and queue semantics. `BulkIntentRun` is the best first candidate. |
| AD-5 | Broader governance should stay lightweight and mirror the existing plan contract where practical: request metadata, approval metadata, optional dual approval, and audit records or summary fields are acceptable; a new workflow engine is not. |
| AD-6 | UI, REST/API, and dashboard summaries should all reuse the same publication-state helper contract. |

---

## 5. Proposed Work Slices

### Slice A — Publication-state semantics for change plans and rollback bundles

**Goal**

Add a normalized read-only publication-state contract that explains where an approved or applied workflow stands in real publication terms.

**Why this is first**

This is the biggest remaining gap in the backlog and it can be solved without changing the core approval workflow.

**Scope**

- add a dedicated helper in `services/provider_write.py` or a small adjacent reporting module
- compute publication state for ROA plans, ASPA plans, and rollback bundles from:
  - plan workflow status
  - latest provider write execution
  - follow-up sync run and follow-up snapshot
  - rollback-bundle status where present
  - existing summary and diff evidence where practical
- expose explicit states such as:
  - `draft`
  - `awaiting_secondary_approval`
  - `approved_pending_apply`
  - `apply_in_progress`
  - `apply_failed`
  - `applied_awaiting_verification`
  - `verified`
  - `verified_with_drift`
  - `verification_failed`
  - `rolled_back`

**Important guardrail**

Do not infer “verified” merely because the provider accepted a write.
Verification should depend on follow-up sync evidence and current state comparison.

**Deliverables**

- publication-state helper contract
- summary schema additions for plan detail and API payloads
- focused tests for state derivation across happy, failed, drifted, and rollback paths

### Slice B — Publication-state and governance reporting surfaces

**Goal**

Project the new publication-state contract into the operator surfaces that already exist.

**Scope**

- add publication-state fields to change-plan, rollback-bundle, and provider-write-execution detail surfaces
- enrich dashboard and aggregate summaries with:
  - plans awaiting verification
  - plans with verification drift
  - rollback bundles available but not yet approved
  - rollback bundles applied
- add list filters and table columns for publication-state posture
- expose the same semantics via API serializers rather than leaving operators to interpret timestamps and raw JSON

**Deliverables**

- updated detail specs, tables, filters, and serializers
- dashboard summary extensions
- focused tests for UI/API payload consistency

### Slice C — Governance expansion to bulk intent runs

**Goal**

Extend the governance contract beyond change plans and typed exceptions to the next most consequential operator workflow.

**Why `BulkIntentRun`**

It already represents a first-class organization-scoped workflow with wide blast radius.
It can generate multiple derivations, reconciliations, and change plans across many scopes, but today it does not carry governance metadata comparable to change plans.

**Scope**

- add first-class governance metadata to `BulkIntentRun`, for example:
  - `ticket_reference`
  - `change_reference`
  - `maintenance_window_start`
  - `maintenance_window_end`
  - `approved_at`
  - `approved_by`
  - optional `requires_secondary_approval`
  - optional `secondary_approved_at`
  - optional `secondary_approved_by`
- decide whether approval should gate execution for bulk runs in the first wave
  - recommended: yes for organization-scoped queued runs
  - keep ad hoc test helpers and internal utility paths lightweight
- record who requested the bulk run and what resulting change plans were spawned under that governance umbrella
- propagate governance references into bulk-run summary payloads and scope-result summaries

**Important constraint**

Do not retroactively govern every low-level template-regeneration helper in this slice.
The goal is to govern the high-blast-radius bulk workflow first.

**Deliverables**

- `BulkIntentRun` governance fields and validation
- approval and optional secondary-approval workflow for bulk runs
- detail/API/reporting coverage for the new governance metadata
- focused tests for governance gating and propagation

### Slice D — Governance roll-up and audit trace consolidation

**Goal**

Make it easier to answer governance questions across object families without manually visiting each object detail page.

**Scope**

- add normalized audit-summary helpers for:
  - change plans
  - rollback bundles
  - bulk intent runs
  - routing-intent exceptions
- expose roll-ups on organization or operations-dashboard surfaces such as:
  - awaiting approval
  - awaiting secondary approval
  - approved pending execution
  - applied pending verification
  - failed
  - rollback available
- decide whether the first wave needs a lightweight shared “governance summary” serializer block for all governed workflow objects

**Recommended shape**

Keep this read-only and summary-oriented.
Do not introduce a polymorphic governance base model unless implementation simplicity clearly justifies it.

**Deliverables**

- reusable governance-summary helper
- dashboard or org-scope roll-up sections
- focused tests for aggregate counts and visibility

---

## 6. Suggested Execution Order

Recommended order:

1. **Slice A** — define publication-state semantics first
2. **Slice B** — expose those semantics across current plan and rollback surfaces
3. **Slice C** — extend governance to bulk intent runs
4. **Slice D** — consolidate governed-workflow roll-ups and audit reporting

Slices B and C can overlap after Slice A lands.
Slice D should finalize after the first additional governed workflow family is in place.

---

## 7. Verification Strategy

Each slice should end with focused verification before moving on.

### Test emphasis

- `netbox_rpki.tests.test_provider_write`
- `netbox_rpki.tests.test_multi_stage_approval`
- `netbox_rpki.tests.test_rollback_bundle`
- bulk-intent workflow tests
- detail/API/dashboard tests for summary exposure

### Minimum verification outcomes

- publication-state derivation stays correct across draft, approved, applied, failed, verified, drifted, and rollback scenarios
- workflow-state changes do not regress existing approve/apply behavior
- bulk intent governance metadata is enforced consistently where the first wave requires approval
- aggregate governance summaries match underlying object state

---

## 8. Exit Criteria

Priority 8 should be updated to **Mostly complete** once all of the following are true:

- provider-backed change plans and rollback bundles expose a normalized publication-state posture
- operators can distinguish approval state, execution state, and verification state without reading raw payloads
- dashboard and API surfaces summarize governance and publication posture consistently
- at least one additional high-impact workflow family beyond ROA plans, ASPA plans, and typed exceptions has first-class governance metadata and approval semantics
- no unresolved design question remains about how publication verification should be represented for the first wave

At that point, any remaining Priority 8 work should be treated as refinement:

- broader governed workflow coverage
- richer exports
- cross-provider policy variation
- future alerting and escalation hooks
