from django.test import SimpleTestCase

from netbox_rpki import navigation
from netbox_rpki.object_registry import get_navigation_groups
from netbox_rpki.tests.registry_scenarios import EXPECTED_NAVIGATION_GROUPS, EXPECTED_NAVIGATION_LINKS


class NavigationTestCase(SimpleTestCase):
    def test_navigation_registry_exposes_expected_groups(self):
        self.assertEqual(
            [(group_name, [spec.key for spec in specs]) for group_name, specs in get_navigation_groups()],
            [(group_name, list(object_keys)) for group_name, object_keys in EXPECTED_NAVIGATION_GROUPS],
        )

    def test_navigation_specs_use_structured_metadata(self):
        groups = dict(get_navigation_groups())
        self.assertEqual(groups['Resources'][0].navigation.label, 'RIR Customer Orgs')
        self.assertEqual(groups['ROAs'][0].navigation.order, 10)
        self.assertEqual(groups['ROAs'][0].routes.add_url_name, 'plugins:netbox_rpki:roa_add')

    def test_resource_menu_items_match_expected_links(self):
        self.assertEqual(
            [item.link_text for item in navigation.resource_menu_items],
            [label for label, _link in EXPECTED_NAVIGATION_LINKS['Resources']],
        )
        self.assertEqual(
            [item.link for item in navigation.resource_menu_items],
            [link for _label, link in EXPECTED_NAVIGATION_LINKS['Resources']],
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

    def test_default_navigation_exports_top_level_menu(self):
        self.assertEqual(navigation.menu.label, 'RPKI')
        self.assertEqual([group.label for group in navigation.menu.groups], ['Resources', 'ROAs'])
        self.assertEqual(navigation.menu.icon_class, 'mdi mdi-bootstrap')