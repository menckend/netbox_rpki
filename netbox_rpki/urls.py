from django.urls import path
from netbox.views.generic import ObjectChangeLogView
from netbox_rpki import models, views


urlpatterns = (
    path("RpkiCertificate/", views.RpkiCertificateListView.as_view(), name="RpkiCertificate_list"),
    path("RpkiCertificate/add/", views.RpkiCertificateEditView.as_view(), name="RpkiCertificate_add"),
    path("RpkiCertificate/<int:pk>/", views.RpkiCertificate.as_view(), name="RpkiCertificate"),
    path("RpkiCertificate/<int:pk>/edit/", views.RpkiCertificateEditView.as_view(), name="RpkiCertificate_edit"),
    path("RpkiCertificate/<int:pk>/delete/", views.RpkiCertificateDeleteView.as_view(), name="RpkiCertificate_delete"),
    path(
        "RpkiCertificate/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="RpkiCertificate_changelog",
        kwargs={"model": models.RpkiCertificate},
    ),

    path("RpkiOrganization/", views.RpkiOrganizationListView.as_view(), name="RpkiOrganization_list"),
    path("RpkiOrganization/add/", views.RpkiOrganizationEditView.as_view(), name="RpkiOrganization_add"),
    path("RpkiOrganization/<int:pk>/", views.RpkiOrganization.as_view(), name="RpkiOrganization"),
    path("RpkiOrganization/<int:pk>/edit/", views.RpkiOrganizationEditView.as_view(), name="RpkiOrganization_edit"),
    path("RpkiOrganization/<int:pk>/delete/", views.RpkiOrganizationDeleteView.as_view(), name="RpkiOrganization_delete"),
    path(
        "RpkiOrganization/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="RpkiOrganization_changelog",
        kwargs={"model": models.RpkiOrganization},
    ),

    path("RpkiRoa/", views.RpkiRoaListView.as_view(), name="RpkiRoa_list"),
    path("RpkiRoa/add/", views.RpkiRoaEditView.as_view(), name="RpkiRoa_add"),
    path("RpkiRoa/<int:pk>/", views.RpkiRoa.as_view(), name="RpkiRoa"),
    path("RpkiRoa/<int:pk>/edit/", views.RpkiRoaEditView.as_view(), name="RpkiRoa_edit"),
    path("RpkiRoa/<int:pk>/delete/", views.RpkiRoaDeleteView.as_view(), name="RpkiRoa_delete"),
    path(
        "RpkiRoa/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="RpkiRoa_changelog",
        kwargs={"model": models.RpkiRoa},
    ),


    path("RpkiRoaPrefices/", views.RpkiRoaPreficesListView.as_view(), name="RpkiRoaPrefices_list"),
    path("RpkiRoaPrefices/add/", views.RpkiRoaPreficesEditView.as_view(), name="RpkiRoaPrefices_add"),
    path("RpkiRoaPrefices/<int:pk>/", views.RpkiRoaPrefices.as_view(), name="RpkiRoaPrefices"),
    path("RpkiRoaPrefices/<int:pk>/edit/", views.RpkiRoaPreficesEditView.as_view(), name="RpkiRoaPrefices_edit"),
    path("RpkiRoaPrefices/<int:pk>/delete/", views.RpkiRoaPreficesDeleteView.as_view(), name="RpkiRoaPrefices_delete"),
    path(
        "RpkiRoaPrefices/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="RpkiRoaPrefices_changelog",
        kwargs={"model": models.RpkiRoaPrefices},
    )
)
