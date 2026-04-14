# Priority 8: Change Control and Auditability — Implementation Plan

**Created:** April 14, 2026
**Status:** Implementation target after Priority 3 and Priority 4 are complete
**Depends on:** Priority 4 (linting deepening), Priority 5 (simulation — already complete)

---

## 1. Purpose

This document is the implementation runbook for the Priority 8 change-control and
auditability work. It adds two governed capabilities on top of the existing ROA and ASPA
change-plan objects:

1. **Rollback bundles** — when a change plan is successfully applied, automatically capture the
   exact inverse delta so the operator can approve and apply a provider-backed rollback without
   reconstructing it manually.
2. **Multi-stage (dual) approval** — allow a plan to require a second independent approver
   before it becomes actionable, with full audit-trail coverage through the existing
   `ApprovalRecord` mechanism.

Both capabilities target the current closure criterion for Priority 8: "after linting and
simulation are available for the same plan objects." That prerequisite is met when Priority 4
and Priority 5 are both complete.

The plan is derived from a review of `models.py`, `services/provider_write.py`,
`views.py`, `forms.py`, `api/serializers.py`, `object_registry.py`, and `detail_specs.py`
as they stand on April 14, 2026.

---

## 2. Current State (read before writing any code)

These components already exist and are complete. Do not recreate or restructure them.

| Component | File | Status |
|-----------|------|--------|
| `ROAChangePlan` | `models.py:4351` | Complete, status DRAFT→APPROVED→APPLYING→APPLIED/FAILED |
| `ASPAChangePlan` | `models.py:4670` | Complete, mirrors ROA plan status machine |
| `ApprovalRecord` | `models.py:4478` | Supports both plan types; records governance metadata + simulation review |
| `ProviderWriteExecution` | `models.py:4543` | Records request/response payloads, followup sync for both plan types |
| `approve_roa_change_plan()` | `services/provider_write.py:391` | Single-stage; lint-gated; simulation-gated; creates ApprovalRecord |
| `approve_aspa_change_plan()` | `services/provider_write.py:485` | Single-stage; no lint gate (N/A); creates ApprovalRecord |
| `apply_roa_change_plan_provider_write()` | `services/provider_write.py:714` | POSTs delta, triggers followup sync |
| `apply_aspa_change_plan_provider_write()` | `services/provider_write.py:795` | POSTs delta, triggers followup sync |
| `build_roa_change_plan_delta()` | `services/provider_write.py:172` | Returns `{'added': [...], 'removed': [...]}` |
| `build_aspa_change_plan_delta()` | `services/provider_write.py:193` | Returns `{'added': [...], 'removed': [...]}` |
| `_submit_krill_route_delta()` | `services/provider_write.py:672` | POSTs internal delta format to Krill |
| `_submit_krill_aspa_delta()` | `services/provider_write.py:699` | Serializes + POSTs ASPA delta to Krill |

What does **not** exist today:

| Missing capability | Notes |
|----|---|
| Rollback bundles | No model, no service, no UI |
| Multi-stage approval | No second-approver status, no secondary approval service |
| `PENDING_SECONDARY_APPROVAL` plan status | Status machine ends at APPROVED before APPLYING |
| `requires_secondary_approval` plan flag | No per-plan or per-org dual-approval control |

---

## 3. Architectural Decisions

All decisions below were made on April 14, 2026.

| ID | Decision |
|----|----------|
| AD-1 | Rollback bundles are a **separate model** (`ROAChangePlanRollbackBundle`, `ASPAChangePlanRollbackBundle`), not reused `ROAChangePlan` instances. A rollback bundle is not a reconciliation-derived plan; it is a pre-computed inverse delta captured at apply-time. |
| AD-2 | Rollback bundle creation is **automatic on successful apply**. After `apply_roa_change_plan_provider_write()` succeeds, a helper `_create_roa_rollback_bundle(plan, delta)` is called inside the success path. The inverse delta is `{'added': delta['removed'], 'removed': delta['added']}`. |
| AD-3 | Rollback bundle **approval does not require lint or simulation re-run**. A rollback reverses an already-approved, already-applied change. Requiring full lint re-run before rollback is an operational anti-pattern; speed matters at rollback time. The `ApprovalRecord` mechanism covers audit. |
| AD-4 | Rollback bundle **apply details are stored on the bundle model directly**, not through `ProviderWriteExecution`. The bundle has its own `apply_started_at`, `applied_at`, `failed_at`, `apply_response_json`, and `apply_error` fields. This avoids updating the `ProviderWriteExecution.exactly_one_plan_target` constraint and keeps V1 rollback scope tight. |
| AD-5 | Multi-stage approval uses a **per-plan `requires_secondary_approval` boolean flag** (default `False`). When set and the first approval runs, the plan transitions to `AWAITING_2ND` instead of `APPROVED`. A second call to `approve_roa_change_plan_secondary()` transitions to `APPROVED`. |
| AD-6 | The new status value for secondary-approval-pending plans is `"awaiting_2nd"` (12 chars, fits in the existing `max_length=16` column without a schema change). Display label: "Awaiting Secondary Approval". |
| AD-7 | **The secondary approver must differ from the primary approver.** If both `approved_by` (primary) and the secondary actor are non-empty and equal (case-insensitive), `approve_roa_change_plan_secondary()` raises `ProviderWriteError`. If either is empty (automated or test contexts), the check is skipped. |
| AD-8 | The `requires_secondary_approval` flag is set **at plan creation time** via the approval form; it is also editable on the plan EDIT view while the plan is in DRAFT status. Once the plan transitions out of DRAFT, the field becomes read-only (enforced in `clean()`). |
| AD-9 | Both ROA and ASPA change plans receive identical dual-approval and rollback bundle treatment. Models and services mirror each other without a shared abstract base. |
| AD-10 | The existing `can_approve` and `can_apply` plan properties are not changed. New `can_approve_secondary` property is added: `True` only when `status == AWAITING_2ND`. |

