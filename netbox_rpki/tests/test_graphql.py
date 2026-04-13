import json
from importlib import import_module

from django.test import SimpleTestCase
from django.urls import reverse

from core.models import ObjectType
from netbox.graphql.schema import Query
from netbox.registry import registry
from users.models import ObjectPermission
from utilities.testing import APITestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.graphql.schema import NetBoxRpkiQuery
from netbox_rpki.models import (
    Certificate,
    CertificateAsn,
    CertificatePrefix,
    Organization,
    Roa,
    RoaPrefix,
)
from netbox_rpki.object_registry import GRAPHQL_OBJECT_SPECS
from netbox_rpki.tests.registry_scenarios import (
    EXPECTED_GRAPHQL_FIELD_NAMES_BY_KEY,
    EXPECTED_GRAPHQL_FIELD_ORDER,
    _build_instance_for_spec,
)
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa,
    create_test_certificate,
    create_test_certificate_asn,
    create_test_certificate_prefix,
    create_test_certificate_revocation_list,
    create_test_end_entity_certificate,
    create_test_organization,
    create_test_object_validation_result,
    create_test_prefix,
    create_test_publication_point,
    create_test_rir,
    create_test_roa,
    create_test_roa_prefix,
    create_test_imported_aspa,
    create_test_imported_aspa_provider,
    create_test_imported_ca_metadata,
    create_test_imported_certificate_observation,
    create_test_imported_child_link,
    create_test_imported_parent_link,
    create_test_imported_publication_point,
    create_test_imported_resource_entitlement,
    create_test_imported_roa_authorization,
    create_test_imported_signed_object,
    create_test_manifest,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_provider_snapshot_diff,
    create_test_provider_snapshot_diff_item,
    create_test_router_certificate,
    create_test_signed_object,
    create_test_trust_anchor,
    create_test_validated_aspa_payload,
    create_test_validated_roa_payload,
    create_test_validation_run,
)


plugin_graphql_schema = import_module('netbox_rpki.graphql.schema')


class GraphQLSchemaRegistrationTestCase(SimpleTestCase):
    def test_schema_exports_plugin_query_list(self):
        self.assertEqual(plugin_graphql_schema.schema, [NetBoxRpkiQuery])

    def test_schema_uses_registry_object_set(self):
        self.assertTupleEqual(
            tuple(plugin_graphql_schema.GRAPHQL_TYPE_CLASS_MAP),
            tuple(spec.registry_key for spec in GRAPHQL_OBJECT_SPECS),
        )
        self.assertDictEqual(
            plugin_graphql_schema.GRAPHQL_FIELD_NAME_MAP,
            {
                spec.registry_key: (spec.graphql.detail_field_name, spec.graphql.list_field_name)
                for spec in GRAPHQL_OBJECT_SPECS
            },
        )

    def test_registry_pins_stable_graphql_field_names(self):
        self.assertDictEqual(
            {
                spec.registry_key: (spec.graphql.detail_field_name, spec.graphql.list_field_name)
                for spec in GRAPHQL_OBJECT_SPECS
            },
            EXPECTED_GRAPHQL_FIELD_NAMES_BY_KEY,
        )

    def test_query_exposes_all_plugin_fields(self):
        custom_fields = {
            'provider_account_summary',
            'provider_snapshot_summary',
            'provider_snapshot_latest_diff',
            'provider_snapshot_diff',
        }
        expected_fields = {
            field_name
            for field_names in EXPECTED_GRAPHQL_FIELD_NAMES_BY_KEY.values()
            for field_name in field_names
        } | custom_fields

        actual_fields = {field.name for field in NetBoxRpkiQuery.__strawberry_definition__.fields}

        self.assertSetEqual(actual_fields, expected_fields)

    def test_query_field_order_matches_registry_order(self):
        actual_field_order = [field.name for field in NetBoxRpkiQuery.__strawberry_definition__.fields]

        self.assertListEqual(
            actual_field_order,
            [
                'provider_account_summary',
                'provider_snapshot_summary',
                'provider_snapshot_latest_diff',
                'provider_snapshot_diff',
                *EXPECTED_GRAPHQL_FIELD_ORDER,
            ],
        )

    def test_type_map_uses_existing_graphql_types(self):
        graphql_types = import_module('netbox_rpki.graphql.types')

        for spec in GRAPHQL_OBJECT_SPECS:
            with self.subTest(object_key=spec.registry_key):
                self.assertIs(
                    plugin_graphql_schema.GRAPHQL_TYPE_CLASS_MAP[spec.registry_key],
                    getattr(graphql_types, f'{spec.model.__name__}Type'),
                )

    def test_plugin_query_is_registered_with_netbox_schema(self):
        self.assertIn(NetBoxRpkiQuery, registry['plugins']['graphql_schemas'])
        self.assertTrue(issubclass(Query, NetBoxRpkiQuery))


class GraphQLSurfaceContractTestCase(APITestCase):
    def graphql_request(self, query):
        response = self.client.post(reverse('graphql'), data={'query': query}, format='json', **self.header)
        self.assertHttpStatus(response, 200)
        return json.loads(response.content)

    def test_every_registered_graphql_object_supports_minimal_detail_and_list_queries(self):
        for spec in GRAPHQL_OBJECT_SPECS:
            instance = _build_instance_for_spec(spec, token=f'{spec.registry_key}-graphql-surface')
            self.add_permissions(f'netbox_rpki.view_{spec.model._meta.model_name}')
            detail_field = spec.graphql.detail_field_name
            list_field = spec.graphql.list_field_name

            data = self.graphql_request(
                f'{{{detail_field}(id: {instance.pk}) {{id}} {list_field} {{id}}}}'
            )

            with self.subTest(object_key=spec.registry_key, instance=instance.pk):
                self.assertNotIn('errors', data)
                self.assertEqual(int(data['data'][detail_field]['id']), instance.pk)
                self.assertIn(
                    instance.pk,
                    [int(item['id']) for item in data['data'][list_field]],
                )


