# NetBox RPKI Plugin: ASPA Operational Support Implementation Plan

Prepared: April 13, 2026

## Purpose

This document turns backlog Priority 3 into an execution plan.

It is intentionally narrower than the main backlog and more concrete than the high-level roadmap. The goal is to define:

- the exact gaps still open for ASPA workflow support
- the implementation order that preserves the current architecture
- the file ownership and schema boundaries for each phase
- the verification gates required before the work can be considered complete

Read this together with:

- [Enhancement Backlog](netbox_rpki_enhancement_backlog.md)
- [Schema Normalization Plan](netbox_rpki_schema_normalization_plan.md)
- [Schema Normalization Decision Log](netbox_rpki_schema_normalization_decision_log.md)
- [Testing Strategy Matrix](netbox_rpki_testing_strategy_matrix.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)

## Objective

Implement first-class ASPA operational support by extending the existing ROA control-plane shape instead of creating an ASPA-only side system.

The target end state is:

1. ASPA intent already exists.
2. ASPA reconciliation already exists.
3. ASPA change planning exists.
4. ASPA provider preview, approval, and apply exist.
5. ASPA execution is auditable.
6. ASPA status is visible in UI, API, and dashboard roll-ups.
7. ASPA provider support is capability-gated at the provider-account level.
8. ASPA lint and simulation can be added later without rewriting the workflow substrate.

## Current Baseline

The repo already contains the first half of the ASPA workflow.

Implemented today:

- local ASPA inventory in `netbox_rpki/models.py`
- imported provider ASPA inventory in `netbox_rpki/models.py`
- Krill ASPA import in `netbox_rpki/services/provider_sync.py`
- provider snapshot and diff handling for imported ASPAs in `netbox_rpki/services/provider_sync_diff.py`
- ASPA intent, match, reconciliation run, and result models in `netbox_rpki/models.py`
- ASPA reconciliation services in `netbox_rpki/services/aspa_intent.py`
- ASPA command, job, API action, and organization drill-down surfaces
- ASPA detail rendering and list/detail registration through the registry surfaces

Not implemented today:

- ASPA change-plan models
- ASPA preview/approve/apply workflow
- ASPA provider write adapter
- ASPA execution audit flow comparable to ROA
- ASPA dashboard and summary roll-ups comparable to ROA
- ASPA lint and simulation
- provider-account ASPA write/read capability surfaces
- broader ASPA provider adapters beyond the current Krill import path

## Design Constraints

### 1. Stay additive first

Do not attempt a full generic rewrite of the ROA change-plan system before landing ASPA support.

The implementation should prefer:

- additive ASPA schema
- shared helper extraction where it reduces duplication immediately
- compatibility-preserving extensions to current provider capability and audit surfaces

### 2. Reuse the ROA workflow shape

The ASPA workflow should follow the same operator steps already used for ROA:

1. reconcile
2. generate plan
3. preview provider delta
4. approve
5. apply
6. resync
7. review audit trail and results

### 3. Respect the ASPA data model

ROAs are independent prefix-origin authorizations.

ASPAs are customer-AS objects with a provider set.

That means the ASPA plan model cannot simply copy ROA item semantics one-for-one. ASPA change planning must support set-level reasoning:

- create an ASPA for a customer
- withdraw an ASPA for a customer
- add provider membership
- remove provider membership
- replace one provider set with another

### 4. Keep shared surfaces authoritative

The implementation must stay aligned with the registry-based plugin contract documented in [CONTRIBUTING.md](../../CONTRIBUTING.md).

That means every phase touching a new model or operator surface must update all affected layers:

- model and migration
- service entry points
- registry metadata
- detail rendering
- REST serialization and custom actions
- GraphQL where appropriate
- UI routes and views where appropriate
- focused regression tests

## Recommended High-Level Decisions

These decisions should be treated as the default execution path unless implementation evidence shows they are too costly.

### 1. Add ASPA-specific change-plan models instead of pausing for a generic rewrite

Recommended first-wave schema:

- `ASPAChangePlan`
- `ASPAChangePlanItem`

This preserves momentum and keeps the ROA-tested workflow intact.

### 2. Generalize provider capability metadata now

The provider-account contract is currently ROA-specific. That is too narrow for Priority 3.

Add capability properties for ASPA support on `RpkiProviderAccount` in `netbox_rpki/models.py` and expose them in the provider-account serializer and related surfaces.

Recommended additions:

- `ProviderAspaWriteMode`
- `supports_aspa_write`
- `aspa_write_mode`
- `aspa_write_capability`
- optional `supports_aspa_read` if the provider capability contract is widened at the same time

### 3. Generalize approval and execution audit only as far as needed

The existing `ApprovalRecord` and `ProviderWriteExecution` objects are tied to `ROAChangePlan`.

Preferred path:

- keep the ROA change-plan flow intact
- extend those audit models additively so they can point at either ROA or ASPA plans
- use explicit exactly-one-target constraints similar to the current ASPA result models

Fallback path if that proves too disruptive:

- add `ASPAApprovalRecord` and `ASPAProviderWriteExecution` for the first wave
- defer audit-model unification to a later governance-focused phase

The preferred path is better because the backlog already frames governance as a shared control-plane concern, not a ROA-only concern.

## Scope

In scope for this plan:

- ASPA provider capability exposure
- ASPA change-plan schema
- ASPA plan generation from reconciliation runs
- Krill-backed ASPA preview and apply
- approval and provider-execution audit support for ASPA plans
- API and UI workflow parity for ASPA plans
- dashboard and summary reporting for ASPA operations
- test harness expansion for offline and mocked provider-write paths

Not in scope for this plan:

- a full generic change-plan framework for every signed-object family
- non-Krill ASPA write adapters in the first phase
- full relying-party ASPA simulation fidelity
- full validator-overlay workflows
- rollback bundles
- multi-stage approval policy

## Target Architecture After This Plan

The intended ASPA workflow stack should look like this:

1. intent layer
   - `ASPAIntent`
2. observed-state layer
   - local `ASPA`
   - imported `ImportedAspa`
3. reconciliation layer
   - `ASPAReconciliationRun`
   - `ASPAIntentResult`
   - `PublishedASPAResult`
4. change-control layer
   - `ASPAChangePlan`
   - `ASPAChangePlanItem`
   - shared or ASPA-scoped approval records
   - shared or ASPA-scoped provider write execution rows
5. provider execution layer
   - preview delta
   - apply delta
   - follow-up sync
6. reporting layer
   - detail pages
   - API custom actions
   - organization and provider-account roll-ups
   - operations dashboard attention views
7. later analysis layer
   - ASPA lint
   - ASPA simulation

## Phase Plan

### Phase 0: Capability Substrate and Decision Lock

Status:

- not started

Objective:

- make provider capability reporting ASPA-aware before adding write workflows
- lock the audit-model approach before authoring migrations

Primary files:

- `netbox_rpki/models.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/graphql/types.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/object_registry.py`
- `netbox_rpki/tests/test_models.py`
- `netbox_rpki/tests/test_api.py`

Required changes:

1. Add ASPA capability terminology beside the existing ROA write capability on `RpkiProviderAccount`.
2. Expose those properties through REST and any provider-account detail surface that currently shows ROA capability.
3. Decide whether audit rows become shared-target models now or whether the first ASPA slice gets parallel audit rows.

Recommended capability fields:

- `ProviderAspaWriteMode.UNSUPPORTED`
- `ProviderAspaWriteMode.KRILL_ASPA_DELTA` or similarly explicit mode naming
- `supports_aspa_write`
- `aspa_write_mode`
- `aspa_write_capability`

Acceptance criteria:

- provider accounts report ASPA write support without inferring from ROA support
- Krill reports ASPA support explicitly
- ARIN remains explicitly unsupported for ASPA write unless and until a real adapter exists
- model and API tests prove the provider capability contract

Verification:

