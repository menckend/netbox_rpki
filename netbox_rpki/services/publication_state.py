"""
Publication-state derivation for change plans and rollback bundles.

This module computes a normalized, read-only publication-state posture from
the combination of:

- plan workflow status
- latest provider write execution (apply mode)
- follow-up sync run and snapshot evidence
- rollback bundle status (where present)

The result distinguishes workflow state from publication verification state.
Operators should use the publication state to understand where an approved
or applied change actually stands in real publication terms.

See: devrun/work_in_progress/netbox_rpki_priority8_change_control_maturity_plan.md
     (Slice A — Publication-state semantics)
"""
from __future__ import annotations

from dataclasses import dataclass

from netbox_rpki import models as rpki_models


@dataclass(frozen=True)
class PublicationStateResult:
    """The derived publication posture of a change plan or rollback bundle."""

    publication_state: str
    workflow_status: str
    verification_detail: str
    has_followup_sync: bool
    followup_sync_status: str
    has_rollback_bundle: bool
    rollback_bundle_status: str

    def as_dict(self) -> dict:
        return {
            'publication_state': self.publication_state,
            'workflow_status': self.workflow_status,
            'verification_detail': self.verification_detail,
            'has_followup_sync': self.has_followup_sync,
            'followup_sync_status': self.followup_sync_status,
            'has_rollback_bundle': self.has_rollback_bundle,
            'rollback_bundle_status': self.rollback_bundle_status,
        }


def derive_change_plan_publication_state(
    plan: rpki_models.ROAChangePlan | rpki_models.ASPAChangePlan,
) -> PublicationStateResult:
    """Derive the publication state for a ROA or ASPA change plan."""
    status = plan.status
    is_roa = isinstance(plan, rpki_models.ROAChangePlan)
    draft_status = rpki_models.ROAChangePlanStatus.DRAFT if is_roa else rpki_models.ASPAChangePlanStatus.DRAFT
    awaiting_2nd = rpki_models.ROAChangePlanStatus.AWAITING_2ND if is_roa else rpki_models.ASPAChangePlanStatus.AWAITING_2ND
    approved_status = rpki_models.ROAChangePlanStatus.APPROVED if is_roa else rpki_models.ASPAChangePlanStatus.APPROVED
    applying_status = rpki_models.ROAChangePlanStatus.APPLYING if is_roa else rpki_models.ASPAChangePlanStatus.APPLYING
    applied_status = rpki_models.ROAChangePlanStatus.APPLIED if is_roa else rpki_models.ASPAChangePlanStatus.APPLIED
    failed_status = rpki_models.ROAChangePlanStatus.FAILED if is_roa else rpki_models.ASPAChangePlanStatus.FAILED

    # Rollback bundle state
    rollback_bundle = _get_rollback_bundle(plan)
    has_rollback = rollback_bundle is not None
    rollback_status = rollback_bundle.status if has_rollback else ''

    # Check if rolled back
    if has_rollback and rollback_status == rpki_models.RollbackBundleStatus.APPLIED:
        return PublicationStateResult(
            publication_state=rpki_models.PublicationState.ROLLED_BACK,
            workflow_status=status,
            verification_detail='Rollback bundle has been applied.',
            has_followup_sync=False,
            followup_sync_status='',
            has_rollback_bundle=True,
            rollback_bundle_status=rollback_status,
        )

    # Pre-apply states
    if status == draft_status:
        return _simple_result(rpki_models.PublicationState.DRAFT, status, has_rollback, rollback_status)

    if status == awaiting_2nd:
        return _simple_result(
            rpki_models.PublicationState.AWAITING_SECONDARY_APPROVAL, status, has_rollback, rollback_status
        )

    if status == approved_status:
        return _simple_result(
            rpki_models.PublicationState.APPROVED_PENDING_APPLY, status, has_rollback, rollback_status
        )

    if status == applying_status:
        return _simple_result(
            rpki_models.PublicationState.APPLY_IN_PROGRESS, status, has_rollback, rollback_status
        )

    if status == failed_status:
        return _simple_result(
            rpki_models.PublicationState.APPLY_FAILED, status, has_rollback, rollback_status
        )

    # Applied — derive verification state from execution evidence
    if status == applied_status:
        return _derive_applied_verification(plan, has_rollback, rollback_status)

    # Fallback for unknown status
    return _simple_result(status, status, has_rollback, rollback_status)


