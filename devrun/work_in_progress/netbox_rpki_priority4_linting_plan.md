# Priority 4: ROA Linting and Safety Analysis — Implementation Plan

**Created:** April 14, 2026  
**Status:** Implementation complete pending full plugin suite verification  
**Depends on:** Provider sync substrate (Priority 2 slices 1–4 complete)

---

## 1. Purpose

This document is the implementation runbook for the Priority 4 linting and safety analysis work.
It is derived from a review of `roa_lint.py`, `models.py`, `views.py`, `forms.py`,
`provider_write.py`, and `detail_specs.py` as they stand on April 14, 2026.

It assumes the developer will read this document before writing code and follow it in
slice order. Each slice is independently verifiable; no slice requires the next to pass
the plugin suite.

Related architectural decisions recorded here were made on April 14, 2026:

| ID | Decision |
|----|----------|
| AD-1 | Add a fourth `ownership_context` rule family. Rules in this family cross-join against IPAM/ASN data. They run in the same `run_roa_lint()` call and produce `ROALintFinding` rows with `rule_family = 'ownership_context'`. |
| AD-2 | When a plan is re-linted and a prior `ROALintAcknowledgement` exists for the same `finding_code + fact_fingerprint` on this plan (from an older lint run), show it as `previously_acknowledged` — a distinct posture state that still requires one-click re-confirmation before approval. |
| AD-3 | Add `ORG` and `PREFIX` scopes to `ROALintSuppressionScope`. ORG-wide suppressions suppress a `finding_code` across the entire organization regardless of intent or profile. PREFIX-scoped suppressions suppress a `finding_code` for a specific prefix CIDR across the org. `fact_fingerprint` is not required for ORG or PREFIX scopes. |
| AD-4 | Add a `ROALintRuleConfig` model per org. Each row overrides the default `severity` or `approval_impact` for one `finding_code` within that org. Global `LINT_RULE_SPECS` in `roa_lint.py` remain the authoritative defaults; the org config only applies overrides. |
| AD-5 | The standalone bulk-acknowledge action (`roachangeplan_acknowledge_lint` URL + `ROAChangePlanAcknowledgeView`) already exists and is wired in `detail_specs.py`. The remaining AD-5 work is enriching it to show the `previously_acknowledged` state described in AD-2 and to confirm the action button is visible on the plan detail page regardless of approval status. |

---

## 2. Current State (read before writing any code)

These objects already exist and are complete. Do not recreate or substantially restructure them:

| Object | File | Notes |
|--------|------|-------|
| `ROALintRun` | `models.py` | Links to `ROAReconciliationRun` + optional `ROAChangePlan`; holds severity counts and `summary_json`. |
| `ROALintFinding` | `models.py` | Links to run + optional `ROAIntentResult`, `PublishedROAResult`, or `ROAChangePlanItem`. Stores `finding_code`, `severity`, `details_json` (includes `rule_family`, `approval_impact`, `fact_fingerprint`, suppression fields). |
| `ROALintAcknowledgement` | `models.py` | Unique on `(change_plan, finding)`. Stores actor, timestamps, ticket/change refs, notes. Clean enforces finding→lint_run→change_plan chain. |
| `ROALintSuppression` | `models.py` | Currently scoped to `INTENT` or `PROFILE`. Stores `fact_fingerprint`, `fact_context_json`; has lift/expiry lifecycle. |
| `ROALintSuppressionScope` | `models.py` (line 377) | Currently `INTENT` and `PROFILE`. |
| `LINT_RULE_SPECS` | `roa_lint.py` | 18 rules across `intent_safety`, `published_hygiene`, `plan_risk`. |
| `run_roa_lint()` | `roa_lint.py` (line 1074) | Entry point. Creates run, iterates intent/published/plan findings, saves summary. |
| `build_roa_change_plan_lint_posture()` | `roa_lint.py` (line ~450) | Computes posture dict. Returns `status`, `can_approve`, per-impact counts. |
| `suppress_roa_lint_finding()` | `roa_lint.py` (line ~1000) | Creates `ROALintSuppression` from a finding. |
| `acknowledge_roa_lint_findings()` | `provider_write.py` (line 359) | Standalone acknowledgement outside approval. |
| `approve_roa_change_plan()` | `provider_write.py` (line 389) | Calls `build_roa_change_plan_lint_posture()` to gate approval. |
| `ROAChangePlanAcknowledgeView` | `views.py` (line ~1357) | Wired at `roachangeplan_acknowledge_lint`. Action button already in `detail_specs.py` (line 943). |
| `ROAChangePlanApproveView` | `views.py` (line ~1298) | Uses `ROAChangePlanApprovalForm` which already collects `acknowledged_findings`. |

---

## 3. Slice Ordering

```
Slice A  →  Slice B  →  Slice C  →  Slice D
  │         (concurrent with A)    (concurrent with B+C after A lands)
  ↓
Slice D (AD-2 carry-forward) can start after A because it only touches
roa_lint.py and forms.py; no new models needed.
```

Recommended order:

