import strawberry
import strawberry_django

from netbox_rpki.object_registry import GRAPHQL_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec

from . import types as graphql_types


def get_graphql_type_class(spec: ObjectSpec) -> type:
    return getattr(graphql_types, spec.graphql.type.class_name)


def get_graphql_field_names(spec: ObjectSpec) -> tuple[str, str]:
    return spec.graphql.detail_field_name, spec.graphql.list_field_name


GRAPHQL_TYPE_CLASS_MAP = {
    spec.key: get_graphql_type_class(spec)
    for spec in GRAPHQL_OBJECT_SPECS
}

GRAPHQL_FIELD_NAME_MAP = {
    spec.key: get_graphql_field_names(spec)
    for spec in GRAPHQL_OBJECT_SPECS
}


def build_query_type() -> type:
    annotations = {}
    namespace = {
        "__module__": __name__,
    }

    for spec in GRAPHQL_OBJECT_SPECS:
        type_class = GRAPHQL_TYPE_CLASS_MAP[spec.key]
        detail_field_name, list_field_name = GRAPHQL_FIELD_NAME_MAP[spec.key]
        annotations[detail_field_name] = type_class
        annotations[list_field_name] = list[type_class]
        namespace[detail_field_name] = strawberry_django.field()
        namespace[list_field_name] = strawberry_django.field()

    namespace["__annotations__"] = annotations
    query_class = type("NetBoxRpkiQuery", (), namespace)
    return strawberry.type(query_class, name="Query")


NetBoxRpkiQuery = build_query_type()


schema = [
    NetBoxRpkiQuery,
]
