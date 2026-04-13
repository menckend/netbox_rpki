from datetime import datetime, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services.provider_sync_krill import (
    krill_ca_metadata_url,
    krill_child_connections_url,
    krill_child_info_url,
    krill_parent_contact_url,
    krill_parent_statuses_url,
    krill_repo_details_url,
    krill_repo_status_url,
    parse_krill_ca_metadata_record,
    parse_krill_child_link_records,
    parse_krill_parent_link_records,
    parse_krill_publication_point_records,
    parse_krill_signed_object_records,
    parse_krill_resource_entitlement_records,
)
from netbox_rpki.tests.krill_payloads import (
    KRILL_CA_METADATA_JSON,
    KRILL_CHILD_CONNECTIONS_JSON,
    KRILL_CHILD_INFO_JSON,
    KRILL_PARENT_CONTACT_JSON,
    KRILL_PARENT_STATUSES_JSON,
    KRILL_REPO_DETAILS_JSON,
    KRILL_REPO_STATUS_JSON,
)


class KrillProviderSyncParserTestCase(SimpleTestCase):
    def test_krill_tier_one_url_builders_match_documented_endpoints(self):
        provider_account = SimpleNamespace(
            api_base_url='https://krill.example/internal/',
            sync_target_handle='netbox rpki dev',
            api_key='krill-token',
        )

        self.assertEqual(
            krill_ca_metadata_url(provider_account),
            'https://krill.example/internal/api/v1/cas/netbox%20rpki%20dev',
        )
        self.assertEqual(
            krill_parent_statuses_url(provider_account),
            'https://krill.example/internal/api/v1/cas/netbox%20rpki%20dev/parents',
        )
        self.assertEqual(
            krill_parent_contact_url(provider_account, 'testbed parent'),
            'https://krill.example/internal/api/v1/cas/netbox%20rpki%20dev/parents/testbed%20parent',
        )
        self.assertEqual(
            krill_child_info_url(provider_account, 'edge customer/01'),
            'https://krill.example/internal/api/v1/cas/netbox%20rpki%20dev/children/edge%20customer%2F01',
        )
        self.assertEqual(
            krill_child_connections_url(provider_account),
            'https://krill.example/internal/api/v1/cas/netbox%20rpki%20dev/stats/children/connections',
        )
        self.assertEqual(
            krill_repo_details_url(provider_account),
            'https://krill.example/internal/api/v1/cas/netbox%20rpki%20dev/repo',
        )
        self.assertEqual(
            krill_repo_status_url(provider_account),
            'https://krill.example/internal/api/v1/cas/netbox%20rpki%20dev/repo/status',
        )

    def test_parse_krill_ca_metadata_record_normalizes_fixture(self):
        record = parse_krill_ca_metadata_record(KRILL_CA_METADATA_JSON)

        self.assertIsNotNone(record)
        self.assertEqual(record.ca_handle, 'netbox-rpki-dev')
        self.assertEqual(record.id_cert_hash, 'krill-ca-id-cert-sha256')
        self.assertEqual(record.publication_uri, 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/')
        self.assertEqual(record.rrdp_notification_uri, 'https://testbed.krill.cloud/rrdp/notification.xml')
        self.assertEqual(record.parent_handles, ('testbed',))
        self.assertEqual(record.child_handles, ('edge-customer-01',))
        self.assertEqual(record.suspended_child_handles, ('edge-customer-archive',))
        self.assertEqual(record.parent_count, 1)
        self.assertEqual(record.resource_class_count, 1)
        self.assertEqual(record.resources.asn_resources, 'AS65000-AS65010')
        self.assertEqual(record.resource_classes[0].parent_handle, 'testbed')
        self.assertEqual(record.resource_classes[0].key_identifier, 'NETBOXRPKIACTIVEKEY0001')

    def test_parse_krill_ca_metadata_record_rejects_non_mapping_payloads(self):
        self.assertIsNone(parse_krill_ca_metadata_record([]))
        self.assertIsNone(parse_krill_ca_metadata_record(None))

    def test_parse_krill_parent_link_records_merges_status_and_contact_payloads(self):
        records = parse_krill_parent_link_records(
            KRILL_PARENT_STATUSES_JSON,
            parent_contact_payloads={'testbed': KRILL_PARENT_CONTACT_JSON},
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.parent_handle, 'testbed')
        self.assertEqual(record.relationship_type, 'rfc6492')
        self.assertEqual(record.service_uri, 'https://testbed.krill.cloud/rfc6492/testbed/')
        self.assertEqual(record.child_handle, 'netbox-rpki-dev')
        self.assertEqual(record.last_exchange_result, 'Success')
        self.assertEqual(record.last_exchange_at, datetime.fromtimestamp(1775988000, tz=timezone.utc))
        self.assertEqual(record.last_success_at, datetime.fromtimestamp(1775988000, tz=timezone.utc))
        self.assertEqual(record.all_resources.ipv4_resources, '10.10.0.0/24, 10.20.0.0/24')
        self.assertEqual(record.classes[0].class_name, '0')
        self.assertEqual(record.classes[0].not_after, datetime(2027, 4, 12, 10, 0, tzinfo=timezone.utc))

    def test_parse_krill_parent_link_records_accepts_contact_only_records(self):
        records = parse_krill_parent_link_records(
            {},
            parent_contact_payloads={'testbed': KRILL_PARENT_CONTACT_JSON},
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].parent_handle, 'testbed')
        self.assertEqual(records[0].relationship_type, 'rfc6492')
        self.assertEqual(records[0].service_uri, 'https://testbed.krill.cloud/rfc6492/testbed/')
        self.assertIsNone(records[0].last_exchange_at)

    def test_parse_krill_child_link_records_merges_discovery_info_and_connections(self):
        records = parse_krill_child_link_records(
            KRILL_CA_METADATA_JSON,
            child_info_payloads={'edge-customer-01': KRILL_CHILD_INFO_JSON},
            child_connections_payload=KRILL_CHILD_CONNECTIONS_JSON,
        )

        self.assertEqual(len(records), 2)
        active_record = records[0]
        suspended_record = records[1]

        self.assertEqual(active_record.child_handle, 'edge-customer-01')
        self.assertEqual(active_record.state, 'active')
        self.assertEqual(active_record.id_cert_hash, 'krill-child-id-cert-sha256')
        self.assertEqual(active_record.user_agent, 'krill/0.16.0')
        self.assertEqual(active_record.last_exchange_result, 'Success')
        self.assertEqual(active_record.entitled_resources.asn_resources, 'AS65010')
        self.assertTrue(active_record.listed_as_child)
        self.assertFalse(active_record.listed_as_suspended)

        self.assertEqual(suspended_record.child_handle, 'edge-customer-archive')
        self.assertEqual(suspended_record.state, 'suspended')
        self.assertTrue(suspended_record.listed_as_suspended)
        self.assertEqual(suspended_record.id_cert_hash, '')

    def test_parse_krill_resource_entitlement_records_builds_composed_family(self):
        records = parse_krill_resource_entitlement_records(
            ca_metadata_payload=KRILL_CA_METADATA_JSON,
            parent_status_payload=KRILL_PARENT_STATUSES_JSON,
            child_info_payloads={'edge-customer-01': KRILL_CHILD_INFO_JSON},
        )

        self.assertEqual(len(records), 4)
        self.assertEqual(
            [record.entitlement_source for record in records],
            [
                rpki_models.ImportedResourceEntitlementSource.CA,
                rpki_models.ImportedResourceEntitlementSource.PARENT,
                rpki_models.ImportedResourceEntitlementSource.PARENT_CLASS,
                rpki_models.ImportedResourceEntitlementSource.CHILD,
            ],
        )
        self.assertEqual(records[0].related_handle, 'netbox-rpki-dev')
        self.assertEqual(records[1].related_handle, 'testbed')
        self.assertEqual(records[2].class_name, '0')
        self.assertEqual(records[2].not_after, datetime(2027, 4, 12, 10, 0, tzinfo=timezone.utc))
        self.assertEqual(records[3].related_handle, 'edge-customer-01')
        self.assertEqual(records[3].ipv4_resources, '10.20.0.0/24')

    def test_parse_krill_resource_entitlement_records_skips_empty_sources(self):
        records = parse_krill_resource_entitlement_records(
            ca_metadata_payload={},
            parent_status_payload={'testbed': {'classes': []}},
            child_info_payloads={'edge-customer-01': {'state': 'active', 'entitled_resources': {}}},
        )

        self.assertEqual(records, [])

    def test_parse_krill_publication_point_records_normalizes_fixture(self):
        records = parse_krill_publication_point_records(
            repo_details_payload=KRILL_REPO_DETAILS_JSON,
            repo_status_payload=KRILL_REPO_STATUS_JSON,
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.service_uri, 'https://testbed.krill.cloud/rfc8181/netbox-rpki-dev/')
        self.assertEqual(record.publication_uri, 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/')
        self.assertEqual(record.rrdp_notification_uri, 'https://testbed.krill.cloud/rrdp/notification.xml')
        self.assertEqual(record.last_exchange_at, datetime.fromtimestamp(1775988000, tz=timezone.utc))
        self.assertEqual(record.next_exchange_before, datetime.fromtimestamp(1776024000, tz=timezone.utc))
        self.assertEqual(record.published_object_count, 2)
        self.assertEqual(
            [published.uri for published in record.published_objects],
            [
                'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.mft',
                'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.crl',
            ],
        )

    def test_parse_krill_publication_point_records_accepts_status_only_payload(self):
        records = parse_krill_publication_point_records(
            repo_details_payload={},
            repo_status_payload={
                'last_exchange': {
                    'timestamp': 1775988000,
                    'uri': 'https://testbed.krill.cloud/rfc8181/netbox-rpki-dev/',
                    'result': 'Success',
                },
                'published': [],
            },
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].service_uri, 'https://testbed.krill.cloud/rfc8181/netbox-rpki-dev/')
        self.assertEqual(records[0].published_object_count, 0)

    def test_parse_krill_signed_object_records_normalizes_fixture(self):
        records = parse_krill_signed_object_records(
            repo_details_payload=KRILL_REPO_DETAILS_JSON,
            repo_status_payload=KRILL_REPO_STATUS_JSON,
        )

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].publication_uri, 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/')
        self.assertEqual(records[0].signed_object_uri, 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.mft')
        self.assertEqual(records[0].signed_object_type, rpki_models.SignedObjectType.MANIFEST)
        self.assertTrue(records[0].object_hash)
        self.assertEqual(records[1].signed_object_uri, 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.crl')
        self.assertEqual(records[1].signed_object_type, rpki_models.SignedObjectType.CRL)
        self.assertNotEqual(records[0].object_hash, records[1].object_hash)
