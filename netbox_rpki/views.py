from datetime import date, timedelta
from types import SimpleNamespace
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View
from netbox.object_actions import AddObject, BulkExport, CloneObject, DeleteObject, EditObject
from netbox.views import generic
from utilities.forms import ConfirmationForm
from utilities.views import ContentTypePermissionRequiredMixin

from netbox_rpki import models, forms, tables, filtersets
from netbox_rpki.jobs import RunAspaReconciliationJob, RunBulkRoutingIntentJob, RunRoutingIntentProfileJob, SyncProviderAccountJob
from netbox_rpki.detail_specs import (
    CERTIFICATE_DETAIL_SPEC,
    DETAIL_SPEC_BY_MODEL,
    DetailFieldSpec,
    ORGANIZATION_DETAIL_SPEC,
    ROA_DETAIL_SPEC,
    ROUTING_INTENT_TEMPLATE_BINDING_DETAIL_SPEC,
)
from netbox_rpki.object_registry import SIMPLE_DETAIL_VIEW_OBJECT_SPECS, VIEW_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec
from netbox_rpki.services import (
    ProviderWriteError,
    acknowledge_roa_lint_findings,
    apply_aspa_rollback_bundle,
    apply_aspa_change_plan_provider_write,
    apply_roa_rollback_bundle,
    apply_roa_change_plan_provider_write,
    approve_bulk_intent_run,
    approve_rollback_bundle,
    approve_aspa_change_plan,
    approve_aspa_change_plan_secondary,
    build_aspa_change_plan_delta,
    build_roa_change_plan_lint_posture,
    build_roa_change_plan_simulation_posture,
    build_external_mismatch_items,
    build_telemetry_source_attention_items,
    build_validation_run_attention_items,
    build_validator_instance_attention_items,
    approve_delegated_publication_workflow,
    approve_roa_change_plan,
    approve_roa_change_plan_secondary,
    build_roa_change_plan_delta,
    create_aspa_change_plan,
    create_roa_change_plan,
    lift_roa_lint_suppression,
    preview_routing_intent_template_binding,
    preview_aspa_change_plan_provider_write,
    preview_roa_change_plan_provider_write,
    build_telemetry_run_history_summary,
    build_validator_run_history_summary,
    run_routing_intent_template_binding_pipeline,
    secondary_approve_bulk_intent_run,
    simulate_roa_change_plan,
    suppress_roa_lint_finding,
)
from netbox_rpki.services.lifecycle_reporting import (
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY,
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY,
    LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE,
    build_provider_lifecycle_health_summary,
    build_provider_lifecycle_timeline,
    build_provider_publication_diff_timeline,
    build_lifecycle_export_response,
    get_effective_lifecycle_thresholds,
    get_lifecycle_export_filename,
    is_within_lifecycle_expiry_threshold,
)
from netbox_rpki.services.provider_sync_contract import build_provider_account_rollup
from netbox_rpki.services.provider_sync_contract import build_provider_account_summary
from netbox_rpki.services.provider_sync_diff import (
    build_latest_provider_snapshot_diff,
    build_provider_snapshot_diff,
)


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


class ASPAChangePlanActionView(generic.ObjectEditView):
    queryset = models.ASPAChangePlan.objects.all()

    def get_required_permission(self):
        return 'netbox_rpki.change_aspachangeplan'

    def get_plan(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def get_requested_by(self, request) -> str:
        return getattr(request.user, 'username', '') if getattr(request.user, 'is_authenticated', False) else ''


class ROARollbackBundleActionView(generic.ObjectEditView):
    queryset = models.ROAChangePlanRollbackBundle.objects.all()

    def get_required_permission(self):
        return 'netbox_rpki.change_roachangeplanrollbackbundle'

    def get_bundle(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def get_requested_by(self, request) -> str:
        return getattr(request.user, 'username', '') if getattr(request.user, 'is_authenticated', False) else ''


class ASPARollbackBundleActionView(generic.ObjectEditView):
    queryset = models.ASPAChangePlanRollbackBundle.objects.all()

    def get_required_permission(self):
        return 'netbox_rpki.change_aspachangeplanrollbackbundle'

    def get_bundle(self, pk):
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


class LifecycleExportViewMixin:
    export_formats = {'json', 'csv'}

    def get_export_format(self, request):
        export_format = request.GET.get('format', 'json').lower()
        if export_format not in self.export_formats:
            return None
        return export_format

    def export_response(self, *, kind, data, export_format, provider_account=None, filters=None):
        try:
            return build_lifecycle_export_response(
                kind,
                data,
                export_format,
                provider_account=provider_account,
                filters=filters,
            )
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))


