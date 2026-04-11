# netbox_rpki Test Suite Plan

This document turns the test-suite goal into a concrete implementation plan with exact module paths, test class names, and named test cases.

The target is a rigorous suite that covers every exposed plugin surface:

- Web UI routes and forms
- Detail templates and related-object tables
- Navigation/menu entry points
- Filtersets and list views
- REST API list/detail/create/update/delete behavior
- GraphQL query and filter behavior
- Browser clickthrough for real user flows

The expectation for each create or update surface is explicit coverage for:

- valid input
- invalid input
- empty input

## Surface Inventory

The current plugin exposes the following surfaces:

### Models

- `Organization`
- `Certificate`
- `Roa`
- `RoaPrefix`
- `CertificatePrefix`
- `CertificateAsn`

### Web UI Routes

Defined in `netbox_rpki/urls.py`.

- `certificate_list`, `certificate_add`, `certificate`, `certificate_edit`, `certificate_delete`
- `organization_list`, `organization_add`, `organization`, `organization_edit`, `organization_delete`
- `roa_list`, `roa_add`, `roa`, `roa_edit`, `roa_delete`
- `roaprefix_list`, `roaprefix_add`, `roaprefix`, `roaprefix_edit`, `roaprefix_delete`
- `certificateprefix_list`, `certificateprefix_add`, `certificateprefix`, `certificateprefix_edit`, `certificateprefix_delete`
- `certificateasn_list`, `certificateasn_add`, `certificateasn`, `certificateasn_edit`, `certificateasn_delete`

Each detail route also exposes NetBox model child URLs through `get_model_urls(...)` and needs smoke coverage.

### Navigation

Defined in `netbox_rpki/navigation.py`.

- visible top-level menu items:
  - `RIR Customer Orgs`
  - `Resource Certificates`
  - `ROAs`
- visible add buttons:
  - `organization_add`
  - `certificate_add`
  - `roa_add`
- hidden but real pages:
  - `certificateprefixes`
  - `certificateasns`
  - `roaprefixes`

### REST API

Defined in `netbox_rpki/api/urls.py` and `netbox_rpki/api/views.py`.

- API root
- `certificate`
- `organization`
- `roa`
- `roaprefix`
- `certificateprefix`
- `certificateasn`

Each resource must have list, detail, create, update, partial update, delete, and filter coverage.

### GraphQL

Defined in `netbox_rpki/graphql/schema.py`.

- singular queries:
  - `netbox_rpki_certificate`
  - `netbox_rpki_certificate_asn`
  - `netbox_rpki_certificate_prefix`
  - `netbox_rpki_organization`
  - `netbox_rpki_roa`
  - `netbox_rpki_roa_prefix`
- list queries:
  - `netbox_rpki_certificate_list`
  - `netbox_rpki_certificate_asn_list`
  - `netbox_rpki_certificate_prefix_list`
  - `netbox_rpki_organization_list`
  - `netbox_rpki_roa_list`
  - `netbox_rpki_roa_prefix_list`

Each list query must be tested with no filters, valid filters, invalid filters, and empty-result filters.

### Templates

Custom detail templates exist for:

- `organization.html`
- `certificate.html`
- `roa.html`
- `roaprefix.html`
- `certificateprefix.html`
- `certificateasn.html`

## Fixture and Helper Architecture

Do not start by adding browser tests. Land shared deterministic object builders first.

### New Shared Modules

- `netbox_rpki/tests/factories/ipam.py`
- `netbox_rpki/tests/factories/rpki.py`
- `netbox_rpki/tests/factories/scenarios.py`
- `netbox_rpki/tests/helpers/payloads.py`
- `netbox_rpki/tests/mixins.py`

### Proposed Helper API

#### `netbox_rpki/tests/factories/ipam.py`

- `create_test_rir()`
- `create_test_tenant()`
- `create_test_aggregate()`
- `create_test_prefix()`
- `create_test_asn()`

#### `netbox_rpki/tests/factories/rpki.py`

