# Intent Authority Map Implementation Plan

Prepared: April 17, 2026

## Purpose

Concrete build specification for the first function-oriented intent page: a read-only ROA-focused Authority Map that answers four questions per managed subject:

1. What ROA intent is currently authoritative?
2. What policy lineage produced that authority?
3. Has that authoritative intent been reconciled against runtime state?
4. If so, what is the drift posture, and is the evidence fresh?

This page uses only existing ROA data. No schema changes.

## Scope

### In scope

- New standalone page: Intent Authority Map (ROA only)
- Read-only operator workflow
- Latest-authoritative intent selection per active+enabled profile
- Joined view of authority lineage, reconciliation posture, and downstream execution state
- Filters for all major operational pivots
- Summary cards for at-a-glance triage
- Menu entry, route, view, form, table, template, and service module
- Unit and integration tests

### Out of scope

- ASPA authority map (requires provenance parity, see UX recommendations phase 3)
- Inline workflow actions (run, approve, create plan — phase 4)
- Database schema changes
- New REST or GraphQL endpoints
- Full subject-level conflict resolution across overlapping profiles
- Drift Workbench page (separate implementation, reuses authority map service)

## User-Facing Contract

### Page name

Intent Authority Map

### Route

- URL path: `/plugins/netbox_rpki/intent/authority/`
- URL name: `plugins:netbox_rpki:intent_authority_map`

### Navigation placement

Add a custom menu item to the `Intent` group in `navigation.py` at position 1, ahead of all existing model-family menu entries (the lowest existing item is Routing Intent Profiles at order 10).

```python
INTENT_AUTHORITY_MAP_MENU_ITEM = PluginMenuItem(
    link='plugins:netbox_rpki:intent_authority_map',
    link_text='Intent Authority Map',
    permissions=[
        'netbox_rpki.view_roaintent',
        'netbox_rpki.view_roaintentresult',
        'netbox_rpki.view_roareconciliationrun',
    ],
)
```

Append to `navigation_groups['Intent']` using the same pattern as the `IRR_DIVERGENCE_MENU_ITEM` append to `navigation_groups['IRR']`, but prepend instead of append so the task page appears before the model-family entries:

```python
navigation_groups['Intent'] = (INTENT_AUTHORITY_MAP_MENU_ITEM,) + navigation_groups.get('Intent', ())
```

### Permission model

The page requires `netbox_rpki.view_roaintent`. The view class will use `ContentTypePermissionRequiredMixin` (consistent with `OperationsDashboardView` and `IrrDivergenceDashboardView`).

## Authoritative Selection Rules

### Rule: latest completed derivation per active profile

For each `RoutingIntentProfile` that satisfies:
- `status = RoutingIntentProfileStatus.ACTIVE`
- `enabled = True`

Select the latest `IntentDerivationRun` that satisfies:
- `intent_profile = profile`
- `status = ValidationRunStatus.COMPLETED`

Order by `completed_at DESC`, take first.

The `ROAIntent` rows from that derivation run are the authoritative intent for that profile.

### Why derivation, not reconciliation, is the authority source

Authority should come from derivation because derivation defines what the system *intends*. Reconciliation is downstream evidence about what *is*. A derivation run may exist without any reconciliation run. A reconciliation run may fail. Tying authority to derivation keeps the concept of "what we intend" separate from "what we've verified."

### Reconciliation join rule

For each authoritative derivation run, select the latest `ROAReconciliationRun` that satisfies:
- `basis_derivation_run = derivation_run`
- `status = ValidationRunStatus.COMPLETED`

**When multiple reconciliation runs exist for the same derivation** (e.g., one with `comparison_scope=LOCAL_ROA_RECORDS` and one with `comparison_scope=PROVIDER_IMPORTED`): prefer `PROVIDER_IMPORTED` when the profile's organization has an active provider account with a completed provider snapshot. Fall back to `LOCAL_ROA_RECORDS` otherwise. Record `comparison_scope` on the row so the operator knows the evidence source.

### Profiles with no completed derivation

These profiles are excluded from the authority map entirely. The empty state should call them out: "N profiles have no completed derivation runs."

### Draft or disabled profiles

Profiles with `status != ACTIVE` or `enabled = False` are excluded. The summary cards should report: "N profiles excluded (draft or disabled)."

### Overlap handling

If two active profiles produce intents for the same prefix (matched on `prefix_cidr_text`), both rows are shown. Each gets an `overlap_warning` string naming the other profile. No merge is attempted — merge semantics require profile-priority rules that do not exist yet.

## Row Model

### New service module

Create: `netbox_rpki/services/intent_authority_map.py`

### Dataclass: RoaAuthorityMapFilters

