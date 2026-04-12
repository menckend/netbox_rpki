from __future__ import annotations

from django.utils import timezone

from netbox_rpki import models as rpki_models


LINT_RULE_INTENT_OVERBROAD = 'intent_max_length_overbroad'
LINT_RULE_PUBLISHED_ORPHANED = 'published_orphaned'
LINT_RULE_PUBLISHED_STALE = 'published_stale'
LINT_RULE_INTENT_STALE = 'intent_stale'
LINT_RULE_REPLACEMENT_REQUIRED = 'replacement_required'
LINT_RULE_INTENT_SUPPRESSED = 'intent_suppressed'
LINT_RULE_INTENT_INACTIVE = 'intent_inactive'
LINT_RULE_PLAN_REPLACE = 'plan_replace'
LINT_RULE_PLAN_RESHAPE = 'plan_reshape'


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


def _create_finding(
    lint_run: rpki_models.ROALintRun,
    *,
    finding_code: str,
    severity: str,
    details_json: dict,
    roa_intent_result: rpki_models.ROAIntentResult | None = None,
    published_roa_result: rpki_models.PublishedROAResult | None = None,
    change_plan_item: rpki_models.ROAChangePlanItem | None = None,
) -> rpki_models.ROALintFinding:
    source_name = (
        roa_intent_result.name
        if roa_intent_result is not None
        else published_roa_result.name
        if published_roa_result is not None
        else change_plan_item.name
        if change_plan_item is not None
        else lint_run.name
    )
    return rpki_models.ROALintFinding.objects.create(
        name=f'{source_name} {finding_code}',
        lint_run=lint_run,
        tenant=lint_run.tenant,
        roa_intent_result=roa_intent_result,
        published_roa_result=published_roa_result,
        change_plan_item=change_plan_item,
        finding_code=finding_code,
        severity=severity,
        details_json=details_json,
        computed_at=timezone.now(),
    )


def _intent_lint_findings(
    lint_run: rpki_models.ROALintRun,
    intent_result: rpki_models.ROAIntentResult,
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

    if details.get('replacement_required'):
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_REPLACEMENT_REQUIRED,
                severity=intent_result.severity,
                roa_intent_result=intent_result,
                details_json={
                    'result_type': intent_result.result_type,
                    'replacement_reason_code': details.get('replacement_reason_code'),
                    'mismatch_axes': details.get('mismatch_axes', []),
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
) -> list[rpki_models.ROALintFinding]:
    details = dict(published_result.details_json or {})
    findings: list[rpki_models.ROALintFinding] = []

    if published_result.result_type == rpki_models.PublishedROAResultType.ORPHANED:
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_PUBLISHED_ORPHANED,
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
                severity=published_result.severity,
                published_roa_result=published_result,
                details_json={
                    'result_type': published_result.result_type,
                    'source': details.get('source'),
                    'prefix_cidr_text': details.get('prefix_cidr_text'),
                },
            )
        )

    if details.get('replacement_required'):
        findings.append(
            _create_finding(
                lint_run,
                finding_code=LINT_RULE_REPLACEMENT_REQUIRED,
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
) -> list[rpki_models.ROALintFinding]:
    findings: list[rpki_models.ROALintFinding] = []
    for item in change_plan.items.all():
        if item.plan_semantic == rpki_models.ROAChangePlanItemSemantic.REPLACE:
            findings.append(
                _create_finding(
                    lint_run,
                    finding_code=LINT_RULE_PLAN_REPLACE,
                    severity=rpki_models.ReconciliationSeverity.INFO,
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
                    severity=rpki_models.ReconciliationSeverity.INFO,
                    change_plan_item=item,
                    details_json={
                        'action_type': item.action_type,
                        'plan_semantic': item.plan_semantic,
                    },
                )
            )
    return findings


def run_roa_lint(
    reconciliation_run: rpki_models.ROAReconciliationRun | int,
    *,
    change_plan: rpki_models.ROAChangePlan | int | None = None,
    run_name: str | None = None,
) -> rpki_models.ROALintRun:
    reconciliation_run = _normalize_reconciliation_run(reconciliation_run)
    change_plan = _normalize_change_plan(change_plan)
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

    all_findings: list[rpki_models.ROALintFinding] = []
    for intent_result in reconciliation_run.intent_results.select_related('roa_intent').all():
        all_findings.extend(_intent_lint_findings(lint_run, intent_result))
    for published_result in reconciliation_run.published_roa_results.all():
        all_findings.extend(_published_lint_findings(lint_run, published_result))
    if change_plan is not None:
        all_findings.extend(_plan_lint_findings(lint_run, change_plan))

    for finding in all_findings:
        severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
        finding_code_counts[finding.finding_code] = finding_code_counts.get(finding.finding_code, 0) + 1

    lint_run.status = rpki_models.ValidationRunStatus.COMPLETED
    lint_run.completed_at = timezone.now()
    lint_run.finding_count = len(all_findings)
    lint_run.info_count = severity_counts[rpki_models.ReconciliationSeverity.INFO]
    lint_run.warning_count = severity_counts[rpki_models.ReconciliationSeverity.WARNING]
    lint_run.error_count = severity_counts[rpki_models.ReconciliationSeverity.ERROR]
    lint_run.critical_count = severity_counts[rpki_models.ReconciliationSeverity.CRITICAL]
    lint_run.summary_json = {
        'severity_counts': severity_counts,
        'finding_code_counts': finding_code_counts,
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
