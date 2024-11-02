from rest_framework.routers import APIRootView
from netbox.api.viewsets import NetBoxModelViewSet
from netbox_rpki.api.serializers import OrganizationSerializer, CertificateSerializer, RoaSerializer, RoaPrefixSerializer
from netbox_rpki import filtersets, models


class RootView(APIRootView):
    def get_view_name(self):
        return 'rpki'


class OrganizationViewSet(NetBoxModelViewSet):
    queryset = models.Organization.objects.all()
    serializer_class = OrganizationSerializer
    filterset_class = filtersets.OrganizationFilterSet


class CertificateViewSet(NetBoxModelViewSet):
    queryset = models.Certificate.objects.all()
    serializer_class = CertificateSerializer
    filterset_class = filtersets.CertificateFilterSet


class RoaViewSet(NetBoxModelViewSet):
    queryset: models.Roa.objects.all()
    serializer_class = RoaSerializer
    filterset_class = filtersets.RoaFilterSet


class RoaPrefixViewSet(NetBoxModelViewSet):
    queryset: models.RoaPrefix.objects.all()
    serializer_class = RoaPrefixSerializer
    filterset_class = filtersets.RoaPrefixFilterSet
