from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
from ipaddress import ip_network

from django.db.models import Q
from django.utils import timezone

from netbox_rpki import models as rpki_models


LINT_RULE_FAMILY_INTENT_SAFETY = 'intent_safety'
LINT_RULE_FAMILY_PUBLISHED_HYGIENE = 'published_hygiene'
LINT_RULE_FAMILY_PLAN_RISK = 'plan_risk'
LINT_RULE_FAMILY_OWNERSHIP_CONTEXT = 'ownership_context'

LINT_APPROVAL_IMPACT_INFORMATIONAL = 'informational'
LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED = 'acknowledgement_required'
LINT_APPROVAL_IMPACT_BLOCKING = 'blocking'

LINT_RULE_INTENT_OVERBROAD = 'intent_max_length_overbroad'
LINT_RULE_INTENT_INCONSISTENT = 'intent_inconsistent_with_published'
LINT_RULE_INTENT_STATE_CONFLICT = 'intent_state_conflict'
LINT_RULE_PUBLISHED_ORPHANED = 'published_orphaned'
LINT_RULE_PUBLISHED_STALE = 'published_stale'
LINT_RULE_PUBLISHED_DUPLICATE = 'published_duplicate'
LINT_RULE_PUBLISHED_BROADER_THAN_NEEDED = 'published_broader_than_needed'
LINT_RULE_PUBLISHED_INCONSISTENT = 'published_inconsistent_with_intent'
LINT_RULE_PUBLISHED_UNSCOPED = 'published_unscoped'
LINT_RULE_INTENT_STALE = 'intent_stale'
LINT_RULE_REPLACEMENT_REQUIRED = 'replacement_required'
LINT_RULE_INTENT_SUPPRESSED = 'intent_suppressed'
LINT_RULE_INTENT_INACTIVE = 'intent_inactive'
LINT_RULE_PLAN_REPLACE = 'plan_replace'
LINT_RULE_PLAN_RESHAPE = 'plan_reshape'
LINT_RULE_PLAN_BROADENS_AUTHORIZATION = 'plan_broadens_authorization'
LINT_RULE_PLAN_WITHDRAW_WITHOUT_REPLACEMENT = 'plan_withdraw_without_replacement'
LINT_RULE_INTENT_ASN_NOT_IN_ORG = 'intent_origin_asn_not_in_org'
LINT_RULE_INTENT_PREFIX_NOT_IN_ORG = 'intent_prefix_no_ipam_match'
LINT_RULE_PUBLISHED_CROSS_ORG_ORIGIN = 'published_cross_org_origin_asn'
LINT_RULE_PLAN_CROSS_ORG_AUTHORIZATION = 'plan_creates_cross_org_authorization'

LINT_SUMMARY_SCHEMA_VERSION = 3
LINT_POSTURE_SCHEMA_VERSION = 2
LINT_LIFECYCLE_SUMMARY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LintRuleSpec:
    label: str
    family: str
    default_severity: str
    approval_impact: str