---

## 4. Slice Ordering

```
Slice A  →  Slice B  →  (Slice D: rollback tests)
Slice C                 →  (Slice D: multi-stage tests)
```

Recommended order:

1. **Slice A** — Rollback bundle models + auto-capture. No service beyond a helper appended to the existing apply path. Self-contained.
2. **Slice B** — Rollback approve + apply workflow. Depends on Slice A (model must exist). ~3 hours.
3. **Slice C** — Multi-stage approval. Does not depend on A or B. Can run concurrently with Slice B. ~2 hours.
4. **Slice D** — Test coverage for all slices. Should be written alongside each slice, verified Green before moving forward.

Each slice has a focused verification command at the bottom. Do not proceed to the next slice until the command is green.

---

## 5. Slice A — Rollback Bundle Models and Auto-Capture

### 5.1 Goal

Two new models are added: `ROAChangePlanRollbackBundle` and `ASPAChangePlanRollbackBundle`.
When a ROA or ASPA change plan is successfully applied, the service automatically creates the
corresponding rollback bundle capturing the inverse delta. The bundle starts in `AVAILABLE`
status. No approve/apply flow is needed in this slice.

### 5.2 New Choices

Add to `models.py` near the other `TextChoices` enums (after `ProviderWriteExecutionMode`):

```python
class RollbackBundleStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    APPROVED = "approved", "Approved"
    APPLYING = "applying", "Applying"
    APPLIED = "applied", "Applied"
    FAILED = "failed", "Failed"
```

### 5.3 New Models

Add both models to `models.py` after the `ProviderWriteExecution` class:

```python
class ROAChangePlanRollbackBundle(NamedRpkiStandardModel):
    """Inverse-delta snapshot captured automatically when a ROA change plan is applied.

    Provides a governed rollback path without requiring a new reconciliation run.
    Approval gates on governance metadata only; lint and simulation re-runs are not required.
    """
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_rollback_bundles',
    )
    source_plan = models.OneToOneField(
        to='ROAChangePlan',
        on_delete=models.PROTECT,
        related_name='rollback_bundle',
    )
    rollback_delta_json = models.JSONField(
        default=dict,
        help_text=(
            'The inverse of the applied delta. '
            'ROA creates become withdraws; withdraws become creates.'
        ),
    )
    item_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=RollbackBundleStatus.choices,
        default=RollbackBundleStatus.AVAILABLE,
    )
    # Governance + approval
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    approved_by = models.CharField(max_length=150, blank=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    # Apply tracking
    apply_requested_by = models.CharField(max_length=150, blank=True)
    apply_started_at = models.DateTimeField(blank=True, null=True)
    applied_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)
    apply_response_json = models.JSONField(default=dict, blank=True)
    apply_error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created",)
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F('maintenance_window_start'))
                ),
                name='netbox_rpki_roa_rollback_valid_mw',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roachangeplanrollbackbundle", args=[self.pk])

    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(
            start_at=self.maintenance_window_start,
            end_at=self.maintenance_window_end,
        )

    @property
    def can_approve(self) -> bool:
        return self.status == RollbackBundleStatus.AVAILABLE

    @property
    def can_apply(self) -> bool:
        return self.status == RollbackBundleStatus.APPROVED


class ASPAChangePlanRollbackBundle(NamedRpkiStandardModel):
    """Inverse-delta snapshot captured automatically when an ASPA change plan is applied."""
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='aspa_rollback_bundles',
    )
    source_plan = models.OneToOneField(
        to='ASPAChangePlan',
        on_delete=models.PROTECT,
        related_name='rollback_bundle',
    )
    rollback_delta_json = models.JSONField(default=dict)
    item_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=RollbackBundleStatus.choices,
        default=RollbackBundleStatus.AVAILABLE,
    )
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    approved_by = models.CharField(max_length=150, blank=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    apply_requested_by = models.CharField(max_length=150, blank=True)
    apply_started_at = models.DateTimeField(blank=True, null=True)
    applied_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)
    apply_response_json = models.JSONField(default=dict, blank=True)
    apply_error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created",)
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F('maintenance_window_start'))
                ),
                name='netbox_rpki_aspa_rollback_valid_mw',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspachangeplanrollbackbundle", args=[self.pk])

    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(
            start_at=self.maintenance_window_start,
            end_at=self.maintenance_window_end,
        )

    @property
    def can_approve(self) -> bool:
        return self.status == RollbackBundleStatus.AVAILABLE

    @property
    def can_apply(self) -> bool:
        return self.status == RollbackBundleStatus.APPROVED
```

### 5.4 Migration

Generate with `makemigrations`. The migration adds two new tables. No existing tables are
altered. Run `migrate --run-syncdb --check` to confirm zero conflicts.

### 5.5 Service — Auto-Capture on Apply

In `services/provider_write.py`, add two private helpers:

