from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils.formats import date_format

from netbox_rpki import filtersets, forms, tables, views
from netbox_rpki.models import Certificate, CertificateAsn, CertificatePrefix, Organization, Roa, RoaPrefix
from netbox_rpki.object_registry import SIMPLE_DETAIL_VIEW_OBJECT_SPECS, VIEW_OBJECT_SPECS
from netbox_rpki.tests.registry_scenarios import _build_instance_for_spec
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


class ViewRegistrySmokeTestCase(TestCase):
    def test_all_objects_expose_view_specs(self):
        self.assertEqual(
            [spec.view.list_class_name for spec in VIEW_OBJECT_SPECS],
            [spec.view.list_class_name for spec in VIEW_OBJECT_SPECS],
        )

    def test_generated_list_views_use_registered_components(self):
        for spec in VIEW_OBJECT_SPECS:
            list_view = getattr(views, spec.view.list_class_name)

            self.assertEqual(list_view.queryset.model, spec.model)
            self.assertIs(list_view.filterset, getattr(filtersets, spec.filterset.class_name))
            self.assertIs(list_view.filterset_form, getattr(forms, spec.filter_form.class_name))
            self.assertIs(list_view.table, getattr(tables, spec.table.class_name))
            if spec.view.edit_class_name is not None:
                edit_view = getattr(views, spec.view.edit_class_name)
                self.assertEqual(edit_view.queryset.model, spec.model)
                self.assertIs(edit_view.form, getattr(forms, spec.form.class_name))
            if spec.view.delete_class_name is not None:
                delete_view = getattr(views, spec.view.delete_class_name)
                self.assertEqual(delete_view.queryset.model, spec.model)

    def test_simple_detail_views_are_generated_from_specs(self):
        self.assertEqual(
            [spec.view.detail_class_name for spec in SIMPLE_DETAIL_VIEW_OBJECT_SPECS],
            [spec.view.detail_class_name for spec in SIMPLE_DETAIL_VIEW_OBJECT_SPECS],
        )

        for spec in SIMPLE_DETAIL_VIEW_OBJECT_SPECS:
            detail_view = getattr(views, spec.view.detail_class_name)
            self.assertEqual(detail_view.queryset.model, spec.model)


class GeneratedSimpleDetailRenderTestCase(PluginViewTestCase):
    def test_generated_simple_detail_views_render(self):
        for spec in SIMPLE_DETAIL_VIEW_OBJECT_SPECS:
            instance = _build_instance_for_spec(spec, token=f'{spec.key}-detail-view')
            self.add_permissions(f'{spec.model._meta.app_label}.view_{spec.model._meta.model_name}')

            response = self.client.get(instance.get_absolute_url())

            with self.subTest(object_key=spec.key):
                self.assertHttpStatus(response, 200)
                self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')


