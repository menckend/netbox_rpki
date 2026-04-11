from django.test import SimpleTestCase

from netbox_rpki import navigation


class NavigationTestCase(SimpleTestCase):
    def test_resource_menu_items_match_expected_links(self):
        self.assertEqual([item.link_text for item in navigation.resource_menu_items], ['RIR Customer Orgs', 'Resource Certificates'])
        self.assertEqual(
            [item.link for item in navigation.resource_menu_items],
            ['plugins:netbox_rpki:organization_list', 'plugins:netbox_rpki:certificate_list'],
        )

    def test_roa_menu_items_match_expected_links(self):
        self.assertEqual([item.link_text for item in navigation.roa_menu_items], ['ROAs'])
        self.assertEqual([item.link for item in navigation.roa_menu_items], ['plugins:netbox_rpki:roa_list'])

    def test_default_navigation_exports_top_level_menu(self):
        self.assertEqual(navigation.menu.label, 'RPKI')
        self.assertEqual([group.label for group in navigation.menu.groups], ['Resources', 'ROAs'])
        self.assertEqual(navigation.menu.icon_class, 'mdi mdi-bootstrap')