from netbox.filtersets import NetBoxModelFilterSet

import netbox_rpki

# from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix


class CertificateFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = netbox_rpki.models.Certificate
        fields = ['name', 'issuer', 'subject', 'serial', 'valid_from', 'valid_to', 'public_key', 'private_key', 'publication_url', 'ca_repository', 'rpki_org', 'self_hosted']

    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class OrganizationFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = netbox_rpki.models.Organization
        fields = ['org_id', 'name', 'parent_rir', 'ext_url']

    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class RoaFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = netbox_rpki.models.Roa
        fields = ['name', 'origin_as', 'valid_from', 'valid_to', 'signed_by']

    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)


class RoaPrefixFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = netbox_rpki.models.RoaPrefix
        fields = ['prefix', 'max_length', 'roa_name']

    def search(self, queryset, name, value):
        return queryset.filter(description__icontains=value)
