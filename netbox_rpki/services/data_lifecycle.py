"""
Data lifecycle services: snapshot retention policy evaluation and purge execution.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

from django.db import models as db_models
from django.utils import timezone

from netbox_rpki import models as rpki_models

# ---------------------------------------------------------------------------
# Schema version for storage impact and purge run summary payloads
# ---------------------------------------------------------------------------
STORAGE_IMPACT_SCHEMA_VERSION = 1
PURGE_RUN_SUMMARY_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Snapshot family descriptors
# Each entry: (family_name, model_class, group_field, time_field, terminal_status_field)
# group_field: the FK field on the model used to group runs by parent
# time_field: the datetime field used to determine recency
# ---------------------------------------------------------------------------
_SNAPSHOT_FAMILIES: tuple[tuple, ...] = (
    ('validator_run', rpki_models.ValidationRun, 'validator_id', 'completed_at'),
    ('provider_snapshot', rpki_models.ProviderSnapshot, 'provider_account_id', 'completed_at'),
    ('telemetry_run', rpki_models.TelemetryRun, 'source_id', 'completed_at'),
    ('irr_snapshot', rpki_models.IrrSnapshot, 'source_id', 'completed_at'),
)


def _compute_keep_pks(
    model_class,
    group_field: str,
    time_field: str,
    keep_count: int | None,
    keep_days: int | None,
) -> set[int]:
    """
    Return PKs that must be retained under the given (keep_count, keep_days) constraints.

    A run is retained if EITHER:
    - It is within the most-recent ``keep_count`` completed runs for its parent, OR
    - Its ``time_field`` is within the last ``keep_days`` days.

    If neither constraint is set, all PKs are retained (no policy active).
    """
    if keep_count is None and keep_days is None:
        return set(model_class.objects.values_list('pk', flat=True))

    keep_pks: set[int] = set()

    if keep_days is not None:
        cutoff = timezone.now() - timedelta(days=keep_days)
        recent_by_age = set(
            model_class.objects.filter(**{f'{time_field}__gte': cutoff})
            .values_list('pk', flat=True)
        )
        keep_pks |= recent_by_age

    if keep_count is not None:
        group_values = (
            model_class.objects
            .filter(**{f'{group_field}__isnull': False})
            .values_list(group_field, flat=True)
            .distinct()
        )
        for group_val in group_values:
            top_pks = list(
                model_class.objects
                .filter(**{group_field: group_val})
                .order_by(f'-{time_field}', '-pk')
                .values_list('pk', flat=True)[:keep_count]
            )
            keep_pks.update(top_pks)

    return keep_pks


def _eligible_pks_for_family(
    model_class,
    group_field: str,
    time_field: str,
    keep_count: int | None,
    keep_days: int | None,
) -> set[int]:
    """Return PKs eligible for purge (i.e., not in the keep set)."""
    if keep_count is None and keep_days is None:
        return set()

    all_pks = set(model_class.objects.values_list('pk', flat=True))
    keep_pks = _compute_keep_pks(model_class, group_field, time_field, keep_count, keep_days)
    return all_pks - keep_pks


# ---------------------------------------------------------------------------
# Public service: storage impact summary
# ---------------------------------------------------------------------------

def build_snapshot_storage_impact(
    policy: rpki_models.SnapshotRetentionPolicy,
) -> dict:
    """
    Return a summary of how the policy would affect each snapshot family.

    The returned dict is safe for JSON serialisation and follows
    ``STORAGE_IMPACT_SCHEMA_VERSION``.
    """
    families = []

    for family_name, model_class, group_field, time_field in _SNAPSHOT_FAMILIES:
        keep_count = getattr(policy, f'{family_name}_keep_count')
        keep_days = getattr(policy, f'{family_name}_keep_days')

        total = model_class.objects.count()
        policy_active = keep_count is not None or keep_days is not None

        if not policy_active:
            families.append({
                'family': family_name,
                'total': total,
                'would_keep': total,
                'would_purge': 0,
                'policy_active': False,
            })
            continue

        eligible = _eligible_pks_for_family(
            model_class, group_field, time_field, keep_count, keep_days
        )
        would_purge = len(eligible)
        families.append({
            'family': family_name,
            'total': total,
            'would_keep': total - would_purge,
            'would_purge': would_purge,
            'policy_active': True,
            'keep_count': keep_count,
            'keep_days': keep_days,
        })

    return {
        'schema_version': STORAGE_IMPACT_SCHEMA_VERSION,
        'policy_id': policy.pk,
        'policy_name': policy.name,
        'enabled': policy.enabled,
        'families': families,
    }


# ---------------------------------------------------------------------------
# Public service: run purge
# ---------------------------------------------------------------------------

def run_snapshot_purge(
    policy: rpki_models.SnapshotRetentionPolicy,
    *,
    dry_run: bool = True,
) -> rpki_models.SnapshotPurgeRun:
    """
    Execute (or preview) a snapshot purge under *policy*.

    Creates and returns a :class:`~netbox_rpki.models.SnapshotPurgeRun` that
    records the outcome. When ``dry_run=True`` no records are deleted.

    Raises on unexpected error after marking the purge run as failed.
    """
    now = timezone.now()
    purge_run = rpki_models.SnapshotPurgeRun.objects.create(
        name=f'Purge {policy.name} {now:%Y-%m-%d %H:%M}',
        policy=policy,
        status=rpki_models.ValidationRunStatus.RUNNING,
        dry_run=dry_run,
        started_at=now,
    )

    summary: dict[str, dict] = {}

    try:
        for family_name, model_class, group_field, time_field in _SNAPSHOT_FAMILIES:
            keep_count = getattr(policy, f'{family_name}_keep_count')
            keep_days = getattr(policy, f'{family_name}_keep_days')

            if keep_count is None and keep_days is None:
                summary[family_name] = {'eligible': 0, 'purged': 0, 'policy_active': False}
                continue

            eligible = _eligible_pks_for_family(
                model_class, group_field, time_field, keep_count, keep_days
            )

            if dry_run or not eligible:
                purged = 0
            else:
                deleted_count, _ = model_class.objects.filter(pk__in=eligible).delete()
                purged = deleted_count

            summary[family_name] = {
                'eligible': len(eligible),
                'purged': purged,
                'policy_active': True,
                'dry_run': dry_run,
            }

        purge_run.status = rpki_models.ValidationRunStatus.COMPLETED
        purge_run.completed_at = timezone.now()
        purge_run.summary_json = {
            'schema_version': PURGE_RUN_SUMMARY_SCHEMA_VERSION,
            'families': summary,
        }
        purge_run.save()

    except Exception as exc:
        purge_run.status = rpki_models.ValidationRunStatus.FAILED
        purge_run.completed_at = timezone.now()
        purge_run.error_text = str(exc)
        purge_run.save()
        raise

    return purge_run
