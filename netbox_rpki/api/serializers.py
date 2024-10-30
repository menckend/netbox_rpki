from rest_framework.serializers import HyperlinkedIdentityField, ValidationError
from rest_framework.relations import PrimaryKeyRelatedField

from netbox.api.fields import ChoiceField, SerializedPKRelatedField

from netbox.api.serializers import NetBoxModelSerializer
from ipam.api.serializers import IPAddressSerializer, ASNSerializer, PrefixSerializer
from tenancy.api.serializers import TenantSerializer
from dcim.api.serializers import SiteSerializer, DeviceSerializer


from netbox_rpki.models import RpkiCertificate, RpkiOrganization, RpkiRoa, RpkiRoaPrefices 

class RpkiCertificateSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki:rpkicertificate-detail")

    class Meta:
        model = RpkiCertificate
        fields = ["id", "name", "issuer", "subject", "serial", "validFrom", "validTo", "publicKey", "privateKey", "publicationUrl", "caRepository","selfHosted", "rpkiOrg"]
        brief_fields = ("name", "issuer", "subject", "serial", "rpkiOrg")


class RpkiOrganizationSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki_:rpkiorganization-detail")

    class Meta:
        model = RpkiOrganization
        fields = ["id", "orgId", "orgName"]
        brief_fields = ("orgId", "orgName")


class RpkiRoaSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki_:rpkiroa-detail")

    class Meta:
        model = RpkiRoa
        fields = ["id", "name", "originaAs", "validFrom", "validTo", "signedBy"]
        brief_fields = ("ordId", "orgName")

class RpkiRoaPreficesSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki_:rpkiroaprefices-detail")

    class Meta:
        model = RpkiRoaPrefices
        fields = ["id", "prefix", "maxlength", "roaName"]
        brief_fields = ("id", "prefix", "maxlength", "roaName")