LINT_RULE_SPECS = {
    LINT_RULE_INTENT_OVERBROAD: LintRuleSpec(
        label='Intent maxLength overbroad',
        family=LINT_RULE_FAMILY_INTENT_SAFETY,
        default_severity=rpki_models.ReconciliationSeverity.WARNING,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_INTENT_INCONSISTENT: LintRuleSpec(
        label='Intent inconsistent with published state',
        family=LINT_RULE_FAMILY_INTENT_SAFETY,
        default_severity=rpki_models.ReconciliationSeverity.ERROR,
        approval_impact=LINT_APPROVAL_IMPACT_BLOCKING,
    ),
    LINT_RULE_INTENT_STATE_CONFLICT: LintRuleSpec(
        label='Intent state conflicts with published state',
        family=LINT_RULE_FAMILY_INTENT_SAFETY,
        default_severity=rpki_models.ReconciliationSeverity.WARNING,
        approval_impact=LINT_APPROVAL_IMPACT_BLOCKING,
    ),
    LINT_RULE_PUBLISHED_ORPHANED: LintRuleSpec(
        label='Published ROA orphaned',
        family=LINT_RULE_FAMILY_PUBLISHED_HYGIENE,
        default_severity=rpki_models.ReconciliationSeverity.WARNING,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_PUBLISHED_STALE: LintRuleSpec(
        label='Published ROA stale',
        family=LINT_RULE_FAMILY_PUBLISHED_HYGIENE,
        default_severity=rpki_models.ReconciliationSeverity.INFO,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_PUBLISHED_DUPLICATE: LintRuleSpec(
        label='Published ROA duplicate',
        family=LINT_RULE_FAMILY_PUBLISHED_HYGIENE,
        default_severity=rpki_models.ReconciliationSeverity.WARNING,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_PUBLISHED_BROADER_THAN_NEEDED: LintRuleSpec(
        label='Published ROA broader than needed',
        family=LINT_RULE_FAMILY_PUBLISHED_HYGIENE,
        default_severity=rpki_models.ReconciliationSeverity.WARNING,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_PUBLISHED_INCONSISTENT: LintRuleSpec(
        label='Published ROA inconsistent with intent',
        family=LINT_RULE_FAMILY_PUBLISHED_HYGIENE,
        default_severity=rpki_models.ReconciliationSeverity.ERROR,
        approval_impact=LINT_APPROVAL_IMPACT_BLOCKING,
    ),
    LINT_RULE_PUBLISHED_UNSCOPED: LintRuleSpec(
        label='Published ROA outside comparison scope',
        family=LINT_RULE_FAMILY_PUBLISHED_HYGIENE,
        default_severity=rpki_models.ReconciliationSeverity.WARNING,
        approval_impact=LINT_APPROVAL_IMPACT_BLOCKING,
    ),
    LINT_RULE_INTENT_STALE: LintRuleSpec(
        label='Intent candidate stale',
        family=LINT_RULE_FAMILY_INTENT_SAFETY,
        default_severity=rpki_models.ReconciliationSeverity.INFO,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_REPLACEMENT_REQUIRED: LintRuleSpec(
        label='Replacement workflow required',
        family=LINT_RULE_FAMILY_PLAN_RISK,
        default_severity=rpki_models.ReconciliationSeverity.INFO,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_INTENT_SUPPRESSED: LintRuleSpec(
        label='Intent suppressed by policy',
        family=LINT_RULE_FAMILY_INTENT_SAFETY,
        default_severity=rpki_models.ReconciliationSeverity.INFO,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_INTENT_INACTIVE: LintRuleSpec(
        label='Intent inactive',
        family=LINT_RULE_FAMILY_INTENT_SAFETY,
        default_severity=rpki_models.ReconciliationSeverity.INFO,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_PLAN_REPLACE: LintRuleSpec(
        label='Plan replacement action',
        family=LINT_RULE_FAMILY_PLAN_RISK,
        default_severity=rpki_models.ReconciliationSeverity.INFO,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_PLAN_RESHAPE: LintRuleSpec(
        label='Plan reshape action',
        family=LINT_RULE_FAMILY_PLAN_RISK,
        default_severity=rpki_models.ReconciliationSeverity.INFO,
        approval_impact=LINT_APPROVAL_IMPACT_INFORMATIONAL,
    ),
    LINT_RULE_PLAN_BROADENS_AUTHORIZATION: LintRuleSpec(
        label='Plan broadens authorization',
        family=LINT_RULE_FAMILY_PLAN_RISK,
        default_severity=rpki_models.ReconciliationSeverity.WARNING,
        approval_impact=LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED,
    ),
    LINT_RULE_PLAN_WITHDRAW_WITHOUT_REPLACEMENT: LintRuleSpec(
        label='Plan withdraws without replacement',
        family=LINT_RULE_FAMILY_PLAN_RISK,
        default_severity=rpki_models.ReconciliationSeverity.ERROR,
        approval_impact=LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED,
    ),
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
}

INTENT_INCONSISTENT_RESULT_TYPES = {
    rpki_models.ROAIntentResultType.ASN_MISMATCH,
    rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_OVERBROAD,
    rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_TOO_NARROW,
    rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_MISMATCH,
    rpki_models.ROAIntentResultType.PREFIX_MISMATCH,
    rpki_models.ROAIntentResultType.MAX_LENGTH_TOO_NARROW,
}

PUBLISHED_INCONSISTENT_RESULT_TYPES = {
    rpki_models.PublishedROAResultType.MAX_LENGTH_TOO_NARROW,
    rpki_models.PublishedROAResultType.WRONG_ORIGIN,
    rpki_models.PublishedROAResultType.WRONG_ORIGIN_AND_MAX_LENGTH_OVERBROAD,
    rpki_models.PublishedROAResultType.WRONG_ORIGIN_AND_MAX_LENGTH_TOO_NARROW,
    rpki_models.PublishedROAResultType.WRONG_ORIGIN_AND_MAX_LENGTH_MISMATCH,
}

SUPPRESSION_DETAIL_EXCLUDED_KEYS = {
    'approval_impact',
    'fact_context',
    'fact_fingerprint',
    'operator_action',
    'operator_message',
    'rule_family',
    'rule_label',
    'source_kind',
    'source_name',
    'suppressed',
    'suppression_expires_at',
    'suppression_id',
    'suppression_name',
    'suppression_reason',
    'suppression_scope_type',
    'why_it_matters',
}


def _source_summary(
    *,
    lint_run: rpki_models.ROALintRun,
    roa_intent_result: rpki_models.ROAIntentResult | None,
    published_roa_result: rpki_models.PublishedROAResult | None,
    change_plan_item: rpki_models.ROAChangePlanItem | None,
) -> tuple[str, str]:
    if roa_intent_result is not None:
        return 'roa_intent_result', roa_intent_result.name
    if published_roa_result is not None:
        return 'published_roa_result', published_roa_result.name
    if change_plan_item is not None:
        return 'change_plan_item', change_plan_item.name
    return 'lint_run', lint_run.name


def _normalize_fact_value(value):
    if isinstance(value, dict):
        return {
            str(key): _normalize_fact_value(subvalue)
            for key, subvalue in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_fact_value(item) for item in value]
    return value


def _suppression_fact_context(*, finding_code: str, details_json: dict) -> dict:
    return {
        'finding_code': finding_code,
        'details': _normalize_fact_value({
            key: value
            for key, value in (details_json or {}).items()
            if key not in SUPPRESSION_DETAIL_EXCLUDED_KEYS
        }),
    }


def _suppression_fact_fingerprint(*, finding_code: str, details_json: dict) -> str:
    serialized = json.dumps(
        _suppression_fact_context(finding_code=finding_code, details_json=details_json),
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _active_suppression_queryset():
    now = timezone.now()
    return rpki_models.ROALintSuppression.objects.select_related(
        'intent_profile',
        'roa_intent',
    ).filter(
        lifted_at__isnull=True,
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )


def _load_org_rule_overrides(organization_id: int) -> dict[str, dict]:
    result = {}
    for config in rpki_models.ROALintRuleConfig.objects.filter(organization_id=organization_id):
        overrides = {}
        if config.severity_override:
            overrides['severity'] = config.severity_override
        if config.approval_impact_override:
            overrides['approval_impact'] = config.approval_impact_override
        if overrides:
            result[config.finding_code] = overrides
    return result


def _finding_prefix_candidates(details_json: dict) -> set[str]:
    candidates = {
        details_json.get('intent_prefix'),
        details_json.get('prefix_cidr_text'),
        details_json.get('published_prefix'),
    }
    return {str(candidate) for candidate in candidates if candidate}


def _matching_suppression(
    *,
    lint_run: rpki_models.ROALintRun,
    finding_code: str,
    details_json: dict,
    roa_intent_result: rpki_models.ROAIntentResult | None,
    change_plan_item: rpki_models.ROAChangePlanItem | None,
) -> rpki_models.ROALintSuppression | None:
    suppression_target_intent = None
    if roa_intent_result is not None:
        suppression_target_intent = roa_intent_result.roa_intent
    elif change_plan_item is not None and change_plan_item.roa_intent_id is not None:
        suppression_target_intent = change_plan_item.roa_intent

    base_queryset = _active_suppression_queryset().filter(
        organization=lint_run.reconciliation_run.organization,
        finding_code=finding_code,
    )
    fingerprint = _suppression_fact_fingerprint(
        finding_code=finding_code,
        details_json=details_json,
    )
    fingerprint_queryset = base_queryset.filter(fact_fingerprint=fingerprint)
    if suppression_target_intent is not None:
        suppression = fingerprint_queryset.filter(
            scope_type=rpki_models.ROALintSuppressionScope.INTENT,
            roa_intent=suppression_target_intent,
        ).first()
        if suppression is not None:
            return suppression

    suppression = fingerprint_queryset.filter(
        scope_type=rpki_models.ROALintSuppressionScope.PROFILE,
        intent_profile=lint_run.reconciliation_run.intent_profile,
    ).first()
    if suppression is not None:
        return suppression

    suppression = base_queryset.filter(
        scope_type=rpki_models.ROALintSuppressionScope.ORG,
        fact_fingerprint='',
    ).first()
    if suppression is not None:
        return suppression

    prefix_candidates = _finding_prefix_candidates(details_json)
    if not prefix_candidates:
        return None

    return base_queryset.filter(
        scope_type=rpki_models.ROALintSuppressionScope.PREFIX,
        fact_fingerprint='',
        prefix_cidr_text__in=prefix_candidates,
    ).first()


def _finding_explanation(
    *,
    finding_code: str,
    details_json: dict,
    lint_run: rpki_models.ROALintRun,
    roa_intent_result: rpki_models.ROAIntentResult | None,
    published_roa_result: rpki_models.PublishedROAResult | None,
    change_plan_item: rpki_models.ROAChangePlanItem | None,
) -> dict:
    rule_spec = LINT_RULE_SPECS[finding_code]
    source_kind, source_name = _source_summary(
        lint_run=lint_run,
        roa_intent_result=roa_intent_result,
        published_roa_result=published_roa_result,
        change_plan_item=change_plan_item,
    )
    explanations = {
        LINT_RULE_INTENT_OVERBROAD: (
            'The intended authorization allows more-specific prefixes than the current intent requires.',
            'Overbroad maxLength increases the blast radius of a mistaken or hijacked origin announcement.',
            'Review the intended maxLength and narrow it unless broader coverage is explicitly required.',
        ),
        LINT_RULE_INTENT_INCONSISTENT: (
            'Published ROA state does not match the modeled intent for prefix, origin ASN, or maxLength.',
            'Traffic may validate differently from the policy expressed in NetBox until publication is aligned.',
            'Review the mismatch axes and generate or apply the replacement needed to align published state.',
        ),
        LINT_RULE_INTENT_STATE_CONFLICT: (
            'An intent marked inactive or suppressed still appears to have matching published coverage.',
            'Suppressed or inactive policy should not silently remain active in published ROA state.',
            'Review the published authorization and withdraw or re-enable the intent explicitly.',
        ),
        LINT_RULE_PUBLISHED_ORPHANED: (
            'A published ROA no longer maps to any current modeled intent.',
            'Orphaned ROAs preserve authorization that operators are no longer explicitly managing.',
            'Review whether the ROA should be withdrawn or whether matching intent is missing from NetBox.',
        ),
        LINT_RULE_PUBLISHED_STALE: (
            'A published ROA was matched through stale state.',
            'Stale publication evidence can hide the current authorization posture.',
            'Refresh provider state or local publication data before treating this result as current.',
        ),
        LINT_RULE_PUBLISHED_DUPLICATE: (
            'Multiple published ROAs appear to cover the same authorization.',
            'Duplicate coverage complicates review and can hide whether publication is intentionally redundant.',
            'Review the duplicate authorization set and remove redundant entries where possible.',
        ),
        LINT_RULE_PUBLISHED_BROADER_THAN_NEEDED: (
            'A published ROA is broader than the current modeled intent requires.',
            'Unnecessary breadth authorizes extra specifics beyond the current routing policy.',
            'Review whether the ROA should be replaced with a narrower maxLength.',
        ),
        LINT_RULE_PUBLISHED_INCONSISTENT: (
            'A published ROA disagrees with current intent on origin ASN or maxLength.',
            'Operators are publishing state that does not match the policy they intend to enforce.',
            'Review the current intent and replace the published authorization with the intended state.',
        ),
        LINT_RULE_PUBLISHED_UNSCOPED: (
            'A published ROA falls outside the comparison scope used for this lint run.',
            'Unscoped published state may indicate unmanaged authorization or an incomplete review boundary.',
            'Confirm the comparison scope and decide whether the ROA should be managed, ignored, or withdrawn.',
        ),
        LINT_RULE_INTENT_STALE: (
            'The best matching authorization for this intent was stale.',
            'Stale comparisons reduce confidence that the modeled match still reflects current publication.',
            'Refresh the source data before relying on this match for operational decisions.',
        ),
        LINT_RULE_REPLACEMENT_REQUIRED: (
            'This issue requires a replacement workflow rather than a simple keep-or-withdraw decision.',
            'Changing origin or maxLength safely usually requires coordinated create and withdraw actions.',
            'Review the replacement reason and confirm the plan carries both sides of the replacement.',
        ),
        LINT_RULE_INTENT_SUPPRESSED: (
            'This intent is currently suppressed by policy.',
            'Suppressed intent is informational, but it still affects why coverage is absent from the target state.',
            'Confirm the suppression remains intentional before treating missing coverage as a defect.',
        ),
        LINT_RULE_INTENT_INACTIVE: (
            'This intent is currently inactive.',
            'Inactive intent should not drive publication unless operators intentionally reactivate it.',
            'Review whether the inactive state is still correct for the service or prefix.',
        ),
        LINT_RULE_PLAN_REPLACE: (
            'The change plan contains a replacement action pair.',
            'Replacement work is higher risk than a pure create or pure withdraw because both old and new state matter.',
            'Review the before and after state to confirm the replacement aligns with intent.',
        ),
        LINT_RULE_PLAN_RESHAPE: (
            'The change plan reshapes coverage rather than only adding or removing it.',
            'Reshape actions can change validation outcomes for existing routes even when total authorization remains similar.',
            'Review the before and after state carefully before approval.',
        ),
        LINT_RULE_PLAN_BROADENS_AUTHORIZATION: (
            'The change plan creates authorization broader than the aggregate prefix length.',
            'Broadening authorization expands what more-specific routes would validate as allowed.',
            'Review whether the new maxLength is intentionally broad enough to justify approval.',
        ),
        LINT_RULE_PLAN_WITHDRAW_WITHOUT_REPLACEMENT: (
            'The change plan withdraws authorization without a matching replacement for the same prefix and origin.',
            'Routes that depend on that authorization may lose valid coverage after the change is applied.',
            'Review whether coverage should be preserved with a matching create before approval.',
        ),
        LINT_RULE_INTENT_ASN_NOT_IN_ORG: (
            'The intended origin ASN is not associated with this organization tenant.',
            'Tenant-owned ASN data helps catch cross-organization policy mistakes before publication.',
            'Confirm the ASN is intentionally external or associate it with this organization tenant.',
        ),
        LINT_RULE_INTENT_PREFIX_NOT_IN_ORG: (
            'No tenant-owned IPAM prefix record matches the intended prefix.',
            'Without a matching tenant-owned prefix, the organization cannot cross-verify that the intent stays within its modeled address space.',
            'Add the prefix to tenant-scoped IPAM or suppress this finding if ownership data is intentionally incomplete.',
        ),
        LINT_RULE_PUBLISHED_CROSS_ORG_ORIGIN: (
            'The published ROA uses an origin ASN that is not associated with this organization tenant.',
            'A published authorization using an external ASN may be intentional, but it deserves review because it can signal cross-organization drift.',
            'Confirm the published authorization is expected or update tenant-owned ASN data to match reality.',
        ),
        LINT_RULE_PLAN_CROSS_ORG_AUTHORIZATION: (
            'The change plan would create a ROA whose origin ASN is not associated with this organization tenant.',
            'Reviewing tenant ownership before approval helps prevent cross-organization authorizations from being submitted by mistake.',
            'Confirm the authorization is intentional before approval or update tenant-owned ASN data first.',
        ),
    }
    operator_message, why_it_matters, operator_action = explanations[finding_code]
    return {
        'rule_label': rule_spec.label,
        'operator_message': operator_message,
        'why_it_matters': why_it_matters,
        'operator_action': operator_action,
        'source_kind': source_kind,
        'source_name': source_name,
    }


def _serialize_suppression(suppression: rpki_models.ROALintSuppression) -> dict:
    return {
        'suppressed': True,
        'suppression_id': suppression.pk,
        'suppression_name': suppression.name,
        'suppression_scope_type': suppression.scope_type,
        'suppression_reason': suppression.reason,
        'suppression_expires_at': suppression.expires_at.isoformat() if suppression.expires_at else None,
    }


def _normalize_reconciliation_run(
    reconciliation_run: rpki_models.ROAReconciliationRun | int,
) -> rpki_models.ROAReconciliationRun:
    if isinstance(reconciliation_run, rpki_models.ROAReconciliationRun):
        return reconciliation_run
    return rpki_models.ROAReconciliationRun.objects.get(pk=reconciliation_run)


def _normalize_change_plan(
    change_plan: rpki_models.ROAChangePlan | int | None,
) -> rpki_models.ROAChangePlan | None:
    if change_plan is None or isinstance(change_plan, rpki_models.ROAChangePlan):
        return change_plan
    return rpki_models.ROAChangePlan.objects.get(pk=change_plan)


def _normalize_lint_run(
    lint_run: rpki_models.ROALintRun | int,
) -> rpki_models.ROALintRun:
    if isinstance(lint_run, rpki_models.ROALintRun):
        return lint_run
    return rpki_models.ROALintRun.objects.get(pk=lint_run)


def _latest_plan_lint_run(
    change_plan: rpki_models.ROAChangePlan,
) -> rpki_models.ROALintRun | None:
    return change_plan.lint_runs.order_by('-started_at', '-created').first()


def build_roa_lint_lifecycle_summary(
    lint_run: rpki_models.ROALintRun | int,
    *,
    change_plan: rpki_models.ROAChangePlan | int | None = None,
    acknowledged_finding_ids: list[int] | None = None,
) -> dict[str, object]:
    lint_run = _normalize_lint_run(lint_run)
    change_plan = _normalize_change_plan(change_plan)

    impact_keys = (
        LINT_APPROVAL_IMPACT_INFORMATIONAL,
        LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED,
        LINT_APPROVAL_IMPACT_BLOCKING,
    )

    acknowledged_ids: set[int] = set()
    prior_acked_pairs: set[tuple[str, str]] = set()
    prior_acked_at_by: dict[tuple[str, str], list[tuple]] = {}
    current_run_latest_ack_at = None
    current_run_latest_ack_by = ''

    if change_plan is not None:
        acknowledged_ids = set(
            change_plan.lint_acknowledgements.filter(lint_run=lint_run).values_list('finding_id', flat=True)
        )
        acknowledged_ids.update(int(pk) for pk in (acknowledged_finding_ids or []))

        current_acks = list(
            rpki_models.ROALintAcknowledgement.objects
            .filter(change_plan=change_plan, lint_run=lint_run)
            .order_by('-acknowledged_at')
            .values('acknowledged_at', 'acknowledged_by')
        )
        if current_acks:
            latest = current_acks[0]
            if latest['acknowledged_at'] is not None:
                current_run_latest_ack_at = latest['acknowledged_at'].isoformat()
            current_run_latest_ack_by = latest['acknowledged_by'] or ''

        for finding_code, details_json, acked_at, acked_by in (
            rpki_models.ROALintAcknowledgement.objects
            .filter(change_plan=change_plan)
            .exclude(lint_run_id=lint_run.pk)
            .values_list('finding__finding_code', 'finding__details_json', 'acknowledged_at', 'acknowledged_by')
        ):
            fact_fingerprint = (details_json or {}).get('fact_fingerprint', '')
            if fact_fingerprint:
                pair = (finding_code, fact_fingerprint)
                prior_acked_pairs.add(pair)
                prior_acked_at_by.setdefault(pair, []).append((acked_at, acked_by or ''))

    total_counts = {key: 0 for key in impact_keys}
    active_counts = {key: 0 for key in impact_keys}
    suppressed_counts = {key: 0 for key in impact_keys}
    acknowledged_counts = {key: 0 for key in impact_keys}
    unresolved_counts = {key: 0 for key in impact_keys}
    suppressed_finding_count = 0
    acknowledged_finding_count = 0
    previously_acknowledged_finding_count = 0
    previously_acknowledged_finding_ids: set[int] = set()
    active_by_family: dict[str, int] = {}
    suppressed_by_scope: dict[str, int] = {}
    carried_forward_contributing_pairs: set[tuple[str, str]] = set()
    finding_count = 0

    for finding in lint_run.findings.all():
        finding_count += 1
        impact = finding.details_json.get('approval_impact') or LINT_APPROVAL_IMPACT_INFORMATIONAL
        if impact not in total_counts:
            total_counts[impact] = 0
            active_counts[impact] = 0
            suppressed_counts[impact] = 0
            acknowledged_counts[impact] = 0
            unresolved_counts[impact] = 0
        total_counts[impact] += 1
        if finding.details_json.get('suppressed'):
            suppressed_counts[impact] += 1
            suppressed_finding_count += 1
            scope_type = finding.details_json.get('suppression_scope_type')
            if scope_type:
                suppressed_by_scope[scope_type] = suppressed_by_scope.get(scope_type, 0) + 1
            continue
        active_counts[impact] += 1
        family = finding.details_json.get('rule_family', '')
        if family:
            active_by_family[family] = active_by_family.get(family, 0) + 1
        if (
            impact == LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED
            and finding.pk in acknowledged_ids
        ):
            acknowledged_counts[impact] += 1
            acknowledged_finding_count += 1
            continue
        if impact == LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED:
            fact_fingerprint = finding.details_json.get('fact_fingerprint', '')
            if fact_fingerprint and (finding.finding_code, fact_fingerprint) in prior_acked_pairs:
                previously_acknowledged_finding_count += 1
                previously_acknowledged_finding_ids.add(finding.pk)
                carried_forward_contributing_pairs.add((finding.finding_code, fact_fingerprint))
                continue
        unresolved_counts[impact] += 1

    carried_forward_latest_at = None
    carried_forward_latest_by = ''
    if carried_forward_contributing_pairs:
        all_acks = []
        for pair in carried_forward_contributing_pairs:
            for acked_at, acked_by in prior_acked_at_by.get(pair, []):
                all_acks.append((acked_at, acked_by))
        valid_acks = [(at, by) for at, by in all_acks if at is not None]
        if valid_acks:
            valid_acks.sort(key=lambda x: x[0], reverse=True)
            carried_forward_latest_at = valid_acks[0][0].isoformat()
            carried_forward_latest_by = valid_acks[0][1]

    now = timezone.now()
    expiring_suppression_count = rpki_models.ROALintSuppression.objects.filter(
        organization=lint_run.reconciliation_run.organization,
        lifted_at__isnull=True,
        expires_at__isnull=False,
        expires_at__lte=now + timedelta(days=30),
    ).count()

    return {
        'lifecycle_summary_schema_version': LINT_LIFECYCLE_SUMMARY_SCHEMA_VERSION,
        'lint_run_id': lint_run.pk,
        'change_plan_id': change_plan.pk if change_plan is not None else None,
        'finding_count': finding_count,
        'active_finding_count': finding_count - suppressed_finding_count,
        'suppressed_finding_count': suppressed_finding_count,
        'acknowledged_finding_count': acknowledged_finding_count,
        'previously_acknowledged_finding_count': previously_acknowledged_finding_count,
        'previously_acknowledged_finding_ids': sorted(previously_acknowledged_finding_ids),
        'approval_impact_counts': total_counts,
        'active_approval_impact_counts': active_counts,
        'suppressed_approval_impact_counts': suppressed_counts,
        'acknowledged_approval_impact_counts': acknowledged_counts,
        'unresolved_approval_impact_counts': unresolved_counts,
        'active_by_family': active_by_family,
        'suppressed_by_scope': suppressed_by_scope,
        'expiring_suppression_count': expiring_suppression_count,
        'carried_forward_count': previously_acknowledged_finding_count,
        'carried_forward_latest_at': carried_forward_latest_at,
        'carried_forward_latest_by': carried_forward_latest_by,
        'current_run_latest_ack_at': current_run_latest_ack_at,
        'current_run_latest_ack_by': current_run_latest_ack_by,
    }


def build_roa_change_plan_lint_posture(
    change_plan: rpki_models.ROAChangePlan | int,
    *,
    acknowledged_finding_ids: list[int] | None = None,
) -> dict[str, object]:
    change_plan = _normalize_change_plan(change_plan)
    if change_plan is None:
        raise ValueError('ROA lint posture requires a change plan.')
    lint_run = _latest_plan_lint_run(change_plan)
    impact_keys = (
        LINT_APPROVAL_IMPACT_INFORMATIONAL,
        LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED,
        LINT_APPROVAL_IMPACT_BLOCKING,
    )
    zero_counts = {key: 0 for key in impact_keys}
    if lint_run is None:
        return {
            'posture_schema_version': LINT_POSTURE_SCHEMA_VERSION,
            'change_plan_id': change_plan.pk,
            'has_lint_run': False,
            'lint_run_id': None,
            'status': 'missing_lint',
            'can_approve': False,
            'finding_count': 0,
            'active_finding_count': 0,
            'suppressed_finding_count': 0,
            'acknowledged_finding_count': 0,
            'previously_acknowledged_finding_count': 0,
            'previously_acknowledged_finding_ids': [],
            'approval_impact_counts': dict(zero_counts),
            'active_approval_impact_counts': dict(zero_counts),
            'suppressed_approval_impact_counts': dict(zero_counts),
            'acknowledged_approval_impact_counts': dict(zero_counts),
            'unresolved_approval_impact_counts': dict(zero_counts),
            'blocking_finding_count': 0,
            'unresolved_blocking_finding_count': 0,
            'acknowledgement_required_finding_count': 0,
            'acknowledged_acknowledgement_required_finding_count': 0,
            'unresolved_acknowledgement_required_finding_count': 0,
            'informational_finding_count': 0,
            'latest_lint_ack_at': None,
            'latest_lint_ack_by': '',
            'carried_forward_count': 0,
            'carried_forward_latest_at': None,
            'carried_forward_latest_by': '',
        }

    summary = build_roa_lint_lifecycle_summary(
        lint_run,
        change_plan=change_plan,
        acknowledged_finding_ids=acknowledged_finding_ids,
    )

    active_counts = summary['active_approval_impact_counts']
    acknowledged_counts = summary['acknowledged_approval_impact_counts']
    unresolved_counts = summary['unresolved_approval_impact_counts']
    unresolved_blocking = unresolved_counts[LINT_APPROVAL_IMPACT_BLOCKING]
    unresolved_ack_required = unresolved_counts[LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED]
    previously_acknowledged_finding_count = summary['previously_acknowledged_finding_count']

    if unresolved_blocking > 0:
        status = 'blocked'
    elif unresolved_ack_required > 0:
        status = 'acknowledgement_required'
    elif previously_acknowledged_finding_count > 0:
        status = 'previously_acknowledged'
    else:
        status = 'clear'

    return {
        'posture_schema_version': LINT_POSTURE_SCHEMA_VERSION,
        'change_plan_id': change_plan.pk,
        'has_lint_run': True,
        'lint_run_id': lint_run.pk,
        'status': status,
        'can_approve': (
            unresolved_blocking == 0
            and unresolved_ack_required == 0
            and previously_acknowledged_finding_count == 0
        ),
        'finding_count': summary['finding_count'],
        'active_finding_count': summary['active_finding_count'],
        'suppressed_finding_count': summary['suppressed_finding_count'],
        'acknowledged_finding_count': summary['acknowledged_finding_count'],
        'previously_acknowledged_finding_count': previously_acknowledged_finding_count,
        'previously_acknowledged_finding_ids': summary['previously_acknowledged_finding_ids'],
        'approval_impact_counts': summary['approval_impact_counts'],
        'active_approval_impact_counts': active_counts,
        'suppressed_approval_impact_counts': summary['suppressed_approval_impact_counts'],
        'acknowledged_approval_impact_counts': acknowledged_counts,
        'unresolved_approval_impact_counts': unresolved_counts,
        'blocking_finding_count': active_counts[LINT_APPROVAL_IMPACT_BLOCKING],
        'unresolved_blocking_finding_count': unresolved_blocking,
        'acknowledgement_required_finding_count': active_counts[LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED],
        'acknowledged_acknowledgement_required_finding_count': (
            acknowledged_counts[LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED]
        ),
        'unresolved_acknowledgement_required_finding_count': unresolved_ack_required,
        'informational_finding_count': active_counts[LINT_APPROVAL_IMPACT_INFORMATIONAL],
        'latest_lint_ack_at': summary['current_run_latest_ack_at'],
        'latest_lint_ack_by': summary['current_run_latest_ack_by'],
        'carried_forward_count': previously_acknowledged_finding_count,
        'carried_forward_latest_at': summary['carried_forward_latest_at'],
        'carried_forward_latest_by': summary['carried_forward_latest_by'],
    }


def refresh_roa_change_plan_lint_posture(
    change_plan: rpki_models.ROAChangePlan | int,
) -> dict[str, object]:
    change_plan = _normalize_change_plan(change_plan)
    if change_plan is None:
        raise ValueError('ROA lint posture requires a change plan.')
    summary_json = dict(change_plan.summary_json or {})
    summary_json['lint_posture'] = build_roa_change_plan_lint_posture(change_plan)
    change_plan.summary_json = summary_json
    change_plan.save(update_fields=('summary_json',))
    return summary_json['lint_posture']


def _create_finding(
    lint_run: rpki_models.ROALintRun,
    *,
    finding_code: str,
    org_overrides: dict[str, dict] | None = None,
    severity: str | None = None,
    details_json: dict,
    roa_intent_result: rpki_models.ROAIntentResult | None = None,
    published_roa_result: rpki_models.PublishedROAResult | None = None,
    change_plan_item: rpki_models.ROAChangePlanItem | None = None,
) -> rpki_models.ROALintFinding:
    rule_spec = LINT_RULE_SPECS[finding_code]
    rule_overrides = (org_overrides or {}).get(finding_code, {})
    effective_severity = rule_overrides.get('severity') or severity or rule_spec.default_severity
    effective_approval_impact = rule_overrides.get('approval_impact') or rule_spec.approval_impact
    suppression = _matching_suppression(
        lint_run=lint_run,
        finding_code=finding_code,
        details_json=details_json,
        roa_intent_result=roa_intent_result,
        change_plan_item=change_plan_item,
    )
    fact_context = _suppression_fact_context(
        finding_code=finding_code,
        details_json=details_json,
    )
    fact_fingerprint = _suppression_fact_fingerprint(
        finding_code=finding_code,
        details_json=details_json,
    )
    source_name = (
        roa_intent_result.name
        if roa_intent_result is not None
        else published_roa_result.name
        if published_roa_result is not None
        else change_plan_item.name
        if change_plan_item is not None
        else lint_run.name
    )
    if suppression is not None:
        suppression.last_matched_at = timezone.now()
        suppression.match_count = suppression.match_count + 1
        suppression.save(update_fields=('last_matched_at', 'match_count'))

    return rpki_models.ROALintFinding.objects.create(
        name=f'{source_name} {finding_code}',
        lint_run=lint_run,
        tenant=lint_run.tenant,
        roa_intent_result=roa_intent_result,
        published_roa_result=published_roa_result,
        change_plan_item=change_plan_item,
        finding_code=finding_code,
        severity=effective_severity,
        details_json={
            'rule_family': rule_spec.family,
            'approval_impact': effective_approval_impact,
            'fact_fingerprint': fact_fingerprint,
            'fact_context': fact_context,
            **(_serialize_suppression(suppression) if suppression is not None else {'suppressed': False}),
            **_finding_explanation(
                finding_code=finding_code,
                details_json=details_json,
                lint_run=lint_run,
                roa_intent_result=roa_intent_result,
                published_roa_result=published_roa_result,
                change_plan_item=change_plan_item,
            ),
            **details_json,
        },
        computed_at=timezone.now(),
    )


def _plan_item_prefix_and_max_length(
    item: rpki_models.ROAChangePlanItem,
) -> tuple[str | None, int | None]:
    for payload in (item.after_state_json, item.before_state_json):
        prefix_cidr_text = payload.get('prefix_cidr_text')
        max_length = payload.get('max_length')
        if prefix_cidr_text:
            return prefix_cidr_text, max_length
    prefix_cidr_text = item.provider_payload_json.get('prefix')
    if prefix_cidr_text:
        return prefix_cidr_text, item.provider_payload_json.get('max_length')
    return None, None


def _plan_item_prefix_asn_key(item: rpki_models.ROAChangePlanItem) -> tuple[str | None, int | None]:
    for payload in (item.after_state_json, item.before_state_json):
        prefix_cidr_text = payload.get('prefix_cidr_text')
        origin_asn_value = payload.get('origin_asn_value')
        if prefix_cidr_text:
            return prefix_cidr_text, origin_asn_value
    prefix_cidr_text = item.provider_payload_json.get('prefix')
    if prefix_cidr_text:
        return prefix_cidr_text, item.provider_payload_json.get('asn')
    return None, None


def _plan_item_broadens_authorization(item: rpki_models.ROAChangePlanItem) -> bool:
    prefix_cidr_text, max_length = _plan_item_prefix_and_max_length(item)
    if not prefix_cidr_text or max_length is None:
        return False
    return max_length > ip_network(prefix_cidr_text, strict=False).prefixlen


def _plan_item_leaves_no_replacement(
    item: rpki_models.ROAChangePlanItem,
    created_keys: set[tuple[str | None, int | None]],
) -> bool:
    if item.action_type != rpki_models.ROAChangePlanAction.WITHDRAW:
        return False
    if item.plan_semantic == rpki_models.ROAChangePlanItemSemantic.REPLACE:
        return False
    return _plan_item_prefix_asn_key(item) not in created_keys


def _build_org_ownership_context(organization: rpki_models.Organization) -> dict[str, set]:
    """
    Load tenant-owned ASN and prefix data for the organization.

    If tenant ownership data is absent, ownership-context rules emit no findings.
    """
    asn_values: set[int] = set()
    prefix_cidrs: set[str] = set()
    tenant = getattr(organization, 'tenant', None)
    if tenant is None:
        return {'asn_values': asn_values, 'prefix_cidrs': prefix_cidrs}

    try:
        from ipam.models import Prefix as IpamPrefix
        from ipam.models.asns import ASN as IpamAsn
    except Exception:
        return {'asn_values': asn_values, 'prefix_cidrs': prefix_cidrs}

    try:
        asn_values.update(IpamAsn.objects.filter(tenant=tenant).values_list('asn', flat=True))
    except Exception:
        pass

    try:
        prefix_cidrs.update(
            str(prefix)
            for prefix in IpamPrefix.objects.filter(tenant=tenant).values_list('prefix', flat=True)
        )
    except Exception:
        pass

    return {'asn_values': asn_values, 'prefix_cidrs': prefix_cidrs}


def _intent_lint_findings(
    lint_run: rpki_models.ROALintRun,
    intent_result: rpki_models.ROAIntentResult,
    *,
    org_overrides: dict[str, dict] | None = None,
) -> list[rpki_models.ROALintFinding]:
    details = dict(intent_result.details_json or {})
    findings: list[rpki_models.ROALintFinding] = []

    if intent_result.result_type in {
        rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
        rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_OVERBROAD,
    }:
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_INTENT_OVERBROAD,
                org_overrides=org_overrides,
                severity=intent_result.severity,
                roa_intent_result=intent_result,
                details_json={
                    'result_type': intent_result.result_type,
                    'intent_prefix': details.get('intent_prefix'),
                    'intent_max_length': details.get('intent_max_length'),
                    'published_max_length': details.get('published_max_length'),
                },
            )
        )

    if intent_result.result_type in INTENT_INCONSISTENT_RESULT_TYPES:
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_INTENT_INCONSISTENT,
                org_overrides=org_overrides,
                severity=intent_result.severity,
                roa_intent_result=intent_result,
                details_json={
                    'result_type': intent_result.result_type,
                    'intent_prefix': details.get('intent_prefix'),
                    'intent_origin_asn': details.get('intent_origin_asn'),
                    'intent_max_length': details.get('intent_max_length'),
                    'published_prefix': details.get('published_prefix'),
                    'published_origin_asn': details.get('published_origin_asn'),
                    'published_max_length': details.get('published_max_length'),
                    'mismatch_axes': details.get('mismatch_axes', []),
                },
            )
        )

    if details.get('replacement_required'):
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_REPLACEMENT_REQUIRED,
                org_overrides=org_overrides,
                severity=intent_result.severity,
                roa_intent_result=intent_result,
                details_json={
                    'result_type': intent_result.result_type,
                    'replacement_reason_code': details.get('replacement_reason_code'),
                    'mismatch_axes': details.get('mismatch_axes', []),
                },
            )
        )

    if (
        intent_result.result_type in {
            rpki_models.ROAIntentResultType.SUPPRESSED_BY_POLICY,
            rpki_models.ROAIntentResultType.INACTIVE_INTENT,
        }
        and (
            intent_result.best_roa_object_id is not None
            or intent_result.best_imported_authorization_id is not None
            or details.get('published_prefix')
        )
    ):
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_INTENT_STATE_CONFLICT,
                org_overrides=org_overrides,
                severity=rpki_models.ReconciliationSeverity.WARNING,
                roa_intent_result=intent_result,
                details_json={
                    'result_type': intent_result.result_type,
                    'intent_prefix': details.get('intent_prefix'),
                    'intent_origin_asn': details.get('intent_origin_asn'),
                    'published_prefix': details.get('published_prefix'),
                    'published_origin_asn': details.get('published_origin_asn'),
                },
            )
        )

    informational_codes = {
        rpki_models.ROAIntentResultType.STALE: LINT_RULE_INTENT_STALE,
        rpki_models.ROAIntentResultType.SUPPRESSED_BY_POLICY: LINT_RULE_INTENT_SUPPRESSED,
        rpki_models.ROAIntentResultType.INACTIVE_INTENT: LINT_RULE_INTENT_INACTIVE,
    }
    finding_code = informational_codes.get(intent_result.result_type)
    if finding_code:
        findings.append(
            _create_finding(
                lint_run,
                finding_code=finding_code,
                org_overrides=org_overrides,
                severity=intent_result.severity,
                roa_intent_result=intent_result,
                details_json={
                    'result_type': intent_result.result_type,
                    'intent_prefix': details.get('intent_prefix'),
                    'intent_origin_asn': details.get('intent_origin_asn'),
                },
            )
        )

    return findings


def _published_lint_findings(
    lint_run: rpki_models.ROALintRun,
    published_result: rpki_models.PublishedROAResult,
    *,
    org_overrides: dict[str, dict] | None = None,
) -> list[rpki_models.ROALintFinding]:
    details = dict(published_result.details_json or {})
    findings: list[rpki_models.ROALintFinding] = []

    if published_result.result_type == rpki_models.PublishedROAResultType.ORPHANED:
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_PUBLISHED_ORPHANED,
                org_overrides=org_overrides,
                severity=published_result.severity,
                published_roa_result=published_result,
                details_json={
                    'result_type': published_result.result_type,
                    'source': details.get('source'),
                    'prefix_cidr_text': details.get('prefix_cidr_text'),
                },
            )
        )
    elif published_result.result_type == rpki_models.PublishedROAResultType.STALE:
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_PUBLISHED_STALE,
                org_overrides=org_overrides,
                severity=published_result.severity,
                published_roa_result=published_result,
                details_json={
                    'result_type': published_result.result_type,
                    'source': details.get('source'),
                    'prefix_cidr_text': details.get('prefix_cidr_text'),
                },
            )
        )
    elif published_result.result_type == rpki_models.PublishedROAResultType.DUPLICATE:
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_PUBLISHED_DUPLICATE,
                org_overrides=org_overrides,
                severity=published_result.severity,
                published_roa_result=published_result,
                details_json={
                    'result_type': published_result.result_type,
                    'source': details.get('source'),
                    'prefix_cidr_text': details.get('prefix_cidr_text'),
                    'origin_asn': details.get('origin_asn'),
                },
            )
        )
    elif published_result.result_type == rpki_models.PublishedROAResultType.BROADER_THAN_NEEDED:
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_PUBLISHED_BROADER_THAN_NEEDED,
                org_overrides=org_overrides,
                severity=published_result.severity,
                published_roa_result=published_result,
                details_json={
                    'result_type': published_result.result_type,
                    'source': details.get('source'),
                    'prefix_cidr_text': details.get('prefix_cidr_text'),
                    'max_length': details.get('max_length'),
                },
            )
        )
    elif published_result.result_type == rpki_models.PublishedROAResultType.UNSCOPED:
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_PUBLISHED_UNSCOPED,
                org_overrides=org_overrides,
                severity=published_result.severity,
                published_roa_result=published_result,
                details_json={
                    'result_type': published_result.result_type,
                    'source': details.get('source'),
                    'prefix_cidr_text': details.get('prefix_cidr_text'),
                    'comparison_scope': details.get('comparison_scope'),
                },
            )
        )

    if published_result.result_type in PUBLISHED_INCONSISTENT_RESULT_TYPES:
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_PUBLISHED_INCONSISTENT,
                org_overrides=org_overrides,
                severity=published_result.severity,
                published_roa_result=published_result,
                details_json={
                    'result_type': published_result.result_type,
                    'source': details.get('source'),
                    'prefix_cidr_text': details.get('prefix_cidr_text'),
                    'origin_asn': details.get('origin_asn'),
                    'max_length': details.get('max_length'),
                },
            )
        )

    if details.get('replacement_required'):
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_REPLACEMENT_REQUIRED,
                org_overrides=org_overrides,
                severity=published_result.severity,
                published_roa_result=published_result,
                details_json={
                    'result_type': published_result.result_type,
                    'replacement_reason_code': details.get('replacement_reason_code'),
                },
            )
        )

    return findings


