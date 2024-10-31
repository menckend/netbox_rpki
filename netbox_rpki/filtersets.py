from netbox.filtersets import NetBoxModelFilterSet
import netbox_rpki
from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix


class CertificateFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = netbox_rpki.models.Certificate
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)

class OrganizationFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = netbox_rpki.models.Organization
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class RoaFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = netbox_rpki.models.Roa
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class RoaPrefixFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = netbox_rpki.models.RoaPrefix
        fields = ['prefix', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)
