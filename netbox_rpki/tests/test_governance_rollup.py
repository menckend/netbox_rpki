"""
Tests for the organization governance roll-up helper.
"""
from django.test import TestCase
from django.utils import timezone

from netbox_rpki import models
from netbox_rpki.services.governance_rollup import build_organization_governance_rollup
from netbox_rpki.tests.utils import (
    create_test_organization,
    create_test_provider_account,
    create_test_roa_change_plan,
    create_test_roa_change_plan_rollback_bundle,
)


class OrganizationGovernanceRollupTest(TestCase):
    """Tests for build_organization_governance_rollup aggregate counts."""

    def setUp(self):
        self.org = create_test_organization(org_id='ROLLUP-ORG', name='Rollup Test Org')
        self.acct = create_test_provider_account(organization=self.org)

    def test_empty_organization(self):
        result = build_organization_governance_rollup(self.org)
        self.assertEqual(result['change_plans']['total'], 0)
        self.assertEqual(result['rollback_bundles']['total'], 0)
        self.assertEqual(result['bulk_intent_runs']['total'], 0)
        self.assertEqual(result['routing_intent_exceptions']['total'], 0)
        self.assertEqual(result['cross_cutting']['awaiting_approval'], 0)
        self.assertEqual(result['cross_cutting']['failed'], 0)

    def test_change_plan_counts_in_rollup(self):
        create_test_roa_change_plan(
            name='draft-plan',
            organization=self.org,
            provider_account=self.acct,
            status=models.ROAChangePlanStatus.DRAFT,
        )
        create_test_roa_change_plan(
            name='approved-plan',
            organization=self.org,
            provider_account=self.acct,
            status=models.ROAChangePlanStatus.APPROVED,
        )
        result = build_organization_governance_rollup(self.org)
        self.assertEqual(result['change_plans']['total'], 2)
        self.assertGreater(result['cross_cutting']['awaiting_approval'], 0)

    def test_bulk_intent_run_counts(self):
        models.BulkIntentRun.objects.create(
            name='pending-run',
            organization=self.org,
            status=models.ValidationRunStatus.PENDING,
        )
        models.BulkIntentRun.objects.create(
            name='completed-run',
            organization=self.org,
            status=models.ValidationRunStatus.COMPLETED,
        )
        models.BulkIntentRun.objects.create(
            name='failed-run',
            organization=self.org,
            status=models.ValidationRunStatus.FAILED,
        )
        result = build_organization_governance_rollup(self.org)
        self.assertEqual(result['bulk_intent_runs']['total'], 3)
        self.assertEqual(result['bulk_intent_runs']['awaiting_approval'], 1)
        self.assertEqual(result['bulk_intent_runs']['completed'], 1)
        self.assertEqual(result['bulk_intent_runs']['failed'], 1)
        self.assertEqual(result['cross_cutting']['failed'], 1)

    def test_bulk_intent_run_approved_pending_execution(self):
        run = models.BulkIntentRun.objects.create(
            name='approved-pending',
            organization=self.org,
            status=models.ValidationRunStatus.PENDING,
            approved_at=timezone.now(),
            approved_by='admin',
        )
        result = build_organization_governance_rollup(self.org)
        self.assertEqual(result['bulk_intent_runs']['approved_pending_execution'], 1)
        self.assertEqual(result['cross_cutting']['approved_pending_execution'], 1)

    def test_bulk_intent_run_awaiting_secondary(self):
        run = models.BulkIntentRun.objects.create(
            name='needs-secondary',
            organization=self.org,
            status=models.ValidationRunStatus.PENDING,
            requires_secondary_approval=True,
            approved_at=timezone.now(),
            approved_by='admin',
        )
        result = build_organization_governance_rollup(self.org)
        self.assertEqual(result['bulk_intent_runs']['awaiting_secondary_approval'], 1)
        self.assertEqual(result['cross_cutting']['awaiting_secondary_approval'], 1)

    def test_exception_counts(self):
        profile = models.RoutingIntentProfile.objects.create(
            name='test-profile',
            organization=self.org,
        )
        now = timezone.now()
        models.RoutingIntentException.objects.create(
            name='active-exception',
            organization=self.org,
            intent_profile=profile,
            enabled=True,
            approved_at=now,
            approved_by='admin',
            starts_at=now - timezone.timedelta(hours=1),
        )
        models.RoutingIntentException.objects.create(
            name='unapproved-exception',
            organization=self.org,
            intent_profile=profile,
            enabled=True,
        )
        models.RoutingIntentException.objects.create(
            name='expired-exception',
            organization=self.org,
            intent_profile=profile,
            enabled=True,
            starts_at=now - timezone.timedelta(hours=5),
            ends_at=now - timezone.timedelta(hours=1),
        )
        result = build_organization_governance_rollup(self.org)
        self.assertEqual(result['routing_intent_exceptions']['total'], 3)
        self.assertEqual(result['routing_intent_exceptions']['enabled'], 3)
        self.assertEqual(result['routing_intent_exceptions']['approved'], 1)
        self.assertEqual(result['routing_intent_exceptions']['unapproved'], 2)
        self.assertEqual(result['routing_intent_exceptions']['expired'], 1)
        self.assertEqual(result['routing_intent_exceptions']['active_windowed'], 1)

    def test_rollback_bundle_counts(self):
        plan = create_test_roa_change_plan(
            name='applied-plan',
            organization=self.org,
            provider_account=self.acct,
            status=models.ROAChangePlanStatus.APPLIED,
        )
        create_test_roa_change_plan_rollback_bundle(
            name='available-bundle',
            organization=self.org,
            source_plan=plan,
            status=models.RollbackBundleStatus.AVAILABLE,
        )
        result = build_organization_governance_rollup(self.org)
        self.assertEqual(result['rollback_bundles']['total'], 1)
        self.assertEqual(result['rollback_bundles']['available_not_applied'], 1)
        self.assertEqual(result['cross_cutting']['rollback_available'], 1)

    def test_cross_cutting_failed_aggregation(self):
        create_test_roa_change_plan(
            name='failed-plan',
            organization=self.org,
            provider_account=self.acct,
            status=models.ROAChangePlanStatus.FAILED,
        )
        plan2 = create_test_roa_change_plan(
            name='applied-plan-2',
            organization=self.org,
            provider_account=self.acct,
            status=models.ROAChangePlanStatus.APPLIED,
        )
        create_test_roa_change_plan_rollback_bundle(
            name='failed-bundle',
            organization=self.org,
            source_plan=plan2,
            status=models.RollbackBundleStatus.FAILED,
        )
        models.BulkIntentRun.objects.create(
            name='failed-run',
            organization=self.org,
            status=models.ValidationRunStatus.FAILED,
        )
        result = build_organization_governance_rollup(self.org)
        self.assertEqual(result['cross_cutting']['failed'], 3)

    def test_result_structure(self):
        result = build_organization_governance_rollup(self.org)
        self.assertIn('change_plans', result)
        self.assertIn('rollback_bundles', result)
        self.assertIn('bulk_intent_runs', result)
        self.assertIn('routing_intent_exceptions', result)
        self.assertIn('cross_cutting', result)
        cross = result['cross_cutting']
        self.assertIn('awaiting_approval', cross)
        self.assertIn('awaiting_secondary_approval', cross)
        self.assertIn('approved_pending_execution', cross)
        self.assertIn('applied_pending_verification', cross)
        self.assertIn('failed', cross)
        self.assertIn('rollback_available', cross)
