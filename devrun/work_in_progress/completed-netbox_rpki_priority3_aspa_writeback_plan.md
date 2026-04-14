# Priority 3: ASPA Write-Back — Implementation Plan

**Target:** complete, harden, and fully test the Krill ASPA provider write-back lifecycle (preview → approve → apply).

---

## 1. Actual Current State

~~Despite the backlog labelling this "Partially complete", inspection shows the **core service infrastructure is virtually finished**. The remaining work is limited to two broken form/serializer subclasses and significant test-coverage gaps.~~

**Updated 2026-04-14:** Slice A is complete. Slice B remains entirely absent. Slice C is substantially complete with one gap.

| Component | File | Status | Gap |
|---|---|---|---|
| `create_aspa_change_plan()` | `services/aspa_change_plan.py` | **Complete** | — |
| `build_aspa_change_plan_delta()` | `services/provider_write.py:L~175` | **Complete** | — |
| `_serialize_krill_aspa_delta()` | `services/provider_write.py:L~677` | **Complete** | No unit test (Slice B) |
| `_submit_krill_aspa_delta()` | `services/provider_write.py:L~699` | **Complete** | — |
| `preview_aspa_change_plan_provider_write()` | `services/provider_write.py:L599` | **Complete** | — |
| `approve_aspa_change_plan()` | `services/provider_write.py:L485` | **Complete** | No service-layer tests (Slice B) |
| `apply_aspa_change_plan_provider_write()` | `services/provider_write.py:L795` | **Complete** | No service-layer failure/repeat tests (Slice B) |
| `ASPAChangePlanPreviewView` | `views.py:L1482` | **Complete** | — |
| `ASPAChangePlanApproveView` | `views.py:L1618` | **Complete** | — |
| `ASPAChangePlanApplyView` | `views.py:L1671` | **Complete** | — |
| `ASPAChangePlanViewSet` | `api/views.py:L856` | **Complete** | — |
| `ASPAChangePlanApprovalForm` | `forms.py:L291` | **Complete** — pops 4 ROA fields, has own `clean()` | Open defect: `fieldsets` includes `requires_secondary_approval` but `test_approve_form_exposes_only_governance_fields` expects it absent — one of these is wrong |
| `ASPAChangePlanApproveActionSerializer` | `api/serializers.py:L747` | **Complete** — 5 governance fields, correct `validate()` | — |
| `ASPAProviderWriteServiceTestCase` | _missing_ | **Absent** | Slice B |
| ASPA API action tests | `tests/test_provider_write.py:L1447` | **Substantial** (9 tests) | `test_apply_action_marks_plan_failed_on_krill_error` missing |
| ASPA view action tests | `tests/test_provider_write.py:L1619` | **Substantial** (9 tests) | — |

---

## 2. Object and Data Structures

### 2.1 Krill ASPA Delta Wire Format

`_submit_krill_aspa_delta()` POSTs to `GET /api/v1/cas/<ca>/aspas` (GET reads, same URL receives POST for writes):

```
POST /api/v1/cas/<ca>/aspas
Content-Type: application/json
Authorization: Bearer <api_key>

{
  "add": [
    {"customer": "AS65001", "providers": ["AS65002", "AS65003"]},
    …
  ],
  "remove": [
    {"customer": "AS65004", "providers": ["AS65005"]},
    …
  ]
}
```

`_serialize_krill_aspa_delta()` translates the internal format (`customer_asn: int`, `provider_asns: [int]`) to the Krill wire format (`customer: "ASN"`, `providers: ["ASN"]`). This serialization is complete but untested.

### 2.2 Internal Delta Format (`build_aspa_change_plan_delta()`)

```python
{
    "added":   [{"customer_asn": 65001, "provider_asns": [65002, 65003], "customer": "AS65001", "providers": [...]}],
    "removed": [{"customer_asn": 65004, "provider_asns": [65005], ...}],
}
```

Semantic-to-operation mapping:

| `plan_semantic` | `provider_operation` | Delta bucket |
|---|---|---|
| `CREATE` | `ADD_PROVIDER_SET` | `added` |
| `REPLACE` | `ADD_PROVIDER_SET` | `added` |
| `RESHAPE` | `ADD_PROVIDER_SET` | `added` |
| `WITHDRAW` | `REMOVE_PROVIDER_SET` | `removed` |
| `REMOVE_PROVIDER` | `REMOVE_PROVIDER_SET` | `removed` |
| `ADD_PROVIDER` | `ADD_PROVIDER_SET` | _excluded_ (no provider_operation set on ADD_PROVIDER items by design) |

