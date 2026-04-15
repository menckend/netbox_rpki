from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import IrrSyncError, sync_irr_source
from netbox_rpki.tests.utils import create_test_irr_source


FIXTURE_PATH = Path(__file__).resolve().parents[2] / 'devrun' / 'irrd' / 'fixtures' / 'local-authoritative.rpsl'

IRRD_GRAPHQL_RESPONSE = {
    'data': {
        'rpslObjects': [
            {
                'objectClass': 'aut-num',
                'rpslPk': 'AS64500',
                'source': 'LOCAL-IRR',
                'objectText': 'aut-num: AS64500\n',
                'autNum': 'AS64500',
                'asName': 'AS-LOCAL-IRR',
                'import': [],
                'export': [],
                'mntBy': ['LOCAL-IRR-MNT'],
                'adminC': ['LOCAL-IRR-PERSON'],
                'techC': ['LOCAL-IRR-PERSON'],
            },
            {
                'objectClass': 'as-set',
                'rpslPk': 'AS64500:AS-LOCAL-CUSTOMERS',
                'source': 'LOCAL-IRR',
                'objectText': 'as-set: AS64500:AS-LOCAL-CUSTOMERS\n',
                'asSet': 'AS64500:AS-LOCAL-CUSTOMERS',
                'members': ['AS64500'],
                'mntBy': ['LOCAL-IRR-MNT'],
                'adminC': ['LOCAL-IRR-PERSON'],
                'techC': ['LOCAL-IRR-PERSON'],
            },
            {
                'objectClass': 'route-set',
                'rpslPk': 'AS64500:RS-LOCAL-EDGE',
                'source': 'LOCAL-IRR',
                'objectText': 'route-set: AS64500:RS-LOCAL-EDGE\n',
                'routeSet': 'AS64500:RS-LOCAL-EDGE',
                'members': [],
                'mpMembers': [],
                'mntBy': ['LOCAL-IRR-MNT'],
                'adminC': ['LOCAL-IRR-PERSON'],
                'techC': ['LOCAL-IRR-PERSON'],
            },
            {
                'objectClass': 'route',
                'rpslPk': '203.0.113.0/24AS64500',
                'source': 'LOCAL-IRR',
                'objectText': 'route: 203.0.113.0/24\n',
                'route': '203.0.113.0/24',
                'origin': 'AS64500',
                'memberOf': ['AS64500:RS-LOCAL-EDGE'],
                'mntBy': ['LOCAL-IRR-MNT'],
            },
            {
                'objectClass': 'route6',
                'rpslPk': '2001:DB8:FBF4::/48AS64500',
                'source': 'LOCAL-IRR',
                'objectText': 'route6: 2001:db8:fbf4::/48\n',
                'route6': '2001:db8:fbf4::/48',
                'origin': 'AS64500',
                'memberOf': ['AS64500:RS-LOCAL-EDGE'],
                'mntBy': ['LOCAL-IRR-MNT'],
            },
            {
                'objectClass': 'mntner',
                'rpslPk': 'LOCAL-IRR-MNT',
                'source': 'LOCAL-IRR',
                'objectText': 'mntner: LOCAL-IRR-MNT\n',
                'mntner': 'LOCAL-IRR-MNT',
                'auth': ['BCRYPT-PW DummyValue  # Filtered for security'],
                'adminC': ['LOCAL-IRR-PERSON'],
                'updTo': ['irrd-dev@example.invalid'],
                'mntBy': ['LOCAL-IRR-MNT'],
            },
        ]
    }
}

