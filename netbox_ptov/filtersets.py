"""Django filtersets for netbox_ptov plugin

Defines the Django filtersets used by the netbox_ptov plugin"""


from netbox.filtersets import NetBoxModelFilterSet
from .models import gns3srv, ptovjob, switchtojob


class gns3srvFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = gns3srv
        fields = ['name', ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class ptovjobFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = ptovjob 
        fields = ['name', 'gns3prjname', 'gns3srv', 'eosuname' ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)

class switchtojobFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = switchtojob
        fields = ['name', 'switch', 'job' ]


    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)
