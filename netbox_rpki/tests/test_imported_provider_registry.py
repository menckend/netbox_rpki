from django.urls import reverse

from netbox_rpki import models as rpki_models
from netbox_rpki.object_registry import get_object_spec
from netbox_rpki.tests.base import PluginViewTestCase, TestCase
from netbox_rpki.tests.registry_scenarios import _build_instance_for_spec
from netbox_rpki.tests.utils import (
    create_test_external_object_reference,
    create_test_imported_aspa,
    create_test_imported_ca_metadata,
    create_test_imported_certificate_observation,
    create_test_imported_child_link,
    create_test_imported_parent_link,
    create_test_imported_publication_point,
    create_test_imported_resource_entitlement,
    create_test_imported_roa_authorization,
    create_test_imported_signed_object,
    create_test_organization,
    create_test_provider_account,
    create_test_provider_snapshot,
)


NEW_IMPORTED_PROVIDER_KEYS = (
    'importedcametadata',
    'importedparentlink',
    'importedchildlink',
    'importedresourceentitlement',
    'importedpublicationpoint',
    'importedcertificateobservation',
)

IMPORTED_OBJECT_KEYS_WITH_EXTERNAL_REFERENCE = (
    'importedroaauthorization',
    'importedaspa',
    'importedcametadata',
    'importedparentlink',
    'importedchildlink',
    'importedresourceentitlement',
    'importedpublicationpoint',
    'importedsignedobject',
    'importedcertificateobservation',
)


def _build_imported_object_with_external_reference(registry_key):
    organization = create_test_organization(
        org_id=f'{registry_key}-org',
        name=f'{registry_key} Organization',
    )
    provider_account = create_test_provider_account(
        name=f'{registry_key} Provider Account',
        organization=organization,
        org_handle=f'{registry_key[:20].upper()}',
    )
    provider_snapshot = create_test_provider_snapshot(
        name=f'{registry_key} Snapshot',
        organization=organization,
        provider_account=provider_account,
    )
    external_reference = create_test_external_object_reference(
        name=f'{registry_key} External Reference',
        organization=organization,
        provider_account=provider_account,
        last_seen_provider_snapshot=provider_snapshot,
        object_type=rpki_models.ExternalObjectType.ROA_AUTHORIZATION,
        provider_identity=f'{registry_key}-provider-identity',
        external_object_id=f'{registry_key}-external-object',
    )

    builders = {
        'importedroaauthorization': lambda: create_test_imported_roa_authorization(
            name='Imported ROA Authorization With External Reference',
            organization=organization,
            provider_snapshot=provider_snapshot,
            prefix_cidr_text='10.10.10.0/24',
            origin_asn_value=64510,
            max_length=24,
            external_object_id='imported-roa-auth-external-object',
            external_reference=external_reference,
        ),
        'importedaspa': lambda: create_test_imported_aspa(
            name='Imported ASPA With External Reference',
            organization=organization,
            provider_snapshot=provider_snapshot,
            customer_as_value=64511,
            external_object_id='imported-aspa-external-object',
            external_reference=external_reference,
        ),
        'importedcametadata': lambda: create_test_imported_ca_metadata(
            name='Imported CA Metadata With External Reference',
            organization=organization,
            provider_snapshot=provider_snapshot,
            external_object_id='imported-ca-metadata-external-object',
            external_reference=external_reference,
        ),
        'importedparentlink': lambda: create_test_imported_parent_link(
            name='Imported Parent Link With External Reference',
            organization=organization,
            provider_snapshot=provider_snapshot,
            external_object_id='imported-parent-link-external-object',
            external_reference=external_reference,
        ),
        'importedchildlink': lambda: create_test_imported_child_link(
            name='Imported Child Link With External Reference',
            organization=organization,
            provider_snapshot=provider_snapshot,
            external_object_id='imported-child-link-external-object',
            external_reference=external_reference,
        ),
        'importedresourceentitlement': lambda: create_test_imported_resource_entitlement(
            name='Imported Resource Entitlement With External Reference',
            organization=organization,
            provider_snapshot=provider_snapshot,
            external_object_id='imported-resource-entitlement-external-object',
            external_reference=external_reference,
        ),
        'importedpublicationpoint': lambda: create_test_imported_publication_point(
            name='Imported Publication Point With External Reference',
            organization=organization,
            provider_snapshot=provider_snapshot,
            external_object_id='imported-publication-point-external-object',
            external_reference=external_reference,
        ),
        'importedsignedobject': lambda: create_test_imported_signed_object(
            name='Imported Signed Object With External Reference',
            organization=organization,
            provider_snapshot=provider_snapshot,
            external_object_id='imported-signed-object-external-object',
            external_reference=external_reference,
        ),
        'importedcertificateobservation': lambda: create_test_imported_certificate_observation(
            name='Imported Certificate Observation With External Reference',
            organization=organization,
            provider_snapshot=provider_snapshot,
            external_object_id='imported-certificate-observation-external-object',
            external_reference=external_reference,
        ),
    }

    return builders[registry_key]()


class ImportedProviderRegistrySpecTestCase(TestCase):
    def test_new_imported_provider_specs_are_read_only(self):
        for registry_key in NEW_IMPORTED_PROVIDER_KEYS:
            spec = get_object_spec(registry_key)
            with self.subTest(registry_key=registry_key):
                self.assertTrue(spec.api.read_only)
                self.assertFalse(spec.view.supports_create)
                self.assertFalse(spec.view.supports_delete)


class ImportedProviderGeneratedSurfaceTestCase(PluginViewTestCase):
    def test_new_imported_provider_objects_render_generated_list_and_detail_views(self):
        for registry_key in NEW_IMPORTED_PROVIDER_KEYS:
            spec = get_object_spec(registry_key)
            instance = _build_instance_for_spec(spec, token=f'{registry_key}-surface')
            self.add_permissions(f'netbox_rpki.view_{spec.model._meta.model_name}')

            list_response = self.client.get(reverse(spec.list_url_name))
            detail_response = self.client.get(instance.get_absolute_url())

            with self.subTest(registry_key=registry_key, instance=instance.pk):
                self.assertHttpStatus(list_response, 200)
                self.assertHttpStatus(detail_response, 200)
                self.assertTemplateUsed(detail_response, 'netbox_rpki/object_detail.html')

    def test_imported_object_detail_views_render_with_populated_external_reference(self):
        for registry_key in IMPORTED_OBJECT_KEYS_WITH_EXTERNAL_REFERENCE:
            spec = get_object_spec(registry_key)
            self.add_permissions(f'netbox_rpki.view_{spec.model._meta.model_name}')

            with self.subTest(registry_key=registry_key):
                instance = _build_imported_object_with_external_reference(registry_key)
                response = self.client.get(instance.get_absolute_url())
                self.assertHttpStatus(response, 200)
                self.assertTemplateUsed(response, 'netbox_rpki/object_detail.html')