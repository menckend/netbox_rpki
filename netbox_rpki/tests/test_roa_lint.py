from django.core.exceptions import ValidationError
from django.test import TestCase
from tenancy.models import Tenant

from netbox_rpki import models as rpki_models
from netbox_rpki.services.roa_lint import (
    LINT_RULE_INTENT_OVERBROAD,
    LINT_RULE_INTENT_ASN_NOT_IN_ORG,
    LINT_RULE_INTENT_PREFIX_NOT_IN_ORG,
    LINT_RULE_INTENT_SUPPRESSED,
    LINT_RULE_PLAN_CROSS_ORG_AUTHORIZATION,
    LINT_RULE_PLAN_BROADENS_AUTHORIZATION,
    LINT_RULE_PUBLISHED_CROSS_ORG_ORIGIN,
    build_roa_change_plan_lint_posture,
    run_roa_lint,
    suppress_roa_lint_finding,
)
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_intent_derivation_run,
    create_test_organization,
    create_test_prefix,
    create_test_roa_change_plan,
    create_test_roa_change_plan_item,
    create_test_roa_intent,
    create_test_roa_intent_result,
    create_test_roa_lint_finding,
    create_test_roa_lint_run,
    create_test_roa_lint_rule_config,
    create_test_roa_lint_suppression,
    create_test_published_roa_result,
    create_test_roa_reconciliation_run,
    create_test_routing_intent_profile,
)


