from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import (
    ExternalValidationError,
    VALIDATOR_FETCH_MODE_LIVE_API,
    VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT,
    sync_validator_instance,
)
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa,
    create_test_aspa_provider,
    create_test_imported_signed_object,
    create_test_organization,
    create_test_prefix,
    create_test_roa,
    create_test_roa_prefix,
    create_test_signed_object,
    create_test_validator_instance,
)


FIXTURE_PATH = Path(__file__).resolve().parents[2] / 'devrun' / 'routinator' / 'fixtures' / 'jsonext-sample.json'

ROUTINATOR_LIVE_RESPONSE = {
    'metadata': {
        'generated': '2026-04-15T03:33:32+00:00',
        'repository_serial': '9876',
    },
    'roas': [
        {
            'prefix': '203.0.113.0/24',
            'asn': 'AS64500',
            'maxLength': 24,
            'uri': 'rsync://rpki.example.invalid/repo/roa-one.roa',
            'hash': 'hash-roa-one',
            'ta': 'test-ta',
        },
    ],
}


class ExternalValidationServiceTestCase(TestCase):
    def setUp(self):
        self.organization = create_test_organization(name='Validator Org')
        self.validator = create_test_validator_instance(
            name='Routinator',
            organization=self.organization,
            software_name='Routinator',
            base_url='https://validator.example.invalid/',
        )
        self.origin_as = create_test_asn(asn=64500)
        self.provider_one = create_test_asn(asn=64501)
        self.provider_two = create_test_asn(asn=64502)
        self.unmatched_origin = create_test_asn(asn=64510)
        self.prefix = create_test_prefix(prefix='203.0.113.0/24')

        self.roa_signed_object = create_test_signed_object(
            name='Authored ROA Object',
            organization=self.organization,
            object_type=rpki_models.SignedObjectType.ROA,
            object_uri='rsync://rpki.example.invalid/repo/roa-one.roa',
            content_hash='hash-roa-one',
        )
        self.roa = create_test_roa(
            name='Authored ROA',
            signed_by=self.roa_signed_object.resource_certificate,
            signed_object=self.roa_signed_object,
            origin_as=self.origin_as,
        )
        create_test_roa_prefix(prefix=self.prefix, roa=self.roa, max_length=24)

        self.aspa_signed_object = create_test_signed_object(
            name='Authored ASPA Object',
            organization=self.organization,
            object_type=rpki_models.SignedObjectType.ASPA,
            object_uri='rsync://rpki.example.invalid/repo/customer.aspa',
            content_hash='hash-aspa-one',
        )
        self.aspa = create_test_aspa(
            name='Authored ASPA',
            organization=self.organization,
            signed_object=self.aspa_signed_object,
            customer_as=self.origin_as,
        )
        create_test_aspa_provider(aspa=self.aspa, provider_as=self.provider_one)
        create_test_aspa_provider(aspa=self.aspa, provider_as=self.provider_two)

        create_test_imported_signed_object(
            name='Imported Unmatched ROA',
            organization=self.organization,
            authored_signed_object=None,
            signed_object_type=rpki_models.SignedObjectType.ROA,
            signed_object_uri='rsync://rpki.example.invalid/repo/unmatched.roa',
            object_hash='hash-roa-unmatched',
        )

    def test_sync_validator_instance_imports_snapshot_fixture(self):
        run = sync_validator_instance(
            self.validator,
            fetch_mode=VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT,
            snapshot_file=str(FIXTURE_PATH),
        )

        self.assertEqual(run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(run.repository_serial, '4242')
        self.assertEqual(run.summary_json['validated_roa_payload_count'], 2)
        self.assertEqual(run.summary_json['validated_aspa_payload_count'], 2)
        self.assertEqual(run.summary_json['matched_authored_object_count'], 2)
        self.assertEqual(run.summary_json['matched_imported_object_count'], 1)

        authored_roa_result = rpki_models.ObjectValidationResult.objects.get(
            validation_run=run,
            signed_object=self.roa_signed_object,
        )
        self.assertEqual(authored_roa_result.match_status, 'authored_signed_object')
        self.assertEqual(authored_roa_result.external_object_uri, 'rsync://rpki.example.invalid/repo/roa-one.roa')

        imported_result = rpki_models.ObjectValidationResult.objects.get(
            validation_run=run,
            imported_signed_object__signed_object_uri='rsync://rpki.example.invalid/repo/unmatched.roa',
        )
        self.assertEqual(imported_result.match_status, 'imported_signed_object')

        unmatched_roa_payload = rpki_models.ValidatedRoaPayload.objects.get(
            validation_run=run,
            observed_prefix='198.51.100.0/24',
        )
        self.assertIsNone(unmatched_roa_payload.prefix)
        self.assertEqual(unmatched_roa_payload.origin_as, self.unmatched_origin)

        aspa_payloads = list(
            rpki_models.ValidatedAspaPayload.objects.filter(validation_run=run).order_by('provider_as__asn')
        )
        self.assertEqual([payload.provider_as.asn for payload in aspa_payloads], [64501, 64502])
        self.assertTrue(all(payload.aspa_id == self.aspa.pk for payload in aspa_payloads))

        self.validator.refresh_from_db()
        self.assertEqual(self.validator.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(self.validator.summary_json['latest_run_id'], run.pk)

    def test_sync_validator_instance_uses_live_routinator_adapter(self):
        with patch('netbox_rpki.services.external_validation._http_json_request', return_value=ROUTINATOR_LIVE_RESPONSE):
            run = sync_validator_instance(self.validator, fetch_mode=VALIDATOR_FETCH_MODE_LIVE_API)

        self.assertEqual(run.repository_serial, '9876')
        self.assertEqual(run.summary_json['validated_roa_payload_count'], 1)
        self.assertEqual(
            rpki_models.ObjectValidationResult.objects.filter(validation_run=run, signed_object=self.roa_signed_object).count(),
            1,
        )

    def test_sync_validator_instance_requires_snapshot_file_for_snapshot_mode(self):
        with self.assertRaises(ExternalValidationError):
            sync_validator_instance(
                self.validator,
                fetch_mode=VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT,
            )


class SyncValidatorInstanceCommandTestCase(TestCase):
    def setUp(self):
        self.validator = create_test_validator_instance(name='Command Validator')

    def test_sync_validator_instance_command_runs_synchronously(self):
        with patch('netbox_rpki.management.commands.sync_validator_instance.sync_validator_instance') as sync_mock:
            run = rpki_models.ValidationRun(name='Validation Run')
            run.pk = 123
            sync_mock.return_value = run
            stdout = StringIO()

            call_command(
                'sync_validator_instance',
                '--validator-instance',
                str(self.validator.pk),
                '--fetch-mode',
                VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT,
                '--snapshot-file',
                str(FIXTURE_PATH),
                stdout=stdout,
            )

        sync_mock.assert_called_once_with(
            self.validator,
            fetch_mode=VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT,
            snapshot_file=str(FIXTURE_PATH),
        )
        self.assertIn('Completed validator import run 123', stdout.getvalue())

    def test_sync_validator_instance_command_enqueues_job(self):
        with patch(
            'netbox_rpki.management.commands.sync_validator_instance.SyncValidatorInstanceJob.enqueue_for_validator',
            return_value=(type('JobRef', (), {'pk': 99})(), True),
        ) as enqueue_mock:
            stdout = StringIO()
            call_command(
                'sync_validator_instance',
                '--validator-instance',
                str(self.validator.pk),
                '--enqueue',
                stdout=stdout,
            )

        enqueue_mock.assert_called_once_with(
            self.validator,
            fetch_mode=VALIDATOR_FETCH_MODE_LIVE_API,
            snapshot_file=None,
        )
        self.assertIn('Enqueued job 99', stdout.getvalue())
