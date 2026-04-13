from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from dataclasses import dataclass
from itertools import count
from typing import Any

from django.urls import reverse
from django.urls.resolvers import URLResolver

from netbox_rpki import models as rpki_models
from netbox_rpki import forms
from netbox_rpki.object_registry import (
    API_OBJECT_SPECS,
    FILTERSET_OBJECT_SPECS,
    FILTER_FORM_OBJECT_SPECS,
    FORM_OBJECT_SPECS,
    GRAPHQL_OBJECT_SPECS,
    TABLE_OBJECT_SPECS,
    VIEW_OBJECT_SPECS,
    get_navigation_groups,
    get_object_spec,
)
from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_aspa,
    create_test_aspa_provider,
    create_test_aspa_intent,
    create_test_aspa_intent_match,
    create_test_aspa_intent_result,
    create_test_aspa_reconciliation_run,
    create_test_certificate,
    create_test_certificate_revocation_list,
    create_test_certificate_asn,
    create_test_certificate_prefix,
    create_test_end_entity_certificate,
    create_test_external_object_reference,
    create_test_organization,
    create_test_manifest,
    create_test_manifest_entry,
    create_test_model,
    create_test_prefix,
    create_test_provider_account,
    create_test_provider_snapshot_diff,
    create_test_provider_snapshot_diff_item,
    create_test_approval_record,
    create_test_imported_aspa,
    create_test_imported_aspa_provider,
    create_test_provider_write_execution,
    create_test_roa_lint_run,
    create_test_roa_lint_finding,
    create_test_publication_point,
    create_test_published_aspa_result,
    create_test_provider_sync_run,
    create_test_provider_snapshot,
    create_test_imported_ca_metadata,
    create_test_imported_certificate_observation,
    create_test_imported_parent_link,
    create_test_imported_child_link,
    create_test_imported_resource_entitlement,
    create_test_imported_publication_point,
    create_test_imported_signed_object,
    create_test_repository,
    create_test_rir,
    create_test_revoked_certificate,
    create_test_roa_change_plan,
    create_test_roa_change_plan_item,
    create_test_roa_change_plan_matrix,
    create_test_imported_roa_authorization,
    create_test_roa,
    create_test_roa_intent,
    create_test_roa_intent_match,
    create_test_roa_intent_override,
    create_test_roa_intent_result,
    create_test_roa_reconciliation_run,
    create_test_roa_prefix,
    create_test_roa_validation_simulation_result,
    create_test_roa_validation_simulation_run,
    create_test_router_certificate,
    create_test_rsc,
    create_test_rsc_file_hash,
    create_test_routing_intent_profile,
    create_test_routing_intent_rule,
    create_test_signed_object,
    create_test_trust_anchor,
    create_test_trust_anchor_key,
    create_test_trust_anchor_locator,
    create_test_intent_derivation_run,
    create_test_published_roa_result,
    create_test_validation_run,
    create_test_validator_instance,
    create_test_object_validation_result,
    create_test_validated_roa_payload,
    create_test_validated_aspa_payload,
)
from netbox_rpki.urls import urlpatterns

EXPECTED_FORM_CLASS_NAMES = tuple(spec.form.class_name for spec in FORM_OBJECT_SPECS)

EXPECTED_FILTER_FORM_CLASS_NAMES = tuple(spec.filter_form.class_name for spec in FILTER_FORM_OBJECT_SPECS)

EXPECTED_FILTERSET_CLASS_NAMES = tuple(spec.filterset.class_name for spec in FILTERSET_OBJECT_SPECS)

EXPECTED_TABLE_CLASS_NAMES = tuple(spec.table.class_name for spec in TABLE_OBJECT_SPECS)


def _build_expected_route_paths() -> dict[str, dict[str, str]]:
    expected_paths: dict[str, dict[str, str]] = {}
    include_routes = [pattern.pattern._route for pattern in urlpatterns if isinstance(pattern, URLResolver)]
    for spec, include_route in zip(VIEW_OBJECT_SPECS, include_routes):
        paths = {
            "list": reverse(spec.routes.list_url_name),
            "detail": reverse(f"plugins:netbox_rpki:{spec.routes.slug}", kwargs={"pk": 1}),
            "include": include_route,
        }
        if spec.view.supports_create:
            paths["add"] = reverse(spec.routes.add_url_name)
            paths["edit"] = reverse(f"plugins:netbox_rpki:{spec.routes.slug}_edit", kwargs={"pk": 1})
        if spec.view.supports_delete:
            paths["delete"] = reverse(f"plugins:netbox_rpki:{spec.routes.slug}_delete", kwargs={"pk": 1})
        expected_paths[spec.registry_key] = paths
    return expected_paths


EXPECTED_ROUTE_PATHS = _build_expected_route_paths()

EXPECTED_MODEL_CHILD_INCLUDE_ROUTES = tuple(
    pattern.pattern._route for pattern in urlpatterns if isinstance(pattern, URLResolver)
)

EXPECTED_NAVIGATION_GROUPS = tuple((group_name, tuple(spec.registry_key for spec in specs)) for group_name, specs in get_navigation_groups())

EXPECTED_NAVIGATION_LINKS = {
    group_name: tuple((spec.navigation.label, spec.list_url_name) for spec in specs)
    for group_name, specs in get_navigation_groups()
}

EXPECTED_GRAPHQL_FIELD_NAMES_BY_KEY = {
    spec.registry_key: (spec.graphql.detail_field_name, spec.graphql.list_field_name)
    for spec in GRAPHQL_OBJECT_SPECS
}

EXPECTED_GRAPHQL_FIELD_ORDER = tuple(
    field_name for field_names in EXPECTED_GRAPHQL_FIELD_NAMES_BY_KEY.values() for field_name in field_names
)

_TEXT_COUNTER = count(1)
_ASN_COUNTER = count(65100)
_PREFIX_COUNTER = count(1)


def get_spec_values(specs, *attrs: str) -> tuple[object, ...]:
    values = []
    for spec in specs:
        value = spec
        for attr in attrs:
            value = getattr(value, attr)
        values.append(value)
    return tuple(values)


def _next_text_index() -> int:
    return next(_TEXT_COUNTER)


def unique_token(prefix: str) -> str:
    return f"{prefix}-{_next_text_index()}"


def create_unique_rir(prefix: str = "rir", **kwargs):
    token = unique_token(prefix)
    return create_test_rir(name=f"{prefix.title()} {token}", slug=token, **kwargs)


def create_unique_organization(prefix: str = "organization", **kwargs):
    token = unique_token(prefix)
    return create_test_organization(org_id=token, name=f"{prefix.title()} {token}", **kwargs)