- `create_test_organization()`
- `create_test_certificate()`
- `create_test_roa()`
- `create_test_roa_prefix()`
- `create_test_certificate_prefix()`
- `create_test_certificate_asn()`

#### `netbox_rpki/tests/factories/scenarios.py`

- `create_test_certificate_bundle()`
- `create_test_roa_bundle()`

#### `netbox_rpki/tests/helpers/payloads.py`

- `organization_form_data()`
- `organization_api_payload()`
- `certificate_form_data()`
- `certificate_api_payload()`
- `roa_form_data()`
- `roa_api_payload()`
- `roaprefix_form_data()`
- `roaprefix_api_payload()`
- `certificateprefix_form_data()`
- `certificateprefix_api_payload()`
- `certificateasn_form_data()`
- `certificateasn_api_payload()`

#### `netbox_rpki/tests/mixins.py`

- `SharedIpamFixturesMixin`
- `CertificateBundleMixin`
- `RoaBundleMixin`
- `PluginAPITestCaseMixin`
- `PluginViewTestCaseMixin`

### Required Dependency Graph

- `Organization` requires `org_id`, `name`
- `Certificate` requires `name`, `auto_renews`, `self_hosted`, `rpki_org`
- `Roa` requires `name`, `auto_renews`, `signed_by`
- `RoaPrefix` requires `prefix`, `max_length`, `roa_name`
- `CertificatePrefix` requires `prefix`, `certificate_name`
- `CertificateAsn` requires `asn`, `certificate_name2`

Transitive upstream fixtures:

- `Certificate` depends on `Organization`
- `CertificateAsn` depends on `Certificate` and `ASN`
- `CertificatePrefix` depends on `Certificate` and `Prefix`
- `Roa` depends on `Certificate` and optionally `ASN`
- `RoaPrefix` depends on `Roa` and `Prefix`

Shared baseline objects for most non-trivial test classes:

- 1 `RIR`
- 1 `Tenant`
- 1 `Aggregate`
- 1 `Prefix`
- 1 `ASN`
- 1 `Organization`
- 1 `Certificate`
- 1 `CertificatePrefix`
- 1 `CertificateAsn`
- 1 `Roa`
- 1 `RoaPrefix`

## Python Test Modules

### `netbox_rpki/tests/test_models.py`

#### `OrganizationModelTestCase`

- `test_str_returns_name`
- `test_get_absolute_url_uses_plugin_namespace`
- `test_optional_fields_may_be_blank`
- `test_parent_rir_is_optional`
- `test_tenant_is_optional`

#### `CertificateModelTestCase`

- `test_str_returns_name`
- `test_get_absolute_url_uses_plugin_namespace`
- `test_optional_text_fields_may_be_blank`
- `test_validity_dates_may_be_blank`
- `test_certificate_requires_rpki_org`

#### `RoaModelTestCase`

- `test_str_returns_name`
- `test_get_absolute_url_uses_plugin_namespace`
- `test_origin_as_is_optional`
- `test_validity_dates_may_be_blank`
- `test_roa_requires_signed_by`

#### `AssignmentModelTestCase`

- `test_roaprefix_str_returns_prefix`
- `test_certificateprefix_str_returns_prefix`
- `test_certificateasn_str_returns_asn`
- `test_assignment_models_use_plugin_absolute_urls`
- `test_protect_relationships_block_parent_deletion`

### `netbox_rpki/tests/test_forms.py`

#### `OrganizationFormTestCase`

- `test_organization_form_accepts_minimal_required_fields`
- `test_organization_form_accepts_full_payload`
- `test_organization_form_rejects_missing_org_id`
- `test_organization_form_rejects_missing_name`
- `test_organization_form_rejects_empty_payload`

#### `CertificateFormTestCase`