- `manage.py test --keepdb --noinput netbox_rpki.tests.test_models`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_api`

### Phase 1: ASPA Change-Plan Schema

Status:

- not started

Objective:

- add the minimum schema required to carry ASPA plan generation, approval state, provider delta metadata, and operator drill-down

Primary files:

- `netbox_rpki/models.py`
- `netbox_rpki/migrations/`
- `netbox_rpki/tests/utils.py`
- `netbox_rpki/tests/test_models.py`
- `netbox_rpki/tests/registry_scenarios.py`

Recommended schema additions:

1. `ASPAChangePlan`
   - `organization`
   - `source_reconciliation_run`
   - `provider_account`
   - `provider_snapshot`
   - `status`
   - governance metadata fields matching `ROAChangePlan`
   - apply timing and actor fields matching `ROAChangePlan`
   - `summary_json`

2. `ASPAChangePlanItem`
   - `change_plan`
   - `action_type`
   - `plan_semantic`
   - `aspa_intent`
   - `aspa`
   - `imported_aspa`
   - provider-operation metadata
   - `before_state_json`
   - `after_state_json`
   - `reason`

3. Additive audit linkage
   - preferred: extend `ApprovalRecord` and `ProviderWriteExecution` to support ASPA plans
   - fallback: add ASPA-scoped analog models

Proposed concrete field set for `ASPAChangePlan`:

- `organization = ForeignKey(Organization, related_name='aspa_change_plans')`
- `source_reconciliation_run = ForeignKey(ASPAReconciliationRun, related_name='change_plans')`
- `provider_account = ForeignKey(RpkiProviderAccount, related_name='aspa_change_plans', null=True, blank=True)`
- `provider_snapshot = ForeignKey(ProviderSnapshot, related_name='aspa_change_plans', null=True, blank=True)`
- `status = CharField(choices=ASPAChangePlanStatus.choices, default=ASPAChangePlanStatus.DRAFT)`
- `ticket_reference = CharField(max_length=200, blank=True)`
- `change_reference = CharField(max_length=200, blank=True)`
- `maintenance_window_start = DateTimeField(null=True, blank=True)`
- `maintenance_window_end = DateTimeField(null=True, blank=True)`
- `approved_at = DateTimeField(null=True, blank=True)`
- `approved_by = CharField(max_length=150, blank=True)`
- `apply_started_at = DateTimeField(null=True, blank=True)`
- `apply_requested_by = CharField(max_length=150, blank=True)`
- `applied_at = DateTimeField(null=True, blank=True)`
- `failed_at = DateTimeField(null=True, blank=True)`
- `summary_json = JSONField(default=dict, blank=True)`

Recommended model properties on `ASPAChangePlan`:

- `is_provider_backed`
- `supports_provider_write`
- `can_preview`
- `can_approve`
- `can_apply`
- `has_governance_metadata`
- `get_governance_metadata()`

Proposed concrete field set for `ASPAChangePlanItem`:

- `change_plan = ForeignKey(ASPAChangePlan, related_name='items')`
- `action_type = CharField(choices=ASPAChangePlanAction.choices)`
- `plan_semantic = CharField(choices=ASPAChangePlanItemSemantic.choices, null=True, blank=True)`
- `aspa_intent = ForeignKey(ASPAIntent, related_name='change_plan_items', null=True, blank=True)`
- `aspa = ForeignKey(ASPA, related_name='change_plan_items', null=True, blank=True)`
- `imported_aspa = ForeignKey(ImportedAspa, related_name='change_plan_items', null=True, blank=True)`
- `provider_operation = CharField(..., blank=True)`
- `provider_payload_json = JSONField(default=dict, blank=True)`
- `before_state_json = JSONField(default=dict, blank=True)`
- `after_state_json = JSONField(default=dict, blank=True)`
- `reason = TextField(blank=True)`

Recommended validation constraints:

1. Provider-imported plans must reference both `provider_account` and `provider_snapshot`.
2. Local-only plans must not require provider metadata.
3. Maintenance-window validation should match the existing `ROAChangePlan` rule exactly.
4. Approval/apply timestamps should remain state-driven rather than manually settable by default workflow services.
5. `ASPAChangePlanItem` should allow either local or imported source linkage, but it should not require both.

Recommended relation strategy for shared audit models:

Preferred additive shape for `ApprovalRecord`:

- keep existing `change_plan`
- add `aspa_change_plan`
- add a check constraint enforcing exactly one target
- add filtered unique or index support only if needed after implementation

Preferred additive shape for `ProviderWriteExecution`:

- keep existing `change_plan`
- add `aspa_change_plan`
- keep `provider_snapshot`, `provider_account`, and follow-up sync links shared
- add a check constraint enforcing exactly one target

If these additive generalizations make the migration or registry wiring too noisy, use the parallel-model fallback and record that choice in the decision log before proceeding.

Recommended enum additions:

- `ASPAChangePlanStatus`
  - `draft`
  - `approved`
  - `applying`
  - `applied`
  - `failed`
- `ASPAChangePlanAction`
  - `create`
  - `withdraw`
- `ASPAChangePlanItemSemantic`
  - `create`
  - `withdraw`
  - `replace`
  - `add_provider`
  - `remove_provider`
  - `reshape`
- ASPA-oriented provider operations
  - either widen `ProviderWriteOperation`
  - or add an ASPA-specific provider-operation enum if widening becomes awkward

Recommended summary payload keys for `ASPAChangePlan.summary_json`:

- `create_count`
- `withdraw_count`
- `replacement_count`
- `provider_add_count`
- `provider_remove_count`
- `provider_backed`
- `provider_account_id`
- `provider_snapshot_id`
- `comparison_scope`
- `plan_semantic_counts`
- `skipped_counts`

Important modeling rule:

`ASPAIntent` is one row per customer/provider pair, but authored and imported ASPA objects are one row per customer with many provider rows.

`ASPAChangePlanItem` therefore needs to support both:

- item rows representing a whole-object create or withdraw
- item rows representing the provider-set effect within a replacement or reshape

Recommended serialized state shape for `before_state_json` and `after_state_json`:

```json
{
  "customer_asn": 64500,
  "customer_display": "AS64500",
  "provider_asns": [64501, 64502],
  "provider_rows": [
    {"asn": 64501, "address_family": ""},
    {"asn": 64502, "address_family": "ipv4"}
  ],
  "source_kind": "local_aspa",
  "source_id": 123,
  "source_name": "Example ASPA",
  "stale": false
}
```

Recommended plan-item summary shape inside `provider_payload_json`:

```json
{
  "customer": "AS64500",
  "providers": ["AS64501", "AS64502"],
  "added_providers": ["AS64502"],
  "removed_providers": ["AS64503"],
  "comment": "Generated from ASPA change plan item 42"
}
```

Acceptance criteria:

- migrations are additive and reversible
- model validation enforces provider-backed plan integrity where applicable
- plan items can express provider-set deltas without losing the whole-object context

Verification:

- `manage.py makemigrations --check --dry-run netbox_rpki`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_models`

### Phase 2: ASPA Change-Plan Generation

Status:

- not started

Objective:

- generate actionable ASPA plans from completed reconciliation runs

Primary files:

- `netbox_rpki/services/aspa_intent.py`
- new service module recommended: `netbox_rpki/services/aspa_change_plan.py`
- `netbox_rpki/services/__init__.py`
- `netbox_rpki/tests/test_aspa_intent_services.py`
- new focused test module recommended: `netbox_rpki/tests/test_aspa_change_plan.py`

Recommended service entry point:

- `create_aspa_change_plan(reconciliation_run, *, name=None)`

Generation rules:

1. A missing intent for an active customer/provider pair should produce a plan that creates or reshapes the target ASPA.
2. A published ASPA with extra providers should produce removal or replacement items.
3. A published orphaned ASPA should produce a withdraw item.
4. Imported provider-backed plans should carry provider operation metadata.
5. Local-only plans should still be generated even when no provider apply path exists.

Required helper behavior:

- serialize a whole ASPA state for `before_state_json`
- serialize a target ASPA state for `after_state_json`
- compute deterministic provider-set deltas per customer ASN
- deduplicate provider removals within replacement workflows
- preserve operator-readable reasons

Recommended helper functions:

- `_serialize_local_aspa_state(aspa)`
- `_serialize_imported_aspa_state(imported_aspa)`
- `_serialize_intent_target_state(customer_as, provider_rows_or_values)`
- `_group_active_intents_by_customer(reconciliation_run)`
- `_group_published_aspas_by_customer(reconciliation_run)`
- `_compute_provider_set_delta(expected_providers, observed_providers)`
- `_build_aspa_plan_reason(...)`
- `_serialize_provider_payload_for_aspa_delta(...)`

Recommended helper outputs:

- full customer ASN
- provider set before
- provider set after
- added providers
- removed providers
- whether the delta is whole-object create, whole-object withdraw, or reshape

Recommended plan-construction algorithm:

1. Partition all active `ASPAIntent` rows in the reconciliation run by customer ASN.
2. For each customer ASN, derive the expected provider set from active intent rows.
3. Resolve the best observed ASPA subject for that customer from local or imported scope.
4. Compute:
   - expected providers
   - observed providers
   - missing providers
   - extra providers
   - whether the observed ASPA is stale
5. Emit one of these customer-level outcomes:
   - create whole ASPA
   - withdraw whole ASPA
   - reshape existing ASPA
   - no-op
6. Persist plan items:
   - one top-level item representing the customer-level action
   - optional subordinate or peer items representing add/remove provider semantics if explicit operator drill-down is desired
7. Populate `summary_json` with both whole-object and provider-set counts.

Recommended naming patterns:

- plan: `{reconciliation_run.name} Change Plan {timestamp}`
- create item: `Create ASPA for AS64500`
- withdraw item: `Withdraw ASPA for AS64500`
- reshape item: `Reshape ASPA for AS64500`
- provider-add item: `Add provider AS64502 to AS64500`
- provider-remove item: `Remove provider AS64503 from AS64500`

Recommended first-wave behavior choice:

Persist explicit provider-add and provider-remove items when a reshape occurs, but keep a customer-level reshape item as the semantic anchor. This gives the operator readable drill-down while preserving an obvious one-row summary at the customer-AS object level.

Acceptance criteria:

- a completed `ASPAReconciliationRun` can produce a plan deterministically
- provider-backed plans include provider payload metadata
- local-only plans still provide useful operator diffs and reasoning
- plan generation tests cover:
  - create from missing state
  - withdraw orphaned state
  - remove extra provider
  - add missing provider
  - replace stale or mismatched imported state

Verification:

- `manage.py test --keepdb --noinput netbox_rpki.tests.test_aspa_intent_services`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_aspa_change_plan`

### Phase 3: Krill ASPA Preview and Apply

Status:

- not started

Objective:

- implement the first provider-backed ASPA write path using the same preview, approve, apply, and resync workflow already used for ROA

Primary files:

- `netbox_rpki/services/provider_write.py`
- `netbox_rpki/services/provider_sync_krill.py`
- `netbox_rpki/services/provider_sync.py`
- `netbox_rpki/tests/test_provider_write.py`
- new focused test module recommended: `netbox_rpki/tests/test_aspa_provider_write.py`

Recommended service entry points:

- `build_aspa_change_plan_delta(plan)`
- `preview_aspa_change_plan_provider_write(plan, *, requested_by='')`
- `approve_aspa_change_plan(plan, *, approved_by='', ...)`
- `apply_aspa_change_plan_provider_write(plan, *, requested_by='')`

Implementation rule:

Do not clone the ROA provider-write module blindly. Extract shared helper pieces where useful:

- plan normalization
- approval-state validation
- governance metadata capture
- execution row creation
- follow-up sync orchestration

Keep family-specific pieces separate:

- delta serialization
- provider endpoint submission
- provider payload shape

Expected Krill path responsibilities:

1. serialize an ASPA delta from plan items
2. submit it to the Krill ASPA write endpoint
3. record a preview execution
4. record an apply execution
5. transition plan status
6. trigger a follow-up sync
7. attach follow-up sync metadata to the execution record

Recommended implementation split inside `provider_write.py`:

Shared helpers:

- normalize ROA or ASPA plan instance
- validate previewable, approvable, and applicable states
- record approval metadata
- create provider-write execution row
- run follow-up sync and attach result metadata

ASPA-specific helpers:

- build ASPA delta from `ASPAChangePlanItem`
- submit ASPA delta to Krill
- serialize Krill request and response payloads
- render ASPA-specific provider capability errors

Recommended delta shape options:

Option A, provider-set replacement payload:

```json
{
  "add": [
    {"customer": "AS64500", "providers": ["AS64501", "AS64502"]}
  ],
  "remove": [
    {"customer": "AS64510", "providers": ["AS64511"]}
  ]
}
```

Option B, whole-object desired-state payload:

```json
{
  "desired": [
    {"customer": "AS64500", "providers": ["AS64501", "AS64502"]},
    {"customer": "AS64520", "providers": []}
  ]
}
```

Preferred direction:

Use the payload shape closest to the real Krill ASPA write contract once that is validated in implementation. Until then, keep internal delta-building logic provider-neutral and convert to provider-specific wire format in the final submission helper.

Recommended execution response payload keys:

- `provider_response`
- `aspa_write_mode`
- `governance`
- `delta_summary`
- `followup_sync`

Recommended `delta_summary` shape:

```json
{
  "customer_count": 2,
  "create_count": 1,
  "withdraw_count": 0,
  "provider_add_count": 1,
  "provider_remove_count": 1
}
```

Recommended error cases to normalize:

- unsupported provider type
- ASPA write capability disabled
- plan not approved
- plan already applied
- duplicate provider add
- remove of non-existent provider
- invalid customer or provider ASN formatting in provider response
- provider accepts request but follow-up sync fails

Acceptance criteria:

- preview records a non-mutating execution row
- approval captures governance metadata
- apply transitions plan state through approved to applying to applied or failed
- follow-up sync metadata is attached on success or recorded as a partial failure on sync failure
- unsupported providers fail cleanly with capability-gated error text

Verification:

- mocked provider-write service tests
- existing provider-sync tests remain green
- recommended focused suite:
  - `manage.py test --keepdb --noinput netbox_rpki.tests.test_aspa_provider_write`
  - `manage.py test --keepdb --noinput netbox_rpki.tests.test_provider_sync`

### Phase 4: Registry, API, and UI Workflow Surfaces

Status:

- not started

Objective:

- make ASPA plans operator-reachable and explainable through the standard plugin surfaces

Primary files:

- `netbox_rpki/object_registry.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/api/urls.py`
- `netbox_rpki/views.py`
- `netbox_rpki/urls.py`
- `netbox_rpki/forms.py`
- `netbox_rpki/tables.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/test_graphql.py`

Required surfaces:

1. new object registration for ASPA change plans and plan items
2. plan detail pages with:
   - summary
   - governance metadata
   - provider capability view
   - approval records
   - provider write executions
3. custom actions:
   - create plan from `ASPAReconciliationRun`
   - preview
   - approve
   - apply
4. API summary endpoint for ASPA plans
5. organization detail integration for latest ASPA plans or plan counts

Recommended UI parity target with ROA:

- if ROA has the operator action, ASPA should get the equivalent unless the domain truly differs

Recommended REST additions:

- `ASPAReconciliationRunViewSet.create_plan`
- `ASPAChangePlanViewSet.preview`
- `ASPAChangePlanViewSet.approve`
- `ASPAChangePlanViewSet.apply`
- optional `ASPAChangePlanViewSet.summary`

Recommended UI routes and views:

- `aspareconciliationrun/<pk>/create-plan/`
- `aspachangeplan/<pk>/preview/`
- `aspachangeplan/<pk>/approve/`
- `aspachangeplan/<pk>/apply/`

Recommended forms:

- `ASPAChangePlanApprovalForm`
  - mirror `ROAChangePlanApprovalForm`
  - reuse the same maintenance-window validator
- preview/apply can continue using `ConfirmationForm`

Recommended detail-page affordances:

- action buttons visible only when `can_preview`, `can_approve`, or `can_apply` is true
- plan summary rendered as formatted JSON initially
- approval records table
- provider write executions table
- optional related reconciliation summary panel

Recommended object registry additions:

- `aspachangeplan`
- `aspachangeplanitem`
- if shared audit models are generalized, expand existing `approvalrecord` and `providerwriteexecution` specs to expose ASPA-target linkage
- if fallback parallel audit models are used, register those objects separately

Recommended API response shape for preview/apply:

```json
{
  "id": 100,
  "name": "ASPA Plan 1",
  "status": "approved",
  "item_count": 3,
  "delta": {...},
  "execution": {...}
}
```

Recommended API response shape for approve:

```json
{
  "id": 100,
  "name": "ASPA Plan 1",
  "status": "approved",
  "item_count": 3,
  "approval_record": {...}
}
```

Acceptance criteria:

- operators can reach every human workflow step from the web UI or the API
- permission checks follow the same pattern as ROA actions
- read-only objects remain read-only
- custom actions return plan plus execution or approval payloads consistently

Verification:

- `manage.py test --keepdb --noinput netbox_rpki.tests.test_api`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_views`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_graphql`

### Phase 5: Reporting and Dashboard Roll-Ups

Status:

- not started

Objective:

- make ASPA operations visible in the same operational reporting layer that currently highlights ROA workflows

Primary files:

- `netbox_rpki/views.py`
- `netbox_rpki/templates/netbox_rpki/operations_dashboard.html`
- `netbox_rpki/api/views.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/test_api.py`

Recommended reporting additions:

1. ASPA reconciliation runs requiring attention
   - missing providers
   - extra providers
   - orphaned ASPAs
   - stale imported ASPAs
2. ASPA change plans requiring attention
   - draft
   - approved
   - failed
3. provider-account capability and last ASPA activity roll-up
4. optional provider-snapshot family roll-up emphasizing ASPA churn

Recommended first dashboard metrics:

- provider accounts with ASPA-capable adapters
- ASPA reconciliation runs with unresolved drift
- open ASPA change plans
- latest ASPA provider-write failures

Recommended inclusion rules for dashboard attention lists:

ASPA reconciliation attention:

- any completed run with non-zero counts in:
  - `missing`
  - `missing_provider`
  - `extra_provider`
  - `orphaned`
  - `stale`
- optionally sort by severity-like priority:
  - stale imported provider-backed runs
  - orphaned
  - missing provider
  - extra provider

ASPA change-plan attention:

- any plan in `draft`, `approved`, or `failed`
- sort by:
  - failed first
  - highest provider-remove count or replacement count
  - newest first

Provider-account attention:

- include provider accounts that support ASPA write but have:
  - stale sync state
  - failed last sync
  - failed recent ASPA execution
  - unresolved ASPA drift in the latest provider-backed run

Acceptance criteria:

- the operations dashboard is no longer ROA-only in practice
- ASPA operators can find outstanding ASPA drift without navigating through object lists manually
- REST summary responses include ASPA workflow aggregates where appropriate

Verification:

- `manage.py test --keepdb --noinput netbox_rpki.tests.test_views`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_api`

### Phase 6: Broader Provider and Analysis Expansion

Status:

- deferred until the first Krill-backed ASPA plan flow is complete

Objective:

- broaden the ASPA workflow after the shared substrate has proven itself

Work items:

1. add more provider adapters only through capability-gated contracts
2. add ASPA lint runs and findings
3. add ASPA simulation if the data available can support meaningful outcomes
4. connect validator or telemetry overlays later if and when they become trustworthy enough to explain to operators

Implementation rule:

Do not block the first ASPA write-back milestone on this phase.

## File Ownership Windows

To reduce merge conflict risk, use the same ownership discipline already documented in the normalization plan.

### Schema window

Owner:

- lead agent only

Files:

