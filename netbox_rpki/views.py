import netbox_rpki
from netbox.views import generic
from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix, CertificatePrefix, CertificateAsn
from netbox_rpki.forms import CertificateForm, OrganizationForm, RoaForm, RoaPrefixForm, CertificatePrefixForm, CertificateAsnForm
from netbox_rpki.tables import CertificateTable, OrganizationTable, RoaTable, RoaPrefixTable, CertificatePrefixTable, CertificateAsnTable
from netbox_rpki import filtersets, forms, tables


class CertificateView(generic.ObjectView):
    queryset = netbox_rpki.models.Certificate.objects.all()

    def get_extra_context(self, request, instance):
        certificateprefix_table = netbox_rpki.tables.CertificatePrefixTable(instance.prefix.all())
        certificateprefix_table.configure(request)
        certificateasn_table = netbox_rpki.tables.CertificateAsnTable(instance.asn.all())
        certificateasn_table.configure(request)
        roa_table = netbox_rpki.tables.RoaTable(instance.roas.all())
        roa_table.configure(request)
        
        return {
            'signed_roas_table': roa_table,
            'assigned_asns_table': certificateasn_table,
            'assigned_prefices_table': certificateprefix_table
        }


class CertificateListView(generic.ObjectListView):
    queryset = Certificate.objects.all()
    filterset = filtersets.CertificateFilterSet
    filterset_form = forms.CertificateFilterForm
    table = tables.CertificateTable


class CertificateEditView(generic.ObjectEditView):
    queryset = Certificate.objects.all()
    form = CertificateForm


class CertificateDeleteView(generic.ObjectDeleteView):
    queryset = Certificate.objects.all()


class OrganizationView(generic.ObjectView):
    queryset = Organization.objects.all()


    def get_extra_context(self, request, instance):
        mycerts_table = tables.CertificateTable(instance.certificates.all())
        mycerts_table.configure(request)

        return {
            'certificates_table': mycerts_table,
        }


class OrganizationListView(generic.ObjectListView):
    queryset = Organization.objects.all()
    table = OrganizationTable


class OrganizationEditView(generic.ObjectEditView):
    queryset = Organization.objects.all()
    form = OrganizationForm


class OrganizationDeleteView(generic.ObjectDeleteView):
    queryset = Organization.objects.all()


class RoaPrefixView(generic.ObjectView):
    queryset = RoaPrefix.objects.all()


class RoaPrefixListView(generic.ObjectListView):
    queryset = RoaPrefix.objects.all()
    table = RoaPrefixTable


class RoaPrefixEditView(generic.ObjectEditView):
    queryset = RoaPrefix.objects.all()
    form = RoaPrefixForm


class RoaPrefixDeleteView(generic.ObjectDeleteView):
    queryset = RoaPrefix.objects.all()


class RoaView(generic.ObjectView):
    queryset = Roa.objects.all()


    def get_extra_context(self, request, instance):
        myroaprefix_table = netbox_rpki.tables.RoaPrefixTable(instance.prefices.all())
        myroaprefix_table.configure(request)

        return {
            'myroaprefices_table': myroaprefix_table
        }


class RoaListView(generic.ObjectListView):
    queryset = Roa.objects.all()
    table = RoaTable


class RoaEditView(generic.ObjectEditView):
    queryset = Roa.objects.all()
    form = RoaForm


class RoaDeleteView(generic.ObjectDeleteView):
    queryset = Roa.objects.all()


class CertificatePrefixView(generic.ObjectView):
    queryset = CertificatePrefix.objects.all()


class CertificatePrefixListView(generic.ObjectListView):
    queryset = CertificatePrefix.objects.all()
    table = CertificatePrefixTable


class CertificatePrefixEditView(generic.ObjectEditView):
    queryset = CertificatePrefix.objects.all()
    form = CertificatePrefixForm


class CertificatePrefixDeleteView(generic.ObjectDeleteView):
    queryset = CertificatePrefix.objects.all()


class RoaView(generic.ObjectView):
    queryset = Roa.objects.all()


    def get_extra_context(self, request, instance):
        certificateprefix_table = netbox_rpki.tables.CertificatePrefixTable(instance.prefices.all())
        certificateprefix_table.configure(request)

        return {
            'certificateprefices_table': certificateprefix_table
        }



class CertificateAsnView(generic.ObjectView):
    queryset = CertificateAsn.objects.all()


class CertificateAsnListView(generic.ObjectListView):
    queryset = CertificateAsn.objects.all()
    table = CertificateAsnTable


class CertificateAsnEditView(generic.ObjectEditView):
    queryset = CertificateAsn.objects.all()
    form = CertificateAsnForm


class CertificateAsnDeleteView(generic.ObjectDeleteView):
    queryset = CertificateAsn.objects.all()


class CertificateAsn(generic.ObjectView):
    queryset = Certificate.objects.all()



class CertificatePrefixView(generic.ObjectView):
    queryset = CertificatePrefix.objects.all()


class CertificatePrefixListView(generic.ObjectListView):
    queryset = CertificatePrefix.objects.all()
    table = CertificatePrefixTable


class CertificatePrefixEditView(generic.ObjectEditView):
    queryset = CertificatePrefix.objects.all()
    form = CertificatePrefixForm


class CertificatePrefixDeleteView(generic.ObjectDeleteView):
    queryset = CertificatePrefix.objects.all()


class CertificatePrefix(generic.ObjectView):
    queryset = Certificate.objects.all()



















