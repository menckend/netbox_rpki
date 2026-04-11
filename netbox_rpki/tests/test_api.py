from django.test import SimpleTestCase

from netbox_rpki.api.serializers import (
    CertificateAsnSerializer,
    CertificatePrefixSerializer,
    CertificateSerializer,
    OrganizationSerializer,
    RoaPrefixSerializer,
    RoaSerializer,
)
from netbox_rpki.api.views import (
    CertificateAsnViewSet,
    CertificatePrefixViewSet,
    CertificateViewSet,
    OrganizationViewSet,
    RoaPrefixViewSet,
    RoaViewSet,
)
from netbox_rpki.models import (
    Certificate,
    CertificateAsn,
    CertificatePrefix,
    Organization,
    Roa,
    RoaPrefix,
)
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


class SerializerSmokeTestCase(SimpleTestCase):
    def test_serializer_urls_use_plugin_namespace(self):
        serializer_map = {
            CertificateSerializer: "plugins-api:netbox_rpki-api:certificate-detail",
            OrganizationSerializer: "plugins-api:netbox_rpki-api:organization-detail",
            RoaSerializer: "plugins-api:netbox_rpki-api:roa-detail",
            RoaPrefixSerializer: "plugins-api:netbox_rpki-api:roaprefix-detail",
            CertificatePrefixSerializer: "plugins-api:netbox_rpki-api:certificateprefix-detail",
            CertificateAsnSerializer: "plugins-api:netbox_rpki-api:certificateasn-detail",
        }

        for serializer_class, expected_view_name in serializer_map.items():
            serializer = serializer_class()
            self.assertEqual(serializer.fields["url"].view_name, expected_view_name)


class ViewSetSmokeTestCase(SimpleTestCase):
    def test_viewsets_define_querysets(self):
        viewset_map = {
            OrganizationViewSet: Organization,
            CertificateViewSet: Certificate,
            RoaViewSet: Roa,
            RoaPrefixViewSet: RoaPrefix,
            CertificatePrefixViewSet: CertificatePrefix,
            CertificateAsnViewSet: CertificateAsn,
        }

        for viewset_class, expected_model in viewset_map.items():
            self.assertEqual(viewset_class.queryset.model, expected_model)


