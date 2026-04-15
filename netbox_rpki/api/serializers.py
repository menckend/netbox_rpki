from django.core.exceptions import ObjectDoesNotExist
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework.serializers import HyperlinkedIdentityField
from rest_framework import serializers

from netbox_rpki import models
from netbox_rpki.services import build_roa_change_plan_lint_posture
from netbox_rpki.services.roa_lint import build_roa_lint_lifecycle_summary
from netbox_rpki.object_registry import API_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec
from netbox_rpki.services.lifecycle_reporting import (
    build_provider_lifecycle_health_summary,
    build_diff_publication_health_rollup,
    build_snapshot_publication_health_rollup,
)
from netbox_rpki.services.governance_rollup import build_organization_governance_rollup
from netbox_rpki.services.publication_state import (
    derive_change_plan_publication_state,
    derive_rollback_bundle_publication_state,
)
from netbox_rpki.services.delegated_workflow import (
    build_authored_ca_relationship_delegated_summary,
    build_delegated_authorization_entity_summary,
    build_delegated_publication_workflow_summary,
    build_managed_authorization_relationship_summary,
)
from netbox_rpki.services.provider_sync_contract import (
    build_provider_account_rollup,
    build_provider_snapshot_diff_rollup,
    build_provider_snapshot_rollup,
)
from netbox_rpki.services.provider_sync_evidence import (
    get_certificate_observation_evidence_summary,
    get_certificate_observation_is_ambiguous,
    get_certificate_observation_publication_linkage_status,
    get_certificate_observation_signed_object_linkage_status,
    get_certificate_observation_source_count,
    get_certificate_observation_source_labels,
    get_publication_point_authored_linkage_status,
    get_publication_point_evidence_summary,
    get_signed_object_authored_linkage_status,
    get_signed_object_evidence_summary,
    get_signed_object_publication_linkage_status,
)
from netbox_rpki.services.overlay_correlation import (
    build_aspa_overlay_summary,
    build_imported_certificate_observation_overlay_summary,
    build_imported_signed_object_overlay_summary,
    build_roa_overlay_summary,
    build_signed_object_overlay_summary,
)
from netbox_rpki.services.overlay_reporting import (
    build_aspa_change_plan_overlay_summary,
    build_aspa_reconciliation_overlay_summary,
    build_roa_change_plan_overlay_summary,
    build_roa_reconciliation_overlay_summary,
)
from netbox_rpki.services.overlay_history import (
    build_telemetry_run_comparison,
    build_telemetry_run_history_summary,
    build_validation_run_comparison,
    build_validator_run_history_summary,
)

def _simulation_run_summary(run):
    summary = dict(run.summary_json or {})
    summary.setdefault('plan_fingerprint', run.plan_fingerprint)
    summary.setdefault('overall_approval_posture', run.overall_approval_posture)
    summary.setdefault('is_current_for_plan', run.is_current_for_plan)
    summary.setdefault('partially_constrained', run.partially_constrained)
    return summary


def _simulation_result_details(result):
    details = dict(result.details_json or {})
    details.setdefault('approval_impact', result.approval_impact)
    details.setdefault('scenario_type', result.scenario_type)
    return details


def _brief_related_object(obj, *, extra_fields=None):
    payload = {
        'id': obj.pk,
        'name': str(obj),
        'object_url': obj.get_absolute_url(),
    }
    for field_name in extra_fields or ():
        payload[field_name] = getattr(obj, field_name)
    return payload


def _brief_related_collection(queryset, *, extra_fields=None):
    return [
        _brief_related_object(obj, extra_fields=extra_fields)
        for obj in queryset
    ]


def build_serializer_class(spec: ObjectSpec) -> type[NetBoxModelSerializer]:
    meta_class = type(
        "Meta",
        (),
        {
            "model": spec.model,
            "fields": spec.api.fields,
            "brief_fields": spec.api.brief_fields,
        },
    )

    return type(
        spec.api.serializer_name,
        (NetBoxModelSerializer,),
        {
            "__module__": __name__,
            "url": HyperlinkedIdentityField(view_name=spec.api.detail_view_name),
            "Meta": meta_class,
        },
    )


SERIALIZER_CLASS_MAP = {}
for object_spec in API_OBJECT_SPECS:
    serializer_class = build_serializer_class(object_spec)
    SERIALIZER_CLASS_MAP[object_spec.registry_key] = serializer_class
    globals()[object_spec.api.serializer_name] = serializer_class


class OrganizationSerializer(SERIALIZER_CLASS_MAP['organization']):
    governance_rollup = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['organization'].Meta):
        fields = SERIALIZER_CLASS_MAP['organization'].Meta.fields + (
            'governance_rollup',
        )

    def get_governance_rollup(self, obj):
        return build_organization_governance_rollup(obj)


SERIALIZER_CLASS_MAP['organization'] = OrganizationSerializer
globals()['OrganizationSerializer'] = OrganizationSerializer


class DelegatedAuthorizationEntitySerializer(SERIALIZER_CLASS_MAP['delegatedauthorizationentity']):
    entity_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['delegatedauthorizationentity'].Meta):
        fields = SERIALIZER_CLASS_MAP['delegatedauthorizationentity'].Meta.fields + (
            'entity_summary',
        )

    def get_entity_summary(self, obj):
        return build_delegated_authorization_entity_summary(obj)


SERIALIZER_CLASS_MAP['delegatedauthorizationentity'] = DelegatedAuthorizationEntitySerializer
globals()['DelegatedAuthorizationEntitySerializer'] = DelegatedAuthorizationEntitySerializer


class ManagedAuthorizationRelationshipSerializer(SERIALIZER_CLASS_MAP['managedauthorizationrelationship']):
    relationship_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['managedauthorizationrelationship'].Meta):
        fields = SERIALIZER_CLASS_MAP['managedauthorizationrelationship'].Meta.fields + (
            'relationship_summary',
        )

    def get_relationship_summary(self, obj):
        return build_managed_authorization_relationship_summary(obj)


SERIALIZER_CLASS_MAP['managedauthorizationrelationship'] = ManagedAuthorizationRelationshipSerializer
globals()['ManagedAuthorizationRelationshipSerializer'] = ManagedAuthorizationRelationshipSerializer


class DelegatedPublicationWorkflowSerializer(SERIALIZER_CLASS_MAP['delegatedpublicationworkflow']):
    workflow_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['delegatedpublicationworkflow'].Meta):
        fields = SERIALIZER_CLASS_MAP['delegatedpublicationworkflow'].Meta.fields + (
            'workflow_summary',
        )

    def get_workflow_summary(self, obj):
        return build_delegated_publication_workflow_summary(obj)


