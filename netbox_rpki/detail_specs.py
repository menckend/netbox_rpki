from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.urls import reverse

from netbox_rpki import models


ValueGetter = Callable[[Any], Any]


def get_pk(instance: Any) -> Any:
    return instance.pk


@dataclass(frozen=True)
class DetailFieldSpec:
    label: str
    value: ValueGetter
    kind: str = 'text'
    url: ValueGetter | None = None
    use_header: bool = True
    empty_text: str | None = None


@dataclass(frozen=True)
class DetailActionSpec:
    permission: str
    label: str
    url_name: str | None = None
    query_param: str | None = None
    value: ValueGetter = get_pk
    direct_url: ValueGetter | None = None
    visible: ValueGetter | None = None


@dataclass(frozen=True)
class DetailTableSpec:
    title: str
    table_class_name: str
    queryset: ValueGetter


@dataclass(frozen=True)
class DetailSpec:
    model: type
    list_url_name: str
    breadcrumb_label: str
    card_title: str
    fields: tuple[DetailFieldSpec, ...]
    actions: tuple[DetailActionSpec, ...] = ()
    side_tables: tuple[DetailTableSpec, ...] = ()
    bottom_tables: tuple[DetailTableSpec, ...] = ()


ORGANIZATION_DETAIL_SPEC = DetailSpec(
    model=models.Organization,
    list_url_name='plugins:netbox_rpki:organization_list',
    breadcrumb_label='RPKI Customer Organizations',
    card_title='RPKI Organization',
    fields=(
        DetailFieldSpec(label='Organization ID', value=lambda obj: obj.org_id),
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(label='Organizaton Name', value=lambda obj: obj.name),
        DetailFieldSpec(
            label='Parent Regional Internet Registry',
            value=lambda obj: obj.parent_rir,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='External URL',
            value=lambda obj: obj.ext_url,
            kind='url',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_organization',
            label='RPKI Certificate',
            url_name='plugins:netbox_rpki:certificate_add',
            query_param='rpki_org',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Certificates',
            table_class_name='CertificateTable',
            queryset=lambda obj: obj.certificates.all(),
        ),
    ),
)


def get_related_count(attribute_name: str) -> ValueGetter:
    return lambda obj, attr=attribute_name: getattr(obj, attr).count()


def get_pretty_json(value: Any) -> str | None:
    if not value:
        return None
    return json.dumps(value, indent=2, sort_keys=True)


def get_profile_description(profile: models.RoutingIntentProfile) -> str | None:
    return profile.description or None


def get_profile_prefix_selector(profile: models.RoutingIntentProfile) -> str | None:
    return profile.prefix_selector_query or None


def get_profile_asn_selector(profile: models.RoutingIntentProfile) -> str | None:
    return profile.asn_selector_query or None


def get_run_result_summary(run: models.ROAReconciliationRun) -> str | None:
    return get_pretty_json(run.result_summary_json)


def get_result_details(result: models.ROAIntentResult) -> str | None:
    return get_pretty_json(result.details_json)


def get_result_expected_origin(result: models.ROAIntentResult) -> Any:
    return result.roa_intent.origin_asn or result.roa_intent.origin_asn_value


def get_result_published_origin(result: models.ROAIntentResult) -> Any:
    if result.best_roa_id is None:
        return None
    return result.best_roa.origin_as


def get_result_best_roa_prefixes(result: models.ROAIntentResult) -> str | None:
    if result.best_roa_id is None:
        return None
    prefixes = [str(prefix.prefix) for prefix in result.best_roa.RoaToPrefixTable.all()]
    return ', '.join(prefixes) or None


def get_result_best_roa_max_lengths(result: models.ROAIntentResult) -> str | None:
    if result.best_roa_id is None:
        return None
    max_lengths = [str(prefix.max_length) for prefix in result.best_roa.RoaToPrefixTable.all()]
    return ', '.join(max_lengths) or None


def get_plan_summary(plan: models.ROAChangePlan) -> str | None:
    return get_pretty_json(plan.summary_json)


