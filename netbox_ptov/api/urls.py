"""Django API url router definitions for the netbox_ptov plugin"""

from netbox.api.routers import NetBoxRouter

from netbox_ptov.api.views import (
    gns3srvViewSet, ptovjobViewSet, switchtojobViewSet, RootView
)

app_name = 'netbox_ptov'

router = NetBoxRouter()
router.APIRootView = RootView
router.register('gns3srv', gns3srvViewSet, basename='gns3srv')
router.register('ptovjob', ptovjobViewSet, basename='ptovjob')
router.register('switchtojob', switchtojobViewSet, basename='switchtojob')

urlpatterns = router.urls
