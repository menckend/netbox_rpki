"""Django API url router definitions for the netbox_ptov plugin"""

from netbox.api.routers import NetBoxRouter

from netbox_rpki.api.views import (
    certificateViewSet, organizationViewSet, roaViewSet, roapreficesViewSet, RootView
)

app_name = 'netbox_ptov'

router = NetBoxRouter()
router.APIRootView = RootView
router.register('certificate', certificateViewSet, basename='certificate')
router.register('organization', organizationViewSet, basename='organization')
router.register('roa', roaViewSet, basename='roa')
router.register('roaprefices', roapreficesViewSet, basename='roaprefices')

urlpatterns = router.urls
