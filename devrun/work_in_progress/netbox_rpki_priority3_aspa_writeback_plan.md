# Priority 3: ASPA Write-Back — Implementation Plan

**Target:** complete, harden, and fully test the Krill ASPA provider write-back lifecycle (preview → approve → apply).

---

## 1. Actual Current State

Despite the backlog labelling this "Partially complete", inspection shows the **core service infrastructure is virtually finished**. The remaining work is limited to two broken form/serializer subclasses and significant test-coverage gaps.

| Component | File | Status | Gap |
|---|---|---|---|
| `create_aspa_change_plan()` | `services/aspa_change_plan.py` | **Complete** | — |
| `build_aspa_change_plan_delta()` | `services/provider_write.py:L~175` | **Complete** | — |
| `_serialize_krill_aspa_delta()` | `services/provider_write.py:L~677` | **Complete** | No unit test |
| `_submit_krill_aspa_delta()` | `services/provider_write.py:L~699` | **Complete** | — |
| `preview_aspa_change_plan_provider_write()` | `services/provider_write.py:L599` | **Complete** | — |
| `approve_aspa_change_plan()` | `services/provider_write.py:L485` | **Complete** | No governance tests |
| `apply_aspa_change_plan_provider_write()` | `services/provider_write.py:L795` | **Complete** | No failure/repeat tests |
| `ASPAChangePlanPreviewView` | `views.py:L1482` | **Complete** | — |
| `ASPAChangePlanApproveView` | `views.py:L1618` | **Complete** | Uses broken form |
| `ASPAChangePlanApplyView` | `views.py:L1671` | **Complete** | — |
| `ASPAChangePlanViewSet` | `api/views.py:L856` | **Complete** | — |
| `ASPAChangePlanApprovalForm` | `forms.py:L243` | **BROKEN** — `pass` subclass of ROA form | Slice A |
| `ASPAChangePlanApproveActionSerializer` | `api/serializers.py:L742` | **BROKEN** — `pass` subclass of ROA serializer | Slice A |
| `ASPAProviderWriteServiceTestCase` | _missing_ | **Absent** | Slice B |
| ASPA API action tests | `tests/test_provider_write.py:L1262` | **Thin** (5 tests) | Slice C |
| ASPA view action tests | `tests/test_provider_write.py:L1388` | **Thin** (7 tests) | Slice C |

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
| AD-3-1 | `ASPAChangePlanApprovalForm` overrides `__init__` to remove `acknowledged_findings`, `acknowledged_simulation_results`, `lint_acknowledgement_notes` fields inherited from `ROAChangePlanApprovalForm` | ROA lint/simulation fields are irrelevant for ASPA; rendering them causes operator confusion. Subclassing `ROAChangePlanApprovalForm` is still correct to inherit the 5 governance fields without duplication |
| AD-3-2 | `ASPAChangePlanApproveActionSerializer` is redefined with exactly the 5 governance fields + the same `validate()` calling `validate_maintenance_window_bounds()` | Inheriting the ROA serializer causes the spurious `acknowledged_finding_ids`/`acknowledged_simulation_result_ids`/`lint_acknowledgement_notes` fields to appear in the API schema and, if submitted by callers, would be passed through `**validated_data` to `approve_aspa_change_plan()` which does not accept them — raising `TypeError` (500 error) |
| AD-3-3 | No ASPA lint gate added to `approve_aspa_change_plan()` now | Consistent with current codebase; deferred to after `aspa_lint.py` is built under Priority 4. Cross-reference: Priority 4 plan notes the ASPA lint gate as an explicit deferred item |
| AD-3-4 | `ProviderWriteExecution.aspa_change_plan` FK and `exactly_one_plan_target` constraint are already in place | No model changes needed in this slice — confirmed by code inspection |
| AD-3-5 | Test fixtures create ASPA plans via `create_aspa_change_plan(reconciliation_run)` (the real service, not a test factory) in service tests; view/API tests may use `create_test_aspa_change_plan()` factory if available | Mirrors the ROA test pattern — service layer tests exercise the real creation path rather than bypassing it with fixtures |