```python
def _create_roa_rollback_bundle(
    plan: rpki_models.ROAChangePlan,
    delta: dict[str, list[dict]],
) -> rpki_models.ROAChangePlanRollbackBundle:
    """Capture the inverse delta after a successful ROA apply. Called inside the apply path."""
    rollback_delta = {
        'added': list(delta.get('removed', [])),
        'removed': list(delta.get('added', [])),
    }
    item_count = len(rollback_delta['added']) + len(rollback_delta['removed'])
    return rpki_models.ROAChangePlanRollbackBundle.objects.create(
        name=f'{plan.name} Rollback Bundle',
        organization=plan.organization,
        tenant=plan.tenant if hasattr(plan, 'tenant') else None,
        source_plan=plan,
        rollback_delta_json=rollback_delta,
        item_count=item_count,
        status=rpki_models.RollbackBundleStatus.AVAILABLE,
    )


def _create_aspa_rollback_bundle(
    plan: rpki_models.ASPAChangePlan,
    delta: dict[str, list[dict]],
) -> rpki_models.ASPAChangePlanRollbackBundle:
    """Capture the inverse delta after a successful ASPA apply. Called inside the apply path."""
    rollback_delta = {
        'added': list(delta.get('removed', [])),
        'removed': list(delta.get('added', [])),
    }
    item_count = len(rollback_delta['added']) + len(rollback_delta['removed'])
    return rpki_models.ASPAChangePlanRollbackBundle.objects.create(
        name=f'{plan.name} Rollback Bundle',
        organization=plan.organization,
        tenant=plan.tenant if hasattr(plan, 'tenant') else None,
        source_plan=plan,
        rollback_delta_json=rollback_delta,
        item_count=item_count,
        status=rpki_models.RollbackBundleStatus.AVAILABLE,
    )
```

In `apply_roa_change_plan_provider_write()`, append inside the success path **after** the
`plan.save()` call that sets `status = APPLIED` and **before** the followup sync block:

```python
        plan.status = rpki_models.ROAChangePlanStatus.APPLIED
        plan.applied_at = applied_at
        plan.save(update_fields=('status', 'applied_at'))

        # Capture rollback bundle for future reversal.
        _create_roa_rollback_bundle(plan, delta)

        response_payload_json = { ...  # existing code continues
```

Do the same in `apply_aspa_change_plan_provider_write()` by calling
`_create_aspa_rollback_bundle(plan, delta)` in the equivalent place.

**Note:** `_create_roa_rollback_bundle` must NOT be inside the `try/except` that catches
provider submission failures — it should only run after `plan.status == APPLIED`.

### 5.6 Registry and Navigation

Add both models to `object_registry.py` in a `"Governance"` navigation group (create the
group if it does not yet exist; otherwise append after the closest related entry):

```python
ObjectSpec(
    registry_key="roachangeplanrollbackbundle",
    model=models.ROAChangePlanRollbackBundle,
    class_prefix="ROAChangePlanRollbackBundle",
    verbose_name="ROA Change Plan Rollback Bundle",
    verbose_name_plural="ROA Change Plan Rollback Bundles",
    navigation_group="Governance",
    api=ApiSpec(read_write=False),   # read-only standard CRUD for now
    view=ViewSpec(can_add=False, can_edit=False, can_delete=False),
)

ObjectSpec(
    registry_key="aspachangeplanrollbackbundle",
    model=models.ASPAChangePlanRollbackBundle,
    class_prefix="ASPAChangePlanRollbackBundle",
    verbose_name="ASPA Change Plan Rollback Bundle",
    verbose_name_plural="ASPA Change Plan Rollback Bundles",
    navigation_group="Governance",
    api=ApiSpec(read_write=False),
    view=ViewSpec(can_add=False, can_edit=False, can_delete=False),
)
```

### 5.7 Detail Spec Panel on Change Plan Pages

In `detail_specs.py`, locate the ROA change plan detail spec and add a `DetailPanel` after the
existing `ApprovalRecord` or `ProviderWriteExecution` related panel:

```python
DetailPanel(
    title="Rollback Bundle",
    related_model="roachangeplanrollbackbundle",
    related_field="source_plan",
    empty_label="No rollback bundle (plan not yet applied).",
)
```

Add the equivalent for `ASPAChangePlan` referencing `aspachangeplanrollbackbundle`.

### 5.8 Slice A Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python \
  manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_rollback_bundle.ROARollbackBundleCreationTestCase
```

The test module `test_rollback_bundle.py` is created in Slice D. For Slice A, run migrations
and a quick smoke test in the Django shell to verify the bundle is created on a mock apply.

---

## 6. Slice B — Rollback Approve and Apply Workflow

### 6.1 Goal

Operators can approve a rollback bundle (governance fields only, no lint/simulation), then
apply it, which POSTs the inverse delta to the provider and runs a followup sync.

### 6.2 Service Functions

Add to `services/provider_write.py`:

```python
def approve_rollback_bundle(
    bundle,  # ROAChangePlanRollbackBundle | ASPAChangePlanRollbackBundle
    *,
    approved_by: str = '',
    ticket_reference: str = '',
    change_reference: str = '',
    maintenance_window_start=None,
    maintenance_window_end=None,
    notes: str = '',
):
    """Approve a rollback bundle. No lint or simulation gate — see AD-3."""
    if not bundle.can_approve:
        raise ProviderWriteError(
            f'Rollback bundle cannot be approved in status "{bundle.status}".'
        )
    approved_at = timezone.now()
    bundle.status = rpki_models.RollbackBundleStatus.APPROVED
    bundle.approved_by = approved_by
    bundle.approved_at = approved_at
    bundle.ticket_reference = ticket_reference
    bundle.change_reference = change_reference
    bundle.maintenance_window_start = maintenance_window_start
    bundle.maintenance_window_end = maintenance_window_end
    bundle.notes = notes
    bundle.full_clean(validate_unique=False)
    bundle.save(update_fields=(
        'status', 'approved_by', 'approved_at',
        'ticket_reference', 'change_reference',
        'maintenance_window_start', 'maintenance_window_end',
        'notes',
    ))
    return bundle


