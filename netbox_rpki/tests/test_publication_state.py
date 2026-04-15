"""Tests for publication-state derivation (Slice A)."""
from django.test import TestCase
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.publication_state import (
    PublicationStateResult,
    derive_change_plan_publication_state,
    derive_rollback_bundle_publication_state,
)
from netbox_rpki.tests.utils import (
    create_test_organization,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_provider_sync_run,
    create_test_provider_write_execution,
    create_test_roa_change_plan,
)


class ROAChangePlanPublicationStateTest(TestCase):
    """Publication-state derivation for ROAChangePlan instances."""

    def setUp(self):
        self.org = create_test_organization(org_id='pub-org', name='Pub Org')
        self.acct = create_test_provider_account(organization=self.org)
        self.snapshot = create_test_provider_snapshot(organization=self.org, provider_account=self.acct)

    def _make_plan(self, status=None, **kwargs):
        return create_test_roa_change_plan(
            organization=self.org,
            provider_account=self.acct,
            provider_snapshot=self.snapshot,
            status=status or rpki_models.ROAChangePlanStatus.DRAFT,
            **kwargs,
        )

    # --- Pre-apply states ---

    def test_draft(self):
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.DRAFT)
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.DRAFT)
        self.assertFalse(result.has_rollback_bundle)

    def test_awaiting_secondary_approval(self):
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.AWAITING_2ND)
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.AWAITING_SECONDARY_APPROVAL)

    def test_approved(self):
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPROVED)
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPROVED_PENDING_APPLY)

    def test_applying(self):
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLYING)
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPLY_IN_PROGRESS)

    def test_failed(self):
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.FAILED)
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPLY_FAILED)

    # --- Applied states ---

    def test_applied_no_execution(self):
        """Applied plan with no execution record falls to awaiting verification."""
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLIED)
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPLIED_AWAITING_VERIFICATION)
        self.assertFalse(result.has_followup_sync)

    def test_applied_with_completed_followup_sync(self):
        """Applied plan with a completed followup sync is VERIFIED."""
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLIED)
        sync_run = create_test_provider_sync_run(
            organization=self.org,
            provider_account=self.acct,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_snapshot = create_test_provider_snapshot(
            name='Followup Snapshot',
            organization=self.org,
            provider_account=self.acct,
        )
        create_test_provider_write_execution(
            name='Apply Execution',
            organization=self.org,
            provider_account=self.acct,
            change_plan=plan,
            execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            started_at=timezone.now(),
            followup_sync_run=sync_run,
            followup_provider_snapshot=followup_snapshot,
        )
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.VERIFIED)
        self.assertTrue(result.has_followup_sync)
        self.assertEqual(result.followup_sync_status, rpki_models.ValidationRunStatus.COMPLETED)

    def test_applied_with_failed_followup_sync(self):
        """Applied plan with a failed followup sync is VERIFICATION_FAILED."""
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLIED)
        sync_run = create_test_provider_sync_run(
            organization=self.org,
            provider_account=self.acct,
            status=rpki_models.ValidationRunStatus.FAILED,
        )
        create_test_provider_write_execution(
            name='Apply Execution Failed Sync',
            organization=self.org,
            provider_account=self.acct,
            change_plan=plan,
            execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            started_at=timezone.now(),
            followup_sync_run=sync_run,
        )
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.VERIFICATION_FAILED)
        self.assertTrue(result.has_followup_sync)

    def test_applied_with_failed_execution(self):
        """Applied plan where the execution itself failed."""
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLIED)
        create_test_provider_write_execution(
            name='Failed Apply Execution',
            organization=self.org,
            provider_account=self.acct,
            change_plan=plan,
            execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
            status=rpki_models.ValidationRunStatus.FAILED,
            started_at=timezone.now(),
            error='Provider returned 500',
        )
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.VERIFICATION_FAILED)

    def test_applied_no_followup_sync(self):
        """Applied plan with execution but no followup sync is awaiting verification."""
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLIED)
        create_test_provider_write_execution(
            name='Apply No Followup',
            organization=self.org,
            provider_account=self.acct,
            change_plan=plan,
            execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            started_at=timezone.now(),
        )
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPLIED_AWAITING_VERIFICATION)

    def test_applied_with_drift(self):
        """Applied plan verified, but a newer snapshot exists → VERIFIED_WITH_DRIFT."""
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLIED)
        sync_run = create_test_provider_sync_run(
            organization=self.org,
            provider_account=self.acct,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_snapshot = create_test_provider_snapshot(
            name='Followup Snapshot Drift',
            organization=self.org,
            provider_account=self.acct,
        )
        create_test_provider_write_execution(
            name='Apply Execution Drift',
            organization=self.org,
            provider_account=self.acct,
            change_plan=plan,
            execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            started_at=timezone.now(),
            followup_sync_run=sync_run,
            followup_provider_snapshot=followup_snapshot,
        )
        # Create a newer snapshot to trigger drift detection
        create_test_provider_snapshot(
            name='Newer Snapshot',
            organization=self.org,
            provider_account=self.acct,
        )
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.VERIFIED_WITH_DRIFT)
        self.assertIn('newer snapshot', result.verification_detail.lower())

    def test_applied_with_json_followup_sync_failed(self):
        """Applied plan with followup_sync in JSON but not linked, and status is failed."""
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLIED)
        create_test_provider_write_execution(
            name='Apply With JSON Sync',
            organization=self.org,
            provider_account=self.acct,
            change_plan=plan,
            execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            started_at=timezone.now(),
            response_payload_json={
                'followup_sync': {
                    'status': rpki_models.ValidationRunStatus.FAILED,
                    'error': 'Connection timeout',
                },
            },
        )
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.VERIFICATION_FAILED)
        self.assertIn('Connection timeout', result.verification_detail)

    # --- Rollback bundle states ---

    def test_rolled_back(self):
        """Plan with an applied rollback bundle is ROLLED_BACK."""
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLIED)
        rpki_models.ROAChangePlanRollbackBundle.objects.create(
            name='Rollback Bundle 1',
            organization=self.org,
            source_plan=plan,
            rollback_delta_json={'items': []},
            status=rpki_models.RollbackBundleStatus.APPLIED,
        )
        result = derive_change_plan_publication_state(plan)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.ROLLED_BACK)
        self.assertTrue(result.has_rollback_bundle)
        self.assertEqual(result.rollback_bundle_status, rpki_models.RollbackBundleStatus.APPLIED)

    def test_applied_with_available_rollback(self):
        """Applied plan with available rollback bundle still shows verification state."""
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLIED)
        rpki_models.ROAChangePlanRollbackBundle.objects.create(
            name='Rollback Bundle Available',
            organization=self.org,
            source_plan=plan,
            rollback_delta_json={'items': []},
            status=rpki_models.RollbackBundleStatus.AVAILABLE,
        )
        result = derive_change_plan_publication_state(plan)
        # Should show awaiting verification (no execution evidence), not rolled back
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPLIED_AWAITING_VERIFICATION)
        self.assertTrue(result.has_rollback_bundle)

    # --- Result contract ---

    def test_as_dict(self):
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.DRAFT)
        result = derive_change_plan_publication_state(plan)
        d = result.as_dict()
        self.assertIn('publication_state', d)
        self.assertIn('workflow_status', d)
        self.assertIn('verification_detail', d)
        self.assertIn('has_followup_sync', d)
        self.assertIn('followup_sync_status', d)
        self.assertIn('has_rollback_bundle', d)
        self.assertIn('rollback_bundle_status', d)

    def test_result_is_frozen(self):
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.DRAFT)
        result = derive_change_plan_publication_state(plan)
        with self.assertRaises(AttributeError):
            result.publication_state = 'something_else'

    def test_preview_execution_is_ignored(self):
        """Preview executions should not affect publication state."""
        plan = self._make_plan(status=rpki_models.ROAChangePlanStatus.APPLIED)
        sync_run = create_test_provider_sync_run(
            organization=self.org,
            provider_account=self.acct,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        # Only a PREVIEW execution, no APPLY execution
        create_test_provider_write_execution(
            name='Preview Execution',
            organization=self.org,
            provider_account=self.acct,
            change_plan=plan,
            execution_mode=rpki_models.ProviderWriteExecutionMode.PREVIEW,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            started_at=timezone.now(),
            followup_sync_run=sync_run,
        )
        result = derive_change_plan_publication_state(plan)
        # No apply execution → awaiting verification
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPLIED_AWAITING_VERIFICATION)


