# Missing Web-UI Paths — Implementation Plan

## Context

The operator action table produced in the prior session identified 11 REST API actions that have
no corresponding web-UI path. This document specifies the exact changes required to implement
all of them.

All UI paths are under `/plugins/netbox-rpki/`. The three files touched are:

| File | Changes |
|------|---------|
| `netbox_rpki/views.py` | 11 new view classes + import additions |
| `netbox_rpki/forms.py` | 1 new form class |
| `netbox_rpki/urls.py` | 11 new `path()` registrations inside `build_object_urlpatterns` |
| `netbox_rpki/templates/netbox_rpki/` | 11 new HTML templates |

---

## Classification

| # | Action | URL | Type |
|---|--------|-----|------|
| 1 | Provider Account Timeline | `provideraccounts/{pk}/timeline/` | Instance data view (GET) |
| 2 | Provider Account Publication Diff Summary | `provideraccounts/{pk}/publication-diff-summary/` | Instance data view (GET) |
| 3 | Provider Account Summary | `provideraccounts/summary/` | List-level summary (GET) |
| 4 | Provider Snapshot Compare | `providersnapshots/{pk}/compare/` | Action view (POST with form) |
| 5 | Provider Snapshot Summary | `providersnapshots/summary/` | List-level summary (GET) |
| 6 | ROA Reconciliation Run Summary | `roareconciliationruns/summary/` | List-level summary (GET) |
| 7 | ASPA Reconciliation Run Summary | `aspareconciliationruns/summary/` | List-level summary (GET) |
| 8 | ROA Change Plan Summary | `roachangeplans/summary/` | List-level summary (GET) |
| 9 | ASPA Change Plan Summary | `aspachangeplans/summary/` | List-level summary (GET) |
| 10 | Validator Instance History Summary | `validatorinstances/{pk}/history-summary/` | Instance data view (GET) |
| 11 | Telemetry Source History Summary | `telemetrysources/{pk}/history-summary/` | Instance data view (GET) |

---

## Cross-Cutting Changes

### `views.py` — import additions

Add to the existing `from netbox_rpki.services import (...)` block (lines 29–61):

```python
    build_validator_run_history_summary,
    build_telemetry_run_history_summary,
```

Add a new top-level import after the `services.lifecycle_reporting` block (~line 74):

```python
from netbox_rpki.services.provider_sync_diff import (
    build_latest_provider_snapshot_diff,
    build_provider_snapshot_diff,
)
```

`build_provider_publication_diff_timeline` and `build_provider_account_summary` are already
imported at lines 68 and 75 respectively — no change needed there.

### `forms.py` — new form class

Add after the last existing form class (currently `BulkIntentRunActionForm`):

```python
class ProviderSnapshotCompareForm(forms.Form):
    base_snapshot = DynamicModelChoiceField(
        queryset=netbox_rpki.models.ProviderSnapshot.objects.none(),
        required=False,
        label='Base Snapshot',
        help_text=(
            'Leave blank to automatically compare against the most recent preceding '
            'completed snapshot for this provider account.'
        ),
    )

    fieldsets = (
        FieldSet('base_snapshot', name='Compare Options'),
    )

    def __init__(self, *args, provider_account=None, **kwargs):
        super().__init__(*args, **kwargs)
        if provider_account is not None:
            self.fields['base_snapshot'].queryset = (
                netbox_rpki.models.ProviderSnapshot.objects
                .filter(provider_account=provider_account)
                .order_by('-completed_at', 'name')
            )
```

---

## Implementation Details

---

### 1. Provider Account Timeline

Renders the lifecycle timeline for a single provider account as HTML.
The same data is already exported via `provideraccounts/{pk}/export/timeline/`.

**`views.py`** — add after `ProviderAccountTimelineExportView` (~line 550):

