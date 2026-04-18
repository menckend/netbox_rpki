
import django_tables2 as tables
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from netbox.tables import NetBoxTable
from netbox.tables.columns import ActionsColumn, TagColumn
from netbox_rpki import models
from netbox_rpki.object_registry import TABLE_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec
from netbox_rpki.services.publication_state import (
    derive_change_plan_publication_state,
    derive_rollback_bundle_publication_state,
)

AVAILABLE_LABEL = mark_safe('<span class="label label-success">Available</span>')
COL_TENANT = """
 {% if record.tenant %}
     <a href="{{ record.tenant.get_absolute_url }}" title="{{ record.tenant.description }}">{{ record.tenant }}</a>
 {% else %}
     &mdash;
 {% endif %}
 """


def _join_display_values(values):
    rendered = [str(value) for value in values if value]
    return ', '.join(rendered) if rendered else 'None'


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


_BaseIrrSourceTable = IrrSourceTable


class IrrSourceTable(_BaseIrrSourceTable):
    sync_health = tables.Column(accessor='sync_health_display', verbose_name='Sync Health')

    class Meta(_BaseIrrSourceTable.Meta):
        fields = _BaseIrrSourceTable.Meta.fields + ('sync_health',)
        default_columns = (
            'name',
            'organization',
            'slug',
            'source_family',
            'write_support_mode',
            'enabled',
            'sync_health',
            'last_sync_status',
            'comments',
            'tenant',
            'tags',
        )


_BaseTelemetrySourceTable = TelemetrySourceTable


class TelemetrySourceTable(_BaseTelemetrySourceTable):
    sync_health = tables.Column(accessor='sync_health_display', verbose_name='Sync Health')

    class Meta(_BaseTelemetrySourceTable.Meta):
        fields = _BaseTelemetrySourceTable.Meta.fields + ('sync_health',)
        default_columns = (
            'name',
            'organization',
            'slug',
            'source_type',
            'enabled',
            'sync_health',
            'last_run_status',
            'comments',
            'tenant',
            'tags',
        )


_BaseRoutingIntentProfileTable = RoutingIntentProfileTable


class RoutingIntentProfileTable(_BaseRoutingIntentProfileTable):
    context_group_names = tables.Column(empty_values=(), verbose_name='Context Groups', orderable=False)

    def render_context_group_names(self, record):
        return _join_display_values(record.context_groups.order_by('priority', 'name').all())

    class Meta(_BaseRoutingIntentProfileTable.Meta):
        fields = _BaseRoutingIntentProfileTable.Meta.fields + ('context_group_names',)
        default_columns = (
            'name',
            'organization',
            'status',
            'context_group_names',
            'enabled',
            'comments',
            'tenant',
            'tags',
        )


_BaseRoutingIntentContextGroupTable = RoutingIntentContextGroupTable


class RoutingIntentContextGroupTable(_BaseRoutingIntentContextGroupTable):
    criteria_count = tables.Column(empty_values=(), verbose_name='Criteria', orderable=False)
    profile_count = tables.Column(empty_values=(), verbose_name='Profiles', orderable=False)
    binding_count = tables.Column(empty_values=(), verbose_name='Bindings', orderable=False)

    def value_criteria_count(self, record):
        return record.criteria.count()

    def value_profile_count(self, record):
        return record.intent_profiles.count()

    def value_binding_count(self, record):
        return record.template_bindings.count()

    class Meta(_BaseRoutingIntentContextGroupTable.Meta):
        fields = _BaseRoutingIntentContextGroupTable.Meta.fields + (
            'criteria_count',
            'profile_count',
            'binding_count',
        )
        default_columns = (
            'name',
            'organization',
            'context_type',
            'priority',
            'criteria_count',
            'profile_count',
            'binding_count',
            'enabled',
            'comments',
            'tenant',
            'tags',
        )


_BaseRoutingIntentContextCriterionTable = RoutingIntentContextCriterionTable


class RoutingIntentContextCriterionTable(_BaseRoutingIntentContextCriterionTable):
    match_target = tables.Column(empty_values=(), verbose_name='Match Target', orderable=False)

    def render_match_target(self, record):
        return _join_display_values(
            (
                record.match_tenant,
                record.match_vrf,
                record.match_site,
                record.match_region,
                record.match_provider_account,
                record.match_circuit,
                record.match_provider,
                record.match_value,
            )
        )

    class Meta(_BaseRoutingIntentContextCriterionTable.Meta):
        fields = _BaseRoutingIntentContextCriterionTable.Meta.fields + ('match_target',)
        default_columns = (
            'name',
            'context_group',
            'criterion_type',
            'match_target',
            'weight',
            'enabled',
            'comments',
            'tenant',
            'tags',
        )


