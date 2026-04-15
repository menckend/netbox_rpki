"""
Tests for BulkIntentRun governance fields, approval workflow, and validation.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from netbox_rpki import models
from netbox_rpki.services.bulk_intent_governance import (
    approve_bulk_intent_run,
    secondary_approve_bulk_intent_run,
    is_bulk_intent_run_approved,
)


class BulkIntentRunGovernanceFieldsTest(TestCase):
    """Tests for governance field defaults and has_governance_metadata property."""

    def setUp(self):
        self.org = models.Organization.objects.create(
            name='Test Org',
            org_id='TEST-ORG',
        )

    def _make_run(self, **kwargs):
        defaults = dict(
            name='test-run',
            organization=self.org,
        )
        defaults.update(kwargs)
        return models.BulkIntentRun.objects.create(**defaults)

    def test_governance_defaults(self):
        run = self._make_run()
        self.assertFalse(run.requires_secondary_approval)
        self.assertEqual(run.ticket_reference, '')
        self.assertEqual(run.change_reference, '')
        self.assertIsNone(run.maintenance_window_start)
        self.assertIsNone(run.maintenance_window_end)
        self.assertIsNone(run.approved_at)
        self.assertEqual(run.approved_by, '')
        self.assertIsNone(run.secondary_approved_at)
        self.assertEqual(run.secondary_approved_by, '')
        self.assertEqual(run.requested_by, '')

    def test_has_governance_metadata_empty(self):
        run = self._make_run()
        self.assertFalse(run.has_governance_metadata)

    def test_has_governance_metadata_with_ticket(self):
        run = self._make_run(ticket_reference='CHG-001')
        self.assertTrue(run.has_governance_metadata)

    def test_has_governance_metadata_with_change_reference(self):
        run = self._make_run(change_reference='REF-001')
        self.assertTrue(run.has_governance_metadata)

    def test_has_governance_metadata_with_maintenance_window(self):
        now = timezone.now()
        run = self._make_run(maintenance_window_start=now)
        self.assertTrue(run.has_governance_metadata)

    def test_has_governance_metadata_with_approved_at(self):
        run = self._make_run(approved_at=timezone.now())
        self.assertTrue(run.has_governance_metadata)

    def test_has_governance_metadata_with_requested_by(self):
        run = self._make_run(requested_by='admin')
        self.assertTrue(run.has_governance_metadata)


class BulkIntentRunMaintenanceWindowValidationTest(TestCase):
    """Tests for maintenance window DB constraint and model clean()."""

    def setUp(self):
        self.org = models.Organization.objects.create(
            name='Test Org MW',
            org_id='TEST-MW',
        )

    def _make_run(self, **kwargs):
        defaults = dict(
            name='mw-test-run',
            organization=self.org,
        )
        defaults.update(kwargs)
        return models.BulkIntentRun(**defaults)

    def test_valid_maintenance_window(self):
        now = timezone.now()
        run = self._make_run(
            maintenance_window_start=now,
            maintenance_window_end=now + timezone.timedelta(hours=2),
        )
        run.full_clean()
        run.save()
        self.assertIsNotNone(run.pk)

    def test_maintenance_window_end_before_start_fails_clean(self):
        now = timezone.now()
        run = self._make_run(
            maintenance_window_start=now,
            maintenance_window_end=now - timezone.timedelta(hours=1),
        )
        with self.assertRaises(ValidationError):
            run.full_clean()

    def test_maintenance_window_same_start_end_is_valid(self):
        now = timezone.now()
        run = self._make_run(
            maintenance_window_start=now,
            maintenance_window_end=now,
        )
        run.full_clean()
        run.save()
        self.assertIsNotNone(run.pk)


class BulkIntentRunRequiresSecondaryApprovalLockTest(TestCase):
    """Tests that requires_secondary_approval cannot be changed after leaving PENDING."""

    def setUp(self):
        self.org = models.Organization.objects.create(
            name='Test Org Lock',
            org_id='TEST-LOCK',
        )

    def test_can_change_secondary_approval_while_pending(self):
        run = models.BulkIntentRun.objects.create(
            name='pending-run',
            organization=self.org,
            status=models.ValidationRunStatus.PENDING,
        )
        run.requires_secondary_approval = True
        run.full_clean()

    def test_cannot_change_secondary_approval_after_running(self):
        run = models.BulkIntentRun.objects.create(
            name='running-run',
            organization=self.org,
            status=models.ValidationRunStatus.RUNNING,
        )
        run.requires_secondary_approval = True
        with self.assertRaises(ValidationError) as ctx:
            run.full_clean()
        self.assertIn('requires_secondary_approval', ctx.exception.message_dict)


class BulkIntentRunApprovalWorkflowTest(TestCase):
    """Tests for approval and secondary approval service functions."""

    def setUp(self):
        self.org = models.Organization.objects.create(
            name='Test Org Approve',
            org_id='TEST-APPROVE',
        )

    def _make_pending_run(self, **kwargs):
        defaults = dict(
            name='approval-run',
            organization=self.org,
            status=models.ValidationRunStatus.PENDING,
        )
        defaults.update(kwargs)
        return models.BulkIntentRun.objects.create(**defaults)

    def test_approve_pending_run(self):
        run = self._make_pending_run()
        result = approve_bulk_intent_run(run, approved_by='admin')
        run.refresh_from_db()
        self.assertIsNotNone(run.approved_at)
        self.assertEqual(run.approved_by, 'admin')

    def test_approve_running_run_fails(self):
        run = self._make_pending_run()
        run.status = models.ValidationRunStatus.RUNNING
        run.save(update_fields=['status'])
        with self.assertRaises(ValidationError):
            approve_bulk_intent_run(run, approved_by='admin')

    def test_secondary_approve_pending_run(self):
        run = self._make_pending_run(requires_secondary_approval=True)
        approve_bulk_intent_run(run, approved_by='admin1')
        secondary_approve_bulk_intent_run(run, approved_by='admin2')
        run.refresh_from_db()
        self.assertIsNotNone(run.secondary_approved_at)
        self.assertEqual(run.secondary_approved_by, 'admin2')

    def test_secondary_approve_without_primary_fails(self):
        run = self._make_pending_run(requires_secondary_approval=True)
        with self.assertRaises(ValidationError):
            secondary_approve_bulk_intent_run(run, approved_by='admin2')

    def test_secondary_approve_without_requirement_fails(self):
        run = self._make_pending_run(requires_secondary_approval=False)
        approve_bulk_intent_run(run, approved_by='admin')
        with self.assertRaises(ValidationError):
            secondary_approve_bulk_intent_run(run, approved_by='admin2')

    def test_is_approved_no_approval(self):
        run = self._make_pending_run()
        self.assertFalse(is_bulk_intent_run_approved(run))

    def test_is_approved_with_approval(self):
        run = self._make_pending_run()
        approve_bulk_intent_run(run, approved_by='admin')
        self.assertTrue(is_bulk_intent_run_approved(run))

    def test_is_approved_requires_secondary_not_yet(self):
        run = self._make_pending_run(requires_secondary_approval=True)
        approve_bulk_intent_run(run, approved_by='admin')
        self.assertFalse(is_bulk_intent_run_approved(run))

    def test_is_approved_with_both_approvals(self):
        run = self._make_pending_run(requires_secondary_approval=True)
        approve_bulk_intent_run(run, approved_by='admin1')
        secondary_approve_bulk_intent_run(run, approved_by='admin2')
        self.assertTrue(is_bulk_intent_run_approved(run))
