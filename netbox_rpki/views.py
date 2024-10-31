"""Defines the 'views' used by the Django apps for serving pages of the netbox_ptov plugin"""

from netbox.views import generic
from netbox_rpki import filtersets, forms, models, tables
from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix
from django.shortcuts import render, redirect
from django.contrib import messages
import json


class CertificateView(generic.ObjectView):
    queryset = models.Certificate.objects.all()

    def get_extra_context(self, request, instance):
        roa_table = tables.RoaTable(instance.signed_by.all())
        table.configure(request)

        return {
            'signed_roas_table': roa_table,
        }


class CertificateListView(generic.ObjectListView):
    queryset = models.Certificate.objects.all()
    table = tables.CertificateTable


class CertificateEditView(generic.ObjectEditView):
    queryset = models.Certificate.objects.all()
    form = forms.CertificateForm


class CertificateDeleteView(generic.ObjectDeleteView):
    queryset = models.Certificate.objects.all()


class Organizationiew(generic.ObjectView):
    queryset = models.Organization.objects.all()


class OrganizationListView(generic.ObjectListView):
    queryset = models.Organization.objects.all()
    table = tables.OrganizationTable


class OrganizationEditView(generic.ObjectEditView):
    queryset = models.Organization.objects.all()
    form = forms.OrganizationForm


class OrganizationDeleteView(generic.ObjectDeleteView):
    queryset = models.Organization.objects.all()


class RoaPrefixView(generic.ObjectView):
    queryset = models.RoaPrefix.objects.all()


class RoaPrefixListView(generic.ObjectListView):
    queryset = models.RoaPrefix.objects.all()
    table = tables.RoaPrefixTable


class RoaPrefixEditView(generic.ObjectEditView):
    queryset = models.RoaPrefix.objects.all()
    form = forms.RoaPrefixForm


class RoaPrefixDeleteView(generic.ObjectDeleteView):
    queryset = models.RoaPrefix.objects.all()


class RoaView(generic.ObjectView):
    queryset = models.Roa.objects.all()


class RoaListView(generic.ObjectListView):
    queryset = models.Roa.objects.all()
    table = tables.RoaTable


class RoaEditView(generic.ObjectEditView):
    queryset = Roa.objects.all()
    form = forms.RoaForm


class RoaDeleteView(generic.ObjectDeleteView):
    queryset = models.Roa.objects.all()