SERIALIZER_CLASS_MAP['delegatedpublicationworkflow'] = DelegatedPublicationWorkflowSerializer
globals()['DelegatedPublicationWorkflowSerializer'] = DelegatedPublicationWorkflowSerializer


class AuthoredCaRelationshipSerializer(SERIALIZER_CLASS_MAP['authoredcarelationship']):
    delegated_workflow_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['authoredcarelationship'].Meta):
        fields = SERIALIZER_CLASS_MAP['authoredcarelationship'].Meta.fields + (
            'delegated_workflow_summary',
        )

    def get_delegated_workflow_summary(self, obj):
        return build_authored_ca_relationship_delegated_summary(obj)


SERIALIZER_CLASS_MAP['authoredcarelationship'] = AuthoredCaRelationshipSerializer
globals()['AuthoredCaRelationshipSerializer'] = AuthoredCaRelationshipSerializer


class ValidatorInstanceSerializer(SERIALIZER_CLASS_MAP['validatorinstance']):
    summary = serializers.SerializerMethodField()
    run_history_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['validatorinstance'].Meta):
        fields = SERIALIZER_CLASS_MAP['validatorinstance'].Meta.fields + (
            'summary',
            'run_history_summary',
        )

    def get_summary(self, obj):
        return obj.summary_json or {}

    def get_run_history_summary(self, obj):
        return build_validator_run_history_summary(obj)


SERIALIZER_CLASS_MAP['validatorinstance'] = ValidatorInstanceSerializer
globals()['ValidatorInstanceSerializer'] = ValidatorInstanceSerializer


class ValidationRunSerializer(SERIALIZER_CLASS_MAP['validationrun']):
    summary = serializers.SerializerMethodField()
    comparison_to_previous = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['validationrun'].Meta):
        fields = SERIALIZER_CLASS_MAP['validationrun'].Meta.fields + (
            'summary',
            'comparison_to_previous',
        )

    def get_summary(self, obj):
        return obj.summary_json or {}

    def get_comparison_to_previous(self, obj):
        return build_validation_run_comparison(obj)


SERIALIZER_CLASS_MAP['validationrun'] = ValidationRunSerializer
globals()['ValidationRunSerializer'] = ValidationRunSerializer


class ObjectValidationResultSerializer(SERIALIZER_CLASS_MAP['objectvalidationresult']):
    details = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['objectvalidationresult'].Meta):
        fields = SERIALIZER_CLASS_MAP['objectvalidationresult'].Meta.fields + (
            'details',
        )

    def get_details(self, obj):
        return obj.details_json or {}


SERIALIZER_CLASS_MAP['objectvalidationresult'] = ObjectValidationResultSerializer
globals()['ObjectValidationResultSerializer'] = ObjectValidationResultSerializer


class ValidatedRoaPayloadSerializer(SERIALIZER_CLASS_MAP['validatedroapayload']):
    details = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['validatedroapayload'].Meta):
        fields = SERIALIZER_CLASS_MAP['validatedroapayload'].Meta.fields + (
            'details',
        )

    def get_details(self, obj):
        return obj.details_json or {}


SERIALIZER_CLASS_MAP['validatedroapayload'] = ValidatedRoaPayloadSerializer
globals()['ValidatedRoaPayloadSerializer'] = ValidatedRoaPayloadSerializer


class ValidatedAspaPayloadSerializer(SERIALIZER_CLASS_MAP['validatedaspapayload']):
    details = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['validatedaspapayload'].Meta):
        fields = SERIALIZER_CLASS_MAP['validatedaspapayload'].Meta.fields + (
            'details',
        )

    def get_details(self, obj):
        return obj.details_json or {}


SERIALIZER_CLASS_MAP['validatedaspapayload'] = ValidatedAspaPayloadSerializer
globals()['ValidatedAspaPayloadSerializer'] = ValidatedAspaPayloadSerializer


class TelemetrySourceSerializer(SERIALIZER_CLASS_MAP['telemetrysource']):
    sync_health = serializers.ReadOnlyField()
    sync_health_display = serializers.ReadOnlyField()
    run_history_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['telemetrysource'].Meta):
        fields = SERIALIZER_CLASS_MAP['telemetrysource'].Meta.fields + (
            'sync_health',
            'sync_health_display',
            'run_history_summary',
        )

    def get_run_history_summary(self, obj):
        return build_telemetry_run_history_summary(obj)


SERIALIZER_CLASS_MAP['telemetrysource'] = TelemetrySourceSerializer
globals()['TelemetrySourceSerializer'] = TelemetrySourceSerializer


class TelemetryRunSerializer(SERIALIZER_CLASS_MAP['telemetryrun']):
    summary = serializers.SerializerMethodField()
    comparison_to_previous = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['telemetryrun'].Meta):
        fields = SERIALIZER_CLASS_MAP['telemetryrun'].Meta.fields + (
            'summary',
            'comparison_to_previous',
        )

    def get_summary(self, obj):
        return obj.summary_json or {}

    def get_comparison_to_previous(self, obj):
        return build_telemetry_run_comparison(obj)


SERIALIZER_CLASS_MAP['telemetryrun'] = TelemetryRunSerializer
globals()['TelemetryRunSerializer'] = TelemetryRunSerializer


class BgpPathObservationSerializer(SERIALIZER_CLASS_MAP['bgppathobservation']):
    details = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['bgppathobservation'].Meta):
        fields = SERIALIZER_CLASS_MAP['bgppathobservation'].Meta.fields + (
            'details',
        )

    def get_details(self, obj):
        return obj.details_json or {}


SERIALIZER_CLASS_MAP['bgppathobservation'] = BgpPathObservationSerializer
globals()['BgpPathObservationSerializer'] = BgpPathObservationSerializer


