from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from netbox_rpki import models as rpki_models
from netbox_rpki.services import ProviderSyncError, sync_provider_account
from netbox_rpki.tests.base import PluginAPITestCase
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_organization,
    create_test_prefix,
    create_test_provider_account,
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

        imported = list(snapshot.imported_roa_authorizations.order_by('prefix_cidr_text'))
        self.assertEqual(sync_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(snapshot.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(sync_run.records_fetched, 2)
        self.assertEqual(sync_run.records_imported, 2)
        self.assertEqual(len(imported), 2)
        self.assertEqual(imported[0].external_object_id, '58bc1674f7784054ba743b9f5c23885b')
        self.assertEqual(imported[0].origin_asn, self.origin_asn)
        self.assertEqual(imported[0].prefix, self.prefix_v4)
        self.assertEqual(imported[0].max_length, 24)
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

        imported = list(snapshot.imported_roa_authorizations.order_by('prefix_cidr_text'))
        self.assertEqual(sync_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(sync_run.records_fetched, 2)
        self.assertEqual(sync_run.records_imported, 2)
        self.assertEqual(imported[0].prefix, prefix_v4)
        self.assertEqual(imported[0].origin_asn, origin_asn)
        self.assertEqual(imported[0].external_object_id, '10.10.0.0/24|24|65000')
        self.assertEqual(imported[0].payload_json['ca_handle'], 'netbox-rpki-dev')
        self.assertEqual(imported[1].prefix, prefix_v6)
        self.assertEqual(imported[1].address_family, rpki_models.AddressFamily.IPV6)
        provider_account.refresh_from_db()
        self.assertEqual(provider_account.last_sync_summary_json['ca_handle'], 'netbox-rpki-dev')

    def test_sync_provider_account_requires_krill_ca_handle(self):
        provider_account = create_test_provider_account(
            name='Invalid Krill Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='',
        )

        with self.assertRaisesMessage(ProviderSyncError, 'missing a Krill CA handle'):
            sync_provider_account(provider_account)


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

        with patch('netbox_rpki.api.views.SyncProviderAccountJob.enqueue', return_value=StubJob()) as enqueue_mock:
            response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['job']['id'], 777)
        enqueue_mock.assert_called_once_with(
            instance=self.provider_account,
            user=self.user,
            provider_account_pk=self.provider_account.pk,
        )