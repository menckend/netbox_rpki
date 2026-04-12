from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import APIRootView

from netbox.api.authentication import TokenWritePermission
from netbox.api.viewsets import NetBoxModelViewSet

from netbox_rpki import filtersets as filterset_module
from netbox_rpki.api.serializers import SERIALIZER_CLASS_MAP
from netbox_rpki.jobs import RunRoutingIntentProfileJob, SyncProviderAccountJob
from netbox_rpki.object_registry import API_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec
from netbox_rpki.services import create_roa_change_plan


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

        job = SyncProviderAccountJob.enqueue(
            instance=provider_account,
            user=request.user,
            provider_account_pk=provider_account.pk,
        )
        serializer = SERIALIZER_CLASS_MAP['rpkiprovideraccount'](provider_account, context={'request': request})
        payload = dict(serializer.data)
        payload['job'] = {
            'id': job.pk,
            'status': job.status,
            'url': job.get_absolute_url(),
        }
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


VIEWSET_CLASS_MAP['routingintentprofile'] = RoutingIntentProfileViewSet
globals()['RoutingIntentProfileViewSet'] = RoutingIntentProfileViewSet
VIEWSET_CLASS_MAP['rpkiprovideraccount'] = RpkiProviderAccountViewSet
globals()['RpkiProviderAccountViewSet'] = RpkiProviderAccountViewSet
VIEWSET_CLASS_MAP['roareconciliationrun'] = ROAReconciliationRunViewSet
globals()['ROAReconciliationRunViewSet'] = ROAReconciliationRunViewSet


__all__ = ("RootView",) + tuple(spec.api.viewset_name for spec in API_OBJECT_SPECS)