class RpkiProviderAccountSerializer(SERIALIZER_CLASS_MAP['rpkiprovideraccount']):
    supports_roa_write = serializers.ReadOnlyField()
    roa_write_mode = serializers.ReadOnlyField()
    roa_write_capability = serializers.ReadOnlyField()
    supports_aspa_write = serializers.ReadOnlyField()
    aspa_write_mode = serializers.ReadOnlyField()
    aspa_write_capability = serializers.ReadOnlyField()
    capability_matrix = serializers.ReadOnlyField()
    sync_health = serializers.ReadOnlyField()
    sync_health_display = serializers.ReadOnlyField()
    last_sync_rollup = serializers.SerializerMethodField()
    lifecycle_health_summary = serializers.SerializerMethodField()
    publication_health = serializers.SerializerMethodField()
    next_sync_due_at = serializers.DateTimeField(read_only=True)

    class Meta(SERIALIZER_CLASS_MAP['rpkiprovideraccount'].Meta):
        fields = SERIALIZER_CLASS_MAP['rpkiprovideraccount'].Meta.fields + (
            'supports_roa_write',
            'roa_write_mode',
            'roa_write_capability',
            'supports_aspa_write',
            'aspa_write_mode',
            'aspa_write_capability',
            'capability_matrix',
            'sync_health',
            'sync_health_display',
            'last_sync_rollup',
            'lifecycle_health_summary',
            'publication_health',
            'next_sync_due_at',
        )

    def get_last_sync_rollup(self, obj):
        request = self.context.get('request')
        visible_snapshot_ids = None
        visible_diff_ids = None

        if request is not None and request.user.is_authenticated:
            summary = obj.last_sync_summary_json or {}
            snapshot_id = summary.get('latest_snapshot_id')
            diff_id = summary.get('latest_diff_id')
            if snapshot_id is not None:
                visible_snapshot_ids = set(
                    models.ProviderSnapshot.objects.restrict(request.user, 'view')
                    .filter(pk=snapshot_id)
                    .values_list('pk', flat=True)
                )
            if diff_id is not None:
                visible_diff_ids = set(
                    models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
                    .filter(pk=diff_id)
                    .values_list('pk', flat=True)
                )

        return build_provider_account_rollup(
            obj,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )

    def get_lifecycle_health_summary(self, obj):
        request = self.context.get('request')
        visible_snapshot_ids = None
        visible_diff_ids = None

        if request is not None and request.user.is_authenticated:
            summary = obj.last_sync_summary_json or {}
            snapshot_id = summary.get('latest_snapshot_id')
            diff_id = summary.get('latest_diff_id')
            if snapshot_id is not None:
                visible_snapshot_ids = set(
                    models.ProviderSnapshot.objects.restrict(request.user, 'view')
                    .filter(pk=snapshot_id)
                    .values_list('pk', flat=True)
                )
            if diff_id is not None:
                visible_diff_ids = set(
                    models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
                    .filter(pk=diff_id)
                    .values_list('pk', flat=True)
                )

        return build_provider_lifecycle_health_summary(
            obj,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )

    def get_publication_health(self, obj):
        return build_provider_account_rollup(obj).get('publication_health') or {}


SERIALIZER_CLASS_MAP['rpkiprovideraccount'] = RpkiProviderAccountSerializer
globals()['RpkiProviderAccountSerializer'] = RpkiProviderAccountSerializer


class ROAReconciliationRunSerializer(SERIALIZER_CLASS_MAP['roareconciliationrun']):
    latest_lint_run = serializers.SerializerMethodField()
    latest_lint_summary = serializers.SerializerMethodField()
    latest_lint_lifecycle_summary = serializers.SerializerMethodField()
    external_overlay_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['roareconciliationrun'].Meta):
        fields = SERIALIZER_CLASS_MAP['roareconciliationrun'].Meta.fields + (
            'latest_lint_run',
            'latest_lint_summary',
            'latest_lint_lifecycle_summary',
            'external_overlay_summary',
        )

    def get_latest_lint_run(self, obj):
        lint_run = obj.lint_runs.order_by('-started_at', '-created').first()
        if lint_run is None:
            return None
        serializer = SERIALIZER_CLASS_MAP['roalintrun'](lint_run, context=self.context)
        return serializer.data

    def get_latest_lint_summary(self, obj):
        lint_run = obj.lint_runs.order_by('-started_at', '-created').first()
        if lint_run is None:
            return None
        return lint_run.summary_json

    def get_latest_lint_lifecycle_summary(self, obj):
        lint_run = obj.lint_runs.order_by('-started_at', '-created').first()
        if lint_run is None:
            return None
        return build_roa_lint_lifecycle_summary(lint_run)

    def get_external_overlay_summary(self, obj):
        return build_roa_reconciliation_overlay_summary(obj)


SERIALIZER_CLASS_MAP['roareconciliationrun'] = ROAReconciliationRunSerializer
globals()['ROAReconciliationRunSerializer'] = ROAReconciliationRunSerializer


class ASPAReconciliationRunSerializer(SERIALIZER_CLASS_MAP['aspareconciliationrun']):
    external_overlay_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['aspareconciliationrun'].Meta):
        fields = SERIALIZER_CLASS_MAP['aspareconciliationrun'].Meta.fields + (
            'external_overlay_summary',
        )

    def get_external_overlay_summary(self, obj):
        return build_aspa_reconciliation_overlay_summary(obj)


SERIALIZER_CLASS_MAP['aspareconciliationrun'] = ASPAReconciliationRunSerializer
globals()['ASPAReconciliationRunSerializer'] = ASPAReconciliationRunSerializer


