from netbox_rpki import models

from .object_specs import (
    ApiSpec,
    FilterSetSpec,
    FilterFormSpec,
    FormSpec,
    GraphQLFilterFieldSpec,
    GraphQLFilterSpec,
    GraphQLSpec,
    GraphQLTypeSpec,
    LabelSpec,
    NavigationSpec,
    ObjectSpec,
    RouteSpec,
    TableSpec,
    ViewSpec,
)


OBJECT_SPECS = (
    ObjectSpec(
        key="certificate",
        model=models.Certificate,
        labels=LabelSpec(singular="Certificate", plural="Certificates"),
        routes=RouteSpec(slug="certificate"),
        api=ApiSpec(
            serializer_name="CertificateSerializer",
            viewset_name="CertificateViewSet",
            basename="certificate",
            fields=(
                "id",
                "url",
                "name",
                "issuer",
                "subject",
                "serial",
                "valid_from",
                "valid_to",
                "auto_renews",
                "public_key",
                "private_key",
                "publication_url",
                "ca_repository",
                "self_hosted",
                "rpki_org",
            ),
            brief_fields=("name", "issuer", "subject", "serial", "rpki_org"),
        ),
        filterset=FilterSetSpec(
            class_name="CertificateFilterSet",
            fields=(
                "name",
                "issuer",
                "subject",
                "serial",
                "valid_from",
                "valid_to",
                "public_key",
                "private_key",
                "publication_url",
                "ca_repository",
                "rpki_org",
                "self_hosted",
                "tenant",
            ),
            search_fields=(
                "name__icontains",
                "issuer__icontains",
                "subject__icontains",
                "serial__icontains",
                "comments__icontains",
            ),
        ),
        graphql=GraphQLSpec(
            filter=GraphQLFilterSpec(
                class_name="CertificateFilter",
                fields=(
                    GraphQLFilterFieldSpec(field_name="name", filter_kind="str"),
                    GraphQLFilterFieldSpec(field_name="issuer", filter_kind="str"),
                    GraphQLFilterFieldSpec(field_name="subject", filter_kind="str"),
                    GraphQLFilterFieldSpec(field_name="serial", filter_kind="str"),
                    GraphQLFilterFieldSpec(field_name="auto_renews", filter_kind="bool"),
                    GraphQLFilterFieldSpec(field_name="self_hosted", filter_kind="bool"),
                    GraphQLFilterFieldSpec(field_name="rpki_org_id", filter_kind="id"),
                ),
            ),
            type=GraphQLTypeSpec(class_name="CertificateType"),
            detail_field_name="netbox_rpki_certificate",
            list_field_name="netbox_rpki_certificate_list",
        ),
        form=FormSpec(
            class_name="CertificateForm",
            fields=(
                "name",
                "issuer",
                "subject",
                "serial",
                "valid_from",
                "valid_to",
                "auto_renews",
                "public_key",
                "private_key",
                "publication_url",
                "ca_repository",
                "rpki_org",
                "self_hosted",
                "tenant",
                "comments",
                "tags",
            ),
        ),
        filter_form=FilterFormSpec(class_name="CertificateFilterForm"),
        table=TableSpec(
            class_name="CertificateTable",
            fields=(
                "pk",
                "id",
                "name",
                "issuer",
                "subject",
                "serial",
                "valid_from",
                "valid_to",
                "auto_renews",
                "public_key",
                "private_key",
                "publication_url",
                "ca_repository",
                "self_hosted",
                "rpki_org",
                "comments",
                "tenant",
                "tags",
            ),
            default_columns=(
                "name",
                "valid_from",
                "valid_to",
                "auto_renews",
                "self_hosted",
                "rpki_org",
                "comments",
                "tenant",
                "tags",
            ),
            linkify_field="name",
        ),
        view=ViewSpec(
            list_class_name="CertificateListView",
            detail_class_name="CertificateView",
            edit_class_name="CertificateEditView",
            delete_class_name="CertificateDeleteView",
        ),
        navigation=NavigationSpec(
            group="Resources",
            label="Resource Certificates",
            order=20,
        ),
    ),
    ObjectSpec(
        key="organization",
        model=models.Organization,
        labels=LabelSpec(singular="Organization", plural="Organizations"),
        routes=RouteSpec(slug="organization"),
        api=ApiSpec(
            serializer_name="OrganizationSerializer",
            viewset_name="OrganizationViewSet",
            basename="organization",
            fields=("id", "url", "org_id", "name", "ext_url", "parent_rir"),
            brief_fields=("org_id", "name", "parent_rir"),
        ),
        filterset=FilterSetSpec(
            class_name="OrganizationFilterSet",
            fields=("org_id", "name", "parent_rir", "ext_url", "tenant"),
            search_fields=(
                "org_id__icontains",
                "name__icontains",
                "ext_url__icontains",
                "comments__icontains",
            ),
        ),
        graphql=GraphQLSpec(
            filter=GraphQLFilterSpec(
                class_name="OrganizationFilter",
                fields=(
                    GraphQLFilterFieldSpec(field_name="org_id", filter_kind="str"),
                    GraphQLFilterFieldSpec(field_name="name", filter_kind="str"),
                    GraphQLFilterFieldSpec(field_name="ext_url", filter_kind="str"),
                    GraphQLFilterFieldSpec(field_name="parent_rir_id", filter_kind="id"),
                ),
            ),
            type=GraphQLTypeSpec(class_name="OrganizationType"),
            detail_field_name="netbox_rpki_organization",
            list_field_name="netbox_rpki_organization_list",
        ),
        form=FormSpec(
            class_name="OrganizationForm",
            fields=("org_id", "name", "parent_rir", "ext_url", "tenant", "comments", "tags"),
        ),
        filter_form=FilterFormSpec(class_name="OrganizationFilterForm"),
        table=TableSpec(
            class_name="OrganizationTable",
            fields=("pk", "id", "org_id", "name", "parent_rir", "ext_url", "comments", "tenant", "tags"),
            default_columns=("org_id", "name", "parent_rir", "ext_url", "comments", "tenant", "tags"),
            linkify_field="name",
        ),
        view=ViewSpec(
            list_class_name="OrganizationListView",
            detail_class_name="OrganizationView",
            edit_class_name="OrganizationEditView",
            delete_class_name="OrganizationDeleteView",
        ),
        navigation=NavigationSpec(
            group="Resources",
            label="RIR Customer Orgs",
            order=10,
        ),
    ),
    ObjectSpec(
        key="roa",
        model=models.Roa,
        labels=LabelSpec(singular="ROA", plural="ROAs"),
        routes=RouteSpec(slug="roa"),
        api=ApiSpec(
            serializer_name="RoaSerializer",
            viewset_name="RoaViewSet",
            basename="roa",
            fields=(
                "id",
                "url",
                "name",
                "origin_as",
                "valid_from",
                "valid_to",
                "auto_renews",
                "signed_by",
            ),
            brief_fields=("name", "origin_as"),
        ),
        filterset=FilterSetSpec(
            class_name="RoaFilterSet",
            fields=("name", "origin_as", "valid_from", "valid_to", "signed_by", "tenant"),
            search_fields=("name__icontains", "comments__icontains"),
        ),
        graphql=GraphQLSpec(
            filter=GraphQLFilterSpec(
                class_name="RoaFilter",
                fields=(
                    GraphQLFilterFieldSpec(field_name="name", filter_kind="str"),
                    GraphQLFilterFieldSpec(field_name="auto_renews", filter_kind="bool"),
                    GraphQLFilterFieldSpec(field_name="origin_as_id", filter_kind="id"),
                    GraphQLFilterFieldSpec(field_name="signed_by_id", filter_kind="id"),
                ),
            ),
            type=GraphQLTypeSpec(class_name="RoaType"),
            detail_field_name="netbox_rpki_roa",
            list_field_name="netbox_rpki_roa_list",
        ),
        form=FormSpec(
            class_name="RoaForm",
            fields=("name", "origin_as", "valid_from", "valid_to", "auto_renews", "signed_by", "tenant", "comments", "tags"),
        ),
        filter_form=FilterFormSpec(class_name="RoaFilterForm"),
        table=TableSpec(
            class_name="RoaTable",
            fields=("pk", "id", "name", "origin_as", "valid_from", "valid_to", "auto_renews", "signed_by", "comments", "tenant", "tags"),
            default_columns=("name", "origin_as", "valid_from", "valid_to", "auto_renews", "comments", "tenant", "tags"),
            linkify_field="name",
        ),
        view=ViewSpec(
            list_class_name="RoaListView",
            detail_class_name="RoaView",
            edit_class_name="RoaEditView",
            delete_class_name="RoaDeleteView",
        ),
        navigation=NavigationSpec(
            group="ROAs",
            label="ROAs",
            order=10,
        ),
    ),
    ObjectSpec(
        key="roaprefix",
        model=models.RoaPrefix,
        labels=LabelSpec(singular="ROA Prefix", plural="ROA Prefixes"),
        routes=RouteSpec(slug="roaprefix"),
        api=ApiSpec(
            serializer_name="RoaPrefixSerializer",
            viewset_name="RoaPrefixViewSet",
            basename="roaprefix",
            fields=("id", "url", "prefix", "max_length", "roa_name"),
            brief_fields=("id", "prefix", "max_length", "roa_name"),
        ),
        filterset=FilterSetSpec(
            class_name="RoaPrefixFilterSet",
            fields=("prefix", "max_length", "roa_name", "tenant"),
            search_fields=("prefix__prefix__icontains", "comments__icontains"),
        ),
        graphql=GraphQLSpec(
            filter=GraphQLFilterSpec(
                class_name="RoaPrefixFilter",
                fields=(
                    GraphQLFilterFieldSpec(field_name="prefix_id", filter_kind="id"),
                    GraphQLFilterFieldSpec(field_name="roa_name_id", filter_kind="id"),
                ),
            ),
            type=GraphQLTypeSpec(class_name="RoaPrefixType"),
            detail_field_name="netbox_rpki_roa_prefix",
            list_field_name="netbox_rpki_roa_prefix_list",
        ),
        form=FormSpec(
            class_name="RoaPrefixForm",
            fields=("prefix", "max_length", "roa_name", "tenant", "comments", "tags"),
        ),
        filter_form=FilterFormSpec(class_name="RoaPrefixFilterForm"),
        table=TableSpec(
            class_name="RoaPrefixTable",
            fields=("pk", "id", "prefix", "max_length", "roa_name", "comments", "tenant", "tags"),
            default_columns=("prefix", "max_length", "roa_name", "comments", "tenant", "tags"),
            linkify_field="pk",
        ),
        view=ViewSpec(
            list_class_name="RoaPrefixListView",
            detail_class_name="RoaPrefixView",
            edit_class_name="RoaPrefixEditView",
            delete_class_name="RoaPrefixDeleteView",
            simple_detail=True,
        ),
    ),
    ObjectSpec(
        key="certificateprefix",
        model=models.CertificatePrefix,
        labels=LabelSpec(singular="Certificate Prefix", plural="Certificate Prefixes"),
        routes=RouteSpec(slug="certificateprefix"),
        api=ApiSpec(
            serializer_name="CertificatePrefixSerializer",
            viewset_name="CertificatePrefixViewSet",
            basename="certificateprefix",
            fields=("id", "url", "prefix", "certificate_name"),
            brief_fields=("id", "prefix", "certificate_name"),
        ),
        filterset=FilterSetSpec(
            class_name="CertificatePrefixFilterSet",
            fields=("prefix", "certificate_name", "tenant"),
            search_fields=("prefix__prefix__icontains", "comments__icontains"),
        ),
        graphql=GraphQLSpec(
            filter=GraphQLFilterSpec(
                class_name="CertificatePrefixFilter",
                fields=(
                    GraphQLFilterFieldSpec(field_name="prefix_id", filter_kind="id"),
                    GraphQLFilterFieldSpec(field_name="certificate_name_id", filter_kind="id"),
                ),
            ),
            type=GraphQLTypeSpec(class_name="CertificatePrefixType"),
            detail_field_name="netbox_rpki_certificate_prefix",
            list_field_name="netbox_rpki_certificate_prefix_list",
        ),
        form=FormSpec(
            class_name="CertificatePrefixForm",
            fields=("prefix", "certificate_name", "tenant", "comments", "tags"),
        ),
        filter_form=FilterFormSpec(class_name="CertificatePrefixFilterForm"),
        table=TableSpec(
            class_name="CertificatePrefixTable",
            fields=("pk", "id", "prefix", "certificate_name", "comments", "tenant", "tags"),
            default_columns=("prefix", "comments", "tenant", "tags"),
            linkify_field="pk",
        ),
        view=ViewSpec(
            list_class_name="CertificatePrefixListView",
            detail_class_name="CertificatePrefixView",
            edit_class_name="CertificatePrefixEditView",
            delete_class_name="CertificatePrefixDeleteView",
            simple_detail=True,
        ),
    ),
    ObjectSpec(
        key="certificateasn",
        model=models.CertificateAsn,
        labels=LabelSpec(singular="Certificate ASN", plural="Certificate ASNs"),
        routes=RouteSpec(slug="certificateasn"),
        api=ApiSpec(
            serializer_name="CertificateAsnSerializer",
            viewset_name="CertificateAsnViewSet",
            basename="certificateasn",
            fields=("id", "url", "asn", "certificate_name2"),
            brief_fields=("id", "asn", "certificate_name2"),
        ),
        filterset=FilterSetSpec(
            class_name="CertificateAsnFilterSet",
            fields=("asn", "certificate_name2", "tenant"),
            search_fields=("certificate_name2__name__icontains", "comments__icontains"),
        ),
        graphql=GraphQLSpec(
            filter=GraphQLFilterSpec(
                class_name="CertificateAsnFilter",
                fields=(
                    GraphQLFilterFieldSpec(field_name="asn_id", filter_kind="id"),
                    GraphQLFilterFieldSpec(field_name="certificate_name2_id", filter_kind="id"),
                ),
            ),
            type=GraphQLTypeSpec(class_name="CertificateAsnType"),
            detail_field_name="netbox_rpki_certificate_asn",
            list_field_name="netbox_rpki_certificate_asn_list",
        ),
        form=FormSpec(
            class_name="CertificateAsnForm",
            fields=("asn", "certificate_name2", "tenant", "comments", "tags"),
        ),
        filter_form=FilterFormSpec(class_name="CertificateAsnFilterForm"),
        table=TableSpec(
            class_name="CertificateAsnTable",
            fields=("pk", "id", "asn", "certificate_name2", "comments", "tenant", "tags"),
            default_columns=("asn", "comments", "tenant", "tags"),
            linkify_field="pk",
        ),
        view=ViewSpec(
            list_class_name="CertificateAsnListView",
            detail_class_name="CertificateAsnView",
            edit_class_name="CertificateAsnEditView",
            delete_class_name="CertificateAsnDeleteView",
            simple_detail=True,
        ),
    ),
)

