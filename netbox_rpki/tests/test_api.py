from django.test import SimpleTestCase

from netbox_rpki import filtersets
from netbox_rpki.api import serializers as api_serializers
from netbox_rpki.api import views as api_views
from netbox_rpki.api.urls import router
from netbox_rpki.api.serializers import (
    CertificateAsnSerializer,
    CertificatePrefixSerializer,
    CertificateSerializer,
    OrganizationSerializer,
    RoaPrefixSerializer,
    RoaSerializer,
)
from netbox_rpki.api.views import RootView
from netbox_rpki.graphql import filters as graphql_filters
from netbox_rpki.graphql import types as graphql_types
from netbox_rpki.models import (
    Certificate,
    CertificateAsn,
    CertificatePrefix,
    Organization,
    Roa,
    RoaPrefix,
)
from netbox_rpki.object_registry import API_OBJECT_SPECS, GRAPHQL_OBJECT_SPECS
from netbox_rpki.tests.base import PluginAPITestCase
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


class ObjectRegistrySmokeTestCase(SimpleTestCase):
    def test_api_object_specs_match_expected_contract(self):
        for spec in API_OBJECT_SPECS:
            with self.subTest(object_key=spec.key):
                self.assertEqual(spec.api.basename, spec.key)
                self.assertTrue(spec.api.serializer_name.endswith('Serializer'))
                self.assertTrue(spec.api.viewset_name.endswith('ViewSet'))

    def test_registry_uses_structured_surface_specs(self):
        for spec in API_OBJECT_SPECS:
            with self.subTest(object_key=spec.key):
                self.assertEqual(getattr(api_serializers, spec.api.serializer_name).__name__, spec.api.serializer_name)
                self.assertEqual(spec.routes.list_url_name, f'plugins:netbox_rpki:{spec.routes.slug}_list')
                self.assertEqual(spec.routes.add_url_name, f'plugins:netbox_rpki:{spec.routes.slug}_add')

    def test_graphql_object_specs_match_expected_contract(self):
        self.assertEqual(
            [spec.graphql.filter.class_name for spec in GRAPHQL_OBJECT_SPECS],
            [getattr(graphql_filters, spec.graphql.filter.class_name).__name__ for spec in GRAPHQL_OBJECT_SPECS],
        )
        self.assertEqual(
            [spec.graphql.type.class_name for spec in GRAPHQL_OBJECT_SPECS],
            [getattr(graphql_types, spec.graphql.type.class_name).__name__ for spec in GRAPHQL_OBJECT_SPECS],
        )


class GraphQLSmokeTestCase(SimpleTestCase):
    def test_generated_graphql_filters_remain_stable_and_inspectable(self):
        for spec in GRAPHQL_OBJECT_SPECS:
            filter_class = getattr(graphql_filters, spec.graphql.filter.class_name)
            with self.subTest(object_key=spec.key):
                self.assertIs(graphql_filters.GRAPHQL_FILTER_CLASS_MAP[spec.key], filter_class)
                self.assertIs(filter_class.__object_spec__, spec)
                for field in spec.graphql.filter.fields:
                    self.assertIn(field.field_name, filter_class.__annotations__)

    def test_generated_graphql_types_remain_stable_and_inspectable(self):
        for spec in GRAPHQL_OBJECT_SPECS:
            type_class = getattr(graphql_types, spec.graphql.type.class_name)
            with self.subTest(object_key=spec.key):
                self.assertIs(graphql_types.GRAPHQL_TYPE_CLASS_MAP[spec.key], type_class)
                self.assertIs(type_class.__object_spec__, spec)
                self.assertEqual(type_class.__name__, spec.graphql.type.class_name)


class SerializerSmokeTestCase(SimpleTestCase):
    def test_serializer_urls_use_plugin_namespace(self):
        for spec in API_OBJECT_SPECS:
            serializer_class = getattr(api_serializers, spec.api.serializer_name)
            serializer = serializer_class()
            with self.subTest(object_key=spec.key):
                self.assertEqual(serializer.fields["url"].view_name, spec.api.detail_view_name)

    def test_serializer_class_names_remain_stable(self):
        self.assertEqual(
            [getattr(api_serializers, spec.api.serializer_name).__name__ for spec in API_OBJECT_SPECS],
            [spec.api.serializer_name for spec in API_OBJECT_SPECS],
        )