```python
@dataclass(frozen=True)
class RoaAuthorityMapFilters:
    organization: Organization | None = None
    intent_profile: RoutingIntentProfile | None = None
    address_family: str = ''                           # 'ipv4' or 'ipv6' or '' for both
    derived_state: str = ''                            # from ROAIntentDerivedState
    exposure_state: str = ''                           # from ROAIntentExposureState
    delegated_entity: DelegatedAuthorizationEntity | None = None
    managed_relationship: ManagedAuthorizationRelationship | None = None
    provider_account: RpkiProviderAccount | None = None
    run_state: str = ''                                # computed classification
    drift_state: str = ''                              # computed classification
    q: str = ''                                        # text search
```

Design decisions:

- `tenant` is omitted from the filter form. Tenant is a scope dimension on ROAIntent (`scope_tenant`) but not a primary operational pivot for authority review. It can be added later if users request it.
- `template_binding` is omitted. Bindings are referenced in `summary_json` but are not a direct FK on ROAIntent. Filtering by binding would require a subquery through the binding context group entries in `summary_json`, which is complex for phase 1.
- `run_state` and `drift_state` are computed values that require post-query filtering. The service applies them after row assembly, not at the ORM level.
- `q` matches against: `prefix_cidr_text`, `origin_asn_value` (as string), `intent_profile.name`, `source_rule.name` (when present), `explanation`.

### Dataclass: RoaAuthorityMapRow

```python
@dataclass(frozen=True)
class RoaAuthorityMapRow:
    # Identity
    authority_key: str                                # ROAIntent.intent_key
    subject_label: str                                # human-readable: "192.0.2.0/24 → AS64496 /24"
    prefix_cidr_text: str                             # ROAIntent.prefix_cidr_text
    origin_asn_value: int | None                      # ROAIntent.origin_asn_value
    max_length: int | None                            # ROAIntent.max_length
    address_family: str                               # ROAIntent.address_family ('ipv4' or 'ipv6')
    is_as0: bool                                      # ROAIntent.is_as0

    # Authority chain: organization and delegation
    organization: Organization                        # ROAIntent.organization
    delegated_entity: DelegatedAuthorizationEntity | None
    managed_relationship: ManagedAuthorizationRelationship | None

    # Authority chain: policy lineage
    intent_profile: RoutingIntentProfile              # ROAIntent.intent_profile
    derivation_run: IntentDerivationRun               # ROAIntent.derivation_run
    source_rule: RoutingIntentRule | None              # ROAIntent.source_rule
    applied_override: ROAIntentOverride | None        # ROAIntent.applied_override
    template_binding_names: tuple[str, ...]           # from summary_json.binding_context_groups keys
    profile_context_group_names: tuple[str, ...]      # from summary_json.profile_context_group_names
    binding_context_group_names: tuple[str, ...]      # flattened from summary_json.binding_context_groups values

    # Scope
    scope_tenant: Tenant | None                       # ROAIntent.scope_tenant
    scope_vrf: VRF | None                             # ROAIntent.scope_vrf
    scope_site: Site | None                           # ROAIntent.scope_site
    scope_region: Region | None                       # ROAIntent.scope_region

    # Authority state
    derived_state: str                                # ROAIntent.derived_state (ACTIVE/SUPPRESSED/SHADOWED)
    exposure_state: str                               # ROAIntent.exposure_state (ADVERTISED/ELIGIBLE_NOT_ADVERTISED/BLOCKED)

    # Reconciliation state
    reconciliation_run: ROAReconciliationRun | None
    comparison_scope: str                             # ROAReconciliationRun.comparison_scope or ''
    run_state: str                                    # computed classification
    drift_state: str                                  # computed classification (maps ROAIntentResultType)
    severity: str                                     # from ROAIntentResult.severity or ''
    latest_intent_result: ROAIntentResult | None

    # Downstream execution state
    latest_change_plan: ROAChangePlan | None
    change_plan_status: str                           # ROAChangePlan.status or ''
    provider_account: RpkiProviderAccount | None      # from ROAChangePlan or reconciliation run

    # Binding freshness (from summary_json cross-reference)
    binding_freshness: str                            # CURRENT/STALE/PENDING/INVALID or '' if no binding

    # Computed summaries
    authority_reason_summary: str                     # condensed explanation + override/exception gloss
    reconciliation_summary: str                       # e.g., "Match", "Missing — no runtime ROA", "ASN mismatch (expected 64496, found 64497)"
    publication_summary: str                          # e.g., "Plan: DRAFT", "Plan: APPLIED", "No plan"
    overlap_warning: str                              # '' or "Also covered by profile: X"

    # Source objects for drill-down links
    roa_intent: ROAIntent
```

Design decisions compared to original plan:

