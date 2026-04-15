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


_BaseROALintSuppressionFilterSet = ROALintSuppressionFilterSet


class ROALintSuppressionFilterSet(_BaseROALintSuppressionFilterSet):
    is_active = django_filters.BooleanFilter(
        method='filter_is_active',
        label='Is Active (not lifted and not expired)',
    )
    is_lifted = django_filters.BooleanFilter(
        method='filter_is_lifted',
        label='Is Lifted',
    )
    is_expired = django_filters.BooleanFilter(
        method='filter_is_expired',
        label='Is Expired (expires_at passed but not lifted)',
    )
    expiring_within_days = django_filters.NumberFilter(
        method='filter_expiring_within_days',
        label='Expiring within N days',
    )

    def filter_is_active(self, queryset, name, value):
        from django.utils import timezone
        now = timezone.now()
        if value is True:
            return queryset.filter(
                lifted_at__isnull=True,
            ).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )
        elif value is False:
            return queryset.filter(
                Q(lifted_at__isnull=False) | Q(expires_at__lte=now)
            )
        return queryset

    def filter_is_lifted(self, queryset, name, value):
        if value is True:
            return queryset.filter(lifted_at__isnull=False)
        elif value is False:
            return queryset.filter(lifted_at__isnull=True)
        return queryset

    def filter_is_expired(self, queryset, name, value):
        from django.utils import timezone
        now = timezone.now()
        if value is True:
            return queryset.filter(
                lifted_at__isnull=True,
                expires_at__isnull=False,
                expires_at__lte=now,
            )
        elif value is False:
            return queryset.filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )
        return queryset

    def filter_expiring_within_days(self, queryset, name, value):
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.now()
        cutoff = now + timedelta(days=int(value))
        return queryset.filter(
            lifted_at__isnull=True,
            expires_at__isnull=False,
            expires_at__lte=cutoff,
            expires_at__gt=now,
        )


globals()['ROALintSuppressionFilterSet'] = ROALintSuppressionFilterSet


_BaseROALintFindingFilterSet = ROALintFindingFilterSet


class ROALintFindingFilterSet(_BaseROALintFindingFilterSet):
    rule_family = django_filters.CharFilter(
        method='filter_rule_family',
        label='Rule family (e.g. intent_safety, published_hygiene, plan_risk, ownership_context)',
    )
    is_suppressed = django_filters.BooleanFilter(
        method='filter_is_suppressed',
        label='Is suppressed',
    )
    approval_impact = django_filters.CharFilter(
        method='filter_approval_impact',
        label='Approval impact (informational, acknowledgement_required, blocking)',
    )

    def filter_rule_family(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(details_json__rule_family=value)

    def filter_is_suppressed(self, queryset, name, value):
        if value is True:
            return queryset.filter(details_json__suppressed=True)
        elif value is False:
            return queryset.filter(details_json__suppressed=False)
        return queryset

    def filter_approval_impact(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(details_json__approval_impact=value)


globals()['ROALintFindingFilterSet'] = ROALintFindingFilterSet
