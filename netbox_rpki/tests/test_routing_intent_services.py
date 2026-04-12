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
    create_test_roa_change_plan_matrix,
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
        self.assertTrue(reconciliation_run.lint_runs.exists())
        self.assertIn('lint_run_id', reconciliation_run.result_summary_json)

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

    def test_change_plan_creation_runs_lint_and_simulation_analysis(self):
        derivation_run = derive_roa_intents(self.profile)
        certificate = create_test_certificate(name='Analysis Local Cert', rpki_org=self.organization)
        replacement_roa = create_test_roa(
            name='Analysis Local ROA',
            signed_by=certificate,
            origin_as=create_test_asn(65564),
        )
        create_test_roa_prefix(prefix=self.primary_prefix, roa=replacement_roa, max_length=26)

        reconciliation_run = reconcile_roa_intents(derivation_run)
        plan = create_roa_change_plan(reconciliation_run)

        self.assertTrue(reconciliation_run.lint_runs.exists())
        self.assertTrue(plan.lint_runs.exists())
        self.assertTrue(plan.simulation_runs.exists())
        self.assertIn('lint_run_id', reconciliation_run.result_summary_json)
        self.assertIn('lint_run_id', plan.summary_json)
        self.assertIn('simulation_run_id', plan.summary_json)

        lint_run = plan.lint_runs.get()
        simulation_run = plan.simulation_runs.get()
        self.assertGreater(lint_run.finding_count, 0)
        self.assertEqual(simulation_run.result_count, plan.items.count())
        self.assertGreaterEqual(simulation_run.predicted_valid_count, 1)

    def test_change_plan_items_record_plan_semantics(self):
        scenario = create_test_roa_change_plan_matrix()

        local_semantics = list(
            scenario.local_plan.items.order_by('name').values_list('plan_semantic', flat=True)
        )
        provider_semantics = list(
            scenario.provider_plan.items.order_by('name').values_list('plan_semantic', flat=True)
        )

        self.assertEqual(local_semantics.count(rpki_models.ROAChangePlanItemSemantic.CREATE), 1)
        self.assertEqual(local_semantics.count(rpki_models.ROAChangePlanItemSemantic.WITHDRAW), 1)
        self.assertEqual(local_semantics.count(rpki_models.ROAChangePlanItemSemantic.REPLACE), 2)
        self.assertEqual(provider_semantics.count(rpki_models.ROAChangePlanItemSemantic.CREATE), 1)
        self.assertEqual(provider_semantics.count(rpki_models.ROAChangePlanItemSemantic.WITHDRAW), 1)
        self.assertEqual(provider_semantics.count(rpki_models.ROAChangePlanItemSemantic.REPLACE), 2)
        self.assertEqual(
            scenario.provider_plan.summary_json['plan_semantic_counts'],
            {
                rpki_models.ROAChangePlanItemSemantic.CREATE: 1,
                rpki_models.ROAChangePlanItemSemantic.REPLACE: 2,
                rpki_models.ROAChangePlanItemSemantic.WITHDRAW: 1,
            },
        )

    def test_reconciliation_summary_stays_consistent_across_local_and_provider_scopes(self):
        scenario = create_test_roa_change_plan_matrix()

        local_summary = scenario.local_reconciliation_run.result_summary_json
        provider_summary = scenario.provider_reconciliation_run.result_summary_json

        self.assertEqual(local_summary['comparison_scope'], rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS)
        self.assertEqual(provider_summary['comparison_scope'], rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED)
        self.assertIsNone(local_summary['provider_snapshot_id'])
        self.assertEqual(provider_summary['provider_snapshot_id'], scenario.provider_snapshot.pk)

        self.assertEqual(local_summary['intent_result_types'], provider_summary['intent_result_types'])
        self.assertEqual(local_summary['published_result_types'], provider_summary['published_result_types'])
        self.assertEqual(local_summary['best_match_kinds'], provider_summary['best_match_kinds'])
        self.assertEqual(local_summary['replacement_required_intent_count'], 1)
        self.assertEqual(local_summary['replacement_required_published_count'], 1)
        self.assertEqual(provider_summary['replacement_required_intent_count'], 1)
        self.assertEqual(provider_summary['replacement_required_published_count'], 1)

    def test_mixed_change_plan_counts_cover_create_withdraw_and_replacement_combinations(self):
        scenario = create_test_roa_change_plan_matrix()

        local_plan = scenario.local_plan
        provider_plan = scenario.provider_plan

        self.assertEqual(local_plan.summary_json['create_count'], 2)
        self.assertEqual(local_plan.summary_json['withdraw_count'], 2)
        self.assertEqual(local_plan.summary_json['replacement_count'], 1)
        self.assertEqual(local_plan.summary_json['replacement_create_count'], 1)
        self.assertEqual(local_plan.summary_json['replacement_withdraw_count'], 1)
        self.assertEqual(local_plan.summary_json['replacement_reason_counts'], {'origin_and_max_length_overbroad': 1})
        self.assertEqual(local_plan.items.filter(action_type=rpki_models.ROAChangePlanAction.CREATE).count(), 2)
        self.assertEqual(local_plan.items.filter(action_type=rpki_models.ROAChangePlanAction.WITHDRAW).count(), 2)

        self.assertEqual(provider_plan.summary_json['create_count'], 2)
        self.assertEqual(provider_plan.summary_json['withdraw_count'], 2)
        self.assertEqual(provider_plan.summary_json['replacement_count'], 1)
        self.assertEqual(provider_plan.summary_json['replacement_create_count'], 1)
        self.assertEqual(provider_plan.summary_json['replacement_withdraw_count'], 1)
        self.assertEqual(provider_plan.summary_json['replacement_reason_counts'], {'origin_and_max_length_overbroad': 1})
        self.assertTrue(provider_plan.summary_json['provider_backed'])
        self.assertEqual(provider_plan.summary_json['provider_account_id'], scenario.provider_account.pk)
        self.assertEqual(provider_plan.summary_json['provider_snapshot_id'], scenario.provider_snapshot.pk)
        self.assertEqual(provider_plan.items.filter(action_type=rpki_models.ROAChangePlanAction.CREATE).count(), 2)
        self.assertEqual(provider_plan.items.filter(action_type=rpki_models.ROAChangePlanAction.WITHDRAW).count(), 2)

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

    def test_summary_action_returns_aggregate_counts(self):
        self.add_permissions('netbox_rpki.view_roareconciliationrun')
        url = reverse('plugins-api:netbox_rpki-api:roareconciliationrun-summary')

        response = self.client.get(url, **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('total_runs', response.data)
        self.assertIn('replacement_required_intent_total', response.data)
        self.assertIn('lint_warning_total', response.data)