```python
class ProviderAccountTimelineView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/provideraccount_timeline.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request, pk):
        queryset = models.RpkiProviderAccount.objects.restrict(request.user, 'view')
        provider_account = get_object_or_404(queryset, pk=pk)
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        timeline = build_provider_lifecycle_timeline(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        return render(request, self.template_name, {
            'object': provider_account,
            'provider_account': provider_account,
            'timeline': timeline,
            'return_url': provider_account.get_absolute_url(),
        })
```

**`urls.py`** — in the existing `if spec.registry_key == 'rpkiprovideraccount':` block, append:

```python
urlpatterns.append(
    path(
        f'{path_prefix}/<int:pk>/timeline/',
        views.ProviderAccountTimelineView.as_view(),
        name='provideraccount_timeline',
    )
)
```

**Template:** `netbox_rpki/templates/netbox_rpki/provideraccount_timeline.html`

- Extends `generic/_base.html`
- Context variables: `provider_account`, `timeline` (result of `build_provider_lifecycle_timeline`)
- Display `timeline` entries (snapshots and diffs) in chronological order as a table or
  card-based timeline
- Include export links to `{% url 'plugins:netbox_rpki:provideraccount_export_timeline' provider_account.pk %}?format=json`
  and `?format=csv`

---

### 2. Provider Account Publication Diff Summary

Renders the publication diff timeline for a single provider account.
`build_provider_publication_diff_timeline` is already imported in `views.py` at line 68 but
currently unused by any UI view.

**`views.py`** — add after `ProviderAccountTimelineView`:

```python
class ProviderAccountPublicationDiffSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/provideraccount_publication_diff_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request, pk):
        queryset = models.RpkiProviderAccount.objects.restrict(request.user, 'view')
        provider_account = get_object_or_404(queryset, pk=pk)
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        diff_summary = build_provider_publication_diff_timeline(
            provider_account,
            visible_diff_ids=visible_diff_ids,
        )
        return render(request, self.template_name, {
            'object': provider_account,
            'provider_account': provider_account,
            'diff_summary': diff_summary,
            'return_url': provider_account.get_absolute_url(),
        })
```

**`urls.py`** — in the `if spec.registry_key == 'rpkiprovideraccount':` block, append:

```python
urlpatterns.append(
    path(
        f'{path_prefix}/<int:pk>/publication-diff-summary/',
        views.ProviderAccountPublicationDiffSummaryView.as_view(),
        name='provideraccount_publication_diff_summary',
    )
)
```

**Template:** `netbox_rpki/templates/netbox_rpki/provideraccount_publication_diff_summary.html`

- Extends `generic/_base.html`
- Context variables: `provider_account`, `diff_summary` (result of
  `build_provider_publication_diff_timeline`)
- Render diff entries showing before/after state per diff, grouped by snapshot diff

---

### 3. Provider Account Summary

A list-level summary view across all visible provider accounts.
`build_provider_account_summary` is already imported and called by
`OperationsDashboardExportView`; the logic here is the same.

**`views.py`** — add after `ProviderAccountPublicationDiffSummaryView`:

```python
class ProviderAccountSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/provideraccount_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request):
        provider_accounts = list(
            models.RpkiProviderAccount.objects.restrict(request.user, 'view')
        )
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_accounts)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_accounts)
            .values_list('pk', flat=True)
        )
        summary = build_provider_account_summary(
            provider_accounts,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        return render(request, self.template_name, {
            'summary': summary,
            'provider_account_count': len(provider_accounts),
            'return_url': reverse('plugins:netbox_rpki:provideraccount_list'),
        })
```

**`urls.py`** — in the `if spec.registry_key == 'rpkiprovideraccount':` block, append:

```python
urlpatterns.append(
    path(
        f'{path_prefix}/summary/',
        views.ProviderAccountSummaryView.as_view(),
        name='provideraccount_summary',
    )
)
```

**Template:** `netbox_rpki/templates/netbox_rpki/provideraccount_summary.html`

- Extends `generic/_base.html`
- Context variables: `summary` (from `build_provider_account_summary`),
  `provider_account_count`
