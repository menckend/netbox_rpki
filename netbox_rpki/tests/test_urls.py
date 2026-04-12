from django.test import SimpleTestCase
from django.urls import resolve, reverse
from django.urls.resolvers import URLResolver

from netbox_rpki.object_registry import VIEW_OBJECT_SPECS
from netbox_rpki.tests.registry_scenarios import EXPECTED_MODEL_CHILD_INCLUDE_ROUTES, EXPECTED_ROUTE_PATHS
from netbox_rpki.urls import urlpatterns


class UrlRegistrationTestCase(SimpleTestCase):
    def test_standard_routes_reverse_to_stable_paths(self):
        for spec in VIEW_OBJECT_SPECS:
            expected_paths = EXPECTED_ROUTE_PATHS[spec.key]
            route_slug = spec.routes.slug

            with self.subTest(object_key=spec.key):
                self.assertEqual(reverse(spec.routes.list_url_name), expected_paths['list'])
                self.assertEqual(
                    reverse(f'plugins:netbox_rpki:{route_slug}', kwargs={'pk': 1}),
                    expected_paths['detail'],
                )
                if spec.view.supports_create:
                    self.assertEqual(reverse(spec.routes.add_url_name), expected_paths['add'])
                    self.assertEqual(
                        reverse(f'plugins:netbox_rpki:{route_slug}_edit', kwargs={'pk': 1}),
                        expected_paths['edit'],
                    )
                if spec.view.supports_delete:
                    self.assertEqual(
                        reverse(f'plugins:netbox_rpki:{route_slug}_delete', kwargs={'pk': 1}),
                        expected_paths['delete'],
                    )

    def test_standard_routes_resolve_to_stable_names(self):
        for spec in VIEW_OBJECT_SPECS:
            expected_paths = EXPECTED_ROUTE_PATHS[spec.key]
            route_slug = spec.routes.slug

            with self.subTest(object_key=spec.key):
                self.assertEqual(resolve(expected_paths['list']).view_name, spec.routes.list_url_name)
                self.assertEqual(resolve(expected_paths['detail']).view_name, f'plugins:netbox_rpki:{route_slug}')
                if spec.view.supports_create:
                    self.assertEqual(resolve(expected_paths['add']).view_name, spec.routes.add_url_name)
                    self.assertEqual(resolve(expected_paths['edit']).view_name, f'plugins:netbox_rpki:{route_slug}_edit')
                if spec.view.supports_delete:
                    self.assertEqual(resolve(expected_paths['delete']).view_name, f'plugins:netbox_rpki:{route_slug}_delete')

    def test_each_object_registers_model_child_url_include(self):
        self.assertEqual(
            [pattern.pattern._route for pattern in urlpatterns if isinstance(pattern, URLResolver)],
            list(EXPECTED_MODEL_CHILD_INCLUDE_ROUTES),
        )