class ViewSetSmokeTestCase(SimpleTestCase):
    def test_viewsets_define_querysets(self):
        for spec in API_OBJECT_SPECS:
            viewset_class = getattr(api_views, spec.api.viewset_name)
            serializer_class = getattr(api_serializers, spec.api.serializer_name)
            filterset_class = getattr(filtersets, spec.filterset.class_name)
            with self.subTest(object_key=spec.key):
                self.assertEqual(viewset_class.queryset.model, spec.model)
                self.assertIs(viewset_class.serializer_class, serializer_class)
                self.assertIs(viewset_class.filterset_class, filterset_class)


class RouterSmokeTestCase(SimpleTestCase):
    def test_root_view_name_remains_stable(self):
        self.assertEqual(RootView().get_view_name(), 'rpki')

    def test_router_registers_expected_viewsets(self):
        self.assertIs(router.APIRootView, RootView)
        self.assertEqual(
            [(prefix, viewset, basename) for prefix, viewset, basename in router.registry],
            [
                (spec.api.basename, getattr(api_views, spec.api.viewset_name), spec.api.basename)
                for spec in API_OBJECT_SPECS
            ],
        )


OBJECT_SPEC_BY_KEY = {spec.key: spec for spec in API_OBJECT_SPECS}


def _resolve_api_test_value(value, test_case):
    return value(test_case) if callable(value) else value


def _assert_response_fields(test_case, data, expected_fields):
    for field_name, expected_value in expected_fields.items():
        test_case.assertEqual(data[field_name], expected_value)


API_TEST_CASES = {
    'organization': {
        'method_singular': 'organization',
        'method_plural': 'organizations',
        'collection_attr': 'organizations',
        'detail_assertions': {'org_id': 'org-1', 'name': 'Organization 1'},
        'list_filter_query': 'Organization 2',
        'list_filter_assertions': {'org_id': 'org-2'},
        'create_valid_payload': lambda self: {
            'org_id': 'org-4',
            'name': 'Organization 4',
            'ext_url': 'https://example.invalid/org-4',
            'parent_rir': self.rir.pk,
        },
        'create_success_lookup': {'org_id': 'org-4', 'name': 'Organization 4'},
        'create_invalid_payload': {
            'org_id': 'org-invalid',
            'name': 'Organization Invalid',
            'parent_rir': 999999,
        },
        'create_invalid_fields': ('parent_rir',),
        'create_empty_fields': ('org_id', 'name'),
        'update_payload': {'name': 'Organization 1 Updated'},
        'assert_updated': lambda self, instance: self.assertEqual(instance.name, 'Organization 1 Updated'),
    },
    'certificate': {
        'method_singular': 'certificate',
        'method_plural': 'certificates',
        'collection_attr': 'certificates',
        'related_permissions': ('netbox_rpki.view_organization',),
        'detail_assertions': {'name': 'Certificate 1', 'issuer': 'Issuer 1'},
        'list_filter_query': 'Issuer 2',
        'list_filter_assertions': {'name': 'Certificate 2'},
        'create_valid_payload': lambda self: {
            'name': 'Certificate 4',
            'issuer': 'Issuer 4',
            'auto_renews': True,
            'self_hosted': False,
            'rpki_org': self.organizations[0].pk,
        },
        'create_success_lookup': {'name': 'Certificate 4', 'issuer': 'Issuer 4'},
        'create_invalid_payload': {
            'name': 'Certificate Invalid',
            'auto_renews': True,
            'self_hosted': False,
            'rpki_org': 999999,
        },
        'create_invalid_fields': ('rpki_org',),
        'create_empty_fields': ('name', 'auto_renews', 'self_hosted', 'rpki_org'),
        'update_payload': {'issuer': 'Issuer 1 Updated'},
        'assert_updated': lambda self, instance: self.assertEqual(instance.issuer, 'Issuer 1 Updated'),
    },
    'roa': {
        'method_singular': 'roa',
        'method_plural': 'roas',
        'collection_attr': 'roas',
        'related_permissions': ('netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn'),
        'detail_assertions': {'name': 'ROA 1'},
        'list_filter_query': 'ROA 2',
        'list_filter_assertions': {'name': 'ROA 2'},
        'create_valid_payload': lambda self: {
            'name': 'ROA 4',
            'origin_as': self.asns[0].pk,
            'auto_renews': True,
            'signed_by': self.certificates[0].pk,
        },
        'create_success_lookup': {'name': 'ROA 4'},
        'create_invalid_payload': {'name': 'ROA Invalid', 'auto_renews': True, 'signed_by': 999999},
        'create_invalid_fields': ('signed_by',),
        'create_empty_fields': ('name', 'auto_renews', 'signed_by'),
        'update_payload': {'name': 'ROA 1 Updated'},
        'assert_updated': lambda self, instance: self.assertEqual(instance.name, 'ROA 1 Updated'),
    },
    'roaprefix': {
        'method_singular': 'roa_prefix',
        'method_plural': 'roa_prefixes',
        'collection_attr': 'roa_prefixes',
        'related_permissions': ('netbox_rpki.view_roa', 'ipam.view_prefix'),
        'detail_assertions': {'max_length': 24},
        'list_filter_query': '10.20.2.0/24',
        'list_filter_assertions': {'max_length': 25},
        'create_valid_payload': lambda self: {
            'prefix': self.prefixes[0].pk,
            'max_length': 27,
            'roa_name': self.roas[1].pk,
        },
        'create_success_lookup': lambda self: {
            'prefix': self.prefixes[0],
            'roa_name': self.roas[1],
            'max_length': 27,
        },
        'create_invalid_payload': lambda self: {'prefix': 999999, 'max_length': 27, 'roa_name': self.roas[1].pk},
        'create_invalid_fields': ('prefix',),
        'create_empty_fields': ('prefix', 'max_length', 'roa_name'),
        'update_payload': {'max_length': 28},
        'assert_updated': lambda self, instance: self.assertEqual(instance.max_length, 28),
    },
    'certificateprefix': {
        'method_singular': 'certificate_prefix',
        'method_plural': 'certificate_prefixes',
        'collection_attr': 'certificate_prefixes',
        'related_permissions': ('netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_prefix'),
        'detail_assertions': lambda self: {'prefix': self.prefixes[0].pk},
        'list_filter_query': '10.30.2.0/24',
        'create_valid_payload': lambda self: {
            'prefix': self.prefixes[0].pk,
            'certificate_name': self.certificates[1].pk,
        },
        'create_success_lookup': lambda self: {'prefix': self.prefixes[0], 'certificate_name': self.certificates[1]},
        'create_invalid_payload': lambda self: {'prefix': self.prefixes[0].pk, 'certificate_name': 999999},
        'create_invalid_fields': ('certificate_name',),
        'create_empty_fields': ('prefix', 'certificate_name'),
        'update_payload': lambda self: {'certificate_name': self.certificates[2].pk},
        'assert_updated': lambda self, instance: self.assertEqual(instance.certificate_name, self.certificates[2]),
    },
    'certificateasn': {
        'method_singular': 'certificate_asn',
        'method_plural': 'certificate_asns',
        'collection_attr': 'certificate_asns',
        'related_permissions': ('netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn'),
        'detail_assertions': lambda self: {'asn': self.asns[0].pk},
        'list_filter_query': 'Certificate ASN Parent 2',
        'create_valid_payload': lambda self: {
            'asn': self.asns[0].pk,
            'certificate_name2': self.certificates[1].pk,
        },
        'create_success_lookup': lambda self: {'asn': self.asns[0], 'certificate_name2': self.certificates[1]},
        'create_invalid_payload': lambda self: {'asn': 999999, 'certificate_name2': self.certificates[1].pk},
        'create_invalid_fields': ('asn',),
        'create_empty_fields': ('asn', 'certificate_name2'),
        'update_payload': lambda self: {'certificate_name2': self.certificates[2].pk},
        'assert_updated': lambda self, instance: self.assertEqual(instance.certificate_name2, self.certificates[2]),
    },
}


