"""Django API url router definitions for the netbox_ptov plugin"""

from netbox.api.routers import NetBoxRouter
import netbox_rpki
from netbox_rpki.api.views import (
    CertificateViewSet, OrganizationViewSet, RoaViewSet, RoaPrefixViewSet, RootView
)

app_name = 'netbox_rpki'

router = NetBoxRouter()
router.APIRootView = RootView
router.register('certificate', netbox_rpki.api.views.CertificateViewSet, basename='certificate')
router.register('organization', netbox_rpki.api.views.OrganizationViewSet, basename='organization')
router.register('roa', netbox_rpki.api.views.RoaViewSet, basename='roa')
router.register('roaprefix', RoaprefixViewSet, basename='roaprefix')

urlpatterns = router.urls