- **Added** `address_family`, `is_as0`, `exposure_state`, `comparison_scope`, `binding_freshness`, `scope_tenant/vrf/site/region`, `change_plan_status`, `provider_account`.
- **Removed** `latest_change_plan` as a separate FK on the dataclass — kept it but clarified it tracks the latest change plan from the source reconciliation run.
- **Removed** `tenant` as a standalone field — it is represented as `scope_tenant`.
- `authority_key` uses `ROAIntent.intent_key` which is a SHA-256 hash of prefix+origin+max_length+scope.
- `subject_label` is a human-readable rendering like `192.0.2.0/24 → AS64496 /24` for rows with an origin, or `192.0.2.0/24 → AS0` for AS0 rows.

### Classification: run_state

| Value | Condition |
|-------|-----------|
| `unreconciled` | No completed reconciliation run for this derivation run |
| `reconciled_current` | Latest reconciliation exists and the intent result is MATCH |
| `reconciled_with_drift` | Latest reconciliation exists and the intent result is not MATCH |
| `reconciliation_failed` | Latest reconciliation run has status=FAILED |

### Classification: drift_state

Map `ROAIntentResultType` values into operational groups:

| drift_state | ROAIntentResultType values |
|-------------|--------------------------|
| `match` | MATCH |
| `missing` | MISSING |
| `origin_mismatch` | ASN_MISMATCH |
| `origin_and_length_mismatch` | ASN_AND_MAX_LENGTH_OVERBROAD, ASN_AND_MAX_LENGTH_TOO_NARROW, ASN_AND_MAX_LENGTH_MISMATCH |
| `prefix_mismatch` | PREFIX_MISMATCH |
| `max_length_overbroad` | MAX_LENGTH_OVERBROAD |
| `max_length_too_narrow` | MAX_LENGTH_TOO_NARROW |
| `stale` | STALE |
| `inactive_intent` | INACTIVE_INTENT |
| `suppressed_by_policy` | SUPPRESSED_BY_POLICY |
| `unknown` | No intent result, or unreconciled |

This preserves the full granularity of the 12-value `ROAIntentResultType` enum rather than collapsing it into fewer categories. The table rendering can display a friendly label; the filter form can offer a dropdown of these values.

### Classification: severity

Mirror `ROAIntentResult.severity` directly (INFO/WARNING/ERROR/CRITICAL). Empty string when unreconciled.

## Service Functions

### Primary entry point

```python
def build_roa_authority_map(
    *,
    filters: RoaAuthorityMapFilters,
) -> RoaAuthorityMapResult:
    """
    Build the authority map for all active ROA intent profiles,
    filtered by the given criteria.

    Returns a result object containing the rows, summary counts,
    and diagnostic metadata.
    """
```

### Result container

```python
@dataclass(frozen=True)
class RoaAuthorityMapResult:
    rows: list[RoaAuthorityMapRow]
    total_row_count: int
    authority_counts: dict[str, int]          # derived_state → count
    exposure_counts: dict[str, int]           # exposure_state → count
    run_state_counts: dict[str, int]          # run_state → count
    drift_counts: dict[str, int]              # drift_state → count
    overlap_count: int
    excluded_profile_count: int               # draft or disabled
    no_derivation_profile_count: int          # active but no completed derivation
    profiles_with_stale_bindings: list[str]   # profile names with STALE/INVALID/PENDING bindings
```

### Internal functions

```python
def get_authoritative_derivation_runs(
    *,
    filters: RoaAuthorityMapFilters,
) -> dict[int, IntentDerivationRun]:
    """
    For each active+enabled RoutingIntentProfile (optionally filtered),
    return the latest completed IntentDerivationRun.
    Returns a dict of {profile_id: derivation_run}.
    """

def get_reconciliation_runs_for_derivations(
    *,
    derivation_run_ids: set[int],
) -> dict[int, ROAReconciliationRun]:
    """
    For each derivation run ID, find the latest completed ROAReconciliationRun
    whose basis_derivation_run matches. Prefer PROVIDER_IMPORTED over
    LOCAL_ROA_RECORDS when both exist.
    Returns a dict of {derivation_run_id: reconciliation_run}.
    """

def get_intent_results_for_reconciliations(
    *,
    reconciliation_run_ids: set[int],
) -> dict[int, ROAIntentResult]:
    """
    Load ROAIntentResult rows for the given reconciliation runs.
    Returns a dict of {roa_intent_id: intent_result}.
    """

def get_latest_change_plans_for_reconciliations(
    *,
    reconciliation_run_ids: set[int],
) -> dict[int, ROAChangePlan]:
    """
    For each reconciliation run, find the latest ROAChangePlan
    (any status — including DRAFT, APPROVED, APPLIED, FAILED).
    Returns a dict of {reconciliation_run_id: change_plan}.
    """

def classify_row(
    *,
    intent: ROAIntent,
    intent_result: ROAIntentResult | None,
    reconciliation_run: ROAReconciliationRun | None,
) -> tuple[str, str, str]:
    """
    Compute (run_state, drift_state, severity) for a single authority row.
    """

def detect_prefix_overlaps(
    rows: list[RoaAuthorityMapRow],
) -> dict[str, list[str]]:
    """
    Find rows from different profiles that share the same prefix_cidr_text.
    Returns {authority_key: [overlapping profile names]}.
    """

def build_subject_label(intent: ROAIntent) -> str:
    """
    Render a human-readable subject label.
    Examples:
      "192.0.2.0/24 → AS64496 /24"
      "2001:db8::/32 → AS0"
      "10.0.0.0/8 → AS64496 /8 (not advertised)"
    """

def parse_summary_json(summary_json: dict) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], str]:
    """
    Extract (template_binding_names, profile_context_group_names,
    binding_context_group_names, binding_freshness) from ROAIntent.summary_json.

    binding_freshness is determined by loading the template bindings referenced
    in binding_context_groups keys and checking their state field.
    """

def build_authority_reason_summary(intent: ROAIntent) -> str:
    """
    Condense the explanation into a short summary.
    Truncate at ~120 chars. Include override or exception gloss if present.
    """

def build_reconciliation_summary(intent_result: ROAIntentResult | None) -> str:
    """
    Derive an operator-friendly reconciliation summary.
    Examples:
      "Match"
      "Missing — no runtime ROA"
      "ASN mismatch (expected 64496, found 64497)"
      "maxLength overbroad (intent /24, runtime /16)"
      "Not reconciled"
    """

def build_publication_summary(change_plan: ROAChangePlan | None) -> str:
    """
    Derive a publication/execution summary.
    Examples:
      "Plan: DRAFT"
      "Plan: APPROVED (dual-approval)"
      "Plan: APPLIED 2026-04-15"
      "Plan: FAILED"
      "No plan"
    """
```

