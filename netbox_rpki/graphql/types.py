import strawberry_django

from netbox.graphql.types import NetBoxObjectType

from netbox_rpki.object_registry import GRAPHQL_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec

from .filters import GRAPHQL_FILTER_CLASS_MAP


def build_graphql_type_class(spec: ObjectSpec) -> type[NetBoxObjectType]:
    type_class = type(
        spec.graphql.type.class_name,
        (NetBoxObjectType,),
        {
            "__module__": __name__,
            "__doc__": f"Generated GraphQL type for {spec.model.__name__}.",
            "__object_spec__": spec,
        },
    )
    return strawberry_django.type(
        spec.model,
        fields=spec.graphql.type.fields,
        filters=GRAPHQL_FILTER_CLASS_MAP[spec.key],
    )(type_class)


GRAPHQL_TYPE_CLASS_MAP = {}
for object_spec in GRAPHQL_OBJECT_SPECS:
    type_class = build_graphql_type_class(object_spec)
    GRAPHQL_TYPE_CLASS_MAP[object_spec.key] = type_class
    globals()[object_spec.graphql.type.class_name] = type_class


__all__ = tuple(spec.graphql.type.class_name for spec in GRAPHQL_OBJECT_SPECS)