def apply_roa_rollback_bundle(
    bundle: rpki_models.ROAChangePlanRollbackBundle,
    *,
    requested_by: str = '',
) -> rpki_models.ROAChangePlanRollbackBundle:
    """Apply a ROA rollback bundle by POSTing the inverse delta to Krill."""
    if not bundle.can_apply:
        raise ProviderWriteError(
            f'Rollback bundle cannot be applied in status "{bundle.status}".'
        )
    provider_account = bundle.source_plan.provider_account
    if provider_account is None or not provider_account.supports_roa_write:
        raise ProviderWriteError('Source plan has no provider account capable of ROA writes.')

    started_at = timezone.now()
    bundle.status = rpki_models.RollbackBundleStatus.APPLYING
    bundle.apply_started_at = started_at
    bundle.apply_requested_by = requested_by
    bundle.failed_at = None
    bundle.save(update_fields=('status', 'apply_started_at', 'apply_requested_by', 'failed_at'))

    try:
        provider_response = _submit_krill_route_delta(
            provider_account,
            bundle.rollback_delta_json,
        )
        applied_at = timezone.now()
        bundle.status = rpki_models.RollbackBundleStatus.APPLIED
        bundle.applied_at = applied_at
        bundle.apply_response_json = {
            'provider_response': provider_response,
            'roa_write_mode': provider_account.roa_write_mode,
            'source_plan_id': bundle.source_plan_id,
        }
        bundle.apply_error = ''
        try:
            followup_sync_run, followup_snapshot = sync_provider_account(
                provider_account,
                snapshot_name=(
                    f'{provider_account.name} Post-Rollback Snapshot {applied_at:%Y-%m-%d %H:%M:%S}'
                ),
            )
            bundle.apply_response_json['followup_sync'] = {
                'provider_sync_run_id': followup_sync_run.pk,
                'provider_snapshot_id': followup_snapshot.pk,
                'status': followup_sync_run.status,
            }
        except Exception as exc:
            bundle.apply_response_json['followup_sync'] = {
                'status': rpki_models.ValidationRunStatus.FAILED,
                'error': str(exc),
            }
        bundle.save(update_fields=(
            'status', 'applied_at', 'apply_response_json', 'apply_error',
        ))
    except Exception as exc:
        completed_at = timezone.now()
        bundle.status = rpki_models.RollbackBundleStatus.FAILED
        bundle.failed_at = completed_at
        bundle.apply_error = str(exc)
        bundle.apply_response_json = {'error': str(exc)}
        bundle.save(update_fields=('status', 'failed_at', 'apply_error', 'apply_response_json'))
        raise ProviderWriteError(str(exc)) from exc

    return bundle


def apply_aspa_rollback_bundle(
    bundle: rpki_models.ASPAChangePlanRollbackBundle,
    *,
    requested_by: str = '',
) -> rpki_models.ASPAChangePlanRollbackBundle:
    """Apply an ASPA rollback bundle by POSTing the inverse delta to Krill."""
    if not bundle.can_apply:
        raise ProviderWriteError(
            f'Rollback bundle cannot be applied in status "{bundle.status}".'
        )
    provider_account = bundle.source_plan.provider_account
    if provider_account is None or not provider_account.supports_aspa_write:
        raise ProviderWriteError('Source plan has no provider account capable of ASPA writes.')

    started_at = timezone.now()
    bundle.status = rpki_models.RollbackBundleStatus.APPLYING
    bundle.apply_started_at = started_at
    bundle.apply_requested_by = requested_by
    bundle.failed_at = None
    bundle.save(update_fields=('status', 'apply_started_at', 'apply_requested_by', 'failed_at'))

    try:
        provider_response = _submit_krill_aspa_delta(
            provider_account,
            bundle.rollback_delta_json,
        )
        applied_at = timezone.now()
        bundle.status = rpki_models.RollbackBundleStatus.APPLIED
        bundle.applied_at = applied_at
        bundle.apply_response_json = {
            'provider_response': provider_response,
            'aspa_write_mode': provider_account.aspa_write_mode,
            'source_plan_id': bundle.source_plan_id,
        }
        bundle.apply_error = ''
        try:
            followup_sync_run, followup_snapshot = sync_provider_account(
                provider_account,
                snapshot_name=(
                    f'{provider_account.name} Post-Rollback Snapshot {applied_at:%Y-%m-%d %H:%M:%S}'
                ),
            )
            bundle.apply_response_json['followup_sync'] = {
                'provider_sync_run_id': followup_sync_run.pk,
                'provider_snapshot_id': followup_snapshot.pk,
                'status': followup_sync_run.status,
            }
        except Exception as exc:
            bundle.apply_response_json['followup_sync'] = {
                'status': rpki_models.ValidationRunStatus.FAILED,
                'error': str(exc),
            }
        bundle.save(update_fields=(
            'status', 'applied_at', 'apply_response_json', 'apply_error',
        ))
    except Exception as exc:
        completed_at = timezone.now()
        bundle.status = rpki_models.RollbackBundleStatus.FAILED
        bundle.failed_at = completed_at
        bundle.apply_error = str(exc)
        bundle.apply_response_json = {'error': str(exc)}
        bundle.save(update_fields=('status', 'failed_at', 'apply_error', 'apply_response_json'))
        raise ProviderWriteError(str(exc)) from exc

    return bundle