- `netbox_rpki/models.py`
- `netbox_rpki/migrations/`
- `netbox_rpki/tests/utils.py`
- `netbox_rpki/tests/registry_scenarios.py`

### Shared surface window

Owner:

- one owner at a time

Files:

- `netbox_rpki/object_registry.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/api/views.py`
- `netbox_rpki/views.py`
- `netbox_rpki/forms.py`
- `netbox_rpki/tables.py`

### Provider write window

Owner:

- one owner at a time

Files:

- `netbox_rpki/services/provider_write.py`
- `netbox_rpki/services/provider_sync.py`
- `netbox_rpki/services/provider_sync_krill.py`
- provider-write and provider-sync tests

## Test Plan

This implementation should follow the testing lanes in [netbox_rpki_testing_strategy_matrix.md](netbox_rpki_testing_strategy_matrix.md).

### Required Lane A coverage

Offline and mocked tests must cover:

- model validation
- migration checks
- plan generation
- provider capability gating
- approval-state transitions
- preview and apply audit recording
- API permission enforcement
- UI affordances and action routing
- dashboard roll-ups

### Required Lane B coverage

Krill-backed validation should be the first live proving ground for ASPA write-through.

At minimum, the implementation should eventually prove:

- preview payload matches the intended provider delta
- apply creates a missing ASPA when required
- apply removes an unwanted provider or withdraws an orphaned ASPA when required
- follow-up sync reflects the applied change

These live tests do not need to block schema and local workflow development, but the design should not make them awkward.

## Suggested Test Modules

Existing modules to extend:

- `netbox_rpki/tests/test_models.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_views.py`
- `netbox_rpki/tests/test_graphql.py`
- `netbox_rpki/tests/test_aspa_intent_services.py`
- `netbox_rpki/tests/test_provider_write.py`
- `netbox_rpki/tests/test_provider_sync.py`

Recommended new focused modules:

- `netbox_rpki/tests/test_aspa_change_plan.py`
- `netbox_rpki/tests/test_aspa_provider_write.py`

Recommended fixture additions in `netbox_rpki/tests/utils.py`:

- `create_test_aspa_change_plan`
- `create_test_aspa_change_plan_item`
- helper builders for imported ASPA replacement scenarios
- helper builders for provider-set delta scenarios

Recommended detailed test matrix:

Model tests in `netbox_rpki/tests/test_models.py`:

- provider account exposes explicit ASPA capability metadata
- `ASPAChangePlan` validates maintenance-window bounds
- provider-backed `ASPAChangePlan` requires provider account and snapshot coherence
- `ASPAChangePlan.can_preview`, `.can_approve`, and `.can_apply` follow status and capability rules
- `ASPAChangePlanItem` accepts local-only items
- `ASPAChangePlanItem` accepts imported-provider items
- generalized `ApprovalRecord` or `ProviderWriteExecution` enforces exactly one target if shared-target design is chosen

Service tests in `netbox_rpki/tests/test_aspa_change_plan.py`:

- generate create plan from missing imported state
- generate withdraw plan from orphaned imported ASPA
- generate reshape plan for missing provider
- generate reshape plan for extra provider
- generate stale replacement plan from stale imported ASPA
- summary JSON counts are deterministic
- local-only plans carry empty provider payloads
- provider-backed plans carry provider payloads

Provider-write tests in `netbox_rpki/tests/test_aspa_provider_write.py`:

- build delta from create-only plan
- build delta from withdraw-only plan
- build delta from reshape plan with both add and remove provider members
- preview records execution without mutating plan state
- approve persists governance metadata and approval record
- apply marks plan applied and records response payload
- apply marks plan failed on provider error
- apply records partial failure on follow-up sync failure
- unsupported provider raises capability error

API tests in `netbox_rpki/tests/test_api.py`:

- `ASPAReconciliationRun.create_plan` action exists and enforces permission
- `ASPAChangePlan.preview` returns delta and execution
- `ASPAChangePlan.approve` returns approval record
- `ASPAChangePlan.apply` returns execution
- summary endpoint returns aggregate counts
- provider-account detail exposes ASPA capability metadata

View tests in `netbox_rpki/tests/test_views.py`:

- ASPA change plan detail shows preview and approve buttons when supported
- preview page renders delta
- approve page renders governance inputs and persists them
- apply page renders governance metadata after approval
- unsupported-provider plan hides write buttons
- operations dashboard includes ASPA sections when relevant objects exist

GraphQL tests in `netbox_rpki/tests/test_graphql.py`:

- list and detail access for `ASPAChangePlan`
- list and detail access for `ASPAChangePlanItem`
- any shared audit object changes expose the new ASPA linkage cleanly

Recommended verification bundles:

Bundle A, schema and services:

- `manage.py makemigrations --check --dry-run netbox_rpki`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_models`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_aspa_intent_services`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_aspa_change_plan`

Bundle B, provider write:

- `manage.py test --keepdb --noinput netbox_rpki.tests.test_aspa_provider_write`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_provider_sync`

Bundle C, surfaces:

- `manage.py test --keepdb --noinput netbox_rpki.tests.test_api`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_views`
- `manage.py test --keepdb --noinput netbox_rpki.tests.test_graphql`

Bundle D, broad plugin gate:

- `manage.py test --keepdb --noinput netbox_rpki --verbosity 1`

## Migration Sequencing Recommendation

Recommended migration slicing:

1. capability substrate and enums
   - provider-account ASPA capability support
2. ASPA change-plan schema
   - change plans, items, and any shared-audit linkage changes
3. no-op or best-effort backfill only if required
   - historical ROA approval rows should not be rewritten unless the shared-audit migration requires it

Recommended sequencing rule:

Keep `models.py` and `migrations/` under single-owner control until the schema stabilizes. Surface work should not begin until the migration contract is frozen for the active phase.

## Risks and Failure Modes

Main risks:

1. copying ROA semantics too literally and losing the ASPA provider-set nature
2. over-generalizing audit or provider-operation models before the ASPA workflow is proven
3. under-generalizing provider capability metadata and leaving ASPA support hidden behind ROA-only flags
4. shipping ASPA plans without dashboard or API summary visibility, which would leave the workflow operationally incomplete

Recommended mitigations:

1. serialize provider-set deltas explicitly from the first plan-generation slice
2. keep provider submission logic family-specific even when approval/audit helpers are shared
3. add focused tests around provider capability exposure before plan implementation
4. make Phase 5 reporting a release gate, not an optional polish task

## Release Gates

Do not mark Priority 3 complete until all of the following are true.

1. `ASPAReconciliationRun` can produce an explicit plan object.
2. The plan can be previewed through a provider-backed path.
3. The plan can be approved and applied through the same governance shape used for ROA.
4. Provider capability gating is explicit and operator-visible.
5. Execution and approval history is queryable from UI and API surfaces.
6. The operations dashboard exposes ASPA attention views.
7. Focused ASPA workflow tests are in place and the broader plugin suite still passes.

## Open Questions

These should be answered before Phase 1 migration authoring is finalized.

1. Should approval and provider-write execution be generalized now, or should the first ASPA slice use parallel audit models?
2. Should `ProviderWriteOperation` become family-aware, or should ASPA write operations use a separate enum?
3. Should the first ASPA plan item represent a whole customer-level reshape only, or also persist provider-add and provider-remove items explicitly?
4. Should GraphQL expose ASPA custom workflow artifacts in the first wave, or can that remain REST plus UI initially?

Recommended answers:

1. generalize audit linkage now if the migration remains additive and readable
2. use family-aware provider operations only if the naming remains explicit; otherwise use a separate ASPA enum
3. persist explicit provider-add and provider-remove semantics in the plan summary and item model
4. keep GraphQL parity for standard object access, but do not block the first wave on workflow-action mutations

## Concrete First Implementation Slice

If implementation starts immediately, the highest-value first slice is:

1. Phase 0 provider capability substrate
2. Phase 1 ASPA change-plan schema
3. Phase 2 ASPA plan generation
4. mocked Phase 3 preview and approval flow

That slice is large enough to prove the design but small enough to avoid getting blocked on live Krill write semantics.

The first slice should change, at minimum:

- `netbox_rpki/models.py`
- `netbox_rpki/migrations/`
- `netbox_rpki/services/aspa_intent.py` or a new `aspa_change_plan.py`
- `netbox_rpki/services/__init__.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/object_registry.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/tests/utils.py`
- `netbox_rpki/tests/test_models.py`
- `netbox_rpki/tests/test_aspa_intent_services.py`
- `netbox_rpki/tests/test_api.py`

## Completion Definition

Priority 3 should be considered functionally complete when ASPA has parity with the current ROA control plane in these areas:

- reconciliation
- change planning
- preview
- approval
- apply
- execution audit
- operator drill-down
- summary reporting

ASPA lint, simulation, and broader provider coverage are explicitly follow-on work. They should improve the ASPA workflow, not define whether the core operational workflow exists.

## Appendix A: Recommended Migration Slices

This appendix turns the phase plan into migration-sized schema slices.

The migration numbers below are symbolic. The numeric prefix will depend on whatever other refactoring lands first.

Recommended symbolic migration names:

1. `aspa_capability_substrate`
2. `aspa_change_plan_schema`
3. `shared_audit_targets_for_aspa`

If the shared-audit generalization is deferred, replace step 3 with:

3. `aspa_audit_models`

### Slice A1: `aspa_capability_substrate`

Goal:

- add provider-account ASPA capability enums or properties without changing workflow models yet

Expected model changes:

- add `ProviderAspaWriteMode`
- add provider-account properties only if no persistent fields are required

Expected migration need:

- possibly none if implemented entirely as enum additions and properties

Files likely touched:

- `netbox_rpki/models.py`
- `netbox_rpki/api/serializers.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/tests/test_models.py`
- `netbox_rpki/tests/test_api.py`

Acceptance gate:

- provider-account capability metadata is ASPA-aware in model and API surfaces

### Slice A2: `aspa_change_plan_schema`

Goal:

- add change-plan models and enums before any provider-write implementation

Expected model changes:

- `ASPAChangePlan`
- `ASPAChangePlanItem`
- `ASPAChangePlanStatus`
- `ASPAChangePlanAction`
- `ASPAChangePlanItemSemantic`
- ASPA plan validation methods and helper properties

Expected migration changes:

- create tables
- add constraints
- add indexes mirroring the ROA plan family where helpful

Recommended indexes:

- `ASPAChangePlan(organization, status)`
- `ASPAChangePlan(provider_account, status)`
- `ASPAChangePlanItem(change_plan, action_type)`
- `ASPAChangePlanItem(change_plan, plan_semantic)`
- optional `ASPAChangePlanItem(aspa_intent)` for drill-down performance

Acceptance gate:

- schema is additive
- model tests prove the plan and item contract

### Slice A3: `shared_audit_targets_for_aspa`

Goal:

- make `ApprovalRecord` and `ProviderWriteExecution` point at either ROA or ASPA plans

Expected model changes:

- add `ApprovalRecord.aspa_change_plan`
- add `ProviderWriteExecution.aspa_change_plan`
- add exactly-one-target constraints

Recommended constraint shape:

- `ApprovalRecord`:
  - `(change_plan IS NOT NULL AND aspa_change_plan IS NULL) OR (change_plan IS NULL AND aspa_change_plan IS NOT NULL)`
- `ProviderWriteExecution`:
  - same exactly-one-target rule

Recommended compatibility rule:

- existing ROA rows remain valid unchanged
- no backfill is required beyond nullable new fields

Acceptance gate:

- historical ROA rows survive untouched
- new ASPA audit rows are storable

### Slice A3 Fallback: `aspa_audit_models`

Use this only if shared-audit generalization proves too noisy.

Fallback models:

- `ASPAApprovalRecord`
- `ASPAProviderWriteExecution`

Fallback downside:

- duplicated surface plumbing
- future governance unification cost
- more work in the dashboard and API layers

## Appendix B: Exact Model and Method Inventory

This appendix lists the concrete model-layer methods and properties that should exist after the first ASPA operational wave.

### `RpkiProviderAccount`

Recommended additions:

- `aspa_write_mode`
- `supports_aspa_write`
- `aspa_write_capability`

Recommended behavior:

- Krill returns explicit supported ASPA write mode
- ARIN returns unsupported
- the capability payload structure mirrors `roa_write_capability`

Recommended payload shape:

```json
{
  "supports_aspa_write": true,
  "aspa_write_mode": "krill_aspa_delta",
  "supported_aspa_plan_actions": ["create", "withdraw"]
}
```

### `ASPAChangePlan`

Recommended methods and properties:

- `__str__`
- `get_absolute_url`
- `clean`
- `has_governance_metadata`
- `get_governance_metadata`
- `is_provider_backed`
- `supports_provider_write`
- `can_preview`
- `can_approve`
- `can_apply`

Recommended semantics:

- `supports_provider_write` should depend on provider-account ASPA capability, not ROA capability
- `can_preview` should allow `draft`, `approved`, and `failed`
- `can_approve` should allow `draft`
- `can_apply` should allow `approved`

### `ASPAChangePlanItem`

Recommended semantics:

- `action_type` remains the operator-visible physical action class
- `plan_semantic` describes the logical reason or category
- `provider_payload_json` contains the provider-facing delta fragment for the specific item
- `before_state_json` and `after_state_json` remain human-readable, not provider-wire-format-only

Recommended exactly-one-or-more linkage rule:

- at least one of `aspa_intent`, `aspa`, or `imported_aspa` should be present for meaningful provenance
- do not require all three
- do not require both local and imported source links on the same row

### `ApprovalRecord` if generalized

Recommended additions:

- `aspa_change_plan`

Recommended helper property:

- `target_change_plan`

Recommended behavior:

- returns whichever plan link is populated

### `ProviderWriteExecution` if generalized

Recommended additions:

- `aspa_change_plan`

Recommended helper properties:

- `target_change_plan`
- optional `object_family`

Recommended behavior:

- surfaces enough metadata for detail pages and dashboard sections to render family-aware labels

## Appendix C: Service Contract Details

This appendix turns the workflow into explicit Python service contracts.

### Recommended new module

- `netbox_rpki/services/aspa_change_plan.py`

Reason:

- `services/aspa_intent.py` already owns reconciliation logic
- change-plan creation is a distinct concern, just as ROA plan creation lives beside reconciliation in a larger routing-intent module

### Recommended exported functions

Add these to `netbox_rpki/services/__init__.py` when implemented:

- `create_aspa_change_plan`
- `build_aspa_change_plan_delta`
- `approve_aspa_change_plan`
- `preview_aspa_change_plan_provider_write`
- `apply_aspa_change_plan_provider_write`

### `create_aspa_change_plan`

Recommended signature:

```python
def create_aspa_change_plan(
    reconciliation_run: rpki_models.ASPAReconciliationRun,
    *,
    name: str | None = None,
) -> rpki_models.ASPAChangePlan:
    ...
```

Preconditions:

- reconciliation run status is `completed`
- if comparison scope is `provider_imported`, the run has a `provider_snapshot`
- provider-backed plans derive `provider_account` from `provider_snapshot.provider_account`

Postconditions:

- creates one `ASPAChangePlan`
- creates one or more `ASPAChangePlanItem`
- persists deterministic `summary_json`

### `build_aspa_change_plan_delta`

Recommended signature:

```python
def build_aspa_change_plan_delta(
    plan: rpki_models.ASPAChangePlan | int,
) -> dict[str, list[dict]]:
    ...
```

Recommended output contract:

- family-specific but deterministic
- stable sort order by customer ASN then provider ASN or provider text
- no duplicate provider members

Recommended return shape:

```json
{
  "added": [
    {"customer_asn": 64500, "providers": [64501, 64502]}
  ],
  "removed": [
    {"customer_asn": 64510, "providers": [64511]}
  ]
}
```

### `approve_aspa_change_plan`

Recommended signature:

```python
def approve_aspa_change_plan(
    plan: rpki_models.ASPAChangePlan | int,
    *,
    approved_by: str = "",
    ticket_reference: str = "",
    change_reference: str = "",
    maintenance_window_start=None,
    maintenance_window_end=None,
    approval_notes: str = "",
) -> rpki_models.ASPAChangePlan:
    ...
```

Expected behavior:

- validate approvable state
- persist governance metadata
- create approval record

### `preview_aspa_change_plan_provider_write`

Recommended signature:

```python
def preview_aspa_change_plan_provider_write(
    plan: rpki_models.ASPAChangePlan | int,
    *,
    requested_by: str = "",
) -> tuple[rpki_models.ProviderWriteExecution, dict[str, list[dict]]]:
    ...
```

Expected behavior:

- validate previewable state
- build delta
- persist preview execution row
- return execution and delta

### `apply_aspa_change_plan_provider_write`

Recommended signature:

```python
def apply_aspa_change_plan_provider_write(
    plan: rpki_models.ASPAChangePlan | int,
    *,
    requested_by: str = "",
) -> tuple[rpki_models.ProviderWriteExecution, dict[str, list[dict]]]:
    ...
