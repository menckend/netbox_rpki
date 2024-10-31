from django.urls import include, path
from utilities.urls import get_model_urls
from netbox_rpki.models import RpkiOrganization, RpkiCertificate, RpkiRoa, RpkiRoaPrefices
from netbox_rpki import  views

app_name = 'netbox_rpki'

urlpatterns = [
    # RpkiCertificate
    path('certificates/', views.RpkiCertificateListView.as_view(), name='rpkicertificate_list'),
    path('certificates/add/', views.RpkiCertificateEditView.as_view(), name='rpkicertificate_add'),
    path('certificates/<int:pk>/', views.RpkiCertificateView.as_view(), name='rpkicertificate'),
    path('certificates/<int:pk>/edit/', views.RpkiCertificateEditView.as_view(), name='rpkicertificate_edit'),
    path('certificates/<int:pk>/delete/', views.RpkiCertificateDeleteView.as_view(), name='rpkicertificate_delete'),
    path('certificates/<int:pk>/', include(get_model_urls('netbox_rpki', 'rpkicertificate'))),
    # RpkiOrganization
    path('orgs/', views.RpkiOrganizationListView.as_view(), name='rpkiOrganization_list'),
#    path('orgs/add/', views.RpkiOrganizationEditView.as_view(), name='rpkiOrganization_add'),
#    path('orgs/<int:pk>/', views.RpkiOrganizationView.as_view(), name='rpkiOrganization'),
#    path('orgs/<int:pk>/edit/', views.RpkiOrganizationEditView.as_view(), name='rpkiOrganization_edit'),
#    path('orgs/<int:pk>/delete/', views.RpkiOrganizationDeleteView.as_view(), name='rpkiOrganization_delete'),
#    path('orgs/<int:pk>/', include(get_model_urls('netbox_rpki', 'rpkiorganization'))),
    # RpkiRoa
#    path('roa/', views.RpkiRoaListView.as_view(), name='rpkiroa_list'),
#    path('roa/add/', views.RpkiRoaEditView.as_view(), name='rpkiroa_add'),
#    path('roa/<int:pk>/', views.RpkiRoaView.as_view(), name='rpkiroa'),
#    path('roa/<int:pk>/edit/', views.RpkiRoaEditView.as_view(), name='rpkiroa_edit'),
#    path('roa/<int:pk>/delete/', views.RpkiRoaDeleteView.as_view(), name='rpkiroa_delete'),
#    path('roa/<int:pk>/', include(get_model_urls('netbox_rpki', 'rpkiroa'))),
    # RpkiRoaPrefices
#    path('roaprefices/', views.RpkiRoaPreficesListView.as_view(), name='rpkiroarefices_list'),
#    path('roarefices/add/', views.RpkiRoaPreficesEditView.as_view(), name='rpkiroarefices_add'),
#    path('roarefices/<int:pk>/', views.RpkiRoaPreficesView.as_view(), name='rpkiroarefices'),
#    path('roarefices/<int:pk>/edit/', views.RpkiRoaPreficesEditView.as_view(), name='rpkiroarefices_edit'),
#    path('roarefices/<int:pk>/delete/', views.RpkiRoaPreficesDeleteView.as_view(), name='rpkiroarefices_delete'),
#    path('roarefices/<int:pk>/', include(get_model_urls('netbox_rpki', 'rpkiroarefices'))),
]
