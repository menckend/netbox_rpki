from django.core.exceptions import ObjectDoesNotExist
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework.serializers import HyperlinkedIdentityField
from rest_framework import serializers

from netbox_rpki import models
from netbox_rpki.object_registry import API_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec
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


class RpkiProviderAccountSerializer(SERIALIZER_CLASS_MAP['rpkiprovideraccount']):
    supports_roa_write = serializers.ReadOnlyField()
    roa_write_mode = serializers.ReadOnlyField()
    roa_write_capability = serializers.ReadOnlyField()
    sync_health = serializers.ReadOnlyField()
    sync_health_display = serializers.ReadOnlyField()
    last_sync_rollup = serializers.SerializerMethodField()
    next_sync_due_at = serializers.DateTimeField(read_only=True)

    class Meta(SERIALIZER_CLASS_MAP['rpkiprovideraccount'].Meta):
        fields = SERIALIZER_CLASS_MAP['rpkiprovideraccount'].Meta.fields + (
            'supports_roa_write',
            'roa_write_mode',
            'roa_write_capability',
            'sync_health',
            'sync_health_display',
            'last_sync_rollup',
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


SERIALIZER_CLASS_MAP['rpkiprovideraccount'] = RpkiProviderAccountSerializer
globals()['RpkiProviderAccountSerializer'] = RpkiProviderAccountSerializer


class ROAReconciliationRunSerializer(SERIALIZER_CLASS_MAP['roareconciliationrun']):
    latest_lint_run = serializers.SerializerMethodField()
    latest_lint_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['roareconciliationrun'].Meta):
        fields = SERIALIZER_CLASS_MAP['roareconciliationrun'].Meta.fields + (
            'latest_lint_run',
            'latest_lint_summary',
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


SERIALIZER_CLASS_MAP['roareconciliationrun'] = ROAReconciliationRunSerializer
globals()['ROAReconciliationRunSerializer'] = ROAReconciliationRunSerializer


class ROAChangePlanSerializer(SERIALIZER_CLASS_MAP['roachangeplan']):
    latest_lint_run = serializers.SerializerMethodField()
    latest_lint_summary = serializers.SerializerMethodField()
    latest_simulation_run = serializers.SerializerMethodField()
    latest_simulation_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['roachangeplan'].Meta):
        fields = SERIALIZER_CLASS_MAP['roachangeplan'].Meta.fields + (
            'latest_lint_run',
            'latest_lint_summary',
            'latest_simulation_run',
            'latest_simulation_summary',
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
        return simulation_run.summary_json


SERIALIZER_CLASS_MAP['roachangeplan'] = ROAChangePlanSerializer
globals()['ROAChangePlanSerializer'] = ROAChangePlanSerializer


class ProviderSnapshotSerializer(SERIALIZER_CLASS_MAP['providersnapshot']):
    latest_diff = serializers.SerializerMethodField()
    latest_diff_summary = serializers.SerializerMethodField()
    family_rollups = serializers.SerializerMethodField()
    family_status_counts = serializers.SerializerMethodField()
    imported_publication_points = serializers.SerializerMethodField()
    imported_signed_objects = serializers.SerializerMethodField()
    imported_certificate_observations = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['providersnapshot'].Meta):
        fields = SERIALIZER_CLASS_MAP['providersnapshot'].Meta.fields + (
            'latest_diff',
            'latest_diff_summary',
            'family_rollups',
            'family_status_counts',
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


SERIALIZER_CLASS_MAP['providersnapshot'] = ProviderSnapshotSerializer
globals()['ProviderSnapshotSerializer'] = ProviderSnapshotSerializer


class ProviderSnapshotDiffSerializer(SERIALIZER_CLASS_MAP['providersnapshotdiff']):
    family_rollups = serializers.SerializerMethodField()
    family_status_counts = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['providersnapshotdiff'].Meta):
        fields = SERIALIZER_CLASS_MAP['providersnapshotdiff'].Meta.fields + (
            'family_rollups',
            'family_status_counts',
        )

    def get_family_rollups(self, obj):
        return build_provider_snapshot_diff_rollup(obj)['family_rollups']

    def get_family_status_counts(self, obj):
        return build_provider_snapshot_diff_rollup(obj)['family_status_counts']