def _plan_lint_findings(
    lint_run: rpki_models.ROALintRun,
    change_plan: rpki_models.ROAChangePlan,
    *,
    org_overrides: dict[str, dict] | None = None,
) -> list[rpki_models.ROALintFinding]:
    findings: list[rpki_models.ROALintFinding] = []
    plan_items = list(change_plan.items.all())
    created_keys = {
        _plan_item_prefix_asn_key(item)
        for item in plan_items
        if item.action_type == rpki_models.ROAChangePlanAction.CREATE
    }
    for item in plan_items:
        if item.plan_semantic == rpki_models.ROAChangePlanItemSemantic.REPLACE:
            findings.append(
                _create_finding(
                    lint_run,
                    finding_code=LINT_RULE_PLAN_REPLACE,
                    org_overrides=org_overrides,
                    change_plan_item=item,
                    details_json={
                        'action_type': item.action_type,
                        'plan_semantic': item.plan_semantic,
                    },
                )
            )
        elif item.plan_semantic == rpki_models.ROAChangePlanItemSemantic.RESHAPE:
            findings.append(
                _create_finding(
                    lint_run,
                    finding_code=LINT_RULE_PLAN_RESHAPE,
                    org_overrides=org_overrides,
                    change_plan_item=item,
                    details_json={
                        'action_type': item.action_type,
                        'plan_semantic': item.plan_semantic,
                    },
                )
            )
        if (
            item.action_type == rpki_models.ROAChangePlanAction.CREATE
            and _plan_item_broadens_authorization(item)
        ):
            prefix_cidr_text, max_length = _plan_item_prefix_and_max_length(item)
            findings.append(
                _create_finding(
                    lint_run,
                    finding_code=LINT_RULE_PLAN_BROADENS_AUTHORIZATION,
                    org_overrides=org_overrides,
                    change_plan_item=item,
                    details_json={
                        'action_type': item.action_type,
                        'plan_semantic': item.plan_semantic,
                        'prefix_cidr_text': prefix_cidr_text,
                        'max_length': max_length,
                    },
                )
            )
        if _plan_item_leaves_no_replacement(item, created_keys):
            prefix_cidr_text, origin_asn_value = _plan_item_prefix_asn_key(item)
            findings.append(
                _create_finding(
                    lint_run,
                    finding_code=LINT_RULE_PLAN_WITHDRAW_WITHOUT_REPLACEMENT,
                    org_overrides=org_overrides,
                    change_plan_item=item,
                    details_json={
                        'action_type': item.action_type,
                        'plan_semantic': item.plan_semantic,
                        'prefix_cidr_text': prefix_cidr_text,
                        'origin_asn_value': origin_asn_value,
                    },
                )
            )
    return findings


