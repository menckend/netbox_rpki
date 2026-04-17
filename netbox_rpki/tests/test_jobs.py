import json
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock, patch

from core.models import Job
from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import ExecuteIrrChangePlanJob, RunBulkRoutingIntentJob, SyncProviderAccountJob
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_irr_change_plan,
    create_test_irr_write_execution,
    create_test_organization,
    create_test_prefix,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_routing_intent_profile,
    create_test_routing_intent_template,
    create_test_routing_intent_template_binding,
    create_test_routing_intent_template_rule,
)


class RunBulkRoutingIntentJobTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='bulk-job-org', name='Bulk Job Org')
        cls.prefix = create_test_prefix('10.89.0.0/24', status='active')
        cls.origin_asn = create_test_asn(65589)
        cls.profile = create_test_routing_intent_profile(
            name='Bulk Job Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.prefix.pk}',
            asn_selector_query=f'id={cls.origin_asn.pk}',
        )
        cls.template = create_test_routing_intent_template(
            name='Bulk Job Template',
            organization=cls.organization,
            status=rpki_models.RoutingIntentTemplateStatus.ACTIVE,
        )
        create_test_routing_intent_template_rule(
            name='Bulk Job Include',
            template=cls.template,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        cls.binding = create_test_routing_intent_template_binding(
            name='Bulk Job Binding',
            template=cls.template,
            intent_profile=cls.profile,
            origin_asn_override=cls.origin_asn,
            prefix_selector_query=f'id={cls.prefix.pk}',
        )

    def _create_job(self, name):
        return Job.objects.create(name=name, status='pending', job_id=uuid4(), data={})

    def test_enqueue_for_organization_deduplicates_existing_active_job(self):
        existing_job = self._create_job('Bulk Routing Intent Run [existing]')

        with patch.object(
            RunBulkRoutingIntentJob,
            'get_active_job_for_request',
            return_value=existing_job,
        ):
            job, created = RunBulkRoutingIntentJob.enqueue_for_organization(
                self.organization,
                profiles=(self.profile,),
                bindings=(self.binding,),
            )

        self.assertIs(job, existing_job)
        self.assertFalse(created)
        execution_record = rpki_models.JobExecutionRecord.objects.get(job=existing_job)
        self.assertEqual(execution_record.disposition, rpki_models.JobExecutionDisposition.MERGED)
        self.assertEqual(execution_record.job_class, 'RunBulkRoutingIntentJob')
        self.assertEqual(execution_record.request_payload_json['organization_pk'], self.organization.pk)

    def test_enqueue_for_organization_records_enqueued_execution_lineage(self):
        queued_job = self._create_job('Bulk Routing Intent Run [queued]')

        with patch.object(RunBulkRoutingIntentJob, 'enqueue', return_value=queued_job):
            job, created = RunBulkRoutingIntentJob.enqueue_for_organization(
                self.organization,
                profiles=(self.profile,),
                bindings=(self.binding,),
            )

        self.assertIs(job, queued_job)
        self.assertTrue(created)
        execution_record = rpki_models.JobExecutionRecord.objects.get(job=queued_job)
        self.assertEqual(execution_record.disposition, rpki_models.JobExecutionDisposition.ENQUEUED)
        self.assertEqual(execution_record.job_class, 'RunBulkRoutingIntentJob')
        self.assertEqual(execution_record.request_payload_json['organization_pk'], self.organization.pk)
        self.assertIn('baseline_fingerprint', execution_record.request_payload_json)

    def test_run_records_bulk_run_in_job_data(self):
        bulk_run = rpki_models.BulkIntentRun.objects.create(
            name='Bulk Job Result',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        save_mock = Mock()
        runner = RunBulkRoutingIntentJob(SimpleNamespace(data=None, save=save_mock))
        runner.logger = Mock()

        with patch('netbox_rpki.jobs.run_bulk_routing_intent_pipeline', return_value=bulk_run) as run_mock:
            runner.run(
                organization_pk=self.organization.pk,
                profile_pks=(self.profile.pk,),
                binding_pks=(self.binding.pk,),
                comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
                provider_snapshot_pk=None,
                create_change_plans=True,
                run_name='Queued Bulk Run',
            )

        run_mock.assert_called_once()
        self.assertEqual(runner.job.data['organization_pk'], self.organization.pk)
        self.assertEqual(runner.job.data['bulk_intent_run_pk'], bulk_run.pk)
        self.assertEqual(runner.job.data['profile_pks'], [self.profile.pk])
        self.assertEqual(runner.job.data['binding_pks'], [self.binding.pk])
        self.assertTrue(runner.job.data['create_change_plans'])
        save_mock.assert_called_once_with(update_fields=('data',))
        self.assertEqual(runner.logger.info.call_count, 2)
        start_event = json.loads(runner.logger.info.call_args_list[0].args[0])
        complete_event = json.loads(runner.logger.info.call_args_list[1].args[0])
        self.assertEqual(start_event['event'], 'job.run.start')
        self.assertEqual(start_event['subsystem'], 'jobs')
        self.assertEqual(start_event['job_class'], 'RunBulkRoutingIntentJob')
        self.assertEqual(start_event['organization_id'], self.organization.pk)
        self.assertEqual(complete_event['event'], 'job.run.complete')
        self.assertEqual(complete_event['bulk_intent_run_pk'], bulk_run.pk)


class ExecuteIrrChangePlanJobTestCase(TestCase):
    def setUp(self):
        self.plan = create_test_irr_change_plan(name='Replay-safe IRR Plan')

    def _create_job(self, name):
        return Job.objects.create(name=name, status='pending', job_id=uuid4(), data={})

    def test_run_records_replayed_execution_lineage(self):
        execution = create_test_irr_write_execution(
            change_plan=self.plan,
            execution_mode=rpki_models.IrrWriteExecutionMode.APPLY,
            request_fingerprint='replay-fingerprint',
        )
        job = self._create_job(ExecuteIrrChangePlanJob.get_job_name(self.plan, execution_mode=rpki_models.IrrWriteExecutionMode.APPLY))
        save_mock = Mock()
        job.save = save_mock
        runner = ExecuteIrrChangePlanJob(job)
        runner.logger = Mock()

        with patch(
            'netbox_rpki.jobs.apply_irr_change_plan',
            return_value=(
                execution,
                {
                    'replayed': True,
                    'replayed_execution_pk': execution.pk,
                    'request_fingerprint': execution.request_fingerprint,
                },
            ),
        ) as apply_mock:
            runner.run(
                change_plan_pk=self.plan.pk,
                execution_mode=rpki_models.IrrWriteExecutionMode.APPLY,
            )

        apply_mock.assert_called_once()
        replay_record = rpki_models.JobExecutionRecord.objects.get(
            job_class='ExecuteIrrChangePlanJob',
            disposition=rpki_models.JobExecutionDisposition.REPLAYED,
        )
        self.assertEqual(replay_record.job_name, ExecuteIrrChangePlanJob.get_job_name(self.plan, execution_mode=rpki_models.IrrWriteExecutionMode.APPLY))
        self.assertEqual(replay_record.resolution_payload_json['irr_write_execution_pk'], execution.pk)


class SyncProviderAccountJobTestCase(TestCase):
    def setUp(self):
        self.organization = create_test_organization(org_id='provider-sync-job-org', name='Provider Sync Job Org')
        self.provider_account = create_test_provider_account(
            name='Provider Sync Job Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-JOB',
            ca_handle='job-ca',
            api_base_url='https://krill.example.invalid',
            api_key='job-token',
        )

    def _create_job(self, name):
        return Job.objects.create(name=name, status='pending', job_id=uuid4(), data={})

    def test_enqueue_allows_resume_when_running_sync_has_no_active_job(self):
        running_snapshot = create_test_provider_snapshot(
            name='Running Resume Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            status=rpki_models.ValidationRunStatus.RUNNING,
        )
        rpki_models.ProviderSyncRun.objects.create(
            name='Running Resume Sync',
            organization=self.organization,
            provider_account=self.provider_account,
            provider_snapshot=running_snapshot,
            status=rpki_models.ValidationRunStatus.RUNNING,
            summary_json={
                'checkpoint': {
                    'resume_supported': True,
                    'current_family': rpki_models.ProviderSyncFamily.CHILD_LINKS,
                },
            },
        )
        queued_job = self._create_job('Provider Sync Resume Job')

        with patch.object(SyncProviderAccountJob, 'enqueue', return_value=queued_job):
            job, created = SyncProviderAccountJob.enqueue_for_provider_account(self.provider_account)

        self.assertIs(job, queued_job)
        self.assertTrue(created)
        execution_record = rpki_models.JobExecutionRecord.objects.get(job=queued_job)
        self.assertEqual(execution_record.disposition, rpki_models.JobExecutionDisposition.ENQUEUED)