def create_unique_certificate(prefix: str = "certificate", rpki_org=None, **kwargs):
    token = unique_token(prefix)
    if rpki_org is None:
        rpki_org = create_unique_organization("certificate-org")
    return create_test_certificate(name=f"{prefix.title()} {token}", rpki_org=rpki_org, **kwargs)


def create_unique_asn(**kwargs):
    return create_test_asn(next(_ASN_COUNTER), **kwargs)


def create_unique_prefix(**kwargs):
    prefix_index = next(_PREFIX_COUNTER)
    second_octet, third_octet = divmod(prefix_index, 250)
    return create_test_prefix(f"10.{second_octet}.{third_octet}.0/24", **kwargs)


def create_unique_roa(prefix: str = "roa", signed_by=None, **kwargs):
    token = unique_token(prefix)
    if signed_by is None:
        signed_by = create_unique_certificate("roa-signing-certificate")
    return create_test_roa(name=f"{prefix.title()} {token}", signed_by=signed_by, **kwargs)


_SKIP_VALUE = object()
_FORM_SCENARIO_BUILDERS: dict[str, Callable[[], dict[str, object]]] = {}
_FILTER_SCENARIO_BUILDERS: dict[str, Callable[[], tuple[FilterCase, ...]]] = {}
_TABLE_SCENARIO_BUILDERS: dict[str, Callable[[], None]] = {}
_READONLY_INSTANCE_BUILDERS: dict[str, Callable[[], object]] = {}


def _registry_key_from_field(field_name: str) -> str | None:
    normalized = field_name.replace("_", "")
    try:
        get_object_spec(normalized)
    except KeyError:
        return None
    return normalized


def _get_choice_value(spec, field_name: str):
    if spec is None or spec.form is None:
        return None

    form_field = getattr(forms, spec.form.class_name)().fields.get(field_name)
    if form_field is not None and getattr(form_field, "queryset", None) is not None:
        return None
    choices = getattr(form_field, "choices", None)
    if choices:
        for value, _label in choices:
            if value not in ("", None):
                return value

    model_field = spec.model._meta.fields_map.get(field_name)
    if model_field is None:
        try:
            model_field = spec.model._meta.get_field(field_name)
        except Exception:
            model_field = None

    choices = getattr(model_field, "choices", None)
    if choices:
        for value, _label in choices:
            if value not in ("", None):
                return value

    return None


def _build_related_value(field_name: str, token: str, variant: int = 0, for_form: bool = False, spec=None):
    if field_name == "parent_rir":
        value = create_unique_rir(f"{token}-rir")
    elif field_name in {"asn", "origin_as", "customer_as", "provider_as"}:
        value = create_unique_asn()
    elif field_name == "rpki_org":
        value = create_unique_organization(f"{token}-org")
    elif field_name in {"resource_certificate", "issuing_certificate"}:
        org = create_unique_organization(f"{token}-resource-certificate-org")
        value = create_unique_certificate(f"{token}-resource-certificate", rpki_org=org)
    elif field_name == "signed_by":
        org = create_unique_organization(f"{token}-signed-by-org")
        value = create_unique_certificate(f"{token}-certificate", rpki_org=org)
    elif field_name == "prefix":
        value = create_unique_prefix()
    elif field_name == "roa_name":
        org = create_unique_organization(f"{token}-roa-org")
        certificate = create_unique_certificate(f"{token}-roa-certificate", rpki_org=org)
        value = create_unique_roa(f"{token}-roa", signed_by=certificate)
    elif field_name == "trust_anchor":
        value = create_test_trust_anchor(name=f"Trust Anchor {token}")
    elif field_name == "publication_point":
        value = create_test_publication_point(name=f"Publication Point {token}")
    elif field_name == "repository":
        value = create_test_repository(name=f"Repository {token}")
    elif field_name == "ee_certificate":
        value = create_test_end_entity_certificate(name=f"EE Certificate {token}")
    elif field_name in {"manifest", "current_manifest"}:
        value = create_test_manifest(name=f"Manifest {token}")
    elif field_name == "current_crl":
        value = create_test_certificate_revocation_list(name=f"CRL {token}")
    elif field_name == "validator":
        value = create_test_validator_instance(name=f"Validator {token}")
    elif field_name == "validation_run":
        value = create_test_validation_run(name=f"Validation Run {token}")
    elif field_name == "intent_profile":
        value = create_test_routing_intent_profile(name=f"Intent Profile {token}")
    elif field_name == "source_rule":
        value = create_test_routing_intent_rule(name=f"Intent Rule {token}")
    elif field_name == "applied_override":
        value = create_test_roa_intent_override(name=f"Intent Override {token}")
    elif field_name == "derivation_run":
        value = create_test_intent_derivation_run(name=f"Derivation Run {token}")
    elif field_name == "roa_intent":
        value = create_test_roa_intent(name=f"ROA Intent {token}")
    elif field_name == "roa":
        value = create_test_roa(name=f"ROA {token}")
    elif field_name == "basis_derivation_run":
        value = create_test_intent_derivation_run(name=f"Basis Run {token}")
    elif field_name == "reconciliation_run":
        if spec is not None and spec.model.__name__ in {
            "ASPAReconciliationRun",
            "ASPAIntentResult",
            "PublishedASPAResult",
            "ASPAIntentMatch",
        }:
            value = create_test_aspa_reconciliation_run(name=f"ASPA Reconciliation Run {token}")
        else:
            value = create_test_roa_reconciliation_run(name=f"Reconciliation Run {token}")
    elif field_name == "aspa_intent":
        value = create_test_aspa_intent(name=f"ASPA Intent {token}")
    elif field_name == "best_roa":
        value = create_test_roa(name=f"Best ROA {token}")
    elif field_name == "best_aspa":
        value = create_test_aspa(name=f"Best ASPA {token}")
    elif field_name == "best_imported_aspa":
        value = create_test_imported_aspa(name=f"Best Imported ASPA {token}")
    elif field_name == "certificate_name":
        org = create_unique_organization(f"{token}-certificate-org")
        value = create_unique_certificate(f"{token}-certificate", rpki_org=org)
    elif field_name == "certificate_name2":
        org = create_unique_organization(f"{token}-certificate2-org")
        value = create_unique_certificate(f"{token}-certificate2", rpki_org=org)
    else:
        registry_key = _registry_key_from_field(field_name)
        if registry_key is not None:
            value = create_test_model(
                get_object_spec(registry_key).model.__name__,
                **_build_model_kwargs_for_spec(get_object_spec(registry_key), f"{token}-{field_name}", variant=variant),
            )
        else:
            value = _SKIP_VALUE

    if for_form and value is not _SKIP_VALUE and hasattr(value, "pk"):
        return value.pk
    return value