def derive_rollback_bundle_publication_state(
    bundle: rpki_models.ROAChangePlanRollbackBundle | rpki_models.ASPAChangePlanRollbackBundle,
) -> PublicationStateResult:
    """Derive the publication state for a rollback bundle."""
    status = bundle.status

    if status == rpki_models.RollbackBundleStatus.AVAILABLE:
        return _bundle_result(rpki_models.PublicationState.APPROVED_PENDING_APPLY, status,
                              'Rollback bundle is available but not yet approved.')

    if status == rpki_models.RollbackBundleStatus.APPROVED:
        return _bundle_result(rpki_models.PublicationState.APPROVED_PENDING_APPLY, status,
                              'Rollback bundle is approved and ready to apply.')

    if status == rpki_models.RollbackBundleStatus.APPLYING:
        return _bundle_result(rpki_models.PublicationState.APPLY_IN_PROGRESS, status,
                              'Rollback is being applied.')

    if status == rpki_models.RollbackBundleStatus.FAILED:
        return _bundle_result(rpki_models.PublicationState.APPLY_FAILED, status,
                              f'Rollback apply failed: {bundle.apply_error or "unknown error"}')

    if status == rpki_models.RollbackBundleStatus.APPLIED:
        followup_sync = (bundle.apply_response_json or {}).get('followup_sync', {})
        followup_sync_status = followup_sync.get('status', '')
        has_followup = bool(followup_sync)

        if has_followup and followup_sync_status == rpki_models.ValidationRunStatus.COMPLETED:
            return PublicationStateResult(
                publication_state=rpki_models.PublicationState.VERIFIED,
                workflow_status=status,
                verification_detail='Rollback applied and follow-up sync completed.',
                has_followup_sync=True,
                followup_sync_status=followup_sync_status,
                has_rollback_bundle=False,
                rollback_bundle_status='',
            )
        if has_followup and followup_sync_status == rpki_models.ValidationRunStatus.FAILED:
            return PublicationStateResult(
                publication_state=rpki_models.PublicationState.VERIFICATION_FAILED,
                workflow_status=status,
                verification_detail=f'Rollback applied but follow-up sync failed: {followup_sync.get("error", "")}',
                has_followup_sync=True,
                followup_sync_status=followup_sync_status,
                has_rollback_bundle=False,
                rollback_bundle_status='',
            )
        return PublicationStateResult(
            publication_state=rpki_models.PublicationState.APPLIED_AWAITING_VERIFICATION,
            workflow_status=status,
            verification_detail='Rollback applied but no follow-up sync evidence.',
            has_followup_sync=False,
            followup_sync_status='',
            has_rollback_bundle=False,
            rollback_bundle_status='',
        )

    return _bundle_result(status, status, '')


def _get_rollback_bundle(plan):
    """Return the rollback bundle for a plan, or None."""
    try:
        return plan.rollback_bundle
    except (
        rpki_models.ROAChangePlanRollbackBundle.DoesNotExist,
        rpki_models.ASPAChangePlanRollbackBundle.DoesNotExist,
    ):
        return None


def _get_latest_apply_execution(plan) -> rpki_models.ProviderWriteExecution | None:
    """Return the most recent APPLY-mode execution for a plan."""
    return (
        plan.provider_write_executions
        .filter(execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY)
        .order_by('-started_at', '-created')
        .first()
    )