class PluginGraphQLTestMixin:
    model = None
    view_permission = ''
    detail_field = ''
    list_field = ''
    detail_selection = 'id'
    valid_filter_cases = ()
    empty_result_filter = ''

    def graphql_request(self, query):
        response = self.client.post(reverse('graphql'), data={'query': query}, format='json', **self.header)
        self.assertHttpStatus(response, 200)
        return json.loads(response.content)

    def build_detail_query(self, object_id):
        return f'{{{self.detail_field}(id: {object_id}) {{{self.detail_selection}}}}}'

    def build_list_query(self, filter_string=''):
        filter_block = f'(filters: {{{filter_string}}})' if filter_string else ''
        return f'{{{self.list_field}{filter_block} {{id}}}}'

    def assert_graphql_success(self, data):
        self.assertNotIn('errors', data)
        self.assertIn('data', data)

    def assert_missing_object_response(self, data, field_name):
        if 'errors' in data:
            if data.get('data') is None:
                return
            self.assertIsNone(data['data'][field_name])
            return

        self.assertIsNone(data['data'][field_name])

    def grant_view_permission(self, constraints=None):
        object_type = ObjectType.objects.get_for_model(self.model)
        permission = ObjectPermission(name=f'{self.model._meta.label_lower}-view', actions=['view'], constraints=constraints)
        permission.save()
        permission.users.add(self.user)
        permission.object_types.add(object_type)
        return permission

    def test_get_object_by_id(self):
        self.add_permissions(self.view_permission)

        instance = self.model.objects.first()
        data = self.graphql_request(self.build_detail_query(instance.pk))

        self.assert_graphql_success(data)
        self.assertEqual(int(data['data'][self.detail_field]['id']), instance.pk)

    def test_get_object_with_invalid_id_returns_null_or_error(self):
        self.add_permissions(self.view_permission)

        data = self.graphql_request(self.build_detail_query(999999))

        self.assert_missing_object_response(data, self.detail_field)

    def test_list_objects_without_filters(self):
        self.add_permissions(self.view_permission)

        data = self.graphql_request(self.build_list_query())

        self.assert_graphql_success(data)
        self.assertEqual(
            [int(item['id']) for item in data['data'][self.list_field]],
            list(self.model.objects.values_list('pk', flat=True)),
        )

    def test_list_objects_with_valid_filters(self):
        self.add_permissions(self.view_permission)

        for filter_string, expected_objects in self.valid_filter_cases:
            with self.subTest(filter_string=filter_string):
                data = self.graphql_request(self.build_list_query(filter_string))

                self.assert_graphql_success(data)
                self.assertEqual(
                    [int(item['id']) for item in data['data'][self.list_field]],
                    [obj.pk for obj in expected_objects],
                )

    def test_list_objects_with_invalid_filter_returns_error(self):
        self.add_permissions(self.view_permission)

        data = self.graphql_request(self.build_list_query('not_a_real_filter: "invalid"'))

        self.assertIn('errors', data)

    def test_list_objects_with_empty_result_filter(self):
        self.add_permissions(self.view_permission)

        data = self.graphql_request(self.build_list_query(self.empty_result_filter))

        self.assert_graphql_success(data)
        self.assertEqual(data['data'][self.list_field], [])

    def test_list_objects_respect_constrained_object_permissions(self):
        self.grant_view_permission(constraints={'id': 0})

        data = self.graphql_request(self.build_list_query())

        self.assert_graphql_success(data)
        self.assertEqual(data['data'][self.list_field], [])

    def test_get_object_respects_constrained_object_permissions(self):
        self.grant_view_permission(constraints={'id': 0})

        instance = self.model.objects.first()
        data = self.graphql_request(self.build_detail_query(instance.pk))

        self.assertIn('errors', data)
        self.assertTrue(data.get('data') is None or data['data'][self.detail_field] is None)


class OrganizationGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = Organization
    view_permission = 'netbox_rpki.view_organization'
    detail_field = 'netbox_rpki_organization'
    list_field = 'netbox_rpki_organization_list'
    detail_selection = 'id org_id name'

    @classmethod
    def setUpTestData(cls):
        cls.rir_a = create_test_rir(name='GraphQL Org RIR A', slug='graphql-org-rir-a')
        cls.rir_b = create_test_rir(name='GraphQL Org RIR B', slug='graphql-org-rir-b')
        cls.organization_alpha = create_test_organization(
            org_id='alpha-org',
            name='Alpha Org',
            ext_url='https://alpha.invalid',
            parent_rir=cls.rir_a,
        )
        cls.organization_beta = create_test_organization(
            org_id='beta-org',
            name='Beta Org',
            ext_url='https://beta.invalid',
        )
        cls.organization_gamma = create_test_organization(
            org_id='gamma-org',
            name='Gamma Org',
            ext_url='https://gamma.invalid',
            parent_rir=cls.rir_b,
        )
        cls.valid_filter_cases = (
            ('org_id: {i_contains: "alpha"}', (cls.organization_alpha,)),
            ('name: {i_contains: "Beta"}', (cls.organization_beta,)),
            (f'parent_rir_id: "{cls.rir_b.pk}"', (cls.organization_gamma,)),
        )
        cls.empty_result_filter = 'name: {i_contains: "missing-org"}'


class CertificateGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = Certificate
    view_permission = 'netbox_rpki.view_certificate'
    detail_field = 'netbox_rpki_certificate'
    list_field = 'netbox_rpki_certificate_list'
    detail_selection = 'id name issuer auto_renews self_hosted'

    @classmethod
    def setUpTestData(cls):
        cls.organization_a = create_test_organization(org_id='cert-alpha-org', name='Cert Alpha Org')
        cls.organization_b = create_test_organization(org_id='cert-beta-org', name='Cert Beta Org')
        cls.trust_anchor = create_test_trust_anchor(
            name='Certificate GraphQL Trust Anchor',
            organization=cls.organization_a,
        )
        cls.publication_point = create_test_publication_point(
            name='Certificate GraphQL Publication Point',
            organization=cls.organization_a,
            publication_uri='rsync://graphql.invalid/certificates/',
        )
        cls.certificate_alpha = create_test_certificate(
            name='Alpha Certificate',
            issuer='Alpha Issuer',
            rpki_org=cls.organization_a,
            auto_renews=True,
            self_hosted=False,
            trust_anchor=cls.trust_anchor,
            publication_point=cls.publication_point,
        )
        cls.certificate_beta = create_test_certificate(
            name='Beta Certificate',
            issuer='Beta Issuer',
            rpki_org=cls.organization_b,
            auto_renews=False,
            self_hosted=True,
        )
        cls.certificate_gamma = create_test_certificate(
            name='Gamma Certificate',
            issuer='Gamma Issuer',
            rpki_org=cls.organization_a,
            auto_renews=True,
            self_hosted=False,
        )
        cls.valid_filter_cases = (
            ('name: {i_contains: "Alpha"}', (cls.certificate_alpha,)),
            ('auto_renews: {exact: true}', (cls.certificate_alpha, cls.certificate_gamma)),
            (f'rpki_org_id: "{cls.organization_b.pk}"', (cls.certificate_beta,)),
            (f'trust_anchor_id: "{cls.trust_anchor.pk}"', (cls.certificate_alpha,)),
            (f'publication_point_id: "{cls.publication_point.pk}"', (cls.certificate_alpha,)),
        )
        cls.empty_result_filter = 'rpki_org_id: "999999"'


class RoaGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = Roa
    view_permission = 'netbox_rpki.view_roa'
    detail_field = 'netbox_rpki_roa'
    list_field = 'netbox_rpki_roa_list'
    detail_selection = 'id name auto_renews'

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='roa-org', name='ROA GraphQL Org')
        cls.signing_certificate_a = create_test_certificate(name='ROA Signing Cert A', rpki_org=cls.organization)
        cls.signing_certificate_b = create_test_certificate(name='ROA Signing Cert B', rpki_org=cls.organization)
        cls.asn_a = create_test_asn(65101)
        cls.asn_b = create_test_asn(65102)
        cls.signed_object_alpha = create_test_signed_object(
            name='Alpha ROA Signed Object',
            organization=cls.organization,
            object_type=rpki_models.SignedObjectType.ROA,
            resource_certificate=cls.signing_certificate_a,
        )
        cls.roa_alpha = create_test_roa(
            name='Alpha ROA',
            signed_by=cls.signing_certificate_a,
            signed_object=cls.signed_object_alpha,
            origin_as=cls.asn_a,
            auto_renews=True,
        )
        cls.roa_beta = create_test_roa(
            name='Beta ROA',
            signed_by=cls.signing_certificate_b,
            origin_as=cls.asn_b,
            auto_renews=False,
        )
        cls.roa_gamma = create_test_roa(
            name='Gamma ROA',
            signed_by=cls.signing_certificate_a,
            origin_as=cls.asn_a,
            auto_renews=True,
        )
        cls.valid_filter_cases = (
            ('name: {i_contains: "Alpha"}', (cls.roa_alpha,)),
            ('auto_renews: {exact: true}', (cls.roa_alpha, cls.roa_gamma)),
            (f'origin_as_id: "{cls.asn_b.pk}"', (cls.roa_beta,)),
            (f'signed_by_id: "{cls.signing_certificate_a.pk}"', (cls.roa_alpha, cls.roa_gamma)),
            (f'signed_object_id: "{cls.signed_object_alpha.pk}"', (cls.roa_alpha,)),
        )
        cls.empty_result_filter = 'signed_by_id: "999999"'


class RoaPrefixGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = RoaPrefix
    view_permission = 'netbox_rpki.view_roaprefix'
    detail_field = 'netbox_rpki_roa_prefix'
    list_field = 'netbox_rpki_roa_prefix_list'
    detail_selection = 'id max_length'

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='roapfx-org', name='ROA Prefix Org')
        cls.signing_certificate = create_test_certificate(name='ROA Prefix Signing Cert', rpki_org=cls.organization)
        cls.roa_a = create_test_roa(name='ROA Prefix A', signed_by=cls.signing_certificate)
        cls.roa_b = create_test_roa(name='ROA Prefix B', signed_by=cls.signing_certificate)
        cls.prefix_a = create_test_prefix('10.10.10.0/24')
        cls.prefix_b = create_test_prefix('10.10.20.0/24')
        cls.prefix_c = create_test_prefix('10.10.30.0/24')
        cls.roa_prefix_a = create_test_roa_prefix(prefix=cls.prefix_a, roa=cls.roa_a, max_length=24)
        cls.roa_prefix_b = create_test_roa_prefix(prefix=cls.prefix_b, roa=cls.roa_b, max_length=25)
        cls.roa_prefix_c = create_test_roa_prefix(prefix=cls.prefix_c, roa=cls.roa_b, max_length=26)
        cls.valid_filter_cases = (
            (f'prefix_id: "{cls.prefix_a.pk}"', (cls.roa_prefix_a,)),
            (f'roa_name_id: "{cls.roa_b.pk}"', (cls.roa_prefix_b, cls.roa_prefix_c)),
        )
        cls.empty_result_filter = 'roa_name_id: "999999"'


class ProviderReportingGraphQLTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-graphql-org', name='Provider GraphQL Org')
        cls.provider_account = create_test_provider_account(
            name='GraphQL Provider Account',
            organization=cls.organization,
            provider_type='krill',
            ca_handle='graphql-ca',
            org_handle='ORG-GRAPHQL',
        )
        cls.other_provider_account = create_test_provider_account(
            name='GraphQL Provider Account 2',
            organization=cls.organization,
            provider_type='arin',
            ca_handle='graphql-ca-2',
            org_handle='ORG-GRAPHQL-2',
        )
        cls.base_snapshot = create_test_provider_snapshot(
            name='GraphQL Base Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
        )
        cls.comparison_snapshot = create_test_provider_snapshot(
            name='GraphQL Comparison Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
        )
        cls.extra_snapshot = create_test_provider_snapshot(
            name='GraphQL Extra Snapshot',
            organization=cls.organization,
            provider_account=cls.other_provider_account,
        )
        cls.snapshot_diff = create_test_provider_snapshot_diff(
            name='GraphQL Snapshot Diff',
            organization=cls.organization,
            provider_account=cls.provider_account,
            base_snapshot=cls.base_snapshot,
            comparison_snapshot=cls.comparison_snapshot,
        )
        create_test_provider_snapshot_diff_item(
            name='GraphQL Snapshot Diff Item',
            snapshot_diff=cls.snapshot_diff,
            object_family='roa_authorizations',
            change_type='changed',
            provider_identity='graphql-provider-identity',
        )
        cls.imported_prefix = create_test_prefix('10.199.0.0/24')
        cls.imported_asn = create_test_asn(65550)
        cls.imported_customer_asn = create_test_asn(65551)
        cls.imported_roa = create_test_imported_roa_authorization(
            name='GraphQL Imported ROA',
            provider_snapshot=cls.comparison_snapshot,
            organization=cls.organization,
            prefix=cls.imported_prefix,
            origin_asn=cls.imported_asn,
            max_length=24,
        )
        cls.imported_aspa = create_test_imported_aspa(
            name='GraphQL Imported ASPA',
            provider_snapshot=cls.comparison_snapshot,
            organization=cls.organization,
            customer_as=cls.imported_customer_asn,
        )
        create_test_imported_aspa_provider(imported_aspa=cls.imported_aspa, provider_as=cls.imported_asn)
        cls.imported_ca_metadata = create_test_imported_ca_metadata(
            name='GraphQL Imported CA Metadata',
            provider_snapshot=cls.comparison_snapshot,
            organization=cls.organization,
            ca_handle='graphql-ca-handle',
        )
        cls.imported_parent_link = create_test_imported_parent_link(
            name='GraphQL Imported Parent Link',
            provider_snapshot=cls.comparison_snapshot,
            organization=cls.organization,
            parent_handle='parent-graphql',
        )
        cls.imported_child_link = create_test_imported_child_link(
            name='GraphQL Imported Child Link',
            provider_snapshot=cls.comparison_snapshot,
            organization=cls.organization,
            child_handle='child-graphql',
        )
        cls.imported_resource_entitlement = create_test_imported_resource_entitlement(
            name='GraphQL Imported Resource Entitlement',
            provider_snapshot=cls.comparison_snapshot,
            organization=cls.organization,
            entitlement_source='graphql-entitlement',
        )
        cls.imported_publication_point = create_test_imported_publication_point(
            name='GraphQL Imported Publication Point',
            provider_snapshot=cls.comparison_snapshot,
            organization=cls.organization,
            publication_uri='rsync://graphql.invalid/repo/',
        )
        cls.imported_signed_object = create_test_imported_signed_object(
            name='GraphQL Imported Signed Object',
            provider_snapshot=cls.comparison_snapshot,
            organization=cls.organization,
            publication_point=cls.imported_publication_point,
            signed_object_uri='rsync://graphql.invalid/repo/example.mft',
        )
        cls.imported_certificate_observation = create_test_imported_certificate_observation(
            name='GraphQL Imported Certificate Observation',
            provider_snapshot=cls.comparison_snapshot,
            organization=cls.organization,
            publication_point=cls.imported_publication_point,
            signed_object=cls.imported_signed_object,
            certificate_uri='rsync://graphql.invalid/repo/example.cer',
            publication_uri=cls.imported_publication_point.publication_uri,
            signed_object_uri=cls.imported_signed_object.signed_object_uri,
        )

    def graphql_request(self, query):
        response = self.client.post(reverse('graphql'), data={'query': query}, format='json', **self.header)
        self.assertHttpStatus(response, 200)
        return json.loads(response.content)

    def test_provider_reporting_queries_expose_summary_and_diff_lookup(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
            'netbox_rpki.view_importedroaauthorization',
            'netbox_rpki.view_importedaspa',
            'netbox_rpki.view_importedcametadata',
            'netbox_rpki.view_importedparentlink',
            'netbox_rpki.view_importedchildlink',
            'netbox_rpki.view_importedresourceentitlement',
            'netbox_rpki.view_importedpublicationpoint',
            'netbox_rpki.view_importedsignedobject',
            'netbox_rpki.view_importedcertificateobservation',
        )

        query = f'''
        {{
            provider_account_summary
            provider_snapshot_summary
            provider_snapshot_latest_diff(snapshot_id: "{self.comparison_snapshot.pk}") {{
                id
                name
                item_count
            }}
            provider_snapshot_diff(base_snapshot_id: "{self.base_snapshot.pk}", comparison_snapshot_id: "{self.comparison_snapshot.pk}") {{
                id
                name
                item_count
            }}
            netbox_rpki_providersnapshot(id: {self.comparison_snapshot.pk}) {{
                id
                name
                summary
                latest_diff {{
                    id
                    name
                }}
                imported_roa_authorizations {{
                    id
                    name
                }}
                imported_aspas {{
                    id
                    name
                }}
                imported_ca_metadata_records {{
                    id
                    name
                }}
                imported_parent_links {{
                    id
                    name
                }}
                imported_child_links {{
                    id
                    name
                }}
                imported_resource_entitlements {{
                    id
                    name
                }}
                imported_publication_points {{
                    id
                    name
                }}
                imported_signed_objects {{
                    id
                    name
                }}
                imported_certificate_observations {{
                    id
                    name
                }}
            }}
        }}
        '''

        data = self.graphql_request(query)

        self.assertNotIn('errors', data)
        self.assertEqual(data['data']['provider_account_summary']['total_accounts'], 2)
        self.assertEqual(data['data']['provider_account_summary']['by_provider_type']['krill'], 1)
        self.assertEqual(data['data']['provider_account_summary']['by_provider_type']['arin'], 1)
        self.assertEqual(data['data']['provider_snapshot_summary']['total_snapshots'], 3)
        self.assertEqual(data['data']['provider_snapshot_summary']['with_diff_count'], 1)
        self.assertEqual(data['data']['provider_snapshot_latest_diff']['id'], str(self.snapshot_diff.pk))
        self.assertEqual(data['data']['provider_snapshot_latest_diff']['item_count'], 1)
        self.assertEqual(data['data']['provider_snapshot_diff']['id'], str(self.snapshot_diff.pk))
        self.assertEqual(data['data']['netbox_rpki_providersnapshot']['latest_diff']['id'], str(self.snapshot_diff.pk))
        self.assertEqual(
            [row['id'] for row in data['data']['netbox_rpki_providersnapshot']['imported_roa_authorizations']],
            [str(self.imported_roa.pk)],
        )
        self.assertEqual(
            [row['id'] for row in data['data']['netbox_rpki_providersnapshot']['imported_aspas']],
            [str(self.imported_aspa.pk)],
        )
        self.assertEqual(
            [row['id'] for row in data['data']['netbox_rpki_providersnapshot']['imported_ca_metadata_records']],
            [str(self.imported_ca_metadata.pk)],
        )
        self.assertEqual(
            [row['id'] for row in data['data']['netbox_rpki_providersnapshot']['imported_parent_links']],
            [str(self.imported_parent_link.pk)],
        )
        self.assertEqual(
            [row['id'] for row in data['data']['netbox_rpki_providersnapshot']['imported_child_links']],
            [str(self.imported_child_link.pk)],
        )
        self.assertEqual(
            [row['id'] for row in data['data']['netbox_rpki_providersnapshot']['imported_resource_entitlements']],
            [str(self.imported_resource_entitlement.pk)],
        )
        self.assertEqual(
            [row['id'] for row in data['data']['netbox_rpki_providersnapshot']['imported_publication_points']],
            [str(self.imported_publication_point.pk)],
        )
        self.assertEqual(
            [row['id'] for row in data['data']['netbox_rpki_providersnapshot']['imported_signed_objects']],
            [str(self.imported_signed_object.pk)],
        )
        self.assertEqual(
            [row['id'] for row in data['data']['netbox_rpki_providersnapshot']['imported_certificate_observations']],
            [str(self.imported_certificate_observation.pk)],
        )
        self.assertEqual(data['data']['netbox_rpki_providersnapshot']['summary'], self.comparison_snapshot.summary_json)


class CertificateRevocationListGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = rpki_models.CertificateRevocationList
    view_permission = 'netbox_rpki.view_certificaterevocationlist'
    detail_field = 'netbox_rpki_certificaterevocationlist'
    list_field = 'netbox_rpki_certificaterevocationlist_list'
    detail_selection = 'id'

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='crl-graphql-org', name='CRL GraphQL Org')
        cls.signed_object = create_test_signed_object(
            name='CRL GraphQL Signed Object',
            organization=cls.organization,
            filename='graphql.crl',
            object_uri='https://graphql.invalid/crl.crl',
            repository_uri='https://graphql.invalid/',
        )
        cls.certificate_revocation_list = create_test_certificate_revocation_list(
            name='CRL GraphQL Record',
            organization=cls.organization,
            signed_object=cls.signed_object,
            publication_uri='https://graphql.invalid/crl.crl',
            crl_number='11',
        )
        cls.valid_filter_cases = (
            (f'signed_object_id: "{cls.signed_object.pk}"', (cls.certificate_revocation_list,)),
        )
        cls.empty_result_filter = 'signed_object_id: "999999"'

    def test_get_object_by_id(self):
        self.add_permissions(self.view_permission)

        data = self.graphql_request(self.build_detail_query(self.certificate_revocation_list.pk))

        self.assert_graphql_success(data)
        self.assertEqual(int(data['data'][self.detail_field]['id']), self.certificate_revocation_list.pk)

    def test_get_object_with_invalid_id_returns_null_or_error(self):
        self.add_permissions(self.view_permission)

        data = self.graphql_request(self.build_detail_query(999999))

        self.assert_missing_object_response(data, self.detail_field)


class EndEntityCertificateGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = rpki_models.EndEntityCertificate
    view_permission = 'netbox_rpki.view_endentitycertificate'
    _spec = next(spec for spec in GRAPHQL_OBJECT_SPECS if spec.registry_key == 'endentitycertificate')
    detail_field = _spec.graphql.detail_field_name
    list_field = _spec.graphql.list_field_name
    detail_selection = 'id'

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='ee-certificate-graphql-org',
            name='EE Certificate GraphQL Org',
        )
        cls.resource_certificate = create_test_certificate(
            name='EE Certificate GraphQL Resource Certificate',
            rpki_org=cls.organization,
        )
        cls.publication_point = create_test_publication_point(
            name='EE Certificate GraphQL Publication Point',
            organization=cls.organization,
            publication_uri='rsync://graphql.invalid/ee/',
        )
        cls.ee_certificate = create_test_end_entity_certificate(
            name='EE Certificate GraphQL Record',
            organization=cls.organization,
            resource_certificate=cls.resource_certificate,
            publication_point=cls.publication_point,
            serial='ee-graphql-serial',
        )
        cls.valid_filter_cases = (
            (f'resource_certificate_id: "{cls.resource_certificate.pk}"', (cls.ee_certificate,)),
            (f'publication_point_id: "{cls.publication_point.pk}"', (cls.ee_certificate,)),
        )
        cls.empty_result_filter = 'resource_certificate_id: "999999"'


class SignedObjectGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = rpki_models.SignedObject
    view_permission = 'netbox_rpki.view_signedobject'
    _spec = next(spec for spec in GRAPHQL_OBJECT_SPECS if spec.registry_key == 'signedobject')
    detail_field = _spec.graphql.detail_field_name
    list_field = _spec.graphql.list_field_name
    detail_selection = (
        'id '
        'manifest_extension { id } '
        'imported_signed_object_observations { id } '
        'validation_results { id }'
    )

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='signed-object-graphql-org',
            name='Signed Object GraphQL Org',
        )
        cls.signed_object = create_test_signed_object(
            name='Signed Object GraphQL Record',
            organization=cls.organization,
            object_type=rpki_models.SignedObjectType.MANIFEST,
            object_uri='rsync://graphql.invalid/repo/object.mft',
            repository_uri='rsync://graphql.invalid/repo/',
        )
        cls.manifest = create_test_manifest(
            name='Signed Object GraphQL Manifest',
            signed_object=cls.signed_object,
            manifest_number='graphql-manifest-1',
        )
        cls.signed_object.current_manifest = cls.manifest
        cls.signed_object.save(update_fields=('current_manifest',))
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Signed Object GraphQL Snapshot',
            organization=cls.organization,
            provider_account=create_test_provider_account(
                name='Signed Object GraphQL Provider Account',
                organization=cls.organization,
                provider_type='krill',
                org_handle='ORG-SIGNED-OBJECT-GQL',
                ca_handle='signed-object-gql',
            ),
        )
        cls.imported_publication_point = create_test_imported_publication_point(
            name='Signed Object GraphQL Imported Publication Point',
            organization=cls.organization,
            provider_snapshot=cls.provider_snapshot,
            authored_publication_point=cls.signed_object.publication_point,
            publication_uri='rsync://graphql.invalid/repo/',
        )
        cls.imported_signed_object = create_test_imported_signed_object(
            name='Signed Object GraphQL Imported Observation',
            organization=cls.organization,
            provider_snapshot=cls.provider_snapshot,
            publication_point=cls.imported_publication_point,
            authored_signed_object=cls.signed_object,
            signed_object_type=rpki_models.SignedObjectType.MANIFEST,
            signed_object_uri=cls.signed_object.object_uri,
        )
        cls.validation_run = create_test_validation_run(
            name='Signed Object GraphQL Validation Run',
        )
        cls.object_validation_result = create_test_object_validation_result(
            name='Signed Object GraphQL Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.signed_object,
        )
        cls.valid_filter_cases = (
            (f'object_type: {{exact: "{rpki_models.SignedObjectType.MANIFEST}"}}', (cls.signed_object,)),
            (f'current_manifest_id: "{cls.manifest.pk}"', (cls.signed_object,)),
        )
        cls.empty_result_filter = 'current_manifest_id: "999999"'

    def test_get_object_by_id(self):
        self.add_permissions(
            self.view_permission,
            'netbox_rpki.view_manifest',
            'netbox_rpki.view_importedsignedobject',
            'netbox_rpki.view_objectvalidationresult',
        )

        data = self.graphql_request(self.build_detail_query(self.signed_object.pk))

        self.assert_graphql_success(data)
        payload = data['data'][self.detail_field]
        self.assertEqual(int(payload['id']), self.signed_object.pk)
        self.assertEqual(int(payload['manifest_extension']['id']), self.manifest.pk)
        self.assertEqual(
            [int(item['id']) for item in payload['imported_signed_object_observations']],
            [self.imported_signed_object.pk],
        )
        self.assertEqual(
            [int(item['id']) for item in payload['validation_results']],
            [self.object_validation_result.pk],
        )


class RouterCertificateGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = rpki_models.RouterCertificate
    view_permission = 'netbox_rpki.view_routercertificate'
    _spec = next(spec for spec in GRAPHQL_OBJECT_SPECS if spec.registry_key == 'routercertificate')
    detail_field = _spec.graphql.detail_field_name
    list_field = _spec.graphql.list_field_name
    detail_selection = 'id'

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='router-cert-graphql-org',
            name='Router Certificate GraphQL Org',
        )
        cls.resource_certificate = create_test_certificate(
            name='Router Certificate GraphQL Resource Certificate',
            rpki_org=cls.organization,
        )
        cls.ee_certificate = create_test_end_entity_certificate(
            name='Router Certificate GraphQL EE Certificate',
            organization=cls.organization,
            resource_certificate=cls.resource_certificate,
            subject='CN=GraphQL Router',
            issuer='CN=GraphQL Issuer',
            serial='graphql-router-serial',
            ski='graphql-router-ski',
        )
        cls.router_certificate = create_test_router_certificate(
            name='Router Certificate GraphQL Record',
            organization=cls.organization,
            resource_certificate=cls.resource_certificate,
            publication_point=cls.ee_certificate.publication_point,
            ee_certificate=cls.ee_certificate,
            asn=create_test_asn(65312),
            subject='CN=GraphQL Router',
            issuer='CN=GraphQL Issuer',
            serial='graphql-router-serial',
            ski='graphql-router-ski',
        )
        cls.valid_filter_cases = (
            (f'ee_certificate_id: "{cls.ee_certificate.pk}"', (cls.router_certificate,)),
        )
        cls.empty_result_filter = 'ee_certificate_id: "999999"'

    def test_get_object_by_id(self):
        self.add_permissions(self.view_permission)

        data = self.graphql_request(self.build_detail_query(self.router_certificate.pk))

        self.assert_graphql_success(data)
        self.assertEqual(int(data['data'][self.detail_field]['id']), self.router_certificate.pk)

    def test_get_object_with_invalid_id_returns_null_or_error(self):
        self.add_permissions(self.view_permission)

        data = self.graphql_request(self.build_detail_query(999999))

        self.assert_missing_object_response(data, self.detail_field)


class ImportedCertificateObservationGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = rpki_models.ImportedCertificateObservation
    view_permission = 'netbox_rpki.view_importedcertificateobservation'
    detail_field = 'netbox_rpki_importedcertificateobservation'
    list_field = 'netbox_rpki_importedcertificateobservation_list'
    detail_selection = 'id'

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='imported-cert-graphql-org',
            name='Imported Certificate GraphQL Org',
        )
        cls.provider_account = create_test_provider_account(
            name='Imported Certificate GraphQL Account',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-IMPORTED-CERT-GRAPHQL',
            ca_handle='imported-cert-graphql',
        )
        cls.snapshot = create_test_provider_snapshot(
            name='Imported Certificate GraphQL Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            status='completed',
        )
        cls.imported_publication_point = create_test_imported_publication_point(
            name='Imported Certificate GraphQL Publication Point',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            publication_uri='rsync://graphql.invalid/repo/',
        )
        cls.imported_signed_object = create_test_imported_signed_object(
            name='Imported Certificate GraphQL Signed Object',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            publication_point=cls.imported_publication_point,
            signed_object_uri='rsync://graphql.invalid/repo/example.mft',
        )
        cls.certificate_observation = create_test_imported_certificate_observation(
            name='Imported Certificate GraphQL Record',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            publication_point=cls.imported_publication_point,
            signed_object=cls.imported_signed_object,
            certificate_uri='rsync://graphql.invalid/repo/example.cer',
            publication_uri=cls.imported_publication_point.publication_uri,
            signed_object_uri=cls.imported_signed_object.signed_object_uri,
        )
        cls.valid_filter_cases = (
            (f'publication_point_id: "{cls.imported_publication_point.pk}"', (cls.certificate_observation,)),
            (f'signed_object_id: "{cls.imported_signed_object.pk}"', (cls.certificate_observation,)),
        )
        cls.empty_result_filter = 'signed_object_id: "999999"'

    def test_get_object_by_id(self):
        self.add_permissions(self.view_permission)

        data = self.graphql_request(self.build_detail_query(self.certificate_observation.pk))

        self.assert_graphql_success(data)
        self.assertEqual(int(data['data'][self.detail_field]['id']), self.certificate_observation.pk)

    def test_get_object_with_invalid_id_returns_null_or_error(self):
        self.add_permissions(self.view_permission)

        data = self.graphql_request(self.build_detail_query(999999))

        self.assert_missing_object_response(data, self.detail_field)


class ImportedPublicationLinkGraphQLTestCase(APITestCase):
    def graphql_request(self, query):
        response = self.client.post(reverse('graphql'), data={'query': query}, format='json', **self.header)
        self.assertHttpStatus(response, 200)
        return json.loads(response.content)

    def assert_graphql_success(self, data):
        self.assertNotIn('errors', data)
        self.assertIn('data', data)

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='imported-publication-link-graphql-org',
            name='Imported Publication Link GraphQL Org',
        )
        cls.provider_account = create_test_provider_account(
            name='Imported Publication Link GraphQL Account',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-IMPORTED-LINK-GRAPHQL',
            ca_handle='imported-link-graphql',
        )
        cls.snapshot = create_test_provider_snapshot(
            name='Imported Publication Link GraphQL Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            status='completed',
        )
        cls.authored_publication_point = create_test_publication_point(
            name='Imported Publication Link GraphQL Authored Publication Point',
            organization=cls.organization,
            publication_uri='rsync://graphql.invalid/repo/',
        )
        cls.authored_signed_object = create_test_signed_object(
            name='Imported Publication Link GraphQL Authored Signed Object',
            organization=cls.organization,
            publication_point=cls.authored_publication_point,
            object_type='manifest',
            object_uri='rsync://graphql.invalid/repo/example.mft',
        )
        cls.imported_publication_point = create_test_imported_publication_point(
            name='Imported Publication Link GraphQL Publication Point',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            authored_publication_point=cls.authored_publication_point,
            publication_uri=cls.authored_publication_point.publication_uri,
        )
        cls.imported_signed_object = create_test_imported_signed_object(
            name='Imported Publication Link GraphQL Signed Object',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            publication_point=cls.imported_publication_point,
            authored_signed_object=cls.authored_signed_object,
            signed_object_type='manifest',
            signed_object_uri=cls.authored_signed_object.object_uri,
            publication_uri=cls.imported_publication_point.publication_uri,
        )

    def test_imported_publication_point_list_filters_by_authored_publication_point(self):
        self.add_permissions('netbox_rpki.view_importedpublicationpoint')

        data = self.graphql_request(
            f'{{netbox_rpki_importedpublicationpoint_list(filters: {{authored_publication_point_id: "{self.authored_publication_point.pk}"}}) {{id}}}}'
        )

        self.assert_graphql_success(data)
        self.assertEqual(
            [int(item['id']) for item in data['data']['netbox_rpki_importedpublicationpoint_list']],
            [self.imported_publication_point.pk],
        )

    def test_imported_signed_object_list_filters_by_authored_signed_object(self):
        self.add_permissions('netbox_rpki.view_importedsignedobject')

        data = self.graphql_request(
            f'{{netbox_rpki_importedsignedobject_list(filters: {{authored_signed_object_id: "{self.authored_signed_object.pk}"}}) {{id}}}}'
        )

        self.assert_graphql_success(data)
        self.assertEqual(
            [int(item['id']) for item in data['data']['netbox_rpki_importedsignedobject_list']],
            [self.imported_signed_object.pk],
        )