def _build_scalar_value(field_name: str, token: str, variant: int = 0, for_form: bool = False, spec=None):
    if field_name in {"tenant", "tags"}:
        return _SKIP_VALUE
    if field_name == "_init_time":
        return 0
    choice_value = _get_choice_value(spec, field_name)
    if choice_value is not None:
        return choice_value
    if field_name in {"name", "org_id", "issuer", "subject", "serial", "publication_url", "ca_repository", "ext_url"}:
        if field_name in {"publication_url", "ca_repository", "ext_url"}:
            return f"https://{token}-{variant}.{field_name}.invalid"
        return f"{field_name.replace('_', ' ').title()} {token} {variant}"
    if field_name in {"comments"}:
        return f"Comments {token} {variant}"
    if field_name in {"auto_renews", "self_hosted", "is_active", "is_current"}:
        return variant % 2 == 0
    if field_name in {"valid_from", "valid_to"}:
        return "2025-01-01" if for_form else date(2025, 1, 1)
    if field_name in {"last_observed_at", "this_update", "next_update", "started_at", "completed_at", "revoked_at", "observed_at", "last_run_at"}:
        return "2025-01-01 00:00:00" if for_form else datetime(2025, 1, 1, 0, 0, 0)
    if field_name in {
        "max_length",
        "weight",
        "max_length_value",
        "origin_asn_value",
        "prefix_count_scanned",
        "intent_count_emitted",
        "warning_count",
        "match_count",
        "matched_intent_count",
        "published_roa_count",
        "intent_count",
        "published_aspa_count",
    }:
        return 24 + variant
    if field_name in {"repository_serial"}:
        return f"serial-{token}-{variant}"
    if field_name in {"input_fingerprint", "intent_key"}:
        return f"{field_name}-{token}-{variant}"
    if field_name in {"description", "prefix_selector_query", "asn_selector_query", "error_summary", "explanation", "reason"}:
        return f"{field_name.replace('_', ' ').title()} {token} {variant}"

    related_value = _build_related_value(field_name, token, variant=variant, for_form=for_form, spec=spec)
    if related_value is not _SKIP_VALUE:
        return related_value

    if field_name.endswith("_id"):
        return f"{field_name.replace('_', '-')}-{token}-{variant}"

    return f"{field_name.replace('_', ' ').title()} {token} {variant}"


def _build_model_kwargs_for_spec(spec, token: str, variant: int = 0) -> dict[str, object]:
    if spec.form is None:
        return {}

    form_class = getattr(forms, spec.form.class_name)
    form = form_class()
    kwargs: dict[str, object] = {}
    for field_name, field in form.fields.items():
        if field_name.startswith("_"):
            continue

        model_field = None
        try:
            model_field = spec.model._meta.get_field(field_name)
        except Exception:
            model_field = None

        should_include = field.required
        if model_field is not None:
            should_include = should_include or (
                not getattr(model_field, "null", False)
                and not getattr(model_field, "blank", False)
                and not model_field.has_default()
            )
        if not should_include:
            continue

        value = _build_scalar_value(field_name, token, variant=variant, for_form=False, spec=spec)
        if value is not _SKIP_VALUE:
            kwargs[field_name] = value
    return kwargs


def _build_form_data_for_spec(spec, token: str | None = None, variant: int = 0) -> dict[str, object]:
    token = token or unique_token(spec.registry_key)
    kwargs = _build_model_kwargs_for_spec(spec, token, variant=variant)
    form_data: dict[str, object] = {}
    form_class = getattr(forms, spec.form.class_name)
    form = form_class()
    for field_name, field in form.fields.items():
        if field_name not in kwargs and not field_name.startswith("_"):
            try:
                model_field = spec.model._meta.get_field(field_name)
            except Exception:
                model_field = None

            if model_field is None:
                if not field.required:
                    continue
            elif model_field.blank or model_field.null or model_field.has_default():
                continue
        if field_name in kwargs:
            value = kwargs[field_name]
        else:
            value = _build_scalar_value(field_name, token, variant=variant, for_form=True, spec=spec)
        if value is not _SKIP_VALUE:
            form_data[field_name] = value
    return form_data


def _build_instance_for_spec(spec, token: str | None = None, variant: int = 0):
    token = token or unique_token(spec.registry_key)
    builder = _READONLY_INSTANCE_BUILDERS.get(spec.registry_key)
    if builder is not None:
        return builder()
    return create_test_model(spec.model.__name__, **_build_model_kwargs_for_spec(spec, token, variant=variant))


def _extract_field_value(instance: object, field_name: str):
    value = getattr(instance, field_name)
    if hasattr(value, "pk"):
        return value.pk
    return value


def _resolve_lookup_value(instance: object, lookup: str):
    value = instance
    parts = lookup.split("__")
    if parts[-1] in {"icontains", "contains", "iexact", "exact"}:
        parts = parts[:-1]
    for part in parts:
        value = getattr(value, part)
    if hasattr(value, "pk"):
        return str(value)
    return value


def _build_filter_cases_for_spec(spec) -> tuple[FilterCase, ...]:
    token = unique_token(f"{spec.registry_key}-filter")
    alpha = _build_instance_for_spec(spec, token=f"{token}-alpha", variant=0)
    bravo = _build_instance_for_spec(spec, token=f"{token}-bravo", variant=1)

    search_field = next(iter(spec.filterset.search_fields), None)
    search_query = None
    if search_field is not None:
        search_value = _resolve_lookup_value(alpha, search_field)
        search_query = str(search_value)

    exact_field = next((field for field in spec.filterset.fields if field not in {"tenant", "tags"}), None)
    if exact_field is not None:
        try:
            model_field = spec.model._meta.get_field(exact_field)
        except Exception:
            model_field = None
        if model_field is not None and model_field.get_internal_type() in {"CharField", "TextField"}:
            exact_field = None
    exact_value = _extract_field_value(bravo, exact_field) if exact_field is not None else None

    cases = []
    if search_query:
        cases.append(
            FilterCase(
                label=f"search by {search_field}",
                params={"q": search_query},
                expected_objects=(alpha,),
            )
        )
    if exact_field is not None:
        cases.append(
            FilterCase(
                label=f"filter by {exact_field}",
                params={exact_field: exact_value},
                expected_objects=(bravo,),
            )
        )
    return tuple(cases)


