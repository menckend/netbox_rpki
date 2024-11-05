# import netbox_rpki
# from django import forms
# from ipam.models import Prefix
from netbox.forms import NetBoxModelForm

# from utilities.forms.fields import CommentField, DynamicModelChoiceField
# from dcim.models import devices
# from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix
from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix


class CertificateForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    class Meta:
        model = Certificate
        fields = ['name', 'issuer', 'subject', 'serial', 'valid_from', 'valid_to', "auto_renews", 'public_key', 'private_key', 'publication_url', 'ca_repository', 'rpki_org', 'self_hosted', 'tenant']


class OrganizationForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()
    
    class Meta:
        model = Organization
        fields = ['org_id', 'name', 'parent_rir', 'ext_url', 'tenant']


class RoaForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()
    class Meta:
        model = Roa
        fields: list[str] = ['name', 'origin_as', 'valid_from', 'valid_to', "auto_renews", 'signed_by', 'tenant']


class RoaPrefixForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()
    class Meta:
        model = RoaPrefix
        fields = ['prefix', 'max_length', 'roa_name', 'tenant']