```

Expected behavior:

- validate applicable state
- set plan to `applying`
- submit provider delta
- set plan to `applied` or `failed`
- record execution payload
- trigger follow-up sync

## Appendix D: Internal Helper Inventory

These helpers should exist either in `aspa_change_plan.py` or `provider_write.py`.

Plan-generation helpers:

- `_normalize_aspa_reconciliation_run`
- `_group_intents_by_customer`
- `_group_published_rows_by_customer`
- `_expected_provider_values_for_customer`
- `_observed_provider_values_for_customer`
- `_compute_provider_delta`
- `_serialize_plan_before_state`
- `_serialize_plan_after_state`
- `_build_create_item`
- `_build_withdraw_item`
- `_build_reshape_item`
- `_build_provider_add_item`
- `_build_provider_remove_item`

Provider-write helpers:

- `_normalize_aspa_plan`
- `_require_aspa_provider_write_capability`
- `_require_aspa_previewable`
- `_require_aspa_approvable`
- `_require_aspa_applicable`
- `_submit_krill_aspa_delta`
- `_aspa_delta_sort_key`

Shared-governance helpers if generalized:

- `_create_approval_record_for_plan`
- `_create_provider_write_execution_for_plan`
- `_get_plan_governance_metadata`

## Appendix E: Registry and Surface Wiring Checklist

This appendix turns the generated-surface work into a literal checklist.

### `object_registry.py`

Add or extend:

- `aspachangeplan`
- `aspachangeplanitem`
- `approvalrecord` if shared-target exposure changes
- `providerwriteexecution` if shared-target exposure changes

Recommended `aspachangeplan` API fields:

- `name`
- `organization`
- `source_reconciliation_run`
- `provider_account`
- `provider_snapshot`
- `status`
- `ticket_reference`
- `change_reference`
- `maintenance_window_start`
- `maintenance_window_end`
- `approved_at`
- `approved_by`
- `apply_started_at`
- `apply_requested_by`
- `applied_at`
- `failed_at`
- `summary_json`

Recommended `aspachangeplanitem` API fields:

- `name`
- `change_plan`
- `action_type`
- `plan_semantic`
- `aspa_intent`
- `aspa`
- `imported_aspa`
- `provider_operation`
- `provider_payload_json`
- `before_state_json`
- `after_state_json`
- `reason`

### `detail_specs.py`

Add:

- `ASPA_CHANGE_PLAN_DETAIL_SPEC`
- `ASPA_CHANGE_PLAN_ITEM_DETAIL_SPEC`

Recommended plan detail bottom tables:

- `ASPA Change Plan Items`
- `Approval Records`
- `Provider Write Executions`

Recommended detail actions:

- `Preview`
- `Approve`
- `Apply`

### `forms.py`

Add:

- `ASPAChangePlanApprovalForm`

Recommended implementation:

- mirror `ROAChangePlanApprovalForm`
- keep shared maintenance-window validation

### `tables.py`

Add:

- `ASPAChangePlanItemTable`

If plan detail pages should display explicit provider set info cleanly, consider custom renderers for:

- `provider_payload_json`
- `before_state_json`
- `after_state_json`

### `urls.py`

Extend `build_object_urlpatterns` with a new ASPA plan route block similar to the ROA block:

- `aspachangeplan_preview`
- `aspachangeplan_approve`
- `aspachangeplan_apply`

Add `aspareconciliationrun_create_plan` only if the URL pattern is implemented through explicit view wiring rather than generated CRUD plus API action alone.

### `views.py`

Add explicit views:

- `ASPAChangePlanActionView`
- `ASPAChangePlanPreviewView`
- `ASPAChangePlanApproveView`
- `ASPAChangePlanApplyView`

Recommended behavior:

- mirror ROA action view structure
- keep text and labels family-appropriate
- reuse `ConfirmationForm` and the new ASPA approval form

### `api/views.py`

Add:

- `ASPAReconciliationRunViewSet.create_plan`
- `ASPAChangePlanViewSet`
  - `preview`
  - `approve`
  - `apply`
  - optional `summary`

### `api/serializers.py`

Add:

- `ASPAChangePlanSerializer`
- ASPA approval action serializer if not reusing a shared approval action serializer

Recommended serializer enhancements:

- expose latest execution summary later if that proves useful
- for the first wave, parity with ROA plan serializer structure is sufficient

## Appendix F: UI and API Acceptance Checklist

This appendix is the operator-surface acceptance test in prose.

### UI checklist

1. An operator can open an `ASPAReconciliationRun` detail page.
2. The page exposes a `Create Plan` action when permissions allow.
3. The resulting `ASPAChangePlan` detail page renders:
   - plan summary
   - governance metadata
   - item list
   - approval record list
   - provider write execution list
4. The plan detail page shows:
   - `Preview` while draft, approved, or failed
   - `Approve` while draft
   - `Apply` while approved
5. Unsupported providers do not display preview or approve or apply controls.
6. The operations dashboard contains ASPA attention sections when ASPA drift or open plans exist.

### API checklist

1. `Organization.run_aspa_reconciliation` remains intact.
2. `ASPAReconciliationRun.create_plan` returns a serialized plan and item count.
3. `ASPAChangePlan.preview` returns plan plus execution plus delta.
4. `ASPAChangePlan.approve` returns plan plus approval record.
5. `ASPAChangePlan.apply` returns plan plus execution plus delta.
6. Provider-account detail returns explicit ASPA capability metadata.

## Appendix G: Suggested Commit Sequence

The plan is large enough that it should not land as one patch unless necessary.

Recommended commit sequence:

1. capability substrate
   - provider-account ASPA capability exposure
   - tests for model and API capability surfaces
2. schema substrate
   - ASPA change-plan models
   - tests and fixtures
3. plan generation
   - create plan service
   - plan-generation tests
4. audit generalization or fallback audit models
   - approval or execution linkage
   - tests
5. preview and approve flow
   - provider-write preview
   - approval service
   - API and UI surfaces
6. apply flow
   - provider submission
   - execution audit
   - follow-up sync
7. dashboard and summary roll-ups
   - view and API reporting
   - dashboard tests

Recommended sequencing rule:

Each commit or small batch should leave the plugin suite green and should not introduce a half-wired surface object without at least basic registry, API, and view coverage.

## Appendix H: First-Wave “Done Means Done” Checklist

Use this as the short operational completion checklist for the first ASPA wave.

- provider accounts expose explicit ASPA write capability
- ASPA reconciliation runs can create plans
- ASPA change plans render through generated surfaces
- ASPA plans can be previewed
- ASPA plans can be approved
- ASPA plans can be applied through a Krill-backed path
- approval and execution audit history is queryable
- unsupported providers fail through explicit capability gating
- operations dashboard includes ASPA attention visibility
- focused ASPA workflow tests exist
- broad plugin suite remains green

## Appendix I: Draft Django Model Skeletons

This appendix is intentionally close to implementation shape. It is not meant to be copied blindly, but it should be close enough that the real implementation can follow it with minimal reinterpretation.

### Proposed capability enum

```python
class ProviderAspaWriteMode(models.TextChoices):
    UNSUPPORTED = "unsupported", "Unsupported"
    KRILL_ASPA_DELTA = "krill_aspa_delta", "Krill ASPA Delta"
```

### Proposed `RpkiProviderAccount` additions

```python
@property
def aspa_write_mode(self) -> str:
    if self.provider_type == ProviderType.KRILL:
        return ProviderAspaWriteMode.KRILL_ASPA_DELTA
    return ProviderAspaWriteMode.UNSUPPORTED

@property
def supports_aspa_write(self) -> bool:
    return self.aspa_write_mode != ProviderAspaWriteMode.UNSUPPORTED

@property
def aspa_write_capability(self) -> dict:
    supported_actions = []
    if self.supports_aspa_write:
        supported_actions = [
            ASPAChangePlanAction.CREATE,
            ASPAChangePlanAction.WITHDRAW,
        ]
    return {
        "supports_aspa_write": self.supports_aspa_write,
        "aspa_write_mode": self.aspa_write_mode,
        "supported_aspa_plan_actions": supported_actions,
    }
