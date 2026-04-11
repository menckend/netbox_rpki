from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import count

from netbox_rpki.tests.utils import (
    create_test_asn,
    create_test_certificate,
    create_test_certificate_asn,
    create_test_certificate_prefix,
    create_test_organization,
    create_test_prefix,
    create_test_rir,
    create_test_roa,
    create_test_roa_prefix,
)


EXPECTED_FORM_CLASS_NAMES = (
    "CertificateForm",
    "OrganizationForm",
    "RoaForm",
    "RoaPrefixForm",
    "CertificatePrefixForm",
    "CertificateAsnForm",
)

EXPECTED_FILTER_FORM_CLASS_NAMES = (
    "CertificateFilterForm",
    "OrganizationFilterForm",
    "RoaFilterForm",
    "RoaPrefixFilterForm",
    "CertificatePrefixFilterForm",
    "CertificateAsnFilterForm",
)

EXPECTED_FILTERSET_CLASS_NAMES = (
    "CertificateFilterSet",
    "OrganizationFilterSet",
    "RoaFilterSet",
    "RoaPrefixFilterSet",
    "CertificatePrefixFilterSet",
    "CertificateAsnFilterSet",
)

EXPECTED_TABLE_CLASS_NAMES = (
    "CertificateTable",
    "OrganizationTable",
    "RoaTable",
    "RoaPrefixTable",
    "CertificatePrefixTable",
    "CertificateAsnTable",
)

EXPECTED_ROUTE_PATHS = {
    "certificate": {
        "list": "/plugins/netbox_rpki/certificate/",
        "add": "/plugins/netbox_rpki/certificate/add/",
        "detail": "/plugins/netbox_rpki/certificate/1/",
        "edit": "/plugins/netbox_rpki/certificate/1/edit/",
        "delete": "/plugins/netbox_rpki/certificate/1/delete/",
        "include": "certificate/<int:pk>/",
    },
    "organization": {
        "list": "/plugins/netbox_rpki/orgs/",
        "add": "/plugins/netbox_rpki/orgs/add/",
        "detail": "/plugins/netbox_rpki/orgs/1/",
        "edit": "/plugins/netbox_rpki/orgs/1/edit/",
        "delete": "/plugins/netbox_rpki/orgs/1/delete/",
        "include": "orgs/<int:pk>/",
    },
    "roa": {
        "list": "/plugins/netbox_rpki/roa/",
        "add": "/plugins/netbox_rpki/roa/add/",
        "detail": "/plugins/netbox_rpki/roa/1/",
        "edit": "/plugins/netbox_rpki/roa/1/edit/",
        "delete": "/plugins/netbox_rpki/roa/1/delete/",
        "include": "roa/<int:pk>/",
    },
    "roaprefix": {
        "list": "/plugins/netbox_rpki/roaprefixes/",
        "add": "/plugins/netbox_rpki/roaprefixes/add/",
        "detail": "/plugins/netbox_rpki/roaprefixes/1/",
        "edit": "/plugins/netbox_rpki/roaprefixes/1/edit/",
        "delete": "/plugins/netbox_rpki/roaprefixes/1/delete/",
        "include": "roaprefixes/<int:pk>/",
    },
    "certificateprefix": {
        "list": "/plugins/netbox_rpki/certificateprefixes/",
        "add": "/plugins/netbox_rpki/certificateprefixes/add/",
        "detail": "/plugins/netbox_rpki/certificateprefixes/1/",
        "edit": "/plugins/netbox_rpki/certificateprefixes/1/edit/",
        "delete": "/plugins/netbox_rpki/certificateprefixes/1/delete/",
        "include": "certificateprefixes/<int:pk>/",
    },
    "certificateasn": {
        "list": "/plugins/netbox_rpki/certificateasns/",
        "add": "/plugins/netbox_rpki/certificateasns/add/",
        "detail": "/plugins/netbox_rpki/certificateasns/1/",
        "edit": "/plugins/netbox_rpki/certificateasns/1/edit/",
        "delete": "/plugins/netbox_rpki/certificateasns/1/delete/",
        "include": "certificateasns/<int:pk>/",
    },
}

