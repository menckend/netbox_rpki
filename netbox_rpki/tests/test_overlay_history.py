from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services import (
    build_telemetry_run_comparison,
    build_telemetry_run_history_summary,
    build_validation_run_comparison,
    build_validator_run_history_summary,
)
from netbox_rpki.tests.utils import (
    create_test_organization,
    create_test_telemetry_run,
    create_test_telemetry_source,
    create_test_validation_run,
    create_test_validator_instance,
)


class OverlayHistoryServiceTestCase(TestCase):
    def setUp(self):
        self.organization = create_test_organization(name='Overlay History Org')
        self.validator = create_test_validator_instance(
            name='Overlay History Validator',
            organization=self.organization,
        )
        self.previous_validation_run = create_test_validation_run(
            name='Older Validation Run',
            validator=self.validator,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            repository_serial='100',
            completed_at=timezone.now() - timedelta(days=2),
            summary_json={
                'validated_roa_payload_count': 2,
                'validated_aspa_payload_count': 1,
            },
        )
        self.latest_validation_run = create_test_validation_run(
            name='Latest Validation Run',
            validator=self.validator,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            repository_serial='101',
            completed_at=timezone.now() - timedelta(hours=1),
            summary_json={
                'validated_roa_payload_count': 3,
                'validated_aspa_payload_count': 1,
            },
        )

        self.telemetry_source = create_test_telemetry_source(
            name='Overlay History Telemetry Source',
            organization=self.organization,
            slug='overlay-history-telemetry',
            import_interval=60,
        )
        self.previous_telemetry_run = create_test_telemetry_run(
            name='Older Telemetry Run',
            source=self.telemetry_source,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=timezone.now() - timedelta(hours=3),
            summary_json={
                'observation_count': 4,
                'unique_path_count': 2,
            },
        )
        self.latest_telemetry_run = create_test_telemetry_run(
            name='Latest Telemetry Run',
            source=self.telemetry_source,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=timezone.now() - timedelta(minutes=30),
            summary_json={
                'observation_count': 6,
                'unique_path_count': 3,
            },
        )

    def test_validator_history_summary_reports_comparison_and_timeline(self):
        summary = build_validator_run_history_summary(self.validator)

        self.assertEqual(summary['summary_schema_version'], 1)
        self.assertEqual(summary['run_count'], 2)
        self.assertEqual(summary['latest_run_id'], self.latest_validation_run.pk)
        self.assertEqual(summary['latest_comparison']['comparison_state'], 'changed')
        self.assertEqual(
            summary['latest_comparison']['changed_summary_fields']['validated_roa_payload_count']['delta'],
            1,
        )
        self.assertEqual(summary['timeline'][0]['run_id'], self.latest_validation_run.pk)

    def test_run_comparison_helpers_report_freshness_and_gap(self):
        validation_comparison = build_validation_run_comparison(self.latest_validation_run)
        telemetry_comparison = build_telemetry_run_comparison(self.latest_telemetry_run)

        self.assertEqual(validation_comparison['timeline_freshness'], 'current')
        self.assertTrue(validation_comparison['repository_serial_changed'])
        self.assertGreater(validation_comparison['observation_gap_seconds'], 0)
        self.assertEqual(telemetry_comparison['comparison_state'], 'changed')
        self.assertEqual(
            telemetry_comparison['changed_summary_fields']['observation_count']['delta'],
            2,
        )

    def test_telemetry_history_summary_uses_source_interval_for_freshness(self):
        summary = build_telemetry_run_history_summary(self.telemetry_source)

        self.assertEqual(summary['summary_schema_version'], 1)
        self.assertEqual(summary['latest_comparison']['timeline_freshness'], 'current')
        self.assertEqual(summary['timeline'][0]['freshness_status'], 'current')
