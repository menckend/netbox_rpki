from datetime import timedelta

from django.db import IntegrityError
from django.db import transaction
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.models import Certificate, CertificateAsn, CertificatePrefix, Organization, Roa, RoaPrefix
from netbox_rpki.object_registry import VIEW_OBJECT_SPECS
from netbox_rpki.sample_data import SEED_TARGET_MODELS
from netbox_rpki.tests.registry_scenarios import SECTION_9_MODEL_SCENARIOS, SECTION_9_SUPPORT_MODEL_SCENARIOS
from netbox_rpki.tests.utils import (
    count_test_sample_dataset,
    create_test_approval_record,
    create_test_asn,
    create_test_aspa,
    create_test_aspa_intent,
    create_test_aspa_intent_match,
    create_test_aspa_intent_result,
    create_test_aspa_reconciliation_run,
    create_test_certificate,
    create_test_certificate_asn,
    create_test_certificate_prefix,
    create_test_end_entity_certificate,
    create_test_model,
    create_test_object_validation_result,
    create_test_intent_derivation_run,
    create_test_organization,
    create_test_aspa_provider,
    create_test_imported_aspa,
    create_test_imported_certificate_observation,
    create_test_imported_publication_point,
    create_test_imported_signed_object,
    create_test_manifest_entry,
    create_test_prefix,
    create_test_publication_point,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_provider_sync_run,
    create_test_provider_write_execution,
    create_test_published_roa_result,
    create_test_published_aspa_result,
    create_test_publication_point,
    create_test_revoked_certificate,
    create_test_roa_change_plan,
    create_test_roa_change_plan_item,
    create_test_rsc_file_hash,
    create_test_imported_roa_authorization,
    create_test_roa,
    create_test_roa_intent,
    create_test_roa_intent_match,
    create_test_roa_intent_override,
    create_test_roa_intent_result,
    create_test_roa_reconciliation_run,
    create_test_roa_prefix,
    create_test_router_certificate,
    create_test_routing_intent_profile,
    create_test_routing_intent_rule,
    create_test_sample_dataset,
    create_test_signed_object,
    create_test_trust_anchor,
    create_test_validated_roa_payload,
    create_test_validation_run,
)


class ModelBehaviorTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization_a = create_test_organization(org_id='org-a', name='Alpha Organization')
        cls.organization_z = create_test_organization(org_id='org-z', name='Zulu Organization')

        cls.certificate_a = create_test_certificate(name='Alpha Certificate', rpki_org=cls.organization_a)
        cls.certificate_z = create_test_certificate(name='Zulu Certificate', rpki_org=cls.organization_z)

        cls.asn_a = create_test_asn(65011)
        cls.asn_z = create_test_asn(65022)

        cls.roa_a = create_test_roa(name='Alpha ROA', origin_as=cls.asn_a, signed_by=cls.certificate_a)
        cls.roa_z = create_test_roa(name='Zulu ROA', origin_as=cls.asn_z, signed_by=cls.certificate_z)

        cls.prefix_a = create_test_prefix('10.0.10.0/24')
        cls.prefix_z = create_test_prefix('10.0.20.0/24')

        cls.roa_prefix_a = create_test_roa_prefix(prefix=cls.prefix_a, roa=cls.roa_a, max_length=24)
        cls.roa_prefix_z = create_test_roa_prefix(prefix=cls.prefix_z, roa=cls.roa_z, max_length=24)

        cls.certificate_prefix_a = create_test_certificate_prefix(prefix=cls.prefix_a, certificate=cls.certificate_a)
        cls.certificate_prefix_z = create_test_certificate_prefix(prefix=cls.prefix_z, certificate=cls.certificate_z)

        cls.certificate_asn_a = create_test_certificate_asn(asn=cls.asn_a, certificate=cls.certificate_a)
        cls.certificate_asn_z = create_test_certificate_asn(asn=cls.asn_z, certificate=cls.certificate_z)

    def test_string_representations(self):
        self.assertEqual(str(self.organization_a), 'Alpha Organization')
        self.assertEqual(str(self.certificate_a), 'Alpha Certificate')
        self.assertEqual(str(self.roa_a), 'Alpha ROA')
        self.assertEqual(str(self.roa_prefix_a), str(self.prefix_a))
        self.assertEqual(str(self.certificate_prefix_a), str(self.prefix_a))
        self.assertEqual(str(self.certificate_asn_a), str(self.asn_a))

    def test_absolute_urls(self):
        self.assertEqual(self.organization_a.get_absolute_url(), reverse('plugins:netbox_rpki:organization', args=[self.organization_a.pk]))
        self.assertEqual(self.certificate_a.get_absolute_url(), reverse('plugins:netbox_rpki:certificate', args=[self.certificate_a.pk]))
        self.assertEqual(self.roa_a.get_absolute_url(), reverse('plugins:netbox_rpki:roa', args=[self.roa_a.pk]))
        self.assertEqual(self.roa_prefix_a.get_absolute_url(), reverse('plugins:netbox_rpki:roaprefix', args=[self.roa_prefix_a.pk]))
        self.assertEqual(self.certificate_prefix_a.get_absolute_url(), reverse('plugins:netbox_rpki:certificateprefix', args=[self.certificate_prefix_a.pk]))
        self.assertEqual(self.certificate_asn_a.get_absolute_url(), reverse('plugins:netbox_rpki:certificateasn', args=[self.certificate_asn_a.pk]))

    def test_name_ordering_for_named_models(self):
        self.assertEqual(list(Organization.objects.values_list('name', flat=True)), ['Alpha Organization', 'Zulu Organization'])
        self.assertEqual(list(Certificate.objects.values_list('name', flat=True)), ['Alpha Certificate', 'Zulu Certificate'])
        self.assertEqual(list(Roa.objects.values_list('name', flat=True)), ['Alpha ROA', 'Zulu ROA'])

    def test_prefix_ordering_for_prefix_models(self):
        self.assertEqual(list(RoaPrefix.objects.values_list('pk', flat=True)), [self.roa_prefix_a.pk, self.roa_prefix_z.pk])
        self.assertEqual(
            list(CertificatePrefix.objects.values_list('pk', flat=True)),
            [self.certificate_prefix_a.pk, self.certificate_prefix_z.pk],
        )

    def test_asn_ordering_for_certificate_asn(self):
        self.assertEqual(
            list(CertificateAsn.objects.values_list('pk', flat=True)),
            [self.certificate_asn_a.pk, self.certificate_asn_z.pk],
        )


class SectionNineModelBehaviorTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.section9_instances = {
            scenario.object_name: scenario.build_instance()
            for scenario in SECTION_9_MODEL_SCENARIOS
        }
        cls.section9_support_instances = {
            scenario.object_name: scenario.build_instance()
            for scenario in SECTION_9_SUPPORT_MODEL_SCENARIOS
        }

    def test_section_nine_registry_models_expose_absolute_urls(self):
        for object_name, instance in self.section9_instances.items():
            spec = next(spec for spec in VIEW_OBJECT_SPECS if spec.model is instance.__class__)
            with self.subTest(object_name=object_name):
                self.assertTrue(hasattr(instance, 'get_absolute_url'))
                self.assertEqual(
                    instance.get_absolute_url(),
                    reverse(f'plugins:netbox_rpki:{spec.routes.slug}', args=[instance.pk]),
                )

    def test_section_nine_registry_models_stringify_cleanly(self):
        for object_name, instance in self.section9_instances.items():
            with self.subTest(object_name=object_name):
                self.assertEqual(str(instance), instance.name)

    def test_section_nine_support_models_stringify_cleanly(self):
        expected_strings = {
            'RevokedCertificate': self.section9_support_instances['RevokedCertificate'].serial,
            'ManifestEntry': self.section9_support_instances['ManifestEntry'].filename,
            'ASPAProvider': str(self.section9_support_instances['ASPAProvider'].provider_as),
            'RSCFileHash': self.section9_support_instances['RSCFileHash'].filename,
        }

        for object_name, instance in self.section9_support_instances.items():
            with self.subTest(object_name=object_name):
                self.assertEqual(str(instance), expected_strings[object_name])

    def test_section_nine_crl_instance_uses_signed_object_extension(self):
        crl = self.section9_instances['CertificateRevocationList']

        self.assertIsNotNone(crl.signed_object)
        self.assertEqual(crl.signed_object.object_type, rpki_models.SignedObjectType.CRL)


class ImportedCertificateObservationModelLinkageTestCase(TestCase):
    def test_imported_certificate_observation_can_link_to_publication_point_and_signed_object(self):
        snapshot = create_test_provider_snapshot()
        publication_point = create_test_imported_publication_point(
            provider_snapshot=snapshot,
            organization=snapshot.organization,
            publication_uri='rsync://example.invalid/repo/',
        )
        signed_object = create_test_imported_signed_object(
            provider_snapshot=snapshot,
            organization=snapshot.organization,
            publication_point=publication_point,
            signed_object_uri='rsync://example.invalid/repo/example.mft',
        )
        observation = create_test_imported_certificate_observation(
            provider_snapshot=snapshot,
            organization=snapshot.organization,
            publication_point=publication_point,
            signed_object=signed_object,
            publication_uri=publication_point.publication_uri,
            signed_object_uri=signed_object.signed_object_uri,
        )

        self.assertEqual(observation.publication_point, publication_point)
        self.assertEqual(observation.signed_object, signed_object)


