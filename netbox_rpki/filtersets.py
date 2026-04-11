from django.db.models import Q

from netbox.filtersets import NetBoxModelFilterSet
from tenancy.filtersets import TenancyFilterSet
from netbox_rpki.object_registry import FILTERSET_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec

def build_filterset_class(spec: ObjectSpec) -> type[NetBoxModelFilterSet]:
    def search(self, queryset, name, value):
        """Perform the filtered search."""
        if not value.strip():
            return queryset

        query = Q()
        for lookup in spec.filterset.search_fields:
            query |= Q(**{lookup: value})
        return queryset.filter(query)

    meta_class = type(
        'Meta',
        (),
        {
            'model': spec.model,
            'fields': spec.filterset.fields,
        },
    )

    return type(
        spec.filterset.class_name,
        (NetBoxModelFilterSet, TenancyFilterSet),
        {
            '__module__': __name__,
            'Meta': meta_class,
            'search': search,
        },
    )


for object_spec in FILTERSET_OBJECT_SPECS:
    globals()[object_spec.filterset.class_name] = build_filterset_class(object_spec)
