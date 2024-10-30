"""Defines the 'views' used by the Django apps for serving pages of the netbox_ptov plugin"""

from netbox.views import generic
from netbox_rpki import filtersets, forms, models, tables
from netbox_rpki.models import RpkiCertificate, RpkiOrganization, RpkiRoa, RpkiRoaPrefices
from django.shortcuts import render, redirect
from django.contrib import messages
import json


class RpkiCertificateView(generic.ObjectView):
    queryset = models.RpkiCertificate.objects.all()

    def get_extra_context(self, request, instance):
        table = tables.rpkiRoaTable(instance.signedBy.all())
        table.configure(request)

        return {
            'roas_table': table,
        }


class RpkiCertificateListView(generic.ObjectListView):
    queryset = models.RpkiCertificate.objects.all()
    table = tables.RpkiCertificateTable


class RpkiCertificateEditView(generic.ObjectEditView):
    queryset = models.RpkiCertificate.objects.all()
    form = forms.RpkiCertificateForm


class RpkiCertificateDeleteView(generic.ObjectDeleteView):
    queryset = models.RpkiCertificate.objects.all()


class RpkiOrganizationiew(generic.ObjectView):
    queryset = models.RpkiOrganization.objects.all()


class RpkiOrganizationListView(generic.ObjectListView):
    queryset = models.RpkiOrganization.objects.all()
    table = tables.RpkiOrganizationTable


class RpkiOrganizationEditView(generic.ObjectEditView):
    queryset = models.RpkiOrganization.objects.all()
    form = forms.RpkiOrganizationForm


class RpkiOrganizationDeleteView(generic.ObjectDeleteView):
    queryset = models.RpkiOrganization.objects.all()


class RpkiRoaPreficesView(generic.ObjectView):
    queryset = models.RpkiRoaPrefices.objects.all()


class RpkiRoaPreficesListView(generic.ObjectListView):
    queryset = models.RpkiRoaPrefices.objects.all()
    table = tables.RpkiRoaPreficesTable


class RpkiRoaPreficesEditView(generic.ObjectEditView):
    queryset = models.RpkiRoaPrefices.objects.all()
    form = forms.RpkiRoaPreficesForm


class RpkiRoaPreficesDeleteView(generic.ObjectDeleteView):
    queryset = models.RpkiRoaPrefices.objects.all()


class RpkiRoaView(generic.ObjectView):
    queryset = models.RpkiRoa.objects.all()


class RpkiRoaListView(generic.ObjectListView):
    queryset = models.RpkiRoa.objects.all()
    table = tables.RpkiRoaTable


class RpkiRoaEditView(generic.ObjectEditView):
    queryset = models.RpkiRoa.objects.all()
    form = forms.RpkiRoaForm


class RpkiRoaDeleteView(generic.ObjectDeleteView):
    queryset = models.RpkiRoa.objects.all()