def _install_registry_api_tests(cls):
    cls.model = OBJECT_SPEC_BY_KEY[cls.object_spec_key].model
    case = API_TEST_CASES[cls.object_spec_key]
    test_names = {
        f"test_get_{case['method_singular']}": '_run_get_object_test',
        f"test_list_{case['method_plural']}": '_run_list_objects_test',
        f"test_list_{case['method_plural']}_filters_by_q": '_run_list_filter_test',
        f"test_create_{case['method_singular']}_with_valid_input": '_run_create_valid_test',
        f"test_create_{case['method_singular']}_with_invalid_input": '_run_create_invalid_test',
        f"test_create_{case['method_singular']}_with_empty_input": '_run_create_empty_test',
        f"test_update_{case['method_singular']}_with_valid_input": '_run_update_test',
        f"test_delete_{case['method_singular']}": '_run_delete_test',
    }

    for test_name, runner_name in test_names.items():
        def test_method(self, runner_name=runner_name):
            getattr(self, runner_name)()

        test_method.__name__ = test_name
        setattr(cls, test_name, test_method)

    return cls


class RegistryDrivenObjectAPITestCase(PluginAPITestCase):
    object_spec_key = None

    @property
    def api_case(self):
        return API_TEST_CASES[self.object_spec_key]

    @property
    def object_spec(self):
        return OBJECT_SPEC_BY_KEY[self.object_spec_key]

    def _get_case_value(self, key):
        return _resolve_api_test_value(self.api_case[key], self)

    def _get_case_instance(self, index_key, default_index):
        collection = getattr(self, self.api_case['collection_attr'])
        return collection[self.api_case.get(index_key, default_index)]

    def _action_permissions(self, action):
        return (
            f'netbox_rpki.{action}_{self.object_spec.api.basename}',
            *self.api_case.get('related_permissions', ()),
        )

    def _run_get_object_test(self):
        self.add_permissions(*self._action_permissions('view'))

        response = self.client.get(self._get_detail_url(self._get_case_instance('detail_index', 0)), **self.header)

        self.assertHttpStatus(response, 200)
        _assert_response_fields(self, response.data, self._get_case_value('detail_assertions'))

    def _run_list_objects_test(self):
        self.add_permissions(*self._action_permissions('view'))

        response = self.client.get(self._get_list_url(), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), self.api_case.get('list_expected_count', 3))

    def _run_list_filter_test(self):
        self.add_permissions(*self._action_permissions('view'))

        response = self.client.get(f"{self._get_list_url()}?q={self.api_case['list_filter_query']}", **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), self.api_case.get('list_filter_expected_count', 1))
        expected_fields = self.api_case.get('list_filter_assertions')
        if expected_fields is not None:
            _assert_response_fields(self, response.data['results'][0], _resolve_api_test_value(expected_fields, self))

    def _run_create_valid_test(self):
        self.add_permissions(*self._action_permissions('add'))

        response = self.client.post(
            self._get_list_url(),
            self._get_case_value('create_valid_payload'),
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 201)
        self.assertTrue(self.model.objects.filter(**self._get_case_value('create_success_lookup')).exists())

    def _run_create_invalid_test(self):
        self.add_permissions(*self._action_permissions('add'))

        response = self.client.post(
            self._get_list_url(),
            self._get_case_value('create_invalid_payload'),
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        for field_name in self.api_case['create_invalid_fields']:
            self.assertIn(field_name, response.data)

    def _run_create_empty_test(self):
        self.add_permissions(*self._action_permissions('add'))

        response = self.client.post(self._get_list_url(), {}, format='json', **self.header)

        self.assertHttpStatus(response, 400)
        for field_name in self.api_case['create_empty_fields']:
            self.assertIn(field_name, response.data)

    def _run_update_test(self):
        self.add_permissions(*self._action_permissions('change'))
        instance = self._get_case_instance('update_index', 0)

        response = self.client.patch(
            self._get_detail_url(instance),
            self._get_case_value('update_payload'),
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        instance.refresh_from_db()
        self.api_case['assert_updated'](self, instance)

    def _run_delete_test(self):
        self.add_permissions(*self._action_permissions('delete'))
        instance = self._get_case_instance('delete_index', 2)

        response = self.client.delete(self._get_detail_url(instance), **self.header)

        self.assertHttpStatus(response, 204)
        self.assertFalse(self.model.objects.filter(pk=instance.pk).exists())


@_install_registry_api_tests
class OrganizationAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'organization'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='API RIR', slug='api-rir')
        cls.organizations = [
            create_test_organization(org_id='org-1', name='Organization 1', parent_rir=cls.rir),
            create_test_organization(org_id='org-2', name='Organization 2'),
            create_test_organization(org_id='org-3', name='Organization 3'),
        ]


@_install_registry_api_tests
class CertificateAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'certificate'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='Certificate API RIR', slug='certificate-api-rir')
        cls.organizations = [
            create_test_organization(org_id='cert-org-1', name='Certificate Org 1', parent_rir=cls.rir),
            create_test_organization(org_id='cert-org-2', name='Certificate Org 2'),
            create_test_organization(org_id='cert-org-3', name='Certificate Org 3'),
        ]
        cls.certificates = [
            create_test_certificate(name='Certificate 1', issuer='Issuer 1', rpki_org=cls.organizations[0], self_hosted=False),
            create_test_certificate(name='Certificate 2', issuer='Issuer 2', rpki_org=cls.organizations[1], self_hosted=True),
            create_test_certificate(name='Certificate 3', issuer='Issuer 3', rpki_org=cls.organizations[2], self_hosted=False),
        ]