class OperationsDashboardExportView(LifecycleExportViewMixin, ContentTypePermissionRequiredMixin, View):
    additional_permissions = [
        'netbox_rpki.view_roa',
        'netbox_rpki.view_certificate',
        'netbox_rpki.view_routingintenttemplatebinding',
        'netbox_rpki.view_routingintentexception',
        'netbox_rpki.view_externalmanagementexception',
        'netbox_rpki.view_bulkintentrun',
        'netbox_rpki.view_roareconciliationrun',
        'netbox_rpki.view_roachangeplan',
        'netbox_rpki.view_aspareconciliationrun',
        'netbox_rpki.view_aspachangeplan',
        'netbox_rpki.view_validatorinstance',
        'netbox_rpki.view_validationrun',
        'netbox_rpki.view_telemetrysource',
        'netbox_rpki.view_irrsource',
        'netbox_rpki.view_irrcoordinationrun',
        'netbox_rpki.view_irrchangeplan',
        'netbox_rpki.view_irrwriteexecution',
    ]

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request):
        dashboard_view = OperationsDashboardView()
        export_format = self.get_export_format(request)
        if export_format is None:
            return HttpResponseBadRequest('Unsupported export format.')

        provider_accounts = dashboard_view.get_provider_accounts(request)
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account__in=[item.pk for item in provider_accounts])
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account__in=[item.pk for item in provider_accounts])
            .values_list('pk', flat=True)
        )
        summary = build_provider_account_summary(
            provider_accounts,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        return self.export_response(
            kind=LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_SUMMARY,
            data=summary,
            export_format=export_format,
            filters={'view': 'operations_dashboard'},
        )


class ProviderAccountLifecycleExportView(LifecycleExportViewMixin, View):
    def get_provider_account(self, request, pk):
        queryset = models.RpkiProviderAccount.objects.restrict(request.user, 'view').select_related('organization')
        return get_object_or_404(queryset, pk=pk)

    def get(self, request, pk):
        export_format = self.get_export_format(request)
        if export_format is None:
            return HttpResponseBadRequest('Unsupported export format.')

        provider_account = self.get_provider_account(request, pk)
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        summary = build_provider_lifecycle_health_summary(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        return self.export_response(
            kind=LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_LIFECYCLE_SUMMARY,
            data=summary,
            export_format=export_format,
            provider_account=provider_account,
            filters={'provider_account_id': provider_account.pk},
        )


class ProviderAccountTimelineExportView(LifecycleExportViewMixin, View):
    def get_provider_account(self, request, pk):
        queryset = models.RpkiProviderAccount.objects.restrict(request.user, 'view').select_related('organization')
        return get_object_or_404(queryset, pk=pk)

    def get(self, request, pk):
        export_format = self.get_export_format(request)
        if export_format is None:
            return HttpResponseBadRequest('Unsupported export format.')

        provider_account = self.get_provider_account(request, pk)
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        timeline = build_provider_lifecycle_timeline(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        return self.export_response(
            kind=LIFECYCLE_EXPORT_KIND_PROVIDER_ACCOUNT_TIMELINE,
            data=timeline,
            export_format=export_format,
            provider_account=provider_account,
            filters={'provider_account_id': provider_account.pk},
        )


class ProviderAccountTimelineView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/provideraccount_timeline.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request, pk):
        queryset = models.RpkiProviderAccount.objects.restrict(request.user, 'view')
        provider_account = get_object_or_404(queryset, pk=pk)
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        timeline = build_provider_lifecycle_timeline(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        return render(request, self.template_name, {
            'object': provider_account,
            'provider_account': provider_account,
            'timeline': timeline,
            'return_url': provider_account.get_absolute_url(),
        })


class ProviderAccountPublicationDiffSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/provideraccount_publication_diff_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request, pk):
        queryset = models.RpkiProviderAccount.objects.restrict(request.user, 'view')
        provider_account = get_object_or_404(queryset, pk=pk)
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        diff_summary = build_provider_publication_diff_timeline(
            provider_account,
            visible_diff_ids=visible_diff_ids,
        )
        return render(request, self.template_name, {
            'object': provider_account,
            'provider_account': provider_account,
            'diff_summary': diff_summary,
            'return_url': provider_account.get_absolute_url(),
        })


class ProviderAccountSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/provideraccount_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request):
        provider_accounts = list(
            models.RpkiProviderAccount.objects.restrict(request.user, 'view')
        )
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_accounts)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_accounts)
            .values_list('pk', flat=True)
        )
        summary = build_provider_account_summary(
            provider_accounts,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        return render(request, self.template_name, {
            'summary': summary,
            'provider_account_count': len(provider_accounts),
            'return_url': reverse('plugins:netbox_rpki:provideraccount_list'),
        })


class ProviderSnapshotCompareView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/providersnapshot_compare.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_providersnapshot'

    def _get_snapshot(self, request, pk):
        queryset = models.ProviderSnapshot.objects.restrict(request.user, 'view')
        return get_object_or_404(queryset, pk=pk)

    def _render(self, request, snapshot, *, form=None, error_text=None, status=200):
        return render(request, self.template_name, {
            'object': snapshot,
            'snapshot': snapshot,
            'form': form or forms.ProviderSnapshotCompareForm(provider_account=snapshot.provider_account),
            'error_text': error_text,
            'return_url': snapshot.get_absolute_url(),
        }, status=status)

    def get(self, request, pk):
        snapshot = self._get_snapshot(request, pk)
        return self._render(request, snapshot)

    def post(self, request, pk):
        snapshot = self._get_snapshot(request, pk)
        form = forms.ProviderSnapshotCompareForm(request.POST, provider_account=snapshot.provider_account)
        if not form.is_valid():
            return self._render(request, snapshot, form=form, status=400)

        base_snapshot = form.cleaned_data.get('base_snapshot')
        error_text = None
        diff = None
        try:
            if base_snapshot is None:
                diff = build_latest_provider_snapshot_diff(snapshot)
                if diff is None:
                    error_text = 'No earlier completed snapshot is available for comparison.'
            else:
                diff = build_provider_snapshot_diff(
                    base_snapshot=base_snapshot,
                    comparison_snapshot=snapshot,
                )
        except ValueError as exc:
            error_text = str(exc)

        if diff is not None:
            messages.success(request, f'Created snapshot diff {diff}.')
            return redirect(diff.get_absolute_url())
        return self._render(request, snapshot, form=form, error_text=error_text)


class ProviderSnapshotSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/providersnapshot_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_providersnapshot'

    def get(self, request):
        queryset = models.ProviderSnapshot.objects.restrict(request.user, 'view')
        by_status: dict[str, int] = {}
        latest_completed_at = None
        with_diff_count = 0
        for snapshot in queryset:
            by_status[snapshot.status] = by_status.get(snapshot.status, 0) + 1
            if snapshot.completed_at is not None and (
                latest_completed_at is None or snapshot.completed_at > latest_completed_at
            ):
                latest_completed_at = snapshot.completed_at
            if snapshot.diffs_as_comparison.exists():
                with_diff_count += 1
        return render(request, self.template_name, {
            'total_snapshots': queryset.count(),
            'by_status': by_status,
            'with_diff_count': with_diff_count,
            'latest_completed_at': latest_completed_at,
            'return_url': reverse('plugins:netbox_rpki:providersnapshot_list'),
        })


class ROAReconciliationRunSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/roareconciliationrun_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_roareconciliationrun'

    def get(self, request):
        queryset = models.ROAReconciliationRun.objects.restrict(request.user, 'view')
        total_runs = queryset.count()
        completed_runs = 0
        replacement_required_intent_total = 0
        replacement_required_published_total = 0
        lint_warning_total = 0
        lint_error_total = 0
        for run in queryset.prefetch_related('lint_runs'):
            if run.status == models.ValidationRunStatus.COMPLETED:
                completed_runs += 1
            summary = dict(run.result_summary_json or {})
            replacement_required_intent_total += summary.get('replacement_required_intent_count', 0)
            replacement_required_published_total += summary.get('replacement_required_published_count', 0)
            lint_run = run.lint_runs.order_by('-started_at', '-created').first()
            if lint_run is not None:
                lint_warning_total += lint_run.warning_count
                lint_error_total += lint_run.error_count + lint_run.critical_count
        return render(request, self.template_name, {
            'total_runs': total_runs,
            'completed_runs': completed_runs,
            'replacement_required_intent_total': replacement_required_intent_total,
            'replacement_required_published_total': replacement_required_published_total,
            'lint_warning_total': lint_warning_total,
            'lint_error_total': lint_error_total,
            'return_url': reverse('plugins:netbox_rpki:roareconciliationrun_list'),
        })


class ASPAReconciliationRunSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/aspareconciliationrun_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_aspareconciliationrun'

    def get(self, request):
        queryset = models.ASPAReconciliationRun.objects.restrict(request.user, 'view')
        total_runs = queryset.count()
        completed_runs = 0
        missing_count = 0
        missing_provider_count = 0
        extra_provider_count = 0
        orphaned_count = 0
        stale_count = 0
        for run in queryset:
            if run.status == models.ValidationRunStatus.COMPLETED:
                completed_runs += 1
            summary = dict(run.result_summary_json or {})
            intent_types = dict(summary.get('intent_result_types') or {})
            published_types = dict(summary.get('published_result_types') or {})
            missing_count += intent_types.get(models.ASPAIntentResultType.MISSING, 0)
            missing_provider_count += intent_types.get(models.ASPAIntentResultType.MISSING_PROVIDER, 0)
            extra_provider_count += published_types.get(models.PublishedASPAResultType.EXTRA_PROVIDER, 0)
            orphaned_count += published_types.get(models.PublishedASPAResultType.ORPHANED, 0)
            stale_count += (
                intent_types.get(models.ASPAIntentResultType.STALE, 0)
                + published_types.get(models.PublishedASPAResultType.STALE, 0)
            )
        return render(request, self.template_name, {
            'total_runs': total_runs,
            'completed_runs': completed_runs,
            'missing_count': missing_count,
            'missing_provider_count': missing_provider_count,
            'extra_provider_count': extra_provider_count,
            'orphaned_count': orphaned_count,
            'stale_count': stale_count,
            'return_url': reverse('plugins:netbox_rpki:aspareconciliationrun_list'),
        })


class ROAChangePlanSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/roachangeplan_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_roachangeplan'

    def get(self, request):
        queryset = models.ROAChangePlan.objects.restrict(request.user, 'view')
        by_status: dict[str, int] = {}
        provider_backed_count = 0
        replacement_count_total = 0
        simulated_plan_count = 0
        simulation_current_plan_count = 0
        simulation_missing_count = 0
        simulation_pending_count = 0
        simulation_stale_count = 0
        simulation_blocking_plan_count = 0
        simulation_ack_required_plan_count = 0
        simulation_informational_plan_count = 0
        simulation_partially_constrained_plan_count = 0
        simulation_status_counts: dict[str, int] = {}
        simulation_approval_impact_totals = {
            models.ROAValidationSimulationApprovalImpact.INFORMATIONAL: 0,
            models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED: 0,
            models.ROAValidationSimulationApprovalImpact.BLOCKING: 0,
        }
        lint_warning_total = 0
        lint_error_total = 0
        lint_blocking_total = 0
        lint_ack_required_total = 0
        lint_acknowledged_total = 0
        lint_suppressed_total = 0
        lint_previously_acknowledged_total = 0
        lint_status_counts: dict[str, int] = {}
        for plan in queryset.prefetch_related('simulation_runs', 'lint_runs'):
            by_status[plan.status] = by_status.get(plan.status, 0) + 1
            if plan.is_provider_backed:
                provider_backed_count += 1
            replacement_count_total += (plan.summary_json or {}).get('replacement_count', 0)
            simulation_posture = build_roa_change_plan_simulation_posture(plan)
            if simulation_posture['has_simulation']:
                simulated_plan_count += 1
            if simulation_posture['is_current_for_plan']:
                simulation_current_plan_count += 1
            if simulation_posture['partially_constrained']:
                simulation_partially_constrained_plan_count += 1
            simulation_status = simulation_posture['status']
            simulation_status_counts[simulation_status] = simulation_status_counts.get(simulation_status, 0) + 1
            if simulation_status == 'missing':
                simulation_missing_count += 1
            elif simulation_status == 'pending':
                simulation_pending_count += 1
            elif simulation_status == 'stale':
                simulation_stale_count += 1
            elif simulation_status == models.ROAValidationSimulationApprovalImpact.BLOCKING:
                simulation_blocking_plan_count += 1
            elif simulation_status == models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED:
                simulation_ack_required_plan_count += 1
            elif simulation_status == models.ROAValidationSimulationApprovalImpact.INFORMATIONAL:
                simulation_informational_plan_count += 1
            for impact, count in (simulation_posture['approval_impact_counts'] or {}).items():
                simulation_approval_impact_totals[impact] = simulation_approval_impact_totals.get(impact, 0) + count
            lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
            if lint_run is not None:
                lint_warning_total += lint_run.warning_count
                lint_error_total += lint_run.error_count + lint_run.critical_count
            lint_posture = build_roa_change_plan_lint_posture(plan)
            lint_blocking_total += lint_posture['unresolved_blocking_finding_count']
            lint_ack_required_total += lint_posture['unresolved_acknowledgement_required_finding_count']
            lint_acknowledged_total += lint_posture['acknowledged_finding_count']
            lint_suppressed_total += lint_posture['suppressed_finding_count']
            lint_previously_acknowledged_total += lint_posture.get('previously_acknowledged_finding_count', 0)
            lint_status = lint_posture['status']
            lint_status_counts[lint_status] = lint_status_counts.get(lint_status, 0) + 1
        return render(request, self.template_name, {
            'total_plans': queryset.count(),
            'by_status': by_status,
            'provider_backed_count': provider_backed_count,
            'replacement_count_total': replacement_count_total,
            'simulated_plan_count': simulated_plan_count,
            'simulation_current_plan_count': simulation_current_plan_count,
            'simulation_missing_count': simulation_missing_count,
            'simulation_pending_count': simulation_pending_count,
            'simulation_stale_count': simulation_stale_count,
            'simulation_blocking_plan_count': simulation_blocking_plan_count,
            'simulation_acknowledgement_required_plan_count': simulation_ack_required_plan_count,
            'simulation_informational_plan_count': simulation_informational_plan_count,
            'simulation_partially_constrained_plan_count': simulation_partially_constrained_plan_count,
            'simulation_status_counts': simulation_status_counts,
            'simulation_approval_impact_totals': simulation_approval_impact_totals,
            'lint_warning_total': lint_warning_total,
            'lint_error_total': lint_error_total,
            'lint_blocking_total': lint_blocking_total,
            'lint_acknowledgement_required_total': lint_ack_required_total,
            'lint_acknowledged_total': lint_acknowledged_total,
            'lint_suppressed_total': lint_suppressed_total,
            'lint_previously_acknowledged_total': lint_previously_acknowledged_total,
            'lint_status_counts': lint_status_counts,
            'return_url': reverse('plugins:netbox_rpki:roachangeplan_list'),
        })


class ASPAChangePlanSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/aspachangeplan_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_aspachangeplan'

    def get(self, request):
        queryset = models.ASPAChangePlan.objects.restrict(request.user, 'view')
        by_status: dict[str, int] = {}
        provider_backed_count = 0
        replacement_count_total = 0
        provider_add_count_total = 0
        provider_remove_count_total = 0
        for plan in queryset:
            by_status[plan.status] = by_status.get(plan.status, 0) + 1
            if plan.is_provider_backed:
                provider_backed_count += 1
            summary = dict(plan.summary_json or {})
            replacement_count_total += summary.get('replacement_count', 0)
            provider_add_count_total += summary.get('provider_add_count', 0)
            provider_remove_count_total += summary.get('provider_remove_count', 0)
        return render(request, self.template_name, {
            'total_plans': queryset.count(),
            'by_status': by_status,
            'provider_backed_count': provider_backed_count,
            'replacement_count_total': replacement_count_total,
            'provider_add_count_total': provider_add_count_total,
            'provider_remove_count_total': provider_remove_count_total,
            'return_url': reverse('plugins:netbox_rpki:aspachangeplan_list'),
        })


class ValidatorInstanceHistorySummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/validatorinstance_history_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_validatorinstance'

    def get(self, request, pk):
        queryset = models.ValidatorInstance.objects.restrict(request.user, 'view')
        validator = get_object_or_404(queryset, pk=pk)
        history = build_validator_run_history_summary(validator)
        return render(request, self.template_name, {
            'object': validator,
            'validator': validator,
            'history': history,
            'return_url': validator.get_absolute_url(),
        })


class TelemetrySourceHistorySummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/telemetrysource_history_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_telemetrysource'

    def get(self, request, pk):
        queryset = models.TelemetrySource.objects.restrict(request.user, 'view')
        source = get_object_or_404(queryset, pk=pk)
        history = build_telemetry_run_history_summary(source)
        return render(request, self.template_name, {
            'object': source,
            'telemetry_source': source,
            'history': history,
            'return_url': source.get_absolute_url(),
        })


class ProviderAccountTimelineView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/provideraccount_timeline.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request, pk):
        queryset = models.RpkiProviderAccount.objects.restrict(request.user, 'view')
        provider_account = get_object_or_404(queryset, pk=pk)
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        timeline = build_provider_lifecycle_timeline(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        return render(request, self.template_name, {
            'object': provider_account,
            'provider_account': provider_account,
            'timeline': timeline,
            'return_url': provider_account.get_absolute_url(),
        })


class ProviderAccountPublicationDiffSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/provideraccount_publication_diff_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request, pk):
        queryset = models.RpkiProviderAccount.objects.restrict(request.user, 'view')
        provider_account = get_object_or_404(queryset, pk=pk)
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account=provider_account)
            .values_list('pk', flat=True)
        )
        diff_summary = build_provider_publication_diff_timeline(
            provider_account,
            visible_diff_ids=visible_diff_ids,
        )
        return render(request, self.template_name, {
            'object': provider_account,
            'provider_account': provider_account,
            'diff_summary': diff_summary,
            'return_url': provider_account.get_absolute_url(),
        })


class ProviderAccountSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/provideraccount_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request):
        provider_accounts = list(
            models.RpkiProviderAccount.objects.restrict(request.user, 'view')
        )
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_accounts)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(request.user, 'view')
            .filter(provider_account__in=provider_accounts)
            .values_list('pk', flat=True)
        )
        summary = build_provider_account_summary(
            provider_accounts,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        return render(request, self.template_name, {
            'summary': summary,
            'provider_account_count': len(provider_accounts),
            'return_url': reverse('plugins:netbox_rpki:provideraccount_list'),
        })


class ProviderSnapshotCompareView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/providersnapshot_compare.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_providersnapshot'

    def _get_snapshot(self, request, pk):
        queryset = models.ProviderSnapshot.objects.restrict(request.user, 'view')
        return get_object_or_404(queryset, pk=pk)

    def _render(self, request, snapshot, *, form=None, error_text=None, status=200):
        return render(request, self.template_name, {
            'object': snapshot,
            'snapshot': snapshot,
            'form': form or forms.ProviderSnapshotCompareForm(provider_account=snapshot.provider_account),
            'error_text': error_text,
            'return_url': snapshot.get_absolute_url(),
        }, status=status)

    def get(self, request, pk):
        snapshot = self._get_snapshot(request, pk)
        return self._render(request, snapshot)

    def post(self, request, pk):
        snapshot = self._get_snapshot(request, pk)
        form = forms.ProviderSnapshotCompareForm(request.POST, provider_account=snapshot.provider_account)
        if not form.is_valid():
            return self._render(request, snapshot, form=form, status=400)

        base_snapshot = form.cleaned_data.get('base_snapshot')
        error_text = None
        diff = None
        try:
            if base_snapshot is None:
                diff = build_latest_provider_snapshot_diff(snapshot)
                if diff is None:
                    error_text = 'No earlier completed snapshot is available for comparison.'
            else:
                diff = build_provider_snapshot_diff(
                    base_snapshot=base_snapshot,
                    comparison_snapshot=snapshot,
                )
        except ValueError as exc:
            error_text = str(exc)

        if diff is not None:
            messages.success(request, f'Created snapshot diff {diff}.')
            return redirect(diff.get_absolute_url())
        return self._render(request, snapshot, form=form, error_text=error_text)


class ProviderSnapshotSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/providersnapshot_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_providersnapshot'

    def get(self, request):
        queryset = models.ProviderSnapshot.objects.restrict(request.user, 'view')
        by_status: dict[str, int] = {}
        latest_completed_at = None
        with_diff_count = 0
        for snapshot in queryset:
            by_status[snapshot.status] = by_status.get(snapshot.status, 0) + 1
            if snapshot.completed_at is not None and (
                latest_completed_at is None or snapshot.completed_at > latest_completed_at
            ):
                latest_completed_at = snapshot.completed_at
            if snapshot.diffs_as_comparison.exists():
                with_diff_count += 1
        return render(request, self.template_name, {
            'total_snapshots': queryset.count(),
            'by_status': by_status,
            'with_diff_count': with_diff_count,
            'latest_completed_at': latest_completed_at,
            'return_url': reverse('plugins:netbox_rpki:providersnapshot_list'),
        })


class ROAReconciliationRunSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/roareconciliationrun_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_roareconciliationrun'

    def get(self, request):
        queryset = models.ROAReconciliationRun.objects.restrict(request.user, 'view')
        total_runs = queryset.count()
        completed_runs = 0
        replacement_required_intent_total = 0
        replacement_required_published_total = 0
        lint_warning_total = 0
        lint_error_total = 0
        for run in queryset.prefetch_related('lint_runs'):
            if run.status == models.ValidationRunStatus.COMPLETED:
                completed_runs += 1
            summary = dict(run.result_summary_json or {})
            replacement_required_intent_total += summary.get('replacement_required_intent_count', 0)
            replacement_required_published_total += summary.get('replacement_required_published_count', 0)
            lint_run = run.lint_runs.order_by('-started_at', '-created').first()
            if lint_run is not None:
                lint_warning_total += lint_run.warning_count
                lint_error_total += lint_run.error_count + lint_run.critical_count
        return render(request, self.template_name, {
            'total_runs': total_runs,
            'completed_runs': completed_runs,
            'replacement_required_intent_total': replacement_required_intent_total,
            'replacement_required_published_total': replacement_required_published_total,
            'lint_warning_total': lint_warning_total,
            'lint_error_total': lint_error_total,
            'return_url': reverse('plugins:netbox_rpki:roareconciliationrun_list'),
        })


class ASPAReconciliationRunSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/aspareconciliationrun_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_aspareconciliationrun'

    def get(self, request):
        queryset = models.ASPAReconciliationRun.objects.restrict(request.user, 'view')
        total_runs = queryset.count()
        completed_runs = 0
        missing_count = 0
        missing_provider_count = 0
        extra_provider_count = 0
        orphaned_count = 0
        stale_count = 0
        for run in queryset:
            if run.status == models.ValidationRunStatus.COMPLETED:
                completed_runs += 1
            summary = dict(run.result_summary_json or {})
            intent_types = dict(summary.get('intent_result_types') or {})
            published_types = dict(summary.get('published_result_types') or {})
            missing_count += intent_types.get(models.ASPAIntentResultType.MISSING, 0)
            missing_provider_count += intent_types.get(models.ASPAIntentResultType.MISSING_PROVIDER, 0)
            extra_provider_count += published_types.get(models.PublishedASPAResultType.EXTRA_PROVIDER, 0)
            orphaned_count += published_types.get(models.PublishedASPAResultType.ORPHANED, 0)
            stale_count += (
                intent_types.get(models.ASPAIntentResultType.STALE, 0)
                + published_types.get(models.PublishedASPAResultType.STALE, 0)
            )
        return render(request, self.template_name, {
            'total_runs': total_runs,
            'completed_runs': completed_runs,
            'missing_count': missing_count,
            'missing_provider_count': missing_provider_count,
            'extra_provider_count': extra_provider_count,
            'orphaned_count': orphaned_count,
            'stale_count': stale_count,
            'return_url': reverse('plugins:netbox_rpki:aspareconciliationrun_list'),
        })


class ROAChangePlanSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/roachangeplan_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_roachangeplan'

    def get(self, request):
        queryset = models.ROAChangePlan.objects.restrict(request.user, 'view')
        by_status: dict[str, int] = {}
        provider_backed_count = 0
        replacement_count_total = 0
        simulated_plan_count = 0
        simulation_current_plan_count = 0
        simulation_missing_count = 0
        simulation_pending_count = 0
        simulation_stale_count = 0
        simulation_blocking_plan_count = 0
        simulation_ack_required_plan_count = 0
        simulation_informational_plan_count = 0
        simulation_partially_constrained_plan_count = 0
        simulation_status_counts: dict[str, int] = {}
        simulation_approval_impact_totals = {
            models.ROAValidationSimulationApprovalImpact.INFORMATIONAL: 0,
            models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED: 0,
            models.ROAValidationSimulationApprovalImpact.BLOCKING: 0,
        }
        lint_warning_total = 0
        lint_error_total = 0
        lint_blocking_total = 0
        lint_ack_required_total = 0
        lint_acknowledged_total = 0
        lint_suppressed_total = 0
        lint_previously_acknowledged_total = 0
        lint_status_counts: dict[str, int] = {}
        for plan in queryset.prefetch_related('simulation_runs', 'lint_runs'):
            by_status[plan.status] = by_status.get(plan.status, 0) + 1
            if plan.is_provider_backed:
                provider_backed_count += 1
            replacement_count_total += (plan.summary_json or {}).get('replacement_count', 0)
            simulation_posture = build_roa_change_plan_simulation_posture(plan)
            if simulation_posture['has_simulation']:
                simulated_plan_count += 1
            if simulation_posture['is_current_for_plan']:
                simulation_current_plan_count += 1
            if simulation_posture['partially_constrained']:
                simulation_partially_constrained_plan_count += 1
            simulation_status = simulation_posture['status']
            simulation_status_counts[simulation_status] = simulation_status_counts.get(simulation_status, 0) + 1
            if simulation_status == 'missing':
                simulation_missing_count += 1
            elif simulation_status == 'pending':
                simulation_pending_count += 1
            elif simulation_status == 'stale':
                simulation_stale_count += 1
            elif simulation_status == models.ROAValidationSimulationApprovalImpact.BLOCKING:
                simulation_blocking_plan_count += 1
            elif simulation_status == models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED:
                simulation_ack_required_plan_count += 1
            elif simulation_status == models.ROAValidationSimulationApprovalImpact.INFORMATIONAL:
                simulation_informational_plan_count += 1
            for impact, count in (simulation_posture['approval_impact_counts'] or {}).items():
                simulation_approval_impact_totals[impact] = simulation_approval_impact_totals.get(impact, 0) + count
            lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
            if lint_run is not None:
                lint_warning_total += lint_run.warning_count
                lint_error_total += lint_run.error_count + lint_run.critical_count
            lint_posture = build_roa_change_plan_lint_posture(plan)
            lint_blocking_total += lint_posture['unresolved_blocking_finding_count']
            lint_ack_required_total += lint_posture['unresolved_acknowledgement_required_finding_count']
            lint_acknowledged_total += lint_posture['acknowledged_finding_count']
            lint_suppressed_total += lint_posture['suppressed_finding_count']
            lint_previously_acknowledged_total += lint_posture.get('previously_acknowledged_finding_count', 0)
            lint_status = lint_posture['status']
            lint_status_counts[lint_status] = lint_status_counts.get(lint_status, 0) + 1
        return render(request, self.template_name, {
            'total_plans': queryset.count(),
            'by_status': by_status,
            'provider_backed_count': provider_backed_count,
            'replacement_count_total': replacement_count_total,
            'simulated_plan_count': simulated_plan_count,
            'simulation_current_plan_count': simulation_current_plan_count,
            'simulation_missing_count': simulation_missing_count,
            'simulation_pending_count': simulation_pending_count,
            'simulation_stale_count': simulation_stale_count,
            'simulation_blocking_plan_count': simulation_blocking_plan_count,
            'simulation_acknowledgement_required_plan_count': simulation_ack_required_plan_count,
            'simulation_informational_plan_count': simulation_informational_plan_count,
            'simulation_partially_constrained_plan_count': simulation_partially_constrained_plan_count,
            'simulation_status_counts': simulation_status_counts,
            'simulation_approval_impact_totals': simulation_approval_impact_totals,
            'lint_warning_total': lint_warning_total,
            'lint_error_total': lint_error_total,
            'lint_blocking_total': lint_blocking_total,
            'lint_acknowledgement_required_total': lint_ack_required_total,
            'lint_acknowledged_total': lint_acknowledged_total,
            'lint_suppressed_total': lint_suppressed_total,
            'lint_previously_acknowledged_total': lint_previously_acknowledged_total,
            'lint_status_counts': lint_status_counts,
            'return_url': reverse('plugins:netbox_rpki:roachangeplan_list'),
        })


class ASPAChangePlanSummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/aspachangeplan_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_aspachangeplan'

    def get(self, request):
        queryset = models.ASPAChangePlan.objects.restrict(request.user, 'view')
        by_status: dict[str, int] = {}
        provider_backed_count = 0
        replacement_count_total = 0
        provider_add_count_total = 0
        provider_remove_count_total = 0
        for plan in queryset:
            by_status[plan.status] = by_status.get(plan.status, 0) + 1
            if plan.is_provider_backed:
                provider_backed_count += 1
            summary = dict(plan.summary_json or {})
            replacement_count_total += summary.get('replacement_count', 0)
            provider_add_count_total += summary.get('provider_add_count', 0)
            provider_remove_count_total += summary.get('provider_remove_count', 0)
        return render(request, self.template_name, {
            'total_plans': queryset.count(),
            'by_status': by_status,
            'provider_backed_count': provider_backed_count,
            'replacement_count_total': replacement_count_total,
            'provider_add_count_total': provider_add_count_total,
            'provider_remove_count_total': provider_remove_count_total,
            'return_url': reverse('plugins:netbox_rpki:aspachangeplan_list'),
        })


class ValidatorInstanceHistorySummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/validatorinstance_history_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_validatorinstance'

    def get(self, request, pk):
        queryset = models.ValidatorInstance.objects.restrict(request.user, 'view')
        validator = get_object_or_404(queryset, pk=pk)
        history = build_validator_run_history_summary(validator)
        return render(request, self.template_name, {
            'object': validator,
            'validator': validator,
            'history': history,
            'return_url': validator.get_absolute_url(),
        })


class TelemetrySourceHistorySummaryView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/telemetrysource_history_summary.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_telemetrysource'

    def get(self, request, pk):
        queryset = models.TelemetrySource.objects.restrict(request.user, 'view')
        source = get_object_or_404(queryset, pk=pk)
        history = build_telemetry_run_history_summary(source)
        return render(request, self.template_name, {
            'object': source,
            'telemetry_source': source,
            'history': history,
            'return_url': source.get_absolute_url(),
        })


class RoutingIntentTemplateBindingActionView(generic.ObjectEditView):
    queryset = models.RoutingIntentTemplateBinding.objects.all()

    def get_required_permission(self):
        return 'netbox_rpki.change_routingintenttemplatebinding'

    def get_binding(self, pk):
        return get_object_or_404(self.queryset, pk=pk)


class RoutingIntentTemplateBindingPreviewView(RoutingIntentTemplateBindingActionView):
    template_name = 'netbox_rpki/routingintenttemplatebinding_preview.html'

    def get(self, request, pk):
        binding = self.get_binding(pk)
        try:
            preview = preview_routing_intent_template_binding(binding)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(binding.get_absolute_url())

        return render(request, self.template_name, {
            'object': binding,
            'binding': binding,
            'preview': preview,
            'return_url': self.get_return_url(request, binding),
        })


class RoutingIntentTemplateBindingRegenerateView(RoutingIntentTemplateBindingActionView):
    template_name = 'netbox_rpki/routingintenttemplatebinding_regenerate.html'

    def _render(self, request, binding, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': binding,
            'binding': binding,
            'form': form or ConfirmationForm(),
            'return_url': self.get_return_url(request, binding),
        }, status=status)

    def get(self, request, pk):
        binding = self.get_binding(pk)
        return self._render(request, binding)

    def post(self, request, pk):
        binding = self.get_binding(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, binding, form=form, status=400)

        try:
            _derivation_run, reconciliation_run = run_routing_intent_template_binding_pipeline(binding)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(binding.get_absolute_url())

        messages.success(request, f'Regenerated routing intent template binding {binding.name}.')
        return redirect(reconciliation_run.get_absolute_url())


