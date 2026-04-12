from django.test import SimpleTestCase

from netbox_rpki.tests.krill_payloads import (
    KRILL_CA_METADATA_JSON,
    KRILL_CHILD_CONNECTIONS_JSON,
    KRILL_CHILD_INFO_JSON,
    KRILL_PARENT_CONTACT_JSON,
    KRILL_PARENT_STATUSES_JSON,
    KRILL_REPO_DETAILS_JSON,
    KRILL_REPO_STATUS_JSON,
)


class KrillPayloadFixturesTestCase(SimpleTestCase):
    def test_confirmed_tier_one_payloads_match_documented_shapes(self):
        self.assertEqual(KRILL_CA_METADATA_JSON['handle'], 'netbox-rpki-dev')
        self.assertEqual(KRILL_CA_METADATA_JSON['children'], ['edge-customer-01'])

        self.assertIn('testbed', KRILL_PARENT_STATUSES_JSON)
        self.assertEqual(KRILL_PARENT_CONTACT_JSON['parent_handle'], 'testbed')

        self.assertEqual(KRILL_CHILD_INFO_JSON['state'], 'active')
        self.assertEqual(KRILL_CHILD_CONNECTIONS_JSON['children'][0]['handle'], 'edge-customer-01')

        self.assertIn('repo_info', KRILL_REPO_DETAILS_JSON)
        self.assertEqual(len(KRILL_REPO_STATUS_JSON['published']), 2)