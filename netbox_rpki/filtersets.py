from netbox.filtersets import NetBoxModelFilterSet
from netbox_rpki.models import certificate, organization, roa, roaprefices


class certificateFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = certificate
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)

class organizationFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = organization
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class roaFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = roa
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class roapreficesFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = roaprefices
        fields = ['prefix', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)
