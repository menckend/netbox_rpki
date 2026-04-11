from django.test import TestCase

from netbox_rpki import filtersets
from netbox_rpki.object_registry import FILTERSET_OBJECT_SPECS
from netbox_rpki.object_registry import get_object_spec
from netbox_rpki.tests.registry_scenarios import (
    EXPECTED_FILTERSET_CLASS_NAMES,
    FILTERSET_SCENARIOS,
    get_spec_values,
)


class FilterSetRegistrySmokeTestCase(TestCase):
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