
import django_tables2 as tables
from django.utils.safestring import mark_safe
# from django_tables2.utils import A

from netbox.tables import NetBoxTable
from netbox.tables.columns import ChoiceFieldColumn, TagColumn
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
            'Meta': meta_class,
        },
    )


for object_spec in TABLE_OBJECT_SPECS:
    globals()[object_spec.table.class_name] = build_table_class(object_spec)
