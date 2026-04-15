from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import (
    build_aspa_overlay_summary,
    build_imported_certificate_observation_overlay_summary,
    build_imported_signed_object_overlay_summary,
    build_roa_overlay_summary,
    build_signed_object_overlay_summary,
)
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa,
    create_test_aspa_provider,
    create_test_bgp_path_observation,
    create_test_imported_certificate_observation,
    create_test_imported_publication_point,
    create_test_imported_signed_object,
    create_test_organization,
    create_test_prefix,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_roa,
    create_test_roa_prefix,
    create_test_signed_object,
    create_test_telemetry_run,
    create_test_telemetry_source,
    create_test_validation_run,
    create_test_object_validation_result,
    create_test_validated_aspa_payload,
    create_test_validated_roa_payload,
)


class OverlayCorrelationServiceTestCase(TestCase):
    def setUp(self):
        self.organization = create_test_organization(name='Overlay Org')
        self.prefix = create_test_prefix(prefix='203.0.113.0/24')
        self.origin_as = create_test_asn(asn=64500)
        self.provider_as = create_test_asn(asn=64501)
        self.peer_as = create_test_asn(asn=64496)

        self.roa_signed_object = create_test_signed_object(
            name='Overlay ROA Signed Object',
            organization=self.organization,
            object_type=rpki_models.SignedObjectType.ROA,
            object_uri='rsync://overlay.invalid/roa.roa',
        )
        self.roa = create_test_roa(
            name='Overlay ROA',
            signed_by=self.roa_signed_object.resource_certificate,
            signed_object=self.roa_signed_object,
            origin_as=self.origin_as,
        )
        create_test_roa_prefix(prefix=self.prefix, roa=self.roa, max_length=24)

        self.aspa_signed_object = create_test_signed_object(
            name='Overlay ASPA Signed Object',
            organization=self.organization,
            object_type=rpki_models.SignedObjectType.ASPA,
            object_uri='rsync://overlay.invalid/customer.aspa',
        )
        self.aspa = create_test_aspa(
            name='Overlay ASPA',
            organization=self.organization,
            signed_object=self.aspa_signed_object,
            customer_as=self.origin_as,
        )
        create_test_aspa_provider(aspa=self.aspa, provider_as=self.provider_as)

        self.validation_run = create_test_validation_run(
            name='Overlay Validation Run',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        self.roa_validation_result = create_test_object_validation_result(
            name='Overlay ROA Validation Result',
            validation_run=self.validation_run,
            signed_object=self.roa_signed_object,
            validation_state=rpki_models.ValidationState.VALID,
            disposition=rpki_models.ValidationDisposition.ACCEPTED,
            match_status='authored_signed_object',
        )
        create_test_validated_roa_payload(
            name='Overlay Validated ROA Payload',
            validation_run=self.validation_run,
            roa=self.roa,
            object_validation_result=self.roa_validation_result,
            prefix=self.prefix,
            origin_as=self.origin_as,
            max_length=24,
        )
        self.aspa_validation_result = create_test_object_validation_result(
            name='Overlay ASPA Validation Result',
            validation_run=self.validation_run,
            signed_object=self.aspa_signed_object,
            validation_state=rpki_models.ValidationState.VALID,
            disposition=rpki_models.ValidationDisposition.ACCEPTED,
            match_status='authored_signed_object',
        )
        create_test_validated_aspa_payload(
            name='Overlay Validated ASPA Payload',
            validation_run=self.validation_run,
            aspa=self.aspa,
            object_validation_result=self.aspa_validation_result,
            customer_as=self.origin_as,
            provider_as=self.provider_as,
        )

        self.telemetry_source = create_test_telemetry_source(
            name='Overlay Telemetry Source',
            organization=self.organization,
            slug='overlay-telemetry',
        )
        self.telemetry_run = create_test_telemetry_run(
            name='Overlay Telemetry Run',
            source=self.telemetry_source,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_bgp_path_observation(
            name='Overlay ROA Observation',
            telemetry_run=self.telemetry_run,
            source=self.telemetry_source,
            prefix=self.prefix,
            observed_prefix='203.0.113.0/24',
            origin_as=self.origin_as,
            observed_origin_asn=self.origin_as.asn,
            peer_as=self.peer_as,
            observed_peer_asn=self.peer_as.asn,
            raw_as_path=f'{self.peer_as.asn} 64510 {self.origin_as.asn}',
            path_asns_json=[self.peer_as.asn, 64510, self.origin_as.asn],
        )
        create_test_bgp_path_observation(
            name='Overlay ASPA Observation',
            telemetry_run=self.telemetry_run,
            source=self.telemetry_source,
            prefix=self.prefix,
            observed_prefix='203.0.113.0/24',
            origin_as=self.origin_as,
            observed_origin_asn=self.origin_as.asn,
            peer_as=self.peer_as,
            observed_peer_asn=self.peer_as.asn,
            raw_as_path=f'{self.peer_as.asn} {self.provider_as.asn} {self.origin_as.asn}',
            path_asns_json=[self.peer_as.asn, self.provider_as.asn, self.origin_as.asn],
        )

        self.provider_account = create_test_provider_account(
            name='Overlay Provider Account',
            organization=self.organization,
            org_handle='ORG-OVERLAY',
        )
        self.provider_snapshot = create_test_provider_snapshot(
            name='Overlay Provider Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
        )
        self.imported_publication_point = create_test_imported_publication_point(
            name='Overlay Imported Publication Point',
            organization=self.organization,
            provider_snapshot=self.provider_snapshot,
            publication_uri='rsync://overlay.invalid/repo/',
        )
        self.imported_signed_object = create_test_imported_signed_object(
            name='Overlay Imported Signed Object',
            organization=self.organization,
            provider_snapshot=self.provider_snapshot,
            publication_point=self.imported_publication_point,
            authored_signed_object=self.roa_signed_object,
            signed_object_type=rpki_models.SignedObjectType.ROA,
            signed_object_uri=self.roa_signed_object.object_uri,
        )
        self.imported_validation_result = create_test_object_validation_result(
            name='Overlay Imported Validation Result',
            validation_run=self.validation_run,
            imported_signed_object=self.imported_signed_object,
            validation_state=rpki_models.ValidationState.VALID,
            disposition=rpki_models.ValidationDisposition.ACCEPTED,
            match_status='imported_signed_object',
        )
        self.imported_certificate_observation = create_test_imported_certificate_observation(
            name='Overlay Imported Certificate Observation',
            organization=self.organization,
            provider_snapshot=self.provider_snapshot,
            publication_point=self.imported_publication_point,
            signed_object=self.imported_signed_object,
            signed_object_uri=self.imported_signed_object.signed_object_uri,
        )

    def test_roa_and_signed_object_overlay_summaries_include_validator_and_telemetry(self):
        roa_summary = build_roa_overlay_summary(self.roa)
        signed_object_summary = build_signed_object_overlay_summary(self.roa_signed_object)

        self.assertEqual(roa_summary['latest_validator_posture']['validation_run_id'], self.validation_run.pk)
        self.assertEqual(roa_summary['telemetry']['matched_observation_count'], 2)
        self.assertEqual(signed_object_summary['latest_validator_posture']['validation_result_id'], self.roa_validation_result.pk)
        self.assertEqual(signed_object_summary['latest_telemetry_posture']['telemetry_run_id'], self.telemetry_run.pk)

    def test_aspa_and_imported_overlay_summaries_include_correlated_provider_evidence(self):
        aspa_summary = build_aspa_overlay_summary(self.aspa)
        imported_signed_object_summary = build_imported_signed_object_overlay_summary(self.imported_signed_object)
        imported_certificate_summary = build_imported_certificate_observation_overlay_summary(self.imported_certificate_observation)

        self.assertEqual(aspa_summary['telemetry']['matched_observation_count'], 1)
        self.assertIn(self.provider_as.asn, aspa_summary['telemetry']['supported_provider_asns'])
        self.assertEqual(imported_signed_object_summary['latest_validator_posture']['validation_result_id'], self.imported_validation_result.pk)
        self.assertEqual(imported_signed_object_summary['drill_down']['authored_signed_object_id'], self.roa_signed_object.pk)
        self.assertEqual(imported_certificate_summary['provider_evidence_linkage_status'], 'linked')
