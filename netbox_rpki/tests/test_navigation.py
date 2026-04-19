from django.test import SimpleTestCase
from django.urls import reverse

from netbox_rpki import navigation
from netbox_rpki.maturity import get_badge
from netbox_rpki.object_registry import get_navigation_groups
from netbox_rpki.tests.registry_scenarios import EXPECTED_NAVIGATION_GROUPS, EXPECTED_NAVIGATION_LINKS


class NavigationTestCase(SimpleTestCase):
    def test_navigation_registry_exposes_expected_groups(self):
        self.assertEqual(
            [(group_name, [spec.registry_key for spec in specs]) for group_name, specs in get_navigation_groups()],
            [(group_name, list(object_keys)) for group_name, object_keys in EXPECTED_NAVIGATION_GROUPS],
        )

    def test_navigation_specs_use_structured_metadata(self):
        groups = dict(get_navigation_groups())
        for group_name, specs in groups.items():
            with self.subTest(group_name=group_name):
                self.assertTrue(specs)
                self.assertTrue(all(spec.navigation is not None for spec in specs))

    def test_resource_menu_items_match_expected_links(self):
        self.assertEqual(
            [item.link_text for item in navigation.resource_menu_items],
            [label for label, _link in EXPECTED_NAVIGATION_LINKS['Resources']] + ['Provider Sync Health', 'Operations'],
        )
        self.assertEqual(
            [item.link for item in navigation.resource_menu_items],
            [link for _label, link in EXPECTED_NAVIGATION_LINKS['Resources']] + [
                'plugins:netbox_rpki:provideraccount_summary',
                'plugins:netbox_rpki:operations_dashboard',
            ],
        )

    def test_provider_sync_health_menu_item_has_expected_permissions(self):
        provider_sync_health_item = navigation.resource_menu_items[-2]

        self.assertEqual(provider_sync_health_item.link_text, 'Provider Sync Health')
        self.assertEqual(provider_sync_health_item.link, 'plugins:netbox_rpki:provideraccount_summary')
        self.assertEqual(provider_sync_health_item.url, reverse('plugins:netbox_rpki:provideraccount_summary'))
        self.assertEqual(
            provider_sync_health_item.permissions,
            [
                'netbox_rpki.view_rpkiprovideraccount',
            ],
        )

    def test_operations_menu_item_has_expected_permissions(self):
        operations_item = navigation.resource_menu_items[-1]

        self.assertEqual(operations_item.link_text, 'Operations')
        self.assertEqual(operations_item.link, 'plugins:netbox_rpki:operations_dashboard')
        self.assertEqual(operations_item.url, reverse('plugins:netbox_rpki:operations_dashboard'))
        self.assertEqual(
            operations_item.permissions,
            [
                'netbox_rpki.view_rpkiprovideraccount',
                'netbox_rpki.view_roaobject',
                'netbox_rpki.view_certificate',
            ],
        )

    def test_roa_menu_items_match_expected_links(self):
        self.assertEqual(
            [item.link_text for item in navigation.roa_menu_items],
            [label for label, _link in EXPECTED_NAVIGATION_LINKS['ROAs']],
        )
        self.assertEqual(
            [item.link for item in navigation.roa_menu_items],
            [link for _label, link in EXPECTED_NAVIGATION_LINKS['ROAs']],
        )

    def test_default_navigation_exports_top_level_menus(self):
        self.assertEqual(
            [m.label for m in navigation.menus],
            [f'RPKI {group_name}{get_badge(group_name)}' for group_name, _ in EXPECTED_NAVIGATION_GROUPS],
        )
        for m in navigation.menus:
            with self.subTest(label=m.label):
                self.assertEqual(m.icon_class, 'mdi mdi-bootstrap')

    def test_intent_authority_map_menu_item_is_first_in_intent_group(self):
        items = navigation.navigation_groups.get('Intent', ())

        self.assertTrue(items)
        self.assertEqual(items[0].link_text, 'Intent Authority Map')
        self.assertEqual(items[0].link, 'plugins:netbox_rpki:intent_authority_map')
        self.assertEqual(
            items[0].permissions,
            [
                'netbox_rpki.view_roaintent',
                'netbox_rpki.view_roaintentresult',
                'netbox_rpki.view_roareconciliationrun',
            ],
        )
