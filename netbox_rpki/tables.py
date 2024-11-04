
import django_tables2 as tables
from netbox.tables import NetBoxTable
# , ChoiceFieldColumn
import netbox_rpki
# from netbox_rpki.models import Certificate, Organization, Roa, RoaPrefix


class CertificateTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.Certificate
        fields = ("pk", "id", "name", "issuer", "subject", "serial", "valid_from", "valid_to", "auto_renews", "publicKey", "private_key", "publication_url", "ca_repository", "self_hosted", "rpki_org")
        default_columns = ("name", "issuer", "subject", "serial", "valid_from", "valid_to", "auto_renews", "publicKey", "private_key", "publication_url;", "ca_repository", "self_hosted", "rpki_org")


class OrganizationTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.Organization
        fields = ("pk", "id", "org_id", "name", "parent_rir", "ext_url")
        default_columns = ("org_id", "name","parent_rir", "ext_url")


class RoaTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.Roa
        fields = ("pk", "id", 'name', "origin_as", "valid_from", "valid_to", "auto_renews", "signed_by")
        default_columns = ("name", "origin_as", "valid_from", "valid_to", "auto_renews", "signed_by")


class RoaPrefixTable(NetBoxTable):
    pk = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.RoaPrefix
        fields = ("pk", "id", "prefix", "max_length", "roa_name")
        default_columns = ("prefix", "max_length", "roa_name")
