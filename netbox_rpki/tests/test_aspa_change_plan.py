from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import create_aspa_change_plan, reconcile_aspa_intents
from netbox_rpki.services.aspa_change_plan import ASPAChangePlanExecutionError
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa,
    create_test_aspa_intent,
    create_test_aspa_provider,
    create_test_imported_aspa,
    create_test_imported_aspa_provider,
    create_test_organization,
    create_test_provider_account,
    create_test_provider_snapshot,
)


class ASPAChangePlanServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='aspa-plan-org', name='ASPA Plan Org')
        cls.provider_account = create_test_provider_account(
            name='ASPA Plan Provider Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-ASPA-PLAN',
            ca_handle='ca-aspa-plan',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='ASPA Plan Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

    def test_create_aspa_change_plan_rejects_incomplete_reconciliation_run(self):
        run = rpki_models.ASPAReconciliationRun.objects.create(
            name='Incomplete ASPA Run',
            organization=self.organization,
            status=rpki_models.ValidationRunStatus.RUNNING,
        )

        with self.assertRaises(ASPAChangePlanExecutionError):
            create_aspa_change_plan(run)

    def test_plan_generation_creates_whole_object_create_for_missing_customer(self):
        customer = create_test_asn(64600)
        provider = create_test_asn(64601)
        create_test_aspa_intent(
            name='Missing Customer Intent',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider,
        )

        run = reconcile_aspa_intents(self.organization)
        plan = create_aspa_change_plan(run)

        self.assertEqual(plan.summary_json['create_count'], 1)
        self.assertEqual(plan.summary_json['withdraw_count'], 0)
        item = plan.items.get(plan_semantic=rpki_models.ASPAChangePlanItemSemantic.CREATE)
        self.assertEqual(item.action_type, rpki_models.ASPAChangePlanAction.CREATE)
        self.assertEqual(item.after_state_json['customer_asn'], 64600)
        self.assertEqual(item.after_state_json['provider_asns'], [64601])
        self.assertEqual(item.provider_payload_json, {})

    def test_plan_generation_creates_whole_object_withdraw_for_orphaned_customer(self):
        customer = create_test_asn(64610)
        provider = create_test_asn(64611)
        aspa = create_test_aspa(
            name='Orphaned Local ASPA',
            organization=self.organization,
            customer_as=customer,
        )
        create_test_aspa_provider(aspa=aspa, provider_as=provider)

        run = reconcile_aspa_intents(self.organization)
        plan = create_aspa_change_plan(run)

        self.assertEqual(plan.summary_json['withdraw_count'], 1)
        item = plan.items.get(plan_semantic=rpki_models.ASPAChangePlanItemSemantic.WITHDRAW)
        self.assertEqual(item.action_type, rpki_models.ASPAChangePlanAction.WITHDRAW)
        self.assertEqual(item.before_state_json['customer_asn'], 64610)
        self.assertEqual(item.before_state_json['provider_asns'], [64611])

    def test_plan_generation_creates_reshape_and_provider_add_items_for_missing_provider(self):
        customer = create_test_asn(64620)
        provider_a = create_test_asn(64621)
        provider_b = create_test_asn(64622)
        create_test_aspa_intent(
            name='Customer Missing Provider A',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider_a,
        )
        create_test_aspa_intent(
            name='Customer Missing Provider B',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider_b,
        )
        aspa = create_test_aspa(
            name='Partial Local ASPA',
            organization=self.organization,
            customer_as=customer,
        )
        create_test_aspa_provider(aspa=aspa, provider_as=provider_a)

        run = reconcile_aspa_intents(self.organization)
        plan = create_aspa_change_plan(run)

        self.assertEqual(plan.summary_json['provider_add_count'], 1)
        reshape_item = plan.items.get(plan_semantic=rpki_models.ASPAChangePlanItemSemantic.RESHAPE)
        add_item = plan.items.get(plan_semantic=rpki_models.ASPAChangePlanItemSemantic.ADD_PROVIDER)
        self.assertEqual(reshape_item.before_state_json['provider_asns'], [64621])
        self.assertEqual(reshape_item.after_state_json['provider_asns'], [64621, 64622])
        self.assertEqual(add_item.action_type, rpki_models.ASPAChangePlanAction.CREATE)
        self.assertEqual(add_item.aspa, aspa)

    def test_plan_generation_creates_reshape_and_provider_remove_items_for_extra_provider(self):
        customer = create_test_asn(64630)
        provider_a = create_test_asn(64631)
        provider_b = create_test_asn(64632)
        create_test_aspa_intent(
            name='Customer Extra Provider Intent',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider_a,
        )
        aspa = create_test_aspa(
            name='Extra Provider Local ASPA',
            organization=self.organization,
            customer_as=customer,
        )
        create_test_aspa_provider(aspa=aspa, provider_as=provider_a)
        create_test_aspa_provider(aspa=aspa, provider_as=provider_b)

        run = reconcile_aspa_intents(self.organization)
        plan = create_aspa_change_plan(run)

        self.assertEqual(plan.summary_json['provider_remove_count'], 1)
        remove_item = plan.items.get(plan_semantic=rpki_models.ASPAChangePlanItemSemantic.REMOVE_PROVIDER)
        self.assertEqual(remove_item.action_type, rpki_models.ASPAChangePlanAction.WITHDRAW)
        self.assertEqual(remove_item.before_state_json['provider_asns'], [64631, 64632])
        self.assertEqual(remove_item.after_state_json['provider_asns'], [64631])

    def test_plan_generation_marks_provider_backed_metadata_for_imported_scope_and_stale_replacement(self):
        customer = create_test_asn(64640)
        provider = create_test_asn(64641)
        create_test_aspa_intent(
            name='Imported Stale Intent',
            organization=self.organization,
            customer_as=customer,
            provider_as=provider,
        )
        imported_aspa = create_test_imported_aspa(
            name='Imported Stale ASPA',
            provider_snapshot=self.provider_snapshot,
            organization=self.organization,
            customer_as=customer,
            is_stale=True,
        )
        create_test_imported_aspa_provider(imported_aspa=imported_aspa, provider_as=provider)

        run = reconcile_aspa_intents(
            self.organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=self.provider_snapshot,
        )
        plan = create_aspa_change_plan(run)

        self.assertTrue(plan.summary_json['provider_backed'])
        self.assertEqual(plan.summary_json['provider_account_id'], self.provider_account.pk)
        self.assertEqual(plan.summary_json['provider_snapshot_id'], self.provider_snapshot.pk)
        replace_item = plan.items.get(plan_semantic=rpki_models.ASPAChangePlanItemSemantic.REPLACE)
        self.assertEqual(replace_item.provider_operation, rpki_models.ProviderWriteOperation.ADD_PROVIDER_SET)
        self.assertEqual(replace_item.provider_payload_json['provider_asns'], [64641])
        self.assertEqual(plan.summary_json['replacement_count'], 1)