def _derive_applied_verification(plan, has_rollback: bool, rollback_status: str) -> PublicationStateResult:
    """
    For an APPLIED plan, determine the verification posture from the
    latest apply execution and its follow-up sync evidence.
    """
    execution = _get_latest_apply_execution(plan)

    if execution is None:
        return PublicationStateResult(
            publication_state=rpki_models.PublicationState.APPLIED_AWAITING_VERIFICATION,
            workflow_status=plan.status,
            verification_detail='Plan is applied but no apply execution record found.',
            has_followup_sync=False,
            followup_sync_status='',
            has_rollback_bundle=has_rollback,
            rollback_bundle_status=rollback_status,
        )

    has_followup_sync = execution.followup_sync_run_id is not None
    followup_sync_status = ''

    if has_followup_sync:
        followup_sync_status = execution.followup_sync_run.status

    response = execution.response_payload_json or {}
    followup_sync_json = response.get('followup_sync', {})

    # If the execution itself failed (e.g., followup sync failed but plan still APPLIED)
    if execution.status == rpki_models.ValidationRunStatus.FAILED:
        return PublicationStateResult(
            publication_state=rpki_models.PublicationState.VERIFICATION_FAILED,
            workflow_status=plan.status,
            verification_detail=f'Apply execution completed with errors: {execution.error or "unknown"}',
            has_followup_sync=has_followup_sync,
            followup_sync_status=followup_sync_status or followup_sync_json.get('status', ''),
            has_rollback_bundle=has_rollback,
            rollback_bundle_status=rollback_status,
        )

    # Execution completed — check follow-up sync evidence
    if has_followup_sync and followup_sync_status == rpki_models.ValidationRunStatus.COMPLETED:
        # Follow-up sync succeeded — check for drift
        followup_snapshot = execution.followup_provider_snapshot
        if followup_snapshot is not None:
            drift = _check_snapshot_drift(plan, followup_snapshot)
            if drift:
                return PublicationStateResult(
                    publication_state=rpki_models.PublicationState.VERIFIED_WITH_DRIFT,
                    workflow_status=plan.status,
                    verification_detail=drift,
                    has_followup_sync=True,
                    followup_sync_status=followup_sync_status,
                    has_rollback_bundle=has_rollback,
                    rollback_bundle_status=rollback_status,
                )
        return PublicationStateResult(
            publication_state=rpki_models.PublicationState.VERIFIED,
            workflow_status=plan.status,
            verification_detail='Apply execution completed and follow-up sync verified.',
            has_followup_sync=True,
            followup_sync_status=followup_sync_status,
            has_rollback_bundle=has_rollback,
            rollback_bundle_status=rollback_status,
        )

    # Follow-up sync failed
    if has_followup_sync and followup_sync_status == rpki_models.ValidationRunStatus.FAILED:
        return PublicationStateResult(
            publication_state=rpki_models.PublicationState.VERIFICATION_FAILED,
            workflow_status=plan.status,
            verification_detail=f'Follow-up sync failed: {followup_sync_json.get("error", execution.error or "")}',
            has_followup_sync=True,
            followup_sync_status=followup_sync_status,
            has_rollback_bundle=has_rollback,
            rollback_bundle_status=rollback_status,
        )

    # Followup sync recorded in JSON but not linked (edge case)
    if not has_followup_sync and followup_sync_json:
        json_status = followup_sync_json.get('status', '')
        if json_status == rpki_models.ValidationRunStatus.FAILED:
            return PublicationStateResult(
                publication_state=rpki_models.PublicationState.VERIFICATION_FAILED,
                workflow_status=plan.status,
                verification_detail=f'Follow-up sync failed: {followup_sync_json.get("error", "")}',
                has_followup_sync=False,
                followup_sync_status=json_status,
                has_rollback_bundle=has_rollback,
                rollback_bundle_status=rollback_status,
            )

    # No follow-up sync evidence at all
    return PublicationStateResult(
        publication_state=rpki_models.PublicationState.APPLIED_AWAITING_VERIFICATION,
        workflow_status=plan.status,
        verification_detail='Apply execution completed but no follow-up sync evidence.',
        has_followup_sync=has_followup_sync,
        followup_sync_status=followup_sync_status,
        has_rollback_bundle=has_rollback,
        rollback_bundle_status=rollback_status,
    )


def _check_snapshot_drift(plan, followup_snapshot) -> str:
    """
    Compare the plan's source snapshot with the follow-up snapshot to detect drift.

    Returns an empty string if no drift is detected, or a description of the drift.

    Currently checks whether a newer snapshot exists for the same provider account
    that was not produced by this plan's apply execution. This is a lightweight
    heuristic; more sophisticated comparison (e.g., ROA-level diff) can be added later.
    """
    if plan.provider_account_id is None:
        return ''

    newer_snapshots = rpki_models.ProviderSnapshot.objects.filter(
        provider_account_id=plan.provider_account_id,
        created__gt=followup_snapshot.created,
    ).exclude(pk=followup_snapshot.pk)

    if newer_snapshots.exists():
        count = newer_snapshots.count()
        return (
            f'{count} newer snapshot(s) exist for the same provider account since the '
            f'follow-up verification snapshot. The current provider state may have drifted.'
        )

    return ''


def _simple_result(
    publication_state: str,
    workflow_status: str,
    has_rollback: bool,
    rollback_status: str,
) -> PublicationStateResult:
    return PublicationStateResult(
        publication_state=publication_state,
        workflow_status=workflow_status,
        verification_detail='',
        has_followup_sync=False,
        followup_sync_status='',
        has_rollback_bundle=has_rollback,
        rollback_bundle_status=rollback_status,
    )


def _bundle_result(
    publication_state: str,
    workflow_status: str,
    verification_detail: str,
) -> PublicationStateResult:
    return PublicationStateResult(
        publication_state=publication_state,
        workflow_status=workflow_status,
        verification_detail=verification_detail,
        has_followup_sync=False,
        followup_sync_status='',
        has_rollback_bundle=False,
        rollback_bundle_status='',
    )
