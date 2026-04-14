from django.test import SimpleTestCase, TestCase

from netbox_rpki import forms
from netbox_rpki.object_registry import FILTER_FORM_OBJECT_SPECS, FORM_OBJECT_SPECS
from netbox_rpki.object_registry import get_object_spec
from netbox_rpki.tests.registry_scenarios import (
    EXPECTED_FILTER_FORM_CLASS_NAMES,
    EXPECTED_FORM_CLASS_NAMES,
    FORM_SCENARIOS,
    create_unique_organization,
    get_spec_values,
)


class FormStructureSmokeTestCase(SimpleTestCase):
    def test_all_objects_expose_form_specs(self):
        self.assertEqual(
            get_spec_values(FORM_OBJECT_SPECS, 'form', 'class_name'),
            EXPECTED_FORM_CLASS_NAMES,
        )

    def test_all_objects_expose_filter_form_specs(self):
        self.assertEqual(
            get_spec_values(FILTER_FORM_OBJECT_SPECS, 'filter_form', 'class_name'),
            EXPECTED_FILTER_FORM_CLASS_NAMES,
        )


class FormRegistryBehaviorTestCase(TestCase):
    def test_generated_filter_forms_define_search_tenant_and_tag_fields(self):
        for spec in FILTER_FORM_OBJECT_SPECS:
            form_class = getattr(forms, spec.filter_form.class_name)
            form = form_class()
            with self.subTest(form_class=form_class.__name__):
                self.assertIn('q', form.fields)
                self.assertIn('tenant', form.fields)
                self.assertIn('tag', form.fields)

    def test_generated_forms_accept_minimal_required_fields(self):
        for scenario in FORM_SCENARIOS:
            form_class = getattr(forms, get_object_spec(scenario.object_key).form.class_name)
            form = form_class(data=scenario.build_valid_data())

            with self.subTest(object_key=scenario.object_key):
                self.assertTrue(form.is_valid(), form.errors)

    def test_generated_forms_reject_missing_required_fields(self):
        for scenario in FORM_SCENARIOS:
            form_class = getattr(forms, get_object_spec(scenario.object_key).form.class_name)
            for field_name in scenario.required_fields:
                payload = scenario.build_valid_data()
                payload.pop(field_name, None)
                form = form_class(data=payload)

                with self.subTest(object_key=scenario.object_key, field_name=field_name):
                    self.assertFalse(form.is_valid())
                    self.assertIn(field_name, form.errors)

    def test_generated_forms_reject_empty_payload(self):
        for scenario in FORM_SCENARIOS:
            form_class = getattr(forms, get_object_spec(scenario.object_key).form.class_name)
            form = form_class(data={})

            with self.subTest(object_key=scenario.object_key):
                self.assertFalse(form.is_valid())
                for field_name in scenario.required_fields:
                    self.assertIn(field_name, form.errors)


class CertificateFormBehaviorTestCase(TestCase):
    def test_certificate_form_treats_boolean_fields_as_optional(self):
        organization = create_unique_organization('certificate-boolean-org')
        form_class = getattr(forms, get_object_spec('certificate').form.class_name)

        for missing_field in ('auto_renews', 'self_hosted'):
            payload = {
                'name': 'RPKI Test Certificate',
                'auto_renews': True,
                'self_hosted': False,
                'rpki_org': organization.pk,
            }
            payload.pop(missing_field)
            form = form_class(data=payload)

            with self.subTest(missing_field=missing_field):
                self.assertTrue(form.is_valid(), form.errors)