EXPECTED_MODEL_CHILD_INCLUDE_ROUTES = tuple(
    path_config["include"]
    for path_config in EXPECTED_ROUTE_PATHS.values()
)

EXPECTED_NAVIGATION_GROUPS = (
    ("Resources", ("organization", "certificate")),
    ("ROAs", ("roa",)),
)

EXPECTED_NAVIGATION_LINKS = {
    "Resources": (
        ("RIR Customer Orgs", "plugins:netbox_rpki:organization_list"),
        ("Resource Certificates", "plugins:netbox_rpki:certificate_list"),
    ),
    "ROAs": (
        ("ROAs", "plugins:netbox_rpki:roa_list"),
    ),
}

EXPECTED_GRAPHQL_FIELD_NAMES_BY_KEY = {
    "certificate": ("netbox_rpki_certificate", "netbox_rpki_certificate_list"),
    "organization": ("netbox_rpki_organization", "netbox_rpki_organization_list"),
    "roa": ("netbox_rpki_roa", "netbox_rpki_roa_list"),
    "roaprefix": ("netbox_rpki_roa_prefix", "netbox_rpki_roa_prefix_list"),
    "certificateprefix": ("netbox_rpki_certificate_prefix", "netbox_rpki_certificate_prefix_list"),
    "certificateasn": ("netbox_rpki_certificate_asn", "netbox_rpki_certificate_asn_list"),
}

EXPECTED_GRAPHQL_FIELD_ORDER = tuple(
    field_name
    for field_names in EXPECTED_GRAPHQL_FIELD_NAMES_BY_KEY.values()
    for field_name in field_names
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


FORM_SCENARIOS = (
    FormScenario(
        object_key="organization",
        required_fields=("org_id", "name"),
        build_valid_data=build_organization_form_data,
    ),
    FormScenario(
        object_key="certificate",
        required_fields=("name", "rpki_org"),
        build_valid_data=build_certificate_form_data,
    ),
    FormScenario(
        object_key="roa",
        required_fields=("name", "signed_by"),
        build_valid_data=build_roa_form_data,
    ),
    FormScenario(
        object_key="roaprefix",
        required_fields=("prefix", "max_length", "roa_name"),
        build_valid_data=build_roa_prefix_form_data,
    ),
    FormScenario(
        object_key="certificateprefix",
        required_fields=("prefix", "certificate_name"),
        build_valid_data=build_certificate_prefix_form_data,
    ),
    FormScenario(
        object_key="certificateasn",
        required_fields=("asn", "certificate_name2"),
        build_valid_data=build_certificate_asn_form_data,
    ),
)


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


FILTERSET_SCENARIOS = (
    FilterSetScenario(object_key="organization", build_filter_cases=build_organization_filter_cases),
    FilterSetScenario(object_key="certificate", build_filter_cases=build_certificate_filter_cases),
    FilterSetScenario(object_key="roa", build_filter_cases=build_roa_filter_cases),
    FilterSetScenario(object_key="roaprefix", build_filter_cases=build_roa_prefix_filter_cases),
    FilterSetScenario(object_key="certificateprefix", build_filter_cases=build_certificate_prefix_filter_cases),
    FilterSetScenario(object_key="certificateasn", build_filter_cases=build_certificate_asn_filter_cases),
)


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


TABLE_SCENARIOS = (
    TableScenario(object_key="organization", build_rows=build_organization_table_rows),
    TableScenario(object_key="certificate", build_rows=build_certificate_table_rows),
    TableScenario(object_key="roa", build_rows=build_roa_table_rows),
    TableScenario(object_key="roaprefix", build_rows=build_roa_prefix_table_rows),
    TableScenario(object_key="certificateprefix", build_rows=build_certificate_prefix_table_rows),
    TableScenario(object_key="certificateasn", build_rows=build_certificate_asn_table_rows),
)