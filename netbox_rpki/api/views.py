from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework.routers import APIRootView

from netbox_rpki.api.serializers import (
    organizationSerializer, certificateSerializer, roaSerializer, roapreficesSerializer
)

from netbox_rpki import filtersets, models


class RootView(APIRootView):
    def get_view_name(self):
        return 'rpki'


class organizationViewSet(NetBoxModelViewSet):
    queryset = models.organization.objects.all()
    serializer_class = organizationSerializer
    filterset_class = filtersets.organizationFilterSet


class certificateViewSet(NetBoxModelViewSet):
    queryset = models.certificate.objects.all()
    serializer_class = certificateSerializer
    filterset_class = filtersets.certificateFilterSet


class roaViewSet(NetBoxModelViewSet):
    queryset = models.roa.objects.all()
    serializer_class = roaSerializer
    filterset_class = filtersets.roaFilterSet

class roapreficesViewSet(NetBoxModelViewSet):
    queryset = models.roaPprefices.objects.all()
    serializer_class = roapreficesSerializer
    filterset_class = filtersets.roapreficesFilterSet
