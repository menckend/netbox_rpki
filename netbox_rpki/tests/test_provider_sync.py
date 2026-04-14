from datetime import timedelta
from unittest.mock import call, patch

from django.db import IntegrityError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services import ProviderSyncError, sync_provider_account
from netbox_rpki.services.lifecycle_reporting import (
    LIFECYCLE_HEALTH_DEFAULTS,
    LIFECYCLE_HEALTH_SUMMARY_SCHEMA_VERSION,
    build_provider_lifecycle_health_summary,
    resolve_lifecycle_health_policy,
)
from netbox_rpki.services.provider_sync_contract import (
    PROVIDER_SYNC_FAMILY_ORDER,
    PROVIDER_SYNC_SUMMARY_SCHEMA_VERSION,
    build_provider_account_rollup,
    build_provider_account_pub_obs_rollup,
    build_provider_snapshot_diff_rollup,
    build_provider_snapshot_rollup,
    build_snapshot_signed_object_type_breakdown,
)
from netbox_rpki.services.provider_sync_evidence import build_certificate_observation_payload
from netbox_rpki.services.provider_sync_evidence import (
    build_certificate_observation_attention_summary,
    build_publication_point_attention_summary,
    build_signed_object_attention_summary,
)
from netbox_rpki.services.provider_sync_krill import (
    KrillCertificateObservationRecord,
    KrillCertificateObservationSourceRecord,
)
from netbox_rpki.services import provider_sync_diff as provider_sync_diff_service
from netbox_rpki.tests.base import PluginAPITestCase
from netbox_rpki.tests.krill_payloads import (
    KRILL_ASPAS_JSON,
    KRILL_CA_METADATA_JSON,
    KRILL_CHILD_CONNECTIONS_JSON,
    KRILL_CHILD_INFO_JSON,
    KRILL_PARENT_CONTACT_JSON,
    KRILL_PARENT_STATUSES_JSON,
    KRILL_REPO_DETAILS_JSON,
    KRILL_REPO_STATUS_JSON,
    KRILL_ROUTES_JSON,
)
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_certificate,
    create_test_external_object_reference,
    create_test_imported_roa_authorization,
    create_test_imported_certificate_observation,
    create_test_imported_publication_point,
    create_test_imported_signed_object,
    create_test_lifecycle_health_policy,
    create_test_organization,
    create_test_prefix,
    create_test_publication_point,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_signed_object,
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
        self.assertEqual(snapshot.summary_json['latest_snapshot_id'], snapshot.pk)
        self.assertEqual(snapshot.summary_json['latest_snapshot_name'], snapshot.name)
        self.assertEqual(snapshot.summary_json['latest_snapshot_status'], rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(snapshot.summary_json['latest_snapshot_completed_at'], sync_run.completed_at.isoformat())
        rollup = build_provider_account_rollup(self.provider_account, summary=snapshot.summary_json)
        snapshot_rollup = build_provider_snapshot_rollup(snapshot)
        self.assertEqual(rollup['latest_snapshot_id'], snapshot.pk)
        self.assertEqual(rollup['family_count'], len(rollup['family_rollups']))
        self.assertIn(rpki_models.ProviderSyncFamilyStatus.COMPLETED, rollup['family_status_counts'])
        self.assertEqual(rollup['family_status_counts'][rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED], 8)
        self.assertEqual(snapshot_rollup['family_count'], len(snapshot_rollup['family_rollups']))
        self.assertEqual(snapshot_rollup['family_rollups'][0]['freshness_status'], 'fresh')
        aspa_rollup = next(
            entry
            for entry in rollup['family_rollups']
            if entry['family'] == rpki_models.ProviderSyncFamily.ASPAS
        )
        self.assertEqual(aspa_rollup['status'], rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED)
        self.assertEqual(aspa_rollup['capability_status'], rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED)
        self.assertEqual(aspa_rollup['capability_mode'], 'provider_limited')
        self.assertIn('hosted ROA authorizations only', aspa_rollup['capability_reason'])

    def test_resolve_lifecycle_health_policy_falls_back_to_built_in_defaults(self):
        self.assertIsNone(resolve_lifecycle_health_policy(provider_account=self.provider_account))

        summary = build_provider_lifecycle_health_summary(self.provider_account)

        self.assertEqual(summary['summary_schema_version'], LIFECYCLE_HEALTH_SUMMARY_SCHEMA_VERSION)
        self.assertEqual(summary['policy']['source'], 'built_in_default')
        self.assertEqual(summary['policy']['policy_id'], None)
        self.assertEqual(summary['policy']['thresholds'], LIFECYCLE_HEALTH_DEFAULTS)

    def test_provider_override_policy_beats_organization_default(self):
        create_test_lifecycle_health_policy(
            name='Organization Default Lifecycle Policy',
            organization=self.organization,
            sync_stale_after_minutes=180,
        )
        provider_override = create_test_lifecycle_health_policy(
            name='Provider Override Lifecycle Policy',
            organization=self.organization,
            provider_account=self.provider_account,
            sync_stale_after_minutes=15,
        )

        resolved_policy = resolve_lifecycle_health_policy(provider_account=self.provider_account)
        summary = build_provider_lifecycle_health_summary(self.provider_account)

        self.assertEqual(resolved_policy, provider_override)
        self.assertEqual(summary['policy']['policy_id'], provider_override.pk)
        self.assertEqual(summary['policy']['source'], 'provider_account_override')
        self.assertEqual(summary['policy']['thresholds']['sync_stale_after_minutes'], 15)

    def test_disabled_provider_override_falls_back_to_organization_default(self):
        organization_default = create_test_lifecycle_health_policy(
            name='Enabled Organization Default Lifecycle Policy',
            organization=self.organization,
            sync_stale_after_minutes=90,
        )
        create_test_lifecycle_health_policy(
            name='Disabled Provider Override Lifecycle Policy',
            organization=self.organization,
            provider_account=self.provider_account,
            enabled=False,
            sync_stale_after_minutes=5,
        )

        resolved_policy = resolve_lifecycle_health_policy(provider_account=self.provider_account)
        summary = build_provider_lifecycle_health_summary(self.provider_account)

        self.assertEqual(resolved_policy, organization_default)
        self.assertEqual(summary['policy']['policy_id'], organization_default.pk)
        self.assertEqual(summary['policy']['source'], 'organization_default')
        self.assertEqual(summary['policy']['thresholds']['sync_stale_after_minutes'], 90)

    def test_sync_provider_account_reuses_arin_external_reference_across_snapshots(self):
        with patch('netbox_rpki.services.provider_sync._fetch_arin_roa_xml', return_value=ARIN_ROA_XML):
            _, first_snapshot = sync_provider_account(self.provider_account)

        first_import = first_snapshot.imported_roa_authorizations.get(prefix_cidr_text='192.0.2.0/24')
        first_reference = first_import.external_reference

        with patch('netbox_rpki.services.provider_sync._fetch_arin_roa_xml', return_value=ARIN_ROA_XML):
            _, second_snapshot = sync_provider_account(self.provider_account)

        second_import = second_snapshot.imported_roa_authorizations.get(prefix_cidr_text='192.0.2.0/24')

        self.assertEqual(rpki_models.ExternalObjectReference.objects.count(), 2)
        self.assertEqual(second_import.external_reference_id, first_reference.pk)
        first_reference.refresh_from_db()
        self.assertEqual(first_reference.last_seen_provider_snapshot, second_snapshot)
        self.assertEqual(first_reference.last_seen_imported_authorization, second_import)

        snapshot_diff = rpki_models.ProviderSnapshotDiff.objects.get(
            base_snapshot=first_snapshot,
            comparison_snapshot=second_snapshot,
        )
        self.assertEqual(snapshot_diff.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(snapshot_diff.summary_json['totals']['records_unchanged'], 2)
        self.assertEqual(snapshot_diff.summary_json['totals']['records_changed'], 0)
        self.assertEqual(snapshot_diff.summary_json['totals']['records_added'], 0)
        self.assertEqual(snapshot_diff.summary_json['totals']['records_removed'], 0)
        self.assertEqual(snapshot_diff.items.count(), 0)

        diff_rollup = build_provider_snapshot_diff_rollup(snapshot_diff)
        self.assertEqual(diff_rollup['item_count'], 0)
        self.assertEqual(diff_rollup['family_count'], len(diff_rollup['family_rollups']))
        self.assertTrue(all(rollup['churn_status'] == 'steady' for rollup in diff_rollup['family_rollups']))

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
        customer_as = create_test_asn(65010)
        provider_as_1 = create_test_asn(65001)
        provider_as_2 = create_test_asn(65002)
        provider_as_3 = create_test_asn(65003)
        authored_resource_certificate = create_test_certificate(
            name='Provider Sync Authored Resource Certificate',
            rpki_org=provider_account.organization,
        )
        authored_publication_point = create_test_publication_point(
            name='Provider Sync Authored Publication Point',
            organization=provider_account.organization,
            publication_uri='rsync://testbed.krill.cloud/repo/netbox-rpki-dev/',
            rsync_base_uri='https://testbed.krill.cloud/rfc8181/netbox-rpki-dev/',
            rrdp_notify_uri='https://testbed.krill.cloud/rrdp/notification.xml',
        )
        authored_manifest_signed_object = create_test_signed_object(
            name='Provider Sync Authored Manifest',
            organization=provider_account.organization,
            publication_point=authored_publication_point,
            resource_certificate=authored_resource_certificate,
            object_type=rpki_models.SignedObjectType.MANIFEST,
            object_uri='rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.mft',
        )
        authored_crl_signed_object = create_test_signed_object(
            name='Provider Sync Authored CRL',
            organization=provider_account.organization,
            publication_point=authored_publication_point,
            resource_certificate=authored_resource_certificate,
            object_type=rpki_models.SignedObjectType.CRL,
            object_uri='rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.crl',
        )

        with patch('netbox_rpki.services.provider_sync._fetch_krill_routes_json', return_value=KRILL_ROUTES_JSON), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_aspas_json',
            return_value=KRILL_ASPAS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_ca_metadata_json',
            return_value=KRILL_CA_METADATA_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_parent_statuses_json',
            return_value=KRILL_PARENT_STATUSES_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_parent_contact_payloads',
            return_value={'testbed': KRILL_PARENT_CONTACT_JSON},
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_child_info_payloads',
            return_value={'edge-customer-01': KRILL_CHILD_INFO_JSON},
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_child_connections_json',
            return_value=KRILL_CHILD_CONNECTIONS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_repo_details_json',
            return_value=KRILL_REPO_DETAILS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_repo_status_json',
            return_value=KRILL_REPO_STATUS_JSON,
        ):
            sync_run, snapshot = sync_provider_account(provider_account)

        imported = list(snapshot.imported_roa_authorizations.select_related('external_reference').order_by('prefix_cidr_text'))
        imported_aspas = list(snapshot.imported_aspas.select_related('external_reference').order_by('customer_as_value'))
        imported_ca_metadata = list(snapshot.imported_ca_metadata_records.select_related('external_reference'))
        imported_parent_links = list(snapshot.imported_parent_links.select_related('external_reference'))
        imported_child_links = list(snapshot.imported_child_links.select_related('external_reference').order_by('child_handle'))
        imported_resource_entitlements = list(snapshot.imported_resource_entitlements.select_related('external_reference').order_by('entitlement_source', 'related_handle', 'class_name'))
        imported_publication_points = list(snapshot.imported_publication_points.select_related('external_reference'))
        imported_signed_objects = list(
            snapshot.imported_signed_objects.select_related('external_reference', 'publication_point').order_by('signed_object_uri')
        )
        imported_certificate_observations = list(
            snapshot.imported_certificate_observations.select_related(
                'external_reference',
                'publication_point',
                'signed_object',
            ).order_by('certificate_key')
        )
        self.assertEqual(sync_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(sync_run.records_fetched, 18)
        self.assertEqual(sync_run.records_imported, 18)
        self.assertEqual(imported[0].prefix, prefix_v4)
        self.assertEqual(imported[0].origin_asn, origin_asn)
        self.assertEqual(imported[0].external_object_id, '10.10.0.0/24|24|65000')
        self.assertIsNotNone(imported[0].external_reference)
        self.assertEqual(imported[0].external_reference.provider_identity, '10.10.0.0/24|24|65000')
        self.assertEqual(imported[0].payload_json['ca_handle'], 'netbox-rpki-dev')
        self.assertEqual(imported[1].prefix, prefix_v6)
        self.assertEqual(imported[1].address_family, rpki_models.AddressFamily.IPV6)
        self.assertEqual(len(imported_aspas), 2)
        self.assertEqual(imported_aspas[0].customer_as, origin_asn)
        self.assertEqual(imported_aspas[0].external_object_id, 'AS65000')
        self.assertIsNotNone(imported_aspas[0].external_reference)
        self.assertEqual(imported_aspas[0].external_reference.object_type, rpki_models.ExternalObjectType.ASPA)
        imported_providers = list(imported_aspas[0].provider_authorizations.order_by('provider_as_value', 'address_family'))
        self.assertEqual([provider.provider_as for provider in imported_providers], [provider_as_1, provider_as_2, provider_as_3])
        self.assertEqual([provider.address_family for provider in imported_providers], ['', rpki_models.AddressFamily.IPV4, rpki_models.AddressFamily.IPV6])
        self.assertEqual(imported_aspas[1].customer_as, customer_as)
        self.assertEqual(imported_aspas[1].provider_authorizations.count(), 0)
        self.assertEqual(len(imported_ca_metadata), 1)
        self.assertEqual(imported_ca_metadata[0].ca_handle, 'netbox-rpki-dev')
        self.assertIsNotNone(imported_ca_metadata[0].external_reference)
        self.assertEqual(len(imported_parent_links), 1)
        self.assertEqual(imported_parent_links[0].parent_handle, 'testbed')
        self.assertEqual(len(imported_child_links), 2)
        self.assertEqual([row.child_handle for row in imported_child_links], ['edge-customer-01', 'edge-customer-archive'])
        self.assertEqual(len(imported_resource_entitlements), 4)
        self.assertEqual(imported_resource_entitlements[0].external_reference.object_type, rpki_models.ExternalObjectType.RESOURCE_ENTITLEMENT)
        self.assertEqual(len(imported_publication_points), 1)
        self.assertEqual(imported_publication_points[0].published_object_count, 2)
        self.assertEqual(imported_publication_points[0].authored_publication_point, authored_publication_point)
        self.assertEqual(imported_publication_points[0].payload_json['authored_linkage']['status'], 'linked')
        self.assertEqual(imported_publication_points[0].payload_json['evidence_summary']['published_object_count'], 2)
        self.assertEqual(imported_publication_points[0].payload_json['published_object_type_counts']['manifest'], 1)
        self.assertEqual(imported_publication_points[0].payload_json['published_object_type_counts']['crl'], 1)
        self.assertEqual(len(imported_signed_objects), 2)
        self.assertEqual(len(imported_certificate_observations), 3)
        self.assertEqual(
            {row.signed_object_type for row in imported_signed_objects},
            {
                rpki_models.SignedObjectType.MANIFEST,
                rpki_models.SignedObjectType.CRL,
            },
        )
        manifest_signed_object = next(
            row for row in imported_signed_objects if row.signed_object_type == rpki_models.SignedObjectType.MANIFEST
        )
        crl_signed_object = next(
            row for row in imported_signed_objects if row.signed_object_type == rpki_models.SignedObjectType.CRL
        )
        self.assertEqual(manifest_signed_object.publication_point, imported_publication_points[0])
        self.assertEqual(crl_signed_object.publication_point, imported_publication_points[0])
        self.assertEqual(manifest_signed_object.authored_signed_object, authored_manifest_signed_object)
        self.assertEqual(crl_signed_object.authored_signed_object, authored_crl_signed_object)
        self.assertEqual(manifest_signed_object.payload_json['publication_linkage']['status'], 'linked')
        self.assertEqual(manifest_signed_object.payload_json['authored_linkage']['status'], 'linked')
        self.assertEqual(manifest_signed_object.payload_json['evidence_summary']['signed_object_type'], 'manifest')
        self.assertEqual(crl_signed_object.payload_json['evidence_summary']['crl_freshness_status'], 'stale')
        signed_object_certificate_observations = [
            row
            for row in imported_certificate_observations
            if row.signed_object_uri
        ]
        self.assertGreaterEqual(len(signed_object_certificate_observations), 1)
        self.assertTrue(all(row.signed_object is not None for row in signed_object_certificate_observations))
        self.assertTrue(
            {row.signed_object for row in signed_object_certificate_observations}.issubset(
                {manifest_signed_object, crl_signed_object}
            )
        )
        linked_publication_point_certificate_observations = [
            row
            for row in imported_certificate_observations
            if row.publication_point is not None
        ]
        self.assertGreaterEqual(len(linked_publication_point_certificate_observations), 1)
        self.assertEqual(
            {row.publication_point for row in linked_publication_point_certificate_observations},
            {imported_publication_points[0]},
        )
        self.assertTrue(all('evidence_summary' in row.payload_json for row in imported_certificate_observations))
        self.assertTrue(all('source_summary' in row.payload_json for row in imported_certificate_observations))
        self.assertTrue(all(row.payload_json['source_summary']['source_count'] >= 1 for row in imported_certificate_observations))
        self.assertTrue(all(row.payload_json['signed_object_linkage']['status'] in {'linked', 'unknown', 'unmatched'} for row in imported_certificate_observations))
        provider_account.refresh_from_db()
        self.assertEqual(snapshot.summary_json['summary_schema_version'], PROVIDER_SYNC_SUMMARY_SCHEMA_VERSION)
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS]['label'],
            'ROA Authorizations',
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS]['family_kind'],
            'control_plane',
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.ASPAS]['records_imported'],
            2,
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CA_METADATA]['records_imported'],
            1,
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.PARENT_LINKS]['records_imported'],
            1,
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CHILD_LINKS]['records_imported'],
            2,
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS]['records_imported'],
            4,
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.PUBLICATION_POINTS]['records_imported'],
            1,
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.PUBLICATION_POINTS]['family_kind'],
            'publication_observation',
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY]['records_imported'],
            2,
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['status'],
            rpki_models.ProviderSyncFamilyStatus.LIMITED,
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['capability_status'],
            rpki_models.ProviderSyncFamilyStatus.LIMITED,
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['capability_mode'],
            'derived',
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['family_kind'],
            'publication_observation',
        )
        self.assertEqual(snapshot.summary_json['latest_snapshot_id'], snapshot.pk)
        self.assertEqual(snapshot.summary_json['latest_snapshot_name'], snapshot.name)
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['evidence_source'],
            'repository_publication',
        )
        self.assertIn(
            'Repository-derived certificate observation is linked to publication points and signed objects',
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['capability_reason'],
        )
        self.assertIn(
            'published_signed_objects',
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['capability_sources'],
        )
        self.assertIn(
            'publication_point_link',
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['capability_sources'],
        )
        self.assertIn(
            'signed_object_link',
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['capability_sources'],
        )
        self.assertIn(
            'repo_status',
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['capability_sources'],
        )
        self.assertEqual(
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['records_imported'],
            3,
        )
        self.assertEqual(snapshot.summary_json['family_rollups'][0]['freshness_status'], 'fresh')
        self.assertEqual(snapshot.summary_json['family_rollups'][0]['churn_status'], 'steady')
        self.assertIn(
            'linked to publication points and signed objects',
            snapshot.summary_json['families'][rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY]['capability_reason'],
        )
        self.assertEqual(snapshot.summary_json['records_imported'], 18)
        self.assertEqual(snapshot.summary_json['route_records_imported'], 2)
        self.assertEqual(snapshot.summary_json['signed_object_records_imported'], 2)
        self.assertEqual(snapshot.summary_json['certificate_records_imported'], 3)
        self.assertEqual(provider_account.last_sync_summary_json['ca_handle'], 'netbox-rpki-dev')
        self.assertEqual(provider_account.last_sync_summary_json['aspa_records_imported'], 2)

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
        create_test_asn(65001)
        create_test_asn(65002)
        create_test_asn(65003)
        create_test_asn(65010)

        with patch('netbox_rpki.services.provider_sync._fetch_krill_routes_json', return_value=KRILL_ROUTES_JSON), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_aspas_json',
            return_value=KRILL_ASPAS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_ca_metadata_json',
            return_value=KRILL_CA_METADATA_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_parent_statuses_json',
            return_value=KRILL_PARENT_STATUSES_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_parent_contact_payloads',
            return_value={'testbed': KRILL_PARENT_CONTACT_JSON},
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_child_info_payloads',
            return_value={'edge-customer-01': KRILL_CHILD_INFO_JSON},
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_child_connections_json',
            return_value=KRILL_CHILD_CONNECTIONS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_repo_details_json',
            return_value=KRILL_REPO_DETAILS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_repo_status_json',
            return_value=KRILL_REPO_STATUS_JSON,
        ):
            _, first_snapshot = sync_provider_account(provider_account)
        first_import = first_snapshot.imported_roa_authorizations.get(prefix_cidr_text='10.10.0.0/24')
        first_reference = first_import.external_reference
        first_aspa_import = first_snapshot.imported_aspas.get(customer_as_value=65000)
        first_aspa_reference = first_aspa_import.external_reference

        with patch('netbox_rpki.services.provider_sync._fetch_krill_routes_json', return_value=KRILL_ROUTES_JSON), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_aspas_json',
            return_value=KRILL_ASPAS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_ca_metadata_json',
            return_value=KRILL_CA_METADATA_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_parent_statuses_json',
            return_value=KRILL_PARENT_STATUSES_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_parent_contact_payloads',
            return_value={'testbed': KRILL_PARENT_CONTACT_JSON},
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_child_info_payloads',
            return_value={'edge-customer-01': KRILL_CHILD_INFO_JSON},
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_child_connections_json',
            return_value=KRILL_CHILD_CONNECTIONS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_repo_details_json',
            return_value=KRILL_REPO_DETAILS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_repo_status_json',
            return_value=KRILL_REPO_STATUS_JSON,
        ):
            _, second_snapshot = sync_provider_account(provider_account)
        second_import = second_snapshot.imported_roa_authorizations.get(prefix_cidr_text='10.10.0.0/24')
        second_aspa_import = second_snapshot.imported_aspas.get(customer_as_value=65000)

        self.assertEqual(rpki_models.ExternalObjectReference.objects.count(), 18)
        self.assertEqual(second_import.external_reference_id, first_reference.pk)
        first_reference.refresh_from_db()
        self.assertEqual(first_reference.last_seen_provider_snapshot, second_snapshot)
        self.assertEqual(first_reference.last_seen_imported_authorization, second_import)
        self.assertEqual(second_aspa_import.external_reference_id, first_aspa_reference.pk)
        first_aspa_reference.refresh_from_db()
        self.assertEqual(first_aspa_reference.last_seen_provider_snapshot, second_snapshot)
        self.assertEqual(first_aspa_reference.last_seen_imported_aspa, second_aspa_import)
        snapshot_diff = rpki_models.ProviderSnapshotDiff.objects.get(
            base_snapshot=first_snapshot,
            comparison_snapshot=second_snapshot,
        )
        self.assertEqual(snapshot_diff.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(
            snapshot_diff.summary_json['totals']['records_unchanged'],
            18,
        )
        self.assertEqual(snapshot_diff.items.count(), 0)
        self.assertEqual(second_snapshot.summary_json['latest_snapshot_id'], second_snapshot.pk)
        self.assertEqual(second_snapshot.summary_json['latest_snapshot_name'], second_snapshot.name)
        self.assertEqual(second_snapshot.summary_json['latest_diff_id'], snapshot_diff.pk)
        self.assertEqual(second_snapshot.summary_json['latest_diff_name'], snapshot_diff.name)
        diff_rollup = build_provider_snapshot_diff_rollup(snapshot_diff)
        self.assertEqual(diff_rollup['item_count'], 0)
        self.assertEqual(diff_rollup['family_count'], len(diff_rollup['family_rollups']))
        self.assertTrue(all(rollup['churn_status'] == 'steady' for rollup in diff_rollup['family_rollups']))

    def test_sync_provider_account_generates_changed_snapshot_diff_items(self):
        provider_account = create_test_provider_account(
            name='Krill Diff Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='netbox-rpki-dev',
            api_base_url='https://localhost:3001',
            api_key='krill-token',
            org_handle='ORG-KRILL-DIFF',
        )
        create_test_prefix('10.10.0.0/24')
        create_test_prefix('2001:db8:100::/48')
        create_test_asn(65000)
        create_test_asn(65001)
        create_test_asn(65002)
        create_test_asn(65003)
        create_test_asn(65010)

        with patch('netbox_rpki.services.provider_sync._fetch_krill_routes_json', return_value=KRILL_ROUTES_JSON), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_aspas_json',
            return_value=KRILL_ASPAS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_ca_metadata_json',
            return_value=KRILL_CA_METADATA_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_parent_statuses_json',
            return_value=KRILL_PARENT_STATUSES_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_parent_contact_payloads',
            return_value={'testbed': KRILL_PARENT_CONTACT_JSON},
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_child_info_payloads',
            return_value={'edge-customer-01': KRILL_CHILD_INFO_JSON},
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_child_connections_json',
            return_value=KRILL_CHILD_CONNECTIONS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_repo_details_json',
            return_value=KRILL_REPO_DETAILS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_repo_status_json',
            return_value=KRILL_REPO_STATUS_JSON,
        ):
            _, first_snapshot = sync_provider_account(provider_account)

        changed_routes = [dict(row) for row in KRILL_ROUTES_JSON]
        changed_routes[0] = dict(changed_routes[0])
        changed_routes[0]['comment'] = 'netbox_rpki sample IPv4 ROA changed'
        changed_aspas = [dict(row) for row in KRILL_ASPAS_JSON[:-1]]
        changed_ca_metadata = dict(KRILL_CA_METADATA_JSON)
        changed_ca_metadata['repo_info'] = dict(KRILL_CA_METADATA_JSON['repo_info'])
        changed_ca_metadata['repo_info']['sia_base'] = 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev-alt/'
        changed_parent_statuses = dict(KRILL_PARENT_STATUSES_JSON)
        changed_parent_statuses['testbed'] = dict(KRILL_PARENT_STATUSES_JSON['testbed'])
        changed_parent_statuses['testbed']['last_exchange'] = dict(KRILL_PARENT_STATUSES_JSON['testbed']['last_exchange'])
        changed_parent_statuses['testbed']['last_exchange']['result'] = 'Warning'
        changed_child_info = dict(KRILL_CHILD_INFO_JSON)
        changed_child_info['entitled_resources'] = dict(KRILL_CHILD_INFO_JSON['entitled_resources'])
        changed_child_info['entitled_resources']['ipv4'] = '10.30.0.0/24'
        changed_repo_status = dict(KRILL_REPO_STATUS_JSON)
        changed_repo_status['last_exchange'] = dict(KRILL_REPO_STATUS_JSON['last_exchange'])
        changed_repo_status['next_exchange_before'] = KRILL_REPO_STATUS_JSON['next_exchange_before'] + 900
        changed_repo_status['published'] = [dict(row) for row in KRILL_REPO_STATUS_JSON['published']]
        changed_repo_status['published'][0]['base64'] = 'MIIKRILLMFT-ALT=='

        with patch('netbox_rpki.services.provider_sync._fetch_krill_routes_json', return_value=changed_routes), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_aspas_json',
            return_value=changed_aspas,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_ca_metadata_json',
            return_value=changed_ca_metadata,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_parent_statuses_json',
            return_value=changed_parent_statuses,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_parent_contact_payloads',
            return_value={'testbed': KRILL_PARENT_CONTACT_JSON},
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_child_info_payloads',
            return_value={'edge-customer-01': changed_child_info},
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_child_connections_json',
            return_value=KRILL_CHILD_CONNECTIONS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_repo_details_json',
            return_value=KRILL_REPO_DETAILS_JSON,
        ), patch(
            'netbox_rpki.services.provider_sync._fetch_krill_repo_status_json',
            return_value=changed_repo_status,
        ):
            _, second_snapshot = sync_provider_account(provider_account)

        snapshot_diff = rpki_models.ProviderSnapshotDiff.objects.get(
            base_snapshot=first_snapshot,
            comparison_snapshot=second_snapshot,
        )
        self.assertEqual(
            snapshot_diff.summary_json['families'][rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS]['records_changed'],
            1,
        )
        self.assertEqual(
            snapshot_diff.summary_json['families'][rpki_models.ProviderSyncFamily.ASPAS]['records_removed'],
            1,
        )
        self.assertEqual(
            snapshot_diff.summary_json['families'][rpki_models.ProviderSyncFamily.CA_METADATA]['records_changed'],
            1,
        )
        self.assertEqual(
            snapshot_diff.summary_json['families'][rpki_models.ProviderSyncFamily.PARENT_LINKS]['records_changed'],
            1,
        )
        self.assertEqual(
            snapshot_diff.summary_json['families'][rpki_models.ProviderSyncFamily.CHILD_LINKS]['records_changed'],
            1,
        )
        self.assertEqual(
            snapshot_diff.summary_json['families'][rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS]['records_changed'],
            1,
        )
        self.assertEqual(
            snapshot_diff.summary_json['families'][rpki_models.ProviderSyncFamily.PUBLICATION_POINTS]['records_changed'],
            1,
        )
        self.assertEqual(
            snapshot_diff.summary_json['families'][rpki_models.ProviderSyncFamily.PUBLICATION_POINTS]['family_kind'],
            'publication_observation',
        )
        self.assertEqual(snapshot_diff.summary_json['family_rollups'][0]['freshness_status'], 'fresh')
        self.assertEqual(snapshot_diff.summary_json['family_rollups'][0]['churn_status'], 'active')
        self.assertEqual(
            set(snapshot_diff.items.values_list('change_type', flat=True)),
            {
                rpki_models.ProviderSnapshotDiffChangeType.CHANGED,
                rpki_models.ProviderSnapshotDiffChangeType.REMOVED,
            },
        )
        self.assertTrue(
            {
                rpki_models.ProviderSyncFamily.CA_METADATA,
                rpki_models.ProviderSyncFamily.PARENT_LINKS,
                rpki_models.ProviderSyncFamily.CHILD_LINKS,
                rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS,
                rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
                rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY,
            }.issubset(set(snapshot_diff.items.values_list('object_family', flat=True)))
        )
        self.assertEqual(second_snapshot.summary_json['latest_snapshot_id'], second_snapshot.pk)
        self.assertEqual(second_snapshot.summary_json['latest_snapshot_name'], second_snapshot.name)
        self.assertEqual(second_snapshot.summary_json['latest_diff_id'], snapshot_diff.pk)
        self.assertEqual(second_snapshot.summary_json['latest_diff_name'], snapshot_diff.name)
        diff_rollup = build_provider_snapshot_diff_rollup(snapshot_diff)
        self.assertEqual(diff_rollup['family_status_counts'][rpki_models.ProviderSyncFamilyStatus.COMPLETED], 8)
        self.assertEqual(diff_rollup['family_status_counts'][rpki_models.ProviderSyncFamilyStatus.LIMITED], 1)
        publication_points_rollup = next(
            rollup
            for rollup in diff_rollup['family_rollups']
            if rollup['family'] == rpki_models.ProviderSyncFamily.PUBLICATION_POINTS
        )
        self.assertEqual(publication_points_rollup['records_changed'], 1)
        self.assertEqual(publication_points_rollup['churn_status'], 'active')
        self.assertEqual(publication_points_rollup['churn_text'], '0 added, 0 removed, 1 changed')

    def test_build_provider_account_rollup_defaults_sparse_summary_and_hides_invisible_related_objects(self):
        provider_account = create_test_provider_account(
            name='Rollup Visibility Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            sync_enabled=True,
            last_sync_summary_json={
                'latest_snapshot_id': 101,
                'latest_snapshot_name': 'Hidden snapshot',
                'latest_snapshot_completed_at': '2026-04-13T00:00:00+00:00',
                'latest_diff_id': 202,
                'latest_diff_name': 'Visible diff',
            },
        )

        rollup = build_provider_account_rollup(
            provider_account,
            summary={
                'latest_snapshot_id': 101,
                'latest_snapshot_name': 'Hidden snapshot',
                'latest_snapshot_completed_at': '2026-04-13T00:00:00+00:00',
                'latest_diff_id': 202,
                'latest_diff_name': 'Visible diff',
            },
            visible_snapshot_ids=set(),
            visible_diff_ids={202},
        )

        self.assertEqual(rollup['family_count'], len(PROVIDER_SYNC_FAMILY_ORDER))
        self.assertEqual(rollup['family_status_counts'][rpki_models.ProviderSyncFamilyStatus.PENDING], 1)
        self.assertEqual(
            rollup['family_status_counts'][rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED],
            len(PROVIDER_SYNC_FAMILY_ORDER) - 1,
        )
        self.assertIsNone(rollup['latest_snapshot_id'])
        self.assertEqual(rollup['latest_snapshot_name'], '')
        self.assertEqual(rollup['latest_snapshot_completed_at'], '')
        self.assertEqual(rollup['latest_diff_id'], 202)
        self.assertEqual(rollup['latest_diff_name'], 'Visible diff')
        self.assertIn('lifecycle_health_summary', rollup)
        self.assertEqual(rollup['lifecycle_health_summary']['summary_schema_version'], LIFECYCLE_HEALTH_SUMMARY_SCHEMA_VERSION)

    def test_build_provider_lifecycle_health_summary_hides_invisible_related_objects(self):
        provider_account = create_test_provider_account(
            name='Lifecycle Visibility Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            sync_enabled=True,
            last_sync_summary_json={
                'latest_snapshot_id': 101,
                'latest_snapshot_name': 'Hidden snapshot',
                'latest_snapshot_completed_at': '2026-04-13T00:00:00+00:00',
                'latest_diff_id': 202,
                'latest_diff_name': 'Visible diff',
                'records_added': 4,
                'records_removed': 2,
                'records_changed': 1,
            },
        )

        summary = build_provider_lifecycle_health_summary(
            provider_account,
            visible_snapshot_ids=set(),
            visible_diff_ids={202},
        )

        self.assertEqual(summary['summary_schema_version'], LIFECYCLE_HEALTH_SUMMARY_SCHEMA_VERSION)
        self.assertIsNone(summary['diff']['latest_snapshot_id'])
        self.assertEqual(summary['diff']['latest_snapshot_name'], '')
        self.assertEqual(summary['diff']['latest_snapshot_completed_at'], '')
        self.assertEqual(summary['diff']['latest_diff_id'], 202)
        self.assertEqual(summary['diff']['latest_diff_name'], 'Visible diff')
        self.assertEqual(summary['diff']['records_added'], 4)
        self.assertEqual(summary['diff']['records_removed'], 2)
        self.assertEqual(summary['diff']['records_changed'], 1)

    def test_build_provider_snapshot_diff_preserves_certificate_observation_linkage_state(self):
        provider_account = create_test_provider_account(
            name='Krill Observation Diff Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='netbox-rpki-dev',
            api_base_url='https://localhost:3001',
            api_key='krill-token',
            org_handle='ORG-KRILL-OBS-DIFF',
        )
        base_snapshot = create_test_provider_snapshot(
            name='Observation Base Snapshot',
            organization=self.organization,
            provider_account=provider_account,
            provider_name='Krill',
        )
        comparison_snapshot = create_test_provider_snapshot(
            name='Observation Comparison Snapshot',
            organization=self.organization,
            provider_account=provider_account,
            provider_name='Krill',
        )

        base_publication_point = create_test_imported_publication_point(
            provider_snapshot=base_snapshot,
            organization=self.organization,
            publication_uri='rsync://example.invalid/repo/base/',
            service_uri='rsync://example.invalid/repo/base/',
            external_object_id='base-publication-point',
        )
        base_signed_object = create_test_imported_signed_object(
            provider_snapshot=base_snapshot,
            organization=self.organization,
            publication_point=base_publication_point,
            publication_uri=base_publication_point.publication_uri,
            signed_object_uri='rsync://example.invalid/repo/base/example.mft',
            signed_object_type=rpki_models.SignedObjectType.MANIFEST,
            object_hash='base-object-hash',
            external_object_id='base-signed-object',
        )
        create_test_imported_certificate_observation(
            provider_snapshot=base_snapshot,
            organization=self.organization,
            publication_point=base_publication_point,
            signed_object=base_signed_object,
            certificate_key='base-certificate-key',
            publication_uri=base_publication_point.publication_uri,
            signed_object_uri=base_signed_object.signed_object_uri,
            external_object_id='base-certificate-key',
        )

        comparison_publication_point = create_test_imported_publication_point(
            provider_snapshot=comparison_snapshot,
            organization=self.organization,
            publication_uri='rsync://example.invalid/repo/base/',
            service_uri='rsync://example.invalid/repo/base/',
            external_object_id='comparison-publication-point',
        )
        comparison_signed_object = create_test_imported_signed_object(
            provider_snapshot=comparison_snapshot,
            organization=self.organization,
            publication_point=comparison_publication_point,
            publication_uri=comparison_publication_point.publication_uri,
            signed_object_uri='rsync://example.invalid/repo/base/example.crl',
            signed_object_type=rpki_models.SignedObjectType.CRL,
            object_hash='comparison-object-hash',
            external_object_id='comparison-signed-object',
        )
        create_test_imported_certificate_observation(
            provider_snapshot=comparison_snapshot,
            organization=self.organization,
            publication_point=comparison_publication_point,
            signed_object=comparison_signed_object,
            certificate_key='base-certificate-key',
            publication_uri=comparison_publication_point.publication_uri,
            signed_object_uri=comparison_signed_object.signed_object_uri,
            external_object_id='base-certificate-key',
        )

        snapshot_diff = provider_sync_diff_service.build_provider_snapshot_diff(
            base_snapshot=base_snapshot,
            comparison_snapshot=comparison_snapshot,
        )

        observation_item = snapshot_diff.items.get(
            object_family=rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY,
            change_type=rpki_models.ProviderSnapshotDiffChangeType.CHANGED,
        )
        self.assertEqual(observation_item.before_state_json['publication_point_key'], base_publication_point.publication_key)
        self.assertEqual(
            observation_item.after_state_json['publication_point_key'],
            comparison_publication_point.publication_key,
        )
        self.assertEqual(observation_item.before_state_json['signed_object_key'], base_signed_object.signed_object_key)
        self.assertEqual(
            observation_item.after_state_json['signed_object_key'],
            comparison_signed_object.signed_object_key,
        )
        self.assertEqual(observation_item.publication_uri, comparison_publication_point.publication_uri)
        self.assertEqual(observation_item.signed_object_uri, comparison_signed_object.signed_object_uri)

    def test_build_provider_account_pub_obs_rollup_uses_latest_completed_snapshot(self):
        now = timezone.now()
        provider_account = create_test_provider_account(
            name='Krill Provider Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='netbox-rpki-dev',
            api_base_url='https://localhost:3001',
            org_handle='ORG-KRILL-ROLLUP',
        )
        stale_snapshot = create_test_provider_snapshot(
            name='Older Snapshot',
            organization=self.organization,
            provider_account=provider_account,
            fetched_at=now - timedelta(days=5),
        )
        latest_snapshot = create_test_provider_snapshot(
            name='Latest Snapshot',
            organization=self.organization,
            provider_account=provider_account,
            fetched_at=now,
        )
        create_test_imported_certificate_observation(
            provider_snapshot=stale_snapshot,
            organization=self.organization,
            certificate_key='older-cert',
            not_after=now + timedelta(days=2),
        )
        create_test_imported_certificate_observation(
            provider_snapshot=latest_snapshot,
            organization=self.organization,
            certificate_key='expiring-cert',
            not_after=now + timedelta(days=10),
        )
        create_test_imported_certificate_observation(
            provider_snapshot=latest_snapshot,
            organization=self.organization,
            certificate_key='stale-cert',
            is_stale=True,
            not_after=now + timedelta(days=10),
        )
        create_test_imported_certificate_observation(
            provider_snapshot=latest_snapshot,
            organization=self.organization,
            certificate_key='far-cert',
            not_after=now + timedelta(days=90),
        )
        create_test_imported_publication_point(
            provider_snapshot=latest_snapshot,
            organization=self.organization,
            publication_uri='rsync://example.invalid/repo/success/',
            last_exchange_result='Success',
        )
        create_test_imported_publication_point(
            provider_snapshot=latest_snapshot,
            organization=self.organization,
            publication_uri='rsync://example.invalid/repo/failure/',
            last_exchange_result='failed',
        )
        create_test_imported_publication_point(
            provider_snapshot=latest_snapshot,
            organization=self.organization,
            publication_uri='rsync://example.invalid/repo/blank/',
            last_exchange_result='',
        )

        rollup = build_provider_account_pub_obs_rollup(provider_account)

        self.assertIsNotNone(rollup)
        assert rollup is not None
        self.assertEqual(rollup['snapshot_id'], latest_snapshot.pk)
        self.assertEqual(rollup['snapshot_name'], latest_snapshot.name)
        self.assertEqual(rollup['certificate_observations']['total'], 3)
        self.assertEqual(rollup['certificate_observations']['stale'], 1)
        self.assertEqual(rollup['certificate_observations']['expiring_soon'], 1)
        self.assertEqual(rollup['publication_points']['total'], 3)
        self.assertEqual(rollup['publication_points']['exchange_not_ok'], 1)

    def test_build_provider_account_pub_obs_rollup_returns_none_without_completed_snapshot(self):
        provider_account = create_test_provider_account(
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='netbox-rpki-dev',
            org_handle='ORG-NO-SNAPSHOT',
        )
        create_test_provider_snapshot(
            organization=self.organization,
            provider_account=provider_account,
            status=rpki_models.ValidationRunStatus.FAILED,
        )

        self.assertIsNone(build_provider_account_pub_obs_rollup(provider_account))

    def test_build_snapshot_signed_object_type_breakdown_counts_each_type(self):
        snapshot = create_test_provider_snapshot(
            organization=self.organization,
            provider_account=create_test_provider_account(
                organization=self.organization,
                provider_type=rpki_models.ProviderType.KRILL,
                ca_handle='netbox-rpki-dev',
                org_handle='ORG-SIGNED-OBJECTS',
            ),
        )
        manifest_publication_point = create_test_imported_publication_point(
            provider_snapshot=snapshot,
            organization=self.organization,
            publication_uri='rsync://example.invalid/repo/manifest/',
        )
        crl_publication_point = create_test_imported_publication_point(
            provider_snapshot=snapshot,
            organization=self.organization,
            publication_uri='rsync://example.invalid/repo/crl/',
        )
        create_test_imported_signed_object(
            provider_snapshot=snapshot,
            organization=self.organization,
            publication_point=manifest_publication_point,
            publication_uri='rsync://example.invalid/repo/manifest/',
            signed_object_uri='rsync://example.invalid/repo/manifest/object-1.mft',
            signed_object_type=rpki_models.SignedObjectType.MANIFEST,
        )
        create_test_imported_signed_object(
            provider_snapshot=snapshot,
            organization=self.organization,
            publication_point=manifest_publication_point,
            publication_uri='rsync://example.invalid/repo/manifest/',
            signed_object_uri='rsync://example.invalid/repo/manifest/object-2.mft',
            signed_object_type=rpki_models.SignedObjectType.MANIFEST,
        )
        create_test_imported_signed_object(
            provider_snapshot=snapshot,
            organization=self.organization,
            publication_point=crl_publication_point,
            publication_uri='rsync://example.invalid/repo/crl/',
            signed_object_uri='rsync://example.invalid/repo/crl/object-1.crl',
            signed_object_type=rpki_models.SignedObjectType.CRL,
        )

        self.assertEqual(
            build_snapshot_signed_object_type_breakdown(snapshot),
            {
                rpki_models.SignedObjectType.CRL: 1,
                rpki_models.SignedObjectType.MANIFEST: 2,
            },
        )

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


