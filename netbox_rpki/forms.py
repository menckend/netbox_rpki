from django import forms
from ipam.models import Prefix
from netbox.forms import NetBoxModelForm
# from utilities.forms.fields import CommentField, DynamicModelChoiceField
from dcim.models import devices
from netbox_rpki.models import RpkiCertificate, RpkiOrganization, RpkiRoa, RpkiRoaPrefices


class RpkiCertificateForm(NetBoxModelForm):
    model = RpkiCertificate
    fields = ("name", "issuer", "subject", "serial", " validFrom", "validTo", "publicKey", "privateKey", "publicationUrl", "caRepository", "OrgID", "selfHosted")


class RpkiOrganizationForm(NetBoxModelForm):
    model = RpkiOrganization
    fields = ("orgId", "orgName")

class RpkiRoaForm(NetBoxModelForm):
    model = RpkiRoa
    fields = ("name", "originAs", "validFrom", "validTo", "signedBy")


class RpkiRoaPreficesForm(NetBoxModelForm):
    model = RpkiRoaPrefices
    fields = ("prefix", "maxLength", "roaName")
