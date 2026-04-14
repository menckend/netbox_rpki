from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import RunBulkRoutingIntentJob
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_organization,
    create_test_prefix,
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

    def test_enqueue_for_organization_deduplicates_existing_active_job(self):
        existing_job = Mock(pk=901)

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