- `test_certificate_form_accepts_required_fields`
- `test_certificate_form_accepts_full_payload`
- `test_certificate_form_rejects_missing_name`
- `test_certificate_form_rejects_missing_rpki_org`
- `test_certificate_form_rejects_missing_auto_renews`
- `test_certificate_form_rejects_missing_self_hosted`
- `test_certificate_form_rejects_empty_payload`

#### `RoaFormTestCase`

- `test_roa_form_accepts_required_fields`
- `test_roa_form_accepts_full_payload`
- `test_roa_form_rejects_missing_name`
- `test_roa_form_rejects_missing_signed_by`
- `test_roa_form_rejects_missing_auto_renews`
- `test_roa_form_rejects_empty_payload`

#### `AssignedResourceFormTestCase`

- `test_roaprefix_form_accepts_required_fields`
- `test_roaprefix_form_rejects_missing_prefix`
- `test_roaprefix_form_rejects_missing_max_length`
- `test_roaprefix_form_rejects_missing_roa_name`
- `test_roaprefix_form_rejects_empty_payload`
- `test_certificateprefix_form_accepts_required_fields`
- `test_certificateprefix_form_rejects_missing_certificate_name`
- `test_certificateprefix_form_rejects_empty_payload`
- `test_certificateasn_form_accepts_required_fields`
- `test_certificateasn_form_rejects_missing_asn`
- `test_certificateasn_form_rejects_missing_certificate_name2`
- `test_certificateasn_form_rejects_empty_payload`

### `netbox_rpki/tests/test_filtersets.py`

#### `OrganizationFilterSetTestCase`

- `test_q_filters_by_org_id`
- `test_q_filters_by_name`
- `test_q_blank_returns_full_queryset`
- `test_parent_rir_filter_matches_expected_rows`
- `test_tenant_filter_matches_expected_rows`
- `test_invalid_parent_rir_id_returns_empty_queryset`

#### `CertificateFilterSetTestCase`

- `test_q_filters_by_name`
- `test_q_filters_by_issuer`
- `test_q_filters_by_subject`
- `test_q_blank_returns_full_queryset`
- `test_rpki_org_filter_matches_expected_rows`
- `test_self_hosted_filter_matches_expected_rows`
- `test_tenant_filter_matches_expected_rows`

#### `RoaFilterSetTestCase`

- `test_q_filters_by_name`
- `test_q_blank_returns_full_queryset`
- `test_origin_as_filter_matches_expected_rows`
- `test_signed_by_filter_matches_expected_rows`
- `test_tenant_filter_matches_expected_rows`

#### `RoaPrefixFilterSetTestCase`

- `test_q_filters_by_prefix_text`
- `test_q_blank_returns_full_queryset`
- `test_prefix_filter_matches_expected_rows`
- `test_max_length_filter_matches_expected_rows`
- `test_roa_name_filter_matches_expected_rows`
- `test_tenant_filter_matches_expected_rows`

#### `CertificatePrefixFilterSetTestCase`

- `test_q_filters_by_prefix_text`
- `test_q_blank_returns_full_queryset`
- `test_prefix_filter_matches_expected_rows`
- `test_certificate_name_filter_matches_expected_rows`
- `test_tenant_filter_matches_expected_rows`

#### `CertificateAsnFilterSetTestCase`

- `test_q_filters_by_certificate_name`
- `test_q_filters_by_comments`
- `test_q_blank_returns_full_queryset`
- `test_asn_filter_matches_expected_rows`
- `test_certificate_name2_filter_matches_expected_rows`
- `test_tenant_filter_matches_expected_rows`

### `netbox_rpki/tests/test_views.py`

#### `OrganizationViewTestCase`

- `test_organization_list_view_renders`
- `test_organization_add_view_renders`
- `test_organization_detail_view_renders`
- `test_organization_edit_view_renders`
- `test_organization_delete_view_renders`
- `test_create_organization_with_valid_input`
- `test_create_organization_with_invalid_input`
- `test_create_organization_with_empty_input`
- `test_edit_organization_with_valid_input`
- `test_delete_organization_removes_object`
- `test_organization_detail_renders_certificates_table`
- `test_organization_detail_add_certificate_link_prefills_rpki_org`