class OrganizationAPITestCase(PluginAPITestCase):
    model = Organization

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='API RIR', slug='api-rir')
        cls.organizations = [
            create_test_organization(org_id='org-1', name='Organization 1', parent_rir=cls.rir),
            create_test_organization(org_id='org-2', name='Organization 2'),
            create_test_organization(org_id='org-3', name='Organization 3'),
        ]

    def test_get_organization(self):
        self.add_permissions('netbox_rpki.view_organization')

        response = self.client.get(self._get_detail_url(self.organizations[0]), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['org_id'], 'org-1')
        self.assertEqual(response.data['name'], 'Organization 1')

    def test_list_organizations(self):
        self.add_permissions('netbox_rpki.view_organization')

        response = self.client.get(self._get_list_url(), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 3)

    def test_list_organizations_filters_by_q(self):
        self.add_permissions('netbox_rpki.view_organization')

        response = self.client.get(f'{self._get_list_url()}?q=Organization 2', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['org_id'], 'org-2')

    def test_create_organization_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_organization')

        response = self.client.post(
            self._get_list_url(),
            {
                'org_id': 'org-4',
                'name': 'Organization 4',
                'ext_url': 'https://example.invalid/org-4',
                'parent_rir': self.rir.pk,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 201)
        self.assertTrue(Organization.objects.filter(org_id='org-4', name='Organization 4').exists())

    def test_create_organization_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_organization')

        response = self.client.post(
            self._get_list_url(),
            {
                'org_id': 'org-invalid',
                'name': 'Organization Invalid',
                'parent_rir': 999999,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        self.assertIn('parent_rir', response.data)

    def test_create_organization_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_organization')

        response = self.client.post(self._get_list_url(), {}, format='json', **self.header)

        self.assertHttpStatus(response, 400)
        self.assertIn('org_id', response.data)
        self.assertIn('name', response.data)

    def test_update_organization_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_organization')

        response = self.client.patch(
            self._get_detail_url(self.organizations[0]),
            {'name': 'Organization 1 Updated'},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.organizations[0].refresh_from_db()
        self.assertEqual(self.organizations[0].name, 'Organization 1 Updated')

    def test_delete_organization(self):
        self.add_permissions('netbox_rpki.delete_organization')

        response = self.client.delete(self._get_detail_url(self.organizations[2]), **self.header)

        self.assertHttpStatus(response, 204)
        self.assertFalse(Organization.objects.filter(pk=self.organizations[2].pk).exists())


class CertificateAPITestCase(PluginAPITestCase):
    model = Certificate

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

    def test_get_certificate(self):
        self.add_permissions('netbox_rpki.view_certificate', 'netbox_rpki.view_organization')

        response = self.client.get(self._get_detail_url(self.certificates[0]), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['name'], 'Certificate 1')
        self.assertEqual(response.data['issuer'], 'Issuer 1')

    def test_list_certificates(self):
        self.add_permissions('netbox_rpki.view_certificate', 'netbox_rpki.view_organization')

        response = self.client.get(self._get_list_url(), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 3)

    def test_list_certificates_filters_by_q(self):
        self.add_permissions('netbox_rpki.view_certificate', 'netbox_rpki.view_organization')

        response = self.client.get(f'{self._get_list_url()}?q=Issuer 2', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'Certificate 2')

    def test_create_certificate_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_certificate', 'netbox_rpki.view_organization')

        response = self.client.post(
            self._get_list_url(),
            {
                'name': 'Certificate 4',
                'issuer': 'Issuer 4',
                'auto_renews': True,
                'self_hosted': False,
                'rpki_org': self.organizations[0].pk,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 201)
        self.assertTrue(Certificate.objects.filter(name='Certificate 4', issuer='Issuer 4').exists())

    def test_create_certificate_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_certificate', 'netbox_rpki.view_organization')

        response = self.client.post(
            self._get_list_url(),
            {
                'name': 'Certificate Invalid',
                'auto_renews': True,
                'self_hosted': False,
                'rpki_org': 999999,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        self.assertIn('rpki_org', response.data)

    def test_create_certificate_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_certificate', 'netbox_rpki.view_organization')

        response = self.client.post(self._get_list_url(), {}, format='json', **self.header)

        self.assertHttpStatus(response, 400)
        self.assertIn('name', response.data)
        self.assertIn('auto_renews', response.data)
        self.assertIn('self_hosted', response.data)
        self.assertIn('rpki_org', response.data)

    def test_update_certificate_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_certificate', 'netbox_rpki.view_organization')

        response = self.client.patch(
            self._get_detail_url(self.certificates[0]),
            {'issuer': 'Issuer 1 Updated'},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.certificates[0].refresh_from_db()
        self.assertEqual(self.certificates[0].issuer, 'Issuer 1 Updated')

    def test_delete_certificate(self):
        self.add_permissions('netbox_rpki.delete_certificate', 'netbox_rpki.view_organization')

        response = self.client.delete(self._get_detail_url(self.certificates[2]), **self.header)

        self.assertHttpStatus(response, 204)
        self.assertFalse(Certificate.objects.filter(pk=self.certificates[2].pk).exists())


class RoaAPITestCase(PluginAPITestCase):
    model = Roa

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

    def test_get_roa(self):
        self.add_permissions('netbox_rpki.view_roa', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.get(self._get_detail_url(self.roas[0]), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['name'], 'ROA 1')

    def test_list_roas(self):
        self.add_permissions('netbox_rpki.view_roa', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.get(self._get_list_url(), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 3)

    def test_list_roas_filters_by_q(self):
        self.add_permissions('netbox_rpki.view_roa', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.get(f'{self._get_list_url()}?q=ROA 2', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'ROA 2')

    def test_create_roa_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_roa', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.post(
            self._get_list_url(),
            {
                'name': 'ROA 4',
                'origin_as': self.asns[0].pk,
                'auto_renews': True,
                'signed_by': self.certificates[0].pk,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 201)
        self.assertTrue(Roa.objects.filter(name='ROA 4').exists())

    def test_create_roa_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_roa', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.post(
            self._get_list_url(),
            {
                'name': 'ROA Invalid',
                'auto_renews': True,
                'signed_by': 999999,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        self.assertIn('signed_by', response.data)

    def test_create_roa_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_roa', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.post(self._get_list_url(), {}, format='json', **self.header)

        self.assertHttpStatus(response, 400)
        self.assertIn('name', response.data)
        self.assertIn('auto_renews', response.data)
        self.assertIn('signed_by', response.data)

    def test_update_roa_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_roa', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.patch(
            self._get_detail_url(self.roas[0]),
            {'name': 'ROA 1 Updated'},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.roas[0].refresh_from_db()
        self.assertEqual(self.roas[0].name, 'ROA 1 Updated')

    def test_delete_roa(self):
        self.add_permissions('netbox_rpki.delete_roa', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.delete(self._get_detail_url(self.roas[2]), **self.header)

        self.assertHttpStatus(response, 204)
        self.assertFalse(Roa.objects.filter(pk=self.roas[2].pk).exists())


class RoaPrefixAPITestCase(PluginAPITestCase):
    model = RoaPrefix

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

    def test_get_roa_prefix(self):
        self.add_permissions('netbox_rpki.view_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.get(self._get_detail_url(self.roa_prefixes[0]), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['max_length'], 24)

    def test_list_roa_prefixes(self):
        self.add_permissions('netbox_rpki.view_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.get(self._get_list_url(), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 3)

    def test_list_roa_prefixes_filters_by_q(self):
        self.add_permissions('netbox_rpki.view_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.get(f'{self._get_list_url()}?q=10.20.2.0/24', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['max_length'], 25)

    def test_create_roa_prefix_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.post(
            self._get_list_url(),
            {
                'prefix': self.prefixes[0].pk,
                'max_length': 27,
                'roa_name': self.roas[1].pk,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 201)
        self.assertTrue(RoaPrefix.objects.filter(prefix=self.prefixes[0], roa_name=self.roas[1], max_length=27).exists())

    def test_create_roa_prefix_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.post(
            self._get_list_url(),
            {
                'prefix': 999999,
                'max_length': 27,
                'roa_name': self.roas[1].pk,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        self.assertIn('prefix', response.data)

    def test_create_roa_prefix_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.post(self._get_list_url(), {}, format='json', **self.header)

        self.assertHttpStatus(response, 400)
        self.assertIn('prefix', response.data)
        self.assertIn('max_length', response.data)
        self.assertIn('roa_name', response.data)

    def test_update_roa_prefix_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.patch(
            self._get_detail_url(self.roa_prefixes[0]),
            {'max_length': 28},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.roa_prefixes[0].refresh_from_db()
        self.assertEqual(self.roa_prefixes[0].max_length, 28)

    def test_delete_roa_prefix(self):
        self.add_permissions('netbox_rpki.delete_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.delete(self._get_detail_url(self.roa_prefixes[2]), **self.header)

        self.assertHttpStatus(response, 204)
        self.assertFalse(RoaPrefix.objects.filter(pk=self.roa_prefixes[2].pk).exists())


class CertificatePrefixAPITestCase(PluginAPITestCase):
    model = CertificatePrefix

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

    def test_get_certificate_prefix(self):
        self.add_permissions('netbox_rpki.view_certificateprefix', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_prefix')

        response = self.client.get(self._get_detail_url(self.certificate_prefixes[0]), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['prefix'], self.prefixes[0].pk)

    def test_list_certificate_prefixes(self):
        self.add_permissions('netbox_rpki.view_certificateprefix', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_prefix')

        response = self.client.get(self._get_list_url(), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 3)

    def test_list_certificate_prefixes_filters_by_q(self):
        self.add_permissions('netbox_rpki.view_certificateprefix', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_prefix')

        response = self.client.get(f'{self._get_list_url()}?q=10.30.2.0/24', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 1)

    def test_create_certificate_prefix_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_certificateprefix', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_prefix')

        response = self.client.post(
            self._get_list_url(),
            {
                'prefix': self.prefixes[0].pk,
                'certificate_name': self.certificates[1].pk,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 201)
        self.assertTrue(CertificatePrefix.objects.filter(prefix=self.prefixes[0], certificate_name=self.certificates[1]).exists())

    def test_create_certificate_prefix_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_certificateprefix', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_prefix')

        response = self.client.post(
            self._get_list_url(),
            {
                'prefix': self.prefixes[0].pk,
                'certificate_name': 999999,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        self.assertIn('certificate_name', response.data)

    def test_create_certificate_prefix_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_certificateprefix', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_prefix')

        response = self.client.post(self._get_list_url(), {}, format='json', **self.header)

        self.assertHttpStatus(response, 400)
        self.assertIn('prefix', response.data)
        self.assertIn('certificate_name', response.data)

    def test_update_certificate_prefix_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_certificateprefix', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_prefix')

        response = self.client.patch(
            self._get_detail_url(self.certificate_prefixes[0]),
            {'certificate_name': self.certificates[2].pk},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.certificate_prefixes[0].refresh_from_db()
        self.assertEqual(self.certificate_prefixes[0].certificate_name, self.certificates[2])

    def test_delete_certificate_prefix(self):
        self.add_permissions('netbox_rpki.delete_certificateprefix', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_prefix')

        response = self.client.delete(self._get_detail_url(self.certificate_prefixes[2]), **self.header)

        self.assertHttpStatus(response, 204)
        self.assertFalse(CertificatePrefix.objects.filter(pk=self.certificate_prefixes[2].pk).exists())


class CertificateAsnAPITestCase(PluginAPITestCase):
    model = CertificateAsn

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

    def test_get_certificate_asn(self):
        self.add_permissions('netbox_rpki.view_certificateasn', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.get(self._get_detail_url(self.certificate_asns[0]), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['asn'], self.asns[0].pk)

    def test_list_certificate_asns(self):
        self.add_permissions('netbox_rpki.view_certificateasn', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.get(self._get_list_url(), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 3)

    def test_list_certificate_asns_filters_by_q(self):
        self.add_permissions('netbox_rpki.view_certificateasn', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.get(f'{self._get_list_url()}?q=Certificate ASN Parent 2', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 1)

    def test_create_certificate_asn_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_certificateasn', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.post(
            self._get_list_url(),
            {
                'asn': self.asns[0].pk,
                'certificate_name2': self.certificates[1].pk,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 201)
        self.assertTrue(CertificateAsn.objects.filter(asn=self.asns[0], certificate_name2=self.certificates[1]).exists())

    def test_create_certificate_asn_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_certificateasn', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.post(
            self._get_list_url(),
            {
                'asn': 999999,
                'certificate_name2': self.certificates[1].pk,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        self.assertIn('asn', response.data)

    def test_create_certificate_asn_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_certificateasn', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.post(self._get_list_url(), {}, format='json', **self.header)

        self.assertHttpStatus(response, 400)
        self.assertIn('asn', response.data)
        self.assertIn('certificate_name2', response.data)

    def test_update_certificate_asn_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_certificateasn', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.patch(
            self._get_detail_url(self.certificate_asns[0]),
            {'certificate_name2': self.certificates[2].pk},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.certificate_asns[0].refresh_from_db()
        self.assertEqual(self.certificate_asns[0].certificate_name2, self.certificates[2])

    def test_delete_certificate_asn(self):
        self.add_permissions('netbox_rpki.delete_certificateasn', 'netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn')

        response = self.client.delete(self._get_detail_url(self.certificate_asns[2]), **self.header)

        self.assertHttpStatus(response, 204)
        self.assertFalse(CertificateAsn.objects.filter(pk=self.certificate_asns[2].pk).exists())

