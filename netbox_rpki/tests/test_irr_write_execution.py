import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import apply_irr_change_plan, preview_irr_change_plan
from netbox_rpki.tests.utils import (
    create_test_imported_irr_route_object,
    create_test_irr_change_plan,
    create_test_irr_change_plan_item,
    create_test_irr_source,
    create_test_organization,
)


class _MockHttpResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode('utf-8')

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class IrrWriteExecutionServiceTestCase(TestCase):
    def setUp(self):
        self.organization = create_test_organization(org_id='irr-write-org', name='IRR Write Org')
        self.source = create_test_irr_source(
            name='Writable IRR',
            slug='writable-irr',
            organization=self.organization,
            write_support_mode=rpki_models.IrrWriteSupportMode.APPLY_SUPPORTED,
            api_key='override-pass',
            query_base_url='http://127.0.0.1:6080',
        )
        self.plan = create_test_irr_change_plan(
            name='IRR Write Plan',
            organization=self.organization,
            source=self.source,
            write_support_mode=rpki_models.IrrWriteSupportMode.APPLY_SUPPORTED,
            status=rpki_models.IrrChangePlanStatus.READY,
            summary_json={'latest_execution': None},
        )

    def test_preview_irr_change_plan_builds_irrd_submit_payloads(self):
        imported_route = create_test_imported_irr_route_object(
            snapshot=self.plan.snapshot,
            source=self.source,
            prefix='198.51.100.0/24',
            origin_asn='AS64501',
            stable_key='route:198.51.100.0/24AS64501',
            rpsl_pk='198.51.100.0/24AS64501',
            object_text='route: 198.51.100.0/24\norigin: AS64501\nmnt-by: LOCAL-IRR-MNT\nsource: LOCAL-IRR\n',
        )
        create_test_irr_change_plan_item(
            name='Create Route',
            change_plan=self.plan,
            action=rpki_models.IrrChangePlanAction.CREATE,
            after_state_json={
                'object_class': 'route',
                'prefix': '203.0.113.0/24',
                'origin_asn': 'AS64500',
                'stable_key': 'route:203.0.113.0/24AS64500',
            },
        )
        create_test_irr_change_plan_item(
            name='Delete Route',
            change_plan=self.plan,
            action=rpki_models.IrrChangePlanAction.DELETE,
            imported_route_object=imported_route,
            before_state_json={
                'object_class': 'route',
                'prefix': '198.51.100.0/24',
                'origin_asn': 'AS64501',
                'source_database_label': 'LOCAL-IRR',
                'stable_key': 'route:198.51.100.0/24AS64501',
            },
        )

        execution, payload = preview_irr_change_plan(self.plan, requested_by='preview-user')

        self.assertEqual(execution.execution_mode, rpki_models.IrrWriteExecutionMode.PREVIEW)
        self.assertEqual(execution.status, rpki_models.IrrWriteExecutionStatus.COMPLETED)
        self.assertEqual(payload['actionable_item_count'], 2)
        create_result = next(item for item in payload['item_results'] if item['action'] == rpki_models.IrrChangePlanAction.CREATE)
        delete_result = next(item for item in payload['item_results'] if item['action'] == rpki_models.IrrChangePlanAction.DELETE)
        self.assertEqual(create_result['operations'][0]['method'], 'POST')
        self.assertEqual(delete_result['operations'][0]['method'], 'DELETE')
        self.assertEqual(delete_result['operations'][0]['body']['override'], 'override-pass')
        self.assertEqual(self.plan.summary_json['latest_execution']['id'], execution.pk)

    @patch('netbox_rpki.services.irr_write.urlopen')
    def test_apply_irr_change_plan_records_completed_execution(self, urlopen_mock):
        urlopen_mock.side_effect = [
            _MockHttpResponse({'summary': {'objects_found': 1, 'successful': 1, 'failed': 0}}),
            _MockHttpResponse({'summary': {'objects_found': 1, 'successful': 1, 'failed': 0}}),
        ]
        imported_route = create_test_imported_irr_route_object(
            snapshot=self.plan.snapshot,
            source=self.source,
            prefix='198.51.100.0/24',
            origin_asn='AS64501',
            stable_key='route:198.51.100.0/24AS64501',
            rpsl_pk='198.51.100.0/24AS64501',
            object_text='route: 198.51.100.0/24\norigin: AS64501\nmnt-by: LOCAL-IRR-MNT\nsource: LOCAL-IRR\n',
        )
        create_test_irr_change_plan_item(
            name='Create Route',
            change_plan=self.plan,
            action=rpki_models.IrrChangePlanAction.CREATE,
            after_state_json={
                'object_class': 'route',
                'prefix': '203.0.113.0/24',
                'origin_asn': 'AS64500',
                'stable_key': 'route:203.0.113.0/24AS64500',
            },
        )
        create_test_irr_change_plan_item(
            name='Delete Route',
            change_plan=self.plan,
            action=rpki_models.IrrChangePlanAction.DELETE,
            imported_route_object=imported_route,
            before_state_json={
                'object_class': 'route',
                'prefix': '198.51.100.0/24',
                'origin_asn': 'AS64501',
                'source_database_label': 'LOCAL-IRR',
                'stable_key': 'route:198.51.100.0/24AS64501',
            },
        )

        execution, response_payload = apply_irr_change_plan(self.plan, requested_by='apply-user')

        self.assertEqual(execution.execution_mode, rpki_models.IrrWriteExecutionMode.APPLY)
        self.assertEqual(execution.status, rpki_models.IrrWriteExecutionStatus.COMPLETED)
        self.assertEqual(self.plan.status, rpki_models.IrrChangePlanStatus.COMPLETED)
        self.assertEqual(len(response_payload['item_results']), 2)
        first_request = urlopen_mock.call_args_list[0].args[0]
        self.assertEqual(first_request.method, 'POST')
        posted_body = json.loads(first_request.data.decode('utf-8'))
        self.assertEqual(posted_body['override'], 'override-pass')

    @patch('netbox_rpki.services.irr_write.urlopen')
    def test_apply_irr_change_plan_records_partial_execution(self, urlopen_mock):
        urlopen_mock.side_effect = [
            _MockHttpResponse({'summary': {'objects_found': 1, 'successful': 1, 'failed': 0}}),
            _MockHttpResponse({
                'summary': {'objects_found': 1, 'successful': 0, 'failed': 1},
                'objects': [{'error_messages': ['Delete rejected']}],
            }),
        ]
        imported_route = create_test_imported_irr_route_object(
            snapshot=self.plan.snapshot,
            source=self.source,
            prefix='198.51.100.0/24',
            origin_asn='AS64501',
            stable_key='route:198.51.100.0/24AS64501',
            rpsl_pk='198.51.100.0/24AS64501',
            object_text='route: 198.51.100.0/24\norigin: AS64501\nmnt-by: LOCAL-IRR-MNT\nsource: LOCAL-IRR\n',
        )
        create_test_irr_change_plan_item(
            name='Create Route',
            change_plan=self.plan,
            action=rpki_models.IrrChangePlanAction.CREATE,
            after_state_json={
                'object_class': 'route',
                'prefix': '203.0.113.0/24',
                'origin_asn': 'AS64500',
                'stable_key': 'route:203.0.113.0/24AS64500',
            },
        )
        create_test_irr_change_plan_item(
            name='Delete Route',
            change_plan=self.plan,
            action=rpki_models.IrrChangePlanAction.DELETE,
            imported_route_object=imported_route,
            before_state_json={
                'object_class': 'route',
                'prefix': '198.51.100.0/24',
                'origin_asn': 'AS64501',
                'source_database_label': 'LOCAL-IRR',
                'stable_key': 'route:198.51.100.0/24AS64501',
            },
        )

        execution, _ = apply_irr_change_plan(self.plan, requested_by='apply-user')

        self.assertEqual(execution.status, rpki_models.IrrWriteExecutionStatus.PARTIAL)
        self.assertEqual(self.plan.status, rpki_models.IrrChangePlanStatus.FAILED)
        self.assertIn('Delete rejected', execution.error)