#### `CertificateViewTestCase`

- `test_certificate_list_view_renders`
- `test_certificate_add_view_renders`
- `test_certificate_detail_view_renders`
- `test_certificate_edit_view_renders`
- `test_certificate_delete_view_renders`
- `test_create_certificate_with_valid_input`
- `test_create_certificate_with_invalid_input`
- `test_create_certificate_with_empty_input`
- `test_edit_certificate_with_valid_input`
- `test_delete_certificate_removes_object_without_children`
- `test_certificate_list_filters_by_q`
- `test_certificate_detail_renders_related_tables`
- `test_certificate_detail_add_prefix_link_prefills_certificate_name`
- `test_certificate_detail_add_asn_link_prefills_certificate_name2`
- `test_certificate_detail_add_roa_link_prefills_signed_by`

#### `RoaViewTestCase`

- `test_roa_list_view_renders`
- `test_roa_add_view_renders`
- `test_roa_detail_view_renders`
- `test_roa_edit_view_renders`
- `test_roa_delete_view_renders`
- `test_create_roa_with_valid_input`
- `test_create_roa_with_invalid_input`
- `test_create_roa_with_empty_input`
- `test_edit_roa_with_valid_input`
- `test_delete_roa_removes_object_without_children`
- `test_roa_detail_renders_roaprefix_table`
- `test_roa_detail_add_roaprefix_link_prefills_roa_name`

#### `RoaPrefixViewTestCase`

- `test_roaprefix_list_view_renders`
- `test_roaprefix_add_view_renders`
- `test_roaprefix_detail_view_renders`
- `test_roaprefix_edit_view_renders`
- `test_roaprefix_delete_view_renders`
- `test_create_roaprefix_with_valid_input`
- `test_create_roaprefix_with_invalid_input`
- `test_create_roaprefix_with_empty_input`
- `test_edit_roaprefix_with_valid_input`
- `test_delete_roaprefix_removes_object`

#### `CertificatePrefixViewTestCase`

- `test_certificateprefix_list_view_renders`
- `test_certificateprefix_add_view_renders`
- `test_certificateprefix_detail_view_renders`
- `test_certificateprefix_edit_view_renders`
- `test_certificateprefix_delete_view_renders`
- `test_create_certificateprefix_with_valid_input`
- `test_create_certificateprefix_with_invalid_input`
- `test_create_certificateprefix_with_empty_input`
- `test_edit_certificateprefix_with_valid_input`
- `test_delete_certificateprefix_removes_object`

#### `CertificateAsnViewTestCase`

- `test_certificateasn_list_view_renders`
- `test_certificateasn_add_view_renders`
- `test_certificateasn_detail_view_renders`
- `test_certificateasn_edit_view_renders`
- `test_certificateasn_delete_view_renders`
- `test_create_certificateasn_with_valid_input`
- `test_create_certificateasn_with_invalid_input`
- `test_create_certificateasn_with_empty_input`
- `test_edit_certificateasn_with_valid_input`
- `test_delete_certificateasn_removes_object`

### `netbox_rpki/tests/test_tables.py`

#### `CertificateTableTestCase`

- `test_certificate_table_default_columns_render`
- `test_certificate_table_name_column_linkifies`
- `test_certificate_table_tenant_column_renders_link`
- `test_certificate_table_tenant_column_renders_dash_when_missing`
- `test_certificate_table_tag_column_uses_certificate_list_url`
- `test_certificate_table_meta_fields_match_model_fields`

#### `RelatedResourceTableTestCase`

- `test_organization_table_name_column_linkifies`
- `test_roa_table_default_columns_include_validity_fields`
- `test_roaprefix_table_pk_column_linkifies`
- `test_certificateprefix_table_pk_column_linkifies`
- `test_certificateasn_table_pk_column_linkifies`
- `test_assignment_tables_render_tenant_dash_when_missing`

