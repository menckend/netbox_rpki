"""Django API url router definitions for the netbox_ptov plugin"""

from netbox.api.routers import NetBoxRouter

from netbox_rpki.api.views import (
    RpkiCertificateViewSet, RpkiOrganizationViewSet, RpkiRoaViewSet, RpkiRoaPreficesViewSet, RootView
)

app_name = 'netbox_ptov'

router = NetBoxRouter()
router.APIRootView = RootView
router.register('rpkicertificate', RpkiCertificateViewSet, basename='rpkicertificate')
router.register('rpkiorganization', RpkiOrganizationViewSet, basename='rpkiorganization')
router.register('rpkiroa', RpkiRoaViewSet, basename='rpkiroa')
router.register('rpkiroaprefices', RpkiRoaPreficesViewSet, basename='rpkiroaprefices')

urlpatterns = router.urls
