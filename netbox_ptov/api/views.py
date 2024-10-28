"""Django API views for the netbox_ptov plugin"""


from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework.routers import APIRootView

from netbox_ptov.api.serializers import (
    gns3srvSerializer, ptovjobSerializer, switchtojobSerializer
)

from netbox_ptov import filtersets, models


class RootView(APIRootView):
    def get_view_name(self):
        return 'ptov'


class ptovjobViewSet(NetBoxModelViewSet):
    queryset = models.ptovjob.objects.all()
    serializer_class = ptovjobSerializer
    filterset_class = filtersets.ptovjobFilterSet


class gns3srvViewSet(NetBoxModelViewSet):
    queryset = models.gns3srv.objects.all()
    serializer_class = gns3srvSerializer
    filterset_class = filtersets.gns3srvFilterSet


class switchtojobViewSet(NetBoxModelViewSet):
    queryset = models.switchtojob.objects.all()
    serializer_class = switchtojobSerializer
    filterset_class = filtersets.switchtojobFilterSet