> Note: `ADD_PROVIDER` items intentionally have no `provider_operation` and are excluded from `build_aspa_change_plan_delta()` (the underlying RESHAPE item carries the full updated provider set for the same customer). This is correct — Krill's delta format is full-customer-set semantics, not per-provider additive.

### 2.3 `approve_aspa_change_plan()` vs `approve_roa_change_plan()`

ASPA approval is intentionally lighter than ROA:

- **No lint gate** — no `ASPALintRun` model exists; this is explicitly deferred to a future slice when `aspa_lint.py` is added (see Priority 4 plan cross-reference).
- **No simulation gate** — no ASPA simulation analogue exists.
- **Approval record created** via `_create_approval_record_for_plan()` with the `aspa_change_plan=plan` payload key.
- `summary_json` **not updated** at approval time (correct — ROA updates it for simulation-review audit; no ASPA analogue).

---

## 3. Architectural Decisions

| # | Decision | Rationale |
|---|---|---|
| AD-3-1 | `ASPAChangePlanApprovalForm` overrides `__init__` to remove `acknowledged_findings`, `previously_acknowledged_findings`, `acknowledged_simulation_results`, `lint_acknowledgement_notes` fields inherited from `ROAChangePlanApprovalForm` | ROA lint/simulation fields are irrelevant for ASPA; rendering them causes operator confusion. Subclassing `ROAChangePlanApprovalForm` is still correct to inherit the governance fields without duplication. Note: `previously_acknowledged_findings` was also added to the pop list (not in the original plan spec) — correct. |
| AD-3-2 | `ASPAChangePlanApproveActionSerializer` is redefined with exactly the 5 governance fields + the same `validate()` calling `validate_maintenance_window_bounds()` | Inheriting the ROA serializer causes the spurious `acknowledged_finding_ids`/`acknowledged_simulation_result_ids`/`lint_acknowledgement_notes` fields to appear in the API schema and, if submitted by callers, would be passed through `**validated_data` to `approve_aspa_change_plan()` which does not accept them — raising `TypeError` (500 error) |
| AD-3-3 | No ASPA lint gate added to `approve_aspa_change_plan()` now | Consistent with current codebase; deferred to after `aspa_lint.py` is built under Priority 4. Cross-reference: Priority 4 plan notes the ASPA lint gate as an explicit deferred item |
| AD-3-4 | `ProviderWriteExecution.aspa_change_plan` FK and `exactly_one_plan_target` constraint are already in place | No model changes needed in this slice — confirmed by code inspection |
| AD-3-5 | Test fixtures create ASPA plans via `create_aspa_change_plan(reconciliation_run)` (the real service, not a test factory) in service tests; view/API tests may use `create_test_aspa_change_plan()` factory if available | Mirrors the ROA test pattern — service layer tests exercise the real creation path rather than bypassing it with fixtures |

---

## 4. Slice A — Serializer and Form Hygiene ✅ DONE

**Goal:** Remove the inherited ROA-specific lint/simulation fields from the ASPA approval form and API serializer, preventing invalid API inputs from causing `TypeError` and hiding irrelevant UI widgets.

**Status (2026-04-14):** Both components are implemented. See open defect note below.

### 4.1 `ASPAChangePlanApproveActionSerializer` (api/serializers.py) ✅

~~Replace the current `pass` body with an explicit definition containing only the five governance fields~~ — already implemented as:

```python
class ASPAChangePlanApproveActionSerializer(serializers.Serializer):
    ticket_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    change_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    maintenance_window_start = serializers.DateTimeField(required=False, allow_null=True)
    maintenance_window_end = serializers.DateTimeField(required=False, allow_null=True)
    approval_notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        models.validate_maintenance_window_bounds(
            start_at=attrs.get('maintenance_window_start'),
            end_at=attrs.get('maintenance_window_end'),
        )
        return attrs
```

**Why not inherit from `ROAChangePlanApproveActionSerializer`:** The parent's `validate()` is the only reusable piece, and it calls `validate_maintenance_window_bounds()` directly. Inheriting saves 1 line while pulling in 3 unwanted fields that can cause runtime errors.

### 4.2 `ASPAChangePlanApprovalForm` (forms.py) ✅ (with open defect)

~~Override `__init__` to delete the ROA-specific fields after calling `super().__init__()`, and replace with a ASPA-specific `fieldsets`~~ — already implemented. The actual implementation pops 4 fields (`acknowledged_findings`, `previously_acknowledged_findings`, `acknowledged_simulation_results`, `lint_acknowledgement_notes`) and uses this `fieldsets`:

```python
class ASPAChangePlanApprovalForm(ROAChangePlanApprovalForm):
    fieldsets = (
        FieldSet(
            'requires_secondary_approval',
            'ticket_reference',
            'change_reference',
            'maintenance_window_start',
            'maintenance_window_end',
            'approval_notes',
            name='Governance',
        ),
    )

    def __init__(self, *args, plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in (
            'acknowledged_findings',
            'previously_acknowledged_findings',
            'acknowledged_simulation_results',
            'lint_acknowledgement_notes',
        ):
            self.fields.pop(field_name, None)

    def clean(self):
        cleaned_data = ConfirmationForm.clean(self)
        validate_maintenance_window_bounds(
            start_at=cleaned_data.get('maintenance_window_start'),
            end_at=cleaned_data.get('maintenance_window_end'),
        )
        return cleaned_data
```

**Open defect:** `fieldsets` includes `requires_secondary_approval` but `test_approve_form_exposes_only_governance_fields` (L1718) asserts it is absent from `form.fields.keys()`. Since `requires_secondary_approval` is NOT popped in `__init__`, it IS present in `fields` — the test is currently failing. Resolution options:
- **Option A (preferred):** Also pop `requires_secondary_approval` in `__init__` if ASPA approval does not support secondary-approval workflow.
- **Option B:** Update the test to include `requires_secondary_approval` in the expected field list if the feature is intentionally supported for ASPA.

Needs a decision before the Slice B test suite is written (the service test setup assumptions differ depending on whether secondary approval is wired up for ASPA).

**Rationale (original):** `ROAChangePlanApprovalForm` has a complex `__init__` that does queryset setup for lint findings and simulation results — neither accessor exists on `ASPAChangePlan`. The fields still appeared in the rendered form with confusing messages. Deleting them post-`super().__init__()` is the correct fix.

> **Note:** The approval view's `post()` handler already reads only the governance fields from `form.cleaned_data`, so no view change is needed.

### 4.3 Slice A Verification (already passing except the `requires_secondary_approval` defect)

```bash
# Run the ASPA change plan action tests (fast smoke check)
cd /home/mencken/src/netbox-v4.5.7/netbox && \
  NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput \
  netbox_rpki.tests.test_provider_write.ASPAChangePlanActionAPITestCase \
  netbox_rpki.tests.test_provider_write.ASPAChangePlanActionViewTestCase

# Confirm the serializer no longer exposes lint/simulation fields:
cd /home/mencken/src/netbox_rpki && \
  python -c "
from netbox_rpki.api.serializers import ASPAChangePlanApproveActionSerializer
s = ASPAChangePlanApproveActionSerializer()
fields = list(s.fields.keys())
assert 'acknowledged_finding_ids' not in fields, f'Unexpected field: acknowledged_finding_ids in {fields}'
assert 'acknowledged_simulation_result_ids' not in fields
assert 'lint_acknowledgement_notes' not in fields
print('OK:', fields)
"
```

---

## 5. Slice B — Service-Layer Unit Tests ❌ NOT STARTED

**Goal:** Achieve test parity with `ProviderWriteServiceTestCase` (ROA) via a new `ASPAProviderWriteServiceTestCase`. These are Django `TestCase` unit tests that exercise the real ASPA change-plan and provider-write services while mocking only the Krill submission seam (`_submit_krill_aspa_delta`) and the follow-up sync (`sync_provider_account`).

**File:** `netbox_rpki/tests/test_provider_write.py` — add after `ProviderWriteServiceTestCase` (currently at the top of the file; no `ASPAProviderWriteServiceTestCase` exists yet).

**Current contract note:** ASPA approval now supports `requires_secondary_approval`; Slice B should treat that as part of the supported governance contract, not as an unresolved prerequisite.

### 5.1 Test Setup

Use the current helper and model contract, which represents ASPA intent and imported ASPA state as customer/provider rows rather than a single provider-set field on one row.

```python
class ASPAProviderWriteServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='aspa-write-org', name='ASPA Write Org')
        cls.customer_as = create_test_asn(65200)
        cls.provider_as_a = create_test_asn(65201)
        cls.provider_as_b = create_test_asn(65202)
        cls.orphaned_customer_as = create_test_asn(65299)
        cls.orphaned_provider_as = create_test_asn(65300)

        cls.provider_account = create_test_provider_account(
            name='ASPA Krill Write Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-ASPA-WRITE',
            ca_handle='ca-aspa-write',
            api_base_url='https://krill.example.invalid',
            api_key='aspa-krill-token',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='ASPA Krill Write Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

        # Intent: one customer ASN with two intended providers, represented as two ASPAIntent rows.
        cls.intent_a = create_test_aspa_intent(
            name='ASPA Write Intent A',
            organization=cls.organization,
            customer_as=cls.customer_as,
            provider_as=cls.provider_as_a,
        )
        cls.intent_b = create_test_aspa_intent(
            name='ASPA Write Intent B',
            organization=cls.organization,
            customer_as=cls.customer_as,
            provider_as=cls.provider_as_b,
        )

        # Imported orphaned ASPA: one customer with one provider and no matching intent.
        cls.orphaned_imported_aspa = create_test_imported_aspa(
            name='Orphaned Imported ASPA',
            provider_snapshot=cls.provider_snapshot,
            organization=cls.organization,
            customer_as=cls.orphaned_customer_as,
            customer_as_value=cls.orphaned_customer_as.asn,
        )
        create_test_imported_aspa_provider(
            imported_aspa=cls.orphaned_imported_aspa,
            provider_as=cls.orphaned_provider_as,
            provider_as_value=cls.orphaned_provider_as.asn,
        )

        cls.reconciliation_run = reconcile_aspa_intents(
            cls.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.plan = create_aspa_change_plan(cls.reconciliation_run)
```

