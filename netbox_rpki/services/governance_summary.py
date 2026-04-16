"""
Governance dashboard summary helpers for change plans and rollback bundles.

Provides aggregate counts of plans and bundles by publication state,
useful for organization-level dashboards and operator overviews.
"""
from __future__ import annotations

from netbox_rpki import models as rpki_models
from netbox_rpki.services.publication_state import (
    derive_change_plan_publication_state,
    derive_rollback_bundle_publication_state,
)


def build_change_plan_governance_summary(
    organization: rpki_models.Organization,
) -> dict:
    """
    Build a governance summary for all ROA and ASPA change plans
    belonging to an organization.

    Returns a dict with counts by publication state.
    """
    roa_plans = rpki_models.ROAChangePlan.objects.filter(organization=organization)
    aspa_plans = rpki_models.ASPAChangePlan.objects.filter(organization=organization)

    state_counts: dict[str, int] = {}

    for plan in roa_plans.select_related(
        'provider_account',
    ).iterator():
        result = derive_change_plan_publication_state(plan)
        state_counts[result.publication_state] = state_counts.get(result.publication_state, 0) + 1

    for plan in aspa_plans.select_related(
        'provider_account',
    ).iterator():
        result = derive_change_plan_publication_state(plan)
        state_counts[result.publication_state] = state_counts.get(result.publication_state, 0) + 1

    return {
        'total_plans': sum(state_counts.values()),
        'by_publication_state': state_counts,
        'awaiting_approval': (
            state_counts.get(rpki_models.PublicationState.DRAFT, 0)
            + state_counts.get(rpki_models.PublicationState.AWAITING_SECONDARY_APPROVAL, 0)
        ),
        'approved_pending_apply': state_counts.get(rpki_models.PublicationState.APPROVED_PENDING_APPLY, 0),
        'apply_in_progress': state_counts.get(rpki_models.PublicationState.APPLY_IN_PROGRESS, 0),
        'awaiting_verification': state_counts.get(rpki_models.PublicationState.APPLIED_AWAITING_VERIFICATION, 0),
        'verified': state_counts.get(rpki_models.PublicationState.VERIFIED, 0),
        'verified_with_drift': state_counts.get(rpki_models.PublicationState.VERIFIED_WITH_DRIFT, 0),
        'verification_failed': state_counts.get(rpki_models.PublicationState.VERIFICATION_FAILED, 0),
        'apply_failed': state_counts.get(rpki_models.PublicationState.APPLY_FAILED, 0),
        'rolled_back': state_counts.get(rpki_models.PublicationState.ROLLED_BACK, 0),
    }


def build_rollback_bundle_governance_summary(
    organization: rpki_models.Organization,
) -> dict:
    """
    Build a governance summary for all rollback bundles belonging
    to an organization.

    Returns a dict with counts by publication state.
    """
    roa_bundles = rpki_models.ROAChangePlanRollbackBundle.objects.filter(organization=organization)
    aspa_bundles = rpki_models.ASPAChangePlanRollbackBundle.objects.filter(organization=organization)

    state_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    for bundle in roa_bundles.iterator():
        result = derive_rollback_bundle_publication_state(bundle)
        state_counts[result.publication_state] = state_counts.get(result.publication_state, 0) + 1
        status_counts[bundle.status] = status_counts.get(bundle.status, 0) + 1

    for bundle in aspa_bundles.iterator():
        result = derive_rollback_bundle_publication_state(bundle)
        state_counts[result.publication_state] = state_counts.get(result.publication_state, 0) + 1
        status_counts[bundle.status] = status_counts.get(bundle.status, 0) + 1

    return {
        'total_bundles': sum(state_counts.values()),
        'by_publication_state': state_counts,
        'by_workflow_status': status_counts,
        'available_not_approved': status_counts.get(rpki_models.RollbackBundleStatus.AVAILABLE, 0),
        'approved_pending_apply': status_counts.get(rpki_models.RollbackBundleStatus.APPROVED, 0),
        'applied': status_counts.get(rpki_models.RollbackBundleStatus.APPLIED, 0),
        'failed': status_counts.get(rpki_models.RollbackBundleStatus.FAILED, 0),
    }
