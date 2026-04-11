from datetime import date

from django.urls import reverse
from django.utils.formats import date_format

from netbox_rpki.models import Certificate, CertificateAsn, CertificatePrefix, Organization, Roa, RoaPrefix
from netbox_rpki.tests.base import PluginViewTestCase
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
from utilities.testing.utils import post_data


class OrganizationViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='View RIR', slug='view-rir')
        cls.organizations = [
            create_test_organization(org_id='view-org-1', name='View Organization 1', parent_rir=cls.rir),
            create_test_organization(org_id='view-org-2', name='View Organization 2'),
            create_test_organization(org_id='view-org-3', name='View Organization 3'),
        ]
        cls.certificates = [
            create_test_certificate(name='Organization Certificate 1', rpki_org=cls.organizations[0]),
            create_test_certificate(name='Organization Certificate 2', rpki_org=cls.organizations[1]),
        ]

    def test_organization_list_view_renders(self):
        self.add_permissions('netbox_rpki.view_organization')

        response = self.client.get(self.plugin_url('organization_list'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'View Organization 1')
        self.assertContains(response, 'View Organization 2')

    def test_create_organization_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_organization', 'ipam.view_rir')

        response = self.client.post(
            self.plugin_url('organization_add'),
            post_data(
                {
                    'org_id': 'view-org-4',
                    'name': 'View Organization 4',
                    'ext_url': 'https://example.invalid/view-org-4',
                    'parent_rir': self.rir,
                }
            ),
        )

        self.assertHttpStatus(response, 302)
        self.assertTrue(Organization.objects.filter(org_id='view-org-4', name='View Organization 4').exists())

    def test_create_organization_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_organization')

        response = self.client.post(
            self.plugin_url('organization_add'),
            post_data({'name': 'View Organization Invalid'}),
        )

        self.assertHttpStatus(response, 200)
        self.assertFalse(Organization.objects.filter(name='View Organization Invalid').exists())
        self.assertFormErrors(response, 'org_id', 'This field is required')

    def test_create_organization_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_organization')

        response = self.client.post(self.plugin_url('organization_add'), post_data({}))

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, 'org_id', 'name', 'This field is required')

    def test_edit_organization_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_organization', 'ipam.view_rir')

        response = self.client.post(
            self.plugin_url('organization_edit', self.organizations[0]),
            post_data(
                {
                    'org_id': self.organizations[0].org_id,
                    'name': 'View Organization 1 Updated',
                    'parent_rir': self.rir,
                }
            ),
        )

        self.assertHttpStatus(response, 302)
        self.organizations[0].refresh_from_db()
        self.assertEqual(self.organizations[0].name, 'View Organization 1 Updated')

    def test_delete_organization(self):
        self.add_permissions('netbox_rpki.delete_organization')

        response = self.client.post(
            self.plugin_url('organization_delete', self.organizations[2]),
            post_data({'confirm': True}),
        )

        self.assertHttpStatus(response, 302)
        self.assertFalse(Organization.objects.filter(pk=self.organizations[2].pk).exists())

    def test_organization_detail_renders_certificates_table_and_prefill_link(self):
        self.add_permissions('netbox_rpki.view_organization', 'netbox_rpki.change_organization')

        response = self.client.get(self.organizations[0].get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Organization Certificate 1')
        self.assertContains(
            response,
            f'{reverse("plugins:netbox_rpki:certificate_add")}?rpki_org={self.organizations[0].pk}',
        )


class CertificateViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='Certificate View RIR', slug='certificate-view-rir')
        cls.organizations = [
            create_test_organization(org_id='cert-view-org-1', name='Certificate View Org 1', parent_rir=cls.rir),
            create_test_organization(org_id='cert-view-org-2', name='Certificate View Org 2'),
            create_test_organization(org_id='cert-view-org-3', name='Certificate View Org 3'),
        ]
        cls.certificates = [
            create_test_certificate(name='View Certificate 1', issuer='View Issuer 1', rpki_org=cls.organizations[0], self_hosted=False),
            create_test_certificate(name='View Certificate 2', issuer='View Issuer 2', rpki_org=cls.organizations[1], self_hosted=True),
            create_test_certificate(name='View Certificate 3', issuer='View Issuer 3', rpki_org=cls.organizations[2], self_hosted=False),
        ]
        cls.prefix = create_test_prefix('10.10.10.0/24')
        cls.asn = create_test_asn(65010, rir=cls.rir)
        cls.roa = create_test_roa(name='View ROA 1', signed_by=cls.certificates[0], auto_renews=True)
        cls.certificate_prefix = create_test_certificate_prefix(prefix=cls.prefix, certificate=cls.certificates[0])
        cls.certificate_asn = create_test_certificate_asn(asn=cls.asn, certificate=cls.certificates[0])

    def test_certificate_list_view_renders(self):
        self.add_permissions('netbox_rpki.view_certificate')

        response = self.client.get(self.plugin_url('certificate_list'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'View Certificate 1')
        self.assertContains(response, 'View Certificate 2')

    def test_certificate_list_view_filters_by_q(self):
        self.add_permissions('netbox_rpki.view_certificate')

        response = self.client.get(f'{self.plugin_url("certificate_list")}?q=View Issuer 2')

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'View Certificate 2')
        self.assertNotContains(response, 'View Certificate 1')

    def test_create_certificate_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_certificate', 'netbox_rpki.view_organization')

        response = self.client.post(
            self.plugin_url('certificate_add'),
            post_data(
                {
                    'name': 'View Certificate 4',
                    'issuer': 'View Issuer 4',
                    'auto_renews': True,
                    'self_hosted': False,
                    'rpki_org': self.organizations[0],
                }
            ),
        )

        self.assertHttpStatus(response, 302)
        self.assertTrue(Certificate.objects.filter(name='View Certificate 4', issuer='View Issuer 4').exists())

    def test_create_certificate_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_certificate', 'netbox_rpki.view_organization')

        response = self.client.post(
            self.plugin_url('certificate_add'),
            post_data(
                {
                    'issuer': 'Invalid Certificate',
                    'auto_renews': True,
                    'self_hosted': False,
                    'rpki_org': self.organizations[0],
                }
            ),
        )

        self.assertHttpStatus(response, 200)
        self.assertFalse(Certificate.objects.filter(issuer='Invalid Certificate').exists())
        self.assertFormErrors(response, 'name', 'This field is required')

    def test_create_certificate_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_certificate')

        response = self.client.post(self.plugin_url('certificate_add'), post_data({}))

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, 'name', 'rpki_org', 'auto_renews', 'self_hosted')

    def test_edit_certificate_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_certificate', 'netbox_rpki.view_organization')

        response = self.client.post(
            self.plugin_url('certificate_edit', self.certificates[0]),
            post_data(
                {
                    'name': self.certificates[0].name,
                    'issuer': 'View Issuer 1 Updated',
                    'auto_renews': True,
                    'self_hosted': False,
                    'rpki_org': self.organizations[0],
                }
            ),
        )

        self.assertHttpStatus(response, 302)
        self.certificates[0].refresh_from_db()
        self.assertEqual(self.certificates[0].issuer, 'View Issuer 1 Updated')

    def test_delete_certificate(self):
        self.add_permissions('netbox_rpki.delete_certificate')

        response = self.client.post(
            self.plugin_url('certificate_delete', self.certificates[2]),
            post_data({'confirm': True}),
        )

        self.assertHttpStatus(response, 302)
        self.assertFalse(Certificate.objects.filter(pk=self.certificates[2].pk).exists())

    def test_certificate_detail_renders_related_tables_and_prefill_links(self):
        self.add_permissions('netbox_rpki.view_certificate', 'netbox_rpki.change_certificate')

        response = self.client.get(self.certificates[0].get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, str(self.prefix.prefix))
        self.assertContains(response, str(self.asn))
        self.assertContains(response, self.roa.name)
        self.assertContains(
            response,
            f'{reverse("plugins:netbox_rpki:certificateprefix_add")}?certificate_name={self.certificates[0].pk}',
        )
        self.assertContains(
            response,
            f'{reverse("plugins:netbox_rpki:certificateasn_add")}?certificate_name2={self.certificates[0].pk}',
        )
        self.assertContains(
            response,
            f'{reverse("plugins:netbox_rpki:roa_add")}?signed_by={self.certificates[0].pk}',
        )


class RoaViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='ROA View RIR', slug='roa-view-rir')
        cls.organization = create_test_organization(org_id='roa-view-org-1', name='ROA View Org 1', parent_rir=cls.rir)
        cls.certificates = [
            create_test_certificate(name='ROA View Certificate 1', rpki_org=cls.organization),
            create_test_certificate(name='ROA View Certificate 2', rpki_org=cls.organization),
            create_test_certificate(name='ROA View Certificate 3', rpki_org=cls.organization),
        ]
        cls.asns = [
            create_test_asn(65301, rir=cls.rir),
            create_test_asn(65302, rir=cls.rir),
            create_test_asn(65303, rir=cls.rir),
        ]
        cls.roas = [
            create_test_roa(
                name='View ROA 1',
                origin_as=cls.asns[0],
                signed_by=cls.certificates[0],
                auto_renews=True,
                valid_from=date(2025, 1, 1),
                valid_to=date(2025, 12, 31),
            ),
            create_test_roa(name='View ROA 2', origin_as=cls.asns[1], signed_by=cls.certificates[1], auto_renews=False),
            create_test_roa(name='View ROA 3', origin_as=cls.asns[2], signed_by=cls.certificates[2], auto_renews=True),
        ]
        cls.prefixes = [
            create_test_prefix('10.40.1.0/24'),
            create_test_prefix('10.40.2.0/24'),
        ]
        cls.roa_prefix = create_test_roa_prefix(prefix=cls.prefixes[0], roa=cls.roas[0], max_length=24)

    def test_roa_list_view_renders(self):
        self.add_permissions('netbox_rpki.view_roa')

        response = self.client.get(self.plugin_url('roa_list'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'View ROA 1')
        self.assertContains(response, 'View ROA 2')

    def test_create_roa_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_roa', 'netbox_rpki.view_certificate', 'ipam.view_asn')

        response = self.client.post(
            self.plugin_url('roa_add'),
            post_data(
                {
                    'name': 'View ROA 4',
                    'origin_as': self.asns[0],
                    'auto_renews': True,
                    'signed_by': self.certificates[0],
                }
            ),
        )

        self.assertHttpStatus(response, 302)
        self.assertTrue(Roa.objects.filter(name='View ROA 4').exists())

    def test_create_roa_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_roa', 'netbox_rpki.view_certificate', 'ipam.view_asn')

        response = self.client.post(
            self.plugin_url('roa_add'),
            post_data({'auto_renews': True, 'signed_by': self.certificates[0]}),
        )

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, 'name', 'This field is required')

    def test_create_roa_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_roa', 'netbox_rpki.view_certificate', 'ipam.view_asn')

        response = self.client.post(self.plugin_url('roa_add'), post_data({}))

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, 'name', 'signed_by', 'This field is required')

    def test_edit_roa_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_roa', 'netbox_rpki.view_certificate', 'ipam.view_asn')

        response = self.client.post(
            self.plugin_url('roa_edit', self.roas[0]),
            post_data(
                {
                    'name': 'View ROA 1 Updated',
                    'origin_as': self.asns[0],
                    'auto_renews': True,
                    'signed_by': self.certificates[0],
                }
            ),
        )

        self.assertHttpStatus(response, 302)
        self.roas[0].refresh_from_db()
        self.assertEqual(self.roas[0].name, 'View ROA 1 Updated')

    def test_delete_roa(self):
        self.add_permissions('netbox_rpki.delete_roa')

        response = self.client.post(
            self.plugin_url('roa_delete', self.roas[2]),
            post_data({'confirm': True}),
        )

        self.assertHttpStatus(response, 302)
        self.assertFalse(Roa.objects.filter(pk=self.roas[2].pk).exists())

    def test_roa_detail_renders_prefix_table_and_prefill_link(self):
        self.add_permissions('netbox_rpki.view_roa', 'netbox_rpki.change_roa')

        response = self.client.get(self.roas[0].get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, str(self.prefixes[0].prefix))
        self.assertContains(response, date_format(self.roas[0].valid_from))
        self.assertContains(response, date_format(self.roas[0].valid_to))
        self.assertContains(
            response,
            f'{reverse("plugins:netbox_rpki:roaprefix_add")}?roa_name={self.roas[0].pk}',
        )


class RoaPrefixViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='ROA Prefix View RIR', slug='roa-prefix-view-rir')
        cls.organization = create_test_organization(org_id='roa-prefix-view-org-1', name='ROA Prefix View Org 1', parent_rir=cls.rir)
        cls.certificate = create_test_certificate(name='ROA Prefix View Certificate', rpki_org=cls.organization)
        cls.roas = [
            create_test_roa(name='ROA Prefix View Parent 1', signed_by=cls.certificate),
            create_test_roa(name='ROA Prefix View Parent 2', signed_by=cls.certificate),
            create_test_roa(name='ROA Prefix View Parent 3', signed_by=cls.certificate),
        ]
        cls.prefixes = [
            create_test_prefix('10.50.1.0/24'),
            create_test_prefix('10.50.2.0/24'),
            create_test_prefix('10.50.3.0/24'),
        ]
        cls.roa_prefixes = [
            create_test_roa_prefix(prefix=cls.prefixes[0], roa=cls.roas[0], max_length=24),
            create_test_roa_prefix(prefix=cls.prefixes[1], roa=cls.roas[1], max_length=25),
            create_test_roa_prefix(prefix=cls.prefixes[2], roa=cls.roas[2], max_length=26),
        ]

    def test_roa_prefix_list_view_renders(self):
        self.add_permissions('netbox_rpki.view_roaprefix')

        response = self.client.get(self.plugin_url('roaprefix_list'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, '10.50.1.0/24')
        self.assertContains(response, '10.50.2.0/24')

    def test_create_roa_prefix_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.post(
            self.plugin_url('roaprefix_add'),
            post_data({'prefix': self.prefixes[0], 'max_length': 27, 'roa_name': self.roas[1]}),
        )

        self.assertHttpStatus(response, 302)
        self.assertTrue(RoaPrefix.objects.filter(prefix=self.prefixes[0], roa_name=self.roas[1], max_length=27).exists())

    def test_create_roa_prefix_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.post(
            self.plugin_url('roaprefix_add'),
            post_data({'max_length': 27, 'roa_name': self.roas[1]}),
        )

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, 'prefix', 'This field is required')

    def test_create_roa_prefix_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.post(self.plugin_url('roaprefix_add'), post_data({}))

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, 'prefix', 'max_length', 'roa_name', 'This field is required')

    def test_edit_roa_prefix_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')

        response = self.client.post(
            self.plugin_url('roaprefix_edit', self.roa_prefixes[0]),
            post_data({'prefix': self.prefixes[0], 'max_length': 28, 'roa_name': self.roas[0]}),
        )

        self.assertHttpStatus(response, 302)
        self.roa_prefixes[0].refresh_from_db()
        self.assertEqual(self.roa_prefixes[0].max_length, 28)

    def test_delete_roa_prefix(self):
        self.add_permissions('netbox_rpki.delete_roaprefix')

        response = self.client.post(
            self.plugin_url('roaprefix_delete', self.roa_prefixes[2]),
            post_data({'confirm': True}),
        )

        self.assertHttpStatus(response, 302)
        self.assertFalse(RoaPrefix.objects.filter(pk=self.roa_prefixes[2].pk).exists())


class CertificatePrefixViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='Certificate Prefix View RIR', slug='certificate-prefix-view-rir')
        cls.organization = create_test_organization(org_id='certificate-prefix-view-org-1', name='Certificate Prefix View Org 1', parent_rir=cls.rir)
        cls.certificates = [
            create_test_certificate(name='Certificate Prefix View Parent 1', rpki_org=cls.organization),
            create_test_certificate(name='Certificate Prefix View Parent 2', rpki_org=cls.organization),
            create_test_certificate(name='Certificate Prefix View Parent 3', rpki_org=cls.organization),
        ]
        cls.prefixes = [
            create_test_prefix('10.60.1.0/24'),
            create_test_prefix('10.60.2.0/24'),
            create_test_prefix('10.60.3.0/24'),
        ]
        cls.certificate_prefixes = [
            create_test_certificate_prefix(prefix=cls.prefixes[0], certificate=cls.certificates[0]),
            create_test_certificate_prefix(prefix=cls.prefixes[1], certificate=cls.certificates[1]),
            create_test_certificate_prefix(prefix=cls.prefixes[2], certificate=cls.certificates[2]),
        ]

    def test_certificate_prefix_list_view_renders(self):
        self.add_permissions('netbox_rpki.view_certificateprefix')

        response = self.client.get(self.plugin_url('certificateprefix_list'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, '10.60.1.0/24')
        self.assertContains(response, '10.60.2.0/24')

    def test_create_certificate_prefix_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_certificateprefix', 'netbox_rpki.view_certificate', 'ipam.view_prefix')

        response = self.client.post(
            self.plugin_url('certificateprefix_add'),
            post_data({'prefix': self.prefixes[0], 'certificate_name': self.certificates[1]}),
        )

        self.assertHttpStatus(response, 302)
        self.assertTrue(CertificatePrefix.objects.filter(prefix=self.prefixes[0], certificate_name=self.certificates[1]).exists())

    def test_create_certificate_prefix_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_certificateprefix', 'netbox_rpki.view_certificate', 'ipam.view_prefix')

        response = self.client.post(
            self.plugin_url('certificateprefix_add'),
            post_data({'certificate_name': self.certificates[1]}),
        )

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, 'prefix', 'This field is required')

    def test_create_certificate_prefix_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_certificateprefix', 'netbox_rpki.view_certificate', 'ipam.view_prefix')

        response = self.client.post(self.plugin_url('certificateprefix_add'), post_data({}))

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, 'prefix', 'certificate_name', 'This field is required')

    def test_edit_certificate_prefix_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_certificateprefix', 'netbox_rpki.view_certificate', 'ipam.view_prefix')

        response = self.client.post(
            self.plugin_url('certificateprefix_edit', self.certificate_prefixes[0]),
            post_data({'prefix': self.prefixes[0], 'certificate_name': self.certificates[2]}),
        )

        self.assertHttpStatus(response, 302)
        self.certificate_prefixes[0].refresh_from_db()
        self.assertEqual(self.certificate_prefixes[0].certificate_name, self.certificates[2])

    def test_delete_certificate_prefix(self):
        self.add_permissions('netbox_rpki.delete_certificateprefix')

        response = self.client.post(
            self.plugin_url('certificateprefix_delete', self.certificate_prefixes[2]),
            post_data({'confirm': True}),
        )

        self.assertHttpStatus(response, 302)
        self.assertFalse(CertificatePrefix.objects.filter(pk=self.certificate_prefixes[2].pk).exists())


class CertificateAsnViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='Certificate ASN View RIR', slug='certificate-asn-view-rir')
        cls.organization = create_test_organization(org_id='certificate-asn-view-org-1', name='Certificate ASN View Org 1', parent_rir=cls.rir)
        cls.certificates = [
            create_test_certificate(name='Certificate ASN View Parent 1', rpki_org=cls.organization),
            create_test_certificate(name='Certificate ASN View Parent 2', rpki_org=cls.organization),
            create_test_certificate(name='Certificate ASN View Parent 3', rpki_org=cls.organization),
        ]
        cls.asns = [
            create_test_asn(65401, rir=cls.rir),
            create_test_asn(65402, rir=cls.rir),
            create_test_asn(65403, rir=cls.rir),
        ]
        cls.certificate_asns = [
            create_test_certificate_asn(asn=cls.asns[0], certificate=cls.certificates[0]),
            create_test_certificate_asn(asn=cls.asns[1], certificate=cls.certificates[1]),
            create_test_certificate_asn(asn=cls.asns[2], certificate=cls.certificates[2]),
        ]

    def test_certificate_asn_list_view_renders(self):
        self.add_permissions('netbox_rpki.view_certificateasn')

        response = self.client.get(self.plugin_url('certificateasn_list'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, '65401')
        self.assertContains(response, '65402')

    def test_create_certificate_asn_with_valid_input(self):
        self.add_permissions('netbox_rpki.add_certificateasn', 'netbox_rpki.view_certificate', 'ipam.view_asn')

        response = self.client.post(
            self.plugin_url('certificateasn_add'),
            post_data({'asn': self.asns[0], 'certificate_name2': self.certificates[1]}),
        )

        self.assertHttpStatus(response, 302)
        self.assertTrue(CertificateAsn.objects.filter(asn=self.asns[0], certificate_name2=self.certificates[1]).exists())

    def test_create_certificate_asn_with_invalid_input(self):
        self.add_permissions('netbox_rpki.add_certificateasn', 'netbox_rpki.view_certificate', 'ipam.view_asn')

        response = self.client.post(
            self.plugin_url('certificateasn_add'),
            post_data({'certificate_name2': self.certificates[1]}),
        )

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, 'asn', 'This field is required')

    def test_create_certificate_asn_with_empty_input(self):
        self.add_permissions('netbox_rpki.add_certificateasn', 'netbox_rpki.view_certificate', 'ipam.view_asn')

        response = self.client.post(self.plugin_url('certificateasn_add'), post_data({}))

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, 'asn', 'certificate_name2', 'This field is required')

    def test_edit_certificate_asn_with_valid_input(self):
        self.add_permissions('netbox_rpki.change_certificateasn', 'netbox_rpki.view_certificate', 'ipam.view_asn')

        response = self.client.post(
            self.plugin_url('certificateasn_edit', self.certificate_asns[0]),
            post_data({'asn': self.asns[0], 'certificate_name2': self.certificates[2]}),
        )

        self.assertHttpStatus(response, 302)
        self.certificate_asns[0].refresh_from_db()
        self.assertEqual(self.certificate_asns[0].certificate_name2, self.certificates[2])

    def test_delete_certificate_asn(self):
        self.add_permissions('netbox_rpki.delete_certificateasn')

        response = self.client.post(
            self.plugin_url('certificateasn_delete', self.certificate_asns[2]),
            post_data({'confirm': True}),
        )

        self.assertHttpStatus(response, 302)
        self.assertFalse(CertificateAsn.objects.filter(pk=self.certificate_asns[2].pk).exists())