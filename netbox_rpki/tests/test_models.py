from django.db import IntegrityError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from netbox_rpki import models as rpki_models
from netbox_rpki.models import Certificate, CertificateAsn, CertificatePrefix, Organization, Roa, RoaPrefix
from netbox_rpki.object_registry import VIEW_OBJECT_SPECS
from netbox_rpki.tests.registry_scenarios import SECTION_9_MODEL_SCENARIOS, SECTION_9_SUPPORT_MODEL_SCENARIOS
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_certificate,
    create_test_certificate_asn,
    create_test_certificate_prefix,
    create_test_model,
    create_test_intent_derivation_run,
    create_test_organization,
    create_test_aspa_provider,
    create_test_manifest_entry,
    create_test_prefix,
    create_test_published_roa_result,
    create_test_revoked_certificate,
    create_test_rsc_file_hash,
    create_test_roa,
    create_test_roa_intent,
    create_test_roa_intent_match,
    create_test_roa_intent_override,
    create_test_roa_intent_result,
    create_test_roa_reconciliation_run,
    create_test_roa_prefix,
    create_test_routing_intent_profile,
    create_test_routing_intent_rule,
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
