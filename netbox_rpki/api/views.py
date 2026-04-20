from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.routers import APIRootView
from django.utils import timezone

from netbox.api.authentication import TokenWritePermission
from netbox.api.viewsets import NetBoxModelViewSet

from netbox_rpki import models as rpki_models
from netbox_rpki import filtersets as filterset_module
from netbox_rpki.api.serializers import (
    ASPAReconciliationRunActionSerializer,
    ASPAChangePlanApproveActionSerializer,
    ASPAChangePlanApproveSecondaryActionSerializer,
    BulkIntentRunActionSerializer,
    BulkIntentRunApproveActionSerializer,
    BulkIntentRunApproveSecondaryActionSerializer,
    DelegatedPublicationWorkflowApproveActionSerializer,
    ProviderSnapshotCompareActionSerializer,
    ROAChangePlanApproveSecondaryActionSerializer,
    RollbackBundleApplyActionSerializer,
    RollbackBundleApproveActionSerializer,
    RoutingIntentProfileRunActionSerializer,
    RoutingIntentTemplateBindingRunActionSerializer,
    ROAChangePlanAcknowledgeActionSerializer,
    ROAChangePlanApproveActionSerializer,
    ROALintFindingSuppressActionSerializer,
    ROALintSuppressionLiftActionSerializer,
    SERIALIZER_CLASS_MAP,
)
from netbox_rpki.jobs import (
    RunAspaReconciliationJob,
    RunBulkRoutingIntentJob,
    RunRoutingIntentProfileJob,
    SyncProviderAccountJob,
)
from netbox_rpki.object_registry import API_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec
from netbox_rpki.services.lifecycle_reporting import (
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY,
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY,
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE,
    build_lifecycle_export_response,
    build_provider_lifecycle_health_summary,
    build_provider_lifecycle_timeline,
    build_provider_publication_diff_timeline,
)
from netbox_rpki.services.provider_sync_contract import build_provider_account_summary
from netbox_rpki.services.provider_credential_validation import validate_provider_account_credentials
from netbox_rpki.services.provider_sync_diff import (
    build_latest_provider_snapshot_diff,
    build_provider_snapshot_diff,
)
from netbox_rpki.services import (
    ProviderWriteError,
    acknowledge_roa_lint_findings,
    apply_aspa_rollback_bundle,
    apply_aspa_change_plan_provider_write,
    apply_roa_rollback_bundle,
    apply_roa_change_plan_provider_write,
    approve_delegated_publication_workflow,
    approve_bulk_intent_run,
    secondary_approve_bulk_intent_run,
    approve_rollback_bundle,
    approve_aspa_change_plan,
    approve_aspa_change_plan_secondary,
    approve_roa_change_plan,
    approve_roa_change_plan_secondary,
    build_roa_change_plan_lint_posture,
    build_roa_change_plan_simulation_posture,
    create_aspa_change_plan,
    create_roa_change_plan,
    preview_routing_intent_template_binding,
    preview_aspa_change_plan_provider_write,
    preview_roa_change_plan_provider_write,
    build_cross_validator_comparison,
    build_snapshot_storage_impact,
    build_telemetry_run_history_summary,
    build_validator_run_history_summary,
    lift_roa_lint_suppression,
    run_routing_intent_template_binding_pipeline,
    simulate_roa_change_plan,
    suppress_roa_lint_finding,
)


class RootView(APIRootView):
    def get_view_name(self):
        return "rpki"


def build_viewset_class(spec: ObjectSpec) -> type[NetBoxModelViewSet]:
    namespace = {
        "__module__": __name__,
        "queryset": spec.model.objects.all(),
        "serializer_class": SERIALIZER_CLASS_MAP[spec.registry_key],
        "filterset_class": getattr(filterset_module, spec.filterset.class_name),
    }
    if spec.api.read_only:
        namespace["http_method_names"] = ["get", "head", "options"]

    return type(
        spec.api.viewset_name,
        (NetBoxModelViewSet,),
        namespace,
    )


VIEWSET_CLASS_MAP = {}
for object_spec in API_OBJECT_SPECS:
    viewset_class = build_viewset_class(object_spec)
    VIEWSET_CLASS_MAP[object_spec.registry_key] = viewset_class
    globals()[object_spec.api.viewset_name] = viewset_class


def _serialize_binding_preview_payload(request, binding, preview):
    payload = dict(SERIALIZER_CLASS_MAP['routingintenttemplatebinding'](binding, context={'request': request}).data)
    payload['compiled_policy'] = {
        'input_fingerprint': preview.compiled_policy.input_fingerprint,
        'warning_count': len(preview.warnings),
        'warnings': list(preview.warnings),
        'binding_count': len(preview.compiled_policy.template_bindings),
        'bindings': [
            {
                'binding_id': compiled.binding.pk,
                'binding_name': compiled.binding.name,
                'template_id': compiled.binding.template_id,
                'template_name': compiled.binding.template.name,
                'template_version': compiled.binding.template.template_version,
                'template_fingerprint': compiled.template_fingerprint,
                'binding_fingerprint': compiled.binding_fingerprint,
                'scoped_prefix_count': len(compiled.prefix_ids),
                'scoped_asn_count': len(compiled.selected_asns),
                'active_rule_count': len(compiled.rules),
            }
            for compiled in preview.compiled_policy.template_bindings
        ],
    }
    payload['preview_result_count'] = len(preview.results)
    payload['preview_results'] = [
        {
            'prefix_id': result.prefix.pk,
            'prefix_cidr_text': result.prefix_cidr_text,
            'origin_asn_id': getattr(result.origin_asn, 'pk', None),
            'origin_asn_value': result.origin_asn_value,
            'max_length': result.max_length,
            'derived_state': result.derived_state,
            'exposure_state': result.exposure_state,
            'source_rule_id': getattr(result.source_rule, 'pk', None),
            'applied_override_id': getattr(result.applied_override, 'pk', None),
            'explanation': result.explanation,
        }
        for result in preview.results
    ]
    return payload


