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
from utilities.forms import ConfirmationForm
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

from netbox_rpki.models import (
    Certificate,
    Organization,
    Roa,
    RoaPrefix,
    CertificatePrefix,
    CertificateAsn,
    validate_maintenance_window_bounds,
)


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


class ROAChangePlanApprovalForm(ConfirmationForm):
    ticket_reference = forms.CharField(required=False, max_length=200, label='Ticket Reference')
    change_reference = forms.CharField(required=False, max_length=200, label='Change Reference')
    maintenance_window_start = forms.DateTimeField(
        required=False,
        label='Maintenance Window Start',
        input_formats=(
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d %H:%M:%S',
        ),
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M',
        ),
        help_text='Optional scheduled start for the approved maintenance window.',
    )
    maintenance_window_end = forms.DateTimeField(
        required=False,
        label='Maintenance Window End',
        input_formats=(
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d %H:%M:%S',
        ),
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M',
        ),
        help_text='Optional scheduled end for the approved maintenance window.',
    )
    approval_notes = forms.CharField(
        required=False,
        label='Approval Notes',
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Optional operator note recorded on the approval record.',
    )

    fieldsets = (
        FieldSet(
            'ticket_reference',
            'change_reference',
            'maintenance_window_start',
            'maintenance_window_end',
            'approval_notes',
            name='Governance',
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        validate_maintenance_window_bounds(
            start_at=cleaned_data.get('maintenance_window_start'),
            end_at=cleaned_data.get('maintenance_window_end'),
        )
        return cleaned_data