class IrrSyncServiceTestCase(TestCase):
    def setUp(self):
        self.irr_source = create_test_irr_source(
            name='Local IRRd',
            slug='local-irrd',
            query_base_url='http://127.0.0.1:6080',
        )

    def test_sync_irr_source_imports_snapshot_file_fixture(self):
        snapshot = sync_irr_source(
            self.irr_source,
            fetch_mode=rpki_models.IrrFetchMode.SNAPSHOT_IMPORT,
            snapshot_file=str(FIXTURE_PATH),
        )

        self.assertEqual(snapshot.status, rpki_models.IrrSnapshotStatus.COMPLETED)
        self.assertEqual(snapshot.summary_json['families']['route']['imported'], 1)
        self.assertEqual(snapshot.summary_json['families']['route6']['imported'], 1)
        self.assertEqual(snapshot.summary_json['families']['route_set']['imported'], 1)
        self.assertEqual(snapshot.summary_json['families']['route_set_member']['imported'], 2)
        self.assertEqual(snapshot.summary_json['families']['as_set']['imported'], 1)
        self.assertEqual(snapshot.summary_json['families']['as_set_member']['imported'], 1)
        self.assertEqual(snapshot.summary_json['families']['aut_num']['imported'], 1)
        self.assertEqual(snapshot.summary_json['families']['mntner']['imported'], 1)
        self.assertEqual(
            list(
                rpki_models.ImportedIrrRouteObject.objects.filter(snapshot=snapshot)
                .order_by('stable_key')
                .values_list('stable_key', flat=True)
            ),
            [
                'route:203.0.113.0/24AS64500',
                'route6:2001:db8:fbf4::/48AS64500',
            ],
        )

        route_set = rpki_models.ImportedIrrRouteSet.objects.get(snapshot=snapshot)
        self.assertEqual(route_set.set_name, 'AS64500:RS-LOCAL-EDGE')
        self.assertEqual(route_set.member_count, 2)

        maintainer = rpki_models.ImportedIrrMaintainer.objects.get(snapshot=snapshot)
        self.assertEqual(maintainer.auth_summary_json, ['BCRYPT-PW filtered'])
        self.assertEqual(maintainer.admin_contact_handles_json, ['LOCAL-IRR-PERSON'])
        self.assertEqual(maintainer.upd_to_addresses_json, ['irrd-dev@example.invalid'])

        self.irr_source.refresh_from_db()
        self.assertEqual(self.irr_source.last_successful_snapshot_id, snapshot.pk)
        self.assertEqual(self.irr_source.last_sync_status, rpki_models.IrrSnapshotStatus.COMPLETED)

    def test_sync_irr_source_uses_irrd_live_adapter(self):
        with patch('netbox_rpki.services.irr_sync._http_json_request', return_value=IRRD_GRAPHQL_RESPONSE), patch(
            'netbox_rpki.services.irr_sync._http_text_request',
            return_value='{"LOCAL-IRR": {"serial_newest_journal": 10, "rpsl_data_updated": "2026-04-15T03:33:32.050009+00:00"}}',
        ):
            snapshot = sync_irr_source(self.irr_source)

        self.assertEqual(snapshot.source_serial, '10')
        self.assertEqual(snapshot.status, rpki_models.IrrSnapshotStatus.COMPLETED)
        self.assertEqual(rpki_models.ImportedIrrRouteSetMember.objects.filter(snapshot=snapshot).count(), 2)
        self.assertEqual(rpki_models.ImportedIrrAsSetMember.objects.filter(snapshot=snapshot).count(), 1)

    def test_sync_irr_source_requires_snapshot_file_for_snapshot_mode(self):
        with self.assertRaises(IrrSyncError):
            sync_irr_source(
                self.irr_source,
                fetch_mode=rpki_models.IrrFetchMode.SNAPSHOT_IMPORT,
            )


class SyncIrrSourceCommandTestCase(TestCase):
    def setUp(self):
        self.irr_source = create_test_irr_source(name='Command IRR', slug='command-irr')

    def test_sync_irr_source_command_runs_synchronously(self):
        with patch('netbox_rpki.management.commands.sync_irr_source.sync_irr_source') as sync_mock:
            snapshot = rpki_models.IrrSnapshot(name='Snapshot')
            snapshot.pk = 123
            sync_mock.return_value = snapshot
            stdout = StringIO()

            call_command(
                'sync_irr_source',
                '--irr-source',
                str(self.irr_source.pk),
                '--fetch-mode',
                rpki_models.IrrFetchMode.SNAPSHOT_IMPORT,
                '--snapshot-file',
                str(FIXTURE_PATH),
                stdout=stdout,
            )

        sync_mock.assert_called_once_with(
            self.irr_source,
            fetch_mode=rpki_models.IrrFetchMode.SNAPSHOT_IMPORT,
            snapshot_file=str(FIXTURE_PATH),
        )
        self.assertIn('Completed IRR import snapshot 123', stdout.getvalue())

    def test_sync_irr_source_command_enqueues_job(self):
        with patch(
            'netbox_rpki.management.commands.sync_irr_source.SyncIrrSourceJob.enqueue_for_source',
            return_value=(type('JobRef', (), {'pk': 99})(), True),
        ) as enqueue_mock:
            stdout = StringIO()
            call_command(
                'sync_irr_source',
                '--irr-source',
                str(self.irr_source.pk),
                '--enqueue',
                stdout=stdout,
            )

        enqueue_mock.assert_called_once_with(
            self.irr_source,
            fetch_mode=rpki_models.IrrFetchMode.LIVE_QUERY,
            snapshot_file=None,
        )
        self.assertIn('Enqueued job 99', stdout.getvalue())
