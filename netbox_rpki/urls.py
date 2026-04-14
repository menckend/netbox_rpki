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
    if spec.registry_key == 'organization':
        urlpatterns.append(
            path(
                f'{path_prefix}/<int:pk>/run-aspa-reconciliation/',
                views.OrganizationRunAspaReconciliationView.as_view(),
                name='organization_run_aspa_reconciliation',
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
                    f'{path_prefix}/<int:pk>/apply/',
                    views.ROAChangePlanApplyView.as_view(),
                    name='roachangeplan_apply',
                ),
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
                    f'{path_prefix}/<int:pk>/apply/',
                    views.ASPAChangePlanApplyView.as_view(),
                    name='aspachangeplan_apply',
                ),
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
]
for object_spec in VIEW_OBJECT_SPECS:
    urlpatterns.extend(build_object_urlpatterns(object_spec))
