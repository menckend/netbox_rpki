from rest_framework.routers import APIRootView

from netbox.api.viewsets import NetBoxModelViewSet

from netbox_rpki import filtersets as filterset_module
from netbox_rpki.api.serializers import SERIALIZER_CLASS_MAP
from netbox_rpki.object_registry import API_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec


class RootView(APIRootView):
    def get_view_name(self):
        return "rpki"


def build_viewset_class(spec: ObjectSpec) -> type[NetBoxModelViewSet]:
    return type(
        spec.api.viewset_name,
        (NetBoxModelViewSet,),
        {
            "__module__": __name__,
            "queryset": spec.model.objects.all(),
            "serializer_class": SERIALIZER_CLASS_MAP[spec.key],
            "filterset_class": getattr(filterset_module, spec.filterset.class_name),
        },
    )


VIEWSET_CLASS_MAP = {}
for object_spec in API_OBJECT_SPECS:
    viewset_class = build_viewset_class(object_spec)
    VIEWSET_CLASS_MAP[object_spec.key] = viewset_class
    globals()[object_spec.api.viewset_name] = viewset_class


__all__ = ("RootView",) + tuple(spec.api.viewset_name for spec in API_OBJECT_SPECS)
