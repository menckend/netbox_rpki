from __future__ import annotations

from collections import Counter

from django.utils import timezone

from netbox_rpki import models as rpki_models


DELEGATED_WORKFLOW_SUMMARY_SCHEMA_VERSION = 1


def approve_delegated_publication_workflow(
    workflow: rpki_models.DelegatedPublicationWorkflow,
    *,
    approved_by: str,
) -> rpki_models.DelegatedPublicationWorkflow:
    if not workflow.requires_approval:
        raise ValueError('This delegated publication workflow does not require approval.')
    if workflow.approved_at is not None:
        raise ValueError('This delegated publication workflow is already approved.')
    if workflow.status == rpki_models.DelegatedPublicationWorkflowStatus.ARCHIVED:
        raise ValueError('Archived delegated publication workflows cannot be approved.')

    workflow.approved_at = timezone.now()
    workflow.approved_by = approved_by
    workflow.save(update_fields=('approved_at', 'approved_by'))
    return workflow


def build_delegated_publication_workflow_summary(
    workflow: rpki_models.DelegatedPublicationWorkflow,
) -> dict[str, object]:
    relationship = workflow.managed_relationship
    delegated_entity = relationship.delegated_entity
    approval_required = bool(workflow.requires_approval)
    approval_missing = approval_required and (workflow.approved_at is None or not workflow.approved_by)
    approval_state = 'not_required'
    if approval_required:
        approval_state = 'awaiting_approval' if approval_missing else 'approved'

    missing_prerequisites: list[str] = []
    if relationship.status != rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE:
        missing_prerequisites.append('managed_relationship_inactive')
    if not delegated_entity.enabled:
        missing_prerequisites.append('delegated_entity_disabled')
    if not (workflow.child_ca_handle or '').strip():
        missing_prerequisites.append('missing_child_ca_handle')
    if not _publication_endpoint(workflow):
        missing_prerequisites.append('missing_publication_endpoint')
    if approval_missing:
        missing_prerequisites.append('awaiting_approval')

    linkage_summary = _build_workflow_linkage_summary(workflow)
    effective_status = _workflow_effective_status(workflow, approval_state=approval_state, missing_prerequisites=missing_prerequisites)

    return {
        'summary_schema_version': DELEGATED_WORKFLOW_SUMMARY_SCHEMA_VERSION,
        'workflow_id': workflow.pk,
        'workflow_name': workflow.name,
        'status': workflow.status,
        'status_label': workflow.get_status_display(),
        'effective_status': effective_status,
        'is_effective': effective_status == rpki_models.DelegatedPublicationWorkflowStatus.ACTIVE,
        'requires_attention': bool(
            missing_prerequisites
            or linkage_summary['linkage_status'] != 'linked'
            or effective_status != rpki_models.DelegatedPublicationWorkflowStatus.ACTIVE
        ),
        'approval': {
            'requires_approval': approval_required,
            'approval_state': approval_state,
            'approved_at': workflow.approved_at.isoformat() if workflow.approved_at is not None else '',
            'approved_by': workflow.approved_by or '',
        },
        'managed_relationship': {
            'id': relationship.pk,
            'name': relationship.name,
            'status': relationship.status,
            'status_label': relationship.get_status_display(),
            'provider_account_id': relationship.provider_account_id,
            'delegated_entity_id': relationship.delegated_entity_id,
            'delegated_entity_enabled': bool(delegated_entity.enabled),
        },
        'publication_endpoint': _publication_endpoint(workflow),
        'missing_prerequisites': missing_prerequisites,
        'linkage': linkage_summary,
    }