class ROAChangePlanSerializer(SERIALIZER_CLASS_MAP['roachangeplan']):
    publication_state = serializers.SerializerMethodField()
    latest_lint_run = serializers.SerializerMethodField()
    latest_lint_summary = serializers.SerializerMethodField()
    latest_lint_posture = serializers.SerializerMethodField()
    latest_lint_lifecycle_summary = serializers.SerializerMethodField()
    latest_simulation_run = serializers.SerializerMethodField()
    latest_simulation_summary = serializers.SerializerMethodField()
    latest_simulation_posture = serializers.SerializerMethodField()
    external_overlay_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['roachangeplan'].Meta):
        fields = SERIALIZER_CLASS_MAP['roachangeplan'].Meta.fields + (
            'publication_state',
            'latest_lint_run',
            'latest_lint_summary',
            'latest_lint_posture',
            'latest_lint_lifecycle_summary',
            'latest_simulation_run',
            'latest_simulation_summary',
            'latest_simulation_posture',
            'external_overlay_summary',
        )

    def get_latest_lint_run(self, obj):
        lint_run = obj.lint_runs.order_by('-started_at', '-created').first()
        if lint_run is None:
            return None
        serializer = SERIALIZER_CLASS_MAP['roalintrun'](lint_run, context=self.context)
        return serializer.data

    def get_latest_lint_summary(self, obj):
        lint_run = obj.lint_runs.order_by('-started_at', '-created').first()
        if lint_run is None:
            return None
        return lint_run.summary_json

    def get_latest_lint_posture(self, obj):
        return build_roa_change_plan_lint_posture(obj)

    def get_latest_lint_lifecycle_summary(self, obj):
        lint_run = obj.lint_runs.order_by('-started_at', '-created').first()
        if lint_run is None:
            return None
        return build_roa_lint_lifecycle_summary(lint_run, change_plan=obj)

    def get_latest_simulation_run(self, obj):
        simulation_run = obj.simulation_runs.order_by('-started_at', '-created').first()
        if simulation_run is None:
            return None
        serializer = SERIALIZER_CLASS_MAP['roavalidationsimulationrun'](simulation_run, context=self.context)
        return serializer.data

    def get_latest_simulation_summary(self, obj):
        simulation_run = obj.simulation_runs.order_by('-started_at', '-created').first()
        if simulation_run is None:
            return None
        return _simulation_run_summary(simulation_run)

    def get_latest_simulation_posture(self, obj):
        simulation_run = obj.simulation_runs.order_by('-started_at', '-created').first()
        if simulation_run is None:
            return None
        summary = _simulation_run_summary(simulation_run)
        return {
            'run_id': simulation_run.pk,
            'plan_fingerprint': summary.get('plan_fingerprint'),
            'overall_approval_posture': summary.get('overall_approval_posture'),
            'is_current_for_plan': summary.get('is_current_for_plan'),
            'partially_constrained': summary.get('partially_constrained'),
            'approval_impact_counts': summary.get('approval_impact_counts') or {},
            'scenario_type_counts': summary.get('scenario_type_counts') or {},
        }

    def get_publication_state(self, obj):
        return derive_change_plan_publication_state(obj).as_dict()

    def get_external_overlay_summary(self, obj):
        return build_roa_change_plan_overlay_summary(obj)


SERIALIZER_CLASS_MAP['roachangeplan'] = ROAChangePlanSerializer
globals()['ROAChangePlanSerializer'] = ROAChangePlanSerializer


class ASPAChangePlanSerializer(SERIALIZER_CLASS_MAP['aspachangeplan']):
    publication_state = serializers.SerializerMethodField()
    external_overlay_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['aspachangeplan'].Meta):
        fields = SERIALIZER_CLASS_MAP['aspachangeplan'].Meta.fields + (
            'publication_state',
            'external_overlay_summary',
        )

    def get_publication_state(self, obj):
        return derive_change_plan_publication_state(obj).as_dict()

    def get_external_overlay_summary(self, obj):
        return build_aspa_change_plan_overlay_summary(obj)


SERIALIZER_CLASS_MAP['aspachangeplan'] = ASPAChangePlanSerializer
globals()['ASPAChangePlanSerializer'] = ASPAChangePlanSerializer


class ROAChangePlanRollbackBundleSerializer(SERIALIZER_CLASS_MAP['roachangeplanrollbackbundle']):
    publication_state = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['roachangeplanrollbackbundle'].Meta):
        fields = SERIALIZER_CLASS_MAP['roachangeplanrollbackbundle'].Meta.fields + (
            'publication_state',
        )

    def get_publication_state(self, obj):
        return derive_rollback_bundle_publication_state(obj).as_dict()


SERIALIZER_CLASS_MAP['roachangeplanrollbackbundle'] = ROAChangePlanRollbackBundleSerializer
globals()['ROAChangePlanRollbackBundleSerializer'] = ROAChangePlanRollbackBundleSerializer


class ASPAChangePlanRollbackBundleSerializer(SERIALIZER_CLASS_MAP['aspachangeplanrollbackbundle']):
    publication_state = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['aspachangeplanrollbackbundle'].Meta):
        fields = SERIALIZER_CLASS_MAP['aspachangeplanrollbackbundle'].Meta.fields + (
            'publication_state',
        )

    def get_publication_state(self, obj):
        return derive_rollback_bundle_publication_state(obj).as_dict()


SERIALIZER_CLASS_MAP['aspachangeplanrollbackbundle'] = ASPAChangePlanRollbackBundleSerializer
globals()['ASPAChangePlanRollbackBundleSerializer'] = ASPAChangePlanRollbackBundleSerializer


class ROAValidationSimulationRunSerializer(SERIALIZER_CLASS_MAP['roavalidationsimulationrun']):
    approval_impact_counts = serializers.SerializerMethodField()
    scenario_type_counts = serializers.SerializerMethodField()
    affected_intended_route_count = serializers.SerializerMethodField()
    affected_collateral_route_count = serializers.SerializerMethodField()
    normalized_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['roavalidationsimulationrun'].Meta):
        fields = SERIALIZER_CLASS_MAP['roavalidationsimulationrun'].Meta.fields + (
            'plan_fingerprint',
            'overall_approval_posture',
            'is_current_for_plan',
            'partially_constrained',
            'approval_impact_counts',
            'scenario_type_counts',
            'affected_intended_route_count',
            'affected_collateral_route_count',
            'normalized_summary',
        )

    def get_approval_impact_counts(self, obj):
        return _simulation_run_summary(obj).get('approval_impact_counts') or {}

    def get_scenario_type_counts(self, obj):
        return _simulation_run_summary(obj).get('scenario_type_counts') or {}

    def get_affected_intended_route_count(self, obj):
        return _simulation_run_summary(obj).get('affected_intended_route_count', 0)

    def get_affected_collateral_route_count(self, obj):
        return _simulation_run_summary(obj).get('affected_collateral_route_count', 0)

    def get_normalized_summary(self, obj):
        return _simulation_run_summary(obj)


SERIALIZER_CLASS_MAP['roavalidationsimulationrun'] = ROAValidationSimulationRunSerializer
globals()['ROAValidationSimulationRunSerializer'] = ROAValidationSimulationRunSerializer