### `netbox_rpki/tests/test_templates.py`

#### `OrganizationTemplateTestCase`

- `test_organization_detail_uses_custom_template`
- `test_organization_detail_renders_breadcrumbs`
- `test_organization_detail_renders_certificates_table`
- `test_organization_detail_add_certificate_link_prefills_rpki_org`

#### `CertificateTemplateTestCase`

- `test_certificate_detail_uses_custom_template`
- `test_certificate_detail_renders_assigned_prefixes_table`
- `test_certificate_detail_renders_assigned_asns_table`
- `test_certificate_detail_renders_roas_table`
- `test_certificate_detail_add_prefix_link_prefills_certificate_name`
- `test_certificate_detail_add_asn_link_prefills_certificate_name2`
- `test_certificate_detail_add_roa_link_prefills_signed_by`

#### `RoaTemplateTestCase`

- `test_roa_detail_uses_custom_template`
- `test_roa_detail_renders_roaprefix_table`
- `test_roa_detail_renders_valid_from_and_valid_to`
- `test_roa_detail_add_roaprefix_link_prefills_roa_name`

#### `AssignedResourceTemplateTestCase`

- `test_roaprefix_detail_uses_custom_template`
- `test_certificateprefix_detail_uses_custom_template`
- `test_certificateasn_detail_uses_custom_template`
- `test_assignment_detail_renders_related_object_links`

### `netbox_rpki/tests/test_navigation.py`

#### `NavigationConfigTestCase`

- `test_top_level_menu_builds_rpki_menu`
- `test_resources_group_contains_organization_and_certificate_items`
- `test_roas_group_contains_roa_item`
- `test_menu_buttons_target_plugin_add_routes`
- `test_hidden_assignment_items_remain_absent_from_visible_menu`
- `test_flat_menu_items_mode_exports_expected_items_when_top_level_menu_false`

### `netbox_rpki/tests/test_api.py`

Keep the existing smoke tests and expand them.

#### `AppTest`

- `test_root`
- `test_root_includes_certificate_endpoint`
- `test_root_includes_organization_endpoint`
- `test_root_includes_roa_endpoint`
- `test_root_includes_roaprefix_endpoint`
- `test_root_includes_certificateprefix_endpoint`
- `test_root_includes_certificateasn_endpoint`

#### `SerializerSmokeTestCase`

- `test_serializer_urls_use_plugin_namespace`
- `test_certificate_serializer_fields_contract`
- `test_organization_serializer_fields_contract`
- `test_roa_serializer_fields_contract`
- `test_assignment_serializer_fields_contract`

#### `ViewSetSmokeTestCase`

- `test_viewsets_define_querysets`
- `test_viewsets_define_filterset_class`
- `test_root_view_name_is_rpki`

#### `OrganizationAPITestCase`

- `test_get_organization`
- `test_list_organizations`
- `test_create_organization_with_valid_input`
- `test_create_organization_with_invalid_input`
- `test_create_organization_with_empty_input`
- `test_update_organization_with_valid_input`
- `test_patch_organization_with_valid_input`
- `test_delete_organization`
- `test_filter_organizations_by_name`
- `test_filter_organizations_by_parent_rir`
- `test_filter_organizations_by_tenant`

#### `CertificateAPITestCase`

- `test_get_certificate`
- `test_list_certificates`
- `test_create_certificate_with_valid_input`
- `test_create_certificate_with_invalid_input`
- `test_create_certificate_with_empty_input`
- `test_update_certificate_with_valid_input`
- `test_patch_certificate_with_valid_input`
- `test_delete_certificate`
- `test_filter_certificates_by_issuer`
- `test_filter_certificates_by_rpki_org`
- `test_filter_certificates_by_self_hosted`
- `test_filter_certificates_by_tenant`

#### `RoaAPITestCase`

