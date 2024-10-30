
import django_tables2 as tables
from netbox.tables import NetBoxTable, ChoiceFieldColumn
import netbox_rpki
from netbox_rpki.models import RpkiCertificate, RpkiOrganization, RpkiRoa, RpkiRoaPrefices


class RpkiCertificateTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.RpkiCertificate
        fields = ("pk", "id", "name", "issuer", "subject", "serial", "validFrom", "validTo", "publicKey", "privateKey", "publicationURL", "caRepository", "selfHosted", "rpkiOrg")
        default_columns = ("name", "issuer", "subject", "serial", "validFrom", "validTo", "publicKey", "privateKey", "publicationURL", "caRepository", "selfHosted", "rpkiOrg")

class RpkiOrganizationTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.RpkiOrganization
        fields = ("pk", "id", "orgId", "orgName")
        default_columns = ("orgName",)

class RpkiRoaTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.RpkiRoa
        fields = ("pk", "id", 'name', "originAs", "validFrom", "validTo", "signedBy")
        default_columns = ("name", "originAs", "validFrom", "validTo", "signedBy")


class RpkiRoaPreficesTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.RpkiRoaPrefices
        fields = ("pk", "id", "prefix", "maxLength", "roaName")
        default_columns = ("prefix", "maxLength", "roaName")