class ROAValidationSimulationResultSerializer(SERIALIZER_CLASS_MAP['roavalidationsimulationresult']):
    operator_message = serializers.SerializerMethodField()
    why_it_matters = serializers.SerializerMethodField()
    operator_action = serializers.SerializerMethodField()
    impact_scope = serializers.SerializerMethodField()
    plan_fingerprint = serializers.SerializerMethodField()
    before_coverage = serializers.SerializerMethodField()
    after_coverage = serializers.SerializerMethodField()
    affected_prefixes = serializers.SerializerMethodField()
    affected_origin_asns = serializers.SerializerMethodField()
    collateral_impact_count = serializers.SerializerMethodField()
    transition_risk = serializers.SerializerMethodField()
    explanation = serializers.SerializerMethodField()
    normalized_details = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['roavalidationsimulationresult'].Meta):
        fields = SERIALIZER_CLASS_MAP['roavalidationsimulationresult'].Meta.fields + (
            'approval_impact',
            'scenario_type',
            'operator_message',
            'why_it_matters',
            'operator_action',
            'impact_scope',
            'plan_fingerprint',
            'before_coverage',
            'after_coverage',
            'affected_prefixes',
            'affected_origin_asns',
            'collateral_impact_count',
            'transition_risk',
            'explanation',
            'normalized_details',
        )

    def get_operator_message(self, obj):
        return _simulation_result_details(obj).get('operator_message')

    def get_why_it_matters(self, obj):
        return _simulation_result_details(obj).get('why_it_matters')

    def get_operator_action(self, obj):
        return _simulation_result_details(obj).get('operator_action')

    def get_impact_scope(self, obj):
        return _simulation_result_details(obj).get('impact_scope')

    def get_plan_fingerprint(self, obj):
        return _simulation_result_details(obj).get('plan_fingerprint')

    def get_before_coverage(self, obj):
        return _simulation_result_details(obj).get('before_coverage') or {}

    def get_after_coverage(self, obj):
        return _simulation_result_details(obj).get('after_coverage') or {}

    def get_affected_prefixes(self, obj):
        return _simulation_result_details(obj).get('affected_prefixes') or []

    def get_affected_origin_asns(self, obj):
        return _simulation_result_details(obj).get('affected_origin_asns') or []

    def get_collateral_impact_count(self, obj):
        return _simulation_result_details(obj).get('collateral_impact_count', 0)

    def get_transition_risk(self, obj):
        return _simulation_result_details(obj).get('transition_risk')

    def get_explanation(self, obj):
        return _simulation_result_details(obj).get('explanation')

    def get_normalized_details(self, obj):
        return _simulation_result_details(obj)


SERIALIZER_CLASS_MAP['roavalidationsimulationresult'] = ROAValidationSimulationResultSerializer
globals()['ROAValidationSimulationResultSerializer'] = ROAValidationSimulationResultSerializer


class ProviderSnapshotSerializer(SERIALIZER_CLASS_MAP['providersnapshot']):
    latest_diff = serializers.SerializerMethodField()
    latest_diff_summary = serializers.SerializerMethodField()
    family_rollups = serializers.SerializerMethodField()
    family_status_counts = serializers.SerializerMethodField()
    publication_health = serializers.SerializerMethodField()
    imported_publication_points = serializers.SerializerMethodField()
    imported_signed_objects = serializers.SerializerMethodField()
    imported_certificate_observations = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['providersnapshot'].Meta):
        fields = SERIALIZER_CLASS_MAP['providersnapshot'].Meta.fields + (
            'latest_diff',
            'latest_diff_summary',
            'family_rollups',
            'family_status_counts',
            'publication_health',
            'imported_publication_points',
            'imported_signed_objects',
            'imported_certificate_observations',
        )

    def _is_expanded_view(self):
        request = self.context.get('request')
        if request is None:
            return False
        parser_context = getattr(request, 'parser_context', None) or {}
        view = parser_context.get('view')
        return getattr(view, 'action', '') in {'retrieve', 'compare'}

    def _serialize_nested_collection(self, obj, *, related_name, serializer_key, select_related_fields=()):
        if not self._is_expanded_view():
            return []
        serializer_class = SERIALIZER_CLASS_MAP[serializer_key]
        queryset = getattr(obj, related_name).all()
        if select_related_fields:
            queryset = queryset.select_related(*select_related_fields)
        return serializer_class(queryset, many=True, context=self.context).data

    def get_latest_diff(self, obj):
        if not self._is_expanded_view():
            return None
        snapshot_diff = obj.diffs_as_comparison.order_by('-compared_at', '-created').first()
        if snapshot_diff is None:
            return None
        serializer = SERIALIZER_CLASS_MAP['providersnapshotdiff'](snapshot_diff, context=self.context)
        return serializer.data

    def get_latest_diff_summary(self, obj):
        if not self._is_expanded_view():
            return None
        request = self.context.get('request')
        visible_diff_ids = None
        if request is not None and request.user.is_authenticated:
            visible_diff_ids = set(
                models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
                .filter(comparison_snapshot=obj)
                .values_list('pk', flat=True)
            )
        return build_provider_snapshot_rollup(obj, visible_diff_ids=visible_diff_ids)['latest_diff_summary']

    def get_family_rollups(self, obj):
        return build_provider_snapshot_rollup(obj)['family_rollups']

    def get_family_status_counts(self, obj):
        return build_provider_snapshot_rollup(obj)['family_status_counts']

    def get_publication_health(self, obj):
        return build_snapshot_publication_health_rollup(obj)

    def get_imported_publication_points(self, obj):
        return self._serialize_nested_collection(
            obj,
            related_name='imported_publication_points',
            serializer_key='importedpublicationpoint',
        )

    def get_imported_signed_objects(self, obj):
        return self._serialize_nested_collection(
            obj,
            related_name='imported_signed_objects',
            serializer_key='importedsignedobject',
            select_related_fields=('external_reference', 'publication_point'),
        )

    def get_imported_certificate_observations(self, obj):
        return self._serialize_nested_collection(
            obj,
            related_name='imported_certificate_observations',
            serializer_key='importedcertificateobservation',
            select_related_fields=('external_reference', 'publication_point', 'signed_object'),
        )


class BulkIntentRunActionSerializer(serializers.Serializer):
    run_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    comparison_scope = serializers.ChoiceField(
        choices=models.ReconciliationComparisonScope.choices,
        default=models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
    )
    provider_snapshot = serializers.PrimaryKeyRelatedField(
        queryset=models.ProviderSnapshot.objects.all(),
        required=False,
        allow_null=True,
    )
    create_change_plans = serializers.BooleanField(required=False, default=False)
    profiles = serializers.PrimaryKeyRelatedField(
        queryset=models.RoutingIntentProfile.objects.all(),
        many=True,
        required=False,
    )
    bindings = serializers.PrimaryKeyRelatedField(
        queryset=models.RoutingIntentTemplateBinding.objects.all(),
        many=True,
        required=False,
    )

    def validate(self, attrs):
        organization = self.context.get('organization')
        profiles = attrs.get('profiles') or []
        bindings = attrs.get('bindings') or []
        provider_snapshot = attrs.get('provider_snapshot')
        if not profiles and not bindings:
            raise serializers.ValidationError(
                'Select at least one routing intent profile or template binding.'
            )
        if organization is None:
            return attrs
        invalid_profiles = [profile.pk for profile in profiles if profile.organization_id != organization.pk]
        if invalid_profiles:
            raise serializers.ValidationError({
                'profiles': 'All selected routing intent profiles must belong to the selected organization.'
            })
        invalid_bindings = [
            binding.pk for binding in bindings if binding.intent_profile.organization_id != organization.pk
        ]
        if invalid_bindings:
            raise serializers.ValidationError({
                'bindings': 'All selected template bindings must belong to the selected organization.'
            })
        if provider_snapshot is not None and provider_snapshot.organization_id != organization.pk:
            raise serializers.ValidationError({
                'provider_snapshot': 'Provider snapshot must belong to the selected organization.'
            })
        return attrs


