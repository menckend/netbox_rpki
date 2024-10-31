import netbox_rpki
from django import forms
from ipam.models import Prefix
from netbox.forms import NetBoxModelForm
from utilities.forms.fields import CommentField, DynamicModelChoiceField
from dcim.models import devices
from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix


class CertificateForm(NetBoxModelForm):
    model = netbox_rpki.models.Certificate
    fields = ["name", "issuer", "subject", "serial", " valid_from", "valid_to", "public_key", "private_key", "publication_url", "ca_repository", "org_id", "self_hosted"]

    class Meta:
        model = netbox_rpki.models.Certificate
#        fields = ["name", "issuer", "subject", "serial", " valid_from", "valid_to", "public_key", "private_key", "publication_url", "ca_repository", "org_id", "self_hosted"]


class OrganizationForm(NetBoxModelForm):
    model = netbox_rpki.models.Organization
    fields = ["org_id", "name"]

    class Meta:
        model = netbox_rpki.models.Organization
#        fields = ["org_id", "name"]


class RoaForm(NetBoxModelForm):
    model = netbox_rpki.models.Roa
    fields = ["name", "origin_as", "valid_from", "valid_to", "signed_by"]

    class Meta:
        model = netbox_rpki.models.Roa
#        fields = ["name", "origin_as", "valid_from", "valid_to", "signed_by"]



class RoaPrefixForm(NetBoxModelForm):
    model = netbox_rpki.models.RoaPrefix
    fields = ["prefix", "max_length", "roa_name"]

    class Meta:
        model = netbox_rpki.models.RoaPrefix
#        fields = ["prefix", "max_length", "roa_name"]
        