---

## 4. Slice A — Serializer and Form Hygiene

**Goal:** Remove the inherited ROA-specific lint/simulation fields from the ASPA approval form and API serializer, preventing invalid API inputs from causing `TypeError` and hiding irrelevant UI widgets.

### 4.1 `ASPAChangePlanApproveActionSerializer` (api/serializers.py)

Replace the current `pass` body with an explicit definition containing only the five governance fields:

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

### 4.2 `ASPAChangePlanApprovalForm` (forms.py)

Override `__init__` to delete the ROA-specific fields after calling `super().__init__()`, and replace with a ASPA-specific `fieldsets`:

```python
class ASPAChangePlanApprovalForm(ROAChangePlanApprovalForm):
    fieldsets = (
        FieldSet(
            'ticket_reference',
            'change_reference',
            'maintenance_window_start',
            'maintenance_window_end',
            'approval_notes',
            name='Governance',
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('acknowledged_findings', 'acknowledged_simulation_results', 'lint_acknowledgement_notes'):
            self.fields.pop(field_name, None)
```

**Rationale:** `ROAChangePlanApprovalForm` has a complex `__init__` that does queryset setup for lint findings and simulation results on `plan.lint_runs` and `plan.simulation_runs` — neither accessor exists on `ASPAChangePlan`, so `getattr(plan, 'lint_runs', None)` returns `None` and the code silently falls through without crashing. However, the fields still appear in the rendered form with confusing messages ("No current unsuppressed acknowledgement-required lint findings remain to acknowledge."). Deleting them post-`super().__init__()` is the correct fix.

> **Note:** The approval view's `post()` handler already reads only the 5 governance fields from `form.cleaned_data`, so no view change is needed — this is purely a rendered-form cleanup.

### 4.3 Slice A Verification

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

## 5. Slice B — Service-Layer Unit Tests

**Goal:** Achieve test parity with `ProviderWriteServiceTestCase` (ROA, 16 tests) via a new `ASPAProviderWriteServiceTestCase`. These are pure Django `TestCase` unit tests that mock only the Krill HTTP layer (`_submit_krill_aspa_delta`) and the followup sync (`sync_provider_account`).

**File:** `netbox_rpki/tests/test_provider_write.py` — add after `ProviderWriteServiceTestCase`.

### 5.1 Test Setup

```python
class ASPAProviderWriteServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='aspa-write-org', name='ASPA Write Org')
        cls.customer_asn = create_test_asn(65200)
        cls.provider_asn_a = create_test_asn(65201)
        cls.provider_asn_b = create_test_asn(65202)

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
        # Intent: customer_asn with 2 providers
        create_test_aspa_intent(
            organization=cls.organization,
            customer_asn=cls.customer_asn,
            provider_asns=[cls.provider_asn_a, cls.provider_asn_b],
        )
        # Imported ASPA (orphaned — no matching intent)
        cls.orphaned_customer_asn = create_test_asn(65299)
        cls.orphaned_imported_aspa = create_test_imported_aspa(
            provider_snapshot=cls.provider_snapshot,
            organization=cls.organization,
            customer_asn=cls.orphaned_customer_asn,
            provider_asns=[create_test_asn(65300)],
        )
        cls.reconciliation_run = run_aspa_reconciliation(
            organization=cls.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.plan = create_aspa_change_plan(cls.reconciliation_run)
```

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

Build a plan where a REPLACE semantic fires (imported ASPA that fully replaces the existing one). Confirm the item's `provider_operation == ADD_PROVIDER_SET` and the entry appears in `added`, not `removed`:

