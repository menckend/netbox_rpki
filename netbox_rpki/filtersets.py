from netbox.filtersets import NetBoxModelFilterSet
from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix


class CertificateFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = Certificate
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)

class OrganizationFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = Organization
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class RoaFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = Roa
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class RoaPrefixFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = roaprefices
        fields = ['prefix', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)