class ROALintRuleConfigTestCase(TestCase):
    def test_org_override_severity(self):
        organization = create_test_organization(org_id='lint-override-org-a', name='Lint Override Org A')
        profile = create_test_routing_intent_profile(name='Lint Override Profile A', organization=organization)
        derivation_run = create_test_intent_derivation_run(
            name='Lint Override Derivation A',
            organization=organization,
            intent_profile=profile,
        )
        roa_intent = create_test_roa_intent(
            name='Lint Override Intent A',
            organization=organization,
            derivation_run=derivation_run,
            intent_profile=profile,
            prefix=create_test_prefix('10.220.0.0/24', status='active'),
            origin_asn=create_test_asn(65220),
            origin_asn_value=65220,
            max_length=24,
        )
        reconciliation_run = create_test_roa_reconciliation_run(
            name='Lint Override Reconciliation A',
            organization=organization,
            intent_profile=profile,
            basis_derivation_run=derivation_run,
        )
        create_test_roa_intent_result(
            name='Lint Override Intent Result A',
            reconciliation_run=reconciliation_run,
            roa_intent=roa_intent,
            result_type=rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            details_json={
                'intent_prefix': '10.220.0.0/24',
                'intent_max_length': 24,
                'published_max_length': 26,
            },
        )
        create_test_roa_lint_rule_config(
            name='Lint Override Severity Config',
            organization=organization,
            finding_code=LINT_RULE_INTENT_OVERBROAD,
            severity_override=rpki_models.ReconciliationSeverity.CRITICAL,
        )

        lint_run = run_roa_lint(reconciliation_run)

        finding = lint_run.findings.get(finding_code=LINT_RULE_INTENT_OVERBROAD)
        self.assertEqual(finding.severity, rpki_models.ReconciliationSeverity.CRITICAL)

    def test_org_override_approval_impact(self):
        organization = create_test_organization(org_id='lint-override-org-b', name='Lint Override Org B')
        profile = create_test_routing_intent_profile(name='Lint Override Profile B', organization=organization)
        derivation_run = create_test_intent_derivation_run(
            name='Lint Override Derivation B',
            organization=organization,
            intent_profile=profile,
        )
        reconciliation_run = create_test_roa_reconciliation_run(
            name='Lint Override Reconciliation B',
            organization=organization,
            intent_profile=profile,
            basis_derivation_run=derivation_run,
        )
        change_plan = create_test_roa_change_plan(
            name='Lint Override Plan B',
            organization=organization,
            source_reconciliation_run=reconciliation_run,
        )
        create_test_roa_change_plan_item(
            name='Lint Override Plan Item B',
            change_plan=change_plan,
            action_type=rpki_models.ROAChangePlanAction.CREATE,
            after_state_json={
                'prefix_cidr_text': '10.221.0.0/24',
                'origin_asn_value': 65221,
                'max_length': 26,
            },
        )
        create_test_roa_lint_rule_config(
            name='Lint Override Approval Impact Config',
            organization=organization,
            finding_code=LINT_RULE_PLAN_BROADENS_AUTHORIZATION,
            approval_impact_override='blocking',
        )

        lint_run = run_roa_lint(reconciliation_run, change_plan=change_plan)

        finding = lint_run.findings.get(finding_code=LINT_RULE_PLAN_BROADENS_AUTHORIZATION)
        self.assertEqual(finding.details_json['approval_impact'], 'blocking')
        self.assertEqual(build_roa_change_plan_lint_posture(change_plan)['status'], 'blocked')

    def test_org_override_not_applied_to_other_org(self):
        organization_a = create_test_organization(org_id='lint-override-org-c1', name='Lint Override Org C1')
        organization_b = create_test_organization(org_id='lint-override-org-c2', name='Lint Override Org C2')
        profile_b = create_test_routing_intent_profile(name='Lint Override Profile C2', organization=organization_b)
        derivation_run_b = create_test_intent_derivation_run(
            name='Lint Override Derivation C2',
            organization=organization_b,
            intent_profile=profile_b,
        )
        roa_intent_b = create_test_roa_intent(
            name='Lint Override Intent C2',
            organization=organization_b,
            derivation_run=derivation_run_b,
            intent_profile=profile_b,
            prefix=create_test_prefix('10.222.0.0/24', status='active'),
            origin_asn=create_test_asn(65222),
            origin_asn_value=65222,
            max_length=24,
        )
        reconciliation_run_b = create_test_roa_reconciliation_run(
            name='Lint Override Reconciliation C2',
            organization=organization_b,
            intent_profile=profile_b,
            basis_derivation_run=derivation_run_b,
        )
        create_test_roa_intent_result(
            name='Lint Override Intent Result C2',
            reconciliation_run=reconciliation_run_b,
            roa_intent=roa_intent_b,
            result_type=rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            details_json={
                'intent_prefix': '10.222.0.0/24',
                'intent_max_length': 24,
                'published_max_length': 26,
            },
        )
        create_test_roa_lint_rule_config(
            name='Lint Override Severity Config Other Org',
            organization=organization_a,
            finding_code=LINT_RULE_INTENT_OVERBROAD,
            severity_override=rpki_models.ReconciliationSeverity.CRITICAL,
        )

        lint_run = run_roa_lint(reconciliation_run_b)

        finding = lint_run.findings.get(finding_code=LINT_RULE_INTENT_OVERBROAD)
        self.assertEqual(finding.severity, rpki_models.ReconciliationSeverity.WARNING)

    def test_org_override_unknown_code_raises(self):
        config = create_test_roa_lint_rule_config(
            name='Lint Override Invalid Code',
            finding_code='not_a_real_code',
        )

        with self.assertRaises(ValidationError):
            config.full_clean()


