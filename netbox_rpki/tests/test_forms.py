from django.test import SimpleTestCase, TestCase

from netbox_rpki import forms
from netbox_rpki import models as rpki_models
from netbox_rpki.object_registry import FILTER_FORM_OBJECT_SPECS, FORM_OBJECT_SPECS
from netbox_rpki.object_registry import get_object_spec
from netbox_rpki.tests.registry_scenarios import (
    EXPECTED_FILTER_FORM_CLASS_NAMES,
    EXPECTED_FORM_CLASS_NAMES,
    FORM_SCENARIOS,
    create_unique_organization,
    get_spec_values,
)
from netbox_rpki.tests.utils import (
    create_test_provider_account,
    create_test_routing_intent_context_group,
    create_test_routing_intent_profile,
    create_test_routing_intent_template,
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

    def test_fieldsets_cover_all_form_fields(self):
        for spec in FORM_OBJECT_SPECS:
            if spec.form.fieldsets is None:
                continue
            fieldset_fields = []
            for fs in spec.form.fieldsets:
                fieldset_fields.extend(fs.fields)
            with self.subTest(form=spec.form.class_name):
                self.assertEqual(
                    sorted(fieldset_fields),
                    sorted(spec.form.fields),
                    f"Fieldset fields do not match form fields for {spec.form.class_name}",
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


class RoutingIntentContextFormBehaviorTestCase(TestCase):
    def test_profile_form_limits_context_groups_to_selected_organization(self):
        form_class = getattr(forms, get_object_spec('routingintentprofile').form.class_name)
        organization = create_unique_organization('profile-context-org')
        other_organization = create_unique_organization('profile-context-other-org')
        matching_group = create_test_routing_intent_context_group(
            name='Matching Group',
            organization=organization,
        )
        create_test_routing_intent_context_group(
            name='Other Group',
            organization=other_organization,
        )

        form = form_class(
            data={
                'name': 'Scoped Profile',
                'organization': organization.pk,
                'status': rpki_models.RoutingIntentProfileStatus.DRAFT,
                'selector_mode': rpki_models.RoutingIntentSelectorMode.FILTERED,
                'default_max_length_policy': rpki_models.DefaultMaxLengthPolicy.EXACT,
                'enabled': True,
                'allow_as0': False,
                'context_groups': [matching_group.pk],
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            set(form.fields['context_groups'].queryset.values_list('pk', flat=True)),
            {matching_group.pk},
        )

    def test_binding_form_rejects_cross_organization_context_groups(self):
        form_class = getattr(forms, get_object_spec('routingintenttemplatebinding').form.class_name)
        organization = create_unique_organization('binding-context-org')
        other_organization = create_unique_organization('binding-context-other-org')
        template = create_test_routing_intent_template(
            name='Scoped Template',
            organization=organization,
        )
        profile = create_test_routing_intent_profile(
            name='Scoped Profile',
            organization=organization,
        )
        invalid_group = create_test_routing_intent_context_group(
            name='Invalid Group',
            organization=other_organization,
        )

        form = form_class(
            data={
                'name': 'Scoped Binding',
                'template': template.pk,
                'intent_profile': profile.pk,
                'enabled': True,
                'binding_priority': 100,
                'binding_label': '',
                'max_length_mode': rpki_models.RoutingIntentRuleMaxLengthMode.INHERIT,
                'prefix_selector_query': '',
                'asn_selector_query': '',
                'state': rpki_models.RoutingIntentTemplateBindingState.PENDING,
                'context_groups': [invalid_group.pk],
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('context_groups', form.errors)

    def test_context_criterion_form_limits_provider_accounts_to_context_group_organization(self):
        form_class = getattr(forms, get_object_spec('routingintentcontextcriterion').form.class_name)
        organization = create_unique_organization('criterion-context-org')
        other_organization = create_unique_organization('criterion-context-other-org')
        context_group = create_test_routing_intent_context_group(
            name='Criterion Group',
            organization=organization,
        )
        matching_account = create_test_provider_account(
            name='Matching Account',
            organization=organization,
            org_handle='ORG-CRITERION-MATCH',
        )
        create_test_provider_account(
            name='Other Account',
            organization=other_organization,
            org_handle='ORG-CRITERION-OTHER',
        )

        form = form_class(initial={'context_group': context_group.pk})

        self.assertEqual(
            set(form.fields['match_provider_account'].queryset.values_list('pk', flat=True)),
            {matching_account.pk},
        )
