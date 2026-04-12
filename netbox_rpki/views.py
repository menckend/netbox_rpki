from types import SimpleNamespace
from urllib.parse import urlencode

from django.urls import reverse
from netbox.object_actions import AddObject, BulkExport, CloneObject, DeleteObject, EditObject
from netbox.views import generic

from netbox_rpki import models, forms, tables, filtersets
from netbox_rpki.detail_specs import (
    CERTIFICATE_DETAIL_SPEC,
    DETAIL_SPEC_BY_MODEL,
    DetailFieldSpec,
    ORGANIZATION_DETAIL_SPEC,
    ROA_DETAIL_SPEC,
)
from netbox_rpki.object_registry import SIMPLE_DETAIL_VIEW_OBJECT_SPECS, VIEW_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec


class MetadataDrivenDetailView(generic.ObjectView):
    template_name = 'netbox_rpki/object_detail.html'
    detail_spec = None

    def get_detail_spec(self):
        if self.detail_spec is None:
            raise AttributeError(f'{self.__class__.__name__} must define detail_spec')
        return self.detail_spec

    def build_detail_field(self, field_spec, instance):
        value = field_spec.value(instance)
        url = self.resolve_detail_field_url(field_spec, instance, value)

        return {
            'kind': field_spec.kind,
            'label': field_spec.label,
            'value': value,
            'url': url,
            'use_header': field_spec.use_header,
            'empty_text': field_spec.empty_text,
            'is_empty': value in (None, ''),
        }

    def resolve_detail_field_url(self, field_spec, instance, value):
        if field_spec.kind == 'url':
            return field_spec.url(instance) if field_spec.url else value

        if field_spec.url is not None:
            return field_spec.url(instance)

        get_absolute_url = getattr(value, 'get_absolute_url', None)
        if callable(get_absolute_url):
            return get_absolute_url()

        return None

    def build_detail_action_button(self, action_spec, instance):
        query_string = urlencode({action_spec.query_param: action_spec.value(instance)})
        return {
            'label': action_spec.label,
            'url': f'{reverse(action_spec.url_name)}?{query_string}',
        }

    def build_detail_table_section(self, request, table_spec, instance):
        table_class = getattr(tables, table_spec.table_class_name)
        table = table_class(table_spec.queryset(instance))
        table.configure(request)

        return {
            'title': table_spec.title,
            'table': table,
        }

    def build_detail_table_sections(self, request, table_specs, instance):
        sections = []

        for table_spec in table_specs:
            section = self.build_detail_table_section(request, table_spec, instance)
            sections.append(section)

        return sections

    def get_extra_context(self, request, instance):
        detail_spec = self.get_detail_spec()
        side_sections = self.build_detail_table_sections(request, detail_spec.side_tables, instance)
        bottom_sections = self.build_detail_table_sections(request, detail_spec.bottom_tables, instance)

        return {
            'detail_spec': detail_spec,
            'detail_fields': [self.build_detail_field(field_spec, instance) for field_spec in detail_spec.fields],
            'detail_action_buttons': [
                self.build_detail_action_button(action_spec, instance)
                for action_spec in detail_spec.actions
                if request.user.has_perm(action_spec.permission)
            ],
            'detail_side_sections': side_sections,
            'detail_bottom_sections': bottom_sections,
        }


class CertificateView(MetadataDrivenDetailView):
    queryset = models.Certificate.objects.all()
    detail_spec = CERTIFICATE_DETAIL_SPEC


class OrganizationView(MetadataDrivenDetailView):
    queryset = models.Organization.objects.all()
    detail_spec = ORGANIZATION_DETAIL_SPEC


class RoaView(MetadataDrivenDetailView):
    queryset = models.Roa.objects.all()
    detail_spec = ROA_DETAIL_SPEC