def get_plan_provider_capability(plan: models.ROAChangePlan) -> str | None:
    if not plan.provider_account_id:
        return None
    return get_pretty_json(plan.provider_account.roa_write_capability)


def get_write_execution_request_payload(execution: models.ProviderWriteExecution) -> str | None:
    return get_pretty_json(execution.request_payload_json)


def get_write_execution_response_payload(execution: models.ProviderWriteExecution) -> str | None:
    return get_pretty_json(execution.response_payload_json)


def get_provider_last_sync_summary(account: models.RpkiProviderAccount) -> str | None:
    return get_pretty_json(account.last_sync_summary_json)


ROA_CHANGE_PLAN_DETAIL_SPEC = DetailSpec(
    model=models.ROAChangePlan,
    list_url_name='plugins:netbox_rpki:roachangeplan_list',
    breadcrumb_label='ROA Change Plans',
    card_title='ROA Change Plan',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Source Reconciliation Run', value=lambda obj: obj.source_reconciliation_run, kind='link'),
        DetailFieldSpec(
            label='Provider Account',
            value=lambda obj: obj.provider_account,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Provider Snapshot',
            value=lambda obj: obj.provider_snapshot,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Approved At', value=lambda obj: obj.approved_at, empty_text='None'),
        DetailFieldSpec(label='Approved By', value=lambda obj: obj.approved_by, empty_text='None'),
        DetailFieldSpec(label='Apply Started At', value=lambda obj: obj.apply_started_at, empty_text='None'),
        DetailFieldSpec(label='Apply Requested By', value=lambda obj: obj.apply_requested_by, empty_text='None'),
        DetailFieldSpec(label='Applied At', value=lambda obj: obj.applied_at, empty_text='None'),
        DetailFieldSpec(label='Failed At', value=lambda obj: obj.failed_at, empty_text='None'),
        DetailFieldSpec(
            label='Provider Write Capability',
            value=get_plan_provider_capability,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Plan Summary',
            value=get_plan_summary,
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplan',
            label='Preview',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplan_preview', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_preview,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplan',
            label='Approve',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplan_approve', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_approve,
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_roachangeplan',
            label='Apply',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:roachangeplan_apply', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.can_apply,
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='ROA Change Plan Items',
            table_class_name='ROAChangePlanItemTable',
            queryset=lambda obj: obj.items.all(),
        ),
        DetailTableSpec(
            title='Provider Write Executions',
            table_class_name='ProviderWriteExecutionTable',
            queryset=lambda obj: obj.provider_write_executions.all(),
        ),
    ),
)


PROVIDER_WRITE_EXECUTION_DETAIL_SPEC = DetailSpec(
    model=models.ProviderWriteExecution,
    list_url_name='plugins:netbox_rpki:providerwriteexecution_list',
    breadcrumb_label='Provider Write Executions',
    card_title='Provider Write Execution',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Provider Account', value=lambda obj: obj.provider_account, kind='link'),
        DetailFieldSpec(
            label='Provider Snapshot',
            value=lambda obj: obj.provider_snapshot,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Change Plan', value=lambda obj: obj.change_plan, kind='link'),
        DetailFieldSpec(label='Execution Mode', value=lambda obj: obj.execution_mode),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Requested By', value=lambda obj: obj.requested_by, empty_text='None'),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Item Count', value=lambda obj: obj.item_count),
        DetailFieldSpec(
            label='Follow-Up Sync Run',
            value=lambda obj: obj.followup_sync_run,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Follow-Up Provider Snapshot',
            value=lambda obj: obj.followup_provider_snapshot,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Error', value=lambda obj: obj.error, empty_text='None'),
        DetailFieldSpec(
            label='Request Payload',
            value=get_write_execution_request_payload,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Response Payload',
            value=get_write_execution_response_payload,
            kind='code',
            empty_text='None',
        ),
    ),
)


