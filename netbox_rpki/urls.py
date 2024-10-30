from django.urls import path
from utilities.urls import get_model_urls
from netbox_rpki.models import RpkiOrganization, RpkiCertificate, RpkiRoa, RpkiRoa
from netbox_rpki import  views

app_name = 'netbox_rpki'

urlpatterns = [
    path("rpkicertificate/", views.RpkiCertificateListView.as_view(), name="rpkicertificate_list"),
    path("rpkicertificate/add/", views.RpkiCertificateEditView.as_view(), name="cpkicertificate_add"),
    path("rpkicertificate/<int:pk>/", views.RpkiCertificate.as_view(), name="RpkiCertificate"),
    path("rpkicertificate/<int:pk>/edit/", views.RpkiCertificateEditView.as_view(), name="RpkiCertificate_edit"),
    path("rpkicertificate/<int:pk>/delete/", views.RpkiCertificateDeleteView.as_view(), name="RpkiCertificate_delete"),
    path('rpkicertificate/<int:pk>/', include(get_model_urls('netbox_rpki', 'rpkicertificate'))),
    path("rpkiorganization/", views.RpkiOrganizationListView.as_view(), name="rpkiorganization_list"),
    path("rpkiorganization/add/", views.RpkiOrganizationEditView.as_view(), name="rpkiorganization_add"),
    path("rpkiorganization/<int:pk>/", views.RpkiOrganization.as_view(), name="rpkiorganization"),
    path("rpkiorganization/<int:pk>/edit/", views.RpkiOrganizationEditView.as_view(), name="rpkiorganization_edit"),
    path("rpkiorganization/<int:pk>/delete/", views.RpkiOrganizationDeleteView.as_view(), name="rpkiorganization_delete"),
    path('rpkiorganization/<int:pk>/', include(get_model_urls('netbox_rpki', 'rpkiorganization'))),
    path("rpkiroa/", views.RpkiRoaListView.as_view(), name="rpkiroa_list"),
    path("rpkiroa/add/", views.RpkiRoaEditView.as_view(), name="rpkiroa_add"),
    path("rpkiroa/<int:pk>/", views.RpkiRoa.as_view(), name="rpkiroa"),
    path("rpkiroa/<int:pk>/edit/", views.RpkiRoaEditView.as_view(), name="rpkiroa_edit"),
    path("rpkiroa/<int:pk>/delete/", views.RpkiRoaDeleteView.as_view(), name="rpkiroa_delete"),
    path('rpkiroa/<int:pk>/', include(get_model_urls('netbox_rpki', 'rpkiroa'))),
    path("rpkiroaprefices/", views.RpkiRoaPreficesListView.as_view(), name="rpkiroaprefices_list"),
    path("rpkiroaprefices/add/", views.RpkiRoaPreficesEditView.as_view(), name="rpkiroaprefices_add"),
    path("rpkiroaprefices/<int:pk>/", views.RpkiRoaPrefices.as_view(), name="rpkiroaprefices"),
    path("rpkiroaprefices/<int:pk>/edit/", views.RpkiRoaPreficesEditView.as_view(), name="rpkiroaprefices_edit"),
    path("rpkiroaprefices/<int:pk>/delete/", views.RpkiRoaPreficesDeleteView.as_view(), name="rpkiroaprefices_delete"),
    path('rpkiroaprefices/<int:pk>/', include(get_model_urls('netbox_rpki', 'rpkiroaprefices'))),
]