Implementation notes for the fixture:

- Import `create_test_imported_aspa_provider`; the imported ASPA helper does not accept a `provider_asns=[...]` list.
- Use `reconcile_aspa_intents(...)`, which matches the current test file and service export surface. `run_aspa_reconciliation_pipeline(...)` is also valid, but use one consistently.
- The baseline fixture above naturally produces:
  - one create or reshape path for customer `AS65200`
  - one withdraw path for orphaned customer `AS65299`
- Because ASPA deltas are customer-set based, assertions should focus on the resulting `customer_asn` plus the full `provider_asns` list in each delta entry, not on one-intent-row-per-delta-entry assumptions.

### 5.2 Tests to Implement

#### Delta and serialization tests

**`test_build_aspa_delta_separates_create_and_withdraw_by_semantic`**

Confirm that CREATE items land in `added`, WITHDRAW items in `removed`, with the correct `customer_asn` and `provider_asns` in each entry:

```python
delta = build_aspa_change_plan_delta(self.plan)

self.assertIn('added', delta)
self.assertIn('removed', delta)

added_customers = {e['customer_asn'] for e in delta['added']}
removed_customers = {e['customer_asn'] for e in delta['removed']}

self.assertIn(self.customer_asn.asn, added_customers)
self.assertIn(self.orphaned_customer_asn.asn, removed_customers)
```

**`test_build_aspa_delta_replace_lands_in_added_only`**

Build a plan where a REPLACE semantic fires for an existing customer with a materially different provider set. Confirm the REPLACE item uses `ADD_PROVIDER_SET` and contributes only to the `added` bucket.

```python
replace_snapshot = create_test_provider_snapshot(
    name='ASPA Replace Snapshot',
    organization=self.organization,
    provider_account=self.provider_account,
    provider_name='Krill',
    status=rpki_models.ValidationRunStatus.COMPLETED,
)
replace_imported_aspa = create_test_imported_aspa(
    name='ASPA Replace Imported',
    provider_snapshot=replace_snapshot,
    organization=self.organization,
    customer_as=self.customer_as,
    customer_as_value=self.customer_as.asn,
)
create_test_imported_aspa_provider(
    imported_aspa=replace_imported_aspa,
    provider_as=create_test_asn(65210),
    provider_as_value=65210,
)
replace_reconciliation = reconcile_aspa_intents(
    self.organization,
    comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
    provider_snapshot=replace_snapshot,
)
replace_plan = create_aspa_change_plan(replace_reconciliation, name='ASPA Replace Plan')
delta = build_aspa_change_plan_delta(replace_plan)

replace_item = replace_plan.items.get(plan_semantic=rpki_models.ASPAChangePlanItemSemantic.REPLACE)
self.assertEqual(replace_item.provider_operation, rpki_models.ProviderWriteOperation.ADD_PROVIDER_SET)
added_customers = {entry['customer_asn'] for entry in delta.get('added', [])}
removed_customers = {entry['customer_asn'] for entry in delta.get('removed', [])}
self.assertIn(self.customer_as.asn, added_customers)
self.assertNotIn(self.customer_as.asn, removed_customers)
```

**`test_serialize_krill_aspa_delta_converts_asn_integers_to_as_prefixed_strings`**

Direct unit test of `_serialize_krill_aspa_delta`:

```python
from netbox_rpki.services.provider_write import _serialize_krill_aspa_delta

internal = {
    'added': [{'customer_asn': 65001, 'provider_asns': [65002, 65003]}],
    'removed': [{'customer_asn': 65004, 'provider_asns': [65005]}],
}
wire = _serialize_krill_aspa_delta(internal)

self.assertEqual(wire, {
    'add': [{'customer': 'AS65001', 'providers': ['AS65002', 'AS65003']}],
    'remove': [{'customer': 'AS65004', 'providers': ['AS65005']}],
})
```