ROUTING_INTENT_PROFILE_DETAIL_SPEC = DetailSpec(
    model=models.RoutingIntentProfile,
    list_url_name='plugins:netbox_rpki:routingintentprofile_list',
    breadcrumb_label='Routing Intent Profiles',
    card_title='Routing Intent Profile Dashboard',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Default Profile', value=lambda obj: obj.is_default),
        DetailFieldSpec(label='Enabled', value=lambda obj: obj.enabled),
        DetailFieldSpec(label='Selector Mode', value=lambda obj: obj.selector_mode),
        DetailFieldSpec(label='Default Max Length Policy', value=lambda obj: obj.default_max_length_policy),
        DetailFieldSpec(label='Allow AS0', value=lambda obj: obj.allow_as0),
        DetailFieldSpec(label='Rules', value=get_related_count('rules')),
        DetailFieldSpec(label='Overrides', value=get_related_count('overrides')),
        DetailFieldSpec(label='Derived Intents', value=get_related_count('roa_intents')),
        DetailFieldSpec(label='Derivation Runs', value=get_related_count('derivation_runs')),
        DetailFieldSpec(label='Reconciliation Runs', value=get_related_count('reconciliation_runs')),
        DetailFieldSpec(
            label='Prefix Selector Query',
            value=get_profile_prefix_selector,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='ASN Selector Query',
            value=get_profile_asn_selector,
            kind='code',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Description',
            value=get_profile_description,
            kind='code',
            empty_text='None',
        ),
    ),
    side_tables=(
        DetailTableSpec(
            title='Routing Intent Rules',
            table_class_name='RoutingIntentRuleTable',
            queryset=lambda obj: obj.rules.all(),
        ),
        DetailTableSpec(
            title='ROA Intent Overrides',
            table_class_name='ROAIntentOverrideTable',
            queryset=lambda obj: obj.overrides.all(),
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Intent Derivation Runs',
            table_class_name='IntentDerivationRunTable',
            queryset=lambda obj: obj.derivation_runs.all(),
        ),
        DetailTableSpec(
            title='ROA Reconciliation Runs',
            table_class_name='ROAReconciliationRunTable',
            queryset=lambda obj: obj.reconciliation_runs.all(),
        ),
        DetailTableSpec(
            title='Derived ROA Intents',
            table_class_name='ROAIntentTable',
            queryset=lambda obj: obj.roa_intents.all(),
        ),
    ),
)


ROA_RECONCILIATION_RUN_DETAIL_SPEC = DetailSpec(
    model=models.ROAReconciliationRun,
    list_url_name='plugins:netbox_rpki:roareconciliationrun_list',
    breadcrumb_label='ROA Reconciliation Runs',
    card_title='ROA Reconciliation Run',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Intent Profile', value=lambda obj: obj.intent_profile, kind='link'),
        DetailFieldSpec(label='Basis Derivation Run', value=lambda obj: obj.basis_derivation_run, kind='link'),
        DetailFieldSpec(label='Comparison Scope', value=lambda obj: obj.comparison_scope),
        DetailFieldSpec(label='Status', value=lambda obj: obj.status),
        DetailFieldSpec(label='Started At', value=lambda obj: obj.started_at, empty_text='None'),
        DetailFieldSpec(label='Completed At', value=lambda obj: obj.completed_at, empty_text='None'),
        DetailFieldSpec(label='Published ROA Count', value=lambda obj: obj.published_roa_count),
        DetailFieldSpec(label='Intent Count', value=lambda obj: obj.intent_count),
        DetailFieldSpec(label='Intent Results', value=get_related_count('intent_results')),
        DetailFieldSpec(label='Published ROA Results', value=get_related_count('published_roa_results')),
        DetailFieldSpec(
            label='Result Summary',
            value=get_run_result_summary,
            kind='code',
            empty_text='None',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='ROA Intent Results',
            table_class_name='ROAIntentResultTable',
            queryset=lambda obj: obj.intent_results.all(),
        ),
        DetailTableSpec(
            title='Published ROA Results',
            table_class_name='PublishedROAResultTable',
            queryset=lambda obj: obj.published_roa_results.all(),
        ),
    ),
)