def build_generated_detail_field_spec(spec: ObjectSpec, field_name: str) -> DetailFieldSpec:
    model_field = spec.model._meta.get_field(field_name)
    kind = 'text'
    empty_text = None
    if getattr(model_field, 'is_relation', False):
        kind = 'link'
        empty_text = 'None'
    elif field_name.endswith(('_url', '_uri')):
        kind = 'url'

    return DetailFieldSpec(
        label=str(model_field.verbose_name).title(),
        value=lambda obj, attr=field_name: getattr(obj, attr),
        kind=kind,
        empty_text=empty_text,
    )


def build_generated_detail_spec(spec: ObjectSpec):
    custom_spec = DETAIL_SPEC_BY_MODEL.get(spec.model)
    if custom_spec is not None:
        return custom_spec

    detail_fields = tuple(
        build_generated_detail_field_spec(spec, field_name)
        for field_name in spec.api.fields
        if field_name not in {'id', 'url'}
    )
    return SimpleNamespace(
        list_url_name=spec.list_url_name,
        breadcrumb_label=spec.labels.plural,
        card_title=spec.labels.singular,
        fields=detail_fields,
        actions=(),
        side_tables=(),
        bottom_tables=(),
    )


def build_list_actions(spec: ObjectSpec):
    actions = [BulkExport]
    if spec.view.supports_create:
        actions.insert(0, AddObject)
    return tuple(actions)


def build_detail_actions(spec: ObjectSpec):
    actions = []
    if spec.view.supports_create:
        actions.extend((CloneObject, EditObject))
    if spec.view.supports_delete:
        actions.append(DeleteObject)
    return tuple(actions)


def build_list_view_class(spec: ObjectSpec) -> type[generic.ObjectListView]:
    return type(
        spec.view.list_class_name,
        (generic.ObjectListView,),
        {
            '__module__': __name__,
            'queryset': spec.model.objects.all(),
            'filterset': getattr(filtersets, spec.filterset.class_name),
            'filterset_form': getattr(forms, spec.filter_form.class_name),
            'table': getattr(tables, spec.table.class_name),
            'actions': build_list_actions(spec),
        },
    )


def build_detail_view_class(spec: ObjectSpec) -> type[MetadataDrivenDetailView]:
    return type(
        spec.view.detail_class_name,
        (MetadataDrivenDetailView,),
        {
            '__module__': __name__,
            'queryset': spec.model.objects.all(),
            'detail_spec': build_generated_detail_spec(spec),
            'actions': build_detail_actions(spec),
        },
    )


def build_edit_view_class(spec: ObjectSpec) -> type[generic.ObjectEditView]:
    if spec.view.edit_class_name is None or spec.form is None:
        raise AttributeError(f'{spec.registry_key} does not define an editable view')
    return type(
        spec.view.edit_class_name,
        (generic.ObjectEditView,),
        {
            '__module__': __name__,
            'queryset': spec.model.objects.all(),
            'form': getattr(forms, spec.form.class_name),
        },
    )


def build_delete_view_class(spec: ObjectSpec) -> type[generic.ObjectDeleteView]:
    if spec.view.delete_class_name is None:
        raise AttributeError(f'{spec.registry_key} does not define a delete view')
    return type(
        spec.view.delete_class_name,
        (generic.ObjectDeleteView,),
        {
            '__module__': __name__,
            'queryset': spec.model.objects.all(),
        },
    )


for object_spec in VIEW_OBJECT_SPECS:
    globals()[object_spec.view.list_class_name] = build_list_view_class(object_spec)
    if object_spec.view.edit_class_name is not None and object_spec.form is not None:
        globals()[object_spec.view.edit_class_name] = build_edit_view_class(object_spec)
    if object_spec.view.delete_class_name is not None:
        globals()[object_spec.view.delete_class_name] = build_delete_view_class(object_spec)


for object_spec in SIMPLE_DETAIL_VIEW_OBJECT_SPECS:
    globals()[object_spec.view.detail_class_name] = build_detail_view_class(object_spec)
