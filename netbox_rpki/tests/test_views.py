from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils.formats import date_format
from django.utils import timezone

from netbox_rpki import filtersets, forms, tables, views
from netbox_rpki.models import Certificate, CertificateAsn, CertificatePrefix, Organization, Roa, RoaPrefix
from netbox_rpki.object_registry import SIMPLE_DETAIL_VIEW_OBJECT_SPECS, VIEW_OBJECT_SPECS, get_object_spec
from netbox_rpki.tests.registry_scenarios import _build_instance_for_spec
from netbox_rpki.tests.base import PluginViewTestCase
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_certificate,
    create_test_certificate_asn,
    create_test_certificate_prefix,
    create_test_intent_derivation_run,
    create_test_organization,
    create_test_prefix,
    create_test_published_roa_result,
    create_test_rir,
    create_test_roa,
    create_test_roa_intent,
    create_test_roa_intent_match,
    create_test_roa_intent_override,
    create_test_roa_intent_result,
    create_test_roa_reconciliation_run,
    create_test_roa_prefix,
    create_test_routing_intent_profile,
    create_test_routing_intent_rule,
    create_test_provider_account,
)
from utilities.testing.utils import post_data
from unittest.mock import patch


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


class OperationsDashboardViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='operations-dashboard-org', name='Operations Dashboard Org')
        cls.failed_provider_account = create_test_provider_account(
            name='Failed Operations Account',
            organization=cls.organization,
            org_handle='ORG-OPS-FAILED',
            sync_interval=60,
            last_successful_sync=timezone.now() - timedelta(days=1),
            last_sync_status='failed',
        )
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

    def test_operations_dashboard_surfaces_sync_and_expiry_issues(self):
        self.add_permissions(
            'netbox_rpki.view_rpkiprovideraccount',
            'netbox_rpki.view_roa',
            'netbox_rpki.view_certificate',
        )

        response = self.client.get(reverse('plugins:netbox_rpki:operations_dashboard'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Operations Dashboard')
        self.assertContains(response, self.failed_provider_account.name)
        self.assertContains(response, self.stale_provider_account.name)
        self.assertNotContains(response, self.healthy_provider_account.name)
        self.assertContains(response, self.expiring_roa.name)
        self.assertNotContains(response, self.future_roa.name)
        self.assertContains(response, self.expiring_certificate.name)
        self.assertNotContains(response, self.future_certificate.name)
        self.assertContains(response, 'Expires in 7 day(s)')
        self.assertContains(response, 'Expires in 14 day(s)')


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
        self.assertContains(response, 'ROA Intent Results')
        self.assertContains(response, 'Published ROA Results')
        self.assertContains(response, 'Dashboard Intent Result')
        self.assertContains(response, 'Dashboard Published Result')

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
