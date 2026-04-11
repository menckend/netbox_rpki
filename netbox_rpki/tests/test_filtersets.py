from django.test import TestCase

from netbox_rpki.filtersets import (
    CertificateAsnFilterSet,
    CertificateFilterSet,
    CertificatePrefixFilterSet,
    OrganizationFilterSet,
    RoaFilterSet,
    RoaPrefixFilterSet,
)
from netbox_rpki.models import Certificate, CertificateAsn, CertificatePrefix, Organization, Roa, RoaPrefix
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


class OrganizationFilterSetTestCase(TestCase):
    queryset = Organization.objects.all()
    filterset = OrganizationFilterSet

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='Filter RIR', slug='filter-rir')
        cls.organizations = [
            create_test_organization(org_id='alpha-org', name='Alpha Org', ext_url='https://alpha.invalid', comments='alpha comments', parent_rir=cls.rir),
            create_test_organization(org_id='bravo-org', name='Bravo Org', ext_url='https://bravo.invalid'),
        ]

    def test_q(self):
        params = {'q': 'alpha.invalid'}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.organizations[0]])

    def test_parent_rir(self):
        params = {'parent_rir': self.rir.pk}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.organizations[0]])


class CertificateFilterSetTestCase(TestCase):
    queryset = Certificate.objects.all()
    filterset = CertificateFilterSet

    @classmethod
    def setUpTestData(cls):
        cls.organization_a = create_test_organization(org_id='cert-filter-a', name='Certificate Filter A')
        cls.organization_b = create_test_organization(org_id='cert-filter-b', name='Certificate Filter B')
        cls.certificates = [
            create_test_certificate(name='Alpha Certificate', issuer='Alpha Issuer', rpki_org=cls.organization_a, self_hosted=False),
            create_test_certificate(name='Bravo Certificate', issuer='Bravo Issuer', rpki_org=cls.organization_b, self_hosted=True),
        ]

    def test_q(self):
        params = {'q': 'Bravo Issuer'}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.certificates[1]])

    def test_rpki_org(self):
        params = {'rpki_org': self.organization_a.pk}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.certificates[0]])


class RoaFilterSetTestCase(TestCase):
    queryset = Roa.objects.all()
    filterset = RoaFilterSet

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='roa-filter-org', name='ROA Filter Org')
        cls.certificates = [
            create_test_certificate(name='ROA Filter Certificate A', rpki_org=cls.organization),
            create_test_certificate(name='ROA Filter Certificate B', rpki_org=cls.organization),
        ]
        cls.asns = [
            create_test_asn(65201),
            create_test_asn(65202),
        ]
        cls.roas = [
            create_test_roa(name='Alpha ROA', origin_as=cls.asns[0], signed_by=cls.certificates[0], comments='alpha comment'),
            create_test_roa(name='Bravo ROA', origin_as=cls.asns[1], signed_by=cls.certificates[1]),
        ]

    def test_q(self):
        params = {'q': 'alpha comment'}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.roas[0]])

    def test_signed_by(self):
        params = {'signed_by': self.certificates[1].pk}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.roas[1]])


class RoaPrefixFilterSetTestCase(TestCase):
    queryset = RoaPrefix.objects.all()
    filterset = RoaPrefixFilterSet

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='roa-prefix-filter-org', name='ROA Prefix Filter Org')
        cls.certificate = create_test_certificate(name='ROA Prefix Filter Certificate', rpki_org=cls.organization)
        cls.roas = [
            create_test_roa(name='ROA Prefix Parent A', signed_by=cls.certificate),
            create_test_roa(name='ROA Prefix Parent B', signed_by=cls.certificate),
        ]
        cls.prefixes = [
            create_test_prefix('10.220.1.0/24'),
            create_test_prefix('10.220.2.0/24'),
        ]
        cls.roa_prefixes = [
            create_test_roa_prefix(prefix=cls.prefixes[0], roa=cls.roas[0], max_length=24, comments='alpha prefix comment'),
            create_test_roa_prefix(prefix=cls.prefixes[1], roa=cls.roas[1], max_length=25),
        ]

    def test_q(self):
        params = {'q': '10.220.2.0/24'}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.roa_prefixes[1]])

    def test_roa_name(self):
        params = {'roa_name': self.roas[0].pk}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.roa_prefixes[0]])


class CertificatePrefixFilterSetTestCase(TestCase):
    queryset = CertificatePrefix.objects.all()
    filterset = CertificatePrefixFilterSet

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='certificate-prefix-filter-org', name='Certificate Prefix Filter Org')
        cls.certificates = [
            create_test_certificate(name='Certificate Prefix Filter A', rpki_org=cls.organization),
            create_test_certificate(name='Certificate Prefix Filter B', rpki_org=cls.organization),
        ]
        cls.prefixes = [
            create_test_prefix('10.230.1.0/24'),
            create_test_prefix('10.230.2.0/24'),
        ]
        cls.certificate_prefixes = [
            create_test_certificate_prefix(prefix=cls.prefixes[0], certificate=cls.certificates[0], comments='alpha certificate prefix'),
            create_test_certificate_prefix(prefix=cls.prefixes[1], certificate=cls.certificates[1]),
        ]

    def test_q(self):
        params = {'q': '10.230.1.0/24'}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.certificate_prefixes[0]])

    def test_certificate_name(self):
        params = {'certificate_name': self.certificates[1].pk}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.certificate_prefixes[1]])


class CertificateAsnFilterSetTestCase(TestCase):
    queryset = CertificateAsn.objects.all()
    filterset = CertificateAsnFilterSet

    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='certificate-asn-filter-org', name='Certificate ASN Filter Org')
        cls.certificates = [
            create_test_certificate(name='Certificate ASN Filter A', rpki_org=cls.organization),
            create_test_certificate(name='Certificate ASN Filter B', rpki_org=cls.organization),
        ]
        cls.asns = [
            create_test_asn(65311),
            create_test_asn(65312),
        ]
        cls.certificate_asns = [
            create_test_certificate_asn(asn=cls.asns[0], certificate=cls.certificates[0], comments='alpha certificate asn'),
            create_test_certificate_asn(asn=cls.asns[1], certificate=cls.certificates[1]),
        ]

    def test_q(self):
        params = {'q': 'Certificate ASN Filter B'}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.certificate_asns[1]])

    def test_certificate_name2(self):
        params = {'certificate_name2': self.certificates[0].pk}
        self.assertEqual(list(self.filterset(params, self.queryset).qs), [self.certificate_asns[0]])