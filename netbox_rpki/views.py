"""Defines the 'views' used by the Django apps for serving pages of the netbox_ptov plugin"""

from netbox.views import generic
from netbox_rpki import filtersets, forms, models, tables
from netbox_rpki.models import RpkiCertificate, RpkiOrganization, RpkiRoa, RpkiRoaPrefices
from django.shortcuts import render, redirect
from django.contrib import messages
import json


class certificateView(generic.ObjectView):
    queryset = models.certificate.objects.all()

    def get_extra_context(self, request, instance):
        table = tables.roaTable(instance.signedBy.all())
        table.configure(request)

        return {
            'roas_table': table,
        }


class certificateListView(generic.ObjectListView):
    queryset = models.certificate.objects.all()
    table = tables.certificateTable


class certificateEditView(generic.ObjectEditView):
    queryset = models.certificate.objects.all()
    form = forms.certificateForm


class certificateDeleteView(generic.ObjectDeleteView):
    queryset = models.certificate.objects.all()


class organizationiew(generic.ObjectView):
    queryset = models.organization.objects.all()


class organizationListView(generic.ObjectListView):
    queryset = models.organization.objects.all()
    table = tables.organizationTable


class organizationEditView(generic.ObjectEditView):
    queryset = models.organization.objects.all()
    form = forms.organizationForm


class organizationDeleteView(generic.ObjectDeleteView):
    queryset = models.organization.objects.all()


class roapreficesView(generic.ObjectView):
    queryset = models.roaprefices.objects.all()


class roapreficesListView(generic.ObjectListView):
    queryset = models.roaprefices.objects.all()
    table = tables.roapreficesTable


class roapreficesEditView(generic.ObjectEditView):
    queryset = models.roaprefices.objects.all()
    form = forms.roapreficesForm


class roapreficesDeleteView(generic.ObjectDeleteView):
    queryset = models.roaprefices.objects.all()


class roaView(generic.ObjectView):
    queryset = models.roa.objects.all()


class roaListView(generic.ObjectListView):
    queryset = models.roa.objects.all()
    table = tables.roaTable


class roaEditView(generic.ObjectEditView):
    queryset = models.roa.objects.all()
    form = forms.roaForm


class roaDeleteView(generic.ObjectDeleteView):
    queryset = models.roa.objects.all()