def _build_table_rows_for_spec(spec) -> None:
    _build_instance_for_spec(spec, token=f"{spec.registry_key}-table-a", variant=0)
    _build_instance_for_spec(spec, token=f"{spec.registry_key}-table-b", variant=1)


def _register_scenario_builders() -> None:
    _FORM_SCENARIO_BUILDERS.update(
        {
            "organization": build_organization_form_data,
            "certificate": build_certificate_form_data,
            "roa": build_roa_form_data,
            "roaprefix": build_roa_prefix_form_data,
            "certificateprefix": build_certificate_prefix_form_data,
            "certificateasn": build_certificate_asn_form_data,
        }
    )
    _FILTER_SCENARIO_BUILDERS.update(
        {
            "organization": build_organization_filter_cases,
            "certificate": build_certificate_filter_cases,
            "roa": build_roa_filter_cases,
            "roaprefix": build_roa_prefix_filter_cases,
            "certificateprefix": build_certificate_prefix_filter_cases,
            "certificateasn": build_certificate_asn_filter_cases,
        }
    )
    _TABLE_SCENARIO_BUILDERS.update(
        {
            "organization": build_organization_table_rows,
            "certificate": build_certificate_table_rows,
            "roa": build_roa_table_rows,
            "roaprefix": build_roa_prefix_table_rows,
            "certificateprefix": build_certificate_prefix_table_rows,
            "certificateasn": build_certificate_asn_table_rows,
        }
    )
    _READONLY_INSTANCE_BUILDERS.update(
        {
            "intentderivationrun": lambda: create_test_intent_derivation_run(name=f"Intent Derivation Run {unique_token('intent-derivation-run')}"),
            "roaintent": lambda: create_test_roa_intent(
                name=f"ROA Intent {unique_token('roa-intent')}",
                origin_asn=create_unique_asn(),
                max_length=24,
            ),
            "aspaintent": lambda: create_test_aspa_intent(
                name=f"ASPA Intent {unique_token('aspa-intent')}",
                customer_as=create_unique_asn(),
                provider_as=create_unique_asn(),
            ),
            "roaintentmatch": lambda: create_test_roa_intent_match(name=f"ROA Intent Match {unique_token('roa-intent-match')}"),
            "aspaintentmatch": lambda: create_test_aspa_intent_match(name=f"ASPA Intent Match {unique_token('aspa-intent-match')}"),
            "roareconciliationrun": lambda: create_test_roa_reconciliation_run(name=f"ROA Reconciliation Run {unique_token('roa-reconciliation-run')}"),
            "roalintrun": lambda: create_test_roa_lint_run(name=f"ROA Lint Run {unique_token('roa-lint-run')}"),
            "aspareconciliationrun": lambda: create_test_aspa_reconciliation_run(name=f"ASPA Reconciliation Run {unique_token('aspa-reconciliation-run')}"),
            "roaintentresult": lambda: create_test_roa_intent_result(name=f"ROA Intent Result {unique_token('roa-intent-result')}"),
            "roalintfinding": lambda: create_test_roa_lint_finding(name=f"ROA Lint Finding {unique_token('roa-lint-finding')}"),
            "aspaintentresult": lambda: create_test_aspa_intent_result(name=f"ASPA Intent Result {unique_token('aspa-intent-result')}"),
            "publishedroaresult": lambda: create_test_published_roa_result(name=f"Published ROA Result {unique_token('published-roa-result')}"),
            "publishedasparesult": lambda: create_test_published_aspa_result(name=f"Published ASPA Result {unique_token('published-aspa-result')}"),
            "rpkiprovideraccount": lambda: create_test_provider_account(
                name=f"Provider Account {unique_token('provider-account')}",
                org_handle=f"ORG{unique_token('orghandle')}",
            ),
            "providersnapshot": lambda: create_test_provider_snapshot(name=f"Provider Snapshot {unique_token('provider-snapshot')}"),
            "providersnapshotdiff": lambda: create_test_provider_snapshot_diff(
                name=f"Provider Snapshot Diff {unique_token('provider-snapshot-diff')}"
            ),
            "providersnapshotdiffitem": lambda: create_test_provider_snapshot_diff_item(
                name=f"Provider Snapshot Diff Item {unique_token('provider-snapshot-diff-item')}"
            ),
            "providersyncrun": lambda: create_test_provider_sync_run(name=f"Provider Sync Run {unique_token('provider-sync-run')}"),
            "providerwriteexecution": lambda: create_test_provider_write_execution(
                name=f"Provider Write Execution {unique_token('provider-write-execution')}"
            ),
            "approvalrecord": lambda: create_test_approval_record(
                name=f"Approval Record {unique_token('approval-record')}"
            ),
            "externalobjectreference": lambda: create_test_external_object_reference(
                name=f"External Object Reference {unique_token('external-object-reference')}"
            ),
            "importedroaauthorization": lambda: create_test_imported_roa_authorization(
                name=f"Imported ROA Authorization {unique_token('imported-roa-authorization')}",
                origin_asn=create_unique_asn(),
                max_length=24,
            ),
            "importedaspa": lambda: create_test_imported_aspa(
                name=f"Imported ASPA {unique_token('imported-aspa')}",
                customer_as=create_unique_asn(),
            ),
            "importedcametadata": lambda: create_test_imported_ca_metadata(
                name=f"Imported CA Metadata {unique_token('imported-ca-metadata')}"
            ),
            "importedparentlink": lambda: create_test_imported_parent_link(
                name=f"Imported Parent Link {unique_token('imported-parent-link')}"
            ),
            "importedchildlink": lambda: create_test_imported_child_link(
                name=f"Imported Child Link {unique_token('imported-child-link')}"
            ),
            "importedresourceentitlement": lambda: create_test_imported_resource_entitlement(
                name=f"Imported Resource Entitlement {unique_token('imported-resource-entitlement')}"
            ),
            "importedpublicationpoint": lambda: create_test_imported_publication_point(
                name=f"Imported Publication Point {unique_token('imported-publication-point')}"
            ),
            "importedsignedobject": lambda: create_test_imported_signed_object(
                name=f"Imported Signed Object {unique_token('imported-signed-object')}"
            ),
            "importedcertificateobservation": lambda: create_test_imported_certificate_observation(
                name=f"Imported Certificate Observation {unique_token('imported-certificate-observation')}"
            ),
            "roachangeplan": lambda: build_roa_change_plan_matrix_instance(),
            "roachangeplanitem": lambda: build_roa_change_plan_matrix_item_instance(),
            "roavalidationsimulationrun": lambda: create_test_roa_validation_simulation_run(
                name=f"ROA Validation Simulation Run {unique_token('roa-validation-simulation-run')}"
            ),
            "roavalidationsimulationresult": lambda: create_test_roa_validation_simulation_result(
                name=f"ROA Validation Simulation Result {unique_token('roa-validation-simulation-result')}"
            ),
        }
    )