class RoutingIntentProfileRunActionSerializer(serializers.Serializer):
    comparison_scope = serializers.ChoiceField(
        choices=models.ReconciliationComparisonScope.choices,
        default=models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
    )
    provider_snapshot = serializers.PrimaryKeyRelatedField(
        queryset=models.ProviderSnapshot.objects.all(),
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        comparison_scope = attrs.get(
            'comparison_scope',
            models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        )
        provider_snapshot = attrs.get('provider_snapshot')
        if comparison_scope == models.ReconciliationComparisonScope.PROVIDER_IMPORTED and provider_snapshot is None:
            raise serializers.ValidationError(
                {'provider_snapshot': 'Provider snapshot is required for provider-imported ROA reconciliation.'}
            )
        return attrs


SERIALIZER_CLASS_MAP['providersnapshot'] = ProviderSnapshotSerializer
globals()['ProviderSnapshotSerializer'] = ProviderSnapshotSerializer


class ProviderSnapshotDiffSerializer(SERIALIZER_CLASS_MAP['providersnapshotdiff']):
    family_rollups = serializers.SerializerMethodField()
    family_status_counts = serializers.SerializerMethodField()
    publication_diff_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['providersnapshotdiff'].Meta):
        fields = SERIALIZER_CLASS_MAP['providersnapshotdiff'].Meta.fields + (
            'family_rollups',
            'family_status_counts',
            'publication_diff_summary',
        )

    def get_family_rollups(self, obj):
        return build_provider_snapshot_diff_rollup(obj)['family_rollups']

    def get_family_status_counts(self, obj):
        return build_provider_snapshot_diff_rollup(obj)['family_status_counts']

    def get_publication_diff_summary(self, obj):
        return build_diff_publication_health_rollup(obj)


SERIALIZER_CLASS_MAP['providersnapshotdiff'] = ProviderSnapshotDiffSerializer
globals()['ProviderSnapshotDiffSerializer'] = ProviderSnapshotDiffSerializer


class RoutingIntentProfileSerializer(SERIALIZER_CLASS_MAP['routingintentprofile']):
    context_group_details = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['routingintentprofile'].Meta):
        fields = SERIALIZER_CLASS_MAP['routingintentprofile'].Meta.fields + (
            'context_group_details',
        )

    def get_context_group_details(self, obj):
        queryset = obj.context_groups.order_by('priority', 'name', 'pk')
        return _brief_related_collection(
            queryset,
            extra_fields=('context_type', 'priority', 'enabled'),
        )


SERIALIZER_CLASS_MAP['routingintentprofile'] = RoutingIntentProfileSerializer
globals()['RoutingIntentProfileSerializer'] = RoutingIntentProfileSerializer


class RoutingIntentContextGroupSerializer(SERIALIZER_CLASS_MAP['routingintentcontextgroup']):
    criteria_details = serializers.SerializerMethodField()
    intent_profile_details = serializers.SerializerMethodField()
    template_binding_details = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['routingintentcontextgroup'].Meta):
        fields = SERIALIZER_CLASS_MAP['routingintentcontextgroup'].Meta.fields + (
            'criteria_details',
            'intent_profile_details',
            'template_binding_details',
        )

    def get_criteria_details(self, obj):
        queryset = obj.criteria.select_related(
            'match_tenant',
            'match_vrf',
            'match_site',
            'match_region',
            'match_provider_account',
            'match_circuit',
            'match_provider',
        ).order_by('weight', 'name', 'pk')
        details = []
        for criterion in queryset:
            target = (
                criterion.match_tenant
                or criterion.match_vrf
                or criterion.match_site
                or criterion.match_region
                or criterion.match_provider_account
                or criterion.match_circuit
                or criterion.match_provider
                or criterion.match_value
                or None
            )
            details.append(
                {
                    'id': criterion.pk,
                    'name': str(criterion),
                    'object_url': criterion.get_absolute_url(),
                    'criterion_type': criterion.criterion_type,
                    'target': str(target) if target is not None else None,
                    'enabled': criterion.enabled,
                    'weight': criterion.weight,
                }
            )
        return details

    def get_intent_profile_details(self, obj):
        queryset = obj.intent_profiles.select_related('organization').order_by('name', 'pk')
        return _brief_related_collection(queryset, extra_fields=('status', 'enabled'))

    def get_template_binding_details(self, obj):
        queryset = obj.template_bindings.select_related('template', 'intent_profile').order_by(
            'intent_profile__name',
            'binding_priority',
            'name',
            'pk',
        )
        return _brief_related_collection(queryset, extra_fields=('state', 'binding_priority', 'enabled'))


SERIALIZER_CLASS_MAP['routingintentcontextgroup'] = RoutingIntentContextGroupSerializer
globals()['RoutingIntentContextGroupSerializer'] = RoutingIntentContextGroupSerializer


class RoutingIntentTemplateBindingSerializer(SERIALIZER_CLASS_MAP['routingintenttemplatebinding']):
    context_group_details = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['routingintenttemplatebinding'].Meta):
        fields = SERIALIZER_CLASS_MAP['routingintenttemplatebinding'].Meta.fields + (
            'context_group_details',
        )

    def get_context_group_details(self, obj):
        queryset = obj.context_groups.order_by('priority', 'name', 'pk')
        return _brief_related_collection(
            queryset,
            extra_fields=('context_type', 'priority', 'enabled'),
        )


SERIALIZER_CLASS_MAP['routingintenttemplatebinding'] = RoutingIntentTemplateBindingSerializer
globals()['RoutingIntentTemplateBindingSerializer'] = RoutingIntentTemplateBindingSerializer