@_install_registry_api_tests
class RoaAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'roa'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='ROA API RIR', slug='roa-api-rir')
        cls.organizations = [
            create_test_organization(org_id='roa-org-1', name='ROA Org 1', parent_rir=cls.rir),
            create_test_organization(org_id='roa-org-2', name='ROA Org 2'),
            create_test_organization(org_id='roa-org-3', name='ROA Org 3'),
        ]
        cls.certificates = [
            create_test_certificate(name='ROA Certificate 1', rpki_org=cls.organizations[0]),
            create_test_certificate(name='ROA Certificate 2', rpki_org=cls.organizations[1]),
            create_test_certificate(name='ROA Certificate 3', rpki_org=cls.organizations[2]),
        ]
        cls.asns = [
            create_test_asn(65101, rir=cls.rir),
            create_test_asn(65102, rir=cls.rir),
            create_test_asn(65103, rir=cls.rir),
        ]
        cls.roas = [
            create_test_roa(name='ROA 1', origin_as=cls.asns[0], signed_by=cls.certificates[0], auto_renews=True),
            create_test_roa(name='ROA 2', origin_as=cls.asns[1], signed_by=cls.certificates[1], auto_renews=False),
            create_test_roa(name='ROA 3', origin_as=cls.asns[2], signed_by=cls.certificates[2], auto_renews=True),
        ]


