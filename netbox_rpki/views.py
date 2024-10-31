"""Defines the 'views' used by the Django apps for serving pages of the netbox_ptov plugin"""

import netbox_rpki
from netbox.views import generic
from netbox_rpki import filtersets, forms, models, tables
from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix
from django.shortcuts import render, redirect
from django.contrib import messages
import json


class CertificateView(generic.ObjectView):
    queryset = netbox_rpki.models.Certificate.objects.all()

    def get_extra_context(self, request, instance):
        roa_table = netbox_rpki.tables.RoaTable(instance.signed_by.all())
        roa_table.configure(request)

        return {
            'signed_roas_table': roa_table,
        }


class CertificateListView(generic.ObjectListView):
    queryset = netbox_rpki.models.Certificate.objects.all()
    table = tables.CertificateTable


class CertificateEditView(generic.ObjectEditView):
    queryset = netbox_rpki.models.Certificate.objects.all()
    form = netbox_rpki.forms.CertificateForm


class CertificateDeleteView(generic.ObjectDeleteView):
    queryset = netbox_rpki.models.Certificate.objects.all()


class Organizationiew(generic.ObjectView):
    queryset = netbox_rpki.models.Organization.objects.all()


class OrganizationListView(generic.ObjectListView):
    queryset = netbox_rpki.models.Organization.objects.all()
    table = netbox_rpki.tables.OrganizationTable


class OrganizationEditView(generic.ObjectEditView):
    queryset = netbox_rpki.models.Organization.objects.all()
    form = netbox_rpki.forms.OrganizationForm


class OrganizationDeleteView(generic.ObjectDeleteView):
    queryset = netbox_rpki.models.Organization.objects.all()


class RoaPrefixView(generic.ObjectView):
    queryset = netbox_rpki.models.RoaPrefix.objects.all()


class RoaPrefixListView(generic.ObjectListView):
    queryset = netbox_rpki.models.RoaPrefix.objects.all()
    table = netbox_rpki.tables.RoaPrefixTable


class RoaPrefixEditView(generic.ObjectEditView):
    queryset = netbox_rpki.models.RoaPrefix.objects.all()
    form = netbox_rpki.forms.RoaPrefixForm


class RoaPrefixDeleteView(generic.ObjectDeleteView):
    queryset = netbox_rpki.models.RoaPrefix.objects.all()


class RoaView(generic.ObjectView):
    queryset = netbox_rpki.models.Roa.objects.all()


class RoaListView(generic.ObjectListView):
    queryset = netbox_rpki.models.Roa.objects.all()
    table = netbox_rpki.tables.RoaTable


class RoaEditView(generic.ObjectEditView):
    queryset = netbox_rpki.models.Roa.objects.all()
    form = netbox_rpki.forms.RoaForm


class RoaDeleteView(generic.ObjectDeleteView):
    queryset = netbox_rpki.models.Roa.objects.all()
