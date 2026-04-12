from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from tenancy.models import Tenant

from netbox_rpki import models as rpki_models
from netbox_rpki.services import create_roa_change_plan, derive_roa_intents, reconcile_roa_intents, run_routing_intent_pipeline
from netbox_rpki.tests.base import PluginAPITestCase
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_certificate,
    create_test_imported_roa_authorization,
    create_test_organization,
    create_test_prefix,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_roa,
    create_test_roa_change_plan,
    create_test_roa_prefix,
    create_test_routing_intent_profile,
    create_test_roa_intent_override,
)


class RoutingIntentServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='intent-org', name='Intent Org')
        cls.tenant = Tenant.objects.create(name='Intent Tenant', slug='intent-tenant')
        cls.primary_prefix = create_test_prefix('10.55.0.0/24', tenant=cls.tenant, status='active')
        cls.secondary_prefix = create_test_prefix('10.56.0.0/24', tenant=cls.tenant, status='active')
        cls.origin_asn = create_test_asn(65551)
        cls.profile = create_test_routing_intent_profile(
            name='Intent Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query='tenant_id={tenant_id}'.format(tenant_id=cls.tenant.pk),
            asn_selector_query='id={asn_id}'.format(asn_id=cls.origin_asn.pk),
        )
        cls.suppress_override = create_test_roa_intent_override(
            name='Suppress Secondary',
            organization=cls.organization,
            intent_profile=cls.profile,
            action=rpki_models.ROAIntentOverrideAction.SUPPRESS,
            prefix=cls.secondary_prefix,
        )

    def test_derivation_creates_active_and_suppressed_intents(self):
        derivation_run = derive_roa_intents(self.profile)

        intents = list(derivation_run.roa_intents.order_by('prefix_cidr_text'))
        self.assertEqual(derivation_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(derivation_run.prefix_count_scanned, 2)
        self.assertEqual(len(intents), 2)

        self.assertEqual(intents[0].prefix, self.primary_prefix)
        self.assertEqual(intents[0].derived_state, rpki_models.ROAIntentDerivedState.ACTIVE)
        self.assertEqual(intents[0].origin_asn, self.origin_asn)
        self.assertEqual(intents[0].max_length, 24)

        self.assertEqual(intents[1].prefix, self.secondary_prefix)
        self.assertEqual(intents[1].derived_state, rpki_models.ROAIntentDerivedState.SUPPRESSED)
        self.assertEqual(intents[1].applied_override, self.suppress_override)

    def test_reconciliation_flags_overbroad_roa(self):
        derivation_run = derive_roa_intents(self.profile)
        certificate = create_test_certificate(name='Intent Cert', rpki_org=self.organization)
        roa = create_test_roa(name='Published ROA', signed_by=certificate, origin_as=self.origin_asn)
        create_test_roa_prefix(prefix=self.primary_prefix, roa=roa, max_length=26)

        reconciliation_run = reconcile_roa_intents(derivation_run)
        intent_result = reconciliation_run.intent_results.get(roa_intent__prefix=self.primary_prefix)
        published_result = reconciliation_run.published_roa_results.get(roa=roa)
        best_match = derivation_run.roa_intents.get(prefix=self.primary_prefix).candidate_matches.get(is_best_match=True)

        self.assertEqual(best_match.match_kind, rpki_models.ROAIntentMatchKind.LENGTH_BROADER)
        self.assertEqual(intent_result.result_type, rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD)
        self.assertEqual(published_result.result_type, rpki_models.PublishedROAResultType.BROADER_THAN_NEEDED)

    def test_reconciliation_supports_provider_imported_scope(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_snapshot = create_test_provider_snapshot(
            name='Provider Snapshot',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        imported_authorization = create_test_imported_roa_authorization(
            name='Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=self.origin_asn,
            max_length=24,
        )

        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )

        intent_result = reconciliation_run.intent_results.get(roa_intent__prefix=self.primary_prefix)
        published_result = reconciliation_run.published_roa_results.get(imported_authorization=imported_authorization)
        best_match = derivation_run.roa_intents.get(prefix=self.primary_prefix).candidate_matches.get(is_best_match=True)

        self.assertEqual(reconciliation_run.provider_snapshot, provider_snapshot)
        self.assertEqual(intent_result.result_type, rpki_models.ROAIntentResultType.MATCH)
        self.assertEqual(intent_result.best_imported_authorization, imported_authorization)
        self.assertEqual(best_match.imported_authorization, imported_authorization)
        self.assertEqual(published_result.result_type, rpki_models.PublishedROAResultType.MATCHED)

    def test_reconciliation_marks_same_prefix_provider_mismatch_as_replacement(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_snapshot = create_test_provider_snapshot(
            name='Replacement Snapshot',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        replacement_import = create_test_imported_roa_authorization(
            name='Replacement Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65561),
            max_length=26,
            payload_json={'comment': 'replace me'},
        )

        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )

        intent_result = reconciliation_run.intent_results.get(roa_intent__prefix=self.primary_prefix)
        published_result = reconciliation_run.published_roa_results.get(imported_authorization=replacement_import)

        self.assertEqual(intent_result.result_type, rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_OVERBROAD)
        self.assertEqual(intent_result.best_imported_authorization, replacement_import)
        self.assertTrue(intent_result.details_json['replacement_required'])
        self.assertEqual(intent_result.details_json['replacement_reason_code'], 'origin_and_max_length_overbroad')
        self.assertEqual(intent_result.details_json['mismatch_axes'], ['origin_asn', 'max_length'])

        self.assertEqual(
            published_result.result_type,
            rpki_models.PublishedROAResultType.WRONG_ORIGIN_AND_MAX_LENGTH_OVERBROAD,
        )
        self.assertTrue(published_result.details_json['replacement_required'])
        self.assertEqual(published_result.details_json['replacement_reason_code'], 'origin_and_max_length_overbroad')
        self.assertEqual(reconciliation_run.result_summary_json['replacement_required_intent_count'], 1)
        self.assertEqual(reconciliation_run.result_summary_json['replacement_required_published_count'], 1)

    def test_change_plan_creates_create_and_withdraw_actions(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_account = create_test_provider_account(
            name='Plan Provider Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-PLAN',
            ca_handle='ca-plan',
            api_base_url='https://krill.example.invalid',
        )
        provider_snapshot = create_test_provider_snapshot(
            name='Plan Snapshot',
            organization=self.organization,
            provider_account=provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        orphaned_prefix = create_test_prefix('10.99.0.0/24')
        orphaned_asn = create_test_asn(65599)
        create_test_imported_roa_authorization(
            name='Orphaned Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=orphaned_prefix,
            origin_asn=orphaned_asn,
            max_length=24,
        )

        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        plan = create_roa_change_plan(reconciliation_run)

        self.assertEqual(plan.items.filter(action_type=rpki_models.ROAChangePlanAction.CREATE).count(), 1)
        self.assertEqual(plan.items.filter(action_type=rpki_models.ROAChangePlanAction.WITHDRAW).count(), 1)
        self.assertEqual(plan.summary_json['create_count'], 1)
        self.assertEqual(plan.summary_json['withdraw_count'], 1)

    def test_change_plan_creates_replacement_items_for_local_mismatch(self):
        derivation_run = derive_roa_intents(self.profile)
        certificate = create_test_certificate(name='Replacement Local Cert', rpki_org=self.organization)
        replacement_roa = create_test_roa(
            name='Replacement Local ROA',
            signed_by=certificate,
            origin_as=create_test_asn(65562),
        )
        create_test_roa_prefix(prefix=self.primary_prefix, roa=replacement_roa, max_length=26)

        reconciliation_run = reconcile_roa_intents(derivation_run)
        plan = create_roa_change_plan(reconciliation_run)

        create_item = plan.items.get(action_type=rpki_models.ROAChangePlanAction.CREATE)
        withdraw_item = plan.items.get(action_type=rpki_models.ROAChangePlanAction.WITHDRAW)

        self.assertEqual(plan.summary_json['replacement_count'], 1)
        self.assertEqual(plan.summary_json['replacement_create_count'], 1)
        self.assertEqual(plan.summary_json['replacement_withdraw_count'], 1)
        self.assertEqual(
            plan.summary_json['replacement_reason_counts'],
            {'origin_and_max_length_overbroad': 1},
        )
        self.assertIn('wrong origin ASN and an overbroad maxLength', create_item.reason)
        self.assertEqual(withdraw_item.roa, replacement_roa)
        self.assertEqual(withdraw_item.provider_operation, '')
        self.assertEqual(withdraw_item.before_state_json['source'], 'local_roa')
        self.assertEqual(withdraw_item.after_state_json['prefix_cidr_text'], '10.55.0.0/24')

    def test_change_plan_creates_replacement_items_for_provider_mismatch(self):
        derivation_run = derive_roa_intents(self.profile)
        provider_account = create_test_provider_account(
            name='Replacement Provider Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-PLAN-REPLACE',
            ca_handle='ca-plan-replace',
            api_base_url='https://krill.example.invalid',
        )
        provider_snapshot = create_test_provider_snapshot(
            name='Replacement Provider Snapshot',
            organization=self.organization,
            provider_account=provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        replacement_import = create_test_imported_roa_authorization(
            name='Replacement Imported Authorization 2',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=create_test_asn(65563),
            max_length=26,
            payload_json={'comment': 'replacement target'},
        )

        reconciliation_run = reconcile_roa_intents(
            derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=provider_snapshot,
        )
        plan = create_roa_change_plan(reconciliation_run)

        create_item = plan.items.get(action_type=rpki_models.ROAChangePlanAction.CREATE)
        withdraw_item = plan.items.get(action_type=rpki_models.ROAChangePlanAction.WITHDRAW)

        self.assertEqual(plan.summary_json['create_count'], 1)
        self.assertEqual(plan.summary_json['withdraw_count'], 1)
        self.assertEqual(plan.summary_json['replacement_count'], 1)
        self.assertEqual(create_item.provider_operation, rpki_models.ProviderWriteOperation.ADD_ROUTE)
        self.assertEqual(
            create_item.provider_payload_json,
            {'asn': self.origin_asn.asn, 'prefix': '10.55.0.0/24', 'max_length': 24},
        )
        self.assertEqual(withdraw_item.imported_authorization, replacement_import)
        self.assertEqual(withdraw_item.provider_operation, rpki_models.ProviderWriteOperation.REMOVE_ROUTE)
        self.assertEqual(
            withdraw_item.provider_payload_json,
            {
                'asn': replacement_import.origin_asn_value,
                'prefix': '10.55.0.0/24',
                'max_length': 26,
                'comment': 'replacement target',
            },
        )
        self.assertEqual(withdraw_item.before_state_json['replacement_reason_code'], 'origin_and_max_length_overbroad')

    def test_management_command_runs_pipeline_synchronously(self):
        call_command('run_routing_intent_profile', '--profile', str(self.profile.pk))
        self.assertTrue(rpki_models.IntentDerivationRun.objects.filter(intent_profile=self.profile).exists())
        self.assertTrue(rpki_models.ROAReconciliationRun.objects.filter(intent_profile=self.profile).exists())

    def test_management_command_supports_provider_imported_scope(self):
        provider_snapshot = create_test_provider_snapshot(
            name='Command Snapshot',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_imported_roa_authorization(
            name='Command Imported Authorization',
            provider_snapshot=provider_snapshot,
            organization=self.organization,
            prefix=self.primary_prefix,
            origin_asn=self.origin_asn,
            max_length=24,
        )

        call_command(
            'run_routing_intent_profile',
            '--profile',
            str(self.profile.pk),
            '--comparison-scope',
            rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            '--provider-snapshot',
            str(provider_snapshot.pk),
        )
        self.assertTrue(
            rpki_models.ROAReconciliationRun.objects.filter(
                intent_profile=self.profile,
                provider_snapshot=provider_snapshot,
                comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            ).exists()
        )


class RoutingIntentProfileRunActionAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='intent-api-org', name='Intent API Org')
        cls.profile = create_test_routing_intent_profile(
            name='Intent API Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        )

    def test_run_action_enqueues_job(self):
        self.add_permissions(
            'netbox_rpki.view_routingintentprofile',
            'netbox_rpki.change_routingintentprofile',
        )
        url = reverse('plugins-api:netbox_rpki-api:routingintentprofile-run', kwargs={'pk': self.profile.pk})

        class StubJob:
            pk = 321
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/321/'

        with patch('netbox_rpki.api.views.RunRoutingIntentProfileJob.enqueue', return_value=StubJob()) as enqueue_mock:
            response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['job']['id'], 321)
        enqueue_mock.assert_called_once_with(
            instance=self.profile,
            user=self.user,
            profile_pk=self.profile.pk,
            comparison_scope='local_roa_records',
            provider_snapshot_pk=None,
        )

    def test_run_action_passes_provider_snapshot_parameters(self):
        self.add_permissions(
            'netbox_rpki.view_routingintentprofile',
            'netbox_rpki.change_routingintentprofile',
        )
        provider_snapshot = create_test_provider_snapshot(
            name='API Snapshot',
            organization=self.organization,
        )
        url = reverse('plugins-api:netbox_rpki-api:routingintentprofile-run', kwargs={'pk': self.profile.pk})

        class StubJob:
            pk = 654
            status = 'queued'

            @staticmethod
            def get_absolute_url():
                return '/core/jobs/654/'

        with patch('netbox_rpki.api.views.RunRoutingIntentProfileJob.enqueue', return_value=StubJob()) as enqueue_mock:
            response = self.client.post(
                url,
                {
                    'comparison_scope': rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
                    'provider_snapshot': provider_snapshot.pk,
                },
                format='json',
                **self.header,
            )

        self.assertHttpStatus(response, 200)
        enqueue_mock.assert_called_once_with(
            instance=self.profile,
            user=self.user,
            profile_pk=self.profile.pk,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot_pk=provider_snapshot.pk,
        )


class ROAReconciliationRunCreatePlanAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='intent-plan-api-org', name='Intent Plan API Org')
        cls.profile = create_test_routing_intent_profile(
            name='Intent Plan Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
        )
        cls.derivation_run = derive_roa_intents(cls.profile)
        cls.reconciliation_run = reconcile_roa_intents(cls.derivation_run)

    def test_create_plan_action_creates_plan(self):
        self.add_permissions(
            'netbox_rpki.view_roareconciliationrun',
            'netbox_rpki.change_routingintentprofile',
        )
        url = reverse('plugins-api:netbox_rpki-api:roareconciliationrun-create-plan', kwargs={'pk': self.reconciliation_run.pk})

        response = self.client.post(url, {}, format='json', **self.header)

        self.assertHttpStatus(response, 200)
        self.assertTrue(rpki_models.ROAChangePlan.objects.filter(source_reconciliation_run=self.reconciliation_run).exists())
        self.assertIn('item_count', response.data)