class GeneratedObjectViewTestMixin:
    view_name = None
    model = None
    list_permissions = ()
    create_permissions = ()
    invalid_create_permissions = None
    empty_create_permissions = None
    edit_permissions = ()
    delete_permissions = ()
    list_expected_text = ()
    filter_query = ''
    filter_expected_text = ()
    filter_unexpected_text = ()
    invalid_form_errors = ()
    empty_form_errors = ()

    def get_valid_create_data(self):
        raise NotImplementedError

    def get_invalid_create_data(self):
        raise NotImplementedError

    def get_edit_instance(self):
        raise NotImplementedError

    def get_valid_edit_data(self):
        raise NotImplementedError

    def get_delete_instance(self):
        raise NotImplementedError

    def assert_valid_create_result(self):
        raise NotImplementedError

    def assert_invalid_create_result(self):
        pass

    def assert_empty_create_result(self):
        pass

    def assert_valid_edit_result(self, instance):
        raise NotImplementedError

    def get_invalid_create_permissions(self):
        if self.invalid_create_permissions is not None:
            return self.invalid_create_permissions
        return self.create_permissions

    def get_empty_create_permissions(self):
        if self.empty_create_permissions is not None:
            return self.empty_create_permissions
        return self.get_invalid_create_permissions()

    def add_test_permissions(self, permissions):
        if permissions:
            self.add_permissions(*permissions)

    def test_list_view_renders(self):
        self.add_test_permissions(self.list_permissions)

        response = self.client.get(self.plugin_url(f'{self.view_name}_list'))

        self.assertHttpStatus(response, 200)
        for text in self.list_expected_text:
            self.assertContains(response, text)

    def test_list_view_filters_by_q(self):
        self.add_test_permissions(self.list_permissions)

        response = self.client.get(
            self.plugin_url(f'{self.view_name}_list'),
            {'q': self.filter_query},
        )

        self.assertHttpStatus(response, 200)
        for text in self.filter_expected_text:
            self.assertContains(response, text)
        for text in self.filter_unexpected_text:
            self.assertNotContains(response, text)

    def test_create_with_valid_input(self):
        self.add_test_permissions(self.create_permissions)

        response = self.client.post(
            self.plugin_url(f'{self.view_name}_add'),
            post_data(self.get_valid_create_data()),
        )

        self.assertHttpStatus(response, 302)
        self.assert_valid_create_result()

    def test_create_with_invalid_input(self):
        self.add_test_permissions(self.get_invalid_create_permissions())

        response = self.client.post(
            self.plugin_url(f'{self.view_name}_add'),
            post_data(self.get_invalid_create_data()),
        )

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, *self.invalid_form_errors)
        self.assert_invalid_create_result()

    def test_create_with_empty_input(self):
        self.add_test_permissions(self.get_empty_create_permissions())

        response = self.client.post(self.plugin_url(f'{self.view_name}_add'), post_data({}))

        self.assertHttpStatus(response, 200)
        self.assertFormErrors(response, *self.empty_form_errors)
        self.assert_empty_create_result()

    def test_edit_with_valid_input(self):
        self.add_test_permissions(self.edit_permissions)
        instance = self.get_edit_instance()

        response = self.client.post(
            self.plugin_url(f'{self.view_name}_edit', instance),
            post_data(self.get_valid_edit_data()),
        )

        self.assertHttpStatus(response, 302)
        self.assert_valid_edit_result(instance)

    def test_delete(self):
        self.add_test_permissions(self.delete_permissions)
        instance = self.get_delete_instance()

        response = self.client.post(
            self.plugin_url(f'{self.view_name}_delete', instance),
            post_data({'confirm': True}),
        )

        self.assertHttpStatus(response, 302)
        self.assertFalse(self.model.objects.filter(pk=instance.pk).exists())