- Present aggregate counts (healthy vs. requiring attention, by provider type, etc.)
- Include export link to `{% url 'plugins:netbox_rpki:operations_export' %}?format=json`
  (the existing operations dashboard export covers the same dataset)

---

### 4. Provider Snapshot Compare

The only POST action in the missing set. Creates a `ProviderSnapshotDiff` by comparing the
selected snapshot against a base. Mirrors `ProviderSnapshotViewSet.compare` in the API.

**`forms.py`** — see the `ProviderSnapshotCompareForm` in the Cross-Cutting section above.

**`views.py`** — add (imports of `build_provider_snapshot_diff` /
`build_latest_provider_snapshot_diff` and `ProviderSnapshotCompareForm` must be added first —
see Cross-Cutting section):

```python
class ProviderSnapshotCompareView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/providersnapshot_compare.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_providersnapshot'

    def _get_snapshot(self, request, pk):
        queryset = models.ProviderSnapshot.objects.restrict(request.user, 'view')
        return get_object_or_404(queryset, pk=pk)

    def _render(self, request, snapshot, *, form=None, diff=None, error_text=None, status=200):
        return render(request, self.template_name, {
            'object': snapshot,
            'snapshot': snapshot,
            'form': form or ProviderSnapshotCompareForm(provider_account=snapshot.provider_account),
            'diff': diff,
            'error_text': error_text,
            'return_url': snapshot.get_absolute_url(),
        }, status=status)

    def get(self, request, pk):
        snapshot = self._get_snapshot(request, pk)
        return self._render(request, snapshot)

    def post(self, request, pk):
        snapshot = self._get_snapshot(request, pk)
        form = ProviderSnapshotCompareForm(request.POST, provider_account=snapshot.provider_account)
        if not form.is_valid():
            return self._render(request, snapshot, form=form, status=400)

        base_snapshot = form.cleaned_data.get('base_snapshot')
        diff = error_text = None
        try:
            if base_snapshot is None:
                diff = build_latest_provider_snapshot_diff(snapshot)
                if diff is None:
                    error_text = 'No earlier completed snapshot is available for comparison.'
            else:
                diff = build_provider_snapshot_diff(
                    base_snapshot=base_snapshot,
                    comparison_snapshot=snapshot,
                )
        except ValueError as exc:
            error_text = str(exc)

        if diff is not None:
            messages.success(request, f'Created snapshot diff {diff}.')
            return redirect(diff.get_absolute_url())
        return self._render(request, snapshot, form=form, error_text=error_text)
```

**`urls.py`** — add a new `if` block for `providersnapshot` (does not exist yet):

```python
if spec.registry_key == 'providersnapshot':
    urlpatterns.append(
        path(
            f'{path_prefix}/<int:pk>/compare/',
            views.ProviderSnapshotCompareView.as_view(),
            name='providersnapshot_compare',
        )
    )
```

**`views.py` import** — add `ProviderSnapshotCompareForm` to the forms import at the top of
`views.py`. Check whether forms are imported via `from netbox_rpki import forms` or individually;
add accordingly.

**Template:** `netbox_rpki/templates/netbox_rpki/providersnapshot_compare.html`

