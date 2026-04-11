from django.test import TestCase

from netbox_rpki.forms import (
    CertificateAsnForm,
    CertificateForm,
    CertificatePrefixForm,
    OrganizationForm,
    RoaForm,
    RoaPrefixForm,
)
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_certificate,
    create_test_organization,
    create_test_prefix,
    create_test_roa,
)


class OrganizationFormTestCase(TestCase):
    def test_organization_form_accepts_minimal_required_fields(self):
        form = OrganizationForm(
            data={
                'org_id': 'rpki-test-org',
                'name': 'RPKI Test Org',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_organization_form_rejects_missing_org_id(self):
        form = OrganizationForm(data={'name': 'RPKI Test Org'})
        self.assertFalse(form.is_valid())
        self.assertIn('org_id', form.errors)

    def test_organization_form_rejects_missing_name(self):
        form = OrganizationForm(data={'org_id': 'rpki-test-org'})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_organization_form_rejects_empty_payload(self):
        form = OrganizationForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('org_id', form.errors)
        self.assertIn('name', form.errors)


class CertificateFormTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='form-org', name='Form Organization')

    def test_certificate_form_accepts_required_fields(self):
        form = CertificateForm(
            data={
                'name': 'RPKI Test Certificate',
                'auto_renews': True,
                'self_hosted': False,
                'rpki_org': self.organization.pk,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_certificate_form_rejects_missing_name(self):
        form = CertificateForm(
            data={
                'auto_renews': True,
                'self_hosted': False,
                'rpki_org': self.organization.pk,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_certificate_form_rejects_missing_rpki_org(self):
        form = CertificateForm(
            data={
                'name': 'RPKI Test Certificate',
                'auto_renews': True,
                'self_hosted': False,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('rpki_org', form.errors)

    def test_certificate_form_rejects_missing_auto_renews(self):
        form = CertificateForm(
            data={
                'name': 'RPKI Test Certificate',
                'self_hosted': False,
                'rpki_org': self.organization.pk,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_certificate_form_rejects_missing_self_hosted(self):
        form = CertificateForm(
            data={
                'name': 'RPKI Test Certificate',
                'auto_renews': True,
                'rpki_org': self.organization.pk,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_certificate_form_rejects_empty_payload(self):
        form = CertificateForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        self.assertIn('rpki_org', form.errors)


class RoaFormTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='roa-form-org', name='ROA Form Organization')
        cls.certificate = create_test_certificate(name='ROA Form Certificate', rpki_org=cls.organization)
        cls.asn = create_test_asn(65100)

    def test_roa_form_accepts_required_fields(self):
        form = RoaForm(
            data={
                'name': 'RPKI Test ROA',
                'origin_as': self.asn.pk,
                'auto_renews': True,
                'signed_by': self.certificate.pk,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_roa_form_rejects_missing_name(self):
        form = RoaForm(
            data={
                'origin_as': self.asn.pk,
                'auto_renews': True,
                'signed_by': self.certificate.pk,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_roa_form_rejects_missing_signed_by(self):
        form = RoaForm(
            data={
                'name': 'RPKI Test ROA',
                'origin_as': self.asn.pk,
                'auto_renews': True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('signed_by', form.errors)

    def test_roa_form_rejects_empty_payload(self):
        form = RoaForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        self.assertIn('signed_by', form.errors)


class RoaPrefixFormTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='roa-prefix-form-org', name='ROA Prefix Form Organization')
        cls.certificate = create_test_certificate(name='ROA Prefix Form Certificate', rpki_org=cls.organization)
        cls.roa = create_test_roa(name='ROA Prefix Form ROA', signed_by=cls.certificate)
        cls.prefix = create_test_prefix('10.200.0.0/24')

    def test_roa_prefix_form_accepts_required_fields(self):
        form = RoaPrefixForm(
            data={
                'prefix': self.prefix.pk,
                'max_length': 24,
                'roa_name': self.roa.pk,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_roa_prefix_form_rejects_missing_prefix(self):
        form = RoaPrefixForm(
            data={
                'max_length': 24,
                'roa_name': self.roa.pk,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('prefix', form.errors)

    def test_roa_prefix_form_rejects_missing_roa_name(self):
        form = RoaPrefixForm(
            data={
                'prefix': self.prefix.pk,
                'max_length': 24,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('roa_name', form.errors)

    def test_roa_prefix_form_rejects_empty_payload(self):
        form = RoaPrefixForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('prefix', form.errors)
        self.assertIn('max_length', form.errors)
        self.assertIn('roa_name', form.errors)


class CertificatePrefixFormTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='certificate-prefix-form-org', name='Certificate Prefix Form Organization')
        cls.certificate = create_test_certificate(name='Certificate Prefix Form Certificate', rpki_org=cls.organization)
        cls.prefix = create_test_prefix('10.210.0.0/24')

    def test_certificate_prefix_form_accepts_required_fields(self):
        form = CertificatePrefixForm(
            data={
                'prefix': self.prefix.pk,
                'certificate_name': self.certificate.pk,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_certificate_prefix_form_rejects_missing_prefix(self):
        form = CertificatePrefixForm(
            data={
                'certificate_name': self.certificate.pk,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('prefix', form.errors)

    def test_certificate_prefix_form_rejects_missing_certificate_name(self):
        form = CertificatePrefixForm(
            data={
                'prefix': self.prefix.pk,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('certificate_name', form.errors)

    def test_certificate_prefix_form_rejects_empty_payload(self):
        form = CertificatePrefixForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('prefix', form.errors)
        self.assertIn('certificate_name', form.errors)


class CertificateAsnFormTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='certificate-asn-form-org', name='Certificate ASN Form Organization')
        cls.certificate = create_test_certificate(name='Certificate ASN Form Certificate', rpki_org=cls.organization)
        cls.asn = create_test_asn(65110)

    def test_certificate_asn_form_accepts_required_fields(self):
        form = CertificateAsnForm(
            data={
                'asn': self.asn.pk,
                'certificate_name2': self.certificate.pk,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_certificate_asn_form_rejects_missing_asn(self):
        form = CertificateAsnForm(
            data={
                'certificate_name2': self.certificate.pk,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('asn', form.errors)

    def test_certificate_asn_form_rejects_missing_certificate_name(self):
        form = CertificateAsnForm(
            data={
                'asn': self.asn.pk,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('certificate_name2', form.errors)

    def test_certificate_asn_form_rejects_empty_payload(self):
        form = CertificateAsnForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('asn', form.errors)
        self.assertIn('certificate_name2', form.errors)