**`test_serialize_krill_aspa_delta_handles_empty_provider_list_for_withdraw`**

```python
internal = {'added': [], 'removed': [{'customer_asn': 65010, 'provider_asns': []}]}
wire = _serialize_krill_aspa_delta(internal)
self.assertEqual(wire['remove'], [{'customer': 'AS65010', 'providers': []}])
```

#### Preview test

**`test_preview_records_execution_without_applying`**

```python
execution, delta = preview_aspa_change_plan_provider_write(self.plan, requested_by='preview-user')

self.assertEqual(execution.execution_mode, rpki_models.ProviderWriteExecutionMode.PREVIEW)
self.assertEqual(execution.status, rpki_models.ValidationRunStatus.COMPLETED)
self.assertEqual(execution.requested_by, 'preview-user')
self.assertEqual(execution.request_payload_json, delta)
# Plan must NOT be mutated during preview
self.plan.refresh_from_db()
self.assertEqual(self.plan.status, rpki_models.ASPAChangePlanStatus.DRAFT)
```

#### Approve tests

**`test_approve_transitions_plan_to_approved`**

```python
plan = create_aspa_change_plan(self.reconciliation_run, name='ASPA Approval Plan')
approve_aspa_change_plan(plan, approved_by='aspa-approver')
plan.refresh_from_db()

self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.APPROVED)
self.assertIsNotNone(plan.approved_at)
self.assertEqual(plan.approved_by, 'aspa-approver')
```

**`test_approve_records_governance_metadata_and_approval_record`**

```python
approve_aspa_change_plan(
    plan,
    approved_by='aspa-approver',
    ticket_reference='ASPA-CHG-1',
    change_reference='ASPA-CAB-1',
    maintenance_window_start=window_start,
    maintenance_window_end=window_end,
    approval_notes='ASPA window note.',
)
plan.refresh_from_db()
approval_record = plan.approval_records.get()

self.assertEqual(plan.ticket_reference, 'ASPA-CHG-1')
self.assertEqual(plan.change_reference, 'ASPA-CAB-1')
self.assertEqual(approval_record.disposition, rpki_models.ValidationDisposition.ACCEPTED)
self.assertEqual(approval_record.recorded_by, 'aspa-approver')
self.assertEqual(approval_record.ticket_reference, 'ASPA-CHG-1')
self.assertEqual(approval_record.notes, 'ASPA window note.')
```

**`test_approve_rejects_already_approved_plan`**

```python
approve_aspa_change_plan(plan, approved_by='first-approver')
with self.assertRaisesMessage(ProviderWriteError, 'Only draft ASPA change plans can be approved'):
    approve_aspa_change_plan(plan, approved_by='second-approver')
```

**`test_approve_rejects_non_provider_backed_plan`**

A plan with no `provider_account` (LOCAL scope plan) should fail ASPA write-capability gating.

```python
local_reconciliation_run = reconcile_aspa_intents(
    self.organization,
    comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
)
local_plan = create_aspa_change_plan(local_reconciliation_run, name='ASPA Local Plan')
with self.assertRaisesMessage(ProviderWriteError, 'not provider-backed'):
    approve_aspa_change_plan(local_plan, approved_by='approver')
```

#### Apply tests

**`test_apply_submits_delta_records_execution_and_triggers_followup_sync`**

Critical lifecycle test (mirrors `test_apply_submits_delta_records_execution_and_triggers_followup_sync` in ROA):

```python
approve_aspa_change_plan(plan, approved_by='apply-approver', ticket_reference='ASPA-APPLY-CHG', ...)

with patch(
    'netbox_rpki.services.provider_write._submit_krill_aspa_delta',
    return_value={'message': 'accepted'},
) as submit_mock:
    with patch(
        'netbox_rpki.services.provider_write.sync_provider_account',
        return_value=(followup_sync_run, followup_snapshot),
    ) as sync_mock:
        execution, delta = apply_aspa_change_plan_provider_write(plan, requested_by='apply-user')

plan.refresh_from_db()
self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.APPLIED)
self.assertIsNotNone(plan.apply_started_at)
self.assertEqual(plan.apply_requested_by, 'apply-user')
self.assertIsNotNone(plan.applied_at)
self.assertIsNone(plan.failed_at)
self.assertEqual(execution.execution_mode, rpki_models.ProviderWriteExecutionMode.APPLY)
self.assertEqual(execution.status, rpki_models.ValidationRunStatus.COMPLETED)
self.assertEqual(execution.followup_sync_run, followup_sync_run)
self.assertEqual(execution.followup_provider_snapshot, followup_snapshot)
self.assertEqual(execution.request_payload_json, delta)
self.assertEqual(execution.response_payload_json['provider_response'], {'message': 'accepted'})
self.assertIn('delta_summary', execution.response_payload_json)
self.assertIn('governance', execution.response_payload_json)

# Krill was called with the internal delta; serialization is covered separately by
# test_serialize_krill_aspa_delta_converts_asn_integers_to_as_prefixed_strings.
submit_mock.assert_called_once_with(self.provider_account, delta)
sync_mock.assert_called_once()
```

