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
from netbox_rpki.services.roa_lint import build_roa_change_plan_lint_posture
# from .choices import (
#    SessionStatusChoices,
#    CommunityStatusChoices,
#    IPAddressFamilyChoices,
# )

from netbox_rpki.models import (
    Certificate,
    Organization,
    RoaObject,
    RoaObjectPrefix,
    CertificatePrefix,
    CertificateAsn,
    validate_maintenance_window_bounds,
)


def _ordered_context_group_queryset():
    return netbox_rpki.models.RoutingIntentContextGroup.objects.select_related('organization').order_by(
        'organization__name',
        'priority',
        'name',
        'pk',
    )


def _ordered_provider_account_queryset():
    return netbox_rpki.models.RpkiProviderAccount.objects.select_related('organization').order_by(
        'organization__name',
        'name',
        'pk',
    )


def _coerce_bound_pk(value):
    if value in (None, '', [], (), {}):
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


_BaseRoutingIntentProfileForm = RoutingIntentProfileForm


class RoutingIntentProfileForm(_BaseRoutingIntentProfileForm):
    context_groups = DynamicModelMultipleChoiceField(
        queryset=netbox_rpki.models.RoutingIntentContextGroup.objects.all(),
        required=False,
        label='Context Groups',
        query_params={'organization_id': '$organization'},
        help_text='Optional context groups used to narrow candidate prefixes before rules are evaluated.',
    )

    fieldsets = (
        FieldSet('name', 'organization', 'status', 'is_default', 'enabled', 'allow_as0', name='Profile'),
        FieldSet('selector_mode', 'prefix_selector_query', 'asn_selector_query', name='Selectors'),
        FieldSet('default_max_length_policy', 'context_groups', name='Intent Policy'),
        FieldSet('description', 'comments', 'tenant', 'tags', name='Metadata'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization_id = (
            _coerce_bound_pk(self.data.get('organization'))
            or _coerce_bound_pk(self.initial.get('organization'))
            or getattr(getattr(self.instance, 'organization', None), 'pk', None)
        )
        queryset = _ordered_context_group_queryset()
        if organization_id is not None:
            queryset = queryset.filter(organization_id=organization_id)
        self.fields['context_groups'].queryset = queryset

    def clean_context_groups(self):
        context_groups = self.cleaned_data.get('context_groups')
        organization = self.cleaned_data.get('organization')
        if not context_groups or organization is None:
            return context_groups
        invalid_ids = [
            group.pk
            for group in context_groups
            if group.organization_id != organization.pk
        ]
        if invalid_ids:
            raise ValidationError('Context groups must belong to the same organization as the routing intent profile.')
        return context_groups


_BaseRoutingIntentContextGroupForm = RoutingIntentContextGroupForm


class RoutingIntentContextGroupForm(_BaseRoutingIntentContextGroupForm):
    fieldsets = (
        FieldSet('name', 'organization', 'context_type', 'priority', 'enabled', name='Context Group'),
        FieldSet('description', 'comments', 'tenant', 'tags', name='Metadata'),
    )


_BaseRoutingIntentContextCriterionForm = RoutingIntentContextCriterionForm


class RoutingIntentContextCriterionForm(_BaseRoutingIntentContextCriterionForm):
    match_provider_account = DynamicModelChoiceField(
        queryset=netbox_rpki.models.RpkiProviderAccount.objects.all(),
        required=False,
        label='Provider Account',
    )

    fieldsets = (
        FieldSet('name', 'context_group', 'criterion_type', 'enabled', 'weight', name='Criterion'),
        FieldSet(
            'match_tenant',
            'match_vrf',
            'match_site',
            'match_region',
            'match_provider_account',
            'match_circuit',
            'match_provider',
            'match_value',
            name='Match Target',
        ),
        FieldSet('comments', 'tenant', 'tags', name='Metadata'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        context_group_id = (
            _coerce_bound_pk(self.data.get('context_group'))
            or _coerce_bound_pk(self.initial.get('context_group'))
            or getattr(getattr(self.instance, 'context_group', None), 'pk', None)
        )
        provider_account_queryset = _ordered_provider_account_queryset()
        if context_group_id is not None:
            context_group = netbox_rpki.models.RoutingIntentContextGroup.objects.filter(pk=context_group_id).first()
            if context_group is not None:
                provider_account_queryset = provider_account_queryset.filter(
                    organization_id=context_group.organization_id
                )
        self.fields['match_provider_account'].queryset = provider_account_queryset


_BaseRoutingIntentTemplateBindingForm = RoutingIntentTemplateBindingForm


class RoutingIntentTemplateBindingForm(_BaseRoutingIntentTemplateBindingForm):
    context_groups = DynamicModelMultipleChoiceField(
        queryset=netbox_rpki.models.RoutingIntentContextGroup.objects.all(),
        required=False,
        label='Context Groups',
        help_text='Optional context groups that gate whether this binding applies to a candidate prefix.',
    )

    fieldsets = (
        FieldSet('name', 'template', 'intent_profile', 'enabled', 'state', name='Binding'),
        FieldSet('binding_priority', 'binding_label', 'context_groups', name='Scope'),
        FieldSet(
            'origin_asn_override',
            'max_length_mode',
            'max_length_value',
            'prefix_selector_query',
            'asn_selector_query',
            name='Override Policy',
        ),
        FieldSet('comments', 'tenant', 'tags', name='Metadata'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        intent_profile_id = (
            _coerce_bound_pk(self.data.get('intent_profile'))
            or _coerce_bound_pk(self.initial.get('intent_profile'))
            or getattr(getattr(self.instance, 'intent_profile', None), 'pk', None)
        )
        template_id = (
            _coerce_bound_pk(self.data.get('template'))
            or _coerce_bound_pk(self.initial.get('template'))
            or getattr(getattr(self.instance, 'template', None), 'pk', None)
        )
        queryset = _ordered_context_group_queryset()
        organization_id = None
        if intent_profile_id is not None:
            organization_id = (
                netbox_rpki.models.RoutingIntentProfile.objects.filter(pk=intent_profile_id)
                .values_list('organization_id', flat=True)
                .first()
            )
        if organization_id is None and template_id is not None:
            organization_id = (
                netbox_rpki.models.RoutingIntentTemplate.objects.filter(pk=template_id)
                .values_list('organization_id', flat=True)
                .first()
            )
        if organization_id is not None:
            queryset = queryset.filter(organization_id=organization_id)
        self.fields['context_groups'].queryset = queryset

    def clean_context_groups(self):
        context_groups = self.cleaned_data.get('context_groups')
        intent_profile = self.cleaned_data.get('intent_profile')
        template = self.cleaned_data.get('template')
        if not context_groups:
            return context_groups
        expected_organization = None
        if intent_profile is not None:
            expected_organization = intent_profile.organization
        elif template is not None:
            expected_organization = template.organization
        if expected_organization is None:
            return context_groups
        invalid_ids = [
            group.pk
            for group in context_groups
            if group.organization_id != expected_organization.pk
        ]
        if invalid_ids:
            raise ValidationError('Context groups must belong to the same organization as the selected template binding.')
        return context_groups


def _lint_finding_label(obj):
    return (
        f'[{obj.severity}] {obj.details_json.get("rule_label", obj.finding_code)}: '
        f'{obj.details_json.get("operator_message", obj.name)}'
    )


def _build_plan_lint_ack_querysets(plan):
    empty = netbox_rpki.models.ROALintFinding.objects.none()
    if plan is None:
        return empty, empty
    posture = build_roa_change_plan_lint_posture(plan)
    latest_lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
    acknowledged_queryset = empty
    if latest_lint_run is not None:
        acknowledged_ids = set(plan.lint_acknowledgements.values_list('finding_id', flat=True))
        current_ids = [
            finding.pk
            for finding in latest_lint_run.findings.all()
            if (
                finding.details_json.get('approval_impact') == 'acknowledgement_required'
                and not finding.details_json.get('suppressed')
                and finding.pk not in acknowledged_ids
                and finding.pk not in posture.get('previously_acknowledged_finding_ids', [])
            )
        ]
        acknowledged_queryset = netbox_rpki.models.ROALintFinding.objects.filter(pk__in=current_ids)
    previous_queryset = netbox_rpki.models.ROALintFinding.objects.filter(
        pk__in=posture.get('previously_acknowledged_finding_ids', [])
    )
    return acknowledged_queryset, previous_queryset


class ROAChangePlanApprovalForm(ConfirmationForm):
    requires_secondary_approval = forms.BooleanField(
        required=False,
        label='Require a second independent approval before this plan can be applied',
        initial=False,
    )
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
    previously_acknowledged_findings = forms.ModelMultipleChoiceField(
        queryset=netbox_rpki.models.ROALintFinding.objects.none(),
        required=False,
        label='Re-Confirm Previously Acknowledged Lint Findings',
        widget=forms.CheckboxSelectMultiple,
        help_text='Select findings previously acknowledged on this plan that should be re-confirmed for the current lint run.',
    )
    acknowledged_simulation_results = forms.ModelMultipleChoiceField(
        queryset=netbox_rpki.models.ROAValidationSimulationResult.objects.none(),
        required=False,
        label='Acknowledge Approval-Required Simulation Results',
        widget=forms.CheckboxSelectMultiple,
        help_text='Select simulation results reviewed and accepted for this change plan.',
    )
    lint_acknowledgement_notes = forms.CharField(
        required=False,
        label='Lint Acknowledgement Notes',
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Optional note recorded on created lint acknowledgements.',
    )

    fieldsets = (
        FieldSet(
            'requires_secondary_approval',
            'ticket_reference',
            'change_reference',
            'maintenance_window_start',
            'maintenance_window_end',
            'approval_notes',
            'acknowledged_findings',
            'previously_acknowledged_findings',
            'acknowledged_simulation_results',
            'lint_acknowledgement_notes',
            name='Governance',
        ),
    )

    def __init__(self, *args, plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan = plan
        queryset, previous_queryset = _build_plan_lint_ack_querysets(plan)
        self.fields['acknowledged_findings'].queryset = queryset
        self.fields['acknowledged_findings'].label_from_instance = _lint_finding_label
        self.fields['previously_acknowledged_findings'].queryset = previous_queryset
        self.fields['previously_acknowledged_findings'].label_from_instance = _lint_finding_label
        if not queryset.exists():
            self.fields['acknowledged_findings'].help_text = (
                'No current unsuppressed acknowledgement-required lint findings remain to acknowledge.'
            )
        if not previous_queryset.exists():
            self.fields['previously_acknowledged_findings'].help_text = (
                'No previously acknowledged lint findings currently need re-confirmation.'
            )
        simulation_queryset = netbox_rpki.models.ROAValidationSimulationResult.objects.none()
        latest_simulation_run_id = (plan.summary_json or {}).get('simulation_run_id') if plan is not None else None
        if latest_simulation_run_id:
            latest_simulation_run = plan.simulation_runs.filter(pk=latest_simulation_run_id).first()
            if latest_simulation_run is not None:
                ack_required_ids = []
                for result in latest_simulation_run.results.all():
                    if result.approval_impact == 'acknowledgement_required':
                        ack_required_ids.append(result.pk)
                simulation_queryset = netbox_rpki.models.ROAValidationSimulationResult.objects.filter(pk__in=ack_required_ids)
                self.fields['acknowledged_simulation_results'].queryset = simulation_queryset
                self.fields['acknowledged_simulation_results'].label_from_instance = (
                    lambda obj: (
                        f'[{obj.outcome_type}] '
                        f'{obj.scenario_type or obj.details_json.get("scenario_type", obj.name)}: '
                        f'{obj.details_json.get("operator_message", obj.name)}'
                    )
                )
        if not simulation_queryset.exists():
            self.fields['acknowledged_simulation_results'].help_text = (
                'No current acknowledgement-required simulation results remain to acknowledge.'
            )

    def clean(self):
        cleaned_data = super().clean()
        validate_maintenance_window_bounds(
            start_at=cleaned_data.get('maintenance_window_start'),
            end_at=cleaned_data.get('maintenance_window_end'),
        )
        acknowledged_findings = cleaned_data.get('acknowledged_findings') or []
        if acknowledged_findings is not None:
            valid_ids = set(self.fields['acknowledged_findings'].queryset.values_list('pk', flat=True))
            selected_ids = {finding.pk for finding in acknowledged_findings}
            if not selected_ids.issubset(valid_ids):
                raise ValidationError({
                    'acknowledged_findings': 'Only current unsuppressed acknowledgement-required findings may be acknowledged.'
                })
        previously_acknowledged_findings = cleaned_data.get('previously_acknowledged_findings') or []
        if previously_acknowledged_findings is not None:
            valid_ids = set(self.fields['previously_acknowledged_findings'].queryset.values_list('pk', flat=True))
            selected_ids = {finding.pk for finding in previously_acknowledged_findings}
            if not selected_ids.issubset(valid_ids):
                raise ValidationError({
                    'previously_acknowledged_findings': (
                        'Only current previously acknowledged findings may be re-confirmed.'
                    )
                })
        acknowledged_simulation_results = cleaned_data.get('acknowledged_simulation_results')
        if acknowledged_simulation_results is not None:
            valid_ids = set(self.fields['acknowledged_simulation_results'].queryset.values_list('pk', flat=True))
            selected_ids = {result.pk for result in acknowledged_simulation_results}
            if not selected_ids.issubset(valid_ids):
                raise ValidationError({
                    'acknowledged_simulation_results': (
                        'Only current acknowledgement-required simulation results may be acknowledged.'
                    )
                })
        return cleaned_data


class ASPAChangePlanApprovalForm(ROAChangePlanApprovalForm):
    fieldsets = (
        FieldSet(
            'requires_secondary_approval',
            'ticket_reference',
            'change_reference',
            'maintenance_window_start',
            'maintenance_window_end',
            'approval_notes',
            name='Governance',
        ),
    )

    def __init__(self, *args, plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in (
            'acknowledged_findings',
            'previously_acknowledged_findings',
            'acknowledged_simulation_results',
            'lint_acknowledgement_notes',
        ):
            self.fields.pop(field_name, None)

    def clean(self):
        cleaned_data = ConfirmationForm.clean(self)
        validate_maintenance_window_bounds(
            start_at=cleaned_data.get('maintenance_window_start'),
            end_at=cleaned_data.get('maintenance_window_end'),
        )
        return cleaned_data


class RollbackBundleApprovalForm(ConfirmationForm):
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
    )
    notes = forms.CharField(
        required=False,
        label='Approval Notes',
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    fieldsets = (
        FieldSet(
            'ticket_reference',
            'change_reference',
            'maintenance_window_start',
            'maintenance_window_end',
            'notes',
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


class ChangePlanSecondaryApprovalForm(ConfirmationForm):
    approval_notes = forms.CharField(
        required=False,
        label='Approval Notes',
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    fieldsets = (
        FieldSet(
            'approval_notes',
            name='Secondary Approval',
        ),
    )


class RoutingIntentProfileRunActionForm(ConfirmationForm):
    comparison_scope = forms.ChoiceField(
        choices=netbox_rpki.models.ReconciliationComparisonScope.choices,
        initial=netbox_rpki.models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        label='Comparison Scope',
    )
    provider_snapshot = DynamicModelChoiceField(
        queryset=netbox_rpki.models.ProviderSnapshot.objects.none(),
        required=False,
        label='Provider Snapshot',
        help_text='Required when using provider-imported comparison scope.',
    )

    fieldsets = (
        FieldSet(
            'comparison_scope',
            'provider_snapshot',
            name='Execution Options',
        ),
    )

    def __init__(self, *args, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        snapshot_queryset = netbox_rpki.models.ProviderSnapshot.objects.none()
        if profile is not None:
            snapshot_queryset = netbox_rpki.models.ProviderSnapshot.objects.filter(
                organization=profile.organization
            ).order_by('name')
        self.fields['provider_snapshot'].queryset = snapshot_queryset

    def clean(self):
        cleaned_data = super().clean()
        comparison_scope = cleaned_data.get(
            'comparison_scope',
            netbox_rpki.models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        )
        provider_snapshot = cleaned_data.get('provider_snapshot')
        if (
            comparison_scope == netbox_rpki.models.ReconciliationComparisonScope.PROVIDER_IMPORTED
            and provider_snapshot is None
        ):
            raise ValidationError({'provider_snapshot': 'Provider snapshot is required for provider-imported ROA reconciliation.'})
        return cleaned_data


class ROAChangePlanLintAcknowledgementForm(ConfirmationForm):
    ticket_reference = forms.CharField(required=False, max_length=200, label='Ticket Reference')
    change_reference = forms.CharField(required=False, max_length=200, label='Change Reference')
    acknowledged_findings = forms.ModelMultipleChoiceField(
        queryset=netbox_rpki.models.ROALintFinding.objects.none(),
        required=False,
        label='Acknowledge Approval-Required Lint Findings',
        widget=forms.CheckboxSelectMultiple,
        help_text='Select current acknowledgement-required lint findings reviewed and accepted for this draft change plan.',
    )
    previously_acknowledged_findings = forms.ModelMultipleChoiceField(
        queryset=netbox_rpki.models.ROALintFinding.objects.none(),
        required=False,
        label='Re-Confirm Previously Acknowledged Lint Findings',
        widget=forms.CheckboxSelectMultiple,
        help_text='Select previously acknowledged findings that should be re-confirmed for the current lint run.',
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
            'previously_acknowledged_findings',
            'lint_acknowledgement_notes',
            name='Lint Review',
        ),
    )

    def __init__(self, *args, plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan = plan
        queryset, previous_queryset = _build_plan_lint_ack_querysets(plan)
        self.fields['acknowledged_findings'].queryset = queryset
        self.fields['acknowledged_findings'].label_from_instance = _lint_finding_label
        self.fields['previously_acknowledged_findings'].queryset = previous_queryset
        self.fields['previously_acknowledged_findings'].label_from_instance = _lint_finding_label
        if not queryset.exists():
            self.fields['acknowledged_findings'].help_text = (
                'No current unsuppressed acknowledgement-required lint findings remain to acknowledge.'
            )
        if not previous_queryset.exists():
            self.fields['previously_acknowledged_findings'].help_text = (
                'No previously acknowledged lint findings currently need re-confirmation.'
            )

    def clean(self):
        cleaned_data = super().clean()
        acknowledged_findings = cleaned_data.get('acknowledged_findings') or []
        previously_acknowledged_findings = cleaned_data.get('previously_acknowledged_findings') or []
        if not self.fields['acknowledged_findings'].queryset.exists() and acknowledged_findings:
            raise ValidationError({'acknowledged_findings': 'No current acknowledgement-required findings remain to acknowledge.'})
        if (
            not self.fields['previously_acknowledged_findings'].queryset.exists()
            and previously_acknowledged_findings
        ):
            raise ValidationError({
                'previously_acknowledged_findings': 'No previously acknowledged findings remain to re-confirm.'
            })
        if not acknowledged_findings and not previously_acknowledged_findings:
            raise ValidationError({
                'acknowledged_findings': 'Select at least one current or previously acknowledged lint finding to confirm.'
            })
        valid_ids = set(self.fields['acknowledged_findings'].queryset.values_list('pk', flat=True))
        selected_ids = {finding.pk for finding in acknowledged_findings}
        if not selected_ids.issubset(valid_ids):
            raise ValidationError({
                'acknowledged_findings': 'Only current unacknowledged acknowledgement-required findings may be acknowledged.'
            })
        valid_previous_ids = set(self.fields['previously_acknowledged_findings'].queryset.values_list('pk', flat=True))
        selected_previous_ids = {finding.pk for finding in previously_acknowledged_findings}
        if not selected_previous_ids.issubset(valid_previous_ids):
            raise ValidationError({
                'previously_acknowledged_findings': 'Only current previously acknowledged findings may be re-confirmed.'
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
                (netbox_rpki.models.ROALintSuppressionScope.ORG, 'Organization'),
                (netbox_rpki.models.ROALintSuppressionScope.PREFIX, 'Prefix'),
            ]


class ROALintSuppressionLiftForm(ConfirmationForm):
    lift_reason = forms.CharField(
        required=False,
        label='Lift Reason',
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Optional note explaining why the suppression was lifted.',
    )


class BulkIntentRunActionForm(ConfirmationForm):
    run_name = forms.CharField(required=False, max_length=200, label='Run Name')
    comparison_scope = forms.ChoiceField(
        choices=netbox_rpki.models.ReconciliationComparisonScope.choices,
        initial=netbox_rpki.models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        label='Comparison Scope',
    )
    provider_snapshot = forms.ModelChoiceField(
        queryset=netbox_rpki.models.ProviderSnapshot.objects.none(),
        required=False,
        label='Provider Snapshot',
    )
    create_change_plans = forms.BooleanField(
        required=False,
        label='Create Draft Change Plans',
        help_text='Create a draft ROA change plan for each qualifying child reconciliation result.',
    )
    profiles = forms.ModelMultipleChoiceField(
        queryset=netbox_rpki.models.RoutingIntentProfile.objects.none(),
        required=False,
        label='Intent Profiles',
        widget=forms.CheckboxSelectMultiple,
    )
    bindings = forms.ModelMultipleChoiceField(
        queryset=netbox_rpki.models.RoutingIntentTemplateBinding.objects.none(),
        required=False,
        label='Template Bindings',
        widget=forms.CheckboxSelectMultiple,
    )

    fieldsets = (
        FieldSet(
            'run_name',
            'comparison_scope',
            'provider_snapshot',
            'create_change_plans',
            'profiles',
            'bindings',
            name='Bulk Routing Intent Run',
        ),
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        profile_queryset = netbox_rpki.models.RoutingIntentProfile.objects.none()
        binding_queryset = netbox_rpki.models.RoutingIntentTemplateBinding.objects.none()
        snapshot_queryset = netbox_rpki.models.ProviderSnapshot.objects.none()
        if organization is not None:
            profile_queryset = netbox_rpki.models.RoutingIntentProfile.objects.filter(
                organization=organization
            ).order_by('name', 'pk')
            binding_queryset = netbox_rpki.models.RoutingIntentTemplateBinding.objects.filter(
                intent_profile__organization=organization
            ).select_related('template', 'intent_profile').order_by(
                'intent_profile__name',
                'binding_priority',
                'name',
                'pk',
            )
            snapshot_queryset = netbox_rpki.models.ProviderSnapshot.objects.filter(
                organization=organization
            ).order_by('-created', '-pk')

        self.fields['profiles'].queryset = profile_queryset
        self.fields['bindings'].queryset = binding_queryset
        self.fields['provider_snapshot'].queryset = snapshot_queryset
        self.fields['profiles'].label_from_instance = lambda obj: f'{obj.name} ({obj.status})'
        self.fields['bindings'].label_from_instance = (
            lambda obj: f'{obj.intent_profile.name} / {obj.template.name} / {obj.name}'
        )

    def clean(self):
        cleaned_data = super().clean()
        profiles = cleaned_data.get('profiles')
        bindings = cleaned_data.get('bindings')
        provider_snapshot = cleaned_data.get('provider_snapshot')
        if not profiles and not bindings:
            raise ValidationError('Select at least one routing intent profile or template binding.')
        if (
            self.organization is not None
            and provider_snapshot is not None
            and provider_snapshot.organization_id != self.organization.pk
        ):
            raise ValidationError({'provider_snapshot': 'Provider snapshot must belong to the selected organization.'})
        return cleaned_data


class ProviderSnapshotCompareForm(forms.Form):
    base_snapshot = DynamicModelChoiceField(
        queryset=netbox_rpki.models.ProviderSnapshot.objects.none(),
        required=False,
        label='Base Snapshot',
        help_text=(
            'Leave blank to automatically compare against the most recent preceding '
            'completed snapshot for this provider account.'
        ),
    )

    fieldsets = (
        FieldSet('base_snapshot', name='Compare Options'),
    )

    def __init__(self, *args, provider_account=None, **kwargs):
        super().__init__(*args, **kwargs)
        if provider_account is not None:
            self.fields['base_snapshot'].queryset = (
                netbox_rpki.models.ProviderSnapshot.objects
                .filter(provider_account=provider_account)
                .order_by('-completed_at', 'name')
            )