class RollbackBundlePublicationStateTest(TestCase):
    """Publication-state derivation for rollback bundle instances."""

    def setUp(self):
        self.org = create_test_organization(org_id='rb-org', name='RB Org')
        self.acct = create_test_provider_account(organization=self.org)
        self.plan = create_test_roa_change_plan(
            organization=self.org,
            provider_account=self.acct,
            status=rpki_models.ROAChangePlanStatus.APPLIED,
        )

    def _make_bundle(self, status=None, **kwargs):
        return rpki_models.ROAChangePlanRollbackBundle.objects.create(
            name='Rollback Bundle',
            organization=self.org,
            source_plan=self.plan,
            rollback_delta_json={'items': []},
            status=status or rpki_models.RollbackBundleStatus.AVAILABLE,
            **kwargs,
        )

    def test_available(self):
        bundle = self._make_bundle(status=rpki_models.RollbackBundleStatus.AVAILABLE)
        result = derive_rollback_bundle_publication_state(bundle)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPROVED_PENDING_APPLY)

    def test_approved(self):
        bundle = self._make_bundle(status=rpki_models.RollbackBundleStatus.APPROVED)
        result = derive_rollback_bundle_publication_state(bundle)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPROVED_PENDING_APPLY)

    def test_applying(self):
        bundle = self._make_bundle(status=rpki_models.RollbackBundleStatus.APPLYING)
        result = derive_rollback_bundle_publication_state(bundle)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPLY_IN_PROGRESS)

    def test_failed(self):
        bundle = self._make_bundle(
            status=rpki_models.RollbackBundleStatus.FAILED,
            apply_error='Provider returned 503',
        )
        result = derive_rollback_bundle_publication_state(bundle)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPLY_FAILED)
        self.assertIn('503', result.verification_detail)

    def test_applied_no_followup(self):
        bundle = self._make_bundle(status=rpki_models.RollbackBundleStatus.APPLIED)
        result = derive_rollback_bundle_publication_state(bundle)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.APPLIED_AWAITING_VERIFICATION)

    def test_applied_with_completed_followup(self):
        bundle = self._make_bundle(
            status=rpki_models.RollbackBundleStatus.APPLIED,
            apply_response_json={
                'followup_sync': {
                    'status': rpki_models.ValidationRunStatus.COMPLETED,
                },
            },
        )
        result = derive_rollback_bundle_publication_state(bundle)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.VERIFIED)

    def test_applied_with_failed_followup(self):
        bundle = self._make_bundle(
            status=rpki_models.RollbackBundleStatus.APPLIED,
            apply_response_json={
                'followup_sync': {
                    'status': rpki_models.ValidationRunStatus.FAILED,
                    'error': 'Sync timeout',
                },
            },
        )
        result = derive_rollback_bundle_publication_state(bundle)
        self.assertEqual(result.publication_state, rpki_models.PublicationState.VERIFICATION_FAILED)
        self.assertIn('Sync timeout', result.verification_detail)