@dataclass(frozen=True)
class FormScenario:
    object_key: str
    required_fields: tuple[str, ...]
    build_valid_data: Callable[[], dict[str, object]]


@dataclass(frozen=True)
class FilterCase:
    label: str
    params: dict[str, object]
    expected_objects: tuple[object, ...]


@dataclass(frozen=True)
class FilterSetScenario:
    object_key: str
    build_filter_cases: Callable[[], tuple[FilterCase, ...]]


@dataclass(frozen=True)
class TableScenario:
    object_key: str
    build_rows: Callable[[], None]


def build_organization_form_data() -> dict[str, object]:
    token = unique_token("form-org")
    return {
        "org_id": token,
        "name": f"RPKI Test Org {token}",
    }


def build_certificate_form_data() -> dict[str, object]:
    organization = create_unique_organization("certificate-form-org")
    return {
        "name": f"RPKI Test Certificate {unique_token('certificate-form')}",
        "auto_renews": True,
        "self_hosted": False,
        "rpki_org": organization.pk,
    }


def build_roa_form_data() -> dict[str, object]:
    organization = create_unique_organization("roa-form-org")
    certificate = create_unique_certificate("roa-form-certificate", rpki_org=organization)
    asn = create_unique_asn()
    return {
        "name": f"RPKI Test ROA {unique_token('roa-form')}",
        "origin_as": asn.pk,
        "auto_renews": True,
        "signed_by": certificate.pk,
    }


def build_roa_prefix_form_data() -> dict[str, object]:
    organization = create_unique_organization("roa-prefix-form-org")
    certificate = create_unique_certificate("roa-prefix-form-certificate", rpki_org=organization)
    roa = create_unique_roa("roa-prefix-form-roa", signed_by=certificate)
    prefix = create_unique_prefix()
    return {
        "prefix": prefix.pk,
        "max_length": 24,
        "roa_name": roa.pk,
    }


def build_certificate_prefix_form_data() -> dict[str, object]:
    organization = create_unique_organization("certificate-prefix-form-org")
    certificate = create_unique_certificate("certificate-prefix-form-certificate", rpki_org=organization)
    prefix = create_unique_prefix()
    return {
        "prefix": prefix.pk,
        "certificate_name": certificate.pk,
    }


def build_certificate_asn_form_data() -> dict[str, object]:
    organization = create_unique_organization("certificate-asn-form-org")
    certificate = create_unique_certificate("certificate-asn-form-certificate", rpki_org=organization)
    asn = create_unique_asn()
    return {
        "asn": asn.pk,
        "certificate_name2": certificate.pk,
    }


def _build_form_scenario(spec):
    form_class = getattr(forms, spec.form.class_name)
    required_fields = tuple(
        name
        for name, field in form_class().fields.items()
        if field.required and not name.startswith("_")
    )
    builder = _FORM_SCENARIO_BUILDERS.get(spec.registry_key)
    if builder is None:
        builder = lambda spec=spec: _build_form_data_for_spec(spec)

    def build_valid_data():
        payload = dict(builder())
        if "_init_time" in form_class().fields and "_init_time" not in payload:
            payload["_init_time"] = 0
        return payload

    return FormScenario(object_key=spec.registry_key, required_fields=required_fields, build_valid_data=build_valid_data)


FORM_SCENARIOS = tuple(_build_form_scenario(spec) for spec in FORM_OBJECT_SPECS)


def build_organization_filter_cases() -> tuple[FilterCase, ...]:
    token = unique_token("organization-filter")
    rir = create_unique_rir("filter-rir")
    alpha = create_test_organization(
        org_id=f"alpha-{token}",
        name=f"Alpha Org {token}",
        ext_url=f"https://alpha-{token}.invalid",
        comments=f"alpha comments {token}",
        parent_rir=rir,
    )
    create_test_organization(
        org_id=f"bravo-{token}",
        name=f"Bravo Org {token}",
        ext_url=f"https://bravo-{token}.invalid",
    )
    return (
        FilterCase(
            label="search by ext_url",
            params={"q": alpha.ext_url},
            expected_objects=(alpha,),
        ),
        FilterCase(
            label="filter by parent_rir",
            params={"parent_rir": rir.pk},
            expected_objects=(alpha,),
        ),
    )


def build_certificate_filter_cases() -> tuple[FilterCase, ...]:
    token = unique_token("certificate-filter")
    organization_a = create_test_organization(org_id=f"cert-filter-a-{token}", name=f"Certificate Filter A {token}")
    organization_b = create_test_organization(org_id=f"cert-filter-b-{token}", name=f"Certificate Filter B {token}")
    alpha = create_test_certificate(
        name=f"Alpha Certificate {token}",
        issuer=f"Alpha Issuer {token}",
        rpki_org=organization_a,
        self_hosted=False,
    )
    bravo = create_test_certificate(
        name=f"Bravo Certificate {token}",
        issuer=f"Bravo Issuer {token}",
        rpki_org=organization_b,
        self_hosted=True,
    )
    return (
        FilterCase(
            label="search by issuer",
            params={"q": bravo.issuer},
            expected_objects=(bravo,),
        ),
        FilterCase(
            label="filter by rpki_org",
            params={"rpki_org": organization_a.pk},
            expected_objects=(alpha,),
        ),
    )


def build_roa_filter_cases() -> tuple[FilterCase, ...]:
    token = unique_token("roa-filter")
    organization = create_test_organization(org_id=f"roa-filter-org-{token}", name=f"ROA Filter Org {token}")
    certificate_a = create_test_certificate(name=f"ROA Filter Certificate A {token}", rpki_org=organization)
    certificate_b = create_test_certificate(name=f"ROA Filter Certificate B {token}", rpki_org=organization)
    asn_a = create_unique_asn()
    asn_b = create_unique_asn()
    alpha = create_test_roa(
        name=f"Alpha ROA {token}",
        origin_as=asn_a,
        signed_by=certificate_a,
        comments=f"alpha comment {token}",
    )
    bravo = create_test_roa(
        name=f"Bravo ROA {token}",
        origin_as=asn_b,
        signed_by=certificate_b,
    )
    return (
        FilterCase(
            label="search by comments",
            params={"q": alpha.comments},
            expected_objects=(alpha,),
        ),
        FilterCase(
            label="filter by signed_by",
            params={"signed_by": certificate_b.pk},
            expected_objects=(bravo,),
        ),
    )