class RoutingIntentProfileRunView(generic.ObjectEditView):
    queryset = models.RoutingIntentProfile.objects.all()
    template_name = 'netbox_rpki/routingintentprofile_run.html'

    def get_required_permission(self):
        return 'netbox_rpki.change_routingintentprofile'

    def get_profile(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def _render(self, request, profile, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': profile,
            'profile': profile,
            'form': form or forms.RoutingIntentProfileRunActionForm(profile=profile),
            'return_url': self.get_return_url(request, profile),
        }, status=status)

    def get(self, request, pk):
        profile = self.get_profile(pk)
        return self._render(request, profile)

    def post(self, request, pk):
        profile = self.get_profile(pk)
        form = forms.RoutingIntentProfileRunActionForm(request.POST, profile=profile)
        if not form.is_valid():
            return self._render(request, profile, form=form, status=400)

        provider_snapshot = form.cleaned_data.get('provider_snapshot')
        job = RunRoutingIntentProfileJob.enqueue(
            instance=profile,
            user=request.user,
            profile_pk=profile.pk,
            comparison_scope=form.cleaned_data['comparison_scope'],
            provider_snapshot_pk=getattr(provider_snapshot, 'pk', provider_snapshot),
        )
        messages.success(request, f'Enqueued routing-intent profile job {job.pk} for {profile.name}.')
        return redirect(profile.get_absolute_url())


class RoutingIntentExceptionApproveView(generic.ObjectEditView):
    queryset = models.RoutingIntentException.objects.all()
    template_name = 'netbox_rpki/routingintentexception_approve.html'

    def get_required_permission(self):
        return 'netbox_rpki.change_routingintentexception'

    def get_exception(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def _render(self, request, exception, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': exception,
            'routing_intent_exception': exception,
            'form': form or ConfirmationForm(),
            'return_url': self.get_return_url(request, exception),
        }, status=status)

    def get(self, request, pk):
        exception = self.get_exception(pk)
        return self._render(request, exception)

    def post(self, request, pk):
        exception = self.get_exception(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, exception, form=form, status=400)

        exception.approved_at = timezone.now()
        exception.approved_by = getattr(request.user, 'username', '')
        exception.save(update_fields=('approved_at', 'approved_by'))
        messages.success(request, f'Approved routing intent exception {exception.name}.')
        return redirect(exception.get_absolute_url())


class DelegatedPublicationWorkflowApproveView(generic.ObjectEditView):
    queryset = models.DelegatedPublicationWorkflow.objects.all()
    template_name = 'netbox_rpki/delegatedpublicationworkflow_approve.html'

    def get_required_permission(self):
        return 'netbox_rpki.change_delegatedpublicationworkflow'

    def get_workflow(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def _render(self, request, workflow, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': workflow,
            'workflow': workflow,
            'form': form or ConfirmationForm(),
            'return_url': self.get_return_url(request, workflow),
        }, status=status)

    def get(self, request, pk):
        workflow = self.get_workflow(pk)
        return self._render(request, workflow)

    def post(self, request, pk):
        workflow = self.get_workflow(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, workflow, form=form, status=400)

        try:
            approve_delegated_publication_workflow(
                workflow,
                approved_by=getattr(request.user, 'username', ''),
            )
        except ValueError:
            return HttpResponseBadRequest('This delegated publication workflow cannot be approved.')

        messages.success(request, f'Approved delegated publication workflow {workflow.name}.')
        return redirect(workflow.get_absolute_url())


class ROAReconciliationRunCreatePlanView(generic.ObjectEditView):
    queryset = models.ROAReconciliationRun.objects.all()
    template_name = 'netbox_rpki/roareconciliationrun_create_plan.html'

    def get_required_permission(self):
        return 'netbox_rpki.view_roareconciliationrun'

    def get_run(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def _require_profile_change_permission(self, request, reconciliation_run):
        if not request.user.has_perm('netbox_rpki.change_routingintentprofile', reconciliation_run.intent_profile):
            raise PermissionDenied('This user does not have permission to create a change plan from this reconciliation run.')

    def _render(self, request, reconciliation_run, *, form=None, status=200):
        self._require_profile_change_permission(request, reconciliation_run)
        return render(request, self.template_name, {
            'object': reconciliation_run,
            'reconciliation_run': reconciliation_run,
            'form': form or ConfirmationForm(),
            'return_url': self.get_return_url(request, reconciliation_run),
        }, status=status)

    def get(self, request, pk):
        reconciliation_run = self.get_run(pk)
        return self._render(request, reconciliation_run)

    def post(self, request, pk):
        reconciliation_run = self.get_run(pk)
        self._require_profile_change_permission(request, reconciliation_run)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, reconciliation_run, form=form, status=400)

        try:
            plan = create_roa_change_plan(reconciliation_run)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(reconciliation_run.get_absolute_url())

        messages.success(request, f'Created ROA change plan {plan.name}.')
        return redirect(plan.get_absolute_url())


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


class OrganizationCreateBulkIntentRunView(generic.ObjectEditView):
    queryset = models.Organization.objects.all()
    template_name = 'netbox_rpki/organization_bulk_intent_run.html'

    def get_required_permission(self):
        return 'netbox_rpki.change_organization'

    def get_organization(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def _render(self, request, organization, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': organization,
            'organization': organization,
            'form': form or forms.BulkIntentRunActionForm(organization=organization),
            'return_url': self.get_return_url(request, organization),
        }, status=status)

    def get(self, request, pk):
        organization = self.get_organization(pk)
        return self._render(request, organization)

    def post(self, request, pk):
        organization = self.get_organization(pk)
        form = forms.BulkIntentRunActionForm(request.POST, organization=organization)
        if not form.is_valid():
            return self._render(request, organization, form=form, status=400)

        job, created = RunBulkRoutingIntentJob.enqueue_for_organization(
            organization=organization,
            profiles=tuple(form.cleaned_data.get('profiles') or ()),
            bindings=tuple(form.cleaned_data.get('bindings') or ()),
            comparison_scope=form.cleaned_data['comparison_scope'],
            provider_snapshot=form.cleaned_data.get('provider_snapshot'),
            create_change_plans=form.cleaned_data.get('create_change_plans', False),
            run_name=form.cleaned_data.get('run_name') or None,
            user=request.user,
        )
        if created:
            messages.success(request, f'Enqueued bulk routing-intent job {job.pk} for {organization.name}.')
        elif job is not None:
            messages.warning(request, f'Bulk routing-intent job {job.pk} is already queued for {organization.name}.')
        else:
            messages.warning(request, f'{organization.name} already has a matching bulk routing-intent run in progress.')
        return redirect(organization.get_absolute_url())


class BulkIntentRunApproveView(generic.ObjectEditView):
    queryset = models.BulkIntentRun.objects.all()
    template_name = 'netbox_rpki/bulkintentrun_approve.html'

    def get_required_permission(self):
        return 'netbox_rpki.change_bulkintentrun'

    def get_bulk_run(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def _render(self, request, bulk_run, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': bulk_run,
            'bulk_run': bulk_run,
            'form': form or ConfirmationForm(),
            'return_url': self.get_return_url(request, bulk_run),
            'action_label': 'Approve',
            'button_class': 'success',
        }, status=status)

    def get(self, request, pk):
        bulk_run = self.get_bulk_run(pk)
        return self._render(request, bulk_run)

    def post(self, request, pk):
        bulk_run = self.get_bulk_run(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, bulk_run, form=form, status=400)

        try:
            approve_bulk_intent_run(bulk_run, approved_by=getattr(request.user, 'username', ''))
        except Exception as exc:
            messages.error(request, str(exc))
            return self._render(request, bulk_run, form=form, status=400)

        messages.success(request, f'Approved bulk intent run "{bulk_run.name}".')
        return redirect(bulk_run.get_absolute_url())


class BulkIntentRunApproveSecondaryView(generic.ObjectEditView):
    queryset = models.BulkIntentRun.objects.all()
    template_name = 'netbox_rpki/bulkintentrun_approve.html'

    def get_required_permission(self):
        return 'netbox_rpki.change_bulkintentrun'

    def get_bulk_run(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def _render(self, request, bulk_run, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': bulk_run,
            'bulk_run': bulk_run,
            'form': form or ConfirmationForm(),
            'return_url': self.get_return_url(request, bulk_run),
            'action_label': 'Secondary Approve',
            'button_class': 'warning',
        }, status=status)

    def get(self, request, pk):
        bulk_run = self.get_bulk_run(pk)
        return self._render(request, bulk_run)

    def post(self, request, pk):
        bulk_run = self.get_bulk_run(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, bulk_run, form=form, status=400)

        try:
            secondary_approve_bulk_intent_run(bulk_run, approved_by=getattr(request.user, 'username', ''))
        except Exception as exc:
            messages.error(request, str(exc))
            return self._render(request, bulk_run, form=form, status=400)

        messages.success(request, f'Secondary-approved bulk intent run "{bulk_run.name}".')
        return redirect(bulk_run.get_absolute_url())


