from django.urls import include, path
from utilities.urls import get_model_urls

from netbox_rpki import views
from netbox_rpki.object_registry import VIEW_OBJECT_SPECS

app_name = 'netbox_rpki'

OBJECT_UI_PATH_PREFIXES = {
    'certificate': 'certificate',
    'organization': 'orgs',
    'roa': 'roa',
    'roaprefix': 'roaprefixes',
    'certificateprefix': 'certificateprefixes',
    'certificateasn': 'certificateasns',
}


def build_object_urlpatterns(spec):
    path_prefix = OBJECT_UI_PATH_PREFIXES.get(spec.key, f'{spec.routes.slug}s')
    route_slug = spec.routes.slug
    list_view = getattr(views, spec.view.list_class_name)
    detail_view = getattr(views, spec.view.detail_class_name)
    urlpatterns = [
        path(f'{path_prefix}/', list_view.as_view(), name=f'{route_slug}_list'),
        path(f'{path_prefix}/<int:pk>/', detail_view.as_view(), name=route_slug),
    ]
    if spec.view.edit_class_name is not None:
        edit_view = getattr(views, spec.view.edit_class_name)
        urlpatterns.append(path(f'{path_prefix}/add/', edit_view.as_view(), name=f'{route_slug}_add'))
        urlpatterns.append(path(f'{path_prefix}/<int:pk>/edit/', edit_view.as_view(), name=f'{route_slug}_edit'))
    if spec.view.delete_class_name is not None:
        delete_view = getattr(views, spec.view.delete_class_name)
        urlpatterns.append(path(f'{path_prefix}/<int:pk>/delete/', delete_view.as_view(), name=f'{route_slug}_delete'))
    urlpatterns.append(path(f'{path_prefix}/<int:pk>/', include(get_model_urls('netbox_rpki', spec.key))))

    return urlpatterns
urlpatterns = []
for object_spec in VIEW_OBJECT_SPECS:
    urlpatterns.extend(build_object_urlpatterns(object_spec))