class OrganizationViewTestCase(GeneratedObjectViewTestMixin, PluginViewTestCase):
    view_name = 'organization'
    model = Organization
    list_permissions = ('netbox_rpki.view_organization',)
    create_permissions = ('netbox_rpki.add_organization', 'ipam.view_rir')
    invalid_create_permissions = ('netbox_rpki.add_organization',)
    empty_create_permissions = ('netbox_rpki.add_organization',)
    edit_permissions = ('netbox_rpki.change_organization', 'ipam.view_rir')
    delete_permissions = ('netbox_rpki.delete_organization',)
    list_expected_text = ('View Organization 1', 'View Organization 2')
    filter_query = 'View Organization 2'
    filter_expected_text = ('View Organization 2',)
    filter_unexpected_text = ('View Organization 1',)
    invalid_form_errors = ('org_id', 'This field is required')
    empty_form_errors = ('org_id', 'name', 'This field is required')

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

    def get_valid_create_data(self):
        return {
            'org_id': 'view-org-4',
            'name': 'View Organization 4',
            'ext_url': 'https://example.invalid/view-org-4',
            'parent_rir': self.rir,
        }

    def get_invalid_create_data(self):
        return {'name': 'View Organization Invalid'}

    def get_edit_instance(self):
        return self.organizations[0]

    def get_valid_edit_data(self):
        return {
            'org_id': self.organizations[0].org_id,
            'name': 'View Organization 1 Updated',
            'parent_rir': self.rir,
        }

    def get_delete_instance(self):
        return self.organizations[2]

    def assert_valid_create_result(self):
        self.assertTrue(Organization.objects.filter(org_id='view-org-4', name='View Organization 4').exists())

    def assert_invalid_create_result(self):
        self.assertFalse(Organization.objects.filter(name='View Organization Invalid').exists())

    def assert_valid_edit_result(self, instance):
        instance.refresh_from_db()
        self.assertEqual(instance.name, 'View Organization 1 Updated')

    def test_organization_detail_renders_certificates_table_and_prefill_link(self):
        self.add_permissions('netbox_rpki.view_organization', 'netbox_rpki.change_organization')

        response = self.client.get(self.organizations[0].get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')
        self.assertContains(response, 'Organization Certificate 1')
        self.assertContains(
            response,
            f'{reverse("plugins:netbox_rpki:certificate_add")}?rpki_org={self.organizations[0].pk}',
        )


class CertificateViewTestCase(GeneratedObjectViewTestMixin, PluginViewTestCase):
    view_name = 'certificate'
    model = Certificate
    list_permissions = ('netbox_rpki.view_certificate',)
    create_permissions = ('netbox_rpki.add_certificate', 'netbox_rpki.view_organization')
    invalid_create_permissions = ('netbox_rpki.add_certificate', 'netbox_rpki.view_organization')
    empty_create_permissions = ('netbox_rpki.add_certificate',)
    edit_permissions = ('netbox_rpki.change_certificate', 'netbox_rpki.view_organization')
    delete_permissions = ('netbox_rpki.delete_certificate',)
    list_expected_text = ('View Certificate 1', 'View Certificate 2')
    filter_query = 'View Issuer 2'
    filter_expected_text = ('View Certificate 2',)
    filter_unexpected_text = ('View Certificate 1',)
    invalid_form_errors = ('name', 'This field is required')
    empty_form_errors = ('name', 'rpki_org', 'auto_renews', 'self_hosted')

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

    def get_valid_create_data(self):
        return {
            'name': 'View Certificate 4',
            'issuer': 'View Issuer 4',
            'auto_renews': True,
            'self_hosted': False,
            'rpki_org': self.organizations[0],
        }

    def get_invalid_create_data(self):
        return {
            'issuer': 'Invalid Certificate',
            'auto_renews': True,
            'self_hosted': False,
            'rpki_org': self.organizations[0],
        }

    def get_edit_instance(self):
        return self.certificates[0]

    def get_valid_edit_data(self):
        return {
            'name': self.certificates[0].name,
            'issuer': 'View Issuer 1 Updated',
            'auto_renews': True,
            'self_hosted': False,
            'rpki_org': self.organizations[0],
        }

    def get_delete_instance(self):
        return self.certificates[2]

    def assert_valid_create_result(self):
        self.assertTrue(Certificate.objects.filter(name='View Certificate 4', issuer='View Issuer 4').exists())

    def assert_invalid_create_result(self):
        self.assertFalse(Certificate.objects.filter(issuer='Invalid Certificate').exists())

    def assert_valid_edit_result(self, instance):
        instance.refresh_from_db()
        self.assertEqual(instance.issuer, 'View Issuer 1 Updated')

    def test_certificate_detail_renders_related_tables_and_prefill_links(self):
        self.add_permissions('netbox_rpki.view_certificate', 'netbox_rpki.change_certificate')

        response = self.client.get(self.certificates[0].get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')
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


class RoaViewTestCase(GeneratedObjectViewTestMixin, PluginViewTestCase):
    view_name = 'roa'
    model = Roa
    list_permissions = ('netbox_rpki.view_roa',)
    create_permissions = ('netbox_rpki.add_roa', 'netbox_rpki.view_certificate', 'ipam.view_asn')
    invalid_create_permissions = ('netbox_rpki.add_roa', 'netbox_rpki.view_certificate', 'ipam.view_asn')
    empty_create_permissions = ('netbox_rpki.add_roa', 'netbox_rpki.view_certificate', 'ipam.view_asn')
    edit_permissions = ('netbox_rpki.change_roa', 'netbox_rpki.view_certificate', 'ipam.view_asn')
    delete_permissions = ('netbox_rpki.delete_roa',)
    list_expected_text = ('View ROA 1', 'View ROA 2')
    filter_query = 'View ROA 2'
    filter_expected_text = ('View ROA 2',)
    filter_unexpected_text = ('View ROA 1',)
    invalid_form_errors = ('name', 'This field is required')
    empty_form_errors = ('name', 'signed_by', 'This field is required')

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

    def get_valid_create_data(self):
        return {
            'name': 'View ROA 4',
            'origin_as': self.asns[0],
            'auto_renews': True,
            'signed_by': self.certificates[0],
        }

    def get_invalid_create_data(self):
        return {'auto_renews': True, 'signed_by': self.certificates[0]}

    def get_edit_instance(self):
        return self.roas[0]

    def get_valid_edit_data(self):
        return {
            'name': 'View ROA 1 Updated',
            'origin_as': self.asns[0],
            'auto_renews': True,
            'signed_by': self.certificates[0],
        }

    def get_delete_instance(self):
        return self.roas[2]

    def assert_valid_create_result(self):
        self.assertTrue(Roa.objects.filter(name='View ROA 4').exists())

    def assert_valid_edit_result(self, instance):
        instance.refresh_from_db()
        self.assertEqual(instance.name, 'View ROA 1 Updated')

    def test_roa_detail_renders_prefix_table_and_prefill_link(self):
        self.add_permissions('netbox_rpki.view_roa', 'netbox_rpki.change_roa')

        response = self.client.get(self.roas[0].get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')
        self.assertContains(response, str(self.prefixes[0].prefix))
        self.assertContains(response, date_format(self.roas[0].valid_from))
        self.assertContains(response, date_format(self.roas[0].valid_to))
        self.assertContains(
            response,
            f'{reverse("plugins:netbox_rpki:roaprefix_add")}?roa_name={self.roas[0].pk}',
        )


class RoaPrefixViewTestCase(GeneratedObjectViewTestMixin, PluginViewTestCase):
    view_name = 'roaprefix'
    model = RoaPrefix
    list_permissions = ('netbox_rpki.view_roaprefix',)
    create_permissions = ('netbox_rpki.add_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')
    invalid_create_permissions = ('netbox_rpki.add_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')
    empty_create_permissions = ('netbox_rpki.add_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')
    edit_permissions = ('netbox_rpki.change_roaprefix', 'netbox_rpki.view_roa', 'ipam.view_prefix')
    delete_permissions = ('netbox_rpki.delete_roaprefix',)
    list_expected_text = ('10.50.1.0/24', '10.50.2.0/24')
    filter_query = '10.50.2.0/24'
    filter_expected_text = ('10.50.2.0/24',)
    filter_unexpected_text = ('10.50.1.0/24',)
    invalid_form_errors = ('prefix', 'This field is required')
    empty_form_errors = ('prefix', 'max_length', 'roa_name', 'This field is required')

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

    def get_valid_create_data(self):
        return {'prefix': self.prefixes[0], 'max_length': 27, 'roa_name': self.roas[1]}

    def get_invalid_create_data(self):
        return {'max_length': 27, 'roa_name': self.roas[1]}

    def get_edit_instance(self):
        return self.roa_prefixes[0]

    def get_valid_edit_data(self):
        return {'prefix': self.prefixes[0], 'max_length': 28, 'roa_name': self.roas[0]}

    def get_delete_instance(self):
        return self.roa_prefixes[2]

    def assert_valid_create_result(self):
        self.assertTrue(RoaPrefix.objects.filter(prefix=self.prefixes[0], roa_name=self.roas[1], max_length=27).exists())

    def assert_valid_edit_result(self, instance):
        instance.refresh_from_db()
        self.assertEqual(instance.max_length, 28)


class CertificatePrefixViewTestCase(GeneratedObjectViewTestMixin, PluginViewTestCase):
    view_name = 'certificateprefix'
    model = CertificatePrefix
    list_permissions = ('netbox_rpki.view_certificateprefix',)
    create_permissions = ('netbox_rpki.add_certificateprefix', 'netbox_rpki.view_certificate', 'ipam.view_prefix')
    invalid_create_permissions = ('netbox_rpki.add_certificateprefix', 'netbox_rpki.view_certificate', 'ipam.view_prefix')
    empty_create_permissions = ('netbox_rpki.add_certificateprefix', 'netbox_rpki.view_certificate', 'ipam.view_prefix')
    edit_permissions = ('netbox_rpki.change_certificateprefix', 'netbox_rpki.view_certificate', 'ipam.view_prefix')
    delete_permissions = ('netbox_rpki.delete_certificateprefix',)
    list_expected_text = ('10.60.1.0/24', '10.60.2.0/24')
    filter_query = '10.60.2.0/24'
    filter_expected_text = ('10.60.2.0/24',)
    filter_unexpected_text = ('10.60.1.0/24',)
    invalid_form_errors = ('prefix', 'This field is required')
    empty_form_errors = ('prefix', 'certificate_name', 'This field is required')

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

    def get_valid_create_data(self):
        return {'prefix': self.prefixes[0], 'certificate_name': self.certificates[1]}

    def get_invalid_create_data(self):
        return {'certificate_name': self.certificates[1]}

    def get_edit_instance(self):
        return self.certificate_prefixes[0]

    def get_valid_edit_data(self):
        return {'prefix': self.prefixes[0], 'certificate_name': self.certificates[2]}

    def get_delete_instance(self):
        return self.certificate_prefixes[2]

    def assert_valid_create_result(self):
        self.assertTrue(CertificatePrefix.objects.filter(prefix=self.prefixes[0], certificate_name=self.certificates[1]).exists())

    def assert_valid_edit_result(self, instance):
        instance.refresh_from_db()
        self.assertEqual(instance.certificate_name, self.certificates[2])


class CertificateAsnViewTestCase(GeneratedObjectViewTestMixin, PluginViewTestCase):
    view_name = 'certificateasn'
    model = CertificateAsn
    list_permissions = ('netbox_rpki.view_certificateasn',)
    create_permissions = ('netbox_rpki.add_certificateasn', 'netbox_rpki.view_certificate', 'ipam.view_asn')
    invalid_create_permissions = ('netbox_rpki.add_certificateasn', 'netbox_rpki.view_certificate', 'ipam.view_asn')
    empty_create_permissions = ('netbox_rpki.add_certificateasn', 'netbox_rpki.view_certificate', 'ipam.view_asn')
    edit_permissions = ('netbox_rpki.change_certificateasn', 'netbox_rpki.view_certificate', 'ipam.view_asn')
    delete_permissions = ('netbox_rpki.delete_certificateasn',)
    list_expected_text = ('65401', '65402')
    filter_query = 'Certificate ASN View Parent 2'
    filter_expected_text = ('65402',)
    filter_unexpected_text = ('65401',)
    invalid_form_errors = ('asn', 'This field is required')
    empty_form_errors = ('asn', 'certificate_name2', 'This field is required')

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

    def get_valid_create_data(self):
        return {'asn': self.asns[0], 'certificate_name2': self.certificates[1]}

    def get_invalid_create_data(self):
        return {'certificate_name2': self.certificates[1]}

    def get_edit_instance(self):
        return self.certificate_asns[0]

    def get_valid_edit_data(self):
        return {'asn': self.asns[0], 'certificate_name2': self.certificates[2]}

    def get_delete_instance(self):
        return self.certificate_asns[2]

    def assert_valid_create_result(self):
        self.assertTrue(CertificateAsn.objects.filter(asn=self.asns[0], certificate_name2=self.certificates[1]).exists())

    def assert_valid_edit_result(self, instance):
        instance.refresh_from_db()
        self.assertEqual(instance.certificate_name2, self.certificates[2])