1. **Slice A** — `ROALintRuleConfig` model (AD-4). It has no dependencies and simplifies everything that follows because new rules can reference it from day one.
2. **Slice B** — ORG and PREFIX suppression scopes (AD-3). Migration only; no rule logic depends on it but the new ownership rules should be suppressible at ORG scope.
3. **Slice C** — `ownership_context` rule family (AD-1). Depends on Slice A (per-org config) and benefits from Slice B (ORG suppression).
4. **Slice D** — Acknowledgement carry-forward and previously-acknowledged posture state (AD-2 + AD-5 enrichment).

Each slice ends with a focused verification command. Do not proceed to the next slice until the command is green.

---

## 4. Slice A — `ROALintRuleConfig` Per-Org Rule Overrides

### 4.1 Goal

Allow an organization to override the default `severity` and/or `approval_impact` for any
`finding_code` defined in `LINT_RULE_SPECS`. The override applies to all lint runs created
for reconciliation runs belonging to that organization.

### 4.2 Model

Add to `models.py` after `ROALintSuppression`:

```python
class ROALintRuleConfig(NamedRpkiStandardModel):
    """Per-organization override for a lint rule's severity or approval impact."""
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_lint_rule_configs',
    )
    finding_code = models.CharField(
        max_length=64,
        help_text='The lint rule code from LINT_RULE_SPECS this override applies to.',
    )
    severity_override = models.CharField(
        max_length=16,
        choices=ReconciliationSeverity.choices,
        blank=True,
        help_text='Leave blank to use the rule default.',
    )
    approval_impact_override = models.CharField(
        max_length=64,
        blank=True,
        help_text=(
            'One of: informational, acknowledgement_required, blocking. '
            'Leave blank to use the rule default.'
        ),
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)
        constraints = (
            models.UniqueConstraint(
                fields=('organization', 'finding_code'),
                name='netbox_rpki_roalintruleconfig_org_code_unique',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_rpki:roalintruleconfig', args=[self.pk])

    def clean(self):
        super().clean()
        from netbox_rpki.services.roa_lint import LINT_RULE_SPECS
        valid_codes = set(LINT_RULE_SPECS.keys())
        if self.finding_code and self.finding_code not in valid_codes:
            raise ValidationError({'finding_code': f'Unknown finding code. Valid codes: {sorted(valid_codes)}'})
        valid_approval_impacts = {'', 'informational', 'acknowledgement_required', 'blocking'}
        if self.approval_impact_override not in valid_approval_impacts:
            raise ValidationError({'approval_impact_override': f'Must be one of: {valid_approval_impacts - {""}}.'})
```

**Important:** Import `LINT_RULE_SPECS` inside `clean()` to avoid a circular import.
`models.py` is imported by `roa_lint.py`; importing `roa_lint` at module level in `models.py`
would create a circular dependency.

### 4.3 Registry Entry

Add to `object_registry.py` in the appropriate section (after `ROALintSuppression`):

```python
ObjectSpec(
    registry_key="roalintruleconfig",
    model=models.ROALintRuleConfig,
    class_prefix="ROALintRuleConfig",
    verbose_name="ROA Lint Rule Config",
    verbose_name_plural="ROA Lint Rule Configs",
    navigation_group="Linting",
    api=ApiSpec(read_write=True),
    view=ViewSpec(can_add=True, can_edit=True, can_delete=True),
)
```

### 4.4 Service Layer Change

In `roa_lint.py`, add a helper to load org-level overrides for a lint run's organization,
then apply them inside `_create_finding()`.

```python
def _load_org_rule_overrides(organization_id: int) -> dict[str, dict]:
    """Returns {finding_code: {'severity': ..., 'approval_impact': ...}} for active org overrides."""
    result = {}
    from netbox_rpki.models import ROALintRuleConfig
    for config in ROALintRuleConfig.objects.filter(organization_id=organization_id):
        overrides = {}
        if config.severity_override:
            overrides['severity'] = config.severity_override
        if config.approval_impact_override:
            overrides['approval_impact'] = config.approval_impact_override
        if overrides:
            result[config.finding_code] = overrides
    return result
```

In `run_roa_lint()`, call once at the start:

```python
org_overrides = _load_org_rule_overrides(reconciliation_run.organization_id)
```

Pass `org_overrides` through to `_create_finding()` (add as a keyword argument).

In `_create_finding()`, after resolving `rule_spec`, apply overrides:

```python
effective_severity = org_overrides.get(finding_code, {}).get('severity') or severity or rule_spec.default_severity
effective_approval_impact = org_overrides.get(finding_code, {}).get('approval_impact') or rule_spec.approval_impact
```

Use `effective_severity` instead of `severity or rule_spec.default_severity` when writing the finding.
Use `effective_approval_impact` instead of `rule_spec.approval_impact` when writing `details_json['approval_impact']`.

The `LINT_RULE_SPECS` dict is not modified. The org override is baked into each persisted
`ROALintFinding.details_json` at creation time, so historical findings are stable even
if the config changes later.

### 4.5 Migration

```
python manage.py makemigrations netbox_rpki --name add_roa_lint_rule_config
```

Verify: `netbox_rpki_roalintruleconfig` table created, unique constraint present.

### 4.6 Detail Spec

Add a `ROA_LINT_RULE_CONFIG_DETAIL_SPEC` entry in `detail_specs.py`. Include a related-objects
section on the `Organization` detail spec linking to its `roa_lint_rule_configs` if the project
pattern supports it (check other `Organization`-linked tables for the insertion point).