SERIALIZER_CLASS_MAP['providersnapshotdiff'] = ProviderSnapshotDiffSerializer
globals()['ProviderSnapshotDiffSerializer'] = ProviderSnapshotDiffSerializer


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

    class Meta(SERIALIZER_CLASS_MAP['importedsignedobject'].Meta):
        fields = SERIALIZER_CLASS_MAP['importedsignedobject'].Meta.fields + (
            'publication_linkage_status',
            'authored_linkage_status',
            'evidence_summary',
        )

    def get_publication_linkage_status(self, obj):
        return get_signed_object_publication_linkage_status(obj)

    def get_authored_linkage_status(self, obj):
        return get_signed_object_authored_linkage_status(obj)

    def get_evidence_summary(self, obj):
        return get_signed_object_evidence_summary(obj)


SERIALIZER_CLASS_MAP['importedsignedobject'] = ImportedSignedObjectSerializer
globals()['ImportedSignedObjectSerializer'] = ImportedSignedObjectSerializer


class ImportedCertificateObservationSerializer(SERIALIZER_CLASS_MAP['importedcertificateobservation']):
    source_count = serializers.SerializerMethodField()
    source_labels = serializers.SerializerMethodField()
    is_ambiguous = serializers.SerializerMethodField()
    publication_linkage_status = serializers.SerializerMethodField()
    signed_object_linkage_status = serializers.SerializerMethodField()
    evidence_summary = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['importedcertificateobservation'].Meta):
        fields = SERIALIZER_CLASS_MAP['importedcertificateobservation'].Meta.fields + (
            'source_count',
            'source_labels',
            'is_ambiguous',
            'publication_linkage_status',
            'signed_object_linkage_status',
            'evidence_summary',
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


SERIALIZER_CLASS_MAP['importedcertificateobservation'] = ImportedCertificateObservationSerializer
globals()['ImportedCertificateObservationSerializer'] = ImportedCertificateObservationSerializer


class SignedObjectSerializer(SERIALIZER_CLASS_MAP['signedobject']):
    legacy_roa = serializers.SerializerMethodField()
    crl_extension = serializers.SerializerMethodField()
    manifest_extension = serializers.SerializerMethodField()
    trust_anchor_key_extension = serializers.SerializerMethodField()
    aspa_extension = serializers.SerializerMethodField()
    rsc_extension = serializers.SerializerMethodField()
    imported_signed_object_observations = serializers.SerializerMethodField()
    validation_results = serializers.SerializerMethodField()

    class Meta(SERIALIZER_CLASS_MAP['signedobject'].Meta):
        fields = SERIALIZER_CLASS_MAP['signedobject'].Meta.fields + (
            'legacy_roa',
            'crl_extension',
            'manifest_extension',
            'trust_anchor_key_extension',
            'aspa_extension',
            'rsc_extension',
            'imported_signed_object_observations',
            'validation_results',
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

    def get_legacy_roa(self, obj):
        return self._serialize_related_object(obj, 'legacy_roa', 'roa')

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


SERIALIZER_CLASS_MAP['signedobject'] = SignedObjectSerializer
globals()['SignedObjectSerializer'] = SignedObjectSerializer


class ROAChangePlanApproveActionSerializer(serializers.Serializer):
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


class ProviderSnapshotCompareActionSerializer(serializers.Serializer):
    base_snapshot = serializers.PrimaryKeyRelatedField(
        queryset=models.ProviderSnapshot.objects.all(),
        required=False,
        allow_null=True,
    )


__all__ = tuple(spec.api.serializer_name for spec in API_OBJECT_SPECS)