def build_roa_prefix_filter_cases() -> tuple[FilterCase, ...]:
    token = unique_token("roa-prefix-filter")
    organization = create_test_organization(org_id=f"roa-prefix-filter-org-{token}", name=f"ROA Prefix Filter Org {token}")
    certificate = create_test_certificate(name=f"ROA Prefix Filter Certificate {token}", rpki_org=organization)
    roa_a = create_test_roa(name=f"ROA Prefix Parent A {token}", signed_by=certificate)
    roa_b = create_test_roa(name=f"ROA Prefix Parent B {token}", signed_by=certificate)
    prefix_a = create_unique_prefix()
    prefix_b = create_unique_prefix()
    alpha = create_test_roa_prefix(prefix=prefix_a, roa=roa_a, max_length=24, comments=f"alpha prefix comment {token}")
    bravo = create_test_roa_prefix(prefix=prefix_b, roa=roa_b, max_length=25)
    return (
        FilterCase(
            label="search by prefix",
            params={"q": str(prefix_b.prefix)},
            expected_objects=(bravo,),
        ),
        FilterCase(
            label="filter by roa_name",
            params={"roa_name": roa_a.pk},
            expected_objects=(alpha,),
        ),
    )


def build_certificate_prefix_filter_cases() -> tuple[FilterCase, ...]:
    token = unique_token("certificate-prefix-filter")
    organization = create_test_organization(org_id=f"certificate-prefix-filter-org-{token}", name=f"Certificate Prefix Filter Org {token}")
    certificate_a = create_test_certificate(name=f"Certificate Prefix Filter A {token}", rpki_org=organization)
    certificate_b = create_test_certificate(name=f"Certificate Prefix Filter B {token}", rpki_org=organization)
    prefix_a = create_unique_prefix()
    prefix_b = create_unique_prefix()
    alpha = create_test_certificate_prefix(
        prefix=prefix_a,
        certificate=certificate_a,
        comments=f"alpha certificate prefix {token}",
    )
    bravo = create_test_certificate_prefix(prefix=prefix_b, certificate=certificate_b)
    return (
        FilterCase(
            label="search by prefix",
            params={"q": str(prefix_a.prefix)},
            expected_objects=(alpha,),
        ),
        FilterCase(
            label="filter by certificate_name",
            params={"certificate_name": certificate_b.pk},
            expected_objects=(bravo,),
        ),
    )


def build_certificate_asn_filter_cases() -> tuple[FilterCase, ...]:
    token = unique_token("certificate-asn-filter")
    organization = create_test_organization(org_id=f"certificate-asn-filter-org-{token}", name=f"Certificate ASN Filter Org {token}")
    certificate_a = create_test_certificate(name=f"Certificate ASN Filter A {token}", rpki_org=organization)
    certificate_b = create_test_certificate(name=f"Certificate ASN Filter B {token}", rpki_org=organization)
    asn_a = create_unique_asn()
    asn_b = create_unique_asn()
    alpha = create_test_certificate_asn(
        asn=asn_a,
        certificate=certificate_a,
        comments=f"alpha certificate asn {token}",
    )
    bravo = create_test_certificate_asn(asn=asn_b, certificate=certificate_b)
    return (
        FilterCase(
            label="search by related certificate name",
            params={"q": certificate_b.name},
            expected_objects=(bravo,),
        ),
        FilterCase(
            label="filter by certificate_name2",
            params={"certificate_name2": certificate_a.pk},
            expected_objects=(alpha,),
        ),
    )


def _build_filterset_scenario(spec):
    builder = _FILTER_SCENARIO_BUILDERS.get(spec.registry_key)
    if builder is None:
        builder = lambda spec=spec: _build_filter_cases_for_spec(spec)
    return FilterSetScenario(object_key=spec.registry_key, build_filter_cases=builder)


FILTERSET_SCENARIOS = tuple(_build_filterset_scenario(spec) for spec in FILTERSET_OBJECT_SPECS)


def build_organization_table_rows() -> None:
    token = unique_token("table-org")
    create_test_organization(org_id=f"table-org-a-{token}", name=f"Table Organization A {token}")
    create_test_organization(org_id=f"table-org-b-{token}", name=f"Table Organization B {token}")


def build_certificate_table_rows() -> None:
    organization = create_unique_organization("table-cert-org")
    token = unique_token("table-cert")
    create_test_certificate(name=f"Table Certificate A {token}", issuer=f"Issuer A {token}", rpki_org=organization)
    create_test_certificate(name=f"Table Certificate B {token}", issuer=f"Issuer B {token}", rpki_org=organization)


def build_roa_table_rows() -> None:
    organization = create_unique_organization("table-roa-org")
    certificate = create_unique_certificate("table-roa-certificate", rpki_org=organization)
    token = unique_token("table-roa")
    create_test_roa(name=f"Table ROA A {token}", origin_as=create_unique_asn(), signed_by=certificate)
    create_test_roa(name=f"Table ROA B {token}", origin_as=create_unique_asn(), signed_by=certificate)


def build_roa_prefix_table_rows() -> None:
    organization = create_unique_organization("table-roa-prefix-org")
    certificate = create_unique_certificate("table-roa-prefix-certificate", rpki_org=organization)
    roa = create_unique_roa("table-roa-prefix-parent", signed_by=certificate)
    create_test_roa_prefix(prefix=create_unique_prefix(), roa=roa, max_length=24)
    create_test_roa_prefix(prefix=create_unique_prefix(), roa=roa, max_length=25)


def build_certificate_prefix_table_rows() -> None:
    organization = create_unique_organization("table-certificate-prefix-org")
    certificate = create_unique_certificate("table-certificate-prefix-parent", rpki_org=organization)
    create_test_certificate_prefix(prefix=create_unique_prefix(), certificate=certificate)
    create_test_certificate_prefix(prefix=create_unique_prefix(), certificate=certificate)


def build_certificate_asn_table_rows() -> None:
    organization = create_unique_organization("table-certificate-asn-org")
    certificate = create_unique_certificate("table-certificate-asn-parent", rpki_org=organization)
    create_test_certificate_asn(asn=create_unique_asn(), certificate=certificate)
    create_test_certificate_asn(asn=create_unique_asn(), certificate=certificate)


def build_roa_change_plan_matrix_instance():
    return create_test_roa_change_plan_matrix(name_token=unique_token('roa-change-plan-matrix')).provider_plan


def build_roa_change_plan_matrix_item_instance():
    return create_test_roa_change_plan_item(
        name=f"ROA Change Plan Item {unique_token('roa-change-plan-item')}",
    )


