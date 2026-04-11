from django.test import RequestFactory, TestCase

from netbox_rpki.models import Certificate, CertificateAsn, CertificatePrefix, Organization, Roa, RoaPrefix
from netbox_rpki.tables import (
    CertificateAsnTable,
    CertificatePrefixTable,
    CertificateTable,
    OrganizationTable,
    RoaPrefixTable,
    RoaTable,
)
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


class TableRenderingTestMixin:
    table = None
    queryset = None

    def test_every_orderable_field_does_not_throw_exception(self):
        disallowed = {'actions'}
        orderable_columns = [
            name
            for name, column in self.table.base_columns.items()
            if getattr(column, 'orderable', False) and name not in disallowed
        ]
        fake_request = RequestFactory().get('/')

        for col in orderable_columns:
            for direction in ('', '-'):
                table = self.table(self.queryset)
                table.order_by = f'{direction}{col}'
                table.as_html(fake_request)


class OrganizationTableTestCase(TableRenderingTestMixin, TestCase):
    table = OrganizationTable
    queryset = Organization.objects.all()

    @classmethod
    def setUpTestData(cls):
        create_test_organization(org_id='table-org-a', name='Table Organization A')
        create_test_organization(org_id='table-org-b', name='Table Organization B')


class CertificateTableTestCase(TableRenderingTestMixin, TestCase):
    table = CertificateTable
    queryset = Certificate.objects.all()

    @classmethod
    def setUpTestData(cls):
        organization = create_test_organization(org_id='table-cert-org', name='Table Certificate Org')
        create_test_certificate(name='Table Certificate A', issuer='Issuer A', rpki_org=organization)
        create_test_certificate(name='Table Certificate B', issuer='Issuer B', rpki_org=organization)


class RoaTableTestCase(TableRenderingTestMixin, TestCase):
    table = RoaTable
    queryset = Roa.objects.all()

    @classmethod
    def setUpTestData(cls):
        organization = create_test_organization(org_id='table-roa-org', name='Table ROA Org')
        certificate = create_test_certificate(name='Table ROA Certificate', rpki_org=organization)
        create_test_roa(name='Table ROA A', origin_as=create_test_asn(65401), signed_by=certificate)
        create_test_roa(name='Table ROA B', origin_as=create_test_asn(65402), signed_by=certificate)


class RoaPrefixTableTestCase(TableRenderingTestMixin, TestCase):
    table = RoaPrefixTable
    queryset = RoaPrefix.objects.all()

    @classmethod
    def setUpTestData(cls):
        organization = create_test_organization(org_id='table-roa-prefix-org', name='Table ROA Prefix Org')
        certificate = create_test_certificate(name='Table ROA Prefix Certificate', rpki_org=organization)
        roa = create_test_roa(name='Table ROA Prefix Parent', signed_by=certificate)
        create_test_roa_prefix(prefix=create_test_prefix('10.240.1.0/24'), roa=roa, max_length=24)
        create_test_roa_prefix(prefix=create_test_prefix('10.240.2.0/24'), roa=roa, max_length=25)


class CertificatePrefixTableTestCase(TableRenderingTestMixin, TestCase):
    table = CertificatePrefixTable
    queryset = CertificatePrefix.objects.all()

    @classmethod
    def setUpTestData(cls):
        organization = create_test_organization(org_id='table-certificate-prefix-org', name='Table Certificate Prefix Org')
        certificate = create_test_certificate(name='Table Certificate Prefix Parent', rpki_org=organization)
        create_test_certificate_prefix(prefix=create_test_prefix('10.250.1.0/24'), certificate=certificate)
        create_test_certificate_prefix(prefix=create_test_prefix('10.250.2.0/24'), certificate=certificate)


class CertificateAsnTableTestCase(TableRenderingTestMixin, TestCase):
    table = CertificateAsnTable
    queryset = CertificateAsn.objects.all()

    @classmethod
    def setUpTestData(cls):
        organization = create_test_organization(org_id='table-certificate-asn-org', name='Table Certificate ASN Org')
        certificate = create_test_certificate(name='Table Certificate ASN Parent', rpki_org=organization)
        create_test_certificate_asn(asn=create_test_asn(65501), certificate=certificate)
        create_test_certificate_asn(asn=create_test_asn(65502), certificate=certificate)