```python
# Use a provider snapshot with an ASPA whose customer matches but providers differ entirely
replace_snapshot = ...  # create snapshot with different provider set for same customer
replace_plan = create_aspa_change_plan(reconciliation_from_replace_snapshot)
delta = build_aspa_change_plan_delta(replace_plan)

replace_item = replace_plan.items.get(plan_semantic=rpki_models.ASPAChangePlanItemSemantic.REPLACE)
self.assertEqual(replace_item.provider_operation, rpki_models.ProviderWriteOperation.ADD_PROVIDER_SET)
added_customers = {e['customer_asn'] for e in delta.get('added', [])}
self.assertIn(replace_item.aspa_intent.customer_asn.asn, added_customers)
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

A plan with no `provider_account` (LOCAL scope plan) should fail `_require_aspa_provider_write_capability`:

```python
local_reconciliation_run = run_aspa_reconciliation(
    organization=self.organization,
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

# Krill was called with the serialized wire-format delta
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

A plan bound to an ARIN provider account (which doesn't support ASPA write) should fail appropriately:

```python
arin_account = create_test_provider_account(
    name='ARIN ASPA Unsupported', organization=self.organization,
    provider_type=rpki_models.ProviderType.ARIN, org_handle='ORG-ARIN-ASPA',
)
... (build plan targeting arin_account) ...

with self.assertRaisesMessage(ProviderWriteError, 'does not support ASPA write operations'):
    build_aspa_change_plan_delta(unsupported_aspa_plan)
```

### 5.3 Slice B Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
  NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput \
  netbox_rpki.tests.test_provider_write.ASPAProviderWriteServiceTestCase
```

---

## 6. Slice C — API and View Test Parity

**Goal:** Fill test gaps in the existing `ASPAChangePlanActionAPITestCase` and `ASPAChangePlanActionViewTestCase` to match the depth of their ROA equivalents.

**File:** `netbox_rpki/tests/test_provider_write.py` — extend existing ASPA test classes.

### 6.1 API Test Additions (`ASPAChangePlanActionAPITestCase`)

**`test_approve_action_records_governance_metadata`**

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

**`test_approve_action_rejects_lint_find_ids_not_in_schema`**

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

**`test_apply_action_records_governance_metadata_in_response`**

```python
approve_aspa_change_plan(self.plan, approved_by='api-approver', ticket_reference='ASPA-APPLY')
...
response = self.client.post(apply_url, {}, format='json', **self.header)
self.assertHttpStatus(response, 200)
self.assertIn('governance', response.data['execution']['response_payload_json'])
```

**`test_apply_action_marks_plan_failed_on_krill_error`**

```python
approve_aspa_change_plan(self.plan, ...)
url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-apply', kwargs={'pk': self.plan.pk})
with patch('netbox_rpki.services.provider_write._submit_krill_aspa_delta', side_effect=RuntimeError('krill down')):
    response = self.client.post(url, {}, format='json', **self.header)

self.assertHttpStatus(response, 400)
self.plan.refresh_from_db()
self.assertEqual(self.plan.status, rpki_models.ASPAChangePlanStatus.FAILED)
```

**`test_custom_actions_require_change_permission`** (extend existing test to include `apply`)

Confirm view-only users cannot trigger any mutation action:

```python
self.add_permissions('netbox_rpki.view_aspachangeplan')
for action in ('preview', 'approve', 'apply'):
    url = reverse(f'plugins-api:netbox_rpki-api:aspachangeplan-{action}', kwargs={'pk': self.plan.pk})
    response = self.client.post(url, {}, format='json', **self.header)
    with self.subTest(action=action):
        self.assertHttpStatus(response, 404)
```

### 6.2 View Test Additions (`ASPAChangePlanActionViewTestCase`)

**`test_approve_view_renders_governance_fields_without_lint_or_simulation_fields`**

```python
self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
url = reverse('plugins:netbox_rpki:aspachangeplan_approve', kwargs={'pk': self.plan.pk})

response = self.client.get(url)

self.assertHttpStatus(response, 200)
self.assertContains(response, 'Ticket Reference')
self.assertContains(response, 'Change Reference')
# Confirm ROA lint fields are NOT rendered
self.assertNotContains(response, 'Acknowledge Approval-Required Lint Findings')
self.assertNotContains(response, 'Acknowledge Approval-Required Simulation Results')
self.assertNotContains(response, 'Lint Acknowledgement Notes')
```

**`test_approve_view_persists_governance_fields`**

```python
response = self.client.post(
    url,
    {
        'confirm': True,
        'ticket_reference': 'ASPA-UI-CHG-1',
        'change_reference': 'ASPA-UI-CAB-1',
        'approval_notes': 'ASPA UI approval.',
    },
)
self.assertRedirects(response, self.plan.get_absolute_url())
self.plan.refresh_from_db()
self.assertEqual(self.plan.status, rpki_models.ASPAChangePlanStatus.APPROVED)
self.assertEqual(self.plan.ticket_reference, 'ASPA-UI-CHG-1')
self.assertEqual(self.plan.approval_records.count(), 1)
```

**`test_apply_view_shows_governance_metadata_after_approval`**

```python
approve_aspa_change_plan(
    self.plan, approved_by='view-approver',
    ticket_reference='ASPA-UI-APPLY-1', change_reference='ASPA-UI-APPLY-CR',
)
self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')

response = self.client.get(reverse('plugins:netbox_rpki:aspachangeplan_apply', kwargs={'pk': self.plan.pk}))

self.assertHttpStatus(response, 200)
self.assertContains(response, 'ASPA-UI-APPLY-1')
self.assertContains(response, 'ASPA-UI-APPLY-CR')
```

> The existing `test_apply_view_shows_governance_metadata_after_approval` is in the view test class — check it's present and if not, add it.

**`test_unsupported_provider_plan_hides_write_buttons_for_aspa`** (if not already present)

```python
# Create an ASPA plan targeting a non-Krill provider account
... (similar to ROA test) ...
# Confirm preview/approve/apply buttons are absent from the plan detail page
self.assertNotContains(response, reverse('plugins:netbox_rpki:aspachangeplan_preview', ...))
```

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

| Criterion | Verification |
|---|---|
| `ASPAChangePlanApproveActionSerializer` has no lint/simulation fields | `s.fields.keys()` does not contain `acknowledged_finding_ids` / `acknowledged_simulation_result_ids` / `lint_acknowledgement_notes` |
| `ASPAChangePlanApprovalForm` renders governance fields only | GET approve view does NOT contain "Acknowledge Approval-Required Lint Findings" or "Simulation Results" |
| Submitting `acknowledged_finding_ids` via ASPA approve API does not 500 | API test: `test_approve_action_rejects_lint_find_ids_not_in_schema` → status != 500 |
| Full ASPA preview → approve → apply lifecycle passes | `test_apply_submits_delta_records_execution_and_triggers_followup_sync` passes |
| Krill wire-format delta serialization is unit-tested | `test_serialize_krill_aspa_delta_converts_asn_integers_to_as_prefixed_strings` passes |
| Apply failure path marks plan FAILED | `test_apply_failure_marks_plan_failed_and_records_error` passes |
| Followup-sync failure marks execution FAILED while plan stays APPLIED | `test_apply_failure_during_followup_sync_records_partial_success` passes |
| All existing ASPA provider write tests pass unchanged | Full `test_provider_write` suite clean |
| All existing `test_aspa_change_plan` tests pass unchanged | No regressions from Slice A form change |

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

1. **Slice A first** — highest risk/impact, easiest to implement, immediate user-visible regression fix.
2. **Slice B second** — service-layer tests are independent and give confidence before touching the API/views.
3. **Slice C third** — test additions on top of the verified service layer.

Total estimated scope: ~3–4 hours of implementation (Slice A ~30 min, Slice B ~2 hr, Slice C ~1 hr).
