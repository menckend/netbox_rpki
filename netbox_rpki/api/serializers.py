from rest_framework.serializers import HyperlinkedIdentityField, ValidationError
from rest_framework.relations import PrimaryKeyRelatedField

from netbox.api.fields import ChoiceField, SerializedPKRelatedField

from netbox.api.serializers import NetBoxModelSerializer
from ipam.api.serializers import IPAddressSerializer, ASNSerializer, PrefixSerializer
from tenancy.api.serializers import TenantSerializer
from dcim.api.serializers import SiteSerializer, DeviceSerializer


from netbox_rpki.models import certificate, organization, roa, roaprefices 

class certificateSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki:certificate-detail")

    class Meta:
        model = certificate
        fields = ["id", "name", "issuer", "subject", "serial", "validFrom", "validTo", "publicKey", "privateKey", "publicationUrl", "caRepository","selfHosted", "rpkiOrg"]
        brief_fields = ("name", "issuer", "subject", "serial", "rpkiOrg")


class organizationSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki_:organization-detail")

    class Meta:
        model = organization
        fields = ["id", "orgId", "orgName"]
        brief_fields = ("orgId", "orgName")


class roaSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki_:roa-detail")

    class Meta:
        model = roa
        fields = ["id", "name", "originaAs", "validFrom", "validTo", "signedBy"]
        brief_fields = ("ordId", "orgName")

class roapreficesSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki_:roaprefices-detail")

    class Meta:
        model = roaprefices
        fields = ["id", "prefix", "maxlength", "roaName"]
        brief_fields = ("id", "prefix", "maxlength", "roaName")