**Key assertion:** `execution.response_payload_json['delta_summary']` must contain `customer_count`, `create_count`, `withdraw_count`, `provider_add_count`, `provider_remove_count` — verify these are populated from the internal delta.

**`test_apply_rejects_repeat_apply`**

```python
approve_aspa_change_plan(plan, approved_by='approver')
with patch('netbox_rpki.services.provider_write._submit_krill_aspa_delta', return_value={}):
    with patch('netbox_rpki.services.provider_write.sync_provider_account', return_value=...):
        apply_aspa_change_plan_provider_write(plan)

with self.assertRaisesMessage(ProviderWriteError, 'already been applied'):
    apply_aspa_change_plan_provider_write(plan)
```

**`test_apply_failure_marks_plan_failed_and_records_error`**

```python
approve_aspa_change_plan(plan, approved_by='failure-approver')

with patch(
    'netbox_rpki.services.provider_write._submit_krill_aspa_delta',
    side_effect=RuntimeError('krill rejected aspa delta'),
):
    with self.assertRaisesMessage(ProviderWriteError, 'krill rejected aspa delta'):
        apply_aspa_change_plan_provider_write(plan, requested_by='failed-apply-user')

plan.refresh_from_db()
self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.FAILED)
self.assertIsNotNone(plan.failed_at)
execution = plan.provider_write_executions.get(execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY)
self.assertEqual(execution.status, rpki_models.ValidationRunStatus.FAILED)
self.assertEqual(execution.error, 'krill rejected aspa delta')
```

**`test_apply_failure_during_followup_sync_records_partial_success`**

Tests the specific path where Krill write succeeds but `sync_provider_account()` raises:

```python
plan → APPLIED (applied_at set) but execution.status == FAILED, execution.error contains sync error message
```

```python
with patch('netbox_rpki.services.provider_write._submit_krill_aspa_delta', return_value={}):
    with patch(
        'netbox_rpki.services.provider_write.sync_provider_account',
        side_effect=RuntimeError('provider unreachable during followup'),
    ):
        execution, _ = apply_aspa_change_plan_provider_write(plan)

plan.refresh_from_db()
self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.APPLIED)  # write succeeded
self.assertEqual(execution.status, rpki_models.ValidationRunStatus.FAILED)  # sync failed
self.assertIn('followup_sync', execution.response_payload_json)
self.assertEqual(execution.response_payload_json['followup_sync']['status'], rpki_models.ValidationRunStatus.FAILED)
```

**`test_capability_gating_rejects_unsupported_provider_type`**

A plan bound to an unsupported provider type such as ARIN should fail at the provider-write capability gate.

```python
arin_account = create_test_provider_account(
    name='ARIN ASPA Unsupported',
    organization=self.organization,
    provider_type=rpki_models.ProviderType.ARIN,
    org_handle='ORG-ARIN-ASPA',
)
unsupported_snapshot = create_test_provider_snapshot(
    name='ARIN ASPA Unsupported Snapshot',
    organization=self.organization,
    provider_account=arin_account,
    provider_name='ARIN',
    status=rpki_models.ValidationRunStatus.COMPLETED,
)
unsupported_reconciliation = create_test_aspa_reconciliation_run(
    name='Unsupported ASPA Reconciliation',
    organization=self.organization,
    provider_snapshot=unsupported_snapshot,
    comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
)
unsupported_plan = create_test_aspa_change_plan(
    name='Unsupported ASPA Plan',
    organization=self.organization,
    source_reconciliation_run=unsupported_reconciliation,
    provider_account=arin_account,
    provider_snapshot=unsupported_snapshot,
)

with self.assertRaisesMessage(ProviderWriteError, 'does not support ASPA write operations'):
    build_aspa_change_plan_delta(unsupported_plan)
```

### 5.2.1 Recommended imports for Slice B

The new service testcase will need these additional imports beyond the current ASPA API/view test block:

```python
from netbox_rpki.services.provider_write import _serialize_krill_aspa_delta
from netbox_rpki.tests.utils import (
    create_test_aspa_change_plan,
    create_test_aspa_intent,
    create_test_aspa_reconciliation_run,
    create_test_imported_aspa,
    create_test_imported_aspa_provider,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_provider_sync_run,
)
```

### 5.3 Slice B Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
  NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput \
  netbox_rpki.tests.test_provider_write.ASPAProviderWriteServiceTestCase