- `test_get_roa`
- `test_list_roas`
- `test_create_roa_with_valid_input`
- `test_create_roa_with_invalid_input`
- `test_create_roa_with_empty_input`
- `test_update_roa_with_valid_input`
- `test_patch_roa_with_valid_input`
- `test_delete_roa`
- `test_filter_roas_by_name`
- `test_filter_roas_by_origin_as`
- `test_filter_roas_by_signed_by`
- `test_filter_roas_by_tenant`

#### `RoaPrefixAPITestCase`

- `test_get_roaprefix`
- `test_list_roaprefixes`
- `test_create_roaprefix_with_valid_input`
- `test_create_roaprefix_with_invalid_input`
- `test_create_roaprefix_with_empty_input`
- `test_update_roaprefix_with_valid_input`
- `test_patch_roaprefix_with_valid_input`
- `test_delete_roaprefix`
- `test_filter_roaprefixes_by_prefix`
- `test_filter_roaprefixes_by_max_length`
- `test_filter_roaprefixes_by_roa_name`
- `test_filter_roaprefixes_by_tenant`

#### `CertificatePrefixAPITestCase`

- `test_get_certificateprefix`
- `test_list_certificateprefixes`
- `test_create_certificateprefix_with_valid_input`
- `test_create_certificateprefix_with_invalid_input`
- `test_create_certificateprefix_with_empty_input`
- `test_update_certificateprefix_with_valid_input`
- `test_patch_certificateprefix_with_valid_input`
- `test_delete_certificateprefix`
- `test_filter_certificateprefixes_by_prefix`
- `test_filter_certificateprefixes_by_certificate_name`
- `test_filter_certificateprefixes_by_tenant`

#### `CertificateAsnAPITestCase`

- `test_get_certificateasn`
- `test_list_certificateasns`
- `test_create_certificateasn_with_valid_input`
- `test_create_certificateasn_with_invalid_input`
- `test_create_certificateasn_with_empty_input`
- `test_update_certificateasn_with_valid_input`
- `test_patch_certificateasn_with_valid_input`
- `test_delete_certificateasn`
- `test_filter_certificateasns_by_asn`
- `test_filter_certificateasns_by_certificate_name2`
- `test_filter_certificateasns_by_tenant`

### `netbox_rpki/tests/test_graphql.py`

#### `GraphQLSchemaRegistrationTestCase`

- `test_query_exposes_all_single_object_fields`
- `test_query_exposes_all_list_fields`
- `test_graphql_types_bind_expected_filter_classes`

#### `OrganizationGraphQLTestCase`

- `test_get_organization_by_id`
- `test_get_organization_with_invalid_id_returns_null_or_error`
- `test_list_organizations_without_filters`
- `test_filter_organizations_by_org_id_icontains`
- `test_filter_organizations_by_name_icontains`
- `test_filter_organizations_by_ext_url_icontains`
- `test_filter_organizations_by_parent_rir_id`
- `test_filter_organizations_with_invalid_parent_rir_id_returns_empty_list`

#### `CertificateGraphQLTestCase`

- `test_get_certificate_by_id`
- `test_get_certificate_with_invalid_id_returns_null_or_error`
- `test_list_certificates_without_filters`
- `test_filter_certificates_by_name_icontains`
- `test_filter_certificates_by_issuer_icontains`
- `test_filter_certificates_by_auto_renews`
- `test_filter_certificates_by_self_hosted`
- `test_filter_certificates_by_rpki_org_id`
- `test_filter_certificates_with_invalid_rpki_org_id_returns_empty_list`

#### `RoaGraphQLTestCase`

- `test_get_roa_by_id`
- `test_get_roa_with_invalid_id_returns_null_or_error`
- `test_list_roas_without_filters`
- `test_filter_roas_by_name_icontains`
- `test_filter_roas_by_auto_renews`
- `test_filter_roas_by_origin_as_id`
- `test_filter_roas_by_signed_by_id`
- `test_filter_roas_with_invalid_signed_by_id_returns_empty_list`

#### `RoaPrefixGraphQLTestCase`