- Extends `generic/_base.html`
- Context variables: `snapshot`, `form` (`ProviderSnapshotCompareForm`), `diff` (on success,
  but view redirects immediately so this won't normally be rendered), `error_text`
- Show snapshot metadata (provider account, status, fetched_at)
- Form: single optional `base_snapshot` selector
- On error, display `error_text` in an alert card (same pattern as
  `roachangeplan_preview.html`)

---

### 5. Provider Snapshot Summary

**`views.py`** — add:

```python
class ProviderSnapshotSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/providersnapshot_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_providersnapshot'

    def get(self, request):
        queryset = models.ProviderSnapshot.objects.restrict(request.user, 'view')
        by_status: dict[str, int] = {}
        latest_completed_at = None
        with_diff_count = 0
        for snapshot in queryset:
            by_status[snapshot.status] = by_status.get(snapshot.status, 0) + 1
            if snapshot.completed_at is not None and (
                latest_completed_at is None or snapshot.completed_at > latest_completed_at
            ):
                latest_completed_at = snapshot.completed_at
            if snapshot.diffs_as_comparison.exists():
                with_diff_count += 1
        return render(request, self.template_name, {
            'total_snapshots': queryset.count(),
            'by_status': by_status,
            'with_diff_count': with_diff_count,
            'latest_completed_at': latest_completed_at,
            'return_url': reverse('plugins:netbox_rpki:providersnapshot_list'),
        })
```

> The computation above mirrors `ProviderSnapshotViewSet.summary` in `api/views.py` verbatim.
> If that logic is later extracted to a service function, both callers should be updated.

**`urls.py`** — extend (or create) the `if spec.registry_key == 'providersnapshot':` block:

```python
if spec.registry_key == 'providersnapshot':
    urlpatterns.append(
        path(
            f'{path_prefix}/summary/',
            views.ProviderSnapshotSummaryView.as_view(),
            name='providersnapshot_summary',
        )
    )
    # (compare action also goes here — see item 4)
```

**Template:** `netbox_rpki/templates/netbox_rpki/providersnapshot_summary.html`

- Context variables: `total_snapshots`, `by_status`, `with_diff_count`, `latest_completed_at`
- Use the same card-grid layout as `operations_dashboard.html`

---

### 6. ROA Reconciliation Run Summary

**`views.py`** — add:

```python
class ROAReconciliationRunSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/roareconciliationrun_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_roareconciliationrun'

    def get(self, request):
        queryset = models.ROAReconciliationRun.objects.restrict(request.user, 'view')
        payload = {
            'total_runs': queryset.count(),
            'completed_runs': 0,
            'replacement_required_intent_total': 0,
            'replacement_required_published_total': 0,
            'lint_warning_total': 0,
            'lint_error_total': 0,
        }
        for run in queryset.prefetch_related('lint_runs'):
            if run.status == models.ValidationRunStatus.COMPLETED:
                payload['completed_runs'] += 1
            summary = dict(run.result_summary_json or {})
            payload['replacement_required_intent_total'] += summary.get(
                'replacement_required_intent_count', 0
            )
            payload['replacement_required_published_total'] += summary.get(
                'replacement_required_published_count', 0
            )
            lint_run = run.lint_runs.order_by('-started_at', '-created').first()
            if lint_run is not None:
                payload['lint_warning_total'] += lint_run.warning_count
                payload['lint_error_total'] += lint_run.error_count + lint_run.critical_count
        return render(request, self.template_name, {
            **payload,
            'return_url': reverse('plugins:netbox_rpki:roareconciliationrun_list'),
        })
```

> Computation mirrors `ROAReconciliationRunViewSet.summary` in `api/views.py`.

**`urls.py`** — add a new `if spec.registry_key == 'roareconciliationrun':` block:

```python
if spec.registry_key == 'roareconciliationrun':
    urlpatterns.append(
        path(
            f'{path_prefix}/summary/',
            views.ROAReconciliationRunSummaryView.as_view(),
            name='roareconciliationrun_summary',
        )
    )
```

**Template:** `netbox_rpki/templates/netbox_rpki/roareconciliationrun_summary.html`

- Context variables (all from `payload`): `total_runs`, `completed_runs`,
  `replacement_required_intent_total`, `replacement_required_published_total`,
  `lint_warning_total`, `lint_error_total`

---

### 7. ASPA Reconciliation Run Summary

**`views.py`** — add:

```python
class ASPAReconciliationRunSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/aspareconciliationrun_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_aspareconciliationrun'

    def get(self, request):
        queryset = models.ASPAReconciliationRun.objects.restrict(request.user, 'view')
        payload = {
            'total_runs': queryset.count(),
            'completed_runs': 0,
            'missing_count': 0,
            'missing_provider_count': 0,
            'extra_provider_count': 0,
            'orphaned_count': 0,
            'stale_count': 0,
        }
        for run in queryset:
            if run.status == models.ValidationRunStatus.COMPLETED:
                payload['completed_runs'] += 1
            summary = dict(run.result_summary_json or {})
            intent_types = dict(summary.get('intent_result_types') or {})
            published_types = dict(summary.get('published_result_types') or {})
            payload['missing_count'] += intent_types.get(
                models.ASPAIntentResultType.MISSING, 0
            )
            payload['missing_provider_count'] += intent_types.get(
                models.ASPAIntentResultType.MISSING_PROVIDER, 0
            )
            payload['extra_provider_count'] += published_types.get(
                models.PublishedASPAResultType.EXTRA_PROVIDER, 0
            )
            payload['orphaned_count'] += published_types.get(
                models.PublishedASPAResultType.ORPHANED, 0
            )
            payload['stale_count'] += (
                intent_types.get(models.ASPAIntentResultType.STALE, 0)
                + published_types.get(models.PublishedASPAResultType.STALE, 0)
            )
        return render(request, self.template_name, {
            **payload,
            'return_url': reverse('plugins:netbox_rpki:aspareconciliationrun_list'),
        })
```

> Computation mirrors `ASPAReconciliationRunViewSet.summary` in `api/views.py`.

**`urls.py`** — add a new `if spec.registry_key == 'aspareconciliationrun':` block:

```python
if spec.registry_key == 'aspareconciliationrun':
    urlpatterns.append(
        path(
            f'{path_prefix}/summary/',
            views.ASPAReconciliationRunSummaryView.as_view(),
            name='aspareconciliationrun_summary',
        )
    )
```

**Template:** `netbox_rpki/templates/netbox_rpki/aspareconciliationrun_summary.html`

- Context variables: `total_runs`, `completed_runs`, `missing_count`,
  `missing_provider_count`, `extra_provider_count`, `orphaned_count`, `stale_count`

---

### 8. ROA Change Plan Summary

The API viewset computes many simulation-related fields (see `ROAChangePlanViewSet.summary` in
`api/views.py` ~line 920). The UI view should compute the same fields.

**`views.py`** — add (copy the aggregation loop from `ROAChangePlanViewSet.summary` verbatim):

```python
class ROAChangePlanSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/roachangeplan_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_roachangeplan'

    def get(self, request):
        queryset = models.ROAChangePlan.objects.restrict(request.user, 'view')
        # Copy the aggregation loop from ROAChangePlanViewSet.summary in api/views.py
        # (lines ~920-980) to build the payload dict, then:
        return render(request, self.template_name, {
            **payload,
            'return_url': reverse('plugins:netbox_rpki:roachangeplan_list'),
        })
```

> Refer to `ROAChangePlanViewSet.summary` starting at line 920 in `api/views.py` for the full
> aggregation logic; replicate it directly here.

**`urls.py`** — extend the existing `if spec.registry_key == 'roachangeplan':` block
(which currently handles `preview`, `acknowledge-lint`, `approve`, `approve-secondary`,
`apply`, `simulate`):

```python
urlpatterns.append(
    path(
        f'{path_prefix}/summary/',
        views.ROAChangePlanSummaryView.as_view(),
        name='roachangeplan_summary',
    )
)
```

**Template:** `netbox_rpki/templates/netbox_rpki/roachangeplan_summary.html`

- Context variables: `total_plans`, `by_status`, `provider_backed_count`,
  `replacement_count_total`, `simulated_plan_count`, and all simulation-related count fields
  produced by the aggregation loop

---

### 9. ASPA Change Plan Summary

**`views.py`** — add (mirror `ASPAChangePlanViewSet.summary` in `api/views.py` ~line 1195):

```python
class ASPAChangePlanSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/aspachangeplan_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_aspachangeplan'

    def get(self, request):
        queryset = models.ASPAChangePlan.objects.restrict(request.user, 'view')
        # Copy the aggregation loop from ASPAChangePlanViewSet.summary in api/views.py
        # (lines ~1195-1230) to build the payload dict, then:
        return render(request, self.template_name, {
            **payload,
            'return_url': reverse('plugins:netbox_rpki:aspachangeplan_list'),
        })
```

**`urls.py`** — extend the existing `if spec.registry_key == 'aspachangeplan':` block:

```python
urlpatterns.append(
    path(
        f'{path_prefix}/summary/',
        views.ASPAChangePlanSummaryView.as_view(),
        name='aspachangeplan_summary',
    )
)
```

**Template:** `netbox_rpki/templates/netbox_rpki/aspachangeplan_summary.html`

- Context variables: `total_plans`, `by_status`, `provider_backed_count`,
  `replacement_count_total`, `provider_add_count_total`, `provider_remove_count_total`

---

### 10. Validator Instance History Summary

`build_validator_run_history_summary` is in `netbox_rpki.services` (imported by `api/views.py`)
but not currently imported in `views.py` — add it (see Cross-Cutting section).

**`views.py`** — add:

```python
class ValidatorInstanceHistorySummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/validatorinstance_history_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_validatorinstance'

    def get(self, request, pk):
        queryset = models.ValidatorInstance.objects.restrict(request.user, 'view')
        validator = get_object_or_404(queryset, pk=pk)
        history = build_validator_run_history_summary(validator)
        return render(request, self.template_name, {
            'object': validator,
            'validator': validator,
            'history': history,
            'return_url': validator.get_absolute_url(),
        })
```

**`urls.py`** — add a new `if spec.registry_key == 'validatorinstance':` block:

```python
if spec.registry_key == 'validatorinstance':
    urlpatterns.append(
        path(
            f'{path_prefix}/<int:pk>/history-summary/',
            views.ValidatorInstanceHistorySummaryView.as_view(),
            name='validatorinstance_history_summary',
        )
    )
```

**Template:** `netbox_rpki/templates/netbox_rpki/validatorinstance_history_summary.html`

- Extends `generic/_base.html`
- Context variables: `validator`, `history` (result of `build_validator_run_history_summary`)
- Check the return value of `build_validator_run_history_summary` in `services/` to identify
  the exact keys; render as a table of recent runs with status/timing columns
- Include a link back to the validator detail page

---

### 11. Telemetry Source History Summary

Identical pattern to item 10.

**`views.py`** — add:

```python
class TelemetrySourceHistorySummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/telemetrysource_history_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_telemetrysource'

    def get(self, request, pk):
        queryset = models.TelemetrySource.objects.restrict(request.user, 'view')
        source = get_object_or_404(queryset, pk=pk)
        history = build_telemetry_run_history_summary(source)
        return render(request, self.template_name, {
            'object': source,
            'telemetry_source': source,
            'history': history,
            'return_url': source.get_absolute_url(),
        })
```

**`urls.py`** — add a new `if spec.registry_key == 'telemetrysource':` block:

```python
if spec.registry_key == 'telemetrysource':
    urlpatterns.append(
        path(
            f'{path_prefix}/<int:pk>/history-summary/',
            views.TelemetrySourceHistorySummaryView.as_view(),
            name='telemetrysource_history_summary',
        )
    )
```

**Template:** `netbox_rpki/templates/netbox_rpki/telemetrysource_history_summary.html`

- Extends `generic/_base.html`
- Context variables: `telemetry_source`, `history` (result of
  `build_telemetry_run_history_summary`)
- Same presentation pattern as `validatorinstance_history_summary.html`

---

## Implementation Order

Dependencies are minimal; work items can be done in any order. Suggested sequence to batch
similar work:

1. **Cross-cutting changes first** — add the two import lines to `views.py`, add
   `ProviderSnapshotCompareForm` to `forms.py`. These unblock items 4, 10, 11.
2. **Items 1 + 2** (provider account instance views) — no new imports needed, services already
   imported. Easiest pair.
3. **Item 3** (provider account summary) — same file block as 1 + 2, natural to batch.
4. **Items 10 + 11** (validator/telemetry history) — once imports added, straightforward.
5. **Items 5 – 9** (five list-level summary views) — repetitive, do as a batch.
6. **Item 4** (snapshot compare) — most complex; depends on form and new service imports.

---

## Template Conventions

All templates follow the pattern established in the existing action templates:

```html
{% extends 'generic/_base.html' %}

{% block title %}… {{ object }}{% endblock %}

{% block content %}
  <div class="row mt-4">
    <div class="col col-md-10 offset-md-1">
      <div class="card border-primary">
        <h2 class="card-header">…</h2>
        <div class="card-body">
          …
        </div>
        <div class="card-footer text-end">
          <a href="{{ return_url }}" class="btn btn-outline-secondary">Back</a>
        </div>
      </div>
    </div>
  </div>
{% endblock %}
```

For list-level summary views (items 3, 5–9) that do not have a single object, omit `object`
from context and use the card-grid layout from `operations_dashboard.html` instead.

---

## Updated Operator Action Table (post-implementation)

Once all items are implemented the complete table will be:

| Action | Method | Web-UI Path | API Path |
|--------|--------|-------------|----------|
| Provider Account — sync | POST | `provideraccounts/{pk}/sync/` | `provideraccount/{pk}/sync/` |
| Provider Account — export lifecycle | GET | `provideraccounts/{pk}/export/lifecycle/` | `provideraccount/{pk}/export/lifecycle/` |
| Provider Account — export timeline | GET | `provideraccounts/{pk}/export/timeline/` | `provideraccount/{pk}/export/timeline/` |
| Provider Account — timeline view | GET | `provideraccounts/{pk}/timeline/` *(new)* | `provideraccount/{pk}/timeline/` |
| Provider Account — publication diff summary | GET | `provideraccounts/{pk}/publication-diff-summary/` *(new)* | `provideraccount/{pk}/publication-diff-summary/` |
| Provider Account — summary | GET | `provideraccounts/summary/` *(new)* | `provideraccount/summary/` |
| Provider Snapshot — compare | POST | `providersnapshots/{pk}/compare/` *(new)* | `providersnapshot/{pk}/compare/` |
| Provider Snapshot — summary | GET | `providersnapshots/summary/` *(new)* | `providersnapshot/summary/` |
| Organization — run ASPA reconciliation | POST | `orgs/{pk}/run-aspa-reconciliation/` | `organization/{pk}/run-aspa-reconciliation/` |
| Organization — create bulk intent run | POST | `orgs/{pk}/create-bulk-intent-run/` | `organization/{pk}/create-bulk-intent-run/` |
| Routing Intent Profile — run | POST | `routingintentprofiles/{pk}/run/` | `routingintentprofile/{pk}/run/` |
| Template Binding — preview | GET/POST | `routingintenttemplatebindings/{pk}/preview/` | `routingintenttemplatebinding/{pk}/preview/` |
| Template Binding — regenerate | POST | `routingintenttemplatebindings/{pk}/regenerate/` | `routingintenttemplatebinding/{pk}/regenerate/` |
| Intent Exception — approve | POST | `routingintentexceptions/{pk}/approve/` | `routingintentexception/{pk}/approve/` |
| Bulk Intent Run — approve | POST | `bulkintentruns/{pk}/approve/` | `bulkintentrun/{pk}/approve/` |
| Bulk Intent Run — approve secondary | POST | `bulkintentruns/{pk}/approve-secondary/` | `bulkintentrun/{pk}/approve-secondary/` |
| Delegated Publication Workflow — approve | POST | `delegatedpublicationworkflows/{pk}/approve/` | `delegatedpublicationworkflow/{pk}/approve/` |
| ROA Reconciliation Run — create plan | POST | `roareconciliationruns/{pk}/create-plan/` | `roareconciliationrun/{pk}/create-plan/` |
| ROA Reconciliation Run — summary | GET | `roareconciliationruns/summary/` *(new)* | `roareconciliationrun/summary/` |
| ASPA Reconciliation Run — create plan | POST | `aspareconciliationruns/{pk}/create-plan/` | `aspareconciliationrun/{pk}/create-plan/` |
| ASPA Reconciliation Run — summary | GET | `aspareconciliationruns/summary/` *(new)* | `aspareconciliationrun/summary/` |
| ROA Change Plan — preview | POST | `roachangeplans/{pk}/preview/` | `roachangeplan/{pk}/preview/` |
| ROA Change Plan — acknowledge lint | POST | `roachangeplans/{pk}/acknowledge-lint/` | `roachangeplan/{pk}/acknowledge-findings/` |
| ROA Change Plan — approve | POST | `roachangeplans/{pk}/approve/` | `roachangeplan/{pk}/approve/` |
| ROA Change Plan — approve secondary | POST | `roachangeplans/{pk}/approve-secondary/` | `roachangeplan/{pk}/approve-secondary/` |
| ROA Change Plan — apply | POST | `roachangeplans/{pk}/apply/` | `roachangeplan/{pk}/apply/` |
| ROA Change Plan — simulate | POST | `roachangeplans/{pk}/simulate/` | `roachangeplan/{pk}/simulate/` |
| ROA Change Plan — summary | GET | `roachangeplans/summary/` *(new)* | `roachangeplan/summary/` |
| ROA Lint Finding — suppress | POST | `roalintfindings/{pk}/suppress/` | `roalintfinding/{pk}/suppress/` |
| ROA Lint Suppression — lift | POST | `roalintsuppressions/{pk}/lift/` | `roalintsuppression/{pk}/lift/` |
| ASPA Change Plan — preview | POST | `aspachangeplans/{pk}/preview/` | `aspachangeplan/{pk}/preview/` |
| ASPA Change Plan — approve | POST | `aspachangeplans/{pk}/approve/` | `aspachangeplan/{pk}/approve/` |
| ASPA Change Plan — approve secondary | POST | `aspachangeplans/{pk}/approve-secondary/` | `aspachangeplan/{pk}/approve-secondary/` |
| ASPA Change Plan — apply | POST | `aspachangeplans/{pk}/apply/` | `aspachangeplan/{pk}/apply/` |
| ASPA Change Plan — summary | GET | `aspachangeplans/summary/` *(new)* | `aspachangeplan/summary/` |
| ROA Rollback Bundle — approve | POST | `roachangeplanrollbackbundles/{pk}/approve/` | `roachangeplanrollbackbundle/{pk}/approve/` |
| ROA Rollback Bundle — apply | POST | `roachangeplanrollbackbundles/{pk}/apply/` | `roachangeplanrollbackbundle/{pk}/apply/` |
| ASPA Rollback Bundle — approve | POST | `aspachangeplanrollbackbundles/{pk}/approve/` | `aspachangeplanrollbackbundle/{pk}/approve/` |
| ASPA Rollback Bundle — apply | POST | `aspachangeplanrollbackbundles/{pk}/apply/` | `aspachangeplanrollbackbundle/{pk}/apply/` |
| Validator Instance — history summary | GET | `validatorinstances/{pk}/history-summary/` *(new)* | `validatorinstance/{pk}/history-summary/` |
| Telemetry Source — history summary | GET | `telemetrysources/{pk}/history-summary/` *(new)* | `telemetrysource/{pk}/history-summary/` |
| Operations Dashboard | GET | `operations/` | — |
| Operations Dashboard — export | GET | `operations/export/` | — |
