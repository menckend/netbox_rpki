from django.test import RequestFactory, SimpleTestCase, TestCase

from netbox_rpki import tables
from netbox_rpki.object_registry import TABLE_OBJECT_SPECS
from netbox_rpki.object_registry import get_object_spec
from netbox_rpki.tests.registry_scenarios import (
    EXPECTED_TABLE_CLASS_NAMES,
    TABLE_SCENARIOS,
    get_spec_values,
)
from netbox_rpki.tests.utils import (
    create_test_provider_snapshot_diff,
    create_test_routing_intent_context_criterion,
    create_test_routing_intent_context_group,
    create_test_routing_intent_profile,
    create_test_routing_intent_template,
    create_test_routing_intent_template_binding,
)


PRIORITY6_EXPECTED_DEFAULT_COLUMNS = {
    'routingintenttemplate': ('name', 'organization', 'status', 'enabled', 'comments', 'tenant', 'tags'),
    'routingintenttemplaterule': ('name', 'template', 'action', 'enabled', 'comments', 'tenant', 'tags'),
    'routingintenttemplatebinding': ('name', 'template', 'intent_profile', 'state', 'enabled', 'comments', 'tenant', 'tags'),
    'routingintentexception': ('name', 'organization', 'exception_type', 'effect_mode', 'enabled', 'comments', 'tenant', 'tags'),
    'bulkintentrun': ('name', 'organization', 'status', 'target_mode', 'started_at', 'comments', 'tenant', 'tags'),
    'bulkintentrunscoperesult': ('name', 'bulk_run', 'intent_profile', 'template_binding', 'status', 'comments', 'tenant', 'tags'),
}


class TableRegistrySmokeTestCase(SimpleTestCase):
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


class Priority6TableContractTestCase(SimpleTestCase):
    def test_priority6_generated_table_fields_and_defaults_remain_stable(self):
        for registry_key, expected_default_columns in PRIORITY6_EXPECTED_DEFAULT_COLUMNS.items():
            object_spec = get_object_spec(registry_key)
            table_class = getattr(tables, object_spec.table.class_name)
            expected_fields = ('pk', 'id') + object_spec.api.fields[2:] + ('comments', 'tenant', 'tags')

            with self.subTest(object_key=registry_key):
                self.assertEqual(object_spec.table.fields, expected_fields)
                self.assertEqual(object_spec.table.default_columns, expected_default_columns)
                self.assertEqual(table_class.Meta.fields, expected_fields)
                self.assertEqual(table_class.Meta.default_columns, expected_default_columns)


class ProviderSnapshotDiffTableTestCase(TestCase):
    def test_churn_value_helpers_read_summary_totals(self):
        snapshot_diff = create_test_provider_snapshot_diff(
            summary_json={
                'totals': {
                    'records_added': 7,
                    'records_removed': 3,
                    'records_changed': 5,
                },
            },
        )
        table = tables.ProviderSnapshotDiffTable(type(snapshot_diff).objects.filter(pk=snapshot_diff.pk))

        self.assertEqual(table.value_records_added(snapshot_diff), 7)
        self.assertEqual(table.value_records_removed(snapshot_diff), 3)
        self.assertEqual(table.value_records_changed(snapshot_diff), 5)
        self.assertIn('records_added', table.columns.columns)
        self.assertIn('records_removed', table.columns.columns)
        self.assertIn('records_changed', table.columns.columns)

    def test_publication_observation_default_columns_include_matured_fields(self):
        publication_table = tables.ImportedPublicationPointTable([])
        certificate_table = tables.ImportedCertificateObservationTable([])

        self.assertIn('last_exchange_result', publication_table.Meta.default_columns)
        self.assertIn('not_after', certificate_table.Meta.default_columns)


class RoutingIntentContextTableTestCase(TestCase):
    def test_profile_and_binding_tables_render_context_group_names(self):
        context_group = create_test_routing_intent_context_group(name='Core Edge')
        profile = create_test_routing_intent_profile(name='Profile With Context', organization=context_group.organization)
        profile.context_groups.add(context_group)
        template = create_test_routing_intent_template(name='Template With Context', organization=context_group.organization)
        binding = create_test_routing_intent_template_binding(
            name='Binding With Context',
            template=template,
            intent_profile=profile,
        )
        binding.context_groups.add(context_group)

        profile_table = tables.RoutingIntentProfileTable(type(profile).objects.filter(pk=profile.pk))
        binding_table = tables.RoutingIntentTemplateBindingTable(type(binding).objects.filter(pk=binding.pk))

        self.assertEqual(profile_table.render_context_group_names(profile), 'Core Edge')
        self.assertEqual(binding_table.render_context_group_names(binding), 'Core Edge')
        self.assertIn('context_group_names', profile_table.columns.columns)
        self.assertIn('context_group_names', binding_table.columns.columns)

    def test_context_group_and_criterion_tables_expose_compact_relationship_columns(self):
        context_group = create_test_routing_intent_context_group(name='Peering')
        profile = create_test_routing_intent_profile(name='Peering Profile', organization=context_group.organization)
        profile.context_groups.add(context_group)
        template = create_test_routing_intent_template(name='Peering Template', organization=context_group.organization)
        binding = create_test_routing_intent_template_binding(
            name='Peering Binding',
            template=template,
            intent_profile=profile,
        )
        binding.context_groups.add(context_group)
        criterion = create_test_routing_intent_context_criterion(
            name='IX Tag',
            context_group=context_group,
            match_value='ix',
        )

        context_group_table = tables.RoutingIntentContextGroupTable(type(context_group).objects.filter(pk=context_group.pk))
        criterion_table = tables.RoutingIntentContextCriterionTable(type(criterion).objects.filter(pk=criterion.pk))

        self.assertEqual(context_group_table.value_criteria_count(context_group), 1)
        self.assertEqual(context_group_table.value_profile_count(context_group), 1)
        self.assertEqual(context_group_table.value_binding_count(context_group), 1)
        self.assertEqual(criterion_table.render_match_target(criterion), 'ix')
        self.assertIn('criteria_count', context_group_table.columns.columns)
        self.assertIn('match_target', criterion_table.columns.columns)
