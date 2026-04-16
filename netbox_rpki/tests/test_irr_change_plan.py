from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import create_irr_change_plans
from netbox_rpki.tests.utils import (
    create_test_authored_as_set,
    create_test_authored_as_set_member,
    create_test_imported_irr_route_set,
    create_test_imported_irr_route_set_member,
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

    def test_create_irr_change_plans_builds_route_set_and_as_set_drafts(self):
        route_set = create_test_imported_irr_route_set(
            snapshot=self.snapshot,
            source=self.source,
            stable_key='route_set:AS64500:RS-EDGE',
            rpsl_pk='AS64500:RS-EDGE',
            set_name='AS64500:RS-EDGE',
            object_text=(
                'route-set: AS64500:RS-EDGE\n'
                'descr: Example route set\n'
                'mnt-by: LOCAL-IRR-MNT\n'
                'members: 198.51.100.0/24\n'
                'source: LOCAL-IRR\n'
            ),
        )
        create_test_imported_irr_route_set_member(
            snapshot=self.snapshot,
            source=self.source,
            parent_route_set=route_set,
            member_text='198.51.100.0/24',
            normalized_prefix='198.51.100.0/24',
        )
        create_test_irr_coordination_result(
            name='Route-Set Membership Gap',
            coordination_run=self.coordination_run,
            source=self.source,
            snapshot=self.snapshot,
            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            result_type=rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            stable_object_key='route:203.0.113.0/24AS64500|AS64500:RS-EDGE',
            summary_json={
                'route_stable_key': 'route:203.0.113.0/24AS64500',
                'route_set_name': 'AS64500:RS-EDGE',
                'route_set_stable_key': route_set.stable_key,
                'route_prefix': '203.0.113.0/24',
            },
        )
        create_test_irr_coordination_result(
            name='AS-Set Membership Gap',
            coordination_run=self.coordination_run,
            source=self.source,
            snapshot=self.snapshot,
            coordination_family=rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP,
            result_type=rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            stable_object_key='AS64500:AS-CUSTOMERS|AS64500',
            summary_json={
                'as_set_name': 'AS64500:AS-CUSTOMERS',
                'member_text': 'AS64500',
                'member_key': 'AS64500',
                'authored_as_set_id': create_test_authored_as_set(
                    name='Authored Customers',
                    organization=self.organization,
                    set_name='AS64500:AS-CUSTOMERS',
                ).pk,
            },
        )
        authored_as_set = rpki_models.AuthoredAsSet.objects.get(set_name='AS64500:AS-CUSTOMERS')
        create_test_authored_as_set_member(
            name='Authored Customer ASN',
            authored_as_set=authored_as_set,
            member_type=rpki_models.AuthoredAsSetMemberType.ASN,
            member_asn_value=64500,
        )

        plans = create_irr_change_plans(self.coordination_run)

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertTrue(plan.summary_json['previewable'])
        self.assertTrue(plan.summary_json['applyable'])
        self.assertEqual(plan.summary_json['item_counts'][rpki_models.IrrChangePlanAction.CREATE], 1)
        self.assertEqual(plan.summary_json['item_counts'][rpki_models.IrrChangePlanAction.MODIFY], 1)
        self.assertEqual(plan.summary_json['item_counts'][rpki_models.IrrChangePlanAction.NOOP], 0)
        self.assertEqual(
            plan.summary_json['family_counts'][rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP],
            1,
        )
        self.assertEqual(
            plan.summary_json['family_counts'][rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP],
            1,
        )
        items = list(plan.items.order_by('coordination_result__coordination_family', 'pk'))
        self.assertEqual([item.action for item in items], [rpki_models.IrrChangePlanAction.CREATE, rpki_models.IrrChangePlanAction.MODIFY])
        self.assertEqual(items[0].object_family, rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP)
        self.assertEqual(items[1].object_family, rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP)
        self.assertEqual(items[0].after_state_json['set_name'], 'AS64500:AS-CUSTOMERS')
        self.assertEqual(items[0].after_state_json['members'], ['AS64500'])
        self.assertEqual(items[0].request_payload_json['operation'], rpki_models.IrrChangePlanAction.CREATE)
        self.assertEqual(items[0].request_payload_json['attributes']['as-set'], 'AS64500:AS-CUSTOMERS')
        self.assertEqual(items[0].request_payload_json['attributes']['members'], ['AS64500'])
        self.assertEqual(items[1].before_state_json['set_name'], 'AS64500:RS-EDGE')
        self.assertEqual(items[1].after_state_json['members'], ['198.51.100.0/24', '203.0.113.0/24'])
        self.assertEqual(items[1].request_payload_json['operation'], rpki_models.IrrChangePlanAction.MODIFY)
        self.assertEqual(items[1].request_payload_json['attributes']['route-set'], 'AS64500:RS-EDGE')
        self.assertEqual(
            items[1].request_payload_json['attributes']['members'],
            ['198.51.100.0/24', '203.0.113.0/24'],
        )

    def test_create_irr_change_plans_builds_route_set_create_and_delete_drafts(self):
        create_test_imported_irr_route_set(
            snapshot=self.snapshot,
            source=self.source,
            stable_key='route_set:AS64500:RS-DELETE',
            rpsl_pk='AS64500:RS-DELETE',
            set_name='AS64500:RS-DELETE',
            object_text=(
                'route-set: AS64500:RS-DELETE\n'
                'descr: Example delete route set\n'
                'mnt-by: LOCAL-IRR-MNT\n'
                'members: 198.51.100.0/24\n'
                'source: LOCAL-IRR\n'
            ),
        )
        create_test_irr_coordination_result(
            name='Route-Set Create Gap',
            coordination_run=self.coordination_run,
            source=self.source,
            snapshot=self.snapshot,
            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            result_type=rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            stable_object_key='route:203.0.113.0/24AS64500|AS64500:RS-CREATE',
            summary_json={
                'route_stable_key': 'route:203.0.113.0/24AS64500',
                'route_set_name': 'AS64500:RS-CREATE',
                'route_prefix': '203.0.113.0/24',
            },
        )
        create_test_irr_coordination_result(
            name='Route-Set Delete Gap',
            coordination_run=self.coordination_run,
            source=self.source,
            snapshot=self.snapshot,
            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            result_type=rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            stable_object_key='route:198.51.100.0/24AS64500|AS64500:RS-DELETE',
            summary_json={
                'route_stable_key': 'route:198.51.100.0/24AS64500',
                'route_set_name': 'AS64500:RS-DELETE',
                'route_set_stable_key': 'route_set:AS64500:RS-DELETE',
                'route_prefix': '198.51.100.0/24',
            },
        )

        plans = create_irr_change_plans(self.coordination_run)

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        items = {
            item.after_state_json.get('set_name') or item.before_state_json.get('set_name'): item
            for item in plan.items.order_by('pk')
        }
        create_item = items['AS64500:RS-CREATE']
        delete_item = items['AS64500:RS-DELETE']
        self.assertEqual(create_item.action, rpki_models.IrrChangePlanAction.CREATE)
        self.assertEqual(create_item.after_state_json['members'], ['203.0.113.0/24'])
        self.assertEqual(create_item.request_payload_json['operation'], rpki_models.IrrChangePlanAction.CREATE)
        self.assertEqual(delete_item.action, rpki_models.IrrChangePlanAction.DELETE)
        self.assertEqual(delete_item.before_state_json['set_name'], 'AS64500:RS-DELETE')
        self.assertEqual(delete_item.after_state_json, {'target_member_text': '198.51.100.0/24', 'membership_change': 'remove'})
        self.assertEqual(delete_item.request_payload_json['operation'], rpki_models.IrrChangePlanAction.DELETE)


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
