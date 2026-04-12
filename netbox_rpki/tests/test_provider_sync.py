from datetime import timedelta
from unittest.mock import call, patch

from django.db import IntegrityError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services import ProviderSyncError, sync_provider_account
from netbox_rpki.tests.base import PluginAPITestCase
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_imported_roa_authorization,
    create_test_organization,
    create_test_prefix,
    create_test_provider_account,
    create_test_provider_snapshot,
)


ARIN_ROA_XML = """
<roaSpecs xmlns=\"http://www.arin.net/regrws/rpki/v1\">
  <roaSpec>
    <asNumber>64496</asNumber>
    <name>headquarters</name>
    <notValidAfter>2030-12-13T00:00:00-05:00</notValidAfter>
    <notValidBefore>2029-12-14T00:00:00-05:00</notValidBefore>
    <roaHandle>58bc1674f7784054ba743b9f5c23885b</roaHandle>
    <resources>
      <roaSpecResource>
        <startAddress>192.0.2.0</startAddress>
        <endAddress>192.0.2.255</endAddress>
        <cidrLength>24</cidrLength>
        <ipVersion>4</ipVersion>
        <maxLength>24</maxLength>
        <autoLinked>true</autoLinked>
      </roaSpecResource>
      <roaSpecResource>
        <startAddress>2001:db8::</startAddress>
        <endAddress>2001:db8::ffff</endAddress>
        <cidrLength>32</cidrLength>
        <ipVersion>6</ipVersion>
        <maxLength>48</maxLength>
        <autoLinked>false</autoLinked>
      </roaSpecResource>
    </resources>
    <autoRenewed>true</autoRenewed>
  </roaSpec>
</roaSpecs>
""".strip()


KRILL_ROUTES_JSON = [
    {
        'asn': 65000,
        'prefix': '10.10.0.0/24',
        'max_length': 24,
        'comment': 'netbox_rpki sample IPv4 ROA',
        'roa_objects': [
            {
                'authorizations': ['10.10.0.0/24-24 => 65000'],
                'validity': {
                    'not_before': '2026-04-12T10:00:00Z',
                    'not_after': '2027-04-12T10:00:00Z',
                },
                'serial': '111',
                'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/v4.roa',
                'base64': 'AAA',
                'hash': 'hash-v4',
            }
        ],
    },
    {
        'asn': 65000,
        'prefix': '2001:db8:100::/48',
        'max_length': 48,
        'comment': 'netbox_rpki sample IPv6 ROA',
        'roa_objects': [
            {
                'authorizations': ['2001:db8:100::/48-48 => 65000'],
                'validity': {
                    'not_before': '2026-04-12T10:00:00Z',
                    'not_after': '2027-04-12T10:00:00Z',
                },
                'serial': '222',
                'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/v6.roa',
                'base64': 'BBB',
                'hash': 'hash-v6',
            }
        ],
    },
]


class ProviderSyncServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-sync-org', name='Provider Sync Org')
        cls.provider_account = create_test_provider_account(
            name='ARIN Account',
            organization=cls.organization,
            org_handle='ORG-ARIN',
        )
        cls.prefix_v4 = create_test_prefix('192.0.2.0/24')
        cls.prefix_v6 = create_test_prefix('2001:db8::/32')
        cls.origin_asn = create_test_asn(64496)

    def test_sync_provider_account_imports_arin_roas(self):
        with patch('netbox_rpki.services.provider_sync._fetch_arin_roa_xml', return_value=ARIN_ROA_XML):
            sync_run, snapshot = sync_provider_account(self.provider_account)

        imported = list(snapshot.imported_roa_authorizations.select_related('external_reference').order_by('prefix_cidr_text'))
        self.assertEqual(sync_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(snapshot.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(sync_run.records_fetched, 2)
        self.assertEqual(sync_run.records_imported, 2)
        self.assertEqual(len(imported), 2)
        self.assertEqual(rpki_models.ExternalObjectReference.objects.count(), 2)
        self.assertEqual(imported[0].external_object_id, '58bc1674f7784054ba743b9f5c23885b')
        self.assertIsNotNone(imported[0].external_reference)
        self.assertEqual(imported[0].external_reference.external_object_id, imported[0].external_object_id)
        self.assertEqual(imported[0].external_reference.provider_identity, '58bc1674f7784054ba743b9f5c23885b|192.0.2.0/24')
        self.assertEqual(imported[0].origin_asn, self.origin_asn)
        self.assertEqual(imported[0].prefix, self.prefix_v4)
        self.assertEqual(imported[0].max_length, 24)
        self.assertNotEqual(imported[0].external_reference_id, imported[1].external_reference_id)
        self.assertEqual(imported[1].address_family, rpki_models.AddressFamily.IPV6)
        self.assertEqual(imported[1].prefix, self.prefix_v6)
        self.provider_account.refresh_from_db()
        self.assertEqual(self.provider_account.last_sync_status, rpki_models.ValidationRunStatus.COMPLETED)

    def test_sync_provider_account_marks_failure(self):
        with patch('netbox_rpki.services.provider_sync._fetch_arin_roa_xml', side_effect=RuntimeError('boom')):
            with self.assertRaisesMessage(ProviderSyncError, 'boom'):
                sync_provider_account(self.provider_account)

    def test_sync_provider_account_imports_krill_routes(self):
        provider_account = create_test_provider_account(
            name='Krill Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='netbox-rpki-dev',
            api_base_url='https://localhost:3001',
            api_key='krill-token',
            org_handle='ORG-KRILL',
        )
        prefix_v4 = create_test_prefix('10.10.0.0/24')
        prefix_v6 = create_test_prefix('2001:db8:100::/48')
        origin_asn = create_test_asn(65000)

        with patch('netbox_rpki.services.provider_sync._fetch_krill_routes_json', return_value=KRILL_ROUTES_JSON):
            sync_run, snapshot = sync_provider_account(provider_account)

        imported = list(snapshot.imported_roa_authorizations.select_related('external_reference').order_by('prefix_cidr_text'))
        self.assertEqual(sync_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(sync_run.records_fetched, 2)
        self.assertEqual(sync_run.records_imported, 2)
        self.assertEqual(imported[0].prefix, prefix_v4)
        self.assertEqual(imported[0].origin_asn, origin_asn)
        self.assertEqual(imported[0].external_object_id, '10.10.0.0/24|24|65000')
        self.assertIsNotNone(imported[0].external_reference)
        self.assertEqual(imported[0].external_reference.provider_identity, '10.10.0.0/24|24|65000')
        self.assertEqual(imported[0].payload_json['ca_handle'], 'netbox-rpki-dev')
        self.assertEqual(imported[1].prefix, prefix_v6)
        self.assertEqual(imported[1].address_family, rpki_models.AddressFamily.IPV6)
        provider_account.refresh_from_db()
        self.assertEqual(provider_account.last_sync_summary_json['ca_handle'], 'netbox-rpki-dev')

    def test_sync_provider_account_reuses_krill_external_reference_across_snapshots(self):
        provider_account = create_test_provider_account(
            name='Krill Identity Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='netbox-rpki-dev',
            api_base_url='https://localhost:3001',
            api_key='krill-token',
            org_handle='ORG-KRILL-IDENTITY',
        )
        create_test_prefix('10.10.0.0/24')
        create_test_prefix('2001:db8:100::/48')
        create_test_asn(65000)

        with patch('netbox_rpki.services.provider_sync._fetch_krill_routes_json', return_value=KRILL_ROUTES_JSON):
            _, first_snapshot = sync_provider_account(provider_account)
        first_import = first_snapshot.imported_roa_authorizations.get(prefix_cidr_text='10.10.0.0/24')
        first_reference = first_import.external_reference

        with patch('netbox_rpki.services.provider_sync._fetch_krill_routes_json', return_value=KRILL_ROUTES_JSON):
            _, second_snapshot = sync_provider_account(provider_account)
        second_import = second_snapshot.imported_roa_authorizations.get(prefix_cidr_text='10.10.0.0/24')

        self.assertEqual(rpki_models.ExternalObjectReference.objects.count(), 2)
        self.assertEqual(second_import.external_reference_id, first_reference.pk)
        first_reference.refresh_from_db()
        self.assertEqual(first_reference.last_seen_provider_snapshot, second_snapshot)
        self.assertEqual(first_reference.last_seen_imported_authorization, second_import)

    def test_sync_provider_account_requires_krill_ca_handle(self):
        provider_account = create_test_provider_account(
            name='Invalid Krill Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='',
        )

        with self.assertRaisesMessage(ProviderSyncError, 'missing a Krill CA handle'):
            sync_provider_account(provider_account)

    def test_provider_account_sync_health_uses_existing_last_sync_state(self):
        now = timezone.now()
        disabled_account = create_test_provider_account(
            name='Disabled Account',
            organization=self.organization,
            org_handle='ORG-DISABLED',
            sync_enabled=False,
            sync_interval=60,
        )
        never_synced_account = create_test_provider_account(
            name='Never Synced Account',
            organization=self.organization,
            org_handle='ORG-NEVER',
            sync_interval=60,
            last_successful_sync=None,
            last_sync_status=rpki_models.ValidationRunStatus.PENDING,
        )
        healthy_account = create_test_provider_account(
            name='Healthy Account',
            organization=self.organization,
            org_handle='ORG-HEALTHY',
            sync_interval=60,
            last_successful_sync=now - timedelta(minutes=15),
            last_sync_status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        stale_account = create_test_provider_account(
            name='Stale Account',
            organization=self.organization,
            org_handle='ORG-STALE',
            sync_interval=60,
            last_successful_sync=now - timedelta(hours=3),
            last_sync_status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        failed_account = create_test_provider_account(
            name='Failed Account',
            organization=self.organization,
            org_handle='ORG-FAILED',
            sync_interval=60,
            last_successful_sync=now - timedelta(minutes=10),
            last_sync_status=rpki_models.ValidationRunStatus.FAILED,
        )

        self.assertEqual(disabled_account.sync_health, rpki_models.ProviderSyncHealth.DISABLED)
        self.assertEqual(never_synced_account.sync_health, rpki_models.ProviderSyncHealth.NEVER_SYNCED)
        self.assertEqual(healthy_account.sync_health, rpki_models.ProviderSyncHealth.HEALTHY)
        self.assertEqual(stale_account.sync_health, rpki_models.ProviderSyncHealth.STALE)
        self.assertEqual(failed_account.sync_health, rpki_models.ProviderSyncHealth.FAILED)

    def test_provider_account_is_sync_due_for_failed_never_synced_and_overdue_accounts(self):
        now = timezone.now()
        never_synced_account = create_test_provider_account(
            name='Due Never Synced',
            organization=self.organization,
            org_handle='ORG-DUE-NEVER',
            sync_interval=60,
            last_successful_sync=None,
            last_sync_status=rpki_models.ValidationRunStatus.PENDING,
        )
        failed_account = create_test_provider_account(
            name='Due Failed',
            organization=self.organization,
            org_handle='ORG-DUE-FAILED',
            sync_interval=60,
            last_successful_sync=now - timedelta(minutes=5),
            last_sync_status=rpki_models.ValidationRunStatus.FAILED,
        )
        stale_account = create_test_provider_account(
            name='Due Stale',
            organization=self.organization,
            org_handle='ORG-DUE-STALE',
            sync_interval=60,
            last_successful_sync=now - timedelta(hours=2),
            last_sync_status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        healthy_account = create_test_provider_account(
            name='Not Due',
            organization=self.organization,
            org_handle='ORG-NOT-DUE',
            sync_interval=60,
            last_successful_sync=now - timedelta(minutes=10),
            last_sync_status=rpki_models.ValidationRunStatus.COMPLETED,
        )

        self.assertTrue(never_synced_account.is_sync_due(reference_time=now))
        self.assertTrue(failed_account.is_sync_due(reference_time=now))
        self.assertTrue(stale_account.is_sync_due(reference_time=now))
        self.assertFalse(healthy_account.is_sync_due(reference_time=now))


class ExternalObjectReferenceModelTestCase(TestCase):
    def test_external_object_reference_is_unique_per_provider_identity(self):
        organization = create_test_organization(org_id='external-reference-org', name='External Reference Org')
        provider_account = create_test_provider_account(
            name='External Reference Account',
            organization=organization,
            org_handle='ORG-REFERENCE',
        )
        snapshot = create_test_provider_snapshot(
            name='Reference Snapshot',
            organization=organization,
            provider_account=provider_account,
        )
        imported = create_test_imported_roa_authorization(
            name='Reference Imported ROA',
            organization=organization,
            provider_snapshot=snapshot,
            prefix=create_test_prefix('198.51.100.0/24'),
            prefix_cidr_text='198.51.100.0/24',
            external_object_id='arin-handle-1',
        )
        rpki_models.ExternalObjectReference.objects.create(
            name='Reference 1',
            organization=organization,
            provider_account=provider_account,
            object_type=rpki_models.ExternalObjectType.ROA_AUTHORIZATION,
            provider_identity='arin-handle-1|198.51.100.0/24',
            external_object_id='arin-handle-1',
            last_seen_provider_snapshot=snapshot,
            last_seen_imported_authorization=imported,
        )

        with self.assertRaises(IntegrityError):
            rpki_models.ExternalObjectReference.objects.create(
                name='Reference 2',
                organization=organization,
                provider_account=provider_account,
                object_type=rpki_models.ExternalObjectType.ROA_AUTHORIZATION,
                provider_identity='arin-handle-1|198.51.100.0/24',
                external_object_id='arin-handle-1',
                last_seen_provider_snapshot=snapshot,
            )


class ProviderSyncCommandTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-command-org', name='Provider Command Org')
        cls.provider_account = create_test_provider_account(
            name='Command ARIN Account',
            organization=cls.organization,
            org_handle='ORG-COMMAND',
        )

    def test_management_command_runs_sync(self):
        with patch('netbox_rpki.management.commands.sync_provider_account.sync_provider_account') as sync_mock:
            sync_run = rpki_models.ProviderSyncRun(name='Sync Run')
            snapshot = rpki_models.ProviderSnapshot(name='Snapshot', provider_name='ARIN')
            sync_mock.return_value = (sync_run, snapshot)
            call_command('sync_provider_account', '--provider-account', str(self.provider_account.pk))

        sync_mock.assert_called_once_with(self.provider_account)

    def test_management_command_enqueue_uses_orchestration_helper(self):
        class StubJob:
            pk = 779

        with patch(
            'netbox_rpki.management.commands.sync_provider_account.SyncProviderAccountJob.enqueue_for_provider_account',
            return_value=(StubJob(), True),
        ) as enqueue_mock:
            call_command('sync_provider_account', '--provider-account', str(self.provider_account.pk), '--enqueue')

        enqueue_mock.assert_called_once_with(self.provider_account)


class ProviderSyncSchedulingCommandTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-schedule-org', name='Provider Schedule Org')
        now = timezone.now()
        cls.due_never_synced = create_test_provider_account(
            name='Due Never Synced',
            organization=cls.organization,
            org_handle='ORG-DUE-NEVER-SCAN',
            sync_interval=60,
            last_successful_sync=None,
            last_sync_status=rpki_models.ValidationRunStatus.PENDING,
        )
        cls.due_failed = create_test_provider_account(
            name='Due Failed',
            organization=cls.organization,
            org_handle='ORG-DUE-FAILED-SCAN',
            sync_interval=60,
            last_successful_sync=now - timedelta(minutes=5),
            last_sync_status=rpki_models.ValidationRunStatus.FAILED,
        )
        cls.not_due = create_test_provider_account(
            name='Not Due',
            organization=cls.organization,
            org_handle='ORG-NOT-DUE-SCAN',
            sync_interval=60,
            last_successful_sync=now - timedelta(minutes=10),
            last_sync_status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.disabled = create_test_provider_account(
            name='Disabled',
            organization=cls.organization,
            org_handle='ORG-DISABLED-SCAN',
            sync_enabled=False,
            sync_interval=60,
            last_successful_sync=None,
        )

    def test_due_accounts_command_enqueues_only_due_scheduled_accounts(self):
        class StubJob:
            def __init__(self, pk):
                self.pk = pk

        with patch(
            'netbox_rpki.management.commands.sync_provider_accounts.SyncProviderAccountJob.enqueue_for_provider_account',
            side_effect=[(StubJob(801), True), (StubJob(802), True)],
        ) as enqueue_mock:
            call_command('sync_provider_accounts')

        self.assertEqual(
            enqueue_mock.call_args_list,
            [call(self.due_never_synced), call(self.due_failed)],
        )

    def test_due_accounts_command_dry_run_does_not_enqueue(self):
        with patch('netbox_rpki.management.commands.sync_provider_accounts.SyncProviderAccountJob.enqueue_for_provider_account') as enqueue_mock:
            call_command('sync_provider_accounts', '--dry-run')

        enqueue_mock.assert_not_called()


class ProviderAccountSyncActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-api-org', name='Provider API Org')
        cls.provider_account = create_test_provider_account(
            name='API ARIN Account',
            organization=cls.organization,
            org_handle='ORG-API',
        )

    def test_sync_action_enqueues_job(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.change_rpkiprovideraccount',
        )
        url = reverse('plugins-api:netbox_rpki-api:provideraccount-sync', kwargs={'pk': self.provider_account.pk})

        class StubJob:
            pk = 777
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/777/'

        with patch(
            'netbox_rpki.api.views.SyncProviderAccountJob.enqueue_for_provider_account',
            return_value=(StubJob(), True),
        ) as enqueue_mock:
            response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['job']['id'], 777)
        self.assertFalse(response.data['sync_in_progress'])
        enqueue_mock.assert_called_once_with(self.provider_account, user=self.user)

    def test_sync_action_reuses_existing_job_payload(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.change_rpkiprovideraccount',
        )
        url = reverse('plugins-api:netbox_rpki-api:provideraccount-sync', kwargs={'pk': self.provider_account.pk})

        class StubJob:
            pk = 778
            status = 'pending'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/778/'

        with patch(
            'netbox_rpki.api.views.SyncProviderAccountJob.enqueue_for_provider_account',
            return_value=(StubJob(), False),
        ):
            response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertTrue(response.data['sync_in_progress'])
        self.assertTrue(response.data['job']['existing'])