```

---

## 6. Slice C — API and View Test Parity ⚠️ MOSTLY DONE

**Goal:** Fill test gaps in the existing `ASPAChangePlanActionAPITestCase` and `ASPAChangePlanActionViewTestCase` to match the depth of their ROA equivalents.

**Status (2026-04-14):** Both classes have grown substantially beyond the "thin" characterisation in this plan. Most targets below are already present; only items marked **MISSING** need to be added.

**File:** `netbox_rpki/tests/test_provider_write.py` — extend existing ASPA test classes.

### 6.1 API Test Additions (`ASPAChangePlanActionAPITestCase`)

Current tests (9): `test_create_plan_action_returns_plan`, `test_preview_action_returns_delta_and_execution`, `test_approve_action_transitions_plan`, `test_approve_action_rejects_invalid_maintenance_window`, `test_approve_serializer_exposes_only_governance_fields`, `test_approve_serializer_drops_roa_only_acknowledgement_inputs`, `test_apply_action_runs_provider_write_flow`, `test_summary_action_returns_aggregate_counts`, `test_custom_actions_require_change_permission`.

**`test_approve_action_records_governance_metadata`** — covered by `test_approve_action_transitions_plan` (checks `ticket_reference` and `approval_record.ticket_reference`) ✅

```python
url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-approve', kwargs={'pk': self.plan.pk})
response = self.client.post(
    url,
    {
        'ticket_reference': 'ASPA-CHG-100',
        'change_reference': 'ASPA-CAB-10',
        'maintenance_window_start': '2026-04-12T22:00:00Z',
        'maintenance_window_end': '2026-04-12T23:00:00Z',
        'approval_notes': 'ASPA API approval note',
    },
    format='json', **self.header,
)
self.assertHttpStatus(response, 200)
self.plan.refresh_from_db()
self.assertEqual(self.plan.ticket_reference, 'ASPA-CHG-100')
self.assertEqual(self.plan.change_reference, 'ASPA-CAB-10')
self.assertIn('approval_record', response.data)
self.assertEqual(response.data['approval_record']['ticket_reference'], 'ASPA-CHG-100')
```

**`test_approve_action_rejects_lint_find_ids_not_in_schema`** — covered by `test_approve_serializer_drops_roa_only_acknowledgement_inputs` (passes data with those fields, asserts `is_valid()` succeeds but fields are absent from `validated_data`) ✅

Confirm that `acknowledged_finding_ids` is NOT accepted by the ASPA serializer (post-fix), i.e., submitting it does not cause a 500:

```python
response = self.client.post(
    url,
    {'acknowledged_finding_ids': [999]},
    format='json', **self.header,
)
# After Slice A fix: either 400 (field rejected) or 200 with field silently ignored
# Acceptable either way, but should never be 500
self.assertNotEqual(response.status_code, 500)
```

**`test_apply_action_records_governance_metadata_in_response`** — the existing `test_apply_action_runs_provider_write_flow` mocks `apply_aspa_change_plan_provider_write` wholesale and returns a pre-built execution; `governance` key in `response_payload_json` is not exercised. Low priority since the service-layer test covers it. ✅ (acceptable)

**`test_apply_action_marks_plan_failed_on_krill_error`** — **MISSING** ❌

```python
approve_aspa_change_plan(self.plan, ...)
url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-apply', kwargs={'pk': self.plan.pk})
with patch('netbox_rpki.services.provider_write._submit_krill_aspa_delta', side_effect=RuntimeError('krill down')):
    response = self.client.post(url, {}, format='json', **self.header)

self.assertHttpStatus(response, 400)
self.plan.refresh_from_db()
self.assertEqual(self.plan.status, rpki_models.ASPAChangePlanStatus.FAILED)
```

> Note: This test must NOT mock `apply_aspa_change_plan_provider_write` — it needs to call the real service so the Krill mock fires.

**`test_custom_actions_require_change_permission`** — already present, already includes `apply` in the loop ✅

### 6.2 View Test Additions (`ASPAChangePlanActionViewTestCase`)

Current tests (9): `test_reconciliation_run_detail_shows_create_plan_button`, `test_reconciliation_run_create_plan_view_creates_plan`, `test_change_plan_detail_shows_preview_and_approve_buttons`, `test_preview_view_renders_delta`, `test_approve_view_renders_and_persists_governance_fields`, `test_approve_form_exposes_only_governance_fields`, `test_approve_view_hides_roa_only_acknowledgement_inputs`, `test_apply_view_shows_governance_metadata_after_approval`, `test_unsupported_provider_plan_hides_write_buttons`.

**`test_approve_view_renders_governance_fields_without_lint_or_simulation_fields`** — covered by `test_approve_view_hides_roa_only_acknowledgement_inputs` and the GET half of `test_approve_view_renders_and_persists_governance_fields` ✅

**`test_approve_view_persists_governance_fields`** — covered by `test_approve_view_renders_and_persists_governance_fields` ✅

**`test_apply_view_shows_governance_metadata_after_approval`** — present as `test_apply_view_shows_governance_metadata_after_approval` ✅

**`test_unsupported_provider_plan_hides_write_buttons_for_aspa`** — present as `test_unsupported_provider_plan_hides_write_buttons` ✅

### 6.3 Slice C Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
  NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput \
  netbox_rpki.tests.test_provider_write.ASPAChangePlanActionAPITestCase \
  netbox_rpki.tests.test_provider_write.ASPAChangePlanActionViewTestCase
```