```

### Proposed `ASPAChangePlan`

```python
class ASPAChangePlan(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name="aspa_change_plans",
    )
    source_reconciliation_run = models.ForeignKey(
        to="ASPAReconciliationRun",
        on_delete=models.PROTECT,
        related_name="change_plans",
    )
    provider_account = models.ForeignKey(
        to="RpkiProviderAccount",
        on_delete=models.PROTECT,
        related_name="aspa_change_plans",
        blank=True,
        null=True,
    )
    provider_snapshot = models.ForeignKey(
        to="ProviderSnapshot",
        on_delete=models.PROTECT,
        related_name="aspa_change_plans",
        blank=True,
        null=True,
    )
    status = models.CharField(
        max_length=16,
        choices=ASPAChangePlanStatus.choices,
        default=ASPAChangePlanStatus.DRAFT,
    )
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=150, blank=True)
    apply_started_at = models.DateTimeField(blank=True, null=True)
    apply_requested_by = models.CharField(max_length=150, blank=True)
    applied_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created", "name")
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F("maintenance_window_start"))
                ),
                name="netbox_rpki_aspachangeplan_valid_maintenance_window",
            ),
        )
        indexes = (
            models.Index(fields=("organization", "status"), name="nb_rpki_acp_org_status_idx"),
            models.Index(fields=("provider_account", "status"), name="nb_rpki_acp_provider_status_idx"),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspachangeplan", args=[self.pk])

    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(
            start_at=self.maintenance_window_start,
            end_at=self.maintenance_window_end,
        )
        if self.provider_snapshot_id is not None and self.provider_account_id is None:
            raise ValidationError({"provider_account": "Provider account is required when provider snapshot is set."})
        if (
            self.provider_snapshot_id is not None
            and self.provider_account_id is not None
            and self.provider_snapshot.provider_account_id != self.provider_account_id
        ):
            raise ValidationError({"provider_snapshot": "Provider snapshot must belong to the selected provider account."})

    @property
    def has_governance_metadata(self) -> bool:
        return any((
            self.ticket_reference,
            self.change_reference,
            self.maintenance_window_start,
            self.maintenance_window_end,
        ))

    def get_governance_metadata(self) -> dict[str, str]:
        metadata = {}
        if self.ticket_reference:
            metadata["ticket_reference"] = self.ticket_reference
        if self.change_reference:
            metadata["change_reference"] = self.change_reference
        if self.maintenance_window_start is not None:
            metadata["maintenance_window_start"] = self.maintenance_window_start.isoformat()
        if self.maintenance_window_end is not None:
            metadata["maintenance_window_end"] = self.maintenance_window_end.isoformat()
        return metadata

    @property
    def is_provider_backed(self) -> bool:
        return self.provider_account_id is not None and self.provider_snapshot_id is not None

    @property
    def supports_provider_write(self) -> bool:
        return self.is_provider_backed and self.provider_account.supports_aspa_write

    @property
    def can_preview(self) -> bool:
        return self.supports_provider_write and self.status in {
            ASPAChangePlanStatus.DRAFT,
            ASPAChangePlanStatus.APPROVED,
            ASPAChangePlanStatus.FAILED,
        }

    @property
    def can_approve(self) -> bool:
        return self.supports_provider_write and self.status == ASPAChangePlanStatus.DRAFT

    @property
    def can_apply(self) -> bool:
        return self.supports_provider_write and self.status == ASPAChangePlanStatus.APPROVED
```

### Proposed `ASPAChangePlanItem`

```python
class ASPAChangePlanItem(NamedRpkiStandardModel):
    change_plan = models.ForeignKey(
        to="ASPAChangePlan",
        on_delete=models.PROTECT,
        related_name="items",
    )
    action_type = models.CharField(
        max_length=16,
        choices=ASPAChangePlanAction.choices,
    )
    plan_semantic = models.CharField(
        max_length=24,
        choices=ASPAChangePlanItemSemantic.choices,
        blank=True,
        null=True,
    )
    aspa_intent = models.ForeignKey(
        to="ASPAIntent",
        on_delete=models.PROTECT,
        related_name="change_plan_items",
        blank=True,
        null=True,
    )
    aspa = models.ForeignKey(
        to="ASPA",
        on_delete=models.PROTECT,
        related_name="change_plan_items",
        blank=True,
        null=True,
    )
    imported_aspa = models.ForeignKey(
        to="ImportedAspa",
        on_delete=models.PROTECT,
        related_name="change_plan_items",
        blank=True,
        null=True,
    )
    provider_operation = models.CharField(
        max_length=32,
        blank=True,
    )
    provider_payload_json = models.JSONField(default=dict, blank=True)
    before_state_json = models.JSONField(default=dict, blank=True)
    after_state_json = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        indexes = (
            models.Index(fields=("change_plan", "action_type"), name="nb_rpki_acpi_plan_action_idx"),
            models.Index(fields=("change_plan", "plan_semantic"), name="nb_rpki_acpi_plan_sem_idx"),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspachangeplanitem", args=[self.pk])

    def clean(self):
        super().clean()
        if not any((self.aspa_intent_id, self.aspa_id, self.imported_aspa_id)):
            raise ValidationError(
                "ASPA change plan items must reference at least one related intent or published object."
            )
```

### Proposed shared-audit additive change

```python
class ApprovalRecord(NamedRpkiStandardModel):
    ...
    change_plan = models.ForeignKey(
        to="ROAChangePlan",
        ...
        blank=True,
        null=True,
    )
    aspa_change_plan = models.ForeignKey(
        to="ASPAChangePlan",
        on_delete=models.PROTECT,
        related_name="approval_records",
        blank=True,
        null=True,
    )

    class Meta:
        constraints = (
            ...,
            models.CheckConstraint(
                condition=(
                    models.Q(change_plan__isnull=False, aspa_change_plan__isnull=True)
                    | models.Q(change_plan__isnull=True, aspa_change_plan__isnull=False)
                ),
                name="netbox_rpki_approvalrecord_exactly_one_plan_target",
            ),
        )
```

```python
class ProviderWriteExecution(NamedRpkiStandardModel):
    ...
    change_plan = models.ForeignKey(
        to="ROAChangePlan",
        ...
        blank=True,
        null=True,
    )
    aspa_change_plan = models.ForeignKey(
        to="ASPAChangePlan",
        on_delete=models.PROTECT,
        related_name="provider_write_executions",
        blank=True,
        null=True,
    )

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(change_plan__isnull=False, aspa_change_plan__isnull=True)
                    | models.Q(change_plan__isnull=True, aspa_change_plan__isnull=False)
                ),
                name="netbox_rpki_providerwriteexecution_exactly_one_plan_target",
            ),
        )
```

## Appendix J: Draft Migration Operations

This appendix describes the migration operations that should likely appear, in order.

### Migration: `aspa_change_plan_schema`

Expected operations:

1. `CreateModel(ASPAChangePlan)`
2. `CreateModel(ASPAChangePlanItem)`
3. `AddConstraint` for maintenance-window validation on `ASPAChangePlan`
4. `AddIndex` for `ASPAChangePlan`
5. `AddIndex` for `ASPAChangePlanItem`

Expected non-operations:

- no data backfill should be required
- no existing rows should need mutation
- no route or API rename should happen here

### Migration: `shared_audit_targets_for_aspa`

Expected operations:

1. `AddField(ApprovalRecord.aspa_change_plan)`
2. `AddField(ProviderWriteExecution.aspa_change_plan)`
3. `AlterField` existing `change_plan` links to allow null if they do not already
4. `AddConstraint` exactly-one-target on `ApprovalRecord`
5. `AddConstraint` exactly-one-target on `ProviderWriteExecution`

Recommended migration safety rule:

Split field additions and constraint additions into separate migrations if needed, so data-state ambiguity is easier to reason about during rollout.

## Appendix K: Draft Service Pseudocode

### `create_aspa_change_plan`

```python
def create_aspa_change_plan(reconciliation_run, *, name=None):
    if reconciliation_run.status != ValidationRunStatus.COMPLETED:
        raise ASPAChangePlanExecutionError(
            "ASPA change plans can only be created from completed reconciliation runs."
        )

    provider_account = None
    provider_snapshot = None
    if reconciliation_run.comparison_scope == ReconciliationComparisonScope.PROVIDER_IMPORTED:
        provider_snapshot = reconciliation_run.provider_snapshot
        if provider_snapshot is None:
            raise ASPAChangePlanExecutionError(
                "Provider-imported ASPA reconciliation runs must reference a provider snapshot."
            )
        provider_account = provider_snapshot.provider_account
        if provider_account is None:
            raise ASPAChangePlanExecutionError(
                "Provider-imported ASPA reconciliation runs must reference a provider account."
            )

    plan = ASPAChangePlan.objects.create(...)

    intent_groups = _group_intents_by_customer(reconciliation_run)
    published_groups = _group_published_rows_by_customer(reconciliation_run)

    for customer_key in sorted(set(intent_groups) | set(published_groups)):
        expected = _expected_provider_values_for_customer(intent_groups.get(customer_key, []))
        observed = _observed_provider_values_for_customer(published_groups.get(customer_key, []))
        delta = _compute_provider_delta(expected, observed)

        if _is_missing_whole_object(expected, observed):
            _build_create_item(...)
            continue
        if _is_orphaned_whole_object(expected, observed):
            _build_withdraw_item(...)
            continue
        if delta.added or delta.removed:
            _build_reshape_item(...)
            for provider_value in delta.added:
                _build_provider_add_item(...)
            for provider_value in delta.removed:
                _build_provider_remove_item(...)

    plan.summary_json = _build_plan_summary(plan)
    plan.save(update_fields=("summary_json",))
    return plan
```

### `build_aspa_change_plan_delta`

```python
def build_aspa_change_plan_delta(plan):
    plan = _normalize_aspa_plan(plan)
    _require_aspa_provider_write_capability(plan)

    added = []
    removed = []

    for item in plan.items.exclude(provider_operation="").order_by("pk"):
        payload = dict(item.provider_payload_json or {})
        if item.provider_operation == ASPAProviderWriteOperation.ADD_PROVIDER_SET:
            added.append(payload)
        elif item.provider_operation == ASPAProviderWriteOperation.REMOVE_PROVIDER_SET:
            removed.append(payload)

    return {
        "added": sorted(added, key=_aspa_delta_sort_key),
        "removed": sorted(removed, key=_aspa_delta_sort_key),
    }
```

### `approve_aspa_change_plan`

```python
def approve_aspa_change_plan(plan, **governance):
    plan = _normalize_aspa_plan(plan)
    _require_aspa_approvable(plan)

    approved_at = timezone.now()
    with transaction.atomic():
        plan.status = ASPAChangePlanStatus.APPROVED
        ...
        plan.save(update_fields=(...))
        _create_approval_record_for_plan(
            plan=plan,
            approved_at=approved_at,
            disposition=ValidationDisposition.ACCEPTED,
            ...
        )
    return plan
```

### `preview_aspa_change_plan_provider_write`

```python
def preview_aspa_change_plan_provider_write(plan, *, requested_by=""):
    plan = _normalize_aspa_plan(plan)
    provider_account = _require_aspa_previewable(plan)
    delta = build_aspa_change_plan_delta(plan)
    started_at = timezone.now()
    execution = _create_provider_write_execution_for_plan(
        plan=plan,
        provider_account=provider_account,
        execution_mode=ProviderWriteExecutionMode.PREVIEW,
        requested_by=requested_by,
        status=ValidationRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=started_at,
        item_count=sum(len(values) for values in delta.values()),
        request_payload_json=delta,
        response_payload_json={
            "preview_only": True,
            "aspa_write_mode": provider_account.aspa_write_mode,
            "governance": plan.get_governance_metadata(),
        },
    )
    return execution, delta