class ROALintSuppressionScopeTestCase(TestCase):
    def _build_reconciliation_context(self, *, org_id: str, name: str, prefix_text: str, asn_value: int):
        organization = create_test_organization(org_id=org_id, name=name)
        profile = create_test_routing_intent_profile(name=f'{name} Profile', organization=organization)
        derivation_run = create_test_intent_derivation_run(
            name=f'{name} Derivation',
            organization=organization,
            intent_profile=profile,
        )
        roa_intent = create_test_roa_intent(
            name=f'{name} Intent {prefix_text}',
            organization=organization,
            derivation_run=derivation_run,
            intent_profile=profile,
            prefix=create_test_prefix(prefix_text, status='active'),
            origin_asn=create_test_asn(asn_value),
            origin_asn_value=asn_value,
            max_length=24,
        )
        reconciliation_run = create_test_roa_reconciliation_run(
            name=f'{name} Reconciliation',
            organization=organization,
            intent_profile=profile,
            basis_derivation_run=derivation_run,
        )
        return organization, profile, roa_intent, reconciliation_run

    def test_org_scope_suppresses_all_findings_for_code(self):
        organization, _, _, reconciliation_run = self._build_reconciliation_context(
            org_id='lint-scope-org-a',
            name='Lint Scope Org A',
            prefix_text='192.0.2.0/24',
            asn_value=65230,
        )
        intent_a = create_test_roa_intent(
            name='Lint Scope Intent A',
            organization=organization,
            derivation_run=reconciliation_run.basis_derivation_run,
            intent_profile=reconciliation_run.intent_profile,
            prefix=create_test_prefix('198.51.100.0/24', status='active'),
            origin_asn=create_test_asn(65231),
            origin_asn_value=65231,
            max_length=24,
        )
        create_test_roa_intent_result(
            name='Lint Scope Result A',
            reconciliation_run=reconciliation_run,
            roa_intent=intent_a,
            result_type=rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            details_json={'intent_prefix': '198.51.100.0/24', 'intent_max_length': 24, 'published_max_length': 26},
        )
        create_test_roa_intent_result(
            name='Lint Scope Result B',
            reconciliation_run=reconciliation_run,
            roa_intent=create_test_roa_intent(
                name='Lint Scope Intent B',
                organization=organization,
                derivation_run=reconciliation_run.basis_derivation_run,
                intent_profile=reconciliation_run.intent_profile,
                prefix=create_test_prefix('203.0.113.0/24', status='active'),
                origin_asn=create_test_asn(65232),
                origin_asn_value=65232,
                max_length=24,
            ),
            result_type=rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            details_json={'intent_prefix': '203.0.113.0/24', 'intent_max_length': 24, 'published_max_length': 26},
        )
        create_test_roa_lint_suppression(
            name='Org Overbroad Suppression',
            organization=organization,
            scope_type=rpki_models.ROALintSuppressionScope.ORG,
            finding_code=LINT_RULE_INTENT_OVERBROAD,
            fact_fingerprint='',
            fact_context_json={},
        )

        lint_run = run_roa_lint(reconciliation_run)

        findings = list(lint_run.findings.filter(finding_code=LINT_RULE_INTENT_OVERBROAD).order_by('name'))
        self.assertEqual(len(findings), 2)
        self.assertTrue(all(finding.details_json['suppressed'] for finding in findings))

    def test_org_scope_does_not_suppress_other_codes(self):
        organization, _, roa_intent, reconciliation_run = self._build_reconciliation_context(
            org_id='lint-scope-org-b',
            name='Lint Scope Org B',
            prefix_text='192.0.2.0/24',
            asn_value=65233,
        )
        create_test_roa_intent_result(
            name='Lint Scope Suppressed Result',
            reconciliation_run=reconciliation_run,
            roa_intent=roa_intent,
            result_type=rpki_models.ROAIntentResultType.SUPPRESSED_BY_POLICY,
            severity=rpki_models.ReconciliationSeverity.INFO,
            details_json={'intent_prefix': '192.0.2.0/24'},
        )
        create_test_roa_lint_suppression(
            name='Org Overbroad Suppression B',
            organization=organization,
            scope_type=rpki_models.ROALintSuppressionScope.ORG,
            finding_code=LINT_RULE_INTENT_OVERBROAD,
            fact_fingerprint='',
            fact_context_json={},
        )

        lint_run = run_roa_lint(reconciliation_run)

        finding = lint_run.findings.get(finding_code=LINT_RULE_INTENT_SUPPRESSED)
        self.assertFalse(finding.details_json['suppressed'])

    def test_prefix_scope_suppresses_matching_prefix_only(self):
        organization, _, _, reconciliation_run = self._build_reconciliation_context(
            org_id='lint-scope-org-c',
            name='Lint Scope Org C',
            prefix_text='192.0.2.0/24',
            asn_value=65234,
        )
        create_test_roa_intent_result(
            name='Prefix Match Result',
            reconciliation_run=reconciliation_run,
            roa_intent=create_test_roa_intent(
                name='Prefix Match Intent',
                organization=organization,
                derivation_run=reconciliation_run.basis_derivation_run,
                intent_profile=reconciliation_run.intent_profile,
                prefix=create_test_prefix('192.0.2.0/24', status='active'),
                origin_asn=create_test_asn(65235),
                origin_asn_value=65235,
                max_length=24,
            ),
            result_type=rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            details_json={'intent_prefix': '192.0.2.0/24', 'intent_max_length': 24, 'published_max_length': 26},
        )
        create_test_roa_intent_result(
            name='Prefix Nonmatch Result',
            reconciliation_run=reconciliation_run,
            roa_intent=create_test_roa_intent(
                name='Prefix Nonmatch Intent',
                organization=organization,
                derivation_run=reconciliation_run.basis_derivation_run,
                intent_profile=reconciliation_run.intent_profile,
                prefix=create_test_prefix('10.0.0.0/8', status='active'),
                origin_asn=create_test_asn(65236),
                origin_asn_value=65236,
                max_length=8,
            ),
            result_type=rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
            severity=rpki_models.ReconciliationSeverity.WARNING,
            details_json={'intent_prefix': '10.0.0.0/8', 'intent_max_length': 8, 'published_max_length': 12},
        )
        create_test_roa_lint_suppression(
            name='Prefix Scoped Suppression',
            organization=organization,
            scope_type=rpki_models.ROALintSuppressionScope.PREFIX,
            finding_code=LINT_RULE_INTENT_OVERBROAD,
            prefix_cidr_text='192.0.2.0/24',
            fact_fingerprint='',
            fact_context_json={},
        )

        lint_run = run_roa_lint(reconciliation_run)

        matching = lint_run.findings.get(name='Prefix Match Result intent_max_length_overbroad')
        nonmatching = lint_run.findings.get(name='Prefix Nonmatch Result intent_max_length_overbroad')
        self.assertTrue(matching.details_json['suppressed'])
        self.assertFalse(nonmatching.details_json['suppressed'])

    def test_suppress_finding_creates_org_suppression(self):
        organization, _, roa_intent, reconciliation_run = self._build_reconciliation_context(
            org_id='lint-scope-org-d',
            name='Lint Scope Org D',
            prefix_text='198.51.100.0/24',
            asn_value=65237,
        )
        lint_run = create_test_roa_lint_run(reconciliation_run=reconciliation_run)
        finding = create_test_roa_lint_finding(
            lint_run=lint_run,
            roa_intent_result=create_test_roa_intent_result(
                reconciliation_run=reconciliation_run,
                roa_intent=roa_intent,
                result_type=rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
                severity=rpki_models.ReconciliationSeverity.WARNING,
                details_json={'intent_prefix': '198.51.100.0/24'},
            ),
            finding_code=LINT_RULE_INTENT_OVERBROAD,
            details_json={'intent_prefix': '198.51.100.0/24'},
        )

        suppression = suppress_roa_lint_finding(
            finding,
            scope_type=rpki_models.ROALintSuppressionScope.ORG,
            reason='Suppress all org findings for this code.',
        )

        self.assertEqual(suppression.organization, organization)
        self.assertEqual(suppression.fact_fingerprint, '')
        self.assertEqual(suppression.prefix_cidr_text, '')

    def test_suppress_finding_creates_prefix_suppression(self):
        _, _, roa_intent, reconciliation_run = self._build_reconciliation_context(
            org_id='lint-scope-org-e',
            name='Lint Scope Org E',
            prefix_text='203.0.113.0/24',
            asn_value=65238,
        )
        lint_run = create_test_roa_lint_run(reconciliation_run=reconciliation_run)
        finding = create_test_roa_lint_finding(
            lint_run=lint_run,
            roa_intent_result=create_test_roa_intent_result(
                reconciliation_run=reconciliation_run,
                roa_intent=roa_intent,
                result_type=rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
                severity=rpki_models.ReconciliationSeverity.WARNING,
                details_json={'intent_prefix': '203.0.113.0/24'},
            ),
            finding_code=LINT_RULE_INTENT_OVERBROAD,
            details_json={'intent_prefix': '203.0.113.0/24'},
        )

        suppression = suppress_roa_lint_finding(
            finding,
            scope_type=rpki_models.ROALintSuppressionScope.PREFIX,
            reason='Suppress for this prefix.',
        )

        self.assertEqual(suppression.fact_fingerprint, '')
        self.assertEqual(suppression.prefix_cidr_text, '203.0.113.0/24')

    def test_suppress_finding_prefix_scope_raises_without_prefix_field(self):
        organization, profile, roa_intent, reconciliation_run = self._build_reconciliation_context(
            org_id='lint-scope-org-f',
            name='Lint Scope Org F',
            prefix_text='198.18.0.0/15',
            asn_value=65239,
        )
        lint_run = create_test_roa_lint_run(reconciliation_run=reconciliation_run)
        finding = create_test_roa_lint_finding(
            lint_run=lint_run,
            roa_intent_result=create_test_roa_intent_result(
                reconciliation_run=reconciliation_run,
                roa_intent=roa_intent,
                result_type=rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
                severity=rpki_models.ReconciliationSeverity.WARNING,
                details_json={'intent_max_length': 15},
            ),
            finding_code=LINT_RULE_INTENT_OVERBROAD,
            details_json={'intent_max_length': 15},
        )

        with self.assertRaisesMessage(ValueError, 'PREFIX-scoped suppressions require a finding with a resolvable prefix field.'):
            suppress_roa_lint_finding(
                finding,
                scope_type=rpki_models.ROALintSuppressionScope.PREFIX,
                reason='No prefix available.',
            )

    def test_suppression_clean_org_rejects_linked_intent(self):
        organization, profile, roa_intent, _ = self._build_reconciliation_context(
            org_id='lint-scope-org-g',
            name='Lint Scope Org G',
            prefix_text='100.64.0.0/10',
            asn_value=65240,
        )
        suppression = rpki_models.ROALintSuppression(
            name='Invalid Org Suppression',
            organization=organization,
            tenant=organization.tenant,
            finding_code=LINT_RULE_INTENT_OVERBROAD,
            scope_type=rpki_models.ROALintSuppressionScope.ORG,
            intent_profile=profile,
            roa_intent=roa_intent,
            reason='Invalid by design.',
            fact_fingerprint='',
            fact_context_json={},
        )

        with self.assertRaises(ValidationError):
            suppression.full_clean()