_register_scenario_builders()


def _build_table_scenario(spec):
    builder = _TABLE_SCENARIO_BUILDERS.get(spec.registry_key)
    if builder is None:
        builder = lambda spec=spec: _build_table_rows_for_spec(spec)
    return TableScenario(object_key=spec.registry_key, build_rows=builder)


TABLE_SCENARIOS = tuple(_build_table_scenario(spec) for spec in TABLE_OBJECT_SPECS)


@dataclass(frozen=True)
class ModelScenario:
    object_name: str
    build_instance: Callable[[], object]


def build_repository_instance():
    return create_test_repository(name=f"Repository {unique_token('repository')}")


def build_publication_point_instance():
    organization = create_unique_organization("publication-point-org")
    repository = create_test_repository(name=f"Repository {unique_token('publication-point-repository')}", organization=organization)
    return create_test_publication_point(
        name=f"Publication Point {unique_token('publication-point')}",
        organization=organization,
        repository=repository,
        publication_uri="https://publication.example.invalid/publish",
        rsync_base_uri="rsync://publication.example.invalid/module/",
        rrdp_notify_uri="https://publication.example.invalid/rrdp/notify.xml",
    )


def build_trust_anchor_instance():
    organization = create_unique_organization("trust-anchor-org")
    return create_test_trust_anchor(
        name=f"Trust Anchor {unique_token('trust-anchor')}",
        organization=organization,
        subject="CN=Trust Anchor",
        subject_key_identifier="ta-ski",
        rsync_uri="rsync://trust-anchor.example.invalid/root/",
        rrdp_notify_uri="https://trust-anchor.example.invalid/rrdp/notify.xml",
    )


def build_trust_anchor_locator_instance():
    trust_anchor = build_trust_anchor_instance()
    return create_test_trust_anchor_locator(
        name=f"Trust Anchor Locator {unique_token('tal')}",
        trust_anchor=trust_anchor,
        rsync_uri="rsync://trust-anchor.example.invalid/root.ta",
        https_uri="https://trust-anchor.example.invalid/root.tal",
        public_key_info="public-key-info",
    )


def build_end_entity_certificate_instance():
    organization = create_unique_organization("ee-certificate-org")
    resource_certificate = create_unique_certificate("ee-certificate-resource", rpki_org=organization)
    publication_point = create_publication_point_instance_for_section9(organization)
    return create_test_end_entity_certificate(
        name=f"End Entity Certificate {unique_token('ee-certificate')}",
        organization=organization,
        resource_certificate=resource_certificate,
        publication_point=publication_point,
        subject="CN=EE",
        issuer="CN=Issuer",
        serial="1234",
        ski="ski",
        aki="aki",
        public_key="public-key",
    )


def create_publication_point_instance_for_section9(organization):
    repository = create_test_repository(name=f"Repository {unique_token('publication-point-repository')}", organization=organization)
    return create_test_publication_point(
        name=f"Publication Point {unique_token('publication-point')}",
        organization=organization,
        repository=repository,
        publication_uri="https://publication.example.invalid/publish",
        rsync_base_uri="rsync://publication.example.invalid/module/",
        rrdp_notify_uri="https://publication.example.invalid/rrdp/notify.xml",
    )


def build_signed_object_instance():
    organization = create_unique_organization("signed-object-org")
    resource_certificate = create_unique_certificate("signed-object-resource", rpki_org=organization)
    ee_certificate = create_test_end_entity_certificate(
        name=f"End Entity Certificate {unique_token('signed-object-ee')}",
        organization=organization,
        resource_certificate=resource_certificate,
        publication_point=create_publication_point_instance_for_section9(organization),
    )
    return create_test_signed_object(
        name=f"Signed Object {unique_token('signed-object')}",
        organization=organization,
        object_type=rpki_models.SignedObjectType.ROA,
        display_label="Signed Object",
        resource_certificate=resource_certificate,
        ee_certificate=ee_certificate,
        publication_point=ee_certificate.publication_point,
        filename="object.roa",
        object_uri="rsync://publication.example.invalid/module/object.roa",
        repository_uri="rsync://publication.example.invalid/module/",
        content_hash="hash",
        serial_or_version="1",
    )


def build_certificate_revocation_list_instance():
    organization = create_unique_organization("crl-org")
    certificate = create_unique_certificate("crl-certificate", rpki_org=organization)
    publication_point = create_publication_point_instance_for_section9(organization)
    signed_object = create_test_signed_object(
        name=f"Signed Object {unique_token('crl-signed-object')}",
        organization=organization,
        object_type=rpki_models.SignedObjectType.CRL,
        resource_certificate=certificate,
        publication_point=publication_point,
        object_uri="https://publication.example.invalid/crl.crl",
        repository_uri="https://publication.example.invalid/",
        filename="crl.crl",
    )
    return create_test_certificate_revocation_list(
        name=f"Certificate Revocation List {unique_token('crl')}",
        organization=organization,
        issuing_certificate=certificate,
        signed_object=signed_object,
        publication_point=publication_point,
        crl_number="1",
        publication_uri="https://publication.example.invalid/crl.crl",
    )


def build_manifest_instance():
    signed_object = build_signed_object_instance()
    crl = build_certificate_revocation_list_instance()
    return create_test_manifest(
        name=f"Manifest {unique_token('manifest')}",
        signed_object=signed_object,
        manifest_number="1",
        current_crl=crl,
    )


def build_trust_anchor_key_instance():
    trust_anchor = build_trust_anchor_instance()
    signed_object = build_signed_object_instance()
    return create_test_trust_anchor_key(
        name=f"Trust Anchor Key {unique_token('tak')}",
        trust_anchor=trust_anchor,
        signed_object=signed_object,
        current_public_key="current-public-key",
        next_public_key="next-public-key",
        publication_uri="https://publication.example.invalid/tak.tak",
    )


def build_aspa_instance():
    organization = create_unique_organization("aspa-org")
    signed_object = build_signed_object_instance()
    return create_test_aspa(
        name=f"ASPA {unique_token('aspa')}",
        organization=organization,
        signed_object=signed_object,
        customer_as=create_unique_asn(),
        valid_from=date(2025, 1, 1),
        valid_to=date(2025, 12, 31),
    )


def build_rsc_instance():
    organization = create_unique_organization("rsc-org")
    signed_object = build_signed_object_instance()
    return create_test_rsc(
        name=f"RSC {unique_token('rsc')}",
        organization=organization,
        signed_object=signed_object,
        version="1",
        digest_algorithm="sha256",
    )