### Row assembly algorithm (detailed)

1. **Resolve authoritative derivation runs.** Query all `RoutingIntentProfile` where `status=ACTIVE` and `enabled=True`. Apply organization filter if set. For each profile, query `IntentDerivationRun` where `status=COMPLETED`, order by `completed_at DESC`, limit 1. Result: `dict[int, IntentDerivationRun]` keyed by profile_id.

2. **Load authoritative intents.** Query `ROAIntent.objects.filter(derivation_run__in=derivation_runs.values()).select_related('organization', 'intent_profile', 'derivation_run', 'delegated_entity', 'managed_relationship', 'source_rule', 'applied_override', 'scope_tenant', 'scope_vrf', 'scope_site', 'scope_region', 'prefix', 'origin_asn')`. Apply direct filters: `address_family`, `derived_state`, `exposure_state`, `delegated_entity`, `managed_relationship`, `organization`, `intent_profile`. Apply `q` text filter using `Q(prefix_cidr_text__icontains=q) | Q(origin_asn_value__icontains=q_as_int) | Q(explanation__icontains=q) | Q(intent_profile__name__icontains=q)`.

3. **Load reconciliation runs.** Call `get_reconciliation_runs_for_derivations()` with the derivation run IDs from step 1. Result: `dict[int, ROAReconciliationRun]` keyed by derivation_run_id.

4. **Load intent results.** Call `get_intent_results_for_reconciliations()` with the reconciliation run IDs from step 3. Result: `dict[int, ROAIntentResult]` keyed by roa_intent_id.

5. **Load change plans.** Call `get_latest_change_plans_for_reconciliations()` with the reconciliation run IDs from step 3. Result: `dict[int, ROAChangePlan]` keyed by reconciliation_run_id. Use `select_related('provider_account')`.

6. **Parse summary_json.** For each intent, call `parse_summary_json()` to extract template binding names, context group names, and binding freshness. This requires a single bulk load of `RoutingIntentTemplateBinding` objects referenced in `summary_json.binding_context_groups` keys — gather all referenced binding PKs across all intents first, then bulk-load.

7. **Assemble rows.** For each `ROAIntent`, look up its reconciliation run, intent result, and change plan from the indexed dicts. Call `classify_row()`, `build_subject_label()`, `build_authority_reason_summary()`, `build_reconciliation_summary()`, `build_publication_summary()`. Construct `RoaAuthorityMapRow`.

8. **Detect overlaps.** Call `detect_prefix_overlaps()` on the assembled rows. For each overlap, set the `overlap_warning` string.

9. **Apply post-query filters.** `run_state` and `drift_state` filters cannot be applied at the ORM level because they are computed. Apply them as list comprehension filters on the assembled rows.

10. **Compute summary counts.** Count rows by `derived_state`, `exposure_state`, `run_state`, `drift_state`. Count overlapping rows. Count excluded profiles and profiles with no derivation.

11. **Return RoaAuthorityMapResult.**

### Performance guardrails

