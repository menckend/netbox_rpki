from rest_framework.serializers import HyperlinkedIdentityField, ValidationError
from rest_framework.relations import PrimaryKeyRelatedField

from netbox.api.fields import ChoiceField, SerializedPKRelatedField

from netbox.api.serializers import NetBoxModelSerializer
from ipam.api.serializers import IPAddressSerializer, ASNSerializer, PrefixSerializer
from tenancy.api.serializers import TenantSerializer
from dcim.api.serializers import SiteSerializer, DeviceSerializer

import netbox_rpki
from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix

class CertificateSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki:certificate-detail")

    class Meta:
        model = netbox_rpki.models.Certificate
        fields = ("id", "name", "issuer", "subject", "serial", "valid_from", "valid_to", "public_key", "private_key", "publication_url", "ca_repository","self_hosted", "rpki_org")
        brief_fields = ("name", "issuer", "subject", "serial", "rpki_org")


class OrganizationSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki_:organization-detail")

    class Meta:
        model = netbox_rpki.models.Organization
        fields = ["id", "org_id", "name"]
        brief_fields = ("org_id", "name")


class RoaSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki_:roa-detail")

    class Meta:
        model = netbox_rpki.models.Roa
        fields = ["id", "name", "origina_as", "valid_from", "valid_to", "signed_by"]
        brief_fields = ("org_id", "name")

class RoaPrefixSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(view_name="plugins-api:netbox_rpki_:roaprefix-detail")

    class Meta:
        model = netbox_rpki.models.RoaPrefix
        fields = ["id", "prefix", "max_length", "roa_name"]
        brief_fields = ("id", "prefix", "max_length", "roa_name")
