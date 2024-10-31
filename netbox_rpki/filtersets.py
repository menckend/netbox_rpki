from netbox.filtersets import NetBoxModelFilterSet
from netbox_rpki.models import RpkiCertificate, RpkiOrganization, RpkiRoa, RpkiRoaPrefices


class certificateFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = certificate
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)

class organizationFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = organization
        fields = ['orgName', ]


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
