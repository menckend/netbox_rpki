from netbox.filtersets import NetBoxModelFilterSet
from tenancy.filtersets import TenancyFilterSet
import netbox_rpki

# from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix


class CertificateFilterSet(NetBoxModelFilterSet, TenancyFilterSet):
    class Meta:
        model = netbox_rpki.models.Certificate
        fields = ['name', 'issuer', 'subject', 'serial', 'valid_from', 'valid_to', 'public_key', 'private_key', 'publication_url', 'ca_repository', 'rpki_org', 'self_hosted', 'tenant']

    def search(self, queryset, name, value):
        """Perform the filtered search."""
        if not value.strip():
            return queryset
        qs_filter = (
                Q(value__icontains=value)
                | Q(description__icontains=value)
        )
        return queryset.filter(qs_filter)


class OrganizationFilterSet(NetBoxModelFilterSet, TenancyFilterSet):
    class Meta:
        model = netbox_rpki.models.Organization
        fields = ['org_id', 'name', 'parent_rir', 'ext_url', 'tenant']

    def search(self, queryset, name, value):
        """Perform the filtered search."""
        if not value.strip():
            return queryset
        qs_filter = (
                Q(value__icontains=value)
                | Q(description__icontains=value)
        )
        return queryset.filter(qs_filter)


class RoaFilterSet(NetBoxModelFilterSet, TenancyFilterSet):
    class Meta:
        model = netbox_rpki.models.Roa
        fields = ['name', 'origin_as', 'valid_from', 'valid_to', 'signed_by', 'tenant']

    def search(self, queryset, name, value):
        """Perform the filtered search."""
        if not value.strip():
            return queryset
        qs_filter = (
                Q(value__icontains=value)
                | Q(description__icontains=value)
        )
        return queryset.filter(qs_filter)


class RoaPrefixFilterSet(NetBoxModelFilterSet, TenancyFilterSet):
    class Meta:
        model = netbox_rpki.models.RoaPrefix
        fields = ['prefix', 'max_length', 'roa_name', 'tenant']

    def search(self, queryset, name, value):
        """Perform the filtered search."""
        if not value.strip():
            return queryset
        qs_filter = (
                Q(value__icontains=value)
                | Q(description__icontains=value)
        )
        return queryset.filter(qs_filter)


class CertificatePrefixFilterSet(NetBoxModelFilterSet, TenancyFilterSet):
    class Meta:
        model = netbox_rpki.models.CertificatePrefix
        fields = ['prefix', 'certificate_name', 'tenant']

    def search(self, queryset, name, value):
        """Perform the filtered search."""
        if not value.strip():
            return queryset
        qs_filter = (
                Q(value__icontains=value)
                | Q(description__icontains=value)
        )
        return queryset.filter(qs_filter)


class CertificateAsnFilterSet(NetBoxModelFilterSet, TenancyFilterSet):
    class Meta:
        model = netbox_rpki.models.CertificateAsn
        fields = ['asn', 'certificate_name2', 'tenant']

    def search(self, queryset, name, value):
        """Perform the filtered search."""
        if not value.strip():
            return queryset
        qs_filter = (
                Q(value__icontains=value)
                | Q(description__icontains=value)
        )
        return queryset.filter(qs_filter)

#    def search(self, queryset, name, value):
#        """Perform the filtered search."""
