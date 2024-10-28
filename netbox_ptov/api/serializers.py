"""Django API serializer definitions for the netbox_ptov plugin"""

from rest_framework.serializers import HyperlinkedIdentityField, ValidationError
from rest_framework.relations import PrimaryKeyRelatedField

from netbox.api.fields import ChoiceField, SerializedPKRelatedField

from netbox.api.serializers import NetBoxModelSerializer
from ipam.api.serializers import IPAddressSerializer, ASNSerializer, PrefixSerializer
from tenancy.api.serializers import TenantSerializer
from dcim.api.serializers import SiteSerializer, DeviceSerializer


from netbox_ptov.models import gns3srv, ptovjob, switchtojob 

class gns3srvSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_ptov:gns3srv-detail")

    class Meta:
        model = gns3srv
        fields = [
            "id",
            "tags",
            "name",
        ]
        brief_fields = ("id", "name")


class ptovjobSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_ptov_:ptovjob-detail")

    class Meta:
        model = ptovjob
        fields = [
            "name", "eosuname", "gns3srv", "gns3prjname", "gns3prjid", "eospasswd"
        ]
        brief_fields = ("name", "gns3prjname", "gns3prjid")


class switchtojobSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_ptov:switchtojob-detail")

    class Meta:
        model = switchtojob
        fields = [
            "name", "switch", "job",
        ]
        brief_fields = ("name", "switch")
