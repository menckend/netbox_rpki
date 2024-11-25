from django import forms
from utilities.forms.rendering import FieldSet
from django.core.exceptions import (
    MultipleObjectsReturned,
    ObjectDoesNotExist,
    ValidationError,
)
from django.utils.translation import gettext as _

from tenancy.models import Tenant
from dcim.models import Device, Site
from ipam.models import IPAddress, Prefix, ASN
from ipam.formfields import IPNetworkFormField
from utilities.forms.fields import (
    DynamicModelChoiceField,
    CSVModelChoiceField,
    CSVModelMultipleChoiceField,
    DynamicModelMultipleChoiceField,
    TagFilterField,
    CSVChoiceField,
    CommentField,
)
from utilities.forms.widgets import APISelect, APISelectMultiple
from netbox.forms import (
    NetBoxModelForm,
    NetBoxModelBulkEditForm,
    NetBoxModelFilterSetForm,
    NetBoxModelImportForm,
)
import netbox_rpki
# from .choices import (
#    SessionStatusChoices,
#    CommunityStatusChoices,
#    IPAddressFamilyChoices,
# )

from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix, CertificatePrefix, CertificateAsn


class CertificateForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    class Meta:
        model = Certificate
        fields = ['name', 'issuer', 'subject', 'serial', 'valid_from', 'valid_to', "auto_renews", 'public_key', 'private_key', 'publication_url', 'ca_repository', 'rpki_org', 'self_hosted', 'tenant', 'comments', 'tags']


class CertificateFilterForm(NetBoxModelFilterSetForm):
    q = forms.CharField(required=False, label="Search")
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    tag = TagFilterField(Certificate)

    model = Certificate


class OrganizationForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    class Meta:
        model = Organization
        fields = ['org_id', 'name', 'parent_rir', 'ext_url', 'tenant', 'comments', 'tags']


class RoaForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    class Meta:
        model = Roa
        fields: list[str] = ['name', 'origin_as', 'valid_from', 'valid_to', "auto_renews", 'signed_by', 'tenant', 'comments', 'tags']


class RoaPrefixForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    class Meta:
        model = RoaPrefix
        fields = ['prefix', 'max_length', 'roa_name', 'tenant', 'comments', 'tags']


class CertificatePrefixForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    class Meta:
        model = CertificatePrefix
        fields = ['prefix', 'certificate_name', 'tenant', 'comments', 'tags']

class CertificateAsnForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    class Meta:
        model = CertificateAsn
        fields = ['asn', 'certificate_name2', 'tenant', 'comments', 'tags']