ROA_INTENT_RESULT_DETAIL_SPEC = DetailSpec(
    model=models.ROAIntentResult,
    list_url_name='plugins:netbox_rpki:roaintentresult_list',
    breadcrumb_label='ROA Intent Results',
    card_title='ROA Intent Result Diff',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Reconciliation Run', value=lambda obj: obj.reconciliation_run, kind='link'),
        DetailFieldSpec(label='ROA Intent', value=lambda obj: obj.roa_intent, kind='link'),
        DetailFieldSpec(label='Result Type', value=lambda obj: obj.result_type),
        DetailFieldSpec(label='Severity', value=lambda obj: obj.severity),
        DetailFieldSpec(label='Match Count', value=lambda obj: obj.match_count),
        DetailFieldSpec(
            label='Best Published ROA',
            value=lambda obj: obj.best_roa,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Computed At', value=lambda obj: obj.computed_at, empty_text='None'),
        DetailFieldSpec(label='Expected Prefix', value=lambda obj: obj.roa_intent.prefix_cidr_text, empty_text='None'),
        DetailFieldSpec(label='Expected Origin ASN', value=get_result_expected_origin, kind='link', empty_text='None'),
        DetailFieldSpec(label='Expected Max Length', value=lambda obj: obj.roa_intent.max_length, empty_text='None'),
        DetailFieldSpec(label='Published Prefixes', value=get_result_best_roa_prefixes, empty_text='None'),
        DetailFieldSpec(label='Published Origin ASN', value=get_result_published_origin, kind='link', empty_text='None'),
        DetailFieldSpec(label='Published Max Lengths', value=get_result_best_roa_max_lengths, empty_text='None'),
        DetailFieldSpec(
            label='Diff Details',
            value=get_result_details,
            kind='code',
            empty_text='None',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Candidate Matches',
            table_class_name='ROAIntentMatchTable',
            queryset=lambda obj: obj.roa_intent.candidate_matches.all(),
        ),
    ),
)


CERTIFICATE_DETAIL_SPEC = DetailSpec(
    model=models.Certificate,
    list_url_name='plugins:netbox_rpki:certificate_list',
    breadcrumb_label='RPKI Customer Certificates',
    card_title='RPKI Customer Certificate',
    fields=(
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Issuer', value=lambda obj: obj.issuer),
        DetailFieldSpec(label='Subject', value=lambda obj: obj.subject),
        DetailFieldSpec(label='Serial', value=lambda obj: obj.serial),
        DetailFieldSpec(label='Valid From', value=lambda obj: obj.valid_from),
        DetailFieldSpec(label='Valid To', value=lambda obj: obj.valid_to),
        DetailFieldSpec(label='Auto-renews?', value=lambda obj: obj.auto_renews),
        DetailFieldSpec(label='Public Key', value=lambda obj: obj.public_key),
        DetailFieldSpec(label='Private Key', value=lambda obj: obj.private_key),
        DetailFieldSpec(label='Publication URL', value=lambda obj: obj.publication_url),
        DetailFieldSpec(label='CA Repository', value=lambda obj: obj.ca_repository),
        DetailFieldSpec(label='Self Hosted', value=lambda obj: obj.self_hosted),
        DetailFieldSpec(
            label='Parent RPKI customer/org',
            value=lambda obj: obj.rpki_org,
            kind='link',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_certificate',
            label='Prefix',
            url_name='plugins:netbox_rpki:certificateprefix_add',
            query_param='certificate_name',
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_certificate',
            label='ASN',
            url_name='plugins:netbox_rpki:certificateasn_add',
            query_param='certificate_name2',
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_certificate',
            label='ROA',
            url_name='plugins:netbox_rpki:roa_add',
            query_param='signed_by',
        ),
    ),
    side_tables=(
        DetailTableSpec(
            title='Attested IP Netblock Resources',
            table_class_name='CertificatePrefixTable',
            queryset=lambda obj: obj.CertificateToPrefixTable.all(),
        ),
        DetailTableSpec(
            title='Attested ASN Resource',
            table_class_name='CertificateAsnTable',
            queryset=lambda obj: obj.CertificatetoASNTable.all(),
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='ROAs',
            table_class_name='RoaTable',
            queryset=lambda obj: obj.roas.all(),
        ),
    ),
)