def build_managed_authorization_relationship_summary(
    relationship: rpki_models.ManagedAuthorizationRelationship,
) -> dict[str, object]:
    workflows = list(
        relationship.publication_workflows.select_related('managed_relationship__delegated_entity').all()
    )
    workflow_summaries = [build_delegated_publication_workflow_summary(workflow) for workflow in workflows]
    status_counts = Counter(workflow.status for workflow in workflows)
    effective_workflow_count = sum(1 for summary in workflow_summaries if summary['is_effective'])
    awaiting_approval_count = sum(
        1
        for summary in workflow_summaries
        if summary['approval']['approval_state'] == 'awaiting_approval'
    )
    attention_workflow_count = sum(1 for summary in workflow_summaries if summary['requires_attention'])
    linked_authored_ids = sorted(
        {
            relationship_id
            for summary in workflow_summaries
            for relationship_id in summary['linkage']['linked_authored_ca_relationship_ids']
        }
    )

    return {
        'summary_schema_version': DELEGATED_WORKFLOW_SUMMARY_SCHEMA_VERSION,
        'relationship_id': relationship.pk,
        'relationship_name': relationship.name,
        'relationship_status': relationship.status,
        'relationship_status_label': relationship.get_status_display(),
        'delegated_entity_enabled': bool(relationship.delegated_entity.enabled),
        'provider_account_id': relationship.provider_account_id,
        'workflow_count': len(workflows),
        'workflow_status_counts': dict(status_counts),
        'effective_workflow_count': effective_workflow_count,
        'awaiting_approval_count': awaiting_approval_count,
        'attention_workflow_count': attention_workflow_count,
        'linked_authored_ca_relationship_count': len(linked_authored_ids),
        'linked_authored_ca_relationship_ids': linked_authored_ids,
        'requires_attention': bool(
            relationship.status != rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE
            or not relationship.delegated_entity.enabled
            or attention_workflow_count
        ),
    }


def build_delegated_authorization_entity_summary(
    entity: rpki_models.DelegatedAuthorizationEntity,
) -> dict[str, object]:
    relationships = list(
        entity.managed_authorization_relationships.select_related('delegated_entity', 'provider_account').all()
    )
    relationship_summaries = [
        build_managed_authorization_relationship_summary(relationship)
        for relationship in relationships
    ]
    relationship_status_counts = Counter(relationship.status for relationship in relationships)
    workflow_count = sum(summary['workflow_count'] for summary in relationship_summaries)
    effective_workflow_count = sum(summary['effective_workflow_count'] for summary in relationship_summaries)
    awaiting_approval_count = sum(summary['awaiting_approval_count'] for summary in relationship_summaries)
    attention_workflow_count = sum(summary['attention_workflow_count'] for summary in relationship_summaries)
    provider_account_ids = sorted(
        {
            relationship.provider_account_id
            for relationship in relationships
            if relationship.provider_account_id is not None
        }
    )

    return {
        'summary_schema_version': DELEGATED_WORKFLOW_SUMMARY_SCHEMA_VERSION,
        'delegated_entity_id': entity.pk,
        'delegated_entity_name': entity.name,
        'enabled': bool(entity.enabled),
        'relationship_count': len(relationships),
        'relationship_status_counts': dict(relationship_status_counts),
        'active_relationship_count': relationship_status_counts.get(
            rpki_models.ManagedAuthorizationRelationshipStatus.ACTIVE,
            0,
        ),
        'workflow_count': workflow_count,
        'effective_workflow_count': effective_workflow_count,
        'awaiting_approval_count': awaiting_approval_count,
        'attention_workflow_count': attention_workflow_count,
        'provider_account_count': len(provider_account_ids),
        'provider_account_ids': provider_account_ids,
        'requires_attention': bool(
            not entity.enabled
            or any(summary['requires_attention'] for summary in relationship_summaries)
        ),
    }


def build_authored_ca_relationship_delegated_summary(
    relationship: rpki_models.AuthoredCaRelationship,
) -> dict[str, object]:
    linked_workflows = list(_matching_workflows_for_authored_relationship(relationship))
    status_counts = Counter(workflow.status for workflow in linked_workflows)
    workflow_summaries = [
        build_delegated_publication_workflow_summary(workflow)
        for workflow in linked_workflows
    ]

    if linked_workflows:
        linkage_status = 'linked'
    elif _candidate_workflows_for_authored_relationship(relationship).exists():
        linkage_status = 'partial'
    else:
        linkage_status = 'unlinked'

    return {
        'summary_schema_version': DELEGATED_WORKFLOW_SUMMARY_SCHEMA_VERSION,
        'authored_ca_relationship_id': relationship.pk,
        'workflow_count': len(linked_workflows),
        'workflow_status_counts': dict(status_counts),
        'effective_workflow_count': sum(1 for summary in workflow_summaries if summary['is_effective']),
        'workflow_ids': [workflow.pk for workflow in linked_workflows],
        'workflow_names': [workflow.name for workflow in linked_workflows],
        'linkage_status': linkage_status,
        'requires_attention': linkage_status != 'linked',
    }