class ImportedPublicationPointSerializer(SERIALIZER_CLASS_MAP['importedpublicationpoint']):
    authored_linkage_status = serializers.SerializerMethodField()
    evidence_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['importedpublicationpoint'].Meta):
        fields = SERIALIZER_CLASS_MAP['importedpublicationpoint'].Meta.fields + (
            'authored_linkage_status',
            'evidence_summary',
        )

    def get_authored_linkage_status(self, obj):
        return get_publication_point_authored_linkage_status(obj)

    def get_evidence_summary(self, obj):
        return get_publication_point_evidence_summary(obj)


SERIALIZER_CLASS_MAP['importedpublicationpoint'] = ImportedPublicationPointSerializer
globals()['ImportedPublicationPointSerializer'] = ImportedPublicationPointSerializer


class ImportedSignedObjectSerializer(SERIALIZER_CLASS_MAP['importedsignedobject']):
    publication_linkage_status = serializers.SerializerMethodField()
    authored_linkage_status = serializers.SerializerMethodField()
    evidence_summary = serializers.SerializerMethodField()
    external_overlay_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['importedsignedobject'].Meta):
        fields = SERIALIZER_CLASS_MAP['importedsignedobject'].Meta.fields + (
            'publication_linkage_status',
            'authored_linkage_status',
            'evidence_summary',
            'external_overlay_summary',
        )

    def get_publication_linkage_status(self, obj):
        return get_signed_object_publication_linkage_status(obj)

    def get_authored_linkage_status(self, obj):
        return get_signed_object_authored_linkage_status(obj)

    def get_evidence_summary(self, obj):
        return get_signed_object_evidence_summary(obj)

    def get_external_overlay_summary(self, obj):
        return build_imported_signed_object_overlay_summary(obj)


SERIALIZER_CLASS_MAP['importedsignedobject'] = ImportedSignedObjectSerializer
globals()['ImportedSignedObjectSerializer'] = ImportedSignedObjectSerializer


class ImportedCertificateObservationSerializer(SERIALIZER_CLASS_MAP['importedcertificateobservation']):
    source_count = serializers.SerializerMethodField()
    source_labels = serializers.SerializerMethodField()
    is_ambiguous = serializers.SerializerMethodField()
    publication_linkage_status = serializers.SerializerMethodField()
    signed_object_linkage_status = serializers.SerializerMethodField()
    evidence_summary = serializers.SerializerMethodField()
    external_overlay_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['importedcertificateobservation'].Meta):
        fields = SERIALIZER_CLASS_MAP['importedcertificateobservation'].Meta.fields + (
            'source_count',
            'source_labels',
            'is_ambiguous',
            'publication_linkage_status',
            'signed_object_linkage_status',
            'evidence_summary',
            'external_overlay_summary',
        )

    def get_source_count(self, obj):
        return get_certificate_observation_source_count(obj)

    def get_source_labels(self, obj):
        return get_certificate_observation_source_labels(obj)

    def get_is_ambiguous(self, obj):
        return get_certificate_observation_is_ambiguous(obj)

    def get_publication_linkage_status(self, obj):
        return get_certificate_observation_publication_linkage_status(obj)

    def get_signed_object_linkage_status(self, obj):
        return get_certificate_observation_signed_object_linkage_status(obj)

    def get_evidence_summary(self, obj):
        return get_certificate_observation_evidence_summary(obj)

    def get_external_overlay_summary(self, obj):
        return build_imported_certificate_observation_overlay_summary(obj)


SERIALIZER_CLASS_MAP['importedcertificateobservation'] = ImportedCertificateObservationSerializer
globals()['ImportedCertificateObservationSerializer'] = ImportedCertificateObservationSerializer


class SignedObjectSerializer(SERIALIZER_CLASS_MAP['signedobject']):
    roa_extension = serializers.SerializerMethodField()
    crl_extension = serializers.SerializerMethodField()
    manifest_extension = serializers.SerializerMethodField()
    trust_anchor_key_extension = serializers.SerializerMethodField()
    aspa_extension = serializers.SerializerMethodField()
    rsc_extension = serializers.SerializerMethodField()
    imported_signed_object_observations = serializers.SerializerMethodField()
    validation_results = serializers.SerializerMethodField()
    external_overlay_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['signedobject'].Meta):
        fields = SERIALIZER_CLASS_MAP['signedobject'].Meta.fields + (
            'roa_extension',
            'crl_extension',
            'manifest_extension',
            'trust_anchor_key_extension',
            'aspa_extension',
            'rsc_extension',
            'imported_signed_object_observations',
            'validation_results',
            'external_overlay_summary',
        )

    def _is_detail_view(self):
        request = self.context.get('request')
        if request is None:
            return False
        parser_context = getattr(request, 'parser_context', None) or {}
        view = parser_context.get('view')
        return getattr(view, 'action', '') == 'retrieve'

    def _serialize_related_object(self, obj, attribute_name, serializer_key):
        if not self._is_detail_view():
            return None
        try:
            related = getattr(obj, attribute_name)
        except ObjectDoesNotExist:
            return None
        if related is None:
            return None
        serializer_class = SERIALIZER_CLASS_MAP[serializer_key]
        return serializer_class(related, context=self.context).data

    def _serialize_related_collection(self, obj, *, related_name, serializer_key, select_related_fields=()):
        if not self._is_detail_view():
            return []
        serializer_class = SERIALIZER_CLASS_MAP[serializer_key]
        queryset = getattr(obj, related_name).all()
        if select_related_fields:
            queryset = queryset.select_related(*select_related_fields)
        return serializer_class(queryset, many=True, context=self.context).data

    def get_roa_extension(self, obj):
        return self._serialize_related_object(obj, 'roa_extension', 'roaobject')

    def get_crl_extension(self, obj):
        return self._serialize_related_object(obj, 'crl_extension', 'certificaterevocationlist')

    def get_manifest_extension(self, obj):
        return self._serialize_related_object(obj, 'manifest_extension', 'manifest')

    def get_trust_anchor_key_extension(self, obj):
        return self._serialize_related_object(obj, 'trust_anchor_key_extension', 'trustanchorkey')

    def get_aspa_extension(self, obj):
        return self._serialize_related_object(obj, 'aspa_extension', 'aspa')

    def get_rsc_extension(self, obj):
        return self._serialize_related_object(obj, 'rsc_extension', 'rsc')

    def get_imported_signed_object_observations(self, obj):
        return self._serialize_related_collection(
            obj,
            related_name='imported_signed_object_observations',
            serializer_key='importedsignedobject',
            select_related_fields=('provider_snapshot', 'publication_point', 'authored_signed_object'),
        )

    def get_validation_results(self, obj):
        return self._serialize_related_collection(
            obj,
            related_name='validation_results',
            serializer_key='objectvalidationresult',
            select_related_fields=('validation_run', 'signed_object'),
        )

    def get_external_overlay_summary(self, obj):
        return build_signed_object_overlay_summary(obj)


