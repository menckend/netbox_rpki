from django.test import SimpleTestCase, TestCase

from netbox_rpki import filtersets
from netbox_rpki.object_registry import FILTERSET_OBJECT_SPECS
from netbox_rpki.object_registry import get_object_spec
from netbox_rpki.tests.registry_scenarios import (
    EXPECTED_FILTERSET_CLASS_NAMES,
    FILTERSET_SCENARIOS,
    get_spec_values,
)


PRIORITY6_EXPECTED_FILTERSET_CONTRACT = {
    'routingintenttemplate': {
        'fields': ('name', 'organization', 'status', 'enabled', 'template_version', 'tenant'),
        'search_fields': ('name__icontains', 'description__icontains', 'template_fingerprint__icontains', 'comments__icontains'),
    },
    'routingintenttemplaterule': {
        'fields': (
            'name', 'template', 'action', 'address_family', 'match_tenant', 'match_vrf', 'match_site', 'match_region',
            'origin_asn', 'enabled', 'tenant',
        ),
        'search_fields': ('name__icontains', 'match_role__icontains', 'match_tag__icontains', 'match_custom_field__icontains', 'comments__icontains'),
    },
    'routingintenttemplatebinding': {
        'fields': ('name', 'template', 'intent_profile', 'enabled', 'binding_priority', 'state', 'origin_asn_override', 'tenant'),
        'search_fields': ('name__icontains', 'binding_label__icontains', 'prefix_selector_query__icontains', 'asn_selector_query__icontains', 'comments__icontains'),
    },
    'routingintentexception': {
        'fields': (
            'name', 'organization', 'intent_profile', 'template_binding', 'exception_type', 'effect_mode', 'prefix', 'origin_asn',
            'tenant_scope', 'vrf_scope', 'site_scope', 'region_scope', 'enabled', 'tenant',
        ),
        'search_fields': ('name__icontains', 'prefix_cidr_text__icontains', 'reason__icontains', 'approved_by__icontains', 'comments__icontains'),
    },
    'bulkintentrun': {
        'fields': ('name', 'organization', 'status', 'trigger_mode', 'target_mode', 'tenant'),
        'search_fields': ('name__icontains', 'baseline_fingerprint__icontains', 'resulting_fingerprint__icontains', 'comments__icontains'),
    },
    'bulkintentrunscoperesult': {
        'fields': (
            'name', 'bulk_run', 'intent_profile', 'template_binding', 'status', 'scope_kind', 'derivation_run',
            'reconciliation_run', 'change_plan', 'tenant',
        ),
        'search_fields': ('name__icontains', 'scope_key__icontains', 'scope_kind__icontains', 'comments__icontains'),
    },
}


class FilterSetRegistrySmokeTestCase(SimpleTestCase):
    def test_all_objects_expose_filterset_specs(self):
        self.assertEqual(
            get_spec_values(FILTERSET_OBJECT_SPECS, 'filterset', 'class_name'),
            EXPECTED_FILTERSET_CLASS_NAMES,
        )


class GeneratedFilterSetBehaviorTestCase(TestCase):
    def test_generated_filtersets_apply_expected_queries(self):
        for scenario in FILTERSET_SCENARIOS:
            object_spec = get_object_spec(scenario.object_key)
            filterset_class = getattr(filtersets, object_spec.filterset.class_name)
            queryset = object_spec.model.objects.all()

            for filter_case in scenario.build_filter_cases():
                with self.subTest(object_key=scenario.object_key, filter_case=filter_case.label):
                    self.assertEqual(
                        list(filterset_class(filter_case.params, queryset).qs),
                        list(filter_case.expected_objects),
                    )


class Priority6FilterSetContractTestCase(TestCase):
    def test_priority6_filter_fields_and_search_contract_remain_stable(self):
        for registry_key, expected in PRIORITY6_EXPECTED_FILTERSET_CONTRACT.items():
            object_spec = get_object_spec(registry_key)
            filterset_class = getattr(filtersets, object_spec.filterset.class_name)

            with self.subTest(object_key=registry_key):
                self.assertEqual(object_spec.filterset.fields, expected['fields'])
                self.assertEqual(object_spec.filterset.search_fields, expected['search_fields'])
                self.assertEqual(filterset_class.Meta.fields, expected['fields'])