class RouterCertificateModelNormalizationTestCase(TestCase):
    def test_router_certificate_can_link_to_matching_ee_certificate(self):
        organization = create_test_organization(org_id='router-link-org', name='Router Link Org')
        resource_certificate = create_test_certificate(
            name='Router Resource Certificate',
            rpki_org=organization,
        )
        publication_point = create_test_publication_point(
            name='Router Publication Point',
            organization=organization,
        )
        ee_certificate = create_test_end_entity_certificate(
            name='Router EE Certificate',
            organization=organization,
            resource_certificate=resource_certificate,
            publication_point=publication_point,
            subject='CN=Router',
            issuer='CN=Issuer',
            serial='router-serial',
            ski='router-ski',
        )

        router_certificate = create_test_router_certificate(
            name='Router Certificate',
            organization=organization,
            resource_certificate=resource_certificate,
            publication_point=publication_point,
            ee_certificate=ee_certificate,
            subject='CN=Router',
            issuer='CN=Issuer',
            serial='router-serial',
            ski='router-ski',
        )

        self.assertEqual(router_certificate.ee_certificate, ee_certificate)
        self.assertEqual(ee_certificate.router_certificate_extension, router_certificate)

    def test_router_certificate_rejects_mismatched_ee_certificate_resource_certificate(self):
        organization = create_test_organization(org_id='router-mismatch-org', name='Router Mismatch Org')
        publication_point = create_test_publication_point(
            name='Router Mismatch Publication Point',
            organization=organization,
        )
        ee_certificate = create_test_end_entity_certificate(
            name='Mismatched Router EE Certificate',
            organization=organization,
            resource_certificate=create_test_certificate(
                name='EE Resource Certificate',
                rpki_org=organization,
            ),
            publication_point=publication_point,
        )
        router_certificate = rpki_models.RouterCertificate(
            name='Invalid Router Certificate',
            organization=organization,
            resource_certificate=create_test_certificate(
                name='Router Resource Certificate',
                rpki_org=organization,
            ),
            publication_point=publication_point,
            ee_certificate=ee_certificate,
        )

        with self.assertRaises(ValidationError) as context:
            router_certificate.full_clean()

        self.assertEqual(
            context.exception.message_dict,
            {'ee_certificate': ['EE certificate must use the same resource certificate as the router certificate.']},
        )


class RoaSignedObjectModelNormalizationTestCase(TestCase):
    def test_roa_can_link_to_matching_signed_object(self):
        organization = create_test_organization(org_id='roa-link-org', name='ROA Link Org')
        signing_certificate = create_test_certificate(
            name='ROA Signing Certificate',
            rpki_org=organization,
        )
        signed_object = create_test_signed_object(
            name='ROA Signed Object',
            organization=organization,
            object_type=rpki_models.SignedObjectType.ROA,
            resource_certificate=signing_certificate,
            valid_from=timezone.now().date(),
            valid_to=(timezone.now() + timedelta(days=30)).date(),
        )
        roa = create_test_roa(
            name='Linked ROA',
            signed_by=signing_certificate,
            signed_object=signed_object,
            valid_from=signed_object.valid_from,
            valid_to=signed_object.valid_to,
        )

        self.assertEqual(roa.signed_object, signed_object)
        self.assertEqual(signed_object.legacy_roa, roa)

    def test_roa_rejects_non_roa_signed_object(self):
        organization = create_test_organization(org_id='roa-invalid-org', name='ROA Invalid Org')
        signing_certificate = create_test_certificate(
            name='ROA Invalid Signing Certificate',
            rpki_org=organization,
        )
        signed_object = create_test_signed_object(
            name='Not A ROA Signed Object',
            organization=organization,
            object_type=rpki_models.SignedObjectType.MANIFEST,
            resource_certificate=signing_certificate,
        )
        roa = rpki_models.Roa(
            name='Invalid ROA',
            signed_by=signing_certificate,
            signed_object=signed_object,
            auto_renews=True,
        )

        with self.assertRaises(ValidationError) as context:
            roa.full_clean()

        self.assertEqual(
            context.exception.message_dict,
            {'signed_object': ['Signed object must use the ROA object type.']},
        )