def _ownership_lint_findings(
    lint_run: rpki_models.ROALintRun,
    *,
    intent_results: list[rpki_models.ROAIntentResult],
    published_results: list[rpki_models.PublishedROAResult],
    plan: rpki_models.ROAChangePlan | None,
    ownership_context: dict[str, set],
    org_overrides: dict[str, dict],
) -> list[rpki_models.ROALintFinding]:
    findings: list[rpki_models.ROALintFinding] = []
    asn_values = ownership_context.get('asn_values', set())
    prefix_cidrs = ownership_context.get('prefix_cidrs', set())

    if asn_values:
        for intent_result in intent_results:
            intent = intent_result.roa_intent
            asn_value = (
                getattr(getattr(intent, 'origin_asn', None), 'asn', None)
                or getattr(intent, 'origin_asn_value', None)
            )
            if asn_value is not None and asn_value not in asn_values:
                findings.append(
                    _create_finding(
                        lint_run,
                        finding_code=LINT_RULE_INTENT_ASN_NOT_IN_ORG,
                        org_overrides=org_overrides,
                        roa_intent_result=intent_result,
                        details_json={
                            'intent_prefix': (intent_result.details_json or {}).get('intent_prefix'),
                            'intent_origin_asn': asn_value,
                            'org_asn_count': len(asn_values),
                        },
                    )
                )

    if prefix_cidrs:
        for intent_result in intent_results:
            intent_prefix = (intent_result.details_json or {}).get('intent_prefix')
            if intent_prefix and intent_prefix not in prefix_cidrs:
                findings.append(
                    _create_finding(
                        lint_run,
                        finding_code=LINT_RULE_INTENT_PREFIX_NOT_IN_ORG,
                        org_overrides=org_overrides,
                        roa_intent_result=intent_result,
                        details_json={
                            'intent_prefix': intent_prefix,
                            'ipam_prefix_count': len(prefix_cidrs),
                        },
                    )
                )

    if asn_values:
        for published_result in published_results:
            details = published_result.details_json or {}
            origin_asn = details.get('origin_asn') or details.get('origin_asn_value')
            if origin_asn is not None and origin_asn not in asn_values:
                findings.append(
                    _create_finding(
                        lint_run,
                        finding_code=LINT_RULE_PUBLISHED_CROSS_ORG_ORIGIN,
                        org_overrides=org_overrides,
                        published_roa_result=published_result,
                        details_json={
                            'prefix_cidr_text': details.get('prefix_cidr_text') or details.get('published_prefix'),
                            'origin_asn': origin_asn,
                            'org_asn_count': len(asn_values),
                        },
                    )
                )

    if plan is not None and asn_values:
        for item in plan.items.filter(action_type=rpki_models.ROAChangePlanAction.CREATE):
            prefix_cidr_text, _ = _plan_item_prefix_and_max_length(item)
            _, origin_asn_value = _plan_item_prefix_asn_key(item)
            if origin_asn_value is not None and origin_asn_value not in asn_values:
                findings.append(
                    _create_finding(
                        lint_run,
                        finding_code=LINT_RULE_PLAN_CROSS_ORG_AUTHORIZATION,
                        org_overrides=org_overrides,
                        change_plan_item=item,
                        details_json={
                            'prefix_cidr_text': prefix_cidr_text,
                            'origin_asn_value': origin_asn_value,
                            'org_asn_count': len(asn_values),
                        },
                    )
                )

    return findings


