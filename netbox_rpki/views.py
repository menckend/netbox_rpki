from datetime import date, timedelta
from types import SimpleNamespace
from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View
from netbox.object_actions import AddObject, BulkExport, CloneObject, DeleteObject, EditObject
from netbox.views import generic
from utilities.forms import ConfirmationForm
from utilities.views import ContentTypePermissionRequiredMixin

from netbox_rpki import models, forms, tables, filtersets
from netbox_rpki.jobs import RunAspaReconciliationJob, SyncProviderAccountJob
from netbox_rpki.detail_specs import (
    CERTIFICATE_DETAIL_SPEC,
    DETAIL_SPEC_BY_MODEL,
    DetailFieldSpec,
    ORGANIZATION_DETAIL_SPEC,
    ROA_DETAIL_SPEC,
)
from netbox_rpki.object_registry import SIMPLE_DETAIL_VIEW_OBJECT_SPECS, VIEW_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec
from netbox_rpki.services import (
    ProviderWriteError,
    apply_roa_change_plan_provider_write,
    approve_roa_change_plan,
    build_roa_change_plan_delta,
    preview_roa_change_plan_provider_write,
)
from netbox_rpki.services.provider_sync_contract import build_provider_account_rollup


class MetadataDrivenDetailView(generic.ObjectView):
    template_name = 'netbox_rpki/object_detail.html'
    detail_spec = None

    def get_detail_spec(self):
        if self.detail_spec is None:
            raise AttributeError(f'{self.__class__.__name__} must define detail_spec')
        return self.detail_spec

    def build_detail_field(self, field_spec, instance):
        value = field_spec.value(instance)
        url = self.resolve_detail_field_url(field_spec, instance, value)

        return {
            'kind': field_spec.kind,
            'label': field_spec.label,
            'value': value,
            'url': url,
            'use_header': field_spec.use_header,
            'empty_text': field_spec.empty_text,
            'is_empty': value in (None, ''),
        }

    def resolve_detail_field_url(self, field_spec, instance, value):
        if field_spec.kind == 'url':
            return field_spec.url(instance) if field_spec.url else value

        if field_spec.url is not None:
            return field_spec.url(instance)

        get_absolute_url = getattr(value, 'get_absolute_url', None)
        if callable(get_absolute_url):
            return get_absolute_url()

        return None

    def build_detail_action_button(self, action_spec, instance):
        if action_spec.direct_url is not None:
            return {
                'label': action_spec.label,
                'url': action_spec.direct_url(instance),
            }

        query_string = urlencode({action_spec.query_param: action_spec.value(instance)})
        return {
            'label': action_spec.label,
            'url': f'{reverse(action_spec.url_name)}?{query_string}',
        }

    def build_detail_table_section(self, request, table_spec, instance):
        table_class = getattr(tables, table_spec.table_class_name)
        table = table_class(table_spec.queryset(instance))
        table.configure(request)

        return {
            'title': table_spec.title,
            'table': table,
        }

    def build_detail_table_sections(self, request, table_specs, instance):
        sections = []

        for table_spec in table_specs:
            section = self.build_detail_table_section(request, table_spec, instance)
            sections.append(section)

        return sections

    def get_extra_context(self, request, instance):
        detail_spec = self.get_detail_spec()
        side_sections = self.build_detail_table_sections(request, detail_spec.side_tables, instance)
        bottom_sections = self.build_detail_table_sections(request, detail_spec.bottom_tables, instance)

        return {
            'detail_spec': detail_spec,
            'detail_fields': [self.build_detail_field(field_spec, instance) for field_spec in detail_spec.fields],
            'detail_action_buttons': [
                self.build_detail_action_button(action_spec, instance)
                for action_spec in detail_spec.actions
                if action_spec.visible is None or action_spec.visible(instance)
                if request.user.has_perm(action_spec.permission)
            ],
            'detail_side_sections': side_sections,
            'detail_bottom_sections': bottom_sections,
        }


class CertificateView(MetadataDrivenDetailView):
    queryset = models.Certificate.objects.all()
    detail_spec = CERTIFICATE_DETAIL_SPEC


class OrganizationView(MetadataDrivenDetailView):
    queryset = models.Organization.objects.all()
    detail_spec = ORGANIZATION_DETAIL_SPEC