### 4.7 Tests

In `netbox_rpki/tests/test_roa_lint.py` (or equivalent):

- `test_org_override_severity`: create a `ROALintRuleConfig` overriding severity for
  `intent_max_length_overbroad` to `critical`, run lint, assert finding has `severity='critical'`.
- `test_org_override_approval_impact`: override `plan_broadens_authorization` to `blocking`,
  run lint, assert posture status becomes `blocked`.
- `test_org_override_not_applied_to_other_org`: override in org A, run lint for org B, assert
  no override applied.
- `test_org_override_unknown_code_raises`: `ROALintRuleConfig.clean()` raises for unknown code.

### 4.8 Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput \
  netbox_rpki.tests.test_roa_lint \
  netbox_rpki.tests.test_provider_write \
  netbox_rpki.tests.test_models
```

---

## 5. Slice B — ORG-wide and PREFIX-scoped Suppression Scopes

### 5.1 Goal

Allow suppressions that do not require a `fact_fingerprint` match:

- `ORG` scope: suppresses `finding_code` for all findings across the entire organization,
  regardless of which intent or profile they come from.
- `PREFIX` scope: suppresses `finding_code` for all findings where the finding's
  `details_json` contains a matching prefix CIDR value (stored as a plain text field
  in the suppression row).

### 5.2 Model Changes

**`ROALintSuppressionScope`** — add two new choices:

```python
class ROALintSuppressionScope(models.TextChoices):
    INTENT = "intent", "Intent"
    PROFILE = "profile", "Profile"
    ORG = "org", "Organization"
    PREFIX = "prefix", "Prefix"
```

**`ROALintSuppression`** — add one optional field:

```python
prefix_cidr_text = models.CharField(
    max_length=50,
    blank=True,
    help_text='Required for prefix-scoped suppressions. CIDR notation, e.g. 192.0.2.0/24.',
)
```

Do not add a FK to the NetBox IPAM Prefix model. The prefix is stored as text to stay
consistent with how prefixes appear in finding `details_json`, and to avoid a dependency
on IPAM records that may not exist for all operators.

**Constraint changes in `ROALintSuppression.Meta`:**

Replace the existing `exact_scope_target` CheckConstraint with:

```python
models.CheckConstraint(
    condition=(
        models.Q(scope_type=ROALintSuppressionScope.INTENT, roa_intent__isnull=False, intent_profile__isnull=True, prefix_cidr_text='')
        | models.Q(scope_type=ROALintSuppressionScope.PROFILE, roa_intent__isnull=True, intent_profile__isnull=False, prefix_cidr_text='')
        | models.Q(scope_type=ROALintSuppressionScope.ORG, roa_intent__isnull=True, intent_profile__isnull=True, prefix_cidr_text='')
        | models.Q(scope_type=ROALintSuppressionScope.PREFIX, roa_intent__isnull=True, intent_profile__isnull=True, prefix_cidr_text__gt='')
    ),
    name='netbox_rpki_roalintsuppression_exact_scope_target',
)
```

Add UniqueConstraints for the new scopes:

```python
models.UniqueConstraint(
    fields=('finding_code', 'organization'),
    condition=models.Q(scope_type=ROALintSuppressionScope.ORG, lifted_at__isnull=True),
    name='netbox_rpki_roalintsuppression_active_org_unique',
),
models.UniqueConstraint(
    fields=('finding_code', 'organization', 'prefix_cidr_text'),
    condition=models.Q(scope_type=ROALintSuppressionScope.PREFIX, lifted_at__isnull=True),
    name='netbox_rpki_roalintsuppression_active_prefix_unique',
),
```

**`ROALintSuppression.clean()`** — add branches:

```python
if self.scope_type == ROALintSuppressionScope.ORG:
    if self.roa_intent_id is not None:
        errors['roa_intent'] = 'Must be empty for org-scoped suppressions.'
    if self.intent_profile_id is not None:
        errors['intent_profile'] = 'Must be empty for org-scoped suppressions.'
    if self.prefix_cidr_text:
        errors['prefix_cidr_text'] = 'Must be empty for org-scoped suppressions.'

if self.scope_type == ROALintSuppressionScope.PREFIX:
    if self.roa_intent_id is not None:
        errors['roa_intent'] = 'Must be empty for prefix-scoped suppressions.'
    if self.intent_profile_id is not None:
        errors['intent_profile'] = 'Must be empty for prefix-scoped suppressions.'
    if not self.prefix_cidr_text:
        errors['prefix_cidr_text'] = 'Prefix CIDR is required for prefix-scoped suppressions.'
    else:
        try:
            ip_network(self.prefix_cidr_text, strict=False)
        except ValueError:
            errors['prefix_cidr_text'] = 'Enter a valid CIDR prefix, e.g. 192.0.2.0/24.'
```

Also remove the `fact_fingerprint` required validation for ORG and PREFIX scopes:

```python
# Existing check:
if not self.fact_fingerprint:
    errors['fact_fingerprint'] = 'A suppression must record the finding facts it applies to.'
# Change to:
if self.scope_type in (ROALintSuppressionScope.INTENT, ROALintSuppressionScope.PROFILE):
    if not self.fact_fingerprint:
        errors['fact_fingerprint'] = 'A suppression must record the finding facts it applies to.'
