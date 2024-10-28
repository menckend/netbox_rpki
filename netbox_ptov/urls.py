"""Django URLs for netbox_ptov plugin

Defines the path objects used by Django/Netbox when serving the pages of the netbox_ptov plugin."""

from django.urls import path
from netbox.views.generic import ObjectChangeLogView

from netbox_ptov import models, views


urlpatterns = (
    path("golabs/", views.golab, name="golab"),
    path("gns3srvs/", views.gns3srvListView.as_view(), name="gns3srv_list"),
    path("gns3srvs/add/", views.gns3srvEditView.as_view(), name="gns3srv_add"),
    path("gns3srvs/<int:pk>/", views.gns3srvView.as_view(), name="gns3srv"),
    path("gns3srvs/<int:pk>/edit/", views.gns3srvEditView.as_view(), name="gns3srv_edit"),
    path("gns3srvs/<int:pk>/delete/", views.gns3srvDeleteView.as_view(), name="gns3srv_delete"),
    path(
        "gns3srvs/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="gns3srv_changelog",
        kwargs={"model": models.gns3srv},
    ),
    path("ptovjobs/", views.ptovjobListView.as_view(), name="ptovjob_list"),
    path("ptovjobs/add/", views.ptovjobEditView.as_view(), name="ptovjob_add"),
    path("ptovjobs/<int:pk>/", views.ptovjobView.as_view(), name="ptovjob"),
    path("ptovjobs/<int:pk>/edit/", views.ptovjobEditView.as_view(), name="ptovjob_edit"),
    path("ptovjobs/<int:pk>/delete/", views.ptovjobDeleteView.as_view(), name="ptovjob_delete"),
    path(
        "ptovjobs/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="ptovjob_changelog",
        kwargs={"model": models.ptovjob},
    ),
    path("switchtojobs/", views.switchtojobListView.as_view(), name="switchtojob_list"),
    path("switchtojobs/add/", views.switchtojobEditView.as_view(), name="switchtojob_add"),
    path("switchtojobs/<int:pk>/", views.switchtojobView.as_view(), name="switchtojob"),
    path('switchtojobs/<int:pk>/', views.switchtojobView.as_view(), name="switchtojob"),
    path("switchtojobs/<int:pk>/edit/", views.switchtojobEditView.as_view(), name="switchtojob_edit"),
    path("switchtojobs/<int:pk>/delete/", views.switchtojobDeleteView.as_view(), name="switchtojob_delete"),
    path(
        "switchtojobs/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="switchtojob_changelog",
        kwargs={"model": models.switchtojob},
    ),
)