class RoutingIntentProfileViewSet(VIEWSET_CLASS_MAP['routingintentprofile']):
    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) == 'run' and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')

        return queryset

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def run(self, request, pk=None):
        profile = self.get_object()

        if not request.user.has_perm('netbox_rpki.change_routingintentprofile', profile):
            raise PermissionDenied('This user does not have permission to run this routing intent profile.')

        input_serializer = RoutingIntentProfileRunActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        comparison_scope = input_serializer.validated_data['comparison_scope']
        provider_snapshot = input_serializer.validated_data.get('provider_snapshot')
        provider_snapshot_pk = getattr(provider_snapshot, 'pk', provider_snapshot)
        if provider_snapshot is not None and provider_snapshot.organization_id != profile.organization_id:
            raise ValidationError({'provider_snapshot': 'Provider snapshot must belong to the selected organization.'})
        job, created = RunRoutingIntentProfileJob.enqueue_for_profile(
            profile,
            user=request.user,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot,
        )
        serializer = SERIALIZER_CLASS_MAP['routingintentprofile'](profile, context={'request': request})
        payload = dict(serializer.data)
        payload['job'] = None
        if job is not None:
            payload['job'] = {
                'id': job.pk,
                'status': job.status,
                'url': job.get_absolute_url(),
                'existing': not created,
                'comparison_scope': comparison_scope,
                'provider_snapshot': provider_snapshot_pk,
            }
        payload['reconciliation_in_progress'] = not created
        return Response(payload)


class ValidatorInstanceViewSet(VIEWSET_CLASS_MAP['validatorinstance']):
    @action(detail=True, methods=['get'])
    def history_summary(self, request, pk=None):
        validator = self.get_object()
        return Response(build_validator_run_history_summary(validator))

    @action(detail=True, methods=['get'])
    def compare(self, request, pk=None):
        primary = self.get_object()
        other_id = request.query_params.get('other')
        if not other_id:
            raise ValidationError({'other': 'The "other" query parameter (validator instance ID) is required.'})
        try:
            secondary = rpki_models.ValidatorInstance.objects.restrict(request.user, 'view').get(pk=int(other_id))
        except (rpki_models.ValidatorInstance.DoesNotExist, ValueError, TypeError):
            raise ValidationError({'other': 'No accessible validator instance found with that ID.'})
        try:
            limit = min(int(request.query_params.get('limit_disagreements', 100)), 1000)
        except (ValueError, TypeError):
            limit = 100
        return Response(build_cross_validator_comparison(primary, secondary, limit_disagreements=limit))


class TelemetrySourceViewSet(VIEWSET_CLASS_MAP['telemetrysource']):
    @action(detail=True, methods=['get'])
    def history_summary(self, request, pk=None):
        source = self.get_object()
        return Response(build_telemetry_run_history_summary(source))


VIEWSET_CLASS_MAP['validatorinstance'] = ValidatorInstanceViewSet
VIEWSET_CLASS_MAP['telemetrysource'] = TelemetrySourceViewSet


class RoutingIntentExceptionViewSet(VIEWSET_CLASS_MAP['routingintentexception']):
    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) == 'approve' and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')

        return queryset

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def approve(self, request, pk=None):
        exception = self.get_object()

        if not request.user.has_perm('netbox_rpki.change_routingintentexception', exception):
            raise PermissionDenied('This user does not have permission to approve this routing intent exception.')

        exception.approved_at = timezone.now()
        exception.approved_by = getattr(request.user, 'username', '')
        exception.save(update_fields=('approved_at', 'approved_by'))
        return Response(SERIALIZER_CLASS_MAP['routingintentexception'](exception, context={'request': request}).data)


class DelegatedPublicationWorkflowViewSet(VIEWSET_CLASS_MAP['delegatedpublicationworkflow']):
    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) == 'approve' and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')

        return queryset

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def approve(self, request, pk=None):
        workflow = self.get_object()

        if not request.user.has_perm('netbox_rpki.change_delegatedpublicationworkflow', workflow):
            raise PermissionDenied('This user does not have permission to approve this delegated publication workflow.')

        input_serializer = DelegatedPublicationWorkflowApproveActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        approved_by = input_serializer.validated_data.get('approved_by') or getattr(request.user, 'username', '')

        try:
            workflow = approve_delegated_publication_workflow(workflow, approved_by=approved_by)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(
            SERIALIZER_CLASS_MAP['delegatedpublicationworkflow'](workflow, context={'request': request}).data
        )


