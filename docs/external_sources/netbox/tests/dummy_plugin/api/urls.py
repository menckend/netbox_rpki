from rest_framework import routers
from netbox.tests.dummy_plugin.api.views import DummyViewSet

router = routers.DefaultRouter()
router.register('dummy-models', DummyViewSet)
urlpatterns = router.urls
