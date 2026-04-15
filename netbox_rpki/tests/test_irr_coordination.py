from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import run_irr_coordination
from netbox_rpki.tests.utils import (
    create_test_irr_snapshot,
    create_test_irr_source,
    create_test_imported_irr_aut_num,
    create_test_imported_irr_maintainer,
    create_test_imported_irr_route_object,
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

        aut_num_result = rpki_models.IrrCoordinationResult.objects.get(
            coordination_run=coordination_run,
            coordination_family=rpki_models.IrrCoordinationFamily.MAINTAINER_SUPPORTABILITY,
            result_type=rpki_models.IrrCoordinationResultType.MATCH,
        )
        self.assertEqual(aut_num_result.imported_maintainer, imported_maintainer)
        self.assertEqual(imported_aut_num.asn, 'AS64500')

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
