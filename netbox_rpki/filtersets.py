from netbox.filtersets import NetBoxModelFilterSet
from .models import gns3srv, ptovjob, switchtojob


class RpkiCertificateFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = RpkiCertificate
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)

class RpkiOrganizationFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = RpkiOrganization
        fields = ['name', ]


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
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)
