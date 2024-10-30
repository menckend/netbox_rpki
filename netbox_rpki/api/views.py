from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework.routers import APIRootView

from netbox_rpki.api.serializers import (
    RpkiOrganizationSerializer, RpkiCertificateSerializer, RpkiRoaSerializer, RpkiRoaPreficesSerializer
)

from netbox_rpki import filtersets, models


class RootView(APIRootView):
    def get_view_name(self):
        return 'rpki'


class RpkiOrganizationViewSet(NetBoxModelViewSet):
    queryset = models.RpkiOrganization.objects.all()
    serializer_class = RpkiOrganizationSerializer
    filterset_class = filtersets.RpkiOrganizationFilterSet


class RpkiCertificateViewSet(NetBoxModelViewSet):
    queryset = models.RpkiCertificate.objects.all()
    serializer_class = RpkiCertificateSerializer
    filterset_class = filtersets.RpkiCertificateFilterSet


class RpkiRoaViewSet(NetBoxModelViewSet):
    queryset = models.RpkiRoa.objects.all()
    serializer_class = RpkiRoaSerializer
    filterset_class = filtersets.RpkiRoaFilterSet

class RpkiRoaPreficesViewSet(NetBoxModelViewSet):
    queryset = models.RpkiRoaPrefices.objects.all()
    serializer_class = RpkiRoaPreficesSerializer
    filterset_class = filtersets.RpkiRoaPreficesFilterSet