- `test_get_roaprefix_by_id`
- `test_get_roaprefix_with_invalid_id_returns_null_or_error`
- `test_list_roaprefixes_without_filters`
- `test_filter_roaprefixes_by_prefix_id`
- `test_filter_roaprefixes_by_roa_name_id`
- `test_filter_roaprefixes_with_invalid_roa_name_id_returns_empty_list`

#### `CertificatePrefixGraphQLTestCase`

- `test_get_certificateprefix_by_id`
- `test_get_certificateprefix_with_invalid_id_returns_null_or_error`
- `test_list_certificateprefixes_without_filters`
- `test_filter_certificateprefixes_by_prefix_id`
- `test_filter_certificateprefixes_by_certificate_name_id`
- `test_filter_certificateprefixes_with_invalid_certificate_name_id_returns_empty_list`

#### `CertificateAsnGraphQLTestCase`

- `test_get_certificateasn_by_id`
- `test_get_certificateasn_with_invalid_id_returns_null_or_error`
- `test_list_certificateasns_without_filters`
- `test_filter_certificateasns_by_asn_id`
- `test_filter_certificateasns_by_certificate_name2_id`
- `test_filter_certificateasns_with_invalid_certificate_name2_id_returns_empty_list`

## Browser Test Modules

Use Playwright only after server-side form, API, and GraphQL contracts are stable.

### Proposed Layout

- `tests/e2e/auth.setup.ts`
- `tests/e2e/netbox-rpki/navigation.spec.ts`
- `tests/e2e/netbox-rpki/organizations.spec.ts`
- `tests/e2e/netbox-rpki/certificates.spec.ts`
- `tests/e2e/netbox-rpki/certificate-prefixes.spec.ts`
- `tests/e2e/netbox-rpki/certificate-asns.spec.ts`
- `tests/e2e/netbox-rpki/roas.spec.ts`
- `tests/e2e/netbox-rpki/roa-prefixes.spec.ts`

### `tests/e2e/auth.setup.ts`

- log in with the local admin user created by `dev.sh start`
- save storage state for reuse by the rest of the suite

### `tests/e2e/netbox-rpki/navigation.spec.ts`

- `shows_plugin_menu_entries_for_organizations_certificates_and_roas`
- `navigates_to_organization_list_from_plugin_menu`
- `navigates_to_certificate_list_from_plugin_menu`
- `navigates_to_roa_list_from_plugin_menu`
- `deep_links_to_hidden_certificateprefix_list`
- `deep_links_to_hidden_certificateasn_list`
- `deep_links_to_hidden_roaprefix_list`

### `tests/e2e/netbox-rpki/organizations.spec.ts`

- `creates_organization_with_valid_input`
- `shows_inline_errors_for_invalid_organization_submission`
- `shows_required_errors_for_empty_organization_submission`
- `edits_organization`
- `deletes_organization`
- `organization_detail_shows_certificates_table`
- `organization_detail_add_certificate_button_prefills_rpki_org`

### `tests/e2e/netbox-rpki/certificates.spec.ts`

- `creates_certificate_with_valid_input`
- `shows_inline_errors_for_invalid_certificate_submission`
- `shows_required_errors_for_empty_certificate_submission`
- `edits_certificate`
- `certificate_detail_shows_related_tables`
- `certificate_detail_add_prefix_button_prefills_certificate_name`
- `certificate_detail_add_asn_button_prefills_certificate_name2`
- `certificate_detail_add_roa_button_prefills_signed_by`

### `tests/e2e/netbox-rpki/certificate-prefixes.spec.ts`

- `creates_certificateprefix_with_valid_input`
- `shows_required_errors_for_empty_certificateprefix_submission`
- `edits_certificateprefix`
- `deletes_certificateprefix`
- `certificateprefix_detail_links_back_to_certificate_and_prefix`

### `tests/e2e/netbox-rpki/certificate-asns.spec.ts`