class RoutingIntentTemplateBindingViewSet(VIEWSET_CLASS_MAP['routingintenttemplatebinding']):
    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) in {'preview', 'regenerate'} and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')

        return queryset

    def _require_change_permission(self, binding):
        if not self.request.user.has_perm('netbox_rpki.change_routingintenttemplatebinding', binding):
            raise PermissionDenied('This user does not have permission to execute actions on this template binding.')

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def preview(self, request, pk=None):
        binding = self.get_object()
        self._require_change_permission(binding)

        try:
            preview = preview_routing_intent_template_binding(binding)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(_serialize_binding_preview_payload(request, binding, preview))

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def regenerate(self, request, pk=None):
        binding = self.get_object()
        self._require_change_permission(binding)
        input_serializer = RoutingIntentTemplateBindingRunActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        provider_snapshot = input_serializer.validated_data.get('provider_snapshot')
        comparison_scope = input_serializer.validated_data['comparison_scope']

        if provider_snapshot is not None and provider_snapshot.organization_id != binding.intent_profile.organization_id:
            raise ValidationError({'provider_snapshot': 'Provider snapshot must belong to the selected organization.'})

        try:
            derivation_run, reconciliation_run = run_routing_intent_template_binding_pipeline(
                binding,
                comparison_scope=comparison_scope,
                provider_snapshot=provider_snapshot,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        binding.refresh_from_db()
        payload = dict(SERIALIZER_CLASS_MAP['routingintenttemplatebinding'](binding, context={'request': request}).data)
        payload['comparison_scope'] = comparison_scope
        payload['provider_snapshot'] = provider_snapshot.pk if provider_snapshot is not None else None
        payload['derivation_run'] = SERIALIZER_CLASS_MAP['intentderivationrun'](
            derivation_run,
            context={'request': request},
        ).data
        payload['reconciliation_run'] = SERIALIZER_CLASS_MAP['roareconciliationrun'](
            reconciliation_run,
            context={'request': request},
        ).data
        return Response(payload)


class OrganizationViewSet(VIEWSET_CLASS_MAP['organization']):
    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) in {'run_aspa_reconciliation', 'create_bulk_intent_run'} and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')

        return queryset

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission], url_path='run-aspa-reconciliation')
    def run_aspa_reconciliation(self, request, pk=None):
        organization = self.get_object()

        if not request.user.has_perm('netbox_rpki.change_organization', organization):
            raise PermissionDenied('You do not have permission to run ASPA reconciliation for this organization.')

        input_serializer = ASPAReconciliationRunActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        provider_snapshot = input_serializer.validated_data.get('provider_snapshot')
        comparison_scope = input_serializer.validated_data['comparison_scope']
        if (
            provider_snapshot is not None
            and provider_snapshot.organization_id != organization.pk
        ):
            raise ValidationError({'provider_snapshot': 'Provider snapshot must belong to the selected organization.'})

        job, created = RunAspaReconciliationJob.enqueue_for_organization(
            organization,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot,
            user=request.user,
        )
        payload = {
            'comparison_scope': comparison_scope,
            'provider_snapshot': provider_snapshot.pk if provider_snapshot is not None else None,
            'job': None,
            'reconciliation_in_progress': not created,
        }
        if job is not None:
            payload['job'] = {
                'id': job.pk,
                'status': job.status,
                'url': job.get_absolute_url(),
                'existing': not created,
            }
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission], url_path='create-bulk-intent-run')
    def create_bulk_intent_run(self, request, pk=None):
        organization = self.get_object()

        if not request.user.has_perm('netbox_rpki.change_organization', organization):
            raise PermissionDenied('You do not have permission to create bulk routing-intent runs for this organization.')

        input_serializer = BulkIntentRunActionSerializer(
            data=request.data,
            context={'organization': organization},
        )
        input_serializer.is_valid(raise_exception=True)
        job, created = RunBulkRoutingIntentJob.enqueue_for_organization(
            organization=organization,
            profiles=tuple(input_serializer.validated_data.get('profiles') or ()),
            bindings=tuple(input_serializer.validated_data.get('bindings') or ()),
            comparison_scope=input_serializer.validated_data['comparison_scope'],
            provider_snapshot=input_serializer.validated_data.get('provider_snapshot'),
            create_change_plans=input_serializer.validated_data.get('create_change_plans', False),
            run_name=input_serializer.validated_data.get('run_name') or None,
            user=request.user,
        )
        payload = {
            'comparison_scope': input_serializer.validated_data['comparison_scope'],
            'provider_snapshot': getattr(input_serializer.validated_data.get('provider_snapshot'), 'pk', None),
            'create_change_plans': input_serializer.validated_data.get('create_change_plans', False),
            'profile_pks': [profile.pk for profile in input_serializer.validated_data.get('profiles') or ()],
            'binding_pks': [binding.pk for binding in input_serializer.validated_data.get('bindings') or ()],
            'job': None,
            'bulk_run_in_progress': not created,
        }
        if job is not None:
            payload['job'] = {
                'id': job.pk,
                'status': job.status,
                'url': job.get_absolute_url(),
                'existing': not created,
            }
        return Response(payload)


