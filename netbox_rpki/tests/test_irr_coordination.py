from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import run_irr_coordination
from netbox_rpki.tests.utils import (
    create_test_irr_snapshot,
    create_test_irr_source,
    create_test_imported_irr_as_set,
    create_test_imported_irr_as_set_member,
    create_test_imported_irr_aut_num,
    create_test_imported_irr_maintainer,
    create_test_imported_irr_route_object,
    create_test_imported_irr_route_set,
    create_test_imported_irr_route_set_member,
    create_test_organization,
    create_test_roa_intent,
)


class IrrCoordinationServiceTestCase(TestCase):
    def setUp(self):
        self.organization = create_test_organization(org_id='irr-coordination-org', name='IRR Coordination Org')
        self.source_a = create_test_irr_source(
            name='Local IRR A',
            slug='local-irr-a',
            organization=self.organization,
        )
        self.snapshot_a = create_test_irr_snapshot(
            name='Snapshot A',
            source=self.source_a,
            completed_at=None,
        )

    def test_run_irr_coordination_matches_and_flags_context(self):
        roa_intent = create_test_roa_intent(
            name='Intent A',
            organization=self.organization,
            prefix_cidr_text='203.0.113.0/24',
            origin_asn_value=64500,
            max_length=24,
            derived_state=rpki_models.ROAIntentDerivedState.ACTIVE,
        )
        imported_route = create_test_imported_irr_route_object(
            snapshot=self.snapshot_a,
            source=self.source_a,
            stable_key='route:203.0.113.0/24AS64500',
            rpsl_pk='203.0.113.0/24AS64500',
            prefix='203.0.113.0/24',
            origin_asn='AS64500',
            route_set_names_json=['AS64500:RS-LOCAL-EDGE'],
            maintainer_names_json=['LOCAL-IRR-MNT'],
        )
        imported_route_set = create_test_imported_irr_route_set(
            snapshot=self.snapshot_a,
            source=self.source_a,
            stable_key='route_set:AS64500:RS-LOCAL-EDGE',
            rpsl_pk='AS64500:RS-LOCAL-EDGE',
            set_name='AS64500:RS-LOCAL-EDGE',
        )
        imported_route_set_member = create_test_imported_irr_route_set_member(
            snapshot=self.snapshot_a,
            source=self.source_a,
            parent_route_set=imported_route_set,
            stable_key='route_set:AS64500:RS-LOCAL-EDGE|203.0.113.0/24',
            rpsl_pk='AS64500:RS-LOCAL-EDGE|203.0.113.0/24',
            member_text='203.0.113.0/24',
            normalized_prefix='203.0.113.0/24',
        )
        imported_as_set = create_test_imported_irr_as_set(
            snapshot=self.snapshot_a,
            source=self.source_a,
            stable_key='as_set:AS64500:AS-LOCAL-CUSTOMERS',
            rpsl_pk='AS64500:AS-LOCAL-CUSTOMERS',
            set_name='AS64500:AS-LOCAL-CUSTOMERS',
        )
        imported_as_set_member = create_test_imported_irr_as_set_member(
            snapshot=self.snapshot_a,
            source=self.source_a,
            parent_as_set=imported_as_set,
            stable_key='as_set:AS64500:AS-LOCAL-CUSTOMERS|AS64500',
            rpsl_pk='AS64500:AS-LOCAL-CUSTOMERS|AS64500',
            member_text='AS64500',
            normalized_asn='AS64500',
        )
        imported_aut_num = create_test_imported_irr_aut_num(
            snapshot=self.snapshot_a,
            source=self.source_a,
            asn='AS64500',
        )
        imported_maintainer = create_test_imported_irr_maintainer(
            snapshot=self.snapshot_a,
            source=self.source_a,
            maintainer_name='LOCAL-IRR-MNT',
        )

        coordination_run = run_irr_coordination(self.organization)

        self.assertEqual(coordination_run.status, rpki_models.IrrCoordinationRunStatus.COMPLETED)
        self.assertEqual(coordination_run.summary_json['source_count'], 1)
        self.assertEqual(
            coordination_run.summary_json['result_counts'][rpki_models.IrrCoordinationFamily.ROUTE_OBJECT][rpki_models.IrrCoordinationResultType.MATCH],
            1,
        )
        match_result = rpki_models.IrrCoordinationResult.objects.get(
            coordination_run=coordination_run,
            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_OBJECT,
            result_type=rpki_models.IrrCoordinationResultType.MATCH,
        )
        self.assertEqual(match_result.roa_intent, roa_intent)
        self.assertEqual(match_result.imported_route_object, imported_route)

        route_set_result = rpki_models.IrrCoordinationResult.objects.get(
            coordination_run=coordination_run,
            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            result_type=rpki_models.IrrCoordinationResultType.MATCH,
        )
        self.assertEqual(route_set_result.roa_intent, roa_intent)
        self.assertEqual(route_set_result.imported_route_object, imported_route)
        self.assertEqual(route_set_result.summary_json['route_set_stable_key'], imported_route_set.stable_key)
        self.assertEqual(route_set_result.summary_json['membership_stable_key'], imported_route_set_member.stable_key)

        as_set_result = rpki_models.IrrCoordinationResult.objects.get(
            coordination_run=coordination_run,
            coordination_family=rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP,
            result_type=rpki_models.IrrCoordinationResultType.MATCH,
        )
        self.assertEqual(as_set_result.roa_intent, roa_intent)
        self.assertEqual(as_set_result.imported_route_object, imported_route)
        self.assertEqual(as_set_result.summary_json['as_set_stable_key'], imported_as_set.stable_key)
        self.assertEqual(as_set_result.summary_json['membership_stable_key'], imported_as_set_member.stable_key)

        aut_num_result = rpki_models.IrrCoordinationResult.objects.get(
            coordination_run=coordination_run,
            coordination_family=rpki_models.IrrCoordinationFamily.MAINTAINER_SUPPORTABILITY,
            result_type=rpki_models.IrrCoordinationResultType.MATCH,
        )
        self.assertEqual(aut_num_result.imported_maintainer, imported_maintainer)
        self.assertEqual(imported_aut_num.asn, 'AS64500')

    def test_run_irr_coordination_reports_route_set_membership_gaps(self):
        create_test_roa_intent(
            name='Intent Missing Membership',
            organization=self.organization,
            prefix_cidr_text='198.51.100.0/24',
            origin_asn_value=64501,
            max_length=24,
            derived_state=rpki_models.ROAIntentDerivedState.ACTIVE,
        )
        missing_route = create_test_imported_irr_route_object(
            snapshot=self.snapshot_a,
            source=self.source_a,
            stable_key='route:198.51.100.0/24AS64501',
            rpsl_pk='198.51.100.0/24AS64501',
            prefix='198.51.100.0/24',
            origin_asn='AS64501',
            route_set_names_json=['AS64501:RS-MISSING'],
            maintainer_names_json=[],
        )

        create_test_roa_intent(
            name='Intent Extra Membership',
            organization=self.organization,
            prefix_cidr_text='192.0.2.0/24',
            origin_asn_value=64502,
            max_length=24,
            derived_state=rpki_models.ROAIntentDerivedState.ACTIVE,
        )
        extra_route = create_test_imported_irr_route_object(
            snapshot=self.snapshot_a,
            source=self.source_a,
            stable_key='route:192.0.2.0/24AS64502',
            rpsl_pk='192.0.2.0/24AS64502',
            prefix='192.0.2.0/24',
            origin_asn='AS64502',
            route_set_names_json=[],
            maintainer_names_json=[],
        )
        extra_route_set = create_test_imported_irr_route_set(
            snapshot=self.snapshot_a,
            source=self.source_a,
            stable_key='route_set:AS64502:RS-EXTRA',
            rpsl_pk='AS64502:RS-EXTRA',
            set_name='AS64502:RS-EXTRA',
        )
        create_test_imported_irr_route_set_member(
            snapshot=self.snapshot_a,
            source=self.source_a,
            parent_route_set=extra_route_set,
            stable_key='route_set:AS64502:RS-EXTRA|192.0.2.0/24',
            rpsl_pk='AS64502:RS-EXTRA|192.0.2.0/24',
            member_text='192.0.2.0/24',
            normalized_prefix='192.0.2.0/24',
        )

        coordination_run = run_irr_coordination(self.organization)

        summary_counts = coordination_run.summary_json['result_counts'][rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP]
        self.assertEqual(summary_counts[rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE], 1)
        self.assertEqual(summary_counts[rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE], 1)

        missing_result = rpki_models.IrrCoordinationResult.objects.get(
            coordination_run=coordination_run,
            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            result_type=rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
        )
        self.assertEqual(missing_result.imported_route_object, missing_route)
        self.assertTrue(missing_result.summary_json['declared_by_route_object'])
        self.assertFalse(missing_result.summary_json['member_present_in_route_set'])

        extra_result = rpki_models.IrrCoordinationResult.objects.get(
            coordination_run=coordination_run,
            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            result_type=rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE,
        )
        self.assertEqual(extra_result.imported_route_object, extra_route)
        self.assertFalse(extra_result.summary_json['declared_by_route_object'])
        self.assertTrue(extra_result.summary_json['member_present_in_route_set'])

    def test_run_irr_coordination_reports_as_set_membership_context_gap(self):
        roa_intent = create_test_roa_intent(
            name='Intent Missing AS-Set Context',
            organization=self.organization,
            prefix_cidr_text='198.51.100.0/24',
            origin_asn_value=64510,
            max_length=24,
            derived_state=rpki_models.ROAIntentDerivedState.ACTIVE,
        )
        imported_route = create_test_imported_irr_route_object(
            snapshot=self.snapshot_a,
            source=self.source_a,
            stable_key='route:198.51.100.0/24AS64510',
            rpsl_pk='198.51.100.0/24AS64510',
            prefix='198.51.100.0/24',
            origin_asn='AS64510',
            route_set_names_json=[],
            maintainer_names_json=['LOCAL-IRR-MNT'],
        )
        create_test_imported_irr_aut_num(
            snapshot=self.snapshot_a,
            source=self.source_a,
            asn='AS64510',
        )
        create_test_imported_irr_maintainer(
            snapshot=self.snapshot_a,
            source=self.source_a,
            maintainer_name='LOCAL-IRR-MNT',
        )

        coordination_run = run_irr_coordination(self.organization)

        summary_counts = coordination_run.summary_json['result_counts'][rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP]
        self.assertEqual(summary_counts[rpki_models.IrrCoordinationResultType.POLICY_CONTEXT_GAP], 1)

        gap_result = rpki_models.IrrCoordinationResult.objects.get(
            coordination_run=coordination_run,
            coordination_family=rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP,
            result_type=rpki_models.IrrCoordinationResultType.POLICY_CONTEXT_GAP,
        )
        self.assertEqual(gap_result.roa_intent, roa_intent)
        self.assertEqual(gap_result.imported_route_object, imported_route)
        self.assertEqual(gap_result.summary_json['origin_asn'], 'AS64510')
        self.assertEqual(gap_result.summary_json['route_policy_count'], 1)

    def test_run_irr_coordination_marks_missing_and_extra_routes(self):
        create_test_roa_intent(
            name='Intent Missing',
            organization=self.organization,
            prefix_cidr_text='203.0.113.0/24',
            origin_asn_value=64500,
            max_length=24,
            derived_state=rpki_models.ROAIntentDerivedState.ACTIVE,
        )
        create_test_imported_irr_route_object(
            snapshot=self.snapshot_a,
            source=self.source_a,
            stable_key='route:198.51.100.0/24AS64501',
            rpsl_pk='198.51.100.0/24AS64501',
            prefix='198.51.100.0/24',
            origin_asn='AS64501',
            route_set_names_json=[],
            maintainer_names_json=[],
        )

        coordination_run = run_irr_coordination(self.organization)

        self.assertTrue(
            rpki_models.IrrCoordinationResult.objects.filter(
                coordination_run=coordination_run,
                result_type=rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
            ).exists()
        )
        self.assertTrue(
            rpki_models.IrrCoordinationResult.objects.filter(
                coordination_run=coordination_run,
                result_type=rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE,
            ).exists()
        )