@_install_registry_api_tests
class RoaPrefixAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'roaprefix'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='ROA Prefix API RIR', slug='roa-prefix-api-rir')
        cls.organization = create_test_organization(org_id='roa-prefix-org-1', name='ROA Prefix Org 1', parent_rir=cls.rir)
        cls.certificate = create_test_certificate(name='ROA Prefix Certificate', rpki_org=cls.organization)
        cls.roas = [
            create_test_roa(name='ROA Prefix Parent 1', signed_by=cls.certificate),
            create_test_roa(name='ROA Prefix Parent 2', signed_by=cls.certificate),
            create_test_roa(name='ROA Prefix Parent 3', signed_by=cls.certificate),
        ]
        cls.prefixes = [
            create_test_prefix('10.20.1.0/24'),
            create_test_prefix('10.20.2.0/24'),
            create_test_prefix('10.20.3.0/24'),
        ]
        cls.roa_prefixes = [
            create_test_roa_prefix(prefix=cls.prefixes[0], roa=cls.roas[0], max_length=24),
            create_test_roa_prefix(prefix=cls.prefixes[1], roa=cls.roas[1], max_length=25),
            create_test_roa_prefix(prefix=cls.prefixes[2], roa=cls.roas[2], max_length=26),
        ]


@_install_registry_api_tests
class CertificatePrefixAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'certificateprefix'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='Certificate Prefix API RIR', slug='certificate-prefix-api-rir')
        cls.organization = create_test_organization(org_id='certificate-prefix-org-1', name='Certificate Prefix Org 1', parent_rir=cls.rir)
        cls.certificates = [
            create_test_certificate(name='Certificate Prefix Parent 1', rpki_org=cls.organization),
            create_test_certificate(name='Certificate Prefix Parent 2', rpki_org=cls.organization),
            create_test_certificate(name='Certificate Prefix Parent 3', rpki_org=cls.organization),
        ]
        cls.prefixes = [
            create_test_prefix('10.30.1.0/24'),
            create_test_prefix('10.30.2.0/24'),
            create_test_prefix('10.30.3.0/24'),
        ]
        cls.certificate_prefixes = [
            create_test_certificate_prefix(prefix=cls.prefixes[0], certificate=cls.certificates[0]),
            create_test_certificate_prefix(prefix=cls.prefixes[1], certificate=cls.certificates[1]),
            create_test_certificate_prefix(prefix=cls.prefixes[2], certificate=cls.certificates[2]),
        ]


@_install_registry_api_tests
class CertificateAsnAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'certificateasn'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='Certificate ASN API RIR', slug='certificate-asn-api-rir')
        cls.organization = create_test_organization(org_id='certificate-asn-org-1', name='Certificate ASN Org 1', parent_rir=cls.rir)
        cls.certificates = [
            create_test_certificate(name='Certificate ASN Parent 1', rpki_org=cls.organization),
            create_test_certificate(name='Certificate ASN Parent 2', rpki_org=cls.organization),
            create_test_certificate(name='Certificate ASN Parent 3', rpki_org=cls.organization),
        ]
        cls.asns = [
            create_test_asn(65201, rir=cls.rir),
            create_test_asn(65202, rir=cls.rir),
            create_test_asn(65203, rir=cls.rir),
        ]
        cls.certificate_asns = [
            create_test_certificate_asn(asn=cls.asns[0], certificate=cls.certificates[0]),
            create_test_certificate_asn(asn=cls.asns[1], certificate=cls.certificates[1]),
            create_test_certificate_asn(asn=cls.asns[2], certificate=cls.certificates[2]),
        ]

