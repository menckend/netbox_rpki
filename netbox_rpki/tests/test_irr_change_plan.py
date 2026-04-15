from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import create_irr_change_plans
from netbox_rpki.tests.utils import (
    create_test_imported_irr_maintainer,
    create_test_irr_coordination_result,
    create_test_irr_coordination_run,
    create_test_irr_snapshot,
    create_test_irr_source,
    create_test_organization,
    create_test_roa_intent,
)


class IrrChangePlanServiceTestCase(TestCase):
    def setUp(self):
        self.organization = create_test_organization(org_id='irr-change-plan-org', name='IRR Change Plan Org')
        self.source = create_test_irr_source(
            name='Plan Source',
            slug='plan-source',
            organization=self.organization,
            write_support_mode=rpki_models.IrrWriteSupportMode.APPLY_SUPPORTED,
        )
        self.snapshot = create_test_irr_snapshot(
            name='Plan Snapshot',
            source=self.source,
        )
        self.coordination_run = create_test_irr_coordination_run(
            name='Plan Coordination',
            organization=self.organization,
            compared_sources=[self.source],
            summary_json={'latest_plan_ids': []},
        )

    def test_create_irr_change_plans_builds_source_specific_items(self):
        roa_intent = create_test_roa_intent(
            name='Intent A',
            organization=self.organization,
            prefix_cidr_text='203.0.113.0/24',
            origin_asn_value=64500,
            max_length=24,
            derived_state=rpki_models.ROAIntentDerivedState.ACTIVE,
        )
        maintainer = create_test_imported_irr_maintainer(
            snapshot=self.snapshot,
            source=self.source,
            maintainer_name='LOCAL-IRR-MNT',
        )
        create_test_irr_coordination_result(
            name='Missing Route',
            coordination_run=self.coordination_run,
            source=self.source,
            snapshot=self.snapshot,
            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_OBJECT,
            result_type=rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            stable_object_key='route:203.0.113.0/24AS64500',
            netbox_object_key='route:203.0.113.0/24AS64500',
            roa_intent=roa_intent,
        )
        create_test_irr_coordination_result(
            name='Maintainer Review',
            coordination_run=self.coordination_run,
            source=self.source,
            snapshot=self.snapshot,
            coordination_family=rpki_models.IrrCoordinationFamily.MAINTAINER_SUPPORTABILITY,
            result_type=rpki_models.IrrCoordinationResultType.UNSUPPORTED_WRITE,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            stable_object_key='route:203.0.113.0/24AS64500',
            imported_maintainer=maintainer,
        )

        plans = create_irr_change_plans(self.coordination_run)

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan.source, self.source)
        self.assertEqual(plan.summary_json['target_source'], self.source.slug)
        self.assertTrue(plan.summary_json['previewable'])
        self.assertTrue(plan.summary_json['applyable'])
        self.assertEqual(plan.summary_json['item_counts'][rpki_models.IrrChangePlanAction.CREATE], 1)
        self.assertEqual(plan.summary_json['item_counts'][rpki_models.IrrChangePlanAction.NOOP], 1)
        self.assertEqual(plan.coordination_run.summary_json['latest_plan_ids'], [plan.pk])

        create_item = plan.items.get(action=rpki_models.IrrChangePlanAction.CREATE)
        self.assertEqual(create_item.object_family, rpki_models.IrrCoordinationFamily.ROUTE_OBJECT)
        self.assertEqual(create_item.request_payload_json['operation'], rpki_models.IrrChangePlanAction.CREATE)
        self.assertEqual(create_item.request_payload_json['source_slug'], self.source.slug)

        noop_item = plan.items.get(action=rpki_models.IrrChangePlanAction.NOOP)
        self.assertEqual(noop_item.object_family, rpki_models.IrrCoordinationFamily.MAINTAINER_SUPPORTABILITY)
        self.assertEqual(noop_item.imported_maintainer, maintainer)

    def test_create_irr_change_plans_downgrades_actionable_items_when_source_is_unsupported(self):
        unsupported_source = create_test_irr_source(
            name='Unsupported Source',
            slug='unsupported-source',
            organization=self.organization,
            write_support_mode=rpki_models.IrrWriteSupportMode.UNSUPPORTED,
        )
        unsupported_snapshot = create_test_irr_snapshot(
            name='Unsupported Snapshot',
            source=unsupported_source,
        )
        coordination_run = create_test_irr_coordination_run(
            name='Unsupported Coordination',
            organization=self.organization,
            compared_sources=[unsupported_source],
        )
        roa_intent = create_test_roa_intent(
            name='Intent B',
            organization=self.organization,
            prefix_cidr_text='198.51.100.0/24',
            origin_asn_value=64501,
            max_length=24,
            derived_state=rpki_models.ROAIntentDerivedState.ACTIVE,
        )
        create_test_irr_coordination_result(
            name='Missing Unsupported Route',
            coordination_run=coordination_run,
            source=unsupported_source,
            snapshot=unsupported_snapshot,
            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_OBJECT,
            result_type=rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
            stable_object_key='route:198.51.100.0/24AS64501',
            netbox_object_key='route:198.51.100.0/24AS64501',
            roa_intent=roa_intent,
        )

        plans = create_irr_change_plans(coordination_run)

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertFalse(plan.summary_json['previewable'])
        self.assertFalse(plan.summary_json['applyable'])
        self.assertEqual(plan.summary_json['item_counts'][rpki_models.IrrChangePlanAction.NOOP], 1)
        self.assertIn('does not currently support automated IRR preview or apply', plan.summary_json['capability_warnings'][0])
        item = plan.items.get()
        self.assertEqual(item.action, rpki_models.IrrChangePlanAction.NOOP)
        self.assertEqual(item.request_payload_json, {})


class CreateIrrChangePlansCommandTestCase(TestCase):
    def setUp(self):
        self.organization = create_test_organization(org_id='irr-change-plan-cmd-org', name='IRR Change Plan Cmd Org')
        self.source = create_test_irr_source(
            name='Command Source',
            slug='command-source',
            organization=self.organization,
        )
        self.coordination_run = create_test_irr_coordination_run(
            name='Command Coordination',
            organization=self.organization,
            compared_sources=[self.source],
        )

    def test_create_irr_change_plans_command_runs_synchronously(self):
        with patch('netbox_rpki.management.commands.create_irr_change_plans.create_irr_change_plans') as create_mock:
            plan = rpki_models.IrrChangePlan(name='Plan A')
            plan.pk = 654
            create_mock.return_value = [plan]
            stdout = StringIO()

            call_command(
                'create_irr_change_plans',
                '--coordination-run',
                str(self.coordination_run.pk),
                stdout=stdout,
            )

        create_mock.assert_called_once_with(self.coordination_run)
        self.assertIn('Created 1 IRR change plans', stdout.getvalue())

    def test_create_irr_change_plans_command_enqueues_job(self):
        with patch(
            'netbox_rpki.management.commands.create_irr_change_plans.CreateIrrChangePlansJob.enqueue_for_coordination_run',
            return_value=(type('JobRef', (), {'pk': 88})(), True),
        ) as enqueue_mock:
            stdout = StringIO()
            call_command(
                'create_irr_change_plans',
                '--coordination-run',
                str(self.coordination_run.pk),
                '--enqueue',
                stdout=stdout,
            )

        enqueue_mock.assert_called_once_with(self.coordination_run)
        self.assertIn('Enqueued job 88', stdout.getvalue())
