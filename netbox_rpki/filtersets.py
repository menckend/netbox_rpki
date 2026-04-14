import django_filters
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


_BaseProviderSnapshotDiffItemFilterSet = ProviderSnapshotDiffItemFilterSet


class ProviderSnapshotDiffItemFilterSet(_BaseProviderSnapshotDiffItemFilterSet):
    family_kind = django_filters.ChoiceFilter(
        choices=(
            ('control_plane', 'Control Plane'),
            ('publication_observation', 'Publication Observation'),
        ),
        method='filter_family_kind',
        label='Family Kind',
    )

    def filter_family_kind(self, queryset, name, value):
        from netbox_rpki.services.provider_sync_contract import PROVIDER_SYNC_FAMILY_METADATA

        if not value:
            return queryset
        matching_families = [
            family
            for family, meta in PROVIDER_SYNC_FAMILY_METADATA.items()
            if meta.get('family_kind') == value
        ]
        if not matching_families:
            return queryset.none()
        return queryset.filter(object_family__in=matching_families)


globals()['ProviderSnapshotDiffItemFilterSet'] = ProviderSnapshotDiffItemFilterSet