class ASPAReconciliationRunCreatePlanView(generic.ObjectEditView):
    queryset = models.ASPAReconciliationRun.objects.all()
    template_name = 'netbox_rpki/roachangeplan_confirm.html'
    action_label = 'Create Plan'
    button_class = 'primary'

    def get_required_permission(self):
        return 'netbox_rpki.change_aspareconciliationrun'

    def get_run(self, pk):
        return get_object_or_404(self.queryset, pk=pk)

    def _render(self, request, reconciliation_run, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': reconciliation_run,
            'change_plan': reconciliation_run,
            'form': form or ConfirmationForm(),
            'return_url': self.get_return_url(request, reconciliation_run),
            'action_label': self.action_label,
            'button_class': self.button_class,
            'show_governance_inputs': False,
        }, status=status)

    def get(self, request, pk):
        reconciliation_run = self.get_run(pk)
        return self._render(request, reconciliation_run)

    def post(self, request, pk):
        reconciliation_run = self.get_run(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, reconciliation_run, form=form, status=400)

        try:
            plan = create_aspa_change_plan(reconciliation_run)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(reconciliation_run.get_absolute_url())

        messages.success(request, f'Created ASPA change plan {plan.name}.')
        return redirect(plan.get_absolute_url())


class OperationsDashboardView(ContentTypePermissionRequiredMixin, View):
    template_name = 'netbox_rpki/operations_dashboard.html'
    additional_permissions = [
        'netbox_rpki.view_roa',
        'netbox_rpki.view_certificate',
        'netbox_rpki.view_routingintenttemplatebinding',
        'netbox_rpki.view_routingintentexception',
        'netbox_rpki.view_bulkintentrun',
        'netbox_rpki.view_roareconciliationrun',
        'netbox_rpki.view_roachangeplan',
        'netbox_rpki.view_aspareconciliationrun',
        'netbox_rpki.view_aspachangeplan',
        'netbox_rpki.view_irrsource',
        'netbox_rpki.view_irrcoordinationrun',
        'netbox_rpki.view_irrchangeplan',
        'netbox_rpki.view_irrwriteexecution',
    ]
    provider_health_priority = {
        models.ProviderSyncHealth.FAILED: 0,
        models.ProviderSyncHealth.STALE: 1,
    }

    def get_required_permission(self):
        return 'netbox_rpki.view_rpkiprovideraccount'

    def get(self, request):
        provider_accounts = self.get_provider_accounts(request)
        expiring_roas = self.get_expiring_roas(request)
        expiring_certificates = self.get_expiring_certificates(request)
        stale_bindings = self.get_stale_bindings(request)
        expiring_exceptions = self.get_expiring_exceptions(request)
        external_management_exceptions_requiring_review = self.get_external_management_exceptions_requiring_review(request)
        bulk_run_rollup = self.get_bulk_run_rollup(request)
        roa_reconciliation_summary = self.get_roa_reconciliation_summary(request)
        roa_change_plan_summary = self.get_roa_change_plan_summary(request)
        reconciliation_attention_runs = self.get_reconciliation_attention_runs(request)
        change_plans_requiring_attention = self.get_change_plans_requiring_attention(request)
        aspa_reconciliation_attention_runs = self.get_aspa_reconciliation_attention_runs(request)
        aspa_change_plans_requiring_attention = self.get_aspa_change_plans_requiring_attention(request)
        validator_instances_requiring_attention = self.get_validator_instances_requiring_attention(request)
        validation_runs_requiring_attention = self.get_validation_runs_requiring_attention(request)
        telemetry_sources_requiring_attention = self.get_telemetry_sources_requiring_attention(request)
        external_mismatch_items = self.get_external_mismatch_items(request)
        irr_sources_requiring_attention = self.get_irr_sources_requiring_attention(request)
        irr_coordination_attention_runs = self.get_irr_coordination_attention_runs(request)
        irr_change_plans_requiring_attention = self.get_irr_change_plans_requiring_attention(request)
        irr_write_failures = self.get_recent_irr_write_failures(request)

        return render(request, self.template_name, {
            'provider_accounts': provider_accounts,
            'expiring_roas': expiring_roas,
            'expiring_certificates': expiring_certificates,
            'stale_bindings': stale_bindings,
            'expiring_exceptions': expiring_exceptions,
            'external_management_exceptions_requiring_review': external_management_exceptions_requiring_review,
            'bulk_run_rollup': bulk_run_rollup,
            'roa_reconciliation_summary': roa_reconciliation_summary,
            'roa_change_plan_summary': roa_change_plan_summary,
            'reconciliation_attention_runs': reconciliation_attention_runs,
            'change_plans_requiring_attention': change_plans_requiring_attention,
            'aspa_reconciliation_attention_runs': aspa_reconciliation_attention_runs,
            'aspa_change_plans_requiring_attention': aspa_change_plans_requiring_attention,
            'validator_instances_requiring_attention': validator_instances_requiring_attention,
            'validation_runs_requiring_attention': validation_runs_requiring_attention,
            'telemetry_sources_requiring_attention': telemetry_sources_requiring_attention,
            'external_mismatch_items': external_mismatch_items,
            'irr_sources_requiring_attention': irr_sources_requiring_attention,
            'irr_coordination_attention_runs': irr_coordination_attention_runs,
            'irr_change_plans_requiring_attention': irr_change_plans_requiring_attention,
            'irr_write_failures': irr_write_failures,
        })

    def get_provider_accounts(self, request):
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
            if provider_account.sync_enabled and self.provider_account_requires_attention(provider_account)
        ]
        provider_accounts.sort(key=self.get_provider_account_sort_key)
        return provider_accounts

    def provider_account_requires_attention(self, provider_account):
        lifecycle_summary = build_provider_lifecycle_health_summary(provider_account)
        return lifecycle_summary['sync']['status'] in {
            models.ProviderSyncHealth.FAILED,
            models.ProviderSyncHealth.STALE,
            models.ProviderSyncHealth.NEVER_SYNCED,
        }

    def build_provider_account_dashboard_row(self, provider_account, *, visible_snapshot_ids=None, visible_diff_ids=None):
        rollup = build_provider_account_rollup(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        lifecycle_summary = build_provider_lifecycle_health_summary(
            provider_account,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )
        rollup['family_status_text'] = self.get_family_status_text(rollup)
        rollup['freshness_text'] = self.get_freshness_text(provider_account, lifecycle_summary)
        rollup['sync_threshold_text'] = (
            f"Stale after {lifecycle_summary['policy']['thresholds']['sync_stale_after_minutes']} minute(s)"
        )
        rollup['attention_summary'] = lifecycle_summary['attention_summary']
        rollup['publication_health'] = lifecycle_summary['publication_health']
        rollup['publication_health_text'] = (
            f"{lifecycle_summary['publication_health']['status']} "
            f"({lifecycle_summary['publication_health']['attention_item_count']} attention items)"
        )
        rollup['latest_snapshot_url'] = self.get_summary_url('plugins:netbox_rpki:providersnapshot', rollup['latest_snapshot_id'])
        rollup['latest_diff_url'] = self.get_summary_url('plugins:netbox_rpki:providersnapshotdiff', rollup['latest_diff_id'])
        rollup['latest_snapshot_label'] = rollup['latest_snapshot_name'] or 'Latest snapshot'
        rollup['latest_diff_label'] = rollup['latest_diff_name'] or 'Latest diff'
        provider_account.last_sync_rollup = rollup
        provider_account.lifecycle_health_summary = lifecycle_summary
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

    def get_freshness_text(self, provider_account, lifecycle_summary):
        if not provider_account.sync_enabled:
            return 'Sync disabled'
        if provider_account.last_successful_sync is None:
            return 'Never synced'
        next_stale_at = lifecycle_summary['sync'].get('next_stale_at')
        if next_stale_at:
            return f'Stale after {next_stale_at}'
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

    def get_validator_instances_requiring_attention(self, request):
        queryset = models.ValidatorInstance.objects.restrict(request.user, 'view').prefetch_related('validation_runs')
        return build_validator_instance_attention_items(queryset)

    def get_validation_runs_requiring_attention(self, request):
        queryset = models.ValidationRun.objects.restrict(request.user, 'view').select_related('validator')
        return build_validation_run_attention_items(queryset)

    def get_telemetry_sources_requiring_attention(self, request):
        queryset = models.TelemetrySource.objects.restrict(request.user, 'view').select_related(
            'organization',
            'last_successful_run',
        ).order_by('organization__name', 'name')
        return build_telemetry_source_attention_items(queryset)

    def get_external_mismatch_items(self, request):
        roas = models.Roa.objects.restrict(request.user, 'view').select_related('origin_as')[:50]
        aspas = models.ASPA.objects.restrict(request.user, 'view').select_related('customer_as', 'signed_object')[:50]
        return build_external_mismatch_items(roas, aspas)

    def get_irr_sources_requiring_attention(self, request):
        queryset = models.IrrSource.objects.restrict(request.user, 'view').select_related(
            'organization',
            'last_successful_snapshot',
        ).order_by('organization__name', 'name')
        items = []
        for source in queryset:
            if source.sync_health not in {
                models.IrrSyncHealth.FAILED,
                models.IrrSyncHealth.STALE,
                models.IrrSyncHealth.NEVER_SYNCED,
            }:
                continue
            items.append({
                'object': source,
                'sync_health': source.sync_health,
                'sync_health_display': source.sync_health_display,
                'latest_snapshot': source.last_successful_snapshot,
                'latest_snapshot_url': self.get_summary_url(
                    'plugins:netbox_rpki:irr_snapshot',
                    getattr(source.last_successful_snapshot, 'pk', None),
                ),
                'freshness_text': self.get_irr_source_freshness_text(source),
                'write_support_mode': source.write_support_mode,
            })
        return items

    def get_irr_source_freshness_text(self, source):
        if source.last_successful_snapshot is None:
            return 'Never synced'
        completed_at = source.last_successful_snapshot.completed_at or source.last_successful_snapshot.started_at
        if completed_at is None:
            return 'Latest snapshot missing completion time'
        return f'Latest snapshot {completed_at}'

    def get_irr_coordination_attention_runs(self, request):
        queryset = models.IrrCoordinationRun.objects.restrict(request.user, 'view').select_related(
            'organization',
        ).order_by('-started_at', '-created')
        items = []
        for run in queryset[:20]:
            summary = run.summary_json or {}
            conflict_count = summary.get('cross_source_conflict_count', 0)
            stale_count = summary.get('stale_source_count', 0)
            non_draftable_count = summary.get('non_draftable_source_count', 0)
            if run.status == models.IrrCoordinationRunStatus.FAILED or conflict_count or stale_count or non_draftable_count:
                items.append({
                    'object': run,
                    'cross_source_conflict_count': conflict_count,
                    'stale_source_count': stale_count,
                    'non_draftable_source_count': non_draftable_count,
                    'draftable_source_count': summary.get('draftable_source_count', 0),
                })
        return items

    def get_irr_change_plans_requiring_attention(self, request):
        queryset = models.IrrChangePlan.objects.restrict(request.user, 'view').select_related(
            'organization',
            'source',
        ).order_by('-created')
        items = []
        for plan in queryset[:20]:
            summary = plan.summary_json or {}
            capability_warnings = list(summary.get('capability_warnings') or [])
            noop_count = (summary.get('item_counts') or {}).get(models.IrrChangePlanAction.NOOP, 0)
            if (
                plan.status in {
                    models.IrrChangePlanStatus.DRAFT,
                    models.IrrChangePlanStatus.READY,
                    models.IrrChangePlanStatus.FAILED,
                }
                or capability_warnings
                or noop_count
            ):
                items.append({
                    'object': plan,
                    'capability_warnings': capability_warnings,
                    'noop_count': noop_count,
                    'latest_execution': summary.get('latest_execution') or {},
                })
        return items

    def get_recent_irr_write_failures(self, request):
        queryset = models.IrrWriteExecution.objects.restrict(request.user, 'view').select_related(
            'organization',
            'source',
            'change_plan',
        ).filter(
            status__in={
                models.IrrWriteExecutionStatus.FAILED,
                models.IrrWriteExecutionStatus.PARTIAL,
            }
        ).order_by('-started_at', '-created')
        return list(queryset[:20])

    def get_expiring_roas(self, request):
        now = timezone.now()
        queryset = models.Roa.objects.restrict(request.user, 'view').select_related(
            'origin_as',
            'signed_by',
            'signed_by__rpki_org',
        ).filter(
            valid_to__isnull=False,
        ).order_by('valid_to', 'name')
        items = []
        for roa in queryset:
            organization = roa.signed_by.rpki_org
            _policy, thresholds, _source = get_effective_lifecycle_thresholds(organization=organization)
            if not is_within_lifecycle_expiry_threshold(
                expires_at=roa.valid_to,
                warning_days=thresholds['roa_expiry_warning_days'],
                reference_time=now,
            ):
                continue
            items.append({
                'object': roa,
                'organization': organization,
                'related_object': roa.signed_by,
                'expiry_text': self.get_expiry_text(roa.valid_to, today=now.date()),
                'expiry_badge_class': self.get_expiry_badge_class(roa.valid_to, today=now.date()),
            })
        return items

    def get_expiring_certificates(self, request):
        now = timezone.now()
        queryset = models.Certificate.objects.restrict(request.user, 'view').select_related('rpki_org').filter(
            valid_to__isnull=False,
        ).order_by('valid_to', 'name')
        items = []
        for certificate in queryset:
            organization = certificate.rpki_org
            _policy, thresholds, _source = get_effective_lifecycle_thresholds(organization=organization)
            if not is_within_lifecycle_expiry_threshold(
                expires_at=certificate.valid_to,
                warning_days=thresholds['certificate_expiry_warning_days'],
                reference_time=now,
            ):
                continue
            items.append({
                'object': certificate,
                'organization': organization,
                'expiry_text': self.get_expiry_text(certificate.valid_to, today=now.date()),
                'expiry_badge_class': self.get_expiry_badge_class(certificate.valid_to, today=now.date()),
            })
        return items

    def get_stale_bindings(self, request):
        attention_states = {
            models.RoutingIntentTemplateBindingState.STALE,
            models.RoutingIntentTemplateBindingState.PENDING,
            models.RoutingIntentTemplateBindingState.INVALID,
        }
        queryset = (
            models.RoutingIntentTemplateBinding.objects.restrict(request.user, 'view')
            .select_related('template', 'intent_profile', 'intent_profile__organization')
            .filter(
                enabled=True,
                template__enabled=True,
                intent_profile__enabled=True,
                state__in=attention_states,
            )
            .order_by('state', 'binding_priority', 'name')
        )
        bindings = []
        for binding in queryset:
            summary = dict(binding.summary_json or {})
            bindings.append({
                'object': binding,
                'organization': binding.intent_profile.organization,
                'reason_summary': summary.get('regeneration_reason_summary') or summary.get('error') or 'Regeneration required',
                'reason_codes': summary.get('regeneration_reason_codes') or (),
                'status_badge_class': self.get_binding_state_badge_class(binding.state),
            })
        return bindings[:10]

    def get_expiring_exceptions(self, request):
        now = timezone.now()
        queryset = (
            models.RoutingIntentException.objects.restrict(request.user, 'view')
            .select_related('organization', 'intent_profile', 'template_binding')
            .filter(
                enabled=True,
                ends_at__isnull=False,
            )
            .order_by('ends_at', 'name')
        )
        items = []
        for exception in queryset:
            _policy, thresholds, _source = get_effective_lifecycle_thresholds(organization=exception.organization)
            if not is_within_lifecycle_expiry_threshold(
                expires_at=exception.ends_at,
                warning_days=thresholds['exception_expiry_warning_days'],
                reference_time=now,
            ):
                continue
            items.append({
                'object': exception,
                'organization': exception.organization,
                'expiry_text': self.get_expiry_text(timezone.localtime(exception.ends_at).date(), today=now.date()),
                'expiry_badge_class': self.get_expiry_badge_class(timezone.localtime(exception.ends_at).date(), today=now.date()),
                'lifecycle_text': self.get_exception_lifecycle_text(exception),
            })
        return items[:10]

    def get_external_management_exceptions_requiring_review(self, request):
        now = timezone.now()
        queryset = (
            models.ExternalManagementException.objects.restrict(request.user, 'view')
            .select_related('organization', 'prefix', 'roa', 'imported_authorization', 'aspa', 'imported_aspa')
            .filter(enabled=True)
            .order_by('review_at', 'ends_at', 'name')
        )
        items = []
        for exception in queryset:
            if not exception.is_review_due and not exception.is_expired:
                continue
            if exception.is_expired:
                status_text = 'Expired'
                status_badge_class = 'danger'
            else:
                status_text = 'Review Due'
                status_badge_class = 'warning'
            items.append({
                'object': exception,
                'organization': exception.organization,
                'scope_text': exception.get_scope_type_display(),
                'status_text': status_text,
                'status_badge_class': status_badge_class,
            })
        return items[:10]

    def get_bulk_run_rollup(self, request):
        queryset = (
            models.BulkIntentRun.objects.restrict(request.user, 'view')
            .select_related('organization')
            .order_by('-started_at', '-created')
        )
        runs = []
        running_count = 0
        failed_count = 0
        completed_count = 0
        attention_count = 0
        for bulk_run in queryset:
            summary = dict(bulk_run.summary_json or {})
            failed_scope_count = summary.get('failed_scope_count', 0)
            scope_result_count = summary.get('scope_result_count', 0)
            change_plan_count = summary.get('change_plan_count', 0)
            status_badge_class = self.get_validation_status_badge_class(bulk_run.status)
            needs_attention = (
                bulk_run.status in {models.ValidationRunStatus.PENDING, models.ValidationRunStatus.RUNNING, models.ValidationRunStatus.FAILED}
                or failed_scope_count > 0
            )
            if bulk_run.status in {models.ValidationRunStatus.PENDING, models.ValidationRunStatus.RUNNING}:
                running_count += 1
            elif bulk_run.status == models.ValidationRunStatus.FAILED:
                failed_count += 1
            elif bulk_run.status == models.ValidationRunStatus.COMPLETED:
                completed_count += 1
            if needs_attention:
                attention_count += 1
            runs.append({
                'object': bulk_run,
                'scope_result_count': scope_result_count,
                'change_plan_count': change_plan_count,
                'failed_scope_count': failed_scope_count,
                'status_badge_class': status_badge_class,
                'status_text': bulk_run.get_status_display(),
                'summary_text': summary.get('error') or (
                    f"{scope_result_count} scope result(s), {change_plan_count} change plan(s)"
                ),
            })
        return {
            'runs': runs[:10],
            'running_count': running_count,
            'failed_count': failed_count,
            'completed_count': completed_count,
            'attention_count': attention_count,
        }

    def get_roa_reconciliation_summary(self, request):
        queryset = (
            models.ROAReconciliationRun.objects.restrict(request.user, 'view')
            .prefetch_related('lint_runs')
        )
        payload = {
            'total_runs': queryset.count(),
            'completed_runs': 0,
            'replacement_required_intent_total': 0,
            'replacement_required_published_total': 0,
            'lint_warning_total': 0,
            'lint_error_total': 0,
        }
        for run in queryset:
            if run.status == models.ValidationRunStatus.COMPLETED:
                payload['completed_runs'] += 1
            summary = dict(run.result_summary_json or {})
            payload['replacement_required_intent_total'] += summary.get('replacement_required_intent_count', 0)
            payload['replacement_required_published_total'] += summary.get('replacement_required_published_count', 0)
            lint_run = run.lint_runs.order_by('-started_at', '-created').first()
            if lint_run is not None:
                payload['lint_warning_total'] += lint_run.warning_count
                payload['lint_error_total'] += lint_run.error_count + lint_run.critical_count
        return payload

    def get_roa_change_plan_summary(self, request):
        queryset = (
            models.ROAChangePlan.objects.restrict(request.user, 'view')
            .prefetch_related('simulation_runs', 'lint_runs')
        )
        by_status: dict[str, int] = {}
        payload = {
            'total_plans': queryset.count(),
            'by_status': by_status,
            'simulated_plan_count': 0,
            'simulation_missing_count': 0,
            'simulation_pending_count': 0,
            'simulation_stale_count': 0,
            'simulation_blocking_plan_count': 0,
            'simulation_ack_required_plan_count': 0,
            'lint_blocking_total': 0,
            'lint_ack_required_total': 0,
            'lint_acknowledged_total': 0,
            'replacement_count_total': 0,
        }
        for plan in queryset:
            by_status[plan.status] = by_status.get(plan.status, 0) + 1
            payload['replacement_count_total'] += (plan.summary_json or {}).get('replacement_count', 0)
            simulation_posture = build_roa_change_plan_simulation_posture(plan)
            if simulation_posture['has_simulation']:
                payload['simulated_plan_count'] += 1
            simulation_status = simulation_posture['status']
            if simulation_status == 'missing':
                payload['simulation_missing_count'] += 1
            elif simulation_status == 'pending':
                payload['simulation_pending_count'] += 1
            elif simulation_status == 'stale':
                payload['simulation_stale_count'] += 1
            elif simulation_status == models.ROAValidationSimulationApprovalImpact.BLOCKING:
                payload['simulation_blocking_plan_count'] += 1
            elif simulation_status == models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED:
                payload['simulation_ack_required_plan_count'] += 1
            lint_posture = build_roa_change_plan_lint_posture(plan)
            payload['lint_blocking_total'] += lint_posture['unresolved_blocking_finding_count']
            payload['lint_ack_required_total'] += lint_posture['unresolved_acknowledgement_required_finding_count']
            payload['lint_acknowledged_total'] += lint_posture['acknowledged_finding_count']
        return payload

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
            latest_lint_run = plan.lint_runs.order_by('-started_at', '-created').first()
            lint_posture = build_roa_change_plan_lint_posture(plan)
            simulation_posture = build_roa_change_plan_simulation_posture(plan)
            latest_simulation = None
            if simulation_posture['run_id'] is not None:
                latest_simulation = plan.simulation_runs.filter(pk=simulation_posture['run_id']).first()
            replacement_count = (plan.summary_json or {}).get('replacement_count', 0)
            if (
                plan.status != models.ROAChangePlanStatus.FAILED
                and replacement_count == 0
                and lint_posture['unresolved_blocking_finding_count'] == 0
                and lint_posture['unresolved_acknowledgement_required_finding_count'] == 0
                and lint_posture['acknowledged_finding_count'] == 0
                and not simulation_posture['awaiting_review']
            ):
                continue
            plans.append({
                'object': plan,
                'replacement_count': replacement_count,
                'warning_count': getattr(latest_lint_run, 'warning_count', 0),
                'error_count': getattr(latest_lint_run, 'error_count', 0) + getattr(latest_lint_run, 'critical_count', 0),
                'lint_posture': lint_posture,
                'blocking_count': lint_posture['unresolved_blocking_finding_count'],
                'ack_required_count': lint_posture['unresolved_acknowledgement_required_finding_count'],
                'acknowledged_count': lint_posture['acknowledged_finding_count'],
                'suppressed_count': lint_posture['suppressed_finding_count'],
                'simulation_posture': simulation_posture,
                'simulation_blocking_count': simulation_posture['approval_impact_counts'].get(
                    models.ROAValidationSimulationApprovalImpact.BLOCKING, 0
                ),
                'simulation_ack_required_count': simulation_posture['approval_impact_counts'].get(
                    models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED, 0
                ),
                'simulation_run': latest_simulation,
                'lint_run': latest_lint_run,
            })
        plans.sort(
            key=lambda item: (
                item['object'].status == models.ROAChangePlanStatus.FAILED,
                item['simulation_posture']['status'] in {
                    'missing',
                    'pending',
                    'stale',
                    models.ROAValidationSimulationApprovalImpact.BLOCKING,
                    models.ROAValidationSimulationApprovalImpact.ACKNOWLEDGEMENT_REQUIRED,
                },
                item['simulation_blocking_count'],
                item['simulation_ack_required_count'],
                item['blocking_count'],
                item['ack_required_count'],
                item['acknowledged_count'],
                item['replacement_count'],
                item['object'].created.timestamp(),
            ),
            reverse=True,
        )
        return plans[:10]

    def get_aspa_reconciliation_attention_runs(self, request):
        queryset = (
            models.ASPAReconciliationRun.objects.restrict(request.user, 'view')
            .select_related('organization', 'provider_snapshot')
        )
        runs = []
        for run in queryset:
            summary = dict(run.result_summary_json or {})
            intent_types = dict(summary.get('intent_result_types') or {})
            published_types = dict(summary.get('published_result_types') or {})
            missing_count = intent_types.get(models.ASPAIntentResultType.MISSING, 0)
            missing_provider_count = intent_types.get(models.ASPAIntentResultType.MISSING_PROVIDER, 0)
            stale_count = (
                intent_types.get(models.ASPAIntentResultType.STALE, 0)
                + published_types.get(models.PublishedASPAResultType.STALE, 0)
            )
            extra_provider_count = published_types.get(models.PublishedASPAResultType.EXTRA_PROVIDER, 0)
            orphaned_count = published_types.get(models.PublishedASPAResultType.ORPHANED, 0)
            if not any((missing_count, missing_provider_count, stale_count, extra_provider_count, orphaned_count)):
                continue
            runs.append({
                'object': run,
                'missing_count': missing_count,
                'missing_provider_count': missing_provider_count,
                'extra_provider_count': extra_provider_count,
                'orphaned_count': orphaned_count,
                'stale_count': stale_count,
            })
        runs.sort(
            key=lambda item: (
                item['stale_count'],
                item['orphaned_count'],
                item['missing_provider_count'],
                item['extra_provider_count'],
                item['missing_count'],
                (item['object'].completed_at or item['object'].started_at or timezone.now()).timestamp(),
            ),
            reverse=True,
        )
        return runs[:10]

    def get_aspa_change_plans_requiring_attention(self, request):
        queryset = (
            models.ASPAChangePlan.objects.restrict(request.user, 'view')
            .select_related('organization', 'provider_account', 'source_reconciliation_run')
        )
        attention_statuses = {
            models.ASPAChangePlanStatus.DRAFT,
            models.ASPAChangePlanStatus.APPROVED,
            models.ASPAChangePlanStatus.FAILED,
        }
        plans = []
        for plan in queryset:
            if plan.status not in attention_statuses:
                continue
            summary = dict(plan.summary_json or {})
            plans.append({
                'object': plan,
                'replacement_count': summary.get('replacement_count', 0),
                'provider_add_count': summary.get('provider_add_count', 0),
                'provider_remove_count': summary.get('provider_remove_count', 0),
            })
        plans.sort(
            key=lambda item: (
                item['object'].status == models.ASPAChangePlanStatus.FAILED,
                item['provider_remove_count'],
                item['replacement_count'],
                item['provider_add_count'],
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

    def get_exception_lifecycle_text(self, exception):
        now = timezone.now()
        if not exception.enabled:
            return 'Disabled'
        if not exception.approved_at or not exception.approved_by:
            return 'Pending Approval'
        if exception.starts_at and exception.starts_at > now:
            return 'Scheduled'
        if exception.ends_at and exception.ends_at < now:
            return 'Expired'
        return 'Active'

    def get_binding_state_badge_class(self, state):
        if state == models.RoutingIntentTemplateBindingState.INVALID:
            return 'danger'
        if state == models.RoutingIntentTemplateBindingState.STALE:
            return 'warning text-dark'
        if state == models.RoutingIntentTemplateBindingState.PENDING:
            return 'info'
        return 'secondary'

    def get_validation_status_badge_class(self, status):
        if status == models.ValidationRunStatus.FAILED:
            return 'danger'
        if status == models.ValidationRunStatus.RUNNING:
            return 'warning text-dark'
        if status == models.ValidationRunStatus.PENDING:
            return 'info'
        return 'success'


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
            'requires_secondary_approval': plan.requires_secondary_approval,
            'ticket_reference': plan.ticket_reference,
            'change_reference': plan.change_reference,
            'maintenance_window_start': plan.maintenance_window_start,
            'maintenance_window_end': plan.maintenance_window_end,
        }
        return forms.ROAChangePlanApprovalForm(data=data, initial=initial, plan=plan)

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
                requires_secondary_approval=form.cleaned_data['requires_secondary_approval'],
                ticket_reference=form.cleaned_data['ticket_reference'],
                change_reference=form.cleaned_data['change_reference'],
                maintenance_window_start=form.cleaned_data['maintenance_window_start'],
                maintenance_window_end=form.cleaned_data['maintenance_window_end'],
                approval_notes=form.cleaned_data['approval_notes'],
                acknowledged_finding_ids=[finding.pk for finding in form.cleaned_data['acknowledged_findings']],
                previously_acknowledged_finding_ids=[
                    finding.pk for finding in form.cleaned_data['previously_acknowledged_findings']
                ],
                acknowledged_simulation_result_ids=[
                    result.pk for result in form.cleaned_data['acknowledged_simulation_results']
                ],
                lint_acknowledgement_notes=form.cleaned_data['lint_acknowledgement_notes'],
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(plan.get_absolute_url())

        messages.success(request, f'Approved ROA change plan {plan.name}.')
        return redirect(plan.get_absolute_url())


class ROAChangePlanApproveSecondaryView(ROAChangePlanActionView):
    template_name = 'netbox_rpki/changeplan_secondary_confirm.html'
    action_label = 'Secondary Approval'
    button_class = 'success'

    def get_form(self, data=None):
        return forms.ChangePlanSecondaryApprovalForm(data=data)

    def _render(self, request, plan, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': plan,
            'change_plan': plan,
            'form': form or self.get_form(),
            'return_url': self.get_return_url(request, plan),
            'action_label': self.action_label,
            'button_class': self.button_class,
        }, status=status)

    def get(self, request, pk):
        plan = self.get_plan(pk)
        return self._render(request, plan)

    def post(self, request, pk):
        plan = self.get_plan(pk)
        form = self.get_form(request.POST)
        if not form.is_valid():
            return self._render(request, plan, form=form, status=400)

        try:
            approve_roa_change_plan_secondary(
                plan,
                secondary_approved_by=self.get_requested_by(request),
                approval_notes=form.cleaned_data['approval_notes'],
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(plan.get_absolute_url())

        messages.success(request, f'Completed secondary approval for ROA change plan {plan.name}.')
        return redirect(plan.get_absolute_url())


class ROAChangePlanAcknowledgeView(ROAChangePlanActionView):
    template_name = 'netbox_rpki/roachangeplan_acknowledge.html'

    def get_form(self, data=None, *, plan):
        initial = {
            'ticket_reference': plan.ticket_reference,
            'change_reference': plan.change_reference,
        }
        return forms.ROAChangePlanLintAcknowledgementForm(data=data, initial=initial, plan=plan)

    def _render(self, request, plan, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': plan,
            'change_plan': plan,
            'form': form or self.get_form(plan=plan),
            'return_url': self.get_return_url(request, plan),
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
            acknowledge_roa_lint_findings(
                plan,
                acknowledged_by=self.get_requested_by(request),
                ticket_reference=form.cleaned_data['ticket_reference'],
                change_reference=form.cleaned_data['change_reference'],
                acknowledged_finding_ids=[finding.pk for finding in form.cleaned_data['acknowledged_findings']],
                previously_acknowledged_finding_ids=[
                    finding.pk for finding in form.cleaned_data['previously_acknowledged_findings']
                ],
                notes=form.cleaned_data['lint_acknowledgement_notes'],
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(plan.get_absolute_url())

        messages.success(request, f'Recorded lint acknowledgement(s) for {plan.name}.')
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


class ROAChangePlanSimulateView(ROAChangePlanActionView):
    template_name = 'netbox_rpki/roachangeplan_simulate.html'

    def _render(self, request, plan, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': plan,
            'change_plan': plan,
            'form': form or ConfirmationForm(),
            'return_url': self.get_return_url(request, plan),
        }, status=status)

    def get(self, request, pk):
        plan = self.get_plan(pk)
        return self._render(request, plan)

    def post(self, request, pk):
        plan = self.get_plan(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._render(request, plan, form=form, status=400)

        simulation_run = simulate_roa_change_plan(plan)
        messages.success(request, f'Recorded ROA validation simulation run {simulation_run.name}.')
        return redirect(simulation_run.get_absolute_url())


class ASPAChangePlanPreviewView(ASPAChangePlanActionView):
    template_name = 'netbox_rpki/roachangeplan_preview.html'

    def _render(self, request, plan, *, execution=None, error_text=None, status=200):
        try:
            delta = build_aspa_change_plan_delta(plan)
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
            execution, _ = preview_aspa_change_plan_provider_write(
                plan,
                requested_by=self.get_requested_by(request),
            )
        except ProviderWriteError as exc:
            return self._render(request, plan, error_text=str(exc), status=400)

        messages.success(request, f'Recorded ASPA provider preview execution {execution.name}.')
        return self._render(request, plan, execution=execution)


class ROALintFindingSuppressView(View):
    template_name = 'netbox_rpki/roalintfinding_suppress.html'

    def get_finding(self, pk):
        return get_object_or_404(models.ROALintFinding.objects.all(), pk=pk)

    def _require_permission(self, request):
        if not request.user.has_perm('netbox_rpki.change_roalintfinding'):
            raise PermissionDenied('You do not have permission to suppress ROA lint findings.')

    def get_requested_by(self, request):
        return getattr(request.user, 'username', '')

    def get(self, request, pk):
        self._require_permission(request)
        finding = self.get_finding(pk)
        form = forms.ROALintFindingSuppressForm(finding=finding)
        return render(request, self.template_name, {
            'object': finding,
            'finding': finding,
            'form': form,
            'return_url': finding.get_absolute_url(),
        })

    def post(self, request, pk):
        self._require_permission(request)
        finding = self.get_finding(pk)
        form = forms.ROALintFindingSuppressForm(request.POST, finding=finding)
        if not form.is_valid():
            return render(request, self.template_name, {
                'object': finding,
                'finding': finding,
                'form': form,
                'return_url': finding.get_absolute_url(),
            }, status=400)

        suppression = suppress_roa_lint_finding(
            finding,
            scope_type=form.cleaned_data['scope_type'],
            reason=form.cleaned_data['reason'],
            created_by=self.get_requested_by(request),
            expires_at=form.cleaned_data['expires_at'],
            notes=form.cleaned_data['notes'],
        )
        messages.success(request, f'Recorded lint suppression {suppression.name}.')
        return redirect(suppression.get_absolute_url())


class ROALintSuppressionLiftView(View):
    template_name = 'netbox_rpki/roalintsuppression_lift.html'

    def get_suppression(self, pk):
        return get_object_or_404(models.ROALintSuppression.objects.all(), pk=pk)

    def _require_permission(self, request):
        if not request.user.has_perm('netbox_rpki.change_roalintsuppression'):
            raise PermissionDenied('You do not have permission to lift ROA lint suppressions.')

    def get_requested_by(self, request):
        return getattr(request.user, 'username', '')

    def get(self, request, pk):
        self._require_permission(request)
        suppression = self.get_suppression(pk)
        form = forms.ROALintSuppressionLiftForm()
        return render(request, self.template_name, {
            'object': suppression,
            'suppression': suppression,
            'form': form,
            'return_url': suppression.get_absolute_url(),
        })

    def post(self, request, pk):
        self._require_permission(request)
        suppression = self.get_suppression(pk)
        form = forms.ROALintSuppressionLiftForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'object': suppression,
                'suppression': suppression,
                'form': form,
                'return_url': suppression.get_absolute_url(),
            }, status=400)

        lift_roa_lint_suppression(
            suppression,
            lifted_by=self.get_requested_by(request),
            lift_reason=form.cleaned_data['lift_reason'],
        )
        messages.success(request, f'Lifted lint suppression {suppression.name}.')
        return redirect(suppression.get_absolute_url())


class ASPAChangePlanApproveView(ASPAChangePlanActionView):
    template_name = 'netbox_rpki/roachangeplan_confirm.html'
    action_label = 'Approve'
    button_class = 'primary'

    def get_form(self, data=None, *, plan):
        initial = {
            'requires_secondary_approval': plan.requires_secondary_approval,
            'ticket_reference': plan.ticket_reference,
            'change_reference': plan.change_reference,
            'maintenance_window_start': plan.maintenance_window_start,
            'maintenance_window_end': plan.maintenance_window_end,
        }
        return forms.ASPAChangePlanApprovalForm(data=data, initial=initial)

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
            approve_aspa_change_plan(
                plan,
                approved_by=self.get_requested_by(request),
                requires_secondary_approval=form.cleaned_data['requires_secondary_approval'],
                ticket_reference=form.cleaned_data['ticket_reference'],
                change_reference=form.cleaned_data['change_reference'],
                maintenance_window_start=form.cleaned_data['maintenance_window_start'],
                maintenance_window_end=form.cleaned_data['maintenance_window_end'],
                approval_notes=form.cleaned_data['approval_notes'],
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(plan.get_absolute_url())

        messages.success(request, f'Approved ASPA change plan {plan.name}.')
        return redirect(plan.get_absolute_url())


class ASPAChangePlanApproveSecondaryView(ASPAChangePlanActionView):
    template_name = 'netbox_rpki/changeplan_secondary_confirm.html'
    action_label = 'Secondary Approval'
    button_class = 'success'

    def get_form(self, data=None):
        return forms.ChangePlanSecondaryApprovalForm(data=data)

    def _render(self, request, plan, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': plan,
            'change_plan': plan,
            'form': form or self.get_form(),
            'return_url': self.get_return_url(request, plan),
            'action_label': self.action_label,
            'button_class': self.button_class,
        }, status=status)

    def get(self, request, pk):
        plan = self.get_plan(pk)
        return self._render(request, plan)

    def post(self, request, pk):
        plan = self.get_plan(pk)
        form = self.get_form(request.POST)
        if not form.is_valid():
            return self._render(request, plan, form=form, status=400)

        try:
            approve_aspa_change_plan_secondary(
                plan,
                secondary_approved_by=self.get_requested_by(request),
                approval_notes=form.cleaned_data['approval_notes'],
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(plan.get_absolute_url())

        messages.success(request, f'Completed secondary approval for ASPA change plan {plan.name}.')
        return redirect(plan.get_absolute_url())


class ASPAChangePlanApplyView(ASPAChangePlanActionView):
    template_name = 'netbox_rpki/roachangeplan_confirm.html'
    action_label = 'Apply'
    button_class = 'success'

    def get(self, request, pk):
        plan = self.get_plan(pk)
        try:
            delta = build_aspa_change_plan_delta(plan)
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
            execution, _ = apply_aspa_change_plan_provider_write(
                plan,
                requested_by=self.get_requested_by(request),
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(plan.get_absolute_url())

        if execution.status == models.ValidationRunStatus.COMPLETED:
            messages.success(request, f'Applied ASPA change plan {plan.name}.')
        else:
            messages.warning(
                request,
                f'Applied ASPA change plan {plan.name}, but the follow-up provider sync did not complete successfully.',
            )
        return redirect(plan.get_absolute_url())


class ROAChangePlanRollbackBundleApproveView(ROARollbackBundleActionView):
    template_name = 'netbox_rpki/rollbackbundle_confirm.html'
    action_label = 'Approve'
    button_class = 'warning'

    def get_form(self, data=None, *, bundle):
        initial = {
            'ticket_reference': bundle.ticket_reference,
            'change_reference': bundle.change_reference,
            'maintenance_window_start': bundle.maintenance_window_start,
            'maintenance_window_end': bundle.maintenance_window_end,
            'notes': bundle.notes,
        }
        return forms.RollbackBundleApprovalForm(data=data, initial=initial)

    def _render(self, request, bundle, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': bundle,
            'rollback_bundle': bundle,
            'form': form or self.get_form(bundle=bundle),
            'return_url': self.get_return_url(request, bundle),
            'action_label': self.action_label,
            'button_class': self.button_class,
            'show_governance_inputs': True,
        }, status=status)

    def get(self, request, pk):
        bundle = self.get_bundle(pk)
        return self._render(request, bundle)

    def post(self, request, pk):
        bundle = self.get_bundle(pk)
        form = self.get_form(request.POST, bundle=bundle)
        if not form.is_valid():
            return self._render(request, bundle, form=form, status=400)

        try:
            approve_rollback_bundle(
                bundle,
                approved_by=self.get_requested_by(request),
                ticket_reference=form.cleaned_data['ticket_reference'],
                change_reference=form.cleaned_data['change_reference'],
                maintenance_window_start=form.cleaned_data['maintenance_window_start'],
                maintenance_window_end=form.cleaned_data['maintenance_window_end'],
                notes=form.cleaned_data['notes'],
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(bundle.get_absolute_url())

        messages.success(request, f'Approved rollback bundle {bundle.name}.')
        return redirect(bundle.get_absolute_url())


class ROAChangePlanRollbackBundleApplyView(ROARollbackBundleActionView):
    template_name = 'netbox_rpki/rollbackbundle_confirm.html'
    action_label = 'Apply'
    button_class = 'danger'

    def get(self, request, pk):
        bundle = self.get_bundle(pk)
        return render(request, self.template_name, {
            'object': bundle,
            'rollback_bundle': bundle,
            'delta': bundle.rollback_delta_json,
            'form': ConfirmationForm(),
            'return_url': self.get_return_url(request, bundle),
            'action_label': self.action_label,
            'button_class': self.button_class,
            'show_governance_inputs': False,
        })

    def post(self, request, pk):
        bundle = self.get_bundle(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'object': bundle,
                'rollback_bundle': bundle,
                'delta': bundle.rollback_delta_json,
                'form': form,
                'return_url': self.get_return_url(request, bundle),
                'action_label': self.action_label,
                'button_class': self.button_class,
                'show_governance_inputs': False,
            }, status=400)

        try:
            bundle = apply_roa_rollback_bundle(
                bundle,
                requested_by=self.get_requested_by(request),
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(bundle.get_absolute_url())

        followup_status = (bundle.apply_response_json or {}).get('followup_sync', {}).get('status')
        if followup_status == models.ValidationRunStatus.FAILED:
            messages.warning(request, f'Applied rollback bundle {bundle.name}, but the follow-up provider sync did not complete successfully.')
        else:
            messages.success(request, f'Applied rollback bundle {bundle.name}.')
        return redirect(bundle.get_absolute_url())


class ASPAChangePlanRollbackBundleApproveView(ASPARollbackBundleActionView):
    template_name = 'netbox_rpki/rollbackbundle_confirm.html'
    action_label = 'Approve'
    button_class = 'warning'

    def get_form(self, data=None, *, bundle):
        initial = {
            'ticket_reference': bundle.ticket_reference,
            'change_reference': bundle.change_reference,
            'maintenance_window_start': bundle.maintenance_window_start,
            'maintenance_window_end': bundle.maintenance_window_end,
            'notes': bundle.notes,
        }
        return forms.RollbackBundleApprovalForm(data=data, initial=initial)

    def _render(self, request, bundle, *, form=None, status=200):
        return render(request, self.template_name, {
            'object': bundle,
            'rollback_bundle': bundle,
            'form': form or self.get_form(bundle=bundle),
            'return_url': self.get_return_url(request, bundle),
            'action_label': self.action_label,
            'button_class': self.button_class,
            'show_governance_inputs': True,
        }, status=status)

    def get(self, request, pk):
        bundle = self.get_bundle(pk)
        return self._render(request, bundle)

    def post(self, request, pk):
        bundle = self.get_bundle(pk)
        form = self.get_form(request.POST, bundle=bundle)
        if not form.is_valid():
            return self._render(request, bundle, form=form, status=400)

        try:
            approve_rollback_bundle(
                bundle,
                approved_by=self.get_requested_by(request),
                ticket_reference=form.cleaned_data['ticket_reference'],
                change_reference=form.cleaned_data['change_reference'],
                maintenance_window_start=form.cleaned_data['maintenance_window_start'],
                maintenance_window_end=form.cleaned_data['maintenance_window_end'],
                notes=form.cleaned_data['notes'],
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(bundle.get_absolute_url())

        messages.success(request, f'Approved rollback bundle {bundle.name}.')
        return redirect(bundle.get_absolute_url())


class ASPAChangePlanRollbackBundleApplyView(ASPARollbackBundleActionView):
    template_name = 'netbox_rpki/rollbackbundle_confirm.html'
    action_label = 'Apply'
    button_class = 'danger'

    def get(self, request, pk):
        bundle = self.get_bundle(pk)
        return render(request, self.template_name, {
            'object': bundle,
            'rollback_bundle': bundle,
            'delta': bundle.rollback_delta_json,
            'form': ConfirmationForm(),
            'return_url': self.get_return_url(request, bundle),
            'action_label': self.action_label,
            'button_class': self.button_class,
            'show_governance_inputs': False,
        })

    def post(self, request, pk):
        bundle = self.get_bundle(pk)
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'object': bundle,
                'rollback_bundle': bundle,
                'delta': bundle.rollback_delta_json,
                'form': form,
                'return_url': self.get_return_url(request, bundle),
                'action_label': self.action_label,
                'button_class': self.button_class,
                'show_governance_inputs': False,
            }, status=400)

        try:
            bundle = apply_aspa_rollback_bundle(
                bundle,
                requested_by=self.get_requested_by(request),
            )
        except ProviderWriteError as exc:
            messages.error(request, str(exc))
            return redirect(bundle.get_absolute_url())

        followup_status = (bundle.apply_response_json or {}).get('followup_sync', {}).get('status')
        if followup_status == models.ValidationRunStatus.FAILED:
            messages.warning(request, f'Applied rollback bundle {bundle.name}, but the follow-up provider sync did not complete successfully.')
        else:
            messages.success(request, f'Applied rollback bundle {bundle.name}.')
        return redirect(bundle.get_absolute_url())