```

### 5.3 Service Layer Changes in `roa_lint.py`

**`_active_suppression_queryset()`** — no change needed; ORG and PREFIX rows pass through.

**`_matching_suppression()`** — extend with new scope lookups after the existing PROFILE check:

```python
# After the existing PROFILE check:

# ORG-wide suppression (no fingerprint required)
org_suppression = queryset.filter(
    scope_type=rpki_models.ROALintSuppressionScope.ORG,
    organization=lint_run.reconciliation_run.organization,
    fact_fingerprint='',
).first()
if org_suppression is not None:
    return org_suppression

# PREFIX-scoped suppression
# Extract prefix from finding context; try common detail_json keys
prefix_candidates = {
    details_json.get('intent_prefix'),
    details_json.get('prefix_cidr_text'),
    details_json.get('published_prefix'),
}
prefix_candidates.discard(None)
if prefix_candidates:
    prefix_suppression = queryset.filter(
        scope_type=rpki_models.ROALintSuppressionScope.PREFIX,
        organization=lint_run.reconciliation_run.organization,
        fact_fingerprint='',
        prefix_cidr_text__in=prefix_candidates,
    ).first()
    if prefix_suppression is not None:
        return prefix_suppression

return None
```

**`suppress_roa_lint_finding()`** — add handling for new scope types:

```python
if scope_type == rpki_models.ROALintSuppressionScope.ORG:
    payload['name'] = f'{finding.finding_code} org suppression for {organization.name}'
    payload['fact_fingerprint'] = ''
    payload['fact_context_json'] = {}
    suppression = rpki_models.ROALintSuppression.objects.filter(
        finding_code=finding.finding_code,
        scope_type=scope_type,
        organization=organization,
        lifted_at__isnull=True,
    ).first()
    if suppression is not None:
        return suppression
    suppression = rpki_models.ROALintSuppression(**payload)
    suppression.full_clean(validate_unique=False)
    suppression.save()
    return suppression

if scope_type == rpki_models.ROALintSuppressionScope.PREFIX:
    prefix_cidr_text = (
        finding.details_json.get('intent_prefix')
        or finding.details_json.get('prefix_cidr_text')
        or finding.details_json.get('published_prefix')
    )
    if not prefix_cidr_text:
        raise ValueError('PREFIX-scoped suppressions require a finding with a resolvable prefix field.')
    payload['prefix_cidr_text'] = prefix_cidr_text
    payload['name'] = f'{finding.finding_code} prefix suppression for {prefix_cidr_text}'
    payload['fact_fingerprint'] = ''
    payload['fact_context_json'] = {}
    suppression = rpki_models.ROALintSuppression.objects.filter(
        finding_code=finding.finding_code,
        scope_type=scope_type,
        organization=organization,
        prefix_cidr_text=prefix_cidr_text,
        lifted_at__isnull=True,
    ).first()
    if suppression is not None:
        return suppression
    suppression = rpki_models.ROALintSuppression(**payload)
    suppression.full_clean(validate_unique=False)
    suppression.save()
    return suppression
```

**Suppress view form** — the `ROALintFindingSuppressView` form should expose the new scope
choices. Check `forms.py` for the scope field definition and add `ORG` and `PREFIX` to its
choices if they are not derived from the model automatically.

### 5.4 Migration

```
python manage.py makemigrations netbox_rpki --name add_lint_suppression_org_prefix_scopes
```

This migration adds `prefix_cidr_text` and alters the constraint definitions. The existing
`INTENT` and `PROFILE` rows are unaffected.

### 5.5 Tests

- `test_org_scope_suppresses_all_findings_for_code`: create ORG-scoped suppression for
  `intent_max_length_overbroad`, run lint with two overbroad intent findings, assert both
  are suppressed.
- `test_org_scope_does_not_suppress_other_codes`: ORG suppression for code A does not
  suppress code B findings.
- `test_prefix_scope_suppresses_matching_prefix_only`: PREFIX suppression for
  `192.0.2.0/24` suppresses a finding with `intent_prefix='192.0.2.0/24'` but not one
  with `intent_prefix='10.0.0.0/8'`.
- `test_suppress_finding_creates_org_suppression`: call `suppress_roa_lint_finding()` with
  `scope_type=ORG`, verify the created suppression has `fact_fingerprint=''`.
- `test_suppress_finding_creates_prefix_suppression`: same for PREFIX scope.
- `test_suppress_finding_prefix_scope_raises_without_prefix_field`: verify `ValueError`
  if the finding has no resolvable prefix in `details_json`.
- `test_suppression_clean_org_rejects_linked_intent`: verify constraint enforcement.

### 5.6 Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput \
  netbox_rpki.tests.test_roa_lint \
  netbox_rpki.tests.test_models
```

---

## 6. Slice C — `ownership_context` Rule Family

### 6.1 Goal

Add four new rules that cross-join ROA intent and published ROA data against IPAM/ASN
ownership records to flag authorization that may reach beyond an organization's resource
space. These rules default to `informational` impact and can be escalated per-org via
`ROALintRuleConfig` (Slice A). They can be silenced org-wide or prefix-wide via the
ORG/PREFIX suppression scopes (Slice B).

### 6.2 New Rule Family Constant

