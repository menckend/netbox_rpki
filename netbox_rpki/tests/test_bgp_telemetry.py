from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import sync_telemetry_source
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_prefix,
    create_test_telemetry_source,
)


FIXTURE_PATH = Path(__file__).resolve().parents[2] / 'devrun' / 'telemetry' / 'fixtures' / 'mrt-observations-sample.json'


class BgpTelemetryServiceTestCase(TestCase):
    def setUp(self):
        self.source = create_test_telemetry_source(name='Route Views MRT', slug='route-views-mrt')
        self.prefix_v4 = create_test_prefix(prefix='203.0.113.0/24')
        self.prefix_v6 = create_test_prefix(prefix='2001:db8:100::/48')
        self.origin_v4 = create_test_asn(asn=64500)
        self.origin_v6 = create_test_asn(asn=64501)
        self.peer_v4 = create_test_asn(asn=64496)
        self.peer_v6 = create_test_asn(asn=64497)

    def test_sync_telemetry_source_imports_snapshot_fixture(self):
        run = sync_telemetry_source(self.source, snapshot_file=str(FIXTURE_PATH))

        self.assertEqual(run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(run.source_fingerprint, 'mrt-snapshot-20260415-0005')
        self.assertEqual(run.summary_json['observation_count'], 2)
        self.assertEqual(run.summary_json['unique_prefix_count'], 2)
        self.assertEqual(run.summary_json['unique_path_count'], 2)
        self.assertEqual(run.summary_json['collector_counts']['route-views2'], 1)
        self.assertEqual(run.summary_json['collector_counts']['route-views6'], 1)

        observations = list(rpki_models.BgpPathObservation.objects.filter(telemetry_run=run).order_by('collector_id'))
        self.assertEqual(len(observations), 2)

        v6_observation = observations[0]
        self.assertEqual(v6_observation.collector_id, 'route-views2')
        self.assertEqual(v6_observation.observed_prefix, '203.0.113.0/24')
        self.assertEqual(v6_observation.origin_as, self.origin_v4)
        self.assertEqual(v6_observation.peer_as, self.peer_v4)
        self.assertEqual(v6_observation.path_asns_json, [64496, 64510, 64500])
        self.assertEqual(len(v6_observation.path_hash), 64)

        other_observation = observations[1]
        self.assertEqual(other_observation.observed_prefix, '2001:db8:100::/48')
        self.assertEqual(other_observation.origin_as, self.origin_v6)
        self.assertEqual(other_observation.peer_as, self.peer_v6)
        self.assertEqual(other_observation.path_asns_json, [64497, 64520, 64501])

        self.source.refresh_from_db()
        self.assertEqual(self.source.last_successful_run_id, run.pk)
        self.assertEqual(self.source.last_run_status, rpki_models.ValidationRunStatus.COMPLETED)


class SyncTelemetrySourceCommandTestCase(TestCase):
    def setUp(self):
        self.source = create_test_telemetry_source(name='Command Telemetry', slug='command-telemetry')

    def test_sync_telemetry_source_command_runs_synchronously(self):
        with patch('netbox_rpki.management.commands.sync_telemetry_source.sync_telemetry_source') as sync_mock:
            run = rpki_models.TelemetryRun(name='Telemetry Run')
            run.pk = 123
            sync_mock.return_value = run
            stdout = StringIO()

            call_command(
                'sync_telemetry_source',
                '--telemetry-source',
                str(self.source.pk),
                '--snapshot-file',
                str(FIXTURE_PATH),
                stdout=stdout,
            )

        sync_mock.assert_called_once_with(self.source, snapshot_file=str(FIXTURE_PATH))
        self.assertIn('Completed telemetry import run 123', stdout.getvalue())

    def test_sync_telemetry_source_command_enqueues_job(self):
        with patch(
            'netbox_rpki.management.commands.sync_telemetry_source.SyncTelemetrySourceJob.enqueue_for_source',
            return_value=(type('JobRef', (), {'pk': 99})(), True),
        ) as enqueue_mock:
            stdout = StringIO()
            call_command(
                'sync_telemetry_source',
                '--telemetry-source',
                str(self.source.pk),
                '--snapshot-file',
                str(FIXTURE_PATH),
                '--enqueue',
                stdout=stdout,
            )

        enqueue_mock.assert_called_once_with(self.source, snapshot_file=str(FIXTURE_PATH))
        self.assertIn('Enqueued job 99', stdout.getvalue())