- `creates_certificateasn_with_valid_input`
- `shows_required_errors_for_empty_certificateasn_submission`
- `edits_certificateasn`
- `deletes_certificateasn`
- `certificateasn_detail_links_back_to_certificate_and_asn`

### `tests/e2e/netbox-rpki/roas.spec.ts`

- `creates_roa_with_valid_input`
- `shows_inline_errors_for_invalid_roa_submission`
- `shows_required_errors_for_empty_roa_submission`
- `edits_roa`
- `roa_detail_shows_roaprefix_table`
- `roa_detail_renders_valid_from_and_valid_to`
- `roa_detail_add_roaprefix_button_prefills_roa_name`

### `tests/e2e/netbox-rpki/roa-prefixes.spec.ts`

- `creates_roaprefix_with_valid_input`
- `shows_required_errors_for_empty_roaprefix_submission`
- `edits_roaprefix`
- `deletes_roaprefix`
- `roaprefix_detail_links_back_to_roa_and_prefix`

## Phase Order

### Phase 1: Shared Fixtures

- add helper builders and payload helpers
- add `setUpTestData` object graphs for reuse
- prove helpers create valid transitive objects deterministically

### Phase 2: Models and Forms

- land `test_models.py`
- expand `test_forms.py`
- pin minimal, maximal, invalid, and empty payload behavior for all six resources

### Phase 3: Filtersets, Tables, Templates, Navigation

- land `test_filtersets.py`
- land `test_tables.py`
- land `test_templates.py`
- land `test_navigation.py`

### Phase 4: Web Views

- land `test_views.py`
- verify every route renders and all CRUD flows have valid, invalid, and empty coverage

### Phase 5: REST API

- expand `test_api.py` from smoke-only to full CRUD and filter coverage
- add a plugin namespace mixin so API helper classes resolve the correct route names

### Phase 6: GraphQL

- land `test_graphql.py`
- verify each singular and list query with valid, invalid, and empty filter behavior

### Phase 7: Browser Clickthrough

- add Playwright setup and end-to-end specs
- keep browser tests focused on real workflows and template/query-string correctness

## Current Expected Failures and Validation Gaps

These are important because some “invalid input” cases should currently pass until application validation is added.

### Known Rendering or Wiring Bugs

- `netbox_rpki/tables.py` uses `publicKey` instead of `public_key` in `CertificateTable.Meta.fields`
- `netbox_rpki/templates/netbox_rpki/roa.html` renders `date_from` and `date_to` instead of `valid_from` and `valid_to`
- `netbox_rpki/templates/netbox_rpki/certificate.html` uses the wrong query-string parameter names for child add buttons
- `netbox_rpki/templates/netbox_rpki/roa.html` uses the wrong query-string parameter name for the ROA Prefix add button

### Validation Gaps

- `Organization.ext_url` is a `CharField`, not a `URLField`
- `Organization` has no uniqueness constraint on `org_id`
- `Certificate` has no validity-window validation
- `Certificate` has no URL validation for `publication_url` or `ca_repository`
- `Roa.origin_as` is nullable
- `Roa` has no consistency validation against the signing certificate
- `RoaPrefix.max_length` has no semantic bounds validation against the selected prefix
- `CertificatePrefix`, `CertificateAsn`, and `RoaPrefix` have no duplicate-pair uniqueness constraints
- relationship models do not enforce tenant consistency across linked objects

The suite should mark these explicitly when adding invalid-input tests:

- invalid case already rejected today
- invalid case currently accepted because validation is missing
- invalid case should become an expected failure until validation code is added

## Definition of Done

This plan is complete only when:

- every route in `netbox_rpki/urls.py` has success-path test coverage
- every create and edit surface has valid, invalid, and empty-input coverage
- every REST resource has CRUD and filter coverage
- every GraphQL query has valid, invalid, and empty filter coverage
- every custom template is rendered in populated and empty-state scenarios
- browser tests prove menu-to-detail-to-child-object clickthrough works
- known template and query-string regressions are pinned by tests