from django.test import RequestFactory, TestCase

from netbox_rpki import tables
from netbox_rpki.object_registry import TABLE_OBJECT_SPECS
from netbox_rpki.object_registry import get_object_spec
from netbox_rpki.tests.registry_scenarios import (
    EXPECTED_TABLE_CLASS_NAMES,
    TABLE_SCENARIOS,
    get_spec_values,
)


class TableRegistrySmokeTestCase(TestCase):
    def test_all_objects_expose_table_specs(self):
        self.assertEqual(
            get_spec_values(TABLE_OBJECT_SPECS, 'table', 'class_name'),
            EXPECTED_TABLE_CLASS_NAMES,
        )


class GeneratedTableRenderingTestCase(TestCase):
    def test_every_orderable_field_does_not_throw_exception(self):
        disallowed = {'actions'}
        fake_request = RequestFactory().get('/')

        for scenario in TABLE_SCENARIOS:
            object_spec = get_object_spec(scenario.object_key)
            scenario.build_rows()
            table_class = getattr(tables, object_spec.table.class_name)
            queryset = object_spec.model.objects.all()
            orderable_columns = [
                name
                for name, column in table_class.base_columns.items()
                if getattr(column, 'orderable', False) and name not in disallowed
            ]

            for column_name in orderable_columns:
                for direction in ('', '-'):
                    with self.subTest(object_key=scenario.object_key, column_name=f'{direction}{column_name}'):
                        table = table_class(queryset)
                        table.order_by = f'{direction}{column_name}'
                        table.as_html(fake_request)