class ValidatedPayloadValidationLinkageTestCase(TestCase):
    def test_validated_roa_payload_can_link_to_object_validation_result(self):
        organization = create_test_organization(org_id='validated-roa-org', name='Validated ROA Org')
        signing_certificate = create_test_certificate(name='Validated ROA Certificate', rpki_org=organization)
        signed_object = create_test_signed_object(
            name='Validated ROA Signed Object',
            organization=organization,
            object_type=rpki_models.SignedObjectType.ROA,
            resource_certificate=signing_certificate,
        )
        roa = create_test_roa(name='Validated ROA', signed_by=signing_certificate, signed_object=signed_object)
        validation_run = create_test_validation_run()
        object_validation_result = create_test_object_validation_result(
            validation_run=validation_run,
            signed_object=signed_object,
        )
        payload = create_test_validated_roa_payload(
            validation_run=validation_run,
            roa=roa,
            object_validation_result=object_validation_result,
        )

        self.assertEqual(payload.object_validation_result, object_validation_result)

    def test_validated_aspa_payload_rejects_mismatched_object_validation_result(self):
        validation_run = create_test_validation_run(name='Validation Run A')
        other_validation_run = create_test_validation_run(name='Validation Run B')
        aspa = create_test_aspa()
        object_validation_result = create_test_object_validation_result(
            validation_run=other_validation_run,
            signed_object=aspa.signed_object,
        )
        payload = rpki_models.ValidatedAspaPayload(
            name='Invalid Validated ASPA Payload',
            validation_run=validation_run,
            aspa=aspa,
            object_validation_result=object_validation_result,
            customer_as=aspa.customer_as,
            provider_as=create_test_asn(65432),
        )

        with self.assertRaises(ValidationError) as context:
            payload.full_clean()

        self.assertEqual(
            context.exception.message_dict,
            {'object_validation_result': ['Object validation result must belong to the same validation run as the validated ASPA payload.']},
        )


class ImportedPublicationLinkageTestCase(TestCase):
    def test_imported_publication_point_can_link_to_authored_publication_point(self):
        organization = create_test_organization(org_id='imported-publication-org', name='Imported Publication Org')
        authored_publication_point = create_test_publication_point(
            organization=organization,
            publication_uri='rsync://example.invalid/repo/',
        )

        imported_publication_point = create_test_imported_publication_point(
            organization=organization,
            authored_publication_point=authored_publication_point,
            publication_uri=authored_publication_point.publication_uri,
        )

        self.assertEqual(imported_publication_point.authored_publication_point, authored_publication_point)

    def test_imported_signed_object_rejects_mismatched_authored_publication_point(self):
        organization = create_test_organization(org_id='imported-signed-object-org', name='Imported Signed Object Org')
        authored_publication_point = create_test_publication_point(
            organization=organization,
            publication_uri='rsync://example.invalid/repo/',
        )
        other_authored_publication_point = create_test_publication_point(
            organization=organization,
            publication_uri='rsync://example.invalid/other/',
        )
        authored_signed_object = create_test_signed_object(
            organization=organization,
            publication_point=other_authored_publication_point,
            object_type=rpki_models.SignedObjectType.MANIFEST,
            object_uri='rsync://example.invalid/repo/example.mft',
        )
        imported_publication_point = create_test_imported_publication_point(
            organization=organization,
            authored_publication_point=authored_publication_point,
            publication_uri=authored_publication_point.publication_uri,
        )
        imported_signed_object = rpki_models.ImportedSignedObject(
            name='Imported Signed Object',
            provider_snapshot=create_test_provider_snapshot(organization=organization),
            organization=organization,
            publication_point=imported_publication_point,
            authored_signed_object=authored_signed_object,
            signed_object_key='imported-signed-object-key',
            signed_object_type=rpki_models.SignedObjectType.MANIFEST,
            publication_uri=imported_publication_point.publication_uri,
            signed_object_uri=authored_signed_object.object_uri,
        )

        with self.assertRaises(ValidationError) as context:
            imported_signed_object.full_clean()

        self.assertEqual(
            context.exception.message_dict,
            {
                'authored_signed_object': [
                    'Authored signed object must use the same authored publication point as the imported signed object.'
                ]
            },
        )


