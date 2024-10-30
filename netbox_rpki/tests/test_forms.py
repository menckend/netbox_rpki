from http import HTTPStatus

from django.test import TestCase

from netbox_rpki.forms import gns3srvForm


class TestGns3srvFormCase(TestCase):
    def test_gns3srv_valid(self):
        form = gns3srvForm(
            data={
                'value': 'myserver.notyourserver',
                'status': 'active'
            }
        )
        self.assertEqual(
            form.errors.get('value'), None
        )
