"""Django API url router definitions for the netbox_rpki plugin"""

from netbox.api.routers import NetBoxRouter

from netbox_rpki.api.views import RootView, VIEWSET_CLASS_MAP
from netbox_rpki.object_registry import API_OBJECT_SPECS

app_name = 'netbox_rpki'

router = NetBoxRouter()
router.APIRootView = RootView
for object_spec in API_OBJECT_SPECS:
    router.register(
        object_spec.api.basename,
        VIEWSET_CLASS_MAP[object_spec.key],
        basename=object_spec.api.basename,
    )

urlpatterns = router.urls