In `roa_lint.py`:

```python
LINT_RULE_FAMILY_OWNERSHIP_CONTEXT = 'ownership_context'
```

### 6.3 New Rules

Add to `LINT_RULE_SPECS`:

```python
LINT_RULE_INTENT_ASN_NOT_IN_ORG = 'intent_origin_asn_not_in_org'
LINT_RULE_INTENT_PREFIX_NOT_IN_ORG = 'intent_prefix_no_ipam_match'
LINT_RULE_PUBLISHED_CROSS_ORG_ORIGIN = 'published_cross_org_origin_asn'
LINT_RULE_PLAN_CROSS_ORG_AUTHORIZATION = 'plan_creates_cross_org_authorization'
```

```python
LINT_RULE_INTENT_ASN_NOT_IN_ORG: LintRuleSpec(
    label='Intent origin ASN not in organization',
    family=LINT_RULE_FAMILY_OWNERSHIP_CONTEXT,
    default_severity=rpki_models.ReconciliationSeverity.WARNING,
    approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
),
LINT_RULE_INTENT_PREFIX_NOT_IN_ORG: LintRuleSpec(
    label='Intent prefix has no IPAM match in organization',
    family=LINT_RULE_FAMILY_OWNERSHIP_CONTEXT,
    default_severity=rpki_models.ReconciliationSeverity.WARNING,
    approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
),
LINT_RULE_PUBLISHED_CROSS_ORG_ORIGIN: LintRuleSpec(
    label='Published ROA uses origin ASN from different organization',
    family=LINT_RULE_FAMILY_OWNERSHIP_CONTEXT,
    default_severity=rpki_models.ReconciliationSeverity.WARNING,
    approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
),
LINT_RULE_PLAN_CROSS_ORG_AUTHORIZATION: LintRuleSpec(
    label='Plan creates cross-organization authorization',
    family=LINT_RULE_FAMILY_OWNERSHIP_CONTEXT,
    default_severity=rpki_models.ReconciliationSeverity.WARNING,
    approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
),
```

Add explanations for all four in `_finding_explanation()`:

```python
LINT_RULE_INTENT_ASN_NOT_IN_ORG: (
    'The intended origin ASN is not associated with the organization that owns this intent.',
    'Authorization from an unowned ASN may indicate a misconfigured intent or a cross-org policy error.',
    'Confirm the origin ASN belongs to this organization or suppress this finding if cross-org authorization is intentional.',
),
LINT_RULE_INTENT_PREFIX_NOT_IN_ORG: (
    'No IPAM prefix record in this organization matches the intended prefix.',
    'Authorizing a prefix with no IPAM record prevents cross-verification of resource ownership.',
    'Add the prefix to IPAM or suppress this finding if IPAM data is intentionally incomplete.',
),
LINT_RULE_PUBLISHED_CROSS_ORG_ORIGIN: (
    'The published ROA uses an origin ASN that belongs to a different organization.',
    'Cross-org origin authorization may be intentional for transit policy but is unusual and worth review.',
    'Confirm this is intentional and suppress at ORG scope if this pattern is expected for this organization.',
),
LINT_RULE_PLAN_CROSS_ORG_AUTHORIZATION: (
    'The change plan would create a ROA whose origin ASN and prefix appear to belong to different organizations.',
    'Cross-org authorization in a plan action requires explicit review before provider submission.',
    'Confirm the authorization is intentional before approval.',
),
```

### 6.4 IPAM Ownership Lookups

Add a helper that loads ownership context for a lint run's organization. Call it once
in `run_roa_lint()` before the finding loops and pass it to the new `_ownership_lint_findings()`
function.

```python
def _build_org_ownership_context(organization: rpki_models.Organization) -> dict:
    """
    Returns a dict with org-level ASN and prefix ownership data:
    {
        'asn_values': set of int ASN values assigned to the org,
        'prefix_cidrs': set of str CIDR strings assigned to the org,
    }
    Pulls from ROAIntent/ASPA ASN references and from IPAM prefix records
    linked to the organization's tenant where available.
    """
    from netbox_rpki.models import ROAIntent, Asn
    from ipam.models import Prefix as IpamPrefix  # NetBox core IPAM

    asn_values: set[int] = set()
    prefix_cidrs: set[str] = set()

    # Org ASNs: derive from all ROAIntent objects for this org
    # (authoritative ownership data; does not require separate IPAM ASN objects)
    for intent in ROAIntent.objects.filter(organization=organization).select_related('origin_asn'):
        if intent.origin_asn_id is not None and hasattr(intent.origin_asn, 'asn'):
            asn_values.add(intent.origin_asn.asn)

    # IPAM prefix records: check NetBox core; may not exist in all deployments
    try:
        tenant = organization.tenant if hasattr(organization, 'tenant') else None
        if tenant is not None:
            for pfx in IpamPrefix.objects.filter(tenant=tenant).values_list('prefix', flat=True):
                prefix_cidrs.add(str(pfx))
    except Exception:
        # IPAM data is optional; ownership rules fall back to informational-only if unavailable
        pass

    return {'asn_values': asn_values, 'prefix_cidrs': prefix_cidrs}
```