class RoaView(MetadataDrivenDetailView):
    queryset = models.Roa.objects.all()
    detail_spec = ROA_DETAIL_SPEC


def build_generated_detail_field_spec(spec: ObjectSpec, field_name: str) -> DetailFieldSpec:
    model_field = spec.model._meta.get_field(field_name)
    kind = 'text'
    empty_text = None
    if getattr(model_field, 'is_relation', False):
        kind = 'link'
        empty_text = 'None'
    elif field_name.endswith(('_url', '_uri')):
        kind = 'url'

    return DetailFieldSpec(
        label=str(model_field.verbose_name).title(),
        value=lambda obj, attr=field_name: getattr(obj, attr),
        kind=kind,
        empty_text=empty_text,
    )


def build_generated_detail_spec(spec: ObjectSpec):
    custom_spec = DETAIL_SPEC_BY_MODEL.get(spec.model)
    if custom_spec is not None:
        return custom_spec

    detail_fields = tuple(
        build_generated_detail_field_spec(spec, field_name)
        for field_name in spec.api.fields
        if field_name not in {'id', 'url'}
    )
    return SimpleNamespace(
        list_url_name=spec.list_url_name,
        breadcrumb_label=spec.labels.plural,
        card_title=spec.labels.singular,
        fields=detail_fields,
        actions=(),
        side_tables=(),
        bottom_tables=(),
    )


def build_list_actions(spec: ObjectSpec):
    actions = [BulkExport]
    if spec.view.supports_create:
        actions.insert(0, AddObject)
    return tuple(actions)


def build_detail_actions(spec: ObjectSpec):
    actions = []
    if spec.view.supports_create:
        actions.extend((CloneObject, EditObject))
    if spec.view.supports_delete:
        actions.append(DeleteObject)
    return tuple(actions)


def build_list_view_class(spec: ObjectSpec) -> type[generic.ObjectListView]:
    return type(
        spec.view.list_class_name,
        (generic.ObjectListView,),
        {
            '__module__': __name__,
            'queryset': spec.model.objects.all(),
            'filterset': getattr(filtersets, spec.filterset.class_name),
            'filterset_form': getattr(forms, spec.filter_form.class_name),
            'table': getattr(tables, spec.table.class_name),
            'actions': build_list_actions(spec),
        },
    )


def build_detail_view_class(spec: ObjectSpec) -> type[MetadataDrivenDetailView]:
    return type(
        spec.view.detail_class_name,
        (MetadataDrivenDetailView,),
        {
            '__module__': __name__,
            'queryset': spec.model.objects.all(),
            'detail_spec': build_generated_detail_spec(spec),
            'actions': build_detail_actions(spec),
        },
    )


def build_edit_view_class(spec: ObjectSpec) -> type[generic.ObjectEditView]:
    if spec.view.edit_class_name is None or spec.form is None:
        raise AttributeError(f'{spec.registry_key} does not define an editable view')
    return type(
        spec.view.edit_class_name,
        (generic.ObjectEditView,),
        {
            '__module__': __name__,
            'queryset': spec.model.objects.all(),
            'form': getattr(forms, spec.form.class_name),
        },
    )


def build_delete_view_class(spec: ObjectSpec) -> type[generic.ObjectDeleteView]:
    if spec.view.delete_class_name is None:
        raise AttributeError(f'{spec.registry_key} does not define a delete view')
    return type(
        spec.view.delete_class_name,
        (generic.ObjectDeleteView,),
        {
            '__module__': __name__,
            'queryset': spec.model.objects.all(),
        },
    )


for object_spec in VIEW_OBJECT_SPECS:
    globals()[object_spec.view.list_class_name] = build_list_view_class(object_spec)
    if object_spec.view.edit_class_name is not None and object_spec.form is not None:
        globals()[object_spec.view.edit_class_name] = build_edit_view_class(object_spec)
    if object_spec.view.delete_class_name is not None:
        globals()[object_spec.view.delete_class_name] = build_delete_view_class(object_spec)


for object_spec in SIMPLE_DETAIL_VIEW_OBJECT_SPECS:
    globals()[object_spec.view.detail_class_name] = build_detail_view_class(object_spec)


