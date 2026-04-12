from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.routers import APIRootView

from netbox.api.authentication import TokenWritePermission
from netbox.api.viewsets import NetBoxModelViewSet

from netbox_rpki import models as rpki_models
from netbox_rpki import filtersets as filterset_module
from netbox_rpki.api.serializers import (
    ASPAReconciliationRunActionSerializer,
    ROAChangePlanApproveActionSerializer,
    SERIALIZER_CLASS_MAP,
)
from netbox_rpki.jobs import RunAspaReconciliationJob, RunRoutingIntentProfileJob, SyncProviderAccountJob
from netbox_rpki.object_registry import API_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec
from netbox_rpki.services import (
    ProviderWriteError,
    apply_roa_change_plan_provider_write,
    approve_roa_change_plan,
    create_roa_change_plan,
    preview_roa_change_plan_provider_write,
    simulate_roa_change_plan,
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

        comparison_scope = request.data.get('comparison_scope', 'local_roa_records')
        provider_snapshot_pk = request.data.get('provider_snapshot')
        job = RunRoutingIntentProfileJob.enqueue(
            instance=profile,
            user=request.user,
            profile_pk=profile.pk,
            comparison_scope=comparison_scope,
            provider_snapshot_pk=provider_snapshot_pk,
        )
        serializer = SERIALIZER_CLASS_MAP['routingintentprofile'](profile, context={'request': request})
        payload = dict(serializer.data)
        payload['job'] = {
            'id': job.pk,
            'status': job.status,
            'url': job.get_absolute_url(),
        }
        payload['job']['comparison_scope'] = comparison_scope
        payload['job']['provider_snapshot'] = provider_snapshot_pk
        return Response(payload)


class OrganizationViewSet(VIEWSET_CLASS_MAP['organization']):
    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) == 'run_aspa_reconciliation' and self.request.user.is_authenticated:
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


class RpkiProviderAccountViewSet(VIEWSET_CLASS_MAP['rpkiprovideraccount']):
    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) == 'sync' and self.request.user.is_authenticated:
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


class ROAChangePlanViewSet(VIEWSET_CLASS_MAP['roachangeplan']):
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self, 'action', None) in {'preview', 'approve', 'apply', 'simulate'} and self.request.user.is_authenticated:
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
        payload['execution'] = SERIALIZER_CLASS_MAP['providerwriteexecution'](
            execution,
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
        lint_warning_total = 0
        lint_error_total = 0
        for plan in queryset.prefetch_related('simulation_runs', 'lint_runs'):
            by_status[plan.status] = by_status.get(plan.status, 0) + 1
            if plan.is_provider_backed:
                provider_backed_count += 1
            replacement_count_total += (plan.summary_json or {}).get('replacement_count', 0)
            simulation_run = plan.simulation_runs.order_by('-started_at', '-created').first()
            if simulation_run is not None:
                simulated_plan_count += 1
            lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
            if lint_run is not None:
                lint_warning_total += lint_run.warning_count
                lint_error_total += lint_run.error_count + lint_run.critical_count
        return Response({
            'total_plans': queryset.count(),
            'by_status': by_status,
            'provider_backed_count': provider_backed_count,
            'replacement_count_total': replacement_count_total,
            'simulated_plan_count': simulated_plan_count,
            'lint_warning_total': lint_warning_total,
            'lint_error_total': lint_error_total,
        })


VIEWSET_CLASS_MAP['routingintentprofile'] = RoutingIntentProfileViewSet
globals()['RoutingIntentProfileViewSet'] = RoutingIntentProfileViewSet
VIEWSET_CLASS_MAP['organization'] = OrganizationViewSet
globals()['OrganizationViewSet'] = OrganizationViewSet
VIEWSET_CLASS_MAP['rpkiprovideraccount'] = RpkiProviderAccountViewSet
globals()['RpkiProviderAccountViewSet'] = RpkiProviderAccountViewSet
VIEWSET_CLASS_MAP['roareconciliationrun'] = ROAReconciliationRunViewSet
globals()['ROAReconciliationRunViewSet'] = ROAReconciliationRunViewSet
VIEWSET_CLASS_MAP['roachangeplan'] = ROAChangePlanViewSet
globals()['ROAChangePlanViewSet'] = ROAChangePlanViewSet


__all__ = ("RootView",) + tuple(spec.api.viewset_name for spec in API_OBJECT_SPECS)
