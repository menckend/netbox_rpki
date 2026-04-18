from django.urls import include, path
from utilities.urls import get_model_urls

from netbox_rpki import views
from netbox_rpki.object_registry import VIEW_OBJECT_SPECS

app_name = 'netbox_rpki'


def build_object_urlpatterns(spec):
    path_prefix = spec.routes.resolved_path_prefix
    route_slug = spec.routes.slug
    list_view = getattr(views, spec.view.list_class_name)
    detail_view = getattr(views, spec.view.detail_class_name)
    urlpatterns = [
        path(f'{path_prefix}/', list_view.as_view(), name=f'{route_slug}_list'),
        path(f'{path_prefix}/<int:pk>/', detail_view.as_view(), name=route_slug),
    ]
    if spec.registry_key == 'rpkiprovideraccount':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/sync/',
                views.ProviderAccountSyncView.as_view(),
                name='provideraccount_sync',
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/test-connection/',
                views.ProviderAccountCredentialValidationView.as_view(),
                name='provideraccount_test_connection',
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/export/lifecycle/',
                views.ProviderAccountLifecycleExportView.as_view(),
                name='provideraccount_export_lifecycle',
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/export/timeline/',
                views.ProviderAccountTimelineExportView.as_view(),
                name='provideraccount_export_timeline',
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/timeline/',
                views.ProviderAccountTimelineView.as_view(),
                name='provideraccount_timeline',
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/publication-diff-summary/',
                views.ProviderAccountPublicationDiffSummaryView.as_view(),
                name='provideraccount_publication_diff_summary',
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/summary/',
                views.ProviderAccountSummaryView.as_view(),
                name='provideraccount_summary',
            )
        )
    if spec.registry_key == 'organization':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/run-aspa-reconciliation/',
                views.OrganizationRunAspaReconciliationView.as_view(),
                name='organization_run_aspa_reconciliation',
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/create-bulk-intent-run/',
                views.OrganizationCreateBulkIntentRunView.as_view(),
                name='organization_create_bulk_intent_run',
            )
        )
    if spec.registry_key == 'routingintenttemplatebinding':
        urlpatterns.extend(
            (
                path(
                    f'{path_prefix}/<int:pk>/preview/',
                    views.RoutingIntentTemplateBindingPreviewView.as_view(),
                    name='routingintenttemplatebinding_preview',
                ),
                path(
                    f'{path_prefix}/<int:pk>/regenerate/',
                    views.RoutingIntentTemplateBindingRegenerateView.as_view(),
                    name='routingintenttemplatebinding_regenerate',
                ),
            )
        )
    if spec.registry_key == 'routingintentprofile':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/run/',
                views.RoutingIntentProfileRunView.as_view(),
                name='routingintentprofile_run',
            )
        )
    if spec.registry_key == 'routingintentexception':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/approve/',
                views.RoutingIntentExceptionApproveView.as_view(),
                name='routingintentexception_approve',
            )
        )
    if spec.registry_key == 'delegatedpublicationworkflow':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/approve/',
                views.DelegatedPublicationWorkflowApproveView.as_view(),
                name='delegatedpublicationworkflow_approve',
            )
        )
    if spec.registry_key == 'roachangeplan':
        urlpatterns.extend(
            (
                path(
                    f'{path_prefix}/<int:pk>/preview/',
                    views.ROAChangePlanPreviewView.as_view(),
                    name='roachangeplan_preview',
                ),
                path(
                    f'{path_prefix}/<int:pk>/acknowledge-lint/',
                    views.ROAChangePlanAcknowledgeView.as_view(),
                    name='roachangeplan_acknowledge_lint',
                ),
                path(
                    f'{path_prefix}/<int:pk>/approve/',
                    views.ROAChangePlanApproveView.as_view(),
                    name='roachangeplan_approve',
                ),
                path(
                    f'{path_prefix}/<int:pk>/approve-secondary/',
                    views.ROAChangePlanApproveSecondaryView.as_view(),
                    name='roachangeplan_approve_secondary',
                ),
                path(
                    f'{path_prefix}/<int:pk>/apply/',
                    views.ROAChangePlanApplyView.as_view(),
                    name='roachangeplan_apply',
                ),
                path(
                    f'{path_prefix}/<int:pk>/simulate/',
                    views.ROAChangePlanSimulateView.as_view(),
                    name='roachangeplan_simulate',
                ),
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/summary/',
                views.ROAChangePlanSummaryView.as_view(),
                name='roachangeplan_summary',
            )
        )
    if spec.registry_key == 'roalintfinding':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/suppress/',
                views.ROALintFindingSuppressView.as_view(),
                name='roalintfinding_suppress',
            )
        )
    if spec.registry_key == 'roalintsuppression':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/lift/',
                views.ROALintSuppressionLiftView.as_view(),
                name='roalintsuppression_lift',
            )
        )
    if spec.registry_key == 'aspareconciliationrun':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/create-plan/',
                views.ASPAReconciliationRunCreatePlanView.as_view(),
                name='aspareconciliationrun_create_plan',
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/summary/',
                views.ASPAReconciliationRunSummaryView.as_view(),
                name='aspareconciliationrun_summary',
            )
        )
    if spec.registry_key == 'roareconciliationrun':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/create-plan/',
                views.ROAReconciliationRunCreatePlanView.as_view(),
                name='roareconciliationrun_create_plan',
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/summary/',
                views.ROAReconciliationRunSummaryView.as_view(),
                name='roareconciliationrun_summary',
            )
        )
    if spec.registry_key == 'bulkintentrun':
        urlpatterns.extend(
            (
                path(
                    f'{path_prefix}/<int:pk>/approve/',
                    views.BulkIntentRunApproveView.as_view(),
                    name='bulkintentrun_approve',
                ),
                path(
                    f'{path_prefix}/<int:pk>/approve-secondary/',
                    views.BulkIntentRunApproveSecondaryView.as_view(),
                    name='bulkintentrun_approve_secondary',
                ),
            )
        )
    if spec.registry_key == 'aspachangeplan':
        urlpatterns.extend(
            (
                path(
                    f'{path_prefix}/<int:pk>/preview/',
                    views.ASPAChangePlanPreviewView.as_view(),
                    name='aspachangeplan_preview',
                ),
                path(
                    f'{path_prefix}/<int:pk>/approve/',
                    views.ASPAChangePlanApproveView.as_view(),
                    name='aspachangeplan_approve',
                ),
                path(
                    f'{path_prefix}/<int:pk>/approve-secondary/',
                    views.ASPAChangePlanApproveSecondaryView.as_view(),
                    name='aspachangeplan_approve_secondary',
                ),
                path(
                    f'{path_prefix}/<int:pk>/apply/',
                    views.ASPAChangePlanApplyView.as_view(),
                    name='aspachangeplan_apply',
                ),
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/summary/',
                views.ASPAChangePlanSummaryView.as_view(),
                name='aspachangeplan_summary',
            )
        )
    if spec.registry_key == 'roachangeplanrollbackbundle':
        urlpatterns.extend(
            (
                path(
                    f'{path_prefix}/<int:pk>/approve/',
                    views.ROAChangePlanRollbackBundleApproveView.as_view(),
                    name='roachangeplanrollbackbundle_approve',
                ),
                path(
                    f'{path_prefix}/<int:pk>/apply/',
                    views.ROAChangePlanRollbackBundleApplyView.as_view(),
                    name='roachangeplanrollbackbundle_apply',
                ),
            )
        )
    if spec.registry_key == 'aspachangeplanrollbackbundle':
        urlpatterns.extend(
            (
                path(
                    f'{path_prefix}/<int:pk>/approve/',
                    views.ASPAChangePlanRollbackBundleApproveView.as_view(),
                    name='aspachangeplanrollbackbundle_approve',
                ),
                path(
                    f'{path_prefix}/<int:pk>/apply/',
                    views.ASPAChangePlanRollbackBundleApplyView.as_view(),
                    name='aspachangeplanrollbackbundle_apply',
                ),
            )
        )
    if spec.registry_key == 'providersnapshot':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/compare/',
                views.ProviderSnapshotCompareView.as_view(),
                name='providersnapshot_compare',
            )
        )
        urlpatterns.append(
            path(
                f'{path_prefix}/summary/',
                views.ProviderSnapshotSummaryView.as_view(),
                name='providersnapshot_summary',
            )
        )
    if spec.registry_key == 'validatorinstance':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/history-summary/',
                views.ValidatorInstanceHistorySummaryView.as_view(),
                name='validatorinstance_history_summary',
            )
        )
    if spec.registry_key == 'telemetrysource':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/history-summary/',
                views.TelemetrySourceHistorySummaryView.as_view(),
                name='telemetrysource_history_summary',
            )
        )
    if spec.view.edit_class_name is not None:
        edit_view = getattr(views, spec.view.edit_class_name)
        urlpatterns.append(path(f'{path_prefix}/add/', edit_view.as_view(), name=f'{route_slug}_add'))
        urlpatterns.append(path(f'{path_prefix}/<int:pk>/edit/', edit_view.as_view(), name=f'{route_slug}_edit'))
    if spec.view.delete_class_name is not None:
        delete_view = getattr(views, spec.view.delete_class_name)
        urlpatterns.append(path(f'{path_prefix}/<int:pk>/delete/', delete_view.as_view(), name=f'{route_slug}_delete'))
    urlpatterns.append(
        path(
            f'{path_prefix}/<int:pk>/',
            include(get_model_urls('netbox_rpki', spec.model._meta.model_name)),
        )
    )

    return urlpatterns
urlpatterns = [
    path('operations/', views.OperationsDashboardView.as_view(), name='operations_dashboard'),
    path('operations/export/', views.OperationsDashboardExportView.as_view(), name='operations_export'),
    path('intent/authority/', views.IntentAuthorityMapView.as_view(), name='intent_authority_map'),
    path('irr/divergence/', views.IrrDivergenceDashboardView.as_view(), name='irr_divergence_dashboard'),
]
for object_spec in VIEW_OBJECT_SPECS:
    urlpatterns.extend(build_object_urlpatterns(object_spec))
