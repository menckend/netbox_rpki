import csv
import json
from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from netbox_rpki import models as rpki_models
from netbox_rpki import filtersets
from netbox_rpki.api import serializers as api_serializers
from netbox_rpki.api import views as api_views
from netbox_rpki.api.urls import router
from netbox_rpki.api.views import RootView
from netbox_rpki.graphql import filters as graphql_filters
from netbox_rpki.graphql import types as graphql_types
from netbox_rpki.object_registry import API_OBJECT_SPECS, GRAPHQL_OBJECT_SPECS, get_object_spec
from netbox_rpki.services.lifecycle_reporting import (
    LIFECYCLE_EXPORT_SCHEMA_VERSION,
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY,
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE,
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY,
    LIFECYCLE_EXPORT_KIND_PROVIDER_PUBLICATION_DIFF_TIMELINE,
    LIFECYCLE_TIMELINE_SCHEMA_VERSION,
    PUBLICATION_DIFF_TIMELINE_SCHEMA_VERSION,
    build_lifecycle_export_payload,
    build_provider_lifecycle_health_summary,
    build_provider_lifecycle_timeline,
    build_provider_publication_diff_timeline,
    get_lifecycle_export_filename,
    iter_lifecycle_export_rows,
)
from netbox_rpki.services.provider_sync_contract import build_provider_sync_summary
from netbox_rpki.services.rov_simulation import _build_plan_fingerprint
from netbox_rpki.tests.base import PluginAPITestCase
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa,
    create_test_aspa_change_plan,
    create_test_aspa_change_plan_item,
    create_test_aspa_intent,
    create_test_aspa_provider,
    create_test_aspa_reconciliation_run,
    create_test_certificate,
    create_test_certificate_asn,
    create_test_certificate_prefix,
    create_test_certificate_revocation_list,
    create_test_end_entity_certificate,
    create_test_irr_snapshot,
    create_test_irr_source,
    create_test_imported_irr_route_object,
    create_test_imported_certificate_observation,
    create_test_imported_publication_point,
    create_test_imported_signed_object,
    create_test_lifecycle_health_policy,
    create_test_manifest,
    create_test_organization,
    create_test_object_validation_result,
    create_test_prefix,
    create_test_publication_point,
    create_test_provider_account,
    create_test_provider_sync_run,
    create_test_provider_snapshot,
    create_test_provider_snapshot_diff,
    create_test_provider_snapshot_diff_item,
    create_test_provider_write_execution,
    create_test_rir,
    create_test_roa,
    create_test_roa_change_plan,
    create_test_roa_change_plan_item,
    create_test_roa_prefix,
    create_test_roa_reconciliation_run,
    create_test_roa_validation_simulation_result,
    create_test_roa_validation_simulation_run,
    create_test_routing_intent_context_criterion,
    create_test_routing_intent_context_group,
    create_test_routing_intent_profile,
    create_test_routing_intent_exception,
    create_test_routing_intent_template,
    create_test_routing_intent_template_binding,
    create_test_routing_intent_template_rule,
    create_test_router_certificate,
    create_test_signed_object,
    create_test_telemetry_source,
    create_test_telemetry_run,
    create_test_bgp_path_observation,
    create_test_trust_anchor,
    create_test_validated_aspa_payload,
    create_test_validated_roa_payload,
    create_test_validation_run,
    create_test_validator_instance,
)


class ObjectRegistrySmokeTestCase(SimpleTestCase):
    def test_api_object_specs_match_expected_contract(self):
        for spec in API_OBJECT_SPECS:
            with self.subTest(object_key=spec.registry_key):
                self.assertEqual(spec.api.basename, spec.routes.slug)
                self.assertTrue(spec.api.serializer_name.endswith('Serializer'))
                self.assertTrue(spec.api.viewset_name.endswith('ViewSet'))

    def test_registry_uses_structured_surface_specs(self):
        for spec in API_OBJECT_SPECS:
            with self.subTest(object_key=spec.registry_key):
                self.assertEqual(getattr(api_serializers, spec.api.serializer_name).__name__, spec.api.serializer_name)
                self.assertEqual(spec.routes.list_url_name, f'plugins:netbox_rpki:{spec.routes.slug}_list')
                self.assertEqual(spec.routes.add_url_name, f'plugins:netbox_rpki:{spec.routes.slug}_add')

    def test_graphql_object_specs_match_expected_contract(self):
        self.assertEqual(
            [spec.graphql.filter.class_name for spec in GRAPHQL_OBJECT_SPECS],
            [getattr(graphql_filters, spec.graphql.filter.class_name).__name__ for spec in GRAPHQL_OBJECT_SPECS],
        )
        self.assertEqual(
            [spec.graphql.type.class_name for spec in GRAPHQL_OBJECT_SPECS],
            [getattr(graphql_types, spec.graphql.type.class_name).__name__ for spec in GRAPHQL_OBJECT_SPECS],
        )


class Priority6GeneratedWorkflowSurfaceContractTestCase(SimpleTestCase):
    def test_bulk_generated_workflow_records_remain_read_only(self):
        for registry_key in ('bulkintentrun', 'bulkintentrunscoperesult'):
            spec = get_object_spec(registry_key)
            viewset_class = getattr(api_views, spec.api.viewset_name)

            with self.subTest(object_key=registry_key):
                self.assertTrue(spec.api.read_only)
                self.assertFalse(spec.view.supports_create)
                self.assertFalse(spec.view.supports_delete)
                if registry_key == 'bulkintentrun':
                    # bulkintentrun exposes approve/approve_secondary POST actions (Gap G/I)
                    self.assertEqual(set(viewset_class.http_method_names), {'get', 'head', 'options', 'post'})
                else:
                    self.assertEqual(set(viewset_class.http_method_names), {'get', 'head', 'options'})


class GraphQLSmokeTestCase(SimpleTestCase):
    def test_generated_graphql_filters_remain_stable_and_inspectable(self):
        for spec in GRAPHQL_OBJECT_SPECS:
            filter_class = getattr(graphql_filters, spec.graphql.filter.class_name)
            with self.subTest(object_key=spec.registry_key):
                self.assertIs(graphql_filters.GRAPHQL_FILTER_CLASS_MAP[spec.registry_key], filter_class)
                self.assertIs(filter_class.__object_spec__, spec)
                for field in spec.graphql.filter.fields:
                    self.assertIn(field.field_name, filter_class.__annotations__)

    def test_generated_graphql_types_remain_stable_and_inspectable(self):
        for spec in GRAPHQL_OBJECT_SPECS:
            type_class = getattr(graphql_types, spec.graphql.type.class_name)
            with self.subTest(object_key=spec.registry_key):
                self.assertIs(graphql_types.GRAPHQL_TYPE_CLASS_MAP[spec.registry_key], type_class)
                self.assertIs(type_class.__object_spec__, spec)
                self.assertEqual(type_class.__name__, spec.graphql.type.class_name)


class SerializerSmokeTestCase(SimpleTestCase):
    def test_serializer_urls_use_plugin_namespace(self):
        for spec in API_OBJECT_SPECS:
            serializer_class = getattr(api_serializers, spec.api.serializer_name)
            serializer = serializer_class()
            with self.subTest(object_key=spec.registry_key):
                self.assertEqual(serializer.fields["url"].view_name, spec.api.detail_view_name)

    def test_serializer_class_names_remain_stable(self):
        self.assertEqual(
            [getattr(api_serializers, spec.api.serializer_name).__name__ for spec in API_OBJECT_SPECS],
            [spec.api.serializer_name for spec in API_OBJECT_SPECS],
        )


class DelegatedWorkflowSerializerTestCase(TestCase):
    def test_delegated_workflow_serializers_expose_service_backed_summaries(self):
        organization = create_test_organization(
            org_id='delegated-serializer-org',
            name='Delegated Serializer Org',
        )
        provider_account = create_test_provider_account(
            name='Delegated Serializer Provider',
            organization=organization,
            org_handle='ORG-DELEGATED-SERIALIZER',
        )
        entity = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='Delegated Serializer Entity',
            organization=organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.DELEGATED,
        )
        relationship = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='Delegated Serializer Relationship',
            organization=organization,
            delegated_entity=entity,
            provider_account=provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        workflow = rpki_models.DelegatedPublicationWorkflow.objects.create(
            name='Delegated Serializer Workflow',
            organization=organization,
            managed_relationship=relationship,
            child_ca_handle='delegated-child-serializer',
            publication_server_uri='https://publication.example.invalid/serializer/',
            status=rpki_models.DelegatedPublicationWorkflowStatus.ACTIVE,
            requires_approval=True,
        )
        authored_relationship = rpki_models.AuthoredCaRelationship.objects.create(
            name='Delegated Serializer Authored CA Relationship',
            organization=organization,
            provider_account=provider_account,
            delegated_entity=entity,
            managed_relationship=relationship,
            child_ca_handle='delegated-child-serializer',
            relationship_type=rpki_models.AuthoredCaRelationshipType.PARENT,
            status=rpki_models.AuthoredCaRelationshipStatus.ACTIVE,
        )

        entity_data = api_serializers.DelegatedAuthorizationEntitySerializer(entity, context={'request': None}).data
        relationship_data = api_serializers.ManagedAuthorizationRelationshipSerializer(relationship, context={'request': None}).data
        workflow_data = api_serializers.DelegatedPublicationWorkflowSerializer(workflow, context={'request': None}).data
        authored_data = api_serializers.AuthoredCaRelationshipSerializer(authored_relationship, context={'request': None}).data

        self.assertIn('entity_summary', entity_data)
        self.assertEqual(entity_data['entity_summary']['workflow_count'], 1)
        self.assertIn('relationship_summary', relationship_data)
        self.assertEqual(relationship_data['relationship_summary']['workflow_count'], 1)
        self.assertIn('workflow_summary', workflow_data)
        self.assertEqual(workflow_data['workflow_summary']['linkage']['linkage_status'], 'linked')
        self.assertEqual(workflow_data['workflow_summary']['linkage']['explicitly_scoped_authored_ca_relationship_count'], 1)
        self.assertIn('delegated_workflow_summary', authored_data)
        self.assertEqual(authored_data['delegated_workflow_summary']['workflow_count'], 1)
        self.assertEqual(authored_data['delegated_workflow_summary']['ownership_scope'], 'managed_relationship')


class LifecycleHealthSurfaceContractTestCase(SimpleTestCase):
    def test_lifecycle_health_hook_and_event_api_surfaces_are_registered(self):
        hook_spec = get_object_spec('lifecyclehealthhook')
        event_spec = get_object_spec('lifecyclehealthevent')
        hook_viewset = getattr(api_views, hook_spec.api.viewset_name)
        event_viewset = getattr(api_views, event_spec.api.viewset_name)
        hook_serializer = getattr(api_serializers, hook_spec.api.serializer_name)
        event_serializer = getattr(api_serializers, event_spec.api.serializer_name)

        self.assertFalse(hook_spec.api.read_only)
        self.assertIn('post', hook_viewset.http_method_names)
        self.assertIn('patch', hook_viewset.http_method_names)
        self.assertIn('delete', hook_viewset.http_method_names)
        self.assertTrue(event_spec.api.read_only)
        self.assertEqual(set(event_viewset.http_method_names), {'get', 'head', 'options'})
        self.assertIn('target_url', hook_serializer.Meta.fields)
        self.assertIn('headers_json', hook_serializer.Meta.fields)
        self.assertIn('event_kinds_json', hook_serializer.Meta.fields)
        self.assertIn('payload_json', event_serializer.Meta.fields)
        self.assertIn('delivery_error', event_serializer.Meta.fields)
        self.assertIn('related_snapshot', event_serializer.Meta.fields)
        self.assertIn('related_snapshot_diff', event_serializer.Meta.fields)


class RoutingIntentContextSerializerTestCase(TestCase):
    def test_profile_serializer_exposes_context_group_details(self):
        organization = create_test_organization(
            org_id='profile-context-serializer-org',
            name='Profile Context Serializer Org',
        )
        profile = create_test_routing_intent_profile(
            name='Profile Serializer',
            organization=organization,
        )
        context_group = create_test_routing_intent_context_group(
            name='Service Edge',
            organization=organization,
            priority=50,
        )
        profile.context_groups.add(context_group)

        serializer = api_serializers.RoutingIntentProfileSerializer(profile, context={'request': None})

        self.assertEqual(serializer.data['context_group_details'][0]['name'], 'Service Edge')
        self.assertEqual(serializer.data['context_group_details'][0]['priority'], 50)
        self.assertIn('object_url', serializer.data['context_group_details'][0])

    def test_context_group_serializer_exposes_criteria_and_related_consumers(self):
        organization = create_test_organization(
            org_id='group-context-serializer-org',
            name='Group Context Serializer Org',
        )
        profile = create_test_routing_intent_profile(
            name='Consumer Profile',
            organization=organization,
        )
        template = create_test_routing_intent_template(
            name='Consumer Template',
            organization=organization,
        )
        binding = create_test_routing_intent_template_binding(
            name='Consumer Binding',
            template=template,
            intent_profile=profile,
        )
        context_group = create_test_routing_intent_context_group(
            name='Peering Group',
            organization=organization,
        )
        profile.context_groups.add(context_group)
        binding.context_groups.add(context_group)
        create_test_routing_intent_context_criterion(
            name='Exchange Tag',
            context_group=context_group,
            criterion_type=rpki_models.RoutingIntentContextCriterionType.TAG,
            match_value='ix',
        )

        serializer = api_serializers.RoutingIntentContextGroupSerializer(context_group, context={'request': None})

        self.assertEqual(serializer.data['criteria_details'][0]['target'], 'ix')
        self.assertEqual(serializer.data['intent_profile_details'][0]['name'], 'Consumer Profile')
        self.assertEqual(serializer.data['template_binding_details'][0]['name'], 'Consumer Binding')

    def test_binding_serializer_exposes_context_group_details(self):
        organization = create_test_organization(
            org_id='binding-context-serializer-org',
            name='Binding Context Serializer Org',
        )
        profile = create_test_routing_intent_profile(
            name='Binding Profile',
            organization=organization,
        )
        template = create_test_routing_intent_template(
            name='Binding Template',
            organization=organization,
        )
        binding = create_test_routing_intent_template_binding(
            name='Binding Serializer',
            template=template,
            intent_profile=profile,
        )
        context_group = create_test_routing_intent_context_group(
            name='Access Group',
            organization=organization,
            priority=25,
        )
        binding.context_groups.add(context_group)

        serializer = api_serializers.RoutingIntentTemplateBindingSerializer(binding, context={'request': None})

        self.assertEqual(serializer.data['context_group_details'][0]['name'], 'Access Group')
        self.assertEqual(serializer.data['context_group_details'][0]['priority'], 25)


