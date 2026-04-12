import json
from importlib import import_module

from django.test import SimpleTestCase
from django.urls import reverse

from core.models import ObjectType
from netbox.graphql.schema import Query
from netbox.registry import registry
from users.models import ObjectPermission
from utilities.testing import APITestCase

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
    create_test_certificate,
    create_test_certificate_asn,
    create_test_certificate_prefix,
    create_test_organization,
    create_test_prefix,
    create_test_rir,
    create_test_roa,
    create_test_roa_prefix,
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
        expected_fields = {
            field_name
            for field_names in EXPECTED_GRAPHQL_FIELD_NAMES_BY_KEY.values()
            for field_name in field_names
        }

        actual_fields = {field.name for field in NetBoxRpkiQuery.__strawberry_definition__.fields}

        self.assertSetEqual(actual_fields, expected_fields)

    def test_query_field_order_matches_registry_order(self):
        actual_field_order = [field.name for field in NetBoxRpkiQuery.__strawberry_definition__.fields]

        self.assertListEqual(actual_field_order, list(EXPECTED_GRAPHQL_FIELD_ORDER))

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
        cls.certificate_alpha = create_test_certificate(
            name='Alpha Certificate',
            issuer='Alpha Issuer',
            rpki_org=cls.organization_a,
            auto_renews=True,
            self_hosted=False,
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
        cls.roa_alpha = create_test_roa(
            name='Alpha ROA',
            signed_by=cls.signing_certificate_a,
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