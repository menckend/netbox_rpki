from netbox.filtersets import NetBoxModelFilterSet
from netbox_rpki.models import RpkiCertificate, RpkiOrganization, RpkiRoa, RpkiRoaPrefices


class RpkiCertificateFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = RpkiCertificate
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)

class RpkiOrganizationFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = RpkiOrganization
        fields = ['orgName', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class RpkiRoaFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = RpkiRoa
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class RpkiRoaPreficesFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = RpkiRoaPrefices
        fields = ['prefix', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)