---

## 7. Closure Criteria

| Criterion | Status | Verification |
|---|---|---|
| `ASPAChangePlanApproveActionSerializer` has no lint/simulation fields | ✅ Done | `test_approve_serializer_exposes_only_governance_fields` passes |
| `ASPAChangePlanApprovalForm` renders governance fields only | ✅ Done | `test_approve_view_hides_roa_only_acknowledgement_inputs` passes |
| Submitting `acknowledged_finding_ids` via ASPA approve API does not 500 | ✅ Done | `test_approve_serializer_drops_roa_only_acknowledgement_inputs` passes |
| `requires_secondary_approval` fieldset/field discrepancy resolved | ❌ Open defect | `test_approve_form_exposes_only_governance_fields` passes (currently failing or field decision needed) |
| Full ASPA preview → approve → apply lifecycle passes | ❌ Needs Slice B | `test_apply_submits_delta_records_execution_and_triggers_followup_sync` passes |
| Krill wire-format delta serialization is unit-tested | ❌ Needs Slice B | `test_serialize_krill_aspa_delta_converts_asn_integers_to_as_prefixed_strings` passes |
| Apply failure path marks plan FAILED | ❌ Needs Slice B | `test_apply_failure_marks_plan_failed_and_records_error` passes |
| Followup-sync failure marks execution FAILED while plan stays APPLIED | ❌ Needs Slice B | `test_apply_failure_during_followup_sync_records_partial_success` passes |
| Apply API action exercises real Krill failure path | ❌ Needs Slice C | `test_apply_action_marks_plan_failed_on_krill_error` passes |
| All existing ASPA provider write tests pass unchanged | ✅ (9 API + 9 view passing) | Full `test_provider_write` suite clean |
| All existing `test_aspa_change_plan` tests pass unchanged | ✅ (no regressions) | No regressions from Slice A form change |

---

## 8. Full Verification Command (All Slices)

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
  NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput \
  netbox_rpki.tests.test_provider_write \
  netbox_rpki.tests.test_aspa_change_plan \
  netbox_rpki.tests.test_api.AspaChangePlanActionAPITestCase
```

Or via devrun:

```bash
cd /home/mencken/src/netbox_rpki/devrun && ./dev.sh test full
```

---

## 9. Deferred Scope

The following items are explicitly **out of scope** for Priority 3 and tracked elsewhere:

| Item | Reason |
|---|---|
| ASPA lint gate in `approve_aspa_change_plan()` | No `aspa_lint.py` exists yet; gating requires an `ASPALintRun` model. Deferred to the ASPA-lint slice within Priority 4 (which currently notes ASPA lint as a future extension). |
| ASPA validation simulation | No simulation analogue exists for ASPA intent. No plan to add this in Priority 4 either. |
| ASPA write-back for providers other than Krill | `ProviderAspaWriteMode` currently has only `KRILL_ASPA_DELTA`. Other provider adapters deferred. |
| ASPA change plan detail template enhancements | Template reuses `roachangeplan_preview.html` / `roachangeplan_confirm.html` which are adequate; deeper ASPA-specific templating deferred to Priority 2 (UI hardening). |
| Per-item `before_state_json` / `after_state_json` population for ASPA | Currently blank in most cases unless set by `aspa_change_plan.py`. Enriching these for diff display is a separate UI slice. |

---

## 10. Slice Ordering Recommendation

1. ~~**Slice A first** — highest risk/impact, easiest to implement, immediate user-visible regression fix.~~ **DONE.**
2. **Resolve `requires_secondary_approval` defect** — decide whether to pop the field in `ASPAChangePlanApprovalForm.__init__` or update the test. ~15 min.
3. **Slice B** — service-layer tests are the primary remaining gap. ~2 hr.
4. **Slice C remainder** — add `test_apply_action_marks_plan_failed_on_krill_error`. ~20 min.

Remaining estimated scope: ~2.5 hours.
