from netbox.views import generic
from netbox_rpki import models, forms, tables, filtersets
from django.shortcuts import get_object_or_404


class CertificateView(generic.ObjectView):
    queryset = models.Certificate.objects.all()

    def get_extra_context(self, request, instance):
        certificateprefix_table = tables.CertificatePrefixTable(instance.CertificateToPrefixTable.all())
        certificateprefix_table.configure(request)
        certificateasn_table = tables.CertificateAsnTable(instance.CertificatetoASNTable.all())
        certificateasn_table.configure(request)
        roa_table = tables.RoaTable(instance.roas.all())
        roa_table.configure(request)

        return {
            'signed_roas_table': roa_table,
            'assigned_asns_table': certificateasn_table,
            'assigned_prefices_table': certificateprefix_table
        }


class CertificateListView(generic.ObjectListView):
    queryset = models.Certificate.objects.all()
    filterset = filtersets.CertificateFilterSet
    filterset_form = forms.CertificateFilterForm
    table = tables.CertificateTable


class CertificateEditView(generic.ObjectEditView):
    queryset = models.Certificate.objects.all()
    form = forms.CertificateForm


class CertificateDeleteView(generic.ObjectDeleteView):
    queryset = models.Certificate.objects.all()


class OrganizationView(generic.ObjectView):
    queryset = models.Organization.objects.all()

    def get_extra_context(self, request, instance):
        mycerts_table = tables.CertificateTable(instance.certificates.all())
        mycerts_table.configure(request)

        return {
            'certificates_table': mycerts_table,
        }


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

    def get_extra_context(self, request, instance):
        roaprefix_table = tables.RoaPrefixTable(instance.RoaToPrefixTable.all())
        roaprefix_table.configure(request)

        return {
            'myroaprefices_table': roaprefix_table
        }


class RoaListView(generic.ObjectListView):
    queryset = models.Roa.objects.all()
    table = tables.RoaTable


class RoaEditView(generic.ObjectEditView):
    queryset = models.Roa.objects.all()
    form = forms.RoaForm


class RoaDeleteView(generic.ObjectDeleteView):
    queryset = models.Roa.objects.all()


class CertificatePrefixView(generic.ObjectView):
    queryset = models.CertificatePrefix.objects.all()


class CertificatePrefixListView(generic.ObjectListView):
    queryset = models.CertificatePrefix.objects.all()
    table = tables.CertificatePrefixTable


class CertificatePrefixEditView(generic.ObjectEditView):
    queryset = models.CertificatePrefix.objects.all()
    form = forms.CertificatePrefixForm


class CertificatePrefixDeleteView(generic.ObjectDeleteView):
    queryset = models.CertificatePrefix.objects.all()


class CertificateAsnView(generic.ObjectView):
    queryset = models.CertificateAsn.objects.all()


class CertificateAsnListView(generic.ObjectListView):
    queryset = models.CertificateAsn.objects.all()
    table = tables.CertificateAsnTable


class CertificateAsnEditView(generic.ObjectEditView):
    queryset = models.CertificateAsn.objects.all()
    form = forms.CertificateAsnForm


class CertificateAsnDeleteView(generic.ObjectDeleteView):
    queryset = models.CertificateAsn.objects.all()
