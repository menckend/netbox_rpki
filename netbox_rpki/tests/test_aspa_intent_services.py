from __future__ import annotations

from collections import Counter
from unittest import skipUnless

from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import reconcile_aspa_intents, run_aspa_reconciliation_pipeline
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa,
    create_test_aspa_intent,
    create_test_aspa_provider,
    create_test_external_management_exception,
    create_test_imported_aspa,
    create_test_imported_aspa_provider,
    create_test_organization,
    create_test_provider_account,
    create_test_provider_snapshot,
)


ASPA_SERVICE_MODELS_AVAILABLE = all(
    hasattr(rpki_models, name)
    for name in (
        'ASPAIntent',
        'ASPAReconciliationRun',
        'ASPAIntentResult',
        'PublishedASPAResult',
    )
)
def _get_first_attr(instance, *names):
    for name in names:
        if hasattr(instance, name):
            return getattr(instance, name)
    return None


@skipUnless(ASPA_SERVICE_MODELS_AVAILABLE, 'ASPA reconciliation models are not available yet.')
class ASPAIntentServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='aspa-intent-org', name='ASPA Intent Org')
        cls.provider_account = create_test_provider_account(
            name='ASPA Provider Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            ca_handle='krill-aspa',
            api_base_url='https://krill.example.invalid',
        )
        cls.customer_a = create_test_asn(64500)
        cls.provider_b = create_test_asn(64501)
        cls.provider_c = create_test_asn(64502)
        cls.provider_d = create_test_asn(64503)
        cls.orphan_customer = create_test_asn(64510)
        cls.orphan_provider = create_test_asn(64511)

    def test_reconcile_local_scope_persists_expected_results(self):
        create_test_aspa_intent(
            name='Intent Match',
            organization=self.organization,
            customer_as=self.customer_a,
            provider_as=self.provider_b,
        )
        create_test_aspa_intent(
            name='Intent Missing Provider',
            organization=self.organization,
            customer_as=self.customer_a,
            provider_as=self.provider_c,
        )
        create_test_aspa_intent(
            name='Intent Missing Customer',
            organization=self.organization,
            customer_as=self.orphan_customer,
            provider_as=self.orphan_provider,
        )

        aspa = create_test_aspa(
            name='Local ASPA',
            organization=self.organization,
            customer_as=self.customer_a,
        )
        create_test_aspa_provider(aspa=aspa, provider_as=self.provider_b)
        create_test_aspa_provider(aspa=aspa, provider_as=self.provider_d)

        orphan_aspa = create_test_aspa(
            name='Orphan ASPA',
            organization=self.organization,
            customer_as=create_test_asn(64520),
        )
        create_test_aspa_provider(aspa=orphan_aspa, provider_as=create_test_asn(64521))

        run = reconcile_aspa_intents(self.organization)

        intent_results = list(run.intent_results.order_by('name'))
        published_results = list(run.published_aspa_results.order_by('name'))

        self.assertEqual(run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(run.comparison_scope, 'local_aspa_records')
        self.assertEqual(run.intent_count, 3)
        self.assertEqual(run.published_aspa_count, 2)
        self.assertEqual(Counter(result.result_type for result in intent_results), Counter({
            'match': 1,
            'missing_provider': 1,
            'missing': 1,
        }))
        self.assertEqual(Counter(result.result_type for result in published_results), Counter({
            'extra_provider': 1,
            'orphaned': 1,
        }))

        intent_result_model = rpki_models.ASPAIntentResult
        published_result_model = rpki_models.PublishedASPAResult
        match_result = intent_result_model.objects.get(reconciliation_run=run, name='Intent Match Result')
        missing_provider_result = intent_result_model.objects.get(
            reconciliation_run=run,
            name='Intent Missing Provider Result',
        )
        missing_result = intent_result_model.objects.get(reconciliation_run=run, name='Intent Missing Customer Result')
        local_result = published_result_model.objects.get(reconciliation_run=run, name='Local ASPA Published Result')

        self.assertEqual(match_result.result_type, 'match')
        self.assertEqual(match_result.best_aspa, aspa)
        self.assertEqual(match_result.details_json['published_provider_values'], [64501, 64503])
        self.assertEqual(missing_provider_result.result_type, 'missing_provider')
        self.assertEqual(missing_result.result_type, 'missing')
        self.assertEqual(local_result.result_type, 'extra_provider')
        self.assertEqual(local_result.details_json['desired_provider_values'], [64501, 64502])
        self.assertEqual(local_result.details_json['published_provider_values'], [64501, 64503])
        run_summary = _get_first_attr(run, 'result_summary_json', 'summary_json') or {}
        self.assertEqual(run_summary['comparison_scope'], 'local_aspa_records')
        self.assertEqual(run_summary['intent_result_types']['match'], 1)
        self.assertEqual(run_summary['published_result_types']['extra_provider'], 1)
        self.assertEqual(_get_first_attr(run, 'intent_count', 'active_intent_count'), 3)
        self.assertEqual(_get_first_attr(run, 'published_aspa_count', 'published_count'), 2)

    def test_reconcile_provider_imported_scope_marks_stale_results(self):
        snapshot = create_test_provider_snapshot(
            name='ASPA Imported Snapshot',
            organization=self.organization,
            provider_account=self.provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        create_test_aspa_intent(
            name='Imported Intent',
            organization=self.organization,
            customer_as=self.customer_a,
            provider_as=self.provider_b,
        )
        imported_aspa = create_test_imported_aspa(
            name='Imported ASPA',
            provider_snapshot=snapshot,
            organization=self.organization,
            customer_as=self.customer_a,
            is_stale=True,
        )
        create_test_imported_aspa_provider(imported_aspa=imported_aspa, provider_as=self.provider_b)

        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope='provider_imported',
            provider_snapshot=snapshot,
        )

        intent_result = rpki_models.ASPAIntentResult.objects.get(reconciliation_run=run, name='Imported Intent Result')
        published_result = rpki_models.PublishedASPAResult.objects.get(
            reconciliation_run=run,
            name='Imported ASPA Published Result',
        )

        self.assertEqual(run.provider_snapshot, snapshot)
        self.assertEqual(intent_result.result_type, 'stale')
        self.assertEqual(intent_result.best_imported_aspa, imported_aspa)
        self.assertEqual(published_result.result_type, 'stale')
        run_summary = _get_first_attr(run, 'result_summary_json', 'summary_json') or {}
        self.assertEqual(run_summary['provider_snapshot_id'], snapshot.pk)

    def test_reconcile_records_matching_external_management_exception(self):
        create_test_aspa_intent(
            name='Externally Managed Intent',
            organization=self.organization,
            customer_as=self.customer_a,
            provider_as=self.provider_b,
        )
        create_test_external_management_exception(
            name='Externally Managed Customer',
            organization=self.organization,
            scope_type=rpki_models.ExternalManagementScope.ASPA_CUSTOMER,
            customer_asn=self.customer_a,
            provider_asn=self.provider_b,
            owner='external-owner',
            reason='ASPA publication remains external during onboarding.',
        )

        run = reconcile_aspa_intents(self.organization)
        intent_result = rpki_models.ASPAIntentResult.objects.get(
            reconciliation_run=run,
            name='Externally Managed Intent Result',
        )

        self.assertEqual(intent_result.result_type, 'missing')
        self.assertEqual(intent_result.details_json['external_management_exception']['owner'], 'external-owner')
        run_summary = _get_first_attr(run, 'result_summary_json', 'summary_json') or {}
        self.assertEqual(run_summary['external_management_matched_intent_count'], 1)

    def test_reconcile_records_delegated_scope_metadata(self):
        delegated_entity = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='ASPA Delegated Entity',
            organization=self.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.CUSTOMER,
        )
        managed_relationship = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='ASPA Delegated Relationship',
            organization=self.organization,
            delegated_entity=delegated_entity,
            provider_account=self.provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        create_test_aspa_intent(
            name='Scoped ASPA Intent',
            organization=self.organization,
            customer_as=self.customer_a,
            provider_as=self.provider_b,
            delegated_entity=delegated_entity,
            managed_relationship=managed_relationship,
        )

        run = reconcile_aspa_intents(self.organization)
        intent_result = rpki_models.ASPAIntentResult.objects.get(reconciliation_run=run, name='Scoped ASPA Intent Result')
        run_summary = _get_first_attr(run, 'result_summary_json', 'summary_json') or {}

        self.assertEqual(intent_result.details_json['delegated_scope']['managed_relationship_id'], managed_relationship.pk)
        self.assertEqual(intent_result.details_json['delegated_scope']['delegated_entity_id'], delegated_entity.pk)
        self.assertEqual(run_summary['delegated_scope_counts']['managed_relationship'], 1)
        self.assertEqual(run_summary['ownership_scope_conflict_customer_count'], 0)

    def test_reconcile_summarizes_customer_scope_conflicts(self):
        entity_a = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='ASPA Conflict Entity A',
            organization=self.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.CUSTOMER,
        )
        entity_b = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='ASPA Conflict Entity B',
            organization=self.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.DOWNSTREAM,
        )
        relationship_a = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='ASPA Conflict Relationship A',
            organization=self.organization,
            delegated_entity=entity_a,
            provider_account=self.provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        relationship_b = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='ASPA Conflict Relationship B',
            organization=self.organization,
            delegated_entity=entity_b,
            provider_account=self.provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        create_test_aspa_intent(
            name='Conflict Intent A',
            organization=self.organization,
            customer_as=self.customer_a,
            provider_as=self.provider_b,
            delegated_entity=entity_a,
            managed_relationship=relationship_a,
        )
        create_test_aspa_intent(
            name='Conflict Intent B',
            organization=self.organization,
            customer_as=self.customer_a,
            provider_as=self.provider_c,
            delegated_entity=entity_b,
            managed_relationship=relationship_b,
        )

        run = reconcile_aspa_intents(self.organization)
        run_summary = _get_first_attr(run, 'result_summary_json', 'summary_json') or {}

        self.assertEqual(run_summary['ownership_scope_conflict_customer_count'], 1)
        self.assertEqual(run_summary['ownership_scope_conflict_customer_asns'], [self.customer_a.asn])

    def test_pipeline_entry_point_delegates_to_reconciliation(self):
        run = run_aspa_reconciliation_pipeline(self.organization)
        self.assertIsNotNone(run.pk)
        self.assertEqual(run.comparison_scope, 'local_aspa_records')