_BaseRoutingIntentTemplateBindingTable = RoutingIntentTemplateBindingTable


class RoutingIntentTemplateBindingTable(_BaseRoutingIntentTemplateBindingTable):
    context_group_names = tables.Column(empty_values=(), verbose_name='Context Groups', orderable=False)

    def render_context_group_names(self, record):
        return _join_display_values(record.context_groups.order_by('priority', 'name').all())

    class Meta(_BaseRoutingIntentTemplateBindingTable.Meta):
        pass


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


class RoaAuthorityMapTable(NetBoxTable):
    subject = tables.Column(
        accessor='subject_label',
        verbose_name='Subject',
        linkify=lambda record: record.roa_intent.get_absolute_url(),
        order_by=('prefix_cidr_text', 'origin_asn_value', 'max_length'),
    )
    organization = tables.Column(accessor='organization', linkify=True)
    intent_profile = tables.Column(accessor='intent_profile', linkify=True, verbose_name='Profile')
    address_family = tables.Column(accessor='address_family', verbose_name='AF')
    derived_state = tables.Column(verbose_name='Authority')
    exposure_state = tables.Column(verbose_name='Exposure')
    run_state = tables.Column(verbose_name='Run State')
    drift_state = tables.Column(verbose_name='Drift')
    severity = tables.Column(verbose_name='Severity')
    authority_reason_summary = tables.Column(verbose_name='Why Authoritative')
    reconciliation_summary = tables.Column(verbose_name='Reconciliation')
    publication_summary = tables.Column(verbose_name='Execution')
    binding_freshness = tables.Column(verbose_name='Binding')
    overlap_warning = tables.Column(verbose_name='Overlap')

    class Meta(NetBoxTable.Meta):
        model = models.ROAIntent
        fields = (
            'subject',
            'organization',
            'intent_profile',
            'address_family',
            'derived_state',
            'exposure_state',
            'run_state',
            'drift_state',
            'severity',
            'authority_reason_summary',
            'reconciliation_summary',
            'publication_summary',
            'binding_freshness',
            'overlap_warning',
        )
        default_columns = (
            'subject',
            'organization',
            'intent_profile',
            'derived_state',
            'run_state',
            'drift_state',
            'severity',
            'authority_reason_summary',
            'publication_summary',
        )

    def render_derived_state(self, value):
        return self._render_badge(value, {
            models.ROAIntentDerivedState.ACTIVE: 'success',
            models.ROAIntentDerivedState.SUPPRESSED: 'warning text-dark',
            models.ROAIntentDerivedState.SHADOWED: 'secondary',
        })

    def render_exposure_state(self, value):
        return self._render_badge(value, {
            models.ROAIntentExposureState.ADVERTISED: 'primary',
            models.ROAIntentExposureState.ELIGIBLE_NOT_ADVERTISED: 'secondary',
            models.ROAIntentExposureState.BLOCKED: 'danger',
        })

    def render_run_state(self, value):
        return self._render_badge(value, {
            'unreconciled': 'secondary',
            'reconciled_current': 'success',
            'reconciled_with_drift': 'warning text-dark',
            'reconciliation_failed': 'danger',
        })

    def render_drift_state(self, value):
        return self._render_badge(value, {
            'match': 'success',
            'missing': 'danger',
            'origin_mismatch': 'danger',
            'origin_and_length_mismatch': 'danger',
            'prefix_mismatch': 'warning text-dark',
            'max_length_overbroad': 'warning text-dark',
            'max_length_too_narrow': 'warning text-dark',
            'stale': 'warning text-dark',
            'inactive_intent': 'secondary',
            'suppressed_by_policy': 'secondary',
            'unknown': 'secondary',
        })

    def render_severity(self, value):
        return self._render_badge(value.upper() if value else '', {
            'INFO': 'info',
            'WARNING': 'warning text-dark',
            'ERROR': 'danger',
            'CRITICAL': 'danger',
        })

    def render_binding_freshness(self, value):
        return self._render_badge(value or 'None', {
            models.RoutingIntentTemplateBindingState.CURRENT: 'success',
            models.RoutingIntentTemplateBindingState.STALE: 'warning text-dark',
            models.RoutingIntentTemplateBindingState.PENDING: 'info',
            models.RoutingIntentTemplateBindingState.INVALID: 'danger',
            'None': 'secondary',
        })

    def render_overlap_warning(self, value):
        if not value:
            return ''
        return self._render_badge(value, {'default': 'warning text-dark'})

    def render_authority_reason_summary(self, value):
        if not value:
            return ''
        return format_html('<span title="{}">{}</span>', value, value)

    def _render_badge(self, value, class_map):
        css_class = class_map.get(value, class_map.get('default', 'secondary'))
        if not value:
            value = ''
        return format_html('<span class="badge text-bg-{}">{}</span>', css_class, value)


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


