import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import apply_irr_change_plan, preview_irr_change_plan
from netbox_rpki.tests.utils import (
    create_test_authored_as_set,
    create_test_authored_as_set_member,
    create_test_imported_irr_route_object,
    create_test_imported_irr_route_set,
    create_test_imported_irr_route_set_member,
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
    def test_apply_irr_change_plan_reuses_matching_execution_when_replay_safe(self, urlopen_mock):
        urlopen_mock.return_value = _MockHttpResponse({'summary': {'objects_found': 1, 'successful': 1, 'failed': 0}})
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

        first_execution, first_payload = apply_irr_change_plan(self.plan, requested_by='apply-user', replay_safe=True)
        second_execution, second_payload = apply_irr_change_plan(self.plan, requested_by='apply-user', replay_safe=True)

        self.assertEqual(first_execution.pk, second_execution.pk)
        self.assertEqual(urlopen_mock.call_count, 1)
        self.assertFalse(first_payload.get('replayed', False))
        self.assertTrue(second_payload['replayed'])
        self.assertEqual(second_payload['replayed_execution_pk'], first_execution.pk)
        self.assertEqual(second_payload['request_fingerprint'], first_execution.request_fingerprint)

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

    def test_preview_irr_change_plan_builds_route_set_modify_payloads(self):
        route_set = create_test_imported_irr_route_set(
            snapshot=self.plan.snapshot,
            source=self.source,
            stable_key='route_set:AS64500:RS-EDGE',
            rpsl_pk='AS64500:RS-EDGE',
            set_name='AS64500:RS-EDGE',
            object_text=(
                'route-set: AS64500:RS-EDGE\n'
                'descr: Example route set\n'
                'mnt-by: LOCAL-IRR-MNT\n'
                'members: 198.51.100.0/24\n'
                'source: LOCAL-IRR\n'
            ),
        )
        create_test_imported_irr_route_set_member(
            snapshot=self.plan.snapshot,
            source=self.source,
            parent_route_set=route_set,
            member_text='198.51.100.0/24',
            normalized_prefix='198.51.100.0/24',
        )
        create_test_irr_change_plan_item(
            name='Modify Route Set',
            change_plan=self.plan,
            object_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            action=rpki_models.IrrChangePlanAction.MODIFY,
            stable_object_key='route:203.0.113.0/24AS64500|AS64500:RS-EDGE',
            source_object_key=route_set.stable_key,
            before_state_json={
                'object_class': 'route-set',
                'set_name': 'AS64500:RS-EDGE',
                'rpsl_pk': 'AS64500:RS-EDGE',
                'stable_key': route_set.stable_key,
                'members': ['198.51.100.0/24'],
                'mp_members': [],
                'existing_object_text': route_set.object_text,
            },
            after_state_json={
                'object_class': 'route-set',
                'set_name': 'AS64500:RS-EDGE',
                'rpsl_pk': 'AS64500:RS-EDGE',
                'stable_key': route_set.stable_key,
                'members': ['198.51.100.0/24', '203.0.113.0/24'],
                'mp_members': [],
                'existing_object_text': route_set.object_text,
            },
        )

        execution, payload = preview_irr_change_plan(self.plan, requested_by='preview-user')

        self.assertEqual(execution.status, rpki_models.IrrWriteExecutionStatus.COMPLETED)
        self.assertEqual(payload['actionable_item_count'], 1)
        item_result = payload['item_results'][0]
        self.assertEqual(item_result['action'], rpki_models.IrrChangePlanAction.MODIFY)
        self.assertEqual(item_result['operations'][0]['method'], 'POST')
        object_text = item_result['operations'][0]['body']['objects'][0]['object_text']
        self.assertIn('route-set: AS64500:RS-EDGE', object_text)
        self.assertIn('members:         198.51.100.0/24, 203.0.113.0/24', object_text)

    @patch('netbox_rpki.services.irr_write.urlopen')
    def test_apply_irr_change_plan_submits_route_set_modify_payload(self, urlopen_mock):
        urlopen_mock.return_value = _MockHttpResponse({'summary': {'objects_found': 1, 'successful': 1, 'failed': 0}})
        route_set = create_test_imported_irr_route_set(
            snapshot=self.plan.snapshot,
            source=self.source,
            stable_key='route_set:AS64500:RS-EDGE',
            rpsl_pk='AS64500:RS-EDGE',
            set_name='AS64500:RS-EDGE',
            object_text=(
                'route-set: AS64500:RS-EDGE\n'
                'descr: Example route set\n'
                'mnt-by: LOCAL-IRR-MNT\n'
                'members: 198.51.100.0/24\n'
                'source: LOCAL-IRR\n'
            ),
        )
        create_test_irr_change_plan_item(
            name='Modify Route Set',
            change_plan=self.plan,
            object_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            action=rpki_models.IrrChangePlanAction.MODIFY,
            stable_object_key='route:203.0.113.0/24AS64500|AS64500:RS-EDGE',
            source_object_key=route_set.stable_key,
            before_state_json={
                'object_class': 'route-set',
                'set_name': 'AS64500:RS-EDGE',
                'rpsl_pk': 'AS64500:RS-EDGE',
                'stable_key': route_set.stable_key,
                'members': ['198.51.100.0/24'],
                'mp_members': [],
                'existing_object_text': route_set.object_text,
            },
            after_state_json={
                'object_class': 'route-set',
                'set_name': 'AS64500:RS-EDGE',
                'rpsl_pk': 'AS64500:RS-EDGE',
                'stable_key': route_set.stable_key,
                'members': ['198.51.100.0/24', '203.0.113.0/24'],
                'mp_members': [],
                'existing_object_text': route_set.object_text,
            },
        )

        execution, _response_payload = apply_irr_change_plan(self.plan, requested_by='apply-user')

        self.assertEqual(execution.status, rpki_models.IrrWriteExecutionStatus.COMPLETED)
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.method, 'POST')
        posted_body = json.loads(request.data.decode('utf-8'))
        self.assertEqual(posted_body['override'], 'override-pass')
        self.assertIn('route-set: AS64500:RS-EDGE', posted_body['objects'][0]['object_text'])

    def test_preview_irr_change_plan_builds_route_set_create_and_delete_payloads(self):
        create_test_irr_change_plan_item(
            name='Create Route Set',
            change_plan=self.plan,
            object_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            action=rpki_models.IrrChangePlanAction.CREATE,
            stable_object_key='route:203.0.113.0/24AS64500|AS64500:RS-CREATE',
            after_state_json={
                'object_class': 'route-set',
                'set_name': 'AS64500:RS-CREATE',
                'rpsl_pk': 'AS64500:RS-CREATE',
                'stable_key': 'route_set:AS64500:RS-CREATE',
                'members': ['203.0.113.0/24'],
                'mp_members': [],
                'maintainer_names': ['LOCAL-IRR-MNT'],
            },
        )
        create_test_irr_change_plan_item(
            name='Delete Route Set',
            change_plan=self.plan,
            object_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            action=rpki_models.IrrChangePlanAction.DELETE,
            stable_object_key='route:198.51.100.0/24AS64500|AS64500:RS-DELETE',
            before_state_json={
                'object_class': 'route-set',
                'set_name': 'AS64500:RS-DELETE',
                'rpsl_pk': 'AS64500:RS-DELETE',
                'stable_key': 'route_set:AS64500:RS-DELETE',
                'members': ['198.51.100.0/24'],
                'mp_members': [],
                'existing_object_text': (
                    'route-set: AS64500:RS-DELETE\n'
                    'descr: Example delete route set\n'
                    'mnt-by: LOCAL-IRR-MNT\n'
                    'members: 198.51.100.0/24\n'
                    'source: LOCAL-IRR\n'
                ),
            },
        )

        execution, payload = preview_irr_change_plan(self.plan, requested_by='preview-user')

        self.assertEqual(execution.status, rpki_models.IrrWriteExecutionStatus.COMPLETED)
        self.assertEqual(payload['actionable_item_count'], 2)
        create_result = next(item for item in payload['item_results'] if item['action'] == rpki_models.IrrChangePlanAction.CREATE)
        delete_result = next(item for item in payload['item_results'] if item['action'] == rpki_models.IrrChangePlanAction.DELETE)
        self.assertEqual(create_result['operations'][0]['method'], 'POST')
        self.assertEqual(delete_result['operations'][0]['method'], 'DELETE')
        self.assertIn('route-set:       AS64500:RS-CREATE', create_result['operations'][0]['body']['objects'][0]['object_text'])
        self.assertIn('route-set: AS64500:RS-DELETE', delete_result['operations'][0]['body']['objects'][0]['object_text'])

    @patch('netbox_rpki.services.irr_write.urlopen')
    def test_apply_irr_change_plan_submits_route_set_create_and_delete_payloads(self, urlopen_mock):
        urlopen_mock.side_effect = [
            _MockHttpResponse({'summary': {'objects_found': 1, 'successful': 1, 'failed': 0}}),
            _MockHttpResponse({'summary': {'objects_found': 1, 'successful': 1, 'failed': 0}}),
        ]
        create_test_irr_change_plan_item(
            name='Create Route Set',
            change_plan=self.plan,
            object_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            action=rpki_models.IrrChangePlanAction.CREATE,
            stable_object_key='route:203.0.113.0/24AS64500|AS64500:RS-CREATE',
            after_state_json={
                'object_class': 'route-set',
                'set_name': 'AS64500:RS-CREATE',
                'rpsl_pk': 'AS64500:RS-CREATE',
                'stable_key': 'route_set:AS64500:RS-CREATE',
                'members': ['203.0.113.0/24'],
                'mp_members': [],
                'maintainer_names': ['LOCAL-IRR-MNT'],
            },
        )
        create_test_irr_change_plan_item(
            name='Delete Route Set',
            change_plan=self.plan,
            object_family=rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            action=rpki_models.IrrChangePlanAction.DELETE,
            stable_object_key='route:198.51.100.0/24AS64500|AS64500:RS-DELETE',
            before_state_json={
                'object_class': 'route-set',
                'set_name': 'AS64500:RS-DELETE',
                'rpsl_pk': 'AS64500:RS-DELETE',
                'stable_key': 'route_set:AS64500:RS-DELETE',
                'members': ['198.51.100.0/24'],
                'mp_members': [],
                'existing_object_text': (
                    'route-set: AS64500:RS-DELETE\n'
                    'descr: Example delete route set\n'
                    'mnt-by: LOCAL-IRR-MNT\n'
                    'members: 198.51.100.0/24\n'
                    'source: LOCAL-IRR\n'
                ),
            },
        )

        execution, _response_payload = apply_irr_change_plan(self.plan, requested_by='apply-user')

        self.assertEqual(execution.status, rpki_models.IrrWriteExecutionStatus.COMPLETED)
        first_request = urlopen_mock.call_args_list[0].args[0]
        second_request = urlopen_mock.call_args_list[1].args[0]
        self.assertEqual(first_request.method, 'POST')
        self.assertEqual(second_request.method, 'DELETE')
        first_body = json.loads(first_request.data.decode('utf-8'))
        second_body = json.loads(second_request.data.decode('utf-8'))
        self.assertIn('route-set:       AS64500:RS-CREATE', first_body['objects'][0]['object_text'])
        self.assertIn('route-set: AS64500:RS-DELETE', second_body['objects'][0]['object_text'])

    def test_preview_irr_change_plan_builds_as_set_create_payloads(self):
        authored_as_set = create_test_authored_as_set(
            name='Authored Customers',
            organization=self.organization,
            set_name='AS64500:AS-CUSTOMERS',
        )
        create_test_authored_as_set_member(
            name='Authored Customer ASN',
            authored_as_set=authored_as_set,
            member_type=rpki_models.AuthoredAsSetMemberType.ASN,
            member_asn_value=64500,
        )
        create_test_irr_change_plan_item(
            name='Create AS-Set',
            change_plan=self.plan,
            object_family=rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP,
            action=rpki_models.IrrChangePlanAction.CREATE,
            stable_object_key='AS64500:AS-CUSTOMERS|AS64500',
            before_state_json={},
            after_state_json={
                'object_class': 'as-set',
                'set_name': 'AS64500:AS-CUSTOMERS',
                'rpsl_pk': 'AS64500:AS-CUSTOMERS',
                'stable_key': f'authored_as_set:{authored_as_set.pk}',
                'members': ['AS64500'],
            },
        )

        execution, payload = preview_irr_change_plan(self.plan, requested_by='preview-user')

        self.assertEqual(execution.status, rpki_models.IrrWriteExecutionStatus.COMPLETED)
        self.assertEqual(payload['actionable_item_count'], 1)
        item_result = payload['item_results'][0]
        self.assertEqual(item_result['action'], rpki_models.IrrChangePlanAction.CREATE)
        self.assertEqual(item_result['operations'][0]['method'], 'POST')
        object_text = item_result['operations'][0]['body']['objects'][0]['object_text']
        self.assertIn('as-set:          AS64500:AS-CUSTOMERS', object_text)
        self.assertIn('members:         AS64500', object_text)

    @patch('netbox_rpki.services.irr_write.urlopen')
    def test_apply_irr_change_plan_submits_as_set_create_payload(self, urlopen_mock):
        urlopen_mock.return_value = _MockHttpResponse({'summary': {'objects_found': 1, 'successful': 1, 'failed': 0}})
        authored_as_set = create_test_authored_as_set(
            name='Authored Customers',
            organization=self.organization,
            set_name='AS64500:AS-CUSTOMERS',
        )
        create_test_irr_change_plan_item(
            name='Create AS-Set',
            change_plan=self.plan,
            object_family=rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP,
            action=rpki_models.IrrChangePlanAction.CREATE,
            stable_object_key='AS64500:AS-CUSTOMERS|AS64500',
            before_state_json={},
            after_state_json={
                'object_class': 'as-set',
                'set_name': 'AS64500:AS-CUSTOMERS',
                'rpsl_pk': 'AS64500:AS-CUSTOMERS',
                'stable_key': f'authored_as_set:{authored_as_set.pk}',
                'members': ['AS64500'],
            },
        )

        execution, _response_payload = apply_irr_change_plan(self.plan, requested_by='apply-user')

        self.assertEqual(execution.status, rpki_models.IrrWriteExecutionStatus.COMPLETED)
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.method, 'POST')
        posted_body = json.loads(request.data.decode('utf-8'))
        self.assertEqual(posted_body['override'], 'override-pass')
        self.assertIn('as-set:          AS64500:AS-CUSTOMERS', posted_body['objects'][0]['object_text'])


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