class RunIrrCoordinationCommandTestCase(TestCase):
    def setUp(self):
        self.organization = create_test_organization(org_id='run-irr-coordination', name='Run IRR Coordination')

    def test_run_irr_coordination_command_runs_synchronously(self):
        with patch('netbox_rpki.management.commands.run_irr_coordination.run_irr_coordination') as coordination_mock:
            coordination_run = rpki_models.IrrCoordinationRun(name='Coordination Run')
            coordination_run.pk = 321
            coordination_mock.return_value = coordination_run
            stdout = StringIO()

            call_command(
                'run_irr_coordination',
                '--organization',
                str(self.organization.pk),
                stdout=stdout,
            )

        coordination_mock.assert_called_once_with(self.organization)
        self.assertIn('Completed IRR coordination run 321', stdout.getvalue())

    def test_run_irr_coordination_command_enqueues_job(self):
        with patch(
            'netbox_rpki.management.commands.run_irr_coordination.RunIrrCoordinationJob.enqueue_for_organization',
            return_value=(type('JobRef', (), {'pk': 77})(), True),
        ) as enqueue_mock:
            stdout = StringIO()
            call_command(
                'run_irr_coordination',
                '--organization',
                str(self.organization.pk),
                '--enqueue',
                stdout=stdout,
            )

        enqueue_mock.assert_called_once_with(self.organization)
        self.assertIn('Enqueued job 77', stdout.getvalue())
