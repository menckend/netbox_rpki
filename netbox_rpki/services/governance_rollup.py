"""
Governance roll-up helpers for organization-level audit summaries.

Provides a unified view across change plans, rollback bundles,
bulk intent runs, and routing-intent exceptions.
"""
from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.publication_state import (
    derive_change_plan_publication_state,
)
from netbox_rpki.services.bulk_intent_governance import is_bulk_intent_run_approved


def build_organization_governance_rollup(
    organization: rpki_models.Organization,
) -> dict:
    """
    Build a consolidated governance roll-up for an organization.

    Returns a dict with sections for each governed workflow family
    and cross-cutting aggregate counts.
    """
    change_plan_summary = _build_change_plan_rollup(organization)
    rollback_bundle_summary = _build_rollback_bundle_rollup(organization)
    bulk_intent_run_summary = _build_bulk_intent_run_rollup(organization)
    exception_summary = _build_exception_rollup(organization)

    return {
        'change_plans': change_plan_summary,
        'rollback_bundles': rollback_bundle_summary,
        'bulk_intent_runs': bulk_intent_run_summary,
        'routing_intent_exceptions': exception_summary,
        'cross_cutting': {
            'awaiting_approval': (
                change_plan_summary['awaiting_approval']
                + bulk_intent_run_summary['awaiting_approval']
            ),
            'awaiting_secondary_approval': (
                change_plan_summary.get('awaiting_secondary_approval', 0)
                + bulk_intent_run_summary.get('awaiting_secondary_approval', 0)
            ),
            'approved_pending_execution': (
                change_plan_summary.get('approved_pending_apply', 0)
                + bulk_intent_run_summary.get('approved_pending_execution', 0)
            ),
            'applied_pending_verification': (
                change_plan_summary.get('awaiting_verification', 0)
            ),
            'failed': (
                change_plan_summary.get('apply_failed', 0)
                + rollback_bundle_summary.get('failed', 0)
                + bulk_intent_run_summary.get('failed', 0)
            ),
            'rollback_available': rollback_bundle_summary.get('available_not_applied', 0),
        },
    }


def _build_change_plan_rollup(organization: rpki_models.Organization) -> dict:
    """Aggregate publication-state counts for ROA and ASPA change plans."""
    state_counts: dict[str, int] = {}

    for plan in rpki_models.ROAChangePlan.objects.filter(
        organization=organization,
    ).select_related('provider_account').iterator():
        result = derive_change_plan_publication_state(plan)
        state_counts[result.publication_state] = state_counts.get(result.publication_state, 0) + 1

    for plan in rpki_models.ASPAChangePlan.objects.filter(
        organization=organization,
    ).select_related('provider_account').iterator():
        result = derive_change_plan_publication_state(plan)
        state_counts[result.publication_state] = state_counts.get(result.publication_state, 0) + 1

    PS = rpki_models.PublicationState
    return {
        'total': sum(state_counts.values()),
        'by_publication_state': state_counts,
        'awaiting_approval': (
            state_counts.get(PS.DRAFT, 0)
            + state_counts.get(PS.AWAITING_SECONDARY_APPROVAL, 0)
        ),
        'awaiting_secondary_approval': state_counts.get(PS.AWAITING_SECONDARY_APPROVAL, 0),
        'approved_pending_apply': state_counts.get(PS.APPROVED_PENDING_APPLY, 0),
        'apply_in_progress': state_counts.get(PS.APPLY_IN_PROGRESS, 0),
        'awaiting_verification': state_counts.get(PS.APPLIED_AWAITING_VERIFICATION, 0),
        'verified': state_counts.get(PS.VERIFIED, 0),
        'verified_with_drift': state_counts.get(PS.VERIFIED_WITH_DRIFT, 0),
        'verification_failed': state_counts.get(PS.VERIFICATION_FAILED, 0),
        'apply_failed': state_counts.get(PS.APPLY_FAILED, 0),
        'rolled_back': state_counts.get(PS.ROLLED_BACK, 0),
    }


def _build_rollback_bundle_rollup(organization: rpki_models.Organization) -> dict:
    """Aggregate rollback bundle counts."""
    status_counts: dict[str, int] = {}

    for bundle in rpki_models.ROAChangePlanRollbackBundle.objects.filter(
        organization=organization,
    ).iterator():
        status_counts[bundle.status] = status_counts.get(bundle.status, 0) + 1

    for bundle in rpki_models.ASPAChangePlanRollbackBundle.objects.filter(
        organization=organization,
    ).iterator():
        status_counts[bundle.status] = status_counts.get(bundle.status, 0) + 1

    RBS = rpki_models.RollbackBundleStatus
    return {
        'total': sum(status_counts.values()),
        'by_workflow_status': status_counts,
        'available_not_applied': (
            status_counts.get(RBS.AVAILABLE, 0)
            + status_counts.get(RBS.APPROVED, 0)
        ),
        'applied': status_counts.get(RBS.APPLIED, 0),
        'failed': status_counts.get(RBS.FAILED, 0),
    }


def _build_bulk_intent_run_rollup(organization: rpki_models.Organization) -> dict:
    """Aggregate bulk intent run governance counts."""
    VS = rpki_models.ValidationRunStatus
    runs = rpki_models.BulkIntentRun.objects.filter(organization=organization)

    status_counts: dict[str, int] = {}
    awaiting_approval = 0
    awaiting_secondary = 0
    approved_pending_execution = 0

    for run in runs.iterator():
        status_counts[run.status] = status_counts.get(run.status, 0) + 1
        if run.status == VS.PENDING:
            if not run.approved_at:
                awaiting_approval += 1
            elif run.requires_secondary_approval and not run.secondary_approved_at:
                awaiting_secondary += 1
            elif is_bulk_intent_run_approved(run):
                approved_pending_execution += 1

    return {
        'total': sum(status_counts.values()),
        'by_status': status_counts,
        'awaiting_approval': awaiting_approval,
        'awaiting_secondary_approval': awaiting_secondary,
        'approved_pending_execution': approved_pending_execution,
        'running': status_counts.get(VS.RUNNING, 0),
        'completed': status_counts.get(VS.COMPLETED, 0),
        'failed': status_counts.get(VS.FAILED, 0),
    }


def _build_exception_rollup(organization: rpki_models.Organization) -> dict:
    """Aggregate routing-intent exception governance counts."""
    now = timezone.now()
    exceptions = rpki_models.RoutingIntentException.objects.filter(organization=organization)

    total = exceptions.count()
    enabled = exceptions.filter(enabled=True).count()
    approved = exceptions.filter(approved_at__isnull=False).count()
    unapproved = total - approved
    expired = exceptions.filter(
        Q(ends_at__isnull=False) & Q(ends_at__lt=now),
    ).count()
    active_windowed = exceptions.filter(
        Q(starts_at__isnull=False) & Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gte=now),
        enabled=True,
    ).count()

    return {
        'total': total,
        'enabled': enabled,
        'approved': approved,
        'unapproved': unapproved,
        'expired': expired,
        'active_windowed': active_windowed,
    }