- **Bulk loads, not per-row queries.** Steps 2-6 each perform one or two ORM queries total, not one per row. The `select_related()` in step 2 eliminates N+1 for the most common FK traversals.
- **Indexed lookups.** Step 4 uses `roa_intent_id` from `ROAIntentResult` to build a dict. Step 5 uses `source_reconciliation_run_id` from `ROAChangePlan` to build a dict.
- **Deferred full-text parsing.** `summary_json` parsing happens per-row but is a dict lookup, not a database hit.
- **Expected scale.** A typical profile with 500 prefixes × 1-3 origins per prefix produces 500-1500 ROAIntent rows per derivation run. An organization with 5 profiles produces 2,500-7,500 rows. Server-side pagination (default 50 rows/page) keeps per-request work bounded.
- **Overlap detection.** Group rows by `prefix_cidr_text`. This is O(N) with a dict. No O(N²) comparison needed.
- **Binding freshness.** The bulk binding load uses `pk__in=binding_ids`, which uses a single `IN` query. The binding set is expected to be small (tens, not thousands).

## Form Plan

### New form class

Add to `netbox_rpki/forms.py`:

```python
class IntentAuthorityMapFilterForm(forms.Form):
    organization = DynamicModelChoiceField(
        queryset=Organization.objects.all(),
        required=False,
        label='Organization',
    )
    intent_profile = DynamicModelChoiceField(
        queryset=RoutingIntentProfile.objects.all(),
        required=False,
        label='Intent Profile',
        query_params={'organization_id': '$organization'},
    )
    address_family = forms.ChoiceField(
        choices=[('', 'All')] + list(AddressFamily.choices),
        required=False,
        label='Address Family',
    )
    derived_state = forms.ChoiceField(
        choices=[('', 'All')] + list(ROAIntentDerivedState.choices),
        required=False,
        label='Derived State',
    )
    exposure_state = forms.ChoiceField(
        choices=[('', 'All')] + list(ROAIntentExposureState.choices),
        required=False,
        label='Exposure',
    )
    delegated_entity = DynamicModelChoiceField(
        queryset=DelegatedAuthorizationEntity.objects.all(),
        required=False,
        label='Delegated Entity',
        query_params={'organization_id': '$organization'},
    )
    managed_relationship = DynamicModelChoiceField(
        queryset=ManagedAuthorizationRelationship.objects.all(),
        required=False,
        label='Managed Relationship',
        query_params={'organization_id': '$organization'},
    )
    run_state = forms.ChoiceField(
        choices=[
            ('', 'All'),
            ('unreconciled', 'Unreconciled'),
            ('reconciled_current', 'Reconciled — Current'),
            ('reconciled_with_drift', 'Reconciled — With Drift'),
            ('reconciliation_failed', 'Reconciliation Failed'),
        ],
        required=False,
        label='Run State',
    )
    drift_state = forms.ChoiceField(
        choices=[
            ('', 'All'),
            ('match', 'Match'),
            ('missing', 'Missing'),
            ('origin_mismatch', 'Origin Mismatch'),
            ('origin_and_length_mismatch', 'Origin + Length Mismatch'),
            ('prefix_mismatch', 'Prefix Mismatch'),
            ('max_length_overbroad', 'maxLength Overbroad'),
            ('max_length_too_narrow', 'maxLength Too Narrow'),
            ('stale', 'Stale'),
            ('inactive_intent', 'Inactive Intent'),
            ('suppressed_by_policy', 'Suppressed by Policy'),
        ],
        required=False,
        label='Drift',
    )
    q = forms.CharField(
        required=False,
        label='Search',
        widget=forms.TextInput(attrs={'placeholder': 'Prefix, ASN, profile, or explanation'}),
    )
```

This follows the `IrrDivergenceDashboardFilterForm` pattern: a plain `forms.Form` (not a model form) because this page is a service projection, not a model list.

### Filter-to-service mapping

The view translates form cleaned_data into `RoaAuthorityMapFilters`:

```python
filters = RoaAuthorityMapFilters(
    organization=form.cleaned_data.get('organization'),
    intent_profile=form.cleaned_data.get('intent_profile'),
    address_family=form.cleaned_data.get('address_family', ''),
    derived_state=form.cleaned_data.get('derived_state', ''),
    exposure_state=form.cleaned_data.get('exposure_state', ''),
    delegated_entity=form.cleaned_data.get('delegated_entity'),
    managed_relationship=form.cleaned_data.get('managed_relationship'),
    run_state=form.cleaned_data.get('run_state', ''),
    drift_state=form.cleaned_data.get('drift_state', ''),
    q=form.cleaned_data.get('q', ''),
)
```

## Table Plan

### New table class

Add to `netbox_rpki/tables.py`:

