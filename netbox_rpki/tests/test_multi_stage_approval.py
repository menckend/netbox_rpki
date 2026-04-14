from django.test import TestCase
from django.urls import reverse

from netbox_rpki import models as rpki_models
from netbox_rpki.services import (
    ProviderWriteError,
    derive_roa_intents,
    approve_aspa_change_plan,
    approve_aspa_change_plan_secondary,
    approve_roa_change_plan,
    approve_roa_change_plan_secondary,
    reconcile_roa_intents,
)
from netbox_rpki.tests.base import PluginAPITestCase, PluginViewTestCase
from netbox_rpki.tests.test_provider_write import build_clean_simulation_plan, current_ack_required_finding_ids
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa_change_plan,
    create_test_aspa_intent,
    create_test_aspa_reconciliation_run,
    create_test_organization,
    create_test_prefix,
    create_test_provider_account,
    create_test_provider_snapshot,
    create_test_routing_intent_profile,
)


class MultiStageApprovalServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='dual-approval-org', name='Dual Approval Org')
        cls.provider_account = create_test_provider_account(
            name='Dual Approval Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-DUAL',
            ca_handle='ca-dual',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Dual Approval Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.prefix = create_test_prefix('10.250.0.0/24')
        cls.asn = create_test_asn(66250)
        cls.profile = create_test_routing_intent_profile(
            name='Dual Approval Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.prefix.pk}',
            asn_selector_query=f'id={cls.asn.pk}',
        )
        cls.derivation_run = derive_roa_intents(cls.profile)
        cls.reconciliation_run = reconcile_roa_intents(
            cls.derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.aspa_customer = create_test_asn(66251)
        cls.aspa_provider = create_test_asn(66252)
        create_test_aspa_intent(
            name='Dual Approval ASPA Intent',
            organization=cls.organization,
            customer_as=cls.aspa_customer,
            provider_as=cls.aspa_provider,
        )
        cls.aspa_reconciliation_run = create_test_aspa_reconciliation_run(
            name='Dual Approval ASPA Reconciliation',
            organization=cls.organization,
            provider_snapshot=cls.provider_snapshot,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

    def test_primary_approval_with_dual_flag_sets_awaiting_2nd(self):
        plan = build_clean_simulation_plan(
            organization=self.organization,
            reconciliation_run=self.reconciliation_run,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
            prefix_text=str(self.prefix.prefix),
            origin_asn_value=self.asn.asn,
            max_length_value=24,
            plan_name='Dual Approval ROA Plan',
        )

        approve_roa_change_plan(
            plan,
            approved_by='primary-user',
            requires_secondary_approval=True,
            acknowledged_finding_ids=current_ack_required_finding_ids(plan),
        )
        plan.refresh_from_db()

        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.AWAITING_2ND)
        self.assertTrue(plan.requires_secondary_approval)
        self.assertTrue(plan.can_approve_secondary)
        self.assertFalse(plan.can_apply)

    def test_secondary_approval_transitions_plan_to_approved(self):
        plan = build_clean_simulation_plan(
            organization=self.organization,
            reconciliation_run=self.reconciliation_run,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
            prefix_text=str(self.prefix.prefix),
            origin_asn_value=self.asn.asn,
            max_length_value=24,
            plan_name='Dual Approval ROA Plan 2',
        )
        approve_roa_change_plan(
            plan,
            approved_by='primary-user',
            requires_secondary_approval=True,
            acknowledged_finding_ids=current_ack_required_finding_ids(plan),
        )

        approve_roa_change_plan_secondary(
            plan,
            secondary_approved_by='secondary-user',
            approval_notes='Second review complete.',
        )
        plan.refresh_from_db()

        self.assertEqual(plan.status, rpki_models.ROAChangePlanStatus.APPROVED)
        self.assertEqual(plan.secondary_approved_by, 'secondary-user')
        self.assertEqual(plan.approval_records.count(), 2)

    def test_secondary_approval_rejects_same_actor_as_primary(self):
        plan = build_clean_simulation_plan(
            organization=self.organization,
            reconciliation_run=self.reconciliation_run,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
            prefix_text=str(self.prefix.prefix),
            origin_asn_value=self.asn.asn,
            max_length_value=24,
            plan_name='Dual Approval Same Actor Plan',
        )
        approve_roa_change_plan(
            plan,
            approved_by='same-user',
            requires_secondary_approval=True,
            acknowledged_finding_ids=current_ack_required_finding_ids(plan),
        )

        with self.assertRaisesMessage(ProviderWriteError, 'secondary approver must be a different person'):
            approve_roa_change_plan_secondary(plan, secondary_approved_by='same-user')

    def test_aspa_dual_approval_transitions_through_awaiting_2nd(self):
        plan = create_test_aspa_change_plan(
            name='Dual Approval ASPA Plan',
            organization=self.organization,
            source_reconciliation_run=self.aspa_reconciliation_run,
            provider_account=self.provider_account,
            provider_snapshot=self.provider_snapshot,
        )

        approve_aspa_change_plan(
            plan,
            approved_by='primary-user',
            requires_secondary_approval=True,
        )
        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.AWAITING_2ND)

        approve_aspa_change_plan_secondary(plan, secondary_approved_by='secondary-user')
        plan.refresh_from_db()
        self.assertEqual(plan.status, rpki_models.ASPAChangePlanStatus.APPROVED)
        self.assertEqual(plan.approval_records.count(), 2)


class MultiStageApprovalViewTestCase(PluginViewTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='dual-approval-view-org', name='Dual Approval View Org')
        cls.provider_account = create_test_provider_account(
            name='Dual Approval View Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-DUAL-VIEW',
            ca_handle='ca-dual-view',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Dual Approval View Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.prefix = create_test_prefix('10.251.0.0/24')
        cls.asn = create_test_asn(66260)
        cls.profile = create_test_routing_intent_profile(
            name='Dual Approval View Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.prefix.pk}',
            asn_selector_query=f'id={cls.asn.pk}',
        )
        cls.derivation_run = derive_roa_intents(cls.profile)
        cls.reconciliation_run = reconcile_roa_intents(
            cls.derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.plan = build_clean_simulation_plan(
            organization=cls.organization,
            reconciliation_run=cls.reconciliation_run,
            provider_account=cls.provider_account,
            provider_snapshot=cls.provider_snapshot,
            prefix_text=str(cls.prefix.prefix),
            origin_asn_value=cls.asn.asn,
            max_length_value=24,
            plan_name='Dual Approval View Plan',
        )
        approve_roa_change_plan(
            cls.plan,
            approved_by='primary-user',
            requires_secondary_approval=True,
            acknowledged_finding_ids=current_ack_required_finding_ids(cls.plan),
        )

    def test_secondary_approval_view_renders(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')

        response = self.client.get(
            reverse('plugins:netbox_rpki:roachangeplan_approve_secondary', kwargs={'pk': self.plan.pk})
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Secondary Approval')

    def test_secondary_approval_view_completes_approval(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')

        response = self.client.post(
            reverse('plugins:netbox_rpki:roachangeplan_approve_secondary', kwargs={'pk': self.plan.pk}),
            {'confirm': True, 'approval_notes': 'View secondary approval.'},
        )

        self.assertRedirects(response, self.plan.get_absolute_url())
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, rpki_models.ROAChangePlanStatus.APPROVED)


class MultiStageApprovalAPITestCase(PluginAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(org_id='dual-approval-api-org', name='Dual Approval API Org')
        cls.provider_account = create_test_provider_account(
            name='Dual Approval API Account',
            organization=cls.organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle='ORG-DUAL-API',
            ca_handle='ca-dual-api',
            api_base_url='https://krill.example.invalid',
        )
        cls.provider_snapshot = create_test_provider_snapshot(
            name='Dual Approval API Snapshot',
            organization=cls.organization,
            provider_account=cls.provider_account,
            provider_name='Krill',
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
        cls.prefix = create_test_prefix('10.252.0.0/24')
        cls.asn = create_test_asn(66270)
        cls.profile = create_test_routing_intent_profile(
            name='Dual Approval API Profile',
            organization=cls.organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'id={cls.prefix.pk}',
            asn_selector_query=f'id={cls.asn.pk}',
        )
        cls.derivation_run = derive_roa_intents(cls.profile)
        cls.reconciliation_run = reconcile_roa_intents(
            cls.derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
            provider_snapshot=cls.provider_snapshot,
        )
        cls.plan = build_clean_simulation_plan(
            organization=cls.organization,
            reconciliation_run=cls.reconciliation_run,
            provider_account=cls.provider_account,
            provider_snapshot=cls.provider_snapshot,
            prefix_text=str(cls.prefix.prefix),
            origin_asn_value=cls.asn.asn,
            max_length_value=24,
            plan_name='Dual Approval API Plan',
        )
        approve_roa_change_plan(
            cls.plan,
            approved_by='primary-user',
            requires_secondary_approval=True,
            acknowledged_finding_ids=current_ack_required_finding_ids(cls.plan),
        )

    def test_approve_secondary_api_action_transitions_plan(self):
        self.add_permissions('netbox_rpki.view_roachangeplan', 'netbox_rpki.change_roachangeplan')
        url = reverse('plugins-api:netbox_rpki-api:roachangeplan-approve-secondary', kwargs={'pk': self.plan.pk})

        response = self.client.post(
            url,
            {'approval_notes': 'API secondary approval.'},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, rpki_models.ROAChangePlanStatus.APPROVED)
        self.assertEqual(self.plan.secondary_approved_by, self.user.username)