_BaseProviderSnapshotDiffTable = ProviderSnapshotDiffTable


class ProviderSnapshotDiffTable(_BaseProviderSnapshotDiffTable):
    records_added = tables.Column(empty_values=(), verbose_name='Added', orderable=False)
    records_removed = tables.Column(empty_values=(), verbose_name='Removed', orderable=False)
    records_changed = tables.Column(empty_values=(), verbose_name='Changed', orderable=False)

    def value_records_added(self, record):
        return ((record.summary_json or {}).get('totals') or {}).get('records_added', 0)

    def value_records_removed(self, record):
        return ((record.summary_json or {}).get('totals') or {}).get('records_removed', 0)

    def value_records_changed(self, record):
        return ((record.summary_json or {}).get('totals') or {}).get('records_changed', 0)

    class Meta(_BaseProviderSnapshotDiffTable.Meta):
        fields = _BaseProviderSnapshotDiffTable.Meta.fields + ('records_added', 'records_removed', 'records_changed')
        default_columns = _BaseProviderSnapshotDiffTable.Meta.default_columns + (
            'records_added',
            'records_removed',
            'records_changed',
        )


_BaseROAChangePlanTable = ROAChangePlanTable


class ROAChangePlanTable(_BaseROAChangePlanTable):
    publication_state = tables.Column(empty_values=(), verbose_name='Publication State', orderable=False)

    def value_publication_state(self, record):
        return derive_change_plan_publication_state(record).publication_state

    def render_publication_state(self, record):
        state = derive_change_plan_publication_state(record).publication_state
        label = dict(models.PublicationState.choices).get(state, state)
        return label

    class Meta(_BaseROAChangePlanTable.Meta):
        fields = _BaseROAChangePlanTable.Meta.fields + ('publication_state',)
        default_columns = _BaseROAChangePlanTable.Meta.default_columns + ('publication_state',)


_BaseASPAChangePlanTable = ASPAChangePlanTable


class ASPAChangePlanTable(_BaseASPAChangePlanTable):
    publication_state = tables.Column(empty_values=(), verbose_name='Publication State', orderable=False)

    def value_publication_state(self, record):
        return derive_change_plan_publication_state(record).publication_state

    def render_publication_state(self, record):
        state = derive_change_plan_publication_state(record).publication_state
        label = dict(models.PublicationState.choices).get(state, state)
        return label

    class Meta(_BaseASPAChangePlanTable.Meta):
        fields = _BaseASPAChangePlanTable.Meta.fields + ('publication_state',)
        default_columns = _BaseASPAChangePlanTable.Meta.default_columns + ('publication_state',)


_BaseROAChangePlanRollbackBundleTable = ROAChangePlanRollbackBundleTable


class ROAChangePlanRollbackBundleTable(_BaseROAChangePlanRollbackBundleTable):
    publication_state = tables.Column(empty_values=(), verbose_name='Publication State', orderable=False)

    def value_publication_state(self, record):
        return derive_rollback_bundle_publication_state(record).publication_state

    def render_publication_state(self, record):
        state = derive_rollback_bundle_publication_state(record).publication_state
        label = dict(models.PublicationState.choices).get(state, state)
        return label

    class Meta(_BaseROAChangePlanRollbackBundleTable.Meta):
        fields = _BaseROAChangePlanRollbackBundleTable.Meta.fields + ('publication_state',)
        default_columns = _BaseROAChangePlanRollbackBundleTable.Meta.default_columns + ('publication_state',)


_BaseASPAChangePlanRollbackBundleTable = ASPAChangePlanRollbackBundleTable


class ASPAChangePlanRollbackBundleTable(_BaseASPAChangePlanRollbackBundleTable):
    publication_state = tables.Column(empty_values=(), verbose_name='Publication State', orderable=False)

    def value_publication_state(self, record):
        return derive_rollback_bundle_publication_state(record).publication_state

    def render_publication_state(self, record):
        state = derive_rollback_bundle_publication_state(record).publication_state
        label = dict(models.PublicationState.choices).get(state, state)
        return label

    class Meta(_BaseASPAChangePlanRollbackBundleTable.Meta):
        fields = _BaseASPAChangePlanRollbackBundleTable.Meta.fields + ('publication_state',)
        default_columns = _BaseASPAChangePlanRollbackBundleTable.Meta.default_columns + ('publication_state',)