```python
class RoaAuthorityMapTable(NetBoxTable):
    subject = tables.Column(
        verbose_name='Subject',
        accessor='subject_label',
        linkify=lambda record: record.roa_intent.get_absolute_url(),
        order_by=('prefix_cidr_text', 'origin_asn_value', 'max_length'),
    )
    organization = tables.Column(
        accessor='organization',
        linkify=True,
    )
    intent_profile = tables.Column(
        accessor='intent_profile',
        linkify=True,
        verbose_name='Profile',
    )
    address_family = tables.Column(
        accessor='address_family',
        verbose_name='AF',
    )
    derived_state = tables.Column(
        verbose_name='Authority',
    )
    exposure_state = tables.Column(
        verbose_name='Exposure',
    )
    run_state = tables.Column(
        verbose_name='Run State',
    )
    drift_state = tables.Column(
        verbose_name='Drift',
    )
    severity = tables.Column(
        verbose_name='Severity',
    )
    authority_reason_summary = tables.Column(
        verbose_name='Why Authoritative',
    )
    reconciliation_summary = tables.Column(
        verbose_name='Reconciliation',
    )
    publication_summary = tables.Column(
        verbose_name='Execution',
    )
    binding_freshness = tables.Column(
        verbose_name='Binding',
    )
    overlap_warning = tables.Column(
        verbose_name='Overlap',
    )

    class Meta:
        fields = (
            'subject',
            'organization',
            'intent_profile',
            'address_family',
            'derived_state',
            'exposure_state',
            'run_state',
            'drift_state',
            'severity',
            'authority_reason_summary',
            'reconciliation_summary',
            'publication_summary',
            'binding_freshness',
            'overlap_warning',
        )
        default_columns = (
            'subject',
            'organization',
            'intent_profile',
            'derived_state',
            'run_state',
            'drift_state',
            'severity',
            'authority_reason_summary',
            'publication_summary',
        )
```

### Column rendering notes

- **`subject`**: Links to the `ROAIntent` detail page. Rendered as `prefix_cidr_text → ASorigin /maxlength` using `subject_label`.
- **`derived_state`**: Badge styling — green for ACTIVE, yellow for SUPPRESSED, grey for SHADOWED.
- **`exposure_state`**: Badge — blue for ADVERTISED, grey for ELIGIBLE_NOT_ADVERTISED, red for BLOCKED.
- **`run_state`**: Badge — grey for unreconciled, green for reconciled_current, orange for reconciled_with_drift, red for reconciliation_failed.
- **`drift_state`**: Badge with severity-colored background.
- **`severity`**: Colored badge matching `ReconciliationSeverity`.
- **`binding_freshness`**: Badge — green for CURRENT, yellow for STALE, orange for PENDING, red for INVALID, grey if no binding.
- **`overlap_warning`**: Only rendered when non-empty; shows a warning icon and the conflicting profile name.
- **`authority_reason_summary`**: Truncated to ~120 chars with tooltip for full text.
- **`reconciliation_summary`**: Short derived string from `ROAIntentResult`, not raw explanation.
- **`publication_summary`**: Shows change plan status or "No plan."

## View Plan

### New view class

Add to `netbox_rpki/views.py`:

```python
class IntentAuthorityMapView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/intent_authority_map.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_roaintent'

    def get(self, request):
        form = forms.IntentAuthorityMapFilterForm(request.GET or None)

        if form.is_valid():
            filters = RoaAuthorityMapFilters(
                organization=form.cleaned_data.get('organization'),
                intent_profile=form.cleaned_data.get('intent_profile'),
                address_family=form.cleaned_data.get('address_family', ''),
                derived_state=form.cleaned_data.get('derived_state', ''),
                exposure_state=form.cleaned_data.get('exposure_state', ''),
                delegated_entity=form.cleaned_data.get('delegated_entity'),
                managed_relationship=form.cleaned_data.get('managed_relationship'),
                run_state=form.cleaned_data.get('run_state', ''),
                drift_state=form.cleaned_data.get('drift_state', ''),
                q=form.cleaned_data.get('q', ''),
            )
        else:
            filters = RoaAuthorityMapFilters()

        result = build_roa_authority_map(filters=filters)
        table = tables.RoaAuthorityMapTable(result.rows)
        paginate_table(table, request)

        return render(request, self.template_name, {
            'filter_form': form,
            'table': table,
            'result': result,
        })
```

### Template context

The template receives:

| Variable | Type | Description |
|----------|------|-------------|
| `filter_form` | `IntentAuthorityMapFilterForm` | Bound or unbound filter form |
| `table` | `RoaAuthorityMapTable` | Paginated authority table |
| `result` | `RoaAuthorityMapResult` | Summary counts and diagnostic metadata |

## Template Plan

### New template

Create: `netbox_rpki/templates/netbox_rpki/intent_authority_map.html`

### Structure