```

### 6.3 Form

Add to `forms.py`:

```python
class RollbackBundleApprovalForm(RpkiActionForm):
    """Governance-only approval form for rollback bundles. No lint or simulation fields."""
    approved_by = forms.CharField(
        label="Approved by",
        max_length=150,
        required=False,
    )
    ticket_reference = forms.CharField(
        label="Ticket reference",
        max_length=200,
        required=False,
    )
    change_reference = forms.CharField(
        label="Change reference",
        max_length=200,
        required=False,
    )
    maintenance_window_start = forms.DateTimeField(
        label="Maintenance window start",
        required=False,
        widget=DateTimePicker(),
    )
    maintenance_window_end = forms.DateTimeField(
        label="Maintenance window end",
        required=False,
        widget=DateTimePicker(),
    )
    notes = forms.CharField(
        label="Approval notes",
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    fieldsets = (
        FieldSet('approved_by', 'ticket_reference', 'change_reference', name="Approval"),
        FieldSet('maintenance_window_start', 'maintenance_window_end', name="Maintenance Window"),
        FieldSet('notes', name="Notes"),
    )
```

### 6.4 Views

Add to `views.py`. Use the same `RpkiActionView` base pattern used by
`ROAChangePlanApproveView`. The ROA views are the normative pattern; repeat for ASPA.

```python
class ROAChangePlanRollbackBundleApproveView(RpkiActionView):
    """Approve a ROA rollback bundle (governance-only; no lint gate)."""
    queryset = models.ROAChangePlanRollbackBundle.objects.all()
    form_class = forms.RollbackBundleApprovalForm
    template_name = "netbox_rpki/roa_rollback_bundle_approve.html"
    action_title = "Approve ROA Rollback Bundle"

    def get_permission(self):
        return "netbox_rpki.approve_roachangeplanrollbackbundle"

    def get_success_url(self, obj):
        return obj.get_absolute_url()

    def get_denied_redirect_url(self, obj):
        return obj.get_absolute_url()

    def action_allowed(self, obj):
        return obj.can_approve

    def perform_action(self, obj, form):
        from netbox_rpki.services.provider_write import approve_rollback_bundle
        return approve_rollback_bundle(
            obj,
            approved_by=form.cleaned_data.get('approved_by', ''),
            ticket_reference=form.cleaned_data.get('ticket_reference', ''),
            change_reference=form.cleaned_data.get('change_reference', ''),
            maintenance_window_start=form.cleaned_data.get('maintenance_window_start'),
            maintenance_window_end=form.cleaned_data.get('maintenance_window_end'),
            notes=form.cleaned_data.get('notes', ''),
        )


class ROAChangePlanRollbackBundleApplyView(RpkiActionView):
    """Apply a ROA rollback bundle. Requires APPROVED status."""
    queryset = models.ROAChangePlanRollbackBundle.objects.all()
    form_class = forms.RpkiApplyConfirmForm   # simple confirm form; no new fields needed
    template_name = "netbox_rpki/roa_rollback_bundle_apply.html"
    action_title = "Apply ROA Rollback Bundle"

    def get_permission(self):
        return "netbox_rpki.apply_roachangeplanrollbackbundle"

    def action_allowed(self, obj):
        return obj.can_apply

    def get_success_url(self, obj):
        return obj.get_absolute_url()

    def perform_action(self, obj, form):
        from netbox_rpki.services.provider_write import apply_roa_rollback_bundle
        return apply_roa_rollback_bundle(
            obj,
            requested_by=self.request.user.username,
        )
```

Create parallel `ASPAChangePlanRollbackBundleApproveView` and
`ASPAChangePlanRollbackBundleApplyView` with the same pattern, calling
`apply_aspa_rollback_bundle`.

### 6.5 URL Registration

In `urls.py`, register four new URL patterns:

```python
path('roa-rollback-bundles/<int:pk>/approve/',
     views.ROAChangePlanRollbackBundleApproveView.as_view(),
     name='roachangeplanrollbackbundle_approve'),
path('roa-rollback-bundles/<int:pk>/apply/',
     views.ROAChangePlanRollbackBundleApplyView.as_view(),
     name='roachangeplanrollbackbundle_apply'),
path('aspa-rollback-bundles/<int:pk>/approve/',
     views.ASPAChangePlanRollbackBundleApproveView.as_view(),
     name='aspachangeplanrollbackbundle_approve'),
path('aspa-rollback-bundles/<int:pk>/apply/',
     views.ASPAChangePlanRollbackBundleApplyView.as_view(),
     name='aspachangeplanrollbackbundle_apply'),
```

### 6.6 Detail Spec Action Buttons

In `detail_specs.py`, register the action buttons on the rollback bundle detail pages:

For `ROAChangePlanRollbackBundle`:
```python
DetailAction(
    url_name='roachangeplanrollbackbundle_approve',
    label='Approve Rollback',
    condition_attr='can_approve',
    button_class='btn-warning',
),
DetailAction(
    url_name='roachangeplanrollbackbundle_apply',
    label='Apply Rollback',
    condition_attr='can_apply',
    button_class='btn-danger',
),
```

Repeat pattern for `ASPAChangePlanRollbackBundle`.

### 6.7 API Support

Add to `api/serializers.py`:

```python
class RollbackBundleApproveActionSerializer(serializers.Serializer):
    approved_by = serializers.CharField(required=False, allow_blank=True, default='')
    ticket_reference = serializers.CharField(required=False, allow_blank=True, default='')
    change_reference = serializers.CharField(required=False, allow_blank=True, default='')
    maintenance_window_start = serializers.DateTimeField(required=False, allow_null=True, default=None)
    maintenance_window_end = serializers.DateTimeField(required=False, allow_null=True, default=None)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class RollbackBundleApplyActionSerializer(serializers.Serializer):
    requested_by = serializers.CharField(required=False, allow_blank=True, default='')
```

Register `approve` and `apply` actions on the rollback bundle viewsets in `api/views.py`
following the same decorator pattern as `ROAChangePlanViewSet.approve_action`.

### 6.8 Slice B Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python \
  manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_rollback_bundle
```

---

## 7. Slice C — Multi-Stage (Dual) Approval

### 7.1 Goal

An operator may require a second independent approver before a change plan can be applied.
When `requires_secondary_approval=True`, the first approval leaves the plan in
`AWAITING_2ND` status. A second call from a different actor transitions it to `APPROVED`
and makes `can_apply` True. Full audit trail is preserved through `ApprovalRecord`.

### 7.2 Status Addition

Add to `ROAChangePlanStatus` and `ASPAChangePlanStatus` in `models.py`:

```python
class ROAChangePlanStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    AWAITING_2ND = "awaiting_2nd", "Awaiting Secondary Approval"   # NEW
    APPROVED = "approved", "Approved"
    APPLYING = "applying", "Applying"
    APPLIED = "applied", "Applied"
    FAILED = "failed", "Failed"
```

```python
class ASPAChangePlanStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    AWAITING_2ND = "awaiting_2nd", "Awaiting Secondary Approval"   # NEW
    APPROVED = "approved", "Approved"
    APPLYING = "applying", "Applying"
    APPLIED = "applied", "Applied"
    FAILED = "failed", "Failed"
```

**No migration required for the choices themselves.** The DB column stores the string value.
`max_length=16` is sufficient: `"awaiting_2nd"` is 12 chars.

### 7.3 New Fields on Plan Models

Add to `ROAChangePlan` and `ASPAChangePlan` in `models.py`:

```python
    requires_secondary_approval = models.BooleanField(
        default=False,
        help_text=(
            'When enabled, the first approval moves the plan to '
            '"Awaiting Secondary Approval" rather than "Approved". '
            'A second independent approver must then confirm before it can be applied.'
        ),
    )
    secondary_approved_by = models.CharField(max_length=150, blank=True)
    secondary_approved_at = models.DateTimeField(blank=True, null=True)
```

Add these fields to the corresponding migrations (one migration can cover both). Both
`requires_secondary_approval` (has a default) and the `secondary_approved_*` fields
(nullable/blank) are safe non-destructive additions.

Add a `clean()` guard on each plan:

```python
    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(...)
        # Prevent changing requires_secondary_approval once plan has moved out of DRAFT.
        if self.pk:
            try:
                original = type(self).objects.get(pk=self.pk)
            except type(self).DoesNotExist:
                return
            if (
                original.status != ROAChangePlanStatus.DRAFT
                and original.requires_secondary_approval != self.requires_secondary_approval
            ):
                raise ValidationError({
                    'requires_secondary_approval': (
                        'Cannot change dual-approval requirement after the plan has left DRAFT status.'
                    )
                })
```

### 7.4 Model Properties Update

On `ROAChangePlan`, add and update:

```python
    @property
    def can_approve(self) -> bool:
        # Unchanged: DRAFT-only
        return self.supports_provider_write and self.status == ROAChangePlanStatus.DRAFT

    @property
    def can_approve_secondary(self) -> bool:
        return self.supports_provider_write and self.status == ROAChangePlanStatus.AWAITING_2ND

    @property
    def can_apply(self) -> bool:
        # Unchanged: APPROVED-only; AWAITING_2ND does NOT allow apply
        return self.supports_provider_write and self.status == ROAChangePlanStatus.APPROVED
```

Repeat for `ASPAChangePlan` substituting `ASPAChangePlanStatus`.

### 7.5 Service Changes — Primary Approval

In `approve_roa_change_plan()`, **after** the existing simulation check and **before** setting
`plan.status = APPROVED`, add:

```python
    target_status = (
        rpki_models.ROAChangePlanStatus.AWAITING_2ND
        if plan.requires_secondary_approval
        else rpki_models.ROAChangePlanStatus.APPROVED
    )
    plan.status = target_status
```

And adjust the `update_fields` tuple to include `requires_secondary_approval` for completeness
(it is already saved at plan creation, so this is a no-op in most cases, but makes the
intent explicit).

In `approve_aspa_change_plan()`, apply the same pattern with `ASPAChangePlanStatus.AWAITING_2ND`.

### 7.6 New Service Function — Secondary Approval

Add to `services/provider_write.py`:

```python
def approve_roa_change_plan_secondary(
    plan: rpki_models.ROAChangePlan | int,
    *,
    secondary_approved_by: str = '',
    approval_notes: str = '',
) -> rpki_models.ROAChangePlan:
    """Complete the second approval stage, transitioning AWAITING_2ND → APPROVED.

    Enforces that the secondary approver differs from the primary approver (AD-7).
    """
    plan = _normalize_plan(plan)
    if plan.status != rpki_models.ROAChangePlanStatus.AWAITING_2ND:
        raise ProviderWriteError(
            f'Plan is not awaiting secondary approval (current status: {plan.status}).'
        )
    # AD-7: secondary actor must differ from primary actor.
    if (
        secondary_approved_by
        and plan.approved_by
        and secondary_approved_by.strip().lower() == plan.approved_by.strip().lower()
    ):
        raise ProviderWriteError(
            'The secondary approver must be a different person than the primary approver '
            f'("{plan.approved_by}").'
        )
    secondary_approved_at = timezone.now()
    with transaction.atomic():
        plan.status = rpki_models.ROAChangePlanStatus.APPROVED
        plan.secondary_approved_by = secondary_approved_by
        plan.secondary_approved_at = secondary_approved_at
        plan.save(update_fields=('status', 'secondary_approved_by', 'secondary_approved_at'))
        # Create a second ApprovalRecord for full audit trail.
        _create_approval_record_for_plan(
            plan=plan,
            approved_by=secondary_approved_by,
            approved_at=secondary_approved_at,
            ticket_reference=plan.ticket_reference,
            change_reference=plan.change_reference,
            maintenance_window_start=plan.maintenance_window_start,
            maintenance_window_end=plan.maintenance_window_end,
            approval_notes=f'[Secondary approval] {approval_notes}'.strip(),
        )
    return plan


def approve_aspa_change_plan_secondary(
    plan: rpki_models.ASPAChangePlan | int,
    *,
    secondary_approved_by: str = '',
    approval_notes: str = '',
) -> rpki_models.ASPAChangePlan:
    """Complete the second approval stage for an ASPA change plan."""
    plan = _normalize_aspa_plan(plan)
    if plan.status != rpki_models.ASPAChangePlanStatus.AWAITING_2ND:
        raise ProviderWriteError(
            f'Plan is not awaiting secondary approval (current status: {plan.status}).'
        )
    if (
        secondary_approved_by
        and plan.approved_by
        and secondary_approved_by.strip().lower() == plan.approved_by.strip().lower()
    ):
        raise ProviderWriteError(
            'The secondary approver must be a different person than the primary approver '
            f'("{plan.approved_by}").'
        )
    secondary_approved_at = timezone.now()
    with transaction.atomic():
        plan.status = rpki_models.ASPAChangePlanStatus.APPROVED
        plan.secondary_approved_by = secondary_approved_by
        plan.secondary_approved_at = secondary_approved_at
        plan.save(update_fields=('status', 'secondary_approved_by', 'secondary_approved_at'))
        _create_approval_record_for_plan(
            plan=plan,
            approved_by=secondary_approved_by,
            approved_at=secondary_approved_at,
            ticket_reference=plan.ticket_reference,
            change_reference=plan.change_reference,
            maintenance_window_start=plan.maintenance_window_start,
            maintenance_window_end=plan.maintenance_window_end,
            approval_notes=f'[Secondary approval] {approval_notes}'.strip(),
        )
    return plan
```

### 7.7 Form Changes

In `forms.py`, add `requires_secondary_approval` to the ROA change plan approval form:

```python
class ROAChangePlanApprovalForm(RpkiActionForm):
    # ... existing fields ...
    requires_secondary_approval = forms.BooleanField(
        label="Require a second independent approval before this plan can be applied",
        required=False,
        initial=False,
    )
    # ... existing fieldsets, add 'requires_secondary_approval' to the governance fieldset
```

Add a new secondary approval form (ROA and ASPA):

```python
class ChangePlanSecondaryApprovalForm(RpkiActionForm):
    """Minimal form for the second approval stage."""
    secondary_approved_by = forms.CharField(
        label="Approved by",
        max_length=150,
        required=False,
    )
    approval_notes = forms.CharField(
        label="Approval notes",
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    fieldsets = (
        FieldSet('secondary_approved_by', 'approval_notes', name="Secondary Approval"),
    )
```

### 7.8 Views

Add to `views.py`:

```python
class ROAChangePlanApproveSecondaryView(RpkiActionView):
    queryset = models.ROAChangePlan.objects.all()
    form_class = forms.ChangePlanSecondaryApprovalForm
    template_name = "netbox_rpki/roa_change_plan_approve_secondary.html"
    action_title = "Secondary Approval — ROA Change Plan"

    def get_permission(self):
        return "netbox_rpki.approve_roachangeplan"

    def action_allowed(self, obj):
        return obj.can_approve_secondary

    def get_success_url(self, obj):
        return obj.get_absolute_url()

    def perform_action(self, obj, form):
        from netbox_rpki.services.provider_write import approve_roa_change_plan_secondary
        return approve_roa_change_plan_secondary(
            obj,
            secondary_approved_by=form.cleaned_data.get('secondary_approved_by', ''),
            approval_notes=form.cleaned_data.get('approval_notes', ''),
        )


class ASPAChangePlanApproveSecondaryView(RpkiActionView):
    # Same pattern, calls approve_aspa_change_plan_secondary
    ...
```

### 7.9 URL Registration

```python
path('roa-change-plans/<int:pk>/approve-secondary/',
     views.ROAChangePlanApproveSecondaryView.as_view(),
     name='roachangeplan_approve_secondary'),
path('aspa-change-plans/<int:pk>/approve-secondary/',
     views.ASPAChangePlanApproveSecondaryView.as_view(),
     name='aspachangeplan_approve_secondary'),
```

### 7.10 API Support

Add to `api/serializers.py`:

```python
class ROAChangePlanApproveSecondaryActionSerializer(serializers.Serializer):
    secondary_approved_by = serializers.CharField(required=False, allow_blank=True, default='')
    approval_notes = serializers.CharField(required=False, allow_blank=True, default='')


class ASPAChangePlanApproveSecondaryActionSerializer(serializers.Serializer):
    secondary_approved_by = serializers.CharField(required=False, allow_blank=True, default='')
    approval_notes = serializers.CharField(required=False, allow_blank=True, default='')
```

Register as `approve_secondary` actions on `ROAChangePlanViewSet` and
`ASPAChangePlanViewSet` in `api/views.py`.

### 7.11 Detail Spec — Secondary Approval Button

In `detail_specs.py`, on the ROA change plan detail spec:

```python
DetailAction(
    url_name='roachangeplan_approve_secondary',
    label='Secondary Approval',
    condition_attr='can_approve_secondary',
    button_class='btn-success',
),
```

Repeat for ASPA.

Also update the `requires_secondary_approval` field visibility: ensure it appears in the plan
detail info table (add to the plan's `DetailSpec` info fields section).

### 7.12 Slice C Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python \
  manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_multi_stage_approval
```

---

## 8. Slice D — Test Coverage

Create two new test modules:
- `netbox_rpki/tests/test_rollback_bundle.py`
- `netbox_rpki/tests/test_multi_stage_approval.py`

### 8.1 `ROARollbackBundleCreationTestCase`

```python
class ROARollbackBundleCreationTestCase(RpkiTestCase):
    """Rollback bundle is created automatically on successful ROA apply."""

    def test_rollback_bundle_created_on_successful_apply(self):
        # Apply a mocked ROA plan; verify ROAChangePlanRollbackBundle exists
        # and rollback_delta is the inverse of the applied delta.
        ...

    def test_rollback_bundle_not_created_on_failed_apply(self):
        # Simulate provider failure; verify no bundle is created.
        ...

    def test_rollback_delta_inverts_added_and_removed(self):
        # Verify: bundle.rollback_delta_json['added'] == original_delta['removed']
        # and bundle.rollback_delta_json['removed'] == original_delta['added']
        ...
```

### 8.2 `ROARollbackBundleLifecycleTestCase`

```python
class ROARollbackBundleLifecycleTestCase(RpkiTestCase):

    def test_approve_bundle_transitions_to_approved(self):
        ...

    def test_apply_bundle_transitions_to_applied_and_updates_status(self):
        # Mock _submit_krill_route_delta; verify status = APPLIED.
        ...

    def test_apply_bundle_fails_if_not_approved(self):
        # Bundle in AVAILABLE status; apply raises ProviderWriteError.
        ...

    def test_apply_bundle_transitions_to_failed_on_provider_error(self):
        # Mock _submit_krill_route_delta to raise; verify status = FAILED.
        ...

    def test_approve_bundle_fails_if_already_applied(self):
        ...
```

### 8.3 `ASPARollbackBundleLifecycleTestCase`

Same test shape as ROA, calling `apply_aspa_rollback_bundle`.

### 8.4 `ROAMultiStageApprovalTestCase`

```python
class ROAMultiStageApprovalTestCase(RpkiTestCase):

    def test_primary_approval_with_dual_flag_sets_awaiting_2nd(self):
        # Create plan with requires_secondary_approval=True; approve; verify status = AWAITING_2ND.
        ...

    def test_primary_approval_without_dual_flag_sets_approved(self):
        # Default flow; verify status = APPROVED (unchanged behaviour).
        ...

    def test_secondary_approval_transitions_awaiting_2nd_to_approved(self):
        ...

    def test_secondary_approval_rejects_same_actor_as_primary(self):
        # Same approved_by for both; verify ProviderWriteError raised.
        ...

    def test_secondary_approval_allows_same_actor_when_primary_is_empty(self):
        # primary approved_by=''; secondary can be anything (AD-7 guard skipped).
        ...

    def test_can_approve_secondary_true_only_in_awaiting_2nd(self):
        # Verify property is False in DRAFT, APPROVED, APPLIED.
        ...

    def test_can_apply_false_in_awaiting_2nd(self):
        # A plan in AWAITING_2ND cannot be applied.
        ...

    def test_two_approval_records_created_for_dual_approval_plan(self):
        # After both approvals, ApprovalRecord.objects.filter(change_plan=plan).count() == 2
        ...
```

### 8.5 `ASPAMultiStageApprovalTestCase`

Same shape as ROA variant, using `approve_aspa_change_plan_secondary`.

### 8.6 View and API Test Cases

Minimal web-view and API smoke tests following the patterns in
`tests/test_views.py` and `tests/test_provider_write.py`:

- `test_rollback_bundle_approve_view_renders_form` — GET returns 200
- `test_rollback_bundle_approve_view_approves_on_post` — POST transitions status
- `test_rollback_bundle_apply_view_denies_unapproved_bundle` — POST when still AVAILABLE returns error
- `test_secondary_approval_view_renders` — GET returns 200
- `test_secondary_approval_view_denies_same_actor` — POST with same actor returns error
- `test_approve_secondary_api_action_transitions_plan` — API `POST approve_secondary` test

### 8.7 Full Suite Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python \
  manage.py test --keepdb --noinput \
  netbox_rpki.tests.test_rollback_bundle \
  netbox_rpki.tests.test_multi_stage_approval
```

Followed by the full suite to confirm no regressions:

```bash
cd /home/mencken/src/netbox_rpki/devrun && ./dev.sh test full
```

---

## 9. Migration Checklist

| Migration scope | What changes | Safety |
|---|---|---|
| Slice A | Two new tables (`ROAChangePlanRollbackBundle`, `ASPAChangePlanRollbackBundle`) | Safe — additive only |
| Slice C | Three new columns on `ROAChangePlan`: `requires_secondary_approval` (BooleanField, `default=False`), `secondary_approved_by` (CharField, blank), `secondary_approved_at` (DateTimeField, null+blank) | Safe — backward-compatible defaults |
| Slice C | Same three columns on `ASPAChangePlan` | Safe |

The `AWAITING_2ND` status value is a TextChoices addition only; no schema change for that.

Recommended: land Slice A migration first, Slice C migration second. They can be separate
migration files in the same migration sequence.

---

## 10. Remaining Gaps After This Plan

The following P8 items are **out of scope** for this plan and should be treated as follow-on:

| Gap | Why deferred |
|-----|--------------|
| Richer publication-state semantics (tag plan items against post-apply followup sync results) | Depends on P2 provider-sync maturation for reliable evidence quality |
| Broader extension of governance to ASPA lint plans | ASPA lint (`aspa_lint.py`) does not exist yet; its approval gate will follow P3+P4 naturally |
| Rollback bundle expiry / time-bounded approval window | Useful but not blocking; add as a field increment after V1 is validated operationally |
| Multi-step approval policies stored at org level (policy-driven rather than per-plan flag) | Org-level governance policy is a later abstraction; per-plan flag validates the workflow first |
