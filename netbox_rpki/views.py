import netbox_rpki
from netbox.views import generic
from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix
from netbox_rpki.forms import CertificateForm, OrganizationForm, RoaForm, RoaPrefixForm
from netbox_rpki.tables import CertificateTable, OrganizationTable, RoaTable, RoaPrefixTable


class CertificateView(generic.ObjectView):
    queryset = netbox_rpki.models.Certificate.objects.all()

    def get_extra_context(self, request, instance):
        roa_table = netbox_rpki.tables.RoaTable(instance.roas.all())
        roa_table.configure(request)

        return {
            'signed_roas_table': roa_table,
        }


class CertificateListView(generic.ObjectListView):
    queryset = Certificate.objects.all()
    table = CertificateTable


class CertificateEditView(generic.ObjectEditView):
    queryset = Certificate.objects.all()
    form = CertificateForm


class CertificateDeleteView(generic.ObjectDeleteView):
    queryset = Certificate.objects.all()


class OrganizationView(generic.ObjectView):
    queryset = Organization.objects.all()


    def get_extra_context(self, request, instance):
        mycerts_table = netbox_rpki.tables.CertificateTable(instance.certificates.all())
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
        roaprefix_table = netbox_rpki.tables.RoaPrefixTable(instance.prefices.all())
        roaprefix_table.configure(request)

        return {
            'roaprefices_table': roaprefix_table
        }


class RoaListView(generic.ObjectListView):
    queryset = Roa.objects.all()
    table = RoaTable


class RoaEditView(generic.ObjectEditView):
    queryset = Roa.objects.all()
    form = RoaForm


class RoaDeleteView(generic.ObjectDeleteView):
    queryset = Roa.objects.all()