def _workflow_effective_status(
    workflow: rpki_models.DelegatedPublicationWorkflow,
    *,
    approval_state: str,
    missing_prerequisites: list[str],
) -> str:
    if workflow.status != rpki_models.DelegatedPublicationWorkflowStatus.ACTIVE:
        return workflow.status
    if approval_state == 'awaiting_approval':
        return 'awaiting_approval'
    if missing_prerequisites:
        return 'attention_required'
    return rpki_models.DelegatedPublicationWorkflowStatus.ACTIVE


def _publication_endpoint(workflow: rpki_models.DelegatedPublicationWorkflow) -> str:
    return (workflow.publication_server_uri or workflow.managed_relationship.service_uri or '').strip()


def _matching_authored_relationships_for_workflow(
    workflow: rpki_models.DelegatedPublicationWorkflow,
):
    queryset = rpki_models.AuthoredCaRelationship.objects.filter(
        organization=workflow.organization,
        child_ca_handle=workflow.child_ca_handle,
    )
    provider_account_id = workflow.managed_relationship.provider_account_id
    if provider_account_id is not None:
        queryset = queryset.filter(provider_account_id=provider_account_id)
    if workflow.parent_ca_handle:
        queryset = queryset.filter(parent_ca_handle=workflow.parent_ca_handle)
    return queryset.order_by('pk')


def _candidate_authored_relationships_for_workflow(
    workflow: rpki_models.DelegatedPublicationWorkflow,
):
    queryset = rpki_models.AuthoredCaRelationship.objects.filter(
        organization=workflow.organization,
        child_ca_handle=workflow.child_ca_handle,
    )
    provider_account_id = workflow.managed_relationship.provider_account_id
    if provider_account_id is not None:
        queryset = queryset.filter(
            provider_account_id=provider_account_id,
        ) | queryset.filter(
            organization=workflow.organization,
            child_ca_handle=workflow.child_ca_handle,
            provider_account__isnull=True,
        )
    return queryset.order_by('pk').distinct()


def _build_workflow_linkage_summary(
    workflow: rpki_models.DelegatedPublicationWorkflow,
) -> dict[str, object]:
    linked_relationships = list(_matching_authored_relationships_for_workflow(workflow))
    candidate_relationships = list(_candidate_authored_relationships_for_workflow(workflow))

    linkage_status = 'linked'
    if not linked_relationships:
        linkage_status = 'partial' if candidate_relationships else 'unlinked'

    return {
        'linkage_status': linkage_status,
        'linked_authored_ca_relationship_count': len(linked_relationships),
        'linked_authored_ca_relationship_ids': [relationship.pk for relationship in linked_relationships],
        'candidate_authored_ca_relationship_count': len(candidate_relationships),
        'candidate_authored_ca_relationship_ids': [relationship.pk for relationship in candidate_relationships],
    }


def _matching_workflows_for_authored_relationship(
    relationship: rpki_models.AuthoredCaRelationship,
):
    queryset = rpki_models.DelegatedPublicationWorkflow.objects.filter(
        organization=relationship.organization,
        child_ca_handle=relationship.child_ca_handle,
    )
    if relationship.parent_ca_handle:
        queryset = queryset.filter(parent_ca_handle=relationship.parent_ca_handle)
    if relationship.provider_account_id is not None:
        queryset = queryset.filter(managed_relationship__provider_account_id=relationship.provider_account_id)
    return queryset.select_related('managed_relationship', 'managed_relationship__delegated_entity').order_by('pk')


def _candidate_workflows_for_authored_relationship(
    relationship: rpki_models.AuthoredCaRelationship,
):
    return rpki_models.DelegatedPublicationWorkflow.objects.filter(
        organization=relationship.organization,
        child_ca_handle=relationship.child_ca_handle,
    ).order_by('pk')