def build_router_certificate_instance():
    organization = create_unique_organization("router-certificate-org")
    publication_point = create_publication_point_instance_for_section9(organization)
    resource_certificate = create_unique_certificate("router-certificate-resource", rpki_org=organization)
    ee_certificate = create_test_end_entity_certificate(
        name=f"End Entity Certificate {unique_token('router-certificate-ee')}",
        organization=organization,
        resource_certificate=resource_certificate,
        publication_point=publication_point,
        subject="CN=Router",
        issuer="CN=Issuer",
        serial="router-serial",
        ski="router-ski",
    )
    return create_test_router_certificate(
        name=f"Router Certificate {unique_token('router-certificate')}",
        organization=organization,
        resource_certificate=resource_certificate,
        publication_point=publication_point,
        ee_certificate=ee_certificate,
        asn=create_unique_asn(),
        subject="CN=Router",
        issuer="CN=Issuer",
        serial="router-serial",
        ski="router-ski",
        router_public_key="router-public-key",
    )


def build_validator_instance():
    organization = create_unique_organization("validator-org")
    return create_test_validator_instance(
        name=f"Validator Instance {unique_token('validator')}",
        organization=organization,
        software_name="validator",
        software_version="1.0",
        base_url="https://validator.example.invalid",
    )


def build_validation_run_instance():
    validator = build_validator_instance()
    return create_test_validation_run(
        name=f"Validation Run {unique_token('validation-run')}",
        validator=validator,
        status=rpki_models.ValidationRunStatus.RUNNING,
        repository_serial="serial-1",
    )


def build_object_validation_result_instance():
    validation_run = build_validation_run_instance()
    signed_object = build_signed_object_instance()
    return create_test_object_validation_result(
        name=f"Object Validation Result {unique_token('validation-result')}",
        validation_run=validation_run,
        signed_object=signed_object,
        validation_state=rpki_models.ValidationState.VALID,
        disposition=rpki_models.ValidationDisposition.ACCEPTED,
        reason="ok",
    )


def build_validated_roa_payload_instance():
    validation_run = build_validation_run_instance()
    roa = create_unique_roa("validated-roa", signed_by=create_unique_certificate("validated-roa-certificate"))
    return create_test_validated_roa_payload(
        name=f"Validated ROA Payload {unique_token('validated-roa')}",
        validation_run=validation_run,
        roa=roa,
        prefix=create_unique_prefix(),
        origin_as=create_unique_asn(),
        max_length=24,
    )


def build_validated_aspa_payload_instance():
    validation_run = build_validation_run_instance()
    aspa = build_aspa_instance()
    return create_test_validated_aspa_payload(
        name=f"Validated ASPA Payload {unique_token('validated-aspa')}",
        validation_run=validation_run,
        aspa=aspa,
        customer_as=create_unique_asn(),
        provider_as=create_unique_asn(),
    )


def build_revoked_certificate_instance():
    revocation_list = build_certificate_revocation_list_instance()
    certificate = create_unique_certificate("revoked-certificate", rpki_org=create_unique_organization("revoked-org"))
    ee_certificate = create_test_end_entity_certificate(
        name=f"End Entity Certificate {unique_token('revoked-ee')}",
        organization=create_unique_organization("revoked-ee-org"),
        resource_certificate=certificate,
        publication_point=create_publication_point_instance_for_section9(create_unique_organization("revoked-pp-org")),
    )
    return create_test_revoked_certificate(
        revocation_list=revocation_list,
        certificate=certificate,
        ee_certificate=ee_certificate,
        serial="revoked-serial",
        revocation_reason="superseded",
    )


def build_manifest_entry_instance():
    manifest = build_manifest_instance()
    signed_object = build_signed_object_instance()
    certificate = create_unique_certificate("manifest-entry-certificate", rpki_org=create_unique_organization("manifest-entry-org"))
    ee_certificate = create_test_end_entity_certificate(
        name=f"End Entity Certificate {unique_token('manifest-entry-ee')}",
        organization=create_unique_organization("manifest-entry-ee-org"),
        resource_certificate=certificate,
        publication_point=create_publication_point_instance_for_section9(create_unique_organization("manifest-entry-pp-org")),
    )
    return create_test_manifest_entry(
        manifest=manifest,
        signed_object=signed_object,
        certificate=certificate,
        ee_certificate=ee_certificate,
        revocation_list=build_certificate_revocation_list_instance(),
        filename="manifest-entry.cer",
        hash_algorithm="sha256",
        hash_value="hash",
    )


def build_aspa_provider_instance():
    aspa = build_aspa_instance()
    return create_test_aspa_provider(aspa=aspa, provider_as=create_unique_asn())


def build_rsc_file_hash_instance():
    rsc = build_rsc_instance()
    return create_test_rsc_file_hash(
        rsc=rsc,
        filename="artifact.json",
        hash_algorithm="sha256",
        hash_value="hash",
        artifact_reference="artifact",
    )


SECTION_9_MODEL_SCENARIOS = (
    ModelScenario("Repository", build_repository_instance),
    ModelScenario("PublicationPoint", build_publication_point_instance),
    ModelScenario("TrustAnchor", build_trust_anchor_instance),
    ModelScenario("TrustAnchorLocator", build_trust_anchor_locator_instance),
    ModelScenario("EndEntityCertificate", build_end_entity_certificate_instance),
    ModelScenario("SignedObject", build_signed_object_instance),
    ModelScenario("CertificateRevocationList", build_certificate_revocation_list_instance),
    ModelScenario("Manifest", build_manifest_instance),
    ModelScenario("TrustAnchorKey", build_trust_anchor_key_instance),
    ModelScenario("ASPA", build_aspa_instance),
    ModelScenario("RSC", build_rsc_instance),
    ModelScenario("RouterCertificate", build_router_certificate_instance),
    ModelScenario("ValidatorInstance", build_validator_instance),
    ModelScenario("ValidationRun", build_validation_run_instance),
    ModelScenario("ObjectValidationResult", build_object_validation_result_instance),
    ModelScenario("ValidatedRoaPayload", build_validated_roa_payload_instance),
    ModelScenario("ValidatedAspaPayload", build_validated_aspa_payload_instance),
)

SECTION_9_SUPPORT_MODEL_SCENARIOS = (
    ModelScenario("RevokedCertificate", build_revoked_certificate_instance),
    ModelScenario("ManifestEntry", build_manifest_entry_instance),
    ModelScenario("ASPAProvider", build_aspa_provider_instance),
    ModelScenario("RSCFileHash", build_rsc_file_hash_instance),
)
