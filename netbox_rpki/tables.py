
import django_tables2 as tables
from django.utils.safestring import mark_safe

from netbox.tables import NetBoxTable
from netbox.tables.columns import ActionsColumn, ChoiceFieldColumn, TagColumn
from netbox_rpki import models
from netbox_rpki.object_registry import TABLE_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec

AVAILABLE_LABEL = mark_safe('<span class="label label-success">Available</span>')
COL_TENANT = """
 {% if record.tenant %}
     <a href="{{ record.tenant.get_absolute_url }}" title="{{ record.tenant.description }}">{{ record.tenant }}</a>
 {% else %}
     &mdash;
 {% endif %}
 """


def build_table_class(spec: ObjectSpec) -> type[NetBoxTable]:
    row_actions = ['changelog']
    if spec.view is not None and spec.view.supports_create:
        row_actions.insert(0, 'edit')
    if spec.view is not None and spec.view.supports_delete:
        insert_at = 1 if 'edit' in row_actions else 0
        row_actions.insert(insert_at, 'delete')

    meta_class = type(
        'Meta',
        (NetBoxTable.Meta,),
        {
            'model': spec.model,
            'fields': spec.table.fields,
            'default_columns': spec.table.default_columns,
        },
    )

    return type(
        spec.table.class_name,
        (NetBoxTable,),
        {
            '__module__': __name__,
            spec.table.linkify_field: tables.Column(linkify=True),
            'tenant': tables.TemplateColumn(template_code=COL_TENANT),
            'tags': TagColumn(url_name=spec.list_url_name),
            'actions': ActionsColumn(actions=tuple(row_actions)),
            'Meta': meta_class,
        },
    )


for object_spec in TABLE_OBJECT_SPECS:
    globals()[object_spec.table.class_name] = build_table_class(object_spec)


_BaseRpkiProviderAccountTable = RpkiProviderAccountTable


class RpkiProviderAccountTable(_BaseRpkiProviderAccountTable):
    sync_health = tables.Column(accessor='sync_health_display', verbose_name='Sync Health')

    class Meta(_BaseRpkiProviderAccountTable.Meta):
        fields = _BaseRpkiProviderAccountTable.Meta.fields + ('sync_health',)
        default_columns = (
            'name',
            'organization',
            'provider_type',
            'org_handle',
            'ca_handle',
            'sync_health',
            'last_sync_status',
            'comments',
            'tenant',
            'tags',
        )


class ASPAProviderAuthorizationTable(NetBoxTable):
    provider_as = tables.Column(linkify=True, verbose_name='Provider ASN')
    tenant = tables.TemplateColumn(template_code=COL_TENANT)
    tags = TagColumn(url_name='plugins:netbox_rpki:aspa_list')
    actions = tables.Column(empty_values=(), orderable=False, verbose_name='')

    def render_actions(self):
        return ''

    class Meta(NetBoxTable.Meta):
        model = models.ASPAProvider
        fields = ('provider_as', 'is_current', 'comments', 'tenant', 'tags', 'actions')
        default_columns = ('provider_as', 'is_current', 'comments', 'tenant', 'tags')


class ImportedAspaProviderTable(NetBoxTable):
    provider_as = tables.Column(linkify=True, verbose_name='Provider ASN')
    tenant = tables.TemplateColumn(template_code=COL_TENANT)
    tags = TagColumn(url_name='plugins:netbox_rpki:importedaspa_list')
    actions = tables.Column(empty_values=(), orderable=False, verbose_name='')

    def render_actions(self):
        return ''

    class Meta(NetBoxTable.Meta):
        model = models.ImportedAspaProvider
        fields = ('provider_as', 'provider_as_value', 'address_family', 'raw_provider_text', 'comments', 'tenant', 'tags', 'actions')
        default_columns = ('provider_as', 'provider_as_value', 'address_family', 'raw_provider_text', 'tenant')