class CertificateRoleValidationTestCase(TestCase):
    def test_end_entity_certificate_rejects_resource_certificate_from_other_organization(self):
        certificate_organization = create_test_organization(org_id='resource-cert-org', name='Resource Cert Org')
        ee_organization = create_test_organization(org_id='ee-org', name='EE Org')
        resource_certificate = create_test_certificate(
            name='Cross-Organization Resource Certificate',
            rpki_org=certificate_organization,
        )
        ee_certificate = rpki_models.EndEntityCertificate(
            name='Invalid EE Certificate',
            organization=ee_organization,
            resource_certificate=resource_certificate,
            publication_point=create_test_publication_point(organization=ee_organization),
        )

        with self.assertRaises(ValidationError) as context:
            ee_certificate.full_clean()

        self.assertEqual(
            context.exception.message_dict,
            {
                'resource_certificate': [
                    'Resource certificate must belong to the same organization as the end-entity certificate.'
                ]
            },
        )

    def test_signed_object_rejects_mismatched_ee_certificate_resource_certificate(self):
        organization = create_test_organization(org_id='signed-object-org', name='Signed Object Org')
        resource_certificate = create_test_certificate(name='Signed Object Resource Certificate', rpki_org=organization)
        other_resource_certificate = create_test_certificate(
            name='Other Resource Certificate',
            rpki_org=organization,
        )
        publication_point = create_test_publication_point(organization=organization)
        ee_certificate = create_test_end_entity_certificate(
            organization=organization,
            resource_certificate=other_resource_certificate,
            publication_point=publication_point,
        )
        signed_object = rpki_models.SignedObject(
            name='Invalid Signed Object',
            organization=organization,
            object_type=rpki_models.SignedObjectType.MANIFEST,
            resource_certificate=resource_certificate,
            ee_certificate=ee_certificate,
            publication_point=publication_point,
        )

        with self.assertRaises(ValidationError) as context:
            signed_object.full_clean()

        self.assertEqual(
            context.exception.message_dict,
            {
                'ee_certificate': [
                    'EE certificate must use the same resource certificate as the signed object.'
                ]
            },
        )


class ASPAProviderModelValidationTestCase(TestCase):
    def test_aspa_provider_enforces_unique_provider_per_aspa(self):
        aspa = create_test_aspa()
        provider_as = create_test_asn(65210)
        create_test_aspa_provider(aspa=aspa, provider_as=provider_as)

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                create_test_aspa_provider(aspa=aspa, provider_as=provider_as)

    def test_aspa_provider_rejects_customer_as_as_provider_as(self):
        customer_as = create_test_asn(65220)
        aspa = create_test_aspa(customer_as=customer_as)
        authorization = rpki_models.ASPAProvider(aspa=aspa, provider_as=customer_as)

        with self.assertRaises(ValidationError) as context:
            authorization.full_clean()

        self.assertEqual(
            context.exception.message_dict,
            {'provider_as': ['Provider ASN must differ from the ASPA customer ASN.']},
        )


class ASPAModelValidationTestCase(TestCase):
    def test_aspa_intent_build_intent_key_is_deterministic(self):
        key_a = rpki_models.ASPAIntent.build_intent_key(customer_asn_value=65123, provider_asn_value=65234)
        key_b = rpki_models.ASPAIntent.build_intent_key(customer_asn_value=65123, provider_asn_value=65234)
        key_c = rpki_models.ASPAIntent.build_intent_key(customer_asn_value=65123, provider_asn_value=65235)

        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_c)

    def test_aspa_intent_enforces_unique_customer_provider_pair(self):
        aspa_intent = create_test_aspa_intent()

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                create_test_aspa_intent(
                    organization=aspa_intent.organization,
                    customer_as=aspa_intent.customer_as,
                    provider_as=aspa_intent.provider_as,
                    intent_key=aspa_intent.intent_key,
                )

    def test_aspa_intent_rejects_customer_as_as_provider_as(self):
        customer_as = create_test_asn(65220)
        aspa_intent = rpki_models.ASPAIntent(
            name='Invalid ASPA Intent',
            organization=create_test_organization(),
            intent_key=rpki_models.ASPAIntent.build_intent_key(
                customer_asn_value=customer_as.asn,
                provider_asn_value=customer_as.asn,
            ),
            customer_as=customer_as,
            provider_as=customer_as,
        )

        with self.assertRaises(ValidationError) as context:
            aspa_intent.full_clean()

        self.assertEqual(
            context.exception.message_dict,
            {'provider_as': ['Provider ASN must differ from the ASPA customer ASN.']},
        )

    def test_aspa_reconciliation_run_requires_provider_snapshot_for_provider_imported_scope(self):
        run = rpki_models.ASPAReconciliationRun(
            name='Invalid ASPA Reconciliation Run',
            organization=create_test_organization(),
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
        )

        with self.assertRaises(ValidationError) as context:
            run.full_clean()

        self.assertEqual(
            context.exception.message_dict,
            {'provider_snapshot': ['Provider snapshot is required for provider-imported ASPA reconciliation runs.']},
        )

    def test_aspa_result_models_enforce_single_row_per_subject(self):
        intent = create_test_aspa_intent()
        run = create_test_aspa_reconciliation_run(organization=intent.organization)
        aspa = create_test_aspa(customer_as=intent.customer_as)
        imported_aspa = create_test_imported_aspa(customer_as=intent.customer_as)

        create_test_aspa_intent_result(
            reconciliation_run=run,
            aspa_intent=intent,
            best_aspa=aspa,
        )
        create_test_published_aspa_result(
            reconciliation_run=run,
            aspa=aspa,
        )

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                create_test_aspa_intent_result(
                    reconciliation_run=run,
                    aspa_intent=intent,
                    best_aspa=aspa,
                )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                create_test_published_aspa_result(
                    reconciliation_run=run,
                    aspa=aspa,
                )

        imported_run = create_test_aspa_reconciliation_run(
            organization=intent.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
        )
        imported_result = create_test_published_aspa_result(
            reconciliation_run=imported_run,
            imported_aspa=imported_aspa,
        )

        self.assertEqual(imported_result.imported_aspa, imported_aspa)
        self.assertIsNone(imported_result.aspa)

    def test_aspa_intent_match_enforces_single_source(self):
        intent = create_test_aspa_intent()
        aspa = create_test_aspa(customer_as=intent.customer_as)
        imported_aspa = create_test_imported_aspa(customer_as=intent.customer_as)

        create_test_aspa_intent_match(
            aspa_intent=intent,
            aspa=aspa,
        )

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                create_test_aspa_intent_match(
                    aspa_intent=intent,
                    aspa=aspa,
                )

        match = rpki_models.ASPAIntentMatch(
            name='Invalid ASPA Intent Match',
            aspa_intent=intent,
            aspa=aspa,
            imported_aspa=imported_aspa,
        )

        with self.assertRaises(ValidationError):
            match.full_clean()


class PriorityOneModelBehaviorTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='priority-one-org', name='Priority One Org')
        cls.profile = create_test_routing_intent_profile(
            name='Default Intent Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            is_default=True,
        )
        cls.rule = create_test_routing_intent_rule(
            name='Default Include Rule',
            intent_profile=cls.profile,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
        )
        cls.override = create_test_roa_intent_override(
            name='Temporary Override',
            organization=cls.organization,
            intent_profile=cls.profile,
            action=rpki_models.ROAIntentOverrideAction.REPLACE_MAX_LENGTH,
            max_length=24,
        )
        cls.derivation_run = create_test_intent_derivation_run(
            name='Derivation Run 1',
            organization=cls.organization,
            intent_profile=cls.profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.origin_asn = create_test_asn(65123)
        cls.prefix = create_test_prefix('10.123.0.0/24')
        cls.roa_intent = create_test_roa_intent(
            name='Expected ROA 1',
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
        cls.signing_certificate = create_test_certificate(name='Priority One Certificate', rpki_org=cls.organization)
        cls.roa = create_test_roa(
            name='Published ROA 1',
            origin_as=cls.origin_asn,
            signed_by=cls.signing_certificate,
        )
        cls.match = create_test_roa_intent_match(
            name='Exact Match 1',
            roa_intent=cls.roa_intent,
            roa=cls.roa,
            match_kind=rpki_models.ROAIntentMatchKind.EXACT,
            is_best_match=True,
        )
        cls.reconciliation_run = create_test_roa_reconciliation_run(
            name='Reconciliation Run 1',
            organization=cls.organization,
            intent_profile=cls.profile,
            basis_derivation_run=cls.derivation_run,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.provider_account = create_test_provider_account(
            name='Provider Account 1',
            organization=cls.organization,
            org_handle='ORG-PRIORITY-ONE',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Provider Snapshot 1',
            organization=cls.organization,
            provider_account=cls.provider_account,
        )
        cls.provider_sync_run = create_test_provider_sync_run(
            name='Provider Sync Run 1',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.imported_authorization = create_test_imported_roa_authorization(
            name='Imported Authorization 1',
            organization=cls.organization,
            provider_snapshot=cls.provider_snapshot,
            prefix=cls.prefix,
            origin_asn=cls.origin_asn,
            max_length=24,
        )
        cls.intent_result = create_test_roa_intent_result(
            name='Intent Result 1',
            reconciliation_run=cls.reconciliation_run,
            roa_intent=cls.roa_intent,
            best_roa=cls.roa,
        )
        cls.published_result = create_test_published_roa_result(
            name='Published Result 1',
            reconciliation_run=cls.reconciliation_run,
            roa=cls.roa,
        )
        cls.change_plan = create_test_roa_change_plan(
            name='Change Plan 1',
            organization=cls.organization,
            source_reconciliation_run=cls.reconciliation_run,
        )
        cls.change_plan_item = create_test_roa_change_plan_item(
            name='Change Plan Item 1',
            change_plan=cls.change_plan,
            action_type=rpki_models.ROAChangePlanAction.CREATE,
            roa_intent=cls.roa_intent,
        )
        cls.provider_write_execution = create_test_provider_write_execution(
            name='Provider Write Execution 1',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_snapshot=cls.provider_snapshot,
            change_plan=cls.change_plan,
        )

    def test_priority_one_models_stringify_cleanly(self):
        for instance in (
            self.profile,
            self.rule,
            self.override,
            self.derivation_run,
            self.roa_intent,
            self.match,
            self.reconciliation_run,
            self.intent_result,
            self.published_result,
            self.provider_account,
            self.provider_snapshot,
            self.provider_sync_run,
            self.provider_write_execution,
            self.imported_authorization,
            self.change_plan,
            self.change_plan_item,
        ):
            with self.subTest(model=instance.__class__.__name__):
                self.assertEqual(str(instance), instance.name)

    def test_priority_one_models_expose_absolute_urls(self):
        expected_routes = {
            self.profile: 'routingintentprofile',
            self.rule: 'routingintentrule',
            self.override: 'roaintentoverride',
            self.derivation_run: 'intentderivationrun',
            self.roa_intent: 'roaintent',
            self.match: 'roaintentmatch',
            self.reconciliation_run: 'roareconciliationrun',
            self.intent_result: 'roaintentresult',
            self.published_result: 'publishedroaresult',
            self.provider_account: 'provideraccount',
            self.provider_snapshot: 'providersnapshot',
            self.provider_sync_run: 'providersyncrun',
            self.provider_write_execution: 'providerwriteexecution',
            self.imported_authorization: 'importedroaauthorization',
            self.change_plan: 'roachangeplan',
            self.change_plan_item: 'roachangeplanitem',
        }
        for instance, route_name in expected_routes.items():
            with self.subTest(model=instance.__class__.__name__):
                self.assertEqual(instance.get_absolute_url(), reverse(f'plugins:netbox_rpki:{route_name}', args=[instance.pk]))

    def test_roa_intent_build_intent_key_is_deterministic(self):
        key_a = rpki_models.ROAIntent.build_intent_key(
            prefix_cidr_text='10.123.0.0/24',
            address_family=rpki_models.AddressFamily.IPV4,
            origin_asn_value=65123,
            max_length=24,
            tenant_id=1,
            vrf_id=2,
            site_id=3,
            region_id=4,
        )
        key_b = rpki_models.ROAIntent.build_intent_key(
            prefix_cidr_text='10.123.0.0/24',
            address_family=rpki_models.AddressFamily.IPV4,
            origin_asn_value=65123,
            max_length=24,
            tenant_id=1,
            vrf_id=2,
            site_id=3,
            region_id=4,
        )
        key_c = rpki_models.ROAIntent.build_intent_key(
            prefix_cidr_text='10.124.0.0/24',
            address_family=rpki_models.AddressFamily.IPV4,
            origin_asn_value=65123,
            max_length=24,
        )

        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_c)

    def test_provider_account_exposes_explicit_roa_write_capability(self):
        krill_account = create_test_provider_account(
            name='Krill Capability Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-KRILL-CAP',
            ca_handle='ca-krill-cap',
            api_base_url='https://krill.example.invalid',
        )

        self.assertFalse(self.provider_account.supports_roa_write)
        self.assertEqual(self.provider_account.roa_write_mode, rpki_models.ProviderRoaWriteMode.UNSUPPORTED)
        self.assertTrue(krill_account.supports_roa_write)
        self.assertEqual(krill_account.roa_write_mode, rpki_models.ProviderRoaWriteMode.KRILL_ROUTE_DELTA)
        self.assertEqual(
            krill_account.roa_write_capability['supported_roa_plan_actions'],
            [rpki_models.ROAChangePlanAction.CREATE, rpki_models.ROAChangePlanAction.WITHDRAW],
        )

    def test_roa_change_plan_state_helpers_reflect_execution_lifecycle(self):
        provider_account = create_test_provider_account(
            name='Failed Plan Krill Account',
            organization=self.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-FAILED-PLAN',
            ca_handle='ca-failed-plan',
            api_base_url='https://krill.example.invalid',
        )
        failed_plan = create_test_roa_change_plan(
            name='Failed Change Plan',
            organization=self.organization,
            source_reconciliation_run=self.reconciliation_run,
            provider_account=provider_account,
            provider_snapshot=create_test_provider_snapshot(
                name='Failed Plan Snapshot',
                organization=self.organization,
                provider_account=provider_account,
            ),
            status=rpki_models.ROAChangePlanStatus.FAILED,
        )

        self.assertFalse(self.change_plan.can_preview)
        self.assertFalse(self.change_plan.can_apply)
        self.assertTrue(failed_plan.can_preview)
        self.assertFalse(failed_plan.can_apply)

    def test_roa_intent_enforces_unique_intent_key_per_derivation_run(self):
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                create_test_roa_intent(
                    name='Duplicate Expected ROA',
                    derivation_run=self.derivation_run,
                    organization=self.organization,
                    intent_profile=self.profile,
                    prefix=self.prefix,
                    prefix_cidr_text=str(self.prefix.prefix),
                    origin_asn=self.origin_asn,
                    origin_asn_value=self.origin_asn.asn,
                    max_length=24,
                    intent_key=self.roa_intent.intent_key,
                )

    def test_reconciliation_result_models_enforce_single_row_per_subject(self):
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                create_test_roa_intent_result(
                    name='Duplicate Intent Result',
                    reconciliation_run=self.reconciliation_run,
                    roa_intent=self.roa_intent,
                )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                create_test_published_roa_result(
                    name='Duplicate Published Result',
                    reconciliation_run=self.reconciliation_run,
                    roa=self.roa,
                )

    def test_imported_authorization_enforces_unique_snapshot_key(self):
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                create_test_imported_roa_authorization(
                    name='Duplicate Imported Authorization',
                    organization=self.organization,
                    provider_snapshot=self.provider_snapshot,
                    prefix=self.prefix,
                    origin_asn=self.origin_asn,
                    max_length=24,
                    authorization_key=self.imported_authorization.authorization_key,
                )

    def test_published_result_accepts_imported_authorization_source(self):
        imported_run = create_test_roa_reconciliation_run(
            name='Imported Reconciliation Run',
            organization=self.organization,
            intent_profile=self.profile,
            basis_derivation_run=self.derivation_run,
            provider_snapshot=self.provider_snapshot,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
        )
        published_result = create_test_published_roa_result(
            name='Imported Published Result',
            reconciliation_run=imported_run,
            imported_authorization=self.imported_authorization,
            roa=None,
        )

        self.assertEqual(published_result.imported_authorization, self.imported_authorization)
        self.assertIsNone(published_result.roa)


class SampleDataFixtureTestCase(TestCase):
    marker = 'Managed by netbox_rpki.tests.sample-data'

    @classmethod
    def setUpTestData(cls):
        cls.dataset = create_test_sample_dataset(
            item_count=12,
            label_prefix='Test Sample Fixture',
            marker=cls.marker,
        )
        cls.counts = count_test_sample_dataset(marker=cls.marker)

    def test_sample_dataset_populates_each_target_table_with_at_least_twelve_rows(self):
        for model in SEED_TARGET_MODELS:
            with self.subTest(model=model.__name__):
                self.assertGreaterEqual(self.counts[model.__name__], 12)

    def test_sample_dataset_returns_expected_primary_collections(self):
        expected_keys = (
            'organizations',
            'certificates',
            'roas',
            'repositories',
            'routing_intent_profiles',
            'roa_intents',
            'reconciliation_runs',
            'aspa_intents',
            'aspa_intent_matches',
            'aspa_reconciliation_runs',
            'aspa_intent_results',
            'published_aspa_results',
        )
        for key in expected_keys:
            with self.subTest(key=key):
                self.assertEqual(len(self.dataset[key]), 12)


class GovernanceModelBehaviorTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='gov-org', name='Governance Org')
        cls.profile = create_test_routing_intent_profile(
            name='Governance Profile',
            organization=cls.organization,
        )
        cls.derivation_run = create_test_intent_derivation_run(
            organization=cls.organization,
            intent_profile=cls.profile,
        )
        cls.reconciliation_run = create_test_roa_reconciliation_run(
            organization=cls.organization,
            intent_profile=cls.profile,
            basis_derivation_run=cls.derivation_run,
        )

    def test_change_plan_rejects_inverted_maintenance_window(self):
        change_plan = rpki_models.ROAChangePlan(
            name='Invalid Governance Plan',
            organization=self.organization,
            source_reconciliation_run=self.reconciliation_run,
            maintenance_window_start=timezone.now(),
            maintenance_window_end=timezone.now() - timedelta(minutes=5),
        )

        with self.assertRaises(ValidationError):
            change_plan.full_clean()

    def test_approval_record_rejects_inverted_maintenance_window(self):
        change_plan = create_test_roa_change_plan(
            organization=self.organization,
            source_reconciliation_run=self.reconciliation_run,
        )
        approval_record = rpki_models.ApprovalRecord(
            name='Invalid Approval Record',
            organization=self.organization,
            change_plan=change_plan,
            maintenance_window_start=timezone.now(),
            maintenance_window_end=timezone.now() - timedelta(minutes=5),
        )

        with self.assertRaises(ValidationError):
            approval_record.full_clean()