API_OBJECT_SPECS = OBJECT_SPECS
GRAPHQL_OBJECT_SPECS = tuple(spec for spec in OBJECT_SPECS if spec.graphql is not None)
FILTERSET_OBJECT_SPECS = tuple(spec for spec in OBJECT_SPECS if spec.filterset is not None)
FORM_OBJECT_SPECS = tuple(spec for spec in OBJECT_SPECS if spec.form is not None)
FILTER_FORM_OBJECT_SPECS = tuple(spec for spec in OBJECT_SPECS if spec.filter_form is not None)
TABLE_OBJECT_SPECS = tuple(spec for spec in OBJECT_SPECS if spec.table is not None)
VIEW_OBJECT_SPECS = tuple(spec for spec in OBJECT_SPECS if spec.view is not None)
SIMPLE_DETAIL_VIEW_OBJECT_SPECS = tuple(spec for spec in VIEW_OBJECT_SPECS if spec.view.simple_detail)
OBJECT_SPEC_BY_KEY = {spec.key: spec for spec in OBJECT_SPECS}
MENU_GROUP_ORDER = ("Resources", "ROAs")


def get_object_spec(key: str) -> ObjectSpec:
    return OBJECT_SPEC_BY_KEY[key]


def get_navigation_groups() -> tuple[tuple[str, tuple[ObjectSpec, ...]], ...]:
    groups = []
    for group_name in MENU_GROUP_ORDER:
        group_specs = tuple(
            sorted(
                (
                    spec
                    for spec in OBJECT_SPECS
                    if spec.has_menu_item and spec.navigation.group == group_name
                ),
                key=lambda spec: spec.navigation.order,
            )
        )
        if group_specs:
            groups.append((group_name, group_specs))

    return tuple(groups)