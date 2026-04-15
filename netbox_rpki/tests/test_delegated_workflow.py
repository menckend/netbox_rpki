from django.test import TestCase

from netbox_rpki import models as rpki_models
from netbox_rpki.services import (
    approve_delegated_publication_workflow,
    build_authored_ca_relationship_delegated_summary,
    build_delegated_authorization_entity_summary,
    build_delegated_publication_workflow_summary,
    build_managed_authorization_relationship_summary,
)
from netbox_rpki.tests.utils import (
    create_test_organization,
    create_test_provider_account,
)


class DelegatedPublicationWorkflowServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = create_test_organization(
            org_id='delegated-workflow-service-org',
            name='Delegated Workflow Service Org',
        )
        cls.provider_account = create_test_provider_account(
            name='Delegated Workflow Service Provider',
            organization=cls.organization,
            org_handle='ORG-DELEGATED-SERVICE',
        )
        cls.entity = rpki_models.DelegatedAuthorizationEntity.objects.create(
            name='Delegated Workflow Service Entity',
            organization=cls.organization,
            kind=rpki_models.DelegatedAuthorizationEntityKind.CUSTOMER,
        )
        cls.relationship = rpki_models.ManagedAuthorizationRelationship.objects.create(
            name='Delegated Workflow Service Relationship',
            organization=cls.organization,
            delegated_entity=cls.entity,
            provider_account=cls.provider_account,
            status=rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
        )
        cls.workflow = rpki_models.DelegatedPublicationWorkflow.objects.create(
            name='Delegated Workflow Service Workflow',
            organization=cls.organization,
            managed_relationship=cls.relationship,
            child_ca_handle='delegated-service-child',
            publication_server_uri='https://publication.example.invalid/service/',
            status=rpki_models.DelegatedPublicationWorkflowStatus.ACTIVE,
            requires_approval=True,
        )
        cls.authored_relationship = rpki_models.AuthoredCaRelationship.objects.create(
            name='Delegated Workflow Service Authored Relationship',
            organization=cls.organization,
            provider_account=cls.provider_account,
            child_ca_handle='delegated-service-child',
            relationship_type=rpki_models.AuthoredCaRelationshipType.PARENT,
            status=rpki_models.AuthoredCaRelationshipStatus.ACTIVE,
        )

    def test_workflow_summary_reports_approval_and_linkage_posture(self):
        summary = build_delegated_publication_workflow_summary(self.workflow)

        self.assertEqual(summary['approval']['approval_state'], 'awaiting_approval')
        self.assertEqual(summary['linkage']['linkage_status'], 'linked')
        self.assertIn(self.authored_relationship.pk, summary['linkage']['linked_authored_ca_relationship_ids'])
        self.assertTrue(summary['requires_attention'])

    def test_relationship_and_entity_summaries_aggregate_workflow_counts(self):
        relationship_summary = build_managed_authorization_relationship_summary(self.relationship)
        entity_summary = build_delegated_authorization_entity_summary(self.entity)
        authored_summary = build_authored_ca_relationship_delegated_summary(self.authored_relationship)

        self.assertEqual(relationship_summary['workflow_count'], 1)
        self.assertEqual(relationship_summary['linked_authored_ca_relationship_count'], 1)
        self.assertEqual(entity_summary['workflow_count'], 1)
        self.assertEqual(entity_summary['relationship_count'], 1)
        self.assertEqual(authored_summary['workflow_count'], 1)
        self.assertEqual(authored_summary['linkage_status'], 'linked')

    def test_approve_workflow_records_actor_and_clears_approval_attention(self):
        approve_delegated_publication_workflow(self.workflow, approved_by='delegated-approver')

        self.workflow.refresh_from_db()
        summary = build_delegated_publication_workflow_summary(self.workflow)

        self.assertEqual(self.workflow.approved_by, 'delegated-approver')
        self.assertIsNotNone(self.workflow.approved_at)
        self.assertEqual(summary['approval']['approval_state'], 'approved')
        self.assertNotIn('awaiting_approval', summary['missing_prerequisites'])

    def test_approve_workflow_rejects_non_approval_workflow(self):
        workflow = rpki_models.DelegatedPublicationWorkflow.objects.create(
            name='Delegated Workflow No Approval',
            organization=self.organization,
            managed_relationship=self.relationship,
            child_ca_handle='delegated-no-approval',
            publication_server_uri='https://publication.example.invalid/no-approval/',
            status=rpki_models.DelegatedPublicationWorkflowStatus.ACTIVE,
            requires_approval=False,
        )

        with self.assertRaisesMessage(ValueError, 'does not require approval'):
            approve_delegated_publication_workflow(workflow, approved_by='ignored-user')