ROA_DETAIL_SPEC = DetailSpec(
    model=models.Roa,
    list_url_name='plugins:netbox_rpki:roa_list',
    breadcrumb_label='RPKI ROAs',
    card_title='RPKI Route Origination Authorization (ROA)',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Origination AS Number',
            value=lambda obj: obj.origin_as,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Date Valid From', value=lambda obj: obj.valid_from),
        DetailFieldSpec(label='Date Valid To', value=lambda obj: obj.valid_to),
        DetailFieldSpec(label='Auto-renews', value=lambda obj: obj.auto_renews),
        DetailFieldSpec(
            label='Signing Certificate',
            value=lambda obj: obj.signed_by.name if obj.signed_by else None,
            kind='link',
            url=lambda obj: obj.signed_by.get_absolute_url() if obj.signed_by else None,
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_roa',
            label='ROA Prefix',
            url_name='plugins:netbox_rpki:roaprefix_add',
            query_param='roa_name',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Prefixes Included in this ROA',
            table_class_name='RoaPrefixTable',
            queryset=lambda obj: obj.RoaToPrefixTable.all(),
        ),
    ),
)


PROVIDER_ACCOUNT_DETAIL_SPEC = DetailSpec(
    model=models.RpkiProviderAccount,
    list_url_name='plugins:netbox_rpki:provideraccount_list',
    breadcrumb_label='Provider Accounts',
    card_title='Provider Account',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Organization', value=lambda obj: obj.organization, kind='link'),
        DetailFieldSpec(label='Provider Type', value=lambda obj: obj.provider_type),
        DetailFieldSpec(label='Transport', value=lambda obj: obj.transport),
        DetailFieldSpec(label='Organization Handle', value=lambda obj: obj.org_handle),
        DetailFieldSpec(label='CA Handle', value=lambda obj: obj.ca_handle, empty_text='None'),
        DetailFieldSpec(label='API Key', value=lambda obj: obj.api_key),
        DetailFieldSpec(label='API Base URL', value=lambda obj: obj.api_base_url, kind='url'),
        DetailFieldSpec(label='Sync Enabled', value=lambda obj: obj.sync_enabled),
        DetailFieldSpec(label='Last Successful Sync', value=lambda obj: obj.last_successful_sync, empty_text='None'),
        DetailFieldSpec(label='Last Sync Status', value=lambda obj: obj.last_sync_status),
        DetailFieldSpec(
            label='Last Sync Summary',
            value=get_provider_last_sync_summary,
            kind='code',
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_rpkiprovideraccount',
            label='Sync',
            direct_url=lambda obj: reverse('plugins:netbox_rpki:provideraccount_sync', kwargs={'pk': obj.pk}),
            visible=lambda obj: obj.sync_enabled,
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Provider Snapshots',
            table_class_name='ProviderSnapshotTable',
            queryset=lambda obj: obj.snapshots.all(),
        ),
        DetailTableSpec(
            title='Provider Sync Runs',
            table_class_name='ProviderSyncRunTable',
            queryset=lambda obj: obj.sync_runs.all(),
        ),
    ),
)


DETAIL_SPEC_BY_MODEL = {
    models.Organization: ORGANIZATION_DETAIL_SPEC,
    models.Certificate: CERTIFICATE_DETAIL_SPEC,
    models.Roa: ROA_DETAIL_SPEC,
    models.RpkiProviderAccount: PROVIDER_ACCOUNT_DETAIL_SPEC,
    models.RoutingIntentProfile: ROUTING_INTENT_PROFILE_DETAIL_SPEC,
    models.ROAReconciliationRun: ROA_RECONCILIATION_RUN_DETAIL_SPEC,
    models.ROAChangePlan: ROA_CHANGE_PLAN_DETAIL_SPEC,
    models.ROAIntentResult: ROA_INTENT_RESULT_DETAIL_SPEC,
    models.ProviderWriteExecution: PROVIDER_WRITE_EXECUTION_DETAIL_SPEC,
}