SERIALIZER_CLASS_MAP['signedobject'] = SignedObjectSerializer
globals()['SignedObjectSerializer'] = SignedObjectSerializer


class RoaObjectSerializer(SERIALIZER_CLASS_MAP['roaobject']):
    external_overlay_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['roaobject'].Meta):
        fields = SERIALIZER_CLASS_MAP['roaobject'].Meta.fields + (
            'external_overlay_summary',
        )

    def get_external_overlay_summary(self, obj):
        return build_roa_overlay_summary(obj)


SERIALIZER_CLASS_MAP['roaobject'] = RoaObjectSerializer
globals()['RoaObjectSerializer'] = RoaObjectSerializer


class ASPASerializer(SERIALIZER_CLASS_MAP['aspa']):
    external_overlay_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['aspa'].Meta):
        fields = SERIALIZER_CLASS_MAP['aspa'].Meta.fields + (
            'external_overlay_summary',
        )

    def get_external_overlay_summary(self, obj):
        return build_aspa_overlay_summary(obj)


SERIALIZER_CLASS_MAP['aspa'] = ASPASerializer
globals()['ASPASerializer'] = ASPASerializer


class ROAChangePlanApproveActionSerializer(serializers.Serializer):
    ticket_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    change_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    maintenance_window_start = serializers.DateTimeField(required=False, allow_null=True)
    maintenance_window_end = serializers.DateTimeField(required=False, allow_null=True)
    approval_notes = serializers.CharField(required=False, allow_blank=True)
    acknowledged_finding_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )
    previously_acknowledged_finding_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )
    acknowledged_simulation_result_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )
    lint_acknowledgement_notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        models.validate_maintenance_window_bounds(
            start_at=attrs.get('maintenance_window_start'),
            end_at=attrs.get('maintenance_window_end'),
        )
        return attrs


class ASPAChangePlanApproveActionSerializer(serializers.Serializer):
    requires_secondary_approval = serializers.BooleanField(required=False, default=False)
    ticket_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    change_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    maintenance_window_start = serializers.DateTimeField(required=False, allow_null=True)
    maintenance_window_end = serializers.DateTimeField(required=False, allow_null=True)
    approval_notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        models.validate_maintenance_window_bounds(
            start_at=attrs.get('maintenance_window_start'),
            end_at=attrs.get('maintenance_window_end'),
        )
        return attrs


class ROAChangePlanApproveSecondaryActionSerializer(serializers.Serializer):
    approval_notes = serializers.CharField(required=False, allow_blank=True, default='')


class ASPAChangePlanApproveSecondaryActionSerializer(serializers.Serializer):
    approval_notes = serializers.CharField(required=False, allow_blank=True, default='')


class RollbackBundleApproveActionSerializer(serializers.Serializer):
    ticket_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    change_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    maintenance_window_start = serializers.DateTimeField(required=False, allow_null=True)
    maintenance_window_end = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        models.validate_maintenance_window_bounds(
            start_at=attrs.get('maintenance_window_start'),
            end_at=attrs.get('maintenance_window_end'),
        )
        return attrs


class RollbackBundleApplyActionSerializer(serializers.Serializer):
    requested_by = serializers.CharField(required=False, allow_blank=True, default='')


class ROAChangePlanAcknowledgeActionSerializer(serializers.Serializer):
    ticket_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    change_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    acknowledged_finding_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )
    previously_acknowledged_finding_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )
    lint_acknowledgement_notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get('acknowledged_finding_ids') and not attrs.get('previously_acknowledged_finding_ids'):
            raise serializers.ValidationError(
                'Provide at least one current or previously acknowledged finding id.'
            )
        return attrs


class ROALintFindingSuppressActionSerializer(serializers.Serializer):
    scope_type = serializers.ChoiceField(choices=models.ROALintSuppressionScope.choices)
    reason = serializers.CharField(max_length=255)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class ROALintSuppressionLiftActionSerializer(serializers.Serializer):
    lift_reason = serializers.CharField(required=False, allow_blank=True)


class ASPAReconciliationRunActionSerializer(serializers.Serializer):
    comparison_scope = serializers.ChoiceField(
        choices=models.ReconciliationComparisonScope.choices,
        default=models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
    )
    provider_snapshot = serializers.PrimaryKeyRelatedField(
        queryset=models.ProviderSnapshot.objects.all(),
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        comparison_scope = attrs.get(
            'comparison_scope',
            models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
        )
        provider_snapshot = attrs.get('provider_snapshot')
        if comparison_scope == models.ReconciliationComparisonScope.PROVIDER_IMPORTED and provider_snapshot is None:
            raise serializers.ValidationError(
                {'provider_snapshot': 'Provider snapshot is required for provider-imported ASPA reconciliation.'}
            )
        return attrs


class RoutingIntentTemplateBindingRunActionSerializer(serializers.Serializer):
    comparison_scope = serializers.ChoiceField(
        choices=models.ReconciliationComparisonScope.choices,
        default=models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
    )
    provider_snapshot = serializers.PrimaryKeyRelatedField(
        queryset=models.ProviderSnapshot.objects.all(),
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        comparison_scope = attrs.get(
            'comparison_scope',
            models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        )
        provider_snapshot = attrs.get('provider_snapshot')
        if comparison_scope == models.ReconciliationComparisonScope.PROVIDER_IMPORTED and provider_snapshot is None:
            raise serializers.ValidationError(
                {'provider_snapshot': 'Provider snapshot is required for provider-imported ROA reconciliation.'}
            )
        return attrs


class ProviderSnapshotCompareActionSerializer(serializers.Serializer):
    base_snapshot = serializers.PrimaryKeyRelatedField(
        queryset=models.ProviderSnapshot.objects.all(),
        required=False,
        allow_null=True,
    )


class BulkIntentRunApproveActionSerializer(serializers.Serializer):
    approved_by = serializers.CharField(required=False, allow_blank=True, default='')


class BulkIntentRunApproveSecondaryActionSerializer(serializers.Serializer):
    approved_by = serializers.CharField(required=False, allow_blank=True, default='')


class DelegatedPublicationWorkflowApproveActionSerializer(serializers.Serializer):
    approved_by = serializers.CharField(required=False, allow_blank=True, default='')


__all__ = tuple(spec.api.serializer_name for spec in API_OBJECT_SPECS)