class ProviderSyncEvidenceContractTestCase(TestCase):
    def test_build_certificate_observation_payload_flags_multi_source_ambiguity(self):
        observation_record = KrillCertificateObservationRecord(
            certificate_key='cert-key-1',
            certificate_uri='rsync://example.invalid/repo/example.cer',
            publication_uri='rsync://example.invalid/repo/',
            signed_object_uri='rsync://example.invalid/repo/example.mft',
            subject='CN=Example',
            issuer='CN=Issuer',
            serial_number='42',
            source_records=(
                KrillCertificateObservationSourceRecord(
                    observation_source=rpki_models.CertificateObservationSource.SIGNED_OBJECT_EE,
                    publication_uri='rsync://example.invalid/repo/',
                    signed_object_uri='rsync://example.invalid/repo/example.mft',
                ),
                KrillCertificateObservationSourceRecord(
                    observation_source=rpki_models.CertificateObservationSource.PARENT_ISSUED,
                    publication_uri='rsync://other.invalid/repo/',
                    related_handle='testbed',
                    class_name='0',
                ),
            ),
        )

        payload = build_certificate_observation_payload(
            observation_record,
            publication_point=None,
            publication_linkage_status='ambiguous',
            publication_linkage_reason='Multiple imported publication points matched the source identity.',
            signed_object=None,
            signed_object_linkage_status='unmatched',
            signed_object_linkage_reason='No imported signed object matched the source identity.',
        )

        self.assertEqual(payload['source_summary']['source_count'], 2)
        self.assertTrue(payload['source_summary']['has_multiple_sources'])
        self.assertTrue(payload['source_summary']['is_ambiguous'])
        self.assertIn('multiple_publication_uris', payload['source_summary']['ambiguity_reasons'])
        self.assertEqual(payload['publication_linkage']['status'], 'ambiguous')
        self.assertEqual(payload['signed_object_linkage']['status'], 'unmatched')

    def test_build_publication_point_attention_summary_flags_failed_exchange_and_overdue(self):
        now = timezone.now()
        publication_point = create_test_imported_publication_point(
            last_exchange_at=now - timedelta(minutes=30),
            last_exchange_result='failed',
            next_exchange_before=None,
            is_stale=True,
        )

        summary = build_publication_point_attention_summary(
            publication_point,
            now=now,
            thresholds={
                'publication_stale_after_minutes': 15,
            },
        )

        self.assertTrue(summary['stale'])
        self.assertEqual(summary['exchange']['status'], 'non_success')
        self.assertTrue(summary['exchange']['failed'])
        self.assertTrue(summary['exchange']['overdue'])
        self.assertTrue(summary['authored_linkage']['missing'])
        self.assertIn('exchange_failed', summary['attention_kinds'])
        self.assertIn('exchange_overdue', summary['attention_kinds'])
        self.assertIn('stale', summary['attention_kinds'])

    def test_build_signed_object_attention_summary_flags_missing_linkages(self):
        signed_object = create_test_imported_signed_object(
            payload_json={
                'publication_linkage': {
                    'status': 'unmatched',
                    'reason': 'No imported publication point matched the source identity.',
                },
                'authored_linkage': {
                    'status': 'unmatched',
                    'reason': 'No authored signed object matched the source identity.',
                },
                'evidence_summary': {
                    'publication_linkage_status': 'unmatched',
                    'authored_linkage_status': 'unmatched',
                },
            },
        )

        summary = build_signed_object_attention_summary(signed_object)

        self.assertTrue(summary['publication_linkage']['missing'])
        self.assertTrue(summary['authored_linkage']['missing'])
        self.assertEqual(summary['signed_object_type'], rpki_models.SignedObjectType.MANIFEST)
        self.assertIn('publication_linkage_missing', summary['attention_kinds'])
        self.assertIn('authored_linkage_missing', summary['attention_kinds'])

    def test_build_certificate_observation_attention_summary_flags_expiry_and_weak_linkage(self):
        now = timezone.now()
        observation_record = KrillCertificateObservationRecord(
            certificate_key='cert-key-2',
            certificate_uri='rsync://example.invalid/repo/example.cer',
            publication_uri='rsync://example.invalid/repo/',
            signed_object_uri='rsync://example.invalid/repo/example.mft',
            subject='CN=Example',
            issuer='CN=Issuer',
            serial_number='99',
            source_records=(
                KrillCertificateObservationSourceRecord(
                    observation_source=rpki_models.CertificateObservationSource.SIGNED_OBJECT_EE,
                    publication_uri='rsync://example.invalid/repo/',
                    signed_object_uri='rsync://example.invalid/repo/example.mft',
                ),
                KrillCertificateObservationSourceRecord(
                    observation_source=rpki_models.CertificateObservationSource.PARENT_ISSUED,
                    publication_uri='rsync://other.invalid/repo/',
                    related_handle='testbed',
                    class_name='0',
                ),
            ),
        )
        payload = build_certificate_observation_payload(
            observation_record,
            publication_point=None,
            publication_linkage_status='unmatched',
            publication_linkage_reason='No imported publication point matched the source identity.',
            signed_object=None,
            signed_object_linkage_status='unmatched',
            signed_object_linkage_reason='No imported signed object matched the source identity.',
        )
        certificate_observation = create_test_imported_certificate_observation(
            not_after=now + timedelta(days=5),
            payload_json=payload,
        )

        summary = build_certificate_observation_attention_summary(
            certificate_observation,
            now=now,
            thresholds={
                'certificate_expiry_warning_days': 30,
                'certificate_expired_grace_minutes': 0,
            },
        )

        self.assertFalse(summary['expiry']['expired'])
        self.assertTrue(summary['expiry']['expiring_soon'])
        self.assertTrue(summary['evidence']['is_ambiguous'])
        self.assertTrue(summary['evidence']['weak_linkage'])
        self.assertTrue(summary['publication_linkage']['missing'])
        self.assertTrue(summary['signed_object_linkage']['missing'])
        self.assertIn('expiring_soon', summary['attention_kinds'])
        self.assertIn('ambiguous', summary['attention_kinds'])
        self.assertIn('publication_linkage_missing', summary['attention_kinds'])

    def test_build_certificate_observation_attention_summary_flags_expired_objects(self):
        now = timezone.now()
        certificate_observation = create_test_imported_certificate_observation(
            not_after=now - timedelta(minutes=1),
            payload_json={
                'publication_linkage': {
                    'status': 'unmatched',
                    'reason': 'No imported publication point matched the source identity.',
                },
                'signed_object_linkage': {
                    'status': 'unmatched',
                    'reason': 'No imported signed object matched the source identity.',
                },
            },
        )

        summary = build_certificate_observation_attention_summary(
            certificate_observation,
            now=now,
            thresholds={
                'certificate_expiry_warning_days': 30,
                'certificate_expired_grace_minutes': 0,
            },
        )

        self.assertTrue(summary['expiry']['expired'])
        self.assertFalse(summary['expiry']['expiring_soon'])
        self.assertTrue(summary['evidence']['weak_linkage'])
        self.assertIn('expired', summary['attention_kinds'])
        self.assertIn('publication_linkage_missing', summary['attention_kinds'])


class ExternalObjectReferenceModelTestCase(TestCase):
    def test_external_object_reference_uses_plugin_detail_url(self):
        external_reference = create_test_external_object_reference(
            name='External Reference Detail URL',
            provider_identity='detail-url-provider-identity',
            external_object_id='detail-url-external-object',
        )

        self.assertEqual(
            external_reference.get_absolute_url(),
            reverse('plugins:netbox_rpki:externalobjectreference', args=[external_reference.pk]),
        )

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
