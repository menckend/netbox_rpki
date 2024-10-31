from django.urls import include, path
from utilities.urls import get_model_urls
from netbox_rpki.models import organization, certificate, roa, roaprefices
from netbox_rpki import  views

app_name = 'netbox_rpki'

urlpatterns = [
    # certificate
    path('certificates/', views.CertificateListView.as_view(), name='certificate_list'),
    path('certificates/add/', views.CertificateEditView.as_view(), name='certificate_add'),
    path('certificates/<int:pk>/', views.CertificateView.as_view(), name='certificate'),
    path('certificates/<int:pk>/edit/', views.CertificateEditView.as_view(), name='certificate_edit'),
    path('certificates/<int:pk>/delete/', views.certificateDeleteView.as_view(), name='certificate_delete'),
    path('certificates/<int:pk>/', include(get_model_urls('netbox_rpki', 'certificate'))),
    # organization
    path('orgs/', views.OrganizationListView.as_view(), name='organization_list'),
    path('orgs/add/', views.OrganizationEditView.as_view(), name='organization_add'),
    path('orgs/<int:pk>/', views.OrganizationView.as_view(), name='organization'),
    path('orgs/<int:pk>/edit/', views.OrganizationEditView.as_view(), name='organization_edit'),
    path('orgs/<int:pk>/delete/', views.OrganizationDeleteView.as_view(), name='organization_delete'),
    path('orgs/<int:pk>/', include(get_model_urls('netbox_rpki', 'organization'))),
    # roa
    path('roa/', views.RoaListView.as_view(), name='roa_list'),
    path('roa/add/', views.RoaEditView.as_view(), name='roa_add'),
    path('roa/<int:pk>/', views.RoaView.as_view(), name='roa'),
    path('roa/<int:pk>/edit/', views.RoaEditView.as_view(), name='roa_edit'),
    path('roa/<int:pk>/delete/', views.RoaDeleteView.as_view(), name='roa_delete'),
    path('roa/<int:pk>/', include(get_model_urls('netbox_rpki', 'roa'))),
    # roaprefix
    path('roaprefices/', views.RoaPrefixListView.as_view(), name='roaprefix_list'),
    path('roaprefices/add/', views.RoaPrefixEditView.as_view(), name='roaprefix_add'),
    path('roaprefices/<int:pk>/', views.RoaPrefixView.as_view(), name='roaprefix'),
    path('roaprefices/<int:pk>/edit/', views.RoaPrefixEditView.as_view(), name='roaprefix_edit'),
    path('roaprefices/<int:pk>/delete/', views.RoaPrefixDeleteView.as_view(), name='roaprefix_delete'),
    path('roaprefices/<int:pk>/', include(get_model_urls('netbox_rpki', 'roaprefix'))),
]