class ROALintOwnershipContextTestCase(TestCase):
    def _build_owned_context(
        self,
        *,
        org_id: str,
        name: str,
        owned_asn: int | None = None,
        owned_prefixes: tuple[str, ...] = (),
    ):
        tenant = Tenant.objects.create(name=f'{name} Tenant', slug=f'{org_id}-tenant')
        organization = create_test_organization(org_id=org_id, name=name, tenant=tenant)
        if owned_asn is not None:
            create_test_asn(owned_asn, tenant=tenant)
        for prefix in owned_prefixes:
            create_test_prefix(prefix, tenant=tenant, status='active')
        profile = create_test_routing_intent_profile(name=f'{name} Profile', organization=organization)
        derivation_run = create_test_intent_derivation_run(
            name=f'{name} Derivation',
            organization=organization,
            intent_profile=profile,
        )
        reconciliation_run = create_test_roa_reconciliation_run(
            name=f'{name} Reconciliation',
            organization=organization,
            intent_profile=profile,
            basis_derivation_run=derivation_run,
        )
        return organization, profile, derivation_run, reconciliation_run

    def test_intent_asn_not_in_org_creates_finding(self):
        organization, profile, derivation_run, reconciliation_run = self._build_owned_context(
            org_id='lint-own-org-a',
            name='Lint Ownership Org A',
            owned_asn=65300,
            owned_prefixes=('192.0.2.0/24',),
        )
        roa_intent = create_test_roa_intent(
            name='Foreign ASN Intent',
            organization=organization,
            derivation_run=derivation_run,
            intent_profile=profile,
            prefix=create_test_prefix('192.0.2.0/24', status='active'),
            origin_asn=create_test_asn(65301),
            origin_asn_value=65301,
            max_length=24,
        )
        create_test_roa_intent_result(
            name='Foreign ASN Intent Result',
            reconciliation_run=reconciliation_run,
            roa_intent=roa_intent,
            result_type=rpki_models.ROAIntentResultType.MATCH,
            details_json={'intent_prefix': '192.0.2.0/24'},
        )

        lint_run = run_roa_lint(reconciliation_run)

        finding = lint_run.findings.get(finding_code=LINT_RULE_INTENT_ASN_NOT_IN_ORG)
        self.assertEqual(finding.details_json['intent_origin_asn'], 65301)

    def test_no_asn_data_no_findings(self):
        organization, profile, derivation_run, reconciliation_run = self._build_owned_context(
            org_id='lint-own-org-b',
            name='Lint Ownership Org B',
            owned_prefixes=('198.51.100.0/24',),
        )
        roa_intent = create_test_roa_intent(
            name='No ASN Ownership Intent',
            organization=organization,
            derivation_run=derivation_run,
            intent_profile=profile,
            prefix=create_test_prefix('198.51.100.0/24', status='active'),
            origin_asn=create_test_asn(65302),
            origin_asn_value=65302,
            max_length=24,
        )
        create_test_roa_intent_result(
            name='No ASN Ownership Intent Result',
            reconciliation_run=reconciliation_run,
            roa_intent=roa_intent,
            result_type=rpki_models.ROAIntentResultType.MATCH,
            details_json={'intent_prefix': '198.51.100.0/24'},
        )

        lint_run = run_roa_lint(reconciliation_run)

        self.assertFalse(lint_run.findings.filter(finding_code=LINT_RULE_INTENT_ASN_NOT_IN_ORG).exists())

    def test_prefix_not_in_ipam_creates_finding(self):
        organization, profile, derivation_run, reconciliation_run = self._build_owned_context(
            org_id='lint-own-org-c',
            name='Lint Ownership Org C',
            owned_asn=65303,
            owned_prefixes=('192.0.2.0/24',),
        )
        roa_intent = create_test_roa_intent(
            name='No IPAM Match Intent',
            organization=organization,
            derivation_run=derivation_run,
            intent_profile=profile,
            prefix=create_test_prefix('203.0.113.0/24', status='active'),
            origin_asn=create_test_asn(65303),
            origin_asn_value=65303,
            max_length=24,
        )
        create_test_roa_intent_result(
            name='No IPAM Match Result',
            reconciliation_run=reconciliation_run,
            roa_intent=roa_intent,
            result_type=rpki_models.ROAIntentResultType.MATCH,
            details_json={'intent_prefix': '203.0.113.0/24'},
        )

        lint_run = run_roa_lint(reconciliation_run)

        finding = lint_run.findings.get(finding_code=LINT_RULE_INTENT_PREFIX_NOT_IN_ORG)
        self.assertEqual(finding.details_json['intent_prefix'], '203.0.113.0/24')

    def test_ownership_findings_suppressible_org_scope(self):
        organization, profile, derivation_run, reconciliation_run = self._build_owned_context(
            org_id='lint-own-org-d',
            name='Lint Ownership Org D',
            owned_asn=65304,
            owned_prefixes=('192.0.2.0/24',),
        )
        roa_intent = create_test_roa_intent(
            name='Suppressed Ownership Intent',
            organization=organization,
            derivation_run=derivation_run,
            intent_profile=profile,
            prefix=create_test_prefix('192.0.2.0/24', status='active'),
            origin_asn=create_test_asn(65305),
            origin_asn_value=65305,
            max_length=24,
        )
        create_test_roa_intent_result(
            name='Suppressed Ownership Result',
            reconciliation_run=reconciliation_run,
            roa_intent=roa_intent,
            result_type=rpki_models.ROAIntentResultType.MATCH,
            details_json={'intent_prefix': '192.0.2.0/24'},
        )
        create_test_roa_lint_suppression(
            name='Ownership Org Suppression',
            organization=organization,
            scope_type=rpki_models.ROALintSuppressionScope.ORG,
            finding_code=LINT_RULE_INTENT_ASN_NOT_IN_ORG,
            fact_fingerprint='',
            fact_context_json={},
        )

        lint_run = run_roa_lint(reconciliation_run)

        finding = lint_run.findings.get(finding_code=LINT_RULE_INTENT_ASN_NOT_IN_ORG)
        self.assertTrue(finding.details_json['suppressed'])

    def test_org_override_escalates_ownership_finding(self):
        organization, _, _, reconciliation_run = self._build_owned_context(
            org_id='lint-own-org-e',
            name='Lint Ownership Org E',
            owned_asn=65306,
            owned_prefixes=('198.51.100.0/24',),
        )
        change_plan = create_test_roa_change_plan(
            name='Ownership Override Plan',
            organization=organization,
            source_reconciliation_run=reconciliation_run,
        )
        create_test_roa_change_plan_item(
            name='Ownership Override Plan Item',
            change_plan=change_plan,
            action_type=rpki_models.ROAChangePlanAction.CREATE,
            after_state_json={
                'prefix_cidr_text': '198.51.100.0/24',
                'origin_asn_value': 65307,
                'max_length': 24,
            },
        )
        create_test_roa_lint_rule_config(
            name='Ownership Override Config',
            organization=organization,
            finding_code=LINT_RULE_PLAN_CROSS_ORG_AUTHORIZATION,
            approval_impact_override='acknowledgement_required',
        )

        lint_run = run_roa_lint(reconciliation_run, change_plan=change_plan)

        finding = lint_run.findings.get(finding_code=LINT_RULE_PLAN_CROSS_ORG_AUTHORIZATION)
        self.assertEqual(finding.details_json['approval_impact'], 'acknowledgement_required')
        self.assertEqual(build_roa_change_plan_lint_posture(change_plan)['status'], 'acknowledgement_required')

    def test_published_cross_org_origin_finding(self):
        organization, _, _, reconciliation_run = self._build_owned_context(
            org_id='lint-own-org-f',
            name='Lint Ownership Org F',
            owned_asn=65308,
        )
        create_test_published_roa_result(
            name='Foreign Published Result',
            reconciliation_run=reconciliation_run,
            result_type=rpki_models.PublishedROAResultType.MATCHED,
            details_json={
                'prefix_cidr_text': '203.0.113.0/24',
                'origin_asn': 65309,
                'max_length': 24,
            },
        )

        lint_run = run_roa_lint(reconciliation_run)

        finding = lint_run.findings.get(finding_code=LINT_RULE_PUBLISHED_CROSS_ORG_ORIGIN)
        self.assertEqual(finding.details_json['origin_asn'], 65309)