class RpkiProviderAccountViewSet(VIEWSET_CLASS_MAP['rpkiprovideraccount']):
    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) in {'sync', 'test_connection'} and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')

        return queryset

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def sync(self, request, pk=None):
        provider_account = self.get_object()

        if not request.user.has_perm('netbox_rpki.change_rpkiprovideraccount', provider_account):
            raise PermissionDenied('This user does not have permission to sync this provider account.')

        if not provider_account.sync_enabled:
            raise ValidationError('This provider account is disabled for sync.')

        job, created = SyncProviderAccountJob.enqueue_for_provider_account(
            provider_account,
            user=request.user,
        )
        serializer = SERIALIZER_CLASS_MAP['rpkiprovideraccount'](provider_account, context={'request': request})
        payload = dict(serializer.data)
        payload['job'] = None
        if job is not None:
            payload['job'] = {
                'id': job.pk,
                'status': job.status,
                'url': job.get_absolute_url(),
                'existing': not created,
            }
        payload['sync_in_progress'] = not created
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission], url_path='test-connection')
    def test_connection(self, request, pk=None):
        provider_account = self.get_object()

        if not request.user.has_perm('netbox_rpki.change_rpkiprovideraccount', provider_account):
            raise PermissionDenied('This user does not have permission to test this provider account.')

        return Response(validate_provider_account_credentials(provider_account))

    def _get_export_format(self, request):
        export_format = request.query_params.get('export_format', 'json').lower()
        if export_format not in {'json', 'csv'}:
            raise ValidationError({'format': 'Supported export formats are json and csv.'})
        return export_format

    def _visible_timeline_ids(self, request, provider_account):
        visible_snapshot_ids = set(
            rpki_models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            rpki_models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        return visible_snapshot_ids, visible_diff_ids

    @action(detail=True, methods=['get'])
    def timeline(self, request, pk=None):
        provider_account = self.get_object()
        if not request.user.has_perm('netbox_rpki.view_rpkiprovideraccount', provider_account):
            raise PermissionDenied('This user does not have permission to view this provider account.')

        visible_snapshot_ids, visible_diff_ids = self._visible_timeline_ids(request, provider_account)
        return Response(build_provider_lifecycle_timeline(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        ))

    @action(detail=True, methods=['get'], url_path='publication-diff-summary')
    def publication_diff_summary(self, request, pk=None):
        provider_account = self.get_object()
        if not request.user.has_perm('netbox_rpki.view_rpkiprovideraccount', provider_account):
            raise PermissionDenied('This user does not have permission to view this provider account.')

        _, visible_diff_ids = self._visible_timeline_ids(request, provider_account)
        return Response(build_provider_publication_diff_timeline(
            provider_account,
            visible_diff_ids=visible_diff_ids,
        ))

    @action(detail=True, methods=['get'], url_path='export/lifecycle')
    def export_summary(self, request, pk=None):
        provider_account = self.get_object()
        if not request.user.has_perm('netbox_rpki.view_rpkiprovideraccount', provider_account):
            raise PermissionDenied('This user does not have permission to view this provider account.')

        export_format = self._get_export_format(request)
        visible_snapshot_ids, visible_diff_ids = self._visible_timeline_ids(request, provider_account)
        summary = build_provider_lifecycle_health_summary(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        try:
            return build_lifecycle_export_response(
                LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY,
                summary,
                export_format,
                provider_account=provider_account,
                filters={'provider_account_id': provider_account.pk},
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    @action(detail=True, methods=['get'], url_path='export/timeline')
    def export_timeline(self, request, pk=None):
        provider_account = self.get_object()
        if not request.user.has_perm('netbox_rpki.view_rpkiprovideraccount', provider_account):
            raise PermissionDenied('This user does not have permission to view this provider account.')

        export_format = self._get_export_format(request)
        visible_snapshot_ids, visible_diff_ids = self._visible_timeline_ids(request, provider_account)
        timeline = build_provider_lifecycle_timeline(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        try:
            return build_lifecycle_export_response(
                LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE,
                timeline,
                export_format,
                provider_account=provider_account,
                filters={'provider_account_id': provider_account.pk},
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    @action(detail=False, methods=['get'])
    def summary(self, request):
        provider_accounts = list(self.filter_queryset(self.get_queryset()))
        visible_snapshot_ids = set(
            rpki_models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_accounts)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            rpki_models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_accounts)
            .values_list('pk', flat=True)
        )
        return Response(build_provider_account_summary(
            provider_accounts,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        ))

    @action(detail=False, methods=['get'], url_path='summary/export')
    def summary_export(self, request):
        provider_accounts = list(self.filter_queryset(self.get_queryset()))
        visible_snapshot_ids = set(
            rpki_models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_accounts)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            rpki_models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_accounts)
            .values_list('pk', flat=True)
        )
        export_format = self._get_export_format(request)
        summary = build_provider_account_summary(
            provider_accounts,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        try:
            return build_lifecycle_export_response(
                LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY,
                summary,
                export_format,
                filters={'provider_account_ids': [provider_account.pk for provider_account in provider_accounts]},
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class ProviderSnapshotViewSet(VIEWSET_CLASS_MAP['providersnapshot']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) == 'compare' and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'view')

        return queryset

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def compare(self, request, pk=None):
        comparison_snapshot = self.get_object()

        if not request.user.has_perm('netbox_rpki.view_providersnapshot', comparison_snapshot):
            raise PermissionDenied('This user does not have permission to compare this provider snapshot.')

        input_serializer = ProviderSnapshotCompareActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        base_snapshot = input_serializer.validated_data.get('base_snapshot')

        try:
            if base_snapshot is None:
                snapshot_diff = build_latest_provider_snapshot_diff(comparison_snapshot)
                if snapshot_diff is None:
                    raise ValidationError(
                        {'base_snapshot': 'No earlier completed snapshot is available for comparison.'}
                    )
            else:
                snapshot_diff = build_provider_snapshot_diff(
                    base_snapshot=base_snapshot,
                    comparison_snapshot=comparison_snapshot,
                )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        serializer = SERIALIZER_CLASS_MAP['providersnapshotdiff'](snapshot_diff, context={'request': request})
        payload = dict(serializer.data)
        payload['item_count'] = snapshot_diff.items.count()
        return Response(payload)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        by_status: dict[str, int] = {}
        latest_completed_at = None
        with_diff_count = 0

        for snapshot in queryset:
            by_status[snapshot.status] = by_status.get(snapshot.status, 0) + 1
            if snapshot.completed_at is not None and (latest_completed_at is None or snapshot.completed_at > latest_completed_at):
                latest_completed_at = snapshot.completed_at
            if snapshot.diffs_as_comparison.exists():
                with_diff_count += 1

        return Response({
            'total_snapshots': queryset.count(),
            'completed_snapshots': by_status.get(rpki_models.ValidationRunStatus.COMPLETED, 0),
            'by_status': by_status,
            'with_diff_count': with_diff_count,
            'latest_completed_at': latest_completed_at,
        })


class ROAReconciliationRunViewSet(VIEWSET_CLASS_MAP['roareconciliationrun']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) == 'create_plan' and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'view')

        return queryset

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def create_plan(self, request, pk=None):
        reconciliation_run = self.get_object()

        if not request.user.has_perm('netbox_rpki.change_routingintentprofile', reconciliation_run.intent_profile):
            raise PermissionDenied('This user does not have permission to create a change plan from this reconciliation run.')

        plan = create_roa_change_plan(reconciliation_run)
        serializer = SERIALIZER_CLASS_MAP['roachangeplan'](plan, context={'request': request})
        payload = dict(serializer.data)
        payload['item_count'] = plan.items.count()
        return Response(payload)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        payload = {
            'total_runs': queryset.count(),
            'completed_runs': 0,
            'replacement_required_intent_total': 0,
            'replacement_required_published_total': 0,
            'lint_warning_total': 0,
            'lint_error_total': 0,
        }
        for run in queryset.prefetch_related('lint_runs'):
            if run.status == rpki_models.ValidationRunStatus.COMPLETED:
                payload['completed_runs'] += 1
            summary = dict(run.result_summary_json or {})
            payload['replacement_required_intent_total'] += summary.get('replacement_required_intent_count', 0)
            payload['replacement_required_published_total'] += summary.get('replacement_required_published_count', 0)
            lint_run = run.lint_runs.order_by('-started_at', '-created').first()
            if lint_run is not None:
                payload['lint_warning_total'] += lint_run.warning_count
                payload['lint_error_total'] += lint_run.error_count + lint_run.critical_count
        return Response(payload)


class ASPAReconciliationRunViewSet(VIEWSET_CLASS_MAP['aspareconciliationrun']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) == 'create_plan' and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')

        return queryset

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def create_plan(self, request, pk=None):
        reconciliation_run = self.get_object()

        if not request.user.has_perm('netbox_rpki.change_aspareconciliationrun', reconciliation_run):
            raise PermissionDenied('This user does not have permission to create an ASPA change plan from this reconciliation run.')

        plan = create_aspa_change_plan(reconciliation_run)
        serializer = SERIALIZER_CLASS_MAP['aspachangeplan'](plan, context={'request': request})
        payload = dict(serializer.data)
        payload['item_count'] = plan.items.count()
        return Response(payload)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        payload = {
            'total_runs': queryset.count(),
            'completed_runs': 0,
            'missing_count': 0,
            'missing_provider_count': 0,
            'extra_provider_count': 0,
            'orphaned_count': 0,
            'stale_count': 0,
        }
        for run in queryset:
            if run.status == rpki_models.ValidationRunStatus.COMPLETED:
                payload['completed_runs'] += 1
            summary = dict(run.result_summary_json or {})
            intent_types = dict(summary.get('intent_result_types') or {})
            published_types = dict(summary.get('published_result_types') or {})
            payload['missing_count'] += intent_types.get(rpki_models.ASPAIntentResultType.MISSING, 0)
            payload['missing_provider_count'] += intent_types.get(rpki_models.ASPAIntentResultType.MISSING_PROVIDER, 0)
            payload['extra_provider_count'] += published_types.get(rpki_models.PublishedASPAResultType.EXTRA_PROVIDER, 0)
            payload['orphaned_count'] += published_types.get(rpki_models.PublishedASPAResultType.ORPHANED, 0)
            payload['stale_count'] += (
                intent_types.get(rpki_models.ASPAIntentResultType.STALE, 0)
                + published_types.get(rpki_models.PublishedASPAResultType.STALE, 0)
            )
        return Response(payload)


class ROAChangePlanViewSet(VIEWSET_CLASS_MAP['roachangeplan']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'action', None) in {
            'preview',
            'acknowledge_findings',
            'approve',
            'approve_secondary',
            'apply',
            'simulate',
        } and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')
        return queryset

    def _require_change_permission(self, plan):
        if not self.request.user.has_perm('netbox_rpki.change_roachangeplan', plan):
            raise PermissionDenied('This user does not have permission to execute actions on this ROA change plan.')

    def _serialize_plan_payload(self, request, plan):
        serializer = SERIALIZER_CLASS_MAP['roachangeplan'](plan, context={'request': request})
        payload = dict(serializer.data)
        payload['item_count'] = plan.items.count()
        return payload

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def preview(self, request, pk=None):
        plan = self.get_object()
        self._require_change_permission(plan)
        try:
            execution, delta = preview_roa_change_plan_provider_write(
                plan,
                requested_by=getattr(request.user, 'username', ''),
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        payload = self._serialize_plan_payload(request, plan)
        payload['delta'] = delta
        payload['provider_request'] = execution.response_payload_json.get('provider_request', {})
        payload['preview_report'] = execution.response_payload_json.get('preview_report', {})
        payload['execution'] = SERIALIZER_CLASS_MAP['providerwriteexecution'](
            execution,
            context={'request': request},
        ).data
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def acknowledge_findings(self, request, pk=None):
        plan = self.get_object()
        self._require_change_permission(plan)
        input_serializer = ROAChangePlanAcknowledgeActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        try:
            acknowledgements = acknowledge_roa_lint_findings(
                plan,
                acknowledged_by=getattr(request.user, 'username', ''),
                ticket_reference=input_serializer.validated_data.get('ticket_reference', ''),
                change_reference=input_serializer.validated_data.get('change_reference', ''),
                acknowledged_finding_ids=input_serializer.validated_data.get('acknowledged_finding_ids', []),
                previously_acknowledged_finding_ids=input_serializer.validated_data.get(
                    'previously_acknowledged_finding_ids', []
                ),
                notes=input_serializer.validated_data.get('lint_acknowledgement_notes', ''),
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        plan.refresh_from_db()
        payload = self._serialize_plan_payload(request, plan)
        payload['acknowledgements'] = SERIALIZER_CLASS_MAP['roalintacknowledgement'](
            acknowledgements,
            many=True,
            context={'request': request},
        ).data
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def approve(self, request, pk=None):
        plan = self.get_object()
        self._require_change_permission(plan)
        input_serializer = ROAChangePlanApproveActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        try:
            plan = approve_roa_change_plan(
                plan,
                approved_by=getattr(request.user, 'username', ''),
                **input_serializer.validated_data,
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        payload = self._serialize_plan_payload(request, plan)
        latest_record = plan.approval_records.order_by('-recorded_at', '-created').first()
        if latest_record is not None:
            payload['approval_record'] = SERIALIZER_CLASS_MAP['approvalrecord'](
                latest_record,
                context={'request': request},
            ).data
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def approve_secondary(self, request, pk=None):
        plan = self.get_object()
        self._require_change_permission(plan)
        input_serializer = ROAChangePlanApproveSecondaryActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        try:
            plan = approve_roa_change_plan_secondary(
                plan,
                secondary_approved_by=getattr(request.user, 'username', ''),
                approval_notes=input_serializer.validated_data.get('approval_notes', ''),
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        payload = self._serialize_plan_payload(request, plan)
        latest_record = plan.approval_records.order_by('-recorded_at', '-created').first()
        if latest_record is not None:
            payload['approval_record'] = SERIALIZER_CLASS_MAP['approvalrecord'](
                latest_record,
                context={'request': request},
            ).data
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def apply(self, request, pk=None):
        plan = self.get_object()
        self._require_change_permission(plan)
        try:
            execution, delta = apply_roa_change_plan_provider_write(
                plan,
                requested_by=getattr(request.user, 'username', ''),
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        plan.refresh_from_db()
        payload = self._serialize_plan_payload(request, plan)
        payload['delta'] = delta
        payload['provider_request'] = execution.response_payload_json.get('provider_request', {})
        payload['preview_report'] = execution.response_payload_json.get('preview_report', {})
        payload['execution'] = SERIALIZER_CLASS_MAP['providerwriteexecution'](
            execution,
            context={'request': request},
        ).data
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def simulate(self, request, pk=None):
        plan = self.get_object()
        self._require_change_permission(plan)
        simulation_run = simulate_roa_change_plan(plan)
        payload = self._serialize_plan_payload(request, plan)
        payload['simulation_run'] = SERIALIZER_CLASS_MAP['roavalidationsimulationrun'](
            simulation_run,
            context={'request': request},
        ).data
        return Response(payload)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        by_status: dict[str, int] = {}
        provider_backed_count = 0
        replacement_count_total = 0
        simulated_plan_count = 0
        simulation_current_plan_count = 0
        simulation_missing_count = 0
        simulation_pending_count = 0
        simulation_stale_count = 0
        simulation_blocking_plan_count = 0
        simulation_ack_required_plan_count = 0
        simulation_informational_plan_count = 0
        simulation_partially_constrained_plan_count = 0
        simulation_status_counts: dict[str, int] = {}
        simulation_approval_impact_totals = {
            rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL: 0,
            rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED: 0,
            rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING: 0,
        }
        lint_warning_total = 0
        lint_error_total = 0
        lint_blocking_total = 0
        lint_ack_required_total = 0
        lint_acknowledged_total = 0
        lint_suppressed_total = 0
        lint_previously_acknowledged_total = 0
        lint_status_counts: dict[str, int] = {}
        for plan in queryset.prefetch_related('simulation_runs', 'lint_runs'):
            by_status[plan.status] = by_status.get(plan.status, 0) + 1
            if plan.is_provider_backed:
                provider_backed_count += 1
            replacement_count_total += (plan.summary_json or {}).get('replacement_count', 0)
            simulation_posture = build_roa_change_plan_simulation_posture(plan)
            if simulation_posture['has_simulation']:
                simulated_plan_count += 1
            if simulation_posture['is_current_for_plan']:
                simulation_current_plan_count += 1
            if simulation_posture['partially_constrained']:
                simulation_partially_constrained_plan_count += 1
            simulation_status = simulation_posture['status']
            simulation_status_counts[simulation_status] = simulation_status_counts.get(simulation_status, 0) + 1
            if simulation_status == 'missing':
                simulation_missing_count += 1
            elif simulation_status == 'pending':
                simulation_pending_count += 1
            elif simulation_status == 'stale':
                simulation_stale_count += 1
            elif simulation_status == rpki_models.ROAValidationSimulationApprovalImpact.BLOCKING:
                simulation_blocking_plan_count += 1
            elif simulation_status == rpki_models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED:
                simulation_ack_required_plan_count += 1
            elif simulation_status == rpki_models.ROAValidationSimulationApprovalImpact.INFORMATIONAL:
                simulation_informational_plan_count += 1
            for impact, count in (simulation_posture['approval_impact_counts'] or {}).items():
                simulation_approval_impact_totals[impact] = simulation_approval_impact_totals.get(impact, 0) + count
            lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
            if lint_run is not None:
                lint_warning_total += lint_run.warning_count
                lint_error_total += lint_run.error_count + lint_run.critical_count
            lint_posture = build_roa_change_plan_lint_posture(plan)
            lint_blocking_total += lint_posture['unresolved_blocking_finding_count']
            lint_ack_required_total += lint_posture['unresolved_acknowledgement_required_finding_count']
            lint_acknowledged_total += lint_posture['acknowledged_finding_count']
            lint_suppressed_total += lint_posture['suppressed_finding_count']
            lint_previously_acknowledged_total += lint_posture.get('previously_acknowledged_finding_count', 0)
            lint_status = lint_posture['status']
            lint_status_counts[lint_status] = lint_status_counts.get(lint_status, 0) + 1
        return Response({
            'total_plans': queryset.count(),
            'by_status': by_status,
            'provider_backed_count': provider_backed_count,
            'replacement_count_total': replacement_count_total,
            'simulated_plan_count': simulated_plan_count,
            'simulation_current_plan_count': simulation_current_plan_count,
            'simulation_missing_count': simulation_missing_count,
            'simulation_pending_count': simulation_pending_count,
            'simulation_stale_count': simulation_stale_count,
            'simulation_blocking_plan_count': simulation_blocking_plan_count,
            'simulation_acknowledgement_required_plan_count': simulation_ack_required_plan_count,
            'simulation_informational_plan_count': simulation_informational_plan_count,
            'simulation_partially_constrained_plan_count': simulation_partially_constrained_plan_count,
            'simulation_status_counts': simulation_status_counts,
            'simulation_approval_impact_totals': simulation_approval_impact_totals,
            'lint_warning_total': lint_warning_total,
            'lint_error_total': lint_error_total,
            'lint_blocking_total': lint_blocking_total,
            'lint_acknowledgement_required_total': lint_ack_required_total,
            'lint_acknowledged_total': lint_acknowledged_total,
            'lint_suppressed_total': lint_suppressed_total,
            'lint_previously_acknowledged_total': lint_previously_acknowledged_total,
            'lint_status_counts': lint_status_counts,
        })


class ROALintFindingViewSet(VIEWSET_CLASS_MAP['roalintfinding']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'action', None) == 'suppress' and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')
        return queryset

    def _require_change_permission(self, finding):
        if not finding.__class__.objects.restrict(self.request.user, 'change').filter(pk=finding.pk).exists():
            raise PermissionDenied('This user does not have permission to modify this ROA lint finding.')

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def suppress(self, request, pk=None):
        finding = self.get_object()
        self._require_change_permission(finding)
        input_serializer = ROALintFindingSuppressActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        suppression = suppress_roa_lint_finding(
            finding,
            scope_type=input_serializer.validated_data['scope_type'],
            reason=input_serializer.validated_data['reason'],
            created_by=getattr(request.user, 'username', ''),
            expires_at=input_serializer.validated_data.get('expires_at'),
            notes=input_serializer.validated_data.get('notes', ''),
        )
        return Response(
            SERIALIZER_CLASS_MAP['roalintsuppression'](suppression, context={'request': request}).data
        )


VIEWSET_CLASS_MAP['roalintfinding'] = ROALintFindingViewSet
globals()['ROALintFindingViewSet'] = ROALintFindingViewSet


class ROALintSuppressionViewSet(VIEWSET_CLASS_MAP['roalintsuppression']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'action', None) == 'lift' and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')
        return queryset

    def _require_change_permission(self, suppression):
        if not suppression.__class__.objects.restrict(self.request.user, 'change').filter(pk=suppression.pk).exists():
            raise PermissionDenied('This user does not have permission to modify this ROA lint suppression.')

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def lift(self, request, pk=None):
        suppression = self.get_object()
        self._require_change_permission(suppression)
        input_serializer = ROALintSuppressionLiftActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        suppression = lift_roa_lint_suppression(
            suppression,
            lifted_by=getattr(request.user, 'username', ''),
            lift_reason=input_serializer.validated_data.get('lift_reason', ''),
        )
        return Response(
            SERIALIZER_CLASS_MAP['roalintsuppression'](suppression, context={'request': request}).data
        )


VIEWSET_CLASS_MAP['roalintsuppression'] = ROALintSuppressionViewSet
globals()['ROALintSuppressionViewSet'] = ROALintSuppressionViewSet


class ASPAChangePlanViewSet(VIEWSET_CLASS_MAP['aspachangeplan']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'action', None) in {'preview', 'approve', 'approve_secondary', 'apply'} and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')
        return queryset

    def _require_change_permission(self, plan):
        if not self.request.user.has_perm('netbox_rpki.change_aspachangeplan', plan):
            raise PermissionDenied('This user does not have permission to execute actions on this ASPA change plan.')

    def _serialize_plan_payload(self, request, plan):
        serializer = SERIALIZER_CLASS_MAP['aspachangeplan'](plan, context={'request': request})
        payload = dict(serializer.data)
        payload['item_count'] = plan.items.count()
        return payload

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def preview(self, request, pk=None):
        plan = self.get_object()
        self._require_change_permission(plan)
        try:
            execution, delta = preview_aspa_change_plan_provider_write(
                plan,
                requested_by=getattr(request.user, 'username', ''),
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        payload = self._serialize_plan_payload(request, plan)
        payload['delta'] = delta
        payload['provider_request'] = execution.response_payload_json.get('provider_request', {})
        payload['preview_report'] = execution.response_payload_json.get('preview_report', {})
        payload['execution'] = SERIALIZER_CLASS_MAP['providerwriteexecution'](
            execution,
            context={'request': request},
        ).data
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def approve(self, request, pk=None):
        plan = self.get_object()
        self._require_change_permission(plan)
        input_serializer = ASPAChangePlanApproveActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        try:
            plan = approve_aspa_change_plan(
                plan,
                approved_by=getattr(request.user, 'username', ''),
                **input_serializer.validated_data,
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        payload = self._serialize_plan_payload(request, plan)
        latest_record = plan.approval_records.order_by('-recorded_at', '-created').first()
        if latest_record is not None:
            payload['approval_record'] = SERIALIZER_CLASS_MAP['approvalrecord'](
                latest_record,
                context={'request': request},
            ).data
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def approve_secondary(self, request, pk=None):
        plan = self.get_object()
        self._require_change_permission(plan)
        input_serializer = ASPAChangePlanApproveSecondaryActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        try:
            plan = approve_aspa_change_plan_secondary(
                plan,
                secondary_approved_by=getattr(request.user, 'username', ''),
                approval_notes=input_serializer.validated_data.get('approval_notes', ''),
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        payload = self._serialize_plan_payload(request, plan)
        latest_record = plan.approval_records.order_by('-recorded_at', '-created').first()
        if latest_record is not None:
            payload['approval_record'] = SERIALIZER_CLASS_MAP['approvalrecord'](
                latest_record,
                context={'request': request},
            ).data
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def apply(self, request, pk=None):
        plan = self.get_object()
        self._require_change_permission(plan)
        try:
            execution, delta = apply_aspa_change_plan_provider_write(
                plan,
                requested_by=getattr(request.user, 'username', ''),
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        plan.refresh_from_db()
        payload = self._serialize_plan_payload(request, plan)
        payload['delta'] = delta
        payload['execution'] = SERIALIZER_CLASS_MAP['providerwriteexecution'](
            execution,
            context={'request': request},
        ).data
        return Response(payload)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        by_status: dict[str, int] = {}
        provider_backed_count = 0
        replacement_count_total = 0
        provider_add_count_total = 0
        provider_remove_count_total = 0
        for plan in queryset:
            by_status[plan.status] = by_status.get(plan.status, 0) + 1
            if plan.is_provider_backed:
                provider_backed_count += 1
            summary = dict(plan.summary_json or {})
            replacement_count_total += summary.get('replacement_count', 0)
            provider_add_count_total += summary.get('provider_add_count', 0)
            provider_remove_count_total += summary.get('provider_remove_count', 0)
        return Response({
            'total_plans': queryset.count(),
            'by_status': by_status,
            'provider_backed_count': provider_backed_count,
            'replacement_count_total': replacement_count_total,
            'provider_add_count_total': provider_add_count_total,
            'provider_remove_count_total': provider_remove_count_total,
        })


class ROAChangePlanRollbackBundleViewSet(VIEWSET_CLASS_MAP['roachangeplanrollbackbundle']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'action', None) in {'approve', 'apply'} and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')
        return queryset

    def _require_change_permission(self, bundle):
        if not self.request.user.has_perm('netbox_rpki.change_roachangeplanrollbackbundle', bundle):
            raise PermissionDenied('This user does not have permission to execute actions on this ROA rollback bundle.')

    def _serialize_bundle_payload(self, request, bundle):
        serializer = SERIALIZER_CLASS_MAP['roachangeplanrollbackbundle'](bundle, context={'request': request})
        return dict(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def approve(self, request, pk=None):
        bundle = self.get_object()
        self._require_change_permission(bundle)
        input_serializer = RollbackBundleApproveActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        try:
            bundle = approve_rollback_bundle(
                bundle,
                approved_by=getattr(request.user, 'username', ''),
                **input_serializer.validated_data,
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(self._serialize_bundle_payload(request, bundle))

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def apply(self, request, pk=None):
        bundle = self.get_object()
        self._require_change_permission(bundle)
        input_serializer = RollbackBundleApplyActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        requested_by = input_serializer.validated_data.get('requested_by') or getattr(request.user, 'username', '')
        try:
            bundle = apply_roa_rollback_bundle(bundle, requested_by=requested_by)
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(self._serialize_bundle_payload(request, bundle))


class ASPAChangePlanRollbackBundleViewSet(VIEWSET_CLASS_MAP['aspachangeplanrollbackbundle']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'action', None) in {'approve', 'apply'} and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')
        return queryset

    def _require_change_permission(self, bundle):
        if not self.request.user.has_perm('netbox_rpki.change_aspachangeplanrollbackbundle', bundle):
            raise PermissionDenied('This user does not have permission to execute actions on this ASPA rollback bundle.')

    def _serialize_bundle_payload(self, request, bundle):
        serializer = SERIALIZER_CLASS_MAP['aspachangeplanrollbackbundle'](bundle, context={'request': request})
        return dict(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def approve(self, request, pk=None):
        bundle = self.get_object()
        self._require_change_permission(bundle)
        input_serializer = RollbackBundleApproveActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        try:
            bundle = approve_rollback_bundle(
                bundle,
                approved_by=getattr(request.user, 'username', ''),
                **input_serializer.validated_data,
            )
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(self._serialize_bundle_payload(request, bundle))

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def apply(self, request, pk=None):
        bundle = self.get_object()
        self._require_change_permission(bundle)
        input_serializer = RollbackBundleApplyActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        requested_by = input_serializer.validated_data.get('requested_by') or getattr(request.user, 'username', '')
        try:
            bundle = apply_aspa_rollback_bundle(bundle, requested_by=requested_by)
        except ProviderWriteError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(self._serialize_bundle_payload(request, bundle))


class BulkIntentRunViewSet(VIEWSET_CLASS_MAP['bulkintentrun']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'action', None) in {'approve', 'approve_secondary'} and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'view')
        return queryset

    def _require_change_permission(self, bulk_run):
        if not self.request.user.has_perm('netbox_rpki.change_bulkintentrun', bulk_run):
            raise PermissionDenied('This user does not have permission to approve this bulk intent run.')

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def approve(self, request, pk=None):
        bulk_run = self.get_object()
        self._require_change_permission(bulk_run)
        input_serializer = BulkIntentRunApproveActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        approved_by = (
            input_serializer.validated_data.get('approved_by')
            or getattr(request.user, 'username', '')
        )
        try:
            bulk_run = approve_bulk_intent_run(bulk_run, approved_by=approved_by)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc

        serializer = SERIALIZER_CLASS_MAP['bulkintentrun'](bulk_run, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission], url_path='approve-secondary')
    def approve_secondary(self, request, pk=None):
        bulk_run = self.get_object()
        self._require_change_permission(bulk_run)
        input_serializer = BulkIntentRunApproveSecondaryActionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        approved_by = (
            input_serializer.validated_data.get('approved_by')
            or getattr(request.user, 'username', '')
        )
        try:
            bulk_run = secondary_approve_bulk_intent_run(bulk_run, approved_by=approved_by)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc

        serializer = SERIALIZER_CLASS_MAP['bulkintentrun'](bulk_run, context={'request': request})
        return Response(serializer.data)


VIEWSET_CLASS_MAP['routingintentprofile'] = RoutingIntentProfileViewSet
globals()['RoutingIntentProfileViewSet'] = RoutingIntentProfileViewSet
VIEWSET_CLASS_MAP['bulkintentrun'] = BulkIntentRunViewSet
globals()['BulkIntentRunViewSet'] = BulkIntentRunViewSet
VIEWSET_CLASS_MAP['routingintentexception'] = RoutingIntentExceptionViewSet
globals()['RoutingIntentExceptionViewSet'] = RoutingIntentExceptionViewSet
VIEWSET_CLASS_MAP['delegatedpublicationworkflow'] = DelegatedPublicationWorkflowViewSet
globals()['DelegatedPublicationWorkflowViewSet'] = DelegatedPublicationWorkflowViewSet
VIEWSET_CLASS_MAP['routingintenttemplatebinding'] = RoutingIntentTemplateBindingViewSet
globals()['RoutingIntentTemplateBindingViewSet'] = RoutingIntentTemplateBindingViewSet
VIEWSET_CLASS_MAP['organization'] = OrganizationViewSet
globals()['OrganizationViewSet'] = OrganizationViewSet
VIEWSET_CLASS_MAP['rpkiprovideraccount'] = RpkiProviderAccountViewSet
globals()['RpkiProviderAccountViewSet'] = RpkiProviderAccountViewSet
VIEWSET_CLASS_MAP['providersnapshot'] = ProviderSnapshotViewSet
globals()['ProviderSnapshotViewSet'] = ProviderSnapshotViewSet
VIEWSET_CLASS_MAP['roareconciliationrun'] = ROAReconciliationRunViewSet
globals()['ROAReconciliationRunViewSet'] = ROAReconciliationRunViewSet
VIEWSET_CLASS_MAP['aspareconciliationrun'] = ASPAReconciliationRunViewSet
globals()['ASPAReconciliationRunViewSet'] = ASPAReconciliationRunViewSet
VIEWSET_CLASS_MAP['roachangeplan'] = ROAChangePlanViewSet
globals()['ROAChangePlanViewSet'] = ROAChangePlanViewSet
VIEWSET_CLASS_MAP['aspachangeplan'] = ASPAChangePlanViewSet
globals()['ASPAChangePlanViewSet'] = ASPAChangePlanViewSet
VIEWSET_CLASS_MAP['roachangeplanrollbackbundle'] = ROAChangePlanRollbackBundleViewSet
globals()['ROAChangePlanRollbackBundleViewSet'] = ROAChangePlanRollbackBundleViewSet
VIEWSET_CLASS_MAP['aspachangeplanrollbackbundle'] = ASPAChangePlanRollbackBundleViewSet
globals()['ASPAChangePlanRollbackBundleViewSet'] = ASPAChangePlanRollbackBundleViewSet


class SnapshotRetentionPolicyViewSet(VIEWSET_CLASS_MAP['snapshotretentionpolicy']):
    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'action', None) == 'run_purge' and self.request.user.is_authenticated:
            return self.queryset.model.objects.restrict(self.request.user, 'change')
        return queryset

    @action(detail=True, methods=['get'])
    def storage_impact(self, request, pk=None):
        policy = self.get_object()
        return Response(build_snapshot_storage_impact(policy))

    @action(detail=True, methods=['post'], permission_classes=[TokenWritePermission])
    def run_purge(self, request, pk=None):
        policy = self.get_object()
        dry_run = bool(request.data.get('dry_run', True))
        from netbox_rpki.jobs import PurgeSnapshotRunJob
        job, created = PurgeSnapshotRunJob.enqueue_for_policy(policy, dry_run=dry_run, user=request.user)
        job_data = None
        if job is not None:
            job_data = {'id': job.pk, 'status': job.status}
        return Response({'enqueued': created if job is not None else False, 'job': job_data, 'dry_run': dry_run}, status=202)


VIEWSET_CLASS_MAP['snapshotretentionpolicy'] = SnapshotRetentionPolicyViewSet
globals()['SnapshotRetentionPolicyViewSet'] = SnapshotRetentionPolicyViewSet


__all__ = ("RootView",) + tuple(spec.api.viewset_name for spec in API_OBJECT_SPECS)
