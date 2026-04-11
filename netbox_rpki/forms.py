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
from netbox_rpki.object_registry import FILTER_FORM_OBJECT_SPECS, FORM_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec
# from .choices import (
#    SessionStatusChoices,
#    CommunityStatusChoices,
#    IPAddressFamilyChoices,
# )

from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix, CertificatePrefix, CertificateAsn


def build_model_form_class(spec: ObjectSpec) -> type[NetBoxModelForm]:
    meta_class = type(
        'Meta',
        (),
        {
            'model': spec.model,
            'fields': spec.form.fields,
        },
    )

    return type(
        spec.form.class_name,
        (NetBoxModelForm,),
        {
            '__module__': __name__,
            'tenant': DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False),
            'comments': CommentField(),
            'Meta': meta_class,
        },
    )


for object_spec in FORM_OBJECT_SPECS:
    globals()[object_spec.form.class_name] = build_model_form_class(object_spec)


def build_filter_form_class(spec: ObjectSpec) -> type[NetBoxModelFilterSetForm]:
    return type(
        spec.filter_form.class_name,
        (NetBoxModelFilterSetForm,),
        {
            '__module__': __name__,
            'q': forms.CharField(required=False, label='Search'),
            'tenant': DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False),
            'tag': TagFilterField(spec.model),
            'model': spec.model,
        },
    )


for object_spec in FILTER_FORM_OBJECT_SPECS:
    globals()[object_spec.filter_form.class_name] = build_filter_form_class(object_spec)
