"""
Approval workflow helpers for governed workflow objects.

Provides approve/secondary-approve functions for BulkIntentRun.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone

from netbox_rpki import models as rpki_models


def approve_bulk_intent_run(
    bulk_run: rpki_models.BulkIntentRun,
    *,
    approved_by: str,
) -> rpki_models.BulkIntentRun:
    """
    Mark a BulkIntentRun as approved.

    Raises ValidationError if the run is not in PENDING status.
    """
    if bulk_run.status != rpki_models.ValidationRunStatus.PENDING:
        raise ValidationError(
            f'Cannot approve a bulk intent run with status "{bulk_run.status}". '
            f'Only PENDING runs can be approved.'
        )
    bulk_run.approved_at = timezone.now()
    bulk_run.approved_by = approved_by
    bulk_run.save(update_fields=['approved_at', 'approved_by'])
    return bulk_run


def secondary_approve_bulk_intent_run(
    bulk_run: rpki_models.BulkIntentRun,
    *,
    approved_by: str,
) -> rpki_models.BulkIntentRun:
    """
    Mark a BulkIntentRun as having secondary approval.

    Raises ValidationError if:
    - The run does not require secondary approval
    - The run is not in PENDING status
    - The run has not been approved first
    """
    if not bulk_run.requires_secondary_approval:
        raise ValidationError('This bulk intent run does not require secondary approval.')
    if bulk_run.status != rpki_models.ValidationRunStatus.PENDING:
        raise ValidationError(
            f'Cannot secondary-approve a bulk intent run with status "{bulk_run.status}". '
            f'Only PENDING runs can be secondary-approved.'
        )
    if not bulk_run.approved_at:
        raise ValidationError('Primary approval must be granted before secondary approval.')
    bulk_run.secondary_approved_at = timezone.now()
    bulk_run.secondary_approved_by = approved_by
    bulk_run.save(update_fields=['secondary_approved_at', 'secondary_approved_by'])
    return bulk_run


def is_bulk_intent_run_approved(bulk_run: rpki_models.BulkIntentRun) -> bool:
    """
    Check whether a BulkIntentRun has all required approvals.
    """
    if not bulk_run.approved_at:
        return False
    if bulk_run.requires_secondary_approval and not bulk_run.secondary_approved_at:
        return False
    return True