class ExecuteIrrChangePlanCommandTestCase(TestCase):
    def setUp(self):
        organization = create_test_organization(org_id='irr-exec-cmd-org', name='IRR Exec Cmd Org')
        source = create_test_irr_source(
            name='Cmd IRR',
            slug='cmd-irr',
            organization=organization,
            api_key='override-pass',
        )
        self.plan = create_test_irr_change_plan(
            name='Command Plan',
            organization=organization,
            source=source,
            status=rpki_models.IrrChangePlanStatus.READY,
        )

    def test_execute_irr_change_plan_command_runs_preview(self):
        with patch('netbox_rpki.management.commands.execute_irr_change_plan.preview_irr_change_plan') as preview_mock:
            execution = rpki_models.IrrWriteExecution(name='Preview Execution')
            execution.pk = 901
            preview_mock.return_value = (execution, {})
            stdout = StringIO()

            call_command(
                'execute_irr_change_plan',
                '--change-plan',
                str(self.plan.pk),
                '--mode',
                rpki_models.IrrWriteExecutionMode.PREVIEW,
                stdout=stdout,
            )

        preview_mock.assert_called_once_with(self.plan)
        self.assertIn('Completed IRR change plan preview execution 901', stdout.getvalue())

    def test_execute_irr_change_plan_command_enqueues_apply(self):
        with patch(
            'netbox_rpki.management.commands.execute_irr_change_plan.ExecuteIrrChangePlanJob.enqueue_for_change_plan',
            return_value=(type('JobRef', (), {'pk': 45})(), True),
        ) as enqueue_mock:
            stdout = StringIO()
            call_command(
                'execute_irr_change_plan',
                '--change-plan',
                str(self.plan.pk),
                '--mode',
                rpki_models.IrrWriteExecutionMode.APPLY,
                '--enqueue',
                stdout=stdout,
            )

        enqueue_mock.assert_called_once_with(
            self.plan,
            execution_mode=rpki_models.IrrWriteExecutionMode.APPLY,
        )
        self.assertIn('Enqueued job 45', stdout.getvalue())
