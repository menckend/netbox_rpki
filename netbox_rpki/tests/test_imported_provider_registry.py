from django.urls import reverse

from netbox_rpki.object_registry import get_object_spec
from netbox_rpki.tests.base import PluginViewTestCase, TestCase
from netbox_rpki.tests.registry_scenarios import _build_instance_for_spec


NEW_IMPORTED_PROVIDER_KEYS = (
    'importedcametadata',
    'importedparentlink',
    'importedchildlink',
    'importedresourceentitlement',
    'importedpublicationpoint',
)


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