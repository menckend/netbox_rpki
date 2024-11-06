"""Django API url router definitions for the netbox_ptov plugin"""

from netbox.api.routers import NetBoxRouter
from netbox_rpki.api.views import CertificateViewSet, OrganizationViewSet, RoaViewSet, RoaPrefixViewSet, CertificatePrefixViewSet, CertificateAsnViewSet,RootView

app_name = 'netbox_rpki'

router = NetBoxRouter()
router.APIRootView = RootView
router.register('certificate', CertificateViewSet, basename='certificate')
router.register('organization', OrganizationViewSet, basename='organization')
router.register('roa', RoaViewSet, basename='roa')
router.register('roaprefix', RoaPrefixViewSet, basename='roaprefix')
router.register('certificateprefix', CertificatePrefixViewSet, basename='certificateprefix')
router.register('certificateasn', CertificateAsnViewSet, basename='certificateasn')

urlpatterns = router.urls