```
{% extends 'generic/_base.html' %}
{% block title %}Intent Authority Map{% endblock %}
{% block content %}
  1. Header card with page explanation
  2. Filter form (follows IRR divergence dashboard pattern)
  3. Summary cards row:
     - Total authoritative subjects
     - Unreconciled (run_state_counts.unreconciled)
     - With drift (run_state_counts.reconciled_with_drift)
     - Missing from runtime (drift_counts.missing)
     - Overlapping profiles (overlap_count)
     - Excluded profiles (excluded_profile_count + no_derivation_profile_count)
  4. Binding freshness warnings:
     - If profiles_with_stale_bindings is non-empty, show an alert:
       "N profiles have stale or invalid template bindings.
        Authority may not reflect the latest template policy."
  5. Authority table (rendered via {% render_table table %} or manual iteration)
  6. Empty state:
     - If no rows and no filters applied:
       "No active routing intent profiles have completed derivation runs.
        Create a profile and run derivation to populate this page."
     - If no rows and filters applied:
       "No authoritative intent rows match the current filters."
{% endblock %}
```

### Visual design notes

- The summary cards follow the exact pattern from `irr_divergence_dashboard.html`: `.row.g-3` with `.col.col-md-2` tiles, each with a `.text-muted.small.text-uppercase` title, a `.fs-2.fw-semibold` count, and a `.text-muted` description.
- The filter form follows the IRR divergence dashboard's inline form layout.
- The table uses `{% render_table table %}` from django-tables2 for pagination.
- Binding freshness warnings use a Bootstrap alert (`alert-warning`) below the summary cards.

## URL Plan

Add to `netbox_rpki/urls.py` in the top-level standalone routes section (near existing `operations/` and `irr/divergence/` routes):

```python
path('intent/authority/', views.IntentAuthorityMapView.as_view(), name='intent_authority_map'),
```

## Test Plan

### Service unit tests

New file: `netbox_rpki/tests/test_intent_authority_map.py`

**Authority selection tests**:

| Test name | Scenario |
|-----------|----------|
| `test_selects_latest_completed_derivation_per_profile` | Two completed runs; returns the one with later `completed_at` |
| `test_excludes_pending_and_failed_derivation_runs` | Only pending and failed runs exist; returns empty |
| `test_excludes_draft_and_disabled_profiles` | Profile has `status=DRAFT` or `enabled=False`; excluded |
| `test_filters_by_organization` | Two orgs, each with a profile; filter to one org |
| `test_filters_by_intent_profile` | Multiple profiles; filter returns only the specified profile's intents |

**Reconciliation join tests**:

| Test name | Scenario |
|-----------|----------|
| `test_joins_latest_completed_reconciliation` | Two completed recon runs for same derivation; returns latest |
| `test_prefers_provider_imported_over_local` | Both LOCAL and PROVIDER_IMPORTED runs exist; returns PROVIDER_IMPORTED |
| `test_marks_unreconciled_when_no_recon_exists` | Derivation run with no reconciliation; run_state = unreconciled |
| `test_marks_failed_when_recon_failed` | Reconciliation with status=FAILED; run_state = reconciliation_failed |

**Classification tests**:

| Test name | Scenario |
|-----------|----------|
| `test_classifies_match_as_reconciled_current` | Intent result type = MATCH → run_state=reconciled_current, drift_state=match |
| `test_classifies_missing_as_drift` | Intent result type = MISSING → run_state=reconciled_with_drift, drift_state=missing |
| `test_classifies_asn_mismatch` | Intent result type = ASN_MISMATCH → drift_state=origin_mismatch |
| `test_classifies_max_length_overbroad` | Intent result type = MAX_LENGTH_OVERBROAD → drift_state=max_length_overbroad |
| `test_severity_mirrors_intent_result` | Intent result severity = CRITICAL → severity = critical |

**Overlap detection tests**:

| Test name | Scenario |
|-----------|----------|
| `test_detects_overlap_across_profiles` | Two profiles produce intents for same prefix; both get overlap_warning |
| `test_no_overlap_for_different_prefixes` | Two profiles, different prefixes; no overlap_warning |
| `test_same_profile_same_prefix_not_overlap` | Same profile, same prefix (different origins); not an overlap |

**Summary and projection tests**:

| Test name | Scenario |
|-----------|----------|
| `test_builds_subject_label_with_origin_and_maxlength` | Standard ROA intent → "192.0.2.0/24 → AS64496 /24" |
| `test_builds_subject_label_for_as0` | AS0 intent → "192.0.2.0/24 → AS0" |
| `test_parses_summary_json_context_groups` | summary_json with profile and binding context groups → correct tuples |
| `test_publication_summary_for_draft_plan` | Change plan with status=DRAFT → "Plan: DRAFT" |
| `test_publication_summary_for_applied_plan` | Change plan with status=APPLIED → "Plan: APPLIED ..." |
| `test_publication_summary_when_no_plan` | No change plan → "No plan" |
| `test_reconciliation_summary_for_match` | Intent result MATCH → "Match" |
| `test_reconciliation_summary_for_missing` | Intent result MISSING → "Missing — no runtime ROA" |

**Filter tests**:

| Test name | Scenario |
|-----------|----------|
| `test_filters_by_address_family` | Mix of IPv4 and IPv6 intents; filter to IPv4 only |
| `test_filters_by_derived_state` | Mix of ACTIVE and SUPPRESSED; filter to SUPPRESSED |
| `test_filters_by_exposure_state` | Filter to ADVERTISED only |
| `test_filters_by_run_state_post_query` | Filter to reconciled_with_drift only (post-query filter) |
| `test_filters_by_drift_state_post_query` | Filter to missing only (post-query filter) |
| `test_q_matches_prefix` | q="192.0.2" matches prefix_cidr_text |
| `test_q_matches_asn` | q="64496" matches origin_asn_value |
| `test_q_matches_profile_name` | q="production" matches intent_profile.name |

### URL tests

Add to `netbox_rpki/tests/test_urls.py`:

```python
def test_intent_authority_map_resolves(self):
    url = reverse('plugins:netbox_rpki:intent_authority_map')
    self.assertEqual(url, '/plugins/netbox_rpki/intent/authority/')
    match = resolve(url)
    self.assertEqual(match.url_name, 'intent_authority_map')
```

### Navigation tests

Add to `netbox_rpki/tests/test_navigation.py`:

```python
def test_intent_authority_map_menu_item_in_intent_group(self):
    items = navigation_groups.get('Intent', ())
    labels = [item.link_text for item in items]
    self.assertIn('Intent Authority Map', labels)

def test_intent_authority_map_menu_item_is_first(self):
    items = navigation_groups.get('Intent', ())
    self.assertEqual(items[0].link_text, 'Intent Authority Map')

def test_intent_authority_map_menu_item_permissions(self):
    items = navigation_groups.get('Intent', ())
    map_item = [i for i in items if i.link_text == 'Intent Authority Map'][0]
    self.assertIn('netbox_rpki.view_roaintent', map_item.permissions)
```

### View integration tests

Add to `netbox_rpki/tests/test_views.py`:

| Test name | Scenario |
|-----------|----------|
| `test_intent_authority_map_renders_200` | GET the page with an active profile and completed derivation; assert 200 |
| `test_intent_authority_map_shows_summary_cards` | Assert response contains summary count elements |
| `test_intent_authority_map_filters_narrow_results` | GET with organization filter; assert fewer rows than unfiltered |
| `test_intent_authority_map_empty_state_no_derivation` | No derivation runs exist; assert empty state message |
| `test_intent_authority_map_empty_state_filters` | Filters exclude all rows; assert filter-specific empty message |
| `test_intent_authority_map_surfaces_overlap_warning` | Two profiles cover same prefix; assert overlap indicator in response |
| `test_intent_authority_map_surfaces_binding_freshness_warning` | Profile has STALE binding; assert warning alert in response |
| `test_intent_authority_map_requires_permission` | User without view_roaintent permission; assert 403 |

## Build Order

| Step | Deliverable | Depends on |
|------|------------|------------|
| 1 | Service dataclasses (`RoaAuthorityMapFilters`, `RoaAuthorityMapRow`, `RoaAuthorityMapResult`) | — |
| 2 | Service functions (authority selection, reconciliation join, classification, overlap, projections) | Step 1 |
| 3 | Service unit tests | Steps 1-2 |
| 4 | Filter form (`IntentAuthorityMapFilterForm`) | — |
| 5 | Table class (`RoaAuthorityMapTable`) | Step 1 |
| 6 | View (`IntentAuthorityMapView`) | Steps 2, 4, 5 |
| 7 | Template (`intent_authority_map.html`) | Step 6 |
| 8 | URL route | Step 6 |
| 9 | Navigation wiring | Step 8 |
| 10 | URL and navigation tests | Steps 8-9 |
| 11 | View integration tests | Steps 6-9 |

Steps 1-3 can be built and tested before any UI work. Steps 4-5 have no dependency on the service layer and can be built in parallel with step 3. Steps 6-9 are sequential. Steps 10-11 run after the full stack is wired.

## Follow-On Work

After this page ships:

1. **Drift Workbench**: Reuse `build_roa_authority_map()` to get the base rows, then group by drift action category using the operator-action mapping from the UX recommendations. Separate view, table, and template; shared service substrate.
2. **Inline actions**: Add "Run Reconciliation" and "View Profile" buttons to the authority table. POST-only, CSRF-protected, permission-checked.
3. **CSV/JSON export**: Follow the operations dashboard export pattern. Add an export view at `intent/authority/export/`.
4. **Authority Change Review**: Diff service comparing consecutive derivation runs per profile. Separate implementation using the authority selection service from this page.
5. **Execution Coverage**: Pipeline stage aggregation service. Builds on the reconciliation join and change plan lookup from this page.
6. **ASPA parity**: After ASPA provenance migration, extend the authority map with an ASPA mode or a unified tabbed view.