def suppress_roa_lint_finding(
    finding: rpki_models.ROALintFinding | int,
    *,
    scope_type: str,
    reason: str,
    created_by: str = '',
    expires_at=None,
    notes: str = '',
) -> rpki_models.ROALintSuppression:
    if not isinstance(finding, rpki_models.ROALintFinding):
        finding = rpki_models.ROALintFinding.objects.select_related(
            'lint_run__reconciliation_run__intent_profile',
            'roa_intent_result__roa_intent',
            'change_plan_item__roa_intent',
        ).get(pk=finding)

    reconciliation_run = finding.lint_run.reconciliation_run
    organization = reconciliation_run.organization
    roa_intent = None
    if finding.roa_intent_result_id is not None:
        roa_intent = finding.roa_intent_result.roa_intent
    elif finding.change_plan_item_id is not None and finding.change_plan_item.roa_intent_id is not None:
        roa_intent = finding.change_plan_item.roa_intent

    payload = {
        'organization': organization,
        'finding_code': finding.finding_code,
        'scope_type': scope_type,
        'reason': reason,
        'notes': notes,
        'fact_fingerprint': finding.details_json.get('fact_fingerprint')
        or _suppression_fact_fingerprint(
            finding_code=finding.finding_code,
            details_json=finding.details_json,
        ),
        'fact_context_json': finding.details_json.get('fact_context')
        or _suppression_fact_context(
            finding_code=finding.finding_code,
            details_json=finding.details_json,
        ),
        'created_by': created_by,
        'created_at': timezone.now(),
        'expires_at': expires_at,
        'tenant': finding.tenant,
    }
    if scope_type == rpki_models.ROALintSuppressionScope.INTENT:
        if roa_intent is None:
            raise ValueError('Intent-scoped suppressions require a lint finding tied to a ROA intent.')
        payload['roa_intent'] = roa_intent
        payload['name'] = f'{finding.finding_code} suppression for {roa_intent.name}'
        suppression = rpki_models.ROALintSuppression.objects.filter(
            finding_code=finding.finding_code,
            scope_type=scope_type,
            roa_intent=roa_intent,
            lifted_at__isnull=True,
        ).first()
        if suppression is not None:
            return suppression
        suppression = rpki_models.ROALintSuppression(**payload)
        suppression.full_clean(validate_unique=False)
        suppression.save()
        return suppression

    if scope_type == rpki_models.ROALintSuppressionScope.PROFILE:
        payload['intent_profile'] = reconciliation_run.intent_profile
        payload['name'] = f'{finding.finding_code} suppression for {reconciliation_run.intent_profile.name}'
        suppression = rpki_models.ROALintSuppression.objects.filter(
            finding_code=finding.finding_code,
            scope_type=scope_type,
            intent_profile=reconciliation_run.intent_profile,
            lifted_at__isnull=True,
        ).first()
        if suppression is not None:
            return suppression
        suppression = rpki_models.ROALintSuppression(**payload)
        suppression.full_clean(validate_unique=False)
        suppression.save()
        return suppression

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
        prefix_candidates = _finding_prefix_candidates(finding.details_json or {})
        if not prefix_candidates:
            raise ValueError('PREFIX-scoped suppressions require a finding with a resolvable prefix field.')
        prefix_cidr_text = sorted(prefix_candidates)[0]
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

    raise ValueError('Unsupported suppression scope.')