**Important:** Do not raise exceptions from this helper if IPAM data is missing or the
`Prefix` model is not importable. Ownership rules should degrade silently to
zero findings if IPAM data is absent, rather than crashing a lint run.

### 6.5 New Finding Function

```python
def _ownership_lint_findings(
    lint_run: rpki_models.ROALintRun,
    *,
    intent_results: list[rpki_models.ROAIntentResult],
    published_results: list[rpki_models.PublishedROAResult],
    plan: rpki_models.ROAChangePlan | None,
    ownership_context: dict,
    org_overrides: dict,
) -> list[rpki_models.ROALintFinding]:
    findings: list[rpki_models.ROALintFinding] = []
    asn_values = ownership_context.get('asn_values', set())
    prefix_cidrs = ownership_context.get('prefix_cidrs', set())

    # Intent: origin ASN not in org
    if asn_values:
        for intent_result in intent_results:
            intent = intent_result.roa_intent
            asn_val = getattr(getattr(intent, 'origin_asn', None), 'asn', None)
            if asn_val is not None and asn_val not in asn_values:
                findings.append(_create_finding(
                    lint_run,
                    finding_code=LINT_RULE_INTENT_ASN_NOT_IN_ORG,
                    roa_intent_result=intent_result,
                    details_json={
                        'intent_prefix': intent_result.details_json.get('intent_prefix'),
                        'intent_origin_asn': asn_val,
                        'org_asn_count': len(asn_values),
                    },
                    org_overrides=org_overrides,
                ))

    # Intent: prefix not in IPAM
    if prefix_cidrs:
        for intent_result in intent_results:
            intent = intent_result.roa_intent
            intent_prefix = intent_result.details_json.get('intent_prefix')
            if intent_prefix and intent_prefix not in prefix_cidrs:
                findings.append(_create_finding(
                    lint_run,
                    finding_code=LINT_RULE_INTENT_PREFIX_NOT_IN_ORG,
                    roa_intent_result=intent_result,
                    details_json={
                        'intent_prefix': intent_prefix,
                        'ipam_prefix_count': len(prefix_cidrs),
                    },
                    org_overrides=org_overrides,
                ))

    # Published: cross-org origin ASN
    if asn_values:
        for pub_result in published_results:
            details = pub_result.details_json or {}
            origin_asn = details.get('origin_asn')
            if origin_asn is not None and origin_asn not in asn_values:
                findings.append(_create_finding(
                    lint_run,
                    finding_code=LINT_RULE_PUBLISHED_CROSS_ORG_ORIGIN,
                    published_roa_result=pub_result,
                    details_json={
                        'prefix_cidr_text': details.get('prefix_cidr_text'),
                        'origin_asn': origin_asn,
                        'org_asn_count': len(asn_values),
                    },
                    org_overrides=org_overrides,
                ))

    # Plan: creates cross-org authorization
    if plan is not None and asn_values:
        for item in plan.items.filter(action_type=rpki_models.ROAChangePlanAction.CREATE):
            prefix_cidr_text, max_length = _plan_item_prefix_and_max_length(item)
            _, origin_asn_value = _plan_item_prefix_asn_key(item)
            if origin_asn_value is not None and origin_asn_value not in asn_values:
                findings.append(_create_finding(
                    lint_run,
                    finding_code=LINT_RULE_PLAN_CROSS_ORG_AUTHORIZATION,
                    change_plan_item=item,
                    details_json={
                        'prefix_cidr_text': prefix_cidr_text,
                        'origin_asn_value': origin_asn_value,
                        'org_asn_count': len(asn_values),
                    },
                    org_overrides=org_overrides,
                ))

    return findings
```

### 6.6 Wire into `run_roa_lint()`

After the existing per-family finding loops, add:

```python
ownership_context = _build_org_ownership_context(reconciliation_run.organization)
all_findings.extend(
    _ownership_lint_findings(
        lint_run,
        intent_results=list(reconciliation_run.intent_results.select_related('roa_intent__origin_asn').all()),
        published_results=list(reconciliation_run.published_roa_results.all()),
        plan=change_plan,
        ownership_context=ownership_context,
        org_overrides=org_overrides,
    )
)
```

The `intent_results` list is already iterated above; re-fetch with `select_related` for the
ASN join rather than re-using the earlier queryset which may not have `origin_asn` prefetched.

### 6.7 Handling Missing IPAM Data

If `asn_values` is empty, the `intent_origin_asn_not_in_org` and related rules produce
zero findings. This is the correct behavior when an operator has not associated ASNs in
NetBox — no false positives. Document this clearly in the `_build_org_ownership_context()`
docstring and in the operator-facing `why_it_matters` text for each rule.

### 6.8 Tests

- `test_intent_asn_not_in_org_creates_finding`: mock ownership context with known ASN set,
  create intent with different ASN, check finding created.
- `test_intent_asn_in_org_no_finding`: intent ASN is in the org set, no finding.
- `test_no_asn_data_no_findings`: empty `asn_values`, zero ownership findings regardless of intent.
- `test_prefix_not_in_ipam_creates_finding`: mock prefix_cidrs, create intent with non-matching
  prefix CIDR, check finding.
- `test_ownership_findings_suppressible_org_scope`: create ORG-scoped suppression for
  `intent_origin_asn_not_in_org`, run lint, assert finding is suppressed.
