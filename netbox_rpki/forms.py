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
    acknowledged_findings = forms.ModelMultipleChoiceField(
        queryset=netbox_rpki.models.ROALintFinding.objects.none(),
        required=False,
        label='Acknowledge Approval-Required Lint Findings',
        widget=forms.CheckboxSelectMultiple,
        help_text='Select acknowledgement-required lint findings reviewed and accepted for this change plan.',
    )
    lint_acknowledgement_notes = forms.CharField(
        required=False,
        label='Lint Acknowledgement Notes',
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Optional note recorded on created lint acknowledgements.',
    )

    fieldsets = (
        FieldSet(
            'ticket_reference',
            'change_reference',
            'maintenance_window_start',
            'maintenance_window_end',
            'approval_notes',
            'acknowledged_findings',
            'lint_acknowledgement_notes',
            name='Governance',
        ),
    )

    def __init__(self, *args, plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan = plan
        latest_lint_run = getattr(plan, 'lint_runs', None)
        latest_lint_run = latest_lint_run.order_by('-started_at', '-created').first() if latest_lint_run is not None else None
        queryset = netbox_rpki.models.ROALintFinding.objects.none()
        if latest_lint_run is not None:
            acknowledged_ids = set(plan.lint_acknowledgements.values_list('finding_id', flat=True)) if plan is not None else set()
            blocking_ids = []
            for finding in latest_lint_run.findings.all():
                if (
                    finding.details_json.get('approval_impact') == 'acknowledgement_required'
                    and not finding.details_json.get('suppressed')
                    and finding.pk not in acknowledged_ids
                ):
                    blocking_ids.append(finding.pk)
            queryset = netbox_rpki.models.ROALintFinding.objects.filter(pk__in=blocking_ids)
            self.fields['acknowledged_findings'].queryset = queryset
            self.fields['acknowledged_findings'].label_from_instance = (
                lambda obj: f'[{obj.severity}] {obj.details_json.get("rule_label", obj.finding_code)}: '
                f'{obj.details_json.get("operator_message", obj.name)}'
            )
        if not queryset.exists():
            self.fields['acknowledged_findings'].help_text = (
                'No current unsuppressed acknowledgement-required lint findings remain to acknowledge.'
            )

    def clean(self):
        cleaned_data = super().clean()
        validate_maintenance_window_bounds(
            start_at=cleaned_data.get('maintenance_window_start'),
            end_at=cleaned_data.get('maintenance_window_end'),
        )
        acknowledged_findings = cleaned_data.get('acknowledged_findings')
        if acknowledged_findings is not None:
            valid_ids = set(self.fields['acknowledged_findings'].queryset.values_list('pk', flat=True))
            selected_ids = {finding.pk for finding in acknowledged_findings}
            if not selected_ids.issubset(valid_ids):
                raise ValidationError({
                    'acknowledged_findings': 'Only current unsuppressed acknowledgement-required findings may be acknowledged.'
                })
        return cleaned_data


class ASPAChangePlanApprovalForm(ROAChangePlanApprovalForm):
    pass


class ROAChangePlanLintAcknowledgementForm(ConfirmationForm):
    ticket_reference = forms.CharField(required=False, max_length=200, label='Ticket Reference')
    change_reference = forms.CharField(required=False, max_length=200, label='Change Reference')
    acknowledged_findings = forms.ModelMultipleChoiceField(
        queryset=netbox_rpki.models.ROALintFinding.objects.none(),
        required=True,
        label='Acknowledge Approval-Required Lint Findings',
        widget=forms.CheckboxSelectMultiple,
        help_text='Select current acknowledgement-required lint findings reviewed and accepted for this draft change plan.',
    )
    lint_acknowledgement_notes = forms.CharField(
        required=False,
        label='Acknowledgement Notes',
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Operator justification recorded on the created lint acknowledgement records.',
    )

    fieldsets = (
        FieldSet(
            'ticket_reference',
            'change_reference',
            'acknowledged_findings',
            'lint_acknowledgement_notes',
            name='Lint Review',
        ),
    )

    def __init__(self, *args, plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan = plan
        latest_lint_run = getattr(plan, 'lint_runs', None)
        latest_lint_run = latest_lint_run.order_by('-started_at', '-created').first() if latest_lint_run is not None else None
        queryset = netbox_rpki.models.ROALintFinding.objects.none()
        if latest_lint_run is not None:
            blocking_ids = []
            acknowledged_ids = set(plan.lint_acknowledgements.values_list('finding_id', flat=True)) if plan is not None else set()
            for finding in latest_lint_run.findings.all():
                if (
                    finding.details_json.get('approval_impact') == 'acknowledgement_required'
                    and not finding.details_json.get('suppressed')
                    and finding.pk not in acknowledged_ids
                ):
                    blocking_ids.append(finding.pk)
            queryset = netbox_rpki.models.ROALintFinding.objects.filter(pk__in=blocking_ids)
        self.fields['acknowledged_findings'].queryset = queryset
        self.fields['acknowledged_findings'].label_from_instance = (
            lambda obj: f'[{obj.severity}] {obj.details_json.get("rule_label", obj.finding_code)}: '
            f'{obj.details_json.get("operator_message", obj.name)}'
        )
        if not queryset.exists():
            self.fields['acknowledged_findings'].required = False
            self.fields['acknowledged_findings'].help_text = (
                'No current unsuppressed acknowledgement-required lint findings remain to acknowledge.'
            )

    def clean(self):
        cleaned_data = super().clean()
        acknowledged_findings = cleaned_data.get('acknowledged_findings')
        if not self.fields['acknowledged_findings'].queryset.exists():
            if acknowledged_findings:
                raise ValidationError({'acknowledged_findings': 'No current acknowledgement-required findings remain to acknowledge.'})
            return cleaned_data
        if not acknowledged_findings:
            raise ValidationError({'acknowledged_findings': 'Select at least one current acknowledgement-required finding to acknowledge.'})
        valid_ids = set(self.fields['acknowledged_findings'].queryset.values_list('pk', flat=True))
        selected_ids = {finding.pk for finding in acknowledged_findings}
        if not selected_ids.issubset(valid_ids):
            raise ValidationError({
                'acknowledged_findings': 'Only current unacknowledged acknowledgement-required findings may be acknowledged.'
            })
        return cleaned_data


class ROALintFindingSuppressForm(ConfirmationForm):
    scope_type = forms.ChoiceField(
        choices=netbox_rpki.models.ROALintSuppressionScope.choices,
        label='Suppression Scope',
    )
    reason = forms.CharField(required=True, max_length=255, label='Reason')
    expires_at = forms.DateTimeField(
        required=False,
        label='Expires At',
        input_formats=(
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d %H:%M:%S',
        ),
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M',
        ),
        help_text='Optional expiry for the suppression.',
    )
    notes = forms.CharField(
        required=False,
        label='Notes',
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    fieldsets = (
        FieldSet('scope_type', 'reason', 'expires_at', 'notes', name='Suppression'),
    )

    def __init__(self, *args, finding=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.finding = finding
        has_intent = bool(
            getattr(finding, 'roa_intent_result_id', None)
            or getattr(getattr(finding, 'change_plan_item', None), 'roa_intent_id', None)
        )
        if not has_intent:
            self.fields['scope_type'].choices = [
                (netbox_rpki.models.ROALintSuppressionScope.PROFILE, 'Profile'),
            ]


class ROALintSuppressionLiftForm(ConfirmationForm):
    lift_reason = forms.CharField(
        required=False,
        label='Lift Reason',
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Optional note explaining why the suppression was lifted.',
    )