```

### `apply_aspa_change_plan_provider_write`

```python
def apply_aspa_change_plan_provider_write(plan, *, requested_by=""):
    plan = _normalize_aspa_plan(plan)
    provider_account = _require_aspa_applicable(plan)
    delta = build_aspa_change_plan_delta(plan)

    started_at = timezone.now()
    plan.status = ASPAChangePlanStatus.APPLYING
    plan.apply_started_at = started_at
    plan.apply_requested_by = requested_by
    plan.failed_at = None
    plan.save(update_fields=("status", "apply_started_at", "apply_requested_by", "failed_at"))

    execution = _create_provider_write_execution_for_plan(...)

    try:
        provider_response = _submit_krill_aspa_delta(provider_account, delta)
        applied_at = timezone.now()
        plan.status = ASPAChangePlanStatus.APPLIED
        plan.applied_at = applied_at
        plan.save(update_fields=("status", "applied_at"))

        try:
            followup_sync_run, followup_snapshot = sync_provider_account(...)
            execution.status = ValidationRunStatus.COMPLETED
        except Exception as exc:
            execution.status = ValidationRunStatus.FAILED
            execution.error = str(exc)

        execution.completed_at = timezone.now()
        execution.response_payload_json = {...}
        execution.save(update_fields=(...))
        return execution, delta

    except Exception as exc:
        completed_at = timezone.now()
        plan.status = ASPAChangePlanStatus.FAILED
        plan.failed_at = completed_at
        plan.save(update_fields=("status", "failed_at"))
        execution.status = ValidationRunStatus.FAILED
        execution.completed_at = completed_at
        execution.error = str(exc)
        execution.response_payload_json = {...}
        execution.save(update_fields=(...))
        raise ASPAProviderWriteError(str(exc)) from exc
```

## Appendix L: Exact Route, View, and Action Names

These names are recommended so the first ASPA wave feels consistent with the existing ROA family.

### UI route names

- `plugins:netbox_rpki:aspachangeplan_list`
- `plugins:netbox_rpki:aspachangeplan`
- `plugins:netbox_rpki:aspachangeplan_preview`
- `plugins:netbox_rpki:aspachangeplan_approve`
- `plugins:netbox_rpki:aspachangeplan_apply`
- `plugins:netbox_rpki:aspachangeplanitem_list`
- `plugins:netbox_rpki:aspachangeplanitem`

### API route names

Expected if generated through the same registry naming pattern:

- `plugins-api:netbox_rpki-api:aspachangeplan-list`
- `plugins-api:netbox_rpki-api:aspachangeplan-detail`
- `plugins-api:netbox_rpki-api:aspachangeplan-preview`
- `plugins-api:netbox_rpki-api:aspachangeplan-approve`
- `plugins-api:netbox_rpki-api:aspachangeplan-apply`
- `plugins-api:netbox_rpki-api:aspachangeplan-summary`
- `plugins-api:netbox_rpki-api:aspareconciliationrun-create-plan`

### Suggested view class names

- `ASPAReconciliationRunViewSet`
- `ASPAChangePlanViewSet`
- `ASPAChangePlanActionView`
- `ASPAChangePlanPreviewView`
- `ASPAChangePlanApproveView`
- `ASPAChangePlanApplyView`

### Suggested permission checks

Model permissions:

- `view_aspachangeplan`
- `change_aspachangeplan`
- `view_aspachangeplanitem`

Action permission policy:

- preview requires `change_aspachangeplan`
- approve requires `change_aspachangeplan`
- apply requires `change_aspachangeplan`
- reconciliation create-plan action should use the same change-level policy approach as ROA change-plan creation

## Appendix M: Suggested Test Case Names

These are concrete candidate names so the future implementation can follow a deliberate test inventory rather than inventing coverage ad hoc.

### `test_models.py`

- `test_provider_account_exposes_explicit_aspa_write_capability`
- `test_aspa_change_plan_validates_maintenance_window_bounds`
- `test_aspa_change_plan_requires_matching_provider_snapshot_and_account`
- `test_aspa_change_plan_can_preview_only_when_provider_backed_and_previewable`
- `test_aspa_change_plan_can_approve_only_when_draft`
- `test_aspa_change_plan_can_apply_only_when_approved`
- `test_aspa_change_plan_item_requires_related_subject_reference`
- `test_approval_record_accepts_aspa_change_plan_target`
- `test_provider_write_execution_accepts_aspa_change_plan_target`

### `test_aspa_change_plan.py`

- `test_create_aspa_change_plan_from_completed_provider_imported_run`
- `test_create_aspa_change_plan_rejects_incomplete_reconciliation_run`
- `test_plan_generation_creates_whole_object_create_for_missing_customer`
- `test_plan_generation_creates_whole_object_withdraw_for_orphaned_customer`
- `test_plan_generation_creates_reshape_and_provider_add_items_for_missing_provider`
- `test_plan_generation_creates_reshape_and_provider_remove_items_for_extra_provider`
- `test_plan_generation_marks_provider_backed_metadata_for_imported_scope`
- `test_plan_summary_counts_are_deterministic`

### `test_aspa_provider_write.py`

- `test_build_aspa_change_plan_delta_serializes_create_payloads`
- `test_build_aspa_change_plan_delta_serializes_withdraw_payloads`
- `test_build_aspa_change_plan_delta_sorts_by_customer_and_provider`
- `test_preview_records_non_mutating_execution`
- `test_approve_transitions_plan_to_approved`
- `test_approve_records_governance_metadata_and_approval_record`
- `test_apply_submits_delta_records_execution_and_triggers_followup_sync`
- `test_apply_rejects_repeat_apply`
- `test_apply_failure_marks_plan_failed_and_records_error`
- `test_capability_gating_rejects_unsupported_provider`

### `test_api.py`

- `test_aspa_reconciliation_create_plan_action_returns_plan`
- `test_aspa_change_plan_preview_action_returns_delta_and_execution`
- `test_aspa_change_plan_approve_action_transitions_plan`
- `test_aspa_change_plan_approve_action_records_governance_metadata`
- `test_aspa_change_plan_apply_action_runs_provider_write_flow`
- `test_aspa_change_plan_summary_action_returns_aggregate_counts`
- `test_provider_account_api_exposes_aspa_write_capability_metadata`
- `test_aspa_change_plan_custom_actions_require_change_permission`

### `test_views.py`

- `test_aspa_change_plan_detail_shows_preview_and_approve_buttons`
- `test_aspa_change_plan_preview_view_renders_delta`
- `test_aspa_change_plan_approve_view_renders_and_persists_governance_fields`
- `test_aspa_change_plan_apply_view_shows_governance_metadata_after_approval`
- `test_aspa_change_plan_unsupported_provider_hides_write_buttons`
- `test_operations_dashboard_surfaces_aspa_reconciliation_attention`
- `test_operations_dashboard_surfaces_open_aspa_change_plans`

## Appendix N: Per-File Task List for the First Build Window

This appendix is the most literal execution checklist in the document.

### `netbox_rpki/models.py`

- add `ProviderAspaWriteMode`
- add `RpkiProviderAccount.aspa_write_mode`
- add `RpkiProviderAccount.supports_aspa_write`
- add `RpkiProviderAccount.aspa_write_capability`
- add `ASPAChangePlanStatus`
- add `ASPAChangePlanAction`
- add `ASPAChangePlanItemSemantic`
- add `ASPAChangePlan`
- add `ASPAChangePlanItem`
- generalize `ApprovalRecord` or add fallback ASPA audit model
- generalize `ProviderWriteExecution` or add fallback ASPA execution model

### `netbox_rpki/migrations/`

- add migration for ASPA plan schema
- add migration for shared-audit target expansion or fallback audit models

### `netbox_rpki/services/aspa_change_plan.py`

- implement plan creation
- implement helper serialization
- implement summary builder

### `netbox_rpki/services/provider_write.py`

- add ASPA plan normalization helpers
- add ASPA approval helper
- add ASPA preview helper
- add ASPA apply helper
- add Krill ASPA submission helper

### `netbox_rpki/services/__init__.py`

- export ASPA plan services

### `netbox_rpki/api/serializers.py`

- add provider-account ASPA capability fields
- add `ASPAChangePlanSerializer`
- add approval serializer if needed

### `netbox_rpki/api/views.py`

- add `ASPAReconciliationRunViewSet.create_plan`
- add `ASPAChangePlanViewSet`

### `netbox_rpki/object_registry.py`

- register ASPA change-plan models
- expose any shared-audit target additions

### `netbox_rpki/detail_specs.py`

- add ASPA change-plan detail spec
- add ASPA change-plan item detail spec
- update provider-account detail if capability display expands

### `netbox_rpki/forms.py`

- add `ASPAChangePlanApprovalForm`

### `netbox_rpki/views.py`

- add ASPA change-plan action views
- add ASPA operations dashboard sections

### `netbox_rpki/urls.py`

- wire ASPA change-plan preview, approve, and apply routes

### `netbox_rpki/tables.py`

- add `ASPAChangePlanItemTable`

### `netbox_rpki/tests/utils.py`

- add ASPA plan and plan-item factories
- add generalized approval or execution factories if shared audit models change

### `netbox_rpki/tests/`

- add and extend tests per Appendix M