def lift_roa_lint_suppression(
    suppression: rpki_models.ROALintSuppression | int,
    *,
    lifted_by: str = '',
    lift_reason: str = '',
) -> rpki_models.ROALintSuppression:
    if not isinstance(suppression, rpki_models.ROALintSuppression):
        suppression = rpki_models.ROALintSuppression.objects.get(pk=suppression)
    if suppression.lifted_at is not None:
        return suppression
    suppression.lifted_at = timezone.now()
    suppression.lifted_by = lifted_by
    suppression.lift_reason = lift_reason
    suppression.full_clean(validate_unique=False)
    suppression.save(update_fields=('lifted_at', 'lifted_by', 'lift_reason'))
    return suppression


def run_roa_lint(
    reconciliation_run: rpki_models.ROAReconciliationRun | int,
    *,
    change_plan: rpki_models.ROAChangePlan | int | None = None,
    run_name: str | None = None,
) -> rpki_models.ROALintRun:
    reconciliation_run = _normalize_reconciliation_run(reconciliation_run)
    change_plan = _normalize_change_plan(change_plan)
    org_overrides = _load_org_rule_overrides(reconciliation_run.organization_id)
    now = timezone.now()
    lint_run = rpki_models.ROALintRun.objects.create(
        name=run_name or f'{reconciliation_run.name} Lint {now:%Y-%m-%d %H:%M:%S}',
        reconciliation_run=reconciliation_run,
        change_plan=change_plan,
        tenant=reconciliation_run.tenant,
        status=rpki_models.ValidationRunStatus.RUNNING,
        started_at=now,
    )

    severity_counts = {
        rpki_models.ReconciliationSeverity.INFO: 0,
        rpki_models.ReconciliationSeverity.WARNING: 0,
        rpki_models.ReconciliationSeverity.ERROR: 0,
        rpki_models.ReconciliationSeverity.CRITICAL: 0,
    }
    finding_code_counts: dict[str, int] = {}
    rule_family_counts: dict[str, int] = {}
    approval_impact_counts = {
        LINT_APPROVAL_IMPACT_INFORMATIONAL: 0,
        LINT_APPROVAL_IMPACT_ACKNOWLEDGEMENT_REQUIRED: 0,
        LINT_APPROVAL_IMPACT_BLOCKING: 0,
    }
    suppressed_finding_count = 0

    intent_results = list(
        reconciliation_run.intent_results.select_related('roa_intent__origin_asn').all()
    )
    published_results = list(reconciliation_run.published_roa_results.all())
    all_findings: list[rpki_models.ROALintFinding] = []
    for intent_result in intent_results:
        all_findings.extend(_intent_lint_findings(lint_run, intent_result, org_overrides=org_overrides))
    for published_result in published_results:
        all_findings.extend(_published_lint_findings(lint_run, published_result, org_overrides=org_overrides))
    if change_plan is not None:
        all_findings.extend(_plan_lint_findings(lint_run, change_plan, org_overrides=org_overrides))
    ownership_context = _build_org_ownership_context(reconciliation_run.organization)
    all_findings.extend(
        _ownership_lint_findings(
            lint_run,
            intent_results=intent_results,
            published_results=published_results,
            plan=change_plan,
            ownership_context=ownership_context,
            org_overrides=org_overrides,
        )
    )

    for finding in all_findings:
        rule_family = finding.details_json.get('rule_family') or LINT_RULE_SPECS[finding.finding_code].family
        approval_impact = finding.details_json.get('approval_impact') or LINT_RULE_SPECS[finding.finding_code].approval_impact
        if finding.details_json.get('suppressed'):
            suppressed_finding_count += 1
        severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
        finding_code_counts[finding.finding_code] = finding_code_counts.get(finding.finding_code, 0) + 1
        rule_family_counts[rule_family] = rule_family_counts.get(rule_family, 0) + 1
        approval_impact_counts[approval_impact] = approval_impact_counts.get(
            approval_impact, 0
        ) + 1

    lint_run.status = rpki_models.ValidationRunStatus.COMPLETED
    lint_run.completed_at = timezone.now()
    lint_run.finding_count = len(all_findings)
    lint_run.info_count = severity_counts[rpki_models.ReconciliationSeverity.INFO]
    lint_run.warning_count = severity_counts[rpki_models.ReconciliationSeverity.WARNING]
    lint_run.error_count = severity_counts[rpki_models.ReconciliationSeverity.ERROR]
    lint_run.critical_count = severity_counts[rpki_models.ReconciliationSeverity.CRITICAL]
    lint_run.summary_json = {
        'summary_schema_version': LINT_SUMMARY_SCHEMA_VERSION,
        'severity_counts': severity_counts,
        'finding_code_counts': finding_code_counts,
        'rule_family_counts': rule_family_counts,
        'approval_impact_counts': approval_impact_counts,
        'blocking_finding_count': approval_impact_counts[LINT_APPROVAL_IMPACT_BLOCKING],
        'informational_finding_count': approval_impact_counts[LINT_APPROVAL_IMPACT_INFORMATIONAL],
        'suppressed_finding_count': suppressed_finding_count,
        'active_finding_count': len(all_findings) - suppressed_finding_count,
        'reconciliation_run_id': reconciliation_run.pk,
        'change_plan_id': getattr(change_plan, 'pk', None),
        'comparison_scope': reconciliation_run.comparison_scope,
    }
    lint_run.save(
        update_fields=(
            'status',
            'completed_at',
            'finding_count',
            'info_count',
            'warning_count',
            'error_count',
            'critical_count',
            'summary_json',
        )
    )
    return lint_run
