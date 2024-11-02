"""Django API url router definitions for the netbox_ptov plugin"""

from netbox.api.routers import NetBoxRouter
from netbox_rpki.api.views import CertificateViewSet, OrganizationViewSet, RoaViewSet, RoaPrefixViewSet, RootView

app_name = 'netbox_rpki'

router = NetBoxRouter()
router.APIRootView = RootView
router.register('certificate', CertificateViewSet, basename='certificate')
router.register('organization', OrganizationViewSet, basename='organization')
router.register('roa', RoaViewSet, basename='roa')
router.register('roaprefix', RoaPrefixViewSet, basename='roaprefix')

urlpatterns = router.urls
