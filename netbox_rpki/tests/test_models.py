from django.test import TestCase
from django.urls import reverse

from netbox_rpki.models import Certificate, CertificateAsn, CertificatePrefix, Organization, Roa, RoaPrefix
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_certificate,
    create_test_certificate_asn,
    create_test_certificate_prefix,
    create_test_organization,
    create_test_prefix,
    create_test_roa,
    create_test_roa_prefix,
)


class ModelBehaviorTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization_a = create_test_organization(org_id='org-a', name='Alpha Organization')
        cls.organization_z = create_test_organization(org_id='org-z', name='Zulu Organization')

        cls.certificate_a = create_test_certificate(name='Alpha Certificate', rpki_org=cls.organization_a)
        cls.certificate_z = create_test_certificate(name='Zulu Certificate', rpki_org=cls.organization_z)

        cls.asn_a = create_test_asn(65011)
        cls.asn_z = create_test_asn(65022)

        cls.roa_a = create_test_roa(name='Alpha ROA', origin_as=cls.asn_a, signed_by=cls.certificate_a)
        cls.roa_z = create_test_roa(name='Zulu ROA', origin_as=cls.asn_z, signed_by=cls.certificate_z)

        cls.prefix_a = create_test_prefix('10.0.10.0/24')
        cls.prefix_z = create_test_prefix('10.0.20.0/24')

        cls.roa_prefix_a = create_test_roa_prefix(prefix=cls.prefix_a, roa=cls.roa_a, max_length=24)
        cls.roa_prefix_z = create_test_roa_prefix(prefix=cls.prefix_z, roa=cls.roa_z, max_length=24)

        cls.certificate_prefix_a = create_test_certificate_prefix(prefix=cls.prefix_a, certificate=cls.certificate_a)
        cls.certificate_prefix_z = create_test_certificate_prefix(prefix=cls.prefix_z, certificate=cls.certificate_z)

        cls.certificate_asn_a = create_test_certificate_asn(asn=cls.asn_a, certificate=cls.certificate_a)
        cls.certificate_asn_z = create_test_certificate_asn(asn=cls.asn_z, certificate=cls.certificate_z)

    def test_string_representations(self):
        self.assertEqual(str(self.organization_a), 'Alpha Organization')
        self.assertEqual(str(self.certificate_a), 'Alpha Certificate')
        self.assertEqual(str(self.roa_a), 'Alpha ROA')
        self.assertEqual(str(self.roa_prefix_a), str(self.prefix_a))
        self.assertEqual(str(self.certificate_prefix_a), str(self.prefix_a))
        self.assertEqual(str(self.certificate_asn_a), str(self.asn_a))

    def test_absolute_urls(self):
        self.assertEqual(self.organization_a.get_absolute_url(), reverse('plugins:netbox_rpki:organization', args=[self.organization_a.pk]))
        self.assertEqual(self.certificate_a.get_absolute_url(), reverse('plugins:netbox_rpki:certificate', args=[self.certificate_a.pk]))
        self.assertEqual(self.roa_a.get_absolute_url(), reverse('plugins:netbox_rpki:roa', args=[self.roa_a.pk]))
        self.assertEqual(self.roa_prefix_a.get_absolute_url(), reverse('plugins:netbox_rpki:roaprefix', args=[self.roa_prefix_a.pk]))
        self.assertEqual(self.certificate_prefix_a.get_absolute_url(), reverse('plugins:netbox_rpki:certificateprefix', args=[self.certificate_prefix_a.pk]))
        self.assertEqual(self.certificate_asn_a.get_absolute_url(), reverse('plugins:netbox_rpki:certificateasn', args=[self.certificate_asn_a.pk]))

    def test_name_ordering_for_named_models(self):
        self.assertEqual(list(Organization.objects.values_list('name', flat=True)), ['Alpha Organization', 'Zulu Organization'])
        self.assertEqual(list(Certificate.objects.values_list('name', flat=True)), ['Alpha Certificate', 'Zulu Certificate'])
        self.assertEqual(list(Roa.objects.values_list('name', flat=True)), ['Alpha ROA', 'Zulu ROA'])

    def test_prefix_ordering_for_prefix_models(self):
        self.assertEqual(list(RoaPrefix.objects.values_list('pk', flat=True)), [self.roa_prefix_a.pk, self.roa_prefix_z.pk])
        self.assertEqual(
            list(CertificatePrefix.objects.values_list('pk', flat=True)),
            [self.certificate_prefix_a.pk, self.certificate_prefix_z.pk],
        )

    def test_asn_ordering_for_certificate_asn(self):
        self.assertEqual(
            list(CertificateAsn.objects.values_list('pk', flat=True)),
            [self.certificate_asn_a.pk, self.certificate_asn_z.pk],
        )