
import django_tables2 as tables
from netbox.tables import NetBoxTable, ChoiceFieldColumn
import netbox_rpki
from netbox_rpki.models import certificate, organization, roa, roaprefices


class certificateTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.certificate
        fields = ("pk", "id", "name", "issuer", "subject", "serial", "validFrom", "validTo", "publicKey", "privateKey", "publicationURL", "caRepository", "selfHosted", "rpkiOrg")
        default_columns = ("name", "issuer", "subject", "serial", "validFrom", "validTo", "publicKey", "privateKey", "publicationURL", "caRepository", "selfHosted", "rpkiOrg")

class organizationTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.organization
        fields = ("pk", "id", "orgId", "orgName")
        default_columns = ("orgName",)

class roaTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.roa
        fields = ("pk", "id", 'name', "originAs", "validFrom", "validTo", "signedBy")
        default_columns = ("name", "originAs", "validFrom", "validTo", "signedBy")


class roapreficesTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.roaprefices
        fields = ("pk", "id", "prefix", "maxLength", "roaName")
        default_columns = ("prefix", "maxLength", "roaName")