class RpkiProviderAccountSerializerTestCase(TestCase):
    def test_provider_account_serializer_exposes_sync_health_fields(self):
        organization = create_test_organization(org_id='provider-serializer-org', name='Provider Serializer Org')
        provider_account = create_test_provider_account(
            name='Provider Serializer Account',
            organization=organization,
            org_handle='ORG-PROVIDER-SERIALIZER',
            sync_interval=60,
            last_successful_sync=timezone.now() - timedelta(hours=3),
        )

        serializer = api_serializers.RpkiProviderAccountSerializer(provider_account, context={'request': None})

        self.assertEqual(serializer.data['sync_health'], 'stale')
        self.assertEqual(serializer.data['sync_health_display'], 'Stale')
        self.assertIn('next_sync_due_at', serializer.data)

    def test_provider_account_serializer_exposes_lifecycle_health_summary(self):
        organization = create_test_organization(
            org_id='provider-serializer-lifecycle-org',
            name='Provider Serializer Lifecycle Org',
        )
        create_test_lifecycle_health_policy(
            name='Provider Serializer Lifecycle Policy',
            organization=organization,
            sync_stale_after_minutes=45,
        )
        provider_account = create_test_provider_account(
            name='Provider Serializer Lifecycle Account',
            organization=organization,
            org_handle='ORG-PROVIDER-SERIALIZER-LIFECYCLE',
        )

        serializer = api_serializers.RpkiProviderAccountSerializer(provider_account, context={'request': None})

        self.assertEqual(serializer.data['lifecycle_health_summary']['summary_schema_version'], 1)
        self.assertEqual(serializer.data['lifecycle_health_summary']['policy']['source'], 'organization_default')
        self.assertEqual(
            serializer.data['lifecycle_health_summary']['policy']['thresholds']['sync_stale_after_minutes'],
            45,
        )
        self.assertIn('publication_health', serializer.data)

    def test_provider_account_serializer_exposes_arin_rollup_capabilities_and_transport(self):
        organization = create_test_organization(org_id='provider-serializer-arin-org', name='Provider Serializer ARIN Org')
        provider_account = create_test_provider_account(
            name='Provider Serializer ARIN Account',
            organization=organization,
            provider_type=rpki_models.ProviderType.ARIN,
            transport=rpki_models.ProviderSyncTransport.OTE,
            org_handle='ORG-PROVIDER-SERIALIZER-ARIN',
        )
        provider_account.last_sync_summary_json = build_provider_sync_summary(
            provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            family_summaries={},
        )
        provider_account.save(update_fields=['last_sync_summary_json'])

        serializer = api_serializers.RpkiProviderAccountSerializer(provider_account, context={'request': None})

        self.assertEqual(serializer.data['transport'], rpki_models.ProviderSyncTransport.OTE)
        self.assertFalse(serializer.data['supports_roa_write'])
        self.assertEqual(serializer.data['roa_write_mode'], rpki_models.ProviderRoaWriteMode.UNSUPPORTED)
        self.assertFalse(serializer.data['supports_aspa_write'])
        self.assertEqual(serializer.data['aspa_write_mode'], rpki_models.ProviderAspaWriteMode.UNSUPPORTED)
        self.assertEqual(serializer.data['last_sync_rollup']['transport'], rpki_models.ProviderSyncTransport.OTE)
        self.assertEqual(
            serializer.data['last_sync_rollup']['supported_families'],
            [rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS],
        )
        aspa_rollup = next(
            row
            for row in serializer.data['last_sync_rollup']['family_rollups']
            if row['family'] == rpki_models.ProviderSyncFamily.ASPAS
        )
        self.assertEqual(aspa_rollup['status'], rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED)
        self.assertEqual(aspa_rollup['capability_mode'], 'provider_limited')
        self.assertIn('hosted ROA authorizations only', aspa_rollup['capability_reason'])

    def test_validation_serializers_expose_summary_and_detail_fields(self):
        validator = create_test_validator_instance(
            name='Serializer Validator',
            summary_json={'adapter': 'routinator'},
        )
        create_test_validation_run(
            name='Serializer Previous Validation Run',
            validator=validator,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            repository_serial='10',
            completed_at=timezone.now() - timedelta(days=2),
            summary_json={'validated_roa_payload_count': 0},
        )
        validation_run = create_test_validation_run(
            validator=validator,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            repository_serial='11',
            completed_at=timezone.now() - timedelta(hours=1),
            summary_json={'validated_roa_payload_count': 1},
        )
        object_result = create_test_object_validation_result(
            validation_run=validation_run,
            details_json={'match_status_reason': 'exact_uri_match'},
        )
        payload = create_test_validated_roa_payload(
            validation_run=validation_run,
            object_validation_result=object_result,
            observed_prefix='198.51.100.0/24',
            details_json={'ta': 'test-ta'},
        )

        validator_data = api_serializers.ValidatorInstanceSerializer(validator, context={'request': None}).data
        run_data = api_serializers.ValidationRunSerializer(validation_run, context={'request': None}).data
        result_data = api_serializers.ObjectValidationResultSerializer(object_result, context={'request': None}).data
        payload_data = api_serializers.ValidatedRoaPayloadSerializer(payload, context={'request': None}).data

        self.assertEqual(validator_data['summary']['adapter'], 'routinator')
        self.assertEqual(validator_data['run_history_summary']['latest_comparison']['comparison_state'], 'changed')
        self.assertEqual(run_data['summary']['validated_roa_payload_count'], 1)
        self.assertEqual(run_data['comparison_to_previous']['comparison_state'], 'changed')
        self.assertEqual(result_data['details']['match_status_reason'], 'exact_uri_match')
        self.assertEqual(payload_data['details']['ta'], 'test-ta')
        self.assertEqual(payload_data['observed_prefix'], '198.51.100.0/24')

    def test_telemetry_serializers_expose_summary_and_detail_fields(self):
        source = create_test_telemetry_source(
            name='Serializer Telemetry Source',
            summary_json={'adapter': 'imported_mrt'},
        )
        create_test_telemetry_run(
            name='Serializer Previous Telemetry Run',
            source=source,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=timezone.now() - timedelta(hours=3),
            summary_json={'observation_count': 0},
        )
        run = create_test_telemetry_run(
            source=source,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=timezone.now() - timedelta(minutes=30),
            summary_json={'observation_count': 1},
        )
        observation = create_test_bgp_path_observation(
            telemetry_run=run,
            source=source,
            details_json={'collector': 'route-views2'},
        )

        source_data = api_serializers.TelemetrySourceSerializer(source, context={'request': None}).data
        run_data = api_serializers.TelemetryRunSerializer(run, context={'request': None}).data
        observation_data = api_serializers.BgpPathObservationSerializer(observation, context={'request': None}).data

        self.assertEqual(source_data['sync_health'], source.sync_health)
        self.assertEqual(source_data['run_history_summary']['latest_comparison']['comparison_state'], 'changed')
        self.assertEqual(run_data['summary']['observation_count'], 1)
        self.assertEqual(run_data['comparison_to_previous']['comparison_state'], 'changed')
        self.assertEqual(observation_data['details']['collector'], 'route-views2')
        self.assertEqual(observation_data['path_asns_json'], [64496, 64510, 64500])

    def test_workflow_serializers_expose_external_overlay_summaries(self):
        organization = create_test_organization(org_id='workflow-serializer-org', name='Workflow Serializer Org')
        validator = create_test_validator_instance(
            name='Workflow Serializer Validator',
            organization=organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        validation_run = create_test_validation_run(
            name='Workflow Serializer Validation Run',
            validator=validator,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        prefix = create_test_prefix('198.51.100.0/24')
        origin_as = create_test_asn(64512)
        provider_as = create_test_asn(64513)
        roa = create_test_roa(name='Workflow Serializer ROA', origin_as=origin_as)
        create_test_roa_prefix(roa=roa, prefix=prefix, max_length=24)
        create_test_validated_roa_payload(
            name='Workflow Serializer ROA Payload',
            validation_run=validation_run,
            roa=roa,
            prefix=prefix,
            origin_as=origin_as,
            observed_prefix=str(prefix.prefix),
            max_length=24,
        )
        telemetry_source = create_test_telemetry_source(
            name='Workflow Serializer Telemetry Source',
            organization=organization,
            slug='workflow-serializer-telemetry',
        )
        telemetry_run = create_test_telemetry_run(
            name='Workflow Serializer Telemetry Run',
            source=telemetry_source,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        provider_account = create_test_provider_account(
            name='Workflow Serializer Provider Account',
            organization=organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-WORKFLOW-SERIALIZER',
            ca_handle='ca-workflow-serializer',
            api_base_url='https://krill.example.invalid',
        )
        create_test_bgp_path_observation(
            name='Workflow Serializer ROA Observation',
            telemetry_run=telemetry_run,
            source=telemetry_source,
            prefix=prefix,
            observed_prefix=str(prefix.prefix),
            origin_as=origin_as,
            observed_origin_asn=origin_as.asn,
            raw_as_path=f'64496 {origin_as.asn}',
            path_asns_json=[64496, origin_as.asn],
        )
        roa_run = create_test_roa_reconciliation_run(
            name='Workflow Serializer ROA Reconciliation',
            organization=organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        roa_plan = create_test_roa_change_plan(
            name='Workflow Serializer ROA Plan',
            organization=organization,
            source_reconciliation_run=roa_run,
        )
        create_test_roa_change_plan_item(
            name='Workflow Serializer ROA Plan Item',
            change_plan=roa_plan,
            roa=roa,
        )

        aspa = create_test_aspa(
            name='Workflow Serializer ASPA',
            organization=organization,
            customer_as=origin_as,
        )
        create_test_aspa_provider(aspa=aspa, provider_as=provider_as)
        create_test_validated_aspa_payload(
            name='Workflow Serializer ASPA Payload',
            validation_run=validation_run,
            aspa=aspa,
            customer_as=origin_as,
            provider_as=provider_as,
        )
        create_test_bgp_path_observation(
            name='Workflow Serializer ASPA Observation',
            telemetry_run=telemetry_run,
            source=telemetry_source,
            prefix=prefix,
            observed_prefix=str(prefix.prefix),
            origin_as=origin_as,
            observed_origin_asn=origin_as.asn,
            raw_as_path=f'64496 {provider_as.asn} {origin_as.asn}',
            path_asns_json=[64496, provider_as.asn, origin_as.asn],
        )
        aspa_run = create_test_aspa_reconciliation_run(
            name='Workflow Serializer ASPA Reconciliation',
            organization=organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        delegated_entity = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='Workflow Serializer Delegated Entity',
            organization=organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.CUSTOMER,
        )
        managed_relationship = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='Workflow Serializer Managed Relationship',
            organization=organization,
            delegated_entity=delegated_entity,
            provider_account=provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        aspa_plan = create_test_aspa_change_plan(
            name='Workflow Serializer ASPA Plan',
            organization=organization,
            source_reconciliation_run=aspa_run,
            delegated_entity=delegated_entity,
            managed_relationship=managed_relationship,
        )
        create_test_aspa_change_plan_item(
            name='Workflow Serializer ASPA Plan Item',
            change_plan=aspa_plan,
            aspa=aspa,
        )

        roa_run_data = api_serializers.ROAReconciliationRunSerializer(roa_run, context={'request': None}).data
        roa_plan_data = api_serializers.ROAChangePlanSerializer(roa_plan, context={'request': None}).data
        aspa_run_data = api_serializers.ASPAReconciliationRunSerializer(aspa_run, context={'request': None}).data
        aspa_plan_data = api_serializers.ASPAChangePlanSerializer(aspa_plan, context={'request': None}).data

        self.assertIn('external_overlay_summary', roa_run_data)
        self.assertEqual(roa_plan_data['external_overlay_summary']['referenced_object_count'], 1)
        self.assertIn('telemetry_status_counts', aspa_run_data['external_overlay_summary'])
        self.assertEqual(aspa_plan_data['external_overlay_summary']['object_family'], 'aspa')
        self.assertEqual(aspa_plan_data['delegated_entity'], delegated_entity.pk)
        self.assertEqual(aspa_plan_data['managed_relationship'], managed_relationship.pk)


class RpkiProviderAccountSummaryAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-summary-api-org', name='Provider Summary API Org')
        create_test_lifecycle_health_policy(
            name='Provider Summary API Org Default Policy',
            organization=cls.organization,
            sync_stale_after_minutes=90,
        )
        cls.arin_account = create_test_provider_account(
            name='Provider Summary API ARIN',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            transport=rpki_models.ProviderSyncTransport.OTE,
            org_handle='ORG-PROVIDER-SUMMARY-ARIN',
        )
        create_test_lifecycle_health_policy(
            name='Provider Summary API ARIN Override Policy',
            organization=cls.organization,
            provider_account=cls.arin_account,
            sync_stale_after_minutes=15,
        )
        cls.arin_account.last_sync_summary_json = build_provider_sync_summary(
            cls.arin_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            family_summaries={},
        )
        cls.arin_account.save(update_fields=['last_sync_summary_json'])

    def test_provider_account_summary_action_exposes_transport_and_arin_rollup_capabilities(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount')

        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:provideraccount-summary'),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['total_accounts'], 1)
        self.assertEqual(response.data['accounts'][0]['transport'], rpki_models.ProviderSyncTransport.OTE)
        self.assertEqual(response.data['accounts'][0]['supported_families'], [rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS])
        aspa_rollup = next(
            row
            for row in response.data['accounts'][0]['family_rollups']
            if row['family'] == rpki_models.ProviderSyncFamily.ASPAS
        )
        self.assertEqual(aspa_rollup['capability_status'], rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED)
        self.assertEqual(aspa_rollup['capability_mode'], 'provider_limited')
        self.assertIn('hosted ROA authorizations only', aspa_rollup['capability_reason'])


class LifecycleExportAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='lifecycle-export-api-ui-org', name='Lifecycle Export API UI Org')
        cls.provider_account = create_test_provider_account(
            name='Lifecycle Export API UI Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='export-api-ui-ca',
            org_handle='ORG-LIFECYCLE-EXPORT-API-UI',
            last_successful_sync=timezone.now() - timedelta(hours=3),
        )
        cls.base_snapshot = create_test_provider_snapshot(
            name='Lifecycle Export API UI Base Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            fetched_at=timezone.now() - timedelta(days=2),
            completed_at=timezone.now() - timedelta(days=2, minutes=5),
        )
        cls.comparison_snapshot = create_test_provider_snapshot(
            name='Lifecycle Export API UI Comparison Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            fetched_at=timezone.now() - timedelta(days=1),
            completed_at=timezone.now() - timedelta(days=1, minutes=5),
        )
        cls.snapshot_diff = create_test_provider_snapshot_diff(
            name='Lifecycle Export API UI Diff',
            organization=cls.organization,
            provider_account=cls.provider_account,
            base_snapshot=cls.base_snapshot,
            comparison_snapshot=cls.comparison_snapshot,
            summary_json={
                'status': rpki_models.ValidationRunStatus.COMPLETED,
                'totals': {
                    'records_added': 1,
                    'records_removed': 2,
                    'records_changed': 3,
                    'records_stale': 1,
                },
            },
        )
        create_test_provider_snapshot_diff_item(
            snapshot_diff=cls.snapshot_diff,
            object_family=rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
            change_type=rpki_models.ProviderSnapshotDiffChangeType.CHANGED,
            is_stale=True,
        )

    def test_provider_account_export_summary_returns_json_envelope(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount')

        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:provideraccount-export-summary', kwargs={'pk': self.provider_account.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['export_schema_version'], LIFECYCLE_EXPORT_SCHEMA_VERSION)
        self.assertEqual(payload['kind'], LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY)
        self.assertEqual(payload['data']['provider_account_id'], self.provider_account.pk)

    def test_provider_account_export_timeline_csv_has_stable_headers(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
        )

        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:provideraccount-export-timeline', kwargs={'pk': self.provider_account.pk}),
            {'export_format': 'csv'},
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="{get_lifecycle_export_filename(LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE, "csv", provider_account=self.provider_account)}"',
        )
        rows = list(csv.DictReader(response.content.decode().splitlines()))
        self.assertEqual(
            tuple(rows[0].keys()),
            (
                'timeline_schema_version',
                'snapshot_id',
                'snapshot_name',
                'snapshot_status',
                'fetched_at',
                'completed_at',
                'lifecycle_status',
                'publication_status',
                'publication_attention_count',
                'latest_diff_id',
                'latest_diff_name',
                'records_added',
                'records_removed',
                'records_changed',
                'publication_changes',
            ),
        )
        self.assertEqual(rows[0]['snapshot_id'], str(self.comparison_snapshot.pk))
        self.assertEqual(rows[0]['latest_diff_id'], str(self.snapshot_diff.pk))

    def test_provider_account_export_timeline_hides_restricted_ids(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount')

        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:provideraccount-export-timeline', kwargs={'pk': self.provider_account.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['data']['item_count'], 0)
        self.assertEqual(payload['data']['items'], [])

    def test_provider_account_summary_export_returns_collection_envelope(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount')

        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:provideraccount-summary-export'),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['export_schema_version'], LIFECYCLE_EXPORT_SCHEMA_VERSION)
        self.assertEqual(payload['kind'], LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY)
        self.assertEqual(payload['data']['total_accounts'], 1)
        self.assertEqual(payload['data']['accounts'][0]['provider_account_id'], self.provider_account.pk)
        self.assertIsNone(payload['data']['accounts'][0]['latest_snapshot_id'])
        self.assertIsNone(payload['data']['accounts'][0]['latest_diff_id'])

    def test_provider_account_summary_export_csv_has_stable_headers(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount')

        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:provideraccount-summary-export'),
            {'export_format': 'csv'},
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="{get_lifecycle_export_filename(LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY, "csv")}"',
        )
        rows = list(csv.DictReader(response.content.decode().splitlines()))
        self.assertEqual(
            tuple(rows[0].keys()),
            (
                'provider_account_id',
                'provider_account_name',
                'organization_id',
                'organization_name',
                'provider_type',
                'transport',
                'sync_enabled',
                'sync_health',
                'sync_health_display',
                'sync_due',
                'summary_schema_version',
                'summary_status',
                'records_added',
                'records_removed',
                'records_changed',
                'latest_snapshot_id',
                'latest_snapshot_name',
                'latest_diff_id',
                'latest_diff_name',
                'total_attention_count',
            ),
        )


class ViewSetSmokeTestCase(SimpleTestCase):
    def test_viewsets_define_querysets(self):
        for spec in API_OBJECT_SPECS:
            viewset_class = getattr(api_views, spec.api.viewset_name)
            serializer_class = getattr(api_serializers, spec.api.serializer_name)
            filterset_class = getattr(filtersets, spec.filterset.class_name)
            with self.subTest(object_key=spec.registry_key):
                self.assertEqual(viewset_class.queryset.model, spec.model)
                self.assertIs(viewset_class.serializer_class, serializer_class)
                self.assertIs(viewset_class.filterset_class, filterset_class)

    def test_viewsets_expose_expected_http_method_contract(self):
        read_only_post_exceptions = {
            'providersnapshot',
            'roareconciliationrun',
            'aspareconciliationrun',
            'roachangeplan',
            'aspachangeplan',
            'roachangeplanrollbackbundle',
            'aspachangeplanrollbackbundle',
            'roalintfinding',
            'roalintsuppression',
            'bulkintentrun',
        }

        for spec in API_OBJECT_SPECS:
            viewset_class = getattr(api_views, spec.api.viewset_name)
            allowed_methods = set(viewset_class.http_method_names)

            with self.subTest(object_key=spec.registry_key):
                self.assertTrue({'get', 'head', 'options'}.issubset(allowed_methods))
                if spec.api.read_only and spec.registry_key not in read_only_post_exceptions:
                    self.assertEqual(allowed_methods, {'get', 'head', 'options'})
                elif spec.api.read_only:
                    self.assertEqual(allowed_methods, {'get', 'head', 'options', 'post'})
                else:
                    self.assertTrue({'post', 'patch', 'delete'}.issubset(allowed_methods))

    def test_viewsets_expose_expected_custom_actions_only(self):
        for spec in API_OBJECT_SPECS:
            viewset_class = getattr(api_views, spec.api.viewset_name)
            expected_actions = EXTRA_ACTION_NAME_CONTRACTS.get(spec.registry_key, ())

            with self.subTest(object_key=spec.registry_key):
                self.assertEqual(
                    tuple(action.__name__ for action in viewset_class.get_extra_actions()),
                    expected_actions,
                )


class RouterSmokeTestCase(SimpleTestCase):
    def test_root_view_name_remains_stable(self):
        self.assertEqual(RootView().get_view_name(), 'rpki')

    def test_router_registers_expected_viewsets(self):
        self.assertIs(router.APIRootView, RootView)
        self.assertEqual(
            [(prefix, viewset, basename) for prefix, viewset, basename in router.registry],
            [
                (spec.api.basename, getattr(api_views, spec.api.viewset_name), spec.api.basename)
                for spec in API_OBJECT_SPECS
            ],
        )


OBJECT_SPEC_BY_REGISTRY_KEY = {spec.registry_key: spec for spec in API_OBJECT_SPECS}


def _get_custom_action_route_names(contract):
    route_names = contract.get('route_names')
    if route_names is not None:
        return route_names
    return (contract['route_name'],)

EXTRA_ACTION_NAME_CONTRACTS = {
    'delegatedpublicationworkflow': ('approve',),
    'organization': ('create_bulk_intent_run', 'run_aspa_reconciliation'),
    'aspareconciliationrun': ('create_plan', 'summary'),
    'aspachangeplan': ('apply', 'approve', 'approve_secondary', 'preview', 'summary'),
    'aspachangeplanrollbackbundle': ('apply', 'approve'),
    'bulkintentrun': ('approve', 'approve_secondary'),
    'providersnapshot': ('compare', 'summary'),
    'routingintentprofile': ('run',),
    'routingintentexception': ('approve',),
    'routingintenttemplatebinding': ('preview', 'regenerate'),
    'validatorinstance': ('history_summary',),
    'telemetrysource': ('history_summary',),
    'rpkiprovideraccount': (
        'export_summary',
        'export_timeline',
        'publication_diff_summary',
        'summary',
        'summary_export',
        'sync',
        'timeline',
    ),
    'roareconciliationrun': ('create_plan', 'summary'),
    'roalintfinding': ('suppress',),
    'roalintsuppression': ('lift',),
    'roachangeplan': ('acknowledge_findings', 'apply', 'approve', 'approve_secondary', 'preview', 'simulate', 'summary'),
    'roachangeplanrollbackbundle': ('apply', 'approve'),
}

CUSTOM_ACTION_CONTRACTS = {
    'delegatedpublicationworkflow': {
        'actions': ('approve',),
        'route_name': 'plugins-api:netbox_rpki-api:delegatedpublicationworkflow-approve',
        'denied_status': 404,
        'view_permissions': ('netbox_rpki.view_delegatedpublicationworkflow',),
        'allowed_permissions': (
            'netbox_rpki.view_delegatedpublicationworkflow',
            'netbox_rpki.change_delegatedpublicationworkflow',
        ),
        'instance_attr': 'delegated_publication_workflow',
    },
    'organization': {
        'actions': ('run_aspa_reconciliation', 'create_bulk_intent_run'),
        'route_names': (
            'plugins-api:netbox_rpki-api:organization-run-aspa-reconciliation',
            'plugins-api:netbox_rpki-api:organization-create-bulk-intent-run',
        ),
        'denied_status': 404,
        'view_permissions': ('netbox_rpki.view_organization',),
        'allowed_permissions': ('netbox_rpki.view_organization', 'netbox_rpki.change_organization'),
        'instance_attr': 'organization',
    },
    'aspareconciliationrun': {
        'actions': ('create_plan',),
        'route_names': ('plugins-api:netbox_rpki-api:aspareconciliationrun-create-plan',),
        'denied_status': 404,
        'view_permissions': ('netbox_rpki.view_aspareconciliationrun',),
        'allowed_permissions': ('netbox_rpki.view_aspareconciliationrun', 'netbox_rpki.change_aspareconciliationrun'),
        'instance_attr': 'aspa_reconciliation_run',
    },
    'aspachangeplan': {
        'actions': ('apply', 'approve', 'approve_secondary', 'preview'),
        'route_names': (
            'plugins-api:netbox_rpki-api:aspachangeplan-preview',
            'plugins-api:netbox_rpki-api:aspachangeplan-approve',
            'plugins-api:netbox_rpki-api:aspachangeplan-approve-secondary',
            'plugins-api:netbox_rpki-api:aspachangeplan-apply',
        ),
        'denied_status': 404,
        'view_permissions': ('netbox_rpki.view_aspachangeplan',),
        'allowed_permissions': ('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan'),
        'instance_attr': 'aspa_change_plan',
    },
    'routingintentprofile': {
        'actions': ('run',),
        'route_name': 'plugins-api:netbox_rpki-api:routingintentprofile-run',
        'denied_status': 404,
        'view_permissions': ('netbox_rpki.view_routingintentprofile',),
        'allowed_permissions': ('netbox_rpki.view_routingintentprofile', 'netbox_rpki.change_routingintentprofile'),
        'instance_attr': 'routing_intent_profile',
    },
    'routingintentexception': {
        'actions': ('approve',),
        'route_name': 'plugins-api:netbox_rpki-api:routingintentexception-approve',
        'denied_status': 404,
        'view_permissions': ('netbox_rpki.view_routingintentexception',),
        'allowed_permissions': ('netbox_rpki.view_routingintentexception', 'netbox_rpki.change_routingintentexception'),
        'instance_attr': 'routing_intent_exception',
    },
    'routingintenttemplatebinding': {
        'actions': ('preview', 'regenerate'),
        'route_names': (
            'plugins-api:netbox_rpki-api:routingintenttemplatebinding-preview',
            'plugins-api:netbox_rpki-api:routingintenttemplatebinding-regenerate',
        ),
        'denied_status': 404,
        'view_permissions': ('netbox_rpki.view_routingintenttemplatebinding',),
        'allowed_permissions': (
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.change_routingintenttemplatebinding',
        ),
        'instance_attr': 'routing_intent_template_binding',
    },
    'rpkiprovideraccount': {
        'actions': ('sync',),
        'route_name': 'plugins-api:netbox_rpki-api:provideraccount-sync',
        'denied_status': 404,
        'view_permissions': ('netbox_rpki.view_rpkiprovideraccount',),
        'allowed_permissions': ('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.change_rpkiprovideraccount'),
        'instance_attr': 'provider_account',
    },
    'roareconciliationrun': {
        'actions': ('create_plan',),
        'route_names': ('plugins-api:netbox_rpki-api:roareconciliationrun-create-plan',),
        'denied_status': 403,
        'view_permissions': ('netbox_rpki.view_roareconciliationrun',),
        'allowed_permissions': ('netbox_rpki.view_roareconciliationrun', 'netbox_rpki.change_routingintentprofile'),
        'instance_attr': 'reconciliation_run',
    },
    'roachangeplan': {
        'actions': ('acknowledge_findings', 'apply', 'approve', 'approve_secondary', 'preview', 'simulate'),
        'route_names': (
            'plugins-api:netbox_rpki-api:roachangeplan-acknowledge-findings',
            'plugins-api:netbox_rpki-api:roachangeplan-preview',
            'plugins-api:netbox_rpki-api:roachangeplan-approve',
            'plugins-api:netbox_rpki-api:roachangeplan-approve-secondary',
            'plugins-api:netbox_rpki-api:roachangeplan-apply',
            'plugins-api:netbox_rpki-api:roachangeplan-simulate',
        ),
        'denied_status': 404,
        'view_permissions': ('netbox_rpki.view_roachangeplan',),
        'allowed_permissions': ('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan'),
        'instance_attr': 'change_plan',
    },
}


def _resolve_api_test_value(value, test_case):
    return value(test_case) if callable(value) else value


def _assert_response_fields(test_case, data, expected_fields):
    for field_name, expected_value in expected_fields.items():
        test_case.assertEqual(data[field_name], expected_value)


API_TEST_CASES = {
    'organization': {
        'method_singular': 'organization',
        'method_plural': 'organizations',
        'collection_attr': 'organizations',
        'detail_assertions': {'org_id': 'org-1', 'name': 'Organization 1'},
        'list_filter_query': 'Organization 2',
        'list_filter_assertions': {'org_id': 'org-2'},
        'create_valid_payload': lambda self: {
            'org_id': 'org-4',
            'name': 'Organization 4',
            'ext_url': 'https://example.invalid/org-4',
            'parent_rir': self.rir.pk,
        },
        'create_success_lookup': {'org_id': 'org-4', 'name': 'Organization 4'},
        'create_invalid_payload': {
            'org_id': 'org-invalid',
            'name': 'Organization Invalid',
            'parent_rir': 999999,
        },
        'create_invalid_fields': ('parent_rir',),
        'create_empty_fields': ('org_id', 'name'),
        'update_payload': {'name': 'Organization 1 Updated'},
        'assert_updated': lambda self, instance: self.assertEqual(instance.name, 'Organization 1 Updated'),
    },
    'certificate': {
        'method_singular': 'certificate',
        'method_plural': 'certificates',
        'collection_attr': 'certificates',
        'related_permissions': ('netbox_rpki.view_organization',),
        'detail_assertions': {'name': 'Certificate 1', 'issuer': 'Issuer 1'},
        'list_filter_query': 'Issuer 2',
        'list_filter_assertions': {'name': 'Certificate 2'},
        'create_valid_payload': lambda self: {
            'name': 'Certificate 4',
            'issuer': 'Issuer 4',
            'auto_renews': True,
            'self_hosted': False,
            'rpki_org': self.organizations[0].pk,
        },
        'create_success_lookup': {'name': 'Certificate 4', 'issuer': 'Issuer 4'},
        'create_invalid_payload': {
            'name': 'Certificate Invalid',
            'auto_renews': True,
            'self_hosted': False,
            'rpki_org': 999999,
        },
        'create_invalid_fields': ('rpki_org',),
        'create_empty_fields': ('name', 'auto_renews', 'self_hosted', 'rpki_org'),
        'update_payload': {'issuer': 'Issuer 1 Updated'},
        'assert_updated': lambda self, instance: self.assertEqual(instance.issuer, 'Issuer 1 Updated'),
    },
    'roaobject': {
        'method_singular': 'roa_object',
        'method_plural': 'roa_objects',
        'collection_attr': 'roas',
        'related_permissions': ('netbox_rpki.view_organization', 'ipam.view_asn'),
        'detail_assertions': {'name': 'ROA 1'},
        'list_filter_query': 'ROA 2',
        'list_filter_assertions': {'name': 'ROA 2'},
        'create_valid_payload': lambda self: {
            'name': 'ROA 4',
            'organization': self.organizations[0].pk,
            'origin_as': self.asns[0].pk,
            'validation_state': rpki_models.ValidationState.UNKNOWN,
        },
        'create_success_lookup': {'name': 'ROA 4'},
        'create_invalid_payload': {'name': 'ROA Invalid', 'organization': 999999},
        'create_invalid_fields': ('organization',),
        'create_empty_fields': ('name',),
        'update_payload': {'name': 'ROA 1 Updated'},
        'assert_updated': lambda self, instance: self.assertEqual(instance.name, 'ROA 1 Updated'),
    },
    'roaobjectprefix': {
        'method_singular': 'roa_object_prefix',
        'method_plural': 'roa_object_prefixes',
        'collection_attr': 'roa_prefixes',
        'related_permissions': ('netbox_rpki.view_roaobject', 'ipam.view_prefix'),
        'detail_assertions': {'max_length': 24},
        'list_filter_query': '10.20.2.0/24',
        'list_filter_assertions': {'max_length': 25},
        'create_valid_payload': lambda self: {
            'roa_object': self.roas[1].pk,
            'prefix': self.prefixes[0].pk,
            'prefix_cidr_text': str(self.prefixes[0].prefix),
            'max_length': 27,
        },
        'create_success_lookup': lambda self: {
            'prefix': self.prefixes[0],
            'roa_object': self.roas[1],
            'max_length': 27,
        },
        'create_invalid_payload': lambda self: {'prefix': 999999, 'max_length': 27, 'roa_object': self.roas[1].pk},
        'create_invalid_fields': ('prefix',),
        'create_empty_fields': ('max_length', 'roa_object'),
        'update_payload': {'max_length': 28},
        'assert_updated': lambda self, instance: self.assertEqual(instance.max_length, 28),
    },
    'certificateprefix': {
        'method_singular': 'certificate_prefix',
        'method_plural': 'certificate_prefixes',
        'collection_attr': 'certificate_prefixes',
        'related_permissions': ('netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_prefix'),
        'detail_assertions': lambda self: {'prefix': self.prefixes[0].pk},
        'list_filter_query': '10.30.2.0/24',
        'create_valid_payload': lambda self: {
            'prefix': self.prefixes[0].pk,
            'certificate_name': self.certificates[1].pk,
        },
        'create_success_lookup': lambda self: {'prefix': self.prefixes[0], 'certificate_name': self.certificates[1]},
        'create_invalid_payload': lambda self: {'prefix': self.prefixes[0].pk, 'certificate_name': 999999},
        'create_invalid_fields': ('certificate_name',),
        'create_empty_fields': ('prefix', 'certificate_name'),
        'update_payload': lambda self: {'certificate_name': self.certificates[2].pk},
        'assert_updated': lambda self, instance: self.assertEqual(instance.certificate_name, self.certificates[2]),
    },
    'certificateasn': {
        'method_singular': 'certificate_asn',
        'method_plural': 'certificate_asns',
        'collection_attr': 'certificate_asns',
        'related_permissions': ('netbox_rpki.view_certificate', 'netbox_rpki.view_organization', 'ipam.view_asn'),
        'detail_assertions': lambda self: {'asn': self.asns[0].pk},
        'list_filter_query': 'Certificate ASN Parent 2',
        'create_valid_payload': lambda self: {
            'asn': self.asns[0].pk,
            'certificate_name2': self.certificates[1].pk,
        },
        'create_success_lookup': lambda self: {'asn': self.asns[0], 'certificate_name2': self.certificates[1]},
        'create_invalid_payload': lambda self: {'asn': 999999, 'certificate_name2': self.certificates[1].pk},
        'create_invalid_fields': ('asn',),
        'create_empty_fields': ('asn', 'certificate_name2'),
        'update_payload': lambda self: {'certificate_name2': self.certificates[2].pk},
        'assert_updated': lambda self, instance: self.assertEqual(instance.certificate_name2, self.certificates[2]),
    },
}


def _install_registry_api_tests(cls):
    cls.model = OBJECT_SPEC_BY_REGISTRY_KEY[cls.object_spec_key].model
    case = API_TEST_CASES[cls.object_spec_key]
    test_names = {
        f"test_get_{case['method_singular']}": '_run_get_object_test',
        f"test_list_{case['method_plural']}": '_run_list_objects_test',
        f"test_list_{case['method_plural']}_filters_by_q": '_run_list_filter_test',
        f"test_create_{case['method_singular']}_with_valid_input": '_run_create_valid_test',
        f"test_create_{case['method_singular']}_with_invalid_input": '_run_create_invalid_test',
        f"test_create_{case['method_singular']}_with_empty_input": '_run_create_empty_test',
        f"test_update_{case['method_singular']}_with_valid_input": '_run_update_test',
        f"test_delete_{case['method_singular']}": '_run_delete_test',
    }

    for test_name, runner_name in test_names.items():
        def test_method(self, runner_name=runner_name):
            getattr(self, runner_name)()

        test_method.__name__ = test_name
        setattr(cls, test_name, test_method)

    return cls


class RegistryDrivenObjectAPITestCase(PluginAPITestCase):
    object_spec_key = None

    @property
    def api_case(self):
        return API_TEST_CASES[self.object_spec_key]

    @property
    def object_spec(self):
        return OBJECT_SPEC_BY_REGISTRY_KEY[self.object_spec_key]

    def _get_case_value(self, key):
        return _resolve_api_test_value(self.api_case[key], self)

    def _get_case_instance(self, index_key, default_index):
        collection = getattr(self, self.api_case['collection_attr'])
        return collection[self.api_case.get(index_key, default_index)]

    def _action_permissions(self, action):
        return (
            f'netbox_rpki.{action}_{self.object_spec.api.basename}',
            *self.api_case.get('related_permissions', ()),
        )

    def _run_get_object_test(self):
        self.add_permissions(*self._action_permissions('view'))

        response = self.client.get(self._get_detail_url(self._get_case_instance('detail_index', 0)), **self.header)

        self.assertHttpStatus(response, 200)
        _assert_response_fields(self, response.data, self._get_case_value('detail_assertions'))

    def _run_list_objects_test(self):
        self.add_permissions(*self._action_permissions('view'))

        response = self.client.get(self._get_list_url(), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), self.api_case.get('list_expected_count', 3))

    def _run_list_filter_test(self):
        self.add_permissions(*self._action_permissions('view'))

        response = self.client.get(f"{self._get_list_url()}?q={self.api_case['list_filter_query']}", **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), self.api_case.get('list_filter_expected_count', 1))
        expected_fields = self.api_case.get('list_filter_assertions')
        if expected_fields is not None:
            _assert_response_fields(self, response.data['results'][0], _resolve_api_test_value(expected_fields, self))

    def _run_create_valid_test(self):
        self.add_permissions(*self._action_permissions('add'))

        response = self.client.post(
            self._get_list_url(),
            self._get_case_value('create_valid_payload'),
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 201)
        self.assertTrue(self.model.objects.filter(**self._get_case_value('create_success_lookup')).exists())

    def _run_create_invalid_test(self):
        self.add_permissions(*self._action_permissions('add'))

        response = self.client.post(
            self._get_list_url(),
            self._get_case_value('create_invalid_payload'),
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        for field_name in self.api_case['create_invalid_fields']:
            self.assertIn(field_name, response.data)

    def _run_create_empty_test(self):
        self.add_permissions(*self._action_permissions('add'))

        response = self.client.post(self._get_list_url(), {}, format='json', **self.header)

        self.assertHttpStatus(response, 400)
        for field_name in self.api_case['create_empty_fields']:
            self.assertIn(field_name, response.data)

    def _run_update_test(self):
        self.add_permissions(*self._action_permissions('change'))
        instance = self._get_case_instance('update_index', 0)

        response = self.client.patch(
            self._get_detail_url(instance),
            self._get_case_value('update_payload'),
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        instance.refresh_from_db()
        self.api_case['assert_updated'](self, instance)

    def _run_delete_test(self):
        self.add_permissions(*self._action_permissions('delete'))
        instance = self._get_case_instance('delete_index', 2)

        response = self.client.delete(self._get_detail_url(instance), **self.header)

        self.assertHttpStatus(response, 204)
        self.assertFalse(self.model.objects.filter(pk=instance.pk).exists())


class CustomActionSurfaceContractTestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='custom-action-org', name='Custom Action Org')
        cls.routing_intent_profile = create_test_routing_intent_profile(
            name='Custom Action Profile',
            organization=cls.organization,
        )
        cls.routing_intent_template = create_test_routing_intent_template(
            name='Custom Action Template',
            organization=cls.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Custom Action Template Rule',
            template=cls.routing_intent_template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        cls.routing_intent_template_binding = create_test_routing_intent_template_binding(
            name='Custom Action Binding',
            template=cls.routing_intent_template,
            intent_profile=cls.routing_intent_profile,
        )
        cls.routing_intent_exception = create_test_routing_intent_exception(
            name='Custom Action Exception',
            organization=cls.organization,
            intent_profile=cls.routing_intent_profile,
            template_binding=cls.routing_intent_template_binding,
        )
        cls.provider_account = create_test_provider_account(
            name='Custom Action Provider',
            organization=cls.organization,
            org_handle='ORG-CUSTOM-ACTION',
        )
        cls.delegated_entity = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='Custom Action Delegated Entity',
            organization=cls.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.DOWNSTREAM,
        )
        cls.managed_authorization_relationship = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='Custom Action Managed Relationship',
            organization=cls.organization,
            delegated_entity=cls.delegated_entity,
            provider_account=cls.provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        cls.delegated_publication_workflow = rpki_models.DelegatedPublicationWorkflow.objects.create(
            name='Custom Action Delegated Workflow',
            organization=cls.organization,
            managed_relationship=cls.managed_authorization_relationship,
            child_ca_handle='delegated-child-ca',
            publication_server_uri='https://publication.example.invalid/upstream/',
            status=rpki_models.DelegatedPublicationWorkflowStatus.ACTIVE,
            requires_approval=True,
        )
        cls.reconciliation_run = create_test_roa_reconciliation_run(
            name='Custom Action Reconciliation',
            organization=cls.organization,
            intent_profile=cls.routing_intent_profile,
        )
        cls.aspa_reconciliation_run = create_test_aspa_reconciliation_run(
            name='Custom ASPA Action Reconciliation',
            organization=cls.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.change_plan = create_test_roa_change_plan(
            name='Custom Action Change Plan',
            organization=cls.organization,
            source_reconciliation_run=cls.reconciliation_run,
        )
        cls.aspa_change_plan = create_test_aspa_change_plan(
            name='Custom ASPA Action Change Plan',
            organization=cls.organization,
            source_reconciliation_run=cls.aspa_reconciliation_run,
        )

    def test_custom_action_routes_reverse(self):
        for registry_key, contract in CUSTOM_ACTION_CONTRACTS.items():
            instance = getattr(self, contract['instance_attr'])

            with self.subTest(object_key=registry_key):
                for route_name in _get_custom_action_route_names(contract):
                    self.assertTrue(reverse(route_name, kwargs={'pk': instance.pk}))

    def test_custom_actions_reject_get_requests(self):
        for registry_key, contract in CUSTOM_ACTION_CONTRACTS.items():
            self.add_permissions(*contract['allowed_permissions'])
            instance = getattr(self, contract['instance_attr'])


            for route_name in _get_custom_action_route_names(contract):
                response = self.client.get(reverse(route_name, kwargs={'pk': instance.pk}), **self.header)

                with self.subTest(object_key=registry_key, route_name=route_name):
                    self.assertHttpStatus(response, 405)

    def test_custom_actions_require_elevated_permissions(self):
        for registry_key, contract in CUSTOM_ACTION_CONTRACTS.items():
            self.add_permissions(*contract['view_permissions'])
            instance = getattr(self, contract['instance_attr'])


            for route_name in _get_custom_action_route_names(contract):
                response = self.client.post(
                    reverse(route_name, kwargs={'pk': instance.pk}),
                    {},
                    format='json',
                    **self.header,
                )

                with self.subTest(object_key=registry_key, route_name=route_name):
                    self.assertHttpStatus(response, contract['denied_status'])


class OrganizationAspaReconciliationActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='org-aspa-action', name='Organization ASPA Action')
        cls.provider_account = create_test_provider_account(
            name='Organization ASPA Provider',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-ASPA-ACTION',
            ca_handle='org-aspa-action',
        )

    def test_run_aspa_reconciliation_action_enqueues_job(self):
        self.add_permissions('netbox_rpki.view_organization', 'netbox_rpki.change_organization')
        url = reverse('plugins-api:netbox_rpki-api:organization-run-aspa-reconciliation', kwargs={'pk': self.organization.pk})

        class StubJob:
            pk = 880
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/880/'

        with patch(
            'netbox_rpki.api.views.RunAspaReconciliationJob.enqueue_for_organization',
            return_value=(StubJob(), True),
        ) as enqueue_mock:
            response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['job']['id'], 880)
        self.assertFalse(response.data['reconciliation_in_progress'])
        enqueue_mock.assert_called_once_with(
            self.organization,
            comparison_scope='local_aspa_records',
            provider_snapshot=None,
            user=self.user,
        )

    def test_run_aspa_reconciliation_action_accepts_provider_snapshot(self):
        self.add_permissions('netbox_rpki.view_organization', 'netbox_rpki.change_organization')
        snapshot = create_test_provider_snapshot(
            name='Organization ASPA Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            status='completed',
        )
        url = reverse('plugins-api:netbox_rpki-api:organization-run-aspa-reconciliation', kwargs={'pk': self.organization.pk})

        class StubJob:
            pk = 881
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/881/'

        with patch(
            'netbox_rpki.api.views.RunAspaReconciliationJob.enqueue_for_organization',
            return_value=(StubJob(), True),
        ) as enqueue_mock:
            response = self.client.post(
                url,
                {
                    'comparison_scope': 'provider_imported',
                    'provider_snapshot': snapshot.pk,
                },
                format='json',
                **self.header,
            )

        self.assertHttpStatus(response, 200)
        enqueue_mock.assert_called_once_with(
            self.organization,
            comparison_scope='provider_imported',
            provider_snapshot=snapshot,
            user=self.user,
        )


class OrganizationBulkIntentRunActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='org-bulk-action', name='Organization Bulk Action')
        cls.prefix = create_test_prefix('10.87.0.0/24', status='active')
        cls.origin_asn = create_test_asn(65587)
        cls.profile = create_test_routing_intent_profile(
            name='Bulk Action Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.prefix.pk}',
            asn_selector_query=f'id={cls.origin_asn.pk}',
        )
        cls.template = create_test_routing_intent_template(
            name='Bulk Action Template',
            organization=cls.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Bulk Action Include',
            template=cls.template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        cls.binding = create_test_routing_intent_template_binding(
            name='Bulk Action Binding',
            template=cls.template,
            intent_profile=cls.profile,
            origin_asn_override=cls.origin_asn,
            prefix_selector_query=f'id={cls.prefix.pk}',
        )
        cls.provider_account = create_test_provider_account(
            name='Organization Bulk Provider',
            organization=cls.organization,
            org_handle='ORG-BULK-ACTION',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Organization Bulk Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

    def test_create_bulk_intent_run_action_returns_bulk_run_summary(self):
        self.add_permissions(
            'netbox_rpki.view_organization',
            'netbox_rpki.change_organization',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:organization-create-bulk-intent-run',
            kwargs={'pk': self.organization.pk},
        )

        class StubJob:
            pk = 882
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/882/'

        with patch(
            'netbox_rpki.api.views.RunBulkRoutingIntentJob.enqueue_for_organization',
            return_value=(StubJob(), True),
        ) as enqueue_mock:
            response = self.client.post(
                url,
                {
                    'run_name': 'API Bulk Run',
                    'profiles': [self.profile.pk],
                    'bindings': [self.binding.pk],
                    'create_change_plans': False,
                },
                format='json',
                **self.header,
            )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['job']['id'], 882)
        self.assertFalse(response.data['bulk_run_in_progress'])
        self.assertEqual(response.data['profile_pks'], [self.profile.pk])
        self.assertEqual(response.data['binding_pks'], [self.binding.pk])
        enqueue_mock.assert_called_once_with(
            organization=self.organization,
            profiles=(self.profile,),
            bindings=(self.binding,),
            comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
            provider_snapshot=None,
            create_change_plans=False,
            run_name='API Bulk Run',
            user=self.user,
        )

    def test_create_bulk_intent_run_action_accepts_provider_snapshot(self):
        self.add_permissions(
            'netbox_rpki.view_organization',
            'netbox_rpki.change_organization',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:organization-create-bulk-intent-run',
            kwargs={'pk': self.organization.pk},
        )

        class StubJob:
            pk = 883
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/883/'

        with patch(
            'netbox_rpki.api.views.RunBulkRoutingIntentJob.enqueue_for_organization',
            return_value=(StubJob(), True),
        ) as enqueue_mock:
            response = self.client.post(
                url,
                {
                    'comparison_scope': rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
                    'provider_snapshot': self.provider_snapshot.pk,
                    'bindings': [self.binding.pk],
                },
                format='json',
                **self.header,
            )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['job']['id'], 883)
        self.assertEqual(response.data['provider_snapshot'], self.provider_snapshot.pk)
        enqueue_mock.assert_called_once_with(
            organization=self.organization,
            profiles=(),
            bindings=(self.binding,),
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
            create_change_plans=False,
            run_name=None,
            user=self.user,
        )

    def test_create_bulk_intent_run_action_response_contract_is_stable(self):
        self.add_permissions(
            'netbox_rpki.view_organization',
            'netbox_rpki.change_organization',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:organization-create-bulk-intent-run',
            kwargs={'pk': self.organization.pk},
        )

        class StubJob:
            pk = 884
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/884/'

        with patch(
            'netbox_rpki.api.views.RunBulkRoutingIntentJob.enqueue_for_organization',
            return_value=(StubJob(), True),
        ):
            response = self.client.post(
                url,
                {
                    'run_name': 'Stable Contract Run',
                    'profiles': [self.profile.pk],
                    'bindings': [self.binding.pk],
                    'create_change_plans': True,
                },
                format='json',
                **self.header,
            )

        self.assertHttpStatus(response, 200)
        self.assertEqual(
            set(response.data),
            {
                'comparison_scope',
                'provider_snapshot',
                'create_change_plans',
                'profile_pks',
                'binding_pks',
                'job',
                'bulk_run_in_progress',
            },
        )
        self.assertEqual(
            set(response.data['job']),
            {'id', 'status', 'url', 'existing'},
        )


class RoutingIntentProfileActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='profile-action-org', name='Profile Action Org')
        cls.profile = create_test_routing_intent_profile(
            name='Profile Action Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        )
        cls.provider_account = create_test_provider_account(
            name='Profile Action Provider',
            organization=cls.organization,
            org_handle='ORG-PROFILE-ACTION',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Profile Action Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

    def test_run_action_enqueues_job(self):
        self.add_permissions(
            'netbox_rpki.view_routingintentprofile',
            'netbox_rpki.change_routingintentprofile',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:routingintentprofile-run',
            kwargs={'pk': self.profile.pk},
        )

        class StubJob:
            pk = 884
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/884/'

        with patch('netbox_rpki.api.views.RunRoutingIntentProfileJob.enqueue', return_value=StubJob()) as enqueue_mock:
            response = self.client.post(
                url,
                {
                    'comparison_scope': rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
                    'provider_snapshot': self.provider_snapshot.pk,
                },
                format='json',
                **self.header,
            )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['job']['id'], 884)
        enqueue_mock.assert_called_once_with(
            instance=self.profile,
            user=self.user,
            profile_pk=self.profile.pk,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot_pk=self.provider_snapshot.pk,
        )


class RoutingIntentExceptionActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='exception-action-org', name='Exception Action Org')
        cls.profile = create_test_routing_intent_profile(
            name='Exception Action Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        )
        cls.exception = create_test_routing_intent_exception(
            name='Exception Action Exception',
            organization=cls.organization,
            intent_profile=cls.profile,
            effect_mode=rpki_models.RoutingIntentExceptionEffectMode.SUPPRESS,
        )

    def test_approve_action_sets_actor_and_timestamp(self):
        self.add_permissions(
            'netbox_rpki.view_routingintentexception',
            'netbox_rpki.change_routingintentexception',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:routingintentexception-approve',
            kwargs={'pk': self.exception.pk},
        )

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.exception.refresh_from_db()
        self.assertEqual(self.exception.approved_by, self.user.username)
        self.assertIsNotNone(self.exception.approved_at)

    def test_approve_action_response_matches_exception_serializer_contract(self):
        self.add_permissions(
            'netbox_rpki.view_routingintentexception',
            'netbox_rpki.change_routingintentexception',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:routingintentexception-approve',
            kwargs={'pk': self.exception.pk},
        )

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        serializer = api_serializers.RoutingIntentExceptionSerializer(
            self.exception.__class__.objects.get(pk=self.exception.pk),
            context={'request': response.wsgi_request},
        )
        self.assertEqual(set(response.data), set(serializer.data))


class DelegatedPublicationWorkflowActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='delegated-workflow-action-org',
            name='Delegated Workflow Action Org',
        )
        cls.provider_account = create_test_provider_account(
            name='Delegated Workflow Provider',
            organization=cls.organization,
            org_handle='ORG-DELEGATED-WORKFLOW',
        )
        cls.entity = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='Delegated Workflow Entity',
            organization=cls.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.CUSTOMER,
        )
        cls.relationship = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='Delegated Workflow Relationship',
            organization=cls.organization,
            delegated_entity=cls.entity,
            provider_account=cls.provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        cls.workflow = rpki_models.DelegatedPublicationWorkflow.objects.create(
            name='Delegated Workflow Action',
            organization=cls.organization,
            managed_relationship=cls.relationship,
            child_ca_handle='delegated-child-approve',
            publication_server_uri='https://publication.example.invalid/delegated/',
            status=rpki_models.DelegatedPublicationWorkflowStatus.ACTIVE,
            requires_approval=True,
        )

    def test_approve_action_sets_actor_and_timestamp(self):
        self.add_permissions(
            'netbox_rpki.view_delegatedpublicationworkflow',
            'netbox_rpki.change_delegatedpublicationworkflow',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:delegatedpublicationworkflow-approve',
            kwargs={'pk': self.workflow.pk},
        )

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.approved_by, self.user.username)
        self.assertIsNotNone(self.workflow.approved_at)
        self.assertEqual(response.data['workflow_summary']['approval']['approval_state'], 'approved')

    def test_approve_action_response_matches_workflow_serializer_contract(self):
        self.add_permissions(
            'netbox_rpki.view_delegatedpublicationworkflow',
            'netbox_rpki.change_delegatedpublicationworkflow',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:delegatedpublicationworkflow-approve',
            kwargs={'pk': self.workflow.pk},
        )

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        serializer = api_serializers.DelegatedPublicationWorkflowSerializer(
            self.workflow.__class__.objects.get(pk=self.workflow.pk),
            context={'request': response.wsgi_request},
        )
        self.assertEqual(set(response.data), set(serializer.data))


class RoutingIntentTemplateBindingActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='binding-action-org', name='Binding Action Org')
        cls.prefix = create_test_prefix('10.88.0.0/24', status='active')
        cls.origin_asn = create_test_asn(65588)
        cls.profile = create_test_routing_intent_profile(
            name='Binding Action Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.prefix.pk}',
            asn_selector_query='id=999999999',
        )
        cls.template = create_test_routing_intent_template(
            name='Binding Action Template',
            organization=cls.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Binding Action Include',
            template=cls.template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        cls.binding = create_test_routing_intent_template_binding(
            name='Binding Action Binding',
            template=cls.template,
            intent_profile=cls.profile,
            origin_asn_override=cls.origin_asn,
            prefix_selector_query=f'id={cls.prefix.pk}',
        )
        cls.provider_account = create_test_provider_account(
            name='Binding Action Provider',
            organization=cls.organization,
            org_handle='ORG-BINDING-ACTION',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Binding Action Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

    def test_preview_action_returns_compiled_preview_results(self):
        self.add_permissions(
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.change_routingintenttemplatebinding',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:routingintenttemplatebinding-preview',
            kwargs={'pk': self.binding.pk},
        )

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['id'], self.binding.pk)
        self.assertEqual(response.data['preview_result_count'], 1)
        self.assertEqual(response.data['preview_results'][0]['prefix_cidr_text'], str(self.prefix.prefix))
        self.assertEqual(response.data['preview_results'][0]['origin_asn_value'], self.origin_asn.asn)
        self.assertIn('compiled_policy', response.data)

    def test_preview_action_response_contract_is_stable(self):
        self.add_permissions(
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.change_routingintenttemplatebinding',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:routingintenttemplatebinding-preview',
            kwargs={'pk': self.binding.pk},
        )

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        serializer = api_serializers.RoutingIntentTemplateBindingSerializer(
            self.binding,
            context={'request': response.wsgi_request},
        )
        self.assertTrue(set(serializer.data).issubset(response.data))
        self.assertIn('compiled_policy', response.data)
        self.assertIn('preview_result_count', response.data)
        self.assertIn('preview_results', response.data)

    def test_regenerate_action_returns_derivation_and_reconciliation_runs(self):
        self.add_permissions(
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.change_routingintenttemplatebinding',
            'netbox_rpki.view_intentderivationrun',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roalintrun',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:routingintenttemplatebinding-regenerate',
            kwargs={'pk': self.binding.pk},
        )

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.binding.refresh_from_db()
        self.assertEqual(response.data['derivation_run']['intent_profile'], self.profile.pk)
        self.assertEqual(response.data['reconciliation_run']['intent_profile'], self.profile.pk)
        self.assertEqual(self.binding.state, rpki_models.RoutingIntentTemplateBindingState.CURRENT)
        self.assertTrue(self.binding.last_compiled_fingerprint)

    def test_regenerate_action_response_contract_is_stable(self):
        self.add_permissions(
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.change_routingintenttemplatebinding',
            'netbox_rpki.view_intentderivationrun',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roalintrun',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:routingintenttemplatebinding-regenerate',
            kwargs={'pk': self.binding.pk},
        )

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.binding.refresh_from_db()
        serializer = api_serializers.RoutingIntentTemplateBindingSerializer(
            self.binding,
            context={'request': response.wsgi_request},
        )
        self.assertTrue(set(serializer.data).issubset(response.data))
        self.assertEqual(
            set(response.data) - set(serializer.data),
            {'comparison_scope', 'provider_snapshot', 'derivation_run', 'reconciliation_run'},
        )

    def test_regenerate_action_accepts_provider_snapshot_for_provider_imported_scope(self):
        self.add_permissions(
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.change_routingintenttemplatebinding',
            'netbox_rpki.view_intentderivationrun',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roalintrun',
        )
        url = reverse(
            'plugins-api:netbox_rpki-api:routingintenttemplatebinding-regenerate',
            kwargs={'pk': self.binding.pk},
        )

        response = self.client.post(
            url,
            {
                'comparison_scope': rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
                'provider_snapshot': self.provider_snapshot.pk,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['comparison_scope'], rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED)
        self.assertEqual(response.data['provider_snapshot'], self.provider_snapshot.pk)
        self.assertEqual(
            response.data['reconciliation_run']['provider_snapshot'],
            self.provider_snapshot.pk,
        )


class AspaChangePlanActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='org-aspa-plan-action', name='Organization ASPA Plan Action')
        cls.provider_account = create_test_provider_account(
            name='Organization ASPA Plan Provider',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-ASPA-PLAN-ACTION',
            ca_handle='org-aspa-plan-action',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Organization ASPA Plan Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            status='completed',
        )
        cls.customer_as = create_test_asn(65500)
        cls.provider_as = create_test_asn(65501)
        create_test_aspa_intent(
            name='Organization ASPA Plan Intent',
            organization=cls.organization,
            customer_as=cls.customer_as,
            provider_as=cls.provider_as,
        )
        cls.aspa_reconciliation_run = create_test_aspa_reconciliation_run(
            name='Organization ASPA Plan Reconciliation',
            organization=cls.organization,
            provider_snapshot=cls.provider_snapshot,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.aspa_change_plan = create_test_aspa_change_plan(
            name='Organization ASPA Change Plan',
            organization=cls.organization,
            source_reconciliation_run=cls.aspa_reconciliation_run,
            provider_account=cls.provider_account,
            provider_snapshot=cls.provider_snapshot,
        )

    def test_aspa_reconciliation_create_plan_action_returns_plan(self):
        self.add_permissions('netbox_rpki.view_aspareconciliationrun', 'netbox_rpki.change_aspareconciliationrun')
        url = reverse('plugins-api:netbox_rpki-api:aspareconciliationrun-create-plan', kwargs={'pk': self.aspa_reconciliation_run.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['source_reconciliation_run'], self.aspa_reconciliation_run.pk)
        self.assertIn('item_count', response.data)

    def test_aspa_change_plan_preview_action_returns_delta_and_execution(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-preview', kwargs={'pk': self.aspa_change_plan.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('delta', response.data)
        self.assertIn('execution', response.data)
        self.assertEqual(response.data['status'], rpki_models.ASPAChangePlanStatus.DRAFT)

    def test_aspa_change_plan_approve_action_transitions_plan(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-approve', kwargs={'pk': self.aspa_change_plan.pk})

        response = self.client.post(url, {'ticket_reference': 'ASPA-API-CHG'}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.aspa_change_plan.refresh_from_db()
        self.assertEqual(self.aspa_change_plan.status, rpki_models.ASPAChangePlanStatus.APPROVED)
        self.assertEqual(self.aspa_change_plan.approved_by, self.user.username)
        self.assertEqual(response.data['approval_record']['ticket_reference'], 'ASPA-API-CHG')

    def test_aspa_change_plan_apply_action_runs_provider_write_flow(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan', 'netbox_rpki.change_aspachangeplan')
        self.aspa_change_plan.status = rpki_models.ASPAChangePlanStatus.APPROVED
        self.aspa_change_plan.approved_at = timezone.now()
        self.aspa_change_plan.approved_by = 'api-approver'
        self.aspa_change_plan.save(update_fields=('status', 'approved_at', 'approved_by'))
        followup_snapshot = create_test_provider_snapshot(
            name='Organization ASPA API Follow-Up Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        followup_sync_run = create_test_provider_sync_run(
            name='Organization ASPA API Follow-Up Sync',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=followup_snapshot,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-apply', kwargs={'pk': self.aspa_change_plan.pk})

        with patch('netbox_rpki.api.views.apply_aspa_change_plan_provider_write', return_value=(
            create_test_provider_write_execution(
                name='Organization ASPA API Execution',
                organization=self.organization,
                provider_account=self.provider_account,
                provider_snapshot=self.provider_snapshot,
                change_plan=None,
                aspa_change_plan=self.aspa_change_plan,
                execution_mode=rpki_models.ProviderWriteExecutionMode.APPLY,
                status=rpki_models.ValidationRunStatus.COMPLETED,
                followup_sync_run=followup_sync_run,
                followup_provider_snapshot=followup_snapshot,
            ),
            {'added': [], 'removed': []},
        )):
            response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('execution', response.data)
        self.assertEqual(response.data['execution']['status'], rpki_models.ValidationRunStatus.COMPLETED)

    def test_aspa_change_plan_summary_action_returns_aggregate_counts(self):
        self.add_permissions('netbox_rpki.view_aspachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:aspachangeplan-summary')

        response = self.client.get(url, **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('total_plans', response.data)
        self.assertIn('by_status', response.data)
        self.assertIn('provider_add_count_total', response.data)


class ProviderAccountSummaryAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-summary-org', name='Provider Summary Org')
        cls.healthy_account = create_test_provider_account(
            name='Provider Summary Healthy',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-SUMMARY-HEALTHY',
            ca_handle='summary-healthy',
            sync_interval=60,
            last_successful_sync=timezone.now(),
            last_sync_status='completed',
        )
        cls.healthy_base_snapshot = create_test_provider_snapshot(
            name='Provider Summary Base Snapshot',
            organization=cls.organization,
            provider_account=cls.healthy_account,
        )
        cls.healthy_snapshot = create_test_provider_snapshot(
            name='Provider Summary Latest Snapshot',
            organization=cls.organization,
            provider_account=cls.healthy_account,
        )
        cls.healthy_diff = create_test_provider_snapshot_diff(
            name='Provider Summary Latest Diff',
            organization=cls.organization,
            provider_account=cls.healthy_account,
            base_snapshot=cls.healthy_base_snapshot,
            comparison_snapshot=cls.healthy_snapshot,
        )
        cls.healthy_account.last_sync_summary_json = build_provider_sync_summary(
            cls.healthy_account,
            status='completed',
            family_summaries={},
        )
        cls.healthy_account.last_sync_summary_json['latest_snapshot_id'] = cls.healthy_snapshot.pk
        cls.healthy_account.last_sync_summary_json['latest_snapshot_name'] = cls.healthy_snapshot.name
        cls.healthy_account.last_sync_summary_json['latest_snapshot_completed_at'] = timezone.now().isoformat()
        cls.healthy_account.last_sync_summary_json['latest_diff_id'] = cls.healthy_diff.pk
        cls.healthy_account.last_sync_summary_json['latest_diff_name'] = cls.healthy_diff.name
        cls.healthy_account.save(update_fields=['last_sync_summary_json'])
        cls.stale_account = create_test_provider_account(
            name='Provider Summary Stale',
            organization=cls.organization,
            provider_type='arin',
            org_handle='ORG-SUMMARY-STALE',
            sync_interval=60,
            last_successful_sync=timezone.now() - timedelta(hours=3),
            last_sync_status='completed',
        )
        cls.failed_account = create_test_provider_account(
            name='Provider Summary Failed',
            organization=cls.organization,
            provider_type='arin',
            org_handle='ORG-SUMMARY-FAILED',
            sync_interval=60,
            last_sync_status='failed',
        )

    def test_provider_account_summary_reports_health_and_capabilities(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
        )

        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:provideraccount-summary'),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['total_accounts'], 3)
        self.assertEqual(response.data['by_provider_type']['arin'], 2)
        self.assertEqual(response.data['by_provider_type']['krill'], 1)
        self.assertEqual(response.data['by_sync_health']['healthy'], 1)
        self.assertEqual(response.data['by_sync_health']['stale'], 1)
        self.assertEqual(response.data['by_sync_health']['failed'], 1)
        self.assertEqual(response.data['latest_snapshot_count'], 1)
        self.assertEqual(response.data['latest_diff_count'], 1)
        self.assertIn('pending', response.data['by_family_status'])
        self.assertEqual(len(response.data['accounts']), 3)
        self.assertTrue(any(account['latest_snapshot_id'] == self.healthy_snapshot.pk for account in response.data['accounts']))
        self.assertTrue(any(account['latest_diff_id'] == self.healthy_diff.pk for account in response.data['accounts']))
        self.assertTrue(any('family_rollups' in account for account in response.data['accounts']))
        self.assertEqual(response.data['accounts'][0]['lifecycle_health_summary']['summary_schema_version'], 1)
        self.assertIn('publication_health', response.data['accounts'][0])
        self.assertEqual(response.data['sync_due_count'], 2)
        self.assertEqual(response.data['roa_write_supported_count'], 1)
        self.assertEqual(response.data['aspa_write_supported_count'], 1)


class ExternalOverlayHistoryAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='external-history-api-org', name='External History API Org')
        cls.validator = create_test_validator_instance(
            name='External History Validator',
            organization=cls.organization,
        )
        create_test_validation_run(
            name='External History Older Validation Run',
            validator=cls.validator,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            repository_serial='200',
            completed_at=timezone.now() - timedelta(days=2),
            summary_json={'validated_roa_payload_count': 1},
        )
        cls.latest_validation_run = create_test_validation_run(
            name='External History Latest Validation Run',
            validator=cls.validator,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            repository_serial='201',
            completed_at=timezone.now() - timedelta(hours=1),
            summary_json={'validated_roa_payload_count': 3},
        )
        cls.telemetry_source = create_test_telemetry_source(
            name='External History Telemetry Source',
            organization=cls.organization,
            slug='external-history-telemetry',
            import_interval=60,
        )
        create_test_telemetry_run(
            name='External History Older Telemetry Run',
            source=cls.telemetry_source,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=timezone.now() - timedelta(hours=3),
            summary_json={'observation_count': 2},
        )
        cls.latest_telemetry_run = create_test_telemetry_run(
            name='External History Latest Telemetry Run',
            source=cls.telemetry_source,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            completed_at=timezone.now() - timedelta(minutes=30),
            summary_json={'observation_count': 5},
        )

    def test_validator_and_telemetry_history_actions_return_comparison_payloads(self):
        self.add_permissions('netbox_rpki.view_validatorinstance', 'netbox_rpki.view_telemetrysource')

        validator_response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:validatorinstance-history-summary', kwargs={'pk': self.validator.pk}),
            **self.header,
        )
        telemetry_response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:telemetrysource-history-summary', kwargs={'pk': self.telemetry_source.pk}),
            **self.header,
        )

        self.assertHttpStatus(validator_response, 200)
        self.assertHttpStatus(telemetry_response, 200)
        self.assertEqual(validator_response.data['latest_run_id'], self.latest_validation_run.pk)
        self.assertEqual(validator_response.data['latest_comparison']['comparison_state'], 'changed')
        self.assertEqual(telemetry_response.data['latest_run_id'], self.latest_telemetry_run.pk)
        self.assertEqual(
            telemetry_response.data['latest_comparison']['changed_summary_fields']['observation_count']['delta'],
            3,
        )

    def _provider_account_timeline_actions_reference(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
        )
        create_test_provider_snapshot_diff_item(
            snapshot_diff=self.healthy_diff,
            object_family=rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
            change_type=rpki_models.ProviderSnapshotDiffChangeType.CHANGED,
        )

        timeline_response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:provideraccount-timeline', kwargs={'pk': self.healthy_account.pk}),
            **self.header,
        )
        publication_diff_response = self.client.get(
            reverse(
                'plugins-api:netbox_rpki-api:provideraccount-publication-diff-summary',
                kwargs={'pk': self.healthy_account.pk},
            ),
            **self.header,
        )

        self.assertHttpStatus(timeline_response, 200)
        self.assertHttpStatus(publication_diff_response, 200)
        self.assertEqual(timeline_response.data['timeline_schema_version'], LIFECYCLE_TIMELINE_SCHEMA_VERSION)
        self.assertEqual(timeline_response.data['item_count'], 2)
        self.assertEqual(timeline_response.data['items'][0]['latest_diff_id'], self.healthy_diff.pk)
        self.assertEqual(timeline_response.data['items'][0]['publication_changes'], 1)
        self.assertEqual(
            publication_diff_response.data['timeline_schema_version'],
            PUBLICATION_DIFF_TIMELINE_SCHEMA_VERSION,
        )
        self.assertEqual(publication_diff_response.data['item_count'], 1)
        self.assertEqual(publication_diff_response.data['items'][0]['snapshot_diff_id'], self.healthy_diff.pk)
        self.assertEqual(publication_diff_response.data['items'][0]['publication_changes'], 1)


class LifecycleExportFormatterAPITestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='lifecycle-export-api-org', name='Lifecycle Export API Org')
        cls.provider_account = create_test_provider_account(
            name='Lifecycle Export API Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='export-api-ca',
            org_handle='ORG-LIFECYCLE-EXPORT-API',
        )
        cls.base_snapshot = create_test_provider_snapshot(
            name='Lifecycle Export Base Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            fetched_at=timezone.now() - timedelta(days=2),
            completed_at=timezone.now() - timedelta(days=2, minutes=5),
        )
        cls.comparison_snapshot = create_test_provider_snapshot(
            name='Lifecycle Export Comparison Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            fetched_at=timezone.now() - timedelta(days=1),
            completed_at=timezone.now() - timedelta(days=1, minutes=5),
        )
        cls.snapshot_diff = create_test_provider_snapshot_diff(
            name='Lifecycle Export Diff',
            organization=cls.organization,
            provider_account=cls.provider_account,
            base_snapshot=cls.base_snapshot,
            comparison_snapshot=cls.comparison_snapshot,
            summary_json={
                'status': rpki_models.ValidationRunStatus.COMPLETED,
                'totals': {
                    'records_added': 1,
                    'records_removed': 2,
                    'records_changed': 3,
                    'records_stale': 1,
                },
            },
        )
        create_test_provider_snapshot_diff_item(
            snapshot_diff=cls.snapshot_diff,
            object_family=rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
            change_type=rpki_models.ProviderSnapshotDiffChangeType.CHANGED,
            is_stale=True,
        )

    def test_lifecycle_export_helpers_build_expected_envelope_and_rows(self):
        summary = build_provider_lifecycle_health_summary(self.provider_account)
        timeline = build_provider_lifecycle_timeline(self.provider_account)
        publication_diff_timeline = build_provider_publication_diff_timeline(self.provider_account)

        summary_payload = build_lifecycle_export_payload(
            LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY,
            summary,
            filters={'provider_account_id': self.provider_account.pk},
        )
        summary_rows = list(iter_lifecycle_export_rows(
            LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY,
            summary,
        ))
        timeline_rows = list(iter_lifecycle_export_rows(
            LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE,
            timeline,
        ))
        publication_diff_rows = list(iter_lifecycle_export_rows(
            LIFECYCLE_EXPORT_KIND_PROVIDER_PUBLICATION_DIFF_TIMELINE,
            publication_diff_timeline,
        ))

        self.assertEqual(summary_payload['export_schema_version'], LIFECYCLE_EXPORT_SCHEMA_VERSION)
        self.assertEqual(summary_payload['kind'], LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY)
        self.assertEqual(summary_payload['format'], 'json')
        self.assertEqual(summary_payload['filters']['provider_account_id'], self.provider_account.pk)
        self.assertEqual(summary_payload['data']['provider_account_id'], self.provider_account.pk)
        self.assertEqual(summary_rows[0]['summary_schema_version'], 1)
        self.assertEqual(timeline_rows[0]['snapshot_id'], self.comparison_snapshot.pk)
        self.assertEqual(timeline_rows[0]['latest_diff_id'], self.snapshot_diff.pk)
        self.assertEqual(publication_diff_rows[0]['snapshot_diff_id'], self.snapshot_diff.pk)
        self.assertEqual(publication_diff_rows[0]['publication_changes'], 1)


class ProviderSnapshotActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-snapshot-action-org', name='Provider Snapshot Action Org')
        cls.provider_account = create_test_provider_account(
            name='Provider Snapshot Action Account',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-SNAPSHOT-ACTION',
            ca_handle='snapshot-action',
        )
        cls.base_snapshot = create_test_provider_snapshot(
            name='Provider Snapshot Base',
            organization=cls.organization,
            provider_account=cls.provider_account,
            fetched_at=timezone.now() - timedelta(hours=2),
            completed_at=timezone.now() - timedelta(hours=2),
            status='completed',
        )
        cls.comparison_snapshot = create_test_provider_snapshot(
            name='Provider Snapshot Comparison',
            organization=cls.organization,
            provider_account=cls.provider_account,
            fetched_at=timezone.now() - timedelta(hours=1),
            completed_at=timezone.now() - timedelta(hours=1),
            status='completed',
        )
        cls.imported_publication_point = create_test_imported_publication_point(
            name='Provider Snapshot API Publication Point',
            organization=cls.organization,
            provider_snapshot=cls.comparison_snapshot,
            publication_uri='rsync://api-snapshot.invalid/repo/',
        )
        cls.imported_signed_object = create_test_imported_signed_object(
            name='Provider Snapshot API Signed Object',
            organization=cls.organization,
            provider_snapshot=cls.comparison_snapshot,
            publication_point=cls.imported_publication_point,
            signed_object_uri='rsync://api-snapshot.invalid/repo/example.mft',
        )
        cls.imported_certificate_observation = create_test_imported_certificate_observation(
            name='Provider Snapshot API Certificate Observation',
            organization=cls.organization,
            provider_snapshot=cls.comparison_snapshot,
            publication_point=cls.imported_publication_point,
            signed_object=cls.imported_signed_object,
            certificate_uri='rsync://api-snapshot.invalid/repo/example.cer',
            publication_uri=cls.imported_publication_point.publication_uri,
            signed_object_uri=cls.imported_signed_object.signed_object_uri,
        )
        cls.comparison_snapshot.summary_json = build_provider_sync_summary(
            cls.provider_account,
            status='completed',
            family_summaries={
                'roa_authorizations': {
                    'records_imported': 2,
                    'records_stale': 1,
                    'records_changed': 1,
                },
            },
        )
        cls.comparison_snapshot.save(update_fields=['summary_json'])

    def test_provider_snapshot_compare_action_returns_persisted_diff(self):
        self.add_permissions('netbox_rpki.view_providersnapshot', 'netbox_rpki.view_providersnapshotdiff')

        response = self.client.post(
            reverse(
                'plugins-api:netbox_rpki-api:providersnapshot-compare',
                kwargs={'pk': self.comparison_snapshot.pk},
            ),
            {'base_snapshot': self.base_snapshot.pk},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['base_snapshot'], self.base_snapshot.pk)
        self.assertEqual(response.data['comparison_snapshot'], self.comparison_snapshot.pk)
        self.assertEqual(response.data['item_count'], 3)
        self.assertIn('family_rollups', response.data)
        self.assertIn('family_status_counts', response.data)
        self.assertIn('publication_diff_summary', response.data)
        publication_points_rollup = next(
            row for row in response.data['family_rollups'] if row['family'] == 'publication_points'
        )
        self.assertEqual(publication_points_rollup['churn_status'], 'active')

    def test_provider_snapshot_summary_reports_status_and_diff_coverage(self):
        self.add_permissions('netbox_rpki.view_providersnapshot', 'netbox_rpki.view_providersnapshotdiff')
        create_test_provider_snapshot_diff(
            name='Provider Snapshot Existing Diff',
            organization=self.organization,
            provider_account=self.provider_account,
            base_snapshot=self.base_snapshot,
            comparison_snapshot=self.comparison_snapshot,
        )

        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:providersnapshot-summary'),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['total_snapshots'], 2)
        self.assertEqual(response.data['completed_snapshots'], 2)
        self.assertEqual(response.data['by_status']['completed'], 2)
        self.assertEqual(response.data['with_diff_count'], 1)
        self.assertIsNotNone(response.data['latest_completed_at'])

    def test_provider_snapshot_detail_includes_publication_observation_children(self):
        self.add_permissions(
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
            'netbox_rpki.view_importedpublicationpoint',
            'netbox_rpki.view_importedsignedobject',
            'netbox_rpki.view_importedcertificateobservation',
        )
        snapshot_diff = create_test_provider_snapshot_diff(
            name='Provider Snapshot Detail Existing Diff',
            organization=self.organization,
            provider_account=self.provider_account,
            base_snapshot=self.base_snapshot,
            comparison_snapshot=self.comparison_snapshot,
        )

        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:providersnapshot-detail', kwargs={'pk': self.comparison_snapshot.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['latest_diff']['id'], snapshot_diff.pk)
        self.assertIn('family_rollups', response.data)
        self.assertIn('family_status_counts', response.data)
        self.assertIn('publication_health', response.data)
        self.assertEqual(response.data['publication_health']['summary_schema_version'], 1)
        self.assertEqual(response.data['latest_diff_summary']['snapshot_diff_id'], snapshot_diff.pk)
        self.assertEqual(response.data['latest_diff']['publication_diff_summary']['summary_schema_version'], 1)
        self.assertTrue(any(row['family'] == 'roa_authorizations' for row in response.data['family_rollups']))
        self.assertEqual(response.data['publication_health']['summary_schema_version'], 1)
        self.assertEqual(
            [row['id'] for row in response.data['imported_publication_points']],
            [self.imported_publication_point.pk],
        )
        self.assertEqual(
            [row['id'] for row in response.data['imported_signed_objects']],
            [self.imported_signed_object.pk],
        )
        self.assertEqual(
            [row['id'] for row in response.data['imported_certificate_observations']],
            [self.imported_certificate_observation.pk],
        )
        imported_certificate_observation = response.data['imported_certificate_observations'][0]
        publication_point = imported_certificate_observation['publication_point']
        signed_object = imported_certificate_observation['signed_object']
        self.assertEqual(
            publication_point['id'] if isinstance(publication_point, dict) else publication_point,
            self.imported_publication_point.pk,
        )
        self.assertEqual(
            signed_object['id'] if isinstance(signed_object, dict) else signed_object,
            self.imported_signed_object.pk,
        )


class ImportedCertificateObservationAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='imported-cert-observation-api-org',
            name='Imported Certificate Observation API Org',
        )
        cls.provider_account = create_test_provider_account(
            name='Imported Certificate Observation API Account',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-IMPORTED-CERT-API',
            ca_handle='imported-cert-api',
        )
        cls.snapshot = create_test_provider_snapshot(
            name='Imported Certificate Observation API Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            status='completed',
        )
        cls.imported_publication_point = create_test_imported_publication_point(
            name='Imported Certificate Observation API Publication Point',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            publication_uri='rsync://api.invalid/repo/',
            payload_json={
                'authored_linkage': {'status': 'linked'},
                'evidence_summary': {'published_object_count': 1, 'authored_linkage_status': 'linked'},
            },
        )
        cls.imported_signed_object = create_test_imported_signed_object(
            name='Imported Certificate Observation API Signed Object',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            publication_point=cls.imported_publication_point,
            signed_object_uri='rsync://api.invalid/repo/example.mft',
            payload_json={
                'publication_linkage': {'status': 'linked'},
                'authored_linkage': {'status': 'unmatched'},
                'evidence_summary': {
                    'signed_object_type': 'manifest',
                    'publication_linkage_status': 'linked',
                    'authored_linkage_status': 'unmatched',
                },
            },
        )
        cls.certificate_observation = create_test_imported_certificate_observation(
            name='Imported Certificate Observation API Record',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            certificate_uri='rsync://api.invalid/repo/example.cer',
            publication_point=cls.imported_publication_point,
            signed_object=cls.imported_signed_object,
            publication_uri=cls.imported_publication_point.publication_uri,
            signed_object_uri=cls.imported_signed_object.signed_object_uri,
            payload_json={
                'source_summary': {
                    'source_count': 2,
                    'source_labels': ['Signed Object EE Certificate', 'Parent Issued Certificate'],
                    'has_multiple_sources': True,
                    'is_ambiguous': True,
                },
                'publication_linkage': {'status': 'derived_from_signed_object'},
                'signed_object_linkage': {'status': 'linked'},
                'evidence_summary': {
                    'source_count': 2,
                    'source_labels': ['Signed Object EE Certificate', 'Parent Issued Certificate'],
                    'has_multiple_sources': True,
                    'is_ambiguous': True,
                    'publication_linkage_status': 'derived_from_signed_object',
                    'signed_object_linkage_status': 'linked',
                },
            },
        )

    def test_imported_certificate_observation_list_and_detail_are_exposed(self):
        self.add_permissions(
            'netbox_rpki.view_importedcertificateobservation',
            'netbox_rpki.view_importedpublicationpoint',
            'netbox_rpki.view_importedsignedobject',
        )
        spec = OBJECT_SPEC_BY_REGISTRY_KEY['importedcertificateobservation']
        list_url = reverse(f'plugins-api:netbox_rpki-api:{spec.api.basename}-list')
        detail_url = reverse(
            spec.api.detail_view_name,
            kwargs={'pk': self.certificate_observation.pk},
        )

        list_response = self.client.get(list_url, **self.header)
        detail_response = self.client.get(detail_url, **self.header)

        self.assertHttpStatus(list_response, 200)
        self.assertEqual(len(list_response.data['results']), 1)
        self.assertEqual(list_response.data['results'][0]['id'], self.certificate_observation.pk)
        self.assertHttpStatus(detail_response, 200)
        self.assertEqual(detail_response.data['id'], self.certificate_observation.pk)
        self.assertEqual(detail_response.data['certificate_uri'], 'rsync://api.invalid/repo/example.cer')
        self.assertEqual(detail_response.data['source_count'], 2)
        self.assertEqual(detail_response.data['source_labels'], ['Signed Object EE Certificate', 'Parent Issued Certificate'])
        self.assertTrue(detail_response.data['is_ambiguous'])
        self.assertEqual(detail_response.data['publication_linkage_status'], 'derived_from_signed_object')
        self.assertEqual(detail_response.data['signed_object_linkage_status'], 'linked')
        publication_point = detail_response.data['publication_point']
        signed_object = detail_response.data['signed_object']
        self.assertEqual(
            publication_point['id'] if isinstance(publication_point, dict) else publication_point,
            self.imported_publication_point.pk,
        )
        self.assertEqual(
            signed_object['id'] if isinstance(signed_object, dict) else signed_object,
            self.imported_signed_object.pk,
        )
        self.assertEqual(detail_response.data['evidence_summary']['source_count'], 2)

    def test_imported_certificate_observation_endpoint_is_read_only(self):
        self.add_permissions('netbox_rpki.add_importedcertificateobservation')
        spec = OBJECT_SPEC_BY_REGISTRY_KEY['importedcertificateobservation']
        list_url = reverse(f'plugins-api:netbox_rpki-api:{spec.api.basename}-list')

        response = self.client.post(
            list_url,
            {
                'name': 'Should Not Create',
                'provider_snapshot': self.snapshot.pk,
                'organization': self.organization.pk,
                'certificate_key': 'blocked',
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 405)


class ImportedIrrRouteObjectProvenanceAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='imported-irr-provenance-api-org',
            name='Imported IRR Provenance API Org',
        )
        cls.source = create_test_irr_source(
            name='Imported IRR Provenance Source',
            slug='imported-irr-provenance-source',
            organization=cls.organization,
        )
        cls.snapshot = create_test_irr_snapshot(
            name='Imported IRR Provenance Snapshot',
            source=cls.source,
            fetch_mode=rpki_models.IrrFetchMode.SNAPSHOT_IMPORT,
            status=rpki_models.IrrSnapshotStatus.COMPLETED,
        )
        cls.route_current = create_test_imported_irr_route_object(
            name='route:198.51.100.0/24AS64500',
            snapshot=cls.snapshot,
            source=cls.source,
            stable_key='route:198.51.100.0/24AS64500',
            prefix='198.51.100.0/24',
            origin_asn='AS64500',
            provenance_type=rpki_models.IrrObjectProvenanceType.IMPORTED,
            creation_path=rpki_models.IrrObjectCreationPath.SNAPSHOT_IMPORT,
            provenance_confidence=rpki_models.IrrObjectProvenanceConfidence.HIGH,
            first_seen_at=timezone.now() - timedelta(days=2),
            last_seen_at=timezone.now() - timedelta(hours=1),
            freshness_status=rpki_models.IrrObjectFreshness.CURRENT,
            provenance_summary_json={
                'fetch_mode': rpki_models.IrrFetchMode.SNAPSHOT_IMPORT,
                'snapshot_status': rpki_models.IrrSnapshotStatus.COMPLETED,
            },
        )
        cls.route_historical = create_test_imported_irr_route_object(
            name='route:203.0.113.0/24AS64501',
            snapshot=cls.snapshot,
            source=cls.source,
            stable_key='route:203.0.113.0/24AS64501',
            prefix='203.0.113.0/24',
            origin_asn='AS64501',
            provenance_type=rpki_models.IrrObjectProvenanceType.DERIVED,
            creation_path=rpki_models.IrrObjectCreationPath.ROUTE_REFERENCE,
            provenance_confidence=rpki_models.IrrObjectProvenanceConfidence.MEDIUM,
            first_seen_at=timezone.now() - timedelta(days=5),
            last_seen_at=timezone.now() - timedelta(days=3),
            freshness_status=rpki_models.IrrObjectFreshness.HISTORICAL,
            provenance_summary_json={
                'derived_from': 'route:203.0.113.0/24AS64501',
            },
        )

    def test_imported_irr_route_object_detail_exposes_provenance_fields(self):
        self.add_permissions('netbox_rpki.view_importedirrrouteobject')
        spec = OBJECT_SPEC_BY_REGISTRY_KEY['imported_irr_route_object']
        detail_url = reverse(spec.api.detail_view_name, kwargs={'pk': self.route_current.pk})

        response = self.client.get(detail_url, **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['id'], self.route_current.pk)
        self.assertEqual(response.data['provenance_type'], rpki_models.IrrObjectProvenanceType.IMPORTED)
        self.assertEqual(response.data['creation_path'], rpki_models.IrrObjectCreationPath.SNAPSHOT_IMPORT)
        self.assertEqual(response.data['provenance_confidence'], rpki_models.IrrObjectProvenanceConfidence.HIGH)
        self.assertEqual(response.data['freshness_status'], rpki_models.IrrObjectFreshness.CURRENT)
        self.assertIn('fetch_mode', response.data['provenance_summary_json'])

    def test_imported_irr_route_object_list_filters_by_provenance_and_freshness(self):
        self.add_permissions('netbox_rpki.view_importedirrrouteobject')
        spec = OBJECT_SPEC_BY_REGISTRY_KEY['imported_irr_route_object']
        list_url = reverse(f'plugins-api:netbox_rpki-api:{spec.api.basename}-list')

        response = self.client.get(
            list_url,
            {
                'provenance_type': rpki_models.IrrObjectProvenanceType.DERIVED,
                'freshness_status': rpki_models.IrrObjectFreshness.HISTORICAL,
            },
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.route_historical.pk)


class ImportedPublicationLinkAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='imported-publication-link-api-org',
            name='Imported Publication Link API Org',
        )
        cls.provider_account = create_test_provider_account(
            name='Imported Publication Link API Account',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-IMPORTED-LINK-API',
            ca_handle='imported-link-api',
        )
        cls.snapshot = create_test_provider_snapshot(
            name='Imported Publication Link API Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            status='completed',
        )
        cls.authored_publication_point = create_test_publication_point(
            name='Imported Publication Link API Authored Publication Point',
            organization=cls.organization,
            publication_uri='rsync://api.invalid/repo/',
        )
        cls.authored_signed_object = create_test_signed_object(
            name='Imported Publication Link API Authored Signed Object',
            organization=cls.organization,
            publication_point=cls.authored_publication_point,
            object_type='manifest',
            object_uri='rsync://api.invalid/repo/example.mft',
        )
        cls.imported_publication_point = create_test_imported_publication_point(
            name='Imported Publication Link API Publication Point',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            authored_publication_point=cls.authored_publication_point,
            publication_uri=cls.authored_publication_point.publication_uri,
            payload_json={
                'authored_linkage': {'status': 'linked'},
                'evidence_summary': {'published_object_count': 1, 'authored_linkage_status': 'linked'},
            },
        )
        cls.imported_signed_object = create_test_imported_signed_object(
            name='Imported Publication Link API Signed Object',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            publication_point=cls.imported_publication_point,
            authored_signed_object=cls.authored_signed_object,
            signed_object_type='manifest',
            signed_object_uri=cls.authored_signed_object.object_uri,
            publication_uri=cls.imported_publication_point.publication_uri,
            payload_json={
                'publication_linkage': {'status': 'linked'},
                'authored_linkage': {'status': 'linked'},
                'evidence_summary': {
                    'signed_object_type': 'manifest',
                    'publication_linkage_status': 'linked',
                    'authored_linkage_status': 'linked',
                },
            },
        )

    def test_imported_publication_point_detail_exposes_authored_publication_point(self):
        self.add_permissions('netbox_rpki.view_importedpublicationpoint', 'netbox_rpki.view_publicationpoint')

        spec = OBJECT_SPEC_BY_REGISTRY_KEY['importedpublicationpoint']
        response = self.client.get(
            reverse(spec.api.detail_view_name, kwargs={'pk': self.imported_publication_point.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        authored_publication_point = response.data['authored_publication_point']
        self.assertEqual(response.data['authored_linkage_status'], 'linked')
        self.assertEqual(response.data['evidence_summary']['published_object_count'], 1)
        self.assertEqual(
            authored_publication_point['id'] if isinstance(authored_publication_point, dict) else authored_publication_point,
            self.authored_publication_point.pk,
        )

    def test_imported_signed_object_detail_exposes_authored_signed_object(self):
        self.add_permissions('netbox_rpki.view_importedsignedobject', 'netbox_rpki.view_signedobject')

        spec = OBJECT_SPEC_BY_REGISTRY_KEY['importedsignedobject']
        response = self.client.get(
            reverse(spec.api.detail_view_name, kwargs={'pk': self.imported_signed_object.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        authored_signed_object = response.data['authored_signed_object']
        self.assertEqual(response.data['publication_linkage_status'], 'linked')
        self.assertEqual(response.data['authored_linkage_status'], 'linked')
        self.assertEqual(response.data['evidence_summary']['signed_object_type'], 'manifest')
        self.assertEqual(
            authored_signed_object['id'] if isinstance(authored_signed_object, dict) else authored_signed_object,
            self.authored_signed_object.pk,
        )


class CertificateRoleLinkAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='certificate-role-link-api-org',
            name='Certificate Role Link API Org',
        )
        cls.trust_anchor = create_test_trust_anchor(
            name='Certificate Role Link API Trust Anchor',
            organization=cls.organization,
        )
        cls.publication_point = create_test_publication_point(
            name='Certificate Role Link API Publication Point',
            organization=cls.organization,
            publication_uri='rsync://api.invalid/certs/',
        )
        cls.certificate = create_test_certificate(
            name='Certificate Role Link API Resource Certificate',
            rpki_org=cls.organization,
            trust_anchor=cls.trust_anchor,
            publication_point=cls.publication_point,
        )
        cls.ee_certificate = create_test_end_entity_certificate(
            name='Certificate Role Link API EE Certificate',
            organization=cls.organization,
            resource_certificate=cls.certificate,
            publication_point=cls.publication_point,
        )

    def test_certificate_detail_exposes_trust_anchor_and_publication_point(self):
        self.add_permissions(
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_trustanchor',
            'netbox_rpki.view_publicationpoint',
        )

        spec = OBJECT_SPEC_BY_REGISTRY_KEY['certificate']
        response = self.client.get(
            reverse(spec.api.detail_view_name, kwargs={'pk': self.certificate.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        trust_anchor = response.data['trust_anchor']
        publication_point = response.data['publication_point']
        self.assertEqual(trust_anchor['id'] if isinstance(trust_anchor, dict) else trust_anchor, self.trust_anchor.pk)
        self.assertEqual(
            publication_point['id'] if isinstance(publication_point, dict) else publication_point,
            self.publication_point.pk,
        )

    def test_end_entity_certificate_detail_exposes_resource_certificate_and_publication_point(self):
        self.add_permissions(
            'netbox_rpki.view_endentitycertificate',
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_publicationpoint',
        )

        spec = OBJECT_SPEC_BY_REGISTRY_KEY['endentitycertificate']
        response = self.client.get(
            reverse(spec.api.detail_view_name, kwargs={'pk': self.ee_certificate.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        resource_certificate = response.data['resource_certificate']
        publication_point = response.data['publication_point']
        self.assertEqual(
            resource_certificate['id'] if isinstance(resource_certificate, dict) else resource_certificate,
            self.certificate.pk,
        )
        self.assertEqual(
            publication_point['id'] if isinstance(publication_point, dict) else publication_point,
            self.publication_point.pk,
        )


class CertificateRevocationListAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='crl-api-org',
            name='CRL API Org',
        )
        cls.signed_object = create_test_signed_object(
            name='CRL API Signed Object',
            organization=cls.organization,
            filename='api.crl',
            object_uri='https://api.invalid/crl.crl',
            repository_uri='https://api.invalid/',
        )
        cls.certificate_revocation_list = create_test_certificate_revocation_list(
            name='CRL API Record',
            organization=cls.organization,
            signed_object=cls.signed_object,
            publication_uri='https://api.invalid/crl.crl',
            crl_number='7',
        )

    def test_certificate_revocation_list_list_and_detail_expose_signed_object(self):
        self.add_permissions(
            'netbox_rpki.view_certificaterevocationlist',
            'netbox_rpki.view_signedobject',
        )
        spec = OBJECT_SPEC_BY_REGISTRY_KEY['certificaterevocationlist']
        list_url = reverse(f'plugins-api:netbox_rpki-api:{spec.api.basename}-list')
        detail_url = reverse(
            spec.api.detail_view_name,
            kwargs={'pk': self.certificate_revocation_list.pk},
        )

        list_response = self.client.get(list_url, **self.header)
        detail_response = self.client.get(detail_url, **self.header)

        self.assertHttpStatus(list_response, 200)
        self.assertEqual(len(list_response.data['results']), 1)
        self.assertEqual(list_response.data['results'][0]['id'], self.certificate_revocation_list.pk)
        signed_object = list_response.data['results'][0]['signed_object']
        self.assertEqual(
            signed_object['id'] if isinstance(signed_object, dict) else signed_object,
            self.signed_object.pk,
        )
        self.assertHttpStatus(detail_response, 200)
        self.assertEqual(detail_response.data['id'], self.certificate_revocation_list.pk)
        signed_object = detail_response.data['signed_object']
        self.assertEqual(
            signed_object['id'] if isinstance(signed_object, dict) else signed_object,
            self.signed_object.pk,
        )


class SignedObjectAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='signed-object-api-org',
            name='Signed Object API Org',
        )
        cls.signed_object = create_test_signed_object(
            name='Signed Object API Record',
            organization=cls.organization,
            object_type='manifest',
            object_uri='rsync://api.invalid/repo/object.mft',
            repository_uri='rsync://api.invalid/repo/',
        )
        cls.manifest = create_test_manifest(
            name='Signed Object API Manifest',
            signed_object=cls.signed_object,
            manifest_number='api-manifest-1',
        )
        cls.signed_object.current_manifest = cls.manifest
        cls.signed_object.save(update_fields=('current_manifest',))
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Signed Object API Snapshot',
            organization=cls.organization,
            provider_account=create_test_provider_account(
                name='Signed Object API Provider Account',
                organization=cls.organization,
                provider_type='krill',
                org_handle='ORG-SIGNED-OBJECT-API',
                ca_handle='signed-object-api',
            ),
        )
        cls.imported_publication_point = create_test_imported_publication_point(
            name='Signed Object API Imported Publication Point',
            organization=cls.organization,
            provider_snapshot=cls.provider_snapshot,
            authored_publication_point=cls.signed_object.publication_point,
            publication_uri='rsync://api.invalid/repo/',
        )
        cls.imported_signed_object = create_test_imported_signed_object(
            name='Signed Object API Imported Observation',
            organization=cls.organization,
            provider_snapshot=cls.provider_snapshot,
            publication_point=cls.imported_publication_point,
            authored_signed_object=cls.signed_object,
            signed_object_type='manifest',
            signed_object_uri=cls.signed_object.object_uri,
        )
        cls.validation_run = create_test_validation_run(
            name='Signed Object API Validation Run',
        )
        cls.object_validation_result = create_test_object_validation_result(
            name='Signed Object API Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.signed_object,
        )

    def test_signed_object_detail_exposes_normalized_reverse_relationships(self):
        self.add_permissions(
            'netbox_rpki.view_signedobject',
            'netbox_rpki.view_manifest',
            'netbox_rpki.view_importedsignedobject',
            'netbox_rpki.view_objectvalidationresult',
        )
        spec = OBJECT_SPEC_BY_REGISTRY_KEY['signedobject']
        detail_url = reverse(spec.api.detail_view_name, kwargs={'pk': self.signed_object.pk})

        response = self.client.get(detail_url, **self.header)

        self.assertHttpStatus(response, 200)
        manifest_extension = response.data['manifest_extension']
        self.assertEqual(
            manifest_extension['id'] if isinstance(manifest_extension, dict) else manifest_extension,
            self.manifest.pk,
        )
        self.assertEqual(
            [row['id'] for row in response.data['imported_signed_object_observations']],
            [self.imported_signed_object.pk],
        )
        self.assertEqual(
            [row['id'] for row in response.data['validation_results']],
            [self.object_validation_result.pk],
        )


class RouterCertificateAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='router-certificate-api-org',
            name='Router Certificate API Org',
        )
        cls.resource_certificate = create_test_certificate(
            name='Router Certificate API Resource Certificate',
            rpki_org=cls.organization,
        )
        cls.ee_certificate = create_test_end_entity_certificate(
            name='Router Certificate API EE Certificate',
            organization=cls.organization,
            resource_certificate=cls.resource_certificate,
            subject='CN=API Router',
            issuer='CN=API Issuer',
            serial='api-router-serial',
            ski='api-router-ski',
        )
        cls.router_certificate = create_test_router_certificate(
            name='Router Certificate API Record',
            organization=cls.organization,
            resource_certificate=cls.resource_certificate,
            publication_point=cls.ee_certificate.publication_point,
            ee_certificate=cls.ee_certificate,
            asn=create_test_asn(65311),
            subject='CN=API Router',
            issuer='CN=API Issuer',
            serial='api-router-serial',
            ski='api-router-ski',
        )

    def test_router_certificate_list_and_detail_expose_ee_certificate(self):
        self.add_permissions(
            'netbox_rpki.view_routercertificate',
            'netbox_rpki.view_endentitycertificate',
        )
        spec = OBJECT_SPEC_BY_REGISTRY_KEY['routercertificate']
        list_url = reverse(f'plugins-api:netbox_rpki-api:{spec.api.basename}-list')
        detail_url = reverse(
            spec.api.detail_view_name,
            kwargs={'pk': self.router_certificate.pk},
        )

        list_response = self.client.get(list_url, **self.header)
        detail_response = self.client.get(detail_url, **self.header)

        self.assertHttpStatus(list_response, 200)
        self.assertEqual(len(list_response.data['results']), 1)
        self.assertEqual(list_response.data['results'][0]['id'], self.router_certificate.pk)
        ee_certificate = list_response.data['results'][0]['ee_certificate']
        self.assertEqual(
            ee_certificate['id'] if isinstance(ee_certificate, dict) else ee_certificate,
            self.ee_certificate.pk,
        )
        self.assertHttpStatus(detail_response, 200)
        self.assertEqual(detail_response.data['id'], self.router_certificate.pk)
        ee_certificate = detail_response.data['ee_certificate']
        self.assertEqual(
            ee_certificate['id'] if isinstance(ee_certificate, dict) else ee_certificate,
            self.ee_certificate.pk,
        )


class ValidatedPayloadValidationLinkAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='validated-payload-api-org',
            name='Validated Payload API Org',
        )
        cls.validation_run = create_test_validation_run(
            name='Validated Payload API Validation Run',
        )
        cls.roa_signing_certificate = create_test_certificate(
            name='Validated Payload API ROA Certificate',
            rpki_org=cls.organization,
        )
        cls.roa_signed_object = create_test_signed_object(
            name='Validated Payload API ROA Signed Object',
            organization=cls.organization,
            object_type='roa',
            resource_certificate=cls.roa_signing_certificate,
        )
        cls.roa = create_test_roa(
            name='Validated Payload API ROA',
            signed_by=cls.roa_signing_certificate,
            signed_object=cls.roa_signed_object,
        )
        cls.roa_object_validation_result = create_test_object_validation_result(
            name='Validated Payload API ROA Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.roa_signed_object,
        )
        cls.validated_roa_payload = create_test_validated_roa_payload(
            name='Validated Payload API ROA Payload',
            validation_run=cls.validation_run,
            roa=cls.roa,
            object_validation_result=cls.roa_object_validation_result,
        )
        cls.aspa = create_test_aspa(
            name='Validated Payload API ASPA',
            organization=cls.organization,
            customer_as=create_test_asn(65410),
        )
        cls.aspa_object_validation_result = create_test_object_validation_result(
            name='Validated Payload API ASPA Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.aspa.signed_object,
        )
        cls.validated_aspa_payload = create_test_validated_aspa_payload(
            name='Validated Payload API ASPA Payload',
            validation_run=cls.validation_run,
            aspa=cls.aspa,
            object_validation_result=cls.aspa_object_validation_result,
            customer_as=cls.aspa.customer_as,
            provider_as=create_test_asn(65411),
        )

    def test_validated_roa_payload_detail_exposes_object_validation_result(self):
        self.add_permissions(
            'netbox_rpki.view_validatedroapayload',
            'netbox_rpki.view_objectvalidationresult',
        )
        spec = OBJECT_SPEC_BY_REGISTRY_KEY['validatedroapayload']
        detail_url = reverse(spec.api.detail_view_name, kwargs={'pk': self.validated_roa_payload.pk})

        response = self.client.get(detail_url, **self.header)

        self.assertHttpStatus(response, 200)
        object_validation_result = response.data['object_validation_result']
        self.assertEqual(
            object_validation_result['id'] if isinstance(object_validation_result, dict) else object_validation_result,
            self.roa_object_validation_result.pk,
        )

    def test_validated_aspa_payload_detail_exposes_object_validation_result(self):
        self.add_permissions(
            'netbox_rpki.view_validatedaspapayload',
            'netbox_rpki.view_objectvalidationresult',
        )
        spec = OBJECT_SPEC_BY_REGISTRY_KEY['validatedaspapayload']
        detail_url = reverse(spec.api.detail_view_name, kwargs={'pk': self.validated_aspa_payload.pk})

        response = self.client.get(detail_url, **self.header)

        self.assertHttpStatus(response, 200)
        object_validation_result = response.data['object_validation_result']
        self.assertEqual(
            object_validation_result['id'] if isinstance(object_validation_result, dict) else object_validation_result,
            self.aspa_object_validation_result.pk,
        )


@_install_registry_api_tests
class OrganizationAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'organization'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='API RIR', slug='api-rir')
        cls.organizations = [
            create_test_organization(org_id='org-1', name='Organization 1', parent_rir=cls.rir),
            create_test_organization(org_id='org-2', name='Organization 2'),
            create_test_organization(org_id='org-3', name='Organization 3'),
        ]


@_install_registry_api_tests
class CertificateAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'certificate'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='Certificate API RIR', slug='certificate-api-rir')
        cls.organizations = [
            create_test_organization(org_id='cert-org-1', name='Certificate Org 1', parent_rir=cls.rir),
            create_test_organization(org_id='cert-org-2', name='Certificate Org 2'),
            create_test_organization(org_id='cert-org-3', name='Certificate Org 3'),
        ]
        cls.certificates = [
            create_test_certificate(name='Certificate 1', issuer='Issuer 1', rpki_org=cls.organizations[0], self_hosted=False),
            create_test_certificate(name='Certificate 2', issuer='Issuer 2', rpki_org=cls.organizations[1], self_hosted=True),
            create_test_certificate(name='Certificate 3', issuer='Issuer 3', rpki_org=cls.organizations[2], self_hosted=False),
        ]


@_install_registry_api_tests
class RoaAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'roaobject'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='ROA API RIR', slug='roa-api-rir')
        cls.organizations = [
            create_test_organization(org_id='roa-org-1', name='ROA Org 1', parent_rir=cls.rir),
            create_test_organization(org_id='roa-org-2', name='ROA Org 2'),
            create_test_organization(org_id='roa-org-3', name='ROA Org 3'),
        ]
        cls.certificates = [
            create_test_certificate(name='ROA Certificate 1', rpki_org=cls.organizations[0]),
            create_test_certificate(name='ROA Certificate 2', rpki_org=cls.organizations[1]),
            create_test_certificate(name='ROA Certificate 3', rpki_org=cls.organizations[2]),
        ]
        cls.asns = [
            create_test_asn(65101, rir=cls.rir),
            create_test_asn(65102, rir=cls.rir),
            create_test_asn(65103, rir=cls.rir),
        ]
        cls.roas = [
            create_test_roa(name='ROA 1', origin_as=cls.asns[0], signed_by=cls.certificates[0], auto_renews=True),
            create_test_roa(name='ROA 2', origin_as=cls.asns[1], signed_by=cls.certificates[1], auto_renews=False),
            create_test_roa(name='ROA 3', origin_as=cls.asns[2], signed_by=cls.certificates[2], auto_renews=True),
        ]
        cls.roa_signed_object = create_test_signed_object(
            name='ROA 1 Signed Object',
            organization=cls.organizations[0],
            object_type='roa',
            resource_certificate=cls.certificates[0],
        )
        cls.roas[0].signed_object = cls.roa_signed_object
        cls.roas[0].save(update_fields=('signed_object',))

    def test_roa_list_and_detail_expose_signed_object(self):
        self.add_permissions('netbox_rpki.view_roaobject', 'netbox_rpki.view_signedobject')
        spec = OBJECT_SPEC_BY_REGISTRY_KEY['roaobject']
        list_url = reverse(f'plugins-api:netbox_rpki-api:{spec.api.basename}-list')
        detail_url = reverse(
            spec.api.detail_view_name,
            kwargs={'pk': self.roas[0].pk},
        )

        list_response = self.client.get(list_url, **self.header)
        detail_response = self.client.get(detail_url, **self.header)

        self.assertHttpStatus(list_response, 200)
        self.assertEqual(list_response.data['results'][0]['id'], self.roas[0].pk)
        signed_object = list_response.data['results'][0]['signed_object']
        self.assertEqual(
            signed_object['id'] if isinstance(signed_object, dict) else signed_object,
            self.roa_signed_object.pk,
        )
        self.assertHttpStatus(detail_response, 200)
        self.assertEqual(detail_response.data['id'], self.roas[0].pk)
        signed_object = detail_response.data['signed_object']
        self.assertEqual(
            signed_object['id'] if isinstance(signed_object, dict) else signed_object,
            self.roa_signed_object.pk,
        )


@_install_registry_api_tests
class RoaPrefixAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'roaobjectprefix'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='ROA Prefix API RIR', slug='roa-prefix-api-rir')
        cls.organization = create_test_organization(org_id='roa-prefix-org-1', name='ROA Prefix Org 1', parent_rir=cls.rir)
        cls.certificate = create_test_certificate(name='ROA Prefix Certificate', rpki_org=cls.organization)
        cls.roas = [
            create_test_roa(name='ROA Prefix Parent 1', signed_by=cls.certificate),
            create_test_roa(name='ROA Prefix Parent 2', signed_by=cls.certificate),
            create_test_roa(name='ROA Prefix Parent 3', signed_by=cls.certificate),
        ]
        cls.prefixes = [
            create_test_prefix('10.20.1.0/24'),
            create_test_prefix('10.20.2.0/24'),
            create_test_prefix('10.20.3.0/24'),
        ]
        cls.roa_prefixes = [
            create_test_roa_prefix(prefix=cls.prefixes[0], roa=cls.roas[0], max_length=24),
            create_test_roa_prefix(prefix=cls.prefixes[1], roa=cls.roas[1], max_length=25),
            create_test_roa_prefix(prefix=cls.prefixes[2], roa=cls.roas[2], max_length=26),
        ]


@_install_registry_api_tests
class CertificatePrefixAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'certificateprefix'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='Certificate Prefix API RIR', slug='certificate-prefix-api-rir')
        cls.organization = create_test_organization(org_id='certificate-prefix-org-1', name='Certificate Prefix Org 1', parent_rir=cls.rir)
        cls.certificates = [
            create_test_certificate(name='Certificate Prefix Parent 1', rpki_org=cls.organization),
            create_test_certificate(name='Certificate Prefix Parent 2', rpki_org=cls.organization),
            create_test_certificate(name='Certificate Prefix Parent 3', rpki_org=cls.organization),
        ]
        cls.prefixes = [
            create_test_prefix('10.30.1.0/24'),
            create_test_prefix('10.30.2.0/24'),
            create_test_prefix('10.30.3.0/24'),
        ]
        cls.certificate_prefixes = [
            create_test_certificate_prefix(prefix=cls.prefixes[0], certificate=cls.certificates[0]),
            create_test_certificate_prefix(prefix=cls.prefixes[1], certificate=cls.certificates[1]),
            create_test_certificate_prefix(prefix=cls.prefixes[2], certificate=cls.certificates[2]),
        ]


@_install_registry_api_tests
class CertificateAsnAPITestCase(RegistryDrivenObjectAPITestCase):
    object_spec_key = 'certificateasn'

    @classmethod
    def setUpTestData(cls):
        cls.rir = create_test_rir(name='Certificate ASN API RIR', slug='certificate-asn-api-rir')
        cls.organization = create_test_organization(org_id='certificate-asn-org-1', name='Certificate ASN Org 1', parent_rir=cls.rir)
        cls.certificates = [
            create_test_certificate(name='Certificate ASN Parent 1', rpki_org=cls.organization),
            create_test_certificate(name='Certificate ASN Parent 2', rpki_org=cls.organization),
            create_test_certificate(name='Certificate ASN Parent 3', rpki_org=cls.organization),
        ]
        cls.asns = [
            create_test_asn(65201, rir=cls.rir),
            create_test_asn(65202, rir=cls.rir),
            create_test_asn(65203, rir=cls.rir),
        ]
        cls.certificate_asns = [
            create_test_certificate_asn(asn=cls.asns[0], certificate=cls.certificates[0]),
            create_test_certificate_asn(asn=cls.asns[1], certificate=cls.certificates[1]),
            create_test_certificate_asn(asn=cls.asns[2], certificate=cls.certificates[2]),
        ]


class ROAValidationSimulationSurfaceAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='simulation-api-org', name='Simulation API Org')
        cls.plan = create_test_roa_change_plan(
            name='Simulation API Plan',
            organization=cls.organization,
            summary_json={
                'simulation_run_id': 0,
                'simulation_plan_fingerprint': 'plan-fingerprint-123',
            },
        )
        cls.plan_item = create_test_roa_change_plan_item(
            name='Simulation API Plan Item',
            change_plan=cls.plan,
            action_type=rpki_models.ROAChangePlanAction.CREATE,
            plan_semantic='reshape',
        )
        cls.invalid_plan_item = create_test_roa_change_plan_item(
            name='Simulation API Invalid Item',
            change_plan=cls.plan,
            action_type=rpki_models.ROAChangePlanAction.WITHDRAW,
            plan_semantic='withdraw',
        )
        cls.not_found_plan_item = create_test_roa_change_plan_item(
            name='Simulation API Not Found Item',
            change_plan=cls.plan,
            action_type=rpki_models.ROAChangePlanAction.CREATE,
            plan_semantic='replace',
        )
        cls.simulation_run = create_test_roa_validation_simulation_run(
            name='Simulation API Run',
            change_plan=cls.plan,
            plan_fingerprint='plan-fingerprint-123',
            overall_approval_posture=rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
            is_current_for_plan=True,
            partially_constrained=True,
            result_count=3,
            predicted_valid_count=1,
            predicted_invalid_count=1,
            predicted_not_found_count=1,
            summary_json={
                'plan_fingerprint': 'plan-fingerprint-123',
                'approval_impact_counts': {
                    rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL: 0,
                    rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED: 1,
                    rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING: 2,
                },
                'scenario_type_counts': {
                    'authorization_broadened_requires_ack': 1,
                    'replacement_breaks_coverage': 1,
                    'withdraw_without_replacement_blocks_intended_route': 1,
                },
                'overall_approval_posture': rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
                'is_current_for_plan': True,
                'partially_constrained': True,
                'affected_intended_route_count': 1,
                'affected_collateral_route_count': 2,
                'predicted_outcome_counts': {
                    rpki_models.ROAValidationSimulationOutcome.VALID: 1,
                    rpki_models.ROAValidationSimulationOutcome.INVALID: 1,
                    rpki_models.ROAValidationSimulationOutcome.NOT_FOUND: 1,
                },
            },
        )
        cls.plan.summary_json = {
            'simulation_run_id': cls.simulation_run.pk,
            'simulation_plan_fingerprint': 'plan-fingerprint-123',
        }
        cls.plan.save(update_fields=('summary_json',))
        cls.simulation_result = create_test_roa_validation_simulation_result(
            name='Simulation API Result',
            simulation_run=cls.simulation_run,
            change_plan_item=cls.plan_item,
            outcome_type=rpki_models.ROAValidationSimulationOutcome.VALID,
            approval_impact=rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED,
            scenario_type='authorization_broadened_requires_ack',
            details_json={
                'scenario_type': 'authorization_broadened_requires_ack',
                'impact_scope': 'collateral',
                'approval_impact': rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED,
                'plan_fingerprint': 'plan-fingerprint-123',
                'operator_message': 'The intended route remains covered, but the plan broadens authorization.',
                'why_it_matters': 'A broader ROA may validate routes that were not intended to be authorized.',
                'operator_action': 'Acknowledge the broader authorization risk before approval.',
                'before_coverage': {'covers_intended_route': True},
                'after_coverage': {'covers_intended_route': True},
                'affected_prefixes': ['10.0.0.0/24'],
                'affected_origin_asns': [64496],
                'collateral_impact_count': 2,
                'transition_risk': 'medium',
                'explanation': 'Replacement remains valid but broadens authorization scope.',
            },
        )
        cls.invalid_simulation_result = create_test_roa_validation_simulation_result(
            name='Simulation API Invalid Result',
            simulation_run=cls.simulation_run,
            change_plan_item=cls.invalid_plan_item,
            outcome_type=rpki_models.ROAValidationSimulationOutcome.INVALID,
            approval_impact=rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
            scenario_type='replacement_breaks_coverage',
            details_json={
                'scenario_type': 'replacement_breaks_coverage',
                'impact_scope': 'intended',
                'approval_impact': rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
                'plan_fingerprint': 'plan-fingerprint-123',
                'operator_message': 'The replacement would invalidate the intended route.',
                'affected_prefixes': ['10.0.1.0/24'],
                'affected_origin_asns': [64497],
            },
        )
        cls.not_found_simulation_result = create_test_roa_validation_simulation_result(
            name='Simulation API Not Found Result',
            simulation_run=cls.simulation_run,
            change_plan_item=cls.not_found_plan_item,
            outcome_type=rpki_models.ROAValidationSimulationOutcome.NOT_FOUND,
            approval_impact=rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
            scenario_type='withdraw_without_replacement_blocks_intended_route',
            details_json={
                'scenario_type': 'withdraw_without_replacement_blocks_intended_route',
                'impact_scope': 'intended',
                'approval_impact': rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
                'plan_fingerprint': 'plan-fingerprint-123',
                'operator_message': 'The withdrawal would leave the route without VRP coverage.',
                'affected_prefixes': ['10.0.2.0/24'],
                'affected_origin_asns': [64498],
            },
        )

    def test_roa_change_plan_detail_exposes_latest_simulation_posture(self):
        self.add_permissions(
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_roachangeplanitem',
            'netbox_rpki.view_roavalidationsimulationrun',
            'netbox_rpki.view_roavalidationsimulationresult',
        )
        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:roachangeplan-detail', kwargs={'pk': self.plan.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(
            response.data['latest_simulation_posture']['overall_approval_posture'],
            rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
        )
        self.assertTrue(response.data['latest_simulation_posture']['is_current_for_plan'])
        self.assertTrue(response.data['latest_simulation_posture']['partially_constrained'])
        self.assertEqual(
            response.data['latest_simulation_summary']['approval_impact_counts'][
                rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED
            ],
            1,
        )
        self.assertEqual(
            response.data['latest_simulation_run']['normalized_summary']['scenario_type_counts'],
            {
                'authorization_broadened_requires_ack': 1,
                'replacement_breaks_coverage': 1,
                'withdraw_without_replacement_blocks_intended_route': 1,
            },
        )
        self.assertEqual(
            response.data['latest_simulation_summary'],
            response.data['latest_simulation_run']['normalized_summary'],
        )
        self.assertEqual(
            response.data['latest_simulation_posture']['approval_impact_counts'],
            response.data['latest_simulation_summary']['approval_impact_counts'],
        )
        self.assertEqual(
            response.data['latest_simulation_posture']['scenario_type_counts'],
            response.data['latest_simulation_summary']['scenario_type_counts'],
        )
        self.assertEqual(
            response.data['latest_simulation_review']['grouped_results']['valid']['results'][0]['affected_prefixes'],
            ['10.0.0.0/24'],
        )
        self.assertEqual(
            response.data['latest_simulation_review']['grouped_results']['invalid']['results'][0]['affected_origin_asns'],
            ['64497'],
        )
        self.assertEqual(
            response.data['latest_simulation_review']['grouped_results']['not_found']['results'][0]['change_plan_item']['id'],
            self.not_found_plan_item.pk,
        )

    def test_simulation_run_detail_exposes_normalized_summary_fields(self):
        self.add_permissions('netbox_rpki.view_roavalidationsimulationrun')
        response = self.client.get(
            reverse(
                'plugins-api:netbox_rpki-api:roavalidationsimulationrun-detail',
                kwargs={'pk': self.simulation_run.pk},
            ),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['plan_fingerprint'], 'plan-fingerprint-123')
        self.assertEqual(
            response.data['overall_approval_posture'],
            rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
        )
        self.assertTrue(response.data['is_current_for_plan'])
        self.assertTrue(response.data['partially_constrained'])
        self.assertEqual(
            response.data['approval_impact_counts'][
                rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED
            ],
            1,
        )
        self.assertEqual(response.data['affected_collateral_route_count'], 2)

    def test_simulation_result_detail_exposes_normalized_explanation_fields(self):
        self.add_permissions('netbox_rpki.view_roavalidationsimulationresult')
        response = self.client.get(
            reverse(
                'plugins-api:netbox_rpki-api:roavalidationsimulationresult-detail',
                kwargs={'pk': self.simulation_result.pk},
            ),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(
            response.data['approval_impact'],
            rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED,
        )
        self.assertEqual(response.data['scenario_type'], 'authorization_broadened_requires_ack')
        self.assertEqual(response.data['impact_scope'], 'collateral')
        self.assertEqual(
            response.data['operator_action'],
            'Acknowledge the broader authorization risk before approval.',
        )
        self.assertEqual(response.data['affected_prefixes'], ['10.0.0.0/24'])
        self.assertEqual(response.data['affected_origin_asns'], [64496])
        self.assertEqual(response.data['collateral_impact_count'], 2)


class ROAChangePlanSimulationSummaryAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='simulation-summary-api-org', name='Simulation Summary API Org')

        cls.missing_plan = create_test_roa_change_plan(
            name='Simulation Missing Plan',
            organization=cls.organization,
        )

        cls.stale_plan = create_test_roa_change_plan(
            name='Simulation Stale Plan',
            organization=cls.organization,
            summary_json={'simulation_run_id': 0},
        )
        cls.stale_run = create_test_roa_validation_simulation_run(
            name='Simulation Stale Run',
            change_plan=cls.stale_plan,
            plan_fingerprint='stale-fingerprint',
            overall_approval_posture=rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL,
            is_current_for_plan=False,
            summary_json={
                'plan_fingerprint': 'stale-fingerprint',
                'approval_impact_counts': {
                    rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL: 1,
                    rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED: 0,
                    rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING: 0,
                },
                'scenario_type_counts': {'no_material_validation_change': 1},
                'overall_approval_posture': rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL,
                'is_current_for_plan': False,
                'partially_constrained': False,
            },
        )
        cls.stale_plan.summary_json = {'simulation_run_id': cls.stale_run.pk}
        cls.stale_plan.save(update_fields=('summary_json',))

        cls.blocking_plan = create_test_roa_change_plan(
            name='Simulation Blocking Plan',
            organization=cls.organization,
            summary_json={'simulation_run_id': 0},
        )
        cls.blocking_run = create_test_roa_validation_simulation_run(
            name='Simulation Blocking Run',
            change_plan=cls.blocking_plan,
            plan_fingerprint=_build_plan_fingerprint(cls.blocking_plan),
            overall_approval_posture=rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
            is_current_for_plan=True,
            summary_json={
                'plan_fingerprint': _build_plan_fingerprint(cls.blocking_plan),
                'approval_impact_counts': {
                    rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL: 0,
                    rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED: 0,
                    rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING: 2,
                },
                'scenario_type_counts': {'withdraw_without_replacement_blocks_intended_route': 2},
                'overall_approval_posture': rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
                'is_current_for_plan': True,
                'partially_constrained': False,
            },
        )
        cls.blocking_plan.summary_json = {'simulation_run_id': cls.blocking_run.pk}
        cls.blocking_plan.save(update_fields=('summary_json',))

        cls.ack_plan = create_test_roa_change_plan(
            name='Simulation Ack Plan',
            organization=cls.organization,
            summary_json={'simulation_run_id': 0},
        )
        cls.ack_run = create_test_roa_validation_simulation_run(
            name='Simulation Ack Run',
            change_plan=cls.ack_plan,
            plan_fingerprint=_build_plan_fingerprint(cls.ack_plan),
            overall_approval_posture=rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED,
            is_current_for_plan=True,
            partially_constrained=True,
            summary_json={
                'plan_fingerprint': _build_plan_fingerprint(cls.ack_plan),
                'approval_impact_counts': {
                    rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL: 0,
                    rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED: 1,
                    rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING: 0,
                },
                'scenario_type_counts': {'insufficient_state_requires_review': 1},
                'overall_approval_posture': rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED,
                'is_current_for_plan': True,
                'partially_constrained': True,
            },
        )
        cls.ack_plan.summary_json = {'simulation_run_id': cls.ack_run.pk}
        cls.ack_plan.save(update_fields=('summary_json',))

        cls.info_plan = create_test_roa_change_plan(
            name='Simulation Informational Plan',
            organization=cls.organization,
            summary_json={'simulation_run_id': 0},
        )
        cls.info_run = create_test_roa_validation_simulation_run(
            name='Simulation Informational Run',
            change_plan=cls.info_plan,
            plan_fingerprint=_build_plan_fingerprint(cls.info_plan),
            overall_approval_posture=rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL,
            is_current_for_plan=True,
            summary_json={
                'plan_fingerprint': _build_plan_fingerprint(cls.info_plan),
                'approval_impact_counts': {
                    rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL: 3,
                    rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED: 0,
                    rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING: 0,
                },
                'scenario_type_counts': {'no_material_validation_change': 3},
                'overall_approval_posture': rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL,
                'is_current_for_plan': True,
                'partially_constrained': False,
            },
        )
        cls.info_plan.summary_json = {'simulation_run_id': cls.info_run.pk}
        cls.info_plan.save(update_fields=('summary_json',))

    def test_roa_change_plan_summary_rolls_up_simulation_posture(self):
        self.add_permissions('netbox_rpki.view_roachangeplan')

        response = self.client.get(
            reverse('plugins-api:netbox_rpki-api:roachangeplan-summary'),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['total_plans'], 5)
        self.assertEqual(response.data['simulated_plan_count'], 4)
        self.assertEqual(response.data['simulation_current_plan_count'], 3)
        self.assertEqual(response.data['simulation_missing_count'], 1)
        self.assertEqual(response.data['simulation_stale_count'], 1)
        self.assertEqual(response.data['simulation_blocking_plan_count'], 1)
        self.assertEqual(response.data['simulation_acknowledgement_required_plan_count'], 1)
        self.assertEqual(response.data['simulation_informational_plan_count'], 1)
        self.assertEqual(response.data['simulation_partially_constrained_plan_count'], 1)
        self.assertEqual(response.data['simulation_status_counts']['missing'], 1)
        self.assertEqual(response.data['simulation_status_counts']['stale'], 1)
        self.assertEqual(
            response.data['simulation_status_counts'][rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING],
            1,
        )
        self.assertEqual(
            response.data['simulation_approval_impact_totals'][rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING],
            2,
        )
        self.assertEqual(
            response.data['simulation_approval_impact_totals'][
                rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED
            ],
            1,
        )