- `test_org_override_escalates_ownership_finding`: `ROALintRuleConfig` sets
  `plan_creates_cross_org_authorization` to `acknowledgement_required`, assert posture
  reflects it.
- `test_plan_cross_org_authorization_finding`: plan has a CREATE item with foreign ASN.

### 6.9 Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput \
  netbox_rpki.tests.test_roa_lint \
  netbox_rpki.tests.test_provider_write \
  netbox_rpki.tests.test_api \
  netbox_rpki.tests.test_views
```

---

## 7. Slice D — Acknowledgement Carry-Forward and Previously-Acknowledged State

### 7.1 Goal

When a plan is re-linted (a new `ROALintRun` is created for the same `ROAChangePlan`),
prior `ROALintAcknowledgement` rows reference findings from the old lint run. The new
findings have no acknowledgements. Instead of requiring full re-acknowledgement from scratch,
detect "previously acknowledged" and surface it as a distinct, low-friction state that
requires only a one-click re-confirmation before approval gates pass.

### 7.2 No Model Changes Required

The `ROALintAcknowledgement` model already stores `finding_id` (a FK to a specific
`ROALintFinding` row) and `lint_run_id`. A "previously acknowledged" finding is one where:

1. The finding is `acknowledgement_required` and unsuppressed in the **current** lint run.
2. There exists a `ROALintAcknowledgement` on the same `change_plan` where the ack'd
   finding has the same `finding_code` and `details_json['fact_fingerprint']` but a
   different (older) `lint_run_id`.

This can be detected entirely in the service layer with an additional query.

### 7.3 `build_roa_change_plan_lint_posture()` Changes

Add a new bucket `previously_acknowledged_counts` alongside the existing impact-keyed dicts.
Extend the per-finding loop:

```python
# Load prior ack fingerprints BEFORE the finding loop:
current_lint_run_id = lint_run.pk
prior_ack_pairs = (
    rpki_models.ROALintAcknowledgement.objects
    .filter(change_plan=change_plan)
    .exclude(lint_run_id=current_lint_run_id)
    .select_related('finding')
    .values_list('finding__finding_code', 'finding__details_json')
)
# Build a set of (finding_code, fact_fingerprint) tuples seen in prior acks
prior_acked_pairs: set[tuple[str, str]] = set()
for code, details_json in prior_ack_pairs:
    fp = (details_json or {}).get('fact_fingerprint', '')
    if fp:
        prior_acked_pairs.add((code, fp))
```

In the per-finding loop, after the existing suppression check and before the
`acknowledgement_required` acknowledgement check:

```python
if (
    impact == LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED
    and finding.pk not in acknowledged_ids
):
    fp = finding.details_json.get('fact_fingerprint', '')
    if (finding.finding_code, fp) in prior_acked_pairs:
        # Previously acknowledged in an older lint run on this plan
        previously_acknowledged_count += 1
        previously_acknowledged_finding_ids.add(finding.pk)
        continue  # Not unresolved — needs re-confirm, but not fully blocking
```

Expose in the returned dict:

```python
'previously_acknowledged_finding_count': previously_acknowledged_count,
'previously_acknowledged_finding_ids': sorted(previously_acknowledged_finding_ids),
```

Change the `status` logic:

```python
if unresolved_blocking > 0:
    status = 'blocked'
elif unresolved_ack_required > 0:
    status = 'acknowledgement_required'
elif previously_acknowledged_count > 0:
    status = 'previously_acknowledged'
else:
    status = 'clear'
```

Update `can_approve`:

```python
'can_approve': unresolved_blocking == 0 and unresolved_ack_required == 0 and previously_acknowledged_count == 0,
```

### 7.4 `approve_roa_change_plan()` Gate Change

The approval check currently blocks on `unresolved_acknowledgement_required_finding_count > 0`.
Add a second gate:

```python
if posture['previously_acknowledged_finding_count'] > 0:
    raise ProviderWriteError(
        'This plan has previously acknowledged findings that must be re-confirmed before approval.'
    )
