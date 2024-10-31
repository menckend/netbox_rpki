from django.urls import include, path
from utilities.urls import get_model_urls
from netbox_rpki.models import organization, certificate, roa, roaprefices
from netbox_rpki import  views

app_name = 'netbox_rpki'

urlpatterns = [
    # certificate
    path('certificates/', views.certificateListView.as_view(), name='certificate_list'),
    path('certificates/add/', views.certificateEditView.as_view(), name='certificate_add'),
    path('certificates/<int:pk>/', views.certificateView.as_view(), name='certificate'),
    path('certificates/<int:pk>/edit/', views.certificateEditView.as_view(), name='certificate_edit'),
    path('certificates/<int:pk>/delete/', views.certificateDeleteView.as_view(), name='certificate_delete'),
    path('certificates/<int:pk>/', include(get_model_urls('netbox_rpki', 'certificate'))),
    # organization
    path('orgs/', views.organizationListView.as_view(), name='organization_list'),
    path('orgs/add/', views.organizationEditView.as_view(), name='organization_add'),
#    path('orgs/<int:pk>/', views.organizationView.as_view(), name='organization'),
#    path('orgs/<int:pk>/edit/', views.organizationEditView.as_view(), name='organization_edit'),
#    path('orgs/<int:pk>/delete/', views.organizationDeleteView.as_view(), name='organization_delete'),
#    path('orgs/<int:pk>/', include(get_model_urls('netbox_rpki', 'organization'))),
    # roa
    path('roa/', views.roaListView.as_view(), name='roa_list'),
    path('roa/add/', views.roaEditView.as_view(), name='roa_add'),
#    path('roa/<int:pk>/', views.roaView.as_view(), name='roa'),
#    path('roa/<int:pk>/edit/', views.roaEditView.as_view(), name='roa_edit'),
#    path('roa/<int:pk>/delete/', views.roaDeleteView.as_view(), name='roa_delete'),
#    path('roa/<int:pk>/', include(get_model_urls('netbox_rpki', 'roa'))),
    # roaprefices
    path('roaprefices/', views.roapreficesListView.as_view(), name='roaprefices_list'),
#    path('roaprefices/add/', views.RpkiRoaPreficesEditView.as_view(), name='roaprefices_add'),
#    path('roaprefices/<int:pk>/', views.RpkiRoaPreficesView.as_view(), name='roaprefices'),
#    path('roaprefices/<int:pk>/edit/', views.RpkiRoaPreficesEditView.as_view(), name='roaprefices_edit'),
#    path('roaprefices/<int:pk>/delete/', views.RpkiRoaPreficesDeleteView.as_view(), name='roaprefices_delete'),
#    path('roaprefices/<int:pk>/', include(get_model_urls('netbox_rpki', 'roaprefices'))),
]