class ValidatedPayloadValidationLinkGraphQLTestCase(APITestCase):
    def graphql_request(self, query):
        response = self.client.post(reverse('graphql'), data={'query': query}, format='json', **self.header)
        self.assertHttpStatus(response, 200)
        return json.loads(response.content)

    def assert_graphql_success(self, data):
        self.assertNotIn('errors', data)
        self.assertIn('data', data)

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='validated-payload-graphql-org',
            name='Validated Payload GraphQL Org',
        )
        cls.validation_run = create_test_validation_run(
            name='Validated Payload GraphQL Validation Run',
        )
        cls.roa_signing_certificate = create_test_certificate(
            name='Validated Payload GraphQL ROA Certificate',
            rpki_org=cls.organization,
        )
        cls.roa_signed_object = create_test_signed_object(
            name='Validated Payload GraphQL ROA Signed Object',
            organization=cls.organization,
            object_type=rpki_models.SignedObjectType.ROA,
            resource_certificate=cls.roa_signing_certificate,
        )
        cls.roa = create_test_roa(
            name='Validated Payload GraphQL ROA',
            signed_by=cls.roa_signing_certificate,
            signed_object=cls.roa_signed_object,
        )
        cls.roa_object_validation_result = create_test_object_validation_result(
            name='Validated Payload GraphQL ROA Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.roa_signed_object,
        )
        cls.validated_roa_payload = create_test_validated_roa_payload(
            name='Validated Payload GraphQL ROA Payload',
            validation_run=cls.validation_run,
            roa=cls.roa,
            object_validation_result=cls.roa_object_validation_result,
        )
        cls.aspa = create_test_aspa(
            name='Validated Payload GraphQL ASPA',
            organization=cls.organization,
            customer_as=create_test_asn(65420),
        )
        cls.aspa_object_validation_result = create_test_object_validation_result(
            name='Validated Payload GraphQL ASPA Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.aspa.signed_object,
        )
        cls.validated_aspa_payload = create_test_validated_aspa_payload(
            name='Validated Payload GraphQL ASPA Payload',
            validation_run=cls.validation_run,
            aspa=cls.aspa,
            object_validation_result=cls.aspa_object_validation_result,
            customer_as=cls.aspa.customer_as,
            provider_as=create_test_asn(65421),
        )

    def test_validated_roa_payload_list_filters_by_object_validation_result(self):
        self.add_permissions('netbox_rpki.view_validatedroapayload')

        data = self.graphql_request(
            f'{{netbox_rpki_validatedroapayload_list(filters: {{object_validation_result_id: "{self.roa_object_validation_result.pk}"}}) {{id}}}}'
        )

        self.assert_graphql_success(data)
        self.assertEqual(
            [int(item['id']) for item in data['data']['netbox_rpki_validatedroapayload_list']],
            [self.validated_roa_payload.pk],
        )

    def test_validated_aspa_payload_list_filters_by_object_validation_result(self):
        self.add_permissions('netbox_rpki.view_validatedaspapayload')

        data = self.graphql_request(
            f'{{netbox_rpki_validatedaspapayload_list(filters: {{object_validation_result_id: "{self.aspa_object_validation_result.pk}"}}) {{id}}}}'
        )

        self.assert_graphql_success(data)
        self.assertEqual(
            [int(item['id']) for item in data['data']['netbox_rpki_validatedaspapayload_list']],
            [self.validated_aspa_payload.pk],
        )


class CertificatePrefixGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = CertificatePrefix
    view_permission = 'netbox_rpki.view_certificateprefix'
    detail_field = 'netbox_rpki_certificate_prefix'
    list_field = 'netbox_rpki_certificate_prefix_list'
    detail_selection = 'id'

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='certpfx-org', name='Certificate Prefix Org')
        cls.certificate_a = create_test_certificate(name='Certificate Prefix A', rpki_org=cls.organization)
        cls.certificate_b = create_test_certificate(name='Certificate Prefix B', rpki_org=cls.organization)
        cls.prefix_a = create_test_prefix('10.20.10.0/24')
        cls.prefix_b = create_test_prefix('10.20.20.0/24')
        cls.prefix_c = create_test_prefix('10.20.30.0/24')
        cls.certificate_prefix_a = create_test_certificate_prefix(prefix=cls.prefix_a, certificate=cls.certificate_a)
        cls.certificate_prefix_b = create_test_certificate_prefix(prefix=cls.prefix_b, certificate=cls.certificate_b)
        cls.certificate_prefix_c = create_test_certificate_prefix(prefix=cls.prefix_c, certificate=cls.certificate_b)
        cls.valid_filter_cases = (
            (f'prefix_id: "{cls.prefix_a.pk}"', (cls.certificate_prefix_a,)),
            (f'certificate_name_id: "{cls.certificate_b.pk}"', (cls.certificate_prefix_b, cls.certificate_prefix_c)),
        )
        cls.empty_result_filter = 'certificate_name_id: "999999"'


class CertificateAsnGraphQLTestCase(PluginGraphQLTestMixin, APITestCase):
    model = CertificateAsn
    view_permission = 'netbox_rpki.view_certificateasn'
    detail_field = 'netbox_rpki_certificate_asn'
    list_field = 'netbox_rpki_certificate_asn_list'
    detail_selection = 'id'

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='certasn-org', name='Certificate ASN Org')
        cls.certificate_a = create_test_certificate(name='Certificate ASN A', rpki_org=cls.organization)
        cls.certificate_b = create_test_certificate(name='Certificate ASN B', rpki_org=cls.organization)
        cls.asn_a = create_test_asn(65201)
        cls.asn_b = create_test_asn(65202)
        cls.asn_c = create_test_asn(65203)
        cls.certificate_asn_a = create_test_certificate_asn(asn=cls.asn_a, certificate=cls.certificate_a)
        cls.certificate_asn_b = create_test_certificate_asn(asn=cls.asn_b, certificate=cls.certificate_b)
        cls.certificate_asn_c = create_test_certificate_asn(asn=cls.asn_c, certificate=cls.certificate_b)
        cls.valid_filter_cases = (
            (f'asn_id: "{cls.asn_a.pk}"', (cls.certificate_asn_a,)),
            (f'certificate_name2_id: "{cls.certificate_b.pk}"', (cls.certificate_asn_b, cls.certificate_asn_c)),
        )
        cls.empty_result_filter = 'certificate_name2_id: "999999"'