```

### 7.5 `acknowledge_roa_lint_findings()` — No Core Change

The function already creates `ROALintAcknowledgement` rows for specified finding PKs.
When `previously_acknowledged_finding_ids` is passed in as the set to acknowledge,
it creates fresh acks for the current lint run's findings. No changes to the function
signature are required.

### 7.6 Form Changes

**`ROAChangePlanApprovalForm`** — separate `acknowledged_findings` queryset into two groups:
truly new `acknowledgement_required` findings and `previously_acknowledged` ones.
Show previously-acked findings in a separate fieldset with label
"Re-confirm Previously Acknowledged Findings":

```python
previously_acknowledged_findings = forms.ModelMultipleChoiceField(
    queryset=netbox_rpki.models.ROALintFinding.objects.none(),
    required=False,
    label='Re-confirm Previously Acknowledged Findings',
    widget=forms.CheckboxSelectMultiple,
    help_text=(
        'These findings were acknowledged in a prior lint run on this plan. '
        'Confirm they are still acceptable before approval.'
    ),
)
```

In `__init__`, after building the existing `acknowledged_findings` queryset, also
query `build_roa_change_plan_lint_posture()` for `previously_acknowledged_finding_ids`
and populate this second field.

In `clean()`, include `previously_acknowledged_findings` PKs when computing the full
acknowledged set passed to `approve_roa_change_plan()`.

**`ROAChangePlanLintAcknowledgementForm`** (standalone bulk-acknowledge form) — same
separation. Add the `previously_acknowledged_findings` field so the standalone
`roachangeplan_acknowledge_lint` action also surfaces the re-confirm path without
requiring operators to go through the full approval form.

### 7.7 View Changes

**`ROAChangePlanAcknowledgeView.post()`** — combine `acknowledged_findings` and
`previously_acknowledged_findings` PKs into a single list passed to
`acknowledge_roa_lint_findings()`.

**`ROAChangePlanApproveView.post()`** — same merge of both queryset PKs.

**`ROAChangePlanAcknowledgeView` visibility** — the action button registered in
`detail_specs.py` at line 943 should be visible regardless of plan status (draft, approved).
Confirm the permission check in the view matches `netbox_rpki.change_roachangeplan` and
that no status gate prevents access when the plan has `previously_acknowledged` posture.

### 7.8 Template Change

Both `roachangeplan_acknowledge.html` and `roachangeplan_confirm.html` need a section
for the `previously_acknowledged_findings` field if it has entries. Use a distinct
visual treatment (e.g. "Re-confirm" label, neutral color) to distinguish it from
the "New acknowledgement required" section.

### 7.9 API Change

The REST API `ROAChangePlanApproveSerializer` (or equivalent in `api/views.py`) accepts
`acknowledged_finding_ids`. Add `previously_acknowledged_finding_ids` as a separate optional
list field. In the API view handler, combine both lists before calling
`approve_roa_change_plan()`.

### 7.10 Tests

- `test_prior_ack_same_fingerprint_shows_previously_acknowledged`: create a plan, lint it,
  ack a finding, re-lint (new finding rows, same fingerprints), call
  `build_roa_change_plan_lint_posture()`, assert `previously_acknowledged_finding_count == 1`
  and `status == 'previously_acknowledged'`.
- `test_prior_ack_different_fingerprint_is_unresolved`: re-lint produces a finding with a
  different fingerprint (different prefix/asn), assert it shows as unresolved, not prior-acked.
- `test_approve_blocked_on_previously_acknowledged`: assert `ProviderWriteError` raised
  if `previously_acknowledged_finding_count > 0` without re-confirmation.
- `test_approve_passes_after_reconfirmation`: pass `previously_acknowledged_finding_ids`
  to `approve_roa_change_plan()`, assert approval succeeds.
- `test_acknowledge_view_post_reconfirms_prior_ack`: POST to `roachangeplan_acknowledge_lint`
  with previously-acked PKs, assert new `ROALintAcknowledgement` created for current lint run.
- `test_posture_clear_after_reconfirmation`: after re-confirm acks, posture status is `clear`.

### 7.11 Verification

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput \
  netbox_rpki.tests.test_roa_lint \
  netbox_rpki.tests.test_provider_write \
  netbox_rpki.tests.test_views \
  netbox_rpki.tests.test_api
```

---

## 8. Full Suite Verification

After all slices are in place:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 /home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput netbox_rpki.tests
```

Or via devrun:

```bash
cd /home/mencken/src/netbox_rpki/devrun && ./dev.sh test full
```

---

## 9. Closure Criteria

Treat this Priority 4 work as closed when all of the following are true:

- [x] `ROALintRuleConfig` is migration-safe, CRUD-reachable, and tests cover per-org severity and approval_impact overrides.
- [x] `ROALintSuppression` accepts `ORG` and `PREFIX` scope types; `_matching_suppression()` checks them; tests confirm ORG suppresses all findings for a code, PREFIX only matches the target CIDR.
- [x] Four `ownership_context` rules emit findings when IPAM/ASN data is present and emit zero findings when data is absent; ownership findings are suppressible at ORG scope.
- [x] `build_roa_change_plan_lint_posture()` returns `previously_acknowledged_finding_count`, `previously_acknowledged_finding_ids`, and `status='previously_acknowledged'` when applicable.
- [x] Approval is gated on `previously_acknowledged_finding_count == 0`.
- [x] The approval form and standalone acknowledge form both present a "re-confirm" section for prior acks.
- [x] The `roachangeplan_acknowledge_lint` action button is visible on the plan detail page at any plan status.
- [ ] The full plugin test suite is green.
- [x] The `LINT_SUMMARY_SCHEMA_VERSION` constant is incremented if `summary_json` shape changes significantly across any slice (currently `3`; no bump required because the new fields were added to lint posture rather than lint-run `summary_json`).

---

## 10. Deferred (Not in This Scope)

- Lint rules for ASPA objects. The shared `roa_lint.py` contract is intentionally ROA-specific. An `aspa_lint.py` service should be added in the Priority 3 ASPA write-back work when the `ASPAChangePlan` approval contract is mature.
- `fact_fingerprint` versioning. The current fingerprint algorithm (SHA-256 of `finding_code` + normalized `details_json`) is stable. Do not change it in this work; any change invalidates all existing suppressions.
- UI rule-browser page showing all `LINT_RULE_SPECS` definitions in a human-readable form. Useful but not required for closure.
- Alerting hooks or threshold-based notification. Deferred to Priority 9.
