
import django_tables2 as tables
from django.utils.safestring import mark_safe
# from django_tables2.utils import A

from netbox.tables import NetBoxTable
from netbox.tables.columns import ChoiceFieldColumn, TagColumn
import netbox_rpki

AVAILABLE_LABEL = mark_safe('<span class="label label-success">Available</span>')
COL_TENANT = """
 {% if record.tenant %}
     <a href="{{ record.tenant.get_absolute_url }}" title="{{ record.tenant.description }}">{{ record.tenant }}</a>
 {% else %}
     &mdash;
 {% endif %}
 """


class CertificateTable(NetBoxTable):
    name = tables.Column(linkify=True)
    tenant = tables.TemplateColumn(
        template_code=COL_TENANT
    )
    tags = TagColumn(
        url_name='plugins:netbox_rpki:certificate_list'
    )

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.Certificate
        fields = ("pk", "id", "name", "issuer", "subject", "serial", "valid_from", "valid_to", "auto_renews", "publicKey", "private_key", "publication_url", "ca_repository", "self_hosted", "rpki_org", "comments", "tenant", "tags")
        default_columns = ("name", "valid_from", "valid_to", "auto_renews",  "self_hosted", "rpki_org", "comments", "tenant", "tags")


class OrganizationTable(NetBoxTable):
    name = tables.Column(linkify=True)
    tenant = tables.TemplateColumn(
        template_code=COL_TENANT
    )
    tags = TagColumn(
        url_name='plugins:netbox_rpki:organization_list'
    )

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.Organization
        fields = ("pk", "id", "org_id", "name", "parent_rir", "ext_url", "comments", "tenant", "tags")
        default_columns = ("org_id", "name", "parent_rir", "ext_url", "comments", "tenant", "tags")


class RoaTable(NetBoxTable):
    name = tables.Column(linkify=True)
    tenant = tables.TemplateColumn(
        template_code=COL_TENANT
    )
    tags = TagColumn(
        url_name='plugins:netbox_rpki:roa_list'
    )

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.Roa
        fields = ("pk", "id", 'name', "origin_as", "valid_from", "valid_to", "auto_renews", "signed_by", "comments", "tenant", "tags")
        default_columns = ("name", "origin_as", "valid_from", "valid_to", "auto_renews", "comments", "tenant", "tags")


class RoaPrefixTable(NetBoxTable):
    pk = tables.Column(linkify=True)
    tenant = tables.TemplateColumn(
        template_code=COL_TENANT
    )
    tags = TagColumn(
        url_name='plugins:netbox_rpki:roaprefix_list'
    )

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.RoaPrefix
        fields = ("pk", "id", "prefix", "max_length", "roa_name", "comments", "tenant", "tags")
        default_columns = ("prefix", "max_length", "roa_name", "comments", "tenant", "tags")


class CertificatePrefixTable(NetBoxTable):
    pk = tables.Column(linkify=True)
    tenant = tables.TemplateColumn(
        template_code=COL_TENANT
    )
    tags = TagColumn(
        url_name='plugins:netbox_rpki:certificateprefix_list'
    )

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.CertificatePrefix
        fields = ("pk", "id", "prefix", "certificate_name", "comments", "tenant", "tags")
        default_columns = ("prefix", "comments", "tenant", "tags")


class CertificateAsnTable(NetBoxTable):
    pk = tables.Column(linkify=True)
    tenant = tables.TemplateColumn(
        template_code=COL_TENANT
    )
    tags = TagColumn(
        url_name='plugins:netbox_rpki:certificateasn_list'
    )

    class Meta(NetBoxTable.Meta):
        model = netbox_rpki.models.CertificateAsn
        fields = ("pk", "id", "asn", "certificate_name2", "comments", "tenant", "tags")
        default_columns = ("asn", "comments", "tenant", "tags")
