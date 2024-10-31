from django import forms
from ipam.models import Prefix
from netbox.forms import NetBoxModelForm
# from utilities.forms.fields import CommentField, DynamicModelChoiceField
from dcim.models import devices
from netbox_rpki.models import certificate, organization, roa, roaprefices


class certificateForm(NetBoxModelForm):
    model = certificate
    fields = ("name", "issuer", "subject", "serial", " validFrom", "validTo", "publicKey", "privateKey", "publicationUrl", "caRepository", "OrgID", "selfHosted")


class organizationForm(NetBoxModelForm):
    model = organization
    fields = ("orgId", "orgName")

class roaForm(NetBoxModelForm):
    model = roa
    fields = ("name", "originAs", "validFrom", "validTo", "signedBy")


class roapreficesForm(NetBoxModelForm):
    model = roaprefices
    fields = ("prefix", "maxLength", "roaName")
