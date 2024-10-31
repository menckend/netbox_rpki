from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework.routers import APIRootView

import netbox_rpki
from netbox_rpki.api.serializers import (
    OrganizationSerializer, CertificateSerializer, RoaSerializer, RoaPrefixSerializer
)

from netbox_rpki import filtersets, models


class RootView(APIRootView):
    def get_view_name(self):
        return 'rpki'


class OrganizationViewSet(NetBoxModelViewSet):
    queryset = netbox_rpki.models.Organization.objects.all()
    serializer_class = netbox_rpki.api.serializers.OrganizationSerializer
    filterset_class = filtersets.OrganizationFilterSet


class CertificateViewSet(NetBoxModelViewSet):
    queryset = netbox_rpki.models.Certificate.objects.all()
    serializer_class = netbox_rpki.api.serializers.CertificateSerializer
    filterset_class = netbox_rpki.filtersets.CertificateFilterSet


class RoaViewSet(NetBoxModelViewSet):
    queryset = netbox_rpki.models.Roa.objects.all()
    serializer_class = netbox_rpki.api.serializers.RoaSerializer
    filterset_class = netbox_rpki.filtersets.RoaFilterSet

class RoaPrefixViewSet(NetBoxModelViewSet):
    queryset = netbox_rpki.models.RoaPrefix.objects.all()
    serializer_class = netbox_rpki.api.serializers.RoaPrefixSerializer
    filterset_class = netbox_rpki.filtersets.RoaPrefixFilterSet