class ROAChangePlanActionView(generic.ObjectEditView):
    queryset = models.ROAChangePlan.objects.all()

    def get_required_permission(self):
        return 'netbox_rpki.change_roachangeplan'

    def get_plan(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def get_requested_by(self, request) -> str:
        return getattr(request.user, 'username', '') if getattr(request.user, 'is_authenticated', False) else ''


class ProviderAccountSyncView(generic.ObjectEditView):
    queryset = models.RpkiProviderAccount.objects.all()
    template_name = 'netbox_rpki/provideraccount_sync.html'

    def get_required_permission(self):
        return 'netbox_rpki.change_rpkiprovideraccount'

    def get_provider_account(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def _render(self, request, provider_account, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': provider_account,
            'provider_account': provider_account,
            'form': form or ConfirmationForm(),
            'return_url': self.get_return_url(request, provider_account),
        }, status=status)

    def get(self, request, pk):
        provider_account = self.get_provider_account(pk)
        return self._render(request, provider_account)

    def post(self, request, pk):
        provider_account = self.get_provider_account(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, provider_account, form=form, status=400)

        if not provider_account.sync_enabled:
            messages.error(request, f'Provider account {provider_account.name} is disabled for sync.')
            return redirect(provider_account.get_absolute_url())

        job, created = SyncProviderAccountJob.enqueue_for_provider_account(
            provider_account,
            user=request.user,
        )
        if created:
            messages.success(
                request,
                f'Enqueued provider sync job {job.pk} for {provider_account.name}.',
            )
        elif job is not None:
            messages.warning(
                request,
                f'Provider sync job {job.pk} is already queued for {provider_account.name}.',
            )
        else:
            messages.warning(
                request,
                f'Provider account {provider_account.name} already has a sync in progress.',
            )
        return redirect(provider_account.get_absolute_url())


class OrganizationRunAspaReconciliationView(generic.ObjectEditView):
    queryset = models.Organization.objects.all()
    template_name = 'netbox_rpki/organization_aspa_reconcile.html'

    def get_required_permission(self):
        return 'netbox_rpki.change_organization'

    def get_organization(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def _render(self, request, organization, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': organization,
            'organization': organization,
            'form': form or ConfirmationForm(),
            'return_url': self.get_return_url(request, organization),
        }, status=status)

    def get(self, request, pk):
        organization = self.get_organization(pk)
        return self._render(request, organization)

    def post(self, request, pk):
        organization = self.get_organization(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, organization, form=form, status=400)

        job, created = RunAspaReconciliationJob.enqueue_for_organization(
            organization,
            user=request.user,
        )
        if created:
            messages.success(
                request,
                f'Enqueued ASPA reconciliation job {job.pk} for {organization.name}.',
            )
        elif job is not None:
            messages.warning(
                request,
                f'ASPA reconciliation job {job.pk} is already queued for {organization.name}.',
            )
        else:
            messages.warning(
                request,
                f'Organization {organization.name} already has an ASPA reconciliation in progress.',
            )
        return redirect(organization.get_absolute_url())


class OperationsDashboardView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/operations_dashboard.html'
    expiry_window_days = 30
    additional_permissions = [
        'netbox_rpki.view_roa',
        'netbox_rpki.view_certificate',
        'netbox_rpki.view_roareconciliationrun',
        'netbox_rpki.view_roachangeplan',
    ]
    provider_health_priority = {
        models.ProviderSyncHealth.FAILED: 0,
        models.ProviderSyncHealth.STALE: 1,
    }

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request):
        today = date.today()
        expiry_threshold = today + timedelta(days=self.expiry_window_days)
        provider_accounts = self.get_provider_accounts(request)
        expiring_roas = self.get_expiring_roas(request, today=today, expiry_threshold=expiry_threshold)
        expiring_certificates = self.get_expiring_certificates(
            request,
            today=today,
            expiry_threshold=expiry_threshold,
        )
        reconciliation_attention_runs = self.get_reconciliation_attention_runs(request)
        change_plans_requiring_attention = self.get_change_plans_requiring_attention(request)

        return render(request, self.template_name, {
            'provider_accounts': provider_accounts,
            'expiring_roas': expiring_roas,
            'expiring_certificates': expiring_certificates,
            'reconciliation_attention_runs': reconciliation_attention_runs,
            'change_plans_requiring_attention': change_plans_requiring_attention,
            'expiry_window_days': self.expiry_window_days,
            'expiry_threshold': expiry_threshold,
        })

    def get_provider_accounts(self, request):
        attention_healths = {
            models.ProviderSyncHealth.FAILED,
            models.ProviderSyncHealth.STALE,
        }
        provider_queryset = models.RpkiProviderAccount.objects.restrict(request.user, 'view').select_related('organization')
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_queryset)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_queryset)
            .values_list('pk', flat=True)
        )
        provider_accounts = [
            self.build_provider_account_dashboard_row(
                provider_account,
                visible_snapshot_ids=visible_snapshot_ids,
                visible_diff_ids=visible_diff_ids,
            )
            for provider_account in provider_queryset
            if provider_account.sync_enabled and provider_account.sync_health in attention_healths
        ]
        provider_accounts.sort(key=self.get_provider_account_sort_key)
        return provider_accounts

    def build_provider_account_dashboard_row(self, provider_account, *, visible_snapshot_ids=None, visible_diff_ids=None):
        rollup = build_provider_account_rollup(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        rollup['family_status_text'] = self.get_family_status_text(rollup)
        rollup['freshness_text'] = self.get_freshness_text(provider_account, rollup)
        rollup['latest_snapshot_url'] = self.get_summary_url('plugins:netbox_rpki:providersnapshot', rollup['latest_snapshot_id'])
        rollup['latest_diff_url'] = self.get_summary_url('plugins:netbox_rpki:providersnapshotdiff', rollup['latest_diff_id'])
        rollup['latest_snapshot_label'] = rollup['latest_snapshot_name'] or 'Latest snapshot'
        rollup['latest_diff_label'] = rollup['latest_diff_name'] or 'Latest diff'
        provider_account.last_sync_rollup = rollup
        return provider_account

    def get_summary_url(self, view_name, object_id):
        if object_id in (None, ''):
            return ''
        return reverse(view_name, kwargs={'pk': object_id})

    def get_family_status_text(self, rollup):
        status_counts = rollup.get('family_status_counts', {})
        if not status_counts:
            return 'No family summary available'
        ordered_statuses = [
            models.ProviderSyncFamilyStatus.COMPLETED,
            models.ProviderSyncFamilyStatus.LIMITED,
            models.ProviderSyncFamilyStatus.PENDING,
            models.ProviderSyncFamilyStatus.RUNNING,
            models.ProviderSyncFamilyStatus.FAILED,
            models.ProviderSyncFamilyStatus.SKIPPED,
            models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED,
        ]
        parts = [f"{status_counts[status]} {status.replace('_', ' ')}" for status in ordered_statuses if status_counts.get(status)]
        return f"{rollup.get('family_count', 0)} families: {', '.join(parts)}"

    def get_freshness_text(self, provider_account, rollup):
        if not provider_account.sync_enabled:
            return 'Sync disabled'
        if provider_account.last_successful_sync is None:
            return 'Never synced'
        next_sync_due_at = rollup.get('next_sync_due_at')
        if next_sync_due_at:
            return f'Next due {next_sync_due_at}'
        return f'Last synced {provider_account.last_successful_sync}'

    def get_provider_account_sort_key(self, provider_account):
        last_successful_sync_timestamp = (
            provider_account.last_successful_sync.timestamp()
            if provider_account.last_successful_sync is not None
            else float('-inf')
        )
        return (
            self.provider_health_priority.get(provider_account.sync_health, 99),
            last_successful_sync_timestamp,
            provider_account.name.lower(),
        )

    def get_expiring_roas(self, request, *, today, expiry_threshold):
        queryset = models.Roa.objects.restrict(request.user, 'view').select_related(
            'origin_as',
            'signed_by',
            'signed_by__rpki_org',
        ).filter(
            valid_to__isnull=False,
            valid_to__lte=expiry_threshold,
        ).order_by('valid_to', 'name')
        return [
            {
                'object': roa,
                'organization': roa.signed_by.rpki_org,
                'related_object': roa.signed_by,
                'expiry_text': self.get_expiry_text(roa.valid_to, today=today),
                'expiry_badge_class': self.get_expiry_badge_class(roa.valid_to, today=today),
            }
            for roa in queryset
        ]

    def get_expiring_certificates(self, request, *, today, expiry_threshold):
        queryset = models.Certificate.objects.restrict(request.user, 'view').select_related('rpki_org').filter(
            valid_to__isnull=False,
            valid_to__lte=expiry_threshold,
        ).order_by('valid_to', 'name')
        return [
            {
                'object': certificate,
                'organization': certificate.rpki_org,
                'expiry_text': self.get_expiry_text(certificate.valid_to, today=today),
                'expiry_badge_class': self.get_expiry_badge_class(certificate.valid_to, today=today),
            }
            for certificate in queryset
        ]

    def get_reconciliation_attention_runs(self, request):
        queryset = (
            models.ROAReconciliationRun.objects.restrict(request.user, 'view')
            .select_related('organization', 'intent_profile', 'provider_snapshot')
            .prefetch_related('lint_runs')
        )
        runs = []
        for run in queryset:
            summary = dict(run.result_summary_json or {})
            lint_run = run.lint_runs.order_by('-started_at', '-created').first()
            replacement_count = summary.get('replacement_required_intent_count', 0)
            warning_count = getattr(lint_run, 'warning_count', 0)
            error_count = getattr(lint_run, 'error_count', 0) + getattr(lint_run, 'critical_count', 0)
            if run.status != models.ValidationRunStatus.COMPLETED and replacement_count == 0 and warning_count == 0 and error_count == 0:
                continue
            if replacement_count == 0 and warning_count == 0 and error_count == 0:
                continue
            runs.append({
                'object': run,
                'replacement_count': replacement_count,
                'warning_count': warning_count,
                'error_count': error_count,
                'lint_run': lint_run,
            })
        runs.sort(
            key=lambda item: (
                item['error_count'],
                item['warning_count'],
                item['replacement_count'],
                (item['object'].completed_at or item['object'].started_at or timezone.now()).timestamp(),
            ),
            reverse=True,
        )
        return runs[:10]

    def get_change_plans_requiring_attention(self, request):
        queryset = (
            models.ROAChangePlan.objects.restrict(request.user, 'view')
            .select_related('organization', 'provider_account', 'source_reconciliation_run')
            .prefetch_related('simulation_runs', 'lint_runs')
        )
        attention_statuses = {
            models.ROAChangePlanStatus.DRAFT,
            models.ROAChangePlanStatus.APPROVED,
            models.ROAChangePlanStatus.FAILED,
        }
        plans = []
        for plan in queryset:
            if plan.status not in attention_statuses:
                continue
            latest_simulation = plan.simulation_runs.order_by('-started_at', '-created').first()
            latest_lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
            plans.append({
                'object': plan,
                'replacement_count': (plan.summary_json or {}).get('replacement_count', 0),
                'warning_count': getattr(latest_lint_run, 'warning_count', 0),
                'error_count': getattr(latest_lint_run, 'error_count', 0) + getattr(latest_lint_run, 'critical_count', 0),
                'simulation_run': latest_simulation,
                'lint_run': latest_lint_run,
            })
        plans.sort(
            key=lambda item: (
                item['object'].status == models.ROAChangePlanStatus.FAILED,
                item['error_count'],
                item['warning_count'],
                item['replacement_count'],
                item['object'].created.timestamp(),
            ),
            reverse=True,
        )
        return plans[:10]

    def get_expiry_text(self, valid_to, *, today):
        days_remaining = (valid_to - today).days
        if days_remaining < 0:
            return f'Expired {-days_remaining} day(s) ago'
        if days_remaining == 0:
            return 'Expires today'
        return f'Expires in {days_remaining} day(s)'

    def get_expiry_badge_class(self, valid_to, *, today):
        days_remaining = (valid_to - today).days
        if days_remaining < 0:
            return 'danger'
        if days_remaining <= 7:
            return 'warning text-dark'
        return 'info'


class ROAChangePlanPreviewView(ROAChangePlanActionView):
    template_name = 'netbox_rpki/roachangeplan_preview.html'

    def _render(self, request, plan, *, execution=None, error_text=None, status=200):
        try:
            delta = build_roa_change_plan_delta(plan)
        except ProviderWriteError as exc:
            delta = None
            error_text = error_text or str(exc)
            status = 400

        return render(request, self.template_name, {
            'object': plan,
            'change_plan': plan,
            'delta': delta,
            'execution': execution,
            'error_text': error_text,
            'form': ConfirmationForm(),
            'return_url': self.get_return_url(request, plan),
        }, status=status)

    def get(self, request, pk):
        plan = self.get_plan(pk)
        return self._render(request, plan)

    def post(self, request, pk):
        plan = self.get_plan(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, plan, status=400)

        try:
            execution, _ = preview_roa_change_plan_provider_write(
                plan,
                requested_by=self.get_requested_by(request),
            )
        except ProviderWriteError as exc:
            return self._render(request, plan, error_text=str(exc), status=400)

        messages.success(request, f'Recorded provider preview execution {execution.name}.')
        return self._render(request, plan, execution=execution)


class ROAChangePlanApproveView(ROAChangePlanActionView):
    template_name = 'netbox_rpki/roachangeplan_confirm.html'
    action_label = 'Approve'
    button_class = 'primary'

    def get_form(self, data=None, *, plan):
        initial = {
            'ticket_reference': plan.ticket_reference,
            'change_reference': plan.change_reference,
            'maintenance_window_start': plan.maintenance_window_start,
            'maintenance_window_end': plan.maintenance_window_end,
        }
        return forms.ROAChangePlanApprovalForm(data=data, initial=initial)

    def _render(self, request, plan, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': plan,
            'change_plan': plan,
            'form': form or self.get_form(plan=plan),
            'return_url': self.get_return_url(request, plan),
            'action_label': self.action_label,
            'button_class': self.button_class,
            'show_governance_inputs': True,
        }, status=status)

    def get(self, request, pk):
        plan = self.get_plan(pk)
        return self._render(request, plan)

    def post(self, request, pk):
        plan = self.get_plan(pk)
        form = self.get_form(request.POST, plan=plan)
        if not form.is_valid():
            return self._render(request, plan, form=form, status=400)

        try:
            approve_roa_change_plan(
                plan,
                approved_by=self.get_requested_by(request),
                ticket_reference=form.cleaned_data['ticket_reference'],
                change_reference=form.cleaned_data['change_reference'],
                maintenance_window_start=form.cleaned_data['maintenance_window_start'],
                maintenance_window_end=form.cleaned_data['maintenance_window_end'],
                approval_notes=form.cleaned_data['approval_notes'],
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(plan.get_absolute_url())

        messages.success(request, f'Approved ROA change plan {plan.name}.')
        return redirect(plan.get_absolute_url())


class ROAChangePlanApplyView(ROAChangePlanActionView):
    template_name = 'netbox_rpki/roachangeplan_confirm.html'
    action_label = 'Apply'
    button_class = 'success'

    def get(self, request, pk):
        plan = self.get_plan(pk)
        try:
            delta = build_roa_change_plan_delta(plan)
        except ProviderWriteError:
            delta = None
        return render(request, self.template_name, {
            'object': plan,
            'change_plan': plan,
            'delta': delta,
            'form': ConfirmationForm(),
            'return_url': self.get_return_url(request, plan),
            'action_label': self.action_label,
            'button_class': self.button_class,
            'show_governance_inputs': False,
        })

    def post(self, request, pk):
        plan = self.get_plan(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'object': plan,
                'change_plan': plan,
                'form': form,
                'return_url': self.get_return_url(request, plan),
                'action_label': self.action_label,
                'button_class': self.button_class,
                'show_governance_inputs': False,
            }, status=400)

        try:
            execution, _ = apply_roa_change_plan_provider_write(
                plan,
                requested_by=self.get_requested_by(request),
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(plan.get_absolute_url())

        if execution.status == models.ValidationRunStatus.COMPLETED:
            messages.success(request, f'Applied ROA change plan {plan.name}.')
        else:
            messages.warning(
                request,
                f'Applied ROA change plan {plan.name}, but the follow-up provider sync did not complete successfully.',
            )
        return redirect(plan.get_absolute_url())
