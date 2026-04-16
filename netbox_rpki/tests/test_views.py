import csv
import json
from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.formats import date_format
from django.utils import timezone

from netbox_rpki import filtersets, forms, tables, views
from netbox_rpki import models as rpki_models
from netbox_rpki.models import Certificate, CertificateAsn, CertificatePrefix, Organization, Roa, RoaPrefix
from netbox_rpki.object_registry import SIMPLE_DETAIL_VIEW_OBJECT_SPECS, VIEW_OBJECT_SPECS, get_object_spec
from netbox_rpki.services import create_roa_change_plan, derive_roa_intents, reconcile_roa_intents
from netbox_rpki.services.lifecycle_reporting import (
    LIFECYCLE_EXPORT_SCHEMA_VERSION,
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY,
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE,
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY,
    LIFECYCLE_EXPORT_KIND_PROVIDER_PUBLICATION_DIFF_TIMELINE,
    get_lifecycle_export_filename,
)
from netbox_rpki.services.provider_sync_contract import build_provider_sync_summary
from netbox_rpki.tests.registry_scenarios import _build_instance_for_spec
from netbox_rpki.tests.base import PluginViewTestCase
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa,
    create_test_aspa_change_plan,
    create_test_aspa_change_plan_item,
    create_test_aspa_intent,
    create_test_aspa_provider,
    create_test_bulk_intent_run,
    create_test_certificate,
    create_test_certificate_asn,
    create_test_certificate_prefix,
    create_test_certificate_revocation_list,
    create_test_end_entity_certificate,
    create_test_external_management_exception,
    create_test_imported_roa_authorization,
    create_test_irr_change_plan,
    create_test_irr_change_plan_item,
    create_test_irr_coordination_run,
    create_test_irr_source,
    create_test_irr_write_execution,
    create_test_intent_derivation_run,
    create_test_lifecycle_health_policy,
    create_test_organization,
    create_test_object_validation_result,
    create_test_prefix,
    create_test_publication_point,
    create_test_provider_snapshot_diff,
    create_test_provider_snapshot_diff_item,
    create_test_published_roa_result,
    create_test_rir,
    create_test_imported_ca_metadata,
    create_test_imported_certificate_observation,
    create_test_imported_child_link,
    create_test_imported_parent_link,
    create_test_imported_publication_point,
    create_test_imported_resource_entitlement,
    create_test_imported_signed_object,
    create_test_manifest,
    create_test_roa,
    create_test_roa_change_plan,
    create_test_roa_change_plan_matrix,
    create_test_roa_change_plan_item,
    create_test_roa_lint_rule_config,
    create_test_aspa_reconciliation_run,
    create_test_roa_intent,
    create_test_roa_intent_match,
    create_test_roa_intent_override,
    create_test_roa_intent_result,
    create_test_roa_reconciliation_run,
    create_test_roa_prefix,
    create_test_roa_validation_simulation_result,
    create_test_roa_validation_simulation_run,
    create_test_routing_intent_profile,
    create_test_routing_intent_exception,
    create_test_routing_intent_rule,
    create_test_routing_intent_template,
    create_test_routing_intent_template_binding,
    create_test_routing_intent_template_rule,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_router_certificate,
    create_test_telemetry_run,
    create_test_telemetry_source,
    create_test_bgp_path_observation,
    create_test_validated_aspa_payload,
    create_test_validated_roa_payload,
    create_test_signed_object,
    create_test_validator_instance,
    create_test_trust_anchor,
    create_test_validation_run,
)
from utilities.testing.utils import post_data
from unittest.mock import patch


def current_ack_required_finding_ids(plan):
    lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
    if lint_run is None:
        return []
    return [
        finding.pk
        for finding in lint_run.findings.all()
        if finding.details_json.get('approval_impact') == 'acknowledgement_required'
        and not finding.details_json.get('suppressed')
    ]


class ViewRegistrySmokeTestCase(SimpleTestCase):
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
            instance = _build_instance_for_spec(spec, token=f'{spec.registry_key}-detail-view')
            self.add_permissions(f'{spec.model._meta.app_label}.view_{spec.model._meta.model_name}')

            response = self.client.get(instance.get_absolute_url())

            with self.subTest(object_key=spec.registry_key):
                self.assertHttpStatus(response, 200)
                self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')


class GeneratedListViewActionLinkTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-view-org', name='Provider View Org')
        cls.provider_account = create_test_provider_account(
            name='Provider View Account',
            organization=cls.organization,
            org_handle='ORG-VIEW',
        )

    def test_provider_account_list_renders_add_link(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.add_rpkiprovideraccount')

        response = self.client.get(reverse('plugins:netbox_rpki:provideraccount_list'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, reverse('plugins:netbox_rpki:provideraccount_add'))
        self.assertNotContains(response, '/plugins/netbox_rpki/provideraccounts/None')

    def test_read_only_generated_lists_expose_only_export_and_changelog(self):
        for registry_key in ('roachangeplanitem', 'providersyncrun', 'publishedroaresult'):
            spec = get_object_spec(registry_key)
            instance = _build_instance_for_spec(spec, token=f'{registry_key}-list-actions')
            self.add_permissions(
                f'netbox_rpki.view_{spec.model._meta.model_name}',
                f'netbox_rpki.add_{spec.model._meta.model_name}',
                f'netbox_rpki.change_{spec.model._meta.model_name}',
                f'netbox_rpki.delete_{spec.model._meta.model_name}',
            )

            response = self.client.get(reverse(spec.list_url_name))

            with self.subTest(object_key=registry_key, instance=instance.pk):
                self.assertHttpStatus(response, 200)
                self.assertEqual([action.name for action in response.context['actions']], ['export'])
                self.assertEqual(
                    tuple(response.context['table'].base_columns['actions'].actions.keys()),
                    ('changelog',),
                )
                self.assertNotContains(response, '/None')


class LifecycleExportFormatterViewTestCase(TestCase):
    def test_lifecycle_export_filename_uses_kind_and_provider_account_slug(self):
        provider_account = create_test_provider_account(
            name='Lifecycle Export View Account',
            organization=create_test_organization(org_id='lifecycle-export-view-org', name='Lifecycle Export View Org'),
            org_handle='ORG-LIFECYCLE-EXPORT-VIEW',
        )

        self.assertEqual(
            get_lifecycle_export_filename(
                LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY,
                'json',
                provider_account=provider_account,
            ),
            f'provider-account-{provider_account.pk}-lifecycle-export-view-account-provider-account-lifecycle-summary.json',
        )
        self.assertEqual(
            get_lifecycle_export_filename(
                LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE,
                'csv',
                provider_account=provider_account,
            ),
            f'provider-account-{provider_account.pk}-lifecycle-export-view-account-provider-account-timeline.csv',
        )
        self.assertEqual(
            get_lifecycle_export_filename(
                LIFECYCLE_EXPORT_KIND_PROVIDER_PUBLICATION_DIFF_TIMELINE,
                'csv',
            ),
            'all-provider-accounts-provider-publication-diff-timeline.csv',
        )


class LifecycleExportViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='lifecycle-export-ui-org', name='Lifecycle Export UI Org')
        cls.provider_account = create_test_provider_account(
            name='Lifecycle Export UI Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='export-ui-ca',
            org_handle='ORG-LIFECYCLE-EXPORT-UI',
            last_successful_sync=timezone.now() - timedelta(hours=3),
        )
        cls.base_snapshot = create_test_provider_snapshot(
            name='Lifecycle Export UI Base Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            fetched_at=timezone.now() - timedelta(days=2),
            completed_at=timezone.now() - timedelta(days=2, minutes=5),
        )
        cls.comparison_snapshot = create_test_provider_snapshot(
            name='Lifecycle Export UI Comparison Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            fetched_at=timezone.now() - timedelta(days=1),
            completed_at=timezone.now() - timedelta(days=1, minutes=5),
        )
        cls.snapshot_diff = create_test_provider_snapshot_diff(
            name='Lifecycle Export UI Diff',
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

    def test_provider_account_detail_shows_export_buttons(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.change_rpkiprovideraccount')

        response = self.client.get(self.provider_account.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, reverse('plugins:netbox_rpki:provideraccount_export_lifecycle', kwargs={'pk': self.provider_account.pk}) + '?format=json')
        self.assertContains(response, reverse('plugins:netbox_rpki:provideraccount_export_lifecycle', kwargs={'pk': self.provider_account.pk}) + '?format=csv')
        self.assertContains(response, reverse('plugins:netbox_rpki:provideraccount_export_timeline', kwargs={'pk': self.provider_account.pk}) + '?format=json')
        self.assertContains(response, reverse('plugins:netbox_rpki:provideraccount_export_timeline', kwargs={'pk': self.provider_account.pk}) + '?format=csv')

    def test_provider_account_lifecycle_export_json_has_envelope(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount')

        response = self.client.get(
            reverse('plugins:netbox_rpki:provideraccount_export_lifecycle', kwargs={'pk': self.provider_account.pk}),
            {'format': 'json'},
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="{get_lifecycle_export_filename(LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY, "json", provider_account=self.provider_account)}"',
        )
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['export_schema_version'], LIFECYCLE_EXPORT_SCHEMA_VERSION)
        self.assertEqual(payload['kind'], LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY)
        self.assertEqual(payload['data']['provider_account_id'], self.provider_account.pk)

    def test_provider_account_timeline_export_csv_has_stable_headers(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
        )

        response = self.client.get(
            reverse('plugins:netbox_rpki:provideraccount_export_timeline', kwargs={'pk': self.provider_account.pk}),
            {'format': 'csv'},
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

    def test_provider_account_timeline_export_respects_visibility_filters(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount')

        response = self.client.get(
            reverse('plugins:netbox_rpki:provideraccount_export_timeline', kwargs={'pk': self.provider_account.pk}),
            {'format': 'json'},
        )

        self.assertHttpStatus(response, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['data']['item_count'], 0)
        self.assertEqual(payload['data']['items'], [])

    def test_operations_dashboard_export_uses_shared_summary_contract(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
            'netbox_rpki.view_roaobject',
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.view_routingintentexception',
            'netbox_rpki.view_externalmanagementexception',
            'netbox_rpki.view_bulkintentrun',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_aspareconciliationrun',
            'netbox_rpki.view_aspachangeplan',
            'netbox_rpki.view_validatorinstance',
            'netbox_rpki.view_validationrun',
            'netbox_rpki.view_telemetrysource',
            'netbox_rpki.view_irrsource',
            'netbox_rpki.view_irrcoordinationrun',
            'netbox_rpki.view_irrchangeplan',
            'netbox_rpki.view_irrwriteexecution',
        )

        response = self.client.get(reverse('plugins:netbox_rpki:operations_export'), {'format': 'json'})

        self.assertHttpStatus(response, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['export_schema_version'], LIFECYCLE_EXPORT_SCHEMA_VERSION)
        self.assertEqual(payload['kind'], LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY)
        self.assertEqual(payload['data']['total_accounts'], 1)
        self.assertEqual(payload['data']['accounts'][0]['provider_account_id'], self.provider_account.pk)


class ProviderAccountSyncViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-sync-ui-org', name='Provider Sync UI Org')
        cls.provider_account = create_test_provider_account(
            name='Provider Sync UI Account',
            organization=cls.organization,
            org_handle='ORG-SYNC-UI',
        )
        cls.disabled_provider_account = create_test_provider_account(
            name='Provider Sync Disabled UI Account',
            organization=cls.organization,
            org_handle='ORG-SYNC-UI-DISABLED',
            sync_enabled=False,
        )

    def test_provider_account_detail_shows_sync_button_when_enabled(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.change_rpkiprovideraccount')

        response = self.client.get(self.provider_account.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, reverse('plugins:netbox_rpki:provideraccount_sync', kwargs={'pk': self.provider_account.pk}))

    def test_provider_account_detail_hides_sync_button_when_disabled(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.change_rpkiprovideraccount')

        response = self.client.get(self.disabled_provider_account.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertNotContains(response, reverse('plugins:netbox_rpki:provideraccount_sync', kwargs={'pk': self.disabled_provider_account.pk}))

    def test_provider_account_sync_view_renders_confirmation(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.change_rpkiprovideraccount')

        response = self.client.get(reverse('plugins:netbox_rpki:provideraccount_sync', kwargs={'pk': self.provider_account.pk}))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Sync Provider Account')
        self.assertContains(response, self.provider_account.name)

    def test_provider_account_sync_view_enqueues_job(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.change_rpkiprovideraccount')

        class StubJob:
            pk = 778
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/778/'

        with patch(
            'netbox_rpki.views.SyncProviderAccountJob.enqueue_for_provider_account',
            return_value=(StubJob(), True),
        ) as enqueue_mock:
            response = self.client.post(
                reverse('plugins:netbox_rpki:provideraccount_sync', kwargs={'pk': self.provider_account.pk}),
                {'confirm': True},
            )

        self.assertRedirects(response, self.provider_account.get_absolute_url())
        enqueue_mock.assert_called_once_with(self.provider_account, user=self.user)

    def test_provider_account_sync_view_does_not_enqueue_when_disabled(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.change_rpkiprovideraccount')

        with patch('netbox_rpki.views.SyncProviderAccountJob.enqueue_for_provider_account') as enqueue_mock:
            response = self.client.post(
                reverse('plugins:netbox_rpki:provideraccount_sync', kwargs={'pk': self.disabled_provider_account.pk}),
                {'confirm': True},
            )

        self.assertRedirects(response, self.disabled_provider_account.get_absolute_url())
        enqueue_mock.assert_not_called()

    def test_provider_account_sync_view_reuses_existing_job(self):
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.change_rpkiprovideraccount')

        class StubJob:
            pk = 779
            status = 'pending'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/779/'

        with patch(
            'netbox_rpki.views.SyncProviderAccountJob.enqueue_for_provider_account',
            return_value=(StubJob(), False),
        ):
            response = self.client.post(
                reverse('plugins:netbox_rpki:provideraccount_sync', kwargs={'pk': self.provider_account.pk}),
                {'confirm': True},
            )

        self.assertRedirects(response, self.provider_account.get_absolute_url())

    def test_provider_account_detail_shows_sync_health(self):
        stale_provider_account = create_test_provider_account(
            name='Provider Sync Stale UI Account',
            organization=self.organization,
            org_handle='ORG-SYNC-UI-STALE',
            sync_interval=60,
            last_successful_sync=timezone.now() - timedelta(hours=4),
            last_sync_status='completed',
        )
        self.add_permissions('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.change_rpkiprovideraccount')

        response = self.client.get(stale_provider_account.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Sync Health')
        self.assertContains(response, 'Stale')

    def test_provider_account_detail_shows_arin_transport_and_rollup_capability_reason(self):
        provider_account = create_test_provider_account(
            name='Provider Sync ARIN OT&E UI Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            transport=rpki_models.ProviderSyncTransport.OTE,
            org_handle='ORG-SYNC-UI-ARIN-OTE',
        )
        provider_account.last_sync_summary_json = build_provider_sync_summary(
            provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            family_summaries={},
        )
        provider_account.save(update_fields=['last_sync_summary_json'])

        self.add_permissions('netbox_rpki.view_rpkiprovideraccount', 'netbox_rpki.change_rpkiprovideraccount')

        response = self.client.get(provider_account.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Transport')
        self.assertContains(response, 'ote')
        self.assertContains(response, 'Last Sync Summary')
        self.assertContains(response, 'provider_limited')
        self.assertContains(response, 'hosted ROA authorizations only')
        self.assertContains(response, 'Lifecycle Health Timeline')
        self.assertContains(response, 'Publication Diff Timeline')


class ProviderSnapshotDetailViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-snapshot-view-org', name='Provider Snapshot View Org')
        cls.provider_account = create_test_provider_account(
            name='Provider Snapshot View Account',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-SNAPSHOT-VIEW',
            ca_handle='snapshot-view',
        )
        cls.base_snapshot = create_test_provider_snapshot(
            name='Provider Snapshot View Base',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
        )
        cls.snapshot = create_test_provider_snapshot(
            name='Provider Snapshot View Comparison',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            summary_json={'families': {'ca_metadata': {'records_imported': 1}}},
        )
        create_test_imported_roa_authorization(
            name='Provider Snapshot Imported ROA',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
        )
        create_test_imported_ca_metadata(
            name='Provider Snapshot Imported CA Metadata',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
        )
        create_test_imported_parent_link(
            name='Provider Snapshot Imported Parent Link',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
        )
        create_test_imported_child_link(
            name='Provider Snapshot Imported Child Link',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
        )
        create_test_imported_resource_entitlement(
            name='Provider Snapshot Imported Resource Entitlement',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
        )
        create_test_imported_publication_point(
            name='Provider Snapshot Imported Publication Point',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
        )
        create_test_imported_certificate_observation(
            name='Provider Snapshot Imported Certificate Observation',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
        )
        create_test_provider_snapshot_diff(
            name='Provider Snapshot View Diff',
            organization=cls.organization,
            provider_account=cls.provider_account,
            base_snapshot=cls.base_snapshot,
            comparison_snapshot=cls.snapshot,
        )

    def test_provider_snapshot_detail_shows_family_tables_and_diffs(self):
        self.add_permissions(
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
            'netbox_rpki.view_importedroaauthorization',
            'netbox_rpki.view_importedcametadata',
            'netbox_rpki.view_importedparentlink',
            'netbox_rpki.view_importedchildlink',
            'netbox_rpki.view_importedresourceentitlement',
            'netbox_rpki.view_importedpublicationpoint',
            'netbox_rpki.view_importedcertificateobservation',
        )

        response = self.client.get(self.snapshot.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Snapshot Comparison Diffs')
        self.assertContains(response, 'Imported CA Metadata')
        self.assertContains(response, 'Imported Parent Links')
        self.assertContains(response, 'Imported Child Links')
        self.assertContains(response, 'Imported Resource Entitlements')
        self.assertContains(response, 'Imported Publication Points')
        self.assertContains(response, 'Imported Certificate Observations')
        self.assertContains(response, 'Provider Snapshot View Diff')
        self.assertContains(response, 'Provider Snapshot Imported CA Metadata')


class SectionNineSurfaceDetailViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='section-nine-view-org', name='Section Nine View Org')
        cls.trust_anchor = create_test_trust_anchor(
            name='Section Nine View Trust Anchor',
            organization=cls.organization,
        )
        cls.resource_publication_point = create_test_publication_point(
            name='Section Nine View Resource Publication Point',
            organization=cls.organization,
            publication_uri='rsync://view.invalid/certs/',
        )
        cls.resource_certificate = create_test_certificate(
            name='Section Nine View Resource Certificate',
            rpki_org=cls.organization,
            trust_anchor=cls.trust_anchor,
            publication_point=cls.resource_publication_point,
        )
        cls.roa_signed_object = create_test_signed_object(
            name='Section Nine View ROA Signed Object',
            organization=cls.organization,
            object_type='roa',
            resource_certificate=cls.resource_certificate,
        )
        cls.roa = create_test_roa(
            name='Section Nine View ROA',
            origin_as=create_test_asn(65314),
            signed_by=cls.resource_certificate,
            signed_object=cls.roa_signed_object,
        )
        cls.router_ee_certificate = create_test_end_entity_certificate(
            name='Section Nine View Router EE Certificate',
            organization=cls.organization,
            resource_certificate=cls.resource_certificate,
            publication_point=cls.resource_publication_point,
            subject='CN=View Router',
            issuer='CN=View Issuer',
            serial='view-router-serial',
            ski='view-router-ski',
        )
        cls.router_certificate = create_test_router_certificate(
            name='Section Nine View Router Certificate',
            organization=cls.organization,
            resource_certificate=cls.resource_certificate,
            publication_point=cls.router_ee_certificate.publication_point,
            ee_certificate=cls.router_ee_certificate,
            asn=create_test_asn(65313),
            subject='CN=View Router',
            issuer='CN=View Issuer',
            serial='view-router-serial',
            ski='view-router-ski',
        )
        cls.crl_signed_object = create_test_signed_object(
            name='Section Nine View CRL Signed Object',
            organization=cls.organization,
            filename='section-nine-view.crl',
            object_uri='https://view.invalid/crl.crl',
            repository_uri='https://view.invalid/',
        )
        cls.certificate_revocation_list = create_test_certificate_revocation_list(
            name='Section Nine View CRL',
            organization=cls.organization,
            signed_object=cls.crl_signed_object,
            publication_uri='https://view.invalid/crl.crl',
            crl_number='42',
        )
        cls.provider_account = create_test_provider_account(
            name='Section Nine View Provider Account',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-SECTION-NINE-VIEW',
            ca_handle='section-nine-view',
        )
        cls.snapshot = create_test_provider_snapshot(
            name='Section Nine View Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
        )
        cls.authored_publication_point = create_test_publication_point(
            name='Section Nine View Authored Publication Point',
            organization=cls.organization,
            publication_uri='rsync://view.invalid/repo/',
        )
        cls.authored_signed_object = create_test_signed_object(
            name='Section Nine View Authored Signed Object',
            organization=cls.organization,
            publication_point=cls.authored_publication_point,
            object_type='manifest',
            object_uri='rsync://view.invalid/repo/example.mft',
        )
        cls.authored_manifest = create_test_manifest(
            name='Section Nine View Authored Manifest',
            signed_object=cls.authored_signed_object,
            manifest_number='manifest-9',
        )
        cls.authored_signed_object.current_manifest = cls.authored_manifest
        cls.authored_signed_object.save(update_fields=('current_manifest',))
        cls.imported_publication_point = create_test_imported_publication_point(
            name='Section Nine View Imported Publication Point',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            authored_publication_point=cls.authored_publication_point,
            publication_uri='rsync://view.invalid/repo/',
            payload_json={
                'authored_linkage': {'status': 'linked'},
                'evidence_summary': {'published_object_count': 1, 'authored_linkage_status': 'linked'},
            },
        )
        cls.imported_signed_object = create_test_imported_signed_object(
            name='Section Nine View Imported Signed Object',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            publication_point=cls.imported_publication_point,
            authored_signed_object=cls.authored_signed_object,
            signed_object_uri='rsync://view.invalid/repo/example.mft',
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
        cls.imported_certificate_observation = create_test_imported_certificate_observation(
            name='Section Nine View Imported Certificate Observation',
            organization=cls.organization,
            provider_snapshot=cls.snapshot,
            publication_point=cls.imported_publication_point,
            signed_object=cls.imported_signed_object,
            certificate_uri='rsync://view.invalid/repo/example.cer',
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
        cls.validation_run = create_test_validation_run(
            name='Section Nine View Validation Run',
        )
        cls.object_validation_result = create_test_object_validation_result(
            name='Section Nine View Object Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.authored_signed_object,
        )

    def test_certificate_revocation_list_detail_shows_signed_object_link(self):
        self.add_permissions('netbox_rpki.view_certificaterevocationlist', 'netbox_rpki.view_signedobject')

        response = self.client.get(self.certificate_revocation_list.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Signed Object')
        self.assertContains(response, self.crl_signed_object.get_absolute_url())
        self.assertContains(response, self.crl_signed_object.name)

    def test_roa_detail_shows_signed_object_link(self):
        self.add_permissions('netbox_rpki.view_roaobject', 'netbox_rpki.view_signedobject')

        response = self.client.get(self.roa.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, self.roa_signed_object.get_absolute_url())
        self.assertContains(response, self.roa_signed_object.name)

    def test_router_certificate_detail_shows_ee_certificate_link(self):
        self.add_permissions('netbox_rpki.view_routercertificate', 'netbox_rpki.view_endentitycertificate')

        response = self.client.get(self.router_certificate.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, self.router_ee_certificate.get_absolute_url())
        self.assertContains(response, self.router_ee_certificate.name)

    def test_certificate_detail_shows_trust_anchor_and_publication_point_links(self):
        self.add_permissions(
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_trustanchor',
            'netbox_rpki.view_publicationpoint',
        )

        response = self.client.get(self.resource_certificate.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Trust Anchor')
        self.assertContains(response, self.trust_anchor.get_absolute_url())
        self.assertContains(response, self.trust_anchor.name)
        self.assertContains(response, 'Publication Point')
        self.assertContains(response, self.resource_publication_point.get_absolute_url())
        self.assertContains(response, self.resource_publication_point.name)

    def test_end_entity_certificate_detail_shows_resource_certificate_and_publication_point_links(self):
        self.add_permissions(
            'netbox_rpki.view_endentitycertificate',
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_publicationpoint',
        )

        response = self.client.get(self.router_ee_certificate.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Resource Certificate')
        self.assertContains(response, self.resource_certificate.get_absolute_url())
        self.assertContains(response, self.resource_certificate.name)
        self.assertContains(response, 'Publication Point')
        self.assertContains(response, self.resource_publication_point.get_absolute_url())
        self.assertContains(response, self.resource_publication_point.name)

    def test_imported_certificate_observation_detail_shows_publication_and_signed_object_links(self):
        self.add_permissions(
            'netbox_rpki.view_importedcertificateobservation',
            'netbox_rpki.view_importedpublicationpoint',
            'netbox_rpki.view_importedsignedobject',
        )

        response = self.client.get(self.imported_certificate_observation.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Publication Point')
        self.assertContains(response, 'Signed Object')
        self.assertContains(response, 'Source Count')
        self.assertContains(response, 'Signed Object EE Certificate')
        self.assertContains(response, 'derived_from_signed_object')
        self.assertContains(response, self.imported_publication_point.get_absolute_url())
        self.assertContains(response, self.imported_signed_object.get_absolute_url())
        self.assertContains(response, self.imported_publication_point.name)
        self.assertContains(response, self.imported_signed_object.name)

    def test_imported_publication_point_detail_shows_authored_publication_point_link(self):
        self.add_permissions('netbox_rpki.view_importedpublicationpoint', 'netbox_rpki.view_publicationpoint')

        response = self.client.get(self.imported_publication_point.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Authored Publication Point')
        self.assertContains(response, 'Authored Linkage Status')
        self.assertContains(response, 'published_object_count')
        self.assertContains(response, self.authored_publication_point.get_absolute_url())
        self.assertContains(response, self.authored_publication_point.name)

    def test_imported_signed_object_detail_shows_authored_signed_object_link(self):
        self.add_permissions('netbox_rpki.view_importedsignedobject', 'netbox_rpki.view_signedobject')

        response = self.client.get(self.imported_signed_object.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Authored Signed Object')
        self.assertContains(response, 'Publication Linkage Status')
        self.assertContains(response, 'manifest')
        self.assertContains(response, self.authored_signed_object.get_absolute_url())
        self.assertContains(response, self.authored_signed_object.name)

    def test_signed_object_detail_shows_roa_extension_link(self):
        self.add_permissions('netbox_rpki.view_signedobject', 'netbox_rpki.view_roaobject')

        response = self.client.get(self.roa_signed_object.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'ROA Object')
        self.assertContains(response, self.roa.get_absolute_url())
        self.assertContains(response, self.roa.name)

    def test_signed_object_detail_shows_manifest_imported_observations_and_validation_results(self):
        self.add_permissions(
            'netbox_rpki.view_signedobject',
            'netbox_rpki.view_manifest',
            'netbox_rpki.view_importedsignedobject',
            'netbox_rpki.view_objectvalidationresult',
        )

        response = self.client.get(self.authored_signed_object.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Manifest')
        self.assertContains(response, self.authored_manifest.get_absolute_url())
        self.assertContains(response, self.authored_manifest.name)
        self.assertContains(response, 'Imported Signed Object Observations')
        self.assertContains(response, self.imported_signed_object.name)
        self.assertContains(response, 'Object Validation Results')
        self.assertContains(response, self.object_validation_result.name)


class ProviderSnapshotDiffDetailViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='provider-diff-view-org', name='Provider Diff View Org')
        cls.provider_account = create_test_provider_account(
            name='Provider Diff View Account',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-DIFF-VIEW',
            ca_handle='diff-view',
        )
        cls.base_snapshot = create_test_provider_snapshot(
            name='Provider Diff Base Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
        )
        cls.comparison_snapshot = create_test_provider_snapshot(
            name='Provider Diff Comparison Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
        )
        cls.snapshot_diff = create_test_provider_snapshot_diff(
            name='Provider Diff View',
            organization=cls.organization,
            provider_account=cls.provider_account,
            base_snapshot=cls.base_snapshot,
            comparison_snapshot=cls.comparison_snapshot,
            summary_json={
                'families': {
                    'roa_authorizations': {
                        'records_imported': 1,
                        'records_changed': 1,
                        'status': 'completed',
                    },
                },
                'totals': {'records_changed': 1, 'records_imported': 1},
            },
        )
        cls.snapshot_diff_item = create_test_provider_snapshot_diff_item(
            name='Provider Diff View Item',
            snapshot_diff=cls.snapshot_diff,
            provider_identity='provider:diff:item',
            before_state_json={'state': 'before'},
            after_state_json={'state': 'after'},
        )

    def test_provider_snapshot_diff_detail_shows_diff_items(self):
        self.add_permissions('netbox_rpki.view_providersnapshotdiff', 'netbox_rpki.view_providersnapshotdiffitem')

        response = self.client.get(self.snapshot_diff.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Family Rollups')
        self.assertContains(response, 'Provider Snapshot Diff Items')
        self.assertContains(response, self.snapshot_diff_item.name)
        self.assertContains(response, 'ROA Authorizations')
        self.assertContains(response, '1 changed')

    def test_provider_snapshot_diff_item_detail_shows_state_payloads(self):
        self.add_permissions('netbox_rpki.view_providersnapshotdiffitem', 'netbox_rpki.view_providersnapshotdiff')

        response = self.client.get(self.snapshot_diff_item.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'provider:diff:item')
        self.assertContains(response, '&quot;state&quot;: &quot;before&quot;')
        self.assertContains(response, '&quot;state&quot;: &quot;after&quot;')


class RoutingIntentTemplateBindingActionViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='binding-view-org', name='Binding View Org')
        cls.prefix = create_test_prefix('10.144.0.0/24', status='active')
        cls.origin_asn = create_test_asn(65644)
        cls.profile = create_test_routing_intent_profile(
            name='Binding View Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.prefix.pk}',
            asn_selector_query='id=999999999',
        )
        cls.template = create_test_routing_intent_template(
            name='Binding View Template',
            organization=cls.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Binding View Include',
            template=cls.template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        cls.binding = create_test_routing_intent_template_binding(
            name='Binding View Binding',
            template=cls.template,
            intent_profile=cls.profile,
            origin_asn_override=cls.origin_asn,
            prefix_selector_query=f'id={cls.prefix.pk}',
        )

    def test_binding_detail_shows_preview_and_regenerate_buttons(self):
        self.add_permissions(
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.change_routingintenttemplatebinding',
            'netbox_rpki.view_routingintentexception',
        )

        response = self.client.get(self.binding.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(
            response,
            reverse('plugins:netbox_rpki:routingintenttemplatebinding_preview', kwargs={'pk': self.binding.pk}),
        )
        self.assertContains(
            response,
            reverse('plugins:netbox_rpki:routingintenttemplatebinding_regenerate', kwargs={'pk': self.binding.pk}),
        )

    def test_binding_preview_view_renders_compiled_results(self):
        self.add_permissions(
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.change_routingintenttemplatebinding',
            'netbox_rpki.view_routingintentexception',
        )

        response = self.client.get(
            reverse('plugins:netbox_rpki:routingintenttemplatebinding_preview', kwargs={'pk': self.binding.pk})
        )

        self.assertHttpStatus(response, 200)
        self.assertTemplateUsed(response, 'netbox_rpki/routingintenttemplatebinding_preview.html')
        self.assertContains(response, 'Template Binding Preview')
        self.assertContains(response, str(self.prefix.prefix))
        self.assertContains(response, f'AS{self.origin_asn.asn}')

    def test_binding_regenerate_view_executes_pipeline_and_redirects(self):
        self.add_permissions(
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.change_routingintenttemplatebinding',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roalintrun',
        )

        response = self.client.post(
            reverse('plugins:netbox_rpki:routingintenttemplatebinding_regenerate', kwargs={'pk': self.binding.pk}),
            {'confirm': True},
        )

        self.binding.refresh_from_db()
        latest_reconciliation = self.binding.intent_profile.reconciliation_runs.order_by('-started_at', '-created').first()

        self.assertIsNotNone(latest_reconciliation)
        self.assertRedirects(response, latest_reconciliation.get_absolute_url())
        self.assertEqual(self.binding.state, rpki_models.RoutingIntentTemplateBindingState.CURRENT)


class RoutingIntentProfileActionViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='profile-view-org', name='Profile View Org')
        cls.profile = create_test_routing_intent_profile(
            name='Profile View Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        )
        cls.provider_account = create_test_provider_account(
            name='Profile View Provider',
            organization=cls.organization,
            org_handle='ORG-PROFILE-VIEW',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Profile View Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
        )

    def test_profile_detail_shows_run_button(self):
        self.add_permissions('netbox_rpki.view_routingintentprofile', 'netbox_rpki.change_routingintentprofile')

        response = self.client.get(self.profile.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(
            response,
            reverse('plugins:netbox_rpki:routingintentprofile_run', kwargs={'pk': self.profile.pk}),
        )

    def test_profile_run_view_enqueues_job(self):
        self.add_permissions('netbox_rpki.view_routingintentprofile', 'netbox_rpki.change_routingintentprofile')

        class StubJob:
            pk = 885
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/885/'

        with patch('netbox_rpki.views.RunRoutingIntentProfileJob.enqueue', return_value=StubJob()) as enqueue_mock:
            response = self.client.post(
                reverse('plugins:netbox_rpki:routingintentprofile_run', kwargs={'pk': self.profile.pk}),
                {
                    'confirm': True,
                    'comparison_scope': rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
                    'provider_snapshot': self.provider_snapshot.pk,
                },
            )

        self.assertRedirects(response, self.profile.get_absolute_url())
        enqueue_mock.assert_called_once_with(
            instance=self.profile,
            user=self.user,
            profile_pk=self.profile.pk,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot_pk=self.provider_snapshot.pk,
        )

    def test_profile_detail_hides_run_button_without_change_permission(self):
        self.add_permissions('netbox_rpki.view_routingintentprofile')

        response = self.client.get(self.profile.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertNotContains(
            response,
            reverse('plugins:netbox_rpki:routingintentprofile_run', kwargs={'pk': self.profile.pk}),
        )


class RoutingIntentExceptionActionViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='exception-view-org', name='Exception View Org')
        cls.profile = create_test_routing_intent_profile(
            name='Exception View Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        )
        cls.exception = create_test_routing_intent_exception(
            name='Exception View Exception',
            organization=cls.organization,
            intent_profile=cls.profile,
        )

    def test_exception_detail_shows_approve_button_and_lifecycle_status(self):
        self.add_permissions('netbox_rpki.view_routingintentexception', 'netbox_rpki.change_routingintentexception')

        response = self.client.get(self.exception.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Pending Approval')
        self.assertContains(
            response,
            reverse('plugins:netbox_rpki:routingintentexception_approve', kwargs={'pk': self.exception.pk}),
        )

    def test_exception_approve_view_sets_actor_and_timestamp(self):
        self.add_permissions('netbox_rpki.view_routingintentexception', 'netbox_rpki.change_routingintentexception')

        response = self.client.post(
            reverse('plugins:netbox_rpki:routingintentexception_approve', kwargs={'pk': self.exception.pk}),
            {'confirm': True},
        )

        self.assertRedirects(response, self.exception.get_absolute_url())
        self.exception.refresh_from_db()
        self.assertEqual(self.exception.approved_by, self.user.username)
        self.assertIsNotNone(self.exception.approved_at)


class DelegatedPublicationWorkflowActionViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='delegated-workflow-view-org',
            name='Delegated Workflow View Org',
        )
        cls.provider_account = create_test_provider_account(
            name='Delegated Workflow View Provider',
            organization=cls.organization,
            org_handle='ORG-DELEGATED-VIEW',
        )
        cls.entity = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='Delegated Workflow View Entity',
            organization=cls.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.DOWNSTREAM,
        )
        cls.relationship = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='Delegated Workflow View Relationship',
            organization=cls.organization,
            delegated_entity=cls.entity,
            provider_account=cls.provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        cls.workflow = rpki_models.DelegatedPublicationWorkflow.objects.create(
            name='Delegated Workflow View Workflow',
            organization=cls.organization,
            managed_relationship=cls.relationship,
            child_ca_handle='delegated-child-view',
            publication_server_uri='https://publication.example.invalid/view/',
            status=rpki_models.DelegatedPublicationWorkflowStatus.ACTIVE,
            requires_approval=True,
        )

    def test_workflow_detail_shows_approve_button_and_summary(self):
        self.add_permissions(
            'netbox_rpki.view_delegatedpublicationworkflow',
            'netbox_rpki.change_delegatedpublicationworkflow',
        )

        response = self.client.get(self.workflow.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Workflow Summary')
        self.assertContains(response, 'awaiting_approval')
        self.assertContains(
            response,
            reverse('plugins:netbox_rpki:delegatedpublicationworkflow_approve', kwargs={'pk': self.workflow.pk}),
        )

    def test_workflow_approve_view_sets_actor_and_timestamp(self):
        self.add_permissions(
            'netbox_rpki.view_delegatedpublicationworkflow',
            'netbox_rpki.change_delegatedpublicationworkflow',
        )

        response = self.client.post(
            reverse('plugins:netbox_rpki:delegatedpublicationworkflow_approve', kwargs={'pk': self.workflow.pk}),
            {'confirm': True},
        )

        self.assertRedirects(response, self.workflow.get_absolute_url())
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.approved_by, self.user.username)
        self.assertIsNotNone(self.workflow.approved_at)


class OrganizationAspaReconciliationViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='organization-aspa-ui', name='Organization ASPA UI')
        cls.customer_as = create_test_asn(65410)
        cls.provider_as = create_test_asn(65411)
        create_test_aspa_intent(
            name='Organization ASPA Intent',
            organization=cls.organization,
            customer_as=cls.customer_as,
            provider_as=cls.provider_as,
        )
        cls.aspa_change_plan = create_test_aspa_change_plan(
            name='Organization ASPA Change Plan',
            organization=cls.organization,
        )

    def test_organization_detail_shows_aspa_sections_and_action(self):
        self.add_permissions(
            'netbox_rpki.view_organization',
            'netbox_rpki.view_aspaintent',
            'netbox_rpki.view_aspareconciliationrun',
            'netbox_rpki.view_aspachangeplan',
            'netbox_rpki.change_organization',
        )

        response = self.client.get(self.organization.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Run ASPA Reconciliation')
        self.assertContains(
            response,
            reverse('plugins:netbox_rpki:organization_run_aspa_reconciliation', kwargs={'pk': self.organization.pk}),
        )
        self.assertContains(response, 'ASPA Intents')
        self.assertContains(response, 'ASPA Reconciliation Runs')
        self.assertContains(response, 'ASPA Change Plans')
        self.assertContains(response, 'Organization ASPA Intent')
        self.assertContains(response, 'Organization ASPA Change Plan')

    def test_organization_aspa_reconciliation_view_renders_confirmation(self):
        self.add_permissions('netbox_rpki.view_organization', 'netbox_rpki.change_organization')

        response = self.client.get(
            reverse('plugins:netbox_rpki:organization_run_aspa_reconciliation', kwargs={'pk': self.organization.pk})
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Run ASPA Reconciliation')
        self.assertContains(response, self.organization.name)

    def test_organization_aspa_reconciliation_view_enqueues_job(self):
        self.add_permissions('netbox_rpki.view_organization', 'netbox_rpki.change_organization')

        class StubJob:
            pk = 882
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/882/'

        with patch(
            'netbox_rpki.views.RunAspaReconciliationJob.enqueue_for_organization',
            return_value=(StubJob(), True),
        ) as enqueue_mock:
            response = self.client.post(
                reverse('plugins:netbox_rpki:organization_run_aspa_reconciliation', kwargs={'pk': self.organization.pk}),
                {'confirm': True},
            )

        self.assertRedirects(response, self.organization.get_absolute_url())
        enqueue_mock.assert_called_once_with(self.organization, user=self.user)


class OrganizationBulkIntentRunViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='organization-bulk-ui', name='Organization Bulk UI')
        cls.prefix = create_test_prefix('10.86.0.0/24', status='active')
        cls.origin_asn = create_test_asn(65412)
        cls.profile = create_test_routing_intent_profile(
            name='Organization Bulk UI Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.prefix.pk}',
            asn_selector_query=f'id={cls.origin_asn.pk}',
        )
        cls.template = create_test_routing_intent_template(
            name='Organization Bulk UI Template',
            organization=cls.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Organization Bulk UI Include',
            template=cls.template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        cls.binding = create_test_routing_intent_template_binding(
            name='Organization Bulk UI Binding',
            template=cls.template,
            intent_profile=cls.profile,
            origin_asn_override=cls.origin_asn,
            prefix_selector_query=f'id={cls.prefix.pk}',
        )
        cls.bulk_run = rpki_models.BulkIntentRun.objects.create(
            name='Organization Bulk UI Run',
            organization=cls.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            target_mode=rpki_models.BulkIntentTargetMode.BINDINGS,
        )

    def test_organization_detail_shows_bulk_intent_run_action(self):
        self.add_permissions('netbox_rpki.view_organization', 'netbox_rpki.change_organization')

        response = self.client.get(self.organization.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Create Bulk Intent Run')
        self.assertContains(
            response,
            reverse('plugins:netbox_rpki:organization_create_bulk_intent_run', kwargs={'pk': self.organization.pk}),
        )

    def test_organization_bulk_intent_run_view_renders_form(self):
        self.add_permissions('netbox_rpki.view_organization', 'netbox_rpki.change_organization')

        response = self.client.get(
            reverse('plugins:netbox_rpki:organization_create_bulk_intent_run', kwargs={'pk': self.organization.pk})
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Create Bulk Intent Run')
        self.assertContains(response, self.profile.name)
        self.assertContains(response, self.binding.name)

    def test_organization_bulk_intent_run_view_enqueues_job_and_redirects(self):
        self.add_permissions(
            'netbox_rpki.view_organization',
            'netbox_rpki.change_organization',
        )

        class StubJob:
            pk = 883
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/883/'

        with patch(
            'netbox_rpki.views.RunBulkRoutingIntentJob.enqueue_for_organization',
            return_value=(StubJob(), True),
        ) as enqueue_mock:
            response = self.client.post(
                reverse('plugins:netbox_rpki:organization_create_bulk_intent_run', kwargs={'pk': self.organization.pk}),
                {
                    'confirm': True,
                    'run_name': 'UI Bulk Run',
                    'profiles': [self.profile.pk],
                    'bindings': [self.binding.pk],
                    'create_change_plans': 'on',
                    'comparison_scope': rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
                },
            )

        self.assertRedirects(response, self.organization.get_absolute_url())
        enqueue_mock.assert_called_once_with(
            organization=self.organization,
            profiles=(self.profile,),
            bindings=(self.binding,),
            comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
            provider_snapshot=None,
            create_change_plans=True,
            run_name='UI Bulk Run',
            user=self.user,
        )


class AspaDetailViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='aspa-view-org', name='ASPA View Org')
        cls.customer_as = create_test_asn(65300)
        cls.provider_as = create_test_asn(65301)
        cls.aspa = create_test_aspa(
            name='ASPA Detail Object',
            organization=cls.organization,
            customer_as=cls.customer_as,
        )
        cls.provider_authorization = create_test_aspa_provider(
            aspa=cls.aspa,
            provider_as=cls.provider_as,
        )
        cls.validated_payload = create_test_validated_aspa_payload(
            name='Validated ASPA Payload Detail',
            aspa=cls.aspa,
            customer_as=cls.customer_as,
            provider_as=cls.provider_as,
        )

    def test_aspa_detail_view_shows_provider_authorizations_and_validated_payloads(self):
        self.add_permissions('netbox_rpki.view_aspa', 'netbox_rpki.view_validatedaspapayload')

        response = self.client.get(self.aspa.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Authorized Provider ASNs')
        self.assertContains(response, str(self.provider_authorization.provider_as))
        self.assertContains(response, 'Validated ASPA Payloads')
        self.assertContains(response, self.validated_payload.name)


class ExternalOverlayDetailViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='overlay-view-org', name='Overlay View Org')
        cls.prefix = create_test_prefix(prefix='203.0.113.0/24')
        cls.origin_as = create_test_asn(65320)
        cls.provider_as = create_test_asn(65321)
        cls.peer_as = create_test_asn(65322)

        cls.roa_signed_object = create_test_signed_object(
            name='Overlay View ROA Signed Object',
            organization=cls.organization,
            object_type=rpki_models.SignedObjectType.ROA,
            object_uri='rsync://overlay-view.invalid/roa.roa',
        )
        cls.roa = create_test_roa(
            name='Overlay View ROA',
            signed_by=cls.roa_signed_object.resource_certificate,
            signed_object=cls.roa_signed_object,
            origin_as=cls.origin_as,
        )
        create_test_roa_prefix(prefix=cls.prefix, roa=cls.roa, max_length=24)

        cls.aspa_signed_object = create_test_signed_object(
            name='Overlay View ASPA Signed Object',
            organization=cls.organization,
            object_type=rpki_models.SignedObjectType.ASPA,
            object_uri='rsync://overlay-view.invalid/customer.aspa',
        )
        cls.aspa = create_test_aspa(
            name='Overlay View ASPA',
            organization=cls.organization,
            signed_object=cls.aspa_signed_object,
            customer_as=cls.origin_as,
        )
        create_test_aspa_provider(aspa=cls.aspa, provider_as=cls.provider_as)

        cls.validation_run = create_test_validation_run(
            name='Overlay View Validation Run',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.roa_validation_result = create_test_object_validation_result(
            name='Overlay View ROA Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.roa_signed_object,
            validation_state=rpki_models.ValidationState.VALID,
            disposition=rpki_models.ValidationDisposition.ACCEPTED,
        )
        create_test_validated_roa_payload(
            name='Overlay View Validated ROA Payload',
            validation_run=cls.validation_run,
            roa=cls.roa,
            object_validation_result=cls.roa_validation_result,
            prefix=cls.prefix,
            origin_as=cls.origin_as,
            max_length=24,
        )
        cls.aspa_validation_result = create_test_object_validation_result(
            name='Overlay View ASPA Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.aspa_signed_object,
            validation_state=rpki_models.ValidationState.VALID,
            disposition=rpki_models.ValidationDisposition.ACCEPTED,
        )
        create_test_validated_aspa_payload(
            name='Overlay View Validated ASPA Payload',
            validation_run=cls.validation_run,
            aspa=cls.aspa,
            object_validation_result=cls.aspa_validation_result,
            customer_as=cls.origin_as,
            provider_as=cls.provider_as,
        )

        cls.telemetry_source = create_test_telemetry_source(
            name='Overlay View Telemetry Source',
            organization=cls.organization,
            slug='overlay-view-telemetry',
        )
        cls.telemetry_run = create_test_telemetry_run(
            name='Overlay View Telemetry Run',
            source=cls.telemetry_source,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_bgp_path_observation(
            name='Overlay View ROA Observation',
            telemetry_run=cls.telemetry_run,
            source=cls.telemetry_source,
            prefix=cls.prefix,
            observed_prefix='203.0.113.0/24',
            origin_as=cls.origin_as,
            observed_origin_asn=cls.origin_as.asn,
            peer_as=cls.peer_as,
            observed_peer_asn=cls.peer_as.asn,
            raw_as_path=f'{cls.peer_as.asn} 64510 {cls.origin_as.asn}',
            path_asns_json=[cls.peer_as.asn, 64510, cls.origin_as.asn],
        )
        create_test_bgp_path_observation(
            name='Overlay View ASPA Observation',
            telemetry_run=cls.telemetry_run,
            source=cls.telemetry_source,
            prefix=cls.prefix,
            observed_prefix='203.0.113.0/24',
            origin_as=cls.origin_as,
            observed_origin_asn=cls.origin_as.asn,
            peer_as=cls.peer_as,
            observed_peer_asn=cls.peer_as.asn,
            raw_as_path=f'{cls.peer_as.asn} {cls.provider_as.asn} {cls.origin_as.asn}',
            path_asns_json=[cls.peer_as.asn, cls.provider_as.asn, cls.origin_as.asn],
        )

        cls.provider_account = create_test_provider_account(
            name='Overlay View Provider Account',
            organization=cls.organization,
            org_handle='ORG-OVERLAY-VIEW',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Overlay View Provider Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
        )
        cls.imported_publication_point = create_test_imported_publication_point(
            name='Overlay View Imported Publication Point',
            organization=cls.organization,
            provider_snapshot=cls.provider_snapshot,
            publication_uri='rsync://overlay-view.invalid/repo/',
        )
        cls.imported_signed_object = create_test_imported_signed_object(
            name='Overlay View Imported Signed Object',
            organization=cls.organization,
            provider_snapshot=cls.provider_snapshot,
            publication_point=cls.imported_publication_point,
            authored_signed_object=cls.roa_signed_object,
            signed_object_type=rpki_models.SignedObjectType.ROA,
            signed_object_uri=cls.roa_signed_object.object_uri,
        )
        create_test_object_validation_result(
            name='Overlay View Imported Validation Result',
            validation_run=cls.validation_run,
            imported_signed_object=cls.imported_signed_object,
            validation_state=rpki_models.ValidationState.VALID,
            disposition=rpki_models.ValidationDisposition.ACCEPTED,
        )
        cls.imported_certificate_observation = create_test_imported_certificate_observation(
            name='Overlay View Imported Certificate Observation',
            organization=cls.organization,
            provider_snapshot=cls.provider_snapshot,
            publication_point=cls.imported_publication_point,
            signed_object=cls.imported_signed_object,
            signed_object_uri=cls.imported_signed_object.signed_object_uri,
        )

    def test_signed_and_imported_detail_views_show_external_overlay_summary(self):
        self.add_permissions(
            'netbox_rpki.view_signedobject',
            'netbox_rpki.view_importedsignedobject',
            'netbox_rpki.view_importedcertificateobservation',
            'netbox_rpki.view_objectvalidationresult',
        )

        signed_response = self.client.get(self.roa_signed_object.get_absolute_url())
        imported_response = self.client.get(self.imported_signed_object.get_absolute_url())
        certificate_response = self.client.get(self.imported_certificate_observation.get_absolute_url())

        self.assertHttpStatus(signed_response, 200)
        self.assertContains(signed_response, 'External Overlay Summary')
        self.assertContains(signed_response, 'latest_validator_posture')

        self.assertHttpStatus(imported_response, 200)
        self.assertContains(imported_response, 'External Overlay Summary')
        self.assertContains(imported_response, 'provider_evidence_linkage_status')

        self.assertHttpStatus(certificate_response, 200)
        self.assertContains(certificate_response, 'External Overlay Summary')
        self.assertContains(certificate_response, 'latest_telemetry_posture')

    def test_roa_and_aspa_detail_views_show_external_overlay_summary(self):
        self.add_permissions(
            'netbox_rpki.view_roaobject',
            'netbox_rpki.view_aspa',
            'netbox_rpki.view_validatedroapayload',
            'netbox_rpki.view_validatedaspapayload',
        )

        roa_response = self.client.get(self.roa.get_absolute_url())
        aspa_response = self.client.get(self.aspa.get_absolute_url())

        self.assertHttpStatus(roa_response, 200)
        self.assertContains(roa_response, 'External Overlay Summary')
        self.assertContains(roa_response, 'matched_observation_count')

        self.assertHttpStatus(aspa_response, 200)
        self.assertContains(aspa_response, 'External Overlay Summary')
        self.assertContains(aspa_response, 'supported_provider_asns')


class ValidatedPayloadDetailViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='validated-payload-view-org', name='Validated Payload View Org')
        cls.validation_run = create_test_validation_run(
            name='Validated Payload View Validation Run',
        )
        cls.roa_signing_certificate = create_test_certificate(
            name='Validated Payload View ROA Certificate',
            rpki_org=cls.organization,
        )
        cls.roa_signed_object = create_test_signed_object(
            name='Validated Payload View ROA Signed Object',
            organization=cls.organization,
            object_type='roa',
            resource_certificate=cls.roa_signing_certificate,
        )
        cls.roa = create_test_roa(
            name='Validated Payload View ROA',
            signed_by=cls.roa_signing_certificate,
            signed_object=cls.roa_signed_object,
        )
        cls.roa_object_validation_result = create_test_object_validation_result(
            name='Validated Payload View ROA Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.roa_signed_object,
        )
        cls.validated_roa_payload = create_test_validated_roa_payload(
            name='Validated Payload View ROA Payload',
            validation_run=cls.validation_run,
            roa=cls.roa,
            object_validation_result=cls.roa_object_validation_result,
        )
        cls.aspa = create_test_aspa(
            name='Validated Payload View ASPA',
            organization=cls.organization,
            customer_as=create_test_asn(65430),
        )
        cls.aspa_object_validation_result = create_test_object_validation_result(
            name='Validated Payload View ASPA Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.aspa.signed_object,
        )
        cls.validated_aspa_payload = create_test_validated_aspa_payload(
            name='Validated Payload View ASPA Payload',
            validation_run=cls.validation_run,
            aspa=cls.aspa,
            object_validation_result=cls.aspa_object_validation_result,
            customer_as=cls.aspa.customer_as,
            provider_as=create_test_asn(65431),
        )

    def test_validated_roa_payload_detail_shows_object_validation_result_link(self):
        self.add_permissions('netbox_rpki.view_validatedroapayload', 'netbox_rpki.view_objectvalidationresult')

        response = self.client.get(self.validated_roa_payload.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, self.roa_object_validation_result.get_absolute_url())
        self.assertContains(response, self.roa_object_validation_result.name)

    def test_validated_aspa_payload_detail_shows_object_validation_result_link(self):
        self.add_permissions('netbox_rpki.view_validatedaspapayload', 'netbox_rpki.view_objectvalidationresult')

        response = self.client.get(self.validated_aspa_payload.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, self.aspa_object_validation_result.get_absolute_url())
        self.assertContains(response, self.aspa_object_validation_result.name)


class RoutingIntentReplacementViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='replacement-view-org', name='Replacement View Org')
        cls.primary_prefix = create_test_prefix('10.155.0.0/24', status='active')
        cls.origin_asn = create_test_asn(65155)
        cls.profile = create_test_routing_intent_profile(
            name='Replacement View Profile',
            organization=cls.organization,
            status='active',
            selector_mode='filtered',
            prefix_selector_query=f'id={cls.primary_prefix.pk}',
            asn_selector_query=f'id={cls.origin_asn.pk}',
        )
        cls.derivation_run = derive_roa_intents(cls.profile)
        cls.provider_account = create_test_provider_account(
            name='Replacement View Provider',
            organization=cls.organization,
            provider_type='krill',
            org_handle='ORG-REPLACEMENT-VIEW',
            ca_handle='ca-replacement-view',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Replacement View Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            status='completed',
        )
        cls.replacement_import = create_test_imported_roa_authorization(
            name='Replacement View Imported Authorization',
            provider_snapshot=cls.provider_snapshot,
            organization=cls.organization,
            prefix=cls.primary_prefix,
            origin_asn=create_test_asn(65156),
            max_length=26,
            payload_json={'comment': 'view replacement'},
        )
        cls.reconciliation_run = reconcile_roa_intents(
            cls.derivation_run,
            comparison_scope='provider_imported',
            provider_snapshot=cls.provider_snapshot,
        )
        cls.intent_result = cls.reconciliation_run.intent_results.get(roa_intent__prefix=cls.primary_prefix)
        cls.published_result = cls.reconciliation_run.published_roa_results.get(imported_authorization=cls.replacement_import)
        cls.plan = create_roa_change_plan(cls.reconciliation_run)
        cls.create_item = cls.plan.items.get(action_type='create')

    def test_reconciliation_detail_view_shows_replacement_summary(self):
        self.add_permissions('netbox_rpki.view_roareconciliationrun')

        response = self.client.get(self.reconciliation_run.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Provider Snapshot')
        self.assertContains(response, 'replacement_required_intent_count')
        self.assertContains(response, 'wrong_origin_and_max_length_overbroad')

    def test_plan_item_detail_view_shows_before_after_and_reason(self):
        self.add_permissions('netbox_rpki.view_roachangeplanitem')

        response = self.client.get(self.create_item.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Before State')
        self.assertContains(response, 'After State')
        self.assertContains(response, 'view replacement')
        self.assertContains(response, 'wrong origin ASN and an overbroad maxLength')

    def test_change_plan_detail_view_shows_lint_and_simulation_tables(self):
        self.add_permissions(
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_roalintrun',
            'netbox_rpki.view_roavalidationsimulationrun',
        )

        response = self.client.get(self.plan.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'ROA Lint Runs')
        self.assertContains(response, 'ROA Validation Simulation Runs')

    def test_approve_view_denies_unresolved_blocking_lint(self):
        url = reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': self.plan.pk})
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')

        get_response = self.client.get(url)

        self.assertHttpStatus(get_response, 200)

        post_response = self.client.post(
            url,
            {
                'confirm': True,
            },
        )

        self.assertRedirects(post_response, self.plan.get_absolute_url())
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, rpki_models.ROAChangePlanStatus.DRAFT)

    def test_approve_view_supports_lint_acknowledgement(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_snapshot = create_test_provider_snapshot(
            name='Ack Required View Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_imported_roa_authorization(
            name='Ack Required View Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=create_test_prefix('10.155.99.0/24', status='active'),
            origin_asn=create_test_asn(65592),
            max_length=24,
        )
        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        plan = create_roa_change_plan(reconciliation_run, name='Ack Required View Plan')
        ack_required_finding = plan.lint_runs.get().findings.get(finding_code='plan_withdraw_without_replacement')
        url = reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': plan.pk})
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')

        get_response = self.client.get(url)

        self.assertHttpStatus(get_response, 200)
        self.assertContains(get_response, 'Acknowledge Approval-Required Lint Findings')
        self.assertContains(get_response, 'Plan withdraws without replacement')

        post_response = self.client.post(
            url,
            {
                'confirm': True,
                'acknowledged_findings': [ack_required_finding.pk],
                'lint_acknowledgement_notes': 'Accepted in UI test.',
            },
        )

        self.assertRedirects(post_response, plan.get_absolute_url())
        self.assertEqual(plan.lint_acknowledgements.count(), 1)

    def test_lint_finding_detail_view_shows_operator_explanation_fields(self):
        finding = self.plan.lint_runs.get().findings.get(finding_code='published_inconsistent_with_intent')
        self.add_permissions('netbox_rpki.view_roalintfinding')

        response = self.client.get(finding.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Rule Label')
        self.assertContains(response, 'Approval Impact')
        self.assertContains(response, 'Operator Message')
        self.assertContains(response, 'Why It Matters')
        self.assertContains(response, 'Operator Action')
        self.assertContains(response, 'Published ROA inconsistent with intent')
        self.assertContains(response, 'blocking')
        self.assertContains(response, 'replace the published authorization')


class OperationsDashboardViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='operations-dashboard-org', name='Operations Dashboard Org')
        cls.arin_account = create_test_provider_account(
            name='Operations Dashboard ARIN',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.ARIN,
            transport=rpki_models.ProviderSyncTransport.OTE,
            org_handle='ORG-OPS-ARIN',
            sync_interval=60,
            last_successful_sync=timezone.now() - timedelta(hours=3),
            last_sync_status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.arin_account.last_sync_summary_json = build_provider_sync_summary(
            cls.arin_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            family_summaries={},
        )
        cls.arin_account.save(update_fields=['last_sync_summary_json'])
        cls.failed_provider_account = create_test_provider_account(
            name='Failed Operations Account',
            organization=cls.organization,
            org_handle='ORG-OPS-FAILED',
            sync_interval=60,
            last_successful_sync=timezone.now() - timedelta(days=1),
            last_sync_status='failed',
        )
        cls.failed_base_snapshot = create_test_provider_snapshot(
            name='Failed Operations Base Snapshot',
            organization=cls.organization,
            provider_account=cls.failed_provider_account,
        )
        cls.failed_comparison_snapshot = create_test_provider_snapshot(
            name='Failed Operations Latest Snapshot',
            organization=cls.organization,
            provider_account=cls.failed_provider_account,
        )
        cls.failed_snapshot_diff = create_test_provider_snapshot_diff(
            name='Failed Operations Latest Diff',
            organization=cls.organization,
            provider_account=cls.failed_provider_account,
            base_snapshot=cls.failed_base_snapshot,
            comparison_snapshot=cls.failed_comparison_snapshot,
        )
        cls.failed_provider_account.last_sync_summary_json = build_provider_sync_summary(
            cls.failed_provider_account,
            status='failed',
            family_summaries={},
            error='Provider sync failed for dashboard test',
            default_supported_status='failed',
        )
        cls.failed_provider_account.last_sync_summary_json['latest_snapshot_id'] = cls.failed_comparison_snapshot.pk
        cls.failed_provider_account.last_sync_summary_json['latest_snapshot_name'] = cls.failed_comparison_snapshot.name
        cls.failed_provider_account.last_sync_summary_json['latest_snapshot_completed_at'] = timezone.now().isoformat()
        cls.failed_provider_account.last_sync_summary_json['latest_diff_id'] = cls.failed_snapshot_diff.pk
        cls.failed_provider_account.last_sync_summary_json['latest_diff_name'] = cls.failed_snapshot_diff.name
        cls.failed_provider_account.save(update_fields=['last_sync_summary_json'])
        cls.stale_provider_account = create_test_provider_account(
            name='Stale Operations Account',
            organization=cls.organization,
            org_handle='ORG-OPS-STALE',
            sync_interval=60,
            last_successful_sync=timezone.now() - timedelta(days=3),
            last_sync_status='completed',
        )
        cls.healthy_provider_account = create_test_provider_account(
            name='Healthy Operations Account',
            organization=cls.organization,
            org_handle='ORG-OPS-HEALTHY',
            sync_interval=60,
            last_successful_sync=timezone.now() - timedelta(minutes=15),
            last_sync_status='completed',
        )
        cls.expiring_certificate = create_test_certificate(
            name='Operations Expiring Certificate',
            rpki_org=cls.organization,
            issuer='Operations Issuer',
            valid_to=date.today() + timedelta(days=14),
        )
        cls.future_certificate = create_test_certificate(
            name='Operations Future Certificate',
            rpki_org=cls.organization,
            valid_to=date.today() + timedelta(days=90),
        )
        cls.expiring_roa = create_test_roa(
            name='Operations Expiring ROA',
            signed_by=cls.expiring_certificate,
            origin_as=create_test_asn(64521),
            valid_to=date.today() + timedelta(days=7),
        )
        cls.future_roa = create_test_roa(
            name='Operations Future ROA',
            signed_by=cls.future_certificate,
            origin_as=create_test_asn(64522),
            valid_to=date.today() + timedelta(days=75),
        )
        cls.intent_profile = create_test_routing_intent_profile(
            name='Operations Intent Profile',
            organization=cls.organization,
        )
        cls.intent_template = create_test_routing_intent_template(
            name='Operations Intent Template',
            organization=cls.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        cls.stale_binding = create_test_routing_intent_template_binding(
            name='Operations Stale Binding',
            template=cls.intent_template,
            intent_profile=cls.intent_profile,
            state=rpki_models.RoutingIntentTemplateBindingState.STALE,
            last_compiled_fingerprint='stale-fingerprint',
            summary_json={
                'regeneration_reason_codes': ['template_rules_changed'],
                'regeneration_reason_summary': 'Template policy changed since the last regeneration.',
            },
        )
        cls.pending_binding = create_test_routing_intent_template_binding(
            name='Operations Pending Binding',
            template=cls.intent_template,
            intent_profile=cls.intent_profile,
            state=rpki_models.RoutingIntentTemplateBindingState.PENDING,
            summary_json={},
        )
        cls.current_binding = create_test_routing_intent_template_binding(
            name='Operations Current Binding',
            template=cls.intent_template,
            intent_profile=cls.intent_profile,
            state=rpki_models.RoutingIntentTemplateBindingState.CURRENT,
            last_compiled_fingerprint='current-fingerprint',
            summary_json={
                'regeneration_reason_codes': [],
                'regeneration_reason_summary': 'No relevant input changes detected.',
            },
        )
        cls.expiring_exception = create_test_routing_intent_exception(
            name='Operations Expiring Exception',
            organization=cls.organization,
            intent_profile=cls.intent_profile,
            template_binding=cls.stale_binding,
            effect_mode=rpki_models.RoutingIntentExceptionEffectMode.TEMPORARY_REPLACEMENT,
            ends_at=timezone.now() + timedelta(days=5),
        )
        cls.future_exception = create_test_routing_intent_exception(
            name='Operations Future Exception',
            organization=cls.organization,
            intent_profile=cls.intent_profile,
            effect_mode=rpki_models.RoutingIntentExceptionEffectMode.SUPPRESS,
            ends_at=timezone.now() + timedelta(days=60),
        )
        cls.external_management_prefix = create_test_prefix('10.201.0.0/24', status='active')
        cls.external_management_origin_asn = create_test_asn(65201)
        cls.review_due_external_management_exception = create_test_external_management_exception(
            name='Operations Review-Due External Exception',
            organization=cls.organization,
            scope_type=rpki_models.ExternalManagementScope.ROA_PREFIX,
            prefix=cls.external_management_prefix,
            origin_asn=cls.external_management_origin_asn,
            max_length=24,
            owner='dashboard-owner',
            reason='Managed externally during adoption.',
            starts_at=timezone.now() - timedelta(days=10),
            review_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=10),
        )
        cls.failed_bulk_run = create_test_bulk_intent_run(
            name='Operations Failed Bulk Run',
            organization=cls.organization,
            status=rpki_models.ValidationRunStatus.FAILED,
            target_mode=rpki_models.BulkIntentTargetMode.BINDINGS,
            started_at=timezone.now() - timedelta(hours=2),
            completed_at=timezone.now() - timedelta(hours=1, minutes=30),
            summary_json={
                'scope_result_count': 1,
                'change_plan_count': 0,
                'failed_scope_count': 1,
                'error': 'Template binding regeneration failed.',
            },
        )
        cls.running_bulk_run = create_test_bulk_intent_run(
            name='Operations Running Bulk Run',
            organization=cls.organization,
            status=rpki_models.ValidationRunStatus.RUNNING,
            target_mode=rpki_models.BulkIntentTargetMode.PROFILES,
            started_at=timezone.now() - timedelta(minutes=20),
            summary_json={
                'scope_result_count': 2,
                'change_plan_count': 1,
                'failed_scope_count': 0,
            },
        )
        cls.completed_bulk_run = create_test_bulk_intent_run(
            name='Operations Completed Bulk Run',
            organization=cls.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            target_mode=rpki_models.BulkIntentTargetMode.MIXED,
            started_at=timezone.now() - timedelta(days=1),
            completed_at=timezone.now() - timedelta(days=1, minutes=-5),
            summary_json={
                'scope_result_count': 3,
                'change_plan_count': 2,
                'failed_scope_count': 0,
            },
        )
        cls.aspa_provider_account = create_test_provider_account(
            name='ASPA Operations Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-OPS-ASPA',
            ca_handle='ops-aspa',
        )
        cls.aspa_snapshot = create_test_provider_snapshot(
            name='ASPA Operations Snapshot',
            organization=cls.organization,
            provider_account=cls.aspa_provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.aspa_reconciliation_run = create_test_aspa_reconciliation_run(
            name='ASPA Operations Reconciliation',
            organization=cls.organization,
            provider_snapshot=cls.aspa_snapshot,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            result_summary_json={
                'intent_result_types': {
                    rpki_models.ASPAIntentResultType.MISSING_PROVIDER: 1,
                    rpki_models.ASPAIntentResultType.STALE: 1,
                },
                'published_result_types': {
                    rpki_models.PublishedASPAResultType.EXTRA_PROVIDER: 1,
                    rpki_models.PublishedASPAResultType.ORPHANED: 1,
                },
            },
        )
        cls.aspa_change_plan = create_test_aspa_change_plan(
            name='ASPA Operations Change Plan',
            organization=cls.organization,
            source_reconciliation_run=cls.aspa_reconciliation_run,
            provider_account=cls.aspa_provider_account,
            provider_snapshot=cls.aspa_snapshot,
            status=rpki_models.ASPAChangePlanStatus.FAILED,
            summary_json={
                'replacement_count': 1,
                'provider_add_count': 2,
                'provider_remove_count': 1,
            },
        )
        cls.validator_attention = create_test_validator_instance(
            name='Operations Validator',
            organization=cls.organization,
            status=rpki_models.ValidationRunStatus.FAILED,
        )
        cls.validation_run_attention = create_test_validation_run(
            name='Operations Validation Run',
            validator=cls.validator_attention,
            status=rpki_models.ValidationRunStatus.FAILED,
            started_at=timezone.now() - timedelta(days=2),
            completed_at=timezone.now() - timedelta(days=2, minutes=-5),
        )
        cls.telemetry_source_attention = create_test_telemetry_source(
            name='Operations Telemetry Source',
            organization=cls.organization,
            slug='operations-telemetry-source',
            last_run_status=rpki_models.ValidationRunStatus.FAILED,
            last_successful_run=None,
        )
        cls.mismatch_validation_run = create_test_validation_run(
            name='Operations Mismatch Validation Run',
            validator=cls.validator_attention,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.mismatch_validation_result = create_test_object_validation_result(
            name='Operations Mismatch Validation Result',
            validation_run=cls.mismatch_validation_run,
            signed_object=cls.expiring_roa.signed_object,
            validation_state=rpki_models.ValidationState.INVALID,
            disposition=rpki_models.ValidationDisposition.REJECTED,
        )
        create_test_validated_roa_payload(
            name='Operations Mismatch ROA Payload',
            validation_run=cls.mismatch_validation_run,
            roa=cls.expiring_roa,
            object_validation_result=cls.mismatch_validation_result,
            observed_prefix='198.51.100.0/24',
        )
        cls.irr_source_attention = create_test_irr_source(
            name='Operations IRR Source',
            slug='operations-irr-source',
            organization=cls.organization,
            last_successful_snapshot=None,
            last_sync_status=rpki_models.IrrSnapshotStatus.FAILED,
        )
        cls.irr_coordination_run = create_test_irr_coordination_run(
            name='Operations IRR Coordination',
            organization=cls.organization,
            compared_sources=[cls.irr_source_attention],
            summary_json={
                'cross_source_conflict_count': 2,
                'stale_source_count': 1,
                'non_draftable_source_count': 1,
                'draftable_source_count': 0,
                'latest_plan_ids': [],
            },
        )
        cls.irr_change_plan = create_test_irr_change_plan(
            name='Operations IRR Change Plan',
            organization=cls.organization,
            coordination_run=cls.irr_coordination_run,
            source=cls.irr_source_attention,
            status=rpki_models.IrrChangePlanStatus.FAILED,
            summary_json={
                'capability_warnings': ['Target source does not currently support automated IRR preview or apply.'],
                'item_counts': {
                    rpki_models.IrrChangePlanAction.NOOP: 1,
                },
                'latest_execution': {
                    'id': 0,
                    'mode': 'apply',
                    'status': 'failed',
                },
            },
        )
        create_test_irr_change_plan_item(
            name='Operations IRR Change Plan Item',
            change_plan=cls.irr_change_plan,
            action=rpki_models.IrrChangePlanAction.NOOP,
        )
        cls.irr_write_execution = create_test_irr_write_execution(
            name='Operations IRR Write Failure',
            organization=cls.organization,
            source=cls.irr_source_attention,
            change_plan=cls.irr_change_plan,
            execution_mode=rpki_models.IrrWriteExecutionMode.APPLY,
            status=rpki_models.IrrWriteExecutionStatus.PARTIAL,
            error='IRR delete rejected during dashboard test',
        )

    def test_operations_dashboard_surfaces_sync_and_expiry_issues(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
            'netbox_rpki.view_roaobject',
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.view_routingintentexception',
            'netbox_rpki.view_externalmanagementexception',
            'netbox_rpki.view_bulkintentrun',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_aspareconciliationrun',
            'netbox_rpki.view_aspachangeplan',
            'netbox_rpki.view_validatorinstance',
            'netbox_rpki.view_validationrun',
            'netbox_rpki.view_telemetrysource',
            'netbox_rpki.view_irrsource',
            'netbox_rpki.view_irrcoordinationrun',
            'netbox_rpki.view_irrchangeplan',
            'netbox_rpki.view_irrwriteexecution',
        )
        scenario = create_test_roa_change_plan_matrix(organization=self.organization)

        response = self.client.get(reverse('plugins:netbox_rpki:operations_dashboard'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Operations Dashboard')
        self.assertContains(response, self.failed_provider_account.name)
        self.assertContains(response, self.stale_provider_account.name)
        self.assertNotContains(response, self.healthy_provider_account.name)
        self.assertContains(response, 'Bindings Requiring Regeneration')
        self.assertContains(response, self.stale_binding.name)
        self.assertContains(response, self.pending_binding.name)
        self.assertNotContains(response, self.current_binding.name)
        self.assertContains(response, 'Template policy changed since the last regeneration.')
        self.assertContains(response, 'Intent Exceptions Nearing Expiry')
        self.assertContains(response, self.expiring_exception.name)
        self.assertNotContains(response, self.future_exception.name)
        self.assertContains(response, 'Expires in 5 day(s)')
        self.assertContains(response, 'External Management Exceptions Requiring Review')
        self.assertContains(response, self.review_due_external_management_exception.name)
        self.assertContains(response, 'Review Due')
        self.assertContains(response, 'Pending Approval')
        self.assertContains(response, 'Recent Bulk Intent Runs')
        self.assertContains(response, self.failed_bulk_run.name)
        self.assertContains(response, self.running_bulk_run.name)
        self.assertContains(response, self.completed_bulk_run.name)
        self.assertContains(response, 'Template binding regeneration failed.')
        self.assertContains(response, 'Freshness')
        self.assertContains(response, 'Family Coverage')
        self.assertContains(response, 'Publication Health')
        self.assertContains(response, self.failed_comparison_snapshot.name)
        self.assertContains(response, self.failed_snapshot_diff.name)
        self.assertContains(response, 'ASPA Reconciliation Runs Requiring Attention')
        self.assertContains(response, self.aspa_reconciliation_run.name)
        self.assertContains(response, 'Open ASPA Change Plans Requiring Attention')
        self.assertContains(response, self.aspa_change_plan.name)
        self.assertContains(response, 'External Evidence Overview')
        self.assertContains(response, 'Validator Instances Requiring Attention')
        self.assertContains(response, self.validator_attention.name)
        self.assertContains(response, 'Validation Runs Requiring Attention')
        self.assertContains(response, self.validation_run_attention.name)
        self.assertContains(response, 'Telemetry Sources Requiring Attention')
        self.assertContains(response, self.telemetry_source_attention.name)
        self.assertContains(response, 'Authored Objects With External Evidence Mismatches')
        self.assertContains(response, self.expiring_roa.name)
        self.assertContains(response, 'validator_invalid')
        self.assertContains(response, self.expiring_roa.name)
        self.assertNotContains(response, self.future_roa.name)
        self.assertContains(response, self.expiring_certificate.name)
        self.assertNotContains(response, self.future_certificate.name)
        self.assertContains(response, 'Expires in 7 day(s)')
        self.assertContains(response, 'Expires in 14 day(s)')
        self.assertContains(response, 'Reconciliation Runs Requiring Attention')
        self.assertContains(response, 'Open ROA Change Plans Requiring Attention')
        self.assertContains(response, 'replacement-required intents')
        self.assertContains(response, 'without simulation')
        self.assertContains(response, 'simulation blocking')
        self.assertContains(response, 'Blocking')
        self.assertContains(response, 'Ack Required')
        self.assertContains(response, 'Acknowledged')
        self.assertContains(response, 'Suppressed')
        self.assertContains(response, scenario.provider_plan.name)
        self.assertContains(response, 'IRR Sources Requiring Attention')
        self.assertContains(response, self.irr_source_attention.name)
        self.assertContains(response, 'IRR Coordination Runs Requiring Attention')
        self.assertContains(response, self.irr_coordination_run.name)
        self.assertContains(response, 'IRR Change Plans Requiring Attention')
        self.assertContains(response, self.irr_change_plan.name)
        self.assertContains(response, 'Recent IRR Write Failures')
        self.assertContains(response, self.irr_write_execution.name)
        self.assertContains(response, 'IRR delete rejected during dashboard test')

    def test_operations_dashboard_surfaces_missing_simulation_attention(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
            'netbox_rpki.view_roaobject',
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.view_routingintentexception',
            'netbox_rpki.view_bulkintentrun',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_aspareconciliationrun',
            'netbox_rpki.view_aspachangeplan',
            'netbox_rpki.view_validatorinstance',
            'netbox_rpki.view_validationrun',
            'netbox_rpki.view_telemetrysource',
            'netbox_rpki.view_irrsource',
            'netbox_rpki.view_irrcoordinationrun',
            'netbox_rpki.view_irrchangeplan',
            'netbox_rpki.view_irrwriteexecution',
        )
        simulation_missing_plan = create_test_roa_change_plan(
            name='Dashboard Missing Simulation Plan',
            organization=self.organization,
        )

        response = self.client.get(reverse('plugins:netbox_rpki:operations_dashboard'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, simulation_missing_plan.name)
        self.assertContains(response, 'No simulation')

    def test_operations_dashboard_uses_effective_lifecycle_policy_thresholds(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
            'netbox_rpki.view_roaobject',
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.view_routingintentexception',
            'netbox_rpki.view_bulkintentrun',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_aspareconciliationrun',
            'netbox_rpki.view_aspachangeplan',
            'netbox_rpki.view_irrsource',
            'netbox_rpki.view_irrcoordinationrun',
            'netbox_rpki.view_irrchangeplan',
            'netbox_rpki.view_irrwriteexecution',
        )

        policy_organization = create_test_organization(
            org_id='operations-policy-org',
            name='Operations Policy Org',
        )
        create_test_lifecycle_health_policy(
            name='Operations Policy Org Thresholds',
            organization=policy_organization,
            sync_stale_after_minutes=10,
            roa_expiry_warning_days=7,
            certificate_expiry_warning_days=7,
            exception_expiry_warning_days=7,
        )
        healthy_provider_account = create_test_provider_account(
            name='Policy Healthy Provider',
            organization=policy_organization,
            org_handle='ORG-OPS-POLICY-HEALTHY',
            last_successful_sync=timezone.now() - timedelta(minutes=5),
            last_sync_status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        stale_provider_account = create_test_provider_account(
            name='Policy Stale Provider',
            organization=policy_organization,
            org_handle='ORG-OPS-POLICY-STALE',
            last_successful_sync=timezone.now() - timedelta(minutes=5),
            last_sync_status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_lifecycle_health_policy(
            name='Policy Stale Provider Override',
            organization=policy_organization,
            provider_account=stale_provider_account,
            sync_stale_after_minutes=1,
        )

        expiring_certificate = create_test_certificate(
            name='Policy Expiring Certificate',
            rpki_org=policy_organization,
            valid_to=date.today() + timedelta(days=14),
        )
        create_test_roa(
            name='Policy Expiring ROA',
            signed_by=expiring_certificate,
            origin_as=create_test_asn(64530),
            valid_to=date.today() + timedelta(days=14),
        )

        response = self.client.get(reverse('plugins:netbox_rpki:operations_dashboard'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Thresholds follow the effective lifecycle policy for each organization or provider account.')
        self.assertContains(response, 'Policy Stale Provider')
        self.assertContains(response, 'Stale after 1 minute(s)')
        self.assertNotContains(response, healthy_provider_account.name)
        self.assertNotContains(response, expiring_certificate.name)
        self.assertNotContains(response, 'Policy Expiring ROA')

    def test_operations_dashboard_surfaces_blocking_simulation_posture_and_counts(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
            'netbox_rpki.view_roaobject',
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.view_routingintentexception',
            'netbox_rpki.view_bulkintentrun',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_aspareconciliationrun',
            'netbox_rpki.view_aspachangeplan',
            'netbox_rpki.view_validatorinstance',
            'netbox_rpki.view_validationrun',
            'netbox_rpki.view_telemetrysource',
            'netbox_rpki.view_irrsource',
            'netbox_rpki.view_irrcoordinationrun',
            'netbox_rpki.view_irrchangeplan',
            'netbox_rpki.view_irrwriteexecution',
            'netbox_rpki.view_roavalidationsimulationrun',
        )
        plan = create_test_roa_change_plan(
            name='Dashboard Blocking Simulation Plan',
            organization=self.organization,
            summary_json={'simulation_run_id': 0},
        )
        simulation_run = create_test_roa_validation_simulation_run(
            name='Dashboard Blocking Simulation Run',
            change_plan=plan,
            plan_fingerprint='dashboard-blocking-fingerprint',
            overall_approval_posture=rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
            is_current_for_plan=False,
            predicted_valid_count=0,
            predicted_invalid_count=2,
            predicted_not_found_count=1,
            summary_json={
                'plan_fingerprint': 'dashboard-blocking-fingerprint',
                'approval_impact_counts': {
                    rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL: 0,
                    rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED: 1,
                    rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING: 2,
                },
                'scenario_type_counts': {'withdraw_without_replacement_blocks_intended_route': 2},
                'overall_approval_posture': rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING,
                'is_current_for_plan': False,
                'partially_constrained': False,
            },
        )
        plan.summary_json = {'simulation_run_id': simulation_run.pk}
        plan.save(update_fields=('summary_json',))

        response = self.client.get(reverse('plugins:netbox_rpki:operations_dashboard'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, plan.name)
        self.assertContains(response, 'blocking')
        self.assertContains(response, '2 blocking / 1 ack-required')
        self.assertContains(response, '/ stale')

    def test_operations_dashboard_shows_arin_roa_only_family_coverage(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
            'netbox_rpki.view_roaobject',
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.view_routingintentexception',
            'netbox_rpki.view_bulkintentrun',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_aspareconciliationrun',
            'netbox_rpki.view_aspachangeplan',
            'netbox_rpki.view_validatorinstance',
            'netbox_rpki.view_validationrun',
            'netbox_rpki.view_telemetrysource',
            'netbox_rpki.view_irrsource',
            'netbox_rpki.view_irrcoordinationrun',
            'netbox_rpki.view_irrchangeplan',
            'netbox_rpki.view_irrwriteexecution',
        )

        response = self.client.get(reverse('plugins:netbox_rpki:operations_dashboard'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Provider Accounts Requiring Attention')
        self.assertContains(response, self.arin_account.name)
        self.assertContains(response, '9 families: 1 pending, 8 not implemented')
        self.assertContains(response, 'Stale after 120 minute(s)')
        self.assertContains(response, 'Bulk Runs Requiring Attention')

    def test_operations_dashboard_shows_export_buttons(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_providersnapshot',
            'netbox_rpki.view_providersnapshotdiff',
            'netbox_rpki.view_roaobject',
            'netbox_rpki.view_certificate',
            'netbox_rpki.view_routingintenttemplatebinding',
            'netbox_rpki.view_routingintentexception',
            'netbox_rpki.view_bulkintentrun',
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_aspareconciliationrun',
            'netbox_rpki.view_aspachangeplan',
            'netbox_rpki.view_validatorinstance',
            'netbox_rpki.view_validationrun',
            'netbox_rpki.view_telemetrysource',
            'netbox_rpki.view_irrsource',
            'netbox_rpki.view_irrcoordinationrun',
            'netbox_rpki.view_irrchangeplan',
            'netbox_rpki.view_irrwriteexecution',
        )

        response = self.client.get(reverse('plugins:netbox_rpki:operations_dashboard'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, reverse('plugins:netbox_rpki:operations_export') + '?format=json')
        self.assertContains(response, reverse('plugins:netbox_rpki:operations_export') + '?format=csv')


class GeneratedSurfaceContractTestCase(PluginViewTestCase):
    def _add_maximum_object_permissions(self, spec):
        self.add_permissions(
            f'netbox_rpki.view_{spec.model._meta.model_name}',
            f'netbox_rpki.add_{spec.model._meta.model_name}',
            f'netbox_rpki.change_{spec.model._meta.model_name}',
            f'netbox_rpki.delete_{spec.model._meta.model_name}',
        )

    def test_all_generated_list_views_match_registry_action_contract(self):
        for spec in VIEW_OBJECT_SPECS:
            instance = _build_instance_for_spec(spec, token=f'{spec.registry_key}-surface-list')
            self._add_maximum_object_permissions(spec)

            response = self.client.get(reverse(spec.list_url_name))

            with self.subTest(object_key=spec.registry_key, instance=instance.pk):
                self.assertHttpStatus(response, 200)
                expected_list_actions = ['add', 'export'] if spec.view.supports_create else ['export']
                expected_row_actions = ('edit', 'delete', 'changelog') if spec.view.supports_create else ('changelog',)
                self.assertEqual([action.name for action in response.context['actions']], expected_list_actions)
                self.assertEqual(
                    tuple(response.context['table'].base_columns['actions'].actions.keys()),
                    expected_row_actions,
                )
                self.assertNotContains(response, '/None')

    def test_all_generated_detail_views_match_registry_action_contract(self):
        for spec in VIEW_OBJECT_SPECS:
            instance = _build_instance_for_spec(spec, token=f'{spec.registry_key}-surface-detail')
            self._add_maximum_object_permissions(spec)

            response = self.client.get(instance.get_absolute_url())

            with self.subTest(object_key=spec.registry_key, instance=instance.pk):
                self.assertHttpStatus(response, 200)
                expected_detail_actions = ['add', 'edit', 'delete'] if spec.view.supports_create else []
                self.assertEqual([action.name for action in response.context['actions']], expected_detail_actions)
                self.assertNotContains(response, '/None')


class ReconciliationDetailViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='reconcile-org', name='Reconcile Org')
        cls.profile = create_test_routing_intent_profile(
            name='Dashboard Profile',
            organization=cls.organization,
            description='Primary profile for reconciliation dashboard coverage.',
            prefix_selector_query='role=edge',
            asn_selector_query='asn=64512',
        )
        cls.rule = create_test_routing_intent_rule(
            name='Dashboard Rule',
            intent_profile=cls.profile,
        )
        cls.override = create_test_roa_intent_override(
            name='Dashboard Override',
            organization=cls.organization,
            intent_profile=cls.profile,
            prefix_cidr_text='10.10.0.0/24',
            origin_asn_value=64512,
            max_length=24,
        )
        cls.derivation_run = create_test_intent_derivation_run(
            name='Dashboard Derivation Run',
            organization=cls.organization,
            intent_profile=cls.profile,
            intent_count_emitted=1,
        )
        cls.origin_asn = create_test_asn(64512)
        cls.prefix = create_test_prefix('10.10.0.0/24')
        cls.roa_intent = create_test_roa_intent(
            name='Dashboard Intent',
            derivation_run=cls.derivation_run,
            organization=cls.organization,
            intent_profile=cls.profile,
            prefix=cls.prefix,
            origin_asn=cls.origin_asn,
            origin_asn_value=cls.origin_asn.asn,
            max_length=24,
            source_rule=cls.rule,
            applied_override=cls.override,
        )
        cls.certificate = create_test_certificate(name='Dashboard Certificate', rpki_org=cls.organization)
        cls.roa = create_test_roa(name='Dashboard Published ROA', origin_as=cls.origin_asn, signed_by=cls.certificate)
        cls.roa_prefix = create_test_roa_prefix(roa=cls.roa, prefix=cls.prefix, max_length=25)
        cls.candidate_match = create_test_roa_intent_match(
            name='Dashboard Candidate Match',
            roa_intent=cls.roa_intent,
            roa=cls.roa,
            details_json={'comparison': 'max_length differs'},
            is_best_match=True,
        )
        cls.reconciliation_run = create_test_roa_reconciliation_run(
            name='Dashboard Reconciliation Run',
            organization=cls.organization,
            intent_profile=cls.profile,
            basis_derivation_run=cls.derivation_run,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            published_roa_count=1,
            intent_count=1,
            result_summary_json={
                'missing': 0,
                'overbroad': 1,
                'matched': 0,
            },
        )
        cls.intent_result = create_test_roa_intent_result(
            name='Dashboard Intent Result',
            reconciliation_run=cls.reconciliation_run,
            roa_intent=cls.roa_intent,
            best_roa=cls.roa,
            match_count=1,
            details_json={
                'expected': {'prefix': '10.10.0.0/24', 'max_length': 24},
                'published': {'prefix': '10.10.0.0/24', 'max_length': 25},
                'delta': {'max_length': {'expected': 24, 'published': 25}},
            },
        )
        cls.published_result = create_test_published_roa_result(
            name='Dashboard Published Result',
            reconciliation_run=cls.reconciliation_run,
            roa=cls.roa,
            details_json={'status': 'extra breadth'},
        )
        cls.validator = create_test_validator_instance(
            name='Reconciliation View Validator',
            organization=cls.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.validation_run = create_test_validation_run(
            name='Reconciliation View Validation Run',
            validator=cls.validator,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.roa_validation_result = create_test_object_validation_result(
            name='Reconciliation View ROA Validation Result',
            validation_run=cls.validation_run,
            signed_object=cls.roa.signed_object,
            validation_state=rpki_models.ValidationState.INVALID,
            disposition=rpki_models.ValidationDisposition.REJECTED,
        )
        create_test_validated_roa_payload(
            name='Reconciliation View ROA Payload',
            validation_run=cls.validation_run,
            roa=cls.roa,
            object_validation_result=cls.roa_validation_result,
            prefix=cls.prefix,
            observed_prefix=str(cls.prefix.prefix),
            origin_as=cls.origin_asn,
            max_length=25,
        )
        cls.telemetry_source = create_test_telemetry_source(
            name='Reconciliation View Telemetry Source',
            organization=cls.organization,
            slug='reconciliation-view-telemetry',
        )
        cls.telemetry_run = create_test_telemetry_run(
            name='Reconciliation View Telemetry Run',
            source=cls.telemetry_source,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_bgp_path_observation(
            name='Reconciliation View ROA Observation',
            telemetry_run=cls.telemetry_run,
            source=cls.telemetry_source,
            prefix=cls.prefix,
            observed_prefix=str(cls.prefix.prefix),
            origin_as=cls.origin_asn,
            observed_origin_asn=cls.origin_asn.asn,
            raw_as_path=f'64496 {cls.origin_asn.asn}',
            path_asns_json=[64496, cls.origin_asn.asn],
        )
        cls.aspa = create_test_aspa(
            name='Reconciliation View ASPA',
            organization=cls.organization,
            customer_as=cls.origin_asn,
        )
        cls.aspa_provider = create_test_aspa_provider(aspa=cls.aspa, provider_as=create_test_asn(64520))
        create_test_validated_aspa_payload(
            name='Reconciliation View ASPA Payload',
            validation_run=cls.validation_run,
            aspa=cls.aspa,
            customer_as=cls.origin_asn,
            provider_as=cls.aspa_provider.provider_as,
        )
        create_test_bgp_path_observation(
            name='Reconciliation View ASPA Observation',
            telemetry_run=cls.telemetry_run,
            source=cls.telemetry_source,
            prefix=cls.prefix,
            observed_prefix=str(cls.prefix.prefix),
            origin_as=cls.origin_asn,
            observed_origin_asn=cls.origin_asn.asn,
            raw_as_path=f'64496 {cls.aspa_provider.provider_as.asn} {cls.origin_asn.asn}',
            path_asns_json=[64496, cls.aspa_provider.provider_as.asn, cls.origin_asn.asn],
        )
        cls.aspa_reconciliation_run = create_test_aspa_reconciliation_run(
            name='Dashboard ASPA Reconciliation Run',
            organization=cls.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            result_summary_json={'intent_result_types': {'match': 1}},
        )
        create_test_aspa_intent(
            name='Dashboard ASPA Intent',
            organization=cls.organization,
            customer_as=cls.origin_asn,
            provider_as=cls.aspa_provider.provider_as,
        )
        cls.aspa_plan = create_test_aspa_change_plan(
            name='Dashboard ASPA Change Plan',
            organization=cls.organization,
            source_reconciliation_run=cls.aspa_reconciliation_run,
        )
        create_test_aspa_change_plan_item(
            name='Dashboard ASPA Change Plan Item',
            change_plan=cls.aspa_plan,
            aspa=cls.aspa,
        )

    def test_routing_intent_profile_detail_renders_dashboard_sections(self):
        self.add_permissions('netbox_rpki.view_routingintentprofile')

        response = self.client.get(self.profile.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')
        self.assertContains(response, 'Routing Intent Profile Dashboard')
        self.assertContains(response, 'Routing Intent Rules')
        self.assertContains(response, 'ROA Intent Overrides')
        self.assertContains(response, 'Intent Derivation Runs')
        self.assertContains(response, 'ROA Reconciliation Runs')
        self.assertContains(response, 'Derived ROA Intents')
        self.assertContains(response, 'Dashboard Rule')
        self.assertContains(response, 'Dashboard Override')
        self.assertContains(response, 'Dashboard Derivation Run')
        self.assertContains(response, 'Dashboard Reconciliation Run')

    def test_routing_intent_profile_detail_renders_with_read_only_child_change_permissions(self):
        self.add_permissions(
            'netbox_rpki.view_routingintentprofile',
            'netbox_rpki.change_intentderivationrun',
            'netbox_rpki.delete_intentderivationrun',
            'netbox_rpki.change_roareconciliationrun',
            'netbox_rpki.delete_roareconciliationrun',
            'netbox_rpki.change_roaintent',
            'netbox_rpki.delete_roaintent',
        )

        response = self.client.get(self.profile.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertEqual(
            {
                section['title']: tuple(section['table'].base_columns['actions'].actions.keys())
                for section in response.context['detail_bottom_sections']
            },
            {
                'Intent Derivation Runs': ('changelog',),
                'ROA Reconciliation Runs': ('changelog',),
                'Derived ROA Intents': ('changelog',),
            },
        )

    def test_reconciliation_run_detail_renders_drilldown_sections(self):
        self.add_permissions('netbox_rpki.view_roareconciliationrun')

        response = self.client.get(self.reconciliation_run.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')
        self.assertContains(response, 'ROA Reconciliation Run')
        self.assertContains(response, 'Result Summary')
        self.assertContains(response, '&quot;overbroad&quot;: 1')
        self.assertContains(response, 'External Overlay Summary')
        self.assertContains(response, 'validator_invalid')
        self.assertContains(response, 'ROA Intent Results')
        self.assertContains(response, 'Published ROA Results')
        self.assertContains(response, 'Dashboard Intent Result')
        self.assertContains(response, 'Dashboard Published Result')

    def test_change_plan_detail_renders_external_overlay_summary(self):
        plan = create_test_roa_change_plan(
            name='Reconciliation View Plan',
            organization=self.organization,
            source_reconciliation_run=self.reconciliation_run,
        )
        create_test_roa_change_plan_item(
            name='Reconciliation View Plan Item',
            change_plan=plan,
            roa=self.roa,
        )
        self.add_permissions(
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_roalintrun',
            'netbox_rpki.view_roavalidationsimulationrun',
        )

        response = self.client.get(plan.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'External Overlay Summary')
        self.assertContains(response, 'validator_state_counts')

    def test_aspa_reconciliation_and_plan_detail_render_external_overlay_summary(self):
        self.add_permissions('netbox_rpki.view_aspareconciliationrun', 'netbox_rpki.view_aspachangeplan')

        run_response = self.client.get(self.aspa_reconciliation_run.get_absolute_url())
        plan_response = self.client.get(self.aspa_plan.get_absolute_url())

        self.assertHttpStatus(run_response, 200)
        self.assertContains(run_response, 'External Overlay Summary')
        self.assertContains(run_response, 'telemetry_status_counts')

        self.assertHttpStatus(plan_response, 200)
        self.assertContains(plan_response, 'External Overlay Summary')
        self.assertContains(plan_response, 'source_reconciliation_run_id')

    def test_reconciliation_run_detail_shows_create_plan_button(self):
        self.add_permissions('netbox_rpki.view_roareconciliationrun', 'netbox_rpki.change_routingintentprofile')

        response = self.client.get(self.reconciliation_run.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(
            response,
            reverse('plugins:netbox_rpki:roareconciliationrun_create_plan', kwargs={'pk': self.reconciliation_run.pk}),
        )

    def test_reconciliation_run_detail_hides_create_plan_button_without_profile_change_permission(self):
        self.add_permissions('netbox_rpki.view_roareconciliationrun')

        response = self.client.get(self.reconciliation_run.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertNotContains(
            response,
            reverse('plugins:netbox_rpki:roareconciliationrun_create_plan', kwargs={'pk': self.reconciliation_run.pk}),
        )

    def test_reconciliation_run_create_plan_view_creates_plan(self):
        self.add_permissions(
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.change_routingintentprofile',
            'netbox_rpki.view_roachangeplan',
        )
        plan = create_test_roa_change_plan(
            name='Reconciliation View Created Plan',
            organization=self.organization,
            source_reconciliation_run=self.reconciliation_run,
        )

        with patch('netbox_rpki.views.create_roa_change_plan', return_value=plan) as create_plan_mock:
            response = self.client.post(
                reverse('plugins:netbox_rpki:roareconciliationrun_create_plan', kwargs={'pk': self.reconciliation_run.pk}),
                {'confirm': True},
            )

        self.assertRedirects(response, plan.get_absolute_url())
        create_plan_mock.assert_called_once_with(self.reconciliation_run)

    def test_reconciliation_run_create_plan_view_requires_profile_change_permission(self):
        self.add_permissions('netbox_rpki.view_roareconciliationrun')

        response = self.client.get(
            reverse('plugins:netbox_rpki:roareconciliationrun_create_plan', kwargs={'pk': self.reconciliation_run.pk})
        )

        self.assertHttpStatus(response, 403)

    def test_roa_intent_result_detail_renders_diff_context_and_candidate_matches(self):
        self.add_permissions('netbox_rpki.view_roaintentresult')

        response = self.client.get(self.intent_result.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')
        self.assertContains(response, 'ROA Intent Result Diff')
        self.assertContains(response, 'Expected Prefix')
        self.assertContains(response, '10.10.0.0/24')
        self.assertContains(response, 'Published Max Lengths')
        self.assertContains(response, '25')
        self.assertContains(response, 'Candidate Matches')
        self.assertContains(response, 'Dashboard Candidate Match')
        self.assertContains(response, '&quot;delta&quot;')


class IrrDetailViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='irr-detail-org', name='IRR Detail Org')
        cls.source = create_test_irr_source(
            name='IRR Detail Source',
            slug='irr-detail-source',
            organization=cls.organization,
        )
        cls.coordination_run = create_test_irr_coordination_run(
            name='IRR Detail Coordination',
            organization=cls.organization,
            compared_sources=[cls.source],
        )
        cls.change_plan = create_test_irr_change_plan(
            name='IRR Detail Change Plan',
            organization=cls.organization,
            coordination_run=cls.coordination_run,
            source=cls.source,
        )
        cls.change_plan_item = create_test_irr_change_plan_item(
            name='IRR Detail Plan Item',
            change_plan=cls.change_plan,
        )
        cls.write_execution = create_test_irr_write_execution(
            name='IRR Detail Write Execution',
            organization=cls.organization,
            source=cls.source,
            change_plan=cls.change_plan,
        )

    def test_irr_change_plan_detail_renders_curated_sections(self):
        self.add_permissions(
            'netbox_rpki.view_irrchangeplan',
            'netbox_rpki.view_irrchangeplanitem',
            'netbox_rpki.view_irrwriteexecution',
        )

        response = self.client.get(self.change_plan.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')
        self.assertContains(response, 'IRR Change Plan Items')
        self.assertContains(response, 'IRR Write Executions')
        self.assertContains(response, self.change_plan_item.name)
        self.assertContains(response, self.write_execution.name)


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

    def test_organization_detail_renders_roa_lint_rule_configs_table(self):
        create_test_roa_lint_rule_config(
            name='Organization Lint Rule Override',
            organization=self.organizations[0],
            severity_override=rpki_models.ReconciliationSeverity.CRITICAL,
        )
        self.add_permissions('netbox_rpki.view_organization', 'netbox_rpki.view_roalintruleconfig')

        response = self.client.get(self.organizations[0].get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'ROA Lint Rule Configs')
        self.assertContains(response, 'Organization Lint Rule Override')


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
            reverse("plugins:netbox_rpki:roaobject_add"),
        )


class RoaViewTestCase(GeneratedObjectViewTestMixin, PluginViewTestCase):
    view_name = 'roaobject'
    model = Roa
    list_permissions = ('netbox_rpki.view_roaobject',)
    create_permissions = ('netbox_rpki.add_roaobject', 'netbox_rpki.view_organization', 'ipam.view_asn')
    invalid_create_permissions = ('netbox_rpki.add_roaobject', 'netbox_rpki.view_organization', 'ipam.view_asn')
    empty_create_permissions = ('netbox_rpki.add_roaobject', 'netbox_rpki.view_organization', 'ipam.view_asn')
    edit_permissions = ('netbox_rpki.change_roaobject', 'netbox_rpki.view_organization', 'ipam.view_asn')
    delete_permissions = ('netbox_rpki.delete_roaobject',)
    list_expected_text = ('View ROA 1', 'View ROA 2')
    filter_query = 'View ROA 2'
    filter_expected_text = ('View ROA 2',)
    filter_unexpected_text = ('View ROA 1',)
    invalid_form_errors = ('name', 'This field is required')
    empty_form_errors = ('name', 'This field is required')

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
            'organization': self.organization,
            'origin_as': self.asns[0],
            'validation_state': rpki_models.ValidationState.UNKNOWN,
        }

    def get_invalid_create_data(self):
        return {'validation_state': rpki_models.ValidationState.UNKNOWN}

    def get_edit_instance(self):
        return self.roas[0]

    def get_valid_edit_data(self):
        return {
            'name': 'View ROA 1 Updated',
            'organization': self.organization,
            'origin_as': self.asns[0],
            'validation_state': rpki_models.ValidationState.UNKNOWN,
        }

    def get_delete_instance(self):
        return self.roas[2]

    def assert_valid_create_result(self):
        self.assertTrue(Roa.objects.filter(name='View ROA 4').exists())

    def assert_valid_edit_result(self, instance):
        instance.refresh_from_db()
        self.assertEqual(instance.name, 'View ROA 1 Updated')

    def test_roa_detail_renders_prefix_table_and_prefill_link(self):
        self.add_permissions('netbox_rpki.view_roaobject', 'netbox_rpki.change_roaobject')

        response = self.client.get(self.roas[0].get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')
        self.assertContains(response, str(self.prefixes[0].prefix))
        self.assertContains(response, date_format(self.roas[0].valid_from))
        self.assertContains(response, date_format(self.roas[0].valid_to))
        self.assertContains(
            response,
            f'{reverse("plugins:netbox_rpki:roaobjectprefix_add")}?roa_object={self.roas[0].pk}',
        )


class RoaPrefixViewTestCase(GeneratedObjectViewTestMixin, PluginViewTestCase):
    view_name = 'roaobjectprefix'
    model = RoaPrefix
    list_permissions = ('netbox_rpki.view_roaobjectprefix',)
    create_permissions = ('netbox_rpki.add_roaobjectprefix', 'netbox_rpki.view_roaobject', 'ipam.view_prefix')
    invalid_create_permissions = ('netbox_rpki.add_roaobjectprefix', 'netbox_rpki.view_roaobject', 'ipam.view_prefix')
    empty_create_permissions = ('netbox_rpki.add_roaobjectprefix', 'netbox_rpki.view_roaobject', 'ipam.view_prefix')
    edit_permissions = ('netbox_rpki.change_roaobjectprefix', 'netbox_rpki.view_roaobject', 'ipam.view_prefix')
    delete_permissions = ('netbox_rpki.delete_roaobjectprefix',)
    list_expected_text = ('10.50.1.0/24', '10.50.2.0/24')
    filter_query = '10.50.2.0/24'
    filter_expected_text = ('10.50.2.0/24',)
    filter_unexpected_text = ('10.50.1.0/24',)
    invalid_form_errors = ('roa_object', 'Select a valid choice.')
    empty_form_errors = ('prefix', 'max_length', 'roa_object', 'This field is required')

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
        return {'prefix': self.prefixes[0], 'prefix_cidr_text': str(self.prefixes[0].prefix), 'max_length': 27, 'roa_object': self.roas[1]}

    def get_invalid_create_data(self):
        return {'max_length': 27, 'roa_object': 999999}

    def get_edit_instance(self):
        return self.roa_prefixes[0]

    def get_valid_edit_data(self):
        return {'prefix': self.prefixes[0], 'prefix_cidr_text': str(self.prefixes[0].prefix), 'max_length': 28, 'roa_object': self.roas[0]}

    def get_delete_instance(self):
        return self.roa_prefixes[2]

    def assert_valid_create_result(self):
        self.assertTrue(RoaPrefix.objects.filter(prefix=self.prefixes[0], roa_object=self.roas[1], max_length=27).exists())

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


class ROAValidationSimulationDetailViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='simulation-view-org', name='Simulation View Org')
        cls.plan = create_test_roa_change_plan(
            name='Simulation View Plan',
            organization=cls.organization,
            summary_json={
                'simulation_run_id': 0,
                'simulation_plan_fingerprint': 'plan-fingerprint-123',
            },
        )
        cls.plan_item = create_test_roa_change_plan_item(
            name='Simulation View Plan Item',
            change_plan=cls.plan,
            action_type=rpki_models.ROAChangePlanAction.CREATE,
            plan_semantic='reshape',
        )
        cls.invalid_plan_item = create_test_roa_change_plan_item(
            name='Simulation View Invalid Item',
            change_plan=cls.plan,
            action_type=rpki_models.ROAChangePlanAction.WITHDRAW,
            plan_semantic='withdraw',
        )
        cls.not_found_plan_item = create_test_roa_change_plan_item(
            name='Simulation View Not Found Item',
            change_plan=cls.plan,
            action_type=rpki_models.ROAChangePlanAction.CREATE,
            plan_semantic='replace',
        )
        cls.simulation_run = create_test_roa_validation_simulation_run(
            name='Simulation View Run',
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
            name='Simulation View Result',
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
            },
        )
        cls.invalid_simulation_result = create_test_roa_validation_simulation_result(
            name='Simulation View Invalid Result',
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
            name='Simulation View Not Found Result',
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

    def test_change_plan_detail_shows_latest_simulation_posture(self):
        self.add_permissions(
            'netbox_rpki.view_roachangeplan',
            'netbox_rpki.view_roachangeplanitem',
            'netbox_rpki.view_roavalidationsimulationrun',
            'netbox_rpki.view_roavalidationsimulationresult',
        )

        response = self.client.get(self.plan.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Latest Simulation Posture')
        self.assertContains(response, 'blocking')
        self.assertContains(response, 'Latest Simulation Is Current')
        self.assertContains(response, 'plan-fingerprint-123')
        self.assertContains(response, 'Simulation Review')
        self.assertContains(response, 'Valid Outcomes')
        self.assertContains(response, 'Invalid Outcomes')
        self.assertContains(response, 'Not Found Outcomes')
        self.assertContains(response, '10.0.0.0/24')
        self.assertContains(response, '10.0.1.0/24')
        self.assertContains(response, '10.0.2.0/24')
        self.assertContains(response, '64496')
        self.assertContains(response, '64497')
        self.assertContains(response, '64498')

    def test_simulation_run_detail_shows_normalized_summary_fields(self):
        self.add_permissions('netbox_rpki.view_roavalidationsimulationrun')

        response = self.client.get(self.simulation_run.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Overall Approval Posture')
        self.assertContains(response, 'Current For Plan')
        self.assertContains(response, 'Partially Constrained')
        self.assertContains(response, 'authorization_broadened_requires_ack')

    def test_simulation_result_detail_shows_operator_explanation_fields(self):
        self.add_permissions('netbox_rpki.view_roavalidationsimulationresult')

        response = self.client.get(self.simulation_result.get_absolute_url())

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Operator Message')
        self.assertContains(response, 'Why It Matters')
        self.assertContains(response, 'Operator Action')
        self.assertContains(response, 'Acknowledge the broader authorization risk before approval.')
